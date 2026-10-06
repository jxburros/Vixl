import math, re, json
from fontTools.ttLib import TTFont
from fontTools.pens.basePen import BasePen
class SVGPathPen(BasePen):
    def __init__(self, gs):
        super().__init__(gs); self.c = []
    def _moveTo(self, p): self.c.append(f"M {p[0]:.2f} {p[1]:.2f}")
    def _lineTo(self, p): self.c.append(f"L {p[0]:.2f} {p[1]:.2f}")
    def _curveToOne(self, a, b, p): self.c.append(f"C {a[0]:.2f} {a[1]:.2f} {b[0]:.2f} {b[1]:.2f} {p[0]:.2f} {p[1]:.2f}")
    def _qCurveToOne(self, a, p): self.c.append(f"Q {a[0]:.2f} {a[1]:.2f} {p[0]:.2f} {p[1]:.2f}")
    def _closePath(self): self.c.append("Z")
    def _endPath(self): pass
    def getCommands(self): return " ".join(self.c)
from fontTools.pens.transformPen import TransformPen
from fontTools.pens.boundsPen import BoundsPen

FONTDIR = '/root/.cache/vixl/fonts/'
_fonts = {}
def font(name):
    if name not in _fonts: _fonts[name] = TTFont(FONTDIR + name)
    return _fonts[name]

def kern_pairs(f):
    # simple GPOS pair kerning lookup is complex; use kern table if present
    pairs = {}
    if 'kern' in f:
        for t in f['kern'].kernTables:
            pairs.update(t.kernTable)
    return pairs

def text_path(fname, text, size, x, baseline, tracking=0, kern=None, per_glyph=False):
    """Return svg d (absolute coords) and glyph boxes. kern: dict index->extra px before glyph i."""
    f = font(fname); upm = f['head'].unitsPerEm; s = size / upm
    cmap = f.getBestCmap(); gs = f.getGlyphSet(); hmtx = f['hmtx']
    kp = kern_pairs(f)
    pen_x = x; ds = []; boxes = []; prev = None
    for i, ch in enumerate(text):
        g = cmap[ord(ch)]
        if prev and (prev, g) in kp: pen_x += kp[(prev, g)] * s
        if kern and i in kern: pen_x += kern[i]
        sp = SVGPathPen(gs)
        tp = TransformPen(sp, (s, 0, 0, -s, pen_x, baseline))
        gs[g].draw(tp)
        bp = BoundsPen(gs); gs[g].draw(bp)
        if bp.bounds:
            b = bp.bounds; boxes.append((ch, pen_x + b[0]*s, baseline - b[3]*s, pen_x + b[2]*s, baseline - b[1]*s))
        else: boxes.append((ch, pen_x, baseline, pen_x, baseline))
        ds.append(sp.getCommands())
        pen_x += hmtx[g][0] * s + tracking; prev = g
    return (ds if per_glyph else " ".join(ds)), boxes, pen_x

def text_width(fname, text, size, tracking=0, kern=None):
    _, boxes, end = text_path(fname, text, size, 0, 0, tracking, kern)
    return boxes[0][1], max(b[3] for b in boxes)  # ink left, ink right

TOK = re.compile(r'[A-Za-z]|-?\d*\.?\d+(?:e-?\d+)?')
def bbox(d):
    nums = []; cmd = None
    toks = TOK.findall(d)
    xs, ys = [], []
    vals = [t for t in toks if not t.isalpha()]
    for i in range(0, len(vals) - 1, 2):
        xs.append(float(vals[i])); ys.append(float(vals[i+1]))
    return min(xs), min(ys), max(xs), max(ys)

def shift(d, dx, dy):
    out = []; k = 0
    for t in TOK.findall(d):
        if t.isalpha(): out.append(t)
        else:
            out.append(f"{float(t) - (dx if k % 2 == 0 else dy):.2f}"); k += 1
    return " ".join(out)

