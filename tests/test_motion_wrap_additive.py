"""Seamless scrolls and symmetric turns (wrap, symmetry), additive tracks, blend windows and piecewise samples."""
import json
import math

import pytest

from vixl.checks import check_design
from vixl.errors import VixlError
from vixl.project import Project
from vixl.timeline import export_timeline, inspect_timeline, project_at, render_at, sample_track


def strip():
    p = Project(1200, 400, "#ffffff")
    p.apply({"type": "timeline-set", "duration": 2000, "loop_mode": "seamless"})
    for i in range(3):
        p.apply({"type": "shape", "shape": "rectangle", "name": f"hill-{i}", "x": i * 1200, "y": 250, "width": 600, "height": 150,
                 "fill": "#3a7d44"})
    p.apply({"type": "group", "name": "ground", "targets": ["hill-0", "hill-1", "hill-2"]})
    p.apply({"type": "shape", "shape": "star", "name": "sun", "x": 80, "y": 40, "width": 120, "height": 120, "fill": "#f5b700",
             "points": 12})
    return p


def codes(p, layer=None):
    found = check_design(p, checks=["motion"])["issues"]
    ident = p.layer(layer)["id"] if layer else None
    return [item.get("code") for item in found if item["check"] == "motion" and (layer is None or ident in item.get("layer_ids", []))]


def track(p, layer, prop):
    ident = p.layer(layer)["id"]
    return next(t for t in p.state["timeline"]["tracks"] if t["target"] == ident and t["property"] == prop)


def test_scroll_and_symmetric_turn_without_marks_still_warn():
    p = strip()
    p.apply({"type": "keyframes", "target": "ground", "property": "translate-x",
             "keys": [{"time": 0, "value": 0}, {"time": 2000, "value": -1200}]})
    p.apply({"type": "keyframes", "target": "sun", "property": "rotation",
             "keys": [{"time": 0, "value": 0}, {"time": 2000, "value": 30}]})
    assert sorted(codes(p, "ground")) == ["linear-motion", "loop-seam"]
    assert sorted(codes(p, "sun")) == ["linear-motion", "loop-seam"]


def test_wrap_and_symmetry_make_whole_repeats_seamless(tmp_path):
    p = strip()
    p.apply({"type": "keyframes", "target": "ground", "property": "translate-x", "wrap": 1200,
             "keys": [{"time": 0, "value": 0}, {"time": 2000, "value": -1200}]})
    p.apply({"type": "keyframes", "target": "sun", "property": "rotation", "symmetry": 12,
             "keys": [{"time": 0, "value": 0}, {"time": 2000, "value": 30}]})
    assert track(p, "ground", "translate-x")["wrap"] == 1200
    assert track(p, "sun", "rotation")["symmetry"] == 12
    found = codes(p)
    assert "loop-seam" not in found and "linear-motion" not in found
    # Closing a wrapped track leaves it alone: a closing key would snap the strip back.
    p.apply({"type": "timeline-set", "close": True})
    assert [k["value"] for k in track(p, "ground", "translate-x")["keys"]] == [0, -1200]
    p.save(tmp_path / "strip.vixl")
    assert track(Project.load(tmp_path / "strip.vixl"), "ground", "translate-x")["wrap"] == 1200


def test_wrap_on_keyframe_and_animate_and_a_partial_repeat_still_warns():
    p = strip()
    p.apply({"type": "animate", "target": "ground", "property": "translate-x", "from": 0, "to": -2400, "easing": "linear",
             "wrap": 1200})
    assert codes(p, "ground") == []
    p.apply({"type": "keyframe", "target": "ground", "property": "translate-x", "time": 2000, "value": -1000})
    assert "loop-seam" in codes(p, "ground")
    p.apply({"type": "keyframe", "target": "ground", "property": "translate-x", "time": 2000, "value": -1200, "wrap": 0})
    assert "wrap" not in track(p, "ground", "translate-x")
    with pytest.raises(VixlError):
        p.apply({"type": "keyframe", "target": "ground", "property": "translate-x", "time": 0, "value": 0, "symmetry": 4})
    with pytest.raises(VixlError):
        p.apply({"type": "keyframe", "target": "sun", "property": "visible", "time": 0, "value": True, "wrap": 10})


