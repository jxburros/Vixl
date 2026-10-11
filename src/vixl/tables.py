"""Data-bound tables: rows (inline, or a workspace CSV) drawn as an ordinary group of vector layers.

``table`` lays rows out into one group: cell text, header band, zebra bands and thin rules, sized
together so columns line up and rows grow to fit wrapped text. The group keeps the recipe (rows and
options) under ``table``. ``table-data`` edits the rows (one cell, appended or removed rows and
columns, a CSV reload) and ``table`` with a ``target`` restyles it; both redraw by updating the
existing layers in place (``charts.sync``), so layer IDs and anything added to them survive.

Columns can be aligned left, center, right or on the decimal point (a price list: ``3.25`` and
``12.5`` share the point, ``8`` ends where the point would be). PPTX export swaps the group for a
native, editable table (see ``table_pptx.py``); SVG and PDF draw its layers as vector text and rules.
"""

from copy import deepcopy
import difflib
import math
import re

from .charts import Kit, Parts, Style, contrast, format_number, hex_color, mix, parse_format, place, rgba, sync
from .errors import VixlError, require
from .model import finite, new_layer

TYPES = ("table", "table-data")
DATA_KEYS = ("table", "csv")
MAX_ROWS = 200
MAX_COLUMNS = 24
MAX_CELL = 1000
ALIGNS = ("left", "center", "right", "decimal")
BORDERS = ("horizontal", "all", "outer", "header", "none")
OPTIONS = (
    "header", "columns", "font_size", "header_font_size", "header_font", "body_font", "text_color",
    "header_color", "header_fill", "fill", "zebra", "borders", "border_color", "border_width", "padding",
    "row_height", "number_format",
)
COLUMN_KEYS = ("width", "align", "format")
# Stacking order of generated layers, bottom to top.
Z_FILL, Z_BAND, Z_RULE, Z_TEXT = range(4)
_NUMERIC = re.compile(r"[-+−]?[$€£¥]?\s*[-+]?\d[\d,]*(\.\d+)?\s*%?")


def cell(value, where):
    """A stored cell: text (trimmed), a finite number, or None for an empty cell."""
    if value is None or value == "":
        return None
    require(isinstance(value, (str, int, float)) and not isinstance(value, bool),
            f"{where} must be text, a number or null; got {value!r}", field=where)
    if isinstance(value, float):
        require(math.isfinite(value), f"{where} must be finite", field=where)
        return int(value) if value == int(value) and abs(value) < 1e15 else value
    if isinstance(value, str):
        require(len(value) <= MAX_CELL, f"{where} is longer than {MAX_CELL} characters", field=where)
        return value.strip() or None
    return value


def clean_rows(rows, field="table"):
    """Validate rows: a list of equally long lists of cells (the header row first when there is one)."""
    require(isinstance(rows, list) and 1 <= len(rows) <= MAX_ROWS + 1 and all(isinstance(r, list) for r in rows),
            f"{field} must be rows: a list of 1–{MAX_ROWS + 1} lists of cells", field=field)
    width = len(rows[0])
    require(1 <= width <= MAX_COLUMNS, f"{field} rows need 1–{MAX_COLUMNS} cells", field=field)
    for i, row in enumerate(rows):
        require(len(row) == width, f"{field}[{i}] has {len(row)} cells; every row needs {width} (the first row's)",
                field=f"{field}[{i}]")
    return [[cell(value, f"{field}[{i}][{j}]") for j, value in enumerate(row)] for i, row in enumerate(rows)]


def rows_from_csv(project, source):
    """Rows from a workspace CSV: its header row, then one row per record (``columns`` picks and orders columns)."""
    from .charts import workspace_file
    from .exports import read_csv

    headers, records = read_csv(workspace_file(project, source["csv"]), limit=MAX_ROWS)
    wanted = source.get("columns") or headers
    missing = [name for name in wanted if name not in headers]
    require(not missing, f"columns {', '.join(map(repr, missing))} are not CSV columns; columns: {', '.join(headers)}",
            field="columns", allowed=headers)
    return clean_rows([list(wanted)] + [[record[name] for name in wanted] for record in records], "csv")


