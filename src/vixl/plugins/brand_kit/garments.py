"""Flat-lay garments for the merch mockups: tee, long-sleeve, crewneck and hoodie, front and back views.

One ``Garment`` holds the measurements; ``garment_view`` draws a view of it as shape layers: a soft shadow, the base
layers (body, collar, neck lining: the layers ``garment_color`` recolours), then shading, seams, stitching, ribbing and
highlights as multiply and screen layers clipped to the body, so the same drawing reads on white and on black.
"""

import math

from ...geometry import bezier_points
from .drawing import CX, LIGHT, SHADE, Pen, drop_shadow, half_outline, layered, lerp, stroke_style, through

VIEW_W = 1100
BASE = "#e9e6df"
CORD = "#e4dfd2"


class Garment:
    """The measurements of one flat-lay garment in view pixels. ``*_x`` values are distances from the axis ``CX``;
    the outline is the right half mirrored. ``front_drop`` is where the front neckline bottoms out, ``back_drop`` the
    back one (a hood's lower edge in the back view); ``rib_cuff`` and ``rib_hem`` are the heights of ribbed bands."""

    DEFAULTS = dict(kind="tee", rib_cuff=0, rib_hem=0, hood=False, pocket=False, view_h=1000, collar_width=22,
                    sleeve_print_at=0.52, chest_top=None, back_top=None, neck_tag_top=None, rim=0,
                    edge_fractions=(0.3, 0.65))

    def __init__(self, **m):
        self.__dict__.update({**self.DEFAULTS, **m})
        self.shoulder = (CX + self.shoulder_x, self.shoulder_y)
        self.armpit = (CX + self.chest_x, self.armpit_y)
        mid = lerp(self.shoulder, self.armpit, 0.5)
        self.sleeve_mid = mid
        points = [mid]
        for angle, length in self.sleeve_path:
            rad = math.radians(angle)
            points.append((points[-1][0] + math.cos(rad) * length, points[-1][1] + math.sin(rad) * length))
        pen = through(points)
        dense, start = [], pen.start
        for seg in pen.segments:
            dense.extend(bezier_points([start, seg[1], seg[2], seg[3]], [i / 16 for i in range(16)]).tolist())
            start = seg[3]
        dense.append(start)
        self.centreline = [tuple(p) for p in dense]
        self.lengths = [0.0]
        for p, q in zip(self.centreline, self.centreline[1:]):
            self.lengths.append(self.lengths[-1] + math.dist(p, q))
        self.cuff_centre, tangent = self.sleeve_point(1.0)
        self.axis = tangent
        self.perp = (-tangent[1], tangent[0])
        half = self.cuff_width / 2
        self.cuff_top = (self.cuff_centre[0] - self.perp[0] * half, self.cuff_centre[1] - self.perp[1] * half)
        self.cuff_bottom = (self.cuff_centre[0] + self.perp[0] * half, self.cuff_centre[1] + self.perp[1] * half)

    def sleeve_point(self, fraction):
        """``(point, unit tangent)`` on the sleeve's centreline at ``fraction`` (0 at the armhole, 1 at the cuff) of
        its length."""
        target = self.lengths[-1] * max(0.0, min(1.0, fraction))
        i = max(1, next((k for k, d in enumerate(self.lengths) if d >= target), len(self.lengths) - 1))
        p, q = self.centreline[i - 1], self.centreline[i]
        span = self.lengths[i] - self.lengths[i - 1] or 1.0
        t = (target - self.lengths[i - 1]) / span
        a, b = self.centreline[max(0, i - 2)], self.centreline[min(len(self.centreline) - 1, i + 1)]
        norm = math.dist(a, b) or 1.0
        return lerp(p, q, t), ((b[0] - a[0]) / norm, (b[1] - a[1]) / norm)

    def sleeve_edges(self, fractions):
        """Points on the sleeve's upper and lower edges at ``fractions`` of its length: the centreline pushed out by the
        sleeve's half width, which tapers from the armhole to the cuff."""
        top, bottom = [], []
        for f in fractions:
            (x, y), (tx, ty) = self.sleeve_point(f)
            half = (self.sleeve_width + (self.cuff_width - self.sleeve_width) * f) / 2
            top.append((x + ty * half, y - tx * half))
            bottom.append((x - ty * half, y + tx * half))
        return top, bottom

    def top_outline(self):
        """Right half of the top edge from the axis to the neck point: the back collar, or the dome of a hood."""
        nx, ny, top = self.neck_x, self.neck_y, self.back_collar_top
        if self.hood:
            return [(CX, top), (CX + nx * 0.45, top + 6), (CX + nx * 0.8, top + 36), (CX + nx * 0.96, top + 80),
                    (CX + nx, ny)]
        return [(CX, top), (CX + nx * 0.6, top + 6), (CX + nx, ny)]

    def points(self):
        """The right half of the outline from the top of the axis to the bottom of it, and its sharp corners."""
        g = self
        S, A, CT, CB = g.shoulder, g.armpit, g.cuff_top, g.cuff_bottom
        ax, ay = g.axis
        cuff = lerp(CT, CB, 0.5)
        out = g.top_outline()
        corners = {len(out) - 1}
        up, down = g.sleeve_edges(g.edge_fractions)
        out += [(CX + g.neck_x + (g.shoulder_x - g.neck_x) * 0.5, g.neck_y + (g.shoulder_y - g.neck_y) * 0.45), S, *up]
        corners.add(len(out))
        out += [CT, (cuff[0] + ax * 5, cuff[1] + ay * 5)]
        corners.add(len(out))
        out += [CB, *down[::-1]]
        out.append((lerp(down[0], A, 0.5)[0] + 5, lerp(down[0], A, 0.5)[1] + 2))
        corners.add(len(out))
        out += [A, (CX + (g.chest_x + g.hem_x) / 2 + 2, (g.armpit_y + g.hem_y) / 2)]
        corners.add(len(out))
        out += [(CX + g.hem_x, g.hem_y), (CX + g.hem_x * 0.5, g.hem_y + 4), (CX, g.hem_y + 6)]
        return out, corners

    def silhouette(self):
        points, corners = self.points()
        return half_outline(points, corners, CX)

    def neck_shapes(self, front):
        """Point lists of the neck: the front collar's outer and inner edges (left to right and right to left), the
        back band's outer and inner arcs (left to right)."""
        nx, ny, band = self.neck_x, self.neck_y, self.collar_width
        drop = self.front_drop if front else self.back_drop
        top = self.back_collar_top
        outer = [(CX - nx, ny), (CX - nx * 0.82, ny + (drop - ny) * 0.55), (CX - nx * 0.4, ny + (drop - ny) * 0.9),
                 (CX, drop), (CX + nx * 0.4, ny + (drop - ny) * 0.9), (CX + nx * 0.82, ny + (drop - ny) * 0.55),
                 (CX + nx, ny)]
        d = drop - band
        rim = self.rim or band
        inner = [(CX + nx - rim, ny - 6), (CX + (nx - band) * 0.84, ny + (d - ny) * 0.5),
                 (CX + (nx - band) * 0.42, ny + (d - ny) * 0.88), (CX, d),
                 (CX - (nx - band) * 0.42, ny + (d - ny) * 0.88), (CX - (nx - band) * 0.84, ny + (d - ny) * 0.5),
                 (CX - nx + rim, ny - 6)]
        right = self.top_outline()
        back_out = [(2 * CX - x, y) for x, y in right[:0:-1]] + right
        rim = self.rim or band
        vertical = min(rim, (ny - top) * 0.62)
        back_in = [(CX + (x - CX) * (1 - rim / nx), ny - 6 - (ny - 6 - y) * (1 - vertical / (ny - 6 - top))) for x, y in right]
        back_in = [(2 * CX - x, y) for x, y in back_in[:0:-1]] + back_in
        return outer, inner, back_out, back_in


