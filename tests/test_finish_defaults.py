"""Clean glow and shadow defaults, fitted dashes and drawings that keep their shape past the box (craft check
2026-10-13: muddy glows and shadows on four pieces, broken dashes and a cut-off loaf on three)."""

import math
import zipfile

import numpy as np
import pytest

from vixl import Project
from vixl.colors import parse, srgb_to_oklab, to_polar
from vixl.render import render


def lch(value):
    return to_polar(srgb_to_oklab(parse(value)[:3]))


def pixel(image, x, y):
    return np.asarray(image.convert("RGB"), dtype=float)[y, x] / 255


# --- glows ---------------------------------------------------------------------------------------------------


def navy_bars(*extra):
    p = Project(240, 160, "#14213d")
    p.apply([{"type": "shape", "shape": "rectangle", "name": "bar", "x": 90, "y": 40, "width": 60, "height": 80,
              "fill": "#f59e0b"}, *extra])
    return p


def test_glow_is_a_lighter_tint_that_only_adds_light_to_a_dark_backdrop():
    p = navy_bars({"type": "look", "target": "bar", "look": "glow", "amount": 1})
    glow = p.layer("bar")["styles"]["outer-glow"]
    assert lch(glow["color"])[0] > lch("#f59e0b")[0]  # lighter than the bar
    assert abs(lch(glow["color"])[2] - lch("#f59e0b")[2]) < 25  # in the bar's hue
    assert glow["opacity"] <= 0.6  # capped: the old recipe went to 1.0
    image = render(p)
    navy = np.array(parse("#14213d")[:3])
    for x in range(70, 90, 3):  # the glow beside the bar never darkens or browns the navy
        assert (pixel(image, x, 80) >= navy - 1 / 255).all()


def test_glow_on_a_light_ground_keeps_the_layers_colour():
    p = Project(240, 160, "#f8fafc")
    p.apply([{"type": "shape", "shape": "ellipse", "name": "dot", "x": 90, "y": 50, "width": 60, "height": 60,
              "fill": "#7c3aed"}, {"type": "look", "target": "dot", "look": "glow"}])
    glow = p.layer("dot")["styles"]["outer-glow"]
    assert glow["color"] == "#7c3aed" and glow["opacity"] <= 0.6


def test_glow_keeps_an_explicit_colour():
    p = navy_bars({"type": "look", "target": "bar", "look": "glow", "color": "#22d3ee"})
    assert p.layer("bar")["styles"]["outer-glow"]["color"] == "#22d3ee"


def test_soft_halo_on_a_gradient_is_a_lighter_capped_tint():
    p = Project(240, 160, "#14213d")
    p.apply([{"type": "gradient", "name": "halo", "x": 20, "y": 0, "width": 200, "height": 160,
              "start": "#f59e0b", "end": "#f59e0b"},
             {"type": "look", "target": "halo", "look": "soft-halo", "amount": 1}])
    core = p.layer("halo")["stops"][0]["color"]
    assert "70%" in core  # the core alpha is capped at 0.7 (it was 1.0 at amount 1)
    tint = core.split("srgb, ")[1].split(" ")[0]
    assert lch(tint)[0] > lch("#f59e0b")[0]


# --- shadows -------------------------------------------------------------------------------------------------


def cream_button(*extra):
    p = Project(300, 200, "#f3e9d2")
    p.apply([{"type": "shape", "shape": "rectangle", "name": "button", "x": 40, "y": 60, "width": 220, "height": 60,
              "fill": "#c1121f"}, *extra])
    return p


def test_soft_shadow_takes_the_backdrop_colour_and_is_small_and_light():
    p = cream_button({"type": "look", "target": "button", "look": "soft-shadow", "amount": 0.5})
    shadow = p.layer("button")["styles"]["drop-shadow"]
    L, C, H = lch(shadow["color"])
    bL, bC, bH = lch("#f3e9d2")
    assert L < bL * 0.5 and C > 0.005 and abs(H - bH) < 15  # the cream in shade, not black or grey
    assert shadow["opacity"] <= 0.25 and shadow["blur"] <= 4 and shadow["dy"] <= 2


def test_soft_shadow_keeps_an_explicit_colour():
    p = cream_button({"type": "look", "target": "button", "look": "soft-shadow", "color": "#000000"})
    assert p.layer("button")["styles"]["drop-shadow"]["color"] == "#000000"


def test_shadow_reads_the_backdrop_under_a_layer_inside_a_group():
    p = Project(300, 200, "#ffffff")
    p.apply([{"type": "shape", "shape": "rectangle", "name": "card", "x": 20, "y": 20, "width": 260, "height": 160,
              "fill": "#1e3a8a"},
             {"type": "shape", "shape": "rectangle", "name": "chip", "x": 100, "y": 80, "width": 80, "height": 40,
              "fill": "#fde68a"},
             {"type": "group", "name": "panel", "targets": ["card", "chip"]},
             {"type": "look", "target": "chip", "look": "soft-shadow"}])
    color = p.layer("chip")["styles"]["drop-shadow"]["color"]
    assert abs(lch(color)[2] - lch("#1e3a8a")[2]) < 15  # navy shade, from the card under it


