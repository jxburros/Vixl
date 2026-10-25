"""``vixl host``: the multi-workspace server for host applications (#537-#541)."""

import json
import os
import re

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402

from vixl.errors import VixlError  # noqa: E402

TOKEN = "t" * 32
AUTH = {"Authorization": f"Bearer {TOKEN}"}


def app_for(root, **options):
    from vixl.host import create_host_app

    return create_host_app(root, TOKEN, **options)


@pytest.fixture
def client(tmp_path):
    with TestClient(app_for(tmp_path / "root"), headers=AUTH) as test:
        yield test


# ------------------------------------------------------------------------------------------------- #537 skeleton


def test_every_route_needs_the_token_even_on_loopback(tmp_path):
    test = TestClient(app_for(tmp_path / "root"))
    for path in ("/host/info", "/host/health", "/w/team"):
        response = test.get(path)
        assert response.status_code == 401, path
        assert response.json()["code"] == "unauthorized" and response.json()["hint"]
        assert response.headers["www-authenticate"] == "Bearer"
    assert test.get("/host/info", headers={"Authorization": "Bearer " + "x" * 32}).status_code == 401
    assert test.get("/host/info", headers=AUTH).status_code == 200
    assert not (tmp_path / "root" / "team").exists()  # refused before anything ran


def test_the_host_refuses_to_start_without_a_usable_token(tmp_path):
    from vixl.host import create_host_app, read_token

    for token in (None, "", "short"):
        with pytest.raises(VixlError) as caught:
            create_host_app(tmp_path / "root", token)
        assert caught.value.code == "authentication_required"
    with pytest.raises(VixlError):
        read_token(environ={})
    assert read_token(environ={"VIXL_HOST_TOKEN": TOKEN}) == TOKEN
    assert read_token("OTHER", environ={"OTHER": TOKEN}) == TOKEN
    secret = tmp_path / "token"
    secret.write_text(TOKEN + "\n")
    assert read_token(environ={"VIXL_HOST_TOKEN_FILE": str(secret)}) == TOKEN
    assert read_token(token_file=str(secret), environ={"VIXL_HOST_TOKEN": "y" * 32}) == TOKEN
    (tmp_path / "empty").write_text("")
    with pytest.raises(VixlError) as caught:
        read_token(token_file=str(tmp_path / "empty"), environ={})
    assert caught.value.code == "authentication_required"


def test_the_cli_refuses_to_start_without_a_token(tmp_path, monkeypatch):
    from vixl.cli import dispatch

    monkeypatch.delenv("VIXL_HOST_TOKEN", raising=False)
    monkeypatch.delenv("VIXL_HOST_TOKEN_FILE", raising=False)
    with pytest.raises(VixlError) as caught:
        dispatch(["host", "--root", str(tmp_path / "root")])
    assert caught.value.code == "authentication_required"


def test_workspaces_are_named_folders_inside_the_root(client, tmp_path):
    root = tmp_path / "root"
    assert client.get("/w/team-1").json() == {"workspace": "team-1"}
    assert (root / "team-1").is_dir()
    for bad in ("..", "Team", "a.b", "x" * 65, "%2e%2e", "%2Fetc", "..%2F..%2Fetc"):
        response = client.get(f"/w/{bad}")
        assert response.status_code in (400, 404), bad
        assert set(response.json()) >= {"code", "message", "hint"}
    assert sorted(path.name for path in root.iterdir()) == ["team-1"]
    assert not (tmp_path / "etc").exists()