def _stroke(view, name, pen, color, width, opacity, dash=None, shift=(0, 0)):
    return view.path(name, pen, pad=3 + width, shift=shift, **stroke_style(color, width, opacity, dash, "butt"))


def _gradient_fill(angle, *stops):
    return {"direction": "angled", "angle": angle, "stops": [{"offset": o, "color": c} for o, c in stops]}


def _seam(v, name, pen, width=1.4, opacity=0.3, dash=None):
    """A sewn line: a dark line with a light one a pixel below it, which reads as a pressed seam on any colour."""
    return [_stroke(v, f"{name}-line", pen, SHADE, width, opacity, dash),
            _stroke(v, f"{name}-light", pen, LIGHT, width, opacity * 0.55, dash, shift=(0, 1.6))]


def _mirror(sign):
    return lambda p: (CX + (p[0] - CX) * sign, p[1])


def _rib_lines(a, b, step, direction, length):
    """Short parallel lines from points along the segment ``a``-``b`` every ``step`` px, ``length`` long toward
    ``direction`` (a unit vector): ribbing."""
    count = max(2, int(math.hypot(b[0] - a[0], b[1] - a[1]) / step))
    pen = None
    for i in range(count + 1):
        p = lerp(a, b, i / count)
        q = (p[0] + direction[0] * length, p[1] + direction[1] * length)
        if pen is None:
            pen = Pen(*p)
        else:
            pen.move(*p)
        pen.line(*q)
    return pen


