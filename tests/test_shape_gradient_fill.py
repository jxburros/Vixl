"""Gradient fills on shapes (``fill_gradient``): raster, SVG, PDF and PowerPoint draw them, ``fill`` keeps a flat
colour, in-place edits and lenient input behave as documented, and SVG round-trips them."""

import io
import re
import xml.etree.ElementTree as ET
import zipfile

import numpy as np
import pytest

from vixl import Project
from vixl.errors import VixlError
from vixl.imports import import_document, render_svg, sanitize_svg

pypdf = pytest.importorskip("pypdf")

RED_BLUE = {"start": "#ff0000", "end": "#0000ff", "direction": "horizontal"}


def rgb(image, x, y):
    return image.getpixel((x, y))[:3]


def reddish(pixel):
    return pixel[0] > pixel[2] + 60 and pixel[1] < 60


def bluish(pixel):
    return pixel[2] > pixel[0] + 60 and pixel[1] < 60


def shapes():
    p = Project(400, 140, "#ffffff")
    p.apply([
        {"type": "shape", "shape": "rectangle", "name": "box", "x": 10, "y": 10, "width": 80, "height": 50,
         "fill_gradient": RED_BLUE},
        {"type": "shape", "shape": "ellipse", "name": "oval", "x": 110, "y": 10, "width": 80, "height": 50,
         "fill_gradient": RED_BLUE},
        {"type": "shape", "shape": "rounded-rectangle", "name": "card", "x": 210, "y": 10, "width": 80, "height": 50,
         "radius": 12, "fill_gradient": RED_BLUE},
        {"type": "shape", "shape": "path", "name": "blob", "x": 310, "y": 10, "path": "M0 0 L80 0 L80 50 L0 50 Z",
         "fill_gradient": RED_BLUE},
        {"type": "shape", "shape": "star", "name": "star", "x": 10, "y": 70, "width": 80, "height": 60,
         "fill_gradient": RED_BLUE},
        {"type": "shape", "shape": "rectangle", "name": "framed", "x": 110, "y": 70, "width": 80, "height": 60,
         "fill_gradient": RED_BLUE, "stroke": "#00ff00", "stroke_width": 6},
        {"type": "shape", "shape": "ellipse", "name": "ring", "x": 210, "y": 70, "width": 80, "height": 60,
         "fill_gradient": RED_BLUE, "stroke": "#00ff00", "stroke_width": 6, "dash": "dashed"},
    ])
    return p


@pytest.fixture(scope="module")
def drawn():
    p = shapes()
    return p, p.render()


@pytest.mark.parametrize("name", ["box", "oval", "card", "blob", "star"])
def test_png_runs_the_gradient_across_each_shape(drawn, name):
    p, image = drawn
    layer = p.layer(name)
    y = layer["y"] + layer["height"] // 2
    inset = 26 if name == "star" else 12  # inside the star's body, between its points
    left, right = rgb(image, layer["x"] + inset, y), rgb(image, layer["x"] + layer["width"] - inset, y)
    assert reddish(left) and bluish(right), (left, right)
    assert layer["fill"] == "#800080"  # the flat colour checks read: the gradient's middle


def test_png_keeps_the_stroke_its_own_colour(drawn):
    p, image = drawn
    framed = p.layer("framed")
    assert rgb(image, framed["x"] + 40, framed["y"] + 2) == (0, 255, 0)  # the inside stroke along the top
    assert rgb(image, framed["x"] + 2, framed["y"] + 30) == (0, 255, 0)
    assert reddish(rgb(image, framed["x"] + 12, framed["y"] + 30))
    assert bluish(rgb(image, framed["x"] + 68, framed["y"] + 30))
    ring = p.layer("ring")
    middle = ring["y"] + ring["height"] // 2
    assert reddish(rgb(image, ring["x"] + 14, middle)) and bluish(rgb(image, ring["x"] + 66, middle))


def test_vertical_and_radial_directions(drawn):
    p = Project(200, 100, "#ffffff")
    p.apply([
        {"type": "shape", "shape": "rectangle", "name": "v", "x": 0, "y": 0, "width": 100, "height": 100,
         "fill_gradient": {"start": "#ff0000", "end": "#0000ff"}},
        {"type": "shape", "shape": "ellipse", "name": "r", "x": 100, "y": 0, "width": 100, "height": 100,
         "fill_gradient": {"start": "#ffffff", "end": "#000000", "direction": "radial"}},
    ])
    image = p.render()
    assert reddish(rgb(image, 50, 4)) and bluish(rgb(image, 50, 95))
    assert rgb(image, 150, 50)[0] > 240 and rgb(image, 150, 94)[0] < 60


