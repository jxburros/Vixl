from lib import *
W, H = 1600, 800
BG = '#151514'; BONE = '#ebe3d2'; ACC = '#b8433f'; MUTE = '#8a8478'
ops = []
S = 380; ox, oy = 244, (H - S)/2 + 34
def M(p): return (ox + p[0]*S, oy + p[1]*S)
SW = 18

# S-vine through the center with tangent angle theta at center
C = (0.5, 0.5); P0 = (0.0, 1.0)
theta = math.radians(-12)
t = (math.cos(theta), math.sin(theta)); n = perp(t)
# center Q = C + n*r ; |Q - P0| = r -> solve r
d = sub(C, P0)
# |d + n r|^2 = r^2 -> d.d + 2 r d.n = 0 -> r = -d.d/(2 d.n)
r = -(d[0]**2 + d[1]**2)/(2*(d[0]*n[0] + d[1]*n[1]))
Q = add(C, mul(n, r))
a0 = math.atan2(P0[1]-Q[1], P0[0]-Q[0]); a1 = math.atan2(C[1]-Q[1], C[0]-Q[0])
# choose short arc
da = (a1 - a0 + math.pi) % (2*math.pi) - math.pi
arc1 = [(Q[0] + abs(r)*math.cos(a0 + da*i/120), Q[1] + abs(r)*math.sin(a0 + da*i/120)) for i in range(121)]
arc2 = [(1-x, 1-y) for x, y in arc1[::-1]]
spts = [M(p) for p in arc1 + arc2[1:]]
sc = Curve(spts)
ops.append(path('stem-line', 'M %.2f %.2f L %.2f %.2f' % (*M((0.0, 0.0)), *M((1.0, 1.0))), fill='transparent', stroke=BONE, sw=SW, line_cap='round'))
ops.append(path('vine', 'M ' + ' L '.join('%.2f %.2f' % p for p in spts), fill='transparent', stroke=BONE, sw=SW, line_cap='round'))

# geometric thorns: straight isoceles triangles on alternating sides, leaning toward growth
tri = []
for f, sd in ((0.14, 1), (0.3, -1), (0.7, 1), (0.86, -1)):
    p, tg = sc.at(f); nn = perp(tg)
    base_c = add(p, mul(nn, sd*SW*0.35))
    dirv = norm(add(mul(nn, sd), mul(tg, 0.55)))
    bw = 22; L = 40
    b1 = add(base_c, mul(tg, bw/2)); b2 = sub(base_c, mul(tg, bw/2))
    tip = add(base_c, mul(dirv, L))
    tri.append([b1, tip, b2])
ops.append(path('thorns', D(tri), fill=BONE))

# rosebud at the top end: teardrop + sepals
pe, te = sc.at(1.0)
ang = math.atan2(te[1], te[0])
def tear(base, ang, Lh, R, n=60):
    # round bottom circle radius R centered at base + R along dir, pointed tip at Lh
    d_ = (math.cos(ang), math.sin(ang)); p_ = perp(d_)
    c_ = add(base, mul(d_, R))
    tip = add(base, mul(d_, Lh))
    pts = []
    # tangent points from tip to circle
    dist = Lh - R; beta = math.acos(R/dist)
    a_tip = ang + math.pi  # direction from center to base side
    start = ang + beta; end = ang + 2*math.pi - beta
    for i in range(n+1):
        a = start + (end-start)*i/n
        pts.append((c_[0] + R*math.cos(a), c_[1] + R*math.sin(a)))
    pts.append(tip)
    return pts
bud_base = add(pe, mul(te, 6))
ops.append(path('bud', poly_d(tear(bud_base, ang, 96, 29)), fill=ACC))
sep = []
for sd in (1, -1):
    b0 = add(pe, mul(te, 4))
    dv = rot(te, sd*38)
    nn = perp(dv)
    sep.append([add(b0, mul(nn, 7)), add(b0, mul(dv, 44)), sub(b0, mul(nn, 7))])
ops.append(path('sepals', D(sep), fill=BONE))
# divider
dx = ox + S + 120
ops.append(path('divider', 'M %.2f %.2f L %.2f %.2f' % (dx, H/2 - 120, dx, H/2 + 120), fill='transparent', stroke=MUTE, sw=2))
# wordmark
tx = dx + 80
d1, b1 = text_d('josefin-sans-300', 'JEFFREY', 92, tx, H/2 - 62, anchor='left', tracking=0.32)
d2, b2 = text_d('josefin-sans-300', 'GUNTLY', 92, tx, H/2 + 62, anchor='left', tracking=0.32)
print(b1, b2)
ops.append(path('wordmark', d1 + ' ' + d2, fill=BONE))
build('05-monoline', BG, ops, size='1600x800')
