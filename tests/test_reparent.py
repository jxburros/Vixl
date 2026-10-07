"""reparent: move existing layers into or out of a group without ungrouping (#382)."""

import numpy as np
import pytest

from vixl.commands import compile_command
from vixl.errors import VixlError
from vixl.group_bake import corners, placement
from vixl.project import Project
from vixl.targets import mode
from vixl.timeline import project_at


def dog(*transforms):
    p = Project(400, 300, "white")
    p.apply([
        {"type": "shape", "name": "body", "shape": "rectangle", "x": 120, "y": 100, "width": 120, "height": 70,
         "fill": "#884422"},
        {"type": "shape", "name": "head", "shape": "ellipse", "x": 230, "y": 70, "width": 60, "height": 50,
         "fill": "#aa6633"},
        {"type": "group", "name": "dog", "targets": ["body", "head"]},
        *transforms,
        {"type": "shape", "name": "tail", "shape": "rectangle", "x": 60, "y": 120, "width": 70, "height": 14,
         "fill": "#331100", "rotation": 15},
    ])
    return p


def where(p, name, time=None):
    frame = p if time is None else project_at(p, time)
    _, full, rest, _ = placement(frame, p.layer(name)["id"])
    return corners(full, rest)


def pixels(p):
    return np.asarray(p.render().convert("RGBA"), dtype=np.int16)


def test_drawing_a_tail_then_moving_it_into_the_dog_leaves_the_render_unchanged():
    p = dog()
    before = pixels(p)
    result = p.apply({"type": "reparent", "targets": ["tail"], "into": "dog"}, detail="compact")
    assert result["reparent"][0]["into"] == "dog" and result["reparent"][0]["layers"] == ["tail"]
    assert p.layer("tail")["parent"] == p.layer("dog")["id"]
    assert np.array_equal(pixels(p), before)
    # The group's content box grew to include the tail, and the dog now moves its tail.
    group = p.layer("dog")
    assert group["content_width"] > 170 and group["x"] <= 60
    tail = where(p, "tail")
    p.apply({"type": "move", "target": "dog", "x": group["x"] + 25})
    assert np.allclose(where(p, "tail"), tail + [25, 0])
    # Back out to the page.
    p.undo()
    p.apply({"type": "reparent", "target": "tail", "into": "page"})
    assert p.layer("tail").get("parent") is None and np.array_equal(pixels(p), before)


@pytest.mark.parametrize("transforms", [
    [{"type": "rotate", "target": "dog", "value": 90}, {"type": "flip", "target": "dog", "direction": "horizontal"}],
    [{"type": "flip", "target": "dog", "direction": "vertical"}],
])
def test_right_angle_turns_and_mirrors_stay_pixel_identical(transforms):
    p = dog(*transforms)
    before = pixels(p)
    p.apply({"type": "reparent", "targets": ["tail"], "into": "dog"})
    assert np.array_equal(pixels(p), before)
    p.apply({"type": "reparent", "targets": ["tail"], "into": None})
    assert np.array_equal(pixels(p), before)
    assert "affine" not in p.layer("tail") and p.layer("tail")["rotation"] == 15


def test_rotated_scaled_and_flipped_groups_keep_the_geometry():
    p = dog({"type": "rotate", "target": "dog", "value": 20}, {"type": "flip", "target": "dog", "direction": "horizontal"},
            {"type": "resize", "target": "dog", "width": 200, "height": 120})
    shapes = {name: where(p, name) for name in ("body", "head", "tail")}
    before = pixels(p)
    p.apply({"type": "reparent", "targets": ["tail"], "into": "dog"})
    assert "affine" in p.layer("tail")  # the group's uneven scale is held in the tail's own matrix
    for name, box in shapes.items():
        assert np.abs(where(p, name) - box).max() < 1e-6, name
    # Only resampling differs: the scaled group is drawn at its content size and then transformed.
    assert np.abs(pixels(p) - before).mean() < 1.5
    p.apply({"type": "reparent", "targets": ["tail"], "into": None})
    assert np.abs(where(p, "tail") - shapes["tail"]).max() < 1e-6
    assert "affine" not in p.layer("tail") and p.layer("tail")["rotation"] == 15


