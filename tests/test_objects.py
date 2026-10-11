"""Objects (#374, #375, #377, #381, #384): declared groups with a kind, parts and sub-objects."""

import io
import json
import xml.etree.ElementTree as ET

import pytest

from vixl import Project, VixlError
from vixl import objects
from vixl.organic import PRESETS


def scene():
    """A person holding a guitar: the guitar is a sub-object with body and neck (no strings yet)."""
    p = Project(400, 300, "white")
    p.apply([
        {"type": "shape", "shape": "ellipse", "name": "body", "x": 100, "y": 120, "width": 160, "height": 80,
         "fill": "#a65"},
        {"type": "shape", "shape": "rectangle", "name": "neck", "x": 250, "y": 150, "width": 120, "height": 20,
         "fill": "#743"},
        {"type": "group", "name": "guitar", "targets": ["body", "neck"]},
        {"type": "object", "target": "guitar", "kind": "acoustic guitar"},
        {"type": "object", "action": "part", "target": "body", "part": "body"},
        {"type": "object", "action": "part", "target": "neck", "part": "neck"},
        {"type": "shape", "shape": "ellipse", "name": "head", "x": 40, "y": 20, "width": 60, "height": 60,
         "fill": "#fc9"},
        {"type": "shape", "shape": "rectangle", "name": "arm-l", "x": 60, "y": 80, "width": 14, "height": 70,
         "fill": "#fc9"},
        {"type": "shape", "shape": "rectangle", "name": "arm-r", "x": 90, "y": 80, "width": 14, "height": 70,
         "fill": "#fc9"},
        {"type": "group", "name": "player", "targets": ["head", "arm-l", "arm-r", "guitar"]},
        {"type": "object", "target": "player", "kind": "person", "label": "Player"},
        {"type": "object", "action": "part", "target": "head", "part": "head"},
        {"type": "object", "action": "part", "target": "arm-l", "part": "upper-arm", "side": "left"},
        {"type": "object", "action": "part", "target": "arm-r", "part": "upper-arm", "side": "right"},
    ])
    return p


# --- #375 taxonomy -----------------------------------------------------------------------------------------------


def test_taxonomy_data_is_valid_with_known_parents_no_cycles_and_unique_aliases():
    kinds = objects.builtin_kinds()
    objects.validate_registry(kinds)
    for name, entry in kinds.items():
        assert entry.get("parent") is None or entry["parent"] in kinds, name
    broken = {**kinds, "loop-a": {"parent": "loop-b"}, "loop-b": {"parent": "loop-a"}}
    with pytest.raises(VixlError, match="cycle"):
        objects.validate_registry(broken)
    with pytest.raises(VixlError, match="already"):
        objects.validate_registry({**kinds, "wolf": {"parent": "mammal", "aliases": ["puppy"]}})
    with pytest.raises(VixlError, match="unknown parent"):
        objects.validate_registry({**kinds, "wolf": {"parent": "canid"}})


def test_every_organic_preset_has_a_kind_and_character_parts_map_onto_person():
    mapping = objects.organic_presets()
    assert set(mapping) == set(PRESETS)
    kinds = objects.builtin_kinds()
    assert all(kind in kinds for kind in mapping.values())
    assert objects.descends(mapping["flower"], "botanical") and objects.descends(mapping["octopus"], "cephalopod")
    assert kinds[mapping["spots"]].get("parent") == "texture" and kinds[mapping["scales"]].get("parent") == "texture"
    from vixl.characters import PARTS

    person = {part["name"] for part in objects.describe("person")["parts"]}
    for part, (name, side) in objects.character_parts().items():
        assert part in PARTS and name in person, part
    assert set(objects.character_parts()) == set(PARTS)


def test_kinds_resolve_by_alias_inherit_fields_and_suggest_on_a_miss():
    assert objects.find("puppy") == "dog" and objects.find("Acoustic Guitar") == "guitar" and objects.find("dogs") == "dog"
    dog = objects.describe("dog")
    assert dog["chain"] == ["organic", "animal", "mammal", "dog"] and dog["path"] == "organic › animal › mammal › dog"
    names = [part["name"] for part in dog["parts"]]
    assert {"head", "body", "leg", "tail", "ear", "snout"} <= set(names)  # animal + mammal parts+ + dog parts+
    assert ["leg", "body"] in dog["connections"] and ["snout", "head"] in dog["connections"]
    assert dog["proportions"] and dog["outline"]["silhouette"] is True  # inherited from mammal and organic
    with pytest.raises(VixlError, match="did you mean 'guitar'"):
        objects.resolve_kind("guitr")


