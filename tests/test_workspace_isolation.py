"""Durable queue quotas (#824), workspace-only resource routes (#820) and link paths without the server's
folders (#829)."""

import json
import os
import subprocess
import sys
import time

from fastapi.testclient import TestClient
import pytest

from vixl import Project, jobs, links
from vixl.errors import VixlError
from vixl.interfaces import Session, create_app
from vixl.jobs import Queue
from vixl.workflows import dispatch


def source(tmp_path, name="source.vixl"):
    project = Project(40, 30, "white")
    project.apply({"type": "text", "name": "title", "text": "Hi", "size": 10})
    project.save(tmp_path / name)
    return project


def production(output):
    return {"kind": "production", "source": "source.vixl", "output": output, "spec": {}}


# Quotas for durable workflow queues (#824)

def test_submissions_past_the_pending_cap_are_refused(tmp_path, monkeypatch):
    monkeypatch.setenv("VIXL_QUEUE_MAX_JOBS", "2")
    source(tmp_path)
    queue = Queue(tmp_path)
    first = queue.submit(production("a"))
    queue.submit(production("b"))
    with pytest.raises(VixlError) as caught:
        queue.submit(production("c"))
    assert caught.value.code == "limit_exceeded"
    assert caught.value.details["limit"] == "max_pending_jobs" and caught.value.details["maximum"] == 2
    assert "VIXL_QUEUE_MAX_JOBS" in str(caught.value)
    assert len(list(queue.directory.glob("*.json"))) == 2
    assert len([path for path in queue.directory.iterdir() if path.is_dir()]) == 2, "a refused job leaves no folder"
    assert queue.work_one(first["id"])["status"] == "completed"  # a finished job frees its place
    assert queue.submit(production("c"))["status"] == "queued"


def test_the_pending_cap_holds_through_the_workflow_action(tmp_path, monkeypatch):
    monkeypatch.setenv("VIXL_QUEUE_MAX_JOBS", "1")
    source(tmp_path)
    session = Session(workspace=tmp_path)
    dispatch(session, "submit", {"job": production("a")})
    with pytest.raises(VixlError) as caught:
        dispatch(session, "submit", {"job": production("b")})
    assert caught.value.code == "limit_exceeded" and str(tmp_path) not in json.dumps(caught.value.as_dict())


def test_the_queue_disk_quota_refuses_and_removes_an_oversized_snapshot(tmp_path, monkeypatch):
    source(tmp_path)
    queue = Queue(tmp_path)
    monkeypatch.setenv("VIXL_QUEUE_MAX_MB", "0.0001")  # about 100 bytes: one snapshot is already too much
    with pytest.raises(VixlError) as caught:
        queue.submit(production("a"))
    assert caught.value.details["limit"] == "max_queue_mb"
    assert not list(queue.directory.glob("*.json")) and not [p for p in queue.directory.iterdir() if p.is_dir()]
    monkeypatch.setenv("VIXL_QUEUE_MAX_MB", "0")  # off
    job = queue.submit(production("a"))
    monkeypatch.setenv("VIXL_QUEUE_MAX_MB", "0.0001")
    with pytest.raises(VixlError) as caught:  # the queue is full before anything new is written
        queue.submit(production("b"))
    assert caught.value.details["limit"] == "max_queue_mb" and "whole disk quota" in str(caught.value)
    assert [path.stem for path in queue.directory.glob("*.json")] == [job["id"]]


def test_finished_jobs_older_than_the_retention_period_are_pruned(tmp_path, monkeypatch):
    source(tmp_path)
    queue = Queue(tmp_path)
    old = queue.work_one(queue.submit(production("old"))["id"])
    recent = queue.work_one(queue.submit(production("recent"))["id"])
    review = queue.submit(production("review"))
    pending = queue.submit(production("pending"))
    assert old["status"] == recent["status"] == "completed"
    long_ago = time.time() - 8 * 86400

    def age(job, status=None):
        record = json.loads(queue.path(job["id"]).read_text())
        record.update(updated=long_ago, **({"status": status} if status else {}))
        queue.path(job["id"]).write_text(json.dumps(record))

    age(old)
    age(review, "needs_review")  # waits for a person: never pruned
    age(pending)  # unfinished: never pruned
    (queue.directory / (old["id"] + ".cancel")).write_bytes(b"cancel")
    later = queue.submit(production("later"))  # submitting prunes first
    remaining = {path.stem for path in queue.directory.glob("*.json")}
    assert remaining == {recent["id"], review["id"], pending["id"], later["id"]}
    assert not (queue.directory / old["id"]).exists() and not (queue.directory / (old["id"] + ".cancel")).exists()
    assert (tmp_path / "old").is_dir(), "published outputs stay"
    with pytest.raises(VixlError):
        queue.status(old["id"])
    monkeypatch.setenv("VIXL_QUEUE_RETENTION_DAYS", "0")  # off
    age(recent)
    assert queue.prune() == []
    monkeypatch.setenv("VIXL_QUEUE_RETENTION_DAYS", "1")
    assert queue.prune() == [recent["id"]]


