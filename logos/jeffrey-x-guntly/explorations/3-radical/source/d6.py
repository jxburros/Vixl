from lib import *
BG = '#151311'; LEAD = '#0d0c0b'; BONE = '#e9dfc9'
C = (500, 438)
LW = 7
ops = []
def sector(r0, r1, a0, a1, n=24):
    out = [polar(C, r1, a0 + (a1-a0)*i/n) for i in range(n+1)]
    inn = [polar(C, r0, a1 - (a1-a0)*i/n) for i in range(n+1)]
    return out + inn

R_OUT = 400
ops.append(path('stone-ring', poly_d(circle_poly(C, R_OUT + 26, 240)), fill='#2a2522'))
ops.append(path('lead-base', poly_d(circle_poly(C, R_OUT + 6, 240)), fill=LEAD))

# outer ring: 24 cells, two blues + amber accent every 6th? alternate
blues = ['#1f3a73', '#2b4f94']
cells = {'#1f3a73': [], '#2b4f94': []}
for i in range(24):
    a0 = -90 + 15*i - 7.5; a1 = a0 + 15
    cells[blues[i % 2]].append(sector(R_OUT - 58, R_OUT, a0, a1))
for col, ps in cells.items():
    ops.append(path('outer-' + col[1:], D(ps), fill=col, stroke=LEAD, sw=LW))
# pearls: small round cells on the outer ring
pearls = [circle_poly(polar(C, R_OUT - 29, -90 + 15*i), 9, 24) for i in range(24)]
ops.append(path('pearls', D(pearls), fill='#d9a441', stroke=LEAD, sw=5))

# ring 2 background: 16 sectors of deep red
reds = ['#6e1826', '#87222f']
cells = {r: [] for r in reds}
RI, RO = 150, R_OUT - 58
for i in range(16):
    a0 = -90 + 22.5*i; a1 = a0 + 22.5
    cells[reds[i % 2]].append(sector(RI, RO, a0, a1))
for col, ps in cells.items():
    ops.append(path('field-' + col[1:], D(ps), fill=col, stroke=LEAD, sw=LW))

# leaves: 8 leaves on diagonals/cardinals, split halves two greens
gL, gD = '#5f8a3e', '#3f6a2c'
halves_l, halves_d, thorns = [], [], []
for i in range(8):
    a = -90 + 45*i + 22.5
    base = polar(C, RI + 6, a)
    lf = leaf(base, a, RO - RI - 16, 46, n=30)
    tip_i = 30
    half1 = lf[:tip_i+1]
    half2 = lf[tip_i:] + [lf[0]]
    halves_l.append(half1 + [base])
    halves_d.append(half2)
    # thorn cells on the cardinal/diagonal lines between leaves
    b = -90 + 45*i
    thorns.append(thorn(polar(C, RI + 4, b), b, 100, 36, hook=0.05, n=14))
ops.append(path('leaf-light', D(halves_l), fill=gL, stroke=LEAD, sw=LW))
ops.append(path('leaf-dark', D(halves_d), fill=gD, stroke=LEAD, sw=LW))
ops.append(path('thorns', D(thorns), fill='#d9a441', stroke=LEAD, sw=LW))

# vine ring around the centre
ops.append(path('vine-ring', ring_d(C, RI + 8, RI - 14, 240), fill='#3f6a2c', stroke=LEAD, sw=LW))
small = []
for i in range(16):
    a = -90 + 22.5*i + 11.25
    small.append(thorn(polar(C, RI + 6, a), a - 20, 26, 14, hook=0.2))
ops.append(path('ring-thorns', D(small), fill='#d9a441', stroke=LEAD, sw=5))

# centre medallion with X
ops.append(path('centre', poly_d(circle_poly(C, RI - 18, 180)), fill='#22305f', stroke=LEAD, sw=LW))
dX, _ = text_d('cinzel-700', 'X', 205, C[0], C[1])
ops.append(path('X-raw', dX, fill='#e0ad48', stroke=LEAD, sw=LW))
ops.append({'type': 'pathfinder', 'name': 'X', 'targets': ['X-raw'], 'mode': 'union'})
ops.append({'type': 'layer-style', 'target': 'X', 'name': 'stroke', 'settings': {'color': LEAD, 'width': LW}})
# star chips in the centre quadrants
chips = []
for a in (-90, 0, 90, 180):
    chips.append(star_poly(polar(C, 92, a), 13, 4, 4, a))
ops.append(path('chips', D(chips), fill=BONE, stroke=LEAD, sw=3))

# light: radial glow over glass + grain
ops.append({'type': 'shape', 'shape': 'ellipse', 'name': 'light', 'x': C[0]-R_OUT, 'y': C[1]-R_OUT, 'width': 2*R_OUT, 'height': 2*R_OUT, 'fill': '#fff3d6'})
ops.append({'type': 'layer-style', 'target': 'light', 'name': 'gradient-overlay', 'settings': {'stops': [{'offset': 0, 'color': '#fff2d0'}, {'offset': 1, 'color': '#000000'}], 'direction': 'radial', 'opacity': 1}})
ops.append({'type': 'blend', 'target': 'light', 'mode': 'overlay'})
ops.append({'type': 'opacity', 'target': 'light', 'value': 0.55})
ops.append({'type': 'effect', 'target': 'light', 'name': 'grain', 'amount': 0.12, 'seed': 4})

# name
dN, bb = text_d('cinzel-700', 'JEFFREY X GUNTLY', 46, 500, 924, tracking=0.22)
print(bb)
ops.append(path('name', dN, fill=BONE))
build('06-rose-window', BG, ops)
