"""Operation/API papercuts: advisories on existing layers, pixel-art width, operations_path, docs names, fonts."""

import asyncio
import json

from mcp.shared.memory import create_connected_server_and_client_session
import pytest

from vixl import Project, VixlError
from vixl.interfaces import mcp_server


def warn(p, ops):
    return p.apply(ops, detail="compact").get("warnings", [])


def test_edit_of_existing_path_layer_does_not_warn_path_only_for_path():  # #229
    p = Project(200, 200, "white")
    p.apply([{"type": "shape", "shape": "path", "name": "p", "path": "M0 0 L10 10", "width": 50, "height": 50,
              "stroke": "red"}])
    assert not [w for w in warn(p, [{"type": "shape", "target": "p", "path": "M0 0 L20 20"}]) if "path" in w]
    p.apply([{"type": "shape", "shape": "rectangle", "name": "r", "width": 20, "height": 20, "fill": "red"}])
    assert any("inner_radius" in w for w in warn(p, [{"type": "shape", "target": "r", "inner_radius": 0.3}]))
    p.apply([{"type": "shape", "shape": "arc", "name": "a", "width": 40, "height": 40, "fill": "red"}])
    assert not warn(p, [{"type": "shape", "target": "a", "inner_radius": 0.3}])
    assert not warn(p, [{"type": "shape", "shape": "donut", "name": "d", "width": 40, "height": 40, "fill": "red",
                         "inner_radius": 0.5}])


def test_pixel_art_accepts_matching_width_and_height_with_rows():  # #227
    p = Project(64, 64, "white")
    rows = ["#..#", ".##."]
    p.apply([{"type": "pixel-art", "name": "ok", "rows": rows, "width": 4, "height": 2}])
    with pytest.raises(VixlError) as err:
        p.apply([{"type": "pixel-art", "name": "bad", "rows": rows, "width": 8}])
    assert "width must be 4" in str(err.value)


def test_role_font_without_typography_warns_about_the_proofing_fallback():  # #248
    p = Project(200, 100, "white")
    first = warn(p, [{"type": "text", "name": "t", "text": "Hi", "font": "heading"}])
    assert any("proofing" in w and "'heading'" in w for w in first)
    assert not warn(p, [{"type": "text", "name": "u", "text": "Hi"}])  # no font asked for: nothing to say


def test_document_create_applies_a_font_pairing(tmp_path, monkeypatch):  # #248
    import vixl.typefaces as typefaces

    def fake_pair(project, pairing=None, **kwargs):
        project.state["typography"] = {"heading": "DejaVuSans.ttf", "body": "DejaVuSans.ttf", "pairing": pairing}
        return {"pairing": pairing}

    monkeypatch.setattr(typefaces, "pair_fonts", fake_pair)
    server = mcp_server(workspace=tmp_path)

    async def scenario():
        async with create_connected_server_and_client_session(server._mcp_server) as client:
            made = await client.call_tool("vixl_document_create", {
                "path": "a.vixl", "width": 64, "height": 64, "font_pairing": "editorial"})
            return json.loads(made.content[0].text)

    assert asyncio.run(scenario())["typography"] == {"pairing": "editorial"}
    assert Project.load(tmp_path / "a.vixl").state["typography"]["pairing"] == "editorial"


def test_font_fallbacks_rejects_a_target():  # #206
    p = Project(100, 100, "white")
    p.apply([{"type": "text", "name": "t", "text": "Hi"}])
    with pytest.raises(VixlError) as err:
        p.apply([{"type": "font-fallbacks", "fonts": ["DejaVuSans.ttf"], "target": "t"}])
    assert "document-wide" in str(err.value)
    p.apply([{"type": "font-fallbacks", "fonts": ["DejaVuSans.ttf"]}])


def test_operations_path_over_mcp_json_and_jsonl(tmp_path):  # #184
    server = mcp_server(workspace=tmp_path)
    (tmp_path / "ops.json").write_text(json.dumps([{"type": "solid", "name": "bg", "color": "red"}]))
    (tmp_path / "ops.jsonl").write_text(
        '{"type": "shape", "shape": "rectangle", "name": "a", "width": 10, "height": 10, "fill": "blue"}\n\n'
        '{"type": "shape", "shape": "rectangle", "name": "b", "width": 10, "height": 10, "fill": "blue"}\n')
    (tmp_path / "bad.jsonl").write_text('{"type": "solid", "name": "x"}\n{oops\n')

    async def scenario():
        async with create_connected_server_and_client_session(server._mcp_server) as client:
            async def call(**args):
                result = await client.call_tool("vixl_operations_apply", args)
                text = "".join(c.text for c in result.content)
                return (True, text) if result.isError else json.loads(text)

            await client.call_tool("vixl_document_create", {"path": "a.vixl", "width": 64, "height": 64})
            assert (await call(operations_path="ops.json"))["success"]
            assert (await call(operations_path="ops.jsonl"))["success"]
            failed, text = await call(operations_path="bad.jsonl")
            assert failed and "line 2" in text
            failed, text = await call(operations_path="../outside.json")
            assert failed
            failed, text = await call()
            assert failed and "operations_path" in text
            layers = (await client.call_tool("vixl_document_inspect", {})).content[0].text
            assert '"a"' in layers and '"b"' in layers

    asyncio.run(scenario())
