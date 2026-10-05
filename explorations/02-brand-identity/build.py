"""Morrow Coffee Roasters — a complete brand identity system built with Vixl.

Run from the repository root:

    python explorations/02-brand-identity/build.py

Everything (editable .vixl sources, exports, check reports) is written to
explorations/02-brand-identity/output/, which is wiped and recreated on every run.
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
WORK = OUT / "work"  # Vixl workspace: editable .vixl sources + workspace resource library

if OUT.exists():
    shutil.rmtree(OUT)
for d in (OUT, WORK, OUT / "logo", OUT / "card", OUT / "icons", OUT / "board", OUT / "reports"):
    d.mkdir(parents=True, exist_ok=True)

# Isolate the user-level resource library from the other agents running in this repo.
os.environ["VIXL_RESOURCES"] = str(WORK / "user-resources.json")
os.environ.setdefault("VIXL_NO_UPDATE", "1")

from vixl import Project  # noqa: E402
from vixl.interfaces import Session  # noqa: E402
from vixl.render import color as parse_color  # noqa: E402
from vixl.design import resolve_color  # noqa: E402
from vixl.typefaces import pair_fonts, install_font  # noqa: E402
from vixl.workflows import dispatch  # noqa: E402
from vixl.exports import export_icons  # noqa: E402

REPORT = {}


def hexof(project, value):
    r, g, b, _ = parse_color(resolve_color(value, project.state))
    return f"#{r:02X}{g:02X}{b:02X}"


def save_json(name, data):
    (OUT / "reports" / name).write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")


def run_cli(*args):
    """Run the vixl CLI (used where the Python API has no direct helper)."""
    env = dict(os.environ)
    res = subprocess.run(["vixl", *args], capture_output=True, text=True, env=env, cwd=str(WORK))
    if res.returncode != 0:
        raise SystemExit(f"vixl {' '.join(args)} failed:\n{res.stdout}\n{res.stderr}")
    return res.stdout


# ---------------------------------------------------------------------------
# 1. Brand foundations: palette-generate (scale + harmony), swatches with modifiers,
#    palette-define, and the type pairing.
# ---------------------------------------------------------------------------

BRAND_OPS = [
    # A full 50–950 tonal scale from the ember accent …
    {"type": "palette-generate", "name": "ember", "color": "#D9642B", "scheme": "scale"},
    # … and a split-complementary harmony, whose teal we darken into a secondary colour.
    {"type": "palette-generate", "name": "accord", "color": "#D9642B", "scheme": "split-complementary"},
    {"type": "swatch", "name": "roast", "color": "#3B2418"},
    {"type": "swatch", "name": "crema", "color": "#F3E9DA"},
    {"type": "swatch", "name": "ember", "color": "@ember-400"},
    {"type": "swatch", "name": "ember-deep", "color": "@ember-700"},
    {"type": "swatch", "name": "kettle", "color": "shade(@accord-2, 45%)"},
    {"type": "swatch", "name": "oat", "color": "mix(@roast, @crema, 80%)"},
    # Near-black brown: roast alone only reaches 4.0:1 on ember, short of 4.5:1 for small text.
    {"type": "swatch", "name": "espresso", "color": "shade(@roast, 50%)"},
    # Derived helpers (not brand colours, used for UI text on chips etc.)
    {"type": "swatch", "name": "on-ember", "color": "readable(@ember, @espresso, @crema)"},
    {"type": "swatch", "name": "on-kettle", "color": "readable(@kettle, @espresso, @crema)"},
    {"type": "swatch", "name": "ember-glow", "color": "lighten(@ember, 12%)"},
]

BRAND_ROLES = ["roast", "crema", "ember", "ember-deep", "kettle", "oat"]
BRAND_NAMES = {
    "roast": "Dark Roast",
    "crema": "Crema",
    "ember": "Ember",
    "ember-deep": "Kiln",
    "kettle": "Kettle",
    "oat": "Oat Milk",
}


def brand_doc(project, fonts=True, extra_fonts=False):
    """Install the shared brand system into a document."""
    project.apply(BRAND_OPS)
    colors = [hexof(project, "@" + k) for k in BRAND_ROLES]
    # palette-define freezes the resolved brand colours as a named palette in the document.
    project.apply({"type": "palette-define", "name": "morrow", "colors": colors})
    if fonts:
        pair_fonts(project, "fraunces-work-sans")  # Fraunces 700 heading + Work Sans 400 body
        install_font(project, "Work Sans", 600, name="work-600")
        if extra_fonts:
            install_font(project, "Fraunces", 400, italic=True, name="fraunces-italic")
            install_font(project, "Work Sans", 300, name="work-300")
            install_font(project, "JetBrains Mono", 500, name="mono")
    return colors


# ---------------------------------------------------------------------------
# 2. The mark: pen-tool Bézier bean, a path-shape crease, pathfinder subtract,
#    sunrise bands, nested pathfinder.
# ---------------------------------------------------------------------------

BEAN_NODES = [  # 220 × 300 local space; explicit in/out Bézier handles (pen tool)
    {"point": [110, 0], "in": [49, 0], "out": [171, 0]},
    {"point": [220, 140], "in": [220, 63], "out": [220, 228]},
    {"point": [105, 300], "in": [168, 300], "out": [47, 300]},
    {"point": [0, 160], "in": [0, 237], "out": [0, 72]},
]
CREASE = (
    "M116 -12 C72 60 156 104 108 156 C62 206 140 248 98 312 "
    "L118 312 C162 248 84 206 130 156 C178 104 94 60 138 -12 Z"
)
BEAN_TILT = 24
BANDS = [(352, 12), (382, 14), (414, 16), (448, 18)]  # sunrise reflection cut-outs (y, h)


def mark_ops(p, x=0, y=0, size=480, fill="@roast"):
    """Operations that build the Morrow mark (a 480-unit disc) at x, y scaled to `size`.
    Returns operations; the final layer is named f"{p}mark"."""
    k = size / 480
    bw, bh = 185 * k, 252 * k
    cx, cy = x + 246 * k, y + 192 * k
    t = math.radians(BEAN_TILT)
    rw = bw * math.cos(t) + bh * math.sin(t)
    rh = bw * math.sin(t) + bh * math.cos(t)
    ops = [
        {"type": "shape", "shape": "ellipse", "name": f"{p}disc", "x": x, "y": y,
         "width": round(size), "height": round(size), "fill": fill},
        {"type": "pen", "name": f"{p}bean", "width": 220, "height": 300, "closed": True,
         "fill": fill, "stroke": "transparent", "stroke_width": 0, "nodes": BEAN_NODES},
        {"type": "shape", "shape": "path", "name": f"{p}crease", "width": 220, "height": 300,
         "fill": fill, "path": CREASE},
        {"type": "pathfinder", "name": f"{p}bean-halves", "targets": [f"{p}bean", f"{p}crease"], "mode": "subtract"},
        {"type": "resize", "target": f"{p}bean-halves", "width": round(bw), "height": round(bh)},
        # Rotation expands the layer box and x/y address the *rotated* box, so rotate first
        # and then place the expanded box around the intended centre.
        {"type": "rotate", "target": f"{p}bean-halves", "value": -BEAN_TILT},
        {"type": "move", "target": f"{p}bean-halves", "x": round(cx - rw / 2), "y": round(cy - rh / 2)},
    ]
    names = [f"{p}disc", f"{p}bean-halves"]
    for i, (by, bh_) in enumerate(BANDS):
        ops.append({"type": "shape", "shape": "rectangle", "name": f"{p}band{i}",
                    "x": x, "y": round(y + by * k), "width": round(size), "height": max(1, round(bh_ * k)),
                    "fill": fill})
        names.append(f"{p}band{i}")
    ops.append({"type": "pathfinder", "name": f"{p}mark", "targets": names, "mode": "subtract"})
    return ops


def sun_ops(p, x, y, size, fill="@ember", inset=0):
    """The ember disc that sits behind the mark (shows through the bean and the bands)."""
    inset = 0 if inset is None else inset
    return [{"type": "shape", "shape": "ellipse", "name": f"{p}sun", "x": x + inset, "y": y + inset,
             "width": round(size - 2 * inset), "height": round(size - 2 * inset), "fill": fill}]


def tracked(text, gap=" "):
    """Fake letter-spacing (Vixl text has no tracking control) with thin spaces."""
    return " ".join(gap.join(word) for word in text.split(" "))


def bounds(project, name):
    return project.inspect(name)["resolved_bounds"]


# ---------------------------------------------------------------------------
# 3. Mark master document (logo-mark size): transparent PNG, strict SVG, saved shape.
# ---------------------------------------------------------------------------

def build_mark(session):
    p = Project.sized("logo-mark", background="transparent")  # 512 × 512
    brand_doc(p, fonts=False)
    p.apply(sun_ops("", 16, 16, 480) + mark_ops("", 16, 16, 480))
    p.save(WORK / "mark.vixl")
    p.export(OUT / "logo" / "morrow-mark.png")  # transparent PNG
    p.export(OUT / "logo" / "morrow-mark.svg", svg_policy="strict")
    # Single-colour (one-ink) version for stamps, embossing and engraving.
    p.apply({"type": "hide", "target": "sun"})
    p.export(OUT / "logo" / "morrow-mark-1color.svg", svg_policy="strict")
    p.apply({"type": "show", "target": "sun"})
    p.save()
    # Save the pen-drawn bean as a reusable workspace shape resource.
    REPORT["shape-save"] = dispatch(session, "shape-save", {"target": "bean", "name": "morrow-bean"}, "mark.vixl")
    return p


# ---------------------------------------------------------------------------
# 4. Lockups: a symbol master + symbol-instances, composed into horizontal / stacked
#    lockups and published as two artboards built from the named logo sizes.
# ---------------------------------------------------------------------------

def add_masters(p):
    """Two symbol masters (positive and reversed) kept hidden; instances follow them."""
    p.apply(mark_ops("master-", 0, 0, 480, fill="@roast"))
    p.apply(mark_ops("master-rev-", 0, 0, 480, fill="@crema"))
    p.apply([
        {"type": "symbol", "target": "master-mark", "name": "MorrowMark"},
        {"type": "symbol", "target": "master-rev-mark", "name": "MorrowMarkReversed"},
        {"type": "hide", "target": "master-mark"},
        {"type": "hide", "target": "master-rev-mark"},
    ])


def mark_instance(p, prefix, x, y, m, reversed_=False):
    sym = "MorrowMarkReversed" if reversed_ else "MorrowMark"
    p.apply(sun_ops(prefix, x, y, m) + [
        {"type": "symbol-instance", "symbol": sym, "name": f"{prefix}mark", "x": x, "y": y, "width": m, "height": m}])
    return [f"{prefix}sun", f"{prefix}mark"]


def lockup(p, prefix, kind, x, y, m, word_size, tag_size, ink="@roast", reversed_=False, group=True):
    """Build a lockup whose top-left is (x, y). Returns (layer names, (width, height))."""
    names = mark_instance(p, prefix, 0, 0, m, reversed_)
    p.apply([
        {"type": "text", "name": f"{prefix}word", "text": "Morrow", "font": "heading", "size": word_size, "color": ink},
        {"type": "text", "name": f"{prefix}tag", "text": tracked("COFFEE ROASTERS"), "font": "work-600",
         "size": tag_size, "color": ink},
    ])
    wb, tb = bounds(p, f"{prefix}word"), bounds(p, f"{prefix}tag")
    if kind == "horizontal":
        gap = round(m * 0.16)
        tgap = round(word_size * 0.1)
        block_h = wb[3] + tgap + tb[3]
        tx, ty = x + m + gap, y + (m - block_h) // 2
        moves = [(f"{prefix}word", tx - round(word_size * 0.025), ty), (f"{prefix}tag", tx, ty + wb[3] + tgap)]
        size = (m + gap + max(wb[2], tb[2]), m)
        mx, my = x, y
    else:
        width = max(m, wb[2], tb[2])
        gap1, gap2 = round(m * 0.1), round(word_size * 0.12)
        mx, my = x + (width - m) // 2, y
        moves = [(f"{prefix}word", x + (width - wb[2]) // 2, y + m + gap1),
                 (f"{prefix}tag", x + (width - tb[2]) // 2, y + m + gap1 + wb[3] + gap2)]
        size = (width, m + gap1 + wb[3] + gap2 + tb[3])
    ops = [{"type": "move", "target": n, "x": mx, "y": my} for n in names]
    ops += [{"type": "move", "target": n, "x": a, "y": b} for n, a, b in moves]
    p.apply(ops)
    names += [f"{prefix}word", f"{prefix}tag"]
    if group:
        p.apply({"type": "group", "name": f"{prefix}lockup", "targets": names})
    return names, size


def measure_lockup(kind, m, word_size, tag_size):
    """Lay a lockup out once in a scratch document to learn its size (for centring)."""
    scratch = Project(2400, 2400)
    brand_doc(scratch)
    add_masters(scratch)
    _, size = lockup(scratch, "z-", kind, 0, 0, m, word_size, tag_size, group=False)
    return size


def build_logo():
    p = Project.sized("logo-horizontal", background="transparent")  # 1600 × 600
    brand_doc(p)
    add_masters(p)
    hw, hh = measure_lockup("horizontal", 380, 236, 42)
    lockup(p, "h-", "horizontal", (1600 - hw) // 2, (600 - hh) // 2, 380, 236, 42)
    sw, sh = measure_lockup("stacked", 520, 220, 42)
    lockup(p, "s-", "stacked", (1000 - sw) // 2, (1200 - sh) // 2, 520, 220, 42)
    ids = {n: p.inspect(n)["id"] for n in ("h-lockup", "s-lockup")}
    p.apply([
        # Artboards created from the named logo sizes, each showing only its own lockup.
        {"type": "artboard", "name": "horizontal", "preset": "logo-horizontal", "targets": [ids["h-lockup"]]},
        {"type": "artboard", "name": "stacked", "preset": "logo-stacked", "targets": [ids["s-lockup"]]},
        # Freeze the brand colours as a check suite (palette regression rule).
        {"type": "suite-set", "name": "brand-colors", "suite": {"rules": [
            {"id": "logo-uses-only-brand-colours", "kind": "palette", "palette": "morrow",
             "tolerance": 8, "max_fraction": 0.03, "alpha_min": 16},
        ]}},
        {"type": "suite-set", "name": "brand-colors-frozen", "suite": {"rules": [
            {"id": "logo-pixels-frozen", "kind": "palette",
             "colors": [hexof(p, "@roast"), hexof(p, "@ember")],
             "tolerance": 8, "max_fraction": 0.03, "alpha_min": 16},
        ]}},
    ])
    p.save(WORK / "logo.vixl")
    for board in ("horizontal", "stacked"):
        p.export(OUT / "logo" / f"morrow-logo-{board}.png", artboard=board)  # transparent PNG
        p.export(OUT / "logo" / f"morrow-logo-{board}.svg", artboard=board, svg_policy="strict")
    return p


# ---------------------------------------------------------------------------
# 5. Business card front/back with bleed → CMYK PDF.
# ---------------------------------------------------------------------------

CARD_BAND = [(0, 6), (16, 8), (36, 10), (60, 12)]  # sunrise stripes (offset from top of band, height)


def build_card_front():
    p = Project.sized("business-card", bleed=True, background="#F3E9DA")  # 1126 × 676 incl. 38px bleed
    brand_doc(p)
    add_masters(p)
    p.apply([{"type": "solid", "name": "paper", "color": "@crema"}])
    g = {k: v["position"] for k, v in p.state["guides"].items()}
    # Sunrise stripes running off the bottom bleed edge.
    base = 548
    ops = []
    for i, (dy, h) in enumerate(CARD_BAND):
        ops.append({"type": "shape", "shape": "rectangle", "name": f"stripe{i}", "x": 0, "y": base + dy + i * 6,
                    "width": 1126, "height": h, "fill": "@ember"})
    ops[-1]["height"] = 676 - ops[-1]["y"]  # the last stripe runs into the bleed
    p.apply(ops)
    # Mark + contact block inside the safe area.
    m = 250
    mark_instance(p, "card-", g["safe-left"], g["safe-top"] + 8, m)
    p.apply([
        {"type": "text", "name": "name", "text": "Ada Okafor", "font": "heading", "size": 62, "color": "@roast"},
        {"type": "text", "name": "role", "text": tracked("HEAD ROASTER"), "font": "work-600", "size": 28,
         "color": "@ember-deep"},
        {"type": "text", "name": "contact",
         "text": "ada@morrow.coffee\n+1 (503) 555-0142\n1120 SE Alder St · Portland, OR",
         "font": "body", "size": 31, "spacing": 14, "color": "@roast"},
        {"type": "shape", "shape": "rectangle", "name": "divider", "width": 4, "height": 268, "fill": "@oat"},
    ])
    tx = g["safe-left"] + m + 72
    nb, rb = bounds(p, "name"), bounds(p, "role")
    p.apply([
        {"type": "move", "target": "divider", "x": tx - 38, "y": g["safe-top"] + 4},
        {"type": "move", "target": "name", "x": tx, "y": g["safe-top"]},
        {"type": "move", "target": "role", "x": tx + 2, "y": g["safe-top"] + nb[3] + 22},
        {"type": "move", "target": "contact", "x": tx + 2, "y": g["safe-top"] + nb[3] + 22 + rb[3] + 40},
        {"type": "text", "name": "url", "text": tracked("MORROW.COFFEE"), "font": "work-600", "size": 27,
         "color": "@roast"},
    ])
    ub = bounds(p, "url")
    p.apply({"type": "move", "target": "url", "x": g["safe-right"] - ub[2], "y": base - ub[3] - 26})
    p.save(WORK / "card-front.vixl")
    return p


def build_card_back(session):
    p = Project.sized("business-card", bleed=True, background="#3B2418")
    brand_doc(p)
    add_masters(p)
    p.apply({"type": "solid", "name": "paper", "color": "@roast"})
    p.save(WORK / "card-back.vixl")
    w, h = 1126, 676
    lw_, lh_ = measure_lockup("stacked", 250, 104, 26)
    x0, y0 = (w - lw_) // 2, (h - lh_) // 2
    keep_out = (x0 - 70, y0 - 50, x0 + lw_ + 70, y0 + lh_ + 50)
    # Scatter the saved pen-tool bean (shape-place) as a quiet pattern around the lockup.
    import random
    rnd = random.Random(7)
    ops, k = [], 0
    for row in range(6):
        for col in range(9):
            x = col * 136 - 30 + (68 if row % 2 else 0) + rnd.randint(-10, 10)
            y = row * 128 - 34 + rnd.randint(-10, 10)
            angle = rnd.choice([-35, -20, 15, 30, 50])
            if x > w - 30:
                continue
            if x + 60 > keep_out[0] and x < keep_out[2] and y + 70 > keep_out[1] and y < keep_out[3]:
                continue
            ops.append({"type": "shape-place", "resource": "morrow-bean", "name": f"bean-{k}", "x": x, "y": y,
                        "width": 44, "height": 60, "fill": "#4A3022"})
            ops.append({"type": "rotate", "target": f"bean-{k}", "value": angle})
            k += 1
    ops.append({"type": "group", "name": "bean-pattern", "targets": [f"bean-{i}" for i in range(k)]})
    REPORT["card-back-shape-place"] = session.apply(ops, document="card-back.vixl")["operations"]
    with session.project(document="card-back.vixl", write=True) as live:
        lockup(live, "b-", "stacked", x0, y0, 250, 104, 26, ink="@crema", reversed_=True)
    return Project.load(WORK / "card-back.vixl")


# ---------------------------------------------------------------------------
# 6. App icon, icon set and favicon.
# ---------------------------------------------------------------------------

def build_app_icon():
    p = Project.sized("app-icon", background="#3B2418")  # 1024 × 1024
    brand_doc(p, fonts=False)
    p.apply([
        {"type": "gradient", "name": "bg", "direction": "radial",
         "stops": [{"offset": 0, "color": "mix(@roast, @ember, 18%)"}, {"offset": 1, "color": "@roast"}]},
    ])
    m = 700
    p.apply(sun_ops("", (1024 - m) // 2, (1024 - m) // 2 - 10, m)
            + mark_ops("", (1024 - m) // 2, (1024 - m) // 2 - 10, m, fill="@crema"))
    p.save(WORK / "app-icon.vixl")
    p.export(OUT / "icons" / "app-icon-1024.png")
    # Full web/apple/android/windows icon set + favicon.ico + site.webmanifest.
    REPORT["export-icons"] = export_icons(p, OUT / "icons" / "set", icon_set="all")
    return p


def build_favicon():
    """Small-size mark: the bean alone, larger and without the sunrise bands."""
    p = Project.sized("favicon", background="transparent")  # 512 × 512
    brand_doc(p, fonts=False)
    p.apply([
        {"type": "shape", "shape": "rounded-rectangle", "name": "tile", "x": 0, "y": 0, "width": 512,
         "height": 512, "radius": 112, "fill": "@roast"},
        {"type": "pen", "name": "bean", "width": 220, "height": 300, "closed": True, "fill": "@ember",
         "stroke": "transparent", "stroke_width": 0, "nodes": BEAN_NODES},
        {"type": "shape", "shape": "path", "name": "crease", "width": 220, "height": 300, "fill": "@ember",
         "path": CREASE.replace("L118 312", "L124 312").replace("C162 248", "C168 248")},
        {"type": "pathfinder", "name": "bean-halves", "targets": ["bean", "crease"], "mode": "subtract"},
        {"type": "resize", "target": "bean-halves", "width": 250, "height": 341},
        {"type": "rotate", "target": "bean-halves", "value": -BEAN_TILT},
    ])
    b = bounds(p, "bean-halves")
    p.apply({"type": "move", "target": "bean-halves", "x": (512 - b[2]) // 2, "y": (512 - b[3]) // 2})
    p.save(WORK / "favicon.vixl")
    p.export(OUT / "icons" / "favicon.ico", icon_sizes=[16, 32, 48, 64])
    p.export(OUT / "icons" / "favicon-512.png")
    return p


# ---------------------------------------------------------------------------
# 7. Brand board: logo, palette chips with hex labels, tonal scale, type specimen,
#    applications. Exported as PNG and standalone HTML.
# ---------------------------------------------------------------------------

def build_board(previews):
    W, H, M = 1920, 1280, 80
    p = Project(W, H, background="#F3E9DA")
    brand_doc(p, extra_fonts=True)
    add_masters(p)
    p.apply([
        {"type": "solid", "name": "paper", "color": "@crema"},
        {"type": "grid", "name": "cols", "columns": 12, "margin": M, "gutter": 24},
        {"type": "text", "name": "hdr-left", "text": tracked("MORROW COFFEE ROASTERS"), "font": "work-600",
         "size": 20, "color": "@roast", "x": M, "y": 52},
        {"type": "text", "name": "hdr-right", "text": tracked("BRAND IDENTITY · V1.0 · 2026"), "font": "work-600",
         "size": 20, "color": "@ember-deep"},
        {"type": "constrain", "target": "hdr-right", "constraints": {"right": "canvas.right-80", "top": "hdr-left.top"}},
        {"type": "shape", "shape": "rectangle", "name": "hdr-rule", "x": M, "y": 96, "width": W - 2 * M, "height": 2,
         "fill": "@oat"},
    ])

    def label(name, text, x, y, color="@ember-deep"):
        p.apply({"type": "text", "name": name, "text": tracked(text), "font": "work-600", "size": 16,
                 "color": color, "x": x, "y": y})

    # --- Row 1: logo on light and reversed -----------------------------------
    top, row_h = 136, 400
    lw = 1100
    p.apply([
        {"type": "shape", "shape": "rounded-rectangle", "name": "panel-light", "x": M, "y": top, "width": lw,
         "height": row_h, "radius": 20, "fill": "mix(@crema, white, 45%)", "stroke": "@oat", "stroke_width": 2},
        {"type": "shape", "shape": "rounded-rectangle", "name": "panel-dark", "x": M + lw + 24, "y": top,
         "width": W - 2 * M - lw - 24, "height": row_h, "radius": 20, "fill": "@roast"},
    ])
    label("lbl-primary", "01  PRIMARY LOCKUP", M + 32, top + 28)
    label("lbl-reversed", "02  STACKED · REVERSED", M + lw + 24 + 32, top + 28, color="@ember-glow")
    hw, hh = measure_lockup("horizontal", 250, 156, 28)
    lockup(p, "bh-", "horizontal", M + (lw - hw) // 2, top + (row_h - hh) // 2 + 14, 250, 156, 28)
    dw = W - 2 * M - lw - 24
    sw, sh = measure_lockup("stacked", 196, 88, 18)
    lockup(p, "bs-", "stacked", M + lw + 24 + (dw - sw) // 2, top + (row_h - sh) // 2 + 22, 196, 88, 18,
           ink="@crema", reversed_=True)

    # --- Row 2: palette chips with hex labels + generated ember scale -------
    py = top + row_h + 76
    label("lbl-palette", "03  COLOUR  —  PALETTE-DEFINE “MORROW”", M, py - 34)
    n, gap = len(BRAND_ROLES), 24
    cw = (W - 2 * M - (n - 1) * gap) // n
    ch = 168
    roles = {"roast": "PRIMARY", "crema": "BACKGROUND", "ember": "ACCENT", "ember-deep": "ACCENT TEXT",
             "kettle": "SECONDARY", "oat": "NEUTRAL"}
    ops = []
    for i, key in enumerate(BRAND_ROLES):
        x = M + i * (cw + gap)
        ink = f"readable(@{key}, @espresso, @crema)"
        ops += [
            {"type": "shape", "shape": "rounded-rectangle", "name": f"chip-{key}", "x": x, "y": py, "width": cw,
             "height": ch, "radius": 14, "fill": f"@{key}",
             **({"stroke": "@oat", "stroke_width": 2} if key == "crema" else {})},
            {"type": "text", "name": f"chip-{key}-role", "text": tracked(roles[key]), "font": "work-600",
             "size": 13, "color": ink, "x": x + 22, "y": py + 20},
            {"type": "text", "name": f"chip-{key}-name", "text": BRAND_NAMES[key], "font": "heading", "size": 32,
             "color": ink, "x": x + 22, "y": py + ch - 84},
            {"type": "text", "name": f"chip-{key}-hex", "text": hexof(p, "@" + key), "font": "mono", "size": 19,
             "color": ink, "x": x + 22, "y": py + ch - 40},
        ]
    p.apply(ops)
    # Generated tonal scale (palette-generate scheme=scale) as a continuous strip.
    sy = py + ch + 20
    steps = ["50", "100", "200", "300", "400", "500", "600", "700", "800", "900", "950"]
    sw_ = (W - 2 * M) / len(steps)
    ops = []
    for i, s in enumerate(steps):
        x0, x1 = round(M + i * sw_), round(M + (i + 1) * sw_)
        ops += [
            {"type": "solid", "name": f"scale-{s}", "x": x0, "y": sy, "width": x1 - x0, "height": 52,
             "color": f"@ember-{s}"},
            {"type": "text", "name": f"scale-{s}-lbl", "text": f"{s}  {hexof(p, '@ember-' + s)}", "font": "mono",
             "size": 14, "color": f"readable(@ember-{s}, @espresso, @crema)", "x": x0 + 12, "y": sy + 18},
        ]
    p.apply(ops)

    # --- Row 3: type specimen ------------------------------------------------
    ty = sy + 52 + 76
    label("lbl-type", "04  TYPE  —  FRAUNCES × WORK SANS", M, ty - 34)
    p.apply([
        {"type": "text", "name": "spec-aa", "text": "Aa", "font": "heading", "size": 200, "color": "@roast",
         "x": M - 8, "y": ty + 4},
        {"type": "text", "name": "spec-head-name", "text": "Fraunces Bold", "font": "heading", "size": 40,
         "color": "@roast", "x": M + 270, "y": ty},
        {"type": "text", "name": "spec-head-use", "text": "Display, headlines, wordmark", "font": "fraunces-italic",
         "size": 26, "color": "@ember-deep", "x": M + 272, "y": ty + 56},
        {"type": "text", "name": "spec-body-name", "text": tracked("WORK SANS  400 / 600"), "font": "work-600",
         "size": 18, "color": "@roast", "x": M + 272, "y": ty + 118},
        {"type": "text", "name": "spec-body",
         "text": "Small-batch coffee, roasted at first light in Portland. We buy directly from "
                 "growers and publish the price we pay for every lot.",
         "font": "body", "size": 20, "spacing": 8, "color": "@roast", "x": M + 272, "y": ty + 150},
        {"type": "text-layout", "target": "spec-body", "width": 540, "height": 100},
    ])

    # --- Row 3 right: applications (rendered from the other documents) -------
    ax = 968
    label("lbl-apps", "05  APPLICATIONS", ax, ty - 34)
    cw2 = 280
    ops = []
    for i, side in enumerate(("card-front", "card-back")):
        ops += [
            {"type": "add", "path": str(previews[side]), "name": f"app-{side}"},
            # Trim the 38px bleed off the rendered card, then scale it down.
            {"type": "crop", "target": f"app-{side}", "x": 38, "y": 38, "width": 1050, "height": 600},
            {"type": "resize", "target": f"app-{side}", "width": cw2},
            {"type": "move", "target": f"app-{side}", "x": ax + i * (cw2 + 24), "y": ty + 6},
        ]
    ix = ax + 2 * (cw2 + 24) + 6
    ops += [
        {"type": "add", "path": str(previews["app-icon"]), "name": "app-icon"},
        {"type": "resize", "target": "app-icon", "width": 160},
        {"type": "move", "target": "app-icon", "x": ix, "y": ty + 6},
    ]
    fx = ix + 160 + 30
    for size, dy in ((64, 0), (32, 82), (16, 132)):
        ops += [
            {"type": "add", "path": str(previews["favicon"]), "name": f"app-favicon-{size}"},
            {"type": "resize", "target": f"app-favicon-{size}", "width": size},
            {"type": "move", "target": f"app-favicon-{size}", "x": fx + (64 - size) // 2, "y": ty + 6 + dy},
        ]
    ops.append({"type": "text", "name": "fav-caption", "text": "64 · 32 · 16", "font": "mono", "size": 13,
                "color": "@roast", "x": fx - 22, "y": ty + 166})
    p.apply(ops)
    # The app icon gets a rounded mask so it previews as it would on a home screen.
    ib = bounds(p, "app-icon")
    p.apply([
        {"type": "shape", "shape": "rounded-rectangle", "name": "icon-shape", "x": ib[0], "y": ib[1],
         "width": ib[2], "height": ib[3], "radius": 36, "fill": "@roast"},
        {"type": "reorder", "target": "icon-shape", "below": "app-icon"},
        {"type": "clip", "target": "app-icon", "base": "icon-shape"},
    ])
    for t in ("app-card-front", "app-card-back", "icon-shape"):
        p.apply({"type": "layer-style", "target": t, "name": "drop-shadow",
                 "settings": {"color": "alpha(@roast, 0.35)", "dx": 0, "dy": 10, "blur": 18}})
    p.apply([
        {"type": "text", "name": "cap-cards", "text": "Business card · 3.5 × 2 in · front / back (CMYK PDF)",
         "font": "body", "size": 15, "color": "@roast", "x": ax, "y": ty + 6 + 160 + 22},
        {"type": "text", "name": "cap-icon", "text": "App icon", "font": "body", "size": 15, "color": "@roast",
         "x": ix, "y": ty + 6 + 160 + 22},
    ])
    # Footer
    p.apply([
        {"type": "text", "name": "footer", "text": "Morrow Coffee Roasters brand identity — built headless with Vixl; every element is an editable layer.",
         "font": "fraunces-italic", "size": 20, "color": "@ember-deep"},
        {"type": "constrain", "target": "footer", "constraints": {"right": "canvas.right-80", "bottom": "canvas.bottom-40"}},
        # HTML export titles the page with the first text layer in stack order; the tracked
        # (thin-space) header would read as "M O R R O W …", so make the footer come first.
        {"type": "reorder", "target": "footer", "above": "paper"},
    ])
    p.save(WORK / "brand-board.vixl")
    return p


# ---------------------------------------------------------------------------
# 8. QA: palette-check suites on the logo, design checks, print checks.
# ---------------------------------------------------------------------------

def qa(session, docs):
    checks = {}
    for board in ("horizontal", "stacked"):
        for suite in ("brand-colors", "brand-colors-frozen"):
            checks[f"logo/{board}/{suite}"] = dispatch(
                session, "check", {"suite": suite, "artboard": board}, "logo.vixl")
    checks["mark/palette-check"] = dispatch(
        session, "palette-check", {"palette": "morrow", "tolerance": 8, "max_fraction": 0.03, "alpha_min": 16},
        "mark.vixl")
    checks["card-front/palette-check"] = dispatch(
        session, "palette-check", {"palette": "morrow", "tolerance": 8, "max_fraction": 0.03}, "card-front.vixl")
    design = {}
    for name, proj in docs.items():
        if name == "brand-board" and os.environ.get("QUICK"):
            continue  # ~3 min: contrast re-renders the whole board twice per text layer
        if name == "logo":
            for board in ("horizontal", "stacked"):
                design[f"logo@{board}"] = proj.check(artboard=board)
            continue
        design[name] = proj.check()
    for name in ("card-front", "card-back"):
        design[name + "/print"] = docs[name].check(checks=["print"])
    save_json("palette-checks.json", checks)
    save_json("design-checks.json", design)
    summary = {k: (v.get("status") or v.get("passed")) for k, v in checks.items()}
    summary.update({f"check:{k}": v.get("passed") for k, v in design.items()})
    return summary


def main():
    session = Session(workspace=WORK)
    docs = {}
    docs["mark"] = build_mark(session)
    docs["logo"] = build_logo()
    docs["card-front"] = build_card_front()
    docs["card-back"] = build_card_back(session)
    for side in ("card-front", "card-back"):
        docs[side].export(OUT / "card" / f"{side}.png")
        docs[side].export(OUT / "card" / f"{side}-cmyk.pdf", color_space="cmyk", ink_limit=300)
        # RGB soft proof through the same GCR separation, to preview the press result on screen.
        docs[side].export(OUT / "card" / f"{side}-softproof.png", proof=True, ink_limit=300)
    docs["app-icon"] = build_app_icon()
    docs["favicon"] = build_favicon()
    previews = {"card-front": OUT / "card" / "card-front.png", "card-back": OUT / "card" / "card-back.png",
                "app-icon": OUT / "icons" / "app-icon-1024.png", "favicon": OUT / "icons" / "favicon-512.png"}
    docs["brand-board"] = build_board(previews)
    docs["brand-board"].export(OUT / "board" / "brand-board.png")
    docs["brand-board"].export(OUT / "board" / "brand-board.html")
    # CLI steps: strict print + colour-vision check on the card, and a deuteranopia
    # simulation of the brand board (vixl export --simulate).
    REPORT["cli-card-check"] = json.loads(run_cli("--json", "-p", "card-front.vixl", "check", "--checks", "print",
                                                  "color_vision", "--strict"))
    run_cli("-p", "brand-board.vixl", "export", str(OUT / "board" / "brand-board-deuteranopia.png"),
            "--simulate", "deuteranopia", "--scale", "0.5")
    REPORT["qa"] = qa(session, docs)
    save_json("build-report.json", REPORT)
    print(json.dumps(REPORT["qa"], indent=2))


if __name__ == "__main__":
    main()
