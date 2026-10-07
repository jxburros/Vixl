"""The overlap check reads each text layer's coverage without drawing a canvas-sized surface (#327)."""

import numpy as np
import pytest

from vixl import Project
from vixl import render
from vixl.render import layer_canvas_alpha, layer_canvas_surface, resolve_layout, resolved_layers


def document():
    p = Project(500, 300, "white")
    p.apply([
        {"type": "text", "name": "plain", "text": "Overlap", "size": 40, "color": "black", "x": 20, "y": 20},
        {"type": "text", "name": "faded", "text": "Overlap", "size": 40, "color": "black", "x": 40, "y": 30,
         "opacity": 0.37},
        {"type": "text", "name": "edge", "text": "Off the edge", "size": 50, "color": "black", "x": 380, "y": 260},
        {"type": "text", "name": "turned", "text": "Turned", "size": 36, "color": "black", "x": 60, "y": 40,
         "rotation": 23},
        {"type": "text", "name": "fractional", "text": "Half", "size": 33, "color": "black", "x": 70.5, "y": 41.5},
        {"type": "text", "name": "hidden", "text": "Hidden", "size": 30, "color": "black", "x": 30, "y": 30},
        {"type": "shape", "shape": "ellipse", "name": "dot", "x": 50, "y": 25, "width": 80, "height": 60,
         "fill": "red", "opacity": 0.5},
        {"type": "text", "name": "blurred", "text": "Blur", "size": 40, "color": "black", "x": 90, "y": 50},
    ])
    p.apply([{"type": "hide", "target": "hidden"}, {"type": "effect", "target": "blurred", "name": "blur", "amount": 3}])
    return p


@pytest.mark.parametrize("box", [(0, 0, 500, 300), (30, 25, 170, 90), (370, 250, 500, 300), (75, 45, 76, 46)])
def test_alpha_in_a_box_matches_the_canvas_surface(box):
    p = document()
    layers = {item["id"]: item for item in resolved_layers(p)}
    bounds = resolve_layout(p, layers=list(layers.values()))
    for layer in layers.values():
        expected = layer_canvas_surface(p, layer, bounds, layers).getchannel("A").crop(box)
        actual = layer_canvas_alpha(p, layer, box, bounds, layers)
        assert actual.size == expected.size and np.array_equal(np.asarray(actual), np.asarray(expected)), layer["name"]


def test_overlap_issues_are_unchanged(monkeypatch):
    p = document()
    fast = p.check(checks=["overlap"])

    def full(project, layer, box, bounds, index):
        return layer_canvas_surface(project, layer, bounds, index).getchannel("A").crop(box)

    monkeypatch.setattr(render, "layer_canvas_alpha", full)
    assert p.check(checks=["overlap"]) == fast
    assert any(issue["check"] == "overlap" for issue in fast["issues"])


def test_overlap_check_draws_no_canvas_sized_surface_for_top_level_text(monkeypatch):
    p = Project(3000, 3000, "white")
    p.apply([{"type": "text", "name": f"t{i}", "text": f"Dense label {i}", "size": 20, "color": "black",
              "x": (i % 6) * 90, "y": (i // 6) * 16} for i in range(36)])
    calls = []
    original = render.layer_canvas_surface
    monkeypatch.setattr(render, "layer_canvas_surface", lambda *a, **k: calls.append(1) or original(*a, **k))
    report = p.check(checks=["overlap"])
    assert any(issue["check"] == "overlap" for issue in report["issues"])
    assert calls == []
