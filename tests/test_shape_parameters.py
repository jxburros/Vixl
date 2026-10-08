"""Shape-specific parameters (#178) and shape content boxes (#187)."""

import io
import zipfile

import numpy as np
import pytest
import resvg_py
from PIL import Image

from vixl import Project, VixlError
from vixl.capabilities import lookup
from vixl.commands import compile_command
from vixl.geometry import SHORTCUTS, parse_path, path_polygons, shape_path
from vixl.shape_catalog import PARAMETRIC_SHORTCUTS, content_box
from vixl.vector_paths import pixel_path


def document(shape, w=200, h=120, **settings):
    p = Project(320, 240, "transparent")
    p.apply({"type": "shape", "shape": shape, "name": "s", "x": 40, "y": 40, "width": w, "height": h,
             "fill": "#2674a8", **settings})
    return p


def outline(p, name="s"):
    return [np.array(polygon) for polygon in path_polygons(pixel_path(p.layer(name), distort=False))]


def inside(polygons, x, y):
    winding = 0
    for pts in polygons:
        for (x0, y0), (x1, y1) in zip(pts, np.roll(pts, -1, axis=0)):
            cross = (x1 - x0) * (y - y0) - (x - x0) * (y1 - y0)
            if y0 <= y < y1 and cross > 0:
                winding += 1
            elif y1 <= y < y0 and cross < 0:
                winding -= 1
    return winding != 0


def alpha(p):
    return np.asarray(p.render())[:, :, 3] > 127


def svg_alpha(p):
    svg = p.export(format="SVG", svg_policy="strict").decode()
    return np.asarray(Image.open(io.BytesIO(resvg_py.svg_to_bytes(svg_string=svg))).convert("RGBA"))[:, :, 3] > 127


@pytest.mark.parametrize("kind", sorted(PARAMETRIC_SHORTCUTS))
def test_parametric_shortcut_defaults_reproduce_the_fixed_outline(kind):
    w, h = 140, 100
    generated = path_polygons(PARAMETRIC_SHORTCUTS[kind]({}, w, h))
    fixed = [[(x * w / 100, y * h / 100) for x, y in polygon] for polygon in path_polygons(SHORTCUTS[kind])]
    assert len(generated) == len(fixed)
    for a, b in zip(generated, fixed):
        assert np.allclose(a, b, atol=1e-4)


@pytest.mark.parametrize("kind, settings", [
    ("heart", {"apex": 0.5, "cleft": 0.2, "tip": 0.95}),
    ("speech-bubble", {"pointer_side": "bottom", "body": 0.75, "pointer_position": 0.2, "pointer_size": 0.25}),
    ("shield", {"depth": 0.55}),
    ("chevron", {"thickness": 0.4}),
    ("trapezoid", {"slant": 0.25}),
    ("parallelogram", {"slant": 0.25}),
    ("triangle", {"apex": 0.5}),
])
def test_explicit_default_parameters_render_like_the_plain_shape(kind, settings):
    plain, explicit = document(kind), document(kind, **settings)
    a, b = alpha(plain), alpha(explicit)
    assert (a ^ b).sum() <= 0.006 * a.sum()  # edge anti-aliasing only: the parametric path draws through the vector renderer


def extents(polygons):
    points = np.vstack(polygons)
    return points.min(axis=0), points.max(axis=0)


def test_heart_cleft_tip_and_lobe_balance():
    base = outline(document("heart"))
    deep = outline(document("heart", cleft=0.45, tip=0.7))
    lop = outline(document("heart", apex=0.3))
    assert extents(deep)[1][1] == pytest.approx(0.7 * 120, abs=0.5)
    # The cleft point sits on the vertical through the apex.
    assert inside(base, 100, 0.3 * 120) and not inside(deep, 100, 0.3 * 120)
    assert extents(lop)[1][1] == pytest.approx(extents(base)[1][1])
    tip_x = max(lop[0], key=lambda q: q[1])[0]
    assert tip_x == pytest.approx(0.3 * 200, abs=0.5)