def test_hard_shadow_without_a_colour_is_a_dark_shade_of_the_backdrop():
    p = cream_button({"type": "look", "target": "button", "look": "hard-shadow"})
    shadow = p.layer("button")["styles"]["drop-shadow"]
    assert shadow["blur"] == 0 and shadow["opacity"] == 1 and shadow["color"] not in ("#000000", "black")
    assert abs(lch(shadow["color"])[2] - lch("#f3e9d2")[2]) < 15


def test_rolled_looks_measure_every_target_in_one_render(monkeypatch):
    from vixl import looks
    from vixl import render as render_module

    calls = []
    original = render_module.render_layers
    monkeypatch.setattr(render_module, "render_layers", lambda *a, **k: calls.append(1) or original(*a, **k))
    p = cream_button({"type": "shape", "shape": "rectangle", "name": "two", "x": 40, "y": 140, "width": 100,
                      "height": 40, "fill": "#003049"})
    looks.execute(p, {"type": "look", "look": "soft-shadow", "targets": ["button", "two"]})
    assert len(calls) == 1


# --- dashes --------------------------------------------------------------------------------------------------


def dashed_runs(shape, dash=(14, 9), fit=None, **extra):
    from vixl.geometry import path_polygons
    from vixl.vector_paths import pixel_path
    from vixl.vector_strokes import dashed, fitted

    p = Project(240, 160, "#ffffff")
    p.apply({"type": "shape", "shape": shape, "name": "s", "x": 20, "y": 20, "width": 160, "height": 110,
             "fill": "transparent", "stroke": "#111111", "stroke_width": 4, "dash": list(dash), **extra})
    polygon = path_polygons(pixel_path(p.layer("s")))[0]
    points = [q for i, q in enumerate(polygon) if i == 0 or q != polygon[i - 1]]
    return p, points, (fitted(points, list(dash), 0, True) if fit is not False else dashed(points, list(dash)))


def test_dashes_divide_a_rectangle_evenly_with_a_dash_on_every_corner():
    p, points, runs = dashed_runs("rectangle")
    corners = [(0, 0), (160, 0), (160, 110), (0, 110)]
    for corner in corners:  # each corner lies inside a dash, not in a gap
        assert any(math.dist(corner, q) < 1e-6 for run, _ in runs for q in run[1:-1]), corner
    lengths = [sum(math.dist(a, b) for a, b in zip(run, run[1:])) for run, _ in runs]
    # Within one side every dash has the same length: no stub dash where the pattern runs out.
    assert max(lengths) - min(lengths) < 0.5 * min(lengths)


def test_unfitted_dashes_leave_stubs_and_gaps_at_corners():
    _, points, runs = dashed_runs("rectangle", fit=False)
    covered = [any(math.dist(c, q) < 1e-6 for run, _ in runs for q in run[1:-1]) for c in ((160, 0), (160, 110), (0, 110))]
    assert not all(covered)


def test_rounded_corners_are_centred_on_a_dash_and_render_that_way():
    p = Project(240, 160, "#ffffff")
    p.apply({"type": "shape", "shape": "rounded-rectangle", "name": "s", "x": 20, "y": 20, "width": 170, "height": 110,
             "radius": 24, "fill": "transparent", "stroke": "#111111", "stroke_width": 4, "dash": [14, 9]})
    image = np.asarray(render(p).convert("L"))
    # The middle of each rounded corner's arc (inside stroke: 2 px in from the outline) is inked.
    r, inset = 24, 2
    for cx, cy, sx, sy in ((20 + r, 20 + r, -1, -1), (190 - r, 20 + r, 1, -1), (190 - r, 130 - r, 1, 1), (20 + r, 130 - r, -1, 1)):
        d = (r - inset) / math.sqrt(2)
        assert image[round(cy + sy * d), round(cx + sx * d)] < 128
    p.apply({"type": "shape", "target": "s", "dash_fit": False})
    assert p.layer("s")["dash_fit"] is False
    assert not np.array_equal(np.asarray(render(p).convert("L")), image)


def test_dotted_ring_has_round_dots_and_no_spur_at_the_seam():
    p = Project(100, 100, "#ffffff")
    p.apply({"type": "shape", "shape": "ellipse", "name": "ring", "x": 20, "y": 20, "width": 50, "height": 50,
             "fill": "transparent", "stroke": "#000000", "stroke_width": 3, "dash": "dotted"})
    ink = np.argwhere(np.asarray(render(p).convert("L")) < 200)
    radius = np.hypot(ink[:, 0] - 44.5, ink[:, 1] - 44.5)
    assert radius.max() < 26.5  # nothing pokes out of the ring (the seam drew a spike outward)


