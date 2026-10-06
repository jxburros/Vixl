from lib import *
C = (500, 500)
BG = '#132019'; GOLD = '#c9a24a'; BONE = '#ece2cb'; OX = '#a3333f'; DEEP = '#1c2c22'
ops = []
# radial glow behind
ops.append({'type': 'shape', 'shape': 'ellipse', 'name': 'halo', 'x': 60, 'y': 60, 'width': 880, 'height': 880, 'fill': '#172a1f'})

# outer rings
ops.append(path('ring-outer', ring_d(C, 462, 455) + ' ' + ring_d(C, 447, 445), fill=GOLD))
ops.append(path('ring-inner', ring_d(C, 365, 362), fill=GOLD))

# arc text
ops.append(path('name-top', arc_text_d('cinzel-700', 'JEFFREY', 50, C, 386, -90, tracking=0.32), fill=BONE))
ops.append(path('name-bottom', arc_text_d('cinzel-700', 'GUNTLY', 50, C, 386+36, 90, tracking=0.32, inside=True), fill=BONE))
# star separators on ring band
st = []
for a in (0, 180):
    p = polar(C, 404, a)
    st.append(poly_d(star_poly(p, 16, 4.5, 4, -90 + a)))
for a in (-25, 25, 155, 205):
    pass
ops.append(path('stars', ' '.join(st), fill=GOLD))

# thorn crown: two interwoven vines
R = 315; A = 11; K = 12
def wv(sign):
    return Curve([polar(C, R + sign*A*math.sin(math.radians(K*360*i/1440)), 360*i/1440) for i in range(1441)])
v1, v2 = wv(1), wv(-1)
vine = [poly_d(ribbon(v1, 6.5)), poly_d(ribbon(v2, 6.5))]
thorns = []; leaves = []
for i in range(K):
    # peaks of v1 at sin=1 -> theta = (90 + 360*i)/K ; peaks of v2 outward at sin=-1
    a1 = (90 + 360*i)/K; a2 = (270 + 360*i)/K
    thorns.append(poly_d(thorn(polar(C, R+A+1, a1), a1 - 12, 30, 13, hook=0.25)))
    thorns.append(poly_d(thorn(polar(C, R-A-1, a2), a2 + 180 + 12, 20, 10, hook=-0.25)))
    # leaves at crossings (theta = 360*i/K and 180..), alternate out/in
    ac = 360*i/K
    leaves.append(poly_d(leaf(polar(C, R+2, ac), ac - 25, 40, 10, bend=0.1)))
    leaves.append(poly_d(leaf(polar(C, R-2, ac + 15), ac + 15 + 180 + 25, 28, 8, bend=-0.1)))
ops.append(path('crown-vine', ' '.join(vine + thorns), fill=GOLD))
ops.append(path('crown-leaves', ' '.join(leaves), fill=OX))

# X branches on diagonals and spikes on cardinals
sp = []; lv = []; mr = []; stars = []
for i in range(4):
    a = 45 + 90*i
    cv = Curve([add(polar(C, 132 + 168*j/40, a), mul(perp(rot((1,0),a)), 9*math.sin(math.pi*j/40*2))) for j in range(41)])
    sp.append(poly_d(ribbon(cv, 0, 0, prof=lambda f: 22*(1-f)**0.8 + 1)))
    for k, sd, L in ((0.18, 1, 24), (0.38, -1, 22), (0.58, 1, 18), (0.76, -1, 14)):
        q, tg = cv.at(k); w = (22*(1-k)**0.8 + 1)/2
        ang = math.degrees(math.atan2(tg[1], tg[0]))
        sp.append(poly_d(thorn(add(q, mul(perp(tg), sd*(w-1))), ang + sd*62, L, 10*(1-k)+4, hook=-sd*0.3)))
    for k, sd in ((0.3, -1), (0.52, 1)):
        q, tg = cv.at(k)
        ang = math.degrees(math.atan2(tg[1], tg[0])) + sd*50
        lv.append(poly_d(leaf(q, ang, 64, 15, bend=sd*0.06)))
        dd = rot((1,0), ang)
        mr.append(poly_d(ribbon(Curve([add(q, mul(dd, 8 + 42*j/10)) for j in range(11)]), 2.6, 0.4)))
    # cardinal
    b = 90*i
    sp.append(poly_d(thorn(polar(C, 160, b), b, 92, 12, hook=0.0, n=20)))
    stars.append(poly_d(star_poly(polar(C, 276, b), 13, 3.5, 4, b)))
    stars.append(poly_d(circle_poly(polar(C, 152, b), 5, 24)))
ops.append(path('branches', ' '.join(sp), fill=GOLD))
ops.append(path('leaves', ' '.join(lv), fill=OX))
ops.append(path('midribs', ' '.join(mr), fill='#5e1720'))
ops.append(path('cardinal-stars', ' '.join(stars), fill=BONE))

# center medallion
ops.append(path('medallion', poly_d(circle_poly(C, 128, 180)), fill=DEEP))
ops.append(path('medallion-ring', ring_d(C, 128, 124) + ' ' + ring_d(C, 116, 114.5), fill=GOLD))
dX, bx = text_d('cormorant-garamond-700', 'X', 230, 500, 500)
ops.append(path('X', dX, fill=GOLD))
dJ, _ = text_d('cormorant-garamond-700', 'J', 84, 446, 506)
dG, _ = text_d('cormorant-garamond-700', 'G', 84, 556, 500)
ops.append(path('JG', dJ + ' ' + dG, fill=BONE))

build('01-thorn-sigil', BG, ops)
