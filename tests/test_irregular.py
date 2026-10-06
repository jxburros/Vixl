"""Irregularity engine: seeded, bounded imperfection for vector layers, and torn edges."""

from copy import deepcopy
import math

import numpy as np
import pytest

from vixl import Project
from vixl.errors import VixlError
from vixl.irregular import (
    STRENGTHS,
    correlated_noise,
    flatten,
    layer_outline,
    ribbon,
    roughen,
    roughen_path,
    stream,
    torn_edge,
    torn_shapes,
)

CIRCLE = "M100 0 C155 0 200 45 200 100 C200 155 155 200 100 200 C45 200 0 155 0 100 C0 45 45 0 100 0 Z"
SQUARE = "M0 0 L200 0 L200 200 L0 200 Z"
LEAF = "M0 50 C20 0 60 0 80 50 C60 100 20 100 0 50 Z"


def distance_to_outline(points, outline):
    """Distance from each of ``points`` to the nearest of a (dense) set of outline points."""
    dense = []
    for p, _, closed in outline:
        seq = np.vstack([p, p[:1]]) if closed else p
        for a, b in zip(seq, seq[1:]):
            dense.append(a + (b - a) * np.linspace(0, 1, max(2, int(np.hypot(*(b - a)))))[:, None])
    dense = np.vstack(dense)
    return np.array([np.hypot(*(dense - q).T).min() for q in points])


def sketch():
    p = Project(500, 400, "white")
    p.apply([{"type": "shape", "shape": "rectangle", "name": "box", "width": 200, "height": 140, "x": 30, "y": 30,
              "fill": "#a8d5c8", "stroke": "#14263b", "stroke_width": 6},
             {"type": "shape", "shape": "path", "name": "line", "path": "M0 60 C60 0 140 120 200 60", "width": 200,
              "height": 120, "x": 260, "y": 30, "fill": "transparent", "stroke": "#14263b", "stroke_width": 8},
             {"type": "shape", "shape": "ellipse", "name": "egg", "width": 120, "height": 90, "x": 40, "y": 240,
              "fill": "#f2a541"}])
    return p


