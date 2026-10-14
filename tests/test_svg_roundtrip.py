"""SVG round trip: Vixl's own SVG re-imports as the same document; other SVG imports as editable layers."""

import base64
import json
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET

import numpy as np
from PIL import Image
import pytest

from vixl import Project
from vixl.errors import VixlError
from vixl.imports import import_document, render_svg, sanitize_svg
from vixl.svg import METADATA

ROOT = Path(__file__).parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "svg"
sys.path.insert(0, str(ROOT / "tests" / "visual"))
from visual_fixtures import FIXTURES as DOCUMENTS  # noqa: E402

sys.path.pop(0)


def pixels(image):
    return np.asarray(image.convert("RGBA"), dtype=int)


def svg_image(data, limits):
    root, width, height = sanitize_svg(data, limits)
    return render_svg(root, width, height)


def with_font_and_variety():
    """Live text in an embedded font, rich text, a rotated group, effects, a style and a mask-free clip."""
    from vixl.fonts import import_font

    p = Project(240, 160, "#f8f4ec")
    import_font(p, ROOT / "src" / "vixl" / "data" / "NotoSans-Regular.ttf", "noto")
    p.apply([
        {"type": "text", "name": "headline", "text": "Round trip", "font": "noto", "size": 28, "x": 12, "y": 10,
         "color": "#1d3557"},
        {"type": "shape", "shape": "star", "name": "star", "x": 150, "y": 20, "width": 60, "height": 60,
         "fill": "#e9c46a", "stroke": "#264653", "stroke_width": 3},
        {"type": "shape", "shape": "ellipse", "name": "dot", "x": 30, "y": 70, "width": 50, "height": 50,
         "fill": "#e76f51"},
        {"type": "text", "name": "caption", "text": "editable", "size": 14, "x": 90, "y": 100, "color": "#264653"},
        {"type": "group", "name": "cluster", "targets": ["dot", "caption"]},
        {"type": "rotate", "target": "cluster", "angle": 8},
        {"type": "effect", "target": "star", "name": "gaussian-blur", "amount": 1.5},
        {"type": "layer-style", "target": "headline", "name": "drop-shadow",
         "settings": {"color": "#00000066", "dx": 2, "dy": 2, "blur": 2}},
    ])
    return p


ROUND_TRIP = {**{name: build for name, build in DOCUMENTS.items()}, "font_and_variety": with_font_and_variety}


@pytest.mark.parametrize("name", sorted(ROUND_TRIP))
def test_own_svg_reimports_as_the_same_document(name):
    original = ROUND_TRIP[name]()
    svg = original.export(format="SVG")
    restored = Project(10, 10)
    result = import_document(restored, svg, "svg")
    assert result["mode"] == "document" and result["canvas"] == "adopted"
    assert restored.state == original.state
    assert np.array_equal(pixels(restored.render()), pixels(original.render()))
    # The embedded document is inert: the SVG draws the same without it.
    plain = METADATA.sub(b"", svg)
    assert np.array_equal(pixels(svg_image(svg, original.limits)), pixels(svg_image(plain, original.limits)))


def test_layers_keep_their_ids_names_text_and_effects():
    original = with_font_and_variety()
    restored = Project(10, 10)
    import_document(restored, original.export(format="SVG"), "svg")
    assert restored.layer("headline")["type"] == "text" and restored.layer("headline")["text"] == "Round trip"
    assert restored.layer("headline")["font"] == original.state["fonts"]["noto"]
    assert restored.state["fonts"] == original.state["fonts"]
    assert restored.layer("cluster")["type"] == "group"
    assert restored.layer("caption")["parent"] == restored.layer("cluster")["id"]
    assert restored.layer("star")["effects"][0]["name"] == "gaussian-blur"
    assert restored.layer("headline")["styles"]["drop-shadow"]
    assert [x["id"] for x in restored.state["layers"]] == [x["id"] for x in original.state["layers"]]
    # The import is one revision: undo returns the empty document.
    restored.undo()
    assert not restored.state["layers"]


