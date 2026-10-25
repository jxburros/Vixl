"""Fixed craft defaults that every feature shares (house style decisions B3, B4, B6, B7, C5, E1, E2, E8, F4).

The values live in the ``craft`` section of ``data/house-style.json`` and are read through ``vixl.house_style``;
this module holds the helpers that apply them, plus thin read-only names for the values (``LINE_HEIGHT``,
``CORNERS``, ``SAFE_AREA`` …) that always reflect the data. Defaults are resolved when an operation runs and
stored on the layer or canvas, so changing the data never changes a saved document; only new layers and new
documents pick it up.
"""

from collections.abc import Mapping

from . import house_style


class _Rule(Mapping):
    """A read-only view of one craft table in the house-style data (never a copy, so it cannot go stale)."""

    def __init__(self, key):
        self._key = key

    def __getitem__(self, name):
        return house_style.rule(self._key)[name]

    def __iter__(self):
        return iter(house_style.rule(self._key))

    def __len__(self):
        return len(house_style.rule(self._key))

    def __repr__(self):
        return repr(dict(self))


# Line height as a multiple of the font size (distance between baselines / size), per text stage.
LINE_HEIGHT = _Rule("line_height")
# Corner radius per corner style, as a fraction of the shape's short side.
CORNERS = _Rule("corner_scale")
# Single values: the house corner style, the safe area for a size that defines none and the stroke width
# (fractions of the short side), the fill without a palette, and the irregular/tear strength.
_SCALARS = {"CORNER": "corner", "SAFE_AREA": "safe_area", "STROKE_WIDTH": "stroke_width",
            "NEUTRAL_FILL": "neutral_fill", "IRREGULAR_STRENGTH": "irregular_strength"}
# Palette roles that shapes and solids take their fill from, and strokes their colour from.
_ROLES = {"SHAPE_FILL_ROLE": "shape", "SOLID_FILL_ROLE": "solid", "STROKE_ROLE": "stroke"}


def __getattr__(name):
    if name in _SCALARS:
        return house_style.rule(_SCALARS[name])
    if name in _ROLES:
        return house_style.rule("fill_roles")[_ROLES[name]]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def line_height(stage):
    """The line-height multiple for a text stage (display, heading, lead, body, caption)."""
    return house_style.rule("line_height")[stage]


def corner():
    """The house corner style (decision E8: sharp)."""
    return house_style.rule("corner")


def fill_role(kind):
    """The palette role a ``shape``/``solid`` fill or a ``stroke`` takes."""
    return house_style.rule("fill_roles")[kind]


def spacing_unit(body):
    """The spacing unit for a body size: half the body (craft ``spacing.unit``), never under the minimum."""
    rule = house_style.rule("spacing")
    return max(rule["minimum_unit"], round(body * rule["unit"]))


def space(n, body):
    """A number of shared spacing units (half the body size)."""
    from .model import finite
    return finite(n, "spacing units", 0, 10000) * spacing_unit(body)


def resolve_space(value, body):
    """Explicit pixels or a unit expression such as '2u'."""
    import re
    from .errors import require
    from .model import finite
    if isinstance(value, str):
        require(re.fullmatch(r"\d+(?:\.\d+)?u", value), "Spacing is pixels or a unit expression such as 2u")
        return space(float(value[:-1]), body)
    return finite(value, "spacing", 0, 1000000)


def measure_chars(stage, large=False):
    """Characters a heavy line should hold at least (``display`` or ``heading``), and the glyph width as a
    share of the size, from craft ``headline_measure``; ``large`` is the expressive measure of bold rolls."""
    rule = house_style.rule("headline_measure")
    return rule[("large_" if large else "") + stage], rule["glyph_width"]


def base_size(canvas):
    """The body text size for a canvas with no type scale: about 2.6% of the short side on screen, and a
    readable point size (7.5–60 pt, growing with the page) for print."""
    rule = house_style.rule("base_size")
    short = min(canvas["width"], canvas["height"])
    if canvas.get("dpi"):
        points = min(max(short / canvas["dpi"] * rule["print_points_per_inch_of_short_side"],
                         rule["print_minimum_points"]), rule["print_maximum_points"])
        return points * canvas["dpi"] / 72
    return max(short * rule["screen_share_of_short_side"], rule["screen_minimum_px"])


