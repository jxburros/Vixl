import sys, math
from lib import *
FI = 'playfair-display-400-italic.ttf'; FR = 'playfair-display-400.ttf'
INK = '#121212'
ops = []
SX = 380
_, bx, _ = text_path(FR, 'X', SX, 0, 0)
xw = bx[0][3] - bx[0][1]; xh = bx[0][4] - bx[0][2]
Xx = 500 - xw/2 - bx[0][1]; Xb = 500 + xh/2
dX, boxX, _ = text_path(FR, 'X', SX, Xx, Xb)
X = boxX[0]; xl, xt, xr, xb = X[1], X[2], X[3], X[4]
w = xr - xl; h = xb - xt
print('X', [round(v) for v in (xl, xt, xr, xb)], file=sys.stderr)
ops.append(shape('X-glyph', dX, fill=INK))
L = lambda y: 448 + 0.65*(y-450) - 2
R = lambda y: 487 + 0.65*(y-450) + 2
yt = xt + 0.075*h; yb = xb - 0.075*h
band = [(xl-8, xt-8), (xl+0.55*w, xt-8), (xl+0.55*w, yt), (R(yt), yt), (R(yb), yb), (xr+8, yb), (xr+8, xb+8),
        (xr-0.55*w, xb+8), (xr-0.55*w, yb), (L(yb), yb), (L(yt), yt), (xl-8, yt)]
ops.append(shape('X-band', "M " + " L ".join(f"{a:.1f} {c:.1f}" for a, c in band) + " Z", fill='#ff0000'))
ops.append({"type": "pathfinder", "name": "X", "targets": ["X-glyph", "X-band"], "mode": "intersect"})
SW = 114
_, bj, _ = text_path(FI, 'Jeffrey', SW, 0, 0)
jr = max(b[3] for b in bj)
jb = xt - 44
dJ, boxesJ, _ = text_path(FI, 'Jeffrey', SW, xl + 0.30*w - jr, jb)
ops.append(shape('Jeffrey', dJ, fill=INK))
_, bg, _ = text_path(FI, 'Guntly', SW, 0, 0)
gb = xb + 34 + 0.78*SW
dG, boxesG, _ = text_path(FI, 'Guntly', SW, xr - 0.30*w - bg[0][1], gb)
ops.append(shape('Guntly', dG, fill=INK))
print('J', [round(v) for v in boxesJ[0][1:3]], round(max(b[3] for b in boxesJ)), 'G', round(boxesG[0][1]), round(max(b[3] for b in boxesG)), round(max(b[4] for b in boxesG)), file=sys.stderr)

a = (xl + 0.075*w, xb); b = (xr - 0.075*w, xt)
dx, dy = b[0]-a[0], b[1]-a[1]
def along(t): return (a[0] + dx*t, a[1] + dy*t)
vp = [(222, 778), (230, 760), (214, 744), (188, 754), (184, 786), (210, 808), (252, 804), (288, 772), along(-0.30), along(-0.12), a, along(0.5), b, along(1.14), along(1.30),
      (712, 228), (748, 196), (790, 192), (816, 214), (812, 246), (786, 256), (770, 240), (778, 222)]
def prof(f):
    return 1.6 + 5.6 * smoothstep(0.0, 0.2, f) - 5.4 * smoothstep(0.80, 1.0, f)
thorns = [(0.09, -1, 12, 6), (0.16, -1, 16, 7), (0.225, 1, 18, 8), (0.285, -1, 18, 8), (0.32, 1, 18, 8),
          (0.555, -1, 18, 8), (0.61, 1, 18, 8), (0.665, -1, 17, 7), (0.72, 1, 16, 7), (0.78, -1, 15, 6), (0.84, 1, 13, 6), (0.90, -1, 10, 5)]
leaves = [(0.13, 1, 30, 11, 50, 4), (0.20, -1, 46, 15, 45, 6), (0.255, 1, 44, 14, 48, 6),
          (0.60, 1, 46, 15, 48, 6), (0.665, -1, 44, 14, 45, 6), (0.73, 1, 38, 12, 50, 5), (0.87, -1, 30, 11, 55, 4)]
ops += vine_ops('vine', vp, prof, thorns, leaves, ink=INK)
ops += sprout('sprout-X', dX, (540, 575), -32, 46, 14, curl=-0.12, ink=INK)
dump(ops, 'ops.json')
