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
DOCUMENT_ID = re.compile(r"d_[0-9a-f]{8}")
MAX_JOBS = 200
MAX_LAYERS = 2000  # Layers one document summary lists at most (``max_layers``).
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
        self.doc_locks = {}
        from .call_limits import BoundedExecutor, Limiter, RestJobs
        from .idempotency import RequestLog

        self.jobs = RestJobs(self.call_limits.hard_timeout, maximum=MAX_JOBS)
        self.limiter = Limiter(self.call_limits, self.jobs, BoundedExecutor(16, name="vixl-host"))
        self.requests = RequestLog()

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

    # ------------------------------------------------------------------------------------------ documents

    def index_path(self, ws):
        return self.state_dir(ws) / "index.json"

    def read_index(self, ws):
        path = self.index_path(ws)
        if not path.is_file():
            return {"host_api": HOST_API, "documents": {}}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except ValueError as exc:
            raise VixlError("invalid_index", f"The document index of workspace {ws!r} is not valid JSON") from exc
        require(isinstance(data, dict) and isinstance(data.get("documents"), dict),
                f"The document index of workspace {ws!r} is malformed", "invalid_index")
        return data

    def update_index(self, ws, change):
        """Apply ``change(index)`` under the workspace's lock and write the index atomically; returns its result."""
        from .fileio import file_lock, temporary

        path = self.index_path(ws)
        with self.lock_for(ws, None), file_lock(str(path)):
            data = self.read_index(ws)
            result = change(data)
            fd, staged = temporary(path.parent, ".json")
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(data, handle, indent=1, sort_keys=True)
            os.replace(staged, path)
            return result

    def lock_for(self, ws, doc):
        with self.lock:
            return self.doc_locks.setdefault((ws, doc), threading.RLock())

    def entry(self, ws, doc):
        """The index entry of document ``doc``; ``not_found`` for an unknown id."""
        require(isinstance(doc, str) and DOCUMENT_ID.fullmatch(doc), f"Document ids look like d_1a2b3c4d, not {doc!r}",
                "not_found", field="id")
        entry = self.read_index(ws)["documents"].get(doc)
        require(entry is not None, f"No document {doc!r} in workspace {ws!r}", "not_found", field="id")
        return entry

    @staticmethod
    def relative(doc):
        return f"{doc}.vixl"

    def new_id(self, ws):
        import uuid

        existing = self.read_index(ws)["documents"]
        while True:
            doc = "d_" + uuid.uuid4().hex[:8]
            if doc not in existing and not (self.workspace(ws) / self.relative(doc)).exists():
                return doc

    def register(self, ws, doc, name=None):
        """Add a new document to the index at revision 1."""
        import time

        now = time.time()

        def add(index):
            index["documents"][doc] = {"id": doc, "path": self.relative(doc), "revision": 1, "created": now,
                                       "updated": now, **({"name": name} if name else {})}
            return dict(index["documents"][doc])

        return self.update_index(ws, add)

    def bump(self, ws, doc):
        """The next revision of ``doc``, recorded in the index."""
        import time

        def advance(index):
            entry = index["documents"].get(doc)
            require(entry is not None, f"Document {doc!r} was deleted", "not_found", field="id")
            entry["revision"] += 1
            entry["updated"] = time.time()
            return entry["revision"]

        return self.update_index(ws, advance)

    def mutate(self, ws, doc, if_revision, fn, *, bump=True):
        """Run ``fn(session, path)`` on ``doc`` holding its lock: refused with ``revision_conflict`` when
        ``if_revision`` is not the current revision; the revision goes up by one when ``bump`` and ``fn`` succeeded.
        Returns ``(result, revision)``."""
        require(if_revision is None or (type(if_revision) is int and if_revision >= 1),
                "if_revision is the revision a change is based on: a positive whole number", field="if_revision")
        with self.lock_for(ws, doc):
            entry = self.entry(ws, doc)
            if if_revision is not None and if_revision != entry["revision"]:
                raise VixlError("revision_conflict", f"{doc} is at revision {entry['revision']}, not {if_revision}; "
                                "another change came first", revision=entry["revision"], if_revision=if_revision,
                                hint="Read the document again, then retry with its current revision")
            result = fn(self.session(ws), self.relative(doc))
            return result, (self.bump(ws, doc) if bump else entry["revision"])

    def read(self, ws, doc, fn):
        """``fn(session, path)`` on ``doc`` and its current revision, without changing it."""
        return self.mutate(ws, doc, None, fn, bump=False)

    async def call(self, ws, route, fn, *, request_id=None, body=None, document=None, heavy=True):
        """Run ``fn()`` for a route: heavy calls through the limiter (they may answer 202 with a job), and with a
        ``request_id`` at most once per workspace: a repeat with the same body returns the first result
        (``replayed: true``), a different body is ``request_id_conflict``."""
        from fastapi.responses import JSONResponse
        from starlette.concurrency import run_in_threadpool

        from .idempotency import fingerprint

        folder = self.workspace(ws)
        entry, key = None, (ws, request_id)
        if request_id is not None:
            require(isinstance(request_id, str) and 0 < len(request_id) <= 64,
                    "request_id is a string of 1-64 characters", field="request_id")
            outcome, entry = self.requests.start(request_id, route, fingerprint(route, body), (ws, document),
                                                 key=key)
            if outcome == "running":
                await run_in_threadpool(entry["done"].wait, 20)
                if entry["result"] is None:
                    job = entry.get("job")
                    return JSONResponse({"status": "running", "request_id": request_id,
                                         **({"job_id": job, "poll": f"/jobs/{job}"} if job else {}),
                                         "message": "The first call with this request_id is still running; poll "
                                                    "its job or repeat this call shortly"}, status_code=202,
                                        headers={"Retry-After": "3"})
            if outcome != "new":
                replay = json.loads(entry["result"])
                if isinstance(replay, dict):
                    replay.update(replayed=True, request_id=request_id)
                return replay

        def work():
            try:
                result = fn()
            except BaseException:
                if entry is not None:
                    self.requests.discard(key, entry)
                raise
            if entry is not None:
                self.requests.finish(entry, json.dumps(result, default=str))
            return result

        if not heavy:
            return await run_in_threadpool(work)
        outcome, value = await self.limiter.run(folder, route, work)
        if outcome == "job":
            from .call_limits import detached

            if entry is not None:
                entry["job"] = value
            return JSONResponse({**detached(value, route, self.call_limits.timeout), "job_id": value},
                                status_code=202, headers={"Location": f"/jobs/{value}", "Retry-After": "3"})
        return value

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

    for fn in [*BUILTIN_ROUTES, *ROUTES, *plugins.hooks("host-route")]:
        fn(app, host)
    return app


