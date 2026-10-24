"""Smaller merch: a baseball cap, a beanie, a pair of socks, an embroidered patch and a pin-back button.

Drawn like the garments (``garments.py``): base layers recoloured by ``garment_color``, shading and stitching as
multiply and screen layers above. The patch is cut around the placed design with ``die-cut`` as the stickers are.
"""

from . import finishes
from .drawing import LIGHT, SHADE, Pen, View, drop_shadow, layered, polygon_pen, rect_quad, through
from .garments import BASE, _gradient_fill, _seam, _stroke
from .goods import BACKGROUND, _weave

PX_PER_MM_SOCK = 3.15


def _ribbing(name, box, step, base, vertical=True):
    """Knit ribs over a base layer: fine lines, dark with a light neighbour."""
    x, y, w, h = box
    ops = []
    for suffix, color, opacity, offset in (("dark", SHADE, 0.16, 0.0), ("light", LIGHT, 0.12, step * 0.3)):
        label = f"{name}-{suffix}"
        ops += [{"type": "shape", "shape": "path", "name": label, "x": x, "y": y, "width": w, "height": h,
                 "path": finishes.hatch_path(w, h, step, 90 if vertical else 0, offset), "fill": "transparent",
                 "stroke": color, "stroke_width": round(step * 0.32, 2), "line_cap": "butt", "opacity": opacity},
                {"type": "blend", "target": label, "value": "multiply" if color == SHADE else "screen"},
                {"type": "clip", "target": label, "base": base}]
    return ops


def _side_light(x, y, w, h, name, base):
    """The dark edges and bright middle of a rounded form lit from the front."""
    return [{"type": "gradient", "name": name, "x": x, "y": y, "width": w, "height": h, "direction": "horizontal",
             "stops": [{"offset": 0, "color": "rgba(0,0,0,0.3)"}, {"offset": 0.28, "color": "rgba(0,0,0,0.02)"},
                       {"offset": 0.44, "color": "rgba(255,255,255,0)"}, {"offset": 0.78, "color": "rgba(0,0,0,0.06)"},
                       {"offset": 1, "color": "rgba(0,0,0,0.34)"}]},
            {"type": "blend", "target": name, "value": "multiply"}, {"type": "clip", "target": name, "base": base}]


