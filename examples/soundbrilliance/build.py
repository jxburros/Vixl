"""soundBrilliance marketing package, built with Vixl.

Run from the repo root:

    python examples/soundbrilliance/build.py             # build everything
    python examples/soundbrilliance/build.py story cards  # build only some pieces

Brand inputs come from soundbrilliance.com: the logo lockup (outlined SVG, imported as editable
vectors), the site palette (cream, near-black and the seven category colours) and the session artwork
and film stills in ``source/``. The site's Miller Display / Basis Grotesque pairing is stood in for by
Libre Caslon Text and Hanken Grotesk, both open fonts that Vixl embeds in every master.

Every piece is written to ``output/<piece>/`` as an editable ``.vixl`` master plus its exports, and is
checked (Vixl design checks plus a per-piece suite) before anything is exported.
"""

import json
import os
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
SRC = HERE / "source"
OUT = HERE / "output"
PREP = OUT / "_prepared"
os.environ.setdefault("VIXL_NO_UPDATE", "1")
sys.path.insert(0, str(ROOT / "src"))

from PIL import Image  # noqa: E402

from vixl import Project  # noqa: E402
from vixl.imports import svg_operations  # noqa: E402
from vixl.typefaces import install_font  # noqa: E402

# Brand (soundbrilliance.com stylesheet) ---------------------------------------------------------
CREAM = "#FEFBF2"
CREAM_2 = "#FBF5E5"
SAND = "#E7E1D1"
INK = "#030102"
STONE = "#827568"  # --dark-neutral
RED = "#F4576A"
BLUE = "#4A9FC9"
YELLOW = "#EBD448"
ORANGE = "#E76F4F"
GREEN = "#479D47"
PURPLE = "#A4659E"
TEAL = "#5BBDA6"

DISPLAY, SERIF, BODY, BODY_SEMI = ("libre-caslon-text-400-italic", "libre-caslon-text-400",
                                    "hanken-grotesk-400", "hanken-grotesk-600")

URL = "soundbrilliance.com"
TAGLINE = "Unlocking the healing potential of music"

# Session categories, in the app's order. Colours follow the category artwork on the site; the one-line
# descriptions are draft copy for the client to approve.
CATEGORIES = [
    ("Perform", RED, "Lock in before the moments that matter."),
    ("Motivate", ORANGE, "Lift your energy and get moving."),
    ("Create", YELLOW, "Make room for ideas to flow."),
    ("Comfort", GREEN, "Ease through the harder days."),
    ("Recover", TEAL, "Help your body reset after effort."),
    ("Calm", BLUE, "Settle in, slow down."),
    ("Sleep", PURPLE, "Wind down toward deeper rest."),
]

STAT_NOTE = ("vs. the same music unenhanced. Fisher exact test, OR 8.9, N = 33, p = 0.0104. "
             "Source: soundbrilliance.com")


# Prepared sources ------------------------------------------------------------------------------
def prepare():
    """Square crops of the film stills and a raster App Store badge (the badge SVG uses a mask)."""
    PREP.mkdir(parents=True, exist_ok=True)
    crops = {"headphones": ("intro.jpg", (420, 0, 958, 538)), "gledhill": ("gledhill.jpg", (400, 0, 928, 528)),
             "cellist": ("abilene-recover.jpg", (50, 170, 480, 600))}
    for name, (source, box) in crops.items():
        target = PREP / f"{name}.jpg"
        if not target.exists():
            Image.open(SRC / source).convert("RGB").crop(box).save(target, quality=94)
    badge = PREP / "appstore.png"
    if not badge.exists():
        import resvg_py

        png = resvg_py.svg_to_bytes(svg_path=str(SRC / "appstore.svg"), zoom=4)
        badge.write_bytes(bytes(png))


def prepared(name):
    return str(PREP / name)


