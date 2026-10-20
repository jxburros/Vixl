"""The actions behind the consolidated MCP tools, with typed signatures that validate their options.

Each MCP tool advertises a few common fields plus a generic ``options`` object. The action a call selects is an
ordinary function here whose keyword parameters (types, bounds, descriptions) are the exact contract: options
are validated against it strictly at runtime, ``vixl_reference(TOOL)`` serves it as JSON Schema, and a
validation error returns the failing action's schema, so the detail is paid for only when it is needed.
"""

from copy import deepcopy
from functools import lru_cache
import inspect
from io import BytesIO
import os
from typing import Annotated, Any, Literal

from pydantic import ConfigDict, Field, ValidationError, create_model

from . import calls
from .assets import read_bounded
from .errors import VixlError, require
from .fileio import file_lock
from .model import Limits

Positive = Annotated[int, Field(ge=1)]
Document = Annotated[str | None, Field(description=".vixl path; default: active document")]
Verbose = Annotated[bool, Field(description="Return the full result instead of the terse summary")]
Variety = Literal["low", "medium", "high", "fixed"]
FontScope = Annotated[Literal["document", "workspace"], Field(
    description="document (default): install into the document; workspace: the brand.json default for new documents")]
PURPOSE_HELP = ("What the piece is for: social, story, poster, flyer, print, document, form, invitation, slides, "
                "diagram, web, email, motion, video, logo, mark, emblem, badge, monogram, icon, app-icon or favicon. "
                "Without a size it picks the size (social 1080×1350, slides 1920×1080, print letter or A4 by locale, "
                "icon 1024×1024); with neither, 1080×1080. It also weights the rolled defaults")
BACKGROUND_HELP = ("Canvas colour. Omitted: the rolled palette's background, or transparent for logo, icon and "
                   "favicon sizes and mark purposes; 'transparent' keeps it clear")
HOUSE_STYLE_HELP = ("'on' (default) rolls a house-style direction (palette, background, motif, look, style, "
                    "fonts …) into design_defaults; 'off' rolls nothing: a white canvas (transparent for marks), "
                    "the workspace default fonts else the bundled font, and neutral layout defaults (craft rules "
                    "still apply). Omitted: the workspace setting (.vixl/variety.json house_style), else on")
REPAIRS = Literal["fit-text", "contrast-ink", "safe-area-nudge"]
CHECKS = Literal["bounds", "overlap", "contrast", "safe_area", "legibility", "blanks", "placeholders", "fonts", "brand",
                 "print", "color_vision", "guides", "alignment", "deck", "title_position", "type_scale", "words",
                 "min_font", "notes", "empty", "form", "drawing", "links", "style", "diagram", "flow", "codes",
                 "composition", "motion", "character", "captions", "connected", "cost", "accessibility"]


class Context:
    """What an action needs from the server: the workspace session, the call runtime and server policy."""

    def __init__(self, session, runtime=None, allow_screen_capture=False):
        self.session = session
        self.runtime = runtime
        self.allow_screen_capture = allow_screen_capture


# tool -> {action: function}; the first action registered for a tool is its default.
ACTIONS = {}
SUMMARIES = {
    "vixl_document": "Documents and history",
    "vixl_apply": "Atomic edit batches, new pieces and workflows",
    "vixl_check": "Tests and measurements",
    "vixl_render": "Previews and motion inspection",
    "vixl_export": "Files out of the document",
    "vixl_reference": "Catalogs, schemas and craft guidance",
}


def action(tool, name):
    def register(fn):
        ACTIONS.setdefault(tool, {})[name] = fn
        return fn

    return register


def image(data):
    from mcp.server.fastmcp import Image

    return Image(data=data, format="png")


@lru_cache(maxsize=None)
def model(tool, name):
    """A pydantic model of the action's keyword parameters (everything after ``ctx``), forbidding extras."""
    fn = ACTIONS[tool][name]
    fields = {}
    for parameter in list(inspect.signature(fn).parameters.values())[1:]:
        annotation = Any if parameter.annotation is inspect.Parameter.empty else parameter.annotation
        default = ... if parameter.default is inspect.Parameter.empty else parameter.default
        fields[parameter.name] = (annotation, default)
    config = ConfigDict(extra="forbid", arbitrary_types_allowed=True, protected_namespaces=())
    return create_model(f"{tool}_{name}".replace("-", "_"), __config__=config, **fields)


def options_schema(tool, name):
    """The action's parameters as slim JSON Schema: properties, required."""
    from .mcp_tools import slim_schema

    schema = slim_schema(deepcopy(model(tool, name).model_json_schema()))
    result = {"summary": (inspect.getdoc(ACTIONS[tool][name]) or "").split("\n\n")[0].replace("\n", " "),
              "properties": schema.get("properties", {})}
    if schema.get("required"):
        result["required"] = schema["required"]
    if schema.get("$defs"):
        result["$defs"] = schema["$defs"]
    return result


def describe(tool, name=None):
    """vixl_reference(TOOL): every action of a tool with its options, or one action."""
    require(tool in ACTIONS, f"Unknown tool {tool!r}; tools with actions: {', '.join(sorted(ACTIONS))}",
            "not_found", field="topic", allowed=sorted(ACTIONS))
    if name is not None:
        known(tool, name)
        return {"tool": tool, "action": name, **options_schema(tool, name)}
    return {"tool": tool, "summary": SUMMARIES.get(tool, ""), "default": next(iter(ACTIONS[tool])),
            "actions": {key: options_schema(tool, key) for key in ACTIONS[tool]}}


def known(tool, name):
    import difflib

    actions = ACTIONS[tool]
    if name not in actions:
        close = difflib.get_close_matches(str(name), list(actions), 2, 0.5)
        raise VixlError("invalid_arguments", f"{tool}: unknown action {name!r}; actions: {', '.join(actions)}"
                        + (f". Did you mean {close[0]!r}?" if close else ""), field="action",
                        allowed=list(actions), **({"suggestions": close} if close else {}))


def invoke(ctx, tool, name, values):
    """Validate ``values`` against the action's signature and run it. An invalid option or an unknown one returns
    the action's exact schema with the error."""
    import difflib

    known(tool, name)
    fields = model(tool, name)
    try:
        parsed = fields.model_validate(values)
    except ValidationError as exc:
        allowed = sorted(fields.model_fields)
        problems, suggestions = [], []
        for item in exc.errors():
            where = ".".join(str(part) for part in item.get("loc", ()))
            key = str(item.get("loc", ("",))[0])
            if item.get("type") == "extra_forbidden":
                close = difflib.get_close_matches(key, allowed, 1, 0.6)
                problems.append(f"unknown option {key!r}" + (f" (did you mean {close[0]!r}?)" if close else ""))
                suggestions += close
            else:
                problems.append(f"{where}: {'missing' if item.get('type') == 'missing' else item.get('msg', 'invalid')}")
        first = str(exc.errors()[0].get("loc", ("",))[0]) if exc.errors() else None
        raise VixlError("invalid_arguments", f"{tool} {name}: " + "; ".join(problems), field=first,
                        allowed=allowed, schema=options_schema(tool, name),
                        **({"suggestions": suggestions} if suggestions else {})) from exc
    arguments = {key: getattr(parsed, key) for key in fields.model_fields}
    return ACTIONS[tool][name](ctx, **arguments)


def merged(options, **given):
    """The values of one call: ``options`` plus the tool's advertised fields that were given (not None)."""
    require(options is None or isinstance(options, dict), "options is an object of action parameters",
            field="options")
    values = dict(options or {})
    for key, value in given.items():
        if value is not None:
            values[key] = value
    return values


# ---------------------------------------------------------------------------------------------- vixl_document


