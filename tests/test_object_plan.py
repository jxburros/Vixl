"""object-plan: a scaffold of placeholder parts from an object kind (and figure-plan, its person alias)."""

import json
from pathlib import Path

import numpy as np
from PIL import Image
import pytest

from vixl import Project, objects
from vixl.errors import VixlError
from vixl.interfaces import Session
from vixl.object_plan import plan
from vixl.workflows import dispatch

FIXTURES = Path(__file__).parent / "fixtures" / "objects"
SEEDS = ("person", "dog", "cat", "bird", "fish", "tree", "flower", "leaf", "mushroom", "guitar", "car", "house", "cup",
         "rock", "cloud")


def object_issues(p):
    return [i for i in p.check(checks=["object"])["issues"] if i["check"] == "object"]


def applied(kind, **fields):
    p = Project(420, 420, "#f4efe6")
    result = plan({"kind": kind, **fields}, p)
    p.apply(result["operations"])
    return p, result


def test_figure_plan_output_is_unchanged(tmp_path):
    """The snapshot was written from figure-plan before object-plan existed; the plan itself stays byte-identical."""
    session = Session(workspace=tmp_path)
    for case in json.loads((FIXTURES / "figure-plan-snapshot.json").read_text(encoding="utf-8")):
        result = dispatch(session, "figure-plan", {"spec": case["spec"]})
        result = {key: value for key, value in result.items() if key != "normalized"}
        assert json.dumps(result) == case["json"], case["spec"]


def test_figure_plan_is_object_plan_with_the_person_template_and_says_so(tmp_path):
    session = Session(workspace=tmp_path)
    result = dispatch(session, "figure-plan", {"spec": {"height": 600}})
    assert result["normalized"] == [{"field": "workflow", "from": "figure-plan", "to": "object-plan",
                                     "reason": "figure-plan is object-plan with kind person and template figure-plan"}]
    direct = dispatch(session, "object-plan", {"kind": "person", "template": "figure-plan", "height": 600})
    assert direct["operations"] == result["operations"] and "normalized" not in direct
    with pytest.raises(VixlError, match="Unknown figure setting"):
        dispatch(session, "figure-plan", {"spec": {"seed": 3}})
    with pytest.raises(VixlError, match="takes kind person"):
        plan({"kind": "dog", "template": "figure-plan"})


@pytest.mark.parametrize("kind", SEEDS)
def test_every_seed_kind_scaffold_passes_the_object_check_as_generated(kind):
    p, result = applied(kind)
    assert object_issues(p) == []
    assert objects.missing_parts(p, p.layer(result["name"])) == []
    x, y, w, h = result["box"]
    assert 0 <= x and 0 <= y and x + w <= 420 and y + h <= 420  # fitted to the canvas by default
    kinds = [op["type"] if op.get("action") != "part" else "part" for op in result["operations"]]
    first = kinds.index("group")
    assert set(kinds[:first]) == {"shape"} and kinds[first + 1] == "object" and set(kinds[first + 2:]) == {"part"}


def test_parts_are_ordered_back_to_front_with_sides_and_depths():
    _, result = applied("dog")
    order = [op["name"] for op in result["operations"] if op["type"] == "shape"]
    far = [order.index(name) for name in order if name.startswith("dog-leg") and name.endswith("far")]
    near = [order.index(name) for name in order if name.startswith("dog-leg") and name.endswith("near")]
    assert max(far) < order.index("dog-body") < min(near) < order.index("dog-head") < order.index("dog-eye")
    depths = {op.get("depth") for op in result["operations"] if op.get("part") == "leg"}
    assert depths == {"far", "near"}
    _, bird = applied("bird")
    wings = [op for op in bird["operations"] if op.get("part") == "wing"]
    assert {(op["side"], op["depth"]) for op in wings} == {("right", "far"), ("left", "near")}
    p, person = applied("person")
    sides = {op["side"] for op in person["operations"] if op.get("part") == "hand"}
    assert sides == {"left", "right"} and person["head_units"] == 7.5
    names = {op["name"] for op in person["operations"] if op["type"] == "shape"}
    assert {"person-hand-left", "person-hand-right", "person-torso", "person-head"} <= names


