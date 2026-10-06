import sys, math
from lib import *
FI = 'cormorant-garamond-500-italic.ttf'; FC = 'cormorant-garamond-500.ttf'
INK = '#141414'
ops = []
def arch(x0, x1, ytop, ybot):
    r = (x1 - x0) / 2; cx = (x0 + x1) / 2; cy = ytop + r
    k = 0.5523 * r
    return (f"M {x0} {ybot} L {x0} {cy} C {x0} {cy-k} {cx-k} {ytop} {cx} {ytop} C {cx+k} {ytop} {x1} {cy-k} {x1} {cy} L {x1} {ybot} Z")
# frame: thick outer rule, thin inner rule
ops.append(shape('frame-outer', arch(232, 768, 92, 908), fill='transparent', stroke=INK, sw=7, pad=5, line_join='miter'))
ops.append(shape('frame-inner', arch(250, 750, 110, 890), fill='transparent', stroke=INK, sw=2, pad=3, line_join='miter'))
def center_text(name, font, txt, size, baseline, tracking=0, cx=500):
    _, b, _ = text_path(font, txt, size, 0, 0, tracking=tracking)
    l, r = b[0][1], max(x[3] for x in b)
    d, b, _ = text_path(font, txt, size, cx - (l + r)/2, baseline, tracking=tracking)
    return shape(name, d, fill=INK)
ops.append(center_text('ex-libris', FC, 'EX LIBRIS', 36, 238, tracking=14))
# small diamond flanking dots
for x in (338, 662):
    ops.append(shape(f'dot{x}', f"M {x} 220 L {x+6} 226 L {x} 232 L {x-6} 226 Z", fill=INK))

EMB0 = len(ops)
# ---- emblem: quill (/) crossed with a thorny rose stem (\) ----
C = (500, 470)
# thorny stem: root bottom-right -> top-left with leaves and a small rose bud
stem = [(646, 668), (604, 612), (554, 548), (500, 486), (446, 424), (398, 368), (362, 326)]
prof = lambda f: 13 - 8 * f
th = [(0.08, 1, 24, 14), (0.18, -1, 26, 14), (0.28, 1, 24, 13), (0.70, -1, 20, 11), (0.80, 1, 17, 10), (0.89, -1, 14, 8)]
lv = [(0.13, -1, 48, 19, 50, 6), (0.23, 1, 40, 16, 50, 5), (0.75, 1, 44, 17, 48, 5), (0.85, -1, 36, 14, 50, 4)]
# quill: nib bottom-left -> plume top-right
N = (356, 676); T = (664, 300)
ux, uy = T[0]-N[0], T[1]-N[1]; Lq = math.hypot(ux, uy); ux, uy = ux/Lq, uy/Lq
vx, vy = -uy, ux   # left normal
def Q(u, v): return (N[0] + ux*u + vx*v, N[1] + uy*u + vy*v)
def Qs(u, v): p = Q(u, v); return f"{p[0]:.1f} {p[1]:.1f}"
# draw the stem first, then a white gap and the quill on top
ops += vine_ops('stem', stem, prof, th, lv, ink=INK)
sp, L = sample(catmull(stem), 80); tip, t = at(sp, L, 1.0); a = math.atan2(t[1], t[0])
ca, sa = math.cos(a), math.sin(a)
def P(u, v): return (tip[0] + ca*u - sa*v, tip[1] + sa*u + ca*v)
def Ps(u, v): p = P(u, v); return f"{p[0]:.1f} {p[1]:.1f}"
ops.append(shape('bud', f"M {Ps(2,0)} C {Ps(-6,-30)} {Ps(44,-36)} {Ps(80,-5)} C {Ps(64,20)} {Ps(28,36)} {Ps(2,0)} Z", fill=INK))
pa, pb = P(34, -28), P(50, 22)
ops.append(shape('bud-petal', f"M {pa[0]:.1f} {pa[1]:.1f} Q {Ps(64,-3)} {pb[0]:.1f} {pb[1]:.1f}", fill='transparent', stroke='#ffffff', sw=3, line_cap='round', pad=3))
for k, s_ in enumerate((-1, 1)):
    ops.append(shape(f'bud-sepal{k}', leaf(P(1, 0), a + s_*0.55, 58, 13, curl=s_*0.16), fill=INK, stroke='#ffffff', sw=3, pad=3))
