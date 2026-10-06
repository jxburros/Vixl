"""SOLSTICE SIGNAL - a print-ready tabloid festival poster built with Vixl.

Run from the repo root:  python explorations/01-print-concert-poster/build.py
Everything lands in explorations/01-print-concert-poster/output/ (wiped on each run).
"""

import json
import math
import os
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "output"
WORK = HERE / ".work"  # font cache + resources, kept out of output/

# The document is a real 11x17 in tabloid with 1/8 in bleed. 150 dpi keeps the
# exported files inside the exploration's size budget; set DPI = 300 for press.
DPI = 150

if OUT.exists():
    shutil.rmtree(OUT)
OUT.mkdir(parents=True)
WORK.mkdir(exist_ok=True)

ENV = dict(os.environ)
ENV.update(
    VIXL_RESOURCES=str(WORK / "resources"),
    VIXL_FONT_CACHE=str(WORK / "fonts"),
    VIXL_NO_UPDATE="1",
)
os.environ.update({k: ENV[k] for k in ("VIXL_RESOURCES", "VIXL_FONT_CACHE", "VIXL_NO_UPDATE")})

from vixl import Project  # noqa: E402  (import after env so resources/fonts resolve locally)

DOC = OUT / "solstice-signal.vixl"
LOG = {}


def vixl(*args, key=None, ok_codes=(0,)):
    """Run the vixl CLI against our document, return parsed JSON when possible."""
    cmd = ["vixl", "-p", str(DOC), *map(str, args)]
    if args[0] == "export":
        cmd.append("--overwrite")  # .work/ files survive between runs; exports refuse to replace them
    res = subprocess.run(cmd, capture_output=True, text=True, env=ENV)
    if res.returncode not in ok_codes:
        print(" ".join(cmd), "\n", res.stdout, res.stderr, file=sys.stderr)
        raise SystemExit(res.returncode)
    try:
        data = json.loads(res.stdout)
    except json.JSONDecodeError:
        data = res.stdout.strip()
    if key:
        LOG[key] = data
    return data


# ---------------------------------------------------------------- 1. canvas + type
subprocess.run(
    ["vixl", "new", "tabloid", "--bleed", "--dpi", str(DPI), "--background", "#140a33", "-o", str(DOC)],
    check=True, env=ENV, capture_output=True,
)
vixl("font", "pair", "syne-dm-sans", key="font_pair")          # Syne 800 heading / DM Sans 400 body
vixl("font", "install", "DM Sans", "--weight", "700", key="font_install")  # bold cut for lineup tiers

p = Project.load(DOC)
cv = p.inspect()["canvas"]
W, H = cv["width"], cv["height"]
S = W / 1688  # all hand-tuned numbers below are for the 150 dpi canvas


def px(v):
    return int(round(v * S))


HORIZON = px(1505)
CX = W // 2

# ---------------------------------------------------------------- 2. colour system
ops = [
    # generated ramps: a hot pink scale and a split-complementary harmony
    {"type": "palette-generate", "name": "dusk", "color": "#ff4f8b", "scheme": "scale"},
    {"type": "palette-generate", "name": "volt", "color": "#ffb23f", "scheme": "split-complementary"},
    # semantic roles built on top of the generated swatches
    {"type": "swatch", "name": "night", "color": "oklch(0.17 0.08 290)"},
    {"type": "swatch", "name": "background", "color": "@night"},
    {"type": "swatch", "name": "ink", "color": "#fff4e6"},
    {"type": "swatch", "name": "muted", "color": "mix(@ink, @dusk-300, 35%)"},
    {"type": "swatch", "name": "accent", "color": "@dusk-500"},
    {"type": "swatch", "name": "sun-hot", "color": "#ffd85e"},
    {"type": "swatch", "name": "sun-mid", "color": "#ff8a3d"},
    {"type": "swatch", "name": "teal", "color": "@volt-2"},
    {"type": "swatch", "name": "lilac", "color": "@volt-3"},
    {"type": "swatch", "name": "accent-text", "color": "readable(@night, @sun-hot, @dusk-300, @ink)"},
]
p.apply(ops, detail="compact")


def text_width(text, font, size):
    """Measure set text with a dry run (nothing is saved)."""
    r = p.apply([{"type": "text", "name": "probe", "text": text, "font": font, "size": size}],
                dry_run=True, detail="compact")
    return next(iter(r["changes"]["layers"].values()))["bounds"][2]


