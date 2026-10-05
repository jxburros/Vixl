"""Pie wedges, donut segments and ring outlines as SVG path data.

``wedge_path`` is the one place this geometry lives: the ``arc`` shape layer draws with it, and
anything else that needs a slice of a circle (a chart layer, a gauge, a progress ring) can call
it directly instead of re-deriving the Bézier arithmetic. It has no dependencies on documents,
layers or colors.

Angles are degrees with 0 at 3 o'clock, growing clockwise on screen (y points down), as in SVG
paths and Vixl gradients. A pie that starts at 12 o'clock therefore starts at -90. A wedge runs
clockwise from ``start`` to ``end``; an ``end`` below ``start`` wraps around (350 to 10 is a 20°
wedge) and a sweep of 360° or more is the full circle or ring. Arcs are cubic Bézier curves, at
most 90° each, so every exporter (SVG, PDF, PowerPoint, raster) draws them without an arc command.
"""

import math

from .errors import require
from .model import finite

MAX_ANGLE = 10000


def sweep_of(start, end):
    """Clockwise sweep in degrees from ``start`` to ``end``: 0 for an empty wedge, 360 for a full turn."""
    delta = end - start
    if abs(delta) >= 360:
        return 360.0
    return float(delta % 360) if delta < 0 else float(delta)


def wedge_point(cx, cy, radius, angle, aspect=1.0):
    """The point on the circle (or ellipse, ``aspect`` = height over width) at ``angle`` degrees."""
    a = math.radians(angle)
    return cx + radius * math.cos(a), cy + radius * aspect * math.sin(a)


def wedge_centroid(cx, cy, radius, start, end, inner=0.0, aspect=1.0):
    """Where to put a label: the middle of the wedge, halfway between its inner and outer edge."""
    return wedge_point(cx, cy, (radius + inner) / 2, start + sweep_of(start, end) / 2, aspect)


def _number(value, digits):
    text = f"{value:.{digits}f}".rstrip("0").rstrip(".")
    return "0" if text in ("", "-0") else text


def _curves(cx, cy, rx, ry, start, sweep):
    """Cubic segments covering ``sweep`` degrees (negative runs back) from ``start``."""
    pieces = max(1, math.ceil(abs(sweep) / 90 - 1e-9))
    step = math.radians(sweep) / pieces
    k = 4 / 3 * math.tan(step / 4)
    a = math.radians(start)
    result = []
    for _ in range(pieces):
        b = a + step
        ca, sa, cb, sb = math.cos(a), math.sin(a), math.cos(b), math.sin(b)
        result.append((
            (cx + rx * (ca - k * sa), cy + ry * (sa + k * ca)),
            (cx + rx * (cb + k * sb), cy + ry * (sb - k * cb)),
            (cx + rx * cb, cy + ry * sb),
        ))
        a = b
    return result


def wedge_path(cx, cy, radius, start, end, inner=0.0, *, aspect=1.0, digits=3):
    """SVG path data for a pie wedge (``inner`` 0) or a donut segment (``inner`` > 0).

    ``radius`` and ``inner`` are the outer and inner radii in the same units as the centre
    (``inner`` is an absolute radius here; the ``arc`` shape layer takes it as a fraction of the
    outer radius). ``aspect`` stretches the vertical radius for an elliptical wedge. A full sweep
    with ``inner`` > 0 is a ring, drawn as two opposite-direction loops so the hole stays open
    under nonzero fill. Returns "" for an empty wedge (``end`` equal to ``start``) or a zero
    radius, so a chart can skip zero-value slices.
    """
    finite(radius, "radius", 0)
    finite(inner, "inner radius", 0)
    require(inner < radius or radius == 0, "The inner radius must be smaller than the outer radius", field="inner_radius")
    sweep = sweep_of(start, end)
    if sweep <= 0 or radius <= 0:
        return ""

    def xy(point):
        return f"{_number(point[0], digits)} {_number(point[1], digits)}"

    def curves(r, first, span):
        return "".join(f" C{xy(a)} {xy(b)} {xy(c)}" for a, b, c in _curves(cx, cy, r, r * aspect, first, span))

    out = f"M{xy(wedge_point(cx, cy, radius, start, aspect))}" + curves(radius, start, sweep)
    if sweep >= 360:
        out += " Z"
        if inner > 0:
            out += f" M{xy(wedge_point(cx, cy, inner, start, aspect))}" + curves(inner, start, -sweep) + " Z"
        return out
    if inner > 0:
        out += f" L{xy(wedge_point(cx, cy, inner, start + sweep, aspect))}" + curves(inner, start + sweep, -sweep)
    else:
        out += f" L{xy((cx, cy))}"
    return out + " Z"


def check_arc(layer):
    """Validate an ``arc`` shape layer's angles and inner radius; returns (start, end, inner)."""
    start = finite(layer.get("start_angle", 0), "start_angle", -MAX_ANGLE, MAX_ANGLE)
    end = finite(layer.get("end_angle", start + 360), "end_angle", -MAX_ANGLE, MAX_ANGLE)
    inner = finite(layer.get("inner_radius", 0), "inner_radius", 0, 0.99)
    require(end != start, "An arc needs an end_angle different from start_angle", field="end_angle")
    return start, end, inner


def arc_layer_path(layer):
    """Path and view box for an ``arc`` shape layer.

    The wedge is a slice of the ellipse that fills the layer box, so wedges that share a box and
    differ only in angles make a pie. It is drawn in pixels and pulled in by half the stroke, which
    keeps a stroked outline inside the box the way ellipses do.
    """
    start, end, inner = check_arc(layer)
    w, h = layer["width"], layer["height"]
    width = layer.get("stroke_width", 1)
    visible = str(layer.get("stroke", "transparent")).strip().lower() not in ("", "none", "transparent")
    pad = width / 2 if visible and width > 0 else 0
    rx, ry = max(w / 2 - pad, 0.01), max(h / 2 - pad, 0.01)
    return wedge_path(w / 2, h / 2, rx, start, end, inner * rx, aspect=ry / rx), (w, h)
