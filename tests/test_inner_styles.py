"""Layer styles drawn inside the silhouette: inner shadow, inner glow and bevel, in every export."""

import io
import re
import zipfile

import numpy as np
import pytest

from vixl import Project
from vixl.errors import VixlError
from vixl.imports import render_svg, sanitize_svg

RED = "#c0392b"


def piece(style=None, settings=None, size=120, **layer):
    p = Project(size, size, "#dddddd")
    p.apply({"type": "shape", "shape": "rectangle", "name": "piece", "x": 20, "y": 20, "width": size - 40,
             "height": size - 40, "fill": RED, **layer})
    if style:
        p.apply({"type": "layer-style", "target": "piece", "name": style, "settings": settings or {}})
    return p


def luma(pixel):
    return 0.2126 * pixel[0] + 0.7152 * pixel[1] + 0.0722 * pixel[2]


def svg_image(p):
    svg = p.export(format="SVG")
    assert b"data:image/png" not in svg, "the styled layer stays vector, with a filter"
    root, width, height = sanitize_svg(svg, p.limits)
    return render_svg(root, width, height)


def mean_difference(a, b):
    return float(np.abs(np.asarray(a.convert("RGBA"), dtype=int) - np.asarray(b.convert("RGBA"), dtype=int)).mean())


def test_inner_shadow_darkens_the_side_the_offset_comes_from_and_stays_inside():
    plain = piece().render()
    image = piece("inner-shadow", {"dx": 6, "dy": 6, "blur": 3, "opacity": 0.8}).render()
    centre = image.getpixel((60, 60))
    assert centre == plain.getpixel((60, 60))
    assert luma(image.getpixel((22, 60))) < luma(centre) - 40  # left edge, inside
    assert luma(image.getpixel((60, 22))) < luma(centre) - 40  # top edge, inside
    assert image.getpixel((97, 60)) == centre and image.getpixel((60, 97)) == centre  # far sides untouched
    # Nothing is drawn outside the silhouette.
    for at in ((17, 60), (60, 17), (102, 60), (60, 102), (5, 5)):
        assert image.getpixel(at) == plain.getpixel(at)


def test_inner_glow_lights_every_edge_evenly():
    image = piece("inner-glow", {"color": "#ffffff", "blur": 4, "opacity": 1}).render()
    centre = luma(image.getpixel((60, 60)))
    edges = [luma(image.getpixel(at)) for at in ((21, 60), (98, 60), (60, 21), (60, 98))]
    assert min(edges) > centre + 40 and max(edges) - min(edges) < 2
    assert image.getpixel((17, 60)) == (221, 221, 221, 255)


def test_bevel_lights_the_side_facing_the_light_and_shades_the_far_side():
    image = piece("bevel", {"angle": 135, "size": 6, "opacity": 0.8}).render()
    centre = luma(image.getpixel((60, 60)))
    assert luma(image.getpixel((22, 60))) > centre + 30 and luma(image.getpixel((60, 22))) > centre + 30
    assert luma(image.getpixel((97, 60))) < centre - 30 and luma(image.getpixel((60, 97))) < centre - 30
    assert image.getpixel((17, 60)) == (221, 221, 221, 255) and image.getpixel((102, 102)) == (221, 221, 221, 255)
    # The other way round with the light below right.
    image = piece("bevel", {"angle": -45, "size": 6, "opacity": 0.8}).render()
    assert luma(image.getpixel((22, 60))) < centre - 30 and luma(image.getpixel((97, 60))) > centre + 30


def test_the_light_stays_put_when_the_layer_turns():
    # A square turned a quarter turn covers the same pixels: the lit edge is still the one facing the light.
    still = piece("bevel", {"angle": 135, "size": 6}).render()
    turned = piece("bevel", {"angle": 135, "size": 6}, rotation=90).render()
    assert mean_difference(still, turned) < 0.5
    turned = piece("inner-shadow", {"dx": 6, "dy": 0, "blur": 2}, rotation=180).render()
    assert luma(turned.getpixel((22, 60))) < luma(turned.getpixel((60, 60))) - 30
    assert turned.getpixel((97, 60)) == turned.getpixel((60, 60))


