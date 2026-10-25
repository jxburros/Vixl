"""The ``vixl host`` API contract (#543): every endpoint is driven here and its answers validated against
``src/vixl/data/host-api.schema.json``, the file ``vixl host --schema`` prints and releases attach."""

import io
import json
import re

import pytest

pytest.importorskip("fastapi")

import jsonschema  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from vixl import host  # noqa: E402

TOKEN = "c" * 32
AUTH = {"Authorization": f"Bearer {TOKEN}"}
SCHEMA = host.schema()
FRAMEWORK = {"/docs", "/docs/oauth2-redirect", "/openapi.json", "/redoc"}  # FastAPI's own pages


def validate(name, instance):
    jsonschema.Draft202012Validator({"$schema": SCHEMA["$schema"], "$defs": SCHEMA["$defs"],
                                     "$ref": f"#/$defs/{name}"}).validate(instance)


class Driver:
    """A test client that records which contract endpoint each call reached and checks its answer."""

    def __init__(self, client):
        self.client, self.seen = client, set()

    def call(self, method, template, *, status=200, params=None, **kwargs):
        url = template
        for key, value in (params or {}).items():
            url = url.replace("{" + key + "}", value)
        response = self.client.request(method, url, **kwargs)
        assert response.status_code == status, (template, response.text)
        key = f"{method} {template.split('?', 1)[0]}"
        assert key in SCHEMA["endpoints"], key
        self.seen.add(key)
        spec = SCHEMA["endpoints"][key]
        if "request" in spec and "json" in kwargs:
            validate(spec["request"]["$ref"].rsplit("/", 1)[1], kwargs["json"])
        if status >= 400:
            validate("Error", response.json())
        elif "response" in spec and status != 202 or key.endswith("/exports"):
            validate(spec["response"]["$ref"].rsplit("/", 1)[1] if "$ref" in spec["response"] else "Any",
                     response.json())
        return response


@pytest.fixture
def driver(tmp_path, monkeypatch):
    monkeypatch.setenv("VIXL_AUTO_FONTS", "off")
    with TestClient(host.create_host_app(tmp_path / "root", TOKEN), headers=AUTH) as client:
        yield Driver(client)


def png():
    from PIL import Image

    stream = io.BytesIO()
    Image.new("RGB", (12, 8), "#2c5aa0").save(stream, format="PNG")
    return stream.getvalue()


def test_every_endpoint_answers_its_contract(driver, tmp_path):
    from vixl import Project

    call = driver.call
    info = call("GET", "/host/info").json()
    assert info["host_api"] == SCHEMA["host_api"] == host.HOST_API
    call("GET", "/host/health")
    assert call("GET", "/host/schema").json() == SCHEMA
    ws = {"ws": "studio"}
    call("GET", "/w/{ws}", params=ws)
    made = call("POST", "/w/{ws}/documents", params=ws, status=201,
                json={"width": 320, "height": 200, "background": "#ffffff", "workspace_fonts": False,
                      "name": "Card"}).json()
    ids = {**ws, "id": made["id"]}
    call("GET", "/w/{ws}/documents", params=ws)
    applied = call("POST", "/w/{ws}/documents/{id}/operations", params=ids, json={
        "operations": [{"type": "text", "name": "title", "text": "Hello", "size": 28, "x": 290, "y": 20,
                        "color": "#111111"}], "if_revision": 1, "request_id": "r-1"}).json()
    assert applied["revision"] == 2
    call("POST", "/w/{ws}/documents/{id}/assets", params=ids, content=png(),
         headers={"content-type": "image/png"})
    svg = b'<svg xmlns="http://www.w3.org/2000/svg" width="20" height="10"><rect width="20" height="10"/></svg>'
    call("POST", "/w/{ws}/documents/{id}/import?format=svg", params=ids, content=svg)
    state = call("GET", "/w/{ws}/documents/{id}", params=ids).json()
    assert state["revision"] == 4
    blob = call("GET", "/w/{ws}/documents/{id}/blob", params=ids)
    assert blob.headers["x-vixl-revision"] == "4"
    report = call("POST", "/w/{ws}/documents/{id}/check", params=ids, json={"checks": ["bounds"]}).json()
    assert any(finding["layer_id"] for finding in report["findings"])
    preview = call("POST", "/w/{ws}/documents/{id}/preview", params=ids, json={"max_px": 200})
    assert preview.headers["content-type"] == "image/png" and int(preview.headers["x-vixl-width"]) <= 200
    call("POST", "/w/{ws}/documents/{id}/compose", params=ids, json={
        "layout": {"name": "hero-statement", "title": "Make it simple", "seed": 2}, "seed": 2, "preview": True})
    job = call("POST", "/w/{ws}/documents/{id}/exports", params=ids, status=202, json={"format": "PNG"}).json()
    jobs = {"id": job["job_id"]}
    status = call("GET", "/jobs/{id}?wait=20", params=jobs)
    assert status.json()["status"] == "completed"
    stream = call("GET", "/jobs/{id}/events", params=jobs)
    events = parse_events(stream.text)
    assert [kind for kind, _ in events][-1:] == ["job-complete"]
    spec = SCHEMA["endpoints"]["GET /jobs/{id}/events"]["events"]
    for kind, data in events:
        validate(spec[kind]["$ref"].rsplit("/", 1)[1], data)
    download = call("GET", "/jobs/{id}/download", params=jobs)
    assert download.content.startswith(b"\x89PNG")
    for kind in SCHEMA["endpoints"]["GET /catalog/{kind}"]["kinds"]:
        query = {"guide": "?brief=a+poster", "operations": "?name=text", "tools": "?profile=studio"}.get(kind, "")
        found = call("GET", "/catalog/{kind}" + query, params={"kind": kind}).json()
        if kind == "tools":
            validate("ToolProfile", found)
    call("GET", "/w/{ws}/brand", params=ws, status=404)
    palette = {"background": "#ffffff", "surface": "#eeeeee", "ink": "#111111", "muted": "#444444",
               "accent": "#0044aa", "accent-text": "#0044aa", "on-accent": "#ffffff"}
    written = call("PUT", "/w/{ws}/brand", params=ws, json={"name": "Plain", "palette": palette}).json()
    assert written["source"] == "brand.json" and written["unmapped"] == []
    assert call("GET", "/w/{ws}/brand", params=ws).json()["digest"] == written["digest"]
    source = Project(80, 60, "#203040")
    source.save(tmp_path / "in.vixl")
    imported = call("POST", "/w/{ws}/documents/import?name=in", params=ws, status=201,
                    content=(tmp_path / "in.vixl").read_bytes()).json()
    call("DELETE", "/w/{ws}/documents/{id}", params={**ws, "id": imported["id"]})
    # A call that outlived the timeout is read back through /jobs/{id}/result.
    from concurrent.futures import Future

    future = Future()
    future.set_result({"id": made["id"], "revision": 5})
    detached = driver.client.app.state.host.jobs.add("operations", future)
    assert call("GET", "/jobs/{id}/result", params={"id": detached}).json()["revision"] == 5
    missing = set(SCHEMA["endpoints"]) - driver.seen
    assert not missing, f"endpoints the contract test did not drive: {missing}"


