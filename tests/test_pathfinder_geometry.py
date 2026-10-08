"""Pathfinder (boolean) layers export as real compound-path geometry: SVG without masks, vector PDF and PPTX."""

import io
import re
import xml.etree.ElementTree as ET
import zipfile

import numpy as np
from PIL import Image
import pytest
import resvg_py

from vixl import Project, VixlError
from vixl.booleans import MAX_SEGMENTS, Unsupported, combine_outlines
from vixl.pathfinder_geometry import MODES, outline_commands, path_data, pathfinder_commands, placed, shape_contours

FLAME = "M55 0 C90 50 110 100 55 200 C0 100 20 50 55 0 Z"
WAVE = "M0 30 C45 0 90 0 135 30 C180 60 225 60 270 30 L270 60 L0 60 Z"


def logo_mark(mode="subtract", background="transparent"):
    """The T04 mark: a disc with a flame and a wave cut out of it."""
    p = Project(512, 512, background)
    p.apply([
        {"type": "shape", "shape": "ellipse", "name": "disc", "width": 480, "height": 480, "x": 16, "y": 16, "fill": "#14263b"},
        {"type": "shape", "shape": "path", "name": "flame", "x": 200, "y": 120, "width": 110, "height": 200,
         "fill": "#f2a541", "path": FLAME},
        {"type": "shape", "shape": "path", "name": "wave", "x": 120, "y": 340, "width": 270, "height": 60,
         "fill": "#f2a541", "path": WAVE},
        {"type": "pathfinder", "name": "mark", "targets": ["disc", "flame", "wave"], "mode": mode},
    ])
    return p


def svg_alpha(data, size=None):
    image = Image.open(io.BytesIO(resvg_py.svg_to_bytes(svg_string=data.decode()))).convert("RGBA")
    return np.asarray(image)[:, :, 3].astype(int)


def render_alpha(project):
    return np.asarray(project.render())[:, :, 3].astype(int)


def agreement(a, b):
    """Fraction of pixels (either covered) on which two alpha images agree about being covered."""
    a, b = a > 127, b > 127
    return (a & b).sum() / max(1, (a | b).sum())


def svg_tree(project, **options):
    return ET.fromstring(project.export(format="SVG", **options))


def test_subtract_is_one_compound_path_without_masks_and_matches_the_render():
    p = logo_mark()
    data = p.export(format="SVG", svg_policy="strict")  # strict accepts it: no raster fallback, no mask to fake a boolean
    text = data.decode()
    assert "<mask" not in text and "mask=" not in text and "mask-type" not in text and "<image" not in text
    paths = ET.fromstring(data).findall(".//{*}path")
    assert len(paths) == 1 and paths[0].get("fill-rule") == "evenodd"
    d = paths[0].get("d")
    assert d.count("M") == 3 and d.count("Z") == 3, "the disc and the two holes are subpaths of one path"
    assert d.count("C") >= 8, "curves stay curves"
    assert agreement(svg_alpha(data), render_alpha(p)) > 0.995
    # The holes are real: the flame and the wave are transparent, the ring around them is solid.
    alpha = svg_alpha(data)
    assert alpha[200, 255] == 0 and alpha[370, 250] == 0 and alpha[100, 256] == 255 and alpha[30, 30] == 0
    # Winding is consistent, so the nonzero fill draws the same shape (renderers differ in their default).
    assert np.array_equal(alpha, svg_alpha(data.replace(b'fill-rule="evenodd"', b'fill-rule="nonzero"')))


