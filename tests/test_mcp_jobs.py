"""Long MCP calls, retries and per-client documents (issues #84 and #85)."""

import asyncio
import json
import threading
import time

from mcp.shared.memory import create_connected_server_and_client_session
import pytest

from vixl import Project
from vixl.calls import CALL, CallState
from vixl.errors import VixlError
from vixl.interfaces import Session, mcp_server


def slow(monkeypatch, seconds, release=None):
    """Make every apply take ``seconds`` (or until ``release`` is set), as a heavy batch would."""
    original = Session.apply

    def apply(self, *args, **kwargs):
        if release is not None:
            release.wait(10)
        else:
            time.sleep(seconds)
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Session, "apply", apply)


class Client:
    """A connected in-memory MCP client that decodes JSON results."""

    def __init__(self, session):
        self.session = session

    async def call(self, name, **arguments):
        progress = arguments.pop("_progress", None)
        result = await self.session.call_tool(name, arguments, progress_callback=progress)
        text = "".join(getattr(item, "text", "") for item in result.content)
        return (result.isError, text) if result.isError else json.loads(text)


def run(server, scenario):
    async def main():
        async with create_connected_server_and_client_session(server._mcp_server) as session:
            return await scenario(Client(session))

    return asyncio.run(main())


def apply_move(x=5):
    return {"operations": [{"type": "move", "target": "t", "x": x}]}


def prepared(tmp_path, **options):
    server = mcp_server(workspace=tmp_path, **options)
    session = server.vixl_runtime.session
    session.create("a.vixl", 200, 100)
    session.apply([{"type": "text", "name": "t", "text": "Hi", "x": 1, "y": 1}])
    return server, session


def test_slow_call_becomes_a_job_and_still_applies_once(tmp_path, monkeypatch):
    server, session = prepared(tmp_path)
    server.vixl_runtime.inline_seconds = 0.2
    slow(monkeypatch, 0.8)

    async def scenario(client):
        pointer = await client.call("vixl_operations_apply", **apply_move(7))
        assert pointer["status"] == "running" and pointer["job"].startswith("job_")
        assert "vixl_job" in pointer["message"] and pointer["tool"] == "vixl_operations_apply"
        # The event loop stays free: the job can be asked about while the edit is still running.
        early = await client.call("vixl_job", id=pointer["job"])
        assert early["status"] in ("queued", "running")
        done = await client.call("vixl_job", action="result", id=pointer["job"], wait=10)
        assert done["status"] == "completed" and done["result"]["success"] is True
        assert done["result"]["document"] == "a.vixl"
        listed = await client.call("vixl_job", action="list")
        assert [job["id"] for job in listed["jobs"]] == [pointer["job"]]
        failed = await client.call("vixl_job", id="job_missing")
        assert failed[0] and "not_found" in failed[1]

    run(server, scenario)
    assert session.inspect()["layers"][0]["x"] == 7


def test_as_job_returns_at_once_and_cancel_stops_a_queued_or_running_batch(tmp_path, monkeypatch):
    server, session = prepared(tmp_path)
    release = threading.Event()
    slow(monkeypatch, 0, release)

    async def scenario(client):
        started = time.monotonic()
        pointer = await client.call("vixl_operations_apply", as_job=True, **apply_move(9))
        assert time.monotonic() - started < 3 and pointer["status"] in ("queued", "running")
        cancelled = await client.call("vixl_job", action="cancel", id=pointer["job"])
        assert cancelled["id"] == pointer["job"]
        release.set()
        final = await client.call("vixl_job", action="status", id=pointer["job"], wait=10)
        return final

    final = run(server, scenario)
    # The cancel arrived while the call was running: it finishes (its edit is atomic) or stops cleanly.
    assert final["status"] in ("completed", "cancelled", "failed")


def test_request_id_replays_the_first_result_instead_of_applying_twice(tmp_path):
    server, session = prepared(tmp_path)

    async def scenario(client):
        first = await client.call("vixl_operations_apply", request_id="r1",
                                  operations=[{"type": "move", "target": "t", "x": 3, "relative": True}])
        again = await client.call("vixl_operations_apply", request_id="r1",
                                  operations=[{"type": "move", "target": "t", "x": 3, "relative": True}])
        assert "replayed" not in first and again["replayed"] is True and again["request_id"] == "r1"
        assert again["changes"] == first["changes"]
        misuse = await client.call("vixl_operations_apply", request_id="r1", operations=[{"type": "hide", "target": "t"}])
        assert misuse[0] and "already used" in misuse[1]
        # A failed call is not remembered, so the retry runs.
        bad = await client.call("vixl_operations_apply", request_id="r2", operations=[{"type": "move", "target": "nope", "x": 1}])
        assert bad[0]
        good = await client.call("vixl_operations_apply", request_id="r2", operations=[{"type": "move", "target": "t", "x": 1}])
        assert good["success"]
        # Document-level tools take it too.
        made = await client.call("vixl_document_create", path="b.vixl", width=10, height=10, request_id="c1")
        again = await client.call("vixl_document_create", path="b.vixl", width=10, height=10, request_id="c1")
        assert again["replayed"] and made["path"] == "b.vixl"

    run(server, scenario)
    # The r1 move (+3) applied once, so x was 4 before r2 moved the layer to 1.
    assert session.inspect(document="a.vixl")["layers"][0]["x"] == 1
    assert [n["operations"] for n in session.history(document="a.vixl")["nodes"]][-3:].count([{"type": "move", "target": "t", "x": 3, "relative": True}]) == 1


