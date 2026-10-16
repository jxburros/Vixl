"""Custom fonts drawn as layers: glyph cells, metrics and TrueType/OpenType/WOFF export.

A document holds one font design (``state["font_design"]``): the family name and naming metadata, vertical
metrics in canvas pixels (``em``, ``ascent``, ``descent``, ``x_height``, ``cap_height``), default side bearing
and space width, kerning pairs, and a glyph map from characters to drawn geometry.

Each glyph has an ``origin`` (the canvas point where its baseline starts) and an ``advance`` (its width in
pixels). Its outlines are either the layers it names (``layers``), or, without a list, every visible vector
layer in its cell: the box from ``origin`` across ``advance`` and from ``ascent`` above the baseline to
``descent`` below it, holding the layer's centre and reaching at most half a cell past it. ``font-grid`` lays
cells out and draws guides, so drawing a glyph is drawing shapes in its cell.

Shapes (their fill and their strokes), pen paths, pathfinder results and plain text layers become outlines;
colour, opacity and effects do not exist in a font. All of a glyph's outlines are merged into one shape
(``booleans.combine_outlines``). One canvas pixel is ``1000 / em`` font units.

``build`` writes TrueType (``ttf``, quadratic ``glyf`` outlines), OpenType CFF (``otf``), WOFF, or WOFF2 (with
the optional ``brotli`` package). ``font-build`` embeds the result in the document under a font name so text
layers can be set in it immediately.
"""

from io import BytesIO
import math
import re
import unicodedata

from ...errors import VixlError, require

TYPES = ("font-design", "font-glyph", "font-grid", "font-build")
FORMATS = ("ttf", "otf", "woff", "woff2")
UNITS_PER_EM = 1000
MAX_GLYPHS = 1024
BUILD_TIMESTAMP = 3818534400  # 2025-01-01 in the font epoch (seconds since 1904)
METRICS = ("em", "ascent", "descent", "line_gap", "x_height", "cap_height", "side_bearing", "space")
TEXT_FIELDS = ("family", "style", "version", "designer", "copyright", "license", "url", "description")
DESIGN_FIELDS = (*TEXT_FIELDS, *METRICS, "weight", "italic_angle", "kerning", "glyphs")
GLYPH_FIELDS = ("layers", "origin", "advance")
SETS = {
    "uppercase": "ABCDEFGHIJKLMNOPQRSTUVWXYZ",
    "lowercase": "abcdefghijklmnopqrstuvwxyz",
    "digits": "0123456789",
    "punctuation": "!\"#$%&'()*+,-./:;<=>?@[\\]^_`{|}~",
}
SETS["letters"] = SETS["uppercase"] + SETS["lowercase"]
SETS["ascii"] = SETS["uppercase"] + SETS["lowercase"] + SETS["digits"] + SETS["punctuation"]
GUIDE = re.compile(r"font-(r\d+-(ascent|cap|x|baseline|descent)|c\d+-(left|right))")
# Vector layers that can become outlines. Anything else in a cell (a reference sketch, a background) is skipped.
VECTOR = ("shape", "pathfinder", "text")


def defaults(em=200):
    return {"em": em, "ascent": em * 0.8, "descent": em * 0.2, "line_gap": 0, "x_height": em * 0.5,
            "cap_height": em * 0.7, "side_bearing": em * 0.05, "space": em * 0.25}