def test_a_bad_quota_setting_is_a_clear_error(tmp_path, monkeypatch):
    monkeypatch.setenv("VIXL_QUEUE_MAX_JOBS", "many")
    with pytest.raises(VixlError, match="VIXL_QUEUE_MAX_JOBS"):
        jobs.quota("max_pending_jobs")


class FakeWorker:
    """Stands in for the detached worker process: it holds the queue's worker lock like the real one."""

    launched, alive = [], []

    def __init__(self, command, **kwargs):
        from filelock import FileLock

        FakeWorker.launched.append(command)
        FakeWorker.alive.append(self)  # a real worker outlives the call that started it
        self.pid = 4242
        directory = Queue(command[-2] if command[1] == "-m" else command[4]).directory
        self.lock = FileLock(str(directory / ".worker.lock"), timeout=0)
        self.lock.acquire()
        (directory / ".worker.pid").write_text(str(self.pid), encoding="ascii")

    def poll(self):
        return None


def test_a_second_start_spawns_no_second_process(tmp_path, monkeypatch):
    FakeWorker.launched, FakeWorker.alive = [], []
    monkeypatch.setattr(subprocess, "Popen", FakeWorker)
    session = Session(workspace=tmp_path)
    first = dispatch(session, "start", {})
    assert first == {"worker_pid": 4242, "workspace": "."} and len(FakeWorker.launched) == 1
    second = dispatch(session, "start", {"workers": 4})
    assert second["already_running"] is True and second["worker_pid"] == 4242 and second["workspace"] == "."
    source(tmp_path)
    submitted = dispatch(session, "submit", {"job": production("a"), "start": True})
    assert submitted["worker"]["already_running"] is True
    assert len(FakeWorker.launched) == 1, "one worker process per queue"
    for process in FakeWorker.alive:
        process.lock.release()


def test_a_second_worker_process_leaves_the_queue_to_the_first(tmp_path):
    source(tmp_path)
    queue = Queue(tmp_path)
    job = queue.submit(production("a"))
    with queue.lock(".worker.lock", 0):  # a running worker holds this for its whole life
        assert queue.worker_alive() is not None
        result = subprocess.run([sys.executable, "-m", "vixl.jobs", str(tmp_path), "1"], capture_output=True,
                                timeout=60, env={**os.environ, "PYTHONPATH": os.pathsep.join(sys.path)})
        assert result.returncode == 0, result.stderr.decode()
        assert queue.status(job["id"])["status"] == "queued", "the second worker did no work"
    assert queue.worker_alive() is None
    assert jobs.worker(tmp_path) is True and queue.status(job["id"])["status"] == "completed"
    assert not (queue.directory / ".worker.pid").exists()


def test_start_launches_one_real_worker_that_drains_the_queue(tmp_path, monkeypatch):
    monkeypatch.setenv("PYTHONPATH", os.pathsep.join(sys.path))
    source(tmp_path)
    queue = Queue(tmp_path)
    job = queue.submit(production("a"))
    started = queue.start()
    assert started["workspace"] == "." and started["worker_pid"] > 0
    deadline = time.time() + 60
    while queue.status(job["id"])["status"] != "completed" and time.time() < deadline:
        time.sleep(0.2)
    assert queue.status(job["id"])["status"] == "completed"


# Workspace isolation for resources (#820)

@pytest.fixture
def global_library(tmp_path, monkeypatch):
    path = tmp_path / "home" / "resources.json"
    path.parent.mkdir()
    path.write_text(json.dumps({"palettes": {"house": ["#000000", "#ffffff"]}}))
    monkeypatch.setenv("VIXL_RESOURCES", str(path))
    return path


def test_rest_resource_routes_write_the_workspace_library_not_the_global_one(tmp_path, global_library):
    workspace = tmp_path / "work"
    workspace.mkdir()
    Project(16, 16).save(workspace / "api.vixl")
    before = global_library.read_bytes()
    client = TestClient(create_app(workspace / "api.vixl"))
    saved = client.post("/resources/palettes/mine", json={"value": ["#112233", "#445566"]})
    assert saved.status_code == 200, saved.text
    assert global_library.read_bytes() == before, "the user-global library is untouched"
    assert json.loads((workspace / ".vixl-resources.json").read_text())["palettes"] == {"mine": ["#112233", "#445566"]}
    assert "mine" in client.get("/resources/palettes").json()["names"]
    assert client.get("/resources/palettes/mine").json()["value"] == ["#112233", "#445566"]
    # A second workspace does not see what the first one saved.
    other = tmp_path / "other"
    other.mkdir()
    Project(16, 16).save(other / "api.vixl")
    assert "mine" not in TestClient(create_app(other / "api.vixl")).get("/resources/palettes").json()["names"]
    # The same holds for the resource workflows REST exposes.
    assert client.post("/workflow/resource-save", json={"kind": "palettes", "name": "two",
                                                        "value": ["#010101", "#020202"]}).status_code == 200
    assert global_library.read_bytes() == before


