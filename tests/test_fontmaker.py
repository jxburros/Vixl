"""Custom fonts: glyphs drawn as layers, built into TrueType/OpenType/WOFF and usable by text in the same document."""

from io import BytesIO
import os
import subprocess
import sys

import numpy as np
import pytest
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.recordingPen import RecordingPen
from fontTools.ttLib import TTFont

from vixl.errors import VixlError
from vixl.project import Project

RING = ("M50 0 C78 0 100 31 100 70 C100 109 78 140 50 140 C22 140 0 109 0 70 C0 31 22 0 50 0 Z "
        "M50 25 C35 25 25 45 25 70 C25 95 35 115 50 115 C65 115 75 95 75 70 C75 45 65 25 50 25 Z")


def drawn():
    """I (a filled bar), O (a ring with a counter) and V (a stroked open path) drawn in font-grid cells."""
    p = Project(1000, 500, background="white")
    p.apply([{"type": "font-design", "family": "Sprout Test", "em": 200, "kerning": {"VO": -10}},
             {"type": "font-grid", "chars": "IOV"}])
    cells = p.state["font_design"]["glyphs"]
    (ix, iy), (ox, oy), (vx, vy) = (cells[c]["origin"] for c in "IOV")
    p.apply([
        {"type": "shape", "shape": "rectangle", "name": "i-stem", "x": ix + 45, "y": iy - 140, "width": 30,
         "height": 140, "fill": "#c33"},
        {"type": "shape", "shape": "path", "name": "o-ring", "x": ox + 10, "y": oy - 140, "path": RING, "fill": "black"},
        {"type": "shape", "shape": "path", "name": "v-stroke", "x": vx + 5, "y": vy - 140, "path": "M5 5 L55 120 L105 5",
         "stroke": "black", "stroke_width": 24},
    ])
    return p


def bounds(font, name):
    pen = BoundsPen(font.getGlyphSet())
    font.getGlyphSet()[name].draw(pen)
    return pen.bounds


def signed_areas(font, name):
    """Signed area of each contour (positive is counter-clockwise, y up)."""
    pen = RecordingPen()
    font.getGlyphSet()[name].draw(pen)
    areas, points = [], []
    for command, args in pen.value:
        if command == "moveTo":
            points = [args[0]]
        elif command in ("lineTo", "curveTo", "qCurveTo"):
            points.extend(a for a in args if a is not None)
        elif command == "closePath":
            areas.append(sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(points, points[1:] + points[:1])) / 2)
    return areas


@pytest.mark.parametrize("suffix", ["ttf", "otf", "woff"])
def test_drawn_glyphs_export_as_a_font_with_metrics_and_kerning(tmp_path, suffix):
    report = {}
    data = drawn().export(tmp_path / f"sprout.{suffix}", report=report)
    font = TTFont(BytesIO(data))
    assert font.flavor == ("woff" if suffix == "woff" else None)
    assert ("CFF " in font) == (suffix == "otf") and ("glyf" in font) == (suffix != "otf")
    assert font.getBestCmap() == {32: "space", 73: "I", 79: "O", 86: "V", 160: "space"}
    assert font["name"].getDebugName(1) == "Sprout Test" and font["name"].getDebugName(6) == "SproutTest-Regular"
    assert font["head"].unitsPerEm == 1000 and font["OS/2"].fsType == 0
    assert font["hhea"].ascent == 800 and font["hhea"].descent == -200
    # 200 px em → 5 units per pixel: the stem sits 45 px into a 120 px cell and is 30 × 140 px.
    assert font["hmtx"]["I"] == (600, 225) and bounds(font, "I") == (225, 0, 375, 700)
    assert font["hmtx"]["space"][0] == 250  # 0.25 em when no glyph draws the space
    # The ring keeps its counter: an outer contour and a hole wound the other way.
    areas = signed_areas(font, "O")
    assert len(areas) == 2 and areas[0] * areas[1] < 0
    # The V's stroke became a filled outline.
    assert bounds(font, "V")[3] > 600
    assert "GPOS" in font and report["kerning_pairs"] == 1
    assert report["characters"] == " IOV" and report["glyphs"] == 5 and "warnings" not in report


def test_outer_contours_follow_each_format_convention(tmp_path):
    p = drawn()
    truetype = TTFont(BytesIO(p.export(tmp_path / "a.ttf")))
    postscript = TTFont(BytesIO(p.export(tmp_path / "a.otf")))
    assert signed_areas(truetype, "I")[0] < 0  # TrueType: clockwise
    assert signed_areas(postscript, "I")[0] > 0  # PostScript: counter-clockwise


