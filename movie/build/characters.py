"""Characters for "The Germ King", built from editable Vixl shapes.

Every part is its own layer; moving parts are grouped so a scene can animate
pivots (arms), blinks (eyes) and talking (mouth) by name.
"""
from __future__ import annotations

from vixlkit import Doc

SKIN = "#f4c9a1"
SKIN_SHADE = "#e8a48a"
OUTLINE = "#241446"
ROBE = "#7451d8"
ROBE_DARK = "#4a2fa8"
GOLD = "#ffd84a"
WHITE = "#f7f4ee"


# --------------------------------------------------------------------------- Pip
def pip(d: Doc, p: str, ox: float, oy: float, k: float, crown: bool = False):
    """Pip the wizard. (ox, oy) is the centre of his feet; ``k`` is pixels per unit
    (he is ~124 units tall, hat included). Returns the outer group name ``p``.

    Named parts: {p}_armL (pivoted at shoulder), {p}_staffG (pivoted at the hand),
    {p}_eyeL/{p}_eyeR (blink), {p}_mouth (visible = talking), {p}_orb, {p}_halo.
    """
    X = lambda v: ox + v * k
    Y = lambda v: oy + v * k
    S = lambda v: v * k
    ow = max(1.5, S(0.9))
    parts: list[str] = []

    # staff + glowing orb (own group so it can tilt when casting)
    staff = [
        d.rect(f"{p}_staff", X(21), Y(-96), S(4.4), S(96), "#8a5a2b", r=S(2), stroke="#4d3015", sw=ow),
        d.ell(f"{p}_halo", X(23.2), Y(-98), S(24), S(24), "#7df3ff", opacity=0.35),
        d.ell(f"{p}_orb", X(23.2), Y(-98), S(11), S(11), "#b9fbff", stroke="#3cc6d6", sw=ow),
    ]
    parts.append(d.group(f"{p}_staffG", staff))
    d.pivot(f"{p}_staffG", 0.5, 1.0)

    # boots, robe, hem, belt, emblem
    parts += [
        d.ell(f"{p}_bootL", X(-9), Y(-3), S(14), S(7), "#3a2a1a"),
        d.ell(f"{p}_bootR", X(9), Y(-3), S(14), S(7), "#3a2a1a"),
        d.poly(f"{p}_robe", [(X(-12), Y(-58)), (X(12), Y(-58)), (X(26), Y(-3)), (X(-26), Y(-3))],
               ROBE, stroke=OUTLINE, sw=ow),
        d.poly(f"{p}_robeShade", [(X(5), Y(-58)), (X(12), Y(-58)), (X(26), Y(-3)), (X(9), Y(-3))],
               ROBE_DARK, opacity=0.55),
        d.poly(f"{p}_hem", [(X(-24.6), Y(-9)), (X(24.6), Y(-9)), (X(26), Y(-3)), (X(-26), Y(-3))], GOLD),
        d.crect(f"{p}_belt", X(0), Y(-33), S(21), S(4.5), GOLD),
        d.crect(f"{p}_buckle", X(0), Y(-33), S(5), S(5.5), "#fff3b0", stroke="#a07a10", sw=max(1, S(0.5))),
        d.star(f"{p}_emblem", X(0), Y(-46), S(10), GOLD),
    ]

    # left arm (waves) — group pivoted at the shoulder
    arm = [
        d.poly(f"{p}_sleeveL", [(X(-17), Y(-57)), (X(-10), Y(-57)), (X(-15), Y(-34)), (X(-24), Y(-34))],
               ROBE, stroke=OUTLINE, sw=ow),
        d.ell(f"{p}_handL", X(-19.5), Y(-31.5), S(8), S(8), SKIN, stroke=OUTLINE, sw=ow),
    ]
    parts.append(d.group(f"{p}_armL", arm))
    d.ops.append({"type": "pivot", "target": f"{p}_armL", "value": [S(11.5), S(1.5)], "units": "px"})
    # right arm holds the staff
    parts += [
        d.poly(f"{p}_sleeveR", [(X(10), Y(-57)), (X(17), Y(-57)), (X(25), Y(-34)), (X(16), Y(-34))],
               ROBE, stroke=OUTLINE, sw=ow),
        d.ell(f"{p}_handR", X(23.2), Y(-31.5), S(8), S(8), SKIN, stroke=OUTLINE, sw=ow),
    ]

    # head
    parts += [
        d.ell(f"{p}_earL", X(-14.2), Y(-65), S(6), S(8), SKIN, stroke=OUTLINE, sw=ow),
        d.ell(f"{p}_earR", X(14.2), Y(-65), S(6), S(8), SKIN, stroke=OUTLINE, sw=ow),
        d.ell(f"{p}_head", X(0), Y(-66), S(29), S(28), SKIN, stroke=OUTLINE, sw=ow),
        d.poly(f"{p}_beard", [(X(-13.5), Y(-63)), (X(-15), Y(-52)), (X(-7), Y(-37)), (X(0), Y(-27)),
                              (X(7), Y(-37)), (X(15), Y(-52)), (X(13.5), Y(-63))],
               WHITE, stroke="#bdb7a8", sw=ow, smooth=True, tension=0.5),
        d.ell(f"{p}_mouth", X(0), Y(-58.5), S(8), S(6), "#5a1d2a"),
        d.ell(f"{p}_stacheL", X(-4.6), Y(-61.5), S(10), S(5), WHITE, stroke="#bdb7a8", sw=max(1, S(0.5)), rot=-14),
        d.ell(f"{p}_stacheR", X(4.6), Y(-61.5), S(10), S(5), WHITE, stroke="#bdb7a8", sw=max(1, S(0.5)), rot=14),
        d.ell(f"{p}_nose", X(0), Y(-65.8), S(8), S(6.5), SKIN_SHADE),
        d.ell(f"{p}_cheekL", X(-9.5), Y(-65), S(5.5), S(3.5), "#ff8fa0", opacity=0.45),
        d.ell(f"{p}_cheekR", X(9.5), Y(-65), S(5.5), S(3.5), "#ff8fa0", opacity=0.45),
    ]
    d.hide(f"{p}_mouth")
    for side, sx in (("L", -1), ("R", 1)):
        eye = [
            d.ell(f"{p}_eyeball{side}", X(sx * 6), Y(-71.2), S(5.2), S(6.6), "#2a2030"),
            d.ell(f"{p}_glint{side}", X(sx * 6 - 0.9), Y(-72.6), S(1.9), S(2.3), "#ffffff"),
        ]
        parts.append(d.group(f"{p}_eye{side}", eye))
    for side, sx in (("L", -1), ("R", 1)):
        parts.append(d.ell(f"{p}_brow{side}", X(sx * 6.6), Y(-77), S(8.5), S(2.6), WHITE, rot=-12 * sx,
                           stroke="#bdb7a8", sw=max(1, S(0.4))))

    # hat
    parts += [
        d.ell(f"{p}_brim", X(0), Y(-78.5), S(48), S(9), "#3b2490", stroke=OUTLINE, sw=ow),
        d.poly(f"{p}_hat", [(X(-17), Y(-79)), (X(-9), Y(-104)), (X(3), Y(-121)), (X(20), Y(-121)),
                            (X(10), Y(-111)), (X(13), Y(-94)), (X(17.5), Y(-79))],
               ROBE, stroke=OUTLINE, sw=ow),
        d.poly(f"{p}_hatShade", [(X(10), Y(-111)), (X(13), Y(-94)), (X(17.5), Y(-79)), (X(7), Y(-79)),
                                 (X(5), Y(-101))], ROBE_DARK, opacity=0.5),
        d.poly(f"{p}_band", [(X(-17.6), Y(-86)), (X(14.8), Y(-86)), (X(16), Y(-80)), (X(-17.8), Y(-80))], GOLD),
        d.star(f"{p}_hatStar", X(-1), Y(-98), S(10), GOLD),
    ]
    if crown:
        crown_names = crown_parts(d, f"{p}_crown", X(0), Y(-83.5), S(1.0))
        parts.append(d.group(f"{p}_crownG", crown_names))
    return d.group(p, parts)


