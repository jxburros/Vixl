"""Camera zoom in films renders the source larger instead of enlarging output pixels (#232)."""

import numpy as np
import pytest
from PIL import Image

from vixl import Project
import vixl.film as film


def soft_pixels(image):
    row = np.asarray(image.convert("L"), dtype=int)[image.height // 2]
    return int(np.count_nonzero((row > 20) & (row < 235)))


def zoomed_frame(tmp_path, source):
    spec = {"width": 200, "height": 100, "fps": 10,
            "shots": [{"source": source, "duration": 100, "camera": {"from": [0.5, 0.5, 2], "to": [0.5, 0.5, 2]}}]}
    return next(film.frames(spec, tmp_path))


@pytest.fixture
def sources(tmp_path):
    p = Project(200, 100)
    p.apply([{"type": "solid", "name": "bg", "color": "black"},
             {"type": "shape", "name": "bar", "shape": "rectangle", "x": 100, "y": 0, "width": 100, "height": 100, "fill": "white"},
             {"type": "text", "name": "t", "text": "Hi", "x": 70, "y": 30, "size": 20, "color": "white"}])
    p.save(tmp_path / "doc.vixl")
    image = Image.new("RGB", (400, 200), "black")
    image.paste((255, 255, 255), (201, 0, 400, 200))
    image.save(tmp_path / "still.png")
    return tmp_path


@pytest.mark.parametrize("source", ["doc.vixl", "still.png"])
def test_zoomed_edges_are_as_sharp_as_a_native_render(sources, source, monkeypatch):
    sharp = zoomed_frame(sources, source)
    assert sharp.size == (200, 100)
    monkeypatch.setattr(film, "MAX_SUPERSAMPLE", 1)
    soft = zoomed_frame(sources, source)
    assert soft_pixels(sharp) <= 1 < soft_pixels(soft)


def test_supersampling_is_bounded_by_the_pixel_budget():
    from vixl.model import Limits
    shot = {"camera": {"from": [0.5, 0.5, 1], "to": [0.5, 0.5, 16]}}
    assert film.supersample(shot, (100, 100), Limits()) == film.MAX_SUPERSAMPLE
    assert film.supersample(shot, (1000, 1000), Limits(max_pixels=2_250_000)) == 1.5
    assert film.supersample({}, (100, 100), Limits()) == 1
