"""Arc, pie wedge and donut segment shapes, and the reusable wedge geometry."""

import io
import math

import numpy as np
import pytest

from vixl import Project
from vixl.errors import VixlError
from vixl.geometry import path_polygons
from vixl.wedge import sweep_of, wedge_centroid, wedge_path, wedge_point


def shoelace(points):
    x, y = np.array(points).T
    return 0.5 * float(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))


def area(path):
    """Net area of a path's loops (a ring's hole subtracts because it runs the other way)."""
    return sum(shoelace(loop) for loop in path_polygons(path))


def alpha(project, **kwargs):
    """Where black ink sits on the white canvas."""
    return np.asarray(project.render(**kwargs).convert("L")) < 128


def test_wedge_path_areas_match_the_circle_formulas():
    r = 100
    for start, end in ((0, 90), (-90, 30), (10, 300), (200, 359)):
        sweep = sweep_of(start, end)
        got = area(wedge_path(0, 0, r, start, end))
        assert got == pytest.approx(math.pi * r * r * sweep / 360, rel=2e-3)
        donut = area(wedge_path(0, 0, r, start, end, 40))
        assert donut == pytest.approx(math.pi * (r * r - 40 * 40) * sweep / 360, rel=2e-3)
    assert area(wedge_path(0, 0, r, 0, 360)) == pytest.approx(math.pi * r * r, rel=2e-3)
    # A full ring is an outer loop plus an opposite-direction hole.
    ring = wedge_path(0, 0, r, 0, 360, 60)
    assert len(path_polygons(ring)) == 2 and area(ring) == pytest.approx(math.pi * (r * r - 60 * 60), rel=2e-3)


def test_angle_convention_and_wraparound():
    assert wedge_point(0, 0, 10, 0) == pytest.approx((10, 0))
    assert wedge_point(0, 0, 10, 90) == pytest.approx((0, 10))      # 3 o'clock is 0, clockwise on screen
    assert wedge_point(0, 0, 10, -90) == pytest.approx((0, -10))    # 12 o'clock
    assert sweep_of(350, 10) == 20 and sweep_of(10, -20) == 330 and sweep_of(0, 720) == 360 and sweep_of(30, 30) == 0
    assert wedge_path(0, 0, 50, 30, 30) == "" and wedge_path(0, 0, 0, 0, 90) == ""
    assert area(wedge_path(0, 0, 100, 350, 10)) == pytest.approx(math.pi * 100 ** 2 * 20 / 360, rel=2e-3)
    # Stretching the vertical radius gives an elliptical wedge.
    assert area(wedge_path(0, 0, 100, 0, 360, aspect=0.5)) == pytest.approx(math.pi * 100 * 50, rel=2e-3)
    x, y = wedge_centroid(0, 0, 100, 0, 90, inner=50)
    assert (x, y) == pytest.approx((75 * math.cos(math.radians(45)), 75 * math.sin(math.radians(45))))
    with pytest.raises(VixlError):
        wedge_path(0, 0, 50, 0, 90, 50)


def test_wedge_path_is_pure_move_line_curve_close_commands():
    from vixl.geometry import parse_path

    commands = {letter for letter, _ in parse_path(wedge_path(0, 0, 80, -90, 200, 30))}
    assert commands == {"M", "L", "C", "Z"}
    assert wedge_path(0, 0, 80, 0, 90) == wedge_path(0, 0, 80, 0, 90), "deterministic"


def make(**extra):
    p = Project(200, 200, "white")
    p.apply([{"type": "shape", "shape": "arc", "name": "a", "width": 160, "height": 160, "x": 20, "y": 20,
              "fill": "#000000", **extra}])
    return p


def test_arc_shape_renders_the_requested_quadrant_and_donut_hole():
    quarter = alpha(make(start_angle=0, end_angle=90))
    assert quarter[104:138, 104:138].mean() > 0.95            # bottom right of the centre
    assert quarter[:100, :].sum() == 0 and quarter[:, :100].sum() == 0
    assert quarter.sum() == pytest.approx(math.pi * 80 ** 2 / 4, rel=0.02)
    ring = alpha(make(inner_radius=0.5))
    assert not ring[100, 100] and ring[100, 30] and ring[100, 170] and not ring[3, 3]
    assert ring.sum() == pytest.approx(math.pi * (80 ** 2 - 40 ** 2), rel=0.02)
    # Default angles draw the whole disc.
    assert alpha(make()).sum() == pytest.approx(math.pi * 80 ** 2, rel=0.02)
    segment = alpha(make(inner_radius=0.5, start_angle=-90, end_angle=0))
    assert segment[40, 150] and not segment[100, 100] and not segment[150, 40]


