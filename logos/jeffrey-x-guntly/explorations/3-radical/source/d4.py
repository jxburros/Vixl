from lib import *
PARCH = '#efe4c8'; INK = '#1e1914'; OX = '#6f1a27'; OXD = '#56121d'; GOLD = '#c89a3e'; GOLDL = '#e2bf6a'; MOSS = '#5f6e36'; MOSSL = '#7f8f4a'
ops = []
def rect(x0, y0, x1, y1): return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]

X0, Y0, X1, Y1 = 270, 150, 730, 610
cx, cy = (X0+X1)/2, (Y0+Y1)/2
# frame: ink line, gold band, ink line
ops.append(path('frame-ink', poly_d(rect(X0-18, Y0-18, X1+18, Y1+18)), fill=INK))
ops.append(path('frame-gold', poly_d(rect(X0-15, Y0-15, X1+15, Y1+15)), fill=GOLD))
ops.append(path('frame-inner-ink', poly_d(rect(X0-3, Y0-3, X1+3, Y1+3)), fill=INK))
ops.append(path('field', poly_d(rect(X0, Y0, X1, Y1)), fill=OX))
# diaper pattern: diamond lattice + tiny quatrefoil dots
lat = []
step = 46
for k in range(-12, 13):
    for sgn in (1, -1):
        # line y = sgn*(x - cx) + cy + k*step  clipped to field
        pts = []
        for x in (X0, X1):
            y = sgn*(x - cx) + cy + k*step
            pts.append((x, y))
        # clip
        (xa, ya), (xb, yb) = pts
        def clip(xa, ya, xb, yb):
            # clip param t in [0,1] for y in [Y0, Y1]
            t0, t1 = 0, 1
            for (p, q) in ((-(yb-ya), ya-Y0), ((yb-ya), Y1-ya)):
                if p == 0: continue
                t = q/p
                if p < 0: t0 = max(t0, t)
                else: t1 = min(t1, t)
            if t0 >= t1: return None
            return (xa+(xb-xa)*t0, ya+(yb-ya)*t0), (xa+(xb-xa)*t1, ya+(yb-ya)*t1)
        c = clip(xa, ya, xb, yb)
        if c: lat.append(ribbon(Curve(list(c)), 1.6))
dots = []
for i in range(-12, 13):
    for j in range(-12, 13):
        x = cx + (i + j)*step/2; y = cy + (i - j)*step/2
        # diamond centers
        x2, y2 = x + step/2, y
        if X0+8 < x2 < X1-8 and Y0+8 < y2 < Y1-8:
            dots.append(star_poly((x2, y2), 6, 2.0, 4, -90))
ops.append(path('diaper-lines', D(lat), fill=OXD))
ops.append(path('diaper-dots', D(dots), fill=GOLD))
ops.append({'type': 'opacity', 'target': 'diaper-dots', 'value': 0.55})

# big initial X
dX, bX = text_d('cinzel-decorative-700', 'X', 350, cx, cy + 4)
print('X bbox', bX)
ops.append(path('X-shadow', dX, fill=OXD))
ops.append({'type': 'move', 'target': 'X-shadow', 'x': 7, 'y': 8, 'relative': True})
ops.append(path('X', dX, fill=GOLD))
ops.append(path('X-line', dX, fill='transparent', stroke=INK, sw=3.5))
ops.append({'type': 'layer-style', 'target': 'X', 'name': 'gradient-overlay', 'settings': {'stops': [{'offset': 0, 'color': GOLDL}, {'offset': 0.55, 'color': GOLD}, {'offset': 1, 'color': '#a47828'}], 'direction': 'angled', 'angle': 60, 'opacity': 1}})

# whiplash vine: root curl bottom-left margin, wraps the initial, weaves through it, exits top with a curl
segs = [((150, 840), (140, 710), (240, 640), (340, 615)),
        ((340, 615), (480, 580), (660, 610), (700, 470)),
        ((700, 470), (735, 360), (650, 290), (560, 300)),
        ((560, 300), (480, 308), (420, 345), (370, 300)),
        ((370, 300), (320, 255), (330, 160), (395, 105))]
