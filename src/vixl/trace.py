"""Shared 2-D geometry for generated and traced artwork.

Contours of a scalar field (marching squares), polyline simplification and smoothing, polygon
measurements, and compact SVG path output. Organic shape generation and the drawing pipeline
both turn sampled geometry into editable Bézier paths through these helpers. Pure NumPy.
"""

import math

import numpy as np

from .errors import require
from .geometry import compact_number


# ---------------------------------------------------------------------------------------------
# Polygons and polylines


def area(points):
    """Signed area (positive when the points run clockwise on a y-down screen)."""
    p = np.asarray(points, dtype=float)
    if len(p) < 3:
        return 0.0
    x, y = p[:, 0], p[:, 1]
    return 0.5 * float(np.dot(x, np.roll(y, -1)) - np.dot(np.roll(x, -1), y))


def oriented(points, clockwise=True):
    """``points`` running clockwise (on screen) or counter-clockwise."""
    p = np.asarray(points, dtype=float)
    return p if (area(p) >= 0) == clockwise else p[::-1].copy()


def centroid(points):
    p = np.asarray(points, dtype=float)
    a = area(p)
    if abs(a) < 1e-12:
        return p.mean(axis=0)
    x, y = p[:, 0], p[:, 1]
    xn, yn = np.roll(x, -1), np.roll(y, -1)
    cross = x * yn - xn * y
    return np.array([np.sum((x + xn) * cross), np.sum((y + yn) * cross)]) / (6 * a)


def length(points, closed=False):
    p = np.asarray(points, dtype=float)
    if len(p) < 2:
        return 0.0
    if closed:
        p = np.vstack([p, p[:1]])
    return float(np.sum(np.hypot(*np.diff(p, axis=0).T)))


def contains(polygon, point):
    """Even-odd point-in-polygon test."""
    x, y = point
    inside = False
    p = np.asarray(polygon, dtype=float)
    for (x1, y1), (x2, y2) in zip(p, np.roll(p, -1, axis=0)):
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1 + 1e-300) + x1:
            inside = not inside
    return inside


def resample(points, count, closed=False):
    """``count`` points evenly spaced by arc length along a polyline or closed loop."""
    p = np.asarray(points, dtype=float)
    if closed:
        p = np.vstack([p, p[:1]])
    segment = np.hypot(*np.diff(p, axis=0).T)
    total = segment.sum()
    if total <= 0 or count < 2:
        return p[:max(1, count)]
    distance = np.concatenate([[0], np.cumsum(segment)])
    targets = np.linspace(0, total, count, endpoint=not closed)
    return np.column_stack([np.interp(targets, distance, p[:, i]) for i in (0, 1)])


def simplify(points, tolerance, closed=False):
    """Ramer–Douglas–Peucker simplification (keeps the first and last point of open lines)."""
    p = np.asarray(points, dtype=float)
    if len(p) <= 3 or tolerance <= 0:
        return p
    if closed:
        # Split at the point farthest from the first so both halves have distinct ends.
        far = int(np.argmax(np.hypot(*(p - p[0]).T)))
        first = simplify(p[: far + 1], tolerance)
        second = simplify(np.vstack([p[far:], p[:1]]), tolerance)
        return np.vstack([first[:-1], second[:-1]])
    keep = np.zeros(len(p), dtype=bool)
    keep[0] = keep[-1] = True
    stack = [(0, len(p) - 1)]
    while stack:
        start, end = stack.pop()
        if end <= start + 1:
            continue
        a, b = p[start], p[end]
        ab = b - a
        norm = math.hypot(*ab)
        segment = p[start + 1:end]
        if norm < 1e-12:
            distance = np.hypot(*(segment - a).T)
        else:
            distance = np.abs(ab[0] * (segment[:, 1] - a[1]) - ab[1] * (segment[:, 0] - a[0])) / norm
        index = int(np.argmax(distance))
        if distance[index] > tolerance:
            middle = start + 1 + index
            keep[middle] = True
            stack.extend([(start, middle), (middle, end)])
    return p[keep]


def chaikin(points, iterations=1, closed=True):
    """Corner cutting: each pass rounds every corner a little more."""
    p = np.asarray(points, dtype=float)
    for _ in range(iterations):
        if len(p) < 3:
            break
        if closed:
            q, r = p, np.roll(p, -1, axis=0)
            p = np.empty((len(q) * 2, 2))
            p[0::2] = 0.75 * q + 0.25 * r
            p[1::2] = 0.25 * q + 0.75 * r
        else:
            q, r = p[:-1], p[1:]
            middle = np.empty((len(q) * 2, 2))
            middle[0::2] = 0.75 * q + 0.25 * r
            middle[1::2] = 0.25 * q + 0.75 * r
            p = np.vstack([p[:1], middle, p[-1:]])
    return p


# ---------------------------------------------------------------------------------------------
# SVG path output


def _number(value, precision):
    return compact_number(value, precision)


