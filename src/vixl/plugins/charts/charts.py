"""Data-bound charts: a table becomes an ordinary group of vector layers kept in sync with it.

``chart`` draws bars, stacked or 100 % bars (vertical or horizontal), lines, areas, pies and
donuts from a table (inline, or a workspace CSV) into one group: rectangles, paths, text and thin
rules, laid out together so the scale, axis ticks, labels, gridlines and legend always agree. The
group keeps the recipe (data and options) under ``chart``. ``chart-data`` edits the table (one
cell, a row, a column, a CSV reload) and ``chart`` with a ``target`` restyles it; both redraw by
updating the existing layers in place, so layer IDs, and anything added to them such as effects or
opacity, survive. Because the result is plain layers, every export, check and render treats it like
any other group; PPTX export swaps it for a native, editable chart (see ``chart_pptx.py``).
"""

from copy import deepcopy
from decimal import ROUND_HALF_UP, Decimal
import difflib
import json
import math
from pathlib import Path
import re

from ...craft import line_height
from ...constants import BUNDLED_FONTS
from ...errors import VixlError, require
from ...model import finite, new_layer

TYPES = ("chart", "chart-data", "chart-emphasis")
KINDS = (
    "bar", "stacked-bar", "percent-bar", "horizontal-bar", "stacked-horizontal-bar", "percent-horizontal-bar",
    "line", "area", "stacked-area", "pie", "donut",
)
MAX_CATEGORIES = 200
MAX_SERIES = 24
AUTO_LABELS = 60  # value_labels "auto" labels charts of up to this many values
LEGENDS = ("auto", "none", "top", "bottom", "left", "right")
LABEL_MODES = ("auto", "none", "value", "percent", "both")
DEFAULT_COLORS = ["#0072b2", "#e69f00", "#009e73", "#cc79a7", "#d55e00", "#56b4e9", "#7f7f7f", "#f0c800"]


def layout_palette(state):
    """The colours of the palette the document's layout (or rolled direction) used, when no palette was made
    active: a deck or report built by layout-apply has role swatches but no active palette, and its charts
    should still be drawn in its colours rather than the default set."""
    name = (state.get("layout") or {}).get("palette") or ((state.get("design_defaults") or {}).get("direction")
                                                           or {}).get("palette")
    if not isinstance(name, str):
        return []
    own = (state.get("palettes") or {}).get(name)
    if own:
        return list(own)
    from ...house_style import palette_colors

    return palette_colors().get(name, [])
# Options that restyle a chart; the data keys are handled separately.
OPTIONS = (
    "kind", "title", "subtitle", "colors", "legend", "legend_values", "value_labels", "total_labels", "gridlines",
    "number_format", "min", "max", "ticks", "value_title", "category_title", "font_size", "title_font",
    "label_font", "text_color", "grid_color", "axis_color", "background", "bar_gap", "line_width", "markers",
    "hole", "start_angle", "center_text", "padding",
)
DATA_KEYS = ("categories", "series", "table", "csv", "data")
MUTES = ("fade", "desaturate")
MUTE_OPACITY = 0.35  # fade: how much of a muted mark's own colour stays over the chart background
EMPHASIS_KEYS = ("focus", "series", "mute", "opacity", "annotate")
# The parts of a chart an address can name (resolve_mark); "mark" stands for the data marks themselves.
MARK_PARTS = ("bar", "slice", "point", "line", "area", "value", "total", "legend", "category-label", "callout")
DATA_MARKS = ("bar", "slice", "point", "line", "area")
# Stacking order of generated layers, bottom to top.
Z_BACKGROUND, Z_GRID, Z_AXIS, Z_MARKS, Z_LINES, Z_MARKERS, Z_VALUES, Z_AXIS_TEXT, Z_LEGEND, Z_TITLE = range(10)
KIND_ALIASES = {
    "column": "bar", "columns": "bar", "vertical-bar": "bar", "clustered-bar": "bar", "clustered-column": "bar",
    "bar-chart": "bar", "column-chart": "bar", "stacked": "stacked-bar", "stacked-column": "stacked-bar",
    "stacked-vertical-bar": "stacked-bar", "bar-stacked": "stacked-bar", "stacked-bar-chart": "stacked-bar",
    "100-stacked-bar": "percent-bar", "stacked-bar-100": "percent-bar", "percent-stacked-bar": "percent-bar",
    "percent-column": "percent-bar", "stacked-100": "percent-bar", "hbar": "horizontal-bar",
    "bar-horizontal": "horizontal-bar", "horizontal-column": "horizontal-bar", "horizontal": "horizontal-bar",
    "horizontal-stacked-bar": "stacked-horizontal-bar", "stacked-bar-horizontal": "stacked-horizontal-bar",
    "horizontal-percent-bar": "percent-horizontal-bar", "line-chart": "line", "area-chart": "area",
    "stacked-area-chart": "stacked-area", "pie-chart": "pie", "doughnut": "donut", "ring": "donut",
    "donut-chart": "donut", "doughnut-chart": "donut",
}


# Number formats are Excel-style: the same string drives Vixl's labels and the PPTX chart.

_LITERAL = r'(?:"[^"]*"|\\.|[^#0.,%"\\])'
_FORMAT = re.compile(rf"({_LITERAL}*)([#0,]*[#0])(\.0*)?(,*)(%?)({_LITERAL}*)")


def _literal(text):
    return re.sub(r'"([^"]*)"|\\(.)', lambda m: m.group(1) if m.group(1) is not None else m.group(2), text)


def parse_format(text):
    """The parts of an Excel-style number format: literals, grouping, decimals, ``,`` scaling, ``%``."""
    require(isinstance(text, str) and 0 < len(text) <= 64, "number_format must be 1–64 characters",
            field="number_format")
    match = _FORMAT.fullmatch(text)
    require(match, f"Unsupported number_format {text!r}; use patterns such as '#,##0', '0.0', '0%', '$#,##0.00' "
            "or '#,##0,\"K\"' (a trailing comma divides by 1000)", field="number_format")
    pre, whole, decimals, scale, percent, post = match.groups()
    return {"pre": _literal(pre), "post": _literal(post), "grouping": "," in whole, "digits": whole.count("0"),
            "decimals": len(decimals) - 1 if decimals else 0, "scale": len(scale), "percent": bool(percent)}


def format_number(value, text):
    """``value`` as text in the format ``text`` (half-up rounding, like a spreadsheet)."""
    spec = parse_format(text)
    number = Decimal(repr(float(value))) * (100 if spec["percent"] else 1) / Decimal(1000) ** spec["scale"]
    rounded = abs(number).quantize(Decimal(1).scaleb(-spec["decimals"]), ROUND_HALF_UP)
    body = f"{rounded:.{spec['decimals']}f}"
    whole, _, fraction = body.partition(".")
    whole = whole.zfill(spec["digits"])
    if spec["grouping"]:
        whole = f"{int(whole):,}".zfill(spec["digits"]) if whole.isdigit() else whole
    sign = "-" if number < 0 and rounded != 0 else ""
    return (sign + spec["pre"] + whole + ("." + fraction if fraction else "") + ("%" if spec["percent"] else "")
            + spec["post"])


def decimals_of(value, limit=2):
    for places in range(limit + 1):
        if abs(round(value, places) - value) < 1e-9 * max(1.0, abs(value)):
            return places
    return limit


def auto_format(values, limit=2):
    places = max((decimals_of(v, limit) for v in values), default=0)
    return "#,##0" + ("." + "0" * places if places else "")


def nice_scale(low, high, intervals, fixed_min=None, fixed_max=None):
    """``(min, max, step, ticks)`` covering [low, high] with about ``intervals`` round-numbered steps."""
    low = fixed_min if fixed_min is not None else low
    high = fixed_max if fixed_max is not None else high
    if high <= low:
        require(fixed_max is None, "max must be greater than the data's lowest value and min", field="max")
        high = low + 1
    span = high - low
    base = 10 ** math.floor(math.log10(span / intervals))
    best = None
    for exponent in (-1, 0, 1):
        for factor in (1, 2, 5):
            step = factor * base * 10 ** exponent
            count = math.ceil(span / step - 1e-9)
            # Headroom above the data counts against a step, so 3,330 gets 0–3,500 rather than 0–4,000.
            score = abs(count - intervals) + (0 if fixed_max is not None else 12 * max(0, (count * step - span) / span - 0.1))
            if best is None or score < best[0] or (score == best[0] and step > best[1]):
                best = (score, step)
    step = round(best[1], 12)
    if fixed_min is None:
        low = round(math.floor(low / step + 1e-9) * step, 12)
    if fixed_max is None:
        high = round(math.ceil(high / step - 1e-9) * step, 12)
    ticks = [round(low + i * step, 12) for i in range(int((high - low) / step + 1e-9) + 1)]
    if len(ticks) < 2:
        ticks = [low, high]
    require(len(ticks) <= 60, "The value axis would have too many ticks; raise ticks' spacing with min, max or ticks",
            field="ticks")
    return low, high, step, ticks


def category_name(value, where):
    require(isinstance(value, (str, int, float)) and not isinstance(value, bool),
            f"{where} must be text or a number; got {value!r}", field=where)
    if isinstance(value, float):
        require(math.isfinite(value), f"{where} must be finite", field=where)
        value = int(value) if value == int(value) else value
    text = str(value).strip()
    require(0 < len(text) <= 120, f"{where} must be 1–120 characters", field=where)
    return text


def cell_value(value, where):
    if value is None or value == "":
        return None
    require(isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value),
            f"{where} must be a number or null; got {value!r}", field=where)
    require(abs(value) <= 1e15, f"{where} is out of range", field=where)
    return value


def clean_table(categories, series):
    """Validate and normalize a table: unique text categories, named series of equal length."""
    require(isinstance(categories, list) and 1 <= len(categories) <= MAX_CATEGORIES,
            f"categories must list 1–{MAX_CATEGORIES} labels", field="categories")
    names = [category_name(c, f"categories[{i}]") for i, c in enumerate(categories)]
    require(len(set(names)) == len(names), "Category labels must be unique", field="categories")
    require(isinstance(series, list) and 1 <= len(series) <= MAX_SERIES,
            f"series must list 1–{MAX_SERIES} named value lists", field="series")
    result = []
    for i, item in enumerate(series):
        require(isinstance(item, dict) and set(item) <= {"name", "values", "color"}
                and isinstance(item.get("name"), str) and item["name"].strip(),
                f"series[{i}] must be {{name, values, color?}}", field=f"series[{i}]")
        values = item.get("values")
        require(isinstance(values, list) and len(values) == len(names),
                f"series[{i}] ({item['name']!r}) needs {len(names)} values, one per category", field=f"series[{i}].values")
        entry = {"name": item["name"].strip()[:120],
                 "values": [cell_value(v, f"series[{i}].values[{j}]") for j, v in enumerate(values)]}
        if item.get("color"):
            require(isinstance(item["color"], str), f"series[{i}].color must be a color", field=f"series[{i}].color")
            entry["color"] = item["color"]
        result.append(entry)
    require(len({s["name"] for s in result}) == len(result), "Series names must be unique", field="series")
    return names, result


def table_from_rows(rows):
    """A table from rows whose first row names the series and whose first column names the categories."""
    require(isinstance(rows, list) and len(rows) >= 2 and all(isinstance(r, list) for r in rows),
            "table must be rows: a header row, then one row per category", field="table")
    header = rows[0]
    require(len(header) >= 2, "table needs a category column and at least one series column", field="table")
    require(all(len(r) == len(header) for r in rows), "table rows must all have the header's length", field="table")
    series = [{"name": category_name(name, f"table[0][{j}]"), "values": [row[j] for row in rows[1:]]}
              for j, name in enumerate(header) if j]
    return clean_table([row[0] for row in rows[1:]], series)


def cell_number(text, where):
    """A number from CSV text: blanks are gaps; thousands commas and a leading currency sign are fine."""
    cleaned = text.strip().replace(",", "").replace(" ", "")
    if not cleaned:
        return None
    cleaned = cleaned.lstrip("$€£")
    try:
        number = float(cleaned)
    except ValueError:
        raise VixlError("invalid_data", f"{where} is not a number: {text!r}", field="csv") from None
    require(math.isfinite(number), f"{where} must be finite", "invalid_data", field="csv")
    return int(number) if number == int(number) and not re.search(r"[.eE]", cleaned) else number


def workspace_file(project, name):
    """The CSV a chart is bound to: a path inside the workspace (never outside it)."""
    require(isinstance(name, str) and name, "csv must be a workspace-relative path", field="csv")
    root = Path(getattr(project, "_workspace", None) or Path.cwd()).resolve()
    path = (root / name).resolve()
    require(path.is_relative_to(root), "csv is outside the workspace", "forbidden", field="csv")
    require(path.is_file(), f"CSV not found in the workspace: {name}", "not_found", field="csv")
    return path


def table_from_csv(project, source):
    """A table from a workspace CSV: the first column (or ``category_column``) names the categories and
    every other column (or ``series_columns``) is a series. Blank cells are gaps."""
    from ...exports import read_csv

    headers, rows = read_csv(workspace_file(project, source["csv"]), limit=MAX_CATEGORIES)
    column = source.get("category_column") or headers[0]
    require(column in headers, f"category_column {column!r} is not a CSV column; columns: {', '.join(headers)}",
            field="category_column", allowed=headers)
    wanted = source.get("series_columns") or [h for h in headers if h != column]
    missing = [h for h in wanted if h not in headers]
    require(not missing and column not in wanted,
            f"series_columns must be CSV columns other than {column!r}; columns: {', '.join(headers)}",
            field="series_columns", allowed=headers)
    series = [{"name": name, "values": [cell_number(row[name], f"{name} in row {i}") for i, row in enumerate(rows, 1)]}
              for name in wanted]
    return clean_table([row[column] for row in rows], series)


def alias_series(series):
    """Chart.js-style spellings (label/data/backgroundColor) and a name → values mapping."""
    if isinstance(series, dict):
        series = [{"name": name, "values": values} for name, values in series.items()]
    if not isinstance(series, list):
        return series
    result = []
    for item in series:
        if isinstance(item, dict):
            item = dict(item)
            for old, new in (("label", "name"), ("data", "values"), ("backgroundColor", "color"),
                             ("fill", "color"), ("colour", "color")):
                if old in item and new not in item:
                    item[new] = item.pop(old)
        result.append(item)
    return result


