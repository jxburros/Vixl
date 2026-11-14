"""Network reads stop at their caps and deadlines (#827, #830): one bounded reader for URL imports, fonts, AI
providers and the Figma API, one deadline for a fetch and its redirects, and a deadline on webhook answers."""

import functools
import gzip
import json
import tracemalloc
import zlib

import httpx
import pytest

from vixl import VixlError, fetch, typefaces
from vixl.plugins.ai import studio_provider as studio
from vixl.plugins.ai.ai import HTTPProvider
from vixl.plugins.figma_import import figma_import

REAL_CLIENT = httpx.Client
PUBLIC = "93.184.216.34"
MIB = 1024 * 1024
BOMB = 48 * MIB  # Decoded size of the compressed bodies below; about 47 KiB on the wire.


@pytest.fixture(autouse=True)
def quiet_network(monkeypatch):
    for name in ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy", "ALL_PROXY", "all_proxy",
                 fetch.ALLOW_PRIVATE_ENV, fetch.OFFLINE_ENV, fetch.FETCH_HOSTS_ENV, fetch.PROXY_RESOLVES_ENV):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(fetch, "resolve", lambda host, port: [PUBLIC])


@pytest.fixture
def served(monkeypatch):
    """Route every httpx client to ``routes`` (path -> response or callable); records each client's timeout."""
    routes, timeouts = {}, []

    def handler(request):
        reply = routes.get(request.url.path, httpx.Response(404))
        return reply(request) if callable(reply) else reply

    def client(**kw):
        timeouts.append(kw.get("timeout"))
        kw["trust_env"] = False
        kw.setdefault("transport", httpx.MockTransport(handler))
        return REAL_CLIENT(**kw)

    monkeypatch.setattr(httpx, "Client", client)
    return routes, timeouts


