"""Regressions for the bugs and slow paths found while building the ten explorations."""

import io
import threading
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from vixl import Project


def ink(image, threshold=128):
    """Pixels darker than ``threshold`` on a light render."""
    return np.asarray(image.convert("L")) < threshold


# Groups and effects draw past their layout box -------------------------------------------------


def test_resized_child_is_not_clipped_by_its_group():
    p = Project(20, 20, "white")
    p.apply([
        {"type": "pixel-art", "name": "a", "rows": ["#.", ".#"], "palette": {"#": "black", ".": "transparent"}},
        {"type": "pixel-art", "name": "b", "rows": ["#"], "palette": {"#": "red"}, "x": 2, "y": 2},
        {"type": "group", "name": "g", "targets": ["a", "b"]},
        {"type": "resize", "target": "a", "width": 8, "height": 8},
    ])
    # The full 8×8 checkerboard (32 dark pixels, one under the red 1×1), not the old 3×3 box.
    assert ink(p.render(), 50).sum() == 31
    group = p.inspect("g")
    assert group["resolved_bounds"] == (0, 0, 3, 3)
    assert group["drawn_bounds"] == (0, 0, 8, 8)


def test_scaled_pixel_group_stays_crisp():
    p = Project(20, 20, "white")
    p.apply([
        {"type": "pixel-art", "name": "a", "rows": ["#.", ".#"], "palette": {"#": "black", ".": "red"}},
        {"type": "group", "name": "g", "targets": ["a"]},
        {"type": "scale", "target": "g", "value": 4},
    ])
    assert len(set(p.render().get_flattened_data())) == 3


def test_animated_nested_limb_stays_visible():
    from vixl.timeline import project_at

    p = Project(400, 400, "white")
    p.apply([
        {"type": "shape", "shape": "rectangle", "name": "upper", "width": 30, "height": 90, "x": 185, "y": 100, "fill": "blue"},
        {"type": "shape", "shape": "rectangle", "name": "lower", "width": 30, "height": 90, "x": 185, "y": 190, "fill": "red"},
        {"type": "group", "name": "forearm", "targets": ["lower"]},
        {"type": "group", "name": "arm", "targets": ["upper", "forearm"]},
        {"type": "pivot", "target": "forearm", "value": [0.5, 0]},
        {"type": "keyframe", "target": "forearm", "property": "rotation", "time": 0, "value": 0},
        {"type": "keyframe", "target": "forearm", "property": "rotation", "time": 1000, "value": 90},
    ])
    for time in (0, 500, 1000):
        image = np.asarray(project_at(p, time).render().convert("RGB"))
        red = ((image[:, :, 0] > 200) & (image[:, :, 1] < 60)).sum()
        assert red > 2500, time  # 30 × 90 forearm, whole at every angle.


@pytest.mark.parametrize("ops", [
    [],
    [{"type": "resize", "target": "g", "width": 180, "height": 90}],
    [{"type": "rotate", "target": "g", "value": 35}],
    [{"type": "flip", "target": "g", "direction": "horizontal"}],
    [{"type": "pivot", "target": "g", "value": [0.2, 0.8]}, {"type": "rotate", "target": "g", "value": -50}],
])
def test_overflowing_group_matches_its_svg(ops):
    import resvg_py

    p = Project(400, 400, "white")
    p.apply([
        {"type": "shape", "shape": "rectangle", "name": "a", "width": 60, "height": 60, "x": 150, "y": 150, "fill": "red"},
        {"type": "shape", "shape": "ellipse", "name": "b", "width": 40, "height": 40, "x": 220, "y": 160, "fill": "blue"},
        {"type": "group", "name": "g", "targets": ["a", "b"]},
        {"type": "resize", "target": "a", "width": 120, "height": 40},
        {"type": "move", "target": "a", "x": -50, "y": -30},
        *ops,
    ])
    raster = np.asarray(p.render().getchannel("A"), dtype=int)
    svg = p.export(format="svg", svg_policy="strict").decode()
    vector = np.asarray(Image.open(io.BytesIO(resvg_py.svg_to_bytes(svg_string=svg))).getchannel("A"), dtype=int)
    assert (np.abs(raster - vector) > 64).mean() < 0.001
    # The part of the child moved outside the group's box is drawn.
    x, y, w, h = p.inspect("g")["drawn_bounds"]
    assert (x, y) < p.inspect("g")["resolved_bounds"][:2] or (x + w, y + h) > (150 + 110, 150 + 60)


