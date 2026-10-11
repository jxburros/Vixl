"""Recreating a logo from an image (#443): curve fitting, one layer per part, path-split and a fidelity number."""

import numpy as np
import pytest
from PIL import Image, ImageDraw

from vixl import Project, drawing
from vixl.commands import compile_command
from vixl.errors import VixlError
from vixl.schema import validate_operation
from vixl.trace import corners, fit_curves, mask_curves


@pytest.fixture
def logo(tmp_path):
    """A flat black logo: a ring, a bar and a triangle side by side, and a dot under them."""
    image = Image.new("RGB", (520, 300), "white")
    draw = ImageDraw.Draw(image)
    draw.ellipse((30, 40, 170, 180), fill="black")
    draw.ellipse((70, 80, 130, 140), fill="white")
    draw.rectangle((210, 50, 260, 170), fill="black")
    draw.polygon([(300, 170), (380, 45), (460, 170)], fill="black")
    draw.ellipse((230, 220, 270, 260), fill="black")
    path = tmp_path / "logo.png"
    image.save(path)
    return path


def traced(logo, **settings):
    p = Project(600, 400, "#ffffff")
    p.apply([{"type": "drawing", "action": "import", "path": str(logo), "name": "logo", "x": 0, "y": 0},
             {"type": "drawing", "action": "vectorize", "target": "logo", "settings": {"mode": "outline", **settings}}])
    return p


def parts(p):
    ident = p.layer("logo")["id"]
    return [layer for layer in p.state["layers"] if layer.get("parent") == ident and layer.get("drawing_role") == "lines"]


def test_fit_curves_keeps_corners_and_needs_few_segments():
    image = Image.new("L", (240, 160), 0)
    draw = ImageDraw.Draw(image)
    draw.rectangle((20, 20, 120, 120), fill=255)
    draw.ellipse((140, 20, 230, 140), fill=255)
    path, loops = mask_curves(np.asarray(image) > 127, tolerance=1.0)
    square, oval = sorted(loops, key=lambda loop: loop[:, 0].min())
    assert len(corners(square, True, 60)) == 4 and corners(oval, True, 60) == []
    contours = path.split("M")[1:]
    assert all("L" not in c for c in contours) and sum(c.count("C") for c in contours) <= 14
    for loop in loops:  # every traced point lies within about a pixel of the fitted curves
        segments = fit_curves(loop, True, 1.0, 60)
        samples = np.concatenate([[(1 - t) ** 3 * s[0] + 3 * (1 - t) ** 2 * t * s[1] + 3 * (1 - t) * t * t * s[2]
                                   + t ** 3 * s[3] for t in np.linspace(0, 1, 60)] for s in segments])
        nearest = np.min(np.hypot(*(loop[:, None, :] - samples[None, :, :]).transpose(2, 0, 1)), axis=1)
        assert nearest.max() < 2.0


def test_outline_curves_replace_hundreds_of_line_segments(logo):
    lines = traced(logo)
    curves = traced(logo, curves=True)
    straight = lines.layer("logo/lines")["path"]
    fitted = curves.layer("logo/lines")["path"]
    assert " C" in fitted and " L" not in fitted
    assert fitted.count("C") * 3 < straight.count("L")
    assert drawing.report(curves, "logo")["fidelity"]["iou"] > 0.97


def test_split_components_gives_one_layer_per_part_in_reading_order(logo):
    p = traced(logo, curves=True, split="components")
    layers = parts(p)
    assert [layer["name"] for layer in layers] == [f"logo/part-00{i}" for i in range(1, 5)]
    centres = [(layer["x"] + layer["width"] / 2, layer["y"] + layer["height"] / 2) for layer in layers]
    assert centres[0][0] < centres[1][0] < centres[2][0]  # ring, bar, triangle on the first line
    assert centres[3][1] > 200  # then the dot below
    ring = layers[0]
    assert ring["path"].count("M") == 2  # the ring keeps its hole
    assert ring["width"] < 160 and ring["x"] > 20  # each part has its own box
    report = drawing.report(p, "logo")
    assert report["fidelity"]["iou"] > 0.97 and report["fidelity"]["mismatch"] < 0.01
    assert report["preserved"] > 0.95
    # Vectorizing again replaces the parts.
    p.apply({"type": "drawing", "action": "vectorize", "target": "logo", "settings": {"mode": "outline"}})
    assert [layer["name"] for layer in parts(p)] == ["logo/lines"]


