"""Portable character packages (#521): the .vixlchar format, discover, inspect and place, the one library and its
validation."""

import hashlib
import io
import json
import zipfile
from pathlib import Path

import pytest

from vixl import Project
from vixl.errors import VixlError
from vixl.interfaces import Session
from vixl.plugins.characters import package as packages
from vixl.workflows import dispatch

FIXTURES = Path(__file__).parent / "fixtures" / "characters"


def hero(width=500, height=450, **character):
    p = Project(width, height)
    p.apply({"type": "character", "name": "hero", "x": 100, "y": 70, **character})
    return p


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    """A workspace with a character document, two scenes and the hero packaged; the user library is beside it."""
    monkeypatch.setenv("VIXL_CHARACTERS", str(tmp_path / "user-library"))
    root = tmp_path / "work"
    root.mkdir()
    hero().save(root / "cast.vixl")
    Project(600, 500).save(root / "scene-a.vixl")
    Project(600, 500).save(root / "scene-b.vixl")
    session = Session(workspace=root)
    dispatch(session, "character-package", {"target": "hero", "output": "chars/hero.vixlchar",
                                            "description": "A friendly guide", "tags": ["guide"],
                                            "version": "1.2.0"}, document="cast.vixl")
    return root, session


def members(path):
    with zipfile.ZipFile(path) as archive:
        return {name: archive.read(name) for name in archive.namelist()}


def repack(path, entries):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, data in entries.items():
            archive.writestr(name, data)
    path.write_bytes(buffer.getvalue())


