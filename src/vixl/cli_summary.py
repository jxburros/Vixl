"""Short human summaries of CLI results.

In a terminal the CLI prints these instead of the full JSON; piped output, ``--json`` and ``VIXL_JSON=1`` keep the
JSON. Formatters are chosen from the shape of the result (a created document, an edit, a check report ...) so every
command that returns one of those kinds is covered; anything else gets the generic fallback.
"""
import os

GLOBAL_VALUE_OPTIONS = ("--project", "-p", "--max-pixels", "--detail")
MAX_ROWS = 10


def wants_json(argv, environ=None):
    """True when ``--json`` or ``VIXL_JSON`` asks for JSON whatever the output stream is."""
    environ = os.environ if environ is None else environ
    flag = str(environ.get("VIXL_JSON", "")).strip().lower()
    return "--json" in argv or flag not in ("", "0", "false", "no", "off")


def human_output(argv, stream):
    """Whether results print as a summary: ``stream`` is a terminal and JSON was not asked for."""
    try:
        interactive = bool(stream.isatty())
    except (AttributeError, ValueError):
        interactive = False
    return interactive and not wants_json(argv)


def command_of(argv):
    """The command word in ``argv``: the first token that is neither a global option nor its value."""
    skip = False
    for token in argv:
        if skip:
            skip = False
        elif token in GLOBAL_VALUE_OPTIONS:
            skip = True
        elif not token.startswith("-"):
            return token
    return None


def size(count):
    """A byte count such as ``16.2 KB``."""
    if count < 1024:
        return f"{count} B"
    count /= 1024
    for unit in ("KB", "MB", "GB"):
        if count < 1024 or unit == "GB":
            return f"{count:.1f} {unit}"
        count /= 1024


def plural(count, word, many=None):
    return f"{count} {word if count == 1 else many or word + 's'}"


def number(value):
    if isinstance(value, float):
        return f"{value:.4g}" if value != int(value) else str(int(value))
    return str(value)


def canvas_text(canvas):
    if not isinstance(canvas, dict) or "width" not in canvas:
        return ""
    text = f"{number(canvas['width'])}×{number(canvas['height'])}"
    if canvas.get("background"):
        text += f"  bg {canvas['background']}"
    return text


def layer_label(layer):
    name = layer.get("name") or layer.get("id") or "layer"
    return f'{layer["type"]} "{name}"' if layer.get("type") else f'"{name}"'


def tail(lines, extra, limit=MAX_ROWS):
    lines = list(lines)
    if len(lines) > limit:
        lines = [*lines[:limit], f"  … {len(lines) - limit} more"]
    return [*lines, *extra]


def notes_of(result, key="warnings"):
    items = result.get(key) or []
    return [f"{key[:-1] if key.endswith('s') else key}: {item}" for item in items[:3] if isinstance(item, str)]


def created(result, command):
    verb = {"new": "created", "open": "opened"}.get(command, "document")
    line = f"{verb} {os.path.basename(str(result['path']))}  {canvas_text(result['canvas'])}".rstrip()
    if result.get("layers"):
        line += f"  {plural(result['layers'], 'layer')}"
    seed = (result.get("design_defaults") or {}).get("seed")
    if seed is not None:
        line += f"  seed {seed}"
    fonts = (result.get("creation") or {}).get("fonts")
    return [line, *([f"fonts: {font_status(fonts)}"] if fonts else [])]


def font_status(fonts):
    """What a new document's fonts are: installed, waiting for the first text, or the fallback and why."""
    pairing = fonts.get("pairing")
    if fonts.get("installed"):
        return f"{pairing} ({fonts.get('origin', 'installed')})"
    if fonts.get("pending"):
        return f"{pairing} (installed with the first text; VIXL_AUTO_FONTS=cache|off to change)"
    return f"fallback ({fonts.get('reason', 'no pairing')})" if pairing or fonts.get("reason") else "fallback"


def state(result, command):
    layers = result["layers"]
    steps = next((result[key] for key in ("undo", "redo") if isinstance(result.get(key), int)), None)
    lead = ""
    if steps is not None:
        key = "undo" if "undo" in result else "redo"
        lead = f"{'undid' if key == 'undo' else 'redid'} {plural(steps, 'step')}  "
    names = ", ".join(f"{layer.get('name', '?')} ({layer.get('type', '?')})" for layer in layers[:8])
    more = f", +{len(layers) - 8} more" if len(layers) > 8 else ""
    line = f"{lead}{canvas_text(result.get('canvas'))}  {plural(len(layers), 'layer')}"
    return [line + (f": {names}{more}" if layers else ""), *notes_of(result, "notes")]


