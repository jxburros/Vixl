"""Scenes 4-8 of "The Germ King": coronation, march, sneeze, aftermath, title."""
from __future__ import annotations

import math
import random

from characters import GOLD, crown_parts, elder, germ, pip
from scenes import (INK, PAPER, agar, blink, bubble, confetti, hall_bench, hall_scenery, micro_bg, narrate,
                    reticle, sparkle_field, talk, vignette)
from vixlkit import Doc, text_width

KINDS = [0, 1, 2, 3, 4]
FACES = ["happy", "grin", "happy", "grin", "happy"]


def bob(d: Doc, name: str, amp: float, period: int, start: int = 0, end: int | None = None, tilt: float = 0):
    d.cycle(name, "translate-y", 0, -amp, period, start=start, end=end)
    if tilt:
        d.cycle(name, "rotation", -tilt, tilt, period * 2, start=start, end=end)


def crowd(d: Doc, prefix: str, specs, D: int, hop_from: int | None = None, seed: int = 5):
    """specs: (x, y, r) tuples. Germs bob gently, and hop wildly from ``hop_from``."""
    rnd = random.Random(seed)
    names = []
    for i, (x, y, r) in enumerate(specs):
        nm = f"{prefix}{i}"
        germ(d, nm, x, y, r, KINDS[i % 5], FACES[(i + 2) % 5])
        d.pivot(nm, 0.5, 1.0)
        blink(d, [f"{nm}_eyes"], [1500 + 230 * i, 4300 + 170 * i])
        if hop_from is None:
            bob(d, nm, 8, 1100 + 90 * i, start=i * 70)
        else:
            bob(d, nm, 8, 1100 + 90 * i, start=i * 70, end=hop_from)
            t = hop_from + rnd.randint(0, 300)
            d.cycle(nm, "translate-y", 0, -r * 1.1, 420 + rnd.randint(0, 160), start=t, end=D, easing="ease-out-quad")
            d.cycle(nm, "rotation", -10, 10, 560 + rnd.randint(0, 200), start=t, end=D)
        names.append(nm)
    return names


