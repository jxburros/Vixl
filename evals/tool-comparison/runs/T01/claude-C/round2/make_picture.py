"""Generate picture.png: a lighthouse on a rocky point at night (flat travel-poster style).
Round 2: night sky, brighter beam, scene mirrored so the lighthouse is on the right, third sailboat.
Pure Pillow + NumPy. Drawn at 2x and downsampled with LANCZOS for clean anti-aliased edges."""
import numpy as np
from PIL import Image, ImageDraw

W, H = 2400, 1600
S = 2                      # supersampling factor
SW, SH = W * S, H * S
HORIZON = 1000             # horizon line (final px)

def P0(pts):  # scale points to supersampled space (no mirroring; used for stars)
    return [(x * S, y * S) for x, y in pts]

def P(pts):  # scale + mirror horizontally (round 2: lighthouse/rocks/sea details flipped to the other side)
    return [((W - x) * S, y * S) for x, y in pts]

def B(pts):  # mirrored box for rectangle/ellipse calls (Pillow needs x0 <= x1)
    (a, b), (c, e) = P(pts)
    return [(min(a, c), min(b, e)), (max(a, c), max(b, e))]

def lerp(a, b, t):
    return tuple(int(round(a[i] + (b[i] - a[i]) * t)) for i in range(3))

# ---------- sky: smooth multi-stop gradient navy -> indigo -> rose -> amber ----------
stops = [(0.00, (3, 5, 16)),       # near-black navy (night)
         (0.40, (9, 13, 38)),      # deep navy
         (0.70, (24, 26, 64)),     # dark indigo
         (0.88, (44, 38, 82)),     # dim violet
         (1.00, (70, 56, 96))]     # faint plum glow at horizon
ys = np.linspace(0, 1, HORIZON * S)
sky = np.zeros((HORIZON * S, 3))
for c in range(3):
    sky[:, c] = np.interp(ys, [s[0] for s in stops], [s[1][c] for s in stops])
img = np.zeros((SH, SW, 3), dtype=np.float64)
img[:HORIZON * S] = sky[:, None, :]

# ---------- sea: gradient from muted plum-teal at horizon to deep navy at bottom ----------
sea_stops = [(0.0, (70, 70, 110)), (0.25, (36, 48, 92)), (1.0, (10, 20, 46))]
ys2 = np.linspace(0, 1, SH - HORIZON * S)
sea = np.zeros((len(ys2), 3))
for c in range(3):
    sea[:, c] = np.interp(ys2, [s[0] for s in sea_stops], [s[1][c] for s in sea_stops])
img[HORIZON * S:] = sea[:, None, :]

base = Image.fromarray(img.clip(0, 255).astype(np.uint8)).convert("RGBA")

def layer():
    return Image.new("RGBA", (SW, SH), (0, 0, 0, 0))

def comp(lyr):
    global base
    base = Image.alpha_composite(base, lyr)

# ---------- stars (upper sky, small 4-point sparkles and dots) ----------
L = layer(); d = ImageDraw.Draw(L)
stars = [(180, 90, 5), (420, 210, 3), (700, 70, 4), (960, 170, 3), (1220, 60, 5),
         (1480, 150, 3), (1750, 80, 4), (2010, 190, 3), (2260, 100, 5), (1100, 300, 3),
         (300, 340, 3), (1640, 280, 3), (2150, 320, 2), (560, 400, 2)]
for x, y, r in stars:
    col = (255, 244, 214, 235)
    d.ellipse(P0([(x - r, y - r), (x + r, y + r)]), fill=col)
    if r >= 4:  # little four-point sparkle
        k = r * 2.6
        d.polygon(P0([(x, y - k), (x + r * 0.5, y), (x, y + k), (x - r * 0.5, y)]), fill=col)
        d.polygon(P0([(x - k, y), (x, y - r * 0.5), (x + k, y), (x, y + r * 0.5)]), fill=col)
comp(L)

# ---------- setting sun on the horizon (right of centre), flat disc + glow rings ----------
L = layer(); d = ImageDraw.Draw(L)
cx, cy = 1700, HORIZON
for rr, a in [(330, 28), (250, 40), (180, 60)]:
    d.ellipse(B([(cx - rr, cy - rr), (cx + rr, cy + rr)]), fill=(255, 196, 110, a))
d.ellipse(B([(cx - 120, cy - 120), (cx + 120, cy + 120)]), fill=(255, 214, 130, 255))
comp(L)

