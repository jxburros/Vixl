"""Build a whole piece in one call: create → fonts → layout → style → look → operations → check → preview →
save → export.

The chain runs on an unsaved document; the .vixl file is written only when every step before it
succeeded, and exports only after that (a failed export removes the document and the files the call
wrote). An error keeps the normal error schema and adds ``step``, the step that failed, to it.
Shared by ``vixl_compose`` (MCP), ``vixl compose`` (CLI), ``POST /compose`` (REST, a dry run: that
server serves one fixed document) and ``compose`` (Python).
"""

from pathlib import Path

from .errors import VixlError, require

CREATE = ("width", "height", "background", "size", "purpose", "dpi", "orientation", "bleed", "seed", "variety")
FIELDS = {"path", *CREATE, "font_pairing", "layout", "style", "look", "operations", "operations_path", "check",
          "strict", "preview", "exports", "overwrite", "dry_run"}


class _Step:
    """Names the failing step on any VixlError raised inside it."""

    def __init__(self, name, done):
        self.name, self.done = name, done

    def __enter__(self):
        return self

    def __exit__(self, kind, exc, traceback):
        if exc is None:
            self.done.append(self.name)
            return False
        if isinstance(exc, VixlError) and "step" not in exc.details:
            exc.details["step"] = self.name
            exc.args = (f"{self.name}: {exc.args[0]}" if exc.args else self.name,)
        return False


def _targets(session, exports, overwrite, path):
    """Validated export targets (same options as vixl_export_batch), checked before anything is written."""
    from .export_batch import MAX_TARGETS, parse_target
    from .mcp_tools import EXPORT_SUFFIXES

    require(isinstance(exports, list) and 0 < len(exports) <= MAX_TARGETS,
            f"exports is a list of 1-{MAX_TARGETS} paths or export targets", field="exports")
    targets, seen = [], set()
    for index, raw in enumerate(exports):
        raw = {"path": raw} if isinstance(raw, str) else raw
        require(isinstance(raw, dict) and "document" not in raw,
                f"exports[{index}] is a path or {{path, scale, …}} (the composed document is exported)",
                field=f"exports[{index}]")
        target = parse_target(index, raw, {})
        destination = session.resolve(target.path)
        require(destination.suffix.lower() in EXPORT_SUFFIXES, f"exports[{index}]: choose a PNG, JPEG, WEBP, TIFF, "
                "AVIF, SVG, PDF, ICO, HTML or PPTX filename", field=f"exports[{index}].path")
        require(destination not in seen and destination != path, f"exports[{index}] repeats a path",
                field=f"exports[{index}].path")
        seen.add(destination)
        replace = overwrite if target.overwrite is None else target.overwrite
        require(replace or not destination.exists(), f"exports[{index}]: {target.path} already exists; set "
                "overwrite=true", field=f"exports[{index}].path")
        targets.append(raw)
    return targets


def _apply(project, operations, validate, detail="brief"):
    if not operations:
        return None
    return project.apply(operations, detail=detail, check=validate)


def _brief(result):
    """What an agent needs from an apply result: changed layers and warnings, not the full diff."""
    if not result:
        return None
    keep = {key: result[key] for key in ("warnings", "normalized", "next_steps") if result.get(key)}
    changes = result.get("changes") or {}
    layers = changes.get("layers") if isinstance(changes, dict) else None
    if isinstance(layers, dict):
        keep["layers"] = [entry.get("name", ident) if isinstance(entry, dict) else ident for ident, entry in layers.items()]
    return keep