def test_every_layer_group_names_its_layer_id():
    original = with_font_and_variety()
    root = ET.fromstring(original.export(format="SVG"))
    ids = {node.get("data-vixl-id") for node in root.iter() if node.get("data-vixl-id")}
    visible = {x["id"] for x in original.state["layers"] if x["visible"] and not x.get("parent")}
    assert visible <= ids


def test_own_svg_into_a_document_with_layers_becomes_one_group():
    original = with_font_and_variety()
    target = Project(240, 160, "#f8f4ec")
    target.apply({"type": "shape", "shape": "rectangle", "name": "headline", "width": 4, "height": 4, "x": 230,
                  "y": 150, "fill": "#000000"})
    result = import_document(target, original.export(format="SVG"), "svg", name="artwork")
    assert result["canvas"] == "kept" and result["layers"] == ["artwork"]
    group = target.layer("artwork")
    assert group["type"] == "group" and not group.get("parent")
    names = {x["name"] for x in target.state["layers"]}
    # Names the document already uses are prefixed; the others stay as they were.
    assert {"star", "cluster", "caption", "artwork/headline"} <= names
    assert target.layer("caption")["type"] == "text"
    region = (0, 0, 220, 140)
    expected = original.render().crop(region)
    assert np.abs(pixels(target.render().crop(region)) - pixels(expected)).max() <= 2


def test_a_page_of_a_multipage_document_reimports_as_that_page():
    p = Project(200, 120, "#ffffff")
    p.apply([{"type": "text", "name": "one", "text": "Page one", "size": 20, "x": 10, "y": 10},
             {"type": "page", "action": "add", "name": "second"},
             {"type": "shape", "shape": "ellipse", "name": "two", "width": 40, "height": 40, "x": 20, "y": 20,
              "fill": "#2a9d8f"}])
    svg = p.export(format="SVG", page="second")
    q = Project(10, 10)
    import_document(q, svg, "svg")
    assert "pages" not in q.state and [x["name"] for x in q.state["layers"]] == ["two"]
    assert np.array_equal(pixels(q.render()), pixels(p.render(page="second")))


def test_svg_changed_after_export_imports_its_visible_elements():
    original = with_font_and_variety()
    svg = original.export(format="SVG").replace(b'fill="rgb(248,244,236)"', b'fill="rgb(0,0,255)"', 1)
    q = Project(240, 160)
    result = import_document(q, svg, "svg", svg_mode="auto")
    assert result["mode"] == "editable"
    assert any("changed after Vixl exported it" in w for w in result["warnings"])
    assert q.render().getpixel((2, 2))[:3] == (0, 0, 255)


def test_tampered_embedded_document_is_refused_and_the_svg_imports_editably():
    original = Project(80, 60, "#ffffff")
    from vixl.assets import add_image

    asset = add_image(original, Image.new("RGBA", (8, 8), (200, 30, 30, 255)))
    # Drawn larger than the file, so the body does not show its bytes and the payload stores them.
    original.apply({"type": "add", "asset": asset, "name": "tile", "x": 4, "y": 4, "width": 16, "height": 16})
    svg = original.export(format="SVG")
    match = METADATA.search(svg)
    payload = json.loads(ET.fromstring(match.group(0)).text)
    name = next(iter(payload["vixl"]["assets"]))
    payload["vixl"]["assets"][name] = base64.b64encode(b"not the image").decode()
    from xml.sax.saxutils import escape

    tampered = (svg[:match.start()] + f'<metadata id="vixl-document">{escape(json.dumps(payload))}</metadata>'.encode()
                + svg[match.end():])
    q = Project(80, 60)
    result = import_document(q, tampered, "svg", svg_mode="auto")
    assert result["mode"] == "editable" and any("could not be read" in w for w in result["warnings"])
    assert asset not in q.assets or q.state["layers"]


