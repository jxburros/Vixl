"""Bulk edits by selector, proportional re-layout across sizes and lean results (issue #86)."""

import asyncio
import json

from mcp.shared.memory import create_connected_server_and_client_session
from PIL import Image
import pytest

from vixl import Project, VixlError
from vixl.interfaces import Session, mcp_server


def menu():
    p = Project(400, 300, "white")
    ops = [{"type": "text", "name": f"price-{i}", "text": f"${i}.50", "size": 20, "x": 10, "y": 10 + i * 30, "color": "black"}
           for i in range(1, 5)]
    ops += [{"type": "text", "name": "title", "text": "Menu", "size": 30, "x": 10, "y": 0, "color": "black"}]
    ops += [{"type": "shape", "shape": "ellipse", "name": f"dot-{i}", "width": 8, "height": 8, "x": 300, "y": 10 + i * 30,
             "fill": "red"} for i in range(1, 3)]
    p.apply(ops)
    return p


def edit(p, where, do, **extra):
    return p.apply([{"type": "edit-layers", "where": where, "do": do, **extra}], detail="compact")


def test_edit_layers_changes_every_match_and_reports_the_count():
    p = menu()
    result = edit(p, {"name": "price-*"}, {"type": "text-set", "color": "#ff0000", "size": 24})
    assert result["edit_layers"] == [{"matched": 4, "layers": ["price-1", "price-2", "price-3", "price-4"]}]
    assert all(p.layer(f"price-{i}")["color"] == "#ff0000" and p.layer(f"price-{i}")["size"] == 24 for i in range(1, 5))
    assert p.layer("title")["size"] == 30 and "warnings" not in result
    # Several operations per match, applied in order, layer by layer.
    edit(p, {"kind": "shape"}, [{"type": "opacity", "value": 0.5}, {"type": "move", "x": 5, "relative": True}])
    assert [p.layer(f"dot-{i}")["opacity"] for i in (1, 2)] == [0.5, 0.5]
    assert [p.layer(f"dot-{i}")["x"] for i in (1, 2)] == [305, 305]


def test_every_selector_key():
    p = menu()
    p.apply([{"type": "layer-intent", "target": "title", "tags": ["heading", "menu"]},
             {"type": "layer-intent", "target": "price-1", "tags": ["menu"]},
             {"type": "layer-intent", "target": "dot-1", "role": "decoration"},
             {"type": "role-set", "name": "dots", "targets": ["dot-1", "dot-2"]},
             {"type": "group", "name": "cluster", "targets": ["price-3", "price-4"]}])

    def names(where):
        return edit(p.clone(), where, {"type": "hide"}, dry_run=True)["edit_layers"][0]["layers"]

    assert names({"name": "PRICE-?"}) == ["price-1", "price-2", "price-3", "price-4"]  # Case-insensitive glob.
    assert names({"name": "price-[12]"}) == ["price-1", "price-2"]
    assert names({"name": ["title", "dot-*"]}) == ["title", "dot-1", "dot-2"]
    assert names({"name_regex": r"^price-[13]$"}) == ["price-1", "price-3"]
    assert names({"kind": "shape"}) == ["dot-1", "dot-2"] and names({"type": "group"}) == ["cluster"]
    assert names({"kind": ["shape", "group"], "shape": "ellipse"}) == ["dot-1", "dot-2"]
    assert names({"tag": "menu"}) == ["price-1", "title"]
    assert names({"tag": "heading"}) == ["title"]
    assert names({"role": "decoration"}) == ["dot-1"] and names({"role": "dots"}) == ["dot-1", "dot-2"]
    assert names({"group": "cluster"}) == ["price-3", "price-4"]
    assert names({"text_contains": "$1"}) == ["price-1"] and names({"text_regex": r"\$[24]\."}) == ["price-2", "price-4"]
    assert names({"kind": "text", "not": {"name": "price-*"}}) == ["title"]
    assert names({"id": ["dot-2"]}) == ["dot-2"]
    assert names({"name": "price-*", "visible": False}) == []
    # Several keys must all match.
    assert names({"kind": "text", "name": "price-*", "text_contains": "2.50"}) == ["price-2"]


