from lib import *
PAPER = '#f2ece0'; INK = '#141210'; RED = '#b3342a'
rng = random.Random(11)
ops = []

def noise1(seed, n=6):
    r = random.Random(seed); ph = [r.uniform(0, 6.28) for _ in range(n)]; fr = [r.uniform(1, 9) for _ in range(n)]
    am = [r.uniform(0.3, 1)/(k+1) for k in range(n)]
    return lambda f: sum(a*math.sin(fr_*f*6.28 + p) for a, fr_, p in zip(am, fr, ph))

def brush_stroke(curve, prof, seed, bristles=18, dry_from=0.45, n=160):
    """sumi stroke from overlapping bristle ribbons; past dry_from bristles thin, skip and end at staggered lengths"""
    r = random.Random(seed)
    polys = []
    p0, t0 = curve.at(0)
    for b in range(bristles):
        u = (b + 0.5)/bristles*2 - 1
        endf = 1 - r.uniform(0, 0.28)*(0.4 + abs(u))
        if abs(u) > 0.8: endf -= r.uniform(0.05, 0.2)
        nz = noise1(seed*31 + b, 5)
        # skips (dry gaps) in tail region
        skips = []
        for _ in range(r.randint(0, 2)):
            s0 = r.uniform(dry_from + 0.05, endf - 0.08)
            skips.append((s0, s0 + r.uniform(0.02, 0.07)))
        segs = [(0.0, endf)]
        for s0, s1 in sorted(skips):
            last = segs.pop(); 
            if s0 > last[0] + 0.02 and s1 < last[1] - 0.02:
                segs += [(last[0], s0), (s1, last[1])]
            else:
                segs.append(last)
        for sa, sb in segs:
            sL, sR = [], []
            m = max(12, int(n*(sb-sa)))
            for i in range(m+1):
                f = sa + (sb-sa)*i/m
                p, t = curve.at(f); nn = perp(t); w = prof(f)/2
                dry = max(0, (f - dry_from)/(1 - dry_from))
                spread = 1 + 0.12*dry
                center = u*w*spread + nz(f)*w*0.04
                pre = 2.8 - 1.1*min(1, f/dry_from)
                half = (w/bristles)*(pre - 1.05*dry) * (0.85 + 0.3*nz(f + 0.3))
                # taper the very ends of each segment
                e = min(1, (f - sa)/0.015 + (0.3 if sa == 0 else 0), (sb - f)/0.04)
                half = max(0.25, half*max(0.15, e))
                sL.append(add(p, mul(nn, center + half))); sR.append(add(p, mul(nn, center - half)))
            polys.append(sL + sR[::-1])
    return polys

# --- main heavy stroke (top-left to bottom-right)
c1 = Curve.beziers([((215, 225), (400, 330), (570, 520), (800, 820))], 200)
prof1 = lambda f: 118*(0.62 + 0.38*math.sin(min(1, f/0.3)*math.pi/2)) * (1 - 0.35*max(0, f-0.5)/0.5)
P1 = brush_stroke(c1, prof1, 5, bristles=20, dry_from=0.42)
# angled press at the landing point (brush set down obliquely)
p0, t0 = c1.at(0.0)
nzh = noise1(77, 4)
hc = add(p0, mul(t0, 18)); ang0 = math.atan2(t0[1], t0[0]) + 0.35
blob = []
for k in range(64):
    th = 2*math.pi*k/64
    rx, ry = 30, 39
    x_, y_ = rx*math.cos(th), ry*math.sin(th)
    rr = 1 + 0.05*nzh(k/64)
    blob.append((hc[0] + rr*(x_*math.cos(ang0) - y_*math.sin(ang0)), hc[1] + rr*(x_*math.sin(ang0) + y_*math.cos(ang0))))
P1.append(blob)

# --- thin vine stroke (top-right to bottom-left) with a curl at the end
c2 = Curve.beziers([((772, 175), (700, 260), (610, 380), (520, 470)),
                    ((520, 470), (400, 590), (300, 660), (240, 790)),
                    ((240, 790), (205, 865), (270, 905), (300, 865)),
                    ((300, 865), (318, 840), (296, 822), (282, 838))], 140)
prof2 = lambda f: (3 + 30*math.sin(min(1, f/0.35)*math.pi/2)) * (1 - 0.85*max(0, f-0.35)/0.65) + 1.2
st = [ribbon(c2, 0, prof=prof2, n=500)]
# thorns as brush flicks
for f, sd, s in ((0.07, 1, 0.7), (0.14, -1, 0.9), (0.24, 1, 1.0), (0.38, -1, 1.0), (0.47, 1, 0.95), (0.56, -1, 0.85), (0.64, 1, 0.75), (0.71, -1, 0.6)):
    q, tg = c2.at(f); w = prof2(f)/2
    ang = math.degrees(math.atan2(tg[1], tg[0]))
    st.append(thorn(add(q, mul(perp(tg), sd*w*0.6)), ang + sd*55, 34*s, (w*1.2 + 6)*s, hook=-sd*0.3))
# leaves as single brush-press shapes
lvs = []
for f, sd, s in ((0.19, -1, 1.0), (0.33, 1, 1.15), (0.52, -1, 0.9), (0.68, 1, 0.7)):
    q, tg = c2.at(f)
    ang = math.degrees(math.atan2(tg[1], tg[0])) + sd*45
    lvs.append(leaf(q, ang, 118*s, 31*s, bend=-sd*0.14))
P2 = st + lvs

# splatter droplets near the head
sp = []
for i in range(14):
    a = rng.uniform(170, 260); d = rng.uniform(62, 120)
    c = polar((215, 225), d, a)
    if c[0] < 40 or c[1] < 40: continue
    sp.append(circle_poly(c, rng.choice([1.5, 2, 2.5, 3.5, 5]), 14))
ops.append(path('stroke-heavy', D(P1), fill=INK))
ops.append(path('stroke-vine', D(P2), fill=INK))
ops.append(path('splatter', D(sp), fill=INK))

# name + seal
dN, bb = text_d('cormorant-garamond-600', 'JEFFREY X GUNTLY', 34, 892, 430, tracking=0.28, rotate=90)
ops.append(path('name', dN, fill=INK))
# seal
sc = (892, 760); S = 74
seal = [(sc[0]-S/2 + rng.uniform(-1.5,1.5), sc[1]-S/2 + rng.uniform(-1.5,1.5)) for _ in range(1)]
def jitter_rect(cx, cy, w, h, j, seed):
    rr = random.Random(seed); pts = []
    corners = [(cx-w/2, cy-h/2), (cx+w/2, cy-h/2), (cx+w/2, cy+h/2), (cx-w/2, cy+h/2)]
    for k in range(4):
        a_, b_ = corners[k], corners[(k+1) % 4]
        for i in range(12):
            t = i/12; pts.append((a_[0]+(b_[0]-a_[0])*t + rr.uniform(-j, j), a_[1]+(b_[1]-a_[1])*t + rr.uniform(-j, j)))
    return pts
ops.append(path('seal', poly_d(jitter_rect(sc[0], sc[1], S, S*1.35, 1.6, 3)), fill=RED))
dJ, _ = text_d('cormorant-garamond-700', 'J', 40, sc[0], sc[1]-22)
dG, _ = text_d('cormorant-garamond-700', 'G', 40, sc[0], sc[1]+23)
ops.append(path('seal-letters', dJ + ' ' + dG, fill=PAPER))
build('03-sumi-thorn', PAPER, ops)