# ---------- distant headland silhouettes on the horizon ----------
L = layer(); d = ImageDraw.Draw(L)
d.polygon(P([(1950, HORIZON), (2050, 965), (2160, 945), (2260, 958), (2400, 940), (2400, HORIZON)]),
          fill=(112, 70, 100, 255))
d.polygon(P([(820, HORIZON), (930, 978), (1040, 970), (1130, HORIZON)]), fill=(130, 78, 104, 255))
comp(L)
# redraw the sea top so the sun is cut flat at the horizon
L = layer(); d = ImageDraw.Draw(L)
arr = np.array(base)
seapart = Image.fromarray(img[HORIZON * S:].clip(0, 255).astype(np.uint8)).convert("RGBA")
base.paste(seapart, (0, HORIZON * S))

# ---------- sea: sun reflection streaks + flat horizontal wave bands ----------
L = layer(); d = ImageDraw.Draw(L)
refl = [(1010, 210, 14), (1032, 170, 10), (1055, 130, 9), (1082, 96, 8), (1112, 70, 7), (1146, 48, 6)]
for y, half, h in refl:
    d.rounded_rectangle(B([(cx - half, y), (cx + half, y + h)]), radius=h * S / 2, fill=(255, 196, 112, 200))
waves = [(1180, 300, 520, 6), (1240, 1250, 1500, 5), (1330, 700, 1080, 6), (1420, 1900, 2300, 6),
         (1500, 400, 900, 7), (1560, 1400, 1850, 6), (1130, 2050, 2350, 5)]
for y, x0, x1, h in waves:
    d.rounded_rectangle(B([(x0, y), (x1, y + h)]), radius=h * S / 2, fill=(90, 100, 150, 120))
comp(L)

# ---------- lighthouse beam: brighter translucent wedge (mirrored: sweeps left across the sea) ----------
LAMP = (560, 452)
L = layer(); d = ImageDraw.Draw(L)
d.polygon(P([LAMP, (2400, 380), (2400, 1060)]), fill=(255, 222, 120, 100))
d.polygon(P([LAMP, (2400, 520), (2400, 900)]), fill=(255, 230, 140, 135))
d.polygon(P([LAMP, (2400, 650), (2400, 780)]), fill=(255, 240, 170, 175))
comp(L)

# ---------- rocky point (left), layered flat facets ----------
L = layer(); d = ImageDraw.Draw(L)
d.polygon(P([(0, 760), (180, 700), (360, 690), (520, 720), (700, 760), (860, 860), (1000, 980),
             (1080, 1060), (1120, 1130), (0, 1130)]), fill=(46, 36, 66, 255))      # back mass
d.polygon(P([(0, 900), (240, 820), (520, 830), (760, 900), (980, 1010), (1180, 1120), (1280, 1220),
             (1320, 1600), (0, 1600)]), fill=(30, 24, 48, 255))                    # front mass
# lit facets (amber side light from the sunset)
lit = (96, 60, 86, 255)
d.polygon(P([(520, 720), (700, 760), (860, 860), (760, 900), (610, 820)]), fill=lit)
d.polygon(P([(860, 860), (1000, 980), (1080, 1060), (980, 1010)]), fill=lit)
d.polygon(P([(760, 900), (980, 1010), (1180, 1120), (1080, 1120), (900, 1020)]), fill=(70, 46, 74, 255))
d.polygon(P([(1180, 1120), (1280, 1220), (1320, 1600), (1240, 1600), (1210, 1300)]), fill=(58, 40, 66, 255))
# small boulders at the waterline
d.polygon(P([(1300, 1400), (1360, 1360), (1440, 1380), (1470, 1440), (1300, 1450)]), fill=(30, 24, 48, 255))
d.polygon(P([(1360, 1360), (1440, 1380), (1400, 1400)]), fill=lit)
# foam where rocks meet sea
for y, x0, x1 in [(1452, 1290, 1500), (1240, 1270, 1420), (1150, 1150, 1250)]:
    d.rounded_rectangle(B([(x0, y), (x1, y + 7)]), radius=7, fill=(220, 210, 230, 150))
comp(L)

# ---------- lighthouse ----------
L = layer(); d = ImageDraw.Draw(L)
bx, by = 560, 760          # base centre on the rocks
top_y = 520
bw, tw = 82, 54            # half widths at base / top
def tower_x(y, side):
    t = (by - y) / (by - top_y)
    hw = bw + (tw - bw) * t
    return bx + side * hw
