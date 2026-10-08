"""What an apply call tells the agent: warnings, schema hints, directories and batch export (#88)."""

import asyncio
import json

from mcp.shared.memory import create_connected_server_and_client_session
from PIL import Image
import pytest

from vixl import Project, VixlError
from vixl.interfaces import Session, mcp_server


def document():
    p = Project(400, 300, "white")
    p.apply([{"type": "text", "name": "t", "text": "Hello", "size": 30, "x": 10, "y": 10}])
    return p


def warnings(ops, p=None):
    return (p or document()).apply(ops, detail="compact").get("warnings", [])


def test_text_off_the_canvas_warns_and_a_small_bleed_does_not():
    assert any("entirely outside the canvas" in w for w in warnings(
        [{"type": "text", "name": "far", "text": "far away", "x": 900, "y": 10}]))
    spill = warnings([{"type": "text", "name": "spill", "text": "A headline that is too wide", "size": 60, "x": 100, "y": 10}])
    assert len(spill) == 1 and "cut off by the canvas edge" in spill[0] and "spill" in spill[0]
    # Artwork bleeding a few pixels is normal; a layer that is mostly outside is not.
    assert not warnings([{"type": "shape", "shape": "rectangle", "name": "bleed", "width": 420, "height": 320,
                          "x": -10, "y": -10, "fill": "red"}])
    assert warnings([{"type": "shape", "shape": "rectangle", "name": "mostly", "width": 200, "height": 100,
                      "x": 350, "y": 10, "fill": "red"}])


def test_only_this_calls_layers_are_checked():
    p = document()
    p.apply([{"type": "text", "name": "far", "text": "far away", "x": 900, "y": 10}])
    # The earlier problem is not repeated while other layers are edited.
    assert warnings([{"type": "move", "target": "t", "x": 20}], p) == []
    assert warnings([{"type": "move", "target": "far", "x": 901}], p)


def test_text_that_does_not_fit_its_box_or_group_warns():
    p = document()
    p.apply({"type": "text-set", "target": "t", "text": "Hello wonderful world"})
    result = warnings([{"type": "text-layout", "target": "t", "width": 100, "height": 30}], p)
    assert len(result) == 1 and "does not fit its 100×30 text box" in result[0]
    p.apply([{"type": "text-layout", "target": "t", "width": 380, "height": 60}])
    p.apply([{"type": "group", "name": "card", "targets": ["t"]}, {"type": "resize", "target": "card", "width": 200, "height": 60}])
    p.apply([{"type": "move", "target": "t", "x": 0, "y": 0}])
    moved = warnings([{"type": "move", "target": "t", "x": 150, "y": 0}], p)
    assert any("extends outside its group 'card'" in w for w in moved), moved


def test_text_layout_with_only_a_width_grows_to_fit_the_wrapped_lines():
    p = Project(400, 300, "white")
    p.apply({"type": "text", "name": "t", "text": "a long paragraph that should wrap inside a narrow box", "size": 20})
    one_line = p.layer("t")["height"]
    result = p.apply({"type": "text-layout", "target": "t", "width": 200}, detail="compact")
    tall = p.layer("t")["height"]
    assert p.layer("t")["width"] == 200 and tall > 2 * one_line
    assert not any("does not fit" in w for w in result.get("warnings", []))
    # A wider box shrinks back to the lines it needs; an explicit height is kept and only grows.
    p.apply({"type": "text-layout", "target": "t", "width": 380})
    assert p.layer("t")["height"] < tall
    p.apply({"type": "text-layout", "target": "t", "width": 380, "height": 200})
    p.apply({"type": "text-layout", "target": "t", "width": 390})
    assert p.layer("t")["height"] == 200


def test_fields_that_change_nothing_are_reported():
    found = warnings([
        {"type": "shape", "shape": "rectangle", "name": "r", "width": 20, "height": 20, "radius": 5, "stroke_width": 2},
        {"type": "gradient", "name": "g", "stops": [{"offset": 0, "color": "red"}, {"offset": 1, "color": "blue"}],
         "start": "red", "angle": 20},
        {"type": "align", "target": "t", "alignment": "center", "margin": 4},
    ])
    text = "\n".join(found)
    assert "operations[0]: shape 'r': radius only rounds" in text and "stroke_width draws nothing" in text
    assert "operations[1]: gradient 'g': start/end are ignored" in text and "angle only applies" in text
    assert "operations[2]: align: margin has no effect" in text
    # Used correctly, nothing is said.
    assert not warnings([
        {"type": "shape", "shape": "rounded-rectangle", "name": "ok", "width": 20, "height": 20, "radius": 5,
         "stroke": "black", "stroke_width": 2},
        {"type": "gradient", "name": "g2", "direction": "angled", "angle": 30},
    ])
    p = document()
    p.apply([{"type": "effect", "target": "t", "name": "blur", "amount": 2}, {"type": "preset-save", "target": "t", "name": "soft"}])
    # An override that matches nothing is invalid input, so it fails the batch rather than warning.
    with pytest.raises(VixlError, match="match no effect in preset 'soft'") as error:
        p.apply([{"type": "preset-apply", "target": "t", "name": "soft", "overrides": {"sharpen": 3}}])
    assert error.value.details["field"] == "overrides" and error.value.details["allowed"] == ["blur"]


