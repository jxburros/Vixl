"""Groups, coordinate spaces and multi-part objects: ungroup with animation, grouped edit reports,
drawing coordinate spaces, attach, isolate and the connected check."""

import numpy as np
import pytest

from vixl.errors import VixlError
from vixl.group_bake import apply_point, corners, placement
from vixl.project import Project
from vixl.timeline import inspect_timeline, project_at


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


def rig():
    """A body group that slides, holding an arm that swings about its shoulder, and a prop."""
    p = Project(400, 300, "#ffffff")
    p.apply([
        {"type": "shape", "name": "torso", "shape": "rectangle", "width": 40, "height": 80, "x": 100, "y": 100},
        {"type": "shape", "name": "arm", "shape": "rectangle", "width": 70, "height": 12, "x": 140, "y": 110},
        {"type": "pivot", "target": "arm", "value": [0, 0.5]},
        {"type": "group", "name": "body", "targets": ["torso", "arm"]},
        {"type": "shape", "name": "prop", "shape": "ellipse", "width": 16, "height": 16, "x": 300, "y": 40},
        {"type": "timeline-set", "duration": 1000, "fps": 24},
        {"type": "keyframes", "target": "arm", "property": "rotation",
         "keys": [{"time": 0, "value": -40}, {"time": 1000, "value": 80, "easing": "ease-in-out"}]},
        {"type": "keyframes", "target": "body", "property": "translate-x", "keys": [{"time": 0, "value": 0}, {"time": 1000, "value": 90}]},
    ])
    return p


def hand(project, time):
    frame = project_at(project, time)
    _, full, rest, _ = placement(frame, project.layer("arm")["id"])
    return np.array(apply_point(full, (rest[0], rest[1] / 2)))


def centre(project, time):
    _, full, rest, _ = placement(project_at(project, time), project.layer("prop")["id"])
    return np.array(apply_point(full, (rest[0] / 2, rest[1] / 2)))


def test_attach_keeps_a_prop_on_a_rotating_arm_hand():
    p = rig()
    p.apply({"type": "motion", "recipe": "attach", "target": "prop", "follow": "arm", "anchor": [1, 0.5]})
    for time in (0, 1000 / 24 * 5, 333, 500, 1000 * 17 / 24, 1000):
        assert np.linalg.norm(centre(p, time) - hand(p, time)) < 1
    inspect = inspect_timeline(p)
    assert inspect["attachments"] == [{"layer": "prop", "to": "arm", "anchor": [70.0, 6.0], "rotation": True,
                                       "start": 0, "end": 1000, "baked": "per-frame translate and rotation keys"}]
    assert {t["property"] for t in inspect["tracks"] if t.get("attached_to") == "arm"} == {"translate-x", "translate-y", "rotation"}
    from vixl.diagnostics import timeline_report

    report = timeline_report(p, targets=["prop"])
    assert report["attachments"][0]["to"] == "arm"
    assert {t["attached_to"] for t in report["tracks"]} == {"arm"}


def test_attach_without_anchor_keeps_the_current_offset_and_can_stay_upright():
    p = rig()
    p.apply({"type": "move", "target": "prop", "x": 202, "y": 108})
    start = centre(p, 0) - hand(p, 0)
    p.apply({"type": "motion", "recipe": "attach", "target": "prop", "to": "arm", "rotation": False})
    assert all(not track["property"] == "rotation" for track in p.state["timeline"]["tracks"] if track["target"] == p.layer("prop")["id"])
    # The prop rides the same point of the arm (the arm's frame turns, so the offset does too).
    assert np.linalg.norm(centre(p, 0) - hand(p, 0) - start) < 1
    distance = np.linalg.norm(start)
    assert abs(np.linalg.norm(centre(p, 600) - hand(p, 600)) - distance) < 1
    p.apply({"type": "remove", "target": "arm"})
    assert "attachments" not in inspect_timeline(p)


def scene():
    p = Project(400, 300, "#ffffff")
    p.apply([
        {"type": "shape", "name": "ground", "shape": "rectangle", "width": 400, "height": 100, "x": 0, "y": 200, "fill": "#00aa00"},
        {"type": "shape", "name": "head", "shape": "ellipse", "width": 40, "height": 40, "x": 100, "y": 60, "fill": "#ff0000"},
        {"type": "shape", "name": "body", "shape": "rectangle", "width": 30, "height": 60, "x": 105, "y": 95, "fill": "#0000ff"},
        {"type": "group", "name": "figure", "targets": ["head", "body"]},
        {"type": "shape", "name": "tree", "shape": "ellipse", "width": 60, "height": 60, "x": 300, "y": 100, "fill": "#005500"},
    ])
    return p


