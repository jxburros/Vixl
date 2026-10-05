"""Step 3: flat-colour the closed regions under the lines; build compare.png."""
import cv2, numpy as np, json, os
HERE = os.path.dirname(os.path.abspath(__file__))
clean = cv2.imread(os.path.join(HERE, 'sketch-clean.png'), 0)
data = json.load(open(os.path.join(HERE, 'strokes.json')))
H, W = clean.shape
def hexc(h): h = h.lstrip('#'); return np.array([int(h[i:i+2], 16) for i in (0, 2, 4)], np.uint8)
PAL = {'roof': '#e2725b', 'walls': '#f7f1e5', 'panes_door': '#14263b', 'sun': '#f2a541',
       'canopy': '#5a8f5a', 'trunk': '#7a5236', 'sky': '#d9ecf2', 'ground': '#a8d5c8'}
barrier = (clean < 160).astype(np.uint8)
# The ground line stops short of the paper edges; extend it horizontally (invisible, colour only)
ground = max((s for s in data['strokes'] if s['kind'] == 'curve' and not s.get('closed')),
             key=lambda s: np.ptp(np.array(s['pts'])[:, 0]))
g = np.array(ground['pts']); g = g[np.argsort(g[:, 0])]
L, R = g[0], g[-1]
cv2.line(barrier, (0, int(round(L[1]))), (int(round(L[0])), int(round(L[1]))), 1, 5)
cv2.line(barrier, (int(round(R[0])), int(round(R[1]))), (W - 1, int(round(R[1]))), 1, 5)
n, lab = cv2.connectedComponents((1 - barrier).astype(np.uint8), connectivity=4)
areas = np.bincount(lab.ravel())
def comp_at(x, y): return lab[int(y), int(x)]
assign = {}
assign[comp_at(W / 2, 3)] = 'sky'
assign[comp_at(W / 2, H - 3)] = 'ground'
circ = [s for s in data['strokes'] if s['kind'] == 'circle'][0]
assign[comp_at(circ['cx'], circ['cy'])] = 'sun'
canopy = [s for s in data['strokes'] if s['kind'] == 'curve' and s.get('closed')][0]
cp = np.array(canopy['pts']); cx, cy = cp.mean(0)
assign[comp_at(cx, cy)] = 'canopy'
lines = [np.array(s['pts']) for s in data['strokes'] if s['kind'] == 'lines']
# trunk: two near-vertical lines below the canopy
trunk = sorted([p for p in lines if p[:, 0].min() > cp[:, 0].min() and p[:, 0].max() < cp[:, 0].max() and p[:, 1].min() > cy],
               key=lambda p: p[:, 0].mean())
tx = (trunk[0][:, 0].mean() + trunk[-1][:, 0].mean()) / 2
ty = (max(trunk[0][:, 1].min(), trunk[-1][:, 1].min()) + min(trunk[0][:, 1].max(), trunk[-1][:, 1].max())) / 2
assign[comp_at(tx, ty)] = 'trunk'
# house: roof apex is the topmost vertex among straight strokes left of the sun
house_pts = np.vstack([p for p in lines if p[:, 0].max() < circ['cx'] - circ['r'] - 150])
apex = house_pts[np.argmin(house_pts[:, 1])]
assign[comp_at(apex[0], apex[1] + 80)] = 'roof'
# remaining components inside the house outline: largest = walls, the others = panes/door
hx0, hx1 = house_pts[:, 0].min(), house_pts[:, 0].max()
for k in range(1, n):
    if k in assign or areas[k] < 50: continue
    ys, xs = np.nonzero(lab == k)
    if xs.min() > hx0 and xs.max() < hx1 and ys.min() > apex[1]:
        assign[k] = 'house?'
hk = [k for k, v in assign.items() if v == 'house?']
walls = max(hk, key=lambda k: areas[k]); assign[walls] = 'walls'
for k in hk:
    if k != walls: assign[k] = 'panes_door'
unassigned = [(k, int(areas[k])) for k in range(1, n) if k not in assign and areas[k] >= 50]
print('regions:', {v: sum(1 for x in assign.values() if x == v) for v in set(assign.values())}, 'unassigned:', unassigned)
col = np.full((H, W, 3), 255, np.uint8)
idx = np.zeros(n, np.int32) - 1
names = list(PAL)
for k, v in assign.items(): idx[k] = names.index(v)
li = idx[lab]
# fill pixels under the lines / invisible barrier with the nearest region's colour
known = (li >= 0).astype(np.uint8)
_, lbl = cv2.distanceTransformWithLabels(1 - known, cv2.DIST_L2, 5, labelType=cv2.DIST_LABEL_PIXEL)
ys, xs = np.nonzero(known)
seed_cls = np.zeros(lbl.max() + 1, np.int32); seed_cls[lbl[ys, xs]] = li[ys, xs]
li = np.where(known > 0, li, seed_cls[lbl])
pal = np.array([hexc(PAL[k]) for k in names])
col = pal[li]
# lines on top (multiply keeps anti-aliasing)
out = (col.astype(np.float32) * (clean[..., None].astype(np.float32) / 255)).astype(np.uint8)
cv2.imwrite(os.path.join(HERE, 'sketch-color.png'), cv2.cvtColor(out, cv2.COLOR_RGB2BGR))
# compare
orig = cv2.imread(os.path.join(HERE, '../../../fixtures/sketch.jpg'))
h = 1000
a = cv2.resize(orig, (int(orig.shape[1] * h / orig.shape[0]), h), interpolation=cv2.INTER_AREA)
b = cv2.resize(cv2.cvtColor(out, cv2.COLOR_RGB2BGR), (int(W * h / H), h), interpolation=cv2.INTER_AREA)
gap = 40
cmp_ = np.full((h + 2 * gap, a.shape[1] + b.shape[1] + 3 * gap, 3), 255, np.uint8)
cmp_[gap:gap + h, gap:gap + a.shape[1]] = a
cmp_[gap:gap + h, 2 * gap + a.shape[1]:2 * gap + a.shape[1] + b.shape[1]] = b
cv2.imwrite(os.path.join(HERE, 'compare.png'), cmp_)