def _slot_images(session, project, layout):
    """``layout`` with its ``image``/``images`` slots embedded: an entry that is not already an asset of the
    document is a workspace file or an https URL, imported through the same limits as vixl_import_image
    (workspace containment, the fetch policy, byte and pixel limits). Returns ``(layout, {asset: source})``."""
    import hashlib

    from .assets import add_encoded, read_bounded
    from .image_import import fetch_image

    sources = {}

    def embed(value, field):
        if not isinstance(value, str) or not value or value in project.assets:
            return value
        limit = project.limits.max_asset_bytes
        if value.lower().startswith(("http://", "https://")):
            data, source = fetch_image(value, project.limits)
        else:
            resolved = session.resolve(value)
            require(resolved.is_file(), f"{field}: no image file at {value!r} in the workspace (give a workspace "
                    "path, an https URL or an asset id from vixl_import_image)", "not_found", field=f"layout.{field}")
            data, source = read_bounded(resolved, limit), {"path": value}
        asset, _ = add_encoded(project, data)
        sources[asset] = {**source, "sha256": hashlib.sha256(data).hexdigest()}
        return asset

    layout = dict(layout)
    if "image" in layout:
        layout["image"] = embed(layout["image"], "image")
    if isinstance(layout.get("images"), list):
        layout["images"] = [embed(item, f"images[{index}]") for index, item in enumerate(layout["images"])]
    return layout, sources


def _keep_background(layout, background):
    """``layout`` set to keep the compose ``background``: an opaque colour becomes the layout's background role
    (the other roles are chosen to read on it), and ``transparent`` keeps the layout from painting one. A layout
    that names its own background role or ``transparent`` is left as given. Returns ``(layout, note or None)``."""
    from .render import color

    if background is None or "transparent" in layout or "background" in (layout.get("colors") or {}):
        return layout, None
    if not isinstance(layout.get("colors", {}), dict):
        return layout, None
    if color(background)[3] == 0:
        return {**layout, "transparent": True}, "transparent: the layout paints no background of its own"
    return ({**layout, "colors": {**layout.get("colors", {}), "background": background}},
            f"{background}: the layout's background role, with text and accents chosen to read on it")


def _style_layout(project, key, layout):
    """``layout`` with the choices a style's own checks expect, where the caller left them open: the alignment
    its text-align rule allows, its first palette (unless the workspace brand sets one) and a dark mode when it asks
    for a dark background. Returns
    ``(layout, {field: value})`` with what was set."""
    from .brand import for_project
    from .style_catalog import STYLES

    entry = STYLES[key]
    rules = {rule["kind"]: rule for rule in entry["checks"]}
    shaped = {}
    allowed = rules.get("text_align", {}).get("params", {}).get("allowed") or []
    if "align" not in layout and allowed and allowed[0] in ("left", "center", "right"):
        shaped["align"] = allowed[0]
    if "palette" not in layout and not isinstance(layout.get("colors"), list) and entry.get("palettes") \
            and not for_project(project).get("palette"):
        shaped["palette"] = list(entry["palettes"][0]["swatches"])
    if "mode" not in layout and "dark_background" in rules:
        shaped["mode"] = "dark"
    return {**layout, **shaped}, shaped


def _style_fonts(project, key):
    """Install the style's first font pairing. A download that fails leaves the fonts as they were and says
    so, since the style tag itself does not depend on it."""
    from .style_catalog import STYLES
    from .typefaces import pair_fonts

    pairings = STYLES[key].get("type", {}).get("pairings") or []
    if not pairings:
        return None
    try:
        installed = pair_fonts(project, pairings[0])
    except VixlError as exc:
        return {"pairing": pairings[0], "installed": False,
                "note": f"{exc.args[0] if exc.args else exc.code}; text keeps the current fonts, pass font_pairing "
                        "to choose another"}
    return {"pairing": installed["pairing"], "installed": True, "typography": installed.get("typography")}


