"""Per-call limits for shared servers: timeout into a job, megapixels, pages and per-workspace concurrency."""

import asyncio
import json
import time

import pytest

from vixl import Project
from vixl.call_limits import GATE, CallLimits, check_export
from vixl.errors import VixlError
from vixl.interfaces import Session
from vixl.model import Limits


def paged(path, pages=3, size=(400, 300)):
    project = Project(*size)
    project.apply([{"type": "page", "action": "add", "name": f"p{i}"} for i in range(pages)])
    project.save(path)
    return path


def client(path, call_limits):
    from fastapi.testclient import TestClient

    from vixl.interfaces import create_app

    return TestClient(create_app(path, call_limits=call_limits))


def test_configure_reads_flags_then_environment():
    env = {"VIXL_CALL_TIMEOUT": "5", "VIXL_MAX_MEGAPIXELS": "12.5", "VIXL_MAX_PAGES": "20",
           "VIXL_MAX_CONCURRENT": "2"}
    limits = CallLimits.configure(env, max_pages=4)
    assert limits == CallLimits(timeout=5.0, max_megapixels=12.5, max_pages=4, max_concurrent=2)
    assert CallLimits.configure({}) == CallLimits() and not CallLimits().any()
    with pytest.raises(VixlError, match="VIXL_MAX_PAGES must be a whole number"):
        CallLimits.configure({"VIXL_MAX_PAGES": "lots"})
    with pytest.raises(VixlError, match="--max-concurrent must be positive"):
        CallLimits.configure({}, max_concurrent=0)
    lowered = CallLimits(max_megapixels=2).apply_to(Limits())
    assert lowered.max_pixels == 2_000_000
    assert CallLimits(max_megapixels=500).apply_to(Limits()).max_pixels == Limits().max_pixels
    described = limits.describe()
    assert described["max_concurrent_per_workspace"] == 2
    assert described["configure"]["timeout"] == {"flag": "--call-timeout", "env": "VIXL_CALL_TIMEOUT"}


def test_export_preflight_counts_pages_and_pixels(tmp_path):
    project = Project.load(paged(tmp_path / "deck.vixl", pages=3))
    check_export(CallLimits(max_pages=3), project, "PDF", {})
    with pytest.raises(VixlError) as caught:
        check_export(CallLimits(max_pages=2), project, "PDF", {})
    assert caught.value.code == "limit_exceeded" and caught.value.details["limit"] == "max_pages"
    assert caught.value.details["value"] == 3 and caught.value.details["hint"]
    check_export(CallLimits(max_pages=2), project, "PDF", {"pages": "1-2"})
    check_export(CallLimits(max_pages=1), project, "PNG", {})  # one page as an image
    with pytest.raises(VixlError, match="writes 3 pages"):
        check_export(CallLimits(max_pages=2), project, "PNG", {"page": "all"})  # contact sheet
    # 400 × 300 × 2² = 0.48 MP per page; three raster pages need 1.44 MP.
    check_export(CallLimits(max_megapixels=0.5), project, "PNG", {"scale": 2})
    with pytest.raises(VixlError) as caught:
        check_export(CallLimits(max_megapixels=1), project, "PDF", {"scale": 2, "pdf_content": "raster"})
    assert caught.value.details["limit"] == "max_megapixels" and caught.value.details["value"] == 1.44
    check_export(CallLimits(max_megapixels=0.2), project, "PDF", {})  # vector pages render no pixels here


def test_rest_export_limits_answer_structured_errors(tmp_path):
    path = paged(tmp_path / "deck.vixl", pages=3, size=(1000, 1000))
    api = client(path, CallLimits(max_pages=2, max_megapixels=2))
    response = api.post("/export", json={"format": "PDF"})
    assert response.status_code == 413
    assert response.json()["error"] == "limit_exceeded" and response.json()["limit"] == "max_pages"
    response = api.post("/export", json={"format": "PNG", "scale": 2})
    assert response.status_code == 413 and response.json()["limit"] == "max_megapixels"
    assert api.post("/export", json={"format": "PNG"}).status_code == 200
    info = api.get("/limits").json()
    assert info["max_pages"] == 2 and info["max_megapixels"] == 2 and info["max_pixels"] == 2_000_000


