"""Durable workspace jobs. Local work is resumable; uncertain inference is never blindly retried.

A queue (``.vixl-jobs`` in a workspace) is bounded: at most ``MAX_PENDING_JOBS`` unfinished jobs
(``VIXL_QUEUE_MAX_JOBS``), ``MAX_QUEUE_MB`` of records, snapshots and staged results (``VIXL_QUEUE_MAX_MB``), one
worker process, and completed, failed and cancelled jobs deleted ``RETENTION_DAYS`` after they ended
(``VIXL_QUEUE_RETENTION_DAYS``; outputs already published to the workspace are kept). ``0`` turns one quota off.
"""

import base64
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import asdict
import hashlib
import os
from pathlib import Path
import shutil
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

BUILTIN_KINDS = ("production", "film", "generate", "video", "lyric-video", "form-fill")
TERMINAL = ("completed", "failed", "cancelled", "needs_review")
# A needs_review job holds what a person needs to settle uncertain paid inference, so it is never pruned.
PRUNED = ("completed", "failed", "cancelled")
MAX_PENDING_JOBS = 64
MAX_QUEUE_MB = 4096
RETENTION_DAYS = 7
QUOTA_ENV = {"max_pending_jobs": "VIXL_QUEUE_MAX_JOBS", "max_queue_mb": "VIXL_QUEUE_MAX_MB",
             "retention_days": "VIXL_QUEUE_RETENTION_DAYS"}
WORKER_START_SECONDS = 20


def quota(name):
    """One queue quota: its environment variable when set (``0`` is off, returned as None), else the default."""
    default = {"max_pending_jobs": MAX_PENDING_JOBS, "max_queue_mb": MAX_QUEUE_MB, "retention_days": RETENTION_DAYS}[name]
    raw = os.environ.get(QUOTA_ENV[name])
    if raw is None or not raw.strip():
        return default or None
    try:
        value = int(raw) if name == "max_pending_jobs" else float(raw)
        require(value >= 0 and value == value and value != float("inf"), "negative")
    except (ValueError, VixlError) as exc:
        raise VixlError("invalid_input", f"{QUOTA_ENV[name]} must be a number, 0 or more (0 turns the quota off); "
                        f"got {raw!r}") from exc
    return value or None


def quotas():
    """The quotas a queue runs with, as ``submit`` and ``start`` results and errors report them."""
    return {name: quota(name) for name in QUOTA_ENV}


