"""Four-legged characters: the quadruped rig, its walk, trot, gallop, jump and idle cycles, and bound artwork."""
import math

import pytest

from vixl.checks import check_design
from vixl.errors import VixlError
from vixl.project import Project
from vixl.plugins.characters.quadruped import CYCLES, LEGS, REQUIRED, SPECIES, foot_contacts
from vixl.spatial import canvas_boxes
from vixl.timeline import export_timeline, project_at, sample_track


def animal(species="horse", duration=1920, **fields):
    p = Project(520, 420, "#f3efe6")
    p.apply({"type": "timeline-set", "duration": duration, "loop_mode": "seamless"})
    p.apply({"type": "character", "name": "steed", "species": species, "height": 300, "x": 80, "y": 60, **fields})
    return p


def issues(p, *checks):
    return [item for item in check_design(p, checks=list(checks))["issues"] if item["check"] in checks]


def track(p, prop):
    ident = p.layer("steed")["id"]
    return next(t for t in p.state["timeline"]["tracks"] if t["target"] == ident and t["property"] == prop)


def joint_gaps(frame, group):
    """Distance between each part's pivot point and its parent's attachment for it, per bone."""
    bones = group["character"]["bones"]
    gaps = {}
    for name, bone in bones.items():
        if "parent" not in bone:
            continue
        child, parent = frame.layer(bone["layer"]), frame.layer(bones[bone["parent"]]["layer"])

        def pivot(layer):
            px, py = layer["pivot"]
            return layer["x"] + px * layer["width"], layer["y"] + py * layer["height"]

        turn = math.radians(-(parent["rotation"] - bones[bone["parent"]].get("rest", 0)))
        dx, dy = bone["at"]
        origin = pivot(parent)
        expected = (origin[0] + dx * math.cos(turn) + dy * math.sin(turn), origin[1] - dx * math.sin(turn) + dy * math.cos(turn))
        gaps[name] = math.dist(pivot(child), expected)
    return gaps


@pytest.mark.parametrize("species", sorted(SPECIES))
def test_standard_quadruped_has_named_parts_and_a_rig(species):
    p = animal(species)
    group = p.layer("steed")
    character = group["character"]
    assert character["plan"] == "quadruped" and character["species"] == species
    assert set(REQUIRED) <= set(character["parts"]) and {"neck", "tail"} <= set(character["parts"])
    assert ("horn" in character["parts"]) == (species == "unicorn")
    bones = character["bones"]
    for leg in LEGS:
        assert bones[f"{leg}-upper-leg"]["parent"] == "body"
        assert bones[f"{leg}-lower-leg"]["parent"] == f"{leg}-upper-leg"
        assert bones[f"{leg}-foot"]["parent"] == f"{leg}-lower-leg"
    assert bones["neck"]["parent"] == "body" and bones["head"]["parent"] == "neck" and bones["tail"]["parent"] == "body"
    # Shoulders sit ahead of the hips on the body, and every foot stands on one ground line.
    assert bones["front-right-upper-leg"]["at"][0] > 0 > bones["hind-right-upper-leg"]["at"][0]
    boxes = canvas_boxes(p)
    bottoms = [boxes[character["parts"][f"{leg}-foot"]][1] + boxes[character["parts"][f"{leg}-foot"]][3] for leg in LEGS]
    assert max(bottoms) - min(bottoms) < 1
    assert boxes[group["id"]][3] == pytest.approx(300, abs=4)
    assert issues(p, "character") == []
    assert max(joint_gaps(p, group).values()) < 1e-6


def test_facing_left_mirrors_the_animal():
    right, left = animal(), animal(facing="left")
    for p, ahead in ((right, 1), (left, -1)):
        boxes = canvas_boxes(p)
        parts = p.layer("steed")["character"]["parts"]
        head, tail = boxes[parts["head"]], boxes[parts["tail"]]
        assert ahead * ((head[0] + head[2] / 2) - (tail[0] + tail[2] / 2)) > 100
    with pytest.raises(VixlError):
        animal(facing="up")
    with pytest.raises(VixlError):
        Project(200, 200, "#ffffff").apply({"type": "character", "name": "hero", "facing": "left"})


