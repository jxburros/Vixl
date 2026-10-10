"""A layer or group scaled to (nearly) nothing renders as nothing, without a large allocation (#597)."""

import numpy as np
import pytest
from PIL import Image

from vixl import Project
from vixl.timeline import render_at

PATH = "M110 0 L220 235.6 L176 380 L44 380 L0 235.6 Z"


def popping_group(start, prop="scale"):
    p = Project(640, 360, "#ffffff")
    p.apply([
        {"type": "shape", "shape": "path", "name": "a", "path": PATH,
         "x": 100, "y": 50, "width": 50, "height": 90, "fill": "#d4241c"},
        {"type": "shape", "shape": "rectangle", "name": "b", "x": 200, "y": 100, "width": 40, "height": 80,
         "fill": "#141414"},
        {"type": "group", "name": "g", "targets": ["a", "b"]},
        {"type": "pivot", "target": "g", "value": [0.5, 1]},
        {"type": "timeline-set", "duration": 2000, "fps": 24},
        {"type": "keyframe", "target": "g", "property": prop, "time": 0, "value": start, "easing": "hold"},
        {"type": "keyframe", "target": "g", "property": prop, "time": 1000, "value": 1},
    ])
    return p


@pytest.fixture
def bounded_rasters(monkeypatch):
    """Fail on any raster larger than a few canvases: the bug asked for gigabytes."""
    original = Image.new

    def new(mode, size, *args, **kwargs):
        assert size[0] * size[1] <= 4 * 640 * 360, f"unbounded raster {size}"
        return original(mode, size, *args, **kwargs)

    monkeypatch.setattr(Image, "new", new)


@pytest.mark.parametrize("prop", ["scale", "scale-x", "scale-y"])
def test_group_with_a_path_at_scale_zero_draws_nothing(bounded_rasters, prop):
    image = render_at(popping_group(0, prop), 0)
    assert (np.asarray(image.convert("RGB")) == 255).all()


@pytest.mark.parametrize("start", [1e-7, 1e-5, 1e-3])
def test_group_with_a_path_near_scale_zero_stays_bounded(bounded_rasters, start):
    image = render_at(popping_group(start), 0)
    changed = (np.asarray(image.convert("RGB")) != 255).any(axis=2).sum()
    assert changed < 50


def test_group_renders_normally_once_scaled_up():
    image = render_at(popping_group(0), 1000)
    assert (np.asarray(image.convert("RGB")) != 255).any(axis=2).sum() > 4000
