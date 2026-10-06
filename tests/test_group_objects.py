"""Groups, coordinate spaces and multi-part objects: ungroup with animation, grouped edit reports,
drawing coordinate spaces, attach, isolate and the connected check."""

import numpy as np
import pytest

from vixl.errors import VixlError
from vixl.group_bake import corners, placement
from vixl.project import Project
from vixl.timeline import project_at


def animated_group(**extra):
    p = Project(300, 200, "#ffffff")
    p.apply([
        {"type": "shape", "name": "a", "shape": "rectangle", "width": 40, "height": 20, "x": 50, "y": 60, "fill": "red"},
        {"type": "shape", "name": "b", "shape": "ellipse", "width": 30, "height": 30, "x": 120, "y": 80, "fill": "blue",
         "rotation": 30},
        {"type": "group", "name": "g", "targets": ["a", "b"]},
        {"type": "timeline-set", "duration": 1000, "fps": 12},
        {"type": "keyframes", "target": "g", "property": "rotation",
         "keys": [{"time": 0, "value": 0}, {"time": 1000, "value": 90, "easing": "ease-in-out"}]},
        {"type": "keyframes", "target": "g", "property": "translate-x", "keys": [{"time": 0, "value": 0}, {"time": 1000, "value": 60}]},
        {"type": "keyframes", "target": "g", "property": "scale", "keys": [{"time": 0, "value": 1}, {"time": 1000, "value": 1.5}]},
        {"type": "keyframes", "target": "b", "property": "x", "keys": [{"time": 0, "value": 70}, {"time": 1000, "value": 40}]},
    ])
    return p


def pose(project, time, name):
    return corners(*placement(project_at(project, time), project.layer(name)["id"])[1:3])


def test_ungroup_moves_group_animation_onto_children():
    p = animated_group()
    times = (0, 250, 500, 1000)
    before = {(t, n): pose(p, t, n) for t in times for n in "ab"}
    result = p.apply({"type": "ungroup", "target": "g"})
    assert "g" not in {layer["name"] for layer in p.state["layers"]}
    assert all(track["target"] in {p.layer("a")["id"], p.layer("b")["id"]} for track in p.state["timeline"]["tracks"])
    assert any("ungroup moved the animation" in w for w in result["warnings"])
    for (t, n), corner in before.items():
        assert np.abs(pose(p, t, n) - corner).max() < 0.5


def test_ungroup_shifts_child_position_keys_into_the_parent_space():
    p = Project(300, 200)
    p.apply([{"type": "shape", "name": "a", "shape": "rectangle", "width": 20, "height": 20, "x": 100, "y": 50},
             {"type": "shape", "name": "b", "shape": "rectangle", "width": 20, "height": 20, "x": 150, "y": 90},
             {"type": "group", "name": "g", "targets": ["a", "b"]},
             {"type": "keyframes", "target": "a", "property": "x", "keys": [{"time": 0, "value": 0}, {"time": 1000, "value": 30}]}])
    before = pose(p, 500, "a")
    p.apply({"type": "ungroup", "target": "g"})
    assert np.abs(pose(p, 500, "a") - before).max() < 1e-6


def test_ungroup_refuses_animation_it_cannot_rewrite():
    p = animated_group()
    p.apply({"type": "keyframes", "target": "g", "property": "opacity", "keys": [{"time": 0, "value": 1}, {"time": 1000, "value": 0}]})
    with pytest.raises(VixlError) as error:
        p.apply({"type": "ungroup", "target": "g"})
    assert "opacity" in str(error.value) and "keyframe-remove" in str(error.value)
    p = animated_group()
    p.apply({"type": "keyframes", "target": "g", "property": "scale-x", "keys": [{"time": 0, "value": 1}, {"time": 1000, "value": 2}]})
    with pytest.raises(VixlError) as error:
        p.apply({"type": "ungroup", "target": "g"})
    assert "scale-x" in str(error.value) and "'b'" in str(error.value)
    assert p.layer("g")["type"] == "group"


def test_group_result_lists_member_offsets_and_brief_edits_name_the_group():
    p = Project(300, 200)
    p.apply([{"type": "shape", "name": "a", "shape": "rectangle", "width": 20, "height": 20, "x": 100, "y": 50},
             {"type": "shape", "name": "b", "shape": "rectangle", "width": 20, "height": 20, "x": 150, "y": 90}])
    result = p.apply({"type": "group", "name": "g", "targets": ["a", "b"]})
    assert result["groups"] == [{"id": p.layer("g")["id"], "name": "g", "bounds": [100, 50, 70, 60],
                                 "members": {"a": [0, 0], "b": [50, 40]}}]
    p.apply({"type": "move", "target": "g", "x": 10, "y": 10})
    change = p.apply({"type": "opacity", "target": "b", "value": 0.5}, detail="brief")["changes"]["layers"][p.layer("b")["id"]]
    assert change["parent"] == p.layer("g")["id"] and change["parent_name"] == "g"
    assert change["coordinate_space"] == "parent"
    assert change["canvas_bounds"] == [60, 50, 20, 20]
    top = p.apply({"type": "opacity", "target": "g", "value": 0.5}, detail="brief")["changes"]["layers"][p.layer("g")["id"]]
    assert "parent" not in top and "canvas_bounds" not in top