# Helpers ---------------------------------------------------------------------------------------
def doc(width, height, background=CREAM, suite=None):
    p = Project(width, height, background, workspace=str(ROOT))
    install_font(p, "Libre Caslon Text", 400, italic=True, role="heading")
    install_font(p, "Libre Caslon Text", 400)
    install_font(p, "Hanken Grotesk", 400, role="body")
    install_font(p, "Hanken Grotesk", 600)
    ops = [{"type": "swatch", "name": name, "color": color} for name, color in
           (("cream", CREAM), ("ink", INK), ("red", RED), ("blue", BLUE), ("yellow", YELLOW),
            ("orange", ORANGE), ("green", GREEN), ("purple", PURPLE), ("teal", TEAL))]
    rules = [
        {"id": "width", "kind": "property", "target": "canvas", "field": "width", "expected": width},
        {"id": "height", "kind": "property", "target": "canvas", "field": "height", "expected": height},
        {"id": "fonts", "kind": "budget", "max_fonts": 4},
    ] + [{"id": f"rule-{i}", **rule} for i, rule in enumerate(suite or [])]
    ops.append({"type": "suite-set", "name": "brief", "suite": {"rules": rules}})
    put(p, ops)
    return p


def logo(name, x, y, width=None, height=None, variant="lockup", on_dark=False):
    """The soundBrilliance logo as grouped editable vector paths, scaled to width or height."""
    root = ET.fromstring((SRC / f"logo-{variant}.svg").read_bytes())
    sw, sh = float(root.get("width")), float(root.get("height"))
    scale = min(width / sw if width else float("inf"), height / sh if height else float("inf"))
    root.set("width", str(sw * scale))
    root.set("height", str(sh * scale))
    ops = svg_operations(ET.tostring(root), Project(100, 100), name)
    for op in ops:
        op["x"] += x
        op["y"] += y
        if on_dark and op.get("fill", "").upper() == INK:
            op["fill"] = CREAM
    ops.append({"type": "group", "name": name, "targets": [op["name"] for op in ops]})
    return ops


def put(p, operations):
    """Apply a batch, then move text given an ``anchor`` (center, right-top, right-bottom) so that point of
    its measured box sits at its x/y."""
    anchors = {}
    for op in operations:
        if "anchor" in op:
            anchors[op["name"]] = (op.pop("anchor"), op["x"], op["y"])
    p.apply(operations, detail="brief")
    moves = []
    for name, (anchor, x, y) in anchors.items():
        cx, cy, w, h = p.bounds(name)
        px, py, _, _ = p.bounds(name, space="parent")  # move takes the parent group's coordinates
        dx = {"center": w / 2}.get(anchor, w if anchor.startswith("right") else 0)
        dy = h / 2 if anchor.endswith("center") else (h if anchor.endswith("bottom") else 0)
        moves.append({"type": "move", "target": name, "x": round(px + x - dx - cx), "y": round(py + y - dy - cy)})
    if moves:
        p.apply(moves, detail="brief")


def text(name, value, x, y, size, color=INK, font=BODY, **extra):
    return {"type": "text", "name": name, "text": value, "font": font, "size": size, "color": color,
            "x": x, "y": y, **extra}


def para(name, value, x, y, size, width, color=INK, font=BODY, line_height=1.3, align="left"):
    return {"type": "rich-text", "name": name, "spans": [{"text": value}], "font": font, "size": size,
            "color": color, "line_height": line_height, "x": x, "y": y, "width": width, "align": align}


def headline(name, parts, x, y, size, width, color=INK, align="left", line_height=1.02):
    """Serif display: plain strings set roman, ("italic", text) tuples set in the italic, like the site."""
    spans = []
    for part in parts:
        if isinstance(part, tuple):
            spans.append({"text": part[1], "italic": True, **({"color": part[2]} if len(part) > 2 else {})})
        else:
            spans.append({"text": part})
    return {"type": "rich-text", "name": name, "spans": spans, "font": SERIF, "size": size, "color": color,
            "line_height": line_height, "x": x, "y": y, "width": width, "align": align,
            "font_variants": {"italic": DISPLAY}}


def circle(name, x, y, d, fill, bleed=False):
    ops = [{"type": "shape", "shape": "ellipse", "name": name, "x": x, "y": y, "width": d, "height": d,
            "fill": fill}]
    ops.append({"type": "layer-intent", "target": name, "role": "decoration", "allow_crop": bleed})
    return ops


def photo_circle(name, image, x, y, d):
    return [{"type": "frame", "name": name, "path": prepared(image), "x": x, "y": y, "width": d, "height": d,
             "fit": "fill", "frame_shape": "ellipse", "downsample": "placed@2x"}]