def test_dry_run_counts_without_changing_and_expect_guards_the_selector():
    p = menu()
    before = json.dumps(p.state, sort_keys=True)
    counted = p.apply([{"type": "edit-layers", "where": {"name": "price-*"}, "do": {"type": "hide"}}], dry_run=True)
    assert counted["dry_run"] and counted["edit_layers"][0]["matched"] == 4
    assert json.dumps(p.state, sort_keys=True) == before
    only = p.apply([{"type": "edit-layers", "where": {"name": "price-*"}, "do": {"type": "hide"}, "dry_run": True}])
    assert only["edit_layers"][0]["dry_run"] is True and all(layer["visible"] for layer in p.state["layers"])
    with pytest.raises(VixlError) as error:
        edit(p, {"name": "price-*"}, {"type": "hide"}, expect=3)
    assert error.value.code == "selector_mismatch" and error.value.details["matched"] == 4
    assert json.dumps(p.state, sort_keys=True) == before
    assert edit(p, {"name": "price-*"}, {"type": "hide"}, expect=4)["edit_layers"][0]["matched"] == 4


def test_a_selector_matching_nothing_warns_instead_of_doing_nothing_silently():
    result = edit(menu(), {"name": "nothing-*"}, {"type": "hide"})
    assert result["edit_layers"][0]["matched"] == 0
    assert any("matched no layers" in warning for warning in result["warnings"])


def test_bad_selectors_and_operations_are_rejected_with_help():
    p = menu()
    cases = [
        ({"nme": "x"}, {"type": "hide"}, "Did you mean 'name' instead of 'nme'"),
        ({"kind": "txet"}, {"type": "hide"}, "Did you mean 'text'"),
        ({"name_regex": "("}, {"type": "hide"}, "not a valid regex"),
        ({"name": 5}, {"type": "hide"}, "where.name must be a string"),
        ({"group": "price-1"}, {"type": "hide"}, "is not a group"),
        ({"group": "nope"}, {"type": "hide"}, "does not exist"),
        ({}, {"type": "hide"}, "must be an object"),
        ({"name": "p*"}, {"type": "hid"}, "Unknown operation type 'hid'"),
        ({"name": "p*"}, {"type": "text", "text": "x"}, "creates layers"),
        ({"name": "p*"}, {"type": "hide", "target": "title"}, "leave out target"),
        ({"name": "p*"}, {"type": "text-set", "bogus": 1}, "Unknown field"),
        ({"name": "p*"}, {"type": "text-set", "target": "title", "size": 0}, "leave out target"),
    ]
    for where, do, message in cases:
        before = json.dumps(p.state, sort_keys=True)
        with pytest.raises(VixlError, match=message):
            edit(p, where, do)
        assert json.dumps(p.state, sort_keys=True) == before
    # An operation that cannot apply to a match fails the whole batch atomically.
    with pytest.raises(VixlError, match="not editable text"):
        edit(p, {"kind": ["text", "shape"]}, {"type": "text-set", "color": "red"})
    assert p.layer("price-1")["color"] == "black"


def test_edit_layers_reports_normalized_spellings_and_follows_service_rules():
    p = menu()
    result = edit(p, {"name": "price-1"}, {"type": "text-set", "colour": "red"})
    assert any("'colour' → 'color'" in note for note in result["normalized"])
    from vixl.interfaces import service_check

    with pytest.raises(VixlError, match="Filesystem fields"):
        p.apply([{"type": "edit-layers", "where": {"name": "price-1"}, "do": {"type": "text-set", "font": "/etc/x.ttf"}}],
                check=service_check)