class Queue:
    def __init__(self, workspace, limits=None):
        self.workspace = Path(workspace).resolve()
        self.directory = self.workspace / ".vixl-jobs"
        self.limits = limits or Limits()

    def resolve(self, value):
        from .assets import local_path

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
        finished = job.get("status") in TERMINAL and not job.get("notified")
        if finished:
            # Set before the write, so a crash after it never sends the event twice.
            job["notified"] = job["updated"]
        write_json(self.path(job["id"]), job)
        if finished:
            deliveries = notify_complete(completion_event(job, self.workspace))
            if deliveries:
                job["deliveries"] = deliveries
                write_json(self.path(job["id"]), job)

    def lock(self, name, timeout):
        self.directory.mkdir(parents=True, exist_ok=True)
        return FileLock(str(self.directory / name), timeout=timeout)

    def records(self):
        """``(id, status, updated)`` of every readable job record."""
        found = []
        for path in sorted(self.directory.glob("*.json")):
            try:
                job = read_json(path)
                found.append((path.stem, job["status"], float(job.get("updated") or job["created"])))
            except (VixlError, KeyError, TypeError, ValueError):
                continue
        return found

    def disk_bytes(self):
        """Bytes under the queue folder (records, input snapshots, checkpoints and staged results)."""
        total, stack = 0, [self.directory]
        while stack:
            try:
                with os.scandir(stack.pop()) as entries:
                    for entry in entries:
                        if entry.is_dir(follow_symlinks=False):
                            stack.append(entry.path)
                        else:
                            total += entry.stat(follow_symlinks=False).st_size
            except OSError:
                continue
        return total

    def remove(self, ident):
        """Delete one job: its record, folder, cancel marker and lock file."""
        record = self.path(ident)
        shutil.rmtree(self.directory / ident, ignore_errors=True)
        for path in (self.directory / (ident + ".cancel"), record, Path(str(record) + ".worker")):
            try:
                path.unlink()
            except OSError:
                pass

    def prune(self, now=None):
        """Delete completed, failed and cancelled jobs that ended more than the retention period ago; the
        ids removed. Outputs published to the workspace are not touched."""
        days = quota("retention_days")
        if days is None or not self.directory.is_dir():
            return []
        cutoff = (time.time() if now is None else now) - days * 86400
        removed = []
        for ident, status, updated in self.records():
            if status not in PRUNED or updated > cutoff:
                continue
            try:
                with FileLock(str(self.path(ident)) + ".worker", timeout=0):
                    self.remove(ident)
            except Timeout:
                continue
            removed.append(ident)
        return removed

    def usage(self):
        """Pending job count and megabytes used, next to the quotas."""
        pending = sum(1 for _, status, _ in self.records() if status not in TERMINAL)
        return {"pending": pending, "disk_mb": round(self.disk_bytes() / 1048576, 1), **quotas()}

    def submit(self, payload):
        """Queue a job, inside the queue's quotas: old finished jobs are pruned first, then a queue at its
        pending-job or disk cap refuses with ``queue_full`` before anything is written. A job whose input
        snapshot takes the queue over the disk cap is removed again."""
        try:
            with self.lock(".queue.lock", 30):
                self.prune()
                self._admit()
                before = {path.stem for path in self.directory.glob("*.json")}
                try:
                    job = self._submit(payload)
                finally:
                    # A refused or failed submission leaves no half-written snapshot folder behind.
                    for folder in self.directory.iterdir():
                        if (folder.is_dir() and folder.name not in before
                                and not (self.directory / (folder.name + ".json")).exists()):
                            shutil.rmtree(folder, ignore_errors=True)
                limit = quota("max_queue_mb")
                used = self.disk_bytes() / 1048576
                if limit is not None and used > limit:
                    self.remove(job["id"])
                    raise self._full("max_queue_mb", round(used, 1), limit, "This job's input snapshot takes the "
                                     f"job queue over its disk quota of {limit:g} MB")
                return job
        except Timeout as exc:
            raise self._full("queue_lock", 1, 1, "The job queue is busy with another submission") from exc

    @staticmethod
    def _full(limit, value, maximum, message):
        hint = ("Retry in a few seconds." if limit == "queue_lock" else
                "Wait for jobs to finish (status), cancel the ones no longer needed, or delete finished job folders "
                f"from .vixl-jobs; an operator can raise the quota with {QUOTA_ENV[limit]}.")
        return VixlError("limit_exceeded", f"{message}. {hint}", limit=limit, value=value, maximum=maximum, hint=hint)

    def _admit(self):
        maximum = quota("max_pending_jobs")
        if maximum is not None:
            pending = sum(1 for _, status, _ in self.records() if status not in TERMINAL)
            if pending >= maximum:
                raise self._full("max_pending_jobs", pending + 1, maximum, f"The job queue already holds {pending} "
                                 f"unfinished jobs, the most it takes")
        limit = quota("max_queue_mb")
        used = self.disk_bytes() / 1048576
        if limit is not None and used >= limit:
            raise self._full("max_queue_mb", round(used, 1), limit, f"The job queue uses its whole disk quota of "
                             f"{limit:g} MB")

    def _submit(self, payload):
        from .project import Project
        from .production import plan
        from .plugins.film.film import plan as film_plan

        bounded_object(
            payload, {"kind", "source", "spec", "output", "provider", "request", "notify"}, "Unknown job field"
        )
        payload = deepcopy(payload)
        kind = payload.get("kind")
        plugin_kind = None if kind in BUILTIN_KINDS else job_kind(kind)
        require(kind in BUILTIN_KINDS or plugin_kind, "Unknown job kind", kinds=list(BUILTIN_KINDS) + plugin_kinds())
        if plugin_kind:
            require(isinstance(payload.get("output"), str), "Job needs an output path")
            output = self.resolve(payload["output"])
            require(not output.is_relative_to(self.directory) and output != self.workspace,
                    "Output cannot target queue storage or workspace root")
            plugin_kind["validate"](self, payload, output)
            return self._enqueue(payload)
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
            from .plugins.lyrics.lyrics import plan as lyric_plan

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
            for key in ("audio", "timing" if request.get("timing") else "lyrics", "template"):
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
        return self._enqueue(payload, ident)

    def _enqueue(self, payload, ident=None):
        ident = ident or uuid.uuid4().hex
        (self.directory / ident).mkdir(parents=True, exist_ok=True)
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
            job.pop("notified", None)  # A resumed job reports its next ending too.
            self.save(job)
            return job

    @staticmethod
    def video_backend(name):
        from .plugins.ai.ai import provider, HTTPProvider

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
                    plugin_kind = None if kind in BUILTIN_KINDS else job_kind(kind)
                    if plugin_kind:
                        result = plugin_kind["run"](self, job, limits, progress, lambda: self.cancelled(ident))
                        job.update(result=result, status=result.get("status", "completed")
                                   if result.get("status") in TERMINAL else "completed")
                    elif kind == "video":
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
                        from .plugins.lyrics.lyrics import export as lyric_export

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
                        from .plugins.film.film import export

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
                        from .plugins.ai.ai import generate, provider

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
                except Exception as exc:  # noqa: BLE001 - every failure is recorded on the job, which then stops or waits for a retry
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
        self.prune()
        ids = [p.stem for p in sorted(self.directory.glob("*.json"))]
        with ThreadPoolExecutor(max_workers=workers) as executor:
            return list(executor.map(self.work_one, ids))

    def worker_alive(self):
        """The pid of the worker process that holds this queue's worker lock (0 when its pid file is
        unreadable), or None when no worker is running."""
        try:
            with self.lock(".worker.lock", 0):
                return None
        except Timeout:
            pass
        try:
            return int((self.directory / ".worker.pid").read_text(encoding="ascii"))
        except (OSError, ValueError):
            return 0

    def start(self, workers=1):
        """Launch the queue's background worker, unless one is running: a queue has one worker process
        (with 1–4 threads). The call returns once the new worker holds the queue, or has already finished."""
        require(type(workers) is int and 1 <= workers <= 4, "Workers must be 1–4")
        try:
            with self.lock(".start.lock", WORKER_START_SECONDS + 10):
                return self._start(workers)
        except Timeout as exc:
            raise self._full("queue_lock", 1, 1, "Another call is starting this queue's worker") from exc

    def _start(self, workers):
        # "." as vixl_document list reports it: MCP and REST results never reveal where the workspace is.
        running = self.worker_alive()
        if running is not None:
            return {**({"worker_pid": running} if running else {}), "workspace": ".", "already_running": True,
                    "note": "This queue's worker is already running and picks up queued jobs; a queue has one "
                            "worker process."}
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
        # Hold the start lock until the worker has the queue (or has drained it and left), so a second start
        # sees it instead of launching another process.
        deadline = time.monotonic() + WORKER_START_SECONDS
        while process.poll() is None and self.worker_alive() is None and time.monotonic() < deadline:
            time.sleep(0.05)
        return {"worker_pid": process.pid, "workspace": "."}


