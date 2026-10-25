"""``vixl host``: one server for many workspaces, for host applications such as AI Server Studio.

``vixl serve`` serves one fixed document to one user. ``vixl host`` serves documents in many workspaces
to another program that holds the bearer token:

* **Auth.** A bearer token is always required, on loopback too; the host refuses to start without one
  (``--token-env``, default ``VIXL_HOST_TOKEN``, or ``--token-file``, default ``VIXL_HOST_TOKEN_FILE``).
  The token rules and the failed-token throttle are those of ``vixl serve`` (``interfaces.require_token``,
  ``interfaces.Failures``). There is no origin check (the caller is a program, not a browser page), and the
  host names are restricted to loopback unless ``--bind`` names another address.
* **Workspaces.** ``/w/{ws}/...`` where ``ws`` matches ``[a-z0-9_-]{1,64}``: the folder ``root/ws``,
  created on first use and checked to resolve inside ``root``. Each workspace has one
  ``Session(workspace=..., require_document=True)``, kept in a bounded LRU.
* **Offline.** ``--offline`` sets ``VIXL_OFFLINE=1`` for the process (``fetch.offline``): URL fetches,
  font downloads, content-pack downloads and AI providers refuse with ``network_disabled``, and
  third-party plugins cannot be enabled.
* **Errors.** Every error answers one shape, ``{code, message, hint, layer_id?, details?}``.
* **Limits.** ``call_limits`` bound every heavy call as they do for ``vixl serve``; ``GET /host/info`` reports
  them.

Route groups other modules add (a later ``PUT /w/{ws}/brand``, for example) register with ``add_routes``; a
plugin adds routes through the ``host-route`` hook. Both receive ``(app, host)``.
"""

from collections import OrderedDict
import json
import os
from pathlib import Path
import re
import threading

from .errors import VixlError, require

HOST_API = 1
DEFAULT_PORT = 8767
TOKEN_ENV = "VIXL_HOST_TOKEN"
TOKEN_FILE_ENV = "VIXL_HOST_TOKEN_FILE"
WORKSPACE_PATTERN = r"[a-z0-9_-]{1,64}"
WORKSPACE = re.compile(WORKSPACE_PATTERN)
HOST_DIR = ".vixl-host"  # Per-workspace host state: the document index and export job results.
MAX_WORKSPACES = 16  # Workspace sessions kept loaded; the least recently used is dropped (everything is saved).
MAX_JSON_BYTES = 1024 * 1024
SCHEMA_PATH = Path(__file__).parent / "data" / "host-api.schema.json"

# HTTP status per error code; anything else is 400.
STATUS = {
    "unauthorized": 401, "authentication_required": 401, "forbidden": 403, "network_disabled": 403,
    "not_found": 404, "no_project": 404, "revision_conflict": 409, "request_id_conflict": 409, "document_busy": 409,
    "job_running": 409, "job_failed": 409, "expired": 410, "resource_limit": 413, "too_many_attempts": 429,
    "missing_dependency": 501, "internal_error": 500,
}
# What to do next, for codes whose message does not already say.
HINTS = {
    "unauthorized": "Send Authorization: Bearer TOKEN with the token the host was started with.",
    "not_found": "Check the id; GET /w/{ws}/documents lists the documents of a workspace.",
    "revision_conflict": "Read the document again (GET /w/{ws}/documents/{id}), then retry with its revision.",
    "request_id_conflict": "Use a fresh request_id for a different request.",
    "expired": "Export results are kept for job_ttl seconds (GET /host/info); export again.",
    "invalid_workspace": "Use 1-64 characters from a-z, 0-9, '-' and '_'.",
    "network_disabled": "The host runs offline; send the bytes instead of a URL.",
    "limit_exceeded": "Make the call smaller, or wait for running calls to finish.",
}


def _jsonable(value):
    return json.loads(json.dumps(value, default=str))


def error_body(exc):
    """The one error shape: ``{code, message, hint, layer_id?, details?}``."""
    details = dict(exc.details)
    hint = details.pop("hint", None)
    suggestions = details.get("suggestions")
    if not hint and isinstance(suggestions, list) and suggestions:
        hint = "; ".join(str(item) for item in suggestions[:3])
    body = {"code": exc.code, "message": str(exc), "hint": hint or HINTS.get(exc.code, "")}
    layer = details.pop("layer_id", None) or details.pop("layer", None)
    if layer is not None:
        body["layer_id"] = layer
    if details:
        body["details"] = _jsonable(details)
    return body


