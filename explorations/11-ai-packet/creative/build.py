"""AI packet, creative designs: "AI, demystified" poster (rolled), "5 AI myths, busted" carousel,
"AI Explorers Club" logo + logo package, and a sticker/badge sheet with looks.

Run from the repo root:   python explorations/11-ai-packet/creative/build.py [piece ...]
Pieces: poster, carousel, logo, stickers (default: all). The carousel and stickers link the mascot
from ../illustrations/mascot.vixl, so build the illustrations first.
"""

import json
import math
import os
import shutil
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
PACKET = HERE.parent
import tempfile  # noqa: E402

CACHE = Path(tempfile.gettempdir()) / "vixl-ai-packet"
CACHE.mkdir(parents=True, exist_ok=True)
os.environ["VIXL_NO_UPDATE"] = "1"

from vixl import Project  # noqa: E402
from vixl.typefaces import install_font, pair_fonts, roll_document  # noqa: E402

PAL = {
    "night": "#0d1030",
    "night2": "#1b1f4f",
    "teal": "#2ee6c5",
    "teal-deep": "#0f766e",
    "coral": "#ff6b5b",
    "coral-deep": "#c2362a",
    "sun": "#ffd166",
    "lilac": "#a78bfa",
    "cream": "#fff6e5",
    "ink": "#141633",
    "muted": "#4a4f7a",
}
TIMINGS = {}


def swatches():
    return [{"type": "swatch", "name": k, "color": v} for k, v in PAL.items()]


def text(name, s, x, y, size, color="@ink", font="body", **kw):
    return {"type": "text", "name": name, "text": s, "x": x, "y": y, "size": size, "color": color, "font": font, **kw}


def report(stem, rep):
    fixes = [i for i in rep["issues"] if i.get("action") == "fix"]
    reviews = [i for i in rep["issues"] if i.get("action") == "review"]
    print(f"  check {stem}: {len(fixes)} fix, {len(reviews)} review")
    for i in fixes + reviews:
        print("    -", i.get("action"), i.get("check"), i.get("message"))


def timed(label):
    class T:
        def __enter__(self):
            self.t = time.perf_counter()

        def __exit__(self, *exc):
            TIMINGS[label] = round(time.perf_counter() - self.t, 2)
            print(f"  {label}: {TIMINGS[label]} s")

    return T()


# ----------------------------------------------------------------------------------------------
# 6. "5 AI myths, busted": an instagram-portrait carousel, one page per slide

MYTHS = [
    ("AI understands things the way people do.",
     "Today's AI is a pattern-finder. It learned from huge amounts of examples, so it can sound sure of itself "
     "without understanding, or being right.",
     "Treat answers as a smart first draft."),
    ("If an AI says it, it must be true.",
     "AI can confidently make things up. People call this a hallucination. It happens most with facts, "
     "numbers, quotes and sources.",
     "Check anything important with a trusted source."),
    ("You have to code to use AI.",
     "Plain language works. Say what you want, who it's for and what good looks like, then refine it together.",
     "Try: “Explain this like I'm 12.”"),
    ("AI is neutral and fair.",
     "AI learns from human-made data, and that data carries our gaps and biases. Some outputs reflect them.",
     "Ask: who might this leave out?"),
    ("AI will do all the thinking for us.",
     "AI is a tool. It speeds up drafts, ideas and practice. Judgment, values and taste stay with you.",
     "Use it to think more, not less."),
]