def test_loop_seam_message_suggests_wrap_or_symmetry():
    p = strip()
    p.apply({"type": "keyframes", "target": "ground", "property": "translate-x",
             "keys": [{"time": 0, "value": 0}, {"time": 2000, "value": -1200}]})
    p.apply({"type": "keyframes", "target": "sun", "property": "rotation",
             "keys": [{"time": 0, "value": 0}, {"time": 2000, "value": 30}]})
    messages = {item["layer_ids"][0]: item["message"] for item in check_design(p, checks=["motion"])["issues"]
                if item.get("code") == "loop-seam"}
    assert "children repeat every 1200 px" in messages[p.layer("ground")["id"]]
    assert "wrap: 1200" in messages[p.layer("ground")["id"]]
    assert "symmetry: 12" in messages[p.layer("sun")["id"]]


def test_scroll_recipe_writes_a_wrapped_constant_speed_track():
    p = strip()
    p.apply({"type": "motion", "recipe": "scroll", "target": "ground", "amount": -2400, "wrap": 1200})
    t = track(p, "ground", "translate-x")
    assert [(k["time"], k["value"]) for k in t["keys"]] == [(0, 0), (2000, -2400)] and t["wrap"] == 1200
    assert codes(p, "ground") == []
    with pytest.raises(VixlError, match="whole multiple"):
        p.apply({"type": "motion", "recipe": "scroll", "target": "ground", "amount": -1000, "wrap": 1200})


def dot():
    p = Project(400, 400, "#ffffff")
    p.apply({"type": "timeline-set", "duration": 2000, "loop_mode": "seamless"})
    p.apply({"type": "shape", "shape": "ellipse", "name": "dot", "x": 180, "y": 180, "width": 40, "height": 40, "fill": "#d1495b"})
    return p


def value(p, prop, time):
    return sample_track(p, track(p, "dot", prop), time)


def test_additive_layer_is_stored_and_summed_at_render(tmp_path):
    p = dot()
    p.apply({"type": "keyframes", "target": "dot", "property": "translate-y",
             "sample": {"fn": "sin", "period": 500, "amplitude": 10, "step_ms": 25}})
    p.apply({"type": "keyframes", "target": "dot", "property": "translate-y", "mode": "add", "additive": "leap",
             "keys": [{"time": 0, "value": 0}, {"time": 500, "value": 0, "easing": "ease-out"},
                      {"time": 1000, "value": -100, "easing": "ease-in"}, {"time": 1500, "value": 0}]})
    t = track(p, "dot", "translate-y")
    assert [layer["layer"] for layer in t["add"]] == ["leap"] and len(t["add"][0]["keys"]) == 4
    base = [k["value"] for k in t["keys"]]
    assert max(base) == pytest.approx(10) and min(base) == pytest.approx(-10)  # The bob's own keys are untouched.
    assert value(p, "translate-y", 1000) == pytest.approx(-100)
    assert value(p, "translate-y", 125) == pytest.approx(10)
    assert value(p, "translate-y", 1125) == pytest.approx(10 + sample_track(p, {"property": "translate-y", "keys": t["add"][0]["keys"]}, 1125))
    assert project_at(p, 1000).layer("dot")["y"] == pytest.approx(80)
    ink = render_at(p, 1000).convert("L").point(lambda v: 0 if v > 250 else 255).getbbox()
    assert ink[1] == pytest.approx(80, abs=1) and ink[3] == pytest.approx(120, abs=1)
    # The document round-trips and the loop checks read the sum.
    p.save(tmp_path / "dot.vixl")
    saved = Project.load(tmp_path / "dot.vixl")
    assert sample_track(saved, track(saved, "dot", "translate-y"), 1000) == pytest.approx(-100)
    assert "loop-seam" not in codes(p)
    info = next(item for item in inspect_timeline(p)["tracks"] if item["property"] == "translate-y")
    assert info["add"][0]["layer"] == "leap"