def test_assets_over_the_budget_are_left_out_and_reported(monkeypatch):
    import vixl.svg

    monkeypatch.setattr(vixl.svg, "EMBED_BUDGET", 10)
    original = with_font_and_variety()
    from vixl.assets import add_image

    asset = add_image(original, Image.new("RGBA", (8, 8), (200, 30, 30, 255)))
    original.apply({"type": "add", "asset": asset, "name": "tile", "x": 4, "y": 4, "width": 16, "height": 16})
    svg = original.export(format="SVG")
    payload = json.loads(ET.fromstring(METADATA.search(svg).group(0)).text)["vixl"]
    assert payload["omitted_assets"] and not payload["assets"]
    result = import_document(Project(240, 160), svg, "svg", svg_mode="auto")
    assert result["mode"] == "editable" and any("leaves out" in w for w in result["warnings"])


def payload_of(svg):
    return json.loads(ET.fromstring(METADATA.search(svg).group(0)).text)["vixl"]


def renamed_font(family):
    """A bundled face renamed to ``family`` (other bytes, so it is not recognised as bundled)."""
    import io

    from fontTools.ttLib import TTFont

    font = TTFont(ROOT / "src" / "vixl" / "data" / "NotoSans-Regular.ttf")
    names = font["name"]
    for name_id in (1, 4, 16):
        names.removeNames(nameID=name_id)
    names.setName(family, 1, 3, 1, 0x409)
    names.setName(family, 4, 3, 1, 0x409)
    stream = io.BytesIO()
    font.save(stream)
    return stream.getvalue()


@pytest.fixture
def font_cache(tmp_path, monkeypatch):
    """An empty font cache and no network: a download attempt fails the test."""
    import httpx

    from vixl import typefaces

    monkeypatch.setenv("VIXL_FONT_CACHE", str(tmp_path / "fonts"))
    real = httpx.Client

    def offline(*args, **kwargs):
        if "transport" in kwargs:
            return real(*args, **kwargs)
        raise AssertionError("the import tried to download a font")

    monkeypatch.setattr(typefaces.httpx, "Client", offline)
    return tmp_path / "fonts"


def google_poster(cache):
    """A text poster in a registered Google Fonts family (Inter, served from the font cache)."""
    from vixl import typefaces

    cache.mkdir(parents=True, exist_ok=True)
    data = renamed_font("Inter")
    (cache / "inter-400.ttf").write_bytes(data)
    p = Project(400, 300, "#ffffff")
    typefaces.install_font(p, "Inter", 400)
    p.apply({"type": "text", "name": "title", "text": "Poster title", "font": "inter-400", "size": 40, "x": 20,
             "y": 20, "color": "#111111"})
    return p, data


def test_a_blank_document_svg_is_small_and_carries_no_font_files(font_cache):
    """Fonts are recorded by identity, not stored: a blank document that registers fonts exports a few KB."""
    from vixl.fonts import import_font

    p, data = google_poster(font_cache)
    p.apply({"type": "remove", "target": "title"})
    import_font(p, ROOT / "src" / "vixl" / "data" / "NotoSans-Regular.ttf", "noto")
    svg = p.export(format="SVG")
    assert len(svg) < 20 * 1024
    payload = payload_of(svg)
    assert not payload["assets"]
    assert {record["source"] for record in payload["fonts"].values()} == {"google", "bundled"}


def test_text_in_a_google_font_stores_no_font_bytes_and_resolves_from_the_font_cache(font_cache):
    p, data = google_poster(font_cache)
    svg = p.export(format="SVG")
    assert base64.b64encode(data[:300]).decode()[:200] not in svg.decode()
    assert len(svg) < len(data) // 4
    record = next(iter(payload_of(svg)["fonts"].values()))
    assert record == {"family": "Inter", "weight": 400, "italic": False, "registered": ["inter-400"],
                      "source": "google"}
    restored = Project(10, 10)
    result = import_document(restored, svg, "svg")
    assert result["fonts"] == {"inter-400": "font cache"} and not result.get("warnings")
    assert restored.state == p.state and restored.assets == p.assets


