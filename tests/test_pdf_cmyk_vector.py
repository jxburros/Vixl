"""CMYK PDF export keeps text and vector shapes as vectors; only images and effects are rasterised."""

import io
import re
import sys
from pathlib import Path

import pytest

from vixl import Project, colors
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))
from icc_helper import cmyk_profile  # noqa: E402

pypdf = pytest.importorskip("pypdf")


def _poster():
    p = Project.sized("poster-11x17", "#14263b", bleed=True)
    p.apply([
        {"type": "text", "name": "head", "text": "Port Ellery Quay", "size": 160, "x": 120, "y": 200, "color": "#f2a541"},
        {"type": "text", "name": "small", "text": "Live brass band", "size": 40, "x": 120, "y": 500, "color": "black"},
        {"type": "shape", "name": "bar", "shape": "rectangle", "x": 100, "y": 800, "width": 1200, "height": 200,
         "fill": "#e2725b", "stroke": "#ffffff", "stroke_width": 8},
        {"type": "gradient", "name": "sky", "x": 100, "y": 1100, "width": 1200, "height": 300, "direction": "horizontal",
         "stops": [{"offset": 0, "color": "#ffd23f"}, {"offset": 1, "color": "#3bceac"}]},
    ])
    return p


def _page(data):
    return pypdf.PdfReader(io.BytesIO(data)).pages[0]


def _content(data):
    return _page(data).get_contents().get_data().decode("latin-1")


def _fills(content, op="k"):
    """The (c, m, y, k) operands of every fill (k) or stroke (K) colour operator."""
    pattern = r"((?:[\d.]+ ){4})" + op + r"\b"
    return [tuple(float(v) for v in match.split()) for match in re.findall(pattern, content)]


def test_cmyk_pdf_is_vector_with_selectable_text_by_default():
    report = {}
    data = _poster().export(format="PDF", color_space="cmyk", report=report)
    page = _page(data)
    text = page.extract_text()
    assert "Port Ellery Quay" in text and "Live brass band" in text
    assert list(page["/Resources"]["/Font"]) and not list(page.images)
    content = _content(data)
    assert _fills(content) and not re.search(r"\b(rg|RG)\b", content), "colours are DeviceCMYK operators, never RGB"
    shading = next(iter(page["/Resources"]["/Shading"].values())).get_object()
    assert shading["/ColorSpace"] == "/DeviceCMYK"
    assert len(shading["/Function"]["/Functions"][0]["/C0"]) == 4
    assert report["content"] == "vector" and report["color_space"] == "cmyk" and report["raster_fallbacks"] == {}
    assert report["fonts"] == 1
    # The print boxes survive: 11.25 x 17.25 in page, 11 x 17 in trim.
    assert [float(v) for v in page.trimbox] == [9, 9, 801, 1233]
    assert [float(v) for v in page.bleedbox] == [0, 0, 810, 1242]
    assert data == _poster().export(format="PDF", color_space="cmyk"), "output is deterministic"


def test_vector_colors_are_separated_like_raster_images():
    p = _poster()
    content = _content(p.export(format="PDF", color_space="cmyk"))
    expected = colors.cmyk_image(Image.new("RGBA", (1, 1), (0xe2, 0x72, 0x5b, 255)))
    # The bar's fill separates exactly like a one-pixel CMYK raster export of the same colour.
    target = tuple(round(v / 255, 3) for v in expected.getpixel((0, 0)))
    assert any(all(abs(a - b) < 0.0011 for a, b in zip(fill, target)) for fill in _fills(content))
    # Pure black text is 100% K, the white stroke no ink at all.
    assert (0.0, 0.0, 0.0, 1.0) in _fills(content) and (0.0, 0.0, 0.0, 0.0) in _fills(content, "K")


def test_separation_options_apply_to_vector_colors():
    p = Project(200, 100, "white")
    p.apply({"type": "solid", "name": "grey", "color": "#808080", "width": 200, "height": 100})
    full = _fills(_content(p.export(format="PDF", color_space="cmyk", black_generation=1.0)))
    none = _fills(_content(p.export(format="PDF", color_space="cmyk", black_generation=0.0)))
    assert any(f[:3] == (0, 0, 0) and f[3] > 0.49 for f in full), "full GCR puts the grey in the K plate"
    assert any(f[3] == 0 and min(f[:3]) > 0.49 for f in none), "no GCR keeps it in C, M and Y"
    # An ink limit caps the total coverage of dark, saturated colours.
    p.apply({"type": "solid", "name": "ink", "color": "#001a4d", "width": 200, "height": 100})
    limited = _fills(_content(p.export(format="PDF", color_space="cmyk", black_generation=0.2, ink_limit=200)))
    assert all(sum(f) <= 2.0 + 0.01 for f in limited)


def test_icc_profile_separates_vector_colors_but_text_black_stays_pure_k():
    profile = cmyk_profile()
    p = _poster()
    content = _content(p.export(format="PDF", color_space="cmyk", icc_profile=profile, intent="perceptual"))
    expected = colors.cmyk_image(Image.new("RGBA", (1, 1), (0xe2, 0x72, 0x5b, 255)), profile=colors.load_profile(profile),
                                  intent="perceptual")
    target = tuple(round(v / 255, 3) for v in expected.getpixel((0, 0)))
    assert any(all(abs(a - b) < 0.0011 for a, b in zip(fill, target)) for fill in _fills(content))
    assert (0.0, 0.0, 0.0, 1.0) in _fills(content)
    assert not re.search(r"\b(rg|RG)\b", content)


def test_effects_and_images_become_cmyk_images_and_are_listed():
    p = _poster()
    p.apply({"type": "shape", "name": "glow", "shape": "ellipse", "x": 300, "y": 1600, "width": 600, "height": 400,
             "fill": "#a8d5c8"})
    p.apply({"type": "layer-style", "name": "drop-shadow", "settings": {"dx": 20, "dy": 20, "blur": 20}})
    report = {}
    data = p.export(format="PDF", color_space="cmyk", report=report)
    page = _page(data)
    assert report["raster_fallbacks"] == {"1": [{"layer": "glow", "reason": "layer styles"}]}
    images = list(page["/Resources"]["/XObject"].values())
    assert len(images) == 1
    image = images[0].get_object()
    assert image["/ColorSpace"] == "/DeviceCMYK" and "/SMask" in image, "a CMYK tile with its transparency"
    assert "Port Ellery Quay" in page.extract_text(), "the rest of the page is still vector"


def test_cmyk_raster_content_is_still_available_and_matches_the_old_behavior():
    data = _poster().export(format="PDF", color_space="cmyk", pdf_content="raster")
    page = _page(data)
    assert len(list(page.images)) == 1 and not page.extract_text().strip()
    assert next(iter(page["/Resources"]["/XObject"].values()))["/ColorSpace"] == "/DeviceCMYK"
    assert [float(v) for v in page.trimbox] == [9, 9, 801, 1233]


def test_multi_page_cmyk_deck_keeps_every_page_vector():
    p = Project(1920, 1080, "#14263b")
    p.apply([{"type": "text", "name": "one", "text": "First slide", "size": 90, "x": 100, "y": 100, "color": "white"},
             {"type": "page", "action": "add", "name": "two"},
             {"type": "text", "name": "two", "text": "Second slide", "size": 90, "x": 100, "y": 100, "color": "#f2a541"}])
    reader = pypdf.PdfReader(io.BytesIO(p.export(format="PDF", color_space="cmyk")))
    assert len(reader.pages) == 2
    assert "First slide" in reader.pages[0].extract_text() and "Second slide" in reader.pages[1].extract_text()