# ------------------------------------------------------------------------ scene 4
def coronation() -> Doc:
    D = 7000
    d = Doc("04-coronation", D, "#0c4a58")
    rnd = micro_bg(d, D, 33, centre="#46d8bd", mid="#1f9a9a", edge="#0b4452")
    # sunburst behind the throne
    cx, cy = 640, 360
    rays = []
    for i in range(14):
        a0 = i * 2 * math.pi / 14
        rays.append(d.poly(f"ray{i}", [(cx, cy), (cx + 1000 * math.cos(a0), cy + 1000 * math.sin(a0)),
                                       (cx + 1000 * math.cos(a0 + 0.12), cy + 1000 * math.sin(a0 + 0.12))],
                           "#fff2a8", opacity=0.16))
    d.group("rays", rays)
    d.key("rays", "rotation", 0, 0)
    d.key("rays", "rotation", D, 40, "linear")
    agar(d, rnd)
    # bunting
    pts = []
    for k0 in range(3):
        ax, bx = k0 * 426.6, (k0 + 1) * 426.6
        for j in range(8):
            t = j / 7
            x = (1 - t) ** 2 * ax + 2 * (1 - t) * t * ((ax + bx) / 2) + t ** 2 * bx
            y = (1 - t) ** 2 * 30 + 2 * (1 - t) * t * 120 + t ** 2 * 30
            pts.append((x, y))
    d.line("buntingLine", pts, "#ffffff", 3, smooth=True, opacity=0.9)
    colors = ["#ff6f91", "#ffd84a", "#7df3ff", "#9bff8a", "#c58bff"]
    for i, (x, y) in enumerate(pts):
        if i % 8 in (0, 7):
            continue
        d.poly(f"flag{i}", [(x - 17, y), (x + 17, y), (x, y + 44)], colors[i % 5], stroke="#ffffff", sw=1.5)
    # sugar-cube steps and carpet
    for i, (x, y, w) in enumerate(((350, 600, 580), (450, 540, 380), (545, 480, 190))):
        d.rect(f"step{i}", x, y, w, 64, "#fff4e2", r=12, stroke="#d7c3a0", sw=3)
        d.rect(f"stepLight{i}", x + 10, y + 8, w - 20, 10, "#ffffff", r=5, opacity=0.8)
    d.poly("carpet", [(600, 480), (680, 480), (800, 664), (480, 664)], "#b8324a", stroke=GOLD, sw=3)

    # Gerald, the crowd, and Pip
    germ(d, "gerald", 430, 668, 58, 1, "grin")
    d.pivot("gerald", 0.5, 1.0)
    bob(d, "gerald", 8, 1000)
    left = [(70, 628, 28), (170, 668, 40), (250, 632, 30), (330, 670, 36), (150, 600, 24), (260, 600, 26)]
    right = [(980, 628, 30), (900, 668, 38), (1080, 668, 42), (1180, 630, 28), (1000, 600, 24), (1130, 600, 26)]
    crowd(d, "cl", left, D, hop_from=4100, seed=3)
    crowd(d, "cr", right, D, hop_from=4150, seed=4)
    pip(d, "pip", 640, 484, 2.2, crown=True)
    d.glow("pip_orb", "#7df3ff", 16)
    d.pivot("pip", 0.5, 1.0)
    d.pivot("pip_crownG", 0.5, 1.0)
    # crown descends
    d.key("pip_crownG", "opacity", 0, 0)
    d.key("pip_crownG", "opacity", 3500, 0)
    d.key("pip_crownG", "opacity", 3650, 1)
    d.key("pip_crownG", "translate-y", 0, -560)
    d.key("pip_crownG", "translate-y", 3500, -560)
    d.key("pip_crownG", "translate-y", 4000, 0, "ease-in-quad")
    d.key("pip_crownG", "translate-y", 4120, -16, "ease-out")
    d.key("pip_crownG", "translate-y", 4260, 0, "ease-in")
    # Pip reacts
    blink(d, ["pip_eyeL", "pip_eyeR"], [900, 2300, 5200])
    talk(d, "pip_mouth", 2650, 3900, 150)
    talk(d, "pip_mouth", 4300, 6600, 130)
    d.key("pip", "scale-y", 3950, 1)
    d.key("pip", "scale-y", 4040, 0.88, "ease-out")
    d.key("pip", "scale-y", 4200, 1.06, "ease-out-quad")
    d.key("pip", "scale-y", 4450, 1)
    d.key("pip_armL", "rotation", 3900, 0)
    d.key("pip_armL", "rotation", 4300, 135, "ease-out-back")
    d.cycle("pip_armL", "rotation", 115, 150, 320, start=4300, end=D)
    d.key("pip_staffG", "rotation", 3900, 0)
    d.key("pip_staffG", "rotation", 4300, -10, "ease-out-back")
    d.key("pip_halo", "scale", 3900, 1)
    d.key("pip_halo", "scale", 4100, 2.6, "ease-out")
    d.key("pip_halo", "scale", 4800, 1.4)
    # sparkle burst where the crown lands
    for i in range(14):
        ang = 2 * math.pi * i / 14
        nm = d.star(f"burst{i}", 640, 300, 26, "#ffd84a" if i % 2 else "#ffffff", points=4, inner=0.3)
        d.key(nm, "opacity", 0, 0)
        d.key(nm, "opacity", 4000, 1)
        d.key(nm, "opacity", 4700, 0)
        d.key(nm, "translate-x", 4000, 0)
        d.key(nm, "translate-x", 4700, 230 * math.cos(ang), "ease-out")
        d.key(nm, "translate-y", 4000, 0)
        d.key(nm, "translate-y", 4700, 230 * math.sin(ang), "ease-out")
        d.key(nm, "rotation", 4000, 0)
        d.key(nm, "rotation", 4700, 180)
    confetti(d, "conf", 70, 9, 4000, 250, 1030, y0=-40, fall=800, dur=2600)
    # dialogue
    bubble(d, "sayGerald", "Lead us, Tall One!\nThe Giants must pay!", 300, 468, 300, 2500, 36, tail="right")
    bubble(d, "sayPip", "Giants?\nOh, I know a few.", 905, 225, 2650, 4100, 38)
    d.text("hail", "ALL HAIL KING PIP!", 640 - text_width("ALL HAIL KING PIP!", 84) / 2, 70, 84, GOLD)
    d.text_stroke("hail", 12, "#4a2fa8")
    d.key("hail", "opacity", 0, 0)
    d.key("hail", "opacity", 4300, 0)
    d.key("hail", "opacity", 4400, 1)
    d.key("hail", "scale", 4300, 0.3)
    d.key("hail", "scale", 4750, 1, "ease-out-back")
    d.cycle("hail", "rotation", -2.5, 2.5, 700, start=4750, end=D)
    vignette(d, "#000000a0", 0.62)
    for b in ("sayGerald", "sayPip", "hail"):
        d.ops.append({"type": "top", "target": b})
    return d