def normalize(op, note):
    """``rows``/``data`` spell the inline table, ``striped`` zebra, and a few other common spellings."""
    for old in ("rows", "data", "cells"):
        if isinstance(op.get(old), list) and "table" not in op:
            op["table"] = op.pop(old)
            note(f"{old!r} → 'table'")
    for old, new in (("striped", "zebra"), ("stripes", "zebra"), ("zebra_stripes", "zebra"), ("border", "borders"),
                     ("gridlines", "borders"), ("header_background", "header_fill"), ("background", "fill"),
                     ("cell_padding", "padding"), ("format", "number_format")):
        if old in op and new not in op:
            op[new] = op.pop(old)
            note(f"{old!r} → {new!r}")
    return op


def read_data(project, op, recipe):
    """Replace ``recipe``'s rows when the operation brings them (inline or a CSV)."""
    given = [k for k in DATA_KEYS if k in op]
    if not given:
        return False
    require(len(given) == 1, "Give the rows once: table or csv", field=given[0])
    if "csv" in op:
        source = {"csv": op["csv"], **({"columns": op["csv_columns"]} if op.get("csv_columns") else {})}
        recipe["rows"] = rows_from_csv(project, source)
        recipe["source"] = source
        recipe.setdefault("header", True)
    else:
        recipe["rows"] = clean_rows(op["table"])
        recipe.pop("source", None)
    return True


def header_count(recipe):
    return 1 if recipe.get("header", True) and len(recipe["rows"]) > 1 else 0


def find_row(recipe, wanted, field):
    """The index into ``rows`` of a body row: a 1-based number or the text of its first cell."""
    rows, top = recipe["rows"], header_count(recipe)
    if isinstance(wanted, int) and not isinstance(wanted, bool):
        require(1 <= wanted <= len(rows) - top, f"{field}: row {wanted} does not exist; the table has "
                f"{len(rows) - top} body row(s), numbered from 1", field=field)
        return wanted - 1 + top
    keys = [str(row[0]) if row[0] is not None else "" for row in rows[top:]]
    if str(wanted) in keys:
        return keys.index(str(wanted)) + top
    close = difflib.get_close_matches(str(wanted), keys, 3, 0.5)
    raise VixlError("invalid_operation", f"{field}: no row starts with {wanted!r}; rows: {', '.join(keys[:40])}"
                    + (f". Did you mean {' or '.join(map(repr, close))}?" if close else ""),
                    field=field, allowed=keys[:100], suggestions=close)


def find_column(recipe, wanted, field):
    """The index of a column: a 1-based number or its header text."""
    rows = recipe["rows"]
    if isinstance(wanted, int) and not isinstance(wanted, bool):
        require(1 <= wanted <= len(rows[0]), f"{field}: column {wanted} does not exist; the table has "
                f"{len(rows[0])} column(s), numbered from 1", field=field)
        return wanted - 1
    names = [str(v) if v is not None else "" for v in rows[0]] if header_count(recipe) else []
    if str(wanted) in names:
        return names.index(str(wanted))
    close = difflib.get_close_matches(str(wanted), names, 3, 0.5)
    raise VixlError("invalid_operation", f"{field}: unknown column {wanted!r}"
                    + (f"; columns: {', '.join(names)}" if names else "; this table has no header, use a number")
                    + (f". Did you mean {' or '.join(map(repr, close))}?" if close else ""),
                    field=field, allowed=names, suggestions=close)


