"""Every heavy service path goes through the call limiter (#821, #823, #826, #828)."""

import asyncio
import io
import json
import threading
import time
from types import SimpleNamespace

import pytest

from vixl import Project, mcp_runtime
from vixl.call_limits import GATE, CallLimits
from vixl.errors import VixlError
from vixl.mcp_runtime import Job, JobStore, Runtime
from vixl.model import Limits

pytest.importorskip("fastapi")

TOKEN = "t" * 32
AUTH = {"Authorization": f"Bearer {TOKEN}"}
SVG = (b'<svg xmlns="http://www.w3.org/2000/svg" width="40" height="20"><rect id="bar" width="40" height="20" '
       b'fill="#123456"/></svg>')


def png(size=(8, 6)):
    from PIL import Image

    stream = io.BytesIO()
    Image.new("RGB", size, "#2c5aa0").save(stream, format="PNG")
    return stream.getvalue()


def rest(tmp_path, call_limits):
    from fastapi.testclient import TestClient

    from vixl.interfaces import create_app

    path = tmp_path / "doc.vixl"
    Project(200, 120).save(path)
    return TestClient(create_app(path, call_limits=call_limits))


def host(tmp_path, call_limits):
    from fastapi.testclient import TestClient

    from vixl.host import create_host_app

    client = TestClient(create_host_app(tmp_path / "root", TOKEN, call_limits=call_limits), headers=AUTH)
    made = client.post("/w/team/documents", json={"width": 200, "height": 120, "workspace_fonts": False})
    assert made.status_code == 201, made.text
    return client, made.json()["id"]


def slow(monkeypatch, module, name, seconds=0.5):
    """Make ``module.name`` take ``seconds`` longer, as a decoder or parser fed a hostile file would."""
    original = getattr(module, name)

    def delayed(*args, **kwargs):
        time.sleep(seconds)
        return original(*args, **kwargs)

    monkeypatch.setattr(module, name, delayed)


# ------------------------------------------------------------------------------------- #821 REST and Host imports


def test_rest_imports_and_uploads_count_against_max_concurrent(tmp_path):
    api = rest(tmp_path, CallLimits(max_concurrent=1))
    calls = (("/import?format=svg&name=logo", SVG), ("/assets?name=photo", png()), ("/fonts?name=face", b"x"))
    held = GATE.acquire(tmp_path, 1)  # another heavy call is running in this workspace
    try:
        for url, body in calls:
            refused = api.post(url, content=body)
            assert refused.status_code == 429 and refused.json()["limit"] == "max_concurrent", url
    finally:
        GATE.release(held)
    assert api.post(*calls[0][:1], content=SVG).status_code == 200
    assert api.post(calls[1][0], content=png()).status_code == 200
    assert len(api.get("/layers").json()) >= 2


