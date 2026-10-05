"""Generates the lighthouse-keeper sprite sheet, JSON and GIFs (Pillow + NumPy only)."""
import json, os
import numpy as np
from PIL import Image

OUT = os.path.dirname(os.path.abspath(__file__))
W = H = 32
GROUND = 30  # bottom row of the supporting boot in every frame

PAL = {
    'O': (26, 20, 32),     # outline / eye
    'Y': (206, 42, 46),    # raincoat (red)
    'y': (138, 22, 38),    # raincoat shade
    'L': (246, 104, 92),   # raincoat highlight
    'S': (240, 184, 138),  # skin
    's': (190, 120, 84),   # skin shade
    'P': (60, 84, 130),    # near trouser leg
    'p': (38, 52, 88),     # far trouser leg
    'B': (70, 54, 74),     # boots
    'b': (112, 94, 116),   # boot highlight
    'G': (96, 100, 116),   # lantern metal
    'F': (255, 246, 190),  # lantern glass glow
    'f': (255, 150, 40),   # flame
}

HEAD = [
    "...YYYYY...",
    "..YLLYYYYY.",
    ".YLYYYYYYYY",
    ".YYYYySSSS.",
    "yYYYYySSOSS",
    "yYYYYySSSS.",
    ".yYYYYsSSs.",
    "..yYYYYYY..",
]
COAT = [
    "..yYYYYYY..",
    ".yyYYYYYYY.",
    ".yyYYYYYOY.",
    ".yyYYYYYYY.",
    ".yyYYYYYOY.",
    "yyyYYYYYYYY",
    "yyyYYYYYOYY",
    "yyyLYYYYYYY",
    "yyyyyyyyyyy",
]
LANTERN = [
    "..G..",
    ".GGG.",
    "GFFFG",
    "GFfFG",
    "GFFFG",
    ".GGG.",
]

def art(rows, ox, oy):
    return {(ox + x, oy + y): c for y, r in enumerate(rows) for x, c in enumerate(r) if c != '.'}

def leg(hip_x, hip_y, ankle_x, lift, pants):
    part = {}
    top_boot = GROUND - 2 - lift
    for y in range(hip_y, top_boot):
        t = (y - hip_y) / max(1, top_boot - 1 - hip_y)
        c = round(hip_x + (ankle_x - hip_x) * t)
        for x in (c - 1, c, c + 1):
            part[(x, y)] = pants
    a = ankle_x
    for x in range(a - 1, a + 2):
        part[(x, top_boot)] = 'B'
    for x in range(a - 1, a + 3):
        part[(x, top_boot + 1)] = 'B'
        part[(x, top_boot + 2)] = 'B'
    part[(a + 1, top_boot + 1)] = 'b'
    return part

def arm(sx, sy, wx, wy):
    part = {}
    n = max(abs(wx - sx), abs(wy - sy))
    for i in range(n + 1):
        x = round(sx + (wx - sx) * i / n); y = round(sy + (wy - sy) * i / n)
        for dx in (0, 1):
            for dy in (0, 1):
                part[(x + dx, y + dy)] = 'Y'
    part[(sx, sy)] = 'L'
    part[(wx + 1, wy + 2)] = 'S'; part[(wx + 2, wy + 2)] = 'S'; part[(wx + 2, wy + 1)] = 's'
    return part, (wx + 2, wy + 3)

def wave_arm(sx, sy, wx, wy):
    """Far arm raised overhead, drawn behind head/coat; open hand above the hood."""
    part = {}
    n = max(abs(wx - sx), abs(wy - sy))
    for i in range(n + 1):
        x = round(sx + (wx - sx) * i / n); y = round(sy + (wy - sy) * i / n)
        for dx in (0, 1):
            part[(x + dx, y)] = 'y'
    for dx in (0, 1):                      # palm, 2 wide x 3 tall
        for dy in (1, 2, 3):
            part[(wx + dx, wy - dy)] = 'S'
    part[(wx + 2, wy - 1)] = 's'           # thumb
    return part

def stamp(canvas, part):
    """Draw a part with its own 1px dark outline (4-neighbour)."""
    for (x, y) in part:
        for nx, ny in ((x+1, y), (x-1, y), (x, y+1), (x, y-1)):
            if (nx, ny) not in part and 0 <= nx < W and 0 <= ny < H:
                canvas[ny][nx] = 'O'
    for (x, y), c in part.items():
        if 0 <= x < W and 0 <= y < H:
            canvas[y][x] = c

