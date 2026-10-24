"""Fixture documents for the visual regression suite, built through the public ``Project`` API.

Each builder takes no arguments and returns a small ``Project`` (at most 256 px a side). Add a fixture
by writing a builder and registering it in ``FIXTURES``; then run ``VIXL_UPDATE_GOLDEN=1 pytest tests/visual``.
"""

from PIL import Image, ImageDraw

from vixl import Project
from vixl.assets import add_image

FIXTURES = {}
SVG_FIXTURES = ("shapes_and_strokes", "path_stroke_only", "gradients", "text_plain", "groups", "dashes_fitted",
                "text_small_caps", "text_hanging_quote")
PDF_FIXTURES = ("shapes_and_strokes", "path_stroke_only", "text_plain", "dashes_fitted", "text_small_caps",
                "text_hanging_quote")
PPTX_FIXTURES = ("shapes_and_strokes", "text_plain", "groups", "dashes_fitted", "text_small_caps", "text_hanging_quote")


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
def effect_white_balance():
    # A neutral picked from a cast, explicit gains, and the effect at half strength.
    p = doc(width=192, height=96, background="#000000")
    left, middle, right = (add_image(p, photo(64)) for _ in range(3))
    p.apply([
        {"type": "add", "asset": left, "name": "neutral", "x": 0, "y": 16},
        {"type": "white-balance", "target": "neutral", "neutral": "#6a7cb4"},
        {"type": "add", "asset": middle, "name": "gains", "x": 64, "y": 16},
        {"type": "white-balance", "target": "gains", "gains": [1.3, 1.0, 0.7]},
        {"type": "add", "asset": right, "name": "half", "x": 128, "y": 16},
        {"type": "white-balance", "target": "half", "gains": [1.3, 1.0, 0.7], "amount": 50},
    ])
    return p