def test_parts_follow_the_build_placements_and_overlap_what_they_attach_to():
    p, result = applied("guitar", x=0, y=0, height=600)
    body, neck, head = (p.layer(f"guitar-{part}") for part in ("body", "neck", "headstock"))
    assert neck["y"] < body["y"] < neck["y"] + neck["height"]  # the neck's bottom overlaps the body's top
    assert head["y"] < neck["y"] < head["y"] + head["height"]
    assert abs((neck["x"] + neck["width"] / 2) - (body["x"] + body["width"] / 2)) <= 1
    p, tree = applied("tree", height=300)
    trunk, canopy = p.layer("tree-trunk"), p.layer("tree-canopy")
    assert canopy["y"] < trunk["y"] < canopy["y"] + canopy["height"]


def test_proportions_sit_at_the_middle_of_their_range_and_a_seed_varies_inside_it():
    p, _ = applied("dog")
    head, body = p.layer("dog-head"), p.layer("dog-body")
    ratio = max(head["width"], head["height"]) / max(body["width"], body["height"])
    assert ratio == pytest.approx(0.45, abs=0.02)
    p, result = applied("tree", height=400)
    assert p.layer("tree-trunk")["height"] / result["box"][3] == pytest.approx(0.375, abs=0.02)
    p, result = applied("person", height=600)
    assert p.layer("person-head")["height"] / result["box"][3] == pytest.approx(1 / 7.5, abs=0.005)
    one, two = plan({"kind": "dog", "seed": 1}), plan({"kind": "dog", "seed": 2})
    assert one["operations"] != two["operations"]
    assert plan({"kind": "dog", "seed": 1})["operations"] == one["operations"]
    for seeded in (1, 2, 3):
        p, _ = applied("dog", seed=seeded)
        assert object_issues(p) == []


def test_a_head_outside_the_person_range_declares_the_object_stylized():
    p, result = applied("person", head_units=4)
    declare = next(op for op in result["operations"] if op["type"] == "object" and "kind" in op)
    assert declare["stylized"] is True and object_issues(p) == []


def test_with_nests_a_sub_object_in_front_of_the_parts():
    p, result = applied("person", height=400, **{"with": [{"kind": "guitar", "anchor": "torso.center"}]})
    guitar = p.layer("person-guitar")
    assert guitar["parent"] == p.layer("person")["id"] and guitar["object"]["kind"] == "guitar"
    assert result["sub_objects"][0]["name"] == "person-guitar"
    tree = objects.tree(p, "person")
    assert tree["sub_objects"][0]["kind"] == "guitar" and tree["missing_parts"] == []
    assert object_issues(p) == []
    layers = p.state["layers"]
    assert layers.index(p.layer("person-guitar-body")) > layers.index(p.layer("person-torso"))
    with pytest.raises(VixlError, match="no part for"):
        plan({"kind": "person", "with": [{"kind": "guitar", "anchor": "tail.center"}]})


def test_view_names_the_kinds_view_only():
    assert plan({"kind": "dog"})["view"] == "side" and plan({"kind": "house"})["view"] == "front"
    with pytest.raises(VixlError, match="side view"):
        plan({"kind": "dog", "view": "front"})