def test_validation_errors_point_at_the_schema_and_name_the_fields():
    p = document()
    with pytest.raises(VixlError) as error:
        p.apply({"type": "shape", "shape": "rectangle", "gradient": ["red", "blue"]})
    err = error.value
    assert "vixl_operation_schema(types=['shape'])" in str(err) and "Allowed:" in str(err)
    assert err.details["schema"] == "vixl_operation_schema(types=['shape'])" and "fill" in err.details["fields"]
    with pytest.raises(VixlError) as error:
        p.apply({"type": "opacity", "target": "t", "value": "0.5"})
    assert "(see vixl_operation_schema(types=['opacity']))" in str(error.value)
    assert "type" in error.value.details["expected"]
    with pytest.raises(VixlError) as error:
        p.apply({"type": "mvoe", "x": 1})
    assert "move" in error.value.details["suggestions"] and "vixl_operation_schema" in str(error.value)
    with pytest.raises(VixlError) as error:
        p.apply({"type": "move", "target": "t"})
    assert "at least one of: x, y" in str(error.value) and "vixl_operation_schema(types=['move'])" in str(error.value)
    with pytest.raises(VixlError, match="exactly"):
        p.apply({"type": "gradient", "name": "g", "stops": [{"pos": 0, "color": "red"}, {"pos": 1, "color": "blue"}]})


def test_document_create_makes_missing_directories(tmp_path):
    session = Session(workspace=tmp_path)
    session.create("deep/er/still/a.vixl", 20, 20)
    assert (tmp_path / "deep/er/still/a.vixl").is_file()
    (tmp_path / "file.txt").write_text("x")
    with pytest.raises(VixlError, match="not a directory"):
        session.create("file.txt/b.vixl", 20, 20)
    with pytest.raises(VixlError, match="outside the workspace"):
        session.create("../escape/c.vixl", 20, 20)
    assert not (tmp_path.parent / "escape").exists()
    with pytest.raises(VixlError):  # A bad request must not leave empty directories behind.
        session.create("nope/never/d.vixl", 20)
    assert not (tmp_path / "nope").exists()


def batch_session(tmp_path):
    session = Session(workspace=tmp_path)
    session.create("poster.vixl", 80, 40, "white")
    session.apply([{"type": "text", "name": "t", "text": "Hi", "size": 12, "x": 4, "y": 4, "color": "black"}])
    session.create("other.vixl", 30, 30, "red")
    return session


def batch(session, targets, **options):
    from vixl.export_batch import export_batch
    from vixl.mcp_tools import export_file

    return export_batch(session, export_file, targets, options.pop("defaults", None), options.pop("overwrite", False),
                        options.pop("stop_on_error", False), options.pop("document", None))


def test_batch_exports_sizes_formats_and_documents_in_one_call(tmp_path):
    session = batch_session(tmp_path)
    result = batch(session, [
        {"path": "out/poster.png"},
        {"path": "out/poster@2x.png", "scale": 2},
        {"path": "out/poster.jpg", "quality": 70},
        {"path": "out/other.png", "document": "other.vixl"},
    ], document="poster.vixl", defaults={"background": "white"})
    assert result["count"] == 4 and result["written"] == 4 and result["failed"] == 0
    assert result["documents"] == ["poster.vixl", "other.vixl"]
    assert [r["path"] for r in result["results"]] == ["out/poster.png", "out/poster@2x.png", "out/poster.jpg", "out/other.png"]
    assert [r["document"] for r in result["results"]] == ["poster.vixl"] * 3 + ["other.vixl"]
    assert Image.open(tmp_path / "out/poster.png").size == (80, 40)
    assert Image.open(tmp_path / "out/poster@2x.png").size == (160, 80)
    assert Image.open(tmp_path / "out/other.png").size == (30, 30)
    assert Image.open(tmp_path / "out/poster.jpg").format == "JPEG"