def test_svg_pdf_and_pptx_draw_the_same_fitted_dashes():
    from vixl.vector_strokes import primitives

    p = Project(240, 160, "#ffffff")
    p.apply({"type": "shape", "shape": "rounded-rectangle", "name": "s", "x": 20, "y": 20, "width": 170, "height": 110,
             "radius": 20, "fill": "transparent", "stroke": "#111111", "stroke_width": 4, "dash": [14, 9]})
    drawn = [path for path, paint in primitives(p.layer("s"), p) if path and paint != "transparent"]
    import tempfile
    from pathlib import Path
    from vixl.export_dispatch import export

    folder = Path(tempfile.mkdtemp())
    export(p, folder / "a.svg")
    svg = (folder / "a.svg").read_text()
    assert all(path in svg for path in drawn)
    export(p, folder / "a.pptx")
    slide = zipfile.ZipFile(folder / "a.pptx").read("ppt/slides/slide1.xml").decode()
    # PowerPoint gets the same outlines as filled shapes (it used to drop the dashes for a solid line).
    assert slide.count("<a:custGeom>") == len(drawn) and "<a:ln w=" not in slide
    export(p, folder / "a.pdf")
    pdf = (folder / "a.pdf").read_bytes()
    assert b"/Subtype /Image" not in pdf and b"/Subtype/Image" not in pdf  # vector, not a raster fallback


# --- drawings past their box ---------------------------------------------------------------------------------

LOAF = "M10 40 Q50 -70 90 40 L90 90 L10 90 Z"  # a dome that rises 15 px above its box


def loaf(*extra, **fields):
    p = Project(200, 200, "#ffffff")
    p.apply([{"type": "shape", "shape": "path", "path": LOAF, "name": "loaf", "x": 30, "y": 60, "width": 100,
              "height": 90, "fill": "#c88a3a", **fields}, *extra])
    return p


def top_ink(p):
    image = np.asarray(render(p).convert("L"))
    return int(np.where((image < 235).any(axis=1))[0].min())


def test_cut_paper_keeps_a_dome_that_rises_past_its_box():
    assert top_ink(loaf()) == 45
    # cut-paper's grain and edge used to drop the overflow marker, so the renderer squeezed the dome into the box.
    assert top_ink(loaf({"type": "cut-paper", "target": "loaf"})) <= 46


def test_check_reports_a_path_drawn_cut_off_at_its_box(monkeypatch):
    from vixl import scene
    from vixl.checks import check_design

    def found(p):
        return [i for i in check_design(p, checks=["bounds"])["issues"] if i.get("code") == "geometry-clipped"]

    assert not found(loaf({"type": "cut-paper", "target": "loaf"}))
    # The cut-paper bug: its texture pass dropped the overflow marker, so the dome was squeezed into the box.
    # A renderer that does that again is caught, as a finding to fix.
    original = scene.paper_image

    def unmarked(image, layer):
        result = original(image, layer)
        if layer.get("cut_paper"):
            result.info.pop("vixl_vector_overflow", None)
        return result

    monkeypatch.setattr(scene, "paper_image", unmarked)
    issues = found(loaf({"type": "cut-paper", "target": "loaf"}))
    assert issues and issues[0]["sides"] == ["top"] and issues[0]["action"] == "fix" and issues[0]["severity"] == "error"
    assert "path-fit" in issues[0]["message"]


# --- where dashes stay exact ---------------------------------------------------------------------------------


def test_imported_svg_dashes_keep_their_exact_lengths():
    from vixl.imports import svg_operations

    svg = (b'<svg xmlns="http://www.w3.org/2000/svg" width="100" height="60"><rect x="5" y="5" width="90" height="50" '
           b'fill="none" stroke="#000" stroke-width="2" stroke-dasharray="6 4"/></svg>')
    p = Project(100, 60, "#ffffff")
    p.apply(svg_operations(svg, p, "art"))
    dashed = [layer for layer in p.state["layers"] if layer.get("dash")]
    assert dashed and all(layer["dash_fit"] is False for layer in dashed)


@pytest.mark.parametrize("look,expected", [("preserve", False), ("current", None)])
def test_converting_an_older_document_keeps_its_dashes_exact(look, expected):
    from vixl.convert import rules

    p = Project(100, 60, "#ffffff")
    p.apply({"type": "shape", "shape": "rectangle", "name": "box", "x": 5, "y": 5, "width": 90, "height": 50,
             "fill": "transparent", "stroke": "#000000", "stroke_width": 2, "dash": [6, 4]})
    ctx = rules.Context(look, (0, 26, 0), p, None)
    rules.dash_fit(ctx, p.state)
    assert p.layer("box").get("dash_fit") is expected
    assert [entry["change"] for entry in (ctx.changes if look == "preserve" else ctx.warnings)] == ["dash-fit"]
