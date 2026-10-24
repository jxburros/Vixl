"""Font installs say where the font came from: download URL, cache file, and the embedded file."""

import asyncio
import hashlib
import json
from pathlib import Path

import httpx
import pytest

from vixl import Project, VixlError, typefaces
from vixl.cli import dispatch
from vixl.interfaces import mcp_server

REAL_CLIENT = httpx.Client
FONT = (Path(typefaces.__file__).parent / "data" / "DejaVuSans.ttf").read_bytes()
STYLESHEET = "@font-face { src: url(https://fonts.gstatic.com/s/x/v1/abc.ttf) format('truetype'); }"


def fake_google(requests):
    def handler(request):
        requests.append(str(request.url))
        if request.url.host == "fonts.googleapis.com":
            return httpx.Response(200, text=STYLESHEET)
        return httpx.Response(200, content=FONT)

    return REAL_CLIENT(transport=httpx.MockTransport(handler))


def test_install_reports_download_then_cache(tmp_path, monkeypatch):
    monkeypatch.setenv("VIXL_FONT_CACHE", str(tmp_path / "cache"))
    requests = []
    first = typefaces.install_font(Project(10, 10), "Inter", 600, client=fake_google(requests))
    assert (first["family"], first["weight"], first["italic"], first["name"]) == ("Inter", 600, False, "inter-600")
    source = first["source"]
    assert source["origin"] == "download" and source["url"] == "https://fonts.gstatic.com/s/x/v1/abc.ttf"
    assert source["stylesheet"].startswith("https://fonts.googleapis.com/css2?family=Inter:wght@600")
    assert source["cache_file"] == str(tmp_path / "cache" / "inter-600.ttf") and Path(source["cache_file"]).is_file()
    assert source["cache_dir"] == str(tmp_path / "cache") and source["cache_dir_from"] == "VIXL_FONT_CACHE"
    assert source["bundled_fallback"] is False
    digest = hashlib.sha256(FONT).hexdigest()
    assert first["file"] == {"asset": f"fonts/{digest}.ttf", "bytes": len(FONT), "sha256": digest}
    assert len(requests) == 2
    # The second install is served from the cache with no network access, and says so.
    again = []
    second = typefaces.install_font(Project(10, 10), "Inter", 600, client=fake_google(again))
    assert again == [] and second["source"]["origin"] == "cache"
    assert second["source"]["cache_file"] == source["cache_file"] and "url" not in second["source"]
    assert second["file"] == first["file"]