def terse_document(summary):
    """A document summary without the rolled design direction (verbose keeps it)."""
    canvas = summary.get("canvas") or {}
    keep = {key: canvas[key] for key in ("width", "height", "background", "size", "dpi") if key in canvas}
    result = {key: summary[key] for key in ("path", "layer_count", "head") if key in summary}
    result["canvas"] = keep
    defaults = summary.get("design_defaults") or {}
    if "seed" in defaults:
        result["seed"] = defaults["seed"]
    creation = summary.get("creation")
    if creation:
        fonts = creation.get("fonts") or {}
        result["creation"] = {**{k: creation[k] for k in ("size", "size_from", "purpose", "background", "background_from",
                                                          "house_style") if k in creation},
                              **({"fonts": {k: fonts[k] for k in ("pairing", "heading", "body", "installed")
                                            if k in fonts}} if fonts else {})}
    for key in ("template", "typography", "font_pairing_error", "workspace_fonts"):
        if summary.get(key):
            result[key] = summary[key]
    if isinstance(result.get("typography"), dict):
        result["typography"] = {k: v for k, v in result["typography"].items() if k in ("pairing", "heading", "body")}
    return result


@action("vixl_document", "inspect")
def document_inspect(
    ctx, target: str | None = None, document: Document = None, verbose: Verbose = False,
    object: Annotated[str | None, Field(description="An object name or path (dog, person/guitar): its kind chain, "
                                                    "bounds, parts, missing required parts and sub-objects; '*' "
                                                    "lists every object")] = None,
):
    """Describe the document or one layer: canvas plus key fields per layer with resolved [x, y, w, h] bounds;
    verbose gives every stored field; object= returns one object's tree."""
    from .changes import summarize

    with ctx.session.project(document=document) as project:
        if object is not None:
            from .objects import tree

            return tree(project, object)
        if verbose:
            return project.inspect(target)
        return summarize(project, target)


@action("vixl_document", "create")
def document_create(
    ctx,
    path: Annotated[str, Field(description="New .vixl file; never overwritten")],
    size: Annotated[str | None, Field(description="Named size: letter, a4, business-card, instagram-portrait, story, "
                                                  "youtube-thumbnail, favicon … (vixl_reference('sizes'))")] = None,
    width: Positive | None = None,
    height: Positive | None = None,
    purpose: Annotated[str | None, Field(description=PURPOSE_HELP)] = None,
    background: Annotated[str | None, Field(description=BACKGROUND_HELP)] = None,
    dpi: Annotated[float | None, Field(ge=36, le=2400)] = None,
    orientation: Literal["portrait", "landscape"] | None = None,
    bleed: Annotated[bool | float, Field(description="Print sizes: true adds standard bleed")] = False,
    seed: int | None = None,
    variety: Variety | None = None,
    font_pairing: Annotated[str | None, Field(
        description="Also install this curated pairing (vixl_reference('fonts') name, or 'random') as the document "
                    "typography; needs the font cache or network")] = None,
    workspace_fonts: Annotated[bool, Field(
        description="Embed the workspace default fonts (brand.json), else the rolled pairing from the font cache or "
                    "network; false keeps the proofing fallback; ignored with font_pairing")] = True,
    house_style: Annotated[Literal["on", "off"] | None, Field(description=HOUSE_STYLE_HELP)] = None,
    template: Annotated[str | None, Field(description="Create from this named template (vixl_reference('templates'))")] = None,
    variables: Annotated[dict | None, Field(description="template: values for its variables")] = None,
    verbose: Verbose = False,
):
    """Create and activate a new .vixl file from a named size, width/height, a purpose or a template (with none of
    them 1080×1080). Print sizes record dpi, bleed, safe area and trim/safe guides; the document gets reproducible
    design defaults (seed, variety), the palette background and the rolled font pairing; house_style='off' rolls
    none of them."""
    session = ctx.session
    if template is not None:
        from .resources import create_template

        require(width is None and height is None and size is None and purpose is None,
                "A template sets its own size; drop size, width, height and purpose", field="template")
        require(house_style is None, "A template sets its own design; drop house_style", field="house_style")
        with session._mutex:
            destination = session.resolve(path)
            require(destination.suffix.lower() == ".vixl", "Use a .vixl path in the workspace", field="path")
            session.make_parent(destination)
            with file_lock(str(destination)):
                require(not destination.exists(), "Destination already exists; open it instead", field="path")
                project = create_template(template, variables, limits=session.limits, workspace=session.workspace)
                project.save(destination)
                session.open(destination)
                created = session.summary(project, destination)
                if project.state.get("template"):
                    created["template"] = project.state["template"]
        return created if verbose else terse_document(created)
    require(variables is None, "variables fill a template; pass template too", field="variables")
    created = session.create(path, width, height, background, size=size, purpose=purpose, dpi=dpi,
                             orientation=orientation, bleed=bleed, seed=seed, variety=variety,
                             workspace_fonts=workspace_fonts and not font_pairing, house_style=house_style)
    if font_pairing:
        from .typefaces import pair_fonts

        try:
            with session.project(write=True, document=path) as project:
                created["typography"] = pair_fonts(project, font_pairing)
        except VixlError as exc:  # the document exists; say the pairing did not apply instead of hiding it
            created["font_pairing_error"] = str(exc)
    return created if verbose else terse_document(created)


@action("vixl_document", "open")
def document_open(
    ctx, path: str,
    verbose: Verbose = False,
):
    """Open and activate an existing .vixl file; other open documents stay available."""
    opened = ctx.session.open(path)
    return opened if verbose else terse_document(opened)


@action("vixl_document", "close")
def document_close(ctx, document: Document = None):
    """Close an open document (default: active). Edits are already saved."""
    return ctx.session.close(document)


@action("vixl_document", "list")
def document_list(
    ctx, path: Annotated[str, Field(description="Workspace directory")] = ".",
    offset: Annotated[int, Field(ge=0)] = 0, limit: Annotated[int, Field(ge=1, le=200)] = 100,
):
    """List workspace files and directories (paginated) and the open documents."""
    session = ctx.session
    directory = session.resolve(path)
    require(directory.is_dir(), "Directory does not exist", field="path")
    entries = sorted(
        (p for p in directory.iterdir()
         if not p.name.endswith(".lock") and not p.name.startswith(".vixl-")
         and p.resolve().is_relative_to(session.workspace)),
        key=lambda p: p.name,
    )
    return {
        "workspace": ".",  # Paths are relative to it; the absolute location stays private to the server.
        **session.open_documents(),
        "entries": [{"path": session.relative(p), **({"directory": True} if p.is_dir() else {})}
                    for p in entries[offset: offset + limit]],
        "next_offset": offset + limit if offset + limit < len(entries) else None,
    }


def history(ctx, action, ref=None, count=1, document=None, dry_run=False, fonts=True):
    result = ctx.session.history(action, ref, count, document, dry_run=dry_run, fonts=fonts)
    result.pop("nodes")
    return result


@action("vixl_document", "history")
def document_history(ctx, document: Document = None, offset: Annotated[int, Field(ge=0)] = 0,
                     limit: Annotated[int, Field(ge=1, le=100)] = 20):
    """Revision summaries, newest first (paginated), with the head, branches and checkpoints."""
    result = ctx.session.history("list", None, 1, document)
    nodes = result.pop("nodes")
    newest = list(reversed(nodes))
    result["total"] = len(nodes)
    result["nodes"] = [{"id": node["id"], "parent": node["parent"], "label": node.get("label"),
                        "operations": [op.get("type") for op in node["operations"]][:10],
                        **({"squashed": True} if node.get("squashed") else {})}
                       for node in newest[offset: offset + limit]]
    result["next_offset"] = offset + limit if offset + limit < len(nodes) else None
    return result


@action("vixl_document", "undo")
def document_undo(ctx, count: Positive = 1, document: Document = None):
    """Undo the last count edits; returns the head."""
    return history(ctx, "undo", count=count, document=document)


