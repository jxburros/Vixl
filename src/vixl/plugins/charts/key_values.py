"""Key–value lists: a label, a value and an optional share per row, in aligned columns with rules between rows.

``key-value-list`` draws rows into one group of text layers and thin rules: labels flush left, values and
shares right-aligned on shared edges (so figures line up even in fonts whose digits are proportional), rows
spaced from the spacing scale (one unit above and below each line, a hairline rule between rows). The group
keeps the recipe under ``key_values``; ``key-value-list`` with a ``target`` restyles it or gives it new rows and
updates the layers in place (``charts.sync``), so layer IDs survive. ``shares: "auto"`` computes each row's share
of the total from numeric values.

``ValueList`` is the geometry. A chart's ``legend_values`` legend is a ``ValueList`` too (swatch, name, total
and, for pies and donuts, the share), so a chart's value legend and a standalone list agree. The
``key-value-list`` container resource places one under a title.
"""

from copy import deepcopy
import re

from ...errors import require
from ...model import finite, new_layer

TYPES = ("key-value-list",)
MAX_ROWS = 200
MAX_TEXT = 500
OPTIONS = ("font_size", "font", "value_font", "text_color", "share_color", "rule_color", "rules", "colors",
           "number_format", "shares")
# Stacking order of generated layers, bottom to top.
Z_RULE, Z_SWATCH, Z_TEXT = 0, 1, 2
_NUMBER = re.compile(r"[-+−]?[$€£¥]?\s*\d[\d,]*(\.\d+)?\s*%?")


class ValueList:
    """Rows of (label, value, share, swatch color) measured into columns before they are placed.

    Spacing comes from the spacing scale for the text size (``craft.spacing_unit``, half the body): one unit
    above and below each line, a one-unit gap after a swatch, two units between label and value and between
    value and share. Given a ``width``, the value and share columns move to its right edge and labels wrap to
    the room left; without one the list is as wide as its widest row."""

    def __init__(self, kit, size, rows, *, width=None, swatch=False, ink, value_ink=None, share_ink=None,
                 value_head=False):
        from ...craft import spacing_unit

        self.kit, self.size = kit, size
        self.unit = unit = spacing_unit(size)
        self.pad = unit
        self.gap = 2 * unit
        self.swatch = round(size * 0.8) if swatch else 0
        self.lead = self.swatch + unit if swatch else 0
        self.rule = max(1, round(unit / 8))
        value_ink, share_ink = value_ink or ink, share_ink or ink
        values = [kit.make(r[1], size, value_ink, value_head, "right", stage="body") if r[1] else None for r in rows]
        shares = [kit.make(r[2], size, share_ink, False, "right", stage="body") if r[2] else None for r in rows]
        self.value_w = max((v["width"] for v in values if v), default=0)
        self.share_w = max((s["width"] for s in shares if s), default=0)
        figures = (self.gap + self.value_w if self.value_w else 0) + (self.gap + self.share_w if self.share_w else 0)
        natural = max((kit.width(r[0], size) for r in rows if r[0]), default=0)
        room = None
        if width is not None:
            room = max(1, width - self.lead - figures)
        labels = []
        for row in rows:
            text = row[0] or ""
            if text and room is not None and kit.width(text, size) > room:
                text = kit.wrap(text, size, room, lines=4)
            labels.append(kit.make(text, size, ink, stage="body") if text else None)
        label_w = max((lab["width"] for lab in labels if lab), default=0) if room is None else min(natural, room)
        self.width = round(max(width or 0, self.lead + label_w + figures))
        self.overflow = room is not None and any(lab and lab["width"] > room + 0.5 for lab in labels)
        # Every column on a row shares one baseline: the row is as tall as its deepest entry plus the padding.
        # Rows keep one rhythm: one baseline depth and one row height for every single-line row, whatever
        # its letters (descenders, figures); a wrapped label makes its own row taller.
        entries = [[e for e in (labels[i], values[i], shares[i]) if e] for i in range(len(rows))]
        cap = max((kit.vertical(e)[1] for row in entries for e in row), default=size * 0.7)
        depths = [max((cap + e["height"] - e["base"] for e in row), default=size) for row in entries]
        single = max((d for d, lab in zip(depths, labels) if not (lab and "\n" in lab["text"])), default=size)
        self.rows, y = [], 0
        for i, row in enumerate(rows):
            height = round(max(depths[i], single) + 2 * self.pad)
            self.rows.append({"top": y, "height": height, "base": y + self.pad + cap, "cap": cap,
                              "label": labels[i], "value": values[i], "share": shares[i], "color": row[3]})
            y += height + (self.rule if i < len(rows) - 1 else 0)
        self.height = max(1, y)

    def columns(self):
        """``(label left, value right edge, share right edge)`` relative to the list's left."""
        share_right = self.width
        value_right = self.width - (self.gap + self.share_w if self.share_w else 0)
        return self.lead, value_right, share_right

    def emit(self, parts, ox, oy, prefix="", rule_color=None, z=(Z_RULE, Z_SWATCH, Z_TEXT), label="row"):
        """Add the list's swatches, texts and rules to ``parts`` with its top-left at (ox, oy); returns its box."""
        from .charts import place

        z_rule, z_swatch, z_text = z if isinstance(z, tuple) else (z, z, z)
        left, value_right, share_right = self.columns()
        for i, row in enumerate(self.rows):
            n = i + 1
            if row["color"] is not None and self.swatch:
                mid = oy + row["base"] - row["cap"] / 2
                parts.rect(f"{prefix}swatch-{i}", f"{label} swatch {n}",
                           (round(ox), round(mid - self.swatch / 2), self.swatch, self.swatch), row["color"], z_swatch)
            base = oy + row["base"]
            if row["label"]:
                place(parts, f"{prefix}label-{i}", f"{label} label {n}", row["label"], ox + left, base, z_text)
            if row["value"]:
                place(parts, f"{prefix}value-{i}", f"{label} value {n}", row["value"], ox + value_right, base, z_text,
                      anchor="right")
            if row["share"]:
                place(parts, f"{prefix}share-{i}", f"{label} share {n}", row["share"], ox + share_right, base, z_text,
                      anchor="right")
            if rule_color and i < len(self.rows) - 1:
                parts.rect(f"{prefix}rule-{i}", f"{label} rule {n}",
                           (round(ox), round(oy + row["top"] + row["height"]), round(self.width), self.rule),
                           rule_color, z_rule)
        return (round(ox), round(oy), self.width, self.height)


