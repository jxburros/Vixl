"""Guides and grids beyond right angles: kinds, generated systems, placement, snapping and checks."""

import math

import numpy as np
import pytest

from vixl import Project
from vixl.errors import VixlError
from vixl.guides import GRID_KINDS, intersections, nearest, point_at


def test_cli_guide_with_an_axis_or_guide_options_adds_a_guide_instead_of_craft_guidance(tmp_path, monkeypatch):
    """`vixl guide margin x 64` (docs/guides.md) was answered by the craft guide (`vixl guide BRIEF`)."""
    from vixl.cli import dispatch

    monkeypatch.chdir(tmp_path)
    dispatch(["new", "400x300", "-o", "g.vixl"])
    dispatch(["-p", "g.vixl", "guide", "left-margin", "x", "64"])
    dispatch(["-p", "g.vixl", "guide", "horizon", "--kind", "segment", "--points", "[[0, 40], [400, 38]]"])
    guides = Project.load(tmp_path / "g.vixl").state["guides"]
    assert guides["left-margin"] == {"axis": "x", "position": 64.0}
    assert guides["horizon"]["kind"] == "segment"
    dispatch(["-p", "g.vixl", "guide", "horizon", "--delete"])
    assert set(Project.load(tmp_path / "g.vixl").state["guides"]) == {"left-margin"}
    advice, _ = dispatch(["guide", "a", "poster", "for", "a", "jazz", "night"])
    assert "success" not in advice  # still the craft guide, not an operation


def center(project, name):
    x, y, w, h = project.inspect(name)["resolved_bounds"]
    return x + w / 2, y + h / 2


@pytest.mark.parametrize("kind", GRID_KINDS)
def test_every_grid_kind_generates_tagged_guides(kind):
    p = Project(400, 300)
    p.apply([{"type": "grid", "name": "g", "kind": kind}])
    guides = p.state["guides"]
    assert guides and all(g["grid"] == "g" for g in guides.values())
    assert p.state["grids"]["g"]["kind"] == kind
    loaded = Project(400, 300)
    loaded.state = p.state
    from vixl.validation import check_state

    check_state(p, p.state)


def test_redefining_and_deleting_grids_and_guides():
    p = Project(400, 300)
    p.apply([{"type": "grid", "name": "g", "kind": "polar", "rings": 3, "spokes": 6},
             {"type": "grid", "name": "g", "kind": "thirds"}])
    assert len(p.state["guides"]) == 8 and p.state["grids"]["g"]["kind"] == "thirds"
    p.apply([{"type": "guide", "name": "focus", "kind": "point", "x": 10, "y": 20},
             {"type": "grid", "name": "g", "delete": True}])
    assert set(p.state["guides"]) == {"focus"} and "g" not in p.state["grids"]
    p.apply([{"type": "guide", "name": "focus", "delete": True}])
    assert not p.state.get("guides")
    # The original columns grid keeps its guide names and positions.
    p.apply([{"type": "grid", "name": "cols", "columns": 3, "margin": 20, "gutter": 10}])
    assert p.state["guides"]["cols-x1-start"]["position"] == 20


def test_guide_kinds_validate_their_fields():
    p = Project(200, 200)
    p.apply([{"type": "guide", "name": "slope", "kind": "line", "points": [[0, 200], [200, 0]]},
             {"type": "guide", "name": "ring", "kind": "circle", "x": 100, "y": 100, "radius": 50},
             {"type": "guide", "name": "s", "kind": "path", "d": "M0 100 C60 0 140 200 200 100"},
             {"type": "guide", "name": "edge", "kind": "segment", "points": [[10, 10], [190, 10]]},
             {"type": "guide", "name": "left", "axis": "x", "position": 20}])
    assert p.state["guides"]["slope"]["angle"] == pytest.approx(-45)
    with pytest.raises(VixlError) as error:
        p.apply([{"type": "guide", "name": "bad", "kind": "circle", "x": 1, "y": 1}])
    assert error.value.details["field"] == "radius"
    with pytest.raises(VixlError):
        p.apply([{"type": "guide", "name": "bad", "kind": "path", "d": "nonsense"}])


