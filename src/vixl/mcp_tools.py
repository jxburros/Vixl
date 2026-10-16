"""The Vixl MCP server: seven verb tools over a persistent workspace session (mcp_actions.py holds their actions).

Responses are minified JSON text (no duplicated structured copy), errors carry the engine's structured
code/field/suggestions (and the expected schema for a bad option or operation), and every document tool accepts
an optional ``document``.
"""

import base64
import binascii
import inspect
import json
import os
import re
from types import SimpleNamespace
from typing import Annotated, Literal

from pydantic import Field, WithJsonSchema

from .errors import VixlError, require
from .fileio import file_lock
from .mcp_runtime import Runtime
from .model import Limits
from .proxy import preview_png
from .schema import operation_schema


def compact_json(value):
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False, default=str)


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
    isolate=None,
    views=None,
    exploded=False,
):
    with session.project(document=document) as project:
        return preview_png(project, max_width, max_height, max_bytes, region=region, variables=variables,
                           artboard=artboard, comp=comp, time=time, proof=proof, simulate=simulate, guides=guides,
                           page=page, values=values, show_fields=show_fields, isolate=isolate, views=views,
                           exploded=exploded)


EXPORT_SUFFIXES = (".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff", ".avif", ".svg", ".pdf", ".ico", ".html", ".htm", ".pptx", ".psd",
                   ".ttf", ".otf", ".woff", ".woff2",
                   ".vixl")


def export_file(session, path, overwrite=False, document=None, **options):
    from .fileio import temporary

    with session._mutex:
        destination = session.resolve(path)
        require(
            destination.suffix.lower() in EXPORT_SUFFIXES,
            "Choose a PNG, JPEG, WEBP, TIFF, AVIF, SVG, PDF, ICO, HTML, PPTX or PSD filename, a TTF, OTF, WOFF or WOFF2 "
            "font (the document's font design), or .vixl with isolate",
            field="path",
        )
        require(destination.suffix.lower() != ".vixl" or options.get("isolate"),
                "A .vixl export writes a portable object document: pass isolate=[OBJECT]", field="path")
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
                from .call_limits import check_export, of

                if destination.suffix.lower() == ".vixl":
                    from .objects import portable_bytes

                    data = portable_bytes(project, options, report)
                    fmt = "VIXL"
                else:
                    check_export(of(session), project, fmt, options)
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
        return {"path": session.relative(destination), "format": fmt, "bytes": len(data), **report,
                "outcome": export_outcome(report)}


def export_outcome(report):
    """A written export executed; it is not validated (exports run no checks) and its warnings need review."""
    from .outcomes import make

    warnings = [str(item) for item in report.get("warnings", [])]
    return make("completed", "not_run", ["export runs no checks: run vixl_check and the suites first", *warnings])


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
    from .plugins.ai.ai import ai_execute

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




SHARED_TOOLS = {"vixl_document", "vixl_render", "vixl_job"}
TOOLS = ("vixl_document", "vixl_apply", "vixl_check", "vixl_render", "vixl_export", "vixl_reference", "vixl_job")
INSTRUCTIONS = (
    "Vixl edits layered design documents in this workspace. Call vixl_reference() first for the working loop, or "
    "vixl_reference(BRIEF) for how to make a kind of work. Loop: vixl_document(action='create', path, size or "
    "purpose) → vixl_apply(operations=[…], check=true) (atomic batches; fields per operation: "
    "vixl_reference('operations', name=[types])) → fix the 'fix' findings → vixl_render() to look → "
    "vixl_export(path). Each tool takes rare parameters in options (vixl_reference(TOOL) lists them per action); "
    "errors return the fields expected. Pass document= when several documents are open."
)
AI_INSTRUCTIONS = (
    "Provider-backed AI editing for Vixl documents in the configured workspace: generate, inpaint, extend, "
    "upscale, remove objects or backgrounds, select subjects/objects, and describe/detect/OCR. Each tool takes "
    "document= (a .vixl path in the workspace) or uses the document opened with vixl_document(action='open'). Results "
    "are saved at once, so the main Vixl server sees them on its next call. Find layers with vixl_document and check "
    "results with vixl_render. Every tool needs a configured provider (vixl_models_list); if none is configured, say "
    "so instead of retrying."
)


def is_ai_tool(name):
    return name.startswith("vixl_ai_") or name == "vixl_models_list"


def unknown_tool_message(name, defined):
    """The error for a call to a tool this server does not serve: the server that serves it, or the closest names."""
    import difflib

    if name in defined:
        return f"Unknown tool: {name}. It is served by vixl mcp --tools {'ai' if is_ai_tool(name) else 'default'}."
    close = difflib.get_close_matches(name, sorted(defined), n=3)
    return f"Unknown tool: {name}." + (f" Did you mean {', '.join(close)}?" if close else f" Tools: {', '.join(TOOLS)}.")