# Rows -------------------------------------------------------------------------------------------------------

def _text(value, where):
    if value is None:
        return ""
    require(isinstance(value, (str, int, float)) and not isinstance(value, bool),
            f"{where} must be text or a number; got {value!r}", field=where)
    if isinstance(value, float):
        finite(value, where, -1e15, 1e15)
        return int(value) if value == int(value) and abs(value) < 1e15 else value
    if isinstance(value, str):
        require(len(value) <= MAX_TEXT, f"{where} is longer than {MAX_TEXT} characters", field=where)
        return value.strip()
    return value


def parse_items(text):
    """Rows from text: one row per line, ``label | value | share`` (the share is optional)."""
    require(isinstance(text, str) and len(text) <= MAX_ROWS * MAX_TEXT, "items is text: one row per line, "
            "label | value | share", field="items")
    rows = []
    for line in text.split("\n"):
        if not line.strip():
            continue
        cells = [cell.strip() for cell in line.split("|")]
        require(len(cells) <= 3, f"Each items line is label | value | share; {line!r} has {len(cells)} parts",
                field="items")
        rows.append({"label": cells[0], "value": cells[1] if len(cells) > 1 else "", "share": cells[2] if len(cells) > 2 else ""})
    return rows


def clean_rows(rows, field="rows"):
    """Rows as ``[{label, value, share}]`` from objects or ``[label, value, share]`` lists."""
    require(isinstance(rows, list) and 1 <= len(rows) <= MAX_ROWS, f"{field} lists 1–{MAX_ROWS} rows", field=field)
    result = []
    for i, row in enumerate(rows):
        where = f"{field}[{i}]"
        if isinstance(row, (list, tuple)):
            require(1 <= len(row) <= 3, f"{where} is [label, value] or [label, value, share]", field=where)
            row = dict(zip(("label", "value", "share"), row))
        require(isinstance(row, dict) and set(row) <= {"label", "value", "share"},
                f"{where} is {{label, value, share?}} or [label, value, share?]", field=where)
        result.append({key: _text(row.get(key), f"{where}.{key}") for key in ("label", "value", "share")})
    return result


