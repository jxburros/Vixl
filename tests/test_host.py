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


# ---------------------------------------------------------------------------------- #539 compose, preview, check


def noisy_png(width=900, height=700):
    import io

    import numpy as np
    from PIL import Image

    pixels = np.random.default_rng(1).integers(0, 256, (height, width, 3), dtype=np.uint8)
    stream = io.BytesIO()
    Image.fromarray(pixels).save(stream, format="PNG")
    return stream.getvalue()


def test_preview_respects_max_px_max_bytes_page_and_region(client):
    import io

    from PIL import Image

    doc = create(client, width=1600, height=1200)["id"]
    client.post(f"/w/team/documents/{doc}/assets?name=noise", content=noisy_png())
    big = client.post(f"/w/team/documents/{doc}/preview", json={"max_px": 1024, "max_bytes": 4_194_304})
    small = client.post(f"/w/team/documents/{doc}/preview", json={"max_px": 300, "max_bytes": 65_536})
    assert big.status_code == small.status_code == 200
    assert big.headers["content-type"] == "image/png" and big.headers["x-vixl-revision"] == "2"
    assert len(small.content) <= 65_536 < len(big.content)
    with Image.open(io.BytesIO(small.content)) as image:
        assert max(image.size) <= 300
        assert image.size == (int(small.headers["x-vixl-width"]), int(small.headers["x-vixl-height"]))
    region = client.post(f"/w/team/documents/{doc}/preview", json={"region": [0, 0, 200, 100], "max_px": 1024})
    with Image.open(io.BytesIO(region.content)) as image:
        assert image.size[0] / image.size[1] == pytest.approx(2, rel=0.05)
    bad = client.post(f"/w/team/documents/{doc}/preview", json={"max_bytes": 10})
    assert bad.status_code == 400 and bad.json()["code"]
    assert client.post(f"/w/team/documents/{doc}/preview", json={"max_width": 10}).status_code == 400


def test_preview_page_all_is_a_contact_sheet(client):
    doc = create(client, width=320, height=180)["id"]
    applied = client.post(f"/w/team/documents/{doc}/operations", json={"operations": [
        {"type": "page", "action": "add", "name": "One"}, {"type": "page", "action": "add", "name": "Two"}]})
    assert applied.status_code == 200, applied.text
    sheet = client.post(f"/w/team/documents/{doc}/preview", json={"page": "all", "max_px": 512})
    first = client.post(f"/w/team/documents/{doc}/preview", json={"page": 1, "max_px": 512})
    assert sheet.status_code == first.status_code == 200 and sheet.content != first.content


def test_check_findings_carry_rule_severity_action_and_layer_id(client):
    doc = create(client, width=300, height=200)["id"]
    applied = client.post(f"/w/team/documents/{doc}/operations", json={"operations": [
        {"type": "text", "name": "headline", "text": "Hello", "size": 40, "x": 260, "y": 20, "color": "#111111"}]})
    layer_id = next(iter(applied.json()["changed"])) if isinstance(applied.json().get("changed"), dict) else None
    report = client.post(f"/w/team/documents/{doc}/check", json={"checks": ["bounds"]}).json()
    assert report["passed"] is False and report["outcome"]["validation"] == "failed"
    assert report["revision"] == 2 and report["counts"]["errors"] >= 1
    finding = report["findings"][0]
    assert {"rule", "severity", "action", "message", "layer_id", "page"} <= set(finding)
    assert finding["rule"].startswith("bounds") and finding["action"] == "fix"
    state = client.get(f"/w/team/documents/{doc}").json()
    assert finding["layer_id"] == state["layers"][0]["id"]
    assert layer_id is None or layer_id == finding["layer_id"]
    assert client.post(f"/w/team/documents/{doc}/check", json={"profile": "draft"}).status_code == 200
    unknown = client.post(f"/w/team/documents/{doc}/check", json={"chekcs": ["bounds"]})
    assert unknown.status_code == 400 and "checks" in unknown.json()["message"]