def edit_data(project, op, recipe):
    """Apply a ``table-data`` operation: replace or reload, then remove, add and set."""
    changed = read_data(project, op, recipe)
    if op.get("reload"):
        require(recipe.get("source"), "This table is not bound to a CSV; give a csv, or edit its cells directly",
                field="reload")
        recipe["rows"] = rows_from_csv(project, recipe["source"])
        changed = True
    rows = recipe["rows"]
    removed = sorted({find_row(recipe, w, f"remove_rows[{i}]") for i, w in enumerate(op.get("remove_rows", []))},
                     reverse=True)
    for index in removed:
        rows.pop(index)
        changed = True
    dropped = sorted({find_column(recipe, w, f"remove_columns[{i}]") for i, w in enumerate(op.get("remove_columns", []))},
                     reverse=True)
    require(len(dropped) < len(rows[0]) or not dropped, "A table keeps at least one column", field="remove_columns")
    for index in dropped:
        for row in rows:
            row.pop(index)
        columns = recipe.get("columns")
        if isinstance(columns, list) and index < len(columns):
            columns.pop(index)
        changed = True
    for i, item in enumerate(op.get("add_columns", [])):
        require(isinstance(item, dict) and "name" in item, f"add_columns[{i}] must be {{name, values?}}",
                field=f"add_columns[{i}]")
        body = len(rows) - header_count(recipe)
        values = item.get("values", [None] * body)
        require(isinstance(values, list) and len(values) == body,
                f"add_columns[{i}].values needs {body} value(s), one per body row", field=f"add_columns[{i}].values")
        if header_count(recipe):
            rows[0].append(item["name"])
        for row, value in zip(rows[header_count(recipe):], values):
            row.append(value)
        changed = True
    for i, row in enumerate(op.get("append", [])):
        if isinstance(row, dict):
            require(header_count(recipe), f"append[{i}]: name cells by column only on a table with a header",
                    field=f"append[{i}]")
            names = [str(v) for v in rows[0]]
            unknown = sorted(set(map(str, row)) - set(names))
            require(not unknown, f"append[{i}] names unknown column(s) {', '.join(map(repr, unknown))}",
                    field=f"append[{i}]", allowed=names)
            row = [row.get(name) for name in names]
        require(isinstance(row, list) and len(row) == len(rows[0]),
                f"append[{i}] needs {len(rows[0])} cells (or {{column: value}})", field=f"append[{i}]")
        rows.append(list(row))
        changed = True
    rows[:] = clean_rows(rows)
    require(len(rows) - header_count(recipe) <= MAX_ROWS, f"A table holds at most {MAX_ROWS} body rows", "resource_limit",
            field="append")
    for i, edit in enumerate(op.get("set", [])):
        require(isinstance(edit, dict) and {"row", "column", "value"} <= set(edit),
                f"set[{i}] must be {{row, column, value}}", field=f"set[{i}]")
        at = (0 if edit["row"] == 0 and header_count(recipe) else find_row(recipe, edit["row"], f"set[{i}].row"))
        rows[at][find_column(recipe, edit["column"], f"set[{i}].column")] = cell(edit["value"], f"set[{i}].value")
        changed = True
    require(changed, "table-data needs something to change: set, append, remove_rows, add_columns, remove_columns, "
            "reload, or new table or csv rows", field="set")


def merge_options(recipe, op):
    for key in OPTIONS:
        if key not in op:
            continue
        if op[key] is None or op[key] == "":
            recipe.pop(key, None)
        else:
            recipe[key] = deepcopy(op[key])


# Layout -------------------------------------------------------------------------------------------

def numeric_text(value):
    return isinstance(value, (int, float)) or (isinstance(value, str) and _NUMERIC.fullmatch(value.strip()) is not None)


def shown(value, fmt):
    """The text a cell shows: numbers in the column's format (when given), text as it is."""
    if value is None:
        return ""
    if fmt and numeric_text(value):
        number = value
        if isinstance(value, str):
            try:
                number = float(re.sub(r"[^\d.\-]", "", value.replace("−", "-")))
            except ValueError:
                return value
        return format_number(number, fmt)
    if isinstance(value, float):
        return f"{value:.10g}"
    return str(value)


def split_decimal(text):
    """(whole, point and fraction) of a figure, split at its decimal point; text without one is all whole."""
    match = re.search(r"\.(?=\d)", text)
    return (text[:match.start()], text[match.start():]) if match else (text, "")


def column_specs(recipe, count, body):
    """Per-column (width spec, align, number format), with alignment inferred from the body cells."""
    given = recipe.get("columns") or []
    specs = []
    for j in range(count):
        entry = given[j] if j < len(given) and isinstance(given[j], dict) else {}
        values = [row[j] for row in body if row[j] is not None]
        numeric = bool(values) and all(numeric_text(v) for v in values)
        align = entry.get("align") or ("right" if numeric else "left")
        specs.append({"width": entry.get("width", "auto"), "align": align,
                      "format": entry.get("format", recipe.get("number_format") if numeric else None)})
    return specs


def fraction(spec):
    if isinstance(spec, str) and spec.endswith("fr"):
        return float(spec[:-2] or 1)
    return None


