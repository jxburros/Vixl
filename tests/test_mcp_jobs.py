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
        pointer = await client.call("vixl_apply", **apply_move(7))
        assert pointer["status"] == "running" and pointer["job"].startswith("job_")
        assert "vixl_job" in pointer["message"] and pointer["tool"] == "vixl_apply"
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
        pointer = await client.call("vixl_apply", as_job=True, **apply_move(9))
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
        first = await client.call("vixl_apply", request_id="r1",
                                  operations=[{"type": "move", "target": "t", "x": 3, "relative": True}])
        again = await client.call("vixl_apply", request_id="r1",
                                  operations=[{"type": "move", "target": "t", "x": 3, "relative": True}])
        assert "replayed" not in first and again["replayed"] is True and again["request_id"] == "r1"
        assert again["changes"] == first["changes"]
        misuse = await client.call("vixl_apply", request_id="r1", operations=[{"type": "hide", "target": "t"}])
        assert misuse[0] and "already used" in misuse[1]
        # A failed call is not remembered, so the retry runs.
        bad = await client.call("vixl_apply", request_id="r2", operations=[{"type": "move", "target": "nope", "x": 1}])
        assert bad[0]
        good = await client.call("vixl_apply", request_id="r2", operations=[{"type": "move", "target": "t", "x": 1}])
        assert good["success"]
        # Document-level tools take it too.
        made = await client.call("vixl_document", action="create", path="b.vixl", width=10, height=10, request_id="c1")
        again = await client.call("vixl_document", action="create", path="b.vixl", width=10, height=10, request_id="c1")
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
        first = await client.call("vixl_apply", request_id="slow", **apply_move(11))
        assert first["status"] == "running"
        retry = await client.call("vixl_apply", request_id="slow", **apply_move(11))
        assert retry["job"] == first["job"] and "still running" in retry["message"]
        release.set()
        done = await client.call("vixl_job", action="result", id=first["job"], wait=10)
        assert done["status"] == "completed"
        replay = await client.call("vixl_apply", request_id="slow", **apply_move(11))
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
        result = await client.call("vixl_apply", operations=operations, _progress=collect)
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
                made = await a.call("vixl_document", action="create", path="a.vixl", width=100, height=50)
                assert made["path"] == "a.vixl"
                await b.call("vixl_document", action="create", path="b.vixl", width=300, height=200)
                # Each client's own call lands on its own document, and says so.
                seen_a = await a.call("vixl_document")
                seen_b = await b.call("vixl_document")
                assert seen_a["document"] == "a.vixl" and seen_a["canvas"]["width"] == 100
                assert seen_b["document"] == "b.vixl" and seen_b["canvas"]["width"] == 300
                edit = await a.call("vixl_apply", operations=[{"type": "solid", "name": "bg"}])
                assert edit["document"] == "a.vixl"
                assert not (await b.call("vixl_document"))["layers"]
                # Opening another document moves only this client's active document, but a connection that has
                # touched two open documents cannot tell whose default it is, so document= becomes required.
                await b.call("vixl_document", action="open", path="a.vixl")
                refused = await b.call("vixl_document")
                assert refused[0] and "ambiguous_document" in refused[1]
                assert (await b.call("vixl_document", document="a.vixl"))["document"] == "a.vixl"
                assert (await a.call("vixl_document"))["document"] == "a.vixl"
                await a.call("vixl_document", action="open", path="b.vixl")
                assert (await a.call("vixl_document"))[0]
                # A client that never opened anything has no default once several documents are open.
                async with create_connected_server_and_client_session(server._mcp_server) as three:
                    failed = await Client(three).call("vixl_document")
                    assert failed[0] and "ambiguous_document" in failed[1]
                    # An explicit document= still works and is named.
                    named = await Client(three).call("vixl_document", document="b.vixl")
                    assert named["document"] == "b.vixl"
                preview = await one.call_tool("vixl_render", {"max_width": 64, "max_height": 64, "document": "b.vixl"})
                assert preview.content[0].type == "image"
                assert json.loads(preview.content[-1].text) == {"document": "b.vixl"}

    asyncio.run(main())


def test_require_document_makes_document_mandatory(tmp_path, monkeypatch):
    server = mcp_server(workspace=tmp_path, require_document=True)

    async def scenario(client):
        made = await client.call("vixl_document", action="create", path="a.vixl", width=40, height=40)
        assert made["path"] == "a.vixl"
        failed = await client.call("vixl_document")
        assert failed[0] and "document_required" in failed[1] and "--require-document" in failed[1]
        failed = await client.call("vixl_apply", operations=[{"type": "solid", "name": "x"}])
        assert failed[0] and "document_required" in failed[1]
        ok = await client.call("vixl_apply", document="a.vixl", operations=[{"type": "solid", "name": "x"}])
        assert ok["document"] == "a.vixl" and ok["success"]
        assert (await client.call("vixl_document", action="close"))[0]
        assert "active" in await client.call("vixl_document", action="close", document="a.vixl")

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