def test_edit_layers_across_pages_and_restores_the_active_page():
    p = Project(200, 100, "white")
    p.apply([{"type": "page", "action": "add", "name": "one"},
             {"type": "text", "name": "t1", "text": "A", "x": 1, "y": 1},
             {"type": "page", "action": "add", "name": "two"},
             {"type": "text", "name": "t2", "text": "B", "x": 1, "y": 1}])
    active = p.state["page"]
    only_active = edit(p, {"kind": "text"}, {"type": "text-set", "color": "red"})
    assert only_active["edit_layers"][0]["layers"] == ["t2"]
    both = edit(p, {"kind": "text", "page": "all"}, {"type": "text-set", "color": "blue"})
    assert both["edit_layers"][0]["matched"] == 2 and both["edit_layers"][0]["pages"] == ["one", "two"]
    assert p.state["page"] == active
    first = edit(p, {"kind": "text", "page": 1}, {"type": "text-set", "color": "green"})
    assert first["edit_layers"][0]["layers"] == ["t1"] and p.state["page"] == active
    with pytest.raises(VixlError, match="no pages"):
        edit(menu(), {"kind": "text", "page": 1}, {"type": "hide"})


def test_edit_layers_works_through_mcp_and_names_the_matches(tmp_path):
    server = mcp_server(workspace=tmp_path)
    session = server.vixl_runtime.session
    session.create("menu.vixl", 400, 300)
    session.apply([{"type": "text", "name": f"price-{i}", "text": "$5", "size": 20, "x": 10, "y": 10 * i} for i in range(1, 4)])

    async def scenario():
        async with create_connected_server_and_client_session(server._mcp_server) as client:
            result = await client.call_tool("vixl_operations_apply", {"document": "menu.vixl", "operations": [
                {"type": "edit-layers", "where": {"name": "price-*"}, "do": {"type": "text-set", "color": "#c00"}}]})
            assert not result.isError, result.content
            return json.loads(result.content[0].text)

    reply = asyncio.run(scenario())
    assert reply["edit_layers"][0]["matched"] == 3 and len(reply["changes"]["layers"]) == 3
    assert all(layer["color"] == "#c00" for layer in session.inspect(document="menu.vixl")["layers"])


def poster():
    p = Project(1080, 1080, "white")
    p.apply([
        {"type": "solid", "name": "bg", "color": "#102030"},
        {"type": "text", "name": "eyebrow", "text": "NEW", "size": 40, "x": 60, "y": 60, "color": "white"},
        {"type": "text", "name": "headline", "text": "Big idea", "size": 120, "x": "center", "y": 380, "color": "white"},
        {"type": "shape", "shape": "rounded-rectangle", "name": "cta", "width": 300, "height": 90, "x": "center",
         "y": 800, "fill": "red", "radius": 20},
        {"type": "shape", "shape": "ellipse", "name": "logo", "width": 100, "height": 100, "x": 920, "y": 920, "fill": "blue"},
    ])
    return p


def rows(result):
    return {row["layer"]: row for row in result["adapt_layout"][0]["layers"]}


def test_adapt_layout_reflows_a_square_into_a_story():
    p = poster()
    result = p.apply([{"type": "adapt-layout", "size": "story"}], detail="brief")
    report = result["adapt_layout"][0]
    assert report["canvas"] == {"from": [1080, 1080], "to": [1080, 1920]} and report["scale"] == 1.0
    assert p.state["canvas"]["size"] == "story"
    moved = rows(result)
    assert moved["bg"]["to"] == [0, 0, 1080, 1920] and moved["bg"]["anchor"] == "stretch-x, stretch-y"
    assert "eyebrow" not in moved  # Top-left stays where it is.
    assert moved["logo"]["anchor"] == "right, bottom"
    logo = moved["logo"]["to"]
    assert logo[0] == 920 and logo[1] + logo[3] == 1920 - 60  # The 60 px bottom margin is kept.
    assert moved["cta"]["to"][0] == 390 and moved["cta"]["anchor"].startswith("center-x")  # Still centred.
    # The relative vertical place of centred content is kept, so it spreads into the taller canvas.
    assert moved["headline"]["to"][1] > moved["headline"]["from"][1] * 1.5


