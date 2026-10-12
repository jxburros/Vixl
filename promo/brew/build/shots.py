"""The shots of "Brew": a potion-making film about why Vixl is fun. Times are milliseconds.

Two voices share the screen. Jeffrey, Vixl's developer, speaks in Fraunces italic and every one of his
lines carries his name; Vixl's own copy stays in Inter Tight, like the rest of the brand.
Beat grid: the score runs at 120 BPM, so a beat is 500 ms.
"""
from __future__ import annotations

import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.append(str(HERE.parents[1] / "build"))
sys.path.insert(0, str(HERE))

from kit import (BODY, DEEP, FPS, GOOD, HEAD, LINE, MONO, MUTED, PANEL, ROOT, SEMI, SKY, WHITE, H, W, Scene,  # noqa: E402
                 centered, chip, ellipse, glow, group, image, rect, rich, shadow, text, wordmark)
from vixl import Project  # noqa: E402
from vixl.typefaces import install_font  # noqa: E402

import potion as P  # noqa: E402

BREW_DIR = HERE.parent
QUOTE = "fraunces-600-italic"
NIGHT = "#141127"
VIOLET = "#7B5CE0"
GOLD = "#FFD98A"
JEFFREY = "Jeffrey, Vixl's developer"


class BrewScene(Scene):
    def __init__(self, name, duration):
        super().__init__(name, duration, NIGHT)

    def project(self):
        # Same as Scene.project, plus Fraunces for Jeffrey's lines; fonts must exist before the text ops.
        p = Project(W, H, self.background)
        p._workspace = str(ROOT)
        install_font(p, "Inter Tight", 800, role="heading")
        install_font(p, "Inter", 400, role="body")
        install_font(p, "Inter", 600)
        install_font(p, "JetBrains Mono", 500)
        install_font(p, "Fraunces", 600, italic=True)
        batch = [{"type": "timeline-set", "duration": self.duration, "fps": FPS, "loop_mode": "off"}] + self.ops
        for i in range(0, len(batch), 9000):
            p.apply(batch[i:i + 9000], detail="brief")
        return p

    def build(self):
        p = self.project()
        p.compact()
        p.save(str(BREW_DIR / "scenes" / f"{self.name}.vixl"), overwrite=True)
        return p


# ------------------------------------------------------------------------------------------ shared
def night(sc, glow_at=(1450, 260), glow2_at=(300, 900), stars=True, seed=3):
    """The shared night sky. Every shot uses the same glows and stars, so a cut never moves the background."""
    sc.add(rect("bg-base", 0, 0, W, 1080, NIGHT),
           glow("bg-glow1", *glow_at, 1500, VIOLET, "38"),
           glow("bg-glow2", *glow2_at, 1200, P.BREW, "1C"))
    if not stars:
        return
    rng = random.Random(seed)
    for i in range(26):
        x, y, r = rng.uniform(40, 1880), rng.uniform(30, 520), rng.choice((3, 4, 5, 6))
        name = f"star{i}"
        sc.add(ellipse(name, x, y, r, r, "#FFFFFF"))
        phase = rng.randint(0, 1600)
        frames = [(0, 0.25)]
        t = phase
        while t < sc.duration:
            frames += [(t, 0.25), (t + 500, 0.9), (t + 1000, 0.25)]
            t += rng.randint(1600, 2600)
        sc.keys(name, "opacity", frames, "ease-in-out")


CREATES = ("shape", "text", "rich-text", "gradient", "pen", "frame", "group")


def finish(sc, keep=(), dur=380):
    """Fade the foreground out at the end of the shot, leaving the sky for the next one.

    ``keep`` names layers the next shot picks up where this one leaves them (the cauldron, the poster).
    """
    grouped, created = set(), []
    for op in sc.ops:
        if op.get("type") == "group":
            grouped.update(op["targets"])
        if op.get("type") in CREATES and "name" in op:
            created.append(op["name"])
    top = [n for n in created if n not in grouped and n not in keep and not n.startswith(("bg-", "star"))]
    sc.add(group("fg", top))
    sc.keys("fg", "opacity", [(0, 1), (sc.duration - dur, 1), (sc.duration - 20, 0)], "ease-in-cubic")
    return sc


def quote(sc, name, line, y, size, t, attribution=JEFFREY, width=1600, x=None, t_attr=None, align="center",
          attr_size=28, color=WHITE):
    """One of Jeffrey's lines: Fraunces italic in curly quotes, with his name underneath."""
    x = (W - width) / 2 if x is None else x
    sc.add(rich(name, f"“{line}”", x, y, size, width, color, QUOTE, align, 1.18))
    sc.words(name, t, "fade-up", "word", 480, 60)
    if attribution:
        lines = max(1, round(len(line) * size * 0.47 / width + 0.45))
        sc.add(rich(f"{name}-by", f"— {attribution}", x, y + lines * size * 1.18 + size * 0.35, attr_size,
                    width, MUTED, SEMI, align, 1.2))
        sc.fade(f"{name}-by", t_attr if t_attr is not None else t + 900, dur=400, rise=10)


