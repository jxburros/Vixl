"""Rewrite saved MCP tool calls, operation batches and MCP server configurations from the 51-tool surface of 0.26
and earlier to the seven tools of this release.

``TOOLS`` maps every earlier tool name to the call that replaces it. An entry names the new tool, fixed arguments
(``action``, ``kind``, ``topic`` …), renamed and dropped parameters, the session step a tool became, or a handler for
tools whose replacement depends on an argument (``vixl_history``'s action, ``vixl_roll``'s apply …). Parameters the
new tool advertises stay at the top level; the rest go into ``options``, where every action takes its detail.
"""

from copy import deepcopy
import json
from pathlib import Path
import re

from ..errors import VixlError, require

# The parameters each current tool advertises at the top level (mcp_tools.build_server); others go in options.
ADVERTISED = {
    "vixl_document": {"action", "path", "size", "purpose", "target", "document", "verbose", "options"},
    "vixl_apply": {"operations", "check", "preview", "dry_run", "create", "workflow", "request", "document", "verbose",
                   "options"},
    "vixl_check": {"action", "checks", "targets", "document", "options"},
    "vixl_render": {"action", "region", "page", "time", "isolate", "document", "options"},
    "vixl_export": {"path", "kind", "overwrite", "document", "options"},
    "vixl_reference": {"topic", "name", "options"},
    "vixl_job": {"action", "id", "wait"},
}
AI_TOOLS = ("vixl_models_list", "vixl_ai_generate", "vixl_ai_remove", "vixl_ai_content_aware_fill",
            "vixl_ai_select_subject", "vixl_ai_remove_background", "vixl_ai_select_object", "vixl_ai_plan",
            "vixl_ai_analyze", "vixl_ai_upscale", "vixl_ai_regenerate", "vixl_ai_extend")
DETAIL_FULL = "detail: 'full' is verbose: true; summary and compact are the terse default"


def entry(to, *, fixed=None, rename=None, drop=None, step=None, handler=None, note=None):
    return {"to": to, "fixed": fixed or {}, "rename": rename or {}, "drop": drop or {}, "step": step,
            "handler": handler, "note": note}


def _history(args):
    """vixl_document with the history action: list → history, undo, redo, checkpoint, checkout, branch, begin, commit, rollback, compact"""
    action = args.pop("action", "list")
    actions = {"list": ("history", {"offset", "limit"}), "undo": ("undo", {"count"}), "redo": ("redo", {"count"}),
               "checkpoint": ("checkpoint", {"ref"}), "checkout": ("checkout", {"ref"}), "branch": ("branch", {"ref"}),
               "begin": ("begin", set()), "commit": ("commit", set()), "rollback": ("rollback", set()),
               "compact": ("compact", {"dry_run", "fonts"})}
    require(action in actions, f"vixl_history action {action!r} has no replacement", field="action")
    name, keep = actions[action]
    dropped = [key for key in args if key not in keep | {"document"}]
    return "vixl_document", {"action": name, **{k: v for k, v in args.items() if k not in dropped}}, \
        [f"{key} does nothing for {action}" for key in dropped]


def _notes(args):
    """vixl_document(action='notes'): add → text, resolve → resolve"""
    action, note_id, text = args.pop("action", "list"), args.pop("note_id", None), args.pop("text", None)
    out = {"action": "notes", **args}
    if action == "add":
        out["text"] = text
    elif action == "resolve":
        out["resolve"] = note_id
    return "vixl_document", out, []


def _styles(args):
    """list/get → vixl_reference('styles'); apply → a style-use step in vixl_apply; check → vixl_check(checks=['style'])"""
    action, name = args.pop("action", "list"), args.pop("name", None)
    document, palette, query = args.pop("document", None), args.pop("palette", None), args.pop("query", None)
    doc = {"document": document} if document else {}
    if action == "apply":
        step = {"type": "style-use", "name": name, **({"palette": palette} if palette is not None else {})}
        return "vixl_apply", {"operations": [step], **doc}, []
    if action == "check":
        return "vixl_check", {"action": "design", "checks": ["style"], **({"style": name} if name else {}), **doc}, []
    if action == "get":
        return "vixl_reference", {"topic": "styles", "name": name}, []
    return "vixl_reference", {"topic": "styles", **({"query": query} if query else {})}, []


