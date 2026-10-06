"""Typed, bounded MCP tools for a persistent Vixl workspace session.

Responses are minified JSON text (no duplicated structured copy), errors carry the engine's
structured code/field/suggestions, and every document tool accepts an optional ``document``.
"""

import base64
import binascii
from copy import deepcopy
from io import BytesIO
import json
import os
from types import SimpleNamespace
from typing import Annotated, Literal

from .fileio import file_lock
from PIL import Image as PILImage
from pydantic import Field, WithJsonSchema

from . import calls
from .assets import read_bounded
from .errors import VixlError, require
from .mcp_runtime import Runtime
from .proxy import encode_png, preview_png
from .schema import operation_schema
from .model import Limits

COORDINATE_NOTE = (
    "x/y accept pixels, 'center' or a percentage like '50%'; width/height accept pixels or '25%' "
    "(of the canvas, or of the parent group for grouped layers). Colors accept CSS and xkcd names, #hex, "
    "rgb()/hsl()/hwb()/lab()/lch()/oklab()/oklch()/cmyk()/kelvin()/color(display-p3 …)/color-mix(), @swatch "
    "references and modifiers such as lighten(@brand, 10%) or mix(@a, @b, 30%). Common aliases (rect, circle, font_size, fill, camelCase keys, "
    "opacity '70%') are accepted and reported under 'normalized'. Opacity is 0–1 everywhere; a bare 70 is an error. "
    "Operations on existing layers take target or targets (a list: applied to each, or jointly for group/align)."
)


def compact_json(value):
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False, default=str)


def strip_prose(schema):
    """Remove descriptions and examples from a schema and the schemas nested in it, in place."""
    if isinstance(schema, list):
        for item in schema:
            strip_prose(item)
    elif isinstance(schema, dict):
        schema.pop("description", None)
        schema.pop("examples", None)
        for key, value in schema.items():
            if key in ("properties", "$defs", "definitions", "patternProperties"):
                for sub in value.values():
                    strip_prose(sub)
            elif key not in ("enum", "const", "default"):
                strip_prose(value)


def service_operation_schema(slim=False):
    """Advertise canonical service operations directly in tools/list, without alias repetition."""
    from .render import EFFECTS

    if slim:
        from .schema import _properties

        kinds = sorted(k for k in _properties() if k not in EFFECTS)
        return {
            "type": "object",
            "required": ["type"],
            "properties": {"type": {"type": "string", "enum": kinds}},
            "additionalProperties": True,
            "description": "Fields per type: call vixl_operation_schema(types=[...]).",
        }
    groups = {}
    for variant in deepcopy(operation_schema()["properties"]["operations"]["items"]["oneOf"]):
        props = variant["properties"]
        kind = props.pop("type")["const"]
        if kind in EFFECTS:
            continue  # All effects use the canonical {type: effect, name: ...} form.
        for field in ("path", "linked"):  # font stays: a registered font name or role (service_fonts)
            if kind not in ("text-layout", "shape", "select") or field != "path":
                props.pop(field, None)
        if kind in ("add", "frame"):
            variant.pop("anyOf")
            variant["required"].append("asset")
        if kind in ("shape", "text"):
            # shape/text also edit an existing layer through target; the full schema says what is required.
            variant.pop("anyOf")
        if kind == "replace-contents":
            variant["anyOf"] = [{"required": ["asset"]}, {"required": ["variable"]}]
        if kind == "mask":
            props["action"]["enum"].remove("import")
        if kind == "effect":
            props["name"] = {"type": "string", "enum": sorted(EFFECTS)}
        # Detailed field prose, summaries and examples remain available through vixl_operation_schema.
        # Avoid repeating them in every tools/list response as the operation catalog grows.
        variant.pop("description", None)
        variant.pop("examples", None)
        for key, constraint in props.items():
            strip_prose(constraint)
            if kind in ("suite-set", "recipe-set") and "properties" in constraint:
                # The suite and recipe objects are typed in vixl_operation_schema and validated when applied.
                props[key] = {"type": "object"}
        if kind in ("diagram", "diagram-set", "text-flow"):
            for key in ("nodes", "edges", "frames"):
                if key in props:  # item fields are checked on apply; vixl_operation_schema lists them
                    props[key] = {"type": "array"}
        if kind in ("field-set", "form", "chart", "chart-data"):
            # Nullable copies of the field settings: names only here, types via vixl_operation_schema.
            props.update({key: {} for key in props if key not in ("target", "kind")})
        key = json.dumps(variant, sort_keys=True)
        groups.setdefault(key, []).append(kind)
    variants = []
    for key, kinds in groups.items():
        variant = json.loads(key)
        variant["properties"]["type"] = {"type": "string", "enum": kinds}
        variants.append(variant)
    # Hoist identical property constraints once. Each variant still lists its allowed
    # fields (additionalProperties=false), keeping per-operation validation strict.
    definitions = {}
    for variant in variants:
        for key, value in variant["properties"].items():
            definitions.setdefault(key, []).append(value)
    # Hoist the common part even when one operation narrows a field (e.g. name enums
    # or a smaller targets limit). Variant-specific constraints remain in oneOf.
    common = {}
    for key, values in definitions.items():
        if len(values) < 2:
            continue
        for value in values:
            if "enum" in value and all(isinstance(v, str) for v in value["enum"]):
                value.setdefault("type", "string")
        shared = {k: v for k, v in values[0].items() if all(other.get(k) == v for other in values)}
        if shared:
            common[key] = shared
    for variant in variants:
        variant.pop("type", None)
        variant["required"].remove("type")
        if not variant["required"]:
            variant.pop("required")
        for key in common.keys() & variant["properties"].keys():
            variant["properties"][key] = {k: v for k, v in variant["properties"][key].items() if k not in common[key]}
    repeated = {}
    for variant in variants:
        for field, constraint in variant["properties"].items():
            if field != "type" and constraint:
                repeated.setdefault((field, json.dumps(constraint, sort_keys=True)), []).append(variant)
    conditions = []
    for (field, encoded), members in repeated.items():
        if len(members) < 2:
            continue
        kinds = [kind for member in members for kind in member["properties"]["type"]["enum"]]
        condition = {"if": {"properties": {"type": {"enum": kinds}}},
                     "then": {"properties": {field: json.loads(encoded)}}}
        if (len(encoded) - 2) * len(members) <= len(json.dumps(condition)):
            continue
        conditions.append(condition)
        for member in members:
            member["properties"][field] = {}
    return {"type": "object", "required": ["type"], "properties": common, "oneOf": variants,
            **({"allOf": conditions} if conditions else {})}


def slim_schema(schema, in_properties=False):
    """Drop pydantic's per-field titles and collapse Optional[X] (anyOf X|null, default null) to X.
    Arguments may still be omitted; this only shortens what every agent reads in tools/list."""
    if isinstance(schema, list):
        return [slim_schema(item) for item in schema]
    if not isinstance(schema, dict):
        return schema
    if in_properties:
        return {key: slim_schema(value) for key, value in schema.items()}
    result = {}
    for key, value in schema.items():
        if key == "title" and isinstance(value, str):
            continue
        result[key] = slim_schema(value, in_properties=key in ("properties", "$defs", "definitions"))
    options = result.get("anyOf")
    if isinstance(options, list) and len(options) == 2 and {"type": "null"} in options:
        other = next(option for option in options if option != {"type": "null"})
        result.pop("anyOf")
        if result.get("default", 0) is None:
            result.pop("default")
        result = {**other, **result}
    return result


Positive = Annotated[int, Field(ge=1)]
Detail = Literal["compact", "full"]
ApplyDetail = Literal["brief", "compact", "full"]
Document = Annotated[str | None, Field(description=".vixl path; default: active document")]


def preview(
    session,
    variables=None,
    max_width=1024,
    max_height=1024,
    max_bytes=1_048_576,
    artboard=None,
    comp=None,
    region=None,
    document=None,
    time=None,
    proof=False,
    simulate=None,
    guides=None,
    page=None,
    values=None,
    show_fields=False,
):
    with session.project(document=document) as project:
        return preview_png(project, max_width, max_height, max_bytes, region=region, variables=variables,
                           artboard=artboard, comp=comp, time=time, proof=proof, simulate=simulate, guides=guides,
                           page=page, values=values, show_fields=show_fields)


EXPORT_SUFFIXES = (".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff", ".avif", ".svg", ".pdf", ".ico", ".html", ".htm", ".pptx", ".psd")


def export_file(session, path, overwrite=False, document=None, **options):
    from .fileio import temporary

    with session._mutex:
        destination = session.resolve(path)
        require(
            destination.suffix.lower() in EXPORT_SUFFIXES,
            "Choose a PNG, JPEG, WEBP, TIFF, AVIF, SVG, PDF, ICO, HTML, PPTX or PSD filename",
            field="path",
        )
        session.make_parent(destination)
        with file_lock(str(destination)):
            require(
                overwrite or not destination.exists(),
                "Destination already exists; set overwrite=true",
                field="path",
            )
            fmt = {".jpg": "JPEG", ".jpeg": "JPEG", ".tif": "TIFF", ".tiff": "TIFF", ".pdf": "PDF", ".ico": "ICO"}.get(
                destination.suffix.lower(), destination.suffix[1:].upper()
            )
            report = {}
            with session.project(document=document) as project:
                data = project.export(format=fmt, report=report, **options)
            fd, temporary_path = temporary(
                destination.parent, like=destination if destination.exists() else None
            )
            try:
                with os.fdopen(fd, "wb") as stream:
                    stream.write(data)
                    stream.flush()
                    os.fsync(stream.fileno())
                if overwrite:
                    os.replace(temporary_path, destination)
                else:
                    # Atomic no-clobber publication, including non-Vixl writers.
                    os.link(temporary_path, destination)
            finally:
                if os.path.exists(temporary_path):
                    os.unlink(temporary_path)
        return {"path": session.relative(destination), "format": fmt, "bytes": len(data), **report}


