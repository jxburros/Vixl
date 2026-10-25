"""Completion webhooks (#579): the pipelines plugin's job-complete consumer POSTs a signed event to an allowed host."""

import hashlib
import hmac
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import threading

import pytest

from vixl import Project
from vixl.interfaces import Session
from vixl.jobs import Queue
from vixl.plugins.pipelines import notify
from vixl.workflows import dispatch

SECRET = "s3cret-for-tests"


class Receiver:
    """A local webhook receiver that answers with the queued status codes (then 200) and records each request."""

    def __init__(self):
        self.requests, self.codes = [], []
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
                owner.requests.append({"headers": dict(self.headers), "body": body, "path": self.path})
                code = owner.codes.pop(0) if owner.codes else 200
                self.send_response(code)
                self.send_header("Content-Length", "0")
                self.end_headers()

            def log_message(self, *args):
                pass

        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_port}/hook"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture
def receiver(tmp_path, monkeypatch):
    server = Receiver()
    monkeypatch.setenv("VIXL_ALLOW_PRIVATE_FETCH", "1")
    monkeypatch.delenv("VIXL_OFFLINE", raising=False)
    monkeypatch.setenv("VIXL_HOOK_SECRET", SECRET)
    monkeypatch.setattr(notify, "BACKOFF", (0, 0, 0))
    allow(tmp_path, ["127.0.0.1"])
    yield server
    server.close()


def allow(root, hosts, **extra):
    (root / ".vixl").mkdir(exist_ok=True)
    (root / ".vixl" / "notify.json").write_text(json.dumps({"allow": hosts, **extra}))


def source(tmp_path):
    from vixl.production import capture_recipe

    p = Project(160, 100, "#102030")
    p.apply({"type": "text", "name": "title", "text": "Hello box", "size": 24, "x": 10, "y": 10})
    capture_recipe(p, {"version": 1, "inputs": {"title": {"type": "string", "default": "Hello", "maxLength": 60}}},
                   {"title": {"target": "title", "field": "text"}})
    p.save(tmp_path / "source.vixl")


def job(tmp_path, url, **notify_fields):
    source(tmp_path)
    queue = Queue(tmp_path)
    submitted = queue.submit({"kind": "production", "source": "source.vixl", "output": "out",
                              "spec": {"rows": [{"title": "Uno"}]},
                              "notify": {"url": url, "secret_env": "VIXL_HOOK_SECRET", **notify_fields}})
    return queue, submitted


def signed(request):
    expected = "sha256=" + hmac.new(SECRET.encode(), request["body"], hashlib.sha256).hexdigest()
    return hmac.compare_digest(request["headers"]["X-Vixl-Signature"], expected)


def test_a_finished_job_posts_once_with_a_valid_signature_and_no_document_content(tmp_path, receiver):
    queue, submitted = job(tmp_path, receiver.url)
    done = queue.work_one(submitted["id"])
    assert done["status"] == "completed"
    queue.save(queue.status(submitted["id"]))  # A finished job is never reported twice.
    assert len(receiver.requests) == 1
    request = receiver.requests[0]
    assert signed(request) and request["headers"]["X-Vixl-Delivery"]
    payload = json.loads(request["body"])
    assert (payload["event"], payload["kind"], payload["id"], payload["status"]) == (
        "job-complete", "production", submitted["id"], "completed")
    assert payload["delivery"] == request["headers"]["X-Vixl-Delivery"]
    text = request["body"].decode()
    assert "Hello box" not in text and "Uno" not in text and str(tmp_path) not in text
    delivery = queue.status(submitted["id"])["deliveries"][0]
    assert delivery["status"] == "delivered" and delivery["attempts"] == 1 and delivery["signed"]


def test_a_server_error_is_retried_with_the_same_delivery_id(tmp_path, receiver):
    receiver.codes = [500, 503]
    queue, submitted = job(tmp_path, receiver.url)
    queue.work_one(submitted["id"])
    assert len(receiver.requests) == 3
    assert len({r["headers"]["X-Vixl-Delivery"] for r in receiver.requests}) == 1
    delivery = queue.status(submitted["id"])["deliveries"][0]
    assert delivery["status"] == "delivered" and delivery["attempts"] == 3


