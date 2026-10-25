"""Per-call limits for a shared server (``vixl serve``, ``vixl view``, ``vixl mcp``).

A long-lived service that several people or agents share needs bounds on what one call may cost,
or one oversized render starves everyone else. These are set per server by flag or environment:

* ``timeout`` (``--call-timeout``, ``VIXL_CALL_TIMEOUT``): seconds a call may run inline. A REST call
  that is still running then answers ``202`` with a job to poll (``GET /jobs/{id}``) instead of
  holding the connection; MCP calls detach into a ``vixl_job`` (MCP's own default is 40 s).
* ``hard_timeout`` (``--call-hard-timeout``, ``VIXL_CALL_HARD_TIMEOUT``): seconds after which a running
  call, detached or not, is asked to stop. It stops at its next checkpoint (between layers, pages,
  frames, export targets and check families) with ``cancelled``; an atomic edit is then not applied.
* ``max_megapixels`` (``--max-megapixels``, ``VIXL_MAX_MEGAPIXELS``): lowers ``Limits.max_pixels``
  (canvases, imports, frames) and caps the pixels one export renders: canvas × scale² × pages.
* ``max_pages`` (``--max-pages``, ``VIXL_MAX_PAGES``): pages one export may write.
* ``max_concurrent`` (``--max-concurrent``, ``VIXL_MAX_CONCURRENT``): heavy calls (exports, renders,
  checks, operation batches, compose, workflows, provider calls) running at once in one workspace,
  detached jobs included. A call over the cap is refused at once instead of queueing.

Exceeding a limit raises ``limit_exceeded`` with ``limit``, ``value``, ``maximum`` and a ``hint``.
A server that other machines can reach (``serve`` or ``view`` on a non-loopback host, ``mcp --http``) starts
with ``network_defaults``; a loopback ``serve``/``view`` and stdio ``mcp`` limit nothing unless configured.
A value of ``0`` turns one limit off, and ``--no-call-limits`` turns off every default. ``describe``
reports the values a server runs with and where each came from.
"""

from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
import heapq
import itertools
import math
import os
from pathlib import Path
import threading
import time
import uuid

from .errors import Cancelled, VixlError, require

ENV = {"timeout": "VIXL_CALL_TIMEOUT", "max_megapixels": "VIXL_MAX_MEGAPIXELS", "max_pages": "VIXL_MAX_PAGES",
       "max_concurrent": "VIXL_MAX_CONCURRENT", "hard_timeout": "VIXL_CALL_HARD_TIMEOUT"}
FLAGS = {"timeout": "--call-timeout", "max_megapixels": "--max-megapixels", "max_pages": "--max-pages",
         "max_concurrent": "--max-concurrent", "hard_timeout": "--call-hard-timeout"}
FRACTIONAL = ("timeout", "max_megapixels", "hard_timeout")
# Formats whose export is one raster image per page (PDF only when it is written as images).
VECTOR_FORMATS = ("SVG", "HTML", "HTM", "PPTX")
FONT_FORMATS = ("TTF", "OTF", "WOFF", "WOFF2")


@dataclass(frozen=True)
class CallLimits:
    timeout: float | None = None
    max_megapixels: float | None = None
    max_pages: int | None = None
    max_concurrent: int | None = None
    hard_timeout: float | None = None
    # Where each value came from: a flag, an environment variable or "default" (network_defaults).
    sources: dict = field(default_factory=dict, compare=False, repr=False)

    @staticmethod
    def network_defaults(cpu=None, mcp=False):
        """The limits of a server other machines can reach. MCP keeps its own 40 s inline wait (clients give up
        at about 60 s), so only REST gets a default ``timeout``."""
        cpu = cpu if cpu is not None else os.cpu_count() or 1
        values = {"max_megapixels": 40.0, "max_pages": 200, "max_concurrent": max(2, cpu), "hard_timeout": 600.0}
        return values if mcp else {"timeout": 120.0, **values}

    @classmethod
    def configure(cls, environ=None, *, network=None, **given):
        """Limits from ``given`` values (CLI flags; ``None`` means not given), else the environment, else the
        ``network`` defaults (``"rest"`` or ``"mcp"`` for a server other machines can reach, ``None`` for none).
        ``0`` turns a limit off."""
        environ = os.environ if environ is None else environ
        defaults = {} if network is None else cls.network_defaults(mcp=network == "mcp")
        values, sources = {}, {}
        for key, variable in ENV.items():
            value = given.get(key)
            source = FLAGS[key]
            if value is None and str(environ.get(variable, "")).strip():
                value, source = environ[variable].strip(), variable
            if value is None:
                if key in defaults:
                    values[key], sources[key] = defaults[key], "default"
                continue
            fractional = key in FRACTIONAL
            try:
                number = float(value) if fractional else int(value)
            except (TypeError, ValueError):
                kind = "number" if fractional else "whole number"
                raise VixlError("invalid_input", f"{source} must be a {kind}, not {value!r}", field=key) from None
            require(math.isfinite(number) and number >= 0, f"{source} must be positive, or 0 for no limit", field=key)
            sources[key] = source
            if number:
                values[key] = number
        return cls(**values, sources=sources)

    def any(self):
        return any(value is not None for value in (self.timeout, self.max_megapixels, self.max_pages,
                                                    self.max_concurrent, self.hard_timeout))

    def pixel_cap(self):
        return None if self.max_megapixels is None else int(self.max_megapixels * 1_000_000)

    def apply_to(self, limits):
        """``limits`` with ``max_pixels`` lowered to the megapixel cap."""
        cap = self.pixel_cap()
        return limits if cap is None or cap >= limits.max_pixels else replace(limits, max_pixels=cap)

    def describe(self, mcp_inline_seconds=None):
        """The limits as a service reports them (``GET /limits``, ``vixl_job(action='list')``)."""
        timeout = self.timeout if self.timeout is not None else mcp_inline_seconds
        return {"timeout_s": timeout, "hard_timeout_s": self.hard_timeout, "max_megapixels": self.max_megapixels,
                "max_pages": self.max_pages, "max_concurrent_per_workspace": self.max_concurrent,
                "source": {key: self.sources.get(key, "unset") for key in ENV},
                "configure": {key: {"flag": FLAGS[key], "env": ENV[key]} for key in ENV}}