def shape(name, d, fill="#111111", stroke="transparent", sw=0, pad=0, **kw):
    x0, y0, x1, y1 = bbox(d)
    x0 = math.floor(x0 - pad); y0 = math.floor(y0 - pad); x1 = math.ceil(x1 + pad); y1 = math.ceil(y1 + pad)
    op = {"type": "shape", "shape": "path", "name": name, "x": x0, "y": y0,
          "width": max(1, x1 - x0), "height": max(1, y1 - y0),
          "path": shift(d, x0, y0), "fill": fill, "stroke": stroke}
    if sw: op["stroke_width"] = sw
    op.update(kw)
    return op

# ---------- curves ----------
def cubic(p0, p1, p2, p3, t):
    u = 1 - t
    return (u**3*p0[0] + 3*u*u*t*p1[0] + 3*u*t*t*p2[0] + t**3*p3[0],
            u**3*p0[1] + 3*u*u*t*p1[1] + 3*u*t*t*p2[1] + t**3*p3[1])

def catmull(pts, samples=24):
    """Catmull-Rom through pts -> list of cubic segments (p0,c1,c2,p3)."""
    segs = []
    P = [pts[0]] + pts + [pts[-1]]
    for i in range(1, len(P) - 2):
        p0, p1, p2, p3 = P[i-1], P[i], P[i+1], P[i+2]
        c1 = (p1[0] + (p2[0]-p0[0])/6, p1[1] + (p2[1]-p0[1])/6)
        c2 = (p2[0] - (p3[0]-p1[0])/6, p2[1] - (p3[1]-p1[1])/6)
        segs.append((p1, c1, c2, p2))
    return segs

def segs_d(segs):
    d = f"M {segs[0][0][0]:.2f} {segs[0][0][1]:.2f}"
    for s in segs: d += f" C {s[1][0]:.2f} {s[1][1]:.2f} {s[2][0]:.2f} {s[2][1]:.2f} {s[3][0]:.2f} {s[3][1]:.2f}"
    return d

def sample(segs, n_per=60):
    pts = []
    for s in segs:
        for k in range(n_per):
            pts.append(cubic(*s, k / n_per))
    pts.append(segs[-1][3])
    # arc length
    L = [0]
    for i in range(1, len(pts)):
        L.append(L[-1] + math.dist(pts[i], pts[i-1]))
    return pts, L

def at(pts, L, frac):
    """point and unit tangent at arc-length fraction"""
    target = frac * L[-1]
    for i in range(1, len(L)):
        if L[i] >= target:
            a, b = pts[i-1], pts[i]
            seg = L[i] - L[i-1] or 1
            t = (target - L[i-1]) / seg
            p = (a[0] + (b[0]-a[0])*t, a[1] + (b[1]-a[1])*t)
            tx, ty = b[0]-a[0], b[1]-a[1]; n = math.hypot(tx, ty) or 1
            return p, (tx/n, ty/n)
    a, b = pts[-2], pts[-1]; tx, ty = b[0]-a[0], b[1]-a[1]; n = math.hypot(tx, ty) or 1
    return pts[-1], (tx/n, ty/n)

def ribbon(segs, w0, w1, wmid=None, n=240, prof=None):
    """Filled tapered ribbon along curve; width function via prof(f) or linear w0->w1."""
    pts, L = sample(segs, 80)
    left, right = [], []
    for k in range(n + 1):
        f = k / n
        p, t = at(pts, L, f)
        w = prof(f) if prof else (w0 + (w1 - w0) * f)
        nx, ny = -t[1], t[0]
        left.append((p[0] + nx*w/2, p[1] + ny*w/2)); right.append((p[0] - nx*w/2, p[1] - ny*w/2))
    poly = left + right[::-1]
    d = "M " + " L ".join(f"{x:.2f} {y:.2f}" for x, y in poly) + " Z"
    return d