def garment_view(g, v, front=True):
    """Operations of one view: ``scene`` (shadow and base layers), ``overlay`` (everything over the print) and the
    ``base`` layer names."""
    body_pen = g.silhouette()
    scene = [*drop_shadow(v, "shadow", body_pen, 4, 14, 18, 0.32), v.path("body", body_pen, fill=BASE)]
    base = ["body"]
    over = []
    if front or not g.hood:
        outer, inner, back_out, back_in = g.neck_shapes(front)
        vertical = dict(start_tangent=(0, 60), end_tangent=(0, -60))
        front_band = through(outer, **vertical)
        front_band.line(*inner[0])
        through(inner, pen=front_band, **vertical)
        front_band.close()
        opening = through(inner, **vertical)
        through([inner[-1], *back_in[::-1][1:-1], inner[0]], pen=opening, start_tangent=(30, -20), end_tangent=(30, 20))
        opening.close()
        back_band = through(back_out, start_tangent=(40, -30), end_tangent=(40, 30))
        back_band.line(*back_in[0])
        through(back_in, pen=back_band, start_tangent=(-30, -20), end_tangent=(-30, 20))
        back_band.close()
        scene += [v.path("neck-inside", opening, fill=BASE), v.path("collar-back", back_band, fill=BASE),
                  v.path("collar", front_band, fill=BASE)]
        base += ["neck-inside", "collar-back", "collar"]
        over += _neck_details(g, v, opening, outer, inner, back_out, back_in, front)
    over += _body_shading(g, v, front)
    if g.hood:
        over += _hood_details(g, v, front)
    if g.pocket and front:
        over += _pocket(g, v)
    return scene, over, [v.name(n) for n in base]