@pytest.mark.parametrize("mode", ["union", "subtract", "intersect"])
def test_every_mode_matches_the_pixels_for_overlapping_rotated_shapes(mode):
    p = Project(400, 400, "transparent")
    p.apply([
        {"type": "shape", "shape": "ellipse", "name": "a", "width": 180, "height": 150, "x": 40, "y": 60, "fill": "purple"},
        {"type": "shape", "shape": "rectangle", "name": "b", "width": 140, "height": 90, "x": 120, "y": 90, "fill": "purple"},
        {"type": "rotate", "target": "b", "value": 33},
        {"type": "shape", "shape": "star", "name": "c", "width": 150, "height": 150, "x": 150, "y": 150, "fill": "purple",
         "sides": 5},
        {"type": "shape", "shape": "rounded-rectangle", "name": "d", "width": 140, "height": 80, "x": 100, "y": 100,
         "fill": "purple", "radius": 18},
        {"type": "pathfinder", "name": "pf", "targets": ["a", "b", "c", "d"] if mode != "intersect" else ["a", "b", "d"],
         "mode": mode},
    ])
    data = p.export(format="SVG", svg_policy="strict")
    assert b"<mask" not in data and b"<image" not in data
    assert (render_alpha(p) > 127).sum() > 4000, "a region big enough to compare"
    assert agreement(svg_alpha(data), render_alpha(p)) > 0.99


def test_resized_nested_flipped_pathfinders_stay_geometry():
    p = Project(500, 400, "transparent")
    p.apply([
        {"type": "shape", "shape": "ellipse", "name": "ring", "width": 160, "height": 160, "x": 40, "y": 40, "fill": "navy"},
        {"type": "shape", "shape": "ellipse", "name": "core", "width": 90, "height": 90, "x": 75, "y": 75, "fill": "navy"},
        {"type": "pathfinder", "name": "donut", "targets": ["ring", "core"], "mode": "subtract"},
        {"type": "shape", "shape": "rectangle", "name": "bar", "width": 260, "height": 30, "x": 20, "y": 110, "fill": "navy"},
        {"type": "pathfinder", "name": "cut", "targets": ["donut", "bar"], "mode": "subtract"},
        {"type": "resize", "target": "cut", "width": 300, "height": 240},
        {"type": "rotate", "target": "cut", "value": 20},
        {"type": "flip", "target": "cut", "direction": "horizontal"},
        {"type": "move", "target": "cut", "x": 100, "y": 60},
    ])
    data = p.export(format="SVG", svg_policy="strict")
    assert b"<mask" not in data and b"<image" not in data
    assert agreement(svg_alpha(data), render_alpha(p)) > 0.97  # the render resamples a turned, stretched layer


def test_a_path_is_cut_off_at_its_box_like_the_render():
    p = Project(260, 160, "transparent")
    p.apply([
        {"type": "shape", "shape": "rectangle", "name": "base", "width": 200, "height": 100, "x": 20, "y": 20, "fill": "navy"},
        # The path's curve swells past its 80 x 100 box; the render (and SVG) clip it there.
        {"type": "shape", "shape": "path", "name": "bulge", "width": 80, "height": 100, "x": 100, "y": 20, "fill": "navy",
         "path": "M0 0 C140 0 140 100 0 100 Z"},
        {"type": "pathfinder", "name": "pf", "targets": ["base", "bulge"], "mode": "subtract"},
    ])
    data = p.export(format="SVG", svg_policy="strict")
    assert agreement(svg_alpha(data), render_alpha(p)) > 0.99
    assert svg_alpha(data)[70, 170] == 0 and svg_alpha(data)[70, 205] == 255