def headline(sc, spans, t=150, y=96, size=72):
    sc.add(rich("headline", spans, 120, y, size, 1680, WHITE, HEAD))
    sc.words("headline", t, "fade-up", "word", 500, 70)


def bubbles(sc, cx, rim_y, scale=1.0, until=None, seed=5):
    rng = random.Random(seed)
    until = until or sc.duration
    for i in range(7):
        name = f"bubble{i}"
        bx = cx + rng.uniform(-230, 230) * scale
        d = rng.choice((18, 22, 26, 30)) * scale
        sc.add(ellipse(name, bx, rim_y, d, d, "#BFFFEA"))
        t = rng.randint(0, 1200)
        op, ty, sx = [(0, 0)], [(0, 0)], [(0, 0.4)]
        while t + 900 < until:
            op += [(t, 0), (t + 150, 0.85), (t + 700, 0.85), (t + 900, 0)]
            ty += [(t, 0), (t + 900, -70 * scale)]
            sx += [(t, 0.4), (t + 700, 1.0), (t + 900, 1.4)]
            t += rng.randint(1100, 1700)
        sc.keys(name, "opacity", op, "linear")
        sc.keys(name, "translate-y", ty, "ease-out-quad")
        sc.keys(name, "scale", sx, "ease-out-quad")


# ----------------------------------------------------------------------------------------------- 1
INGREDIENTS = [("an idea", -380, -16), ("autumn vibes", 300, 12), ("bold type", -240, 18), ("1080 × 1350", 420, -10),
               ("moodboard.jpg", -460, 8), ("brand colours", 260, -14), ("a vague feeling", -120, 20)]
BREW_COLOURS = ["#3FE0B0", "#F4A259", "#7B5CE0", "#E79AC3", "#5FD3E0", "#FFD166", "#C77DFF", "#3FE0B0"]
POT_X, RIM_Y = 960, 720
POT_PARTS = ["pot-leg1", "pot-leg2", "pot-body", "pot-hi", "pot-rim", "pot-brew", "pot-glow"]


def s01_ingredients():
    sc = BrewScene("01-ingredients", 8000)
    night(sc)
    sc.add(P.cauldron(POT_X, RIM_Y, 0.85))
    sc.keys("pot-glow", "opacity", [(0, 0.5), (2000, 0.8), (8000, 1)], "ease-in-out")
    bubbles(sc, POT_X, RIM_Y, 0.85)
    quote(sc, "q", "It kind of feels like making a potion.", 110, 80, 250, t_attr=1300)
    times = [2200 + i * 560 for i in range(len(INGREDIENTS))]
    brew = [(0, BREW_COLOURS[0])]
    for i, ((label, dx, rot), t) in enumerate(zip(INGREDIENTS, times)):
        name = f"ing{i}"
        w = round(len(label) * 30 * 0.58 + 48)
        sc.add(chip(name, label, POT_X - w / 2, RIM_Y - 70, size=30, fg=WHITE, bg="#2F2752", font=MONO,
                    stroke="#8F7BFF"))
        land = t + 760
        sc.keys(name, "translate-y", [(0, -820), (t, -820), (land, 0)], "ease-in-quad")
        sc.keys(name, "translate-x", [(0, dx), (t, dx), (land, 0)], "ease-out-cubic")
        sc.keys(name, "rotation", [(0, rot), (t, rot), (land, rot * 0.3)], "linear")
        sc.keys(name, "scale", [(0, 1), (land - 60, 1), (land + 220, 0.1)], "ease-in-cubic")
        sc.keys(name, "opacity", [(0, 1), (land, 1), (land + 220, 0)], "linear")
        ring = f"splash{i}"
        sc.add(ellipse(ring, POT_X, RIM_Y + 4, 220, 40, "#00000000", "#E8FFF6", 4))
        sc.keys(ring, "scale", [(0, 0.3), (land, 0.3), (land + 500, 2.1)], "ease-out-cubic")
        sc.keys(ring, "opacity", [(0, 0), (land, 0), (land + 60, 0.9), (land + 500, 0)], "linear")
        brew += [(land, BREW_COLOURS[i]), (land + 300, BREW_COLOURS[i + 1])]
    sc.keys("pot-brew", "fill", brew, "ease-in-out")
    keep = POT_PARTS + [f"bubble{i}" for i in range(7)] + [f"splash{i}" for i in range(len(INGREDIENTS))]
    return finish(sc, keep)


