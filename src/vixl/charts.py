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

from .errors import VixlError, require
from .model import finite, new_layer

TYPES = ("chart", "chart-data")
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
# Options that restyle a chart; the data keys are handled separately.
OPTIONS = (
    "kind", "title", "subtitle", "colors", "legend", "legend_values", "value_labels", "total_labels", "gridlines",
    "number_format", "min", "max", "ticks", "value_title", "category_title", "font_size", "title_font",
    "label_font", "text_color", "grid_color", "axis_color", "background", "bar_gap", "line_width", "markers",
    "hole", "start_angle", "center_text", "padding",
)
DATA_KEYS = ("categories", "series", "table", "csv")
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


# ---------------------------------------------------------------------------------------------
# Numbers: Excel-style formats (the same string drives Vixl's labels and the PPTX chart), scales

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
            score = abs(math.ceil(span / step - 1e-9) - intervals)
            if best is None or score < best[0] or (score == best[0] and step > best[1]):
                best = (score, step)
    step = round(best[1], 12)
    if fixed_min is None:
        low = round(math.floor(low / step + 1e-9) * step, 12)
    if fixed_max is None:
        high = round(math.ceil(high / step - 1e-9) * step, 12)
    ticks = [round(low + i * step, 12) for i in range(int((high - low) / step + 1e-9) + 1)]
    require(len(ticks) <= 60, "The value axis would have too many ticks; raise ticks' spacing with min, max or ticks",
            field="ticks")
    return low, high, step, ticks


# ---------------------------------------------------------------------------------------------
# Data: tables from inline values, rows or a workspace CSV

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
    from .exports import read_csv

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


def read_data(project, op, recipe):
    """Replace ``recipe``'s table when the operation brings one (inline, rows or a CSV)."""
    given = [k for k in DATA_KEYS if k in op]
    if not given:
        return False
    require(len(given) == 1 or set(given) == {"categories", "series"},
            f"Give the data once: categories + series, a table, or a csv; got {', '.join(given)}", field=given[0])
    if "csv" in op:
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
    return True


def find(names, wanted, what, field):
    text = category_name(wanted, field) if what == "category" else wanted
    if text in names:
        return names.index(text)
    close = difflib.get_close_matches(str(text), names, 3, 0.5)
    raise VixlError("invalid_operation", f"Unknown {what} {text!r}; {what}s: {', '.join(names[:40])}"
                    + (f". Did you mean {' or '.join(map(repr, close))}?" if close else ""),
                    field=field, allowed=names[:100], suggestions=close)


def edit_data(project, op, recipe):
    """Apply a ``chart-data`` operation to the recipe's table: replace or reload, then remove, add, set."""
    changed = read_data(project, op, recipe)
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


# ---------------------------------------------------------------------------------------------
# Statistics: what the chart says in numbers (kept on the recipe so agents never recompute them)

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


# ---------------------------------------------------------------------------------------------
# Style: colors and fonts from the document

def rgba(state, value):
    from .design import resolve_color
    from .render import color

    return color(resolve_color(value, state))


def unit(rgb):
    return tuple(c / 255 for c in rgb[:3])


def contrast(state, first, second):
    """WCAG contrast ratio between two colors (color expressions or RGB tuples)."""
    from .colors import contrast_ratio

    return contrast_ratio(unit(first if isinstance(first, tuple) else rgba(state, first)),
                          unit(second if isinstance(second, tuple) else rgba(state, second)))


def mix(front, back, amount):
    """``front`` faded toward ``back`` (RGB tuples): ``amount`` 1 is all front."""
    return tuple(round(f * amount + b * (1 - amount)) for f, b in zip(front[:3], back[:3]))


def hex_color(rgb):
    return "#%02x%02x%02x" % tuple(rgb)


