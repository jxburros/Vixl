"""The parity cases: the same content as Vixl operations and as HTML/CSS/SVG for Chromium.

Each case builds a ``Project``, renders matching markup (using the same font file through
@font-face, the same sizes and colours) and measures both. Where geometry has a closed form the case
also measures both against an exact supersampled reference (``ideal``), which tells a Vixl defect from
a browser's own choice."""

from dataclasses import dataclass, field
import base64
import io
import math
from pathlib import Path
from typing import Callable

import numpy as np
from PIL import Image

from . import ideal, metrics

import vixl
from vixl import Project
from vixl.assets import add_image

FONT = Path(vixl.__file__).parent / "data" / "NotoSans-Regular.ttf"
FONTS = (("Parity", FONT),)
CASES = []


@dataclass
class Case:
    name: str
    category: str
    title: str
    width: int
    height: int
    background: str
    build: Callable  # () -> Project
    html: Callable  # (project) -> body markup
    analyze: Callable  # (Context) -> metrics dict
    css: str = ""
    note: str = ""
    reference: Callable = None  # (project) -> ideal RGB float array, shown in the report when given
    tags: tuple = field(default_factory=tuple)


@dataclass
class Context:
    case: Case
    project: object
    vixl: Image.Image
    chrome: Image.Image
    measured: dict


def case(**kwargs):
    CASES.append(Case(**kwargs))


def hex_rgb(value):
    value = value.lstrip("#")
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))


def layer(project, name):
    from vixl.render import resolved_layers

    return next(item for item in resolved_layers(project) if item.get("name") == name)


def glyphs(project, name):
    """Vixl's glyph pen positions on the canvas: ``[(char index, x, baseline y, line, text)]``, one per
    cluster (the first glyph of each), plus the layer."""
    from vixl import richtext
    from vixl.text import placed_glyphs

    item = layer(project, name)
    if richtext.active(item):
        found = [(g.text, g.x, g.y, g.line) for g in richtext.fitted(project, item).glyphs]
    else:
        found = [(g[5], g[2], g[3], g[6]) for g in placed_glyphs(project, item)]
    # Map each cluster to its index in the layer text; wrapping drops the spaces at line breaks.
    source, result, index = item["text"], [], 0
    for text, x, y, line in found:
        if text:
            at = source.find(text, index)
            at = index if at < 0 else at
            result.append((at, item["x"] + x, item["y"] + y, line, text))
            index = at + len(text)
    return result, item


def text_markup(name, text, size, color, x, baseline, tracking=0, width=None, line_height=None, extra=""):
    style = f"left:{x}px;font:{size}px Parity;color:{color};"
    if tracking:
        style += f"letter-spacing:{tracking}px;"
    if width is not None:
        style += f"width:{width}px;white-space:normal;overflow-wrap:break-word;"
    if line_height is not None:
        style += f"line-height:{line_height}px;"
    return (f"<div class='t' data-measure='{name}' data-baseline='{baseline}' "
            f"style='{style}{extra}'>{text}</div>")


def data_url(image):
    buffer = io.BytesIO()
    image.save(buffer, "PNG")
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode()


# ---- text ----------------------------------------------------------------------------------------

def text_metrics(ctx, name="t", color="#111111"):
    project, bg = ctx.project, hex_rgb(ctx.case.background)
    ink = hex_rgb(color)
    cv, cc = metrics.coverage(ctx.vixl, bg, ink), metrics.coverage(ctx.chrome, bg, ink)
    placed, item = glyphs(project, name)
    out = {"diff": metrics.diff(ctx.vixl, ctx.chrome)}
    chars = {c["i"]: c for c in ctx.measured.get(name, [])}
    if chars and placed:
        # Pen positions within each line, Chromium's layout minus Vixl's (origin: the line's first glyph).
        deltas, origins = [], {}
        for i, x, _, line, _ in placed:
            if i in chars:
                origin = origins.setdefault(line, chars[i]["x"] - x)
                deltas.append(chars[i]["x"] - origin - x)
        out["layout_dx"] = {"max": round(max(abs(d) for d in deltas), 3),
                            "mean": round(float(np.mean(np.abs(deltas))), 3),
                            "end": round(deltas[-1], 3)}
    bv, bc = metrics.bbox(cv), metrics.bbox(cc)
    out["ink_box"] = {"vixl": bv, "chrome": bc,
                      "delta": None if not (bv and bc) else [round(c - v, 3) for v, c in zip(bv, bc)]}
    wv, wc = metrics.weight(cv), metrics.weight(cc)
    out["ink_weight_ratio"] = round(wv / wc, 4) if wc else None
    out["sharpness"] = {"vixl": metrics.sharpness(cv), "chrome": metrics.sharpness(cc)}
    # Per-glyph horizontal position of the drawn ink, Chromium relative to Vixl: a spread well above a
    # tenth of a pixel means one renderer moves glyphs off their layout positions (whole-pixel snapping).
    lines = {}
    for i, x, y, line, text in placed:
        lines.setdefault(line, []).append((x, y, text))
    shifts = []
    size = item.get("size", 16)
    for points in lines.values():
        for (x, y, text), nxt in zip(points, points[1:] + [None]):
            right = nxt[0] if nxt else x + size * 0.6
            if not text.strip() or right - x < 4:
                continue
            window = (math.floor(x), math.floor(y - size * 0.8), math.ceil(right), math.ceil(y + size * 0.25))
            if cv[window[1]:window[3], window[0]:window[2]].sum() < 2:
                continue
            s = metrics.local_shift(cv, cc, window, search=2)
            if s is not None:
                shifts.append(s)
    if shifts:
        relative = np.array(shifts) - np.median(shifts)
        out["glyph_shift"] = {"median": round(float(np.median(shifts)), 3),
                              "spread": round(float(np.percentile(np.abs(relative), 90)), 3),
                              "rms": round(float(np.sqrt((relative**2).mean())), 3), "values": shifts}
    return out