def leaves(count=24):
    p = Project(900, 500, "white")
    p.apply([{"type": "shape", "shape": "path", "name": f"leaf{i}", "path": LEAF, "width": 80, "height": 100,
              "x": 20 + (i % 8) * 105, "y": 20 + (i // 8) * 130, "fill": "#4f8a3b", "stroke": "#1d3b14",
              "stroke_width": 3} for i in range(count)])
    p.apply([{"type": "group", "name": "leaves", "targets": [f"leaf{i}" for i in range(count)]}])
    return p


# --- noise and outlines ------------------------------------------------------------------------


def test_noise_is_bounded_seeded_and_closed_loops_have_no_seam():
    arc = np.linspace(0, 500, 4000, endpoint=False)
    a = correlated_noise(stream(3), arc, 40, 500, True, 3, 0.5)
    assert np.array_equal(a, correlated_noise(stream(3), arc, 40, 500, True, 3, 0.5))
    assert not np.array_equal(a, correlated_noise(stream(4), arc, 40, 500, True, 3, 0.5))
    assert a.min() >= -1 and a.max() <= 1 and a.max() - a.min() > 0.8
    assert abs(a[0] - a[-1]) < 0.05, "a closed outline continues smoothly across its seam"
    open_ = correlated_noise(stream(3), arc, 40, 500, False, 1)
    assert open_.min() >= -1 and open_.max() <= 1


def test_correlation_length_sets_how_fast_the_noise_changes():
    arc = np.linspace(0, 1000, 5000)
    fast = correlated_noise(stream(1), arc, 10, 1000, False, 1)
    slow = correlated_noise(stream(1), arc, 200, 1000, False, 1)
    assert np.abs(np.diff(fast)).mean() > 4 * np.abs(np.diff(slow)).mean()
    rough = correlated_noise(stream(1), arc, 100, 1000, False, 4, 0.7)
    smooth = correlated_noise(stream(1), arc, 100, 1000, False, 1)
    assert np.abs(np.diff(rough)).mean() > np.abs(np.diff(smooth)).mean()


def test_roughen_path_is_deterministic_bounded_and_moves_the_outline():
    a = roughen_path(CIRCLE, 5, wobble=4, length=30, jitter=1.5)
    assert a == roughen_path(CIRCLE, 5, wobble=4, length=30, jitter=1.5)
    assert a != roughen_path(CIRCLE, 6, wobble=4, length=30, jitter=1.5)
    original = flatten(CIRCLE)
    moved = np.vstack([p for p, _, _ in flatten(a)])
    away = distance_to_outline(moved, original)
    assert away.max() <= 4 + 1.5 + 0.6, "no point leaves wobble + jitter (plus sampling) of the source"
    assert away.max() > 1.5, "and the outline does move"
    assert roughen_path(CIRCLE, 5, wobble=0.5, length=30) != roughen_path(CIRCLE, 5, wobble=6, length=30)


def test_corners_survive_wobble_and_vertices_follow_jitter():
    corners = np.array([[0, 0], [200, 0], [200, 200], [0, 200]])
    pts = np.vstack([p for p, _, _ in flatten(roughen_path(SQUARE, 2, wobble=3, length=40))])
    for corner in corners:
        assert np.hypot(*(pts - corner).T).min() <= 3.01, "a square keeps its corners, displaced by at most the wobble"
    moved = np.vstack([p for p, _, _ in flatten(roughen_path(SQUARE, 2, wobble=0, jitter=8))])
    assert np.hypot(*(moved - corners[0]).T).min() > 0.01 and np.hypot(*(moved - corners[0]).T).min() <= 8.01
    assert len(moved) == 4, "jitter alone moves vertices and adds none"


def test_roughen_streams_are_independent_per_subpath_and_seed_must_be_whole():
    two = "M0 0 L100 0 L100 100 L0 100 Z M300 0 L400 0 L400 100 L300 100 Z"
    subs = roughen(flatten(two), 1, wobble=5, length=20)
    a = subs[0][0] - [0, 0]
    b = subs[1][0] - [300, 0]
    assert a.shape == b.shape and not np.allclose(a, b)
    with pytest.raises(VixlError):
        roughen_path(CIRCLE, -1)


def test_ribbon_widths_follow_the_requested_profile():
    line = np.column_stack([np.linspace(0, 100, 50), np.zeros(50)])
    widths = np.linspace(2, 10, 50)
    (poly, closed), = ribbon(line, False, widths)
    assert closed and len(poly) == 100
    assert abs((poly[0] - poly[-1])[1]) == pytest.approx(2) and abs((poly[49] - poly[50])[1]) == pytest.approx(10)
    loops = ribbon(np.array([[0, 0], [10, 0], [10, 10], [0, 10]], float), True, np.full(4, 2.0))
    assert len(loops) == 2


# --- the irregular operation -------------------------------------------------------------------


def snapshot(project):
    return [(layer["name"], layer.get("path"), layer.get("fill"), layer.get("stroke"), layer.get("stroke_width"),
             layer["x"], layer["y"], layer["width"], layer["height"], layer.get("rotation", 0))
            for layer in project.state["layers"]]


def test_seed_is_required_and_remove_needs_none():
    p = sketch()
    with pytest.raises(VixlError) as error:
        p.apply({"type": "irregular", "targets": ["box"]})
    assert "seed" in str(error.value)
    with pytest.raises(VixlError):
        p.apply({"type": "irregular", "target": "box", "seed": -1})
    with pytest.raises(VixlError):
        p.apply({"type": "irregular", "target": "box", "seed": 1, "strength": "wild"})
    p.apply({"type": "irregular", "target": "box", "seed": 1})
    p.apply({"type": "irregular", "target": "box", "remove": True})


def test_same_seed_same_result_and_other_seeds_differ():
    a, b, c = sketch(), sketch(), sketch()
    op = {"type": "irregular", "targets": ["box", "line", "egg"]}
    a.apply({**op, "seed": 4})
    b.apply({**op, "seed": 4})
    c.apply({**op, "seed": 5})
    assert snapshot(a) == snapshot(b)
    assert snapshot(a) != snapshot(c)
    assert a.render().tobytes() == b.render().tobytes() != c.render().tobytes()
    # The result does not depend on how many times a project was loaded or rendered before.
    a.render()
    d = sketch()
    d.apply({**op, "seed": 4})
    assert snapshot(d) == snapshot(a)


@pytest.mark.parametrize("strength", sorted(STRENGTHS))
def test_every_strength_stays_within_its_bounds(strength):
    p = leaves()
    before = {layer["name"]: deepcopy(layer) for layer in p.state["layers"] if layer["type"] == "shape"}
    p.apply({"type": "irregular", "target": "leaves", "seed": 8, "strength": strength})
    preset = STRENGTHS[strength]
    size = max(math.sqrt(80 * 100), 0.35 * 100)
    from vixl.colors import parse, srgb_to_oklab

    spread = set()
    for name, old in before.items():
        new = p.layer(name)
        assert new["shape"] == "path" and new["irregular"]["recipe"]["strength"] == strength
        assert abs(((new["rotation"] - old["rotation"] + 180) % 360) - 180) <= preset["rotation"] + 1e-9
        assert abs(new["x"] - old["x"] + (new["width"] - old["width"]) / 2) <= preset["position"] * size + 1e-9
        assert abs(new["y"] - old["y"] + (new["height"] - old["height"]) / 2) <= preset["position"] * size + 1e-9
        assert 1 - preset["width"] - 1e-9 <= new["stroke_width"] / old["stroke_width"] <= 1 + preset["width"] + 1e-9
        ink = p.layer(f"{name}-ink") if f"{name}-ink" in [x["name"] for x in p.state["layers"]] else None
        for key, now in (("fill", new["fill"]), ("stroke", ink["fill"] if ink else new["stroke"])):
            lightness = srgb_to_oklab(parse(now)[:3])[0] - srgb_to_oklab(parse(old[key])[:3])[0]
            assert abs(lightness) <= preset["lightness"] + 0.006
        spread.add(round(new["rotation"], 3))
    assert len(spread) > 12, "each layer of the set gets its own variation"


def test_explicit_fields_set_exact_bounds_and_zero_switches_an_effect_off():
    p = leaves(30)
    old = {layer["name"]: deepcopy(layer) for layer in p.state["layers"] if layer["type"] == "shape"}
    p.apply({"type": "irregular", "target": "leaves", "seed": 1, "wobble": 0, "jitter": 0, "pressure": 0,
             "rotation_jitter": 2, "position_jitter": 3, "scale_jitter": 0, "lightness_drift": 0.03,
             "hue_drift": 4, "chroma_drift": 0, "width_variation": 0.2})
    rotations, moves, widths = [], [], []
    for name, before in old.items():
        new = p.layer(name)
        assert new["path"] == before["path"] and new["shape"] == "path", "no geometry change was asked for"
        rotations.append(new["rotation"] if new["rotation"] <= 180 else new["rotation"] - 360)
        moves.append(max(abs(new["x"] - before["x"]), abs(new["y"] - before["y"])))
        widths.append(new["stroke_width"] / before["stroke_width"])
    assert max(map(abs, rotations)) <= 2 and max(map(abs, rotations)) > 1.0
    assert max(moves) <= 3 and max(moves) > 1.5
    assert 0.8 <= min(widths) and max(widths) <= 1.2 and max(widths) - min(widths) > 0.2


def test_amount_scales_the_preset_and_only_limits_the_effects():
    base = leaves(12)
    base.apply({"type": "irregular", "target": "leaves", "seed": 1, "amount": 0})
    for layer in base.state["layers"]:
        if layer["type"] == "shape":
            assert layer["path"] == LEAF and layer["rotation"] == 0 and layer["stroke_width"] == 3
    colors = leaves(12)
    colors.apply({"type": "irregular", "target": "leaves", "seed": 1, "only": ["color"]})
    for layer in colors.state["layers"]:
        if layer["type"] == "shape":
            assert layer["path"] == LEAF and layer["rotation"] == 0 and layer["x"] == layer["irregular"]["source"]["x"]
    assert len({layer["fill"] for layer in colors.state["layers"] if layer["type"] == "shape"}) > 6
    loud = leaves(12)
    quiet = leaves(12)
    loud.apply({"type": "irregular", "target": "leaves", "seed": 1, "only": ["placement"], "amount": 2})
    quiet.apply({"type": "irregular", "target": "leaves", "seed": 1, "only": ["placement"], "amount": 0.5})

    def reach(project):
        """How far the centre of any layer moved (the box may grow evenly around it)."""
        return max(abs(layer["x"] + layer["width"] / 2 - layer["irregular"]["source"]["x"] - 40)
                   for layer in project.state["layers"] if layer["type"] == "shape")

    assert reach(loud) > 2 * reach(quiet)


def test_outline_wobble_is_bounded_and_boxes_grow_so_nothing_is_cut_off():
    p = Project(400, 400, "white")
    p.apply({"type": "shape", "shape": "path", "name": "blob", "path": CIRCLE, "width": 200, "height": 200, "x": 100,
             "y": 100, "fill": "#e2725b"})
    source = layer_outline(p.layer("blob"), p)
    p.apply({"type": "irregular", "target": "blob", "seed": 3, "wobble": 9, "wobble_length": 35, "jitter": 0,
             "only": ["wobble"]})
    layer = p.layer("blob")
    assert layer["width"] > 200 and layer["x"] < 100, "the box grew evenly to hold the bulges"
    assert layer["x"] + layer["width"] / 2 == pytest.approx(200) and layer["y"] + layer["height"] / 2 == pytest.approx(200)
    grown = int(layer["width"] - 200) // 2
    new = np.vstack([pts for pts, _, _ in layer_outline(layer, p)]) - grown
    assert distance_to_outline(new, source).max() <= 9.6
    assert new.min() >= -9.6 and new.max() <= 209.6
    # Nothing was cut off at the old box: the drawn area is the area of the outline itself.
    ink = np.asarray(p.render().convert("L")) < 250
    outline = layer_outline(layer, p)
    polygon = sum(abs(0.5 * np.dot(pts[:, 0], np.roll(pts[:, 1], -1)) - 0.5 * np.dot(pts[:, 1], np.roll(pts[:, 0], -1)))
                  for pts, _, _ in outline)
    assert ink.sum() == pytest.approx(polygon, rel=0.02)
    ys, xs = np.nonzero(ink)
    assert xs.min() >= 100 - 9.6 and xs.max() <= 299 + 9.6 and ys.min() >= 100 - 9.6 and ys.max() <= 299 + 9.6


def test_a_primitive_becomes_a_path_that_looks_like_it_did():
    p = Project(300, 300, "white")
    shapes = [("rectangle", {}), ("rounded-rectangle", {"radius": 20}), ("ellipse", {}), ("star", {}),
              ("polygon", {"sides": 6}), ("heart", {}), ("capsule", {}), ("arc", {"start_angle": 0, "end_angle": 200,
                                                                              "inner_radius": 0.4})]
    for i, (shape, extra) in enumerate(shapes):
        p.apply({"type": "shape", "shape": shape, "name": f"s{i}", "width": 120, "height": 80, "x": 20, "y": 20,
                 "fill": "#000000", "stroke": "#ff0000", "stroke_width": 6, **extra})
    for i, (shape, _) in enumerate(shapes):
        plain = Project(300, 300, "white")
        plain.state["layers"].append(deepcopy(p.layer(f"s{i}")))
        plain.state["active_layer"] = plain.state["layers"][0]["id"]
        original = np.asarray(plain.render().convert("L")) < 250
        plain.apply({"type": "irregular", "target": f"s{i}", "seed": 1, "strength": "subtle",
                     "only": ["wobble", "jitter"]})
        layer = plain.layer(f"s{i}")
        assert layer["shape"] == "path", shape
        after = np.asarray(plain.render().convert("L")) < 250
        assert abs(int(after.sum()) - int(original.sum())) < 0.06 * original.sum() + 30, shape
        assert (after & original).sum() > 0.85 * original.sum(), shape


def test_a_path_whose_box_comes_from_its_curves_can_be_made_irregular():
    # Without width/height the box is the path's reach, which is fractional for curves.
    p = Project(300, 300, "white")
    p.apply({"type": "shape", "shape": "path", "name": "blob", "path": "M10 10 C80 0 130 40 121.7 90 Z",
             "fill": "#000000", "stroke": "#ff0000", "stroke_width": 4})
    assert p.layer("blob")["width"] != int(p.layer("blob")["width"])
    p.apply({"type": "irregular", "target": "blob", "seed": 3, "strength": "natural",
             "only": ["wobble", "pressure", "width"]})
    assert p.layer("blob")["irregular"]["recipe"]["seed"] == 3


def test_pressure_turns_a_stroke_into_a_ribbon_with_varying_width():
    p = sketch()
    p.apply({"type": "irregular", "target": "line", "seed": 2, "wobble": 0, "pressure": 0.6, "only": []})
    layer = p.layer("line")
    assert layer["stroke"] == "transparent" and layer["fill"] == "#14263b" and layer["stroke_width"] == 0
    assert layer["path"].count("M") == 1 and layer["path"].rstrip().endswith("Z")
    (outline,) = flatten(layer["path"])
    pts = outline[0]
    half = len(pts) // 2
    left, right = pts[:half], pts[half:][::-1]
    gaps = np.hypot(*(left - right).T)
    assert gaps.max() <= 8 * 1.6 + 0.2 and gaps.min() >= 8 * 0.4 - 0.2 and gaps.max() - gaps.min() > 3
    # A closed filled shape keeps its fill and gets a sibling ribbon for the outline.
    p.apply({"type": "irregular", "target": "box", "seed": 2, "wobble": 0, "pressure": 0.5, "only": []})
    names = [x["name"] for x in p.state["layers"]]
    assert names.index("box-ink") == names.index("box") + 1
    base, ink = p.layer("box"), p.layer("box-ink")
    assert base["stroke"] == "transparent" and base["fill"] == "#a8d5c8" and ink["fill"] == "#14263b"
    assert ink["part_of"] == base["id"] and ink["path"].count("M") == 2
    assert (ink["x"], ink["y"], ink["width"], ink["height"]) == (base["x"], base["y"], base["width"], base["height"])
    # Regrowing replaces the ribbon rather than adding another; remove deletes it.
    p.apply({"type": "irregular", "target": "box", "seed": 9})
    assert [x["name"] for x in p.state["layers"]].count("box-ink") == 1
    p.apply({"type": "irregular", "target": "box", "remove": True})
    assert "box-ink" not in [x["name"] for x in p.state["layers"]]
    assert p.layer("box")["stroke"] == "#14263b" and p.layer("box")["shape"] == "rectangle"


def test_stroke_ribbons_respect_the_layer_limit_and_say_how_to_avoid_it():
    from vixl.model import Limits

    p = Project(900, 500, "white", limits=Limits(max_layers=30))
    p.apply([{"type": "shape", "shape": "path", "name": f"leaf{i}", "path": LEAF, "width": 80, "height": 100,
              "x": i * 30, "fill": "#4f8a3b", "stroke": "#1d3b14", "stroke_width": 3} for i in range(20)])
    with pytest.raises(VixlError) as error:
        p.apply({"type": "irregular", "targets": [f"leaf{i}" for i in range(20)], "seed": 1})
    assert "pressure" in str(error.value) and len(p.state["layers"]) == 20
    p.apply({"type": "irregular", "targets": [f"leaf{i}" for i in range(20)], "seed": 1, "pressure": 0})
    assert len(p.state["layers"]) == 20 and p.layer("leaf3")["stroke"] != "transparent"


def test_regrow_starts_from_the_source_and_remove_restores_it_exactly():
    p = sketch()
    original = snapshot(p)
    names = ["box", "line", "egg"]
    p.apply({"type": "irregular", "targets": names, "seed": 4, "strength": "rough"})
    first = snapshot(p)
    p.apply({"type": "irregular", "targets": names, "seed": 4, "strength": "rough"})
    assert snapshot(p) == first, "applying again with the same seed changes nothing: it does not stack"
    p.apply({"type": "irregular", "targets": names, "seed": 5})
    fresh = sketch()
    fresh.apply({"type": "irregular", "targets": names, "seed": 5, "strength": "rough"})
    assert snapshot(p) == snapshot(fresh), "a new seed regrows from the source and keeps the recipe"
    assert p.layer("box")["irregular"]["recipe"]["seed"] == 5
    p.apply({"type": "irregular", "targets": names, "remove": True})
    assert snapshot(p) == original
    assert not any("irregular" in layer for layer in p.state["layers"])
    with pytest.raises(VixlError):
        p.apply({"type": "irregular", "target": "box", "remove": True})


def test_undo_and_redo_use_normal_history():
    p = sketch()
    before = snapshot(p)
    p.apply({"type": "irregular", "targets": ["box", "line"], "seed": 4})
    after = snapshot(p)
    assert after != before
    p.undo()
    assert snapshot(p) == before
    p.redo()
    assert snapshot(p) == after
    p.apply({"type": "irregular", "targets": ["box", "line"], "seed": 4}, dry_run=True)
    assert snapshot(p) == after


def test_groups_expand_and_non_vector_layers_are_refused():
    p = leaves(5)
    p.apply({"type": "text", "text": "Hello", "name": "title", "size": 30, "x": 10, "y": 300})
    with pytest.raises(VixlError) as error:
        p.apply({"type": "irregular", "target": "title", "seed": 1})
    assert "vector" in str(error.value)
    p.apply({"type": "group", "name": "words", "targets": ["title"]})
    with pytest.raises(VixlError) as error:
        p.apply({"type": "irregular", "target": "words", "seed": 1})
    assert "no vector layers" in str(error.value)
    p.apply({"type": "irregular", "target": "leaves", "seed": 1})
    assert sum("irregular" in layer for layer in p.state["layers"]) == 5
    with pytest.raises(VixlError):
        p.apply({"type": "irregular", "target": "ghost", "seed": 1})


def test_colors_drift_in_oklab_within_bounds_and_keep_alpha():
    from vixl.colors import parse, srgb_to_oklab, to_polar

    p = Project(100, 100)
    p.apply([{"type": "swatch", "name": "brand", "color": "#2255aa"}])
    p.apply([{"type": "shape", "shape": "rectangle", "name": f"r{i}", "width": 20, "height": 20, "x": i * 5,
              "fill": "@brand" if i % 2 else "rgba(200, 40, 40, 0.5)", "stroke": "transparent"} for i in range(20)])
    p.apply({"type": "irregular", "targets": [f"r{i}" for i in range(20)], "seed": 3, "only": ["color"],
             "lightness_drift": 0.05, "hue_drift": 6, "chroma_drift": 0.2})
    for i in range(20):
        layer = p.layer(f"r{i}")
        old = parse("#2255aa" if i % 2 else "rgba(200, 40, 40, 0.5)")
        new = parse(layer["fill"])
        assert new[3] == pytest.approx(old[3], abs=0.01)
        (l0, c0, h0), (l1, c1, h1) = (to_polar(srgb_to_oklab(c[:3])) for c in (old, new))
        assert abs(l1 - l0) <= 0.05 + 0.006 and abs(((h1 - h0 + 180) % 360) - 180) <= 6.5 or c1 < 0.02
        assert layer["stroke"] == "transparent"
    assert len({p.layer(f"r{i}")["fill"] for i in range(1, 20, 2)}) > 5


def test_placement_leaves_constrained_axes_alone():
    p = Project(200, 200)
    p.apply([{"type": "shape", "shape": "rectangle", "name": "a", "width": 20, "height": 20, "x": 10, "y": 10,
              "fill": "#000"}, {"type": "shape", "shape": "rectangle", "name": "b", "width": 20, "height": 20,
                                "x": 10, "y": 50, "fill": "#000"}])
    p.layer("b")["constraints"] = {"left": "a.left"}
    p.apply({"type": "irregular", "targets": ["a", "b"], "seed": 2, "position_jitter": 5, "only": []})
    assert p.layer("b")["x"] == 10 and p.layer("b")["y"] != 50 and p.layer("a")["x"] != 10


def test_save_load_export_and_schema(tmp_path):
    p = sketch()
    p.apply({"type": "irregular", "targets": ["box", "line", "egg"], "seed": 4})
    p.save(tmp_path / "x.vixl")
    loaded = Project.load(tmp_path / "x.vixl")
    assert snapshot(loaded) == snapshot(p) and loaded.render().tobytes() == p.render().tobytes()
    svg = p.export(format="SVG")
    assert b"<image" not in svg and svg.count(b"<path") >= 3
    from vixl.schema import operation_schema, validate_operation

    variants = {v["properties"]["type"]["const"]: v for v in operation_schema()["properties"]["operations"]["items"]["oneOf"]}
    for kind in ("irregular", "tear"):
        for name, prop in variants[kind]["properties"].items():
            if name not in ("type", "target"):
                assert prop.get("type") or prop.get("enum") or prop.get("anyOf"), (kind, name)
        assert variants[kind]["properties"]["seed"]["description"]
    with pytest.raises(VixlError) as error:
        validate_operation({"type": "irregular", "target": "box"})
    assert "seed" in str(error.value) and "remove" in str(error.value)
    note = []
    assert validate_operation({"type": "roughen", "target": "box", "seed": 2}, note)["type"] == "irregular"


def test_cli_compiles_irregular_and_tear():
    from vixl.commands import compile_command

    assert compile_command(["irregular", "box", "egg", "--seed", "3", "--strength", "rough", "--wobble", "2.5",
                            "--only", "wobble", "color"]) == {
        "type": "irregular", "targets": ["box", "egg"], "seed": 3, "strength": "rough", "wobble": 2.5,
        "only": ["wobble", "color"]}
    assert compile_command(["irregular", "box", "--remove"]) == {"type": "irregular", "target": "box", "remove": True}
    assert compile_command(["tear", "photo", "--seed", "2", "--edges", "bottom", "left", "--as", "clip",
                            "--rim-width", "4"]) == {"type": "tear", "target": "photo", "seed": 2,
                                                     "edges": ["bottom", "left"], "as": "clip", "rim_width": 4.0}


def test_mcp_schema_describes_the_new_operations(tmp_path):
    import asyncio
    import json

    from vixl.interfaces import Session
    from vixl.mcp_tools import build_server

    server = build_server(Session(workspace=tmp_path))
    result = asyncio.run(server.call_tool("vixl_operation_schema", {"types": ["irregular", "tear"]}))
    content = result[0] if isinstance(result, tuple) else result
    schema = json.loads(content[0].text)
    assert "wobble_length" in schema["irregular"]["properties"] and "edges" in schema["tear"]["properties"]


# --- torn edges --------------------------------------------------------------------------------


def test_torn_edge_is_bounded_deterministic_and_rougher_when_asked():
    stations, offsets = torn_edge(600, 20, stream(2), length=90, roughness=0.5)
    assert offsets.min() >= 0 and offsets.max() <= 20 and offsets.max() - offsets.min() > 8
    assert stations[0] == 0 and stations[-1] == 600
    again = torn_edge(600, 20, stream(2), length=90, roughness=0.5)[1]
    assert np.array_equal(offsets, again)
    assert not np.array_equal(offsets, torn_edge(600, 20, stream(3), length=90, roughness=0.5)[1])
    gentle = torn_edge(600, 20, stream(2), length=90, roughness=0.0)[1]
    jagged = torn_edge(600, 20, stream(2), length=90, roughness=1.0)[1]
    assert np.abs(np.diff(jagged)).sum() > 1.5 * np.abs(np.diff(gentle)).sum()


def test_torn_shapes_stay_in_the_box_within_the_depth_and_nest():
    w, h, depth, rim = 400, 300, 24, 8
    shapes = torn_shapes(w, h, 7, ("bottom", "left"), depth=depth, length=60, rim=rim, fibres=0.5)
    face, band = shapes["face"], shapes["rim"]
    # The face never leaves the box, and the untorn top and right edges stay on it.
    assert face.min() >= -1e-9 and face[:, 0].max() <= w + 1e-9 and face[:, 1].max() <= h + 1e-9
    assert np.isclose(face[:, 1].min(), 0) and np.isclose(face[:, 0].max(), w)
    assert (face[:, 1] < 1e-9).sum() >= 2, "the untorn top edge stays straight"
    # Nothing is torn deeper than depth: every point is within `depth` of the box outline.
    near = np.minimum.reduce([face[:, 0], w - face[:, 0], face[:, 1], h - face[:, 1]])
    assert np.all(near <= depth + 1e-6)
    # The rim polygon reaches out toward the box edge beyond the face and never leaves the box.
    assert band.min() >= -1e-9 and band[:, 0].max() <= w + 1e-9 and band[:, 1].max() <= h + 1e-9
    assert band[:, 1].max() >= face[:, 1].max() and band[:, 0].min() <= face[:, 0].min()
    assert shapes["fibres"], "fibres were asked for"
    for start, control, end in shapes["fibres"]:
        for point in (start, end):
            assert 0 <= point[0] <= w and 0 <= point[1] <= h
    same = torn_shapes(w, h, 7, ("bottom", "left"), depth=depth, length=60, rim=rim, fibres=0.5)
    assert np.array_equal(face, same["face"]) and len(same["fibres"]) == len(shapes["fibres"])
    other = torn_shapes(w, h, 8, ("bottom", "left"), depth=depth, length=60, rim=rim, fibres=0.5)
    assert not np.array_equal(face, other["face"])
    assert torn_shapes(w, h, 7, (), depth=depth, length=60)["face"].shape == (4, 2)


def paper(rotation=0, **extra):
    p = Project(520, 420, "white")
    p.apply({"type": "shape", "shape": "rectangle", "name": "sheet", "width": 360, "height": 260, "x": 80, "y": 70,
             "fill": "#000000"})
    if rotation:
        p.apply({"type": "rotate", "target": "sheet", "value": rotation})
    return p


def ink(project):
    return np.asarray(project.render().convert("L")) < 128


def test_mask_tear_cuts_the_edge_within_its_depth_and_is_deterministic():
    p, q = paper(), paper()
    full = ink(p)
    op = {"type": "tear", "target": "sheet", "seed": 3, "edges": ["bottom"], "depth": 30, "rim_width": 0, "fibres": 0}
    p.apply(op)
    q.apply(op)
    torn = ink(p)
    assert np.array_equal(torn, ink(q)) and p.render().tobytes() == q.render().tobytes()
    assert (torn & ~full).sum() == 0, "a tear only removes"
    assert np.array_equal(torn[:300], full[:300]), "above depth rows nothing changes"
    assert 0 < (full & ~torn).sum() < 360 * 30
    rows = np.nonzero(torn.any(axis=1))[0]
    assert rows.max() <= 329 and rows.max() >= 300
    p.apply({**op, "seed": 4})
    assert not np.array_equal(torn, ink(p)), "a new seed regrows the edge"
    assert p.layer("sheet")["tear"]["recipe"]["seed"] == 4
    assert len([x for x in p.state["layers"] if x["name"].startswith("sheet")]) == 1, "no rim layers when rim is 0"
    p.apply({"type": "tear", "target": "sheet", "remove": True})
    assert np.array_equal(ink(p), full) and p.layer("sheet")["mask"] is None and "tear" not in p.layer("sheet")


def test_mask_tear_adds_rim_and_fibre_layers_under_the_target_and_regrows_them():
    p = paper()
    p.apply({"type": "tear", "target": "sheet", "seed": 3, "edges": ["bottom", "right"], "strength": "rough"})
    names = [x["name"] for x in p.state["layers"]]
    assert names == ["sheet-rim", "sheet-fibres", "sheet"]
    rim = p.layer("sheet-rim")
    assert rim["part_of"] == p.layer("sheet")["id"] and rim["fill"] == "#fffdf7"
    assert (rim["x"], rim["y"], rim["width"], rim["height"]) == (80, 70, 360, 260)
    before = (rim["path"], p.layer("sheet-fibres")["path"])
    p.apply({"type": "tear", "target": "sheet", "seed": 4})
    names = [x["name"] for x in p.state["layers"]]
    assert sorted(names) == ["sheet", "sheet-fibres", "sheet-rim"], "regrowing replaces the helper layers"
    assert (p.layer("sheet-rim")["path"], p.layer("sheet-fibres")["path"]) != before
    assert p.layer("sheet")["tear"]["recipe"]["strength"] == "rough" and p.layer("sheet")["tear"]["recipe"]["seed"] == 4
    p.apply({"type": "tear", "target": "sheet", "remove": True})
    assert [x["name"] for x in p.state["layers"]] == ["sheet"]
    # Undo brings the tear back in one step.
    p.undo()
    assert len(p.state["layers"]) == 3


def test_tear_keeps_an_existing_mask_and_restores_it():
    p = paper()
    p.apply({"type": "mask", "target": "sheet", "action": "create"})
    half = p.image(p.layer("sheet")["mask"]["asset"], "L").copy()
    half.paste(0, (0, 0, 180, 260))
    from vixl.assets import add_image

    p.layer("sheet")["mask"] = {"asset": add_image(p, half, "masks"), "enabled": True}
    left_cut = ink(p)
    p.apply({"type": "tear", "target": "sheet", "seed": 1, "edges": ["right"], "depth": 25, "rim_width": 0,
             "fibres": 0})
    torn = ink(p)
    assert not torn[70:330, 80:260].any(), "the old mask still applies"
    assert (left_cut & ~torn).sum() > 0
    p.apply({"type": "tear", "target": "sheet", "remove": True})
    assert np.array_equal(ink(p), left_cut)


@pytest.mark.parametrize("rotation", [0, 17, 90, 200])
def test_mask_and_clip_tears_agree_on_turned_layers(rotation):
    """The mask is made in the layer's own box and turned the way the layer is, so it lines up."""
    a, b = paper(rotation), paper(rotation)
    op = {"type": "tear", "target": "sheet", "seed": 6, "edges": ["bottom", "left"], "depth": 26, "rim_width": 0,
          "fibres": 0}
    a.apply({**op, "as": "mask"})
    b.apply({**op, "as": "clip"})
    ia, ib = ink(a), ink(b)
    assert abs(int(ia.sum()) - int(ib.sum())) < 0.01 * ia.sum()
    assert (ia ^ ib).sum() < 0.01 * ia.sum()
    whole = ink(paper(rotation))
    assert (ia & ~whole).sum() < 0.002 * whole.sum() and ia.sum() < whole.sum()


def test_clip_tear_uses_a_vector_face_and_releases_cleanly():
    p = paper()
    p.apply({"type": "tear", "target": "sheet", "as": "clip", "seed": 2, "edges": ["top"], "strength": "natural"})
    sheet = p.layer("sheet")
    face = p.layer("sheet-face")
    assert sheet["clip"] == face["id"] and face["part_of"] == sheet["id"] and face["shape"] == "path"
    assert [x["name"] for x in p.state["layers"]] == ["sheet-rim", "sheet-face", "sheet-fibres", "sheet"]
    path = face["path"]
    p.apply({"type": "tear", "target": "sheet", "seed": 9})
    assert p.layer("sheet-face")["id"] == face["id"] and p.layer("sheet-face")["path"] != path
    assert len(p.state["layers"]) == 4
    with pytest.raises(VixlError):
        p.apply({"type": "tear", "target": "sheet", "seed": 9, "as": "mask"})
    p.apply({"type": "tear", "target": "sheet", "remove": True})
    assert [x["name"] for x in p.state["layers"]] == ["sheet"] and "clip" not in p.layer("sheet")
    p.apply([{"type": "shape", "shape": "rectangle", "name": "base", "width": 50, "height": 50},
             {"type": "clip", "target": "sheet", "base": "base"}])
    with pytest.raises(VixlError) as error:
        p.apply({"type": "tear", "target": "sheet", "as": "clip", "seed": 1})
    assert "already clipped" in str(error.value)


def test_path_tear_draws_free_layers_and_regrows_in_place():
    p = Project(500, 400, "#233044")
    p.apply({"type": "tear", "name": "scrap", "seed": 3, "width": 300, "height": 200, "x": 100, "y": 80, "edges": ["all"],
             "fill": "#f7f1e5", "depth": 20})
    assert [x["name"] for x in p.state["layers"]] == ["scrap-rim", "scrap-face", "scrap-fibres"]
    face = p.layer("scrap-face")
    assert face["tear"]["mode"] == "path" and (face["x"], face["y"]) == (100, 80) and face["fill"] == "#f7f1e5"
    assert p.state["active_layer"] == face["id"]
    d = face["path"]
    shape = ink_where(p, 0.5)
    assert 0.80 < shape.sum() / (300 * 200) < 1.0
    p.apply({"type": "tear", "target": "scrap-face", "seed": 4})
    assert [x["name"] for x in p.state["layers"]] == ["scrap-rim", "scrap-face", "scrap-fibres"]
    assert p.layer("scrap-face")["id"] == face["id"] and p.layer("scrap-face")["path"] != d
    p.apply({"type": "tear", "target": "scrap-face", "remove": True})
    assert not p.state["layers"]
    # With a target, the layers go over it and the box is the target's.
    p.apply({"type": "shape", "shape": "rectangle", "name": "card", "width": 100, "height": 60, "x": 10, "y": 20})
    p.apply({"type": "tear", "target": "card", "as": "path", "seed": 1, "fill": "#fff"})
    assert [x["name"] for x in p.state["layers"]][0] == "card" and p.layer("card-face")["width"] == 100


def ink_where(project, level):
    render = project.render().convert("RGB")
    background = np.asarray(render)[0, 0]
    return np.abs(np.asarray(render).astype(int) - background).sum(axis=2) > 80


def test_tear_errors_say_what_to_do():
    p = paper()
    with pytest.raises(VixlError) as error:
        p.apply({"type": "tear", "target": "sheet"})
    assert "seed" in str(error.value)
    with pytest.raises(VixlError) as error:
        p.apply({"type": "tear", "seed": 1, "as": "mask", "width": 10, "height": 10})
    assert "needs a target" in str(error.value)
    with pytest.raises(VixlError) as error:
        p.apply({"type": "tear", "seed": 1})
    assert "width and height" in str(error.value)
    with pytest.raises(VixlError):
        p.apply({"type": "tear", "target": "sheet", "seed": 1, "edges": ["middle"]})
    with pytest.raises(VixlError):
        p.apply({"type": "tear", "target": "sheet", "remove": True})
    with pytest.raises(VixlError):
        p.apply({"type": "tear", "target": "sheet", "seed": 1, "depth": 0})


def test_a_torn_document_saves_exports_and_rerenders(tmp_path):
    p = paper()
    p.apply({"type": "tear", "target": "sheet", "seed": 3, "edges": ["all"], "strength": "rough"})
    p.save(tmp_path / "t.vixl")
    loaded = Project.load(tmp_path / "t.vixl")
    assert loaded.render().tobytes() == p.render().tobytes()
    assert p.export(format="PDF").startswith(b"%PDF")
    assert len(p.export(format="PNG")) > 1000
    # The rim and fibres are plain vector paths in an SVG export.
    paths = Project(300, 300, "white")
    paths.apply({"type": "tear", "name": "scrap", "seed": 3, "width": 200, "height": 200, "edges": ["all"]})
    svg = paths.export(format="SVG")
    assert b"<image" not in svg and svg.count(b"<path") == 3
