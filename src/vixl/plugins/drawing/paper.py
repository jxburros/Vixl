"""A photographed sheet of paper, flattened.

``drawing`` finds the sheet in a photo (the bright page on a darker desk). Here its outline is
fitted with a four-sided polygon and, when the camera looked at the page from an angle so that
the page is a trapezoid, the photo is warped so the page becomes a rectangle again (perspective
correction), before any line is traced. The four corners are all it takes: the page's proportions
follow from them for a pinhole camera looking at the middle of the photo, so a circle drawn on
the page comes out round. A page that only turned (a rectangle, however tilted) is left to the
drawing's own tilt detection; so is a page the frame cuts off, whose corners are not in the photo.
Pure NumPy and Pillow.
"""

import math

import numpy as np
from PIL import Image

MAX_TILT = 30.0         # degrees: a page turned further than this is left alone
NEEDS_WARP = 1.0        # degrees of non-parallel or non-square corners, or ...
NEEDS_RATIO = 1.02      # ... a share of 2% between opposite sides, before a page is warped
MAX_SIZE = 6000         # pixels, either way, of the flattened page


def _cross(a, b):
    return a[0] * b[1] - a[1] * b[0]


def _meet(a, r, b, s):
    """Where the line a + t·r crosses b + u·s: (t, u), or None when they are parallel."""
    cross = _cross(r, s)
    if abs(cross) < 1e-9:
        return None
    w = b - a
    return _cross(w, s) / cross, _cross(w, r) / cross


def fit_quad(hull):
    """The four-sided polygon that encloses a convex outline most tightly: while there are more
    than four sides, the one whose removal (its neighbours run on until they cross) adds the least
    area goes. Returns the corners ordered top-left, top-right, bottom-right, bottom-left, or None
    when the outline is not a roughly upright page."""
    points = [np.asarray(p, float) for p in hull]
    while len(points) > 4:
        n = len(points)
        best = None
        for i in range(n):
            a, b, c, d = points[i - 1], points[i], points[(i + 1) % n], points[(i + 2) % n]
            meet = _meet(a, b - a, d, c - d)
            if meet is None or meet[0] < 1 or meet[1] < 1:
                continue
            corner = a + (b - a) * meet[0]
            added = abs(_cross(corner - b, c - b)) / 2
            if best is None or added < best[0]:
                best = (added, i, corner)
        if best is None:
            # No side can be dropped by running its neighbours on: drop the sharpest-looking corner.
            i = min(range(n), key=lambda k: abs(_cross(points[k] - points[k - 1], points[(k + 1) % n] - points[k])))
            del points[i]
            continue
        _, i, corner = best
        points = points[i:] + points[:i]
        points = [corner] + points[2:]
    if len(points) != 4:
        return None
    p = np.array(points)
    order = [int(np.argmin(p[:, 0] + p[:, 1])), int(np.argmax(p[:, 0] - p[:, 1])),
             int(np.argmax(p[:, 0] + p[:, 1])), int(np.argmin(p[:, 0] - p[:, 1]))]
    if len(set(order)) != 4:
        return None
    quad = p[order]
    for a, b, upright in ((0, 1, True), (3, 2, True), (0, 3, False), (1, 2, False)):
        v = quad[b] - quad[a]
        tilt = math.degrees(math.atan2(v[1], v[0])) if upright else math.degrees(math.atan2(v[0], v[1]))
        if abs(tilt) > MAX_TILT:
            return None
    return quad


def _angle_between(u, v):
    """Degrees between two directions, ignoring which way they point."""
    angle = abs(math.degrees(math.atan2(_cross(u, v), float(u @ v))))
    return min(angle, 180 - angle)


def skew(quad):
    """How far the quad is from a (possibly turned) rectangle: (degrees that opposite sides are
    out of parallel or the corners out of square, ratio of the longer to the shorter of opposite
    sides)."""
    top, right, bottom, left = quad[1] - quad[0], quad[2] - quad[1], quad[2] - quad[3], quad[3] - quad[0]
    lengths = [float(np.linalg.norm(v)) for v in (top, bottom, left, right)]
    ratio = max(max(lengths[0], lengths[1]) / max(1e-9, min(lengths[0], lengths[1])),
                max(lengths[2], lengths[3]) / max(1e-9, min(lengths[2], lengths[3])))
    corners = [abs(_angle_between(a, b) - 90) for a, b in ((top, left), (top, right), (bottom, left), (bottom, right))]
    return max(_angle_between(top, bottom), _angle_between(left, right), *corners), ratio