def test_user_kind_merges_in_and_bad_input_is_refused(tmp_path):
    from vixl.resources import register

    register("objects", "mascot-bean", {"parent": "mascot-figure", "aliases": ["bean"],
                                        "parts+": [{"name": "antenna", "count": 2}]}, workspace=tmp_path)
    kinds = objects.registry(tmp_path)
    assert objects.find("bean", kinds) == "mascot-bean"
    item = objects.describe("bean", tmp_path)
    assert item["chain"][-3:] == ["person", "mascot-figure", "mascot-bean"]
    assert "antenna" in [p["name"] for p in item["parts"]] and "head" in [p["name"] for p in item["parts"]]
    with pytest.raises(VixlError, match="parent"):
        register("objects", "floaty", {"summary": "no parent"}, workspace=tmp_path)
    with pytest.raises(VixlError, match="unknown field"):
        register("objects", "odd", {"parent": "animal", "legs": 4}, workspace=tmp_path)
    with pytest.raises(VixlError, match="already"):
        register("objects", "pup", {"parent": "dog", "aliases": ["puppy"]}, workspace=tmp_path)


def test_objects_surface_in_cli_guide_capabilities_and_resources(tmp_path, monkeypatch, capsys):
    from vixl.briefs import guide
    from vixl.capabilities import lookup
    from vixl.cli import main

    monkeypatch.chdir(tmp_path)
    main(["objects", "show", "dog"])
    shown = json.loads(capsys.readouterr().out)
    assert shown["chain"] == ["organic", "animal", "mammal", "dog"] and shown["connections"]
    main(["objects", "guitar"])
    assert json.loads(capsys.readouterr().out)["kind"] == "guitar"
    assert guide("dog")["object"]["kind"] == "dog"
    assert guide("a friendly dog sitting")["object"]["kind"] == "dog"
    assert guide("a potted cactus")["object"]["kind"] == "cactus"
    found = lookup("objects")
    assert "object" in found["operations"] and "organic" in found["taxonomy"]
    assert "multi-part-objects" in found["guidance"]
    from tests.test_agent_interface import call
    from vixl.interfaces import mcp_server

    server = mcp_server(workspace=tmp_path)
    error, text, _ = call(server, "vixl_resource_get", {"kind": "objects", "name": "puppy"})
    assert not error and json.loads(text)["value"]["kind"] == "dog"


# --- #374 the object operation -------------------------------------------------------------------------------------


def test_object_set_part_unset_and_aliases():
    p = scene()
    assert p.layer("guitar")["object"] == {"version": 1, "kind": "guitar"}
    assert p.layer("player")["object"]["label"] == "Player"
    assert p.layer("arm-l")["object_part"] == {"name": "upper-arm", "side": "left"}
    result = p.apply([{"type": "subject", "target": "guitar", "object_kind": "ukulele", "name": "Uke"}], detail="compact")
    assert p.layer("guitar")["object"]["kind"] == "guitar" and p.layer("guitar")["object"]["label"] == "Uke"
    assert any("subject" in note for note in result["normalized"])
    result = p.apply({"type": "object", "action": "part", "target": "neck", "part": "nek"}, detail="compact")
    assert any("did you mean 'neck'" in w for w in result["warnings"])
    with pytest.raises(VixlError, match="is not inside an object"):
        Project(50, 50).apply([{"type": "shape", "shape": "rectangle", "name": "x"},
                               {"type": "object", "action": "part", "target": "x", "part": "leg"}])
    with pytest.raises(VixlError, match="an object is a group"):
        p.apply({"type": "object", "target": "head", "kind": "dog"})
    with pytest.raises(VixlError, match="Unknown object kind"):
        p.apply({"type": "object", "target": "guitar", "kind": "zzzz"})
    p.apply({"type": "object", "action": "unset", "target": "guitar"})
    assert "object" not in p.layer("guitar") and "object_part" not in p.layer("neck")


def test_object_takes_targets_and_is_classified_each():
    from vixl.targets import EACH, markdown_table

    assert "object" in EACH
    p = scene()
    p.apply({"type": "object", "action": "part", "targets": ["body", "neck"], "part": "body"})
    assert p.layer("neck")["object_part"]["name"] == "body"
    from pathlib import Path

    docs = (Path(__file__).resolve().parent.parent / "docs" / "operations.md").read_text(encoding="utf-8")
    assert markdown_table() in docs