def _neck_details(g, v, opening, outer, inner, back_out, back_in, front):
    ops = []
    vertical = dict(start_tangent=(0, 60), end_tangent=(0, -60))
    # The lining inside the neck is in shade, darkest under the front collar.
    ops += layered(v, "neck-lining", opening, base="neck-inside", blend="multiply",
                   opacity=(0.26 if g.hood else 0.2) if front else 0.1, fill=SHADE)
    ops += layered(v, "neck-collar-shadow", through(inner, **vertical), base="neck-inside", blend="multiply",
                   opacity=0.34 if front else 0.2, blur=7, fill="transparent", stroke=SHADE, stroke_width=16,
                   line_cap="butt")
    if not g.hood:
        # Rib: short dashes across the band, plus the sewn edges.
        centre = through([lerp(a, b, 0.5) for a, b in zip(outer, inner[::-1])], **vertical)
        width = g.collar_width - 4
        ops.append(_stroke(v, "collar-rib", centre, SHADE, width, 0.13, dash=[1.4, 3.2]))
        ops.append(_stroke(v, "collar-rib-light", centre, LIGHT, width, 0.1, dash=[1.2, 3.4], shift=(1.2, 0)))
        back_centre = through([lerp(a, b, 0.5) for a, b in zip(back_out, back_in)], start_tangent=(40, -30),
                              end_tangent=(40, 30))
        ops.append(_stroke(v, "collar-back-rib", back_centre, SHADE, 14, 0.12, dash=[1.4, 3.2]))
        ops.append(_stroke(v, "collar-back-rib-light", back_centre, LIGHT, 14, 0.09, dash=[1.2, 3.4], shift=(1.2, 0)))
    else:
        edge = through([lerp(a, b, 0.5) for a, b in zip(back_out, back_in)], start_tangent=(40, -30), end_tangent=(40, 30))
        ops.append(_stroke(v, "hood-stitch", edge, SHADE, 1.0, 0.24, dash=[5, 4]))
        ops += layered(v, "hood-rim-shade", through(back_in, start_tangent=(30, -20), end_tangent=(30, 20)),
                       base="collar-back", blend="multiply", opacity=0.3, blur=6, fill="transparent", stroke=SHADE,
                       stroke_width=14, line_cap="butt")
    ops += _seam(v, "collar-edge-outer", through(outer, **vertical), 1.6, 0.34)
    ops += _seam(v, "collar-edge-inner", through(inner, **vertical), 1.4, 0.4)
    ops += _seam(v, "collar-back-edge", through(back_in, start_tangent=(-30, -20), end_tangent=(-30, 20)), 1.4, 0.4)
    return ops


def _body_shading(g, v, front):
    ops = []
    A, S = g.armpit, g.shoulder
    ax, ay = g.axis
    # Light from the upper left: a broad tone over the whole garment.
    ops += [{"type": "gradient", "name": v.name("tone"), "x": CX - 520 + v.ox, "y": 20 + v.oy, "width": 1040,
             "height": g.hem_y - 10, **_gradient_fill(70, (0, "rgba(255,255,255,0)"), (1, "rgba(0,0,0,0.14)"))},
            {"type": "blend", "target": v.name("tone"), "value": "multiply"},
            {"type": "clip", "target": v.name("tone"), "base": v.name("body")}]
    for sign, name, strength in ((1, "r", 1.0), (-1, "l", 0.7)):
        px = _mirror(sign)
        armpit = px(A)
        crease = through([(armpit[0] - sign * 6, armpit[1] + 2), (armpit[0] - sign * 30, armpit[1] + 40),
                          (armpit[0] - sign * 52, armpit[1] + 96)])
        ops += layered(v, f"armpit-{name}", crease, base="body", blend="multiply", opacity=0.13 * strength, blur=16,
                       fill="transparent", stroke=SHADE, stroke_width=22, line_cap="round")
        seam = through([px(S), (px(S)[0] - sign * 8, S[1] + 70), (armpit[0] - sign * 16, armpit[1] - 70), armpit])
        ops += _seam(v, f"armhole-{name}", seam)
        under = through([px(g.cuff_bottom), (px(lerp(g.cuff_bottom, A, 0.5))[0], lerp(g.cuff_bottom, A, 0.5)[1] + 2), armpit])
        ops += layered(v, f"sleeve-under-{name}", under, base="body", blend="multiply", opacity=0.3 * strength, blur=8,
                       fill="transparent", stroke=SHADE, stroke_width=24, line_cap="round")
        if len(g.sleeve_path) > 1:
            elbow, (tx, ty) = g.sleeve_point(0.5)
            half = g.cuff_width * 0.6
            line = through([px((elbow[0] + ty * half, elbow[1] - tx * half)),
                            px((elbow[0] - ty * half, elbow[1] + tx * half))])
            ops += layered(v, f"elbow-{name}", line, base="body", blend="multiply", opacity=0.1 * strength, blur=9,
                           fill="transparent", stroke=SHADE, stroke_width=22, line_cap="round")
        if g.rib_cuff:
            ops += _cuff_rib(g, v, px, name)
        else:
            # Cuff: a sewn hem a little inside the edge.
            inset = 17
            cuff = through([px((g.cuff_top[0] - ax * inset + g.perp[0] * 6, g.cuff_top[1] - ay * inset + g.perp[1] * 6)),
                            px((g.cuff_bottom[0] - ax * inset - g.perp[0] * 6, g.cuff_bottom[1] - ay * inset - g.perp[1] * 6))])
            ops += _seam(v, f"cuff-{name}", cuff, 1.4, 0.3)
            ops.append(_stroke(v, f"cuff-{name}-stitch", cuff, SHADE, 1.0, 0.22, dash=[5, 4]))
    if g.rib_hem:
        ops += _hem_rib(g, v)
    else:
        # The hem: a sewn double line above the edge.
        hem = through([(CX - g.hem_x + 8, g.hem_y - 30), (CX - g.hem_x * 0.5, g.hem_y - 27), (CX, g.hem_y - 26),
                       (CX + g.hem_x * 0.5, g.hem_y - 27), (CX + g.hem_x - 8, g.hem_y - 30)])
        ops += _seam(v, "hem", hem, 1.4, 0.3)
        stitch = through([(CX - g.hem_x + 8, g.hem_y - 22), (CX, g.hem_y - 18), (CX + g.hem_x - 8, g.hem_y - 22)])
        ops.append(_stroke(v, "hem-stitch", stitch, SHADE, 1.0, 0.22, dash=[5, 4]))
    ops += _folds(g, v)
    return ops


