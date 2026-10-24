"""The ``object`` check (#378): declared objects measured against their kind."""

import pytest

from vixl import Project, objects
from vixl import object_check
from vixl.checks import CHECKS

SEEDS = ("person", "dog", "cat", "bird", "fish", "tree", "flower", "leaf", "mushroom", "guitar", "car", "house", "cup",
         "rock", "cloud")
# One part per seed that nothing else attaches to, and a move that takes it clear of what it touches.
LOOSE = {"person": ("walker/hand[left]", -100, 0), "dog": ("dog/tail", -60, 0), "cat": ("cat/tail", -40, -60),
         "bird": ("bird/beak", 130, 0), "fish": ("fish/tail-fin", 0, 140), "tree": ("tree/branch-l", 130, 0),
         "flower": ("flower/leaf-l", 130, 0), "leaf": ("leaf/stalk", 130, 0), "mushroom": ("mushroom/stem", 0, 160),
         "guitar": ("guitar/bridge", 130, 0), "car": ("car/window-back", 0, -100), "house": ("house/chimney", 130, 0),
         "cup": ("cup/handle", 130, 0), "rock": ("rock/facet-top", 0, -100), "cloud": ("cloud/puff-left", -80, -100)}


def build(kind, width=420, height=520):
    p = Project(width, height, "#8ecae6")
    p.apply(objects.merged(kind)["build"]["example"])
    return p


def found(p, checks=("object",), **options):
    return [i for i in p.check(checks=list(checks), **options)["issues"] if i["check"] in ("object", "connected")]


def test_a_dog_with_three_legs_has_one_finding_with_rule_box_measure_action_and_hint():
    p = build("dog")
    p.apply({"type": "remove", "target": "dog/leg-near-front"})
    [issue] = found(p)
    assert issue["rule"] == "object.part-count" and issue["action"] == "fix" and issue["severity"] == "warning"
    assert issue["measured"] == {"actual": 3, "expected": 4, "unit": "parts"}
    assert len(issue["layer_ids"]) == 3 and len(issue["box"]) == 4
    assert "body.bottom" in issue["hint"] and issue["object"] == "dog" and issue["kind"] == "dog"
    assert p.check(checks=["object"])["passed"] is False


def test_a_missing_required_part_and_unknown_or_unsided_parts():
    p = build("dog")
    p.apply([{"type": "remove", "target": "dog/head"}, {"type": "remove", "target": "dog/eye"},
             {"type": "remove", "target": "dog/ear"}, {"type": "remove", "target": "dog/snout"}])
    [issue] = found(p)
    assert issue["rule"] == "object.part-missing" and issue["part"] == "head" and issue["measured"]["actual"] == 0
    p = build("bird")
    p.apply([{"type": "object", "action": "part", "target": "bird/wing[right]", "part": "wing"},
             {"type": "object", "action": "part", "target": "bird/wing[left]", "part": "wing"},
             {"type": "object", "action": "part", "target": "bird/eye", "part": "gizzard"}])
    rules = sorted(i["rule"] for i in found(p))
    assert rules == ["object.part-side", "object.part-unknown"]
    assert all(i["action"] == "review" for i in found(p))


def test_a_neck_detached_mid_animation_is_found_at_that_frame():
    p = build("guitar")
    neck, head = p.layer("guitar/neck"), p.layer("guitar/headstock")
    keys = []
    for layer in (neck, head):
        x = layer["x"]
        keys += [{"type": "keyframe", "target": layer["id"], "property": "x", "time": t, "value": v}
                 for t, v in ((0, x), (479, x + 160), (958, x))]
    p.apply([{"type": "timeline-set", "duration": 1000, "fps": 24}, *keys])
    [issue] = found(p, ("object", "connected"))
    assert issue["rule"] == "object.gap" and issue["frame"] == "middle" and issue["gap"] > 2
    assert issue["message"].startswith("guitar/neck ↔ guitar/body:") and "at the middle frame" in issue["message"]
    assert issue["measured"] == {"actual": issue["gap"], "expected": 2, "unit": "px"}


def test_proportions_out_of_range_and_the_stylized_and_ignore_opt_outs():
    p = build("guitar")
    p.apply({"type": "resize", "target": "guitar/neck", "height": 220})
    [issue] = found(p)
    assert issue["rule"] == "object.proportion" and issue["action"] == "review"
    assert issue["measured"]["expected"] == [0.45, 0.7] and issue["measured"]["actual"] > 0.7
    p.apply({"type": "object", "target": "guitar", "stylized": True})
    assert found(p) == [] and objects.tree(p, "guitar")["stylized"] is True
    p.apply([{"type": "object", "target": "guitar", "stylized": False},
             {"type": "object", "target": "guitar", "proportions": "ignore"}])
    assert found(p) == [] and p.layer("guitar")["object"]["proportions"] == "ignore"
    p.apply({"type": "object", "target": "guitar", "proportions": "check"})
    assert [i["rule"] for i in found(p)] == ["object.proportion"]