def test_a_google_font_missing_from_the_cache_is_downloaded_only_when_installs_are_allowed(font_cache, monkeypatch):
    import httpx

    from vixl import typefaces

    p, data = google_poster(font_cache)
    svg = p.export(format="SVG")
    (font_cache / "inter-400.ttf").unlink()
    off = Project(10, 10)
    result = import_document(off, svg, "svg", install_fonts=False)
    assert result["fonts"] == {"inter-400": "fallback"}
    assert any("Inter 400 (inter-400)" in w and "cache only" in w for w in result["warnings"])
    requests = []

    def handler(request):
        requests.append(request.url.host)
        if request.url.host == "fonts.googleapis.com":
            return httpx.Response(200, text="@font-face { src: url(https://fonts.gstatic.com/s/x/v1/a.ttf) "
                                            "format('truetype'); }")
        return httpx.Response(200, content=data)

    real = httpx.Client
    monkeypatch.setattr(typefaces.httpx, "Client",
                        lambda *args, **kwargs: real(transport=kwargs.get("transport") or httpx.MockTransport(handler)))
    on = Project(10, 10)
    result = import_document(on, svg, "svg")
    assert result["fonts"] == {"inter-400": "downloaded"} and requests
    assert on.state == p.state


def test_a_user_font_that_cannot_be_found_falls_back_with_a_warning(tmp_path, font_cache):
    from vixl.fonts import import_font

    path = tmp_path / "house.ttf"
    path.write_bytes(renamed_font("Vixl House Face"))
    p = Project(200, 80, "#ffffff")
    import_font(p, path, "house")
    p.apply({"type": "text", "name": "word", "text": "House", "font": "house", "size": 30, "x": 10, "y": 10})
    svg = p.export(format="SVG")
    assert payload_of(svg)["fonts"][p.state["fonts"]["house"]]["source"] == "file"
    restored = Project(10, 10)
    result = import_document(restored, svg, "svg")
    assert result["mode"] == "document" and result["fonts"] == {"house": "fallback"}
    assert any("Vixl House Face 400 (house)" in w and "DejaVu Sans" in w for w in result["warnings"])
    fallback = (ROOT / "src" / "vixl" / "data" / "DejaVuSans.ttf").read_bytes()
    assert restored.assets[restored.state["fonts"]["house"]] == fallback
    assert restored.layer("word")["text"] == "House" and restored.layer("word")["font"] == restored.state["fonts"]["house"]
    # Everything but the font file comes back as it was.
    assert [x["id"] for x in restored.state["layers"]] == [x["id"] for x in p.state["layers"]]
    # A document that has the font registered under the same name supplies it.
    target = Project(200, 80, "#ffffff")
    import_font(target, path, "house")
    result = import_document(target, svg, "svg", name="art")
    assert result["fonts"] == {"house": "document"} and not result.get("warnings")


def test_images_shown_as_they_are_are_stored_once():
    from vixl.assets import add_image

    p = Project(80, 60, "#ffffff")
    shown = add_image(p, Image.new("RGBA", (20, 10), (200, 30, 30, 255)))
    hidden = add_image(p, Image.new("RGBA", (6, 6), (30, 30, 200, 255)))
    scaled = add_image(p, Image.new("RGBA", (4, 4), (30, 200, 30, 255)))
    p.apply([{"type": "add", "asset": shown, "name": "shown", "x": 3, "y": 4},
             {"type": "add", "asset": hidden, "name": "hidden", "x": 40, "y": 4},
             {"type": "hide", "target": "hidden"},
             {"type": "add", "asset": scaled, "name": "scaled", "x": 40, "y": 30, "width": 12, "height": 12}])
    svg = p.export(format="SVG")
    payload = payload_of(svg)
    # The body draws the shown image with the file's own bytes; the payload points at that element.
    ident = payload["images"][shown]
    element = next(e for e in ET.fromstring(svg).iter() if e.get("id") == ident)
    assert element.get("href") == "data:image/png;base64," + base64.b64encode(p.assets[shown]).decode()
    assert svg.count(base64.b64encode(p.assets[shown])[:40]) == 1
    # Members with no element of their own stay in the payload.
    assert set(payload["assets"]) == {hidden, scaled}
    restored = Project(10, 10)
    import_document(restored, svg, "svg")
    assert restored.state == p.state and restored.assets == p.assets
    # Without the document the body keeps the re-encoded image, as before.
    assert b"vixl-asset-" not in p.export(format="SVG", svg_document=False)