def text_case(name, text, size, *, color="#111111", background="#ffffff", width=360, height=None, tracking=0,
              title=None, note="", tags=()):
    height = height or int(size * 1.6) + 16
    baseline = round(8 + size * 1.07)

    def build():
        p = Project(width, height, background)
        op = {"type": "text", "text": text, "name": "t", "size": size, "x": 8, "y": 0, "color": color,
              "font": str(FONT)}
        if tracking:
            op["tracking"] = tracking
        p.apply([op])
        # Put the first baseline on a whole pixel with a whole-pixel layer position: move the layer by
        # the whole-pixel part only, so no placement resampling enters the comparison.
        first = glyphs(p, "t")[0][0]
        p.apply([{"type": "move", "target": "t", "x": 8, "y": baseline - math.floor(first[2])}])
        return p

    def html(project):
        placed, _ = glyphs(project, "t")
        return text_markup("t", text, size, color, placed[0][1], placed[0][2], tracking)

    case(name=name, category="text", title=title or f"{text[:24]!r} at {size}px", width=width, height=height,
         background=background, build=build, html=html, analyze=lambda ctx: text_metrics(ctx, color=color),
         note=note, tags=tags)


PANGRAM = "The quick brown fox jumps over the lazy dog. AVA Wo Ty 0123"
text_case("text_body_12", PANGRAM, 12, width=380, tags=("body",))
text_case("text_body_14", PANGRAM, 14, width=440, tags=("body",))
text_case("text_body_16", PANGRAM, 16, width=500, tags=("body",))
text_case("text_small_light_on_dark", "Light text on a dark panel, 12px", 12, color="#f2f2f2",
          background="#1d2733", width=260, tags=("gamma",),
          note="Gamma: light-on-dark small text shows a rasterizer's contrast and gamma handling.")
text_case("text_small_gray", "Secondary gray caption text 11px", 11, color="#767676", width=240, tags=("gamma",))
text_case("text_display_64_kerning", "AVATAR Wolf Type", 64, width=640, tags=("kerning",),
          note="Kerning pairs AV, VA, AT, TA, Wo, Ty.")
text_case("text_display_96_ligatures", "office fifty", 96, width=620, tags=("ligatures",),
          note="ffi and fi ligatures (NotoSans liga).")
text_case("text_display_120", "Hamburg", 120, width=520, tags=("display",))
text_case("text_tracking_28", "TRACKED CAPS", 28, tracking=6, width=420, tags=("tracking",),
          note="tracking 6 px (CSS letter-spacing 6px).")


def paragraph_build(width, size, text, box):
    def build():
        p = Project(width, 220, "#ffffff")
        p.apply([
            {"type": "text", "text": text, "name": "t", "size": size, "x": 10, "y": 10, "color": "#222222",
             "font": str(FONT)},
            {"type": "text-layout", "target": "t", "width": box, "height": 200},
        ])
        return p
    return build


PARAGRAPH = ("Typography is the craft of arranging type to make written language legible, readable and "
             "appealing when displayed. Kerning, tracking and leading all matter.")


def paragraph_html(size, box):
    def html(project):
        placed, _ = glyphs(project, "t")
        ys = sorted({round(y, 3) for _, _, y, _, _ in placed})
        pitch = ys[1] - ys[0] if len(ys) > 1 else size * 1.4
        return text_markup("t", PARAGRAPH, size, "#222222", 10, placed[0][2], width=box, line_height=pitch)
    return html


