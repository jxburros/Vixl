"""The ``studio`` AI provider (#544): every capability through a fake Studio gateway (an httpx MockTransport), the
error mapping, the echoed call context, offline mode, and no request to any other host."""

import base64
import io
import json
from types import SimpleNamespace

import httpx
import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402

from vixl.errors import VixlError  # noqa: E402
from vixl.plugins.ai import studio_provider as studio  # noqa: E402

TOKEN = "s" * 32
AUTH = {"Authorization": f"Bearer {TOKEN}"}
GATEWAY = "https://studio.example/gateway"
GATEWAY_TOKEN = "gateway-secret-token"


def png(width, height, mode="RGBA", color=(200, 40, 40, 255)):
    from PIL import Image

    stream = io.BytesIO()
    Image.new(mode, (width, height), color if mode != "L" else 255).save(stream, format="PNG")
    return base64.b64encode(stream.getvalue()).decode()


class Gateway:
    """A fake gateway: records every request and answers each capability in the shape the contract proposes."""

    def __init__(self):
        self.requests = []
        self.fail = None  # (status, body) to answer instead

    def __call__(self, request):
        self.requests.append(request)
        if self.fail:
            return httpx.Response(self.fail[0], json=self.fail[1])
        body = json.loads(request.content)
        capability = request.url.path.rsplit("/", 1)[1]
        size = (body["constraints"].get("width", 8), body["constraints"].get("height", 8))
        answer = {
            "plan": {"operations": [{"type": "text", "text": "Hi", "x": 10, "y": 10, "size": 20}]},
            "describe": {"description": "A red square"},
            "detect": {"objects": [{"label": "kite", "x": 1, "y": 2, "width": 10, "height": 12}]},
            "ocr": {"text": "HELLO", "lines": ["HELLO"]},
            "generate": {"image": png(*size), "model": "gw-image-1", "seed": 7},
            "upscale": {"image": png(*size), "model": "gw-upscale-1"},
            "segment": {"mask": png(*size, mode="L")},
            "background-remove": {"mask": png(*size, mode="L")},
        }[capability]
        return httpx.Response(200, json=answer)


@pytest.fixture
def gateway(monkeypatch, tmp_path):
    fake = Gateway()
    monkeypatch.setattr(studio.StudioProvider, "transport", httpx.MockTransport(fake))

    def no_network(self, request):  # Any real connection is a failure: only the fake gateway may answer.
        raise AssertionError(f"A request reached {request.url.host}")

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", no_network)
    monkeypatch.setenv("STUDIO_TOKEN", GATEWAY_TOKEN)
    monkeypatch.setenv("VIXL_PROVIDERS", str(tmp_path / "providers.json"))
    monkeypatch.setenv("VIXL_AUTO_FONTS", "off")
    monkeypatch.setenv("VIXL_OFFLINE", "")  # Restored after the test; the offline host sets it.
    yield fake
    studio.deactivate()


def options(**extra):
    return SimpleNamespace(provider="studio", provider_url=GATEWAY, provider_token_env="STUDIO_TOKEN", **extra)


@pytest.fixture
def client(gateway, tmp_path):
    from vixl.host import create_host_app

    app = create_host_app(tmp_path / "root", TOKEN, offline=True, options=options())
    with TestClient(app, headers=AUTH) as test:
        yield test


def new_document(client):
    made = client.post("/w/team/documents", json={"width": 64, "height": 48, "background": "#ffffff",
                                                   "workspace_fonts": False})
    assert made.status_code == 201, made.text
    return made.json()["id"]


def ai(client, doc, command, *args, headers=None, status=200):
    response = client.post(f"/w/team/documents/{doc}/ai", json={"command": command, "args": list(args)},
                           headers=headers or {})
    assert response.status_code == status, response.text
    return response.json()


