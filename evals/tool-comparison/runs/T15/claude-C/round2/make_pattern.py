"""Generate the Tidewick seamless pattern (tile.png, tile.svg, preview-3x3.png, mug-wrap.png).
Run: python3 make_pattern.py   (needs pycairo, numpy, Pillow)"""
import math, os, random
import cairo
import numpy as np
from PIL import Image

OUT = os.path.dirname(os.path.abspath(__file__))
T = 1024
SEED = 15

def hexrgb(h):
    h = h.lstrip('#'); return tuple(int(h[i:i+2], 16) / 255 for i in (0, 2, 4))
NAVY, AMBER, FOAM, CORAL, CREAM = map(hexrgb, ["#14263b", "#f2a541", "#a8d5c8", "#e2725b", "#f7f1e5"])

# ---------------------------------------------------------------- motifs
# Each draws centred on (0,0) at unit scale `s`; caller applies translate/rotate.

def kelp(ctx, s, col, rng):
    L = 200 * s
    bend = rng.uniform(-0.35, 0.35) * L
    p0, c1, c2, p3 = (0, L/2), (bend, L/6), (-bend, -L/6), (bend*0.4, -L/2)
    def pt(t):
        u = 1 - t
        return (u**3*p0[0] + 3*u*u*t*c1[0] + 3*u*t*t*c2[0] + t**3*p3[0],
                u**3*p0[1] + 3*u*u*t*c1[1] + 3*u*t*t*c2[1] + t**3*p3[1])
    ctx.set_source_rgb(*col)
    ctx.set_line_cap(cairo.LINE_CAP_ROUND)
    ctx.set_line_width(5 * s)
    ctx.move_to(*p0); ctx.curve_to(*c1, *c2, *p3); ctx.stroke()
    n = 7
    for i in range(n):
        t = 0.12 + 0.82 * i / (n - 1)
        x, y = pt(t)
        x2, y2 = pt(min(t + 0.01, 1))
        ang = math.atan2(y2 - y, x2 - x)
        side = 1 if i % 2 == 0 else -1
        bl = (46 - 22 * t) * s           # blade length shrinks to the tip
        bw = (13 - 5 * t) * s
        ctx.save(); ctx.translate(x, y); ctx.rotate(ang + side * 0.9)
        ctx.move_to(0, 0)
        ctx.curve_to(bl*0.3, -bw, bl*0.8, -bw*0.8, bl, 0)
        ctx.curve_to(bl*0.8, bw*0.6, bl*0.3, bw*0.7, 0, 0)
        ctx.close_path(); ctx.fill(); ctx.restore()
    ctx.arc(*p3, 6 * s, 0, 2*math.pi); ctx.fill()

def shell(ctx, s, col, rng):
    # filled spiral shell body + navy-ish spiral line on top
    R = 34 * s
    ctx.set_source_rgb(*col)
    ctx.arc(0, 0, R, 0, 2*math.pi); ctx.fill()
    # lip / opening
    ctx.move_to(R*0.2, R*0.95)
    ctx.curve_to(R*1.1, R*1.25, R*1.45, R*0.4, R*0.95, -R*0.1)
    ctx.line_to(R*0.6, R*0.6); ctx.close_path(); ctx.fill()
    # logarithmic spiral
    ln = CREAM
    ctx.set_source_rgb(*ln)
    ctx.set_line_width(3.2 * s); ctx.set_line_cap(cairo.LINE_CAP_ROUND)
    a, b = R * 0.06, 0.19
    first = True
    for k in range(0, 260):
        th = k * 0.06
        r = a * math.exp(b * th)
        if r > R * 0.88: break
        x, y = r * math.cos(th), r * math.sin(th)
        (ctx.move_to if first else ctx.line_to)(x, y); first = False
    ctx.stroke()
    ctx.arc(0, 0, 2.6 * s, 0, 2*math.pi); ctx.fill()

def wave(ctx, s, col, rng):
    # a curling wave crest: swell rising into a spiral curl, plus two trailing lines
    w = 150 * s
    ctx.set_source_rgb(*col)
    ctx.set_line_cap(cairo.LINE_CAP_ROUND); ctx.set_line_join(cairo.LINE_JOIN_ROUND)
    ctx.set_line_width(7 * s)
    cx, cy, R = w*0.18, -w*0.12, w*0.2
    ctx.move_to(-w/2, w*0.15)
    ctx.curve_to(-w*0.25, w*0.15, -w*0.1, -w*0.32, cx, cy - R)
    # spiral curl inward
    first = True
    for k in range(0, 120):
        th = -math.pi/2 + k * 0.07
        r = R * (1 - k / 135)
        x, y = cx + r * math.cos(th), cy + r * math.sin(th)
        ctx.line_to(x, y)
    ctx.stroke()
    ctx.set_line_width(5 * s)
    for j, off in enumerate((0.13, 0.25)):
        ctx.move_to(-w/2 + w*0.1*j + w*0.05, w*off + w*0.15)
        ctx.curve_to(-w*0.1, w*(off + 0.08), w*0.15, w*(off + 0.02), w*0.45 - w*0.12*j, w*off + w*0.03)
        ctx.stroke()

def dot(ctx, s, col, rng):
    ctx.set_source_rgb(*col); ctx.arc(0, 0, s, 0, 2*math.pi); ctx.fill()

# ---------------------------------------------------------------- layout on a torus
def tdist(a, b):
    dx = abs(a[0] - b[0]); dy = abs(a[1] - b[1])
    dx = min(dx, T - dx); dy = min(dy, T - dy)
    return math.hypot(dx, dy)

