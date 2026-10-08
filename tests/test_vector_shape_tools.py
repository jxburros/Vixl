"""Catalog, stroke and path operations stay editable and agree across vector exports."""

import io

import numpy as np
import pytest
import resvg_py
from PIL import Image

from vixl import Project, VixlError
from vixl.geometry import parse_path, shape_path
from vixl.shape_catalog import KINDS
from vixl.vector_paths import path_nodes


def document(shape="rectangle", **settings):
    p = Project(300, 240, "transparent")
    p.apply(
        {
            "type": "shape",
            "shape": shape,
            "name": "s",
            "width": 140,
            "height": 100,
            "x": 70,
            "y": 70,
            "fill": "#2674a8",
            **settings,
        }
    )
    return p


def svg_image(p):
    svg = p.export(format="SVG", svg_policy="strict")
    assert b"<image" not in svg
    return np.asarray(Image.open(io.BytesIO(resvg_py.svg_to_bytes(svg_string=svg.decode()))).convert("RGBA"))


def assert_svg_agreement(p):
    a = np.asarray(p.render())[:, :, 3] > 127
    b = svg_image(p)[:, :, 3] > 127
    assert (a & b).sum() / max(1, (a | b).sum()) > 0.985


@pytest.mark.parametrize("kind", KINDS)
def test_catalog_is_editable_vector_geometry(kind):
    p = document(kind)
    assert p.layer()["shape"] == kind
    assert p.render().getbbox()
    data = p.export(format="SVG", svg_policy="strict")
    assert b"<path" in data and b"<image" not in data
    assert p.export(format="PDF").startswith(b"%PDF")
    ident = p.layer()["id"]
    p.apply({"type": "shape", "target": "s", "fill": "purple", "thickness": "12%"})
    assert p.layer()["id"] == ident
    assert parse_path(shape_path(p.layer())[0])


def test_corner_radii_css_order_and_styles_change_the_geometry():
    p = document("rounded-rectangle", radius=["40%", 0, 25, 0])
    alpha = np.asarray(p.render())[:, :, 3]
    assert alpha[70, 70] == 0 and alpha[70, 209] > 0
    assert alpha[169, 209] == 0 and alpha[169, 70] > 0
    assert_svg_agreement(p)
    paths = []
    for style in ("round", "chamfer", "inverted"):
        p.apply({"type": "shape", "target": "s", "corner_style": style})
        paths.append(shape_path(p.layer())[0])
        assert_svg_agreement(p)
    assert len(set(paths)) == 3


@pytest.mark.parametrize("style", ["triangle", "open", "concave", "round"])
def test_arrow_dimensions_and_heads_remain_parametric(style):
    p = document("arrow", head_length=30, head_width=70, shaft_width=16, heads="both", head_style=style)
    first = shape_path(p.layer())[0]
    p.apply({"type": "shape", "target": "s", "head_length": 45})
    assert shape_path(p.layer())[0] != first
    assert_svg_agreement(p)
    p.apply({"type": "shape", "target": "s", "curve": 0.2, "point_radius": 3})
    assert p.render().getbbox()
    assert_svg_agreement(p)


def test_star_rounding_and_rotation_offset():
    p = document("star", point_radius=9, valley_radius=3, rotation_offset=18)
    path = shape_path(p.layer())[0]
    assert "Q" in path
    p.apply({"type": "shape", "target": "s", "valley_radius": 8})
    assert path != shape_path(p.layer())[0]
    assert_svg_agreement(p)


@pytest.mark.parametrize("kind", ["ring", "frame", "gear", "tag", "lock", "info", "warning"])
def test_compound_catalog_holes_survive_conversion(kind):
    p = document(kind)
    before = np.asarray(p.render())[:, :, 3]
    p.apply({"type": "shape-to-path", "target": "s"})
    assert p.layer()["shape"] == "path"
    assert len(p.inspect("s")["path_nodes"]) >= 2
    assert np.array_equal(before, np.asarray(p.render())[:, :, 3])
    assert_svg_agreement(p)


def test_node_insertion_is_an_exact_bezier_split_and_history_undoes():
    p = document("path", path="M0 20 C20 0 90 100 140 20 L140 100 L0 100 Z")
    before = p.layer()["path"]
    old_image = np.asarray(p.render())
    p.apply({"type": "path-edit", "target": "s", "action": "insert", "index": 0, "fraction": 0.37})
    nodes = p.inspect("s")["path_nodes"][0]["nodes"]
    assert len(nodes) == 5 and "in" in nodes[1] and "out" in nodes[1]
    assert np.abs(old_image.astype(int) - np.asarray(p.render()).astype(int)).mean() < 0.1
    p.undo()
    assert p.layer()["path"] == before


