"""Trim path: draw a shape's or path's stroke only between two points along its outline.

``trim_start`` and ``trim_end`` are percentages (0–100) of the outline's length, so animating
``trim_end`` from 0 to 100 draws a line on, and a ``trim_start`` that follows it undraws it. Only
the stroke is trimmed; the fill stays whole. A path with several contours trims each one by the same
percentages. The outline of a closed shape starts at the top-left corner of a rectangle and the top
of an ellipse and runs clockwise; paths and polygons run in the order they are written.

The trimmed stroke is a dashed stroke whose single dash covers the visible part, in the outline's
own units, so stills and animation frames (resvg) and SVG exports draw it the same way. PDF and
PowerPoint exports fall back to a raster of the layer.
"""

from functools import lru_cache
import io
import math
import xml.etree.ElementTree as ET

import numpy as np

from .errors import require
from .model import finite

TRIM = ("trim_start", "trim_end")
CAPS = ("butt", "round", "square")
CURVE_STEPS = 64
SQUARE_JOINS = ("rectangle", "rounded-rectangle", "capsule")


def schema():
    """JSON Schema properties shared by the ``shape`` and ``pen`` operations."""
    percent = {"type": "number", "minimum": 0, "maximum": 100}
    return {
        "trim_start": {**percent, "description": "Stroke trim: percent of the outline's length where the visible stroke starts "
                       "(default 0). Animate it with keyframe/animate property trim_start; start above end swaps them."},
        "trim_end": {**percent, "description": "Stroke trim: percent of the outline's length where the visible stroke ends "
                     "(default 100). Animate trim_end from 0 to 100 to draw a line on (animate-preset draw-on)."},
        "line_cap": {"enum": list(CAPS), "description": "Stroke end caps (default butt). round gives a trimmed or drawn-on stroke round ends."},
    }


def trim_range(layer):
    """The visible part of a shape's stroke as ``(start, end)`` fractions of its length, or ``None``
    when the stroke is not trimmed. A start past the end swaps them."""
    if layer.get("type") != "shape":
        return None
    start, end = float(layer.get("trim_start", 0)), float(layer.get("trim_end", 100))
    start, end = max(0.0, min(start, end)), min(100.0, max(start, end))
    if start <= 0 and end >= 100:
        return None
    return start / 100, end / 100


def validate_trim(layer):
    for key in TRIM:
        if key in layer:
            finite(layer[key], key, 0, 100)


def _num(value):
    text = f"{value:.3f}".rstrip("0").rstrip(".")
    return "0" if text in ("", "-0") else text


def _d(commands):
    return " ".join(letter + " ".join(_num(v) for v in values) for letter, values in commands)


def _arc_path(kind, x0, y0, x1, y1, radius):
    if kind == "ellipse":
        cx, cy, rx, ry = (x0 + x1) / 2, (y0 + y1) / 2, (x1 - x0) / 2, (y1 - y0) / 2
        arc = f"A{rx} {ry} 0 0 1 "
        return f"M{cx} {y0} {arc}{x1} {cy} {arc}{cx} {y1} {arc}{x0} {cy} {arc}{cx} {y0} Z"
    if kind == "rectangle" or radius <= 0:
        return f"M{x0} {y0} L{x1} {y0} L{x1} {y1} L{x0} {y1} Z"
    r = radius
    arc = f"A{r} {r} 0 0 1 "
    return (f"M{x0 + r} {y0} L{x1 - r} {y0} {arc}{x1} {y0 + r} L{x1} {y1 - r} {arc}{x1 - r} {y1} "
            f"L{x0 + r} {y1} {arc}{x0} {y1 - r} L{x0} {y0 + r} {arc}{x0 + r} {y0} Z")