# ----------------------------------------------------------------------------------------------- 2
HERO = dict(x=744, y=300, w=432, h=540)
HERO_LEFT = (120, 260, 480, 600)  # the poster's place in shots 3 and 4


def s02_moon():
    sc = BrewScene("02-moon", 7000)
    night(sc)
    sc.add(glow("moon-halo", 1600, 300, 520, GOLD, "50"), ellipse("moon", 1600, 300, 190, 190, "#FFF1C9"),
           ellipse("moon-c1", 1570, 280, 34, 34, "#00000012"), ellipse("moon-c2", 1630, 330, 22, 22, "#00000010"),
           group("sky-moon", ["moon-halo", "moon", "moon-c1", "moon-c2"]))
    sc.keys("sky-moon", "translate-y", [(0, 1150), (700, 1150), (2900, 0)], "ease-out-cubic")
    sc.add(rect("spoon", POT_X + 120, RIM_Y - 330, 30, 380, "#7A5A3A", 15))
    sc.keys("spoon", "rotation", [(0, 14), (600, -16), (1200, 14), (1800, -16), (2400, 14), (3000, -12)],
            "ease-in-out-sine")
    sc.fade("spoon", 0, dur=500)
    sc.slide("spoon", 0, dy=-120, dur=600, easing="ease-out-cubic")
    sc.add(P.cauldron(POT_X, RIM_Y, 0.85))
    sc.keys("pot-glow", "opacity", [(0, 1), (3100, 1), (3500, 1.0)])
    sc.keys("pot-glow", "scale", [(0, 1), (3100, 1), (3600, 1.8), (4400, 1.1)], "ease-out-cubic")
    bubbles(sc, POT_X, RIM_Y, 0.85, until=3400, seed=8)
    pot = ["spoon", "pot-leg1", "pot-leg2", "pot-body", "pot-hi", "pot-rim", "pot-brew", "pot-glow"] + \
          [f"bubble{i}" for i in range(7)]
    sc.add(group("pot", pot))
    quote(sc, "q", "Stir it up, wait for the full moon, and see what comes out!", 90, 66, 200, width=1500,
          t_attr=1500)
    for name in ("q", "q-by"):
        sc.keys(name, "opacity", [(3000, 1), (3400, 0)], "ease-in-cubic")
    sc.add(glow("burst", POT_X, RIM_Y - 60, 1300, GOLD, "88"))
    sc.keys("burst", "scale", [(0, 0.1), (3300, 0.1), (3800, 1.2)], "ease-out-cubic")
    sc.keys("burst", "opacity", [(0, 0), (3300, 0), (3500, 1), (4600, 0)], "ease-in-out")
    sc.keys("pot", "translate-y", [(0, 0), (3600, 0), (4500, 700)], "ease-in-cubic")
    sc.add(P.poster_group("hero", HERO["x"], HERO["y"], HERO["w"], HERO["h"]), shadow("hero", 60, 28, 0.55))
    sc.keys("hero", "translate-y", [(0, 380), (3400, 380), (4500, -40)], "ease-out-back")
    sc.keys("hero", "scale", [(0, 0.12), (3400, 0.12), (4500, 1.0)], "ease-out-back")
    sc.keys("hero", "opacity", [(0, 0), (3400, 0), (3700, 1)])
    sc.add(centered("hero-file", "harvest-moon.vixl  ·  1080 × 1350", 870, 28, MUTED, MONO))
    sc.fade("hero-file", 5000, dur=400, rise=10)
    return finish(sc, ("pot", "hero", "burst"))