def _roll(args):
    """apply: true → a roll step in vixl_apply; otherwise vixl_reference('roll')"""
    if args.pop("apply", False):
        document = args.pop("document", None)
        return "vixl_apply", {"operations": [{"type": "roll", **args}], **({"document": document} if document else {})}, []
    dropped = [key for key in ("slots", "unfilled") if key in args]
    for key in dropped:
        args.pop(key)
    return "vixl_reference", {"topic": "roll", **args}, [f"{key} only applies with apply: true" for key in dropped]


def _guide(args):
    """vixl_reference(topic=brief), or vixl_reference() without a brief"""
    brief = args.pop("brief", None)
    return "vixl_reference", {"topic": brief or "start", **args}, []


def _fonts(args):
    """vixl_reference('fonts', name=family or pairing, view …)"""
    view = args.get("view", "pairings")
    family, pairing = args.pop("family", None), args.pop("pairing", None)
    name = family if view == "font" else pairing if view == "pairing" else None
    notes = []
    if view not in ("font", "pairing") and family:
        args["name"] = family
    elif name:
        args["name"] = name
    return "vixl_reference", {"topic": "fonts", **args}, notes


def _compose(args):
    """vixl_apply(create={path, size, layout …}, operations, check, preview; exports in options)"""
    create = {key: args.pop(key) for key in ("path", "size", "width", "height", "purpose", "background",
                                             "font_pairing", "layout", "style", "look", "dpi", "orientation", "bleed",
                                             "seed", "variety") if key in args}
    return "vixl_apply", {"create": create, **args}, []


def _adapt(args):
    """vixl_apply(workflow='adapt-sizes', request={sizes, formats …})"""
    document = args.pop("document", None)
    return "vixl_apply", {"workflow": "adapt-sizes", "request": args, **({"document": document} if document else {})}, []


def _workflow(args):
    """vixl_apply(workflow=action, request)"""
    out = {"workflow": args.pop("action", None), "request": args.pop("request", None) or {}}
    return "vixl_apply", {**out, **args}, []


def _resource_add(args):
    """vixl_apply(workflow='resource-save', request={kind, name, value})"""
    return "vixl_apply", {"workflow": "resource-save", "request": args}, []


def _resource_get(args):
    """vixl_reference(topic=kind, name)"""
    return "vixl_reference", {"topic": args.pop("kind"), **args}, []


def _text_add(args):
    """a text operation in vixl_apply"""
    document = args.pop("document", None)
    return "vixl_apply", {"operations": [{"type": "text", **args}], **({"document": document} if document else {})}, []


