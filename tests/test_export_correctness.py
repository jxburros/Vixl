"""Export correctness and fill/stroke defaults: PDF fallback pages, PPTX plain-text weight, JPEG quality in PDF,
PDF/deck titles, open-shape fills, `none` colours, size warnings and ICC-aware image import."""

import hashlib
import io
import re
import sys
import zipfile
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from vixl import Project
from vixl.assets import add_image, decode
from vixl.model import Limits

sys.path.insert(0, str(Path(__file__).parent))
pypdf = pytest.importorskip("pypdf")
pptx = pytest.importorskip("pptx")
FONT = Path(__file__).parents[1] / "src" / "vixl" / "data" / "DejaVuSans.ttf"


def _slide_xml(project):
    return zipfile.ZipFile(io.BytesIO(project.export(format="PPTX"))).read("ppt/slides/slide1.xml").decode()


# -- #201 ---------------------------------------------------------------------------------------


def test_vector_pdf_of_blend_mode_page_falls_back_to_an_image():
    p = Project(400, 300, "white")
    p.apply([{"type": "shape", "name": "a", "shape": "rectangle", "x": 20, "y": 20, "width": 200, "height": 200, "fill": "#e2725b"},
             {"type": "shape", "name": "b", "shape": "ellipse", "x": 100, "y": 60, "width": 200, "height": 200, "fill": "#3366cc"},
             {"type": "blend", "target": "b", "value": "multiply"}])
    report = {}
    data = p.export(format="PDF", report=report)
    assert data.startswith(b"%PDF") and report["raster_fallbacks"]


def test_vector_pdf_of_adjustment_layer_page_falls_back_to_an_image():
    p = Project(400, 300, "white")
    p.apply([{"type": "shape", "name": "a", "shape": "rectangle", "x": 20, "y": 20, "width": 200, "height": 200, "fill": "#e2725b"},
             {"type": "adjustment", "name": "adj", "effects": [{"name": "exposure", "value": 0.2}]}])
    assert p.export(format="PDF").startswith(b"%PDF")


# -- #198 ---------------------------------------------------------------------------------------


def test_pptx_plain_text_in_a_bold_registered_face_is_bold():
    data = FONT.read_bytes()
    asset = f"fonts/{hashlib.sha256(data).hexdigest()}.ttf"
    p = Project(1920, 1080, "white")
    p.assets[asset] = data
    p.apply([{"type": "font-register", "name": "sans-700", "asset": asset}])
    p.apply({"type": "text", "name": "t", "text": "Heavy", "size": 80, "x": 100, "y": 100, "font": "sans-700"})
    xml = _slide_xml(p)
    assert re.search(r'<a:rPr[^>]* b="1"', xml)
    assert not re.search(r'<a:rPr[^>]* i="1"', xml)


# -- #202 ---------------------------------------------------------------------------------------


def _photo_project():
    rng = np.random.default_rng(1)
    image = Image.fromarray(rng.integers(0, 255, (200, 200, 3), dtype=np.uint8), "RGB")
    p = Project(400, 400, "white")
    name = add_image(p, image)
    p.apply([{"type": "add", "name": "photo", "asset": name, "x": 0, "y": 0}, {"type": "resize", "target": "photo", "width": 400, "height": 400}])
    return p


@pytest.mark.parametrize("content", ["vector", "raster"])
def test_pdf_quality_applies_to_images(content):
    p = _photo_project()
    default = p.export(format="PDF", pdf_content=content)
    low = p.export(format="PDF", pdf_content=content, quality=20)
    assert b"DCTDecode" in low and b"DCTDecode" not in default
    assert len(low) < len(default)


# -- #209 / #220 --------------------------------------------------------------------------------


def _poster():
    p = Project(1200, 1800, "white")
    p.apply([{"type": "text", "name": "kicker", "text": "Port Ellery Quay", "size": 30, "x": 60, "y": 40},
             {"type": "text", "name": "headline", "text": "Harbor Lights", "size": 160, "x": 60, "y": 120}])
    return p


def test_pdf_title_is_the_headline_not_the_first_text():
    info = pypdf.PdfReader(io.BytesIO(_poster().export(format="PDF"))).metadata
    assert info.title == "Harbor Lights"


def test_explicit_pdf_title_wins_and_file_name_is_the_last_resort(tmp_path):
    assert pypdf.PdfReader(io.BytesIO(_poster().export(format="PDF", title="Custom"))).metadata.title == "Custom"
    out = tmp_path / "quiet-sheet.pdf"
    Project(300, 300, "white").export(out)
    assert pypdf.PdfReader(str(out)).metadata.title == "quiet-sheet"


def test_deck_title_is_not_a_substring_match():
    from vixl.deck import title_layer

    p = Project(1920, 1080, "white")
    p.apply([{"type": "text", "name": "s-code-title", "text": "main.py", "size": 40, "x": 100, "y": 60},
             {"type": "text", "name": "title", "text": "The heading", "size": 100, "x": 100, "y": 300},
             {"type": "text", "name": "body", "text": "Body copy here", "size": 36, "x": 100, "y": 700}])
    assert title_layer(p)["name"] == "title"


def test_layer_role_title_is_explicit():
    from vixl.deck import title_layer

    p = Project(1920, 1080, "white")
    p.apply([{"type": "text", "name": "big", "text": "Not it", "size": 150, "x": 100, "y": 60},
             {"type": "text", "name": "small", "text": "It", "size": 40, "x": 100, "y": 400}])
    p.apply({"type": "layer-intent", "target": "small", "role": "title"})
    assert title_layer(p)["name"] == "small"


