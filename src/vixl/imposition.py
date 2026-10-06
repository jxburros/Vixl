"""Data merge into print imposition: n-up sheets from a template document and a CSV.

``merge-impose`` takes a template (a .vixl document with ``${variables}``), a CSV (one row per copy)
and a sheet spec (page size, grid, gutters, margins, bleed, crop marks, registration marks, slug
text) and lays the merged copies out on print sheets. The result is a multi-page print PDF whose text
is real, selectable vector text, and/or an editable *sheet document*: a .vixl with one page per
sheet, where every cell is a ``link`` layer (see links.py) to the template with its CSV row as the
link's variables. Because the cells are live links, the sheet follows later edits to the template;
re-running the merge (``rerun``) follows later edits to the data.

Every row is validated before anything is written: variables the template needs but the row lacks,
CSV columns the template never uses (with a did-you-mean), text that overflows its box, characters no
font can draw, and image files that are missing. An empty cell is an empty value, not a missing one.
Messages name rows and columns, never cell values.
"""

import difflib
import math
from pathlib import Path
import re

from .errors import VixlError, require
from .model import finite, new_layer, uid

ACTIONS = {"merge-impose": ({"template", "data", "rows", "sheet", "output", "sheet_document", "variables", "page", "artboard",
                             "unknown", "defaults", "skip_invalid", "dry_run", "check", "copies", "replace", "rerun"}, set())}

SHEET_KEYS = ("size", "width", "height", "unit", "orientation", "dpi", "cols", "rows", "gutter", "margin", "bleed",
              "crop_marks", "registration", "slug", "order", "align", "background")
MARK_KEYS = ("length", "offset", "weight")
UNITS = ("in", "mm", "cm", "pt")
MAX_ITEMS = 5000
MAX_PAGES = 500
NAME = re.compile(r"[\w-]+")
BUILTINS = ("page", "pages", "page_name")
SCANNED = ("layers", "swatches", "character_styles", "paragraph_styles", "canvas")
CROP_LENGTH_PT, CROP_GAP_PT, CROP_WEIGHT_PT = 9.0, 4.5, 0.25
REGISTRATION_RADIUS_PT = 3.0
SLUG_PT = 6.0
SLUG_FIELDS = ("template", "page", "pages", "first", "last", "count", "rows")

PATH = {"type": "string", "description": "Workspace-relative path."}
FIELD_TYPES = {
    "template": {**PATH, "description": "The template .vixl (default: the open document)."},
    "data": {**PATH, "description": "A CSV with a column per template variable and a row per copy. Give data or rows."},
    "rows": {"type": "array", "items": {"type": "object"}, "description": "Inline rows instead of a CSV: a list of "
             "{variable: value} objects."},
    "sheet": {"type": "object", "description": "The sheet spec: size (a named paper size) or width/height/unit, "
              "orientation, dpi, cols/rows (default: as many as fit), gutter, margin, bleed, crop_marks, "
              "registration, slug, order, align, background. Lengths are in the sheet's unit (inches for "
              "letter, millimetres for a4)."},
    "output": {**PATH, "description": "The print PDF (.pdf) or, with a .vixl path, the editable sheet document."},
    "sheet_document": {**PATH, "description": "Also write the editable sheet document (.vixl): one page per "
                       "sheet, one live link per copy."},
    "variables": {"type": "object", "description": "Values for every copy; a CSV column overrides them."},
    "page": {"type": ["string", "integer"], "description": "The template's page (default: its active page)."},
    "artboard": {"type": "string", "description": "The template's artboard (default: its whole canvas)."},
    "unknown": {"type": "string", "enum": ["warn", "error", "ignore"], "default": "warn",
                "description": "What to do with CSV columns the template does not use."},
    "defaults": {"type": "string", "enum": ["error", "warn", "ignore"], "default": "error",
                 "description": "What to do with a template variable the data has no column for (every copy would print "
                 "the template's own sample value). Constants belong in variables."},
    "skip_invalid": {"type": "boolean", "default": False, "description": "Leave out rows that fail validation "
                     "instead of failing the merge."},
    "dry_run": {"type": "boolean", "description": "Validate and report the layout without writing."},
    "check": {"type": "string", "enum": ["design"], "description": "Also run the design checks on every row."},
    "copies": {"type": "integer", "minimum": 1, "maximum": 1000, "default": 1,
               "description": "Print every row this many times."},
    "replace": {"type": "boolean", "description": "Overwrite existing outputs."},
    "rerun": {**PATH, "description": "A sheet document from an earlier merge: repeat it with its recorded template, "
              "data and sheet spec (request fields override), rewriting its outputs."},
}


