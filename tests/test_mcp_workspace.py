"""Model-facing contracts, workspace safety and persistent-session regressions."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
import json
import os
import sys

import jsonschema
import numpy as np
from PIL import Image
import pytest

from vixl import Project, VixlError
from vixl.interfaces import Session, mcp_server
from vixl.mcp_tools import export_file, preview
from test_interfaces_ai import FakeProvider


def test_tools_list_is_lean_and_operations_are_checked_when_applied(tmp_path):
    async def run():
        server = mcp_server(workspace=tmp_path)
        tools = {t.name: t for t in await server.list_tools()}
        schema = tools["vixl_apply"].inputSchema
        jsonschema.Draft202012Validator.check_schema(schema)
        jsonschema.validate({"operations": [{"type": "text", "text": "title"}, {"type": "hide"}]}, schema)
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate({"operations": [{"text": "no type"}]}, schema)
        assert not any(name.startswith("vixl_ai") for name in tools)
        ai = {t.name: t for t in await mcp_server(workspace=tmp_path, tools="ai").list_tools()}
        assert "args" not in ai["vixl_ai_generate"].inputSchema["properties"]
        assert ai["vixl_ai_generate"].inputSchema["properties"]["seed"]["type"] == "integer"
        await server.call_tool("vixl_document", {"action": "create", "path": "a.vixl", "width": 16, "height": 16})
        for invalid, kind in (({"type": "made-up"}, None), ({"type": "opacity", "value": 3}, "opacity"),
                              ({"type": "mask", "action": "import"}, "mask")):
            with pytest.raises(Exception) as caught:
                await server.call_tool("vixl_apply", {"operations": [invalid]})
            error = json.loads(str(caught.value)[str(caught.value).index("{"):])
            if kind:  # Range and service-policy refusals do not need the full operation schema.
                assert "schema" not in error


    asyncio.run(run())


def test_compact_changes_and_dry_run(tmp_path):
    session = Session(workspace=tmp_path)
    session.create("poster.vixl", 100, 100)
    session.apply([{"type": "solid", "name": f"layer{i}"} for i in range(28)])
    ident = session.inspect()["layers"][0]["id"]
    original = (tmp_path / "poster.vixl").read_bytes()
    result = session.apply([{"type": "move", "target": ident, "x": 12}], dry_run=True)
    assert len(json.dumps(result)) < 600
    assert result["changes"]["layers"][ident]["x"] == 12
    assert result["changes"]["layers"][ident]["bounds"][0] == 12
    assert (tmp_path / "poster.vixl").read_bytes() == original
    assert session.inspect()["layers"][0]["x"] == 0
    full = session.apply([{"type": "move", "target": ident, "x": 12}], detail="full")
    assert len(full["changes"]["layers"]["before"]) == 28
    result = session.apply([{"type": "top", "target": ident}])
    assert result["changes"]["layer_order"][-1] == ident
    result = session.apply([{"type": "remove", "target": ident}])
    assert result["changes"]["layers"][ident]["removed"]


def test_session_caches_and_reloads_external_changes(tmp_path, monkeypatch):
    p = Project(16, 16)
    p.apply({"type": "solid", "name": "logo"})
    path = tmp_path / "doc.vixl"
    p.save(path)
    original_load = Project.load
    calls = []

    def load(*args, **kwargs):
        calls.append(args[0])
        return original_load(*args, **kwargs)

    monkeypatch.setattr(Project, "load", load)
    session = Session(path)
    for _ in range(10):
        session.inspect()
        session.validate()
    session.apply([{"type": "move", "x": 3}])
    session.inspect()
    assert len(calls) == 1
    external = original_load(path)
    external.apply({"type": "move", "x": 8})
    external.save()
    assert session.inspect()["layers"][0]["x"] == 8
    assert len(calls) == 2
    with pytest.raises(VixlError):
        session.apply([{"type": "move", "x": 10}, {"type": "opacity", "value": 400}])
    assert session.inspect()["layers"][0]["x"] == 8


def test_save_failure_discards_dirty_cache(tmp_path, monkeypatch):
    session = Session(workspace=tmp_path)
    session.create("a.vixl", 16, 16)
    session.apply([{"type": "solid"}])
    original = Project.save

    def fail(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(Project, "save", fail)
    with pytest.raises(OSError):
        session.apply([{"type": "move", "x": 10}])
    monkeypatch.setattr(Project, "save", original)
    assert session.inspect()["layers"][0]["x"] == 0


def test_two_sessions_and_threads_do_not_lose_edits(tmp_path):
    first = Session(workspace=tmp_path)
    first.create("a.vixl", 16, 16)
    first.apply([{"type": "solid"}])
    second = Session(tmp_path / "a.vixl")

    def move(i):
        (first if i % 2 else second).apply([{"type": "move", "x": 1, "relative": True}])

    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(move, range(12)))
    assert first.inspect()["layers"][0]["x"] == 12
    assert second.inspect()["layers"][0]["x"] == 12


def test_workspace_io_boundaries_and_failed_switch(tmp_path):
    workspace = tmp_path / "work"
    workspace.mkdir()
    session = Session(workspace=workspace)
    with pytest.raises(VixlError, match="Create or open"):
        session.inspect()
    session.create("a.vixl", 16, 16)
    original_head = session.inspect()["head"]
    for path in ("../escape.vixl", str(tmp_path / "outside.vixl")):
        with pytest.raises(VixlError):
            session.create(path, 16, 16)
    outside = tmp_path / "outside"
    outside.mkdir()
    try:
        (workspace / "link").symlink_to(outside, target_is_directory=True)
    except OSError:
        pass  # Windows accounts may lack symlink privileges.
    else:
        with pytest.raises(VixlError):
            session.create("link/escape.vixl", 16, 16)
    with pytest.raises(VixlError):
        session.create("a.vixl", 32, 32)
    with pytest.raises((VixlError, OSError)):
        session.open("missing.vixl")
    assert session.inspect()["head"] == original_head
    export_file(session, "out.png")
    assert Image.open(workspace / "out.png").size == (16, 16)
    with pytest.raises(VixlError):
        export_file(session, "out.png")
    export_file(session, "out.png", overwrite=True)
    with pytest.raises(VixlError):
        export_file(session, "a.vixl", overwrite=True)
    session.create("b.vixl", 32, 32)
    session.open("a.vixl")
    assert session.inspect()["head"] == original_head


def test_photo_preview_is_bounded_and_document_unchanged(tmp_path):
    # Incompressible 12 MP RGB pixels exercise the worst-case PNG size.
    source = Image.fromarray(np.random.default_rng(42).integers(0, 256, (3000, 4000, 3), dtype=np.uint8))
    data = BytesIO()
    source.save(data, format="PNG")
    session = Session(workspace=tmp_path)
    session.create("photo.vixl", 4000, 3000)
    session.import_image(data.getvalue())
    before = session.inspect()
    for width, height, budget in ((1024, 1024, 1048576), (2048, 1024, 65536)):
        result = preview(session, max_width=width, max_height=height, max_bytes=budget)
        image = Image.open(BytesIO(result))
        assert len(result) <= budget
        assert image.width <= width and image.height <= height
        assert abs(image.width / image.height - 4 / 3) < 0.01
    assert session.inspect() == before


def test_typed_ai_preserves_arguments_and_undo(tmp_path, monkeypatch):
    import vixl.plugins.ai.ai

    backend = FakeProvider()
    monkeypatch.setattr(vixl.plugins.ai.ai, "provider", lambda _: backend)
    session = Session(workspace=tmp_path)
    session.create("a.vixl", 16, 16)
    server = __import__("vixl.mcp_tools", fromlist=["build_server"]).build_server(session, tools="ai")

    async def call(tool_name, **arguments):
        return await server.call_tool(tool_name, arguments)

    asyncio.run(call("vixl_ai_generate", prompt="literal --seed 99", seed=7, name="--logo"))
    assert backend.requests[-1][1]["prompt"] == "literal --seed 99"
    assert backend.requests[-1][1]["seed"] == 7
    ident = session.inspect()["layers"][0]["id"]
    asyncio.run(call("vixl_ai_remove_background", layer="--logo"))
    assert session.inspect()["layers"][0]["mask"]["enabled"]
    asyncio.run(call("vixl_ai_regenerate", layer=ident, prompt="again", seed=8))
    assert len(session.inspect()["layers"]) == 1
    assert session.inspect()["layers"][0]["id"] == ident
    session.history("undo")
    assert session.inspect()["layers"][0]["provenance"]["request"]["prompt"] == "literal --seed 99"


def test_real_mcp_empty_workspace_to_export(tmp_path):
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    Image.new("RGB", (20, 10), "red").save(tmp_path / "photo.png")

    async def run():
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "vixl", "mcp", "--workspace", str(tmp_path)],
            env=os.environ.copy(),
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as client:
                await client.initialize()

                async def call(tool_name, **args):
                    result = await client.call_tool(tool_name, args)
                    assert not result.isError, result
                    return result

                await call("vixl_document", action="list")
                created = await call("vixl_document", action="create", path="a.vixl", width=20, height=10)
                assert len(created.content[0].text) < 400  # a new blank document's result is terse
                await call("vixl_apply", operations=[{"type": "import-image", "path": "photo.png", "name": "photo"}])
                result = await call("vixl_apply", operations=[{"type": "move", "x": 1}])
                assert len(result.model_dump_json()) < 1500
                await call("vixl_render", max_width=16, max_height=16)
                await call("vixl_export", path="out.png")
                await call("vixl_document", action="create", path="b.vixl", width=10, height=10)
                await call("vixl_document", action="open", path="a.vixl")
                failed = await client.call_tool("vixl_apply", {"document": "a.vixl", "operations": [
                    {"type": "import-image", "path": "../outside.png"}]})
                assert failed.isError and "ambiguous_document" not in failed.content[0].text
                # Two documents open on one connection: a call must name its document.
                ambiguous = await client.call_tool("vixl_document", {"target": "photo"})
                assert ambiguous.isError and "ambiguous_document" in ambiguous.content[0].text
                await call("vixl_document", target="photo", document="a.vixl")

    asyncio.run(run())
    assert Image.open(tmp_path / "out.png").size == (20, 10)
    assert Project.load(tmp_path / "a.vixl").layer()["x"] == 1


def test_relative_initial_project_and_external_change_during_read(tmp_path, monkeypatch):
    directory = tmp_path / "sub"
    directory.mkdir()
    p = Project(16, 16)
    p.save(directory / "a.vixl")
    monkeypatch.chdir(tmp_path)
    session = Session("sub/a.vixl")
    with session.project() as cached:
        other = Project.load(directory / "a.vixl")
        other.apply({"type": "solid", "name": "external"})
        other.save()
        assert not cached.state["layers"]
    assert session.inspect()["layers"][0]["name"] == "external"


def test_workspace_export_profile_with_filename_format(tmp_path):
    session = Session(workspace=tmp_path)
    session.create("a.vixl", 1200, 800)
    # Filename format takes precedence; the profile still supplies its size/quality.
    result = export_file(session, "social.png", profile="instagram")
    with Image.open(tmp_path / "social.png") as image:
        assert image.format == result["format"] == "PNG"
        assert image.size == (1080, 720)


def test_mcp_splits_into_design_and_ai_servers(tmp_path, monkeypatch):
    import vixl.plugins.ai.ai
    from vixl.mcp_tools import SHARED_TOOLS, TOOLS, build_server

    backend = FakeProvider()
    monkeypatch.setattr(vixl.plugins.ai.ai, "provider", lambda _: backend)

    async def names(server):
        return {t.name for t in await server.list_tools()}

    design = asyncio.run(names(mcp_server(workspace=tmp_path)))
    ai = asyncio.run(names(mcp_server(workspace=tmp_path, tools="ai")))
    assert design == set(TOOLS) and design & ai == SHARED_TOOLS
    assert {"vixl_ai_generate", "vixl_models_list"} <= ai and "vixl_apply" not in ai
    with pytest.raises(VixlError):
        mcp_server(workspace=tmp_path, tools="core")

    # Separate processes share documents through the workspace: AI edits reach the design server.
    core_session, ai_session = Session(workspace=tmp_path), Session(workspace=tmp_path)
    core_server = build_server(core_session)
    ai_server = build_server(ai_session, tools="ai")
    asyncio.run(core_server.call_tool("vixl_document", {"action": "create", "path": "a.vixl", "width": 16, "height": 16}))
    asyncio.run(ai_server.call_tool("vixl_ai_generate", {"prompt": "a sun", "name": "sun", "document": "a.vixl"}))
    assert [layer["name"] for layer in core_session.inspect()["layers"]] == ["sun"]
    asyncio.run(core_server.call_tool("vixl_apply", {"operations": [{"type": "hide", "target": "sun"}]}))
    ai_session.open("a.vixl")
    assert not ai_session.inspect()["layers"][0]["visible"]


def test_import_document_step_routes_figma_sources_with_their_options(tmp_path, monkeypatch):
    import vixl.imports
    from vixl.mcp_tools import build_server

    seen = []

    def fake(project, data, format, name="import", page=1, dpi=144, svg_mode="editable", **options):
        seen.append((data, format, page, options))
        return {"imported": format}

    monkeypatch.setattr(vixl.imports, "import_document", fake)
    session = Session(workspace=tmp_path)
    session.create("a.vixl", 16, 16)
    server = build_server(session)
    asyncio.run(server.call_tool("vixl_apply", {"operations": [{
        "type": "import-document", "source": "https://www.figma.com/design/KEY/name", "node_id": "1-2",
        "page": "Cover", "rasterize_unsupported": True}]}))
    assert seen == [("https://www.figma.com/design/KEY/name", "figma", "Cover",
                     {"node_id": "1-2", "rasterize_unsupported": True})]
    with pytest.raises(Exception, match="Figma import options"):
        asyncio.run(server.call_tool("vixl_apply", {"operations": [{
            "type": "import-document", "path": "a.svg", "node_id": "1:2"}]}))


def test_import_document_step_imports_exported_figma_json_offline(tmp_path):
    import shutil
    from pathlib import Path

    from vixl.mcp_tools import build_server

    shutil.copy(Path(__file__).parent / "fixtures" / "figma" / "poster.json", tmp_path / "poster.json")
    session = Session(workspace=tmp_path)
    session.create("a.vixl", 16, 16)
    server = build_server(session)
    asyncio.run(server.call_tool("vixl_apply", {"operations": [{"type": "import-document", "path": "poster.json"}]}))
    layers = session.inspect()["layers"]
    assert any(layer["type"] == "text" for layer in layers)
    assert len(layers) > 1