def body_size(project):
    """The document's body text size: its type scale's ``body`` style, else the canvas rule above."""
    body = (project.state.get("character_styles") or {}).get("body") or {}
    size = body.get("size")
    if isinstance(size, (int, float)) and not isinstance(size, bool) and size > 0:
        return max(1, round(size))
    return max(1, round(base_size(project.state["canvas"])))


def stage_for(size, body):
    """The text stage a size reads as, relative to the body size."""
    ratio = size / max(body, 1)
    if ratio >= 2.8:
        return "display"
    if ratio >= 1.7:
        return "heading"
    if ratio >= 1.15:
        return "lead"
    if ratio <= 0.85:
        return "caption"
    return "body"


def natural_height(data, size):
    """The font's own line pitch (ascent + descent) at ``size``."""
    from .text import face

    outline = face(data)[0]
    return (outline["hhea"].ascent - outline["hhea"].descent) * size / outline["head"].unitsPerEm


def spacing_for(project, font, size, multiple):
    """Plain-text ``spacing`` (pixels added to the font's own pitch) that puts baselines ``multiple`` × size
    apart. Negative for tight display type in fonts with a tall natural pitch."""
    from .text import font_data

    try:
        natural = natural_height(font_data(project, {"font": font, "text": "x"}), size)
    except Exception:  # noqa: BLE001 - A font the outline reader cannot parse keeps the old fixed leading.
        return 4
    return round(size * multiple - natural)


def corner_style(project):
    """The document's corner style: its rolled direction's ``corner``, else the house default."""
    style = ((project.state.get("design_defaults") or {}).get("direction") or {}).get("corner")
    return style if style in CORNERS else corner()


def fill_for(project, role):
    """A palette role reference when the document defines that swatch, else the neutral fill."""
    return f"@{role}" if role in (project.state.get("swatches") or {}) else house_style.rule("neutral_fill")


def stroke_color(project):
    role = fill_role("stroke")
    if role in (project.state.get("swatches") or {}):
        return f"@{role}"
    from .operations import default_ink

    return default_ink(project)


def stroke_width(width, height):
    return max(1, round(min(width, height) * house_style.rule("stroke_width")))


safe_area = house_style.safe_area


def _visible(value):
    return str(value).strip().lower() not in ("", "none", "transparent", "#0000", "#00000000")


def shape_defaults(project, op, fields, width, height):
    """Fill a new shape's fill, stroke and corner from the document direction and report what was filled in.

    Closed shapes take ``@accent`` (else the neutral fill); a stroke without a width gets one proportional to
    the shape, and a width without a colour gets ``@ink``. An open shape (geometry.is_open_shape: OPEN_SHAPES, a path
    with no Z or an arc with closed: false) with neither fill nor stroke is drawn as an ``@ink`` stroke and stays unfilled (geometry.default_fill).
    A rounded rectangle without a radius takes the document's corner style, or soft when that is sharp."""
    from .geometry import is_open_shape
    from .selectors import record

    filled = {}
    short = min(width, height)
    open_shape = is_open_shape({**op, **fields})
    reference = max(width, height) * 0.25 if open_shape or short < max(width, height) * 0.1 else short
    stroked = "stroke" in op and _visible(op["stroke"])
    if open_shape and "fill" not in op and "stroke" not in op:
        fields["stroke"] = filled["stroke"] = stroke_color(project)
        stroked = True
    elif "fill" not in op and not (open_shape and stroked):
        fields["fill"] = filled["fill"] = fill_for(project, fill_role("shape"))
    if stroked and "stroke_width" not in op:
        fields["stroke_width"] = filled["stroke_width"] = max(1, round(reference * house_style.rule("stroke_width")))
    elif "stroke" not in op and "stroke" not in fields and op.get("stroke_width", 0) > 0:
        fields["stroke"] = filled["stroke"] = stroke_color(project)
    if op.get("shape") == "rounded-rectangle" and "radius" not in op:
        style = corner_style(project)
        fields["radius"] = filled["radius"] = round(short * CORNERS[style if CORNERS[style] else "soft"], 2)
    if filled:
        record(project, "defaults", {"layer": op.get("name"), **filled})


def check_spacing(layer):
    """Line spacing may be negative for tight display type, but never so tight that lines run backwards."""
    from .model import finite

    finite(layer.get("spacing", 4), "spacing", -float(layer.get("size", 48)), 1000)