def test_open_path_with_a_stroke_fills_only_when_asked():
    p = Project(200, 120, "#000000")
    p.apply({"type": "shape", "name": "hook", "shape": "path", "path": "M10 100 L190 100 L100 20", "x": 0, "y": 0,
             "width": 200, "height": 120, "stroke": "#ffffff", "stroke_width": 2, "fill_gradient": RED_BLUE})
    image = p.render()
    assert reddish(rgb(image, 40, 90)) and bluish(rgb(image, 160, 90))  # an explicit gradient fills, like a fill


def test_an_explicit_fill_string_stays_with_the_gradient():
    p = Project(100, 100)
    p.apply({"type": "shape", "shape": "rectangle", "name": "s", "width": 50, "height": 50, "fill": "#123456",
             "fill_gradient": RED_BLUE})
    assert p.layer("s")["fill"] == "#123456" and p.layer("s")["fill_gradient"] == RED_BLUE
    assert reddish(rgb(p.render(), 4, 25))


def test_in_place_edits_set_replace_and_remove_the_gradient():
    p = Project(100, 60, "#ffffff")
    p.apply({"type": "shape", "shape": "rectangle", "name": "s", "width": 100, "height": 60, "fill": "#00ff00"})
    first = p.render()
    p.apply({"type": "shape", "target": "s", "fill_gradient": RED_BLUE})
    assert p.layer("s")["fill"] == "#800080"
    image = p.render()
    assert image.tobytes() != first.tobytes()  # the cached layer image follows the new field
    assert reddish(rgb(image, 4, 30)) and bluish(rgb(image, 95, 30))
    p.apply({"type": "shape", "target": "s", "fill_gradient": {**RED_BLUE, "end": "#ffff00"}})
    assert rgb(p.render(), 95, 30)[1] > 200
    p.apply({"type": "shape", "target": "s", "fill": "#00ff00"})
    assert "fill_gradient" not in p.layer("s") and rgb(p.render(), 95, 30) == (0, 255, 0)
    p.apply({"type": "shape", "target": "s", "fill_gradient": RED_BLUE})
    p.apply({"type": "shape", "target": "s", "fill_gradient": None})
    assert "fill_gradient" not in p.layer("s") and p.layer("s")["fill"] == "#800080"
    p.apply({"type": "shape", "target": "s", "fill_gradient": RED_BLUE})
    result = p.apply({"type": "shape", "target": "s", "fill_gradient": "none"})
    assert "fill_gradient" not in p.layer("s") and any("fill_gradient 'none'" in n for n in result["normalized"])
    p.apply({"type": "shape", "target": "s", "fill_gradient": RED_BLUE})
    p.apply({"type": "shape", "target": "s", "stroke": "#000000", "stroke_width": 2})
    assert p.layer("s")["fill_gradient"] == RED_BLUE  # other edits leave the gradient alone


def test_cli_takes_a_json_fill_gradient():
    from vixl.design_cli import compile_design

    op = compile_design("shape", ["rectangle", "--fill-gradient", '{"start":"#ff0000","end":"#0000ff"}'])
    assert op["fill_gradient"] == {"start": "#ff0000", "end": "#0000ff"}


def test_a_fill_object_normalizes_to_fill_gradient():
    p = Project(100, 100)
    result = p.apply([
        {"type": "shape", "shape": "rectangle", "name": "a", "width": 50, "height": 50,
         "fill": {"start": "#ff0000", "end": "#0000ff"}},
        {"type": "shape", "shape": "rectangle", "name": "b", "width": 50, "height": 50,
         "fill": {"gradient": {"stops": [{"offset": 0, "color": "#ff0000"}, {"offset": 1, "color": "#0000ff"}]}}},
        {"type": "shape", "shape": "ellipse", "name": "c", "width": 50, "height": 50,
         "fill": {"colors": ["#ff0000", "#00ff00", "#0000ff"], "direction": "horizontal"}},
        {"type": "shape", "shape": "ellipse", "name": "d", "width": 50, "height": 50,
         "fillGradient": {"from": "#ff0000", "to": "#0000ff"}},
    ])
    assert p.layer("a")["fill_gradient"] == {"start": "#ff0000", "end": "#0000ff"}
    assert p.layer("b")["fill_gradient"]["stops"][1]["color"] == "#0000ff"
    assert [s["offset"] for s in p.layer("c")["fill_gradient"]["stops"]] == [0, 0.5, 1]
    assert p.layer("c")["fill"] == "#00ff00"
    assert p.layer("d")["fill_gradient"] == {"start": "#ff0000", "end": "#0000ff"}
    notes = " ".join(result["normalized"])
    assert "→ 'fill_gradient'" in notes and "fill_gradient.colors" in notes and "fill_gradient.from" in notes


