"""Rendering shortcuts must draw exactly what a full render draws, and must actually skip the work."""

import random

import numpy as np
import pytest
from PIL import Image

from vixl import Project
from vixl.assets import add_image
from vixl import render as R
from vixl.timeline import project_at, render_at


def pixels(image):
    return np.asarray(image).astype(int)


def fresh(p):
    q = p.clone()
    q._cache = None
    return R.render(q)


def scene():
    p = Project(900, 700, "#f4f0e8")
    p.apply([
        {"type": "shape", "shape": "ellipse", "name": "e", "x": 100, "y": 100, "width": 300, "height": 200,
         "fill": "#e63", "rotation": 20},
        {"type": "text", "name": "t", "text": "Hello region", "size": 60, "x": 350, "y": 300, "color": "navy"},
        {"type": "shape", "shape": "star", "name": "s", "x": 600, "y": 400, "width": 200, "height": 200,
         "fill": "gold", "stroke": "black", "stroke_width": 4},
        {"type": "shape", "shape": "rectangle", "name": "r", "x": 50, "y": 500, "width": 700, "height": 120,
         "fill": "rgba(0,120,200,0.5)"},
        {"type": "shape", "shape": "rectangle", "name": "r2", "x": 300, "y": 50, "width": 100, "height": 500,
         "fill": "#2a2"},
    ], detail="brief")
    p.apply([{"type": "look", "look": "soft-shadow", "targets": ["e", "t"]},
             {"type": "group", "targets": ["s", "r"], "name": "g"},
             {"type": "blend", "target": "r2", "value": "multiply"},
             {"type": "opacity", "target": "t", "value": 0.7}], detail="brief")
    return p