def schemas(add):
    from ...schema import S, N, B, field

    px = {"type": "number", "minimum": 0, "maximum": 100000}
    text = {"type": "string", "maxLength": 500}
    point = {"type": "array", "items": N, "minItems": 2, "maxItems": 2}
    add("font-design", {
        "family": field(text, "Font family name, as apps list it (default none: font-build and font export "
                              "need one)."),
        "style": field(text, "Style name (default Regular); Bold, Italic or Bold Italic set the style flags."),
        "em": field(px, "The em in canvas pixels, the font's size unit (default 200). One pixel is 1000/em "
                        "font units. Changing it does not move cells laid out by font-grid."),
        "ascent": field(px, "Height above the baseline that lines reserve, in pixels (default 0.8 em)."),
        "descent": field(px, "Depth below the baseline that lines reserve, in pixels (default 0.2 em)."),
        "line_gap": field(px, "Extra space between lines, in pixels (default 0)."),
        "x_height": field(px, "Height of lowercase x, in pixels (default 0.5 em): a guide and a font metric."),
        "cap_height": field(px, "Height of capitals, in pixels (default 0.7 em): a guide and a font metric."),
        "side_bearing": field(px, "Space added left and right of a glyph whose advance is not given (default "
                                  "0.05 em)."),
        "space": field(px, "Advance of the space character when no glyph draws it (default 0.25 em)."),
        "weight": {"type": "integer", "minimum": 1, "maximum": 1000,
                   "description": "Weight class, 100 (thin) to 900 (black); default 400, or 700 for a Bold style."},
        "italic_angle": {"type": "number", "minimum": -90, "maximum": 90,
                         "description": "Slant in degrees, negative leaning right as in fonts (default 0)."},
        "version": field(text, "Font version such as 1.000 (default 1.000)."),
        "designer": field(text, "Designer name, written to the font's name table."),
        "copyright": field(text, "Copyright notice."),
        "license": field(text, "License description, such as SIL Open Font License 1.1."),
        "url": field(text, "Designer or vendor URL."),
        "description": field(text, "A short description of the font."),
        "kerning": {"type": "object", "maxProperties": 4096,
                    "additionalProperties": {"type": "number", "minimum": -10000, "maximum": 10000},
                    "description": "Kerning pairs: two characters → an adjustment in pixels (negative pulls them "
                                   "together), e.g. {\"AV\": -12}. Merged into the existing pairs; 0 removes one."},
    })
    add("font-glyph", {
        "char": field(S, "The character the glyph draws: one character, or a code point such as U+E001."),
        "targets": {"type": "array", "items": S, "minItems": 1, "maxItems": 512,
                    "description": "Layers (groups include their visible children) whose outlines make the glyph. "
                                   "Without target or targets the glyph uses the layers in its cell."},
        "origin": field(point, "Canvas [x, y] where the glyph's baseline starts. Default with layers: the left "
                               "of their outlines less the side bearing, on their bottom edge."),
        "advance": field(px, "Advance width in pixels. Default: the outlines' width plus a side bearing each "
                             "side (or up to their right edge plus one, with an origin)."),
        "remove": field(B, "true removes the glyph for char."),
    }, ["char"])
    add("font-grid", {
        "chars": {"type": "string", "minLength": 1, "maxLength": MAX_GLYPHS,
                  "description": "Characters to make cells for, in order; or a set name: uppercase, lowercase, "
                                 "letters, digits, punctuation, ascii."},
        "columns": {"type": "integer", "minimum": 1, "maximum": 64,
                    "description": "Cells per row (default up to 10)."},
        "advance": field(px, "Cell width in pixels, the glyphs' advance (default 0.6 em)."),
        "gap": field(px, "Space between cells, in pixels (default 0.25 em)."),
        "x": field(N, "Left of the first cell (default the gap)."),
        "y": field(N, "Top of the first row (default the gap)."),
        "guides": field(B, "Draw ascent, cap-height, x-height, baseline and descent guides per row and cell edges "
                           "per column (default true)."),
    }, ["chars"])
    add("font-build", {
        "name": field(S, "Register the built font under this name for text layers (default the family as "
                         "letters, digits and hyphens)."),
        "format": {"enum": ["ttf", "otf"], "description": "Outline format of the embedded font (default ttf)."},
    })


def design(state):
    return state.get("font_design") or {}


def metrics(state):
    record = design(state)
    values = defaults(record.get("em", 200))
    values.update({key: record[key] for key in METRICS if key in record})
    return values