@pytest.mark.parametrize("gradient", [
    {"start": "#ff0000", "end": "#0000ff", "shade": 2},
    {"stops": [{"offset": 0.5, "color": "#ff0000"}, {"offset": 0.2, "color": "#0000ff"}]},
    {"start": "not-a-colour", "end": "#0000ff"},
    {"direction": "diagonal", "start": "#000000"},
    {"direction": "horizontal"},
])
def test_invalid_gradients_are_refused(gradient):
    p = Project(100, 100)
    with pytest.raises(VixlError):
        p.apply({"type": "shape", "shape": "rectangle", "name": "s", "width": 50, "height": 50,
                 "fill_gradient": gradient})
    assert not p.state["layers"]


def test_swatches_and_variables_in_stops_resolve_and_follow_their_definitions():
    p = Project(100, 60, "#ffffff")
    p.apply([
        {"type": "swatch", "name": "brand", "color": "#ff0000"},
        {"type": "variable", "name": "tone", "value": "#0000ff"},
        {"type": "shape", "shape": "rectangle", "name": "s", "width": 100, "height": 60,
         "fill_gradient": {"start": "@brand", "end": "${tone}", "direction": "horizontal"}},
    ])
    assert p.layer("s")["fill"] == "#800080"
    image = p.render()
    assert reddish(rgb(image, 4, 30)) and bluish(rgb(image, 95, 30))
    p.apply({"type": "swatch", "name": "brand", "color": "#00ff00"})
    assert rgb(p.render(), 4, 30)[1] > 200
    svg = p.export(format="SVG").decode()
    assert "rgb(0,255,0)" in svg and "rgb(0,0,255)" in svg


def test_svg_fills_the_shape_with_a_gradient(drawn):
    p, image = drawn
    data = p.export(format="SVG")
    root = ET.fromstring(data)
    ids = {node.get("id") for node in root.iter() if node.tag.endswith("Gradient")}
    painted = [node for node in root.iter() if (node.get("fill") or "").startswith("url(#vixl-gradient")]
    assert len(painted) >= 7 and {re.search(r"#([^)]+)", n.get("fill"))[1] for n in painted} <= ids
    assert 'stroke="rgb(0,255,0)"' in data.decode() or "rgb(0,255,0)" in data.decode()
    drawn_svg = render_svg(*sanitize_svg(data, p.limits))
    for name in ("box", "oval", "card", "blob"):
        layer = p.layer(name)
        y = layer["y"] + layer["height"] // 2
        assert reddish(rgb(drawn_svg, layer["x"] + 12, y)) and bluish(rgb(drawn_svg, layer["x"] + 68, y)), name
    difference = np.abs(np.asarray(drawn_svg.convert("RGB"), int) - np.asarray(image.convert("RGB"), int))
    assert difference.mean() < 2


@pytest.mark.parametrize("gradient", [
    {"start": "#ff0000", "end": "#0000ff", "direction": "angled", "angle": 30},
    {"stops": [{"offset": 0, "color": "#ffffff"}, {"offset": 0.6, "color": "#ff0000"}, {"offset": 1, "color": "#000000"}],
     "direction": "radial", "center": [0.3, 0.4]},
])
def test_svg_matches_png_for_scaled_paths_and_turned_shapes(gradient):
    p = Project(240, 160, "#ffffff")
    p.apply([
        {"type": "shape", "shape": "path", "name": "scaled", "x": 10, "y": 10, "width": 100, "height": 120,
         "path": "M0 0 L10 0 L10 12 L0 12 Z", "path_view": [10, 12], "fill_gradient": gradient},
        {"type": "shape", "shape": "rounded-rectangle", "name": "turned", "x": 130, "y": 30, "width": 90,
         "height": 90, "radius": 10, "fill_gradient": gradient, "rotation": 20},
    ])
    image = np.asarray(p.render().convert("RGB"), int)
    svg = np.asarray(render_svg(*sanitize_svg(p.export(format="SVG"), p.limits)).convert("RGB"), int)
    assert np.abs(svg - image).mean() < 2.5