def normalize(op, note):
    """Chart-kind spellings and Chart.js-style fields (labels/datasets, data), as other operations do."""
    for key in list(op):
        snake = re.sub(r"(?<=[a-z0-9])([A-Z])", r"_\1", key).lower().replace("-", "_")
        if snake in ("chart_type", "charttype", "type_of_chart", "chart_kind", "variant") and "kind" not in op:
            op["kind"] = op.pop(key)
            note(f"{key!r} → 'kind'")
    kind = op.get("kind")
    if isinstance(kind, str) and kind not in KINDS:
        guess = KIND_ALIASES.get(kind.lower().replace("_", "-").replace(" ", "-"))
        if guess:
            note(f"kind {kind!r} → {guess!r}")
            op["kind"] = guess
    if isinstance(op.get("data"), dict):
        op.update({k: v for k, v in op.pop("data").items() if k not in op})
        note("data → categories/series")
    elif isinstance(op.get("data"), list) and "table" not in op and all(isinstance(r, list) for r in op["data"]):
        op["table"] = op.pop("data")
        note("data → table")
    if isinstance(op.get("labels"), list) and "categories" not in op:
        op["categories"] = op.pop("labels")
        note("'labels' → 'categories'")
    if "datasets" in op and "series" not in op:
        op["series"] = op.pop("datasets")
        note("'datasets' → 'series'")
    for old, new in (("show_legend", "legend"), ("show_values", "value_labels"), ("data_labels", "value_labels"),
                     ("show_gridlines", "gridlines"), ("grid", "gridlines"), ("x_title", "category_title"),
                     ("x_axis_title", "category_title"), ("y_title", "value_title"), ("y_axis_title", "value_title"),
                     ("y_min", "min"), ("y_max", "max"), ("palette", "colors"), ("color_palette", "colors"),
                     ("number_formatting", "number_format"), ("format", "number_format")):
        if old in op and new not in op:
            op[new] = op.pop(old)
            note(f"{old!r} → {new!r}")
    if "series" in op:
        op["series"] = alias_series(op["series"])
    if isinstance(op.get("add_series"), list):
        op["add_series"] = alias_series(op["add_series"])
    return op


def normalize_emphasis(op, note):
    """Forgiving spellings of ``chart-emphasis``: highlight/categories for focus, callout/label for annotate, one
    category given as text, grey for desaturate."""
    for old, new in (("highlight", "focus"), ("categories", "focus"), ("category", "focus"), ("callout", "annotate"),
                     ("annotation", "annotate"), ("label", "annotate"), ("mode", "mute")):
        if old in op and new not in op:
            op[new] = op.pop(old)
            note(f"{old!r} → {new!r}")
    focus = op.get("focus")
    if isinstance(focus, (str, int, float)) and not isinstance(focus, bool):
        op["focus"] = [focus]
        note("focus as one category → a one-item list")
    elif "focus" in op and focus is None:
        op["focus"] = []
        note("focus null → [] (removes the emphasis)")
    mute = op.get("mute")
    if isinstance(mute, str) and mute not in MUTES:
        guess = {"grey": "desaturate", "gray": "desaturate", "greyscale": "desaturate", "grayscale": "desaturate",
                 "desaturated": "desaturate", "dim": "fade", "faded": "fade", "lighten": "fade"}.get(mute.lower())
        if guess:
            op["mute"] = guess
            note(f"mute {mute!r} → {guess!r}")
    return op


def read_data(project, op, recipe):
    """Replace ``recipe``'s table when the operation brings one (inline, rows or a CSV)."""
    from .datasets import binding, detach

    given = [k for k in DATA_KEYS if k in op]
    if not given and "derive" in op:
        recipe["categories"], recipe["series"] = binding(project, op, recipe)
        return True
    if not given:
        return False
    require(len(given) == 1 or set(given) == {"categories", "series"},
            f"Give data once: categories + series, table, csv or a dataset name; got {', '.join(given)}", field=given[0])
    if "data" in op:
        categories, series = binding(project, op, recipe)
    elif "csv" in op:
        source = {k: op[k] for k in ("csv", "category_column", "series_columns") if op.get(k)}
        categories, series = table_from_csv(project, source)
        recipe["source"] = source
    elif "table" in op:
        categories, series = table_from_rows(op["table"])
        recipe.pop("source", None)
    else:
        require("categories" in op and "series" in op, "Inline data needs both categories and series",
                field="categories" if "categories" not in op else "series")
        categories, series = clean_table(op["categories"], op["series"])
        recipe.pop("source", None)
    recipe["categories"], recipe["series"] = categories, series
    if "data" not in op:
        require("derive" not in op, "derive needs a dataset binding", field="derive")
        detach(recipe)
    return True


def find(names, wanted, what, field):
    text = category_name(wanted, field) if what == "category" else wanted
    if text in names:
        return names.index(text)
    close = difflib.get_close_matches(str(text), names, 3, 0.5)
    plural = "categories" if what == "category" else what
    raise VixlError("invalid_operation", f"Unknown {what} {text!r}; {plural}: {', '.join(names[:40])}"
                    + (f". Did you mean {' or '.join(map(repr, close))}?" if close else ""),
                    field=field, allowed=names[:100], suggestions=close)


def edit_data(project, op, recipe):
    """Apply a ``chart-data`` operation to the recipe's table: replace or reload, then remove, add, set."""
    changed = read_data(project, op, recipe)
    require("data" not in recipe or not any(key in op for key in
            ("set", "append", "remove_categories", "remove_series", "add_series", "reload")),
            "Edit the shared dataset with dataset, or provide inline data to detach this chart", field="data")
    if op.get("reload"):
        require(recipe.get("source"), "This chart is not bound to a CSV; give a csv, or edit its values directly",
                field="reload")
        recipe["categories"], series = table_from_csv(project, recipe["source"])
        colors = {s["name"]: s["color"] for s in recipe["series"] if s.get("color")}
        recipe["series"] = [{**s, **({"color": colors[s["name"]]} if s["name"] in colors else {})} for s in series]
        changed = True
    categories, series = recipe["categories"], recipe["series"]
    for index, name in enumerate(op.get("remove_categories", [])):
        at = find(categories, name, "category", f"remove_categories[{index}]")
        categories.pop(at)
        for s in series:
            s["values"].pop(at)
        changed = True
    for index, name in enumerate(op.get("remove_series", [])):
        series.pop(find([s["name"] for s in series], name, "series", f"remove_series[{index}]"))
        changed = True
    for index, item in enumerate(alias_series(op.get("add_series", []))):
        require(isinstance(item, dict), f"add_series[{index}] must be {{name, values, color?}}",
                field=f"add_series[{index}]")
        series.append({"name": item.get("name"), "values": item.get("values"), **({"color": item["color"]} if item.get("color") else {})})
        changed = True
    for index, row in enumerate(op.get("append", [])):
        require(isinstance(row, dict) and "category" in row and "values" in row,
                f"append[{index}] must be {{category, values}}", field=f"append[{index}]")
        values = row["values"]
        if isinstance(values, dict):
            unknown = sorted(set(values) - {s["name"] for s in series})
            require(not unknown, f"append[{index}] names unknown series {', '.join(map(repr, unknown))}",
                    field=f"append[{index}].values")
            values = [values.get(s["name"]) for s in series]
        require(isinstance(values, list) and len(values) == len(series),
                f"append[{index}].values needs one value per series ({len(series)})", field=f"append[{index}].values")
        categories.append(row["category"])
        for s, value in zip(series, values):
            s["values"].append(value)
        changed = True
    categories[:], series[:] = clean_table(categories, series)
    for index, edit in enumerate(op.get("set", [])):
        require(isinstance(edit, dict) and "category" in edit and "value" in edit,
                f"set[{index}] must be {{category, series?, value}}", field=f"set[{index}]")
        names = [s["name"] for s in series]
        if "series" in edit:
            which = find(names, edit["series"], "series", f"set[{index}].series")
        else:
            require(len(series) == 1, f"set[{index}] needs a series: this chart has {', '.join(map(repr, names))}",
                    field=f"set[{index}].series", allowed=names)
            which = 0
        series[which]["values"][find(categories, edit["category"], "category", f"set[{index}].category")] = (
            cell_value(edit["value"], f"set[{index}].value"))
        changed = True
    require(changed, "chart-data needs something to change: set, append, remove_categories, add_series, "
            "remove_series, reload, or new categories/series, table or csv", field="set")


# Statistics are kept on the recipe so agents never recompute them.

def statistics(recipe):
    categories, series = recipe["categories"], recipe["series"]
    total = lambda values: round(sum(v for v in values if v is not None), 9)  # noqa: E731
    by_series = {s["name"]: total(s["values"]) for s in series}
    by_category = {c: total([s["values"][i] for s in series]) for i, c in enumerate(categories)}
    grand = round(sum(by_series.values()), 9)
    result = {"kind": recipe["kind"], "categories": len(categories), "series": len(series),
              "totals": {"by_category": by_category, "by_series": by_series, "grand": grand}}
    if recipe["kind"] in ("pie", "donut") and grand > 0:
        result["shares"] = {c: round((v or 0) / grand * 100, 6) for c, v in zip(categories, series[0]["values"])}
    return result


def rgba(state, value):
    from ...design import resolve_color
    from ...render import color

    return color(resolve_color(value, state))


def unit(rgb):
    return tuple(c / 255 for c in rgb[:3])


def contrast(state, first, second):
    """WCAG contrast ratio between two colors (color expressions or RGB tuples)."""
    from ...colors import contrast_ratio

    return contrast_ratio(unit(first if isinstance(first, tuple) else rgba(state, first)),
                          unit(second if isinstance(second, tuple) else rgba(state, second)))


def mix(front, back, amount):
    """``front`` faded toward ``back`` (RGB tuples): ``amount`` 1 is all front."""
    return tuple(round(f * amount + b * (1 - amount)) for f, b in zip(front[:3], back[:3]))


def hex_color(rgb):
    return "#%02x%02x%02x" % tuple(rgb)


class Emphasis:
    """A chart's emphasis (``recipe["emphasis"]``): which marks stay in their colour, how the rest is drawn and
    what the callouts say. A mark is in focus when it matches the focus on every dimension it has: a bar, point
    or slice has a series and a category, a line or area only a series, a total only a category."""

    def __init__(self, project, recipe, style):
        spec = recipe.get("emphasis") or {}
        categories, names = recipe["categories"], [s["name"] for s in recipe["series"]]
        self.active = bool(spec)
        self.categories = [categories.index(c) for c in spec.get("focus", []) if c in categories]
        self.series = names.index(spec["series"]) if spec.get("series") in names else None
        self.mode, self.amount = spec.get("mute", "fade"), spec.get("opacity", MUTE_OPACITY)
        self.text = spec.get("annotate") if self.categories else None
        self.state, self.bg = project.state, style.bg
        self.used, self._muted = {"focus": [], "muted": []}, {}

    def focused(self, series=None, category=None):
        """Whether the mark of this series and category index is in focus (None: the mark has no such dimension)."""
        if not self.active:
            return True
        if series is not None and self.series is not None and series != self.series:
            return False
        return not (category is not None and self.categories and category not in self.categories)

    def muted(self, value):
        if value not in self._muted:
            r, g, b, a = rgba(self.state, value)
            if self.mode == "desaturate":
                from ...colors import oklab_to_srgb, srgb_to_oklab

                lightness = srgb_to_oklab(unit((r, g, b)))[0]
                rgb = tuple(round(min(max(c, 0.0), 1.0) * 255) for c in oklab_to_srgb((lightness, 0.0, 0.0)))
            else:
                rgb = mix((r, g, b), self.bg, self.amount)
            self._muted[value] = hex_color(rgb) + (f"{a:02x}" if a < 255 else "")
        return self._muted[value]

    def color(self, value, series=None, category=None):
        """``value`` for a mark in focus, its muted form otherwise; records both for the summary and the checks."""
        if not self.active:
            return value
        strong = self.focused(series, category)
        drawn = value if strong else self.muted(value)
        seen = self.used["focus" if strong else "muted"]
        shown = hex_color(rgba(self.state, drawn)[:3])
        if shown not in seen:
            seen.append(shown)
        return drawn

    def ink(self, style, series=None, category=None):
        """Text colour of a label beside a mark: the chart's ink in focus, its secondary text colour otherwise."""
        return style.ink if self.focused(series, category) else style.muted

    def callout(self, value, category, series, total, number_format):
        """The callout text for one focus mark: ``${value}``, ``${percent}`` (share of the chart's total),
        ``${category}`` and ``${series}`` filled in."""
        share = value / total if total else 0
        percent = format_number(share, "0%" if abs(share * 100 - round(share * 100)) < 0.05 else "0.0%")
        fields = {"value": format_number(value, number_format), "percent": percent, "category": category,
                  "series": series or ""}
        return re.sub(r"\$\{(value|percent|category|series)\}", lambda m: fields[m[1]], self.text)

    def summary(self, recipe):
        spec = recipe["emphasis"]
        return {"focus": list(spec.get("focus", [])), **({"series": spec["series"]} if spec.get("series") else {}),
                "mute": self.mode, "focus_colors": self.used["focus"][:64], "muted_colors": self.used["muted"][:64],
                "surface": hex_color(self.bg)}


class Style:
    """Colors, type sizes and spacing a chart draws with, taken from the options and the document."""

    def __init__(self, project, recipe, width, height):
        state = project.state
        self.project, self.recipe = project, recipe
        # Sizes sit on the document's type scale (its character styles) when it has one.
        self.scale = sorted({float(s["size"]) for s in state.get("character_styles", {}).values() if "size" in s})
        self.fs = int(round(recipe["font_size"])) if recipe.get("font_size") else self.snap(max(10, min(40, min(width, height) / 30)))
        self.pad = int(round(recipe["padding"] if "padding" in recipe else self.fs * 0.8))
        if "padding" not in recipe:
            from ...craft import space
            self.pad = int(space(2, self.fs))
        override = recipe.get("background")
        self.surface = override or state["canvas"]["background"]
        surface = rgba(state, self.surface)
        self.bg = surface[:3] if surface[3] >= 128 else (255, 255, 255)
        from ...colors import relative_luminance

        self.dark = relative_luminance(unit(self.bg)) < 0.4
        ink = recipe.get("text_color")
        if not ink:
            ink = "#f3f4f6" if self.dark else "#1f2937"
            if not override and "ink" in state.get("swatches", {}) and contrast(state, "@ink", self.bg) >= 4.5:
                ink = "@ink"
        self.ink = ink
        rgb = rgba(state, ink)[:3]
        # Secondary text (ticks, categories, subtitle) is the ink faded toward the background, as far as
        # still reads at the 4.5:1 that the contrast check asks of text.
        amount = 0.62
        while amount < 1 and contrast(state, mix(rgb, self.bg, amount), self.bg) < 4.7:
            amount += 0.04
        self.muted = hex_color(mix(rgb, self.bg, min(amount, 1)))
        self.grid = recipe.get("grid_color") or hex_color(mix(rgb, self.bg, 0.14))
        self.axis = recipe.get("axis_color") or hex_color(mix(rgb, self.bg, 0.5))
        self.separator = hex_color(self.bg)

    def snap(self, size):
        """``size`` pixels, or the nearest size of the document's type scale."""
        if not self.scale:
            return max(1, int(round(size)))
        return int(round(min(self.scale, key=lambda step: abs(math.log(size / step)))))

    def smaller(self, size):
        """The next size down: one pixel, or one step of the type scale."""
        lower = [step for step in self.scale if step < size]
        return int(round(max(lower))) if lower else size - 1

    def colors(self, count):
        """One color per series (or slice): explicit colors first, then the document's accents (all of them on a
        page whose layout drew two or three), then the document palette, then a color-blind-safe default set."""
        state = self.project.state
        pool = [c for c in (self.recipe.get("colors") or [])]
        explicit = len(pool)
        palette = (state.get("palettes") or {}).get(state.get("active_palette")) or layout_palette(state)
        usable = [c for c in palette if contrast(state, c, self.bg) >= 1.6]
        swatches = state.get("swatches", {})
        if count == 1 and not explicit and "accent" in swatches:
            pool.append("@accent")
        elif count > 1 and not explicit and "accent" in swatches and "accent-2" in swatches:
            pool.extend(f"@{role}" for role in ("accent", "accent-2", "accent-3") if role in swatches)
        pool += [c for c in usable + DEFAULT_COLORS if c not in pool]
        return [pool[i % len(pool)] for i in range(count)]

    def on(self, fill):
        """Label color that reads on ``fill``: white or near-black, whichever contrasts more."""
        state = self.project.state
        return "#ffffff" if contrast(state, "#ffffff", fill) >= contrast(state, "#111827", fill) else "#111827"


