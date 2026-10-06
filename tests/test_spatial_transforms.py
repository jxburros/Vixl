import math
import pytest
import numpy as np
from vixl import Project
from vixl.affine import layer_matrix
from vixl.render import resolve_layout
from vixl.spatial import query, canvas_boxes


def shape(p, name="a", x=20, y=30, w=40, h=20):
    p.apply(
        {
            "type": "shape",
            "shape": "rectangle",
            "name": name,
            "x": x,
            "y": y,
            "width": w,
            "height": h,
            "fill": "red",
        }
    )
    return p.layer(name)


def anchor_point(p, name, fraction):
    layer = p.layer(name)
    return layer_matrix(layer, resolve_layout(p)[layer["id"]]) @ [
        fraction[0] * layer["width"],
        fraction[1] * layer["height"],
        1,
    ]


def test_fractional_size_scale_and_exports(tmp_path):
    p = Project(200, 100)
    shape(p, w=40.25, h=20.125, x=20.375, y=10.625)
    p.apply({"type": "scale", "target": "a", "value": 1.01})
    p.apply({"type": "scale", "target": "a", "value": 1 / 1.01})
    assert p.layer("a")["width"] == pytest.approx(40.25)
    assert resolve_layout(p)[p.layer("a")["id"]][:2] == (20.375, 10.625)
    p.render()
    p.export(tmp_path / "s.svg")
    assert "40.25" in (tmp_path / "s.svg").read_text()
    p.export(tmp_path / "s.pdf", pdf_content="vector")
    assert (tmp_path / "s.pdf").stat().st_size > 100


@pytest.mark.parametrize("kind", ["text", "rich-text"])
@pytest.mark.parametrize("grouped", [False, True])
def test_spatial_ink_uses_text_outlines_in_canvas_coordinates(kind, grouped):
    from vixl.affine import corners, envelope
    from vixl.checks import group_matrix
    from vixl.render import resolved_layers
    from vixl.text_metrics import inspect_text

    p = Project(500, 300)
    content = {"text": "Hi"} if kind == "text" else {"spans": [{"text": "Hi"}], "width": 200, "height": 100}
    p.apply({"type": kind, "name": "label", "x": 60, "y": 80, "size": 24, **content})
    if kind == "text":
        p.apply({"type": "text-layout", "target": "label", "width": 200, "height": 100})
    if grouped:
        p.apply(
            [
                {"type": "group", "name": "g", "targets": ["label"]},
                {"type": "scale", "target": "g", "x": 1.25, "y": 0.8},
                {"type": "rotate", "target": "g", "value": 23},
                {"type": "skew", "target": "label", "x": 12},
            ]
        )
    layers = resolved_layers(p)
    index = {layer["id"]: layer for layer in layers}
    label = index[p.layer("label")["id"]]
    local = resolve_layout(p, layers=layers)
    box = local[label["id"]]
    ink = inspect_text(p, label, box)["ink_bounds"]
    transform = group_matrix(label, index, local) @ layer_matrix(label, box)
    expected = envelope(corners((ink[0] - box[0], ink[1] - box[1], *ink[2:]), transform))
    actual = p.spatial(target="label", bounds="ink")["layers"][0]["bounds"]
    assert actual == pytest.approx(expected)
    layout = p.spatial(target="label", bounds="box")["layers"][0]["bounds"]
    assert actual[2] * actual[3] < layout[2] * layout[3] / 4


@pytest.mark.parametrize("rotation", [0, 31, 90, 225])
@pytest.mark.parametrize("fraction", [[0, 0], [0.5, 0.5], [1, 1], [0.3, 0.9]])
def test_anchor_stays_fixed_under_rotation_and_pivot(rotation, fraction):
    p = Project(600, 600)
    shape(p, x=200, y=200)
    p.apply(
        [
            {"type": "pivot", "target": "a", "value": [0.2, 0.8]},
            {"type": "rotate", "target": "a", "value": rotation},
        ]
    )
    before = anchor_point(p, "a", fraction)
    p.apply({"type": "resize", "target": "a", "width": 90.5, "height": 32.25, "anchor": fraction})
    assert anchor_point(p, "a", fraction) == pytest.approx(before)
    p.apply({"type": "scale", "target": "a", "x": -0.5, "y": 1.3, "anchor": fraction})
    assert anchor_point(p, "a", fraction) == pytest.approx(before)