def test_a_layer_running_off_the_canvas_has_no_shadow_along_the_canvas_edge():
    p = piece("inner-shadow", {"dx": 6, "dy": 6, "blur": 3, "opacity": 0.8}, x=-30, y=-30)
    image = p.render()
    assert image.getpixel((0, 0)) == image.getpixel((30, 30))
    # A layer that ends exactly at the canvas edge does have one.
    flush = piece("inner-shadow", {"dx": 6, "dy": 6, "blur": 3, "opacity": 0.8}, x=0, y=0).render()
    assert luma(flush.getpixel((1, 40))) < luma(flush.getpixel((40, 40))) - 40


def test_inner_styles_follow_a_silhouette_with_a_hole_and_sit_above_overlays():
    p = Project(120, 120, "#dddddd")
    p.apply([
        {"type": "shape", "shape": "arc", "name": "ring", "x": 10, "y": 10, "width": 100, "height": 100,
         "fill": RED, "inner_radius": 0.5, "start_angle": 0, "end_angle": 360},
        {"type": "layer-style", "target": "ring", "name": "color-overlay", "settings": {"color": "#2a9d8f"}},
        {"type": "layer-style", "target": "ring", "name": "inner-shadow", "settings": {"dx": 4, "dy": 0, "blur": 2}},
    ])
    image = p.render()
    assert image.getpixel((60, 60)) == (221, 221, 221, 255)  # the hole stays empty
    body = image.getpixel((97, 60))
    assert body[1] > body[0], "the overlay colours the ring"
    assert luma(image.getpixel((12, 60))) < luma(body) - 30  # inside the outer edge
    assert luma(image.getpixel((87, 60))) < luma(body) - 30  # inside the hole's edge, right of the hole


@pytest.mark.parametrize("style, settings", [
    ("inner-shadow", {"dx": 5, "dy": 5, "blur": 4, "opacity": 0.7}),
    ("inner-glow", {"color": "#fff3b0", "blur": 6, "opacity": 0.9}),
    ("bevel", {"angle": 120, "size": 7, "opacity": 0.7}),
])
@pytest.mark.parametrize("layer", [{}, {"shape": "star", "rotation": 25}, {"x": -20, "y": 70}])
def test_svg_draws_the_same_pixels(style, settings, layer):
    p, plain = piece(style, settings, **layer), piece(**layer)
    image = p.render()
    assert mean_difference(image, plain.render()) > 0.5, "the style is visible"
    # No further from the SVG than the two rasterisers' antialiasing already is without the style.
    assert mean_difference(image, svg_image(p)) < mean_difference(plain.render(), svg_image(plain)) + 0.3


def test_svg_matches_with_outer_styles_and_an_overlay_together():
    p = piece("bevel", {"size": 5})
    p.apply([
        {"type": "layer-style", "target": "piece", "name": "drop-shadow", "settings": {"dx": 4, "dy": 4, "blur": 3}},
        {"type": "layer-style", "target": "piece", "name": "color-overlay", "settings": {"color": "#2a9d8f"}},
        {"type": "layer-style", "target": "piece", "name": "inner-glow", "settings": {"blur": 3}},
    ])
    assert mean_difference(p.render(), svg_image(p)) < 0.6


@pytest.mark.parametrize("style", ["inner-shadow", "inner-glow", "bevel"])
def test_pdf_embeds_the_styled_layer_as_the_renderer_draws_it(style):
    import pypdfium2

    def pdf_to_image(data, scale=1):
        document = pypdfium2.PdfDocument(io.BytesIO(data))
        try:
            return document[0].render(scale=scale).to_pil()
        finally:
            document.close()

    p = piece(style, {"opacity": 0.8})
    report = {}
    data = p.export(format="PDF", report=report)
    assert report["raster_fallbacks"]["1"] == [{"layer": "piece", "reason": "layer styles"}]
    assert mean_difference(pdf_to_image(data, scale=1), p.render().convert("RGB")) < 1.0


def slide_xml(data):
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        return archive.read("ppt/slides/slide1.xml").decode()