def check_sdk():
    """Fail before importing the version-specific SDK API, including source checkouts."""
    from importlib.metadata import PackageNotFoundError, version

    try:
        installed = version("mcp")
    except PackageNotFoundError as exc:
        raise VixlError("missing_dependency", "Vixl needs the mcp SDK 1.x: pip install 'mcp>=1.21.1,<2'") from exc
    # Releases before 1.21.1 import a helper that current pydantic no longer has.
    parts = ([int(part) for part in re.findall(r"\d+", installed)[:3]] + [0, 0, 0])[:3]
    require(parts[0] == 1 and parts[1:] >= [21, 1],
            f"Vixl needs the mcp SDK >=1.21.1,<2 (found {installed}): pip install 'mcp>=1.21.1,<2'",
            "missing_dependency")


Options = Annotated[dict | None, Field(description="Other parameters of the action (vixl_reference(TOOL) lists them)")]
Document = Annotated[str | None, Field(description=".vixl path; default: the active document")]
Verbose = Annotated[bool, Field(description="Full result instead of the terse summary")]
OperationItem = Annotated[dict, WithJsonSchema({"type": "object", "required": ["type"],
                                                "properties": {"type": {"type": "string"}}})]
DocumentAction = Literal["create", "open", "close", "inspect", "list", "history", "undo", "redo", "checkpoint",
                         "checkout", "branch", "begin", "commit", "rollback", "compact", "notes"]
CheckAction = Literal["design", "validate", "measure", "spacing", "spatial", "pixels"]
RenderAction = Literal["preview", "compare", "timeline", "timeline-inspect", "animation", "animation-inspect"]
ExportKind = Literal["file", "batch", "animation", "timeline", "audio", "icons", "character"]