@pytest.mark.parametrize("side", ["bottom", "top", "left", "right"])
def test_speech_bubble_tail_side_position_and_body(side):
    p = document("speech-bubble", pointer_side=side, pointer_position=0.5, body=0.7, pointer_size=0.2)
    polygons = outline(p)
    tip = {"bottom": (100, 119.9), "top": (100, 0.1), "left": (0.1, 60), "right": (199.9, 60)}[side]
    assert inside(polygons, *tip) or min(np.hypot(*(polygons[0] - tip).T)) < 1
    body = {"bottom": (100, 0.35 * 120), "top": (100, 120 - 0.35 * 120),
            "left": (200 - 0.35 * 200, 60), "right": (0.35 * 200, 60)}[side]
    assert inside(polygons, *body)
    corner = {"bottom": (5, 115), "top": (5, 5), "left": (5, 5), "right": (195, 5)}[side]
    assert not inside(polygons, *corner)


def test_shield_chevron_slant_triangle_and_tag_parameters_change_geometry():
    assert inside(outline(document("shield")), 10, 0.6 * 120)
    assert not inside(outline(document("shield", depth=0.8)), 10, 0.6 * 120)
    assert inside(outline(document("chevron")), 70, 10)
    assert not inside(outline(document("chevron", thickness=0.2)), 70, 10)
    assert not inside(outline(document("trapezoid", slant=0.4)), 70, 2)
    assert inside(outline(document("parallelogram", slant=0.1)), 30, 2)
    assert inside(outline(document("triangle", apex=0)), 2, 10)
    assert inside(outline(document("tag")), 50, 3) and not inside(outline(document("tag", depth=0.4)), 50, 3)
    rounded = outline(document("triangle", point_radius=20))
    assert not inside(rounded, 199, 119)


@pytest.mark.parametrize("settings", [
    {"shape": "heart", "apex": 0.35, "cleft": 0.35, "tip": 0.8},
    {"shape": "speech-bubble", "pointer_side": "right", "pointer_position": 0.7, "body": 0.8},
    {"shape": "shield", "depth": 0.3},
    {"shape": "trapezoid", "slant": 0.1},
])
def test_parameters_agree_across_raster_svg_pdf_and_pptx(settings):
    p = document(**settings)
    a, b = alpha(p), svg_alpha(p)
    assert (a & b).sum() / (a | b).sum() > 0.985
    assert p.export(format="PDF").startswith(b"%PDF")
    with zipfile.ZipFile(io.BytesIO(p.export(format="PPTX"))) as archive:
        assert b"custGeom" in archive.read("ppt/slides/slide1.xml")
    assert parse_path(shape_path(p.layer())[0])


def test_parameters_edit_in_place_validate_and_normalize():
    p = document("speech-bubble")
    ident = p.layer()["id"]
    result = p.apply({"type": "shape", "target": "s", "tail_side": "top", "body_ratio": 0.6, "tail_position": 0.8})
    assert p.layer()["id"] == ident
    assert p.layer()["pointer_side"] == "top" and p.layer()["body"] == 0.6 and p.layer()["pointer_position"] == 0.8
    assert any("tail_side" in note for note in result["normalized"])
    with pytest.raises(VixlError):
        p.apply({"type": "shape", "target": "s", "pointer_side": "middle"})
    assert p.layer()["pointer_side"] == "top"
    warned = p.apply({"type": "shape", "shape": "rectangle", "name": "r", "width": 10, "height": 10, "cleft": 0.3})
    assert any("cleft only shapes 'heart'" in text for text in warned["warnings"])


def test_capabilities_list_shape_parameters():
    info = lookup("shapes")
    assert "shapes" in info["topics"]
    assert set(info["shape_parameters"]["heart"]) == {"apex", "cleft", "tip"}
    assert "pointer_side" in info["shape_parameters"]["speech-bubble"]
    assert "content_bounds" in info["content_boxes"]


# Content boxes ------------------------------------------------------------------------------------------


@pytest.mark.parametrize("shape, settings, expected", [
    ("ellipse", {}, (100 - 100 / 2 ** 0.5, 60 - 60 / 2 ** 0.5, 200 / 2 ** 0.5, 120 / 2 ** 0.5)),
    ("speech-bubble", {}, (5, 3, 190, 84)),
    ("speech-bubble", {"pointer_side": "top", "body": 0.5}, (5, 63, 190, 54)),
    ("tag", {}, (44, 0, 156, 120)),
    ("callout", {}, (0, 0, 200, 96)),
    ("frame", {"thickness": 10}, (10, 10, 180, 100)),
    ("browser-window", {"thickness": 10}, (10, 20, 180, 90)),
    ("phone-frame", {"thickness": 12}, (12, 12, 176, 96)),
    ("banner", {}, (30, 21.6, 140, 76.8)),
])
def test_content_box_of_shape_families(shape, settings, expected):
    layer = document(shape, **settings).layer()
    assert content_box(layer) == pytest.approx(expected, abs=0.01)


