"""Letter-spacing (tracking) measures the way it draws, and glyph ink past the text box is not cut off."""

import io
from pathlib import Path
import zipfile

import numpy as np
from PIL import Image
import pytest
import resvg_py

from vixl import Project
from vixl.proxy import render_preview
from vixl.richtext import layout
from vixl.text_metrics import inspect_text


def ink(image, threshold=60):
    """Bounding box of dark pixels on a white render."""
    grey = np.asarray(image.convert("L"), dtype=int)
    rows, cols = np.nonzero(grey < 255 - threshold)
    return (int(cols.min()), int(rows.min()), int(cols.max()) + 1, int(rows.max()) + 1)


def test_tracking_goes_between_letters_not_after_the_last():
    p = Project(800, 200, "white")
    p.apply({"type": "rich-text", "name": "plain", "markdown": "HELLO", "size": 48, "color": "black"})
    p.apply({"type": "rich-text", "name": "tracked", "markdown": "[HELLO]{tracking=20}", "size": 48, "color": "black"})
    plain, tracked = layout(p, p.layer("plain")), layout(p, p.layer("tracked"))
    assert tracked.box[2] == pytest.approx(plain.box[2] + 4 * 20)
    assert p.layer("tracked")["width"] == tracked.width


@pytest.mark.parametrize("align", ["center", "right"])
def test_tracked_text_is_ink_aligned_in_its_box(align):
    p = Project(800, 200, "white")
    p.apply({"type": "rich-text", "name": "t", "markdown": "[OHIO]{tracking=30}", "size": 60, "color": "black",
             "x": 100, "y": 50, "width": 600, "height": 100, "align": align})
    box = ink(p.render())
    if align == "center":
        assert abs((box[0] + box[2]) / 2 - 400) <= 1
    else:
        assert 700 - 8 <= box[2] <= 700  # the O's right side bearing, not 30 px of tracking


def test_centred_tracked_text_stays_centred_on_the_canvas():
    p = Project(800, 200, "white")
    p.apply({"type": "text", "name": "t", "text": "HOHOHO", "size": 48, "color": "black", "x": 100, "y": 60})
    p.apply({"type": "text-style", "target": "t", "tracking": 24})
    p.apply({"type": "move", "target": "t", "x": (800 - p.layer("t")["width"]) / 2})
    box = ink(p.render())
    assert abs((box[0] + box[2]) / 2 - 400) <= 1


def test_tracked_line_that_fits_without_its_trailing_space_does_not_wrap():
    p = Project(800, 200, "white")
    p.apply({"type": "rich-text", "name": "t", "markdown": "WIDE", "size": 48, "color": "black"})
    width = layout(p, p.layer("t")).box[2] + 3 * 40 + 1
    p.apply({"type": "rich-text", "name": "boxed", "markdown": "[WIDE]{tracking=40}", "size": 48, "color": "black",
             "width": width, "height": 200})
    result = layout(p, p.layer("boxed"))
    assert len(result.lines) == 1
    assert result.box[2] == pytest.approx(width - 1)  # still tracked


def test_adding_tracking_to_plain_text_does_not_move_it():
    p = Project(900, 300, "white")
    p.apply({"type": "text", "name": "t", "text": "Summer Market", "size": 64, "color": "black", "x": 80, "y": 90})
    layer = p.layer("t")
    before = inspect_text(p, layer, (layer["x"], layer["y"], layer["width"], layer["height"]))
    left = ink(p.render())[0]
    p.apply({"type": "text-style", "target": "t", "tracking": 6})
    layer = p.layer("t")
    after = inspect_text(p, layer, (layer["x"], layer["y"], layer["width"], layer["height"]))
    assert after["baseline"] == pytest.approx(before["baseline"], abs=0.5)
    assert abs(ink(p.render())[0] - left) <= 1


def test_downscaled_preview_of_tracked_text_matches_the_export():
    p = Project(3000, 600, "white")
    # 110 px at a 0.205 preview is 22.55 px: rounded to whole pixels, the line would set 2% wide.
    p.apply({"type": "text", "name": "t", "text": "TRACKED HEADLINE TEXT", "size": 110, "color": "black",
             "x": 100, "y": 200})
    p.apply({"type": "text-style", "target": "t", "tracking": 40})
    full = ink(p.render())
    preview = render_preview(p, 615, 1000)
    scale = preview.width / 3000
    small = ink(preview)
    for edge, expected in zip(small, full):
        assert abs(edge / scale - expected) <= 2.5 / scale


def test_italic_overhang_is_drawn_past_the_box():
    """Synthetic italic slants the last letter past its advance; it used to be cut at the layer's edge."""
    p = Project(600, 300, "white")
    p.apply({"type": "rich-text", "name": "auto", "markdown": "*Wolf*", "size": 120, "color": "black", "x": 50, "y": 60})
    clipped_at = p.layer("auto")["x"] + p.layer("auto")["width"]
    drawn = ink(p.render())
    assert drawn[2] > clipped_at + 4
    # The same line in a box wide enough to hold the slant draws the same ink.
    q = Project(600, 300, "white")
    q.apply({"type": "rich-text", "name": "wide", "markdown": "*Wolf*", "size": 120, "color": "black", "x": 50, "y": 60,
             "width": 500, "height": p.layer("auto")["height"]})
    assert ink(q.render()) == drawn
    # The layer box is still the layout box: alignment and wrapping are unchanged.
    assert p.layer("auto")["width"] == layout(p, p.layer("auto")).width


