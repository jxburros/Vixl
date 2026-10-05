"""Composable organic shapes: generators, rules, presets, regrowth and interfaces."""

import json

import numpy as np
import pytest

from vixl import Project
from vixl.errors import VixlError
from vixl.organic import PRESETS, build_parts, catalog
from vixl import trace


def form(parts, **extra):
    p = Project(300, 300, "white")
    p.apply([{"type": "organic", "name": "form", "parts": parts, "width": 260, "height": 260, "x": 20, "y": 20, **extra}])
    return p


def ink(image):
    return np.asarray(image.convert("L")) < 200


@pytest.mark.parametrize("preset", sorted(PRESETS))
def test_every_preset_draws_editable_paths(preset):
    p = Project(160, 160, "white")
    p.apply([{"type": "organic", "preset": preset, "name": "it", "width": 140, "height": 140, "x": 10, "y": 10}])
    top = p.layer("it")
    assert top["organic"]["preset"] == preset
    shapes = [layer for layer in p.state["layers"] if layer["type"] == "shape"]
    assert shapes and all(layer["shape"] == "path" for layer in shapes)
    assert ink(p.render()).sum() > 50


def test_seed_is_deterministic_and_regrowth_keeps_identity():
    a = Project(200, 200)
    b = Project(200, 200)
    for p in (a, b):
        p.apply([{"type": "organic", "preset": "starfish", "name": "star", "seed": 4, "width": 180, "height": 180}])
    assert a.layer("star/body")["path"] == b.layer("star/body")["path"]
    ident = a.layer("star")["id"]
    a.apply([{"type": "organic", "target": "star", "seed": 5}])
    assert a.layer("star")["id"] == ident and a.layer("star")["organic"]["seed"] == 5
    assert a.layer("star/body")["path"] != b.layer("star/body")["path"]
    # Regrowing keeps colors the user changed on the parts.
    a.layer("star/body")["fill"] = "#123456"
    a.apply([{"type": "organic", "target": "star", "seed": 6}])
    assert a.layer("star/body")["fill"] == "#123456"
    single = Project(100, 100)
    single.apply([{"type": "organic", "name": "leafy", "parts": [{"generator": "blob"}], "width": 80}])
    layer = single.layer("leafy")
    assert layer["type"] == "shape" and layer["width"] == 80 and 40 < layer["height"] < 120
    before = single.layer("leafy")["path"]
    single.apply([{"type": "organic", "target": "leafy", "seed": 9}])
    assert single.layer("leafy")["path"] != before


def test_radial_whorls_alternate_and_mirror_does_not_cancel():
    built = build_parts([{"name": "p", "generator": "petal", "rules": [
        {"rule": "transform", "scale": 0.4}, {"rule": "radial", "count": 5, "radius": 0.2, "rings": 2}]}], 0, 0.5)
    assert len(built[0][1].elements()) == 10
    # Two overlapping, mirrored halves: the overlap stays filled (no nonzero-winding hole).
    p = form([{"name": "half", "generator": "ellipse", "params": {"aspect": 0.6},
               "rules": [{"rule": "transform", "translate": [0.25, 0]}, {"rule": "mirror", "axis": "x", "asymmetry": 0}],
               "fill": "black"}])
    image = p.render()
    assert image.getpixel((150, 150))[:3] == (0, 0, 0)


def test_along_follows_a_tentacle_spine_and_at_uses_anchors():
    built = build_parts([
        {"name": "stem", "generator": "tentacle", "params": {"curl": 0.6, "wave": 0, "wobble": 0}},
        {"name": "leaves", "generator": "leaf", "rules": [{"rule": "along", "spine": "part:stem", "count": 6,
                                                           "side": "alternate", "scale": 0.2}]},
        {"name": "tree", "generator": "branch", "params": {"depth": 4}},
        {"name": "fruit", "generator": "ellipse", "rules": [{"rule": "at", "anchors": "tree.tips", "scale": 0.03}]},
    ], 1, 0.5)
    parts = dict((spec["name"], shape) for spec, shape in built)
    spine = np.array([(x, y) for x, y, _ in parts["stem"].anchors["spine"]])
    for leaf in parts["leaves"].tags["shape"]:
        base = leaf["points"][0]
        assert np.min(np.hypot(*(spine - base).T)) < 0.05
    assert len(parts["fruit"].tags["shape"]) == len(parts["tree"].anchors["tips"]) == 2 ** 3