def paragraph_metrics(ctx):
    out = text_metrics(ctx, color="#222222")
    placed, _ = glyphs(ctx.project, "t")
    vixl_lines = {}
    for i, _, y, line, _ in placed:
        vixl_lines.setdefault(line, []).append(i)
    chrome_lines = {}
    for c in ctx.measured.get("t", []):
        if c["c"].strip():
            chrome_lines.setdefault(round(c["y"]), []).append(c["i"])
    starts_v = [min(v) for _, v in sorted(vixl_lines.items())]
    starts_c = [min(v) for _, v in sorted(chrome_lines.items())]
    def words(starts):
        return [PARAGRAPH[s:e].strip() for s, e in zip(starts, starts[1:] + [len(PARAGRAPH)])]

    out["lines"] = {"vixl": len(starts_v), "chrome": len(starts_c), "same_breaks": starts_v == starts_c,
                    "vixl_first_words": [w.split(" ")[0] for w in words(starts_v)],
                    "chrome_first_words": [w.split(" ")[0] for w in words(starts_c)]}
    ys = sorted({round(y, 3) for _, _, y, _, _ in placed})
    out["line_pitch"] = round(ys[1] - ys[0], 3) if len(ys) > 1 else None
    return out


for size, box in ((14, 300), (16, 340)):
    case(name=f"text_paragraph_{size}", category="text", title=f"Wrapped paragraph {size}px in {box}px",
         width=380, height=220, background="#ffffff", build=paragraph_build(380, size, PARAGRAPH, box),
         html=paragraph_html(size, box), analyze=paragraph_metrics, tags=("paragraph",),
         note="Line breaks and line pitch (CSS line-height set to Vixl's pitch).")


def baseline_case():
    """Text placed with baseline_y: the layer lands on a fractional y."""
    def build():
        p = Project(380, 80, "#ffffff")
        p.apply([{"type": "text", "text": "Baseline aligned 15px text", "name": "t", "size": 15, "x": 8,
                  "baseline_y": 40, "color": "#111111", "font": str(FONT)}])
        return p

    def html(project):
        placed, _ = glyphs(project, "t")
        return text_markup("t", "Baseline aligned 15px text", 15, "#111111", placed[0][1], 40)

    def analyze(ctx):
        out = text_metrics(ctx)
        item = layer(ctx.project, "t")
        out["layer_y"] = item["y"]
        upright = Project(380, 80, "#ffffff")
        upright.apply([{"type": "text", "text": "Baseline aligned 15px text", "name": "t", "size": 15, "x": 8,
                        "y": math.floor(item["y"]), "color": "#111111", "font": str(FONT)}])
        whole = metrics.sharpness(metrics.coverage(upright.render(), (255, 255, 255), (17, 17, 17)))
        out["sharpness_vs_whole_pixel_y"] = round(out["sharpness"]["vixl"] / whole, 3) if whole else None
        return out

    case(name="text_baseline_y_fractional", category="text", title="baseline_y on a fractional layer y",
         width=380, height=80, background="#ffffff", build=build, html=html, analyze=analyze,
         tags=("subpixel",), note="baseline_y=40 puts the layer at a fractional y.")


baseline_case()


# ---- shapes and strokes --------------------------------------------------------------------------

def shape_metrics(ctx, inside, fill, partial_rows=()):
    bg = hex_rgb(ctx.case.background)
    w, h = ctx.case.width, ctx.case.height
    exact = ideal.supersample(inside, w, h)
    cv, cc = metrics.coverage(ctx.vixl, bg, fill), metrics.coverage(ctx.chrome, bg, fill)
    edge = (exact > 0.001) & (exact < 0.999)
    grown = edge.copy()
    for axis in (0, 1):
        grown |= np.roll(edge, 1, axis) | np.roll(edge, -1, axis)
    out = {"diff": metrics.diff(ctx.vixl, ctx.chrome),
           "vs_ideal": {"vixl": metrics.error(cv, exact), "chrome": metrics.error(cc, exact)},
           "edge_vs_ideal": {"vixl": metrics.error(cv, exact, grown), "chrome": metrics.error(cc, exact, grown)},
           "area": {"ideal": round(float(exact.sum()), 2), "vixl": round(float(cv.sum()), 2),
                    "chrome": round(float(cc.sum()), 2)}}
    for row in partial_rows:
        out[f"row_{row}"] = {"ideal": [round(v, 3) for v in exact[row]], "vixl": [round(v, 3) for v in cv[row]],
                             "chrome": [round(v, 3) for v in cc[row]]}
    return out


def shape_case(name, title, width, height, ops, svg, inside, fill="#1d3557", background="#ffffff", note="", tags=()):
    def build():
        p = Project(width, height, background)
        p.apply(ops)
        return p

    markup = (f"<svg class='a' style='left:0;top:0' width='{width}' height='{height}' "
              f"xmlns='http://www.w3.org/2000/svg'>{svg}</svg>")
    case(name=name, category="shapes", title=title, width=width, height=height, background=background,
         build=build, html=lambda project: markup, analyze=lambda ctx: shape_metrics(ctx, inside, hex_rgb(fill)),
         reference=lambda project: ideal_image(inside, width, height, background, fill), note=note, tags=tags)


