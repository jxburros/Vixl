import sys, math
from lib import *
FL = 'unifrakturmaguntia-400.ttf'; FC = 'cormorant-garamond-500.ttf'
INK = '#121212'
ops = []
C = (500, 410)
def branch(name, p0, p1, bow, w0, w1, thorns, side_bow=1):
    mx, my = (p0[0]+p1[0])/2, (p0[1]+p1[1])/2
    dx, dy = p1[0]-p0[0], p1[1]-p0[1]; n = math.hypot(dx, dy)
    nx, ny = -dy/n, dx/n
    mid = (mx + nx*bow, my + ny*bow)
    q1 = ((p0[0]+mid[0])/2 + nx*bow*0.25, (p0[1]+mid[1])/2 + ny*bow*0.25)
    q2 = ((p1[0]+mid[0])/2 + nx*bow*0.25, (p1[1]+mid[1])/2 + ny*bow*0.25)
    pts = [p0, q1, mid, q2, p1]
    prof = lambda f: w0 + (w1 - w0) * f**0.9
    return pts, prof
# Branch A: bottom-left -> top-right (rose stem), Branch B: bottom-right -> top-left (bramble)
A, profA = branch('A', (268, 676), (736, 178), 26, 24, 6, [])
B, profB = branch('B', (732, 676), (264, 178), -26, 24, 6, [])
thA = [(0.07, 1, 28, 17), (0.15, -1, 30, 17), (0.24, 1, 28, 16), (0.31, -1, 24, 14), (0.63, 1, 24, 13), (0.70, -1, 22, 12), (0.78, 1, 19, 10), (0.85, -1, 15, 8)]
thB = [(0.07, -1, 28, 17), (0.15, 1, 30, 17), (0.24, -1, 28, 16), (0.31, 1, 24, 14), (0.63, -1, 24, 13), (0.70, 1, 22, 12), (0.78, -1, 19, 10), (0.85, 1, 15, 8)]
lvA = [(0.90, -1, 46, 18, 42, 5), (0.74, -1, 50, 19, 48, 6)]
lvB = [(0.90, 1, 46, 18, 42, 5), (0.74, 1, 50, 19, 48, 6), (0.995, -1, 44, 17, 25, 1), (0.995, 1, 40, 15, 28, 1)]
ops += vine_ops('branchB', B, profB, thB, lvB, ink=INK)
# white halo where A crosses over B
segA = catmull(A)
ops.append(shape('crossing-gap', ribbon(segA, 0, 0, prof=lambda f: profA(f) + 18 if 0.40 < f < 0.60 else 0.01, n=400), fill='#ffffff'))
ops += vine_ops('branchA', A, profA, thA, lvA, ink=INK)
# rosebud at top of A
sp, L = sample(segA, 80); tip, t = at(sp, L, 1.0)
ang = math.atan2(t[1], t[0])
ca, sa = math.cos(ang), math.sin(ang)
def P(u, v): return (tip[0] + ca*u - sa*v, tip[1] + sa*u + ca*v)
hip = P(4, 0)
def Ps(u, v): p = P(u, v); return f"{p[0]:.1f} {p[1]:.1f}"
ops.append(shape('rosebud', f"M {Ps(4,0)} C {Ps(-6,-34)} {Ps(50,-40)} {Ps(92,-6)} C {Ps(74,22)} {Ps(32,40)} {Ps(4,0)} Z", fill=INK))
p_a = P(40, -31); p_b = P(58, 25)
ops.append(shape('petal-line1', f"M {p_a[0]:.1f} {p_a[1]:.1f} Q {P(72,-4)[0]:.1f} {P(72,-4)[1]:.1f} {p_b[0]:.1f} {p_b[1]:.1f}", fill='transparent', stroke='#ffffff', sw=4, line_cap='round', pad=3))
for k, s_ in enumerate((-1, 1)):
    ops.append(shape(f'sepal{k}', leaf(P(2, 0), ang + s_*0.55, 66, 15, curl=s_*0.16), fill=INK, stroke='#ffffff', sw=4, pad=3))
ops.append(shape('hip', circle(hip, 12), fill=INK, stroke='#ffffff', sw=3, pad=3))
# initials
SL = 220
def place(ch, cx, cy):
    _, b, _ = text_path(FL, ch, SL, 0, 0)
    bx0, by0, bx1, by1 = b[0][1:]
    ox = cx - (bx0 + bx1)/2; oy = cy - (by0 + by1)/2
    d, bb, _ = text_path(FL, ch, SL, ox, oy)
    print(ch, [round(v) for v in bb[0][1:]], file=sys.stderr)
    return d
ops.append(shape('J', place('J', 314, 444), fill=INK))
ops.append(shape('G', place('G', 692, 432), fill=INK))
# wordmark
SW = 44; tr = 9
_, b, end = text_path(FC, 'JEFFREY X GUNTLY', SW, 0, 0, tracking=tr)
wl, wr = b[0][1], max(x[3] for x in b)
d, b, _ = text_path(FC, 'JEFFREY X GUNTLY', SW, 500 - (wl + wr)/2, 800, tracking=tr)
ops.append(shape('wordmark', d, fill=INK))
for o in ops:
    if 'y' in o: o['y'] += 32
dump(ops, 'ops.json')