def status_of(exc):
    if exc.code == "limit_exceeded":
        return {"max_concurrent": 429, "max_queue": 503}.get(exc.details.get("limit"), 413)
    return STATUS.get(exc.code, 400)


def capabilities():
    """What this installation can do, probed without importing the optional packages."""
    import importlib.util
    import shutil

    from . import plugins
    from .fetch import offline

    return {"pptx": True, "pdf_import": importlib.util.find_spec("pypdfium2") is not None,
            "ffmpeg": shutil.which("ffmpeg") is not None, "ai": "ai" in plugins.BUILTIN and not offline()}


ROUTES = []


def add_routes(fn):
    """Register ``fn(app, host)``, called by every ``create_host_app`` to add a group of routes."""
    ROUTES.append(fn)
    return fn


class Host:
    """The workspaces under ``root`` and what the routes share: their sessions, limits and job store."""

    def __init__(self, root, *, limits=None, call_limits=None, job_ttl=3600.0):
        from .call_limits import CallLimits
        from .model import Limits

        root = Path(root).expanduser()
        require(not root.exists() or root.is_dir(), f"{root} is not a directory", field="root")
        root.mkdir(parents=True, exist_ok=True)
        self.root = root.resolve()
        from .interfaces import broad_workspace

        require(not broad_workspace(self.root), f"Refusing {self.root} as the host root: it is the home folder or a "
                "filesystem root. Pass --root DIR, a folder for the host's workspaces", "unsafe_workspace",
                field="root")
        self.call_limits = call_limits if call_limits is not None else CallLimits.configure(network="rest")
        self.limits = self.call_limits.apply_to(limits or Limits())
        require(job_ttl > 0, "job_ttl must be positive", field="job_ttl")
        self.job_ttl = float(job_ttl)
        self.sessions = OrderedDict()
        self.lock = threading.RLock()

    def workspace(self, ws):
        """``root/ws``, created on first use; refused unless ``ws`` matches the pattern and resolves inside root."""
        require(isinstance(ws, str) and WORKSPACE.fullmatch(ws), f"Workspace names match {WORKSPACE_PATTERN}",
                "invalid_workspace", field="ws")
        folder = self.root / ws
        if not folder.exists():
            folder.mkdir()
        resolved = folder.resolve()
        require(resolved.is_dir() and resolved.is_relative_to(self.root) and resolved != self.root,
                f"Workspace {ws!r} is outside the host root", "forbidden", field="ws")
        return resolved

    def state_dir(self, ws, *parts):
        folder = self.workspace(ws).joinpath(HOST_DIR, *parts)
        folder.mkdir(parents=True, exist_ok=True)
        return folder

    def session(self, ws):
        """The workspace's session (one per workspace, the least recently used dropped past ``MAX_WORKSPACES``)."""
        from .interfaces import Session

        folder = self.workspace(ws)
        with self.lock:
            session = self.sessions.pop(ws, None)
            if session is None:
                session = Session(workspace=folder, require_document=True, limits=self.limits)
                session.call_limits = self.call_limits
            self.sessions[ws] = session
            while len(self.sessions) > MAX_WORKSPACES:
                self.sessions.popitem(last=False)
            return session

    def info(self):
        from . import __version__
        from .fetch import offline, policy

        return {"vixl": __version__, "host_api": HOST_API, "capabilities": capabilities(),
                "limits": {**self.call_limits.describe(), "max_pixels": self.limits.max_pixels,
                           "max_dimension": self.limits.max_dimension, "max_json_bytes": MAX_JSON_BYTES,
                           "max_upload_bytes": self.limits.max_asset_bytes},
                "job_ttl": self.job_ttl, "offline": offline(), "network": policy(),
                "workspaces": {"pattern": WORKSPACE_PATTERN, "max_loaded": MAX_WORKSPACES}}