def character(value):
    """The character ``value`` names: itself, or ``U+XXXX``."""
    require(isinstance(value, str) and value, "char is one character or a code point such as U+E001", field="char")
    match = re.fullmatch(r"[Uu]\+([0-9A-Fa-f]{4,6})", value)
    if match:
        point = int(match.group(1), 16)
        require(point <= 0x10FFFF, "Code points stop at U+10FFFF", field="char")
        value = chr(point)
    require(len(value) == 1, f"char is one character, not {value!r}; give each character its own font-glyph",
            field="char")
    category = unicodedata.category(value)
    require(category not in ("Cc", "Cs", "Cn") or 0xE000 <= ord(value) <= 0xF8FF,
            f"U+{ord(value):04X} is a control, surrogate or unassigned code point", field="char")
    return value


def glyph_name(char):
    from fontTools.agl import UV2AGL

    if char == " ":
        return "space"
    point = ord(char)
    return UV2AGL.get(point) or (f"uni{point:04X}" if point <= 0xFFFF else f"u{point:05X}")


def execute(project, op):
    kind = op["type"]
    state = project.state
    if kind == "font-design":
        record = dict(design(state))
        for key in TEXT_FIELDS:
            if key in op:
                value = op[key].strip()
                if value:
                    record[key] = value
                else:
                    record.pop(key, None)
        for key in (*METRICS, "weight", "italic_angle"):
            if key in op:
                record[key] = op[key]
        require(record.get("em", 200) > 0, "em must be above 0", field="em")
        if "kerning" in op:
            pairs = dict(record.get("kerning", {}))
            for pair, value in op["kerning"].items():
                require(isinstance(pair, str) and len(pair) == 2,
                        f"Kerning pairs are two characters, not {pair!r}", field="kerning")
                if value:
                    pairs[pair] = value
                else:
                    pairs.pop(pair, None)
            record["kerning"] = pairs
        state["font_design"] = record
        return
    if kind == "font-glyph":
        char = character(op["char"])
        record = dict(design(state))
        glyphs = dict(record.get("glyphs", {}))
        if op.get("remove"):
            require(char in glyphs, f"The font has no glyph for {char!r}", field="char")
            glyphs.pop(char)
        else:
            refs = op.get("targets") or ([op["target"]] if op.get("target") else [])
            entry = dict(glyphs.get(char, {}))
            if refs:
                ids = [project.layer(ref)["id"] for ref in refs]
                require(len(set(ids)) == len(ids), "targets names a layer twice", field="targets")
                entry["layers"] = ids
                if "origin" not in op and "origin" not in glyphs.get(char, {}):
                    entry.pop("advance", None)
            if "origin" in op:
                entry["origin"] = [float(v) for v in op["origin"]]
            if "advance" in op:
                entry["advance"] = op["advance"]
            require(entry.get("layers") or "origin" in entry,
                    f"Give the glyph for {char!r} its layers (target or targets) or a cell (origin and advance)",
                    field="targets")
            require("layers" in entry or "advance" in entry,
                    "A glyph drawn from its cell needs an advance (its cell width)", field="advance")
            glyphs[char] = entry
            require(len(glyphs) <= MAX_GLYPHS, f"A font holds at most {MAX_GLYPHS} glyphs", "resource_limit")
        record["glyphs"] = glyphs
        state["font_design"] = record
        return
    if kind == "font-grid":
        grid(project, op)
        return
    if kind == "font-build":
        import hashlib

        record = design(state)
        name = op.get("name") or re.sub(r"[^\w-]+", "-", record.get("family", "")).strip("-")
        require(name, "Name the font first: font-design family=NAME", field="name")
        from ...design import named

        named(name)
        data = build(project, op.get("format", "ttf"))
        asset = f"fonts/{hashlib.sha256(data).hexdigest()}.ttf"
        project.assets[asset] = data
        from ...resources import execute_resource

        execute_resource(project, {"type": "font-register", "name": name, "asset": asset})
        return
    raise VixlError("invalid_operation", f"Unknown font operation {kind}")