class Kit:
    """Measures and builds text so labels sit where the layout says (ink-tight boxes, baselines)."""

    def __init__(self, project, recipe, style):
        from ...render import resolve_font

        self.project, self.style = project, style
        self.fonts = {head: resolve_font(project, recipe.get("title_font" if head else "label_font")
                                         or ("heading" if head else "body")) for head in (True, False)}
        self._vertical = {}
        self._spacing = {}

    def spacing(self, font, size, stage):
        """Line spacing that sets wrapped chart text on the house line-height table (craft ``line_height``):
        titles as headings, the subtitle as a lead, labels and legends as captions."""
        from ...craft import line_height, spacing_for

        key = (font, size, stage)
        if key not in self._spacing:
            self._spacing[key] = spacing_for(self.project, self.project.state.get("fonts", {}).get(font, font), size,
                                             line_height(stage))
        return self._spacing[key]

    def vertical(self, layer):
        """(ascent, height above the baseline of a digit) for this font and size."""
        from ...render import text_metrics
        from ...text import face, primary_font_data

        key = (layer["font"], layer["size"])
        if key not in self._vertical:
            try:
                outline = face(primary_font_data(self.project, layer))[0]
                ascent = outline["hhea"].ascent * layer["size"] / outline["head"].unitsPerEm
                box = text_metrics(self.project, {**layer, "text": "0"})[2]
                self._vertical[key] = (ascent, ascent - box[1])
            except Exception:  # noqa: BLE001 - bitmap or unusual fonts: estimate from the size
                self._vertical[key] = (layer["size"] * 0.9, layer["size"] * 0.7)
        return self._vertical[key]

    def make(self, text, size, color, head=False, align="left", stage=None):
        from ...render import text_metrics

        font, role = self.fonts[head]
        size = max(1, int(round(size)))
        stage = stage or ("heading" if head else "caption")
        layer = {"text": text, "font": font, "size": size, "color": color, "align": align,
                 "spacing": self.spacing(font, size, stage), "auto_size": True}
        width, height, box = text_metrics(self.project, layer)
        ascent, cap = self.vertical(layer)
        base = ascent - box[1] if isinstance(box, tuple) and len(box) == 4 else height * 0.8
        return {**layer, "role": role, "width": width, "height": height, "base": base, "cap": cap}

    def width(self, text, size, head=False):
        return self.make(text, size, "black", head)["width"]

    def wrap(self, text, size, limit, lines=3):
        """``text`` broken at spaces to fit ``limit`` pixels (at most ``lines`` lines)."""
        if "\n" in text or self.width(text, size) <= limit:
            return text
        rows, current = [], ""
        for word in text.split():
            attempt = f"{current} {word}".strip()
            if current and self.width(attempt, size) > limit:
                rows.append(current)
                current = word
            else:
                current = attempt
        rows.append(current)
        if len(rows) > lines:
            rows = rows[:lines - 1] + [" ".join(rows[lines - 1:])]
        return "\n".join(rows)


class Parts:
    """The layers a chart is made of, in stacking order, each under a stable key."""

    def __init__(self):
        self.items, self.keys = [], set()

    def add(self, key, label, kind, z, init=None, **fields):
        require(key not in self.keys, f"Internal error: duplicate chart part {key}", "internal_error")
        self.keys.add(key)
        self.items.append({"key": key, "label": label, "kind": kind, "z": z, "fields": fields, "init": init or {}})

    def rect(self, key, label, box, fill, z, **extra):
        x, y, w, h = box
        self.add(key, label, "rect", z, x=x, y=y, width=max(1, w), height=max(1, h), fill=fill, **extra)

    def ordered(self):
        return sorted(self.items, key=lambda item: item["z"])

    def text(self, key, label, lab, x, y, z, rotation=0):
        """A text layer for the measured label ``lab`` with its ink box's top-left at (x, y)."""
        fields = {k: lab[k] for k in ("text", "size", "color", "font", "align", "spacing", "width", "height")}
        if lab["role"]:
            fields["font_role"] = lab["role"]
        self.add(key, label, "text", z, x=round(x), y=round(y), rotation=rotation, **fields)
        return (round(x), round(y), lab["width"], lab["height"])


def spot(lab, x, y, anchor="left", at="base"):
    """Top-left of ``lab`` placed at x (its left, center or right edge per ``anchor``) and y (its baseline,
    top or middle per ``at``)."""
    left = x if anchor == "left" else x - lab["width"] / 2 if anchor == "center" else x - lab["width"]
    return left, {"base": y - lab["base"], "top": y, "mid": y - lab["height"] / 2}[at]


def place(parts, key, label, lab, x, y, z, anchor="left", at="base"):
    """Add ``lab`` as a text part positioned by ``spot``; returns its box."""
    return parts.text(key, label, lab, *spot(lab, x, y, anchor, at), z)


def crosses(box, a, b, margin=2):
    """Whether the segment a-b passes through ``box`` (x, y, w, h) widened by ``margin`` (Liang-Barsky)."""
    x0, y0, x1, y1 = box[0] - margin, box[1] - margin, box[0] + box[2] + margin, box[1] + box[3] + margin
    dx, dy = b[0] - a[0], b[1] - a[1]
    low, high = 0.0, 1.0
    for p, q in ((-dx, a[0] - x0), (dx, x1 - a[0]), (-dy, a[1] - y0), (dy, y1 - a[1])):
        if p == 0:
            if q < 0:
                return False
            continue
        t = q / p
        if p < 0:
            low = max(low, t)
        else:
            high = min(high, t)
        if low > high:
            return False
    return True


class Collider:
    """Keeps automatic labels from landing on each other."""

    def __init__(self):
        self.boxes = []

    def free(self, box, margin=2):
        x, y, w, h = box
        return not any(x < bx + bw + margin and bx < x + w + margin and y < by + bh + margin and by < y + h + margin
                       for bx, by, bw, bh in self.boxes)

    def take(self, box):
        self.boxes.append(box)

    @staticmethod
    def overlaps(a, b, margin=1):
        return (a[0] < b[0] + b[2] + margin and b[0] < a[0] + a[2] + margin and a[1] < b[1] + b[3] + margin
                and b[1] < a[1] + a[3] + margin)


def header(kit, style, recipe, parts, size):
    """Title and subtitle at the top-left; returns the y below them."""
    y = style.pad
    for key, size_, color, head, stage in (("title", style.snap(style.fs * 1.5), style.ink, True, "heading"),
                                           ("subtitle", style.snap(style.fs * 1.1), style.muted, False, "lead")):
        if recipe.get(key):
            lab = kit.make(kit.wrap(recipe[key], size_, size[0] - 2 * style.pad, 4), size_, color, head, stage=stage)
            place(parts, key, key, lab, style.pad, y, Z_TITLE, at="top")
            y += lab["height"] + round(style.fs * 0.4)
    return y


class Legend:
    """A row or column of swatch + label entries, measured before the plot is sized."""

    def __init__(self, kit, style, entries, position, room):
        self.position, self.style = position, style
        fs = style.fs
        self.swatch = round(fs * 0.8)
        # One legend line is a body line of the house line-height table; a label of several lines takes
        # as many rows as it needs, so entries never overlap.
        self.row = round(fs * line_height("body"))
        spacing = round(fs * 1.4)
        labels = [(kit.make(text, fs, style.ink, stage="body"), color) for text, color in entries]
        self.entries, x, y, widest, line = [], 0, 0, 0, self.row
        for lab, color in labels:
            width = self.swatch + round(fs * 0.45) + lab["width"]
            depth = max(self.row, lab["height"] + round(fs * (line_height("body") - 1)))
            if position in ("top", "bottom") and x and x + width > room:
                x, y, line = 0, y + line, self.row
            line = max(line, depth)
            self.entries.append((x, y, lab, color, depth))
            widest, x = max(widest, x + width), x + width + spacing
            if position in ("left", "right"):
                x, y, line = 0, y + depth, self.row
        self.width = widest
        self.height = max(e[1] + e[4] for e in self.entries)

    def emit(self, parts, ox, oy):
        s = self.style
        for i, (x, y, lab, color, _) in enumerate(self.entries):
            mid = oy + y + self.row / 2
            parts.rect(f"legend-swatch-{i}", f"legend swatch {i + 1}",
                       (round(ox + x), round(mid - self.swatch / 2), self.swatch, self.swatch), color, Z_LEGEND)
            place(parts, f"legend-label-{i}", f"legend label {i + 1}", lab, ox + x + self.swatch + round(s.fs * 0.45),
                  mid + lab["cap"] / 2, Z_LEGEND)


class ValueLegend:
    """The ``legend_values`` legend: a key-value list (``key_values.ValueList``) of swatch, name, total and, for
    pies and donuts, share, with rules between rows, so names, numbers and percentages read as one list."""

    def __init__(self, project, kit, style, entries, position, room):
        from .key_values import ValueList

        self.position = position
        rows = ValueList(kit, style.fs, entries, swatch=True, ink=style.ink, share_ink=style.muted)
        # Beside the plot the list takes at most about half the chart; above or below it, the full width.
        limit = room * (0.5 if position in ("left", "right") else 1)
        if rows.width > limit:
            rows = ValueList(kit, style.fs, entries, width=limit, swatch=True, ink=style.ink, share_ink=style.muted)
        self.rows, self.width, self.height = rows, rows.width, rows.height
        self.rule = hex_color(mix(rgba(project.state, style.ink)[:3], style.bg, 0.25))

    def emit(self, parts, ox, oy):
        self.rows.emit(parts, ox, oy, prefix="legend-", rule_color=self.rule, z=Z_LEGEND, label="legend")


def legend_position(recipe, count, radial):
    choice = recipe.get("legend", "auto")
    if choice is True:
        choice = "auto"
    if choice is False or choice == "none":
        return None
    if choice == "auto":
        if count < 2:
            return None
        return "right" if radial else "bottom"
    return choice


def labels_mode(recipe, radial):
    """(show, force, content): value labels on at all, shown even where they crowd, and what they say."""
    mode = recipe.get("value_labels", "auto")
    if mode is False or mode == "none":
        return False, False, "value"
    force = mode is True or mode in ("value", "percent", "both")
    content = mode if mode in ("value", "percent", "both") else ("percent" if radial else "value")
    require(radial or content == "value", "percent and both value labels are for pie and donut charts",
            field="value_labels")
    return True, force, content


def segment(project, parts, kind, key, label, points, fill, stroke=None, width=0, z=Z_MARKS, **extra):
    """A path layer drawn through ``points`` (``kind`` 'area' closes it); its box fits the points."""
    xs, ys = [p[0] for p in points], [p[1] for p in points]
    pad = width / 2 + 1
    left, top = math.floor(min(xs) - pad), math.floor(min(ys) - pad)
    w, h = math.ceil(max(xs) + pad) - left, math.ceil(max(ys) + pad) - top
    d = " ".join(f"{'ML'[i > 0]}{x - left:.2f} {y - top:.2f}" for i, (x, y) in enumerate(points))
    parts.add(key, label, "path", z, x=left, y=top, width=w, height=h, path=d + (" Z" if kind == "area" else ""),
              path_view=[w, h], fill=fill, stroke=stroke or "transparent", stroke_width=width, line_cap="round", **extra)