def add_arguments(parser):
    """The limit flags of ``vixl serve``, ``vixl view`` and ``vixl mcp``."""
    parser.add_argument("--call-timeout", type=float, dest="call_timeout",
                        help="Seconds a call runs inline before it continues as a job (also VIXL_CALL_TIMEOUT; "
                             "MCP default 40, REST default none, or 120 when serving other machines)")
    parser.add_argument("--call-hard-timeout", type=float, dest="call_hard_timeout",
                        help="Seconds after which a running call is cancelled at its next checkpoint "
                             "(VIXL_CALL_HARD_TIMEOUT; default none, or 600 when serving other machines)")
    parser.add_argument("--max-megapixels", type=float, help="Pixels one call may render, in millions; also caps "
                        "canvases and imports (VIXL_MAX_MEGAPIXELS)")
    parser.add_argument("--max-pages", type=int, help="Pages one export may write (VIXL_MAX_PAGES)")
    parser.add_argument("--max-concurrent", type=int, help="Heavy calls running at once per workspace, jobs included "
                        "(VIXL_MAX_CONCURRENT)")
    parser.add_argument("--no-call-limits", action="store_true",
                        help="Do not apply the default limits of a server other machines can reach")


def from_arguments(args, network=None):
    """Limits from the parsed flags; ``network`` (``"rest"``/``"mcp"``) when other machines can reach the server."""
    return CallLimits.configure(timeout=args.call_timeout, max_megapixels=args.max_megapixels,
                                max_pages=args.max_pages, max_concurrent=args.max_concurrent,
                                hard_timeout=args.call_hard_timeout,
                                network=None if args.no_call_limits else network)


def exceeded(limit, value, maximum, message, hint):
    return VixlError("limit_exceeded", f"{message} ({FLAGS[limit]}, {ENV[limit]}). {hint}", limit=limit, value=value,
                     maximum=maximum, hint=hint)


def of(session):
    """The limits a session runs with (none unless a server configured them)."""
    return getattr(session, "call_limits", None) or CallLimits()


def export_pages(project, fmt, options):
    """How many pages an export writes (1 for a document without pages)."""
    from .pages import page_list, parse_pages

    pages = page_list(project)
    if not pages:
        return 1
    page, selected = options.get("page"), options.get("pages")
    if page == "all" or selected == "all":
        return len(pages)
    if selected:
        return len(parse_pages(selected))
    if page is not None:
        return 1
    return len(pages) if fmt in ("PDF", "PPTX", "HTML", "HTM") else 1


def check_export(limits, project, fmt, options):
    """Refuse an export over the page or megapixel cap before anything renders."""
    if limits.max_pages is None and limits.max_megapixels is None:
        return
    fmt = (fmt or "PNG").upper()
    if fmt in FONT_FORMATS:
        return  # a font file renders no pages
    count = export_pages(project, fmt, options)
    if limits.max_pages is not None and count > limits.max_pages:
        raise exceeded("max_pages", count, limits.max_pages,
                       f"This export writes {count} pages; the server allows {limits.max_pages} per call",
                       "Export fewer pages at once (pages='1-10', then the next range).")
    cap = limits.pixel_cap()
    if cap is None:
        return
    canvas = project.state["canvas"]
    scale = float(options.get("scale") or 1)
    per_page = canvas["width"] * canvas["height"] * scale * scale
    vector = fmt in VECTOR_FORMATS or (fmt == "PDF" and options.get("pdf_content") != "raster" and scale == 1)
    total = per_page if vector else per_page * count
    if total > cap:
        megapixels = round(total / 1_000_000, 2)
        raise exceeded("max_megapixels", megapixels, limits.max_megapixels,
                       f"This export renders {megapixels:g} megapixels; the server allows {limits.max_megapixels:g} "
                       "per call", "Lower scale, export fewer pages at once, or export a vector format (PDF, SVG).")