def test_two_rest_imports_never_run_at_once(tmp_path, monkeypatch):
    from vixl import svg_import

    running, peak, lock = [], [], threading.Lock()
    original = svg_import.svg_operations

    def counted(*args, **kwargs):
        with lock:
            running.append(1)
            peak.append(len(running))
        try:
            time.sleep(0.3)
            return original(*args, **kwargs)
        finally:
            with lock:
                running.pop()

    monkeypatch.setattr(svg_import, "svg_operations", counted)
    api = rest(tmp_path, CallLimits(max_concurrent=1))
    statuses = []
    threads = [threading.Thread(target=lambda: statuses.append(
        api.post("/import?format=svg&name=logo", content=SVG).status_code)) for _ in range(3)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(20)
    assert max(peak) == 1 and 200 in statuses and set(statuses) <= {200, 429}


def test_slow_rest_decoders_hit_the_hard_timeout(tmp_path, monkeypatch):
    from vixl import image_import, svg_import

    slow(monkeypatch, image_import, "add_encoded")
    slow(monkeypatch, svg_import, "svg_operations")
    api = rest(tmp_path, CallLimits(hard_timeout=0.1))
    for url, body in (("/assets?name=photo", png()), ("/import?format=svg&name=logo", SVG)):
        stopped = api.post(url, content=body)
        assert stopped.status_code == 400, stopped.text
        assert stopped.json()["error"] == "cancelled" and "hard timeout" in stopped.json()["message"], url
    assert api.get("/layers").json() == []  # nothing was applied


def test_slow_rest_import_continues_as_a_job(tmp_path, monkeypatch):
    from vixl import image_import

    slow(monkeypatch, image_import, "add_encoded", 0.4)
    api = rest(tmp_path, CallLimits(timeout=0.05))
    detached = api.post("/assets?name=photo", content=png())
    assert detached.status_code == 202 and detached.json()["route"] == "assets"
    job = detached.json()["job"]
    assert api.get(f"/jobs/{job}", params={"wait": 10}).json()["status"] == "completed"
    assert api.get(f"/jobs/{job}/result").json()["name"] == "photo"


def test_host_assets_and_imports_are_heavy_calls(tmp_path, monkeypatch):
    from vixl import image_import, svg_import

    client, doc = host(tmp_path, CallLimits(max_concurrent=1, hard_timeout=0.1))
    calls = ((f"/w/team/documents/{doc}/assets?name=photo", png()),
             (f"/w/team/documents/{doc}/import?format=svg&name=logo", SVG))
    held = GATE.acquire(tmp_path / "root" / "team", 1)
    try:
        for url, body in calls:
            refused = client.post(url, content=body)
            assert refused.status_code == 429, (url, refused.text)
    finally:
        GATE.release(held)
    slow(monkeypatch, image_import, "add_encoded")
    slow(monkeypatch, svg_import, "svg_operations")
    for url, body in calls:
        stopped = client.post(url, content=body)
        assert stopped.status_code >= 400 and "hard timeout" in stopped.text, (url, stopped.text)
    assert client.get(f"/w/team/documents/{doc}").json()["revision"] == 1  # nothing was applied


# ------------------------------------------------------------------------------------- #828 MCP renders and the gate


def runtime(monkeypatch, tmp_path=None, *, workers=4, queue=None, inline_seconds=2, call_limits=None):
    monkeypatch.setenv("VIXL_MCP_WORKERS", str(workers))
    if queue is not None:
        monkeypatch.setenv("VIXL_MCP_QUEUE", str(queue))
    session = SimpleNamespace(workspace=tmp_path, call_limits=call_limits or CallLimits())
    return Runtime(session, json.dumps, RuntimeError, inline_seconds=inline_seconds)


def test_render_takes_the_workspace_gate_without_becoming_a_job_tool():
    assert mcp_runtime.takes_gate("vixl_render") and not mcp_runtime.takes_job("vixl_render")
    assert mcp_runtime.takes_gate("vixl_export") and mcp_runtime.takes_gate("vixl_ai_generate")
    assert not mcp_runtime.takes_gate("vixl_job") and not mcp_runtime.takes_gate("vixl_document")


def test_two_mcp_renders_on_different_documents_never_run_at_once(tmp_path, monkeypatch):
    rt = runtime(monkeypatch, tmp_path, call_limits=CallLimits(max_concurrent=1))
    running, peak, lock = [], [], threading.Lock()

    def vixl_render(document: str | None = None) -> dict:
        with lock:
            running.append(document)
            peak.append(len(running))
        time.sleep(0.2)
        with lock:
            running.remove(document)
        return {"rendered": document}

    tool = rt.wrap(vixl_render)

    async def scenario():
        return await asyncio.gather(*(tool(document=f"{name}.vixl") for name in "abc"))

    results = [json.loads(text)["rendered"] for text in asyncio.run(scenario())]
    assert results == ["a.vixl", "b.vixl", "c.vixl"]  # each waited for its turn instead of being refused
    assert max(peak) == 1
    assert rt.in_flight == 0 and GATE.running == {}


def test_a_render_that_finds_no_slot_within_the_inline_time_is_refused_as_busy(tmp_path, monkeypatch):
    rt = runtime(monkeypatch, tmp_path, inline_seconds=0.2, call_limits=CallLimits(max_concurrent=1))
    ran = []

    def vixl_render(document: str | None = None) -> dict:
        ran.append(document)
        return {}

    def vixl_check(document: str | None = None) -> dict:
        ran.append("check")
        return {}

    held = GATE.acquire(tmp_path, 1)
    try:
        started = time.monotonic()
        with pytest.raises(RuntimeError) as caught:
            asyncio.run(rt.wrap(vixl_render)())
        waited = time.monotonic() - started
        error = json.loads(str(caught.value))
        assert error["limit"] == "max_concurrent" and error["retryable"] is True and 0.2 <= waited < 5
        started = time.monotonic()
        with pytest.raises(RuntimeError, match="max_concurrent"):  # a job tool is still refused at once
            asyncio.run(rt.wrap(vixl_check)())
        assert time.monotonic() - started < 0.15
    finally:
        GATE.release(held)
    assert ran == [] and rt.in_flight == 0
    asyncio.run(rt.wrap(vixl_render)(document="a.vixl"))
    assert ran == ["a.vixl"]


def test_renders_are_not_gated_without_max_concurrent(tmp_path, monkeypatch):
    rt = runtime(monkeypatch, tmp_path)
    held = GATE.acquire(tmp_path, 1)
    try:
        def vixl_render() -> dict:
            return {"ok": True}

        assert json.loads(asyncio.run(rt.wrap(vixl_render)())) == {"ok": True}
    finally:
        GATE.release(held)


# ------------------------------------------------------------------------------------- #823 MCP queue and job store


def blocking(release, name="vixl_export"):
    def tool(document: str | None = None) -> dict:
        release.wait(10)
        return {"ok": True}

    tool.__name__ = name
    return tool


def test_mcp_refuses_calls_past_its_queue_with_a_retryable_busy_error(monkeypatch):
    rt = runtime(monkeypatch, workers=1, queue=2, inline_seconds=0.05)
    assert rt.capacity == 3
    release = threading.Event()
    tool = rt.wrap(blocking(release))

    async def scenario():
        held = [json.loads(await tool()) for _ in range(3)]  # one running, two waiting: all became jobs
        refused = []
        for _ in range(4):
            try:
                await tool()
            except RuntimeError as exc:
                refused.append(json.loads(str(exc)))
        assert rt.in_flight == 3 and rt.queue_depth() == 2
        status = json.loads(await rt.wrap(job_tool(rt))(action="list"))  # polling is not queued behind the calls
        release.set()
        for pointer in held:
            await asyncio.to_thread(rt.jobs.get(pointer["job"]).done.wait, 10)
        after = json.loads(await tool())
        return held, refused, status, after

    held, refused, status, after = asyncio.run(scenario())
    assert [pointer["status"] for pointer in held] == ["running", "queued", "queued"]
    assert len(refused) == 4
    for error in refused:
        assert error["error"] == "limit_exceeded" and error["limit"] == "max_queue"
        assert error["retryable"] is True and error["maximum"] == 3
    assert len(status["jobs"]) == 3
    assert after == {"ok": True} and rt.in_flight == 0


def job_tool(rt):
    def vixl_job(action: str = "status", id: str | None = None, wait: float = 0) -> dict:
        return rt.job(action, id, wait)

    return vixl_job


def test_the_job_store_never_exceeds_its_maximum(monkeypatch):
    monkeypatch.setattr(mcp_runtime, "MAX_JOBS", 3)
    rt = runtime(monkeypatch, workers=8, queue=64)
    assert rt.capacity == 3  # every held call may become a job, so no more than the store remembers
    release = threading.Event()
    tool = rt.wrap(blocking(release))

    async def scenario():
        pointers = [json.loads(await tool(as_job=True)) for _ in range(3)]
        for _ in range(5):
            with pytest.raises(RuntimeError, match="max_queue"):
                await tool(as_job=True)
        assert len(rt.jobs.jobs) == 3
        release.set()
        for pointer in pointers:
            await asyncio.to_thread(rt.jobs.get(pointer["job"]).done.wait, 10)
        for _ in range(10):  # finished jobs make room; the store stays at its maximum
            pointer = json.loads(await tool(as_job=True))
            await asyncio.to_thread(rt.jobs.get(pointer["job"]).done.wait, 10)
            assert len(rt.jobs.jobs) <= 3
        return pointers

    pointers = asyncio.run(scenario())
    assert rt.jobs.get(pointers[0]["job"]) is None  # the oldest finished job was forgotten


def test_a_store_full_of_unfinished_jobs_refuses_the_next_one():
    from concurrent.futures import Future

    store = JobStore(maximum=2)
    box = SimpleNamespace(started=None, submitted=None, progress=None)
    futures = [Future() for _ in range(3)]
    first = store.add(Job("vixl_export", None, None, futures[0], box))
    store.add(Job("vixl_export", None, None, futures[1], box))
    with pytest.raises(VixlError) as caught:
        store.add(Job("vixl_export", None, None, futures[2], box))
    assert caught.value.details["limit"] == "max_queue" and caught.value.details["retryable"] is True
    assert len(store.jobs) == 2
    futures[0].set_result("{}")
    store.add(Job("vixl_export", None, None, futures[2], box))
    assert len(store.jobs) == 2 and store.get(first.id) is None


# ------------------------------------------------------------------------------------- #826 MCP HTTP body limit


def test_mcp_http_refuses_an_oversized_body_before_the_sdk_reads_it(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from vixl.interfaces import mcp_http_app, mcp_server

    server = mcp_server(workspace=tmp_path)
    app = mcp_http_app(server, token=TOKEN, max_body_bytes=2048)
    reached = []
    handle = server.session_manager.handle_request

    async def spy(scope, receive, send):
        reached.append(scope["path"])
        return await handle(scope, receive, send)

    monkeypatch.setattr(server.session_manager, "handle_request", spy)
    headers = {**AUTH, "Accept": "application/json, text/event-stream", "Content-Type": "application/json"}
    message = {"jsonrpc": "2.0", "id": 1, "method": "initialize",
               "params": {"protocolVersion": "2025-03-26", "capabilities": {},
                          "clientInfo": {"name": "test", "version": "1"}}}
    huge = json.dumps({**message, "padding": "x" * 4096}).encode()
    with TestClient(app) as client:
        declared = client.post("/mcp", content=huge, headers=headers)
        assert declared.status_code == 413 and declared.json()["error"] == "resource_limit"
        assert declared.json()["limit"] == 2048
        streamed = client.post("/mcp", content=iter([huge[:1000], huge[1000:]]), headers=headers)  # no Content-Length
        assert streamed.status_code == 413
        assert reached == []
        # An unauthorized caller is refused before its body is read or measured.
        assert client.post("/mcp", content=huge, headers={"Content-Type": "application/json"}).status_code == 401
        assert client.post("/mcp", json=message, headers=headers).status_code == 200
        assert reached == ["/mcp"]


def test_mcp_body_limit_follows_the_asset_limit_and_the_environment():
    from vixl.interfaces import mcp_body_limit

    default = mcp_body_limit(Limits(), environ={})
    assert default > Limits().max_asset_bytes * 4 // 3  # room for the largest inline data_base64 upload
    assert mcp_body_limit(Limits(max_asset_bytes=3_000_000), environ={}) == 4_000_000 + 1024 * 1024
    assert mcp_body_limit(Limits(), environ={"VIXL_MCP_MAX_BODY_BYTES": "5000"}) == 5000
    for bad in ("0", "lots", "-1"):
        with pytest.raises(VixlError):
            mcp_body_limit(Limits(), environ={"VIXL_MCP_MAX_BODY_BYTES": bad})
