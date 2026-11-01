"""Stage 2 contracts at the public check and delivery boundaries."""
import asyncio
import json

import pytest
from PIL import Image

from vixl import Project, VixlError
from vixl.call_limits import CallLimits, check_export, quote
from vixl.check_results import last_check
from vixl.checks import tally
from vixl.cli_summary import check as check_text
from vixl.interfaces import Session
from vixl.mcp_tools import build_server


def test_repeated_findings_have_one_group_and_a_blocking_verdict():
    issues = [{"check": "fonts", "code": "fallback", "severity": "warning", "layers": [f"t{i}"],
               "message": "Choose a font"} for i in range(20)]
    report = {**tally(issues), "issues": issues}
    assert report["summary"] == [{"rule": "fonts.fallback", "action": "fix", "count": 20,
                                   "layers": ["t0", "t1", "t2"], "fix": "Choose a font"}]
    assert "fonts.fallback" in report["verdict"]
    assert "no errors and no fix" in report["verdict"]
    assert report["top"] == report["summary"]
    assert "fonts.fallback" in check_text(report, "check")[0]


def test_delivery_cache_survives_reload_and_becomes_stale(tmp_path, monkeypatch):
    monkeypatch.setattr("vixl.render_cache.user_cache_dir", lambda: tmp_path / "cache")
    p = Project(400, 300)
    p.apply({"type": "text", "name": "t", "text": "Hello", "size": 30})
    p.save(tmp_path / "a.vixl")
    assert last_check(p) == "not_run"
    p.check(checks=["fonts"])
    report = {}
    p.export(report=report)
    assert report["last_check"]["fix"] >= 1
    reopened = Project.load(p.path)
    assert last_check(reopened)["revision"] == p.head
    reopened.apply({"type": "move", "target": "t", "x": 40})
    assert last_check(reopened) == "stale"
    with pytest.raises(VixlError, match="Design checks failed"):
        reopened.export(tmp_path / "strict.png", strict=True)
    assert not (tmp_path / "strict.png").exists()
    report = {}
    reopened.export(report=report, check_status=False)
    assert "last_check" not in report


def test_named_unattached_suite_and_inherited_profile(tmp_path):
    from vixl.resources import register

    register("suites", "delivery", {"rules": [{"id": "wide", "kind": "assert", "expression": "canvas.width >= 1000"}]}, workspace=tmp_path)
    p = Project(300, 200, workspace=tmp_path)
    report = p.check(checks=["bounds"], suites=["delivery"])
    assert not report["passed"] and "delivery" in report["verdict"]
    assert "suites" not in p.state
    (tmp_path / "brand.json").write_text(json.dumps({"suites": ["delivery"]}))
    for profile in (None, "review"):
        report = p.check(checks=["bounds"], profile=profile)
        suites = report.get("suites", report.get("profile", {}).get("suites"))
        assert suites["delivery"]["status"] == "failed"
        assert not report["passed"]


@pytest.mark.parametrize("rich", [False, True])
def test_word_break_finding_and_fitting(rich):
    p = Project(800, 500)
    op = {"type": "rich-text" if rich else "text", "name": "t", "size": 90}
    op["markdown" if rich else "text"] = "demystified"
    if rich:
        op["width"] = 200
    p.apply(op)
    p.apply({"type": "text-layout", "target": "t", "width": 200, "height": 400})
    findings = p.check(checks=["legibility"], thumbnail_width=None)["issues"]
    assert len([x for x in findings if x["rule"] == "legibility.word-break"]) == 1
    p.apply({"type": "fit-text", "target": "t", "width": 200, "height": 400})
    assert not any(x["rule"] == "legibility.word-break" for x in p.check(checks=["legibility"], thumbnail_width=None)["issues"])


def test_off_canvas_contrast_does_not_leak_internal_region_error():
    p = Project(800, 500)
    p.apply({"type": "text", "name": "t", "text": "Hello world", "x": 700, "y": 100, "size": 90})
    report = p.check(checks=["bounds", "contrast"])
    assert any(x["rule"] == "bounds.cut-off" for x in report["issues"])
    assert not any(x["rule"] == "contrast.unmeasurable" for x in report["issues"])


@pytest.mark.parametrize("effect", ["halftone", "crosshatch"])
def test_effect_paper_and_ink(effect):
    from vixl.artistic import artistic_filter as apply

    image = Image.new("RGBA", (16, 16), "white")
    result = apply(image, {"name": effect, "amount": 8, "paper": "#abcdef", "color": "red"})
    assert result.getpixel((0, 0))[:3] == (171, 205, 239)
    result = apply(Image.new("RGBA", (16, 16), "black"),
                   {"name": effect, "amount": 8, "paper": "white", "color": "red"})
    assert (255, 0, 0) in {v[:3] for v in result.getdata()}