def cap():
    """A six-panel baseball cap seen from the front."""
    v = View(0, 0)
    crown = (Pen(190, 560).curve(190, 280, 330, 118, 550, 118).curve(770, 118, 910, 280, 910, 560)
             .curve(800, 592, 300, 592, 190, 560).close())
    brim = (Pen(196, 566).curve(340, 560, 760, 560, 904, 566).curve(990, 640, 900, 770, 550, 800)
            .curve(200, 770, 110, 640, 196, 566).close())
    scene = [*drop_shadow(v, "shadow", brim, 4, 20, 24, 0.3), v.path("brim", brim, fill=BASE),
             v.path("crown", crown, fill=BASE)]
    over = [*_side_light(150, 110, 800, 700, "tone", "crown"),
            *layered(v, "crown-light", through([(330, 230), (420, 160), (520, 140)]), base="crown", blend="screen",
                     opacity=0.18, blur=16, fill="transparent", stroke=LIGHT, stroke_width=34, line_cap="round"),
            *layered(v, "brim-top-shade", through([(190, 580), (550, 612), (910, 580)]), base="brim", blend="multiply",
                     opacity=0.55, blur=8, fill="transparent", stroke=SHADE, stroke_width=26, line_cap="butt"),
            *layered(v, "brim-shade", through([(200, 700), (550, 780), (900, 700)]), base="brim", blend="multiply",
                     opacity=0.22, blur=18, fill="transparent", stroke=SHADE, stroke_width=60, line_cap="round")]
    for name, pts in (("seam-l", [(550, 126), (420, 190), (335, 320), (300, 570)]),
                      ("seam-r", [(550, 126), (680, 190), (765, 320), (800, 570)]),
                      ("seam-ll", [(550, 126), (360, 160), (250, 330), (214, 530)]),
                      ("seam-rr", [(550, 126), (740, 160), (850, 330), (886, 530)])):
        curve = through(pts)
        over += _seam(v, name, curve, 1.5, 0.28)
        over.append(_stroke(v, f"{name}-stitch", curve, SHADE, 1.0, 0.2, dash=[6, 4], shift=(5, 0)))
    for x in (498, 602):
        over.append({"type": "shape", "shape": "ellipse", "name": f"eyelet-{x}", "x": x - 8, "y": 150, "width": 16,
                     "height": 12, "fill": "#2a2d33", "opacity": 0.85})
    over += [{"type": "shape", "shape": "ellipse", "name": "button", "x": 528, "y": 100, "width": 44, "height": 30,
              "fill": BASE},
             {"type": "shape", "shape": "ellipse", "name": "button-shade", "x": 528, "y": 100, "width": 44, "height": 30,
              "fill": SHADE, "opacity": 0.18}]
    over += _seam(v, "band", through([(196, 540), (550, 572), (904, 540)]), 1.5, 0.3)
    for i, dy in enumerate((16, 30, 44)):
        stitch = through([(210 + dy * 1.2, 590 + dy * 0.4), (550, 640 + dy * 0.9), (890 - dy * 1.2, 590 + dy * 0.4)])
        over.append(_stroke(v, f"brim-stitch-{i}", stitch, SHADE, 1.0, 0.2, dash=[6, 4]))
    front = polygon_pen([(360, 288), (740, 288), (764, 532), (336, 532)])
    areas = {"front-panel": {"corners": rect_quad(550, 300, 360, 216), "print_size_mm": [90, 54], "surface": "base",
                             "clip_path": v.clip_path_at(front), "shade": False, "gloss": False}}
    return {"description": "A baseball cap seen from the front; the print goes on the front panel (90 × 54 mm), "
                           "which suits the embroidery finish.",
            "width": 1100, "height": 900, "background": BACKGROUND, "operations": scene, "overlay": over,
            "base": ["brim", "crown", "button"], "garment_color": "#2d3a4a", "areas": areas}


def beanie():
    """A knitted beanie with a folded cuff."""
    v = View(0, 0)
    crown = Pen(170, 690).curve(170, 330, 320, 96, 500, 96).curve(680, 96, 830, 330, 830, 690).close()
    cuff = (Pen(120, 640).curve(300, 664, 700, 664, 880, 640).line(892, 880).curve(892, 910, 870, 924, 840, 924)
            .line(160, 924).curve(130, 924, 108, 910, 108, 880).close())
    scene = [*drop_shadow(v, "shadow", cuff, 4, 22, 24, 0.3), v.path("crown", crown, fill=BASE),
             v.path("cuff-band", cuff, fill=BASE)]
    over = [*_ribbing("crown-ribs", (150, 90, 700, 620), 12, "crown"), *_ribbing("cuff-ribs", (100, 640, 800, 290), 14, "cuff-band"),
            *_side_light(100, 90, 800, 840, "tone", "cuff-band"), *_side_light(100, 90, 800, 640, "tone-crown", "crown"),
            *layered(v, "cuff-fold", through([(130, 650), (500, 676), (870, 650)]), base="cuff-band", blend="multiply",
                     opacity=0.4, blur=7, fill="transparent", stroke=SHADE, stroke_width=24, line_cap="butt"),
            *layered(v, "crown-light", through([(300, 260), (380, 180), (480, 150)]), base="crown", blend="screen",
                     opacity=0.16, blur=16, fill="transparent", stroke=LIGHT, stroke_width=36, line_cap="round"),
            *layered(v, "cuff-light", through([(190, 700), (210, 820)]), base="cuff-band", blend="screen", opacity=0.12,
                     blur=12, fill="transparent", stroke=LIGHT, stroke_width=30, line_cap="round")]
    label = polygon_pen([(150, 690), (850, 690), (856, 900), (144, 900)])
    areas = {"cuff": {"corners": rect_quad(500, 700, 360, 200), "print_size_mm": [90, 50], "surface": "base",
                      "clip_path": v.clip_path_at(label), "shade": False, "gloss": False}}
    return {"description": "A knitted beanie with a folded cuff; the print or woven label goes on the cuff "
                           "(90 × 50 mm).", "width": 1000, "height": 1100, "background": BACKGROUND,
            "operations": scene, "overlay": over, "base": ["crown", "cuff-band"], "garment_color": "#c24d3d",
            "areas": areas}


