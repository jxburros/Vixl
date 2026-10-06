"""The shared anchor table, curve evaluator and number formatter reproduce the per-module copies they replaced."""

import math

import numpy as np
import pytest

from vixl import adapt, guides, links, transforms
from vixl.geometry import ANCHORS, bezier_points, compact_number, parse_path, path_polygons
from vixl.irregular import flatten

PATHS = [
    "M10 10 C 40 0 60 40 90 10 S 150 60 100 90 Q 50 120 10 90 Z",
    "M0 0 L100 0 L100 100 L0 100 Z M20 20 C 30 10 70 10 80 20 L 80 80 Z",
    "M5 50 A 40 40 0 1 1 95 50 A 40 40 0 1 1 5 50 Z",
    "M0 0 Q 50 100 100 0 T 200 0",
]


def old_path_polygons(path):
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
            for step in range(1, 49):
                t = step / 48
                working = controls
                while len(working) > 1:
                    working = [(a[0] * (1 - t) + b[0] * t, a[1] * (1 - t) + b[1] * t) for a, b in zip(working, working[1:])]
                points.append(working[0])
            current = tuple(values[-2:])
    if points:
        polygons.append(points)
    return polygons


@pytest.mark.parametrize("path", PATHS)
def test_path_polygons_unchanged_by_the_shared_curve_evaluator(path):
    new, old = path_polygons(path), old_path_polygons(path)
    assert len(new) == len(old)
    for a, b in zip(new, old):
        assert len(a) == len(b)
        assert np.allclose(np.array(a), np.array(b), atol=1e-9, rtol=0)


def old_bezier(controls, t):
    work = [np.tile(p, (len(t), 1)) for p in controls]
    while len(work) > 1:
        work = [(1 - t) * a + t * b for a, b in zip(work, work[1:])]
    return work[0]


@pytest.mark.parametrize("controls", [[(0, 0), (10, 40), (30, -20), (50, 5)], [(0, 0), (20, 30), (40, 0)]])
def test_bezier_points_matches_the_irregular_evaluator(controls):
    ts = np.linspace(0, 1, 17)[1:]
    assert np.array_equal(bezier_points(controls, ts), old_bezier([np.array(c, float) for c in controls], ts[:, None]))


def test_irregular_flatten_samples_curves():
    subs = flatten(PATHS[0])
    points, nodes, closed = subs[0]
    assert closed and nodes[0] and len(points) > 20
    assert np.hypot(*(points.max(axis=0) - points.min(axis=0))) > 100


def test_every_module_uses_the_one_anchor_table():
    for name, (fx, fy) in ANCHORS.items():
        assert guides.ANCHORS[name] == (fx, fy) and links._position(name) == [fx, fy]
        assert transforms.anchor(name) == [fx, fy]
    assert guides.ANCHORS is ANCHORS and links.ANCHORS is ANCHORS and transforms.ANCHORS is ANCHORS
    for name in ANCHORS:
        assert name in adapt.ANCHORS
    assert adapt.ANCHORS["bottom-right"] == ("end", "end") and adapt.ANCHORS["top"] == ("center", "start")
    assert links._position("bottom-center") == [0.5, 1] and transforms.anchor("center-left") == [0, 0.5]


@pytest.mark.parametrize("value, digits, expected", [(0.0, 3, "0"), (-0.0001, 3, "0"), (1.5, 2, "1.5"), (12.0, 2, "12"), (-3.14159, 3, "-3.142"), (100.0, 0, "100")])
def test_compact_number(value, digits, expected):
    assert compact_number(value, digits) == expected
    assert math.isfinite(float(expected))
