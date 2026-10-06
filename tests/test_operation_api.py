"""The 0.21 operation API contract: every schema error at once, one opacity scale, target/targets
everywhere, the path box, and canvas-space edits of grouped layers."""

import json
from pathlib import Path
import subprocess
import sys

import pytest
from fastapi.testclient import TestClient

from vixl import Project, VixlError
from vixl.commands import compile_command
from vixl.interfaces import create_app, mcp_server
from vixl.schema import operation_schema, validate_operation
from vixl.spatial import canvas_boxes
from vixl.targets import EACH, JOINT, markdown_table

from test_agent_interface import call, error_payload

THREE_BAD = [
    {"type": "shape", "shape": "ellipse", "name": "a", "width": 40, "height": 40, "bogus": 1},
    {"type": "move", "target": "a", "x": 5},
    {"type": "opacity", "value": 70},
    {"type": "nonsense"},
]


def stage():
    p = Project(400, 300)
    p.apply([{"type": "shape", "shape": "rectangle", "name": n, "x": 40 * i, "y": 10, "width": 30, "height": 30}
             for i, n in enumerate(("a", "b", "c"))])
    return p


# --- #241: every schema error in one response -------------------------------------------------


@pytest.mark.parametrize("dry_run", [False, True])
def test_a_batch_reports_every_invalid_operation_at_once(dry_run):
    p = stage()
    with pytest.raises(VixlError) as error:
        p.apply(THREE_BAD, dry_run=dry_run)
    details = error.value.as_dict()
    assert details["error_count"] == 3 and [e["operation_index"] for e in details["errors"]] == [0, 2, 3]
    # The top-level fields describe the first error; the message lists all of them.
    assert details["operation_index"] == 0 and details["field"] == "bogus"
    assert details["errors"][1]["field"] == "value" and details["errors"][2]["error"] == "unknown_operation"
    assert all(f"operations[{i}]" in details["message"] for i in (0, 2, 3))
    assert [layer["name"] for layer in p.state["layers"]] == ["a", "b", "c"]  # nothing applied


def test_execution_errors_stay_first_only_and_a_lone_error_keeps_its_shape():
    p = stage()
    with pytest.raises(VixlError) as error:
        p.apply([{"type": "move", "target": "zz", "x": 1}, {"type": "move", "target": "yy", "x": 1}])
    assert error.value.details["operation_index"] == 0 and "errors" not in error.value.details
    with pytest.raises(VixlError) as error:
        p.apply([{"type": "hide", "target": "a"}, {"type": "opacity", "target": "a", "value": 2}])
    assert error.value.details["operation_index"] == 1 and "errors" not in error.value.details


def test_unknown_fields_fail_instead_of_warning():
    p = stage()
    with pytest.raises(VixlError, match=r"Unknown field\(s\) 'spread' in effects\[0\]"):
        p.apply({"type": "adjustment", "name": "adj", "effects": [{"name": "brightness", "amount": 10, "spread": 2}]})
    # A valid field that does nothing for this shape is still only an advisory.
    result = p.apply({"type": "shape", "shape": "rectangle", "name": "r", "radius": 4, "width": 9, "height": 9})
    assert "radius only rounds" in " ".join(result["warnings"])


def test_mcp_rest_and_cli_surface_the_full_list(tmp_path):
    server = mcp_server(workspace=tmp_path)
    call(server, "vixl_document_create", {"path": "a.vixl", "width": 64, "height": 64})
    failed, text, _ = call(server, "vixl_operations_apply", {"operations": THREE_BAD, "dry_run": True})
    assert failed and [e["operation_index"] for e in error_payload(text)["errors"]] == [0, 2, 3]
    path = tmp_path / "b.vixl"
    Project(64, 64).save(path)
    with TestClient(create_app(path)) as client:
        response = client.post("/operations", json={"operations": THREE_BAD})
    assert response.status_code == 400 and len(response.json()["errors"]) == 3
    result = subprocess.run([sys.executable, "-m", "vixl", "-p", str(path), "apply", "-"],
                            input=json.dumps({"operations": THREE_BAD}).encode(), capture_output=True, timeout=30,
                            env={"PYTHONPATH": str(Path(__file__).parents[1] / "src"), "PATH": ""})
    assert result.returncode == 1
    assert all(f"operations[{i}]" in result.stderr.decode() for i in (0, 2, 3))


