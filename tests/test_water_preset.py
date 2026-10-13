"""The water scene preset: filled layered bands that fill their box, not line waves."""

import numpy as np

from vixl import Project
from vixl.colors import parse


def sea(**extra):
    p = Project(1080, 1080, "#14263b")
    p.apply({"type": "organic", "preset": "water", "name": "sea", "x": 0, "y": 700, "width": 1080, "height": 380,
             **extra})
    return p


def parts(p):
    group = p.layer("sea")
    return [layer for layer in p.state["layers"] if layer.get("parent") == group["id"]]


def luminance(value):
    r, g, b = parse(value)[:3]
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def test_water_is_filled_bands_that_fill_the_box_edge_to_edge():
    p = sea()
    layers = parts(p)
    bands = [layer for layer in layers if not layer["name"].endswith("-crest")]
    crests = [layer for layer in layers if layer["name"].endswith("-crest")]
    assert [layer["name"] for layer in bands] == [f"sea/band-{i}" for i in range(1, 5)]
    assert len(crests) == 4
    assert all(layer["fill"] not in ("transparent", "none") for layer in layers)
    assert all(layer["stroke"] == "transparent" for layer in layers)
    # Light at the horizon, darker toward the viewer.
    tones = [luminance(layer["fill"]) for layer in bands]
    assert tones == sorted(tones, reverse=True)
    image = np.asarray(p.render().convert("RGB")).astype(int)
    for x in (2, 540, 1077):
        assert tuple(image[1077, x]) != (20, 38, 59)  # the front band reaches the bottom corners
    # Every column of the box is water below the back band's crest line.
    covered = (np.abs(image[760:1080].astype(int) - [20, 38, 59]).sum(axis=2) > 6).mean()
    assert covered > 0.97


def test_water_takes_brand_tones_back_to_front_and_a_seed():
    p = sea(params={"tones": ["#a8d5c8", "#3f7f95", "#14263b"], "bands": 3, "crest": False}, seed=1)
    layers = parts(p)
    assert [layer["fill"] for layer in layers] == ["#a8d5c8", "#3f7f95", "#14263b"]
    q = sea(params={"tones": ["#a8d5c8", "#3f7f95", "#14263b"], "bands": 3, "crest": False}, seed=2)
    assert [layer["path"] for layer in parts(p)] != [layer["path"] for layer in parts(q)]
    r = sea(params={"tones": ["#a8d5c8", "#3f7f95", "#14263b"], "bands": 3, "crest": False}, seed=1)
    assert [layer["path"] for layer in parts(p)] == [layer["path"] for layer in parts(r)]


def test_water_exports_as_vector_paths():
    p = sea()
    svg = p.export(format="SVG", svg_policy="strict")
    assert b"<image" not in svg and svg.count(b"<path") >= 8