def _cuff_rib(g, v, px, name):
    """A ribbed cuff: the band at the end of the sleeve with its seam, ribs and a little shade."""
    ax, ay = g.axis
    r = g.rib_cuff
    a, b = px(g.cuff_top), px(g.cuff_bottom)
    sign = 1 if name == "r" else -1
    back = (-ax * sign, -ay)
    ops = []
    band = Pen(*a).line(*b).line(b[0] + back[0] * r, b[1] + back[1] * r).line(a[0] + back[0] * r, a[1] + back[1] * r).close()
    ops += layered(v, f"cuff-{name}-band", band, base="body", blend="multiply", opacity=0.07, fill=SHADE)
    ribs = _rib_lines(lerp(a, b, 0.04), lerp(a, b, 0.96), 5.2, back, r - 3)
    ops.append(_stroke(v, f"cuff-{name}-rib", ribs, SHADE, 1.5, 0.17))
    ops.append(_stroke(v, f"cuff-{name}-rib-light", ribs, LIGHT, 1.3, 0.12, shift=(1.4, 0)))
    seam = through([(a[0] + back[0] * r, a[1] + back[1] * r), (b[0] + back[0] * r, b[1] + back[1] * r)])
    ops += _seam(v, f"cuff-{name}-seam", seam, 1.6, 0.34)
    return ops


def _hem_rib(g, v):
    top = g.hem_y - g.rib_hem
    left, right = CX - g.hem_x + 2, CX + g.hem_x - 2
    ops = []
    band = Pen(left, top).line(right, top).line(right + 4, g.hem_y + 4).line(left - 4, g.hem_y + 4).close()
    ops += layered(v, "hem-band", band, base="body", blend="multiply", opacity=0.07, fill=SHADE)
    ribs = _rib_lines((left, top + 4), (right, top + 4), 5.2, (0, 1), g.rib_hem - 6)
    ops.append(_stroke(v, "hem-rib", ribs, SHADE, 1.5, 0.17))
    ops.append(_stroke(v, "hem-rib-light", ribs, LIGHT, 1.3, 0.12, shift=(1.4, 0)))
    seam = through([(left, top + 1), (CX, top - 2), (right, top + 1)])
    ops += _seam(v, "hem-seam", seam, 1.6, 0.34)
    ops += layered(v, "hem-fold", seam, base="body", blend="multiply", opacity=0.14, blur=7, fill="transparent",
                   stroke=SHADE, stroke_width=14, line_cap="butt")
    return ops