def build_carousel():
    W, H = 1080, 1350
    p = Project.new("instagram-portrait", background=PAL["cream"], seed=5, purpose="social",
                    workspace=str(PACKET))
    pair_fonts(p, "bricolage-figtree")
    install_font(p, "Space Mono", 700)
    install_font(p, "Figtree", 700)
    ops = swatches()
    # master: shared frame, header strip, footer with page counter and the mascot (a live link)
    ops.append({"type": "master", "action": "add", "name": "myth", "background": PAL["cream"]})
    master_ops = [
        {"type": "shape", "shape": "rectangle", "name": "band", "x": 0, "y": 0, "width": W, "height": 150,
         "fill": "@night"},
        text("series", "5 AI MYTHS, BUSTED", 72, 66, 34, color="@sun", font="space-mono-700"),
        text("counter", "${page} / ${pages}", 1008, 66, 34, color="@cream", font="space-mono-700", align="right"),
        {"type": "shape", "shape": "rectangle", "name": "foot-rule", "x": 72, "y": 1196, "width": 936, "height": 4,
         "fill": "@night"},
        text("handle", "AI EXPLORERS CLUB", 72, 1226, 34, color="@ink", font="space-mono-700"),
        text("swipe", "swipe →", 1008, 1222, 36, color="@coral-deep", font="figtree-700", align="right"),
    ]
    ops += master_ops  # layers added right after `master add` belong to that master
    ops.append({"type": "constrain", "target": "counter", "constraints": {"right": "canvas.right-72"}})
    ops.append({"type": "constrain", "target": "swipe", "constraints": {"right": "canvas.right-72"}})
    for i, (myth, truth, tip) in enumerate(MYTHS, start=1):
        pg = f"myth-{i}"
        ops.append({"type": "page", "action": "add", "name": pg, "master": "myth",
                    "notes": f"Myth {i}: {myth}"})
        y = 200
        ops.append(text("myth-label", f"MYTH #{i}", 72, y, 34, color="@coral-deep", font="space-mono-700", page=pg))
        ops.append({"type": "text", "name": "title", "text": f"“{myth}”", "x": 72, "y": y + 56, "size": 84,
                    "color": "@ink", "font": "heading", "line_height": 1.05, "page": pg})
        ops.append({"type": "text-layout", "target": "title", "width": 936, "page": pg})
        p.apply(ops)
        ops = []
        title_bottom = _bottom(p, "title", pg)
        # the strike: one hand-drawn line through the middle of each title line, roughened with irregular
        tb = _bounds(p, "title", pg)
        lines = max(1, round(tb[3] / (84 * 1.05)))
        pitch = tb[3] / lines
        strikes = []
        ink = _line_extents(p, pg, tb, lines)
        for k in range(lines):
            cy = tb[1] + pitch * (k + 0.55)
            x0, x1 = ink[k]
            ops.append({"type": "pen", "name": f"strike-{k}", "points": [[x0 - 12, cy + 6], [(x0 + x1) / 2, cy - 2],
                                                                        [x1 + 12, cy - 6]],
                        "stroke": "@coral", "stroke_width": 12, "line_cap": "round", "page": pg})
            strikes.append(f"strike-{k}")
        ops.append({"type": "irregular", "targets": strikes, "seed": 10 + i, "strength": "natural", "page": pg})
        ops.append({"type": "group", "name": "strike", "targets": strikes, "page": pg})
        ops.append({"type": "layer-intent", "target": "strike", "role": "decoration", "allow_overlap": ["title"], "page": pg})
        # BUSTED stamp
        sy = title_bottom + 50
        ops.append({"type": "shape", "shape": "stamp", "name": "stamp", "x": 72, "y": sy, "width": 330, "height": 112,
                    "fill": "@coral-deep", "page": pg})
        ops.append({"type": "text", "name": "stamp-text", "text": "BUSTED", "within": "stamp", "size": 52,
                    "font": "heading", "color": "@cream", "page": pg})
        ops.append({"type": "group", "name": "busted", "targets": ["stamp", "stamp-text"], "page": pg})
        ops.append({"type": "rotate", "target": "busted", "value": -6, "page": pg})
        # (the look goes on the stamp, not the group: a hard-shadow on a group holding text makes the
        # contrast check report that text at 1.00:1, see NOTES.md)
        ops.append({"type": "look", "target": "stamp", "look": "hard-shadow", "color": "@ink", "amount": 0.3,
                    "page": pg})
        ty = sy + 170
        ops.append(text("truth-label", "THE TRUTH", 72, ty, 34, color="@teal-deep", font="space-mono-700", page=pg))
        ops.append(text("truth", truth, 72, ty + 46, 42, color="@ink", page=pg))
        ops.append({"type": "text-layout", "target": "truth", "width": 930, "page": pg})
        p.apply(ops)
        ops = []
        # The CTA hangs off the body with constraints (box top = truth bottom + 44, text inside the box), so it
        # reflows if the copy changes; only the box height is measured from the wrapped tip.
        ops.append(text("tip", "\u2192 " + tip, 104, 0, 38, color="@sun", font="figtree-700", page=pg))
        ops.append({"type": "text-layout", "target": "tip", "width": 560, "page": pg})
        p.apply(ops)
        ops = []
        tip_h = round(_bounds(p, "tip", pg)[3]) + 64
        ops.append({"type": "shape", "shape": "rectangle", "name": "tip-box", "x": 72, "y": 0, "width": 640,
                    "height": tip_h, "fill": "@night", "page": pg})
        ops.append({"type": "reorder", "target": "tip-box", "below": "tip", "page": pg})
        ops.append({"type": "constrain", "target": "tip-box", "page": pg,
                    "constraints": {"left": "canvas.left+72", "top": "truth.bottom+44"}})
        ops.append({"type": "constrain", "target": "tip", "page": pg,
                    "constraints": {"left": "tip-box.left+32", "top": "tip-box.top+30"}})
        ops.append({"type": "link", "name": "byte", "source": "illustrations/mascot.vixl", "x": 740, "y": 0,
                    "width": 300, "height": 300, "fit": "fit", "page": pg})
        ops.append({"type": "constrain", "target": "byte", "page": pg,
                    "constraints": {"right": "canvas.right-60", "top": "tip-box.top-40"}})
        ops.append({"type": "look", "target": "tip-box", "look": "hard-shadow", "color": "@teal", "amount": 0.35,
                    "page": pg})
    p.apply(ops)
    p.apply([{"type": "page", "action": "remove", "page": 1}]) if _has_blank_first_page(p) else None
    with timed("carousel check"):
        # checks=["deck"] runs only the deck check (no legibility/overlap/contrast), so run both, page by page
        rep = p.check(checks=["deck"])
        report("carousel deck", rep)
        for i in range(1, len(MYTHS) + 1):
            p.apply([{"type": "page", "action": "select", "page": f"myth-{i}"}])
            report(f"carousel myth-{i}", p.check())
    with timed("carousel save+export"):
        p.save(str(HERE / "myths-carousel.vixl"), overwrite=True)
        # Python export has no pages="all" (the CLI loops for you); write one PNG per page plus a sheet
        for i in range(1, len(MYTHS) + 1):
            p.export(str(HERE / f"myths-carousel-{i}.png"), page=f"myth-{i}", overwrite=True)
        # The built-in contact sheet (export page="all") re-wraps body text at thumbnail size and clips the
        # last line ("reflect them." on myth 4, see NOTES.md), so the sheet is assembled from the page PNGs.
        from PIL import Image
        thumbs = [Image.open(HERE / f"myths-carousel-{i}.png").convert("RGB").resize((400, 500), Image.LANCZOS)
                  for i in range(1, len(MYTHS) + 1)]
        sheet = Image.new("RGB", (5 * 400 + 6 * 16, 500 + 32), "#e4e1ea")
        for i, t in enumerate(thumbs):
            sheet.paste(t, (16 + i * 416, 16))
        sheet.save(HERE / "myths-carousel-sheet.jpg", quality=85)
        p.export(str(HERE / "myths-carousel.pdf"), overwrite=True)
    return p


