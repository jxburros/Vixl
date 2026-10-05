"""Step 2: skeletonize the ink, trace strokes, fit straight lines / circle / smooth curves,
close gaps, and write sketch-lines.svg, sketch-clean.png and strokes.json (the editable source)."""
import cv2, numpy as np, json, os, math
from skimage.morphology import skeletonize
from scipy.ndimage import gaussian_filter1d
HERE = os.path.dirname(os.path.abspath(__file__))
ink = cv2.imread(os.path.join(HERE, 'work_ink.png'), 0) > 0
H, W = ink.shape
dist = cv2.distanceTransform(ink.astype(np.uint8), cv2.DIST_L2, 5)
sk = skeletonize(ink)
STROKE_W = float(np.clip(2 * np.median(dist[sk]), 3, 12))

# ---------------- skeleton graph ----------------
OFF = [(-1,-1),(-1,0),(-1,1),(0,-1),(0,1),(1,-1),(1,0),(1,1)]
pix = set(zip(*np.nonzero(sk)))
def nbrs(p):
    return [(p[0]+dy, p[1]+dx) for dy, dx in OFF if (p[0]+dy, p[1]+dx) in pix]
deg = {p: len(nbrs(p)) for p in pix}
nodepix = {p for p in pix if deg[p] != 2}
# cluster adjacent junction pixels into nodes
node_of = {}; nodes = []
for p in nodepix:
    if p in node_of: continue
    stack = [p]; node_of[p] = len(nodes); members = []
    while stack:
        q = stack.pop(); members.append(q)
        for r in nbrs(q):
            if r in nodepix and r not in node_of:
                node_of[r] = len(nodes); stack.append(r)
    nodes.append(np.mean(members, 0)[::-1])  # (x,y)
edges = []  # dict(pts Nx2 xy, a=node, b=node)
visited = set()
for p in nodepix:
    for q in nbrs(p):
        if q in nodepix or (p, q) in visited: continue
        path = [p, q]; prev, cur = p, q
        while cur not in nodepix:
            nx = [r for r in nbrs(cur) if r != prev and not (r in nodepix and node_of[r] == node_of[p] and len(path) < 3)]
            nx = [r for r in nx if r != prev]
            if not nx: break
            # prefer non-visited continuation
            prev, cur = cur, nx[0]
            path.append(cur)
        visited.add((path[-1], path[-2])); visited.add((p, q))
        a = node_of[p]; b = node_of.get(path[-1], None)
        if b is None: continue
        edges.append({'pts': np.array([(c, r) for r, c in path], float), 'a': a, 'b': b})
# dedupe edges traced from both sides
uniq = {}; 
for e in edges:
    key = (min(e['a'], e['b']), max(e['a'], e['b']), len(e['pts']))
    uniq.setdefault(key, e)
edges = list(uniq.values())
# pure loops without nodes
seen = set(); 
for e in edges:
    for r, c in e['pts'][:, ::-1].astype(int): seen.add((r, c))
for p in pix:
    if p in seen or p in nodepix: continue
    loop = [p]; seen.add(p); prev, cur = None, p
    while True:
        nx = [r for r in nbrs(cur) if r != prev and r not in seen]
        if not nx: break
        prev, cur = cur, nx[0]; seen.add(cur); loop.append(cur)
    if len(loop) > 30:
        edges.append({'pts': np.array([(c, r) for r, c in loop], float), 'a': None, 'b': None, 'loop': True})

def plen(pts): return float(np.sum(np.linalg.norm(np.diff(pts, axis=0), axis=1)))
# prune short spurs (skeleton artifacts) that end at a free endpoint
nodedeg = {}
for e in edges:
    for k in ('a', 'b'):
        if e[k] is not None: nodedeg[e[k]] = nodedeg.get(e[k], 0) + 1
def is_free(n): return nodedeg.get(n, 0) == 1
edges = [e for e in edges if not (e.get('a') is not None and plen(e['pts']) < 14 and (is_free(e['a']) ^ is_free(e['b'])))]
nodedeg = {}
for e in edges:
    for k in ('a', 'b'):
        if e[k] is not None: nodedeg[e[k]] = nodedeg.get(e[k], 0) + 1