def test_a_person_head_ratio_is_measured_in_the_objects_own_frame():
    p = build("person")
    p.apply({"type": "scale", "target": "walker/head", "factor": 2})
    [issue] = found(p)
    assert issue["rule"] == "object.proportion" and issue["part"] == "head"
    p = build("dog")
    p.apply({"type": "rotate", "target": "dog", "angle": 90})
    assert found(p) == []


def bear(ear_scale=1.0, left_x=140):
    p = Project(400, 400, "white")
    size = 40 * ear_scale
    p.apply([
        {"type": "shape", "shape": "ellipse", "name": "ear-l", "x": left_x, "y": 60, "width": size, "height": size, "fill": "#7f5539"},
        {"type": "shape", "shape": "ellipse", "name": "ear-r", "x": 220, "y": 60, "width": 40, "height": 40, "fill": "#7f5539"},
        {"type": "shape", "shape": "ellipse", "name": "body", "x": 130, "y": 150, "width": 140, "height": 180, "fill": "#9c6644"},
        {"type": "shape", "shape": "ellipse", "name": "head", "x": 150, "y": 70, "width": 100, "height": 100, "fill": "#9c6644"},
        *[{"type": "shape", "shape": "capsule", "name": f"leg-{i}", "x": 140 + i * 30, "y": 280, "width": 26, "height": 60,
           "fill": "#7f5539"} for i in range(4)],
        {"type": "group", "name": "bear", "targets": ["ear-l", "ear-r", "body", "head", "leg-0", "leg-1", "leg-2", "leg-3"]},
        {"type": "object", "target": "bear", "kind": "bear"},
        {"type": "object", "action": "part", "target": "body", "part": "body"},
        {"type": "object", "action": "part", "target": "head", "part": "head"},
        {"type": "object", "action": "part", "target": "ear-l", "part": "ear", "side": "left"},
        {"type": "object", "action": "part", "target": "ear-r", "part": "ear", "side": "right"},
        {"type": "object", "action": "part", "targets": ["leg-0", "leg-1", "leg-2", "leg-3"], "part": "leg"},
    ])
    return p


def test_mirrored_ears_that_differ_in_size_or_sit_on_one_side():
    assert found(bear()) == []
    [issue] = found(bear(ear_scale=1.5))
    assert issue["rule"] == "object.symmetry-size" and issue["measured"]["expected"] == 0.15
    assert issue["message"].startswith("bear/ear[left] and bear/ear[right] differ in size by")
    [issue] = found(bear(left_x=205))
    assert issue["rule"] == "object.symmetry-side" and "bear/head" in issue["message"]
    p = bear(left_x=205)
    p.apply([{"type": "object", "action": "part", "target": "bear/ear[left]", "part": "ear", "side": "left", "depth": "far"}])
    assert found(p) == []  # a side view: far and near are not mirrored
    assert objects.tree(p, "bear")["parts"][0]["depth"] == "far"


def test_a_far_leg_above_the_body_is_one_layering_finding():
    p = build("dog")
    p.apply({"type": "top", "target": "dog/leg-far-front"})
    [issue] = found(p)
    assert issue["rule"] == "object.layering" and issue["action"] == "review"
    assert issue["message"].startswith("dog/leg (leg-far-front) (far limbs) draws over dog/body")
    assert issue["measured"]["expected"][:3] == ["far limbs", "tail", "body"]
    p = build("guitar")
    p.apply({"type": "bottom", "target": "guitar/strings"})
    [issue] = found(p)
    assert issue["rule"] == "object.layering" and issue["layer_ids"][0] == p.layer("guitar/strings")["id"]


def test_connected_leaves_declared_objects_to_the_object_check():
    p = build("dog")
    p.apply([{"type": "move", "target": "dog/tail", "x": -60, "relative": True},
             {"type": "shape", "shape": "ellipse", "name": "a", "x": 10, "y": 400, "width": 30, "height": 30},
             {"type": "shape", "shape": "ellipse", "name": "b", "x": 100, "y": 400, "width": 30, "height": 30},
             {"type": "group", "name": "plain", "targets": ["a", "b"]}])
    both = found(p, ("object", "connected"))
    assert [(i["check"], i.get("group")) for i in both] == [("object", None), ("connected", "plain")]
    assert both[0]["rule"] == "object.gap" and both[0]["message"].startswith("dog/tail ↔ dog/body")
    alone = found(p, ("connected",))
    assert sorted(i["group"] for i in alone) == ["dog", "plain"]
    p.apply({"type": "layer-intent", "target": "dog/tail", "detached_ok": True})
    assert found(p) == []  # a part that floats on purpose