def test_overhang_agrees_across_png_svg_and_pdf():
    pdfium = pytest.importorskip("pypdfium2")
    p = Project(600, 300, "white")
    p.apply({"type": "rich-text", "name": "t", "markdown": "*Wolf*", "size": 120, "color": "black", "x": 50, "y": 60})
    png = ink(p.render())
    svg = Image.open(io.BytesIO(resvg_py.svg_to_bytes(svg_string=p.export(format="SVG").decode())))
    white = Image.new("RGBA", svg.size, "white")
    white.alpha_composite(svg.convert("RGBA"))
    document = pdfium.PdfDocument(io.BytesIO(p.export(format="PDF")))
    try:
        page = document[0]
        pdf = page.render(scale=600 / page.get_width()).to_pil()
    finally:
        document.close()
    for other in (ink(white), ink(pdf)):
        assert all(abs(a - b) <= 2 for a, b in zip(other, png)), (other, png)


def test_scaled_auto_sized_text_with_overhang_fills_its_stored_box():
    """A preview stores a rounded box for auto-sized text; the padded drawing is scaled to it like the plain one."""
    p = Project(2000, 600, "white")
    p.apply({"type": "rich-text", "name": "t", "markdown": "*Wolf Lindqvist*", "size": 150, "color": "black",
             "x": 100, "y": 150})
    full = ink(p.render())
    preview = render_preview(p, 397, 1000)
    scale = preview.width / 2000
    for edge, expected in zip(ink(preview), full):
        assert abs(edge / scale - expected) <= 2.5 / scale


def test_pptx_does_not_track_after_the_last_letter():
    p = Project(800, 200, "white")
    p.apply({"type": "rich-text", "name": "t", "markdown": "[HELLO]{tracking=10}", "size": 48, "color": "black"})
    with zipfile.ZipFile(io.BytesIO(p.export(format="PPTX"))) as deck:
        slide = deck.read("ppt/slides/slide1.xml").decode()
    assert slide.count(' spc="') == 1
    assert "<a:t>HELL</a:t>" in slide and "<a:t>O</a:t>" in slide


def test_adding_layer_tracking_keeps_plain_text_in_place():
    p = Project(900, 300, "white")
    p.apply({"type": "text", "name": "t", "text": "HELLO WORLD", "size": 64, "color": "black", "x": 120, "y": 100})
    before = ink(p.render())
    height = p.layer("t")["height"]
    p.apply({"type": "text-set", "target": "t", "tracking": 20})
    after = ink(p.render())
    assert after[0] == before[0] and after[1] == before[1] and after[3] == before[3]
    assert after[2] == pytest.approx(before[2] + 10 * 20, abs=1)
    assert p.layer("t")["height"] == height


def test_layer_tracked_text_centres_on_its_ink():
    p = Project(900, 300, "white")
    p.apply({"type": "text", "name": "t", "text": "HOHOHO", "size": 64, "color": "black", "x": 100, "y": 100,
             "tracking": 30})
    p.apply({"type": "move", "target": "t", "x": (900 - p.layer("t")["width"]) / 2})
    box = ink(p.render())
    assert abs((box[0] + box[2]) / 2 - 450) <= 1


def test_downscaled_preview_scales_layer_tracking():
    p = Project(3000, 600, "white")
    p.apply({"type": "text", "name": "t", "text": "TRACKED HEADLINE TEXT", "size": 110, "color": "black",
             "x": 100, "y": 200, "tracking": 40})
    full = ink(p.render())
    for width in (594, 1500):
        preview = render_preview(p, width, 1000)
        scale = preview.width / 3000
        for edge, expected in zip(ink(preview), full):
            assert abs(edge / scale - expected) <= 2.5 / scale


def test_linked_document_draws_tracked_text_at_the_linked_scale(tmp_path):
    source = Project(2000, 400, "white")
    source.apply({"type": "text", "name": "t", "text": "LINKED TRACKED TITLE", "size": 110, "color": "black",
                  "x": 60, "y": 120})
    source.apply({"type": "text-style", "target": "t", "tracking": 40})
    source.save(tmp_path / "title.vixl")
    full = ink(source.render())
    host = Project(500, 200, "white")
    host.save(tmp_path / "host.vixl")
    host.apply({"type": "link", "source": "title.vixl", "name": "title", "width": 410})
    scale = 410 / 2000
    for edge, expected in zip(ink(host.render()), full):
        assert abs(edge / scale - expected) <= 2.5 / scale


PINYON = Path.home() / ".cache/vixl/fonts/pinyon-script-400.ttf"


@pytest.mark.skipif(not PINYON.exists(), reason="Pinyon Script is not in the font cache")
def test_script_swash_is_not_cut_off():
    p = Project(900, 300, "white")
    p.apply({"type": "rich-text", "name": "t", "markdown": "Lindqvist", "size": 120, "font": str(PINYON),
             "color": "black", "x": 100, "y": 60})
    layer = p.layer("t")
    q = Project(900, 300, "white")
    q.apply({"type": "rich-text", "name": "t", "markdown": "Lindqvist", "size": 120, "font": str(PINYON),
             "color": "black", "x": 100, "y": 60, "width": 700, "height": layer["height"]})
    drawn = ink(p.render())
    assert drawn[2] > layer["x"] + layer["width"]  # the final t's stroke reaches past its advance
    assert drawn == ink(q.render())