cv = Curve.beziers(segs, 140)
p0, t0 = cv.at(0.0)
root = spiral_pts(p0, math.degrees(math.atan2(-t0[1], -t0[0])), 34, turns=1.3, shrink=0.35, cw=-1, n=80)
endp, tg = cv.at(1.0)
curl = spiral_pts(endp, math.degrees(math.atan2(tg[1], tg[0])), 30, turns=1.4, shrink=0.35, cw=1, n=80)
allc = Curve(root[::-1] + cv.pts[1:] + curl[1:])
Lr = Curve(root).L; Lm = cv.L; La = allc.L
fr = Lr/La; fm = (Lr+Lm)/La
def wprof(f):
    if f < fr: return 3 + 23*(f/fr)**0.6
    if f < fm: return 26 - 17*(f-fr)/(fm-fr)
    return 9 - 7*(f-fm)/(1-fm)
Xpolys = flatten_d(dX)
# crossing intervals
ins = [inside(Xpolys, allc.at(i/2000)[0]) for i in range(2001)]
ivs = []; start = None
for i, v in enumerate(ins):
    if v and start is None: start = i
    if not v and start is not None: ivs.append((start/2000, i/2000)); start = None
print('crossings', ivs)
under = [iv for k, iv in enumerate(ivs) if k % 2 == 1]
def in_under(f, pad=0.012):
    return any(a_-pad <= f <= b_+pad for a_, b_ in under)
# stem pieces
cuts = [0.0]
for a_, b_ in under: cuts += [a_, b_]
cuts.append(1.0)
stem = []
for k in range(0, len(cuts), 2):
    fa, fb = cuts[k], cuts[k+1]
    n = max(20, int((fb-fa)*La/3))
    Lp, Rp = [], []
    for i in range(n+1):
        f = fa + (fb-fa)*i/n
        p, t = allc.at(f); nn = perp(t); w = wprof(f)/2
        Lp.append(add(p, mul(nn, w))); Rp.append(sub(p, mul(nn, w)))
    stem.append(Lp + Rp[::-1])
# thorns + leaves on main section, mapped into allc fractions
th = [(f, s, 1 - 0.4*f) for f, s in ((0.05, 1), (0.1, -1), (0.17, 1), (0.24, -1), (0.31, 1), (0.39, -1), (0.47, 1), (0.55, -1), (0.62, 1), (0.69, -1), (0.76, 1), (0.83, -1), (0.9, 1))]
lf = [(f, s, sc) for f, s, sc in ((0.07, -1, 1.2), (0.14, 1, 1.15), (0.28, -1, 1.1), (0.35, 1, 1.0), (0.5, -1, 1.0), (0.58, 1, 1.0), (0.72, -1, 0.9), (0.8, 1, 0.8), (0.88, -1, 0.7))]
mapf = lambda f: fr + f*(fm-fr)
th = [(f, s, sc) for f, s, sc in th if not in_under(mapf(f), 0.03)]
lf = [(f, s, sc) for f, s, sc in lf if not in_under(mapf(f), 0.04)]
st, lv, rb = vine(cv, 26, 9, th, lf, leaf_len=70, leaf_w=19, thorn_len=28)
ops.append(path('vine-thorns', D(st[1:]), fill=INK))
ops.append(path('vine', D(stem), fill=MOSS, stroke=INK, sw=3))
ops.append(path('vine-leaves', D(lv), fill=MOSSL, stroke=INK, sw=2.5))
ops.append(path('vine-ribs', D(rb), fill=INK))

# name
dN, bN = text_d('cormorant-unicase-600', 'Jeffrey  Guntly', 64, 500, 752, tracking=0.06)
print('name', bN)
ops.append(path('name', dN, fill=INK))
# little x star between words
ops.append(path('name-star', poly_d(star_poly((500, 752), 13, 3.4, 4, -90)), fill=OX))
# rule + caption
r = [ribbon(Curve([(380, 828), (470, 828)]), 1.6, 1.6), ribbon(Curve([(530, 828), (620, 828)]), 1.6, 1.6)]
r.append(star_poly((500, 828), 8, 2.2, 4))
ops.append(path('rule', D(r), fill=INK))
shift_ops(ops, 0, 38)
build('04-illuminated-initial', PARCH, ops)
