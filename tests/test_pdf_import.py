"""PDF import as editable layers: Vixl's own PDFs come back close to the original; other PDFs become layers."""

from pathlib import Path
import sys

import numpy as np
from PIL import Image
import pytest

pdfium = pytest.importorskip("pypdfium2")

from vixl import Project  # noqa: E402
from vixl.errors import VixlError  # noqa: E402
from vixl.imports import import_document  # noqa: E402

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "tests" / "visual"))
from visual_fixtures import FIXTURES as DOCUMENTS  # noqa: E402

sys.path.pop(0)


def pixels(image):
    return np.asarray(image.convert("RGBA"), dtype=int)


def pdf_image(data, scale=1):
    document = pdfium.PdfDocument(data)
    try:
        return document[0].render(scale=scale).to_pil().convert("RGBA")
    finally:
        document.close()


def poster():
    from vixl.assets import add_image

    p = Project(320, 200, "#f8f4ec")
    tile = Image.new("RGBA", (24, 16), (200, 30, 30, 255))
    tile.paste((30, 90, 200, 255), (12, 0, 24, 16))
    asset = add_image(p, tile)
    p.apply([
        {"type": "text", "name": "title", "text": "Spring fair", "size": 34, "x": 16, "y": 12, "color": "#1d3557"},
        {"type": "text", "name": "body", "text": "Saturday 10–4\nTown square", "size": 16, "x": 16, "y": 64,
         "color": "#264653"},
        {"type": "text", "name": "tilt", "text": "Free entry", "size": 18, "x": 200, "y": 150, "color": "#e63946",
         "rotation": -12},
        {"type": "shape", "shape": "star", "name": "star", "x": 230, "y": 16, "width": 70, "height": 70,
         "fill": "#e9c46a", "stroke": "#264653", "stroke_width": 3},
        {"type": "shape", "shape": "path", "name": "wave", "path": "M0 20 C30 0 60 40 90 20", "x": 16, "y": 140,
         "width": 90, "height": 40, "stroke": "#2a9d8f", "stroke_width": 4, "fill": "transparent",
         "line_cap": "round"},
        {"type": "shape", "shape": "ellipse", "name": "dot", "x": 130, "y": 120, "width": 40, "height": 40,
         "fill": "#e76f51"},
        {"type": "add", "asset": asset, "name": "tile", "x": 140, "y": 30, "width": 48, "height": 32},
    ])
    return p


ROUND_TRIP = {"poster": (poster, 1.2), "shapes_and_strokes": (DOCUMENTS["shapes_and_strokes"], 1.0),
              "path_stroke_only": (DOCUMENTS["path_stroke_only"], 1.0), "text_plain": (DOCUMENTS["text_plain"], 0.5),
              "text_stroked": (DOCUMENTS["text_stroked"], 0.5), "chart_bar": (DOCUMENTS["chart_bar"], 0.5),
              "effect_blur_shadow_glow": (DOCUMENTS["effect_blur_shadow_glow"], 0.5)}


@pytest.mark.parametrize("name", sorted(ROUND_TRIP))
def test_own_pdf_comes_back_as_editable_layers_close_to_the_original(name):
    build, tolerance = ROUND_TRIP[name]
    original = build()
    data = original.export(format="PDF")
    restored = Project(10, 10)
    result = import_document(restored, data, "pdf")
    assert result["mode"] == "editable"
    c = original.state["canvas"]
    assert (restored.state["canvas"]["width"], restored.state["canvas"]["height"]) == (c["width"], c["height"])
    texts = sorted(x["text"] for x in original.state["layers"] if x["type"] == "text" and x["visible"])
    assert sorted(x["text"] for x in restored.state["layers"] if x["type"] == "text") == texts
    difference = np.abs(pixels(restored.render()) - pixels(original.render()))
    assert difference.mean() < tolerance, difference.mean()


def test_own_pdf_keeps_text_live_with_size_colour_place_and_rotation():
    original = poster()
    restored = Project(10, 10)
    import_document(restored, original.export(format="PDF"), "pdf")
    by_text = {x["text"]: x for x in restored.state["layers"] if x["type"] == "text"}
    title, body, tilt = by_text["Spring fair"], by_text["Saturday 10–4\nTown square"], by_text["Free entry"]
    assert title["size"] == 34 and title["color"] == "#1d3557"
    assert abs(title["x"] - 16) <= 1 and abs(title["y"] - 12) <= 1
    assert body["size"] == 16 and abs(body["line_height"] - original.layer("body")["line_height"]) < 0.1
    assert abs(tilt["rotation"] % 360 - 348) < 0.01
    shapes = [x for x in restored.state["layers"] if x["type"] == "shape"]
    star = next(x for x in shapes if x["fill"] == "#e9c46a")
    # The fill and the outline the PDF paints as two objects are one layer again.
    assert star["stroke"] == "#264653" and star["stroke_width"] == 3
    wave = next(x for x in shapes if x["stroke"] == "#2a9d8f")
    assert wave["fill"] == "transparent" and wave["line_cap"] == "round"
    tile = next(x for x in restored.state["layers"] if x["type"] == "raster")
    assert (round(tile["x"]), round(tile["y"]), round(tile["width"]), round(tile["height"])) == (140, 30, 48, 32)
    assert restored.state["canvas"]["background"] == "#f8f4ec"


