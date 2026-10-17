"""Hostile or broken input from outside (archives, paths) fails as a VixlError that names no absolute path."""

import asyncio
import json
import struct

import pytest
from mcp.server.fastmcp.exceptions import ToolError

from vixl import Project, VixlError
from vixl.interfaces import Session
from vixl.mcp_tools import build_server


def patch_member(data, name, *, flags=0, method=None):
    """``data`` (a ZIP archive) with ``name``'s general-purpose flags or compression method rewritten in both its
    local header and its central directory entry."""
    data = bytearray(data)
    encoded = name.encode()
    for signature, flag_at, method_at, name_at in ((b"PK\x03\x04", 6, 8, 30), (b"PK\x01\x02", 8, 10, 46)):
        start = 0
        while (start := data.find(signature, start)) != -1:
            if data[start + name_at:start + name_at + len(encoded)] == encoded:
                current = struct.unpack_from("<H", data, start + flag_at)[0]
                struct.pack_into("<H", data, start + flag_at, current | flags)
                if method is not None:
                    struct.pack_into("<H", data, start + method_at, method)
            start += 4
    return bytes(data)


@pytest.mark.parametrize("change", [{"flags": 1}, {"method": 99}], ids=["encrypted", "method-99"])
def test_encrypted_and_method99_archives_are_invalid_project(tmp_path, change):  # #676
    path = tmp_path / "doc.vixl"
    Project(40, 30, "#ffffff").save(path)
    path.write_bytes(patch_member(path.read_bytes(), "project.json", **change))
    with pytest.raises(VixlError) as raised:
        Project.load(path)
    assert raised.value.code == "invalid_project"
    assert "unsupported or encrypted ZIP member" in str(raised.value)


def call_error(server, name, **arguments):
    with pytest.raises(ToolError) as raised:
        asyncio.run(server.call_tool(name, arguments))
    message = str(raised.value)
    return message, json.loads(message[message.index("{"):])


def test_nul_path_is_invalid_input(tmp_path):  # #676
    session = Session(workspace=tmp_path)
    with pytest.raises(VixlError) as raised:
        session.resolve("a\0b.vixl")
    assert raised.value.code == "invalid_input" and raised.value.details["field"] == "path"
    server = build_server(Session(workspace=tmp_path))
    message, error = call_error(server, "vixl_document", action="open", path="a\0b.vixl")
    assert error["error"] == "invalid_input" and str(tmp_path) not in message


def test_document_list_hides_absolute_workspace(tmp_path):  # #676
    server = build_server(Session(workspace=tmp_path))
    content = asyncio.run(server.call_tool("vixl_document", {"action": "list"}))
    text = content[0].text if isinstance(content, list) else content[0][0].text
    assert json.loads(text)["workspace"] == "." and str(tmp_path) not in text


def test_mcp_os_errors_show_paths_relative_to_the_workspace(tmp_path, monkeypatch):  # #676
    from vixl import assets

    def unreadable(path, limit):
        raise PermissionError(13, "Permission denied", str(path))

    monkeypatch.setattr(assets, "read_bounded", unreadable)
    server = build_server(Session(workspace=tmp_path))
    asyncio.run(server.call_tool("vixl_document", {"action": "create", "path": "a.vixl", "width": 20, "height": 20}))
    message, error = call_error(server, "vixl_apply", operations=[{"type": "import-image", "path": "art/photo.png"}])
    assert error["error"] == "io_error" and error["message"] == "Permission denied: art/photo.png"
    assert str(tmp_path) not in message


def test_friendly_shows_a_file_outside_the_workspace_by_basename_only(tmp_path):  # #676
    from vixl.errors import friendly

    inside = FileNotFoundError(2, "No such file or directory", str(tmp_path / "art" / "a.png"))
    outside = FileNotFoundError(2, "No such file or directory", "/srv/private/b.png")
    assert str(friendly(inside, relative_to=tmp_path)) == "No such file: art/a.png"
    assert str(friendly(outside, relative_to=tmp_path)) == "No such file: b.png"
    assert str(friendly(outside)) == "No such file: /srv/private/b.png"  # The CLI shows what the user typed.
