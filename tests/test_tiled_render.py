"""Tiled compositing (#588): tiles, bands and the streamed PNG must give exactly the single-canvas pixels."""

import io
import random
import zlib

import numpy as np
import pytest
from PIL import Image

from vixl import Project
from vixl import render as R
from vixl import tiles
from vixl.assets import add_image
from vixl.fileio import PngWriter, adler32_combine


def pixels(image):
    return np.asarray(image.convert("RGBA")).astype(int)


def single(p, background="transparent"):
    """The canvas drawn the old way: one canvas, no tiles."""
    q = p.clone()
    q._cache = None
    return R.render_layers(q, background=background)


def photo(size, seed=1):
    rng = np.random.default_rng(seed)
    data = rng.integers(0, 255, (size[1] // 8 + 1, size[0] // 8 + 1, 3), dtype=np.uint8)
    return Image.fromarray(data).resize(size, Image.Resampling.BICUBIC)


def random_document(seed, size=(1500, 1100)):
    """Layers of every kind the compositor treats differently, placed so that they straddle tile edges."""
    rng = random.Random(seed)
    w, h = size
    p = Project(w, h, rng.choice(["white", "transparent", "#102030"]))
    ops, later = [{"type": "gradient", "name": "bg", "x": 0, "y": 0, "width": w, "height": h,
                   "direction": rng.choice(["vertical", "horizontal", "radial", "angled"]), "angle": 35,
                   "start": "#f4efe6", "end": "#3b6ea5"}], []
    for i in range(26):
        sw, sh = rng.randrange(60, 520), rng.randrange(60, 420)
        name = f"s{i}"
        ops.append({"type": "shape", "shape": rng.choice(["ellipse", "rectangle", "rounded-rectangle", "star"]),
                    "name": name, "x": rng.randrange(-80, w - 40), "y": rng.randrange(-80, h - 40), "width": sw,
                    "height": sh, "fill": "#%06x" % rng.randrange(0xFFFFFF),
                    **({"x": rng.randrange(0, w) + 0.5} if i % 7 == 0 else {})})
        if i % 3 == 0:
            later.append({"type": "opacity", "target": name, "value": round(rng.uniform(0.2, 0.9), 2)})
        if i % 4 == 0:
            later.append({"type": "blend", "target": name, "value": rng.choice(["multiply", "screen", "overlay", "add"])})
        if i % 5 == 0:
            later.append({"type": "rotate", "target": name, "angle": rng.randrange(1, 359)})
    for i in range(8):
        ops.append({"type": "text", "name": f"t{i}", "text": rng.choice(["Tiles fjord gyp", "Overhang Wj", "Label 12"]),
                    "size": rng.randrange(20, 160), "x": rng.randrange(-40, w - 100), "y": rng.randrange(-20, h - 60),
                    "color": "#%06x" % rng.randrange(0xFFFFFF)})
    p.apply(ops, detail="brief")
    p.apply([{"type": "add", "asset": add_image(p, photo((700, 500), seed)), "name": "photo",
              "x": rng.randrange(0, w - 500), "y": rng.randrange(0, h - 300)},
             {"type": "resize", "target": "photo", "width": 820, "height": 590}], detail="brief")
    later += [{"type": "look", "look": "soft-shadow", "targets": ["s1", "t0", "s2"]},
              {"type": "group", "targets": ["s3", "s4", "t1"], "name": "g"},
              {"type": "rotate", "target": "g", "angle": 12},
              {"type": "clip", "target": "s5", "base": "s6"}]
    p.apply(later, detail="brief")
    return p


@pytest.mark.parametrize("tile", [256, 1000])
@pytest.mark.parametrize("seed", [1, 2, 3])
def test_tiles_equal_the_single_canvas_on_random_documents(seed, tile):
    p = random_document(seed)
    background = p.state["canvas"]["background"]
    expected = single(p, background)
    assert np.array_equal(pixels(R.render_tiled(p, background, tile=tile)), pixels(expected))
    # One worker and several give the same bytes.
    assert R.render_tiled(p, background, tile=tile, workers=1).tobytes() == expected.tobytes()


def test_a_large_render_is_tiled_and_matches_the_single_canvas(monkeypatch):
    p = random_document(4)
    expected = single(p, p.state["canvas"]["background"])
    calls = []
    original = tiles.tiles
    monkeypatch.setattr(tiles, "tiles", lambda *a, **k: calls.append(1) or original(*a, **k))
    monkeypatch.setattr(R, "TILED_PIXELS", 1_000_000)
    p._cache = None
    assert np.array_equal(pixels(p.render()), pixels(expected))
    assert calls
    # The snapshot a tiled render leaves serves the next edit: only the moved layer's neighbourhood is drawn again.
    p.apply({"type": "move", "target": "s7", "x": 333, "y": 444}, detail="brief")
    assert np.array_equal(pixels(p.render()), pixels(single(p, p.state["canvas"]["background"])))
    assert len(calls) == 1


def test_a_small_render_is_not_tiled(monkeypatch):
    p = random_document(5, (600, 400))
    monkeypatch.setattr(tiles, "tiles", lambda *a, **k: pytest.fail("a small canvas was tiled"))
    p.render()


def test_a_lit_and_adjusted_document_tiles_exactly(monkeypatch):
    p = random_document(6)
    p.apply([{"type": "lighting", "ambient": 0.8, "lights": [{"x": 400, "y": 300, "radius": 500, "intensity": 0.6}],
              "vignette": 0.5},
             {"type": "adjustment", "name": "grade", "effects": [{"name": "levels", "black": 10, "white": 240}]}],
            detail="brief")
    assert R.region_renders_alone(p)
    q = p.clone()
    q._cache = None
    expected = R.render(q)
    monkeypatch.setattr(R, "TILED_PIXELS", 1_000_000)
    p._cache = None
    assert np.array_equal(pixels(p.render()), pixels(expected))
    data = p.export(alpha="keep")
    assert np.array_equal(pixels(Image.open(io.BytesIO(data))), pixels(expected))


def test_an_opaque_blended_shape_cut_by_a_tile_blends_as_on_the_whole_canvas():
    # Multiply and screen had an all-opaque shortcut that rounded differently from the general equation: the middle
    # of an opaque shape (a tile of it) took the shortcut, the whole shape with its transparent corners did not.
    p = Project(700, 500, "#d08214")
    p.apply([{"type": "shape", "shape": "ellipse", "name": "m", "x": 40, "y": 30, "width": 600, "height": 420,
              "fill": "#82c8f0"},
             {"type": "shape", "shape": "ellipse", "name": "s", "x": 140, "y": 90, "width": 500, "height": 380,
              "fill": "#e04377"},
             {"type": "blend", "target": "m", "value": "multiply"}, {"type": "blend", "target": "s", "value": "screen"}],
            detail="brief")
    expected = single(p, "#d08214")
    assert np.array_equal(pixels(R.render_tiled(p, "#d08214", tile=128)), pixels(expected))
    assert np.array_equal(pixels(p.render(region=(250, 200, 100, 100))), pixels(expected.crop((250, 200, 350, 300))))


@pytest.mark.parametrize("blend", ["multiply", "screen", "darken", "lighten", "difference", "add", "subtract"])
def test_a_blend_gives_a_pixel_the_same_value_whatever_else_is_in_the_box(blend):
    rng = np.random.default_rng(5)
    bottom = Image.fromarray(np.dstack([rng.integers(0, 256, (64, 64, 3), dtype=np.uint8),
                                        np.full((64, 64), 255, np.uint8)]))
    top = np.dstack([rng.integers(0, 256, (64, 64, 3), dtype=np.uint8), np.full((64, 64), 255, np.uint8)])
    top[:8, :, 3] = 90  # The box as a whole is not opaque; its lower part is.
    top = Image.fromarray(top)
    whole = R.composite(bottom, top, blend)
    part = R.composite(bottom.crop((0, 8, 64, 64)), top.crop((0, 8, 64, 64)), blend)
    assert np.array_equal(np.asarray(whole.crop((0, 8, 64, 64))), np.asarray(part))


def small_cache(p, megabytes=1):
    """Make ordinary layers count as too large for the layer cache, as full-canvas layers are on a print canvas."""
    p._cache = None
    R.layer_cache(p).budget = megabytes * 1024 * 1024 * 4
    return p


def large_layers(clip=False):
    p = Project(1300, 900, "white")
    p.apply([
        {"type": "solid", "name": "ground", "color": "#fff7ed"},
        {"type": "gradient", "name": "radial", "x": 0, "y": 0, "width": 1300, "height": 900, "direction": "radial",
         "start": "#fde68a", "end": "rgba(30,64,175,0.6)"},
        {"type": "gradient", "name": "down", "x": 100, "y": 37, "width": 1100, "height": 800, "direction": "vertical",
         "start": "#20242a", "end": "#2c3138"},
        {"type": "gradient", "name": "across", "x": -50, "y": 200, "width": 1250, "height": 690,
         "direction": "horizontal", "start": "rgba(255,0,0,0.3)", "end": "rgba(0,0,255,0.5)"},
        {"type": "gradient", "name": "slant", "x": 0, "y": 0, "width": 1300, "height": 900, "direction": "angled",
         "angle": 25, "start": "rgba(0,0,0,0)", "end": "rgba(0,80,0,0.4)"},
        {"type": "shape", "shape": "rectangle", "name": "panel", "x": 150, "y": 120, "width": 1000, "height": 640,
         "fill": "#235cdb"},
        {"type": "shape", "shape": "rectangle", "name": "framed", "x": 60, "y": 60, "width": 900, "height": 600,
         "fill": "rgba(255,255,255,0.3)", "stroke": "#111", "stroke_width": 6},
        {"type": "shape", "shape": "ellipse", "name": "disc", "x": 500, "y": 300, "width": 600, "height": 450,
         "fill": "rgba(220,40,40,0.5)"},
        {"type": "text", "name": "title", "text": "Tiles", "size": 300, "x": 200, "y": 250, "color": "#111"},
        {"type": "opacity", "target": "panel", "value": 0.6},
        {"type": "blend", "target": "down", "value": "multiply"},
    ], detail="brief")
    p.apply([{"type": "add", "asset": add_image(p, photo((640, 420))), "name": "photo", "x": 30, "y": 20},
             {"type": "resize", "target": "photo", "width": 800, "height": 600},
             {"type": "opacity", "target": "photo", "value": 0.5},
             {"type": "look", "look": "soft-shadow", "targets": ["disc"]}], detail="brief")
    if clip:
        p.apply({"type": "clip", "target": "title", "base": "panel"}, detail="brief")
    return p


@pytest.mark.parametrize("clip", [False, True])
def test_layers_too_large_for_the_cache_are_drawn_by_region_or_held_once(monkeypatch, clip):
    p = large_layers(clip)
    expected = single(p, "white")
    small_cache(p)
    layers, bounds = R.resolved(p)
    regions, held = tiles.plan(p, layers, bounds)
    names = {layer["name"] for _, layer, _ in held}
    # Fills and gradients are drawn tile by tile; what cannot be cropped exactly is drawn once and shared.
    assert len(regions) == (5 if clip else 6)  # ground, four gradients and the panel (held when something clips to it)
    assert {"framed", "disc", "photo"} <= names and ("panel" in names) == clip
    whole = []
    original = R.draw_ink
    monkeypatch.setattr(R, "draw_ink", lambda project, layer, b, profile=None: (
        whole.append((layer["name"], layer["width"], layer["height"])) or original(project, layer, b, profile)))
    assert np.array_equal(pixels(R.render_tiled(p, "white", tile=256)), pixels(expected))
    for name in ("photo", "disc", "framed"):
        assert sum(1 for drawn in whole if drawn[0] == name and drawn[1] > tiles.PROBE[0]) == 1, name
    # No tile drew a whole gradient or fill.
    assert not [drawn for drawn in whole if drawn[0] in ("radial", "slant", "down", "across", "ground")
                and drawn[1] * drawn[2] > 256 * 256]
    cache = R.layer_cache(p)
    assert not cache.held and not cache.regions


def test_a_document_whose_large_layers_cost_more_than_the_canvas_is_not_tiled(monkeypatch):
    p = Project(1000, 800, "white")
    p.apply([{"type": "shape", "shape": "ellipse", "name": f"e{i}", "x": 0, "y": 0, "width": 1000, "height": 800,
              "fill": "rgba(200,30,30,0.3)"} for i in range(4)], detail="brief")
    expected = single(p, "white")
    small_cache(p)
    layers, bounds = R.resolved(p)
    assert tiles.plan(p, layers, bounds) is None
    assert np.array_equal(pixels(R.render_tiled(p, "white", tile=256)), pixels(expected))
    monkeypatch.setattr(R, "TILED_PIXELS", 100_000)
    assert tiles.png(p) is None
    assert np.array_equal(pixels(Image.open(io.BytesIO(p.export()))), pixels(expected))


def test_a_gradient_box_is_the_crop_of_the_whole_gradient():
    from vixl.design_render import gradient_image

    p = Project(100, 100)
    for layer in ({"direction": "vertical"}, {"direction": "horizontal"}, {"direction": "radial", "center": (0.3, 0.6)},
                  {"direction": "angled", "angle": 70}, {"direction": "radial", "end": "rgba(0,0,255,0.2)"}):
        layer = {"type": "gradient", "start": "#20242a", "end": "#c9d6e8", **layer}
        whole = gradient_image(p, layer, (701, 533))
        for box in ((0, 0, 701, 533), (65, 130, 400, 131), (300, 77, 701, 533), (1, 63, 66, 200)):
            assert gradient_image(p, layer, (701, 533), box).tobytes() == whole.crop(box).tobytes(), (layer, box)


EXPORTS = [("white", "auto", "RGB"), ("transparent", "auto", "RGBA"), ("transparent", "keep", "RGBA"),
           ("white", "keep", "RGBA"), ("transparent", "flatten", "RGB")]


@pytest.mark.parametrize("canvas,alpha,mode", EXPORTS)
def test_a_large_png_export_is_streamed_with_the_pixels_of_the_single_canvas_export(monkeypatch, tmp_path, canvas,
                                                                                     alpha, mode):
    p = Project(1400, 1000, canvas)
    p.apply([{"type": "shape", "shape": "ellipse", "name": f"s{i}", "x": 90 * i, "y": 60 * i, "width": 420,
              "height": 300, "fill": ("#e63", "rgba(0,90,200,0.5)", "#2a2")[i % 3]} for i in range(12)]
            + [{"type": "text", "name": "t", "text": "Streamed", "size": 180, "x": 120, "y": 600, "color": "#123"}],
            detail="brief")
    before = Image.open(io.BytesIO(p.export(alpha=alpha, background="#ffeecc", dpi=300)))
    streamed = []
    original = tiles.bands
    monkeypatch.setattr(tiles, "bands", lambda *a, **k: streamed.append(1) or original(*a, **k))
    monkeypatch.setattr(R, "TILED_PIXELS", 1_000_000)
    q = p.clone()
    q._cache = None
    path = tmp_path / "out.png"
    report = {}
    data = q.export(path, alpha=alpha, background="#ffeecc", report=report, dpi=300)
    assert streamed and path.read_bytes() == data
    after = Image.open(io.BytesIO(data))
    after.load()
    assert after.mode == before.mode == mode and after.size == before.size
    assert after.tobytes() == before.tobytes()
    assert after.info["dpi"] == pytest.approx(before.info["dpi"])


def test_a_transparent_canvas_covered_by_opaque_layers_streams_without_alpha(monkeypatch):
    p = Project(1200, 900, "transparent")
    p.apply([{"type": "solid", "name": "ground", "color": "#fff7ed"},
             {"type": "shape", "shape": "ellipse", "name": "e", "x": 100, "y": 100, "width": 800, "height": 600,
              "fill": "#e63"}], detail="brief")
    before = Image.open(io.BytesIO(p.export()))
    monkeypatch.setattr(R, "TILED_PIXELS", 500_000)
    p._cache = None
    after = Image.open(io.BytesIO(p.export()))
    assert before.mode == after.mode == "RGB" and before.tobytes() == after.tobytes()


def test_transparency_found_late_on_an_opaque_canvas_restarts_the_stream_with_alpha(monkeypatch):
    p = Project(1200, 900, "white")
    p.apply([{"type": "shape", "shape": "ellipse", "name": "e", "x": 100, "y": 100, "width": 800, "height": 600,
              "fill": "#e63"}], detail="brief")
    monkeypatch.setattr(R, "TILED_PIXELS", 500_000)
    original = tiles.bands

    def holed(*args, **kwargs):
        for top, band in original(*args, **kwargs):
            if top:
                band.putpixel((5, 0), (0, 0, 0, 0))
            yield top, band

    monkeypatch.setattr(tiles, "bands", holed)
    image = Image.open(io.BytesIO(p.export()))
    assert image.mode == "RGBA" and image.getpixel((5, 0)) == (255, 255, 255, 255)
    assert image.getchannel("A").getextrema()[0] == 0


def test_exports_the_stream_does_not_cover_keep_the_single_canvas_path(monkeypatch, tmp_path):
    p = Project(1200, 900, "white")
    p.apply({"type": "shape", "shape": "ellipse", "name": "e", "x": 100, "y": 100, "width": 800, "height": 600,
             "fill": "#e63"}, detail="brief")
    monkeypatch.setattr(R, "TILED_PIXELS", 500_000)
    monkeypatch.setattr(tiles, "bands", lambda *a, **k: pytest.fail("streamed"))
    assert Image.open(io.BytesIO(p.export(format="jpeg"))).size == (1200, 900)
    assert Image.open(io.BytesIO(p.export(scale=0.5))).size == (600, 450)
    assert Image.open(io.BytesIO(p.export(simulate="deuteranopia"))).size == (1200, 900)
    # A document that reads the whole canvas is not tiled.
    p.apply({"type": "adjustment", "name": "soften", "effects": [{"name": "blur", "amount": 3}]}, detail="brief")
    assert not R.region_renders_alone(p)
    assert Image.open(io.BytesIO(p.export())).size == (1200, 900)


@pytest.mark.parametrize("mode", ["RGB", "RGBA"])
def test_the_png_writer_round_trips_bands_of_any_height(mode):
    rng = np.random.default_rng(11)
    width, height = 333, 517
    flat = np.zeros((height, width, len(mode)), dtype=np.uint8)
    flat[:] = (40, 90, 200, 255)[:len(mode)]
    flat[100:300, 50:200] = rng.integers(0, 256, (200, 150, len(mode)), dtype=np.uint8)
    smooth = np.cumsum(rng.integers(0, 3, (height, width, len(mode)), dtype=np.uint8), axis=1, dtype=np.uint8)
    for data in (flat, smooth):
        image = Image.fromarray(data, mode)
        for pool in (None, R.render_pool()):
            stream = io.BytesIO()
            writer = PngWriter(stream, image.size, mode, (300, 300), pool)
            top = 0
            for rows in (1, 31, 32, 33, 200, 220):
                writer.write(image.crop((0, top, width, top + rows)))
                top += rows
            assert top == height
            writer.close()
            decoded = Image.open(io.BytesIO(stream.getvalue()))
            decoded.load()
            assert decoded.mode == mode and decoded.tobytes() == image.tobytes()
            assert decoded.info["dpi"] == pytest.approx((300, 300), abs=0.02)


def test_the_png_writer_refuses_a_missing_or_misfit_band():
    writer = PngWriter(io.BytesIO(), (10, 10), "RGB")
    with pytest.raises(ValueError):
        writer.write(Image.new("RGB", (9, 4)))
    writer.write(Image.new("RGBA", (10, 4)))
    with pytest.raises(ValueError):
        writer.close()


def test_adler32_combine_matches_zlib():
    rng = random.Random(3)
    for _ in range(50):
        first, second = rng.randbytes(rng.randrange(0, 70000)), rng.randbytes(rng.randrange(0, 70000))
        assert adler32_combine(zlib.adler32(first), zlib.adler32(second), len(second)) == zlib.adler32(first + second)


def test_a_cancelled_or_failed_tiled_render_releases_what_it_held(monkeypatch):
    p = small_cache(large_layers())
    original = R._render_layers
    seen = []

    def failing(*args, **kwargs):
        seen.append(1)
        if len(seen) > 3:
            raise RuntimeError("stop")
        return original(*args, **kwargs)

    monkeypatch.setattr(R, "_render_layers", failing)
    with pytest.raises(RuntimeError):
        R.render_tiled(p, "white", tile=256)
    cache = R.layer_cache(p)
    assert not cache.held and not cache.regions