def test_geometry_nearest_points_and_intersections():
    canvas = {"width": 200, "height": 200}
    circle = {"kind": "circle", "x": 100, "y": 100, "radius": 50}
    line = {"kind": "line", "x": 0, "y": 100, "angle": 0}
    point, distance, tangent = nearest(circle, canvas, (100, 20))
    assert np.allclose(point, (100, 50)) and distance == pytest.approx(30)
    crossings = intersections(circle, line, canvas)
    assert [tuple(np.round(q, 3)) for q in crossings] == [(50, 100), (150, 100)]
    top, angle = point_at(circle, canvas, 0)
    assert np.allclose(top, (100, 50)) and angle % 360 == pytest.approx(0)
    diagonal = {"kind": "segment", "points": [[0, 0], [200, 200]]}
    assert np.allclose(point_at(diagonal, canvas, 0.25)[0], (50, 50))


def test_place_distributes_on_a_circle_and_turns_with_it():
    p = Project(400, 400)
    p.apply([{"type": "guide", "name": "ring", "kind": "circle", "x": 200, "y": 200, "radius": 120}]
            + [{"type": "shape", "shape": "rectangle", "name": f"t{i}", "width": 30, "height": 8} for i in range(8)]
            + [{"type": "place", "targets": [f"t{i}" for i in range(8)], "guide": "ring", "orient": "normal"}])
    for i in range(8):
        cx, cy = center(p, f"t{i}")
        assert math.hypot(cx - 200, cy - 200) == pytest.approx(120, abs=1)
        expected = math.degrees(math.atan2(cy - 200, cx - 200)) % 180
        assert min(abs(p.layer(f"t{i}")["rotation"] % 180 - expected), 180 - abs(p.layer(f"t{i}")["rotation"] % 180 - expected)) < 1
    assert center(p, "t0") == pytest.approx((200, 80), abs=1)   # the first copy sits at the top


def test_place_at_fractions_spacing_intersections_and_anchors():
    p = Project(300, 300)
    p.apply([{"type": "grid", "name": "rule", "kind": "thirds"},
             {"type": "guide", "name": "floor", "kind": "segment", "points": [[0, 250], [300, 250]]},
             {"type": "shape", "shape": "ellipse", "name": "sun", "width": 40, "height": 40},
             {"type": "shape", "shape": "rectangle", "name": "post", "width": 10, "height": 60},
             {"type": "place", "target": "sun", "guide": "rule-x1", "with": "rule-y1"},
             {"type": "place", "target": "post", "guide": "floor", "at": 0.5, "anchor": "bottom"}])
    assert center(p, "sun") == pytest.approx((100, 100), abs=1)
    x, y, w, h = p.inspect("post")["resolved_bounds"]
    assert (x + w / 2, y + h) == pytest.approx((150, 250), abs=1)
    q = Project(300, 100)
    q.apply([{"type": "guide", "name": "row", "kind": "segment", "points": [[0, 50], [300, 50]]}]
            + [{"type": "shape", "shape": "rectangle", "name": f"b{i}", "width": 10, "height": 10} for i in range(3)]
            + [{"type": "place", "targets": ["b0", "b1", "b2"], "guide": "row", "spacing": 40, "at": 0.1}])
    assert [center(q, f"b{i}")[0] for i in range(3)] == pytest.approx([30, 70, 110], abs=1)
    with pytest.raises(VixlError) as error:
        q.apply([{"type": "place", "target": "b0", "guide": "nope"}])
    assert error.value.details["field"] == "guide"


def test_place_works_inside_a_scaled_group():
    p = Project(400, 400)
    p.apply([{"type": "shape", "shape": "rectangle", "name": "a", "width": 20, "height": 20, "x": 0, "y": 0},
             {"type": "shape", "shape": "rectangle", "name": "b", "width": 20, "height": 20, "x": 180, "y": 180},
             {"type": "group", "name": "g", "targets": ["a", "b"]},
             {"type": "scale", "target": "g", "value": 2},
             {"type": "guide", "name": "spot", "kind": "point", "x": 150, "y": 220},
             {"type": "place", "target": "a", "guide": "spot"}])
    image = p.render()
    alpha = np.asarray(image.getchannel("A"))
    ys, xs = np.nonzero(alpha[180:260, 110:190])
    assert (xs.mean() + 110, ys.mean() + 180) == pytest.approx((150, 220), abs=2)