def test_wedges_sharing_a_box_tile_the_circle_without_gaps():
    p = Project(200, 200, "white")
    shares = [0.446, 0.337, 0.071, 0.146]
    start = -90.0
    for index, share in enumerate(shares):
        end = start + 360 * share
        p.apply([{"type": "shape", "shape": "arc", "name": f"s{index}", "width": 180, "height": 180, "x": 10,
                  "y": 10, "start_angle": start, "end_angle": end, "fill": "#000000"}])
        start = end
    disc = Project(200, 200, "white")
    disc.apply([{"type": "shape", "shape": "ellipse", "width": 180, "height": 180, "x": 10, "y": 10, "fill": "#000000"}])
    mismatch = (alpha(p) != alpha(disc)).sum()
    assert mismatch < 0.01 * alpha(disc).sum()


def test_stroke_stays_inside_the_layer_box_and_non_square_boxes_make_ellipses():
    p = make(stroke="#ff0000", stroke_width=10)
    ink = np.asarray(p.render().convert("L")) < 250
    ys, xs = np.nonzero(ink)
    assert xs.min() >= 19 and xs.max() <= 180 and ys.min() >= 19 and ys.max() <= 180
    ellipse = Project(300, 200, "white")
    ellipse.apply([{"type": "shape", "shape": "arc", "width": 240, "height": 100, "x": 30, "y": 50,
                    "inner_radius": 0.5, "fill": "#000000"}])
    ink = alpha(ellipse)
    assert ink.sum() == pytest.approx(math.pi * 120 * 50 * 0.75, rel=0.03)
    assert ink[100, 40] and not ink[100, 150]


def test_arc_validation_names_the_field():
    p = Project(100, 100)
    for bad, field in (({"start_angle": 40, "end_angle": 40}, "end_angle"), ({"inner_radius": 1}, "inner_radius"),
                       ({"inner_radius": -0.1}, "inner_radius")):
        with pytest.raises(VixlError) as error:
            p.apply([{"type": "shape", "shape": "arc", "width": 50, "height": 50, **bad}])
        assert field in str(error.value) or error.value.details.get("field") == field
    with pytest.raises(VixlError):
        p.apply([{"type": "shape", "shape": "arc", "width": 50, "height": 50, "start_angle": "north"}])
    # Stars keep their own inner radius range.
    with pytest.raises(VixlError):
        p.apply([{"type": "shape", "shape": "star", "width": 50, "height": 50, "inner_radius": 0}])


def test_spelling_aliases_resolve_to_arc():
    p = Project(100, 100)
    notes = []
    from vixl.schema import validate_operation

    op = validate_operation({"type": "donut", "width": 60, "height": 60, "start": -90, "end": 90}, notes)
    assert op["shape"] == "arc" and op["inner_radius"] == 0.6 and (op["start_angle"], op["end_angle"]) == (-90, 90)
    p.apply([{"type": "pie", "name": "slice", "width": 60, "height": 60, "start_angle": 0, "end_angle": 120}])
    assert p.layer("slice")["shape"] == "arc"


def test_arc_resizes_scales_and_survives_save_and_load(tmp_path):
    p = make(start_angle=0, end_angle=90, inner_radius=0.3)
    p.apply([{"type": "resize", "target": "a", "width": 80, "height": 80}])
    small = alpha(p)
    assert small.sum() == pytest.approx(math.pi * (40 ** 2 - 12 ** 2) / 4, rel=0.05)
    p.save(tmp_path / "arc.vixl")
    loaded = Project.load(tmp_path / "arc.vixl")
    assert loaded.layer("a")["end_angle"] == 90
    assert loaded.render().tobytes() == p.render().tobytes()


def test_arc_exports_as_vector_in_svg_pdf_and_pptx():
    p = Project(960, 540, "white")
    p.apply([{"type": "shape", "shape": "arc", "name": "wedge", "width": 300, "height": 300, "x": 40, "y": 40,
              "start_angle": -90, "end_angle": 40, "fill": "#14263b", "stroke": "#f2a541", "stroke_width": 6},
             {"type": "shape", "shape": "arc", "name": "ring", "width": 300, "height": 300, "x": 500, "y": 40,
              "inner_radius": 0.6, "fill": "#a8d5c8"}])
    svg = p.export(format="SVG")
    assert b"<image" not in svg and svg.count(b"<path") == 2 and b" A" not in svg
    report = {}
    pdf = p.export(format="PDF", pdf_content="vector", report=report)
    assert report["raster_fallbacks"] == {}
    pypdf = pytest.importorskip("pypdf")
    page = pypdf.PdfReader(io.BytesIO(pdf)).pages[0]
    assert not list(page.images) and b" c\n" in page.get_contents().get_data()
    pptx = pytest.importorskip("pptx")
    shapes = list(pptx.Presentation(io.BytesIO(p.export(format="PPTX"))).slides[0].shapes)
    assert [shape.name for shape in shapes] == ["wedge", "ring"]
    # Every exporter draws the same ring: the SVG and PNG agree on where the hole is.
    import resvg_py
    from PIL import Image

    raster = Image.open(io.BytesIO(resvg_py.svg_to_bytes(svg_string=svg.decode()))).convert("RGBA")
    assert raster.getpixel((650, 190))[3] == 0 or raster.getpixel((650, 190))[:3] == (255, 255, 255)
    assert raster.getpixel((520 + 20, 190))[3] > 200


