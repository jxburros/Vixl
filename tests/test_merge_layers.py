"""rasterize bakes styles and clipping; merge-layers and flatten turn layers into one raster layer."""

import numpy as np
import pytest

from vixl import Project
from vixl.commands import compile_command
from vixl.errors import VixlError


def pixels(p):
    return np.asarray(p.render(), dtype=np.int16)


def same(a, b, tolerance=2):
    return a.shape == b.shape and int(np.abs(a - b).max()) <= tolerance


def scene():
    p = Project(160, 120, "white")
    p.apply([
        {"type": "shape", "shape": "rectangle", "name": "back", "x": 10, "y": 10, "width": 90, "height": 70, "fill": "#2563eb"},
        {"type": "shape", "shape": "ellipse", "name": "disc", "x": 50, "y": 30, "width": 70, "height": 70, "fill": "#f59e0b"},
        {"type": "blend", "target": "disc", "value": "multiply"},
        {"type": "text", "name": "label", "text": "Hi", "size": 30, "color": "#111827", "x": 20, "y": 20},
        {"type": "layer-style", "target": "label", "name": "drop-shadow", "settings": {"dx": 3, "dy": 3, "blur": 2}},
    ])
    return p


def test_rasterize_bakes_layer_styles():
    p = scene()
    before = pixels(p)
    p.apply({"type": "rasterize", "target": "label"})
    layer = p.layer("label")
    assert layer["type"] == "raster" and not layer.get("styles")
    assert layer["provenance"]["original"]["styles"]["drop-shadow"]
    assert same(before, pixels(p))


def test_rasterize_bakes_clipping_and_keeps_pixels_outside_the_canvas():
    p = Project(100, 100, "white")
    p.apply([
        {"type": "shape", "shape": "ellipse", "name": "base", "x": -20, "y": 10, "width": 80, "height": 80, "fill": "#0f766e"},
        {"type": "shape", "shape": "rectangle", "name": "stripe", "x": -30, "y": 40, "width": 120, "height": 20, "fill": "#facc15"},
        {"type": "clip", "target": "stripe", "base": "base"},
    ])
    before = pixels(p)
    p.apply({"type": "rasterize", "target": "stripe"})
    stripe = p.layer("stripe")
    assert "clip" not in stripe and stripe["x"] < 0  # the clipped stripe reaches past the left edge, as the base does
    assert same(before, pixels(p))


def test_merge_layers_composites_blend_modes_among_the_merged_layers():
    p = scene()
    p.apply({"type": "solid", "name": "paper", "color": "white", "width": 160, "height": 120})
    p.apply({"type": "bottom", "target": "paper"})
    before = pixels(p)
    head = p.head
    result = p.apply({"type": "merge-layers", "targets": ["paper", "back", "disc"]})
    names = [x["name"] for x in p.state["layers"]]
    assert names == ["disc", "label"]  # at the topmost merged layer's place, under its name
    merged = p.layer("disc")
    assert merged["type"] == "raster" and merged["blend"] == "normal"
    assert {x["name"] for x in merged["provenance"]["originals"]} == {"paper", "back", "disc"}
    assert merged["provenance"]["type"] == "merged"
    assert same(before, pixels(p))
    assert not result.get("warnings")  # the multiply layer only blended with merged layers over an opaque paper
    p.undo()
    assert p.head == head and [x["name"] for x in p.state["layers"]] == ["paper", "back", "disc", "label"]


def test_merge_warns_when_a_blend_mode_met_layers_below_the_merge():
    p = scene()
    result = p.apply({"type": "merge", "targets": ["disc", "label"], "name": "art"})
    assert any("normal blend mode" in w for w in result["warnings"])
    assert [x["name"] for x in p.state["layers"]] == ["back", "art"]


def test_merge_takes_groups_with_their_members_and_redirects_clipping():
    p = scene()
    p.apply([
        {"type": "group", "name": "pair", "targets": ["back", "disc"]},
        {"type": "shape", "shape": "rectangle", "name": "tint", "x": 0, "y": 0, "width": 160, "height": 120, "fill": "#ff000080"},
        {"type": "clip", "target": "tint", "base": "label"},
    ])
    before = pixels(p)
    p.apply({"type": "merge-layers", "targets": ["pair", "label"]})
    assert [x["name"] for x in p.state["layers"]] == ["label", "tint"]
    assert p.layer("tint")["clip"] == p.layer("label")["id"]
    assert len(p.layer("label")["provenance"]["originals"]) == 4
    # The tint now clips to everything merged, not only to the text.
    assert not same(before, pixels(p))


def test_merge_refuses_layers_in_different_groups_and_discards_hidden_ones():
    p = scene()
    p.apply({"type": "group", "name": "g", "targets": ["back"]})
    with pytest.raises(VixlError, match="share a parent"):
        p.apply({"type": "merge-layers", "targets": ["back", "disc"]})
    p.apply({"type": "hide", "target": "g"})
    result = p.apply({"type": "merge-layers", "targets": ["g", "disc", "label"]})
    assert any("discarded" in w for w in result["warnings"])
    assert [x["name"] for x in p.state["layers"]] == ["label"]


def test_flatten_draws_the_page_into_one_canvas_layer_and_can_keep_hidden_layers(tmp_path):
    p = scene()
    p.apply([{"type": "solid", "name": "paper", "color": "white", "width": 160, "height": 120},
             {"type": "bottom", "target": "paper"},
             {"type": "shape", "shape": "star", "name": "ghost", "width": 30, "height": 30, "fill": "red"},
             {"type": "hide", "target": "ghost"}])
    before = pixels(p)
    kept = p.clone()
    result = p.apply({"type": "flatten"})
    assert [x["name"] for x in p.state["layers"]] == ["flattened"]
    flat = p.layer("flattened")
    assert (flat["width"], flat["height"], flat["x"], flat["y"]) == (160, 120, 0, 0)
    assert flat["provenance"]["type"] == "flattened" and len(flat["provenance"]["originals"]) == 5
    assert any("hidden" in w for w in result["warnings"])
    assert same(before, pixels(p))
    p.save(tmp_path / "flat.vixl")
    assert same(before, pixels(Project.load(tmp_path / "flat.vixl")))
    kept.apply({"type": "flatten", "keep_hidden": True, "name": "art"})
    assert [x["name"] for x in kept.state["layers"]] == ["art", "ghost"]


def test_cli_commands_compile_to_the_operations():
    assert compile_command("merge-layers back disc --name art") == {"type": "merge-layers", "targets": ["back", "disc"], "name": "art"}
    assert compile_command("flatten --keep-hidden") == {"type": "flatten", "keep_hidden": True}
