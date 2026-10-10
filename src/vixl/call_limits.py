"""Per-call limits for a shared server (``vixl serve``, ``vixl view``, ``vixl mcp``).

A long-lived service that several people or agents share needs bounds on what one call may cost,
or one oversized render starves everyone else. These are set per server by flag or environment:

* ``timeout`` (``--call-timeout``, ``VIXL_CALL_TIMEOUT``): seconds a call may run inline. A REST call
  that is still running then answers ``202`` with a job to poll (``GET /jobs/{id}``) instead of
  holding the connection; MCP calls detach into a ``vixl_job`` (MCP's own default is 40 s). Calls
  are never killed: the work finishes and its result waits in the job.
* ``max_megapixels`` (``--max-megapixels``, ``VIXL_MAX_MEGAPIXELS``): lowers ``Limits.max_pixels``
  (canvases, imports, frames) and caps the pixels one export renders: canvas × scale² × pages.
* ``max_pages`` (``--max-pages``, ``VIXL_MAX_PAGES``): pages one export may write.
* ``max_concurrent`` (``--max-concurrent``, ``VIXL_MAX_CONCURRENT``): heavy calls (exports, renders,
  checks, operation batches, compose, workflows, provider calls) running at once in one workspace,
  detached jobs included. A call over the cap is refused at once instead of queueing.

Exceeding a limit raises ``limit_exceeded`` with ``limit``, ``value``, ``maximum`` and a ``hint``.
Nothing is limited unless configured; ``describe`` reports the values a server runs with.
"""

from collections import OrderedDict
from contextlib import contextmanager
from dataclasses import dataclass, replace
import math
import os
from pathlib import Path
import threading
import time
import uuid

from .errors import VixlError, require

ENV = {"timeout": "VIXL_CALL_TIMEOUT", "max_megapixels": "VIXL_MAX_MEGAPIXELS", "max_pages": "VIXL_MAX_PAGES",
       "max_concurrent": "VIXL_MAX_CONCURRENT"}
FLAGS = {"timeout": "--call-timeout", "max_megapixels": "--max-megapixels", "max_pages": "--max-pages",
         "max_concurrent": "--max-concurrent"}
# Formats whose export is one raster image per page (PDF only when it is written as images).
VECTOR_FORMATS = ("SVG", "HTML", "HTM", "PPTX")


@dataclass(frozen=True)
class CallLimits:
    timeout: float | None = None
    max_megapixels: float | None = None
    max_pages: int | None = None
    max_concurrent: int | None = None

    @classmethod
    def configure(cls, environ=None, **given):
        """Limits from ``given`` values (CLI flags; ``None`` means not given), else the environment."""
        environ = os.environ if environ is None else environ
        values = {}
        for key, variable in ENV.items():
            value = given.get(key)
            source = FLAGS[key]
            if value is None and str(environ.get(variable, "")).strip():
                value, source = environ[variable].strip(), variable
            if value is None:
                continue
            fractional = key in ("timeout", "max_megapixels")
            try:
                number = float(value) if fractional else int(value)
            except (TypeError, ValueError):
                kind = "number" if fractional else "whole number"
                raise VixlError("invalid_input", f"{source} must be a {kind}, not {value!r}", field=key) from None
            require(math.isfinite(number) and number > 0, f"{source} must be positive", field=key)
            values[key] = number
        return cls(**values)

    def any(self):
        return any(value is not None for value in (self.timeout, self.max_megapixels, self.max_pages,
                                                    self.max_concurrent))

    def pixel_cap(self):
        return None if self.max_megapixels is None else int(self.max_megapixels * 1_000_000)

    def apply_to(self, limits):
        """``limits`` with ``max_pixels`` lowered to the megapixel cap."""
        cap = self.pixel_cap()
        return limits if cap is None or cap >= limits.max_pixels else replace(limits, max_pixels=cap)

    def describe(self, mcp_inline_seconds=None):
        """The limits as a service reports them (``GET /limits``, ``vixl_job(action='list')``)."""
        timeout = self.timeout if self.timeout is not None else mcp_inline_seconds
        return {"timeout_s": timeout, "max_megapixels": self.max_megapixels, "max_pages": self.max_pages,
                "max_concurrent_per_workspace": self.max_concurrent,
                "configure": {key: {"flag": FLAGS[key], "env": ENV[key]} for key in ENV}}


def add_arguments(parser):
    """The limit flags of ``vixl serve``, ``vixl view`` and ``vixl mcp``."""
    parser.add_argument("--call-timeout", type=float, dest="call_timeout",
                        help="Seconds a call runs inline before it continues as a job (also VIXL_CALL_TIMEOUT; "
                             "MCP default 40, REST default none)")
    parser.add_argument("--max-megapixels", type=float, help="Pixels one call may render, in millions; also caps "
                        "canvases and imports (VIXL_MAX_MEGAPIXELS)")
    parser.add_argument("--max-pages", type=int, help="Pages one export may write (VIXL_MAX_PAGES)")
    parser.add_argument("--max-concurrent", type=int, help="Heavy calls running at once per workspace, jobs included "
                        "(VIXL_MAX_CONCURRENT)")


def from_arguments(args):
    return CallLimits.configure(timeout=args.call_timeout, max_megapixels=args.max_megapixels,
                                max_pages=args.max_pages, max_concurrent=args.max_concurrent)


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


class RestJobs:
    """REST calls that outlived the timeout. Their futures keep running; the result waits here."""

    def __init__(self):
        self.jobs = OrderedDict()
        self.lock = threading.Lock()

    def add(self, route, future):
        ident = uuid.uuid4().hex[:16]
        with self.lock:
            self.jobs[ident] = {"id": ident, "route": route, "future": future, "created": time.time()}
            while len(self.jobs) > MAX_REST_JOBS:
                # Forget the oldest finished job; a running one is never dropped.
                victim = next((k for k, j in self.jobs.items() if j["future"].done()), None)
                if victim is None:
                    break
                del self.jobs[victim]
        return ident

    def get(self, ident):
        with self.lock:
            job = self.jobs.get(ident)
        require(job is not None, f"Unknown job {ident!r}; this server remembers its last {MAX_REST_JOBS} jobs",
                "not_found", field="id")
        return job

    def summary(self, job):
        from .errors import friendly

        future = job["future"]
        status = "running" if not future.done() else "failed" if future.exception() is not None else "completed"
        result = {"id": job["id"], "status": status, "route": job["route"],
                  "elapsed_s": round(time.time() - job["created"], 1), "result_url": f"/jobs/{job['id']}/result"}
        if status == "running":
            result["retry_after_s"] = 3
        elif status == "failed":
            result["error"] = friendly(future.exception()).as_dict()
        return result

    def recent(self):
        with self.lock:
            return list(reversed(self.jobs.values()))


def detached(job_id, route, timeout):
    """The 202 body of a REST call that became a job."""
    return {"status": "running", "job": job_id, "route": route, "poll": f"/jobs/{job_id}",
            "result_url": f"/jobs/{job_id}/result", "retry_after_s": 3,
            "message": f"Still running after {timeout:g} s; it continues as a job. Poll /jobs/{job_id}?wait=20, "
                       f"then GET /jobs/{job_id}/result. Do not send the call again unless the job fails."}
