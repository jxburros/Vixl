"""Build the Vixl "Ripple" logo kit: every file in this folder except START-HERE.md.

Run from the repository root:

    python assets/brand/ripple/build.py

The logo is pure geometry (no font); only the overview sheet's labels download Inter from Google Fonts
(cached after the first run). Existing outputs are replaced. The MP4 files need ffmpeg.
"""

import math
import shutil
import sys
from pathlib import Path

from PIL import Image

from vixl import Project
from vixl.timeline import export_timeline
from vixl.typefaces import install_font

KIT = Path(__file__).resolve().parent

INK, BLUE, SKY, WHITE, BLACK = "#252B39", "#3575EE", "#6A9AFF", "#FFFFFF", "#000000"
MID, PALE = "#5B8FF5", "#A9C4FF"

# Colour treatments: letter ink, then the seven ripple bands from the waterline down. On dark the
# ripple fades towards the background instead of towards white.
TREATMENTS = {
    "color": (INK, [BLUE, BLUE, MID, MID, SKY, SKY, PALE]),
    "reverse": (WHITE, [SKY, SKY, "#5B87E6", "#5B87E6", "#4A6FC0", "#4A6FC0", "#3A5288"]),
    "black": (BLACK, [BLACK] * 7),
    "white": (WHITE, [WHITE] * 7),
}
# Sideways drift of each band, in units of the x's width / 190.
DRIFT = [0, 16, -14, 22, -18, 26, -10]
BANDS = 7
BAND_FILL = 0.55  # inked share of each band's slot; the rest is gap


# Geometry ----------------------------------------------------------------------------------------
def arm_for(stroke, width, run_height):
    """Horizontal width of a diagonal bar that is `stroke` thick across `width` x `run_height`."""
    arm = stroke
    for _ in range(20):
        arm = stroke * math.hypot(1, (width - arm) / run_height)
    return arm


def v_shape(width, h, arm):
    """The top V of an X that is `width` wide and `2h` tall, built from two straight bars."""
    s = (width - arm) / (2 * h)
    inner = (width - 2 * arm) / (2 * s)
    return [(0, 0), (arm, 0), (width / 2, inner), (width - arm, 0), (width, 0), (width - s * h, h), (s * h, h)]


def clip(points, y0, y1):
    """The part of a polygon between two horizontal lines."""
    def cut(pts, keep, edge):
        out = []
        for a, b in zip(pts, pts[1:] + pts[:1]):
            if keep(a):
                out.append(a)
            if keep(a) != keep(b):
                t = (edge - a[1]) / (b[1] - a[1])
                out.append((a[0] + t * (b[0] - a[0]), edge))
        return out
    pts = cut(points, lambda q: q[1] >= y0, y0)
    return cut(pts, lambda q: q[1] <= y1, y1) if pts else []


def box(x, y, w, h):
    return [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]


def moved(points, dx, dy):
    return [(px + dx, py + dy) for px, py in points]


def ripple(name, points, top, height, drift_unit, colours, still=False):
    """Cut a reflection (points hanging from y=`top`) into bands that drift sideways."""
    parts = []
    for i in range(BANDS):
        y0 = top + height * i / BANDS
        part = clip(points, y0, y0 + height / BANDS * BAND_FILL)
        if len(part) >= 3:
            dx = 0 if still else DRIFT[i] * drift_unit
            parts.append((f"{name} band {i + 1}", moved(part, dx, 0), colours[i]))
    return parts


def wordmark(u, ink, colours, still=False):
    """The wordmark at scale `u`, baseline at y=0: v and i, then an x and an l whose lower halves are
    their rippling reflection in a waterline at half the x-height."""
    stroke, xh, gap, space, vw, xw = 52 * u, 190 * u, 22 * u, 34 * u, 200 * u, 190 * u
    shapes, x = [], 0.0
    shapes.append(("v", moved(v_shape(vw, xh, arm_for(stroke, vw, 2 * xh)), x, -xh), ink))
    x += vw + space
    shapes += [("i stem", box(x, -xh, stroke, xh), ink), ("i dot", box(x, -xh - gap - stroke, stroke, stroke), ink)]
    x += stroke + space
    half = v_shape(xw, xh / 2, arm_for(stroke, xw, xh))
    shapes.append(("x", moved(half, x, -xh), ink))
    reflection = moved([(px, xh / 2 - py) for px, py in half], x, -xh / 2)
    shapes += ripple("x reflection", reflection, -xh / 2, xh / 2, u, colours, still)
    x += xw + space
    full = xh + gap + stroke
    shapes.append(("l", box(x, -full, stroke, full - xh / 2), ink))
    shapes += ripple("l reflection", box(x, -xh / 2, stroke, xh / 2), -xh / 2, xh / 2, u, colours, still)
    return shapes