def test_pptx_inner_shadow_is_powerpoints_own_and_the_shape_stays_editable():
    p = piece("inner-shadow", {"color": "#102030", "dx": 3, "dy": 4, "blur": 2, "opacity": 0.5})
    report = {}
    xml = slide_xml(p.export(format="PPTX", report=report))
    assert report["raster_fallbacks"] == {}
    assert report["native_effects"] == {"1": [{"layer": "piece", "effect": "inner-shadow"}]}
    assert "LibreOffice" in report["warnings"][-1]
    from pptx import Presentation

    assert len(Presentation(io.BytesIO(p.export(format="PPTX"))).slides[0].shapes) == 1
    blur, distance, direction = map(int, re.search(r'<a:innerShdw blurRad="(\d+)" dist="(\d+)" dir="(\d+)">', xml).groups())
    # In the slide's units per pixel, read off the shape's own width (80 px).
    emu = int(re.findall(r'<a:ext cx="(\d+)"', xml)[-1]) / 80
    assert (blur, distance) == (round(4 * emu), round(5 * emu)) and abs(direction / 60000 - 53.13) < 0.01
    assert '<a:srgbClr val="102030"><a:alpha val="50000"/></a:srgbClr></a:innerShdw>' in xml
    assert "<p:pic>" not in xml


@pytest.mark.parametrize("style, layer", [("inner-glow", {}), ("bevel", {}), ("inner-shadow", {"rotation": 30}),
                                          ("inner-shadow", {"stroke": "#000000", "stroke_width": 3})])
def test_pptx_falls_back_to_a_picture_of_the_render_for_the_rest(style, layer):
    p = piece(style, **layer)
    report = {}
    xml = slide_xml(p.export(format="PPTX", report=report))
    assert report["raster_fallbacks"]["1"] == [{"layer": "piece", "reason": "layer styles"}]
    assert "<p:pic>" in xml and "innerShdw" not in xml


def test_settings_are_validated_and_forgiving_names_are_normalized():
    p = piece()
    with pytest.raises(VixlError, match="Invalid bevel settings"):
        p.apply({"type": "layer-style", "target": "piece", "name": "bevel", "settings": {"dx": 3}})
    with pytest.raises(VixlError):
        p.apply({"type": "layer-style", "target": "piece", "name": "bevel", "settings": {"highlight": "not-a-colour"}})
    result = p.apply({"type": "layer-style", "target": "piece", "name": "Inner Shadow",
                      "settings": {"offset_x": 3, "radius": 2, "opacity": "50%"}})
    assert p.layer("piece")["styles"]["inner-shadow"] == {"dx": 3, "blur": 2, "opacity": 0.5}
    assert result.get("normalized")
    p.apply({"type": "layer-style", "target": "piece", "name": "bevel", "settings": {"depth": 5, "enabled": False}})
    assert p.layer("piece")["styles"]["bevel"] == {"size": 5, "enabled": False}
    before = piece("inner-shadow", {"dx": 3, "blur": 2, "opacity": 0.5}).render()
    assert p.render().tobytes() == before.tobytes(), "a disabled bevel draws nothing"
    p.apply({"type": "layer-style", "target": "piece", "name": "inner-shadow", "remove": True})
    assert p.render().tobytes() == piece().render().tobytes()


def test_a_reduced_preview_scales_the_inner_styles(tmp_path):
    p = piece("bevel", {"size": 8, "opacity": 0.8}, size=240)
    full = p.render()
    small = p.export(format="PNG", scale=0.5)
    from PIL import Image

    with Image.open(io.BytesIO(small)) as half:
        assert mean_difference(half.convert("RGBA"), full.resize(half.size, Image.Resampling.BOX)) < 1.5


def test_cut_paper_edge_light_adds_a_bevel_and_clear_removes_it():
    p = piece()
    p.apply({"type": "cut-paper", "targets": ["piece"], "thickness": 3, "edge_light": {"angle": 90}})
    assert p.layer("piece")["styles"]["bevel"] == {"size": 3, "opacity": 0.25, "angle": 90}
    lit = p.render()
    assert luma(lit.getpixel((60, 22))) > luma(lit.getpixel((60, 97)))
    p.apply({"type": "cut-paper", "targets": ["piece"], "thickness": 3})
    assert "bevel" not in p.layer("piece")["styles"]
    p.apply({"type": "cut-paper", "targets": ["piece"], "edge_light": {}})
    p.apply({"type": "cut-paper", "targets": ["piece"], "clear": True})
    assert "bevel" not in p.layer("piece").get("styles", {}) and "cut_paper" not in p.layer("piece")
