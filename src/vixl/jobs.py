"""Durable workspace jobs. Local work is resumable; uncertain inference is never blindly retried."""

import base64
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import asdict
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid
from urllib.parse import quote

from filelock import FileLock, Timeout

from .automation import bounded_object
from .errors import VixlError, require
from .model import Limits
from .production import read_json, write_json, write_bytes, file_digest, publish_file


class Queue:
    def __init__(self, workspace, limits=None):
        self.workspace = Path(workspace).resolve()
        self.directory = self.workspace / ".vixl-jobs"
        self.limits = limits or Limits()

    def resolve(self, value):
        from .film import local_path

        return local_path(self.workspace, value)

    def path(self, ident):
        require(
            isinstance(ident, str) and len(ident) == 32 and all(c in "0123456789abcdef" for c in ident),
            "Invalid job ID",
        )
        return self.directory / (ident + ".json")

    def status(self, ident):
        job = read_json(self.path(ident))
        require(
            isinstance(job, dict) and job.get("version") == 1 and job.get("id") == ident,
            "Unsupported job record",
        )
        job["outcome"] = job_outcome(job)
        return job

    def save(self, job):
        job["updated"] = time.time()
        job["outcome"] = job_outcome(job)
        write_json(self.path(job["id"]), job)

    def submit(self, payload):
        from .project import Project
        from .production import plan
        from .film import plan as film_plan

        bounded_object(
            payload, {"kind", "source", "spec", "output", "provider", "request"}, "Unknown job field"
        )
        payload = deepcopy(payload)
        kind = payload.get("kind")
        require(kind in ("production", "film", "generate", "video", "lyric-video", "form-fill"), "Unknown job kind")
        fields = ({"spec"} if kind in ("production", "film") else {"request"} if kind in ("lyric-video", "form-fill")
                  else {"provider", "request"})
        require(fields <= payload.keys(), "Missing job fields", required=sorted(fields))
        require(isinstance(payload.get("output"), str), "Job needs an output path")
        output = self.resolve(payload["output"])
        require(
            not output.is_relative_to(self.directory) and output != self.workspace,
            "Output cannot target queue storage or workspace root",
        )
        require(kind == "production" or not output.exists(), "Job output already exists")
        if kind == "production":
            plan(payload["spec"])
        elif kind == "film":
            film_plan(payload["spec"], self.limits, output.suffix.lower() in (".mp4", ".webm"))
        elif kind == "video":
            require(output.suffix.lower() in (".mp4", ".webm"), "Video output must be MP4 or WebM")
            self.video_backend(payload["provider"])
            bounded_object(
                payload["request"],
                {"prompt", "model", "width", "height", "duration", "source_asset"},
                "Unknown video request field",
            )
            require(
                isinstance(payload["request"].get("prompt"), str)
                and len(payload["request"]["prompt"]) <= 100000,
                "Video needs a bounded prompt",
            )
            self.limits.size(payload["request"]["width"], payload["request"]["height"])
            from .model import finite

            finite(payload["request"]["duration"], "video duration", 0.1, 600)
        if kind == "lyric-video":
            from .lyrics import plan as lyric_plan

            require(isinstance(payload["request"], dict), "Lyric video job request must be an object")
            payload["request"] = {**payload["request"], "output": payload["output"]}
            require(output.suffix.lower() in (".mp4", ".webm"), "Lyric video output must be MP4 or WebM")
            require(isinstance(payload["request"].get("build"), str), "Lyric video jobs need a build path")
            require(not self.resolve(payload["request"]["build"]).exists(), "Lyric video build already exists")
            lyric_plan(payload["request"], self.workspace, self.limits)
        if kind == "form-fill":
            request = payload["request"]
            require(isinstance(request, dict), "Form fill job request must be an object")
            bounded_object(request, {"data", "name", "format", "mode", "skip_invalid", "check", "unknown", "dpi",
                                     "retain_inputs"}, "Unknown form fill request field")
            require(isinstance(request.get("data"), str), "Form fill jobs need a data CSV")
            require(output.suffix.lower() in (".pdf", ".zip"), "Form fill job output is a combined .pdf or a .zip of files")
            require(isinstance(payload.get("source"), str), "Form fill jobs need the source form document")
            from .forms import read_rows

            read_rows(self.resolve(request["data"]))
        if kind == "generate":
            require(output.suffix == ".vixl", "Generated image jobs save an editable .vixl document")
            bounded_object(
                payload["request"],
                {"prompt", "negative_prompt", "width", "height", "mode", "seed", "model", "strength"},
                "Unknown generation request field",
            )
            require(isinstance(payload["request"].get("prompt"), str), "Generation requires a prompt")
            self.limits.size(payload["request"]["width"], payload["request"]["height"])
            require(
                payload["request"].get("mode", "generate") == "generate",
                "Queued image generation uses generate mode",
            )
            require(
                isinstance(payload.get("provider"), str), "Pin an explicit provider for queued generation"
            )
        ident = uuid.uuid4().hex
        folder = self.directory / ident
        folder.mkdir(parents=True)
        if payload.get("source"):
            source = Project.load(self.resolve(payload["source"]), limits=self.limits)
            source.path, source._revision = None, None
            source.save(folder / "source.vixl")
            payload["source"] = str((folder / "source.vixl").relative_to(self.workspace))
        require(
            kind not in ("production", "generate", "form-fill") or payload.get("source"), "Job needs a source document"
        )
        if kind == "form-fill":
            # Freeze the data (personal data: deleted when the job ends unless retain_inputs).
            from .assets import read_bounded

            source = self.resolve(payload["request"]["data"])
            destination = folder / "input-data.csv"
            write_bytes(destination, read_bounded(source, 8 * 1024 * 1024))
            payload["request"]["data"] = str(destination.relative_to(self.workspace))
        if kind == "lyric-video":
            # Freeze the song, lyrics and template; the worker builds and renders from these copies.
            from .assets import read_bounded

            request = payload["request"]
            for key in ("audio", "lyrics", "template"):
                source = self.resolve(request[key])
                destination = folder / (f"input-{key}" + source.suffix)
                write_bytes(destination, read_bounded(source, self.limits.max_project_bytes))
                request[key] = str(destination.relative_to(self.workspace))
        if kind == "film":
            # Freeze media inputs so edits outside the queue cannot alter a submitted film.
            from .assets import read_bounded

            for i, item in enumerate(payload["spec"]["shots"] + payload["spec"].get("audio", [])):
                source = self.resolve(item["source"])
                destination = folder / (f"input-{i}" + source.suffix)
                write_bytes(destination, read_bounded(source, self.limits.max_project_bytes))
                item["source"] = str(destination.relative_to(self.workspace))
        job = {
            "version": 1,
            "id": ident,
            "created": time.time(),
            "status": "queued",
            "payload": payload,
            "progress": {"done": 0},
            "attempts": 0,
            "limits": asdict(self.limits),
        }
        self.save(job)
        return job

    def cancel(self, ident):
        job = self.status(ident)
        if job["status"] not in ("completed", "failed", "cancelled", "needs_review"):
            write_bytes(self.directory / (ident + ".cancel"), b"cancel", replace=True)
        return {
            "id": ident,
            "cancel_requested": True,
            "note": "Cancellation stops local work at a safe boundary; remote generation may still finish.",
        }

    def cancelled(self, ident):
        return (self.directory / (ident + ".cancel")).exists()

    def form_fill_step(self, job, limits, progress):
        """Fill a frozen form from frozen rows into one combined PDF or a ZIP of files, then
        delete the data copy (unless ``retain_inputs``)."""
        import shutil
        import tempfile
        import zipfile

        from .forms import fill_data
        from .project import Project

        payload, ident = job["payload"], job["id"]
        request = payload["request"]
        data = self.resolve(request["data"])
        checkpoint = self.checkpoint_path(job)
        try:
            if not checkpoint.exists():
                project = Project.load(self.resolve(payload["source"]), limits=limits)
                options = {k: request[k] for k in ("mode", "skip_invalid", "check", "unknown", "dpi") if k in request}
                if checkpoint.suffix == ".pdf":
                    report = fill_data(project, data, combine=checkpoint, cancelled=lambda: self.cancelled(ident), **options)
                else:
                    staging = Path(tempfile.mkdtemp(prefix="vixl-form-job-"))
                    try:
                        report = fill_data(project, data, staging / "out", name=request.get("name", "{row}"),
                                           format=request.get("format", "pdf"), cancelled=lambda: self.cancelled(ident),
                                           progress=progress, **options)
                        with zipfile.ZipFile(checkpoint, "w", zipfile.ZIP_DEFLATED) as archive:
                            for item in report.get("outputs", []):
                                name = Path(item["output"]).name
                                info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
                                archive.writestr(info, Path(item["output"]).read_bytes())
                                item["output"] = name
                    finally:
                        shutil.rmtree(staging, ignore_errors=True)
                report.pop("output", None)
                job["result"] = report
            self.publish_checkpoint(job)
        finally:
            if not request.get("retain_inputs") and (job["status"] in ("completed", "cancelled") or self.cancelled(ident)):
                data.unlink(missing_ok=True)

    def checkpoint_path(self, job):
        suffix = ".vixl" if job["payload"]["kind"] == "generate" else Path(job["payload"]["output"]).suffix
        return self.directory / job["id"] / ("result" + suffix)

    def publish_checkpoint(self, job):
        source = self.checkpoint_path(job)
        checksum = file_digest(source)
        job.setdefault("result", {}).update(
            checkpoint=str(source.relative_to(self.workspace)), sha256=checksum
        )
        if self.cancelled(job["id"]):
            job["status"] = "cancelled"
            return
        output = self.resolve(job["payload"]["output"])
        if output.exists():
            require(file_digest(output) == checksum, "Job output already exists with different content")
        else:
            publish_file(output, source)
        job["result"]["output"] = job["payload"]["output"]
        job["status"] = "completed"

    def resume(self, ident):
        with FileLock(str(self.path(ident)) + ".worker", timeout=1):
            job = self.status(ident)
            require(
                job["status"] in ("failed", "needs_review", "cancelled", "waiting"), "Job is not resumable"
            )
            require(
                not (
                    job["payload"]["kind"] == "generate"
                    and job.get("request_started")
                    and not self.checkpoint_path(job).exists()
                ),
                "Cannot safely retry uncertain image inference; check the provider and submit a new job",
            )
            marker = self.directory / (ident + ".cancel")
            if marker.exists():
                marker.unlink()
            job.update(status="queued", next_poll=0)
            job["attempts"] = 0
            self.save(job)
            return job

    @staticmethod
    def video_backend(name):
        from .ai import provider, HTTPProvider

        backend = provider(name)
        require(
            type(backend) is HTTPProvider and "video" in backend.config.get("capabilities", []),
            "Video requires an explicitly configured HTTP gateway advertising video",
            "unsupported_capability",
        )
        return backend

    def video_step(self, job):
        payload, ident = job["payload"], job["id"]
        limits = Limits(**job.get("limits", asdict(self.limits)))
        backend = self.video_backend(payload["provider"])
        if job.get("remote_id"):
            result = backend.json("GET", "/video/jobs/" + quote(job["remote_id"], safe=""))
        elif job.get("request_started"):
            result = backend.json("GET", "/video/jobs/by-key/" + ident)
            require(
                result.get("status") != "not_found",
                "Uncertain submission: gateway cannot find request key",
                "remote_unknown",
            )
        else:
            job["request_started"] = True
            self.save(job)
            request = deepcopy(payload["request"])
            if request.get("source_asset"):
                from .project import Project

                require(payload.get("source"), "Reference asset requires source document")
                project = Project.load(self.resolve(payload["source"]), limits=limits)
                asset = request.pop("source_asset")
                require(asset in project.assets, "Missing reference image")
                request["source_image"] = base64.b64encode(project.assets[asset]).decode()
            result = backend.json("POST", "/video/jobs", json={**request, "client_id": ident})
        require(
            result.get("status") in ("queued", "running", "completed", "failed"), "Invalid video job status"
        )
        require(
            isinstance(result.get("id"), str) and 0 < len(result["id"]) <= 200, "Video gateway needs a job ID"
        )
        require(
            not job.get("remote_id") or result["id"] == job["remote_id"], "Video gateway changed job identity"
        )
        job["remote_id"] = result["id"]
        self.save(job)
        if self.cancelled(ident):
            job["status"] = "cancelled"
            return
        if result["status"] == "failed":
            job.update(
                status="failed", error={"code": "provider_error", "message": "Video generation failed"}
            )
            return
        if result["status"] != "completed":
            job["status"] = "waiting"
            job["next_poll"] = time.time() + 2
            return
        import binascii

        encoded = result.get("video_base64")
        require(
            isinstance(encoded, str) and len(encoded) <= limits.max_asset_bytes * 4 // 3 + 8,
            "Video response exceeds asset limit",
            "resource_limit",
        )
        try:
            data = base64.b64decode(encoded, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise VixlError("provider_error", "Video gateway returned invalid base64") from exc
        require(len(data) <= limits.max_asset_bytes, "Video response exceeds asset limit", "resource_limit")
        output = self.resolve(payload["output"])
        expected = "mp4" if output.suffix.lower() == ".mp4" else "webm"
        require(result.get("format") == expected, "Video output format mismatch")
        require(
            (expected == "mp4" and data[4:8] == b"ftyp")
            or (expected == "webm" and data.startswith(b"\x1a\x45\xdf\xa3")),
            "Invalid video container",
        )
        if output.exists():
            require(output.read_bytes() == data, "Video destination already exists")
        else:
            write_bytes(output, data)
        job["result"] = {
            "output": payload["output"],
            "sha256": hashlib.sha256(data).hexdigest(),
            "provider": payload["provider"],
            "remote_id": job["remote_id"],
        }
        job["status"] = "completed"

    def work_one(self, ident):
        from .project import Project

        lock = FileLock(str(self.path(ident)) + ".worker", timeout=0)
        try:
            with lock:
                job = self.status(ident)
                if job["status"] not in ("queued", "running", "waiting"):
                    return job
                if self.cancelled(ident):
                    job["status"] = "cancelled"
                    self.save(job)
                    return job
                if job.get("next_poll", 0) > time.time():
                    return job
                if job["attempts"] >= 60:
                    job.update(
                        status="needs_review",
                        error={"code": "poll_limit", "message": "Remote job polling limit reached"},
                    )
                    self.save(job)
                    return job
                kind = job["payload"]["kind"]
                limits = Limits(**job.get("limits", asdict(self.limits)))
                if (
                    kind == "generate"
                    and job.get("request_started")
                    and not self.checkpoint_path(job).exists()
                ):
                    job.update(
                        status="needs_review",
                        error={
                            "code": "remote_unknown",
                            "message": "Image request may have completed. Check the provider before submitting a new job.",
                        },
                    )
                    self.save(job)
                    return job
                job["status"] = "running"
                job["attempts"] += 1
                self.save(job)

                def progress(value):
                    job["progress"] = value
                    self.save(job)

                try:
                    payload = job["payload"]
                    if kind == "video":
                        self.video_step(job)
                    elif kind == "production":
                        from .production import run

                        result = run(
                            Project.load(self.resolve(payload["source"]), limits=limits),
                            payload["spec"],
                            self.resolve(payload["output"]),
                            cancelled=lambda: self.cancelled(ident),
                            progress=progress,
                        )
                        job.update(result=result, status=result["status"])
                    elif kind == "form-fill":
                        self.form_fill_step(job, limits, progress)
                    elif kind == "lyric-video":
                        from .lyrics import export as lyric_export

                        checkpoint = self.checkpoint_path(job)
                        built = self.directory / ident / "build.vixl"
                        if not checkpoint.exists():
                            request = {**payload["request"], "replace": True,
                                       "build": str(built.relative_to(self.workspace)),
                                       "output": str(checkpoint.relative_to(self.workspace))}
                            report = lyric_export(request, self.workspace, limits,
                                                  cancelled=lambda: self.cancelled(ident), progress=progress)
                            job["result"] = {key: report[key] for key in ("frames", "duration_ms", "fps", "warnings", "verification")}
                        self.publish_checkpoint(job)
                        target = self.resolve(payload["request"]["build"])
                        if job["status"] == "completed" and built.exists() and not target.exists():
                            publish_file(target, built)
                            job["result"]["build"] = payload["request"]["build"]
                    elif kind == "film":
                        from .film import export

                        checkpoint = self.checkpoint_path(job)
                        if not checkpoint.exists():
                            result = export(
                                payload["spec"],
                                self.workspace,
                                checkpoint,
                                limits=limits,
                                cancelled=lambda: self.cancelled(ident),
                                progress=progress,
                            )
                            job["result"] = result
                        self.publish_checkpoint(job)
                    else:
                        from .ai import generate, provider

                        checkpoint = self.checkpoint_path(job)
                        if not checkpoint.exists():
                            project = Project.load(self.resolve(payload["source"]), limits=limits)
                            job["request_started"] = True
                            self.save(job)
                            job["result"] = generate(
                                project, payload["request"], provider(payload["provider"])
                            )
                            project.path, project._revision = None, None
                            project.save(checkpoint)
                        else:
                            Project.load(
                                checkpoint, limits=limits
                            )  # Validate recovered archive before publication.
                        self.publish_checkpoint(job)
                except Exception as exc:
                    error = exc.as_dict() if isinstance(exc, VixlError) else {"code": type(exc).__name__}
                    uncertain = kind in ("video", "generate") and job.get("request_started")
                    # Pollable jobs retain remote identifiers and can be resumed after transient failure.
                    status = (
                        "waiting"
                        if kind == "video" and job.get("remote_id")
                        else "needs_review"
                        if uncertain
                        else "failed"
                    )
                    job.update(
                        status="cancelled" if self.cancelled(ident) else status,
                        error=error,
                        next_poll=time.time() + min(60, 2 ** min(job["attempts"], 6)),
                    )
                self.save(job)
                return job
        except Timeout:
            return self.status(ident)

    def work(self, workers=1):
        require(type(workers) is int and 1 <= workers <= 4, "Workers must be 1–4")
        ids = [p.stem for p in sorted(self.directory.glob("*.json"))]
        with ThreadPoolExecutor(max_workers=workers) as executor:
            return list(executor.map(self.work_one, ids))

    def start(self, workers=1):
        require(type(workers) is int and 1 <= workers <= 4, "Workers must be 1–4")
        command = (
            [
                sys.executable,
                "workflow",
                "worker",
                "--workspace",
                str(self.workspace),
                "--workers",
                str(workers),
            ]
            if getattr(sys, "frozen", False)
            else [sys.executable, "-m", "vixl.jobs", str(self.workspace), str(workers)]
        )
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        process = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=flags,
            start_new_session=os.name != "nt",
        )
        return {"worker_pid": process.pid, "workspace": str(self.workspace)}


def worker(workspace, workers=1):
    queue = Queue(workspace)
    while True:
        jobs = queue.work(workers)
        if not any(j["status"] in ("queued", "running", "waiting") for j in jobs):
            break
        time.sleep(2)


def job_outcome(job):
    """A job's outcome (outcomes.py): execution from its status; a production job's validation and review come
    from its outputs. A job left needs_review by an uncertain remote request did not complete."""
    from .outcomes import make, of_status

    status = job.get("status")
    if status == "needs_review" and job.get("error"):
        return make("failed", reasons=[job["error"].get("message") or job["error"].get("code", "error")])
    outcome = of_status(status)
    result = job.get("result")
    outputs = result.get("outcome") if isinstance(result, dict) else None
    if outputs and outcome["execution"] == "completed" and "counts" in outputs:
        validation = {"validated": "passed", "validation_failed": "failed", "needs_review": "passed"}.get(
            outputs["state"], "not_run")
        reasons = [] if outputs["state"] == "validated" else [f"outputs by state: {outputs['counts']}"]
        outcome = {**make("completed", validation, reasons), "outputs": outputs}
    return outcome


if __name__ == "__main__":
    worker(sys.argv[1], int(sys.argv[2]))