def mark(u, ink, colours, bands=None):
    """The symbol: the x on its own, a v standing on its rippling reflection. Baseline at y=0."""
    size = 190 * u
    half = v_shape(size, size / 2, arm_for(52 * u, size, size))
    shapes = [("v", moved(half, 0, -size), ink)]
    reflection = moved([(px, size / 2 - py) for px, py in half], 0, -size / 2)
    if bands is None:
        return shapes + ripple("reflection", reflection, -size / 2, size / 2, u, colours)
    # Simplified small-size ripple: fewer, thicker bands with a small drift.
    count, fill, drift = bands
    for i in range(count):
        y0 = -size / 2 + size / 2 * i / count
        part = clip(reflection, y0, y0 + size / 2 / count * fill)
        if len(part) >= 3:
            shapes.append((f"reflection band {i + 1}", moved(part, drift[i] * u, 0), colours[min(2 * i, 6)]))
    return shapes


def extent(shapes):
    xs = [px for _, pts, _ in shapes for px, _ in pts]
    ys = [py for _, pts, _ in shapes for _, py in pts]
    return min(xs), min(ys), max(xs), max(ys)


def document(shapes, width, height, background="transparent", centre=True):
    """A document with the shapes centred (by their ink) on a width x height canvas."""
    x0, y0, x1, y1 = extent(shapes)
    dx, dy = (width - (x1 - x0)) / 2 - x0, (height - (y1 - y0)) / 2 - y0
    p = Project(width, height, background=background)
    ops = []
    for name, pts, fill in shapes:
        pts = moved(pts, dx, dy)
        left, top = min(px for px, _ in pts), min(py for _, py in pts)
        d = "M" + " L".join(f"{round(px - left, 2)} {round(py - top, 2)}" for px, py in pts) + " Z"
        ops.append({"type": "shape", "shape": "path", "name": name, "path": d, "x": round(left, 2), "y": round(top, 2),
                    "fill": fill})
    p.apply(ops)
    return p


# Outputs -----------------------------------------------------------------------------------------
def fresh(*folders):
    for folder in folders:
        path = KIT / folder
        if path.exists():
            shutil.rmtree(path)
        path.mkdir(parents=True)


def core(p, name, png_scales=(1, 2)):
    p.save(str(KIT / "Editable-Vixl" / f"{name}.vixl"), overwrite=True)
    p.export(str(KIT / "SVG" / f"{name}.svg"), overwrite=True)
    p.export(str(KIT / "PDF" / f"{name}.pdf"), overwrite=True)
    for scale in png_scales:
        suffix = "" if scale == 1 else f"@{scale}x"
        p.export(str(KIT / "PNG" / f"{name}{suffix}.png"), scale=scale, overwrite=True)


def icon(p, name, sizes, jpg=False, ico=False, small=None):
    """Master PNG, SVG and editable master, plus resized PNGs. Sizes under 128 px come from `small`
    (the simplified symbol) when given: seven ripple bands blur together below that."""
    p.save(str(KIT / "Editable-Vixl" / f"{name}.vixl"), overwrite=True)
    p.export(str(KIT / "SVG" / f"{name}.svg"), overwrite=True)
    master = KIT / "Icons" / f"{name}.png"
    p.export(str(master), overwrite=True)
    if small is not None:
        small_png = KIT / "Icons" / f"{name}-small-master.png"
        small.export(str(small_png), overwrite=True)
    with Image.open(master) as image:
        for size in sizes:
            source = Image.open(small_png) if small is not None and size < 128 else image
            source.resize((size, size), Image.LANCZOS).save(KIT / "Icons" / f"{name}-{size}.png")
    if small is not None:
        small_png.unlink()
    with Image.open(master) as image:
        if jpg:
            image.convert("RGB").save(KIT / "Icons" / f"{name}.jpg", quality=92)
        if ico:
            image.save(KIT / "Icons" / f"{name}.ico", sizes=[(s, s) for s in (16, 32, 48, 64, 128, 256)])


def animated(treatment, background):
    """The wordmark with its ripple swaying: every band below the waterline swings on its own phase,
    the deeper ones further, on a seamless 1.6 s loop."""
    ink, colours = TREATMENTS[treatment]
    p = document(wordmark(1.35, ink, colours, still=True), 1200, 500, background=background)
    ops = [{"type": "timeline-set", "duration": 1600, "loop_mode": "seamless"}]
    for layer in p.state["layers"]:
        if " band " in layer["name"]:
            i = int(layer["name"].rsplit(" ", 1)[1]) - 1
            if i:
                ops.append({"type": "keyframes", "target": layer["name"], "property": "translate-x",
                            "sample": {"fn": "sin", "period": 1600, "amplitude": round((4 + 3.4 * i) * 1.35, 2),
                                       "offset": 0, "phase": 0.37 * i, "samples": 32, "duration": 1600}})
    p.apply(ops)
    name = f"horizontal-{treatment}-animated"
    p.save(str(KIT / "Editable-Vixl" / f"{name}.vixl"), overwrite=True)
    export_timeline(p, str(KIT / "Animated" / f"{name}.gif"), fps=24, overwrite=True)
    export_timeline(p, str(KIT / "Animated" / f"{name}.webp"), fps=24, overwrite=True)
    if shutil.which("ffmpeg"):
        export_timeline(p, str(KIT / "Animated" / f"{name}.mp4"), fps=30, overwrite=True)
    else:
        print("ffmpeg not found: skipped", f"{name}.mp4", file=sys.stderr)


