"""Drawing helpers for the built-in merch and print products (``products.py``, ``garments.py``).

A product is drawn as vector paths from a few measurements, never as a picture: ``Pen`` builds absolute path data,
``through`` and ``half_outline`` turn key points into smooth outlines (a symmetric garment is its right half
mirrored), and ``View`` places operations with tight bounding boxes at an offset in a scene. Shading, seams and
stitching are separate layers over the base layers (multiply and screen blends), so one drawing serves any colour.
Everything is measured in a flat-lay view at 30 px per inch (about 1.18 px per millimetre).
"""

import math

from ...geometry import compact_number

PX_PER_MM = 30 / 25.4
# The axis of a symmetric view, which every garment view is drawn around.
CX = 550
SHADE = "#000000"
LIGHT = "#ffffff"


class Pen:
    """An absolute path in view coordinates, built from the right half of a symmetric outline (``mirror``) or in
    one go."""

    def __init__(self, x, y):
        self.start = (x, y)
        self.segments = []
        self.closed = False

    @property
    def end(self):
        return self.segments[-1][-1] if self.segments else self.start

    def line(self, x, y):
        self.segments.append(("L", (x, y)))
        return self

    def move(self, x, y):
        """Start a new subpath (strokes made of many short lines, such as ribbing)."""
        self.segments.append(("M", (x, y)))
        return self

    def curve(self, x1, y1, x2, y2, x, y):
        self.segments.append(("C", (x1, y1), (x2, y2), (x, y)))
        return self

    def quad(self, x1, y1, x, y):
        self.segments.append(("Q", (x1, y1), (x, y)))
        return self

    def close(self):
        self.closed = True
        return self

    def mirror(self, cx):
        """Continue from the end (which lies on the axis ``x = cx``) back along this outline mirrored about the
        axis, and close it: the full outline of a symmetric shape drawn as its right half."""
        points = [self.start] + [seg[-1] for seg in self.segments]

        def flip(p):
            return (2 * cx - p[0], p[1])

        for i in range(len(self.segments) - 1, -1, -1):
            seg, back = self.segments[i], flip(points[i])
            if seg[0] == "M":
                raise ValueError("A mirrored outline is one subpath")
            if seg[0] == "L":
                self.line(*back)
            elif seg[0] == "C":
                self.curve(*flip(seg[2]), *flip(seg[1]), *back)
            else:
                self.quad(*flip(seg[1]), *back)
        return self.close()

    def points(self):
        out = [self.start]
        for seg in self.segments:
            out.extend(seg[1:])
        return out

    def data(self, dx=0, dy=0):
        parts = [f"M{compact_number(self.start[0] + dx, 2)} {compact_number(self.start[1] + dy, 2)}"]
        for seg in self.segments:
            coords = " ".join(f"{compact_number(x + dx, 2)} {compact_number(y + dy, 2)}" for x, y in seg[1:])
            parts.append(f"{seg[0]}{coords}")
        if self.closed:
            parts.append("Z")
        return " ".join(parts)


def polygon_pen(points, closed=True):
    pen = Pen(*points[0])
    for x, y in points[1:]:
        pen.line(x, y)
    return pen.close() if closed else pen


def lerp(a, b, t):
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)


def rotated_quad(center, width, height, up):
    """Corners (top-left, top-right, bottom-right, bottom-left) of a ``width`` × ``height`` rectangle centred on
    ``center`` whose upward direction is the unit vector ``up``."""
    ux, uy = up
    rx, ry = -uy, ux
    hw, hh = width / 2, height / 2
    cx, cy = center
    return [[round(cx - rx * hw + ux * hh, 2), round(cy - ry * hw + uy * hh, 2)],
            [round(cx + rx * hw + ux * hh, 2), round(cy + ry * hw + uy * hh, 2)],
            [round(cx + rx * hw - ux * hh, 2), round(cy + ry * hw - uy * hh, 2)],
            [round(cx - rx * hw - ux * hh, 2), round(cy - ry * hw - uy * hh, 2)]]


def rect_quad(cx, top, width, height):
    left = cx - width / 2
    return [[round(left, 2), top], [round(left + width, 2), top], [round(left + width, 2), round(top + height, 2)],
            [round(left, 2), round(top + height, 2)]]