def ideal_image(inside, width, height, background, fill):
    c = ideal.supersample(inside, width, height)[..., None]
    bg, fg = np.array(hex_rgb(background), float) / 255, np.array(hex_rgb(fill), float) / 255
    return bg * (1 - c) + fg * c


shape_case(
    "shape_circle_edges", "Circles 61 px and 9 px: edge AA", 120, 90,
    [{"type": "shape", "shape": "ellipse", "name": "big", "x": 10, "y": 10, "width": 61, "height": 61,
      "fill": "#1d3557"},
     {"type": "shape", "shape": "ellipse", "name": "small", "x": 90, "y": 20, "width": 9, "height": 9,
      "fill": "#1d3557"}],
    "<ellipse cx='40.5' cy='40.5' rx='30.5' ry='30.5' fill='#1d3557'/>"
    "<ellipse cx='94.5' cy='24.5' rx='4.5' ry='4.5' fill='#1d3557'/>",
    ideal.union(ideal.ellipse(40.5, 40.5, 30.5, 30.5), ideal.ellipse(94.5, 24.5, 4.5, 4.5)),
    tags=("aa",))

shape_case(
    "shape_rounded_rect", "Rounded rectangle r=14 and a capsule", 220, 90,
    [{"type": "shape", "shape": "rounded-rectangle", "name": "card", "x": 10, "y": 10, "width": 100,
      "height": 70, "radius": 14, "fill": "#1d3557"},
     {"type": "shape", "shape": "capsule", "name": "pill", "x": 125, "y": 30, "width": 85, "height": 27,
      "fill": "#1d3557"}],
    "<rect x='10' y='10' width='100' height='70' rx='14' fill='#1d3557'/>"
    "<rect x='125' y='30' width='85' height='27' rx='13.5' fill='#1d3557'/>",
    ideal.union(ideal.rounded_rect(10, 10, 110, 80, 14), ideal.rounded_rect(125, 30, 210, 57, 13.5)),
    tags=("aa",))

PENTAGON = [(25, 0), (50, 20), (40, 50), (10, 50), (0, 20)]
shape_case(
    "shape_fractional_position", "Ellipse, square and pentagon path at fractional positions", 180, 80,
    [{"type": "shape", "shape": "ellipse", "name": "dot", "x": 10.4, "y": 20.3, "width": 40, "height": 40,
      "fill": "#1d3557"},
     {"type": "shape", "shape": "rectangle", "name": "sq", "x": 70.6, "y": 20.3, "width": 30, "height": 30,
      "fill": "#1d3557"},
     {"type": "shape", "shape": "path", "name": "pent", "x": 115.6, "y": 15.7, "width": 50, "height": 50,
      "path": "M" + " L".join(f"{x} {y}" for x, y in PENTAGON) + " Z", "fill": "#1d3557"}],
    "<ellipse cx='30.4' cy='40.3' rx='20' ry='20' fill='#1d3557'/>"
    "<rect x='70.6' y='20.3' width='30' height='30' fill='#1d3557'/>"
    "<path transform='translate(115.6 15.7)' d='M" + " L".join(f"{x} {y}" for x, y in PENTAGON) + " Z' fill='#1d3557'/>",
    ideal.union(ideal.ellipse(30.4, 40.3, 20, 20), ideal.rounded_rect(70.6, 20.3, 100.6, 50.3, 0),
                ideal.polygon([(x + 115.6, y + 15.7) for x, y in PENTAGON])),
    tags=("subpixel",), note="Layers at fractional positions: drawn there (ellipse, path) or resampled (rectangle).")

HAIRLINES = [  # (ax, ay, bx, by, width) in canvas pixels; the layer box is 10..190 x 10..90
    (20, 20, 180, 20, 1), (20, 30.5, 180, 30.5, 1), (20, 40.5, 180, 40.5, 0.5), (20, 50, 180, 50, 2),
    (20, 60, 180, 85, 1), (20, 85, 180, 62, 1.5),
]


def hairline_ops():
    # The trailing moves pin the path's box to the layer's, so path coordinates stay canvas offsets.
    return [{"type": "shape", "shape": "path", "name": f"line{index}", "x": 10, "y": 10, "width": 180, "height": 80,
             "path": f"M{ax - 10} {ay - 10} L{bx - 10} {by - 10} M0 0 M180 80", "fill": "transparent",
             "stroke": "#000000", "stroke_width": w}
            for index, (ax, ay, bx, by, w) in enumerate(HAIRLINES)]