# --------------- merge edges that run straight through a junction ---------------
def end_dir(pts, at_start, L=18):
    if at_start:
        p0 = pts[0]; acc = 0; i = 0
        while i < len(pts) - 1 and np.linalg.norm(pts[i] - p0) < L: i += 1
        v = p0 - pts[i]
    else:
        p0 = pts[-1]; i = len(pts) - 1
        while i > 0 and np.linalg.norm(pts[i] - p0) < L: i -= 1
        v = p0 - pts[i]
    n = np.linalg.norm(v); return v / n if n else v
ends_at = {}
for i, e in enumerate(edges):
    if e.get('loop'): continue
    ends_at.setdefault(e['a'], []).append((i, 0)); ends_at.setdefault(e['b'], []).append((i, 1))
link = {}
for n, lst in ends_at.items():
    if len(lst) < 2: continue
    cands = []
    for x in range(len(lst)):
        for y in range(x + 1, len(lst)):
            (i, s), (j, t) = lst[x], lst[y]
            if i == j: continue
            di = end_dir(edges[i]['pts'], s == 0); dj = end_dir(edges[j]['pts'], t == 0)
            dot = float(np.dot(di, dj))  # outward dirs: straight-through means dot ~ -1
            if dot < -math.cos(math.radians(28)): cands.append((dot, lst[x], lst[y]))
    cands.sort()
    for dot, u, v in cands:
        if u in link or v in link: continue
        link[u] = v; link[v] = u
# walk chains
used = set(); chains = []
def oriented(i, start_end):  # points of edge i walking away from end start_end
    p = edges[i]['pts']; return p if start_end == 0 else p[::-1]
for i, e in enumerate(edges):
    if e.get('loop'):
        chains.append({'pts': e['pts'], 'closed': True, 'ends': [None, None]}); used.add(i); continue
for i in range(len(edges)):
    if i in used: continue
    # find a chain start: go backwards along links
    cur, ent = i, 0; guard = 0; closed = False
    while (cur, ent) in link and guard < 1000:
        j, t = link[(cur, ent)]; cur, ent = j, 1 - t; guard += 1
        if cur == i: closed = True; break
    start = (cur, ent)
    pts = []; cur, ent = start; first_node = edges[cur]['a'] if ent == 0 else edges[cur]['b']
    while True:
        used.add(cur); seg = oriented(cur, ent)
        pts.extend(seg.tolist() if not pts else seg[1:].tolist())
        out = (cur, 1 - ent)
        if out not in link: last_node = edges[cur]['b'] if ent == 0 else edges[cur]['a']; break
        j, t = link[out]
        if j in used: last_node = None; closed = True; break
        cur, ent = j, t
    chains.append({'pts': np.array(pts), 'closed': closed, 'ends': [None if closed else first_node, None if closed else last_node]})
chains = [c for c in chains if plen(c['pts']) > 12]

# ---------------- fitting ----------------
def fit_circle(p):
    x, y = p[:, 0], p[:, 1]
    A = np.c_[2 * x, 2 * y, np.ones(len(x))]; b = x * x + y * y
    cx, cy, c = np.linalg.lstsq(A, b, rcond=None)[0]
    r = math.sqrt(c + cx * cx + cy * cy)
    res = np.sqrt((x - cx) ** 2 + (y - cy) ** 2) - r
    ang = np.unwrap(np.arctan2(y - cy, x - cx)); cover = abs(ang[-1] - ang[0])
    return cx, cy, r, float(np.sqrt(np.mean(res ** 2))), cover
def fit_line(p):
    m = p.mean(0); u, s, vt = np.linalg.svd(p - m); d = vt[0]
    res = (p - m) @ vt[1]
    return m, d, float(np.sqrt(np.mean(res ** 2)))
def snap_dir(d, tol=3.5):
    a = math.degrees(math.atan2(d[1], d[0]))
    for t in (0, 90, 180, -90, -180):
        if abs(a - t) <= tol:
            r = math.radians(t); return np.array([math.cos(r), math.sin(r)]), True
    return d, False
def intersect(m1, d1, m2, d2):
    A = np.array([d1, -d2]).T
    if abs(np.linalg.det(A)) < 1e-6: return None
    t = np.linalg.solve(A, m2 - m1); return m1 + t[0] * d1