class Style:
    """Colors, type sizes and spacing a chart draws with, taken from the options and the document."""

    def __init__(self, project, recipe, width, height):
        state = project.state
        self.project, self.recipe = project, recipe
        # Sizes sit on the document's type scale (its character styles) when it has one.
        self.scale = sorted({float(s["size"]) for s in state.get("character_styles", {}).values() if "size" in s})
        self.fs = int(round(recipe["font_size"])) if recipe.get("font_size") else self.snap(max(10, min(40, min(width, height) / 30)))
        self.pad = int(round(recipe["padding"] if "padding" in recipe else self.fs * 0.8))
        override = recipe.get("background")
        self.surface = override or state["canvas"]["background"]
        surface = rgba(state, self.surface)
        self.bg = surface[:3] if surface[3] >= 128 else (255, 255, 255)
        from .colors import relative_luminance

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
        """One color per series (or slice): explicit colors first, then the document palette, then a
        color-blind-safe default set."""
        state = self.project.state
        pool = [c for c in (self.recipe.get("colors") or [])]
        explicit = len(pool)
        palette = (state.get("palettes") or {}).get(state.get("active_palette")) or []
        usable = [c for c in palette if contrast(state, c, self.bg) >= 1.6]
        if count == 1 and not explicit and "accent" in state.get("swatches", {}):
            pool.append("@accent")
        pool += [c for c in usable + DEFAULT_COLORS if c not in pool]
        return [pool[i % len(pool)] for i in range(count)]

    def on(self, fill):
        """Label color that reads on ``fill``: white or near-black, whichever contrasts more."""
        state = self.project.state
        return "#ffffff" if contrast(state, "#ffffff", fill) >= contrast(state, "#111827", fill) else "#111827"


class Kit:
    """Measures and builds text so labels sit where the layout says (ink-tight boxes, baselines)."""

    def __init__(self, project, recipe, style):
        from .render import resolve_font

        self.project, self.style = project, style
        self.fonts = {head: resolve_font(project, recipe.get("title_font" if head else "label_font")
                                         or ("heading" if head else "body")) for head in (True, False)}
        self._vertical = {}

    def vertical(self, layer):
        """(ascent, height above the baseline of a digit) for this font and size."""
        from .render import text_metrics
        from .text import face, primary_font_data

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

    def make(self, text, size, color, head=False, align="left"):
        from .render import text_metrics

        font, role = self.fonts[head]
        layer = {"text": text, "font": font, "size": max(1, int(round(size))), "color": color, "align": align,
                 "spacing": max(0, round(size * 0.12)), "auto_size": True}
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


# ---------------------------------------------------------------------------------------------
# Layout: shared furniture (title, legend) then the plot

def header(kit, style, recipe, parts, size):
    """Title and subtitle at the top-left; returns the y below them."""
    y = style.pad
    for key, size_, color, head in (("title", style.snap(style.fs * 1.5), style.ink, True),
                                           ("subtitle", style.snap(style.fs * 1.1), style.muted, False)):
        if recipe.get(key):
            lab = kit.make(kit.wrap(recipe[key], size_, size[0] - 2 * style.pad, 4), size_, color, head)
            place(parts, key, key, lab, style.pad, y, Z_TITLE, at="top")
            y += lab["height"] + round(style.fs * 0.4)
    return y