def grid(project, op):
    state = project.state
    chars = SETS.get(op["chars"], op["chars"])
    chars = "".join(dict.fromkeys(chars))  # each character once, in order
    for char in chars:
        character(char)
    record = dict(design(state))
    m = metrics(state)
    em = m["em"]
    advance = op.get("advance", round(em * 0.6, 3))
    require(advance > 0, "advance must be above 0", field="advance")
    gap = op.get("gap", round(em * 0.25, 3))
    columns = op.get("columns", min(10, len(chars)))
    rows = math.ceil(len(chars) / columns)
    left, top = op.get("x", gap), op.get("y", gap)
    height = m["ascent"] + m["descent"]
    right, bottom = left + columns * advance + (columns - 1) * gap, top + rows * height + (rows - 1) * gap
    canvas = state["canvas"]
    require(right <= canvas["width"] and bottom <= canvas["height"],
            f"The grid needs a canvas of at least {math.ceil(right + gap)}×{math.ceil(bottom + gap)} px; resize it "
            "(canvas operation) or change columns, advance or gap", field="chars")
    glyphs = dict(record.get("glyphs", {}))
    for i, char in enumerate(chars):
        row, column = divmod(i, columns)
        x = left + column * (advance + gap)
        baseline = top + row * (height + gap) + m["ascent"]
        glyphs[char] = {"origin": [x, baseline], "advance": advance}
    require(len(glyphs) <= MAX_GLYPHS, f"A font holds at most {MAX_GLYPHS} glyphs", "resource_limit")
    record["glyphs"] = glyphs
    state["font_design"] = record
    guides = {name: guide for name, guide in state.get("guides", {}).items() if not GUIDE.fullmatch(name)}
    if op.get("guides", True):
        for row in range(rows):
            baseline = top + row * (height + gap) + m["ascent"]
            for label, offset in (("ascent", -m["ascent"]), ("cap", -m["cap_height"]), ("x", -m["x_height"]),
                                  ("baseline", 0), ("descent", m["descent"])):
                guides[f"font-r{row + 1}-{label}"] = {"axis": "y", "position": baseline + offset}
        for column in range(columns):
            x = left + column * (advance + gap)
            guides[f"font-c{column + 1}-left"] = {"axis": "x", "position": x}
            guides[f"font-c{column + 1}-right"] = {"axis": "x", "position": x + advance}
        from ...guides import MAX_GUIDES

        require(len(guides) <= MAX_GUIDES, f"The document would hold more than {MAX_GUIDES} guides; pass "
                "guides=false", "resource_limit", field="guides")
    state["guides"] = guides


def validate(project, state):
    record = state.get("font_design")
    if record is None:
        return
    require(isinstance(record, dict) and set(record) <= set(DESIGN_FIELDS), "Invalid font design", "invalid_project")
    for key in TEXT_FIELDS:
        require(isinstance(record.get(key, ""), str), f"Invalid font design {key}", "invalid_project")
    for key in (*METRICS, "weight", "italic_angle"):
        value = record.get(key, 0)
        require(isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value),
                f"Invalid font design {key}", "invalid_project")
    kerning = record.get("kerning", {})
    require(isinstance(kerning, dict) and all(isinstance(k, str) and len(k) == 2 and isinstance(v, (int, float))
                                              for k, v in kerning.items()), "Invalid font kerning", "invalid_project")
    glyphs = record.get("glyphs", {})
    require(isinstance(glyphs, dict) and len(glyphs) <= MAX_GLYPHS, "Invalid font glyphs", "invalid_project")
    for char, entry in glyphs.items():
        require(isinstance(char, str) and len(char) == 1 and isinstance(entry, dict)
                and set(entry) <= set(GLYPH_FIELDS), "Invalid font glyph", "invalid_project")
        require(isinstance(entry.get("layers", []), list) and all(isinstance(i, str) for i in entry.get("layers", [])),
                "Invalid font glyph layers", "invalid_project")
        origin = entry.get("origin", [0, 0])
        require(isinstance(origin, list) and len(origin) == 2 and all(isinstance(v, (int, float)) for v in origin),
                "Invalid font glyph origin", "invalid_project")


# --------------------------------------------------------------------------------------------- outlines


def _paints(project, value):
    from ...design import resolve_color
    from ...render import color

    if isinstance(value, dict):
        return True
    if value is None or str(value).strip().lower() in ("", "none", "transparent"):
        return False
    return color(resolve_color(value, project.state))[3] > 0


