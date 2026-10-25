"""Object kinds link to construction knowledge (#376): the ``build`` block, its merge, its references and the
seed examples."""

import json

import pytest

from vixl import Project, VixlError, objects
from vixl.briefs import guide, object_guide, object_summary
from vixl.geometry import ANCHORS
from vixl.operations import OPERATION_TYPES
from vixl.schema import operation_schema, validate_operation

SEEDS = ("person", "dog", "cat", "bird", "fish", "tree", "flower", "leaf", "mushroom", "guitar", "car", "house", "cup",
         "rock", "cloud")


def example(kind):
    return objects.merged(kind)["build"]["example"]


def test_build_merges_down_the_chain_child_first_without_duplicates():
    build = objects.merged("dog")["build"]
    assert list(build) == [key for key in objects.BUILD_FIELDS if key in build]
    assert build["approach"][0].startswith("Dog:") and build["approach"][-1].startswith("Vary sizes")  # dog … organic
    assert build["palette"] == "natural:earth" and build["looks"][:2] == ["plush", "hand-made"]  # animal, mammal
    ears = [item for item in build["placements"] if item["part"] == "ear"]
    assert ears == [{"part": "ear", "anchor": "head.top-left", "at": "top"}]  # dog's ear replaces mammal's
    assert build["example"] == objects.builtin_kinds()["dog"]["build"]["example"]
    merged = objects.merge_build({"guidance": ["a", "b"], "palette": "x", "example": [{"type": "hide"}]},
                                 {"guidance": ["c", "a"], "palette": "y"})
    assert merged == {"guidance": ["c", "a", "b"], "palette": "y", "example": [{"type": "hide"}]}


def test_inherited_placements_fit_the_kind_and_anchors_read_canonically():
    assert not any(item["part"] == "eye" for item in objects.merged("insect").get("build", {}).get("placements", []))
    kinds = {**objects.builtin_kinds(), "pup": {"parent": "dog", "build": {
        "placements": [{"part": "tail", "anchor": "body.middle-left", "at": "center-right"}]}}}
    tail = next(item for item in objects.merged("pup", kinds)["build"]["placements"] if item["part"] == "tail")
    assert tail == {"part": "tail", "anchor": "body.left", "at": "right"}
    assert objects.placement_anchor("body.bottom-center") == ("body", "bottom")
    assert objects.spread("0.15-0.85") == (0.15, 0.85) and objects.spread("0.9-0.1") is None


def test_every_name_a_build_block_uses_exists():
    variants = {v["properties"]["type"]["const"]: v for v in operation_schema()["properties"]["operations"]["items"]["oneOf"]}
    kinds = objects.builtin_kinds()
    with_build = [name for name, entry in kinds.items() if entry.get("build")]
    assert set(SEEDS) <= set(with_build)
    for name in with_build:
        build = kinds[name]["build"]
        assert objects.unknown_references(build) == {}, name
        # A class block may name parts only some of its kinds have, but some kind at or below it has each one.
        below = [kind for kind in kinds if objects.descends(kind, name, kinds)]
        parts = {part["name"] for kind in below for part in objects.merged(kind, kinds).get("parts", [])}
        for item in build.get("placements", []):
            target, anchor = objects.placement_anchor(item["anchor"])
            assert anchor in ANCHORS and item["part"] in parts and target in parts | {"object"}, (name, item)
        for pattern in build.get("patterns", []):
            preset = variants[pattern["op"]]["properties"].get("preset", {})
            assert "preset" not in pattern or pattern["preset"] in preset.get("enum", []), (name, pattern)
    for name in SEEDS:
        build = objects.merged(name, kinds)["build"]
        parts = {part["name"] for part in objects.merged(name, kinds)["parts"]}
        for item in build["placements"]:
            assert item["part"] in parts and item["anchor"].split(".")[0] in parts | {"object"}, (name, item)
        assert build["approach"] and build["research"] and build["placements"] and "object" in build["checks"], name


