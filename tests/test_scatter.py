"""Scatter, seamless pattern tiles, stepped repeats, sampled keys, line boil and the fur looks (#256, #240, #216, #247)."""

import json
import math

import numpy as np
import pytest
from shapely.geometry import Point, Polygon

from vixl import Project, VixlError
from vixl.model import Limits
from vixl.render import resolve_layout
from vixl.scatter import ghosts, outline, toroidal_poisson


def stage(limits=None):
    project = Project(600, 400, "#ffffff", limits=limits)
    project.apply([
        {"type": "shape", "shape": "ellipse", "name": "blob", "x": 100, "y": 80, "width": 400, "height": 240,
         "fill": "#c58b52"},
        {"type": "shape", "shape": "star", "name": "dot", "x": 10, "y": 10, "width": 20, "height": 20, "fill": "#223355"},
        {"type": "shape", "shape": "ellipse", "name": "pea", "x": 40, "y": 10, "width": 14, "height": 14, "fill": "#e4572e"},
        {"type": "shape", "shape": "rectangle", "name": "hole", "x": 250, "y": 150, "width": 100, "height": 100,
         "fill": "#eeeeee"},
    ])
    return project


def centers(project, group):
    bounds = resolve_layout(project)
    kids = [x for x in project.state["layers"] if x.get("parent") == project.layer(group)["id"]]
    origin = bounds[project.layer(group)["id"]]
    return [(origin[0] + b[0] + b[2] / 2, origin[1] + b[1] + b[3] / 2) for b in (bounds[k["id"]] for k in kids)]


def test_scatter_inside_is_seeded_spaced_inside_and_clear_of_exclusions():
    project = stage()
    op = {"type": "scatter", "target": "blob", "source": ["dot", "pea"], "count": 60, "seed": 3, "rotation_jitter": 180,
          "scale_jitter": 0.3, "exclude": ["hole"], "name": "confetti"}
    result = project.apply(op)
    report = result["scatter"][0]
    assert report["name"] == "confetti" and 40 <= report["copies"] <= 60
    points = centers(project, "confetti")
    assert len(points) == report["copies"]
    region = Polygon(outline(project, project.layer("blob"))[0][0])
    hole = Polygon([(250, 150), (350, 150), (350, 250), (250, 250)])
    assert all(region.buffer(1).contains(Point(p)) for p in points)
    assert not any(hole.contains(Point(p)) for p in points)
    nearest = min(math.dist(a, b) for i, a in enumerate(points) for b in points[i + 1:])
    assert nearest >= report["spacing"] * 0.8  # jitter-free Poisson spacing, measured on rotated bounds
    assert not project.layer("dot")["visible"] and not project.layer("pea")["visible"]
    # The same seed gives the same scatter; another seed a different one.
    again = stage()
    again.apply(op)
    assert centers(again, "confetti") == points
    other = stage()
    other.apply({**op, "seed": 4})
    assert centers(other, "confetti") != points


def test_merge_draws_one_path_per_tone_and_counts_few_layers():
    project = stage()
    before = len(project.state["layers"])
    report = project.apply({"type": "scatter", "target": "blob", "source": "dot", "count": 400, "seed": 1,
                            "tone_variation": 0.1, "tones": 3, "merge": True, "name": "stars"})["scatter"][0]
    assert report["copies"] > 300
    group = project.layer("stars")
    tones = [x for x in project.state["layers"] if x.get("parent") == group["id"]]
    assert group["type"] == "group" and 2 <= len(tones) <= 3
    assert all(x["shape"] == "path" for x in tones) and len({x["fill"] for x in tones}) == len(tones)
    assert len(project.state["layers"]) - before == len(tones) + 1
    # The merged geometry renders where the copies would be: inside the blob, not outside it.
    image = np.asarray(project.render().convert("RGB"), dtype=int)
    assert (np.abs(image[200, 300] - [255, 255, 255]).sum() > 0)
    assert (image[20:60, 520:590] == 255).all()


