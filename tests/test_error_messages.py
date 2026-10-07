"""Errors a person can act on: no Python reprs, no hints for the wrong interface, no echoed inputs."""

import asyncio
import json

import pytest

from vixl import Project, VixlError
from vixl.cli import check_names, main
from vixl.interfaces import mcp_server


def cli(capsys, *args):
    code = main(list(args))
    captured = capsys.readouterr()
    return code, captured.out, captured.err


@pytest.fixture
def doc(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert main(["new", "200x100", "-o", "H.vixl", "--background", "white"]) == 0
    for name in ("a", "b", "c"):
        assert main(["-p", "H.vixl", "shape", "rectangle", "--name", name]) == 0
    return tmp_path / "H.vixl"


def test_undo_and_redo_go_as_far_as_history_allows(doc, capsys):
    capsys.readouterr()
    code, out, _ = cli(capsys, "-p", str(doc), "undo", "999")
    result = json.loads(out)
    assert code == 0 and result["undo"] == 3 and "only 3 step(s)" in result["notes"][-1]
    code, out, _ = cli(capsys, "-p", str(doc), "redo", "50")
    assert json.loads(out)["redo"] == 3
    code, _, err = cli(capsys, "-p", str(doc), "undo", "abc")
    assert code == 1 and "whole number" in err and "int()" not in err


def test_project_redo_restores_once_and_reports_steps():
    project = Project(50, 50)
    for index in range(5):
        project.apply({"type": "shape", "shape": "rectangle", "name": f"r{index}"})
    assert project.undo(10) == 5 and project.state["layers"] == []
    assert project.redo(2) == 2 and [layer["name"] for layer in project.state["layers"]] == ["r0", "r1"]
    with pytest.raises(VixlError, match="positive whole number"):
        project.undo(0)


def test_cli_check_accepts_every_registered_check(doc, capsys):
    assert {"motion", "character", "captions", "connected", "deck", "codes"} <= set(check_names())
    code, out, _ = cli(capsys, "-p", str(doc), "check", "--checks", "motion", "character", "captions")
    assert code == 0 and "passed" in json.loads(out)


@pytest.mark.parametrize("typo, hint", [("trianglee", "triangle"), ("hexagonn", "hexagon")])
def test_shape_typos_are_errors_with_a_suggestion(typo, hint):
    with pytest.raises(VixlError, match=f"Did you mean '{hint}'"):
        Project(100, 100).apply({"type": "shape", "shape": typo, "name": "s"})


def test_shape_variants_still_map_to_their_base_shape():
    project = Project(100, 100)
    project.apply([{"type": "shape", "shape": "hexagonal", "name": "h"}, {"type": "shape", "shape": "stars", "name": "s"}])
    assert project.layer("h")["shape"] == "polygon" and project.layer("s")["shape"] == "star"


@pytest.mark.parametrize("sides", [0, 2, 1000])
def test_polygon_sides_have_one_range(sides):
    with pytest.raises(VixlError, match=r"minimum of 3|maximum of 128"):
        Project(100, 100).apply({"type": "shape", "shape": "polygon", "sides": sides, "name": "p"})


def test_cli_errors_name_cli_commands_and_plain_causes(doc, tmp_path, capsys):
    code, _, err = cli(capsys, "-p", str(doc), "opacity", "a", "-0.1")
    assert code == 1 and "vixl capabilities opacity" in err and "vixl_operation_schema" not in err
    code, _, err = cli(capsys, "-p", str(tmp_path / "missing.vixl"), "layers")
    assert code == 1 and err.startswith("ERROR: No such file") and "Errno" not in err
    (tmp_path / "bin.json").write_bytes(b"\xff\xfe")
    code, _, err = cli(capsys, "-p", str(doc), "apply", str(tmp_path / "bin.json"))
    assert code == 1 and "not UTF-8" in err and "codec" not in err
    (tmp_path / "notimg.jpg").write_text("hello")
    code, _, err = cli(capsys, "-p", str(doc), "import", str(tmp_path / "notimg.jpg"))
    assert code == 1 and "not a supported image format" in err and "0x" not in err


def test_cli_size_dpi_and_format_messages(tmp_path, capsys, monkeypatch):
    monkeypatch.chdir(tmp_path)
    code, _, err = cli(capsys, "new", "800x600", "--dpi", "0", "-o", "d.vixl")
    assert code == 1 and "36–2400" in err and not (tmp_path / "d.vixl").exists()
    code, _, err = cli(capsys, "new", "-10x10", "-o", "n.vixl")
    assert code == 1 and "1–16384" in err
    assert main(["new", "10X10", "-o", "u.vixl"]) == 0
    code, _, err = cli(capsys, "new", "", "-o", "e.vixl")
    assert code == 1 and "Give a size" in err
    code, _, err = cli(capsys, "-p", "u.vixl", "export", "out.xyz")
    assert code == 1 and "'.xyz'" in err and "png" in err and "pptx" in err


def test_cli_exports_wav_and_refuses_to_overwrite(tmp_path, capsys, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert main(["new", "100x100", "-o", "a.vixl"]) == 0
    capsys.readouterr()
    code, out, _ = cli(capsys, "-p", "a.vixl", "export", "a.wav")
    assert code == 0 and json.loads(out)["sample_rate"] and (tmp_path / "a.wav").stat().st_size > 44
    code, _, err = cli(capsys, "-p", "a.vixl", "export", "a.wav")
    assert code == 1 and "--overwrite" in err


def test_python_export_audio_raises_a_structured_error_on_overwrite(tmp_path):
    from vixl.audio import export_audio

    project = Project(100, 100)
    export_audio(project, tmp_path / "a.wav")
    with pytest.raises(VixlError) as caught:
        export_audio(project, tmp_path / "a.wav")
    assert caught.value.code == "output_exists"
    export_audio(project, tmp_path / "a.wav", overwrite=True)


def test_unknown_fields_suggest_aliases_and_the_right_operation():
    with pytest.raises(VixlError, match="'fill' instead of 'colr'"):
        Project(100, 100).apply({"type": "shape", "name": "s", "colr": "red"})
    with pytest.raises(VixlError, match="text-layout") as caught:
        Project(100, 100).apply({"type": "text", "name": "t", "text": "hi", "width": 50})
    assert "'within' instead of 'width'" not in str(caught.value)


def test_too_long_lists_are_reported_by_size_not_echoed():
    with pytest.raises(VixlError) as caught:
        Project(500, 500).apply({"type": "pen", "name": "x", "points": [[1, 1]] * 100_000})
    assert "at most 512 entries; got 100000" in str(caught.value) and len(str(caught.value)) < 300


def test_deep_group_chains_fail_fast_at_the_first_bad_step():
    import time

    operations = [{"type": "shape", "shape": "rectangle", "name": "s0"}]
    operations += [{"type": "group", "name": f"g{i}", "targets": ["s0" if i == 0 else f"g{i - 1}"]} for i in range(500)]
    project = Project(200, 200)
    started = time.monotonic()
    with pytest.raises(VixlError, match=r"operations\[16\].*15 nested groups"):
        project.apply(operations)
    assert time.monotonic() - started < 2 and project.state["layers"] == []
    project.apply(operations[:16])


def test_mcp_argument_errors_use_the_json_error_shape(tmp_path):
    server = mcp_server(workspace=tmp_path)

    async def run():
        return await server.call_tool("vixl_resource_get", {"name": "x"})

    with pytest.raises(Exception) as caught:
        asyncio.run(run())
    payload = json.loads(str(caught.value))
    assert payload["error"] == "invalid_arguments" and payload["field"] == "kind" and "pydantic" not in str(caught.value)


def test_mcp_errors_name_mcp_tools(tmp_path):
    server = mcp_server(workspace=tmp_path)

    async def run(name, arguments):
        return await server.call_tool(name, arguments)

    asyncio.run(run("vixl_document_create", {"path": "a.vixl", "width": 400, "height": 300}))
    with pytest.raises(Exception) as caught:
        asyncio.run(run("vixl_operations_apply", {"operations": [
            {"type": "layout-apply", "name": "zzzz-no-such-layout"}]}))
    assert "vixl_layouts_list" in str(caught.value) and "vixl layout list" not in str(caught.value)


def test_compact_toolset_texts_only_name_served_tools(tmp_path):
    import re

    server = mcp_server(workspace=tmp_path, tools="compact")
    listed = asyncio.run(server.list_tools())
    served = {tool.name for tool in listed}
    text = server.instructions + " ".join((tool.description or "") + json.dumps(tool.inputSchema) for tool in listed)
    assert set(re.findall(r"vixl_[a-z_]+", text)) <= served


def test_rest_routes_name_unknown_fields_and_ask_for_a_bearer_token(tmp_path):
    from fastapi.testclient import TestClient

    from vixl.interfaces import create_app

    path = tmp_path / "doc.vixl"
    Project(40, 30).save(path)
    with TestClient(create_app(path, token="secret")) as client:
        denied = client.post("/export", json={})
        assert denied.status_code == 401 and denied.headers["WWW-Authenticate"] == "Bearer"
        client.headers["Authorization"] = "Bearer secret"
        for route, body in (("/export", {"format": "PNG", "bogus": 1}), ("/compare", {"bogus": "x"}),
                            ("/preview", {"bogus": 1})):
            response = client.post(route, json=body)
            assert response.status_code == 400 and "'bogus'" in response.json()["message"], route
            assert response.json()["field"] == "bogus"
