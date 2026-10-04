"""Bounded NDJSON editing session: one load, atomic requests, durable saves."""

import json
import io
from contextlib import redirect_stdout
import sys

from .errors import VixlError, require


def run(project, source=None, sink=None, detail="compact"):
    from .cli import project_command
    source, sink = source or sys.stdin, sink or sys.stdout
    while True:
        line = source.readline(1_000_001)
        if not line:
            break
        request = {}
        try:
            require(len(line) <= 1_000_000, "Session request exceeds one MB", "resource_limit")
            request = json.loads(line)
            require(isinstance(request, dict), "Session request must be an object")
            require(set(request) <= {"id", "operations", "command", "dry_run"}, "Unknown session request fields")
            require(isinstance(request.get("dry_run", False), bool), "dry_run must be a boolean")
            require(("operations" in request) != ("command" in request), "Provide operations or command")
            candidate = project.clone()
            if "operations" in request:
                result = candidate.apply(request["operations"], dry_run=request.get("dry_run", False), detail=detail)
                changed = not request.get("dry_run", False)
            else:
                command = request["command"]
                require(isinstance(command, list) and command and all(isinstance(x, str) for x in command), "command is an argv array")
                require(command[0] not in ("save", "transaction", "serve", "view", "mcp", "session"), "Command is unavailable inside a session")
                require("-" not in command[1:], "stdin/stdout file streams are unavailable inside a session; use operation requests or file paths")
                require("dry_run" not in request, "dry_run applies to operation requests")
                captured = io.StringIO()
                with redirect_stdout(captured):
                    try:
                        result, changed = project_command(candidate, command[0], command[1:], detail=detail)
                    except SystemExit as exc:
                        require(exc.code in (0, None), "Command exited unsuccessfully", "usage_error")
                        result, changed = {"help": captured.getvalue()}, False
            if changed:
                candidate.save()
                project.__dict__.update(candidate.__dict__)
            response = {"id": request.get("id"), "success": True, "result": result}
        except (VixlError, OSError, ValueError, TypeError, KeyError) as exc:
            response = {"id": request.get("id") if isinstance(request, dict) else None, "success": False,
                        **(exc.as_dict() if isinstance(exc, VixlError) else {"error": "invalid_request", "message": str(exc)})}
        sink.write(json.dumps(response, ensure_ascii=False) + "\n")
        sink.flush()
