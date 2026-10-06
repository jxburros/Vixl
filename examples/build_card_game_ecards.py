"""Six cheeky card-gaming ecards, built only from editable Vixl layers."""

import argparse
import textwrap
from pathlib import Path
from vixl import Project
from vixl.fonts import import_font

W, H = 1200, 800
SERIF, SANS = "DejaVu-Serif", "DejaVu-Sans"
FONT_FILES = {SERIF: "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf",
              SANS: "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"}
RED, INK, CREAM, GOLD = "#c8283c", "#1b1b22", "#fbf6ea", "#e6c06a"

# (slug, felt, felt-dark, headline, subline, card faces [(rank, suit)], pose)
CARDS = [
    ("full-house", "#12503a", "#082a1f", "Care to see\nmy full house?",
     "Three of a kind, two of a kind, and a very open door.",
     [("K", "♥"), ("K", "♠"), ("K", "♦"), ("7", "♣"), ("7", "♥")]),
    ("hit-me", "#5a1230", "#2a0716", "Hit me.\nI'm not the type\nto stand.",
     "Twenty-one never looked so good on you.",
     [("A", "♠"), ("K", "♥")]),
    ("strip-poker", "#2c1a5c", "#120a2c", "Strip poker?\nI fold…\neventually.",
     "Fair warning: I'm wearing a lot of layers.",
     [("2", "♣"), ("7", "♦"), ("J", "♠"), ("4", "♥"), ("9", "♣")]),
    ("royal-flush", "#0f3d57", "#071d2c", "You make me\nfeel like a\nroyal flush.",
     "Hot, hard to beat, and best enjoyed together.",
     [("10", "♥"), ("J", "♥"), ("Q", "♥"), ("K", "♥"), ("A", "♥")]),
    ("shuffle", "#6b2a12", "#2e1006", "Let's shuffle.\nThen I'll deal\nwith you.",
     "I'll cut the deck. You cut the small talk.",
     [("Q", "♥"), ("J", "♣"), ("A", "♦"), ("3", "♠")]),
    ("all-in", "#143d2e", "#06201a", "I'm all in.\nAre you?",
     "No bluffing. Winner takes the night.",
     [("A", "♥"), ("A", "♠")]),
]


def wrap(text, width=34):
    return textwrap.fill(text, width)


def card(name, rank, suit, x, y, angle, scale=1.0):
    """One playing card: white face, corner index, big centre pip."""
    w, h = int(200 * scale), int(280 * scale)
    colour = RED if suit in "♥♦" else INK
    ops = [
        {"type": "shape", "shape": "rectangle", "name": f"{name}-face", "width": w, "height": h,
         "fill": CREAM, "stroke": "#b9ad92", "stroke_width": 2, "x": x, "y": y},
        {"type": "round-corners", "target": f"{name}-face", "radius": int(16 * scale)},
        {"type": "text", "name": f"{name}-rank", "text": rank, "size": int(40 * scale), "color": colour,
         "font": SERIF, "x": x + int(14 * scale), "y": y + int(8 * scale)},
        {"type": "text", "name": f"{name}-corner", "text": suit, "size": int(34 * scale), "color": colour,
         "font": SANS, "x": x + int(16 * scale), "y": y + int(52 * scale)},
        {"type": "text", "name": f"{name}-pip", "text": suit, "size": int(120 * scale), "color": colour,
         "font": SANS, "x": x + int(w / 2 - 50 * scale), "y": y + int(h / 2 - 78 * scale)},
        {"type": "group", "name": name, "targets": [f"{name}-face", f"{name}-rank", f"{name}-corner",
                                                      f"{name}-pip"]},
        {"type": "rotate", "target": name, "value": angle},
        {"type": "layer-style", "target": name, "name": "drop-shadow",
         "settings": {"color": "#000000", "opacity": 0.45, "blur": 18, "dx": -4, "dy": 10}},
    ]
    return ops


def build(slug, felt, dark, headline, sub, faces, out):
    p = Project(W, H, dark)
    for family, path in FONT_FILES.items():
        import_font(p, path, family)
    ops = [
        {"type": "gradient", "name": "felt", "start": felt, "end": dark},
        {"type": "look", "target": "felt", "look": "grain", "amount": 0.3},
        {"type": "shape", "shape": "rectangle", "name": "gold-frame", "width": W - 48, "height": H - 48,
         "fill": "none", "stroke": GOLD, "stroke_width": 3, "x": 24, "y": 24},
        {"type": "shape", "shape": "rectangle", "name": "gold-frame-inner", "width": W - 66, "height": H - 66,
         "fill": "none", "stroke": GOLD, "stroke_width": 1, "x": 33, "y": 33},
    ]
    # Fan of cards on the left, rotated about each card's own centre.
    n = len(faces)
    gap = 96 if n < 4 else 66
    for i, (rank, suit) in enumerate(faces):
        t = i - (n - 1) / 2
        ops += card(f"card{i + 1}", rank, suit, 196 + gap * t, 250 - abs(t) * 12, t * 10)
    lines = headline.count("\n") + 1
    top = 400 - lines * 38 - 40
    rule_y = top + lines * 66 + 22
    ops += [
        {"type": "text", "name": "headline", "text": headline, "size": 50, "color": CREAM, "font": SERIF,
         "align": "left", "spacing": 12, "x": 650, "y": top},
        {"type": "solid", "name": "rule", "width": 70, "height": 4, "color": GOLD, "x": 654, "y": rule_y},
        {"type": "text", "name": "subline", "text": wrap(sub), "size": 22, "color": GOLD, "font": SANS,
         "align": "left", "spacing": 8, "x": 654, "y": rule_y + 24},
        {"type": "text", "name": "footer", "text": "♠ ♥ ♣ ♦   DEALT WITH LOVE   ♦ ♣ ♥ ♠", "size": 16,
         "color": "#9fb3a8", "font": SANS, "x": "center", "y": 722},
    ]
    p.apply(ops)
    p.save(out / f"{slug}.vixl")
    p.export(out / f"{slug}.png", overwrite=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", default="examples/output/ecards")
    out = Path(ap.parse_args().output)
    out.mkdir(parents=True, exist_ok=True)
    for c in CARDS:
        build(*c, out)
    print(f"Wrote {len(CARDS)} ecards to {out.resolve()}")
