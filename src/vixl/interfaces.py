"""Cached project sessions, fixed-project REST and workspace-scoped MCP services."""

from contextlib import contextmanager
import hmac
from pathlib import Path
from threading import RLock

from .fileio import file_lock

from .assets import add_encoded
from .errors import VixlError, require
from .model import Limits
from . import __version__
from .project import Project
from .validation import validate


def service_check(operation):
    """Restrictions for remote/agent callers, applied after normalization so aliases such as
    ``font_family`` cannot bypass them. Service clients import images explicitly; they cannot
    read arbitrary server files, enable plugins, or resolve linked assets or fonts."""
    from .render import EFFECTS
    from .operations import OPERATION_TYPES

    kind = operation.get("type")
    require(
        not any(k in operation for k in ("linked", "font", "display_font"))
        and ("path" not in operation or (kind in ("text-layout", "shape") or (kind == "select" and operation.get("shape") == "path"))),
        "Filesystem fields (path, linked, font) are unavailable through services; "
        "import images with vixl_import_image and reference the returned asset",
        "forbidden",
        field=next((k for k in ("path", "linked", "font", "display_font") if k in operation), None),
    )
    require(kind in set(OPERATION_TYPES) | set(EFFECTS), "Unsupported service operation", field="type")
    if kind == "effect":
        import difflib

        name = operation.get("name")
        close = difflib.get_close_matches(str(name), EFFECTS, 2, 0.5)
        require(
            name in EFFECTS,
            f"Unknown effect {name!r}"
            + (f"; did you mean {' or '.join(map(repr, close))}?" if close else "; see allowed for built-in effects"),
            "forbidden",
            field="name",
            allowed=list(EFFECTS),
            suggestions=close,
        )
    if kind == "mask":
        require(operation.get("action") != "import", "Import masks using embedded assets", "forbidden")


class _Document:
    __slots__ = ("path", "project", "stamp")

    def __init__(self, path, project, stamp):
        self.path, self.project, self.stamp = path, project, stamp