def test_relative_match_and_fit():
    p = Project(500, 500)
    shape(p)
    shape(p, "b", w=80, h=100)
    p.apply({"type": "resize", "target": "a", "width": "+8", "height": "-5%"})
    assert (p.layer("a")["width"], p.layer("a")["height"]) == (48, 19)
    p.apply({"type": "match-size", "targets": ["a"], "to": "b", "axis": "width"})
    assert (p.layer("a")["width"], p.layer("a")["height"]) == (80, 19)
    p.apply({"type": "fit", "target": "a", "box": [100, 100, 160, 160], "mode": "contain"})
    assert canvas_boxes(p)[p.layer("a")["id"]] == pytest.approx((100, 161, 160, 38))
    p.apply({"type": "fit", "target": "a", "box": "b", "mode": "stretch"})
    assert canvas_boxes(p)[p.layer("a")["id"]] == pytest.approx(canvas_boxes(p)[p.layer("b")["id"]])


def test_nested_canvas_move_roundtrip_and_warning():
    p = Project(500, 500)
    shape(p, x=200, y=200)
    p.apply(
        [
            {"type": "group", "name": "inner", "targets": ["a"]},
            {"type": "group", "name": "outer", "targets": ["inner"]},
            {"type": "rotate", "target": "outer", "value": 25},
            {"type": "scale", "target": "outer", "x": 2, "y": 0.5},
        ]
    )
    p.apply({"type": "move", "target": "a", "space": "canvas", "x": 70.25, "y": 80.75})
    assert canvas_boxes(p)[p.layer("a")["id"]][:2] == pytest.approx((70.25, 80.75))
    p.apply(
        {"type": "move", "target": "a", "space": "canvas", "relative": True, "x": 1, "y": -1, "step": 0.25}
    )
    assert canvas_boxes(p)[p.layer("a")["id"]][:2] == pytest.approx((70.5, 80.5))
    result = p.apply({"type": "move", "target": "a", "space": "canvas", "x": 2000, "y": 2000})
    assert any("entirely outside" in warning for warning in result["warnings"])


def test_skew_matrix_native_render_and_timeline(tmp_path):
    p = Project(300, 300)
    shape(p, x=100, y=100, w=50, h=30)
    p.apply([{"type": "pivot", "target": "a", "value": "center"}, {"type": "skew", "target": "a", "x": 30}])
    assert resolve_layout(p)[p.layer("a")["id"]][2] == pytest.approx(50 + 30 / math.sqrt(3))
    p.render()
    p.export(tmp_path / "skew.svg")
    xml = (tmp_path / "skew.svg").read_text()
    assert "matrix(" in xml and "<image" not in xml
    p.export(tmp_path / "skew.pdf", pdf_content="vector")
    p.apply({"type": "transform", "target": "a", "matrix": [2, 0, 0.5, 3, 5, 8]})
    layer = p.layer("a")
    assert layer["width"] == 100 and layer["height"] == 90
    from vixl.affine import linear

    assert (linear(layer)[:2, :2] @ np.diag([2, 3])) == pytest.approx(np.array([[2, 0.5], [0, 3]]))
    p.apply({"type": "animate", "target": "a", "property": "skew_y", "from": 0, "to": 20, "duration": 1000})
    from vixl.timeline import project_at

    mid = project_at(p, 500)
    assert mid.layer("a")["skew_y"] == pytest.approx(10)


def test_relationships_grid_guides_composition_hits_free_and_snaps():
    p = Project(300, 200)
    shape(p, "a", x=20, y=30, w=40, h=20)
    shape(p, "b", x=80, y=30, w=40, h=20)
    p.apply(
        [
            {"type": "grid", "name": "layout", "columns": 3, "rows": 2},
            {"type": "guide", "name": "left", "axis": "x", "position": 22},
        ]
    )
    result = query(p, target="a", to="b", describe=True)
    r = result["relations"][0]
    assert r["horizontal_gap"] == 20 and r["nearest_edge_distance"] == 20
    assert "left-of" in r["positions"] and r["alignments"] == ["top", "center-y", "bottom"]
    assert "20 px gap" in result["layers"][0]["description"]
    all_info = query(p, target="a", mode="all")["layers"][0]
    assert all_info["grid"]["columns"]["occupied"] == [1]
    assert all_info["canvas"]["edges"]["right"] == 240
    assert all_info["composition"]["center"]["points"][0]["point"] == [150, 100]
    assert query(p, point=[25, 35], mode="hit")["hits"][0]["name"] == "a"
    shape(p, "cover", x=25, y=35, w=30, h=10)
    assert [v["name"] for v in query(p, point=[30, 40], mode="hit")["hits"]] == ["cover", "a"]
    p.apply({"type": "hide", "target": "cover"})
    assert [v["name"] for v in query(p, point=[30, 40], mode="hit")["hits"]] == ["a"]
    free = query(p, mode="free")["rectangles"]
    assert free and free[0]["area"] >= 300 * 150
    snap = query(p, target="a", mode="snap", grid="layout")["layers"][0]["suggestions"]
    proposal = next(v for v in snap if v["to"] == "left")
    p.apply(proposal["operation"])
    assert query(p, target="a", mode="guides")["layers"][0]["guides"]["nearest"]["x"]["distance"] == 0