def _local_contours(project, item):
    """Closed contours of a vector layer's drawn area, in its own pixels (0…width, 0…height)."""
    from ...booleans import Unsupported
    from ...geometry import default_fill, parse_path
    from ...pathfinder_geometry import _from_commands, pathfinder_outline, shape_contours

    kind = item["type"]
    for key, what in (("mask", "a mask"), ("clip", "clipping"), ("repeat", "a repeat")):
        require(not item.get(key), f"Layer {item['name']!r} has {what}, which a glyph outline cannot keep; "
                "combine its shapes with pathfinder instead", field="targets")
    if kind == "shape":
        contours = []
        if item.get("shape") != "line" and _paints(project, default_fill(item)):
            contours += shape_contours(item)
        stroked = [style for style in [{"color": item.get("stroke", "transparent"),
                                        "width": item.get("stroke_width", 1)}, *item.get("strokes", [])]
                   if style.get("width", 1) > 0 and _paints(project, style.get("color"))]
        if stroked or item.get("shape") == "line":
            from ...vector_paths import pixel_path
            from ...vector_strokes import expanded

            for d, paint in expanded(item, pixel_path(item, False)):
                if d and _paints(project, paint):
                    contours += _from_commands(parse_path(d), 1, 1)
        return contours
    if kind == "pathfinder":
        try:
            return pathfinder_outline(item, project.state)
        except Unsupported as exc:
            raise VixlError("invalid_operation", f"Pathfinder {item['name']!r} cannot become a glyph outline: {exc}",
                            field="targets") from exc
    from ...richtext import active
    from ...text import UnsupportedText, plan

    require(not active(item), f"Rich text {item['name']!r} cannot become a glyph outline; use a plain text layer",
            field="targets")
    try:
        layout = plan(project, item)
    except UnsupportedText as exc:
        raise VixlError("invalid_operation", f"Text {item['name']!r} cannot become a glyph outline: {exc}",
                        field="targets") from exc
    sx, sy = item["width"] / max(1e-6, layout.width), item["height"] / max(1e-6, layout.height)
    contours = []
    for path, (a, b, c, d, e, f) in layout.paths:
        require(isinstance(path, str), f"Text {item['name']!r} draws a colour emoji, which an outline font cannot "
                "hold", field="targets")
        for contour in _from_commands(parse_path(path), 1, 1):
            contours.append([tuple(((a * x + c * y + e) * sx, (b * x + d * y + f) * sy) for x, y in seg)
                             for seg in contour])
    return contours


class Scene:
    """The resolved layers of a document with their canvas transforms, shared by every glyph of one build."""

    def __init__(self, project):
        from ...render import resolve_layout, resolved_layers

        self.project = project
        self.layers = resolved_layers(project)
        self.index = {item["id"]: item for item in self.layers}
        self.local = resolve_layout(project, layers=self.layers)
        self.children = {}
        for item in self.layers:
            self.children.setdefault(item.get("parent"), []).append(item)
        self._boxes = None

    def shown(self, item):
        while item is not None:
            if not item.get("visible", True) or item.get("opacity", 1) <= 0:
                return False
            item = self.index.get(item.get("parent"))
        return True

    def matrix(self, item):
        from ...affine import layer_matrix
        from ...checks import group_matrix

        return group_matrix(item, self.index, self.local) @ layer_matrix(item, self.local[item["id"]])

    def leaves(self, item):
        """``item`` itself, or a group's visible descendants that draw."""
        if item["type"] != "group":
            return [item]
        return [leaf for child in self.children.get(item["id"], []) if child.get("visible", True)
                for leaf in self.leaves(child)]

    def contours(self, item):
        """Canvas-space contours of a layer (y down), or an error naming it when it is not vector art."""
        require(item["type"] in VECTOR, f"Layer {item['name']!r} is a {item['type']} layer; glyphs are made of "
                "shapes, paths, pathfinder results and text (turn a scan into paths with drawing vectorize)", field="targets")
        transform = self.matrix(item)

        def move(p):
            x, y, _ = transform @ [p[0], p[1], 1]
            return float(x), float(y)

        return [[tuple(move(p) for p in seg) for seg in contour] for contour in _local_contours(self.project, item)]

    def boxes(self):
        if self._boxes is None:
            from ...spatial import canvas_boxes

            self._boxes = canvas_boxes(self.project, layers=self.layers, local=self.local)
        return self._boxes


