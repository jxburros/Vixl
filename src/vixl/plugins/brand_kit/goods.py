"""Merch other than garments: a tote bag, stickers (die-cut and kiss-cut) and an enamel pin on its card.

Like the garments they are drawn as vector paths and shaded with multiply and screen layers over base layers, so a bag
takes any ``garment_color``. A sticker and a pin have no fixed outline: ``die-cut`` traces the placed design's ink,
so the vinyl border, the cut line or the metal rim follows the artwork.
"""

from . import finishes
from .drawing import Pen, View, drop_shadow, layered, polygon_pen, rect_quad, through
from .garments import BASE, _gradient_fill, _seam, _stroke

BACKGROUND = "#e6e9ee"
SHADE, LIGHT = "#000000", "#ffffff"


def _weave(name, box, base, spacing=4.0, opacity=0.07):
    """A canvas weave over a base layer: two sets of fine multiply lines at right angles."""
    x, y, w, h = box
    ops = []
    for suffix, angle, color in (("warp", 90, SHADE), ("weft", 0, SHADE)):
        label = f"{name}-{suffix}"
        ops += [{"type": "shape", "shape": "path", "name": label, "x": x, "y": y, "width": w, "height": h,
                 "path": finishes.hatch_path(w, h, spacing, angle), "fill": "transparent", "stroke": color,
                 "stroke_width": 1.2, "line_cap": "butt", "opacity": opacity},
                {"type": "blend", "target": label, "value": "multiply"},
                {"type": "clip", "target": label, "base": base}]
    return ops


def tote():
    v = View(0, 0)
    body = (Pen(224, 470).line(976, 470).line(990, 1286).curve(991, 1304, 982, 1312, 962, 1312).line(238, 1312)
            .curve(218, 1312, 209, 1304, 210, 1286).close())

    def handle(dy, inset):
        """A handle strap: its arc lifted by ``dy`` and its feet staying on the bag."""
        outer = through([(322 + inset, 490), (326 + inset, 330 + dy), (420, 186 + dy), (600, 142 + dy),
                         (780, 186 + dy), (874 - inset, 330 + dy), (878 - inset, 490)],
                        start_tangent=(0, -90), end_tangent=(0, 90))
        inner = through([(878 - inset - 48, 490), (874 - inset - 48, 336 + dy), (770, 238 + dy), (600, 198 + dy),
                         (430, 238 + dy), (326 + inset + 48, 336 + dy), (322 + inset + 48, 490)],
                        start_tangent=(0, -90), end_tangent=(0, 90))
        outer.line(*inner.start)
        for seg in inner.segments:
            outer.segments.append(seg)
        return outer.close()

    back = handle(-30, 36)
    front = handle(0, 0)
    scene = [*drop_shadow(v, "shadow", body, 4, 22, 26, 0.3),
             v.path("handle-back", back, fill=BASE), v.path("body", body, fill=BASE),
             v.path("handle", front, fill=BASE)]
    over = [*layered(v, "handle-back-shade", back, base="handle-back", blend="multiply", opacity=0.22, fill=SHADE)]
    # The front handle falls on the bag: a soft shadow under its feet, clipped to the body.
    feet = Pen(318, 470).line(878, 470).line(878, 530).line(318, 530).close()
    over += layered(v, "handle-shadow", feet, base="body", blend="multiply", opacity=0.2, blur=14, fill=SHADE)
    over += [{"type": "gradient", "name": "tone", "x": 200, "y": 470, "width": 800, "height": 850,
              **_gradient_fill(72, (0, "rgba(255,255,255,0)"), (1, "rgba(0,0,0,0.13)"))},
             {"type": "blend", "target": "tone", "value": "multiply"}, {"type": "clip", "target": "tone", "base": "body"}]
    over += _weave("weave", (200, 470, 800, 850), "body")
    sides = Pen(228, 560).line(238, 1296)
    over += layered(v, "side-l", sides, base="body", blend="multiply", opacity=0.14, blur=16, fill="transparent",
                    stroke=SHADE, stroke_width=36, line_cap="butt")
    over += layered(v, "side-r", Pen(972, 560).line(982, 1296), base="body", blend="multiply", opacity=0.2, blur=16,
                    fill="transparent", stroke=SHADE, stroke_width=36, line_cap="butt")
    over += layered(v, "fold-1", through([(300, 760), (470, 840), (640, 880)]), base="body", blend="multiply",
                    opacity=0.07, blur=22, fill="transparent", stroke=SHADE, stroke_width=40, line_cap="round")
    over += layered(v, "fold-1-light", through([(300, 790), (470, 870), (640, 910)]), base="body", blend="screen",
                    opacity=0.1, blur=18, fill="transparent", stroke=LIGHT, stroke_width=28, line_cap="round")
    over += layered(v, "bottom-shade", through([(250, 1300), (600, 1306), (950, 1300)]), base="body", blend="multiply",
                    opacity=0.2, blur=12, fill="transparent", stroke=SHADE, stroke_width=26, line_cap="butt")
    # Hem, handle stitching boxes and the bottom seam.
    over += _seam(v, "hem", through([(224, 520), (600, 521), (976, 520)]), 1.6, 0.3)
    over.append(_stroke(v, "hem-stitch", through([(224, 534), (600, 535), (976, 534)]), SHADE, 1.1, 0.24, dash=[7, 5]))
    for name, x in (("l", 322), ("r", 780)):
        box = polygon_pen([(x, 476), (x + 96, 476), (x + 96, 600), (x, 600)])
        over.append(_stroke(v, f"patch-{name}", box, SHADE, 1.1, 0.26, dash=[7, 5]))
        cross = Pen(x, 476).line(x + 96, 600).move(x + 96, 476).line(x, 600)
        over.append(_stroke(v, f"patch-{name}-cross", cross, SHADE, 1.1, 0.24, dash=[7, 5]))
    over += _seam(v, "bottom", through([(228, 1290), (600, 1296), (972, 1290)]), 1.4, 0.26)
    for name, pen in (("handle-edge", front),):
        over += _seam(v, name, pen, 1.5, 0.3)
    over += layered(v, "handle-light", through([(334, 400), (356, 270), (440, 200)]), base="handle", blend="screen",
                    opacity=0.16, blur=5, fill="transparent", stroke=LIGHT, stroke_width=10, line_cap="round")
    over += layered(v, "handle-dark", through([(870, 410), (838, 290), (770, 224)]), base="handle", blend="multiply",
                    opacity=0.22, blur=6, fill="transparent", stroke=SHADE, stroke_width=14, line_cap="round")
    clip = polygon_pen([(236, 560), (964, 560), (968, 1296), (232, 1296)])
    areas = {"front": {"corners": rect_quad(600, 580, 560, 660), "print_size_mm": [280, 330], "surface": "base",
                       "clip_path": v.clip_path_at(clip), "shade": False, "gloss": False}}
    return {"description": "A canvas tote bag with a double handle, front view. Area: front (280 × 330 mm).",
            "width": 1200, "height": 1400, "background": BACKGROUND, "operations": scene, "overlay": over,
            "base": ["handle-back", "body", "handle"], "garment_color": "#efe9dc", "areas": areas}


