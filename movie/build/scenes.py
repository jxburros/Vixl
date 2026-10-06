"""The seven scenes of "The Germ King". Each function returns a ``Doc``."""
from __future__ import annotations

import math
import random

from characters import GOLD, crown_parts, elder, germ, pip
from vixlkit import Doc, text_width

INK = "#241446"
PAPER = "#fffdf5"


# ------------------------------------------------------------------ shared helpers
def talk(d: Doc, mouth: str, t0: int, t1: int, step: int = 170, visible_first: bool = True):
    """Flap a mouth layer open/closed between t0 and t1 (stepped visibility)."""
    d.talks.append((mouth, t0, t1, step))
    d.key(mouth, "visible", 0, False)
    t, on = t0, True
    while t < t1:
        d.key(mouth, "visible", t, on)
        t += step
        on = not on
    d.key(mouth, "visible", t1, False)


def blink(d: Doc, eyes: list[str], times: list[int], dur: int = 150):
    for e in eyes:
        d.key(e, "scale-y", 0, 1)
        for t in times:
            d.key(e, "scale-y", t, 1)
            d.key(e, "scale-y", t + dur // 2, 0.08)
            d.key(e, "scale-y", t + dur, 1)


def bubble(d: Doc, name: str, text: str, cx: float, cy: float, t0: int, t1: int,
           size: int = 34, tail: str = "left", fill: str = PAPER, ink: str = INK, stroke: str = INK):
    """Speech bubble centred on (cx, cy) that pops in at t0 and out at t1."""
    tw = text_width(text, size)
    lines = text.count("\n") + 1
    bw = tw + size * 1.5
    bh = lines * size * 1.2 + size * 0.9
    H = bh / 0.74
    up = tail.startswith("up")
    top = cy - bh / 2 - (H - bh) if up else cy - bh / 2  # the tail adds height above when flipped
    d.shape(f"{name}_b", "speech-bubble", cx - bw / 2, top, bw, H, fill, stroke=stroke, sw=4)
    if tail.endswith("right"):
        d.ops.append({"type": "flip", "target": f"{name}_b", "direction": "horizontal"})
    if up:
        d.ops.append({"type": "flip", "target": f"{name}_b", "direction": "vertical"})
    d.ctext(f"{name}_t", text, cx, cy, size, ink)
    d.group(name, [f"{name}_b", f"{name}_t"])
    d.pivot(name, 0.9 if tail.endswith("right") else 0.1, 0.0 if up else 1.0)
    d.key(name, "opacity", 0, 0)
    d.key(name, "opacity", t0, 0)
    d.key(name, "opacity", t0 + 120, 1)
    d.key(name, "opacity", t1, 1)
    d.key(name, "opacity", t1 + 140, 0)
    d.key(name, "scale", 0, 0.6)
    d.key(name, "scale", t0, 0.6)
    d.key(name, "scale", t0 + 260, 1, "ease-out-back")
    d.key(name, "scale", t1, 1)
    d.key(name, "scale", t1 + 140, 0.85, "ease-in")
    return name


def narrate(d: Doc, name: str, text: str, t0: int, t1: int, y: int = 34, size: int = 46):
    """Storybook narration line (white, dark outline) that fades in and out."""
    from vixlkit import text_width
    d.text(name, text, 640 - text_width(text, size) / 2, y, size, "#ffffff")
    d.text_stroke(name, 9, "#1a0f33")
    d.key(name, "opacity", 0, 0)
    d.key(name, "opacity", t0, 0)
    d.key(name, "opacity", t0 + 300, 1)
    d.key(name, "opacity", t1, 1)
    d.key(name, "opacity", t1 + 300, 0)
    d.key(name, "translate-y", t0, 12)
    d.key(name, "translate-y", t0 + 300, 0, "ease-out")
    d.ops.append({"type": "top", "target": name})


def vignette(d: Doc, strength: str = "#000000b0", inner: float = 0.55, name: str = "vignette"):
    d.gradient(name, [(0, "#00000000"), (inner, "#00000000"), (1, strength)], direction="radial")


def sparkle_field(d: Doc, prefix: str, n: int, seed: int, color: str = "#ffffff", area=(0, 0, 1280, 720),
                  size=(3, 9), twinkle: int = 1400, opacity: float = 0.9):
    rnd = random.Random(seed)
    names = []
    for i in range(n):
        x = rnd.uniform(area[0], area[0] + area[2])
        y = rnd.uniform(area[1], area[1] + area[3])
        s = rnd.uniform(*size)
        nm = d.ell(f"{prefix}{i}", x, y, s, s, color, opacity=opacity)
        t0 = rnd.randint(0, twinkle)
        d.cycle(nm, "opacity", 0.15, opacity, twinkle * rnd.uniform(0.7, 1.3), start=t0)
        names.append(nm)
    return names



# ------------------------------------------------------------------ the council hall
def hall_scenery(d: Doc):
    # wall, stone courses, windows, banners
    d.gradient("wall", [(0, "#241a3a"), (0.55, "#4a3765"), (1, "#33264a")])
    for i, y in enumerate(range(70, 400, 82)):
        d.line(f"course{i}", [(0, y), (1280, y)], "#ffffff", 2, smooth=False, opacity=0.07)
        for j, x in enumerate(range(60 + (i % 2) * 85, 1280, 170)):
            d.line(f"joint{i}_{j}", [(x, y), (x, y + 82)], "#ffffff", 2, smooth=False, opacity=0.06)
    for i, cx in enumerate((465, 815)):
        d.rect(f"winGlass{i}", cx - 62, 190, 124, 190, "#6f8fe0")
        d.ell(f"winArch{i}", cx, 190, 124, 124, "#6f8fe0")
        d.rect(f"winSill{i}", cx - 62, 340, 124, 40, "#a9bff2", opacity=0.55)
        d.line(f"winBar{i}", [(cx, 130), (cx, 382)], "#1d1633", 7, smooth=False)
        d.line(f"winBar2{i}", [(cx - 62, 270), (cx + 62, 270)], "#1d1633", 7, smooth=False)
        d.rect(f"winFrame{i}", cx - 62, 190, 124, 192, "#00000000", stroke="#1d1633", sw=9)
        d.ell(f"winFrameTop{i}", cx, 190, 124, 124, "#00000000", stroke="#1d1633", sw=9)
    d.ell("moonGlow", 835, 215, 70, 70, "#fff6c8", opacity=0.25)
    d.ell("moon", 835, 215, 34, 34, "#fff6c8")
    sparkle_field(d, "star", 14, 4, "#ffffff", area=(410, 150, 460, 120), size=(3, 6), twinkle=1800)
    for i, bx in enumerate((70, 1210)):
        d.rect(f"banner{i}", bx - 55, 0, 110, 300, "#8f2a3a", stroke=GOLD, sw=4)
        d.poly(f"bannerTip{i}", [(bx - 55, 300), (bx, 360), (bx + 55, 300)], "#8f2a3a", stroke=GOLD, sw=4)
        d.star(f"bannerStar{i}", bx, 170, 52, GOLD)
        d.rect(f"bannerBar{i}", bx - 62, 0, 124, 14, "#c9a14a")
    # torches
    for i, tx in enumerate((190, 1090)):
        d.ell(f"torchLight{i}", tx, 230, 340, 340, "#ffb347", opacity=0.14)
        d.cycle(f"torchLight{i}", "opacity", 0.1, 0.2, 520 + 90 * i)
        d.rect(f"torchHolder{i}", tx - 9, 252, 18, 70, "#2a1d12")
        d.ell(f"torchFlame{i}", tx, 240, 36, 42, "#ff9d2e")
        d.poly(f"torchTip{i}", [(tx - 15, 232), (tx, 176), (tx + 15, 232)], "#ff9d2e", smooth=True, tension=0.45)
        d.ell(f"torchCore{i}", tx, 246, 18, 24, "#ffe27a")
        d.group(f"torchFire{i}", [f"torchFlame{i}", f"torchTip{i}", f"torchCore{i}"])
        d.pivot(f"torchFire{i}", 0.5, 1.0)
        d.cycle(f"torchFire{i}", "scale-y", 0.92, 1.12, 260 + 40 * i)


def hall_bench(d: Doc, poster: bool = True):
    # the bench, floor and sign: everything here is built for tall people
    d.rect("floor", 0, 646, 1280, 80, "#3a2c4f")
    d.gradient("floorShade", [(0, "#00000066"), (1, "#00000000")], y=646, h=44)
    d.rect("benchFront", -10, 408, 1300, 242, "#5a3a2c")
    for i in range(8):
        d.rect(f"benchPanel{i}", 12 + i * 160, 440, 140, 180, "#6b4535", r=10, stroke="#3b241b", sw=3)
    d.gradient("benchShade", [(0, "#00000070"), (1, "#00000000")], y=408, h=40)
    d.rect("benchTop", -10, 384, 1300, 26, "#9a6a46")
    d.rect("benchTopLight", -10, 384, 1300, 6, "#c79566")
    d.ctext("benchPlate", "ORDER OF THE VERY TALL", 760, 428, 26, "#d9b86a")
    d.opacity("benchPlate", 0.8)
    if poster:  # MUST BE THIS TALL TO SPEAK
        d.rect("posterPaper", 62, 448, 196, 188, "#f1e4c0", stroke="#8a6a3a", sw=3)
        d.poly("posterArrow", [(160, 454), (186, 488), (170, 488), (170, 506), (150, 506), (150, 488), (134, 488)],
               "#d33a3a")
        d.ctext("posterText", "MUST BE\nTHIS TALL\nTO SPEAK", 160, 570, 27, INK)
        d.group("poster", ["posterPaper", "posterArrow", "posterText"])


# ------------------------------------------------------------------ microscope world
def micro_bg(d: Doc, D: int, seed: int, centre="#2cc2b0", mid="#1a8c93", edge="#0b4452", rods=6):
    rnd = random.Random(seed)
    d.gradient("water", [(0, centre), (0.6, mid), (1, edge)], direction="radial")
    for i in range(rods):  # drifting rod-shaped bacteria far in the background
        w, h = rnd.uniform(170, 280), rnd.uniform(46, 70)
        nm = d.shape(f"rod{i}", "capsule", rnd.uniform(0, 1100), rnd.uniform(40, 420), w, h, "#9ff0d4", opacity=0.14)
        d.rotate(nm, rnd.uniform(-35, 35))
        d.key(nm, "translate-x", 0, 0)
        d.key(nm, "translate-x", D, rnd.uniform(-90, 90), "linear")
    for i in range(10):
        r = rnd.uniform(60, 170)
        nm = d.ell(f"bokeh{i}", rnd.uniform(0, 1280), rnd.uniform(40, 520), r, r, "#bff7e8", opacity=0.07)
        d.cycle(nm, "translate-x", -30, 30, rnd.uniform(5000, 9000), start=0)
    for i in range(34):
        r = rnd.uniform(5, 20)
        nm = d.ell(f"spore{i}", rnd.uniform(0, 1280), rnd.uniform(60, 640), r, r, "#ffffff", opacity=0.28,
                   stroke="#e8fff8", sw=1.5)
        d.key(nm, "translate-y", 0, 0)
        d.key(nm, "translate-y", D, -rnd.uniform(60, 220), "linear")
        d.cycle(nm, "translate-x", -12, 12, rnd.uniform(1800, 3400), start=0)
    return rnd


def agar(d: Doc, rnd: random.Random, top: int = 612, rim: str = "#b98a2e", fill: str = "#e8bb55",
         dots: str = "#c98d2a"):
    d.ell("agarRim", 640, top + 288, 2400, 600, rim)
    d.ell("agar", 640, top + 300, 2340, 590, fill)
    d.ell("agarShine", 640, top + 28, 1500, 70, "#fff1b8", opacity=0.35)
    for i in range(22):
        r = rnd.uniform(6, 22)
        d.ell(f"colony{i}", rnd.uniform(40, 1240), rnd.uniform(top + 28, top + 98), r * 2, r, dots, opacity=0.55)


def reticle(d: Doc, label: str = "MICROSCOPE  x40,000"):
    """Faint microscope-eyepiece furniture: scale bar and magnification label."""
    d.text("scopeLabel", label, 36, 28, 26, "#d9fff4")
    d.opacity("scopeLabel", 0.7)
    d.line("scaleBar", [(36, 686), (196, 686)], "#d9fff4", 4, smooth=False, opacity=0.7)
    d.text("scaleText", "1 micron", 36, 650, 24, "#d9fff4")
    d.opacity("scaleText", 0.7)


def confetti(d: Doc, prefix: str, n: int, seed: int, t0: int, x0: float, x1: float, y0: float = -40,
             fall: float = 760, dur: int = 2600):
    rnd = random.Random(seed)
    for i in range(n):
        w, h = rnd.uniform(8, 16), rnd.uniform(14, 26)
        nm = d.rect(f"{prefix}{i}", rnd.uniform(x0, x1), y0, w, h,
                    rnd.choice(["#ffd84a", "#ff6f91", "#7df3ff", "#9bff8a", "#c58bff", "#ffffff"]))
        s = t0 + rnd.randint(0, 700)
        d.key(nm, "opacity", 0, 0)
        d.key(nm, "opacity", s, 0)
        d.key(nm, "opacity", s + 50, 1)
        d.key(nm, "translate-y", s, 0)
        d.key(nm, "translate-y", s + dur, fall, "linear")
        d.key(nm, "translate-x", s, 0)
        d.key(nm, "translate-x", s + dur, rnd.uniform(-160, 160), "ease-in-out-sine")
        d.key(nm, "rotation", s, 0)
        d.key(nm, "rotation", s + dur, rnd.uniform(-720, 720), "linear")


# ------------------------------------------------------------------------ scene 1
def council() -> Doc:
    D = 9000
    d = Doc("01-council", D, "#2b2142")

    hall_scenery(d)

    # the council (very tall)
    elder(d, "e1", "tallworth", 290, 205, 2.0)
    elder(d, "e2", "longshanks", 640, 205, 2.0)
    elder(d, "e3", "highbrow", 990, 205, 2.0)

    hall_bench(d)
    # gavel
    d.rect("gavelHandle", 1056, 330, 12, 66, "#6b4a2b", r=5)
    d.rect("gavelHead", 1032, 312, 60, 30, "#8a5a2b", r=8, stroke="#4d3015", sw=3)
    d.group("gavel", ["gavelHandle", "gavelHead"])
    d.pivot("gavel", 0.55, 1.0)
    d.key("gavel", "rotation", 0, 0)
    d.key("gavel", "rotation", 6700, 0)
    d.key("gavel", "rotation", 6850, -38, "ease-out")
    d.key("gavel", "rotation", 6960, 8, "ease-in")
    d.key("gavel", "rotation", 7100, 0)
    d.ctext("bang", "BANG!", 1140, 345, 52, "#ffd84a")
    d.opacity("bang", 0)
    d.rotate("bang", -8)
    d.key("bang", "opacity", 6940, 0)
    d.key("bang", "opacity", 6990, 1)
    d.key("bang", "opacity", 7500, 1)
    d.key("bang", "opacity", 7700, 0)
    d.key("bang", "scale", 6940, 0.5)
    d.key("bang", "scale", 7060, 1.15, "ease-out-back")

    # Pip walks in, waves, is ignored, jumps, deflates
    pip(d, "pip", 380, 694, 1.4)
    d.glow("pip_orb", "#7df3ff", 14)
    d.pivot("pip", 0.5, 1.0)
    d.key("pip", "translate-x", 0, -560)
    d.key("pip", "translate-x", 1900, 0, "ease-out")
    d.cycle("pip", "translate-y", 0, -9, 380, start=0, end=1900, easing="ease-out")
    d.cycle("pip", "rotation", -2.5, 2.5, 950, start=0, end=1900)
    d.key("pip", "rotation", 2100, 0)
    # wave
    d.key("pip_armL", "rotation", 1900, 0)
    d.key("pip_armL", "rotation", 2300, 125, "ease-out-back")
    d.cycle("pip_armL", "rotation", 105, 140, 300, start=2300, end=3900)
    d.key("pip_armL", "rotation", 4300, 0, "ease-in-out")
    blink(d, ["pip_eyeL", "pip_eyeR"], [1100, 3300, 6100])
    talk(d, "pip_mouth", 2300, 4000)
    bubble(d, "sayPip1", "Honorable Council!\nI request a seat!", 570, 500, 2300, 4100, 34)
    # jumps
    for i, t in enumerate((7100, 7750)):
        d.key("pip", "translate-y", t, 0)
        d.key("pip", "translate-y", t + 260, -110, "ease-out-quad")
        d.key("pip", "translate-y", t + 560, 0, "ease-in-quad")
        d.key("pip", "scale-y", t - 120, 1)
        d.key("pip", "scale-y", t - 20, 0.86)
        d.key("pip", "scale-y", t + 100, 1.12)
        d.key("pip", "scale-y", t + 560, 0.9)
        d.key("pip", "scale-y", t + 700, 1)
    d.key("pip_armL", "rotation", 7000, 0)
    d.key("pip_armL", "rotation", 7200, 140, "ease-out")
    d.cycle("pip_armL", "rotation", 120, 150, 240, start=7200, end=8500)
    d.key("pip_armL", "rotation", 8800, 0)
    talk(d, "pip_mouth", 7300, 8500, 140)
    bubble(d, "sayPip2", "I'M RIGHT HERE!", 600, 500, 7300, 8800, 42)
    # the final droop
    d.key("pip", "rotation", 8500, 0)
    d.key("pip", "rotation", 8900, -4, "ease-in-out")

    # the council ignores him (pupils scan left-right over his head; never down)
    for i, e in enumerate(("e1", "e2", "e3")):
        d.cycle(f"{e}_pupils", "translate-x", -5, 6, 1700 + i * 230, start=0)
        d.cycle(e, "translate-y", 0, -4, 2600 + i * 300, start=i * 200)
    talk(d, "e2_mouth", 4150, 5400)
    bubble(d, "sayE2", "Did someone\nspeak?", 868, 205, 4150, 5600, 34)
    talk(d, "e1_mouth", 5700, 6900)
    bubble(d, "sayE1", "Probably just\na draft.", 478, 188, 5700, 7000, 34)
    talk(d, "e3_mouth", 6700, 7500)
    bubble(d, "sayE3", "Next case!", 1130, 160, 6700, 8000, 38)

    vignette(d, "#000000a0", 0.55)
    narrate(d, "narr", "Wizard Pip had one small problem.", 300, 2300)
    d.ops.append({"type": "top", "target": "sayPip1"})
    for b in ("sayPip2", "sayE2", "sayE1", "sayE3", "bang"):
        d.ops.append({"type": "top", "target": b})
    d.solid("fadeIn", "#000000")  # open from black
    d.key("fadeIn", "opacity", 0, 1)
    d.key("fadeIn", "opacity", 700, 0, "ease-out")
    return d


# ------------------------------------------------------------------------ scene 2
def shrink() -> Doc:
    D = 6000
    d = Doc("02-shrink", D, "#150f2e")
    d.gradient("sky", [(0, "#100a26"), (0.6, "#2c1a5e"), (1, "#6a3688")])
    sparkle_field(d, "star", 70, 11, "#ffffff", area=(0, 0, 1280, 420), size=(2, 6), twinkle=2200)
    d.ell("moonGlow", 1040, 160, 260, 260, "#ffe9a8", opacity=0.12)
    d.ell("moon", 1040, 160, 150, 150, "#fff3c4")
    for i, (mx, my, mr) in enumerate(((1000, 130, 24), (1075, 190, 18), (1030, 215, 12))):
        d.ell(f"crater{i}", mx, my, mr, mr, "#e6d49a", opacity=0.7)
    # distant council tower, left behind
    d.poly("hills", [(0, 560), (180, 500), (380, 540), (620, 480), (860, 540), (1100, 490), (1280, 540), (1280, 720), (0, 720)],
           "#1d1340")
    d.poly("tower", [(1000, 500), (1000, 330), (985, 330), (1020, 270), (1055, 330), (1040, 330), (1040, 500)], "#150e30")
    d.rect("towerWin", 1012, 380, 16, 28, "#ffcf5a")
    d.rect("ground", 0, 628, 1280, 100, "#2b1f4a")
    d.gradient("groundLight", [(0, "#ffffff22"), (1, "#ffffff00")], y=628, h=30)

    # magic circle (drawn in perspective, centred on Pip's feet)
    cx, cy = 470, 656
    ring = [d.ell("ringOuter", cx, cy, 700, 190, "#00000000", stroke="#7df3ff", sw=6),
            d.ell("ringInner", cx, cy, 560, 152, "#00000000", stroke="#ff7bd5", sw=4),
            d.ell("circleGlow", cx, cy, 640, 170, "#7df3ff", opacity=0.3)]
    pts = []
    for i in range(5):
        a = -math.pi / 2 + i * 4 * math.pi / 5
        pts.append((cx + 270 * math.cos(a), cy + 72 * math.sin(a)))
    ring.append(d.poly("pentagram", pts, "#00000000", stroke="#ffffff", sw=4, smooth=False))
    runes = []
    for i in range(8):
        phi = 2 * math.pi * i / 8
        rx, ry = cx + 315 * math.cos(phi), cy + 86 * math.sin(phi)
        nm = d.shape(f"rune{i}", "diamond", rx - 11, ry - 11, 22, 22, "#ffd84a" if i % 2 else "#ff7bd5")
        runes.append(nm)
        for t in range(3000, D, 120):
            ang = phi + (t - 3000) / 1000.0 * 1.6
            d.key(nm, "translate-x", t, 315 * math.cos(ang) - 315 * math.cos(phi), "linear")
            d.key(nm, "translate-y", t, 86 * math.sin(ang) - 86 * math.sin(phi), "linear")
    d.group("circle", ring + runes)
    d.key("circle", "opacity", 0, 0)
    d.key("circle", "opacity", 3000, 0)
    d.key("circle", "opacity", 3500, 1)
    d.key("circle", "opacity", 5300, 1)
    d.key("circle", "opacity", 5900, 0)
    d.cycle("circleGlow", "opacity", 0.2, 0.55, 500, start=3000, end=D)

    # beam of light
    d.gradient("beam", [(0, "#7df3ff00"), (0.5, "#7df3ff99"), (1, "#7df3ff00")], direction="horizontal",
               x=300, y=0, w=340, h=660)
    d.blend("beam", "screen")
    d.key("beam", "opacity", 0, 0)
    d.key("beam", "opacity", 3300, 0)
    d.key("beam", "opacity", 4200, 0.75)
    d.key("beam", "opacity", 5400, 0.9)

    # Pip, close-up, grumpy
    pip(d, "pip", 470, 650, 3.3)
    d.glow("pip_orb", "#7df3ff", 18)
    d.pivot("pip", 0.5, 0.55)
    d.cycle("pip", "translate-y", 0, -5, 1400, start=0, end=3000)
    d.key("pip_armL", "rotation", 0, 0)
    d.key("pip_armL", "rotation", 2900, 0)
    d.key("pip_armL", "rotation", 3300, 105, "ease-out-back")
    d.key("pip_staffG", "rotation", 0, 0)
    d.key("pip_staffG", "rotation", 3000, 0)
    d.key("pip_staffG", "rotation", 3400, 14, "ease-out-back")
    d.key("pip_halo", "scale", 0, 1)
    d.key("pip_halo", "scale", 3000, 1)
    d.key("pip_halo", "scale", 4200, 2.4, "ease-in")
    d.key("pip_halo", "opacity", 3000, 0.35)
    d.key("pip_halo", "opacity", 4200, 0.5)
    blink(d, ["pip_eyeL", "pip_eyeR"], [1500, 2700])
    talk(d, "pip_mouth", 500, 2700, 160)
    talk(d, "pip_mouth", 3100, 4500, 130)
    bubble(d, "sayA", "Fine. If they won't\nlook UP at me...", 840, 330, 500, 2800, 40)
    bubble(d, "sayB", "...I'll go\nSMALLER!", 840, 300, 3100, 4600, 58)
    # shrink and spin, then vanish into a glint
    d.key("pip", "rotation", 0, 0)
    d.key("pip", "rotation", 4200, 0)
    d.key("pip", "rotation", 5400, -540, "ease-in-cubic")
    d.key("pip", "scale", 0, 1)
    d.key("pip", "scale", 4200, 1)
    d.key("pip", "scale", 5400, 0.02, "ease-in-cubic")
    d.key("pip", "translate-y", 3000, 0)
    d.key("pip", "translate-y", 4200, -12, "ease-out")
    d.key("pip", "translate-y", 5400, -60, "ease-in")
    # sparkles streaming upward
    rnd = random.Random(7)
    for i in range(34):
        x = cx + rnd.uniform(-300, 300)
        y = cy + rnd.uniform(-20, 40)
        nm = d.star(f"spark{i}", x, y, rnd.uniform(14, 34), rnd.choice(["#7df3ff", "#ffffff", "#ffd84a", "#ff7bd5"]),
                    points=4, inner=0.3)
        t0 = rnd.randint(3100, 4700)
        d.key(nm, "opacity", 0, 0)
        d.key(nm, "opacity", t0, 0)
        d.key(nm, "opacity", t0 + 200, 1)
        d.key(nm, "opacity", t0 + 1100, 0)
        d.key(nm, "translate-y", t0, 0)
        d.key(nm, "translate-y", t0 + 1200, -rnd.uniform(220, 520), "ease-out")
        d.key(nm, "rotation", t0, 0)
        d.key(nm, "rotation", t0 + 1200, rnd.uniform(-180, 180))
    # final glint where he vanished + white-out
    d.star("glint", 470, 470, 150, "#ffffff", points=4, inner=0.12)
    d.glow("glint", "#7df3ff", 30)
    d.key("glint", "opacity", 0, 0)
    d.key("glint", "opacity", 5200, 0)
    d.key("glint", "opacity", 5500, 1)
    d.key("glint", "scale", 5200, 0.1)
    d.key("glint", "scale", 5700, 1.4, "ease-out")
    d.key("glint", "rotation", 5200, 0)
    d.key("glint", "rotation", 5900, 90)
    d.solid("flash", "#ffffff")
    d.key("flash", "opacity", 0, 0)
    d.key("flash", "opacity", 5350, 0)
    d.key("flash", "opacity", 5950, 1, "ease-in")
    vignette(d, "#000000a0", 0.6)
    for b in ("sayA", "sayB", "flash"):
        d.ops.append({"type": "top", "target": b})
    return d


# ------------------------------------------------------------------------ scene 3
def arrival() -> Doc:
    D = 7000
    d = Doc("03-arrival", D, "#0c4a58")
    rnd = micro_bg(d, D, 21)
    agar(d, rnd)
    reticle(d)

    # the germs: many, and all small
    cast = [
        ("g0", 90, 612, 30, 0, "happy"), ("g1", 215, 640, 38, 3, "grin"), ("g2", 330, 620, 32, 4, "happy"),
        ("g3", 430, 655, 42, 1, "happy"), ("g4", 770, 625, 34, 2, "grin"), ("g5", 850, 660, 44, 3, "happy"),
        ("g6", 1100, 625, 36, 0, "happy"), ("g7", 1190, 660, 42, 4, "grin"), ("g8", 1020, 668, 30, 2, "happy"),
        ("g9", 700, 618, 28, 3, "grin"),
    ]
    ids = []
    for nm, x, y, r, kind, face in cast:
        germ(d, nm, x, y, r, kind, face)
        d.pivot(nm, 0.5, 1.0)
        ids.append((nm, x))
    germ(d, "gerald", 960, 640, 66, 1, "grin")
    d.pivot("gerald", 0.5, 1.0)
    ids.append(("gerald", 960))
    for i, (nm, x) in enumerate(ids):
        d.cycle(nm, "translate-y", 0, -9, 1100 + 110 * i, start=i * 90)
        blink(d, [f"{nm}_eyes"], [1900 + 170 * i, 5600])
    # arrival: comet trail, Pip drops in, impact
    d.gradient("trail", [(0, "#ffffff00"), (1, "#ffffffee")], x=530, y=-420, w=70, h=520)
    d.blend("trail", "screen")
    d.effect("trail", "gaussian-blur", radius=12)
    d.key("trail", "translate-y", 0, -200)
    d.key("trail", "translate-y", 700, -200)
    d.key("trail", "translate-y", 1400, 560, "ease-in-quad")
    d.key("trail", "opacity", 0, 0)
    d.key("trail", "opacity", 760, 0.9)
    d.key("trail", "opacity", 1400, 0.9)
    d.key("trail", "opacity", 1700, 0)
    pip(d, "pip", 565, 690, 2.5, crown=False)
    d.glow("pip_orb", "#7df3ff", 14)
    d.pivot("pip", 0.5, 1.0)
    d.key("pip", "translate-y", 0, -900)
    d.key("pip", "translate-y", 700, -900)
    d.key("pip", "translate-y", 1400, 0, "ease-in-quad")
    d.key("pip", "rotation", 700, 8)
    d.key("pip", "rotation", 1400, 0)
    d.key("pip", "scale-y", 1400, 1)
    d.key("pip", "scale-y", 1480, 0.78, "ease-out")
    d.key("pip", "scale-y", 1700, 1.1, "ease-out-quad")
    d.key("pip", "scale-y", 1950, 1)
    d.key("pip", "scale-x", 1400, 1)
    d.key("pip", "scale-x", 1480, 1.18, "ease-out")
    d.key("pip", "scale-x", 1950, 1)
    d.key("pip_armL", "rotation", 0, 160)
    d.key("pip_armL", "rotation", 1400, 150)
    d.key("pip_armL", "rotation", 1900, 0, "ease-out")
    # shock ripples where he lands
    for i in range(3):
        nm = d.ell(f"ripple{i}", 565, 694, 100, 26, "#00000000", stroke="#fff6cf", sw=5)
        t0 = 1400 + i * 170
        d.key(nm, "opacity", 0, 0)
        d.key(nm, "opacity", t0, 0.9)
        d.key(nm, "opacity", t0 + 900, 0)
        d.key(nm, "scale", t0, 0.3)
        d.key(nm, "scale", t0 + 900, 5, "ease-out")
    blink(d, ["pip_eyeL", "pip_eyeR"], [2600, 5400])
    talk(d, "pip_mouth", 3900, 5100, 140)
    # germs recoil, then bow
    for i, (nm, x) in enumerate(ids):
        side = 1 if x < 565 else -1
        d.key(nm, "scale", 1400, 1)
        d.key(nm, "scale", 1550, 1.22, "ease-out-back")
        d.key(nm, "scale", 2100, 1.0)
        d.key(nm, "rotation", 4300, 0)
        d.key(nm, "rotation", 4800 + 60 * i, 38 * side, "ease-out")
        d.key(f"{nm}_eyes", "scale", 1400, 1)
        d.key(f"{nm}_eyes", "scale", 1550, 1.4, "ease-out-back")
        d.key(f"{nm}_eyes", "scale", 3000, 1)
    talk(d, "gerald_mouth", 2150, 3700, 150)
    bubble(d, "sayGerald", "Look at him!\nSo... TALL!", 1085, 440, 2100, 3900, 38)
    bubble(d, "sayPip", "...Tall?", 640, 340, 3900, 4900, 48)
    bubble(d, "sayPip2", "I could\nget used to this.", 705, 330, 5000, 7000, 38)
    talk(d, "pip_mouth", 5100, 6300, 140)
    # Pip puffs up with pride
    d.key("pip", "scale", 4700, 1)
    d.key("pip", "scale", 5200, 1.07, "ease-out-back")
    d.key("pip_staffG", "rotation", 4800, 0)
    d.key("pip_staffG", "rotation", 5300, 10, "ease-out-back")
    vignette(d, "#000000a0", 0.62)
    narrate(d, "narr", "Somewhere very, very small...", 150, 1900, y=60)
    for b in ("sayGerald", "sayPip", "sayPip2"):
        d.ops.append({"type": "top", "target": b})
    return d


SCENES = [council, shrink, arrival]


def build_all(directory: str) -> list[str]:
    paths = []
    for make in SCENES:
        doc = make()
        print(f"building {doc.name} ...", flush=True)
        paths.append(doc.build(directory))
    return paths