def sheet_spec(spec):
    """A validated sheet spec with defaults filled in. Errors name the offending key."""
    require(spec is None or isinstance(spec, dict), "sheet must be an object", field="sheet")
    spec = dict(spec or {})
    unknown = sorted(set(spec) - set(SHEET_KEYS))
    if unknown:
        hints = {key: difflib.get_close_matches(key, SHEET_KEYS, 1, 0.5) for key in unknown}
        raise VixlError("invalid_request", f"Unknown sheet field(s) {', '.join(map(repr, unknown))}; allowed: "
                        f"{', '.join(SHEET_KEYS)}" + "".join(f". Did you mean {v[0]!r} instead of {k!r}?"
                                                             for k, v in hints.items() if v),
                        field="sheet." + unknown[0], allowed=list(SHEET_KEYS))
    custom = "width" in spec or "height" in spec
    require(not (custom and "size" in spec), "Give a named size or width and height, not both", field="sheet.size")
    require(("width" in spec) == ("height" in spec), "Give both width and height", field="sheet.width")
    if custom:
        require(spec.get("unit") in UNITS, f"A custom size needs unit: one of {', '.join(UNITS)}", field="sheet.unit")
    else:
        spec.setdefault("size", "letter")
        require(isinstance(spec["size"], str), "size must be a named size such as letter or a4", field="sheet.size")
        require(spec.get("unit") in (None, *UNITS), f"unit must be one of {', '.join(UNITS)}", field="sheet.unit")
    require(spec.get("orientation") in (None, "portrait", "landscape"), "orientation must be portrait or landscape",
            field="sheet.orientation")
    finite(spec.setdefault("dpi", 300), "dpi", 36, 2400)
    for key in ("cols", "rows"):
        if spec.get(key) is not None:
            require(isinstance(spec[key], int) and not isinstance(spec[key], bool) and 1 <= spec[key] <= 200,
                    f"{key} must be a whole number from 1 to 200", field="sheet." + key)
    spec["gutter"] = _pair(spec.get("gutter", 0), "gutter")
    if "margin" in spec:
        spec["margin"] = _edges(spec["margin"])
    bleed = spec.setdefault("bleed", "template")
    require(bleed == "template" or (isinstance(bleed, (int, float)) and not isinstance(bleed, bool) and bleed >= 0),
            "bleed is a length or 'template' (use the bleed the template was made with)", field="sheet.bleed")
    marks = spec.setdefault("crop_marks", True)
    if isinstance(marks, dict):
        require(set(marks) <= set(MARK_KEYS), f"crop_marks takes {', '.join(MARK_KEYS)}", field="sheet.crop_marks")
        for key, value in marks.items():
            finite(value, "crop mark " + key, 0, 1000)
    else:
        require(isinstance(marks, bool), "crop_marks is true, false or {length, offset, weight}", field="sheet.crop_marks")
    require(isinstance(spec.setdefault("registration", False), bool), "registration is true or false",
            field="sheet.registration")
    slug = spec.setdefault("slug", None)
    require(slug is None or (isinstance(slug, str) and len(slug) <= 300), "slug is text of up to 300 characters",
            field="sheet.slug")
    if slug:
        try:
            slug.format_map({key: 0 for key in SLUG_FIELDS})
        except (KeyError, IndexError, ValueError) as exc:
            raise VixlError("invalid_request", f"slug can use {', '.join('{' + key + '}' for key in SLUG_FIELDS)}: {exc!r}",
                            field="sheet.slug") from exc
    require(spec.setdefault("order", "rows") in ("rows", "columns"), "order must be rows or columns", field="sheet.order")
    require(spec.setdefault("align", "center") in ("center", "top-left"), "align must be center or top-left",
            field="sheet.align")
    from .render import color

    color(spec.setdefault("background", "#ffffff"))
    return spec


def _pair(value, name):
    values = [value, value] if isinstance(value, (int, float)) and not isinstance(value, bool) else value
    require(isinstance(values, list) and len(values) == 2, f"{name} is a length or [horizontal, vertical]",
            field="sheet." + name)
    return [finite(v, name, 0, 10000) for v in values]


def _edges(value):
    """[top, right, bottom, left] from a length, [vertical, horizontal], [top, right, bottom, left] or a dict."""
    if isinstance(value, dict):
        require(set(value) <= {"top", "right", "bottom", "left"}, "margin keys are top, right, bottom, left",
                field="sheet.margin")
        edges = [value.get(key, 0) for key in ("top", "right", "bottom", "left")]
    elif isinstance(value, list) and len(value) == 2:
        edges = [value[0], value[1], value[0], value[1]]
    elif isinstance(value, list) and len(value) == 4:
        edges = value
    else:
        edges = [value] * 4
    return [finite(v, "margin", 0, 10000) for v in edges]


