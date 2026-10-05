#!/usr/bin/env python3
"""Generate the Tidewick seamless pattern tile (SVG) deterministically.

Motifs are placed by toroidal dart-throwing (Poisson-disc style) so spacing is
even but not a grid. Every motif whose bounding radius crosses a tile edge is
drawn again at the wrapped offsets (+/-1024 in x and/or y); the whole tile is
clipped to 0..1024, so anything leaving one edge re-enters on the opposite one.
"""
import math, random, sys, os

S = 1024
NAVY, AMBER, FOAM, CORAL, CREAM = "#14263b", "#f2a541", "#a8d5c8", "#e2725b", "#f7f1e5"
rng = random.Random(15)

def tdist(a, b):
    dx = abs(a[0] - b[0]); dy = abs(a[1] - b[1])
    dx = min(dx, S - dx); dy = min(dy, S - dy)
    return math.hypot(dx, dy)

placed = []  # (x, y, radius, kind, params)

def throw(kind, n, rmin, rmax, gap, tries=4000):
    got = 0
    for _ in range(tries):
        if got >= n:
            break
        r = rng.uniform(rmin, rmax)
        p = (rng.uniform(0, S), rng.uniform(0, S))
        if all(tdist(p, q[:2]) >= r + q[2] + gap for q in placed):
            placed.append((p[0], p[1], r, kind, {"rot": rng.uniform(0, 360)}))
            got += 1
    return got

# ---------- motif builders (local coords, centred on 0,0, scaled to radius r) ----------
def kelp(r, rot, color):
    # wavy stem from bottom to top with alternating leaf blades
    L = r * 1.8
    pts = []
    n = 24
    for i in range(n + 1):
        t = i / n
        y = L / 2 - t * L
        x = math.sin(t * math.pi * 2.2) * r * 0.12
        pts.append((x, y))
    stem = "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    out = [f'<path d="{stem}" fill="none" stroke="{color}" stroke-width="{max(2.5, r*0.05):.1f}" stroke-linecap="round"/>']
    k = 6
    for j in range(k):
        t = 0.12 + j * (0.8 / k)
        i = int(t * n)
        x, y = pts[i]
        side = 1 if j % 2 == 0 else -1
        ln = r * (0.55 - 0.05 * j)
        w = ln * 0.32
        # blade: a leaf shape angled upward
        ang = math.radians(-50 * side)
        tipx, tipy = x + side * ln * 0.85, y - ln * 0.55
        c1 = (x + side * ln * 0.25, y - w * 1.6)
        c2 = (x + side * ln * 0.70, y + w * 0.2)
        d = (f"M{x:.1f},{y:.1f} Q{c1[0]:.1f},{c1[1]:.1f} {tipx:.1f},{tipy:.1f} "
             f"Q{c2[0]:.1f},{c2[1]:.1f} {x:.1f},{y:.1f}Z")
        out.append(f'<path d="{d}" fill="{color}"/>')
    # small float bladder at the top
    tx, ty = pts[-1]
    out.append(f'<circle cx="{tx:.1f}" cy="{ty - r*0.06:.1f}" r="{r*0.07:.1f}" fill="{color}"/>')
    return f'<g transform="rotate({rot:.1f})">' + "".join(out) + "</g>"

def shell(r, rot, body, line):
    # spiral shell: filled logarithmic-spiral outline + inner spiral line
    a, b = r * 0.08, 0.19
    tmax = math.log(r / a) / b
    sp = []
    steps = 90
    for i in range(steps + 1):
        t = tmax * i / steps
        rr = a * math.exp(b * t)
        sp.append((rr * math.cos(t), rr * math.sin(t)))
    outline = "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in sp) + "Z"
    line_d = "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in sp)
    # radial ridges
    ridges = []
    for i in range(30, steps, 9):
        x, y = sp[i]
        t = tmax * i / steps
        rin = a * math.exp(b * (t - 2 * math.pi)) if t > 2 * math.pi else 0
        ridges.append(f'M{rin*math.cos(t):.1f},{rin*math.sin(t):.1f} L{x:.1f},{y:.1f}')
    sw = max(1.8, r * 0.06)
    return (f'<g transform="rotate({rot:.1f})">'
            f'<path d="{outline}" fill="{body}"/>'
            f'<path d="{line_d}" fill="none" stroke="{line}" stroke-width="{sw:.1f}" stroke-linecap="round"/>'
            f'<path d="{" ".join(ridges)}" fill="none" stroke="{line}" stroke-width="{sw*0.6:.1f}" stroke-linecap="round" opacity="0.7"/>'
            "</g>")