def test_compose_rebuilds_the_document_and_raises_the_revision(client, monkeypatch):
    monkeypatch.setenv("VIXL_AUTO_FONTS", "off")
    doc = create(client, width=400, height=300)["id"]
    piece = {"layout": {"name": "hero-statement", "title": "Make it simple", "subtitle": "One idea, said well.",
                        "seed": 7}, "seed": 7, "preview": True}
    dry = client.post(f"/w/team/documents/{doc}/compose", json={**piece, "dry_run": True})
    assert dry.status_code == 200, dry.text
    assert dry.json()["revision"] == 1 and dry.json()["preview_base64"]
    assert client.get(f"/w/team/documents/{doc}").json()["layer_count"] == 0
    made = client.post(f"/w/team/documents/{doc}/compose", json={**piece, "if_revision": 1, "request_id": "c-1"})
    assert made.status_code == 200, made.text
    result = made.json()
    assert result["revision"] == 2 and "layout" in result["steps"] and "check" in result
    state = client.get(f"/w/team/documents/{doc}").json()
    assert state["canvas"]["width"] == 400 and state["layer_count"] > 0
    assert client.post(f"/w/team/documents/{doc}/compose", json={**piece, "if_revision": 1}).status_code == 409
    assert client.post(f"/w/team/documents/{doc}/compose", json={**piece, "exports": ["a.png"]}).status_code == 400
    assert not list((client.app.state.host.root / "team" / ".vixl-host" / "tmp").iterdir())


def test_a_host_composed_piece_renders_like_an_in_process_compose(client, tmp_path, monkeypatch):
    """Stands in for the plan's golden image: the visual fixture set is full (tests/visual allows 30)."""
    from vixl import Project
    from vixl.compose import run

    monkeypatch.setenv("VIXL_AUTO_FONTS", "off")
    piece = {"layout": {"name": "event-poster", "title": "Jazz night", "body": "Fridays at nine", "seed": 3},
             "seed": 3, "house_style": "on"}
    doc = create(client, width=240, height=320, seed=3)["id"]
    assert client.post(f"/w/team/documents/{doc}/compose", json=piece).status_code == 200
    hosted = Project.load(tmp_path / "root" / "team" / f"{doc}.vixl")
    local = tmp_path / "local"
    local.mkdir()
    run(local, path="piece.vixl", width=240, height=320, **piece)
    direct = Project.load(local / "piece.vixl")
    assert hosted.render().tobytes() == direct.render().tobytes()


# ------------------------------------------------------------------------------------------- #540 export jobs


def exported(client, doc, ws="team", **body):
    started = client.post(f"/w/{ws}/documents/{doc}/exports", json=body)
    assert started.status_code == 202, started.text
    job = started.json()
    assert job["job_id"] and job["download"] == f"/jobs/{job['job_id']}/download"
    status = client.get(f"/jobs/{job['job_id']}?wait=20").json()
    return job["job_id"], status


@pytest.mark.parametrize("fmt, media, magic", [
    ("PNG", "image/png", b"\x89PNG"), ("PDF", "application/pdf", b"%PDF"),
    ("PPTX", "application/vnd.openxmlformats-officedocument.presentationml.presentation", b"PK")])
def test_png_pdf_and_pptx_export_through_a_job(client, tmp_path, fmt, media, magic):
    doc = create(client)["id"]
    client.post(f"/w/team/documents/{doc}/operations", json={"operations": [BOX]})
    ident, status = exported(client, doc, format=fmt)
    assert status["status"] == "completed" and status["kind"] == "export", status
    assert status["progress"]["fraction"] == 1.0 and status["revision"] == 2 and status["expires_at"]
    download = client.get(f"/jobs/{ident}/download")
    assert download.status_code == 200 and download.headers["content-type"].startswith(media)
    assert download.content.startswith(magic)
    assert f'{doc}.{fmt.lower()}' in download.headers["content-disposition"]
    assert (tmp_path / "root" / "team" / ".vixl-host" / "jobs" / ident / f"{doc}.{fmt.lower()}").is_file()


def test_progress_never_goes_back():
    from concurrent.futures import Future

    from vixl.call_limits import RestJobs

    jobs = RestJobs()
    job = jobs.get(jobs.add("exports", Future()))
    seen = []
    for done, total in ((0, 4), (2, 4), (1, 4), (3, 10), (4, 4)):
        jobs.progress(job, done, total)
        seen.append(job["progress"]["fraction"])
    assert seen == sorted(seen) and seen[-1] == 1.0 and seen[2] == 0.5