def test_registered_fonts_match_the_pdf_font_family():
    from vixl.fonts import import_font

    font = ROOT / "src" / "vixl" / "data" / "NotoSans-Regular.ttf"
    original = Project(200, 60, "#ffffff")
    import_font(original, font, "noto")
    original.apply({"type": "text", "name": "t", "text": "Noto here", "font": "noto", "size": 24, "x": 8, "y": 8})
    target = Project(10, 10)
    import_font(target, font, "body-face")
    result = import_document(target, original.export(format="PDF"), "pdf")
    layer = next(x for x in target.state["layers"] if x["type"] == "text")
    assert layer["font"] == target.state["fonts"]["body-face"] and not result.get("warnings")
    assert np.abs(pixels(target.render()) - pixels(original.render())).mean() < 0.2


def test_shadings_and_effects_become_image_layers_in_stacking_order():
    p = Project(160, 100, "#ffffff")
    p.apply([{"type": "shape", "shape": "rectangle", "name": "under", "width": 160, "height": 30, "y": 70,
              "fill": "#264653"},
             {"type": "gradient", "name": "sky", "width": 120, "height": 60, "x": 20, "y": 10, "start": "#e63946",
              "end": "#1d3557"},
             {"type": "shape", "shape": "ellipse", "name": "sun", "width": 30, "height": 30, "x": 60, "y": 25,
              "fill": "#e9c46a"}])
    q = Project(10, 10)
    result = import_document(q, p.export(format="PDF"), "pdf")
    kinds = [x["type"] for x in q.state["layers"]]
    assert kinds == ["shape", "raster", "shape"]
    assert result["rasterized"][0]["reason"] == ["shading"]
    assert np.abs(pixels(q.render()) - pixels(p.render())).mean() < 0.5


def test_foreign_pdf_text_paths_and_images():
    data = (ROOT / "tests" / "fixtures" / "pdf" / "simple.pdf").read_bytes()
    p = Project(10, 10)
    result = import_document(p, data, "pdf")
    assert (p.state["canvas"]["width"], p.state["canvas"]["height"]) == (200, 150)
    assert p.state["canvas"]["background"] == "#ffffff"
    layers = p.state["layers"]
    assert [x["type"] for x in layers] == ["shape", "shape", "shape", "text", "raster"]
    rect, curve, frame, text, image = layers
    assert rect["fill"] == "#0000ff" and (rect["x"], rect["y"], rect["width"], rect["height"]) == (20, 90, 60, 40)
    assert curve["fill"] == "transparent" and curve["stroke"] == "#ff0000" and curve["stroke_width"] == 3
    assert curve["line_cap"] == "round"
    assert text["text"] == "Hello PDF\nSecond line" and text["size"] == 18 and text["color"] == "#333333"
    assert any("Helvetica" in w for w in result["warnings"])
    # The even-odd frame keeps its hole.
    assert p.render().getpixel((150, 35)) == (255, 255, 255, 255)
    assert (image["width"], image["height"]) == (30, 20)
    assert np.abs(pixels(p.render()) - pixels(pdf_image(data))).mean() < 6


def test_import_into_a_document_with_layers_keeps_its_canvas():
    p = Project(400, 300, "#000000")
    p.apply({"type": "shape", "shape": "rectangle", "name": "existing", "width": 10, "height": 10})
    result = import_document(p, (ROOT / "tests" / "fixtures" / "pdf" / "simple.pdf").read_bytes(), "pdf")
    assert (p.state["canvas"]["width"], p.state["canvas"]["background"]) == (400, "#000000")
    assert result["layers"] == {"text": 2, "path": 3, "image": 1}
    assert p.state["layers"][0]["name"] == "existing" and len(p.state["layers"]) == 6


def test_raster_import_remains_available():
    data = Project(100, 50, "#ff0000").export(format="PDF")
    p = Project(300, 300)
    result = import_document(p, data, "pdf", svg_mode="appearance", dpi=144)
    layer = p.state["layers"][0]
    assert result["mode"] == "appearance" and layer["type"] == "raster" and (layer["width"], layer["height"]) == (200, 100)
    assert p.state["canvas"]["width"] == 300


def test_out_of_range_page_leaves_the_document_untouched():
    p = Project(50, 50)
    head = p.head
    with pytest.raises(VixlError, match="out of range"):
        import_document(p, Project(20, 20, "red").export(format="PDF"), "pdf", page=2)
    assert p.head == head and not p.state["layers"]