class Session:
    """Workspace-scoped documents kept loaded between calls.

    Several documents can be open at once (bounded LRU); every method takes an optional
    ``document`` path and otherwise uses the active document."""

    MAX_OPEN = 8

    def __init__(self, path=None, limits=None, *, workspace=None):
        self.limits = limits or Limits()
        self.workspace = Path(workspace or (Path(path).resolve().parent if path else Path.cwd())).resolve()
        require(self.workspace.is_dir(), "Workspace must be an existing directory")
        self.path = None
        self.documents = {}
        self._mutex = RLock()
        if path:
            self.open(path if workspace else Path(path).resolve())

    def resolve(self, path):
        resolved = (self.workspace / path).resolve()
        require(resolved.is_relative_to(self.workspace), "Path is outside the workspace", "forbidden", field="path")
        return resolved

    def relative(self, path):
        return str(Path(path).relative_to(self.workspace))

    @staticmethod
    def stamp(path):
        stat = path.stat()
        return (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)

    def _remember(self, path, project, stamp):
        project._workspace = self.workspace
        self.documents.pop(path, None)
        self.documents[path] = _Document(path, project, stamp)
        while len(self.documents) > self.MAX_OPEN:
            oldest = next(iter(self.documents))
            if oldest == path:
                break
            del self.documents[oldest]  # Everything is already saved; reopening reloads it.
        self.path = path

    def open(self, path):
        with self._mutex:
            resolved = self.resolve(path)
            require(resolved.is_file(), f"Document does not exist: {path}", "not_found", field="path")
            with file_lock(str(resolved)):
                stamp = self.stamp(resolved)
                project = Project.load(resolved, limits=self.limits)
                self._remember(resolved, project, stamp)
            return self.summary(project)

    def create(self, path, width=None, height=None, background="transparent", *, size=None, dpi=None, orientation=None, bleed=False):
        with self._mutex:
            resolved = self.resolve(path)
            require(resolved.suffix.lower() == ".vixl", "Document path must end in .vixl", field="path")
            require(resolved.parent.is_dir(), "Destination directory must exist", field="path")
            require((size is None) != (width is None or height is None), "Provide width and height, or a named size", field="size")
            with file_lock(str(resolved)):
                require(not resolved.exists(), "Destination already exists; open it instead", field="path")
                if size is not None:
                    project = Project.sized(size, background, limits=self.limits, dpi=dpi, orientation=orientation, bleed=bleed)
                else:
                    require(not (orientation or bleed), "orientation and bleed need a named size", field="size")
                    project = Project(width, height, background, limits=self.limits)
                    if dpi:
                        project.apply({"type": "canvas", "dpi": dpi})
                project.save(resolved)
                self._remember(resolved, project, self.stamp(resolved))
            return self.summary(project)

    def close(self, document=None):
        with self._mutex:
            path = self.resolve(document) if document else self.path
            require(path in self.documents, "Document is not open", "no_project", field="document")
            del self.documents[path]
            if self.path == path:
                self.path = next(reversed(self.documents), None)
            return self.open_documents()

    def open_documents(self):
        return {
            "active": self.relative(self.path) if self.path else None,
            "open": [self.relative(path) for path in self.documents],
        }

    def summary(self, project, path=None):
        return {
            "path": self.relative(path or self.path),
            "canvas": project.state["canvas"],
            "layer_count": len(project.state["layers"]),
            "head": project.head,
        }

    @contextmanager
    def project(self, write=False, document=None):
        # Serialize threads and cooperating CLI/service writers. Revalidate only when disk changes.
        with self._mutex:
            if document:
                path = self.resolve(document)
                require(path.suffix.lower() == ".vixl", "Document path must end in .vixl", field="document")
                if path not in self.documents:
                    require(path.is_file(), f"Document does not exist: {document}", "not_found", field="document")
            else:
                require(self.path is not None, "Create or open a document first", "no_project")
                path = self.path
            with file_lock(str(path)):
                entry = self.documents.get(path)
                try:
                    stamp = self.stamp(path)
                    if entry is None or entry.project is None or stamp != entry.stamp:
                        entry = _Document(path, Project.load(path, limits=self.limits), stamp)
                    # Addressing a document explicitly keeps it open but does not change the active one.
                    self.documents.pop(path, None)
                    self.documents[path] = entry
                    while len(self.documents) > self.MAX_OPEN:
                        oldest = next(iter(self.documents))
                        if oldest in (path, self.path):
                            break
                        del self.documents[oldest]
                    project = entry.project
                    project._workspace = self.workspace
                    revision = project._revision
                    yield project
                    if write:
                        project.save()
                    if project._revision != revision:
                        entry.stamp = self.stamp(path)
                except BaseException:
                    # A failed provider, operation or save must never leave unsaved cached state.
                    self.documents.pop(path, None)
                    if self.path == path and not path.exists():
                        self.path = None
                    raise

    def inspect(self, target=None, document=None):
        with self.project(document=document) as p:
            return p.inspect(target)

    def apply(self, operations, dry_run=False, detail="compact", document=None):
        if isinstance(operations, dict):
            operations = operations.get("operations", [operations])
        require(isinstance(operations, list), "Expected operation array")
        with self.project(write=not dry_run, document=document) as p:
            return p.apply(operations, dry_run=dry_run, detail=detail, check=service_check)

    def render(self, variables=None, artboard=None, comp=None, document=None):
        with self.project(document=document) as p:
            return p.export(variables=variables, artboard=artboard, comp=comp, format="PNG")

    def measure_spacing(self, document=None, **options):
        with self.project(document=document) as p:
            return p.measure_spacing(**options)

    def measure(self, document=None, **options):
        with self.project(document=document) as p:
            return p.measure(**options)

    def check(self, document=None, **options):
        with self.project(document=document) as p:
            return p.check(**options)

    def validate(self, profile=None, rules=None, document=None):
        with self.project(document=document) as p:
            return validate(p, profile, rules)

    def history(self, action="list", ref=None, count=1, document=None):
        require(
            action
            in ("list", "undo", "redo", "branch", "checkpoint", "checkout", "begin", "commit", "rollback"),
            "Unknown history action",
            field="action",
        )
        with self.project(write=action != "list", document=document) as p:
            if action in ("undo", "redo"):
                getattr(p, action)(count)
            elif action in ("branch", "checkpoint", "checkout"):
                require(ref, f"History {action} requires ref", field="ref")
                getattr(p, action)(ref)
            elif action in ("begin", "commit", "rollback"):
                getattr(p, action)()
            return {
                "head": p.head,
                "branch": p.current_branch,
                "branches": p.branches,
                "checkpoints": p.checkpoints,
                "nodes": [{k: v for k, v in node.items() if k not in ("state", "delta")} for node in p.nodes.values()],
            }

    def import_image(self, data, name="image", document=None):
        with self.project(write=True, document=document) as p:
            asset, _ = add_encoded(p, data)
            p.apply({"type": "add", "asset": asset, "name": name})
            layer = p.inspect(p.state["active_layer"])
            return {
                "id": layer["id"],
                "name": layer["name"],
                "width": layer["width"],
                "height": layer["height"],
                "bounds": layer["resolved_bounds"],
                "asset": asset,
            }

    def ai(self, command, args, document=None):
        from .ai import ai_command

        require(command in ("ask", "generate", "ai", "select", "detect", "ocr"), "Unsupported AI command")
        require(isinstance(args, list) and all(isinstance(x, str) for x in args), "AI args must be strings")
        require(not any(x in ("-h", "--help") for x in args), "Help flags are not service commands")
        with self.project(document=document) as p:
            result, changed = ai_command(p, command, args)
            if changed:
                p.save()
            return result


