"""Shared vector paths for procedural shortcuts and bounded editable Bézier geometry."""

import math
import re

from .errors import require
from .shape_catalog import KINDS as CATALOG_SHAPES

SHORTCUTS = {
    "triangle": "M50 0 L100 100 L0 100 Z",
    "right-triangle": "M0 0 L100 100 L0 100 Z",
    "diamond": "M50 0 L100 50 L50 100 L0 50 Z",
    "arrow": "M0 30 L60 30 L60 0 L100 50 L60 100 L60 70 L0 70 Z",
    "chevron": "M0 0 L40 0 L100 50 L40 100 L0 100 L60 50 Z",
    "cross": "M35 0 L65 0 L65 35 L100 35 L100 65 L65 65 L65 100 L35 100 L35 65 L0 65 L0 35 L35 35 Z",
    "heart": "M50 95 C35 80 0 55 0 30 C0 0 35 -5 50 20 C65 -5 100 0 100 30 C100 55 65 80 50 95 Z",
    "speech-bubble": "M10 0 L90 0 Q100 0 100 10 L100 65 Q100 75 90 75 L45 75 L20 100 L20 75 L10 75 Q0 75 0 65 L0 10 Q0 0 10 0 Z",
    "shield": "M0 0 L100 0 L100 45 Q100 80 50 100 Q0 80 0 45 Z",
    "trapezoid": "M25 0 L75 0 L100 100 L0 100 Z",
    "parallelogram": "M25 0 L100 0 L75 100 L0 100 Z",
}

# The one anchor table: named points of a box as (x, y) fractions. Every module that accepts an anchor
# name (pivot, resize, fit, guides, links, adapt) resolves it through canonical_anchor().
ANCHORS = {
    "top-left": (0, 0), "top": (0.5, 0), "top-right": (1, 0),
    "left": (0, 0.5), "center": (0.5, 0.5), "right": (1, 0.5),
    "bottom-left": (0, 1), "bottom": (0.5, 1), "bottom-right": (1, 1),
}


def _anchor_synonyms():
    synonyms = {}
    for name, (fx, fy) in ANCHORS.items():
        rows = {0: ("top",), 0.5: ("center", "middle"), 1: ("bottom",)}[fy]
        cols = {0: ("left",), 0.5: ("center", "middle"), 1: ("right",)}[fx]
        for v in rows:
            for h in cols:
                synonyms[f"{v}-{h}"] = synonyms[f"{h}-{v}"] = name
    for name in ANCHORS:
        synonyms.pop(name, None)
    return synonyms


ANCHOR_SYNONYMS = _anchor_synonyms()  # e.g. bottom-center, center-left, middle-right -> bottom, left, right
# Text layers have one more anchor: their first line's baseline (at the box's horizontal centre). It depends on
# the font, not on the box, so it is not a fraction in ANCHORS; align and snap measure it per text layer and
# reject it for other layers. Only callers that pass ``baseline=True`` accept it.
BASELINE = "baseline"


def canonical_anchor(value, baseline=False):
    """The canonical anchor name for ``value`` (a name or a synonym such as 'bottom-center'), else None.
    With ``baseline``, 'baseline' (or 'first-baseline') is accepted too."""
    if not isinstance(value, str):
        return None
    key = value.strip().lower().replace("_", "-").replace(" ", "-")
    if baseline and key in (BASELINE, "first-baseline"):
        return BASELINE
    return key if key in ANCHORS else ANCHOR_SYNONYMS.get(key)


EXTRA_SHAPES = (*CATALOG_SHAPES, *SHORTCUTS, "pentagon", "hexagon", "octagon", "capsule", "path", "arc")
# Shapes drawn from path data that already includes their own stroke inset (see wedge.arc_layer_path).
PATH_SHAPES = ("path", "arc")
# Shape kinds that are open strokes by nature; a ``path`` is open when it has no closing Z, and an
# ``arc`` when it has ``closed: false``. Test a layer with is_open_shape.
OPEN_SHAPES = ("line", "wave", "zigzag", "sawtooth", "square-wave", "dashed-line", "scribble", "squiggle", "swash-underline")


def is_open_shape(layer):
    if layer.get("shape") in OPEN_SHAPES:
        return True
    if layer.get("shape") == "arc":
        return layer.get("closed", True) is False
    return layer.get("shape") == "path" and re.search(r"[Zz]", str(layer.get("path", ""))) is None


def default_fill(layer):
    """The fill a shape layer paints with. An open shape (a line, or a path with no closing Z) that has a
    stroke and no explicit fill gets none; every other shape without a fill is white. Every backend uses this."""
    if "fill" in layer:
        return layer["fill"]
    stroked = str(layer.get("stroke", "transparent")).strip().lower() not in ("", "none", "transparent")
    return "transparent" if stroked and is_open_shape(layer) else "white"