class Legend:
    """A row or column of swatch + label entries, measured before the plot is sized."""

    def __init__(self, kit, style, entries, position, room):
        self.position, self.style = position, style
        fs = style.fs
        self.swatch = round(fs * 0.8)
        self.row = round(fs * 1.5)
        spacing = round(fs * 1.4)
        labels = [(kit.make(text, fs, style.ink), color) for text, color in entries]
        self.entries, x, y, widest = [], 0, 0, 0
        for lab, color in labels:
            width = self.swatch + round(fs * 0.45) + lab["width"]
            if position in ("top", "bottom") and x and x + width > room:
                x, y = 0, y + self.row
            self.entries.append((x, y, lab, color))
            widest, x = max(widest, x + width), x + width + spacing
            if position in ("left", "right"):
                x, y = 0, y + self.row
        self.width = widest
        self.height = max(e[1] for e in self.entries) + self.row

    def emit(self, parts, ox, oy):
        s = self.style
        for i, (x, y, lab, color) in enumerate(self.entries):
            mid = oy + y + self.row / 2
            parts.rect(f"legend-swatch-{i}", f"legend swatch {i + 1}",
                       (round(ox + x), round(mid - self.swatch / 2), self.swatch, self.swatch), color, Z_LEGEND)
            place(parts, f"legend-label-{i}", f"legend label {i + 1}", lab, ox + x + self.swatch + round(s.fs * 0.45),
                  mid + lab["cap"] / 2, Z_LEGEND)


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
        self.shown, forced, _ = labels_mode(recipe, False)
        self.auto = self.shown and not forced
        if self.auto and self.n * self.m > AUTO_LABELS:
            self.shown = self.auto = False  # automatic labels are for charts of a readable number of values
        self.point_labels = self.shown and not (self.area and not forced)
        self.totals_shown = bool(recipe.get("total_labels")) and self.stacked and not self.percent
        self.crowd = Collider()
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
        self.draw_legend()
        self.stats.update(scale={"min": self.lo, "max": self.hi, "step": self.step, "ticks": self.ticks, "format": self.tick_format},
                          label_format=self.label_format, colors=self.colors, legend=self.position)

    # -- geometry -----------------------------------------------------------------------------

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
            entries = [(s["name"] + (f"  {format_number(totals['by_series'][s['name']], self.label_format)}"
                                     if recipe.get("legend_values") else ""), self.colors[i]) for i, s in enumerate(self.series)]
            self.legend = Legend(kit, style, entries, self.position, W - 2 * pad)
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
            if self.point_labels or self.totals_shown:
                longest = max([kit.width(format_number(v, self.label_format), fs) for row in self.zero for v in row] + [0])
                right -= 0 if self.stacked and not self.totals_shown else longest + gap
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

    def label(self, key, name, value, x, y, anchor, color, at="base", fit=None):
        """A data label; automatic labels are skipped when they do not fit their mark or would crowd another."""
        lab = self.kit.make(format_number(value, self.label_format), self.value_size, color)
        left, top = spot(lab, x, y, anchor, at)
        box = (round(left), round(top), lab["width"], lab["height"])
        if self.auto:
            if fit and ((fit[0] is not None and lab["width"] > fit[0]) or (fit[1] is not None and lab["height"] > fit[1])):
                return
            if not self.crowd.free(box) or box[0] < 0 or box[0] + box[2] > self.W or box[1] < 0 or box[1] + box[3] > self.H:
                return
        self.crowd.take(box)
        self.parts.text(key, name, lab, left, top, Z_VALUES)

    # -- drawing ------------------------------------------------------------------------------

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
                parts.rect(f"bar-{s_index}-{i}", f"bar {s['name']} {self.categories[i]}", (x, y, w, h),
                           self.colors[s_index], Z_MARKS)
                if not self.shown:
                    continue
                key, name = f"value-{s_index}-{i}", f"value {s['name']} {self.categories[i]}"
                if self.stacked:
                    self.label(key, name, v, x + w / 2, y + h / 2 + self.value_cap / 2, "center", style.on(self.colors[s_index]),
                               fit=(w - 4, h - 2))
                elif self.horizontal:
                    forward = v > 0
                    self.label(key, name, v, x + w + gap if forward else x - gap, y + h / 2 + self.value_cap / 2,
                               "left" if forward else "right", style.ink, fit=(None, h * 1.3))
                elif v > 0:
                    self.label(key, name, v, x + w / 2, y - gap, "center", style.ink, fit=(w * 1.3, None))
                else:
                    self.label(key, name, v, x + w / 2, y + h + gap + self.value_cap, "center", style.ink, fit=(w * 1.3, None))
        if not self.totals_shown:
            return
        for i, category in enumerate(self.categories):
            if not any(row[i] for row in self.zero):
                continue
            total, up = self.stats["totals"]["by_category"][category], positive[i] > 0
            end = self.vp(positive[i] if up else negative[i])
            key, name = f"total-{i}", f"total {category}"
            if self.horizontal:
                self.label(key, name, total, end + gap if up else end - gap, self.center(i) + self.value_cap / 2,
                           "left" if up else "right", style.ink)
            elif up:
                self.label(key, name, total, self.center(i), end - gap, "center", style.ink)
            else:
                self.label(key, name, total, self.center(i), end + gap + self.value_cap, "center", style.ink)

    def draw_lines(self):
        parts, style, gap, n = self.parts, self.style, self.gap, self.n
        width = self.recipe.get("line_width") or (max(2, round(style.fs * 0.18)) if n <= 60 else 1.5)
        dots = self.recipe.get("markers", n * self.m <= 60) and not self.area
        dot = max(6, round(width * 2.4))
        below = [0] * n
        for s_index, s in enumerate(self.series):
            color, name = self.colors[s_index], s["name"]
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
                points = [(self.center(i), self.vp(v)) if v is not None else None for i, v in enumerate(s["values"])]
            for i, point in enumerate(points):
                if point is None:
                    continue
                x, y = point
                if dots:
                    parts.add(f"marker-{s_index}-{i}", f"marker {name} {self.categories[i]}", "ellipse", Z_MARKERS,
                              x=round(x - dot / 2), y=round(y - dot / 2), width=dot, height=dot, fill=color)
                if self.point_labels and s["values"][i] is not None:
                    value, reach = s["values"][i], (dot if dots else width) / 2 + gap
                    key, label = f"value-{s_index}-{i}", f"value {name} {self.categories[i]}"
                    if value >= 0:
                        self.label(key, label, value, x, y - reach, "center", style.ink)
                    else:
                        self.label(key, label, value, x, y + reach + self.value_cap, "center", style.ink)

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
    shown, _, content = labels_mode(recipe, True)
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
        names = [(c + (f"  {format_number(values[i], label_format)}" if recipe.get("legend_values") else ""), colors[i])
                 for i, c in enumerate(categories)]
        legend = Legend(kit, style, names, position, W - 2 * pad)
        if position == "top":
            legend_y, top = top, top + legend.height + gap
        elif position == "bottom":
            bottom -= legend.height + gap
        elif position == "left":
            left += legend.width + gap * 2
        else:
            right -= legend.width + gap * 2
    labels = {i: kit.make(slice_text(i), fs, style.ink) for i in range(len(categories)) if shown and shares[i] > 0}
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
                  path_view=[w, h], fill=colors[i], stroke=style.separator, stroke_width=outline, line_cap="round")
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
            place(parts, f"slice-label-{i}", f"slice label {categories[i]}", lab, x, y, Z_VALUES, "center", "mid")
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