def test_package_round_trip_keeps_the_rig_and_the_manifest_matches(workspace):
    root, session = workspace
    path = root / "chars" / "hero.vixlchar"
    files = members(path)
    assert set(files) == {"manifest.json", "character.vixl"}
    manifest = json.loads(files["manifest.json"])
    assert manifest["format"] == "vixl-character" and manifest["version"] == 1
    assert manifest["name"] == "hero" and manifest["kind"] == "person" and manifest["character_version"] == "1.2.0"
    assert manifest["files"]["character.vixl"] == hashlib.sha256(files["character.vixl"]).hexdigest()
    assert {"left-upper-arm", "right-lower-leg"} <= set(manifest["rig"])
    assert manifest["rig"]["left-lower-arm"] == {"part": "left-lower-arm", "parent": "left-upper-arm",
                                                 "length": manifest["rig"]["left-lower-arm"]["length"],
                                                 "limits": [-150, 150]}
    assert {"neutral", "confused", "celebrate"} <= set(manifest["expressions"])
    assert {"rest", "celebrate", "wave"} <= set(manifest["poses"]) and {"wave", "walk"} <= set(manifest["motions"])
    assert manifest["checks"] == ["character"]
    inspected = dispatch(session, "character-inspect", {"package": "chars/hero.vixlchar"})
    assert inspected["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert inspected["rig"] == manifest["rig"] and inspected["parts"] == manifest["parts"]
    placed = dispatch(session, "character-place", {"package": "hero", "x": 40}, document="scene-a.vixl")
    scene = Project.load(root / "scene-a.vixl")
    group = scene.layer(placed["layer"]["id"])
    original = Project.load(root / "cast.vixl").layer("hero")
    assert set(group["character"]["parts"]) == set(original["character"]["parts"])
    assert set(group["character"]["bones"]) == set(original["character"]["bones"])
    ids = {layer["id"] for layer in scene.state["layers"]}
    # Rig bindings point at the placed copies, never at the source document's layers.
    assert all(bone["layer"] in ids and bone["layer"] in group["character"]["parts"].values()
               for bone in group["character"]["bones"].values())
    assert not set(group["character"]["parts"].values()) & set(original["character"]["parts"].values())
    assert group["x"] == 40 and placed["checks"]["passed"]


def test_place_in_two_documents_with_motion_expression_and_pose_independently(workspace):
    root, session = workspace
    a = dispatch(session, "character-place", {"package": "chars/hero.vixlchar", "motion": "wave",
                                              "expression": "confused"}, document="scene-a.vixl")
    b = dispatch(session, "character-place", {"package": "chars/hero.vixlchar", "pose": "celebrate",
                                              "expression": "celebrate", "x": 300}, document="scene-a.vixl")
    c = dispatch(session, "character-place", {"package": "hero", "pose": "celebrate", "motion": "wave"},
                 document="scene-b.vixl")
    assert (a["motion"], a["expression"]) == ("wave", "confused") and (b["pose"], c["motion"]) == ("celebrate", "wave")
    scene = Project.load(root / "scene-a.vixl")
    first, second = scene.layer(a["layer"]["id"]), scene.layer(b["layer"]["id"])
    assert first["name"] != second["name"]
    tracks = scene.state["timeline"]["tracks"]
    moving = {track["target"] for track in tracks}
    assert set(first["character"]["parts"].values()) & moving
    assert not set(second["character"]["parts"].values()) & moving
    assert second["character"]["bones"]["left-upper-arm"]["angle"] == -100
    # Editing one copy leaves the other alone.
    head = second["character"]["parts"]["head"]
    scene.apply({"type": "shape", "target": first["character"]["parts"]["head"], "fill": "#00ff00"})
    assert scene.layer(head)["fill"] != "#00ff00"
    other = Project.load(root / "scene-b.vixl").layer(c["layer"]["id"])
    assert other["character"]["bones"]["right-upper-arm"]["angle"] == 100
    smirk = scene.layer(first["character"]["parts"]["mouth"])
    plain = scene.layer(second["character"]["parts"]["mouth"])
    assert smirk.get("rotation", 0) != 0 and plain.get("rotation", 0) == 0


def test_unknown_joint_missing_bone_and_missing_part_are_located_errors(workspace, tmp_path):
    root, session = workspace
    before = (root / "scene-a.vixl").read_bytes()
    with pytest.raises(VixlError) as caught:
        dispatch(session, "character-place", {"package": "hero", "pose": {"left-elbow": 30}}, document="scene-a.vixl")
    assert caught.value.details["field"] == "pose.left-elbow"
    assert caught.value.details["suggestions"] == ["left-lower-arm"]
    with pytest.raises(VixlError) as caught:
        dispatch(session, "character-place", {"package": "hero", "motion": "fly"}, document="scene-a.vixl")
    assert caught.value.details["field"] == "motion" and "wave" in caught.value.details["allowed"]
    assert (root / "scene-a.vixl").read_bytes() == before
    # A rig without arm bones cannot wave: packaging that motion names the bones it lacks.
    legs = hero()
    legs.apply({"type": "character-rig", "target": "hero", "bones": {
        "left-upper-leg": {"part": "left-upper-leg", "origin": [62, 180], "length": 55},
        "right-upper-leg": {"part": "right-upper-leg", "origin": [97, 180], "length": 55}}})
    with pytest.raises(VixlError) as caught:
        packages.build(legs, "hero", tmp_path / "legs.vixlchar", motions={"wave": {"cycle": "wave"}})
    assert caught.value.details["field"] == "motions.wave"
    assert caught.value.details["missing"] == ["right-upper-arm", "right-lower-arm"]
    assert "walk" in caught.value.details["suggestions"]
    with pytest.raises(VixlError, match="no right-upper-arm") as caught:
        legs.apply({"type": "character-cycle", "target": "hero", "cycle": "wave"})
    assert caught.value.details["field"] == "cycle"
    built = packages.build(legs, "hero", tmp_path / "legs.vixlchar")
    assert "wave" not in built["motions"] and "walk" in built["motions"]
    # Bound artwork without brows has no brow expressions.
    bound = Project(400, 400)
    names = ["torso", "head", "left-eye", "right-eye", "mouth", "left-upper-arm", "left-lower-arm", "left-hand",
             "right-upper-arm", "right-lower-arm", "right-hand", "left-upper-leg", "left-lower-leg", "left-foot",
             "right-upper-leg", "right-lower-leg", "right-foot"]
    bound.apply([{"type": "shape", "shape": "rectangle", "name": n, "x": 10 * i, "y": 10, "width": 8, "height": 30,
                  "fill": "#888"} for i, n in enumerate(names)])
    bound.apply([{"type": "character", "name": "bot", "parts": {n: n for n in names}},
                 {"type": "character-rig", "target": "bot", "bones": {
                     "right-upper-arm": {"origin": [84, 10], "length": 30}, "right-lower-arm": {
                         "parent": "right-upper-arm", "length": 30}}}])
    packages.build(bound, "bot", tmp_path / "bot.vixlchar")
    package = packages.read(tmp_path / "bot.vixlchar")
    assert "confused" not in package["manifest"]["expressions"]
    with pytest.raises(VixlError) as caught:
        packages.place(Project(300, 300), package, {"expression": {"left-brow": "raised"}})
    assert caught.value.details["field"] == "expression.left-brow" and caught.value.details["missing"] == ["left-brow"]


def test_overrides_colors_outfit_and_proportions_only_with_scale_parts(workspace):
    root, session = workspace
    placed = dispatch(session, "character-place", {"package": "hero", "colors": {"skin": "#7c5036"},
                                                   "outfit": {"torso": "#22aa66"}, "height": 160,
                                                   "scale_parts": {"head": 1.25, "left-upper-arm": 1.2}},
                      document="scene-a.vixl")
    scene = Project.load(root / "scene-a.vixl")
    group = scene.layer(placed["layer"]["id"])
    parts = group["character"]["parts"]
    source = Project.load(root / "cast.vixl").layer("hero")
    original = Project.load(root / "cast.vixl")
    assert scene.layer(parts["head"])["fill"] == "#7c5036" and scene.layer(parts["torso"])["fill"] == "#22aa66"
    assert scene.layer(parts["head"])["width"] == pytest.approx(original.layer(source["character"]["parts"]["head"])["width"] * 1.25)
    assert group["character"]["bones"]["left-upper-arm"]["length"] == pytest.approx(
        source["character"]["bones"]["left-upper-arm"]["length"] * 1.2)
    with pytest.raises(VixlError, match="scale_parts") as caught:
        dispatch(session, "character-place", {"package": "hero", "width": 100, "height": 300}, document="scene-a.vixl")
    assert caught.value.details["field"] == "height"
    with pytest.raises(VixlError) as caught:
        dispatch(session, "character-place", {"package": "hero", "colors": {"fur": "#000"}}, document="scene-a.vixl")
    assert caught.value.details["field"] == "colors" and "skin" in caught.value.details["allowed"]
    with pytest.raises(VixlError, match="at most 4"):
        dispatch(session, "character-place", {"package": "hero", "scale_parts": {"head": 9}}, document="scene-a.vixl")


def test_package_files_are_untrusted_and_bounded(workspace):
    root, session = workspace
    path = root / "chars" / "hero.vixlchar"
    files = members(path)
    bad = root / "bad.vixlchar"
    for entries, code in (
        ({**files, "../escape.txt": b"x"}, "invalid_pack"),
        ({**files, "character.vixl": files["character.vixl"] + b"\0"}, "invalid_pack"),
        ({"manifest.json": files["manifest.json"]}, "invalid_pack"),
        ({**files, "manifest.json": b"{" * 10 + b"}"}, "invalid_pack"),
        ({**files, "manifest.json": json.dumps({**json.loads(files["manifest.json"]), "run": "rm -rf /"}).encode()},
         "invalid_pack"),
        ({**files, "manifest.json": json.dumps({**json.loads(files["manifest.json"]), "parts": ["head"]}).encode()},
         "invalid_pack"),
        ({**files, "manifest.json": b" " * (packages.MAX_MANIFEST_BYTES + 1)}, "resource_limit"),
    ):
        repack(bad, entries)
        with pytest.raises(VixlError) as caught:
            dispatch(session, "character-inspect", {"package": "bad.vixlchar"})
        assert caught.value.code == code, entries.keys()
    bad.write_bytes(b"not a zip")
    with pytest.raises(VixlError, match="not a ZIP"):
        dispatch(session, "character-place", {"package": "bad.vixlchar"}, document="scene-a.vixl")
    assert "character_library" not in Project.load(root / "scene-a.vixl").state
    with pytest.raises(VixlError) as caught:
        dispatch(session, "character-package", {"target": "hero", "output": "chars/hero.vixlchar"}, document="cast.vixl")
    assert caught.value.code == "output_exists"
    rewritten = dispatch(session, "character-package", {"target": "hero", "output": "chars/hero.vixlchar",
                                                        "overwrite": True}, document="cast.vixl")
    assert rewritten["output"] == "chars/hero.vixlchar"
    with pytest.raises(VixlError, match="escapes"):
        dispatch(session, "character-inspect", {"package": "user:../cast.vixlchar"})


def test_discover_scans_the_workspace_and_user_library(workspace):
    root, session = workspace
    library = root.parent / "user-library"
    library.mkdir()
    (root / "chars" / "hero.vixlchar").replace(library / "hero.vixlchar")
    dispatch(session, "character-package", {"target": "hero", "output": "robots/scout.vixlchar", "name": "scout",
                                            "tags": ["robot"]}, document="cast.vixl")
    (root / ".hidden").mkdir()
    (root / ".hidden" / "skip.vixlchar").write_bytes(b"ignored")
    (root / "broken.vixlchar").write_bytes(b"not a package")
    found = dispatch(session, "character-discover", {})
    names = {(item["name"], item["source"], item["package"]) for item in found["characters"]}
    assert names == {("scout", "workspace", "robots/scout.vixlchar"), ("hero", "user", "user:hero.vixlchar")}
    assert [item["package"] for item in found["invalid"]] == ["broken.vixlchar"]
    assert dispatch(session, "character-discover", {"query": "robot"})["count"] == 1
    placed = dispatch(session, "character-place", {"package": "hero", "expression": "happy"}, document="scene-a.vixl")
    assert placed["package"] == "user:hero.vixlchar"
    scene = Project.load(root / "scene-a.vixl")
    scene.apply({"type": "character-save", "target": placed["layer"]["name"], "name": "guide"})
    scene.save(root / "scene-a.vixl", overwrite=True)
    listed = dispatch(session, "character-discover", {}, document="scene-a.vixl")
    assert listed["document"] == ["guide"]


def test_character_save_and_load_use_the_object_library_and_read_the_old_one():
    p = hero()
    p.apply({"type": "character-save", "target": "hero", "name": "hero-template", "tags": ["cast"]})
    saved = p.state["object_library"]["hero-template"]
    assert saved["kind"] == "person" and saved["tags"] == ["cast"] and "character_library" not in p.state
    p.apply({"type": "object-place", "name": "hero-template", "x": 260})
    assert len(p.state["layers"]) == 42
    with pytest.raises(VixlError, match="not a character"):
        p.apply([{"type": "shape", "name": "box", "shape": "rectangle", "width": 10, "height": 10, "fill": "#000"},
                 {"type": "group", "name": "crate", "targets": ["box"]},
                 {"type": "object-save", "target": "crate", "name": "crate"},
                 {"type": "character-load", "template": "crate", "name": "c"}])
    # A document saved before the one library keeps characters in character_library: character-load still reads it.
    old = hero()
    layers = [dict(layer) for layer in old.state["layers"]]
    old.state["character_library"] = {"legacy": layers}
    result = old.apply({"type": "character-load", "template": "legacy", "name": "friend", "x": 250})
    assert old.layer("friend")["character"] and any("character_library" in n for n in result.get("normalized", []))


def test_convert_moves_the_old_character_library_into_the_object_library(tmp_path):
    from vixl.convert import convert_file

    old = hero()
    old.apply({"type": "character-save", "target": "hero", "name": "taken"})
    old.state["character_library"] = {"guide": [dict(layer) for layer in old.state["layers"]],
                                      "taken": [dict(layer) for layer in old.state["layers"]]}
    old.save(tmp_path / "old.vixl")
    report = convert_file(tmp_path / "old.vixl", tmp_path / "new.vixl")
    new = Project.load(tmp_path / "new.vixl")
    assert "character_library" not in new.state
    assert {"guide", "taken", "taken-character"} <= set(new.state["object_library"])
    assert new.state["object_library"]["guide"]["kind"] == "person"
    moved = [change for change in report["changes"] if change["change"] == "character-library"]
    assert {(c["before"], c["after"]) for c in moved} == {("guide", "guide"), ("taken", "taken-character")}
    new.apply({"type": "character-load", "template": "guide", "name": "friend"})
    assert new.layer("friend")["character"]["bones"]


def test_a_declared_object_placed_from_a_package_passes_the_object_check(tmp_path):
    p = hero()
    p.apply({"type": "object", "target": "hero", "kind": "person", "stylized": True})
    built = packages.build(p, "hero", tmp_path / "mascot.vixlchar")
    assert built["checks"] == ["character", "object"]
    scene = Project(600, 500)
    package = packages.read(tmp_path / "mascot.vixlchar")
    placed = packages.place(scene, package, {"motion": "wave", "expression": "happy", "x": 80})
    assert placed["checks"]["passed"] and placed["checks"]["checks"] == ["character", "object"]
    assert scene.layer(placed["layer"]["id"])["object"]["kind"] == "person"
    assert scene.check(checks=["object"])["passed"]
    # The placement is one undo step.
    scene.undo()
    assert scene.state["layers"] == []
    # The standard character's shoulders sit outside its torso: raised arms open a gap the check reports.
    raised = packages.place(scene, package, {"pose": "celebrate"})
    assert not raised["checks"]["passed"]
    assert {issue["rule"] for issue in raised["checks"]["issues"]} == {"object.gap"}


def pose_snapshot(scene, group):
    """Each rigged part's box and rotation relative to the character group, rounded."""
    parts = group["character"]["parts"]
    shot = {}
    for part in sorted(parts):
        layer = scene.layer(parts[part])
        shot[part] = [round(layer[k], 1) for k in ("x", "y", "width", "height")] + [round(layer.get("rotation", 0), 1)]
    return shot


def test_representative_poses_match_their_snapshots(tmp_path):
    packages.build(hero(), "hero", tmp_path / "hero.vixlchar")
    package = packages.read(tmp_path / "hero.vixlchar")
    shots = {}
    for pose, expression in (("rest", "neutral"), ("celebrate", "celebrate"), ("wave", "confused"),
                             ("point", "surprised")):
        scene = Project(400, 400)
        placed = packages.place(scene, package, {"pose": pose, "expression": expression})
        shots[f"{pose}+{expression}"] = pose_snapshot(scene, scene.layer(placed["layer"]["id"]))
    expected = json.loads((FIXTURES / "pose-snapshots.json").read_text(encoding="utf-8"))
    assert shots == expected