def test_additive_layer_without_a_track_keys_the_current_value_and_can_be_removed():
    p = dot()
    p.apply({"type": "keyframes", "target": "dot", "property": "rotation", "mode": "add",
             "keys": [{"time": 0, "value": 0}, {"time": 1000, "value": 45}, {"time": 2000, "value": 0}]})
    t = track(p, "dot", "rotation")
    assert t["keys"] == [{"time": 0, "value": 0}] and t["add"][0]["layer"] == "add"
    assert value(p, "rotation", 1000) == 45
    # No target: the active layer. The layer's name is not mistaken for a target layer.
    p.apply({"type": "keyframes", "property": "rotation", "mode": "add", "additive": "sway",
             "keys": [{"time": 0, "value": 0}, {"time": 1000, "value": 5}, {"time": 2000, "value": 0}]})
    assert value(p, "rotation", 1000) == 50
    p.apply({"type": "keyframe-remove", "target": "dot", "property": "rotation", "additive": "add"})
    assert value(p, "rotation", 1000) == 5
    p.apply({"type": "keyframe-remove", "target": "dot", "property": "rotation", "additive": "sway"})
    assert "add" not in track(p, "dot", "rotation")
    with pytest.raises(VixlError):
        p.apply({"type": "keyframe", "target": "dot", "property": "visible", "time": 0, "value": True, "mode": "add"})
    with pytest.raises(VixlError):
        p.apply({"type": "keyframe", "target": "dot", "property": "rotation", "time": 0, "value": 1, "additive": "x"})


def test_an_open_additive_layer_is_a_loop_seam():
    p = dot()
    p.apply({"type": "keyframes", "target": "dot", "property": "translate-y", "keys": [{"time": 0, "value": 0}]})
    p.apply({"type": "keyframes", "target": "dot", "property": "translate-y", "mode": "add",
             "keys": [{"time": 0, "value": 0, "easing": "ease-in-out"}, {"time": 2000, "value": 60}]})
    assert "loop-seam" in codes(p, "dot")


def test_additive_sum_agrees_in_lottie_and_frame_exports(tmp_path):
    p = dot()
    p.apply({"type": "keyframes", "target": "dot", "property": "translate-y",
             "sample": {"fn": "sin", "period": 1000, "amplitude": 10, "step_ms": 50}})
    p.apply({"type": "keyframes", "target": "dot", "property": "translate-y", "mode": "add", "additive": "leap",
             "keys": [{"time": 0, "value": 0}, {"time": 500, "value": 0}, {"time": 1000, "value": -100}, {"time": 1500, "value": 0}]})
    out = tmp_path / "dot.json"
    export_timeline(p, out, fps=20)
    layer = next(item for item in json.loads(out.read_text())["layers"] if item["nm"] == "dot")
    position = layer["ks"]["p"]
    keys = position["y"]["k"] if position.get("s") else position["k"]
    seen = {key["t"]: key["s"][-1 if position.get("s") else 1] for key in keys}
    assert len(seen) >= 30
    for frame, y in seen.items():
        # Lottie positions are the layer's centre: the summed bob and leap, frame for frame.
        assert y == pytest.approx(project_at(p, frame * 50).layer("dot")["y"] + 20, abs=1e-3)
    assert min(seen.values()) == pytest.approx(100, abs=1e-3) and max(seen.values()) > 205
    export_timeline(p, tmp_path / "dot.gif", fps=2)
    from PIL import Image, ImageSequence

    tops = [frame.convert("L").point(lambda v: 0 if v > 250 else 255).getbbox()[1]
            for frame in ImageSequence.Iterator(Image.open(tmp_path / "dot.gif"))]
    assert tops[0] == pytest.approx(180, abs=1) and tops[1] == pytest.approx(80, abs=1)  # 0 ms, then the leap's top at 1000 ms
    # A frame exported as SVG carries the same summed position (the dot's centre at y=100).
    svg = project_at(p, 1000).export(format="SVG", svg_document=False).decode()
    assert "translate(200.0 100.0)" in svg
    from vixl.diagnostics import timeline_report

    listed = next(item for item in timeline_report(p)["tracks"] if item["property"] == "translate-y")
    assert listed["additive"] == [{"layer": "leap", "key_count": 4}]


