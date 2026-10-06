import math, json, os, subprocess, random
from fontTools.ttLib import TTFont
from fontTools.pens.recordingPen import RecordingPen
from fontTools.pens.transformPen import TransformPen
from fontTools.pens.boundsPen import BoundsPen

HERE = os.path.dirname(os.path.abspath(__file__))
VIXL = '/root/.cache/uv/archive-v0/uqrdffbcAdce9Ut8/bin/vixl'
OUT = '/home/user/Vixl/logos/jeffrey-x-guntly/explorations/3-radical'

# ---------------- geometry ----------------
def add(a, b): return (a[0]+b[0], a[1]+b[1])
def sub(a, b): return (a[0]-b[0], a[1]-b[1])
def mul(a, s): return (a[0]*s, a[1]*s)
def norm(a):
    l = math.hypot(*a) or 1
    return (a[0]/l, a[1]/l)
def perp(a): return (-a[1], a[0])
def rot(v, deg):
    r = math.radians(deg); c, s = math.cos(r), math.sin(r)
    return (v[0]*c - v[1]*s, v[0]*s + v[1]*c)
def polar(c, r, deg):
    a = math.radians(deg); return (c[0]+r*math.cos(a), c[1]+r*math.sin(a))

def cubic(p0, p1, p2, p3, t):
    u = 1-t
    return (u**3*p0[0]+3*u*u*t*p1[0]+3*u*t*t*p2[0]+t**3*p3[0],
            u**3*p0[1]+3*u*u*t*p1[1]+3*u*t*t*p2[1]+t**3*p3[1])

class Curve:
    """polyline sampled from a chain of cubic segments [(p0,p1,p2,p3),...] or from points"""
    def __init__(self, pts):
        self.pts = pts
        self.cum = [0]
        for i in range(1, len(pts)):
            self.cum.append(self.cum[-1] + math.dist(pts[i-1], pts[i]))
        self.L = self.cum[-1]
    @classmethod
    def beziers(cls, segs, n=80):
        pts = []
        for k, s in enumerate(segs):
            for i in range(n+1):
                if k and i == 0: continue
                pts.append(cubic(*s, i/n))
        return cls(pts)
    @classmethod
    def arc(cls, c, r, a0, a1, n=360):
        return cls([polar(c, r, a0 + (a1-a0)*i/n) for i in range(n+1)])
    def at(self, f):
        d = f*self.L
        lo, hi = 0, len(self.cum)-1
        while hi-lo > 1:
            m = (lo+hi)//2
            if self.cum[m] <= d: lo = m
            else: hi = m
        seg = self.cum[hi]-self.cum[lo] or 1
        t = (d-self.cum[lo])/seg
        p = (self.pts[lo][0]+(self.pts[hi][0]-self.pts[lo][0])*t, self.pts[lo][1]+(self.pts[hi][1]-self.pts[lo][1])*t)
        tan = norm(sub(self.pts[hi], self.pts[lo]))
        return p, tan

def ribbon(curve, w0, w1=None, prof=None, n=200):
    """tapered filled stroke polygon along a curve; width fn of f"""
    if prof is None:
        w1 = w0 if w1 is None else w1
        prof = lambda f: w0 + (w1-w0)*f
    L, R = [], []
    for i in range(n+1):
        f = i/n
        p, t = curve.at(f)
        nn = perp(t); w = prof(f)/2
        L.append(add(p, mul(nn, w))); R.append(sub(p, mul(nn, w)))
    return L + R[::-1]

def area(poly):
    a = 0
    for i in range(len(poly)):
        x1, y1 = poly[i]; x2, y2 = poly[(i+1) % len(poly)]
        a += x1*y2 - x2*y1
    return a/2

def poly_d(poly, orient=1):
    if (area(poly) > 0) != (orient > 0): poly = poly[::-1]
    return 'M ' + ' L '.join(f'{x:.2f} {y:.2f}' for x, y in poly) + ' Z'

def qcurve(a, c, b, n=16):
    return [((1-t)**2*a[0]+2*(1-t)*t*c[0]+t*t*b[0], (1-t)**2*a[1]+2*(1-t)*t*c[1]+t*t*b[1]) for t in [i/n for i in range(n+1)]]

def leaf(base, ang, length, width, bend=0.0, n=20):
    """pointed leaf polygon from base along angle (deg). bend curls tip sideways."""
    d = rot((1, 0), ang); p = perp(d)
    tip = add(add(base, mul(d, length)), mul(p, bend*length))
    c1 = add(add(base, mul(d, length*0.45)), mul(p, width*1.0 + bend*length*0.3))
    c2 = add(add(base, mul(d, length*0.45)), mul(p, -width*1.0 + bend*length*0.3))
    side1 = qcurve(base, c1, tip, n)
    side2 = qcurve(tip, c2, base, n)
    return side1 + side2[1:-1]