@fixture
def effect_stack_rotated():
    # Effects run in the layer's frame before it turns: a LUT moved first, blur spreading past the
    # turned box, and an emboss whose light stays at the canvas's top left.
    p = doc(width=200, height=120, background="#20242c")
    asset = add_image(p, checker(48))
    values = [[g * 0.9 + 0.1, b * 0.8, r] for b in (0, 1) for g in (0, 1) for r in (0, 1)]
    p.apply([
        {"type": "lut", "name": "swap", "size": 2, "values": values},
        {"type": "add", "asset": asset, "name": "soft", "x": 20, "y": 30},
        {"type": "resize", "target": "soft", "width": 60, "height": 60},
        {"type": "rotate", "target": "soft", "value": 25},
        {"type": "blur", "target": "soft", "amount": 2},
        {"type": "lookup", "target": "soft", "name": "swap"},
        {"type": "effect-move", "target": "soft", "effect": "lookup", "to": "top"},
        {"type": "add", "asset": asset, "name": "relief", "x": 120, "y": 30},
        {"type": "resize", "target": "relief", "width": 60, "height": 60},
        {"type": "rotate", "target": "relief", "value": -40},
        {"type": "emboss", "target": "relief", "amount": 60},
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


@fixture
def dashes_fitted():
    # Dash patterns fitted to corners (rounded, notched, sharp) and a dotted ring with round dots.
    return doc(240, 170, "#ffffff", ops=[
        rect("card", 12, 12, 100, 70, "transparent", radius=16, stroke="#1d3557", stroke_width=4, dash=[12, 8]),
        {"type": "shape", "shape": "ticket", "name": "coupon", "x": 128, "y": 12, "width": 100, "height": 70,
         "fill": "#e63946", "stroke": "#fff1e6", "stroke_width": 3, "dash": [9, 6]},
        {"type": "shape", "shape": "ellipse", "name": "ring", "x": 16, "y": 100, "width": 56, "height": 56,
         "fill": "transparent", "stroke": "#2a9d8f", "stroke_width": 3, "dash": "dotted"},
        {"type": "shape", "shape": "path", "name": "zig", "x": 90, "y": 108, "width": 140, "height": 44,
         "path": "M0 40 L35 4 L70 40 L105 4 L140 40", "fill": "none", "stroke": "#264653", "stroke_width": 3,
         "dash": [8, 5]},
    ])


@fixture
def finish_glow_shadow():
    # Default glow on a dark ground (a lighter tint that adds light) and a default shadow on a light one (the
    # ground in shade, small and light).
    p = doc(240, 160, "#14213d", ops=[
        rect("bar", 30, 40, 40, 90, "#f59e0b"),
        {"type": "look", "target": "bar", "look": "glow", "amount": 0.8},
        rect("panel", 120, 20, 110, 120, "#f3e9d2"),
        rect("button", 140, 60, 70, 34, "#c1121f"),
        {"type": "group", "name": "card", "targets": ["panel", "button"]},
        {"type": "look", "target": "button", "look": "soft-shadow", "amount": 0.8},
    ])
    return p


@fixture
def text_small_caps():
    # Small caps synthesized from capitals (DejaVu Sans has no smcp), from a font's own small capitals (Noto Sans
    # has smcp), and on one rich-text span.
    from pathlib import Path

    import vixl
    from vixl.fonts import import_font

    p = doc(220, 150)
    import_font(p, str(Path(vixl.__file__).parent / "data" / "NotoSans-Regular.ttf"), "noto")
    p.apply([
        {"type": "text", "text": "Small Caps", "name": "synthesized", "size": 30, "x": 12, "y": 10,
         "color": "#264653", "text_transform": "small-caps"},
        {"type": "text", "text": "Small Caps", "name": "smcp", "font": "noto", "size": 30, "x": 12, "y": 54,
         "color": "#264653", "text_transform": "small-caps"},
        {"type": "rich-text", "name": "span", "markdown": "In [small caps]{small-caps} now", "size": 16, "x": 12,
         "y": 108, "color": "#333333"},
    ])
    return p


@fixture
def text_hanging_quote():
    # Hanging punctuation: the opening quote of a boxed paragraph sits left of the margin rule, the letters on it;
    # the closing quote of a right-aligned line hangs past the right rule.
    return doc(220, 150, ops=[
        rect("margin-left", 22, 8, 1, 134, "#e07a5f"),
        rect("margin-right", 198, 8, 1, 134, "#e07a5f"),
        {"type": "text", "text": "“Hang the quote,” she said, “and the line reads straight.”",
         "name": "quote", "size": 18, "x": 23, "y": 12, "color": "#1d3557", "hanging_punctuation": True},
        {"type": "text-layout", "target": "quote", "width": 175},
        {"type": "text", "text": "— “The end.”", "name": "signoff", "size": 18, "x": 23, "y": 108,
         "color": "#1d3557", "align": "right", "hanging_punctuation": True},
        {"type": "text-layout", "target": "signoff", "width": 175},
    ])


_MERCH = {}


def _merch_views():
    """The front of a tee and of a hoodie and a die-cut sticker, built by the mockup workflow around one badge and
    reduced to thumbnails (rendered once per process)."""
    if not _MERCH:
        import tempfile
        from pathlib import Path

        from vixl.interfaces import Session
        from vixl.workflows import dispatch

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            badge = Project(400, 400, "transparent")
            badge.apply([
                {"type": "shape", "shape": "ellipse", "name": "sun", "x": 20, "y": 20, "width": 360, "height": 360,
                 "fill": "#f4a261"},
                {"type": "shape", "shape": "ellipse", "name": "core", "x": 80, "y": 80, "width": 240, "height": 240,
                 "fill": "#e9c46a"},
                rect("wave", 20, 230, 360, 50, "#2a9d8f"),
                rect("deep", 20, 300, 360, 50, "#264653"),
            ])
            badge.save(root / "badge.vixl")
            session = Session(root / "badge.vixl", workspace=root)
            for name, colour, crop in (("tee", "#2b3a55", (0, 0, 1100, 1000)),
                                       ("hoodie", "#9c3d3d", (0, 0, 1100, 990)),
                                       ("sticker", None, (240, 240, 960, 960))):
                dispatch(session, "mockup", {"mockup": name, "output": f"{name}.vixl", "design": "badge.vixl",
                                             **({"garment_color": colour} if colour else {})})
                mockup = Project.load(root / f"{name}.vixl")
                mockup._workspace = root
                view = mockup.render().convert("RGBA").crop(crop)
                _MERCH[name] = view.resize((84, round(84 * view.height / view.width)), Image.Resampling.BOX)
    return _MERCH


@fixture
def merch_tee_hoodie_sticker():
    # The vector merch mockups: a garment colour on a tee and a hoodie with the art on the chest, and a die-cut sticker
    # whose border follows the art.
    p = doc(256, 96, "#e6e9ee")
    for i, view in enumerate(_merch_views().values()):
        p.apply({"type": "add", "asset": add_image(p, view), "name": f"view-{i}", "x": 2 + i * 85,
                 "y": (96 - view.height) // 2})
    return p