class Gate:
    """Heavy calls running per workspace, across every server in this process."""

    def __init__(self):
        self.running = {}
        self.lock = threading.Lock()

    def acquire(self, workspace, maximum):
        """Count one heavy call in ``workspace``; refuse it when ``maximum`` are already running.
        Returns the key to pass to ``release`` (``None`` when nothing is limited)."""
        if maximum is None:
            return None
        key = str(Path(workspace).resolve()) if workspace is not None else "-"
        with self.lock:
            busy = self.running.get(key, 0)
            if busy >= maximum:
                raise exceeded("max_concurrent", busy + 1, maximum,
                               f"{busy} heavy call(s) are already running in this workspace; the server allows "
                               f"{maximum} at once", "Wait for a running call or job to finish (poll its job), "
                               "then retry.")
            self.running[key] = busy + 1
        return key

    def release(self, key):
        if key is None:
            return
        with self.lock:
            left = self.running.get(key, 1) - 1
            if left > 0:
                self.running[key] = left
            else:
                self.running.pop(key, None)

    @contextmanager
    def slot(self, workspace, maximum):
        key = self.acquire(workspace, maximum)
        try:
            yield
        finally:
            self.release(key)


GATE = Gate()
MAX_REST_JOBS = 100
REST_QUEUE = 16  # REST calls that may wait for a worker; one more is answered 503.


class BoundedExecutor:
    """A thread pool that holds at most ``workers`` running and ``queue`` waiting calls, and refuses the next
    one with ``limit_exceeded`` (``limit: max_queue``, answered 503) instead of queueing it without bound."""

    def __init__(self, workers, queue=REST_QUEUE, name="vixl-rest"):
        self.pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix=name)
        self.workers, self.queue = workers, queue
        self.slots = threading.BoundedSemaphore(workers + queue)

    def submit(self, fn, *args, **kwargs):
        if not self.slots.acquire(blocking=False):
            raise VixlError("limit_exceeded", f"The server is busy: {self.workers} calls are running and {self.queue} "
                            "are waiting", limit="max_queue", value=self.workers + self.queue + 1,
                            maximum=self.workers + self.queue, hint="Retry after a few seconds.")
        try:
            future = self.pool.submit(fn, *args, **kwargs)
        except BaseException:
            self.slots.release()
            raise
        future.add_done_callback(lambda _: self.slots.release())
        return future


class Watchdog:
    """Asks calls to stop when their hard timeout passes: it sets the call's ``CallState.cancel``, and the work
    raises ``cancelled`` at its next checkpoint. One daemon thread serves every call of the process."""

    def __init__(self):
        self.heap = []
        self.order = itertools.count()
        self.condition = threading.Condition()
        self.thread = None

    def watch(self, state, seconds):
        """Cancel ``state`` after ``seconds``; returns a handle for ``forget``."""
        entry = [time.monotonic() + seconds, next(self.order), state, seconds]
        with self.condition:
            heapq.heappush(self.heap, entry)
            if self.thread is None:
                self.thread = threading.Thread(target=self.run, name="vixl-watchdog", daemon=True)
                self.thread.start()
            self.condition.notify()
        return entry

    def forget(self, entry):
        """The call ended: drop its reference (the entry leaves the heap when its time comes)."""
        entry[2] = None

    def run(self):
        while True:
            with self.condition:
                while not self.heap:
                    self.condition.wait()
                deadline, _, state, seconds = self.heap[0]
                delay = deadline - time.monotonic()
                if delay > 0 and state is not None:
                    self.condition.wait(delay)
                    continue
                heapq.heappop(self.heap)
            if state is not None:
                state.reason = (f"Call stopped after the {seconds:g} s hard timeout ({FLAGS['hard_timeout']}, "
                                f"{ENV['hard_timeout']})")
                state.cancel.set()


WATCHDOG = Watchdog()


def watch(state, limits, future):
    """Cancel the call behind ``future`` (its ``CallState`` is ``state``) after the hard timeout, if one is set."""
    if limits.hard_timeout is None:
        return
    entry = WATCHDOG.watch(state, limits.hard_timeout)
    future.add_done_callback(lambda _: WATCHDOG.forget(entry))