def test_agents_sharing_one_connection_must_name_the_document(tmp_path):
    # Subagents of one host share its MCP connection, so the server sees them as one client.
    server = mcp_server(workspace=tmp_path)
    session = server.vixl_runtime.session

    async def scenario(client):
        await client.call("vixl_document", action="create", path="poster.vixl", width=100, height=100)
        alone = await client.call("vixl_apply", operations=[{"type": "solid", "name": "bg"}])
        assert alone["success"] and alone["document"] == "poster.vixl"  # One open document: no document= needed.
        await client.call("vixl_document", action="create", path="infographic.vixl", width=200, height=100)
        refused = await client.call("vixl_apply", operations=[{"type": "solid", "name": "stray"}])
        assert refused[0]
        error = json.loads(refused[1][refused[1].index("{"):])
        assert error["error"] == "ambiguous_document" and error["field"] == "document"
        assert set(error["documents"]) == {"poster.vixl", "infographic.vixl"}
        assert "document='poster.vixl'" in error["suggestions"] and "document=" in error["message"]
        for tool, args in (("vixl_document", {}), ("vixl_render", {}), ("vixl_check", {}),
                           ("vixl_document", {"action": "close"})):
            assert (await client.call(tool, **args))[0], tool
        named = await client.call("vixl_apply", document="poster.vixl", operations=[{"type": "solid", "name": "mine"}])
        assert named["success"] and named["document"] == "poster.vixl"
        # A failed call drops its document from the server's cache; that must not make the other one the default.
        broken = await client.call("vixl_apply", document="poster.vixl", operations=[{"type": "move", "target": "nope"}])
        assert broken[0]
        assert "ambiguous_document" in (await client.call("vixl_apply", operations=[{"type": "solid"}]))[1]
        # Closing one leaves a single open document, and the default works again.
        await client.call("vixl_document", action="close", document="infographic.vixl")
        assert (await client.call("vixl_document"))["document"] == "poster.vixl"

    run(server, scenario)
    assert [layer["name"] for layer in session.inspect(document="poster.vixl")["layers"]] == ["bg", "mine"]
    assert Project.load(tmp_path / "infographic.vixl").state["layers"] == []


def test_client_without_a_choice_does_not_inherit_the_server_default(tmp_path):
    class Who:
        pass

    session = Session(workspace=tmp_path)
    session.create("started.vixl", 10, 10)  # The document a server was started with.
    mine, theirs = Who(), Who()
    token = CALL.set(CallState(client=theirs))
    try:
        session.create("theirs.vixl", 10, 10)
    finally:
        CALL.reset(token)
    token = CALL.set(CallState(client=mine))
    try:
        with pytest.raises(VixlError) as caught:
            session.active()
        assert caught.value.code == "ambiguous_document"
        session.open("started.vixl")
        assert session.relative(session.active()) == "started.vixl"  # Chosen by this client, and only that one.
    finally:
        CALL.reset(token)
    token = CALL.set(CallState(client=theirs))
    try:
        assert session.relative(session.active()) == "theirs.vixl"
    finally:
        CALL.reset(token)


def test_instructions_describe_jobs_and_ids(tmp_path):
    assert "vixl_job" in mcp_server(workspace=tmp_path).instructions
    assert "vixl_job" in mcp_server(workspace=tmp_path, tools="ai").instructions
    assert "request_id" in mcp_server(workspace=tmp_path).instructions


def test_tool_schemas_offer_request_id_and_as_job_only_where_they_help(tmp_path):
    async def scenario():
        tools = {t.name: t for t in await mcp_server(workspace=tmp_path).list_tools()}
        apply = tools["vixl_apply"].inputSchema["properties"]
        assert {"request_id", "as_job"} <= set(apply) and "ctx" not in apply
        assert "request_id" in tools["vixl_document"].inputSchema["properties"]
        assert "as_job" not in tools["vixl_document"].inputSchema["properties"]
        export = tools["vixl_export"].inputSchema["properties"]
        assert {"request_id", "as_job"} <= set(export)
        assert "as_job" in tools["vixl_check"].inputSchema["properties"]
        for name in ("vixl_job", "vixl_render", "vixl_reference"):
            assert not {"request_id", "as_job"} & set(tools[name].inputSchema["properties"])

    asyncio.run(scenario())


def test_cancelled_status_uses_the_error_type_not_its_text():  # #685
    from concurrent.futures import Future

    from vixl.errors import Cancelled
    from vixl.mcp_runtime import Job

    class Box:
        started = submitted = None
        progress = None

    def finished(error):
        future = Future()
        future.set_exception(error)
        return Job("vixl_apply", None, None, future, Box()).status

    class ToolError(Exception):
        pass

    lookalike = VixlError("invalid_operation", 'Text says {"error":"cancelled"}')
    wrapped = ToolError('{"error":"cancelled"}')
    wrapped.__cause__ = lookalike
    assert finished(wrapped) == "failed"
    real = ToolError("stopped")
    real.__cause__ = Cancelled()
    assert finished(real) == "cancelled"
    assert finished(Cancelled("Timeline cancelled")) == "cancelled"


def test_every_cancelled_error_is_typed():  # #685
    from vixl.calls import check_cancelled
    from vixl.errors import Cancelled, require

    with pytest.raises(Cancelled) as error:
        require(False, "Film cancelled", "cancelled")
    assert error.value.code == "cancelled" and str(error.value) == "Film cancelled"
    state = CallState()
    state.cancel.set()
    token = CALL.set(state)
    try:
        with pytest.raises(Cancelled):
            check_cancelled()
    finally:
        CALL.reset(token)
