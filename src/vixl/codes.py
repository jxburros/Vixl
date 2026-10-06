"""QR codes and barcodes drawn as native vector shapes.

``qr`` and ``barcode`` create a ``shape`` layer of kind ``path`` whose path is the code's dark modules
merged into rectilinear outlines (holes wound the other way, so nonzero and even-odd fills agree), in
a ``path_view`` of whole modules scaled to the layer's box. Raster, SVG, PDF and PPTX therefore draw
the code as ordinary vector geometry. The layer keeps the settings under ``code``; data containing
``${variables}`` is re-encoded whenever the document is resolved, so merges print one code per row.
With an opaque ``background`` the code and a background rectangle of the same box are grouped.

QR codes come from ``segno``. Code 128 (sets B and C, switching for runs of digits) and EAN-13 are
encoded here, with their check characters computed (Code 128) or validated (EAN-13).
"""

from copy import deepcopy

from .errors import VixlError, require
from .model import finite, new_layer

TYPES = ("qr", "barcode")
ERRORS = ("L", "M", "Q", "H")
SYMBOLOGIES = ("code128", "ean13")
QUIET = {"qr": 4, "code128": 10, "ean13": (11, 7)}
MAX_DATA = 2000
VIEW_HEIGHT = 100  # path units for a barcode's height (bars span it; the layer box scales it)
EDIT_KEYS = ("data", "error", "quiet", "color", "background", "size", "module", "width", "height", "symbology")

# Code 128 bar/space widths for values 0-106 (103-105 start A/B/C, 106 stop).
CODE128 = """212222 222122 222221 121223 121322 131222 122213 122312 132212 221213 221312 231212 112232 122132 122231
113222 123122 123221 223211 221132 221231 213212 223112 312131 311222 321122 321221 312212 322112 322211 212123
212321 232121 111323 131123 131321 112313 132113 132311 211313 231113 231311 112133 112331 132131 113123 113321
133121 313121 211331 231131 213113 213311 213131 311123 311321 331121 312113 312311 332111 314111 221411 431111
111224 111422 121124 121421 141122 141221 112214 112412 122114 122411 142112 142211 241211 221114 413111 241112
134111 111242 121142 121241 114212 124112 124211 411212 421112 421211 212141 214121 412121 111143 111341 131141
114113 114311 411113 411311 113141 114131 311141 411131 211412 211214 211232 2331112""".split()
START_B, START_C, CODE_B, CODE_C, STOP = 104, 105, 100, 99, 106
EAN_L = ("0001101", "0011001", "0010011", "0111101", "0100011", "0110001", "0101111", "0111011", "0110111", "0001011")
EAN_G = tuple(code[::-1].translate(str.maketrans("01", "10")) for code in EAN_L)
EAN_R = tuple(code.translate(str.maketrans("01", "10")) for code in EAN_L)
EAN_PARITY = ("LLLLLL", "LLGLGG", "LLGGLG", "LLGGGL", "LGLLGG", "LGGLLG", "LGGGLL", "LGLGLG", "LGLGGL", "LGGLGL")


# ---------------------------------------------------------------------------------------------
# Encoders


def code128_values(data):
    """Symbol values for ``data`` (printable ASCII): set C for runs of four or more digits (or an all-digit
    even-length string), set B otherwise, with the start, check and stop values."""
    require(data and all(32 <= ord(ch) <= 126 for ch in data), "Code 128 data must be printable ASCII (space to ~)",
            "invalid_code", field="data")
    values, i, current = [], 0, None

    def digit_run(at):
        end = at
        while end < len(data) and data[end].isdigit():
            end += 1
        return end - at

    while i < len(data):
        run = digit_run(i)
        if run >= 4 or (run == len(data) and run >= 2 and run % 2 == 0):
            run -= run % 2
            if current != "C":
                values.append(START_C if current is None else CODE_C)
                current = "C"
            values += [int(data[k:k + 2]) for k in range(i, i + run, 2)]
            i += run
            continue
        if current != "B":
            values.append(START_B if current is None else CODE_B)
            current = "B"
        values.append(ord(data[i]) - 32)
        i += 1
    check = (values[0] + sum(position * value for position, value in enumerate(values[1:], 1))) % 103
    return [*values, check, STOP]