def test_spatial_selectors_and_group_coordinates():
    p = Project(200, 200)
    shape(p, "a-one")
    shape(p, "a-two", x=80)
    p.apply({"type": "group", "name": "g", "targets": ["a-one", "a-two"]})
    assert len(query(p, target="a-*")["layers"]) == 2
    assert len(query(p, target="group:g")["layers"]) == 2
    assert len(query(p, targets=[{"group": "g"}])["layers"]) == 2
    for entry in query(p, target="group:g", mode="canvas")["layers"]:
        assert entry["bounds"] == pytest.approx(p.inspect(entry["id"])["canvas_bounds"])


def test_pixel_snapping_and_field_rejection():
    p = Project(100, 100)
    shape(p, x=0.4, y=0.6, w=10.2, h=10.2)
    p.apply({"type": "snap-to-pixel", "target": "a", "value": True})
    assert resolve_layout(p)[p.layer("a")["id"]][:2] == (0, 1)
    p.apply({"type": "scale", "target": "a", "value": 1.1})
    assert p.layer("a")["width"] == 11


def test_canvas_center_and_fit_in_rotated_group():
    p = Project(400, 200)
    shape(p, x=30.25, y=20.75)
    p.apply(
        [{"type": "group", "name": "g", "targets": ["a"]}, {"type": "rotate", "target": "g", "value": 20}]
    )
    p.apply({"type": "move", "target": "a", "space": "canvas", "x": "center", "y": "center"})
    b = canvas_boxes(p)[p.layer("a")["id"]]
    assert (b[0] + b[2] / 2, b[1] + b[3] / 2) == pytest.approx((200, 100))
    p.apply({"type": "fit", "target": "a", "box": [50, 20, 80, 120], "mode": "cover"})
    b = canvas_boxes(p)[p.layer("a")["id"]]
    assert b[2] >= 80 - 1e-8 and b[3] >= 120 - 1e-8
    assert (b[0] + b[2] / 2, b[1] + b[3] / 2) == pytest.approx((90, 80))


def test_native_skew_matches_raster_and_fractional_coverage():
    import io
    import resvg_py
    from PIL import Image

    p = Project(200, 200)
    shape(p, x=50.25, y=60.75, w=50.25, h=30.5)
    p.apply({"type": "skew", "target": "a", "x": 25, "y": 10})
    raster = np.asarray(p.render())[:, :, 3] > 128
    svg_bytes = resvg_py.svg_to_bytes(svg_string=p.export(format="SVG").decode())
    native = np.asarray(Image.open(io.BytesIO(svg_bytes)).convert("RGBA"))[:, :, 3] > 128
    assert (raster & native).sum() / (raster | native).sum() > 0.95
    p = Project(20, 20)
    shape(p, x=5.25, y=5, w=0.25, h=5)
    alpha = np.asarray(p.render())[:, :, 3]
    assert 0 < alpha.sum() < 255 * 5


def test_document_snap_override_and_animated_fractional_sizes():
    from vixl.timeline import project_at

    p = Project(100, 100)
    shape(p, x=0.4, y=0.6, w=10.25, h=20.25)
    p.apply({"type": "snap-to-pixel", "scope": "document", "value": True})
    assert resolve_layout(p)[p.layer("a")["id"]] == (0, 1, 10, 20)
    p.apply({"type": "snap-to-pixel", "target": "a", "value": False})
    assert resolve_layout(p)[p.layer("a")["id"]] == (0.4, 0.6, 10.25, 20.25)
    p.apply(
        {"type": "animate", "target": "a", "property": "width", "from": 10.25, "to": 11.25, "duration": 1000}
    )
    assert project_at(p, 500).layer("a")["width"] == pytest.approx(10.75)
    p.apply({"type": "animate", "target": "a", "property": "skew-x", "to": 20, "duration": 1000})
    assert project_at(p, 500).layer("a")["skew_x"] == pytest.approx(10)