class Cartesian:
    """Bar, line and area charts: plot rectangle, scale, gridlines, tick and category labels, marks, legend."""

    def __init__(self, project, recipe, size, style, kit, parts, stats):
        self.project, self.recipe, self.style, self.kit, self.parts, self.stats = project, recipe, style, kit, parts, stats
        self.W, self.H = size
        kind = recipe["kind"]
        self.horizontal = "horizontal" in kind
        self.percent = kind.startswith("percent")
        self.stacked = self.percent or kind.startswith("stacked")
        self.area, self.bars = "area" in kind, "bar" in kind
        self.categories, self.series = recipe["categories"], recipe["series"]
        self.n, self.m = len(self.categories), len(self.series)
        self.gap = max(3, round(style.fs * 0.45))
        self.colors = [s.get("color") or c for s, c in zip(self.series, style.colors(self.m))]
        self.em = Emphasis(project, recipe, style)
        # Where the marks landed (bar boxes, line points) and the callouts set beside them; ``quiet`` marks give
        # their value label up to a callout.
        self.extent, self.points, self.callouts, self.quiet = {}, {}, {}, set()
        self.shown, forced, _ = labels_mode(recipe, False)
        self.auto = self.shown and not forced
        if self.auto and self.n * self.m > AUTO_LABELS:
            self.shown = self.auto = False  # automatic labels are for charts of a readable number of values
        self.point_labels = self.shown and not (self.area and not forced)
        self.totals_shown = bool(recipe.get("total_labels")) and self.stacked and not self.percent
        self.crowd = Collider()
        self.pending = []
        # The drawn lines and markers of a line chart, which automatic value labels keep clear of.
        self.paths, self.marks = [], []
        self.cap = kit.make("0", style.fs, style.ink)["cap"]
        self.value_size = max(8, style.snap(style.fs * 0.85))
        self.value_cap = kit.make("0", self.value_size, style.ink)["cap"]
        values = [v for s in self.series for v in s["values"] if v is not None]
        self.label_format = recipe.get("number_format") or auto_format(values + list(stats["totals"]["by_category"].values()))

    def build(self):
        self.value_range()
        self.frame()
        self.axes()
        (self.draw_bars if self.bars else self.draw_lines)()
        self.draw_callouts()
        self.place_labels()
        self.draw_legend()
        if self.em.active:
            self.stats["emphasis"] = self.em.summary(self.recipe)
        self.stats.update(scale={"min": self.lo, "max": self.hi, "step": self.step, "ticks": self.ticks, "format": self.tick_format},
                          label_format=self.label_format, colors=self.colors, legend=self.position)

    def value_range(self):
        zero = self.zero = [[v or 0 for v in s["values"]] for s in self.series]
        require(not self.percent or all(v >= 0 for row in zero for v in row), "Percent charts cannot hold negative values")
        require(not self.area or self.n >= 2, "Area charts need at least two categories")
        if self.percent:
            self.data_low, self.data_high = 0, 100
        elif self.stacked:
            self.data_low = min(0, *(sum(min(row[i], 0) for row in zero) for i in range(self.n)))
            self.data_high = max(0, *(sum(max(row[i], 0) for row in zero) for i in range(self.n)))
        else:
            flat = [v for s in self.series for v in s["values"] if v is not None] or [0]
            self.data_low, self.data_high = min(0, *flat), max(0, *flat)

    def frame(self):
        """Reserve room for the title, legend, axis titles and labels, then size the plot with what is left."""
        W, H, style, kit, recipe = self.W, self.H, self.style, self.kit, self.recipe
        gap, fs, pad = self.gap, style.fs, style.pad
        totals = self.stats["totals"]
        self.position = legend_position(recipe, self.m, False)
        self.legend = None
        if self.position:
            if recipe.get("legend_values"):
                entries = [(s["name"], format_number(totals["by_series"][s["name"]], self.label_format), None,
                            self.em.color(self.colors[i], i)) for i, s in enumerate(self.series)]
                self.legend = ValueLegend(self.project, kit, style, entries, self.position, W - 2 * pad)
            else:
                self.legend = Legend(kit, style, [(s["name"], self.em.color(self.colors[i], i))
                                                  for i, s in enumerate(self.series)], self.position, W - 2 * pad)
        top = header(kit, style, recipe, self.parts, (W, H))
        left, right, bottom = pad, W - pad, H - pad
        if self.legend and self.position == "top":
            self.legend_y, top = top, top + self.legend.height + gap
        elif self.legend and self.position == "bottom":
            bottom -= self.legend.height + gap
        elif self.legend and self.position == "left":
            left += self.legend.width + gap * 2
        elif self.legend and self.position == "right":
            right -= self.legend.width + gap * 2
        titles = {key: kit.make(recipe[key], fs, style.muted, align="center") if recipe.get(key) else None
                  for key in ("value_title", "category_title")}
        self.side_title, self.bottom_title = ((titles["category_title"], titles["value_title"]) if self.horizontal
                                              else (titles["value_title"], titles["category_title"]))
        if self.side_title:
            self.title_x, left = left, left + self.side_title["height"] + gap
        if self.bottom_title:
            bottom -= self.bottom_title["height"]
            self.title_y, bottom = bottom, bottom - gap
        above = not self.horizontal and (self.totals_shown or (self.point_labels and not (self.bars and self.stacked)))
        top += round(self.value_cap + gap * 1.5) if above else round(self.cap / 2) + 2
        self.prepare_callouts()
        if self.callouts and not self.horizontal:
            top += max(lab["height"] for lab in self.callouts.values()) + gap
        if self.horizontal:
            self.cat_labels = [kit.make(kit.wrap(c, fs, W * 0.35), fs, style.muted, align="right") for c in self.categories]
            left += max(lab["width"] for lab in self.cat_labels) + gap * 2
            room, spacing = right - left - self.cap * 6, kit.width("1,000", fs) * 1.7
        else:
            room, spacing = bottom - top - self.cap * 3, self.cap * 3.2
        intervals = max(2, min(recipe.get("ticks", 5), int(max(1, room) / spacing)))
        self.lo, self.hi, self.step, self.ticks = nice_scale(self.data_low, self.data_high, intervals,
                                                              recipe.get("min"), recipe.get("max"))
        self.tick_format = recipe.get("number_format") or auto_format(self.ticks + [self.step], 4)
        self.tick_labels = [kit.make(f"{t:g}%" if self.percent else format_number(t, self.tick_format), fs, style.muted,
                                     align="center" if self.horizontal else "right") for t in self.ticks]
        widest = max(lab["width"] for lab in self.tick_labels)
        if self.horizontal:
            right -= widest / 2 + 2
            self.longest = 0
            if self.point_labels or self.totals_shown:
                longest = max([kit.width(format_number(v, self.label_format), fs) for row in self.zero for v in row] + [0])
                self.longest = 0 if self.stacked and not self.totals_shown else longest + gap
                right -= self.longest
            if self.callouts:
                right -= max(lab["width"] for lab in self.callouts.values()) + gap
            bottom -= self.cap + max(lab["height"] - lab["base"] for lab in self.tick_labels) + gap * 2
            top += gap
            self.px0, self.px1, self.py0, self.py1 = left, right, top, bottom
            self.band = (bottom - top) / self.n
        else:
            left += widest + gap * 2
            if self.area:
                right -= max(0, kit.width(self.categories[-1], fs) / 2 - pad) + 2
            self.band = (right - left) / (self.n - 1 if self.area else self.n)
            limit, skip = self.band * 0.96, 1
            wrapped = [kit.wrap(c, fs, limit) for c in self.categories]
            if max(kit.width(line, fs) for text in wrapped for line in text.split("\n")) > limit * 1.02:
                # Even wrapped they would touch: show every few, each on one line where it fits.
                skip = math.ceil((max(kit.width(c, fs) for c in self.categories) + gap) / max(1, self.band))
                wrapped = [kit.wrap(c, fs, self.band * skip - gap) for c in self.categories]
            self.cat_labels = [(i, kit.make(text, fs, style.muted, align="center")) for i, text in enumerate(wrapped)
                               if i % skip == 0]
            bottom -= self.cap + max(lab["height"] - lab["base"] for _, lab in self.cat_labels) + gap * 2
            self.px0, self.px1, self.py0, self.py1 = left, right, top, bottom
        require(self.px1 - self.px0 > 20 and self.py1 - self.py0 > 20,
                "The chart is too small for its labels; enlarge it, shorten the text or lower font_size")
        self.base = 0 if self.lo <= 0 <= self.hi else self.lo

    def prepare_callouts(self):
        """The callout of each focus category, made before the plot is sized so it gets its room. With one
        series in focus it speaks for that mark and takes the place of its value label; otherwise it speaks for
        the whole category and ``${value}`` is the category's total."""
        em, totals = self.em, self.stats["totals"]
        if not em.text:
            return
        single = em.series if em.series is not None else (0 if self.m == 1 else None)
        for i in em.categories:
            category = self.categories[i]
            value = self.series[single]["values"][i] if single is not None else totals["by_category"][category]
            if value is None:
                continue
            text = em.callout(value, category, self.series[single]["name"] if single is not None else None,
                              totals["grand"], self.label_format)
            self.callouts[i] = self.kit.make(self.kit.wrap(text, self.style.fs, self.W * 0.4), self.style.fs,
                                             self.style.ink, align="left" if self.horizontal else "center")
            if single is not None and not (self.bars and self.stacked):
                self.quiet.add((single, i))

    def draw_callouts(self):
        """Callouts beside their focus marks: above a bar, stack or point (below a negative one), past the end of
        a horizontal bar, clear of the value labels drawn there. Automatic value labels keep clear of them."""
        style, gap, em = self.style, self.gap, self.em
        lift = round(self.value_cap + gap * 1.5)
        for i, lab in self.callouts.items():
            series = [em.series] if em.series is not None else list(range(self.m))
            whole = self.bars and self.stacked
            if self.bars:
                boxes = [self.extent[(s, i)] for s in (range(self.m) if whole else series) if (s, i) in self.extent]
                if not boxes:
                    continue
                x0, y0 = min(b[0] for b in boxes), min(b[1] for b in boxes)
                x1, y1 = max(b[0] + b[2] for b in boxes), max(b[1] + b[3] for b in boxes)
                reach = gap
            else:
                points = [self.points[(s, i)] for s in series if (s, i) in self.points]
                if not points:
                    continue
                x0 = x1 = points[0][0]
                y0, y1 = min(p[1] for p in points), max(p[1] for p in points)
                reach = max(p[2] for p in points)
            up = sum(self.zero[s][i] for s in (range(self.m) if whole else series)) >= 0
            if whole:
                labelled = self.totals_shown
            else:
                labelled = (self.shown if self.bars else self.point_labels) and not any((s, i) in self.quiet for s in series)
            if self.horizontal:
                offset = self.longest if labelled else 0
                left, top = spot(lab, x1 + reach + offset if up else x0 - reach - offset, (y0 + y1) / 2,
                                 "left" if up else "right", "mid")
            else:
                offset = lift if labelled else 0
                left, top = spot(lab, (x0 + x1) / 2, y0 - reach - offset - lab["height"] if up else y1 + reach + offset,
                                 "center", "top")
            if self.bars and not whole and up:
                # A callout wider than its bar clears the neighbouring bars of the category and their labels.
                for s in range(self.m):
                    if s in series or (s, i) not in self.extent:
                        continue
                    bx, by, bw, bh = self.extent[(s, i)]
                    if self.horizontal:
                        reach_x = bx + bw + (self.longest if self.shown else 0)
                        if Collider.overlaps((left, top, lab["width"], lab["height"]), (bx, by, reach_x - bx, bh), gap):
                            left = max(left, reach_x + gap)
                    else:
                        roof = by - (lift if self.shown else 0)
                        if Collider.overlaps((left, top, lab["width"], lab["height"]), (bx, roof, bw, bh + by - roof), gap):
                            top = min(top, roof - gap - lab["height"])
            elif not self.bars and em.series is not None:
                # Beside other lines, the callout goes below its point when that is the side clear of them.
                key = f"value-{em.series}-{i}"
                other = y1 + reach + offset if up else y0 - reach - offset - lab["height"]
                if not self.clear_of_marks((round(left), round(top), lab["width"], lab["height"]), key) and \
                        self.clear_of_marks((round(left), round(other), lab["width"], lab["height"]), key):
                    top = other
            left = min(max(left, style.pad), max(style.pad, self.W - style.pad - lab["width"]))
            top = min(max(top, style.pad), max(style.pad, self.H - style.pad - lab["height"]))
            box = self.parts.text(f"callout-{i}", f"callout {self.categories[i]}", lab, left, top, Z_VALUES)
            self.marks.append((-1, box))

    def vp(self, value):
        """Pixel position of a value along the value axis."""
        fraction = (value - self.lo) / (self.hi - self.lo)
        if self.horizontal:
            return self.px0 + fraction * (self.px1 - self.px0)
        return self.py1 - fraction * (self.py1 - self.py0)

    def center(self, i):
        if self.horizontal:
            return self.py0 + (i + 0.5) * self.band
        return self.px0 + i * self.band if self.area else self.px0 + (i + 0.5) * self.band

    def box(self, c0, c1, v0, v1):
        """Rounded x, y, width, height of a mark spanning c0–c1 along the categories and v0–v1 along the values."""
        a0, a1, b0, b1 = round(c0), round(c1), round(min(v0, v1)), round(max(v0, v1))
        if self.horizontal:
            return b0, a0, max(1, b1 - b0), max(1, a1 - a0)
        return a0, b0, max(1, a1 - a0), max(1, b1 - b0)

    def label(self, key, name, value, x, y, anchor, color, at="base", fit=None, drop=0, alternative=None):
        """A data label at (x, y + ``drop`` cap heights). Forced labels are placed at once; automatic ones wait
        for ``place_labels``, which decides for the chart as a whole; ``alternative`` (y, drop) is a second spot
        (below a line's point instead of above it) for when the first one sits on another series."""
        entry = {"key": key, "name": name, "text": format_number(value, self.label_format), "x": x, "y": y,
                 "anchor": anchor, "color": color, "at": at, "fit": fit, "drop": drop, "alternative": alternative}
        if self.auto:
            self.pending.append(entry)
            return
        lab = self.kit.make(entry["text"], self.value_size, color)
        left, top = spot(lab, x, y + drop * self.value_cap, anchor, at)
        self.crowd.take((round(left), round(top), lab["width"], lab["height"]))
        self.parts.text(key, name, lab, left, top, Z_VALUES)

    def layout_labels(self, entries, size):
        """``[(entry, lab, left, top)]`` for ``entries`` at ``size``, or None when one of them does not fit its
        mark, leaves the chart or crowds another."""
        crowd, placed = Collider(), []
        cap = self.kit.make("0", size, self.style.ink)["cap"]
        for entry in entries:
            lab = self.kit.make(entry["text"], size, entry["color"])
            fit = entry["fit"]
            if fit and ((fit[0] is not None and lab["width"] > fit[0]) or (fit[1] is not None and lab["height"] > fit[1])):
                return None
            y, drop = entry["alternative"] if entry.get("flipped") else (entry["y"], entry["drop"])
            left, top = spot(lab, entry["x"], y + drop * cap, entry["anchor"], entry["at"])
            box = (round(left), round(top), lab["width"], lab["height"])
            if not (crowd.free(box) and 0 <= box[0] and box[0] + box[2] <= self.W and 0 <= box[1]
                    and box[1] + box[3] <= self.H and self.clear_of_marks(box, entry["key"])):
                return None
            crowd.take(box)
            placed.append((entry, lab, left, top))
        return placed

    def clear_of_marks(self, box, key):
        """A value label that touches no line or marker of another series (resting on one, it hides it; its
        own line may run under it, as it always has)."""
        own = int(key.split("-")[1]) if key.startswith("value-") else None
        if any(Collider.overlaps(box, mark) for series, mark in self.marks if series != own):
            return False
        return not any(crosses(box, a, b, width / 2 + 1) for series, run, width in self.paths if series != own
                       for a, b in zip(run, run[1:]))

    def place_labels(self):
        """Automatic labels, decided for the whole chart so they thin evenly: every label (at a smaller size if
        that is what fits), else whole series from the largest down, else every k-th label of the largest
        series, else none. A series never loses labels from some of its marks only."""
        if not self.pending:
            return
        floor = max(8, self.style.snap(self.style.fs * 0.6))
        sizes = sorted({self.value_size, *(max(floor, self.style.snap(self.value_size * f)) for f in (0.85, 0.7))},
                       reverse=True)
        sizes = [size for size in sizes if size <= self.value_size]
        groups = {}
        for entry in self.pending:
            groups.setdefault(entry["key"].rsplit("-", 1)[0], []).append(entry)

        def weight(name):
            if name == "total":
                return math.inf  # asked for explicitly
            values = self.series[int(name.split("-")[1])]["values"]
            return sum(abs(v) for v in values if v is not None)

        order = sorted(groups, key=weight, reverse=True)
        chosen = None
        for size in sizes:
            chosen = self.layout_labels([e for name in order for e in groups[name]], size)
            if chosen:
                break
        if not chosen and any(e.get("alternative") for name in order[1:] for e in groups[name]):
            # Lines that run close: the largest series keeps its labels above its points, the others move theirs
            # below theirs, each series on one side.
            flipped = [{**e, "flipped": bool(e.get("alternative"))} for name in order[1:] for e in groups[name]]
            for size in sizes:
                chosen = self.layout_labels(groups[order[0]] + flipped, size)
                if chosen:
                    break
        if not chosen:
            best = None
            for size in sizes:
                if not self.layout_labels(groups[order[0]], size):
                    continue
                kept = []
                for name in order:
                    if self.layout_labels(kept + groups[name], size):
                        kept += groups[name]
                if best is None or len(kept) > len(best[0]):
                    best = (kept, size)
            if best:
                chosen = self.layout_labels(*best)
        if not chosen:
            first = groups[order[0]]
            for stride in range(2, len(first)):
                for size in sizes:
                    chosen = self.layout_labels(first[::stride], size)
                    if chosen:
                        break
                if chosen:
                    break
        for entry, lab, left, top in chosen or []:
            self.crowd.take((round(left), round(top), lab["width"], lab["height"]))
            self.parts.text(entry["key"], entry["name"], lab, left, top, Z_VALUES)
        self.pending = []

    def axes(self):
        parts, style, gap = self.parts, self.style, self.gap
        gw = max(1, round(style.fs / 14))
        baseline = self.vp(self.base)
        x0, y0 = round(self.px0), round(self.py0)
        w, h = round(self.px1 - self.px0), round(self.py1 - self.py0)
        for i, t in enumerate(self.ticks):
            if self.recipe.get("gridlines", True) and abs(self.vp(t) - baseline) > 0.5:
                at = round(self.vp(t) - gw / 2)
                parts.rect(f"gridline-{i}", f"gridline {i + 1}", (at, y0, gw, h) if self.horizontal else (x0, at, w, gw),
                           style.grid, Z_GRID, role="decoration")
            lab = self.tick_labels[i]
            if self.horizontal:
                place(parts, f"tick-label-{i}", f"tick label {i + 1}", lab, self.vp(t), self.py1 + gap + self.cap, Z_AXIS_TEXT, "center")
            else:
                place(parts, f"tick-label-{i}", f"tick label {i + 1}", lab, self.px0 - gap, self.vp(t) + self.cap / 2,
                      Z_AXIS_TEXT, "right")
        at = round(baseline - (gw + 1) / 2)
        parts.rect("axis-line", "axis line", (at, y0, gw + 1, h) if self.horizontal else (x0, at, w, gw + 1),
                   style.axis, Z_AXIS, role="decoration")
        if self.horizontal:
            for i, lab in enumerate(self.cat_labels):
                place(parts, f"category-label-{i}", f"category label {i + 1}", lab, self.px0 - gap * 1.5, self.center(i),
                      Z_AXIS_TEXT, "right", "mid")
        else:
            for i, lab in self.cat_labels:
                place(parts, f"category-label-{i}", f"category label {i + 1}", lab, self.center(i),
                      self.py1 + gap + self.cap, Z_AXIS_TEXT, "center")
        if self.side_title:
            lab = self.side_title
            parts.text("side-title", "side title", lab, self.title_x, (self.py0 + self.py1) / 2 - lab["width"] / 2,
                       Z_AXIS_TEXT, rotation=270)
        if self.bottom_title:
            place(parts, "bottom-title", "bottom title", self.bottom_title, (self.px0 + self.px1) / 2, self.title_y,
                  Z_AXIS_TEXT, "center", "top")

    def draw_bars(self):
        parts, style, gap, n, m = self.parts, self.style, self.gap, self.n, self.m
        inner = 0 if self.stacked or m == 1 else (2 if self.band / m > 14 else 1)
        group = self.band * (1 - self.recipe.get("bar_gap", 0.3))
        slot = group if self.stacked else (group - inner * (m - 1)) / m
        positive, negative = [0] * n, [0] * n
        for s_index, s in enumerate(self.series):
            for i, v in enumerate(s["values"]):
                if not v:
                    continue
                start = self.center(i) - group / 2 + (0 if self.stacked else s_index * (slot + inner))
                if self.stacked:
                    running = positive if v > 0 else negative
                    share = v / (sum(row[i] for row in self.zero) / 100) if self.percent else v
                    v0, v1 = self.vp(running[i]), self.vp(running[i] + share)
                    running[i] += share
                else:
                    v0, v1 = self.vp(self.base), self.vp(v)
                x, y, w, h = self.box(start, start + slot, v0, v1)
                fill = self.em.color(self.colors[s_index], s_index, i)
                parts.rect(f"bar-{s_index}-{i}", f"bar {s['name']} {self.categories[i]}", (x, y, w, h), fill, Z_MARKS)
                self.extent[(s_index, i)] = (x, y, w, h)
                if not self.shown or (s_index, i) in self.quiet:
                    continue
                key, name = f"value-{s_index}-{i}", f"value {s['name']} {self.categories[i]}"
                ink = self.em.ink(style, s_index, i)
                if self.stacked:
                    self.label(key, name, v, x + w / 2, y + h / 2, "center", style.on(fill),
                               fit=(w - 4, h - 2), drop=0.5)
                elif self.horizontal:
                    forward = v > 0
                    self.label(key, name, v, x + w + gap if forward else x - gap, y + h / 2,
                               "left" if forward else "right", ink, fit=(None, h * 1.3), drop=0.5)
                elif v > 0:
                    self.label(key, name, v, x + w / 2, y - gap, "center", ink, fit=(max(w * 1.3, self.band / m), None))
                else:
                    self.label(key, name, v, x + w / 2, y + h + gap, "center", ink, fit=(max(w * 1.3, self.band / m), None), drop=1)
        if not self.totals_shown:
            return
        for i, category in enumerate(self.categories):
            if not any(row[i] for row in self.zero):
                continue
            total, up = self.stats["totals"]["by_category"][category], positive[i] > 0
            end = self.vp(positive[i] if up else negative[i])
            key, name, ink = f"total-{i}", f"total {category}", self.em.ink(style, None, i)
            if self.horizontal:
                self.label(key, name, total, end + gap if up else end - gap, self.center(i),
                           "left" if up else "right", ink, drop=0.5)
            elif up:
                self.label(key, name, total, self.center(i), end - gap, "center", ink)
            else:
                self.label(key, name, total, self.center(i), end + gap, "center", ink, drop=1)

    def draw_lines(self):
        parts, style, gap, n, em = self.parts, self.style, self.gap, self.n, self.em
        width = self.recipe.get("line_width") or (max(2, round(style.fs * 0.18)) if n <= 60 else 1.5)
        dots = self.recipe.get("markers", n * self.m <= 60) and not self.area
        dot = max(6, round(width * 2.4))
        below = [0] * n
        for s_index, s in enumerate(self.series):
            own, name = self.colors[s_index], s["name"]
            color = em.color(own, s_index)
            if self.area:
                tops = [below[i] + (v or 0) if self.stacked else (v or 0) for i, v in enumerate(s["values"])]
                lower = [below[i] if self.stacked else self.base for i in range(n)]
                upper = [(self.center(i), self.vp(tops[i])) for i in range(n)]
                floor = [(self.center(i), self.vp(lower[i])) for i in reversed(range(n))]
                segment(self.project, parts, "area", f"area-{s_index}", f"area {name}", upper + floor, color,
                        z=Z_MARKS, init={"opacity": 1 if self.stacked else 0.75})
                below = tops if self.stacked else below
                points = upper
            else:
                runs, run = [], []
                for i, v in enumerate(s["values"]):
                    if v is None:
                        runs.append(run)
                        run = []
                    else:
                        run.append((self.center(i), self.vp(v)))
                runs.append(run)
                for r_index, run in enumerate(runs):
                    if len(run) > 1:
                        segment(self.project, parts, "line", f"line-{s_index}-{r_index}", f"line {name}", run, "transparent",
                                color, width, Z_LINES)
                        self.paths.append((s_index, run, width))
                points = [(self.center(i), self.vp(v)) if v is not None else None for i, v in enumerate(s["values"])]
            for i, point in enumerate(points):
                if point is None:
                    continue
                x, y = point
                size = dot if dots else width
                if dots:
                    parts.add(f"marker-{s_index}-{i}", f"marker {name} {self.categories[i]}", "ellipse", Z_MARKERS,
                              x=round(x - dot / 2), y=round(y - dot / 2), width=dot, height=dot,
                              fill=em.color(own, s_index, i))
                    if not self.area:
                        self.marks.append((s_index, (round(x - dot / 2), round(y - dot / 2), dot, dot)))
                if i in em.categories and em.focused(s_index, i) and s["values"][i] is not None:
                    # The point in focus: a larger dot in the series colour, ringed in the background colour.
                    size = round(dot * 1.7)
                    box = (round(x - size / 2), round(y - size / 2), size, size)
                    parts.add(f"focus-{s_index}-{i}", f"focus {name} {self.categories[i]}", "ellipse", Z_MARKERS,
                              x=box[0], y=box[1], width=size, height=size, fill=em.color(own, s_index, i),
                              stroke=style.separator, stroke_width=max(1, round(dot * 0.2)))
                    self.marks.append((s_index, box))
                if s["values"][i] is not None:
                    self.points[(s_index, i)] = (x, y, size / 2 + gap)
                if self.point_labels and s["values"][i] is not None and (s_index, i) not in self.quiet:
                    value, reach = s["values"][i], size / 2 + gap
                    key, label = f"value-{s_index}-{i}", f"value {name} {self.categories[i]}"
                    above, below = (y - reach, 0), (y + reach, 1)
                    first, second = (above, below) if value >= 0 else (below, above)
                    self.label(key, label, value, x, first[0], "center", em.ink(style, s_index, i), drop=first[1],
                               alternative=second if self.m > 1 and not self.area else None)

    def draw_legend(self):
        legend, W, H, pad = self.legend, self.W, self.H, self.style.pad
        if not legend:
            return
        if self.position == "bottom":
            legend.emit(self.parts, max(pad, (self.px0 + self.px1) / 2 - legend.width / 2), H - pad - legend.height)
        elif self.position == "top":
            legend.emit(self.parts, self.px0, self.legend_y)
        elif self.position == "left":
            legend.emit(self.parts, pad, (self.py0 + self.py1) / 2 - legend.height / 2)
        else:
            legend.emit(self.parts, W - pad - legend.width, (self.py0 + self.py1) / 2 - legend.height / 2)