def sticker(kiss=False):
    """A sticker lying on a surface. The die-cut one is the artwork with a white border and a soft shadow; the kiss-cut
    one sits on its backing sheet, with the cut line showing around it."""
    size = 1200
    operations = [{"type": "gradient", "name": "surface", "x": 0, "y": 0, "width": size, "height": size,
                   **_gradient_fill(35, (0, "#dfe5ec"), (1, "#c8d0da"))}]
    if kiss:
        sheet = Pen(150, 150).line(1050, 150).line(1050, 1050).line(150, 1050).close()
        v = View(0, 0)
        operations += [*drop_shadow(v, "sheet-shadow", sheet, 4, 14, 22, 0.28), v.path("sheet", sheet, fill="#f8f7f3"),
                       *_corner_sheen("sheet")]
        description = "A kiss-cut sticker on its backing sheet. Area: face (76 × 76 mm)."
    else:
        description = "A die-cut sticker: the artwork with a white border, lying on a surface. Area: face (76 × 76 mm)."
    face = {"corners": rect_quad(600, 330, 540, 540),
            "print_size_mm": [76, 76], "surface": "none", "cut": {"mode": "kiss" if kiss else "die", "border_mm": 3},
            "shade": False, "gloss": not kiss}
    return {"description": description, "width": size, "height": size, "background": "#d5dbe3",
            "operations": operations, "areas": {"face": face}}


def _corner_sheen(base):
    return [{"type": "gradient", "name": "sheet-sheen", "x": 150, "y": 150, "width": 900, "height": 900,
             **_gradient_fill(40, (0, "rgba(255,255,255,0.5)"), (0.5, "rgba(255,255,255,0)"), (1, "rgba(0,0,0,0.05)"))},
            {"type": "blend", "target": "sheet-sheen", "value": "overlay"},
            {"type": "clip", "target": "sheet-sheen", "base": base}]


def pin():
    """An enamel pin on its backing card: the metal rim follows the artwork, and the enamel finish gives the colours a
    gloss."""
    v = View(0, 0)
    width, height = 1100, 1400
    card = Pen(190, 130).line(910, 130).line(910, 1270).line(190, 1270).close()
    operations = [{"type": "gradient", "name": "surface", "x": 0, "y": 0, "width": width, "height": height,
                   **_gradient_fill(30, (0, "#303640"), (1, "#1d2128"))},
                  *drop_shadow(v, "card-shadow", card, 6, 22, 26, 0.5), v.path("card", card, fill="#f4efe4"),
                  {"type": "shape", "shape": "ellipse", "name": "hang-hole", "x": 520, "y": 164, "width": 60,
                   "height": 60, "fill": "#2a2f37"},
                  {"type": "shape", "shape": "rectangle", "name": "card-border", "x": 226, "y": 166, "width": 648,
                   "height": 1068, "fill": "transparent", "stroke": "#c8bfa9", "stroke_width": 3}]
    overlay = [{"type": "gradient", "name": "card-sheen", "x": 190, "y": 130, "width": 720, "height": 1140,
                **_gradient_fill(48, (0, "rgba(255,255,255,0.35)"), (0.4, "rgba(255,255,255,0)"),
                                 (1, "rgba(0,0,0,0.08)"))},
               {"type": "blend", "target": "card-sheen", "value": "overlay"},
               {"type": "clip", "target": "card-sheen", "base": "card"}]
    face = {"corners": rect_quad(550, 440, 420, 420), "print_size_mm": [35, 35], "surface": "none",
            "cut": {"mode": "pin", "border_mm": 1.3}, "finish": "enamel", "shade": False, "gloss": True}
    return {"description": "An enamel pin on its backing card: a gold rim follows the artwork's outline. Area: face "
                           "(35 × 35 mm); the enamel finish is its default.",
            "width": width, "height": height, "background": "#262b33", "operations": operations, "overlay": overlay,
            "areas": {"face": face}}


GOODS = {"tote": tote, "sticker": lambda: sticker(False), "sticker-kiss-cut": lambda: sticker(True),
         "enamel-pin": pin}
