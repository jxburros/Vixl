"""The remaining drawing finish guarantees: tangent joins, deskew and traced roughness."""

from copy import deepcopy

import numpy as np
import pytest
from PIL import Image, ImageDraw

from vixl import Project
from vixl.errors import VixlError
from vixl.plugins.drawing import drawing, gaps


def test_canopy_gap_follows_both_end_tangents():
    left = {"points": np.array([[-40, 40], [-20, 15], [0, 0]], float), "closed": False}
    right = {"points": np.array([[78, 0], [98, 15], [118, 40]], float), "closed": False}
    assert gaps.close_gaps([left, right], 78) == 1
    bridge = np.vstack([left["points"][2:], right["points"][1:-2]])
    assert bridge[:, 1].min() < -5, "the canopy should arch across the gap"
    assert np.allclose(left["points"][-1], right["points"][0])
    assert np.linalg.norm(np.diff(bridge, axis=0), axis=1).max() <= 3
    first, last = bridge[1] - bridge[0], bridge[-1] - bridge[-2]
    assert np.dot(first / np.linalg.norm(first), [0.8, -0.6]) > 0.99
    assert np.dot(last / np.linalg.norm(last), [0.8, 0.6]) > 0.99


def test_curved_ends_pointing_away_keep_the_bounded_midpoint_bridge():
    left = {"points": np.array([[20, 20], [10, 10], [0, 0]], float), "closed": False}
    right = {"points": np.array([[78, 0], [68, 10], [58, 20]], float), "closed": False}
    a = {"stroke": 0, "which": -1, "point": left["points"][-1], "direction": np.array([-1, -1]) / np.sqrt(2),
         "straight": False}
    b = {"stroke": 1, "which": 0, "point": right["points"][0], "direction": np.array([1, -1]) / np.sqrt(2),
         "straight": False}
    assert gaps._join([left, right], a, b, 78)
    assert np.allclose(left["points"][-1], [39, 0])
    assert np.allclose(right["points"][0], [39, 0])


@pytest.mark.parametrize("size", [400, 800, 1200])
@pytest.mark.parametrize("angle", [-2.0, 2.0])
def test_synthetic_two_degree_drawing_does_not_overshoot(size, angle):
    image = Image.new("L", (size, size))
    draw = ImageDraw.Draw(image)
    for fraction in (0.2, 0.4, 0.6, 0.8):
        draw.line([(size * .1, size * fraction), (size * .9, size * fraction)], fill=255, width=3)
    draw.rectangle([size * .2, size * .1, size * .8, size * .9], outline=255, width=3)
    tilted = np.asarray(image.rotate(angle, resample=Image.Resampling.BICUBIC)) > 127
    assert drawing.skew_angle(tilted) == pytest.approx(-angle, abs=0.15)


def test_vectorize_smooths_traced_steps_and_can_keep_raw_points(tmp_path):
    image = Image.new("RGB", (320, 180), "white")
    points = [(x, round(90 + 35 * np.sin(x / 60))) for x in range(20, 300)]
    ImageDraw.Draw(image).line(points, fill="black", width=4)
    path = tmp_path / "curve.png"
    image.save(path)
    project = Project(320, 180)
    project.apply({"type": "drawing", "action": "import", "path": str(path), "name": "art",
                   "settings": {"deskew": False, "perspective": False}})

    def trace(settings):
        project.apply({"type": "drawing", "action": "vectorize", "target": "art", "settings": settings})
        return [np.asarray(record["points"]) for layer in project.state["layers"]
                for record in layer.get("drawing_strokes", [])]

    raw = trace({"smooth": 0, "detail": 0})
    finished = trace({"detail": 0, "width": "uniform"})
    assert len(raw) == len(finished) == 1
    assert np.allclose(raw[0][[0, -1]], finished[0][[0, -1]])

    def turning(points):
        directions = np.diff(points, axis=0)
        angles = np.unwrap(np.arctan2(directions[:, 1], directions[:, 0]))
        return np.abs(np.diff(angles)).sum()

    assert turning(finished[0]) < turning(raw[0]) * .5
    before = deepcopy(project.state)
    with pytest.raises(VixlError):
        trace({"smooth": 1.1})
    assert project.state == before