def test_node_move_handles_corner_round_open_reverse_and_transaction_rollback():
    p = document("star", sides=5)
    p.apply({"type": "shape-to-path", "target": "s"})
    original = p.inspect("s")["path_nodes"][0]["nodes"][0]["point"]
    p.apply(
        {"type": "path-edit", "target": "s", "action": "move", "index": 0, "point": [3, 4], "relative": True}
    )
    assert p.inspect("s")["path_nodes"][0]["nodes"][0]["point"] == pytest.approx(
        [original[0] + 3, original[1] + 4], abs=0.001
    )
    p.apply({"type": "path-edit", "target": "s", "action": "smooth", "index": 1, "symmetric": True})
    p.apply(
        {
            "type": "path-edit",
            "target": "s",
            "action": "move-handle",
            "index": 1,
            "handle": "out",
            "point": [80, 30],
            "symmetric": True,
        }
    )
    n = p.inspect("s")["path_nodes"][0]["nodes"][1]
    assert [n["in"][j] + n["out"][j] for j in (0, 1)] == pytest.approx([2 * v for v in n["point"]], abs=0.002)
    p.apply({"type": "path-edit", "target": "s", "action": "corner", "index": 1})
    assert "in" not in p.inspect("s")["path_nodes"][0]["nodes"][1]
    p.apply({"type": "path-edit", "target": "s", "action": "round", "index": 2, "radius": 4})
    assert len(p.inspect("s")["path_nodes"][0]["nodes"]) == 11
    p.apply({"type": "path-edit", "target": "s", "action": "open"})
    assert not p.inspect("s")["path_nodes"][0]["closed"]
    p.apply({"type": "path-edit", "target": "s", "action": "reverse"})
    p.apply({"type": "path-edit", "target": "s", "action": "close"})
    before = p.inspect("s")
    with pytest.raises(VixlError):
        p.apply(
            [
                {"type": "path-edit", "target": "s", "action": "move", "point": [5, 5]},
                {"type": "path-edit", "target": "s", "action": "delete", "index": 999},
            ]
        )
    assert p.inspect("s") == before


def test_simplify_smooth_and_round_all_corners():
    p = document("path", path="M0 0 L20 0 L40 0 L60 0 L100 0 L100 100 L0 100 Z")
    p.apply({"type": "path-simplify", "target": "s", "tolerance": 0.5})
    assert len(path_nodes(p.layer()["path"])[0]["nodes"]) == 4
    p.apply({"type": "round-corners", "target": "s", "radius": 8})
    assert len(path_nodes(p.layer()["path"])[0]["nodes"]) == 8
    p.apply({"type": "path-smooth", "target": "s", "amount": 0.4})
    assert all("out" in n for n in path_nodes(p.layer()["path"])[0]["nodes"])


@pytest.mark.parametrize("join", ["miter", "bevel", "round"])
def test_offset_grows_and_shrinks_vector_outline(join):
    p = document()
    p.apply({"type": "offset-path", "target": "s", "distance": 10, "join": join})
    assert p.render().getbbox() == (60, 60, 220, 180)
    assert_svg_agreement(p)
    p = document()
    p.apply({"type": "offset-path", "target": "s", "distance": -10, "join": join})
    assert p.render().getbbox() == (80, 80, 200, 160)
    assert_svg_agreement(p)


@pytest.mark.parametrize(
    "alignment,expected",
    [("inside", (70, 70, 210, 170)), ("center", (65, 65, 215, 175)), ("outside", (60, 60, 220, 180))],
)
def test_stroke_alignment_extends_outside_layer_without_raster_clipping(alignment, expected):
    p = document(fill="transparent", stroke="red", stroke_width=10, stroke_align=alignment)
    assert p.render().getbbox() == expected
    assert_svg_agreement(p)
    p.apply({"type": "outline-stroke", "target": "s"})
    assert p.layer()["stroke_width"] == 0 and p.layer()["fill"] == "red"
    assert p.render().getbbox() == expected
    assert_svg_agreement(p)


def test_dash_phase_caps_profiles_markers_and_multiple_strokes():
    p = document(
        "path",
        path="M15 50 L125 50",
        fill="transparent",
        stroke="red",
        stroke_width=12,
        dash=[8, 4],
        line_cap="round",
        dash_offset=0,
    )
    a = np.asarray(p.render())
    p.apply({"type": "shape", "target": "s", "dash_offset": 5})
    assert not np.array_equal(a, np.asarray(p.render()))
    p.apply(
        {
            "type": "shape",
            "target": "s",
            "width_profile": [[0, 0], [0.4, 1], [1, 0.2]],
            "marker_end": "triangle",
            "marker_size": 20,
            "strokes": [{"color": "navy", "width": 2, "dash": "dotted", "line_cap": "round"}],
        }
    )
    assert_svg_agreement(p)
    assert p.export(format="PDF").startswith(b"%PDF")
    p.apply({"type": "outline-stroke", "target": "s"})
    assert len(p.state["layers"]) == 2