def test_blend_window_matches_the_wave_outside_and_the_poses_inside():
    p = dot()

    def wave(t):
        return 20 * math.sin(math.tau * t / 400)

    p.apply({"type": "keyframes", "target": "dot", "property": "rotation",
             "sample": {"fn": "sin", "period": 400, "amplitude": 20, "step_ms": 20,
                        "blend": {"start": 500, "duration": 1000, "poses": [{"at": 0.15, "value": -38}, {"at": 0.5, "value": 30},
                                                                          {"at": 0.85, "value": -10}]}}})
    keys = track(p, "dot", "rotation")["keys"]
    for t in (0, 100, 260, 480, 500, 1500, 1520, 1700, 2000):
        assert value(p, "rotation", t) == pytest.approx(wave(t), abs=1e-4)
    assert value(p, "rotation", 650) == pytest.approx(-38)
    assert value(p, "rotation", 1000) == pytest.approx(30)
    assert value(p, "rotation", 1350) == pytest.approx(-10)
    # The window is a handful of eased keys, not the wave's samples, and has no jump at either edge.
    assert [k["time"] for k in keys if 500 <= k["time"] <= 1500] == [500, 650, 1000, 1350, 1500]
    for edge in (500, 1500):
        assert abs(value(p, "rotation", edge + 1) - value(p, "rotation", edge - 1)) < 2
    with pytest.raises(VixlError, match="inside"):
        p.apply({"type": "keyframes", "target": "dot", "property": "rotation",
                 "sample": {"fn": "sin", "blend": {"start": 1800, "duration": 500, "poses": [{"at": 0.5, "value": 1}]}}})


def test_piecewise_sample_joins_segments_continuously():
    p = dot()
    p.apply({"type": "keyframes", "target": "dot", "property": "translate-x",
             "sample": [{"fn": "sin", "period": 400, "amplitude": 10, "duration": 700, "step_ms": 20},
                        {"fn": "triangle", "period": 300, "amplitude": 30, "offset": 100, "duration": 600, "step_ms": 20},
                        {"fn": "sin", "period": 700, "amplitude": 5, "step_ms": 20}]})
    keys = track(p, "dot", "translate-x")["keys"]
    times = [k["time"] for k in keys]
    assert times == sorted(set(times)) and times[0] == 0 and times[-1] == 2000
    joint = 10 * math.sin(math.tau * 700 / 400)
    assert value(p, "translate-x", 700) == pytest.approx(joint, abs=1e-4)
    # Each later segment starts on the value the one before reached: no step larger than the waves' own.
    steps = [abs(b["value"] - a["value"]) for a, b in zip(keys, keys[1:])]
    assert max(steps) < 9
    assert value(p, "translate-x", 1300) == pytest.approx(joint, abs=1e-4)  # two whole triangle periods later
    with pytest.raises(VixlError, match="duration"):
        p.apply({"type": "keyframes", "target": "dot", "property": "translate-x",
                 "sample": [{"fn": "sin"}, {"fn": "sin"}]})


def test_blend_on_an_existing_track_hands_over_to_poses_and_back():
    p = dot()
    p.apply({"type": "motion", "recipe": "wiggle", "target": "dot", "amount": 10, "frequency": 2})
    before = [dict(key) for key in track(p, "dot", "rotation")["keys"]]

    def was(time):
        return sample_track(p, {"property": "rotation", "keys": before}, time)

    p.apply({"type": "keyframes", "target": "dot", "property": "rotation",
             "blend": {"start": 500, "duration": 600, "poses": [{"at": 0.5, "value": 90}]}})
    keys = track(p, "dot", "rotation")["keys"]
    for time in (0, 200, 500, 1100, 1500, 2000):
        assert value(p, "rotation", time) == pytest.approx(was(time), abs=1e-6)
    assert value(p, "rotation", 800) == pytest.approx(90)
    assert [key["time"] for key in keys if 500 <= key["time"] <= 1100] == [500, 800, 1100]
    assert [key for key in keys if key["time"] < 500] == [key for key in before if key["time"] < 500]
    # A property without keys leaves from and returns to its current value.
    p.apply({"type": "keyframes", "target": "dot", "property": "translate-x",
             "blend": {"start": 0, "duration": 1000, "poses": [{"at": 0.4, "value": 50, "easing": "ease-in"}]}})
    assert [(key["time"], key["value"]) for key in track(p, "dot", "translate-x")["keys"]] == [(0, 0), (400, 50), (1000, 0)]
    with pytest.raises(VixlError):
        p.apply({"type": "keyframes", "target": "dot", "property": "rotation", "keys": [{"time": 0, "value": 1}],
                 "blend": {"start": 0, "duration": 100, "poses": [{"at": 0.5, "value": 1}]}})