def widths_for(specs, natural, minimum, total):
    """Column widths: fixed pixels, ``auto`` (natural width) and ``Nfr`` shares of what is left. With a total
    width, leftover space widens auto columns and a shortfall narrows them toward their longest word."""
    widths = [float(s["width"]) if isinstance(s["width"], (int, float)) else natural[j] for j, s in enumerate(specs)]
    shares = [fraction(s["width"]) for s in specs]
    autos = [j for j, s in enumerate(specs) if s["width"] == "auto"]
    if total is None:
        return [max(1.0, w) for w in widths], False
    flexible = [j for j, share in enumerate(shares) if share]
    fixed = sum(w for j, w in enumerate(widths) if j not in flexible)
    if flexible:
        room = total - fixed
        weight = sum(shares[j] for j in flexible)
        for j in flexible:
            widths[j] = max(minimum[j], room * shares[j] / weight)
    else:
        spare = total - sum(widths)
        if spare > 0 and autos:
            base = sum(natural[j] for j in autos) or 1
            for j in autos:
                widths[j] += spare * natural[j] / base
        elif spare < 0 and autos:
            give = [max(0.0, widths[j] - minimum[j]) for j in autos]
            if sum(give) > 0:
                take = min(1.0, -spare / sum(give))
                for j, slack in zip(autos, give):
                    widths[j] -= slack * take
    used = sum(widths)
    return [max(1.0, w) for w in widths], used > total + 0.5


def wrap(kit, text, size, limit, head):
    """``text`` broken at spaces (and kept at its own line breaks) to fit ``limit`` pixels."""
    lines = []
    for paragraph in text.split("\n"):
        current = ""
        for word in paragraph.split(" "):
            attempt = f"{current} {word}" if current else word
            if current and kit.width(attempt, size, head) > limit:
                lines.append(current)
                current = word
            else:
                current = attempt
        lines.append(current)
    return "\n".join(lines)