def create_host_app(root, token, *, offline=False, call_limits=None, limits=None, job_ttl=3600.0,
                    bind="127.0.0.1"):
    """The ``vixl host`` app. ``token`` is required; ``offline`` turns network access off for the process."""
    try:
        from fastapi import FastAPI, Request
        from fastapi.exceptions import RequestValidationError
        from fastapi.responses import JSONResponse
        from starlette.exceptions import HTTPException
        from starlette.middleware.trustedhost import TrustedHostMiddleware
    except ImportError as exc:
        raise VixlError("missing_dependency", "vixl host needs the server extra: pip install 'vixl-engine[server]'",
                        hint="pip install 'vixl-engine[server]'") from exc
    from . import __version__
    from .interfaces import LOOPBACK, BodyLimit, Failures, require_token, token_matches

    require(isinstance(token, str) and token, f"vixl host needs a bearer token: set {TOKEN_ENV} (or pass "
            "--token-env NAME or --token-file FILE)", "authentication_required", field="token",
            suggestions=['Generate one with: python -c "import secrets; print(secrets.token_urlsafe(32))"'])
    require_token(token)
    if offline:
        from .fetch import OFFLINE_ENV
        from .plugins import external

        require(not external.enabled(), "Third-party plugins cannot run on an offline host", "network_disabled",
                field="plugins")
        os.environ[OFFLINE_ENV] = "1"
    host = Host(root, limits=limits, call_limits=call_limits, job_ttl=job_ttl)
    failures = Failures()

    def answer(exc, headers=None):
        status = status_of(exc)
        if status in (429, 503) and not headers:
            headers = {"Retry-After": str(exc.details.get("retry_after", 3))}
        return JSONResponse(error_body(exc), status_code=status, headers=headers)

    host.answer = answer
    app = FastAPI(title="Vixl host", version=__version__)
    app.state.host = host

    class Body(BodyLimit):
        @staticmethod
        async def refuse(maximum, send):
            exc = VixlError("resource_limit", f"The request body is larger than {maximum:,} bytes",
                            hint="Send a smaller body: downsample images, split operations into several batches",
                            limit=maximum)
            payload = json.dumps(error_body(exc)).encode()
            await send({"type": "http.response.start", "status": 413,
                        "headers": [(b"content-type", b"application/json"),
                                    (b"content-length", str(len(payload)).encode()), (b"connection", b"close")]})
            await send({"type": "http.response.body", "body": payload})

    def body_limit(path):
        return host.limits.max_asset_bytes if path.endswith(("/assets", "/import")) else MAX_JSON_BYTES

    app.add_middleware(Body, maximum=body_limit)  # Inside the guard: an unauthorized body is never read.
    if bind in LOOPBACK:
        app.add_middleware(TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1", "[::1]", "testserver"])

    @app.middleware("http")
    async def guard(request: Request, call_next):
        client = request.client.host if request.client else "unknown"
        wait = failures.retry_after(client)
        if wait:
            return answer(VixlError("too_many_attempts", "Too many failed bearer tokens; retry later",
                                    hint=f"Retry after {wait} s with the right token"), {"Retry-After": str(wait)})
        if not token_matches(request.headers.get("authorization", ""), token):
            failures.failed(client)
            return answer(VixlError("unauthorized", "This host needs a bearer token"), {"WWW-Authenticate": "Bearer"})
        return await call_next(request)

    @app.exception_handler(VixlError)
    async def vixl_error(request: Request, exc: VixlError):
        return answer(exc)

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request: Request, exc: RequestValidationError):
        problems = [{"field": ".".join(str(part) for part in error.get("loc", ())[1:]) or None,
                     "message": error.get("msg")} for error in exc.errors()][:10]
        field = problems[0]["field"] if problems else None
        return answer(VixlError("invalid_request", "The request does not match this endpoint: "
                                + "; ".join(f"{p['field']}: {p['message']}" for p in problems), field=field,
                                errors=problems))

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException):
        code = {404: "not_found", 405: "method_not_allowed"}.get(exc.status_code, "http_error")
        message = "No such endpoint" if exc.status_code == 404 else str(exc.detail)
        response = answer(VixlError(code, message, hint="GET /host/schema lists the endpoints"))
        response.status_code = exc.status_code
        return response

    @app.exception_handler(OSError)
    async def os_error(request: Request, exc: OSError):
        from .errors import friendly

        return answer(friendly(exc, relative_to=host.root))  # Never an absolute path on the server.

    @app.exception_handler(MemoryError)
    async def out_of_memory(request: Request, exc: MemoryError):
        from .errors import friendly

        return answer(friendly(exc))

    @app.get("/host/info")
    def host_info():
        return host.info()

    @app.get("/host/health")
    def host_health():
        return {"ok": True, "warm": bool(host.sessions)}

    @app.get("/w/{ws}")
    def workspace_info(ws: str):
        host.workspace(ws)
        return {"workspace": ws}

    from . import plugins

    for fn in [*ROUTES, *plugins.hooks("host-route")]:
        fn(app, host)
    return app