def test_a_workspace_symlinked_out_of_the_root_is_refused(client, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    try:
        (tmp_path / "root" / "escape").symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("symlinks are not available")
    response = client.get("/w/escape")
    assert response.status_code == 403 and response.json()["code"] == "forbidden"


def test_host_info_reports_version_api_capabilities_limits_and_ttl(client):
    from vixl import __version__

    info = client.get("/host/info").json()
    assert info["vixl"] == __version__ and info["host_api"] == 1
    assert set(info["capabilities"]) == {"pptx", "pdf_import", "ffmpeg", "ai"}
    assert all(isinstance(value, bool) for value in info["capabilities"].values())
    assert {"timeout_s", "max_megapixels", "max_pages", "max_concurrent_per_workspace"} <= set(info["limits"])
    assert info["limits"]["source"]["max_pages"] == "default"  # a host gets the shared-server defaults
    assert info["job_ttl"] == 3600
    assert info["workspaces"]["pattern"] == "[a-z0-9_-]{1,64}"
    assert client.get("/host/health").json() == {"ok": True, "warm": False}


def test_errors_have_one_shape(client):
    unknown = client.get("/no/such/route")
    assert unknown.status_code == 404
    assert set(unknown.json()) == {"code", "message", "hint"}
    from vixl.host import error_body

    body = error_body(VixlError("layer_not_found", "No layer 'x'", layer="x", suggestions=["Use 'y'"], field="t"))
    assert body == {"code": "layer_not_found", "message": "No layer 'x'", "hint": "Use 'y'", "layer_id": "x",
                    "details": {"suggestions": ["Use 'y'"], "field": "t"}}


def test_a_large_body_is_refused_in_the_error_shape(client):
    response = client.post("/w/team/documents", content=b"{" + b" " * (1024 * 1024 + 10) + b"}",
                           headers={"content-type": "application/json"})
    assert response.status_code == 413 and response.json()["code"] == "resource_limit"


def test_offline_refuses_url_fetches_pack_downloads_and_plugin_enabling(tmp_path, monkeypatch):
    from vixl import packs
    from vixl.fetch import fetch_bounded, offline
    from vixl.plugins import enable_plugins

    monkeypatch.delenv("VIXL_OFFLINE", raising=False)
    app_for(tmp_path / "root", offline=True)
    try:
        assert offline()
        with pytest.raises(VixlError) as caught:
            fetch_bounded("https://example.com/cat.png", 1024)
        assert caught.value.code == "network_disabled"
        assert not packs.downloads_allowed()
        with pytest.raises(VixlError) as caught:
            enable_plugins()
        assert caught.value.code == "network_disabled"
    finally:
        os.environ.pop("VIXL_OFFLINE", None)


def test_offline_font_install_uses_only_the_cache(tmp_path, monkeypatch):
    from vixl import Project
    from vixl.typefaces import install_font

    monkeypatch.setenv("VIXL_OFFLINE", "1")
    monkeypatch.setenv("VIXL_FONT_CACHE", str(tmp_path / "fonts"))
    with pytest.raises(VixlError) as caught:
        install_font(Project(100, 100), "Inter", 400)
    assert caught.value.code == "network_disabled"


def test_offline_host_refuses_enabled_plugins(tmp_path, monkeypatch):
    from vixl.plugins import external

    monkeypatch.setattr(external, "_ENABLED", True)
    with pytest.raises(VixlError) as caught:
        app_for(tmp_path / "root", offline=True)
    assert caught.value.code == "network_disabled"
    os.environ.pop("VIXL_OFFLINE", None)


def test_the_server_extra_import_guard(tmp_path, monkeypatch):
    import sys

    monkeypatch.setitem(sys.modules, "fastapi", None)
    with pytest.raises(VixlError) as caught:
        app_for(tmp_path / "root")
    assert caught.value.code == "missing_dependency" and "vixl-engine[server]" in str(caught.value)


def test_cli_flags_include_the_call_limits_and_the_schema(tmp_path):
    from vixl.cli import dispatch
    from vixl.host import host_parser

    a = host_parser().parse_args(["--root", "r", "--offline", "--bind", "0.0.0.0", "--max-pages", "5",
                                  "--token-file", "tok"])
    assert (a.root, a.offline, a.bind, a.max_pages, a.token_file, a.port) == ("r", True, "0.0.0.0", 5, "tok", 8767)
    contract, _ = dispatch(["host", "--schema"])
    assert contract["properties"]["host_api"]["const"] == 1


def test_routes_registered_with_add_routes_join_the_app(tmp_path, monkeypatch):
    from vixl import host

    def brand(app, served):
        @app.put("/w/{ws}/brand")
        def put_brand(ws: str):
            served.workspace(ws)
            return {"ok": True}

    monkeypatch.setattr(host, "ROUTES", [brand])
    test = TestClient(app_for(tmp_path / "root"), headers=AUTH)
    assert test.put("/w/team/brand").json() == {"ok": True}
    assert TestClient(app_for(tmp_path / "root")).put("/w/team/brand").status_code == 401


# ------------------------------------------------------------------------------- #538 documents and operations


def create(client, ws="team", **body):
    response = client.post(f"/w/{ws}/documents", json={"width": 200, "height": 120, "background": "#ffffff",
                                                       "workspace_fonts": False, **body})
    assert response.status_code == 201, response.text
    return response.json()


BOX = {"type": "shape", "shape": "rectangle", "name": "box", "x": 10, "y": 10, "width": 40, "height": 30,
       "fill": "#d63c3c"}


def test_documents_get_opaque_ids_an_index_and_revision_one(client, tmp_path):
    made = create(client, name="Spring card")
    doc = made["id"]
    assert re.fullmatch(r"d_[0-9a-f]{8}", doc) and made["revision"] == 1 and made["name"] == "Spring card"
    assert made["canvas"]["width"] == 200
    folder = tmp_path / "root" / "team"
    assert (folder / f"{doc}.vixl").is_file()
    index = json.loads((folder / ".vixl-host" / "index.json").read_text())
    assert index["documents"][doc]["revision"] == 1 and index["documents"][doc]["path"] == f"{doc}.vixl"
    listed = client.get("/w/team/documents").json()["documents"]
    assert [entry["id"] for entry in listed] == [doc]
    assert client.get("/w/team/documents/d_00000000").status_code == 404
    assert client.get("/w/team/documents/..%2Fx").status_code == 404
    assert client.get(f"/w/other/documents/{doc}").status_code == 404  # ids are per workspace


def test_each_change_raises_the_revision_and_a_stale_one_conflicts(client):
    doc = create(client)["id"]
    first = client.post(f"/w/team/documents/{doc}/operations", json={"operations": [BOX], "if_revision": 1})
    assert first.status_code == 200 and first.json()["revision"] == 2
    dry = client.post(f"/w/team/documents/{doc}/operations",
                      json={"operations": [{**BOX, "name": "other"}], "dry_run": True})
    assert dry.json()["revision"] == 2  # a dry run changes nothing
    stale = client.post(f"/w/team/documents/{doc}/operations",
                        json={"operations": [{**BOX, "name": "late"}], "if_revision": 1})
    assert stale.status_code == 409
    body = stale.json()
    assert body["code"] == "revision_conflict" and body["details"]["revision"] == 2 and body["hint"]
    state = client.get(f"/w/team/documents/{doc}").json()
    assert state["revision"] == 2 and [layer["name"] for layer in state["layers"]] == ["box"]


def test_a_retried_request_id_applies_once_and_a_different_body_conflicts(client):
    doc = create(client)["id"]
    request = {"operations": [BOX], "request_id": "op-1"}
    first = client.post(f"/w/team/documents/{doc}/operations", json=request).json()
    again = client.post(f"/w/team/documents/{doc}/operations", json=request).json()
    assert again["replayed"] is True and again["revision"] == first["revision"] == 2
    assert client.get(f"/w/team/documents/{doc}").json()["layer_count"] == 1
    other = client.post(f"/w/team/documents/{doc}/operations",
                        json={"operations": [{**BOX, "x": 99}], "request_id": "op-1"})
    assert other.status_code == 409 and other.json()["code"] == "request_id_conflict"
    # Request ids are scoped to their workspace.
    elsewhere = create(client, ws="lab")["id"]
    assert client.post(f"/w/lab/documents/{elsewhere}/operations", json=request).json()["revision"] == 2


def test_a_retried_create_makes_one_document(client):
    first = create(client, request_id="new-1")
    again = create(client, request_id="new-1")
    assert again["id"] == first["id"] and again["replayed"] is True
    assert len(client.get("/w/team/documents").json()["documents"]) == 1


def test_import_then_blob_round_trips_the_document(client, tmp_path):
    from vixl import Project

    source = Project(160, 90, "#102030")
    source.apply([BOX, {"type": "text", "name": "title", "text": "Hello", "size": 20, "x": 60, "y": 30}])
    source.save(tmp_path / "card.vixl")
    data = (tmp_path / "card.vixl").read_bytes()
    made = client.post("/w/team/documents/import?name=card", content=data)
    assert made.status_code == 201, made.text
    doc = made.json()["id"]
    assert made.json()["revision"] == 1 and made.json()["untrusted"]  # layer names and text are document data
    blob = client.get(f"/w/team/documents/{doc}/blob")
    assert blob.status_code == 200 and blob.headers["x-vixl-revision"] == "1"
    (tmp_path / "back.vixl").write_bytes(blob.content)
    assert Project.load(tmp_path / "back.vixl").state == Project.load(tmp_path / "card.vixl").state
    refused = client.post("/w/team/documents/import", content=b"not a zip")
    assert refused.status_code == 400 and set(refused.json()) >= {"code", "message", "hint"}
    assert len(client.get("/w/team/documents").json()["documents"]) == 1
    assert not list((tmp_path / "root" / "team" / ".vixl-host" / "tmp").iterdir())


def test_layer_bounds_equal_the_measured_render_bounds(client, tmp_path):
    from vixl import Project

    doc = create(client)["id"]
    client.post(f"/w/team/documents/{doc}/operations", json={"operations": [
        BOX, {**BOX, "name": "turned", "x": 100, "rotation": 30},
        {"type": "group", "name": "pair", "targets": ["box", "turned"]}]})
    state = client.get(f"/w/team/documents/{doc}").json()
    project = Project.load(tmp_path / "root" / "team" / f"{doc}.vixl")
    for layer in state["layers"]:
        measured = project.measure(target=layer["id"])["bounds"]
        assert layer["bounds"] == pytest.approx(measured, abs=1e-3), layer["name"]
    parents = {layer["name"]: layer["parent"] for layer in state["layers"]}
    assert parents["box"] == next(layer["id"] for layer in state["layers"] if layer["name"] == "pair")
    assert client.get(f"/w/team/documents/{doc}?max_layers=1").json()["truncated"] is True


def test_operations_refuse_files_and_unknown_fields(client):
    doc = create(client)["id"]
    linked = client.post(f"/w/team/documents/{doc}/operations",
                         json={"operations": [{"type": "add", "path": "/etc/passwd"}]})
    assert linked.status_code in (400, 403)
    unknown = client.post(f"/w/team/documents/{doc}/operations", json={"operations": [BOX], "operations_path": "x"})
    assert unknown.status_code == 400 and unknown.json()["details"]["field"] == "operations_path"


def test_assets_take_raw_bytes_and_bump_the_revision(client):
    import io

    from PIL import Image

    doc = create(client)["id"]
    stream = io.BytesIO()
    Image.new("RGB", (8, 6), "#2c5aa0").save(stream, format="PNG")
    added = client.post(f"/w/team/documents/{doc}/assets?name=photo&credit=Me", content=stream.getvalue())
    assert added.status_code == 200, added.text
    assert added.json()["revision"] == 2
    assert client.post(f"/w/team/documents/{doc}/assets", content=b"").status_code == 400


def test_svg_artwork_imports_into_a_document(client):
    doc = create(client)["id"]
    svg = (b'<svg xmlns="http://www.w3.org/2000/svg" width="40" height="20"><rect id="bar" width="40" '
           b'height="20" fill="#123456"/></svg>')
    imported = client.post(f"/w/team/documents/{doc}/import?format=svg&name=logo", content=svg)
    assert imported.status_code == 200, imported.text
    assert imported.json()["revision"] == 2


def test_delete_removes_the_working_copy_and_the_index_entry(client, tmp_path):
    doc = create(client)["id"]
    assert client.delete(f"/w/team/documents/{doc}?if_revision=7").status_code == 409
    assert client.delete(f"/w/team/documents/{doc}").json() == {"deleted": doc, "revision": 1}
    assert not (tmp_path / "root" / "team" / f"{doc}.vixl").exists()
    assert client.get(f"/w/team/documents/{doc}").status_code == 404
    assert client.get("/w/team/documents").json()["documents"] == []


def test_a_call_over_the_timeout_continues_as_a_job_and_its_retry_points_at_it(tmp_path, monkeypatch):
    import threading
    import time

    from vixl.call_limits import CallLimits
    from vixl.interfaces import Session

    gate = threading.Event()
    original = Session.apply_reviewed

    def slow(self, *args, **kwargs):
        gate.wait(5)
        return original(self, *args, **kwargs)

    doc = create(TestClient(app_for(tmp_path / "root"), headers=AUTH))["id"]
    test = TestClient(app_for(tmp_path / "root", call_limits=CallLimits(timeout=0.05)), headers=AUTH)
    monkeypatch.setattr(Session, "apply_reviewed", slow)
    request = {"operations": [BOX], "request_id": "slow-1"}
    started = test.post(f"/w/team/documents/{doc}/operations", json=request)
    assert started.status_code == 202
    job = started.json()["job_id"]
    gate.set()
    for _ in range(100):
        status = test.get(f"/jobs/{job}?wait=1").json()
        if status["status"] != "running":
            break
        time.sleep(0.05)
    assert status["status"] == "completed" and status["kind"] == "call"
    assert test.get(f"/jobs/{job}/result").json()["revision"] == 2
    assert test.post(f"/w/team/documents/{doc}/operations", json=request).json()["replayed"] is True
    assert test.get("/jobs/nope").status_code == 404