def create_app(path, *, token=None, limits=None):
    try:
        from fastapi import FastAPI, Request
        from fastapi.responses import JSONResponse, Response
        from starlette.middleware.trustedhost import TrustedHostMiddleware
    except ImportError as exc:
        raise VixlError("missing_dependency", "Install vixl-engine[server]") from exc
    session = Session(path, limits)
    app = FastAPI(title="Vixl Engine", version=__version__)
    if not token:
        app.add_middleware(
            TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1", "[::1]", "testserver"]
        )

    @app.middleware("http")
    async def guard(request: Request, call_next):
        if request.url.path != "/view" and token and not hmac.compare_digest(request.headers.get("authorization", ""), "Bearer " + token):
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        origin = request.headers.get("origin")
        if origin and origin != str(request.base_url).rstrip("/"):
            return JSONResponse({"error": "cross_origin_forbidden"}, status_code=403)
        maximum = session.limits.max_asset_bytes if request.url.path in ("/assets", "/fonts", "/import") else 1024 * 1024
        if request.url.path == "/fonts":
            maximum = min(maximum, 16 * 1024 * 1024)
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > maximum:
                return JSONResponse({"error": "resource_limit"}, status_code=413)
        request._body = bytes(body)
        return await call_next(request)

    @app.exception_handler(VixlError)
    async def vixl_error(request: Request, exc: VixlError):
        return JSONResponse(exc.as_dict(), status_code=403 if exc.code == "forbidden" else 400)

    @app.get("/view")
    def viewer():
        from fastapi.responses import HTMLResponse
        return HTMLResponse((Path(__file__).parent / "data" / "view.html").read_text(encoding="utf-8"),
                            headers={"Cache-Control": "no-store", "X-Frame-Options": "DENY"})

    @app.get("/review")
    def review():
        from .review import notes
        with session.project() as project:
            return {"head": project.head, "layers": project.inspect()["layers"],
                    "history": session.history()["nodes"], **notes(session.path)}

    @app.get("/notes")
    def review_notes():
        from .review import notes
        return notes(session.path)

    @app.post("/notes")
    def add_note(body: dict):
        from .review import notes
        return notes(session.path, "add", text=body.get("text"))

    @app.post("/notes/{note_id}/resolve")
    def resolve_note(note_id: str):
        from .review import notes
        return notes(session.path, "resolve", note_id=note_id)

    @app.get("/schema")
    def schema():
        from .schema import operation_schema

        return operation_schema()

    @app.get("/workflow/schema")
    def workflow_schema():
        from .workflows import describe
        return describe()

    @app.post("/workflow/{action}")
    def workflow(action: str, body: dict):
        from .workflows import dispatch
        # REST remains scoped to its active project. Other document/library/job I/O is MCP/CLI only.
        from .studio import REST_ACTIONS
        require(action in {"check", "act", "plan", "film-plan", "lyric-video-plan", "organic-catalog", "form-fill", "drawing-report"} | REST_ACTIONS,
                "This workflow needs a workspace CLI/MCP session", "forbidden")
        return dispatch(session, action, body)

    @app.get("/resources/{kind}")
    def resources_list(kind: str):
        from .resources import catalog

        return {"names": sorted(catalog(kind))}

    @app.get("/resources/{kind}/{name}")
    def resource_get(kind: str, name: str):
        from .resources import get

        return {"name": name, "value": get(kind, name)}

    @app.post("/resources/{kind}/{name}")
    def resource_add(kind: str, name: str, body: dict):
        from .resources import register

        return register(kind, name, body.get("value"))

    @app.post("/export")
    def export_document(body: dict):
        allowed = {
            "format",
            "quality",
            "scale",
            "variables",
            "background",
            "artboard",
            "comp",
            "sampling",
            "profile",
            "svg_policy",
            "color_space",
            "icc_profile_base64",
            "intent",
            "black_generation",
            "ink_limit",
            "proof",
            "simulate",
            "dpi",
            "icon_sizes",
            "time",
            "page",
            "pages",
            "pdf_content",
            "fillable",
            "values",
            "fill_mode",
        }
        require(set(body) <= allowed, "Unknown export option")
        fmt = body.get("format", "PNG").upper()
        media = {
            "PNG": "image/png",
            "JPEG": "image/jpeg",
            "JPG": "image/jpeg",
            "SVG": "image/svg+xml",
            "HTML": "text/html",
            "WEBP": "image/webp",
            "TIFF": "image/tiff",
            "AVIF": "image/avif",
            "PDF": "application/pdf",
            "ICO": "image/x-icon",
            "PPTX": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        }
        require(fmt in media, "Unsupported export format")
        body = dict(body)
        if "icc_profile_base64" in body:
            from .mcp_tools import decode_upload

            body["icc_profile"] = decode_upload(body.pop("icc_profile_base64"), 16 * 1024 * 1024)
        with session.project() as project:
            return Response(project.export(**body), media_type=media[fmt])

    @app.get("/sizes")
    def size_catalog(category: str | None = None, search: str | None = None):
        from .sizes import catalog

        return catalog(category, search)

    @app.get("/layouts")
    def layout_catalog():
        from .layouts import catalog

        return catalog()

    @app.get("/typefaces")
    def typeface_catalog(category: str | None = None, role: str | None = None, mood: str | None = None):
        from .typefaces import list_fonts

        return list_fonts(category, role, mood)

    @app.get("/typefaces/pairings")
    def typeface_pairings(mood: str | None = None, best_for: str | None = None, family: str | None = None):
        from .typefaces import list_pairings

        return list_pairings(mood, best_for, family)

    @app.post("/typefaces/pair")
    def typeface_pair(body: dict):
        from .typefaces import pair_fonts

        with session.project(write=True) as project:
            return pair_fonts(project, body.get("pairing", "random"), seed=body.get("seed"), mood=body.get("mood"), best_for=body.get("best_for"))

    @app.post("/typefaces/install")
    def typeface_install(body: dict):
        from .typefaces import install_font

        require(isinstance(body.get("family"), str), "family is required", field="family")
        with session.project(write=True) as project:
            return install_font(project, body["family"], body.get("weight", 400), body.get("italic", False), body.get("name"), body.get("role"))

    @app.get("/roll")
    def design_roll(purpose: str | None = None, mood: str | None = None, seed: int | None = None):
        from .typefaces import roll_document

        with session.project() as project:
            return roll_document(project, seed=seed, purpose=purpose, mood=mood)

    @app.get("/brushes")
    def brush_catalog():
        from .brushes import catalog

        return catalog()

    @app.post("/color")
    def color_tools(body: dict):
        from .feature_cli import color_command

        action = body.get("action", "info")
        colors = body.get("colors", [])
        require(isinstance(colors, list) and 0 < len(colors) <= 16, "colors must be a list of 1–16 values")
        args = [action, *map(str, colors)]
        for key in ("to", "scheme", "count", "amount", "space"):
            if key in body:
                args += ["--" + key, str(body[key])]
        result = color_command(args)
        return result if isinstance(result, dict) else {"results": result}

    @app.get("/timeline")
    def timeline():
        from .timeline import inspect_timeline

        with session.project() as p:
            return inspect_timeline(p)

    @app.get("/timeline/frame")
    def timeline_frame(time: str = "0", max_width: int = 1024, max_height: int = 1024):
        from .mcp_tools import preview

        value = float(time) if time.replace(".", "", 1).isdigit() else time
        return Response(preview(session, None, max_width, max_height, 4_194_304, time=value), media_type="image/png")

    @app.post("/timeline/export")
    def timeline_export(body: dict):
        import tempfile

        from .timeline import export_timeline

        allowed = {"format", "fps", "scale", "start", "end", "background", "columns", "quality", "colors"}
        require(set(body) <= allowed, f"Timeline export accepts {sorted(allowed)}", field="body")
        fmt = body.get("format", "gif")
        suffix = {"gif": ".gif", "apng": ".png", "webp": ".webp", "sheet": ".png", "frames": ".zip", "mp4": ".mp4", "webm": ".webm"}
        require(fmt in suffix, "Unsupported timeline format", field="format")
        media = {"gif": "image/gif", "apng": "image/apng", "webp": "image/webp", "sheet": "image/png", "frames": "application/zip", "mp4": "video/mp4", "webm": "video/webm"}
        with tempfile.TemporaryDirectory(prefix="vixl-timeline-") as staging:
            path = Path(staging) / ("animation" + suffix[fmt])
            with session.project() as p:
                export_timeline(p, path, **body)
            return Response(path.read_bytes(), media_type=media[fmt])

    @app.post("/fonts")
    async def fonts(request: Request, name: str):
        import hashlib
        from .fonts import validate_font

        data = await request.body()
        validate_font(data)
        with session.project(write=True) as project:
            asset = f"fonts/{hashlib.sha256(data).hexdigest()}.ttf"
            project.assets[asset] = data
            return project.apply({"type": "font-register", "name": name, "asset": asset}, detail="compact")

    @app.get("/document")
    def document():
        return session.inspect()

    @app.get("/layers")
    def layers():
        return session.inspect()["layers"]

    @app.post("/operations")
    def operations(body: dict):
        return session.apply(
            body.get("operations"), bool(body.get("dry_run", False)), body.get("detail", "compact")
        )

    @app.get("/render")
    def render():
        return Response(session.render(), media_type="image/png")

    @app.post("/render")
    def render_variables(body: dict):
        return Response(
            session.render(body.get("variables"), body.get("artboard"), body.get("comp")),
            media_type="image/png",
        )

    def fixed(body):
        # The REST service is bound to one document; it never opens other workspace files.
        require("document" not in body, "This server serves one fixed document", "forbidden", field="document")
        return body

    @app.post("/spacing")
    def spacing(body: dict):
        return session.measure_spacing(**fixed(body))

    @app.post("/check")
    def check(body: dict):
        return session.check(**fixed(body))

    @app.post("/preview")
    def preview_image(body: dict):
        from .mcp_tools import preview

        options = fixed(body)
        allowed = {"variables", "max_width", "max_height", "max_bytes", "artboard", "comp", "region", "time", "proof", "simulate",
                   "guides", "page", "values", "show_fields"}
        require(not set(options) - allowed, f"Preview accepts {sorted(allowed)}", field="body")
        return Response(preview(session, **options), media_type="image/png")

    @app.post("/compare")
    def compare_revisions(body: dict):
        import base64
        import io
        from .checks import compare

        options = fixed(body)
        with session.project() as p:
            image, summary = compare(
                p,
                options.get("before", "previous"),
                options.get("after", "head"),
                mode=options.get("mode", "side-by-side"),
            )
        stream = io.BytesIO()
        image.save(stream, format="PNG")
        return {**summary, "image_base64": base64.b64encode(stream.getvalue()).decode()}

    @app.get("/pixels/{target}")
    def pixels(target: str):
        with session.project() as p:
            return p.inspect_pixels(target)

    @app.get("/animation")
    def animation():
        with session.project() as p:
            return p.inspect_animation()

    @app.get("/animation/frame/{name}")
    def animation_frame(name: str, scale: float = 1, sampling: str = "nearest"):
        import io

        with session.project() as p:
            image = p.render_frame(name, int(scale) if float(scale).is_integer() else scale, sampling)
            stream = io.BytesIO()
            image.save(stream, format="PNG")
            return Response(stream.getvalue(), media_type="image/png")

    @app.post("/animation/export")
    def animation_export(body: dict):
        from .animation import animation_bytes

        allowed = {"format", "scale", "sampling", "colors", "columns"}
        require(set(body) <= allowed, f"Animation export accepts {sorted(allowed)}", field="body")
        if isinstance(body.get("scale"), float) and body["scale"].is_integer():
            body["scale"] = int(body["scale"])
        fmt = body.get("format", "gif")
        with session.project() as p:
            data, _ = animation_bytes(p, **body)
        return Response(data, media_type={"gif": "image/gif", "apng": "image/apng"}.get(fmt, "image/png"))

    @app.post("/measure")
    def measure(body: dict):
        return session.measure(**fixed(body))

    @app.post("/validate")
    def validation(body: dict):
        return session.validate(body.get("profile"), body.get("rules"))

    @app.get("/history")
    def history():
        return session.history()

    @app.post("/history/{action}")
    def history_action(action: str, body: dict):
        return session.history(action, body.get("ref"), body.get("count", 1))

    @app.post("/import")
    async def import_document(request: Request, format: str, name: str = "import", page: int = 1, dpi: int = 144, svg_mode: str = "editable"):
        from .imports import import_document as execute_import
        from starlette.concurrency import run_in_threadpool
        data = await request.body()
        def apply_import():
            with session.project(write=True) as project:
                return execute_import(project, data, format, name, page, dpi, svg_mode)
        return await run_in_threadpool(apply_import)

    @app.post("/assets")
    async def assets(request: Request, name: str = "image"):
        from starlette.concurrency import run_in_threadpool

        return await run_in_threadpool(session.import_image, await request.body(), name)

    @app.post("/ai/{command}")
    def ai(command: str, body: dict):
        return session.ai(command, body.get("args", []))

    return app