def read_token(token_env=TOKEN_ENV, token_file=None, environ=None):
    """The bearer token from ``token_file`` (default ``VIXL_HOST_TOKEN_FILE``), else the ``token_env`` variable."""
    environ = os.environ if environ is None else environ
    token_file = token_file or environ.get(TOKEN_FILE_ENV, "").strip() or None
    if token_file:
        path = Path(token_file).expanduser()
        require(path.is_file(), f"No token file at {token_file}", "authentication_required", field="token_file")
        token = path.read_text(encoding="utf-8").strip()
        require(token, f"The token file {token_file} is empty", "authentication_required", field="token_file")
        return token
    token = environ.get(token_env, "").strip()
    require(token, f"vixl host needs a bearer token: set {token_env}, or pass --token-file FILE",
            "authentication_required", field="token",
            suggestions=['Generate one with: python -c "import secrets; print(secrets.token_urlsafe(32))"'])
    return token


def host_parser():
    """The ``vixl host`` flags. Integrations that add host options (an AI provider, for example) extend this."""
    from .call_limits import add_arguments
    from .commands import Parser

    p = Parser(prog="vixl host", description="Serve documents in many workspaces to a host application")
    p.add_argument("--root", help="The folder that holds one sub-folder per workspace")
    p.add_argument("--port", type=int, default=DEFAULT_PORT)
    p.add_argument("--bind", default="127.0.0.1", help="The address to listen on (default 127.0.0.1)")
    p.add_argument("--token-env", default=TOKEN_ENV, help=f"The variable holding the bearer token (default {TOKEN_ENV})")
    p.add_argument("--token-file", help=f"A file holding the bearer token (also {TOKEN_FILE_ENV})")
    p.add_argument("--job-ttl", type=float, default=3600.0, help="Seconds an export result stays downloadable")
    p.add_argument("--schema", action="store_true", help="Print the host API contract (JSON Schema) and exit")
    p.add_argument("--offline", action="store_true",
                   help="Turn off every network access (URL imports, font and pack downloads, providers); also "
                   "VIXL_OFFLINE=1")
    p.add_argument("--tls-cert", help="Serve HTTPS with this PEM certificate (with --tls-key)")
    p.add_argument("--tls-key", help="The PEM private key for --tls-cert")
    add_arguments(p)
    return p


def schema():
    """The host API contract: JSON Schema definitions of every endpoint's request and response."""
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def cli(args, limits=None):
    """``vixl host``: print the contract with ``--schema``, else serve until stopped."""
    from .call_limits import from_arguments
    from .fetch import offline

    a = host_parser().parse_args(args)
    if a.schema:
        return schema()
    require(a.root, "Pass --root DIR: the folder that holds the workspaces", "usage_error", field="root")
    token = read_token(a.token_env, a.token_file)
    from .interfaces import serving_policy

    tls = (a.tls_cert, a.tls_key) if a.tls_cert or a.tls_key else None
    ssl = serving_policy(a.bind, token, tls)
    try:
        import uvicorn
    except ImportError as exc:
        raise VixlError("missing_dependency", "vixl host needs the server extra: pip install 'vixl-engine[server]'",
                        hint="pip install 'vixl-engine[server]'") from exc
    app = create_host_app(a.root, token, offline=a.offline or offline(), call_limits=from_arguments(a, "rest"),
                          limits=limits, job_ttl=a.job_ttl, bind=a.bind)
    import sys

    print(f"vixl host: root {app.state.host.root}, http{'s' if ssl else ''}://{a.bind}:{a.port}", file=sys.stderr)
    uvicorn.run(app, host=a.bind, port=a.port, **ssl)
    return None