def layout(canvas, spec):
    """The grid, in sheet pixels (floats): the page, the template's trim and bleed, the grid and its origin and
    the mark geometry. ``unit`` is the unit the spec's lengths use. Raises when the spec does not fit."""
    from .sizes import UNIT_INCHES, resolve, to_pixels

    spec = sheet_spec(spec)
    dpi = spec["dpi"]
    if "width" in spec:
        unit, size = spec["unit"], None
        width, height = finite(spec["width"], "width", 1e-6), finite(spec["height"], "height", 1e-6)
        if spec.get("orientation") == "portrait" and width > height or spec.get("orientation") == "landscape" and height > width:
            width, height = height, width
    else:
        info = resolve(spec["size"], orientation=spec.get("orientation"))
        require("physical" in info, f"{info['size']} is a screen size; sheets use paper sizes such as letter, a4 or tabloid",
                field="sheet.size")
        physical = info["physical"]
        unit, size = spec.get("unit") or physical["unit"], info["size"]
        factor = UNIT_INCHES[physical["unit"]] / UNIT_INCHES[unit]
        width, height = physical["width"] * factor, physical["height"] * factor
    ppu = to_pixels(1, unit, dpi)
    page = (round(width * ppu), round(height * ppu))
    require(page[0] >= 8 and page[1] >= 8, "The sheet is too small", field="sheet.size")
    # The template: its trim box (the canvas minus its bleed) and the scale from its pixels to sheet pixels.
    bleed_t = canvas.get("bleed", 0)
    trim_t = (canvas["width"] - 2 * bleed_t, canvas["height"] - 2 * bleed_t)
    template_dpi = canvas.get("dpi")
    scale = dpi / template_dpi if template_dpi else 1.0
    trim = (trim_t[0] * scale, trim_t[1] * scale)
    available_bleed = bleed_t * scale
    bleed = available_bleed if spec["bleed"] == "template" else spec["bleed"] * ppu
    require(bleed <= available_bleed + 0.5, f"The sheet asks for {spec['bleed']} {unit} of bleed but the template has only "
            f"{available_bleed / ppu:.4g} {unit}; make the template with bleed (a print size with bleed) or lower bleed",
            field="sheet.bleed")
    bleed = min(bleed, available_bleed)
    gx, gy = spec["gutter"][0] * ppu, spec["gutter"][1] * ppu
    marks = _marks(spec, ppu, dpi, bleed, unit)
    need = marks["need"] if marks["crop"] else 0
    reach = need + (2 * marks["target"] + 2 * marks["weight"] if marks["registration"] else 0)
    inch = UNIT_INCHES["in"] / UNIT_INCHES[unit] * ppu
    # By default the margin is as small as the marks allow, but at least a quarter inch.
    margins = [m * ppu for m in spec["margin"]] if "margin" in spec else [max(inch / 4, reach + 1)] * 4
    top, right, bottom, left = margins
    avail_w, avail_h = page[0] - left - right, page[1] - top - bottom

    def fit(space, item, gap):
        return int((space + gap + 0.5) // (item + gap))

    counts = {}
    for axis, wanted, item, space, gap in (("cols", spec.get("cols"), trim[0], avail_w, gx),
                                           ("rows", spec.get("rows"), trim[1], avail_h, gy)):
        maximum = fit(space, item, gap)
        require(maximum >= 1, f"A {trim[0] / ppu:.4g} × {trim[1] / ppu:.4g} {unit} item does not fit inside the margins of "
                f"a {width:.4g} × {height:.4g} {unit} sheet; lower margin or choose a larger sheet", field="sheet." + axis)
        count = wanted or maximum
        require(count <= maximum, f"{count} {axis} of {item / ppu:.4g} {unit} items need "
                f"{(count * item + (count - 1) * gap) / ppu:.4g} {unit} but only {space / ppu:.4g} {unit} are free inside the "
                f"margins; at most {maximum} fit. Lower {axis}, margin or gutter, or choose a larger sheet", field="sheet." + axis)
        counts[axis] = count
    cols, rows = counts["cols"], counts["rows"]
    grid = (cols * trim[0] + (cols - 1) * gx, rows * trim[1] + (rows - 1) * gy)
    origin = (left + (avail_w - grid[0]) / 2, top + (avail_h - grid[1]) / 2) if spec["align"] == "center" else (left, top)
    plan = {"spec": spec, "unit": unit, "size": size, "dpi": dpi, "ppu": ppu, "page": page, "page_unit": (width, height),
            "scale": scale, "bleed_t": bleed_t, "trim_t": trim_t, "trim": trim, "bleed": bleed, "gutter": (gx, gy),
            "margins": (top, right, bottom, left), "cols": cols, "rows": rows, "per_page": cols * rows, "grid": grid,
            "origin": origin, "marks": marks, "template_dpi": template_dpi}
    room = {"left": origin[0], "right": page[0] - origin[0] - grid[0], "top": origin[1], "bottom": page[1] - origin[1] - grid[1]}
    for side, space in room.items():
        if (marks["crop"] or marks["registration"]) and space + 0.5 < reach:
            what = "Crop and registration marks" if marks["crop"] and marks["registration"] else (
                "Crop marks" if marks["crop"] else "Registration marks")
            raise VixlError("invalid_request", f"{what} need {reach / ppu:.3g} {unit} between the grid and the {side} edge of "
                            f"the sheet but there are {space / ppu:.3g} {unit}; raise margin or lower "
                            f"{'cols' if side in ('left', 'right') else 'rows'}, or turn the marks off",
                            field="sheet.margin")
    return plan


def _marks(spec, ppu, dpi, bleed, unit):
    options = spec["crop_marks"] if isinstance(spec["crop_marks"], dict) else {}
    pt = dpi / 72
    weight = max(1, round(options.get("weight", CROP_WEIGHT_PT) * pt))
    length = options["length"] * ppu if "length" in options else CROP_LENGTH_PT * pt
    offset = options["offset"] * ppu if "offset" in options else bleed + CROP_GAP_PT * pt
    require(offset + 0.5 >= bleed, f"Crop marks start {offset / ppu:.3g} {unit} from the trim, inside the {bleed / ppu:.3g} "
            f"{unit} bleed; use an offset of at least the bleed", field="sheet.crop_marks")
    return {"crop": bool(spec["crop_marks"]), "length": length, "offset": offset, "weight": weight,
            "need": offset + length + weight / 2, "registration": spec["registration"],
            "target": REGISTRATION_RADIUS_PT * pt, "slug": spec["slug"], "slug_px": SLUG_PT * pt}


def slots(plan, count):
    """[(sheet index, column, row)] for ``count`` copies in reading order."""
    result = []
    for index in range(count):
        sheet, slot = divmod(index, plan["per_page"])
        if plan["spec"]["order"] == "columns":
            col, row = slot // plan["rows"], slot % plan["rows"]
        else:
            col, row = slot % plan["cols"], slot // plan["cols"]
        result.append((sheet, col, row))
    return result


def cell_geometry(plan, col, row, occupied):
    """One copy's placement: ``(trim box, bleed per side, layer box, template crop)``. The trim box is
    (x, y, width, height) in sheet pixels. Bleed is (left, top, right, bottom); where a neighbouring copy shares
    an edge each gets half the gutter at most, so one copy's bleed never covers another. The layer box is the
    integer box the link occupies, and the crop (template pixels) maps that box back onto the template exactly,
    so a trim edge lands where it belongs even when the box is rounded."""
    (ox, oy), (tw, th), (gx, gy), bleed = plan["origin"], plan["trim"], plan["gutter"], plan["bleed"]
    x, y = ox + col * (tw + gx), oy + row * (th + gy)
    left = min(bleed, gx / 2) if (col - 1, row) in occupied else bleed
    right = min(bleed, gx / 2) if (col + 1, row) in occupied else bleed
    top = min(bleed, gy / 2) if (col, row - 1) in occupied else bleed
    bottom = min(bleed, gy / 2) if (col, row + 1) in occupied else bleed
    x0, y0, x1, y1 = round(x - left), round(y - top), round(x + tw + right), round(y + th + bottom)
    scale, tb = plan["scale"], plan["bleed_t"]
    (trim_w, trim_h) = plan["trim_t"]
    crop = [max(0.0, tb + (x0 - x) / scale), max(0.0, tb + (y0 - y) / scale),
            min(trim_w + 2.0 * tb, tb + trim_w + (x1 - (x + tw)) / scale),
            min(trim_h + 2.0 * tb, tb + trim_h + (y1 - (y + th)) / scale)]
    return (x, y, tw, th), (left, top, right, bottom), (x0, y0, x1 - x0, y1 - y0), crop


def mark_shapes(plan, used_cols, used_rows):
    """Crop and registration marks in the margins: ``[(name, kind, x, y, width, height)]`` in sheet pixels, kind
    ``solid`` (a filled bar) or ``target`` (a ring)."""
    marks = plan["marks"]
    (ox, oy), (tw, th), (gx, gy), t = plan["origin"], plan["trim"], plan["gutter"], marks["weight"]
    grid_w, grid_h = used_cols * tw + (used_cols - 1) * gx, used_rows * th + (used_rows - 1) * gy
    page_w, page_h = plan["page"]
    shapes = []

    def edges(origin, size, gap, count):
        found = []
        for index in range(count):
            start = origin + index * (size + gap)
            for edge in (start, start + size):
                if not found or abs(edge - found[-1]) > 0.5:
                    found.append(edge)
        return found

    if marks["crop"]:
        offset, length = marks["offset"], marks["length"]
        for number, edge in enumerate(edges(ox, tw, gx, used_cols), 1):
            x = round(edge - t / 2)
            shapes.append((f"crop-top-{number}", "solid", x, round(oy - offset - length), t, round(length)))
            shapes.append((f"crop-bottom-{number}", "solid", x, round(oy + grid_h + offset), t, round(length)))
        for number, edge in enumerate(edges(oy, th, gy, used_rows), 1):
            y = round(edge - t / 2)
            shapes.append((f"crop-left-{number}", "solid", round(ox - offset - length), y, round(length), t))
            shapes.append((f"crop-right-{number}", "solid", round(ox + grid_w + offset), y, round(length), t))
    if marks["registration"]:
        r = marks["target"]
        d = (marks["need"] if marks["crop"] else 0) + r + t  # just beyond the crop marks
        for name, cx, cy in (("top", page_w / 2, oy - d), ("bottom", page_w / 2, oy + grid_h + d),
                             ("left", ox - d, page_h / 2), ("right", ox + grid_w + d, page_h / 2)):
            size = round(2 * r)
            shapes.append((f"registration-{name}", "target", round(cx - size / 2), round(cy - size / 2), size, size))
            shapes.append((f"registration-{name}-h", "solid", round(cx - 1.75 * r), round(cy - t / 2), round(3.5 * r), t))
            shapes.append((f"registration-{name}-v", "solid", round(cx - t / 2), round(cy - 1.75 * r), t, round(3.5 * r)))
    return shapes


def template_variables(view):
    """(used, defaults, images, fields) for a template view: the variable names it draws, the ones it defines,
    its image variables and its form field keys."""
    from .forms import all_fields, has_fields

    state = view.state
    from .variables import names, strings

    used = {name for key in SCANNED for text in strings(state.get(key)) for name in names(text)}
    images = {layer["asset_variable"] for layer in state.get("layers", []) if layer.get("asset_variable")}
    defaults = set(state.get("variables", {})) - set(BUILTINS)
    fields = {layer["field"]["key"] for _, layer in all_fields(view)} if has_fields(view) else set()
    return used - set(BUILTINS), defaults, images, fields


def read_data(session, request):
    """(headers, rows, workspace-relative source or None) from ``data`` (a CSV) or ``rows`` (inline objects)."""
    from .exports import read_csv

    require(("data" in request) != ("rows" in request), "Give data (a CSV) or rows (inline objects), not both",
            field="data", suggestions=[{"data": "rows.csv"}, {"rows": [{"first": "Ada"}]}])
    if "data" in request:
        require(isinstance(request["data"], str), "data is a workspace-relative CSV path", field="data")
        path = session.resolve(request["data"])
        require(path.is_file(), f"Data file does not exist: {request['data']}", "not_found", field="data")
        headers, rows = read_csv(path, MAX_ITEMS)
        return headers, rows, session.relative(path)
    rows = request["rows"]
    require(isinstance(rows, list) and 0 < len(rows) <= MAX_ITEMS and all(isinstance(row, dict) for row in rows),
            f"rows is a list of 1 to {MAX_ITEMS} objects", field="rows")
    headers = []
    for row in rows:
        for key, value in row.items():
            require(isinstance(key, str) and key and (value is None or isinstance(value, (str, int, float, bool))),
                    "rows hold {name: text, number or true/false} values", field="rows")
            if key not in headers:
                headers.append(key)
    return headers, [{key: "" if row.get(key) is None else str(row[key]) for key in headers} for row in rows], None


def _constants(variables):
    require(variables is None or (isinstance(variables, dict) and len(variables) <= 256 and all(
        isinstance(k, str) and NAME.fullmatch(k) and isinstance(v, (str, int, float, bool)) for k, v in variables.items())),
        "variables maps names to text, numbers or true/false", field="variables")
    return {key: value if isinstance(value, str) else str(value) for key, value in (variables or {}).items()}


class Preflight:
    """Validates rows against the template by the same route the sheet draws them: as a link with variables."""

    def __init__(self, session, host, source, request, template):
        from .links import prepare

        self.session, self.host, self.source, self.template = session, host, source, template
        self.page, self.artboard, self.check = request.get("page"), request.get("artboard"), request.get("check")
        self.constants = _constants(request.get("variables"))
        self.prepare = prepare
        prepared = prepare(host, self._link({}))
        self.used, self.defaults, self.images, self.fields = template_variables(prepared.view)
        self.revision, self.size = prepared.revision, prepared.size
        self.known = self.used | self.defaults | self.images | self.fields | set(self.constants)
        # Templates need a sample value for every variable, so a variable without a column would print the sample.
        self.needed = (self.used | self.images) - self.fields - set(self.constants)

    def _link(self, values):
        return {"id": "merge", "name": "merge", "source": self.source, "source_page": self.page, "artboard": self.artboard,
                "variables": values}

    def columns(self, headers, unknown, defaults):
        """(errors, warnings, unmatched) for the data as a whole: variables the template draws that no column provides
        (``defaults`` picks error, warn or ignore), and columns that match no variable (``unknown``)."""
        errors, warnings = [], []
        unmatched = [name for name in headers if name not in self.known]
        for name in sorted(self.needed - set(headers)) if defaults != "ignore" else ():
            close = difflib.get_close_matches(name, unmatched, 1, 0.5)
            (errors if defaults == "error" else warnings).append(
                {"row": None, "code": "missing_column", "column": name,
                 "message": f"The template draws ${{{name}}} but the data has no {name!r} column, so every copy would print the "
                 "template's own sample value" + (f" (did you mean {close[0]!r}?)" if close else "")
                 + "; add the column, pass a constant in variables, or set defaults to warn"})
        if unknown != "ignore":
            for name in unmatched:
                close = difflib.get_close_matches(name, sorted(self.known - set(headers)), 1, 0.5)
                (errors if unknown == "error" else warnings).append(
                    {"row": None, "code": "unknown_column", "column": name,
                     "message": f"The data column {name!r} matches no variable in the template"
                     + (f" (did you mean {close[0]!r}?)" if close else "")})
        return errors, warnings, unmatched

    def values(self, number, row, csv_dir):
        """(variables for the copy, errors): known columns with empty cells kept as empty values, image columns turned
        into workspace-relative file paths."""
        values, errors = dict(self.constants), []
        for column, cell in row.items():
            if column not in self.known or column in self.fields:
                continue
            if len(cell) > 10000 or "\0" in cell:
                errors.append(self._error(number, "invalid_value", f"column {column!r} is too long or not text", column=column))
            elif column in self.images:
                values[column], problem = self._image(cell, csv_dir, column) if cell else (cell, f"the image cell {column!r} is empty")
                if problem:
                    errors.append(self._error(number, "missing_image", problem, column=column))
            else:
                values[column] = cell
        return values, errors

    def _image(self, cell, csv_dir, column):
        """(value, problem): an embedded asset ID, or the workspace-relative path of an image next to the CSV or
        in the workspace."""
        if cell in self.template.assets:
            return cell, None
        for base in (csv_dir, self.session.workspace):
            path = (base / cell).resolve()
            if path.is_file():
                if not path.is_relative_to(self.session.workspace):
                    return cell, f"the image for {column!r} is outside the workspace"
                return self.session.relative(path), None
        return cell, f"the image file for {column!r} does not exist"

    @staticmethod
    def _error(number, code, message, **extra):
        return {"row": number, "code": code, "message": f"Row {number}: {message}", **extra}

    def row(self, number, values):
        """(errors, notes) for one copy with its variables applied: text that does not fit its box, characters no font
        draws and, with ``check: design``, the design checks."""
        from .checks import boxed_text_overflow, check_design, glyph_reports
        from .render import resolved_layers

        try:
            view = self.prepare(self.host, self._link(values)).view
            layers = resolved_layers(view)
        except VixlError as exc:
            return [self._error(number, exc.code, str(exc))], []
        index = {item["id"]: item for item in layers}

        def shown(item):
            while item:
                if not item["visible"] or item["opacity"] <= 0:
                    return False
                item = index.get(item.get("parent"))
            return True

        errors, notes = [], []
        text = [item for item in layers if item["type"] == "text" and shown(item)]
        for item in text:
            needed = boxed_text_overflow(view, item)
            if needed:
                errors.append(self._error(number, "overflow", f"text layer {item['name']!r} does not fit its "
                                          f"{item['width']}×{item['height']} box (it needs {needed[0]}×{needed[1]})",
                                          layer=item["name"]))
        for item, report in glyph_reports(view, text):
            if report["missing"]:
                errors.append(self._error(number, "missing_glyphs", f"text layer {item['name']!r} has characters no font can "
                                          f"draw ({''.join(report['missing'][:12])}); they would print as empty boxes",
                                          layer=item["name"]))
        if self.check == "design" and not errors:
            result = check_design(view, checks=["bounds", "overlap", "contrast", "fonts", "links"])
            errors += [self._error(number, "design", issue["message"]) for issue in result["issues"]
                       if issue["severity"] == "error"]
            notes += [{"row": number, "code": "design", "message": f"Row {number}: {issue['message']}"}
                      for issue in result["issues"] if issue["severity"] != "error"]
        return errors, notes


def build_sheet(session, plan, items, source, revision, size, page, artboard, path=None):
    """The sheet document in memory: one page per sheet, a ``link`` layer per copy, marks and slug text.
    ``items`` is [(row number, copy number, variables)]. With ``path`` (where the sheet document will be saved)
    the cells store the template relative to that folder when it lies inside it."""
    from .links import stored_source
    from .pages import empty_content, put_content, set_builtins
    from .pages import MAX_PAGES as PAGE_LIMIT
    from .project import Project
    from .render import text_metrics

    spec = plan["spec"]
    sheets = max(1, math.ceil(len(items) / plan["per_page"]))
    require(sheets <= min(MAX_PAGES, PAGE_LIMIT), f"{len(items)} copies need {sheets} sheets; at most "
            f"{min(MAX_PAGES, PAGE_LIMIT)} are supported", "resource_limit", field="rows")
    project = Project(plan["page"][0], plan["page"][1], spec["background"], limits=session.limits)
    project._workspace = session.workspace
    if path is not None:
        project.path = Path(path).resolve()
    cell_source = stored_source(project, session.resolve(source))
    canvas = project.state["canvas"]
    canvas["dpi"] = plan["dpi"]
    canvas["physical"] = {"width": plan["page_unit"][0], "height": plan["page_unit"][1], "unit": plan["unit"], "bleed": 0}
    if plan["size"]:
        canvas["size"] = plan["size"]
    by_sheet = {}
    for (sheet, col, row), item in zip(slots(plan, len(items)), items):
        by_sheet.setdefault(sheet, []).append((col, row, item))
    records = []
    for sheet in range(sheets):
        entries = by_sheet.get(sheet, [])
        occupied = {(col, row) for col, row, _ in entries}
        layers = []
        for col, row, (number, copy, variables) in entries:
            _, _, box, crop = cell_geometry(plan, col, row, occupied)
            layer = new_layer(f"row-{number}" if copy == 1 else f"row-{number}-copy-{copy}", "link", box[2], box[3],
                              source=cell_source, fit="stretch", crop=[int(v) if float(v).is_integer() else round(v, 6) for v in crop],
                              variables=dict(variables), source_hash=revision, source_size=list(size))
            layer["x"], layer["y"] = box[0], box[1]
            if page is not None:
                layer["source_page"] = page
            if artboard:
                layer["artboard"] = artboard
            layers.append(layer)
        used_cols = max((col for col, _, _ in entries), default=0) + 1
        used_rows = max((row for _, row, _ in entries), default=0) + 1
        for name, kind, x, y, w, h in mark_shapes(plan, used_cols, used_rows):
            if kind == "target":
                layer = new_layer(name, "shape", w, h, shape="ellipse", fill="transparent", stroke="#000000",
                                  stroke_width=plan["marks"]["weight"])
            else:
                layer = new_layer(name, "solid", w, h, fill="#000000")
            layer["x"], layer["y"] = x, y
            layers.append(layer)
        if spec["slug"]:
            numbers = [entry[2][0] for entry in entries]
            text = spec["slug"].format_map({"template": Path(source).stem, "page": sheet + 1, "pages": sheets,
                                            "first": min(numbers, default=0), "last": max(numbers, default=0),
                                            "count": len(entries), "rows": len(items)})
            layer = new_layer("slug", "text", 1, 1, text=text, font="DejaVuSans.ttf", size=max(1, round(plan["marks"]["slug_px"])),
                              color="#000000", align="left", spacing=4, auto_size=True)
            layer["width"], layer["height"], _ = text_metrics(project, layer)
            layer["x"], layer["y"] = round(plan["origin"][0]), round(plan["page"][1] - layer["height"] - 3 * plan["dpi"] / 72)
            below = plan["origin"][1] + plan["grid"][1] + (plan["marks"]["need"] if plan["marks"]["crop"] else 0)
            require(layer["y"] >= below - 0.5, "There is no room for the slug text below the grid; raise margin or use fewer "
                    "rows", field="sheet.slug")
            layers.append(layer)
        require(len(layers) <= project.limits.max_layers, f"Sheet {sheet + 1} needs {len(layers)} layers, over the "
                f"{project.limits.max_layers} layer limit; use larger items or turn off the marks", "resource_limit")
        content = {**empty_content(), "layers": layers, "active_layer": layers[-1]["id"] if layers else None}
        records.append(({"id": uid("pg"), "name": f"sheet-{sheet + 1}"}, content))
    state = project.state
    state["pages"] = [record for record, _ in records]
    put_content(state, records[0][1])
    state["page"] = records[0][0]["id"]
    for record, content in records[1:]:
        record["content"] = content
    set_builtins(state)
    return project


def run(session, template, request):
    """Validate, lay out and write a merge. ``template`` is the loaded template Project: a saved document inside
    the workspace. Returns the report."""
    from .pdf_export import export_pdf
    from .production import write_bytes
    from .validation import check_state

    require(getattr(template, "path", None) is not None, "The template must be a saved .vixl document", field="template")
    try:
        source = session.relative(Path(template.path).resolve())
    except ValueError as exc:
        raise VixlError("forbidden", "The template is outside the workspace; merges run inside one workspace",
                        field="template") from exc
    request = dict(request)
    for field in ("unknown", "defaults", "check"):
        enum = FIELD_TYPES[field]["enum"]
        require(request.get(field) is None or request[field] in enum, f"{field} must be one of {', '.join(enum)}", field=field)
    unknown, defaults, copies = request.get("unknown") or "warn", request.get("defaults") or "error", request.get("copies", 1)
    require(isinstance(copies, int) and not isinstance(copies, bool) and 1 <= copies <= 1000, "copies must be 1 to 1000",
            field="copies")
    for field in ("skip_invalid", "dry_run", "replace"):
        require(type(request.get(field, False)) is bool, f"{field} must be true or false", field=field)
    outputs = _outputs(session, request, request.get("replace", False) or request.get("dry_run", False))
    require(request.get("dry_run") or outputs, "Give output (a .pdf or .vixl) or sheet_document, or dry_run to only validate",
            field="output")
    spec = sheet_spec(request.get("sheet"))
    headers, rows, data_source = read_data(session, request)
    host = _host(session)
    check = Preflight(session, host, source, request, template)
    # An artboard is the item when one is chosen: its size, and no bleed (artboards carry none).
    item = {**template.state["canvas"], "width": check.size[0], "height": check.size[1]}
    if request.get("artboard"):
        item.pop("bleed", None)
    plan = layout(item, spec)
    column_errors, column_warnings, unmatched = check.columns(headers, unknown, defaults)
    csv_dir = session.resolve(data_source).parent if data_source else session.workspace
    report = {"rows": len(rows), "valid": 0, "invalid": [], "errors": list(column_errors), "warnings": list(column_warnings),
              "unknown_columns": unmatched,
              "variables": {"used": sorted(check.used), "defaults": sorted(check.defaults), "images": sorted(check.images),
                            "columns": headers}}
    if plan["template_dpi"] is None:
        report["warnings"].append({"row": None, "code": "template_dpi", "message": "The template has no dpi, so it is placed at "
                                   "one pixel per sheet pixel; make it from a print size or give it a dpi for a predictable size"})
    valid, bad = [], set()
    for number, row in enumerate(rows, 1):
        values, problems = check.values(number, row, csv_dir)
        if not problems and not column_errors:
            more, notes = check.row(number, values)
            problems += more
            report["warnings"] += notes
        if problems:
            bad.add(number)
            report["errors"] += problems
        else:
            valid.append((number, values))
    expanded = [(number, copy, values) for number, values in valid for copy in range(1, copies + 1)]
    report.update(invalid=sorted(bad), valid=len(valid),
                  layout=describe(plan, len(expanded), math.ceil(len(expanded) / plan["per_page"])))
    if request.get("dry_run"):
        report["dry_run"] = True
        return report
    blocking = [item for item in report["errors"] if item["row"] is None]
    if blocking or (bad and not request.get("skip_invalid")):
        raise VixlError("merge_invalid", f"{len(blocking)} data problem(s) and {len(bad)} row(s) failed validation; nothing was "
                        "written (skip_invalid writes the valid rows)", report=report)
    require(valid, "No valid rows to write", "merge_invalid", report=report)
    require(len(expanded) <= MAX_ITEMS, f"At most {MAX_ITEMS} copies per merge", "resource_limit", field="copies")
    sheet = build_sheet(session, plan, expanded, source, check.revision, check.size, request.get("page"), request.get("artboard"),
                        outputs.get("sheet_document"))
    sheet.state["merge"] = _record(request, source, data_source, plan)
    check_state(sheet, sheet.state)
    sheet.nodes, sheet.head, sheet._head_state, sheet.branches = {}, None, None, {}
    sheet._verified = set()
    sheet._record([], f"Merge {len(valid)} rows of {Path(source).name}")
    report["pages"] = report["layout"]["pages"]
    if "pdf" in outputs:
        info = {}
        data = export_pdf(sheet, None, content="vector", dpi=plan["dpi"], title=f"{Path(source).stem} (merged)", report=info)
        report.update(fonts=info["fonts"], raster_fallbacks=info["raster_fallbacks"], bytes=len(data))
        write_bytes(outputs["pdf"], data, replace=request.get("replace", False))
        report["output"] = session.relative(outputs["pdf"])
    if "sheet_document" in outputs:
        sheet.save(outputs["sheet_document"])
        report["sheet_document"] = session.relative(outputs["sheet_document"])
    return report


def _outputs(session, request, replace):
    outputs = {}
    for field in ("output", "sheet_document"):
        if request.get(field) is None:
            continue
        require(isinstance(request[field], str), f"{field} is a workspace-relative path", field=field)
        path = session.resolve(request[field])
        kind = {".pdf": "pdf", ".vixl": "sheet_document"}.get(path.suffix.lower())
        require(kind and (field == "output" or kind == "sheet_document"),
                "output is a .pdf (the print sheets) or a .vixl (the editable sheet document); sheet_document is a .vixl",
                field=field)
        require(kind not in outputs, "Give one PDF and one sheet document at most", field=field)
        require(path.parent.is_dir(), f"The folder for {request[field]} does not exist", field=field)
        require(replace or not path.exists(), f"{request[field]} already exists; choose a new name or pass replace: true",
                "output_exists", field=field)
        outputs[kind] = path
    return outputs


def _record(request, source, data_source, plan):
    """What a later ``rerun`` needs to repeat this merge."""
    record = {"version": 1, "template": source, "sheet": plan["spec"]}
    if data_source:
        record["data"] = data_source
    else:
        record["rows"] = request["rows"]
    for key in ("variables", "page", "artboard", "unknown", "defaults", "skip_invalid", "check", "copies", "output",
                "sheet_document"):
        if request.get(key) not in (None, False):
            record[key] = request[key]
    return record


def describe(plan, copies, sheets):
    """The layout in the sheet's own unit, for reports."""
    ppu, marks = plan["ppu"], plan["marks"]

    def u(value):
        return round(value / ppu, 4)

    return {"page": {"size": plan["size"], "width": round(plan["page_unit"][0], 4), "height": round(plan["page_unit"][1], 4),
                     "unit": plan["unit"], "pixels": list(plan["page"]), "dpi": plan["dpi"]},
            "item": {"trim": [u(plan["trim"][0]), u(plan["trim"][1])], "bleed": u(plan["bleed"]), "scale": round(plan["scale"], 6)},
            "grid": {"cols": plan["cols"], "rows": plan["rows"], "per_page": plan["per_page"], "order": plan["spec"]["order"],
                     "gutter": [u(v) for v in plan["gutter"]], "margin": [u(v) for v in plan["margins"]],
                     "origin": [u(v) for v in plan["origin"]]},
            "marks": {"crop_marks": marks["crop"], "registration": marks["registration"], "slug": bool(marks["slug"]),
                      "crop_length": u(marks["length"]), "crop_offset": u(marks["offset"])},
            "copies": copies, "pages": sheets}


def _host(session):
    """A stand-in sheet document that rows are validated against: it carries the workspace links resolve in."""
    from .project import Project

    host = Project(8, 8, limits=session.limits)
    host._workspace = session.workspace
    return host


def dispatch(session, request, document=None):
    """The ``merge-impose`` workflow action."""
    try:
        request = dict(request)
        if request.get("rerun"):
            request = _rerun(session, request)
        with session.project(document=request.pop("template", None) or document) as project:
            template = project.clone()
        return run(session, template, request)
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        raise VixlError("invalid_request", f"Invalid merge-impose request: {exc!r}",
                        suggestions=["See vixl_workflow_schema actions['merge-impose'].properties"]) from exc


def _rerun(session, request):
    """The recorded request of a sheet document (its template, data, sheet spec and outputs), overridden by the fields
    of ``request``. Outputs are rewritten, so ``replace`` defaults to true."""
    require(isinstance(request["rerun"], str), "rerun is the path of a sheet document", field="rerun")
    with session.project(document=request["rerun"]) as sheet:
        record = sheet.state.get("merge")
    require(isinstance(record, dict) and record.get("version") == 1,
            f"{request['rerun']} was not made by merge-impose, so it has no recorded merge", field="rerun")
    merged = {key: value for key, value in record.items() if key != "version"}
    if "data" in request or "rows" in request:
        merged.pop("data", None)
        merged.pop("rows", None)
    merged.update({key: value for key, value in request.items() if key != "rerun"})
    if isinstance(record.get("sheet"), dict) and isinstance(request.get("sheet"), dict):
        merged["sheet"] = {**record["sheet"], **request["sheet"]}
    if "sheet_document" not in merged and not str(merged.get("output", "")).endswith(".vixl"):
        merged["sheet_document"] = request["rerun"]
    merged.setdefault("replace", True)
    return merged


def cli(args, options, limits):
    """``vixl merge [TEMPLATE.vixl] --data rows.csv --out sheets.pdf …``: the workspace is the current folder."""
    from . import Project
    from .cli import current_path

    args = list(args)
    project = None
    if "--rerun" not in args and not any(arg in ("-h", "--help") for arg in args):
        path = args.pop(0) if args and args[0].endswith(".vixl") else current_path(options.project)
        project = Project.load(path, limits=limits, allow_linked=options.allow_linked)
        project._workspace = Path.cwd()
    return command(project, args, limits)


def command(project, args, limits):
    from .commands import Parser, pairs
    from .interfaces import Session

    p = Parser(prog="vixl merge", description="Merge a CSV into the template and impose the copies on print sheets")
    p.add_argument("--data", help="CSV with one row per copy")
    p.add_argument("--out", "--output", dest="output", help="The print PDF (.pdf) or the sheet document (.vixl)")
    p.add_argument("--sheet-document", dest="sheet_document", help="Also write the editable sheet document (.vixl)")
    p.add_argument("--rerun", help="Repeat the merge recorded in this sheet document")
    p.add_argument("--size", help="Named paper size (default letter)")
    p.add_argument("--orientation", choices=["portrait", "landscape"])
    p.add_argument("--unit", choices=UNITS, help="Unit for lengths (default: the size's)")
    p.add_argument("--dpi", type=float)
    p.add_argument("--cols", type=int)
    p.add_argument("--rows", type=int)
    p.add_argument("--gutter", type=float)
    p.add_argument("--margin", type=float)
    p.add_argument("--bleed", help="A length, or 'template' (default) for the bleed the template was made with")
    p.add_argument("--crop-marks", dest="crop_marks", action="store_true", default=None)
    p.add_argument("--no-crop-marks", dest="crop_marks", action="store_false")
    p.add_argument("--registration", action="store_true", default=None)
    p.add_argument("--slug", help="Bottom-margin text: {template} {page} {pages} {first} {last} {count} {rows}")
    p.add_argument("--order", choices=["rows", "columns"])
    p.add_argument("--align", choices=["center", "top-left"])
    p.add_argument("--background")
    p.add_argument("--copies", type=int)
    p.add_argument("--set", action="append", metavar="NAME=VALUE", help="A value for every copy (repeat)")
    p.add_argument("--page", help="The template's page")
    p.add_argument("--artboard")
    p.add_argument("--unknown", choices=["warn", "error", "ignore"], help="Data columns the template does not use")
    p.add_argument("--defaults", choices=["error", "warn", "ignore"],
                   help="Template variables the data has no column for (they would print the template's sample value)")
    p.add_argument("--skip-invalid", dest="skip_invalid", action="store_true", default=None)
    p.add_argument("--dry-run", dest="dry_run", action="store_true", default=None)
    p.add_argument("--check", choices=["design"])
    p.add_argument("--replace", action="store_true", default=None)
    a = {key: value for key, value in vars(p.parse_args(args)).items() if value is not None}
    sheet = {key: a.pop(key) for key in ("size", "orientation", "unit", "dpi", "cols", "rows", "gutter", "margin", "crop_marks",
                                         "registration", "slug", "order", "align", "background") if key in a}
    if "bleed" in a:
        value = a.pop("bleed")
        sheet["bleed"] = value if value == "template" else float(value)
    if sheet:
        a["sheet"] = sheet
    if "set" in a:
        a["variables"] = pairs(a.pop("set"))
    if isinstance(a.get("page"), str) and a["page"].isdigit():
        a["page"] = int(a["page"])
    session = Session(None, limits, workspace=Path.cwd())
    if "rerun" in a:
        a = _rerun(session, a)
        with session.project(document=a.pop("template")) as loaded:
            project = loaded.clone()
    return run(session, project, a)
