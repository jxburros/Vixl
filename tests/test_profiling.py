"""Render profiling (#594): per-layer times and cache counters on every interface with VIXL_PROFILE, nothing
when it is off; the opt-in ``cost`` check; per-frame timing in timeline export progress."""

import asyncio
import json

import pytest

from vixl import Project, profiling
from vixl.cli import main


def document(path=None):
    p = Project(400, 300, "white")
    p.apply([{"type": "shape", "shape": "star", "name": "s", "x": 10, "y": 10, "width": 100, "height": 100,
              "fill": "gold"},
             {"type": "text", "name": "t", "text": "Hello", "size": 40, "x": 200, "y": 100, "color": "black"},
             {"type": "look", "look": "soft-shadow", "target": "t"}], detail="brief")
    if path:
        p.save(path)
    return p


def test_a_profile_reports_layers_caches_and_incremental_renders():
    p = document()
    with profiling.profile() as run:
        p.render()
        p.apply({"type": "move", "target": "s", "x": 40, "y": 30}, detail="brief")
        p.render()
    report = run.report()
    assert {entry["name"] for entry in report["layers"]} == {"s", "t"}
    star = next(entry for entry in report["layers"] if entry["name"] == "s")
    assert star["draws"] == 1 and set(star["stages_ms"]) >= {"draw", "transform", "effects"}
    caches = report["caches"]
    # The moved star is found in the layer cache; the shadowed text was styled once.
    assert caches["layer_hits"] >= 1 and caches["layer_misses"] == 2 and caches["styled_misses"] == 1
    first, second = report["renders"]
    assert first["incremental"] is False and second["incremental"] is True
    assert 0 < second["dirty_pixels"] < second["canvas_pixels"]
    assert {"render", "resolve", "layout"} <= set(report["phases_ms"])
    assert report["by_type"]["shape"]["layers"] == 1


def test_profiles_cost_nothing_when_off(monkeypatch, tmp_path):
    monkeypatch.delenv("VIXL_PROFILE", raising=False)
    monkeypatch.setattr(profiling.Profile, "__init__", lambda self: pytest.fail("profiled without VIXL_PROFILE"))
    document(tmp_path / "doc.vixl")
    assert main(["-p", str(tmp_path / "doc.vixl"), "--json", "export", str(tmp_path / "a.png")]) == 0
    assert profiling.current() is None


def test_the_cli_returns_the_profile_with_its_result(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("VIXL_PROFILE", "1")
    document(tmp_path / "doc.vixl")
    assert main(["-p", str(tmp_path / "doc.vixl"), "--json", "export", str(tmp_path / "a.png")]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["output"] and result["render_profile"]["layers_drawn"] >= 2
    assert "disk_misses" in result["render_profile"]["caches"] or "disk_frame_misses" in result["render_profile"]["caches"]


def test_a_cli_result_that_is_not_json_reports_the_profile_on_stderr(monkeypatch, tmp_path, capsysbinary):
    monkeypatch.setenv("VIXL_PROFILE", "1")
    document(tmp_path / "doc.vixl")
    assert main(["-p", str(tmp_path / "doc.vixl"), "export", "-", "--format", "PNG"]) == 0
    captured = capsysbinary.readouterr()
    assert captured.out.startswith(b"\x89PNG") and b"render_profile" in captured.err


def test_mcp_results_carry_the_profile(monkeypatch, tmp_path):
    from mcp.shared.memory import create_connected_server_and_client_session

    from vixl.interfaces import mcp_server

    monkeypatch.setenv("VIXL_PROFILE", "1")
    document(tmp_path / "doc.vixl")
    server = mcp_server(workspace=tmp_path)

    async def scenario():
        async with create_connected_server_and_client_session(server._mcp_server) as client:
            await client.call_tool("vixl_document_open", {"path": "doc.vixl"})
            checked = await client.call_tool("vixl_check", {"checks": ["overlap"]})
            preview = await client.call_tool("vixl_render_preview", {"max_width": 200, "max_height": 200})
            return checked, preview

    checked, preview = asyncio.run(scenario())
    result = json.loads("".join(getattr(item, "text", "") for item in checked.content))
    assert "render_profile" in result and "caches" in result["render_profile"]
    notes = [json.loads(item.text) for item in preview.content if getattr(item, "text", None)]
    assert any("render_profile" in note for note in notes)


def test_rest_responses_carry_the_profile(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient

    from vixl.interfaces import create_app

    document(tmp_path / "doc.vixl")
    with TestClient(create_app(tmp_path / "doc.vixl")) as client:
        assert "x-vixl-profile" not in client.get("/render").headers
        monkeypatch.setenv("VIXL_PROFILE", "1")
        image = client.get("/render")
        assert image.headers["content-type"] == "image/png"
        assert json.loads(image.headers["x-vixl-profile"])["render_count"] >= 1
        checked = client.post("/check", json={"checks": ["overlap"]})
        assert checked.status_code == 200 and "render_profile" in checked.json()


def test_the_cost_check_names_the_layer_that_dominates_the_render():
    from vixl.checks import check_design

    p = Project(1600, 1200, "white")
    p.apply([{"type": "shape", "shape": "rectangle", "name": f"r{i}", "x": 20 + i * 40, "y": 20, "width": 30,
              "height": 30, "fill": "#369"} for i in range(12)]
            + [{"type": "solid", "name": "haze", "color": "#88aacc", "width": 1600, "height": 1200},
               {"type": "effect", "target": "haze", "name": "blur", "amount": 60},
               {"type": "effect", "target": "haze", "name": "noise", "amount": 0.05}], detail="brief")
    report = check_design(p, checks=["cost"])
    findings = [item for item in report["issues"] if item["check"] == "cost"]
    assert [item["layers"] for item in findings] == [["haze"]]
    finding = findings[0]
    assert finding["action"] == "review" and "blur radius 60 px" in finding["message"]
    assert finding["ms"] > 10 * finding["median_ms"] and "blur radius 60 px" in finding["causes"]
    assert report["passed"]  # a review finding, not a failure
    assert not [item for item in check_design(document(), checks=["cost"])["issues"] if item["check"] == "cost"]


def test_timeline_exports_report_per_frame_timing(tmp_path):
    from vixl.timeline import export_timeline

    p = document()
    p.apply([{"type": "timeline-set", "duration": 1000},
             {"type": "keyframe", "target": "s", "property": "x", "time": 0, "value": 0},
             {"type": "keyframe", "target": "s", "property": "x", "time": 1000, "value": 200}], detail="brief")
    seen = []
    export_timeline(p, tmp_path / "a.gif", fps=8, progress=seen.append)
    assert [item["done"] for item in seen] == list(range(1, 9)) and seen[-1]["total"] == 8
    timing = [item["timing"] for item in seen]
    assert all({"elapsed_s", "eta_s", "setup_ms", "raster_ms"} <= set(item) for item in timing)
    assert timing[-1]["eta_s"] == 0 and timing[-1]["elapsed_s"] >= timing[0]["elapsed_s"]


def test_job_progress_carries_the_timing():
    from vixl.calls import CALL, CallState, progress_dict

    reports = []
    state = CallState(report=lambda *args: reports.append(args))
    token = CALL.set(state)
    try:
        progress_dict({"done": 2, "total": 10, "timing": {"elapsed_s": 1.0, "eta_s": 4.0}})
    finally:
        CALL.reset(token)
    assert reports == [(2, 10, None, {"elapsed_s": 1.0, "eta_s": 4.0})]