def test_blur_spreads_past_the_layer_box():
    p = Project(300, 200, "#000")
    p.apply([
        {"type": "text", "name": "t", "text": "H", "size": 120, "color": "#fff", "x": 100, "y": 40},
        {"type": "effect", "target": "t", "name": "blur", "amount": 20},
    ])
    x, y, w, h = p.inspect("t")["resolved_bounds"]
    image = p.render().convert("L")
    assert image.getpixel((x - 4, y + h // 2)) > 0 and image.getpixel((x + w + 3, y + h // 2)) > 0
    # Soft on every side: no step at the old box edge.
    row = [image.getpixel((i, y + h // 2)) for i in range(x - 3, x + 3)]
    assert max(b - a for a, b in zip(row, row[1:])) < 30
    drawn = p.inspect("t")["drawn_bounds"]
    assert drawn[0] == x - 60 and drawn[2] == w + 120
    svg = p.export(format="svg").decode()
    assert 'width="' + str(w + 120) + '"' in svg  # The filter region covers the blur.


def test_rasterize_bakes_the_whole_blur():
    p = Project(200, 200, "white")
    p.apply([
        {"type": "shape", "shape": "ellipse", "name": "e", "width": 40, "height": 40, "x": 80, "y": 80, "fill": "black"},
        {"type": "effect", "target": "e", "name": "blur", "amount": 5},
    ])
    before = np.asarray(p.render())
    p.apply({"type": "rasterize", "target": "e"})
    layer = p.layer("e")
    assert (layer["width"], layer["x"]) == (70, 65)
    assert np.abs(np.asarray(p.render()).astype(int) - before).max() <= 1


# Shapes, swatches, text and artboards ---------------------------------------------------------


@pytest.mark.parametrize("shape", ["rectangle", "rounded-rectangle", "ellipse", "capsule", "line", "star", "polygon"])
def test_stroke_wider_than_its_shape_renders(shape):
    p = Project(100, 100, "white")
    p.apply({"type": "shape", "shape": shape, "name": "s", "width": 20, "height": 20, "x": 40, "y": 40,
             "fill": "red", "stroke": "black", "stroke_width": 26})
    p.render()
    p.export(format="svg")


def test_stroked_ring_animates_to_scale_zero():
    from vixl.timeline import project_at

    p = Project(700, 700, "white")
    p.apply([
        {"type": "shape", "shape": "ellipse", "name": "ring", "width": 600, "height": 600, "x": 50, "y": 50,
         "fill": "transparent", "stroke": "black", "stroke_width": 26},
        {"type": "keyframe", "target": "ring", "property": "scale", "time": 0, "value": 0},
        {"type": "keyframe", "target": "ring", "property": "scale", "time": 1000, "value": 1},
    ])
    sizes = [ink(project_at(p, t).render()).sum() for t in (0, 20, 50, 100, 500)]
    assert sizes == sorted(sizes) and sizes[-1] > 0


def test_repeats_accept_swatch_colors():
    p = Project(200, 200)
    p.apply([
        {"type": "swatch", "name": "a", "color": "#ff0000"},
        {"type": "swatch", "name": "b", "color": "#00ff00"},
        {"type": "shape", "shape": "rectangle", "name": "r", "width": 50, "height": 5, "fill": "@a"},
        {"type": "repeat-blend", "target": "r", "count": 3, "dy": 10, "end": {"fill": "@b"}},
    ])
    image = p.render()
    assert [image.getpixel((5, y))[:3] for y in (2, 22)] == [(255, 0, 0), (0, 255, 0)]
    p.apply({"type": "swatch", "name": "b", "color": "#0000ff"})
    assert p.render().getpixel((5, 22))[:3] == (0, 0, 255)


def test_swatch_defined_from_a_variable():
    p = Project(100, 100)
    p.apply([
        {"type": "variable", "name": "c", "value": "#f00"},
        {"type": "swatch", "name": "s", "color": "${c}"},
        {"type": "swatch", "name": "soft", "color": "mix(@s, white, 50%)"},
        {"type": "shape", "shape": "rectangle", "name": "r", "width": 10, "height": 10, "fill": "@s"},
        {"type": "text", "name": "t", "text": "x", "color": "@soft", "x": 50, "y": 50},
        {"type": "style-define", "name": "h", "settings": {"color": "@s"}},
    ])
    assert p.render().getpixel((5, 5))[:3] == (255, 0, 0)
    assert p.render(variables={"c": "#00f"}).getpixel((5, 5))[:3] == (0, 0, 255)
    p.apply({"type": "variable", "name": "c", "value": "#0f0"})
    assert p.render().getpixel((5, 5))[:3] == (0, 255, 0)


def test_fit_shrinks_a_long_word_instead_of_breaking_it():
    p = Project(1700, 600, "white")
    p.apply([
        {"type": "text", "name": "t", "text": "SOLSTICE", "size": 270, "color": "black"},
        {"type": "text-layout", "target": "t", "width": 1000, "height": 420, "fit": True},
    ])
    rows = ink(p.render()).any(axis=1).nonzero()[0]
    assert rows.max() - rows.min() < 200  # One line of type, not "SOLSTI / CE".
    p.apply({"type": "text-set", "target": "t", "text": "SUMMER SOLSTICE SIGNAL"})
    rows = ink(p.render()).any(axis=1).nonzero()[0]
    assert rows.max() - rows.min() > 150  # Several words still wrap between words.


def test_text_fit_rule_on_auto_sized_text():
    p = Project(400, 200, "white")
    p.apply([
        {"type": "text", "name": "t", "text": "Hello", "size": 40, "color": "black"},
        {"type": "text", "name": "boxed", "text": "A much longer line", "size": 40, "color": "black", "y": 80},
        {"type": "text-layout", "target": "boxed", "width": 120, "height": 40},
        {"type": "suite-set", "name": "s", "suite": {"rules": [
            {"id": "auto", "kind": "text-fit", "target": "t", "minimum": 10},
            {"id": "big", "kind": "text-fit", "target": "t", "minimum": 60},
            {"id": "boxed", "kind": "text-fit", "target": "boxed", "minimum": 10},
        ]}},
    ])
    status = {r["id"]: r["status"] for r in p.check_suite("s")["results"]}
    assert status == {"auto": "passed", "big": "failed", "boxed": "failed"}


def test_artboard_position_is_a_viewport(tmp_path):
    p = Project(400, 400, "white")
    p.apply([
        {"type": "shape", "shape": "rectangle", "name": "a", "width": 100, "height": 100, "x": 300, "y": 300, "fill": "red"},
        {"type": "text", "name": "t", "text": "Hi", "size": 20, "color": "black"},
        {"type": "constrain", "target": "t", "constraints": {"right": "canvas.right-10", "bottom": "canvas.bottom-10"}},
        {"type": "artboard", "name": "crop", "width": 100, "height": 100, "x": 300, "y": 300},
        {"type": "artboard", "name": "small", "width": 200, "height": 200},
    ])
    crop = p.render(artboard="crop")
    assert crop.size == (100, 100) and crop.getpixel((50, 50))[:3] == (255, 0, 0)
    full = ink(p.render()).nonzero()
    cropped = ink(crop).nonzero()
    # The constrained text stays where the document puts it.
    assert (cropped[0].min(), cropped[1].min()) == (full[0].min() - 300, full[1].min() - 300)
    # Without x/y an artboard is still a resized canvas whose constraints reflow.
    small = ink(p.render(artboard="small")).nonzero()
    assert small[1].max() < 200 - 5
    p.save(tmp_path / "boards.vixl")
    assert Project.load(tmp_path / "boards.vixl").state["artboards"]["crop"]["x"] == 300
    assert b'width="100"' in p.export(format="svg", artboard="crop")


# Missing glyphs --------------------------------------------------------------------------------


def test_missing_glyphs_fail_every_check():
    from vixl.validation import validate

    p = Project(600, 200, "white")
    p.apply([
        {"type": "variable", "name": "name", "value": "Ember"},
        {"type": "text", "name": "t", "text": "${name}", "size": 40, "color": "black"},
        {"type": "suite-set", "name": "s", "suite": {"rules": [{"id": "fit", "kind": "text-fit", "target": "t"}]}},
    ])
    assert p.check(checks=["contrast"])["passed"] and p.check_suite("s")["passed"] and validate(p)["valid"]
    row = {"name": "日本語"}
    report = p.check(checks=["contrast"], variables=row)
    assert not report["passed"]
    assert any(i["check"] == "fonts" and i["missing"] == sorted(row["name"]) for i in report["issues"])
    suite = p.check_suite("s", variables=row)
    assert suite["status"] == "failed" and suite["results"][-1]["id"] == "missing-glyphs"
    p.apply({"type": "variable", "name": "name", "value": row["name"]})
    assert not validate(p)["valid"]


# Concurrency ----------------------------------------------------------------------------------


def test_text_shaping_is_thread_safe_on_a_cold_font_cache():
    import vixl.text as text

    data = (Path(text.__file__).parent / "data" / "DejaVuSans.ttf").read_bytes()
    errors = []
    for attempt in range(8):
        blob = data + bytes(attempt + 1)  # A font no thread has parsed yet.
        barrier = threading.Barrier(6)

        def work(i):
            try:
                barrier.wait()
                text.measure(blob, f"Hello wörld {i}", 30 + i, width=150)
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)

        threads = [threading.Thread(target=work, args=(i,)) for i in range(6)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
    assert errors == []


# Performance paths keep identical results -----------------------------------------------------


def test_single_pass_contrast_matches_per_layer_measurement():
    from vixl.measure import measure, top_level_contrast
    import vixl.render as render

    p = Project(800, 600, "#223344")
    p.apply([
        {"type": "gradient", "name": "sky", "width": 800, "height": 600, "start": "#ffcc00", "end": "#330066"},
        {"type": "text", "name": "under", "text": "Below", "size": 40, "color": "white", "x": 40, "y": 40},
        {"type": "shape", "shape": "rounded-rectangle", "name": "panel", "width": 500, "height": 200, "x": 30, "y": 20,
         "fill": "#ffffffcc"},
        {"type": "text", "name": "over", "text": "On the panel", "size": 36, "color": "#555", "x": 60, "y": 60},
        {"type": "layer-style", "target": "over", "name": "drop-shadow", "settings": {"blur": 4}},
        {"type": "text", "name": "blend", "text": "Multiply", "size": 50, "color": "#ff0000", "x": 300, "y": 300},
        {"type": "blend", "target": "blend", "value": "multiply"},
        {"type": "shape", "shape": "ellipse", "name": "disc", "width": 200, "height": 200, "x": 500, "y": 350, "fill": "teal"},
        {"type": "text", "name": "clipped", "text": "CLIP", "size": 60, "color": "yellow", "x": 480, "y": 420},
        {"type": "clip", "target": "clipped", "base": "disc"},
        {"type": "adjustment", "name": "grade", "effects": [{"name": "saturation", "amount": -50}]},
        {"type": "text", "name": "top", "text": "Above the grade", "size": 32, "color": "#eeeeee", "x": 40, "y": 520},
        {"type": "text", "name": "off", "text": "Off canvas", "size": 32, "color": "white", "x": 700, "y": 100},
    ])
    ids = [layer["id"] for layer in p.state["layers"] if layer["type"] == "text"]
    calls = []
    original = render._render_layers
    render._render_layers = lambda *args: calls.append(1) or original(*args)
    try:
        fast = top_level_contrast(p.clone(), ids)
    finally:
        render._render_layers = original
    assert len(calls) == 1
    for ident in ids:
        try:
            slow = measure(p.clone(), target=ident)["contrast"]
        except Exception as exc:  # noqa: BLE001
            assert str(fast[ident]) == str(exc)
        else:
            assert fast[ident] == slow


def strokes(count, start=0, target="paint"):
    return [{"type": "paint", "target": target, "brush": "round", "size": 10, "color": "black",
             "points": [[(i % 70) * 10 + 10, (i * 7) % 480 + 10], [(i % 70) * 10 + 60, (i * 7) % 480 + 15]]}
            for i in range(start, start + count)]


def test_painting_more_strokes_renders_only_the_new_ones(monkeypatch):
    import vixl.brushes as brushes

    p = Project(800, 500)
    p.apply([{"type": "paint-layer", "name": "paint"}, *strokes(60)])
    painted = []
    original = brushes.stroke_patch
    monkeypatch.setattr(brushes, "stroke_patch", lambda *a: painted.append(1) or original(*a))
    p.apply(strokes(2, 60))
    assert len(painted) == 2
    fresh = Project(800, 500)
    fresh.apply([{"type": "paint-layer", "name": "paint"}, *strokes(62)])
    assert np.array_equal(np.asarray(fresh.render()), np.asarray(p.render()))


@pytest.mark.parametrize("brush", ["watercolor", "dry-brush", "spray", "chalk", "splatter"])
def test_stroke_patch_matches_full_layer_coverage(brush):
    from vixl.brushes import brush_settings, stroke_patch

    stroke = {"brush": brush, "size": 40, "seed": 3, "points": [[-20, 30], [120, 90, 0.5], [300, 10]]}
    settings = brush_settings({}, brush)
    patch, (x, y) = stroke_patch(stroke, settings, (200, 260))
    full = np.zeros((200, 260), np.float32)
    full[y:y + patch.shape[0], x:x + patch.shape[1]] = patch
    assert patch.shape[1] < 260 or patch.shape[0] < 200 or brush == "splatter"
    assert full.max() > 0
    # Same stroke drawn alone on a layer: the patch is the whole visible result.
    p = Project(260, 200)
    p.apply([{"type": "paint-layer", "name": "paint"},
             {"type": "paint", "target": "paint", "brush": brush, "size": 40, "seed": 3,
              "points": [[-20, 30], [120, 90, 0.5], [300, 10]]}])
    alpha = np.asarray(p.render().getchannel("A")).astype(float)
    assert np.abs(alpha - np.uint8(np.clip(full, 0, 1) * 255 + 0.5)).max() <= 1


def test_moving_paint_layers_reuse_their_cached_image(tmp_path, monkeypatch):
    import vixl.brushes as brushes
    from vixl.timeline import export_timeline

    p = Project(400, 300, "white")
    p.apply([{"type": "paint-layer", "name": "paint"}, *strokes(30),
             {"type": "keyframe", "target": "paint", "property": "translate-x", "time": 0, "value": 0},
             {"type": "keyframe", "target": "paint", "property": "translate-x", "time": 1000, "value": -80}])
    p.save(tmp_path / "film.vixl")
    p = Project.load(tmp_path / "film.vixl")
    monkeypatch.setenv("VIXL_RENDER_CACHE", str(tmp_path / "cache"))
    calls = []
    original = brushes.paint_image
    monkeypatch.setattr(brushes, "paint_image", lambda *a: calls.append(1) or original(*a))
    export_timeline(p, tmp_path / "a.gif", fps=6)
    assert len(calls) == 1  # Painted once, then moved frame to frame.
    assert any((tmp_path / "cache").glob("*.png")) and not (tmp_path / ".vixl-cache").exists()
    calls.clear()
    export_timeline(Project.load(tmp_path / "film.vixl"), tmp_path / "b.gif", fps=6)
    assert calls == []  # A later export reuses the persistent cache.


def test_full_bleed_blur_keeps_its_edges_and_moving_it_refreshes_them():
    p = Project(200, 100, "white")
    p.apply([
        {"type": "solid", "name": "photo", "color": "#204080", "width": 100, "height": 50},
        {"type": "effect", "target": "photo", "name": "blur", "amount": 6},
    ])
    # At the canvas edge the blur continues the photo instead of fading to the background.
    assert p.render().getpixel((0, 20))[:3] == (32, 64, 128)
    p.apply({"type": "move", "target": "photo", "x": 50, "y": 25})
    # Moved away from the canvas edge, the same layer (same size, same cache entry otherwise)
    # gets soft edges.
    edge = p.render().getpixel((50, 45))[:3]
    assert edge != (32, 64, 128) and edge != (255, 255, 255)


def test_blur_spreads_only_before_per_pixel_effects():
    from vixl.render import effect_margin

    def layer(*names):
        return {"effects": [{"name": name, "amount": 4, "enabled": True} for name in names]}

    assert effect_margin(layer("blur")) == (12, 12)
    assert effect_margin(layer("noise", "blur", "saturation", "gaussian-blur")) == (24, 24)
    # A size- or position-dependent effect after the blur keeps the stack inside the box, so
    # existing documents render exactly as before (a wave's phase does not shift).
    for later in ("wave", "vignette", "contrast", "grain", "oil-paint"):
        assert effect_margin(layer("blur", later)) == (0, 0)
    assert effect_margin({"effects": [{"name": "blur", "amount": 4, "enabled": False}]}) == (0, 0)