def test_svg_document_can_be_left_out():
    p = Project(40, 40)
    p.apply({"type": "shape", "shape": "ellipse", "name": "dot", "width": 20, "height": 20})
    assert b"vixl-document" not in p.export(format="SVG", svg_document=False)
    assert b"vixl-document" not in p.export(format="HTML")


# --- other SVG -------------------------------------------------------------------------------------------------------


def foreign(name, mode="editable"):
    data = (FIXTURES / name).read_bytes()
    reference = svg_image(data, Project(1, 1).limits)
    project = Project(*reference.size)
    result = import_document(project, data, "svg", svg_mode=mode)
    return project, result, reference


def test_foreign_shapes_become_editable_layers_and_groups():
    p, result, reference = foreign("shapes.svg")
    assert result["mode"] == "editable"
    layers = {x["name"]: x for x in p.state["layers"]}
    assert all(x["type"] in ("shape", "group") for x in layers.values())
    assert layers["Frames"]["type"] == "group"  # an Inkscape layer label names the group
    assert layers["faded"]["type"] == "group" and layers["faded"]["opacity"] == 0.5
    assert layers["card"]["parent"] == layers["Frames"]["id"] and layers["card"]["stroke"] == "#073642"
    assert layers["sun"]["fill"] == "#b58900cc"
    assert layers["zigzag"]["line_cap"] == "round" and layers["rule"]["dash"] == [8.0, 4.0]
    # viewBox 0 0 120 90 shown at 240×180: geometry and stroke widths scale by 2
    assert layers["card"]["stroke_width"] == 4
    # the even-odd ring keeps its hole
    ring = layers["ring"]
    assert p.render().getpixel((round(ring["x"] + ring["width"] / 2), round(ring["y"] + ring["height"] / 2)))[:3] \
        == (253, 246, 227)
    assert np.abs(pixels(p.render()) - pixels(reference)).mean() < 0.3


def test_foreign_text_styles_gradients_symbols_and_images():
    p, result, reference = foreign("text-and-styles.svg")
    layers = {x["name"]: x for x in p.state["layers"]}
    headline = layers["headline"]
    assert headline["type"] == "text" and headline["text"] == "Live text" and headline["size"] == 18
    assert headline["align"] == "center" and headline["color"] == "#f1faee"
    assert abs(headline["x"] + headline["width"] / 2 - 160) <= 1.5
    note = layers["note"]
    assert note["type"] == "text" and note["text"] == "First line\nSecond line"
    assert layers["swatch"]["type"] == "raster" and (layers["swatch"]["width"], layers["swatch"]["height"]) == (32, 24)
    assert layers["halo"]["type"] == "gradient" and layers["halo"]["direction"] == "radial"
    assert layers["badge"]["fill"] == "#e63946" and layers["badge"]["stroke"] == "#ffffff"  # class rules apply
    sky = p.state["layers"][0]  # a gradient rectangle: an editable gradient layer
    assert sky["type"] == "gradient" and sky["direction"] == "angled" and abs(sky["angle"] - 90) < 1e-6
    end = bytes.fromhex(sky["stops"][-1]["color"][1:7])
    assert max(abs(a - b) for a, b in zip(end, bytes.fromhex("457b9d"))) <= 2
    assert layers["badge"].get("styles") is None
    assert {layers["dot"]["fill"], layers["dot-2"]["fill"]} == {"#f4a261", "#2a9d8f"}  # use of a symbol
    assert headline["font"] == "DejaVuSans.ttf"  # a bundled face matches its family name
    assert not result.get("warnings")
    assert np.abs(pixels(p.render()) - pixels(reference)).mean() < 2