def test_batch_validates_everything_before_writing_anything(tmp_path):
    session = batch_session(tmp_path)
    with pytest.raises(VixlError) as error:
        batch(session, [{"path": "a.png"}, {"path": "b.png", "qualty": 80}], document="poster.vixl")
    assert "targets[1]" in str(error.value) and "did you mean 'quality'" in str(error.value)
    assert not (tmp_path / "a.png").exists()
    with pytest.raises(VixlError, match="both write"):
        batch(session, [{"path": "a.png"}, {"path": "a.png", "scale": 2}], document="poster.vixl")
    with pytest.raises(VixlError, match="targets\\[0\\].scale"):
        batch(session, [{"path": "a.png", "scale": 99}], document="poster.vixl")
    with pytest.raises(VixlError, match="PNG, JPEG"):
        batch(session, [{"path": "a.png"}, {"path": "b.exe"}], document="poster.vixl")
    (tmp_path / "taken.png").write_bytes(b"x")
    with pytest.raises(VixlError, match="already exists"):
        batch(session, [{"path": "a.png"}, {"path": "taken.png"}], document="poster.vixl")
    assert not (tmp_path / "a.png").exists()
    assert batch(session, [{"path": "taken.png"}], document="poster.vixl", overwrite=True)["written"] == 1
    assert (tmp_path / "taken.png").stat().st_size > 1


def test_batch_reports_a_failing_target_and_can_stop(tmp_path):
    session = batch_session(tmp_path)
    targets = [{"path": "a.png"}, {"path": "b.png", "document": "missing.vixl"}, {"path": "c.png"}]
    result = batch(session, targets, document="poster.vixl")
    assert result["written"] == 2 and result["failed"] == 1
    assert result["results"][1]["error"]["error"] == "not_found"
    assert (tmp_path / "a.png").is_file() and (tmp_path / "c.png").is_file()
    stopped = batch(session, [{"path": "d.png", "document": "missing.vixl"}, {"path": "e.png"}],
                    document="poster.vixl", stop_on_error=True)
    assert stopped["stopped_early"] and not (tmp_path / "e.png").exists()


def test_batch_tool_over_mcp_and_require_document(tmp_path):
    server = mcp_server(workspace=tmp_path, require_document=True)
    batch_session(tmp_path)

    async def scenario():
        async with create_connected_server_and_client_session(server._mcp_server) as client:
            async def call(**args):
                result = await client.call_tool("vixl_export_batch", args)
                return result.isError, "".join(c.text for c in result.content)

            failed, text = await call(targets=[{"path": "x.png"}])
            assert failed and "document_required" in text
            failed, text = await call(targets=[{"path": "x.png", "document": "poster.vixl"}, {"path": "y/z.webp", "scale": 0.5, "document": "other.vixl"}])
            assert not failed and json.loads(text)["written"] == 2

    asyncio.run(scenario())
    assert Image.open(tmp_path / "y/z.webp").size == (15, 15)


def test_misspelt_tool_arguments_are_reported_instead_of_silently_dropped(tmp_path):
    server = mcp_server(workspace=tmp_path)

    async def scenario():
        async with create_connected_server_and_client_session(server._mcp_server) as client:
            await client.call_tool("vixl_document_create", {"path": "a.vixl", "width": 64, "height": 64})
            result = await client.call_tool("vixl_operations_apply", {
                "operations": [{"type": "solid", "name": "bg"}], "detial": "full", "dryrun": True})
            applied = json.loads(result.content[0].text)
            preview = await client.call_tool("vixl_render_preview", {"regoin": [0, 0, 8, 8], "max_width": 32})
            fine = await client.call_tool("vixl_document_inspect", {})
            return applied, preview, json.loads(fine.content[0].text)

    applied, preview, fine = asyncio.run(scenario())
    (warning,) = applied["warnings"]
    assert "'detial' (did you mean 'detail'?)" in warning and "'dryrun' (did you mean 'dry_run'?)" in warning
    assert applied["success"] and applied["dry_run"] is False  # The misspelt option really was not applied.
    assert preview.content[0].type == "image"
    assert "'regoin' (did you mean 'region'?)" in json.loads(preview.content[-1].text)["warnings"][0]
    assert "warnings" not in fine


def test_create_and_export_make_missing_directories_over_mcp(tmp_path):
    server = mcp_server(workspace=tmp_path)

    async def scenario():
        async with create_connected_server_and_client_session(server._mcp_server) as client:
            async def call(tool, **args):
                result = await client.call_tool(tool, args)
                text = "".join(item.text for item in result.content)
                return (True, text) if result.isError else json.loads(text)

            made = await call("vixl_document_create", path="clients/acme/2026/poster.vixl", width=40, height=40)
            assert made["path"] == "clients/acme/2026/poster.vixl"
            out = await call("vixl_export_file", path="clients/acme/out/final/poster.png")
            assert out["path"] == "clients/acme/out/final/poster.png"
            clash = await call("vixl_document_create", path="clients/acme/2026/poster.vixl/x.vixl", width=4, height=4)
            assert clash[0]
            escape = await call("vixl_document_create", path="../outside/a.vixl", width=4, height=4)
            assert escape[0] and "outside the workspace" in escape[1]

    asyncio.run(scenario())
    assert (tmp_path / "clients/acme/out/final/poster.png").is_file() and not (tmp_path.parent / "outside").exists()
