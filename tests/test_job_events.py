"""One completion event for durable jobs (F2), and durable job kinds a plugin adds (implementation plan step 7)."""

import pytest

from vixl import Project, plugins
from vixl.errors import VixlError
from vixl.jobs import Queue


def hooked(monkeypatch, points):
    original = plugins.hooks

    def hooks(point):
        return tuple(points[point]) if point in points else original(point)

    monkeypatch.setattr(plugins, "hooks", hooks)


def source(tmp_path):
    from vixl.production import capture_recipe

    p = Project(160, 100, "#102030")
    p.apply({"type": "text", "name": "title", "text": "Hello box", "size": 24, "x": 10, "y": 10})
    capture_recipe(p, {"version": 1, "inputs": {"title": {"type": "string", "default": "Hello", "maxLength": 60}}},
                   {"title": {"target": "title", "field": "text"}})
    p.save(tmp_path / "source.vixl")


def test_a_finished_job_emits_one_event_without_document_content(tmp_path, monkeypatch):
    events = []
    hooked(monkeypatch, {"job-complete": [lambda event: events.append(event) or {"sent": True}]})
    source(tmp_path)
    queue = Queue(tmp_path)
    job = queue.submit({"kind": "production", "source": "source.vixl", "output": "out",
                        "spec": {"rows": [{"title": "Uno"}]}})
    assert events == []
    done = queue.work_one(job["id"])
    assert done["status"] == "completed"
    queue.save(queue.status(job["id"]))  # Saving a finished job again sends nothing.
    assert len(events) == 1
    event = events[0]
    assert {"event", "kind", "id", "status", "state", "counts", "report", "workspace"} <= event.keys()
    assert (event["event"], event["kind"], event["id"], event["status"]) == ("job-complete", "production", job["id"],
                                                                            "completed")
    assert "box" not in repr(event) and "Uno" not in repr(event)
    assert queue.status(job["id"])["deliveries"] == [{"sent": True}]


def test_a_failing_consumer_is_recorded_and_the_job_still_completes(tmp_path, monkeypatch):
    def broken(event):
        raise RuntimeError("receiver down")

    hooked(monkeypatch, {"job-complete": [broken]})
    source(tmp_path)
    queue = Queue(tmp_path)
    job = queue.submit({"kind": "production", "source": "source.vixl", "output": "out",
                        "spec": {"rows": [{"title": "Uno"}]}})
    done = queue.work_one(job["id"])
    assert done["status"] == "completed"
    assert "receiver down" in queue.status(job["id"])["deliveries"][0]["error"]


def test_a_resumed_job_reports_its_next_ending(tmp_path, monkeypatch):
    events = []
    hooked(monkeypatch, {"job-complete": [events.append]})
    source(tmp_path)
    queue = Queue(tmp_path)
    job = queue.submit({"kind": "production", "source": "source.vixl", "output": "out",
                        "spec": {"rows": [{"title": "Uno"}]}})
    queue.cancel(job["id"])
    assert queue.work_one(job["id"])["status"] == "cancelled"
    queue.resume(job["id"])
    assert queue.work_one(job["id"])["status"] == "completed"
    assert [e["status"] for e in events] == ["cancelled", "completed"]


def test_a_plugin_job_kind_is_validated_queued_and_run(tmp_path, monkeypatch):
    seen = []

    def validate(queue, payload, output):
        if payload.get("request", {}).get("bad"):
            raise VixlError("invalid_value", "bad request")

    def run(queue, job, limits, progress, cancelled):
        progress({"done": 1})
        seen.append(job["payload"]["request"])
        return {"status": "completed", "counts": {"passed": 1}}

    def kind(name):
        return {"validate": validate, "run": run} if name == "echo" else None

    kind.KINDS = ("echo",)
    hooked(monkeypatch, {"job-kind": [kind]})
    queue = Queue(tmp_path)
    with pytest.raises(VixlError, match="bad request"):
        queue.submit({"kind": "echo", "output": "echo-out", "request": {"bad": True}})
    with pytest.raises(VixlError) as unknown:
        queue.submit({"kind": "nope", "output": "x"})
    assert "echo" in unknown.value.as_dict()["kinds"]
    job = queue.submit({"kind": "echo", "output": "echo-out", "request": {"n": 1}})
    done = queue.work_one(job["id"])
    assert done["status"] == "completed" and done["result"]["counts"] == {"passed": 1}
    assert seen == [{"n": 1}]
