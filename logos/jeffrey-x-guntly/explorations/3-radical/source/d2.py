from lib import *
W, H = 800, 1360
BONE = '#efe5cf'; INK = '#1d1813'; NIGHT = '#1b1930'; GOLD = '#c39a45'; OX = '#7c1f2b'; SAGE = '#8d9c62'; SAGED = '#5d6b3b'
ops = []
rng = random.Random(7)

# card borders
def rect(x0,y0,x1,y1): return [(x0,y0),(x1,y0),(x1,y1),(x0,y1)]
ops.append(path('borders', poly_d(rect(22,22,W-22,H-22)) + ' ' + poly_d(rect(26,26,W-26,H-26),-1) + ' ' + poly_d(rect(34,34,W-34,H-34)) + ' ' + poly_d(rect(35.5,35.5,W-35.5,H-35.5),-1), fill=INK))

# arch window
ax0, ax1 = 92, 708; ar = (ax1-ax0)/2; acy = 170 + ar; aby = 1090
def arch(x0, x1, cy, by, r):
    pts = [(x0, by), (x0, cy)]
    pts += [polar((400, cy), r, 180 + 180*i/120) for i in range(121)]
    pts += [(x1, cy), (x1, by)]
    return pts
ops.append(path('arch-sky', poly_d(arch(ax0, ax1, acy, aby, ar)), fill=NIGHT))
# arch double frame lines (rings)
ops.append(path('arch-frame', poly_d(arch(ax0-14, ax1+14, acy, aby+14, ar+14)) + ' ' + poly_d(arch(ax0-8, ax1+8, acy, aby+8, ar+8), -1)
               + ' ' + poly_d(arch(ax0-3, ax1+3, acy, aby+3, ar+3)) + ' ' + poly_d(arch(ax0, ax1, acy, aby, ar), -1), fill=INK))

# stars in sky (seeded, avoid center lane)
stars = []
for i in range(70):
    x = rng.uniform(ax0+18, ax1-18); y = rng.uniform(190, 1060)
    if (x-400)**2/ (ar-20)**2 + 0 > 1 and False: continue
    if y < acy and math.dist((x, y), (400, acy)) > ar-18: continue
    r = rng.choice([1.3, 1.6, 2.0, 2.4])
    stars.append(poly_d(circle_poly((x, y), r, 10)))
for (x, y, s) in [(122, 600, 13), (682, 470, 11), (640, 640, 13), (160, 760, 10), (300, 250, 8), (560, 860, 9)]:
    stars.append(poly_d(star_poly((x, y), s, s*0.22, 4)))
ops.append(path('stars', ' '.join(stars), fill=BONE))
ops.append({'type': 'opacity', 'target': 'stars', 'value': 0.85})

# crescent moon
moon_c = (400, 330)
m = circle_poly(moon_c, 62, 120)
ops.append(path('moon-disc', poly_d(m), fill=GOLD))
ops.append(path('moon-bite', poly_d(circle_poly((424, 315), 56, 120)), fill=NIGHT))

# two vines rising from the ground, crossing to form an X
def vineA(mirror):
    segs = [[(150, 1080), (185, 900), (330, 800), (400, 680)],
            [(400, 680), (480, 570), (600, 480), (618, 360)],
            [(618, 360), (630, 285), (600, 250), (570, 252)]]
    if mirror:
        segs = [[(800-x, y) for x, y in sg] for sg in segs]
    return Curve.beziers([tuple(sg) for sg in segs], 120)
polys = []; lvs = []; ribs = []; curls = []
for mi in (0, 1):
    cv = vineA(mi)
    sgn = -1 if mi else 1
    th = [(f, s*sgn, 1.0 - f*0.5) for f, s in ((0.05, 1), (0.11, -1), (0.18, 1), (0.25, -1), (0.33, 1), (0.42, -1), (0.56, 1), (0.63, -1), (0.7, 1), (0.77, -1), (0.84, 1), (0.9, -1))]
    lf = [(f, s*sgn, sc) for f, s, sc in ((0.08, -1, 1.2), (0.15, 1, 1.1), (0.28, -1, 1.1), (0.6, 1, 0.95), (0.67, -1, 0.9), (0.74, 1, 0.85), (0.81, -1, 0.75), (0.87, 1, 0.65), (0.93, -1, 0.5))]
    st, lv, rb = vine(cv, 20, 3.5, th, lf, leaf_len=64, leaf_w=16, thorn_len=24)
    polys += st; lvs += lv; ribs += rb
    # curl tendril at tip
    end, tg = cv.at(1.0)
    ang = math.degrees(math.atan2(tg[1], tg[0]))
    cp = spiral_pts(end, ang, 20, turns=1.6, shrink=0.3, cw=sgn*-1 if False else (1 if mi == 0 else -1), n=70)
    curls.append(ribbon(Curve(cp), 0, prof=lambda f: 3.5*(1-f)+0.8, n=90))