def test_render_reads_the_form_fields_once_not_once_per_text_layer(monkeypatch):
    from vixl import forms

    p = Project(1200, 1200, "white")
    p.apply([{"type": "text", "name": f"t{i}", "text": f"Label {i}", "size": 14, "x": (i % 10) * 110,
              "y": (i // 10) * 30, "color": "black"} for i in range(200)], detail="brief")
    calls = []
    original = forms.has_fields
    monkeypatch.setattr(forms, "has_fields", lambda project: calls.append(1) or original(project))
    p._cache = None
    R.render(p)
    assert len(calls) <= 3


def test_an_outline_free_rectangle_is_filled_without_supersampling(monkeypatch):
    from vixl.design_render import shape_image

    p = Project(400, 400, "white")
    p.apply({"type": "shape", "shape": "rectangle", "name": "r", "x": 0, "y": 0, "width": 37, "height": 21,
             "fill": "#336699"}, detail="brief")
    monkeypatch.setattr(Image.Image, "resize", lambda *a, **k: pytest.fail("supersampled"))
    image = shape_image(p, p.layer("r"))
    assert image.size == (37, 21) and (np.asarray(image) == (0x33, 0x66, 0x99, 255)).all()


def test_a_styled_layer_does_not_draw_a_canvas_sized_tile(monkeypatch):
    p = Project(3000, 3000, "white")
    p.apply([{"type": "shape", "shape": "ellipse", "name": "c", "x": 1400, "y": 1400, "width": 80, "height": 80,
              "fill": "#e63"},
             {"type": "look", "look": "soft-shadow", "target": "c"}], detail="brief")
    sizes = []
    original = Image.new
    monkeypatch.setattr(Image, "new", lambda mode, size, *a, **k: sizes.append(tuple(size)) or original(mode, size, *a, **k))
    p._cache = None
    R.render(p)
    assert sizes.count((3000, 3000)) == 1  # the background


def test_a_styled_layer_that_moves_reuses_its_styled_pixels(monkeypatch):
    from vixl import design_render

    p = scene()
    # Somewhere its shadow stays clear of the canvas edge, which would cut the styled area.
    p.apply({"type": "move", "target": "e", "x": 250, "y": 200}, detail="brief")
    R.render(p)
    calls = []
    original = design_render.styled_image
    monkeypatch.setattr(design_render, "styled_image", lambda *a: calls.append(1) or original(*a))
    p.apply({"type": "move", "target": "e", "x": 270, "y": 215}, detail="brief")
    image = R.render(p)
    assert calls == []
    assert np.array_equal(pixels(image), pixels(fresh(p)))


def test_opacity_tables_match_rounding_each_alpha():
    image = Image.new("RGBA", (256, 1))
    image.putalpha(Image.frombytes("L", (256, 1), bytes(range(256))))
    scaled = R.with_opacity(image.copy(), 0.37)
    assert np.asarray(scaled.getchannel("A"))[0].tolist() == [round(a * 0.37) for a in range(256)]


def test_previews_try_fast_compression_first():
    from io import BytesIO

    from vixl.proxy import encode_png

    image = Image.effect_noise((300, 300), 40).convert("RGBA")
    fast = BytesIO()
    image.save(fast, format="PNG", compress_level=1)
    assert encode_png(image, 4_000_000) == fast.getvalue()
    small = encode_png(image, len(fast.getvalue()) - 1)
    assert len(small) < len(fast.getvalue())


def test_a_layer_without_effects_skips_the_effect_stack():
    p = scene()
    image = Image.new("RGBA", (5, 5))
    layer = {**p.layer("e"), "effects": [{"name": "blur", "amount": 2, "enabled": False}]}
    assert R.layer_effects(p, layer, (0, 0, 5, 5), image) is image


@pytest.mark.parametrize("region", [(0, 0, 900, 700), (90, 90, 200, 150), (300, 250, 500, 200),
                                    (580, 380, 300, 300), (0, 0, 1, 1), (899, 699, 1, 1), (450, 0, 450, 700)])
def test_a_region_renders_the_same_pixels_as_a_crop(region):
    p = scene()
    x, y, w, h = region
    assert np.array_equal(pixels(p.render(region=region)), pixels(p.render().crop((x, y, x + w, y + h))))


def test_a_region_skips_layers_outside_it(monkeypatch):
    p = scene()
    drawn = []
    original = R.layer_ink
    monkeypatch.setattr(R, "layer_ink", lambda project, layer, bounds: drawn.append(layer["name"]) or original(project, layer, bounds))
    p.render(region=(0, 0, 60, 60))
    assert "t" not in drawn and "g" not in drawn


def test_a_region_of_a_lit_scene_falls_back_to_a_crop():
    p = scene()
    p.state["lighting"] = {"ambient": 0.8, "vignette": 0.5}
    assert not R.region_renders_alone(p)
    assert np.array_equal(pixels(p.render(region=(100, 100, 50, 50))), pixels(p.render().crop((100, 100, 150, 150))))


def test_identical_and_recoloured_labels_rasterise_their_glyphs_once(monkeypatch):
    import resvg_py

    from vixl import vector_raster

    vector_raster.CACHE.clear()
    vector_raster.CACHE.bytes = 0
    p = Project(600, 200, "white")
    p.apply([{"type": "text", "name": f"t{i}", "text": "Same words", "size": 30, "x": 10, "y": 10 + i * 40,
              "color": color} for i, color in enumerate(["navy", "tomato", "rgba(0,0,0,0.5)"])], detail="brief")
    calls = []
    original = resvg_py.svg_to_bytes
    monkeypatch.setattr(resvg_py, "svg_to_bytes", lambda **k: calls.append(1) or original(**k))
    p._cache = None
    image = R.render(p)
    assert len(calls) == 1
    ink = [tuple(c) for c in np.asarray(image)[:, :, :3].reshape(-1, 3) if tuple(c) != (255, 255, 255)]
    assert (0, 0, 128) in ink and (255, 99, 71) in ink


def test_a_render_looks_each_font_up_once_per_text(monkeypatch):
    from vixl import text

    p = Project(800, 800, "white")
    p.apply([{"type": "text", "name": f"t{i}", "text": "Repeat", "size": 14, "x": (i % 10) * 70, "y": (i // 10) * 30,
              "color": "black"} for i in range(100)], detail="brief")
    calls = []
    original = text._font_data
    monkeypatch.setattr(text, "_font_data", lambda *a: calls.append(1) or original(*a))
    p._cache = None
    R.render(p)
    assert len(calls) == 1


def test_incremental_renders_match_full_renders_through_random_edits():
    random.seed(7)
    p = scene()
    names = ["e", "t", "g", "r2"]
    edits = [
        lambda n: {"type": "move", "target": n, "x": random.randint(-100, 800), "y": random.randint(-100, 600)},
        lambda n: {"type": "opacity", "target": n, "value": round(random.random(), 2)},
        lambda n: {"type": "rotate", "target": n, "angle": random.randint(0, 359)},
        lambda n: {"type": random.choice(["hide", "show"]), "target": n},
        lambda n: {"type": "blend", "target": n, "value": random.choice(["normal", "multiply", "screen"])},
    ]
    for _ in range(40):
        p.apply(random.choice(edits)(random.choice(names)), detail="brief")
        assert np.array_equal(pixels(R.render(p)), pixels(fresh(p)))


def test_moving_one_layer_redraws_only_its_neighbourhood(monkeypatch):
    p = Project(2000, 2000, "white")
    p.apply([{"type": "shape", "shape": "ellipse", "name": f"s{i}", "x": (i % 20) * 100, "y": (i // 20) * 100,
              "width": 60, "height": 60, "fill": "#369"} for i in range(400)], detail="brief")
    R.render(p)
    p.apply({"type": "move", "target": "s0", "x": 10, "y": 10}, detail="brief")
    drawn = []
    original = R.layer_ink
    monkeypatch.setattr(R, "layer_ink", lambda project, layer, bounds: drawn.append(layer["name"]) or original(project, layer, bounds))
    image = R.render(p)
    assert len(drawn) < 10
    assert np.array_equal(pixels(image), pixels(fresh(p)))


def test_timeline_frames_render_incrementally_and_exactly():
    p = Project(640, 360, "#203040")
    p.apply([{"type": "text", "name": "title", "text": "Hello world", "size": 48, "x": 40, "y": 120, "color": "white"},
             {"type": "shape", "shape": "ellipse", "name": "dot", "x": 20, "y": 20, "width": 60, "height": 60,
              "fill": "tomato"},
             {"type": "timeline-set", "duration": 2000}])
    # Kinetic glyphs draw past their layer's box: the dirty box must grow to hold them.
    p.apply({"type": "text-animate", "target": "title", "preset": "fade-down", "unit": "char", "duration": 1500,
             "distance": 60})
    p.apply({"type": "keyframe", "target": "dot", "property": "x", "time": 0, "value": 20})
    p.apply({"type": "keyframe", "target": "dot", "property": "x", "time": 2000, "value": 560})
    for time in range(0, 2001, 100):
        frame = project_at(p, time)
        frame._cache = None
        assert np.array_equal(pixels(render_at(p, time)), pixels(R.render(frame)))
    assert p._cache.snapshot is not None


def test_documents_that_read_the_whole_canvas_render_in_full():
    p = scene()
    p.apply({"type": "adjustment", "name": "adj", "effects": [{"name": "blur", "amount": 2}]}, detail="brief")
    assert not R.region_renders_alone(p)
    R.render(p)
    assert getattr(p._cache, "snapshot", None) is None


@pytest.mark.parametrize("edit", [
    lambda p: p.apply({"type": "swatch", "name": "shade", "color": "#00ff00"}, detail="brief"),
    lambda p: p.apply({"type": "variable", "name": "word", "value": "Changed"}, detail="brief"),
    lambda p: p.apply({"type": "canvas", "background": "#102030"}, detail="brief"),
    lambda p: p.apply({"type": "layer-style", "target": "e", "name": "drop-shadow",
                       "settings": {"color": "@shade", "dx": 30}}, detail="brief"),
    lambda p: p.apply({"type": "opacity", "target": "label", "value": 0.4}, detail="brief"),
    lambda p: p.apply({"type": "add", "asset": add_image(p, Image.new("RGBA", (20, 20), "blue")), "name": "img2",
                       "x": 700, "y": 50}, detail="brief"),
], ids=["swatch", "variable", "background", "style", "opacity", "asset"])
def test_every_input_of_the_render_caches_reaches_the_pixels(edit):
    """The styled-patch cache, the layer fingerprints and the reused canvas each read these inputs."""
    p = scene()
    p.apply([{"type": "swatch", "name": "shade", "color": "#ff0000"},
             {"type": "variable", "name": "word", "value": "Original"},
             {"type": "text", "name": "label", "text": "${word}", "size": 30, "x": 20, "y": 20, "color": "black"},
             {"type": "layer-style", "target": "e", "name": "drop-shadow", "settings": {"color": "@shade"}},
             {"type": "add", "asset": add_image(p, Image.new("RGBA", (20, 20), "red")), "name": "img",
              "x": 600, "y": 50}],
            detail="brief")
    before = pixels(R.render(p))
    edit(p)
    after = pixels(R.render(p))
    assert not np.array_equal(before, after)
    assert np.array_equal(after, pixels(fresh(p)))