# -- #199 / #200 / #228 -------------------------------------------------------------------------


def _stroke_only_path():
    p = Project(200, 200, "#14263b")
    p.apply({"type": "shape", "name": "stalk", "shape": "path", "path": "M10 100 C60 20 140 180 190 100", "x": 0, "y": 0,
             "width": 200, "height": 200, "stroke": "#a8d5c8", "stroke_width": 6})
    return p


def test_default_fill_helper():
    from vixl.geometry import default_fill

    assert default_fill({"shape": "path", "path": "M0 0 L9 9", "stroke": "red"}) == "transparent"
    assert default_fill({"shape": "path", "path": "M0 0 L9 9 Z", "stroke": "red"}) == "white"
    assert default_fill({"shape": "path", "path": "M0 0 L9 9", "stroke": "red", "fill": "blue"}) == "blue"
    assert default_fill({"shape": "rectangle", "stroke": "red"}) == "white"
    assert default_fill({"shape": "path", "path": "M0 0 L9 9"}) == "white"  # no stroke either: unchanged


def test_open_stroked_path_has_no_fill_in_every_output():
    p = _stroke_only_path()
    image = np.asarray(p.render())[:, :, :3].astype(int)
    assert not (image > 235).all(axis=2).any(), "no white fill sliver"
    svg = p.export(format="SVG").decode()
    assert "rgb(255,255,255)" not in svg and "#ffffff" not in svg.lower()
    pdf = pypdf.PdfReader(io.BytesIO(p.export(format="PDF"))).pages[0]
    assert "1 1 1 rg" not in pdf.get_contents().get_data().decode("latin-1")
    slide = Project(1920, 1080, "#14263b")
    slide.apply({"type": "shape", "name": "wave", "shape": "path", "path": "M0 50 Q50 0 100 50 T200 50", "x": 100, "y": 100,
                 "width": 800, "height": 200, "stroke": "#a8d5c8", "stroke_width": 6})
    assert "FFFFFF" not in _slide_xml(slide)


def test_explicit_fill_on_an_open_path_is_kept():
    q = Project(200, 200, "#14263b")
    q.apply({"type": "shape", "name": "s", "shape": "path", "path": "M10 100 L190 100 L100 20", "x": 0, "y": 0, "width": 200,
             "height": 200, "stroke": "#a8d5c8", "stroke_width": 2, "fill": "#ff0000"})
    assert np.asarray(q.render())[80, 100, 0] > 200  # inside the triangle: red fill


def test_text_svg_omits_noop_stroke_attributes():
    p = Project(400, 200, "white")
    p.apply({"type": "text", "name": "t", "text": "Hi", "size": 80, "x": 20, "y": 20})
    svg = p.export(format="SVG").decode()
    assert "stroke-width" not in svg and "paint-order" not in svg
    p.apply({"type": "text-set", "target": "t", "stroke_width": 4, "stroke_color": "red"})
    assert "stroke-width" in p.export(format="SVG").decode()


# -- #223 ---------------------------------------------------------------------------------------


def test_none_colour_is_transparent():
    from vixl.colors import parse

    assert parse("none")[3] == 0 and parse("NONE")[3] == 0
    p = Project(200, 200, "white")
    p.apply({"type": "shape", "name": "s", "shape": "rectangle", "x": 10, "y": 10, "width": 100, "height": 100,
             "fill": "None", "stroke": "red", "stroke_width": 4})
    assert p.layer("s")["fill"] == "transparent"


def test_irregular_accepts_fill_none():
    p = Project(300, 300, "white")
    p.apply({"type": "shape", "name": "s", "shape": "ellipse", "x": 50, "y": 50, "width": 100, "height": 100, "fill": "none",
             "stroke": "black", "stroke_width": 3})
    p.apply({"type": "irregular", "target": "s", "seed": 3})


# -- #190 ---------------------------------------------------------------------------------------


def test_png_size_warning_names_texture_looks_and_max_bytes_warns():
    p = Project(1080, 1080, "#d8c9a8")
    p.apply({"type": "shape", "name": "panel", "shape": "rectangle", "x": 0, "y": 0, "width": 1080, "height": 1080, "fill": "#d8c9a8"})
    p.apply({"type": "look", "target": "panel", "look": "paper", "amount": 0.3})
    report = {}
    data = p.export(format="PNG", report=report, max_bytes=50_000)
    assert len(data) > 50_000
    text = " ".join(report["warnings"])
    assert "max_bytes" in text and "panel" in text
    quiet = {}
    Project(200, 200, "white").export(format="PNG", report=quiet, max_bytes=10_000_000)
    assert "warnings" not in quiet


# -- #194 ---------------------------------------------------------------------------------------


def test_cmyk_jpeg_with_a_profile_imports_through_the_profile():
    from icc_helper import cmyk_profile

    cyan = Image.new("CMYK", (8, 8), (180, 40, 0, 60))
    buffer = io.BytesIO()
    cyan.save(buffer, format="JPEG", icc_profile=cmyk_profile())
    data = buffer.getvalue()
    managed = decode(data, Limits(), "RGBA").getpixel((4, 4))
    naive = Image.open(io.BytesIO(data)).convert("RGBA").getpixel((4, 4))
    assert managed[3] == 255 and managed[:3] != naive[:3]