def layout(project, recipe, width=None):
    """``(parts, size, summary)``: every layer the table is made of, the table's size and its measurements."""
    rows = recipe["rows"]
    top = header_count(recipe)
    count = len(rows[0])
    body = rows[top:]
    canvas = project.state["canvas"]
    basis = width or canvas["width"]
    probe = {"background": recipe.get("fill"), "text_color": recipe.get("text_color")}
    style = Style(project, probe, basis, basis)
    short = min(canvas["width"], canvas["height"])
    fs = int(round(recipe["font_size"])) if recipe.get("font_size") else style.snap(max(12, min(36, short / 34, basis / 12)))
    hfs = int(round(recipe.get("header_font_size", fs)))
    kit = Kit(project, {"title_font": recipe.get("header_font", "heading"), "label_font": recipe.get("body_font", "body")},
              style)
    pad = recipe.get("padding")
    padx = round(pad if pad is not None else fs * 0.6)
    pady = round(pad if pad is not None else fs * 0.45)
    ink = style.ink
    state = project.state
    header_fill = recipe.get("header_fill")
    header_ink = recipe.get("header_color")
    if not header_ink:
        header_ink = ink
        if header_fill and contrast(state, ink, header_fill) < 4.5:
            header_ink = style.on(header_fill)
    rule = recipe.get("border_color") or hex_color(mix(rgba(state, ink)[:3], style.bg, 0.25))
    weight = recipe.get("border_width", 1)
    zebra = recipe.get("zebra")
    if zebra is True:
        zebra = hex_color(mix(rgba(state, ink)[:3], style.bg, 0.06))
    specs = column_specs(recipe, count, body)

    texts = [[shown(v, specs[j]["format"] if i >= top else None) for j, v in enumerate(row)] for i, row in enumerate(rows)]
    head = [i < top for i in range(len(rows))]
    size_of = [hfs if h else fs for h in head]
    natural, minimum, wholes, points = [], [], [], []
    for j in range(count):
        column = [(texts[i][j], size_of[i], head[i]) for i in range(len(rows))]
        widest = max((kit.width(line, s, h) for t, s, h in column for line in t.split("\n") if line), default=0)
        word = max((kit.width(w, s, h) for t, s, h in column for w in t.split() if w), default=0)
        whole = point = 0.0
        if specs[j]["align"] == "decimal":
            for i in range(top, len(rows)):
                left, right = split_decimal(texts[i][j])
                whole = max(whole, kit.width(left, fs, False) if left else 0)
                point = max(point, kit.width(right, fs, False) if right else 0)
            widest = max(widest, whole + point)
            word = max(word, whole + point)
        natural.append(widest + 2 * padx)
        minimum.append(word + 2 * padx)
        wholes.append(whole)
        points.append(point)
    widths, overflow = widths_for(specs, natural, minimum, width)
    widths = [round(w) for w in widths]
    total = sum(widths)
    if width is not None and not overflow:
        widths[-1] += width - total  # rounding lands on the last column, so the table is exactly as wide as asked
        total = width

    parts = Parts()
    lefts = [sum(widths[:j]) for j in range(count)]
    labs, heights = [], []
    for i, row in enumerate(texts):
        color = header_ink if head[i] else ink
        row_labs, extent = [], 0
        for j, text in enumerate(row):
            if not text:
                row_labs.append(None)
                continue
            align = specs[j]["align"]
            lines = wrap(kit, text, size_of[i], widths[j] - 2 * padx, head[i])
            if align == "decimal" and (head[i] or "\n" in lines):
                align = "right"
            lab = kit.make(lines, size_of[i], color, head[i], "left" if align == "decimal" else align, stage="body")
            ascent, cap = kit.vertical(lab)
            row_labs.append((lab, cap, align))
            extent = max(extent, cap + lab["height"] - lab["base"])
        height = max(round(extent + 2 * pady), int(recipe.get("row_height", 0)), round(fs + 2 * pady))
        labs.append(row_labs)
        heights.append(height)
    tops = [sum(heights[:i]) for i in range(len(rows))]
    total_h = sum(heights)

    if recipe.get("fill"):
        parts.rect("fill", "fill", (0, 0, total, total_h), recipe["fill"], Z_FILL)
    if top and header_fill:
        parts.rect("header-band", "header band", (0, 0, total, heights[0]), header_fill, Z_BAND)
    if zebra:
        for i in range(top + 1, len(rows), 2):
            parts.rect(f"band-{i}", f"band {i}", (0, tops[i], total, heights[i]), zebra, Z_BAND)
    borders = recipe.get("borders", "horizontal")
    w = max(1, round(weight))
    lines = []
    if borders in ("horizontal", "all", "header") and top:
        lines.append(("rule-header", (0, heights[0] - w, total, w * (2 if borders != "all" else 1))))
    if borders in ("horizontal", "all"):
        for i in range(top + 1, len(rows)):
            lines.append((f"rule-{i}", (0, tops[i] - (w // 2), total, w)))
        lines.append(("rule-bottom", (0, total_h - w, total, w)))
    if borders in ("all", "outer"):
        lines.append(("rule-top", (0, 0, total, w)))
        if borders == "outer":
            if top:
                lines.append(("rule-header", (0, heights[0] - w, total, w)))
            lines.append(("rule-bottom", (0, total_h - w, total, w)))
        lines.append(("rule-left", (0, 0, w, total_h)))
        lines.append(("rule-right", (total - w, 0, w, total_h)))
    if borders == "all":
        for j in range(1, count):
            lines.append((f"rule-col-{j}", (lefts[j] - (w // 2), 0, w, total_h)))
    seen = set()
    for key, box in lines:
        if key not in seen:
            seen.add(key)
            parts.rect(key, key.replace("-", " "), box, rule, Z_RULE)

    for i, row_labs in enumerate(labs):
        for j, item in enumerate(row_labs):
            if item is None:
                continue
            lab, cap, align = item
            base = tops[i] + pady + cap
            left, right = lefts[j] + padx, lefts[j] + widths[j] - padx
            if align == "decimal":
                whole, _ = split_decimal(texts[i][j])
                x = right - points[j] - (kit.width(whole, fs, False) if whole else 0)
                place(parts, f"cell-{i}-{j}", f"r{i}c{j + 1}" if not head[i] else f"h{j + 1}", lab, x, base, Z_TEXT)
            else:
                x = {"left": left, "center": (left + right) / 2, "right": right}[align]
                anchor = {"left": "left", "center": "center", "right": "right"}[align]
                place(parts, f"cell-{i}-{j}", f"r{i}c{j + 1}" if not head[i] else f"h{j + 1}", lab, x, base, Z_TEXT,
                      anchor=anchor)
    summary = {"rows": len(body), "columns": count, "header": bool(top), "column_widths": widths,
               "row_heights": heights, "font_size": fs, "overflow": overflow,
               "aligns": [s["align"] for s in specs]}
    if overflow:
        summary["needed_width"] = round(sum(minimum))
    return parts, (max(1, total), max(1, total_h)), summary


def redraw(project, group, recipe, width=None):
    """Lay the recipe out again into ``group`` (at ``width`` when given) and record its measurements."""
    check_options(project.state, recipe)
    asked = width if width is not None else recipe.get("width")
    parts, (w, h), summary = layout(project, recipe, asked)
    summary["layers"] = sync(project, group, parts, field="table_part")
    if asked is not None:
        recipe["width"] = asked
    recipe["summary"] = summary
    group["table"] = recipe
    group["content_width"], group["content_height"] = w, h
    group["width"], group["height"] = w, h
    project.state["active_layer"] = group["id"]
    if summary["overflow"]:
        from .notices import warn

        warn(project, f"Table {group['name']!r} needs about {summary['needed_width']} px but is {asked} px wide: "
                      "its text runs past its columns. Widen it, lower font_size, or give columns fixed widths")


def execute(project, op):
    from .operations import append_layer, default_name

    if op["type"] == "table-data":
        group = project.layer(op.get("target"))
        require(group["type"] == "group" and "table" in group, f"{group['name']!r} is not a table; target a table group",
                field="target")
        recipe = deepcopy(group["table"])
        edit_data(project, op, recipe)
        return redraw(project, group, recipe)
    target = project.layer(op["target"]) if op.get("target") else None
    if target is not None:
        require(target["type"] == "group" and "table" in target, f"{target['name']!r} is not a table; target a table "
                "group or omit target to draw a new one", field="target")
    recipe = deepcopy(target["table"]) if target else {"header": True}
    merge_options(recipe, op)
    if not read_data(project, op, recipe):
        require(target is not None, "A table needs rows: table (a header row, then one list per row) or csv",
                field="table")
    if target is not None:
        if "name" in op and op["name"] != target["name"]:
            from .operations import unique_name

            target["name"] = unique_name(project, op["name"])
        for axis in ("x", "y"):
            if axis in op:
                target[axis], target["constraints"] = op[axis], {}
        if "width" in op:
            project.limits.size(op["width"], 1)
        return redraw(project, target, recipe, op.get("width"))
    group = new_layer(op["name"] if "name" in op else default_name(project, "table"), "group", 1, 1,
                      x=op.get("x", 0), y=op.get("y", 0), content_width=1, content_height=1)
    append_layer(project, group)
    redraw(project, group, recipe, op.get("width"))


def check_color(state, value, field):
    from .charts import check_color as chart_color

    chart_color(state, value, field)


def check_options(state, recipe):
    """Validate a table recipe (also run when a document is loaded)."""
    clean_rows(recipe.get("rows"), "rows")
    require(type(recipe.get("header", True)) is bool, "header must be true or false", field="header")
    columns = recipe.get("columns", [])
    require(isinstance(columns, list) and len(columns) <= MAX_COLUMNS, f"columns lists up to {MAX_COLUMNS} column "
            "settings", field="columns")
    for j, entry in enumerate(columns):
        require(isinstance(entry, dict) and set(entry) <= set(COLUMN_KEYS),
                f"columns[{j}] must be {{width?, align?, format?}}", field=f"columns[{j}]")
        width = entry.get("width", "auto")
        require((isinstance(width, (int, float)) and not isinstance(width, bool) and 1 <= width <= 20000)
                or width == "auto" or (isinstance(width, str) and re.fullmatch(r"\d*(\.\d+)?fr", width)
                                       and (fraction(width) or 0) > 0),
                f"columns[{j}].width is pixels, 'auto' or a share such as '1fr' or '2fr'", field=f"columns[{j}].width")
        require(entry.get("align", "left") in ALIGNS, f"columns[{j}].align is one of {', '.join(ALIGNS)}",
                field=f"columns[{j}].align", allowed=list(ALIGNS))
        if entry.get("format"):
            parse_format(entry["format"])
    if recipe.get("number_format"):
        parse_format(recipe["number_format"])
    require(recipe.get("borders", "horizontal") in BORDERS, f"borders is one of {', '.join(BORDERS)}", field="borders",
            allowed=list(BORDERS))
    for key in ("text_color", "header_color", "header_fill", "fill", "border_color"):
        if recipe.get(key):
            check_color(state, recipe[key], key)
    if recipe.get("zebra") not in (None, True, False):
        check_color(state, recipe["zebra"], "zebra")
    for key, low, high in (("font_size", 6, 300), ("header_font_size", 6, 300), ("border_width", 0.5, 20),
                           ("padding", 0, 200), ("row_height", 0, 2000), ("width", 1, 20000)):
        if key in recipe:
            finite(recipe[key], key, low, high)
    allowed = ["heading", "body", "DejaVuSans.ttf", *state.get("fonts", {})]
    for key in ("header_font", "body_font"):
        require(recipe.get(key, "body") in allowed, f"{key} must be a registered font or the heading or body role; "
                f"available: {', '.join(allowed)}", field=key, allowed=allowed)


def validate_table(layer, state):
    """A loaded table group carries a well-formed recipe."""
    if layer["type"] != "group":
        return
    import json

    require(isinstance(layer["table"], dict) and len(json.dumps(layer["table"])) <= 4_000_000, "Invalid table recipe",
            "invalid_project")
    check_options(state, layer["table"])


def schemas(add):
    from .schema import COORD, SIZE

    S, B, N = {"type": "string"}, {"type": "boolean"}, {"type": "number"}
    value = {"type": ["string", "number", "null"]}
    index = {"type": ["string", "integer"]}

    def d(schema, text):
        return {**schema, "description": text}

    def nullable(schema):
        schema = deepcopy(schema)
        if "anyOf" in schema:
            schema["anyOf"].append({"type": "null"})
        elif "enum" in schema:
            schema["enum"] = [*schema["enum"], None]
        else:
            schema["type"] = [schema["type"], "null"] if isinstance(schema["type"], str) else [*schema["type"], "null"]
        return schema

    column = {"type": "object", "properties": {
        "width": d({"type": ["number", "string"]}, "Pixels, 'auto' (fits its widest cell; the default) or a share "
                   "of the remaining width such as '1fr' or '2fr'."),
        "align": d({"enum": list(ALIGNS)}, "left, center, right, or decimal (figures share their decimal point: "
                   "prices). Default: right for numeric columns, else left."),
        "format": d(S, "Excel-style number format for this column's numbers, such as '$#,##0.00' or '0.0%'.")},
        "additionalProperties": False}
    data = {
        "table": d({"type": "array", "items": {"type": "array", "items": value, "maxItems": MAX_COLUMNS},
                    "minItems": 1, "maxItems": MAX_ROWS + 1},
                   "Rows of cells (text, numbers or null): the header row first (unless header is false), then the body."),
        "csv": d(S, "Workspace-relative CSV: its header row and records become the rows. table-data reload re-reads it."),
        "csv_columns": d({"type": "array", "items": S, "minItems": 1, "maxItems": MAX_COLUMNS},
                         "CSV columns to show, in this order (default: all)."),
    }
    options = {
        "header": d(B, "The first row is a header, set in the header font with a rule under it (default true)."),
        "columns": d({"type": "array", "items": column, "maxItems": MAX_COLUMNS},
                     "Per-column width, align and format, in column order; missing entries use the defaults."),
        "font_size": d(N, "Body text size in pixels (default: scaled to the table width)."),
        "header_font_size": d(N, "Header text size in pixels (default: font_size)."),
        "header_font": d(S, "Registered font or the heading/body role for the header row (default heading)."),
        "body_font": d(S, "Registered font or the heading/body role for the body (default body)."),
        "text_color": d(S, "Body text color (default: @ink, else dark or light to suit the fill)."),
        "header_color": d(S, "Header text color (default: the text color, or white/black to read on header_fill)."),
        "header_fill": d(S, "Band behind the header row (default: none)."),
        "fill": d(S, "Background behind the whole table (default: none; the canvas shows through)."),
        "zebra": d({"type": ["boolean", "string"]}, "Shade every other body row: true for a faint tint of the text "
                   "color, or a color."),
        "borders": d({"enum": list(BORDERS)}, "Rules: horizontal (default: under the header and between rows), all "
                     "(a full grid), outer (a frame and the header rule), header (only under the header) or none."),
        "border_color": d(S, "Rule color (default: the text color faded toward the background)."),
        "border_width": d(N, "Rule thickness in pixels (default 1; the header rule is twice as thick)."),
        "padding": d(N, "Space inside each cell in pixels (default: from the font size)."),
        "row_height": d(N, "Minimum row height in pixels; rows still grow to fit wrapped text."),
        "number_format": d(S, "Excel-style format for numbers in every numeric column, unless the column sets its own."),
    }
    frame = {"target": d(S, "Existing table group to restyle, resize or give new rows; omit to draw a new table."),
             "name": d(S, "Group name; the layers inside are named NAME/part."), "x": COORD, "y": COORD,
             "width": d(SIZE, "Table width; columns share it (default: the width the cells need).")}
    add("table", {**frame, **data, **{k: nullable(v) for k, v in options.items()}},
        description="Draw a table from rows or a CSV as vector layers (aligned columns, header, rules), or restyle one.")
    add("table-data", {
        "target": d(S, "Table group ID or name (default: the active layer)."),
        "set": d({"type": "array", "items": {"type": "object", "properties": {
            "row": d(index, "Body row number from 1, or the text of its first cell; 0 is the header row."),
            "column": d(index, "Column number from 1, or its header text."),
            "value": d(value, "New cell value; null empties it.")}, "required": ["row", "column", "value"],
            "additionalProperties": False}, "minItems": 1, "maxItems": 2000}, "Cell edits, e.g. a new price."),
        "append": d({"type": "array", "items": {"anyOf": [{"type": "array", "items": value},
                                                          {"type": "object", "additionalProperties": value}]},
                     "minItems": 1, "maxItems": MAX_ROWS}, "New rows at the end: a list of cells, or {column: value}."),
        "remove_rows": d({"type": "array", "items": index, "minItems": 1}, "Body rows to drop (numbers or first cells)."),
        "add_columns": d({"type": "array", "items": {"type": "object", "properties": {
            "name": d(value, "Header text of the new column."),
            "values": d({"type": "array", "items": value}, "One value per body row (default: empty).")},
            "required": ["name"], "additionalProperties": False}, "minItems": 1}, "Columns to add at the right."),
        "remove_columns": d({"type": "array", "items": index, "minItems": 1}, "Columns to drop (numbers or header text)."),
        "reload": d(B, "Re-read the CSV the table is bound to."),
        **data,
    }, description="Edit a table's rows in place: cells, added or removed rows and columns, a CSV reload or new rows; "
                   "it redraws with the same layer IDs.")


def compile_command(cmd, args):
    if cmd not in TYPES:
        return None
    import json

    from .commands import Parser, number_or_center

    p = Parser(prog=f"vixl {cmd}", description="Data-bound tables; vixl schema lists every field.")
    op = {"type": cmd}
    p.add_argument("--target")
    p.add_argument("--csv", help="workspace CSV: its header row and records")
    p.add_argument("--table", type=json.loads, help='JSON rows, e.g. [["Item","Price"],["Tea",3.25]]')
    if cmd == "table":
        p.add_argument("--name")
        for key in ("x", "y"):
            p.add_argument("--" + key, type=number_or_center)
        p.add_argument("--width", type=int)
        p.add_argument("--csv-columns", help="comma-separated CSV columns to show")
        p.add_argument("--columns", type=json.loads, help='JSON list of {"width", "align", "format"} per column')
        p.add_argument("--align", help="comma-separated align per column: left, center, right or decimal")
        for key in ("header-font", "body-font", "text-color", "header-color", "header-fill", "fill", "border-color",
                    "number-format"):
            p.add_argument("--" + key)
        p.add_argument("--zebra", nargs="?", const="true", help="shade alternate rows (optionally a color)")
        p.add_argument("--borders", choices=list(BORDERS))
        for key in ("font-size", "header-font-size", "border-width", "padding", "row-height"):
            p.add_argument("--" + key, type=float)
        p.add_argument("--no-header", dest="header", action="store_false", default=None)
    else:
        p.add_argument("--set", action="append", metavar="ROW:COLUMN=VALUE", help="set one cell (blank empties it)")
        p.add_argument("--append", action="append", metavar="JSON", type=json.loads, help="a row as a JSON list")
        p.add_argument("--remove-row", action="append", dest="remove_rows")
        p.add_argument("--remove-column", action="append", dest="remove_columns")
        p.add_argument("--reload", action="store_true", default=None, help="re-read the bound CSV")
    a = vars(p.parse_args(args))
    align = a.pop("align", None)
    for key, value in a.items():
        if value is None:
            continue
        if key == "csv_columns":
            value = [v.strip() for v in value.split(",") if v.strip()]
        elif key == "zebra":
            value = True if value == "true" else value
        elif key == "set":
            value = [parse_set(item) for item in value]
        elif key in ("remove_rows", "remove_columns"):
            value = [int(v) if v.isdigit() else v for v in value]
        op[key] = value
    if align:
        columns = op.get("columns") or []
        names = [v.strip() for v in align.split(",")]
        op["columns"] = [{**(columns[j] if j < len(columns) else {}), **({"align": n} if n else {})}
                         for j, n in enumerate(names)] + columns[len(names):]
    return op


def parse_set(item):
    require("=" in item and ":" in item.split("=", 1)[0], "Use --set ROW:COLUMN=VALUE", "usage_error")
    left, value = item.split("=", 1)
    row, column = left.rsplit(":", 1)
    as_index = lambda text: int(text) if text.isdigit() else text  # noqa: E731
    number = value.strip()
    try:
        parsed = int(number) if re.fullmatch(r"-?\d+", number) else float(number) if re.fullmatch(r"-?\d*\.\d+", number) else value
    except ValueError:
        parsed = value
    return {"row": as_index(row), "column": as_index(column), "value": parsed if value != "" else None}