def code128_modules(data):
    """Bars as a '1'/'0' module string (no quiet zone)."""
    bits = []
    for value in code128_values(data):
        for index, width in enumerate(CODE128[value]):
            bits.append(("1" if index % 2 == 0 else "0") * int(width))
    return "".join(bits)


def ean13_check(digits):
    total = sum(int(d) * (3 if i % 2 else 1) for i, d in enumerate(digits[:12]))
    return str((10 - total % 10) % 10)


def ean13_modules(data):
    """The 95-module EAN-13 pattern for 12 digits (check digit added) or 13 (check digit validated)."""
    digits = data.replace(" ", "").replace("-", "")
    require(digits.isdigit() and len(digits) in (12, 13), "EAN-13 data is 12 digits (the check digit is added) or 13",
            "invalid_code", field="data")
    check = ean13_check(digits)
    if len(digits) == 13:
        require(digits[12] == check, f"EAN-13 check digit of {digits} should be {check}", "invalid_code", field="data",
                suggestions=[digits[:12] + check])
    else:
        digits += check
    parity = EAN_PARITY[int(digits[0])]
    left = "".join((EAN_L if side == "L" else EAN_G)[int(d)] for d, side in zip(digits[1:7], parity))
    right = "".join(EAN_R[int(d)] for d in digits[7:])
    return "101" + left + "01010" + right + "101", digits


def qr_matrix(data, error):
    import segno

    try:
        code = segno.make(data, error=error.lower(), micro=False, boost_error=False)
    except (ValueError, segno.DataOverflowError) as exc:
        raise VixlError("invalid_code", f"Cannot encode a QR code: {exc}", field="data") from None
    return [[bool(cell) for cell in row] for row in code.matrix], code.version


# ---------------------------------------------------------------------------------------------
# Geometry


def outline(matrix, offset=0):
    """SVG path data for the dark cells of ``matrix`` (rows of booleans) as merged rectilinear contours,
    shifted by ``offset`` modules. Every contour runs clockwise around dark (holes counter-clockwise)."""
    rows, cols = len(matrix), len(matrix[0]) if matrix else 0

    def dark(x, y):
        return 0 <= y < rows and 0 <= x < cols and matrix[y][x]

    edges = {}
    for y in range(rows):
        for x in range(cols):
            if not matrix[y][x]:
                continue
            if not dark(x, y - 1):
                edges.setdefault((x, y), []).append((x + 1, y))
            if not dark(x + 1, y):
                edges.setdefault((x + 1, y), []).append((x + 1, y + 1))
            if not dark(x, y + 1):
                edges.setdefault((x + 1, y + 1), []).append((x, y + 1))
            if not dark(x - 1, y):
                edges.setdefault((x, y + 1), []).append((x, y))
    parts = []
    for start in sorted(edges):
        while edges.get(start):
            loop, point, heading = [start], start, None
            while True:
                options = edges[point]
                if len(options) > 1 and heading is not None:
                    # Where two dark cells touch at a corner, turn so each cell keeps its own contour.
                    options.sort(key=lambda end: _turn(heading, (end[0] - point[0], end[1] - point[1])))
                end = options.pop(0)
                heading = (end[0] - point[0], end[1] - point[1])
                point = end
                if point == start:
                    break
                loop.append(point)
            corners = [p for i, p in enumerate(loop) if not _collinear(loop[i - 1], p, loop[(i + 1) % len(loop)])]
            parts.append("M" + " L".join(f"{x + offset:g} {y + offset:g}" for x, y in corners) + " Z")
    return " ".join(parts)


