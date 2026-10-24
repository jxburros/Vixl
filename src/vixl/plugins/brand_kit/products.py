"""The built-in merch and print products of the ``mockup`` workflow, drawn as vector paths.

Each entry of ``PRODUCTS`` is a mockup template (see ``mockups.py``): a scene of ordinary shape layers, named print
**areas** with their corners, clip path and physical ``print_size_mm``, and, for garments and bags, a default
``garment_color`` and the ``base`` layers it recolours. The drawings are computed from measurements
(``garments.py``, ``drawing.py``), so a product is a few kilobytes of path data that stays crisp at any export scale.
Area corners keep the aspect ratio of their print size, so a design looks on the product as it will print.
"""

from . import accessories, garments, goods
from .drawing import CX, PX_PER_MM, View, polygon_pen, rect_quad, rotated_quad

PRODUCTS = {}

# Print sizes in millimetres (width, height): the largest prints of the common garment placements.
FRONT_CHEST_MM = (254, 254)
FULL_MM = (305, 406)
SLEEVE_MM = (76, 76)
HEM_TAG_MM = (51, 38)
NECK_TAG_MM = (76, 44)


def _px(size, scale=PX_PER_MM):
    return round(size[0] * scale, 2), round(size[1] * scale, 2)


def _garment_areas(g, front, back):
    """The standard areas of a garment drawn in ``front`` and ``back`` views, with corners in scene coordinates and
    clip paths that keep the print on the fabric."""
    top = g.chest_top or g.front_drop + 54
    back_top = g.back_top or g.back_drop + 74
    fw, fh = _px(FULL_MM)
    cw, ch = _px(FRONT_CHEST_MM)

    def torso(view, y0):
        inset = g.shoulder_x - 24
        pen = polygon_pen([(CX - inset, y0), (CX + inset, y0), (CX + g.chest_x - 6, g.armpit_y),
                           (CX + g.hem_x - 6, g.hem_y - 8), (CX - g.hem_x + 6, g.hem_y - 8),
                           (CX - g.chest_x + 6, g.armpit_y)])
        return view.clip_path_at(pen)

    base = {"surface": "base", "shade": False, "gloss": False}
    areas = {
        "front-chest": {"corners": front.quad_at(rect_quad(CX, top, cw, ch)), "print_size_mm": list(FRONT_CHEST_MM),
                        "clip_path": torso(front, g.front_drop + 12), **base},
        "full-front": {"corners": front.quad_at(rect_quad(CX, top, fw, fh)), "print_size_mm": list(FULL_MM),
                       "clip_path": torso(front, g.front_drop + 12), **base},
        "back": {"corners": back.quad_at(rect_quad(CX, back_top, fw, fh)), "print_size_mm": list(FULL_MM),
                 "clip_path": torso(back, g.back_drop + 8), **base},
    }
    sw, sh = _px(SLEEVE_MM)
    for name, sign in (("sleeve-l", 1), ("sleeve-r", -1)):
        (px_, py_), (tx, ty) = g.sleeve_point(g.sleeve_print_at)
        centre = (CX + (px_ - CX) * sign, py_)
        up = (-sign * tx, -ty)
        areas[name] = {"corners": front.quad_at(rotated_quad(centre, sw, sh, up)), "print_size_mm": list(SLEEVE_MM),
                       "clip_path": front.clip_path_at(polygon_pen(rotated_quad(centre, sw + 16, sh + 16, up))), **base}
    tw, th = _px(HEM_TAG_MM)
    tag_x, tag_y = CX - g.hem_x + 14 + tw / 2, g.hem_y - g.rib_hem - 38 - th
    areas["hem-tag"] = {"corners": front.quad_at(rect_quad(tag_x, tag_y, tw, th)), "print_size_mm": list(HEM_TAG_MM),
                        "clip_path": front.clip_path_at(polygon_pen([(tag_x - tw / 2 - 6, tag_y - 6),
                                                                      (tag_x + tw / 2 + 6, tag_y - 6),
                                                                      (tag_x + tw / 2 + 6, tag_y + th + 6),
                                                                      (tag_x - tw / 2 - 6, tag_y + th + 6)])), **base}
    nw, nh = _px(NECK_TAG_MM)
    ny = g.neck_tag_top or g.back_collar_top + g.collar_width + 14
    areas["inside-neck"] = {"corners": front.quad_at(rect_quad(CX, ny, nw, nh)), "print_size_mm": list(NECK_TAG_MM),
                            "clip_path": front.clip_path_at(polygon_pen([(CX - nw / 2 - 4, ny - 2), (CX + nw / 2 + 4, ny - 2),
                                                                           (CX + nw / 2 + 4, ny + nh + 4),
                                                                           (CX - nw / 2 - 4, ny + nh + 4)])), **base}
    return areas