# white tower body
d.polygon(P([(tower_x(by, -1), by), (tower_x(top_y, -1), top_y), (tower_x(top_y, 1), top_y),
             (tower_x(by, 1), by)]), fill=(244, 232, 220, 255))
# red bands
red = (200, 56, 60, 255)
for y0, y1 in [(700, 650), (600, 560)]:
    d.polygon(P([(tower_x(y0, -1), y0), (tower_x(y1, -1), y1), (tower_x(y1, 1), y1), (tower_x(y0, 1), y0)]),
              fill=red)
# shadow side (right half, flat shade) - on its own layer so it blends over the bands
comp(L); L = layer(); d = ImageDraw.Draw(L)
d.polygon(P([(bx + 8, by), (bx + 6, top_y), (tower_x(top_y, 1), top_y), (tower_x(by, 1), by)]),
          fill=(40, 30, 70, 70))
comp(L); L = layer(); d = ImageDraw.Draw(L)
# door + window
d.rounded_rectangle(B([(bx - 16, by - 58), (bx + 16, by)]), radius=14, fill=(52, 36, 60, 255))
d.rounded_rectangle(B([(bx - 9, 612), (bx + 9, 642)]), radius=8, fill=(52, 36, 60, 255))
# base plinth
d.rectangle(B([(bx - 104, by - 6), (bx + 104, by + 18)]), fill=(70, 52, 78, 255))
# gallery
d.rectangle(B([(bx - 76, top_y - 14), (bx + 76, top_y)]), fill=(52, 36, 60, 255))
d.rectangle(B([(bx - 66, top_y - 22), (bx + 66, top_y - 14)]), fill=(52, 36, 60, 255))
# lantern room: glowing glass
glow = layer(); gd = ImageDraw.Draw(glow)
for rr, a in [(120, 30), (80, 50), (52, 80)]:
    gd.ellipse(B([(LAMP[0] - rr, LAMP[1] - rr), (LAMP[0] + rr, LAMP[1] + rr)]), fill=(255, 226, 140, a))
d.rectangle(B([(bx - 40, top_y - 92), (bx + 40, top_y - 22)]), fill=(255, 226, 140, 255))
d.rectangle(B([(bx - 4, top_y - 92), (bx + 4, top_y - 22)]), fill=(52, 36, 60, 255))  # mullion
# roof + finial
d.polygon(P([(bx - 54, top_y - 92), (bx, top_y - 150), (bx + 54, top_y - 92)]), fill=red)
d.polygon(P([(bx, top_y - 150), (bx + 54, top_y - 92), (bx + 6, top_y - 92)]), fill=(160, 40, 52, 255))
d.ellipse(B([(bx - 9, top_y - 166), (bx + 9, top_y - 148)]), fill=(52, 36, 60, 255))
comp(glow)
comp(L)

# ---------- three sailboats ----------
def sailboat(x, y, s, sail=(246, 236, 222, 255), sail2=(232, 200, 176, 255)):
    L = layer(); d = ImageDraw.Draw(L)
    # reflection
    d.polygon(P([(x - 46 * s, y + 4 * s), (x + 46 * s, y + 4 * s), (x + 10 * s, y + 70 * s), (x - 6 * s, y + 70 * s)]),
              fill=(240, 220, 200, 34))
    # mast
    d.rectangle(B([(x - 2 * s, y - 112 * s), (x + 2 * s, y - 12 * s)]), fill=(52, 36, 60, 255))
    # main sail and jib
    d.polygon(P([(x - 4 * s, y - 108 * s), (x - 4 * s, y - 18 * s), (x - 62 * s, y - 18 * s)]), fill=sail)
    d.polygon(P([(x + 4 * s, y - 96 * s), (x + 4 * s, y - 18 * s), (x + 44 * s, y - 18 * s)]), fill=sail2)
    # hull
    d.polygon(P([(x - 58 * s, y - 14 * s), (x + 62 * s, y - 14 * s), (x + 42 * s, y + 6 * s), (x - 44 * s, y + 6 * s)]),
              fill=(200, 56, 60, 255))
    comp(L)

sailboat(1560, 1180, 0.85)
sailboat(2080, 1360, 1.15, sail2=(244, 210, 150, 255))
sailboat(1880, 1110, 0.6)   # round 2: third, smaller and more distant boat

out = base.convert("RGB").resize((W, H), Image.LANCZOS)
out.save(__file__.replace("make_picture.py", "picture.png"))
print(out.size, out.mode)