def test_layer_budget_comes_from_limits_and_merge_is_the_way_out():
    project = stage(Limits(max_layers=40))
    with pytest.raises(VixlError) as caught:
        project.apply({"type": "scatter", "target": "blob", "source": "dot", "count": 80, "seed": 1})
    assert caught.value.code == "resource_limit" and "merge" in str(caught.value)
    project.apply({"type": "scatter", "target": "blob", "source": "dot", "count": 80, "seed": 1, "merge": True})


def test_along_points_base_on_the_edge_and_outward():
    project = Project(400, 400, "#ffffff")
    project.apply({"type": "shape", "shape": "ellipse", "name": "disc", "x": 100, "y": 100, "width": 200,
                   "height": 200, "fill": "#333"})
    project.apply({"type": "scatter", "target": "disc", "mark": {"mark": "tuft", "width": 10, "height": 30},
                   "placement": "along", "count": 24, "seed": 2, "name": "rays"})
    group = project.layer("rays")
    for layer in [x for x in project.state["layers"] if x.get("parent") == group["id"]]:
        b = resolve_layout(project)[layer["id"]]
        g = resolve_layout(project)[group["id"]]
        cx, cy = g[0] + b[0] + b[2] / 2, g[1] + b[1] + b[3] / 2
        # Base on the circle, so the centre sits half a tuft outside it, along the radius it points along.
        assert math.dist((cx, cy), (200, 200)) == pytest.approx(115, abs=2)
        up = (math.sin(math.radians(layer["rotation"])), -math.cos(math.radians(layer["rotation"])))
        radial = ((cx - 200) / 115, (cy - 200) / 115)
        assert up[0] * radial[0] + up[1] * radial[1] > 0.98


def test_fur_preset_puts_tufts_behind_and_flicks_in_front():
    project = stage()
    report = project.apply({"type": "scatter", "target": "blob", "preset": "fur", "seed": 1})["scatter"][0]
    order = [x["name"] for x in project.state["layers"]]
    assert report["layers"] == ["blob-fur", "blob-fur-flicks"] and report["flicks"] > 0
    assert order.index("blob-fur") < order.index("blob") < order.index("blob-fur-flicks")
    tufts = project.layer("blob-fur")
    assert tufts["shape"] == "path" and tufts["scatter"]["preset"] == "fur"
    assert project.layer("blob-fur-flicks")["fill"] != tufts["fill"]


def test_toroidal_poisson_keeps_its_spacing_across_the_seams():
    rng = np.random.default_rng(5)
    points = toroidal_poisson(rng, 200, 120, 30, 500)
    assert len(points) > 12
    for i, (ax, ay) in enumerate(points):
        for bx, by in points[i + 1:]:
            dx, dy = abs(ax - bx), abs(ay - by)
            assert math.hypot(min(dx, 200 - dx), min(dy, 120 - dy)) >= 30 - 1e-9
    assert ghosts((190, 50, 20, 20), 200, 120) == [(-200, 0)]
    assert sorted(ghosts((-5, -5, 20, 20), 200, 120)) == [(0, 120), (200, 0), (200, 120)]