# ------------------------------------------------------------------------ scene 5
def march() -> Doc:
    D = 5500
    d = Doc("05-march", D, "#2a0f3e")
    rnd = micro_bg(d, D, 41, centre="#e0527a", mid="#8c2a6a", edge="#240c36", rods=7)
    # the sleeping giant rises beyond the horizon
    elder(d, "giant", "highbrow", 1070, 330, 4.2)
    d.key("giant", "translate-y", 0, 1000)
    d.key("giant", "translate-y", 1800, 1000)
    d.key("giant", "translate-y", 3600, 0, "ease-out-cubic")
    for part in ("whiteL", "whiteR"):
        d.key(f"giant_{part}", "scale-y", 0, 0.08)
    d.key("giant_pupils", "scale-y", 0, 0.05)
    d.key("giant_mouth", "visible", 0, False)
    for i, t in enumerate(range(2600, D, 900)):
        d.key("giant_mouth", "visible", t, True)
        d.key("giant_mouth", "visible", t + 500, False)
    d.text("zzz", "Z z z", 930, 140, 54, "#ffffff")
    d.opacity("zzz", 0)
    d.key("zzz", "opacity", 3300, 0)
    d.key("zzz", "opacity", 3700, 0.9)
    d.cycle("zzz", "translate-y", 0, -20, 1200, start=3700, end=D)
    agar(d, rnd, rim="#6a2a5a", fill="#a8466c", dots="#7c2c58")
    # ground marks scroll past: the army is moving
    for i in range(26):
        x = rnd.uniform(0, 2800)
        nm = d.ell(f"mark{i}", x, rnd.uniform(650, 710), rnd.uniform(26, 60), rnd.uniform(8, 16), "#5c1f4c", opacity=0.55)
        d.key(nm, "translate-x", 0, 0)
        d.key(nm, "translate-x", D, -1500, "linear")
    # the marching army
    front = [(130, 670, 40), (300, 672, 44), (700, 670, 40), (870, 672, 46), (1010, 670, 40), (1170, 672, 42)]
    back = [(60, 628, 32), (230, 630, 30), (400, 628, 34), (680, 630, 30), (800, 628, 34), (950, 630, 30), (1100, 628, 32),
            (1230, 630, 30)]
    for i, (x, y, r) in enumerate(front + back):
        nm = f"m{i}"
        germ(d, nm, x, y, r, KINDS[i % 5], "grin" if i % 3 else "evil")
        d.pivot(nm, 0.5, 1.0)
        bob(d, nm, 14, 360, start=(i % 4) * 90, tilt=4)
    # flags
    for i, x in enumerate((90, 330, 740)):
        d.rect(f"pole{i}", x, 430, 7, 190, "#8a5a2b")
        d.poly(f"flagCloth{i}", [(x + 7, 436), (x + 100, 462), (x + 7, 492)], "#d12f4f", stroke=GOLD, sw=3)
        d.group(f"banner{i}", [f"pole{i}", f"flagCloth{i}"])
        d.pivot(f"banner{i}", 0.05, 1.0)
        d.cycle(f"banner{i}", "rotation", -5, 5, 700 + 90 * i, start=0)
        bob(d, f"banner{i}", 14, 360, start=i * 90, tilt=0)
    germ(d, "gerald", 560, 650, 92, 1, "evil")
    d.pivot("gerald", 0.5, 1.0)
    bob(d, "gerald", 12, 420, tilt=2)
    pip(d, "pip", 560, 564, 1.7, crown=True)
    d.glow("pip_orb", "#7df3ff", 14)
    d.pivot("pip", 0.5, 1.0)
    bob(d, "pip", 12, 420, tilt=2)
    d.key("pip_staffG", "rotation", 0, 0)
    d.key("pip_staffG", "rotation", 500, 28, "ease-out-back")
    d.key("pip_staffG", "rotation", 2600, 28)
    d.key("pip_staffG", "rotation", 3300, 0, "ease-in-out")
    d.key("pip_halo", "scale", 400, 1)
    d.key("pip_halo", "scale", 800, 2.2, "ease-out")
    d.key("pip_halo", "scale", 2600, 1.4)
    blink(d, ["pip_eyeL", "pip_eyeR"], [2400, 4700])
    talk(d, "pip_mouth", 500, 2300, 140)
    talk(d, "pip_mouth", 3500, 5200, 150)
    bubble(d, "sayPip1", "TO THE COUNCIL!", 640, 330, 500, 2500, 56)
    bubble(d, "sayPip2", "Time to get...\nSERIOUS.", 560, 280, 3500, 5400, 48)
    vignette(d, "#000000a0", 0.6)
    narrate(d, "narr", "Soon, an army was on the march.", 100, 1900)
    for b in ("sayPip1", "sayPip2", "zzz"):
        d.ops.append({"type": "top", "target": b})
    return d