def ring(name, x, y, d, color=INK, width=3):
    return [{"type": "shape", "shape": "ellipse", "name": name, "x": x, "y": y, "width": d, "height": d,
             "fill": "none", "stroke": color, "stroke_width": width},
            {"type": "layer-intent", "target": name, "role": "decoration", "allow_crop": True}]


def mark_badge(name, x, y, d, disc=CREAM):
    """The B mark on a cream disc, as on the session artwork."""
    inner = round(d * 0.56)
    return [{"type": "shape", "shape": "ellipse", "name": f"{name}-disc", "x": x, "y": y, "width": d, "height": d,
             "fill": disc},
            *logo(f"{name}-mark", x + (d - inner * 98 / 93) / 2, y + (d - inner) / 2, height=inner, variant="mark"),
            {"type": "group", "name": name, "targets": [f"{name}-disc", f"{name}-mark"]}]


def pill(name, label, x, y, w, h, fill, size, color=INK):
    return [{"type": "shape", "shape": "rounded-rectangle", "name": f"{name}-bg", "x": x, "y": y, "width": w,
             "height": h, "radius": h / 2, "fill": fill},
            text(f"{name}-label", label, x + w / 2, y + h / 2, size, color, DISPLAY, anchor="center")]


def appstore(name, x, y, height):
    w = round(height * 205 / 59)
    return [{"type": "frame", "name": name, "path": prepared("appstore.png"), "x": x, "y": y, "width": w,
             "height": height, "fit": "fit"},
            {"type": "layer-intent", "target": name, "alt": "Download on the App Store"}]


def finish(p, folder, stem, exports, **check_options):
    folder = OUT / folder
    folder.mkdir(parents=True, exist_ok=True)
    report = p.check(**check_options)
    fixes = [i for i in report["issues"] if i["action"] == "fix"]
    print(f"  check {stem}: {len(report['issues'])} issues, {len(fixes)} to fix")
    for issue in report["issues"]:
        if issue["action"] != "informational":
            print("   ", issue["action"].upper(), issue["check"], (issue["message"] or "")[:160])
    suites = {name: p.check_suite(name) for name in p.state.get("suites", {})}
    for name, suite in suites.items():
        if not suite["passed"]:
            print("    SUITE", name, json.dumps([r for r in suite.get("results", []) if r.get("status") != "passed"])[:600])
    report["suites"] = suites
    (folder / f"{stem}.check.json").write_text(json.dumps(report, indent=2, default=str) + "\n")
    if fixes or not all(s["passed"] for s in suites.values()):
        raise RuntimeError(f"Fix design findings before exporting {stem}")
    p.compact()
    p.save(str(folder / f"{stem}.vixl"), overwrite=True)
    for ext, options in exports:
        path = folder / f"{stem}.{ext}"
        p.export(str(path), overwrite=True, **options)
        print("  wrote", path.relative_to(ROOT))
    return p


def contrast(target, minimum=4.5):
    return {"kind": "contrast", "target": target, "minimum": minimum}


# Pieces ----------------------------------------------------------------------------------------
def hero_post():
    """Instagram square: the brand promise, headphones still in a circle over the blue disc."""
    p = doc(1080, 1080, suite=[contrast("headline", 4.5), {"kind": "text", "contains": "healing potential"}])
    put(p, [
        *circle("disc", 470, 400, 860, BLUE, bleed=True),
        *photo_circle("photo", "headphones.jpg", 380, 470, 520),
        {"type": "layer-intent", "target": "photo", "alt": "A listener putting on headphones"},
        *ring("ring", 340, 430, 600, INK, 3),
        {"type": "layer-intent", "target": "ring", "allow_overlap": ["photo", "disc"]},
        headline("headline", ["Unlocking the healing potential of ", ("italic", "music")], 72, 84, 84, 760,
                 line_height=1.04),
        {"type": "layer-intent", "target": "headline", "role": "title"},
        *logo("logo", 72, 940, width=300),
        {"type": "layer-intent", "target": "photo", "allow_overlap": ["disc"]},
    ])
    return finish(p, "01-social", "hero-post", [("png", {}), ("jpg", {"quality": 92})])