def test_box_and_names_and_refusals():
    p = Project(400, 300)
    first = plan({"kind": "car", "box": [20, 40, 200, 100]}, p)
    x, y, w, h = first["box"]
    assert 20 <= x and 40 <= y and x + w <= 221 and y + h <= 141 and (w >= 199 or h >= 99)
    p.apply(first["operations"])
    second = plan({"kind": "car"}, p)
    assert second["name"] == "car-2" and all(op["name"].startswith("car-2") for op in second["operations"]
                                              if op["type"] == "shape")
    with pytest.raises(VixlError, match="lists no parts"):
        plan({"kind": "vehicle"})
    with pytest.raises(VixlError, match="not both"):
        plan({"kind": "car", "box": [0, 0, 10, 10], "height": 20})
    with pytest.raises(VixlError, match="Unknown object-plan field"):
        plan({"kind": "car", "colour": "red"})


def test_every_kind_with_parts_plans_and_applies():
    kinds = objects.registry()
    for kind, entry in kinds.items():
        fields = objects.merged(kind, kinds)
        if fields.get("texture") or not fields.get("parts"):
            continue
        p = Project(300, 300)
        p.apply(plan({"kind": kind}, p)["operations"])
        assert objects.missing_parts(p, p.layer(kind)) == [], kind


def test_next_steps_name_each_part_its_placeholder_and_the_loop():
    result = plan({"kind": "guitar"})
    steps = {step["part"]: step for step in result["next_steps"]["parts"]}
    assert steps["neck"]["layers"] == ["guitar-neck"] and "body.top" in steps["neck"]["do"]
    assert result["next_steps"]["approach"] and "action: outline" in result["next_steps"]["then"][0]
    assert result["parts"]["strings"] == ["guitar-strings"]


def test_apply_false_leaves_the_document_untouched_and_apply_true_is_one_undo_step(tmp_path):
    session = Session(workspace=tmp_path)
    p = Project(400, 400)
    p.save(tmp_path / "pic.vixl")
    before = (tmp_path / "pic.vixl").read_bytes()
    result = dispatch(session, "object-plan", {"kind": "cup"}, document="pic.vixl")
    assert "applied" not in result and (tmp_path / "pic.vixl").read_bytes() == before
    result = dispatch(session, "object-plan", {"kind": "cup", "apply": True}, document="pic.vixl")
    assert result["applied"] is True
    p = Project.load(tmp_path / "pic.vixl")
    assert p.layer("cup")["object"]["kind"] == "cup" and len(p.nodes) == 2
    p.undo()
    assert p.state["layers"] == []


def test_the_cli_plans_without_a_document_and_applies_with_one():
    from vixl.cli import object_plan_command

    result, changed = object_plan_command(None, ["mushroom", "--height", "200", "--seed", "4"])
    assert not changed and result["box"][3] in (199, 200, 201) and result["kind"] == "mushroom"
    p = Project(300, 300)
    result, changed = object_plan_command(p, ["mushroom", "--box", "10", "10", "100", "200", "--apply"])
    assert changed and result["applied"] and p.layer("mushroom")["object"]["kind"] == "mushroom"
    with pytest.raises(VixlError, match="needs a document"):
        object_plan_command(None, ["mushroom", "--apply"])


def test_a_guitar_scaffold_renders_a_guitar_silhouette():
    """Acceptance: a guitar planned 600 px tall, rendered alone, matches the stored silhouette (IoU of the coarse
    masks) and reads as one: tall, with a narrow neck above a wider body."""
    p = Project(400, 700, "transparent")
    result = plan({"kind": "guitar", "x": 100, "y": 50, "height": 600}, p)
    p.apply(result["operations"])
    x, y, w, h = result["box"]
    assert h == pytest.approx(600, abs=2) and 2.2 < h / w < 3.6
    alpha = np.asarray(p.render().getchannel("A").crop((x, y, x + w, y + h)).resize((24, 64), Image.BILINEAR)) > 127
    expected = np.asarray(Image.open(FIXTURES / "guitar-silhouette.png").convert("L")) > 127
    iou = (alpha & expected).sum() / (alpha | expected).sum()
    assert iou > 0.9, iou
    rows = alpha.sum(axis=1)
    assert rows[:24].max() < rows[40:].max() / 2  # the neck and headstock are much narrower than the body