strokes = []
for c in chains:
    p = c['pts']; L = plen(p)
    if L > 250:
        cx, cy, r, rms, cover = fit_circle(p)
        if 50 < r < 300 and rms < 0.035 * r and cover > math.radians(200):
            strokes.append({'kind': 'circle', 'cx': cx, 'cy': cy, 'r': r, 'fit_rms': rms, 'ends': [None, None]}); continue
    work = np.vstack([p, p[:1]]) if c['closed'] else p
    ap = cv2.approxPolyDP(work.astype(np.float32).reshape(-1, 1, 2), 7, False).reshape(-1, 2)
    idx = [int(np.argmin(np.linalg.norm(work - v, axis=1))) for v in ap]
    idx = sorted(set(idx)); idx[0] = 0; idx[-1] = len(work) - 1
    segs = []; ok = True
    for i0, i1 in zip(idx[:-1], idx[1:]):
        sp = work[i0:i1 + 1]; sl = np.linalg.norm(sp[-1] - sp[0])
        trim = max(1, int(len(sp) * 0.12)); core = sp[trim:-trim] if len(sp) > 2 * trim + 4 else sp
        m, d, rms = fit_line(core)
        if sl < 35 or rms > 2.6: ok = False; break
        if np.dot(d, sp[-1] - sp[0]) < 0: d = -d
        segs.append((m, d))
    if ok:
        for k in range(1, len(segs)):
            turn = math.degrees(math.acos(np.clip(np.dot(segs[k - 1][1], segs[k][1]), -1, 1)))
            if turn < 30: ok = False; break
    if ok and not c['closed']:
        segs = [(m, snap_dir(d)[0]) for m, d in segs]
        verts = [segs[0][0] + np.dot(work[0] - segs[0][0], segs[0][1]) * segs[0][1]]
        for k in range(1, len(segs)):
            v = intersect(segs[k - 1][0], segs[k - 1][1], segs[k][0], segs[k][1]); verts.append(v)
        verts.append(segs[-1][0] + np.dot(work[-1] - segs[-1][0], segs[-1][1]) * segs[-1][1])
        strokes.append({'kind': 'lines', 'pts': np.array(verts), 'ends': c['ends']}); continue
    # free-hand curve: smooth but keep the drawn shape
    sg = 12 if L > 1000 else 5   # long gentle lines (ground) get more smoothing than the canopy lobes
    if c['closed']:
        sm = np.c_[gaussian_filter1d(p[:, 0], sg, mode='wrap'), gaussian_filter1d(p[:, 1], sg, mode='wrap')]
    else:
        sm = np.c_[gaussian_filter1d(p[:, 0], sg, mode='nearest'), gaussian_filter1d(p[:, 1], sg, mode='nearest')]
        sm[0], sm[-1] = p[0], p[-1]
    strokes.append({'kind': 'curve', 'pts': sm, 'closed': c['closed'], 'ends': c['ends']})

# ---------------- gap closing ----------------
log = []
def free_ends():
    out = []
    for si, s in enumerate(strokes):
        if s['kind'] == 'circle' or s.get('closed'): continue
        for k in (0, 1):
            n = s['ends'][k]
            if n is None or nodedeg.get(n, 0) == 1: out.append((si, k))
    return out
def endpt(si, k): p = strokes[si]['pts']; return p[0] if k == 0 else p[-1]
def tangent(si, k):
    s = strokes[si]; p = s['pts']
    return end_dir(p, k == 0, L=25)
# 1) join pairs of free curve ends with a smooth bridge (mutual nearest, < 100 px)
fe = [e for e in free_ends() if strokes[e[0]]['kind'] == 'curve']
pairs = []
for a in fe:
    best = min((b for b in fe if b != a), key=lambda b: np.linalg.norm(endpt(*a) - endpt(*b)), default=None)
    if best is None: continue
    bb = min((x for x in fe if x != best), key=lambda x: np.linalg.norm(endpt(*best) - endpt(*x)))
    dd = np.linalg.norm(endpt(*a) - endpt(*best))
    if bb == a and dd < 100 and a < best: pairs.append((a, best, dd))