def test_cli_compiles_arc_options():
    from vixl.commands import compile_command

    op = compile_command(["shape", "arc", "--start-angle", "-90", "--end-angle", "30", "--inner-radius", "0.6",
                          "--width", "120", "--height", "120", "--fill", "#e2725b"])
    assert op == {"type": "shape", "shape": "arc", "start_angle": -90.0, "end_angle": 30.0, "inner_radius": 0.6,
                  "width": 120, "height": 120, "fill": "#e2725b"}
    assert compile_command(["shape", "arc", "--open", "--stroke", "red"])["closed"] is False


def test_saved_shape_library_keeps_arc_angles(tmp_path, monkeypatch):
    from vixl.interfaces import Session
    from vixl.workflows import dispatch

    monkeypatch.setenv("VIXL_RESOURCES", str(tmp_path / "global.json"))
    session = Session(workspace=tmp_path)
    session.create("main.vixl", 200, 200)
    session.apply({"type": "shape", "shape": "arc", "name": "a", "width": 80, "height": 80, "fill": "red",
                   "start_angle": 20, "end_angle": 200, "inner_radius": 0.4})
    dispatch(session, "shape-save", {"target": "a", "name": "my-arc"})
    session.apply({"type": "shape-place", "resource": "my-arc", "name": "again", "width": 40, "height": 40})
    with session.project() as p:
        layer = p.layer("again")
        assert layer["shape"] == "arc" and layer["width"] == 40
        assert (layer["start_angle"], layer["end_angle"], layer["inner_radius"]) == (20, 200, 0.4)


def open_arc(**extra):
    p = Project(240, 240, "white")
    p.apply([{"type": "shape", "shape": "arc", "name": "a", "x": 20, "y": 20, "width": 200, "height": 200,
              "start_angle": -50, "end_angle": 100, "stroke": "#000000", "stroke_width": 9, "closed": False, **extra}])
    return p


def test_open_arc_strokes_only_the_curve_and_has_no_default_fill():
    """#605: closed: false draws the curve alone, unfilled, with nothing to the centre."""
    from vixl.geometry import default_fill, is_open_shape

    p = open_arc()
    layer = p.layer("a")
    assert is_open_shape(layer) and default_fill(layer) == "transparent"
    ink = alpha(p)
    assert not ink[120, 120] and not ink[89, 146]           # the centre and the radius at -50°
    assert ink[120, 213]                                    # on the curve at 3 o'clock
    assert not ink[120, 27]                                 # 180° is outside the sweep
    closed = alpha(open_arc(closed=True, fill="none"))
    assert closed[89, 146]                                  # the wedge outline runs along that radius
    # Round caps have something to cap: the ends reach a little past the butt ends.
    assert alpha(open_arc(line_cap="round")).sum() > ink.sum()


def test_open_arc_is_open_in_svg_pdf_and_pptx():
    p = open_arc(line_cap="round")
    svg = p.export(format="SVG").decode()
    path = svg[svg.index("<path"):]
    path = path[:path.index(">")]
    assert ('fill="none"' in path or 'fill-opacity="0.0"' in path) and "Z" not in path.split(' d="')[1].split('"')[0]
    assert 'stroke-linecap="round"' in path
    pdf = p.export(format="PDF", pdf_content="vector")
    pypdf = pytest.importorskip("pypdf")
    content = pypdf.PdfReader(io.BytesIO(pdf)).pages[0].get_contents().get_data()
    arc = content.split(b" RG\n", 1)[1]
    assert b"c\nS\n" in arc and b"\nh\n" not in arc and b"\nf\n" not in arc and b"B\n" not in arc
    pptx = pytest.importorskip("pptx")
    from lxml import etree

    shape = list(pptx.Presentation(io.BytesIO(p.export(format="PPTX"))).slides[0].shapes)[0]
    xml = etree.tostring(shape._element).decode()
    assert "<a:close/>" not in xml and "<a:noFill/>" in xml


def test_open_arc_validation_and_edit():
    p = Project(100, 100)
    with pytest.raises(VixlError) as error:
        p.apply([{"type": "shape", "shape": "arc", "width": 50, "height": 50, "closed": False, "inner_radius": 0.5,
                  "stroke": "black"}])
    assert "inner_radius" in str(error.value) or error.value.details.get("field") == "inner_radius"
    q = open_arc(closed=True, fill="none")
    q.apply({"type": "shape", "target": "a", "closed": False})
    assert q.layer("a")["closed"] is False and not alpha(q)[89, 146]