def test_groups_move_with_their_children_and_cycles_are_refused():
    p = dog()
    p.apply([{"type": "shape", "name": "ball", "shape": "ellipse", "x": 300, "y": 200, "width": 30, "height": 30},
             {"type": "group", "name": "toys", "targets": ["ball"]}])
    ball = where(p, "ball")
    p.apply({"type": "reparent", "targets": ["toys"], "into": "dog"})
    assert p.layer("toys")["parent"] == p.layer("dog")["id"] and np.allclose(where(p, "ball"), ball)
    with pytest.raises(VixlError) as caught:
        p.apply({"type": "reparent", "targets": ["dog"], "into": "toys"})
    assert "inside itself" in str(caught.value) and caught.value.details["field"] == "into"
    with pytest.raises(VixlError):
        p.apply({"type": "reparent", "targets": ["dog"], "into": "dog"})
    with pytest.raises(VixlError) as caught:
        p.apply({"type": "reparent", "targets": ["tail"], "into": "ball"})
    assert "must name a group" in str(caught.value)


def test_stacking_position_and_keep_local():
    p = dog()
    p.apply({"type": "reparent", "targets": ["tail"], "into": "dog", "below": "body"})
    children = [item["name"] for item in p.state["layers"] if item.get("parent") == p.layer("dog")["id"]]
    assert children == ["tail", "body", "head"]
    p.apply({"type": "reparent", "targets": ["tail"], "into": "dog", "index": 1})
    children = [item["name"] for item in p.state["layers"] if item.get("parent") == p.layer("dog")["id"]]
    assert children == ["body", "tail", "head"]
    q = dog({"type": "move", "target": "dog", "x": 100})
    q.apply({"type": "reparent", "targets": ["tail"], "into": "dog", "keep": "local", "fit": False})
    assert (q.layer("tail")["x"], q.layer("tail")["y"]) == (60, 120)
    assert q.layer("dog")["content_width"] == 170


def test_animated_targets_keep_their_tracks_or_are_refused_by_name():
    p = dog({"type": "move", "target": "dog", "x": 150})
    p.apply([{"type": "timeline-set", "duration": 1000, "fps": 12},
             {"type": "keyframes", "target": "tail", "property": "x",
              "keys": [{"time": 0, "value": 20}, {"time": 1000, "value": 80}]},
             {"type": "keyframes", "target": "tail", "property": "rotation",
              "keys": [{"time": 0, "value": 0}, {"time": 1000, "value": 45}]}])
    poses = {t: where(p, "tail", t) for t in (0, 500, 1000)}
    p.apply({"type": "reparent", "targets": ["tail"], "into": "dog"})
    for t, box in poses.items():
        assert np.abs(where(p, "tail", t) - box).max() < 0.5, t
    q = dog({"type": "rotate", "target": "dog", "value": 30})
    q.apply([{"type": "timeline-set", "duration": 1000, "fps": 12},
             {"type": "keyframes", "target": "tail", "property": "x",
              "keys": [{"time": 0, "value": 20}, {"time": 1000, "value": 80}]}])
    with pytest.raises(VixlError) as caught:
        q.apply({"type": "reparent", "targets": ["tail"], "into": "dog"})
    assert caught.value.details["tracks"] == ["x"] and "keyframe-remove" in str(caught.value)
    assert q.layer("tail").get("parent") is None
    # A rotation track survives a turned parent.
    r = dog({"type": "rotate", "target": "dog", "value": 30})
    r.apply([{"type": "timeline-set", "duration": 1000, "fps": 12},
             {"type": "keyframes", "target": "tail", "property": "rotation",
              "keys": [{"time": 0, "value": 0}, {"time": 1000, "value": 90}]}])
    poses = {t: where(r, "tail", t) for t in (0, 500, 1000)}
    r.apply({"type": "reparent", "targets": ["tail"], "into": "dog"})
    for t, box in poses.items():
        assert np.abs(where(r, "tail", t) - box).max() < 0.5, t


def test_undo_redo_aliases_cli_and_targets_mode():
    p = dog()
    p.apply({"type": "move-into", "targets": ["tail"], "into": "dog"})
    assert p.layer("tail")["parent"] == p.layer("dog")["id"]
    p.undo()
    assert p.layer("tail").get("parent") is None and p.layer("dog")["content_width"] == 170
    p.redo()
    assert p.layer("tail")["parent"] == p.layer("dog")["id"]
    assert mode("reparent") == "joint"
    assert compile_command("reparent tail paw --into dog --below body --no-fit") == {
        "type": "reparent", "targets": ["tail", "paw"], "into": "dog", "below": "body", "fit": False}
    assert compile_command("reparent tail --into page")["into"] is None