@pytest.mark.parametrize("mode", ["exclude", "minus-back", "divide", "trim", "merge"])
def test_new_pathfinder_modes_produce_real_geometry(mode):
    p = document(fill="red")
    p.apply(
        {
            "type": "shape",
            "shape": "rectangle",
            "name": "b",
            "width": 140,
            "height": 100,
            "x": 130,
            "y": 110,
            "fill": "blue",
        }
    )
    p.apply({"type": "pathfinder", "targets": ["s", "b"], "name": "result", "mode": mode})
    alpha = np.asarray(p.render())[:, :, 3]
    if mode == "exclude":
        assert alpha[120, 150] == 0 and alpha[90, 80] == 255
    elif mode == "minus-back":
        assert alpha[90, 80] == 0 and alpha[190, 250] == 255
    elif mode == "divide":
        assert len([item for item in p.state["layers"] if item.get("parent") == p.layer("result")["id"]]) == 3
    assert_svg_agreement(p)


@pytest.mark.parametrize("mode", ["divide", "trim"])
def test_pathfinder_pieces_abut_without_a_hairline_seam(mode):  # #362
    p = Project(300, 240, "#ffffff")
    p.apply([
        {"type": "shape", "shape": "rectangle", "name": "sq", "x": 40, "y": 40, "width": 140, "height": 140, "fill": "#1d4ed8"},
        {"type": "shape", "shape": "ellipse", "name": "ci", "x": 110, "y": 60, "width": 150, "height": 150, "fill": "#1d4ed8"},
    ])
    plain = np.asarray(p.render().convert("L"), dtype=int)
    p.apply({"type": "pathfinder", "targets": ["sq", "ci"], "mode": mode, "name": "parts"})
    image = np.asarray(p.render().convert("L"), dtype=int)
    fill = plain[100, 60]
    # Where the pieces meet the paint is solid; the white paper does not show through along the cut.
    assert image[60:170, 120:175].max() <= fill + 8, image[60:170, 120:175].max()
    # The pieces reach under each other only: no paint spreads past the outline of the whole.
    assert image[plain == 255].min() >= 250


@pytest.mark.parametrize(
    "kind",
    [
        "arc",
        "arch",
        "bulge",
        "flag",
        "wave",
        "fisheye",
        "inflate",
        "squeeze",
        "twist",
        "pucker",
        "bloat",
        "zig-zag",
    ],
)
def test_non_destructive_warps_remain_vector_and_removable(kind):
    p = document("star")
    before = p.layer().copy()
    original = np.asarray(p.render())
    p.apply(
        {"type": "distort", "target": "s", "kind": kind, "amount": 0.3, "angle": 80, "size": 4, "ridges": 5}
    )
    assert p.layer()["shape"] == before["shape"]
    assert not np.array_equal(original, np.asarray(p.render()))
    assert_svg_agreement(p)
    assert p.export(format="PDF").startswith(b"%PDF")
    p.apply({"type": "distort", "target": "s", "remove": True})
    assert np.array_equal(original, np.asarray(p.render()))


def test_corner_pin_and_group_distortion_move_children_together():
    p = document()
    p.apply(
        {
            "type": "distort",
            "target": "s",
            "kind": "corner-pin",
            "corners": [[0, 10], [140, 0], [120, 100], [20, 90]],
        }
    )
    assert_svg_agreement(p)
    p.apply({"type": "distort", "target": "s", "remove": True})
    p.apply(
        {
            "type": "shape",
            "shape": "ellipse",
            "name": "e",
            "width": 30,
            "height": 30,
            "x": 120,
            "y": 90,
            "fill": "red",
        }
    )
    p.apply({"type": "group", "name": "g", "targets": ["s", "e"]})
    ids = [item["id"] for item in p.state["layers"]]
    original = np.asarray(p.render())
    p.apply({"type": "distort", "target": "g", "kind": "wave", "amount": 0.15})
    assert ids == [item["id"] for item in p.state["layers"]]
    assert not np.array_equal(original, np.asarray(p.render()))
    assert_svg_agreement(p)
    assert p.export(format="PDF").startswith(b"%PDF")


def test_new_controls_reject_invalid_values_atomically():
    p = document()
    for settings in (
        {"radius": [1, 2]},
        {"dash": [0, 4]},
        {"width_profile": [[0, 1], [0.5, 1], [0.4, 2], [1, 1]]},
        {"exponent": 0},
        {"count": 10000},
    ):
        before = p.inspect("s")
        with pytest.raises(VixlError):
            p.apply({"type": "shape", "target": "s", **settings})
        assert p.inspect("s") == before