# ----------------------------------------------------------------------------------------------- 3
def s03_ready(report):
    """``report`` is what the real ``check`` said about the hero poster (see make_video.measured_checks)."""
    sc = BrewScene("03-ready", 7000)
    night(sc, glow_at=(600, 500), stars=False)
    headline(sc, [("What comes out is ", None), ("ready to use.", SKY)])
    px, py, pw, ph = HERO_LEFT
    sc.add(P.poster_group("hero", px, py, pw, ph), shadow("hero", 50, 24, 0.5))
    # Shot 2 ends with the poster at HERO scaled 1:1 and raised 40 px; start there and settle into place.
    k = HERO["w"] / pw
    dx = (HERO["x"] + HERO["w"] / 2) - (px + pw / 2)
    dy = (HERO["y"] - 40 + HERO["h"] / 2) - (py + ph / 2)
    for prop, v in (("translate-x", dx), ("translate-y", dy), ("scale", k)):
        sc.keys("hero", prop, [(0, round(v, 2)), (150, round(v, 2)), (950, 0 if prop != "scale" else 1)],
                "ease-in-out-cubic")
    marks = []
    for i, (mx, my) in enumerate(((px, py), (px + pw, py), (px, py + ph), (px + pw, py + ph))):
        sx, sy = (-1 if mx == px else 1), (-1 if my == py else 1)
        hx = mx + (sx * 14 if sx > 0 else -14 - 40)
        vy = my + (sy * 14 if sy > 0 else -14 - 40)
        sc.add(rect(f"crop{i}h", hx, my - 1, 40, 2, WHITE), rect(f"crop{i}v", mx - 1, vy, 2, 40, WHITE))
        marks += [f"crop{i}h", f"crop{i}v"]
    sc.add(rect("bleed", px - 10, py - 10, pw + 20, ph + 20, "#00000000", 0, "#FF6BD5", 2))
    marks.append("bleed")
    sc.add(group("marks", marks))
    sc.fade("marks", 1200, dur=500)
    sc.add(rich("marks-label", "trim  ·  bleed", px, py + ph + 22, 22, pw, MUTED, MONO, "center"))
    sc.fade("marks-label", 1400, dur=400)

    rows = [("Live text", "‘HARVEST MOON’ is still type, not pixels"),
            (f"{report['layers']} layers", "every part stays editable"),
            ("Fonts embedded", "Inter Tight and Inter travel with the file"),
            ("Checked", f"{report['checks']} checks, {report['fixes']} things to fix"),
            ("Print", "CMYK PDF with trim and bleed, when you ask")]
    fx, fy = 700, 270
    for i, (title, detail) in enumerate(rows):
        y = fy + i * 112
        name = f"r{i}"
        sc.add(rect(f"{name}-bg", fx, y, 1100, 92, PANEL, 18),
               ellipse(f"{name}-dot", fx + 52, y + 46, 40, 40, GOOD),
               rich(f"{name}-mark", "✓", fx + 32, y + 28, 26, 40, DEEP, HEAD, "center", 1.2),
               text(f"{name}-title", title, fx + 96, y + 26, 32, WHITE, SEMI),
               text(f"{name}-detail", detail, fx + 400, y + 31, 26, MUTED, BODY),
               group(name, [f"{name}-bg", f"{name}-dot", f"{name}-mark", f"{name}-title", f"{name}-detail"]))
        sc.fade(name, 1000 + i * 380, dur=300)
        sc.slide(name, 1000 + i * 380, dx=50, dur=450)
    quote(sc, "q", "Everything is already almost ready for print.", 880, 40, 3600, width=1100, x=fx, align="left",
          attr_size=24)
    return finish(sc, ("hero",))


# ----------------------------------------------------------------------------------------------- 4
ASKS = [("Warmer sky, please.", 1000), ("Bigger moon.", 3000), ("Make the badge say 7 PM.", 5000)]