def test_coincident_tangent_and_touching_outlines_combine_exactly():
    """Shared edges, equal shapes and tangent circles are where boolean geometry usually breaks."""
    def alpha(contours, size=220):
        d = path_data(outline_commands(contours))
        svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}"><path d="{d}" fill-rule="evenodd"/></svg>'
        return svg_alpha(svg.encode()) > 127 if d else np.zeros((size, size), bool)

    def op(shape, x, y, w, h, rotation=0, **extra):
        item = {"type": "shape", "shape": shape, "width": w, "height": h, "rotation": rotation, **extra}
        return placed(shape_contours(item), item, x, y)

    cases = {
        "abutting": [op("rectangle", 20, 20, 100, 100), op("rectangle", 120, 20, 60, 100)],
        "shared edge": [op("rectangle", 20, 20, 100, 100), op("rectangle", 20, 20, 50, 100)],
        "identical": [op("ellipse", 20, 20, 100, 70), op("ellipse", 20, 20, 100, 70)],
        "circle in square": [op("rectangle", 20, 20, 100, 100), op("ellipse", 20, 20, 100, 100)],
        "tangent circles": [op("ellipse", 20, 60, 80, 80), op("ellipse", 100, 60, 80, 80)],
        "internally tangent": [op("ellipse", 20, 20, 100, 100), op("ellipse", 20, 45, 50, 50)],
        "concentric": [op("ellipse", 20, 20, 120, 120), op("ellipse", 50, 50, 60, 60)],
        "diamond in square": [op("rectangle", 20, 20, 100, 100), op("diamond", 20, 20, 100, 100)],
        "lens": [op("ellipse", 20, 40, 100, 100), op("ellipse", 80, 40, 100, 100)],
        "vertex on rim": [op("ellipse", 20, 20, 140, 140), op("triangle", 20, 20, 140, 140)],
    }
    for name, inputs in cases.items():
        masks = [alpha(c) for c in inputs]
        expected = {"union": masks[0] | masks[1], "intersect": masks[0] & masks[1], "subtract": masks[0] & ~masks[1]}
        for mode, want in expected.items():
            got = alpha(combine_outlines(inputs, MODES[mode]))
            assert (got != want).sum() <= 30, f"{name} {mode}"  # only anti-aliased edge pixels may differ
        back = alpha(combine_outlines(inputs[::-1], MODES["subtract"]))
        assert (back != (masks[1] & ~masks[0])).sum() <= 30, f"{name} reversed subtract"


def test_result_keeps_curves_whole_and_merges_collinear_edges():
    p = logo_mark()
    commands = pathfinder_commands(p.layer("mark"), p.state)
    assert [c for c, _ in commands].count("C") == 4 + 2 + 2  # the disc's four arcs, the flame's two, the wave's two
    assert [c for c, _ in commands].count("L") == 3
    # Two abutting rectangles unite into one four-sided outline, not six pieces.
    q = Project(200, 100, "transparent")
    q.apply([{"type": "shape", "shape": "rectangle", "name": "a", "width": 100, "height": 60, "x": 0, "y": 0},
             {"type": "shape", "shape": "rectangle", "name": "b", "width": 60, "height": 60, "x": 100, "y": 0},
             {"type": "pathfinder", "name": "u", "targets": ["a", "b"], "mode": "union"}])
    united = pathfinder_commands(q.layer("u"), q.state)
    assert [c for c, _ in united] == ["M", "L", "L", "L", "Z"]


def test_a_cubic_that_loops_through_itself_is_combined():
    p = Project(300, 300, "transparent")
    p.apply([{"type": "shape", "shape": "rectangle", "name": "bg", "width": 240, "height": 240, "x": 20, "y": 20, "fill": "navy"},
             {"type": "shape", "shape": "path", "name": "loop", "width": 200, "height": 200, "x": 40, "y": 40, "fill": "navy",
              "path": "M20 180 C260 -40 -60 -40 180 180 Z"},
             {"type": "pathfinder", "name": "pf", "targets": ["bg", "loop"], "mode": "subtract"}])
    data = p.export(format="SVG", svg_policy="strict")
    assert agreement(svg_alpha(data), render_alpha(p)) > 0.99


def test_empty_result_exports_nothing_and_does_not_fail():
    p = Project(100, 100, "transparent")
    p.apply([{"type": "shape", "shape": "rectangle", "name": "a", "width": 50, "height": 50, "x": 10, "y": 10},
             {"type": "shape", "shape": "rectangle", "name": "b", "width": 50, "height": 50, "x": 10, "y": 10},
             {"type": "pathfinder", "name": "pf", "targets": ["a", "b"], "mode": "subtract"}])
    data = p.export(format="SVG", svg_policy="strict")
    assert not ET.fromstring(data).findall(".//{*}path") and svg_alpha(data).max() == 0