@action("vixl_document", "redo")
def document_redo(ctx, count: Positive = 1, document: Document = None):
    """Redo count undone edits; returns the head."""
    return history(ctx, "redo", count=count, document=document)


@action("vixl_document", "checkpoint")
def document_checkpoint(ctx, ref: Annotated[str, Field(description="Checkpoint name")], document: Document = None):
    """Name the current revision so checkout can return to it."""
    return history(ctx, "checkpoint", ref, document=document)


@action("vixl_document", "checkout")
def document_checkout(ctx, ref: Annotated[str, Field(description="head~N, branch, checkpoint or revision ID")],
                      document: Document = None):
    """Move the document to a revision, branch or checkpoint."""
    return history(ctx, "checkout", ref, document=document)


@action("vixl_document", "branch")
def document_branch(ctx, ref: Annotated[str, Field(description="Branch name")], document: Document = None):
    """Start a named branch at the current revision."""
    return history(ctx, "branch", ref, document=document)


@action("vixl_document", "begin")
def document_begin(ctx, document: Document = None):
    """Begin a transaction: later edits become one revision at commit (rollback drops them)."""
    return history(ctx, "begin", document=document)


@action("vixl_document", "commit")
def document_commit(ctx, document: Document = None):
    """Commit the open transaction as one revision."""
    return history(ctx, "commit", document=document)


@action("vixl_document", "rollback")
def document_rollback(ctx, document: Document = None):
    """Drop the open transaction's edits."""
    return history(ctx, "rollback", document=document)


@action("vixl_document", "compact")
def document_compact(
    ctx, dry_run: Annotated[bool, Field(description="Report what would be dropped without changing anything")] = False,
    fonts: Annotated[bool, Field(description="Also unregister fonts no text, role or fallback uses")] = True,
    document: Document = None,
):
    """Discard ALL undo history, branches and checkpoints and drop embedded files the design does not use; the
    design itself does not change. Use dry_run first."""
    return history(ctx, "compact", document=document, dry_run=dry_run, fonts=fonts)


@action("vixl_document", "notes")
def document_notes(
    ctx, text: Annotated[str | None, Field(description="Add a note with this text")] = None,
    resolve: Annotated[str | None, Field(description="Resolve the note with this ID")] = None,
    document: Document = None,
):
    """Human review notes left in vixl view: list them, add one (text) or resolve one (resolve)."""
    from .review import notes

    require(text is None or resolve is None, "Give text to add a note or resolve to close one, not both",
            field="text")
    with ctx.session.project(document=document) as project:
        if text is not None:
            return notes(project.path, "add", text=text)
        if resolve is not None:
            return notes(project.path, "resolve", note_id=resolve)
        return notes(project.path, "list")


# ---------------------------------------------------------------------------------------------- vixl_apply

Check = Annotated[bool | str | list[str] | None, Field(
    description="Also run vixl_check on the result: true (default checks) or check names. Lists 'fix' findings, "
                "composition findings and those on the layers this batch touched, and the two weakest regions")]
Preview = Annotated[bool | dict | None, Field(
    description="Also return a small preview PNG: true, or {page, region, max_width (512), max_height, time, isolate, "
                "overlay, focus, regions}. overlay (with check) outlines each fix finding; focus (a finding's index) "
                "zooms to it; with check, real-size crops of the weakest regions follow (regions: 0-2, default 2)")]
OperationsPath = Annotated[str | None, Field(
    description="Workspace .json (array) or .jsonl (one operation per line) file of operations instead of operations")]


def teach(exc, operations):
    """An invalid operation's error with the exact schema of each failing operation type."""
    from .steps import step_schema, step_type

    details = exc.details
    indexes = [details.get("operation_index")] + [item.get("operation_index") for item in details.get("errors", [])
                                                  if isinstance(item, dict)]
    schemas = {}
    for index in indexes:
        if not isinstance(index, int) or not isinstance(operations, list) or not 0 <= index < len(operations):
            continue
        op = operations[index]
        kind = op.get("type") if isinstance(op, dict) else None
        if not isinstance(kind, str) or kind in schemas or len(schemas) >= 3:
            continue
        found = step_schema(step_type(kind)) if step_type(kind) else operation_variant(kind)
        if found:
            schemas[kind] = found
    if schemas and not isinstance(details.get("schema"), dict):
        details["schema"] = schemas  # the exact contract, in place of a pointer to look it up
    return exc


def operation_variant(kind):
    """One operation type's exact schema (fields, enums, requirements, summary and examples), or None."""
    from .normalize import _canonical_type
    from .render import EFFECTS
    from .schema import operation_schema

    variants = {v["properties"]["type"]["const"]: v
                for v in operation_schema()["properties"]["operations"]["items"]["oneOf"]}
    canonical = _canonical_type(kind, set(variants))
    if canonical not in variants:
        return None
    variant = deepcopy(variants[canonical])
    for field in ("path", "linked"):
        if field != "path" or canonical not in ("text-layout", "shape", "select"):
            variant["properties"].pop(field, None)
    if canonical == "effect":
        variant["properties"]["name"] = {"enum": sorted(EFFECTS)}
    return variant


@action("vixl_apply", "batch")
def apply_batch(
    ctx,
    operations: Annotated[list[dict] | None, Field(min_length=1, max_length=Limits().max_operations)] = None,
    operations_path: OperationsPath = None,
    dry_run: bool = False,
    check: Check = None,
    preview: Preview = None,
    suites: Annotated[bool | str | list[str] | None, Field(
        description="Also run the document's check suites (attached with suite-set): true for all, or names")] = None,
    repair: Annotated[bool | list[REPAIRS] | None, Field(
        description="After the batch apply the built-in repair for each fix finding (fit-text, contrast-ink, "
                    "safe-area-nudge); each kept only if its finding is resolved and nothing new fails")] = None,
    detail: Annotated[Literal["brief", "compact", "full"] | None, Field(
        description="brief (default): ID, name and bounds of each changed layer; compact (verbose) adds changed "
                    "values; full adds before/after snapshots")] = None,
    verbose: Verbose = False,
    document: Document = None,
):
    """Apply operations atomically (all or none) and autosave. Items may also be session steps (import-image,
    import-document, import-font, font-pair, font-install, style-use, roll) that run in order inside the same
    all-or-nothing batch. check, suites and preview return the findings, failing rules and a preview in the same
    call."""
    from .critique import take_previews

    session, runtime = ctx.session, ctx.runtime
    require(operations is not None or operations_path is not None, "Pass operations or operations_path",
            field="operations")
    detail = detail or ("compact" if verbose else "brief")
    budget = runtime.inline_seconds / 2 if runtime is not None and runtime.inline_seconds else None
    try:
        if not (check or preview or suites or repair):
            result, png = session.apply(operations, dry_run, detail, document, operations_path=operations_path), None
        else:
            result, png = session.apply_reviewed(operations, dry_run, detail, document,
                                                 operations_path=operations_path, check=check, preview=preview,
                                                 budget=budget, suites=suites, repair=repair)
    except VixlError as exc:
        raise teach(exc, operations) from exc
    crops = take_previews(result)
    for number, entry in enumerate((result.get("check") or {}).get("regions", [])[:len(crops)], start=2):
        entry["preview"] = f"image {number} of {len(crops) + 1}"
    if png is None:
        return result
    return [result, image(png), *(image(data) for data in crops)]