def parse_path(path):
    """Normalize the complete SVG path language, including arcs and smooth commands."""
    from fontTools.pens.recordingPen import RecordingPen
    from fontTools.svgLib.path import parse_path as parse_svg
    from .errors import VixlError

    require(isinstance(path, str) and 0 < len(path) <= 262144, "Path must contain 1–262144 characters", "resource_limit")
    require(re.match(r"\s*[Mm]", path) is not None, "Path must start with M")
    require(not re.sub(r"[MmLlHhVvCcSsQqTtAaZz]|[-+]?(?:\d*\.\d+|\d+\.?\d*)(?:[eE][-+]?\d+)?|[\s,]", "", path),
            "Invalid SVG path syntax")
    pen = RecordingPen()
    try:
        parse_svg(path, pen)
    except (ValueError, IndexError, AssertionError, TypeError) as exc:
        raise VixlError("invalid_path", f"Invalid SVG path: {exc}") from exc
    require(sum(1 for command, _ in pen.value if command != "endPath") <= 8192,
            "Path supports at most 8192 commands", "resource_limit")
    commands = []
    for command, points in pen.value:
        if command == "endPath":
            continue
        letter = {"moveTo": "M", "lineTo": "L", "curveTo": "C", "qCurveTo": "Q", "closePath": "Z"}[command]
        values = [v for point in points for v in point]
        require(all(math.isfinite(v) and abs(v) <= 1e6 for v in values), "Path coordinates exceed limits")
        commands.append((letter, values))
    require(commands, "Path has no geometry")
    return commands


def compact_number(value, digits):
    """``value`` with at most ``digits`` decimals and no trailing zeros ('-0' reads '0'): path-data numbers."""
    text = f"{value:.{digits}f}"
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return "0" if text in ("", "-0") else text


def bezier_points(controls, ts):
    """Points of the Bézier curve with the given control points (any degree) at parameters ``ts``
    (de Casteljau), as an (n, 2) float array. The one curve evaluator for path flattening."""
    import numpy as np

    t = np.asarray(ts, dtype=float).reshape(-1, 1)
    work = [np.tile(np.asarray(p, dtype=float), (len(t), 1)) for p in controls]
    while len(work) > 1:
        work = [(1 - t) * a + t * b for a, b in zip(work, work[1:])]
    return work[0]


def path_polygons(path):
    polygons, points, current = [], [], (0, 0)
    for command, values in parse_path(path):
        if command == "M":
            if points:
                polygons.append(points)
            current = tuple(values)
            points = [current]
        elif command == "Z":
            if points:
                points.append(points[0])
                current = points[0]
        elif command == "L":
            current = tuple(values)
            points.append(current)
        else:
            controls = [current, *zip(values[::2], values[1::2])]
            points.extend(map(tuple, bezier_points(controls, [step / 48 for step in range(1, 49)]).tolist()))
            current = tuple(values[-2:])
    if points:
        polygons.append(points)
    return polygons


def path_extents(path):
    """``(min_x, min_y, max_x, max_y)`` of a path's drawn geometry (curves flattened), in its own units."""
    points = [point for polygon in path_polygons(path) for point in polygon]
    xs, ys = [p[0] for p in points], [p[1] for p in points]
    return min(xs), min(ys), max(xs), max(ys)


def path_box(path):
    """The (width, height) a ``path`` shape gets when created without them.

    Path coordinates are literal local pixels: a point (px, py) draws at the layer's (x + px, y + py).
    The box runs from that origin to the path's farthest point on each axis, never the whole canvas,
    and the path text is kept as written. Negative coordinates draw left of / above the box (keep
    paths in positive coordinates, or use ``path-fit`` to scale geometry into a box)."""
    _, _, x1, y1 = path_extents(path)
    return max(1, x1), max(1, y1)


def path_overflows(layer):
    """Whether authored path geometry extends beyond its coordinate frame (stroke excluded)."""
    if layer.get("shape") != "path":
        return False
    x0, y0, x1, y1 = path_extents(layer["path"])
    w, h = layer.get("path_view", (layer["width"], layer["height"]))
    return x0 < 0 or y0 < 0 or x1 > w or y1 > h


def shape_path(layer):
    shape = layer["shape"]
    from .shape_catalog import active, path
    if active(layer) and shape not in ("path", "arc"):
        return path(layer), (layer["width"], layer["height"])
    if shape == "path":
        return layer["path"], layer.get("path_view", (layer["width"], layer["height"]))
    if shape == "arc":
        from .wedge import arc_layer_path

        return arc_layer_path(layer)
    if shape in SHORTCUTS:
        return SHORTCUTS[shape], (100, 100)
    sides = {"pentagon": 5, "hexagon": 6, "octagon": 8}.get(
        shape, layer.get("sides", 5 if shape == "star" else 6)
    )
    points = []
    for i in range(sides * 2 if shape == "star" else sides):
        radius = layer.get("inner_radius", 0.5) if shape == "star" and i % 2 else 1
        angle = i * 2 * math.pi / (sides * 2 if shape == "star" else sides) - math.pi / 2
        points.append((50 + math.cos(angle) * 50 * radius, 50 + math.sin(angle) * 50 * radius))
    return "M" + " L".join(f"{x:g} {y:g}" for x, y in points) + " Z", (100, 100)