def test_service_resource_calls_refuse_a_missing_workspace(global_library):
    from vixl import resources, studio

    class NoWorkspace:
        workspace = None

    before = global_library.read_bytes()
    for action, request in (("resource-list", {"kind": "palettes"}),
                            ("resource-get", {"kind": "palettes", "name": "house"}),
                            ("resource-save", {"kind": "palettes", "name": "x", "value": ["#000000", "#ffffff"]})):
        with pytest.raises(VixlError) as caught:
            studio.dispatch(NoWorkspace(), action, request)
        assert caught.value.code == "forbidden"
    with pytest.raises(VixlError):
        resources.service_workspace(object())
    assert global_library.read_bytes() == before


# Link paths never show where the workspace is (#829)

def tile(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    project = Project(20, 20, "white")
    project.apply({"type": "solid", "name": "bg", "color": "#ff0000"})
    project.save(path, overwrite=True)


def test_link_status_and_missing_link_errors_over_rest_hold_no_absolute_path(tmp_path):
    tile(tmp_path / "assets" / "tile.vixl")
    Project(100, 100, "white").save(tmp_path / "host.vixl")
    client = TestClient(create_app(tmp_path / "host.vixl"))
    applied = client.post("/operations", json={"operations": [
        {"type": "link", "source": "assets/tile.vixl", "name": "t"}]})
    assert applied.status_code == 200, applied.text
    listed = client.post("/workflow/links", json={})
    assert listed.status_code == 200, listed.text
    [item] = listed.json()["links"]
    assert item["state"] == "ok" and item["path"] == "assets/tile.vixl" and item["resolved_from"] == "document"
    assert str(tmp_path) not in listed.text
    (tmp_path / "assets" / "tile.vixl").unlink()
    missing = client.post("/workflow/links", json={})
    [item] = missing.json()["links"]
    assert item["state"] == "missing" and "looked for assets/tile.vixl" in item["message"]
    assert str(tmp_path) not in missing.text
    for response in (client.post("/export", json={"format": "PNG"}), client.post("/check", json={"checks": ["links"]}),
                     client.post("/workflow/check", json={}), client.get("/project")):
        assert str(tmp_path) not in response.text, response.text
    failed = client.post("/export", json={"format": "PNG"})
    assert failed.status_code == 400 and failed.json()["error"] == "link_missing"
    assert failed.json()["path"] == "assets/tile.vixl"


def test_link_paths_are_relative_in_python_and_absolute_only_with_allow_linked(tmp_path):
    tile(tmp_path / "ws" / "assets" / "tile.vixl")
    host = Project(100, 100, "white", workspace=tmp_path / "ws")
    host.save(tmp_path / "ws" / "pages" / "card.vixl")
    host.apply({"type": "link", "source": "assets/tile.vixl", "name": "t"})
    [item] = links.status(host)
    assert item["path"] == "assets/tile.vixl" and item["resolved_from"] == "workspace"
    (tmp_path / "ws" / "assets" / "tile.vixl").unlink()
    with pytest.raises(VixlError) as caught:
        links.open_source(host, links.locate(host, "assets/tile.vixl"), "assets/tile.vixl")
    assert str(tmp_path) not in json.dumps(caught.value.as_dict())
    assert "pages/assets/tile.vixl, assets/tile.vixl" in str(caught.value)  # both places searched, workspace-relative
    # A linked document that links back: the cycle's chain is workspace-relative too.
    a, b = Project(20, 20, workspace=tmp_path / "ws"), Project(20, 20, workspace=tmp_path / "ws")
    a.save(tmp_path / "ws" / "a.vixl")
    b.save(tmp_path / "ws" / "b.vixl")
    b.apply({"type": "link", "source": "a.vixl", "name": "to-a"})
    b.save()
    with pytest.raises(VixlError) as caught:
        a.apply({"type": "link", "source": "b.vixl", "name": "to-b"})
    assert caught.value.code == "link_cycle" and caught.value.details["chain"] == ["a.vixl", "b.vixl", "a.vixl"]
    # A document outside its workspace: paths are relative to the document's folder.
    tile(tmp_path / "bare" / "tile.vixl")
    bare = Project(50, 50, workspace=tmp_path / "ws")
    bare.save(tmp_path / "bare" / "host.vixl")
    bare.apply({"type": "link", "source": "tile.vixl", "name": "t"})
    assert links.status(bare)[0]["path"] == "tile.vixl"
    # Only the explicit local opt-in to files anywhere shows where such a file is.
    tile(tmp_path / "far" / "tile.vixl")
    far = str((tmp_path / "far" / "tile.vixl").resolve())
    with pytest.raises(VixlError) as caught:
        bare.apply({"type": "link", "source": far, "name": "far"})
    assert caught.value.code == "forbidden"
    bare.allow_linked = True
    bare.apply({"type": "link", "source": far, "name": "far"})
    assert {item["layer"]: item["path"] for item in links.status(bare)}["far"] == far
