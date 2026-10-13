"""Closed-shape stroke geometry: from "inset by half the stroke, stroked inward" to "inside and flush".

Up to 0.26 a plain rectangle, rounded rectangle, capsule or ellipse with a stroke of width ``s`` was drawn as the
shape inset by ``s`` with the stroke centred on that outline, so the ink ran from ``s/2`` to ``3s/2`` inside the box
and the outer edge of the ink had the corner radius ``radius``. The flush model draws the ink from the box edge to
``s`` inside it, with the outer corner radius equal to ``radius``. Moving the box in by ``s/2`` on every side and
keeping the radius puts the ink exactly where it was. Polygons and stars already drew their ink from the edge to
``s``, and lines, arcs and paths keep their geometry, so only the four box shapes move.

Styled strokes (dashes, extra strokes, width profiles ...) on closed shapes were centred on the box edge by default;
the flush model draws every closed shape's stroke inside unless ``stroke_align`` says otherwise, so a styled stroke
that relied on the old default gets an explicit ``stroke_align: "center"``.
"""

from functools import lru_cache
import io

BOX_SHAPES = ("rectangle", "rounded-rectangle", "capsule", "ellipse")
# The radius rounded rectangles take when none is stored: a fifth of the short side (shape_catalog).
DEFAULT_RADIUS = {"rounded-rectangle": 0.2}
# Animated properties that move or resize the box: the converter cannot shift keyframes for them.
GEOMETRY_TRACKS = ("x", "y", "width", "height", "radius", "scale", "scale_x", "scale_y", "stroke_width")


@lru_cache(maxsize=None)
def engine_model():
    """``"flush"`` when the running Vixl draws a closed shape's stroke from the box edge inward, ``"inset"`` when it
    still insets the shape by half the stroke first. Measured on a tiny render, so the kit follows whichever renderer
    is installed."""
    from PIL import Image

    from ..project import Project

    probe = Project(40, 40)
    probe.apply([{"type": "shape", "shape": "rectangle", "x": 0, "y": 0, "width": 40, "height": 40,
                  "fill": "transparent", "stroke": "#000000", "stroke_width": 10}])
    image = Image.open(io.BytesIO(probe.export(format="PNG"))).convert("RGBA")
    return "flush" if image.getpixel((2, 20))[3] > 128 else "inset"


def stroke_visible(project, layer):
    width = layer.get("stroke_width", 1)
    stroke = layer.get("stroke", "transparent")
    if not isinstance(width, (int, float)) or width <= 0 or stroke in (None, "", "none", "transparent"):
        return False
    try:
        from ..design import resolve_color
        from ..render import color

        return color(resolve_color(stroke, project.state))[3] > 0
    except Exception:  # noqa: BLE001 - an unresolvable colour still draws something
        return True


def styled(layer):
    from ..vector_strokes import active

    return bool(active(layer))


def plain_box(layer):
    """A shape the plain stroke rule draws: one of the four box shapes without styled strokes, catalog geometry or
    distortion."""
    from ..shape_catalog import active as catalog_active

    return (layer.get("type", "shape") == "shape" and layer.get("shape") in BOX_SHAPES and not styled(layer)
            and not catalog_active(layer) and not layer.get("distort") and not layer.get("_distort_groups"))


def catalog(layer):
    from ..shape_catalog import active as catalog_active

    return bool(catalog_active(layer))


def plain_corners(layer):
    """A plain closed shape other than the four box shapes (polygon, star, shortcut shapes such as triangle): its
    box stays, only the outer corners of its stroke change."""
    from ..geometry import PATH_SHAPES

    return (layer.get("type", "shape") == "shape" and layer.get("shape") not in BOX_SHAPES
            and layer.get("shape") not in PATH_SHAPES and closed(layer) and not styled(layer) and not catalog(layer)
            and not layer.get("distort") and not layer.get("_distort_groups"))


def closed(layer):
    from ..geometry import is_open_shape

    return layer.get("type", "shape") == "shape" and not is_open_shape(layer)


def inset_box(layer):
    """The fields that keep a plain box shape's ink in place under the flush model, or a reason it cannot be done.

    Returns ``(fields, None)`` or ``(None, reason)``."""
    from ..render import transformed_size

    s = float(layer.get("stroke_width", 1))
    w, h = layer.get("width"), layer.get("height")
    if not all(isinstance(v, (int, float)) for v in (w, h)):
        return None, "its size is not stored in pixels"
    if min(w, h) - s < 1:
        return None, "the stroke fills the whole box"
    if layer.get("repeat") or layer.get("pivot") is not None:
        return None, "it repeats or turns about a pivot"
    fields = {"width": number(w - s), "height": number(h - s)}
    before = transformed_size(layer)
    after = transformed_size({**layer, **fields})
    fields["x"] = number(layer.get("x", 0) + (before[0] - after[0]) / 2)
    fields["y"] = number(layer.get("y", 0) + (before[1] - after[1]) / 2)
    shape = layer.get("shape")
    if shape in DEFAULT_RADIUS and "radius" not in layer:
        # The default radius follows the box, which is now smaller: store the one it had.
        fields["radius"] = number(min(w, h) * DEFAULT_RADIUS[shape])
    return fields, None


def number(value):
    value = round(float(value), 3)
    return int(value) if value.is_integer() else value
