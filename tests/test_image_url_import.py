"""Image (and font) imports from URLs: fetch policy, SSRF refusals and provenance. All offline."""

import asyncio
import hashlib
from io import BytesIO
import json
from pathlib import Path

import httpx
from PIL import Image
import pytest

from vixl import Project, VixlError
from vixl import fetch
from vixl.interfaces import create_app, mcp_server
from vixl.model import Limits

REAL_CLIENT = httpx.Client
PUBLIC = "93.184.216.34"
PROXY_VARS = ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy", "ALL_PROXY", "all_proxy",
              "NO_PROXY", "no_proxy")


def png(color="red", size=(8, 6)):
    stream = BytesIO()
    Image.new("RGBA", size, color).save(stream, format="PNG")
    return stream.getvalue()


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    for name in PROXY_VARS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.delenv(fetch.ALLOW_PRIVATE_ENV, raising=False)
    dns = {"images.example": [PUBLIC], "fonts.example": [PUBLIC], "cdn.example": [PUBLIC],
           "internal.example": ["10.0.0.7"], "mixed.example": [PUBLIC, "127.0.0.1"]}

    def resolve(host, port):
        if host not in dns:
            raise VixlError("fetch_failed", f"Cannot resolve host {host!r}")
        return dns[host]

    monkeypatch.setattr(fetch, "resolve", resolve)
    return dns


@pytest.fixture
def served(monkeypatch):
    """Route every httpx client to a handler; returns the list of requests seen."""
    seen, routes = [], {}

    def handler(request):
        seen.append(request)
        reply = routes.get(request.url.path, httpx.Response(404))
        return reply(request) if callable(reply) else reply

    def client(**kw):
        kw["trust_env"] = False
        return REAL_CLIENT(transport=httpx.MockTransport(handler), **kw)

    monkeypatch.setattr(httpx, "Client", client)
    return seen, routes


def test_url_import_records_source_credit_and_license(served):
    seen, routes = served
    data = png()
    routes["/cat.png"] = httpx.Response(200, content=data, headers={"content-type": "application/octet-stream"})
    project = Project(64, 64)
    result = project.import_image(url="https://images.example/cat.png", name="cat",
                                  credit="Photo: Ana Ruiz", license="CC BY 4.0")
    digest = hashlib.sha256(data).hexdigest()
    assert result["source"]["url"] == "https://images.example/cat.png"
    assert result["source"]["bytes"] == len(data) and result["source"]["sha256"] == digest
    assert result["source"]["fetched_at"].endswith("Z")
    assert (result["credit"], result["license"]) == ("Photo: Ana Ruiz", "CC BY 4.0")
    assert (result["width"], result["height"]) == (8, 6)
    # Connected to the checked address; the host name stays in Host and SNI.
    request = seen[0]
    assert request.url.host == PUBLIC and request.headers["host"] == "images.example"
    assert request.extensions["sni_hostname"] == "images.example"
    provenance = project.layer("cat")["provenance"]
    assert provenance["source"]["url"] == "https://images.example/cat.png"
    assert provenance["credit"] == "Photo: Ana Ruiz" and provenance["license"] == "CC BY 4.0"
    from vixl.changes import summarize
    from vixl.validation import dependencies

    brief = next(layer for layer in summarize(project)["layers"] if layer["name"] == "cat")
    assert brief["source_url"] == "https://images.example/cat.png" and brief["license"] == "CC BY 4.0"
    assert dependencies(project)["attributions"][0]["credit"] == "Photo: Ana Ruiz"


@pytest.mark.parametrize("url", [
    "https://127.0.0.1/x.png", "https://10.1.2.3/x.png", "https://169.254.169.254/latest/meta-data",
    "https://[::1]/x.png", "https://[::ffff:127.0.0.1]/x.png", "https://[64:ff9b::a00:1]/x.png",
    "https://0.0.0.0/x.png", "https://224.0.0.1/x.png", "https://100.64.0.1/x.png",
    "https://internal.example/x.png", "https://mixed.example/x.png",
])
def test_private_and_special_addresses_are_refused_before_connecting(served, url):
    seen, _ = served
    project = Project(16, 16)
    with pytest.raises(VixlError) as caught:
        project.import_image(url=url)
    assert caught.value.code == "unsafe_url" and not seen
    assert not project.state["layers"]


