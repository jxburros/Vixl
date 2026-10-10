"""Composited groups are cached under a key covering their whole subtree (#589): an unchanged group is
not composited from its children again, and every input of a descendant reaches the pixels."""

import random

import numpy as np
import pytest
from PIL import Image

from vixl import Project
from vixl import render as R
from vixl.assets import add_image

from test_apply_speed import register, wide_font


def pixels(image):
    return np.asarray(image).astype(int)


def fresh(p):
    q = p.clone()
    q._cache = None
    return R.render(q)


def full(p):
    """A render that cannot reuse the last canvas, so every top-level layer is drawn."""
    if getattr(p._cache, "snapshot", None) is not None:
        p._cache.snapshot = None
    return R.render(p)


def grouped():
    p = Project(600, 400, "white")
    register(p, "brand", wide_font(1))
    register(p, "wide", wide_font(2))
    p.apply([
        {"type": "swatch", "name": "accent", "color": "#cc3300"},
        {"type": "variable", "name": "word", "value": "Hello"},
        {"type": "shape", "shape": "ellipse", "name": "a", "x": 10, "y": 10, "width": 120, "height": 80, "fill": "@accent"},
        {"type": "text", "name": "t", "text": "${word}", "size": 30, "x": 20, "y": 100, "color": "navy", "font": "brand"},
        {"type": "add", "asset": add_image(p, Image.new("RGBA", (40, 30), "green")), "name": "img", "x": 100, "y": 20},
        {"type": "shape", "shape": "star", "name": "s", "x": 200, "y": 100, "width": 80, "height": 80, "fill": "gold"},
        {"type": "shape", "shape": "rectangle", "name": "r", "x": 260, "y": 60, "width": 60, "height": 40, "fill": "#36c"},
        {"type": "shape", "shape": "rectangle", "name": "bg", "x": 0, "y": 300, "width": 600, "height": 100,
         "fill": "#eee"},
    ], detail="brief")
    p.apply([{"type": "group", "targets": ["s", "r"], "name": "inner"},
             {"type": "group", "targets": ["a", "t", "img", "inner"], "name": "outer"},
             {"type": "rotate", "target": "outer", "angle": 8}], detail="brief")
    return p


CHILDREN = {"a", "t", "img", "s", "r", "inner"}


def test_an_unchanged_group_is_not_composited_again(monkeypatch):
    p = grouped()
    first = full(p)
    drawn = []
    original = R.layer_ink
    monkeypatch.setattr(R, "layer_ink", lambda project, layer, bounds: drawn.append(layer["name"]) or original(project, layer, bounds))
    again = full(p)
    assert not CHILDREN & set(drawn)
    assert "outer" in drawn  # looked up, and found in the cache
    assert np.array_equal(pixels(first), pixels(again))
    # A sibling moving over the group recomposites the canvas there, not the group's children.
    p.apply({"type": "move", "target": "bg", "x": 0, "y": 50}, detail="brief")
    drawn.clear()
    image = R.render(p)
    assert not CHILDREN & set(drawn)
    assert np.array_equal(pixels(image), pixels(fresh(p)))


def test_moving_a_group_reuses_its_composited_pixels(monkeypatch):
    p = grouped()
    full(p)
    p.apply({"type": "move", "target": "outer", "x": 140, "y": 30}, detail="brief")
    drawn = []
    original = R.layer_ink
    monkeypatch.setattr(R, "layer_ink", lambda project, layer, bounds: drawn.append(layer["name"]) or original(project, layer, bounds))
    image = full(p)
    assert not CHILDREN & set(drawn)
    assert np.array_equal(pixels(image), pixels(fresh(p)))