@action("vixl_apply", "create")
def apply_create(
    ctx,
    create: Annotated[dict, Field(description="The new document: {path, size | width+height, purpose, background, "
                                              "font_pairing, layout {name, slots…}, style, look, dpi, orientation, "
                                              "bleed, seed, variety, house_style ('on' or 'off': "
                                              "'off' rolls no direction)}")],
    operations: Annotated[list[dict] | None, Field(max_length=Limits().max_operations)] = None,
    operations_path: OperationsPath = None,
    check: Annotated[bool | list[str], Field(description="vixl_check the result (true, or check names)")] = True,
    strict: Annotated[bool, Field(description="Fail, saving nothing, when check has 'fix' findings")] = False,
    preview: Annotated[bool | dict | None, Field(description="true or {page, region, max_width, max_height, time}")] = None,
    exports: Annotated[list[str | dict] | None, Field(description="Paths or batch export targets", max_length=64)] = None,
    overwrite: Annotated[bool, Field(description="Exports may replace files")] = False,
    dry_run: bool = False,
):
    """Build a whole new piece in one call: create → font pairing → layout → style → look → operations → check →
    preview → save → exports. Atomic: nothing is saved or exported unless every step succeeds; an error names its
    step. The new document becomes active."""
    from .compose import compose

    require(isinstance(create, dict), "create is an object: {path, size, purpose, layout …}", field="create")
    fields = dict(create)
    path = fields.pop("path", None)
    known_keys = {"font_pairing", "layout", "style", "look"}
    picked = {key: fields.pop(key) for key in list(fields) if key in known_keys}
    try:
        result, png = compose(ctx.session, path=path, operations=operations, operations_path=operations_path,
                              check=check, strict=strict, preview=preview, exports=exports, overwrite=overwrite,
                              dry_run=dry_run, **picked, **fields)
    except VixlError as exc:
        raise teach(exc, operations) from exc
    return result if png is None else [result, image(png)]


@action("vixl_apply", "workflow")
def apply_workflow(
    ctx, workflow: Annotated[str, Field(description="Workflow action (vixl_reference('workflows') lists them)")],
    request: Annotated[dict | None, Field(description="The action's fields")] = None,
    document: Document = None,
):
    """Run a production workflow: suites (check, act), resources, libraries, branches and groups, merge-impose,
    form-fill, repair-layout, check-all, replace-across, film and lyric video, adapt-sizes and more."""
    from .proxy import encode_png
    from .workflows import dispatch

    request = request or {}
    require(isinstance(request, dict), "request is an object of the action's fields", field="request")
    if workflow == "screen-capture":
        require(ctx.allow_screen_capture, "Desktop capture is disabled; start vixl mcp with --allow-screen-capture "
                "or VIXL_ALLOW_SCREEN_CAPTURE=1", "permission_denied")
    result = dispatch(ctx.session, workflow, request, document)
    if workflow in ("film-preview", "video-sample", "audio-analyze"):
        from PIL import Image as PILImage

        paths = result.get("images", []) if isinstance(result, dict) else []
        if isinstance(result, dict) and not paths:
            paths = [result.get("output") or result.get("spectrogram")]
        images = []
        for path in paths[:8]:
            if isinstance(path, str) and path.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
                with PILImage.open(ctx.session.resolve(path)) as source:
                    images.append(image(encode_png(source.convert("RGB"), 524288)))
        if images:
            return [result, *images]
    return result


# ---------------------------------------------------------------------------------------------- vixl_check

Targets = Annotated[list[str] | None, Field(description="Layer IDs, names, globs or groups")]


@action("vixl_check", "design")
def check_design(
    ctx,
    checks: Annotated[list[CHECKS] | None, Field(description="Check names (vixl_reference('checks')); default: the "
                                                             "standard set")] = None,
    targets: Targets = None,
    profile: Annotated[str | None, Field(description="draft, review, final or a workspace .vixl-checks.json profile: "
                                                     "picks the checks and suites; its fail_on decides passed")] = None,
    safe_area: Annotated[float | str | dict | None, Field(
        description="Inset from every edge: pixels, '5%', or {left, top, right, bottom}")] = None,
    avoid: Annotated[list[list[float | str]] | None, Field(
        description="Reserved zones [x, y, w, h] (pixels or %) that content must not touch")] = None,
    thumbnail_width: Annotated[int | Literal["auto"] | None, Field(
        description="Judge text at this thumbnail width; 'auto' is 320, null turns the thumbnail test off")] = "auto",
    min_thumbnail_text: Annotated[float, Field(gt=0, le=200)] = 10,
    min_contrast: Annotated[float | None, Field(ge=1, le=21)] = None,
    ink_limit: Annotated[float, Field(ge=100, le=400, description="print check: total ink limit %")] = 300,
    min_ppi: Annotated[float, Field(ge=36, le=2400, description="print check: lowest image resolution")] = 200,
    artboard: str | None = None,
    comp: str | None = None,
    page: Annotated[int | str | None, Field(description="Page to check (default: the active page)")] = None,
    deck: Annotated[dict | None, Field(description="deck checks: {profile: projected|screen|phone, min_font, "
                                                   "thumbnail_width, max_words, pages, include_hidden}")] = None,
    sample: Annotated[str | None, Field(description="form checks: 'worst' or a workspace CSV of rows")] = None,
    style: Annotated[str | list[str] | None, Field(description="style check: this style (or list) instead of the "
                                                               "document's style tag")] = None,
    connect_tolerance: Annotated[float, Field(ge=0, le=100, description="connected check: gap still touching, px")] = 2,
    repair: Annotated[bool | list[REPAIRS] | None, Field(
        description="Apply the suggested built-in repairs first (one undoable batch), then check")] = None,
    offset: Annotated[int, Field(ge=0, description="First finding to list")] = 0,
    limit: Annotated[int | None, Field(ge=1, le=200, description="Findings to list; counts still cover all")] = None,
    waivers: Annotated[bool, Field(description="false reports every finding as if nothing were waived")] = True,
    artboards: Annotated[Literal["all"] | list[str] | None, Field(description="Check every artboard or these")] = None,
    pages: Annotated[Literal["all"] | list[int | str] | None, Field(description="Check every page or these")] = None,
    comps: Annotated[Literal["all"] | list[str] | None, Field(description="Check with every layer comp or these")] = None,
    include_hidden: Annotated[bool, Field(description="pages='all' also checks hidden pages")] = False,
    document: Document = None,
):
    """Find design problems without looking (bounds, overlap, contrast, safe area, legibility, blanks, placeholders,
    fonts, composition and the opt-in checks). Each finding has a rule ID, layers, a box, measured versus expected,
    an action (fix, review, informational) and for fix findings a repair suggestion."""
    session = ctx.session
    if style is not None and checks is None:
        checks = ["style"]
    return session.check(
        document=document, checks=checks, targets=targets, safe_area=safe_area, avoid=avoid,
        thumbnail_width=thumbnail_width, min_thumbnail_text=min_thumbnail_text, min_contrast=min_contrast,
        ink_limit=ink_limit, min_ppi=min_ppi, artboard=artboard, comp=comp, page=page, deck=deck,
        sample=sample, style=style,
        connect_tolerance=connect_tolerance, repair=repair, offset=offset, limit=limit, profile=profile,
        waivers=waivers,
        **{key: value for key, value in (("artboards", artboards), ("pages", pages), ("comps", comps))
           if value is not None},
        **({"include_hidden": True} if include_hidden else {}),
    )


@action("vixl_check", "validate")
def check_validate(
    ctx, profile: str | None = None, rules: Annotated[list[str] | None, Field(description="Rule names")] = None,
    targets: Targets = None, verbose: Annotated[bool, Field(description="Include passes")] = False,
    severity: Literal["error", "warning", "info"] | None = None, suppress: list[str] | None = None,
    offset: Annotated[int, Field(ge=0)] = 0, limit: Annotated[int, Field(ge=1, le=200)] = 50,
    document: Document = None,
):
    """Rule-based validation of document structure and saved suites against a profile or named rules (bounded).
    Mark intentional bleed with layer-intent allow_crop or role background/decoration."""
    from .diagnostics import validation_report

    report = ctx.session.validate(profile, rules, document, suppress=suppress)
    return validation_report(report, detail="full" if verbose else "summary", targets=targets, severity=severity,
                             offset=offset, limit=limit)


