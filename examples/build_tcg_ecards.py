"""Cheeky trading-card-game ecards: a tilted collectible card plus a message, all editable layers.

The cards are generic (no real game's name, frame or art) so the set is safe to share.
"""

import argparse
import textwrap
from pathlib import Path
from vixl import Project
from vixl.fonts import import_font

W, H = 1200, 800
SERIF, SANS = "DejaVu-Serif", "DejaVu-Sans"
FONT_FILES = {SERIF: "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf",
              SANS: "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"}
CREAM, GOLD, INK = "#fbf3dc", "#f0c35a", "#1d1a24"

# slug, backdrop, backdrop-dark, frame, card name, cost pips, icon, art top, art bottom,
# type line, rules text, stat, headline, subline, tapped
CARDS = [
    ("booster-pack", "#3a1a6e", "#150a33", "#7a4de0", "Your Booster Pack", ["#f0c35a", "#e0486a"],
     "star", "#ffd86b", "#d4467a", "Rare Encounter — Foil",
     "When you open this pack, draw something shiny. Gently.", "5/5",
     "Let's open a pack\ntogether. I'm hoping\nfor a holo.", "Slow hands only. No creasing.", False),
    ("tap-me", "#0f4a46", "#06211f", "#2fb39a", "You, Tonight", ["#7fe0c8"],
     "ring", "#9ff3df", "#2a7f9a", "Enchantment — Invitation",
     "Tap me for one very good time. Untaps next turn.", "♥/♥",
     "Tap me.\nI promise I untap\nnext turn.", "Summoning sickness is the only thing slowing me down.", True),
    ("mint-condition", "#5a3a0c", "#241505", "#e1ad3a", "Mint Condition", ["#fbf3dc", "#e1ad3a"],
     "chevron", "#fff0b8", "#d98a2b", "Graded 10 — Gem",
     "Perfect centering. Sharp corners. Never been handled.", "10/10",
     "Mint condition.\nNever been handled.", "…yet.", False),
    ("trade", "#10375c", "#071729", "#4a9be0", "Fair Trade", ["#8fc4f2", "#f08aa8"],
     "arrow", "#a8d4ff", "#4568c8", "Sorcery — Negotiation",
     "Show me yours and I'll show you mine. Both players draw.", "2/2",
     "Wanna trade?\nI'll show you my rare\nif you show me yours.", "Binder rules: look, don't fold.", False),
    ("double-sleeved", "#5a1030", "#26061a", "#e0486a", "Fully Protected", ["#f08aa8", "#fbf3dc"],
     "shield", "#ffb3c8", "#a82a5c", "Artifact — Safety",
     "Double-sleeved. Top-loaded. Handled with care and a little bit of rough.", "0/9",
     "Double-sleeved,\ntop-loaded, and\nready for you.", "Safety first. Fun second. Round two third.", False),
    ("chase-card", "#4a2a08", "#1f1103", "#f0a23a", "Chase Card", ["#ffd86b", "#ffd86b", "#e0486a"],
     "heart", "#ffe6a0", "#e0486a", "Legendary Creature — Crush",
     "Never left in a binder. Always in my hands.", "9/9",
     "You're my chase card.\nI'd sleeve you\nfirst.", "Full-art, holo, and way out of my league.", False),
    ("draw-two", "#3a0f4a", "#16061f", "#c04ad8", "Draw Two", ["#e8a0f4"],
     "triangle", "#f0b8ff", "#8a3ad0", "Instant — Come Over",
     "Draw two. Your place or mine? Both are legal.", "2/∞",
     "Draw two.\nYour place or mine?", "Either way, I'm bringing the good snacks.", False),
    ("mana-flood", "#0c3a5a", "#051a2a", "#3ab0e0", "Mana Overflow", ["#7fd4f8", "#7fd4f8", "#7fd4f8", "#7fd4f8"],
     "tag", "#a8e8ff", "#2a68c8", "Land — Tidal Isle",
     "Tap for blue. Tap again for more. Never run dry.", "∞/∞",
     "You give me\nmana flood.", "I'm overflowing and I have no plans to discard.", False),
]


def wrap(text, width):
    return textwrap.fill(text, width)


