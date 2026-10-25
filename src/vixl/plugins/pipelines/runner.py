"""The pipeline runner (F1, #568): run a pipeline's steps per document, hold the failing ones, and keep a resumable
run record.

``pipeline-run`` takes a saved pipeline name (or an inline pipeline) and runs it over its targets. Every document goes
through the document steps in order; a step that fails holds that document (``held``, with its findings) and, with
``on_fail: hold``, the others continue (``stop`` ends the run at the first hold). After the documents, the run steps
(``proof``, ``package``) take every output that was not held. ``act`` and ``repair`` change a working copy under
``.vixl-runs/<run>/work/``, never the source document, and the later steps export and check that copy.

The run record ``.vixl-runs/<run>/run.json`` holds the Vixl version, the pipeline digest, per document its input
digests (the document, brand.json, the documents it links and the pipeline's ``inputs`` data files), every step's
status, key, log file (``logs/``) and outputs (path, SHA-256, bytes), and an outcome: ``passed``, ``held``,
``visual-review-needed`` (nothing failed, but a suite, an export check or an approval still needs a person) or
``failed`` (a step could not run). It is written atomically after every step.

Running the same run id again resumes: a step is reused when its key (a digest of the document inputs and every step
up to it) matches the record, it finished, and its outputs are still on disk with the recorded checksum; the first
step that does not match runs again, and so does every step after it. So a changed input (the document, brand.json, a
linked source, a data file or the pipeline) invalidates exactly the steps that depend on it. Exports never replace a
file unless the step says ``overwrite: true`` or the file is one this run wrote and has not changed since.

The dry run (the default when the run has no record yet) lists every planned step and output, and which steps a real
run would reuse, and writes nothing. A real run ends with the shared completion event (``vixl.jobs.notify_complete``),
so completion webhooks fire; as a durable job (kind ``pipeline``) the job's own event is used instead.
"""

from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import re

from ...design import named
from ...errors import VixlError, require
from ...hashing import content_hash
from .spec import DOCUMENT_STEPS, MUTATING, RUN_STEPS, TOKENS, resolve, step_kind, validate_targets

RUNS = ".vixl-runs"
DONE = ("passed", "visual-review-needed", "held")
OUTCOMES = ("passed", "held", "visual-review-needed", "failed")
REQUEST = {"pipeline", "run", "documents", "group", "dry_run", "notify"}
MAX_LOG_BYTES = 256 * 1024


def _now():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _digest(path):
    from ...production import file_digest

    path = Path(path)
    return file_digest(path) if path.is_file() else None


def run_folder(session, run_id):
    return session.resolve(f"{RUNS}/{named(run_id)}")


def _slug(relative):
    return re.sub(r"[^A-Za-z0-9._-]+", "__", relative)


def default_run_id(name, pipeline):
    """A named pipeline resumes its own record by default; an inline one is named by its content."""
    return name if name else f"inline-{content_hash(pipeline)[:12]}"


def documents(session, pipeline, request):
    """The run's documents (workspace-relative), from the request's documents/group or the pipeline's targets."""
    from ..workspace_qa.workspace_checks import members

    targets = {key: request[key] for key in ("documents", "group") if request.get(key) is not None}
    if targets:
        validate_targets(targets, "request")
    else:
        targets = pipeline.get("targets") or {}
    require(targets, "Give the documents to run: targets in the pipeline, or documents/group in the request",
            field="documents")
    paths, _ = members(session, targets)
    return [session.relative(path) for path in paths]


def environment(session, relative, pipeline):
    """The inputs besides the document that its results depend on: brand.json, linked documents, data files."""
    from ...brand import brand_path
    from ...links import link_layers, locate
    from ...project import Project

    found = {"brand.json": _digest(brand_path(session.workspace)), "links": {}, "data": {}}
    try:
        project = Project.load(session.resolve(relative), limits=session.limits)
        project._workspace = session.workspace
        for _, layer in link_layers(project.state):
            try:
                path = locate(project, layer["source"])
            except VixlError:
                found["links"][layer["source"]] = None
                continue
            found["links"][session.relative(path) if path.is_relative_to(session.workspace) else str(path)] = \
                _digest(path)
    except (VixlError, OSError, ValueError):
        pass  # The check or export step reports a document it cannot open.
    for name in pipeline.get("inputs", []):
        found["data"][name] = _digest(session.resolve(name))
    return found


