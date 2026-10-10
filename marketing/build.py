"""Vixl marketing kit: social cards, print, a pitch deck and a motion teaser, all made with Vixl.

Run from the repo root:

    python marketing/build.py            # build everything
    python marketing/build.py og deck    # build only some pieces

Every piece is written to marketing/output/<piece>/ as an editable .vixl master plus its exports.
The Digital Shift logo is placed as a live link to the masters in assets/brand/digital-shift/Editable-Vixl,
so a logo update flows into every piece on the next build.
"""

import json
import os
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
OUT = HERE / "output"
os.environ.setdefault("VIXL_NO_UPDATE", "1")
os.chdir(ROOT)  # link sources resolve against the workspace (repo root)

from vixl import Project  # noqa: E402
from vixl.typefaces import install_font  # noqa: E402

# Brand (assets/brand/digital-shift/START-HERE.md) ----------------------------------------------
CHARCOAL = "#252B39"
DEEP = "#1A1F2B"
PANEL = "#2F3647"
LINE = "#3C4458"
BLUE = "#3575EE"
SKY = "#6A9AFF"
WHITE = "#FFFFFF"
MUTED = "#AEB7CA"
PAPER = "#F5F7FB"
INK = CHARCOAL
SUBTLE = "#5B6478"
CODE_KEY = "#8FB4FF"
CODE_STR = "#9FE3B4"
CODE_NUM = "#FFC37A"

LOGOS = "assets/brand/digital-shift/Editable-Vixl"
HEAD, BODY, SEMI, MONO = "inter-tight-800", "inter-400", "inter-600", "jetbrains-mono-500"

# Facts used in the copy (counted from the 0.21.0 source; see README.md in this folder).
VERSION = "0.21.0"
FACTS = {"operations": 180, "sizes": 150, "layouts": 47, "styles": 28, "looks": 17, "brushes": 17,
         "templates": 40, "containers": 19, "batch": "10,000"}
INTERFACES = ["MCP", "CLI", "Python", "REST"]
FORMATS = ["PNG", "JPEG", "WEBP", "TIFF", "AVIF", "SVG", "PDF", "PPTX", "HTML", "ICO", "GIF", "MP4"]
TAGLINE = "The image editor your AI agent can actually use."
SUB = "Create, inspect, edit, measure and export layered designs through MCP, CLI, Python or REST."
REPO = "github.com/jxburros/Vixl"


# Helpers ---------------------------------------------------------------------------------------
def new(width, height, background=CHARCOAL, **kw):
    p = Project(width, height, background, **kw)
    p._workspace = str(ROOT)  # logo links resolve against the repo root
    install_font(p, "Inter Tight", 800, role="heading")
    install_font(p, "Inter", 400, role="body")
    install_font(p, "Inter", 600)
    install_font(p, "JetBrains Mono", 500)
    p.apply([
        {"type": "swatch", "name": "brand", "color": BLUE},
        {"type": "swatch", "name": "sky", "color": SKY},
        {"type": "swatch", "name": "charcoal", "color": CHARCOAL},
    ], detail="brief")
    return p


def bounds(p, name):
    """The layer's box on the canvas, grouped or not (``space="parent"`` gives it in its group's coordinates)."""
    return p.bounds(name)


def logo(name, variant, x, y, width=None, height=None):
    op = {"type": "link", "name": name, "source": f"{LOGOS}/{variant}.vixl", "x": x, "y": y, "fit": "fit"}
    if width:
        op["width"] = width
    if height:
        op["height"] = height
    return op


def pixels(prefix, seed, area, count, size_range, colors, opacity=(0.25, 1.0)):
    """Scattered square 'pixels', the motif taken from the logo's detached pixels."""
    rng = random.Random(seed)
    x0, y0, w, h = area
    ops = []
    for i in range(count):
        s = rng.choice(range(size_range[0], size_range[1] + 1, 2))
        alpha = round(rng.uniform(*opacity) * 255)
        ops.append({"type": "shape", "shape": "rectangle", "name": f"{prefix}-{i}",
                    "x": x0 + rng.randrange(max(1, w - s)), "y": y0 + rng.randrange(max(1, h - s)),
                    "width": s, "height": s, "fill": f"{rng.choice(colors)}{alpha:02X}"})
    return ops


def pixel_stair(prefix, x, y, cell, gap, steps, color=BLUE, fade=True):
    """A diagonal run of pixels that echoes the offset V shapes of the mark."""
    ops = []
    for i in range(steps):
        alpha = 255 - int(i * (200 / max(1, steps - 1))) if fade else 255
        ops.append({"type": "shape", "shape": "rectangle", "name": f"{prefix}-{i}",
                    "x": x + i * (cell + gap), "y": y + i * (cell + gap) // 2,
                    "width": cell, "height": cell, "fill": f"{color}{alpha:02X}"})
    return ops