def worker(workspace, workers=1):
    """Work the queue until it is idle. One worker runs per queue: a second one finds the worker lock held
    and returns (False)."""
    queue = Queue(workspace)
    try:
        with queue.lock(".worker.lock", 2):
            pid_file = queue.directory / ".worker.pid"
            pid_file.write_text(str(os.getpid()), encoding="ascii")
            try:
                while True:
                    jobs = queue.work(workers)
                    if not any(j["status"] in ("queued", "running", "waiting") for j in jobs):
                        break
                    time.sleep(2)
            finally:
                pid_file.unlink(missing_ok=True)
    except Timeout:
        return False
    return True


def job_kind(kind):
    """A plugin's durable job kind ({"validate": fn(queue, payload, output), "run": fn(queue, job, limits, progress,
    cancelled) -> result}), or None."""
    from . import plugins

    return plugins.first("job-kind", kind) if isinstance(kind, str) else None


def plugin_kinds():
    from . import plugins

    return sorted(name for fn in plugins.hooks("job-kind") for name in getattr(fn, "KINDS", ()))


def completion_event(job, workspace):
    """The one completion event shape shared by durable jobs, check-all and pipeline runs: what finished and how,
    never document content. ``workspace`` is the absolute path, for in-process ``job-complete`` hooks that read
    the workspace's own settings; what a hook sends elsewhere leaves it out (the notify plugin's webhook body)."""
    outcome = job.get("outcome") or {}
    result = job.get("result") if isinstance(job.get("result"), dict) else {}
    counts = (outcome.get("outputs") or {}).get("counts") or result.get("counts") or {}
    return {"event": "job-complete", "kind": job["payload"]["kind"], "id": job["id"], "status": job["status"],
            "state": outcome.get("state"), "counts": counts, "report": job["payload"].get("output"),
            "workspace": str(workspace), "notify": job["payload"].get("notify"),
            "error": (job.get("error") or {}).get("code")}


def notify_complete(event):
    """Hand a terminal event to every ``job-complete`` hook. A failing consumer is recorded, never raised: the work
    it reports on is already done."""
    from . import plugins

    deliveries = []
    for fn in plugins.hooks("job-complete"):
        try:
            result = fn(event)
        except Exception as exc:  # noqa: BLE001 - a consumer's failure must not undo or fail the finished job
            result = {"hook": f"{fn.__module__}.{fn.__name__}", "error": str(exc)[:200]}
        if result:
            deliveries.append(result)
    return deliveries


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
