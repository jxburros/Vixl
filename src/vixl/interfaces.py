"""Cached project sessions, fixed-project REST and workspace-scoped MCP services."""

from collections import OrderedDict
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
        and ("path" not in operation or (kind in ("text-layout", "shape", "paint") or (kind == "select" and operation.get("shape") == "path"))),
        "Filesystem fields (path, linked, font files) are unavailable through services; "
        "import images with import-image and reference the returned asset"
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


def offset_indexes(exc, indexes, start=0):
    """Rewrite an error's operation indexes (local to one segment of a batch) to their place in the whole batch."""
    def place(value):
        return indexes[value] if isinstance(value, int) and 0 <= value < len(indexes) else value

    if "operation_index" in exc.details:
        exc.details["operation_index"] = place(exc.details["operation_index"])
    for item in exc.details.get("errors", []) or []:
        if isinstance(item, dict) and "operation_index" in item:
            item["operation_index"] = place(item["operation_index"])
    return exc


class _Document:
    __slots__ = ("path", "project", "stamp")

    def __init__(self, path, project, stamp):
        self.path, self.project, self.stamp = path, project, stamp


def broad_workspace(folder):
    """Whether ``folder`` is the home folder or a filesystem root: too much to hand an agent by accident."""
    folder = Path(folder).resolve()
    try:
        home = Path.home().resolve()
    except (RuntimeError, OSError):
        home = None
    return folder == home or folder == Path(folder.anchor)


def refuse_broad_workspace(folder):
    """Refuse the home folder or a filesystem root as a workspace nobody chose (the current directory)."""
    require(not broad_workspace(folder), f"Refusing {folder} as the workspace: it is the home folder or a "
            "filesystem root, and no workspace was given. Pass --workspace DIR (Session(workspace=DIR)) or start "
            "in a project folder", "unsafe_workspace", field="workspace")


