"""Colour font files in text (COLRv0, COLRv1, OpenType-SVG, CBDT/CBLC, sbix): text set in one draws its colour
glyphs in every exporter (or reports the documented fallback), and counts in the metrics and checks."""

import hashlib
import io
import json
import re

import pytest
from PIL import Image

from tests import color_font_helper as fonts
from vixl import color_fonts, emojis, text
from vixl.checks import missing_glyphs
from vixl.errors import VixlError
from vixl.project import Project

RED, BLUE, GREEN, WHITE = (255, 0, 0, 255), (0, 0, 255, 255), (0, 170, 0, 255), (255, 255, 255, 255)
VECTOR, BITMAP = ("COLRv0", "COLRv1", "SVG"), ("CBDT", "sbix")
# At size 100 a glyph of the fixture fonts is 50 px wide: the colour glyph of "A" covers 40 x 70 px, red below and
# blue (or a gradient ending in blue) above; the text layer sits at (10, 10), so its baseline is at y = 80.
LOWER, UPPER, SECOND = (35, 70), (35, 13), (85, 45)


def register(project, data, name="color"):
    asset = f"fonts/{hashlib.sha256(data).hexdigest()}.ttf"
    project.assets[asset] = data
    project.apply({"type": "font-register", "name": name, "asset": asset})


def document(data, content="AB", **fields):
    project = Project(300, 140, background="white")
    register(project, data)
    project.apply({"type": "text", "text": content, "name": "t", "font": "color", "size": 100, "color": "#00aa00",
                   "x": 10, "y": 10, **fields})
    return project


def close(pixel, expected, tolerance=12):
    return all(abs(a - b) <= tolerance for a, b in zip(pixel, expected))


def svg_fallbacks(svg):
    found = re.search(rb'<metadata id="vixl-document">(.*?)</metadata>', svg, re.S)
    from html import unescape

    return json.loads(unescape(found.group(1).decode()))["vixl"].get("raster_fallbacks", [])


@pytest.mark.parametrize("kind", fonts.FORMATS)
def test_each_colour_format_draws_its_colours_in_png(kind):
    project = document(fonts.FORMATS[kind]())
    pixels = project.render().load()
    assert close(pixels[LOWER], RED) and close(pixels[UPPER], BLUE)
    # "B" has no colour glyph: it keeps its outline in the text colour (the CBDT fixture has no outlines at all).
    assert close(pixels[SECOND], WHITE if kind == "CBDT" else GREEN)
    assert close(pixels[150, 45], WHITE)


@pytest.mark.parametrize("kind", fonts.FORMATS)
def test_colour_glyphs_sit_on_the_baseline_and_count_in_the_metrics(kind):
    project = document(fonts.FORMATS[kind]())
    layer = project.layer("t")
    # The box is the ink of the 700-unit glyph (70 px), not the fallback renderer's guess, and two 50 px advances wide.
    assert (layer["width"], layer["height"]) == (100, 70)
    found = project.inspect()["layers"][0]
    ink = found["ink_bounds"]
    assert ink[1] == pytest.approx(10) and ink[3] == pytest.approx(70)
    assert ink[0] == pytest.approx(15, abs=1)
    assert missing_glyphs(project) == []
    # A box too small for the line is an overflow, as for outline text.
    project.apply({"type": "text-layout", "target": "t", "width": 60, "height": 40})
    from vixl.checks import boxed_text_overflow

    assert boxed_text_overflow(project, project.layer("t"))


@pytest.mark.parametrize("kind", VECTOR)
def test_svg_writes_vector_colour_glyphs(kind):
    project = document(fonts.FORMATS[kind]())
    svg = project.export(format="SVG")
    assert b"<image" not in svg and svg_fallbacks(svg) == []
    assert b"<script" not in svg  # the SVG fixture's glyph document carries one
    import resvg_py

    pixels = Image.open(io.BytesIO(resvg_py.svg_to_bytes(svg_string=svg.decode()))).convert("RGBA").load()
    assert close(pixels[LOWER], RED) and close(pixels[UPPER], BLUE) and close(pixels[SECOND], GREEN)
    assert project.export(format="SVG", svg_policy="strict")


@pytest.mark.parametrize("kind", BITMAP)
def test_svg_embeds_bitmap_glyphs_and_reports_them(kind):
    project = document(fonts.FORMATS[kind]())
    svg = project.export(format="SVG")
    assert b"<image" in svg and b"data:image/png;base64," in svg
    assert [(item["layer"], kind in item["reason"]) for item in svg_fallbacks(svg)] == [("t", True)]
    with pytest.raises(VixlError) as caught:
        project.export(format="SVG", svg_policy="strict")
    assert caught.value.code == "svg_raster_required"


def test_pdf_draws_flat_colr_layers_as_vector_paths():
    pypdf = pytest.importorskip("pypdf")
    project = document(fonts.colr_v0(foreground=True))
    report = {}
    pdf = project.export(format="PDF", report=report)
    assert report["raster_fallbacks"] == {}
    page = pypdf.PdfReader(io.BytesIO(pdf)).pages[0]
    content = page.get_contents().get_data().decode("latin-1")
    assert "1 0 0 rg" in content  # the red layer
    assert content.count("0 0.6667 0 rg") >= 2  # the foreground layer and the outline "B", both in the text colour
    assert not page.images