def leaf(base, ang, length, width, curl=0.0):
    """Pointed almond leaf from base along angle (radians). curl bends the tip sideways."""
    ca, sa = math.cos(ang), math.sin(ang)
    def P(u, v):  # u along, v across
        return (base[0] + ca*u - sa*v, base[1] + sa*u + ca*v)
    tip = P(length, curl*length)
    c1 = P(length*0.25, width*0.75); c2 = P(length*0.75, width*0.55 + curl*length*0.6)
    c3 = P(length*0.75, -width*0.55 + curl*length*0.6); c4 = P(length*0.25, -width*0.75)
    b = P(0, 0)
    return (f"M {b[0]:.2f} {b[1]:.2f} C {c1[0]:.2f} {c1[1]:.2f} {c2[0]:.2f} {c2[1]:.2f} {tip[0]:.2f} {tip[1]:.2f} "
            f"C {c3[0]:.2f} {c3[1]:.2f} {c4[0]:.2f} {c4[1]:.2f} {b[0]:.2f} {b[1]:.2f} Z")

def thorn(base, ang, length, width, hook=0.25):
    """Curved thorn: triangle with concave sides and slightly hooked tip."""
    ca, sa = math.cos(ang), math.sin(ang)
    def P(u, v): return (base[0] + ca*u - sa*v, base[1] + sa*u + ca*v)
    a = P(0, width/2); b = P(0, -width/2); tip = P(length, hook*length)
    ca1 = P(length*0.35, width*0.12 + hook*length*0.2); cb1 = P(length*0.45, -width*0.05 + hook*length*0.5)
    return (f"M {a[0]:.2f} {a[1]:.2f} Q {ca1[0]:.2f} {ca1[1]:.2f} {tip[0]:.2f} {tip[1]:.2f} "
            f"Q {cb1[0]:.2f} {cb1[1]:.2f} {b[0]:.2f} {b[1]:.2f} Z")

def circle(c, r):
    x, y = c
    k = 0.5523 * r
    return (f"M {x+r:.2f} {y:.2f} C {x+r:.2f} {y+k:.2f} {x+k:.2f} {y+r:.2f} {x:.2f} {y+r:.2f} "
            f"C {x-k:.2f} {y+r:.2f} {x-r:.2f} {y+k:.2f} {x-r:.2f} {y:.2f} "
            f"C {x-r:.2f} {y-k:.2f} {x-k:.2f} {y-r:.2f} {x:.2f} {y-r:.2f} "
            f"C {x+k:.2f} {y-r:.2f} {x+r:.2f} {y-k:.2f} {x+r:.2f} {y:.2f} Z")

def spiral_pts(c, r0, a0, turns, shrink, n=12, direction=1):
    pts = []
    for k in range(n + 1):
        f = k / n
        a = a0 + direction * turns * 2 * math.pi * f
        r = r0 * (1 - shrink * f)
        pts.append((c[0] + r*math.cos(a), c[1] + r*math.sin(a)))
    return pts

def dump(ops, path):
    json.dump(ops, open(path, 'w'))