def text_defaults(project, layer, op):
    """Fill a new text layer's size and leading from the type scale and the line-height table, and report
    what was filled in."""
    from .model import finite
    from .selectors import record

    filled = {}
    body = body_size(project)
    if "size" in op:
        layer["size"] = op["size"]
    else:
        layer["size"] = filled["size"] = body
    if "spacing" in op:
        layer["spacing"] = op["spacing"]
    else:
        multiple = op.get("line_height")
        if multiple is None:
            stage = stage_for(layer["size"], body)
            multiple = filled["line_height"] = line_height(stage)
            filled["stage"] = stage
        layer["line_height"] = finite(multiple, "line_height", 0.5, 5)
        layer["spacing"] = spacing_for(project, layer["font"], layer["size"], multiple)
    check_spacing(layer)
    if filled:
        record(project, "defaults", {"layer": layer["name"], **filled})


def illustration_on(project, choice=None):
    """Whether a new illustrated form (an organic shape, an ``object-plan`` scaffold) gets the house illustration
    finish. ``choice`` is the operation's ``illustration``: ``plain`` never, ``house`` always, and without it a
    document that has design defaults which are not ``house_style: "off"`` (a bare ``Project(width, height)`` has none)."""
    if choice in ("plain", "house"):
        return choice == "house"
    defaults = project.state.get("design_defaults") if project is not None else None
    return bool(defaults) and defaults.get("house_style") != house_style.OFF


def illustration_style(project, box, rng):
    """The house illustration finish for one object drawn in ``box`` ([x, y, width, height]): ``stroke`` (ink) and
    ``stroke_width`` of the part lines (``craft.illustration.outline``: its width share of the box's larger side) under the
    ``policy`` (parts), ``shadow`` (the settings of a hard ``drop-shadow``: blur 0, ink colour, offset cast away from
    the light), ``irregular`` (the strength and effects of the wobble; ``wobble_element`` is the smallest element, in
    pixels, a layer that holds many should have to be wobbled) and ``strokes``, the extra lines inside the outline:
    usually none, with the data's probability one or two ``{gap, width}`` lines, drawn from ``rng`` (a
    ``random.Random``) so a seed decides them. ``gap`` is the space between the outline's inner edge (or the previous
    line) and the line."""
    from .geometry import ANCHORS, canonical_anchor

    rule = house_style.illustration()
    outline, shadow, extra = rule["outline"], rule["shadow"], rule["extra_lines"]
    larger = max(float(box[2]), float(box[3]), 1.0)
    ink = stroke_color(project)
    width = max(outline["minimum"], round(larger * outline["width_share"], 2))
    cast = None
    if shadow["kind"] != "none":
        light = ANCHORS[canonical_anchor(rule["light"] if shadow["angle_from"] == "light" else shadow["angle_from"])]
        vx, vy = 0.5 - light[0], 0.5 - light[1]
        scale = max(abs(vx), abs(vy))
        vx, vy = (vx / scale, vy / scale) if scale else (0.0, 1.0)
        distance = larger * shadow["distance_share"]
        cast = {"color": ink, "dx": round(distance * vx, 2), "dy": round(distance * vy, 2), "blur": 0,
                "opacity": shadow["opacity"]}
    strokes = []
    if rng.random() < extra["probability"]:
        gap = max(outline["minimum"], round(larger * extra["offset_share"], 2))
        line = max(outline["minimum"], round(width * extra["width"], 2))
        strokes = [{"gap": gap, "width": line} for _ in range(rng.randint(*extra["count"]))]
    wobble = {key: value for key, value in rule["irregular"].items() if key != "element_widths"}
    return {"policy": outline["policy"], "stroke": ink, "stroke_width": width, "shadow": cast, "irregular": wobble,
            "wobble_element": round(rule["irregular"]["element_widths"] * width, 2), "strokes": strokes}


def illustration_small(width, element):
    """Whether a part ``element`` pixels across is too small for part lines ``width`` wide: its line would have to be
    under half that width (``illustration_part_width``). A flat illustration draws an eye or a spot without an outline."""
    return element * house_style.rule("illustration")["outline"]["element_share"] < width / 2


def illustration_part_width(width, element):
    """The part-line width for a part whose elements are about ``element`` pixels across: ``width``, but at most the
    data's ``element_share`` of the element, so a seed head or a spot is not drowned by the outline of a petal."""
    outline = house_style.rule("illustration")["outline"]
    return round(min(width, max(outline["minimum"], element * outline["element_share"])), 2)