def frame(dy, far, near, arm_dx, sway, wave=None):
    canvas = [[None] * W for _ in range(H)]
    by = 14 + dy                       # coat top
    hip = by + 7
    stamp(canvas, leg(far[0], hip, far[1], far[2], 'p'))
    stamp(canvas, leg(near[0], hip, near[1], near[2], 'P'))
    if wave is not None:               # wrist position of the raised far arm
        stamp(canvas, wave_arm(13, by + 2, wave[0], wave[1]))
    stamp(canvas, art(COAT, 10, by))
    stamp(canvas, art(HEAD, 10, by - 8))
    a, hand = arm(16, by + 2, 20 + arm_dx, by + 5)
    stamp(canvas, art(LANTERN, hand[0] - 2 + sway, hand[1]))
    stamp(canvas, a)
    return canvas

FRAMES = [
    # name,   duration, dy, far leg (hip,ankle,lift), near leg, arm dx, lantern sway
    ("idle_1", 400, 0, (14, 14, 0), (16, 17, 0), 0, 0),
    ("idle_2", 400, 1, (14, 14, 0), (16, 17, 0), 0, 1),
    ("walk_1", 120, 0, (14, 10, 0), (16, 20, 0), -1, 1),
    ("walk_2", 120, -1, (14, 13, 2), (16, 16, 0), 0, 0),
    ("walk_3", 120, 0, (14, 19, 0), (16, 11, 0), 1, -1),
    ("walk_4", 120, -1, (15, 16, 0), (15, 13, 2), 0, 0),
    # wave: idle stance, far arm raised overhead, hand tilts back then forward
    ("wave_1", 250, 0, (14, 14, 0), (16, 17, 0), 0, 0, (8, 6)),
    ("wave_2", 250, 0, (14, 14, 0), (16, 17, 0), 0, 1, (17, 4)),
]

def to_rgba(canvas):
    a = np.zeros((H, W, 4), np.uint8)
    for y in range(H):
        for x in range(W):
            c = canvas[y][x]
            if c:
                a[y, x] = (*PAL[c], 255)
    return a

imgs = [to_rgba(frame(*f[2:])) for f in FRAMES]
sheet = np.concatenate(imgs, axis=1)
Image.fromarray(sheet).save(os.path.join(OUT, "keeper-sheet.png"))

meta = {"image": "keeper-sheet.png", "size": {"w": 256, "h": 32}, "frames": [
    {"name": f[0], "x": i * 32, "y": 0, "width": 32, "height": 32, "duration": f[1]}
    for i, f in enumerate(FRAMES)],
    "animations": {"idle": ["idle_1", "idle_2"], "walk": ["walk_1", "walk_2", "walk_3", "walk_4"],
                   "wave": ["wave_1", "wave_2"]}}
with open(os.path.join(OUT, "keeper-sheet.json"), "w") as fh:
    json.dump(meta, fh, indent=2)

# Shared palette: index 0 = transparent, 1.. = sprite colours
keys = list(PAL)
flat = [255, 0, 255] + [v for k in keys for v in PAL[k]]
flat += [0] * (768 - len(flat))
lut = {PAL[k]: i + 1 for i, k in enumerate(keys)}

def to_p(rgba, scale=8):
    idx = np.zeros((H, W), np.uint8)
    for y in range(H):
        for x in range(W):
            if rgba[y, x, 3]:
                idx[y, x] = lut[tuple(rgba[y, x, :3])]
    idx = idx.repeat(scale, 0).repeat(scale, 1)  # nearest-neighbour 8x
    im = Image.fromarray(idx); im.putpalette(flat)  # L -> P with our palette
    return im

for anim, sel in (("idle", FRAMES[:2]), ("walk", FRAMES[2:6]), ("wave", FRAMES[6:])):
    ps = [to_p(imgs[FRAMES.index(f)]) for f in sel]
    ps[0].save(os.path.join(OUT, f"keeper-{anim}.gif"), save_all=True, append_images=ps[1:],
               duration=[f[1] for f in sel], loop=0, transparency=0, disposal=2, optimize=False)
print("colours used:", len({tuple(p) for p in sheet.reshape(-1, 4) if p[3]}))