# ---------------------------------------------------------------------------------------------
# Keeping the group in step with its recipe

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


def sync(project, group, parts):
    """Make the group's generated children match ``parts``: update layers in place (same IDs), add the
    missing ones, drop the ones the chart no longer draws, and order them as the layout stacks them."""
    layers = project.state["layers"]
    wanted = parts.ordered()
    by_key = {p["key"]: p for p in wanted}
    mine = {x["chart_part"]: x for x in layers if x.get("parent") == group["id"] and "chart_part" in x}
    stale = [x for key, x in mine.items() if key not in by_key or part_kind(x) != by_key[key]["kind"]]
    reuse = {key: x for key, x in mine.items() if x not in stale}
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
        from .timeline import prune_targets

        prune_targets(project.state, removed)
    kept = []
    for part in wanted:
        fields, layer = part["fields"], reuse.get(part["key"])
        if layer is None:
            project.limits.size(fields["width"], fields["height"])
            layer = new_layer(child_name(project, group, part["label"]), "text" if part["kind"] == "text" else "shape",
                              fields["width"], fields["height"], parent=group["id"], chart_part=part["key"])
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
        if part["kind"] == "text" and "font_role" not in fields:
            layer.pop("font_role", None)
        kept.append(layer)
    ids = {x["id"] for x in kept}
    foreign = [x for x in layers if x.get("parent") == group["id"] and x["id"] not in ids]
    rest = [x for x in layers if x["id"] not in ids and x not in foreign]
    at = rest.index(group)
    layers[:] = rest[:at] + kept + foreign + rest[at:]
    return len(kept)