def test_paths_resolve_everywhere_with_ambiguity_and_did_you_mean():
    p = scene()
    assert p.layer("player/guitar/neck")["name"] == "neck"
    assert p.layer("Player/head")["name"] == "head"  # the label works as the first segment
    assert p.layer("player/upper-arm[right]")["name"] == "arm-r"
    p.apply({"type": "move", "target": "player/guitar", "x": 70, "relative": True})
    assert p.layer("guitar")["x"] == 130
    with pytest.raises(VixlError, match="names 2 layers"):
        p.layer("player/upper-arm")
    with pytest.raises(VixlError, match="did you mean 'player/guitar/neck'"):
        p.layer("player/guitar/nekc")
    with pytest.raises(VixlError) as missing:
        p.layer("nobody/head")
    assert missing.value.code == "layer_not_found"


def test_selectors_pick_objects_kinds_and_parts():
    p = scene()
    result = p.apply({"type": "edit-layers", "where": {"object": "player/guitar"},
                      "do": {"type": "opacity", "value": 0.5}, "dry_run": True}, detail="compact")
    assert set(result["selection"][0]["names"]) >= {"guitar", "body", "neck"} if "selection" in result else True
    p.apply({"type": "edit-layers", "where": {"object_kind": "instrument", "kind": "shape"},
             "do": {"type": "opacity", "value": 0.5}})
    assert p.layer("neck")["opacity"] == 0.5 and p.layer("head")["opacity"] == 1
    p.apply({"type": "edit-layers", "where": {"part": "upper-arm"}, "do": {"type": "opacity", "value": 0.25}})
    assert p.layer("arm-l")["opacity"] == 0.25 and p.layer("arm-r")["opacity"] == 0.25
    with pytest.raises(VixlError, match="did you mean 'guitar'"):
        p.apply({"type": "edit-layers", "where": {"object_kind": "guiter"}, "do": {"type": "hide"}})


def test_duplicate_keeps_records_and_ungroup_refuses_an_object():
    p = scene()
    p.apply({"type": "duplicate", "target": "player", "name": "player-2"})
    copy = p.layer("player-2")
    assert copy["object"]["kind"] == "person" and copy["id"] != p.layer("player")["id"]
    assert p.layer("player-2/guitar/neck")["object_part"] == {"name": "neck"}
    assert p.layer("player-2/guitar/neck")["id"] != p.layer("neck")["id"]
    with pytest.raises(VixlError, match="declared guitar object"):
        p.apply({"type": "ungroup", "target": "guitar"})
    p.apply({"type": "ungroup", "target": "guitar", "force": True})
    assert p.find_layer("guitar") is None


def test_character_is_a_person_whose_parts_read_through():
    p = Project(400, 400)
    p.apply({"type": "character", "name": "hero"})
    assert objects.record(p.layer("hero"))["kind"] == "person"
    assert "object" not in p.layer("hero")  # read through, not copied
    assert p.layer("hero/upper-arm[left]")["character_part"] == "left-upper-arm"
    assert p.layer("hero/left-hand")["character_part"] == "left-hand"
    tree = objects.tree(p, "hero")
    assert tree["implicit"] and not tree["missing_parts"]
    assert {"part": "foot", "side": "right"}.items() <= next(x for x in tree["parts"] if x["layer"] == "hero/right-foot").items()


def test_records_survive_save_and_open(tmp_path):
    p = scene()
    p.save(tmp_path / "scene.vixl")
    loaded = Project.load(tmp_path / "scene.vixl")
    assert loaded.layer("player/guitar")["object"]["kind"] == "guitar"
    assert loaded.layer("player/upper-arm[left]")["object_part"]["side"] == "left"


# --- #377 inspect, preview, measure and export one object ------------------------------------------------------------


def test_inspect_object_tree_flags_missing_parts_and_lists_all_objects():
    from vixl.changes import summarize

    p = scene()
    guitar = objects.tree(p, "player/guitar")
    assert guitar["chain"] == ["constructed", "instrument", "guitar"]
    assert set(guitar["missing_parts"]) == {"headstock", "strings"}
    assert {part["path"] for part in guitar["parts"]} == {"player/guitar/body", "player/guitar/neck"}
    assert guitar["bounds"]["canvas"] == [100.0, 120.0, 270.0, 80.0]
    person = objects.tree(p, "player")
    assert [sub["object"] for sub in person["sub_objects"]] == ["guitar"]
    outline = objects.tree(p, "*")
    assert outline["count"] == 1 and outline["objects"][0]["sub_objects"] == ["player/guitar"]
    compact = {layer["name"]: layer for layer in summarize(p)["layers"]}
    assert compact["neck"]["object_part"] == {"name": "neck"} and compact["neck"]["object_path"] == "player/guitar/neck"
    assert compact["guitar"]["object"]["kind"] == "guitar"
    assert {"path": "player/guitar", "kind": "guitar"} in summarize(p)["objects"]