ops.append(path('vines', D(polys + curls), fill=GOLD))
ops.append(path('vine-leaves', D(lvs), fill=SAGE))
ops.append(path('vine-ribs', D(ribs), fill=SAGED))

# blossom at the crossing point - find approx crossing at x=400
cross = (400, 680)
pet = []
for k in range(5):
    a = -90 + 72*k
    pet.append(poly_d(leaf(cross, a, 40, 19)))
ops.append(path('rose', ' '.join(pet), fill=OX))
ops.append(path('rose-heart', poly_d(circle_poly(cross, 8, 24)), fill=GOLD))

# ground mound
ground = [(ax0, aby)] + [(ax0 + (ax1-ax0)*i/60, aby - 34*math.sin(math.pi*i/60)**1.4 - 6*math.sin(i/3.0)) for i in range(61)] + [(ax1, aby)]
ops.append(path('ground', poly_d(ground), fill=INK))

# numeral medallion at arch apex
apex = (400, 100)
ops.append(path('numeral-disc', poly_d(circle_poly(apex, 46, 120)), fill=BONE))
ops.append(path('numeral-ring', ring_d(apex, 46, 42) + ' ' + ring_d(apex, 37, 35.5), fill=INK))
dX, _ = text_d('cinzel-700', 'X', 44, apex[0], apex[1])
ops.append(path('numeral', dX, fill=OX))
# small flourish dots beside medallion
fl = []
for sx in (-1, 1):
    fl.append(poly_d(star_poly((400 + sx*150, 100), 10, 2.6, 4)))
    fl.append(poly_d(ribbon(Curve([(400 + sx*66, 100), (400 + sx*134, 100)]), 2.2, 2.2)))
    fl.append(poly_d(ribbon(Curve([(400 + sx*166, 100), (400 + sx*300, 100)]), 2.2, 0.3)))
ops.append(path('top-flourish', ' '.join(fl), fill=INK))

# banner
by = 1150; bh = 82; bx0, bx1 = 110, 690
tail = 54
ban = [(bx0, by), (bx1, by), (bx1, by+bh), (bx0, by+bh)]
lt = [(bx0-tail+6, by+22), (bx0+30, by+22), (bx0+30, by+bh+22), (bx0-tail+6, by+bh+22), (bx0-tail+30, by+bh/2+22)]
rt = [(800-x, y) for x, y in lt]
ops.append(path('banner-tails', poly_d(lt) + ' ' + poly_d(rt), fill='#5a1520'))
ops.append(path('banner-folds', poly_d([(bx0, by+bh), (bx0+30, by+bh+22), (bx0+30, by+bh)]) + ' ' + poly_d([(bx1, by+bh), (bx1-30, by+bh+22), (bx1-30, by+bh)]), fill='#3d0d15'))
ops.append(path('banner', poly_d(ban), fill=OX))
ops.append(path('banner-line', poly_d([(bx0+10, by+8), (bx1-10, by+8), (bx1-10, by+bh-8), (bx0+10, by+bh-8)]) + ' ' + poly_d([(bx0+12, by+10), (bx1-12, by+10), (bx1-12, by+bh-10), (bx0+12, by+bh-10)], -1), fill=GOLD))
dN, bb = text_d('cinzel-700', 'JEFFREY X GUNTLY', 38, 400, by + bh/2, tracking=0.12)
ops.append(path('name', dN, fill=BONE))
bs = [poly_d(star_poly((400 + dx, 1290), sz, sz*0.25, 4)) for dx, sz in ((-40, 8), (0, 13), (40, 8))]
ops.append(path('foot-stars', ' '.join(bs), fill=INK))

build('02-tarot-x', BONE, ops, size='800x1360')