def crown_parts(d: Doc, p: str, cx: float, cy: float, k: float):
    """A small gold crown sitting around the hat band (cx, cy = band centre)."""
    base = cy - 2 * k
    pts = [(cx - 15 * k, base), (cx - 17 * k, base - 13 * k), (cx - 9 * k, base - 6 * k),
           (cx - 4 * k, base - 17 * k), (cx, base - 8 * k), (cx + 4 * k, base - 17 * k),
           (cx + 9 * k, base - 6 * k), (cx + 17 * k, base - 13 * k), (cx + 15 * k, base)]
    ow = max(1.5, 0.9 * k)
    return [
        d.poly(f"{p}", pts, "#ffc928", stroke="#8a5a00", sw=ow),
        d.crect(f"{p}_rim", cx, base - 1.5 * k, 30.5 * k, 3.2 * k, "#ffe27a", stroke="#8a5a00", sw=ow),
        d.ell(f"{p}_gem1", cx, base - 12 * k, 3.6 * k, 3.6 * k, "#ff4f6d"),
        d.ell(f"{p}_gem2", cx - 11 * k, base - 8 * k, 3 * k, 3 * k, "#4fd8ff"),
        d.ell(f"{p}_gem3", cx + 11 * k, base - 8 * k, 3 * k, 3 * k, "#7dff8a"),
    ]