@pytest.mark.parametrize("shape, settings", [
    ("rounded-rectangle", {"radius": 30}), ("capsule", {}), ("star", {}), ("polygon", {"sides": 6}),
    ("burst", {}), ("seal", {}), ("ring", {}), ("ticket", {}), ("stamp", {}), ("heart", {}), ("shield", {}),
    ("triangle", {}), ("diamond", {}), ("cloud", {}), ("trapezoid", {}), ("arrow", {}), ("hexagram", {}),
    ("heart", {"apex": 0.3, "cleft": 0.4}), ("speech-bubble", {"pointer_side": "left", "body": 0.6}),
    ("arc", {"inner_radius": 0.6}), ("polygon", {"sides": 3}),
    ("rounded-rectangle", {"radius": 30, "corner_style": "inverted"}),
])
def test_content_box_lies_inside_the_filled_outline(shape, settings):
    p = document(shape, **settings)
    layer = p.layer()
    x, y, w, h = content_box(layer)
    assert w > 0 and h > 0 and (w, h) != (layer["width"], layer["height"])
    if shape in ("ring", "arc"):
        return  # the content box is the hole, checked below
    polygons = outline(p)
    inset = 0.02 * min(w, h)
    for px, py in ((x + inset, y + inset), (x + w - inset, y + inset), (x + inset, y + h - inset),
                   (x + w - inset, y + h - inset), (x + w / 2, y + h / 2)):
        assert inside(polygons, px, py), (px, py)


def test_ring_content_box_is_the_opening():
    p = document("ring", w=200, h=200, thickness=20)
    x, y, w, h = content_box(p.layer())
    assert (x + w / 2, y + h / 2) == pytest.approx((100, 100))
    assert w == pytest.approx(160 / 2 ** 0.5)
    assert not inside(outline(p), x + w / 2, y + h / 2)


def test_plain_boxes_report_no_content_bounds():
    p = document("rectangle")
    assert "content_bounds" not in p.inspect("s")
    p.apply({"type": "shape", "shape": "line", "name": "l", "width": 50, "height": 2, "stroke": "black"})
    assert "content_bounds" not in p.inspect("l")


def test_inspect_and_results_report_canvas_content_bounds():
    p = Project(320, 240, "transparent")
    result = p.apply({"type": "shape", "shape": "speech-bubble", "name": "b", "x": 40, "y": 30, "width": 200,
                      "height": 120}, detail="brief")
    added = next(iter(result["changes"]["layers"].values()))
    assert added["content_bounds"] == [45.0, 33.0, 190.0, 84.0]
    assert p.inspect("b")["content_bounds"] == [45.0, 33.0, 190.0, 84.0]
    moved = p.apply({"type": "move", "target": "b", "x": 50, "y": 30}, detail="brief")
    assert next(iter(moved["changes"]["layers"].values()))["content_bounds"] == [55.0, 33.0, 190.0, 84.0]
    p.apply({"type": "flip", "target": "b", "direction": "vertical"})
    assert p.inspect("b")["content_bounds"] == [55.0, 63.0, 190.0, 84.0]
    p.apply([{"type": "flip", "target": "b", "direction": "vertical"}, {"type": "rotate", "target": "b", "value": 90}])
    x, y, w, h = p.inspect("b")["content_bounds"]
    bx, by, bw, bh = p.inspect("b")["canvas_bounds"]
    assert (w, h) == pytest.approx((84, 190))
    # The body sits away from the tail: after a quarter turn the tail points left.
    assert x + w / 2 > bx + bw / 2


def test_align_relative_to_content_centres_text_in_the_bubble_body():
    p = Project(320, 240, "transparent")
    p.apply([
        {"type": "shape", "shape": "speech-bubble", "name": "b", "x": 40, "y": 30, "width": 200, "height": 120},
        {"type": "text", "text": "Hi", "name": "t", "size": 20, "color": "black"},
        {"type": "align", "targets": ["t"], "relative_to": "b", "box": "content", "alignment": "center"},
    ])
    x, y, w, h = p.inspect("t")["resolved_bounds"]
    assert (x + w / 2, y + h / 2) == pytest.approx((140, 75), abs=0.6)
    p.apply({"type": "align", "targets": ["t"], "relative_to": "b", "alignment": "center"})
    x, y, w, h = p.inspect("t")["resolved_bounds"]
    assert y + h / 2 == pytest.approx(90, abs=0.6)
    with pytest.raises(VixlError) as error:
        p.apply({"type": "align", "target": "t", "box": "content", "alignment": "center"})
    assert error.value.details.get("field") == "box" or "relative_to" in str(error.value)