def test_pattern_scatter_is_seamless_reports_its_seam_and_rewraps_after_a_motif_edit():
    project = stage()
    op = {"type": "pattern-scatter", "source": ["dot", "pea"], "width": 160, "height": 160, "count": 14, "seed": 4,
          "rotation_jitter": 180, "background": "#f3e9d2", "pattern": "confetti", "name": "tile"}
    report = project.apply(op)["pattern_scatter"][0]
    assert report["ghosts"] > 0 and report["seam"]["seamless"] and report["pattern"] == "confetti"
    tile = project.layer("tile")
    assert (tile["content_width"], tile["content_height"]) == (160, 160)
    assert tile["pattern_scatter"]["source"] == [project.layer("dot")["id"], project.layer("pea")["id"]]
    from vixl.scatter import tile_image

    image = np.asarray(tile_image(project, tile).convert("RGB"), dtype=int)
    # Wrapped: the left and right columns (and top and bottom rows) continue each other.
    assert np.abs(image[:, 0] - image[:, -1]).mean() < 25 and np.abs(image[0] - image[-1]).mean() < 25
    stored = project.state["patterns"]["confetti"]
    assert (stored["width"], stored["height"]) == (160, 160)
    first = [(x["x"], x["y"]) for x in project.state["layers"] if x.get("parent") == tile["id"]]
    project.apply({"type": "shape", "target": "pea", "width": 40, "height": 40})
    again = project.apply({"type": "pattern-scatter", "target": "tile"})["pattern_scatter"][0]
    assert again["copies"] == report["copies"] and again["seam"]["seamless"]
    peas = [x for x in project.state["layers"] if x.get("parent") == tile["id"] and x["fill"] == "#e4572e"]
    assert peas and all(x["width"] == pytest.approx(40) for x in peas)
    assert [(x["x"], x["y"]) for x in project.state["layers"] if x.get("parent") == tile["id"]] != first
    merged = project.apply({"type": "pattern-scatter", "target": "tile", "merge": True})["pattern_scatter"][0]
    assert merged["seam"]["seamless"]
    assert all(x["type"] == "shape" for x in project.state["layers"] if x.get("parent") == tile["id"])


def test_scatter_inside_keeps_whole_motifs_inside_the_outline():  # #362
    project = Project(400, 300, "#ffffff")
    project.apply([
        {"type": "shape", "shape": "rounded-rectangle", "name": "card", "x": 40, "y": 40, "width": 320, "height": 220,
         "radius": 40, "fill": "#f3e9d2"},
        {"type": "shape", "shape": "ellipse", "name": "dot", "x": 0, "y": 0, "width": 30, "height": 30, "fill": "#223355"},
    ])
    project.apply({"type": "scatter", "target": "card", "source": ["dot"], "count": 30, "seed": 2, "scale_jitter": 0.3,
                   "name": "dots"})
    region = Polygon(outline(project, project.layer("card"))[0][0])
    bounds = resolve_layout(project)
    origin = bounds[project.layer("dots")["id"]]
    copies = [x for x in project.state["layers"] if x.get("parent") == project.layer("dots")["id"]]
    assert len(copies) >= 10
    for copy in copies:
        x, y, w, h = bounds[copy["id"]]
        disc = Point(origin[0] + x + w / 2, origin[1] + y + h / 2).buffer(max(w, h) / 2)
        assert region.buffer(0.5).contains(disc), copy["name"]


def test_wrapped_motifs_of_a_canvas_sized_tile_are_not_reported_as_cut_off():  # #354
    project = Project(160, 160, "#ffffff")
    project.apply([
        {"type": "shape", "shape": "star", "name": "dot", "x": 10, "y": 10, "width": 30, "height": 30, "fill": "#223355"},
        {"type": "shape", "shape": "ellipse", "name": "pea", "x": 40, "y": 10, "width": 24, "height": 24, "fill": "#e4572e"},
    ])
    result = project.apply({"type": "pattern-scatter", "source": ["dot", "pea"], "width": 160, "height": 160, "count": 14,
                            "seed": 4, "name": "tile"})
    assert result["pattern_scatter"][0]["ghosts"] > 0
    assert "cut off" not in json.dumps(result)
    bounds = [x for x in project.check(checks=["bounds"])["issues"] if x["check"] == "bounds"]
    assert bounds and all(x["severity"] == "info" and x.get("intentional") for x in bounds), bounds
    assert all("seamless pattern tile" in x["message"] for x in bounds)


def test_pattern_define_reports_its_seam_check():
    project = stage()
    result = project.apply({"type": "pattern-define", "name": "blobby", "target": "blob"})
    assert result["patterns"][0]["name"] == "blobby" and "edge_error" in result["patterns"][0]["seam"]