@pytest.fixture
def clock(monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(fetch, "_now", lambda: now[0])
    return now


def wire(body, encoding):
    """A route answering ``body`` as it is on the wire: streamed, so nothing decodes it before the reader does."""
    return lambda request: httpx.Response(200, content=iter([body]), headers={"content-encoding": encoding})


@functools.cache
def bomb_body(encoding):
    raw = b"\0" * BOMB
    return gzip.compress(raw) if encoding == "gzip" else zlib.compress(raw)


def bomb(encoding="gzip"):
    body = bomb_body(encoding)
    assert len(body) < 64 * 1024
    return httpx.Response(200, content=iter([body]), headers={"content-encoding": encoding})


def peak_of(call):
    """Run ``call``; return (its exception or result, peak bytes allocated while it ran)."""
    bomb_body("gzip"), bomb_body("deflate")  # Built before the measurement starts.
    tracemalloc.start()
    try:
        try:
            outcome = call()
        except VixlError as exc:
            outcome = exc
        return outcome, tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()


def refused(outcome, peak, limit):
    assert isinstance(outcome, VixlError) and outcome.code == "resource_limit", outcome
    # The cap, one decoded chunk and working room; the body would decode to 48 MiB.
    assert peak <= limit + fetch.CHUNK + 2 * MIB, f"{peak} bytes allocated for a {limit}-byte cap"


# ------------------------------------------------------------------------------------------------- the reader

@pytest.mark.parametrize("encoding", ["gzip", "deflate"])
def test_a_compressed_bomb_is_refused_before_it_is_decoded(served, encoding):
    served[0]["/bomb.png"] = lambda request: bomb(encoding)
    limit = MIB
    outcome, peak = peak_of(lambda: fetch.fetch_bounded("https://images.example/bomb.png", limit))
    refused(outcome, peak, limit)


def test_compressed_bodies_under_the_cap_decode_whole(served):
    payload = bytes(range(256)) * 4000
    raw_deflate = zlib.compressobj(wbits=-zlib.MAX_WBITS)
    bodies = {"gzip": gzip.compress(payload), "x-gzip": gzip.compress(payload), "deflate": zlib.compress(payload),
              "identity": payload}
    for index, (encoding, body) in enumerate(bodies.items()):
        served[0][f"/{index}"] = wire(body, encoding)
        assert fetch.fetch_bounded(f"https://images.example/{index}", len(payload))[0] == payload, encoding
    # Some servers send "deflate" without the zlib header.
    served[0]["/raw"] = wire(raw_deflate.compress(payload) + raw_deflate.flush(), "deflate")
    assert fetch.fetch_bounded("https://images.example/raw", len(payload))[0] == payload
    # Exactly at the cap passes; one byte less of cap refuses.
    with pytest.raises(VixlError) as caught:
        fetch.fetch_bounded("https://images.example/0", len(payload) - 1)
    assert caught.value.code == "resource_limit"


def test_requests_ask_only_for_encodings_the_reader_bounds(served):
    seen = []
    served[0]["/x"] = lambda request: seen.append(request.headers["accept-encoding"]) or httpx.Response(200, content=b"ok")
    served[0]["/br"] = wire(b"\x0b\x02\x80ok\x03", "br")
    served[0]["/bad"] = wire(b"not gzip at all", "gzip")
    assert fetch.fetch_bounded("https://images.example/x", 100)[0] == b"ok"
    assert seen == ["gzip, deflate"]
    for path in ("/br", "/bad"):
        with pytest.raises(VixlError) as caught:
            fetch.fetch_bounded("https://images.example" + path, 100)
        assert caught.value.code == "fetch_failed" and "DecodingError" in str(caught.value), path


def test_an_oversized_content_length_is_refused_before_the_body_is_read(served):
    taken = []

    def body():
        for index in range(50):
            taken.append(index)
            yield b"\0" * 1000

    served[0]["/big"] = httpx.Response(200, content=body(), headers={"content-length": "50000"})
    with pytest.raises(VixlError) as caught:
        fetch.fetch_bounded("https://images.example/big", 10_000)
    assert caught.value.code == "resource_limit" and not taken


def test_a_stream_stops_at_the_piece_that_would_pass_the_cap(served):
    taken = []

    def body():
        for index in range(50):
            taken.append(index)
            yield b"\0" * 1000

    served[0]["/stream"] = httpx.Response(200, content=body())
    with pytest.raises(VixlError) as caught:
        fetch.fetch_bounded("https://images.example/stream", 2500)
    assert caught.value.code == "resource_limit" and len(taken) == 3


# --------------------------------------------------------------------------------------- the callers of the reader

def test_figma_api_answers_are_streamed_against_the_cap(monkeypatch):
    monkeypatch.setattr(figma_import, "MAX_RESPONSE", 4000)
    taken = []

    def body():
        for index in range(200):
            taken.append(index)
            yield b" " * 1000

    client = figma_import.FigmaClient("tok", transport=httpx.MockTransport(
        lambda request: httpx.Response(200, content=body())))
    with pytest.raises(VixlError) as caught:
        client.file("KEY")
    assert caught.value.code == "resource_limit" and "single frame" in str(caught.value)
    assert len(taken) == 5  # The eager reader took all 200 before it looked at the size.


def test_figma_api_refuses_a_compressed_bomb_and_reads_error_detail(monkeypatch):
    monkeypatch.setattr(figma_import, "MAX_RESPONSE", MIB)
    client = figma_import.FigmaClient("tok", transport=httpx.MockTransport(lambda request: bomb()))
    refused(*peak_of(lambda: client.file("KEY")), MIB)
    packed = httpx.MockTransport(wire(gzip.compress(json.dumps({"name": "Poster"}).encode()), "gzip"))
    assert figma_import.FigmaClient("tok", transport=packed).file("KEY") == {"name": "Poster"}
    failing = figma_import.FigmaClient("tok", transport=httpx.MockTransport(
        lambda request: httpx.Response(400, json={"err": "Bad ids"})))
    with pytest.raises(VixlError) as caught:
        failing.file("KEY")
    assert caught.value.code == "figma_bad_request" and "Bad ids" in str(caught.value)
    huge_error = figma_import.FigmaClient("tok", transport=httpx.MockTransport(
        lambda request: httpx.Response(500, content=b"x" * (figma_import.MAX_ERROR_BODY + 1))))
    with pytest.raises(VixlError) as caught:
        huge_error.file("KEY")
    assert caught.value.code == "figma_error" and caught.value.details["status"] == 500


def test_provider_answers_are_bounded_before_decoding(served, monkeypatch):
    from vixl.plugins.ai import ai

    monkeypatch.setattr(ai, "MAX_RESPONSE", MIB)
    served[0]["/describe"] = lambda request: bomb()
    backend = HTTPProvider("fixture", {"url": "http://localhost:8188"})
    refused(*peak_of(lambda: backend.invoke("describe", {})), MIB)
    served[0]["/describe"] = wire(gzip.compress(b'{"description": "ok"}'), "gzip")
    assert backend.invoke("describe", {}) == {"description": "ok"}


def test_studio_gateway_answers_are_bounded_before_decoding(monkeypatch):
    from vixl.plugins.ai import ai

    monkeypatch.setattr(ai, "MAX_RESPONSE", MIB)
    monkeypatch.setattr(studio.StudioProvider, "transport", httpx.MockTransport(lambda request: bomb()))
    backend = studio.StudioProvider("http://127.0.0.1:9/gateway", "t" * 32)
    refused(*peak_of(lambda: backend.invoke("describe", {"source_image": "x"})), MIB)


def test_font_downloads_are_bounded_before_decoding(monkeypatch):
    monkeypatch.setattr(typefaces, "LIMIT", MIB)
    client = REAL_CLIENT(transport=httpx.MockTransport(lambda request: bomb()))
    refused(*peak_of(lambda: typefaces._get(client, "https://fonts.example/a.ttf")), MIB)


# ---------------------------------------------------------------------------------------------------- deadlines

def test_redirect_hops_share_one_deadline(served, clock):
    routes, timeouts = served

    def hop(target):
        def reply(request):
            clock[0] += 25  # Each hop answers just inside its own 30 s timeout.
            return httpx.Response(302, headers={"location": target})
        return reply

    for index in range(5):
        routes[f"/{index}"] = hop(f"/{index + 1}")
    routes["/5"] = httpx.Response(200, content=b"late")
    with pytest.raises(VixlError) as caught:
        fetch.fetch_bounded("https://images.example/0", 100)
    assert caught.value.code == "fetch_failed" and "longer than 120 s" in str(caught.value)
    assert timeouts == [30, 30, 30, 30, 20]  # What was left of the 120 s; the sixth request is never sent.
    # Inside the deadline the same chain is followed.
    timeouts.clear()
    routes["/3"] = httpx.Response(200, content=b"on time")
    assert fetch.fetch_bounded("https://images.example/0", 100)[0] == b"on time"
    assert timeouts == [30, 30, 30, 30]


def test_a_trickled_body_is_cut_off_at_the_deadline(served, clock):
    taken = []

    def body():
        while True:
            taken.append(1)
            clock[0] += 1
            yield b"\0"

    served[0]["/slow"] = httpx.Response(200, content=body())
    with pytest.raises(VixlError) as caught:
        fetch.fetch_bounded("https://images.example/slow", 1_000_000)
    assert caught.value.code == "fetch_failed" and "longer than 120 s" in str(caught.value)
    assert len(taken) <= fetch.TOTAL_TIMEOUT + 1


def test_a_trickling_webhook_receiver_is_cut_off_at_the_deadline(served, clock):
    taken = []

    def body():
        while True:
            taken.append(1)
            clock[0] += 1
            yield b"."

    served[0]["/hook"] = httpx.Response(200, content=body())
    assert fetch.post_bounded("https://hooks.example/hook", b"{}", {}) == {"status": 200}
    assert len(taken) <= fetch.TIMEOUT + 1  # Without the deadline it read all 64 KiB, one byte a second.


def test_a_webhook_answer_is_dropped_undecoded_and_capped(served):
    taken = []

    def body():
        for _ in range(100):
            taken.append(1)
            yield b"\0" * 10_000

    served[0]["/hook"] = httpx.Response(202, content=body())
    served[0]["/bomb"] = lambda request: bomb()
    assert fetch.post_bounded("https://hooks.example/hook", b"{}", {}) == {"status": 202}
    assert len(taken) == 7
    outcome, peak = peak_of(lambda: fetch.post_bounded("https://hooks.example/bomb", b"{}", {}))
    assert outcome == {"status": 200} and peak < 2 * MIB