@action("vixl_check", "measure")
def check_measure(
    ctx, point: list[int] | None = None, region: list[int] | None = None, foreground: str | None = None,
    target: str | None = None, histogram: Literal["summary", "full", "none"] = "summary",
    artboard: str | None = None, comp: str | None = None, document: Document = None,
):
    """Read rendered RGBA samples, alpha-weighted averages, channel statistics and layer contrast; histogram=full
    returns 256 bins per channel."""
    return ctx.session.measure(document=document, point=point, region=region, foreground=foreground, target=target,
                               histogram=histogram, artboard=artboard, comp=comp)


@action("vixl_check", "spacing")
def check_spacing(
    ctx, targets: Targets = None, axis: Literal["horizontal", "vertical"] = "vertical",
    around: str | None = None, before: str | None = None, after: str | None = None,
    expected: float | None = None, tolerance: Annotated[float, Field(ge=0)] = 1,
    artboard: str | None = None, comp: str | None = None, document: Document = None,
):
    """Pass/fail for intended equal gaps (or balance before/after an object) within a tolerance."""
    return ctx.session.measure_spacing(document=document, targets=targets, axis=axis, around=around, before=before,
                                       after=after, expected=expected, tolerance=tolerance, artboard=artboard,
                                       comp=comp)


@action("vixl_check", "spatial")
def check_spatial(
    ctx, target: str | None = None, targets: list[str | dict] | None = None, to: str | None = None,
    mode: Literal["relations", "canvas", "matrix", "grid", "guides", "composition", "hit", "free", "snap",
                  "all"] = "all",
    bounds: Literal["box", "ink"] = "box", tolerance: float = 1, point: list[float] | None = None,
    region: list[float] | None = None, grid: str | None = None, describe: bool = False,
    include_hidden: bool = False, limit: Annotated[int, Field(ge=1, le=200)] = 20, artboard: str | None = None,
    page: str | int | None = None, safe_area: float | list[float] | dict | None = None, document: Document = None,
):
    """Canvas-space relations, gaps, alignment, margins, grid and guide offsets, hit tests, free regions and snap
    operations; respects parent transforms."""
    with ctx.session.project(document=document) as project:
        return project.spatial(target=target, targets=targets, to=to, mode=mode, bounds=bounds, tolerance=tolerance,
                               point=point, region=region, grid=grid, describe=describe,
                               include_hidden=include_hidden, limit=limit, artboard=artboard, page=page,
                               safe_area=safe_area)


@action("vixl_check", "pixels")
def check_pixels(ctx, target: str | None = None, document: Document = None):
    """A pixel layer as compact character rows and palette colours, without image bytes."""
    with ctx.session.project(document=document) as project:
        return project.inspect_pixels(target)


# ---------------------------------------------------------------------------------------------- vixl_render

Region = Annotated[list[float | str] | None, Field(
    description="Zoom to [x, y, width, height] in document pixels or percentages", min_length=4, max_length=4)]
Isolate = Annotated[list[str] | None, Field(
    description="Only these layers or objects (names, object paths such as dog/head, object:KIND), zoomed to their ink")]
Time = Annotated[float | str | None, Field(description="Timeline frame: ms, '1.5s', '50%' or a marker name")]


@action("vixl_render", "preview")
def render_preview(
    ctx,
    max_width: Annotated[int, Field(ge=1, le=4096)] = 1024,
    max_height: Annotated[int, Field(ge=1, le=4096)] = 1024,
    max_bytes: Annotated[int, Field(ge=65536, le=4194304)] = 1_048_576,
    region: Region = None,
    page: Annotated[int | str | None, Field(description="Page number or name; 'all' shows every page on one sheet")] = None,
    time: Time = None,
    isolate: Isolate = None,
    variables: dict | None = None,
    artboard: str | None = None,
    comp: str | None = None,
    proof: Annotated[bool, Field(description="Soft-proof the CMYK print separation")] = False,
    simulate: Literal["protanopia", "deuteranopia", "tritanopia", "achromatopsia"] | None = None,
    guides: Annotated[bool | list[str] | None, Field(description="Draw guides: true for all, or guide/grid names")] = None,
    values: Annotated[dict | None, Field(description="Form field values to show, by field key")] = None,
    show_fields: Annotated[bool, Field(description="Outline form fields with their keys and tab order")] = False,
    overlay: Annotated[bool, Field(description="Run vixl_check and outline each fix finding, labelled with its rule "
                                               "and layer ID; also returns the boxes")] = False,
    views: Annotated[list[Literal["parts"]] | None, Field(
        description="['parts']: a labelled contact sheet of each isolated object, assembled and part by part")] = None,
    exploded: Annotated[bool, Field(description="With isolate: add an exploded view of the parts")] = False,
    document: Document = None,
):
    """An aspect-preserving PNG capped in size and bytes. region zooms (up to 8x); time shows an animation frame;
    proof shows CMYK print colour; simulate checks colour-blind legibility; isolate shows one object alone."""
    from .mcp_tools import preview

    session = ctx.session
    if overlay:
        from .feedback import preview as feedback_preview

        with session.project(document=document) as project:
            report = project.check(page=page)
            data, feedback = feedback_preview(project, report["issues"], overlay=True, max_width=max_width,
                                              max_height=max_height, max_bytes=max_bytes, region=region, page=page)
        feedback.update(outcome=report["outcome"], findings=len(report["issues"]))
        return [feedback, image(data)]
    return image(preview(session, variables, max_width, max_height, max_bytes, artboard, comp, region, document,
                         time=time, proof=proof, simulate=simulate, guides=guides, page=page, values=values,
                         show_fields=show_fields, isolate=isolate, views=views, exploded=exploded))


@action("vixl_render", "compare")
def render_compare(
    ctx, before: Annotated[str, Field(description="head, previous, head~N, branch, checkpoint or revision ID")] = "previous",
    after: str = "head", mode: Literal["side-by-side", "diff"] = "side-by-side",
    max_width: Annotated[int, Field(ge=64, le=4096)] = 1024, max_height: Annotated[int, Field(ge=64, le=4096)] = 768,
    isolate: Isolate = None, document: Document = None,
):
    """Compare two revisions: side-by-side before|after, or diff with changed pixels in red; also returns the
    changed fraction and region."""
    from .checks import compare
    from .proxy import encode_png

    session = ctx.session
    with session.project(document=document) as project:
        picture, summary = compare(project, before, after, max_width=max_width, max_height=max_height, mode=mode,
                                   isolate=isolate)
        summary["document"] = session.relative(project.path)
    return [summary, image(encode_png(picture, 2_097_152))]


@action("vixl_render", "timeline")
def render_timeline(
    ctx, time: Annotated[float | str | None, Field(description="One frame: ms, '1.5s', '50%' or marker")] = None,
    count: Annotated[int, Field(ge=2, le=48, description="Frames in the contact sheet when time is omitted")] = 8,
    times: Annotated[list[float | str] | None, Field(max_length=48, description="Exact frames for the sheet")] = None,
    columns: Annotated[int | None, Field(ge=1, le=12)] = None,
    max_width: Annotated[int, Field(ge=64, le=4096)] = 1600,
    thumbnail: Annotated[int | None, Field(ge=32, le=1600, description="Phone-size strip: poster (frame 0), middle "
                                                                        "and last frame, each this wide (e.g. 360)")] = None,
    document: Document = None,
):
    """Check keyframed motion without exporting: one frame at time, or a labelled contact sheet of evenly spaced
    (count) or chosen (times) frames; frame 0 is labelled poster."""
    from .mcp_tools import preview
    from .proxy import encode_png
    from .timeline import contact_sheet

    session = ctx.session
    with session.project(document=document) as project:
        if time is not None:
            return image(preview(session, None, max_width, max_width, 2_097_152, None, None, None, document, time=time))
        sheet = contact_sheet(project, count, columns, max_width, times=times, thumbnail=thumbnail)
    return image(encode_png(sheet, 4_194_304))