def test_fidelity_drops_when_a_part_is_lost(logo):
    p = traced(logo, split="components")
    full = drawing.report(p, "logo")["fidelity"]
    p.apply({"type": "hide", "target": "logo/part-002"})
    worse = drawing.report(p, "logo")["fidelity"]
    assert worse["iou"] < full["iou"] - 0.05 and worse["mismatch_pixels"] > full["mismatch_pixels"]


def test_curves_and_split_are_outline_settings(logo):
    p = Project(600, 400, "#ffffff")
    p.apply({"type": "drawing", "action": "import", "path": str(logo), "name": "logo"})
    with pytest.raises(VixlError):
        p.apply({"type": "drawing", "action": "vectorize", "target": "logo", "settings": {"curves": True}})
    with pytest.raises(VixlError):
        p.apply({"type": "drawing", "action": "vectorize", "target": "logo",
                 "settings": {"mode": "outline", "split": "letters"}})


def test_drawing_compare_workflow_reports_fidelity(logo, tmp_path):
    from vixl.interfaces import Session
    from vixl.workflows import dispatch

    p = traced(logo, curves=True)
    p.save(tmp_path / "logo.vixl")
    session = Session(tmp_path / "logo.vixl", workspace=tmp_path)
    result = dispatch(session, "drawing-compare", {"target": "logo", "output": "compare.png"})
    assert result["fidelity"]["iou"] > 0.97 and (tmp_path / "compare.png").exists()


def bar():
    p = Project(400, 300, "#ffffff")
    p.apply({"type": "shape", "shape": "rectangle", "name": "bar", "x": 50, "y": 100, "width": 300, "height": 60,
             "fill": "#111111"})
    return p


def ink(p):
    return np.asarray(p.render().convert("L")) < 128


def test_path_split_by_line_with_overlap():
    p = bar()
    before = ink(p)
    p.apply({"type": "path-split", "target": "bar", "line": [[150, 80], [150, -10]], "overlap": 4,
             "names": ["left", "right"]})
    left, right = p.layer("left"), p.layer("right")
    assert p.layer("bar")["visible"] is False
    assert left["fill"] == right["fill"] == "#111111" and left["x"] == right["x"] == 50
    # Together they draw exactly the original.
    assert (ink(p) ^ before).sum() < 0.01 * before.sum()
    # Each reaches 4 px across the cut at x = 50 + 150.
    hide = p.clone()
    hide.apply({"type": "hide", "target": "right"})
    xs = np.nonzero(ink(hide).any(axis=0))[0]
    assert xs.min() == pytest.approx(50, abs=1) and xs.max() == pytest.approx(204, abs=1.5)
    hide = p.clone()
    hide.apply({"type": "hide", "target": "left"})
    xs = np.nonzero(ink(hide).any(axis=0))[0]
    assert xs.min() == pytest.approx(196, abs=1.5) and xs.max() == pytest.approx(349, abs=1)


def test_path_split_by_polygon_in_canvas_space():
    p = bar()
    p.apply({"type": "path-split", "target": "bar", "space": "canvas",
             "polygon": [[100, 90], [180, 90], [180, 170], [100, 170]]})
    outside = p.layer("bar-b")
    assert p.layer("bar-a")["visible"]
    p.apply({"type": "hide", "target": "bar-b"})
    xs = np.nonzero(ink(p).any(axis=0))[0]
    assert xs.min() == pytest.approx(100, abs=1) and xs.max() == pytest.approx(179, abs=1)
    assert outside["path"].count("M") == 2  # the left stub and the right remainder


def test_path_split_errors_and_cli():
    p = bar()
    with pytest.raises(VixlError):
        p.apply({"type": "path-split", "target": "bar", "polygon": [[0, 0], [10, 0], [10, 10]],
                 "line": [[0, 0], [1, 1]]})
    with pytest.raises(VixlError):  # a polygon away from the shape cuts nothing off
        p.apply({"type": "path-split", "target": "bar", "space": "canvas",
                 "polygon": [[-500, -500], [-400, -500], [-400, -400]]})
    p = bar()
    p.apply({"type": "text", "text": "Hi", "name": "words"})
    with pytest.raises(VixlError):
        p.apply({"type": "path-split", "target": "words", "line": [[0, 0], [10, 0]]})
    op = compile_command(["path-split", "bar", "--line", "[[0,0],[10,10]]", "--overlap", "2", "--names", "a,b"])
    assert op == {"type": "path-split", "target": "bar", "line": [[0, 0], [10, 10]], "overlap": 2.0, "names": ["a", "b"]}
    validate_operation(op)