class Session:
    """Workspace-scoped documents kept loaded between calls.

    Several documents can be open at once (bounded LRU); every method takes an optional
    ``document`` path and otherwise uses the active document. The active document belongs to
    one MCP client session (see ``calls.py``), so clients sharing a server cannot redirect each
    other's edits; with ``require_document`` there is no active document and ``document`` is
    mandatory.

    An MCP client session is a connection, not an agent: subagents of one host share a stdio
    connection, and the protocol carries nothing that tells them apart. So an MCP call without
    ``document`` is refused (``ambiguous_document``) once its client has created, opened or
    addressed more than one document that is still open, or when it never chose one and several
    are open; a call can then only act on a document its caller named."""

    MAX_OPEN = 8

    def __init__(self, path=None, limits=None, *, workspace=None, require_document=False):
        self.limits = limits or Limits()
        self.workspace = Path(workspace or (Path(path).resolve().parent if path else Path.cwd())).resolve()
        require(self.workspace.is_dir(), "Workspace must be an existing directory")
        if workspace is None and path is None:
            refuse_broad_workspace(self.workspace)
        self.require_document = require_document
        self._path = None  # The server-wide default: the document it started with, or set outside MCP.
        self._client_paths = WeakKeyDictionary()
        self._client_seen = WeakKeyDictionary()  # Client -> documents it created, opened or named, by recency.
        self.documents = {}
        # Each document's render caches, kept when the document is reloaded (it changed on disk, a call
        # failed, or it was closed and opened again): keys are content-addressed, so a reload re-renders
        # only what changed.
        self._render_caches = OrderedDict()
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
        client = current_client()
        if client is not None:
            # ``documents`` is a cache (a failed call or the LRU drops entries), so what a connection has touched
            # is tracked apart from it and forgotten only when the document is closed.
            own = self._client_paths.get(client)
            mine = [path for path in self._client_seen.get(client, ()) if path.exists()]
            if [path for path in mine if path != own]:
                self._ambiguous(own, mine)
            if client not in self._client_paths and len(everyone := self._open_paths()) > 1:
                self._ambiguous(None, everyone)
        require(self.path is not None, "Create or open a document first", "no_project")
        return self.path

    def _open_paths(self):
        paths = dict.fromkeys(self.documents)
        for seen in self._client_seen.values():
            paths.update(seen)
        if self._path is not None:
            paths[self._path] = True
        return [path for path in paths if path.exists()]

    def _ambiguous(self, own, paths):
        names = [self.relative(path) for path in reversed(paths)]
        active = f" This connection last created or opened {self.relative(own)}." if own is not None else ""
        raise VixlError(
            "ambiguous_document",
            f"{len(names)} documents are open ({', '.join(names)}) and this call did not name one. Clients sharing "
            f"one connection (subagents, for example) share its active document, so a call without document= "
            f"could act on another caller's file.{active} Pass document= with the .vixl path you mean.",
            field="document",
            documents=names,
            suggestions=[f"document={name!r}" for name in names],
        )

    def _seen(self, path):
        client = current_client()
        if client is not None:
            seen = self._client_seen.setdefault(client, {})
            seen.pop(path, None)
            seen[path] = True
            while len(seen) > 2 * self.MAX_OPEN:  # Two are enough to refuse; keep the most recent.
                del seen[next(iter(seen))]

    def resolve(self, path):
        require("\0" not in str(path), "Path contains a NUL byte", "invalid_input", field="path")
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

    def load(self, path):
        """``Project.load`` that carries the document's previous render caches over."""
        project = Project.load(path, limits=self.limits)
        kept = self._render_caches.pop(path, None)
        if kept is not None:
            project._cache, project._paint_cache = kept
        self._render_caches[path] = (project._cache, project._paint_cache)
        while len(self._render_caches) > 2 * self.MAX_OPEN:
            self._render_caches.popitem(last=False)
        return project

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
        self._seen(path)
        note_document(path)

    def open(self, path):
        """Open a document and return its summary."""
        with self._mutex:
            resolved = self.resolve(path)
            require(resolved.is_file(), f"Document does not exist: {path}", "not_found", field="path")
            with file_lock(str(resolved)):
                project = self.load(resolved)
                self._remember(resolved, project, self.stamp(resolved))
            summary = self.summary(project)
            return summary

    def create(self, path, width=None, height=None, background=None, *, size=None, purpose=None, dpi=None,
               orientation=None, bleed=False, seed=None, variety=None, workspace_fonts=True, house_style=None):
        """Create and save a document through ``creation.create``; the summary adds ``creation`` (size,
        background and fonts chosen, and why) and ``workspace_fonts`` (the ``brand.json`` fonts embedded)."""
        with self._mutex:
            resolved = self.resolve(path)
            require(resolved.suffix.lower() == ".vixl", "Document path must end in .vixl", field="path")
            from .creation import resolve_size

            resolve_size(width, height, size, purpose)  # a bad request must not leave directories behind
            from .variety import house_style_off

            house_style_off(house_style, self.workspace)
            self.make_parent(resolved)
            with file_lock(str(resolved)):
                require(not resolved.exists(), "Destination already exists; open it instead", field="path")
                report = {}
                project = self.new_project(width, height, background, size=size, purpose=purpose, dpi=dpi,
                                           orientation=orientation, bleed=bleed, seed=seed, variety=variety,
                                           workspace_fonts=workspace_fonts, report=report, house_style=house_style)
                project.save(resolved)
                self._remember(resolved, project, self.stamp(resolved))
            return {**self.summary(project), **report}

    def new_project(self, width=None, height=None, background=None, *, size=None, purpose=None, dpi=None,
                    orientation=None, bleed=False, seed=None, variety=None, workspace_fonts=False, report=None,
                    house_style=None):
        """An unsaved document as ``create`` makes it (``creation.create``): from a named size, width/height,
        a purpose or nothing (1080×1080), with the workspace's design defaults. ``report`` receives
        ``creation`` and ``workspace_fonts``."""
        from .creation import create

        return create(width, height, background, size=size, purpose=purpose, dpi=dpi, orientation=orientation,
                      bleed=bleed, seed=seed, variety=variety, workspace=self.workspace, remember=True,
                      workspace_fonts=workspace_fonts, limits=self.limits, report=report, house_style=house_style)

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
            require(document is not None or current_client() is not None or len(self.documents) <= 1,
                    "Several documents are open; pass document explicitly to close one", "ambiguous_document",
                    field="document", documents=[self.relative(path) for path in self.documents])
            path = self.resolve(document) if document else self.active()
            client = current_client()
            mine = self._client_seen.get(client, {}) if client is not None else {}
            # A document this connection touched counts as open even when the cache has dropped it.
            require(path in self.documents or path in mine, "Document is not open", "no_project", field="document")
            note_document(path)
            self.documents.pop(path, None)
            for seen in self._client_seen.values():
                seen.pop(path, None)
            if self.path == path:
                # Another client's document must not become this client's active one.
                pool = self.documents if client is None else [p for p in mine if p.exists()]
                self.path = next(reversed(pool), None)
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
                self._seen(path)
            else:
                path = self.active()
            note_document(path)
            with file_lock(str(path)):
                entry = self.documents.get(path)
                try:
                    stamp = self.stamp(path)
                    if entry is None or entry.project is None or stamp != entry.stamp:
                        entry = _Document(path, self.load(path), stamp)
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
                       check=None, preview=None, budget=None, suites=None, repair=None):
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
        from .steps import is_step

        if any(is_step(op) for op in operations):
            return self.apply_steps(operations, dry_run, detail, document, check=check, preview=preview,
                                    budget=budget, suites=suites, repair=repair)
        with self.project(write=not dry_run, document=document) as p:
            from .service_fonts import checker

            return apply_reviewed(p, operations, dry_run=dry_run, detail=detail, check=check, preview=preview,
                                  validate=checker(p, service_check), budget=budget, suites=suites,
                                  repair=repair)

    def apply_steps(self, operations, dry_run, detail, document, **review):
        """A batch that mixes operations with session steps (steps.py): every item applies, in order, to one
        candidate copy that replaces the document only when all succeeded. Workspace-scoped font steps run after."""
        from .steps import is_step, workspace_scoped

        if any(not (is_step(op) and workspace_scoped(op)) for op in operations):
            with self.project(write=not dry_run, document=document) as p:
                return self.apply_steps_to(p, operations, dry_run, detail, **review)
        return self.apply_steps_to(None, operations, dry_run, detail, **review)

    def apply_steps_to(self, p, operations, dry_run, detail, **review):
        """apply_steps on a document the caller has loaded (``p``; None when every item is a workspace step):
        the CLI runs ``vixl apply`` batches with steps through it and saves ``p`` itself."""
        from .checks import apply_reviewed
        from .service_fonts import checker
        from .steps import is_step, run, workspace_scoped

        later = [(index, op) for index, op in enumerate(operations) if is_step(op) and workspace_scoped(op)]
        items = [(index, op) for index, op in enumerate(operations) if not (is_step(op) and workspace_scoped(op))]
        steps, result, image = [], {"success": True}, None
        if items:
            candidate = p.clone()
            validate = checker(candidate, service_check)
            segment = []

            def flush(final=False):
                nonlocal result, image
                if not segment and not final:
                    return
                start = segment[0][0] if segment else 0
                ops = [op for _, op in segment]
                try:
                    if final:
                        result, image = apply_reviewed(candidate, ops, detail=detail, validate=validate, **review)
                    else:
                        candidate.apply(ops, detail=detail, validator=validate)
                except VixlError as exc:
                    offset_indexes(exc, [index for index, _ in segment], start)
                    raise
                segment.clear()

            for index, op in items:
                if not is_step(op):
                    segment.append((index, op))
                    continue
                flush()
                kind, value, expanded = run(self, candidate, op, index)
                if expanded is not None:
                    segment.extend((index, item) for item in expanded)
                steps.append({"index": index, "type": kind, **({"result": value} if value is not None else {})})
            flush(final=True)
            result["dry_run"] = dry_run
            if not dry_run:
                p.__dict__.update(candidate.__dict__)
        elif any(review.get(key) for key in ("check", "preview", "suites", "repair")):
            raise VixlError("invalid_operation", "check, preview, suites and repair need document operations; this "
                            "batch only changes workspace defaults", field="check")
        for index, op in later:
            kind, value, _ = run(self, None, op, index) if not dry_run else (op["type"], {"dry_run": True}, None)
            steps.append({"index": index, "type": kind, "result": value})
        result["steps"] = steps
        return result, image

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
        # A form sample is read from disk: confine it to the workspace for every service (MCP and REST).
        sample = options.get("sample")
        if sample not in (None, "worst"):
            require(isinstance(sample, str), "sample must be 'worst' or a workspace CSV path", field="sample")
            options["sample"] = str(self.resolve(sample))
        # repair writes (one undoable batch); a plain check only reads.
        with self.project(write=bool(options.get("repair")), document=document) as p:
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
        from .plugins.ai.ai import ai_command

        require(command in ("ask", "generate", "ai", "select", "detect", "ocr"), "Unsupported AI command")
        require(isinstance(args, list) and all(isinstance(x, str) for x in args), "AI args must be strings")
        require(not any(x in ("-h", "--help") for x in args), "Help flags are not service commands")
        with self.project(document=document) as p:
            result, changed = ai_command(p, command, args)
            if changed:
                p.save()
            return result