# ------------------------------------------------------------------------------------------------ route groups

CREATE_FIELDS = {"name", "size", "width", "height", "purpose", "brief", "background", "dpi", "orientation", "bleed",
                 "seed", "variety", "house_style", "font_pairing", "workspace_fonts", "template", "variables",
                 "request_id"}
OPERATION_FIELDS = {"operations", "dry_run", "detail", "check", "preview", "suites", "repair", "if_revision",
                    "request_id"}
IMPORT_FORMATS = ("svg", "pdf")


def _summary(session, path, project, revision, doc, max_layers=MAX_LAYERS):
    """A document's state: canvas, head and its layers (id, name, type, parent, visible and canvas bounds)."""
    from .untrusted import mark

    layers = project.inspect()["layers"]
    shown = []
    for layer in layers[:max_layers]:
        item = {"id": layer["id"], "name": layer.get("name"), "type": layer.get("type"),
                "parent": layer.get("parent"), "visible": layer.get("visible", True),
                "bounds": [round(value, 3) for value in layer.get("canvas_bounds") or ()]}
        if isinstance(layer.get("text"), str):
            item["text"] = layer["text"][:500]
        shown.append(item)
    pages = project.state.get("pages") or []
    result = {"id": doc, "revision": revision, "canvas": project.state["canvas"], "head": project.head,
              "layer_count": len(layers), "pages": len(pages), "layers": shown, "truncated": len(layers) > len(shown)}
    return mark(result)