def polar(cx, cy, radius, angle):
    """The point ``radius`` from the center at ``angle`` radians clockwise from 12 o'clock."""
    return cx + radius * math.sin(angle), cy - radius * math.cos(angle)


def wedge_path(cx, cy, outer, inner, start, end):
    """``(build, samples)`` for a pie slice or donut segment from ``start`` to ``end`` radians: ``build(ox, oy)``
    gives its SVG path relative to an origin, ``samples`` are points along its outline for sizing the layer."""
    sweep = end - start
    steps = max(2, math.ceil(math.degrees(sweep) / 2))
    angles = [start + sweep * k / steps for k in range(steps + 1)]
    samples = [polar(cx, cy, outer, a) for a in angles] + ([polar(cx, cy, inner, a) for a in angles] if inner else [(cx, cy)])

    def build(ox, oy):
        def pt(radius, angle):
            x, y = polar(cx, cy, radius, angle)
            return f"{x - ox:.2f} {y - oy:.2f}"

        arc = lambda radius, large, direction: f"A {radius:.2f} {radius:.2f} 0 {large} {direction}"  # noqa: E731
        if sweep >= 2 * math.pi - 1e-6:
            half = start + math.pi
            path = (f"M {pt(outer, start)} {arc(outer, 1, 1)} {pt(outer, half)} {arc(outer, 1, 1)} {pt(outer, start)} Z")
            if inner:
                path += f" M {pt(inner, start)} {arc(inner, 1, 0)} {pt(inner, half)} {arc(inner, 1, 0)} {pt(inner, start)} Z"
            return path
        large = 1 if sweep > math.pi else 0
        if inner:
            return (f"M {pt(outer, start)} {arc(outer, large, 1)} {pt(outer, end)} L {pt(inner, end)} "
                    f"{arc(inner, large, 0)} {pt(inner, start)} Z")
        return f"M {cx - ox:.2f} {cy - oy:.2f} L {pt(outer, start)} {arc(outer, large, 1)} {pt(outer, end)} Z"

    return build, samples


def radial(project, recipe, size, style, kit, parts, stats):
    """Pie and donut: wedges as path layers, percent labels pushed apart around the ring, legend, center text."""
    W, H = size
    donut = recipe["kind"] == "donut"
    categories, values = recipe["categories"], recipe["series"][0]["values"]
    require(len(recipe["series"]) == 1, "Pie and donut charts take one series; the categories are the slices", field="series")
    require(all(v is None or v >= 0 for v in values), "Pie and donut values cannot be negative", field="series")
    total = stats["totals"]["grand"]
    require(total > 0, "A pie or donut needs a positive total", field="series")
    fs, pad = style.fs, style.pad
    gap = max(3, round(fs * 0.45))
    colors = style.colors(len(categories))
    em = Emphasis(project, recipe, style)
    drawn = [em.color(color, 0, i) for i, color in enumerate(colors)]
    shown, force, content = labels_mode(recipe, True)
    label_format = recipe.get("number_format") or auto_format([v for v in values if v is not None])
    shares = [(v or 0) / total for v in values]
    percent_format = "0%" if all(abs(s * 100 - round(s * 100)) < 0.05 for s in shares) else "0.0%"

    def slice_text(i):
        percent, amount = format_number(shares[i], percent_format), format_number(values[i], label_format)
        return {"percent": percent, "value": amount, "both": f"{amount} ({percent})"}[content]

    top = header(kit, style, recipe, parts, size)
    left, right, bottom = pad, W - pad, H - pad
    position = legend_position(recipe, len(categories), True)
    legend = None
    if position:
        if recipe.get("legend_values"):
            entries = [(c, format_number(values[i] or 0, label_format), format_number(shares[i], percent_format), drawn[i])
                       for i, c in enumerate(categories)]
            legend = ValueLegend(project, kit, style, entries, position, W - 2 * pad)
            # The list pairs each name with its value and share, so automatic labels around the ring would repeat it.
            shown = shown and force
        else:
            legend = Legend(kit, style, [(c, drawn[i]) for i, c in enumerate(categories)], position, W - 2 * pad)
        if position == "top":
            legend_y, top = top, top + legend.height + gap
        elif position == "bottom":
            bottom -= legend.height + gap
        elif position == "left":
            left += legend.width + gap * 2
        else:
            right -= legend.width + gap * 2
    labels = {i: kit.make(slice_text(i), fs, em.ink(style, 0, i)) for i in range(len(categories))
              if shown and shares[i] > 0}
    # A callout takes the place of its slice's label, so the labels still clear each other around the ring.
    callouts = {i: kit.make(kit.wrap(em.callout(values[i], categories[i], recipe["series"][0]["name"], total,
                                                label_format), fs, W * 0.3), fs, style.ink)
                for i in em.categories if em.text and shares[i] > 0}
    labels.update(callouts)
    room_x = max((lab["width"] for lab in labels.values()), default=0) + gap if labels else 0
    room_y = max((lab["height"] for lab in labels.values()), default=0) + gap if labels else 0
    cx, cy = (left + right) / 2, (top + bottom) / 2
    outer = min(right - left - 2 * room_x, bottom - top - 2 * room_y) / 2
    require(outer >= 12, "The chart is too small for its labels; enlarge it, shorten the text or lower font_size")
    inner = outer * recipe.get("hole", 0.55) if donut else 0
    outline = max(1, round(fs / 8))
    start, cumulative = math.radians(recipe.get("start_angle", 0)), 0.0
    last = max(i for i, s in enumerate(shares) if s > 0)
    sides = {True: [], False: []}
    for i, share in enumerate(shares):
        if share <= 0:
            continue
        a0 = start + cumulative * 2 * math.pi
        cumulative += share
        a1 = start + (2 * math.pi if i == last else cumulative * 2 * math.pi)
        build, samples = wedge_path(cx, cy, outer, inner, a0, a1)
        pad_ = outline / 2 + 1
        x0, y0 = math.floor(min(p[0] for p in samples) - pad_), math.floor(min(p[1] for p in samples) - pad_)
        w = math.ceil(max(p[0] for p in samples) + pad_) - x0
        h = math.ceil(max(p[1] for p in samples) + pad_) - y0
        parts.add(f"slice-{i}", f"slice {categories[i]}", "path", Z_MARKS, x=x0, y=y0, width=w, height=h, path=build(x0, y0),
                  path_view=[w, h], fill=drawn[i], stroke=style.separator, stroke_width=outline, line_cap="round")
        if i in labels:
            # Just outside the slice's middle; labels at the top or bottom sit above or below the ring.
            middle, lab = (a0 + a1) / 2, labels[i]
            x, y = polar(cx, cy, outer + gap, middle)
            sides[math.sin(middle) >= 0].append([i, lab, x + math.sin(middle) * lab["width"] / 2,
                                                  y - math.cos(middle) * lab["height"] / 2])
    ring = outer + gap
    for right_side, items in sides.items():
        items.sort(key=lambda item: item[3])
        for k in range(1, len(items)):
            items[k][3] = max(items[k][3], items[k - 1][3] + (items[k - 1][1]["height"] + items[k][1]["height"]) / 2 + 2)
        if items and items[-1][3] + items[-1][1]["height"] / 2 > H - pad:
            items[-1][3] = H - pad - items[-1][1]["height"] / 2
            for k in range(len(items) - 2, -1, -1):
                items[k][3] = min(items[k][3], items[k + 1][3] - (items[k][1]["height"] + items[k + 1][1]["height"]) / 2 - 2)
        for i, lab, x, y in items:
            # A label pushed beside the ring keeps its inner edge outside it.
            near = max(0.0, abs(y - cy) - lab["height"] / 2)
            if near < ring:
                x = cx + (1 if right_side else -1) * (math.sqrt(ring * ring - near * near) + lab["width"] / 2)
            key = "callout" if i in callouts else "slice-label"
            place(parts, f"{key}-{i}", f"{key.replace('-', ' ')} {categories[i]}", lab, x, y, Z_VALUES, "center", "mid")
    if donut and recipe.get("center_text"):
        text = recipe["center_text"].replace("{total}", format_number(total, label_format))
        points = style.snap(fs * 1.8)
        lab = kit.make(text, points, style.ink, True, "center")
        while points > 8 and (lab["width"] > inner * 1.7 or lab["height"] > inner * 1.2):
            points = style.smaller(points)
            lab = kit.make(text, points, style.ink, True, "center")
        place(parts, "center-text", "center text", lab, cx, cy, Z_TITLE, "center", "mid")
    if legend:
        oy = {"top": legend_y if position == "top" else 0, "bottom": H - pad - legend.height}.get(position)
        ox = {"left": pad, "right": W - pad - legend.width}.get(position, (left + right) / 2 - legend.width / 2)
        legend.emit(parts, ox, cy - legend.height / 2 if oy is None else oy)
    stats["slices"] = {c: {"value": values[i], "share": round(shares[i] * 100, 6)} for i, c in enumerate(categories)}
    if em.active:
        stats["emphasis"] = em.summary(recipe)
    stats.update(label_format=label_format, percent_format=percent_format, colors=colors, legend=position)