def test_own_svg_round_trips_a_gradient_fill(drawn):
    p, _ = drawn
    restored = Project(10, 10)
    result = import_document(restored, p.export(format="SVG"), "svg")
    assert result["mode"] == "document" and restored.state == p.state


def test_foreign_svg_gradient_shapes_import_as_fill_gradient():
    svg = b"""<svg xmlns="http://www.w3.org/2000/svg" width="200" height="100">
      <defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="0">
        <stop offset="0" stop-color="#ff0000"/><stop offset="1" stop-color="#0000ff" stop-opacity="0.5"/>
      </linearGradient></defs>
      <rect x="10" y="10" width="80" height="60" rx="10" fill="url(#g)"/>
      <path d="M110 10 L190 10 L190 70 L110 70 Z" fill="url(#g)" stroke="#00ff00" stroke-width="4"/>
    </svg>"""
    p = Project(200, 100, "#ffffff")
    result = import_document(p, svg, "svg", svg_mode="editable")
    layers = [layer for layer in p.state["layers"] if layer["type"] == "shape"]
    assert len(layers) == 2 and all(layer.get("fill_gradient") and not layer.get("styles") for layer in layers)
    assert not result.get("warnings")
    image = p.render()
    assert reddish(rgb(image, 16, 40)) and rgb(image, 84, 40)[2] > 150
    assert rgb(image, 120, 40)[0] > 180 and rgb(image, 110, 40)[1] > 200  # the stroke stays green


def test_pptx_writes_a_gradient_fill(drawn):
    p, _ = drawn
    xml = zipfile.ZipFile(io.BytesIO(p.export(format="PPTX"))).read("ppt/slides/slide1.xml").decode()
    assert xml.count("<a:gradFill") >= 7 and "<p:pic>" not in xml
    framed = xml[xml.index('name="framed"'):]
    assert '<a:ln w=' in framed.split("</p:sp>")[0] and "00FF00" in framed.split("</p:sp>")[0]


def test_pdf_draws_gradient_fills_as_shadings(drawn):
    p, image = drawn
    report = {}
    data = p.export(format="PDF", report=report)
    assert not report.get("raster_fallbacks")
    content = pypdf.PdfReader(io.BytesIO(data)).pages[0].get_contents().get_data().decode("latin-1")
    assert content.count(" sh") >= 7 and "W n" in content
    pdfium = pytest.importorskip("pypdfium2")
    page = pdfium.PdfDocument(data)[0]
    size = (p.state["canvas"]["width"], p.state["canvas"]["height"])
    shown = page.render(scale=size[0] / page.get_width()).to_pil().convert("RGB").resize(size)
    assert np.abs(np.asarray(shown, int) - np.asarray(image.convert("RGB"), int)).mean() < 2


def test_pdf_draws_translucent_gradient_fills_as_images():
    p = Project(100, 60, "#ffffff")
    p.apply({"type": "shape", "shape": "ellipse", "name": "fade", "width": 100, "height": 60,
             "fill_gradient": {"start": "#ff0000", "end": "#ff000000"}})
    report = {}
    data = p.export(format="PDF", report=report)
    assert data.startswith(b"%PDF") and any(item["layer"] == "fade" for page in report["raster_fallbacks"].values() for item in page)


def test_design_styles_count_gradient_fills_as_gradients():
    from vixl.styles import _gradient_layers

    p = shapes()

    class Facts:
        layers = p.state["layers"]

    assert len(_gradient_layers(Facts)) == 7


def test_a_mono_logo_recolours_the_gradient_too():
    from vixl.plugins.brand_kit.logo_package import recolor

    p = shapes()
    recolor(p, "#000000")
    for layer in p.state["layers"]:
        gradient = layer["fill_gradient"]
        assert gradient["start"] == gradient["end"] == "#000000"