async def profiled_response(response, run):
    """A REST response with ``run``'s render profile: in the ``X-Vixl-Profile`` header (compact, the slowest
    layers first) and, for a JSON object body, as ``render_profile`` in the body too."""
    import json

    from fastapi.responses import Response

    report = run.report()
    headers = {k: v for k, v in response.headers.items() if k.lower() not in ("content-length", "content-type")}
    summary = {**report, "layers": report["layers"][:5], "renders": report["renders"][-3:]}
    headers["x-vixl-profile"] = json.dumps(summary, separators=(",", ":"))[:6000]
    body = b"".join([chunk async for chunk in response.body_iterator])
    media = response.headers.get("content-type", "")
    if media.startswith("application/json"):
        try:
            value = json.loads(body)
        except ValueError:
            value = None
        if isinstance(value, dict):
            value["render_profile"] = report
            body = json.dumps(value).encode()
    return Response(body, status_code=response.status_code, headers=headers, media_type=media or None)


def create_app(path, *, token=None, limits=None, call_limits=None):
    """The REST app for one document. ``call_limits`` (default: from the environment, see ``call_limits.py``)
    bounds each call: a timeout after which a call answers 202 with a job, an export page and megapixel cap
    and the heavy calls running at once in the workspace."""
    try:
        from fastapi import FastAPI, Request
        from fastapi.responses import JSONResponse, Response
        from starlette.middleware.trustedhost import TrustedHostMiddleware
    except ImportError as exc:
        raise VixlError("missing_dependency", "Install vixl-engine[server]") from exc
    import asyncio
    from concurrent.futures import ThreadPoolExecutor
    import contextvars
    import functools

    from .call_limits import GATE, CallLimits, RestJobs, check_export, detached
    from .untrusted import mark

    require_token(token)
    failures = Failures()
    CHECK_FIELDS, MEASURE_FIELDS, SPACING_FIELDS = route_fields()
    call_limits = call_limits if call_limits is not None else CallLimits.configure()
    session = Session(path, call_limits.apply_to(limits or Limits()))
    session.call_limits = call_limits
    jobs = RestJobs()
    workers = ThreadPoolExecutor(max_workers=16, thread_name_prefix="vixl-rest")

    def limited(fn):
        """A heavy route: counted against max_concurrent, and detached into a job after the timeout."""
        @functools.wraps(fn)
        async def wrapper(*args, **kwargs):
            key = GATE.acquire(session.workspace, call_limits.max_concurrent)
            try:
                # Run in a copy of the request's context, so a VIXL_PROFILE render profile sees the work.
                future = workers.submit(contextvars.copy_context().run, fn, *args, **kwargs)
            except BaseException:
                GATE.release(key)
                raise
            future.add_done_callback(lambda _: GATE.release(key))
            waiter = asyncio.wrap_future(future)
            waiter.add_done_callback(lambda f: f.cancelled() or f.exception())  # Retrieved even if nobody waits.
            if call_limits.timeout is None:
                return await waiter
            try:
                return await asyncio.wait_for(asyncio.shield(waiter), call_limits.timeout)
            except asyncio.TimeoutError:
                ident = jobs.add(fn.__name__, future)
                return JSONResponse(detached(ident, fn.__name__, call_limits.timeout), status_code=202,
                                    headers={"Location": f"/jobs/{ident}", "Retry-After": "3"})

        return wrapper
    app = FastAPI(title="Vixl Engine", version=__version__)
    if not token:
        app.add_middleware(
            TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1", "[::1]", "testserver"]
        )

    @app.middleware("http")
    async def guard(request: Request, call_next):
        if request.url.path != "/view" and token:  # /view is a static shell; its data calls carry the token.
            refused = authorize(request, token, JSONResponse, failures)
            if refused is not None:
                return refused
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
        from . import profiling

        if not profiling.enabled():
            return await call_next(request)
        with profiling.profile() as run:
            response = await call_next(request)
        return await profiled_response(response, run)

    @app.exception_handler(VixlError)
    async def vixl_error(request: Request, exc: VixlError):
        status = 403 if exc.code == "forbidden" else 400
        if exc.code == "limit_exceeded":
            status = 429 if exc.details.get("limit") == "max_concurrent" else 413
        return JSONResponse(exc.as_dict(), status_code=status,
                            headers={"Retry-After": "3"} if status == 429 else None)

    @app.get("/limits")
    def server_limits():
        from .fetch import policy

        return {**call_limits.describe(), "max_pixels": session.limits.max_pixels,
                "max_dimension": session.limits.max_dimension, "network": policy()}

    @app.get("/jobs")
    def job_list():
        return {"jobs": [jobs.summary(job) for job in jobs.recent()[:20]], "limits": call_limits.describe()}

    async def finished(ident, wait):
        job = jobs.get(ident)
        if wait and not job["future"].done():
            try:
                await asyncio.wait_for(asyncio.shield(asyncio.wrap_future(job["future"])), min(float(wait), 50))
            except Exception:  # Timed out, or failed: the summary says which.
                pass
        return job

    @app.get("/jobs/{ident}")
    async def job_status(ident: str, wait: float = 0):
        return jobs.summary(await finished(ident, wait))

    @app.get("/jobs/{ident}/result")
    async def job_result(ident: str, wait: float = 0):
        """What the original call would have answered: its file, JSON or error."""
        job = await finished(ident, wait)
        if not job["future"].done():
            return JSONResponse(jobs.summary(job), status_code=409, headers={"Retry-After": "3"})
        return job["future"].result()  # A failure re-raises and the handlers answer as the call would have.

    @app.exception_handler(MemoryError)
    async def out_of_memory(request: Request, exc: MemoryError):
        from .errors import friendly

        return JSONResponse(friendly(exc).as_dict(), status_code=400)

    @app.exception_handler(OSError)
    async def os_error(request: Request, exc: OSError):
        from .errors import friendly

        error = friendly(exc, relative_to=session.workspace)  # Never the absolute path on the server.
        return JSONResponse(error.as_dict(), status_code=404 if error.code == "not_found" else 400)

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
            return mark({"head": project.head, "layers": project.inspect()["layers"],
                         "history": session.history()["nodes"], **notes(session.path)})

    @app.get("/notes")
    def review_notes():
        from .review import notes
        return mark(notes(session.path))

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
    @limited
    def workflow(action: str, body: dict):
        from .workflows import dispatch
        # REST remains scoped to its active project. Other document/library/job I/O is MCP/CLI only.
        from .interface_capabilities import REST_WORKFLOWS
        require(action in REST_WORKFLOWS,
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
    @limited
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
            "svg_document",
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
            "TTF": "font/ttf",
            "OTF": "font/otf",
            "WOFF": "font/woff",
            "WOFF2": "font/woff2",
        }
        require(fmt in media, "Unsupported export format")
        body = dict(body)
        if "icc_profile_base64" in body:
            from .mcp_tools import decode_upload

            body["icc_profile"] = decode_upload(body.pop("icc_profile_base64"), 16 * 1024 * 1024)
        with session.project() as project:
            check_export(call_limits, project, fmt, body)
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
    @limited
    def timeline_frame(time: str = "0", max_width: int = 1024, max_height: int = 1024):
        from .mcp_tools import preview

        value = float(time) if time.replace(".", "", 1).isdigit() else time
        return Response(preview(session, None, max_width, max_height, 4_194_304, time=value), media_type="image/png")

    @app.post("/timeline/export")
    @limited
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
        return mark(session.inspect())

    @app.get("/layers")
    def layers():
        # A bare list has no room for the key; the header names the same paths.
        return JSONResponse(session.inspect()["layers"], headers={"X-Vixl-Untrusted": "[].name, [].text"})

    @app.post("/operations")
    @limited
    def operations(body: dict):
        import base64

        result, image = session.apply_reviewed(
            body.get("operations"), bool(body.get("dry_run", False)), body.get("detail", "compact"),
            operations_path=body.get("operations_path"), check=body.get("check"), preview=body.get("preview"),
            suites=body.get("suites"), repair=body.get("repair"),
        )
        from .critique import take_previews

        for entry, png in zip(result.get("check", {}).get("regions", []), take_previews(result)):
            entry["preview_base64"] = base64.b64encode(png).decode()
        if image is not None:
            result["preview_base64"] = base64.b64encode(image).decode()
        return result

    @app.get("/render")
    @limited
    def render():
        return Response(session.render(), media_type="image/png")

    @app.post("/render")
    @limited
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
        known_fields(fixed(body), SPACING_FIELDS, "spacing")
        return session.measure_spacing(**body)

    @app.post("/check")
    @limited
    def check(body: dict):
        known_fields(fixed(body), CHECK_FIELDS, "check")
        return mark(session.check(**body))

    @app.post("/preview")
    @limited
    def preview_image(body: dict):
        from .mcp_tools import preview

        options = fixed(body)
        allowed = {"variables", "max_width", "max_height", "max_bytes", "artboard", "comp", "region", "time", "proof", "simulate",
                   "guides", "page", "values", "show_fields", "isolate", "views", "exploded"}
        known_fields(options, allowed, "preview")
        return Response(preview(session, **options), media_type="image/png")

    @app.post("/compose")
    @limited
    def compose_piece(body: dict):
        """vixl_apply(create=…) as a dry run: this server serves one fixed document, so it builds, checks and previews the
        piece without saving it (use MCP or the CLI to write it)."""
        import base64
        from .compose import compose

        options = fixed(body)
        require(not options.get("exports") and options.get("dry_run", True) is True
                and not {"path", "operations_path"} & set(options),
                "REST compose is a dry run (no path or exports); use vixl_apply(create=…) or vixl compose to save", "forbidden")
        result, image = compose(session, **{**options, "dry_run": True})
        if image is not None:
            result["preview_base64"] = base64.b64encode(image).decode()
        return result

    @app.post("/compare")
    @limited
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
    @limited
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
        known_fields(fixed(body), MEASURE_FIELDS, "measure")
        return session.measure(**body)

    @app.post("/validate")
    @limited
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
    async def import_document(request: Request, format: str, name: str = "import", page: str = "1", dpi: int = 144,
                              svg_mode: str = "editable", node_id: str | None = None,
                              rasterize_unsupported: bool = False):
        from .imports import import_document as execute_import
        from starlette.concurrency import run_in_threadpool
        data = await request.body()
        # A figma import's body is a file URL or key; the server's FIGMA_TOKEN reads the file.
        figma = format.lower() == "figma"
        require(figma or page.isdigit(), "page must be a number", field="page")
        options = {"node_id": node_id, "rasterize_unsupported": rasterize_unsupported} if figma else {}
        def apply_import():
            with session.project(write=True) as project:
                return execute_import(project, data, format, name, int(page) if page.isdigit() else page, dpi,
                                      svg_mode, **options)
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
    @limited
    def ai(command: str, body: dict):
        return session.ai(command, body.get("args", []))

    return app