def _turn(heading, step):
    """0 for a right turn (clockwise in screen coordinates), 1 straight, 2 left."""
    cross = heading[0] * step[1] - heading[1] * step[0]
    return 0 if cross > 0 else 2 if cross < 0 else 1


def _collinear(a, b, c):
    return (b[0] - a[0]) * (c[1] - b[1]) == (b[1] - a[1]) * (c[0] - b[0])


def bars(bits, left):
    """Path data for a 1-D code's bars (runs of '1') across ``VIEW_HEIGHT``, shifted by ``left`` modules."""
    parts, x = [], 0
    while x < len(bits):
        if bits[x] == "1":
            end = x
            while end < len(bits) and bits[end] == "1":
                end += 1
            a, b = x + left, end + left
            parts.append(f"M{a} 0 L{b} 0 L{b} {VIEW_HEIGHT} L{a} {VIEW_HEIGHT} Z")
            x = end
        else:
            x += 1
    return " ".join(parts)


def geometry(record, data):
    """``(path, path_view, details)`` for a code record with its data resolved."""
    kind = record["kind"]
    require(isinstance(data, str) and data and len(data) <= MAX_DATA, f"Code data must be 1 to {MAX_DATA} characters",
            "invalid_code", field="data")
    if kind == "qr":
        matrix, version = qr_matrix(data, record.get("error", "M"))
        quiet = record.get("quiet", QUIET["qr"])
        count = len(matrix) + 2 * quiet
        path = outline(matrix, quiet)
        from .geometry import parse_path

        try:
            parse_path(path)
        except VixlError as exc:
            raise VixlError("invalid_code", f"This QR code (version {version}) has too much detail to draw as one path; "
                            "shorten the data or lower the error correction", field="data") from exc
        return path, [count, count], {"version": version, "modules": len(matrix), "quiet": [quiet] * 4}
    if kind == "ean13":
        modules, digits = ean13_modules(data)
        left, right = QUIET["ean13"] if record.get("quiet") is None else (record["quiet"], record["quiet"])
        details = {"digits": digits}
    else:
        modules = code128_modules(data)
        left = right = QUIET["code128"] if record.get("quiet") is None else record["quiet"]
        details = {}
    return bars(modules, left), [left + len(modules) + right, VIEW_HEIGHT], {
        **details, "modules": len(modules), "quiet": [left, 0, right, 0]}


def resolve(layer, variables):
    """Re-encode a code layer whose data holds ``${variables}`` (resolved_layers calls this on its copy)."""
    from .variables import substitute

    record = layer["code"]
    if "${" not in record["data"]:
        return
    layer["path"], layer["path_view"], _ = geometry(record, substitute(record["data"], variables))


# ---------------------------------------------------------------------------------------------
# Operations


def schemas(add):
    from .schema import COORD, S, enum, field

    common = {
        "name": field(S, "Layer name (the group's name when there is a background)."),
        "data": field(S, "What the code encodes; may contain ${variables}, resolved at render time for merges."),
        "x": COORD, "y": COORD,
        "color": field(S, "Module (bar) colour; default black. Keep it dark on a light background."),
        "background": field(S, "Background colour behind the code and its quiet zone; default white. 'none' or "
                            "'transparent' draws no background (then keep the quiet zone clear yourself)."),
        "quiet": {"type": "integer", "minimum": 0, "maximum": 40,
                  "description": "Quiet zone in modules on each side (default 4 for QR, 10 for Code 128, 11/7 for EAN-13)."},
        "module": {"type": "number", "exclusiveMinimum": 0, "maximum": 200,
                   "description": "Pixels per module (the narrowest bar); default 8 for QR, 3 for barcodes. Give "
                   "module or size/width."},
    }
    add("qr", {**common, "error": {**enum(*ERRORS), "description": "Error correction: L (7%), M (15%, default), "
                                   "Q (25%) or H (30%; survives a small logo on top)."},
               "size": {"type": "number", "exclusiveMinimum": 0, "maximum": 16384,
                        "description": "Side of the whole code including the quiet zone, in pixels."}})
    add("barcode", {**common, "symbology": {**enum(*SYMBOLOGIES), "description": "code128 (any printable ASCII; "
                                            "default) or ean13 (12 digits, or 13 with a valid check digit)."},
                    "width": {"type": "number", "exclusiveMinimum": 0, "maximum": 16384,
                              "description": "Width of the whole barcode including quiet zones, in pixels."},
                    "height": {"type": "number", "exclusiveMinimum": 0, "maximum": 16384,
                               "description": "Bar height in pixels (default: half the width, at least 40)."}})