def test_tile_variation_varies_each_repeat_and_is_seeded():
    project = Project(240, 240, "#ffffff")
    project.apply({"type": "solid", "name": "ground", "color": "#ffffff"})
    project.apply({"type": "pattern-fill", "target": "ground", "pattern": "checker", "spacing": 40, "name": "plain"})
    plain = np.asarray(project.render().convert("RGB"), dtype=int)
    project.apply({"type": "remove", "target": "plain"})
    project.apply({"type": "pattern-fill", "target": "ground", "pattern": "checker", "spacing": 40,
                   "tile_variation": 1, "seed": 3, "name": "varied"})
    varied = np.asarray(project.render().convert("RGB"), dtype=int)
    cells = {tuple(varied[y, x]) for y in range(20, 240, 80) for x in range(20, 240, 80)}
    assert len({tuple(plain[y, x]) for y in range(20, 240, 80) for x in range(20, 240, 80)}) == 1
    assert len(cells) > 3


def test_repeat_with_steps_makes_real_copies_and_merge_makes_one_path():
    project = stage()
    project.apply({"type": "repeat", "target": "dot", "count": 5, "dx": 40, "rotation_step": 20, "scale_step": 0.8,
                   "opacity_step": -0.2, "name": "trail"})
    copies = [x for x in project.state["layers"] if x.get("parent") == project.layer("trail")["id"]]
    assert [round(x["rotation"]) for x in copies] == [0, 20, 40, 60, 80]
    assert [round(x["opacity"], 2) for x in copies] == [1, 0.8, 0.6, 0.4, 0.2]
    assert copies[-1]["width"] == pytest.approx(20 * 0.8 ** 4)
    assert "repeat" not in copies[0]
    project.apply({"type": "repeat", "target": "pea", "count": 6, "dx": -30, "rotation_jitter": 30, "seed": 2,
                   "merge": True, "name": "peas"})
    peas = project.layer("peas")
    assert peas["shape"] == "path" and peas["path"].count("M") == 6
    with pytest.raises(VixlError):
        project.layer("pea")
    # A plain repeat stays one live layer.
    project.apply({"type": "repeat", "target": "hole", "count": 3, "dx": 10})
    assert project.layer("hole")["repeat"]["count"] == 3


