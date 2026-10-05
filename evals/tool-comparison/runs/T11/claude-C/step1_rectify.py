"""Step 1: find the paper, undo perspective/tilt, flatten lighting, extract ink mask."""
import cv2, numpy as np, json, sys, os
HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, '../../../fixtures/sketch.jpg')
OUT_W = 2000

img = cv2.imread(SRC)
gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
# paper = bright; desk = dark brown
paper = (cv2.GaussianBlur(gray, (0, 0), 3) > 140).astype(np.uint8) * 255
paper = cv2.morphologyEx(paper, cv2.MORPH_CLOSE, np.ones((25, 25), np.uint8))
cnts, _ = cv2.findContours(paper, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
c = max(cnts, key=cv2.contourArea)
hull = cv2.convexHull(c)
quad = None
for eps in np.linspace(0.005, 0.05, 40):
    a = cv2.approxPolyDP(hull, eps * cv2.arcLength(hull, True), True)
    if len(a) == 4:
        quad = a.reshape(4, 2).astype(np.float32); break
assert quad is not None
# order TL, TR, BR, BL
s = quad.sum(1); d = np.diff(quad, axis=1).ravel()
tl, br = quad[np.argmin(s)], quad[np.argmax(s)]
tr, bl = quad[np.argmin(d)], quad[np.argmax(d)]
q = np.array([tl, tr, br, bl], np.float32)
wpx = (np.linalg.norm(tr - tl) + np.linalg.norm(br - bl)) / 2
hpx = (np.linalg.norm(bl - tl) + np.linalg.norm(br - tr)) / 2
OUT_H = int(round(OUT_W * hpx / wpx))
# inset a little so no desk pixels survive at the borders
inset = 6.0
dst = np.array([[-inset, -inset], [OUT_W + inset, -inset], [OUT_W + inset, OUT_H + inset], [-inset, OUT_H + inset]], np.float32)
M = cv2.getPerspectiveTransform(q, dst)
warp = cv2.warpPerspective(img, M, (OUT_W, OUT_H), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
wg = cv2.cvtColor(warp, cv2.COLOR_BGR2GRAY).astype(np.float32)
# flatten shading: divide by a large-scale background estimate (closing removes ink first)
bg = cv2.morphologyEx(wg, cv2.MORPH_CLOSE, np.ones((31, 31), np.uint8))
bg = cv2.GaussianBlur(bg, (0, 0), 25)
flat = np.clip(wg / np.maximum(bg, 1) * 255, 0, 255).astype(np.uint8)
flat_s = cv2.GaussianBlur(flat, (0, 0), 1.2)
ink = (flat_s < 170).astype(np.uint8)
# drop specks
n, lab, st, _ = cv2.connectedComponentsWithStats(ink, 8)
keep = np.zeros(n, bool); keep[1:] = st[1:, cv2.CC_STAT_AREA] >= 60
ink = keep[lab].astype(np.uint8) * 255
cv2.imwrite(os.path.join(HERE, 'work_warp.png'), warp)
cv2.imwrite(os.path.join(HERE, 'work_flat.png'), flat)
cv2.imwrite(os.path.join(HERE, 'work_ink.png'), ink)
json.dump({'quad_src_TL_TR_BR_BL': q.tolist(), 'out_size': [OUT_W, OUT_H], 'inset_px': inset}, open(os.path.join(HERE, 'work_rectify.json'), 'w'), indent=1)
print(q, OUT_W, OUT_H)