def _garment(g, description, color):
    front, back = View(0, 0, "front-"), View(garments.VIEW_W, 0, "back-")
    f_scene, f_over, f_base = garments.garment_view(g, front, True)
    b_scene, b_over, b_base = garments.garment_view(g, back, False)
    return {"description": description, "width": garments.VIEW_W * 2, "height": g.view_h,
            "background": "#e6e9ee", "operations": [*f_scene, *b_scene], "overlay": [*f_over, *b_over],
            "base": [*f_base, *b_base], "garment_color": color, "areas": _garment_areas(g, front, back)}


AREAS_NOTE = (" Areas: front-chest, full-front, back, sleeve-l (the wearer's left, on the right of the front view), "
              "sleeve-r, hem-tag and inside-neck.")

ARM = (0.12, 0.25, 0.4, 0.55, 0.7, 0.85)  # where a bent sleeve's edges are sampled
BENT = [(38, 90), (68, 150), (90, 330)]  # a long sleeve: out and down, then hanging

TEE = dict(kind="tee", sleeve_path=[(40, 160)], sleeve_width=196, cuff_width=196, shoulder_x=262, shoulder_y=126,
           chest_x=292, armpit_y=372, hem_x=284, hem_y=905, neck_x=100, neck_y=70, back_collar_top=40,
           front_drop=178, back_drop=108, collar_width=22)
LONG_SLEEVE = dict(TEE, kind="long-sleeve", sleeve_path=BENT, sleeve_width=190, cuff_width=104, rib_cuff=28,
                   edge_fractions=ARM, sleeve_print_at=0.2)
CREWNECK = dict(kind="crewneck", sleeve_path=BENT, sleeve_width=196, cuff_width=108, shoulder_x=270, shoulder_y=132,
                chest_x=304, armpit_y=392, hem_x=296, hem_y=925, neck_x=108, neck_y=78, back_collar_top=44,
                front_drop=190, back_drop=114, collar_width=32, rib_cuff=36, rib_hem=56, edge_fractions=ARM,
                sleeve_print_at=0.2, view_h=1000)
HOODIE = dict(kind="hoodie", sleeve_path=BENT, sleeve_width=204, cuff_width=108, shoulder_x=270, shoulder_y=178,
              chest_x=304, armpit_y=424, hem_x=296, hem_y=915, neck_x=156, neck_y=126, back_collar_top=20,
              front_drop=262, back_drop=318, collar_width=20, rim=30, rib_cuff=38, rib_hem=64, hood=True, pocket=True,
              pocket_top=630, pocket_half_top=172, pocket_half_bottom=212, edge_fractions=ARM, sleeve_print_at=0.2,
              view_h=990, neck_tag_top=84, chest_top=312, back_top=352)

PRODUCTS["tee"] = _garment(garments.Garment(**TEE),
                           "A crew-neck t-shirt, front and back, flat on a light ground." + AREAS_NOTE, "#f1efe9")
PRODUCTS["long-sleeve"] = _garment(garments.Garment(**LONG_SLEEVE),
                                   "A long-sleeve t-shirt with ribbed cuffs, front and back." + AREAS_NOTE, "#f1efe9")
PRODUCTS["crewneck"] = _garment(garments.Garment(**CREWNECK),
                                "A crewneck sweatshirt with ribbed collar, cuffs and waistband, front and back."
                                + AREAS_NOTE, "#e4e2dc")
PRODUCTS["hoodie"] = _garment(garments.Garment(**HOODIE),
                              "A pullover hoodie with drawstrings, kangaroo pocket and ribbed cuffs, front and back "
                              "(the hood lies flat behind the neck)." + AREAS_NOTE, "#e4e2dc")

for _name, _make in {**goods.GOODS, **accessories.ACCESSORIES}.items():
    PRODUCTS[_name] = _make()
