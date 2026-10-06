"""Per-call context for services: which client is calling, which document the call used, and how a
long call reports progress or learns it was cancelled.

A service wrapper (``mcp_runtime.py``) installs a ``CallState`` before running a tool. Worker
threads see the same object (a copied context still points at it), so code deep inside an
operation can call ``progress()`` or ``check_cancelled()`` without every signature carrying a
callback. Without a wrapper (CLI, Python, REST) every helper here is a no-op.
"""

from contextvars import ContextVar
import threading

from .errors import require

CALL = ContextVar("vixl_call", default=None)
UNKNOWN = ContextVar("vixl_unknown_arguments", default=())  # Tool arguments the client sent that no parameter takes.


class CallState:
    """One tool call. ``client`` identifies the MCP session making it (None outside MCP)."""

    def __init__(self, client=None, report=None):
        self.client = client
        self.report = report
        self.document = None
        self.unknown = UNKNOWN.get()
        self.cancel = threading.Event()


def current_client():
    state = CALL.get()
    return state.client if state is not None else None


def note_document(path):
    """Record the document this call acted on, so its result can name it."""
    state = CALL.get()
    if state is not None and path is not None:
        state.document = path


def progress(done, total=None, message=None):
    """Report ``done`` of ``total`` units of work; ignored unless a service is listening."""
    state = CALL.get()
    if state is not None and state.report is not None:
        state.report(done, total, message)


def progress_dict(value):
    """Adapter for the ``progress({"done": n, "total": m})`` callbacks in timeline and film exports."""
    progress(value.get("done", 0), value.get("total"))


def cancelled():
    state = CALL.get()
    return state is not None and state.cancel.is_set()


def check_cancelled():
    require(not cancelled(), "Call cancelled", "cancelled")
