"""Side-by-side: the current Digital Shift logo, R2 (ripple) and R2b, light and dark, large and small.

R2b keeps the ripple in the x only: rippling the l detaches its bottom bands and it reads as "!".

Run from the repository root: PYTHONPATH=explorations/logo-alternatives python explorations/logo-alternatives/compare.py
"""

import io
import shutil
from pathlib import Path

from PIL import Image

from build import H, INK, OUT, PAPER, SKY, W, fonts, path, poly, rect
from build_m import wordmark
from build_r import ripple_reflection
from vixl import Project

KIT = Path("assets/brand/digital-shift/PNG")
WORK = OUT / "compare-parts"
MUTED = "#6B7080"


def x_only(ripple):
    """Ripple the x's reflection; leave the l's reflection one solid block."""
    def draw(name, points, x, y, fill, extra):
        if name.startswith("l"):
            return [path(name, poly(points), x, y, fill, **extra)]
        return ripple(name, points, x, y, fill, extra)
    return draw


def r2(dark, steady_l=False):
    p = Project(W, H, background="transparent")
    ripple = ripple_reflection(colours=(SKY, SKY, "#5A84DC", "#4467B0")) if dark else ripple_reflection()
    reflect = x_only(ripple) if steady_l else ripple
    if dark:
        wordmark(p, l_mode="split", ink=PAPER, reflection=SKY, reflect=reflect)
    else:
        wordmark(p, l_mode="split", reflect=reflect)
    slug = f"r2{'b' if steady_l else ''}-{'dark' if dark else 'light'}"
    if not dark:
        p.save(str(OUT / f"r2b-steady-l.vixl" if steady_l else OUT / "r2-ripple.vixl"), overwrite=True)
    return p.export(str(WORK / f"{slug}-full.png"), scale=2, overwrite=True)


def trimmed(name, data):
    """Crop to the ink so both logos are compared at the same visible width."""
    image = Image.open(io.BytesIO(data) if isinstance(data, bytes) else data)
    image = image.crop(image.getbbox())
    target = WORK / f"{name}.png"
    image.save(target)
    return target, image.size


def main():
    WORK.mkdir(parents=True, exist_ok=True)
    parts = {
        "old-light": trimmed("old-light", KIT / "horizontal-color@2x.png"),
        "old-dark": trimmed("old-dark", KIT / "horizontal-reverse@2x.png"),
        "new-light": trimmed("new-light", r2(False)),
        "new-dark": trimmed("new-dark", r2(True)),
        "fix-light": trimmed("fix-light", r2(False, steady_l=True)),
        "fix-dark": trimmed("fix-dark", r2(True, steady_l=True)),
    }
    cw, pad, gap, head = 640, 70, 36, 250
    tile_h = 380
    small_h = 300
    sheet = Project(pad * 2 + 3 * cw + 2 * gap, head + 2 * (tile_h + gap) + small_h + pad, background="#F3F2EE")
    bold, body = fonts(sheet, ("Inter Tight", 800), ("Inter", 400))
    ops = [
        {"type": "text", "name": "Title", "text": "Current logo and R2, side by side", "font": bold, "size": 60,
         "color": INK, "x": pad, "y": 56},
        {"type": "text", "name": "Subtitle", "text": "Each trimmed to its ink and shown at the same width. R2b ripples only the x, so the l stays an l.",
         "font": body, "size": 28, "color": MUTED, "x": pad, "y": 132},
    ]
    for col, (key, label) in enumerate([("old", "Current · Digital Shift"), ("new", "R2 · Ripple"), ("fix", "R2b · Ripple, steady l")]):
        x = pad + col * (cw + gap)
        ops.append({"type": "text", "name": f"Head {key}", "text": label, "font": bold, "size": 30, "color": INK,
                    "x": x, "y": head - 46})
        for row, tone in enumerate(("light", "dark")):
            y = head + 20 + row * (tile_h + gap)
            ops.append(rect(f"Tile {key} {tone}", x, y, cw, tile_h, PAPER if tone == "light" else INK, radius=24))
            path, (pw, ph) = parts[f"{key}-{tone}"]
            width = 520
            height = round(ph * width / pw)
            ops += [{"type": "add", "path": str(path), "name": f"{key} {tone}", "x": x, "y": y},
                    {"type": "resize", "target": f"{key} {tone}", "width": width, "height": height},
                    {"type": "move", "target": f"{key} {tone}", "x": x + (cw - width) / 2, "y": y + (tile_h - height) / 2}]
        # Small sizes: where a logo usually lives (nav bar, email signature, footer).
        y = head + 20 + 2 * (tile_h + gap)
        ops.append(rect(f"Small {key}", x, y, cw, small_h, PAPER, radius=24))
        path, (pw, ph) = parts[f"{key}-light"]
        left = x + 40
        for width in (260, 140, 80):
            height = round(ph * width / pw)
            name = f"{key} small {width}"
            ops += [{"type": "add", "path": str(path), "name": name, "x": left, "y": y},
                    {"type": "resize", "target": name, "width": width, "height": height},
                    {"type": "move", "target": name, "x": left, "y": y + 130 - height / 2},
                    {"type": "text", "name": f"{name} label", "text": f"{width} px", "font": body, "size": 20,
                     "color": MUTED, "x": left, "y": y + 230}]
            left += width + 50
    sheet.apply(ops)
    sheet.save(str(OUT / "compare-r2.vixl"), overwrite=True)
    sheet.export(str(OUT / "compare-r2.png"), overwrite=True)
    shutil.rmtree(WORK)  # the sheet embeds its own copies of the trimmed images
    print("built compare-r2")


if __name__ == "__main__":
    main()