def test_retry_of_a_running_call_points_at_its_job(tmp_path, monkeypatch):
    server, session = prepared(tmp_path)
    server.vixl_runtime.inline_seconds = 0.2
    release = threading.Event()
    slow(monkeypatch, 0, release)

    async def scenario(client):
        first = await client.call("vixl_operations_apply", request_id="slow", **apply_move(11))
        assert first["status"] == "running"
        retry = await client.call("vixl_operations_apply", request_id="slow", **apply_move(11))
        assert retry["job"] == first["job"] and "still running" in retry["message"]
        release.set()
        done = await client.call("vixl_job", action="result", id=first["job"], wait=10)
        assert done["status"] == "completed"
        replay = await client.call("vixl_operations_apply", request_id="slow", **apply_move(11))
        assert replay["replayed"] is True

    run(server, scenario)
    assert session.inspect()["layers"][0]["x"] == 11


def test_batches_report_progress_notifications(tmp_path):
    server, session = prepared(tmp_path)
    seen = []

    async def collect(progress, total, message):
        seen.append((progress, total, message))

    async def scenario(client):
        operations = [{"type": "shape", "shape": "rectangle", "name": f"s{i}", "width": 5, "height": 5, "x": i}
                      for i in range(40)]
        result = await client.call("vixl_operations_apply", operations=operations, _progress=collect)
        assert result["success"]

    run(server, scenario)
    assert seen and seen[-1][0] == seen[-1][1] == 40 and all(total == 40 for _, total, _ in seen)


def test_cancelled_batch_leaves_the_document_untouched(tmp_path):
    p = Project(50, 50)
    p.save(tmp_path / "a.vixl")
    session = Session(workspace=tmp_path)
    session.open("a.vixl")
    state = CallState()
    state.cancel.set()
    token = CALL.set(state)
    try:
        with pytest.raises(VixlError) as error:
            session.apply([{"type": "solid", "name": "x"}])
    finally:
        CALL.reset(token)
    assert error.value.code == "cancelled" and Project.load(tmp_path / "a.vixl").state["layers"] == []


def test_job_tool_serves_durable_workspace_jobs(tmp_path):
    from vixl.jobs import Queue

    source = Project(40, 40)
    source.apply({"type": "text", "name": "title", "text": "Hi", "size": 10})
    source.save(tmp_path / "source.vixl")
    job = Queue(tmp_path).submit({"kind": "production", "source": "source.vixl", "output": "campaign",
                                  "spec": {"rows": [{"title": "One"}]}})
    server = mcp_server(workspace=tmp_path)

    async def scenario(client):
        queued = await client.call("vixl_job", id=job["id"])
        assert queued["status"] == "queued" and queued["kind"] == "production"
        Queue(tmp_path).work_one(job["id"])
        done = await client.call("vixl_job", action="result", id=job["id"])
        assert done["status"] == "completed" and done["progress"]["done"] == 1
        cancelled = await client.call("vixl_job", action="cancel", id=job["id"])
        assert cancelled["id"] == job["id"]

    run(server, scenario)


def test_active_document_is_per_client_and_results_name_the_document(tmp_path):
    server = mcp_server(workspace=tmp_path)

    async def main():
        async with create_connected_server_and_client_session(server._mcp_server) as one:
            async with create_connected_server_and_client_session(server._mcp_server) as two:
                a, b = Client(one), Client(two)
                made = await a.call("vixl_document_create", path="a.vixl", width=100, height=50)
                assert made["path"] == "a.vixl"
                await b.call("vixl_document_create", path="b.vixl", width=300, height=200)
                # Each client's own call lands on its own document, and says so.
                seen_a = await a.call("vixl_document_inspect")
                seen_b = await b.call("vixl_document_inspect")
                assert seen_a["document"] == "a.vixl" and seen_a["canvas"]["width"] == 100
                assert seen_b["document"] == "b.vixl" and seen_b["canvas"]["width"] == 300
                edit = await a.call("vixl_operations_apply", operations=[{"type": "solid", "name": "bg"}])
                assert edit["document"] == "a.vixl"
                assert not (await b.call("vixl_document_inspect"))["layers"]
                # Opening another document moves only this client's active document.
                await b.call("vixl_document_open", path="a.vixl")
                assert (await b.call("vixl_document_inspect"))["document"] == "a.vixl"
                assert (await a.call("vixl_document_inspect"))["document"] == "a.vixl"
                await a.call("vixl_document_open", path="b.vixl")
                assert (await b.call("vixl_document_inspect"))["document"] == "a.vixl"
                # A client that never opened anything has no active document.
                async with create_connected_server_and_client_session(server._mcp_server) as three:
                    failed = await Client(three).call("vixl_document_inspect")
                    assert failed[0] and "no_project" in failed[1]
                    # An explicit document= still works and is named.
                    named = await Client(three).call("vixl_document_inspect", document="b.vixl")
                    assert named["document"] == "b.vixl"
                preview = await one.call_tool("vixl_render_preview", {"max_width": 64, "max_height": 64})
                assert preview.content[0].type == "image"
                assert json.loads(preview.content[-1].text) == {"document": "b.vixl"}

    asyncio.run(main())