# what cannot be geometry


def stroked_boolean():
    p = Project(200, 200, "white")
    p.apply([{"type": "shape", "shape": "ellipse", "name": "a", "width": 120, "height": 120, "x": 20, "y": 20,
              "fill": "navy", "stroke": "red", "stroke_width": 6},
             {"type": "shape", "shape": "rectangle", "name": "b", "width": 80, "height": 80, "x": 70, "y": 70, "fill": "gold"},
             {"type": "pathfinder", "name": "pf", "targets": ["a", "b"], "mode": "subtract"}])
    return p


def test_strict_svg_rejects_a_boolean_it_cannot_make_geometry_instead_of_faking_it_with_masks():
    p = stroked_boolean()
    with pytest.raises(VixlError) as caught:
        p.export(format="SVG", svg_policy="strict")
    assert caught.value.code == "svg_raster_required"
    fallback = caught.value.details["fallbacks"][0]
    assert fallback["layer"] == "pf" and "operand has a stroke" in fallback["reason"]
    # The appearance policy keeps the exact look as an image (never as masks) and lists it.
    data = p.export(format="SVG")
    assert b"<mask" not in data and len(ET.fromstring(data).findall(".//{*}image")) == 1
    assert b"operand has a stroke" in data


def test_pdf_and_pptx_list_the_same_reason_when_they_draw_an_image():
    p = stroked_boolean()
    for fmt in ("PDF", "PPTX"):
        report = {}
        p.export(format=fmt, report=report)
        assert report["raster_fallbacks"]["1"] == [
            {"layer": "pf", "reason": "pathfinder: an operand has a stroke (draw strokes as their own layers)"}]


def test_too_many_segments_are_refused_not_approximated():
    big = [[((x, 0.0), (x + 1.0, 0.0))] for x in range(MAX_SEGMENTS + 1)]
    with pytest.raises(Unsupported, match="segments"):
        combine_outlines([big], MODES["union"])


def test_pdf_draws_the_boolean_as_one_vector_path():
    pypdf = pytest.importorskip("pypdf")
    p = logo_mark(background="white")
    report = {}
    data = p.export(format="PDF", report=report)
    assert report["raster_fallbacks"] == {} and report["content"] == "vector"
    page = pypdf.PdfReader(io.BytesIO(data)).pages[0]
    content = page.get_contents().get_data().decode("latin-1")
    assert content.count("f*") == 1 and content.count(" c\n") == 8 and not list(page.images)
    pdfium = pytest.importorskip("pypdfium2")
    bitmap = pdfium.PdfDocument(data)[0].render(scale=1).to_pil().convert("RGB")
    drawn = np.asarray(bitmap).astype(int)
    reference = np.asarray(p.render().convert("RGB")).astype(int)
    assert drawn.shape == reference.shape
    assert (np.abs(drawn - reference).max(axis=2) > 96).mean() < 0.005
    assert tuple(drawn[200, 255]) == (255, 255, 255), "the flame is a hole in the PDF too"


def test_pptx_draws_the_boolean_as_one_freeform_with_holes():
    pptx = pytest.importorskip("pptx")
    p = logo_mark(background="white")
    report = {}
    data = p.export(format="PPTX", report=report)
    assert report["raster_fallbacks"] == {}
    deck = pptx.Presentation(io.BytesIO(data))
    shapes = [s for s in deck.slides[0].shapes if s.name == "mark"]
    assert len(shapes) == 1 and shapes[0].shape_type == pptx.enum.shapes.MSO_SHAPE_TYPE.FREEFORM
    xml = zipfile.ZipFile(io.BytesIO(data)).read("ppt/slides/slide1.xml").decode()
    assert xml.count("<a:path ") == 1 and xml.count("<a:moveTo>") == 3 and xml.count("<a:close/>") == 3
    assert "<p:pic>" not in xml and not re.search(r"ppt/media/", " ".join(zipfile.ZipFile(io.BytesIO(data)).namelist()))