def _line_extents(p, page, box, lines):
    """Left and right ink edge of each line of a wrapped text block, measured on the rendered page."""
    import numpy as np

    img = np.asarray(p.render(page=page).convert("RGB")).astype(int)
    x, y, w, h = (round(v) for v in box)
    out = []
    for k in range(lines):
        band = img[y + k * h // lines: y + (k + 1) * h // lines, x: x + w]
        dark = (band.sum(axis=2) < 200).any(axis=0).nonzero()[0]
        out.append((int(x + dark.min()), int(x + dark.max())) if len(dark) else (x, x + w))
    return out


def _bounds(p, name, page):
    return _inspect_on(p, name, page)["canvas_bounds"]


def _bottom(p, name, page):
    info = p.inspect(name) if page is None else _inspect_on(p, name, page)
    b = info["canvas_bounds"]
    return round(b[1] + b[3])


def _inspect_on(p, name, page):
    p.apply([{"type": "page", "action": "select", "page": page}])
    return p.inspect(name)


def _has_blank_first_page(p):
    pages = p.inspect().get("pages") or []
    return bool(pages) and pages[0].get("layers", 1) == 0


# ----------------------------------------------------------------------------------------------
# 5. "AI, demystified" poster: roll a direction, keep the best seed, then finish it by hand

POSTER_SLOTS = {
    "title": "AI, demystified",
    "subtitle": "What it is, how it learns, and how to use it well.",
    "body": "AI finds patterns in lots of examples and uses them to make useful guesses. It is a tool: powerful, "
            "imperfect, and best with a curious human in the loop.",
    "label": "A friendly field guide",
    "cta": "Start exploring",
}
# Seeds compared (see NOTES.md): 11-16 at medium/high, 21-24 at high with mode=dark. Seed 23 (acid-violet,
# Unbounded + Manrope, wide-statement, avant-garde tier) was the strongest; headline=measured is locked
# because the rolled "large" headline broke "demystified" mid-word on every seed tried.
POSTER_SEED = 23


def build_poster():
    p = Project.new("poster-11x17", seed=POSTER_SEED, variety="high", purpose="poster", workspace=str(PACKET))
    with timed("poster roll+apply"):
        r = roll_document(p, seed=POSTER_SEED, purpose="poster", mood="playful", variety="high",
                          locks={"mode": "dark", "headline": "measured"}, apply=True, slots=POSTER_SLOTS)
    d = r["direction"]
    print(f"  rolled: {d['layout']} / {d['pairing']} / {d['palette']} / {d['style']} / tier {r.get('tier')}")
    W, H = p.state["canvas"]["width"], p.state["canvas"]["height"]
    # (no packet swatches here: they would redefine the rolled @ink/@accent roles the layout uses)
    ops = []
    # the rolled motif is a small dash that pokes out of the frame's top-right corner; drop it
    ops.append({"type": "remove", "target": "direction-motif"})
    # the rolled block sits low with ~1000 px of air above it; lift the copy so the art gets the lower half
    for nm in ("label", "headline", "subtitle", "body", "cta-button", "cta"):
        ops.append({"type": "move", "target": nm, "relative": True, "y": -620})
    # a constellation network in the empty lower half, in the rolled roles (@accent, @ink)
    import random
    rnd = random.Random(4)
    cols = [(330, [4000, 4350]), (800, [3800, 4150, 4500]), (1270, [3950, 4300, 4650]), (1740, [4150, 4480])]
    pts = [[(x, y) for y in ys] for x, ys in cols]
    lines, nodes = [], []
    for li in range(len(pts) - 1):
        for a in pts[li]:
            for b in pts[li + 1]:
                nm = f"net-w{len(lines)}"
                w = rnd.random()
                ops.append(path_line(nm, a, b, stroke="@accent" if w > 0.55 else "@ink",
                                     stroke_width=round(8 + w * 14), opacity=round(0.35 + 0.5 * w, 2)))
                lines.append(nm)
    for li, col in enumerate(pts):
        for k, (x, y) in enumerate(col):
            nm = f"net-n{li}{k}"
            ops.append({"type": "shape", "shape": "ellipse", "name": nm, "x": x - 60, "y": y - 60, "width": 120,
                        "height": 120, "fill": "@background", "stroke": "@accent", "stroke_width": 22})
            nodes.append(nm)
    ops.append({"type": "group", "name": "net-lines", "targets": lines})
    ops.append({"type": "group", "name": "net-nodes", "targets": nodes})
    ops.append({"type": "look", "targets": nodes, "look": "glow", "color": "@accent", "amount": 0.45})
    ops.append({"type": "group", "name": "network", "targets": ["net-lines", "net-nodes"]})
    ops.append({"type": "layer-intent", "target": "network", "role": "decoration"})
    # Byte, linked live from the illustration source
    ops.append({"type": "link", "name": "byte", "source": "illustrations/mascot.vixl", "x": 1720, "y": 3420,
                "width": 1400, "height": 1400, "fit": "fit"})
    ops.append(text("credit", "AI EXPLORERS CLUB \u00b7 FIELD GUIDE NO. 1", 231, 4760, 64, color="@accent",
                    font="body"))
    p.apply(ops)
    with timed("poster check"):
        rep = p.check()
    report("poster", rep)
    with timed("poster save+export"):
        p.save(str(HERE / "poster-ai-demystified.vixl"), overwrite=True)
        p.export(str(HERE / "poster-ai-demystified.png"), scale=0.4, overwrite=True)
        p.export(str(HERE / "poster-ai-demystified.pdf"), overwrite=True)
    return p


def path_line(name, a, b, pad=16, **kw):
    x0, y0 = min(a[0], b[0]) - pad, min(a[1], b[1]) - pad
    x1, y1 = max(a[0], b[0]) + pad, max(a[1], b[1]) + pad
    return {"type": "shape", "shape": "path", "name": name, "x": x0, "y": y0, "width": x1 - x0, "height": y1 - y0,
            "path": f"M{a[0] - x0} {a[1] - y0} L{b[0] - x0} {b[1] - y0}", "line_cap": "round", **kw}


# ----------------------------------------------------------------------------------------------
# 7. "AI Explorers Club" logo, then the logo-package workflow


def logo_mark_ops(cx, cy, r, prefix=""):
    """A compass badge built as one silhouette with holes (so the mono variants keep their detail):
    an outer rim, a gap, a teal orbit ring with dots, a gap, and an inner disc with the compass needle
    cut out of it."""
    P = prefix

    def disc(name, k, fill="@night"):
        return {"type": "shape", "shape": "ellipse", "name": P + name, "x": cx - r * k, "y": cy - r * k,
                "width": 2 * r * k, "height": 2 * r * k, "fill": fill}

    o = [disc("rim-outer", 1.0), disc("rim-cut", 0.9),
         {"type": "pathfinder", "name": P + "rim", "targets": [P + "rim-outer", P + "rim-cut"], "mode": "subtract"},
         disc("core-disc", 0.7),
         {"type": "shape", "shape": "star", "name": P + "needle-cut", "sides": 4, "inner_radius": 0.22,
          "x": cx - r * 0.6, "y": cy - r * 0.6, "width": r * 1.2, "height": r * 1.2, "fill": "@night"},
         {"type": "pathfinder", "name": P + "core", "targets": [P + "core-disc", P + "needle-cut"], "mode": "subtract"},
         {"type": "shape", "shape": "ring", "name": P + "orbit-ring", "x": cx - r * 0.84, "y": cy - r * 0.84,
          "width": r * 1.68, "height": r * 1.68, "thickness": 0.07, "fill": "@teal"},
         disc("orbit-dot", 0.075, "@sun"),
         {"type": "move", "target": P + "orbit-dot", "relative": True, "y": -r * 0.805},
         {"type": "radial-repeat", "target": P + "orbit-dot", "count": 8, "cx": cx, "cy": cy, "merge": True,
          "name": P + "orbit"},
         disc("hub", 0.11, "@coral")]
    return o


def build_logo():
    p = Project.new("logo-horizontal", seed=3, purpose="logo", workspace=str(PACKET))
    print("  canvas background:", p.state["canvas"].get("background"))
    pair_fonts(p, "bricolage-figtree")
    install_font(p, "Space Mono", 700)
    ops = swatches()
    ops += logo_mark_ops(300, 300, 220)
    ops.append({"type": "group", "name": "mark", "targets": ["rim", "core", "orbit-ring", "orbit", "hub"]})
    ops.append(text("name", "AI Explorers", 580, 168, 150, color="@night", font="heading", line_height=1.0))
    ops.append(text("tag", "C L U B", 588, 352, 64, color="@coral-deep", font="space-mono-700"))
    p.apply(ops)
    tb = p.inspect("tag")["canvas_bounds"]
    nb = p.inspect("name")["canvas_bounds"]
    x0 = round(tb[0] + tb[2] + 28)
    ops = [{"type": "shape", "shape": "rectangle", "name": "tag-rule", "x": x0, "y": round(tb[1] + tb[3] / 2 - 5),
            "width": round(nb[0] + nb[2] - x0), "height": 10, "fill": "@teal-deep"}]
    ops.append({"type": "group", "name": "wordmark", "targets": ["name", "tag", "tag-rule"]})
    p.apply(ops)
    with timed("logo check"):
        report("logo", p.check())
    p.save(str(HERE / "logo.vixl"), overwrite=True)
    p.export(str(HERE / "logo.png"), overwrite=True)
    p.export(str(HERE / "logo.svg"), svg_policy="strict", overwrite=True)

    out = HERE / "logo-package"
    if out.exists():
        shutil.rmtree(out)
    req = {"source": "creative/logo.vixl", "output": "creative/logo-package", "mark": "mark", "wordmark": "wordmark",
           "png_sizes": [256], "icons": "web", "social": True, "proof": False, "dark": PAL["night"]}
    reqf = CACHE / "logo-package-request.json"
    reqf.write_text(json.dumps(req))
    import subprocess
    with timed("logo-package workflow"):
        r = subprocess.run(["vixl", "workflow", "logo-package", "--request", str(reqf), "--workspace", str(PACKET)],
                           capture_output=True, text=True)
    if r.returncode:
        print("  logo-package failed:", r.stdout[-1500:], r.stderr[-1500:])
        return p
    res = json.loads(r.stdout)
    # keep the hand-off lean for this repo: the per-variant .vixl sources (each embeds the fonts, ~240 KB)
    # and the @3x PNGs are dropped; logo.vixl above is the editable master. (usage.html is off: with 42
    # embedded PNGs it was 2.8 MB, more than every other file in the package together.)
    shutil.rmtree(out / "source", ignore_errors=True)
    for f in (out / "png").glob("*@3x.png"):
        f.unlink()
    (CACHE / "logo-package-result.json").write_text(json.dumps(res, indent=1))
    rep = res.get("report") or res.get("result", {}).get("report") or {}
    print("  logo-package:", {k: v for k, v in res.items() if k in ("files", "written", "count")} or list(res)[:12])
    print("  report keys:", list(rep)[:12])
    return p


# ----------------------------------------------------------------------------------------------
# 8. Sticker sheet: six habits of a good AI explorer, each finished with a different look


def build_stickers():
    W, H = 1800, 1200
    p = Project(W, H, background="#e9e4f7", workspace=str(PACKET))
    pair_fonts(p, "bricolage-figtree")
    ops = swatches()
    ops.append({"type": "pattern-fill", "target": None} if False else {"type": "swatch", "name": "paper",
                                                                        "color": "#e9e4f7"})
    stickers = [
        # name, centre, shape spec, fill, text, text colour, look, look colour
        ("ask", (330, 330), {"shape": "speech-bubble", "width": 400, "height": 320}, "@coral",
         "Ask good\nquestions", "@night", "risograph", None),
        ("check", (900, 330), {"shape": "shield", "width": 330, "height": 380}, "@teal",
         "Check\nthe facts", "@night", "duotone", None),
        ("human", (1470, 330), {"shape": "heart", "width": 400, "height": 360}, "@lilac",
         "Human in\nthe loop", "@night", "watercolor", None),
        ("prompt", (330, 870), {"shape": "starburst", "width": 420, "height": 420}, "@sun",
         "Prompt\nlike a pro", "@night", "sketch", None),
        ("curious", (900, 870), {"shape": "seal", "width": 400, "height": 400}, "@sun",
         "Stay\ncurious", "@night", "gradient", None),
        ("kind", (1470, 870), {"shape": "squircle", "width": 380, "height": 340}, "@cream",
         "Be kind\nto people", "@coral-deep", "hand-made", None),
    ]
    for name, (cx, cy), spec, fill, label, tcol, look, lcol in stickers:
        w, h = spec["width"], spec["height"]
        ops.append({"type": "shape", "name": f"{name}-die", "x": cx - w / 2 - 22, "y": cy - h / 2 - 22,
                    "width": w + 44, "height": h + 44, "fill": "#ffffff", **{k: v for k, v in spec.items()
                                                                           if k not in ("width", "height")}})
        ops.append({"type": "shape", "name": f"{name}-face", "x": cx - w / 2, "y": cy - h / 2, "fill": fill, **spec})
        ops.append({"type": "text", "name": f"{name}-text", "text": label, "within": f"{name}-face", "size": 54,
                    "font": "heading", "color": tcol, "align": "center", "line_height": 1.0})
        look_op = {"type": "look", "target": f"{name}-face", "look": look, "amount": 0.6}
        if lcol:
            look_op["color"] = lcol
        ops.append(look_op)
        ops.append({"type": "group", "name": name, "targets": [f"{name}-die", f"{name}-face", f"{name}-text"]})
        ops.append({"type": "layer-style", "target": f"{name}-die", "name": "drop-shadow",
                    "settings": {"color": "#2a2f6e", "dx": 0, "dy": 10, "blur": 16, "opacity": 0.35}})
    for name, deg in (("ask", -6), ("check", 4), ("human", -3), ("prompt", 7), ("curious", -5), ("kind", 3)):
        ops.append({"type": "pivot", "target": name, "value": "center"})  # rotate about the centre (NOTES.md)
        ops.append({"type": "rotate", "target": name, "value": deg})
    p.apply(ops)
    # Byte joins the sheet as a sticker too: the linked illustration with a white die-cut stroke
    p.apply([{"type": "link", "name": "byte-sticker", "source": "illustrations/mascot.vixl", "x": 1180, "y": 520,
              "width": 300, "height": 300, "fit": "fit"},
             {"type": "layer-style", "target": "byte-sticker", "name": "stroke",
              "settings": {"color": "#ffffff", "width": 14}}])
    with timed("stickers check"):
        report("stickers", p.check())
    with timed("stickers save+export"):
        p.save(str(HERE / "sticker-sheet.vixl"), overwrite=True)
        p.export(str(HERE / "sticker-sheet.png"), overwrite=True)
    return p


def build_roll_sheet():
    """The seeds compared before picking the poster direction, rolled exactly as the CLI did
    (`vixl new poster-11x17 --seed S` then `vixl roll --apply --for poster --mood playful --seed S`)."""
    from PIL import Image, ImageDraw

    runs = [(s, "medium", {}) for s in (11, 12, 13)] + [(s, "high", {}) for s in (14, 15, 16)] + \
           [(s, "high", {"mode": "dark"}) for s in (21, 22, 23, 24)]
    cells = []
    for seed, variety, locks in runs:
        t = time.perf_counter()
        p = Project.new("poster-11x17", seed=seed, variety=variety, purpose="poster")
        r = roll_document(p, seed=seed, purpose="poster", mood="playful", variety=variety, locks=locks, apply=True,
                          slots=POSTER_SLOTS)
        img = p.render().convert("RGB")
        img.thumbnail((330, 510))
        d = r["direction"]
        label = f"{seed} {variety}{' dark' if locks else ''} | {r.get('tier')}\n{d['layout']} / {d['palette']}"
        cells.append((img, label))
        print(f"  roll {seed}: {round(time.perf_counter() - t, 1)} s  {label.replace(chr(10), ' ')}")
    w, h = 330, 510
    sheet = Image.new("RGB", (5 * (w + 16) + 16, 2 * (h + 60) + 16), "white")
    dr = ImageDraw.Draw(sheet)
    for i, (img, label) in enumerate(cells):
        x, y = 16 + (i % 5) * (w + 16), 16 + (i // 5) * (h + 60)
        sheet.paste(img, (x, y + 40))
        dr.text((x, y), label, fill="black")
    sheet.save(HERE / "poster-roll-comparison.jpg", quality=82)


PIECES = {"rolls": build_roll_sheet, "stickers": build_stickers, "logo": build_logo, "poster": build_poster, "carousel": build_carousel}

if __name__ == "__main__":
    wanted = sys.argv[1:] or list(PIECES)
    for name in wanted:
        t = time.perf_counter()
        print(f"[{name}]")
        PIECES[name]()
        print(f"  total {round(time.perf_counter() - t, 1)} s")
    print("timings:", TIMINGS)
