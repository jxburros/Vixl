"""Retry keys for mutating calls: a repeated ``request_id`` returns the first call's result instead of applying twice.

Shared by MCP (``mcp_runtime``, keyed by the request id) and ``vixl host`` (keyed by workspace and request id).
A key used again with a different tool or a different body (``digest``) is ``request_id_conflict``. The log is
bounded overall and per document, and keeps results up to ``MAX_REMEMBERED_BYTES``.
"""

from collections import OrderedDict
import hashlib
import json
import threading

from .errors import VixlError

MAX_REQUESTS = 512
MAX_PER_DOCUMENT = 64
MAX_REMEMBERED_BYTES = 262_144


def fingerprint(name, kwargs):
    """The digest a repeat must match: the tool (or route) and its arguments, key order ignored."""
    text = json.dumps({"tool": name, "args": kwargs}, sort_keys=True, default=str, ensure_ascii=False)
    return hashlib.sha256(text.encode()).hexdigest()


class RequestLog:
    """Recent request ids and their recorded results, bounded overall and per document."""

    def __init__(self):
        self.entries = OrderedDict()
        self.lock = threading.Lock()

    def start(self, request_id, tool, digest, document, *, key=None):
        """('new', entry) for a first sight, ('replay'|'running', entry) for a repeat. ``key`` (default
        ``request_id``) is what entries are stored under, so a host can scope ids to a workspace."""
        key = request_id if key is None else key
        with self.lock:
            entry = self.entries.get(key)
            if entry is not None:
                if entry["tool"] != tool or entry["digest"] != digest:
                    raise VixlError(
                        "request_id_conflict",
                        f"request_id {request_id!r} was already used for {entry['tool']} with different "
                        "arguments; use a fresh id for a different call",
                        field="request_id",
                    )
                self.entries.move_to_end(key)
                return ("replay" if entry["result"] is not None else "running"), entry
            entry = {"tool": tool, "digest": digest, "document": document, "result": None,
                     "job": None, "done": threading.Event()}
            self.entries[key] = entry
            same = [k for k, e in self.entries.items() if e["document"] == document]
            for stale in same[: max(0, len(same) - MAX_PER_DOCUMENT)]:
                del self.entries[stale]
            while len(self.entries) > MAX_REQUESTS:
                self.entries.popitem(last=False)
            return "new", entry

    def finish(self, entry, text):
        entry["result"] = text if len(text) <= MAX_REMEMBERED_BYTES else json.dumps(
            {"note": "The first result was too large to keep; read the document to see its effect"})
        entry["done"].set()

    def discard(self, key, entry):
        with self.lock:
            if self.entries.get(key) is entry:
                del self.entries[key]
        entry["done"].set()