LOOPBACK = ("127.0.0.1", "localhost", "::1")


def serving_policy(host, token, tls):
    """Refuse a remote bind without a token; warn on stderr when a remote bind sends the token over plain HTTP.
    Returns the uvicorn TLS options."""
    import sys

    require_token(token)
    require(host in LOOPBACK or token, "Non-loopback serving requires VIXL_API_TOKEN", "authentication_required")
    certfile, keyfile = tls or (None, None)
    require(bool(certfile) == bool(keyfile), "Pass both --tls-cert and --tls-key", field="tls")
    if host not in LOOPBACK and not certfile:
        print(f"Serving plain HTTP on {host}; the bearer token is sent in cleartext. Put a TLS reverse proxy in "
              "front, or pass --tls-cert and --tls-key (docs/reference/interfaces.md).", file=sys.stderr)
    return {"ssl_certfile": certfile, "ssl_keyfile": keyfile} if certfile else {}


def serve(path, host="127.0.0.1", port=8765, token=None, limits=None, *, open_browser=False, call_limits=None,
          tls=None):
    """``tls`` is ``(certfile, keyfile)`` to serve HTTPS directly."""
    ssl = serving_policy(host, token, tls)
    try:
        import uvicorn
    except ImportError as exc:
        raise VixlError("missing_dependency", "Install vixl-engine[server]") from exc
    app = create_app(path, token=token, limits=limits, call_limits=call_limits)
    if open_browser:
        import asyncio
        import webbrowser

        scheme = "https" if ssl else "http"

        class ViewerServer(uvicorn.Server):
            async def startup(self, sockets=None):
                await super().startup(sockets=sockets)
                if self.started:
                    local_host = "127.0.0.1" if host == "0.0.0.0" else "::1" if host == "::" else host
                    address = f"[{local_host}]" if ":" in local_host else local_host
                    await asyncio.to_thread(webbrowser.open, f"{scheme}://{address}:{port}/view")

        ViewerServer(uvicorn.Config(app, host=host, port=port, **ssl)).run()
    else:
        uvicorn.run(app, host=host, port=port, **ssl)