@action("vixl_render", "timeline-inspect")
def render_timeline_inspect(
    ctx, verbose: Annotated[bool, Field(description="Add paginated keys")] = False,
    targets: list[str] | None = None, properties: list[str] | None = None,
    start: float | str | None = None, end: float | str | None = None,
    offset: Annotated[int, Field(ge=0)] = 0, limit: Annotated[int, Field(ge=1, le=200)] = 50,
    key_offset: Annotated[int, Field(ge=0)] = 0, key_limit: Annotated[int, Field(ge=1, le=200)] = 50,
    document: Document = None,
):
    """Keyframed motion (keyframe, motion, animate, character-cycle): tracks per layer and property, filtered by
    target/property globs and time range."""
    from .diagnostics import timeline_report

    with ctx.session.project(document=document) as project:
        return timeline_report(project, detail="full" if verbose else "summary", targets=targets,
                               properties=properties, start=start, end=end, offset=offset, limit=limit,
                               key_offset=key_offset, key_limit=key_limit)


@action("vixl_render", "animation")
def render_animation(
    ctx, name: Annotated[str, Field(description="Saved frame name (frame-save)")],
    scale: Annotated[float, Field(ge=0.05, le=8)] = 1, sampling: Literal["nearest", "smooth"] = "nearest",
    document: Document = None,
):
    """One saved frame (frame-by-frame animation, sprites) at native size; nearest needs an integer scale and keeps
    pixel art crisp."""
    with ctx.session.project(document=document) as project:
        picture = project.render_frame(name, int(scale) if float(scale).is_integer() else scale, sampling)
        stream = BytesIO()
        picture.save(stream, format="PNG")
        require(len(stream.getvalue()) <= 4_194_304, "Frame preview exceeds 4 MiB; use a smaller scale")
        return image(stream.getvalue())


@action("vixl_render", "animation-inspect")
def render_animation_inspect(ctx, document: Document = None):
    """Frame-by-frame animation: saved frame names, sizes and durations and the named animations."""
    with ctx.session.project(document=document) as project:
        return project.inspect_animation()


# ---------------------------------------------------------------------------------------------- vixl_export

Overwrite = Annotated[bool, Field(description="Replace an existing file")]


@action("vixl_export", "file")
def export_one(
    ctx,
    path: Annotated[str, Field(description="Workspace file; the format follows the extension (.png .jpg .webp .tif "
                                           ".avif .svg .pdf .ico .html .pptx .psd, .vixl with isolate; .ttf .otf .woff .woff2 "
                                           "write the font design)")],
    overwrite: Overwrite = False,
    quality: Annotated[int | None, Field(ge=1, le=100)] = None,
    scale: Annotated[float, Field(ge=0.01, le=16)] = 1,
    profile: Annotated[str | None, Field(description="Export profile: its size and quality")] = None,
    variables: dict | None = None,
    background: str = "white",
    sampling: Literal["smooth", "nearest"] = "smooth",
    svg_policy: Annotated[Literal["appearance", "strict"], Field(description="strict rejects raster fallbacks")] = "appearance",
    artboard: str | None = None,
    comp: str | None = None,
    color_space: Annotated[Literal["rgb", "cmyk"], Field(description="cmyk separates JPEG/TIFF/PDF for print")] = "rgb",
    icc_profile: Annotated[str | None, Field(description="Workspace path of a CMYK .icc/.icm profile")] = None,
    intent: Literal["perceptual", "relative", "saturation", "absolute"] = "relative",
    black_generation: Annotated[float, Field(ge=0, le=1)] = 1.0,
    ink_limit: Annotated[float | None, Field(ge=100, le=400, description="Total ink limit, percent")] = None,
    proof: bool = False,
    simulate: Literal["protanopia", "deuteranopia", "tritanopia", "achromatopsia"] | None = None,
    dpi: Annotated[float | None, Field(ge=36, le=2400)] = None,
    icon_sizes: list[int] | None = None,
    time: Time = None,
    page: Annotated[int | str | None, Field(description="One page of a multi-page document")] = None,
    pages: Annotated[list[int | str] | str | None, Field(description="PDF/PPTX/HTML pages: [1, 3] or '1-3,intro'")] = None,
    pdf_content: Annotated[Literal["vector", "raster"] | None, Field(
        description="PDF pages as vector text and shapes (default) or one image per page")] = None,
    fillable: Annotated[bool, Field(description="PDF with fillable form fields")] = False,
    values: Annotated[dict | None, Field(description="Form field values by key: a filled copy")] = None,
    fill_mode: Literal["flatten", "editable"] = "flatten",
    alpha: Annotated[Literal["auto", "keep", "flatten"], Field(
        description="auto writes RGB when fully opaque, keep always RGBA, flatten composites onto background")] = "auto",
    presenter: Annotated[bool | dict | None, Field(
        description=".html of a multi-page document is a slide presentation; false writes one static image; options "
                    "{theme, slide_images, notes, start, title}")] = None,
    title: Annotated[str | None, Field(description="PDF document title")] = None,
    max_bytes: Annotated[int | None, Field(ge=1, description="Raster size budget: a warning when larger")] = None,
    isolate: Annotated[list[str] | None, Field(
        description="Only these layers or objects, cropped to their ink on a transparent canvas; a .vixl path writes "
                    "a portable object document")] = None,
    padding: Annotated[float | None, Field(ge=0, le=4096, description="Pixels around the ink with isolate")] = None,
    document: Document = None,
):
    """Export one file, full size by default (vixl_reference('exports') explains formats, CMYK, PDF, PPTX, HTML and
    forms). Returns file metadata, never image bytes."""
    from .mcp_tools import export_file

    session = ctx.session
    profile_bytes = read_bounded(session.resolve(icc_profile), 16 * 1024 * 1024) if icc_profile else None
    options = dict(quality=quality, scale=scale, profile=profile, variables=variables, background=background,
                   sampling=sampling, svg_policy=svg_policy, artboard=artboard, comp=comp, color_space=color_space,
                   icc_profile=profile_bytes, intent=intent, black_generation=black_generation, ink_limit=ink_limit,
                   proof=proof, simulate=simulate, dpi=dpi, icon_sizes=icon_sizes, time=time, page=page, pages=pages,
                   pdf_content=pdf_content, fillable=fillable, values=values, fill_mode=fill_mode, alpha=alpha,
                   presenter=presenter, title=title, max_bytes=max_bytes, isolate=isolate, padding=padding)
    return export_file(session, path, overwrite, document, **options)


@action("vixl_export", "batch")
def export_many(
    ctx,
    targets: Annotated[list[dict], Field(min_length=1, max_length=64, description=(
        "Outputs: {path, document?, overwrite?, ...any file export option}; one entry per file"))],
    defaults: Annotated[dict | None, Field(description="Options shared by every target; a target's own win")] = None,
    overwrite: Overwrite = False,
    stop_on_error: bool = False,
    document: Document = None,
):
    """Several files in one call (sizes, formats, artboards or documents). Every target is checked first, then
    written in order; each reports its own metadata or error."""
    from .export_batch import export_batch
    from .mcp_tools import export_file

    return export_batch(ctx.session, export_file, targets, defaults, overwrite, stop_on_error, document)