def _known(body, allowed, route):
    from .interfaces import known_fields

    require(isinstance(body, dict), f"The {route} body is a JSON object", "invalid_request")
    known_fields(body, allowed, route)


def document_routes(app, host):
    """Documents and operations (#538): create, import, list, read, blob, operations, assets, artwork import and
    delete. Every route wraps ``Session`` methods; each change raises the document's revision by one."""
    from fastapi import Request
    from fastapi.responses import Response

    @app.get("/w/{ws}/documents")
    def list_documents(ws: str):
        index = host.read_index(ws)
        return {"workspace": ws, "documents": sorted(index["documents"].values(), key=lambda e: e["created"])}

    @app.post("/w/{ws}/documents", status_code=201)
    async def create_document(ws: str, body: dict):
        _known(body, CREATE_FIELDS, "create")
        options = {key: value for key, value in body.items() if key != "request_id"}

        def create():
            doc = host.new_id(ws)
            session, path = host.session(ws), host.relative(doc)
            created = _create(session, path, dict(options))
            entry = host.register(ws, doc, options.get("name"))
            with session.project(document=path) as project:
                summary = _summary(session, path, project, entry["revision"], doc)
            return {**summary, **({"name": entry["name"]} if "name" in entry else {}),
                    **{key: created[key] for key in ("creation", "template", "brief", "typography",
                                                     "font_pairing_error", "workspace_fonts") if created.get(key)}}

        return await host.call(ws, "create", create, request_id=body.get("request_id"), body=options)

    @app.post("/w/{ws}/documents/import", status_code=201)
    async def import_vixl(ws: str, request: Request, name: str | None = None, request_id: str | None = None):
        import hashlib

        data = await request.body()
        require(data, "Send the .vixl file as the request body", "invalid_request", field="body")

        def load():
            from .project import Project

            doc = host.new_id(ws)
            staging = host.state_dir(ws, "tmp")
            from .fileio import temporary

            fd, staged = temporary(staging, ".vixl")
            with os.fdopen(fd, "wb") as handle:
                handle.write(data)
            try:
                # Loading applies the archive budgets (bytes, entries, image pixels, fonts) and the document checks.
                project = Project.load(staged, limits=host.limits)
                target = host.workspace(ws) / host.relative(doc)
                require(not target.exists(), f"{doc} exists", "invalid_request")
                os.replace(staged, target)
            finally:
                Path(staged).unlink(missing_ok=True)
            entry = host.register(ws, doc, name)
            session = host.session(ws)
            return _summary(session, host.relative(doc), project, entry["revision"], doc)

        return await host.call(ws, "import", load, request_id=request_id,
                               body={"sha256": hashlib.sha256(data).hexdigest(), "name": name})

    @app.get("/w/{ws}/documents/{doc}")
    def get_document(ws: str, doc: str, max_layers: int = 500):
        require(1 <= max_layers <= MAX_LAYERS, f"max_layers is 1-{MAX_LAYERS}", field="max_layers")

        def state(session, path):
            with session.project(document=path) as project:
                return _summary(session, path, project, None, doc, max_layers)

        summary, revision = host.read(ws, doc, state)
        return {**summary, "revision": revision}

    @app.get("/w/{ws}/documents/{doc}/blob")
    def document_blob(ws: str, doc: str):
        def blob(session, path):
            with session.project(document=path):
                return session.resolve(path).read_bytes()

        data, revision = host.read(ws, doc, blob)
        return Response(data, media_type="application/vnd.vixl+zip",
                        headers={"X-Vixl-Revision": str(revision),
                                 "Content-Disposition": f'attachment; filename="{doc}.vixl"'})

    @app.post("/w/{ws}/documents/{doc}/operations")
    async def apply_operations(ws: str, doc: str, body: dict):
        import base64

        _known(body, OPERATION_FIELDS, "operations")
        operations = body.get("operations")
        require(isinstance(operations, (list, dict)), "operations is a list of operations", field="operations")
        dry_run = body.get("dry_run", False)
        require(type(dry_run) is bool, "dry_run is a boolean", field="dry_run")

        def apply(session, path):
            from .critique import take_previews

            result, image = session.apply_reviewed(
                operations, dry_run, body.get("detail", "compact"), document=path, check=body.get("check"),
                preview=body.get("preview"), suites=body.get("suites"), repair=body.get("repair"))
            for entry, png in zip(result.get("check", {}).get("regions", []), take_previews(result)):
                entry["preview_base64"] = base64.b64encode(png).decode()
            if image is not None:
                result["preview_base64"] = base64.b64encode(image).decode()
            return result

        def run():
            result, revision = host.mutate(ws, doc, body.get("if_revision"), apply, bump=not dry_run)
            return _marked({**result, "id": doc, "revision": revision})

        return await host.call(ws, "operations", run, request_id=body.get("request_id"),
                               body={k: v for k, v in body.items() if k != "request_id"}, document=doc)

    @app.post("/w/{ws}/documents/{doc}/assets")
    async def add_asset(ws: str, doc: str, request: Request, name: str = "image", credit: str | None = None,
                        license: str | None = None, if_revision: int | None = None, request_id: str | None = None):
        import hashlib

        data = await request.body()
        require(data, "Send the image bytes as the request body", "invalid_request", field="body")

        def add(session, path):
            return session.import_image(data, name, document=path, credit=credit, license=license)

        def run():
            result, revision = host.mutate(ws, doc, if_revision, add)
            return {**result, "id": doc, "revision": revision}

        return await host.call(ws, "assets", run, request_id=request_id, document=doc, heavy=False,
                               body={"sha256": hashlib.sha256(data).hexdigest(), "name": name, "credit": credit,
                                     "license": license, "if_revision": if_revision})

    @app.post("/w/{ws}/documents/{doc}/import")
    async def import_artwork(ws: str, doc: str, request: Request, format: str, name: str = "import", page: int = 1,
                             dpi: int = 144, svg_mode: str = "editable", if_revision: int | None = None,
                             request_id: str | None = None):
        import hashlib

        require(format in IMPORT_FORMATS, f"format is one of {', '.join(IMPORT_FORMATS)}", field="format")
        data = await request.body()
        require(data, "Send the file as the request body", "invalid_request", field="body")

        def add(session, path):
            from .imports import import_document

            with session.project(write=True, document=path) as project:
                return import_document(project, data, format, name, page, dpi, svg_mode)

        def run():
            result, revision = host.mutate(ws, doc, if_revision, add)
            return _marked({**result, "id": doc, "revision": revision})

        return await host.call(ws, "import-artwork", run, request_id=request_id, document=doc,
                               body={"sha256": hashlib.sha256(data).hexdigest(), "format": format, "name": name,
                                     "page": page, "dpi": dpi, "svg_mode": svg_mode, "if_revision": if_revision})

    @app.delete("/w/{ws}/documents/{doc}")
    def delete_document(ws: str, doc: str, if_revision: int | None = None):
        def remove(session, path):
            try:
                session.close(path)
            except VixlError:
                pass  # Not open in this session.
            target = session.resolve(path)
            for extra in (target, target.with_name(target.name + ".notes.json")):
                extra.unlink(missing_ok=True)

        _, revision = host.mutate(ws, doc, if_revision, remove, bump=False)
        host.update_index(ws, lambda index: index["documents"].pop(doc, None))
        return {"deleted": doc, "revision": revision}


