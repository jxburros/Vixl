"""Round 2: add a chimney on the right side of the roof to the fitted strokes from round 1,
then re-render sketch-clean.png, sketch-lines.svg and strokes.json with the same renderer
(same stroke width, anti-aliasing, round caps/joins) as step2_vectorize.py."""
import cv2, numpy as np, json, os
HERE = os.path.dirname(os.path.abspath(__file__))
data = json.load(open(os.path.join(HERE, '..', 'strokes.json')))
W, H, STROKE_W = data['width'], data['height'], data['stroke_width']
strokes = [dict(s) for s in data['strokes']]
for s in strokes:
    if 'pts' in s: s['pts'] = np.array(s['pts'], float)

# right roof line = the 'lines' stroke that descends from the apex to the right eave
lines = [s for s in strokes if s['kind'] == 'lines' and len(s['pts']) == 2]
def slope_ok(p): d = p[1] - p[0]; return abs(d[0]) > 100 and 0.5 < (d[1] / d[0]) < 2
right_roof = max((s for s in lines if slope_ok(s['pts'])), key=lambda s: s['pts'][:, 0].mean())
a, b = sorted(right_roof['pts'].tolist(), key=lambda p: p[0])
a, b = np.array(a), np.array(b)
def roof_y(x): return a[1] + (b[1] - a[1]) * (x - a[0]) / (b[0] - a[0])
# chimney: two vertical sides rising from the roof line and a horizontal top, placed on the
# right slope at ~40-62% of the way from the apex to the eave
x0 = a[0] + 0.40 * (b[0] - a[0]); x1 = a[0] + 0.62 * (b[0] - a[0])
x0, x1 = round(x0), round(x1)
top = round(roof_y(x0) - 62)
chimney = np.array([[x0, roof_y(x0)], [x0, top], [x1, top], [x1, roof_y(x1)]], float)
strokes.append({'kind': 'lines', 'pts': chimney, 'added': 'round2-chimney'})
log = data['gap_log'] + [{'round2': 'added chimney', 'pts': chimney.round(1).tolist(), 'on_stroke': 'right roof line'}]
print('right roof', a.round(1), b.round(1), 'chimney', chimney.round(1).tolist())

SS = 3
def render(scale=SS):
    im = np.full((H * scale, W * scale), 255, np.uint8)
    w = max(1, int(round(STROKE_W * scale)))
    for s in strokes:
        if s['kind'] == 'circle':
            cv2.circle(im, (int(round(s['cx'] * scale * 16)), int(round(s['cy'] * scale * 16))), int(round(s['r'] * scale * 16)), 0, w, cv2.LINE_AA, 4)
        else:
            pts = np.round(s['pts'] * scale * 16).astype(np.int32).reshape(-1, 1, 2)
            cv2.polylines(im, [pts], bool(s.get('closed')), 0, w, cv2.LINE_AA, 4)
            if not s.get('closed'):
                for e in (s['pts'][0], s['pts'][-1]):
                    cv2.circle(im, (int(round(e[0] * scale * 16)), int(round(e[1] * scale * 16))), int(round(w / 2 * 16)), 0, -1, cv2.LINE_AA, 4)
    return cv2.resize(im, (W, H), interpolation=cv2.INTER_AREA)
cv2.imwrite(os.path.join(HERE, 'sketch-clean.png'), render())

def fmt(v): return f'{v:.1f}'
def curve_path(P, closed):
    Q = cv2.approxPolyDP(P.astype(np.float32).reshape(-1, 1, 2), 0.8, closed).reshape(-1, 2).astype(float)
    if len(Q) < 3: return 'M' + ' L'.join(f'{fmt(x)},{fmt(y)}' for x, y in Q)
    n = len(Q); d = f'M{fmt(Q[0][0])},{fmt(Q[0][1])}'
    rng = range(n) if closed else range(n - 1)
    for i in rng:
        p0 = Q[(i - 1) % n] if (closed or i > 0) else Q[i]; p1 = Q[i]; p2 = Q[(i + 1) % n]
        p3 = Q[(i + 2) % n] if (closed or i + 2 < n) else p2
        c1 = p1 + (p2 - p0) / 6; c2 = p2 - (p3 - p1) / 6
        d += f' C{fmt(c1[0])},{fmt(c1[1])} {fmt(c2[0])},{fmt(c2[1])} {fmt(p2[0])},{fmt(p2[1])}'
    return d + (' Z' if closed else '')
svg = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">',
       f'<rect width="{W}" height="{H}" fill="#ffffff"/>',
       f'<g id="lines" fill="none" stroke="#000000" stroke-width="{STROKE_W:.1f}" stroke-linecap="round" stroke-linejoin="round">']
for i, s in enumerate(strokes):
    if s.get('added') == 'round2-chimney':
        svg.append(f'<path id="s{i}-chimney" d="M' + ' L'.join(f'{fmt(x)},{fmt(y)}' for x, y in s['pts']) + '"/>')
    elif s['kind'] == 'circle':
        svg.append(f'<circle id="s{i}-circle" cx="{fmt(s["cx"])}" cy="{fmt(s["cy"])}" r="{fmt(s["r"])}"/>')
    elif s['kind'] == 'lines':
        svg.append(f'<path id="s{i}-straight" d="M' + ' L'.join(f'{fmt(x)},{fmt(y)}' for x, y in s['pts']) + '"/>')
    else:
        svg.append(f'<path id="s{i}-curve" d="{curve_path(s["pts"], bool(s.get("closed")))}"/>')
svg += ['</g>', '</svg>']
open(os.path.join(HERE, 'sketch-lines.svg'), 'w').write('\n'.join(svg))
ser = [{k: (v.tolist() if isinstance(v, np.ndarray) else v) for k, v in s.items()} for s in strokes]
json.dump({'width': W, 'height': H, 'stroke_width': STROKE_W, 'strokes': ser, 'gap_log': log},
          open(os.path.join(HERE, 'strokes.json'), 'w'))