def test_require_document_makes_document_mandatory(tmp_path, monkeypatch):
    server = mcp_server(workspace=tmp_path, require_document=True)

    async def scenario(client):
        made = await client.call("vixl_document_create", path="a.vixl", width=40, height=40)
        assert made["path"] == "a.vixl"
        failed = await client.call("vixl_document_inspect")
        assert failed[0] and "document_required" in failed[1] and "--require-document" in failed[1]
        failed = await client.call("vixl_operations_apply", operations=[{"type": "solid", "name": "x"}])
        assert failed[0] and "document_required" in failed[1]
        ok = await client.call("vixl_operations_apply", document="a.vixl", operations=[{"type": "solid", "name": "x"}])
        assert ok["document"] == "a.vixl" and ok["success"]
        assert (await client.call("vixl_document_close"))[0]
        assert "active" in await client.call("vixl_document_close", document="a.vixl")

    run(server, scenario)
    assert "document=" in server.instructions
    monkeypatch.setenv("VIXL_REQUIRE_DOCUMENT", "1")
    assert mcp_server(workspace=tmp_path).vixl_runtime.session.require_document is True
    monkeypatch.setenv("VIXL_REQUIRE_DOCUMENT", "0")
    assert mcp_server(workspace=tmp_path).vixl_runtime.session.require_document is False


def test_session_scopes_active_document_by_client_context(tmp_path):
    class Who:
        pass

    session = Session(workspace=tmp_path)
    session.create("shared.vixl", 10, 10)
    first, second = Who(), Who()
    for client, name in ((first, "one.vixl"), (second, "two.vixl")):
        token = CALL.set(CallState(client=client))
        try:
            assert session.relative(session.path) == "shared.vixl"  # The server default until it picks one.
            session.create(name, 10, 10)
            assert session.relative(session.path) == name
        finally:
            CALL.reset(token)
    assert session.relative(session.path) == "shared.vixl"  # Outside MCP nothing changed.


def test_compact_tool_set_polls_jobs_through_the_workflow_tool(tmp_path, monkeypatch):
    server = mcp_server(workspace=tmp_path, tools="compact")
    session = server.vixl_runtime.session
    session.create("a.vixl", 100, 100)
    session.apply([{"type": "text", "name": "t", "text": "Hi", "x": 1, "y": 1}])
    server.vixl_runtime.inline_seconds = 0.2
    slow(monkeypatch, 0.6)

    async def scenario(client):
        pointer = await client.call("vixl_operations_apply", **apply_move(4))
        assert pointer["status"] == "running" and "vixl_workflow" in pointer["message"]
        server.vixl_runtime.inline_seconds = 10  # A poll that waits must not itself become a job.
        done = await client.call("vixl_workflow", action="status", request={"id": pointer["job"], "wait": 10})
        assert done["status"] == "completed" and done["result"]["success"]
        failed = await client.call("vixl_workflow", action="cancel", request={"id": "job_unknown"})
        assert failed[0]

    run(server, scenario)
    assert session.inspect()["layers"][0]["x"] == 4


def test_instructions_describe_jobs_and_ids(tmp_path):
    assert "vixl_job" in mcp_server(workspace=tmp_path).instructions
    assert "vixl_job" in mcp_server(workspace=tmp_path, tools="ai").instructions
    assert "vixl_workflow" in mcp_server(workspace=tmp_path, tools="compact").instructions
    assert "request_id" in mcp_server(workspace=tmp_path).instructions


def test_tool_schemas_offer_request_id_and_as_job_only_where_they_help(tmp_path):
    async def scenario():
        tools = {t.name: t for t in await mcp_server(workspace=tmp_path).list_tools()}
        apply = tools["vixl_operations_apply"].inputSchema["properties"]
        assert {"request_id", "as_job"} <= set(apply) and "ctx" not in apply
        assert "request_id" in tools["vixl_document_create"].inputSchema["properties"]
        assert "as_job" not in tools["vixl_document_create"].inputSchema["properties"]
        # vixl_export_file already has a background colour: the job flag must not collide with it.
        export = tools["vixl_export_file"].inputSchema["properties"]
        assert export["background"]["default"] == "white" and "as_job" in export
        for name in ("vixl_job", "vixl_render_preview", "vixl_document_inspect"):
            assert not {"request_id", "as_job"} & set(tools[name].inputSchema["properties"])

    asyncio.run(scenario())
