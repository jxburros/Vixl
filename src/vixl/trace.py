"""Shared 2-D geometry for generated and traced artwork.

Contours of a scalar field (marching squares), polyline simplification and smoothing, polygon
measurements, and compact SVG path output. Organic shape generation and the drawing pipeline
both turn sampled geometry into editable Bézier paths through these helpers. Pure NumPy.
"""

import math

import numpy as np

from .errors import require
from .geometry import compact_number


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


def path_data(points, closed=False, smooth=True, precision=2, tension=1.0):
    """An SVG path for one polyline or loop. ``smooth`` passes a Catmull–Rom spline through the
    points (as cubic Béziers); otherwise straight segments join them."""
    p = np.asarray(points, dtype=float)
    if len(p) == 0:
        return ""

    def fmt(pt):
        return f"{compact_number(pt[0], precision)} {compact_number(pt[1], precision)}"

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


# Cubic Bézier fitting (Schneider, "An algorithm for automatically fitting digitized curves", Graphics Gems
# 1990), split at detected corners, so traced outlines become few editable curves instead of polylines.

def _unit(v):
    norm = float(np.hypot(*v))
    return v / norm if norm > 1e-12 else np.zeros(2)


def _bezier(control, t):
    t = np.asarray(t, float)[:, None]
    m = 1 - t
    return m ** 3 * control[0] + 3 * m * m * t * control[1] + 3 * m * t * t * control[2] + t ** 3 * control[3]


def _chord_params(points):
    steps = np.r_[0.0, np.cumsum(np.hypot(*np.diff(points, axis=0).T))]
    return steps / steps[-1] if steps[-1] > 0 else np.linspace(0, 1, len(points))


def _generate(points, params, start_tangent, end_tangent):
    """Least-squares control points for fixed end tangents."""
    first, last = points[0], points[-1]
    t = params
    b1, b2 = 3 * t * (1 - t) ** 2, 3 * t * t * (1 - t)
    a1, a2 = b1[:, None] * start_tangent, b2[:, None] * end_tangent
    c00, c01, c11 = (a1 * a1).sum(), (a1 * a2).sum(), (a2 * a2).sum()
    rest = points - _bezier(np.array([first, first, last, last]), t)
    x0, x1 = (a1 * rest).sum(), (a2 * rest).sum()
    det = c00 * c11 - c01 * c01
    chord = float(np.hypot(*(last - first)))
    alpha1 = alpha2 = 0.0
    if abs(det) > 1e-12:
        alpha1, alpha2 = (x0 * c11 - x1 * c01) / det, (c00 * x1 - c01 * x0) / det
    if alpha1 < 1e-6 * chord or alpha2 < 1e-6 * chord:
        alpha1 = alpha2 = chord / 3
    return np.array([first, first + start_tangent * alpha1, last + end_tangent * alpha2, last])


def _reparameterize(control, points, params):
    """One Newton–Raphson step towards each point's nearest parameter."""
    t = params[:, None]
    m = 1 - t
    q = _bezier(control, params)
    d1 = 3 * (m * m * (control[1] - control[0]) + 2 * m * t * (control[2] - control[1]) + t * t * (control[3] - control[2]))
    d2 = 6 * (m * (control[2] - 2 * control[1] + control[0]) + t * (control[3] - 2 * control[2] + control[1]))
    numerator = ((q - points) * d1).sum(axis=1)
    denominator = (d1 * d1).sum(axis=1) + ((q - points) * d2).sum(axis=1)
    safe = np.where(np.abs(denominator) > 1e-12, denominator, 1)
    return np.clip(np.where(np.abs(denominator) > 1e-12, params - numerator / safe, params), 0, 1)


def _fit(points, start_tangent, end_tangent, error, out, depth=0):
    if len(points) == 2 or depth > 24:
        gap = float(np.hypot(*(points[-1] - points[0]))) / 3
        out.append(np.array([points[0], points[0] + start_tangent * gap, points[-1] + end_tangent * gap, points[-1]]))
        return
    params = _chord_params(points)
    control = _generate(points, params, start_tangent, end_tangent)
    for attempt in range(5):
        distances = ((_bezier(control, params) - points) ** 2).sum(axis=1)
        worst = int(np.argmax(distances))
        if distances[worst] < error:
            out.append(control)
            return
        if distances[worst] > error * 16 or attempt == 4:
            break
        params = _reparameterize(control, points, params)
        control = _generate(points, params, start_tangent, end_tangent)
    split = min(max(worst, 1), len(points) - 2)
    reach = min(3, split, len(points) - 1 - split)
    centre = _unit(points[split - reach] - points[split + reach])
    if not centre.any():
        centre = _unit(points[split - 1] - points[split])
    _fit(points[:split + 1], start_tangent, centre, error, out, depth + 1)
    _fit(points[split:], -centre, end_tangent, error, out, depth + 1)


