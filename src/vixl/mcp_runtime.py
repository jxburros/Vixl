"""How MCP tool calls run: off the event loop, with progress, background jobs and retries.

FastMCP calls a plain function tool directly on the event loop, so one slow render blocks every
other call (and the heartbeat) of every client sharing the server, and a client that gives up
after 60 s still has its edit applied, with nothing to tell it so. Every tool therefore runs in a
worker thread through ``Runtime.wrap``:

* A call that outlives ``inline_seconds`` (default 40) is *detached*: it keeps running, and the
  client receives ``{"status": "running", "job": ...}`` while it can still read the answer.
  ``as_job: true`` on the heavy tools returns that job at once. When more calls are in flight than
  there are workers, a new call waits proportionally less before it becomes a job, so clients do
  not time out while their call is still queued; job pointers report ``queued``, ``wait_ms`` and
  ``queue_depth``.
* ``vixl_job`` reports a job's progress, waits for it, returns its result or cancels it. Ids of
  durable workspace jobs (``vixl_workflow submit``) are served from ``jobs.py``.
* A client that sent a progress token receives ``notifications/progress`` while the call runs
  (operation batches, timeline frames, export targets).
* ``request_id`` on the mutating tools makes a retry safe: the second call with the same id
  returns the first call's recorded result (``"replayed": true``) instead of applying twice, or
  points at the job that is still running. A recent-id store is kept per document and bounded.
* Results name the document they acted on, so a call that fell back to another client's active
  document is visible.
"""

import asyncio
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
import difflib
import functools
import hashlib
import inspect
import json
import os
import re
import threading
import time
from typing import Annotated
import uuid

from pydantic import Field

from .calls import CALL, UNKNOWN, CallState
from .errors import VixlError, for_surface, memory_guard, require

DEFAULT_INLINE_SECONDS = 40
DEFAULT_WORKERS = 32
# Under load the inline wait shrinks, but never below this (or below inline_seconds when that is smaller).
MIN_INLINE_SECONDS = 2.0
MAX_JOBS = 100
MAX_REQUESTS = 512
MAX_PER_DOCUMENT = 64
MAX_REMEMBERED_BYTES = 262_144

# Tools that change documents or files, or spend provider calls: safe to retry with request_id.
RETRYABLE = {
    "vixl_operations_apply", "vixl_import_image", "vixl_import_document", "vixl_import_font",
    "vixl_document_create", "vixl_document_close", "vixl_template_create", "vixl_export_file",
    "vixl_export_batch", "vixl_export_timeline", "vixl_export_animation", "vixl_export_icons",
    "vixl_font_pair", "vixl_font_install", "vixl_history", "vixl_workflow", "vixl_roll", "vixl_adapt_layout",
    "vixl_compose",
}
# Tools worth running as a job: heavy renders, exports, imports, large batches and provider calls.
JOB_TOOLS = {
    "vixl_operations_apply", "vixl_import_image", "vixl_import_document", "vixl_export_file",
    "vixl_export_batch", "vixl_export_timeline", "vixl_export_animation", "vixl_export_icons",
    "vixl_font_pair", "vixl_font_install", "vixl_workflow", "vixl_roll", "vixl_check", "vixl_adapt_layout",
    "vixl_compose",
}
NO_EXTRAS = {"vixl_job"}

RequestId = Annotated[str | None, Field(max_length=64, description="Retry key: a repeat returns the first result")]
AsJob = Annotated[bool, Field(description="Return a job id at once; poll vixl_job")]


def takes_request_id(name):
    return name not in NO_EXTRAS and (name in RETRYABLE or name.startswith("vixl_ai_"))


def takes_job(name):
    return name not in NO_EXTRAS and (name in JOB_TOOLS or name.startswith("vixl_ai_"))


def fingerprint(name, kwargs):
    text = json.dumps({"tool": name, "args": kwargs}, sort_keys=True, default=str, ensure_ascii=False)
    return hashlib.sha256(text.encode()).hexdigest()