def thorn(base, ang, length, bw, hook=0.25, n=12):
    """curved thorn: base center, pointing angle, base width, hook curls tip"""
    d = rot((1, 0), ang); p = perp(d)
    b1 = add(base, mul(p, bw/2)); b2 = sub(base, mul(p, bw/2))
    tip = add(add(base, mul(d, length)), mul(p, hook*length))
    c1 = add(add(base, mul(d, length*0.5)), mul(p, bw*0.15 + hook*length*0.15))
    c2 = add(add(base, mul(d, length*0.5)), mul(p, -bw*0.35 + hook*length*0.5))
    return qcurve(b1, c1, tip, n) + qcurve(tip, c2, b2, n)[1:]

def circle_poly(c, r, n=64):
    return [polar(c, r, 360*i/n) for i in range(n)]

def star_poly(c, ro, ri, k=4, rot0=-90):
    pts = []
    for i in range(2*k):
        pts.append(polar(c, ro if i % 2 == 0 else ri, rot0 + 180*i/k))
    return pts

def ring_d(c, r1, r2, n=180):
    return poly_d(circle_poly(c, r1, n), 1) + ' ' + poly_d(circle_poly(c, r2, n), -1)

# ---------------- type as outlines ----------------
_fonts = {}
def font(name):
    if name not in _fonts:
        _fonts[name] = TTFont(os.path.join(HERE, 'fonts', name + '.ttf'))
    return _fonts[name]

def glyph_rec(fname, ch):
    f = font(fname); cmap = f.getBestCmap(); gs = f.getGlyphSet()
    gn = cmap[ord(ch)]
    return gs, gn, gs[gn].width

def rec_to_d(rec):
    out = []
    for op, args in rec.value:
        if op == 'moveTo': out.append('M %.2f %.2f' % args[0])
        elif op == 'lineTo': out.append('L %.2f %.2f' % args[0])
        elif op == 'curveTo': out.append('C ' + ' '.join('%.2f %.2f' % a for a in args))
        elif op == 'qCurveTo':
            # expand implied on-curve points
            pts = list(args)
            if pts[-1] is None:
                pts = pts[:-1]
            # handled via decomposition
            if len(pts) == 1: out.append('L %.2f %.2f' % pts[0]); continue
            offs = pts[:-1]; end = pts[-1]
            for i, c in enumerate(offs):
                if i < len(offs)-1:
                    nxt = ((c[0]+offs[i+1][0])/2, (c[1]+offs[i+1][1])/2)
                else:
                    nxt = end
                out.append('Q %.2f %.2f %.2f %.2f' % (c[0], c[1], nxt[0], nxt[1]))
        elif op == 'closePath' or op == 'endPath': out.append('Z')
    return ' '.join(out)

def text_d(fname, s, size, x, y, anchor='center', tracking=0.0, rotate=0.0, origin=None, baseline=False):
    """Outline text. (x,y) = anchor point; anchor center -> centered on cap box (or baseline if baseline=True).
    tracking in em. returns d, bbox"""
    f = font(fname); upm = f['head'].unitsPerEm; sc = size/upm
    gs = f.getGlyphSet(); cmap = f.getBestCmap()
    # measure
    adv = 0; items = []
    for ch in s:
        if ch == ' ':
            adv += gs[cmap[32]].width*sc + tracking*size; continue
        gn = cmap[ord(ch)]
        items.append((gn, adv)); adv += gs[gn].width*sc + tracking*size
    total = adv - tracking*size
    bp = BoundsPen(gs)
    for gn, a in items:
        tp = TransformPen(bp, (sc, 0, 0, -sc, a, 0)); gs[gn].draw(tp)
    xmin, ymin, xmax, ymax = bp.bounds
    if anchor == 'center':
        ox = x - (xmin+xmax)/2
        oy = y if baseline else y - (ymin+ymax)/2
    elif anchor == 'left':
        ox = x - xmin; oy = y if baseline else y - (ymin+ymax)/2
    elif anchor == 'right':
        ox = x - xmax; oy = y if baseline else y - (ymin+ymax)/2
    rec = RecordingPen()
    ang = math.radians(rotate); c, s_ = math.cos(ang), math.sin(ang)
    org = origin or (x, y)
    for gn, a in items:
        # glyph -> local (a + gx*sc, -gy*sc) -> offset -> rotate about org
        tx = a + ox - org[0]; ty = oy - org[1]
        m = (sc*c, sc*s_, sc*s_*-1*-1, 0, 0, 0)
        # full affine: X = c*(sc*gx + tx) - s*(-sc*gy + ty) + org ; Y = s*(sc*gx+tx) + c*(-sc*gy+ty) + org
        A = c*sc; B = s_*sc; C = s_*sc; D = -c*sc
        E = c*tx - s_*ty + org[0]; F = s_*tx + c*ty + org[1]
        tp = TransformPen(rec, (A, B, C, D, E, F)); gs[gn].draw(tp)
    bbox = (xmin+ox, ymin+oy, xmax+ox, ymax+oy)
    return rec_to_d(rec), bbox