# --- #242: one opacity scale ------------------------------------------------------------------


@pytest.mark.parametrize("operation, read", [
    ({"type": "opacity", "target": "a", "value": "70%"}, lambda p: p.layer("a")["opacity"]),
    ({"type": "keyframe", "target": "a", "property": "opacity", "time": 0, "value": "70%"},
     lambda p: p.state["timeline"]["tracks"][0]["keys"][0]["value"]),
    ({"type": "animate", "target": "a", "property": "opacity", "from": "0%", "to": "70%", "duration": 100},
     lambda p: p.state["timeline"]["tracks"][0]["keys"][-1]["value"]),
    ({"type": "keyframes", "target": "a", "property": "opacity", "keys": [{"time": 0, "value": "70%"}]},
     lambda p: p.state["timeline"]["tracks"][0]["keys"][0]["value"]),
    ({"type": "layer-style", "target": "a", "name": "drop-shadow", "settings": {"opacity": "70%"}},
     lambda p: p.layer("a")["styles"]["drop-shadow"]["opacity"]),
    ({"type": "shape", "shape": "ellipse", "name": "e", "opacity": "70%"}, lambda p: p.layer("e")["opacity"]),
])
def test_percentage_strings_are_read_as_fractions_everywhere(operation, read):
    p = stage()
    result = p.apply(operation)
    assert read(p) == pytest.approx(0.7) and "'70%' → 0.7" in " ".join(result["normalized"])


@pytest.mark.parametrize("operation, field", [
    ({"type": "opacity", "target": "a", "value": 70}, "value"),
    ({"type": "keyframe", "target": "a", "property": "opacity", "time": 0, "value": 70}, "value"),
    ({"type": "animate", "target": "a", "property": "opacity", "to": 70}, "to"),
    ({"type": "layer-style", "target": "a", "name": "outer-glow", "settings": {"opacity": 70}}, "settings.opacity"),
    ({"type": "text", "text": "hi", "opacity": 70}, "opacity"),
])
def test_a_bare_number_above_one_is_an_error_that_suggests_both_spellings(operation, field):
    with pytest.raises(VixlError) as error:
        stage().apply(operation)
    assert error.value.details["field"] == field and error.value.details["suggestions"] == [0.7, "70%"]
    assert 'use 0.7 or the string "70%"' in str(error.value)
    # Opacity of other properties keeps its own range: a keyframe x of 70 is just a position.
    stage().apply({"type": "keyframe", "target": "a", "property": "x", "time": 0, "value": 70})


def test_layers_take_rotation_and_opacity_when_created():
    p = Project(400, 300)
    p.apply([
        {"type": "shape", "shape": "ellipse", "name": "e", "width": 50, "height": 50, "opacity": 0.5, "rotation": 20,
         "x": "center", "y": "center"},
        {"type": "text", "name": "t", "text": "Hi", "rotation": -5, "opacity": "40%"},
        {"type": "gradient", "name": "g", "width": 40, "height": 40, "rotation": 45, "opacity": 0.25},
        {"type": "solid", "name": "s", "width": 10, "height": 10, "opacity": 0.6},
    ])
    e = p.layer("e")
    assert (e["opacity"], e["rotation"]) == (0.5, 20)
    x, y, w, h = p.inspect("e")["resolved_bounds"]
    assert abs(x + w / 2 - 200) <= 1 and abs(y + h / 2 - 150) <= 1  # centred after rotating
    assert (p.layer("t")["rotation"], p.layer("t")["opacity"]) == (355, 0.4)
    assert (p.layer("g")["rotation"], p.layer("g")["opacity"], p.layer("s")["opacity"]) == (45, 0.25, 0.6)
    p.apply({"type": "shape", "target": "e", "opacity": 1, "rotation": 0})  # with target: the edited layer's
    assert (p.layer("e")["opacity"], p.layer("e")["rotation"]) == (1, 0)