def vine_ops(name, pts, prof, thorns=(), leaves=(), ink='#141414', smooth_pts=None):
    """pts: waypoints; prof(f)->width; thorns: list of (frac, side, len, width); leaves: (frac, side, len, width, ang_deg, stem)"""
    segs = catmull(pts)
    ops = [shape(name + '-stem', ribbon(segs, 0, 0, prof=prof, n=400), fill=ink)]
    spts, L = sample(segs, 80)
    for i, (fr, side, ln, wd, *rest) in enumerate(thorns):
        p, t = at(spts, L, fr)
        a = math.atan2(t[1], t[0]) + side * math.radians(rest[0] if rest else 58)
        w = prof(fr)
        base = (p[0] + math.cos(a) * (w/2 - 1.5), p[1] + math.sin(a) * (w/2 - 1.5))
        ops.append(shape(f'{name}-thorn{i}', thorn(base, a, ln, wd, hook=-side*0.18), fill=ink))
    for i, (fr, side, ln, wd, ang, stem) in enumerate(leaves):
        p, t = at(spts, L, fr)
        a = math.atan2(t[1], t[0]) + side * math.radians(ang)
        w = prof(fr)
        sb = (p[0] + math.cos(a) * (w/2 - 1), p[1] + math.sin(a) * (w/2 - 1))
        d = ''
        if stem > 0:
            se = (sb[0] + math.cos(a) * stem, sb[1] + math.sin(a) * stem)
            ops.append(shape(f'{name}-petiole{i}', f"M {p[0]:.2f} {p[1]:.2f} L {se[0]:.2f} {se[1]:.2f}", fill='transparent', stroke=ink, sw=max(2.2, w*0.35), line_cap='round', pad=3))
            sb = se
        ops.append(shape(f'{name}-leaf{i}', leaf(sb, a, ln, wd, curl=side*0.12), fill=ink))
    return ops

def smoothstep(a, b, x):
    t = max(0, min(1, (x - a) / (b - a))); return t*t*(3-2*t)

def frac_of(pts_way, target):
    segs = catmull(pts_way); spts, L = sample(segs, 80)
    i = min(range(len(spts)), key=lambda k: math.dist(spts[k], target))
    return L[i] / L[-1]

def cutleaf(name, base, ang_deg, ln, wd, color='#ffffff', curl=0.0):
    return shape(name, leaf(base, math.radians(ang_deg), ln, wd, curl=curl), fill=color)

def sprout(name, glyph_d, base, ang_deg, ln, wd, curl=0.0, ink='#141414'):
    """Leaf that is black outside the letter and white (carved) inside it."""
    ld = leaf(base, math.radians(ang_deg), ln, wd, curl=curl)
    return [shape(name + '-leaf', ld, fill=ink),
            shape(name + '-cutA', ld, fill='#ffffff'),
            shape(name + '-cutB', glyph_d, fill='#ffffff'),
            {"type": "pathfinder", "name": name + '-carve', "targets": [name + '-cutA', name + '-cutB'], "mode": "intersect"}]

def arc_text(fname, text, size, C, R, center_deg, tracking=0, bottom=False):
    """Glyphs on an arc. top: reads clockwise, glyph tops outward, baseline at radius R.
    bottom: reads left-to-right along the bottom, glyph tops inward, baseline at radius R."""
    f = font(fname); upm = f['head'].unitsPerEm; s = size / upm
    cmap = f.getBestCmap(); gs = f.getGlyphSet(); hmtx = f['hmtx']
    advs = [hmtx[cmap[ord(ch)]][0] * s for ch in text]
    total = sum(advs) + tracking * (len(text) - 1)
    Rm = R + (0.35*size if not bottom else -0.35*size)
    span = total / Rm
    ds = []
    pos = 0
    for ch, adv in zip(text, advs):
        mid = pos + adv / 2
        if not bottom:
            th = math.radians(center_deg) - span/2 + mid / Rm
            t = (-math.sin(th), math.cos(th)); up = (math.cos(th), math.sin(th))
        else:
            th = math.radians(center_deg) + span/2 - mid / Rm
            t = (math.sin(th), -math.cos(th)); up = (-math.cos(th), -math.sin(th))
        p = (C[0] + R*math.cos(th), C[1] + R*math.sin(th))
        o = (p[0] - t[0]*adv/2, p[1] - t[1]*adv/2)
        g = cmap[ord(ch)]
        if ch != ' ':
            sp = SVGPathPen(gs)
            tp = TransformPen(sp, (s*t[0], s*t[1], s*up[0], s*up[1], o[0], o[1]))
            gs[g].draw(tp)
            ds.append(sp.getCommands())
        pos += adv + tracking
    return " ".join(ds)