class RestJobs:
    """REST calls that outlived the timeout, and ``vixl host`` export jobs. Their futures keep running; the result
    waits here. A job may carry ``fields`` of its own (``vixl host``: kind, workspace, document, ``result_path``,
    ``expires``); ``progress`` records how far it got."""

    def __init__(self, hard_timeout=None, maximum=MAX_REST_JOBS):
        self.jobs = OrderedDict()
        self.lock = threading.Lock()
        self.hard_timeout = hard_timeout
        self.maximum = maximum

    def add(self, route, future, ident=None, **fields):
        ident = ident or uuid.uuid4().hex[:16]
        with self.lock:
            self.jobs[ident] = {**fields, "id": ident, "route": route, "future": future, "created": time.time(),
                                "progress": None}
            while len(self.jobs) > self.maximum:
                # Forget the oldest finished job, else the oldest one still running past its hard timeout (it was
                # cancelled and has not reached a checkpoint); a running job within its time is never dropped.
                victim = next((k for k, j in self.jobs.items() if j["future"].done()), None)
                if victim is None and self.hard_timeout is not None:
                    expired = time.time() - self.hard_timeout
                    victim = next((k for k, j in self.jobs.items() if j["created"] < expired), None)
                if victim is None:
                    break
                del self.jobs[victim]
        return ident

    def get(self, ident):
        with self.lock:
            job = self.jobs.get(ident)
        require(job is not None, f"Unknown job {ident!r}; this server remembers its last {self.maximum} jobs",
                "not_found", field="id")
        return job

    def progress(self, job, done, total=None):
        """Record ``done`` of ``total``. ``fraction`` never goes back: a later, smaller report is clamped."""
        with self.lock:
            previous = (job.get("progress") or {}).get("fraction")
            fraction = min(1.0, max(0.0, done / total)) if total else previous
            if previous is not None and fraction is not None:
                fraction = max(fraction, previous)
            job["progress"] = {"done": done, **({"total": total} if total else {}), "fraction": fraction}

    def summary(self, job):
        from .errors import friendly

        future = job["future"]
        error = future.exception() if future.done() else None
        status = ("running" if not future.done() else "cancelled" if isinstance(error, Cancelled)
                  else "failed" if error is not None else "completed")
        result = {"id": job["id"], "status": status, "route": job["route"],
                  "elapsed_s": round(time.time() - job["created"], 1), "result_url": f"/jobs/{job['id']}/result"}
        if job.get("progress"):
            result["progress"] = job["progress"]
        if status == "running":
            result["retry_after_s"] = 3
        elif status in ("failed", "cancelled"):
            result["error"] = friendly(error).as_dict()
        return result

    def recent(self):
        with self.lock:
            return list(reversed(self.jobs.values()))


class Limiter:
    """How a service runs a heavy call: counted against ``max_concurrent`` in its workspace, on a bounded pool, in a
    copy of the request's context with a fresh ``CallState`` (so a render profile and ``check_cancelled`` see it),
    cancelled at its next checkpoint after the hard timeout, and handed to ``jobs`` when it outlives the timeout.
    ``vixl serve`` and ``vixl host`` share it."""

    def __init__(self, limits, jobs, workers):
        self.limits, self.jobs, self.workers = limits, jobs, workers

    async def run(self, workspace, route, fn, *args, **kwargs):
        """``("done", value)``, or ``("job", id)`` when the call is still running after the timeout."""
        import asyncio
        import contextvars

        from .calls import CALL, CallState

        key = GATE.acquire(workspace, self.limits.max_concurrent)
        context, state = contextvars.copy_context(), CallState()
        context.run(CALL.set, state)
        try:
            future = self.workers.submit(context.run, fn, *args, **kwargs)
        except BaseException:
            GATE.release(key)
            raise
        future.add_done_callback(lambda _: GATE.release(key))
        watch(state, self.limits, future)
        waiter = asyncio.wrap_future(future)
        waiter.add_done_callback(lambda f: f.cancelled() or f.exception())  # Retrieved even if nobody waits.
        if self.limits.timeout is None:
            return "done", await waiter
        try:
            return "done", await asyncio.wait_for(asyncio.shield(waiter), self.limits.timeout)
        except asyncio.TimeoutError:
            return "job", self.jobs.add(route, future)


def detached(job_id, route, timeout):
    """The 202 body of a REST call that became a job."""
    return {"status": "running", "job": job_id, "route": route, "poll": f"/jobs/{job_id}",
            "result_url": f"/jobs/{job_id}/result", "retry_after_s": 3,
            "message": f"Still running after {timeout:g} s; it continues as a job. Poll /jobs/{job_id}?wait=20, "
                       f"then GET /jobs/{job_id}/result. Do not send the call again unless the job fails."}