def test_events_stream_progress_then_one_terminal_event(client, monkeypatch):
    from vixl import plugins

    delivered = []
    original = plugins.hooks
    monkeypatch.setattr(plugins, "hooks", lambda point: (delivered.append,) if point == "job-complete"
                        else original(point))
    doc = create(client)["id"]
    ident = client.post(f"/w/team/documents/{doc}/exports", json={"format": "PNG"}).json()["job_id"]
    with client.stream("GET", f"/jobs/{ident}/events") as stream:
        assert stream.headers["content-type"].startswith("text/event-stream")
        lines = [line for line in stream.iter_lines() if line]
    kinds = [line.split(": ", 1)[1] for line in lines if line.startswith("event: ")]
    assert kinds.count("job-complete") == 1 and kinds[-1] == "job-complete"
    payloads = [json.loads(line.split(": ", 1)[1]) for line in lines if line.startswith("data: ")]
    fractions = [p["progress"]["fraction"] for p in payloads[:-1] if (p.get("progress") or {}).get("fraction")
                 is not None]
    assert fractions == sorted(fractions)
    event = payloads[-1]
    assert {"event", "kind", "id", "status", "state", "counts", "report", "workspace", "notify", "error"} <= set(event)
    assert (event["event"], event["kind"], event["id"], event["status"], event["workspace"]) == (
        "job-complete", "export", ident, "completed", "team")
    assert event["counts"]["files"] == 1 and event["report"] == f"/jobs/{ident}/download"
    assert delivered == [event]  # the plugins' job-complete hook got it once
    again = [line for line in client.get(f"/jobs/{ident}/events").text.splitlines() if line.startswith("event: ")]
    assert again == ["event: job-complete"]


def test_a_failed_export_reports_a_structured_error(client):
    doc = create(client)["id"]
    ident, status = exported(client, doc, format="TTF")
    assert status["status"] == "failed"
    assert set(status["error"]) >= {"code", "message", "hint"}
    refused = client.get(f"/jobs/{ident}/download")
    assert refused.status_code == 409 and refused.json()["code"] == "job_failed"


def test_bad_export_requests_are_refused_before_a_job_starts(client):
    doc = create(client)["id"]
    assert client.post(f"/w/team/documents/{doc}/exports", json={"format": "BMP"}).status_code == 400
    unknown = client.post(f"/w/team/documents/{doc}/exports", json={"format": "PNG", "options": {"scael": 2}})
    assert unknown.status_code == 400 and "scale" in unknown.json()["message"]


def test_export_limits_come_from_the_call_limits(tmp_path):
    from vixl.call_limits import CallLimits

    test = TestClient(app_for(tmp_path / "root", call_limits=CallLimits(max_megapixels=0.05)), headers=AUTH)
    doc = create(test)["id"]
    refused = test.post(f"/w/team/documents/{doc}/exports", json={"format": "PNG", "options": {"scale": 4}})
    assert refused.status_code == 413
    assert refused.json()["code"] == "limit_exceeded" and refused.json()["details"]["limit"] == "max_megapixels"


def test_a_download_after_the_ttl_is_gone(tmp_path):
    import time

    test = TestClient(app_for(tmp_path / "root", job_ttl=0.3), headers=AUTH)
    assert test.get("/host/info").json()["job_ttl"] == 0.3
    doc = create(test)["id"]
    ident, status = exported(test, doc, format="PNG")
    assert status["status"] == "completed"
    folder = tmp_path / "root" / "team" / ".vixl-host" / "jobs" / ident
    assert folder.is_dir()
    time.sleep(0.4)
    gone = test.get(f"/jobs/{ident}/download")
    assert gone.status_code == 410 and gone.json()["code"] == "expired"
    assert not folder.exists()  # the sweeper deleted it
    assert test.get(f"/jobs/{ident}").json()["status"] == "expired"


def test_the_sweeper_removes_results_an_earlier_process_left(tmp_path):
    import os as _os

    from vixl.host import Host

    host = Host(tmp_path / "root", job_ttl=60)
    stale = host.state_dir("team", "jobs", "0123456789abcdef")
    (stale / "old.png").write_bytes(b"x")
    _os.utime(stale, (0, 0))
    fresh = host.state_dir("team", "jobs", "fedcba9876543210")
    host.sweep(orphans=True)
    assert not stale.exists() and fresh.exists()


# --------------------------------------------------------------------------- #541 catalogs and the studio profile