def arc_text_d(fname, s, size, c, r, center_deg, tracking=0.0, inside=False):
    """text along circle; outward-reading on top (inside=False: letters upright at top, baseline on circle radius r)"""
    f = font(fname); upm = f['head'].unitsPerEm; sc = size/upm
    gs = f.getGlyphSet(); cmap = f.getBestCmap()
    widths = []
    for ch in s:
        gn = cmap[ord(ch)] if ch != ' ' else cmap[32]
        widths.append(gs[gn].width*sc)
    total = sum(widths) + tracking*size*(len(s)-1)
    # angular length
    sign = 1 if not inside else -1
    span = total / r * 180/math.pi
    a = center_deg - sign*span/2
    rec = RecordingPen()
    for ch, w in zip(s, widths):
        mid = a + sign*(w/2)/r*180/math.pi
        if ch != ' ':
            gn = cmap[ord(ch)]
            p = polar(c, r, mid)
            # rotation of glyph: up direction = outward radial (top) for not inside
            theta = math.radians(mid + 90) if not inside else math.radians(mid - 90)
            cs, sn = math.cos(theta), math.sin(theta)
            # local glyph coords: x along tangent, centered at w/2; y up = -outward
            # X = p + (gx*sc - w/2)*t + (gy*sc)*u, where t=(cs,sn), u = outward
            if not inside:
                u = (math.cos(math.radians(mid)), math.sin(math.radians(mid)))
            else:
                u = (-math.cos(math.radians(mid)), -math.sin(math.radians(mid)))
            t = (cs, sn)
            A = t[0]*sc; B = t[1]*sc; C = u[0]*sc; D = u[1]*sc
            E = p[0] - t[0]*w/2; F = p[1] - t[1]*w/2
            tp = TransformPen(rec, (A, B, C, D, E, F)); gs[gn].draw(tp)
        a += sign*(w + tracking*size)/r*180/math.pi
    return rec_to_d(rec)

# ---------------- doc helpers ----------------
def path(name, d, fill=None, stroke=None, sw=None, **kw):
    op = {'type': 'shape', 'shape': 'path', 'name': name, 'path': d}
    if fill: op['fill'] = fill
    if stroke: op['stroke'] = stroke; op['stroke_width'] = sw or 2
    op.update(kw)
    return op

def split_ops(ops, limit=7000):
    out = []
    for op in ops:
        if op.get('type') == 'shape' and op.get('shape') == 'path' and len(op['path'].split()) / 2.2 > limit:
            subs = ['M' + x for x in op['path'].split('M') if x.strip()]
            chunks = []; cur = []; cnt = 0
            for sp in subs:
                c = sp.count('L') + sp.count('Q') + sp.count('C') + 2
                if cur and cnt + c > limit:
                    chunks.append(cur); cur = []; cnt = 0
                cur.append(sp); cnt += c
            if cur: chunks.append(cur)
            names = []
            for i, ch in enumerate(chunks):
                o = dict(op); o['path'] = ' '.join(ch); o['name'] = op['name'] + ('' if i == 0 else f'-{i+1}')
                names.append(o['name']); out.append(o)
            if len(names) > 1:
                out.append({'type': 'group', 'name': op['name'] + '-group', 'targets': names})
        else:
            out.append(op)
    return out

def build(slug, bg, ops, fonts=(), size='1000x1000', post=None):
    os.makedirs(OUT, exist_ok=True)
    proj = os.path.join(OUT, slug + '.vixl')
    if os.path.exists(proj): os.remove(proj)
    subprocess.run([VIXL, 'new', size, '-o', proj, '--background', bg], check=True, capture_output=True)
    for fam, w, it in fonts:
        args = [VIXL, '--project', proj, 'font', 'install', fam, '--weight', str(w)]
        if it: args.append('--italic')
        subprocess.run(args, check=True, capture_output=True)
    ops = split_ops(ops)
    opf = os.path.join(HERE, slug + '.ops.json')
    json.dump(ops, open(opf, 'w'))
    r = subprocess.run([VIXL, '--project', proj, 'apply', opf], capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stdout[-3000:], r.stderr[-3000:]); raise SystemExit(1)
    try:
        w = json.loads(r.stdout).get('warnings')
        if w: print('WARN', w)
    except Exception: pass
    png = os.path.join(OUT, slug + '.png')
    r = subprocess.run([VIXL, '--project', proj, 'render', '--out', png, '--overwrite'], capture_output=True, text=True)
    if r.returncode != 0: print(r.stdout[-2000:], r.stderr[-2000:])
    print('built', proj)