def test_dash_and_distortion_parameters_are_animatable():
    from vixl.timeline import project_at

    p = document(
        "path", path="M10 40 L130 40", fill="transparent", stroke="red", stroke_width=5, dash=[10, 5]
    )
    p.apply(
        [
            {"type": "distort", "target": "s", "kind": "wave", "amount": 0.1},
            {"type": "keyframe", "target": "s", "property": "dash_offset", "time": 0, "value": 0},
            {"type": "keyframe", "target": "s", "property": "dash_offset", "time": 1000, "value": 20},
            {"type": "keyframe", "target": "s", "property": "distort:amount", "time": 0, "value": 0.1},
            {"type": "keyframe", "target": "s", "property": "distort:amount", "time": 1000, "value": 0.5},
        ]
    )
    middle = project_at(p, 500)
    assert middle.layer("s")["dash_offset"] == pytest.approx(10)
    assert middle.layer("s")["distort"]["amount"] == pytest.approx(0.3)


def test_trim_composes_with_dashes_and_stays_vector_in_pdf():
    p = document(
        "path",
        path="M10 50 L130 50",
        fill="transparent",
        stroke="navy",
        stroke_width=8,
        dash=[8, 4],
        trim_start=25,
        trim_end=75,
        line_cap="butt",
    )
    alpha = np.asarray(p.render())[:, :, 3]
    assert alpha[120, 80] == 0 and alpha[120, 190] == 0
    assert alpha[120, 110:170].sum() > 0
    assert_svg_agreement(p)
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(p.export(format="PDF")))
    assert not reader.pages[0].images


def test_zero_width_dash_is_empty_and_dashed_inside_stays_inside():
    p = document(stroke="red", stroke_width=0, dash="dotted", fill="transparent")
    assert p.render().getbbox() is None
    p = document(stroke="red", stroke_width=8, dash=[8, 4], stroke_align="inside", fill="transparent")
    bounds = p.render().getbbox()
    assert bounds[0] >= 70 and bounds[1] >= 70 and bounds[2] <= 210 and bounds[3] <= 170
    assert_svg_agreement(p)


def test_fractional_shape_with_outside_stroke_matches_native_geometry():
    p = document(
        "rounded-rectangle",
        width=140.5,
        height=100.75,
        radius=[8, 20, 0, 0],
        stroke="red",
        stroke_width=4,
        stroke_align="outside",
    )
    assert_svg_agreement(p)


def test_offset_collapse_is_rejected_and_concave_inset_can_split():
    p = document(width=100, height=100)
    before = p.inspect("s")
    for distance in (-50, -60, -200):
        with pytest.raises(VixlError, match="collapses"):
            p.apply({"type": "offset-path", "target": "s", "distance": distance})
        assert p.inspect("s") == before
    p = document("path", path="M0 0 H50 V45 H90 V0 H140 V100 H90 V55 H50 V100 H0 Z")
    p.apply({"type": "offset-path", "target": "s", "distance": -6, "join": "round"})
    assert len(path_nodes(p.layer()["path"])) == 2
    assert_svg_agreement(p)


def test_offset_preserves_holes_and_can_close_them():
    p = document("ring", thickness=10)
    p.apply({"type": "offset-path", "target": "s", "distance": 5})
    assert len(path_nodes(p.layer()["path"])) == 2
    assert np.asarray(p.render())[120, 140, 3] == 0
    assert_svg_agreement(p)
    p = document("ring", thickness=10)
    p.apply({"type": "offset-path", "target": "s", "distance": 70})
    assert len(path_nodes(p.layer()["path"])) == 1
    assert np.asarray(p.render())[120, 140, 3] == 255


def test_path_and_warp_records_survive_save_load(tmp_path):
    p = document("gear", teeth=11, depth=8, hole=20)
    p.apply(
        [
            {"type": "shape-to-path", "target": "s"},
            {
                "type": "path-edit",
                "target": "s",
                "action": "move",
                "index": 0,
                "point": [1, 2],
                "relative": True,
            },
            {"type": "shape", "target": "s", "stroke": "navy", "stroke_width": 3, "dash": [7, 3]},
            {"type": "distort", "target": "s", "kind": "bulge", "amount": 0.2},
        ]
    )
    before = np.asarray(p.render())
    file = tmp_path / "vectors.vixl"
    p.save(file)
    restored = Project.load(file)
    assert restored.inspect("s")["path_nodes"] == p.inspect("s")["path_nodes"]
    assert np.array_equal(before, np.asarray(restored.render()))