@pytest.mark.parametrize("kind", ["COLRv1", "SVG", "CBDT", "sbix"])
def test_pdf_keeps_other_colour_glyphs_as_an_image_and_says_so(kind):
    project = document(fonts.FORMATS[kind]())
    report = {}
    pdf = project.export(format="PDF", report=report)
    assert pdf.startswith(b"%PDF")
    assert [(item["layer"], kind in item["reason"]) for item in report["raster_fallbacks"]["1"]] == [("t", True)]


@pytest.mark.parametrize("kind", fonts.FORMATS)
@pytest.mark.parametrize("rich", [False, True])
def test_pptx_keeps_colour_glyphs_as_a_picture_and_says_so(kind, rich):
    project = Project(300, 140, background="white")
    register(project, fonts.FORMATS[kind]())
    project.apply({"type": "rich-text" if rich else "text", **({"markdown": "AB"} if rich else {"text": "AB"}),
                   "name": "t", "font": "color", "size": 100, "color": "#00aa00", "x": 10, "y": 10})
    report = {}
    assert len(project.export(format="PPTX", report=report)) > 1000
    assert [(item["layer"], kind in item["reason"]) for item in report["raster_fallbacks"]["1"]] == [("t", True)]


def test_outline_text_is_not_reported_as_colour_glyphs():
    project = Project(300, 140, background="white")
    project.apply({"type": "text", "text": "AB", "name": "t", "size": 60})
    assert color_fonts.layer_kinds(project, project.layer("t")) == []
    report = {}
    project.export(format="PPTX", report=report)
    assert report["raster_fallbacks"] == {}


@pytest.mark.parametrize("kind", fonts.FORMATS)
def test_rich_text_draws_colour_glyphs(kind):
    project = Project(300, 160, background="white")
    register(project, fonts.FORMATS[kind]())
    project.apply({"type": "rich-text", "markdown": "AB", "name": "t", "font": "color", "size": 100, "color": "#00aa00",
                   "x": 10, "y": 10})
    assert color_fonts.layer_kinds(project, project.layer("t")) == [kind]
    image = project.render()
    colors = {pixel[:3] for _, pixel in image.getcolors(maxcolors=1 << 20)}
    assert RED[:3] in colors and BLUE[:3] in colors


def test_the_foreground_palette_entry_takes_the_text_colour():
    project = document(fonts.colr_v0(foreground=True))
    pixels = project.render().load()
    assert close(pixels[LOWER], RED) and close(pixels[UPPER], GREEN)
    project.apply({"type": "text-set", "target": "t", "color": "#0000ff"})
    assert close(project.render().load()[UPPER], BLUE)


def test_colrv1_gradients_transforms_composites_and_clip_boxes():
    project = Project(300, 140, background="white")
    register(project, fonts.colr_v1_paints())
    project.apply({"type": "text", "text": "ACDEF", "name": "t", "font": "color", "size": 100, "color": "#00aa00",
                   "x": 10, "y": 10})
    pixels = project.render().load()

    def at(index, x, y):
        """The pixel at font-unit (x, y) of the glyph at ``index``."""
        return pixels[round(10 + 50 * index + x / 10), round(80 - y / 10)]

    assert close(at(0, 250, 350), RED, 30) and close(at(0, 250, 500), (255, 255, 0, 255), 30)  # radial: centre, r=150
    assert close(at(1, 250, 500), (255, 128, 0, 255), 30)  # sweep: a quarter turn is halfway from red to yellow
    assert close(at(1, 250, 200), (128, 128, 128, 255), 30)  # three quarters: halfway from yellow to blue
    assert close(at(2, 250, 350), RED) and close(at(2, 80, 30), WHITE)  # src-in: the corner is outside the turned box
    assert close(at(3, 300, 300), (128, 128, 0, 255), 30)  # yellow multiplied onto half-transparent blue
    assert close(at(3, 100, 50), (128, 128, 255, 255), 30)  # the backdrop alone
    assert close(at(3, 100, 650), WHITE)  # above the clip box
    assert close(at(4, 250, 350), GREEN) and not close(at(4, 250, 100), GREEN)  # the text-colour box over the glyph of A


def test_bitmap_strike_is_the_smallest_one_large_enough():
    data = fonts.sbix(ppems=(20, 70, 140))
    assert color_fonts.strikes(text.face(data)[0]) == (20, 70, 140)
    assert color_fonts.strike_for((20, 70, 140), 50) == 70
    assert color_fonts.strike_for((20, 70, 140), 70) == 70
    assert color_fonts.strike_for((20, 70, 140), 500) == 140
    assert color_fonts.strike_for((20, 70, 140), None) == 140
    small, large = text.glyph_outline(data, "A", 12)[0], text.glyph_outline(data, "A", 100)[0]
    assert small.kind == large.kind == "sbix" and len(small) < len(large)
    # Whatever the strike, the glyph covers the same part of the em.
    assert small.bounds == pytest.approx(large.bounds, abs=30)
    pixels = document(data).render().load()
    assert close(pixels[LOWER], RED) and close(pixels[UPPER], BLUE)