def fit_size(text, font, max_w, start):
    """Largest size <= start whose widest line fits max_w (Syne's width varies a lot)."""
    w = max(text_width(line, font, start) for line in text.split("\n"))
    return start if w <= max_w else int(start * max_w / w)


ops = []

# ---------------------------------------------------------------- 3. sky, sun, stars
ops += [
    {"type": "gradient", "name": "sky", "width": W, "height": HORIZON + px(40), "x": 0, "y": 0,
     "direction": "vertical", "stops": [
         {"offset": 0.0, "color": "@night"},
         {"offset": 0.35, "color": "#2a0f5c"},
         {"offset": 0.62, "color": "#7a1f7a"},
         {"offset": 0.82, "color": "@dusk-500"},
         {"offset": 1.0, "color": "@sun-mid"}]},
    # radial haze behind the sun, screened on
    {"type": "gradient", "name": "haze", "width": px(1700), "height": px(1700),
     "x": CX - px(850), "y": HORIZON - px(1150), "direction": "radial", "stops": [
         {"offset": 0.0, "color": "alpha(@sun-hot, 0.55)"},
         {"offset": 0.45, "color": "alpha(@dusk-400, 0.25)"},
         {"offset": 1.0, "color": "alpha(@dusk-400, 0)"}]},
    {"type": "blend", "target": "haze", "value": "screen"},
]