def spiral_pts(start, ang, r0, turns=1.2, shrink=0.75, cw=1, n=60):
    """tendril curl: starts at `start` heading `ang`, curling with decreasing radius"""
    pts = [start]; p = start; a = ang; r = r0
    total = 360*turns; step = total/n
    for i in range(n):
        a += cw*step
        rr = r0 * (shrink ** (i*step/360*2))
        ds = math.radians(step)*rr
        p = add(p, mul(rot((1, 0), a), ds)); pts.append(p)
    return pts

def vine(curve, w0, w1, thorns=(), leaves=(), leaf_len=50, leaf_w=13, thorn_len=22, rng=None):
    """thorns: list of (f, side, scale); leaves: list of (f, side, scale). returns stem polys, leaf polys, rib polys"""
    prof = lambda f: w0 + (w1-w0)*f
    stem = [ribbon(curve, 0, prof=prof, n=max(60, int(curve.L/4)))]
    lv = []; ribs = []
    for f, sd, s in thorns:
        q, tg = curve.at(f); w = prof(f)/2
        ang = math.degrees(math.atan2(tg[1], tg[0]))
        stem.append(thorn(add(q, mul(perp(tg), sd*(w*0.7))), ang + sd*58, thorn_len*s, max(4, (w*1.5+4)*s), hook=-sd*0.28))
    for f, sd, s in leaves:
        q, tg = curve.at(f)
        ang = math.degrees(math.atan2(tg[1], tg[0])) + sd*48
        L = leaf_len*s
        lv.append(leaf(q, ang, L, leaf_w*s, bend=-sd*0.08))
        dd = rot((1, 0), ang)
        p0 = add(q, mul(dd, L*0.12))
        ribs.append(ribbon(Curve(qcurve(p0, add(add(q, mul(dd, L*0.5)), mul(perp(dd), -sd*0.04*L)), add(q, mul(dd, L*0.82)), 10)), max(1.2, leaf_w*s*0.16), 0.3))
    return stem, lv, ribs

def D(polys, orient=1):
    return ' '.join(poly_d(p, orient) for p in polys)

def flatten_d(d, n=8):
    toks = d.replace(',', ' ').split(); i = 0; polys = []; cur = []; p = (0, 0)
    while i < len(toks):
        c = toks[i]; i += 1
        if c == 'M':
            if cur: polys.append(cur)
            p = (float(toks[i]), float(toks[i+1])); i += 2; cur = [p]
        elif c == 'L':
            p = (float(toks[i]), float(toks[i+1])); i += 2; cur.append(p)
        elif c == 'Q':
            c1 = (float(toks[i]), float(toks[i+1])); e = (float(toks[i+2]), float(toks[i+3])); i += 4
            cur += qcurve(p, c1, e, n)[1:]; p = e
        elif c == 'C':
            c1 = (float(toks[i]), float(toks[i+1])); c2 = (float(toks[i+2]), float(toks[i+3])); e = (float(toks[i+4]), float(toks[i+5])); i += 6
            cur += [cubic(p, c1, c2, e, k/n) for k in range(1, n+1)]; p = e
        elif c == 'Z':
            if cur: polys.append(cur); cur = []
    if cur: polys.append(cur)
    return polys

def inside(polys, pt):
    x, y = pt; c = False
    for poly in polys:
        n = len(poly)
        for k in range(n):
            x1, y1 = poly[k]; x2, y2 = poly[(k+1) % n]
            if (y1 > y) != (y2 > y) and x < (x2-x1)*(y-y1)/(y2-y1) + x1:
                c = not c
    return c

def shift_d(d, dx, dy):
    out = []; k = 0
    for tok in d.split():
        if tok.isalpha(): out.append(tok); k = 0; continue
        v = float(tok)
        out.append('%.2f' % (v + (dx if k % 2 == 0 else dy))); k += 1
    return ' '.join(out)

def shift_ops(ops, dx, dy):
    for o in ops:
        if 'path' in o and isinstance(o['path'], str): o['path'] = shift_d(o['path'], dx, dy)
    return ops