@pytest.mark.parametrize("kind", SEEDS)
def test_breaking_one_constraint_of_a_seed_gives_exactly_one_finding(kind):
    p = build(kind, 620, 520)
    assert found(p) == []
    target, dx, dy = LOOSE[kind]
    p.apply({"type": "move", "target": target, "x": dx, "y": dy, "relative": True})
    issues = found(p)
    assert [i["rule"] for i in issues] == ["object.gap"], [i["message"] for i in issues]
    assert issues[0]["action"] == "fix" and issues[0]["hint"]


def test_object_runs_by_default_only_where_objects_are_declared():
    assert "object" in CHECKS
    p = build("dog")
    p.apply({"type": "move", "target": "dog/tail", "x": -60, "relative": True})
    report = p.check()
    assert "object" in report["checked"]["checks"]
    assert [i["rule"] for i in report["issues"] if i["check"] == "object"] == ["object.gap"]
    plain = Project(400, 400)
    plain.apply({"type": "character", "name": "hero"})
    assert not [i for i in plain.check()["issues"] if i["check"] == "object"]  # a character is checked by character
    plain.apply({"type": "object", "target": "hero", "kind": "person"})
    assert [i["rule"] for i in plain.check()["issues"] if i["check"] == "object"] == ["object.proportion"]
    plain.apply({"type": "object", "target": "hero", "stylized": True})
    assert not [i for i in plain.check()["issues"] if i["check"] == "object"]


def test_targets_limit_the_check_to_the_objects_they_touch():
    p = Project(900, 520, "#8ecae6")
    p.apply(objects.merged("dog")["build"]["example"])
    p.apply([{**op, "x": op["x"] + 440} if "x" in op else op for op in objects.merged("cloud")["build"]["example"]])
    p.apply([{"type": "move", "target": "dog/tail", "x": -60, "relative": True},
             {"type": "move", "target": "cloud/puff-left", "x": -80, "y": -100, "relative": True}])
    assert sorted(i["object"] for i in found(p)) == ["cloud", "dog"]
    assert [i["object"] for i in found(p, targets=["dog/head"])] == ["dog"]
    assert [i["object"] for i in found(p, targets=["cloud"])] == ["cloud"]


def test_part_masks_drawn_over_the_object_region_match_the_canvas_render():
    from vixl.parts import part_mask
    from vixl.render import resolve_layout, resolved_layers

    p = build("dog", 700, 700)
    p.apply([{"type": "shape", "shape": "rectangle", "name": "ground", "x": 0, "y": 600, "width": 700, "height": 40},
             {"type": "group", "name": "scene", "targets": ["dog", "ground"]},
             {"type": "rotate", "target": "dog", "angle": 30}, {"type": "scale", "target": "scene", "factor": 1.3},
             {"type": "effect", "effect": "drop-shadow", "target": "dog/body"}])
    kinds = objects.registry()
    context = object_check.Context(p, None, kinds, 2, object_check.frames_of(p))
    [subject] = object_check.subjects(p, kinds)
    left, top, width, height = context.region(subject)
    layers = resolved_layers(p)
    local, index = resolve_layout(p, layers=layers), {item["id"]: item for item in layers}
    for layer in subject.parts:
        full = part_mask(p, index[layer["id"]], local, index)
        mine = context.mask(subject, layer)
        assert mine.shape == (height, width) and full.sum() == mine.sum() > 0
        assert (full[top:top + height, left:left + width] == mine).mean() > 0.999


def test_more_findings_plug_in_through_finders(monkeypatch):
    def outline(context, subject):
        yield object_check.Finding("outline-seam", f"{subject.path}: a seam shows", [subject.group], "review",
                                   {"actual": 1, "expected": 0, "unit": "seams"}, "outline the silhouette")

    monkeypatch.setattr(object_check, "FINDERS", [*object_check.FINDERS, outline])
    p = build("cup")
    [issue] = found(p)
    assert issue["rule"] == "object.outline-seam" and issue["hint"] == "outline the silhouette"
    assert issue["layer_ids"] == [p.layer("cup")["id"]] and issue["measured"]["unit"] == "seams"