def test_adapt_layout_scales_sizes_and_text_with_the_canvas():
    p = poster()
    result = p.apply([{"type": "adapt-layout", "width": 540, "height": 540}], detail="brief")
    moved = rows(result)
    assert result["adapt_layout"][0]["scale"] == 0.5
    assert p.layer("headline")["size"] == 60 and moved["headline"]["font_size"] == 60
    assert (p.layer("cta")["width"], p.layer("cta")["height"]) == (150, 45)
    assert moved["logo"]["to"] == [460, 460, 50, 50]
    kept = poster()
    kept.apply({"type": "adapt-layout", "width": 540, "height": 540, "text": "keep"})
    assert kept.layer("headline")["size"] == 120
    fill = poster()
    assert fill.apply({"type": "adapt-layout", "width": 2160, "height": 1080, "scale": "fill"}, detail="brief")["adapt_layout"][0]["scale"] == 2.0
    assert poster().apply({"type": "adapt-layout", "width": 2160, "height": 1080, "scale": 3})["adapt_layout"][0]["scale"] == 3.0


def test_adapt_layout_anchors_where_and_constraints():
    p = poster()
    p.apply({"type": "constrain", "target": "logo", "constraints": {"right": "canvas.right-60", "bottom": "canvas.bottom-60"}})
    result = p.apply([{"type": "adapt-layout", "width": 2160, "height": 1080, "anchors": {"eyebrow": "bottom-left", "kind:text": "keep"},
                       "where": {"not": {"name": "cta"}}}], detail="brief")
    moved = rows(result)
    assert "eyebrow" not in moved  # kind:text keeps every text layer, so the eyebrow rule never gets to apply
    assert "cta" not in moved and p.layer("cta")["x"] == 390  # Not selected: untouched.
    logo = p.inspect("logo")["resolved_bounds"]
    # The constraints were kept and re-evaluated on the new canvas (offsets scaled by the 1.0 scale).
    assert logo[0] + logo[2] == 2160 - 60 and logo[1] + logo[3] == 1080 - 60
    assert p.layer("logo")["constraints"]["right"] == "canvas.right-60"
    p2 = poster()
    p2.apply({"type": "adapt-layout", "width": 1080, "height": 1920, "anchors": {"headline": "top", "role:decoration": "keep"}})
    assert p2.inspect("headline")["resolved_bounds"][1] == 380  # Top-anchored: the margin is kept.


def test_adapt_layout_covers_with_photos_and_leaves_pixel_layers_alone():
    p = Project(200, 100, "white")
    photo = Image.new("RGB", (200, 100), "blue")
    from io import BytesIO

    buffer = BytesIO()
    photo.save(buffer, format="PNG")
    from vixl.assets import add_encoded

    asset, _ = add_encoded(p, buffer.getvalue())
    p.apply([{"type": "add", "asset": asset, "name": "photo"}, {"type": "text", "name": "t", "text": "Hi", "size": 20, "x": 10, "y": 10}])
    result = p.apply([{"type": "adapt-layout", "width": 100, "height": 200}], detail="brief")
    photo_row = rows(result)["photo"]
    assert photo_row["anchor"] == "cover" and photo_row["to"][3] == 200 and photo_row["to"][2] == 400  # Not distorted.
    assert photo_row["to"][0] <= 0 and photo_row["to"][0] + photo_row["to"][2] >= 100  # It still covers the canvas.


def test_adapt_layout_stack_mode_and_option_conflicts_are_unchanged():
    p = Project(300, 300, "white")
    p.apply([{"type": "text", "name": "a", "text": "A", "size": 20, "x": 5, "y": 5},
             {"type": "text", "name": "b", "text": "B", "size": 20, "x": 5, "y": 100}])
    result = p.apply({"type": "adapt-layout", "targets": ["a", "b"], "width": 100, "height": 200, "margin": 5})
    assert p.state["canvas"]["width"] == 100 and "adapt_layout" not in result
    for bad, message in (
        ({"targets": ["a"], "width": 100, "height": 100, "scale": "fit"}, "belong to mode 'proportional'"),
        ({"size": "story", "targets": ["a"]}, "needs targets, width and height"),
        ({"size": "story", "margin": 4}, "belong to mode 'stack'"),
        ({"size": "story", "scale": "bogus"}, "scale is one of"),
        ({"size": "story", "anchors": {"a": "middle"}}, "unknown anchor 'middle'"),
        ({"size": "story", "width": 10, "height": 10}, "named size, or width and height"),
        ({"size": "nonesuch"}, "Unknown size"),
        ({}, "requires at least one of"),
    ):
        with pytest.raises(VixlError, match=message):
            p.apply({"type": "adapt-layout", **bad})
    paged = Project(100, 100)
    paged.apply([{"type": "page", "action": "add", "name": "one"}])
    with pytest.raises(VixlError, match="multi-page"):
        paged.apply({"type": "adapt-layout", "size": "story"})