def test_place_within_and_text_within_use_the_content_box_through_groups():
    p = Project(320, 240, "transparent")
    p.apply([
        {"type": "shape", "shape": "speech-bubble", "name": "b", "x": 20, "y": 20, "width": 200, "height": 120,
         "pointer_side": "left", "body": 0.8},
        {"type": "group", "name": "g", "targets": ["b"]},
        {"type": "move", "target": "g", "x": 60, "y": 40},
        {"type": "text", "text": "Hello", "name": "t", "size": 18, "color": "black", "within": "b"},
    ])
    cx, cy, cw, ch = p.inspect("b")["content_bounds"]
    x, y, w, h = p.inspect("t")["canvas_bounds"]
    assert (x + w / 2, y + h / 2) == pytest.approx((cx + cw / 2, cy + ch / 2), abs=0.6)
    p.apply({"type": "place", "targets": ["t"], "within": "b", "anchor": "top-left", "margin": 6})
    x, y, *_ = p.inspect("t")["canvas_bounds"]
    assert (x, y) == pytest.approx((cx + 6, cy + 6), abs=0.6)
    p.apply({"type": "place", "targets": ["t"], "within": "b", "box": "bounds", "anchor": "bottom-right"})
    x, y, w, h = p.inspect("t")["canvas_bounds"]
    bx, by, bw, bh = p.inspect("b")["canvas_bounds"]
    assert (x + w, y + h) == pytest.approx((bx + bw, by + bh), abs=0.6)
    with pytest.raises(VixlError):
        p.apply({"type": "text", "text": "x", "within": "b", "x": 10})
    with pytest.raises(VixlError):
        p.apply({"type": "place", "targets": ["t"]})


def test_cli_align_place_and_text_take_content_boxes():
    op = compile_command("align title center --relative-to bubble --box content")
    op = op[0] if isinstance(op, list) else op
    assert op["box"] == "content" and op["relative_to"] == "bubble"
    assert compile_command("place line --within bubble --anchor top-left --margin 6") == {
        "type": "place", "target": "line", "within": "bubble", "anchor": "top-left", "margin": 6.0}
    assert compile_command("text add Hi --within bubble") == {"type": "text", "text": "Hi", "within": "bubble"}
    with pytest.raises(VixlError):
        compile_command("place line --within bubble --guide g")


def _pieces(image):
    """Separate filled regions in an image (4-connected)."""
    mask = np.asarray(image.getchannel("A")) > 128
    seen, pieces = np.zeros_like(mask), 0
    for start in zip(*np.nonzero(mask)):
        if seen[start]:
            continue
        pieces += 1
        stack = [start]
        seen[start] = True
        while stack:
            y, x = stack.pop()
            for ny, nx in ((y + 1, x), (y - 1, x), (y, x + 1), (y, x - 1)):
                if 0 <= ny < mask.shape[0] and 0 <= nx < mask.shape[1] and mask[ny, nx] and not seen[ny, nx]:
                    seen[ny, nx] = True
                    stack.append((ny, nx))
    return pieces


def test_confetti_scatters_count_seeded_pieces():
    p = Project(300, 300, "transparent")
    result = p.apply({"type": "shape", "shape": "confetti", "name": "c", "x": 10, "y": 10, "width": 250,
                      "height": 250, "fill": "orange", "count": 40, "seed": 3})
    assert not result.get("warnings")
    assert _pieces(p.render()) == 40
    again = Project(300, 300, "transparent")
    again.apply({"type": "shape", "shape": "confetti", "name": "c", "x": 10, "y": 10, "width": 250, "height": 250,
                 "fill": "orange", "count": 40, "seed": 3})
    assert again.render().tobytes() == p.render().tobytes()
    p.apply({"type": "shape", "target": "c", "seed": 4})
    assert p.render().tobytes() != again.render().tobytes()
    single = Project(300, 300, "transparent")
    single.apply({"type": "shape", "shape": "confetti", "name": "c", "width": 60, "height": 20, "fill": "orange"})
    assert _pieces(single.render()) == 1  # without count, one slip as before