def fill(template, tokens):
    unknown = sorted(set(re.findall(r"\{(\w*)\}", template)) - set(TOKENS))
    require(not unknown, f"Export path {template!r} uses unknown field(s) {unknown}; use "
            f"{', '.join('{' + t + '}' for t in TOKENS)}", field="steps")
    return re.sub(r"\{(\w+)\}", lambda m: tokens[m.group(1)], template)


class Run:
    """One pipeline run over its documents (see the module docstring)."""

    def __init__(self, session, request, *, cancelled=None, progress=None):
        from ... import __version__

        self.session = session
        self.name, self.pipeline = resolve(session, request["pipeline"])
        self.id = named(request.get("run") or default_run_id(self.name, self.pipeline))
        self.folder = run_folder(session, self.id)
        self.path = self.folder / "run.json"
        self.relative = session.relative(self.path)
        self.documents = documents(session, self.pipeline, request)
        self.steps = [(step_kind(step, i), step[step_kind(step, i)], step.get("id"))
                      for i, step in enumerate(self.pipeline["steps"])]
        self.document_steps = [step for step in self.steps if step[0] in DOCUMENT_STEPS]
        self.run_steps = [step for step in self.steps if step[0] in RUN_STEPS]
        self.mutating = any(kind in MUTATING for kind, _, _ in self.document_steps)
        self.on_fail = self.pipeline.get("on_fail", "hold")
        self.version = __version__
        self.digest = content_hash(self.pipeline)
        self.previous = self._previous()
        self.owned = self._owned()
        self._cancelled = cancelled
        self._progress = progress

    # The previous record -------------------------------------------------------------------------

    def _previous(self):
        from ...production import read_json

        if not self.path.is_file():
            return None
        try:
            record = read_json(self.path)
        except VixlError:
            return None
        return record if isinstance(record, dict) and record.get("format") == "vixl-pipeline-run" else None

    def _owned(self):
        """Files the previous attempt of this run wrote that still hold the recorded bytes: a re-run may replace them."""
        owned = {}
        for item in (self.previous or {}).get("outputs", []):
            path = self.session.resolve(item["path"])
            if path.is_file() and _digest(path) == item.get("sha256"):
                owned[item["path"]] = item["sha256"]
        return owned

    def _intact(self, step):
        return all(_digest(self.session.resolve(item["path"])) == item.get("sha256") for item in step.get("outputs", []))

    # Keys ----------------------------------------------------------------------------------------

    def _inputs(self, relative):
        return {"document": _digest(self.session.resolve(relative)),
                **environment(self.session, relative, self.pipeline), "vixl_version": self.version}

    def _extra(self, kind, options):
        """Inputs a step reads besides the document: an approval's decisions file."""
        if kind == "approve" and options.get("decisions"):
            return {"decisions": _digest(self.session.resolve(options["decisions"]))}
        return None

    def keys(self, inputs):
        keys, key = [], content_hash({"inputs": inputs})
        for kind, options, _ in self.document_steps:
            key = content_hash({"previous": key, "step": {kind: options}, "extra": self._extra(kind, options)})
            keys.append(key)
        return keys

    def _reusable(self, prior, key):
        return (isinstance(prior, dict) and prior.get("key") == key and prior.get("status") in DONE
                and self._intact(prior))

    def _work(self, relative):
        return f"{RUNS}/{self.id}/work/{relative}"

    def _snapshot(self, relative, index):
        return self.folder / "snapshots" / _slug(relative) / f"{index}.vixl"

    def resume_point(self, relative, keys):
        """``(first step to run, reused prior steps)`` for a document, given its step keys."""
        prior = ((self.previous or {}).get("documents") or {}).get(relative) or {}
        old = prior.get("steps") or []
        start = 0
        while start < len(keys) and start < len(old) and self._reusable(old[start], keys[start]):
            if old[start]["status"] == "held":
                start += 1
                break
            start += 1
        if self.mutating:
            # A run starting after a mutating step continues from the snapshot that step left.
            while start:
                last = max((i for i in range(start) if self.document_steps[i][0] in MUTATING), default=None)
                if last is None:
                    break
                snapshot = self._snapshot(relative, last)
                if snapshot.is_file() and _digest(snapshot) == old[last].get("after"):
                    break
                start = last
        return start, old[:start]

    # Steps ---------------------------------------------------------------------------------------

    def _log(self, relative, index, kind, payload):
        from ...production import write_bytes

        folder = self.folder / "logs" / (_slug(relative) if relative else "run")
        path = folder / f"{index:02d}-{kind}.json"
        text = json.dumps(payload, indent=2, default=str)
        if len(text) > MAX_LOG_BYTES:
            text = json.dumps({"truncated": True, "bytes": len(text), "head": text[:MAX_LOG_BYTES // 2]}, indent=2)
        write_bytes(path, text.encode("utf-8"), replace=True)
        return self.session.relative(path)

    def _tokens(self, relative):
        path = Path(relative)
        return {"doc": path.stem, "dir": path.parent.as_posix(), "run": self.id, "name": self.name or "inline"}

    def _allowed(self, path, overwrite):
        relative = self.session.relative(self.session.resolve(path))
        return overwrite or relative in self.owned or not self.session.resolve(path).exists()

    def planned_outputs(self, relative, kind, options):
        if kind != "export":
            return []
        tokens = self._tokens(relative)
        found = []
        for target in options["targets"]:
            path = self.session.relative(self.session.resolve(fill(target["path"], tokens)))
            found.append({"path": path, "exists": self.session.resolve(path).exists(),
                          "replace_allowed": self._allowed(path, options.get("overwrite", False))})
        return found

    def execute(self, relative, current, kind, options, outputs):
        """``(status, summary, outputs)`` of one document step; ``status`` is passed, held, visual-review-needed or
        failed."""
        from ...workflows import dispatch

        session = self.session
        if kind == "act":
            request = {"operations": deepcopy(options["operations"]),
                       **({"suites": options["suites"]} if "suites" in options else {})}
            result = dispatch(session, "act", request, document=current)
            summary = {key: result.get(key) for key in ("success", "committed", "changes") if key in result}
            if result.get("success", True) is False:
                return "held", {**summary, "reason": "the act step's suites did not pass"}, []
            return "passed", summary, []
        if kind == "check":
            from ..workspace_qa.workspace_checks import _suite, check_document, failing

            request = {key: options[key] for key in ("checks", "profile", "suites", "waivers") if key in options}
            record = check_document(session, current, request, _suite(session, options.get("suite")))
            if record.get("status") == "error":
                return "failed", {"error": record.get("error")}, []
            messages = failing(record, options.get("fail_on", "error"))
            summary = {"status": record["status"], "errors": record.get("errors", 0),
                       "warnings": record.get("warnings", 0), "failing": messages[:20],
                       "findings": record.get("issues", [])[:10],
                       "suites": {name: suite["status"] for name, suite in record.get("suites", {}).items()}}
            if messages:
                return "held", {**summary, "reason": f"{len(messages)} finding(s) reach "
                                f"{options.get('fail_on', 'error')}"}, []
            if any(status == "needs_review" for status in summary["suites"].values()):
                return "visual-review-needed", {**summary, "reason": "a suite needs review"}, []
            return "passed", summary, []
        if kind == "repair":
            result = dispatch(session, "repair-layout", {**deepcopy(options), "dry_run": False}, document=current)
            return "passed", {key: result.get(key) for key in ("feasible", "committed", "selected", "unsatisfied")
                              if key in result}, []
        if kind == "export":
            from ...export_batch import export_batch
            from ...io_policy import export_file

            planned = self.planned_outputs(relative, kind, options)
            refused = [item["path"] for item in planned if not item["replace_allowed"]]
            require(not refused, f"Export would replace existing file(s) {', '.join(refused[:5])}; set overwrite: true "
                    "on the export step", "output_exists", field="steps")
            targets = [{**deepcopy(target), "path": item["path"], "overwrite": item["exists"]}
                       for target, item in zip(options["targets"], planned)]
            result = export_batch(session, export_file, targets, options.get("defaults"), document=current)
            failed = [item for item in result["results"] if item.get("error")]
            if failed:
                return "failed", {"errors": [item["error"] for item in failed][:5]}, []
            written = [{"path": item["path"], "sha256": _digest(session.resolve(item["path"])),
                        "bytes": session.resolve(item["path"]).stat().st_size} for item in planned]
            return "passed", {"written": len(written)}, written
        if kind == "export_check":
            return self._export_check(options, outputs)
        if kind == "approve":
            return self._approve(relative, options, outputs)
        raise VixlError("invalid_request", f"Unknown document step {kind}")

    def _export_check(self, options, outputs):
        from ...export_checks import verify

        require(outputs, "export_check needs an export step before it", field="steps")
        verdicts, held, review = {}, [], []
        for item in outputs:
            verdict = verify(self.session.resolve(item["path"]), deepcopy(options.get("spec")))
            verdicts[item["path"]] = {key: verdict[key] for key in ("passed", "spec", "issues", "outcome")
                                      if key in verdict}
            if not verdict["passed"]:
                held.append(item["path"])
            elif any(issue.get("action") == "review" for issue in verdict.get("issues", ())):
                review.append(item["path"])
        summary = {"verdicts": verdicts}
        if held:
            return "held", {**summary, "reason": f"export check failed for {', '.join(held[:5])}"}, []
        if review:
            return "visual-review-needed", {**summary, "reason": f"export check needs review for {', '.join(review[:5])}"}, []
        return "passed", summary, []

    def _approve(self, relative, options, outputs):
        from ...production import read_json

        path = options.get("decisions")
        if not path or not self.session.resolve(path).is_file():
            return "visual-review-needed", {"reason": "awaiting approval: no decisions file yet", "decisions": path}, []
        value = read_json(self.session.resolve(path))
        items = value.get("items") if isinstance(value, dict) else None
        require(isinstance(items, list), f"{path} is not a proof page's decisions JSON", field="steps")
        decided = {item.get("path"): item.get("decision", "pending") for item in items if isinstance(item, dict)}
        wanted = [item["path"] for item in outputs] or [relative]
        found = {name: decided.get(name, decided.get(Path(name).name, "pending")) for name in wanted}
        summary = {"decisions": found}
        if "rejected" in found.values():
            return "held", {**summary, "reason": "rejected in review"}, []
        if all(value == "approved" for value in found.values()):
            return "passed", summary, []
        return "visual-review-needed", {**summary, "reason": "awaiting approval"}, []

    # Working copies ------------------------------------------------------------------------------

    def _prepare(self, relative, start):
        """Put the working copy in the state the step ``start`` expects: the snapshot of the last mutating step
        before it, or a fresh copy of the source."""
        from ...production import publish_file
        from ...project import Project

        work = self.session.resolve(self._work(relative))
        last = max((i for i in range(start) if self.document_steps[i][0] in MUTATING), default=None)
        if last is not None:
            publish_file(work, self._snapshot(relative, last), replace=True)
            return
        project = Project.load(self.session.resolve(relative), limits=self.session.limits)
        project._workspace = self.session.workspace
        work.parent.mkdir(parents=True, exist_ok=True)
        if work.exists():
            work.unlink()
        project.save(work)  # Saving into another folder keeps relative link sources pointing at the same files.

    def _keep(self, relative, index):
        from ...production import publish_file

        snapshot = self._snapshot(relative, index)
        publish_file(snapshot, self.session.resolve(self._work(relative)), replace=True)
        return _digest(snapshot)

    # Running -------------------------------------------------------------------------------------

    def cancelled(self):
        from ... import calls

        return bool(self._cancelled and self._cancelled()) or calls.cancelled()

    def progress(self, done, total, message):
        from ... import calls

        calls.progress(done, total, message)
        if self._progress:
            self._progress({"done": done, "total": total})

    def plan(self):
        """The dry run: every step per document with its planned outputs and whether a real run would reuse it."""
        entries = []
        for relative in self.documents:
            keys = self.keys(self._inputs(relative))
            start, _ = self.resume_point(relative, keys)
            steps = []
            for index, (kind, options, ident) in enumerate(self.document_steps):
                steps.append({"index": index, "kind": kind, **({"id": ident} if ident else {}),
                              "plan": "reuse" if index < start else "run",
                              "outputs": self.planned_outputs(relative, kind, options)})
            entries.append({"path": relative, "steps": steps,
                            **({"working_copy": self._work(relative)} if self.mutating else {})})
        run_steps = [{"kind": kind, **({"id": ident} if ident else {}), "output": options["output"],
                      "exists": self.session.resolve(options["output"]).exists()}
                     for kind, options, ident in self.run_steps]
        outputs = sorted({item["path"] for entry in entries for step in entry["steps"] for item in step["outputs"]}
                         | {step["output"] for step in run_steps})
        refused = sorted({item["path"] for entry in entries for step in entry["steps"] for item in step["outputs"]
                          if not item["replace_allowed"]})
        return {"dry_run": True, "run": self.id, "pipeline": self.name, "record": self.relative,
                "resumes": self.previous is not None, "documents": entries, "run_steps": run_steps,
                "outputs": outputs, "refused": refused, "written": False,
                "next": "Run again with dry_run: false to execute" + (f"; {len(refused)} export(s) would be refused "
                                                                      "(set overwrite: true on the export step)"
                                                                      if refused else "")}

    def _record(self, status, entries, run_entries):
        counts = {name: 0 for name in (*OUTCOMES, "pending")}
        for entry in entries.values():
            counts[entry["outcome"]] += 1
        outputs = [{**item, "document": entry["path"]} for entry in entries.values()
                   for step in entry["steps"] for item in step.get("outputs", [])]
        outputs += [{**item, "document": None} for step in run_entries for item in step.get("outputs", [])]
        return {"format": "vixl-pipeline-run", "version": 1, "run": self.id, "pipeline": self.name,
                "pipeline_digest": self.digest, "vixl_version": self.version, "status": status,
                "on_fail": self.on_fail, "started": self.started, "updated": _now(),
                "documents": entries, "run_steps": run_entries, "outputs": outputs, "counts": counts}

    def _save(self, status, entries, run_entries):
        from ...production import write_json

        record = self._record(status, entries, run_entries)
        write_json(self.path, record)
        return record

    def document(self, relative, entries, run_entries):
        inputs = self._inputs(relative)
        keys = self.keys(inputs)
        start, reused = self.resume_point(relative, keys)
        entry = {"path": relative, "input": inputs, "outcome": "pending", "steps": [],
                 **({"working_copy": self._work(relative)} if self.mutating else {})}
        entries[relative] = entry
        for step in reused:
            entry["steps"].append({**step, "reused": True})
        if inputs["document"] is None:
            entry.update(outcome="failed", reason="the document is missing")
            return entry
        current = self._work(relative) if self.mutating else relative
        if self.mutating and start < len(self.document_steps):
            try:
                self._prepare(relative, start)
            except (VixlError, OSError, ValueError) as exc:
                entry.update(outcome="failed", reason=f"the working copy could not be made: {str(exc)[:300]}")
                return entry
        if not (entry["steps"] and entry["steps"][-1]["status"] == "held"):
            for index in range(start, len(self.document_steps)):
                if self.cancelled():
                    return entry
                kind, options, ident = self.document_steps[index]
                outputs = [item for step in entry["steps"] for item in step.get("outputs", [])]
                began = _now()
                try:
                    status, summary, written = self.execute(relative, current, kind, options, outputs)
                except VixlError as exc:
                    status, summary, written = "failed", {"error": exc.as_dict()}, []
                step = {"index": index, "kind": kind, **({"id": ident} if ident else {}), "key": keys[index],
                        "status": status, "started": began, "finished": _now(), "outputs": written,
                        "summary": {key: summary[key] for key in ("reason", "status", "failing", "error", "errors",
                                                                  "written", "needs_review", "skipped")
                                    if key in summary}}
                if self.mutating:
                    step["after"] = (self._keep(relative, index) if kind in MUTATING
                                     else _digest(self.session.resolve(current)))
                step["log"] = self._log(relative, index, kind, {"step": {kind: options}, "status": status,
                                                                "result": summary})
                entry["steps"].append(step)
                for item in written:
                    self.owned[item["path"]] = item["sha256"]
                if status in ("held", "failed"):
                    break
                self._save("running", entries, run_entries)
        statuses = [step["status"] for step in entry["steps"]]
        last = entry["steps"][-1] if entry["steps"] else None
        if "failed" in statuses:
            entry["outcome"] = "failed"
        elif "held" in statuses:
            entry["outcome"] = "held"
        elif len(entry["steps"]) < len(self.document_steps):
            entry["outcome"] = "pending"
        else:
            entry["outcome"] = "visual-review-needed" if "visual-review-needed" in statuses else "passed"
        if last and entry["outcome"] in ("held", "failed", "visual-review-needed"):
            entry["reason"] = next((step["summary"].get("reason")
                                    or str((step["summary"].get("error") or {}).get("message", ""))[:300]
                                    for step in reversed(entry["steps"]) if step["status"] != "passed"), None)
            entry["findings"] = next((step["summary"].get("failing") for step in reversed(entry["steps"])
                                      if step["summary"].get("failing")), [])
        return entry

    def run_step(self, index, kind, options, ident, entries, previous):
        """A proof or package step over every output of the documents that were not held."""
        from ...workflows import dispatch

        include = [(entry["path"], entry["outcome"], item) for entry in entries.values()
                   if entry["outcome"] in ("passed", "visual-review-needed")
                   for step in entry["steps"] for item in step.get("outputs", [])]
        key = content_hash({"step": {kind: options}, "outputs": [[p, o, i["path"], i["sha256"]] for p, o, i in include],
                            "held": sorted(p for p, e in entries.items() if e["outcome"] in ("held", "failed"))})
        prior = next((step for step in previous if step.get("index") == index), None)
        if self._reusable(prior, key):
            return {**prior, "reused": True}
        output = self.session.relative(self.session.resolve(options["output"]))
        overwrite = options.get("overwrite", False) or output in self.owned
        began = _now()
        try:
            require(include, f"{kind}: no outputs to include (every document was held or wrote nothing)",
                    "invalid_request", field="steps")
            if kind == "proof":
                items = [{"path": item["path"], "note": f"{path}: {outcome}"} for path, outcome, item in include]
                result = dispatch(self.session, "proof", {"items": items[:200], "output": output,
                                                          "decisions": True, "overwrite": overwrite,
                                                          **{k: options[k] for k in ("title", "max_size")
                                                             if k in options}})
            else:
                from ..workspace_qa.package import build

                request = {**deepcopy(options), "run": self.relative, "output": output, "overwrite": overwrite}
                result = build(self.session, request)
            status, summary = "passed", {key: result.get(key) for key in ("output", "files", "held", "outcome")
                                         if key in result}
        except VixlError as exc:
            status, summary = "failed", {"error": exc.as_dict()}
        written = []
        path = self.session.resolve(output)
        if status == "passed" and path.is_file():
            written = [{"path": output, "sha256": _digest(path), "bytes": path.stat().st_size}]
            self.owned[output] = written[0]["sha256"]
        return {"index": index, "kind": kind, **({"id": ident} if ident else {}), "key": key, "status": status,
                "started": began, "finished": _now(), "outputs": written,
                "summary": {k: summary[k] for k in ("output", "files", "error") if k in summary},
                "log": self._log(None, index, kind, {"step": {kind: options}, "status": status, "result": summary})}

    def execute_all(self):
        from ...fileio import file_lock

        self.started = (self.previous or {}).get("started") or _now()
        self.folder.mkdir(parents=True, exist_ok=True)
        try:
            lock = file_lock(str(self.folder / "run"), timeout=1)
            lock.__enter__()
        except Exception as exc:  # noqa: BLE001 - filelock raises its own Timeout type
            raise VixlError("busy", f"Run {self.id} is already running", field="run") from exc
        try:
            return self._execute()
        finally:
            lock.__exit__(None, None, None)

    def _execute(self):
        entries, run_entries = {}, []
        self._save("running", entries, run_entries)
        stopped = cancelled = False
        for done, relative in enumerate(self.documents, 1):
            if self.cancelled():
                cancelled = True
                break
            entry = self.document(relative, entries, run_entries)
            self._save("running", entries, run_entries)
            self.progress(done, len(self.documents), relative)
            if self.cancelled():
                cancelled = True
                break
            if entry["outcome"] == "held" and self.on_fail == "stop":
                stopped = True
                break
        for relative in self.documents:
            entries.setdefault(relative, {"path": relative, "outcome": "pending", "steps": [],
                                          "reason": "not run: the run stopped" if stopped else "not run"})
        if not (stopped or cancelled):
            previous = (self.previous or {}).get("run_steps") or []
            offset = len(self.document_steps)
            for number, (kind, options, ident) in enumerate(self.run_steps):
                run_entries.append(self.run_step(offset + number, kind, options, ident, entries, previous))
                self._save("running", entries, run_entries)
        counts = self._record("running", entries, run_entries)["counts"]
        if cancelled:
            status = "cancelled"
        elif counts["failed"] or any(step["status"] == "failed" for step in run_entries):
            status = "failed"
        elif counts["held"] or counts["visual-review-needed"] or counts["pending"] or stopped:
            status = "needs_review"
        else:
            status = "completed"
        record = self._record(status, entries, run_entries)
        record["outcome"] = self.outcome(record, stopped)
        if stopped:
            record["stopped"] = True
        from ...production import write_json

        write_json(self.path, record)
        return record

    def outcome(self, record, stopped):
        from ...outcomes import make

        counts = record["counts"]
        execution = {"cancelled": "cancelled", "failed": "failed"}.get(record["status"], "completed")
        checked = any(kind in ("check", "export_check", "approve") or (kind == "act" and options.get("suites"))
                      for kind, options, _ in self.document_steps)
        reasons = []
        if counts["held"]:
            reasons.append(f"{counts['held']} document(s) held")
        if counts["visual-review-needed"]:
            reasons.append(f"{counts['visual-review-needed']} document(s) need visual review")
        if stopped:
            reasons.append("the run stopped at the first held document (on_fail: stop)")
        validation = "failed" if counts["held"] else "passed" if checked else "not_run"
        return make(execution, validation, reasons)


def summary(record):
    """The compact result of a finished run."""
    return {"run": record["run"], "pipeline": record["pipeline"], "record": None, "status": record["status"],
            "counts": record["counts"], "outcome": record.get("outcome"),
            "documents": [{"path": entry["path"], "outcome": entry["outcome"],
                           **({"reason": entry["reason"]} if entry.get("reason") else {}),
                           **({"findings": entry["findings"][:5]} if entry.get("findings") else {}),
                           "steps": [{"kind": step["kind"], "status": step["status"],
                                      **({"reused": True} if step.get("reused") else {})}
                                     for step in entry["steps"]]}
                          for entry in record["documents"].values()],
            "run_steps": [{"kind": step["kind"], "status": step["status"],
                           **({"reused": True} if step.get("reused") else {}),
                           **({"error": step["summary"]["error"]} if step["summary"].get("error") else {})}
                          for step in record["run_steps"]],
            "outputs": [{"path": item["path"], "sha256": item["sha256"]} for item in record["outputs"]],
            **({"stopped": True} if record.get("stopped") else {})}


def event(session, record, notify=None):
    """The shared completion event of a finished run (vixl.jobs.completion_event's shape)."""
    counts = {key: value for key, value in record["counts"].items() if value}
    return {"event": "job-complete", "kind": "pipeline", "id": record["run"], "status": record["status"],
            "state": (record.get("outcome") or {}).get("state"), "counts": counts,
            "report": session.relative(run_folder(session, record["run"]) / "run.json"),
            "workspace": str(session.workspace), "notify": notify, "error": None}


def run(session, request, *, cancelled=None, progress=None, emit=True):
    """The ``pipeline-run`` workflow action."""
    from ...automation import bounded_object

    bounded_object(request, REQUEST, "Unknown pipeline-run field")
    require("pipeline" in request, "pipeline-run needs pipeline: a saved pipeline name or a pipeline object",
            field="pipeline")
    if request.get("notify") is not None:
        from .notify import validate

        validate(request["notify"])
    runner = Run(session, request, cancelled=cancelled, progress=progress)
    dry_run = request.get("dry_run", runner.previous is None)
    require(type(dry_run) is bool, "dry_run must be boolean", field="dry_run")
    if dry_run:
        result = runner.plan()
        if "dry_run" not in request:
            result["note"] = "This run has no record yet, so dry_run defaults to true"
        return result
    record = runner.execute_all()
    result = {**summary(record), "record": runner.relative}
    if emit:
        from ...jobs import notify_complete

        deliveries = notify_complete(event(session, record, request.get("notify")))
        if deliveries:
            result["notify"] = deliveries
            record["deliveries"] = deliveries
            from ...production import write_json

            write_json(runner.path, record)
    return result


# The durable job kind ---------------------------------------------------------------------------

JOB_FIELDS = {"pipeline", "documents", "group"}


def _job_run_id(queue, output):
    relative = output.relative_to(queue.workspace).as_posix()
    parts = relative.split("/")
    require(len(parts) == 2 and parts[0] == RUNS, f"A pipeline job's output is its run folder {RUNS}/<run id>",
            field="output")
    return named(parts[1])


def _validate_job(queue, payload, output):
    from ...automation import bounded_object
    from ...interfaces import Session

    request = payload.get("request")
    require(isinstance(request, dict), "A pipeline job needs request: {pipeline, documents?, group?}", field="request")
    bounded_object(request, JOB_FIELDS, "Unknown pipeline job request field")
    require("pipeline" in request, "A pipeline job needs request.pipeline", field="request.pipeline")
    _job_run_id(queue, output)
    session = Session(None, queue.limits, workspace=queue.workspace)
    resolve(session, request["pipeline"])
    if payload.get("notify") is not None:
        from .notify import validate

        validate(payload["notify"])


def _run_job(queue, job, limits, progress, cancelled):
    from ...interfaces import Session

    payload = job["payload"]
    session = Session(None, limits, workspace=queue.workspace)
    run_id = _job_run_id(queue, queue.resolve(payload["output"]))
    result = run(session, {**payload["request"], "run": run_id, "dry_run": False}, cancelled=cancelled,
                 progress=progress, emit=False)
    status = result["status"]
    return {"status": status if status in ("completed", "failed", "cancelled", "needs_review") else "needs_review",
            "counts": {key: value for key, value in result["counts"].items() if value}, "run": result["record"],
            "outcome": result.get("outcome")}


JOB = {"validate": _validate_job, "run": _run_job}


def job_kind(kind):
    """The ``job-kind`` hook: durable ``pipeline`` jobs."""
    return JOB if kind == "pipeline" else None


job_kind.KINDS = ("pipeline",)
