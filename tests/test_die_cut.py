"""die-cut (#444 item 4): a sticker cut line around the targets' ink, offset by a distance."""

import pytest

from vixl import Project
from vixl.commands import compile_command
from vixl.errors import VixlError
from vixl.geometry import default_fill
from vixl.schema import validate_operation
from vixl.targets import mode


def sticker():
    p = Project(400, 300, "#ffffff")
    p.apply([
        {"type": "shape", "shape": "ellipse", "name": "badge", "x": 100, "y": 80, "width": 120, "height": 120,
         "fill": "#e63946"},
        {"type": "shape", "shape": "rectangle", "name": "tab", "x": 200, "y": 120, "width": 80, "height": 40,
         "fill": "#1d3557"},
        {"type": "shape", "shape": "rectangle", "name": "other", "x": 10, "y": 10, "width": 30, "height": 30,
         "fill": "#000000"},
    ])
    return p


def test_cut_line_is_the_offset_union_outline():
    p = sticker()
    result = p.apply({"type": "die-cut", "targets": ["badge", "tab"], "distance": 10})
    line = p.layer("cut-line")
    assert line["shape"] == "path" and line["fill"] == "transparent" and default_fill(line) == "transparent"
    assert line["stroke"] and line["stroke_width"] == 1
    # The union of both targets grown by 10 px: one piece spanning 90..290 x 70..210, around the ellipse and tab.
    assert line["die_cut"]["pieces"] == 1
    assert line["x"] == pytest.approx(90, abs=2) and line["y"] == pytest.approx(70, abs=2)
    assert line["x"] + line["width"] == pytest.approx(290, abs=2)
    assert line["y"] + line["height"] == pytest.approx(210, abs=2)
    assert "Z" in line["path"]  # closed contours
    assert result["die_cut"][0]["pieces"] == 1
    # It is stacked right above the topmost target, and the untouched layer is not inside it.
    names = [layer["name"] for layer in p.state["layers"]]
    assert names.index("cut-line") == names.index("tab") + 1
    assert line["x"] > 40


def test_separate_parts_stay_separate_contours_and_holes_are_filled():
    p = Project(400, 200, "#ffffff")
    p.apply([
        {"type": "shape", "shape": "ellipse", "name": "ring", "x": 20, "y": 20, "width": 140, "height": 140,
         "fill": "transparent", "stroke": "#000", "stroke_width": 12},
        {"type": "shape", "shape": "rectangle", "name": "far", "x": 300, "y": 60, "width": 60, "height": 60, "fill": "#000"},
    ])
    p.apply({"type": "die-cut", "targets": ["ring", "far"], "distance": 6, "name": "cut"})
    line = p.layer("cut")
    assert line["die_cut"]["pieces"] == 2
    assert line["path"].count("M") == 2  # outer outlines only: the ring's hole is not cut


def test_renders_unfilled_in_raster_and_svg(tmp_path):
    p = sticker()
    p.apply({"type": "die-cut", "targets": ["badge"], "distance": 20, "stroke": "#00ff00", "stroke_width": 2})
    image = p.render()
    line = p.layer("cut-line")
    inside = image.getpixel((line["x"] + 8, line["y"] + 8))[:3]  # just inside the line's box corner: background
    assert inside == (255, 255, 255)
    svg = p.export(tmp_path / "s.svg", format="SVG").decode()
    import re

    (element,) = [e for e in re.findall(r"<path[^>]*>", svg) if 'stroke="rgb(0,255,0)"' in e]
    assert 'fill-opacity="0.0"' in element or 'fill="none"' in element


def test_die_cut_is_a_joint_operation_and_validates():
    assert mode("die-cut") == "joint"
    validate_operation({"type": "die-cut", "targets": ["a", "b"], "distance": 8})
    p = sticker()
    p.apply({"type": "die-cut", "target": "badge"})  # a lone target is a one-layer list
    assert p.layer("cut-line")["die_cut"]["distance"] == 12
    p.apply({"type": "sticker-outline", "targets": ["tab"], "name": "tab-cut"})
    assert p.layer("tab-cut")


def test_nothing_to_cut_is_an_error():
    p = Project(200, 200, "#ffffff")
    p.apply({"type": "shape", "shape": "rectangle", "name": "gone", "x": 10, "y": 10, "width": 20, "height": 20,
             "fill": "transparent"})
    with pytest.raises(VixlError):
        p.apply({"type": "die-cut", "targets": ["gone"]})


def test_cli():
    assert compile_command(["die-cut", "badge", "tab", "--distance", "8"]) == {
        "type": "die-cut", "targets": ["badge", "tab"], "distance": 8.0}
