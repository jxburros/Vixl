"""Calls that miss: an unknown tool names the closest ones (or the server that serves it), and an unknown or
badly typed option returns the chosen action's exact schema."""

import asyncio
import json

import pytest
from mcp.server.fastmcp.exceptions import ToolError

from vixl.interfaces import Session
from vixl.mcp_tools import build_server


def call_error(server, name, **arguments):
    with pytest.raises(ToolError) as raised:
        asyncio.run(server.call_tool(name, arguments))
    return str(raised.value)


def payload(message):
    return json.loads(message[message.index("{"):])


def test_tool_from_the_other_server_names_the_mode_that_serves_it(tmp_path):
    message = call_error(build_server(Session(workspace=tmp_path)), "vixl_ai_generate")
    assert "--tools ai" in message
    message = call_error(build_server(Session(workspace=tmp_path), tools="ai"), "vixl_apply")
    assert "--tools default" in message


def test_misspelled_tool_suggests_close_names_and_old_names_are_simply_unknown(tmp_path):
    server = build_server(Session(workspace=tmp_path))
    assert "vixl_apply" in call_error(server, "vixl_aply")
    message = call_error(server, "vixl_text_add")
    assert message.startswith("Unknown tool: vixl_text_add") and "removed" not in message


def test_unknown_option_lists_the_action_schema(tmp_path):
    server = build_server(Session(workspace=tmp_path))
    asyncio.run(server.call_tool("vixl_document", {"action": "create", "path": "a.vixl", "width": 20, "height": 20}))
    error = payload(call_error(server, "vixl_render", max_widht=10))
    assert error["error"] == "invalid_arguments" and "max_width" in error["suggestions"]
    assert "max_width" in error["schema"]["properties"]
    error = payload(call_error(server, "vixl_export", path="x.png", options={"quality": 500}))
    assert error["field"] == "quality" and error["schema"]["properties"]["quality"]["maximum"] == 100
    error = payload(call_error(server, "vixl_check", action="nonsense"))
    assert error["error"] == "invalid_arguments"


def test_unadvertised_arguments_fold_into_options(tmp_path):
    server = build_server(Session(workspace=tmp_path))
    asyncio.run(server.call_tool("vixl_document", {"action": "create", "path": "a.vixl", "width": 40, "height": 20}))

    def size(arguments):
        from io import BytesIO

        from PIL import Image
        import base64

        content = asyncio.run(server.call_tool("vixl_render", arguments))
        content = content[0] if isinstance(content, tuple) else content
        return Image.open(BytesIO(base64.b64decode(content[0].data))).size

    assert size({"max_width": 20}) == size({"options": {"max_width": 20}}) == (20, 10)


def test_mcp_missing_import_reports_relative_path(tmp_path):  # #676
    server = build_server(Session(workspace=tmp_path))
    asyncio.run(server.call_tool("vixl_document", {"action": "create", "path": "a.vixl", "width": 20, "height": 20}))
    message = call_error(server, "vixl_apply", operations=[{"type": "import-image", "path": "art/missing.png"}])
    error = payload(message)
    assert error["error"] == "not_found" and "art/missing.png" in error["message"]
    assert str(tmp_path) not in message and "Errno" not in message