def test_each_catalog_kind_equals_the_catalog_bundle_section(client):
    from vixl.catalog import BUILDERS

    for kind, build in BUILDERS.items():
        response = client.get(f"/catalog/{kind}")
        assert response.status_code == 200, kind
        assert response.json() == json.loads(json.dumps(build())), kind
    assert client.get("/catalog/nope").status_code == 404


def test_the_guide_catalog_is_the_rest_guide(client, tmp_path):
    from vixl import Project
    from vixl.briefs import guide
    from vixl.interfaces import create_app

    Project(10, 10).save(tmp_path / "one.vixl")
    rest = TestClient(create_app(tmp_path / "one.vixl"))
    for brief in ("a poster for a jazz night", None):
        query = f"?brief={brief}" if brief else ""
        hosted, served = client.get(f"/catalog/guide{query}").json(), rest.get(f"/guide{query}").json()
        for found in (hosted, served):  # the suggested direction is a fresh roll on each call
            found.pop("direction", None), found.pop("recommendations", None)
        assert hosted == served
    seeded = client.get("/catalog/guide?brief=a jazz poster&seed=4").json()
    assert seeded == json.loads(json.dumps(guide("a jazz poster", seed=4)))


def test_the_capabilities_catalog_has_the_host_column_and_probes(client):
    from vixl.interface_capabilities import matrix

    found = client.get("/catalog/capabilities").json()
    assert found["interfaces"] == matrix() and "Host" in found["interfaces"]["Authentication"]
    assert set(found["host"]) == {"pptx", "pdf_import", "ffmpeg", "ai"}


def test_operations_catalog_gives_field_schemas(client):
    found = client.get("/catalog/operations?name=text,shape").json()["operations"]
    assert set(found) == {"text", "shape"} and "properties" in found["text"]
    assert client.get("/catalog/operations").status_code == 400
    assert client.get("/catalog/operations?name=nope").status_code == 404


def test_the_studio_profile_names_real_endpoints_with_valid_input_schemas(client):
    import jsonschema

    profile = client.get("/catalog/tools?profile=studio").json()
    tools = profile["tools"]
    assert profile["host_api"] == 1 and 10 <= len(tools) <= 14
    sample = {"{ws}": "team", "{id}": "d_1a2b3c4d", "{job_id}": "0123456789abcdef", "{kind}": "sizes"}
    for tool in tools:
        url = tool["path"]
        for key, value in sample.items():
            url = url.replace(key, value)
        assert any(route.path_regex.fullmatch(url) and tool["method"] in route.methods
                   for route in client.app.routes if hasattr(route, "methods")), tool["name"]
        jsonschema.Draft202012Validator.check_schema(tool["input_schema"])
        assert "vixl_" not in tool["description"] and tool["description"].endswith(".")
    names = [tool["name"] for tool in tools]
    assert len(set(names)) == len(names)
    apply = next(tool for tool in tools if tool["name"] == "apply_operations")["input_schema"]
    jsonschema.validate({"id": "d_1a2b3c4d", "operations": [{"type": "text", "text": "Hi"}]}, apply)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate({"id": "d_1a2b3c4d", "operations": [{"type": "no-such-operation"}]}, apply)
    assert client.get("/catalog/tools?profile=nope").status_code == 404


def test_the_studio_profile_inputs_are_accepted_by_the_endpoints(client):
    """A call built from each input schema's fields reaches its endpoint without an unknown-field error."""
    import jsonschema

    from vixl.host import tool_profile

    schemas = {tool["name"]: tool["input_schema"] for tool in tool_profile("studio")["tools"]}
    request = {"width": 200, "height": 120, "workspace_fonts": False}
    jsonschema.validate(request, schemas["create_document"])
    doc = client.post("/w/team/documents", json=request).json()["id"]
    calls = {"apply_operations": {"operations": [BOX], "check": True, "if_revision": 1},
             "check_document": {"checks": ["bounds"]}, "preview_document": {"max_px": 200, "page": 1},
             "compose_document": {"dry_run": True, "check": False}}
    for name, body in calls.items():
        jsonschema.validate({"id": doc, **body}, schemas[name])
        path = next(tool["path"] for tool in tool_profile("studio")["tools"] if tool["name"] == name)
        response = client.post(path.replace("{ws}", "team").replace("{id}", doc), json=body)
        assert response.status_code == 200, (name, response.text)