@pytest.mark.parametrize("url", ["http://images.example/x.png", "ftp://images.example/x.png",
                                 "https://user:pw@images.example/x.png", "file:///etc/passwd"])
def test_scheme_and_credentials_are_refused(served, url):
    with pytest.raises(VixlError) as caught:
        Project(16, 16).import_image(url=url)
    assert caught.value.code == "unsafe_url" and not served[0]


def test_escape_hatch_allows_intranet_hosts(served, monkeypatch):
    _, routes = served
    routes["/x.png"] = httpx.Response(200, content=png())
    monkeypatch.setenv(fetch.ALLOW_PRIVATE_ENV, "1")
    assert Project(16, 16).import_image(url="https://internal.example/x.png")["width"] == 8


def test_redirects_are_revalidated_and_bounded(served):
    seen, routes = served
    data = png("blue")
    routes["/start"] = httpx.Response(302, headers={"location": "https://cdn.example/final.png"})
    routes["/final.png"] = httpx.Response(200, content=data)
    result = Project(16, 16).import_image(url="https://images.example/start")
    assert result["source"]["url"] == "https://cdn.example/final.png"
    assert result["source"]["requested_url"] == "https://images.example/start"
    assert [r.headers["host"] for r in seen] == ["images.example", "cdn.example"]

    seen.clear()
    routes["/evil"] = httpx.Response(301, headers={"location": "https://169.254.169.254/latest"})
    with pytest.raises(VixlError) as caught:
        Project(16, 16).import_image(url="https://images.example/evil")
    assert caught.value.code == "unsafe_url" and len(seen) == 1
    routes["/down"] = httpx.Response(302, headers={"location": "http://cdn.example/final.png"})
    with pytest.raises(VixlError, match="HTTPS"):
        Project(16, 16).import_image(url="https://images.example/down")
    routes["/loop"] = httpx.Response(302, headers={"location": "/loop"})
    with pytest.raises(VixlError, match="redirected more than"):
        Project(16, 16).import_image(url="https://images.example/loop")


def test_size_cap_and_non_image_content(served):
    _, routes = served
    limits = Limits(max_asset_bytes=1000)
    routes["/big.png"] = httpx.Response(200, content=b"\x89PNG" + b"\0" * 5000)
    with pytest.raises(VixlError) as caught:
        Project(16, 16, limits=limits).import_image(url="https://images.example/big.png")
    assert caught.value.code == "resource_limit"

    def chunked(request):
        return httpx.Response(200, content=iter([b"\0" * 600, b"\0" * 600]))

    routes["/stream.png"] = chunked
    with pytest.raises(VixlError) as caught:
        Project(16, 16, limits=limits).import_image(url="https://images.example/stream.png")
    assert caught.value.code == "resource_limit"
    routes["/page.png"] = httpx.Response(200, content=b"<html>not an image</html>",
                                         headers={"content-type": "image/png"})
    with pytest.raises(VixlError) as caught:
        Project(16, 16).import_image(url="https://images.example/page.png")
    assert caught.value.code == "invalid_image"
    routes["/gone.png"] = httpx.Response(404)
    with pytest.raises(VixlError, match="HTTP 404"):
        Project(16, 16).import_image(url="https://images.example/gone.png")


def test_decompression_bomb_limits_apply_to_url_imports(served):
    _, routes = served
    routes["/huge.png"] = httpx.Response(200, content=png(size=(400, 400)))
    with pytest.raises(VixlError):
        Project(16, 16, limits=Limits(max_pixels=10_000)).import_image(url="https://images.example/huge.png")


def test_proxy_mode_keeps_the_host_name_and_still_checks_resolution(served, monkeypatch):
    seen, routes = served
    routes["/x.png"] = httpx.Response(200, content=png())
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy.invalid:3128")
    Project(16, 16).import_image(url="https://images.example/x.png")
    assert seen[-1].url.host == "images.example"
    with pytest.raises(VixlError) as caught:
        Project(16, 16).import_image(url="https://internal.example/x.png")
    assert caught.value.code == "unsafe_url"