# --- #188: target and targets -----------------------------------------------------------------


def test_per_layer_operations_take_targets_and_apply_to_each():
    p = stage()
    result = p.apply([{"type": "opacity", "targets": ["a", "b"], "value": 0.5},
                      {"type": "layer-intent", "targets": ["a", "c"], "allow_crop": True},
                      {"type": "move", "targets": ["b", "c"], "x": 10, "relative": True},
                      {"type": "blur", "targets": ["a", "b"], "amount": 2}])
    assert [layer["opacity"] for layer in p.state["layers"]] == [0.5, 0.5, 1]
    assert p.layer("b")["x"] == 50 and p.layer("c")["x"] == 90 and p.layer("a")["x"] == 0
    assert all(p.layer(n)["effects"] for n in ("a", "b")) and result["operations"] == 4
    p.undo()  # one batch, one history entry
    assert [layer["opacity"] for layer in p.state["layers"]] == [1, 1, 1]
    assert p.nodes[p.redo_stack[-1]]["operations"][0]["targets"] == ["a", "b"]


def test_targets_errors_name_the_original_operation():
    p = stage()
    with pytest.raises(VixlError) as error:
        p.apply([{"type": "hide", "target": "a"}, {"type": "rotate", "targets": ["b", "missing"], "value": 9}])
    assert error.value.details["operation_index"] == 1 and error.value.details["requested"] == "missing"
    assert p.layer("b")["rotation"] == 0 and p.layer("a")["visible"]  # atomic
    with pytest.raises(VixlError, match="takes target or targets, not both"):
        p.apply({"type": "hide", "target": "a", "targets": ["b"]})


def test_single_and_joint_operations_normalize_the_other_spelling():
    p = stage()
    result = p.apply({"type": "rename", "targets": ["a"], "name": "first"})
    assert p.layer("first") and "'targets' with one layer → 'target'" in result["normalized"][0]
    with pytest.raises(VixlError, match="rename takes one target; got targets with 2 layers"):
        p.apply({"type": "rename", "targets": ["first", "b"], "name": "x"})
    result = p.apply({"type": "group", "name": "g", "target": "b"})
    assert p.layer("b")["parent"] == p.layer("g")["id"] and "'target' → 'targets'" in result["normalized"][0]


def test_nested_operations_fan_out_too():
    p = stage()
    p.apply([{"type": "action-define", "name": "fade",
              "action": {"operations": [{"type": "opacity", "targets": ["a", "c"], "value": 0.3}]}},
             {"type": "action-apply", "name": "fade"}])
    assert [layer["opacity"] for layer in p.state["layers"]] == [0.3, 1, 0.3]


def test_every_operation_declares_its_targets_mode_and_the_docs_table_is_generated():
    variants = {v["properties"]["type"]["const"]: v for v in operation_schema()["properties"]["operations"]["items"]["oneOf"]}
    for kind, variant in variants.items():
        assert variant["x-targets"] in ("each", "joint", "one"), kind
        assert ("targets" in variant["properties"]) == (variant["x-targets"] != "one"), kind
    assert EACH <= set(variants) and JOINT <= set(variants)
    # A required target accepts targets instead.
    validate_operation({"type": "layer-intent", "targets": ["a"], "allow_crop": True})
    validate_operation({"type": "shape", "targets": ["a", "b"], "fill": "red"})
    docs = (Path(__file__).parents[1] / "docs/operations.md").read_text(encoding="utf-8")
    assert markdown_table() in docs, "regenerate the table in docs/operations.md with vixl.targets.markdown_table()"


# --- #251: the path box ---------------------------------------------------------------------