def socks():
    """A pair of crew socks lying flat, each with a print on the leg."""
    v = View(0, 0)
    w, h = 1400, 900
    scene, over, areas = [], [], {}
    for name, mirror in (("l", False), ("r", True)):
        def t(x, y, mirror=mirror):
            return (w - 30 - x * 0.82 if mirror else 30 + x * 0.82, 40 + y * 0.82)

        def pt(coords):
            return [t(x, y) for x, y in coords]

        sock = Pen(*t(150, 40)).line(*t(396, 40)).line(*t(406, 600))
        sock.curve(*t(430, 650), *t(560, 668), *t(680, 688)).curve(*t(780, 706), *t(840, 780), *t(808, 850))
        sock.curve(*t(786, 906), *t(700, 912), *t(620, 912)).line(*t(270, 912))
        sock.curve(*t(190, 912), *t(134, 860), *t(134, 780)).close()
        base = f"sock-{name}"
        scene += [*drop_shadow(v, f"shadow-{name}", sock, 4, 16, 18, 0.3), v.path(base, sock, fill=BASE)]
        heel = Pen(*t(134, 700)).curve(*t(134, 830), *t(190, 912), *t(280, 912)).line(*t(360, 912))
        heel.curve(*t(380, 820), *t(330, 730), *t(250, 700)).close()
        toe = Pen(*t(660, 690)).curve(*t(780, 706), *t(840, 780), *t(808, 850))
        toe.curve(*t(786, 906), *t(730, 912), *t(680, 912)).curve(*t(700, 820), *t(700, 740), *t(660, 690)).close()
        over += layered(v, f"heel-{name}", heel, base=base, blend="multiply", opacity=0.22, fill=SHADE)
        over += layered(v, f"toe-{name}", toe, base=base, blend="multiply", opacity=0.22, fill=SHADE)
        left, right = sorted((t(150, 40)[0], t(396, 40)[0]))
        over += _ribbing(f"cuff-{name}-ribs", (int(left) - 2, int(t(0, 40)[1]) - 2, int(right - left) + 6, 94), 9, base)
        over += _seam(v, f"cuff-{name}-seam", through(pt([(146, 150), (398, 150)])), 1.5, 0.3)
        edge = [(160, 160), (170, 560)] if not mirror else [(386, 160), (396, 560)]
        over += layered(v, f"leg-shade-{name}", through(pt(edge)), base=base, blend="multiply", opacity=0.14, blur=14,
                        fill="transparent", stroke=SHADE, stroke_width=40, line_cap="butt")
        over += layered(v, f"instep-{name}", through(pt([(420, 640), (600, 690), (780, 760)])), base=base,
                        blend="multiply", opacity=0.14, blur=10, fill="transparent", stroke=SHADE, stroke_width=26,
                        line_cap="round")
        size = (50 * PX_PER_MM_SOCK, 94 * PX_PER_MM_SOCK)
        corners = rect_quad(t(273, 0)[0], t(0, 190)[1], *size)
        pad = polygon_pen([(corners[0][0] - 10, corners[0][1] - 4), (corners[1][0] + 10, corners[1][1] - 4),
                           (corners[2][0] + 10, corners[2][1] + 4), (corners[3][0] - 10, corners[3][1] + 4)])
        areas[base] = {"corners": corners, "print_size_mm": [50, 94], "surface": "base",
                       "clip_path": v.clip_path_at(pad), "shade": False, "gloss": False}
    return {"description": "A pair of crew socks, flat; each has a print on the leg (50 × 94 mm). Areas: sock-l and "
                           "sock-r.", "width": w, "height": h, "background": BACKGROUND, "operations": scene,
            "overlay": over, "base": ["sock-l", "sock-r"], "garment_color": "#f1efe9", "areas": areas}