@pytest.mark.parametrize("cycle", ["walk", "trot", "gallop", "idle"])
def test_gaits_are_editable_joint_keys_that_loop_and_keep_the_joints_connected(cycle):
    p = animal()
    p.apply({"type": "character-cycle", "target": "steed", "cycle": cycle})
    group = p.layer("steed")
    tracks = [t for t in p.state["timeline"]["tracks"] if t["target"] == group["id"]]
    props = {t["property"] for t in tracks}
    # The cycle is angles of named joints on the character (and the body's rise and fall), not baked part positions.
    assert {"joint:body", "joint:tail", "translate-y", *(f"joint:{leg}-upper-leg" for leg in LEGS)} <= props
    assert all(prop == "translate-y" or prop.startswith("joint:") for prop in props)
    assert len(tracks) == len(p.state["timeline"]["tracks"])
    assert 4 <= len(track(p, "joint:front-right-upper-leg")["keys"]) <= 40
    # Seamless: every track ends where it starts, and the motion check has nothing to say.
    for t in tracks:
        assert sample_track(p, t, 1920) == pytest.approx(sample_track(p, t, 0), abs=1e-3)
    assert issues(p, "character", "motion") == []
    for time in range(0, 1920, 96):
        frame = project_at(p, time)
        assert max(joint_gaps(frame, frame.layer("steed")).values()) < 1e-6


def landings(p, start, period):
    """The time within one stride at which each foot comes down."""
    contacts = foot_contacts(p, p.layer("steed"), 0, p.state["timeline"]["duration"])
    result = {}
    for leg, spans in contacts.items():
        result[leg] = next(begin for begin, _ in spans if begin >= start) - start
        assert result[leg] < period + 20
    return result


def test_gallop_feet_land_in_sequence_and_leave_the_ground_together():
    p = animal()
    p.apply({"type": "character-cycle", "target": "steed", "cycle": "gallop"})
    contacts = foot_contacts(p, p.layer("steed"), 0, 1920)
    # Four strides in the loop; each foot comes down once a stride.
    assert all(3 <= len(spans) <= 5 for spans in contacts.values())
    first = landings(p, 400, 480)
    order = sorted(first, key=lambda leg: (first[leg] - first["hind-left"]) % 480)
    assert order == ["hind-left", "hind-right", "front-left", "front-right"]
    # The suspension: some frames of every stride have no foot on the ground.
    grounded = {time for spans in contacts.values() for begin, end in spans for time in range(begin, end + 1, 10)}
    assert any(time not in grounded for time in range(480, 960, 10))
    # A foot on the ground stays where it landed while the body travels over it.
    ident = p.layer("steed")["character"]["parts"]["hind-left-foot"]
    begin, end = next(span for span in contacts["hind-left"] if span[0] >= 400)
    assert end - begin >= 60
    low = [canvas_boxes(project_at(p, time))[ident] for time in range(begin, end + 1, 10)]
    assert max(box[1] + box[3] for box in low) - min(box[1] + box[3] for box in low) < 7


def test_walk_and_trot_footfall_patterns():
    p = animal(duration=2000)
    p.apply({"type": "character-cycle", "target": "steed", "cycle": "walk", "period": 1000})
    first = landings(p, 900, 1000)
    order = sorted(first, key=lambda leg: (first[leg] - first["hind-left"]) % 1000)
    assert order == ["hind-left", "front-left", "hind-right", "front-right"]  # four beats, one side then the other
    p = animal(duration=1280)
    p.apply({"type": "character-cycle", "target": "steed", "cycle": "trot"})
    first = landings(p, 600, 640)
    assert abs(first["hind-left"] - first["front-right"]) <= 40 and abs(first["hind-right"] - first["front-left"]) <= 40
    assert abs((first["hind-left"] - first["hind-right"]) % 640 - 320) <= 60  # diagonal pairs, half a stride apart


def test_a_gait_that_runs_to_the_loop_end_fits_whole_strides():
    p = animal(duration=2000)
    result = p.apply({"type": "character-cycle", "target": "steed", "cycle": "trot"})
    assert any("whole stride" in warning for warning in result["warnings"])
    assert issues(p, "motion") == []
    # Run again with another stride: the old keys in the span are replaced, not mixed in.
    count = len(track(p, "joint:hind-left-upper-leg")["keys"])
    p.apply({"type": "character-cycle", "target": "steed", "cycle": "trot"})
    assert len(track(p, "joint:hind-left-upper-leg")["keys"]) == count