ops.append(shape('bud-hip', circle(P(2, 0), 11), fill=INK, stroke='#ffffff', sw=2.5, pad=3))
# vane outline (asymmetric feather) from u=120 to tip
Lt = Lq
vane = (f"M {Qs(112, 0)} C {Qs(170, 30)} {Qs(300, 52)} {Qs(Lt-30, 30)} C {Qs(Lt-8, 18)} {Qs(Lt+6, 6)} {Qs(Lt+8, 0)} "
        f"C {Qs(Lt-30, -10)} {Qs(320, -34)} {Qs(200, -36)} C {Qs(160, -34)} {Qs(130, -20)} {Qs(112, 0)} Z")
gap = ribbon([(Q(60, 0), Q(140, 0), Q(300, 0), Q(Lt, 0))], 0, 0, prof=lambda f: 26)
ops.append(shape('quill-gap', f"M {Qs(40,0)} L {Qs(40,0)} Z", fill='transparent'))
ops.append(shape('quill-halo', vane, fill='#ffffff', stroke='#ffffff', sw=14, pad=8))
ops.append(shape('quill-shaft-halo', ribbon([(Q(0, 0), Q(40, 0), Q(80, 0), Q(130, 0))], 0, 0, prof=lambda f: 2 + 9*f + 12), fill='#ffffff'))
ops.append(shape('quill-vane', vane, fill=INK))
# shaft (calamus) from nib to vane
ops.append(shape('quill-shaft', ribbon([(Q(0, 0), Q(40, 0), Q(80, 0), Q(130, 0))], 0, 0, prof=lambda f: 1.5 + 8*min(1, f*1.4)), fill=INK))
# nib slit
ops.append(shape('nib-slit', f"M {Qs(4, 0)} L {Qs(26, 0)}", fill='transparent', stroke='#ffffff', sw=1.6, line_cap='round', pad=3))
# rachis (white line) along the vane
# barb splits: white notches cut into vane edges
barbs = []
for u, side, ln in [(176, 1, 40), (226, 1, 44), (292, 1, 40), (360, 1, 32), (418, 1, 22), (196, -1, 36), (258, -1, 40), (330, -1, 32), (396, -1, 22)]:
    o1 = Q(u + 16, side*80); o2 = Q(u + 2, side*80); inner = Q(u - ln, side*12)
    nm = f'barb{u}{"a" if side > 0 else "b"}'; barbs.append(nm)
    ops.append(shape(nm, f"M {o1[0]:.1f} {o1[1]:.1f} L {o2[0]:.1f} {o2[1]:.1f} L {inner[0]:.1f} {inner[1]:.1f} Z", fill='#ffffff'))
ops.append({"type": "pathfinder", "name": "quill-feather", "targets": ["quill-vane"] + barbs, "mode": "subtract"})
ops.append(shape('rachis', f"M {Qs(118, 0)} C {Qs(200, 2)} {Qs(320, 4)} {Qs(Lt-4, 1)}", fill='transparent', stroke='#ffffff', sw=3.2, line_cap='round', pad=3))
for o in ops[EMB0:]:
    if 'y' in o: o['y'] += 14
ops.append(center_text('name', FI, 'Jeffrey X Guntly', 66, 788))
# divider: thin rule with central thorn sprig
ops.append(shape('rule-l', "M 330 838 L 478 838", fill='transparent', stroke=INK, sw=1.6, pad=2))
ops.append(shape('rule-r', "M 522 838 L 670 838", fill='transparent', stroke=INK, sw=1.6, pad=2))
ops.append(shape('rule-leafL', leaf((500, 838), math.pi, 20, 9), fill=INK))
ops.append(shape('rule-leafR', leaf((500, 838), 0, 20, 9), fill=INK))
dump(ops, 'ops.json')