def test_the_same_design_builds_the_same_bytes(tmp_path):
    assert drawn().export(tmp_path / "a.otf") == drawn().export(tmp_path / "b.otf")


def test_font_build_embeds_the_font_for_text_in_the_same_document():
    p = drawn()
    p.apply([{"type": "font-build"},
             {"type": "text", "text": "VOI", "font": "Sprout-Test", "size": 100, "x": 20, "y": 330, "color": "black",
              "name": "specimen"}])
    assert p.state["fonts"]["Sprout-Test"].startswith("fonts/")
    ink = np.asarray(p.render().convert("L"))[330:480, 20:400] < 128
    assert ink.sum() > 1500
    # Three glyphs side by side: ink in each third of the 1.8 em wide line.
    columns = ink.any(axis=0)
    assert columns[:60].any() and columns[60:120].any() and columns[120:180].any()
    p.apply([{"type": "font-build", "name": "sprout-otf", "format": "otf"}])
    assert TTFont(BytesIO(p.assets[p.state["fonts"]["sprout-otf"]]))["CFF "]


def test_explicit_layers_text_sources_and_private_use_code_points(tmp_path):
    p = Project(600, 300)
    p.apply([
        {"type": "font-design", "family": "Marks", "em": 100, "side_bearing": 10},
        {"type": "shape", "shape": "star", "name": "star", "x": 20, "y": 20, "width": 80, "height": 80, "fill": "red",
         "opacity": 0.4},
        {"type": "text", "text": "A", "name": "letter", "x": 300, "y": 20, "size": 100, "color": "black"},
        {"type": "font-glyph", "char": "U+E001", "target": "star"},
        {"type": "font-glyph", "char": "A", "targets": ["letter"]},
    ])
    font = TTFont(BytesIO(p.export(tmp_path / "marks.ttf")))
    assert font.getBestCmap()[0xE001] == "uniE001"
    # Without an origin the glyph sits on its bottom edge with the side bearing each side (10 px = 100 units).
    x0, y0, x1, y1 = bounds(font, "uniE001")
    assert (x0, y0) == (100, 0) and font["hmtx"]["uniE001"][0] == round(x1 + 100)
    assert bounds(font, "A")[2] - bounds(font, "A")[0] > 300


def test_a_cell_takes_its_vector_layers_and_skips_others():
    from vixl.fontmaker import glyph_outlines

    p = Project(400, 300)
    p.apply([{"type": "font-design", "family": "Cells", "em": 100},
              {"type": "font-glyph", "char": "x", "origin": [100, 150], "advance": 60},
              # Centred on the cell but far larger than it: a backdrop, not part of the glyph.
              {"type": "shape", "shape": "rectangle", "name": "backdrop", "x": -70, "y": -30, "width": 400,
               "height": 300, "fill": "white"},
              {"type": "shape", "shape": "rectangle", "name": "mark", "x": 110, "y": 100, "width": 40, "height": 50,
               "fill": "black"},
              {"type": "shape", "shape": "rectangle", "name": "far", "x": 300, "y": 100, "width": 40, "height": 50,
               "fill": "black"},
              {"type": "shape", "shape": "rectangle", "name": "hidden", "x": 115, "y": 110, "width": 10, "height": 10,
               "fill": "black"},
              {"type": "hide", "target": "hidden"}])
    warnings = []
    contours, advance = glyph_outlines(p, warnings=warnings)["x"]
    assert advance == 600 and len(contours) == 1
    xs = [pt[0] for seg in contours[0] for pt in seg]
    assert min(xs) == pytest.approx(100) and max(xs) == pytest.approx(500)
    assert warnings == []


def test_grid_lays_out_cells_and_guides_and_refuses_a_small_canvas():
    p = Project(800, 600)
    p.apply([{"type": "font-design", "em": 100}, {"type": "font-grid", "chars": "digits", "columns": 4}])
    glyphs = p.state["font_design"]["glyphs"]
    assert list(glyphs) == list("0123456789")
    assert glyphs["0"] == {"origin": [25, 105], "advance": 60} and glyphs["4"]["origin"] == [25, 230]
    guides = p.state["guides"]
    assert guides["font-r1-baseline"] == {"axis": "y", "position": 105}
    assert guides["font-r3-descent"]["position"] == 375 and guides["font-c4-right"]["position"] == 340
    p.apply([{"type": "font-grid", "chars": "AB", "guides": False}])
    assert not any(name.startswith("font-r") for name in p.state["guides"])
    with pytest.raises(VixlError, match="canvas of at least"):
        Project(100, 100).apply([{"type": "font-grid", "chars": "uppercase"}])