def changed_fields(delta):
    return [key for key in (delta.get("changed") or [k for k in delta if k not in DERIVED]) if key not in DERIVED]


DERIVED = {"bounds", "canvas_bounds", "content_bounds", "ink_bounds", "line_bounds", "baseline", "baselines",
           "ascent", "descent", "cap_height", "x_height", "metrics_space", "resolved_bounds", "coordinate_space",
           "parent", "group", "grouped"}


OMITTED = ("layers_omitted", "changed_omitted", "removed_omitted")  # brief detail's counts past its caps


def named(result, lines):
    """``lines`` with the first prefixed by the document's file name, so a command never edits an unnamed file."""
    if lines and isinstance(result.get("path"), str):
        lines[0] = f"{os.path.basename(result['path'])}: {lines[0]}"
    return lines


def edit(result, command):
    changes = result.get("changes") or {}
    layers = changes.get("layers") or {}
    lines = []
    changed = []
    for delta in layers.values():
        if delta.get("added"):
            lines.append(f"added {layer_label(delta)}")
        elif delta.get("removed"):
            lines.append(f"removed \"{delta.get('name', 'layer')}\"")
        else:
            changed.append(delta)
    omitted = {key: (changes.get(key) or {}).get("count", 0) for key in OMITTED}
    if omitted["layers_omitted"]:
        lines.append(f"added {plural(omitted['layers_omitted'], 'more layer')}")
    if omitted["removed_omitted"]:
        lines.append(f"removed {plural(omitted['removed_omitted'], 'more layer')}")
    if changed or omitted["changed_omitted"]:
        fields = list(dict.fromkeys(field for delta in changed for field in changed_fields(delta)))
        detail = f": {', '.join(fields[:6])}" if fields else ""
        lines.append(f"changed {plural(len(changed) + omitted['changed_omitted'], 'layer')}{detail}")
    others = [key for key in changes if key not in ("layers", "active_layer", *OMITTED)]
    if others:
        lines.append(f"changed {', '.join(others[:5])}")
    if not lines:
        lines.append("no changes")
    count = result.get("operations")
    if isinstance(count, int) and count > 1:
        lines.insert(0, f"applied {plural(count, 'operation')}")
    if result.get("dry_run"):
        lines[0] = f"dry run: {lines[0]}"
    return named(result, [*lines, *notes_of(result)])


def check(result, command):
    errors, warnings = result.get("errors", 0), result.get("warnings", 0)
    names = (result.get("checked") or {}).get("checks") or []
    scope = f" ({', '.join(names)})" if 0 < len(names) <= 4 else f" ({len(names)} checks)" if names else ""
    verdict = "passed" if result.get("passed") else "failed"
    head = f"check {verdict}{scope} — {plural(errors, 'error')}, {plural(warnings, 'warning')}"
    rank = {"error": 0, "warning": 1}
    issues = sorted(result.get("issues") or [], key=lambda issue: rank.get(issue.get("severity"), 2))
    rows = [f"  {issue.get('severity', '?'):<7} {', '.join(issue.get('layers') or ['-']):<16} {issue.get('message', '')}"
            for issue in issues]
    return named(result, [head, *tail(rows, [])])


def written(result, command):
    verb = "rendered" if command == "render" else "exported"
    line = f"{verb} {result['output']}"
    if isinstance(result.get("bytes"), int):
        line += f" ({size(result['bytes'])})"
    return named(result, [line, *notes_of(result)])


def schema_groups(result, command):
    """``vixl schema`` without arguments: each purpose with its operation names."""
    rows = []
    for title, names in result["groups"].items():
        words = ", ".join(names)
        rows.append(f"{title}: {words if len(words) <= 100 else words[:99].rsplit(', ', 1)[0] + ', …'}")
    return [f"{result['count']} operations", *rows, result["next"]]


def layer_table(items, command):
    if not items:
        return ["no layers"]
    rows = []
    for layer in items:
        where = ""
        if "width" in layer and "height" in layer:
            where = f"{number(layer['width'])}×{number(layer['height'])} at {number(layer.get('x', 0))},{number(layer.get('y', 0))}"
        hidden = "  hidden" if layer.get("visible") is False else ""
        rows.append(f"  {layer['name']:<20} {layer['type']:<8} {where}{hidden}".rstrip())
    return [plural(len(items), "layer"), *tail(rows, [])]


def history(items, command):
    rows = [f"  {node['id']}  {node.get('label') or plural(len(node.get('operations') or []), 'operation')}" for node in items]
    return [plural(len(items), "revision"), *tail(rows, [])]


def validation(result, command):
    checks = result.get("checks") or []
    failed = [c for c in checks if not c.get("passed")]
    head = f"validation {'passed' if result.get('valid') else 'failed'} — {plural(len(checks), 'rule')}"
    return [head, *tail([f"  {c.get('rule')}" for c in failed], [])]