# ------------------------------------------------------------------------ scene 6
def sneeze() -> Doc:
    D = 5200
    d = Doc("06-sneeze", D, "#1d1a3a")
    d.gradient("wall", [(0, "#241a3a"), (1, "#3c2f5a")])
    d.rect("pillow", 120, 30, 1040, 640, "#e9eeff", r=120, stroke="#aab4d8", sw=6)
    d.gradient("pillowShade", [(0, "#8794c433"), (1, "#8794c400")], direction="horizontal", x=120, y=30, w=300, h=640)
    d.gradient("blanketGlow", [(0, "#00000000"), (1, "#00000066")], y=500, h=220)
    elder(d, "big", "highbrow", 640, 300, 7.2)
    d.pivot("big", 0.5, 0.45)
    # asleep, then waking
    for part in ("whiteL", "whiteR"):
        d.key(f"big_{part}", "scale-y", 0, 0.1)
        d.key(f"big_{part}", "scale-y", 1500, 0.1)
        d.key(f"big_{part}", "scale-y", 1800, 0.8, "ease-out")
        d.key(f"big_{part}", "scale-y", 3000, 0.8)
        d.key(f"big_{part}", "scale-y", 3300, 0.12, "ease-in")
        d.key(f"big_{part}", "scale-y", 4400, 0.12)
        d.key(f"big_{part}", "scale-y", 4900, 0.7)
    d.key("big_pupils", "scale-y", 0, 0.1)
    d.key("big_pupils", "scale-y", 1500, 0.1)
    d.key("big_pupils", "scale-y", 1800, 1, "ease-out")
    d.key("big_pupils", "scale-y", 3000, 1)
    d.key("big_pupils", "scale-y", 3300, 0.1, "ease-in")
    d.key("big_pupils", "scale-y", 4400, 0.1)
    d.key("big_pupils", "scale-y", 4900, 1)
    d.cycle("big_pupils", "translate-x", -10, 10, 500, start=1800, end=3000)
    # snoring, twitching nose
    d.key("big_mouth", "visible", 0, False)
    for t in range(300, 1500, 600):
        d.key("big_mouth", "visible", t, True)
        d.key("big_mouth", "visible", t + 320, False)
    d.key("big_mouth", "visible", 3380, True)
    d.key("big_mouth", "visible", D, True)
    d.pivot("big_nose", 0.5, 0.5)
    d.pivot("big_noseTip", 0.5, 0.5)
    d.cycle("big_nose", "scale", 1.0, 1.06, 160, start=1300, end=3300)
    d.cycle("big_noseTip", "scale", 1.0, 1.25, 160, start=1300, end=3300)
    # head tilts back, then snaps forward
    d.key("big", "rotation", 0, 0)
    d.key("big", "rotation", 1800, 0)
    d.key("big", "rotation", 3200, -6, "ease-in-out")
    d.key("big", "rotation", 3380, 9, "ease-in")
    d.key("big", "rotation", 3800, 0, "ease-out")
    d.key("big", "scale", 1800, 1)
    d.key("big", "scale", 3200, 1.07, "ease-in-out")
    d.key("big", "scale", 3400, 0.96, "ease-in")
    d.key("big", "scale", 3900, 1)
    for i, t in enumerate(range(3420, 4100, 70)):  # shake
        d.key("big", "translate-x", t, (-1) ** i * 18)
        d.key("big", "translate-y", t, (-1) ** i * 12)
    d.key("big", "translate-x", 4200, 0)
    d.key("big", "translate-y", 4200, 0)

    # tiny Pip and the germ army, tickling the nose
    pip(d, "pip", 640, 446, 1.4, crown=True)
    d.glow("pip_orb", "#7df3ff", 12)
    d.pivot("pip", 0.5, 0.5)
    germs = [("gz0", 560, 440, 20, 0), ("gz1", 720, 442, 22, 3), ("gz2", 600, 372, 18, 2), ("gz3", 690, 366, 18, 4),
             ("gz4", 520, 330, 16, 1), ("gz5", 760, 334, 16, 0), ("gz6", 640, 520, 22, 3)]
    for nm, x, y, r, kind in germs:
        germ(d, nm, x, y, r, kind, "grin")
        d.pivot(nm, 0.5, 0.5)
        d.cycle(nm, "translate-y", 0, -6, 600 + 70 * kind, start=0, end=3300)
    d.cycle("pip_staffG", "rotation", -14, 20, 300, start=300, end=3300)
    talk(d, "pip_mouth", 200, 1500, 150)
    bubble(d, "sayPip", "Tickle, tickle...", 400, 330, 200, 1700, 36, tail="right")
    # the build-up
    bubble(d, "ah1", "Ah...", 1060, 140, 1750, 2350, 60)
    bubble(d, "ah2", "Ahhh...", 1040, 130, 2350, 3000, 78)
    bubble(d, "ah3", "AAAHHH...", 1030, 120, 3000, 3420, 100)
    # blast: spray, speed lines, flash, and the shout
    rnd = random.Random(13)
    for i in range(44):
        r = rnd.uniform(8, 24)
        nm = d.ell(f"drop{i}", 640, 540, r, r * 1.2, "#cfeeff", stroke="#7fb8dc", sw=1.5)
        a = rnd.uniform(-0.9, 0.9) + math.pi / 2
        dist = rnd.uniform(500, 1100)
        d.key(nm, "opacity", 0, 0)
        d.key(nm, "opacity", 3380, 1)
        d.key(nm, "opacity", 4300, 0)
        d.key(nm, "translate-x", 3380, 0)
        d.key(nm, "translate-x", 4300, dist * math.cos(a) * 1.4, "ease-out")
        d.key(nm, "translate-y", 3380, 0)
        d.key(nm, "translate-y", 4300, dist * math.sin(a) * 0.9 + 200, "ease-out")
    for i in range(22):
        a = 2 * math.pi * i / 22
        x0, y0 = 640 + 380 * math.cos(a), 360 + 300 * math.sin(a)
        x1, y1 = 640 + 900 * math.cos(a), 360 + 700 * math.sin(a)
        w = 14
        nm = d.poly(f"speed{i}", [(x0, y0), (x1 - w * math.sin(a), y1 + w * math.cos(a)), (x1 + w * math.sin(a), y1 - w * math.cos(a))],
                    "#ffffff", opacity=0.8)
        d.key(nm, "opacity", 0, 0)
        d.key(nm, "opacity", 3400, 0.85)
        d.key(nm, "opacity", 4100, 0)
    # Pip and germs are blown away
    for nm, dx, dy, rot in (("pip", 900, 340, 900), ("gz0", -700, 420, -700), ("gz1", 800, 520, 600),
                            ("gz2", -900, -200, -800), ("gz3", 900, -260, 700), ("gz4", -600, -500, -500),
                            ("gz5", 700, -520, 500), ("gz6", 120, 760, 400)):
        d.key(nm, "translate-x", 3300, 0)
        d.key(nm, "translate-x", 4400, dx, "ease-out")
        d.key(nm, "translate-y", 3300, 0)
        d.key(nm, "translate-y", 4400, dy, "ease-out")
        d.key(nm, "rotation", 3300, 0)
        d.key(nm, "rotation", 4400, rot, "ease-out")
        d.key(nm, "scale", 3300, 1)
        d.key(nm, "scale", 4400, 0.4, "ease-out")
    d.text("choo", "AH-CHOO!!!", 640 - text_width("AH-CHOO!!!", 168) / 2, 50, 168, "#ffd84a")
    d.text_stroke("choo", 20, "#c8312d")
    d.rotate("choo", -6)
    d.key("choo", "opacity", 0, 0)
    d.key("choo", "opacity", 3400, 0)
    d.key("choo", "opacity", 3460, 1)
    d.key("choo", "scale", 3400, 0.3)
    d.key("choo", "scale", 3700, 1.1, "ease-out-back")
    d.key("choo", "scale", 4400, 1.1, "linear")
    d.key("choo", "opacity", 4700, 1)
    d.key("choo", "opacity", 5100, 0)
    d.solid("flash", "#ffffff")
    d.key("flash", "opacity", 0, 0)
    d.key("flash", "opacity", 3370, 0)
    d.key("flash", "opacity", 3430, 0.9)
    d.key("flash", "opacity", 3800, 0)
    vignette(d, "#000000a8", 0.55)
    narrate(d, "narr", "Meanwhile, one very tall sleeper...", 100, 1700, y=14, size=44)
    for b in ("sayPip", "ah1", "ah2", "ah3", "choo", "flash"):
        d.ops.append({"type": "top", "target": b})
    return d


