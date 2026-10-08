"""Exporters agree with the raster renderer: open paths, stroke overflow, masked opacity, faces and simulations."""

import io
import re
import zipfile
from importlib import resources

import numpy as np
import pytest
from fontTools.ttLib import TTFont
from PIL import Image

from vixl import Project, VixlError

OPEN_PATH = {"type": "shape", "shape": "path", "name": "p", "path": "M 0 0 Q 100 200 200 0", "stroke": "#cc0000",
             "stroke_width": 6, "x": 100, "y": 50}


@pytest.mark.parametrize("extra", [{}, {"width": 200}, {"width": 200.5, "height": 100.25}])
def test_open_path_with_a_derived_size_stays_unfilled_in_raster(extra):
    project = Project(400, 200, background="#3355aa")
    project.apply([{**OPEN_PATH, **extra}])
    assert project.render().convert("RGB").getpixel((200, 80)) == (51, 85, 170)


def test_irregular_open_path_stays_unfilled():
    project = Project(400, 200, background="#3355aa")
    project.apply([OPEN_PATH, {"type": "irregular", "target": "p", "seed": 3}])
    assert project.render().convert("RGB").getpixel((200, 80)) == (51, 85, 170)


def test_svg_strokes_reach_past_the_layer_box(tmp_path):
    import resvg_py

    project = Project(400, 200, background="#ffffff")
    project.apply([{"type": "shape", "shape": "path", "name": "v", "path": "M 0 0 L 100 100 L 200 0", "stroke": "#cc0000",
                    "stroke_width": 20, "x": 100, "y": 50, "width": 200, "height": 100}])
    project.export(tmp_path / "v.svg")
    image = Image.open(io.BytesIO(resvg_py.svg_to_bytes(svg_string=(tmp_path / "v.svg").read_text()))).convert("RGB")
    pixels = np.asarray(image)
    ys, xs = np.nonzero((pixels[:, :, 0] > 150) & (pixels[:, :, 1] < 100))
    assert xs.min() < 100 and xs.max() > 300 and ys.min() < 50 and ys.max() > 150


@pytest.mark.parametrize("extra", [
    {"type": "mask", "target": "r", "action": "create"},
    {"type": "effect", "target": "r", "name": "posterize", "amount": 4},
])
def test_pdf_applies_layer_opacity_once_on_raster_fallbacks(tmp_path, extra):
    pdfium = pytest.importorskip("pypdfium2")
    project = Project(200, 100, background="#ffffff")
    project.apply([{"type": "shape", "shape": "rectangle", "name": "r", "width": 200, "height": 100, "fill": "#000000",
                    "opacity": 0.5}, extra])
    project.export(tmp_path / "m.pdf")
    page = pdfium.PdfDocument(str(tmp_path / "m.pdf"))[0].render(scale=1).to_pil().convert("L")
    assert abs(page.getpixel((100, 50)) - project.render().convert("L").getpixel((100, 50))) <= 2


def test_pptx_fallback_image_carries_opacity_once(tmp_path):
    project = Project(200, 100, background="#ffffff")
    project.apply([{"type": "shape", "shape": "rectangle", "name": "r", "width": 200, "height": 100, "fill": "#000000",
                    "opacity": 0.5}, {"type": "mask", "target": "r", "action": "create"}])
    project.export(tmp_path / "m.pptx")
    package = zipfile.ZipFile(tmp_path / "m.pptx")
    media = [name for name in package.namelist() if name.startswith("ppt/media/")]
    alpha = Image.open(io.BytesIO(package.read(media[0]))).getchannel("A")
    assert alpha.getextrema() == (128, 128)


def test_pptx_draws_a_skewed_layer_as_a_listed_picture(tmp_path):
    project = Project(400, 300, background="#ffffff")
    project.apply([{"type": "shape", "shape": "rectangle", "name": "r", "width": 60, "height": 60, "x": 200, "y": 220,
                    "fill": "#ff0000"}, {"type": "skew", "target": "r", "x": 30}])
    report = {}
    project.export(tmp_path / "s.pptx", report=report)
    assert report["raster_fallbacks"] == {"1": [{"layer": "r", "reason": "skew"}]}
    xml = zipfile.ZipFile(tmp_path / "s.pptx").read("ppt/slides/slide1.xml").decode()
    assert "<p:pic>" in xml and 'prst="rect"' in xml.split("<p:pic>")[1]
    emu = int(re.search(r'sldSz cx="(\d+)"', zipfile.ZipFile(tmp_path / "s.pptx").read("ppt/presentation.xml").decode())[1]) / 400
    left, top = (int(v) / emu for v in re.search(r'<a:off x="(\d+)" y="(\d+)"/>', xml.split("<p:pic>")[1]).groups())
    box = project.render().convert("RGB").point(lambda v: 255 - v).getbbox()
    assert abs(left - box[0]) <= 1 and abs(top - box[1]) <= 1


def test_pptx_marks_bold_and_italic_faces_imported_under_any_name(tmp_path):
    from vixl.fonts import import_font

    font = TTFont(io.BytesIO(resources.files("vixl").joinpath("data/DejaVuSans.ttf").read_bytes()))
    font["OS/2"].usWeightClass = 700
    font["OS/2"].fsSelection = 0b100001  # bold, italic
    font.save(tmp_path / "face.ttf")
    project = Project(400, 200, background="#ffffff")
    import_font(project, str(tmp_path / "face.ttf"), "serifb")
    project.apply([{"type": "text", "name": "t", "text": "Bold", "font": "serifb", "color": "#000000"}])
    project.export(tmp_path / "x.pptx")
    xml = zipfile.ZipFile(tmp_path / "x.pptx").read("ppt/slides/slide1.xml").decode()
    run = re.search(r"<a:rPr[^>]*>", xml)[0]
    assert 'b="1"' in run and 'i="1"' in run


def test_pptx_refuses_print_and_simulation_options(tmp_path):
    project = Project(100, 100, background="#ffffff")
    with pytest.raises(VixlError, match="simulate"):
        project.export(tmp_path / "s.pptx", simulate="deuteranopia")
    assert not (tmp_path / "s.pptx").exists()