def compose(session, *, path=None, operations=None, operations_path=None, layout=None, style=None, look=None,
            font_pairing=None, check=True, strict=False, preview=None, exports=None, overwrite=False,
            dry_run=False, **create):
    """Run the chain; returns ``(result, PNG bytes or None)``. ``dry_run`` runs every step up to preview and
    writes nothing (``path`` may be omitted)."""
    from .checks import batch_findings, _apply_options
    from .interfaces import service_check
    from .service_fonts import checker

    done = []
    with _Step("request", done):
        unknown = sorted(set(create) - set(CREATE))
        require(not unknown, f"Unknown compose field(s) {unknown}; fields: {', '.join(sorted(FIELDS))}",
                field=unknown[0] if unknown else None, allowed=sorted(FIELDS))
        require(type(dry_run) is bool and type(strict) is bool and type(overwrite) is bool,
                "dry_run, strict and overwrite are booleans", field="dry_run")
        resolved = None
        if not dry_run:
            require(isinstance(path, str), "Give path: the new .vixl document to write", field="path")
        if path is not None:
            resolved = session.resolve(path)
            require(resolved.suffix.lower() == ".vixl", "path must end in .vixl", field="path")
            require(dry_run or not resolved.exists(), f"{path} already exists; compose makes a new document",
                    field="path")
        require(not (dry_run and exports), "dry_run writes nothing; drop exports", field="exports")
        require(operations is None or operations_path is None, "Pass operations or operations_path, not both",
                field="operations_path")
        if operations_path is not None:
            operations = session.load_operations(operations_path)
        if isinstance(operations, dict):
            operations = operations.get("operations", [operations]) if "type" not in operations else [operations]
        require(operations is None or isinstance(operations, list), "operations is a list", field="operations")
        require(layout is None or (isinstance(layout, dict) and isinstance(layout.get("name"), str)),
                "layout is a layout-apply object with name and slots, e.g. {name: 'hero-statement', title: …}",
                field="layout")
        looks = [look] if isinstance(look, dict) else look or []
        require(isinstance(looks, list) and all(isinstance(item, dict) and item.get("look") for item in looks),
                "look is {look, target?, color?, amount?} or a list of them", field="look")
        require(style is None or isinstance(style, str), "style is a style name (vixl_styles)", field="style")
        names, preview_options = _apply_options(check if check is not False else None, preview)
    targets = []
    if exports:
        with _Step("export", []):  # checked now, before anything is built or written
            targets = _targets(session, exports, overwrite, resolved)

    with _Step("create", done):
        report = {}
        project = session.new_project(**create, workspace_fonts=not font_pairing, report=report)
        project._workspace = session.workspace
        validate = checker(project, service_check)
    steps = {"creation": report["creation"]} if report.get("creation") else {}
    if report.get("workspace_fonts"):
        steps["workspace_fonts"] = report["workspace_fonts"]
    style_key = None
    if style:
        with _Step("style", []):
            from .styles import resolve

            style_key = resolve(style)
    if font_pairing:
        with _Step("fonts", done):
            from .typefaces import pair_fonts

            typography = pair_fonts(project, font_pairing)
            steps["fonts"] = {key: typography.get(key) for key in ("pairing", "typography")}
    elif style_key and not report.get("workspace_fonts") and not (layout and ("font" in layout or "display_font" in layout)):
        # A style names its typefaces; without a pairing of the caller's own, use the style's.
        with _Step("fonts", done):
            fonts = _style_fonts(project, style_key)
            if fonts:
                steps["fonts"] = fonts
    if layout:
        with _Step("layout", done):
            layout, sources = _slot_images(session, project, layout)
            layout, kept = _keep_background(layout, create.get("background"))
            shaped = {}
            if style_key:
                layout, shaped = _style_layout(project, style_key, layout)
            steps["layout"] = _brief(_apply(project, [{**layout, "type": "layout-apply"}], validate)) or {}
            if sources:
                steps["layout"]["imported"] = [{"asset": asset, **source} for asset, source in sources.items()]
            if kept:
                steps["layout"]["background"] = kept
            if shaped:
                steps["layout"]["from_style"] = shaped
            record = project.state.get("layout") or {}
            for key in ("name", "seed", "blanks", "omitted", "notes"):
                if record.get(key):
                    steps["layout"][key] = record[key]
    if style:
        with _Step("style", done):
            from .styles import apply_operations

            _apply(project, apply_operations(style), validate)
            steps["style"] = {"style": style}
    if looks:
        with _Step("look", done):
            steps["look"] = _brief(_apply(project, [{**item, "type": "look"} for item in looks], validate))
    if operations:
        with _Step("operations", done):
            steps["operations"] = _brief(_apply(project, operations, validate))
    report = None
    if check is not False:
        with _Step("check", done):
            report = batch_findings(project, names, {layer["name"] for layer in project.state["layers"]})
            fixes = [issue for issue in report.get("issues", []) if issue.get("action") == "fix"]
            if strict and fixes:
                raise VixlError("design_check_failed", f"{len(fixes)} finding(s) need a fix; nothing was saved",
                                report=report)
    image = None
    if preview:
        with _Step("preview", done):
            from .proxy import preview_png

            image = preview_png(project, max_bytes=524_288, **preview_options)
    result = {"steps": done, **steps}
    if report is not None:
        result["check"] = report
    if dry_run:
        result.update(dry_run=True, canvas=project.state["canvas"], layer_count=len(project.state["layers"]))
        return result, image
    with _Step("save", done):
        from .fileio import file_lock

        with session._mutex:
            session.make_parent(resolved)
            with file_lock(str(resolved)):
                require(not resolved.exists(), f"{path} appeared while composing; nothing was saved", field="path")
                previous = session.path
                project.save(resolved)
                session._remember(resolved, project, session.stamp(resolved))
        result.update(document=session.relative(resolved), canvas=project.state["canvas"],
                      layer_count=len(project.state["layers"]), head=project.head, active_document=True)
        if previous and previous != resolved and Path(previous).is_relative_to(session.workspace):
            # Like vixl_document_create, compose activates the new document; say so, since later calls without
            # document= now edit and export it rather than the one that was active.
            result.setdefault("warnings", []).append(
                f"{session.relative(resolved)} is now the active document; calls without document= use it. Pass "
                f"document={session.relative(previous)!r} to keep working on the previous one.")
    if targets:
        written = []
        try:
            with _Step("export", done):
                from .export_batch import export_batch
                from .mcp_tools import export_file

                batch = export_batch(session, export_file, targets, overwrite=overwrite, stop_on_error=True,
                                     document=path)
                written = [session.resolve(item["path"]) for item in batch["results"] if "error" not in item]
                failed = [item for item in batch["results"] if "error" in item]
                if failed:
                    error = failed[0]["error"]
                    raise VixlError(error["error"], f"{failed[0]['path']}: {error['message']}",
                                    **{k: v for k, v in error.items() if k not in ("error", "message")})
                result["exports"] = [{key: item.get(key) for key in ("path", "format", "bytes")}
                                     for item in batch["results"]]
        except VixlError:
            for file in written:
                if not overwrite:
                    Path(file).unlink(missing_ok=True)
            session.documents.pop(resolved, None)
            if session.path == resolved:
                session.path = None
            resolved.unlink(missing_ok=True)
            raise
        result["steps"] = done
    return result, image