def _paint(value, field):
    if value is None:
        return None
    if isinstance(value, str) and value.strip().lower() in ("none", "transparent"):
        return "transparent"
    require(isinstance(value, str), f"{field} is a colour", field=field)
    return value


def _record(op, base=None):
    record = dict(base or {})
    kind = op["type"]
    if kind == "qr":
        record["kind"] = "qr"
        if "error" in op:
            record["error"] = op["error"]
        record.setdefault("error", "M")
    else:
        if "symbology" in op or "kind" not in record:
            record["kind"] = op.get("symbology", "code128")
    if "data" in op:
        require(isinstance(op["data"], str), "data is text", field="data")
        record["data"] = op["data"]
    if "quiet" in op:
        record["quiet"] = op["quiet"]
    require("data" in record, f"{kind} needs data (the text, URL or number to encode)", field="data",
            suggestions=[{"type": kind, "data": "https://example.com" if kind == "qr" else "12345678"}])
    return record


def _size(op, record, view, layer=None):
    """(width, height) in pixels from size/width/height or the module size."""
    count = view[0]
    if record["kind"] == "qr":
        if "size" in op:
            side = finite(op["size"], "size", 1, 16384)
        elif "module" in op or layer is None:
            side = count * finite(op.get("module", 8), "module", 0.01, 200)
        else:
            side = layer["width"] * count / layer["path_view"][0]  # keep the module size when the data changes
        return side, side
    if "width" in op:
        width = finite(op["width"], "width", 1, 16384)
    elif "module" in op or layer is None:
        width = count * finite(op.get("module", 3), "module", 0.01, 200)
    else:
        width = layer["width"] * count / layer["path_view"][0]
    height = op["height"] if "height" in op else (layer["height"] if layer else max(40, width / 2))
    return width, finite(height, "height", 1, 16384)


def execute(project, op):
    from .design import resolve_color
    from .render import color, document_variables
    from .variables import substitute

    target = op.get("target")
    if target:
        return _edit(project, project.layer(target), op)
    record = _record(op)
    path, view, _ = geometry(record, substitute(record["data"], document_variables(project)))
    width, height = _size(op, record, view)
    fill = op.get("color", "black")
    background = _paint(op.get("background", "white"), "background")
    for value, name in ((fill, "color"), (background, "background")):
        color(resolve_color(value, project.state))
    _create(project, op, record, path, view, width, height, fill, background)


def _create(project, op, record, path, view, width, height, fill, background):
    from .operations import append_layer, default_name, unique_name

    base = op["name"] if "name" in op else default_name(project, "qr code" if record["kind"] == "qr" else "barcode")
    x, y = op.get("x", 0), op.get("y", 0)
    modules = new_layer(base if background == "transparent" else f"{base} code", "shape", width, height, shape="path",
                        path=path, path_view=view, fill=fill, stroke="transparent", stroke_width=0, code=record)
    if background == "transparent":
        modules["x"], modules["y"] = x, y
        append_layer(project, modules)
        return
    unique_name(project, base)
    group = new_layer(base, "group", width, height, x=x, y=y, content_width=width, content_height=height)
    backdrop = new_layer(f"{base} background", "shape", width, height, shape="rectangle", fill=background,
                         stroke="transparent", stroke_width=0)
    for child in (backdrop, modules):
        child["parent"] = group["id"]
    append_layer(project, group)
    append_layer(project, backdrop)
    append_layer(project, modules)
    project.state["active_layer"] = group["id"]