# ------------------------------------------------------------------------ elders
ELDERS = {
    "tallworth": dict(robe="#b03a48", trim=GOLD, hat="pointy", hat_col="#8f2a3a", beard="#cfd2d8",
                      beard_len=1.0, skin="#e9bf98", glasses=False),
    "longshanks": dict(robe="#2f8f8f", trim="#e8f6f2", hat="pointy", hat_col="#1f6b6e", beard=None,
                       beard_len=0, skin="#f0cdb0", glasses=True),
    "highbrow": dict(robe="#d8a22a", trim="#6b3f10", hat="miter", hat_col="#f3d36b", beard="#fffdf5",
                     beard_len=0.8, skin="#e3b48a", glasses=False),
}


SICK_SKIN = "#b9cf98"


def elder(d: Doc, p: str, kind: str, cx: float, cy: float, k: float = 2.0, sick: bool = False,
          therm: bool = False):
    """A very tall council member; (cx, cy) is the head centre, ``k`` pixels per unit
    (head 60x72 units). Named parts: {p}_mouth (visible = talking), {p}_pupils
    (translate-x to scan), {p}_head (group of the whole figure is ``p``)."""
    c = dict(ELDERS[kind])
    if sick:
        c["skin"] = SICK_SKIN
    X = lambda v: cx + v * k
    Y = lambda v: cy + v * k
    S = lambda v: v * k
    ow = max(2.0, S(0.9))
    parts: list[str] = []

    # body, collar, emblem
    parts += [
        d.poly(f"{p}_robe", [(X(-38), Y(60)), (X(38), Y(60)), (X(100), Y(120)), (X(120), Y(300)),
                             (X(-120), Y(300)), (X(-100), Y(120))], c["robe"], stroke=OUTLINE, sw=ow),
        d.poly(f"{p}_collar", [(X(-38), Y(60)), (X(0), Y(120)), (X(38), Y(60)), (X(48), Y(66)), (X(0), Y(140)),
                               (X(-48), Y(66))], c["trim"], stroke=OUTLINE, sw=max(1, ow * 0.6)),
        d.star(f"{p}_emblem", X(0), Y(170), S(30), c["trim"], points=6, inner=0.5),
    ]
    if c["hat"] == "pointy" and kind == "longshanks":
        # silver hair bun behind the head
        parts += [d.ell(f"{p}_bun", X(0), Y(-48), S(40), S(30), "#e9e9ee", stroke="#b8b8c4", sw=ow)]
    # head
    parts += [
        d.ell(f"{p}_earL", X(-30), Y(4), S(10), S(16), c["skin"], stroke=OUTLINE, sw=ow),
        d.ell(f"{p}_earR", X(30), Y(4), S(10), S(16), c["skin"], stroke=OUTLINE, sw=ow),
        d.ell(f"{p}_head", X(0), Y(0), S(60), S(72), c["skin"], stroke=OUTLINE, sw=ow),
    ]
    if c["beard"]:
        bl = c["beard_len"]
        parts.append(d.poly(f"{p}_beard",
                            [(X(-30), Y(14)), (X(-36), Y(48 * bl + 12)), (X(-24), Y(100 * bl + 20)),
                             (X(0), Y(150 * bl + 20)), (X(24), Y(100 * bl + 20)), (X(36), Y(48 * bl + 12)),
                             (X(30), Y(14))],
                            c["beard"], stroke="#9aa0ab", sw=ow, smooth=True, tension=0.5))
    parts += [
        d.ell(f"{p}_mouth", X(0), Y(33), S(16), S(11), "#5a1d2a", stroke=OUTLINE, sw=max(1, ow * 0.7)),
        d.ell(f"{p}_nose", X(0), Y(9), S(15), S(22), c["skin"], stroke=OUTLINE, sw=max(1, ow * 0.7)),
        d.ell(f"{p}_noseTip", X(0), Y(16), S(12), S(9), "#ff3b3b" if sick else "#e08a7a",
              opacity=0.95 if sick else 0.8),
    ]
    if sick:
        parts += [
            d.ell(f"{p}_noseRed", X(0), Y(11), S(17), S(22), "#ff5a4f", opacity=0.55),
            d.ell(f"{p}_bagL", X(-14), Y(1), S(18), S(6), "#8b6aa6", opacity=0.55),
            d.ell(f"{p}_bagR", X(14), Y(1), S(18), S(6), "#8b6aa6", opacity=0.55),
            d.ell(f"{p}_sweat1", X(-35), Y(-24), S(7), S(10), "#8fd8ff", stroke="#4a9ccc", sw=max(1, ow * 0.4)),
            d.ell(f"{p}_sweat2", X(36), Y(-30), S(7), S(10), "#8fd8ff", stroke="#4a9ccc", sw=max(1, ow * 0.4)),
        ]
    d.hide(f"{p}_mouth")
    if c["beard"]:
        for side, sx in (("L", -1), ("R", 1)):
            parts.append(d.ell(f"{p}_stache{side}", X(sx * 9), Y(26), S(22), S(10), c["beard"],
                               stroke="#9aa0ab", sw=max(1, ow * 0.6), rot=sx * 12))
    else:
        parts.append(d.line(f"{p}_lips", [(X(-8), Y(31)), (X(0), Y(33)), (X(8), Y(31))], "#8a3a3a", sw=max(2, S(1.6))))

    if therm:
        parts += [
            d.poly(f"{p}_therm", [(X(2), Y(33)), (X(52), Y(16)), (X(54), Y(22)), (X(4), Y(39))], "#f4fbff",
                   stroke="#6a7a88", sw=max(1.5, ow * 0.6)),
            d.line(f"{p}_thermHg", [(X(8), Y(34)), (X(44), Y(21.5))], "#e8352e", sw=max(2, S(1.4))),
        ]
    # eyes: white, pupils (scan), heavy lids
    pupils: list[str] = []
    for side, sx in (("L", -1), ("R", 1)):
        parts.append(d.ell(f"{p}_white{side}", X(sx * 14), Y(-8), S(16), S(11), "#ffffff", stroke=OUTLINE, sw=max(1, ow * 0.7)))
    for side, sx in (("L", -1), ("R", 1)):
        pupils.append(d.ell(f"{p}_pupil{side}", X(sx * 14), Y(-8), S(6.2), S(6.2), "#2a2030"))
    parts.append(d.group(f"{p}_pupils", pupils))
    for side, sx in (("L", -1), ("R", 1)):
        parts.append(d.poly(f"{p}_lid{side}",
                            [(X(sx * 14 - 8.6), Y(-8)), (X(sx * 14 - 6), Y(-14.2)), (X(sx * 14), Y(-15.8)),
                             (X(sx * 14 + 6), Y(-14.2)), (X(sx * 14 + 8.6), Y(-8)), (X(sx * 14), Y(-9.8))],
                            c["skin"], stroke=OUTLINE, sw=max(1, ow * 0.7), smooth=True, tension=0.3))
        parts.append(d.ell(f"{p}_brow{side}", X(sx * 14), Y(-20), S(22), S(7),
                           c["beard"] or "#e9e9ee", rot=-sx * 10, stroke="#9aa0ab", sw=max(1, ow * 0.5)))
    if c["glasses"]:
        for side, sx in (("L", -1), ("R", 1)):
            parts.append(d.ell(f"{p}_lens{side}", X(sx * 14), Y(-8), S(21), S(18), "#bfeaff", opacity=0.3,
                               stroke="#3c3c48", sw=max(2, S(1.2))))
        parts.append(d.line(f"{p}_bridge", [(X(-4), Y(-9)), (X(0), Y(-11)), (X(4), Y(-9))], "#3c3c48", sw=max(2, S(1.2))))

    # hat
    if c["hat"] == "pointy":
        top = -150 if kind == "tallworth" else -128
        parts += [
            d.ell(f"{p}_brim", X(0), Y(-34), S(96), S(14), c["hat_col"], stroke=OUTLINE, sw=ow),
            d.poly(f"{p}_hat", [(X(-36), Y(-34)), (X(-22), Y(top * 0.6)), (X(-4), Y(top)), (X(8), Y(top)),
                                (X(22), Y(top * 0.6)), (X(36), Y(-34))], c["hat_col"], stroke=OUTLINE, sw=ow),
            d.poly(f"{p}_hatBand", [(X(-36), Y(-48)), (X(35), Y(-48)), (X(36), Y(-34)), (X(-36), Y(-34))], c["trim"]),
            d.star(f"{p}_hatStar", X(0), Y(-82), S(24), c["trim"]),
        ]
    else:  # bishop-like miter
        parts += [
            d.poly(f"{p}_hat", [(X(-36), Y(-32)), (X(-34), Y(-110)), (X(-12), Y(-160)), (X(0), Y(-132)),
                                (X(12), Y(-160)), (X(34), Y(-110)), (X(36), Y(-32))], c["hat_col"],
                   stroke=OUTLINE, sw=ow),
            d.poly(f"{p}_hatBand", [(X(-36), Y(-52)), (X(36), Y(-52)), (X(36), Y(-32)), (X(-36), Y(-32))], c["trim"]),
            d.star(f"{p}_hatStar", X(0), Y(-88), S(26), "#c8312d", points=4, inner=0.35),
        ]
    return d.group(p, parts)