def test_foreign_unsupported_elements_fail_editable_and_become_images_in_auto():
    p = Project(160, 100)
    head = p.head
    with pytest.raises(VixlError, match="filter") as error:
        import_document(p, (FIXTURES / "filtered.svg").read_bytes(), "svg")
    assert error.value.code == "unsupported_svg" and p.head == head and not p.state["layers"]
    p, result, reference = foreign("filtered.svg", "auto")
    layers = {x["name"]: x for x in p.state["layers"]}
    assert [x["layer"] for x in result["rasterized"]] == ["blurred", "clipped"]
    assert layers["blurred"]["type"] == "raster" and layers["clipped"]["type"] == "raster"
    assert layers["back"]["type"] == layers["plain"]["type"] == "shape"
    assert [x["name"] for x in p.state["layers"]] == ["back", "blurred", "clipped", "plain"]
    assert np.abs(pixels(p.render()) - pixels(reference)).mean() < 0.2


def test_rotated_and_anchored_text_lands_where_the_svg_draws_it():
    data = (b'<svg xmlns="http://www.w3.org/2000/svg" width="200" height="200">'
            b'<text x="100" y="100" font-family="DejaVu Sans" font-size="24" text-anchor="end" transform="rotate(-30 100 100)">Tilted</text>'
            b'</svg>')
    reference = svg_image(data, Project(1, 1).limits)
    p = Project(200, 200)
    import_document(p, data, "svg")
    layer = p.state["layers"][0]
    assert layer["type"] == "text" and abs(layer["rotation"] % 360 - 330) < 1e-6 and layer["align"] == "right"
    got = p.render().getchannel("A").getbbox()
    want = reference.getchannel("A").getbbox()
    assert all(abs(a - b) <= 3 for a, b in zip(got, want)), (got, want)


def test_mixed_tspans_warn_and_unknown_fonts_fall_back():
    data = (b'<svg xmlns="http://www.w3.org/2000/svg" width="200" height="60"><text x="5" y="30" '
            b'font-family="Helvetica Neue, Arial">Hello <tspan font-weight="bold">bold</tspan></text></svg>')
    p = Project(200, 60)
    result = import_document(p, data, "svg")
    assert p.state["layers"][0]["text"] == "Hello bold"
    assert any("mixes styles" in w for w in result["warnings"])
    assert any("Helvetica Neue" in w for w in result["warnings"])


def test_registered_fonts_are_matched_by_family_name():
    from vixl.fonts import import_font

    p = Project(200, 60)
    import_font(p, ROOT / "src" / "vixl" / "data" / "NotoSans-Regular.ttf", "noto-sans")
    data = b'<svg xmlns="http://www.w3.org/2000/svg" width="200" height="60"><text x="5" y="30" ' \
           b'font-family="\'Noto Sans\', sans-serif">Hi</text></svg>'
    result = import_document(p, data, "svg")
    assert p.layer("import-text")["font"] == p.state["fonts"]["noto-sans"] and not result.get("warnings")


def test_old_vixl_svg_without_metadata_names_layers_from_data_layer():
    original = DOCUMENTS["groups"]()
    plain = METADATA.sub(b"", original.export(format="SVG"))
    p = Project(original.state["canvas"]["width"], original.state["canvas"]["height"])
    import_document(p, plain, "svg")
    names = {x["name"] for x in p.state["layers"]}
    original_names = {x["name"] for x in original.state["layers"] if x["type"] != "text"}
    assert original_names <= names
    assert re.search(rb'data-vixl-id="lyr_[0-9a-f]{16}"', plain)