def test_jump_blends_into_a_gallop_and_adds_its_height_to_the_bob():
    p = animal()
    p.apply({"type": "character-cycle", "target": "steed", "cycle": "gallop"})
    before = {t["property"]: [dict(key) for key in t["keys"]] for t in p.state["timeline"]["tracks"]}
    gallop = {prop: {time: sample_track(p, {"property": prop, "keys": keys}, time) for time in (0, 240, 480, 1440, 1700, 1920)}
              for prop, keys in before.items()}
    p.apply({"type": "character-cycle", "target": "steed", "cycle": "jump", "start": 480, "duration": 960, "amount": 120})
    hind = track(p, "joint:hind-right-upper-leg")
    # Outside the window the gallop is untouched; inside it are the jump's few poses, entered and left at the
    # gallop's own values.
    for time in (0, 240, 480, 1440, 1700, 1920):
        assert sample_track(p, hind, time) == pytest.approx(gallop["joint:hind-right-upper-leg"][time], abs=1e-6)
    assert [key["time"] for key in hind["keys"] if 480 <= key["time"] <= 1440] == [480, 653, 806, 979, 1171, 1325, 1440]
    assert sample_track(p, hind, 806) == pytest.approx(-42)  # pushing off: the hind legs reach back
    # The leap is an additive layer over the gallop's own rise and fall, which keeps its keys.
    bob = track(p, "translate-y")
    assert bob["keys"] == before["translate-y"] and [layer["layer"] for layer in bob["add"]] == ["jump"]
    apex = 480 + round(0.52 * 960)
    own = sample_track(p, {"property": "translate-y", "keys": bob["keys"]}, apex)
    assert sample_track(p, bob, apex) == pytest.approx(own - 120)
    assert sample_track(p, bob, 480) == pytest.approx(gallop["translate-y"][480])
    boxes = [canvas_boxes(project_at(p, time))[p.layer("steed")["id"]] for time in (0, apex)]
    assert boxes[0][1] - boxes[1][1] > 80
    assert issues(p, "character", "motion") == []
    for time in range(480, 1441, 96):
        frame = project_at(p, time)
        assert max(joint_gaps(frame, frame.layer("steed")).values()) < 1e-6
    # A second jump replaces the first one's height instead of stacking on it.
    p.apply({"type": "character-cycle", "target": "steed", "cycle": "jump", "start": 480, "duration": 960, "amount": 60})
    assert sample_track(p, track(p, "translate-y"), apex) == pytest.approx(own - 60)


def test_standing_jump_starts_and_ends_at_rest():
    p = animal(duration=1000)
    p.apply({"type": "character-cycle", "target": "steed", "cycle": "jump"})
    for t in p.state["timeline"]["tracks"]:
        assert sample_track(p, t, 0) == pytest.approx(0) and sample_track(p, t, 1000) == pytest.approx(0)
    assert sample_track(p, track(p, "joint:front-right-lower-leg"), 520) == pytest.approx(-100)
    assert issues(p, "character") == []


def test_humanoid_and_quadruped_cycles_do_not_cross():
    p = animal()
    with pytest.raises(VixlError, match="walk, trot, gallop, jump, idle"):
        p.apply({"type": "character-cycle", "target": "steed", "cycle": "run"})
    q = Project(300, 400, "#ffffff")
    q.apply({"type": "character", "name": "hero", "height": 300})
    with pytest.raises(VixlError, match="humanoid"):
        q.apply({"type": "character-cycle", "target": "hero", "cycle": "gallop"})
    assert set(CYCLES) == {"walk", "trot", "gallop", "jump", "idle"}


def drawn_animal():
    """An animal drawn by hand in the canvas: slanted legs, no feet, neck and tail."""
    p = Project(400, 300, "#ffffff")
    p.apply({"type": "timeline-set", "duration": 1280, "loop_mode": "seamless"})
    ops = [{"type": "shape", "shape": "ellipse", "name": "barrel", "x": 100, "y": 90, "width": 180, "height": 70, "fill": "#444444"},
           {"type": "shape", "shape": "ellipse", "name": "skull", "x": 285, "y": 40, "width": 60, "height": 40, "fill": "#444444"},
           {"type": "shape", "shape": "rectangle", "name": "throat", "x": 262, "y": 60, "width": 26, "height": 60, "fill": "#444444"},
           {"type": "shape", "shape": "rectangle", "name": "brush", "x": 92, "y": 100, "width": 10, "height": 70, "fill": "#222222"}]
    parts = {"body": "barrel", "head": "skull", "neck": "throat", "tail": "brush"}
    for leg, x in (("front-left", 252), ("front-right", 240), ("hind-left", 132), ("hind-right", 120)):
        ops.append({"type": "shape", "shape": "rectangle", "name": f"{leg}-thigh", "x": x, "y": 130, "width": 18, "height": 70, "fill": "#555555"})
        ops.append({"type": "shape", "shape": "rectangle", "name": f"{leg}-shin", "x": x + 3, "y": 196, "width": 12, "height": 74, "fill": "#666666"})
        parts[f"{leg}-upper-leg"], parts[f"{leg}-lower-leg"] = f"{leg}-thigh", f"{leg}-shin"
    p.apply(ops)
    p.apply({"type": "rotate", "target": "hind-right-thigh", "value": 12})
    return p, parts