def overview():
    """A one-page reference sheet, assembled from the kit's own PNGs."""
    sheet = Project(2000, 1500, background="#F3F2EE")
    bold = install_font(sheet, "Inter Tight", 800)["name"]
    body = install_font(sheet, "Inter", 400)["name"]
    cards = [("Primary / light backgrounds", "horizontal-color", WHITE), ("Reversed / dark backgrounds", "horizontal-reverse", INK),
             ("One color / printing", "horizontal-black", WHITE), ("Symbol / light", "mark-color", WHITE),
             ("Symbol / dark", "mark-reverse", INK), ("App / social icon", None, WHITE)]
    ops = [{"type": "text", "name": "Title", "text": "Vixl / Ripple logo kit", "font": bold, "size": 64, "color": INK,
            "x": 60, "y": 48},
           {"type": "text", "name": "Subtitle", "text": "Wordmark • Symbol • Light & dark • One color • App & favicon • Animated",
            "font": body, "size": 30, "color": "#6B7080", "x": 60, "y": 132}]
    for i, (label, name, bg) in enumerate(cards):
        x, y = 60 + (i % 3) * 640, 210 + (i // 3) * 640
        ops.append({"type": "shape", "shape": "rounded-rectangle", "name": f"Card {i + 1}", "x": x, "y": y,
                    "width": 600, "height": 600, "radius": 24, "fill": bg})
        ops.append({"type": "text", "name": f"Label {i + 1}", "text": label, "font": body, "size": 24,
                    "color": "#AEB7CA" if bg == INK else "#6B7080", "x": x + 24, "y": y + 22})
        source = KIT / ("Icons/app-icon-dark.png" if name is None else f"PNG/{name}@2x.png")
        width = 420 if name is None else 540
        ops.append({"type": "add", "path": str(source), "name": f"Logo {i + 1}", "x": x, "y": y})
        with Image.open(source) as image:
            height = round(image.height * width / image.width)
        ops += [{"type": "resize", "target": f"Logo {i + 1}", "width": width, "height": height},
                {"type": "move", "target": f"Logo {i + 1}", "x": x + (600 - width) / 2, "y": y + (600 - height) / 2}]
    # Logos go under the labels so a dark card's label stays readable.
    sheet.apply(ops)
    for i in range(len(cards)):
        sheet.apply([{"type": "top", "target": f"Label {i + 1}"}])
    sheet.export(str(KIT / "00-kit-overview.png"), overwrite=True)


def main():
    fresh("SVG", "PNG", "PDF", "Icons", "Animated", "Editable-Vixl")
    for treatment, (ink, colours) in TREATMENTS.items():
        core(document(wordmark(1.35, ink, colours), 1200, 500), f"horizontal-{treatment}")
        core(document(mark(2.5, ink, colours), 800, 800), f"mark-{treatment}")
    # Small sizes: three thick bands with a small drift, so the ripple survives at 16-96 px.
    simple = (3, 0.62, [0, 7, -6])
    icon(document(mark(2.9, *TREATMENTS["reverse"]), 1024, 1024, background=INK), "app-icon-dark",
         (48, 96, 180, 192, 256, 512), jpg=True,
         small=document(mark(3.4, *TREATMENTS["reverse"], bands=simple), 1024, 1024, background=INK))
    icon(document(mark(2.5, *TREATMENTS["color"]), 1024, 1024, background=WHITE), "social-avatar-light",
         (48, 96, 180, 192, 256, 512), jpg=True,
         small=document(mark(2.9, *TREATMENTS["color"], bands=simple), 1024, 1024, background=WHITE))
    icon(document(mark(1.95, *TREATMENTS["reverse"], bands=simple), 512, 512), "favicon-dark",
         (16, 32, 48, 64, 128, 256), ico=True)
    icon(document(mark(1.95, *TREATMENTS["color"], bands=simple), 512, 512), "favicon-light",
         (16, 32, 48, 64, 128, 256), ico=True)
    animated("color", WHITE)
    animated("reverse", INK)
    overview()
    print("built", sum(1 for path in KIT.rglob("*") if path.is_file()), "files in", KIT)


if __name__ == "__main__":
    main()