def _number(value):
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str) and _NUMBER.fullmatch(value.strip()):
        try:
            return float(re.sub(r"[^\d.\-]", "", value.replace("−", "-")))
        except ValueError:
            return None
    return None


def shown_rows(recipe):
    """``[(label, value, share)]`` as the list shows them: numbers formatted, ``shares: "auto"`` computed."""
    from .charts import format_number

    fmt = recipe.get("number_format")
    rows = recipe["rows"]
    shares = None
    if recipe.get("shares") == "auto":
        numbers = [_number(r["value"]) for r in rows]
        require(all(n is not None and n >= 0 for n in numbers),
                "shares: \"auto\" needs a number of zero or more as every row's value", field="shares")
        total = sum(numbers)
        require(total > 0, "shares: \"auto\" needs a positive total", field="shares")
        fractions = [n / total for n in numbers]
        percent = "0%" if all(abs(f * 100 - round(f * 100)) < 0.05 for f in fractions) else "0.0%"
        shares = [format_number(f, percent) for f in fractions]

    def show(value):
        if isinstance(value, (int, float)):
            return format_number(value, fmt) if fmt else f"{value:.10g}"
        return value or ""

    return [(show(r["label"]), show(r["value"]), shares[i] if shares else show(r["share"])) for i, r in enumerate(rows)]


# Layout and operation ---------------------------------------------------------------------------------------

def layout(project, recipe, width=None):
    """``(parts, size, summary)``: every layer the list is made of, its size and its measurements."""
    from .charts import Kit, Parts, Style, hex_color, mix, rgba
    from ...craft import body_size

    canvas = project.state["canvas"]
    style = Style(project, {"text_color": recipe.get("text_color"), "font_size": 12}, canvas["width"], canvas["height"])
    size = int(round(recipe["font_size"])) if recipe.get("font_size") else body_size(project)
    kit = Kit(project, {"title_font": recipe.get("value_font", "body"), "label_font": recipe.get("font", "body")}, style)
    state = project.state
    ink = style.ink
    rows = shown_rows(recipe)
    colors = recipe.get("colors") or []
    entries = [(*row, colors[i % len(colors)] if colors else None) for i, row in enumerate(rows)]
    share_ink = recipe.get("share_color") or style.muted
    values = ValueList(kit, size, entries, width=width, swatch=bool(colors), ink=ink, share_ink=share_ink,
                       value_head="value_font" in recipe)
    rule = None
    if recipe.get("rules", True):
        rule = recipe.get("rule_color") or hex_color(mix(rgba(state, ink)[:3], style.bg, 0.25))
    parts = Parts()
    values.emit(parts, 0, 0, rule_color=rule)
    left, value_right, share_right = values.columns()
    summary = {"rows": len(rows), "font_size": size, "unit": values.unit, "row_heights": [r["height"] for r in values.rows],
               "columns": {"label": left, "value_right": value_right, **({"share_right": share_right} if values.share_w else {})},
               "overflow": values.overflow}
    return parts, (max(1, values.width), values.height), summary


def redraw(project, group, recipe, width=None):
    """Lay the recipe out again into ``group`` (at ``width`` when given) and record its measurements."""
    from .charts import sync

    check_options(project.state, recipe)
    asked = width if width is not None else recipe.get("width")
    parts, (w, h), summary = layout(project, recipe, asked)
    summary["layers"] = sync(project, group, parts, field="kv_part")
    if asked is not None:
        recipe["width"] = asked
    recipe["summary"] = summary
    group["key_values"] = recipe
    group["content_width"], group["content_height"] = w, h
    group["width"], group["height"] = w, h
    project.state["active_layer"] = group["id"]
    if summary["overflow"]:
        from ...notices import warn

        warn(project, f"Key-value list {group['name']!r} is {asked} px wide, too narrow for a label beside its "
                      "figures; widen it or lower font_size")


def fit(project, group, width, height, minimum=12):
    """Redraw ``group`` at ``width``, stepping its text size down (to ``minimum``) until it is at most ``height`` tall."""
    recipe = deepcopy(group["key_values"])
    size = recipe.get("container_font_size") or recipe.get("font_size")
    if size is None:
        from ...craft import body_size

        size = body_size(project)
    recipe["container_font_size"] = size
    while True:
        recipe["font_size"] = size
        redraw(project, group, recipe, width)
        if group["height"] <= height or size <= minimum:
            return group["height"] <= height
        size -= 1
        recipe = deepcopy(group["key_values"])