@action("vixl_export", "animation")
def export_animation(
    ctx, path: str, overwrite: Overwrite = False,
    format: Literal["gif", "apng", "webp", "mp4", "webm", "sheet"] | None = None,
    animation: Annotated[str | None, Field(description="One named animation (animation-set); default every saved frame")] = None,
    scale: Annotated[float, Field(ge=0.05, le=32)] = 1, sampling: Literal["nearest", "smooth"] = "nearest",
    colors: Annotated[int, Field(ge=2, le=256)] = 256, quality: Annotated[int, Field(ge=1, le=100)] = 90,
    columns: Positive | None = None,
    dither: Annotated[Literal["auto", "none", "ordered", "floyd"], Field(description="GIF dithering")] = "auto",
    max_bytes: Annotated[int | None, Field(ge=1, description="Soft size target: a warning when larger")] = None,
    document: Document = None,
):
    """Saved frames (frame-save) as GIF, APNG, animated WebP, MP4/WebM (needs ffmpeg) or a PNG sprite sheet plus
    JSON timing; nearest keeps pixel art crisp at integer scales."""
    session = ctx.session
    with session.project(document=document) as project:
        destination = session.resolve(path)
        result = project.export_animation(destination, format=format, animation=animation,
                                          scale=int(scale) if float(scale).is_integer() else scale, sampling=sampling,
                                          colors=colors, quality=quality, columns=columns, overwrite=overwrite,
                                          dither=dither, max_bytes=max_bytes)
        result["output"] = session.relative(destination)
        if "metadata" in result:
            result["metadata"] = session.relative(destination.with_suffix(".json"))
        return result


@action("vixl_export", "timeline")
def export_timeline(
    ctx, path: str, overwrite: Overwrite = False,
    format: Literal["gif", "apng", "webp", "sheet", "frames", "mp4", "webm"] | None = None,
    fps: Annotated[float | None, Field(ge=1, le=60)] = None, scale: Annotated[float, Field(ge=0.05, le=16)] = 1.0,
    start: float | str | None = None, end: float | str | None = None, background: str | None = None,
    columns: Positive | None = None, quality: Annotated[int, Field(ge=1, le=100)] = 90,
    colors: Annotated[int, Field(ge=2, le=256)] = 256,
    dither: Annotated[Literal["auto", "none", "ordered", "floyd"], Field(description="GIF dithering")] = "auto",
    max_bytes: Annotated[int | None, Field(ge=1, description="Soft size target: a warning when larger")] = None,
    poster: Annotated[float | str | None, Field(description="GIF/WebP/APNG: the moment whose frame comes first "
                                                            "(time, marker, percent or 'end')")] = None,
    sample_rate: Annotated[int | None, Field(ge=8000, le=96000, description="MP4/WebM audio rate, Hz")] = None,
    target_bytes: Annotated[int | None, Field(ge=1, description="GIF/WebP/APNG size to fit (steps down colors, fps, "
                                                                "scale)")] = None,
    preset: Annotated[Literal["chat", "web", "email"] | None, Field(description="GIF/WebP/APNG size presets")] = None,
    document: Document = None,
):
    """The keyframe timeline as GIF, APNG, animated WebP, sprite sheet (+JSON), PNG-sequence ZIP or MP4/WebM
    (needs ffmpeg); results report the frames and size written."""
    from .timeline import export_timeline as write

    session = ctx.session
    with session.project(document=document) as project:
        destination = session.resolve(path)
        result = write(project, destination, format=format,
                       fps=int(fps) if fps and float(fps).is_integer() else fps, scale=scale, start=start, end=end,
                       background=background, columns=columns, quality=quality, colors=colors, overwrite=overwrite,
                       dither=dither, max_bytes=max_bytes, poster=poster, sample_rate=sample_rate,
                       target_bytes=target_bytes, preset=preset, progress=calls.progress_dict,
                       cancelled=calls.cancelled)
        result["output"] = session.relative(destination)
        if "metadata" in result:
            result["metadata"] = session.relative(destination.with_suffix(".json"))
        return result


@action("vixl_export", "audio")
def export_audio(
    ctx, path: Annotated[str, Field(description="New .wav file")],
    sample_rate: Annotated[int | None, Field(ge=8000, le=96000, description="Hz; default the highest source rate "
                                                                            "up to 48000")] = None,
    document: Document = None,
):
    """Mix the document's imported and synthesized audio tracks to a new WAV."""
    from .audio import export_audio as mix

    session = ctx.session
    destination = session.resolve(path)
    require(destination.suffix.lower() == ".wav", "Choose a .wav output", field="path")
    session.make_parent(destination)
    with session.project(document=document) as project:
        report = mix(project, destination, sample_rate)
    return {**report, "output": session.relative(destination)}


@action("vixl_export", "icons")
def export_icon_set(
    ctx, path: Annotated[str, Field(description="Workspace folder for the icon files")],
    icon_set: Literal["web", "apple", "android", "windows", "all"] = "web",
    sampling: Literal["smooth", "nearest"] = "smooth", document: Document = None,
):
    """Render once and write a standard icon set: web (favicon.ico, 16/32/48, apple-touch-icon, android-chrome,
    site.webmanifest), apple, android, windows or all."""
    from .exports import export_icons

    session = ctx.session
    with session.project(document=document) as project:
        destination = session.resolve(path)
        result = export_icons(project, destination, icon_set=icon_set, sampling=sampling)
        result["directory"] = session.relative(destination)
        return result


@action("vixl_export", "character")
def export_character_library(
    ctx, path: Annotated[str, Field(description="New .vixl character library")],
    target: Annotated[str, Field(description="The character to save")], document: Document = None,
):
    """Save one reusable character and its assets to a new .vixl library; load it with character-load source=path."""
    from .plugins.characters.characters import export_character

    session = ctx.session
    destination = session.resolve(path)
    require(destination.suffix.lower() == ".vixl", "Choose a .vixl character library file", field="path")
    require(not destination.exists(), "Character output already exists", field="path")
    session.make_parent(destination)
    with session.project(document=document) as project:
        report = export_character(project, target, destination)
    return {**report, "output": session.relative(destination)}


MOTION_SUFFIXES = (".gif", ".apng", ".mp4", ".webm", ".zip")


def export_kind(ctx, path, values, document):
    """The export kind a call implies: batch for targets, audio for .wav, timeline or saved-frame animation for
    motion formats, else one file."""
    if "targets" in values:
        return "batch"
    suffix = os.path.splitext(path or "")[1].lower()
    if suffix == ".wav":
        return "audio"
    if suffix in MOTION_SUFFIXES or (suffix == ".webp" and ("fps" in values or "animation" in values)):
        if "animation" in values:
            return "animation"
        with ctx.session.project(document=document) as project:
            frames = (project.state.get("animation") or {}).get("frames")
            return "animation" if frames and not project.state.get("timeline") else "timeline"
    return "file"


# ---------------------------------------------------------------------------------------------- vixl_reference


@action("vixl_reference", "start")
def reference_start(ctx):
    """The working loop, every kind of work and every guidance name."""
    from .briefs import guide

    return guide(None, workspace=ctx.session.workspace)


@action("vixl_reference", "guide")
def reference_guide(
    ctx, name: Annotated[str | None, Field(description="A kind of work, a free-text brief or a guidance name")] = None,
    seed: int | None = None, variety: Variety | None = None,
):
    """What to make and how: the approach, operations, layouts, looks and styles for a kind of work or brief, a
    guidance text, motifs for a setting. Any unknown topic is read as a brief."""
    from .briefs import guide

    return guide(name, seed=seed, variety=variety, workspace=ctx.session.workspace)