def test_a_colour_font_in_the_fallbacks_covers_its_characters():
    project = Project(300, 140, background="white")
    register(project, fonts.cbdt(char=""), "symbols")
    project.apply({"type": "font-fallbacks", "fonts": ["symbols"]})
    project.apply({"type": "text", "text": "", "name": "t", "size": 100, "color": "#00aa00", "x": 10, "y": 10})
    assert missing_glyphs(project) == []
    assert text.glyph_coverage(project, project.layer("t"))["fallback"] == [""]
    colors = {pixel[:3] for _, pixel in project.render().getcolors(maxcolors=1 << 20)}
    assert RED[:3] in colors and BLUE[:3] in colors


def test_the_emoji_library_stays_the_default_over_a_colour_font():
    project = document(fonts.colr_v0(char="😀"), "😀")
    glyph = text.shape(text.font_data(project, project.layer("t")), "😀", 100)[0][0]
    assert emojis.is_glyph(glyph.data)  # VIXL Line artwork, although the layer's font has a colour glyph for it
    project.apply({"type": "emoji-mode", "mode": "font"})
    glyph = text.shape(text.font_data(project, project.layer("t")), "😀", 100)[0][0]
    assert not emojis.is_glyph(glyph.data)
    assert isinstance(text.glyph_outline(glyph.data, glyph.name)[0], color_fonts.ColorGlyph)
    pixels = project.render().load()
    assert close(pixels[LOWER], RED) and close(pixels[UPPER], BLUE)


def test_colour_glyphs_follow_a_text_path_and_refuse_a_warp():
    project = document(fonts.colr_v0(), "AA")
    project.apply({"type": "text-layout", "target": "t", "width": 280, "height": 120, "path": [[10, 100], [270, 100]]})
    colors = {pixel[:3] for _, pixel in project.render().getcolors(maxcolors=1 << 20)}
    assert RED[:3] in colors and BLUE[:3] in colors
    report = {}
    project.export(format="PDF", report=report)
    assert "colour font" in report["raster_fallbacks"]["1"][0]["reason"]
    project = document(fonts.colr_v0(), "AA")
    with pytest.raises(VixlError) as caught:
        project.apply({"type": "text-layout", "target": "t", "width": 280, "height": 120, "warp": "arc"})
        project.render()
    assert "Colour font glyphs cannot be bent" in str(caught.value)


def test_a_bitmap_only_colour_font_imports_saves_and_reloads(tmp_path):
    from vixl.fonts import import_font

    path = tmp_path / "emoji.ttf"
    path.write_bytes(fonts.cbdt())
    project = Project(300, 140, background="white")
    import_font(project, path, "color")
    project.apply({"type": "text", "text": "A", "name": "t", "font": "color", "size": 100, "x": 10, "y": 10})
    project.save(tmp_path / "doc.vixl")
    loaded = Project.load(tmp_path / "doc.vixl")
    pixels = loaded.render().load()
    assert close(pixels[LOWER], RED) and close(pixels[UPPER], BLUE)


def test_a_font_with_neither_outlines_nor_colour_glyphs_is_still_refused():
    from fontTools.ttLib import TTFont

    font = TTFont(io.BytesIO(fonts.cbdt()))
    del font["CBDT"], font["CBLC"]
    buffer = io.BytesIO()
    font.save(buffer)
    with pytest.raises(text.UnsupportedText):
        text._face(buffer.getvalue())


def test_fitted_text_draws_colour_glyphs():
    project = document(fonts.sbix(), "AB AB AB")
    project.apply({"type": "text-layout", "target": "t", "width": 120, "height": 60, "fit": True})
    colors = {pixel[:3] for _, pixel in project.render().getcolors(maxcolors=1 << 20)}
    assert RED[:3] in colors and BLUE[:3] in colors


@pytest.mark.parametrize("rich", [False, True])
def test_animated_text_moves_colour_glyphs(rich):
    from vixl.timeline import render_at

    project = Project(300, 200, background="white")
    register(project, fonts.colr_v0())
    project.apply([{"type": "rich-text" if rich else "text", **({"markdown": "AA"} if rich else {"text": "AA"}),
                    "name": "t", "font": "color", "size": 100, "color": "#00aa00", "x": 10, "y": 60},
                   {"type": "timeline-set", "duration": 2000, "fps": 10, "loop_mode": "off"},
                   {"type": "text-animate", "target": "t", "preset": "fade-down", "unit": "char", "duration": 1000,
                    "distance": 30, "easing": "linear"}])
    for time in (500, 2000):
        colors = {pixel[:3] for _, pixel in render_at(project, time).getcolors(maxcolors=1 << 20)}
        assert any(r - b > 80 and r - g > 80 for r, g, b in colors) and any(b - r > 80 and b - g > 80 for r, g, b in colors)