def merge_options(recipe, op):
    for key in OPTIONS:
        if key not in op:
            continue
        if op[key] is None or op[key] == "":
            recipe.pop(key, None)
        else:
            recipe[key] = deepcopy(op[key])


def read_rows(op, recipe):
    given = [k for k in ("rows", "items") if k in op]
    if not given:
        return False
    require(len(given) == 1, "Give the rows once: rows or items", field=given[0])
    recipe["rows"] = clean_rows(op["rows"]) if "rows" in op else clean_rows(parse_items(op["items"]), "items")
    return True


def normalize(op, note):
    """``entries``/``data``/``pairs`` spell the rows, and a few other common spellings."""
    for old in ("entries", "data", "pairs"):
        if isinstance(op.get(old), list) and "rows" not in op:
            op["rows"] = op.pop(old)
            note(f"{old!r} → 'rows'")
    for old, new in (("color", "text_color"), ("size", "font_size"), ("dividers", "rules"), ("divider_color", "rule_color"),
                     ("percent_color", "share_color"), ("format", "number_format"), ("swatches", "colors")):
        if old in op and new not in op:
            op[new] = op.pop(old)
            note(f"{old!r} → {new!r}")
    return op


def execute(project, op):
    from ...operations import append_layer, default_name, unique_name

    target = project.layer(op["target"]) if op.get("target") else None
    if target is not None:
        require(target["type"] == "group" and "key_values" in target, f"{target['name']!r} is not a key-value list; "
                "target a key-value-list group or omit target to draw a new one", field="target")
    recipe = deepcopy(target["key_values"]) if target else {}
    merge_options(recipe, op)
    if not read_rows(op, recipe):
        require(target is not None, "A key-value list needs rows (a list of {label, value, share}) or items "
                "(one 'label | value | share' per line)", field="rows")
    if target is not None:
        if "name" in op and op["name"] != target["name"]:
            target["name"] = unique_name(project, op["name"])
        for axis in ("x", "y"):
            if axis in op:
                target[axis], target["constraints"] = op[axis], {}
        if "width" in op:
            project.limits.size(op["width"], 1)
        return redraw(project, target, recipe, op.get("width"))
    group = new_layer(op["name"] if "name" in op else default_name(project, "key-value-list"), "group", 1, 1,
                      x=op.get("x", 0), y=op.get("y", 0), content_width=1, content_height=1)
    append_layer(project, group)
    redraw(project, group, recipe, op.get("width"))


def check_options(state, recipe):
    """Validate a key-value-list recipe (also run when a document is loaded)."""
    from .charts import check_color, parse_format

    clean_rows(recipe.get("rows"))
    for key in ("text_color", "share_color", "rule_color"):
        if recipe.get(key):
            check_color(state, recipe[key], key)
    colors = recipe.get("colors", [])
    require(isinstance(colors, list) and len(colors) <= 64, "colors lists up to 64 swatch colors", field="colors")
    for color in colors:
        check_color(state, color, "colors")
    require(type(recipe.get("rules", True)) is bool, "rules must be true or false", field="rules")
    require(recipe.get("shares") in (None, "auto"), "shares is \"auto\" (each value's share of the total) or omitted",
            field="shares")
    if recipe.get("number_format"):
        parse_format(recipe["number_format"])
    for key, low, high in (("font_size", 4, 300), ("container_font_size", 4, 300), ("width", 1, 20000)):
        if key in recipe:
            finite(recipe[key], key, low, high)
    allowed = ["heading", "body", "DejaVuSans.ttf", *state.get("fonts", {})]
    for key in ("font", "value_font"):
        require(recipe.get(key, "body") in allowed, f"{key} must be a registered font or the heading or body role; "
                f"available: {', '.join(allowed)}", field=key, allowed=allowed)


def validate(layer, state):
    """A loaded key-value-list group carries a well-formed recipe."""
    if layer["type"] != "group":
        return
    import json

    require(isinstance(layer["key_values"], dict) and len(json.dumps(layer["key_values"])) <= 1_000_000,
            "Invalid key-value list recipe", "invalid_project")
    check_options(state, layer["key_values"])