def layout(project, recipe, size):
    """``(parts, statistics)``: every layer the chart is made of, in stacking order, plus what it says in numbers."""
    style = Style(project, recipe, *size)
    kit = Kit(project, recipe, style)
    parts, stats = Parts(), statistics(recipe)
    if recipe["kind"] in ("pie", "donut"):
        radial(project, recipe, size, style, kit, parts, stats)
    else:
        Cartesian(project, recipe, size, style, kit, parts, stats).build()
    if recipe.get("background"):
        parts.rect("background", "background", (0, 0, *size), recipe["background"], Z_BACKGROUND)
    stats["labels"] = sum(1 for item in parts.items if item["key"].startswith(("value-", "slice-label-")))
    return parts, stats


SHAPES = {"rect": "rectangle", "ellipse": "ellipse", "path": "path"}


def part_kind(layer):
    return "text" if layer["type"] == "text" else {v: k for k, v in SHAPES.items()}.get(layer.get("shape"))


def child_name(project, group, label, layer=None):
    base = f"{group['name']}/{label}"[:190]
    taken = {x["name"] for x in project.state["layers"] if x is not layer} | {x["id"] for x in project.state["layers"]}
    name, index = base, 2
    while name in taken:
        name, index = f"{base} {index}", index + 1
    return name


_PART_KEY = re.compile(r"([a-z]+(?:-[a-z]+)*)((?:-\d+)+)")
_SERIES_CATEGORY = {"bar": "bar", "marker": "point", "focus": "point", "value": "value"}
_CATEGORY = {"slice": "slice", "slice-label": "value", "total": "total", "category-label": "category-label",
             "callout": "callout"}
_LEGEND = ("legend-swatch", "legend-label", "legend-value", "legend-share")


def mark_of(key, recipe):
    """``(mark, slot)`` for a generated part key: ``mark`` is what the part stands for in the data,
    ``{part, series?, category?}`` by name, and ``slot`` tells apart the parts that share a mark (a legend entry's
    swatch and label, the runs of a broken line). ``(None, None)`` for parts that belong to no series or category
    (gridlines, ticks, titles)."""
    match = _PART_KEY.fullmatch(key or "")
    if not match:
        return None, None
    head, numbers = match[1], [int(n) for n in match[2].split("-")[1:]]
    categories, names = recipe.get("categories", []), [s.get("name") for s in recipe.get("series", [])]
    radial = recipe.get("kind") in ("pie", "donut")
    try:
        if head in _SERIES_CATEGORY and len(numbers) == 2:
            return {"part": _SERIES_CATEGORY[head], "series": names[numbers[0]], "category": categories[numbers[1]]}, head
        if head == "line" and len(numbers) == 2:
            return {"part": "line", "series": names[numbers[0]]}, f"line-{numbers[1]}"
        if head == "area" and len(numbers) == 1:
            return {"part": "area", "series": names[numbers[0]]}, head
        if head in _CATEGORY and len(numbers) == 1:
            return {"part": _CATEGORY[head], **({"series": names[0]} if radial else {}),
                    "category": categories[numbers[0]]}, head
        if head in _LEGEND and len(numbers) == 1:
            if radial:
                return {"part": "legend", "series": names[0], "category": categories[numbers[0]]}, head
            return {"part": "legend", "series": names[numbers[0]]}, head
    except IndexError:
        pass
    return None, None


def identity(key, mark):
    """What a part is, whatever its position in the table: its slot plus the series and category it stands for."""
    match = _PART_KEY.fullmatch(key or "")
    if not match or not isinstance(mark, dict):
        return None
    slot = f"line-{match[2].rsplit('-', 1)[1]}" if match[1] == "line" else match[1]
    return slot, mark.get("series"), mark.get("category")


def resolve_mark(project, address):
    """Layer IDs of the chart parts an address names, in stacking order.

    ``address`` is ``{chart, series?, category?, part?}``: the chart group, the series and category by name as the
    data has them, and the part (``MARK_PARTS``; without one, the data marks: bars, slices, points, lines and
    areas). A part matches when it agrees with every name given, so ``{chart, category}`` is every bar of that
    category and ``{chart, series}`` a whole series. The lookup reads the chart's data, so it holds after
    ``chart-data`` edits that add, remove or reorder rows. Unknown names are an error listing the valid ones."""
    require(isinstance(address, dict), "A chart mark address is {chart, series?, category?, part?}", field="target")
    extra = sorted(set(address) - {"chart", "series", "category", "part"})
    require(not extra, f"A chart mark address takes chart, series, category and part; got {', '.join(map(repr, extra))}",
            field="target", allowed=["chart", "series", "category", "part"])
    group = project.layer(address.get("chart"))
    require(group["type"] == "group" and "chart" in group, f"{group['name']!r} is not a chart; chart names a chart group",
            field="target.chart")
    recipe = group["chart"]
    names = [s["name"] for s in recipe["series"]]
    wanted = {}
    if address.get("series") is not None:
        wanted["series"] = names[find(names, address["series"], "series", "target.series")]
    if address.get("category") is not None:
        wanted["category"] = recipe["categories"][find(recipe["categories"], address["category"], "category",
                                                       "target.category")]
    part = address.get("part")
    require(part is None or part in MARK_PARTS or part == "mark",
            f"part must be one of {', '.join(MARK_PARTS)} (or mark, the default: the data marks); got {part!r}",
            field="target.part", allowed=["mark", *MARK_PARTS])
    kinds = DATA_MARKS if part in (None, "mark") else (part,)
    found, present = [], set()
    for layer in project.state["layers"]:
        if layer.get("parent") != group["id"]:
            continue
        mark, _ = mark_of(layer.get("chart_part"), recipe)
        if mark is None:
            continue
        present.add(mark["part"])
        if mark["part"] in kinds and all(mark.get(key) == value for key, value in wanted.items()):
            found.append(layer["id"])
    if not found:
        what = " or ".join(kinds) if len(kinds) < 4 else "data mark"
        where = ", ".join(f"{key} {value!r}" for key, value in wanted.items()) or "any series or category"
        raise VixlError("invalid_operation", f"{group['name']!r} draws no {what} for {where}. Its parts: "
                        f"{', '.join(sorted(present)) or 'none'}" + ("; a line or area belongs to a series, not a "
                        "category: name the point, or leave category out" if "category" in wanted and
                        set(kinds) <= {"line", "area"} else ""), field="target", allowed=sorted(present))
    return found


def resolve_target(project, address):
    """The ``target-resolver`` hook: a ``{chart, ...}`` address is a chart mark; anything else is not ours."""
    if not isinstance(address, dict) or "chart" not in address:
        return None
    return resolve_mark(project, address)


def sync(project, group, parts, field="chart_part", marks=None):
    """Make the group's generated children match ``parts``: update layers in place (same IDs), add the
    missing ones, drop the ones the chart no longer draws, and order them as the layout stacks them. ``field`` is
    the layer key holding each part's key (tables use ``table_part``).

    ``marks(key)`` gives ``(mark, slot)`` for the parts that stand for data (``mark_of``). Those layers carry the
    mark as ``chart_mark`` and are matched by it rather than by their key, which is a position in the table: when
    rows are reordered or removed, the layer of a series and category stays that series and category, with its ID
    and whatever was added to it."""
    layers = project.state["layers"]
    wanted = parts.ordered()
    mine = {x[field]: x for x in layers if x.get("parent") == group["id"] and field in x}
    known = {}
    for key, layer in mine.items():
        ident = identity(key, layer.get("chart_mark")) if marks else None
        if ident is not None:
            known.setdefault(ident, layer)
    reuse, used = {}, set()
    for part in wanted:
        mark = marks(part["key"])[0] if marks else None
        part["mark"] = mark
        layer = known.get(identity(part["key"], mark)) if mark else None
        if layer is None:
            # Not a data part, or a document from before marks were stored: the key is the identity.
            layer = mine.get(part["key"])
            if layer is not None and mark and isinstance(layer.get("chart_mark"), dict):
                layer = None
        if layer is not None and layer["id"] not in used and part_kind(layer) == part["kind"]:
            reuse[part["key"]] = layer
            used.add(layer["id"])
    stale = [x for x in mine.values() if x["id"] not in used]
    fresh = sum(1 for p in wanted if p["key"] not in reuse)
    require(len(layers) - len(stale) + fresh <= project.limits.max_layers,
            f"This chart needs {len(layers) - len(stale) + fresh} layers; a document holds at most "
            f"{project.limits.max_layers}. Use fewer categories, or turn off value_labels or markers",
            "resource_limit", field="categories")
    removed = {x["id"] for x in stale}
    if removed:
        layers[:] = [x for x in layers if x["id"] not in removed]
        for item in layers:
            if item.get("clip") in removed:
                item.pop("clip")
        from ...timeline import prune_targets

        prune_targets(project.state, removed)
    # Layers that change places take each other's names (category label 2 becomes category label 3): free the
    # names first, so none of them is pushed to "… 2" by a name its old holder is about to give up.
    for part in wanted:
        layer = reuse.get(part["key"])
        if layer is not None and layer["name"] != f"{group['name']}/{part['label']}"[:190]:
            layer["name"] = f"\x00{layer['id']}"
    kept = []
    for part in wanted:
        fields, layer = part["fields"], reuse.get(part["key"])
        if layer is None:
            project.limits.size(fields["width"], fields["height"])
            layer = new_layer(child_name(project, group, part["label"]), "text" if part["kind"] == "text" else "shape",
                              fields["width"], fields["height"], parent=group["id"], **{field: part["key"]})
            if part["kind"] == "text":
                layer["auto_size"] = True
            else:
                layer["shape"] = SHAPES[part["kind"]]
            layer.update(deepcopy(part["init"]))
            layers.append(layer)
        else:
            name = f"{group['name']}/{part['label']}"[:190]
            if layer["name"] != name:
                layer["name"] = child_name(project, group, part["label"], layer)
        layer.update(deepcopy(fields))
        layer[field] = part["key"]
        if part["mark"]:
            layer["chart_mark"] = part["mark"]
        else:
            layer.pop("chart_mark", None)
        if part["kind"] == "text" and "font_role" not in fields:
            layer.pop("font_role", None)
        kept.append(layer)
    # A value label is set against the marks by design (a line runs through it, an area lies under it, it sits on
    # its bar): those pairs are not overlap findings. Labels against each other still are.
    drawn = [(x[field], x["id"]) for x in kept if x["type"] != "text"]
    for layer in kept:
        key = layer[field]
        if key.startswith(("value-", "total-")):
            category = key.rsplit("-", 1)[1]
            own = [ident for part, ident in drawn if part.startswith(("line-", "area-"))
                   or (part.startswith(("bar-", "marker-")) and part.rsplit("-", 1)[1] == category)]
            layer["allow_overlap"] = own[:512]
    ids = {x["id"] for x in kept}
    foreign = [x for x in layers if x.get("parent") == group["id"] and x["id"] not in ids]
    rest = [x for x in layers if x["id"] not in ids and x not in foreign]
    at = rest.index(group)
    layers[:] = rest[:at] + kept + foreign + rest[at:]
    return len(kept)


def redraw(project, group, recipe, size=None):
    """Lay the recipe out again into ``group`` (resized to ``size`` when given) and record the statistics."""
    width, height = size or (group["content_width"], group["content_height"])
    settle_emphasis(project, group, recipe)
    check_options(project.state, recipe)
    parts, stats = layout(project, recipe, (width, height))
    stats["layers"] = sync(project, group, parts, marks=lambda key: mark_of(key, recipe))
    recipe["summary"] = stats
    group["chart"] = recipe
    group["content_width"], group["content_height"] = width, height
    if size:
        group["width"], group["height"] = width, height
    project.state["active_layer"] = group["id"]


def settle_emphasis(project, group, recipe):
    """Keep a chart's emphasis in step with its data: focus categories or a series the data no longer has are
    dropped (with a warning), and with nothing left in focus the emphasis goes."""
    from ...notices import warn

    spec = recipe.get("emphasis")
    if not isinstance(spec, dict):
        return
    categories, names = recipe.get("categories") or [], [s.get("name") for s in recipe.get("series") or []]
    lost = [c for c in spec.get("focus", []) if c not in categories]
    if lost:
        spec["focus"] = [c for c in spec["focus"] if c in categories]
        warn(project, f"{group['name']!r} no longer has {', '.join(map(repr, lost[:6]))}; its emphasis dropped "
                      f"{'it' if len(lost) == 1 else 'them'}")
    if "series" in spec and spec["series"] not in names:
        warn(project, f"{group['name']!r} no longer has the series {spec['series']!r}; its emphasis dropped it")
        del spec["series"]
    if not spec.get("focus"):
        spec.pop("focus", None)
        spec.pop("annotate", None)
    if not spec.get("focus") and ("series" not in spec or recipe.get("kind") in ("pie", "donut")):
        if lost or "series" in spec:
            warn(project, f"{group['name']!r} has nothing left in focus; its emphasis was removed")
        del recipe["emphasis"]