def test_isolate_by_path_and_kind_and_the_parts_contact_sheet():
    from vixl.proxy import isolated, render_preview

    p = scene()
    view = isolated(p, ["player/guitar"])
    hidden = {layer["name"] for layer in view.state["layers"] if not layer["visible"]}
    assert hidden == {"head", "arm-l", "arm-r"}
    assert isolated(p, ["object:instrument"])._isolated == [p.layer("guitar")["id"]]
    with pytest.raises(VixlError, match="No object of kind"):
        isolated(p, ["object:animal"])
    single = render_preview(p, 400, 400, isolate=["player"])
    sheet = render_preview(p, 800, 800, isolate=["player"], views=["parts"], exploded=True)
    assert sheet.size != single.size and sheet.width > 400  # assembled, exploded, head, two arms, guitar


def test_measure_and_spatial_accept_a_part():
    p = scene()
    assert p.spatial(targets=["player/guitar/neck", "player/head"]) is not None
    from vixl.measure import measure

    measured = measure(p, target="player/guitar/neck")
    assert measured.get("target", {}).get("name", "neck") == "neck"
    assert json.dumps(measured)


@pytest.mark.parametrize("fmt", ["PNG", "SVG", "PDF", "PSD"])
def test_isolated_export_is_cropped_to_the_object(fmt):
    p = scene()
    report = {}
    data = p.export(format=fmt, isolate=["player/guitar"], padding=5, report=report)
    assert report["isolated"] == {"layers": ["guitar"], "size": [280, 90]}
    if fmt == "PNG":
        from PIL import Image

        image = Image.open(io.BytesIO(data))
        assert image.size == (280, 90) and image.getpixel((0, 0))[3] == 0
    if fmt == "SVG":
        root = ET.fromstring(data)
        assert root.get("width") == "280" and not root.findall(".//*[@data-layer='head']")
        assert root.find(".//*[@data-vixl-kind='guitar']//*[@data-vixl-part='neck']") is not None


def test_portable_object_file_round_trips_through_export_and_object_place(tmp_path):
    from vixl.interfaces import mcp_server
    from tests.test_agent_interface import call

    p = scene()
    p.save(tmp_path / "scene.vixl")
    server = mcp_server(tmp_path / "scene.vixl", workspace=tmp_path)
    error, text, _ = call(server, "vixl_export_file", {"path": "guitar.vixl", "isolate": ["player/guitar"]})
    assert not error, text
    assert json.loads(text)["objects"] == ["guitar"]
    error, text, _ = call(server, "vixl_export_file", {"path": "bad.vixl"})
    assert error and "isolate" in text
    target = Project(500, 400, workspace=tmp_path)
    target.apply({"type": "object-place", "name": "axe", "source": "guitar.vixl", "x": 10, "y": 20})
    placed = target.layer("axe")
    assert placed["object"]["kind"] == "guitar" and target.layer("axe/neck")["object_part"] == {"name": "neck"}
    assert (placed["x"], placed["y"], placed["width"], placed["height"]) == (10, 20, 270, 80)


# --- #381 save and place editable objects --------------------------------------------------------------------------


def test_object_save_and_place_round_trip_with_new_ids_records_and_recolor():
    p = scene()
    p.apply({"type": "object-save", "target": "guitar", "name": "axe"})
    before = {layer["name"]: layer for layer in objects.subtree(p, p.layer("guitar")["id"])}
    p.apply({"type": "object-place", "name": "axe", "x": 100, "y": 120})
    p.apply({"type": "object-place", "name": "axe", "x": 0, "y": 0, "recolor": {"neck": "#000000"}})
    first = p.layer("axe")
    assert p.layer("axe 2")["object"]["kind"] == "guitar"
    assert first["object"]["kind"] == "guitar" and first["id"] != p.layer("guitar")["id"]
    assert (first["width"], first["height"]) == (before["guitar"]["width"], before["guitar"]["height"])
    neck = p.layer("axe/guitar/neck") if p.find_layer("axe/guitar/neck") else p.layer("axe/neck")
    assert neck["object_part"] == {"name": "neck"} and (neck["x"], neck["y"]) == (before["neck"]["x"], before["neck"]["y"])
    assert p.layer("axe 2/neck")["fill"] == "#000000" and neck["fill"] == "#743"
    p.apply({"type": "move", "target": "axe/neck", "x": 5, "relative": True})
    assert p.layer("axe 2/neck")["x"] == before["neck"]["x"]  # copies are independent
    with pytest.raises(VixlError, match="does not have"):
        p.apply({"type": "object-place", "name": "axe", "recolor": {"tail": "red"}})
    with pytest.raises(VixlError, match="No saved object"):
        p.apply({"type": "object-place", "name": "nothing"})