def test_quote_matches_limits_without_writing(tmp_path, monkeypatch):
    p = Project(1000, 1000)
    limits = CallLimits(max_megapixels=2)
    quoted = quote(p, "PNG", {"scale": 2}, limits)
    assert not quoted["within_limits"]
    with pytest.raises(VixlError) as exc:
        check_export(limits, p, "PNG", {"scale": 2})
    assert exc.value.details["value"] == quoted["megapixels"] == 4
    monkeypatch.setattr(p, "render", lambda **kw: pytest.fail("quote rendered"))
    assert p.export(tmp_path / "none.png", dry_run=True)["dry_run"]
    assert not (tmp_path / "none.png").exists()
    p.apply({"type": "timeline-set", "duration": 1000, "fps": 24})
    motion = quote(p, "GIF", {})
    assert motion["frames"] == 24 and motion["duration_s"] == 1


@pytest.mark.parametrize("arguments,expected", [
    ({"operations": [{"type": "layout-apply", "name": "event-poster", "palette": "meadow"}]}, "palette"),
    ({"operations": [{"type": "layout-apply", "name": "event-poster", "date": "Today"}]}, "label"),
    ({"operations": [{"type": "solid", "color": "red"}], "options": {"detail": "summary"}}, "brief"),
])
def test_errors_are_small_and_actionable(tmp_path, arguments, expected):
    from mcp.server.fastmcp.exceptions import ToolError

    server = build_server(Session(workspace=tmp_path))
    asyncio.run(server.call_tool("vixl_document", {"action": "create", "path": "a.vixl", "width": 800, "height": 600}))
    with pytest.raises(ToolError) as exc:
        asyncio.run(server.call_tool("vixl_apply", arguments))
    message = str(exc.value)
    assert len(message) < 600
    assert expected in message and '"schema"' not in message


def test_dry_run_repair_cannot_claim_document_was_validated():
    from vixl.plugins.layout_repair.layout_repair import repair_layout

    p = Project(600, 400)
    p.apply({"type": "text", "name": "t", "text": "Hello", "size": 40, "x": -10, "y": 50})
    head = p.head
    proposal = repair_layout(p, checks=["bounds"], dry_run=True)
    assert proposal["operations"] and not proposal["committed"]
    assert proposal["outcome"]["state"] == "proposed"
    assert proposal["outcome"]["validation"] == "would_pass"
    assert proposal["outcome"]["review"] == "required"
    assert p.head == head
    committed = repair_layout(p, checks=["bounds"], dry_run=False)
    assert committed["committed"] and committed["outcome"]["validation"] == "passed"


def test_rest_quote_and_check_suite(tmp_path):
    from fastapi.testclient import TestClient
    from vixl.interfaces import create_app
    from vixl.resources import register

    register("suites", "delivery", {"rules": [{"id": "wide", "kind": "assert", "expression": "canvas.width >= 1000"}]}, workspace=tmp_path)
    p = Project(400, 300, workspace=tmp_path)
    path = tmp_path / "a.vixl"
    p.save(path)
    client = TestClient(create_app(path, call_limits=CallLimits(max_megapixels=1)))
    result = client.post("/export?dry_run=1", json={"format": "PNG", "scale": 4})
    assert result.status_code == 200
    assert result.json()["within_limits"] is False
    check = client.post("/check", json={"checks": ["bounds"], "suites": ["delivery"]})
    assert check.status_code == 200 and not check.json()["passed"]


def test_cjk_wraps_are_not_mid_word_defects():
    from vixl.text import mid_word

    assert mid_word("demystifie", "d")
    assert not mid_word("demysti-", "fied")
    assert not mid_word("漢", "字")


def test_inherited_design_suite_does_not_recurse(tmp_path):
    from vixl.resources import register

    register("suites", "design-suite", {"rules": [{"id": "design", "kind": "design", "options": {"checks": ["bounds"]}}]}, workspace=tmp_path)
    (tmp_path / "brand.json").write_text(json.dumps({"suites": ["design-suite"]}))
    p = Project(400, 300, workspace=tmp_path)
    assert p.check()["passed"]
    assert p.check(profile="review")["passed"]
    assert "suites" not in p.check(profile="review", suites="none")["profile"]


def test_rest_render_status_and_opt_out(tmp_path):
    from fastapi.testclient import TestClient
    from vixl.interfaces import create_app

    p = Project(40, 30)
    path = tmp_path / "a.vixl"
    p.save(path)
    client = TestClient(create_app(path))
    assert json.loads(client.get("/render").headers["X-Vixl-Last-Check"]) == "not_run"
    assert json.loads(client.post("/render", json={}).headers["X-Vixl-Last-Check"]) == "not_run"
    assert "X-Vixl-Last-Check" not in client.post("/render", json={"check_status": False}).headers