class Job:
    """One call that outlived its client's patience, or was started with as_job=true."""

    def __init__(self, tool, document, request_id, future, box):
        self.id = "job_" + uuid.uuid4().hex[:12]
        self.tool, self.document, self.request_id = tool, document, request_id
        self.future, self.box = future, box
        self.created = time.time()
        self.done = threading.Event()
        self.finished = None
        self.cancel_requested = False
        future.add_done_callback(self._finish)

    def _finish(self, _):
        self.finished = time.time()
        self.done.set()

    @property
    def status(self):
        if self.future.cancelled():
            return "cancelled"
        if not self.future.done():
            return "running" if self.box.started else "queued"
        error = self.future.exception()
        if error is None:
            return "completed"
        return "cancelled" if '"error":"cancelled"' in str(error) else "failed"

    def summary(self):
        status = self.status
        result = {"id": self.id, "status": status, "tool": self.tool}
        if self.box.submitted is not None:
            result["queued"] = status == "queued"
            result["wait_ms"] = round(((self.box.started or time.time()) - self.box.submitted) * 1000)
        if self.document:
            result["document"] = self.document
        if self.request_id:
            result["request_id"] = self.request_id
        end = self.finished or time.time()
        result["elapsed_s"] = round(end - (self.box.started or self.created), 1)
        if self.box.progress:
            result["progress"] = self.box.progress
        if status in ("queued", "running"):
            result["retry_after_s"] = 3
            if self.cancel_requested:
                result["cancel_requested"] = True
        return result


class JobStore:
    def __init__(self):
        self.jobs = OrderedDict()
        self.lock = threading.Lock()

    def add(self, job):
        with self.lock:
            self.jobs[job.id] = job
            while len(self.jobs) > MAX_JOBS:
                # Forget the oldest finished job first; a running one is never dropped.
                victim = next((k for k, j in self.jobs.items() if j.done.is_set()), None)
                if victim is None:
                    break
                del self.jobs[victim]
        return job

    def get(self, ident):
        with self.lock:
            return self.jobs.get(ident)

    def recent(self):
        with self.lock:
            return list(reversed(self.jobs.values()))


class RequestLog:
    """Recent request ids and their recorded results, bounded overall and per document."""

    def __init__(self):
        self.entries = OrderedDict()
        self.lock = threading.Lock()

    def start(self, request_id, tool, digest, document):
        """('new', entry) for a first sight, ('replay'|'running', entry) for a repeat."""
        with self.lock:
            entry = self.entries.get(request_id)
            if entry is not None:
                if entry["tool"] != tool or entry["digest"] != digest:
                    raise VixlError(
                        "request_id_conflict",
                        f"request_id {request_id!r} was already used for {entry['tool']} with different "
                        "arguments; use a fresh id for a different call",
                        field="request_id",
                    )
                self.entries.move_to_end(request_id)
                return ("replay" if entry["result"] is not None else "running"), entry
            entry = {"tool": tool, "digest": digest, "document": document, "result": None,
                     "job": None, "done": threading.Event()}
            self.entries[request_id] = entry
            same = [k for k, e in self.entries.items() if e["document"] == document]
            for key in same[: max(0, len(same) - MAX_PER_DOCUMENT)]:
                del self.entries[key]
            while len(self.entries) > MAX_REQUESTS:
                self.entries.popitem(last=False)
            return "new", entry

    def finish(self, entry, text):
        entry["result"] = text if len(text) <= MAX_REMEMBERED_BYTES else json.dumps(
            {"note": "The first result was too large to keep; read the document to see its effect"})
        entry["done"].set()

    def discard(self, request_id, entry):
        with self.lock:
            if self.entries.get(request_id) is entry:
                del self.entries[request_id]
        entry["done"].set()


class _Box:
    """State shared between a running call, its progress reporter and its job."""

    def __init__(self):
        self.submitted = None
        self.started = None
        self.progress = None
        self.job = None
        self.state = None
        self.inline = True
        self.last_notified = 0.0