def build_server(session, *, planner=False, tools="default", allow_screen_capture=None):
    """Create the FastMCP server. ``tools='default'`` serves the seven design tools; ``tools='ai'`` serves the
    provider-backed tools plus the shared document, render and job tools. ``planner`` adds the provider-backed
    planning tool to the AI server."""
    check_sdk()
    if allow_screen_capture is None:
        allow_screen_capture = os.environ.get("VIXL_ALLOW_SCREEN_CAPTURE", "").strip().lower() in ("1", "true", "yes", "on")
    from mcp.server.fastmcp import FastMCP
    from mcp.server.fastmcp.exceptions import ToolError

    from .mcp_actions import ACTIONS, Context, describe, export_kind, invoke, merged

    require(tools in ("default", "ai"), "tools must be default or ai", field="tools")
    server = FastMCP("Vixl AI" if tools == "ai" else "Vixl", instructions=AI_INSTRUCTIONS if tools == "ai" else INSTRUCTIONS)

    def selected(name):
        if name in SHARED_TOOLS:
            return True
        return is_ai_tool(name) == (tools == "ai")

    from . import __version__

    # serverInfo.version names the engine, not the MCP SDK.
    server._mcp_server.version = __version__
    from .call_limits import of as call_limits_of

    runtime = Runtime(session, compact_json, ToolError, inline_seconds=call_limits_of(session).timeout)
    server.vixl_runtime = runtime
    context = Context(session, runtime, allow_screen_capture)
    defined = set()
    manager = server._tool_manager
    serve_call = manager.call_tool

    async def call_tool(name, arguments, context=None, convert_result=False):
        registered = manager.get_tool(name)
        if registered is None:
            raise ToolError(unknown_tool_message(name, defined))
        arguments = fold_options(registered, arguments)
        try:
            return await serve_call(name, arguments, context=context, convert_result=convert_result)
        except ToolError as exc:
            from pydantic import ValidationError

            if isinstance(exc.__cause__, ValidationError):
                raise ToolError(compact_json(argument_error(name, exc.__cause__))) from exc
            raise

    manager.call_tool = call_tool

    def tool(fn):
        """Register a tool returning minified JSON, with structured errors. It runs in a worker
        thread with progress, background jobs and retry ids (mcp_runtime.py)."""
        wrapper = runtime.wrap(fn)
        defined.add(fn.__name__)
        if selected(fn.__name__):
            # Python 3.13 dedents docstrings, 3.11 and 3.12 do not: clean them so every client gets the same text.
            server.tool(description=inspect.cleandoc(fn.__doc__ or ""), structured_output=False)(wrapper)
        return wrapper

    @tool
    def vixl_document(
        action: DocumentAction = "inspect",
        path: Annotated[str | None, Field(description="create/open: the .vixl file; list: a folder")] = None,
        size: Annotated[str | None, Field(description="create: a named size (vixl_reference('sizes'))")] = None,
        purpose: Annotated[str | None, Field(description="create: poster, social, slides, logo, icon …")] = None,
        target: Annotated[str | None, Field(description="inspect: one layer")] = None,
        document: Document = None,
        verbose: Verbose = False,
        options: Options = None,
    ) -> dict:
        """Create (path plus size, width/height, purpose or template), open, close, inspect and list documents;
        history, undo/redo, checkpoints and review notes."""
        return invoke(context, "vixl_document", action, merged(options, path=path, size=size, purpose=purpose,
                                                                target=target, document=document,
                                                                verbose=verbose or None))

    @tool
    def vixl_apply(
        operations: Annotated[list[OperationItem] | None, Field(max_length=Limits().max_operations,
            description="Operations and session steps, applied all or none; exact fields: "
                        "vixl_reference('operations', name=[types])")] = None,
        check: Annotated[bool | str | list[str] | None, Field(description="Also run vixl_check on the result")] = None,
        preview: Annotated[bool | dict | None, Field(description="Also return a small preview PNG")] = None,
        dry_run: bool = False,
        create: Annotated[dict | None, Field(description="Build a new piece in one call: {path, size, purpose, "
                                                         "layout, font_pairing, style, look …}")] = None,
        workflow: Annotated[str | None, Field(description="Run this workflow action instead "
                                                          "(vixl_reference('workflows'))")] = None,
        request: Annotated[dict | None, Field(description="The workflow's fields")] = None,
        document: Document = None,
        verbose: Verbose = False,
        options: Options = None,
    ) -> dict | list:
        """Apply an atomic batch of operations (and steps such as import-image or font-pair) to a document, build a
        new piece with create, or run a workflow; check and preview report on the result in the same call."""
        if workflow is not None:
            require(operations is None and create is None, "workflow runs alone; drop operations and create",
                    field="workflow")
            return invoke(context, "vixl_apply", "workflow",
                          merged(options, workflow=workflow, request=request, document=document,
                                 dry_run=dry_run or None, check=check, preview=preview, verbose=verbose or None))
        if create is not None:
            return invoke(context, "vixl_apply", "create",
                          merged(options, create=create, operations=operations, check=check, preview=preview,
                                 dry_run=dry_run or None, document=document, verbose=verbose or None))
        return invoke(context, "vixl_apply", "batch",
                      merged(options, operations=operations, check=check, preview=preview, dry_run=dry_run or None,
                             document=document, verbose=verbose or None))

    @tool
    def vixl_check(
        action: CheckAction = "design",
        checks: Annotated[list[str] | None, Field(description="design: check names (vixl_reference('checks'))")] = None,
        targets: Annotated[list | None, Field(description="Layer IDs, names, globs or groups")] = None,
        document: Document = None,
        options: Options = None,
    ) -> dict:
        """Test the document without looking: design checks with rule IDs and repairs, rule validation, rendered
        colour measurement, spacing pass/fail, spatial relations and pixel rows."""
        return invoke(context, "vixl_check", action, merged(options, checks=checks, targets=targets,
                                                             document=document))

    @tool
    def vixl_render(
        action: RenderAction = "preview",
        region: Annotated[list[float | str] | None, Field(description="Zoom to [x, y, w, h]")] = None,
        page: Annotated[int | str | None, Field(description="Page number or name; 'all' for a sheet")] = None,
        time: Annotated[float | str | None, Field(description="Animation time: ms, '1.5s', '50%' or marker")] = None,
        isolate: Annotated[list[str] | None, Field(description="Only these layers or objects")] = None,
        document: Document = None,
        options: Options = None,
    ) -> dict | list:
        """Look at the document: a bounded PNG preview, a revision comparison, a timeline frame or contact sheet, a
        saved animation frame, or the timeline and frame summaries."""
        return invoke(context, "vixl_render", action, merged(options, region=region, page=page, time=time,
                                                              isolate=isolate, document=document))

    @tool
    def vixl_export(
        path: Annotated[str | None, Field(description="Workspace file; the extension picks the format")] = None,
        kind: Annotated[ExportKind | None, Field(description="Default: from the extension (.wav audio, .gif/.mp4 "
                                                             "motion, batch with targets)")] = None,
        overwrite: bool = False,
        document: Document = None,
        options: Options = None,
    ) -> dict:
        """Write files: one image, PDF, SVG, PPTX, HTML or PSD; a batch; animations, timelines, audio, icon sets or
        a character library (vixl_reference('exports'))."""
        values = merged(options, path=path, overwrite=overwrite or None, document=document)
        return invoke(context, "vixl_export", kind or export_kind(context, path, values, document), values)

    @tool
    def vixl_reference(
        topic: Annotated[str, Field(description="operations, workflows, capabilities, sizes, layouts, fonts, "
                                                "brushes, styles, looks, color, roll, palettes, templates, objects, "
                                                "guidance, house-style, a tool name, a guidance name or a "
                                                "brief")] = "start",
        name: Annotated[str | list[str] | None, Field(description="The entry to read (operation types, a layout, a "
                                                                  "style …)")] = None,
        options: Options = None,
    ) -> dict:
        """Catalogs, exact schemas and craft guidance: what to make for a brief, operation and tool fields, sizes,
        layouts, fonts, styles, colours and resources."""
        topics = ACTIONS["vixl_reference"]
        if topic in topics:
            return invoke(context, "vixl_reference", topic, merged(options, name=name))
        if topic in ACTIONS:
            require(not options, "a tool's reference takes name (one action) only", field="options")
            return describe(topic, name)
        require(name is None, "name goes with a catalog topic; a brief or guidance name is the topic itself",
                field="name")
        return invoke(context, "vixl_reference", "guide", merged(options, name=topic))

    @tool
    def vixl_job(
        action: Literal["status", "result", "cancel", "list"] = "status",
        id: str | None = None,
        wait: Annotated[float, Field(ge=0, le=50, description="Seconds to wait for the job to finish")] = 0,
    ) -> dict:
        """Follow a call that returned {status: running, job} (after ~40 s, or as_job=true): status, result, cancel,
        or list recent jobs; also takes a durable workflow job ID."""
        return runtime.job(action, id, wait)

    @tool
    def vixl_models_list(
        provider: str | None = None, capability: str | None = None, refresh: bool = False
    ) -> dict:
        """Discover authenticated model IDs and supported capabilities; keys stay in server environment variables."""
        from .plugins.ai.models import configured, DEFAULTS, CAPABILITIES, refresh as refresh_models

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

    server._mcp_server.instructions += (
        " A call still running after ~40 s returns a job: poll vixl_job and do not resend it (mutating calls take "
        "request_id so a retry never applies twice)."
    )
    if session.require_document:
        server._mcp_server.instructions += " Every document tool needs document= on every call."
    for registered in server._tool_manager.list_tools():
        registered.parameters = slim_schema(registered.parameters)
        runtime.watch_arguments(registered)
    return server