def schemas(add):
    from ...schema import COORD, SIZE

    S, B, N = {"type": "string"}, {"type": "boolean"}, {"type": "number"}
    cell = {"type": ["string", "number", "null"]}

    def d(schema, text):
        return {**schema, "description": text}

    def nullable(schema):
        schema = deepcopy(schema)
        if "enum" in schema:
            schema["enum"] = [*schema["enum"], None]
        else:
            schema["type"] = [schema["type"], "null"] if isinstance(schema["type"], str) else [*schema["type"], "null"]
        return schema

    row = {"anyOf": [
        {"type": "object", "properties": {"label": d(cell, "Row label, set flush left."),
                                          "value": d(cell, "Row value, right-aligned on the value column's edge."),
                                          "share": d(cell, "Optional share (a percentage), right-aligned in its own column.")},
         "additionalProperties": False},
        {"type": "array", "items": cell, "minItems": 1, "maxItems": 3}]}
    options = {
        "font_size": d(N, "Text size in pixels (default: the document's body size). Row padding and column gaps follow "
                       "it through the spacing scale."),
        "font": d(S, "Registered font or the heading/body role for the labels (default body)."),
        "value_font": d(S, "Registered font or the heading/body role for values (default: the label font)."),
        "text_color": d(S, "Label and value color (default: @ink, else dark or light to suit the background)."),
        "share_color": d(S, "Share color (default: the text color faded toward the background, still 4.5:1)."),
        "rule_color": d(S, "Color of the rules between rows (default: the text color faded toward the background)."),
        "rules": d(B, "Draw a hairline rule between rows (default true)."),
        "colors": d({"type": "array", "items": S, "maxItems": 64},
                    "A swatch color per row, set before the label (a legend); repeats when shorter than the rows."),
        "number_format": d(S, "Excel-style format for numeric values, such as '#,##0' or '$#,##0.00'."),
        "shares": d({"enum": ["auto"]}, "auto: compute each row's share of the total from numeric values, as a "
                    "percentage in the share column."),
    }
    add("key-value-list", {
        "target": d(S, "Existing key-value list group to restyle, resize or give new rows; omit to draw a new list."),
        "name": d(S, "Group name; the layers inside are named NAME/part."), "x": COORD, "y": COORD,
        "width": d(SIZE, "List width: values and shares sit at its right edge and labels wrap to fit (default: the "
                   "width the rows need)."),
        "rows": d({"type": "array", "items": row, "minItems": 1, "maxItems": MAX_ROWS},
                  "Rows as {label, value, share?} or [label, value, share?]."),
        "items": d(S, "Rows as text, one per line: 'label | value | share' (share optional)."),
        **{k: nullable(v) for k, v in options.items()},
    }, description="Draw a key-value list (labels left; values and shares right-aligned in columns; rules between "
                   "rows) as editable text layers, or restyle one.")


def compile_command(cmd, args):
    if cmd not in TYPES:
        return None
    import json

    from ...commands import Parser, number_or_center

    p = Parser(prog=f"vixl {cmd}", description="Key-value lists; vixl schema lists every field.")
    p.add_argument("--target")
    p.add_argument("--name")
    p.add_argument("--items", help="one row per line (\\n): label | value | share")
    p.add_argument("--rows", type=json.loads, help='JSON rows, e.g. [["Drip", 15900, "44.6%%"]]')
    for key in ("x", "y"):
        p.add_argument("--" + key, type=number_or_center)
    p.add_argument("--width", type=int)
    for key in ("font", "value-font", "text-color", "share-color", "rule-color", "number-format"):
        p.add_argument("--" + key)
    p.add_argument("--font-size", type=float)
    p.add_argument("--colors", help="comma-separated swatch colors, one per row")
    p.add_argument("--no-rules", dest="rules", action="store_false", default=None)
    p.add_argument("--auto-shares", dest="shares", action="store_const", const="auto")
    op = {"type": cmd}
    for key, value in vars(p.parse_args(args)).items():
        if value is None:
            continue
        if key == "items":
            value = value.replace("\\n", "\n")
        elif key == "colors":
            value = [v.strip() for v in value.split(",") if v.strip()]
        op[key] = value
    return op
