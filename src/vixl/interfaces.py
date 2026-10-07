"""Cached project sessions, fixed-project REST and workspace-scoped MCP services."""

from contextlib import contextmanager
import hmac
from pathlib import Path
from threading import RLock
from weakref import WeakKeyDictionary

from .calls import current_client, note_document
from .fileio import file_lock

from .errors import VixlError, require
from .model import Limits
from . import __version__
from .project import Project
from .validation import validate


def service_check(operation, fonts=None):
    """Restrictions for remote/agent callers, applied after normalization so aliases such as
    ``font_family`` cannot bypass them. Service clients import images explicitly; they cannot
    read arbitrary server files, enable plugins, or resolve linked assets or font files.
    ``fonts`` (the names a document allows, see ``service_fonts``) lets operations on a document
    name a registered font or role; without it any ``font`` is refused."""
    from .render import EFFECTS
    from .operations import OPERATION_TYPES

    kind = operation.get("type")
    blocked = ("linked",) if fonts is not None else ("linked", "font", "display_font")
    require(
        not any(k in operation for k in blocked)
        and ("path" not in operation or (kind in ("text-layout", "shape") or (kind == "select" and operation.get("shape") == "path"))),
        "Filesystem fields (path, linked, font files) are unavailable through services; "
        "import images with vixl_import_image and reference the returned asset"
        + ("" if fonts is not None else "; fonts are named only in operations applied to a document, by registered name or role"),
        "forbidden",
        field=next((k for k in ("path", *blocked) if k in operation), None),
    )
    if fonts is not None:
        from .service_fonts import check_fonts

        check_fonts(operation, fonts)
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
    ``document`` path and otherwise uses the active document. The active document belongs to
    one MCP client session (see ``calls.py``), so clients sharing a server cannot redirect each
    other's edits; with ``require_document`` there is no active document and ``document`` is
    mandatory."""

    MAX_OPEN = 8

    def __init__(self, path=None, limits=None, *, workspace=None, require_document=False):
        self.limits = limits or Limits()
        self.workspace = Path(workspace or (Path(path).resolve().parent if path else Path.cwd())).resolve()
        require(self.workspace.is_dir(), "Workspace must be an existing directory")
        self.require_document = require_document
        self._path = None  # The server-wide default: the document it started with, or set outside MCP.
        self._client_paths = WeakKeyDictionary()
        self.documents = {}
        self._mutex = RLock()
        if path:
            self.open(path if workspace else Path(path).resolve())

    @property
    def path(self):
        client = current_client()
        return self._path if client is None else self._client_paths.get(client, self._path)

    @path.setter
    def path(self, value):
        client = current_client()
        if client is None:
            self._path = value
        else:
            self._client_paths[client] = value

    def active(self):
        """The calling client's active document, unless the server insists on ``document=``."""
        require(
            not self.require_document,
            "document= is required on this server (started with --require-document); pass the .vixl path",
            "document_required",
            field="document",
        )
        require(self.path is not None, "Create or open a document first", "no_project")
        return self.path

    def resolve(self, path):
        resolved = (self.workspace / path).resolve()
        require(resolved.is_relative_to(self.workspace), "Path is outside the workspace", "forbidden", field="path")
        return resolved

    def relative(self, path):
        # Reported paths use "/" on every platform (Windows accepts it when a client passes one back).
        return Path(path).relative_to(self.workspace).as_posix()

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
        note_document(path)

    def open(self, path, upgrade=None):
        """Open a document. A document saved before the 0.21 rendering changes reports the affected
        layers under ``upgrade``; ``upgrade="accept"`` records the new rendering as accepted and
        ``"pin-fills"`` also restores the white fill of open shapes (see upgrade.py)."""
        from .upgrade import report, upgrade as run_upgrade

        require(upgrade in (None, "accept", "pin-fills"), "upgrade must be 'accept' or 'pin-fills'",
                field="upgrade")
        with self._mutex:
            resolved = self.resolve(path)
            require(resolved.is_file(), f"Document does not exist: {path}", "not_found", field="path")
            with file_lock(str(resolved)):
                project = Project.load(resolved, limits=self.limits)
                done = None
                if upgrade and project.upgraded_from:
                    done = run_upgrade(project, pin_fills=upgrade == "pin-fills")
                    project.save()
                self._remember(resolved, project, self.stamp(resolved))
            summary = self.summary(project)
            if done:
                summary["upgrade"] = done
            elif project.upgraded_from and (notice := report(project.state, project.upgraded_from)):
                summary["upgrade"] = notice
            return summary

    def create(self, path, width=None, height=None, background=None, *, size=None, purpose=None, dpi=None,
               orientation=None, bleed=False, seed=None, variety=None, workspace_fonts=True):
        """Create and save a document through ``creation.create``; the summary adds ``creation`` (size,
        background and fonts chosen, and why) and ``workspace_fonts`` (the ``brand.json`` fonts embedded)."""
        with self._mutex:
            resolved = self.resolve(path)
            require(resolved.suffix.lower() == ".vixl", "Document path must end in .vixl", field="path")
            from .creation import resolve_size

            resolve_size(width, height, size, purpose)  # a bad request must not leave directories behind
            self.make_parent(resolved)
            with file_lock(str(resolved)):
                require(not resolved.exists(), "Destination already exists; open it instead", field="path")
                report = {}
                project = self.new_project(width, height, background, size=size, purpose=purpose, dpi=dpi,
                                           orientation=orientation, bleed=bleed, seed=seed, variety=variety,
                                           workspace_fonts=workspace_fonts, report=report)
                project.save(resolved)
                self._remember(resolved, project, self.stamp(resolved))
            return {**self.summary(project), **report}

    def new_project(self, width=None, height=None, background=None, *, size=None, purpose=None, dpi=None,
                    orientation=None, bleed=False, seed=None, variety=None, workspace_fonts=False, report=None):
        """An unsaved document as ``create`` makes it (``creation.create``): from a named size, width/height,
        a purpose or nothing (1080×1080), with the workspace's design defaults. ``report`` receives
        ``creation`` and ``workspace_fonts``."""
        from .creation import create

        return create(width, height, background, size=size, purpose=purpose, dpi=dpi, orientation=orientation,
                      bleed=bleed, seed=seed, variety=variety, workspace=self.workspace, remember=True,
                      workspace_fonts=workspace_fonts, limits=self.limits, report=report)

    def make_parent(self, path):
        """Create the missing directories above ``path`` (always inside the workspace: ``resolve``
        has already rejected anything else, symlinks included)."""
        require(
            not path.parent.exists() or path.parent.is_dir(),
            f"{self.relative(path.parent)} exists and is not a directory", field="path",
        )
        path.parent.mkdir(parents=True, exist_ok=True)

    def close(self, document=None):
        with self._mutex:
            path = self.resolve(document) if document else self.active()
            require(path in self.documents, "Document is not open", "no_project", field="document")
            note_document(path)
            del self.documents[path]
            if self.path == path:
                # Another client's document must not become this client's active one.
                self.path = next(reversed(self.documents), None) if current_client() is None else None
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
            **({"design_defaults": project.state["design_defaults"]} if "design_defaults" in project.state else {}),
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
                path = self.active()
            note_document(path)
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

    def load_operations(self, path):
        """Operations from a workspace JSON file (array, or an object with ``operations``) or a JSONL file
        (one operation per line; a bad line is reported with its line number)."""
        import json

        from .assets import read_bounded

        resolved = self.resolve(path)
        require(resolved.is_file(), f"No operations file at {path!r}", "not_found", field="operations_path")
        text = read_bounded(resolved, 8 * 1024 * 1024).decode("utf-8-sig", "replace")
        if resolved.suffix.lower() in (".jsonl", ".ndjson"):
            operations = []
            for number, line in enumerate(text.splitlines(), 1):
                if not line.strip():
                    continue
                try:
                    item = json.loads(line)
                except ValueError as exc:
                    raise VixlError("invalid_json", f"{path} line {number}: {exc}", field="operations_path") from exc
                require(isinstance(item, dict), f"{path} line {number}: expected one operation object per line",
                        "invalid_json", field="operations_path")
                operations.append(item)
            return operations
        try:
            loaded = json.loads(text)
        except ValueError as exc:
            raise VixlError("invalid_json", f"{path}: {exc}", field="operations_path") from exc
        return loaded

    def apply(self, operations, dry_run=False, detail="compact", document=None, operations_path=None):
        return self.apply_reviewed(operations, dry_run, detail, document, operations_path)[0]

    def apply_reviewed(self, operations, dry_run=False, detail="compact", document=None, operations_path=None,
                       check=None, preview=None, budget=None, suites=None):
        """apply, plus the optional ``check`` findings, attached ``suites`` and ``preview`` PNG of the result
        (checks.apply_reviewed):
        returns ``(result, PNG bytes or None)``."""
        from .checks import apply_reviewed

        if operations_path is not None:
            require(operations is None, "Pass operations or operations_path, not both", field="operations_path")
            operations = self.load_operations(operations_path)
        if isinstance(operations, dict):
            single = "type" in operations or "operation" in operations
            operations = [operations] if single else operations.get("operations", [operations])
        require(isinstance(operations, list), "Expected operation array")
        with self.project(write=not dry_run, document=document) as p:
            from .service_fonts import checker

            return apply_reviewed(p, operations, dry_run=dry_run, detail=detail, check=check, preview=preview,
                                  validate=checker(p, service_check), budget=budget, suites=suites)

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

    def validate(self, profile=None, rules=None, document=None, **options):
        with self.project(document=document) as p:
            return validate(p, profile, rules, **options)

    def history(self, action="list", ref=None, count=1, document=None, *, dry_run=False, fonts=True):
        """Navigate history. ``compact`` squashes it to the current state and drops unused embedded
        files (``dry_run`` reports what it would drop; ``fonts`` False keeps unused registered fonts)."""
        require(
            action
            in ("list", "undo", "redo", "branch", "checkpoint", "checkout", "begin", "commit", "rollback", "compact"),
            "Unknown history action",
            field="action",
        )
        with self.project(write=action != "list" and not (action == "compact" and dry_run), document=document) as p:
            compacted = p.compact(fonts=fonts, dry_run=dry_run) if action == "compact" else None
            steps = None
            if action in ("undo", "redo"):
                steps = getattr(p, action)(count)
            elif action in ("branch", "checkpoint", "checkout"):
                require(ref, f"History {action} requires ref", field="ref")
                getattr(p, action)(ref)
            elif action in ("begin", "commit", "rollback"):
                getattr(p, action)()
            return {
                **({action: steps} if steps is not None else {}),
                **({"notes": [f"{action} {count}: only {steps} step(s) were available"]}
                   if steps is not None and steps < count else {}),
                "head": p.head,
                "branch": p.current_branch,
                "branches": p.branches,
                "checkpoints": p.checkpoints,
                "nodes": [{k: v for k, v in node.items() if k not in ("state", "delta")} for node in p.nodes.values()],
                **({"compact": compacted} if compacted else {}),
            }

    def import_image(self, data=None, name="image", document=None, *, url=None, source=None, credit=None,
                     license=None):
        """Embed image bytes, or download ``url`` first (outside the document lock)."""
        from .image_import import attribution, fetch_image, import_image

        require((data is None) != (url is None), "Provide exactly one of image bytes or url", field="url")
        attribution(credit, license)
        if url is not None:
            data, source = fetch_image(url, self.limits)
        with self.project(write=True, document=document) as p:
            return import_image(p, data, name, source=source, credit=credit, license=license)

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
            return JSONResponse({"error": "unauthorized"}, status_code=401, headers={"WWW-Authenticate": "Bearer"})
        origin = request.headers.get("origin")
        if origin and origin != str(request.base_url).rstrip("/"):
            return JSONResponse({"error": "cross_origin_forbidden"}, status_code=403)
        maximum = session.limits.max_asset_bytes if request.url.path in ("/assets", "/fonts", "/import") else 1024 * 1024
        if request.url.path == "/fonts":
            maximum = min(maximum, 16 * 1024 * 1024)
        too_large = VixlError("resource_limit", f"The request body is larger than {maximum:,} bytes; send a smaller body "
                              "(downsample images, split operations into several batches)",
                              limit=maximum).as_dict()
        declared = request.headers.get("content-length", "")
        if declared.isdigit() and int(declared) > maximum:
            # Refuse before reading: the body is never buffered.
            return JSONResponse(too_large, status_code=413, headers={"Connection": "close"})
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > maximum:
                return JSONResponse(too_large, status_code=413, headers={"Connection": "close"})
        request._body = bytes(body)
        return await call_next(request)

    @app.exception_handler(VixlError)
    async def vixl_error(request: Request, exc: VixlError):
        return JSONResponse(exc.as_dict(), status_code=403 if exc.code == "forbidden" else 400)

    @app.exception_handler(MemoryError)
    async def out_of_memory(request: Request, exc: MemoryError):
        from .errors import friendly

        return JSONResponse(friendly(exc).as_dict(), status_code=400)

    @app.get("/view")
    def viewer():
        from fastapi.responses import HTMLResponse
        import base64

        data = Path(__file__).parent / "data"
        html = (data / "view.html").read_text(encoding="utf-8")
        for placeholder, filename in (("__VIXL_FAVICON__", "favicon-dark.svg"),
                                      ("__VIXL_LOGO__", "horizontal-reverse.svg")):
            encoded = base64.b64encode((data / "brand" / filename).read_bytes()).decode("ascii")
            html = html.replace(placeholder, "data:image/svg+xml;base64," + encoded)
        return HTMLResponse(html, headers={"Cache-Control": "no-store", "X-Frame-Options": "DENY"})

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
        require(action in {"check", "act", "plan", "film-plan", "lyric-video-plan", "organic-catalog", "form-fill", "drawing-report", "links"} | REST_ACTIONS,
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
            "alpha",
            "presenter",
        }
        known_fields(body, allowed, "export")
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
            "PSD": "image/vnd.adobe.photoshop",
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

    @app.get("/guide")
    def guide(brief: str | None = None):
        from .briefs import guide as make_guide

        return make_guide(brief)

    @app.get("/styles")
    def style_catalog(query: str | None = None, name: str | None = None):
        from . import styles

        return styles.describe(name) if name else styles.listing(query)

    @app.get("/looks")
    def look_catalog():
        from .looks import catalog

        return {"looks": catalog()}

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
        from .typefaces import pair_fonts, pair_workspace

        if body.get("scope") == "workspace":
            return pair_workspace(session.workspace, body.get("pairing", "random"), seed=body.get("seed"), mood=body.get("mood"), best_for=body.get("best_for"))
        require(body.get("scope", "document") == "document", "scope must be document or workspace", field="scope")
        with session.project(write=True) as project:
            return pair_fonts(project, body.get("pairing", "random"), seed=body.get("seed"), mood=body.get("mood"), best_for=body.get("best_for"))

    @app.post("/typefaces/install")
    def typeface_install(body: dict):
        from .typefaces import install_font, install_workspace

        require(isinstance(body.get("family"), str), "family is required", field="family")
        if body.get("scope") == "workspace":
            return install_workspace(session.workspace, body["family"], body.get("weight", 400), body.get("italic", False), body.get("name"), body.get("role"))
        require(body.get("scope", "document") == "document", "scope must be document or workspace", field="scope")
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

        allowed = {"format", "fps", "scale", "start", "end", "background", "columns", "quality", "colors", "dither", "max_bytes", "poster", "sample_rate", "target_bytes", "preset"}
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
        import base64

        result, image = session.apply_reviewed(
            body.get("operations"), bool(body.get("dry_run", False)), body.get("detail", "compact"),
            operations_path=body.get("operations_path"), check=body.get("check"), preview=body.get("preview"),
            suites=body.get("suites"),
        )
        if image is not None:
            result["preview_base64"] = base64.b64encode(image).decode()
        return result

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
                   "guides", "page", "values", "show_fields", "isolate"}
        known_fields(options, allowed, "preview")
        return Response(preview(session, **options), media_type="image/png")

    @app.post("/compose")
    def compose_piece(body: dict):
        """vixl_compose as a dry run: this server serves one fixed document, so it builds, checks and previews the
        piece without saving it (use MCP or the CLI to write it)."""
        import base64
        from .compose import compose

        options = fixed(body)
        require(not options.get("exports") and options.get("dry_run", True) is True
                and not {"path", "operations_path"} & set(options),
                "REST compose is a dry run (no path or exports); use vixl_compose or vixl compose to save", "forbidden")
        result, image = compose(session, **{**options, "dry_run": True})
        if image is not None:
            result["preview_base64"] = base64.b64encode(image).decode()
        return result

    @app.post("/compare")
    def compare_revisions(body: dict):
        import base64
        import io
        from .checks import compare

        options = fixed(body)
        known_fields(options, {"before", "after", "mode", "isolate"}, "compare")
        with session.project() as p:
            image, summary = compare(
                p,
                options.get("before", "previous"),
                options.get("after", "head"),
                mode=options.get("mode", "side-by-side"),
                isolate=options.get("isolate"),
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
        import tempfile

        from .animation import VIDEO, animation_bytes, export_animation

        allowed = {"format", "scale", "sampling", "colors", "columns", "animation", "quality", "dither", "max_bytes"}
        require(set(body) <= allowed, f"Animation export accepts {sorted(allowed)}", field="body")
        if isinstance(body.get("scale"), float) and body["scale"].is_integer():
            body["scale"] = int(body["scale"])
        fmt = body.get("format", "gif")
        media = {"gif": "image/gif", "apng": "image/apng", "webp": "image/webp", "mp4": "video/mp4", "webm": "video/webm"}
        if fmt in VIDEO:
            with tempfile.TemporaryDirectory(prefix="vixl-animation-") as staging:
                path = Path(staging) / ("animation." + fmt)
                with session.project() as p:
                    export_animation(p, path, **body)
                return Response(path.read_bytes(), media_type=media[fmt])
        with session.project() as p:
            data, _ = animation_bytes(p, **body)
        return Response(data, media_type=media.get(fmt, "image/png"))

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
        return session.history(action, body.get("ref"), body.get("count", 1), dry_run=bool(body.get("dry_run", False)),
                               fonts=bool(body.get("fonts", True)))

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
    async def assets(request: Request, name: str = "image", url: str | None = None, credit: str | None = None,
                     license: str | None = None):
        from functools import partial

        from starlette.concurrency import run_in_threadpool

        body = await request.body()
        require(not (url and body), "Send image bytes or a url query parameter, not both", field="url")
        return await run_in_threadpool(partial(session.import_image, None if url else body, name, url=url,
                                               credit=credit, license=license))

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


def require_document_default():
    """``VIXL_REQUIRE_DOCUMENT=1`` makes every document call name its document (see Session)."""
    import os

    return os.environ.get("VIXL_REQUIRE_DOCUMENT", "").strip().lower() in ("1", "true", "yes", "on")


def mcp_server(path=None, limits=None, *, workspace=None, schema="full", planner=False, tools="all",
               require_document=None):
    try:
        from .mcp_tools import build_server
        import mcp.server.fastmcp  # noqa: F401
    except ImportError as exc:
        raise VixlError("missing_dependency", "Install vixl-engine[mcp]") from exc

    if require_document is None:
        require_document = require_document_default()
    session = Session(path, limits, workspace=workspace, require_document=require_document)
    return build_server(session, schema=schema, planner=planner, tools=tools)


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
            return JSONResponse({"error": "unauthorized"}, status_code=401, headers={"WWW-Authenticate": "Bearer"})
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



def known_fields(body, allowed, route):
    """Refuse a REST body with fields the route does not read, naming them and the accepted ones."""
    import difflib

    unknown = sorted(set(body) - set(allowed))
    if unknown:
        close = {key: difflib.get_close_matches(key, sorted(allowed), 1, 0.6) for key in unknown}
        hints = [f"{match[0]!r} instead of {key!r}" for key, match in close.items() if match]
        raise VixlError("invalid_operation", f"Unknown {route} field(s) {', '.join(map(repr, unknown))}; accepted: "
                        f"{', '.join(sorted(allowed))}" + (f". Did you mean {', '.join(hints)}?" if hints else ""),
                        field=unknown[0], allowed=sorted(allowed))