def _folds(g, v):
    """Soft folds and highlights: multiply shading hardly shows on a dark garment, so the form also rides on light
    that screens over it (invisible on white)."""
    ops = []
    for sign, name in ((1, "r"), (-1, "l")):
        px = _mirror(sign)
        sh = lerp(g.shoulder, g.cuff_top, 0.55)
        ridge = through([px((CX + g.neck_x + 10, g.neck_y + 6)),
                         px((CX + g.neck_x + (g.shoulder_x - g.neck_x) * 0.55, g.neck_y + (g.shoulder_y - g.neck_y) * 0.55 + 4)),
                         px((g.shoulder[0] - 6, g.shoulder[1] + 8)), px((sh[0], sh[1] + 10))])
        ops += layered(v, f"shoulder-light-{name}", ridge, base="body", blend="screen", opacity=0.15, blur=8,
                       fill="transparent", stroke=LIGHT, stroke_width=14, line_cap="round")
        fold = through([px((CX + g.chest_x - 40, g.armpit_y + 150)), px((CX + g.chest_x - 130, g.armpit_y + 230)),
                        px((CX + 70, g.armpit_y + 270))])
        ops += layered(v, f"fold-{name}", fold, base="body", blend="multiply", opacity=0.07, blur=16,
                       fill="transparent", stroke=SHADE, stroke_width=26, line_cap="round")
        ops += layered(v, f"fold-light-{name}", fold, base="body", blend="screen", opacity=0.08, blur=14,
                       fill="transparent", stroke=LIGHT, stroke_width=18, line_cap="round")
        end = through([px(lerp(g.cuff_top, g.cuff_bottom, 0.1)), px(lerp(g.cuff_top, g.cuff_bottom, 0.9))])
        ops += layered(v, f"cuff-light-{name}", end, base="body", blend="screen", opacity=0.12, blur=4,
                       fill="transparent", stroke=LIGHT, stroke_width=6, line_cap="butt")
    chest = through([(CX - 190, g.armpit_y - 20), (CX - 40, g.armpit_y - 40)])
    ops += layered(v, "chest-light", chest, base="body", blend="screen", opacity=0.07, blur=34,
                   fill="transparent", stroke=LIGHT, stroke_width=110, line_cap="round")
    hem = through([(CX - g.hem_x + 20, g.hem_y - 8), (CX, g.hem_y - 4), (CX + g.hem_x - 20, g.hem_y - 8)])
    ops += layered(v, "hem-sheen", hem, base="body", blend="screen", opacity=0.1, blur=3, fill="transparent",
                   stroke=LIGHT, stroke_width=5, line_cap="butt")
    return ops