def test_rest_concurrency_cap_refuses_with_429(tmp_path):
    path = paged(tmp_path / "doc.vixl", pages=1)
    api = client(path, CallLimits(max_concurrent=1))
    held = GATE.acquire(tmp_path, 1)  # another heavy call is running in this workspace
    try:
        response = api.post("/check", json={})
        assert response.status_code == 429 and response.headers["retry-after"] == "3"
        assert response.json()["limit"] == "max_concurrent"
        assert api.get("/document").status_code == 200  # light calls are not counted
    finally:
        GATE.release(held)
    assert api.post("/check", json={}).status_code == 200


def test_rest_call_over_the_timeout_continues_as_a_job(tmp_path, monkeypatch):
    path = paged(tmp_path / "doc.vixl", pages=1)

    def slow_check(self, document=None, **options):
        time.sleep(0.6)
        return {"passed": True, "slow": True}

    monkeypatch.setattr(Session, "check", slow_check)
    api = client(path, CallLimits(timeout=0.1))
    response = api.post("/check", json={})
    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "running" and response.headers["location"] == f"/jobs/{body['job']}"
    early = api.get(f"/jobs/{body['job']}/result")
    assert early.status_code in (200, 409)
    status = api.get(f"/jobs/{body['job']}", params={"wait": 10}).json()
    assert status["status"] == "completed"
    assert api.get(f"/jobs/{body['job']}/result").json() == {"passed": True, "slow": True}
    assert body["job"] in [job["id"] for job in api.get("/jobs").json()["jobs"]]
    assert api.get("/jobs/nope").status_code == 400


def mcp(session):
    from vixl.mcp_tools import build_server

    server = build_server(session)

    def call(name, **arguments):
        result = asyncio.run(server.call_tool(name, arguments))
        content = result[0] if isinstance(result, tuple) else result
        return json.loads(content[0].text)

    return server, call


def test_mcp_applies_the_same_limits(tmp_path):
    paged(tmp_path / "deck.vixl", pages=3)
    session = Session(workspace=tmp_path)
    session.call_limits = CallLimits(timeout=7, max_pages=2, max_concurrent=1)
    server, call = mcp(session)
    assert server.vixl_runtime.inline_seconds == 7
    call("vixl_document_open", path="deck.vixl")
    with pytest.raises(Exception) as caught:
        call("vixl_export_file", path="deck.pdf")
    assert '"limit_exceeded"' in str(caught.value) and "max_pages" in str(caught.value)
    assert call("vixl_export_file", path="two.pdf", pages="1-2")["format"] == "PDF"
    held = GATE.acquire(tmp_path, 1)
    try:
        with pytest.raises(Exception, match="max_concurrent"):
            call("vixl_check")
        assert call("vixl_document_inspect")  # light tools still answer
    finally:
        GATE.release(held)
    assert call("vixl_check")["passed"] in (True, False)
    listed = call("vixl_job", action="list")
    assert listed["limits"]["max_pages"] == 2 and listed["limits"]["timeout_s"] == 7


def test_serve_and_mcp_accept_limit_flags():
    from vixl.call_limits import add_arguments, from_arguments
    from vixl.commands import Parser

    parser = Parser(prog="vixl serve")
    add_arguments(parser)
    parsed = parser.parse_args(["--call-timeout", "30", "--max-megapixels", "25", "--max-pages", "50",
                                "--max-concurrent", "4"])
    assert from_arguments(parsed) == CallLimits(timeout=30, max_megapixels=25, max_pages=50, max_concurrent=4)