shape_case(
    "stroke_hairlines", "Hairlines 0.5-2 px, on and off the pixel grid, and shallow diagonals", 200, 100,
    hairline_ops(),
    "".join(f"<path d='M{ax} {ay} L{bx} {by}' stroke='#000000' stroke-width='{w}' fill='none'/>"
            for ax, ay, bx, by, w in HAIRLINES),
    ideal.union(*(ideal.segment(ax, ay, bx, by, w) for ax, ay, bx, by, w in HAIRLINES)),
    fill="#000000", tags=("strokes",),
    note="Path strokes; non-integer widths are passed as numbers.")

shape_case(
    "shape_rotated_rect", "Rectangle rotated 30 degrees", 140, 120,
    [{"type": "shape", "shape": "rectangle", "name": "bar", "x": 30, "y": 40, "width": 80, "height": 40,
      "fill": "#1d3557"},
     {"type": "rotate", "target": "bar", "value": 30}],
    "<rect x='30' y='40' width='80' height='40' fill='#1d3557' transform='rotate(30 70 60)'/>",
    ideal.rotated(ideal.rounded_rect(30, 40, 110, 80, 0), 70, 60, 30),
    tags=("rotation",))


def rotated_text_case():
    text, size = "Rotated text", 28

    def build():
        p = Project(260, 160, "#ffffff")
        p.apply([{"type": "text", "text": text, "name": "t", "size": size, "x": 40, "y": 60, "color": "#111111",
                  "font": str(FONT)},
                 {"type": "rotate", "target": "t", "value": -20}])
        return p

    def html(project):
        from vixl.render import resolve_layout

        item = layer(project, "t")
        bx, by, bw, bh = resolve_layout(project)[item["id"]]
        cx, cy = bx + bw / 2, by + bh / 2
        # The upright layer is centred on the rotated layer's box; glyph positions are box-relative.
        upright = Project(260, 160, "#ffffff")
        upright.apply([{"type": "text", "text": text, "name": "t", "size": size, "x": 0, "y": 0,
                        "color": "#111111", "font": str(FONT)}])
        placed, _ = glyphs(upright, "t")
        x0, y0 = cx - item["width"] / 2, cy - item["height"] / 2
        return (f"<div class='a' style='left:0;top:0;width:260px;height:160px;transform-origin:{cx}px {cy}px;"
                f"' data-transform='rotate(-20deg)'>"
                + text_markup("t", text, size, "#111111", x0 + placed[0][1], y0 + placed[0][2]) + "</div>")

    def analyze(ctx):
        bg, ink = (255, 255, 255), (17, 17, 17)
        cv, cc = metrics.coverage(ctx.vixl, bg, ink), metrics.coverage(ctx.chrome, bg, ink)
        return {"diff": metrics.diff(ctx.vixl, ctx.chrome),
                "sharpness": {"vixl": metrics.sharpness(cv), "chrome": metrics.sharpness(cc)},
                "ink_weight_ratio": round(metrics.weight(cv) / max(metrics.weight(cc), 1e-9), 4),
                "ink_box": {"vixl": metrics.bbox(cv), "chrome": metrics.bbox(cc)}}

    case(name="text_rotated", category="text", title="28px text rotated -20 degrees", width=260, height=160,
         background="#ffffff", build=build, html=html, analyze=analyze, tags=("rotation",),
         note="Vixl rasterizes upright and resamples; Chromium rotates the outlines.")


rotated_text_case()


# ---- gradients -----------------------------------------------------------------------------------