TOOLS = {
    # Documents and history
    "vixl_document_create": entry("vixl_document", fixed={"action": "create"}),
    "vixl_document_open": entry("vixl_document", fixed={"action": "open"}, drop={
        "upgrade": "vixl upgrade is gone: convert the file once with vixl convert"}),
    "vixl_document_close": entry("vixl_document", fixed={"action": "close"}),
    "vixl_document_inspect": entry("vixl_document", fixed={"action": "inspect"}, handler="detail"),
    "vixl_workspace_list": entry("vixl_document", fixed={"action": "list"}, rename={"directory": "path"}),
    "vixl_template_create": entry("vixl_document", fixed={"action": "create"}, rename={"name": "template"}),
    "vixl_history": entry("vixl_document", handler=_history),
    "vixl_review_notes": entry("vixl_document", handler=_notes),
    # Edits, new pieces and workflows
    "vixl_operations_apply": entry("vixl_apply"),
    "vixl_compose": entry("vixl_apply", handler=_compose, note="compose is vixl_apply(create={…})"),
    "vixl_workflow": entry("vixl_apply", handler=_workflow),
    "vixl_adapt_layout": entry("vixl_apply", handler=_adapt, note="adapt-layout is the adapt-sizes workflow"),
    "vixl_resource_add": entry("vixl_apply", handler=_resource_add),
    "vixl_import_image": entry("vixl_apply", step="import-image"),
    "vixl_import_document": entry("vixl_apply", step="import-document"),
    "vixl_import_font": entry("vixl_apply", step="import-font"),
    "vixl_font_pair": entry("vixl_apply", step="font-pair"),
    "vixl_font_install": entry("vixl_apply", step="font-install"),
    "vixl_styles": entry("vixl_reference", handler=_styles),
    "vixl_roll": entry("vixl_reference", handler=_roll),
    "vixl_text_add": entry("vixl_apply", handler=_text_add, note="removed in 0.21: a text operation"),
    # Tests and measurements
    "vixl_check": entry("vixl_check", fixed={"action": "design"}),
    "vixl_validate": entry("vixl_check", fixed={"action": "validate"}, handler="detail"),
    "vixl_measure": entry("vixl_check", fixed={"action": "measure"}),
    "vixl_measure_spacing": entry("vixl_check", fixed={"action": "spacing"}),
    "vixl_spatial": entry("vixl_check", fixed={"action": "spatial"}),
    "vixl_pixels_inspect": entry("vixl_check", fixed={"action": "pixels"}),
    # Looking
    "vixl_render_preview": entry("vixl_render", fixed={"action": "preview"}),
    "vixl_render_compare": entry("vixl_render", fixed={"action": "compare"}),
    "vixl_timeline_preview": entry("vixl_render", fixed={"action": "timeline"}),
    "vixl_timeline_inspect": entry("vixl_render", fixed={"action": "timeline-inspect"}, handler="detail"),
    "vixl_animation_preview": entry("vixl_render", fixed={"action": "animation"}),
    "vixl_animation_inspect": entry("vixl_render", fixed={"action": "animation-inspect"}),
    # Files
    "vixl_export_file": entry("vixl_export", fixed={"kind": "file"}),
    "vixl_export_batch": entry("vixl_export", fixed={"kind": "batch"}),
    "vixl_export_animation": entry("vixl_export", fixed={"kind": "animation"}),
    "vixl_export_timeline": entry("vixl_export", fixed={"kind": "timeline"}),
    "vixl_export_audio": entry("vixl_export", fixed={"kind": "audio"}),
    "vixl_export_icons": entry("vixl_export", fixed={"kind": "icons"}, rename={"directory": "path"}),
    "vixl_export_character": entry("vixl_export", fixed={"kind": "character"}, rename={"output": "path"}),
    # Reference
    "vixl_guide": entry("vixl_reference", handler=_guide),
    "vixl_capabilities": entry("vixl_reference", fixed={"topic": "capabilities"}, rename={"topic": "name"}),
    "vixl_operation_schema": entry("vixl_reference", fixed={"topic": "operations"}, rename={"types": "name"}),
    "vixl_workflow_schema": entry("vixl_reference", fixed={"topic": "workflows"}),
    "vixl_sizes_list": entry("vixl_reference", fixed={"topic": "sizes"}, rename={"search": "name"}),
    "vixl_layouts_list": entry("vixl_reference", fixed={"topic": "layouts"}),
    "vixl_fonts": entry("vixl_reference", handler=_fonts),
    "vixl_brushes_list": entry("vixl_reference", fixed={"topic": "brushes"}),
    "vixl_color": entry("vixl_reference", fixed={"topic": "color"}, rename={"colors": "name"}),
    "vixl_resources_list": entry("vixl_reference", rename={"kind": "topic"}),
    "vixl_resource_get": entry("vixl_reference", handler=_resource_get),
    "vixl_job": entry("vixl_job"),
    # The provider-backed tools (vixl mcp --tools ai) keep their names and parameters.
    **{name: entry(name) for name in AI_TOOLS},
}
CURRENT_TOOLS = set(ADVERTISED) | set(AI_TOOLS)

# Server flags and environment variables: (flag, value or None for any) -> replacement argv (empty: drop it).
SERVER_FLAGS = {("--tools", "core"): [], ("--tools", "compact"): [], ("--tools", "all"): [],
                ("--tools", "default"): ["--tools", "default"], ("--tools", "ai"): ["--tools", "ai"], ("--schema", None): []}
SERVER_ENV = {"VIXL_MCP_TOOLS": "removed: vixl mcp serves the seven design tools; --tools ai the provider tools",
              "VIXL_MCP_SCHEMA": "removed: there is one schema mode"}
OPERATION_FIELDS = {"house_style_version": "house-style versioning was removed",
                    "_house_style_version": "house-style versioning was removed"}


def describe(name):
    """One line on what replaces the earlier tool ``name``."""
    spec = TOOLS[name]
    if callable(spec["handler"]):
        text = spec["handler"].__doc__.strip()
    elif spec["step"]:
        text = f"{'an' if spec['step'][0] in 'aeiou' else 'a'} `{spec['step']}` step in `vixl_apply`"
    elif spec["to"] == name and not spec["fixed"]:
        text = "unchanged"
    else:
        fixed = ", ".join(f"{key}='{value}'" for key, value in spec["fixed"].items())
        text = f"`{spec['to']}({fixed})`" if fixed else f"`{spec['to']}`"
    if spec["handler"] == "detail":
        text += "; detail='full' → verbose"
    renamed = ", ".join(f"{old} → {new}" for old, new in spec["rename"].items())
    dropped = ", ".join(f"{old} dropped" for old in spec["drop"])
    return "; ".join(part for part in (text, renamed, dropped) if part)