def _cell_layers(scene, origin, advance, m, claimed, warnings, char):
    ox, oy = origin
    top, bottom = oy - m["ascent"], oy + m["descent"]
    height = bottom - top
    found = []
    for item in scene.layers:
        if item["type"] == "group" or item["id"] in claimed or not scene.shown(item):
            continue
        if item.get("role") in ("background", "decoration"):
            continue
        x, y, w, h = scene.boxes()[item["id"]]
        cx, cy = x + w / 2, y + h / 2
        inside = ox <= cx < ox + advance and top <= cy < bottom
        reach = (x >= ox - advance / 2 and x + w <= ox + advance * 1.5 and y >= top - height / 2
                 and y + h <= bottom + height / 2)
        if not (inside and reach):
            continue
        if item["type"] not in VECTOR:
            warnings.append(f"Glyph {char!r}: skipped {item['type']} layer {item['name']!r} (only vector layers "
                            "become outlines)")
            continue
        found.append(item)
    return found


def _merge(parts, char):
    """One clean outline (no overlaps, outer contours one way and holes the other) from per-layer contours."""
    from ...booleans import Unsupported, combine_outlines

    parts = [part for part in parts if part]
    if not parts:
        return []
    try:
        return combine_outlines(parts, lambda *inside: any(inside))
    except Unsupported:
        pass
    try:  # too many segments to merge at once: clean each layer and let the overlaps stand
        return [contour for part in parts for contour in combine_outlines([part], lambda inside: inside)]
    except Unsupported as exc:
        raise VixlError("resource_limit", f"Glyph {char!r} is too detailed to outline ({exc}); simplify its paths "
                        "with path-simplify", field="char") from exc


def glyph_outlines(project, scene=None, warnings=None):
    """``{char: (contours in font units, advance in font units)}`` for every glyph of the design. Contours are
    lists of segments ((p0, p1) lines and (p0, c1, c2, p3) cubics), y up, outer contours clockwise."""
    state = project.state
    record = design(state)
    m = metrics(state)
    scale = UNITS_PER_EM / m["em"]
    scene = scene or Scene(project)
    warnings = [] if warnings is None else warnings
    glyphs = record.get("glyphs", {})
    claimed = {ident for entry in glyphs.values() for ident in entry.get("layers", [])}
    result = {}
    for char, entry in glyphs.items():
        if entry.get("layers"):
            items = []
            for ident in entry["layers"]:
                if ident not in scene.index:
                    warnings.append(f"Glyph {char!r}: a layer it used was deleted")
                    continue
                if scene.shown(scene.index[ident]):
                    items += [leaf for leaf in scene.leaves(scene.index[ident]) if leaf["type"] != "group"]
        else:
            items = _cell_layers(scene, entry["origin"], entry["advance"], m, claimed, warnings, char)
        outline = _merge([scene.contours(item) for item in items], char)
        xs = [p[0] for contour in outline for seg in contour for p in seg]
        ys = [p[1] for contour in outline for seg in contour for p in seg]
        bearing = m["side_bearing"]
        if "origin" in entry:
            ox, oy = entry["origin"]
        elif xs:
            ox, oy = min(xs) - bearing, max(ys)
        else:
            ox, oy = 0, 0
        if "advance" in entry:
            advance = entry["advance"]
        elif xs:
            advance = max(xs) - ox + bearing
        else:
            advance = m["space"]
        if not outline and char != " " and not unicodedata.category(char).startswith("Z"):
            warnings.append(f"Glyph {char!r} draws nothing")
        result[char] = ([[tuple(((x - ox) * scale, (oy - y) * scale) for x, y in seg) for seg in contour]
                         for contour in outline], max(0, advance * scale))
    return result