def test_isolate_previews_one_object_cropped_to_its_ink():
    from vixl.proxy import render_preview

    p = scene()
    image = render_preview(p, 512, 512, isolate=["figure"]).convert("RGB")
    # The figure's ink is 40 x 95 px; a small margin, then enlarged for detail.
    assert 0.4 < image.width / image.height < 0.5
    colours = {colour for _, colour in image.getcolors(1 << 20)}
    assert (255, 0, 0) in colours and (0, 0, 255) in colours
    assert (0, 170, 0) not in colours and (0, 85, 0) not in colours  # ground and tree are hidden
    full = render_preview(p, 400, 300, isolate=["figure"], region=[0, 0, 400, 300]).convert("RGB")
    assert full.size == (400, 300) and full.getpixel((330, 130)) == (255, 255, 255)
    with pytest.raises(VixlError):
        render_preview(p, 512, 512, isolate=["nothing"])


def test_compare_can_isolate_an_object():
    from vixl.checks import compare

    p = scene()
    p.apply({"type": "move", "target": "head", "x": 4, "y": 0})
    image, summary = compare(p, "previous", "head", isolate=["figure"])
    x, y, w, h = summary["region"]
    assert x < 100 and y < 60 and x + w > 140 and y + h > 155 and w < 80
    cx, cy, cw, ch = summary["changed_region"]
    assert x <= cx and cx + cw <= x + w and 50 <= cy <= 65


def mascot():
    p = Project(300, 240, "#ffffff")
    p.apply([
        {"type": "shape", "name": "body", "shape": "ellipse", "width": 80, "height": 100, "x": 100, "y": 90, "fill": "#e07a5f"},
        {"type": "shape", "name": "head", "shape": "ellipse", "width": 60, "height": 60, "x": 110, "y": 40, "fill": "#e07a5f"},
        {"type": "shape", "name": "ear", "shape": "triangle", "width": 20, "height": 20, "x": 120, "y": 26, "fill": "#e07a5f"},
        {"type": "shape", "name": "tail", "shape": "rectangle", "width": 30, "height": 8, "x": 200, "y": 150, "fill": "#e07a5f"},
        {"type": "text", "name": "label", "text": "Hi", "x": 10, "y": 10, "size": 18},
        {"type": "group", "name": "cat", "targets": ["body", "head", "ear", "tail", "label"]},
    ])
    return p


def connected(project, **options):
    return [i for i in project.check(checks=["connected"], **options)["issues"] if i["check"] == "connected"]


def test_connected_check_finds_parts_floating_free_of_the_body():
    p = mascot()
    found = connected(p)
    assert [(i["layers"], i["group"]) for i in found] == [(["tail"], "cat")]
    assert 15 <= found[0]["gap"] <= 25 and "detached_ok" in found[0]["message"]
    assert connected(p, connect_tolerance=25) == []
    p.apply({"type": "layer-intent", "target": "tail", "detached_ok": True})
    assert connected(p) == []
    p.apply([{"type": "layer-intent", "target": "tail", "detached_ok": False},
             {"type": "move", "target": "tail", "x": 170, "y": 150, "space": "canvas"}])
    assert connected(p) == []
    assert "connected" not in p.check()["checked"]["checks"]


def test_connected_check_samples_animation_frames():
    p = mascot()
    p.apply([{"type": "move", "target": "tail", "x": 170, "y": 150, "space": "canvas"},
             {"type": "timeline-set", "duration": 1000, "fps": 10},
             {"type": "keyframes", "target": "tail", "property": "translate-x",
              "keys": [{"time": 0, "value": 0}, {"time": 500, "value": 40}, {"time": 1000, "value": 0}]}])
    found = connected(p)
    assert len(found) == 1 and found[0]["frame"] == "middle" and "middle frame" in found[0]["message"]


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


def test_multi_part_object_guidance_points_at_isolate_and_connected():
    from vixl.capabilities import TOPICS
    from vixl.guidance import GUIDANCE

    text = GUIDANCE["multi-part-objects"]
    assert "isolate" in text and "connected" in text and "detached_ok" in text and "silhouette" in text
    assert "multi-part-objects" in TOPICS["drawing"][1]


def test_layer_intent_cli_covers_every_field_and_compact_inspect_shows_them():
    from vixl.changes import summarize
    from vixl.commands import compile_command
    from vixl.schema import _properties

    op = compile_command("layer-intent tail --role title --allow-overlap body --tags paw fur --allow-crop "
                         "--color-vision-safe --detached-ok --alt 'A curled tail' --no-decorative")
    fields = set(_properties()["layer-intent"]) - {"type", "targets"}
    assert fields <= set(op), sorted(fields - set(op))
    assert op["role"] == "title"
    assert compile_command("layer-intent tail --no-detached-ok")["detached_ok"] is False
    p = Project(200, 100, "#ffffff")
    p.apply([{"type": "shape", "name": "body", "shape": "rectangle", "width": 40, "height": 20, "fill": "red"},
             {"type": "shape", "name": "tail", "shape": "rectangle", "width": 10, "height": 5, "x": 80, "fill": "red"},
             {**op, "role": "decoration"}])
    brief = summarize(p, "tail")
    assert brief["role"] == "decoration" and brief["tags"] == ["fur", "paw"]
    assert brief["detached_ok"] and brief["allow_crop"] and brief["color_vision_safe"]
    assert "detached_ok" not in summarize(p, "body")