def test_hit_ink_holes_region_and_group_opacity():
    p = Project(200, 200)
    p.apply(
        {
            "type": "shape",
            "name": "a",
            "shape": "ellipse",
            "x": 30,
            "y": 30,
            "width": 100,
            "height": 100,
            "fill": "red",
        }
    )
    assert query(p, mode="hit", point=[31, 31], bounds="box")["hits"]
    assert not query(p, mode="hit", point=[31, 31], bounds="ink")["hits"]
    assert query(p, mode="hit", region=[70, 70, 2, 2], bounds="ink")["hits"]
    p.apply(
        [
            {"type": "group", "name": "g", "targets": ["a"]},
            {"type": "opacity", "target": "g", "value": 0.5},
            {"type": "opacity", "target": "a", "value": 0.5},
        ]
    )
    hits = query(p, mode="hit", point=[80, 80])["hits"]
    assert hits[0]["name"] == "a" and hits[0]["opacity"] == 0.25


def test_query_page_artboard_and_safe_insets():
    p = Project(200, 200)
    shape(p, x=20, y=30)
    p.apply({"type": "artboard", "name": "crop", "x": 10, "y": 10, "width": 100, "height": 100})
    entry = query(p, target="a", mode="canvas", artboard="crop", safe_area={"left": 5, "top": 10})["layers"][
        0
    ]
    assert entry["canvas"]["safe_area"]["left"] == 5
    assert entry["canvas"]["safe_area"]["top"] == 10
    p.apply({"type": "page", "action": "add", "name": "second"})
    shape(p, "other", x=100, y=100)
    assert query(p, target="other", page="second")["layers"][0]["name"] == "other"


def test_invalid_transforms_are_atomic_and_fields_upright():
    from vixl.errors import VixlError

    p = Project(200, 200)
    shape(p)
    before = p.inspect("a")
    for op in [
        {"type": "skew", "x": 45, "y": 45},
        {"type": "transform", "matrix": [0, 0, 0, 0, 0, 0]},
        {"type": "resize", "width": "-110%"},
    ]:
        with pytest.raises(VixlError):
            p.apply({"target": "a", **op})
        assert p.inspect("a") == before
    p.apply(
        {
            "type": "field",
            "kind": "text",
            "name": "f",
            "key": "f",
            "label": "Field",
            "width": 80,
            "height": 25,
        }
    )
    with pytest.raises(VixlError, match="upright"):
        p.apply({"type": "skew", "target": "f", "x": 10})
    with pytest.raises(VixlError, match="upright"):
        p.apply(
            {"type": "animate", "target": "f", "property": "skew_y", "from": 0, "to": 20, "duration": 1000}
        )


def test_snap_resize_suggestions_apply_without_mutating_query():
    p = Project(300, 200)
    shape(p, x=20, y=30)
    p.apply(
        [
            {"type": "grid", "name": "z-first", "columns": 3, "rows": 2},
            {"type": "grid", "name": "a-active", "columns": 6, "rows": 4},
            {"type": "guide", "name": "right", "axis": "x", "position": 62},
        ]
    )
    before = p.inspect()
    assert p.spatial(target="a", mode="grid")["layers"][0]["grid"]["name"] == "a-active"
    suggestions = p.spatial(target="a", mode="snap", grid="a-active")["layers"][0]["suggestions"]
    assert p.inspect() == before
    assert any(item.get("kind") == "resize" for item in suggestions)
    for item in suggestions:
        p.clone().apply(item["operation"])


@pytest.mark.parametrize("pivot", [None, [0.2, 0.8]])
@pytest.mark.parametrize("flipped", [False, True])
def test_skew_keeps_the_current_pivot_of_rotated_artwork(pivot, flipped):
    p = Project(400, 400)
    shape(p, x=100, y=100, w=100, h=40)
    p.apply({"type": "rotate", "target": "a", "value": 30})
    if pivot is not None:
        p.apply({"type": "pivot", "target": "a", "value": pivot})
    if flipped:
        p.apply({"type": "flip", "target": "a", "direction": "horizontal"})
    fixed = pivot or [0.5, 0.5]
    before = anchor_point(p, "a", fixed)
    p.apply({"type": "skew", "target": "a", "x": 20})
    assert anchor_point(p, "a", fixed) == pytest.approx(before)