# ------------------------------------------------------------------------------------------------ build


def _draw(contours, pen):
    for contour in contours:
        pen.moveTo(_int(contour[0][0]))
        for i, seg in enumerate(contour):
            if len(seg) == 2:
                if i < len(contour) - 1 or _int(seg[1]) != _int(contour[0][0]):
                    pen.lineTo(_int(seg[1]))
            else:
                pen.curveTo(*(_int(p) for p in seg[1:]))
        pen.closePath()


def _int(point):
    return round(point[0]), round(point[1])


def _notdef(m, scale):
    """A hollow box, the conventional missing-glyph mark."""
    width, height = round(m["em"] * 0.5 * scale), round(m["cap_height"] * scale)
    inset, line = round(UNITS_PER_EM * 0.05), round(UNITS_PER_EM * 0.05)
    x0, x1, y0, y1 = inset, width - inset, 0, height

    def box(a, b, c, d, clockwise):
        points = [(a, c), (a, d), (b, d), (b, c)] if clockwise else [(a, c), (b, c), (b, d), (a, d)]
        return [(p, q) for p, q in zip(points, points[1:] + points[:1])]

    return [box(x0, x1, y0, y1, True), box(x0 + line, x1 - line, y0 + line, y1 - line, False)], width


def _style_flags(style):
    words = style.lower().split()
    return "bold" in words, bool({"italic", "oblique"} & set(words))