def corners(points, closed=True, threshold=60.0, reach=4.0):
    """Indices where the outline turns by more than ``threshold`` degrees within ``reach`` pixels each way."""
    p = np.asarray(points, float)
    n = len(p)
    if n < 5:
        return list(range(n)) if not closed else []
    step = max(float(np.median(np.hypot(*np.diff(p, axis=0).T))), 1e-6)
    k = max(1, min(n // 4, int(round(reach / step))))
    index = np.arange(n)
    before = p[(index - k) % n] if closed else p[np.clip(index - k, 0, n - 1)]
    after = p[(index + k) % n] if closed else p[np.clip(index + k, 0, n - 1)]
    a, b = p - before, after - p
    turn = np.degrees(np.abs(np.arctan2(a[:, 0] * b[:, 1] - a[:, 1] * b[:, 0], (a * b).sum(axis=1))))
    found = []
    for i in np.argsort(-turn):
        if turn[i] < threshold:
            break
        if not closed and (i < k or i > n - 1 - k):
            continue
        if all(min(abs(i - j), n - abs(i - j)) > k for j in found):
            found.append(int(i))
    return sorted(found)


def fit_curves(points, closed=True, tolerance=1.0, corner_threshold=60.0):
    """Cubic Bézier segments ``[[p0, c1, c2, p3], …]`` within ``tolerance`` pixels of ``points``, with sharp
    corners (a turn over ``corner_threshold`` degrees) kept as corners and smooth joins elsewhere."""
    p = np.asarray(points, float)
    if closed and len(p) > 1 and np.allclose(p[0], p[-1]):
        p = p[:-1]
    keep = np.r_[True, np.hypot(*np.diff(p, axis=0).T) > 1e-9]
    p = p[keep]
    n = len(p)
    if n < 3:
        return []
    error = max(tolerance, 0.05) ** 2
    marks = corners(p, closed, corner_threshold)
    segments = []
    if closed:
        if not marks:
            # A smooth loop: start where it is straightest and fit it with matching end tangents.
            start = 0
            p = np.r_[p[start:], p[:start]]
            loop = np.r_[p, p[:1]]
            tangent = _unit(p[min(3, n - 1)] - p[-min(3, n - 1)])
            _fit(loop, tangent, -tangent, error, segments)
            return segments
        p = np.r_[p[marks[0]:], p[:marks[0]]]
        marks = [(m - marks[0]) % n for m in marks] + [n]
        p = np.r_[p, p[:1]]
    else:
        marks = [0, *[m for m in marks if 0 < m < n - 1], n - 1]
    for a, b in zip(marks, marks[1:]):
        run = p[a:b + 1]
        if len(run) < 2:
            continue
        # End tangents come from the run's own first and last few pixels, skipping the corner point itself
        # (a traced corner is slightly rounded, and its neighbours would tilt a straight side).
        inner = 1 if len(run) > 4 else 0
        reach = max(inner + 1, min(10, len(run) // 3))
        _fit(run, _unit(run[reach] - run[inner]), _unit(run[-1 - reach] - run[-1 - inner]), error, segments)
    return segments


def curves_path(segments, closed=True, precision=2):
    """SVG path data for Bézier segments from ``fit_curves`` (one contour)."""
    if not segments:
        return ""

    def fmt(q):
        return f"{compact_number(q[0], precision)} {compact_number(q[1], precision)}"

    parts = ["M" + fmt(segments[0][0])]
    parts += [f"C{fmt(c[1])} {fmt(c[2])} {fmt(c[3])}" for c in segments]
    return " ".join(parts) + (" Z" if closed else "")


def mask_curves(mask, *, tolerance=1.0, corner_threshold=60.0, smooth=0.6, min_area=4.0, offset=(0.0, 0.0)):
    """Closed Bézier contours (outer edges and holes, opposite directions) around the True pixels of ``mask``,
    as ``(path data, loops)``. Coordinates are pixel edges: a pixel at column x spans x to x + 1."""
    from PIL import Image, ImageFilter

    image = Image.fromarray(np.asarray(mask, dtype=np.uint8) * 255)
    if smooth > 0:
        image = image.filter(ImageFilter.GaussianBlur(smooth))
    field = np.asarray(image, dtype=float) / 255
    paths, loops = [], []
    for loop in contours(field, 0.5):
        if abs(area(loop)) < min_area:
            continue
        loop = loop + 0.5 + np.asarray(offset, float)
        segments = fit_curves(loop, True, tolerance, corner_threshold)
        if segments:
            paths.append(curves_path(segments, True))
            loops.append(loop)
    return " ".join(paths), loops