def test_every_capability_goes_to_the_gateway_with_capability_and_constraints_only(client, gateway, tmp_path):
    doc = new_document(client)
    made = ai(client, doc, "generate", "--prompt", "a red kite", "--model", "someone-elses-model")
    assert made["revision"] == 2 and made["provenance"]["provider"] == "studio"
    assert made["provenance"]["model"] == "gw-image-1"  # Provenance records what the gateway used.
    layer = made["layer"]
    plan = ai(client, doc, "ask", "add a greeting")
    assert plan["proposal"][0]["type"] == "text" and plan["revision"] == 2  # A proposal changes nothing.
    assert ai(client, doc, "ai", "describe")["description"] == "A red square"
    assert ai(client, doc, "detect", "kite")["objects"][0]["box"] == [1, 2, 10, 12]
    assert ai(client, doc, "ocr")["text"] == "HELLO"
    assert ai(client, doc, "select", "object", "kite")["revision"] == 3
    assert ai(client, doc, "ai", "background-remove", layer)["revision"] == 4
    upscaled = ai(client, doc, "ai", "upscale", layer, "--scale", "2")
    assert upscaled["revision"] == 5 and upscaled["provenance"]["model"] == "gw-upscale-1"

    paths = [request.url.path for request in gateway.requests]
    assert paths == [f"/gateway/v1/{name}" for name in ("generate", "plan", "describe", "detect", "ocr", "segment",
                                                         "background-remove", "upscale")]
    for request in gateway.requests:
        body = json.loads(request.content)
        assert set(body) == {"capability", "constraints", "inputs"}
        assert body["capability"] == request.url.path.rsplit("/", 1)[1]
        assert "model" not in body["inputs"] and "model" not in body["constraints"]
        assert request.headers["authorization"] == f"Bearer {GATEWAY_TOKEN}"
    generate = json.loads(gateway.requests[0].content)
    assert generate["constraints"]["width"] == 64 and generate["inputs"]["prompt"] == "a red kite"
    # No request reached any other host, and the token never reached a file.
    assert {request.url.host for request in gateway.requests} == {"studio.example"}
    assert not (tmp_path / "providers.json").exists()
    assert GATEWAY_TOKEN not in (tmp_path / "root" / "team" / f"{doc}.vixl").read_bytes().decode("latin-1")


def test_the_host_call_context_is_echoed_on_every_gateway_call(client, gateway):
    doc = new_document(client)
    ai(client, doc, "ai", "describe", headers={"X-Call-Context": "studio-run-42"})
    ai(client, doc, "ocr", headers={"X-Call-Context": "studio-run-43"})
    ai(client, doc, "detect")
    assert [request.headers.get("x-call-context") for request in gateway.requests] == [
        "studio-run-42", "studio-run-43", None]
    refused = client.post(f"/w/team/documents/{doc}/ai", json={"command": "ocr"},
                          headers={"X-Call-Context": "x" * 5000})
    assert refused.status_code == 400 and refused.json()["code"] == "invalid_request"
    assert len(gateway.requests) == 3


@pytest.mark.parametrize("status, body, code, http", [
    (403, {"error": {"code": "refused", "message": "Policy says no"}}, "provider_refused", 403),
    (451, {}, "provider_refused", 403),
    (429, {"error": {"code": "limit_exceeded", "message": "Quota", "retry_after": 30}}, "limit_exceeded", 429),
    (402, {"error": {"message": "Out of credits"}}, "limit_exceeded", 429),
    (500, {"error": {"code": "backend_down", "message": "Model offline"}}, "provider_error", 502),
    (502, "not json", "provider_error", 502),
])
def test_gateway_errors_map_to_vixl_codes(client, gateway, status, body, code, http):
    doc = new_document(client)
    gateway.fail = (status, body)
    answer = ai(client, doc, "generate", "--prompt", "kite", status=http)
    assert answer["code"] == code and answer["details"]["provider"] == "studio"
    if code == "limit_exceeded" and status == 429:
        assert answer["details"]["retry_after"] == 30
    gateway.fail = None
    assert client.get(f"/w/team/documents/{doc}").json()["revision"] == 1  # A failed call changes nothing.