def _marked(result):
    from .untrusted import mark

    return mark(result)


def _create(session, path, options):
    """Create the document through ``Session.create`` (or a template, or the first size a brief suggests)."""
    from .briefs import guide

    options.pop("name", None)
    template, variables = options.pop("template", None), options.pop("variables", None)
    font_pairing = options.pop("font_pairing", None)
    brief = options.pop("brief", None)
    report = {}
    if brief is not None:
        require(isinstance(brief, str) and brief.strip(), "brief is the words of the request", field="brief")
        found = guide(brief)
        report["brief"] = {key: found.get(key) for key in ("matched", "kind", "title") if found.get(key)}
        if not any(options.get(key) for key in ("size", "width", "height", "purpose")) and found.get("sizes"):
            options["size"] = found["sizes"][0]
            report["brief"]["size"] = options["size"]
    if template is not None:
        from .fileio import file_lock
        from .resources import create_template

        require(not options, "A template sets its own size and design; drop " + ", ".join(sorted(options)),
                field="template")
        destination = session.resolve(path)
        with session._mutex, file_lock(str(destination)):
            require(not destination.exists(), "Destination already exists", field="path")
            project = create_template(template, variables, limits=session.limits, workspace=session.workspace)
            project.save(destination)
        report["template"] = project.state.get("template") or template
        return report
    require(variables is None, "variables fill a template; pass template too", field="variables")
    workspace_fonts = options.pop("workspace_fonts", True)
    created = session.create(path, options.pop("width", None), options.pop("height", None),
                             options.pop("background", None), workspace_fonts=workspace_fonts and not font_pairing,
                             **options)
    report.update({key: created[key] for key in ("creation", "workspace_fonts") if created.get(key)})
    if font_pairing:
        from .typefaces import pair_fonts

        try:
            with session.project(write=True, document=path) as project:
                report["typography"] = pair_fonts(project, font_pairing)
        except VixlError as exc:  # The document exists; say the pairing did not apply.
            report["font_pairing_error"] = str(exc)
    return report


