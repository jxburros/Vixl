"""Service policy: REST path confinement (#668), bearer-token handling (#674), cleartext warnings (#624)."""

import pytest

from vixl import Project
from vixl.errors import VixlError

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from vixl import interfaces  # noqa: E402
from vixl.interfaces import create_app, mcp_http_app, mcp_server  # noqa: E402

TOKEN = "a-test-token-that-is-long-enough"


@pytest.fixture
def form(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (tmp_path / "outside.csv").write_text("name\nRows outside the workspace\n")
    (workspace / "rows.csv").write_text("name\nAda\n")
    p = Project(200, 80)
    p.apply({"type": "field", "name": "name", "kind": "text", "label": "Name", "size": 10, "x": 10, "y": 10,
             "width": 120, "height": 20})
    path = workspace / "form.vixl"
    p.save(path)
    return path


# -- #668: REST /check, /measure and /spacing


@pytest.mark.parametrize("sample", ["../outside.csv", "/etc/hostname"])
def test_rest_check_refuses_a_sample_outside_the_workspace(form, sample):
    with TestClient(create_app(form)) as client:
        response = client.post("/check", json={"checks": ["form"], "sample": sample})
    assert response.status_code == 403 and response.json()["error"] == "forbidden"


def test_rest_check_reads_a_workspace_sample_and_hides_missing_paths(form):
    with TestClient(create_app(form)) as client:
        assert client.post("/check", json={"checks": ["form"], "sample": "rows.csv"}).status_code == 200
        assert client.post("/check", json={"checks": ["form"], "sample": "worst"}).status_code == 200
        missing = client.post("/check", json={"checks": ["form"], "sample": "missing.csv"})
    assert missing.status_code == 404 and missing.json()["error"] == "not_found"
    assert str(form.parent) not in missing.text


def test_rest_check_measure_and_spacing_name_unknown_fields(form):
    with TestClient(create_app(form)) as client:
        for route, body in (("/check", {"bogus": 1}), ("/measure", {"point": [1, 1], "bogus": 1}),
                            ("/spacing", {"bogus": 1})):
            response = client.post(route, json=body)
            assert response.status_code == 400 and "'bogus'" in response.json()["message"], route
        # The fields the routes do read still work, including vixl_check's repair and waivers.
        assert client.post("/check", json={"checks": ["bounds"], "waivers": False, "limit": 5}).status_code == 200
        assert client.post("/measure", json={"point": [1, 1]}).status_code == 200


def test_mcp_check_confines_the_sample_through_the_shared_session_path(form):
    import asyncio

    server = mcp_server(workspace=form.parent)

    async def run():
        return await server.call_tool("vixl_check", {"document": "form.vixl", "checks": ["form"],
                                                     "sample": "../outside.csv"})

    with pytest.raises(Exception, match="outside the workspace"):
        asyncio.run(run())


# -- #674: bearer tokens


def apps(path):
    yield "rest", create_app(path, token=TOKEN)
    yield "mcp", mcp_http_app(mcp_server(workspace=path.parent), token=TOKEN)


def probe(kind):
    return "/document" if kind == "rest" else "/mcp"


def test_non_ascii_bearer_is_401_not_500(form):
    for kind, app in apps(form):
        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.get(probe(kind), headers={"Authorization": "Bearer s\xe9cret".encode("latin-1")})
            assert response.status_code == 401, kind


def test_short_tokens_are_refused(form):
    with pytest.raises(VixlError) as caught:
        create_app(form, token="abc")
    assert caught.value.code == "authentication_required" and "24" in str(caught.value)
    with pytest.raises(VixlError):
        mcp_http_app(mcp_server(workspace=form.parent), token="x" * 23)
    with pytest.raises(VixlError):
        interfaces.serve(form, host="0.0.0.0", token="short")


def test_repeated_failures_are_throttled(form):
    for kind, app in apps(form):
        with TestClient(app) as client:
            for _ in range(interfaces.Failures.LIMIT):
                assert client.get(probe(kind), headers={"Authorization": "Bearer wrong"}).status_code == 401
            throttled = client.get(probe(kind), headers={"Authorization": "Bearer " + TOKEN})
            assert throttled.status_code == 429 and int(throttled.headers["Retry-After"]) >= 1, kind


def test_throttle_forgets_old_failures_and_caps_clients():
    failures = interfaces.Failures()
    for second in range(failures.LIMIT):
        failures.failed("1.2.3.4", now=float(second))
    assert failures.retry_after("1.2.3.4", now=float(failures.LIMIT)) > 0
    assert failures.retry_after("1.2.3.4", now=failures.WINDOW + failures.LIMIT) == 0
    for n in range(failures.MAX_CLIENTS + 10):
        failures.failed(f"10.0.{n // 256}.{n % 256}", now=0.0)
    assert len(failures._seen) == failures.MAX_CLIENTS


# -- #624: cleartext warning and direct TLS


@pytest.fixture
def no_server(monkeypatch):
    uvicorn = pytest.importorskip("uvicorn")
    calls = []
    monkeypatch.setattr(uvicorn, "run", lambda app, **kw: calls.append(kw))
    return calls


def test_serve_warns_on_plain_http_remote_bind(form, no_server, capsys):
    interfaces.serve(form, host="0.0.0.0", token=TOKEN)
    assert "cleartext" in capsys.readouterr().err and "ssl_certfile" not in no_server[-1]
    interfaces.serve(form, host="127.0.0.1")
    assert "cleartext" not in capsys.readouterr().err
    interfaces.serve(form, host="0.0.0.0", token=TOKEN, tls=("cert.pem", "key.pem"))
    assert "cleartext" not in capsys.readouterr().err
    assert no_server[-1]["ssl_certfile"] == "cert.pem" and no_server[-1]["ssl_keyfile"] == "key.pem"
    with pytest.raises(VixlError):
        interfaces.serve(form, host="0.0.0.0", token=TOKEN, tls=("cert.pem", None))


def test_serve_mcp_warns_on_plain_http_remote_bind(form, no_server, capsys):
    interfaces.serve_mcp(mcp_server(workspace=form.parent), host="0.0.0.0", token=TOKEN)
    assert "cleartext" in capsys.readouterr().err


def test_cli_offline_and_tls_flags_reach_the_server(form, no_server, monkeypatch):
    from vixl import cli

    monkeypatch.setenv("VIXL_OFFLINE", "")  # Restored after the test; the CLI sets it for the process.
    monkeypatch.setenv("VIXL_API_TOKEN", TOKEN)
    cli.dispatch(["-p", str(form), "serve", "--host", "0.0.0.0", "--offline", "--tls-cert", "c.pem",
                  "--tls-key", "k.pem"])
    import os

    assert os.environ["VIXL_OFFLINE"] == "1" and no_server[-1]["ssl_certfile"] == "c.pem"
