"""The variations workflow (#649): seeded rolls on copies of the open document, a contact sheet and a seed per tile."""

import asyncio
import json

import pytest
from PIL import Image

from vixl import Project, workflows
from vixl.errors import VixlError
from vixl.interfaces import Session, mcp_server
from vixl.typefaces import roll_document

SLOTS = {"title": "Summer Night Market", "subtitle": "Food, music and late shopping", "label": "June 21"}


def fake_pair(project, pairing=None, **kwargs):
    """Skip the font download: the proofing font stands in for the pairing."""
    project.state["typography"] = {"body": "DejaVuSans.ttf", "heading": "DejaVuSans.ttf"}
    return {"origin": "cache", "heading": {"name": "DejaVuSans.ttf"}, "body": {"name": "DejaVuSans.ttf"}}


@pytest.fixture
def space(tmp_path, monkeypatch):
    monkeypatch.setattr("vixl.typefaces.pair_fonts", fake_pair)
    post = Project.sized("instagram-post")
    roll_document(post, workspace=tmp_path, seed=5, purpose="social", variety="medium", apply=True, slots=SLOTS)
    post.save(tmp_path / "post.vixl")
    Project.sized("instagram-post").save(tmp_path / "empty.vixl")
    return tmp_path


def run(space, request, document="post.vixl"):
    return workflows.dispatch(Session(workspace=space), "variations", request, document)


def snapshot(space, name="post.vixl"):
    return json.dumps(Project.load(space / name).state, sort_keys=True, default=str)


def test_variations_is_a_registered_workflow_with_typed_fields():
    description = workflows.describe()["actions"]["variations"]
    assert description["required"] == ["output"] and description["summary"]
    assert set(description["fields"]) == {"count", "seeds", "locks", "slots", "purpose", "mood", "variety", "output",
                                          "overwrite", "width", "columns"}
    for name, schema in description["properties"].items():
        assert schema.get("type") and schema.get("description"), name


def test_each_seed_is_a_tile_and_the_document_is_unchanged(space):
    before, file = snapshot(space), (space / "post.vixl").read_bytes()
    result = run(space, {"seeds": [11, 12, 13], "output": "options.png", "width": 240})
    assert result["unchanged"] is True and [tile["seed"] for tile in result["tiles"]] == [11, 12, 13]
    assert [tile["tile"] for tile in result["tiles"]] == [1, 2, 3]
    sheet = Image.open(space / "options.png")
    assert list(sheet.size) == result["size"] and sheet.width == 3 * 240 + 4 * 16
    # Each roll chose its own direction, and says what it chose and what its findings are.
    assert len({(tile["layout"], tile["palette"]) for tile in result["tiles"]}) > 1
    for tile in result["tiles"]:
        assert set(tile["findings"]) == {"fix", "review"} and tile["pairing"]
        assert tile["apply"] == {"type": "roll", "seed": tile["seed"], "replace": True, "slots": SLOTS}
    # The tiles differ from each other.
    tiles = [sheet.convert("RGB").crop((16 + i * 256, 40, 16 + i * 256 + 240, 280)).tobytes() for i in range(3)]
    assert len(set(tiles)) == 3
    assert snapshot(space) == before and (space / "post.vixl").read_bytes() == file


def test_count_draws_fresh_seeds_and_the_same_seeds_give_the_same_sheet(space):
    result = run(space, {"count": 2, "output": "two.png", "width": 160, "columns": 1})
    seeds = [tile["seed"] for tile in result["tiles"]]
    assert len(seeds) == 2 and seeds[0] != seeds[1]
    assert Image.open(space / "two.png").width == 160 + 2 * 16
    again = run(space, {"seeds": seeds, "output": "again.png", "width": 160, "columns": 1})
    assert [t["layout"] for t in again["tiles"]] == [t["layout"] for t in result["tiles"]]
    assert (space / "two.png").read_bytes() == (space / "again.png").read_bytes()


def test_locks_keep_a_choice_across_the_tiles(space):
    result = run(space, {"seeds": [3, 4], "output": "locked.png", "width": 160,
                         "locks": {"palette": "ocean"}})
    assert {tile["palette"] for tile in result["tiles"]} == {"ocean"}
    assert all(tile["apply"]["locks"] == {"palette": "ocean"} for tile in result["tiles"])


def test_a_tile_is_reapplied_with_its_seed(space):
    server = mcp_server(workspace=space)

    def call(name, arguments):
        content = asyncio.run(server.call_tool(name, arguments))
        content = content[0] if isinstance(content, tuple) else content
        return content

    out = call("vixl_apply", {"workflow": "variations", "document": "post.vixl",
                              "request": {"seeds": [21, 22], "output": "mcp.png", "width": 160}})
    assert len(out) == 2 and out[1].type == "image"  # the result and the contact sheet
    tiles = json.loads(out[0].text)["tiles"]
    choice = tiles[1]
    expect = Project.load(space / "post.vixl")
    roll_document(expect, workspace=space, seed=22, purpose="social", apply=True, slots=SLOTS, replace=True)
    call("vixl_apply", {"document": "post.vixl", "operations": [choice["apply"]]})
    kept = Project.load(space / "post.vixl")
    assert kept.state["layout"]["name"] == choice["layout"] == expect.state["layout"]["name"]
    boxes = [(x["name"], x["type"], x.get("x"), x.get("y"), x.get("size"), x.get("fill") or x.get("color"))
             for x in kept.state["layers"]]
    assert boxes == [(x["name"], x["type"], x.get("x"), x.get("y"), x.get("size"), x.get("fill") or x.get("color"))
                     for x in expect.state["layers"]]
    # Rolling again replaced the layout instead of stacking a second one on it.
    assert len([x for x in kept.state["layers"] if x["name"] == "headline"]) == 1


def test_bad_requests_are_refused_before_anything_is_written(space):
    for request, field in (
            ({"output": "x.txt", "seeds": [1, 2]}, "output"),
            ({"output": "x.png", "count": 1}, "count"),
            ({"output": "x.png", "count": 5}, "count"),
            ({"output": "x.png", "seeds": [1, 1]}, "seeds"),
            ({"output": "x.png", "seeds": [1, 2, 3], "count": 2}, "count"),
            ({"output": "x.png", "seeds": [1, 2], "width": 10}, "width"),
            ({"output": "x.png", "seeds": [1, 2], "columns": 9}, "columns")):
        with pytest.raises(VixlError) as caught:
            run(space, request)
        assert caught.value.details.get("field") == field, request
    assert not (space / "x.png").exists()
    (space / "taken.png").write_bytes(b"keep")
    with pytest.raises(VixlError, match="already exists"):
        run(space, {"output": "taken.png", "seeds": [1, 2], "width": 128})
    assert (space / "taken.png").read_bytes() == b"keep"
    run(space, {"output": "taken.png", "seeds": [1, 2], "width": 128, "overwrite": True})
    assert (space / "taken.png").read_bytes()[:4] == b"\x89PNG"


def test_a_document_without_a_layout_needs_copy(space):
    with pytest.raises(VixlError) as caught:
        run(space, {"output": "y.png", "seeds": [1, 2], "width": 128}, document="empty.vixl")
    assert caught.value.details["field"] == "slots"
    result = run(space, {"output": "y.png", "seeds": [1, 2], "width": 128, "slots": {"title": "Hello"}},
                 document="empty.vixl")
    assert len(result["tiles"]) == 2 and not Project.load(space / "empty.vixl").state["layers"]