def test_bound_artwork_is_rigged_from_its_layers_and_runs_the_cycles():
    p, parts = drawn_animal()
    before = canvas_boxes(p)
    p.apply({"type": "character", "name": "steed", "plan": "quadruped", "parts": parts})
    group = p.layer("steed")
    bones = group["character"]["bones"]
    assert set(bones) == set(parts) and "front-left-foot" not in bones
    assert bones["hind-right-upper-leg"]["rest"] == 12  # the rotation it was drawn with is its rest pose
    after = canvas_boxes(p)
    for name in ("barrel", "skull", "throat", "front-left-shin", "hind-right-thigh"):
        assert after[p.layer(name)["id"]] == pytest.approx(before[p.layer(name)["id"]], abs=0.01)  # binding moves nothing
    assert issues(p, "character") == []
    p.apply({"type": "character-cycle", "target": "steed", "cycle": "trot"})
    assert issues(p, "character", "motion") == []
    contacts = foot_contacts(p, p.layer("steed"))
    assert all(len(contacts[leg]) >= 2 for leg in LEGS)
    p.apply({"type": "character-cycle", "target": "steed", "cycle": "jump", "start": 320, "duration": 640})
    assert [item for item in issues(p, "character", "motion") if item["severity"] != "info"] == []
    swing = [project_at(p, time).layer("front-right-thigh")["rotation"] for time in range(0, 320, 40)]
    assert max(swing) != min(swing)
    with pytest.raises(VixlError, match="hind-left-lower-leg"):
        q, parts = drawn_animal()
        del parts["hind-left-lower-leg"]
        q.apply({"type": "character", "name": "steed", "plan": "quadruped", "parts": parts})
    with pytest.raises(VixlError, match="Unknown quadruped part"):
        q, parts = drawn_animal()
        q.apply({"type": "character", "name": "steed", "plan": "quadruped", "parts": {**parts, "wing": "brush"}})


def test_character_check_reports_a_part_pulled_off_its_joint():
    p = animal()
    assert issues(p, "character") == []
    leg = p.layer("steed")["character"]["parts"]["front-right-lower-leg"]
    p.apply({"type": "move", "target": leg, "x": p.layer(leg)["x"] + 40, "y": p.layer(leg)["y"]})
    found = issues(p, "character")
    assert [item["code"] for item in found] == ["joint-detached"] and "front-right-lower-leg" in found[0]["message"]
    p.apply({"type": "character-pose", "target": "steed", "angles": {}})
    assert issues(p, "character") == []
    # A part animated on its own track leaves the body mid-loop.
    p.apply({"type": "animate", "target": leg, "property": "translate-y", "from": 0, "to": 60, "end": 960, "close": True})
    found = issues(p, "character")
    assert [item["code"] for item in found] == ["joint-detached"]


def test_quadruped_saves_loads_and_exports(tmp_path):
    p = animal("unicorn")
    p.apply({"type": "character-cycle", "target": "steed", "cycle": "gallop"})
    p.apply({"type": "character-save", "target": "steed", "name": "sparkle"})
    p.apply({"type": "character-load", "name": "twin", "template": "sparkle", "x": 200, "y": 60, "colors": {"coat": "#223344"}})
    twin = p.layer("twin")
    assert twin["character"]["plan"] == "quadruped" and twin["character"]["species"] == "unicorn"
    assert p.layer(twin["character"]["parts"]["body"])["fill"] == "#223344"
    p.apply({"type": "character-cycle", "target": "twin", "cycle": "walk"})
    assert issues(p, "character") == []
    p.save(tmp_path / "herd.vixl")
    loaded = Project.load(tmp_path / "herd.vixl")
    assert loaded.layer("steed")["character"]["bones"]["neck"]["parent"] == "body"
    report = export_timeline(loaded, tmp_path / "herd.gif", fps=10)
    assert report["frames"] >= 8
    export_timeline(loaded, tmp_path / "herd.json", fps=10)