# ------------------------------------------------------------------------ scene 7
def aftermath() -> Doc:
    D = 9500
    d = Doc("07-aftermath", D, "#2b2142")
    hall_scenery(d)
    elder(d, "e1", "tallworth", 290, 292, 2.0, sick=True)
    elder(d, "e2", "longshanks", 640, 292, 2.0, sick=True)
    elder(d, "e3", "highbrow", 990, 292, 2.0, sick=True, therm=True)
    hall_bench(d, poster=False)
    # the army on the bench top
    rnd = random.Random(8)
    specs = [(120, 404, 24), (210, 408, 28), (330, 404, 22), (560, 408, 28), (700, 404, 24), (800, 408, 30),
             (900, 404, 22), (1160, 408, 28), (1230, 404, 24), (60, 406, 20)]
    crowd(d, "bz", specs, D, hop_from=2200, seed=2)
    germ(d, "gerald", 600, 410, 44, 1, "grin")
    d.pivot("gerald", 0.5, 1.0)
    bob(d, "gerald", 10, 700)
    pip(d, "pip", 465, 404, 1.8, crown=True)
    d.glow("pip_orb", "#7df3ff", 14)
    d.pivot("pip", 0.5, 1.0)
    d.glow("pip_crownG", "#ffd84a", 10)
    # sick council: slumped, sniffling, looking down at Pip for the first time
    for i, e in enumerate(("e1", "e2", "e3")):
        d.cycle(f"{e}_pupils", "translate-y", 5, 8, 900, start=0)
        d.key(f"{e}_pupils", "translate-x", 0, 0)
        d.cycle(f"{e}", "translate-y", 0, 5, 1700 + 220 * i, start=i * 150)
        d.cycle(f"{e}_sweat1", "translate-y", 0, 46, 1500 + 200 * i, start=0, easing="ease-in")
        d.cycle(f"{e}_sweat2", "translate-y", 0, 46, 1800 + 150 * i, start=300, easing="ease-in")
    d.key("e2_pupils", "translate-x", 1800, 0)
    d.key("e2_pupils", "translate-x", 2300, -9, "ease-out")
    d.key("e3_pupils", "translate-x", 1800, 0)
    d.key("e3_pupils", "translate-x", 2300, -9, "ease-out")
    d.key("e1_pupils", "translate-x", 1800, 0)
    d.key("e1_pupils", "translate-x", 2300, 9, "ease-out")
    # sneezes
    for e, t in (("e1", 400), ("e3", 800), ("e2", 1200)):
        d.key(e, "scale", t - 50, 1)
        d.key(e, "scale", t + 80, 1.07, "ease-out")
        d.key(e, "scale", t + 300, 1)
        talk(d, f"{e}_mouth", t, t + 400, 100)
    bubble(d, "ach1", "Achoo!", 450, 150, 400, 1300, 36)
    bubble(d, "ach3", "ACHOO!", 1135, 150, 800, 1700, 36)
    bubble(d, "ach2", "*sniff*", 830, 140, 1250, 1900, 32)
    # dialogue
    talk(d, "e2_mouth", 2100, 4100, 170)
    bubble(d, "sayE2", "King Pip... we take you\nVERY seriously now.", 830, 150, 2100, 4300, 36)
    talk(d, "e3_mouth", 4400, 5700, 170)
    bubble(d, "sayE3", "Please. Make it stop.", 1090, 160, 4400, 5900, 34)
    talk(d, "pip_mouth", 6100, 7700, 140)
    bubble(d, "sayPip1", "Now who's too small?", 720, 520, 6100, 7900, 46, tail="up-left")
    talk(d, "pip_mouth", 8000, 9000, 150)
    bubble(d, "sayPip2", "...Bless you.", 660, 520, 8000, 9500, 52, tail="up-left")
    d.key("pip_eyeL", "scale-y", 8300, 1)
    d.key("pip_eyeL", "scale-y", 8400, 0.08)
    d.key("pip_armL", "rotation", 6000, 0)
    d.key("pip_armL", "rotation", 6400, 120, "ease-out-back")
    d.cycle("pip_armL", "rotation", 100, 135, 400, start=6400, end=7900)
    d.key("pip_armL", "rotation", 8300, 0, "ease-in-out")
    d.key("pip_halo", "scale", 8000, 1)
    d.key("pip_halo", "scale", 8300, 3, "ease-out")
    d.key("pip_halo", "scale", 9300, 1.6)
    blink(d, ["pip_eyeR"], [3000, 5000, 6900])
    # a final synchronised sneeze
    for e in ("e1", "e2", "e3"):
        d.key(e, "translate-x", 8900, 0)
        for j, t in enumerate(range(8920, 9300, 50)):
            d.key(e, "translate-x", t, (-1) ** j * 10)
        d.key(e, "translate-x", 9350, 0)
    vignette(d, "#000000a0", 0.55)
    for b in ("ach1", "ach2", "ach3", "sayE2", "sayE3", "sayPip1", "sayPip2"):
        d.ops.append({"type": "top", "target": b})
    return d