def test_cache_dir_default_and_unwritable_cache(tmp_path, monkeypatch):
    monkeypatch.delenv("VIXL_FONT_CACHE", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(Path, "mkdir", lambda *args, **kwargs: (_ for _ in ()).throw(OSError("read-only")))
    result = typefaces.install_font(Project(10, 10), "Inter", 400, italic=True, client=fake_google([]))
    assert result["italic"] and result["name"] == "inter-400-italic"
    assert result["source"]["cache_dir_from"] == "default" and result["source"]["cache_dir"].endswith("fonts")
    assert result["source"]["origin"] == "download" and result["source"]["cache_file"] is None  # nothing was cached


def test_pair_reports_origin_for_both_fonts(tmp_path, monkeypatch):
    monkeypatch.setenv("VIXL_FONT_CACHE", str(tmp_path))
    pairing = next(p for p in typefaces.pairings() if p["heading"]["family"] != p["body"]["family"])
    result = typefaces.pair_fonts(Project(10, 10), pairing["name"], client=fake_google([]))
    assert result["origin"] == "download"
    assert result["heading"]["source"]["origin"] == result["body"]["source"]["origin"] == "download"
    assert result["heading"]["role"] == "heading" and result["body"]["file"]["bytes"] == len(FONT)
    # One style already cached and one not is reported as mixed.
    (tmp_path / f"{typefaces.slug(pairing['body']['family'])}-{pairing['body']['weight']}.ttf").unlink()
    result = typefaces.pair_fonts(Project(10, 10), pairing["name"], client=fake_google([]))
    assert result["origin"] == "mixed" and result["heading"]["source"]["origin"] == "cache"
    assert result["body"]["source"]["origin"] == "download"
    assert typefaces.origin_of() == "mixed"  # nothing installed is not one origin


def test_failed_download_never_substitutes_the_bundled_font(tmp_path, monkeypatch):
    monkeypatch.setenv("VIXL_FONT_CACHE", str(tmp_path))
    project = Project(10, 10)

    def refuse(request):
        return httpx.Response(503)

    with pytest.raises(VixlError) as caught:
        typefaces.install_font(project, "Inter", 400, client=httpx.Client(transport=httpx.MockTransport(refuse)))
    assert caught.value.code == "font_download_failed"
    assert project.state.get("fonts", {}) == {} and not project.assets


def test_roll_apply_reports_the_installed_fonts(tmp_path, monkeypatch):
    monkeypatch.setenv("VIXL_FONT_CACHE", str(tmp_path))
    monkeypatch.setattr(typefaces, "fetch_font", lambda family, weight=400, italic=False, *, client=None, source=None:
                        (source.update(origin="cache", cache_file=f"/cache/{family}-{weight}.ttf") or (FONT, family)))
    project = Project(800, 800)
    result = typefaces.roll_document(project, seed=3, apply=True)
    assert result["fonts"]["origin"] == "cache"
    assert result["fonts"]["heading"]["source"]["cache_file"].startswith("/cache/")


def test_cli_and_mcp_return_the_source(tmp_path, monkeypatch):
    monkeypatch.setenv("VIXL_FONT_CACHE", str(tmp_path / "cache"))
    monkeypatch.setattr(typefaces.httpx, "Client", lambda *args, **kwargs: fake_google([]))
    project = Project(100, 100)
    project.save(tmp_path / "doc.vixl")
    result, _ = dispatch(["-p", str(tmp_path / "doc.vixl"), "font", "install", "Inter", "--weight", "700"])
    assert result["source"]["origin"] == "download" and result["file"]["bytes"] == len(FONT)

    server = mcp_server(workspace=tmp_path)

    async def call(name, arguments):
        content = await server.call_tool(name, arguments)
        content = content[0] if isinstance(content, tuple) else content
        return json.loads("".join(getattr(item, "text", "") for item in content))

    asyncio.run(call("vixl_document", {"action": "open", "path": "doc.vixl"}))
    def step(**fields):
        return asyncio.run(call("vixl_apply", {"operations": [fields]}))["steps"][0]["result"]

    installed = step(type="font-install", family="Inter", weight=700, name="inter-bold")
    assert installed["source"]["origin"] == "cache" and installed["source"]["cache_file"].endswith("inter-700.ttf")
    paired = step(type="font-pair", pairing=typefaces.pairings()[0]["name"])
    assert paired["origin"] in ("cache", "download", "mixed") and paired["heading"]["source"]["cache_dir_from"] == "VIXL_FONT_CACHE"
    steps = asyncio.run(call("vixl_reference", {"topic": "operations", "name": ["font-install", "font-pair"]}))
    for name in ("font-install", "font-pair"):
        assert "cache" in steps[name]["description"] or "Download" in steps[name]["description"]
    # The commands bring the body text face's italic too.
    assert paired["body"]["body_italic"]["name"] == paired["body"]["name"] + "-italic"


def fake_google_faces():
    """``fake_google`` serving a face of its own for every family and style requested."""
    from urllib.parse import parse_qs

    from font_helper import make_font

    def handler(request):
        if request.url.host == "fonts.googleapis.com":
            family, axis = parse_qs(request.url.query.decode())["family"][0].split(":")
            name = f"{typefaces.slug(family)}{'-italic' if 'ital' in axis else ''}"
            return httpx.Response(200, text=STYLESHEET.replace("abc.ttf", f"{name}.ttf"))
        name = request.url.path.rsplit("/", 1)[-1][:-4]
        return httpx.Response(200, content=make_font("Plain slanted", family=name.removesuffix("-italic"),
                                                     italic=name.endswith("-italic")))

    return REAL_CLIENT(transport=httpx.MockTransport(handler))


def test_font_pair_brings_the_body_italic_that_italic_text_then_uses(tmp_path, monkeypatch):
    from vixl.render import resolved_layers
    from vixl.richtext import styled_spans

    monkeypatch.setenv("VIXL_FONT_CACHE", str(tmp_path))
    project = Project(400, 100)
    result = typefaces.pair_fonts(project, "source-serif-sans", client=fake_google_faces(), body_italic=True)
    italic = result["body"]["body_italic"]
    assert italic == {"name": "source-sans-3-400-italic", "origin": "download"}
    assert (tmp_path / "source-sans-3-400-italic.ttf").is_file() and italic["name"] in project.state["fonts"]
    project.apply({"type": "rich-text", "name": "t", "markdown": "Plain *slanted*", "font": "body"})
    layer = next(item for item in resolved_layers(project) if item["name"] == "t")
    span = styled_spans(project, layer)[1]
    assert span["font"] == project.state["fonts"][italic["name"]] and not span["fake_italic"]
    # Rolls and other internal pairings install the two styles only, and so does a face without an italic.
    assert "body_italic" not in typefaces.pair_fonts(Project(10, 10), "source-serif-sans", client=fake_google([]))["body"]
    plain = typefaces.pair_fonts(Project(10, 10), "space-mono-space-grotesk", client=fake_google([]), body_italic=True)
    assert "body_italic" not in plain["body"]


def test_a_body_italic_that_cannot_be_fetched_is_skipped(tmp_path, monkeypatch):
    monkeypatch.setenv("VIXL_FONT_CACHE", str(tmp_path))
    monkeypatch.setenv("VIXL_OFFLINE", "1")
    for name in ("source-serif-4-600", "source-sans-3-400"):
        (tmp_path / f"{name}.ttf").write_bytes(FONT)
    project = Project(10, 10)
    result = typefaces.pair_fonts(project, "source-serif-sans", body_italic=True)
    assert "network" in result["body"]["body_italic"]["skipped"] and result["origin"] == "cache"
    assert "source-sans-3-400-italic" not in project.state["fonts"]