def code_layer(project, layer):
    """The code's shape layer for a target that is the code or its group."""
    if layer.get("code"):
        return layer
    if layer["type"] == "group":
        for item in project.state["layers"]:
            if item.get("parent") == layer["id"] and item.get("code"):
                return item
    raise VixlError("invalid_operation", f"{layer['name']!r} is not a QR code or barcode", field="target")


def _edit(project, layer, op):
    from .design import resolve_color
    from .render import color, document_variables
    from .variables import substitute

    require(not {"name", "x", "y"} & op.keys(), "Rename or move a code with rename or move; qr/barcode with a target "
            "changes data, error, quiet, color, background and size", field="target")
    code = code_layer(project, layer)
    kind = op["type"]
    require((kind == "qr") == (code["code"]["kind"] == "qr"), f"{layer['name']!r} is a "
            f"{code['code']['kind']} code; edit it with {'qr' if code['code']['kind'] == 'qr' else 'barcode'}",
            field="target")
    record = _record(op, deepcopy(code["code"]))
    path, view, _ = geometry(record, substitute(record["data"], document_variables(project)))
    width, height = _size(op, record, view, code)
    code.update(code=record, path=path, path_view=view, width=width, height=height)
    if "color" in op:
        color(resolve_color(op["color"], project.state))
        code["fill"] = op["color"]
    group = project.layer(code["parent"]) if code.get("parent") else None
    backdrop = None
    if group and group["type"] == "group":
        backdrop = next((item for item in project.state["layers"] if item.get("parent") == group["id"]
                         and item is not code and item["name"] == f"{group['name']} background"), None)
    if "background" in op:
        value = _paint(op["background"], "background")
        require(backdrop is not None, "This code was created without a background; add a shape behind it instead",
                field="background")
        color(resolve_color(value, project.state))
        backdrop["fill"] = value
    if backdrop is not None:
        backdrop.update(width=width, height=height)
        group.update(width=width, height=height, content_width=width, content_height=height)


def validate(layer):
    """Structure of a stored code record (document load and every edit)."""
    record = layer["code"]
    require(isinstance(record, dict) and record.get("kind") in ("qr", *SYMBOLOGIES) and isinstance(record.get("data"), str)
            and layer.get("type") == "shape" and layer.get("shape") == "path", "Invalid code layer", "invalid_project")
    require(record.get("error", "M") in ERRORS, "Invalid QR error correction", "invalid_project")
    quiet = record.get("quiet")
    require(quiet is None or (isinstance(quiet, int) and 0 <= quiet <= 40), "Invalid code quiet zone", "invalid_project")


# ---------------------------------------------------------------------------------------------
# Checks


MIN_MM = {"qr": 0.33, "code128": 0.19, "ean13": 0.264}
MIN_PIXELS = 2