def set_emphasis(recipe, op):
    """Apply a ``chart-emphasis`` operation to the recipe: ``focus: []`` (without a series) removes the emphasis,
    anything else updates it, keeping the settings the operation does not name."""
    names = [s["name"] for s in recipe["series"]]
    if op.get("focus") == [] and op.get("series") is None:
        recipe.pop("emphasis", None)
        return
    spec = deepcopy(recipe.get("emphasis") or {})
    if "focus" in op:
        focus = []
        for index, name in enumerate(op["focus"]):
            name = recipe["categories"][find(recipe["categories"], name, "category", f"focus[{index}]")]
            if name not in focus:
                focus.append(name)
        spec["focus"] = focus
    if "series" in op:
        if op["series"] is None:
            spec.pop("series", None)
        else:
            spec["series"] = names[find(names, op["series"], "series", "series")]
    for key in ("mute", "opacity", "annotate"):
        if key in op:
            if op[key] in (None, ""):
                spec.pop(key, None)
            else:
                spec[key] = op[key]
    radial = recipe["kind"] in ("pie", "donut")
    require(spec.get("focus") or ("series" in spec and not radial),
            "chart-emphasis needs focus: the categories to keep in colour" + (
                " (the slices of a pie or donut)" if radial else ", or series for a whole series")
            + f". Categories: {', '.join(recipe['categories'][:40])}", field="focus", allowed=recipe["categories"][:100])
    require("annotate" not in spec or spec.get("focus"), "annotate labels the focus categories; name them in focus",
            field="annotate")
    recipe["emphasis"] = spec


def check_emphasis(recipe):
    """Validate a stored emphasis (also when a document is loaded)."""
    spec = recipe["emphasis"]
    require(isinstance(spec, dict) and set(spec) <= set(EMPHASIS_KEYS), "Invalid chart emphasis", field="emphasis")
    focus = spec.get("focus", [])
    require(isinstance(focus, list) and all(c in recipe["categories"] for c in focus),
            "emphasis focus must list categories of the chart", field="focus", allowed=recipe["categories"][:100])
    names = [s["name"] for s in recipe["series"]]
    require("series" not in spec or spec["series"] in names, "emphasis series must be a series of the chart",
            field="series", allowed=names)
    require(focus or "series" in spec, "A chart emphasis needs focus categories or a series", field="focus")
    require(spec.get("mute", "fade") in MUTES, f"mute must be one of {', '.join(MUTES)}", field="mute", allowed=list(MUTES))
    if "opacity" in spec:
        finite(spec["opacity"], "opacity", 0, 1)
    require("annotate" not in spec or (isinstance(spec["annotate"], str) and 0 < len(spec["annotate"]) <= 500 and focus),
            "annotate must be text of at most 500 characters for the focus categories", field="annotate")


def emphasis_findings(checks, resolved, issue):
    """The ``color_vision`` findings of emphasised charts: a focus colour that the muted marks cannot be told from
    (to typical vision, or with a colour-vision deficiency), and muted marks that vanish into the chart's
    background. ``layer-intent color_vision_safe`` on the chart accepts it."""
    if "color_vision" not in checks:
        return
    from PIL import Image

    from ... import colors
    from ...render import color

    def lab(rgb):
        return colors.srgb_to_oklab(unit(rgb))

    def seen(rgb, kind):
        return colors.simulate_vision(Image.new("RGB", (1, 1), tuple(rgb)), kind).convert("RGB").getpixel((0, 0))

    for group in resolved.values():
        recipe = group.get("chart") if group["type"] == "group" else None
        found = (recipe or {}).get("summary", {}).get("emphasis")
        if not found or group.get("color_vision_safe"):
            continue
        focus = [color(c)[:3] for c in found.get("focus_colors", [])]
        muted = [color(c)[:3] for c in found.get("muted_colors", [])]
        surface = color(found.get("surface", "#ffffff"))[:3]
        worst = None
        for kind in (None, "protanopia", "deuteranopia", "tritanopia"):
            for a in focus:
                for b in muted:
                    gap = math.dist(lab(seen(a, kind) if kind else a), lab(seen(b, kind) if kind else b))
                    if gap < 0.07 and (worst is None or gap < worst[0]):
                        worst = (gap, kind)
        if worst:
            issue("color_vision", "warning",
                  f"{group['name']!r} emphasis: the marks in focus and the muted ones look alike"
                  + (f" with {worst[1]}" if worst[1] else "") + "; lower chart-emphasis opacity, use mute "
                  "desaturate, or give the focus series a stronger color", [group], code="emphasis-indistinct",
                  **({"vision": worst[1]} if worst[1] else {}), distance=round(worst[0], 3))
        faint = [b for b in muted if contrast(None, b, surface) < 1.15]
        if faint:
            issue("color_vision", "warning",
                  f"{group['name']!r} emphasis: the muted marks nearly vanish into the background; raise "
                  "chart-emphasis opacity or use mute desaturate", [group], code="emphasis-faint",
                  contrast=round(min(contrast(None, b, surface) for b in faint), 2))


def plain(layer):
    """True for a layer that draws what is inside it unchanged (no scaling, rotation, fading, effects)."""
    return not (layer.get("rotation", 0) % 360 or layer.get("flip_x") or layer.get("flip_y") or layer["opacity"] != 1
                or layer["blend"] != "normal" or layer["mask"] or layer.get("clip") or layer.get("styles")
                or layer.get("repeat") or any(e.get("enabled", True) for e in layer["effects"])
                or (layer["width"], layer["height"]) != (layer.get("content_width", layer["width"]),
                                                          layer.get("content_height", layer["height"])))


def chart_contrast(project, resolved, local_bounds, bounds, items):
    """Contrast of the text inside chart groups, ``{id: result}`` as ``measure(target=...)`` reports it.

    Measuring a grouped label renders the whole document twice, which for a chart's dozens of labels takes
    minutes. A chart's labels never overlap each other, so one render without them is every label's
    backdrop and one render with them is every label's result: two renders per chart. Labels that are
    restyled, or in a group that is scaled, rotated, faded or masked, are left to the general measurement."""
    from ...measure import target_contrast
    from ...render import layer_image

    plans = {}
    for item in items:
        group = resolved.get(item.get("parent"))
        if group is None or not ("chart" in group or "table" in group) or item.get("styles") or item["effects"]:
            continue
        chain, ok = group, True
        while chain is not None and ok:
            ok, chain = plain(chain), resolved.get(chain.get("parent"))
        if ok:
            plans.setdefault(group["id"], []).append(item)
    results = {}
    for ident, labels in plans.items():
        probe = project.clone()
        branch = probe.layer(ident)
        while branch:  # what is stacked above the chart is not part of its backdrop
            position = probe.state["layers"].index(branch)
            for other in probe.state["layers"][position + 1:]:
                if other.get("parent") == branch.get("parent"):
                    other["visible"] = False
            branch = probe.layer(branch["parent"]) if branch.get("parent") else None
        wanted = {item["id"] for item in labels}
        hide = [layer for layer in probe.state["layers"] if layer["id"] in wanted]
        for layer in hide:
            layer["visible"] = False
        backdrop = probe.render()
        for layer in hide:
            layer["visible"] = True
        shown = probe.render()
        for item in labels:
            x, y, w, h = bounds[item["id"]]
            if w < 1 or h < 1 or x < 0 or y < 0 or x + w > backdrop.width or y + h > backdrop.height:
                continue
            try:
                coverage = layer_image(probe, item, local_bounds[item["id"]]).getchannel("A")
                if coverage.size != (w, h) or not coverage.getbbox():
                    continue
                results[item["id"]] = target_contrast(item, shown.crop((x, y, x + w, y + h)),
                                                      backdrop.crop((x, y, x + w, y + h)), coverage, origin=(x, y))
            except VixlError:
                continue
    return results


def series_colors(project, resolved):
    """``[(chart group, [(series name, RGB, [mark layers])])]``: the fill (stroke for lines) each series of
    every chart is drawn in, read from the chart's generated marks, so checks can compare series colors."""
    import re

    from ...design import resolve_color
    from ...render import color

    found = []
    for group in resolved.values():
        recipe = group.get("chart")
        if not recipe or group["type"] != "group":
            continue
        radial = recipe.get("kind") in ("pie", "donut")
        names = recipe.get("categories", []) if radial else [s.get("name") for s in recipe.get("series", [])]
        series = {}
        for layer in resolved.values():
            match = re.fullmatch(r"(bar|area|line|slice)-(\d+)(?:-\d+)?", layer.get("chart_part", ""))
            if layer.get("parent") != group["id"] or not match or not layer["visible"]:
                continue
            value = layer.get("stroke") if match[1] == "line" else layer.get("fill")
            rgba = color(resolve_color(value, project.state)) if value else (0, 0, 0, 0)
            if rgba[3] < 128:
                continue
            index = int(match[2])
            own = (recipe.get("summary") or {}).get("colors") or []
            if recipe.get("emphasis") and index < len(own):
                # Muted marks are drawn in a muted form of the series colour; the series is still its own colour.
                rgba = color(resolve_color(own[index], project.state))
            entry = series.setdefault(index, [names[index] if index < len(names) else f"series {index + 1}", rgba[:3], []])
            entry[2].append(layer)
        found.append((group, [tuple(series[i]) for i in sorted(series)]))
    return found


def merge_options(recipe, op):
    for key in OPTIONS:
        if key not in op:
            continue
        value = op[key]
        if key == "kind" or value not in (None, ""):
            recipe[key] = deepcopy(value)
        else:
            recipe.pop(key, None)
    if recipe.get("legend") is True:
        recipe["legend"] = "auto"
    elif recipe.get("legend") is False:
        recipe["legend"] = "none"


def default_box(project, op):
    """``(x, y, width, height)`` of a new chart: the explicit fields, and for the rest the canvas safe area inset
    by one spacing step (two units, about one body size), so a chart placed without coordinates passes the
    safe-area check. Without a safe area that is the whole canvas, as before."""
    from ...craft import body_size, space
    from ...sizes import safe_sides

    canvas = project.state["canvas"]
    W, H = canvas["width"], canvas["height"]
    sides = safe_sides(canvas)
    if not any(sides):
        return op.get("x", 0), op.get("y", 0), op.get("width", W), op.get("height", H)
    bleed = canvas.get("bleed", 0)
    left, top, right, bottom = (bleed + side for side in sides)
    pad = space(2, body_size(project))
    x = op.get("x", left + pad)
    y = op.get("y", top + pad)
    width = op.get("width", max(1, round(W - right - pad - (x if isinstance(x, (int, float)) else left + pad))))
    height = op.get("height", max(1, round(H - bottom - pad - (y if isinstance(y, (int, float)) else top + pad))))
    return x, y, width, height


def execute(project, op):
    from ...operations import append_layer, default_name

    if op["type"] == "chart-emphasis":
        group = project.layer(op.get("target"))
        require(group["type"] == "group" and "chart" in group, f"{group['name']!r} is not a chart; chart-emphasis "
                "works on bar, line, area, pie and donut charts made by chart", field="target")
        recipe = deepcopy(group["chart"])
        set_emphasis(recipe, op)
        return redraw(project, group, recipe)
    if op["type"] == "chart-data":
        group = project.layer(op.get("target"))
        require(group["type"] == "group" and "chart" in group, f"{group['name']!r} is not a chart; target a chart group",
                field="target")
        recipe = deepcopy(group["chart"])
        edit_data(project, op, recipe)
        return redraw(project, group, recipe)
    target = project.layer(op["target"]) if op.get("target") else None
    if target is not None:
        require(target["type"] == "group" and "chart" in target, f"{target['name']!r} is not a chart; target a chart group "
                "or omit target to draw a new one", field="target")
    recipe = deepcopy(target["chart"]) if target else {"kind": "bar"}
    merge_options(recipe, op)
    pinned = [s["name"] for s in recipe.get("series", []) if s.get("color")] if op.get("colors") else []
    if pinned and not (op.get("series") or op.get("rows") or op.get("csv")):
        from ...notices import warn

        warn(project, f"colors does not recolour series {', '.join(map(repr, pinned[:6]))}: each stores its own "
                      "color, which wins; resend series with new colors, or without color to take colors")
    if not read_data(project, op, recipe):
        require(target is not None, "A chart needs data: categories + series, table, csv or a dataset name", field="categories")
    if target is not None:
        if "name" in op and op["name"] != target["name"]:
            from ...operations import unique_name

            target["name"] = unique_name(project, op["name"])
        for axis in ("x", "y"):
            if axis in op:
                target[axis], target["constraints"] = op[axis], {}
        size = None
        if "width" in op or "height" in op:
            size = (op.get("width", target["content_width"]), op.get("height", target["content_height"]))
            project.limits.size(*size)
        return redraw(project, target, recipe, size)
    x, y, width, height = default_box(project, op)
    project.limits.size(width, height)
    group = new_layer(op["name"] if "name" in op else default_name(project, "chart"), "group", width, height,
                      x=x, y=y, content_width=width, content_height=height)
    append_layer(project, group)
    redraw(project, group, recipe, (width, height))


def check_color(state, value, field):
    from ...design import resolve_color
    from ...render import color

    require(isinstance(value, str) and value, f"{field} must be a color", field=field)
    color(resolve_color(value, state))


def check_options(state, recipe):
    """Validate a chart recipe's options and data (also run when a document is loaded)."""
    require(recipe.get("kind") in KINDS, f"kind must be one of {', '.join(KINDS)}; got {recipe.get('kind')!r}",
            field="kind", allowed=list(KINDS))
    clean_table(recipe.get("categories"), recipe.get("series"))
    for key in ("title", "subtitle", "value_title", "category_title", "center_text"):
        require(key not in recipe or (isinstance(recipe[key], str) and len(recipe[key]) <= 500),
                f"{key} must be text of at most 500 characters", field=key)
    for key in ("text_color", "grid_color", "axis_color", "background"):
        if key in recipe:
            check_color(state, recipe[key], key)
    if "colors" in recipe:
        require(isinstance(recipe["colors"], list) and len(recipe["colors"]) <= 64, "colors must list up to 64 colors",
                field="colors")
        for color in recipe["colors"]:
            check_color(state, color, "colors")
    for s in recipe["series"]:
        if "color" in s:
            check_color(state, s["color"], "series.color")
    require(recipe.get("legend", "auto") in LEGENDS, f"legend must be one of {', '.join(LEGENDS)}", field="legend",
            allowed=list(LEGENDS))
    require(recipe.get("value_labels", "auto") in (True, False, *LABEL_MODES),
            f"value_labels must be true, false or one of {', '.join(LABEL_MODES)}", field="value_labels")
    for key in ("legend_values", "total_labels", "gridlines", "markers"):
        require(key not in recipe or isinstance(recipe[key], bool), f"{key} must be true or false", field=key)
    for key, low, high in (("min", -1e15, 1e15), ("max", -1e15, 1e15), ("font_size", 6, 300), ("bar_gap", 0, 0.9),
                           ("line_width", 0.5, 50), ("hole", 0.2, 0.9), ("start_angle", -360, 360), ("padding", 0, 500)):
        if key in recipe:
            finite(recipe[key], key, low, high)
    require("min" not in recipe or "max" not in recipe or recipe["min"] < recipe["max"], "min must be less than max",
            field="max")
    require("ticks" not in recipe or (type(recipe["ticks"]) is int and 2 <= recipe["ticks"] <= 20),
            "ticks must be a whole number from 2 to 20", field="ticks")
    if "number_format" in recipe:
        parse_format(recipe["number_format"])
    allowed = ["heading", "body", *BUNDLED_FONTS[:2], *state.get("fonts", {})]
    for key in ("title_font", "label_font"):
        require(recipe.get(key, "body") in allowed, f"{key} must be a registered font or the heading or body role; "
                f"available: {', '.join(allowed)}", field=key, allowed=allowed)
    if recipe["kind"] in ("pie", "donut"):
        require(len(recipe["series"]) == 1, "Pie and donut charts take one series; the categories are the slices",
                field="series")
    require("center_text" not in recipe or recipe["kind"] == "donut", "center_text is for donut charts", field="center_text")
    if "emphasis" in recipe:
        check_emphasis(recipe)