def test_adapt_copies_one_call_several_sizes(tmp_path):
    from vixl.adapt import adapt_copies
    from vixl.mcp_tools import export_file

    session = Session(workspace=tmp_path)
    session.create("campaign/poster.vixl", 1080, 1080, "#102030")
    session.apply([{"type": "text", "name": "headline", "text": "Big idea", "size": 90, "x": "center", "y": 300, "color": "white"},
                   {"type": "shape", "shape": "ellipse", "name": "logo", "width": 80, "height": 80, "x": 960, "y": 960, "fill": "blue"}])
    before = (tmp_path / "campaign/poster.vixl").read_bytes()
    result = adapt_copies(session, export_file, ["story", "1200x628", {"width": 600, "height": 600, "name": "small"}],
                          directory="campaign/sizes", document="campaign/poster.vixl", formats=["png"], report="layers")
    assert [d["size"] for d in result["documents"]] == ["story", "1200x628", "small"]
    assert [d["canvas"] for d in result["documents"]] == [[1080, 1920], [1200, 628], [600, 600]]
    assert result["documents"][0]["path"] == "campaign/sizes/poster-story.vixl"
    assert all(d["layers"] and d["exports"][0]["format"] == "PNG" for d in result["documents"])
    assert Image.open(tmp_path / "campaign/sizes/poster-story.png").size == (1080, 1920)
    assert Image.open(tmp_path / "campaign/sizes/poster-small.png").size == (600, 600)
    assert Project.load(tmp_path / "campaign/sizes/poster-1200x628.vixl").state["canvas"]["width"] == 1200
    assert (tmp_path / "campaign/poster.vixl").read_bytes() == before  # The source is untouched.
    with pytest.raises(VixlError, match="already exists"):
        adapt_copies(session, export_file, ["story"], directory="campaign/sizes", document="campaign/poster.vixl")
    with pytest.raises(VixlError, match="same file name"):
        adapt_copies(session, export_file, ["story", "story"], directory="x", document="campaign/poster.vixl")
    with pytest.raises(VixlError, match="options accepts"):
        adapt_copies(session, export_file, ["story"], directory="x", options={"margin": 3}, document="campaign/poster.vixl")
    assert not (tmp_path / "x").exists()  # Validation failed before anything was written.


def test_adapt_layout_tool_over_mcp(tmp_path):
    server = mcp_server(workspace=tmp_path)
    session = server.vixl_runtime.session
    session.create("p.vixl", 400, 400)
    session.apply([{"type": "text", "name": "t", "text": "Hello", "size": 40, "x": 10, "y": 10, "color": "black"}])

    async def scenario():
        async with create_connected_server_and_client_session(server._mcp_server) as client:
            result = await client.call_tool("vixl_adapt_layout", {"document": "p.vixl", "sizes": ["story", "800x200"],
                                                                  "directory": "out", "request_id": "adapt-1"})
            assert not result.isError, result.content
            again = await client.call_tool("vixl_adapt_layout", {"document": "p.vixl", "sizes": ["story", "800x200"],
                                                                 "directory": "out", "request_id": "adapt-1"})
            return json.loads(result.content[0].text), json.loads(again.content[0].text)

    first, again = asyncio.run(scenario())
    assert first["count"] == 2 and again["replayed"] is True  # The retry did not run (it would have refused the existing files).
    assert (tmp_path / "out/p-story.vixl").is_file() and (tmp_path / "out/p-800x200.vixl").is_file()