def conversion(result, command):
    """``vixl convert``: one line per file, then the warnings (what was not converted or will look different)."""
    summary = result["summary"]
    lines = []
    for report in result["converted"]:
        counts = report.get("counts") or {}
        target = os.path.basename(str(report["output"])) if report.get("output") else "(dry run)"
        saved = f" (saved by {report['saved_by']})" if report.get("saved_by") else ""
        lines.append(f"converted {os.path.basename(str(report['source']))}{saved} → {target}  "
                     f"{plural(counts.get('changes', 0), 'change')}, {plural(counts.get('warnings', 0), 'warning')}")
    for item in result.get("failed") or []:
        lines.append(f"failed {os.path.basename(str(item['source']))}: {item.get('message', item.get('error'))}")
    if len(result["converted"]) + len(result.get("failed") or []) > 1:
        lines.insert(0, f"{plural(summary['converted'], 'file')} converted, {summary['failed']} failed — "
                        f"{plural(summary['changes'], 'change')}, {plural(summary['warnings'], 'warning')}")
    rows = [f"  warning {entry.get('layer') or entry.get('at') or '-'}: {entry['reason']}"
            for report in result["converted"] for entry in report.get("warnings") or []]
    return [*tail(lines, []), *tail(rows, [])]


def assertion(result, command):
    return [f"assertion passed: {result['rule']}"]


def short(value):
    if isinstance(value, str):
        return value if len(value) <= 60 else value[:57] + "…"
    if isinstance(value, bool):
        return "yes" if value else "no"
    return number(value)


def title_of(item):
    for key in ("name", "id", "title", "family", "path", "output", "label"):
        if isinstance(item.get(key), (str, int)):
            return str(item[key])
    return ""


def listing(items, count):
    """The members of a short list of words, or ``count`` when it is long or holds anything else."""
    words = [str(item) for item in items]
    if 0 < len(items) <= 4 and all(isinstance(item, str) and len(item) <= 24 for item in items):
        return ", ".join(words)
    return count


def generic_dict(result, command):
    rows = []
    for key, value in result.items():
        if isinstance(value, (str, int, float, bool)):
            rows.append(f"{key}: {short(value)}")
        elif isinstance(value, list):
            rows.append(f"{key}: {listing(value, plural(len(value), 'item'))}")
        elif isinstance(value, dict):
            rows.append(f"{key}: {listing(list(value), plural(len(value), 'field'))}")
    head = f"{command or 'result'}"
    if not rows:
        return [f"{head}: done"]
    return [head, *tail([f"  {row}" for row in rows], [], limit=12)]


def generic_list(result, command):
    if all(isinstance(item, (str, int, float)) for item in result):
        return [plural(len(result), "item") + (": " + ", ".join(short(item) for item in result[:MAX_ROWS]) if result else "")]
    rows = [f"  {title_of(item) or short(str(item))}" if isinstance(item, dict) else f"  {short(item)}" for item in result]
    return [plural(len(result), "item"), *tail(rows, [])]


def summarize(result, command=None):
    """A short human summary of a CLI result (a dict, a list or a scalar), without a trailing newline."""
    if isinstance(result, dict):
        if "path" in result and "canvas" in result and isinstance(result.get("layers"), int):
            lines = created(result, command)
        elif "canvas" in result and isinstance(result.get("layers"), list):
            lines = state(result, command)
        elif isinstance(result.get("groups"), dict) and "next" in result and command == "schema":
            lines = schema_groups(result, command)
        elif "changes" in result and "success" in result:
            lines = edit(result, command)
        elif "passed" in result and "issues" in result:
            lines = check(result, command)
        elif isinstance(result.get("output"), str) and isinstance(result.get("bytes"), int):
            lines = written(result, command)
        elif "valid" in result and isinstance(result.get("checks"), list):
            lines = validation(result, command)
        elif isinstance(result.get("converted"), list) and isinstance(result.get("summary"), dict):
            lines = conversion(result, command)
        elif result.get("passed") is True and isinstance(result.get("rule"), str):
            lines = assertion(result, command)
        else:
            lines = generic_dict(result, command)
    elif isinstance(result, list):
        if result and all(isinstance(item, dict) and "type" in item and "name" in item for item in result):
            lines = layer_table(result, command)
        elif result and all(isinstance(item, dict) and "parent" in item and "operations" in item for item in result):
            lines = history(result, command)
        elif not result and command == "layers":
            lines = layer_table(result, command)
        else:
            lines = generic_list(result, command)
    else:
        lines = [str(result)]
    return "\n".join(lines)