EDITS = {
    "child field": lambda p: p.apply({"type": "move", "target": "a", "x": 30, "y": 5}, detail="brief"),
    "child fill": lambda p: p.apply({"type": "shape", "target": "r", "fill": "#0a0"}, detail="brief"),
    "nested child": lambda p: p.apply({"type": "rotate", "target": "s", "angle": 30}, detail="brief"),
    "nested group": lambda p: p.apply({"type": "opacity", "target": "inner", "value": 0.5}, detail="brief"),
    "child font": lambda p: p.apply({"type": "text-set", "target": "t", "font": "wide"}, detail="brief"),
    "child asset": lambda p: p.apply({"type": "replace-contents", "target": "img",
                                      "asset": add_image(p, Image.new("RGBA", (40, 30), "purple"))}, detail="brief"),
    "variable": lambda p: p.apply({"type": "variable", "name": "word", "value": "Changed"}, detail="brief"),
    "swatch": lambda p: p.apply({"type": "swatch", "name": "accent", "color": "#0033cc"}, detail="brief"),
    "hide child": lambda p: p.apply({"type": "hide", "target": "img"}, detail="brief"),
    "restack": lambda p: p.apply({"type": "top", "target": "a"}, detail="brief"),
}


@pytest.mark.parametrize("name", list(EDITS))
def test_every_descendant_input_reaches_the_group(name):
    p = grouped()
    before = pixels(full(p))
    EDITS[name](p)
    after = pixels(full(p))
    assert not np.array_equal(before, after), name
    assert np.array_equal(after, pixels(fresh(p))), name


def test_cached_groups_match_full_renders_through_random_edits():
    random.seed(11)
    p = grouped()
    names = ["a", "t", "img", "s", "r", "inner", "outer", "bg"]
    edits = [
        lambda n: {"type": "move", "target": n, "x": random.randint(-50, 500), "y": random.randint(-50, 350)},
        lambda n: {"type": "opacity", "target": n, "value": round(random.random(), 2)},
        lambda n: {"type": "rotate", "target": n, "angle": random.randint(0, 359)},
        lambda n: {"type": random.choice(["hide", "show"]), "target": n},
        lambda n: {"type": "blend", "target": n, "value": random.choice(["normal", "multiply", "screen"])},
    ]
    for step in range(40):
        p.apply(random.choice(edits)(random.choice(names)), detail="brief")
        image = full(p) if step % 2 else R.render(p)
        assert np.array_equal(pixels(image), pixels(fresh(p)))


def test_a_child_clipped_to_a_layer_outside_the_group_is_not_cached():
    p = grouped()
    layers = R.resolved_layers(p)
    bounds = R.resolve_layout(p, layers=layers)
    outer = next(item for item in layers if item["name"] == "outer")
    p._resolution = (p.state, layers, bounds)
    try:
        assert R.subtree_key(p, outer) is not None
        r = next(item for item in layers if item["name"] == "r")
        r["clip"] = next(item for item in layers if item["name"] == "bg")["id"]
        p._subtree_memo = None
        assert R.subtree_key(p, outer) is None
    finally:
        p._resolution = None


def test_a_pathfinder_is_cached_and_follows_its_fill(monkeypatch):
    from vixl import design_render

    p = Project(300, 200, "white")
    p.apply([{"type": "swatch", "name": "ink", "color": "#123456"},
             {"type": "shape", "shape": "ellipse", "name": "a", "x": 20, "y": 20, "width": 120, "height": 120,
              "fill": "@ink"},
             {"type": "shape", "shape": "rectangle", "name": "b", "x": 90, "y": 50, "width": 150, "height": 80},
             {"type": "pathfinder", "name": "u", "targets": ["a", "b"], "mode": "union"}],
            detail="brief")
    before = full(p)
    calls = []
    original = design_render.special_image
    monkeypatch.setattr(design_render, "special_image",
                        lambda project, layer: calls.append(layer["type"]) or original(project, layer))
    assert np.array_equal(pixels(full(p)), pixels(before))
    assert "pathfinder" not in calls
    p.apply({"type": "swatch", "name": "ink", "color": "#ff0000"}, detail="brief")
    after = full(p)
    assert not np.array_equal(pixels(after), pixels(before))
    assert np.array_equal(pixels(after), pixels(fresh(p)))