def patch():
    """An embroidered patch with a merrow border, sewn on denim."""
    size = 1200
    operations = [{"type": "solid", "name": "denim", "color": "#2f4a6d"}]
    overlay = _weave("denim-weave", (0, 0, size, size), "denim", 5.0, 0.16)
    face = {"corners": rect_quad(600, 330, 540, 540), "print_size_mm": [76, 76], "surface": "none",
            "cut": {"mode": "patch", "border_mm": 2.5}, "finish": "embroidery", "shade": False, "gloss": False}
    return {"description": "An embroidered patch with a merrow border, sewn on denim: the border follows the artwork. "
                           "Area: face (76 × 76 mm); the embroidery finish is its default.",
            "width": size, "height": size, "background": "#2f4a6d", "operations": operations, "overlay": overlay,
            "areas": {"face": face}}


def _circle(cx, cy, r):
    return f"M{cx - r} {cy} A{r} {r} 0 1 0 {cx + r} {cy} A{r} {r} 0 1 0 {cx - r} {cy} Z"


def button():
    """A pin-back button: a printed face under a clear dome, in a metal rim."""
    size, c, r = 1000, 500, 300
    rim = {"type": "shape", "shape": "ellipse", "name": "rim", "x": c - r - 26, "y": c - r - 26, "width": 2 * r + 52,
           "height": 2 * r + 52, "fill": "#b8bec6", "fill_gradient": {
               "direction": "angled", "angle": 45, "stops": [{"offset": 0, "color": "#f4f6f8"},
                                                              {"offset": 0.5, "color": "#aab1ba"},
                                                              {"offset": 1, "color": "#d9dde2"}]}}
    operations = [{"type": "gradient", "name": "surface", "x": 0, "y": 0, "width": size, "height": size,
                   **_gradient_fill(40, (0, "#e7d9c4"), (1, "#d3c1a6"))},
                  {"type": "shape", "shape": "ellipse", "name": "shadow", "x": c - r - 14, "y": c - r + 6,
                   "width": 2 * r + 52, "height": 2 * r + 52, "fill": SHADE, "opacity": 0.32},
                  {"type": "blur", "target": "shadow", "amount": 20}, rim]
    overlay = [{"type": "shape", "shape": "ellipse", "name": "face-edge", "x": c - r, "y": c - r, "width": 2 * r,
                "height": 2 * r, "fill": "transparent", "stroke": SHADE, "stroke_width": 3, "opacity": 0.3},
               {"type": "gradient", "name": "dome", "x": c - r, "y": c - r, "width": 2 * r, "height": 2 * r,
                "direction": "radial", "center": [0.34, 0.3],
                "stops": [{"offset": 0, "color": "rgba(255,255,255,0.55)"},
                          {"offset": 0.35, "color": "rgba(255,255,255,0.08)"},
                          {"offset": 1, "color": "rgba(0,0,0,0.22)"}]},
               {"type": "blend", "target": "dome", "value": "overlay"},
               {"type": "clip", "target": "dome", "base": "face-surface"}]
    face = {"corners": rect_quad(c, c - r, 2 * r, 2 * r), "print_size_mm": [57, 57], "surface": "#ffffff",
            "clip_path": _circle(c, c, r), "shade": False, "gloss": False}
    return {"description": "A 57 mm pin-back button: the print under a glossy dome, in a metal rim. Area: face "
                           "(57 mm round).", "width": size, "height": size, "background": "#dccdb4",
            "operations": operations, "overlay": overlay, "areas": {"face": face}}


ACCESSORIES = {"cap": cap, "beanie": beanie, "socks": socks, "patch": patch, "button": button}