def markdown_table():
    """The tool table of docs/converting.md (a test compares them)."""
    rows = ["| Earlier tool | Now |", "| --- | --- |"]
    rows += [f"| `{name}` | {describe(name)} |" for name in TOOLS]
    return "\n".join(rows)


class Batch:
    def __init__(self):
        self.changes, self.warnings = [], []

    def change(self, where, change, reason, **values):
        self.changes.append({"change": change, "at": where, "reason": reason, **values})

    def warn(self, where, change, reason, **values):
        self.warnings.append({"change": change, "at": where, "reason": reason, **values})


def _prefix(name):
    """(prefix, tool) for a client-prefixed tool name such as ``mcp__SERVER__TOOL``, else ('', name)."""
    match = re.match(r"^(.*__)?(vixl_\w+)$", name) if isinstance(name, str) else None
    return (match.group(1) or "", match.group(2)) if match else ("", name)


def convert_call(name, arguments, batch, where):
    """``(new_name, new_arguments)`` for one tool call."""
    prefix, bare = _prefix(name)
    args = deepcopy(arguments or {})
    original = deepcopy(args)
    if bare not in TOOLS:
        if bare == "vixl_apply" and isinstance(args.get("operations"), list):
            args["operations"] = convert_operations(args["operations"], batch, f"{where}.operations")
        elif bare not in CURRENT_TOOLS and isinstance(bare, str) and bare.startswith("vixl_"):
            batch.warn(where, "unmapped-tool", f"{bare} is not a Vixl tool of any release this kit knows; left as it is")
        return name, args
    spec = TOOLS[bare]
    notes = []
    for old, reason in spec["drop"].items():
        if old in args:
            notes.append(f"{old} dropped: {reason}")
            args.pop(old)
    for old, new in spec["rename"].items():
        if old in args:
            args[new] = args.pop(old)
    tool = spec["to"]
    handler = spec["handler"]
    if handler == "detail":
        detail = args.pop("detail", None)
        if detail == "full":
            args["verbose"] = True
        elif detail is not None and bare != "vixl_document_inspect":
            notes.append(DETAIL_FULL)
    elif callable(handler):
        tool, args, extra = handler(args)
        notes += extra
    if spec["step"]:
        document = args.pop("document", None)
        args = {"operations": [{"type": spec["step"], **args}], **({"document": document} if document else {})}
    if not callable(handler):
        args = {**spec["fixed"], **args}
    top = ADVERTISED.get(tool)
    if top is not None:
        options = dict(args.pop("options", None) or {})
        for key in [key for key in args if key not in top]:
            options[key] = args.pop(key)
        if options:
            args["options"] = options
    if tool == "vixl_apply" and isinstance(args.get("operations"), list):
        args["operations"] = convert_operations(args["operations"], batch, f"{where}.operations")
    if prefix + tool == name and args == original:
        return name, args
    batch.change(where, "tool", spec["note"] or f"{bare} is {tool}" + (
        f"({', '.join(f'{k}={v!r}' for k, v in args.items() if k in ('action', 'kind', 'topic', 'workflow'))})"),
        before=bare, after=prefix + tool)
    for note in notes:
        batch.warn(where, "parameter", note, tool=bare)
    return prefix + tool, args


def convert_operations(operations, batch, where):
    out = []
    for index, op in enumerate(operations):
        if isinstance(op, dict):
            op = dict(op)
            for key, reason in OPERATION_FIELDS.items():
                if key in op:
                    batch.change(f"{where}[{index}]", "operation-field", reason, field=key, before=op.pop(key))
        out.append(op)
    return out


def convert_server(config, batch, where):
    """An MCP server entry ``{command, args, env}`` without the removed tool-set and schema flags."""
    config = deepcopy(config)
    args = config.get("args")
    if isinstance(args, list) and any(str(arg) == "mcp" for arg in args):
        out, index = [], 0
        while index < len(args):
            arg = str(args[index])
            flag, value = (arg.split("=", 1) + [None])[:2] if arg.startswith("--") and "=" in arg else (arg, None)
            if flag in ("--tools", "--schema"):
                if value is None and index + 1 < len(args):
                    value, index = str(args[index + 1]), index + 1
                key = (flag, value) if (flag, value) in SERVER_FLAGS else (flag, None)
                replacement = SERVER_FLAGS.get(key)
                if replacement is None:
                    batch.warn(where, "server-flag", f"{flag} {value} is not a known value; dropped")
                    replacement = []
                if replacement != [flag, value]:
                    batch.change(where, "server-flag", f"vixl mcp {flag} {value}: "
                                 + ("removed; the server serves the seven design tools" if not replacement
                                    else "kept"), before=f"{flag} {value}")
                out += replacement
            else:
                out.append(args[index])
            index += 1
        config["args"] = out
    env = config.get("env")
    if isinstance(env, dict):
        for key, reason in SERVER_ENV.items():
            if key in env:
                value = env.pop(key)
                if key == "VIXL_MCP_TOOLS" and value == "ai":
                    config["args"] = [*config.get("args", []), "--tools", "ai"]
                batch.change(where, "server-env", reason, before=f"{key}={value}")
    return config


