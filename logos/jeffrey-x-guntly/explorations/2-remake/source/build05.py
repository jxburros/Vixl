import sys, math
from lib import *
FC = 'cinzel-500.ttf'
INK = '#141414'
C = (500, 500)
ops = []
ops.append(shape('ring-outer', circle(C, 384), fill='transparent', stroke=INK, sw=7, pad=5))
ops.append(shape('ring-inner', circle(C, 368), fill='transparent', stroke=INK, sw=2, pad=3))
ops.append(shape('ring-core', circle(C, 262), fill='transparent', stroke=INK, sw=2, pad=3))
SZ = 58; TR = 16
ops.append(shape('arc-jeffrey', arc_text(FC, 'JEFFREY', SZ, C, 292, -90, tracking=TR), fill=INK))
cap = 0.70 * SZ
ops.append(shape('arc-guntly', arc_text(FC, 'GUNTLY', SZ, C, 292 + cap, 90, tracking=TR, bottom=True), fill=INK))
# side ornaments at 9 and 3 o'clock: leaf pair + thorn dot
for k, ang in enumerate((180, 0)):
    th = math.radians(ang); r = 315
    p = (C[0] + r*math.cos(th), C[1] + r*math.sin(th))
    tang = th + math.pi/2
    ops.append(shape(f'orn{k}a', leaf(p, tang, 26, 11), fill=INK))
    ops.append(shape(f'orn{k}b', leaf(p, tang + math.pi, 26, 11), fill=INK))
    ops.append(shape(f'orn{k}c', circle(p, 5), fill=INK))
# central crossroads: two thorny vines crossing, ends curling into hooks
rel = [(-136, 178), (-110, 124), (-56, 56), (0, 0), (56, -56), (102, -110), (126, -158), (122, -196), (98, -214), (72, -206), (66, -182), (82, -170), (96, -178)]
A = [(C[0] + x, C[1] + 12 + y) for x, y in rel]
B = [(C[0] - x, C[1] + 12 + y) for x, y in rel]
prof = lambda f: 4 + 11 * smoothstep(0, 0.10, f) - 13 * smoothstep(0.55, 1.0, f)
thA = [(0.10, 1, 22, 12), (0.17, -1, 24, 13), (0.25, 1, 23, 12), (0.50, -1, 20, 11), (0.585, 1, 18, 10), (0.66, 1, 14, 8), (0.73, 1, 11, 6)]
thB = [(f, -s, l, w) for f, s, l, w in thA]
lvA = [(0.04, -1, 40, 16, 55, 4), (0.05, 1, 34, 14, 60, 3), (0.545, -1, 38, 15, 50, 5), (0.62, -1, 30, 12, 55, 4)]
lvB = [(f, -s, l, w, a, st) for f, s, l, w, a, st in lvA]
ops += vine_ops('vineB', B, prof, thB, lvB, ink=INK)
segA = catmull(A)
ops.append(shape('cross-gap', ribbon(segA, 0, 0, prof=lambda f: prof(f) + 16 if 0.33 < f < 0.435 else 0.01, n=400), fill='#ffffff'))
ops += vine_ops('vineA', A, prof, thA, lvA, ink=INK)
# guiding star above the crossing
def star4(c, R, r):
    pts = []
    for k in range(8):
        a = -math.pi/2 + k*math.pi/4
        rr = R if k % 2 == 0 else r
        pts.append((c[0] + rr*math.cos(a), c[1] + rr*math.sin(a)))
    return "M " + " L ".join(f"{x:.1f} {y:.1f}" for x, y in pts) + " Z"
ops.append(shape('star', star4((500, 366), 26, 6), fill=INK))
dump(ops, 'ops.json')
