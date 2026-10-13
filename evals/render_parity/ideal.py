"""Exact (supersampled) references: what a perfect box-filtered rasterizer would draw.

A browser is one opinion; for geometry with a closed form there is a ground truth, and measuring both
Vixl and Chromium against it tells a defect from a different choice."""

import math

import numpy as np


def supersample(inside, width, height, n=16):
    """Coverage of the region where ``inside(x, y)`` (vectorised over arrays) holds, box-filtered:
    the fraction of an n x n grid of sample points per pixel that fall inside."""
    offsets = (np.arange(n) + 0.5) / n
    xs = (np.arange(width)[:, None] + offsets[None, :]).ravel()
    out = np.zeros((height, width))
    for row in range(height):
        ys = row + offsets
        X, Y = np.meshgrid(xs, ys)
        hits = inside(X, Y).reshape(n, width, n)
        out[row] = hits.mean(axis=(0, 2))
    return out


def ellipse(cx, cy, rx, ry):
    return lambda x, y: ((x - cx) / rx) ** 2 + ((y - cy) / ry) ** 2 <= 1


def rounded_rect(x0, y0, x1, y1, r):
    def inside(x, y):
        qx = np.maximum(np.maximum(x0 + r - x, x - (x1 - r)), 0)
        qy = np.maximum(np.maximum(y0 + r - y, y - (y1 - r)), 0)
        within = (x >= x0) & (x <= x1) & (y >= y0) & (y <= y1)
        return within & (qx * qx + qy * qy <= r * r)
    return inside


def ring(inner, outer):
    """Points inside ``outer`` but not ``inner`` (a stroke band between two shapes)."""
    return lambda x, y: outer(x, y) & ~inner(x, y)


def polygon(points):
    """Points inside a closed polygon (even-odd rule)."""
    def inside(x, y):
        result = np.zeros(np.shape(x), bool)
        for (x1, y1), (x2, y2) in zip(points, points[1:] + points[:1]):
            if y1 == y2:
                continue
            result ^= ((y1 > y) != (y2 > y)) & (x < (x2 - x1) * (y - y1) / (y2 - y1) + x1)
        return result
    return inside


def segment(ax, ay, bx, by, width, cap="butt"):
    """A straight stroke of ``width`` from (ax, ay) to (bx, by)."""
    dx, dy = bx - ax, by - ay
    length = math.hypot(dx, dy)

    def inside(x, y):
        t = ((x - ax) * dx + (y - ay) * dy) / (length * length)
        if cap == "butt":
            ok = (t >= 0) & (t <= 1)
        else:
            ok = (t >= -width / 2 / length) & (t <= 1 + width / 2 / length)
        px, py = ax + t * dx, ay + t * dy
        return ok & ((x - px) ** 2 + (y - py) ** 2 <= (width / 2) ** 2)
    return inside


def rotated(inside, cx, cy, degrees):
    """``inside`` turned clockwise (y down) about (cx, cy)."""
    a = math.radians(degrees)
    c, s = math.cos(a), math.sin(a)

    def turned(x, y):
        u, v = x - cx, y - cy
        return inside(cx + c * u + s * v, cy - s * u + c * v)
    return turned


def union(*shapes):
    def inside(x, y):
        result = shapes[0](x, y)
        for shape in shapes[1:]:
            result = result | shape(x, y)
        return result
    return inside


def gaussian(image, sigma):
    """A float array (h, w) or (h, w, c) blurred with a true Gaussian of ``sigma`` (edges padded with
    zeros, i.e. transparent)."""
    radius = max(1, int(math.ceil(4 * sigma)))
    k = np.exp(-0.5 * (np.arange(-radius, radius + 1) / sigma) ** 2)
    k /= k.sum()
    a = np.asarray(image, float)
    for axis in (0, 1):
        a = np.apply_along_axis(lambda v: np.convolve(v, k, mode="same"), axis, a)
    return a


def linear_ramp(width, start, end):
    """Ideal horizontal gradient row: colour at each pixel centre ((i + 0.5) / width) as 0-1 floats."""
    t = (np.arange(width) + 0.5) / width
    s, e = np.array(start, float) / 255, np.array(end, float) / 255
    return s[None, :] + (e - s)[None, :] * t[:, None]


def area_downscale(image, factor):
    """An exact box-filter (area average) downscale of an (h, w, c) float array by an integer factor."""
    h, w = image.shape[0] // factor * factor, image.shape[1] // factor * factor
    a = image[:h, :w]
    return a.reshape(h // factor, factor, w // factor, factor, -1).mean(axis=(1, 3))