TOOL_CAP = 2000  # characters of one advertised tool (name, description and input schema)


def surface(tools="default"):
    """What a client reads in tools/list and the instructions: characters per tool (compact JSON of each tool
    object), the total, approximate tokens (characters / 4) and the instruction length."""
    import asyncio
    import tempfile
    from pathlib import Path

    from .interfaces import Session

    with tempfile.TemporaryDirectory() as workspace:
        server = build_server(Session(workspace=Path(workspace)), tools=tools)
        listed = asyncio.run(server.list_tools())
        instructions = server._mcp_server.instructions or ""
    sizes = {tool.name: len(compact_json(tool.model_dump(exclude_none=True))) for tool in listed}
    total = sum(sizes.values())
    return {"tools": dict(sorted(sizes.items())), "total_chars": total, "total_tokens": round(total / 4),
            "instructions_chars": len(instructions), "instructions_tokens": round(len(instructions) / 4)}


def fold_options(registered, arguments):
    """Arguments a tool does not advertise go into its ``options`` (validated there against the chosen action),
    so ``vixl_render(max_width=200)`` and ``vixl_render(options={max_width: 200})`` are the same call."""
    properties = registered.parameters.get("properties", {})
    if "options" not in properties or not isinstance(arguments, dict):
        return arguments
    extra = {key: value for key, value in arguments.items() if key not in properties}
    if not extra:
        return arguments
    options = arguments.get("options")
    if options is not None and not isinstance(options, dict):
        return arguments
    return {**{key: value for key, value in arguments.items() if key in properties},
            "options": {**extra, **(options or {})}}


def argument_error(tool, error):
    """A tool-argument validation failure in the same JSON shape as every other Vixl error."""
    problems = []
    for item in error.errors():
        where = ".".join(str(part) for part in item.get("loc", ()) if part != tool + "Arguments")
        text = "missing" if item.get("type") == "missing" else item.get("msg", "invalid")
        problems.append((where, text))
    field = problems[0][0] if problems else None
    message = "; ".join(f"{where}: {text}" if where else text for where, text in problems) or "Invalid arguments"
    return {"error": "invalid_arguments", "message": f"{tool}: {message}", "field": field,
            "fields": [where for where, _ in problems if where]}