def wave(r, rot, color, accent):
    # curling wave: a swell rising into a spiral curl, with two echo lines underneath
    out = []
    sw = max(3, r * 0.07)
    for k, (off, col, wscale) in enumerate([(0, color, 1.0), (r * 0.22, accent, 0.7), (r * 0.42, color, 0.5)]):
        x0 = -r
        y0 = r * 0.35 + off
        # swell
        d = f"M{x0:.1f},{y0:.1f} C{-r*0.5:.1f},{y0:.1f} {-r*0.1:.1f},{y0 - r*0.9 + off*0.3:.1f} {r*0.35:.1f},{y0 - r*0.75 + off*0.2:.1f}"
        if k == 0:
            # curl: spiral inward
            cx, cy = r * 0.3, -r * 0.15
            pts = []
            for i in range(40):
                t = i / 39
                ang = -math.pi / 2 + t * math.pi * 1.6
                rr = r * 0.42 * (1 - 0.65 * t)
                pts.append((cx + rr * math.cos(ang), cy + rr * math.sin(ang)))
            d += " L" + " L".join(f"{x:.1f},{y:.1f}" for x, y in pts)
        else:
            d += f" C{r*0.6:.1f},{y0 - r*0.7 + off*0.2:.1f} {r*0.75:.1f},{y0 - r*0.45:.1f} {r*0.72:.1f},{y0 - r*0.25:.1f}"
        out.append(f'<path d="{d}" fill="none" stroke="{col}" stroke-width="{sw*wscale:.1f}" stroke-linecap="round" stroke-linejoin="round"/>')
    # foam droplets off the crest
    for (fx, fy, fr) in [(-r*0.15, -r*0.62, 0.06), (-r*0.38, -r*0.42, 0.045), (r*0.0, -r*0.85, 0.04)]:
        out.append(f'<circle cx="{fx:.1f}" cy="{fy:.1f}" r="{r*fr:.1f}" fill="{accent}"/>')
    return f'<g transform="rotate({rot:.1f})">' + "".join(out) + "</g>"

def dot(r, color):
    return f'<circle cx="0" cy="0" r="{r:.1f}" fill="{color}"/>'

# ---------- placement ----------
# big motifs first, then medium, then dots fill the gaps
# round 2: about a third fewer motifs (158 -> 106); gaps widened so the
# remaining motifs still spread evenly instead of clumping.
throw("kelp", 5, 78, 105, 40)
throw("wave", 5, 58, 78, 40)
throw("shell", 9, 24, 42, 34)
throw("dot", 47, 5, 9, 26, tries=20000)
throw("dot", 40, 2.5, 4.5, 18, tries=20000)

kelp_cols = [NAVY, FOAM, NAVY, AMBER]
wave_cols = [(NAVY, FOAM), (FOAM, NAVY), (CORAL, AMBER), (NAVY, CORAL)]
shell_cols = [(AMBER, NAVY)]  # round 2: every shell amber, navy spiral/ridges
dot_cols = [AMBER, CORAL, FOAM, NAVY, AMBER, FOAM]

counts = {}
motifs = []
for (x, y, r, kind, p) in placed:
    i = counts.get(kind, 0); counts[kind] = i + 1
    rot = p["rot"]
    if kind == "kelp":
        # keep kelp loosely upright-ish but varied (+/-55 deg), for a sea-floor feel
        g = kelp(r, (rot % 110) - 55, kelp_cols[i % len(kelp_cols)])
    elif kind == "wave":
        c, a = wave_cols[i % len(wave_cols)]
        g = wave(r, (rot % 80) - 40, c, a)
    elif kind == "shell":
        b, l = shell_cols[i % len(shell_cols)]
        g = shell(r, rot, b, l)
    else:
        g = dot(r, dot_cols[i % len(dot_cols)])
    motifs.append((x, y, r * 1.15, kind, g))

body = []
wrapped = 0
for (x, y, rb, kind, g) in motifs:
    xs = [0] + ([S] if x - rb < 0 else []) + ([-S] if x + rb > S else [])
    ys = [0] + ([S] if y - rb < 0 else []) + ([-S] if y + rb > S else [])
    for dx in xs:
        for dy in ys:
            if dx or dy:
                wrapped += 1
            body.append(f'<g transform="translate({x+dx:.2f},{y+dy:.2f})">{g}</g>')

svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{S}" height="{S}" viewBox="0 0 {S} {S}">\n'
       f'<title>Tidewick seamless tile</title>\n'
       f'<defs><clipPath id="tile"><rect width="{S}" height="{S}"/></clipPath></defs>\n'
       f'<rect width="{S}" height="{S}" fill="{CREAM}"/>\n'
       f'<g clip-path="url(#tile)">\n' + "\n".join(body) + "\n</g>\n</svg>\n")

out = sys.argv[1] if len(sys.argv) > 1 else "tile.svg"
open(out, "w").write(svg)
print("placed:", counts, "wrapped copies:", wrapped, file=sys.stderr)