def test_radial_repeat_steps_and_merge():
    project = stage()
    project.apply({"type": "radial-repeat", "target": "pea", "count": 8, "cx": 300, "cy": 200, "opacity_step": -0.1,
                   "name": "ring"})
    kids = [x for x in project.state["layers"] if x.get("parent") == project.layer("ring")["id"]]
    assert sorted(round(x["opacity"], 2) for x in kids) == [0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
    project.apply({"type": "radial-repeat", "target": "dot", "count": 12, "cx": 300, "cy": 200, "mirror": True,
                   "rotation_jitter": 10, "seed": 1, "merge": True, "name": "star-ring"})
    ring = project.layer("star-ring")
    assert ring["type"] == "shape" and ring["path"].count("M") == 24


def test_keyframes_sample_writes_waves_as_keys():
    project = stage()
    project.apply({"type": "timeline-set", "duration": 2000, "fps": 24})
    project.apply({"type": "keyframes", "target": "dot", "property": "rotation",
                   "sample": {"fn": "sin", "period": 1000, "amplitude": 10, "offset": 5, "step_ms": 125,
                              "duration": 1000}})
    keys = project.state["timeline"]["tracks"][0]["keys"]
    assert len(keys) == 9 and keys[2]["time"] == 250 and keys[2]["value"] == pytest.approx(15)
    assert keys[6]["value"] == pytest.approx(-5)
    project.apply({"type": "keyframes", "target": "pea", "property": "opacity",
                   "sample": {"fn": "square", "period": 500, "amplitude": 0.5, "offset": 0.5, "samples": 4,
                              "duration": 1000}})
    track = next(t for t in project.state["timeline"]["tracks"] if t["property"] == "opacity")
    assert [k["value"] for k in track["keys"]] == [1, 0, 1, 0, 1] and track["keys"][0]["easing"] == "hold"
    noise = {"fn": "noise", "period": 400, "amplitude": 6, "samples": 20, "duration": 1200, "seed": 2}
    project.apply({"type": "keyframes", "target": "hole", "property": "translate-y", "sample": noise})
    values = [k["value"] for k in next(t for t in project.state["timeline"]["tracks"]
                                       if t["property"] == "translate-y")["keys"]]
    assert max(abs(v) for v in values) <= 6 and len(set(values)) > 5
    assert values[0] == pytest.approx(values[-1])  # a whole number of periods loops
    with pytest.raises(VixlError):
        project.apply({"type": "keyframes", "target": "dot", "property": "x"})


def test_line_boil_cycles_wobbled_copies_one_at_a_time():
    project = Project(300, 300, "#ffffff")
    project.apply([{"type": "timeline-set", "duration": 1000, "fps": 24},
                   {"type": "shape", "shape": "ellipse", "name": "ball", "x": 60, "y": 60, "width": 160,
                    "height": 160, "fill": "#e4572e", "stroke": "#111111", "stroke_width": 4}])
    project.apply({"type": "motion", "recipe": "line-boil", "target": "ball", "fps": 10, "variants": 3, "seed": 5})
    boil = project.layer("ball-boil")
    drawings = [x for x in project.state["layers"] if x.get("parent") == boil["id"]]
    assert len(drawings) == 3 and len({x["path"] for x in drawings}) == 3
    assert [x["irregular"]["recipe"]["seed"] for x in drawings] == [5, 6, 7]
    from vixl.timeline import project_at

    for time in (0, 120, 250, 330, 990):
        frame = project_at(project, time)
        shown = [x["name"] for x in frame.state["layers"] if x.get("parent") == boil["id"] and x["visible"]]
        assert len(shown) == 1, (time, shown)
    assert project_at(project, 0).layer("ball")["visible"] and not project_at(project, 120).layer("ball")["visible"]


def test_hand_made_and_plush_looks_remove_cleanly():
    project = stage()
    plain = project.render()
    before = json.dumps(project.state["layers"], sort_keys=True)
    project.apply({"type": "look", "target": "blob", "look": "hand-made"})
    blob = project.layer("blob")
    assert blob["shape"] == "path" and blob["looks"]["hand-made"]["irregular"] == [blob["id"]]
    project.apply({"type": "look", "target": "blob", "look": "plush", "amount": 0.7})
    helpers = [x for x in project.state["layers"] if x.get("part_of") == blob["id"]]
    assert {x["name"] for x in helpers} == {"blob-plush", "blob-plush-flicks"}
    assert helpers[0]["styles"]["gradient-overlay"]
    project.apply({"type": "look", "target": "blob", "look": "plush", "amount": 0.3})  # replaces, never stacks
    assert len([x for x in project.state["layers"] if x.get("part_of") == blob["id"]]) == 2
    for look in ("plush", "hand-made"):
        project.apply({"type": "look", "target": "blob", "look": look, "remove": True})
    assert json.dumps(project.state["layers"], sort_keys=True) == before
    assert np.array_equal(np.asarray(project.render()), np.asarray(plain))
    with pytest.raises(VixlError):
        project.apply([{"type": "text", "text": "Hi", "name": "hi"}, {"type": "look", "target": "hi", "look": "hand-made"}])


def test_fur_blob_preset_grows_tufts_body_and_flicks():
    project = Project(300, 300, "#ffffff")
    project.apply({"type": "organic", "preset": "fur-blob", "name": "fluff", "width": 240, "height": 240,
                   "params": {"tufts": 40, "color": "#b07848"}})
    names = [x["name"] for x in project.state["layers"]]
    assert names == ["fluff/tufts", "fluff/body", "fluff/flicks", "fluff"]
    assert project.layer("fluff/tufts")["path"].count("M") == 40