def s04_adjust():
    sc = BrewScene("04-adjust", 8000)
    night(sc, glow_at=(500, 600), stars=False)
    headline(sc, [("Close? ", None), ("Don't re-roll. Just ask.", SKY)])
    px, py, pw, ph = HERO_LEFT
    sheets = P.harvest("hero", px, py, pw, ph)
    warm = P.PALETTES["ember"]
    sheets["sky"].append({"type": "gradient", "name": "hero-sky2", "direction": "vertical", "x": px, "y": py,
                          "width": pw, "height": ph,
                          "stops": [{"offset": o, "color": c} for o, c in zip((0, 0.45, 0.78, 1), warm["sky"])]})
    sc.add(P.flat(sheets), group("hero", P.names(sheets)), shadow("hero", 50, 24, 0.5))
    a, b, c = (t + 600 for _, t in ASKS)
    sc.keys("hero-sky2", "opacity", [(0, 0), (a, 0), (a + 700, 1)], "ease-in-out")
    sc.keys("hero-moon", "fill", [(0, P.PALETTES["harvest"]["moon"]), (a, P.PALETTES["harvest"]["moon"]),
                                  (a + 700, warm["moon"])], "ease-in-out")
    sc.keys("hero-far", "fill", [(0, P.PALETTES["harvest"]["far"]), (a, P.PALETTES["harvest"]["far"]),
                                 (a + 700, warm["far"])], "ease-in-out")
    sc.keys("hero-near", "fill", [(0, P.PALETTES["harvest"]["near"]), (a, P.PALETTES["harvest"]["near"]),
                                  (a + 700, warm["near"])], "ease-in-out")
    md, mcx, mcy = 0.5 * pw, px + pw / 2, py + ph * 0.64
    grow = 1.22
    for name, (ox, oy) in (("hero-moon", (0, 0)), ("hero-halo", (0, 0)), ("hero-crater1", (-0.18 * md, -0.1 * md)),
                           ("hero-crater2", (0.16 * md, 0.14 * md))):
        sc.keys(name, "scale", [(0, 1), (b, 1), (b + 600, grow)], "ease-out-back")
        if ox or oy:
            sc.keys(name, "translate-x", [(0, 0), (b, 0), (b + 600, round(ox * (grow - 1), 2))], "ease-out-back")
            sc.keys(name, "translate-y", [(0, 0), (b, 0), (b + 600, round(oy * (grow - 1), 2))], "ease-out-back")
    sc.key("hero-badge-label", "text", 0, "FREE")
    sc.key("hero-badge-label", "text", c + 150, "7 PM")
    sc.keys("hero-badge", "scale", [(0, 1), (c, 1), (c + 150, 1.25), (c + 500, 1)], "ease-out-back")
    sc.keys("hero-badge", "rotation", [(0, 0), (c, 0), (c + 500, 360)], "ease-in-out-cubic")

    cx, cw = 700, 1100
    sc.add(rect("chat", cx, 260, cw, 600, DEEP, 24, LINE))
    sc.add(text("chat-title", "same document, three requests", cx + 36, 284, 22, MUTED, MONO))
    sc.fade("chat", 200, dur=400)
    sc.fade("chat-title", 300, dur=400)
    for i, (ask, t) in enumerate(ASKS):
        y = 350 + i * 168
        w = round(len(ask) * 32 * 0.52 + 64)
        name = f"ask{i}"
        sc.add(rect(f"{name}-bg", cx + cw - 40 - w, y, w, 70, VIOLET, 35),
               rich(f"{name}-text", ask, cx + cw - 40 - w, y + 16, 32, w, WHITE, SEMI, "center", 1.2),
               group(name, [f"{name}-bg", f"{name}-text"]))
        sc.pop(name, t, 420, 0.7)
        reply = f"reply{i}"
        sc.add(rich(reply, [("✓ ", GOOD), ("one edit, same poster", MUTED)], cx + 40, y + 92, 24, 600, WHITE, MONO))
        sc.fade(reply, t + 800, dur=300, rise=8)
    sc.add(rich("tally", "edits 0    re-rolls 0", cx, 880, 34, cw, WHITE, MONO, "right"))
    sc.key("tally", "text", 0, "edits 0    re-rolls 0")
    sc.fade("tally", 500, dur=400)
    for i, (_, t) in enumerate(ASKS):
        sc.key("tally", "text", t + 600, f"edits {i + 1}    re-rolls 0")
    quote(sc, "q", "I can be really close, and I can just ask for adjustments to my liking.", 930, 34, 6300,
          width=1680, x=120, align="left", attr_size=22, attribution="Jeffrey")
    return finish(sc)


# ----------------------------------------------------------------------------------------------- 5
BASE = dict(title_scale=0.72, moon_size=1.15)
FIXES = [("bigger title", dict(title_scale=1.0, moon_size=1.0)), ("title at the bottom", dict(title_at="bottom")),
         ("left-aligned", dict(align="left")), ("framed", dict(frame=True)), ("plum palette", dict(palette="plum")),
         ("smaller moon", dict(moon_size=0.7)), ("no badge", dict(badge=None)),
         ("bold + warm", dict(title_scale=1.0, moon_size=0.9, palette="ember"))]
PICK5 = 0


