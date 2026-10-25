"""``vixl host``: the multi-workspace server for host applications (#537-#541)."""

import os

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