def test_public_address_classification():
    assert fetch.public_address("8.8.8.8") and fetch.public_address("2606:4700::1111")
    for address in ("127.0.0.1", "10.0.0.1", "172.16.0.1", "192.168.1.1", "169.254.169.254", "::1", "fe80::1",
                    "fc00::1", "::", "::ffff:10.0.0.1", "::127.0.0.1", "2002:7f00:1::", "ff02::1", "not-an-ip"):
        assert not fetch.public_address(address), address


def test_path_and_bytes_imports_take_credit_and_license(tmp_path):
    project = Project(32, 32)
    (tmp_path / "a.png").write_bytes(png())
    result = project.import_image(tmp_path / "a.png", credit="Me", license="CC0")
    assert result["source"]["path"].endswith("a.png") and result["license"] == "CC0"
    result = project.import_image(data=png("green"), name="b", credit="  ")
    assert "credit" not in result and "sha256" in result["source"]
    project.apply({"type": "add", "path": str(tmp_path / "a.png"), "name": "c", "credit": "Ana", "license": "MIT"})
    assert project.layer("c")["provenance"]["credit"] == "Ana"
    with pytest.raises(VixlError):
        project.import_image(data=png(), credit=5)
    with pytest.raises(VixlError, match="exactly one"):
        project.import_image(tmp_path / "a.png", url="https://images.example/x.png")


def call(server, name, arguments):
    async def run():
        result = await server.call_tool(name, arguments)
        content = result[0] if isinstance(result, tuple) else result
        return json.loads("".join(getattr(item, "text", "") for item in content))

    return asyncio.run(run())


def test_mcp_rest_and_cli_url_imports(served, tmp_path):
    _, routes = served
    routes["/cat.png"] = httpx.Response(200, content=png())
    font = (Path(__import__("vixl").__file__).parent / "data" / "DejaVuSans.ttf").read_bytes()
    routes["/brand.ttf"] = httpx.Response(200, content=font)
    server = mcp_server(workspace=tmp_path)
    call(server, "vixl_document_create", {"path": "d.vixl", "width": 64, "height": 64})
    result = call(server, "vixl_import_image", {"url": "https://images.example/cat.png", "name": "cat",
                                                 "credit": "Ana", "license": "CC BY 4.0"})
    assert result["source"]["url"] == "https://images.example/cat.png" and result["credit"] == "Ana"
    inspected = call(server, "vixl_document_inspect", {"target": "cat"})
    assert inspected["source_url"] == "https://images.example/cat.png" and inspected["license"] == "CC BY 4.0"
    (tmp_path / "local.png").write_bytes(png())
    result = call(server, "vixl_import_image", {"path": "local.png", "license": "CC0"})
    assert result["source"]["path"] == "local.png" and result["license"] == "CC0"
    call(server, "vixl_import_font", {"url": "https://fonts.example/brand.ttf", "name": "brand"})
    call(server, "vixl_operations_apply", {"operations": [{"type": "text", "text": "Hi", "font": "brand"}]})

    from fastapi.testclient import TestClient

    Project(32, 32).save(tmp_path / "r.vixl")
    client = TestClient(create_app(tmp_path / "r.vixl"))
    reply = client.post("/assets", params={"url": "https://images.example/cat.png", "license": "CC0"})
    assert reply.status_code == 200, reply.text
    assert reply.json()["source"]["sha256"] and reply.json()["license"] == "CC0"

    from vixl.cli import project_command

    project = Project(32, 32)
    result, changed = project_command(project, "import", ["https://images.example/cat.png", "--credit", "Ana"])
    assert changed and result["source"]["url"].endswith("cat.png") and result["credit"] == "Ana"
    (tmp_path / "p.png").write_bytes(png())
    result, _ = project_command(project, "import", [str(tmp_path / "p.png"), "--name", "photo"])
    assert project.layer("photo")["provenance"]["source"]["sha256"] == result["source"]["sha256"]


def test_font_url_import_uses_the_same_guard(served):
    from vixl.fonts import import_font

    with pytest.raises(VixlError) as caught:
        import_font(Project(16, 16), "https://169.254.169.254/font.ttf", "x")
    assert caught.value.code == "unsafe_url" and not served[0]
