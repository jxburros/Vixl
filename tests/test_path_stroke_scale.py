"""``render --scale N`` widens a path's stroke N times, not N * N: the scaled copy scales the path's
``path_view`` with its box, since native path strokes are measured in view units."""

import io

import numpy as np
from PIL import Image
import pytest
import resvg_py

from vixl import Project
from vixl.proxy import scaled_project

SQUARE = "M 50 50 L 250 50 L 250 150 L 50 150 Z"


def document(**extra):
    p = Project(300, 200, "white")
    p.apply({"type": "shape", "shape": "path", "name": "p", "path": SQUARE, "fill": "#d4241c", "stroke": "#000000",
             "stroke_width": 10, **extra})
    return p


def left_stroke(image, scale):
    """Dark pixels on the row through the middle of the square, left of its centre."""
    gray = np.asarray(image.convert("L"))
    return int((gray[100 * scale, :150 * scale] < 60).sum())


def png(project, scale):
    return Image.open(io.BytesIO(project.export(format="PNG", scale=scale)))


@pytest.mark.parametrize("extra", [
    {},
    {"path": "M 25 25 L 125 25 L 125 75 L 25 75 Z", "path_view": [125, 75], "width": 250, "height": 150},
    {"dash": [400, 1]},  # a styled stroke, drawn in box pixels; its dash lengths scale too
    {"stroke_width": 4, "strokes": [{"color": "#000000", "width": 10}]},
], ids=["native", "path-view", "dashed", "extra-strokes"])
def test_scaled_render_widens_path_stroke_by_the_scale(extra):
    p = document(**extra)
    one, three = left_stroke(png(p, 1), 1), left_stroke(png(p, 3), 3)
    assert abs(one - (20 if "path_view" in extra else 10)) <= 1
    assert abs(three - 3 * one) <= 2, (one, three)


def test_scaled_svg_and_raster_strokes_match():
    p = document()
    svg = Image.open(io.BytesIO(resvg_py.svg_to_bytes(svg_string=p.export(format="SVG", scale=3).decode())))
    assert abs(left_stroke(svg, 3) - left_stroke(png(p, 3), 3)) <= 2
    assert abs(left_stroke(svg, 3) - 30) <= 2


def test_scaled_copy_scales_path_view_and_leaves_source_alone():
    p = document()
    copy = scaled_project(p, 3)
    layer, source = copy.state["layers"][-1], p.state["layers"][-1]
    assert layer["path_view"] == [750, 450] and layer["stroke_width"] == 30
    assert layer["path"].startswith("M150 150")
    assert source["path"] == SQUARE and source["path_view"] == [250, 150] and source["stroke_width"] == 10