def tcg_card(c, x, y, angle):
    """A portrait collectible card (300x420) drawn from editable layers."""
    (_, _, _, frame, name, pips, icon, art_a, art_b, type_line, rules, stat, *_rest) = c
    w, h = 300, 420
    ops = [
        {"type": "shape", "shape": "rectangle", "name": "c-body", "width": w, "height": h, "fill": INK,
         "x": x, "y": y},
        {"type": "round-corners", "target": "c-body", "radius": 18},
        {"type": "shape", "shape": "rectangle", "name": "c-frame", "width": w - 14, "height": h - 14,
         "fill": frame, "x": x + 7, "y": y + 7},
        {"type": "round-corners", "target": "c-frame", "radius": 13},
        {"type": "shape", "shape": "rectangle", "name": "c-title", "width": w - 34, "height": 36,
         "fill": CREAM, "stroke": INK, "stroke_width": 2, "x": x + 17, "y": y + 17},
        {"type": "round-corners", "target": "c-title", "radius": 8},
        {"type": "text", "name": "c-name", "text": name, "size": 17, "color": INK, "font": SERIF,
         "x": x + 26, "y": y + 24},
    ]
    # Cost pips along the top-right, over the title bar.
    for i, pip in enumerate(pips):
        ops.append({"type": "shape", "shape": "ellipse", "name": f"c-pip{i}", "width": 17, "height": 17,
                    "fill": pip, "stroke": INK, "stroke_width": 2, "x": x + w - 36 - i * 21, "y": y + 27})
    ops += [
        {"type": "gradient", "name": "c-art", "start": art_a, "end": art_b, "width": w - 44, "height": 170,
         "x": x + 22, "y": y + 62},
        {"type": "shape", "shape": icon, "name": "c-icon", "width": 110, "height": 110,
         "fill": "#fffaf0", "stroke": INK, "stroke_width": 3, "x": x + w / 2 - 55, "y": y + 92},
        {"type": "shape", "shape": "rectangle", "name": "c-art-edge", "width": w - 44, "height": 170,
         "fill": "none", "stroke": INK, "stroke_width": 3, "x": x + 22, "y": y + 62},
        {"type": "shape", "shape": "rectangle", "name": "c-type", "width": w - 34, "height": 28,
         "fill": CREAM, "stroke": INK, "stroke_width": 2, "x": x + 17, "y": y + 240},
        {"type": "text", "name": "c-type-text", "text": type_line, "size": 13, "color": INK, "font": SANS,
         "x": x + 25, "y": y + 246},
        {"type": "shape", "shape": "rectangle", "name": "c-rules", "width": w - 34, "height": 110,
         "fill": "#f6ead0", "stroke": INK, "stroke_width": 2, "x": x + 17, "y": y + 274},
        {"type": "text", "name": "c-rules-text", "text": wrap(rules, 30), "size": 13, "color": INK,
         "font": SANS, "spacing": 5, "x": x + 27, "y": y + 285},
        {"type": "shape", "shape": "rectangle", "name": "c-stat", "width": 66, "height": 26,
         "fill": CREAM, "stroke": INK, "stroke_width": 2, "x": x + w - 83, "y": y + 376},
        {"type": "text", "name": "c-stat-text", "text": stat, "size": 14, "color": INK, "font": SERIF,
         "x": x + w - 72, "y": y + 381},
        {"type": "group", "name": "tcg-card", "targets": [
            "c-body", "c-frame", "c-title", "c-name", *[f"c-pip{i}" for i in range(len(pips))],
            "c-art", "c-icon", "c-art-edge", "c-type", "c-type-text", "c-rules", "c-rules-text",
            "c-stat", "c-stat-text"]},
        {"type": "rotate", "target": "tcg-card", "value": angle},
        {"type": "layer-style", "target": "tcg-card", "name": "drop-shadow",
         "settings": {"color": "#000000", "opacity": 0.55, "blur": 26, "dx": -6, "dy": 14}},
    ]
    return ops


def build(c, out):
    slug, felt, dark, frame, *_mid, headline, sub, tapped = c
    p = Project(W, H, dark)
    for family, path in FONT_FILES.items():
        import_font(p, path, family)
    lines = headline.count("\n") + 1
    top = 400 - lines * 36 - 30
    rule_y = top + lines * 62 + 20
    ops = [
        {"type": "gradient", "name": "backdrop", "start": felt, "end": dark},
        {"type": "look", "target": "backdrop", "look": "grain", "amount": 0.25},
        {"type": "shape", "shape": "rectangle", "name": "gold-frame", "width": W - 48, "height": H - 48,
         "fill": "none", "stroke": GOLD, "stroke_width": 3, "x": 24, "y": 24},
        {"type": "shape", "shape": "rectangle", "name": "gold-frame-inner", "width": W - 66, "height": H - 66,
         "fill": "none", "stroke": GOLD, "stroke_width": 1, "x": 33, "y": 33},
    ]
    ops += tcg_card(c, 60 if tapped else 150, 190, 90 if tapped else -7)
    ops += [
        {"type": "text", "name": "headline", "text": headline, "size": 46, "color": CREAM, "font": SERIF,
         "align": "left", "spacing": 14, "x": 570, "y": top},
        {"type": "solid", "name": "rule", "width": 70, "height": 4, "color": GOLD, "x": 574, "y": rule_y},
        {"type": "text", "name": "subline", "text": wrap(sub, 38), "size": 21, "color": GOLD, "font": SANS,
         "align": "left", "spacing": 8, "x": 574, "y": rule_y + 24},
        {"type": "text", "name": "footer", "text": "◆   LIMITED PRINT RUN OF ONE   ◆", "size": 15,
         "color": "#b4a8c8", "font": SANS, "x": "center", "y": 722},
    ]
    p.apply(ops)
    p.save(out / f"{slug}.vixl")
    p.export(out / f"{slug}.png", overwrite=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", default="examples/output/tcg-ecards")
    out = Path(ap.parse_args().output)
    out.mkdir(parents=True, exist_ok=True)
    for card in CARDS:
        build(card, out)
    print(f"Wrote {len(CARDS)} ecards to {out.resolve()}")