@action("vixl_reference", "operations")
def reference_operations(
    ctx, name: Annotated[str | list[str] | None, Field(description="1–20 operation types; none lists every operation "
                                                                  "by purpose")] = None,
):
    """The exact JSON Schema (fields, enums, requirements, summary, examples) of the named operation types,
    including the session steps; without a name every operation by purpose."""
    import difflib

    from .schema import _properties
    from .steps import STEPS, step_schema, step_type

    if name is None:
        from .briefs import guide

        listing = guide("operations")
        listing["steps"] = {kind: step_schema(kind)["description"] for kind in STEPS}
        return listing
    types = [part.strip() for part in name.split(",")] if isinstance(name, str) else name
    require(isinstance(types, list) and 0 < len(types) <= 20, "Request 1–20 operation types", field="name")
    result = {}
    for kind in types:
        step = step_type(kind)
        if step:
            result[step] = step_schema(step)
            continue
        variant = operation_variant(kind)
        if variant is None:
            close = difflib.get_close_matches(str(kind), [*_properties(), *STEPS], 3, 0.5)
            result[kind] = {"error": "unknown operation type", "suggestions": close}
            continue
        result[variant["properties"]["type"]["const"]] = variant
    return result


@action("vixl_reference", "capabilities")
def reference_capabilities(
    ctx, name: Annotated[str | None, Field(description="A topic (text, drawing, animation, film, layout, color, export) "
                                                       "or any words such as 'loop'")] = None,
    fields: Annotated[bool, Field(description="Add each matching operation's fields")] = False,
):
    """Field-level reference for a topic: matching operations, workflows, gotchas, limits and guidance names."""
    from .capabilities import lookup

    return lookup(name, fields=fields)


@action("vixl_reference", "workflows")
def reference_workflows(ctx, name: Annotated[str | None, Field(description="One workflow action")] = None):
    """Workflow actions (vixl_apply workflow=…) and their request fields."""
    from .workflows import describe as workflows

    found = workflows()
    if name is None:
        return found
    actions = found.get("actions", {})
    require(name in actions, f"Unknown workflow action {name!r}", "not_found", field="name", allowed=sorted(actions))
    return {"action": name, **actions[name]}


@action("vixl_reference", "sizes")
def reference_sizes(ctx, name: Annotated[str | None, Field(description="Words to search for")] = None,
                    category: str | None = None):
    """Named document sizes: print (with dpi, bleed and safe area), social, web, ads, email, video, slides,
    screens, app-store, icons, logos and game."""
    from .sizes import catalog

    return catalog(category, name)


@action("vixl_reference", "layouts")
def reference_layouts(ctx, name: Annotated[str | None, Field(description="One layout: its principles and slots")] = None):
    """Principled text layouts (hero-statement, editorial-grid, rule-of-thirds …) applied with layout-apply; fill
    every slot it lists."""
    from .layouts import LAYOUTS, catalog, describe as layout

    if name:
        require(name in LAYOUTS, f"Unknown layout {name!r}", field="name")
        return {"name": name, **layout(name), "options": catalog()["options"]}
    return catalog()


@action("vixl_reference", "fonts")
def reference_fonts(
    ctx, name: Annotated[str | None, Field(description="A family (view font) or pairing (view pairing)")] = None,
    view: Literal["fonts", "font", "pairings", "pairing", "principles"] | None = None,
    category: str | None = None, role: str | None = None, mood: str | None = None, best_for: str | None = None,
):
    """Researched typefaces, curated heading/body pairings with the reason each works, and the pairing principles;
    install with the font-pair or font-install operation."""
    from . import typefaces

    if view is None and name:
        try:
            return typefaces.get_pairing(name)
        except VixlError:
            return typefaces.show_font(name)
    view = view or "pairings"
    if view == "fonts":
        return typefaces.list_fonts(category, role, mood)
    if view == "font":
        require(name, "view font needs name (a family)", field="name")
        return typefaces.show_font(name)
    if view == "principles":
        return {"principles": typefaces.principles()}
    if view == "pairing":
        require(name, "view pairing needs name", field="name")
        return typefaces.get_pairing(name)
    return typefaces.list_pairings(mood, best_for, name)


@action("vixl_reference", "brushes")
def reference_brushes(ctx):
    """Built-in brushes and their settings; paint with {type: paint, brush, points | path, size, color}."""
    from .brushes import catalog

    return catalog()


@action("vixl_reference", "styles")
def reference_styles(ctx, name: Annotated[str | None, Field(description="One style: principles, palettes, type, "
                                                                       "do/don't and checks")] = None,
                     query: Annotated[str | None, Field(description="Words to find")] = None):
    """Design styles (swiss, brutalist, art-deco, risograph …); apply one with the style-use operation."""
    from . import styles

    return styles.describe(name) if name else styles.listing(query)


@action("vixl_reference", "looks")
def reference_looks(ctx):
    """Finishing looks (glow, soft-shadow, gradient, grain, paper …) for the look operation."""
    from .briefs import guide

    return guide("looks")


@action("vixl_reference", "color")
def reference_color(
    ctx, name: Annotated[str | list[str], Field(description="One colour or a list (up to 16)")],
    action: Literal["info", "convert", "harmony", "scale", "mix", "contrast", "names", "natural"] = "info",
    to: Literal["hex", "rgb", "hsl", "hsv", "hwb", "cmyk", "lab", "lch", "oklab", "oklch", "css"] | None = None,
    scheme: str = "complementary", count: int | None = None,
    amount: Annotated[float, Field(ge=0, le=1)] = 0.5, space: str = "oklab",
):
    """Colour tools: info (every representation, names, contrast), convert, harmony, scale (50–950), mix, contrast
    (WCAG), names (search), natural (a natural palette for a subject and light)."""
    colors = [name] if isinstance(name, str) else list(name)
    require(0 < len(colors) <= 16, "Give 1–16 colours", field="name")
    if action == "natural":
        from .natural_guidance import natural_palette

        return natural_palette(colors[0], colors[1] if len(colors) > 1 else "day")
    from .feature_cli import color_command

    args = [action, *colors]
    if to:
        args += ["--to", to]
    if count:
        args += ["--count", str(count)]
    args += ["--scheme", scheme, "--amount", str(amount), "--space", space]
    result = color_command(args)
    return result if isinstance(result, dict) else {"results": result}


@action("vixl_reference", "roll")
def reference_roll(
    ctx, purpose: str | None = None, mood: str | None = None, seed: int | None = None, variety: Variety | None = None,
    locks: Annotated[dict | None, Field(description="Fix choices such as palette or layout")] = None,
    document: Document = None,
):
    """Roll a coherent direction (layout, pairing, palette, look …) honouring the workspace brand.json, without
    changing anything; the roll operation applies one."""
    from .typefaces import roll_document

    session = ctx.session
    if document or session.path:
        with session.project(document=document) as project:
            return roll_document(project, seed=seed, purpose=purpose, mood=mood, locks=locks, variety=variety)
    return roll_document(workspace=session.workspace, seed=seed, purpose=purpose, mood=mood, locks=locks,
                         variety=variety)


def _resource(kind):
    def read(ctx, name: Annotated[str | None, Field(description="One entry; none lists the names")] = None):
        from .resources import catalog, get

        workspace = ctx.session.workspace
        if kind == "objects":
            from .objects import describe as object_kind

            if name:
                return {"name": name, "value": object_kind(name, workspace)}
            return {"kind": kind, "names": sorted(catalog(kind, workspace=workspace))}
        if kind == "house-style":
            from .house_style import show

            return {"name": name or "all", "value": show(None if name in (None, "", "all", "default") else name)}
        if name:
            return {"name": name, "value": get(kind, name, workspace=workspace)}
        return {"kind": kind, "names": sorted(catalog(kind, workspace=workspace))}

    read.__doc__ = {
        "palettes": "Built-in and saved palettes; name reads one.",
        "templates": "Document templates (vixl_document create template=NAME); name reads one.",
        "guidance": "Craft guidance names; name reads one text (user additions included).",
        "objects": "Object kinds (dog, guitar, person …); name reads its parts, connections, proportions and layering.",
        "house-style": "The built-in default brand: craft rules, tiers and levels, or a purpose's profile (name).",
    }[kind]
    return read


for _kind in ("palettes", "templates", "guidance", "objects", "house-style"):
    action("vixl_reference", _kind)(_resource(_kind))