def hermite(p0, t0, p1, t1, n=30):
    L = np.linalg.norm(p1 - p0); m0, m1 = t0 * L, -t1 * L
    s = np.linspace(0, 1, n)[:, None]
    return (2*s**3-3*s**2+1)*p0 + (s**3-2*s**2+s)*m0 + (-2*s**3+3*s**2)*p1 + (s**3-s**2)*m1
for (sa, ka), (sb, kb), dd in pairs:
    p0, p1 = endpt(sa, ka), endpt(sb, kb)
    br = hermite(p0, tangent(sa, ka), p1, tangent(sb, kb))
    if sa == sb:
        P = strokes[sa]['pts']; P = P if ka == 1 else P[::-1]
        strokes[sa]['pts'] = np.vstack([P, br[1:-1]]); strokes[sa]['closed'] = True
    else:
        A = strokes[sa]['pts']; A = A if ka == 1 else A[::-1]
        B = strokes[sb]['pts']; B = B if kb == 0 else B[::-1]
        strokes[sa]['pts'] = np.vstack([A, br[1:-1], B]); strokes[sa]['ends'] = [strokes[sa]['ends'][1 - ka] if True else None, strokes[sb]['ends'][1 - kb]]
        strokes[sb]['kind'] = 'dead'
    log.append(f'bridged curve ends {np.round(p0).tolist()} -> {np.round(p1).tolist()} ({dd:.0f}px)')
strokes = [s for s in strokes if s['kind'] != 'dead']

def render_ids(exclude=None, width=3):
    m = np.full((H, W), -1, np.int32)
    for si, s in enumerate(strokes):
        if si == exclude: continue
        tmp = np.zeros((H, W), np.uint8)
        if s['kind'] == 'circle': cv2.circle(tmp, (int(round(s['cx'])), int(round(s['cy']))), int(round(s['r'])), 1, width)
        else: cv2.polylines(tmp, [np.round(s['pts']).astype(np.int32).reshape(-1, 1, 2)], bool(s.get('closed')), 1, width)
        m[tmp > 0] = si
    return m
# 2) extend free ends along their tangent until they meet another stroke (<= 38 px);
#    ends that sat on a junction are trimmed/extended onto the stroke they touched.
MAXGAP = 38
for rnd in range(2):
    for si, k in sorted(free_ends(), key=lambda e: 0):
        ids = render_ids(exclude=si)
        p0 = endpt(si, k).copy(); t = tangent(si, k)
        hit = None
        for step in np.arange(1, MAXGAP, 0.5):
            q = p0 + t * step; x, y = int(round(q[0])), int(round(q[1]))
            if not (0 <= x < W and 0 <= y < H): break
            if ids[y, x] >= 0: hit = q + t * 1.0; break
        if hit is not None and np.linalg.norm(hit - p0) > 1.5:
            P = strokes[si]['pts']
            if strokes[si]['kind'] == 'lines':
                if k == 0: P[0] = hit
                else: P[-1] = hit
            else:
                P = np.vstack([hit, P]) if k == 0 else np.vstack([P, hit])
            strokes[si]['pts'] = P
            strokes[si]['ends'][k] = -1  # now attached
            log.append(f'extended {strokes[si]["kind"]} end {np.round(p0).tolist()} by {np.linalg.norm(hit-p0):.0f}px')
# 1b) corners: two free straight ends close together (<= 22 px) with clearly different
#     directions are moved to the intersection of their lines
fe = [e for e in free_ends() if strokes[e[0]]['kind'] == 'lines']
done = set()
for a in fe:
    for b in fe:
        if a >= b or a in done or b in done: continue
        pa, pb = endpt(*a).copy(), endpt(*b).copy()
        if np.linalg.norm(pa - pb) > 22: continue
        ta, tb = tangent(*a), tangent(*b)
        if abs(np.dot(ta, tb)) > math.cos(math.radians(45)): continue
        q = intersect(pa, ta, pb, tb)
        if q is None or np.linalg.norm(q - pa) > 25 or np.linalg.norm(q - pb) > 25: continue
        for (si, k) in (a, b):
            P = strokes[si]['pts']
            if k == 0: P[0] = q
            else: P[-1] = q
            strokes[si]['ends'][k] = -1
        done |= {a, b}
        log.append(f'closed corner {np.round(pa).tolist()} / {np.round(pb).tolist()} at {np.round(q).tolist()}')