def serve(path, host="127.0.0.1", port=8765, token=None, limits=None, *, open_browser=False):
    require(
        host in ("127.0.0.1", "localhost", "::1") or token,
        "Non-loopback serving requires VIXL_API_TOKEN",
        "authentication_required",
    )
    try:
        import uvicorn
    except ImportError as exc:
        raise VixlError("missing_dependency", "Install vixl-engine[server]") from exc
    app = create_app(path, token=token, limits=limits)
    if open_browser:
        import asyncio
        import webbrowser

        class ViewerServer(uvicorn.Server):
            async def startup(self, sockets=None):
                await super().startup(sockets=sockets)
                if self.started:
                    local_host = "127.0.0.1" if host == "0.0.0.0" else "::1" if host == "::" else host
                    address = f"[{local_host}]" if ":" in local_host else local_host
                    await asyncio.to_thread(webbrowser.open, f"http://{address}:{port}/view")

        ViewerServer(uvicorn.Config(app, host=host, port=port)).run()
    else:
        uvicorn.run(app, host=host, port=port)


def mcp_server(path=None, limits=None, *, workspace=None, schema="full", planner=False, tools="all"):
    try:
        from .mcp_tools import build_server
        import mcp.server.fastmcp  # noqa: F401
    except ImportError as exc:
        raise VixlError("missing_dependency", "Install vixl-engine[mcp]") from exc

    return build_server(Session(path, limits, workspace=workspace), schema=schema, planner=planner, tools=tools)