def test_retries_stop_after_three_and_a_client_error_is_not_retried(tmp_path, receiver):
    receiver.codes = [500] * 10
    queue, submitted = job(tmp_path, receiver.url)
    queue.work_one(submitted["id"])
    assert len(receiver.requests) == 4  # the first attempt and 3 retries
    assert queue.status(submitted["id"])["deliveries"][0]["status"] == "failed"
    receiver.requests.clear()
    receiver.codes = [404]
    assert notify.send(receiver.url, {"event": "job-complete"}, None, "d1")["attempts"] == 1


def test_a_host_outside_the_allow_list_is_refused(tmp_path, receiver):
    allow(tmp_path, ["hooks.example.org"])
    queue, submitted = job(tmp_path, receiver.url)
    queue.work_one(submitted["id"])
    assert receiver.requests == []
    delivery = queue.status(submitted["id"])["deliveries"][0]
    assert delivery["status"] == "refused" and "allow list" in delivery["reason"]


def test_plain_http_is_refused_except_to_a_loopback_address(tmp_path, receiver):
    allow(tmp_path, ["hooks.example.org"])
    record = notify.deliver({"event": "job-complete", "kind": "check-all", "id": "x", "status": "completed",
                             "workspace": str(tmp_path), "notify": {"url": "http://hooks.example.org/hook"}})
    assert record["status"] == "refused" and "HTTPS" in record["reason"]


def test_offline_sends_nothing(tmp_path, receiver, monkeypatch):
    monkeypatch.setenv("VIXL_OFFLINE", "1")
    queue, submitted = job(tmp_path, receiver.url)
    queue.work_one(submitted["id"])
    assert receiver.requests == []
    assert queue.status(submitted["id"])["deliveries"][0]["status"] == "skipped"


def test_a_missing_secret_refuses_rather_than_sending_unsigned(tmp_path, receiver, monkeypatch):
    monkeypatch.delenv("VIXL_HOOK_SECRET")
    queue, submitted = job(tmp_path, receiver.url)
    queue.work_one(submitted["id"])
    assert receiver.requests == []
    assert "VIXL_HOOK_SECRET" in queue.status(submitted["id"])["deliveries"][0]["reason"]


def test_check_all_emits_the_shared_event_and_posts_it(tmp_path, receiver):
    source(tmp_path)
    session = Session(None, workspace=tmp_path)
    result = dispatch(session, "check-all", {"documents": ["*.vixl"], "notify": {"url": receiver.url,
                                                                                  "secret_env": "VIXL_HOOK_SECRET"}})
    assert result["notify"][0]["status"] == "delivered"
    payload = json.loads(receiver.requests[0]["body"])
    assert payload["kind"] == "check-all" and payload["status"] == "completed"
    assert payload["counts"]["passed"] + payload["counts"]["needs_review"] + payload["counts"]["failed"] == 1
    assert signed(receiver.requests[0])


def test_a_pipeline_run_posts_its_outcome_and_the_workspace_default_applies(tmp_path, receiver):
    allow(tmp_path, ["127.0.0.1"], url=receiver.url, secret_env="VIXL_HOOK_SECRET")
    source(tmp_path)
    session = Session(None, workspace=tmp_path)
    pipeline = {"version": 1, "targets": {"documents": ["source.vixl"]},
                "steps": [{"export": {"targets": [{"path": "out/{doc}.png"}]}}]}
    result = dispatch(session, "pipeline-run", {"pipeline": pipeline, "run": "hook", "dry_run": False})
    assert result["notify"][0]["status"] == "delivered" and len(receiver.requests) == 1
    payload = json.loads(receiver.requests[0]["body"])
    assert payload["kind"] == "pipeline" and payload["id"] == "hook" and payload["counts"] == {"passed": 1}
    assert payload["report"] == ".vixl-runs/hook/run.json"
    # A dry run is not a finished run: nothing is sent.
    dispatch(session, "pipeline-run", {"pipeline": pipeline, "run": "hook2", "dry_run": True})
    assert len(receiver.requests) == 1


def test_a_bad_notify_value_is_refused_up_front(tmp_path):
    source(tmp_path)
    session = Session(None, workspace=tmp_path)
    from vixl.errors import VixlError

    with pytest.raises(VixlError, match="notify"):
        dispatch(session, "pipeline-run", {"pipeline": {"version": 1, "targets": {"documents": ["source.vixl"]},
                                                        "steps": [{"check": {}}]},
                                           "notify": {"url": "https://x.example", "token": "nope"}})
