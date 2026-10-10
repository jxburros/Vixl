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
    except Exception:  # A font the outline reader cannot parse keeps the old fixed leading.
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


def safe_area(width, height):
    return round(min(width, height) * house_style.rule("safe_area"))


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