def validate_chart(layer, state):
    """A loaded chart group: a group carrying a well-formed recipe (a rasterized chart keeps its recipe inertly)."""
    if layer["type"] != "group":
        return
    require(isinstance(layer["chart"], dict) and len(json.dumps(layer["chart"])) <= 4_000_000, "Invalid chart recipe",
            "invalid_project")
    check_options(state, layer["chart"])
    summary = layer["chart"].get("summary", {})
    colors, scale = summary.get("colors", []), summary.get("scale", {})
    require(isinstance(summary, dict) and isinstance(colors, list) and len(colors) <= 400
            and all(isinstance(c, str) for c in colors) and summary.get("legend") in (None, "top", "bottom", "left", "right")
            and isinstance(scale, dict) and all(isinstance(scale.get(k, 0), (int, float)) for k in ("min", "max", "step")),
            "Invalid chart summary", "invalid_project")
    marked = summary.get("emphasis", {})
    require(isinstance(marked, dict) and all(
        isinstance(marked.get(key, []), list) and len(marked[key]) <= 64 and all(isinstance(c, str) for c in marked[key])
        for key in ("focus_colors", "muted_colors") if key in marked) and isinstance(marked.get("surface", ""), str),
        "Invalid chart summary", "invalid_project")
    for value in [*marked.get("focus_colors", []), *marked.get("muted_colors", []), *([marked["surface"]] if "surface" in marked else [])]:
        check_color(state, value, "summary.emphasis")
    for key in ("label_format", "percent_format"):
        if key in summary:
            parse_format(summary[key])
    if "format" in scale:
        parse_format(scale["format"])


def schemas(add):
    from ...schema import COORD, SIZE
    from .datasets import binding_schema

    S, B, N = {"type": "string"}, {"type": "boolean"}, {"type": "number"}
    cell = {"type": ["number", "null"]}

    def d(schema, text):
        return {**schema, "description": text}

    def nullable(schema):
        schema = deepcopy(schema)
        if "anyOf" in schema:
            schema["anyOf"].append({"type": "null"})
        else:
            schema["type"] = [schema["type"], "null"] if isinstance(schema["type"], str) else [*schema["type"], "null"]
            if "enum" in schema:
                schema["enum"] = [*schema["enum"], None]
        return schema

    series = {"type": "object", "properties": {"name": d(S, "Series name (legend entry)."),
                                               "values": d({"type": "array", "items": cell, "maxItems": MAX_CATEGORIES},
                                                           "One number per category; null leaves a gap."),
                                               "color": d(S, "Fill color; defaults come from the palette.")},
              "required": ["name", "values"], "additionalProperties": False}
    data = {
        **binding_schema(),
        "categories": d({"type": "array", "items": {"type": ["string", "number"]}, "minItems": 1, "maxItems": MAX_CATEGORIES},
                        "Category labels (x axis, or the slices of a pie), unique."),
        "series": d({"type": "array", "items": series, "minItems": 1, "maxItems": MAX_SERIES},
                    "Named value lists, one value per category. Pie and donut take one series."),
        "table": d({"type": "array", "items": {"type": "array", "items": {"type": ["string", "number", "null"]}},
                    "minItems": 2, "maxItems": MAX_CATEGORIES + 1},
                   "Rows instead of categories/series: a header row (first cell ignored, then series names), then "
                   "[category, value, …] per row."),
        "csv": d(S, "Workspace-relative CSV: first column (or category_column) = categories, the other columns "
                    "(or series_columns) = series. chart-data reload re-reads it."),
        "category_column": d(S, "CSV column holding the categories (default: the first)."),
        "series_columns": d({"type": "array", "items": S, "minItems": 1, "maxItems": MAX_SERIES},
                            "CSV columns to plot (default: all others)."),
    }
    options = {
        "kind": d({"enum": list(KINDS)}, "bar (default), stacked-bar, percent-bar (100 %), horizontal-bar, "
                  "stacked-horizontal-bar, percent-horizontal-bar, line, area, stacked-area, pie, donut."),
        "title": d(S, "Chart title (heading font)."),
        "subtitle": d(S, "Line under the title."),
        "colors": d({"type": "array", "items": S, "maxItems": 64},
                    "Series (pie: slice) colors, any color or @swatch; default: the document palette, then a color-blind-safe set."),
        "legend": d({"anyOf": [B, {"enum": list(LEGENDS)}]}, "auto (default: shown for 2+ series or any pie), none, "
                    "top, bottom, left or right."),
        "legend_values": d(B, "Draw the legend as an aligned key-value list: swatch, name and total (pie and donut: also the share)."),
        "value_labels": d({"anyOf": [B, {"enum": list(LABEL_MODES)}]},
                          "auto (default: label what fits), true (label everything), false/none, or for pie/donut "
                          "value, percent or both."),
        "total_labels": d(B, "Stacked charts: show each stack's total."),
        "gridlines": d(B, "Gridlines at each value tick (default true)."),
        "number_format": d(S, "Excel-style format for ticks and labels, such as '#,##0', '0.0', '0%', '$#,##0.00' or "
                              "'#,##0,\"K\"'; also used in the PPTX chart."),
        "min": d(N, "Value-axis minimum (default 0 or the data's minimum)."),
        "max": d(N, "Value-axis maximum (default: a round number above the data)."),
        "ticks": d({"type": "integer", "minimum": 2, "maximum": 20}, "About this many value-axis intervals (default 5)."),
        "value_title": d(S, "Value-axis title."),
        "category_title": d(S, "Category-axis title."),
        "font_size": d(N, "Label size in pixels (default: scaled to the chart); the title is 1.5×."),
        "title_font": d(S, "Registered font name or the heading/body role for the title (default heading)."),
        "label_font": d(S, "Registered font name or the heading/body role for all other text (default body)."),
        "text_color": d(S, "Text color (default: the @ink swatch, else dark or light to suit the background)."),
        "grid_color": d(S, "Gridline color."),
        "axis_color": d(S, "Axis rule color."),
        "background": d(S, "Fill behind the chart (default: none; the canvas shows through)."),
        "bar_gap": d(N, "Bars: gap between categories as a fraction of the band, 0–0.9 (default 0.3)."),
        "line_width": d(N, "Line charts: stroke width in pixels."),
        "markers": d(B, "Line charts: dots at each point (default: on up to 60 points)."),
        "hole": d(N, "Donut: hole size as a fraction of the radius, 0.2–0.9 (default 0.55)."),
        "start_angle": d(N, "Pie/donut: where the first slice starts, in degrees clockwise from 12 o'clock."),
        "center_text": d(S, "Donut: text in the hole; {total} becomes the sum."),
        "padding": d(N, "Space between the chart's edge and its content in pixels."),
    }
    frame = {"target": d(S, "Existing chart group to restyle, resize or give new data; omit to draw a new chart."),
             "name": d(S, "Group name; the layers inside are named NAME/part."), "x": COORD, "y": COORD,
             "width": d(SIZE, "Chart width (default: the canvas safe area, inset two spacing units)."),
             "height": d(SIZE, "Chart height (default: the canvas safe area, inset two spacing units).")}
    add("chart", {**frame, **data, **{k: (v if k == "kind" else nullable(v)) for k, v in options.items()}},
        description="Draw a data-bound chart (bars, lines, areas, pie, donut) as vector layers, or restyle one with target.")
    add("chart-data", {
        "target": d(S, "Chart group ID or name (default: the active layer)."),
        "set": d({"type": "array", "items": {"type": "object", "properties": {
            "category": d({"type": ["string", "number"]}, "Category label."),
            "series": d(S, "Series name (optional on one-series charts)."),
            "value": d(cell, "New value; null clears it.")}, "required": ["category", "value"],
            "additionalProperties": False}, "minItems": 1, "maxItems": 1000}, "Cell edits, e.g. fix one month."),
        "append": d({"type": "array", "items": {"type": "object", "properties": {
            "category": d({"type": ["string", "number"]}, "New category label."),
            "values": d({"anyOf": [{"type": "array", "items": cell}, {"type": "object", "additionalProperties": cell}]},
                        "One value per series, or {series: value}.")}, "required": ["category", "values"],
            "additionalProperties": False}, "minItems": 1, "maxItems": MAX_CATEGORIES}, "New categories (rows) at the end."),
        "remove_categories": d({"type": "array", "items": {"type": ["string", "number"]}, "minItems": 1}, "Categories to drop."),
        "add_series": d({"type": "array", "items": series, "minItems": 1}, "Series to add."),
        "remove_series": d({"type": "array", "items": S, "minItems": 1}, "Series to drop."),
        "reload": d(B, "Re-read the CSV the chart is bound to."),
        **data,
    }, description="Edit a chart's data in place: cell edits, new or removed categories and series, a CSV "
                               "reload, or a new table. The chart redraws with the same layer IDs and reports its totals under chart.summary.")


    add("chart-emphasis", {
        "target": d(S, "Chart group ID or name (default: the active layer)."),
        "focus": d({"type": "array", "items": {"type": ["string", "number"]}, "maxItems": MAX_CATEGORIES, "uniqueItems": True},
                   "Categories to keep in colour (the slices of a pie or donut); every other mark is muted. [] "
                   "removes the emphasis and restores the chart."),
        "series": d({"type": ["string", "null"]}, "Limit the focus to one series: with focus, that series' marks in "
                    "those categories; alone, the whole series (a line among lines). null removes the limit."),
        "mute": d({"enum": [*MUTES, None]}, "How the rest is drawn: fade (default: toward the chart "
                  "background) or desaturate (a grey of the same lightness)."),
        "opacity": d({"type": ["number", "null"], "minimum": 0, "maximum": 1},
                     f"fade: how much of a muted mark's colour stays, 0-1 (default {MUTE_OPACITY}); '35%' is read as 0.35."),
        "annotate": d({"type": ["string", "null"], "maxLength": 500},
                      "Callout set beside each focus mark, in place of its value label. ${value}, ${percent} (share "
                      "of the chart's total), ${category} and ${series} are filled in from the data; with several "
                      "series and no series named, ${value} is the category's total. null removes it."),
    }, description="Make chosen categories of a chart stand out: they keep their colours, the rest is muted, and an "
                   "optional callout labels them. Stored with the chart, so chart-data edits keep it; focus: [] "
                   "restores the chart.")


def compile_command(cmd, args):
    if cmd not in TYPES:
        return None
    from ...commands import Parser, number_or_center

    if cmd == "chart-emphasis":
        p = Parser(prog="vixl chart-emphasis", description="Highlight chosen categories of a chart, mute the rest, "
                                                           "add a callout; vixl schema lists every field.")
        p.add_argument("focus", nargs="*", help="categories to keep in colour")
        p.add_argument("--target")
        p.add_argument("--series", help="limit the focus to one series")
        p.add_argument("--mute", choices=list(MUTES))
        p.add_argument("--opacity", type=float, help="fade: how much of a muted mark's colour stays, 0-1")
        p.add_argument("--annotate", help="callout text; ${value}, ${percent}, ${category}, ${series}")
        p.add_argument("--clear", action="store_true", help="remove the emphasis")
        a = vars(p.parse_args(args))
        clear = a.pop("clear")
        require(not (clear and a["focus"]), "Give categories or --clear, not both", "usage_error")
        op = {"type": cmd, **{key: value for key, value in a.items() if value not in (None, [])}}
        if clear:
            op["focus"] = []
        return op

    p = Parser(prog=f"vixl {cmd}", description="Data-bound charts; vixl schema lists every field.")
    op = {"type": cmd}
    p.add_argument("--data", help="named shared dataset")
    p.add_argument("--derive", type=json.loads, help='JSON {"kind":"sum|share|max","by":"series|category"}')
    if cmd == "chart":
        p.add_argument("kind", nargs="?", choices=list(KINDS))
        p.add_argument("--target")
        p.add_argument("--name")
        for key in ("x", "y"):
            p.add_argument("--" + key, type=number_or_center)
        p.add_argument("--width", type=int)
        p.add_argument("--height", type=int)
        p.add_argument("--csv", help="workspace CSV: first column categories, the others series")
        p.add_argument("--category-column")
        p.add_argument("--series-columns", help="comma-separated CSV columns to plot")
        p.add_argument("--categories", type=json.loads, help='JSON list, e.g. ["Jan","Feb"]')
        p.add_argument("--series", type=json.loads, help='JSON list of {"name", "values"}')
        p.add_argument("--table", type=json.loads, help="JSON rows: a header row, then [category, value, …]")
        for key in ("title", "subtitle", "number-format", "value-title", "category-title", "title-font", "label-font",
                    "text-color", "grid-color", "axis-color", "background", "center-text"):
            p.add_argument("--" + key)
        p.add_argument("--colors", help="comma-separated colors")
        p.add_argument("--legend", choices=list(LEGENDS))
        p.add_argument("--value-labels", choices=["auto", "true", "false", *LABEL_MODES[1:]])
        for key in ("min", "max", "font-size", "bar-gap", "line-width", "hole", "start-angle", "padding"):
            p.add_argument("--" + key, type=float)
        p.add_argument("--ticks", type=int)
        for key in ("legend-values", "total-labels"):
            p.add_argument("--" + key, action="store_true", default=None)
        p.add_argument("--no-gridlines", dest="gridlines", action="store_false", default=None)
        p.add_argument("--no-markers", dest="markers", action="store_false", default=None)
    else:
        p.add_argument("--target")
        p.add_argument("--set", action="append", metavar="CATEGORY[:SERIES]=VALUE",
                       help="set one value (blank clears it); the series may be left out on one-series charts")
        p.add_argument("--append", action="append", metavar="CATEGORY=V1,V2,…", help="add a category with one value per series")
        p.add_argument("--remove-category", action="append", dest="remove_categories")
        p.add_argument("--remove-series", action="append")
        p.add_argument("--reload", action="store_true", default=None, help="re-read the bound CSV")
        p.add_argument("--csv")
        p.add_argument("--categories", type=json.loads)
        p.add_argument("--series", type=json.loads)
        p.add_argument("--table", type=json.loads)
    a = vars(p.parse_args(args))
    for key, value in a.items():
        if value is None:
            continue
        if key == "value_labels":
            value = {"true": True, "false": False}.get(value, value)
        elif key == "colors" or key == "series_columns":
            value = [v.strip() for v in value.split(",") if v.strip()]
        elif key in ("ticks",):
            value = int(value)
        elif key == "set":
            value = [parse_set(item) for item in value]
        elif key == "append":
            value = [parse_append(item) for item in value]
        op[key] = value
    return op


def number_arg(text, field):
    if text.strip() == "":
        return None
    try:
        return int(text) if re.fullmatch(r"-?\d+", text.strip()) else float(text)
    except ValueError:
        raise VixlError("usage_error", f"{field} must be a number, got {text!r}") from None


def parse_set(item):
    require("=" in item, "Use --set CATEGORY[:SERIES]=VALUE", "usage_error")
    left, value = item.rsplit("=", 1)
    category, _, series = left.partition(":")
    return {"category": category, **({"series": series} if series else {}), "value": number_arg(value, "value")}


def parse_append(item):
    require("=" in item, "Use --append CATEGORY=V1,V2,…", "usage_error")
    category, values = item.split("=", 1)
    return {"category": category, "values": [number_arg(v, "value") for v in values.split(",")]}