def test_font_operations_explain_mistakes(tmp_path):
    p = Project(300, 200)
    p.apply([{"type": "shape", "shape": "rectangle", "name": "box", "width": 20, "height": 20}])
    for op, message in [
        ({"type": "font-glyph", "char": "AB", "target": "box"}, "one character"),
        ({"type": "font-glyph", "char": "Q"}, "its layers"),
        ({"type": "font-glyph", "char": "Q", "origin": [0, 0]}, "advance"),
        ({"type": "font-glyph", "char": "Q", "remove": True}, "no glyph"),
        ({"type": "font-design", "kerning": {"ABC": 1}}, "two characters"),
        ({"type": "font-build"}, "family"),
    ]:
        with pytest.raises(VixlError, match=message):
            p.apply([op])
    with pytest.raises(VixlError, match="family"):
        p.export(tmp_path / "x.ttf")
    p.apply([{"type": "font-design", "family": "Box"}])
    with pytest.raises(VixlError, match="no glyphs"):
        p.export(tmp_path / "x.ttf")
    p.apply([{"type": "add", "path": str(write_png(tmp_path)), "name": "photo"},
             {"type": "font-glyph", "char": "B", "target": "photo"}])
    with pytest.raises(VixlError, match="drawing vectorize"):
        p.export(tmp_path / "x.ttf")
    p.apply([{"type": "font-glyph", "char": "B", "target": "box"}])
    p.export(tmp_path / "x.ttf")
    with pytest.raises(VixlError, match="overwrite"):
        p.export(tmp_path / "x.ttf")
    with pytest.raises(VixlError, match="font design"):
        p.export(tmp_path / "y.ttf", color_space="cmyk")
    p.apply([{"type": "remove", "target": "box"}])
    report = {}
    p.export(tmp_path / "x.ttf", overwrite=True, report=report)
    assert "Glyph 'B': a layer it used was deleted" in report["warnings"]


def write_png(tmp_path):
    from PIL import Image

    path = tmp_path / "photo.png"
    Image.new("RGB", (20, 20), "red").save(path)
    return path


def test_woff2_needs_brotli(tmp_path):
    pytest.importorskip("fontTools")
    try:
        import brotli  # noqa: F401
    except ImportError:
        with pytest.raises(VixlError, match="brotli"):
            drawn().export(tmp_path / "x.woff2")
    else:
        assert TTFont(BytesIO(drawn().export(tmp_path / "x.woff2"))).flavor == "woff2"


def test_font_design_survives_save_and_invalid_records_are_refused(tmp_path):
    drawn().save(tmp_path / "doc.vixl")
    loaded = Project.load(tmp_path / "doc.vixl")
    assert loaded.state["font_design"]["kerning"] == {"VO": -10}
    assert TTFont(BytesIO(loaded.export(tmp_path / "again.ttf")))["glyf"]["O"].numberOfContours == 2
    from vixl.fontmaker import validate

    state = {"font_design": {"glyphs": {"AB": {}}}}
    with pytest.raises(VixlError, match="glyph"):
        validate(loaded, state)
    with pytest.raises(VixlError, match="font design"):
        validate(loaded, {"font_design": {"colour": "red"}})


def test_export_file_rest_and_cli_write_fonts(tmp_path):
    from fastapi.testclient import TestClient
    from vixl.interfaces import Session, create_app
    from vixl.mcp_tools import export_file

    drawn().save(tmp_path / "doc.vixl")
    result = export_file(Session(workspace=tmp_path), "out.otf", document="doc.vixl")
    assert result["format"] == "OTF" and result["glyphs"] == 5 and result["family"] == "Sprout Test"
    response = TestClient(create_app(tmp_path / "doc.vixl")).post("/export", json={"format": "WOFF"})
    assert response.status_code == 200 and response.headers["content-type"] == "font/woff"
    assert TTFont(BytesIO(response.content)).flavor == "woff"
    env = {**os.environ, "PYTHONPATH": os.pathsep.join(sys.path)}
    run = subprocess.run([sys.executable, "-m", "vixl", "-p", str(tmp_path / "doc.vixl"), "export",
                          str(tmp_path / "cli.ttf")], capture_output=True, text=True, env=env)
    assert run.returncode == 0, run.stderr
    assert TTFont(tmp_path / "cli.ttf").getBestCmap()[ord("V")] == "V"