def dot_grid(name, x, y, width, height, step, color="#FFFFFF14", dot=3):
    return [
        {"type": "shape", "shape": "ellipse", "name": name, "x": x, "y": y, "width": dot, "height": dot,
         "fill": color},
        {"type": "repeat", "target": name, "count": max(1, width // step), "dx": step, "dy": 0},
        {"type": "group", "name": f"{name}-row", "targets": [name]},
        {"type": "repeat", "target": f"{name}-row", "count": max(1, height // step), "dx": 0, "dy": step},
        {"type": "layer-intent", "target": f"{name}-row", "role": "decoration"},
    ]


def chip(p, name, text, x, y, size=22, fg=WHITE, bg=PANEL, stroke=None, pad=(18, 10), font=SEMI,
         radius=None):
    """Pill label: text first (to measure its ink box), then a capsule centred behind it."""
    p.apply({"type": "text", "name": f"{name}-label", "text": text, "font": font, "size": size,
             "color": fg, "x": x + pad[0], "y": y}, detail="brief")
    _, ly, lw, _ = bounds(p, f"{name}-label")
    cap = size * 0.72  # cap height of Inter: centre on it so descenders do not push the label up
    w, h = round(lw + 2 * pad[0]), round(cap + 2 * pad[1] + size * 0.3)
    bg_op = {"type": "shape", "shape": "rounded-rectangle", "name": f"{name}-bg", "x": x, "y": y,
             "width": w, "height": h, "radius": radius if radius is not None else h / 2, "fill": bg}
    if stroke:
        bg_op.update(stroke=stroke, stroke_width=2)
    top_gap = ly - y  # distance from the text box top to its ink top
    p.apply([bg_op,
             {"type": "move", "target": f"{name}-label", "x": x + pad[0], "y": y + (h - cap) / 2 - top_gap},
             {"type": "lower", "target": f"{name}-bg"},
             {"type": "group", "name": name, "targets": [f"{name}-bg", f"{name}-label"]}], detail="brief")
    return x, y, w, h


def chips_row(p, prefix, labels, x, y, gap=12, **kw):
    cx = x
    boxes = []
    for i, label in enumerate(labels):
        box = chip(p, f"{prefix}-{i}", label, cx, y, **kw)
        boxes.append(box)
        cx += box[2] + gap
    return boxes


def code_card(name, x, y, width, lines, size=22, title="design.json", height=None, chrome=True):
    """A dark editor window holding syntax-coloured lines; each line is (indent level, [(text, color)])."""
    top = 58 if chrome else 28
    line = size * 1.5
    h = height or round(top + 30 + line * len(lines))
    ops = [
        {"type": "shape", "shape": "rounded-rectangle", "name": f"{name}-bg", "x": x, "y": y,
         "width": width, "height": h, "radius": 18, "fill": DEEP, "stroke": LINE, "stroke_width": 2},
    ]
    if chrome:
        for i, c in enumerate(["#FF6B6B", "#FFC37A", "#5FD38D"]):
            ops.append({"type": "shape", "shape": "ellipse", "name": f"{name}-dot{i}", "x": x + 24 + i * 22,
                        "y": y + 22, "width": 12, "height": 12, "fill": c})
        ops.append({"type": "text", "name": f"{name}-title", "text": title, "font": MONO, "size": max(20, round(size * 0.8)),
                    "color": MUTED, "x": x + 100, "y": y + 18})
    spans, paragraphs = [], []
    for i, (indent, runs) in enumerate(lines):
        spans.extend({"text": text, "color": color} for text, color in runs)
        if i < len(lines) - 1:
            spans.append({"text": "\n"})
        paragraphs.append({"indent": round(indent * 2 * size * 0.6)})
    ops.append({"type": "rich-text", "name": f"{name}-code", "spans": spans, "paragraphs": paragraphs,
                "font": MONO, "size": size, "color": WHITE, "line_height": 1.25, "x": x + 28, "y": y + top + 6,
                "width": width - 56})
    ops.append({"type": "group", "name": name, "targets": [o["name"] for o in ops]})
    return ops


def op_line(indent, key, value, color, last=False):
    return (indent, [(f'"{key}"', CODE_KEY), (": ", WHITE), (value, color), ("" if last else ",", WHITE)])


SNIPPET = [
    (0, [("[", WHITE)]),
    (1, [("{", WHITE)]),
    op_line(2, "type", '"layout-apply"', CODE_STR),
    op_line(2, "name", '"hero-statement"', CODE_STR),
    op_line(2, "title", '"Launch day"', CODE_STR),
    op_line(2, "seed", "7", CODE_NUM, last=True),
    (1, [("},", WHITE)]),
    (1, [("{", WHITE), ('"type"', CODE_KEY), (": ", WHITE), ('"look"', CODE_STR), (", ", WHITE),
         ('"look"', CODE_KEY), (": ", WHITE), ('"glow"', CODE_STR), ("}", WHITE)]),
    (0, [("]", WHITE)]),
]


def save_and_export(p, folder, stem, exports, check=True, **check_options):
    folder = OUT / folder
    folder.mkdir(parents=True, exist_ok=True)
    p.save(str(folder / f"{stem}.vixl"))
    report = {}
    if check:
        result = p.check(**check_options)
        report = {"issues": [{k: i.get(k) for k in ("check", "severity", "action", "layer", "message")}
                             for i in result.get("issues", [])]}
        fixes = [i for i in report["issues"] if i["action"] == "fix"]
        print(f"  check {stem}: {len(report['issues'])} issues, {len(fixes)} to fix")
        for issue in report["issues"]:
            print("   ", issue["action"].upper(), issue["check"], (issue["message"] or "")[:150])
        (folder / f"{stem}.check.json").write_text(json.dumps(report, indent=2) + "\n")
    for ext, options in exports:
        path = folder / f"{stem}.{ext}"
        p.export(str(path), overwrite=True, **options)
        print("  wrote", path.relative_to(ROOT))
    return report


def sheet(p, path, **options):
    from vixl.deck import contact_sheet

    contact_sheet(p, **options).convert("RGB").save(path)
    print("  wrote", Path(path).relative_to(ROOT))


# Layout helpers --------------------------------------------------------------------------------
def headline(name, text, x, y, size, accent=None, color=WHITE, width=None, align="left", line_height=0.92,
             accent_color=SKY):
    """Display type as rich text so the accent phrase can change colour and the leading stays tight."""
    spans = [{"text": text}]
    if accent and accent in text:
        before, after = text.split(accent, 1)
        spans = [s for s in ({"text": before}, {"text": accent, "color": accent_color}, {"text": after}) if s["text"]]
    op = {"type": "rich-text", "name": name, "spans": spans, "font": HEAD, "size": size, "color": color,
          "line_height": line_height, "align": align, "x": x, "y": y}
    if width:
        op["width"] = width
    return op


def bottom(p, name):
    x, y, w, h = bounds(p, name)
    return y + h


# Showcase: real outputs from the repo's explorations and docs, every one of them made with Vixl.
SHOW = {
    "poster": ("Print poster", "explorations/01-print-concert-poster/output/poster-rgb.png"),
    "painting": ("Generative painting", "explorations/05-generative-painting/output/painting.jpg"),
    "pixel": ("Pixel-art game", "explorations/04-pixel-rpg/output/title@4x-nearest.png"),
    "map": ("Tile maps", "explorations/04-pixel-rpg/output/map@3x.png"),
    "donut": ("Data infographic", "explorations/08-infographic/output/social-donut-1080.png"),
    "film": ("Character animation", "explorations/10-character-film/output/film-shot2.png"),
    "photo": ("Photo editing", "explorations/06-photo-lab/output/after.jpg"),
    "campaign": ("Brand campaign", "explorations/09-collab-campaign/output/00-overview.png"),
    "chart": ("Editable charts", "docs/assets/generated/chart.png"),
    "watercolor": ("Artistic filters", "explorations/05-generative-painting/output/variant-watercolor.jpg"),
}


def photo(name, key, x, y, w, h, radius=18, base=PANEL):
    """A showcase image cropped into a rounded frame (frame + clip, both editable)."""
    return [
        {"type": "shape", "shape": "rounded-rectangle", "name": f"{name}-base", "x": x, "y": y,
         "width": w, "height": h, "radius": radius, "fill": base},
        {"type": "frame", "name": name, "path": SHOW[key][1], "x": x, "y": y, "width": w, "height": h,
         "fit": "fill"},
        {"type": "clip", "target": name, "base": f"{name}-base"},
    ]


def fit_code(p, name, pad=30):
    """Grow a code card's background to the measured height of its code."""
    _, by, _, _ = bounds(p, f"{name}-bg")
    _, cy, _, ch = bounds(p, f"{name}-code")
    p.apply({"type": "resize", "target": f"{name}-bg", "height": round(cy + ch + pad - by)}, detail="brief")


def text(name, value, x, y, size, color=MUTED, font=BODY, **extra):
    return {"type": "text", "name": name, "text": value, "font": font, "size": size, "color": color, "x": x,
            "y": y, **extra}


def para(name, value, x, y, size, width, color=MUTED, font=BODY, line_height=1.3, align="left"):
    return {"type": "rich-text", "name": name, "spans": [{"text": value}], "font": font, "size": size,
            "color": color, "line_height": line_height, "x": x, "y": y, "width": width, "align": align}


def glow(name, x, y, size, color=BLUE, strength="55"):
    return {"type": "gradient", "name": name, "direction": "radial", "width": size, "height": size, "x": x, "y": y,
            "stops": [{"offset": 0, "color": f"{color}{strength}"}, {"offset": 0.6, "color": f"{color}10"},
                      {"offset": 1, "color": f"{color}00"}]}


LOOP = [("Inspect", "Read layers, bounds and fonts"), ("Apply", "Atomic batches, up to 10,000 ops"),
        ("Check", "Contrast, overlap, bounds, print"), ("Preview", "Render and look"),
        ("Export", "PNG, SVG, PDF, PPTX, MP4 ...")]

MAKES = ["Posters & social", "Charts & diagrams", "Slides & decks", "Fillable forms", "Motion & GIFs",
         "Pixel art & sprites", "Paintings & filters", "CMYK print PDFs"]


def loop_steps(p, prefix, x, y, width, size=30, vertical=False, dark=True, step_h=None):
    """The inspect -> apply -> check -> preview -> export loop as numbered cards."""
    fg, sub, card, num = (WHITE, MUTED, PANEL, SKY) if dark else (INK, SUBTLE, WHITE, "#2A62D6")
    n = len(LOOP)
    ops = []
    if vertical:
        h = step_h or round(size * 3.3)
        for i, (title, desc) in enumerate(LOOP):
            cy = y + i * (h + 18)
            ops += [
                {"type": "shape", "shape": "rounded-rectangle", "name": f"{prefix}-card{i}", "x": x, "y": cy,
                 "width": width, "height": h, "radius": 20, "fill": card,
                 **({} if dark else {"stroke": "#DCE2EE", "stroke_width": 2})},
                text(f"{prefix}-num{i}", f"0{i + 1}", x + 32, cy + h / 2 - size * 0.62, round(size * 1.1), num, HEAD),
                text(f"{prefix}-title{i}", title, x + 32 + size * 2.6, cy + h / 2 - size * 0.95, size, fg, HEAD),
                text(f"{prefix}-desc{i}", desc, x + 32 + size * 2.6, cy + h / 2 + size * 0.2, round(size * 0.62), sub),
            ]
    else:
        gap = 20
        w = (width - gap * (n - 1)) / n
        h = step_h or round(size * 4.2)
        for i, (title, desc) in enumerate(LOOP):
            cx = x + i * (w + gap)
            ops += [
                {"type": "shape", "shape": "rounded-rectangle", "name": f"{prefix}-card{i}", "x": round(cx), "y": y,
                 "width": round(w), "height": h, "radius": 18, "fill": card,
                 **({} if dark else {"stroke": "#DCE2EE", "stroke_width": 2})},
                text(f"{prefix}-num{i}", f"0{i + 1}", round(cx + 26), y + 24, round(size * 0.7), num, HEAD),
                text(f"{prefix}-title{i}", title, round(cx + 26), y + 24 + size * 1.1, size, fg, HEAD),
                para(f"{prefix}-desc{i}", desc, round(cx + 26), round(y + 24 + size * 2.5), round(size * 0.55),
                     round(w - 52), sub),
            ]
            if i < n - 1:
                ops.append({"type": "shape", "shape": "chevron", "name": f"{prefix}-arrow{i}",
                            "x": round(cx + w + gap / 2 - 6), "y": round(y + h / 2 - 9), "width": 12, "height": 18,
                            "fill": num})
    p.apply(ops, detail="brief")


# Pieces ---------------------------------------------------------------------------------------
def build_github():
    """GitHub social preview, 1280 x 640, light treatment."""
    W, H = 1280, 640
    p = new(W, H, PAPER)
    p.apply([
        *dot_grid("grid", 20, 20, 660, H - 20, 30, "#252B3912"),
        logo("logo", "horizontal-color", 64, 60, width=230),
        headline("headline", "Editable image\ndocuments for\nAI agents.", 64, 190, 66, "AI agents.", INK,
                 accent_color=BLUE),
        *photo("show-poster", "poster", 712, 48, 252, 352),
        *photo("show-pixel", "pixel", 712, 416, 252, 176),
        *photo("show-painting", "painting", 980, 48, 252, 236),
        *photo("show-film", "photo", 980, 300, 252, 292),
    ], detail="brief")
    p.apply([
        {"type": "look", "targets": ["show-poster-base", "show-pixel-base", "show-painting-base", "show-film-base"],
         "look": "soft-shadow", "color": "#252B39", "amount": 0.4},
        para("sub", "Create, inspect, edit, check and export layered designs. No GUI required.", 64,
             bottom(p, "headline") + 28, 25, 560, SUBTLE),
    ], detail="brief")
    chips_row(p, "iface", INTERFACES, 64, bottom(p, "sub") + 30, size=20, fg=INK, bg=WHITE, stroke="#D5DBE7")
    save_and_export(p, "social", "github-preview-1280x640", [("png", {})], thumbnail_width=640)


def build_og():
    """Open Graph / link-preview card, 1200 x 630."""
    W, H = 1200, 630
    p = new(W, H, CHARCOAL)
    p.apply([
        glow("glow", 520, -300, 1100),
        *dot_grid("grid", 24, 24, W - 24, H - 24, 32, "#FFFFFF10"),
        logo("logo", "horizontal-reverse", 64, 56, width=240),
        headline("headline", "The image editor\nyour AI agent can\nactually use.", 64, 178, 62, "actually use."),
        *code_card("code", 670, 118, 480, SNIPPET, size=20),
        *pixel_stair("stair", 1018, 540, 16, 8, 5, SKY),
    ], detail="brief")
    fit_code(p, "code")
    p.apply([
        text("sub", "Layered, editable designs\nthrough MCP, CLI, Python and REST.", 64, bottom(p, "headline") + 30,
             26, MUTED),
        {"type": "look", "target": "code", "look": "soft-shadow", "color": "#000000"},
    ], detail="brief")
    chips_row(p, "tag", [f"v{VERSION}", "No GUI required", "Editable .vixl masters"], 64, bottom(p, "sub") + 34,
              size=20)
    save_and_export(p, "social", "og-card-1200x630", [("png", {})], thumbnail_width=600)


def build_linkedin():
    """LinkedIn page banner, 1584 x 396. The left fifth stays quiet for the profile picture."""
    W, H = 1584, 396
    p = new(W, H, CHARCOAL)
    p.apply([
        glow("glow", 900, -500, 1300),
        *dot_grid("grid", 16, 16, W - 16, H - 16, 28, "#FFFFFF0E"),
        *pixels("px", 4, (0, 0, 420, 396), 26, (8, 22), [BLUE, SKY], (0.15, 0.6)),
        headline("headline", "Design work, as\noperations your agent runs.", 470, 92, 58, "operations"),
        logo("logo", "horizontal-reverse", W - 262, 60, width=230),
    ], detail="brief")
    chips_row(p, "fmt", ["PNG", "SVG", "PDF", "PPTX", "HTML", "GIF", "MP4", "WAV", "CMYK"], 470, bottom(p, "headline") + 40,
              size=20, fg=WHITE, bg=PANEL)
    p.apply(text("url", REPO, W - 70, 316, 22, MUTED, MONO), detail="brief")
    x, y, w, h = bounds(p, "url")
    p.apply({"type": "move", "target": "url", "x": W - 70 - w, "y": 316}, detail="brief")
    save_and_export(p, "social", "linkedin-banner-1584x396", [("png", {})], thumbnail_width=792)


def build_carousel():
    """Six-slide Instagram/LinkedIn carousel, 1080 x 1350, exported as PDF and one PNG per slide."""
    W, H = 1080, 1350
    p = new(W, H, CHARCOAL)
    M = 88

    p.apply([{"type": "master", "action": "add", "name": "frame", "background": CHARCOAL},
             *dot_grid("m-grid", 24, 24, W - 24, H - 24, 36, "#FFFFFF0D"),
             logo("m-logo", "horizontal-reverse", M, H - 118, width=168),
             text("m-num", "${page} / ${pages}", W - M - 70, H - 96, 24, MUTED, MONO)], detail="brief")

    def page(name, notes=""):
        p.apply({"type": "page", "action": "add", "name": name, "master": "frame", "notes": notes}, detail="brief")

    # 1 - cover
    page("cover")
    p.apply([
        glow("c-glow", -200, -200, 1400),
        logo("c-mark", "mark-reverse", W - 470, 150, width=400),
        text("c-kicker", "VIXL  /  " + VERSION, M, 180, 26, SKY, MONO),
        headline("c-title", "Design is\nnow an\nAPI call.", M, 520, 150, "API call."),
    ], detail="brief")
    p.apply([para("c-sub", "An editable image-document engine for AI agents. Swipe to see how it works.", M,
                  bottom(p, "c-title") + 44, 34, 760, MUTED)], detail="brief")

    # 2 - the problem
    page("problem")
    p.apply([
        text("p-kicker", "THE PROBLEM", M, 150, 26, SKY, MONO),
        headline("p-title", "Design tools are\nbuilt for hands,\nnot agents.", M, 220, 92, "not agents."),
    ], detail="brief")
    y = bottom(p, "p-title") + 80
    points = [("Click-only editors", "An agent cannot drag a slider it cannot see."),
              ("Flattened exports", "One PNG back, and every layer is gone."),
              ("Guess-and-hope", "No way to know the text overflowed until a human looks.")]
    ops = []
    for i, (t, d) in enumerate(points):
        yy = y + i * 190
        ops += [{"type": "shape", "shape": "rectangle", "name": f"p-px{i}", "x": M, "y": yy + 10, "width": 22,
                 "height": 22, "fill": BLUE},
                text(f"p-t{i}", t, M + 56, yy, 44, WHITE, HEAD),
                para(f"p-d{i}", d, M + 56, yy + 66, 32, 820, MUTED)]
    p.apply(ops, detail="brief")

    # 3 - the loop
    page("loop")
    p.apply([text("l-kicker", "HOW IT WORKS", M, 150, 26, SKY, MONO),
             headline("l-title", "One loop.\nEvery design.", M, 220, 92, "Every design.")], detail="brief")
    loop_steps(p, "l", M, bottom(p, "l-title") + 60, W - 2 * M, size=40, vertical=True, step_h=122)

    # 4 - what you can make (real outputs)
    page("gallery")
    p.apply([text("g-kicker", "MADE WITH VIXL", M, 150, 26, SKY, MONO),
             headline("g-title", "Not a toy.\nA whole studio.", M, 220, 92, "A whole studio.")], detail="brief")
    top = bottom(p, "g-title") + 60
    gw, gh, gap = (W - 2 * M - 24) // 2, 214, 24
    keys = ["poster", "painting", "pixel", "donut", "film", "photo"]
    ops = []
    for i, key in enumerate(keys):
        cx, cy = M + (i % 2) * (gw + gap), top + (i // 2) * (gh + gap)
        ops += photo(f"g-{key}", key, cx, cy, gw, gh)
    p.apply(ops, detail="brief")
    ops = []
    for i, key in enumerate(keys):
        cx, cy = M + (i % 2) * (gw + gap), top + (i // 2) * (gh + gap)
        ops.append(chip_ops(f"g-lab{i}", SHOW[key][0], cx + 14, cy + gh - 60, size=24))
    for o in ops:
        chip(p, *o)

    # 5 - numbers
    page("numbers")
    p.apply([text("n-kicker", "IN THE BOX", M, 150, 26, SKY, MONO),
             headline("n-title", "Batteries,\nincluded.", M, 220, 92, "included.")], detail="brief")
    top = bottom(p, "n-title") + 70
    stats = [(FACTS["operations"], "operations"), (FACTS["sizes"], "named sizes"), (FACTS["layouts"], "layouts"),
             (FACTS["templates"], "templates"), (FACTS["styles"], "design styles"), (FACTS["looks"], "finishing looks")]
    ops = []
    for i, (n, label) in enumerate(stats):
        cx, cy = M + (i % 2) * 460, top + (i // 2) * 200
        ops += [text(f"n-v{i}", str(n), cx, cy, 120, WHITE if i % 3 else SKY, HEAD),
                text(f"n-l{i}", label, cx + 4, cy + 136, 36, MUTED)]
    p.apply(ops, detail="brief")

    # 6 - CTA
    page("start")
    p.apply([glow("s-glow", 100, 300, 1200, BLUE, "66"),
             text("s-kicker", "GET STARTED", M, 150, 26, SKY, MONO),
             headline("s-title", "Give your agent\na design studio.", M, 220, 92, "a design studio."),
             ], detail="brief")
    top = bottom(p, "s-title") + 70
    cmd = [(0, [("$ ", SKY), ("pip install -e '.[server,pdf]'", WHITE)]),
           (0, [("$ ", SKY), ("vixl mcp --workspace . \\", WHITE)]),
           (2, [("--tools core --schema slim", WHITE)]),
           (0, [("", WHITE)]),
           (0, [("# or Windows: Vixl-Setup.exe", MUTED)])]
    p.apply([*code_card("s-code", M, top, W - 2 * M, cmd, size=34, title="terminal")], detail="brief")
    fit_code(p, "s-code")
    p.apply([text("s-url", REPO, M, bottom(p, "s-code") + 60, 40, WHITE, SEMI)], detail="brief")

    report = save_and_export(p, "carousel", "carousel-1080x1350", [("pdf", {})], thumbnail_width=540,
                             checks=["bounds", "overlap", "contrast", "fonts", "deck"], deck={"profile": "phone"})
    for i, name in enumerate(["cover", "problem", "loop", "gallery", "numbers", "start"], 1):
        p.export(str(OUT / "carousel" / f"slide-{i}-{name}.png"), page=name, overwrite=True)
    sheet(p, OUT / "carousel" / "contact-sheet.png", width=360, columns=6)
    return report


def chip_ops(name, label, x, y, size=20):
    return (name, label, x, y, size, WHITE, "#1A1F2BD9")


def build_story():
    """Vertical story, 1080 x 1920 (keeps the top and bottom 250 px clear of platform UI)."""
    W, H = 1080, 1920
    p = new(W, H, CHARCOAL)
    M = 80
    p.apply([
        glow("glow", -300, 900, 1600, BLUE, "60"),
        *dot_grid("grid", 24, 24, W - 24, H - 24, 36, "#FFFFFF0D"),
        logo("logo", "horizontal-reverse", M, 270, width=220),
        headline("head", "Your agent’s\nnew design\nstudio.", M, 420, 128, "studio."),
    ], detail="brief")
    top = bottom(p, "head") + 56
    p.apply([*photo("s-a", "poster", M, top, 400, 540), *photo("s-b", "painting", M + 430, top, 490, 255),
             *photo("s-c", "pixel", M + 430, top + 285, 490, 255)], detail="brief")
    p.apply({"type": "look", "targets": ["s-a-base", "s-b-base", "s-c-base"], "look": "soft-shadow",
             "color": "#000000", "amount": 0.5}, detail="brief")
    p.apply([para("cta", "Inspect. Apply. Check. Preview. Export.", M, top + 590, 40, W - 2 * M, WHITE, SEMI)],
            detail="brief")
    chips_row(p, "iface", INTERFACES, M, bottom(p, "cta") + 34, size=28)
    save_and_export(p, "social", "story-1080x1920", [("png", {})], thumbnail_width=540,
                    safe_area={"left": 60, "right": 60, "top": 250, "bottom": 250})


def build_poster():
    """Tabloid (11 x 17 in) launch poster with bleed, as an RGB PNG and a CMYK PDF for print."""
    p = new(100, 100, CHARCOAL)
    p.apply({"type": "canvas", "size": "tabloid", "dpi": 150, "bleed": True, "background": CHARCOAL}, detail="brief")
    c = p.state["canvas"]
    W, H = c["width"], c["height"]
    M = 140
    p.apply([
        glow("glow", -500, 900, 2400, BLUE, "70"),
        *dot_grid("grid", 30, 30, W - 30, H - 30, 44, "#FFFFFF10"),
        logo("mark", "mark-reverse", W - 700, 120, width=580),
        *pixels("px", 11, (60, 560, W - 120, 150), 30, (12, 34), [BLUE, SKY], (0.2, 0.8)),
        text("kicker", "VIXL " + VERSION + "  /  IMAGE DOCUMENTS FOR AI AGENTS", M, 160, 30, SKY, MONO),
        headline("head", "EDIT.\nCHECK.\nSHIP.", M, 780, 270, "CHECK.", line_height=0.86),
    ], detail="brief")
    top = bottom(p, "head") + 70
    p.apply([para("sub", "Layered designs your AI agent can build, measure and fix, then export to PNG, SVG, "
                  "vector PDF, PowerPoint, HTML, GIF or MP4. Text, vector paths, masks and pages stay editable.",
                  M, top, 44, W - 2 * M - 60, MUTED, line_height=1.35)], detail="brief")
    top = bottom(p, "sub") + 80
    cols = [("For agents", f"MCP server with {FACTS['operations']} operations, atomic batches and structured errors."),
            ("For checks", "Contrast, overlap, bounds, safe areas, fonts and print ink, before export."),
            ("For print", "Bleed, trim, CMYK PDF and TIFF with TrimBox and BleedBox.")]
    cw = (W - 2 * M - 80) / 3
    ops = []
    for i, (t, d) in enumerate(cols):
        cx = round(M + i * (cw + 40))
        ops += [{"type": "shape", "shape": "rectangle", "name": f"col-rule{i}", "x": cx, "y": top, "width": round(cw),
                 "height": 6, "fill": BLUE if i != 1 else SKY},
                text(f"col-t{i}", t, cx, top + 40, 46, WHITE, HEAD),
                para(f"col-d{i}", d, cx, top + 112, 32, round(cw), MUTED)]
    p.apply(ops, detail="brief")
    p.apply([logo("logo", "horizontal-reverse", M - 16, H - 250, width=320),
             text("url", REPO, M, H - 250, 40, WHITE, MONO)], detail="brief")
    x, y, w, h = bounds(p, "url")
    p.apply({"type": "move", "target": "url", "x": W - M - w, "y": H - 196}, detail="brief")
    save_and_export(p, "print", "poster-tabloid", [("png", {"scale": 0.5}), ("pdf", {"color_space": "cmyk"})],
                    checks=["bounds", "overlap", "contrast", "safe_area", "fonts", "print"])


def build_onepager():
    """Letter-size product sheet on a light background; vector PDF."""
    p = new(100, 100, WHITE)
    p.apply({"type": "canvas", "size": "letter", "dpi": 150, "background": WHITE}, detail="brief")
    W, H = p.state["canvas"]["width"], p.state["canvas"]["height"]
    M = 90
    p.apply([
        {"type": "shape", "shape": "rectangle", "name": "band", "x": 0, "y": 0, "width": W, "height": 520,
         "fill": CHARCOAL},
        glow("glow", 500, -500, 1200),
        *dot_grid("grid", 16, 16, W - 16, 504, 26, "#FFFFFF10"),
        logo("logo", "horizontal-reverse", M, 64, width=210),
        text("kicker", "PRODUCT SHEET  /  " + VERSION, W - M - 330, 92, 20, "#A9C3FF", MONO),
        headline("head", "The image editor your\nAI agent can actually use.", M, 210, 64, "actually use."),
    ], detail="brief")
    p.apply([para("sub", SUB + " No graphical display required.", M, bottom(p, "head") + 30, 25, W - 2 * M - 80,
                  MUTED)], detail="brief")
    x, y, w, h = bounds(p, "kicker")
    p.apply({"type": "move", "target": "kicker", "x": W - M - w, "y": 92}, detail="brief")
    p.apply({"type": "resize", "target": "band", "height": bottom(p, "sub") + 70}, detail="brief")
    top = bottom(p, "band") + 48
    p.apply([text("loop-h", "How an agent works with Vixl", M, top, 30, INK, HEAD)], detail="brief")
    loop_steps(p, "loop", M, bottom(p, "loop-h") + 24, W - 2 * M, size=24, dark=False, step_h=134)
    top = bottom(p, "loop-card0") + 48
    feats = [("Stays editable", "Text, shapes, masks, effects, variables, pages and history live in one portable "
              ".vixl master."),
             ("Checks itself", "Overflowing text, low contrast, overlaps, missing glyphs and thin ink are caught "
              "before export."),
             ("Speaks every interface", "MCP for agents, a CLI for scripts, a Python API and REST, all sharing "
              "one set of operations."),
             ("Ships real files", "PNG, SVG, vector PDF, CMYK print, editable PPTX, HTML decks, GIF, WebP, "
              "MP4 and WAV."),
             ("Knows design", f"{FACTS['layouts']} layouts, {FACTS['templates']} templates, {FACTS['styles']} "
              f"styles, {FACTS['looks']} finishing looks, safe palettes and font pairings."),
             ("Goes beyond posters", "Editable vector paths, charts, diagrams, fillable forms, pixel art, "
              "character animation and sound.")]
    cw = (W - 2 * M - 50) / 2
    ops = []
    for i, (t, d) in enumerate(feats):
        cx, cy = round(M + (i % 2) * (cw + 50)), top + (i // 2) * 134
        ops += [{"type": "shape", "shape": "rectangle", "name": f"f-px{i}", "x": cx, "y": cy + 8, "width": 14,
                 "height": 14, "fill": BLUE},
                text(f"f-t{i}", t, cx + 30, cy, 25, INK, HEAD),
                para(f"f-d{i}", d, cx + 30, cy + 40, 19, round(cw - 30), SUBTLE, line_height=1.35)]
    p.apply(ops, detail="brief")
    top = bottom(p, "f-d4") + 44
    p.apply([text("code-h", "Hello, Vixl in Python", M, top, 22, INK, HEAD)], detail="brief")
    py = [(0, [("from ", CODE_KEY), ("vixl ", WHITE), ("import ", CODE_KEY), ("Project", WHITE)]),
          (0, [("p = Project(", WHITE), ("800", CODE_NUM), (", ", WHITE), ("600", CODE_NUM), (", background=", WHITE),
               ('"#18283b"', CODE_STR), (")", WHITE)]),
          (0, [("p.apply([{", WHITE), ('"type"', CODE_KEY), (": ", WHITE), ('"text"', CODE_STR), (", ", WHITE),
               ('"text"', CODE_KEY), (": ", WHITE), ('"Hello, Vixl"', CODE_STR), ("}])", WHITE)]),
          (0, [("p.export(", WHITE), ('"hello.png"', CODE_STR), (")", WHITE)])]
    p.apply(code_card("py", M, bottom(p, "code-h") + 20, W - 2 * M, py, size=17, title="hello.py"), detail="brief")
    fit_code(p, "py", 24)
    p.apply([{"type": "shape", "shape": "rectangle", "name": "foot-rule", "x": M, "y": H - 112, "width": W - 2 * M,
              "height": 2, "fill": "#DCE2EE"},
             logo("foot-logo", "horizontal-color", M, H - 96, width=130),
             text("foot-url", REPO, M, H - 88, 20, INK, MONO)], detail="brief")
    x, y, w, h = bounds(p, "foot-url")
    p.apply({"type": "move", "target": "foot-url", "x": W - M - w, "y": H - 82}, detail="brief")
    save_and_export(p, "print", "one-pager-letter", [("pdf", {}), ("png", {})])


def build_deck():
    """Nine-slide pitch deck, 1920 x 1080: PDF, editable PPTX and a self-contained HTML presenter."""
    W, H = 1920, 1080
    p = new(W, H, CHARCOAL)
    M = 140
    p.apply([{"type": "master", "action": "add", "name": "std", "background": CHARCOAL},
             *dot_grid("m-grid", 30, 30, W - 30, H - 30, 40, "#FFFFFF0B"),
             logo("m-logo", "horizontal-reverse", M, H - 112, width=150),
             text("m-num", "${page}", W - M - 30, H - 96, 24, MUTED, MONO)], detail="brief")

    def slide(name, notes, master="std"):
        p.apply({"type": "page", "action": "add", "name": name, "master": master, "notes": notes,
                 "transition": "fade"}, detail="brief")

    def title(prefix, kicker, head, accent=None, y=150, size=96):
        p.apply([text(f"{prefix}-kicker", kicker, M, y - 50, 26, SKY, MONO),
                 headline(f"{prefix}-title", head, M, y, size, accent)], detail="brief")
        return bottom(p, f"{prefix}-title")

    slide("title", "Vixl is an editable image-document engine built for AI agents. 30-second pitch.", master=None)
    p.apply([glow("t-glow", 700, -400, 1800, BLUE, "60"),
             *dot_grid("t-grid", 30, 30, W - 30, H - 30, 40, "#FFFFFF0B"),
             logo("t-mark", "mark-reverse", W - 760, 170, width=620),
             logo("t-logo", "horizontal-reverse", M, 150, width=300),
             headline("t-title", "The image editor\nyour AI agent can\nactually use.", M, 400, 112, "actually use.")],
            detail="brief")
    p.apply([text("t-sub", f"Release {VERSION}  ·  MCP · CLI · Python · REST", M, bottom(p, "t-title") + 60, 32,
                  MUTED)], detail="brief")

    slide("problem", "Creative tools assume a person with a mouse. Agents need structure, feedback and editable output.")
    y = title("pr", "THE PROBLEM", "Design tools are built\nfor hands, not agents.", "not agents.")
    cards = [("Click-only", "Sliders, canvases and menus an agent cannot see or drive."),
             ("Flattened", "Image generators return pixels; the layers and text are gone."),
             ("Unchecked", "Nobody knows the headline overflowed until a human looks.")]
    cw = (W - 2 * M - 80) / 3
    ops = []
    for i, (t, d) in enumerate(cards):
        cx = round(M + i * (cw + 40))
        ops += [{"type": "shape", "shape": "rounded-rectangle", "name": f"pr-card{i}", "x": cx, "y": y + 90,
                 "width": round(cw), "height": 330, "radius": 24, "fill": PANEL},
                text(f"pr-n{i}", f"0{i + 1}", cx + 44, y + 130, 32, SKY, HEAD),
                text(f"pr-t{i}", t, cx + 44, y + 190, 52, WHITE, HEAD),
                para(f"pr-d{i}", d, cx + 44, y + 270, 30, round(cw - 88), MUTED)]
    p.apply(ops, detail="brief")

    slide("solution", "Every design is a document of editable layers. Every change is an operation.")
    y = title("so", "THE SOLUTION", "Design as atomic,\ncheckable operations.", "checkable")
    p.apply(code_card("so-code", W - M - 700, y + 70, 700, SNIPPET, size=26), detail="brief")
    fit_code(p, "so-code")
    pts = ["Editable .vixl masters: text, vector paths, masks, pages",
           f"{FACTS['operations']} operations, up to {FACTS['batch']} per atomic batch",
           "Structured errors with suggestions",
           "Undo, branches, checkpoints and diffs"]
    ops = []
    for i, t in enumerate(pts):
        ops += [{"type": "shape", "shape": "rectangle", "name": f"so-px{i}", "x": M, "y": y + 110 + i * 100 + 12,
                 "width": 18, "height": 18, "fill": BLUE},
                text(f"so-p{i}", t, M + 44, y + 110 + i * 100, 34, WHITE)]
    p.apply(ops, detail="brief")

    slide("loop", "The agent loop: inspect the document, apply a batch, run checks, preview, export.")
    y = title("lo", "HOW IT WORKS", "One loop for every design.", "every design.")
    loop_steps(p, "lo", M, y + 120, W - 2 * M, size=44, step_h=300)
    p.apply([para("lo-note", "Checks find overflowing text, low contrast, overlaps, unsafe margins, missing glyphs "
                  "and print ink problems, so the agent fixes them before anyone looks.", M, y + 480, 32,
                  W - 2 * M, MUTED)], detail="brief")

    slide("gallery", "All of these were built with Vixl in this repository's explorations, without a GUI.")
    y = title("ga", "MADE WITH VIXL", "Posters to pixel games.", "pixel games.")
    keys = ["poster", "painting", "pixel", "donut", "film", "photo", "map", "chart"]
    gw, gh, gap = (W - 2 * M - 3 * 28) // 4, 290, 28
    ops = []
    for i, key in enumerate(keys):
        ops += photo(f"ga-{key}", key, M + (i % 4) * (gw + gap), y + 70 + (i // 4) * (gh + gap), gw, gh)
    p.apply(ops, detail="brief")
    for i, key in enumerate(keys):
        chip(p, *chip_ops(f"ga-lab{i}", SHOW[key][0], M + (i % 4) * (gw + gap) + 14,
                          y + 70 + (i // 4) * (gh + gap) + gh - 58, size=22))

    slide("quality", "Real timings from the exploration projects, before and after the 0.18.0 performance fixes.")
    y = title("qa", "FAST WHERE IT MATTERS", "Seconds, not minutes.", "Seconds,")
    rows = [("Full design check, 11 x 17 poster", "10+ min", "17 s"),
            ("Paint 400 brush strokes", "9.8 s", "1.6 s"),
            ("Add 1 stroke to a 3,000-stroke layer", "10.7 s", "0.3 s")]
    cw = (W - 2 * M - 80) / 3
    ops = []
    for i, (label, before, after) in enumerate(rows):
        cx = round(M + i * (cw + 40))
        ops += [{"type": "shape", "shape": "rounded-rectangle", "name": f"qa-card{i}", "x": cx, "y": y + 90,
                 "width": round(cw), "height": 420, "radius": 24, "fill": PANEL},
                text(f"qa-before{i}", before, cx + 44, y + 140, 44, MUTED, HEAD),
                {"type": "shape", "shape": "rectangle", "name": f"qa-strike{i}", "x": cx + 44, "y": y + 172,
                 "width": 10, "height": 4, "fill": MUTED},
                text(f"qa-after{i}", after, cx + 44, y + 210, 130, SKY, HEAD),
                para(f"qa-l{i}", label, cx + 44, y + 380, 28, round(cw - 88), WHITE)]
    p.apply(ops, detail="brief")
    for i in range(3):
        bx, by, bw, bh = bounds(p, f"qa-before{i}")
        p.apply([{"type": "shape", "target": f"qa-strike{i}", "width": bw + 8, "x": bx - 4,
                  "y": round(by + bh / 2 - 2)},
                 {"type": "layer-intent", "target": f"qa-strike{i}", "allow_overlap": [f"qa-before{i}"]}],
                detail="brief")
    p.apply([para("qa-note", "Timings from the repository's exploration projects (explorations/README.md), "
                  "before and after the performance fixes in Vixl 0.18.0.", M, y + 550, 28, W - 2 * M, MUTED)],
            detail="brief")

    slide("interfaces", "Same operations everywhere: an agent over MCP, a shell script, a notebook or a web service.")
    y = title("if", "INTERFACES", "Four doors, one engine.", "one engine.")
    doors = [("MCP", "vixl mcp --tools core", "Agents in Claude Code and other MCP clients"),
             ("CLI", "vixl -p a.vixl text add 'Hi'", "Scripts, CI pipelines and batch jobs"),
             ("Python", "Project(800, 600).apply([...])", "Notebooks, generators, data merges"),
             ("REST", "POST /operations", "Web apps and live human review")]
    cw = (W - 2 * M - 3 * 30) / 4
    ops = []
    for i, (n, cmd, d) in enumerate(doors):
        cx = round(M + i * (cw + 30))
        ops += [{"type": "shape", "shape": "rounded-rectangle", "name": f"if-card{i}", "x": cx, "y": y + 90,
                 "width": round(cw), "height": 420, "radius": 24, "fill": PANEL},
                text(f"if-n{i}", n, cx + 40, y + 130, 64, SKY if i == 0 else WHITE, HEAD),
                para(f"if-c{i}", cmd, cx + 40, y + 240, 24, round(cw - 80), CODE_STR, MONO),
                para(f"if-d{i}", d, cx + 40, y + 340, 28, round(cw - 80), MUTED)]
    p.apply(ops, detail="brief")

    slide("outputs", "One master, every format. CMYK print, editable PowerPoint and mixed WAV audio included.")
    y = title("ou", "OUTPUTS", "One master. Every format.", "Every format.")
    fm = FORMATS + ["CMYK", "WebM", "APNG", "WAV audio"]
    ops = []
    cw, chh = (W - 2 * M - 3 * 28) / 4, 120
    for i, f in enumerate(fm):
        cx, cy = round(M + (i % 4) * (cw + 28)), y + 90 + (i // 4) * (chh + 24)
        ops += [{"type": "shape", "shape": "rounded-rectangle", "name": f"ou-c{i}", "x": cx, "y": cy,
                 "width": round(cw), "height": chh, "radius": 18, "fill": PANEL if i % 5 else BLUE},
                text(f"ou-t{i}", f, cx + 36, cy + 36, 40, WHITE, HEAD)]
    p.apply(ops, detail="brief")

    slide("start", "Install from source or the Windows installer, then connect an agent.", master=None)
    p.apply([glow("st-glow", -300, 200, 1800, BLUE, "66"),
             *dot_grid("st-grid", 30, 30, W - 30, H - 30, 40, "#FFFFFF0B"),
             headline("st-title", "Give your agent\na design studio.", M, 200, 112, "a design studio.")],
            detail="brief")
    cmd = [(0, [("$ ", SKY), ("pip install -e '.[server,pdf]'", WHITE)]),
           (0, [("$ ", SKY), ("vixl mcp --workspace . --tools core --schema slim", WHITE)])]
    p.apply(code_card("st-code", M, bottom(p, "st-title") + 80, 1300, cmd, size=30, title="terminal"),
            detail="brief")
    fit_code(p, "st-code")
    p.apply([logo("st-logo", "horizontal-reverse", M, H - 200, width=280),
             text("st-url", REPO, M + 360, H - 160, 40, WHITE, MONO)], detail="brief")

    save_and_export(p, "deck", "vixl-pitch-deck", [("pdf", {}), ("pptx", {}), ("html", {})],
                    checks=["bounds", "overlap", "contrast", "fonts", "deck"], deck={"profile": "screen"})
    sheet(p, OUT / "deck" / "contact-sheet.png", width=480, columns=3)
    p.export(str(OUT / "deck" / "vixl-pitch-deck.png"), page="title", scale=0.5, overwrite=True)


def build_teaser():
    """Six-second square motion teaser: MP4 and GIF."""
    W = H = 1080
    p = new(W, H, CHARCOAL)
    p.apply([
        glow("glow", -200, -200, 1500, BLUE, "50"),
        *dot_grid("grid", 24, 24, W - 24, H - 24, 36, "#FFFFFF0D"),
        logo("mark", "mark-reverse", 340, 250, width=400),
        headline("w0", "Inspect.", 0, 740, 110, align="center", width=W),
        headline("w1", "Apply.", 0, 740, 110, align="center", width=W),
        headline("w2", "Check.", 0, 740, 110, "Check.", align="center", width=W),
        headline("w3", "Preview.", 0, 740, 110, align="center", width=W),
        headline("w4", "Export.", 0, 740, 110, align="center", width=W),
        logo("end-logo", "horizontal-reverse", 290, 330, width=500),
        text("end-line", "Image documents for AI agents", 0, 640, 44, MUTED, SEMI),
        text("end-url", REPO, 0, 720, 34, SKY, MONO),
        {"type": "timeline-set", "duration": 6600, "fps": 24},
    ], detail="brief")
    for n in ("end-line", "end-url"):
        x, y, w, h = bounds(p, n)
        p.apply({"type": "move", "target": n, "x": round((W - w) / 2), "y": y}, detail="brief")
    ops = [{"type": "animate-preset", "target": "mark", "preset": "pop-in", "start": 0, "duration": 600},
           {"type": "keyframe", "target": "mark", "property": "opacity", "time": 4200, "value": 1},
           {"type": "keyframe", "target": "mark", "property": "opacity", "time": 4500, "value": 0}]
    for i in range(5):
        t0 = 500 + i * 720
        ops += [{"type": "keyframe", "target": f"w{i}", "property": "opacity", "time": 0, "value": 0, "easing": "hold"},
                {"type": "keyframe", "target": f"w{i}", "property": "opacity", "time": t0, "value": 0},
                {"type": "keyframe", "target": f"w{i}", "property": "opacity", "time": t0 + 160, "value": 1},
                {"type": "keyframe", "target": f"w{i}", "property": "translate-y", "time": t0, "value": 40,
                 "easing": "ease-out-cubic"},
                {"type": "keyframe", "target": f"w{i}", "property": "translate-y", "time": t0 + 260, "value": 0},
                {"type": "keyframe", "target": f"w{i}", "property": "opacity", "time": t0 + 600, "value": 1},
                {"type": "keyframe", "target": f"w{i}", "property": "opacity", "time": t0 + 720, "value": 0}]
    for n, t in (("end-logo", 4500), ("end-line", 4800), ("end-url", 5050)):
        ops += [{"type": "keyframe", "target": n, "property": "opacity", "time": 0, "value": 0, "easing": "hold"},
                {"type": "animate-preset", "target": n, "preset": "slide-in-up", "start": t, "duration": 500,
                 "distance": 40, "fade": True}]
    p.apply(ops, detail="brief")
    folder = OUT / "motion"
    folder.mkdir(parents=True, exist_ok=True)
    p.save(str(folder / "teaser.vixl"))
    from vixl.timeline import contact_sheet, export_timeline
    export_timeline(p, str(folder / "teaser.mp4"), fps=24, overwrite=True)
    export_timeline(p, str(folder / "teaser.gif"), fps=12, scale=0.5, colors=96, overwrite=True)
    from vixl.timeline import render_at

    render_at(p, 5800).convert("RGB").save(folder / "teaser-frame.png")
    contact_sheet(p, count=12, columns=6, max_width=1800).convert("RGB").save(folder / "teaser-contact-sheet.png")
    print("  wrote motion/teaser.{vixl,mp4,gif} and contact sheet")


def build_stickers():
    """A US Letter sheet of die-cut style stickers for events."""
    p = new(100, 100, WHITE)
    p.apply({"type": "canvas", "size": "letter", "dpi": 150, "background": WHITE}, detail="brief")
    H = p.state["canvas"]["height"]
    D = 480
    cells = [(100, 70), (695, 70), (100, 575), (695, 575), (100, 1080), (695, 1080)]
    fills = [CHARCOAL, BLUE, WHITE, CHARCOAL, BLUE, CHARCOAL]
    p.apply([{"type": "shape", "shape": "ellipse" if i % 3 != 1 else "rounded-rectangle", "name": f"cut{i}",
              "x": x, "y": y, "width": D, "height": D, "radius": 84, "fill": fills[i], "stroke": "#C9D1E0",
              "stroke_width": 3} for i, (x, y) in enumerate(cells)], detail="brief")
    (x0, y0), (x1, y1), (x2, y2), (x3, y3), (x4, y4), (x5, y5) = cells
    p.apply([
        logo("s0-mark", "mark-reverse", x0 + 90, y0 + 90, width=D - 180),
        logo("s1-logo", "stacked-white", x1 + 85, y1 + 70, width=D - 170),
        text("s2-t", "MADE WITH", 0, y2 + 150, 38, INK, MONO),
        logo("s2-logo", "horizontal-color", x2 + 50, y2 + 200, width=D - 100),
        headline("s3-t", "No GUI.\nNo\nproblem.", x3, y3 + 110, 80, "problem.", align="center", width=D),
        headline("s4-t", "checked\nbefore\nexport", x4, y4 + 100, 86, align="center", width=D),
        *pixel_stair("s5-px", x5 + 150, y5 + 70, 12, 7, 10, SKY, fade=False),
        text("s5-a", "MCP", 0, y5 + 160, 140, WHITE, HEAD),
        text("s5-b", "READY", 0, y5 + 320, 52, SKY, MONO),
    ], detail="brief")
    for n, cx in (("s2-t", x2), ("s5-a", x5), ("s5-b", x5)):
        x, y, w, h = bounds(p, n)
        p.apply({"type": "move", "target": n, "x": round(cx + (D - w) / 2), "y": y}, detail="brief")
    p.apply([text("note", "Cut along the grey outlines. Kiss-cut on matte vinyl.", 100, H - 70, 22, SUBTLE)],
            detail="brief")
    save_and_export(p, "print", "sticker-sheet-letter", [("pdf", {}), ("png", {"scale": 0.5})],
                    checks=["bounds", "overlap", "contrast", "fonts"])


def build_overview():
    """A one-image board of the whole kit, framed from the exports above."""
    W, H = 2400, 1580
    p = new(W, H, CHARCOAL)
    o = "marketing/output"
    tiles = [  # path, x, y, w, h, label
        (f"{o}/social/og-card-1200x630.png", 80, 220, 900, 473, "Open Graph card"),
        (f"{o}/social/github-preview-1280x640.png", 80, 760, 900, 450, "GitHub social preview"),
        (f"{o}/print/poster-tabloid.png", 1030, 220, 430, 659, "Tabloid poster, CMYK PDF"),
        (f"{o}/print/one-pager-letter.png", 1030, 940, 430, 556, "Product sheet"),
        (f"{o}/social/story-1080x1920.png", 1510, 220, 380, 676, "Story"),
        (f"{o}/print/sticker-sheet-letter.png", 1510, 960, 380, 492, "Sticker sheet"),
        (f"{o}/deck/vixl-pitch-deck.png", 1940, 220, 380, 214, "Pitch deck"),
        (f"{o}/carousel/slide-1-cover.png", 1940, 500, 380, 475, "Carousel"),
        (f"{o}/social/linkedin-banner-1584x396.png", 1940, 1030, 380, 95, "LinkedIn banner"),
        (f"{o}/motion/teaser-frame.png", 1940, 1196, 300, 300, "Motion teaser"),
    ]
    p.apply([*dot_grid("grid", 24, 24, W - 24, H - 24, 40, "#FFFFFF0B"),
             logo("logo", "horizontal-reverse", 80, 60, width=260),
             headline("head", "Marketing kit, made with Vixl.", 420, 92, 64, "made with Vixl.")], detail="brief")
    ops = []
    for i, (path, x, y, w, h, label) in enumerate(tiles):
        ops += [{"type": "shape", "shape": "rounded-rectangle", "name": f"t{i}-base", "x": x, "y": y, "width": w,
                 "height": h, "radius": 12, "fill": PANEL},
                {"type": "frame", "name": f"t{i}", "path": path, "x": x, "y": y, "width": w, "height": h,
                 "fit": "fill"},
                {"type": "clip", "target": f"t{i}", "base": f"t{i}-base"}]
    p.apply(ops, detail="brief")
    p.apply({"type": "look", "targets": [f"t{i}-base" for i in range(len(tiles))], "look": "soft-shadow",
             "color": "#000000", "amount": 0.4}, detail="brief")
    for i, (path, x, y, w, h, label) in enumerate(tiles):
        below = h < 150 or label == "GitHub social preview"  # short banner; card whose chips sit at the bottom
        ly = y + h + 8 if below else y + h - 46
        chip(p, f"lab{i}", label, x + 10, ly, 18, WHITE, "#1A1F2BE0", pad=(12, 8))
    save_and_export(p, ".", "kit-overview", [("png", {"scale": 0.75})], checks=["bounds", "fonts"])


PIECES = {
    "og": build_og,
    "github": build_github,
    "linkedin": build_linkedin,
    "story": build_story,
    "carousel": build_carousel,
    "poster": build_poster,
    "onepager": build_onepager,
    "stickers": build_stickers,
    "deck": build_deck,
    "teaser": build_teaser,
    "overview": build_overview,
}


def main(argv):
    names = argv or list(PIECES)
    for name in names:
        print(f"[{name}]")
        PIECES[name]()


if __name__ == "__main__":
    main(sys.argv[1:])