def story():
    """Instagram story: 'How you feel is yours to direct', the seven sessions, then the call to action."""
    p = doc(1080, 1920, suite=[contrast("headline"), {"kind": "count", "target": "cat-*-bg", "minimum": 7,
                                                       "maximum": 7},
                                {"kind": "spacing", "targets": [f"cat-{i}-bg" for i in range(7)], "axis": "vertical"}])
    ops = [*mark_badge("mark", 72, 270, 96, disc=SAND),
           headline("headline", ["How you feel is ", ("italic", "yours to direct.")], 72, 410, 104, 900,
                    line_height=1.0),
           {"type": "layer-intent", "target": "headline", "role": "title"}]
    y, h, gap = 720, 92, 18
    for i, (name, color, _) in enumerate(CATEGORIES):
        ops += pill(f"cat-{i}", name, 72 + (i % 2) * 120, y + i * (h + gap), 816, h, color, 52)
    ops += [
        text("cta", "Start your first session today", 72, 1520, 52, INK, SERIF),
        *appstore("appstore", 72, 1600, 90),
        text("url", URL, 1008, 1645, 30, INK, BODY_SEMI, anchor="right-center"),
    ]
    put(p, ops)
    return finish(p, "01-social", "story", [("png", {})])


def carousel():
    """Six-slide 4:5 carousel: promise, the three ingredients, the evidence, the call to action."""
    W, H, M = 1080, 1350, 80
    slides = []

    def slide(stem, background=CREAM, suite=None):
        p = doc(W, H, background, suite=suite)
        slides.append((stem, p))
        return p

    def counter(i, color=INK):
        return text("counter", f"{i} / 6", W - M, M, 28, color, BODY_SEMI, anchor="right-top")

    def section(num, title, body, color=INK):
        return [text("eyebrow", f"0{num}", M, 860, 30, color, BODY_SEMI),
                headline("title", [("italic", title)], M, 910, 104, W - 2 * M, color),
                para("body", body, M, 1050, 36, W - 2 * M - 60, color, line_height=1.32),
                {"type": "layer-intent", "target": "title", "role": "title"}]

    p = slide("carousel-1", suite=[contrast("headline")])
    put(p, [
        *circle("disc", 300, -260, 1040, YELLOW, bleed=True),
        *photo_circle("photo", "headphones.jpg", 470, 130, 520),
        {"type": "layer-intent", "target": "photo", "alt": "A listener putting on headphones",
         "allow_overlap": ["disc"]},
        headline("headline", ["Your health,", ("italic", " in your hands.")], M, 790, 120, 900, line_height=1.0),
        {"type": "layer-intent", "target": "headline", "role": "title"},
        *logo("logo", M, 1206, width=300),
        text("swipe", "Swipe  →", W - M, 1214, 30, INK, BODY_SEMI, anchor="right-top"),
        *mark_badge("mark", M, M, 88, disc=SAND),
    ])

    p = slide("carousel-2", YELLOW, suite=[contrast("body"), contrast("title")])
    put(p, [
        *[op for k in range(5) for op in ring(f"wave-{k}", 260 + k * 70 - (k % 2) * 40, 50 + k * 34,
                                                  520 + k * 30, INK, 3)],
        counter(2),
        *section(1, "Enhanced music",
                 "Music you already love, precision-engineered with subharmonics, binaural beats and "
                 "neural entrainment to shape how your nervous system responds."),
    ])
    put(p, [{"type": "layer-intent", "target": f"wave-{k}", "allow_overlap": [f"wave-{j}" for j in range(5)]}
             for k in range(5)])

    p = slide("carousel-3", TEAL, suite=[contrast("body"), contrast("title")])
    put(p, [
        *circle("disc", 540, 120, 640, CREAM, bleed=True),
        *photo_circle("photo", "gledhill.jpg", 180, 160, 560),
        {"type": "layer-intent", "target": "photo", "alt": "Visual artist Linden Gledhill at work",
         "allow_overlap": ["disc"]},
        counter(3),
        *section(2, "Natural visuals",
                 "Nature-based imagery, created in part by scientist and visual artist Linden Gledhill, "
                 "to give your eyes somewhere to rest."),
    ])

    p = slide("carousel-4", RED, suite=[contrast("body"), contrast("title")])
    put(p, [
        *circle("disc", 160, 120, 600, CREAM),
        *photo_circle("photo", "cellist.jpg", 380, 240, 500),
        {"type": "layer-intent", "target": "photo", "alt": "Cellist Abilene, who records guidance for the app",
         "allow_overlap": ["disc"]},
        counter(4),
        *section(3, "Expert guidance",
                 "A human voice guides every session and builds body awareness. Journeys string sessions "
                 "into programs built around your goals."),
    ])

    p = slide("carousel-5", INK, suite=[contrast("stat-label"), contrast("note", 4.5)])
    put(p, [
        counter(5, CREAM),
        text("eyebrow", "Grounded in science", M, 200, 30, YELLOW, BODY_SEMI),
        headline("stat", [("italic", "9×")], M, 250, 400, 900, YELLOW, line_height=1.0),
        {"type": "layer-intent", "target": "stat", "role": "title"},
        para("stat-label", "more likely to reduce anxiety and physiologic stress together.",
             M, 720, 56, W - 2 * M, CREAM, SERIF, line_height=1.2),
        para("note", STAT_NOTE, M, 1080, 24, W - 2 * M - 120, "#CFC7B8", line_height=1.4),
        *logo("logo", M, 1206, width=300, on_dark=True),
    ])

    p = slide("carousel-6", CREAM, suite=[contrast("headline")])
    ops = [counter(6),
           headline("headline", ["Start your first session ", ("italic", "today.")], M, 160, 108, 920,
                    line_height=1.0),
           {"type": "layer-intent", "target": "headline", "role": "title"}]
    d, gap = 200, 28
    for i, (name, color, _) in enumerate(CATEGORIES):
        row, col = divmod(i, 4) if i < 4 else (1, i - 4)
        x = M + col * (d + gap) + (row * (d + gap) // 2)
        ops += [*circle(f"dot-{i}", x, 520 + row * (d + gap), d, color),
                text(f"dot-{i}-label", name, x + d / 2, 520 + row * (d + gap) + d / 2, 40, INK, DISPLAY,
                     anchor="center")]
    ops += [*appstore("appstore", M, 1040, 100), text("url", URL, M, 1186, 32, STONE, BODY_SEMI),
            *logo("logo", W - M - 300, 1206, width=300)]
    put(p, ops)

    for stem, p in slides:
        finish(p, "02-carousel", stem, [("png", {})])
    sheet = Image.new("RGB", (6 * 360 + 7 * 20, 450 + 40), "#EDE7D7")
    for i, (stem, _) in enumerate(slides):
        im = Image.open(OUT / "02-carousel" / f"{stem}.png").convert("RGB").resize((360, 450), Image.LANCZOS)
        sheet.paste(im, (20 + i * 380, 20))
    sheet.save(OUT / "02-carousel" / "carousel-overview.png")
    print("  wrote", (OUT / "02-carousel" / "carousel-overview.png").relative_to(ROOT))


def cards():
    """One square card per session category, in the style of the app's session artwork."""
    for i, (name, color, line) in enumerate(CATEGORIES):
        p = doc(1080, 1080, color, suite=[contrast("name", 3), contrast("line")])
        put(p, [
            *[op for k in range(3) for op in ring(f"ring-{k}", 440 + k * 90, -120 - k * 40, 620 + k * 60, INK, 3)],
            *mark_badge("mark", 72, 72, 112),
            headline("name", [("italic", name)], 72, 640, 210, 940, line_height=1.0),
            {"type": "layer-intent", "target": "name", "role": "title"},
            para("line", line, 72, 900, 44, 936, INK, SERIF, line_height=1.2),
            text("url", URL, 1008, 1008, 26, INK, BODY_SEMI, anchor="right-bottom"),
        ])
        put(p, [{"type": "layer-intent", "target": f"ring-{k}", "allow_overlap": [f"ring-{j}" for j in range(3)]}
                 for k in range(3)])
        finish(p, "03-session-cards", f"{i + 1}-{name.lower()}", [("png", {})])


def banners():
    """LinkedIn and X headers plus an Open Graph link image, one composition adapted to each ratio."""
    for stem, (w, h) in {"linkedin-banner": (1584, 396), "x-header": (1500, 500), "og-image": (1200, 630)}.items():
        p = doc(w, h, suite=[contrast("tagline")])
        ops = []
        unit = min(h, 400)  # the cluster stays clear of the copy on tall ratios
        for k, (color, f) in enumerate([(RED, 0.95), (BLUE, 0.75), (YELLOW, 0.55)]):
            d = unit * 1.1 * f
            ops += circle(f"c{k}", w - unit * 1.35 + k * unit * 0.45, h - d * 0.72, d, color, bleed=True)
        if stem == "og-image":
            ops += [*logo("logo", 80, 90, width=420),
                    headline("tagline", ["How you feel is ", ("italic", "yours to direct.")], 80, 200, 76, 600,
                             line_height=1.02),
                    text("url", URL, 80, 520, 28, STONE, BODY_SEMI)]
        else:
            s = h / 500
            left, lw = round(64 * s + 20), round(520 * s)
            top = round(h * 0.3)
            ops += [*logo("logo", left, top, width=lw),
                    headline("tagline", ["Grounded in science.\n", ("italic", "Designed for daily life.")],
                             left, round(top + lw * 93 / 867 + 30 * s), round(40 * s + 4),
                             round(w - unit * 1.35 - left - 40),
                             line_height=1.15)]
        put(p, ops)
        put(p, [{"type": "layer-intent", "target": f"c{k}", "allow_overlap": [f"c{j}" for j in range(3)]}
                 for k in range(3)])
        finish(p, "04-banners", stem, [("png", {})])


def flyer():
    """US Letter flyer for clinics, studios and gyms: promise, three ingredients, sessions, QR to the site."""
    W, H = 2550, 3300  # US Letter at 300 dpi
    p = doc(W, H, suite=[contrast("headline"), {"kind": "relation", "target": "qr", "to": "canvas",
                                                "position": "inside", "minimum": 150}])
    M = 180
    ops = [
        *circle("disc", W - 1380, -620, 1700, BLUE, bleed=True),
        *photo_circle("photo", "headphones.jpg", W - 1160, 180, 860),
        {"type": "layer-intent", "target": "photo", "alt": "A listener putting on headphones",
         "allow_overlap": ["disc"]},
        *logo("logo", M, 220, width=900),
        headline("headline", ["Unlocking the healing\npotential of ", ("italic", "music.")], M, 1200, 190, 2200,
                 line_height=1.02),
        {"type": "layer-intent", "target": "headline", "role": "title"},
        para("lead", "soundBrilliance layers precision-engineered audio, natural visuals and expert guidance over "
             "music you already love, so you can direct how you feel: calmer, more focused, better rested.",
             M, 1680, 62, 2100, INK, line_height=1.35),
    ]
    feats = [("Enhanced music", "Subharmonics, binaural beats and neural entrainment."),
             ("Natural visuals", "Nature-based imagery by artist Linden Gledhill."),
             ("Expert guidance", "A real human voice that guides each session.")]
    cw = (W - 2 * M - 2 * 90) / 3
    for i, (t, b) in enumerate(feats):
        x = M + i * (cw + 90)
        ops += [{"type": "shape", "shape": "rectangle", "name": f"feat-{i}-rule", "x": x, "y": 2080, "width": cw,
                 "height": 8, "fill": [RED, YELLOW, TEAL][i]},
                text(f"feat-{i}-title", t, x, 2120, 64, INK, DISPLAY),
                para(f"feat-{i}-body", b, x, 2220, 46, cw, INK, line_height=1.3)]
    d = 200
    for i, (name, color, _) in enumerate(CATEGORIES):
        x = M + i * ((W - 2 * M - d) / 6)
        ops += [*circle(f"dot-{i}", x, 2500, d, color),
                text(f"dot-{i}-label", name, x + d / 2, 2500 + d / 2, 42, INK, DISPLAY, anchor="center")]
    ops += [
        text("cta", "Start your first session today.", M, 2860, 84, INK, DISPLAY),
        text("url", f"{URL}  ·  Download on the App Store", M, 2980, 46, INK, BODY_SEMI),
        {"type": "qr", "name": "qr", "data": "https://www.soundbrilliance.com/", "size": 300,
         "x": W - M - 300, "y": 2780, "background": CREAM, "color": INK, "quiet": 2},
    ]
    put(p, ops)
    finish(p, "05-print", "flyer-letter", [("pdf", {}), ("png", {"scale": 0.4})])


def brand_sheet():
    """One-page reference: logo, palette, category colours and type."""
    W, H = 1920, 1080
    p = doc(W, H, suite=[contrast("title")])
    ops = [*logo("logo", 100, 100, width=640),
           headline("title", [("italic", "Brand essentials")], 100, 260, 96, 1000),
           {"type": "layer-intent", "target": "title", "role": "title"},
           text("type-h", "Libre Caslon Text Italic — display (stand-in for Miller Display)", 100, 410, 30,
                STONE, BODY_SEMI),
           headline("type-sample", ["Settle in, ", ("italic", "slow down.")], 100, 455, 72, 900),
           text("type-b", "Hanken Grotesk — body (stand-in for Basis Grotesque Pro)", 100, 590, 30, STONE,
                BODY_SEMI),
           para("type-body", "Grounded in science. Designed for daily life. How you feel is yours to direct.",
                100, 635, 38, 820, INK)]
    core = [("Cream", CREAM, INK), ("Cream 2", CREAM_2, INK), ("Sand", SAND, INK), ("Ink", INK, CREAM),
            ("Stone", STONE, INK)]
    for i, (n, c, fg) in enumerate(core):
        x = 1040 + i * 156
        ops += [{"type": "shape", "shape": "rounded-rectangle", "name": f"core-{i}", "x": x, "y": 120, "width": 140,
                 "height": 220, "radius": 16, "fill": c, "stroke": SAND, "stroke_width": 2},
                text(f"core-{i}-n", n, x + 16, 260, 24, fg, BODY_SEMI),
                text(f"core-{i}-h", c, x + 16, 292, 20, fg, BODY)]
    for i, (n, c, _) in enumerate(CATEGORIES):
        col, row = i % 4, i // 4
        x, y = 1040 + col * 195, 420 + row * 270
        ops += [*circle(f"cat-{i}", x, y, 170, c),
                text(f"cat-{i}-n", n, x + 85, y + 75, 34, INK, DISPLAY, anchor="center"),
                text(f"cat-{i}-h", c, x + 85, y + 118, 20, INK, BODY_SEMI, anchor="center")]
    ops += [text("note", "Category colours follow the session artwork: one colour per session type.", 100, 960, 26,
                 STONE, BODY)]
    put(p, ops)
    finish(p, "00-brand", "brand-essentials", [("png", {}), ("pdf", {})])


def breathe():
    """An eight-second breathing loop: the blue disc grows for four seconds and settles for four."""
    from vixl.timeline import export_timeline

    p = doc(1080, 1080, suite=[contrast("inhale", 3)])
    put(p, [
        *circle("disc", 190, 150, 700, BLUE),
        *ring("ring", 140, 100, 800, INK, 3),
        {"type": "layer-intent", "target": "ring", "allow_overlap": ["disc"]},
        {"type": "layer-intent", "target": "disc", "allow_overlap": ["ring"]},
        headline("inhale", [("italic", "Breathe in")], 90, 440, 96, 900, align="center"),
        headline("exhale", [("italic", "Breathe out")], 90, 440, 96, 900, align="center"),
        {"type": "layer-intent", "target": "exhale", "allow_overlap": ["inhale", "disc"],
         "waive": [{"check": "contrast", "reason": "transparent on the poster frame; fades in at 3.6 s over the disc"}]},
        {"type": "layer-intent", "target": "inhale", "allow_overlap": ["exhale", "disc"]},
        text("line", "Settle in, slow down.", 540, 935, 40, INK, SERIF, anchor="center"),
        *logo("logo", 390, 975, width=300),
        {"type": "opacity", "target": "exhale", "value": 0},  # the still export shows the inhale state
        {"type": "timeline-set", "duration": "8s", "fps": 20, "loop": 0},
        {"type": "pivot", "target": "disc", "value": "center"},
        {"type": "pivot", "target": "ring", "value": "center"},
        {"type": "keyframe", "targets": ["disc"], "property": "scale", "time": 0, "value": 0.62,
         "easing": "ease-in-out-sine"},
        {"type": "keyframe", "targets": ["disc"], "property": "scale", "time": "4s", "value": 1.0,
         "easing": "ease-in-out-sine"},
        {"type": "keyframe", "targets": ["disc"], "property": "scale", "time": "8s", "value": 0.62},
        {"type": "keyframe", "target": "inhale", "property": "opacity", "time": 0, "value": 1, "easing": "hold"},
        {"type": "keyframe", "target": "inhale", "property": "opacity", "time": "3.6s", "value": 1,
         "easing": "ease-in-out"},
        {"type": "keyframe", "target": "inhale", "property": "opacity", "time": "4.2s", "value": 0, "easing": "hold"},
        {"type": "keyframe", "target": "inhale", "property": "opacity", "time": "7.6s", "value": 0,
         "easing": "ease-in-out"},
        {"type": "keyframe", "target": "inhale", "property": "opacity", "time": "8s", "value": 1},
        {"type": "keyframe", "target": "exhale", "property": "opacity", "time": 0, "value": 0, "easing": "hold"},
        {"type": "keyframe", "target": "exhale", "property": "opacity", "time": "3.6s", "value": 0,
         "easing": "ease-in-out"},
        {"type": "keyframe", "target": "exhale", "property": "opacity", "time": "4.2s", "value": 1, "easing": "hold"},
        {"type": "keyframe", "target": "exhale", "property": "opacity", "time": "7.6s", "value": 1,
         "easing": "ease-in-out"},
        {"type": "keyframe", "target": "exhale", "property": "opacity", "time": "8s", "value": 0},
    ])
    finish(p, "06-motion", "breathe-loop", [("png", {})])
    folder = OUT / "06-motion"
    for name, options in (("breathe-loop.gif", {"scale": 0.5, "colors": 64}), ("breathe-loop.mp4", {})):
        try:
            result = export_timeline(p, str(folder / name), overwrite=True, **options)
            print("  wrote", (folder / name).relative_to(ROOT), result.get("bytes", ""))
        except Exception as error:  # MP4 needs ffmpeg on PATH
            print("  skipped", name, str(error)[:120])


def overview():
    """One contact sheet of every still, for review."""
    tiles = [("00-brand/brand-essentials", 2), ("01-social/hero-post", 1), ("01-social/story", 1),
             *[(f"02-carousel/carousel-{i}", 1) for i in range(1, 7)],
             *[(f"03-session-cards/{i + 1}-{name.lower()}", 1) for i, (name, _, _) in enumerate(CATEGORIES)],
             ("04-banners/linkedin-banner", 2), ("04-banners/x-header", 2), ("04-banners/og-image", 2),
             ("05-print/flyer-letter", 1), ("06-motion/breathe-loop", 1)]
    row_h, gap, width = 360, 24, 2400
    rows, row, x = [], [], gap
    for stem, _ in tiles:
        im = Image.open(OUT / f"{stem}.png").convert("RGB")
        w = round(im.width * row_h / im.height)
        if x + w + gap > width and row:
            rows.append(row)
            row, x = [], gap
        row.append(im.resize((w, row_h), Image.LANCZOS))
        x += w + gap
    rows.append(row)
    sheet = Image.new("RGB", (width, gap + len(rows) * (row_h + gap)), SAND)
    for r, items in enumerate(rows):
        x = gap
        for im in items:
            sheet.paste(im, (x, gap + r * (row_h + gap)))
            x += im.width + gap
    sheet.save(OUT / "overview.png")
    print("  wrote", (OUT / "overview.png").relative_to(ROOT))


PIECES = {"brand": brand_sheet, "hero": hero_post, "story": story, "carousel": carousel, "cards": cards,
          "banners": banners, "flyer": flyer, "motion": breathe, "overview": overview}

if __name__ == "__main__":
    prepare()
    chosen = sys.argv[1:] or list(PIECES)
    for key in chosen:
        print(key)
        PIECES[key]()