def _hood_details(g, v, front):
    """The hood: drawstrings and eyelets on the front, the seam and lower edge of the hood lying flat on the back."""
    ops = []
    if front:
        drop = g.front_drop
        for sign, name in ((1, "r"), (-1, "l")):
            px = _mirror(sign)
            eye = px((CX + 62, drop - 26))
            cord = through([eye, px((CX + 70, drop + 70)), px((CX + 56, drop + 170)), px((CX + 60, drop + 250))],
                           start_tangent=(0, 40), end_tangent=(0, 40))
            ops.append(v.path(f"cord-{name}-shadow", cord, pad=8, shift=(2, 3),
                              **stroke_style(SHADE, 9, 0.28, None, "round")))
            ops.append(v.path(f"cord-{name}", cord, pad=8, **stroke_style(CORD, 6.5, 1, None, "round")))
            ops.append(v.path(f"cord-{name}-twist", cord, pad=8,
                              **stroke_style(SHADE, 6.5, 0.16, [1.2, 2.6], "butt")))
            tip = through([px((CX + 60, drop + 236)), px((CX + 60, drop + 262))])
            ops.append(v.path(f"cord-{name}-tip", tip, pad=8, **stroke_style("#6c6a66", 8, 1, None, "round")))
            ring = through([(eye[0] - 5, eye[1]), (eye[0] + 5, eye[1])])
            ops.append(v.path(f"eyelet-{name}", ring, pad=8, **stroke_style("#4b4a48", 11, 1, None, "round")))
            ops.append(v.path(f"eyelet-{name}-hole", ring, pad=8, **stroke_style("#15151a", 5, 1, None, "round")))
    else:
        nx, ny, top = g.neck_x, g.neck_y, g.back_collar_top
        centre = through([(CX, top + 4), (CX, (top + g.back_drop) / 2), (CX, g.back_drop - 10)])
        ops += _seam(v, "hood-centre", centre, 1.5, 0.3)
        edge = through([(CX - nx - 6, ny + 8), (CX - nx * 0.7, g.back_drop - 66), (CX - nx * 0.28, g.back_drop - 14),
                        (CX, g.back_drop), (CX + nx * 0.28, g.back_drop - 14), (CX + nx * 0.7, g.back_drop - 66),
                        (CX + nx + 6, ny + 8)], start_tangent=(10, 60), end_tangent=(10, -60))
        ops += _seam(v, "hood-edge", edge, 1.6, 0.34)
        ops += layered(v, "hood-shadow", edge, base="body", blend="multiply", opacity=0.26, blur=9, fill="transparent",
                       stroke=SHADE, stroke_width=16, line_cap="butt", shift=(0, 7))
        dome = through([(CX - nx + 14, ny - 6), (CX - nx * 0.8, top + 52), (CX - nx * 0.4, top + 14), (CX, top + 8),
                        (CX + nx * 0.4, top + 14), (CX + nx * 0.8, top + 52), (CX + nx - 14, ny - 6)])
        ops.append(_stroke(v, "hood-stitch", dome, SHADE, 1.0, 0.22, dash=[5, 4]))
    return ops


def _pocket(g, v):
    """The kangaroo pocket: stitched top and sides, with the hand openings as shadowed slits."""
    top = g.pocket_top
    bottom = g.hem_y - g.rib_hem
    wt, wb = g.pocket_half_top, g.pocket_half_bottom
    ops = []
    shape = Pen(CX - wt, top).line(CX + wt, top).line(CX + wb, bottom).line(CX - wb, bottom).close()
    ops += layered(v, "pocket-fill", shape, base="body", blend="multiply", opacity=0.05, fill=SHADE)
    ops += layered(v, "pocket-shadow", through([(CX - wt, top + 2), (CX, top + 5), (CX + wt, top + 2)]), base="body",
                   blend="multiply", opacity=0.22, blur=5, fill="transparent", stroke=SHADE, stroke_width=8,
                   line_cap="butt", shift=(0, 5))
    for sign, name in ((1, "r"), (-1, "l")):
        px = _mirror(sign)
        side = through([px((CX + wt, top)), px((CX + (wt + wb) / 2 + 8, (top + bottom) / 2)), px((CX + wb, bottom))])
        ops += _seam(v, f"pocket-side-{name}", side, 1.5, 0.32)
        slit = through([px((CX + wt - 4, top + 6)), px((CX + wt + 22, top + 108))])
        ops += layered(v, f"pocket-slit-{name}", slit, base="body", blend="multiply", opacity=0.55, blur=2, fill="transparent",
                       stroke=SHADE, stroke_width=9, line_cap="round")
        ops.append(_stroke(v, f"pocket-slit-{name}-lip", slit, LIGHT, 1.4, 0.3, shift=(-3 * sign, 0)))
        ops.append(_stroke(v, f"pocket-stitch-{name}", through([px((CX + wt - 10, top + 4)), px((CX + wt + 16, top + 112))]),
                           SHADE, 1.0, 0.22, dash=[5, 4]))
    top_line = through([(CX - wt, top), (CX, top - 1), (CX + wt, top)])
    ops += _seam(v, "pocket-top", top_line, 1.5, 0.32)
    ops.append(_stroke(v, "pocket-top-stitch", through([(CX - wt + 8, top + 8), (CX, top + 7), (CX + wt - 8, top + 8)]),
                       SHADE, 1.0, 0.22, dash=[5, 4]))
    return ops