def build(project, format="ttf", report=None):
    """Font file bytes of the document's font design: ``ttf``, ``otf``, ``woff`` or ``woff2``. ``report``
    receives the family, glyph count, characters and warnings."""
    from fontTools.fontBuilder import FontBuilder
    from fontTools.pens.cu2quPen import Cu2QuPen
    from fontTools.pens.reverseContourPen import ReverseContourPen
    from fontTools.pens.t2CharStringPen import T2CharStringPen
    from fontTools.pens.ttGlyphPen import TTGlyphPen

    require(format in FORMATS, f"Font format must be one of {', '.join(FORMATS)}", field="format")
    state = project.state
    record = design(state)
    family = record.get("family")
    require(family, "Name the font first: font-design family=NAME", field="family")
    require(record.get("glyphs"), "The font has no glyphs; lay out cells with font-grid or map layers with "
            "font-glyph", field="glyphs")
    m = metrics(state)
    scale = UNITS_PER_EM / m["em"]
    warnings = []
    outlines = glyph_outlines(project, warnings=warnings)
    if " " not in outlines:
        outlines[" "] = ([], m["space"] * scale)
    order, cmap, shapes, advances = [".notdef"], {}, {".notdef": _notdef(m, scale)[0]}, {".notdef": _notdef(m, scale)[1]}
    for char in sorted(outlines, key=ord):
        name = glyph_name(char)
        contours, advance = outlines[char]
        order.append(name)
        cmap[ord(char)] = name
        shapes[name], advances[name] = contours, round(advance)
    if 0xA0 not in cmap:
        cmap[0xA0] = "space"  # a no-break space looks like a space
    style = record.get("style", "Regular")
    bold, italic = _style_flags(style)
    postscript = re.sub(r"[^A-Za-z0-9-]", "", f"{family}-{style}".replace(" ", ""))[:63] or "Font-Regular"
    truetype = format != "otf"
    fb = FontBuilder(UNITS_PER_EM, isTTF=truetype)
    fb.setupGlyphOrder(order)
    fb.setupCharacterMap(cmap)
    if truetype:
        glyphs = {}
        for name in order:
            pen = TTGlyphPen(None)
            _draw(shapes[name], Cu2QuPen(pen, max_err=1.0, reverse_direction=False))
            glyphs[name] = pen.glyph()
        fb.setupGlyf(glyphs)
        table = fb.font["glyf"]
        lsb = {name: getattr(table[name], "xMin", 0) for name in order}
    else:
        charstrings = {}
        for name in order:
            pen = T2CharStringPen(advances[name], None)
            _draw(shapes[name], ReverseContourPen(pen))  # PostScript outer contours run counter-clockwise
            charstrings[name] = pen.getCharString()
        fb.setupCFF(postscript, {"FullName": f"{family} {style}", "FamilyName": family, "Weight": style},
                    charstrings, {})
        lsb = {}
        for name, charstring in charstrings.items():
            bounds = charstring.calcBounds(None)
            lsb[name] = round(bounds[0]) if bounds else 0
    fb.setupHorizontalMetrics({name: (advances[name], lsb[name]) for name in order})
    ascent, descent = round(m["ascent"] * scale), round(m["descent"] * scale)
    gap = round(m["line_gap"] * scale)
    fb.setupHorizontalHeader(ascent=ascent, descent=-descent, lineGap=gap)
    version = record.get("version", "1.000")
    names = {"familyName": family, "styleName": style, "fullName": f"{family} {style}", "psName": postscript,
             "uniqueFontIdentifier": f"{version};{postscript}", "version": f"Version {version}"}
    for key, field_name in (("copyright", "copyright"), ("designer", "designer"), ("license", "licenseDescription"),
                            ("url", "designerURL"), ("description", "description")):
        if record.get(key):
            names[field_name] = record[key]
    fb.setupNameTable(names)
    ys = [p[1] for contours in shapes.values() for contour in contours for seg in contour for p in seg]
    selection = (0x20 if bold else 0) | (0x01 if italic else 0) or 0x40
    fb.setupOS2(sTypoAscender=ascent, sTypoDescender=-descent, sTypoLineGap=gap,
                usWinAscent=max(ascent, round(max(ys, default=0))), usWinDescent=max(descent, -round(min(ys, default=0))),
                sxHeight=round(m["x_height"] * scale), sCapHeight=round(m["cap_height"] * scale),
                usWeightClass=record.get("weight", 700 if bold else 400), fsType=0, fsSelection=selection,
                achVendID="NONE", version=4)
    fb.font["head"].macStyle = (1 if bold else 0) | (2 if italic else 0)
    # A fixed date keeps the bytes (and the embedded asset's hash) the same for the same design.
    fb.font["head"].created = fb.font["head"].modified = BUILD_TIMESTAMP
    fb.font.recalcTimestamp = False
    fb.font["OS/2"].recalcUnicodeRanges(fb.font)
    if hasattr(fb.font["OS/2"], "recalcCodePageRanges"):
        fb.font["OS/2"].recalcCodePageRanges(fb.font)
    fb.setupPost(italicAngle=record.get("italic_angle", 0), keepGlyphNames=True)
    pairs = []
    for pair, value in sorted(record.get("kerning", {}).items()):
        left, right = (glyph_name(c) if c in outlines else None for c in pair)
        if left and right:
            pairs.append(f"    pos {left} {right} {round(value * scale)};")
        else:
            warnings.append(f"Kerning pair {pair!r} names a character the font does not draw")
    if pairs:
        fb.addOpenTypeFeatures("feature kern {\n" + "\n".join(pairs) + "\n} kern;\n")
    if format in ("woff", "woff2"):
        if format == "woff2":
            try:
                import brotli  # noqa: F401
            except ImportError as exc:
                raise VixlError("missing_dependency", "WOFF2 needs the brotli package (pip install brotli); export "
                                ".woff or .ttf instead", field="format") from exc
        fb.font.flavor = format
    stream = BytesIO()
    fb.font.save(stream)
    data = stream.getvalue()
    if report is not None:
        report.update({"family": family, "style": style, "glyphs": len(order),
                       "characters": "".join(sorted(outlines, key=ord)), "units_per_em": UNITS_PER_EM,
                       "kerning_pairs": len(pairs)})
        if warnings:
            report["warnings"] = [*report.get("warnings", []), *warnings]
    return data


def export_font(project, path=None, format=None, report=None):
    """Write the font design to ``path`` (format from ``format`` or the extension) and return the bytes."""
    from pathlib import Path

    format = (format or Path(path).suffix.lstrip(".")).lower()
    data = build(project, format, report)
    if path:
        Path(path).write_bytes(data)
    return data