class View:
    """Draws into a scene at an offset: every helper returns ordinary operations with a tight bounding box."""

    def __init__(self, ox, oy, prefix=""):
        self.ox, self.oy, self.prefix = ox, oy, prefix

    def name(self, name):
        return f"{self.prefix}{name}"

    def at(self, point):
        return [round(point[0] + self.ox, 2), round(point[1] + self.oy, 2)]

    def quad_at(self, corners):
        return [self.at(p) for p in corners]

    def path(self, name, pen, pad=0, shift=(0, 0), **style):
        points = pen.points()
        xs, ys = [p[0] for p in points], [p[1] for p in points]
        x0, y0 = math.floor(min(xs) - pad), math.floor(min(ys) - pad)
        x1, y1 = math.ceil(max(xs) + pad), math.ceil(max(ys) + pad)
        return {"type": "shape", "shape": "path", "name": self.name(name), "x": x0 + self.ox + shift[0],
                "y": y0 + self.oy + shift[1],
                "width": max(1, x1 - x0), "height": max(1, y1 - y0), "path": pen.data(-x0, -y0), **style}

    def clip_path_at(self, pen):
        return pen.data(self.ox, self.oy)


def stroke_style(color, width, opacity=1, dash=None, cap="round"):
    style = {"fill": "transparent", "stroke": color, "stroke_width": width, "line_cap": cap}
    if opacity != 1:
        style["opacity"] = opacity
    if dash:
        style["dash"] = dash
    return style


def layered(view, name, pen, *, base, blend=None, opacity=1, blur=0, pad=0, **style):
    """A shading layer clipped to ``base``: the path, an optional blur, a blend mode and the clip."""
    layer = view.name(name)
    ops = [view.path(name, pen, pad=pad + blur * 2, **style)]
    if opacity != 1:
        ops[0]["opacity"] = opacity
    if blur:
        ops.append({"type": "blur", "target": layer, "amount": blur})
    if blend:
        ops.append({"type": "blend", "target": layer, "value": blend})
    ops.append({"type": "clip", "target": layer, "base": view.name(base)})
    return ops


def drop_shadow(view, name, pen, dx=6, dy=16, blur=20, opacity=0.3):
    """A soft shadow under a silhouette: a black copy shifted by (dx, dy) and blurred."""
    layer = view.name(name)
    return [view.path(name, pen, pad=blur * 2 + 2, shift=(dx, dy), fill="#000000", opacity=opacity),
            {"type": "blur", "target": layer, "amount": blur}]




def through(points, corners=(), start_tangent=None, end_tangent=None, k=1.0, pen=None):
    """A smooth open curve through ``points`` (Catmull-Rom as cubic Béziers). Indices in ``corners`` stay sharp;
    the end tangents default to the chord to the neighbouring point. Continues ``pen`` when given."""
    n = len(points)
    tangents = []
    for i, p in enumerate(points):
        if i in corners:
            tangents.append((0.0, 0.0))
        elif i == 0:
            tangents.append(start_tangent or ((points[1][0] - p[0]) * k, (points[1][1] - p[1]) * k))
        elif i == n - 1:
            tangents.append(end_tangent or ((p[0] - points[i - 1][0]) * k, (p[1] - points[i - 1][1]) * k))
        else:
            tangents.append(((points[i + 1][0] - points[i - 1][0]) * k / 2, (points[i + 1][1] - points[i - 1][1]) * k / 2))
    pen = pen or Pen(*points[0])
    for i in range(n - 1):
        (x0, y0), (x1, y1), t0, t1 = points[i], points[i + 1], tangents[i], tangents[i + 1]
        pen.curve(x0 + t0[0] / 3, y0 + t0[1] / 3, x1 - t1[0] / 3, y1 - t1[1] / 3, x1, y1)
    return pen


def half_outline(points, corners=(), axis=550, k=1.0):
    """The full outline of a symmetric shape from the points of its right half, which run from the top of the
    axis to the bottom of it."""
    first = (abs(points[1][0] - points[0][0]) * 0.6 * k + 1, 0)
    last = (-(abs(points[-1][0] - points[-2][0]) * 0.6 * k + 1), 0)
    pen = through(points, corners, start_tangent=first, end_tangent=last, k=k)
    return pen.mirror(axis)