def parse_events(text):
    events, kind = [], None
    for line in text.splitlines():
        if line.startswith("event: "):
            kind = line[len("event: "):]
        elif line.startswith("data: "):
            events.append((kind, json.loads(line[len("data: "):])))
    return events


def test_errors_answer_the_error_shape(driver):
    call = driver.call
    call("GET", "/w/{ws}/documents/{id}", params={"ws": "studio", "id": "d_00000000"}, status=404)
    call("GET", "/catalog/{kind}", params={"kind": "nope"}, status=404)
    call("POST", "/w/{ws}/documents", params={"ws": "studio"}, json={"width": 10, "height": 10, "size": "a4"},
         status=400)
    unknown = driver.client.post("/w/studio/documents", json={"colour": "red"})
    assert unknown.status_code == 400
    validate("Error", unknown.json())
    validate("Error", TestClient(driver.client.app).get("/host/info").json())


def test_the_contract_lists_exactly_the_app_routes(driver):
    def template(path):
        return re.sub(r"\{(doc|ident)\}", "{id}", path)

    served = {f"{method} {template(route.path)}" for route in driver.client.app.routes
              if hasattr(route, "methods") and route.path not in FRAMEWORK for method in route.methods
              if method != "HEAD"}
    assert served == set(SCHEMA["endpoints"])


def test_request_definitions_match_what_the_routes_accept():
    from vixl.interfaces import EXPORT_FIELDS, EXPORT_MEDIA

    defs = SCHEMA["$defs"]
    assert set(defs["CreateRequest"]["properties"]) == host.CREATE_FIELDS
    assert set(defs["OperationsRequest"]["properties"]) == host.OPERATION_FIELDS
    assert set(defs["ComposeRequest"]["properties"]) == host.compose_fields()
    assert set(defs["PreviewRequest"]["properties"]) == host.PREVIEW_FIELDS
    assert defs["ExportRequest"]["properties"]["format"]["enum"] == sorted(EXPORT_MEDIA)
    assert defs["ExportRequest"]["properties"]["options"]["propertyNames"]["enum"] == sorted(EXPORT_FIELDS
                                                                                              - {"format"})
    assert SCHEMA["endpoints"]["GET /catalog/{kind}"]["kinds"] == list(host.CATALOG_KINDS)


def test_the_schema_is_valid_json_schema_and_published_by_the_cli():
    from vixl.cli import dispatch

    jsonschema.Draft202012Validator.check_schema(SCHEMA)
    assert dispatch(["host", "--schema"])[0] == SCHEMA


def test_releases_attach_the_contract_like_the_catalog_schema():
    from pathlib import Path

    workflow = (Path(__file__).parents[1] / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    assert "vixl --json host --schema > dist/vixl-host-api.schema.json" in workflow
    assert "dist/vixl-host-api.schema.json" in workflow.split("upload-artifact", 1)[1]