# 1c) corners of straight polylines that stop just short of another stroke (e.g. the
#     wall-top/right-wall corner under the roof line): continue the segment past the
#     corner until it meets that stroke (<= 30 px), as a short extra straight stroke.
newst = []
for si, s in enumerate(list(strokes)):
    if s['kind'] != 'lines' or len(s['pts']) < 3: continue
    ids = render_ids(exclude=si)
    P = s['pts']
    for i in range(1, len(P) - 1):
        best = None
        for nb in (i - 1, i + 1):
            t = P[i] - P[nb]; t = t / np.linalg.norm(t)
            hit = None
            for step in np.arange(STROKE_W, 30, 0.5):
                q = P[i] + t * step; x, y = int(round(q[0])), int(round(q[1]))
                if not (0 <= x < W and 0 <= y < H): break
                if ids[y, x] >= 0: hit = q + t; break
            if hit is not None and (best is None or np.linalg.norm(hit - P[i]) < np.linalg.norm(best - P[i])):
                best = hit
        if best is not None:
            newst.append({'kind': 'lines', 'pts': np.array([P[i].copy(), best]), 'ends': [-1, -1]})
            log.append(f'continued corner {np.round(P[i]).tolist()} by {np.linalg.norm(best-P[i]):.0f}px to meet a stroke')
strokes += newst

# junction ends of straight strokes: snap exactly onto the stroke they touch (small +-12px search)
for si, s in enumerate(strokes):
    if s['kind'] != 'lines': continue
    for k in (0, 1):
        n = s['ends'][k]
        if n is None or n == -1 or nodedeg.get(n, 0) == 1: continue
        ids = render_ids(exclude=si, width=1)
        P = s['pts']; p0 = P[0] if k == 0 else P[-1]; t = tangent(si, k)
        best = None
        for step in np.arange(-12, 12.5, 0.5):
            q = p0 + t * step; x, y = int(round(q[0])), int(round(q[1]))
            if 0 <= x < W and 0 <= y < H and ids[y, x] >= 0:
                if best is None or abs(step) < abs(best): best = step
        if best is not None:
            q = p0 + t * best
            if k == 0: P[0] = q
            else: P[-1] = q

# ---------------- outputs ----------------
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
            if not s.get('closed'):  # round caps
                for e in (s['pts'][0], s['pts'][-1]):
                    cv2.circle(im, (int(round(e[0] * scale * 16)), int(round(e[1] * scale * 16))), int(round(w / 2 * 16)), 0, -1, cv2.LINE_AA, 4)
    return cv2.resize(im, (W, H), interpolation=cv2.INTER_AREA)
clean = render()
cv2.imwrite(os.path.join(HERE, 'sketch-clean.png'), clean)

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
    if s['kind'] == 'circle':
        svg.append(f'<circle id="s{i}-circle" cx="{fmt(s["cx"])}" cy="{fmt(s["cy"])}" r="{fmt(s["r"])}"/>')
    elif s['kind'] == 'lines':
        svg.append(f'<path id="s{i}-straight" d="M' + ' L'.join(f'{fmt(x)},{fmt(y)}' for x, y in s['pts']) + '"/>')
    else:
        svg.append(f'<path id="s{i}-curve" d="{curve_path(s["pts"], bool(s.get("closed")))}"/>')
svg += ['</g>', '</svg>']
open(os.path.join(HERE, 'sketch-lines.svg'), 'w').write('\n'.join(svg))
ser = []
for s in strokes:
    d = {k: (v.tolist() if isinstance(v, np.ndarray) else v) for k, v in s.items() if k != 'ends'}
    ser.append(d)
json.dump({'width': W, 'height': H, 'stroke_width': STROKE_W, 'strokes': ser, 'gap_log': log}, open(os.path.join(HERE, 'strokes.json'), 'w'))
print('stroke width', STROKE_W)
from collections import Counter
print(Counter(s['kind'] for s in strokes))
for s in strokes:
    if s['kind'] == 'circle': print('circle', s['cx'], s['cy'], s['r'], s['fit_rms'])
print('\n'.join(log))