def require_document_default():
    """``VIXL_REQUIRE_DOCUMENT=1`` makes every document call name its document (see Session)."""
    import os

    return os.environ.get("VIXL_REQUIRE_DOCUMENT", "").strip().lower() in ("1", "true", "yes", "on")


def mcp_server(path=None, limits=None, *, workspace=None, planner=False, tools="default",
               require_document=None, call_limits=None, allow_screen_capture=None):
    try:
        from .mcp_tools import build_server, check_sdk
        check_sdk()
        import mcp.server.fastmcp  # noqa: F401
    except ImportError as exc:
        raise VixlError("missing_dependency", "The mcp package is missing; reinstall vixl-engine") from exc

    if require_document is None:
        require_document = require_document_default()
    from .call_limits import CallLimits

    call_limits = call_limits if call_limits is not None else CallLimits.configure()
    session = Session(path, call_limits.apply_to(limits or Limits()), workspace=workspace,
                      require_document=require_document)
    session.call_limits = call_limits
    return build_server(session, planner=planner, tools=tools,
                        allow_screen_capture=allow_screen_capture)


def mcp_http_app(server, *, token=None):
    """SDK Streamable HTTP with the REST bearer-token and same-origin policy."""
    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.middleware.trustedhost import TrustedHostMiddleware
    from starlette.responses import JSONResponse
    from mcp.server.transport_security import TransportSecuritySettings

    require_token(token)
    failures = Failures()
    # Our guard handles both public, token-protected hosts and loopback DNS rebinding.
    server.settings.transport_security = TransportSecuritySettings(enable_dns_rebinding_protection=False)
    app = server.streamable_http_app()

    async def guard(request, call_next):
        if token:
            refused = authorize(request, token, JSONResponse, failures)
            if refused is not None:
                return refused
        origin = request.headers.get("origin")
        if origin and origin != str(request.base_url).rstrip("/"):
            return JSONResponse({"error": "cross_origin_forbidden"}, status_code=403)
        return await call_next(request)

    app.add_middleware(BaseHTTPMiddleware, dispatch=guard)
    if not token:
        app.add_middleware(TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1", "[::1]", "testserver"])
    return app


def serve_mcp(server, host="127.0.0.1", port=8766, token=None, *, tls=None):
    ssl = serving_policy(host, token, tls)
    import uvicorn
    uvicorn.run(mcp_http_app(server, token=token), host=host, port=port, **ssl)


MIN_TOKEN_LENGTH = 24


def require_token(token):
    """A configured bearer token must be long enough that guessing it is not practical."""
    if token:
        require(len(token) >= MIN_TOKEN_LENGTH, f"VIXL_API_TOKEN must be at least {MIN_TOKEN_LENGTH} characters",
                "authentication_required", field="token",
                suggestions=['Generate one with: python -c "import secrets; print(secrets.token_urlsafe(32))"'])


def token_matches(header, token):
    """Constant-time bearer check on bytes: a non-ASCII header is a mismatch, not an error."""
    return hmac.compare_digest(header.encode("utf-8", "surrogateescape"), ("Bearer " + token).encode("utf-8"))


class Failures:
    """Failed bearer attempts per client address: after ``LIMIT`` failures within ``WINDOW`` seconds the address
    is answered 429 without comparing, until the oldest failure leaves the window. Each REST or MCP HTTP app
    keeps one."""

    LIMIT, WINDOW, MAX_CLIENTS = 20, 60.0, 1024

    def __init__(self):
        self._seen = OrderedDict()  # Client address -> deque of failure times, least recently failed first.
        self._lock = RLock()

    def _recent(self, client, now):
        times = self._seen.get(client)
        while times and now - times[0] > self.WINDOW:
            times.popleft()
        return times

    def retry_after(self, client, now=None):
        """Whole seconds until ``client`` may try again, or 0."""
        import math
        import time

        now = time.monotonic() if now is None else now
        with self._lock:
            times = self._recent(client, now)
            if not times or len(times) < self.LIMIT:
                return 0
            return max(1, math.ceil(self.WINDOW - (now - times[0])))

    def failed(self, client, now=None):
        from collections import deque
        import time

        now = time.monotonic() if now is None else now
        with self._lock:
            times = self._recent(client, now)
            if times is None:
                times = self._seen[client] = deque(maxlen=self.LIMIT)
            self._seen.move_to_end(client)
            times.append(now)
            while len(self._seen) > self.MAX_CLIENTS:
                self._seen.popitem(last=False)


def authorize(request, token, response, failures):
    """None when the request carries the bearer token; otherwise the 401 (or, once throttled, 429) response."""
    client = request.client.host if request.client else "unknown"
    wait = failures.retry_after(client)
    if wait:
        return response({"error": "too_many_attempts", "message": "Too many failed bearer tokens; retry later"},
                        status_code=429, headers={"Retry-After": str(wait)})
    if token_matches(request.headers.get("authorization", ""), token):
        return None
    failures.failed(client)
    return response({"error": "unauthorized"}, status_code=401, headers={"WWW-Authenticate": "Bearer"})


def route_fields():
    """The body fields REST ``/check``, ``/measure`` and ``/spacing`` accept, from the functions they call."""
    import inspect

    from .checks import check_design
    from .measure import measure
    from .spacing import measure_spacing

    def named(*functions):
        return {name for function in functions for name, parameter in inspect.signature(function).parameters.items()
                if parameter.kind not in (parameter.VAR_KEYWORD, parameter.VAR_POSITIONAL)} - {"self", "project"}

    # ``repairs`` is check_design's internal switch for repair suggestions; vixl_check does not offer it either.
    return named(Project.check, check_design) - {"repairs"}, named(measure), named(measure_spacing)



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