# ------------------------------------------------------------------------ scene 8
def title() -> Doc:
    D = 4500
    d = Doc("08-title", D, "#1c1240")
    d.gradient("sky", [(0, "#150c33"), (0.7, "#3f2486"), (1, "#8a3f9c")])
    sparkle_field(d, "star", 60, 17, "#ffffff", area=(0, 0, 1280, 560), size=(3, 9), twinkle=1900)
    d.ell("moonGlow", 1040, 140, 260, 260, "#ffe9a8", opacity=0.10)
    d.rect("ground", 0, 640, 1280, 90, "#241550")
    # the title
    d.text("title", "THE GERM KING", 640 - text_width("THE GERM KING", 150) / 2, 250, 150, GOLD)
    d.text_stroke("title", 16, "#3a1f6e")
    d.key("title", "opacity", 0, 0)
    d.key("title", "opacity", 250, 0)
    d.key("title", "opacity", 400, 1)
    d.key("title", "scale", 250, 0.2)
    d.key("title", "scale", 900, 1, "ease-out-back")
    cn = crown_parts(d, "crown", 640, 244, 4.4)
    d.group("crownG", cn)
    d.pivot("crownG", 0.5, 1.0)
    d.glow("crownG", "#ffd84a", 14)
    d.key("crownG", "opacity", 0, 0)
    d.key("crownG", "opacity", 1000, 0)
    d.key("crownG", "opacity", 1100, 1)
    d.key("crownG", "translate-y", 0, -500)
    d.key("crownG", "translate-y", 1000, -500)
    d.key("crownG", "translate-y", 1500, 0, "ease-in-quad")
    d.key("crownG", "translate-y", 1620, -20, "ease-out")
    d.key("crownG", "translate-y", 1760, 0, "ease-in")
    d.text("sub", "a very small revenge", 640 - text_width("a very small revenge", 56) / 2, 450, 56, "#ffffff")
    d.key("sub", "opacity", 0, 0)
    d.key("sub", "opacity", 1900, 0)
    d.key("sub", "opacity", 2500, 1)
    d.key("sub", "translate-y", 1900, 24)
    d.key("sub", "translate-y", 2500, 0, "ease-out")
    d.text("madewith", "made with Vixl", 640 - text_width("made with Vixl", 28) / 2, 540, 28, "#cfc2ff")
    d.key("madewith", "opacity", 0, 0)
    d.key("madewith", "opacity", 2800, 0)
    d.key("madewith", "opacity", 3400, 0.8)
    # germs parade along the bottom, Pip waves
    for i in range(7):
        x = 90 + i * 150
        germ(d, f"p{i}", x, 656, 30 + (i % 3) * 4, KINDS[i % 5], FACES[i % 5])
        d.pivot(f"p{i}", 0.5, 1.0)
        d.cycle(f"p{i}", "translate-y", 0, -26, 520 + 40 * i, start=300 + i * 110, easing="ease-out-quad")
    pip(d, "pip", 1130, 676, 1.7, crown=True)
    d.pivot("pip", 0.5, 1.0)
    d.glow("pip_orb", "#7df3ff", 14)
    d.cycle("pip_armL", "rotation", 100, 140, 400, start=2300)
    d.key("pip_armL", "rotation", 0, 0)
    d.key("pip_armL", "rotation", 2300, 100)
    blink(d, ["pip_eyeL", "pip_eyeR"], [2600, 3800])
    return d


SCENES = [coronation, march, sneeze, aftermath, title]
