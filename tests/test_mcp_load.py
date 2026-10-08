"""Many agents on one MCP server (#167): calls queued behind busy workers become jobs sooner."""

import asyncio
import json
import threading

from vixl import mcp_runtime
from vixl.mcp_runtime import Runtime


def runtime(monkeypatch, workers, inline_seconds):
    monkeypatch.setenv("VIXL_MCP_WORKERS", str(workers))
    return Runtime(None, json.dumps, RuntimeError, inline_seconds=inline_seconds)


def blocking_tool(release):
    def vixl_export_file(document: str | None = None) -> dict:
        release.wait(10)
        return {"ok": True}

    return vixl_export_file


def test_inline_budget_shrinks_only_when_calls_exceed_workers(monkeypatch):
    rt = runtime(monkeypatch, workers=4, inline_seconds=40)
    assert rt.budget(1) == rt.budget(4) == 40
    assert rt.budget(8) == 20 and rt.budget(16) == 10
    assert rt.budget(10_000) == mcp_runtime.MIN_INLINE_SECONDS
    assert runtime(monkeypatch, workers=1, inline_seconds=0.5).budget(50) == 0.5


def test_queued_calls_become_jobs_early_and_report_their_wait(monkeypatch):
    monkeypatch.setattr(mcp_runtime, "MIN_INLINE_SECONDS", 0.05)
    rt = runtime(monkeypatch, workers=2, inline_seconds=2)
    release = threading.Event()
    tool = rt.wrap(blocking_tool(release))

    async def scenario():
        tasks = [asyncio.create_task(tool()) for _ in range(8)]
        queued = [json.loads(text) for text in await asyncio.gather(*tasks[2:])]
        release.set()
        running = [json.loads(text) for text in await asyncio.gather(*tasks[:2])]
        return queued, running

    queued, running = asyncio.run(scenario())
    # The two calls that got a worker answered inline; the six behind them came back as jobs well
    # before the 2 s inline budget, saying they are queued and how deep the queue is.
    assert running == [{"ok": True}, {"ok": True}]
    for pointer in queued:
        assert pointer["status"] == "queued" and pointer["queued"] is True
        assert pointer["job"].startswith("job_") and "Queued behind" in pointer["message"]
        assert 1 <= pointer["queue_depth"] <= 6 and pointer["wait_ms"] < 2000
    for pointer in queued:
        done = rt.job("result", pointer["job"], wait=10)
        assert done["status"] == "completed" and done["result"] == {"ok": True}
        assert done["queued"] is False and done["wait_ms"] >= 0
    assert rt.queue_depth() == 0 and rt.in_flight == 0


def test_concurrent_clients_on_threads_keep_the_count_consistent(monkeypatch):
    rt = runtime(monkeypatch, workers=3, inline_seconds=5)
    release = threading.Event()
    release.set()
    tool = rt.wrap(blocking_tool(release))
    results, errors = [], []

    def client():
        try:
            for _ in range(5):
                results.append(json.loads(asyncio.run(tool())))
        except Exception as exc:  # pragma: no cover - reported below
            errors.append(exc)

    threads = [threading.Thread(target=client) for _ in range(12)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(30)
    assert not errors and results == [{"ok": True}] * 60
    assert rt.in_flight == 0
