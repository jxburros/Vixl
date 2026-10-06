"""Shared editable affine geometry, in canvas coordinates with clockwise angles."""

import math
import numpy as np


def matrix(a=1, b=0, c=0, d=1, e=0, f=0):
    return np.array([[a, c, e], [b, d, f], [0.0, 0.0, 1.0]])


def linear(layer):
    angle = math.radians(layer.get("rotation", 0))
    co, si = math.cos(angle), math.sin(angle)
    skew = matrix(
        1, math.tan(math.radians(layer.get("skew_y", 0))), math.tan(math.radians(layer.get("skew_x", 0))), 1
    )
    flip = matrix(-1 if layer.get("flip_x") else 1, 0, 0, -1 if layer.get("flip_y") else 1)
    extra = matrix(*layer.get("affine", [1, 0, 0, 1, 0, 0]))
    return extra @ matrix(co, si, -si, co) @ skew @ flip


def layer_matrix(layer, bounds):
    from .render import rest_size

    x, y, w, h = bounds
    rw, rh = rest_size(layer)
    return matrix(e=x + w / 2, f=y + h / 2) @ linear(layer) @ matrix(e=-rw / 2, f=-rh / 2)


def corners(box, transform):
    x, y, w, h = box
    return (transform @ np.array([[x, x + w, x + w, x], [y, y, y + h, y + h], [1, 1, 1, 1]]))[:2].T


def envelope(points):
    low, high = np.min(points, axis=0), np.max(points, axis=0)
    return tuple(float(v) for v in (*low, *(high - low)))


def precise(layer):
    return bool(layer.get("skew_x") or layer.get("skew_y") or layer.get("affine"))