def test_build_blocks_are_validated():
    with pytest.raises(VixlError, match="unknown field"):
        objects.validate_entry("pup", {"parent": "dog", "build": {"recipe": []}})
    with pytest.raises(VixlError, match="anchor"):
        objects.validate_entry("pup", {"parent": "dog", "build": {"placements": [{"part": "leg", "anchor": "body.under"}]}})
    with pytest.raises(VixlError, match="spread"):
        objects.validate_entry("pup", {"parent": "dog", "build": {"placements": [
            {"part": "leg", "anchor": "body.bottom", "spread": "0.8-0.2"}]}})
    with pytest.raises(VixlError, match="research"):
        objects.validate_entry("pup", {"parent": "dog", "build": {"research": [{"title": "x", "notes": "y",
                                                                               "url": "http://example.com"}]}})
    with pytest.raises(VixlError, match="does not have"):
        objects.validate_user_kind("pup", {"parent": "dog", "build": {"operations": ["teleport"]}})
    assert objects.unknown_references({"palette": "natural:lava", "shapes": ["ellipse", "blobfish"]}) == {
        "palette": ["natural:lava"], "shapes": ["blobfish"]}


@pytest.mark.parametrize("kind", SEEDS)
def test_seed_example_applies_renders_and_passes_the_checks(kind):
    ops = example(kind)
    assert 6 <= len(ops) <= 20, len(ops)
    assert all(op["type"] in OPERATION_TYPES for op in ops)
    for op in ops:
        validate_operation(json.loads(json.dumps(op)))
    assert any(op["type"] == "object" and op.get("kind") == kind for op in ops) and ops[-1]["type"] == "object"
    p = Project(420, 520, "#8ecae6")
    assert p.apply(ops)["success"]
    assert p.render().getbbox() is not None
    report = p.check(checks=["object", "connected"])
    assert [i["message"] for i in report["issues"]] == []
    assert [i["message"] for i in p.check(checks=["connected"])["issues"]] == []
    group = next(layer for layer in objects.all_objects(p) if layer.get("object"))
    assert objects.record(group)["kind"] == kind and not objects.missing_parts(p, group)


def test_vixl_reference_returns_the_build_block_and_example(tmp_path):
    found = guide("guitar")
    assert found["build"]["example"] == example("guitar")
    assert found["approach"][0].startswith("Guitar:") and "vixl_check(checks=['object'])" in " ".join(found["approach"])
    assert found["operations"] == found["build"]["operations"] and "build" not in found["object"]
    summary = object_summary("dog")
    assert summary["build"]["placements"] and not {"example", "research"} & set(summary["build"])
    assert "example" in summary["more"]
    from tests.test_agent_interface import call
    from vixl.interfaces import mcp_server

    server = mcp_server(workspace=tmp_path)
    error, text, _ = call(server, "vixl_reference", {"topic": "guitar"})
    assert not error and json.loads(text)["build"]["example"] == example("guitar")
    error, text, _ = call(server, "vixl_reference", {"topic": "objects", "name": "acoustic guitar"})
    assert not error and json.loads(text)["value"]["build"]["placements"]


def test_a_kind_without_a_build_block_gets_the_generic_loop():
    found = object_guide("fur")
    assert "build" not in found and found["approach"][0].startswith("Draw each part as its own layer")
    assert "multi-part-objects" in found["guidance"]


def test_declaring_an_object_points_to_its_build_block():
    p = Project(300, 300)
    p.apply({"type": "shape", "shape": "ellipse", "name": "blob", "width": 40, "height": 40})
    result = p.apply([{"type": "group", "name": "pet", "targets": ["blob"]}, {"type": "object", "target": "pet", "kind": "puppy"}])
    step = result["next_steps"][0]
    assert step["object"] == "pet" and step["kind"] == "dog" and "vixl_reference('objects', name='dog')" in step["how"]
    assert "next_steps" not in p.apply({"type": "object", "target": "pet", "notes": "a good dog"})


def test_cli_shows_the_build_block(tmp_path, monkeypatch, capsys):
    from vixl.cli import main

    monkeypatch.chdir(tmp_path)
    main(["objects", "show", "house"])
    shown = json.loads(capsys.readouterr().out)
    assert shown["build"]["example"] and shown["build"]["placements"][0]["part"]