def run(workspace=".", **request):
    """Python entry point: ``run("work", path="card.vixl", size="instagram-post", layout={...}, exports=["card.png"])``.
    Returns the result, with the preview PNG bytes under ``preview_png`` when ``preview`` was asked for."""
    from .interfaces import Session

    result, image = compose(Session(workspace=workspace), **request)
    if image is not None:
        result["preview_png"] = image
    return result


def cli(args, options, limits):
    """``vixl compose --request FILE [--preview OUT.png] [--workspace DIR]``."""
    from .cli import read_json
    from .commands import Parser
    from .interfaces import Session

    parser = Parser(prog="vixl compose", description="Build a whole piece in one call: create, fonts, layout, style, "
                    "look, operations, check, preview, save and exports (atomic; errors name the failing step)")
    parser.add_argument("--request", required=True, help="JSON request file (or - for stdin); fields as vixl_compose")
    parser.add_argument("--preview", help="Write the preview PNG here")
    parser.add_argument("--workspace", default=str(Path.cwd()))
    a = parser.parse_args(args)
    request = read_json(a.request)
    require(isinstance(request, dict), "The request is a JSON object", field="request")
    session = Session(options.project, limits, workspace=a.workspace)
    preview_path = None
    if a.preview:
        preview_path = session.resolve(a.preview)
        require(preview_path.suffix.lower() == ".png" and not preview_path.exists(), "Choose a new .png for --preview",
                field="preview")
        request.setdefault("preview", True)
    result, image = compose(session, **request)
    if image is not None and preview_path is not None:
        with preview_path.open("xb") as stream:
            stream.write(image)
        result["preview"] = session.relative(preview_path)
    return result