def check_codes(candidate, resolved, layers, issue):
    """The ``codes`` check: module size at the export dpi, contrast between modules and background, and a quiet
    zone free of other ink."""
    import numpy as np

    from .colors import contrast_ratio
    from .render import color
    from .spatial import canvas_boxes

    codes = [item for item in layers if item.get("code")]
    if not codes:
        return
    boxes = canvas_boxes(candidate)
    image = np.asarray(candidate.render().convert("RGB"), dtype=float)
    dpi = candidate.state["canvas"].get("dpi")
    for layer in codes:
        record, view = layer["code"], layer["path_view"]
        kind = record["kind"]
        x, y, w, h = boxes[layer["id"]]
        module = w / view[0]
        label = "QR code" if kind == "qr" else {"ean13": "EAN-13 barcode", "code128": "Code 128 barcode"}[kind]
        if dpi:
            size = module / dpi * 25.4
            if size < MIN_MM[kind]:
                issue("codes", "error", f"{layer['name']!r}: modules are {size:.3f} mm at {dpi} dpi; a {label} needs at "
                      f"least {MIN_MM[kind]} mm to scan reliably (make it larger)", [layer], module_mm=round(size, 4))
        elif module < MIN_PIXELS:
            issue("codes", "error", f"{layer['name']!r}: modules are {module:.2f} px; use at least {MIN_PIXELS} px per "
                  "module so screens and cameras can resolve them", [layer], module_px=round(module, 3))
        elif not float(module).is_integer() and module < 4:
            issue("codes", "warning", f"{layer['name']!r}: modules are {module:.2f} px, so their edges blur; use a whole "
                  "number of pixels per module", [layer], module_px=round(module, 3))
        if any(item.get("rotation") or item.get("skew_x") or item.get("skew_y")
               for item in (layer, *_ancestors(layer, resolved))):
            continue  # a turned code still scans; its quiet zone is not an axis-aligned band to sample
        left, top = int(round(x)), int(round(y))
        right, bottom = int(round(x + w)), int(round(y + h))
        if right - left < 4 or bottom - top < 4 or left < 0 or top < 0 or right > image.shape[1] or bottom > image.shape[0]:
            issue("codes", "warning", f"{layer['name']!r} is partly outside the canvas; the quiet zone cannot be checked",
                  [layer])
            continue
        quiet = [q * module for q in _quiet(record, view)]
        region = image[top:bottom, left:right]
        mask = np.zeros(region.shape[:2], dtype=bool)
        inset = 1  # skip the anti-aliased edge of the box and of the symbol
        ql, qt, qr, qb = (int(np.floor(v)) - inset for v in quiet)
        if ql > 0:
            mask[inset:-inset, inset:inset + ql] = True
        if qr > 0:
            mask[inset:-inset, -inset - qr:-inset] = True
        if qt > 0:
            mask[inset:inset + qt, inset:-inset] = True
        if qb > 0:
            mask[-inset - qb:-inset, inset:-inset] = True
        ink = color(layer.get("fill", "black"))
        if not mask.any():
            continue
        ring = region[mask]
        paper = np.median(ring, axis=0)
        ratio = float(contrast_ratio(tuple(paper / 255), tuple(c / 255 for c in ink[:3])))
        if ratio < 3:
            issue("codes", "error", f"{layer['name']!r}: modules and background contrast only {ratio:.1f}:1; scanners "
                  "need dark modules on a light background (aim for 4.5:1 or more)", [layer], contrast=round(ratio, 2))
        elif ratio < 4.5:
            issue("codes", "warning", f"{layer['name']!r}: modules and background contrast {ratio:.1f}:1; aim for 4.5:1",
                  [layer], contrast=round(ratio, 2))
        if sum(ink[:3]) > sum(paper):
            issue("codes", "warning", f"{layer['name']!r} is light on dark; many scanners only read dark modules on a "
                  "light background", [layer])
        stray = np.abs(ring - paper).max(axis=1) > 48
        if stray.mean() > 0.002:
            issue("codes", "error", f"{layer['name']!r}: other ink covers {stray.mean():.1%} of the quiet zone; keep "
                  "the margin around the code clear", [layer], quiet_zone_ink=round(float(stray.mean()), 4))


def _ancestors(layer, resolved):
    while layer.get("parent") and layer["parent"] in resolved:
        layer = resolved[layer["parent"]]
        yield layer


def _quiet(record, view):
    """(left, top, right, bottom) quiet zone in modules."""
    if record["kind"] == "qr":
        q = record.get("quiet", QUIET["qr"])
        return q, q, q, q
    if record.get("quiet") is not None:
        return record["quiet"], 0, record["quiet"], 0
    left, right = QUIET["ean13"] if record["kind"] == "ean13" else (QUIET["code128"],) * 2
    return left, 0, right, 0
