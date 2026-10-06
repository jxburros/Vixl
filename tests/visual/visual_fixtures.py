"""Fixture documents for the visual regression suite, built through the public ``Project`` API.

Each builder takes no arguments and returns a small ``Project`` (at most 256 px a side). Add a fixture
by writing a builder and registering it in ``FIXTURES``; then run ``VIXL_UPDATE_GOLDEN=1 pytest tests/visual``.
"""

from PIL import Image, ImageDraw

from vixl import Project
from vixl.assets import add_image

FIXTURES = {}
SVG_FIXTURES = ("shapes_and_strokes", "path_stroke_only", "gradients", "text_plain", "groups")
PDF_FIXTURES = ("shapes_and_strokes", "path_stroke_only", "text_plain")
PPTX_FIXTURES = ("shapes_and_strokes", "text_plain", "groups")


def fixture(builder):
    FIXTURES[builder.__name__] = builder
    return builder


def doc(width=200, height=160, background="#f4efe6", ops=()):
    p = Project(width, height, background)
    if ops:
        p.apply(list(ops))
    return p


def rect(name, x, y, w, h, fill, **kw):
    return {"type": "shape", "shape": "rectangle", "name": name, "x": x, "y": y, "width": w, "height": h, "fill": fill, **kw}


def checker(size=48, cells=6, a="#d63c3c", b="#2c5aa0"):
    image = Image.new("RGBA", (size, size), a)
    draw = ImageDraw.Draw(image)
    step = size // cells
    for i in range(cells):
        for j in range(cells):
            if (i + j) % 2:
                draw.rectangle([i * step, j * step, (i + 1) * step - 1, (j + 1) * step - 1], fill=b)
    draw.ellipse([size // 4, size // 4, size * 3 // 4, size * 3 // 4], fill=(255, 255, 255, 255))
    return image


def photo(size=96):
    """A deterministic noisy gradient standing in for a photograph."""
    image = Image.new("RGB", (size, size))
    px = image.load()
    for y in range(size):
        for x in range(size):
            noise = ((x * 7919 + y * 104729 + x * y * 31) % 29) - 14
            px[x, y] = (
                max(0, min(255, 40 + x * 2 + noise)),
                max(0, min(255, 80 + y + noise)),
                max(0, min(255, 200 - x + noise)),
            )
    return image.convert("RGBA")


@fixture
def shapes_and_strokes():
    return doc(ops=[
        rect("box", 10, 10, 70, 50, "#e07a5f", stroke="#3d405b", stroke_width=4),
        {"type": "shape", "shape": "ellipse", "name": "disc", "x": 100, "y": 10, "width": 60, "height": 60, "fill": "#81b29a"},
        {"type": "shape", "shape": "rectangle", "name": "round", "x": 10, "y": 80, "width": 70, "height": 60,
         "fill": "#f2cc8f", "radius": 14, "stroke": "#3d405b", "stroke_width": 2},
        {"type": "shape", "shape": "polygon", "name": "hex", "x": 100, "y": 85, "width": 60, "height": 60, "sides": 6, "fill": "#3d405b"},
        {"type": "shape", "shape": "polygon", "name": "star", "x": 165, "y": 20, "width": 30, "height": 30, "sides": 5,
         "inner_radius": 0.4, "fill": "#e9c46a"},
    ])


@fixture
def path_open_default_fill():
    # An open path with no fill given: pins today's default fill for open shapes.
    return doc(ops=[
        {"type": "shape", "shape": "path", "name": "arc", "x": 20, "y": 20, "width": 160, "height": 120,
         "path": "M0 100 C30 -20 120 -20 160 100", "stroke": "#264653", "stroke_width": 4},
        {"type": "shape", "shape": "path", "name": "zig", "x": 20, "y": 100, "width": 160, "height": 40,
         "path": "M0 40 L40 0 L80 40 L120 0 L160 40"},
    ])


@fixture
def path_stroke_only():
    return doc(ops=[
        {"type": "shape", "shape": "path", "name": "loop", "x": 20, "y": 15, "width": 70, "height": 70,
         "path": "M35 0 C70 0 70 70 35 70 C0 70 0 0 35 0 Z", "fill": "transparent", "stroke": "#bc4749", "stroke_width": 5},
        {"type": "shape", "shape": "path", "name": "wave", "x": 20, "y": 100, "width": 160, "height": 40,
         "path": "M0 20 C27 -10 53 50 80 20 C107 -10 133 50 160 20", "fill": "transparent", "stroke": "#386641",
         "stroke_width": 6, "line_cap": "round"},
        {"type": "shape", "shape": "rectangle", "name": "frame", "x": 110, "y": 15, "width": 70, "height": 70,
         "fill": "transparent", "stroke": "#1d3557", "stroke_width": 3},
    ])


@fixture
def text_plain():
    return doc(ops=[
        {"type": "text", "text": "Vixl", "name": "title", "size": 44, "x": 14, "y": 10, "color": "#264653"},
        {"type": "text", "text": "Layered design,\nrendered small.", "name": "body", "size": 16, "x": 14, "y": 78, "color": "#333333"},
        {"type": "text", "text": "centered caption", "name": "cap", "size": 12, "x": 14, "y": 130, "color": "#6a6a6a"},
    ])


@fixture
def text_stroked():
    return doc(background="#264653", ops=[
        {"type": "text", "text": "Outline", "name": "outline", "size": 46, "x": 12, "y": 14, "color": "#e9c46a"},
        {"type": "text-set", "target": "outline", "stroke_color": "#ffffff", "stroke_width": 3},
        {"type": "text", "text": "Edge", "name": "edge", "size": 40, "x": 12, "y": 80, "color": "#00000000"},
        {"type": "text-set", "target": "edge", "stroke_color": "#f4a261", "stroke_width": 2},
    ])


@fixture
def rich_text():
    return doc(width=220, height=200, ops=[
        {"type": "rich-text", "name": "body", "markdown": "# Heading\nSome **bold** and *italic* text,\n- first item\n- second item\n\n[Colour]{color=#bc4749 size=22} run",
         "size": 15, "width": 196, "x": 12, "y": 10, "color": "#222222"},
    ])


@fixture
def gradients():
    return doc(width=240, height=160, ops=[
        {"type": "gradient", "name": "linear", "x": 10, "y": 10, "width": 100, "height": 60, "start": "#f94144", "end": "#277da1",
         "direction": "horizontal"},
        {"type": "gradient", "name": "radial", "x": 130, "y": 10, "width": 100, "height": 60, "start": "#ffffff", "end": "#1d3557",
         "direction": "radial"},
        {"type": "gradient", "name": "angled", "x": 10, "y": 85, "width": 100, "height": 60, "direction": "angled", "angle": 45,
         "stops": [{"offset": 0, "color": "#f9c74f"}, {"offset": 0.5, "color": "#90be6d"}, {"offset": 1, "color": "#577590"}]},
        {"type": "gradient", "name": "radial fade", "x": 130, "y": 85, "width": 100, "height": 60, "direction": "radial",
         "start": "#e63946", "end": "#e6394600"},
    ])


@fixture
def gradient_to_transparent():
    return doc(background="#1d3557", ops=[
        rect("band", 0, 60, 200, 40, "#f1faee"),
        {"type": "gradient", "name": "fade", "x": 10, "y": 10, "width": 180, "height": 140, "direction": "vertical",
         "start": "#e63946", "end": "#e6394600"},
        {"type": "gradient", "name": "white fade", "x": 10, "y": 110, "width": 180, "height": 40, "direction": "horizontal",
         "start": "#ffffff", "end": "#ffffff00"},
    ])


@fixture
def effect_blur_shadow_glow():
    return doc(ops=[
        rect("blurred", 10, 10, 60, 50, "#e76f51", radius=8),
        {"type": "effect", "target": "blurred", "name": "blur", "amount": 4},
        rect("shadowed", 100, 12, 60, 50, "#2a9d8f", radius=8),
        {"type": "layer-style", "target": "shadowed", "name": "drop-shadow",
         "settings": {"color": "#000000", "dx": 6, "dy": 8, "blur": 6, "opacity": 0.6}},
        {"type": "shape", "shape": "ellipse", "name": "glow", "x": 40, "y": 85, "width": 60, "height": 60, "fill": "#264653"},
        {"type": "layer-style", "target": "glow", "name": "outer-glow", "settings": {"color": "#ffd166", "blur": 12, "opacity": 0.9}},
        {"type": "shape", "shape": "ellipse", "name": "ringed", "x": 125, "y": 90, "width": 55, "height": 50, "fill": "#8ecae6"},
        {"type": "layer-style", "target": "ringed", "name": "stroke", "settings": {"color": "#023047", "width": 4}},
    ])


@fixture
def effect_denoise():
    p = doc(width=96, height=96, background="#000000")
    asset = add_image(p, photo(96))
    p.apply([
        {"type": "add", "asset": asset, "name": "photo", "x": 0, "y": 0},
        {"type": "effect", "target": "photo", "name": "denoise", "luminance": 70, "chroma": 70},
    ])
    return p


@fixture
def effect_lookup_lut():
    p = doc(width=200, height=100, ops=[
        {"type": "gradient", "name": "ramp", "x": 0, "y": 0, "width": 200, "height": 50, "start": "#ff0000", "end": "#0000ff",
         "direction": "horizontal"},
        {"type": "gradient", "name": "ramp2", "x": 0, "y": 50, "width": 200, "height": 50, "start": "#00ff00", "end": "#ffff00",
         "direction": "horizontal"},
    ])
    # A 2x2x2 cube that swaps channels and lifts shadows (red varies fastest).
    values = [[g * 0.9 + 0.1, b * 0.8, r] for b in (0, 1) for g in (0, 1) for r in (0, 1)]
    p.apply([
        {"type": "lut", "name": "swap", "size": 2, "values": values},
        {"type": "lookup", "target": "ramp", "name": "swap"},
        {"type": "lookup", "target": "ramp2", "name": "swap", "amount": 0.5},
    ])
    return p


@fixture
def effect_temperature_tint():
    p = doc(width=192, height=96, background="#000000")
    asset = add_image(p, photo(96))
    second = add_image(p, photo(96))
    p.apply([
        {"type": "add", "asset": asset, "name": "warm", "x": 0, "y": 0},
        {"type": "effect", "target": "warm", "name": "temperature", "amount": 40},
        {"type": "add", "asset": second, "name": "magenta", "x": 96, "y": 0},
        {"type": "effect", "target": "magenta", "name": "tint", "amount": 40},
    ])
    return p


@fixture
def raster_rotated_scaled():
    p = doc(width=200, height=160, background="#ffffff")
    asset = add_image(p, checker(48))
    p.apply([
        {"type": "add", "asset": asset, "name": "rot", "x": 20, "y": 30},
        {"type": "resize", "target": "rot", "width": 72, "height": 72},
        {"type": "rotate", "target": "rot", "value": 30},
        {"type": "add", "asset": asset, "name": "small", "x": 130, "y": 30},
        {"type": "rotate", "target": "small", "value": 45},
        {"type": "add", "asset": asset, "name": "magnified", "x": 20, "y": 110},
        {"type": "resize", "target": "magnified", "width": 36, "height": 36},
    ])
    return p


@fixture
def raster_on_dark_halo():
    # Rotating a light-edged raster over a dark background exposes fringing at the resampled edge.
    p = doc(width=160, height=160, background="#101820")
    image = Image.new("RGBA", (60, 60), (255, 255, 255, 255))
    ImageDraw.Draw(image).rectangle([10, 10, 49, 49], fill=(240, 90, 60, 255))
    asset = add_image(p, image)
    p.apply([
        {"type": "add", "asset": asset, "name": "tile", "x": 50, "y": 50},
        {"type": "rotate", "target": "tile", "value": 20},
    ])
    return p


@fixture
def blend_modes():
    ops = []
    modes = ["multiply", "screen", "overlay", "darken", "lighten", "difference", "add", "subtract"]
    for i, mode in enumerate(modes):
        x, y = 8 + (i % 4) * 48, 8 + (i // 4) * 70
        ops += [
            rect(f"base-{i}", x, y, 40, 60, "#4a7fb5"),
            {"type": "shape", "shape": "ellipse", "name": f"top-{i}", "x": x + 6, "y": y + 10, "width": 36, "height": 36, "fill": "#e8a33d"},
            {"type": "blend", "target": f"top-{i}", "value": mode},
        ]
    return doc(width=200, height=140, ops=ops)


@fixture
def groups():
    return doc(ops=[
        rect("card", 10, 10, 100, 80, "#ffffff", radius=8, stroke="#adb5bd", stroke_width=2),
        {"type": "shape", "shape": "ellipse", "name": "dot", "x": 22, "y": 22, "width": 30, "height": 30, "fill": "#e63946"},
        {"type": "text", "text": "Group", "name": "label", "size": 20, "x": 22, "y": 58, "color": "#1d3557"},
        {"type": "group", "name": "badge", "targets": ["card", "dot", "label"]},
        {"type": "move", "target": "badge", "x": 45, "y": 30},
        {"type": "opacity", "target": "badge", "value": 0.8},
        rect("under", 5, 100, 60, 50, "#2a9d8f"),
    ])


@fixture
def chart_bar():
    p = Project(240, 160, "#ffffff")
    p.apply({"type": "chart", "name": "Sales", "kind": "bar", "title": "Cups sold",
             "categories": ["Jan", "Feb", "Mar", "Apr"],
             "series": [{"name": "Cups", "values": [12, 18, 15, 24]}]})
    return p


@fixture
def chart_line():
    p = Project(240, 160, "#ffffff")
    p.apply({"type": "chart", "name": "Trend", "kind": "line", "title": "Trend",
             "categories": ["Q1", "Q2", "Q3", "Q4"],
             "series": [{"name": "A", "values": [4, 9, 7, 14]}, {"name": "B", "values": [10, 8, 12, 9]}]})
    return p


@fixture
def organic_starfish():
    p = Project(200, 200, "#f1faee")
    p.apply({"type": "organic", "preset": "starfish", "name": "star", "seed": 4, "width": 170, "height": 170, "x": 15, "y": 15})
    return p


@fixture
def irregular_torn():
    return doc(ops=[
        rect("sheet", 20, 20, 160, 110, "#fefae0", stroke="#bc6c25", stroke_width=2),
        {"type": "irregular", "target": "sheet", "seed": 3, "strength": "rough"},
        {"type": "shape", "shape": "ellipse", "name": "blob", "x": 60, "y": 40, "width": 80, "height": 60, "fill": "#dda15e"},
        {"type": "irregular", "target": "blob", "seed": 7},
    ])
