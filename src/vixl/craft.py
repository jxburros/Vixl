"""Fixed craft defaults that every feature shares (house style decisions B3, B4, B6, B7, C5, E2, E8, F4).

These are the values a field falls back to when an operation leaves it out. They are resolved when an
operation runs and stored on the layer or canvas, so changing one here never changes a saved document;
only new layers and new documents pick it up.
"""

# Line height as a multiple of the font size (distance between baselines / size), per text stage.
LINE_HEIGHT = {"display": 1.0, "heading": 1.1, "lead": 1.35, "body": 1.45, "caption": 1.3}
# Safe area for a document whose size defines none, as a fraction of the canvas short side.
SAFE_AREA = 0.05
# Stroke width for a stroke given without a width, as a fraction of the shape's short side.
STROKE_WIDTH = 0.015
# Fill for shapes and solids when the document has no palette role to use.
NEUTRAL_FILL = "#8c8c8c"
# Palette roles that shapes and solids take their fill from, and strokes their colour from.
SHAPE_FILL_ROLE, SOLID_FILL_ROLE, STROKE_ROLE = "accent", "surface", "ink"
# Corner radius per corner style, as a fraction of the shape's short side; the house style is sharp.
CORNERS = {"sharp": 0, "soft": 0.08, "round": 0.25, "pill": 0.5}
CORNER = "sharp"
# Strength of irregular and tear when none is given.
IRREGULAR_STRENGTH = "subtle"


def base_size(canvas):
    """The body text size for a canvas with no type scale: about 2.6% of the short side on screen, and a
    readable point size (7.5–60 pt, growing with the page) for print."""
    short = min(canvas["width"], canvas["height"])
    if canvas.get("dpi"):
        points = min(max(short / canvas["dpi"] * 1.25, 7.5), 60)
        return points * canvas["dpi"] / 72
    return max(short * 0.026, 10)


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
    corner = ((project.state.get("design_defaults") or {}).get("direction") or {}).get("corner")
    return corner if corner in CORNERS else CORNER


def fill_for(project, role):
    """A palette role reference when the document defines that swatch, else the neutral fill."""
    return f"@{role}" if role in (project.state.get("swatches") or {}) else NEUTRAL_FILL


def stroke_color(project):
    if STROKE_ROLE in (project.state.get("swatches") or {}):
        return f"@{STROKE_ROLE}"
    from .operations import default_ink

    return default_ink(project)


def stroke_width(width, height):
    return max(1, round(min(width, height) * STROKE_WIDTH))


def safe_area(width, height):
    return round(min(width, height) * SAFE_AREA)


def _visible(value):
    return str(value).strip().lower() not in ("", "none", "transparent", "#0000", "#00000000")


def shape_defaults(project, op, fields, width, height):
    """Fill a new shape's fill, stroke and corner from the document direction and report what was filled in.

    Closed shapes take ``@accent`` (else the neutral fill); a stroke without a width gets one proportional to
    the shape, and a width without a colour gets ``@ink``. An open shape (geometry.OPEN_SHAPES or a path with
    no Z) with neither fill nor stroke is drawn as an ``@ink`` stroke and stays unfilled (geometry.default_fill).
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
        fields["fill"] = filled["fill"] = fill_for(project, SHAPE_FILL_ROLE)
    if stroked and "stroke_width" not in op:
        fields["stroke_width"] = filled["stroke_width"] = max(1, round(reference * STROKE_WIDTH))
    elif "stroke" not in op and "stroke" not in fields and op.get("stroke_width", 0) > 0:
        fields["stroke"] = filled["stroke"] = stroke_color(project)
    if op.get("shape") == "rounded-rectangle" and "radius" not in op:
        corner = corner_style(project)
        fields["radius"] = filled["radius"] = round(short * CORNERS[corner if CORNERS[corner] else "soft"], 2)
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
            multiple = filled["line_height"] = LINE_HEIGHT[stage]
            filled["stage"] = stage
        layer["line_height"] = finite(multiple, "line_height", 0.5, 5)
        layer["spacing"] = spacing_for(project, layer["font"], layer["size"], multiple)
    check_spacing(layer)
    if filled:
        record(project, "defaults", {"layer": layer["name"], **filled})