def test_constraints_follow_point_and_straight_guides():
    p = Project(300, 300)
    p.apply([{"type": "guide", "name": "focus", "kind": "point", "x": 120, "y": 80},
             {"type": "guide", "name": "flat", "kind": "line", "x": 0, "y": 200, "angle": 0},
             {"type": "guide", "name": "tilt", "kind": "line", "x": 0, "y": 200, "angle": 20},
             {"type": "shape", "shape": "rectangle", "name": "r", "width": 20, "height": 10},
             {"type": "constrain", "target": "r", "constraints": {"center-x": "guide:focus.center-x", "top": "guide:flat.top"}}])
    x, y, w, h = p.inspect("r")["resolved_bounds"]
    assert (x + w / 2, y) == (120, 200)
    with pytest.raises(VixlError) as error:
        p.apply([{"type": "constrain", "target": "r", "constraints": {"center-x": "guide:tilt.center-x", "top": "guide:flat.top"}}])
    assert "place" in str(error.value)


def test_snap_and_near_miss_checks():
    p = Project(400, 300, "white")
    p.apply([{"type": "grid", "name": "g", "kind": "thirds"},
             {"type": "shape", "shape": "rectangle", "name": "box", "width": 60, "height": 40, "x": 136, "y": 60},
             {"type": "guide", "name": "slope", "kind": "line", "x": 0, "y": 280, "angle": -30},
             {"type": "shape", "shape": "rectangle", "name": "bar", "width": 100, "height": 10, "x": 20, "y": 230},
             {"type": "rotate", "target": "bar", "value": -28.5},
             {"type": "shape", "shape": "rectangle", "name": "a", "width": 50, "height": 50, "x": 250, "y": 200},
             {"type": "shape", "shape": "rectangle", "name": "b", "width": 50, "height": 50, "x": 252, "y": 120}])
    report = p.check(checks=["guides", "alignment"])
    messages = " | ".join(issue["message"] for issue in report["issues"])
    assert "'box'" in messages and "off guide 'g-x1'" in messages
    assert "1.5° off guide 'slope'" in messages
    assert any(issue["check"] == "alignment" and set(issue["layers"]) == {"a", "b"} for issue in report["issues"])
    assert report["passed"]  # near misses are warnings
    p.apply([{"type": "snap", "targets": ["box", "bar"]}])
    assert p.layer("bar")["rotation"] == pytest.approx(330)
    remaining = p.check(checks=["guides"])["issues"]
    assert not [issue for issue in remaining if issue["layers"] == ["box"]]


def test_previews_show_guides_and_viewports_move_them():
    from vixl.proxy import render_preview, scaled_project
    from vixl.design_render import artboard_project

    p = Project(400, 400, "white")
    p.apply([{"type": "grid", "name": "dial", "kind": "polar", "rings": 2, "spokes": 4},
             {"type": "guide", "name": "edge", "kind": "segment", "points": [[100, 100], [300, 120]]}])
    plain = render_preview(p, 200, 200)
    shown = render_preview(p, 200, 200, guides=True)
    assert plain.tobytes() != shown.tobytes()
    small = scaled_project(p, 0.5)
    assert small.state["guides"]["dial-r1"]["radius"] == pytest.approx(50)
    assert small.state["guides"]["edge"]["points"][1] == pytest.approx([150, 60])
    p.apply([{"type": "artboard", "name": "crop", "x": 100, "y": 50, "width": 200, "height": 200}])
    board = artboard_project(p, "crop")
    assert board.state["guides"]["dial-center"]["x"] == pytest.approx(100)


def test_cli_compiles_guides_grids_place_and_snap():
    from vixl.commands import compile_command

    assert compile_command(["grid", "g", "--kind", "polar", "--rings", "3", "--spokes", "12"]) == {
        "type": "grid", "name": "g", "kind": "polar", "rings": 3, "spokes": 12}
    assert compile_command(["guide", "s", "--kind", "line", "--x", "0", "--y", "10", "--angle", "30"]) == {
        "type": "guide", "name": "s", "kind": "line", "x": 0.0, "y": 10.0, "angle": 30.0}
    assert compile_command(["guide", "m", "x", "64"]) == {"type": "guide", "name": "m", "axis": "x", "position": 64.0}
    assert compile_command(["place", "a", "b", "--guide", "ring", "--orient", "tangent"]) == {
        "type": "place", "targets": ["a", "b"], "guide": "ring", "orient": "tangent"}
    assert compile_command(["snap", "a", "--tolerance", "4"]) == {"type": "snap", "target": "a", "tolerance": 4.0}