class Runtime:
    def __init__(self, session, compact_json, tool_error, inline_seconds=None, poll_with_workflow=False):
        self.session = session
        self.poll_with_workflow = poll_with_workflow  # The compact tool set has no vixl_job.
        self.compact_json = compact_json
        self.tool_error = tool_error
        if inline_seconds is None:
            inline_seconds = float(os.environ.get("VIXL_MCP_INLINE_SECONDS", DEFAULT_INLINE_SECONDS))
        self.inline_seconds = inline_seconds
        self.jobs = JobStore()
        self.log = RequestLog()
        self.parameters = {}  # Tool name -> the parameter names it takes (see watch_arguments).
        self.workers = int(os.environ.get("VIXL_MCP_WORKERS", DEFAULT_WORKERS))
        self.executor = ThreadPoolExecutor(max_workers=self.workers, thread_name_prefix="vixl-call")
        self.in_flight = 0  # Calls submitted to ``executor`` that have not finished (running or queued).
        self.flight_lock = threading.Lock()
        # Following a job must never queue behind the calls it is waiting for.
        self.light = ThreadPoolExecutor(max_workers=8, thread_name_prefix="vixl-poll")

    def wrap(self, fn):
        """An async tool that runs ``fn`` in a worker thread, with the extras this tool offers."""
        from mcp.server.fastmcp import Context

        name = fn.__name__
        returns = fn.__annotations__.get("return")
        extras = {}
        if takes_request_id(name):
            extras["request_id"] = RequestId
        if takes_job(name):
            extras["as_job"] = AsJob
        extras["ctx"] = Context

        @functools.wraps(fn)
        async def wrapper(*args, **kwargs):
            ctx = kwargs.pop("ctx", None)
            return await self.invoke(fn, name, returns, args, kwargs, ctx)

        signature = inspect.signature(fn)
        parameters = list(signature.parameters.values()) + [
            inspect.Parameter(key, inspect.Parameter.KEYWORD_ONLY, default=False if key == "as_job" else None,
                              annotation=annotation)
            for key, annotation in extras.items()
        ]
        wrapper.__signature__ = signature.replace(parameters=parameters)
        wrapper.__annotations__ = {**fn.__annotations__, **extras}
        if returns is dict:
            wrapper.__annotations__["return"] = str
        return wrapper

    def watch_arguments(self, registered):
        """Report arguments a tool does not take. FastMCP drops them silently, so a misspelt option
        (``detial="full"``) would look like success; the result gets a warning naming it instead."""
        known = set(registered.parameters.get("properties", {}))
        original = registered.run
        self.parameters[registered.name] = known

        async def run(arguments, *args, **kwargs):
            unknown = tuple(key for key in (arguments or {}) if key not in known)
            token = UNKNOWN.set(unknown) if unknown else None
            try:
                return await original(arguments, *args, **kwargs)
            finally:
                if token is not None:
                    UNKNOWN.reset(token)

        object.__setattr__(registered, "run", run)

    def ignored(self, name, state):
        """The warning for this call's unknown arguments, if any."""
        if not state.unknown:
            return None
        known = self.parameters.get(name, set())
        hints = []
        for key in state.unknown:
            close = difflib.get_close_matches(key, sorted(known), 1, 0.6)
            hints.append(f"{key!r} (did you mean {close[0]!r}?)" if close else repr(key))
        return f"{name} ignored unknown argument(s): {', '.join(hints)}. Parameters: {', '.join(sorted(known))}"

    def label(self, result, state):
        """Name the document a result is about, unless the tool already did."""
        if state.document is None or "document" in result or "documents" in result:
            return
        try:
            shown = self.session.relative(state.document)
        except ValueError:
            return
        if result.get("path") != shown:
            result["document"] = shown

    def call(self, fn, returns, args, kwargs, state):
        """The synchronous body: run the tool with this call's context and shape its result."""
        token = CALL.set(state)
        try:
            try:
                result = memory_guard(fn)(*args, **kwargs)
            except VixlError as exc:
                raise self.tool_error(self.compact_json(for_surface(exc.as_dict(), "mcp"))) from exc
            warning = self.ignored(fn.__name__, state)
            if isinstance(result, list) and result and isinstance(result[0], dict):
                # A JSON result with images after it (vixl_operations_apply preview=…): shape the JSON part.
                self.label(result[0], state)
                if warning:
                    result[0]["warnings"] = [*result[0].get("warnings", []), warning]
                return [self.compact_json(result[0]), *result[1:]]
            if isinstance(result, dict):
                self.label(result, state)
                if warning:
                    result["warnings"] = [*result.get("warnings", []), warning]
                return self.compact_json(result)
            if getattr(returns, "__name__", "") == "Image" and (state.document is not None or warning):
                # Image tools: the picture cannot carry the name or a warning, so a text line follows it.
                note = {**({"document": self.session.relative(state.document)} if state.document is not None else {}),
                        **({"warnings": [warning]} if warning else {})}
                result = [result, self.compact_json(note)]
            return result
        finally:
            CALL.reset(token)

    def work(self, fn, returns, args, kwargs, state, box, request_id, entry):
        box.started = time.time()
        try:
            result = self.call(fn, returns, args, kwargs, state)
        except BaseException:
            if entry is not None:
                self.log.discard(request_id, entry)
            raise
        if entry is not None:
            if isinstance(result, str):
                self.log.finish(entry, result)
            elif isinstance(result, list) and result and isinstance(result[0], str):
                self.log.finish(entry, result[0])  # A replay returns the JSON; the edit must not run twice.
            else:
                self.log.discard(request_id, entry)
        return result

    def reporter(self, box, ctx, loop):
        try:
            meta = ctx.request_context.meta
            token = meta.progressToken if meta else None
        except (AttributeError, ValueError):
            token = None

        def report(done, total=None, message=None):
            box.progress = {"done": done, **({"total": total} if total else {}), **({"message": message} if message else {})}
            now = time.monotonic()
            if token is None or not box.inline or (now - box.last_notified < 0.25 and not (total and done >= total)):
                return
            box.last_notified = now
            try:
                future = asyncio.run_coroutine_threadsafe(ctx.report_progress(done, total, message), loop)
            except RuntimeError:  # The client and its loop are gone: the edit goes on without notifications.
                box.inline = False
                return
            future.add_done_callback(lambda f: f.cancelled() or f.exception())

        return report

    def queue_depth(self):
        """Calls waiting for a free worker."""
        with self.flight_lock:
            return max(0, self.in_flight - self.workers)

    def budget(self, in_flight):
        """How long a call waits inline before it becomes a job. With more calls in flight than workers,
        the call may sit in the queue for most of that time, so the wait shrinks in proportion."""
        if in_flight <= self.workers:
            return self.inline_seconds
        return max(min(MIN_INLINE_SECONDS, self.inline_seconds), self.inline_seconds * self.workers / in_flight)

    def submit(self, *args):
        """Run ``work`` on the call pool, counting it in flight until it ends (or is cancelled while queued)."""
        with self.flight_lock:
            self.in_flight += 1
            in_flight = self.in_flight
        try:
            future = self.executor.submit(self.work, *args)
        except BaseException:
            self.landed(None)
            raise
        future.add_done_callback(self.landed)
        return future, in_flight

    def landed(self, _):
        with self.flight_lock:
            self.in_flight -= 1

    def pointer(self, job, why):
        text = job.summary()
        text["job"] = text.pop("id")
        text["queue_depth"] = self.queue_depth()
        poll = (f"vixl_workflow(action='status', request={{'id': '{job.id}', 'wait': 20}})" if self.poll_with_workflow
                else f"vixl_job(action='status', id='{job.id}', wait=20), then action='result'")
        text["message"] = why + f" Poll {poll}. Do not send the call again unless the job fails."
        return self.compact_json(text)

    def detach(self, name, kwargs, future, box, request_id, entry):
        job = self.jobs.add(Job(name, kwargs.get("document"), request_id, future, box))
        box.job, box.inline = job, False
        if entry is not None:
            entry["job"] = job
        return job

    async def invoke(self, fn, name, returns, args, kwargs, ctx):
        request_id = kwargs.pop("request_id", None)
        as_job = kwargs.pop("as_job", False)
        loop = asyncio.get_running_loop()
        try:
            client = ctx.session if ctx is not None else None
        except ValueError:
            client = None
        box = _Box()
        state = CallState(client=client, report=self.reporter(box, ctx, loop) if ctx is not None else None)
        box.state = state
        entry = None
        if request_id:
            digest = fingerprint(name, kwargs)
            try:
                outcome, entry = self.log.start(request_id, name, digest, self.document_key(kwargs, state))
            except VixlError as exc:
                raise self.tool_error(self.compact_json(exc.as_dict())) from exc
            if outcome == "replay":
                return self.replayed(entry, request_id)
            if outcome == "running":
                return await self.join(entry, request_id)
        box.submitted = time.time()
        gate = None
        if takes_job(name):
            # Heavy calls count against the server's per-workspace cap (call_limits.py), jobs included.
            from .call_limits import GATE, of

            try:
                maximum = of(self.session).max_concurrent
                if maximum is not None:
                    gate = GATE.acquire(getattr(self.session, "workspace", None), maximum)
            except VixlError as exc:
                if entry is not None:
                    self.log.discard(request_id, entry)
                raise self.tool_error(self.compact_json(for_surface(exc.as_dict(), "mcp"))) from exc
        if name in NO_EXTRAS:
            future, in_flight = self.light.submit(self.work, fn, returns, args, kwargs, state, box, request_id, entry), 0
        else:
            try:
                future, in_flight = self.submit(fn, returns, args, kwargs, state, box, request_id, entry)
            except BaseException:
                if gate is not None:
                    GATE.release(gate)
                raise
        if gate is not None:
            future.add_done_callback(lambda _: GATE.release(gate))
        if as_job:
            job = self.detach(name, kwargs, future, box, request_id, entry)
            return self.pointer(job, "Started in the background.")
        waiter = asyncio.wrap_future(future)
        waiter.add_done_callback(lambda f: f.cancelled() or f.exception())  # Retrieved even if nobody waits.
        if returns is not dict or not self.inline_seconds or name in NO_EXTRAS:
            return await waiter
        budget = self.budget(in_flight)
        try:
            return await asyncio.wait_for(asyncio.shield(waiter), budget)
        except asyncio.TimeoutError:
            job = self.detach(name, kwargs, future, box, request_id, entry)
            why = (f"Still running after {budget:g} s." if box.started else
                   f"Queued behind {self.queue_depth()} other call(s) after {budget:g} s; it runs when a worker is free.")
            return self.pointer(job, why)
        except asyncio.CancelledError:
            # The client gave up or disconnected. The edit still finishes; keep it findable.
            self.detach(name, kwargs, future, box, request_id, entry)
            raise

    def document_key(self, kwargs, state):
        token = CALL.set(state)
        try:
            return kwargs.get("document") or (
                self.session.relative(self.session.path) if self.session.path is not None else "workspace"
            )
        except ValueError:
            return "workspace"
        finally:
            CALL.reset(token)

    def replayed(self, entry, request_id):
        try:
            data = json.loads(entry["result"])
        except ValueError:
            return entry["result"]
        if isinstance(data, dict):
            data.update(replayed=True, request_id=request_id)
            return self.compact_json(data)
        return entry["result"]

    async def join(self, entry, request_id):
        """A repeat of a call that is still running: wait a little, then answer or point at its job."""
        wait = self.inline_seconds or DEFAULT_INLINE_SECONDS
        await asyncio.get_running_loop().run_in_executor(None, entry["done"].wait, wait)
        if entry["result"] is not None:
            return self.replayed(entry, request_id)
        job = entry.get("job")
        if job is not None:
            return self.pointer(job, "The original call with this request_id is still running.")
        return self.compact_json({
            "status": "running", "request_id": request_id,
            "message": "The original call with this request_id is still running; repeat this call shortly.",
        })

    def job(self, action="status", id=None, wait=0):
        require(action in ("status", "result", "cancel", "list"), "action is status, result, cancel or list",
                field="action")
        if action == "list":
            from .call_limits import of

            return {"jobs": [job.summary() for job in self.jobs.recent()[:20]],
                    "limits": of(self.session).describe(self.inline_seconds)}
        require(isinstance(id, str) and id, "id is required", field="id")
        if re.fullmatch(r"[0-9a-f]{32}", id):
            return self.durable(action, id)
        job = self.jobs.get(id)
        require(job is not None, f"Unknown job {id!r}; this server remembers its last {MAX_JOBS} jobs",
                "not_found", field="id")
        if action == "cancel":
            job.cancel_requested = True
            if not job.future.cancel() and job.box.state is not None:
                job.box.state.cancel.set()
            return {**job.summary(), "note": "A call that is already running stops at its next checkpoint "
                    "(timeline frames, export targets); edits already saved stay saved."}
        if wait:
            job.done.wait(min(float(wait), 50))
        summary = job.summary()
        if action == "status" or not job.done.is_set():
            return summary
        error = job.future.exception() if not job.future.cancelled() else None
        if error is not None:
            try:
                summary["error"] = json.loads(str(error)[str(error).index("{"):])
            except ValueError:
                summary["error"] = {"message": str(error)}
            return summary
        if job.future.cancelled():
            return summary
        value = job.future.result()
        if isinstance(value, list):
            # JSON followed by images: a job result is JSON only, so say where the images went.
            images = sum(1 for part in value if not isinstance(part, str))
            value = next((part for part in value if isinstance(part, str)), "{}")
            if images:
                summary["note"] = f"{images} image(s) are not kept with a job result; call vixl_render_preview."
        try:
            summary["result"] = json.loads(value)
        except (TypeError, ValueError):
            summary["result"] = value
        return summary

    def durable(self, action, ident):
        from .jobs import Queue

        queue = Queue(self.session.workspace, self.session.limits)
        if action == "cancel":
            return queue.cancel(ident)
        job = queue.status(ident)
        keep = ("id", "status", "progress", "attempts", "error", "result")
        summary = {k: job[k] for k in keep if k in job}
        summary["kind"] = job["payload"]["kind"]
        if action == "result" and job["status"] not in ("completed", "failed", "cancelled", "needs_review"):
            summary.pop("result", None)
        return summary
