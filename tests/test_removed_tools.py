import asyncio

import pytest
from mcp.server.fastmcp.exceptions import ToolError

from vixl import briefs
from vixl.errors import VixlError
from vixl.interfaces import Session
from vixl.mcp_tools import REMOVED_TOOLS, build_server


def call_error(server, name, **arguments):
    with pytest.raises(ToolError) as raised:
        asyncio.run(server.call_tool(name, arguments))
    return str(raised.value)


def test_removed_text_tool_names_its_replacement(tmp_path):
    message = call_error(build_server(Session(workspace=tmp_path), tools="core"), "vixl_text_add", text="Hi")
    assert "vixl_operations_apply" in message and "'text' operation" in message


def test_tool_from_another_toolset_names_the_mode_that_serves_it(tmp_path):
    message = call_error(build_server(Session(workspace=tmp_path), tools="core"), "vixl_ai_generate")
    assert "--tools ai" in message
    message = call_error(build_server(Session(workspace=tmp_path), tools="compact"), "vixl_check")
    assert "--tools core" in message


def test_misspelled_tool_suggests_close_names(tmp_path):
    message = call_error(build_server(Session(workspace=tmp_path), tools="core"), "vixl_operation_apply")
    assert "vixl_operations_apply" in message


def test_removed_tools_are_not_served(tmp_path):
    tools = {tool.name for tool in asyncio.run(build_server(Session(workspace=tmp_path)).list_tools())}
    assert not tools & set(REMOVED_TOOLS)


def test_guide_capabilities_alias_points_to_vixl_capabilities():
    with pytest.raises(VixlError) as raised:
        briefs.guide("capabilities animation")
    assert raised.value.code == "moved"
    assert "vixl_capabilities(topic='animation')" in str(raised.value)
    assert briefs.guide("animation")["kind"] == "animation"