def _contours(commands):
    """Split normalized path commands into contours, each starting with its own moveTo."""
    contours, current, start = [], None, (0.0, 0.0)
    for letter, values in commands:
        if letter == "M":
            current, start = [(letter, values)], (values[0], values[1])
            contours.append(current)
            continue
        if current is None or current[-1][0] == "Z":
            current = [("M", start)]
            contours.append(current)
        current.append((letter, values))
    return contours


def _curve(points, steps=CURVE_STEPS):
    t = np.linspace(0.0, 1.0, steps + 1)[:, None]
    pts = np.asarray(points, dtype=float)
    if len(pts) == 3:
        curve = (1 - t) ** 2 * pts[0] + 2 * (1 - t) * t * pts[1] + t**2 * pts[2]
    else:
        curve = (1 - t) ** 3 * pts[0] + 3 * (1 - t) ** 2 * t * pts[1] + 3 * (1 - t) * t**2 * pts[2] + t**3 * pts[3]
    return float(np.hypot(*np.diff(curve, axis=0).T).sum())


def _length(contour):
    total, current, start = 0.0, None, None
    for letter, values in contour:
        if letter == "M":
            current = start = (values[0], values[1])
            continue
        if letter == "Z":
            total += math.dist(current, start)
            current = start
            continue
        points = list(zip(values[::2], values[1::2]))
        if letter == "C" and len(points) == 3:
            total += _curve([current, *points])
        elif letter == "Q" and len(points) == 2:
            total += _curve([current, *points])
        else:  # A line, or a curve with extra off-curve points, measured through its points.
            for point in points:
                total += math.dist(current, point)
                current = point
        current = points[-1]
    return total


def _transform(commands, scale, offset):
    return [(letter, tuple(v * scale[i % 2] + offset[i % 2] for i, v in enumerate(values))) for letter, values in commands]


@lru_cache(maxsize=64)
def _outline(shape, path, width, height, inset, radius, sides, inner_radius):
    """The outline as ``((commands, length), …)``, one entry per contour, in its own units: the
    path's viewBox for a ``path`` shape, else pixels of the ``width`` × ``height`` box, inset by
    ``inset`` on every side."""
    from .geometry import parse_path, shape_path

    if shape == "path":
        commands = parse_path(path)
    elif shape == "line":
        commands = [("M", (inset, inset)), ("L", (width - inset, height - inset))]
    else:
        x0, y0, x1, y1 = inset, inset, width - inset, height - inset
        if x1 - x0 < 1e-3 or y1 - y0 < 1e-3:
            return ()  # The stroke leaves no room inside the box: draw nothing, as untrimmed shapes do.
        if shape in ("rectangle", "rounded-rectangle", "capsule", "ellipse"):
            radius = min(radius, (x1 - x0) / 2, (y1 - y0) / 2)
            commands = parse_path(_arc_path(shape, x0, y0, x1, y1, radius))
        else:
            outline, box = shape_path({"shape": shape, "sides": sides, "inner_radius": inner_radius})
            commands = _transform(parse_path(outline), ((x1 - x0) / box[0], (y1 - y0) / box[1]), (x0, y0))
    return tuple((tuple(c), _length(c)) for c in _contours(commands))