def path_data(points, closed=False, smooth=True, precision=2, tension=1.0):
    """An SVG path for one polyline or loop. ``smooth`` passes a Catmull–Rom spline through the
    points (as cubic Béziers); otherwise straight segments join them."""
    p = np.asarray(points, dtype=float)
    if len(p) == 0:
        return ""

    def fmt(pt):
        return f"{_number(pt[0], precision)} {_number(pt[1], precision)}"

    if len(p) < 3 or not smooth:
        body = "M" + fmt(p[0]) + "".join(" L" + fmt(q) for q in p[1:])
        return body + (" Z" if closed else "")
    n = len(p)
    commands = ["M" + fmt(p[0])]
    count = n if closed else n - 1
    k = tension / 6
    for i in range(count):
        p0 = p[(i - 1) % n] if closed or i > 0 else p[i]
        p1, p2 = p[i], p[(i + 1) % n]
        p3 = p[(i + 2) % n] if closed or i + 2 < n else p2
        c1 = p1 + (p2 - p0) * k
        c2 = p2 - (p3 - p1) * k
        commands.append(f"C{fmt(c1)} {fmt(c2)} {fmt(p2)}")
    if closed:
        commands.append("Z")
    return " ".join(commands)


def elements_path(elements, precision=2):
    """One compound SVG path for several ``{"points", "closed", "smooth"}`` elements."""
    parts = [path_data(e["points"], e.get("closed", True), e.get("smooth", True), precision)
             for e in elements if len(e["points"])]
    return " ".join(part for part in parts if part)


# ---------------------------------------------------------------------------------------------
# Contours of a scalar field


def contours(field, level=0.5, *, min_points=3):
    """Closed contour loops of ``field`` (2-D array) at ``level``, in pixel-centre coordinates.

    The field is padded below the level so every contour closes. Each loop keeps the region above
    the level on the same side, so outer boundaries and holes run in opposite directions and a
    nonzero-filled path reproduces holes."""
    f = np.asarray(field, dtype=float)
    require(f.ndim == 2 and f.size <= 16_777_216, "Contour fields must be 2-D and at most 16 megapixels", "resource_limit")
    low = min(float(f.min()) if f.size else 0.0, level) - 1.0
    f = np.pad(f, 1, constant_values=low)
    inside = f > level
    cases = (inside[:-1, :-1].astype(np.uint8) * 8 + inside[:-1, 1:] * 4 + inside[1:, 1:] * 2
             + inside[1:, :-1] * 1)
    ys, xs = np.nonzero((cases > 0) & (cases < 15))

    def edge_point(key):
        kind, x, y = key
        if kind == "h":  # between grid points (x, y) and (x + 1, y)
            a, b = f[y, x], f[y, x + 1]
            t = (level - a) / (b - a) if b != a else 0.5
            return (x + t - 1, y - 1)
        a, b = f[y, x], f[y + 1, x]
        t = (level - a) / (b - a) if b != a else 0.5
        return (x - 1, y + t - 1)

    return _contours_linked(f, level, cases, ys, xs, edge_point, min_points)


def _contours_linked(f, level, cases, ys, xs, edge_point, min_points):
    """Link oriented marching-squares segments into loops (see ``contours``)."""
    outgoing = {}
    for y, x in zip(ys.tolist(), xs.tolist()):
        case = int(cases[y, x])
        a, b, c, d = f[y, x], f[y, x + 1], f[y + 1, x + 1], f[y + 1, x]
        top, right, bottom, left = ("h", x, y), ("v", x + 1, y), ("h", x, y + 1), ("v", x, y)
        # Directed edges with the inside (above level) on the right of travel, y down.
        table = {
            1: [(left, bottom)], 2: [(bottom, right)], 3: [(left, right)], 4: [(right, top)],
            6: [(bottom, top)], 7: [(left, top)], 8: [(top, left)], 9: [(top, bottom)],
            11: [(top, right)], 12: [(right, left)], 13: [(right, bottom)], 14: [(bottom, left)],
        }
        if case in (5, 10):
            centre = (a + b + c + d) / 4 > level
            if case == 5:   # tr and bl inside
                pairs = [(right, top), (left, bottom)] if not centre else [(left, top), (right, bottom)]
            else:           # tl and br inside
                pairs = [(top, left), (bottom, right)] if not centre else [(top, right), (bottom, left)]
        else:
            pairs = table[case]
        for start, end in pairs:
            outgoing[start] = end
    loops = []
    while outgoing:
        start, end = outgoing.popitem()
        loop = [edge_point(start)]
        key = end
        while key != start:
            loop.append(edge_point(key))
            following = outgoing.pop(key, None)
            if following is None:
                break
            key = following
        if len(loop) >= min_points:
            loops.append(np.array(loop, dtype=float))
    return loops


def mask_contours(mask, *, smooth=0.0, tolerance=0.6, min_area=4.0):
    """Simplified loops around the True pixels of ``mask``. ``smooth`` blurs the mask first
    (pixels), which rounds stair-steps into curves."""
    from PIL import Image, ImageFilter

    image = Image.fromarray(np.asarray(mask, dtype=np.uint8) * 255)
    if smooth > 0:
        image = image.filter(ImageFilter.GaussianBlur(smooth))
    field = np.asarray(image, dtype=float) / 255
    loops = []
    for loop in contours(field, 0.5):
        if abs(area(loop)) < min_area:
            continue
        loops.append(simplify(loop, tolerance, closed=True))
    return loops


def rasterize(elements, size, scale=1.0, offset=(0, 0)):
    """A boolean mask of closed elements drawn at ``scale`` with nonzero winding (PIL draws each
    polygon filled, which is a union of same-direction loops)."""
    from PIL import Image, ImageDraw

    image = Image.new("L", size, 0)
    draw = ImageDraw.Draw(image)
    for element in elements:
        if not element.get("closed", True) or len(element["points"]) < 3:
            continue
        p = (np.asarray(element["points"], dtype=float) - offset) * scale
        draw.polygon([tuple(q) for q in p], fill=255)
    return np.asarray(image) > 127