# ------------------------------------------------------------------------ germs
GERM_PALETTE = [("#6fd36b", "#3d8f3b"), ("#c26be0", "#7d3a99"), ("#ff9f4a", "#b8641a"), ("#4fc8e0", "#2a8aa0"),
                ("#ff6f91", "#b83a5b")]


def germ(d: Doc, p: str, cx: float, cy: float, r: float, kind: int = 0, face: str = "happy"):
    """A cheerful microbe: blob body with spikes, big eyes, optional face. (cx, cy) is its
    centre, ``r`` its radius. Parts: {p}_body, {p}_eyes (blink group), {p}_mouth."""
    fill, dark = GERM_PALETTE[kind % len(GERM_PALETTE)]
    ow = max(1.5, r * 0.07)
    parts: list[str] = []
    spikes = 10 if kind % 2 == 0 else 0
    if spikes:
        import math
        pts = []
        for i in range(spikes * 2):
            ang = math.pi * 2 * i / (spikes * 2) - math.pi / 2
            rad_ = r * (1.34 if i % 2 == 0 else 1.02)
            pts.append((cx + math.cos(ang) * rad_, cy + math.sin(ang) * rad_))
        parts.append(d.poly(f"{p}_spikes", pts, dark, stroke=dark, sw=ow, smooth=False))
    parts.append(d.ell(f"{p}_body", cx, cy, r * 2, r * 1.92, fill, stroke=dark, sw=ow))
    parts += [
        d.ell(f"{p}_sheen", cx - r * 0.38, cy - r * 0.5, r * 0.7, r * 0.4, "#ffffff", opacity=0.35, rot=-25),
        d.ell(f"{p}_spotA", cx + r * 0.42, cy + r * 0.52, r * 0.3, r * 0.26, dark, opacity=0.35),
        d.ell(f"{p}_spotB", cx - r * 0.55, cy + r * 0.3, r * 0.2, r * 0.18, dark, opacity=0.35),
    ]
    eyes = [
        d.ell(f"{p}_eyeWL", cx - r * 0.34, cy - r * 0.1, r * 0.5, r * 0.58, "#ffffff", stroke=dark, sw=max(1, ow * 0.6)),
        d.ell(f"{p}_eyeWR", cx + r * 0.34, cy - r * 0.1, r * 0.5, r * 0.58, "#ffffff", stroke=dark, sw=max(1, ow * 0.6)),
        d.ell(f"{p}_pupL", cx - r * 0.3, cy - r * 0.06, r * 0.22, r * 0.26, "#1c1426"),
        d.ell(f"{p}_pupR", cx + r * 0.38, cy - r * 0.06, r * 0.22, r * 0.26, "#1c1426"),
    ]
    parts.append(d.group(f"{p}_eyes", eyes))
    if face == "happy":
        parts.append(d.line(f"{p}_mouth", [(cx - r * 0.3, cy + r * 0.36), (cx, cy + r * 0.62), (cx + r * 0.3, cy + r * 0.36)],
                            "#1c1426", sw=max(2, r * 0.09)))
    elif face == "grin":
        parts.append(d.ell(f"{p}_mouth", cx, cy + r * 0.5, r * 0.62, r * 0.38, "#5a1d2a", stroke="#1c1426", sw=max(1, ow * 0.6)))
    else:  # evil
        parts.append(d.line(f"{p}_mouth", [(cx - r * 0.34, cy + r * 0.52), (cx - r * 0.1, cy + r * 0.42), (cx + r * 0.1, cy + r * 0.56),
                                           (cx + r * 0.34, cy + r * 0.44)], "#1c1426", sw=max(2, r * 0.09), smooth=False))
        parts.append(d.line(f"{p}_browL", [(cx - r * 0.62, cy - r * 0.55), (cx - r * 0.12, cy - r * 0.34)], "#1c1426", sw=max(2, r * 0.1), smooth=False))
        parts.append(d.line(f"{p}_browR", [(cx + r * 0.62, cy - r * 0.55), (cx + r * 0.12, cy - r * 0.34)], "#1c1426", sw=max(2, r * 0.1), smooth=False))
    return d.group(p, parts)