def trim_geometry(layer, stroke_visible=True):
    """What to draw for a trimmed shape: ``{"view", "fill", "strokes", "width", "cap", "join", "line"}``.

    ``strokes`` lists ``(path data, dasharray, dashoffset)`` per contour; ``fill`` is the path data
    of the whole outline (``None`` for a line); ``view`` is a ``path`` shape's viewBox size (its
    geometry stays in those units) and ``None`` for shapes laid out in pixels."""
    start, end = trim_range(layer) or (0.0, 1.0)
    shape, width = layer["shape"], layer.get("stroke_width", 1)
    path = shape == "path"
    view = tuple(layer.get("path_view", (layer["width"], layer["height"]))) if path else None
    w, h = layer["width"], layer["height"]
    radius = layer.get("radius", min(w, h) / (2 if shape == "capsule" else 5)) if shape in ("rounded-rectangle", "capsule") else 0
    pad = width / 2 if stroke_visible else 0
    sides, inner = layer.get("sides", 5 if shape == "star" else 6), layer.get("inner_radius", 0.5)
    if path:  # In the path's own viewBox units, so cached apart from the layer's size.
        outline = stroke_outline = _outline("path", layer["path"], 0, 0, 0, 0, 0, 0)
    else:
        # The box is inset by half the stroke, so the stroke stays inside the layer. Rectangles and
        # ellipses draw their stroke inward from that edge, so its centerline is half a stroke further in.
        outline = _outline(shape, None, w, h, pad, radius, sides, inner)
        rounded = shape in ("rectangle", "rounded-rectangle", "capsule", "ellipse")
        stroke_outline = _outline(shape, None, w, h, 2 * pad, max(radius - pad, 0), sides, inner) if rounded and pad else outline
    strokes = []
    for commands, length in stroke_outline:
        if length <= 0 or end <= start:
            continue
        visible = (end - start) * length
        if end >= 1:
            visible += length * 0.01  # Rounding in the length must not leave the end of the stroke undrawn.
        period = visible + length
        offset = (period - start * length) % period if start > 0 else 0.0
        strokes.append((_d(commands), f"{_num(visible)} {_num(length)}", _num(offset)))
    cap = layer.get("line_cap", "butt")
    return {
        "view": view,
        "fill": None if shape == "line" else _d([c for contour, _ in outline for c in contour]),
        "strokes": strokes,
        "width": max(width, 0.25) if shape == "line" else width,
        "cap": cap,
        "join": "round" if cap == "round" or (not path and shape not in SQUARE_JOINS) else "miter",
        "line": shape == "line",
    }


def trimmed_image(project, layer):
    """The layer's shape drawn with its stroke trimmed (resvg, like path shapes)."""
    import resvg_py
    from PIL import Image

    from .colors import hex_of, parse
    from .design import resolve_color
    from .geometry import default_fill

    def paint(field, default):
        rgba = parse(resolve_color(layer.get(field, default), project.state))
        return hex_of((*rgba[:3], 1)), str(rgba[3])

    w, h = layer["width"], layer["height"]
    stroke, stroke_opacity = paint("stroke", "transparent")
    fill, fill_opacity = paint("fill", default_fill(layer))
    geometry = trim_geometry(layer, float(stroke_opacity) > 0)
    root = ET.Element("svg", xmlns="http://www.w3.org/2000/svg", width=str(w), height=str(h))
    if geometry["view"]:
        root.set("viewBox", f"0 0 {geometry['view'][0]} {geometry['view'][1]}")
        root.set("preserveAspectRatio", "none")
    if geometry["fill"] and float(fill_opacity) > 0:
        ET.SubElement(root, "path", {"d": geometry["fill"], "fill": fill, "fill-opacity": fill_opacity, "stroke": "none"})
    if geometry["line"] and float(stroke_opacity) == 0:
        stroke, stroke_opacity = fill, fill_opacity  # A line with no stroke color draws in its fill color.
    if float(stroke_opacity) > 0 and geometry["width"] > 0:
        for d, dash, offset in geometry["strokes"]:
            ET.SubElement(root, "path", {
                "d": d, "fill": "none", "stroke": stroke, "stroke-opacity": stroke_opacity,
                "stroke-width": _num(geometry["width"]), "stroke-dasharray": dash, "stroke-dashoffset": offset,
                "stroke-linecap": geometry["cap"], "stroke-linejoin": geometry["join"],
            })
    data = resvg_py.svg_to_bytes(svg_string=ET.tostring(root, encoding="unicode"))
    return Image.open(io.BytesIO(data)).convert("RGBA")


def require_shape(layer, prop):
    require(layer["type"] == "shape", f"{prop} trims the stroke of a shape or path layer; {layer['name']!r} is a {layer['type']} layer",
            field="property")