def mcp_http_app(server, *, token=None):
    """SDK Streamable HTTP with the REST bearer-token and same-origin policy."""
    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.middleware.trustedhost import TrustedHostMiddleware
    from starlette.responses import JSONResponse
    from mcp.server.transport_security import TransportSecuritySettings

    # Our guard handles both public, token-protected hosts and loopback DNS rebinding.
    server.settings.transport_security = TransportSecuritySettings(enable_dns_rebinding_protection=False)
    app = server.streamable_http_app()

    async def guard(request, call_next):
        if token and not hmac.compare_digest(request.headers.get("authorization", ""), "Bearer " + token):
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        origin = request.headers.get("origin")
        if origin and origin != str(request.base_url).rstrip("/"):
            return JSONResponse({"error": "cross_origin_forbidden"}, status_code=403)
        return await call_next(request)

    app.add_middleware(BaseHTTPMiddleware, dispatch=guard)
    if not token:
        app.add_middleware(TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1", "[::1]", "testserver"])
    return app


def serve_mcp(server, host="127.0.0.1", port=8766, token=None):
    require(host in ("127.0.0.1", "localhost", "::1") or token,
            "Non-loopback serving requires VIXL_API_TOKEN", "authentication_required")
    import uvicorn
    uvicorn.run(mcp_http_app(server, token=token), host=host, port=port)