def s05_eight():
    sc = BrewScene("05-eight", 8000)
    night(sc, glow_at=(960, 600), stars=False)
    sc.add(centered("headline", [("Eight ideas for one problem? ", None), ("See them all.", SKY)], 96, 72))
    sc.words("headline", 150, "fade-up", "word", 500, 70)
    sc.add(centered("problem", [("the problem: ", MUTED), ("the title feels lost", GOLD)], 190, 26, WHITE, MONO))
    sc.fade("problem", 500, dur=300)
    w, h, gap = 250, 312, 30
    x0 = (W - (4 * w + 3 * gap)) / 2
    for i, (label, fix) in enumerate(FIXES):
        x, y = x0 + (i % 4) * (w + gap), 260 + (i // 4) * (h + gap)
        name = f"v{i}"
        sc.add(P.poster_group(name, x, y, w, h, info_on=False, **{**BASE, **fix}))
        tag = f"{name}-tag"
        sc.add(chip(tag, f"{i + 1}  {label}", x + 10, y + h - 44, size=17, fg=WHITE, bg="#0E0B1CD0", font=MONO))
        t = 900 + i * 170
        sc.pop(name, t, 450, 0.8)
        sc.fade(tag, t + 250, dur=250)
        if i != PICK5:
            for n in (name, tag):
                sc.keys(n, "opacity", [(5200, 1), (5600, 0.25)], "ease-in-out")
    px, py = x0 + (PICK5 % 4) * (w + gap), 260 + (PICK5 // 4) * (h + gap)
    sc.add(rect("pick", px - 8, py - 8, w + 16, h + 16, "#00000000", 14, GOOD, 6))
    sc.pop("pick", 5300, 400, 1.15)
    sc.add(chip("pick-chip", "✓ this one", px + w - 150, py - 30, size=22, fg=DEEP, bg=GOOD, font=SEMI, width=150))
    sc.pop("pick-chip", 5500, 380, 0.5)
    quote(sc, "q", "If I have 8 ideas on how to fix one design problem, I can see them all made at once.",
          945, 32, 2600, width=1680, attr_size=22, attribution="Jeffrey")
    return finish(sc)


# ----------------------------------------------------------------------------------------------- 6
PALETTE_NAMES = list(P.PALETTES)


def rounds(seed=11):
    """Three rounds of twenty: each round keeps what the last pick settled and varies the rest."""
    rng = random.Random(seed)
    picks = (3, 6, 15)
    out, fixed = [], {}
    for r in range(3):
        tiles = []
        for _ in range(20):
            v = dict(fixed)
            v.setdefault("palette", rng.choice(PALETTE_NAMES))
            if r <= 1:
                v.update(title_at=rng.choice(("top", "top", "bottom")), align=rng.choice((None, None, "left")))
                v.update(frame=rng.random() < 0.3, badge=rng.choice(("FREE", "FREE", None)))
            v.update(moon_size=round(rng.uniform(0.7, 1.15), 2), title_scale=round(rng.uniform(0.82, 1.0), 2),
                     hill_amp=round(rng.uniform(0.5, 1.8), 2))
            tiles.append(v)
        out.append(tiles)
        chosen = tiles[picks[r]]
        if r == 0:
            fixed = {"palette": chosen["palette"]}
        elif r == 1:
            fixed.update({k: chosen[k] for k in ("title_at", "align", "frame", "badge")})
    return out, picks


def s06_rounds():
    sc = BrewScene("06-rounds", 9000)
    night(sc, glow_at=(960, 500), stars=False)
    headline(sc, [("Pick one. ", None), ("Brew twenty more.", SKY)])
    all_rounds, picks = rounds()
    w, h, gx, gy = 150, 188, 20, 22
    x0, y0 = (W - (10 * w + 9 * gx)) / 2, 250
    starts = (300, 3000, 5700)
    sc.add(text("round", "ROUND 1  ·  20 variations", x0, 200, 26, GOLD, MONO))
    sc.key("round", "text", 0, "ROUND 1  ·  20 variations")
    sc.fade("round", 250, dur=300)
    rail_x = x0
    for r, tiles in enumerate(all_rounds):
        t0 = starts[r]
        t_pick, t_out = t0 + 1500, t0 + 2400
        if r:
            sc.key("round", "text", t0 - 100, f"ROUND {r + 1}  ·  20 variations")
        for i, v in enumerate(tiles):
            x, y = x0 + (i % 10) * (w + gx), y0 + (i // 10) * (h + gy)
            name = f"r{r}t{i}"
            sc.add(P.poster_group(name, x, y, w, h, info_on=False, **v))
            sc.show(name, t0, t_out + 400)
            ti = t0 + i * 35
            sc.keys(name, "scale", [(0, 0.6), (ti, 0.6), (ti + 380, 1)], "ease-out-back")
            if i == picks[r]:
                sc.keys(name, "opacity", [(0, 0), (ti, 0), (ti + 220, 1), (t_out, 1), (t_out + 300, 0)])
            else:
                sc.keys(name, "opacity", [(0, 0), (ti, 0), (ti + 220, 1), (t_pick, 1), (t_pick + 300, 0.2),
                                          (t_out, 0.2), (t_out + 300, 0)])
        px, py = x0 + (picks[r] % 10) * (w + gx), y0 + (picks[r] // 10) * (h + gy)
        ring = f"pick{r}"
        sc.add(rect(ring, px - 6, py - 6, w + 12, h + 12, "#00000000", 12, GOOD, 5))
        sc.keys(ring, "opacity", [(0, 0), (t_pick, 0), (t_pick + 200, 1), (t_out, 1), (t_out + 300, 0)])
        # The pick lands in the rail below and stays.
        rx = rail_x + r * 170
        keep = f"keep{r}"
        sc.add(P.poster_group(keep, rx, 720, 120, 150, info_on=False, **tiles[picks[r]]))
        sc.fade(keep, t_out, dur=400)
        sc.keys(keep, "translate-y", [(0, -60), (t_out, -60), (t_out + 500, 0)], "ease-out-back")
        if r < 2:
            arrow = f"arrow{r}"
            sc.add(rich(arrow, "→", rx + 124, 765, 40, 46, MUTED, SEMI, "center"))
            sc.fade(arrow, t_out + 300, dur=300)
    sc.add(text("rail-label", "your picks", x0, 890, 22, MUTED, MONO))
    sc.fade("rail-label", starts[0] + 2400, dur=300)
    sc.add(rich("tally", [("60", GOLD), (" designs seen.  ", WHITE), ("3", GOLD), (" decisions made.", WHITE)],
                640, 760, 48, 1160, WHITE, HEAD, "right"))
    sc.words("tally", 8200, "fade-up", "word", 400, 60)
    quote(sc, "q", "Make 20 variations, pick one, make 20 variations of that, pick one, and so on.", 950, 32,
          600, width=1680, x=x0, align="left", attr_size=22, attribution="Jeffrey", t_attr=1600)
    return finish(sc)


# ----------------------------------------------------------------------------------------------- 7
BRIEFS = [("A PINCH", "a poster for a night market",
           dict(plain=True, palette="slate", title="NIGHT MARKET", info="OCT 24", badge=None)),
          ("A SPOONFUL", "autumn night market poster, warm colours, a big moon",
           dict(palette="harvest", badge=None, info="NIGHT MARKET  ·  OCT 24")),
          ("A HANDFUL", "Harvest Moon night market, Oct 24. Indigo to amber, heavy type, a cratered moon over "
           "rolling hills, a FREE badge, 1080 × 1350.", dict())]


def s07_direction():
    sc = BrewScene("07-direction", 8000)
    night(sc, glow_at=(1500, 500), stars=False)
    headline(sc, [("A pinch of direction, ", None), ("or a handful.", SKY)])
    w, h = 300, 375
    for i, (amount, brief, kw) in enumerate(BRIEFS):
        cx = 370 + i * 590
        x = cx - 250
        name = f"brief{i}"
        sc.add(rect(f"{name}-bg", x, 220, 500, 190, DEEP, 20, LINE),
               text(f"{name}-amount", amount, x + 28, 240, 22, GOLD, MONO),
               rich(f"{name}-text", brief, x + 28, 280, 22, 444, WHITE, BODY, line_height=1.3),
               group(name, [f"{name}-bg", f"{name}-amount", f"{name}-text"]))
        t = 500 + i * 900
        sc.fade(name, t, dur=350, rise=16)
        poster = f"out{i}"
        sc.add(P.poster_group(poster, cx - w / 2, 450, w, h, **kw), shadow(poster, 40, 18, 0.5))
        sc.pop(poster, t + 900, 500, 0.7)
    sc.add(rich("note", [("Small models make something tidy, if a little plain. ", MUTED),
                         ("More direction, better results.", WHITE)], 120, 850, 28, 1680, WHITE, BODY, "center"))
    sc.fade("note", 3800, dur=400, rise=10)
    quote(sc, "q", "You can give it as little or as much information as you want, and you'll still pretty much get "
          "something close to what you were thinking.", 910, 32, 4600, width=1500, attr_size=22,
          attribution="Jeffrey")
    sc.add(rich("illus", "illustration: one recipe, three briefs", 1000, 1040, 18, 800, "#6E6990", MONO, "right"))
    sc.fade("illus", 1400, dur=400)
    return finish(sc)


# ----------------------------------------------------------------------------------------------- 8
SIZES = [("Story", "1080 × 1920", 120, 250, 320, 569), ("Poster", "1080 × 1350", 470, 250, 400, 500),
         ("Post", "1080 × 1080", 900, 250, 300, 300), ("Link card", "1200 × 630", 1230, 250, 570, 299),
         ("Flyer", "A6", 940, 580, 220, 310), ("Slide", "1920 × 1080", 1230, 580, 570, 321),
         ("Banner", "1584 × 396", 470, 790, 400, 100)]


def s08_bottles():
    sc = BrewScene("08-bottles", 8000)
    night(sc, glow_at=(960, 600), stars=False)
    sc.add(rich("headline", [("One potion. ", None), ("A hundred bottles.", SKY)], 120, 70, 64, 1680, WHITE, HEAD))
    sc.words("headline", 100, "fade-up", "word", 500, 70)
    sc.add(rich("sub", "Same recipe, tailored to every size, format and platform. Similar, never the same.",
                120, 160, 28, 1680, MUTED, BODY))
    sc.fade("sub", 900, dur=400)
    palettes = ["harvest", "harvest", "harvest", "harvest", "harvest", "harvest", "harvest"]
    for i, ((label, size, x, y, w, h), pal) in enumerate(zip(SIZES, palettes)):
        name = f"b{i}"
        sc.add(P.poster_group(name, x, y, w, h, palette=pal, info_on=h > 120), shadow(name, 36, 16, 0.5))
        tag = f"{name}-tag"
        sc.add(chip(tag, f"{label}  ·  {size}", x, y + h + 10, size=17, fg=WHITE, bg=PANEL, font=MONO))
        t = 600 + i * 330
        sc.pop(name, t, 480, 0.7)
        sc.fade(tag, t + 300, dur=250)
    # The same set in a second colourway, to show "similar, never the same".
    sc.add(chip("swap", "→  same set, plum colourway", 120, 900, size=24, fg=DEEP, bg=GOLD, font=SEMI))
    sc.pop("swap", 5200, 400, 0.6)
    for i, (label, size, x, y, w, h) in enumerate(SIZES):
        name = f"c{i}"
        sc.add(P.poster_group(name, x, y, w, h, palette="plum", info_on=h > 120))
        sc.keys(name, "opacity", [(0, 0), (5400 + i * 90, 0), (5800 + i * 90, 1)], "ease-in-out")
    return finish(sc)


# ----------------------------------------------------------------------------------------------- 9
OUT = "marketing/output/"
WALL = [("kit", OUT + "kit-overview.png", 120, 250, 600, 435), ("campaign", OUT + "campaign/contact-sheet.png", 120, 705, 600, 233),
        ("tabloid", OUT + "print/poster-tabloid.png", 740, 250, 300, 460),
        ("carousel", OUT + "carousel/contact-sheet.png", 740, 730, 300, 261),
        ("story", OUT + "social/story-1080x1920.png", 1060, 250, 250, 444),
        ("teaser", OUT + "motion/teaser-frame.png", 1060, 714, 250, 250),
        ("og", OUT + "social/og-card-1200x630.png", 1330, 250, 470, 247),
        ("map", OUT + "showcase/capability-map.png", 1330, 517, 470, 353),
        ("linkedin", OUT + "social/linkedin-banner-1584x396.png", 1330, 890, 470, 117)]


def s09_self():
    sc = BrewScene("09-self", 7000)
    night(sc, glow_at=(960, 540), stars=False)
    headline(sc, [("It even makes ", None), ("its own marketing.", SKY)])
    names = []
    for i, (key, path, x, y, w, h) in enumerate(WALL):
        sc.add(image(key, path, x, y, w, h, 14), shadow(f"{key}-base", 30, 14, 0.5))
        sc.pop(key, 400 + i * 150, 480, 0.85)
        names.append(key)
    sc.add(group("wall", names))
    sc.keys("wall", "opacity", [(3600, 1), (4100, 0.35)], "ease-in-out")
    sc.add(rect("band", 0, 470, W, 260, "#0E0B1CE6"))
    sc.fade("band", 3800, dur=400)
    quote(sc, "q", "I think that's so funny.", 520, 84, 4000, attr_size=28, t_attr=4600)
    sc.add(chip("this", "Including this video.", 1340, 760, size=30, fg=DEEP, bg=GOLD, font=SEMI, width=400))
    sc.pop("this", 5500, 450, 0.5)
    sc.keys("this", "rotation", [(5500, -8), (5950, -4)], "ease-out-back")
    return finish(sc)


# ----------------------------------------------------------------------------------------------- 10
def s10_fun():
    sc = BrewScene("10-fun", 6000)
    night(sc, glow_at=(960, 460), glow2_at=(960, 1000), seed=9)
    quote(sc, "q", "I am actually having way too much fun with this app.", 380, 100, 300, width=1500, t_attr=2600,
          attr_size=34)
    return finish(sc)


# ----------------------------------------------------------------------------------------------- 11
def s11_end():
    sc = BrewScene("11-end", 5000)
    night(sc, glow_at=(960, 420), glow2_at=(960, 1000), seed=4)
    ops, names = wordmark("m", 760, 120, 400)
    sc.add(ops, group("logo", names))
    sc.pop("logo", 0, 600, 0.5)
    sc.add(centered("line", [("Every potion comes with ", None), ("its recipe.", SKY)], 400, 86))
    sc.words("line", 300, "fade-up", "word", 500, 100)
    sc.add(centered("recipe", "The .vixl master: layers, live text and history, ready for the next brew.", 530, 32,
                    MUTED, BODY))
    sc.fade("recipe", 1200, dur=400, rise=12)
    sc.add(centered("tagline", [("Ideas become ", None), ("editable.", SKY)], 680, 48, WHITE, HEAD))
    sc.fade("tagline", 1700, dur=400, rise=12)
    sc.add(centered("url", "github.com/jxburros/Vixl", 770, 40, WHITE, MONO))
    sc.fade("url", 2000, dur=400, rise=12)
    sc.add(centered("made", "Every frame of this video is an editable Vixl document.", 970, 26, MUTED, BODY))
    sc.fade("made", 2500, dur=500)
    return finish(sc)


SCENES = [s01_ingredients, s02_moon, s03_ready, s04_adjust, s05_eight, s06_rounds, s07_direction, s08_bottles,
          s09_self, s10_fun, s11_end]