def test_a_gateway_message_is_cut_and_flattened():
    error = studio.gateway_error(500, {"error": {"message": "line one\nline two " + "x" * 1000}})
    assert "\n" not in str(error) and len(str(error)) < 400


def test_while_active_every_capability_routes_to_studio_and_other_providers_are_refused(client, gateway):
    from vixl.plugins.ai.ai import provider
    from vixl.plugins.ai.models import CAPABILITIES, route

    for capability in CAPABILITIES:
        assert route(capability) is studio.active()
    assert provider() is studio.active() and provider("studio") is studio.active()
    for other in ("openai", "flux", "my-gateway"):
        with pytest.raises(VixlError) as caught:
            route("generate", other)
        assert caught.value.code == "forbidden"
        with pytest.raises(VixlError):
            provider(other)
    doc = new_document(client)
    refused = ai(client, doc, "generate", "--prompt", "kite", "--provider", "openai", status=403)
    assert refused["code"] == "forbidden" and not gateway.requests


def test_offline_lets_exactly_the_gateway_url_through(client, gateway):
    from vixl.fetch import network_allowed, offline

    assert offline()
    network_allowed("studio", GATEWAY + "/v1/generate")
    for url in ("https://studio.example/other", "https://studio.example.evil/gateway/v1/generate",
                "https://elsewhere.example/gateway/v1/generate", None):
        with pytest.raises(VixlError) as caught:
            network_allowed("other", url)
        assert caught.value.code == "network_disabled"
    info = client.get("/host/info").json()
    assert info["provider"] == {"type": "studio", "url": GATEWAY} and info["capabilities"]["ai"] is True
    studio.deactivate()
    with pytest.raises(VixlError):
        network_allowed("studio", GATEWAY + "/v1/generate")


def test_a_host_without_the_provider_has_none(gateway, tmp_path):
    from vixl.host import create_host_app

    create_host_app(tmp_path / "a", TOKEN, options=options())
    assert studio.active() is not None
    plain = TestClient(create_host_app(tmp_path / "b", TOKEN), headers=AUTH)
    assert studio.active() is None
    doc = new_document(plain)
    assert ai(plain, doc, "ocr", status=501)["code"] == "provider_not_configured"


def test_configuration_is_checked(gateway, tmp_path, monkeypatch):
    from vixl.host import create_host_app

    for bad in ("http://studio.example/gw", "ftp://studio.example", "https://user:pw@studio.example",
                "https://studio.example/gw?key=1"):
        with pytest.raises(VixlError) as caught:
            create_host_app(tmp_path / "r", TOKEN, options=SimpleNamespace(
                provider="studio", provider_url=bad, provider_token_env="STUDIO_TOKEN"))
        assert caught.value.code == "provider_not_configured"
    studio.activate("http://127.0.0.1:9911", "STUDIO_TOKEN")  # Plain http only to a loopback gateway.
    monkeypatch.delenv("STUDIO_TOKEN")
    with pytest.raises(VixlError) as caught:
        studio.activate(GATEWAY, "STUDIO_TOKEN")
    assert caught.value.code == "provider_not_configured"
    with pytest.raises(VixlError):
        create_host_app(tmp_path / "r", TOKEN, options=SimpleNamespace(provider=None, provider_url=GATEWAY,
                                                                         provider_token_env=None))
    assert GATEWAY_TOKEN not in repr(studio.StudioProvider(GATEWAY, GATEWAY_TOKEN))


def test_vixl_host_takes_the_provider_flags():
    from vixl.host import host_parser

    a = host_parser().parse_args(["--root", "r", "--provider", "studio", "--provider-url", GATEWAY,
                                  "--provider-token-env", "STUDIO_TOKEN"])
    assert (a.provider, a.provider_url, a.provider_token_env) == ("studio", GATEWAY, "STUDIO_TOKEN")
    assert "--provider-url" in host_parser().format_help()