SUN_D = px(1000)
SUN_Y = HORIZON - px(650)
ops += [
    {"type": "shape", "shape": "ellipse", "name": "sun", "width": SUN_D, "height": SUN_D,
     "x": CX - SUN_D // 2, "y": SUN_Y, "fill": "@sun-hot"},
    {"type": "layer-style", "target": "sun", "name": "gradient-overlay", "settings": {
        "direction": "vertical", "stops": [
            {"offset": 0, "color": "@sun-hot"},
            {"offset": 0.5, "color": "@sun-mid"},
            {"offset": 1, "color": "@dusk-500"}]}},
    {"type": "layer-style", "target": "sun", "name": "outer-glow",
     "settings": {"color": "@dusk-400", "blur": 60, "opacity": 0.8}},
    # sky-coloured slices that thicken towards the horizon, clipped to the sun disc
    {"type": "shape", "shape": "rectangle", "name": "slice", "width": SUN_D + px(40), "height": px(6),
     "x": CX - SUN_D // 2 - px(20), "y": SUN_Y + px(380), "fill": "#7a1f7a"},
    {"type": "repeat-blend", "target": "slice", "count": 9, "dy": px(40), "dh": px(3),
     "end": {"height": px(30), "fill": "@dusk-500"}},
    {"type": "group", "name": "sun-slices", "targets": ["slice"]},
    {"type": "clip", "target": "sun-slices", "base": "sun"},
    {"type": "blend", "target": "sun-slices", "value": "multiply"},
]

# stars: a small field + a few bright four-point sparkles
star_field = [(70, 330, 16), (250, 640, 12), (1580, 420, 16), (1420, 690, 10), (180, 960, 12),
              (1560, 1010, 14), (95, 760, 9), (1610, 220, 9), (420, 1080, 8), (1270, 1040, 8),
              (60, 1180, 10), (1490, 560, 7)]
for i, (x, y, r) in enumerate(star_field):
    ops.append({"type": "shape", "shape": "star", "name": f"star-{i}", "width": px(r * 2), "height": px(r * 2),
                "x": px(x), "y": px(y), "sides": 5, "inner_radius": 0.45, "fill": "@ink"})
for i, (x, y, r) in enumerate([(300, 760, 46), (1430, 820, 38), (1240, 470, 30)]):
    name = f"sparkle-{i}"
    ops += [
        {"type": "shape", "shape": "star", "name": name, "width": px(r * 2), "height": px(r * 2),
         "x": px(x), "y": px(y), "sides": 4, "inner_radius": 0.16, "fill": "@ink"},
        {"type": "layer-style", "target": name, "name": "outer-glow",
         "settings": {"color": "@sun-hot", "blur": 24, "opacity": 0.9}},
    ]

# ---------------------------------------------------------------- 4. mountains + ground
ops += [
    {"type": "shape", "shape": "polygon", "name": "peak-far-l", "sides": 3, "width": px(900), "height": px(380),
     "x": px(-180), "y": HORIZON - px(375), "fill": "#3a1364"},
    {"type": "shape", "shape": "polygon", "name": "peak-far-r", "sides": 3, "width": px(1000), "height": px(440),
     "x": px(980), "y": HORIZON - px(435), "fill": "#3a1364"},
    {"type": "shape", "shape": "polygon", "name": "peak-near-l", "sides": 3, "width": px(700), "height": px(250),
     "x": px(220), "y": HORIZON - px(245), "fill": "#1d0b40"},
    {"type": "shape", "shape": "polygon", "name": "peak-near-r", "sides": 3, "width": px(620), "height": px(220),
     "x": px(1180), "y": HORIZON - px(215), "fill": "#1d0b40"},
    {"type": "group", "name": "mountains",
     "targets": ["peak-far-l", "peak-far-r", "peak-near-l", "peak-near-r"]},
    {"type": "layer-style", "target": "mountains", "name": "gradient-overlay", "settings": {
        "direction": "vertical", "stops": [
            {"offset": 0, "color": "#6b3a9e"},
            {"offset": 0.35, "color": "#3a1667"},
            {"offset": 1, "color": "#14072e"}]}},
    {"type": "opacity", "target": "mountains", "value": 0.97},
    # ground: angled multi-stop gradient
    {"type": "gradient", "name": "ground", "width": W, "height": H - HORIZON, "x": 0, "y": HORIZON,
     "direction": "angled", "angle": 80, "stops": [
         {"offset": 0, "color": "#2b0c4f"},
         {"offset": 0.4, "color": "#170a35"},
         {"offset": 1, "color": "#07041a"}]},
    {"type": "solid", "name": "horizon-line", "width": W, "height": px(4), "x": 0, "y": HORIZON,
     "color": "@dusk-300"},
    {"type": "layer-style", "target": "horizon-line", "name": "outer-glow",
     "settings": {"color": "@dusk-400", "blur": 18, "opacity": 1}},
]

# perspective grid: horizontal rungs via repeat-blend (closer = thicker, wider gaps impossible,
# so dh grows instead) + a fan of rays drawn as ONE path contour from the vanishing point
GROUND_H = H - HORIZON
ops += [
    {"type": "shape", "shape": "rectangle", "name": "rung", "width": W, "height": px(2), "x": 0,
     "y": HORIZON + px(18), "fill": "alpha(@dusk-400, 0.55)"},
    {"type": "repeat-blend", "target": "rung", "count": 14, "dy": px(78), "dh": px(0.4),
     "end": {"height": px(7), "fill": "alpha(@teal, 0.35)"}},
]
fan = []
vx, vy = W / 2, 0
for k in range(-12, 13):
    bx = W / 2 + k * (W / 7.5)
    fan.append(f"M{vx:.1f} {vy:.1f} L{bx:.1f} {GROUND_H:.1f}")
ops += [
    {"type": "shape", "shape": "path", "name": "rays", "width": W, "height": GROUND_H, "x": 0, "y": HORIZON,
     "path": " ".join(fan), "fill": "transparent", "stroke": "alpha(@dusk-400, 0.45)", "stroke_width": px(3)},
    {"type": "group", "name": "grid", "targets": ["rung", "rays"]},
    {"type": "blend", "target": "grid", "value": "screen"},
]

# ---------------------------------------------------------------- 5. headline type
SIG_SIZE = fit_size("SIGNAL", "heading", px(1080), px(220))
ops += [
    {"type": "text", "name": "title", "text": "SOLSTICE", "font": "heading",
     "size": fit_size("SOLSTICE", "heading", px(1440), px(260)),
     "color": "@ink", "align": "center"},
    {"type": "text-layout", "target": "title", "width": px(1580), "height": px(330),
     "warp": "arc", "amount": 0.2},
    {"type": "constrain", "target": "title",
     "constraints": {"center-x": "canvas.center-x", "top": "guide:safe-top.top+70"}},
    {"type": "layer-style", "target": "title", "name": "gradient-overlay", "settings": {
        "direction": "vertical", "stops": [
            {"offset": 0, "color": "@ink"},
            {"offset": 0.55, "color": "@sun-hot"},
            {"offset": 1, "color": "@sun-mid"}]}},
    {"type": "layer-style", "target": "title", "name": "stroke", "settings": {"color": "@night", "width": 6}},
    {"type": "layer-style", "target": "title", "name": "drop-shadow",
     "settings": {"color": "@dusk-600", "dx": 0, "dy": 18, "blur": 0, "opacity": 1}},

    {"type": "text", "name": "subtitle", "text": "SIGNAL", "font": "heading", "size": SIG_SIZE,
     "color": "@night", "align": "center"},
    {"type": "text-layout", "target": "subtitle", "width": px(1300), "height": px(330),
     "warp": "flag", "amount": 0.12},
    {"type": "layer-style", "target": "subtitle", "name": "stroke", "settings": {"color": "@sun-hot", "width": 5}},
    {"type": "constrain", "target": "subtitle",
     "constraints": {"center-x": "canvas.center-x", "top": "title.bottom-110"}},
    {"type": "layer-style", "target": "subtitle", "name": "outer-glow",
     "settings": {"color": "@dusk-400", "blur": 30, "opacity": 0.9}},
]

# text on a path: an arc concentric with the sun. Measure the set line with a dry run
# first so the arc spans exactly the text, centred at 12 o'clock.
ARC_TEXT = "THREE NIGHTS  \u2022  UNDER THE LONGEST SUN  \u2022  MOJAVE DESERT"
ARC_SIZE = px(42)
probe = p.apply([{"type": "text", "name": "probe", "text": ARC_TEXT, "font": "dm-sans-700", "size": ARC_SIZE}],
                dry_run=True, detail="compact")
text_w = next(iter(probe["changes"]["layers"].values()))["bounds"][2]
ARC_R = SUN_D // 2 + px(95)             # baseline radius
PAD = px(70)                             # room for glyph height above the baseline
span = (text_w * 1.04) / ARC_R           # radians the text needs
ARC_W = 2 * ARC_R + 2 * PAD
ARC_H = ARC_R + PAD + px(10)
arc_pts = []
for i in range(61):
    a = -math.pi / 2 - span / 2 - 0.02 + i * (span + 0.04) / 60
    arc_pts.append([round(ARC_W / 2 + ARC_R * math.cos(a), 1), round(ARC_R + PAD + ARC_R * math.sin(a), 1)])
ops += [
    {"type": "text", "name": "arc-line", "text": ARC_TEXT, "font": "dm-sans-700", "size": ARC_SIZE,
     "color": "@ink"},
    {"type": "text-layout", "target": "arc-line", "width": ARC_W, "height": ARC_H, "path": arc_pts},
    {"type": "constrain", "target": "arc-line",
     "constraints": {"center-x": "sun.center-x", "top": f"sun.center-y-{ARC_R + PAD}"}},
]

ops += [
    {"type": "text", "name": "eyebrow", "text": "VOL. IV  \u2014  A DESERT LISTENING FESTIVAL",
     "font": "dm-sans-700", "size": px(30), "color": "@lilac"},
    {"type": "constrain", "target": "eyebrow",
     "constraints": {"center-x": "canvas.center-x", "bottom": f"arc-line.top-{px(8)}"}},
]

# ---------------------------------------------------------------- 6. date badge
ops += [
    {"type": "shape", "shape": "star", "name": "badge", "width": px(360), "height": px(360), "sides": 18,
     "inner_radius": 0.84, "fill": "@teal"},
    {"type": "constrain", "target": "badge",
     "constraints": {"right": "guide:safe-right.right-40", "top": f"sun.top+{px(330)}"}},
    {"type": "rotate", "target": "badge", "value": 12},
    {"type": "layer-style", "target": "badge", "name": "drop-shadow",
     "settings": {"color": "#07041a", "dx": 8, "dy": 12, "blur": 0, "opacity": 0.85}},
    {"type": "text", "name": "badge-text", "text": "JUNE\n19–21", "font": "heading", "size": px(50),
     "color": "@night", "align": "center", "spacing": 0},
    {"type": "constrain", "target": "badge-text",
     "constraints": {"center-x": "badge.center-x", "center-y": "badge.center-y"}},
    {"type": "rotate", "target": "badge-text", "value": 12},
]

# ---------------------------------------------------------------- 7. lineup panel
PANEL_W = px(1420)
PANEL_H = px(690)
ops += [
    {"type": "shape", "shape": "rounded-rectangle", "name": "panel", "width": PANEL_W, "height": PANEL_H,
     "radius": px(36), "fill": "alpha(#07041a, 0.72)", "stroke": "alpha(@dusk-300, 0.8)",
     "stroke_width": px(3)},
    {"type": "constrain", "target": "panel",
     "constraints": {"center-x": "canvas.center-x", "top": f"canvas.top+{HORIZON + px(105)}"}},
    {"type": "layer-style", "target": "panel", "name": "outer-glow",
     "settings": {"color": "@dusk-500", "blur": 40, "opacity": 0.55}},

    {"type": "text", "name": "lineup-label", "text": "THE  LINEUP", "font": "dm-sans-700", "size": px(34),
     "color": "@accent-text"},
    {"type": "constrain", "target": "lineup-label",
     "constraints": {"center-x": "panel.center-x", "top": f"panel.top+{px(48)}"}},

    {"type": "text", "name": "headliners", "text": "NOVA CRANE\nTHE GLASS ORCHARD", "font": "heading",
     "size": fit_size("NOVA CRANE\nTHE GLASS ORCHARD", "heading", px(1240), px(110)),
     "color": "@ink", "align": "center", "spacing": px(6)},
    {"type": "constrain", "target": "headliners",
     "constraints": {"center-x": "panel.center-x", "top": "lineup-label.bottom+28"}},

    {"type": "text", "name": "support",
     "text": "MIRA SOL  •  HALCYON DRIFT  •  OKONKWO & THE TIDES\n"
             "PALE LANTERN  •  JUNO VEGA  •  SILVER COYOTE",
     "font": "dm-sans-700", "size": px(46), "color": "@sun-hot", "align": "center", "spacing": px(18)},
    {"type": "constrain", "target": "support",
     "constraints": {"center-x": "panel.center-x", "top": "headliners.bottom+40"}},

    {"type": "text", "name": "undercard",
     "text": "Ada Reyes · Low Meridian · Fennel & Smoke · Dust Choir · Kestrel Hum\n"
             "Wren Okafor · The Dry Lakes · Sunset Telegraph · DJ Marisol (sunrise set)",
     "font": "body", "size": px(34), "color": "@muted", "align": "center", "spacing": px(14)},
    {"type": "constrain", "target": "undercard",
     "constraints": {"center-x": "panel.center-x", "top": "support.bottom+34"}},

    {"type": "shape", "shape": "line", "name": "panel-rule", "width": px(360), "height": px(3),
     "stroke": "alpha(@dusk-300, 0.7)", "stroke_width": px(3)},
    {"type": "constrain", "target": "panel-rule",
     "constraints": {"center-x": "panel.center-x", "top": "undercard.bottom+36"}},
    {"type": "text", "name": "extras",
     "text": "ART CARS  \u00b7  STAR PARTY  \u00b7  SUNRISE YOGA  \u00b7  +30 MORE",
     "font": "dm-sans-700", "size": px(32), "color": "@teal"},
    {"type": "constrain", "target": "extras",
     "constraints": {"center-x": "panel.center-x", "top": "panel-rule.bottom+30"}},
]

# ---------------------------------------------------------------- 8. footer (anchored to safe guides)
ops += [
    {"type": "text", "name": "venue", "text": "MOJAVE DRY LAKE BED\nLUCERNE VALLEY, CALIFORNIA",
     "font": "dm-sans-700", "size": px(40), "color": "@ink", "spacing": px(10)},
    {"type": "constrain", "target": "venue",
     "constraints": {"left": "guide:safe-left.left+60", "bottom": "guide:safe-bottom.bottom-70"}},

    {"type": "shape", "shape": "capsule", "name": "cta", "width": px(520), "height": px(110), "fill": "@sun-hot"},
    {"type": "constrain", "target": "cta",
     "constraints": {"right": "guide:safe-right.right-60", "bottom": "guide:safe-bottom.bottom-70"}},
    {"type": "layer-style", "target": "cta", "name": "drop-shadow",
     "settings": {"color": "@dusk-600", "dx": 0, "dy": 10, "blur": 0, "opacity": 1}},
    {"type": "text", "name": "cta-text", "text": "SOLSTICESIGNAL.FM", "font": "dm-sans-700", "size": px(40),
     "color": "@night"},
    {"type": "constrain", "target": "cta-text",
     "constraints": {"center-x": "cta.center-x", "center-y": "cta.center-y"}},

    {"type": "text", "name": "fineprint",
     "text": "ALL AGES  ·  CAMPING INCLUDED  ·  NO GLASS  ·  LEAVE NO TRACE",
     "font": "body", "size": px(26), "color": "@muted"},
    {"type": "constrain", "target": "fineprint",
     "constraints": {"center-x": "canvas.center-x", "bottom": "guide:safe-bottom.bottom-12"}},
]

# ---------------------------------------------------------------- 9. finishing: grain + vignette
ops += [
    {"type": "adjustment", "name": "vignette",
     "effects": [{"name": "vignette", "strength": 0.55, "radius": 0.95}]},
    {"type": "adjustment", "name": "grain", "effects": [{"name": "grain", "amount": 0.07, "seed": 7}]},
    {"type": "blend", "target": "grain", "value": "overlay"},
    {"type": "opacity", "target": "grain", "value": 0.8},
]

res = p.apply(ops, detail="compact")
LOG["apply_normalized"] = res.get("normalized")

# Comps: "print" is the finished poster; "vector" switches off the backdrop-dependent
# layers (screen/multiply/overlay blends, adjustment layers) that otherwise force the SVG
# exporter to rasterize the entire document into one <image>.
p.apply([
    {"type": "comp-save", "name": "print"},
    {"type": "hide", "target": "haze"},
    {"type": "hide", "target": "vignette"},
    {"type": "hide", "target": "grain"},
    {"type": "blend", "target": "sun-slices", "value": "normal"},
    {"type": "blend", "target": "grid", "value": "normal"},
    {"type": "comp-save", "name": "vector"},
    {"type": "comp-apply", "name": "print"},
])
p.checkpoint("poster-v1")
p.save(DOC)

if os.environ.get("QUICK"):
    img = p.render()
    img.thumbnail((1100, 1100))
    img.save(WORK / "quick.png")
    raise SystemExit(0)

# ---------------------------------------------------------------- 10. QA
FAST = ["bounds", "overlap", "safe_area", "legibility", "print", "color_vision"]
vixl("check", "--checks", *FAST, "--ink-limit", "300", key="check_print_colorvision", ok_codes=(0, 1))
vixl("check", "--checks", "contrast", key="check_contrast_all", ok_codes=(0, 1))

# ---------------------------------------------------------------- 11. renders + exports
# Vixl ships no press profiles. Without one, --proof only reflects the GCR/ink-limit
# separation, which round-trips almost exactly to RGB. Fetch Artifex's free SWOP-like
# CMYK profile (Ghostscript) so the soft proof actually shows press gamut loss.
ICC = WORK / "default_cmyk.icc"
if not ICC.exists():
    import urllib.request

    try:
        urllib.request.urlretrieve(
            "https://raw.githubusercontent.com/ArtifexSoftware/ghostpdl/master/iccprofiles/default_cmyk.icc", ICC)
    except Exception as exc:  # offline: the GCR proof still works
        print("ICC download failed:", exc, file=sys.stderr)
HAVE_ICC = ICC.exists()
LOG["icc_profile"] = str(ICC.name) if HAVE_ICC else None

MAIN = round(1500 / H, 4)
SMALL = round(1000 / H, 4)
vixl("export", OUT / "poster-rgb.png", "--scale", MAIN, key="export_png")
vixl("export", WORK / "proof-gcr.png", "--proof", "--ink-limit", "300", "--scale", MAIN)
if HAVE_ICC:
    vixl("export", OUT / "poster-softproof-swop.png", "--proof", "--icc", ICC, "--intent", "perceptual",
         "--scale", MAIN)
for kind in ("deuteranopia", "protanopia", "tritanopia"):
    vixl("export", WORK / f"sim-{kind}.png", "--simulate", kind, "--scale", SMALL)
# The poster's blend modes and adjustment layers make the whole page an image anyway.
# Vixl 0.20.0's vector PDF writer crashes on such pages (KeyError 'type' in the page
# fallback), so ask for a raster page directly.
vixl("export", OUT / "poster-cmyk.pdf", "--cmyk", "--ink-limit", "300", "--quality", "75",
     "--pdf-content", "raster", key="export_pdf")
if HAVE_ICC:
    vixl("export", OUT / "poster-cmyk-swop.jpg", "--cmyk", "--icc", ICC, "--intent", "relative",
         "--quality", "72", key="export_jpg")
else:
    vixl("export", OUT / "poster-cmyk.jpg", "--cmyk", "--ink-limit", "300", "--quality", "72", key="export_jpg")
vixl("export", OUT / "poster.svg", "--comp", "vector", key="export_svg")
vixl("export", WORK / "poster-fullcomp.svg", key="export_svg_full_comp")

# ---------------------------------------------------------------- 12. verify the print files
import numpy as np  # noqa: E402
from PIL import Image, ImageDraw, ImageFont  # noqa: E402


def ink_stats(path):
    im = Image.open(path)
    a = np.asarray(im, dtype=np.float32)
    tac = a.sum(axis=2) / 255 * 100
    return {"mode": im.mode, "size": im.size, "dpi": im.info.get("dpi"),
            "max_total_ink_pct": round(float(tac.max()), 1),
            "p99_total_ink_pct": round(float(np.percentile(tac, 99)), 1)}


LOG["cmyk_jpeg"] = ink_stats(OUT / ("poster-cmyk-swop.jpg" if HAVE_ICC else "poster-cmyk.jpg"))
pdf = (OUT / "poster-cmyk.pdf").read_bytes()
LOG["pdf"] = {"header": pdf[:8].decode("latin-1"), "DeviceCMYK": b"DeviceCMYK" in pdf,
              "DCTDecode": b"DCTDecode" in pdf, "MediaBox": pdf[pdf.find(b"/MediaBox"):][:40].decode("latin-1")}
svg = (OUT / "poster.svg").read_text(errors="replace")
LOG["svg"] = {"bytes": len(svg), "image_elements": svg.count("<image"), "path_elements": svg.count("<path")}


def label_sheet(items, out, width=2000):
    ims = [Image.open(f).convert("RGB") for f, _ in items]
    w, h = ims[0].size
    sheet = Image.new("RGB", (len(ims) * (w + 12) + 12, h + 64), "#111")
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default(max(14, w // 26))
    for i, (im, (_, label)) in enumerate(zip(ims, items)):
        sheet.paste(im, (12 + i * (w + 12), 52))
        draw.text((12 + i * (w + 12), 14), label, fill="#eee", font=font)
    sheet.thumbnail((width, width))
    sheet.save(out, quality=86) if str(out).endswith(".jpg") else sheet.save(out, optimize=True)


def mean_diff(a, b):
    x = np.asarray(Image.open(a).convert("RGB"), dtype=np.int16)
    y = np.asarray(Image.open(b).convert("RGB"), dtype=np.int16)
    d = np.abs(x - y)
    return {"mean_abs_rgb": round(float(d.mean()), 2), "max_abs_rgb": int(d.max()),
            "pct_pixels_changed_gt8": round(float((d.max(axis=2) > 8).mean() * 100), 1)}


LOG["proof_vs_rgb"] = {"gcr_ink_limit_300": mean_diff(OUT / "poster-rgb.png", WORK / "proof-gcr.png")}
items = [(OUT / "poster-rgb.png", "RGB render"), (WORK / "proof-gcr.png", "proof: GCR, TAC 300%")]
if HAVE_ICC:
    LOG["proof_vs_rgb"]["swop_icc_perceptual"] = mean_diff(OUT / "poster-rgb.png", OUT / "poster-softproof-swop.png")
    items.append((OUT / "poster-softproof-swop.png", "proof: SWOP ICC"))
label_sheet(items, OUT / "compare-rgb-vs-proof.jpg")
label_sheet([(WORK / f"sim-{k}.png", k) for k in ("deuteranopia", "protanopia", "tritanopia")],
            OUT / "colorvision-sims.jpg")

(OUT / "qa-report.json").write_text(json.dumps(LOG, indent=2, default=str))
total = 0
for f in sorted(OUT.iterdir()):
    total += f.stat().st_size
    print(f"{f.name:32s} {f.stat().st_size / 1e6:6.2f} MB")
print(f"{'TOTAL':32s} {total / 1e6:6.2f} MB")