def gradient_case(name, title, start, end, width=512, height=40):
    def build():
        p = Project(width, height, "#000000")
        p.apply([{"type": "gradient", "name": "g", "x": 0, "y": 0, "width": width, "height": height,
                  "start": start, "end": end, "direction": "horizontal"}])
        return p

    def analyze(ctx):
        exact = ideal.linear_ramp(width, hex_rgb(start), hex_rgb(end))
        out = {"diff": metrics.diff(ctx.vixl, ctx.chrome)}
        for label, image in (("vixl", ctx.vixl), ("chrome", ctx.chrome)):
            a = metrics.rgb(image)
            row = a[height // 2]
            channel = int(np.argmax(np.abs(np.array(hex_rgb(end)) - np.array(hex_rgb(start)))))
            out[label] = {
                "vs_ideal": metrics.error(row, exact),
                "levels": metrics.levels(row[:, channel]),
                "banding": metrics.banding(a[:, :, channel]),
                "row_noise": round(float(np.abs(np.diff(a[:, :, channel], axis=0)).mean() * 255), 3),
            }
        return out

    markup = (f"<div class='a' style='left:0;top:0;width:{width}px;height:{height}px;"
              f"background:linear-gradient(to right,{start},{end})'></div>")
    def reference(project):
        return np.broadcast_to(ideal.linear_ramp(width, hex_rgb(start), hex_rgb(end))[None], (height, width, 3))

    case(name=name, category="gradients", title=title, width=width, height=height, background="#000000",
         build=build, html=lambda project: markup, analyze=analyze, reference=reference, tags=("banding",))


gradient_case("gradient_full_range", "Black to white over 512 px", "#000000", "#ffffff")
gradient_case("gradient_subtle_dark", "Subtle dark ramp #20242a to #2c3138 over 600 px (banding)",
              "#20242a", "#2c3138", width=600)
gradient_case("gradient_saturated", "Red to blue over 512 px (sRGB interpolation)", "#ff0000", "#0000ff")


def radial_case():
    def build():
        p = Project(200, 200, "#000000")
        p.apply([{"type": "gradient", "name": "g", "x": 0, "y": 0, "width": 200, "height": 200,
                  "start": "#ffffff", "end": "#1d3557", "direction": "radial"}])
        return p

    markup = ("<div class='a' style='left:0;top:0;width:200px;height:200px;"
              "background:radial-gradient(closest-side,#ffffff,#1d3557)'></div>")

    def analyze(ctx):
        return {"diff": metrics.diff(ctx.vixl, ctx.chrome),
                "center_row": {"vixl": [int(v) for v in np.asarray(ctx.vixl.convert('L'))[100, ::20]],
                               "chrome": [int(v) for v in np.asarray(ctx.chrome.convert('L'))[100, ::20]]}}

    case(name="gradient_radial", category="gradients", title="Radial white to navy", width=200, height=200,
         background="#000000", build=build, html=lambda project: markup, analyze=analyze, tags=("banding",))


radial_case()


# ---- opacity and blending ------------------------------------------------------------------------

BLEND_MODES = ["normal", "multiply", "screen", "overlay", "darken", "lighten", "difference", "add"]
CSS_BLEND = {"add": "plus-lighter"}
BASE, TOP, CANVAS = "#3a86c8", "#f4a259", "#e9e4d8"


def blend_formula(mode, cb, cs):
    if mode == "normal":
        return cs
    if mode == "multiply":
        return cb * cs
    if mode == "screen":
        return cb + cs - cb * cs
    if mode == "overlay":
        return np.where(cb <= 0.5, 2 * cb * cs, 1 - 2 * (1 - cb) * (1 - cs))
    if mode == "darken":
        return np.minimum(cb, cs)
    if mode == "lighten":
        return np.maximum(cb, cs)
    if mode == "difference":
        return np.abs(cb - cs)
    return np.minimum(1, cb + cs)


def blend_case():
    cell = 60

    def build():
        p = Project(cell * 4, cell * 4, CANVAS)
        ops = []
        for i, mode in enumerate(BLEND_MODES):
            x, y = (i % 4) * cell, (i // 4) * 2 * cell
            ops += [{"type": "shape", "shape": "rectangle", "name": f"b{i}", "x": x + 5, "y": y + 5, "width": 50,
                     "height": 110, "fill": BASE},
                    {"type": "shape", "shape": "rectangle", "name": f"t{i}", "x": x + 15, "y": y + 15, "width": 40,
                     "height": 40, "fill": TOP},
                    {"type": "shape", "shape": "rectangle", "name": f"o{i}", "x": x + 15, "y": y + 65, "width": 40,
                     "height": 40, "fill": TOP, "opacity": 0.5}]
            if mode != "normal":
                ops += [{"type": "blend", "target": f"t{i}", "value": mode},
                        {"type": "blend", "target": f"o{i}", "value": mode}]
        p.apply(ops)
        return p

    def html(project):
        parts = []
        for i, mode in enumerate(BLEND_MODES):
            x, y = (i % 4) * cell, (i // 4) * 2 * cell
            css = CSS_BLEND.get(mode, mode)
            parts.append(
                f"<div class='a' style='left:{x + 5}px;top:{y + 5}px;width:50px;height:110px;background:{BASE}'></div>"
                f"<div class='a' style='left:{x + 15}px;top:{y + 15}px;width:40px;height:40px;background:{TOP};"
                f"mix-blend-mode:{css}'></div>"
                f"<div class='a' style='left:{x + 15}px;top:{y + 65}px;width:40px;height:40px;background:{TOP};"
                f"opacity:.5;mix-blend-mode:{css}'></div>")
        return "".join(parts)

    def analyze(ctx):
        cb, cs = np.array(hex_rgb(BASE)) / 255, np.array(hex_rgb(TOP)) / 255
        out = {"diff": metrics.diff(ctx.vixl, ctx.chrome)}
        worst = {"vixl": 0, "chrome": 0}
        for i, mode in enumerate(BLEND_MODES):
            x, y = (i % 4) * cell, (i // 4) * 2 * cell
            full = blend_formula(mode, cb, cs)
            half = cb + 0.5 * (full - cb)
            entry = {}
            for label, image in (("vixl", ctx.vixl), ("chrome", ctx.chrome)):
                a = np.asarray(image.convert("RGB"), int)
                got_full, got_half = a[y + 35, x + 35], a[y + 85, x + 35]
                err = max(int(np.abs(got_full - np.round(full * 255)).max()),
                          int(np.abs(got_half - np.round(half * 255)).max()))
                entry[label] = {"opaque": got_full.tolist(), "half": got_half.tolist(), "max_error": err}
                worst[label] = max(worst[label], err)
            entry["ideal"] = {"opaque": np.round(full * 255).astype(int).tolist(),
                              "half": np.round(half * 255).astype(int).tolist()}
            out[mode] = entry
        out["max_error"] = worst
        return out

    case(name="blend_and_opacity", category="compositing", title="Blend modes at 100% and 50% opacity",
         width=cell * 4, height=cell * 4, background=CANVAS, build=build, html=html, analyze=analyze,
         tags=("blend",), note="add is compared with CSS plus-lighter.")


blend_case()


# ---- blur and shadow -----------------------------------------------------------------------------

def blur_case(sigma):
    def build():
        p = Project(160, 120, "#ffffff")
        p.apply([{"type": "shape", "shape": "rectangle", "name": "r", "x": 50, "y": 30, "width": 60, "height": 60,
                  "fill": "#1d3557"},
                 {"type": "effect", "target": "r", "name": "blur", "amount": sigma}])
        return p

    markup = (f"<svg class='a' style='left:0;top:0' width='160' height='120' xmlns='http://www.w3.org/2000/svg'>"
              f"<filter id='f' x='-50%' y='-50%' width='200%' height='200%'><feGaussianBlur stdDeviation='{sigma}'/>"
              f"</filter><rect x='50' y='30' width='60' height='60' fill='#1d3557' filter='url(#f)'/></svg>")

    def exact():
        return ideal.gaussian(ideal.supersample(ideal.rounded_rect(50, 30, 110, 90, 0), 160, 120, 4), sigma)

    def analyze(ctx):
        truth = exact()
        out = {"diff": metrics.diff(ctx.vixl, ctx.chrome), "sigma": sigma}
        for label, image in (("vixl", ctx.vixl), ("chrome", ctx.chrome)):
            cov = metrics.coverage(image, (255, 255, 255), hex_rgb("#1d3557"))
            out[label] = {"vs_ideal": metrics.error(cov, truth),
                          "sigma_estimate": metrics.sigma_from_rise(metrics.rise_10_90(cov[60, 20:80]))}
        out["ideal_sigma_estimate"] = metrics.sigma_from_rise(metrics.rise_10_90(truth[60, 20:80]))
        return out

    case(name=f"blur_sigma_{sigma}", category="effects", title=f"Gaussian blur, standard deviation {sigma}",
         width=160, height=120, background="#ffffff", build=build, html=lambda project: markup, analyze=analyze,
         reference=lambda project: ideal_from_coverage(exact(), "#ffffff", "#1d3557"), tags=("blur",))


def ideal_from_coverage(cov, background, fill):
    c = np.asarray(cov)[..., None]
    bg, fg = np.array(hex_rgb(background), float) / 255, np.array(hex_rgb(fill), float) / 255
    return bg * (1 - c) + fg * c


blur_case(2)
blur_case(6)


def shadow_case():
    def build():
        p = Project(180, 140, "#f4efe6")
        p.apply([{"type": "shape", "shape": "rectangle", "name": "card", "x": 40, "y": 30, "width": 80, "height": 60,
                  "fill": "#2a9d8f"},
                 {"type": "layer-style", "target": "card", "name": "drop-shadow",
                  "settings": {"color": "#000000", "dx": 6, "dy": 8, "blur": 6, "opacity": 0.6}}])
        return p

    markup = ("<svg class='a' style='left:0;top:0' width='180' height='140' xmlns='http://www.w3.org/2000/svg'>"
              "<filter id='s' x='-50%' y='-50%' width='200%' height='200%'><feDropShadow dx='6' dy='8' "
              "stdDeviation='6' flood-color='#000' flood-opacity='0.6'/></filter>"
              "<rect x='40' y='30' width='80' height='60' fill='#2a9d8f' filter='url(#s)'/></svg>")

    def exact(sigma=6):
        shape = ideal.supersample(ideal.rounded_rect(40, 30, 120, 90, 0), 180, 140, 4)
        shadow = ideal.gaussian(ideal.supersample(ideal.rounded_rect(46, 38, 126, 98, 0), 180, 140, 4), sigma) * 0.6
        bg, fill = np.array(hex_rgb("#f4efe6")) / 255, np.array(hex_rgb("#2a9d8f")) / 255
        under = bg * (1 - shadow[..., None])
        return under * (1 - shape[..., None]) + fill * shape[..., None]

    def analyze(ctx):
        truth = exact()
        candidates = {float(sigma): exact(sigma) for sigma in np.arange(4.0, 8.01, 0.25)}
        out = {"diff": metrics.diff(ctx.vixl, ctx.chrome)}
        for label, image in (("vixl", ctx.vixl), ("chrome", ctx.chrome)):
            a = metrics.rgb(image)
            d = (a - truth) * 255
            # The shadow's spread: the Gaussian whose exact shadow fits this render best.
            fit = min(candidates, key=lambda sigma: float(((a - candidates[sigma]) ** 2).mean()))
            out[label] = {"rms_vs_ideal": round(float(np.sqrt((d**2).mean())), 3),
                          "max_vs_ideal": round(float(np.abs(d).max()), 2), "fitted_sigma": fit}
        return out

    case(name="drop_shadow", category="effects", title="Drop shadow dx 6, dy 8, blur 6, opacity 0.6",
         width=180, height=140, background="#f4efe6", build=build, html=lambda project: markup, analyze=analyze,
         reference=lambda project: exact(), tags=("blur",),
         note="Compared with SVG feDropShadow stdDeviation=6, the export's mapping of blur.")


shadow_case()


# ---- image resampling ----------------------------------------------------------------------------

def photo(size=512):
    """A deterministic photo-like test image: smooth colour fields, fine texture, a zone plate whose
    frequency rises past the output's Nyquist limit, and hard-edged shapes."""
    y, x = np.mgrid[0:size, 0:size].astype(float)
    r = np.hypot(x - size * 0.72, y - size * 0.72)
    zone = 0.5 + 0.5 * np.cos(math.pi * r * r / (size * 0.9))
    rng = np.random.default_rng(7)
    texture = rng.normal(0, 0.06, (size, size))
    base = np.stack([0.25 + 0.5 * x / size, 0.35 + 0.4 * y / size, 0.8 - 0.5 * x / size], axis=-1)
    a = base + texture[..., None]
    plate = r < size * 0.27
    a[plate] = zone[plate][:, None] * np.array([0.95, 0.9, 0.85])
    a[(np.abs(x - size * 0.25) < size * 0.12) & (np.abs(y - size * 0.25) < size * 0.12)] = (0.95, 0.85, 0.2)
    stripes = (x > size * 0.05) & (x < size * 0.45) & (y > size * 0.55) & (y < size * 0.95)
    a[stripes] = ((x[stripes] // 3) % 2)[:, None] * np.array([1.0, 1.0, 1.0])
    return Image.fromarray(np.uint8(np.clip(a, 0, 1) * 255 + 0.5)).convert("RGBA")


def downscale_case(target):
    source = photo(512)

    def build():
        p = Project(target, target, "#000000")
        asset = add_image(p, source)
        p.apply([{"type": "add", "asset": asset, "name": "photo", "x": 0, "y": 0},
                 {"type": "resize", "target": "photo", "width": target, "height": target}])
        return p

    markup = (f"<img class='a' style='left:0;top:0;width:{target}px;height:{target}px' "
              f"src='{data_url(source)}'>")

    def reference(project):
        a = np.asarray(source.convert("RGB"), float) / 255
        factor = 512 // target
        if 512 % target == 0:
            return ideal.area_downscale(a, factor)
        return np.asarray(source.convert("RGB").resize((target, target), Image.Resampling.BOX), float) / 255

    def analyze(ctx):
        truth = reference(ctx.project)
        out = {"diff": metrics.diff(ctx.vixl, ctx.chrome)}
        plate = slice(int(target * 0.5), target), slice(int(target * 0.5), target)
        stripes = slice(int(target * 0.6), int(target * 0.9)), slice(int(target * 0.1), int(target * 0.4))
        for label, image in (("vixl", ctx.vixl), ("chrome", ctx.chrome)):
            a = metrics.rgb(image)
            d = (a - truth) * 255
            out[label] = {"rms_vs_area_average": round(float(np.sqrt((d**2).mean())), 3),
                          "zone_plate_rms_vs_area": round(float(np.sqrt((d[plate] ** 2).mean())), 3),
                          "stripe_alias_std": round(float(a[stripes].mean(axis=2).std() * 255), 3),
                          "sharpness": metrics.sharpness(a.mean(axis=2))}
        out["area_average"] = {"stripe_alias_std": round(float(truth[stripes].mean(axis=2).std() * 255), 3),
                               "sharpness": metrics.sharpness(truth.mean(axis=2))}
        return out

    case(name=f"image_downscale_{target}", category="images", title=f"512 px photo-like image shown at {target} px",
         width=target, height=target, background="#000000", build=build, html=lambda project: markup,
         analyze=analyze, reference=reference, tags=("resampling",),
         note="Reference: exact area average (box filter); 3 px stripes alias at non-integer factors.")


downscale_case(128)
downscale_case(170)