def page_aspect(quad, centre):
    """Width over height of the rectangle photographed as ``quad``: the pinhole camera that sees
    it (square pixels, optical axis through ``centre``) is found from the corners alone (Zhang and
    He, whiteboard scanning). Falls back to the mean side lengths when the corners are too
    square-on or too skewed to say."""
    top, bottom = np.linalg.norm(quad[1] - quad[0]), np.linalg.norm(quad[2] - quad[3])
    left, right = np.linalg.norm(quad[3] - quad[0]), np.linalg.norm(quad[2] - quad[1])
    plain = (top + bottom) / max(1e-9, left + right)
    m1, m2, m3, m4 = (np.append(quad[i] - centre, 1.0) for i in (0, 1, 3, 2))
    with np.errstate(all="ignore"):
        k2 = float(np.cross(m1, m4) @ m3 / (np.cross(m2, m4) @ m3))
        k3 = float(np.cross(m1, m4) @ m2 / (np.cross(m3, m4) @ m2))
        n2, n3 = k2 * m2 - m1, k3 * m3 - m1
        f2 = -(n2[0] * n3[0] + n2[1] * n3[1]) / (n2[2] * n3[2])
        ratio = math.sqrt((n2[0] ** 2 + n2[1] ** 2 + f2 * n2[2] ** 2) / (n3[0] ** 2 + n3[1] ** 2 + f2 * n3[2] ** 2))
    if not (np.isfinite(f2) and f2 > 0 and np.isfinite(ratio)) or abs(math.log(ratio / plain)) > math.log(1.35):
        return plain
    return ratio


def inset_quad(quad, distance):
    """The quad with each side moved ``distance`` pixels inwards (clear of the page's own edge)."""
    centre = quad.mean(axis=0)
    lines = []
    for a, b in zip(quad, np.roll(quad, -1, axis=0)):
        d = (b - a) / max(1e-9, float(np.linalg.norm(b - a)))
        normal = np.array([-d[1], d[0]])
        if (centre - a) @ normal < 0:
            normal = -normal
        lines.append((a + normal * distance, d))
    corners = []
    for i in range(4):
        (p, r), (q, s) = lines[i - 1], lines[i]
        meet = _meet(p, r, q, s)
        corners.append(p + r * meet[0] if meet is not None else quad[i])
    return np.array(corners)


def frame_for(hull, size, inset):
    """How to flatten the page whose outline in a photo of ``size`` (width, height) is ``hull``:
    {"quad": its four corners, "size": [width, height] of the flat page}, or None when the page
    needs no perspective correction (it is a plain rectangle, it runs off the frame, or it is not
    an upright page)."""
    quad = fit_quad(hull)
    width, height = size
    margin = 0.005 * min(width, height)
    if quad is None or (quad[:, 0] < margin).any() or (quad[:, 0] > width - margin).any() \
            or (quad[:, 1] < margin).any() or (quad[:, 1] > height - margin).any():
        return None
    angle, ratio = skew(quad)
    if angle < NEEDS_WARP and ratio < NEEDS_RATIO:
        return None
    quad = inset_quad(quad, inset)
    aspect = page_aspect(quad, np.array([width / 2, height / 2]))
    flat = (np.linalg.norm(quad[1] - quad[0]) + np.linalg.norm(quad[2] - quad[3])) / 2
    out_w, out_h = max(16.0, flat), max(16.0, flat / aspect)
    shrink = min(1.0, MAX_SIZE / max(out_w, out_h))
    return {"quad": np.round(quad, 2).tolist(), "size": [max(16, round(out_w * shrink)), max(16, round(out_h * shrink))]}


def _coefficients(quad, size):
    """Pillow's perspective coefficients taking each pixel of a ``size`` rectangle to the quad."""
    w, h = size
    rows, values = [], []
    for (x, y), (u, v) in zip(((0, 0), (w, 0), (w, h), (0, h)), quad):
        rows.append([x, y, 1, 0, 0, 0, -u * x, -u * y])
        values.append(u)
        rows.append([0, 0, 0, x, y, 1, -v * x, -v * y])
        values.append(v)
    return tuple(np.linalg.solve(np.array(rows, float), np.array(values, float)))


def rectify(image, frame):
    """The page of ``frame`` (see ``frame_for``) as a flat rectangle."""
    size = tuple(int(v) for v in frame["size"])
    return image.transform(size, Image.Transform.PERSPECTIVE, _coefficients(np.asarray(frame["quad"], float), size),
                           Image.Resampling.BICUBIC)