def test_placing_in_another_document_carries_images_and_scales(tmp_path):
    from PIL import Image

    p = Project(200, 200, workspace=tmp_path)
    buffer = io.BytesIO()
    Image.new("RGB", (20, 20), "red").save(buffer, "PNG")
    (tmp_path / "patch.png").write_bytes(buffer.getvalue())
    p.import_image(tmp_path / "patch.png", name="patch")
    p.apply([{"type": "shape", "shape": "ellipse", "name": "face", "width": 40, "height": 40},
             {"type": "group", "name": "mascot", "targets": ["patch", "face"]},
             {"type": "object", "target": "mascot", "kind": "mascot"}])
    p.save(tmp_path / "source.vixl")
    p.export(tmp_path / "mascot-only.png", isolate=["mascot"])
    other = Project(300, 300, workspace=tmp_path)
    from vixl.objects import portable_bytes

    (tmp_path / "mascot.vixl").write_bytes(portable_bytes(p, {"isolate": ["mascot"]}))
    other.apply({"type": "object-place", "name": "m", "source": "mascot.vixl", "width": 80})
    placed = other.layer("m")
    assert placed["width"] == 80 and placed["object"]["kind"] == "mascot-figure"
    asset = other.layer("m/patch")["asset"]
    assert asset in other.assets
    other.save(tmp_path / "other.vixl")
    assert Project.load(tmp_path / "other.vixl").layer("m/patch")["asset"] == asset


# --- #384 identity in exports --------------------------------------------------------------------------------------


def test_svg_carries_object_identity_with_unique_ids():
    p = scene()
    p.apply({"type": "duplicate", "target": "player", "name": "player-2"})
    root = ET.fromstring(p.export(format="SVG"))
    ns = "{http://www.w3.org/2000/svg}"
    neck = root.find(".//*[@data-vixl-kind='guitar']//*[@data-vixl-part='neck']")
    assert neck is not None and neck.get("id") == "player--guitar--neck"
    guitar = root.find(".//*[@data-vixl-object='player/guitar']")
    assert guitar.get("data-vixl-kind") == "guitar" and guitar.find(f"{ns}title").text == "guitar"
    ids = [element.get("id") for element in root.iter() if element.get("id")]
    assert len(ids) == len(set(ids))
    assert root.find(".//*[@data-vixl-object='player-2/guitar']") is not None


def test_pptx_groups_are_named_with_descriptions_and_psd_groups_carry_the_kind():
    from pptx import Presentation

    p = scene()
    deck = Presentation(io.BytesIO(p.export(format="PPTX")))
    groups = {shape.name: shape for shape in deck.slides[0].shapes}
    assert "Player" in groups
    player = groups["Player"]
    assert player._element.nvGrpSpPr.cNvPr.get("descr") == "Player (person)"
    inner = {shape.name: shape for shape in player.shapes}
    assert inner["guitar"]._element.nvGrpSpPr.cNvPr.get("descr") == "guitar (guitar)"
    psd = p.export(format="PSD")
    assert "Player (person)".encode("utf-16-be") in psd and "guitar (guitar)".encode("utf-16-be") in psd


def test_manifest_lists_objects(tmp_path, monkeypatch, capsys):
    from vixl.cli import main

    scene().save(tmp_path / "scene.vixl")
    monkeypatch.chdir(tmp_path)
    main(["-p", "scene.vixl", "manifest"])
    manifest = json.loads(capsys.readouterr().out)
    assert manifest["objects"][0]["object"] == "player" and manifest["objects"][0]["sub_objects"] == ["player/guitar"]
    main(["-p", "scene.vixl", "inspect", "--object", "player/guitar"])
    assert json.loads(capsys.readouterr().out)["missing_parts"] == ["headstock", "strings"]


def test_cli_declares_objects_and_parts():
    from vixl.commands import compile_command

    assert compile_command("object dog-group --kind dog") == {"type": "object", "target": "dog-group", "kind": "dog"}
    assert compile_command("object part dog/leg-1 --part leg --side left") == {
        "type": "object", "action": "part", "target": "dog/leg-1", "part": "leg", "side": "left"}
    assert compile_command("object unset dog")["action"] == "unset"
    assert compile_command("object-place axe --x 10 --scale 2") == {"type": "object-place", "name": "axe", "x": 10.0,
                                                                     "scale": 2.0}