def test_new_operations_are_advertised_and_described(tmp_path):
    async def scenario():
        server = mcp_server(workspace=tmp_path)
        async with create_connected_server_and_client_session(server._mcp_server) as client:
            result = await client.call_tool("vixl_operation_schema", {"types": ["edit-layers", "adapt-layout"]})
            return json.loads(result.content[0].text)

    schemas = asyncio.run(scenario())
    edit_props = schemas["edit-layers"]["properties"]
    assert set(edit_props) >= {"where", "do", "dry_run", "expect"} and "name_regex" in edit_props["where"]["description"]
    adapt = schemas["adapt-layout"]["properties"]
    assert set(adapt) >= {"size", "scale", "anchors", "where", "text", "targets", "margin"}
    assert "stretch-x" in adapt["anchors"]["description"] and schemas["adapt-layout"]["anyOf"]


def test_brief_is_leaner_than_compact_and_full_keeps_snapshots():
    p = Project(400, 300, "white")
    p.apply([{"type": "text", "name": "t", "text": "Hello", "size": 30, "x": 10, "y": 10}])
    ops = [{"type": "shape", "shape": "rectangle", "name": f"s{i}", "width": 5, "height": 5, "fill": "red", "x": i}
           for i in range(10)]
    brief = p.clone().apply(ops, detail="brief")
    compact = p.clone().apply(ops, detail="compact")
    assert len(json.dumps(brief)) < len(json.dumps(compact))
    added = next(iter(brief["changes"]["layers"].values()))
    assert added["added"] and added["name"] == "s0" and added["type"] == "shape" and len(added["bounds"]) == 4
    assert "fill" not in added
    moved = p.apply({"type": "move", "target": "t", "x": 40}, detail="brief")
    (entry,) = moved["changes"]["layers"].values()
    assert entry["changed"] == ["x"] and list(entry["bounds"][:2]) == [40, 10]
    removed = p.apply({"type": "remove", "target": "t"}, detail="brief")
    assert next(iter(removed["changes"]["layers"].values())) == {"removed": True, "name": "t"}
    with pytest.raises(VixlError, match="brief, compact or full"):
        p.apply({"type": "hide", "target": "s0"}, detail="tiny")


def test_mcp_apply_defaults_to_brief_and_text_add_too(tmp_path):
    server = mcp_server(workspace=tmp_path)

    async def scenario():
        async with create_connected_server_and_client_session(server._mcp_server) as client:
            async def call(tool, **args):
                result = await client.call_tool(tool, args)
                assert not result.isError, result.content
                return json.loads(result.content[0].text)

            await call("vixl_document_create", path="a.vixl", width=300, height=200)
            default = await call("vixl_operations_apply", operations=[
                {"type": "shape", "shape": "rectangle", "name": "box", "width": 50, "height": 50, "fill": "red"}])
            (layer,) = default["changes"]["layers"].values()
            assert set(layer) == {"added", "name", "type", "bounds"}
            full = await call("vixl_operations_apply", detail="compact", operations=[
                {"type": "move", "target": "box", "x": 9}])
            assert next(iter(full["changes"]["layers"].values()))["x"] == 9
            added = await call("vixl_operations_apply", operations=[{"type": "text", "text": "Hi", "name": "hi"}])
            assert next(iter(added["changes"]["layers"].values()))["name"] == "hi"

    asyncio.run(scenario())


def test_brief_results_keep_text_layers_to_the_documented_fields():
    p = Project(400, 300, "white")
    added = p.apply({"type": "text", "name": "t", "text": "Hello", "size": 30}, detail="brief")["changes"]["layers"]
    assert set(next(iter(added.values()))) == {"added", "name", "type", "bounds"}
    changed = p.apply({"type": "text-set", "target": "t", "text": "Hello there"}, detail="brief")["changes"]["layers"]
    assert set(next(iter(changed.values()))) <= {"changed", "bounds"}