def layout():
    rng = random.Random(SEED)
    placed = []   # (kind, x, y, radius, scale, rot, color)
    def try_place(kind, n, rad_fn, colors, tries=4000, pad=14):
        c = 0
        for _ in range(tries):
            if c >= n: break
            sc = rad_fn()
            r = sc[0]
            p = (rng.uniform(0, T), rng.uniform(0, T))
            if all(tdist(p, (q[1], q[2])) > r + q[3] + pad for q in placed):
                placed.append((kind, p[0], p[1], r, sc[1], rng.uniform(0, 2*math.pi),
                               colors[c % len(colors)]))
                c += 1
        return c
    def kelp_s():
        s = rng.uniform(0.75, 1.15); return (95 * s, s)
    def wave_s():
        s = rng.uniform(0.7, 1.1); return (80 * s, s)
    def shell_s():
        s = rng.uniform(0.55, 1.0); return (44 * s, s)
    try_place('kelp', 5, kelp_s, [NAVY, FOAM, NAVY, FOAM])
    try_place('wave', 5, wave_s, [NAVY, CORAL, FOAM, NAVY])
    try_place('shell', 8, shell_s, [AMBER])
    def dot_s():
        r = rng.choice([4, 5, 6, 7, 9]); return (r, r)
    try_place('dot', 93, dot_s, [NAVY, AMBER, CORAL, FOAM], tries=20000, pad=12)
    # shells & kelp: rotation limited a bit so kelp reads as upright-ish fronds
    out = []
    for k, x, y, r, s, rot, col in placed:
        if k == 'kelp': rot = rng.uniform(-0.6, 0.6)
        if k == 'wave': rot = rng.uniform(-0.5, 0.5) + (math.pi if rng.random() < 0.0 else 0)
        out.append((k, x, y, r, s, rot, col, rng.random()))
    return out

FN = {'kelp': kelp, 'wave': wave, 'shell': shell, 'dot': dot}

def draw_tile(ctx, items):
    ctx.set_source_rgb(*CREAM); ctx.rectangle(0, 0, T, T); ctx.fill()
    order = {'kelp': 0, 'wave': 1, 'shell': 2, 'dot': 3}
    for k, x, y, r, s, rot, col, seed in sorted(items, key=lambda i: order[i[0]]):
        for dx in (-T, 0, T):
            for dy in (-T, 0, T):
                # skip copies that cannot touch the tile
                if x + dx + r*1.6 < 0 or x + dx - r*1.6 > T or y + dy + r*1.6 < 0 or y + dy - r*1.6 > T:
                    continue
                ctx.save(); ctx.translate(x + dx, y + dy); ctx.rotate(rot)
                FN[k](ctx, s, col, random.Random(seed))   # same seed => identical copies
                ctx.restore()

def main():
    items = layout()
    print({k: sum(1 for i in items if i[0] == k) for k in FN})
    surf = cairo.ImageSurface(cairo.FORMAT_RGB24, T, T)
    draw_tile(cairo.Context(surf), items)
    png = os.path.join(OUT, 'tile.png'); surf.write_to_png(png)
    svg = cairo.SVGSurface(os.path.join(OUT, 'tile.svg'), T, T)
    svg.set_document_unit(cairo.SVG_UNIT_PX)
    draw_tile(cairo.Context(svg), items); svg.finish()

    tile = Image.open(png).convert('RGB')
    prev = Image.new('RGB', (3*T, 3*T))
    for i in range(3):
        for j in range(3): prev.paste(tile, (i*T, j*T))
    prev.save(os.path.join(OUT, 'preview-3x3.png'))

    # mug wrap: pattern tiled across 2550x1050, centred cream label
    W, H = 2550, 1050
    ms = cairo.ImageSurface(cairo.FORMAT_RGB24, W, H)
    c = cairo.Context(ms)
    pat = cairo.SurfacePattern(surf); pat.set_extend(cairo.EXTEND_REPEAT)
    c.set_source(pat); c.paint()
    lw, lh, rad = 600, 300, 36
    lx, ly = (W - lw) / 2, (H - lh) / 2
    def rrect(x, y, w, h, r):
        c.new_sub_path()
        c.arc(x+w-r, y+r, r, -math.pi/2, 0); c.arc(x+w-r, y+h-r, r, 0, math.pi/2)
        c.arc(x+r, y+h-r, r, math.pi/2, math.pi); c.arc(x+r, y+r, r, math.pi, 1.5*math.pi)
        c.close_path()
    rrect(lx, ly, lw, lh, rad); c.set_source_rgb(*CREAM); c.fill_preserve()
    c.set_source_rgb(*NAVY); c.set_line_width(4); c.stroke()
    rrect(lx+14, ly+14, lw-28, lh-28, rad-12); c.set_line_width(1.5); c.stroke()
    c.select_font_face('P052', cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
    c.set_font_size(112)
    e = c.text_extents('Tidewick')
    c.move_to(W/2 - e.width/2 - e.x_bearing, H/2 - e.height/2 - e.y_bearing)
    c.show_text('Tidewick')
    ms.write_to_png(os.path.join(OUT, 'mug-wrap.png'))

    # seam check: wrapped tile edges vs neighbouring interior rows
    a = np.asarray(tile).astype(int)
    print('edge diff L/R', np.abs(a[:, 0] - a[:, -1]).mean(), 'T/B', np.abs(a[0] - a[-1]).mean(),
          'interior adjacent-col', np.abs(a[:, 500] - a[:, 501]).mean())

if __name__ == '__main__':
    main()
