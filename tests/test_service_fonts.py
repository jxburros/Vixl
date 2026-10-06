"""Service (MCP/REST) operations accept registered font names and roles, never font files."""

import asyncio
import hashlib
import json
from pathlib import Path

import pytest

import vixl
from vixl import Project, VixlError
from vixl.interfaces import Session, mcp_server

DEJAVU = Path(vixl.__file__).parent / "data" / "DejaVuSans.ttf"


def call(server, name, arguments):
    async def run():
        try:
            result = await server.call_tool(name, arguments)
        except Exception as exc:  # FastMCP surfaces tool failures as ToolError
            return True, str(exc)
        content = result[0] if isinstance(result, tuple) else result
        return False, "".join(getattr(item, "text", "") for item in content)

    return asyncio.run(run())


def error_payload(text):
    return json.loads(text[text.index("{"):])


@pytest.fixture
def session(tmp_path):
    session = Session(workspace=tmp_path)
    session.create("doc.vixl", 400, 200)
    data = DEJAVU.read_bytes()
    with session.project(write=True) as project:
        asset = f"fonts/{hashlib.sha256(data).hexdigest()}.ttf"
        project.assets[asset] = data
        project.apply([{"type": "font-register", "name": "serif-400", "asset": asset, "role": "heading"}])
    session.asset = asset
    return session


def test_batches_accept_registered_fonts_and_roles(session):
    result = session.apply([
        {"type": "text", "name": "a", "text": "A", "font": "serif-400"},
        {"type": "text", "name": "b", "text": "B", "font": "heading"},
        {"type": "text", "name": "c", "text": "C", "font_family": "serif-400"},  # aliases are normalized first
        {"type": "text-set", "target": "a", "font": "serif-400", "text": "AA"},
        {"type": "rich-text", "name": "r", "spans": [{"text": "x", "font": "serif-400"}, {"text": " y"}]},
        {"type": "rich-text", "name": "m", "markdown": "[x]{font=heading} y"},
        {"type": "text-style", "target": "m", "match": "y", "font": "serif-400"},
    ])
    assert result["success"]
    with session.project() as project:
        assert project.layer("a")["font"] == session.asset and project.layer("b")["font_role"] == "heading"
        assert project.layer("c")["font"] == session.asset
        assert project.layer("r")["rich"]["spans"][0]["font"] == session.asset
        assert project.layer("m")["rich"]["spans"][0]["font"] == session.asset


def test_font_registered_earlier_in_the_batch_is_accepted(session):
    session.apply([
        {"type": "font-register", "name": "later", "asset": session.asset},
        {"type": "text", "name": "t", "text": "T", "font": "later"},
    ])
    with session.project() as project:
        assert project.layer("t")["font"] == session.asset


def test_unregistered_font_names_point_to_the_install_path(session):
    with pytest.raises(VixlError) as caught:
        session.apply([{"type": "solid", "name": "bg"}, {"type": "text", "text": "x", "font": "serif-4000"}])
    error = caught.value.as_dict()
    assert error["error"] == "missing_font" and error["field"] == "font" and error["operation_index"] == 1
    assert error["suggestions"] == ["serif-400"] and "vixl_font_install" in error["message"]
    assert "heading" in error["allowed"] and "serif-400" in error["allowed"]
    with session.project() as project:
        assert project.state["layers"] == []  # nothing from the failed batch was kept


def test_font_files_are_still_refused_everywhere_a_font_can_be_named(session, tmp_path):
    attempts = [
        {"type": "text", "text": "x", "font": "/etc/passwd"},
        {"type": "text", "text": "x", "font": "../outside.ttf"},
        {"type": "text", "text": "x", "font_family": str(DEJAVU)},
        {"type": "rich-text", "name": "r", "spans": [{"text": "x", "font": str(DEJAVU)}]},
        {"type": "rich-text", "name": "r", "markdown": f"[x]{{font={DEJAVU}}}"},
        {"type": "layout-apply", "name": "hero-statement", "display_font": "/etc/passwd"},
    ]
    for operation in attempts:
        with pytest.raises(VixlError) as caught:
            session.apply([operation])
        assert caught.value.code == "forbidden", operation
        assert "vixl_font_install" in str(caught.value)
    with pytest.raises(VixlError) as caught:
        session.apply([{"type": "add", "path": "outside.png"}])  # path/linked stay refused
    assert caught.value.code == "forbidden"


def test_mcp_batch_with_font_schema_and_errors(tmp_path):
    server = mcp_server(workspace=tmp_path)
    call(server, "vixl_document_create", {"path": "a.vixl", "width": 200, "height": 100})
    data = DEJAVU.read_bytes()
    asset = f"fonts/{hashlib.sha256(data).hexdigest()}.ttf"
    project = Project.load(tmp_path / "a.vixl")
    project.assets[asset] = data
    project.apply([{"type": "font-register", "name": "body-font", "asset": asset}])
    project.save(tmp_path / "a.vixl")
    failed, text = call(server, "vixl_operations_apply", {"operations": [
        {"type": "text", "name": "t", "text": "hello", "font": "body-font"},
        {"type": "text-set", "target": "t", "font": "body-font", "size": 30}]})
    assert not failed and json.loads(text)["success"]
    failed, text = call(server, "vixl_operations_apply", {"operations": [{"type": "text", "text": "a", "font": "/etc/passwd"}]})
    assert failed and error_payload(text)["error"] == "forbidden" and "vixl_font_install" in error_payload(text)["message"]
    failed, text = call(server, "vixl_operation_schema", {"types": ["text", "text-set"]})
    schema = json.loads(text)
    for kind in ("text", "text-set"):
        assert "Registered font name" in schema[kind]["properties"]["font"]["description"]
        assert "path" not in schema[kind]["properties"] and "linked" not in schema[kind]["properties"]

    async def tools():
        return {t.name: t for t in await server.list_tools()}

    inline = asyncio.run(tools())["vixl_operations_apply"]
    assert '"font"' in json.dumps(inline.inputSchema) and "registered font name" in inline.description