def _tool_call(value):
    """``(name key, arguments key)`` when ``value`` is one tool call in a shape this kit reads, else None."""
    if not isinstance(value, dict):
        return None
    for name_key in ("tool", "name", "tool_name"):
        name = value.get(name_key)
        if isinstance(name, str) and "vixl_" in name and _prefix(name)[1].startswith("vixl_"):
            for args_key in ("arguments", "args", "input", "params", "parameters"):
                if args_key in value and (value[args_key] is None or isinstance(value[args_key], dict)):
                    return name_key, args_key
            return name_key, None
    return None


def convert_value(value, batch, where="$"):
    if isinstance(value, list):
        if value and all(isinstance(item, dict) and "type" in item and _tool_call(item) is None for item in value):
            return convert_operations(value, batch, where)
        return [convert_value(item, batch, f"{where}[{index}]") for index, item in enumerate(value)]
    if not isinstance(value, dict):
        return value
    if isinstance(value.get("mcpServers"), dict):
        out = dict(value)
        out["mcpServers"] = {name: convert_server(server, batch, f"{where}.mcpServers.{name}")
                             for name, server in value["mcpServers"].items()}
        return out
    if value.get("method") == "tools/call" and isinstance(value.get("params"), dict):
        out = dict(value)
        params = dict(value["params"])
        params["name"], params["arguments"] = convert_call(params.get("name"), params.get("arguments"), batch,
                                                           where)
        out["params"] = params
        return out
    found = _tool_call(value)
    if found:
        name_key, args_key = found
        out = dict(value)
        new_name, new_args = convert_call(value[name_key], value.get(args_key) if args_key else None, batch, where)
        out[name_key] = new_name
        out[args_key or "arguments"] = new_args
        return out
    if isinstance(value.get("operations"), list):
        out = dict(value)
        out["operations"] = convert_operations(value["operations"], batch, f"{where}.operations")
        return out
    if "type" in value:
        return convert_operations([value], batch, where)[0]
    return {key: convert_value(item, batch, f"{where}.{key}") for key, item in value.items()}


def convert_batch(value):
    """``(converted, report)`` for saved tool calls, operation batches or an MCP configuration (any JSON value)."""
    batch = Batch()
    converted = convert_value(value, batch)
    return converted, {"changes": batch.changes, "warnings": batch.warnings,
                       "counts": {"changes": len(batch.changes), "warnings": len(batch.warnings)}}


def convert_batch_file(source, output=None, *, dry_run=False, overwrite=False):
    """Convert a ``.json`` or ``.jsonl`` file of saved calls; writes ``NAME-converted.EXT`` unless told otherwise."""
    source = Path(source)
    require(source.is_file(), f"File does not exist: {source}", "not_found", field="path")
    output = Path(output) if output else source.with_name(source.stem + "-converted" + source.suffix)
    text = source.read_text(encoding="utf-8")
    lines = source.suffix.lower() == ".jsonl"
    try:
        value = [json.loads(line) for line in text.splitlines() if line.strip()] if lines else json.loads(text)
    except json.JSONDecodeError as exc:
        raise VixlError("invalid_json", f"{source.name} is not JSON: {exc}", field="path") from exc
    converted, report = convert_batch(value)
    if not dry_run:
        require(overwrite or not output.exists(), f"{output} exists; pass --overwrite to replace it", "output_exists",
                field="output")
        require(output.resolve() != source.resolve(), "Write the converted calls to a new file", "output_exists",
                field="output")
        body = "".join(json.dumps(item) + "\n" for item in converted) if lines else json.dumps(converted, indent=2) + "\n"
        output.write_text(body, encoding="utf-8")
    return {"source": str(source), "output": None if dry_run else str(output), "dry_run": dry_run, **report}