def test_blend_occlude_and_intersect_run_in_pixels():
    p = form([{"name": "pair", "generator": "ellipse",
               "rules": [{"rule": "transform", "scale": 0.4},
                         {"rule": "along", "spine": [[-0.3, 0], [0.3, 0]], "count": 2, "side": "center", "scale": 1},
                         {"rule": "blend", "radius": 0.05}]}])
    path = p.layer("form")["path"]
    assert path.count("M") == 1          # two overlapping circles became one outline
    q = form([{"name": "scales", "generator": "scales", "params": {"rows": 3, "columns": 3},
               "rules": [{"rule": "occlude", "gap": 2}]}])
    assert q.layer("form")["path"].count("M") >= 9
    r = form([{"name": "dome", "generator": "ellipse", "rules": [{"rule": "intersect", "half": "top"}], "fill": "black"}])
    image = r.render()
    assert image.getpixel((150, 60))[:3] == (0, 0, 0) and image.getpixel((150, 240))[:3] == (255, 255, 255)


def test_generators_cover_patterns_cells_and_lsystems():
    built = build_parts([
        {"name": "rd", "generator": "pattern", "params": {"kind": "stripes", "grid": 64, "steps": 1500}},
        {"name": "cells", "generator": "cells", "params": {"count": 20, "within": "square"}},
        {"name": "fern", "generator": "lsystem", "params": {"iterations": 3}},
        {"name": "seeds", "generator": "phyllotaxis", "params": {"count": 55}},
        {"name": "sf", "generator": "superformula", "params": {"m": 6, "n1": 1, "n2": 1, "n3": 1}},
        {"name": "shell", "generator": "shell", "params": {"chambers": 6}},
    ], 2, 0.5)
    parts = {spec["name"]: shape for spec, shape in built}
    assert parts["rd"].elements() and 10 <= len(parts["cells"].tags["shape"]) <= 20
    assert len(parts["seeds"].tags["shape"]) == 55
    assert len(parts["shell"].tags["chambers"]) == 7
    outline = parts["sf"].tags["shape"][0]["points"]
    assert abs(np.hypot(*outline.T).max() - 1) < 1e-6


def test_errors_name_the_field():
    with pytest.raises(VixlError) as error:
        form([{"generator": "unicorn"}])
    assert error.value.details["field"] == "parts[0].generator"
    with pytest.raises(VixlError) as error:
        form([{"generator": "leaf", "params": {"shpe": "ovate"}}])
    assert "shpe" in str(error.value)
    with pytest.raises(VixlError) as error:
        form([{"generator": "blob", "rules": [{"rule": "radial", "count": 5000}]}])
    assert error.value.details.get("field") == "parts[0].rules[0].count"
    p = Project(100, 100)
    with pytest.raises(VixlError) as error:
        p.apply([{"type": "organic", "preset": "flower", "colors": {"leafs": "red"}}])
    assert "leafs" in str(error.value)
    with pytest.raises(VixlError):
        p.apply([{"type": "organic", "parts": [{"generator": "blob", "rules": [{"rule": "at", "anchors": "nope.tips"}]}]}])


def test_svg_export_is_vector_and_paths_allow_large_forms():
    p = Project(300, 300)
    p.apply([{"type": "organic", "preset": "sunflower", "name": "sun", "width": 280, "height": 280}])
    svg = p.export(format="SVG")
    assert b"<image" not in svg and svg.count(b"<path") >= 3
    from vixl.geometry import parse_path

    assert len(parse_path(" ".join(f"M{i} 0 L{i} 1" for i in range(3000)))) == 6000


def test_cli_compiles_presets_and_catalog_is_discoverable(tmp_path):
    from vixl.commands import compile_command
    from vixl.workflows import dispatch
    from vixl.interfaces import Session

    op = compile_command(["organic", "flower", "--set", "petals=8", "--color", "petals=#ffffff", "--seed", "3", "--width", "200"])
    assert op == {"type": "organic", "preset": "flower", "seed": 3, "width": 200, "params": {"petals": 8},
                  "colors": {"petals": "#ffffff"}}
    info = catalog()
    assert {"flower", "tree", "starfish"} <= set(info["presets"]) and "superformula" in info["generators"]
    assert "occlude" in info["rules"]
    assert dispatch(Session(workspace=tmp_path), "organic-catalog", {})["presets"]["fern"]
    from vixl.cli import dispatch as cli

    result, _ = cli(["organics"])
    assert "phyllotaxis" in json.dumps(result)


def test_contours_keep_holes_and_close():
    yy, xx = np.mgrid[0:120, 0:120]
    r = np.hypot(xx - 60, yy - 60)
    loops = trace.contours(((r < 50) & (r > 20)).astype(float))
    areas = sorted(trace.area(loop) for loop in loops)
    assert len(loops) == 2 and areas[0] < 0 < areas[1]
    assert abs(areas[1] - np.pi * 50 ** 2) / (np.pi * 50 ** 2) < 0.02