def job_routes(app, host):
    """Calls that outlived the timeout, and export jobs (#540)."""

    @app.get("/jobs/{ident}")
    async def job_status(ident: str, wait: float = 0):
        return job_summary(host, await _finished(host, ident, wait))

    @app.get("/jobs/{ident}/result")
    async def job_result(ident: str, wait: float = 0):
        job = await _finished(host, ident, wait)
        require(job["future"].done(), f"Job {ident} is still running", "job_running", field="id",
                hint=f"Poll /jobs/{ident}?wait=20")
        return job["future"].result()  # A failure re-raises; the handlers answer as the call would have.


async def _finished(host, ident, wait):
    import asyncio

    job = host.jobs.get(ident)
    if wait and not job["future"].done():
        try:
            await asyncio.wait_for(asyncio.shield(asyncio.wrap_future(job["future"])), min(float(wait), 50))
        except Exception:  # noqa: BLE001 - Timed out or failed: the summary says which.
            pass
    return job


def job_summary(host, job):
    """``{id, kind, status, progress, error?, ...}`` with the error in the host's error shape."""
    from .errors import friendly

    summary = host.jobs.summary(job)
    future = job["future"]
    error = future.exception() if future.done() and not future.cancelled() else None
    result = {"id": job["id"], "kind": job.get("kind", "call"), "status": summary["status"],
              "progress": job.get("progress") or {"fraction": 1.0 if future.done() else None},
              "elapsed_s": summary["elapsed_s"]}
    if job.get("kind", "call") == "call":
        result.update(route=job["route"], result_url=f"/jobs/{job['id']}/result")
    if error is not None:
        result["error"] = error_body(friendly(error))
    if summary["status"] == "running":
        result["retry_after_s"] = 3
    return result


BUILTIN_ROUTES = [document_routes, job_routes]


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