def test_a_path_without_a_size_gets_its_box_from_the_path_not_the_canvas():
    p = Project(800, 600)
    path = "M300 200 L340 260 Q350 210 320 190 M310 220 L330 230"
    p.apply({"type": "shape", "shape": "path", "name": "flick", "path": path, "stroke": "red", "stroke_width": 2})
    flick = p.layer("flick")
    assert flick["path"] == path and (flick["x"], flick["y"]) == (0, 0)  # literal local pixels, text kept
    assert flick["width"] == pytest.approx(342.5) and flick["height"] == 260 and flick["path_view"] == [342.5, 260]
    p.apply({"type": "shape", "shape": "path", "name": "w", "path": "M0 0 L10 40", "width": 50, "x": 5})
    assert (p.layer("w")["width"], p.layer("w")["height"], p.layer("w")["path_view"]) == (50, 40, [50, 40])
    # The rendered pixels sit where the coordinates say, offset by x/y.
    p2 = Project(100, 100)
    p2.apply({"type": "shape", "shape": "path", "name": "sq", "path": "M20 30 L40 30 L40 50 L20 50 Z", "x": 10,
              "fill": "black"})
    assert p2.render().getbbox() == (30, 30, 50, 50)


# --- #244: groups -------------------------------------------------------------------------------


def grouped():
    p = Project(400, 300)
    p.apply([{"type": "shape", "shape": "rectangle", "name": "a", "x": 100, "y": 100, "width": 50, "height": 50},
             {"type": "text", "name": "t", "text": "hi", "x": 200, "y": 120},
             {"type": "shape", "shape": "rectangle", "name": "mug", "x": 10, "y": 10, "width": 20, "height": 20},
             {"type": "group", "name": "g", "targets": ["a", "t"]},
             {"type": "scale", "target": "g", "value": 2}])
    return p


def test_shape_and_text_edits_of_grouped_layers_accept_canvas_space():
    p = grouped()
    p.apply([{"type": "shape", "target": "a", "x": 50, "y": 60, "space": "canvas"},
             {"type": "text", "target": "t", "x": 300, "y": 20, "space": "canvas"}])
    assert canvas_boxes(p)[p.layer("a")["id"]][:2] == pytest.approx((50, 60))
    assert canvas_boxes(p)[p.layer("t")["id"]][:2] == pytest.approx((300, 20), abs=1)
    p.apply({"type": "shape", "target": "a", "x": 10})  # parent space stays the default
    assert p.layer("a")["x"] == 10


def test_pivot_in_canvas_units_goes_through_the_parent_groups():
    p = grouped()
    x, y, w, h = canvas_boxes(p)[p.layer("a")["id"]]
    p.apply({"type": "pivot", "target": "a", "value": [x + w / 4, y + h], "units": "canvas"})
    assert p.layer("a")["pivot"] == pytest.approx([0.25, 1])
    assert canvas_boxes(p)[p.layer("a")["id"]] == pytest.approx((x, y, w, h))  # the drawn pose is kept
    assert compile_command("pivot a 10 20 --canvas")["units"] == "canvas"


def test_group_above_or_below_sets_the_new_groups_slot():
    p = grouped()
    p.apply({"type": "group", "name": "m", "targets": ["mug"], "above": "g"})
    top = [layer["name"] for layer in p.state["layers"] if not layer.get("parent")]
    assert top.index("m") == top.index("g") + 1
    p.apply({"type": "group", "name": "m2", "targets": ["m"], "below": "g"})
    top = [layer["name"] for layer in p.state["layers"] if not layer.get("parent")]
    assert top.index("m2") < top.index("g")
    with pytest.raises(VixlError, match="outside the group"):
        p.apply({"type": "group", "name": "bad", "targets": ["g"], "above": "g"})
    assert compile_command("group h a --below g")["below"] == "g"
    assert compile_command("shape ellipse --opacity 70% --rotation 20")["opacity"] == "70%"
    assert compile_command("shape --target a --x 5 --space canvas")["space"] == "canvas"
