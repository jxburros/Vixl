import sys, math
from lib import *
F = 'im-fell-english-400.ttf'
INK = '#141414'
S = 184; DY = 42
ops = []
b1 = 440 + DY; b2 = 652 + DY
_, bj, endj = text_path(F, 'Jeffrey', S, 0, 0)
jw_l, jw_r = bj[0][1], bj[-1][3]
_, bx, _ = text_path(F, 'X', S*1.18, 0, 0)
gapX = 34
total = (jw_r - jw_l) + gapX + (bx[0][3] - bx[0][1])
x0 = 500 - total/2 - jw_l
dJ, boxesJ, _ = text_path(F, 'Jeffrey', S, x0, b1, per_glyph=True)
for i, (d, b) in enumerate(zip(dJ, boxesJ)):
    ops.append(shape(f'Jeffrey-{i}-{b[0]}', d, fill=INK))
Xx = x0 + jw_r + gapX - bx[0][1]
dX, boxX, _ = text_path(F, 'X', S*1.18, Xx, b1)
X = boxX[0]; xl, xt, xr, xb = X[1], X[2], X[3], X[4]
ops.append(shape('X-glyph', dX, fill=INK))
w = xr - xl; h = xb - xt
band = [(xl-6, xt-6), (xl+0.50*w, xt-6), (xl+0.50*w, xt+0.10*h), (xl+0.42*w, xt+0.13*h),
        (xr-0.08*w, xb-0.16*h), (xr+6, xb-0.10*h), (xr+6, xb+6), (xr-0.50*w, xb+6), (xr-0.50*w, xb-0.08*h),
        (xr-0.40*w, xb-0.12*h), (xl+0.06*w, xt+0.14*h), (xl-6, xt+0.10*h)]
ops.append(shape('X-band', "M " + " L ".join(f"{a:.1f} {c:.1f}" for a, c in band) + " Z", fill='#ff0000'))
ops.append({"type": "pathfinder", "name": "X", "targets": ["X-glyph", "X-band"], "mode": "intersect"})
_, bg, _ = text_path(F, 'Guntly', S, 0, 0)
gx = x0 + jw_l + 92 - bg[0][1]
dG, boxesG, _ = text_path(F, 'Guntly', S, gx, b2, per_glyph=True)
for i, (d, b) in enumerate(zip(dG, boxesG)):
    ops.append(shape(f'Guntly-{i}-{b[0]}', d, fill=INK))

# sprouting leaves: black outside the letter, carved white inside
glyph = {b[0]+str(i): d for i, (d, b) in enumerate(zip(dJ, boxesJ))}
glyphG = {b[0]+str(i): d for i, (d, b) in enumerate(zip(dG, boxesG))}
ops += sprout('sprout-J', glyph['J0'], (181, 432 + DY), -148, 40, 14, curl=0.10)
ops += sprout('sprout-X', dX, (811, 390 + DY), -28, 42, 14, curl=-0.12)
ops += sprout('sprout-G', glyphG['G0'], (246, 622 + DY), 196, 40, 14, curl=-0.10)
ops += sprout('sprout-l', glyphG['l4'], (624, 612 + DY), -128, 30, 11, curl=0.1)
vp = [(116, 632), (160, 586), (205, 548), (262, 516), (340, 501), (430, 503), (520, 513), (606, 508),
      (672, 489), (712, 463), (724, 448), (791, 368), (856, 293), (884, 256), (900, 214), (891, 178), (862, 161), (833, 168), (820, 192), (830, 213), (849, 216)]
vp = [(a, b + DY) for a, b in vp]
def prof(f):
    return 3 + 10 * smoothstep(0, 0.2, f) - 11.2 * smoothstep(0.80, 1.0, f)
fx = frac_of(vp, (724, 448 + DY))
thorns = [(0.10, -1, 15, 8), (0.17, 1, 15, 8), (0.30, -1, 16, 9), (0.40, 1, 15, 8), (0.465, -1, 16, 9), (0.545, 1, 15, 8),
          (0.63, -1, 15, 8), (0.705, 1, 15, 8), (0.79, 1, 14, 8), (0.85, -1, 12, 7), (0.885, 1, 11, 6), (0.95, 1, 9, 5)]
leaves = [(0.02, 1, 32, 13, 38, 4), (0.055, -1, 30, 12, 48, 4), (0.245, 1, 32, 13, 48, 5), (0.35, -1, 28, 12, 50, 4),
          (0.505, -1, 30, 12, 45, 5), (0.60, 1, 26, 11, 50, 4), (fx - 0.01, -1, 30, 12, 58, 5),
          (0.83, 1, 28, 11, 45, 4), (0.915, -1, 22, 9, 60, 3)]
ops += vine_ops('vine', vp, prof, thorns, leaves, ink=INK)
dump(ops, 'ops.json')