def decode_upload(data_base64, limit):
    require(isinstance(data_base64, str) and data_base64, "data_base64 must be a non-empty string")
    payload = data_base64.split(",", 1)[1] if data_base64.startswith("data:") else data_base64
    payload = "".join(payload.split())
    require(len(payload) <= limit * 4 // 3 + 8, "Image exceeds byte limit", "resource_limit")
    try:
        return base64.b64decode(payload, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise VixlError("invalid_image", "data_base64 is not valid base64", field="data_base64") from exc


def typed_ai(session, command, words=(), document=None, **options):
    from .ai import ai_execute

    defaults = dict(
        words=list(words),
        provider=None,
        prompt=None,
        negative_prompt=None,
        size=None,
        model=None,
        mode=None,
        selection=None,
        name="generated",
        seed=None,
        strength=0.75,
        apply=False,
        detail="compact",
        double=False,
        scale=2,
        left=0,
        right=0,
        top=0,
        bottom=0,
    )
    defaults.update(options)
    with session.project(document=document) as project:
        result, changed = ai_execute(project, command, SimpleNamespace(**defaults))
        if changed:
            project.save()
        return result


# Tools both split servers need: the AI server addresses layers by name and checks its results.
SHARED_TOOLS = {"vixl_workspace_list", "vixl_document_open", "vixl_document_inspect", "vixl_render_preview", "vixl_job"}
AI_INSTRUCTIONS = (
    "Provider-backed AI editing for Vixl documents in the configured workspace: generate, inpaint, extend, "
    "upscale, remove objects or backgrounds, select subjects/objects, and describe/detect/OCR. Each tool takes "
    "document= (a .vixl path in the workspace) or uses the document opened with vixl_document_open. Results are "
    "saved at once, so the main Vixl server sees them on its next call. Find layers with vixl_document_inspect and "
    "check results with vixl_render_preview. Every tool needs a configured provider (vixl_models_list); if none "
    "is configured, say so instead of retrying."
)


def is_ai_tool(name):
    return name.startswith("vixl_ai_") or name == "vixl_models_list"


def build_server(session, *, schema="full", planner=False, tools="all"):
    """Create the FastMCP server. ``schema='slim'`` advertises only operation type names (fetch
    fields with vixl_operation_schema); ``planner`` exposes the provider-backed planning tool,
    which is redundant when the calling agent plans its own operations. ``tools`` selects a split:
    ``core`` (editing, rendering, export and catalogs), ``ai`` (provider-backed tools plus the
    shared document tools), or ``all``."""
    from mcp.server.fastmcp import FastMCP, Image
    from mcp.server.fastmcp.exceptions import ToolError

    require(schema in ("full", "slim"), "schema must be full or slim")
    require(tools in ("all", "core", "ai", "compact"), "tools must be all, core, ai or compact")
    Operation = Annotated[dict, WithJsonSchema(service_operation_schema(slim=schema == "slim"))]
    server = FastMCP(
        "Vixl AI" if tools == "ai" else "Vixl",
        instructions=AI_INSTRUCTIONS if tools == "ai" else (
            "Edit layered image documents in the configured workspace. START HERE (open-ended briefs default to this path, "
            "not freehand shapes): "
            + ("" if tools == "compact" else "vixl_guide(brief) says what to make and with which tools (icons, characters, scenes, "
               "patterns, mandalas, logos, diagrams, social cards, slides, posters); ")
            + "1) vixl_sizes_list → vixl_document_create(size=…); 2) text work: vixl_layouts_list → layout-apply, filling every "
            "slot it lists (art with no text frame: shape/organic/pathfinder/radial-repeat); 3) type: vixl_fonts → vixl_font_pair "
            "(the bundled font is a proofing fallback); 4) finish with look (glow, soft-shadow, gradient, grain, paper …) and, "
            "when the brief names a style, vixl_styles; 5) vixl_check → fix the 'fix' findings, glance at 'review' → "
            "vixl_render_preview (region= to zoom) → vixl_export_file. Typical loop: vixl_document_create/open → "
            "vixl_operations_apply (atomic batches; dry_run to test; check=true and preview=true return the vixl_check "
            "findings and a small preview in the same call) → vixl_export_file. Use layer IDs or "
            "names from results. Batches accept up to 10,000 operations atomically. Path coordinates are literal local pixels; "
            "use path-fit to scale geometry into its box. vixl_capabilities(topic) lists relevant fields and gotchas. " + COORDINATE_NOTE + " Errors are JSON with error, message, field, "
            "operation_index and suggestions; a batch with several invalid operations lists them all under errors. Paths are relative to the workspace; imports accept a path or "
            "base64 bytes. Several documents can be open: pass document= to address one. When a brief leaves the "
            "look open, vixl_roll a few directions and compare previews. Paint with brushes (vixl_brushes_list), animate "
            "with motion recipes (loops, stagger), character cycles and keyframes (→ vixl_timeline_preview → "
            "vixl_export_timeline), and "
            "export print-ready CMYK PDF/TIFF/JPEG with vixl_export_file. Slides and carousels are pages (page "
            "operation; preview page='all'; export .pdf, .pptx or .html, a self-contained presentation); forms "
            "are field layers (field operation; check form; export_file fillable=true, or values= to fill); hand "
            "drawings are drawing operations (import, clean, vectorize, straighten, fill) checked with check "
            "drawing; a design derived from another is a live link layer, and print "
            "sheets from a CSV are vixl_workflow merge-impose. "
            + ("AI tools need a configured provider." if tools == "all" else
               "Provider-backed AI tools are served separately by vixl mcp --tools ai.")
        ),
    )

    def selected(name):
        if tools == "compact":
            # The compact set stays at 12 tools: job ids are polled through vixl_workflow instead of vixl_job.
            return name in (SHARED_TOOLS - {"vixl_job"}) | {"vixl_document_create", "vixl_operations_apply", "vixl_operation_schema",
                "vixl_workflow", "vixl_workflow_schema", "vixl_export_file", "vixl_import_image", "vixl_import_document"}
        if tools == "all" or name in SHARED_TOOLS:
            return True
        return is_ai_tool(name) == (tools == "ai")

    runtime = Runtime(session, compact_json, ToolError, poll_with_workflow=tools == "compact")
    server.vixl_runtime = runtime

    def tool(fn):
        """Register a tool returning minified JSON, with structured errors. It runs in a worker
        thread with progress, background jobs and retry ids (mcp_runtime.py)."""
        wrapper = runtime.wrap(fn)
        if selected(fn.__name__):
            server.tool(structured_output=False)(wrapper)
        return wrapper

    @tool
    def vixl_resources_list(kind: Literal["palettes", "templates", "guidance"]) -> dict:
        """Discover built-in and user-added design resources without an open document."""
        from .resources import catalog

        return {"kind": kind, "names": sorted(catalog(kind))}

    @tool
    def vixl_workflow_schema() -> dict:
        """Discover production actions and request fields. Read docs/production.md for recipe/job contracts."""
        from .workflows import describe
        return describe()

    @tool
    def vixl_workflow(
        action: str,
        request: dict, document: Document = None,
    ) -> dict | list:
        """Unified workflows: resources, palettes, saved shapes, suites, effects, plugin packs, project groups,
        branch/merge collaboration, production, libraries, jobs, linked-document status (links) and print merge
        (merge-impose). Discover action fields with vixl_workflow_schema.
        Paths stay in workspace. Branch merge and group apply default to dry_run=true.

        Long jobs: submit with start=true, then status. A call that returned {job: job_…} is followed with
        action status/cancel and request {id, wait?}. AI jobs require an explicit configured provider.
        Repairs preserve test suites. Unknown/unmeasurable checks report needs_review.
        """
        from .workflows import dispatch

        if action in ("status", "cancel") and str(request.get("id", "")).startswith("job_"):
            # A call that became a job (see vixl_job); the compact tool set polls it here.
            return runtime.job("result" if action == "status" else action, request["id"],
                               min(float(request.get("wait", 0)), 25))
        result = dispatch(session, action, request, document)
        if action in ("film-preview", "video-sample", "audio-analyze"):
            paths = result.get("images", []) if isinstance(result, dict) else []
            if isinstance(result, dict) and not paths:
                paths = [result.get("output") or result.get("spectrogram")]
            images = []
            for path in paths[:8]:
                if isinstance(path, str) and path.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
                    resolved = session.resolve(path)
                    with PILImage.open(resolved) as source:
                        images.append(Image(data=encode_png(source.convert("RGB"), 524288), format="png"))
            if images:
                return [compact_json(result), *images]
        return result

    @tool
    def vixl_resource_get(kind: Literal["palettes", "templates", "guidance"], name: str) -> dict:
        """Read a named palette, template or guidance text (also vixl_guide(brief=NAME)) before applying it."""
        from .resources import get

        return {"name": name, "value": get(kind, name)}

    @tool
    def vixl_resource_add(
        kind: Literal["palettes", "templates", "guidance"], name: str, value: list | dict | str
    ) -> dict:
        """Register custom JSON design data or plain-text guidance in the user's library."""
        from .resources import register

        return register(kind, name, value)

    @tool
    def vixl_template_create(path: str, name: str, variables: dict | None = None) -> dict:
        """Create and activate an editable document from a named template without overwriting files."""
        from .resources import create_template

        with session._mutex:
            destination = session.resolve(path)
            require(destination.suffix.lower() == ".vixl", "Use a .vixl path in the workspace", field="path")
            session.make_parent(destination)
            with file_lock(str(destination)):
                require(not destination.exists(), "Destination already exists")
                project = create_template(name, variables, limits=session.limits, workspace=session.workspace)
                project.save(destination)
                result = session.open(destination)
                if isinstance(result, dict) and project.state.get("template"):
                    result["template"] = project.state["template"]
                return result

    @tool
    def vixl_import_font(path: str, name: str, document: Document = None) -> dict:
        """Import a workspace TTF/OTF font; use its registered name as font in text operations."""
        from .fonts import import_font

        with session.project(write=True, document=document) as project:
            return import_font(project, session.resolve(path), name)

    @tool
    def vixl_models_list(
        provider: str | None = None, capability: str | None = None, refresh: bool = False
    ) -> dict:
        """Discover authenticated model IDs and supported capabilities; keys stay in server environment variables."""
        from .models import configured, DEFAULTS, CAPABILITIES, refresh as refresh_models

        require(capability is None or capability in CAPABILITIES, "Unknown model capability")
        settings = configured()
        names = [provider] if provider else list(settings)
        result = []
        for name in names:
            config = settings.get(name, DEFAULTS.get(name))
            require(config is not None, "Unknown provider")
            models = refresh_models(name) if refresh or "models" not in config else config["models"]
            result.extend(
                {"provider": name, **item}
                for item in models
                if not capability or capability in item.get("capabilities", [])
            )
        return {"models": result}

    @tool
    def vixl_workspace_list(
        directory: str = ".",
        offset: Annotated[int, Field(ge=0)] = 0,
        limit: Annotated[int, Field(ge=1, le=200)] = 100,
    ) -> dict:
        """List workspace files/directories (paginated) and the open documents."""
        directory_path = session.resolve(directory)
        require(directory_path.is_dir(), "Directory does not exist", field="directory")
        entries = sorted(
            (
                p
                for p in directory_path.iterdir()
                if not p.name.endswith(".lock")
                and not p.name.startswith(".vixl-")
                and p.resolve().is_relative_to(session.workspace)
            ),
            key=lambda p: p.name,
        )
        return {
            "workspace": str(session.workspace),
            **session.open_documents(),
            "entries": [
                {"path": session.relative(p), **({"directory": True} if p.is_dir() else {})}
                for p in entries[offset : offset + limit]
            ],
            "next_offset": offset + limit if offset + limit < len(entries) else None,
        }

    @tool
    def vixl_document_create(
        path: str,
        width: Positive | None = None,
        height: Positive | None = None,
        background: str = "transparent",
        size: Annotated[
            str | None,
            Field(description="Named size instead of width/height: letter, a4, business-card, instagram-portrait, story, youtube-thumbnail, favicon, logo-horizontal … (vixl_sizes_list)"),
        ] = None,
        dpi: Annotated[float | None, Field(ge=36, le=2400)] = None,
        orientation: Literal["portrait", "landscape"] | None = None,
        bleed: Annotated[bool | float, Field(description="Print sizes: true adds standard bleed")] = False,
        seed: int | None = None,
        variety: Literal["low", "medium", "high", "fixed"] | None = None,
        font_pairing: Annotated[
            str | None,
            Field(description="Also install and apply this curated pairing (a vixl_font_pair name, or 'random') as "
                              "the document typography; needs the font cache or network"),
        ] = None,
    ) -> dict:
        """Create and activate a new .vixl file from width/height or a named size (print sizes record dpi,
        bleed, safe area and trim/safe guides). Never overwrites an existing file. font_pairing replaces
        a separate vixl_font_pair call, so heading/body roles resolve to real typefaces, not the proofing fallback."""
        created = session.create(path, width, height, background, size=size, dpi=dpi, orientation=orientation, bleed=bleed, seed=seed, variety=variety)
        if font_pairing:
            from .typefaces import pair_fonts

            try:
                with session.project(write=True, document=path) as project:
                    created["typography"] = pair_fonts(project, font_pairing)
            except VixlError as exc:  # the document exists; say the pairing did not apply instead of hiding it
                created["font_pairing_error"] = str(exc)
        return created

    @tool
    def vixl_document_open(path: str) -> dict:
        """Open and activate an existing .vixl file. Other open documents stay available."""
        return session.open(path)

    @tool
    def vixl_document_close(document: Document = None) -> dict:
        """Close an open document (default: active). Edits are already saved."""
        return session.close(document)

    @tool
    def vixl_document_inspect(
        target: str | None = None, detail: Detail = "compact", document: Document = None
    ) -> dict:
        """Describe the document or one layer. compact: canvas plus key fields per layer with resolved
        [x, y, w, h] bounds; full: every stored field."""
        from .changes import summarize

        with session.project(document=document) as project:
            if detail == "full":
                return project.inspect(target)
            return summarize(project, target)

    @tool
    def vixl_operations_apply(
        operations: Annotated[list[Operation] | None, Field(min_length=1, max_length=Limits().max_operations)] = None,
        dry_run: bool = False,
        detail: ApplyDetail = "brief",
        document: Document = None,
        operations_path: Annotated[
            str | None,
            Field(description="Workspace-relative .json (array) or .jsonl (one operation per line) file to apply "
                              "instead of operations; JSONL errors cite the line number"),
        ] = None,
        check: Annotated[
            bool | str | list[str] | None,
            Field(description="Also run vixl_check on the result: true (default checks) or check names. Lists 'fix' "
                              "findings and those on the layers this batch touched"),
        ] = None,
        preview: Annotated[
            bool | dict | None,
            Field(description="Also return a small preview PNG: true, or {page, region, max_width (512), max_height, time}"),
        ] = None,
    ) -> dict:
        """Apply operations atomically (all or none) and autosave. Give operations inline, or operations_path
        for a large batch kept in a workspace file. brief (default) returns the ID, name and
        resulting bounds of each changed layer plus warnings (off-canvas or overflowing text, ignored fields);
        compact adds the new values of changed fields; full adds before/after snapshots. dry_run validates and
        previews the changes without saving. Omit target to use the active layer; edit-layers changes every
        layer matching a selector in one operation.
        font (text, text-set, rich-text spans, layout-apply, fields) takes a registered font name or a role
        (heading, body); install fonts first with vixl_font_pair or vixl_font_install.
        text-set changes a whole text layer (content, color, size, font; rich-text formatting is kept where it
        still applies); text-style styles a phrase, character range or paragraphs inside it.
        shape/solid/gradient/text add a layer, but with target they edit that existing layer in place
        (keeping its ID), e.g. {type: shape, target: bar, fill: "#6b3f69"}.
        check and preview save the vixl_check and vixl_render_preview round trips (also with dry_run); they are
        skipped, with a note, when the edit itself took more than half the inline time limit."""
        require(operations is not None or operations_path is not None, "Pass operations or operations_path",
                field="operations")
        if not check and not preview:
            return session.apply(operations, dry_run, detail, document, operations_path=operations_path)
        budget = runtime.inline_seconds / 2 if runtime.inline_seconds else None
        result, image = session.apply_reviewed(operations, dry_run, detail, document, operations_path=operations_path,
                                               check=check, preview=preview, budget=budget)
        return result if image is None else [result, Image(data=image, format="png")]

    @tool
    def vixl_operation_schema(types: list[str]) -> dict:
        """Return the exact JSON Schema for the named operation types (fields, enums, requirements)."""
        from .schema import _properties
        from .render import EFFECTS

        require(
            isinstance(types, list) and 0 < len(types) <= 20, "Request 1–20 operation types", field="types"
        )
        variants = {
            v["properties"]["type"]["const"]: v
            for v in operation_schema()["properties"]["operations"]["items"]["oneOf"]
        }
        result = {}
        for kind in types:
            from .normalize import _canonical_type

            canonical = _canonical_type(kind, set(variants))
            if canonical not in variants:
                import difflib

                close = difflib.get_close_matches(canonical, list(_properties()), 3, 0.5)
                result[kind] = {"error": "unknown operation type", "suggestions": close}
                continue
            variant = deepcopy(variants[canonical])
            for field in ("path", "linked"):
                if field != "path" or canonical not in ("text-layout", "shape", "select"):
                    variant["properties"].pop(field, None)
            if canonical == "effect":
                variant["properties"]["name"] = {"enum": sorted(EFFECTS)}
            result[canonical] = variant
        return result

    @tool
    def vixl_render_preview(
        variables: dict | None = None,
        max_width: Annotated[int, Field(ge=1, le=4096)] = 1024,
        max_height: Annotated[int, Field(ge=1, le=4096)] = 1024,
        max_bytes: Annotated[int, Field(ge=65536, le=4194304)] = 1_048_576,
        region: Annotated[
            list[float | str] | None,
            Field(
                description="Zoom to [x, y, width, height] in document pixels or percentages",
                min_length=4,
                max_length=4,
            ),
        ] = None,
        artboard: str | None = None,
        comp: str | None = None,
        time: Annotated[
            float | str | None, Field(description="Timeline frame: ms, '1.5s', '50%' or a marker name")
        ] = None,
        proof: Annotated[bool, Field(description="Soft-proof the CMYK print separation")] = False,
        simulate: Literal["protanopia", "deuteranopia", "tritanopia", "achromatopsia"] | None = None,
        guides: Annotated[bool | list[str] | None, Field(description="Draw guides over the preview: true for all, or guide/grid names")] = None,
        page: Annotated[int | str | None, Field(description="Page number or name; 'all' shows every page on one sheet")] = None,
        values: Annotated[dict | None, Field(description="Form field values to show, by field key")] = None,
        show_fields: Annotated[bool, Field(description="Outline form fields with their keys and tab order")] = False,
        document: Document = None,
    ) -> Image:
        """Return an aspect-preserving PNG capped in dimensions and bytes, rendered at preview resolution.
        region zooms into part of the canvas and may enlarge it up to 8x for detail checks. time previews
        an animation frame; proof shows print (CMYK) color; simulate checks color-blind legibility."""
        return Image(
            data=preview(
                session,
                variables,
                max_width,
                max_height,
                max_bytes,
                artboard,
                comp,
                region,
                document,
                time=time,
                proof=proof,
                simulate=simulate,
                guides=guides,
                page=page,
                values=values,
                show_fields=show_fields,
            ),
            format="png",
        )

    @tool
    def vixl_render_compare(
        before: str = "previous",
        after: str = "head",
        mode: Literal["side-by-side", "diff"] = "side-by-side",
        max_width: Annotated[int, Field(ge=64, le=4096)] = 1024,
        max_height: Annotated[int, Field(ge=64, le=4096)] = 768,
        document: Document = None,
    ) -> list:
        """Compare two revisions (head, previous, head~N, branch, checkpoint or revision ID).
        side-by-side shows before|after; diff highlights changed pixels in red. Also returns the
        changed fraction and changed region in document pixels."""
        from .checks import compare

        with session.project(document=document) as project:
            image, summary = compare(
                project, before, after, max_width=max_width, max_height=max_height, mode=mode
            )
            summary["document"] = session.relative(project.path)
        return [compact_json(summary), Image(data=encode_png(image, 2_097_152), format="png")]

    @tool
    def vixl_check(
        checks: list[Literal["bounds", "overlap", "contrast", "safe_area", "legibility", "blanks", "fonts", "brand", "print", "color_vision", "guides", "alignment",
                             "deck", "title_position", "type_scale", "words", "min_font", "notes", "empty", "form", "drawing", "links", "style",
                             "diagram", "flow", "motion", "character", "captions"]]
        | None = None,
        targets: list[str] | None = None,
        safe_area: Annotated[
            float | str | dict | None,
            Field(description="Inset from every edge: pixels, '5%', or {left, top, right, bottom}"),
        ] = None,
        avoid: Annotated[
            list[list[float | str]] | None,
            Field(description="Reserved zones [x, y, w, h] (pixels or %) that content must not touch"),
        ] = None,
        thumbnail_width: Annotated[int | Literal["auto"] | None, Field(description="judge text at this thumbnail width; 'auto' (default) is 320, null turns the thumbnail test off")] = "auto",
        min_thumbnail_text: Annotated[float, Field(gt=0, le=200)] = 10,
        min_contrast: Annotated[float | None, Field(ge=1, le=21)] = None,
        ink_limit: Annotated[float, Field(ge=100, le=400, description="print check: total ink limit %")] = 300,
        min_ppi: Annotated[float, Field(ge=36, le=2400, description="print check: lowest image resolution")] = 200,
        artboard: str | None = None,
        comp: str | None = None,
        page: Annotated[int | str | None, Field(description="Page to check (default: the active page)")] = None,
        deck: Annotated[dict | None, Field(description="deck checks: {profile: projected|screen|phone, min_font (profile units), thumbnail_width, max_words, pages, include_hidden}")] = None,
        sample: Annotated[str | None, Field(description="form checks: 'worst' (worst-case values) or a workspace CSV of rows")] = None,
        style: Annotated[str | list[str] | None, Field(description="style check: evaluate this style (or list) instead of the document's style tag")] = None,
        document: Document = None,
    ) -> dict:
        """Find design problems without looking: content cut off by the canvas, overlapping text, low WCAG
        text contrast (4.5:1, or 3:1 for 24px+), content outside a safe area or inside reserved zones, and
        text too small at thumbnail width. print (opt-in) checks ink coverage, low-resolution images, tiny
        type in points and backgrounds that stop short of the bleed; color_vision (opt-in) finds text whose
        contrast collapses for color-blind readers; deck checks every page plus title placement, type
        scale, words per page, projected type size and speaker notes; form checks fields (names, overlap, tab
        order, sizes, contrast) and with sample finds values that overflow; style (opt-in) evaluates the document's
        style tag rule by rule. Each issue has a severity (error, warning, info) and an action: fix (needs a design
        change), review (look and decide) or informational (expected, such as a crop marked with layer-intent
        allow_crop); by_action lists the issue indexes under each. Reports only problems."""
        return session.check(
            document=document,
            checks=checks,
            targets=targets,
            safe_area=safe_area,
            avoid=avoid,
            thumbnail_width=thumbnail_width,
            min_thumbnail_text=min_thumbnail_text,
            min_contrast=min_contrast,
            ink_limit=ink_limit,
            min_ppi=min_ppi,
            artboard=artboard,
            comp=comp,
            page=page,
            deck=deck,
            sample=sample if sample in (None, "worst") else str(session.resolve(sample)),
            style=style,
        )

    @tool
    def vixl_import_document(format: Literal["svg", "pdf"], path: str | None = None,
                            data_base64: str | None = None, name: str = "import", page: int = 1,
                            dpi: int = 144, document: Document = None, svg_mode: Literal["editable", "appearance", "auto"] = "editable") -> dict:
        """Import editable SVG paths, or use svg_mode=appearance/auto for complex static SVG
        rendered with its original source retained. PDF imports one raster page. External/active SVG is rejected."""
        from .imports import import_document
        require((path is None) != (data_base64 is None), "Provide exactly one of path or data_base64")
        limit = session.limits.max_asset_bytes
        data = read_bounded(session.resolve(path), limit) if path else decode_upload(data_base64, limit)
        with session.project(write=True, document=document) as project:
            return import_document(project, data, format, name, page, dpi, svg_mode)

    @tool
    def vixl_review_notes(action: Literal["list", "add", "resolve"] = "list", text: str | None = None,
                          note_id: str | None = None, document: Document = None) -> dict:
        """Read human feedback left in vixl view; add a note or resolve one by ID."""
        from .review import notes
        with session.project(document=document) as project:
            return notes(project.path, action, text=text, note_id=note_id)

    @tool
    def vixl_import_image(
        path: str | None = None,
        data_base64: Annotated[
            str | None, Field(description="Image bytes as base64 or a data: URL, when no file path exists")
        ] = None,
        name: str = "image",
        document: Document = None,
    ) -> dict:
        """Embed an image as a new layer from a workspace file or from base64 bytes. Returns the layer
        id, size and bounds. PNG/JPEG/WebP keep their original bytes."""
        require((path is None) != (data_base64 is None), "Provide exactly one of path or data_base64")
        limit = session.limits.max_asset_bytes
        data = read_bounded(session.resolve(path), limit) if path else decode_upload(data_base64, limit)
        return session.import_image(data, name, document)

    @tool
    def vixl_export_file(
        path: str,
        quality: Annotated[int, Field(ge=1, le=100)] | None = None,
        scale: Annotated[float, Field(ge=0.01, le=16)] = 1,
        profile: str | None = None,
        variables: dict | None = None,
        background: str = "white",
        overwrite: bool = False,
        sampling: Literal["smooth", "nearest"] = "smooth",
        svg_policy: Literal["appearance", "strict"] = "appearance",
        artboard: str | None = None,
        comp: str | None = None,
        color_space: Literal["rgb", "cmyk"] = "rgb",
        icc_profile: Annotated[str | None, Field(description="Workspace path of a CMYK .icc/.icm profile")] = None,
        intent: Literal["perceptual", "relative", "saturation", "absolute"] = "relative",
        black_generation: Annotated[float, Field(ge=0, le=1)] = 1.0,
        ink_limit: Annotated[float | None, Field(ge=100, le=400, description="Total ink limit, percent")] = None,
        proof: bool = False,
        simulate: Literal["protanopia", "deuteranopia", "tritanopia", "achromatopsia"] | None = None,
        dpi: Annotated[float | None, Field(ge=36, le=2400)] = None,
        icon_sizes: list[int] | None = None,
        time: float | str | None = None,
        page: Annotated[int | str | None, Field(description="One page of a multi-page document")] = None,
        pages: Annotated[list[int | str] | str | None, Field(description="PDF/PPTX pages: [1, 3] or '1-3,intro'")] = None,
        pdf_content: Annotated[Literal["vector", "raster"] | None, Field(
            description="PDF pages as vector text and shapes (the default, RGB or CMYK) or as one image per page; "
                        "the result's content and content_reason say which was written")] = None,
        fillable: Annotated[bool, Field(description="PDF with fillable form fields")] = False,
        values: Annotated[dict | None, Field(description="Form field values by key: a filled copy (nothing is saved)")] = None,
        fill_mode: Literal["flatten", "editable"] = "flatten",
        alpha: Annotated[Literal["auto", "keep", "flatten"], Field(
            description="PNG/WEBP/TIFF/AVIF channels: auto writes RGB when the image is fully opaque, keep always "
                        "RGBA, flatten composites onto background and writes RGB")] = "auto",
        presenter: Annotated[bool | dict | None, Field(
            description=".html of a multi-page document is a self-contained slide presentation; false writes one "
                        "static image instead, true presents any document. Options: {theme: dark|light|auto, "
                        "slide_images: svg|png, notes: bool, start: slide number or page name, title}")] = None,
        title: Annotated[str | None, Field(description="PDF document title; default the page's title layer, then the file name")] = None,
        max_bytes: Annotated[int | None, Field(ge=1, description="Size budget for a raster file: a warning (never a failure) when the file is larger")] = None,
        document: Document = None,
    ) -> dict:
        """Export to a workspace file, format from extension (PNG/JPEG/WEBP/TIFF/AVIF/SVG/PDF/ICO/PPTX/PSD), full
        size by default. color_space=cmyk separates JPEG/TIFF/PDF for print (with an ICC profile for press
        accuracy, else device-naive GCR with black_generation and ink_limit); dpi defaults to the canvas
        dpi (a multi-page screen document is a 7.5 in tall slide, as in PPTX; dpi sizes both). SVG policy strict
        rejects any embedded raster fallback. time exports one timeline frame. PDF is vector by default, CMYK
        too: real text, vector shapes and colours in DeviceCMYK, with images only for effects and the like
        (see raster_fallbacks). A multi-page document exports every shown page to PDF or PowerPoint (editable
        slides with speaker notes; its warnings name fonts to install) or HTML (a self-contained
        presentation: keyboard, overview, transitions, speaker view; pages= picks pages). fillable writes PDF form fields; values
        fills them (flatten draws them into the artwork, editable prefills a fillable PDF). PNG and other alpha
        formats are RGB when the image is opaque;
        alpha=flatten forces RGB on background, alpha=keep forces RGBA. Print-size PDFs measure exactly trim +
        bleed with TrimBox and BleedBox. PSD is a layered handoff file: one pixel layer per layer (effects
        included), groups as layer groups, text as pixels (warnings say so). Returns file metadata, never image bytes."""
        profile_bytes = read_bounded(session.resolve(icc_profile), 16 * 1024 * 1024) if icc_profile else None
        return export_file(
            session,
            path,
            overwrite,
            document,
            quality=quality,
            scale=scale,
            profile=profile,
            variables=variables,
            background=background,
            sampling=sampling,
            svg_policy=svg_policy,
            artboard=artboard,
            comp=comp,
            color_space=color_space,
            icc_profile=profile_bytes,
            intent=intent,
            black_generation=black_generation,
            ink_limit=ink_limit,
            proof=proof,
            simulate=simulate,
            dpi=dpi,
            icon_sizes=icon_sizes,
            time=time,
            page=page,
            pages=pages,
            pdf_content=pdf_content,
            fillable=fillable,
            values=values,
            fill_mode=fill_mode,
            alpha=alpha,
            presenter=presenter,
            title=title,
            max_bytes=max_bytes,
        )

    @tool
    def vixl_export_batch(
        targets: Annotated[
            list[dict],
            Field(
                min_length=1,
                max_length=64,
                description="Outputs to write: {path, document?, overwrite?, ...any vixl_export_file option} "
                "(scale, profile, artboard, page, quality, color_space, …); one entry per file",
            ),
        ],
        defaults: Annotated[dict | None, Field(description="Options shared by every target; a target's own win")] = None,
        overwrite: bool = False,
        stop_on_error: bool = False,
        document: Document = None,
    ) -> dict:
        """Export several files in one call: several sizes, formats or artboards of one document, or
        several documents. Every target is checked first (unknown options, duplicate or existing paths), then
        written in order; each reports its own file metadata or error. Missing directories are created."""
        from .export_batch import export_batch

        return export_batch(session, export_file, targets, defaults, overwrite, stop_on_error, document)

    @tool
    def vixl_adapt_layout(
        sizes: Annotated[
            list[str | dict],
            Field(
                min_length=1,
                max_length=16,
                description="Target sizes: a named size ('story', 'a4'), 'WIDTHxHEIGHT', or {size | width+height, "
                "orientation?, dpi?, bleed?, name?}",
            ),
        ],
        directory: str = ".",
        name: Annotated[str, Field(description="File name template for each adapted copy: {name} {size} {index}")] = "{name}-{size}",
        options: Annotated[dict | None, Field(description="adapt-layout settings for every size: scale, anchors, where, text")] = None,
        formats: Annotated[list[str] | None, Field(description="Also export each copy, e.g. ['png']")] = None,
        overwrite: bool = False,
        report: Literal["summary", "layers"] = "summary",
        document: Document = None,
    ) -> dict:
        """Adapt one document to several sizes in one call (a campaign: square, story, banner, print). Each size is
        a saved copy re-laid out by the adapt-layout operation (sizes scale, each layer keeps its anchor to an edge
        or its relative place, backgrounds stretch, photos cover) and optionally exported. Returns per size the
        new file, canvas, scale, how many layers moved and any warnings; report='layers' lists where each layer
        went. The source document is not changed; refine a copy with vixl_operations_apply."""
        from .adapt import adapt_copies

        return adapt_copies(session, export_file, sizes, directory, name, options, document, overwrite, formats, report)

    @tool
    def vixl_job(
        action: Literal["status", "result", "cancel", "list"] = "status",
        id: str | None = None,
        wait: Annotated[float, Field(ge=0, le=50, description="Seconds to wait for the job to finish")] = 0,
    ) -> dict:
        """Follow a long call. A call still running after about 40 s (VIXL_MCP_INLINE_SECONDS), or one sent
        with as_job=true, returns {status: running, job: ID} while it carries on. status reports
        progress (wait= blocks until it ends or the time is up), result returns the call's normal result, cancel
        stops a queued job or a running one at its next checkpoint, list shows recent jobs. Also accepts the ID
        of a durable workflow job. A call that timed out on your side is in list: read its result instead
        of sending it again (or retry with the same request_id)."""
        return runtime.job(action, id, wait)

    @tool
    def vixl_spatial(
        target: str | None = None, targets: list[str | dict] | None = None, to: str | None = None,
        mode: Literal["relations", "canvas", "matrix", "grid", "guides", "composition", "hit", "free", "snap", "all"] = "all",
        bounds: Literal["box", "ink"] = "box", tolerance: float = 1,
        point: list[float] | None = None, region: list[float] | None = None, grid: str | None = None,
        describe: bool = False, include_hidden: bool = False,
        limit: Annotated[int, Field(ge=1, le=200)] = 20,
        artboard: str | None = None, page: str | int | None = None,
        safe_area: float | list[float] | dict | None = None, document: Document = None,
    ) -> dict:
        """Canvas-space relationships, gaps, alignment, margins, grid/guide offsets, hit tests, empty regions and snap operations.
        Targets accept IDs, names, globs and groups; choose box or ink bounds. Results respect parent transforms."""
        with session.project(document=document) as project:
            return project.spatial(target=target, targets=targets, to=to, mode=mode, bounds=bounds,
                                   tolerance=tolerance, point=point, region=region, grid=grid, describe=describe,
                                   include_hidden=include_hidden, limit=limit, artboard=artboard, page=page, safe_area=safe_area)

    @tool
    def vixl_measure_spacing(
        targets: list[str] | None = None,
        axis: Literal["horizontal", "vertical"] = "vertical",
        around: str | None = None,
        before: str | None = None,
        after: str | None = None,
        expected: float | None = None,
        tolerance: Annotated[float, Field(ge=0)] = 1,
        artboard: str | None = None,
        comp: str | None = None,
        document: Document = None,
    ) -> dict:
        """Pass/fail for intended equal gaps (or balance before/after an object) within a tolerance: exact gaps,
        overlap and spread. Open-ended layout questions (relations, margins, free space): vixl_spatial."""
        return session.measure_spacing(
            document=document,
            targets=targets,
            axis=axis,
            around=around,
            before=before,
            after=after,
            expected=expected,
            tolerance=tolerance,
            artboard=artboard,
            comp=comp,
        )

    @tool
    def vixl_pixels_inspect(target: str | None = None, document: Document = None) -> dict:
        """Inspect a pixel layer as compact character rows and palette colors, without image bytes."""
        with session.project(document=document) as project:
            return project.inspect_pixels(target)

    @tool
    def vixl_animation_inspect(document: Document = None) -> dict:
        """Frame-by-frame animation (frame-save, animation-set; sprites, pixel art): saved frame names, sizes and
        durations and the named animations (frame order, timing, loop). Keyframed motion: vixl_timeline_inspect."""
        with session.project(document=document) as project:
            return project.inspect_animation()

    @tool
    def vixl_animation_preview(
        name: str,
        scale: Annotated[float, Field(ge=0.05, le=8)] = 1,
        sampling: Literal["nearest", "smooth"] = "nearest",
        document: Document = None,
    ) -> Image:
        """Preview one saved frame (frame-save) by name (default: native size). Nearest needs an integer scale and
        keeps pixel art crisp; smooth re-renders at any scale. Keyframed motion: vixl_timeline_preview."""
        with session.project(document=document) as project:
            image = project.render_frame(name, int(scale) if float(scale).is_integer() else scale, sampling)
            stream = BytesIO()
            image.save(stream, format="PNG")
            require(len(stream.getvalue()) <= 4_194_304, "Frame preview exceeds 4 MiB; use a smaller scale")
            return Image(data=stream.getvalue(), format="png")

    @tool
    def vixl_export_character(target: str, output: str, document: Document = None) -> dict:
        """Save one reusable character and its assets to a new .vixl library file. Load with character-load source=output."""
        from .characters import export_character

        destination = session.resolve(output)
        require(destination.suffix.lower() == ".vixl", "Choose a .vixl character library file", field="output")
        require(not destination.exists(), "Character output already exists", field="output")
        session.make_parent(destination)
        with session.project(document=document) as project:
            report = export_character(project, target, destination)
        return {**report, "output": session.relative(destination)}

    @tool
    def vixl_export_audio(path: str, document: Document = None) -> dict:
        """Mix the document's imported and synthesized audio tracks to a new WAV; reports clipped samples."""
        from .audio import export_audio

        destination = session.resolve(path)
        require(destination.suffix.lower() == ".wav", "Choose a .wav output", field="path")
        session.make_parent(destination)
        with session.project(document=document) as project:
            report = export_audio(project, destination)
        return {**report, "output": session.relative(destination)}

    @tool
    def vixl_export_animation(
        path: str,
        format: Literal["gif", "apng", "webp", "mp4", "webm", "sheet"] | None = None,
        animation: str | None = None,
        scale: Annotated[float, Field(ge=0.05, le=32)] = 1,
        sampling: Literal["nearest", "smooth"] = "nearest",
        colors: Annotated[int, Field(ge=2, le=256)] = 256,
        quality: Annotated[int, Field(ge=1, le=100)] = 90,
        columns: Positive | None = None,
        document: Document = None,
        overwrite: bool = False,
        dither: Annotated[Literal["auto", "none", "ordered", "floyd"], Field(description="GIF dithering against one shared palette (no shimmer between frames): auto picks ordered for gradients")] = "auto",
        max_bytes: Annotated[int | None, Field(ge=1, description="Soft size target: the result warns (and suggests MP4/WebP) when the file is larger")] = None,
    ) -> dict:
        """Write saved frames as GIF, APNG, animated WebP, MP4/WebM (needs ffmpeg) or a PNG sprite sheet plus
        JSON timing metadata in the workspace. Format follows the extension. animation=NAME exports one named
        animation (a subset of the saved frames with its own order, timing and loop; define it with the
        animation-set operation, see vixl_animation_inspect); omit it to export every saved frame in saved
        order. A sheet holds every saved frame (or the animation's) and its JSON lists the named animations.
        Refuses existing files unless overwrite=true. sampling="nearest" (integer scale 1–32) keeps pixel art crisp; "smooth"
        re-renders at any scale 0.05–32 for illustrations. colors caps the GIF palette; quality applies to
        MP4/WebM and smooth WebP (nearest WebP is lossless)."""
        with session.project(document=document) as project:
            destination = session.resolve(path)
            result = project.export_animation(
                destination,
                format=format,
                animation=animation,
                scale=int(scale) if float(scale).is_integer() else scale,
                sampling=sampling,
                colors=colors,
                quality=quality,
                columns=columns,
                overwrite=overwrite,
                dither=dither,
                max_bytes=max_bytes,
            )
            result["output"] = session.relative(destination)
            if "metadata" in result:
                result["metadata"] = session.relative(destination.with_suffix(".json"))
            return result

    @tool
    def vixl_sizes_list(
        category: str | None = None, search: str | None = None
    ) -> dict:
        """Named document sizes: print (letter, a4, business-card, posters, in/mm with dpi, bleed and safe
        area), social, web, ads, email, video, slides, screens, app-store, icons, logos and game. Use a name
        with vixl_document_create(size=...) or the canvas operation's size field."""
        from .sizes import catalog

        return catalog(category, search)

    @tool
    def vixl_color(
        action: Literal["info", "convert", "harmony", "scale", "mix", "contrast", "names", "natural"],
        colors: Annotated[list[str], Field(min_length=1, max_length=16)],
        to: Literal["hex", "rgb", "hsl", "hsv", "hwb", "cmyk", "lab", "lch", "oklab", "oklch", "css"] | None = None,
        scheme: str = "complementary",
        count: int | None = None,
        amount: Annotated[float, Field(ge=0, le=1)] = 0.5,
        space: str = "oklab",
    ) -> dict:
        """Color language tools. info: every representation (hex, rgb, hsl, oklch, lab, cmyk), nearest names,
        WCAG contrast vs white/black. convert: one space. harmony: complementary, analogous, triadic,
        split-complementary, tetradic, square, monochromatic, tints, shades, tones. scale: 50–950 ramp. mix:
        two colors. contrast: WCAG ratio and AA/AAA. names: search about 1,040 color names. Any value accepts
        names, hex, rgb/hsl/hwb/lab/lch/oklab/oklch/cmyk/kelvin()/color(display-p3 …)/color-mix() and
        modifiers such as lighten(navy, 20%)."""
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

    @tool
    def vixl_layouts_list(name: str | None = None) -> dict:
        """Principled layout scaffolds (hero-statement, editorial-grid, rule-of-thirds, golden-section,
        z-pattern, logo-horizontal, app-icon, story-vertical …) with the principles each encodes and the
        slots each one needs. Apply with operation {type: layout-apply, name, <slots>, seed (int or
        'random'), palette, mode, type_scale, density, align, accent, unfilled}. Fill every slot: unfilled
        slots render as [Label] blanks that vixl_check rejects, and a slot the layout does not use is an
        error. Unspecified choices are rolled from the seed. Layouts produce editable layers, role swatches
        (@background @ink @accent …), a type scale and guides, and use the document typography. Pass name
        for one layout's principles and each slot's meaning. Layouts are text compositions; for icons, characters, scenes
        and patterns call vixl_guide. An unfilled image slot gets next_steps in the layout-apply result (import, resource,
        draw, AI)."""
        from .layouts import LAYOUTS, catalog, describe

        if name:
            require(name in LAYOUTS, f"Unknown layout {name!r}", field="name")
            return {"name": name, **describe(name), "options": catalog()["options"]}
        return catalog()

    @tool
    def vixl_capabilities(topic: str | None = None, fields: bool = False) -> dict:
        """Field-level reference for a topic (text, drawing, animation, film, layout, color, export or any words such
        as 'loop'): matching operations (fields=true adds their fields), workflows, gotchas, limits and guidance names.
        What to make and the approach: vixl_guide."""
        from .capabilities import lookup

        return lookup(topic, fields=fields)

    @tool
    def vixl_guide(
        brief: Annotated[str | None, Field(description="A kind of work (icon, character, scene, pattern, mandala, logo, diagram, "
                                                      "animation, poster …), a free-text brief such as 'a looping mascot card', "
                                                      "a guidance name (natural-motion, looping-motion, character-rigging, "
                                                      "imperfection …), 'operations' or 'looks'")] = None,
        seed: int | None = None,
        variety: Literal["low", "medium", "high", "fixed"] | None = None,
    ) -> dict:
        """What to make and how. No brief: the start-here recipe, every kind of work and every guidance name. A kind or
        free-text brief: the approach, the operations, layouts, looks and styles that suit it, the guidance to read and a
        working example. A guidance name returns that guidance text. brief=operations lists every operation by purpose;
        brief=looks lists the finishing looks. Use it before improvising: layouts are text compositions, so non-poster
        work starts here. Field-level detail: vixl_capabilities."""
        from .briefs import guide

        return guide(brief, seed=seed, variety=variety, workspace=session.workspace)

    @tool
    def vixl_styles(
        action: Literal["list", "get", "apply", "check"] = "list",
        name: Annotated[str | None, Field(description="Style name (get, apply) or style to check against (check; default the document's tag)")] = None,
        query: Annotated[str | None, Field(description="list: words to find in names, summaries, keywords and uses")] = None,
        palette: Annotated[bool, Field(description="apply: also define and apply the style's first palette")] = False,
        document: Document = None,
    ) -> dict:
        """Design style catalog (swiss, brutalist, neo-brutalist, minimalist, scandinavian, bauhaus, art-deco,
        mid-century-modern, memphis, retro-futurism, vaporwave, y2k, editorial, corporate-flat, material, glassmorphism,
        grunge-zine, japanese-minimal, vintage-letterpress, hand-drawn, maximalist, cyberpunk, kawaii, line-art, risograph,
        data-viz, art-nouveau, pixel-art). list searches them; get returns principles, palettes, type, layout, imagery,
        do/don't and the premade checks; apply tags the document (style-set), stores the brief as design guidance and
        optionally applies the palette; check evaluates the style's rules on the document (same as vixl_check
        checks=['style'])."""
        from . import styles

        if action == "list":
            return styles.listing(query)
        if action == "check":
            return session.check(document=document, checks=["style"], style=name)
        require(name, f"{action} needs a style name (vixl_styles lists them)", field="name")
        if action == "get":
            return styles.describe(name)
        return session.apply(styles.apply_operations(name, palette=palette), False, "compact", document)

    @tool
    def vixl_fonts(
        view: Literal["fonts", "font", "pairings", "pairing", "principles"] = "pairings",
        family: str | None = None,
        pairing: str | None = None,
        category: str | None = None,
        role: str | None = None,
        mood: str | None = None,
        best_for: str | None = None,
    ) -> dict:
        """Researched typeface catalog (open-licensed Google Fonts with classification, x-height, contrast,
        mood and roles), curated heading/body pairings with the reason each works, and the pairing
        principles guide. view=font needs family; view=pairing needs pairing (why it works). Nothing is downloaded; install with vixl_font_pair or
        vixl_font_install. The bundled fallback font is for proofing only."""
        from . import typefaces

        if view == "fonts":
            return typefaces.list_fonts(category, role, mood)
        if view == "font":
            require(family, "view=font needs family", field="family")
            return typefaces.show_font(family)
        if view == "principles":
            return {"principles": typefaces.principles()}
        if view == "pairing":
            require(pairing, "view=pairing needs pairing", field="pairing")
            return typefaces.get_pairing(pairing)
        return typefaces.list_pairings(mood, best_for, family)

    @tool
    def vixl_font_pair(
        pairing: str = "random",
        seed: int | None = None,
        mood: str | None = None,
        best_for: str | None = None,
        document: Document = None,
    ) -> dict:
        """Download (or reuse from cache), embed and register a curated pairing's heading and body fonts and
        make them the document typography that layouts use by default. pairing='random' rolls one among
        those matching mood/best_for (seed reproduces it). The result's origin (cache, download or mixed) and
        each font's source (download URL, cache file, VIXL_FONT_CACHE) and embedded file show where they came from;
        the bundled fallback is never substituted for a failed download."""
        from .typefaces import pair_fonts

        with session.project(write=True, document=document) as project:
            return pair_fonts(project, pairing, seed=seed, mood=mood, best_for=best_for)

    @tool
    def vixl_font_install(
        family: str,
        weight: Annotated[int, Field(ge=100, le=900)] = 400,
        italic: bool = False,
        name: str | None = None,
        role: Literal["heading", "body"] | None = None,
        document: Document = None,
    ) -> dict:
        """Download one style of any Google Fonts family, embed and register it (default name
        family-weight); role makes it the document's heading or body font. The result's source says whether
        it came from the cache (cache_file, VIXL_FONT_CACHE) or a download (url), and file the embedded asset."""
        from .typefaces import install_font

        with session.project(write=True, document=document) as project:
            return install_font(project, family, weight, italic, name, role)

    @tool
    def vixl_roll(
        purpose: str | None = None,
        mood: str | None = None,
        seed: int | None = None,
        variety: Literal["low", "medium", "high", "fixed"] | None = None,
        locks: dict | None = None,
        apply: bool = False,
        slots: dict | None = None,
        unfilled: Literal["omit", "blank"] | None = None,
        document: Document = None,
    ) -> dict:
        """Roll a coherent direction honoring workspace brand.json. apply=true installs fonts and
        applies the layout in one undo step; slots fills its content (e.g. {title: Launch}).
        locks fixes choices such as palette or layout. unfilled: slots you did not fill are left out
        (omit, the default when slots is given) so the result passes vixl_check, or shown as [Label]
        placeholders to fill (blank, the default without slots). The result lists what is missing."""
        from .typefaces import roll_document
        if document or session.path or apply:
            with session.project(write=apply, document=document) as project:
                return roll_document(project, seed=seed, purpose=purpose, mood=mood, locks=locks,
                                     apply=apply, slots=slots, unfilled=unfilled, variety=variety)
        return roll_document(workspace=session.workspace, seed=seed, purpose=purpose, mood=mood, locks=locks, variety=variety)

    @tool
    def vixl_brushes_list() -> dict:
        """Built-in brushes (round, soft-round, airbrush, pencil, ink, fineliner, brush-pen, marker,
        highlighter, calligraphy, chalk, charcoal, crayon, watercolor, dry-brush, spray, splatter) and their
        settings. Paint with operation {type: paint, brush, points: [[x, y, pressure?], …] | path: 'M… C…',
        size, color}; strokes stay editable on paint layers."""
        from .brushes import catalog

        return catalog()

    @tool
    def vixl_timeline_inspect(
        document: Document = None, detail: Literal["summary", "full"] = "summary",
        targets: list[str] | None = None, properties: list[str] | None = None,
        start: float | str | None = None, end: float | str | None = None,
        offset: Annotated[int, Field(ge=0)] = 0, limit: Annotated[int, Field(ge=1, le=200)] = 50,
        key_offset: Annotated[int, Field(ge=0)] = 0, key_limit: Annotated[int, Field(ge=1, le=200)] = 50,
    ) -> dict:
        """Keyframed motion (keyframe, motion, animate, character-cycle): the timeline's tracks per layer and property,
        bounded; full adds paginated keys. Filter by target/property globs and time range. Saved frames:
        vixl_animation_inspect."""
        from .diagnostics import timeline_report

        with session.project(document=document) as project:
            return timeline_report(project, detail=detail, targets=targets, properties=properties,
                                   start=start, end=end, offset=offset, limit=limit,
                                   key_offset=key_offset, key_limit=key_limit)

    @tool
    def vixl_timeline_preview(
        time: Annotated[float | str | None, Field(description="One frame: ms, '1.5s', '50%' or marker")] = None,
        count: Annotated[int, Field(ge=2, le=48, description="Frames in the contact sheet when time is omitted")] = 8,
        columns: Annotated[int | None, Field(ge=1, le=12)] = None,
        max_width: Annotated[int, Field(ge=64, le=4096)] = 1600,
        document: Document = None,
        times: Annotated[list[float | str] | None, Field(max_length=48, description="Exact frames for the contact sheet: ms, '1.5s', '50%' or markers")] = None,
        thumbnail: Annotated[int | None, Field(ge=32, le=1600, description="Phone-size strip: poster (frame 0), middle and last frame side by side, each this many px wide (e.g. 360)")] = None,
    ) -> Image:
        """Check motion without exporting: one frame at time, or a labelled contact sheet of evenly
        spaced frames (count) or chosen frames (times). Frame 0 is labelled "poster", the frame many apps
        show alone. thumbnail=360 shows poster, middle and last frame at phone width to check how the
        card reads small."""
        from .timeline import contact_sheet

        with session.project(document=document) as project:
            if time is not None:
                data = preview(session, None, max_width, max_width, 2_097_152, None, None, None, document, time=time)
                return Image(data=data, format="png")
            sheet = contact_sheet(project, count, columns, max_width, times=times, thumbnail=thumbnail)
        return Image(data=encode_png(sheet, 4_194_304), format="png")

    @tool
    def vixl_export_timeline(
        path: str,
        format: Literal["gif", "apng", "webp", "sheet", "frames", "mp4", "webm"] | None = None,
        fps: Annotated[float | None, Field(ge=1, le=60)] = None,
        scale: Annotated[float, Field(ge=0.05, le=16)] = 1.0,
        start: float | str | None = None,
        end: float | str | None = None,
        background: str | None = None,
        columns: Positive | None = None,
        quality: Annotated[int, Field(ge=1, le=100)] = 90,
        colors: Annotated[int, Field(ge=2, le=256)] = 256,
        overwrite: bool = False,
        document: Document = None,
        dither: Annotated[Literal["auto", "none", "ordered", "floyd"], Field(description="GIF dithering against one shared palette (stable between frames): auto picks ordered when the frames hold gradients")] = "auto",
        max_bytes: Annotated[int | None, Field(ge=1, description="Soft size target: the result warns, and suggests MP4/WebP, when the file is larger")] = None,
        poster: Annotated[float | str | None, Field(description="GIF/WebP/APNG: time, marker, percent or 'end' whose frame comes first (many apps show only frame 0); the loop stays seamless")] = None,
    ) -> dict:
        """Write the keyframe timeline as GIF, APNG, animated WebP, sprite sheet (+JSON), PNG-sequence ZIP,
        or MP4/WebM (needs ffmpeg). Format follows the extension. Frames render crisply at scale (0.05–16,
        within the pixel budget). colors (GIF palette 2–256) plus lower fps/scale shrink GIFs; results report
        bytes and warn above 1 MB or max_bytes, and suggest MP4/WebP for big or gradient-heavy GIFs. dither
        smooths GIF gradients. poster rotates the frames so a chosen moment (e.g. 'end') comes first; the
        result warns when that first frame is empty. Results report the frames and size actually written."""
        from .timeline import export_timeline

        with session.project(document=document) as project:
            destination = session.resolve(path)
            result = export_timeline(
                project,
                destination,
                format=format,
                fps=int(fps) if fps and float(fps).is_integer() else fps,
                scale=scale,
                start=start,
                end=end,
                background=background,
                columns=columns,
                quality=quality,
                colors=colors,
                overwrite=overwrite,
                dither=dither,
                max_bytes=max_bytes,
                poster=poster,
                progress=calls.progress_dict,
                cancelled=calls.cancelled,
            )
            result["output"] = session.relative(destination)
            if "metadata" in result:
                result["metadata"] = session.relative(destination.with_suffix(".json"))
            return result

    @tool
    def vixl_export_icons(
        directory: str,
        icon_set: Literal["web", "apple", "android", "windows", "all"] = "web",
        sampling: Literal["smooth", "nearest"] = "smooth",
        document: Document = None,
    ) -> dict:
        """Render once and write a standard icon set into a workspace folder: web (favicon.ico, 16/32/48,
        apple-touch-icon, android-chrome 192/512, site.webmanifest), apple, android, windows or all."""
        from .exports import export_icons

        with session.project(document=document) as project:
            destination = session.resolve(directory)
            result = export_icons(project, destination, icon_set=icon_set, sampling=sampling)
            result["directory"] = session.relative(destination)
            return result

    @tool
    def vixl_measure(
        point: list[int] | None = None,
        region: list[int] | None = None,
        foreground: str | None = None,
        target: str | None = None,
        histogram: Literal["summary", "full", "none"] = "summary",
        artboard: str | None = None,
        comp: str | None = None,
        document: Document = None,
    ) -> dict:
        """Read RGBA samples, alpha-weighted averages, channel statistics and rendered layer contrast.
        histogram=summary returns percentiles; full returns 256 bins per channel."""
        return session.measure(
            document=document,
            point=point,
            region=region,
            foreground=foreground,
            target=target,
            histogram=histogram,
            artboard=artboard,
            comp=comp,
        )

    @tool
    def vixl_validate(
        profile: str | None = None, rules: list[str] | None = None, document: Document = None,
        detail: Literal["summary", "full"] = "summary", targets: list[str] | None = None,
        severity: Literal["error", "warning", "info"] | None = None,
        suppress: list[str] | None = None, offset: Annotated[int, Field(ge=0)] = 0,
        limit: Annotated[int, Field(ge=1, le=200)] = 50,
    ) -> dict:
        """Rule-based validation against a profile or named rules (document structure and saved suites), bounded;
        full includes passes. For rendered design problems (overlap, contrast, cut-off text) use vixl_check.
        Filters preserve overall validity; suppress omits rules. Mark intentional bleed with layer-intent allow_crop
        or role background/decoration."""
        from .diagnostics import validation_report

        report = session.validate(profile, rules, document, suppress=suppress)
        return validation_report(report, detail=detail, targets=targets, severity=severity, offset=offset, limit=limit)

    @tool
    def vixl_history(
        action: Literal[
            "list", "undo", "redo", "branch", "checkpoint", "checkout", "begin", "commit", "rollback"
        ] = "list",
        ref: str | None = None,
        count: Positive = 1,
        offset: Annotated[int, Field(ge=0)] = 0,
        limit: Annotated[int, Field(ge=1, le=100)] = 20,
        document: Document = None,
    ) -> dict:
        """Navigate history. list returns newest-first revision summaries (paginated); other actions
        return the current head. Old revisions are squashed automatically and never block edits."""
        result = session.history(action, ref, count, document)
        nodes = result.pop("nodes")
        if action == "list":
            newest = list(reversed(nodes))
            result["total"] = len(nodes)
            result["nodes"] = [
                {
                    "id": node["id"],
                    "parent": node["parent"],
                    "label": node.get("label"),
                    "operations": [op.get("type") for op in node["operations"]][:10],
                    **({"squashed": True} if node.get("squashed") else {}),
                }
                for node in newest[offset : offset + limit]
            ]
            result["next_offset"] = offset + limit if offset + limit < len(nodes) else None
        return result

    @tool
    def vixl_ai_generate(
        prompt: str,
        mode: Literal["generate", "inpaint", "img2img"] = "generate",
        width: Positive | None = None,
        height: Positive | None = None,
        seed: int | None = None,
        name: str = "generated",
        provider: str | None = None,
        model: str | None = None,
        negative_prompt: str | None = None,
        strength: Annotated[float, Field(ge=0, le=1)] = 0.75,
        document: Document = None,
    ) -> dict:
        """Generate an image layer. Defaults to canvas size; supply both width/height together.
        inpaint uses the current selection; img2img uses the canvas. Both must match canvas size."""
        require((width is None) == (height is None), "Supply both width and height, or neither")
        return typed_ai(
            session,
            "generate",
            document=document,
            prompt=prompt,
            mode=mode,
            size=f"{width}x{height}" if width is not None else None,
            seed=seed,
            name=name,
            provider=provider,
            model=model,
            negative_prompt=negative_prompt,
            strength=strength,
        )

    @tool
    def vixl_ai_remove(
        name: str = "removed-object", provider: str | None = None, document: Document = None
    ) -> dict:
        """Inpaint the selected object using a provider; insert a masked editable layer."""
        return typed_ai(session, "ai", ["remove"], document=document, name=name, provider=provider)

    @tool
    def vixl_ai_content_aware_fill(
        prompt: str | None = None,
        name: str = "filled-region",
        provider: str | None = None,
        document: Document = None,
    ) -> dict:
        """Fill the current selection using a configured provider, preserving pixels outside it."""
        return typed_ai(
            session,
            "ai",
            ["content-aware-fill"],
            document=document,
            prompt=prompt,
            name=name,
            provider=provider,
        )

    @tool
    def vixl_ai_select_subject(provider: str | None = None, document: Document = None) -> dict:
        """Select the main subject using a provider-generated segmentation mask."""
        return typed_ai(session, "ai", ["select-subject"], document=document, provider=provider)

    @tool
    def vixl_ai_remove_background(layer: str, provider: str | None = None, document: Document = None) -> dict:
        """Attach a provider-generated foreground mask to a layer, preserving editable source pixels."""
        return typed_ai(session, "ai", ["background-remove", layer], document=document, provider=provider)

    @tool
    def vixl_ai_select_object(label: str, provider: str | None = None, document: Document = None) -> dict:
        """Select the named object using a provider-generated mask of the current canvas."""
        return typed_ai(session, "select", ["object", label], document=document, provider=provider)

    if planner:

        @tool
        def vixl_ai_plan(
            prompt: str, apply: bool = False, provider: str | None = None, document: Document = None
        ) -> dict:
            """Ask a configured provider to propose edits; inspect the proposal before apply=true."""
            return typed_ai(session, "ask", document=document, prompt=prompt, apply=apply, provider=provider)

    @tool
    def vixl_ai_analyze(
        capability: Literal["describe", "detect", "ocr"],
        query: str = "",
        provider: str | None = None,
        document: Document = None,
    ) -> dict:
        """Describe the canvas, detect objects, or read its text using a configured vision provider."""
        return typed_ai(
            session,
            "ai" if capability == "describe" else capability,
            ["describe", query] if capability == "describe" else [query],
            document=document,
            provider=provider,
        )

    @tool
    def vixl_ai_upscale(
        layer: str,
        scale: Annotated[float, Field(gt=0, le=16)] = 2,
        provider: str | None = None,
        document: Document = None,
    ) -> dict:
        """Create an upscaled copy of a layer using a configured provider."""
        return typed_ai(session, "ai", ["upscale", layer], document=document, scale=scale, provider=provider)

    @tool
    def vixl_ai_regenerate(
        layer: str,
        prompt: str | None = None,
        seed: int | None = None,
        provider: str | None = None,
        document: Document = None,
    ) -> dict:
        """Regenerate a generated layer using its saved settings, preserving its stable ID."""
        return typed_ai(
            session,
            "ai",
            ["regenerate", layer],
            document=document,
            prompt=prompt,
            seed=seed,
            provider=provider,
        )

    @tool
    def vixl_ai_extend(
        prompt: str,
        left: Annotated[int, Field(ge=0)] = 0,
        right: Annotated[int, Field(ge=0)] = 0,
        top: Annotated[int, Field(ge=0)] = 0,
        bottom: Annotated[int, Field(ge=0)] = 0,
        seed: int | None = None,
        name: str = "extension",
        provider: str | None = None,
        document: Document = None,
    ) -> dict:
        """Outpaint the canvas by the specified pixel distances; at least one must be positive."""
        return typed_ai(
            session,
            "ai",
            ["extend"],
            document=document,
            prompt=prompt,
            left=left,
            right=right,
            top=top,
            bottom=bottom,
            seed=seed,
            name=name,
            provider=provider,
        )

    @server.resource("vixl://operations")
    def operations_reference() -> str:
        return json.dumps(operation_schema())

    poll = "vixl_workflow (action status, request {id})" if tools == "compact" else "vixl_job"
    server._mcp_server.instructions += (
        f" Results name their document. A call still running after ~40 s returns a job: poll {poll} and do not "
        "resend it (heavy calls can also pass as_job=true; mutating calls take request_id so a retry never "
        "applies twice)."
    )
    if session.require_document:
        server._mcp_server.instructions += " Every document tool needs document= on every call."
    for registered in server._tool_manager.list_tools():
        registered.parameters = slim_schema(registered.parameters)
        runtime.watch_arguments(registered)
    return server
