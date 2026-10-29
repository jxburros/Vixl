"""Transformed groups dissolve through the shared appearance-preserving move planner."""

from copy import deepcopy

import numpy as np
import pytest

from vixl.commands import compile_command
from vixl.errors import VixlError
from vixl.group_bake import corners, placement
from vixl.project import Project
from vixl.timeline import project_at


def scene():
    project = Project(360, 240, "white")
    project.apply([
        {"type": "shape", "name": "a", "shape": "rectangle", "width": 70, "height": 20,
         "x": 100, "y": 80, "fill": "red"},
        {"type": "shape", "name": "b", "shape": "ellipse", "width": 35, "height": 30,
         "x": 190, "y": 110, "fill": "blue", "rotation": 25},
        {"type": "group", "name": "g", "targets": ["a", "b"]},
    ])
    return project


def pose(project, name, time=None):
    frame = project if time is None else project_at(project, time)
    return corners(*placement(frame, project.layer(name)["id"])[1:3])


def test_rotated_title_keeps_geometry_and_render_with_only_resampling_difference():
    project = Project(360, 180, "white")
    project.apply([
        {"type": "text", "name": "title", "text": "Move together", "size": 28,
         "x": 30, "y": 40, "color": "black"},
        {"type": "shape", "name": "rule", "shape": "rectangle", "width": 180, "height": 3,
         "x": 30, "y": 80, "fill": "red"},
        {"type": "group", "name": "g", "targets": ["title", "rule"]},
        {"type": "rotate", "target": "g", "value": 352},
    ])
    before = np.asarray(project.render(), dtype=np.int16)
    boxes = {name: pose(project, name) for name in ("title", "rule")}
    ids = {name: project.layer(name)["id"] for name in boxes}
    project.apply({"type": "ungroup", "target": "g", "keep": "appearance"})
    for name, box in boxes.items():
        assert np.allclose(pose(project, name), box, atol=1e-7)
        assert project.layer(name)["id"] == ids[name]
    # A transformed group was sampled as one surface; its editable children now sample separately.
    difference = np.abs(np.asarray(project.render(), dtype=np.int16) - before)
    assert difference.mean() < 0.6
    assert (difference > 3).sum() < difference.size * 0.025


def test_flipped_scaled_nested_group_preserves_rotated_child_geometry_and_order():
    project = scene()
    project.apply([
        {"type": "shape", "name": "c", "shape": "rectangle", "width": 10, "height": 10},
        {"type": "group", "name": "outer", "targets": ["g", "c"]},
        {"type": "rotate", "target": "outer", "value": 18},
        {"type": "rotate", "target": "g", "value": 32},
        {"type": "flip", "target": "g", "direction": "horizontal"},
        {"type": "resize", "target": "g", "width": 150, "height": 90},
    ])
    boxes = {name: pose(project, name) for name in ("a", "b", "c")}
    project.apply({"type": "ungroup", "target": "g", "keep": "appearance"})
    for name, box in boxes.items():
        assert np.allclose(pose(project, name), box, atol=1e-7)
    assert project.layer("a")["parent"] == project.layer("outer")["id"]
    assert [item["name"] for item in project.state["layers"]] == ["a", "b", "c", "outer"]
    assert "affine" in project.layer("b")


@pytest.mark.parametrize("child_rotation", [False, True])
def test_animated_rotated_group_preserves_five_sampled_poses(child_rotation):
    project = scene()
    project.apply([
        {"type": "rotate", "target": "g", "value": 352},
        {"type": "timeline-set", "duration": 1000, "fps": 12},
        {"type": "keyframes", "target": "g", "property": "rotation",
         "keys": [{"time": 0, "value": 352}, {"time": 1000, "value": 400}]},
        {"type": "keyframes", "target": "g", "property": "translate-x",
         "keys": [{"time": 0, "value": 0}, {"time": 1000, "value": 30}]},
    ])
    if child_rotation:
        project.apply({"type": "keyframes", "target": "a", "property": "rotation",
                       "keys": [{"time": 0, "value": 20}, {"time": 1000, "value": 60}]})
    before = {(name, time): pose(project, name, time) for name in ("a", "b")
              for time in (0, 250, 500, 750, 1000)}
    project.apply({"type": "ungroup", "target": "g", "keep": "appearance"})
    for (name, time), box in before.items():
        assert np.abs(pose(project, name, time) - box).max() < 0.5


@pytest.mark.parametrize("operation, message", [
    ({"type": "layer-style", "target": "g", "name": "drop-shadow"}, "styles"),
    ({"type": "blend", "target": "g", "mode": "multiply"}, "blend"),
])
def test_appearance_refusals_are_atomic(operation, message):
    project = scene()
    project.apply(operation)
    before = deepcopy(project.state)
    with pytest.raises(VixlError, match=message):
        project.apply({"type": "ungroup", "target": "g", "keep": "appearance"})
    assert project.state == before


def test_mask_refuses_without_mutation():
    project = scene()
    project.apply({"type": "mask", "target": "g", "action": "gradient"})
    before = deepcopy(project.state)
    with pytest.raises(VixlError, match="mask"):
        project.apply({"type": "ungroup", "target": "g", "keep": "appearance"})
    assert project.state == before


def test_child_parent_space_tracks_on_rotated_group_refuse_by_name():
    project = scene()
    project.apply([
        {"type": "rotate", "target": "g", "value": 20},
        {"type": "keyframes", "target": "a", "property": "x",
         "keys": [{"time": 0, "value": 0}, {"time": 1000, "value": 20}]},
    ])
    before = deepcopy(project.state)
    with pytest.raises(VixlError, match="parent's coordinates") as caught:
        project.apply({"type": "ungroup", "target": "g", "keep": "appearance"})
    assert caught.value.details["tracks"] == ["x"]
    assert project.state == before


def test_nonoverlapping_fade_moves_to_children_and_overlapping_fade_refuses():
    project = scene()
    project.apply({"type": "opacity", "target": "g", "value": 0.5})
    before = np.asarray(project.render(), dtype=np.int16)
    project.apply({"type": "ungroup", "target": "g", "keep": "appearance"})
    assert all(project.layer(name)["opacity"] == 0.5 for name in ("a", "b"))
    assert np.abs(np.asarray(project.render(), dtype=np.int16) - before).max() <= 1
    project = scene()
    project.apply([{"type": "move", "target": "b", "x": 10, "y": 0},
                   {"type": "opacity", "target": "g", "value": 0.5}])
    before = deepcopy(project.state)
    with pytest.raises(VixlError, match="overlapping"):
        project.apply({"type": "ungroup", "target": "g", "keep": "appearance"})
    assert project.state == before


def test_strict_default_still_refuses_transforms_and_cli_accepts_appearance():
    project = scene()
    project.apply({"type": "rotate", "target": "g", "value": 352})
    with pytest.raises(VixlError, match="Reset group transforms"):
        project.apply({"type": "ungroup", "target": "g"})
    assert compile_command("ungroup g --keep appearance --force") == {
        "type": "ungroup", "target": "g", "keep": "appearance", "force": True}