def redraw(project, group, recipe, size=None):
    """Lay the recipe out again into ``group`` (resized to ``size`` when given) and record the statistics."""
    width, height = size or (group["content_width"], group["content_height"])
    check_options(project.state, recipe)
    parts, stats = layout(project, recipe, (width, height))
    stats["layers"] = sync(project, group, parts)
    recipe["summary"] = stats
    group["chart"] = recipe
    group["content_width"], group["content_height"] = width, height
    if size:
        group["width"], group["height"] = width, height
    project.state["active_layer"] = group["id"]


# ---------------------------------------------------------------------------------------------
# Checks

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
    from .measure import target_contrast
    from .render import layer_image

    plans = {}
    for item in items:
        group = resolved.get(item.get("parent"))
        if group is None or "chart" not in group or item.get("styles") or item["effects"]:
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


# ---------------------------------------------------------------------------------------------
# Operations

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


def execute(project, op):
    from .operations import append_layer, default_name

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
    if not read_data(project, op, recipe):
        require(target is not None, "A chart needs data: categories + series, a table, or a csv", field="categories")
    if target is not None:
        if "name" in op and op["name"] != target["name"]:
            from .operations import unique_name

            target["name"] = unique_name(project, op["name"])
        for axis in ("x", "y"):
            if axis in op:
                target[axis], target["constraints"] = op[axis], {}
        size = None
        if "width" in op or "height" in op:
            size = (op.get("width", target["content_width"]), op.get("height", target["content_height"]))
            project.limits.size(*size)
        return redraw(project, target, recipe, size)
    canvas = project.state["canvas"]
    width, height = op.get("width", canvas["width"]), op.get("height", canvas["height"])
    project.limits.size(width, height)
    group = new_layer(op["name"] if "name" in op else default_name(project, "chart"), "group", width, height,
                      x=op.get("x", 0), y=op.get("y", 0), content_width=width, content_height=height)
    append_layer(project, group)
    redraw(project, group, recipe, (width, height))


def check_color(state, value, field):
    from .design import resolve_color
    from .render import color

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
    allowed = ["heading", "body", "DejaVuSans.ttf", *state.get("fonts", {})]
    for key in ("title_font", "label_font"):
        require(recipe.get(key, "body") in allowed, f"{key} must be a registered font or the heading or body role; "
                f"available: {', '.join(allowed)}", field=key, allowed=allowed)
    if recipe["kind"] in ("pie", "donut"):
        require(len(recipe["series"]) == 1, "Pie and donut charts take one series; the categories are the slices",
                field="series")
    require("center_text" not in recipe or recipe["kind"] == "donut", "center_text is for donut charts", field="center_text")


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
    for key in ("label_format", "percent_format"):
        if key in summary:
            parse_format(summary[key])
    if "format" in scale:
        parse_format(scale["format"])


def schemas(add):
    from .schema import COORD, SIZE

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
        "legend_values": d(B, "Add each series' (pie: slice's) total to its legend entry."),
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
             "width": d(SIZE, "Chart width (default: the canvas)."), "height": d(SIZE, "Chart height (default: the canvas).")}
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


# ---------------------------------------------------------------------------------------------
# Human command syntax

def compile_command(cmd, args):
    if cmd not in TYPES:
        return None
    from .commands import Parser, number_or_center

    p = Parser(prog=f"vixl {cmd}", description="Data-bound charts; vixl schema lists every field.")
    op = {"type": cmd}
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
