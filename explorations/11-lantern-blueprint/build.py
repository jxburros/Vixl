"""THE FRESNEL LANTERN: an 18 × 24 in patent-plate poster built from Vixl 0.20.0 vector features.

Run from the repo root:

    python explorations/11-lantern-blueprint/build.py

Everything is a native Vixl layer. Nothing is imported: the lantern, gears, lens rings, beams,
callouts and figure panels come from the 0.20 parametric shape catalog, stroke controls (dashes,
caps, multiple strokes, width profiles, markers), path editing (shape-to-path, path-edit,
offset-path, path-smooth, round-corners, outline-stroke), the new pathfinder modes (divide,
exclude), non-destructive distortion (corner-pin, arc, flag), precise transforms (skew, matrix,
anchored resize, fit, match-size), hug stacks and the spatial API.

Outputs go to explorations/11-lantern-blueprint/output/.
"""

import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OUT = HERE / "output"
os.environ.setdefault("VIXL_NO_UPDATE", "1")
os.chdir(ROOT)
sys.path.insert(0, str(ROOT / "src"))

from vixl import Project  # noqa: E402
from vixl.checks import check_design  # noqa: E402
from vixl.typefaces import install_font  # noqa: E402

W, H = 1800, 2400  # 18 × 24 in at 100 dpi

NAVY = "#0E2A47"
DEEP = "#0A1F36"
INK = "#E8F1FF"
FAINT = "#E8F1FF55"
GHOST = "#E8F1FF22"
GOLD = "#F2C14E"
AMBER = "#F29E4C"
SKY = "#7FB2FF"
CX = W / 2  # lantern centreline

HEAD = "barlow-condensed-700"
SUB = "barlow-condensed-500"
MONO = "ibm-plex-mono-400"
MONO_B = "ibm-plex-mono-600"


def text(name, value, x, y, size, font=MONO, color=INK, **kw):
    return {"type": "text", "name": name, "text": value, "x": x, "y": y, "size": size, "font": font,
            "color": color, **kw}


def pen(name, points, color=INK, width=2, **kw):
    xs, ys = [p[0] for p in points], [p[1] for p in points]
    x0, y0 = min(xs), min(ys)
    local = [[px - x0, py - y0] for px, py in points]
    return {"type": "pen", "name": name, "points": local, "x": x0, "y": y0, "stroke": color,
            "stroke_width": width, "fill": "transparent", **kw}


def shape(kind, name, x, y, w, h, **kw):
    kw.setdefault("fill", "transparent")
    return {"type": "shape", "shape": kind, "name": name, "x": x, "y": y, "width": w, "height": h, **kw}


# Sheet -----------------------------------------------------------------------------------------
def sheet():
    ops = [
        shape("rectangle", "paper", 0, 0, W, H, fill=NAVY),
        {"type": "pattern-fill", "target": "paper", "name": "drafting-grid", "pattern": "grid", "spacing": 50,
         "colors": ["#E8F1FF1C", "#00000000"], "opacity": 0.9},
        {"type": "drawn-texture", "target": "paper", "name": "paper-tooth", "preset": "stipple", "color": "#06162A",
         "seed": 4, "strength": 0.25, "grain": 0.6, "scale": 2},
        # Border: an inside rule plus a hairline outside rule from a single shape (multiple strokes).
        shape("rectangle", "border", 60, 60, W - 120, H - 120, stroke=INK, stroke_width=6, stroke_align="inside",
              strokes=[{"color": INK, "width": 1.5, "stroke_align": "outside"}]),
        shape("rectangle", "border-inner", 84, 84, W - 168, H - 168, stroke=FAINT, stroke_width=1,
              dash=[2, 6], line_cap="round"),
        # Edge rulers (tick strips) on all four sides.
        shape("ruler", "ruler-top", 160, 66, W - 320, 18, count=64, fill=FAINT),
        shape("ruler", "ruler-bottom", 160, H - 84, W - 320, 18, count=64, fill=FAINT),
        shape("ruler", "ruler-left", 66, 160, H - 320, 18, count=88, fill=FAINT),
        shape("ruler", "ruler-right", W - 84, 160, H - 320, 18, count=88, fill=FAINT),
    ]
    # Vertical rulers: draw horizontally, rotate 90°, then place the rotated box by its canvas corner.
    for side, x in (("left", 66), ("right", W - 84)):
        ops += [{"type": "rotate", "target": f"ruler-{side}", "value": 90},
                {"type": "move", "target": f"ruler-{side}", "space": "canvas", "x": x, "y": 160}]
    for i, (x, y, rot) in enumerate([(90, 90, 0), (W - 210, 90, 90), (W - 210, H - 210, 180), (90, H - 210, 270)]):
        ops += [shape("corner-ornament", f"corner-{i}", x, y, 120, 120, fill=GOLD, thickness=4),
                {"type": "rotate", "target": f"corner-{i}", "value": rot}]
    return ops


# Header ----------------------------------------------------------------------------------------
def header():
    return [
        text("eyebrow", "LAMPLIGHT WORKS  ·  PATENT DRAWINGS  ·  SERIES L", 160, 150, 26, MONO_B, GOLD,
             spacing=4),
        text("title", "THE FRESNEL LANTERN", 152, 184, 150, HEAD, INK),
        text("subtitle", "A rotating harbour light with stepped prism rings, clockwork drive and Argand burner",
             160, 352, 30, SUB, "#AFC3DE"),
        # Rounded seal with stepped notch edge, plus its lettering arched with an arc distortion.
        shape("seal", "seal", 1440, 132, 230, 230, fill=GOLD, count=28, depth=0.07),
        shape("ring", "seal-ring", 1466, 158, 178, 178, fill=NAVY, thickness=6),
        text("seal-top", "PLATE", 1513, 186, 30, HEAD, NAVY, spacing=6),
        text("seal-num", "IV", 1524, 212, 92, HEAD, NAVY),
        text("seal-foot", "v0.20.0", 1505, 298, 20, MONO_B, NAVY),
        shape("rectangle", "header-rule", 160, 404, W - 320, 4, fill=INK),
        shape("dashed-line", "header-rule-2", 160, 414, W - 320, 6, stroke=FAINT, stroke_width=2, dash=[18, 8]),
    ]


# Main elevation --------------------------------------------------------------------------------
def beams():
    # Two light beams: plain rectangles bent into perspective wedges with a corner-pin distortion.
    return [
        shape("rectangle", "beam-right", 1060, 700, 640, 560, fill="#F2C14E30"),
        {"type": "distort", "target": "beam-right", "kind": "corner-pin",
         "corners": [[0, 210], [640, 0], [640, 560], [0, 350]]},
        shape("rectangle", "beam-left", 100, 700, 640, 560, fill="#F2C14E18"),
        {"type": "distort", "target": "beam-left", "kind": "corner-pin",
         "corners": [[0, 0], [640, 210], [640, 350], [0, 560]]},
        # Swept rays with width profiles: thin at the lamp, swelling outward, tapering at the tip.
        pen("ray-1", [[1080, 960], [1300, 900], [1560, 830], [1700, 800]], GOLD, 10, smooth=True,
            width_profile=[[0, 0.15], [0.55, 1], [1, 0.05]], line_cap="round"),
        pen("ray-2", [[1080, 1000], [1320, 1030], [1560, 1080], [1700, 1110]], GOLD, 8, smooth=True,
            width_profile=[[0, 0.15], [0.6, 1], [1, 0.05]], line_cap="round"),
        pen("ray-3", [[720, 960], [500, 905], [300, 860], [140, 830]], "#F2C14E99", 8, smooth=True,
            width_profile=[[0, 0.15], [0.55, 1], [1, 0.05]], line_cap="round"),
    ]


def lantern():
    ops = [
        # Sunburst glow behind the lens and the burner flame.
        shape("sunburst", "glow", CX - 280, 696, 560, 560, fill="#F2C14E26", count=32),
        # Housing: per-corner radii (round top, square base) and a double rule.
        shape("rounded-rectangle", "housing", CX - 190, 700, 380, 560, radius=[60, 60, 6, 6], stroke=INK,
              stroke_width=5, strokes=[{"color": FAINT, "width": 1.5, "stroke_align": "inside"}]),
        shape("notched-rectangle", "lens-frame", CX - 160, 736, 320, 488, stroke=SKY, stroke_width=2,
              notch=18),
    ]
    # Fresnel rings: concentric vertical lenses (vesica) with alternating solid and dashed strokes.
    for i, (w, h) in enumerate([(300, 460), (246, 384), (192, 306), (138, 228), (84, 150)]):
        style = {"stroke": INK, "stroke_width": 3} if i % 2 == 0 else {"stroke": SKY, "stroke_width": 2,
                                                                         "dash": [10, 6]}
        ops.append(shape("lens", f"fresnel-{i}", CX - w / 2, 980 - h / 2, w, h, fill="#7FB2FF12", **style))
    ops += [
        shape("flame", "flame", CX - 30, 930, 60, 96, fill=GOLD),
        shape("teardrop", "flame-core", CX - 14, 982, 28, 40, fill="#FFF3C4"),
        # Roof: a chamfered isosceles triangle, a half-circle dome, a finial and an arrow vane.
        shape("isosceles-triangle", "roof", CX - 240, 500, 480, 210, fill=DEEP, stroke=INK, stroke_width=5,
              corner_style="chamfer", point_radius=14),
        shape("half-circle", "dome", CX - 70, 474, 140, 70, fill=DEEP, stroke=INK, stroke_width=4),
        shape("ellipse", "finial", CX - 16, 446, 32, 32, fill=GOLD),
        shape("arrow", "vane", CX - 130, 434, 260, 36, fill=INK, head_style="concave", heads="end",
              head_length=0.22, shaft_width=0.25),
        # Gallery deck with railing (a stepped tick strip) and a chamfered pedestal.
        shape("rectangle", "deck", CX - 320, 1262, 640, 22, fill=INK),
        shape("ruler", "railing", CX - 300, 1224, 600, 38, count=24, fill=FAINT),
        shape("rounded-rectangle", "pedestal", CX - 240, 1284, 480, 290, radius=[0, 0, 24, 24],
              corner_style="chamfer", stroke=INK, stroke_width=4, fill="#0A1F3699"),
        # Clockwork cutaway: three meshing gears with different tooth counts.
        shape("gear", "gear-drive", CX - 210, 1310, 220, 220, teeth=22, depth=0.12, hole=0.28,
              stroke=GOLD, stroke_width=3),
        shape("gear", "gear-idler", CX - 4, 1352, 128, 128, teeth=13, depth=0.16, hole=0.3,
              stroke=INK, stroke_width=3),
        shape("gear", "gear-escape", CX + 112, 1318, 96, 96, teeth=10, depth=0.18, hole=0.32,
              stroke=SKY, stroke_width=3),
        shape("rounded-rectangle", "plinth", CX - 300, 1574, 600, 64, radius=[10, 10, 0, 0], fill=INK),
        # Base course: three chamfered steps, each anchored-resized from the plinth's centre.
        shape("rounded-rectangle", "step-1", CX - 300, 1638, 600, 20, radius=4, corner_style="chamfer",
              fill="#E8F1FFAA"),
        shape("rounded-rectangle", "step-2", CX - 300, 1658, 600, 20, radius=4, corner_style="chamfer",
              fill="#E8F1FF77"),
        shape("rounded-rectangle", "step-3", CX - 300, 1678, 600, 20, radius=4, corner_style="chamfer",
              fill="#E8F1FF44"),
        {"type": "resize", "target": "step-1", "width": "+40", "anchor": "center"},
        {"type": "resize", "target": "step-2", "width": "+80", "anchor": "center"},
        {"type": "resize", "target": "step-3", "width": "+120", "anchor": "center"},
    ]
    return ops


def construction():
    ops = [
        # Dash-dot centreline with round caps.
        pen("centreline", [[CX, 424], [CX, 1730]], FAINT, 2, dash=[36, 8, 4, 8], line_cap="round"),
        # Height dimension with markers at both ends and offset dashes.
        pen("dim-height", [[1300, 434], [1300, 1698]], INK, 2, marker_start="triangle", marker_end="triangle",
            marker_size=16),
        pen("dim-height-top", [[1150, 434], [1330, 434]], FAINT, 1, dash=[6, 4]),
        pen("dim-height-bottom", [[1260, 1698], [1330, 1698]], FAINT, 1, dash=[6, 4]),
        text("dim-height-label", "1 264 mm", 1314, 1400, 26, MONO_B, INK),
        pen("dim-width", [[CX - 360, 1740], [CX + 360, 1740]], INK, 2, marker_start="open", marker_end="open",
            marker_size=16),
        text("dim-width-label", "720 mm", CX - 52, 1702, 26, MONO_B, INK),
        # Section line A–A through the lens, with concave markers pointing in.
        pen("section", [[CX - 230, 980], [CX + 230, 980]], AMBER, 3, dash=[24, 8], marker_start="concave",
            marker_end="concave", marker_size=18),
        text("section-a1", "A", CX - 268, 960, 32, HEAD, "#FFD27A"),
        text("section-a2", "A", CX + 246, 960, 32, HEAD, "#FFD27A"),
        # A curved rotation arrow over the clockwork (quadratic arrow from explicit local points).
        shape("arrow", "rotation", CX - 200, 1500, 400, 70, fill=GOLD, heads="both", head_style="triangle",
              **{"from": [10, 20], "to": [390, 20], "control": [200, 80]}, shaft_width=6, head_length=22,
              head_width=24),
    ]
    return ops


CALLOUTS = [
    # number, label, detail, anchor point on the drawing, side
    (1, "Arrow weathervane", "turns the cowl off the wind", (CX + 110, 452), "right"),
    (2, "Ventilator dome", "vents the burner smoke", (CX + 56, 520), "right"),
    (3, "Fresnel prism rings", "five stepped lenses", (CX + 140, 860), "right"),
    (4, "Argand burner", "hollow wick, glass chimney", (CX - 26, 990), "left"),
    (5, "Gallery railing", "24 stanchions, wrought iron", (CX - 270, 1240), "left"),
    (6, "Clockwork drive", "22-13-10 gear train, 1 rev/min", (CX - 150, 1420), "left"),
    (7, "Granite plinth", "three-step base course", (CX + 310, 1668), "right"),
]


def callouts():
    ops = []
    rows = {"left": 0, "right": 0}
    for number, label, detail, (ax, ay), side in CALLOUTS:
        row = rows[side]
        rows[side] += 1
        y = {"left": [860, 1080, 1360], "right": [470, 590, 800, 1520]}[side][row]
        x = 150 if side == "left" else 1330
        bubble_x = x + 300 if side == "left" else x - 20
        ops += [
            shape("ellipse", f"num-{number}-disc", x, y, 52, 52, fill=GOLD),
            text(f"num-{number}", str(number), x + 15.5, y + 6, 34, HEAD, NAVY),
            # Hug stacks: the label pill sizes itself to its text and padding.
            text(f"label-{number}", label.upper(), 0, 0, 26, HEAD, INK),
            text(f"detail-{number}", detail, 0, 0, 20, MONO, "#C9D8EE"),
            {"type": "stack", "name": f"callout-{number}", "targets": [f"label-{number}", f"detail-{number}"],
             "direction": "vertical", "gap": 2, "size": "hug", "background": "#0A1F36", "radius": 8,
             "stroke": FAINT, "stroke_width": 1, "padding": {"top": 8, "right": 14, "bottom": 10, "left": 14}},
            {"type": "move", "target": f"callout-{number}", "x": x + 66, "y": y - 6},
        ]
        start = (x + 26, y + 26)
        ops.append({"_leader": number, "start": start, "anchor": (ax, ay), "side": side, "bubble_x": bubble_x})
    return ops


def resolve_leaders(p, ops):
    """Leaders start at the far edge of each measured callout and end in a round marker on the part."""
    final = []
    for op in ops:
        if "_leader" not in op:
            final.append(op)
            continue
        number, (ax, ay) = op["_leader"], op["anchor"]
        info = p.spatial(target=f"callout-{number}", mode="canvas")["layers"][0]
        x, y, w, h = info["bounds"]
        sx = x + w + 6 if op["side"] == "left" else x - 6
        sy = y + h / 2
        if op["side"] == "right":
            disc = p.spatial(target=f"num-{number}-disc", mode="canvas")["layers"][0]["bounds"]
            sx = disc[0] - 6
            sy = disc[1] + disc[3] / 2
        elbow = (ax + (40 if op["side"] == "right" else -40), sy)
        final.append(pen(f"leader-{number}", [[sx, sy], list(elbow), [ax, ay]], INK, 1.5, marker_end="round",
                         marker_size=10, line_join="round"))
    return final


# Figure panels -----------------------------------------------------------------------------------
PANEL_Y, PANEL_H = 1800, 360
PANELS = [(160, "FIG. 2", "LENS PROFILE · SECTION A–A"), (660, "FIG. 3", "PRISM RINGS · PATHFINDER DIVIDE"),
          (1160, "FIG. 4", "HOUSING · ISOMETRIC")]


def panels():
    ops = []
    for i, (x, fig, caption) in enumerate(PANELS):
        ops += [
            shape("rectangle", f"panel-{i}", x, PANEL_Y, 480, PANEL_H, fill="#0A1F3680", stroke=INK,
                  stroke_width=2),
            shape("corner-bracket", f"panel-{i}-mark", x + 10, PANEL_Y + 10, 34, 34, stroke=GOLD, stroke_width=3,
                  thickness=3, fill=GOLD),
            text(f"panel-{i}-fig", fig, x + 56, PANEL_Y + 14, 28, HEAD, GOLD),
            text(f"panel-{i}-cap", caption, x + 56, PANEL_Y + 48, 20, MONO, "#C9D8EE"),
        ]
    # FIG. 2 — a squircle converted to nodes, reshaped into a plano-convex section, smoothed,
    # then given an offset coating outline and rounded corners on a duplicate.
    px, py = 160 + 150, PANEL_Y + 88
    ops += [
        shape("squircle", "profile", px, py, 170, 200, fill="#7FB2FF55", stroke=INK, stroke_width=3),
        {"type": "shape-to-path", "target": "profile"},
        {"type": "path-simplify", "target": "profile", "tolerance": 0.6},  # 192 sampled nodes → a few dozen
        {"type": "path-edit", "target": "profile", "action": "move", "contour": 0, "index": 0, "point": [40, 0],
         "relative": True},
        {"type": "path-edit", "target": "profile", "action": "insert", "contour": 0, "index": 1, "fraction": 0.5},
        {"type": "path-edit", "target": "profile", "action": "corner", "contour": 0, "index": 2},
        {"type": "path-smooth", "target": "profile", "amount": 0.4, "iterations": 1},
        {"type": "duplicate", "target": "profile", "name": "profile-coating"},
        {"type": "offset-path", "target": "profile-coating", "distance": 14, "join": "round"},
        {"type": "shape", "target": "profile-coating", "fill": "transparent", "stroke": GOLD, "stroke_width": 2,
         "dash": [8, 6]},
        pen("profile-axis", [[160 + 60, py + 100], [160 + 440, py + 100]], AMBER, 2, dash=[16, 6, 3, 6],
            marker_end="triangle", marker_size=12),
        text("profile-note", "offset +14 px coating", 160 + 40, PANEL_Y + 320, 20, MONO, GOLD),
    ]
    # FIG. 3 — three overlapping rings divided into independent faces; a fourth disc is XOR-ed.
    cx0, cy0 = 660 + 240, PANEL_Y + 180
    r = 76
    for name, (dx, dy), color in (("ring-a", (-55, -30), "#7FB2FF"), ("ring-b", (55, -30), "#F2C14E"),
                                  ("ring-c", (0, 62), "#F29E4C")):
        ops.append(shape("ellipse", name, cx0 + dx - r, cy0 + dy - r, 2 * r, 2 * r, fill=color))
    # Divide takes opaque, unstroked operands; the outlines are drawn afterwards as their own layers.
    ops.append({"type": "pathfinder", "name": "prism-faces", "targets": ["ring-a", "ring-b", "ring-c"],
                "mode": "divide"})
    for name, (dx, dy) in (("ring-a", (-55, -30)), ("ring-b", (55, -30)), ("ring-c", (0, 62))):
        ops.append(shape("ellipse", f"{name}-outline", cx0 + dx - r, cy0 + dy - r, 2 * r, 2 * r, stroke=INK,
                         stroke_width=2))
    ops.append(text("prism-note", "divide → 7 editable faces", 660 + 40, PANEL_Y + 320, 20, MONO, GOLD))
    # FIG. 4 — an isometric housing: a cube, a skewed document panel via an affine matrix, an arched label.
    bx, by = 1160 + 70, PANEL_Y + 100
    ops += [
        shape("cube", "iso-cube", bx, by + 30, 170, 170, fill="#7FB2FF40", stroke=INK, stroke_width=2, depth=0.35),
        shape("document", "iso-spec", 0, 0, 150, 120, fill="#F2C14E40", stroke=GOLD, stroke_width=2, fold=0.2),
        {"type": "transform", "target": "iso-spec", "matrix": [0.866, 0.5, 0, 1, bx + 210, by + 20]},
        text("iso-label", "SPEC SHEET", 0, 0, 22, HEAD, INK),
        {"type": "transform", "target": "iso-label", "matrix": [0.866, 0.5, 0, 1, bx + 222, by + 62]},
        shape("dashed-line", "iso-ground", 1160 + 40, PANEL_Y + 300, 400, 6, stroke=FAINT, stroke_width=2,
              dash=[4, 6], line_cap="round"),
        text("iso-note", "matrix [.866 .5 0 1 e f]", 1160 + 40, PANEL_Y + 320, 20, MONO, GOLD),
    ]
    return ops


# Title block -------------------------------------------------------------------------------------
def title_block():
    y = 2196
    cells = [("DRAWN", "Vixl 0.20.0 · Python API"), ("SCALE", "1 : 8"), ("SHEET", "4 OF 7"),
             ("DATE", "2026-10-06"), ("CHECKED", "check · spatial")]
    ops = [shape("rectangle", "title-block", 160, y, W - 320, 110, fill="#0A1F36", stroke=INK, stroke_width=3)]
    widths = [400, 170, 190, 250, 250]  # leaves the right end of the block for the banner
    x = 160
    for i, ((key, value), w) in enumerate(zip(cells, widths)):
        if i:
            ops.append(pen(f"tb-div-{i}", [[x, y], [x, y + 110]], INK, 2))
        ops += [text(f"tb-key-{i}", key, x + 20, y + 16, 20, MONO_B, GOLD, spacing=3),
                text(f"tb-val-{i}", value, x + 20, y + 50, 32, SUB, INK)]
        x += w
    # The banner names the series; flag distortion gives it a cloth wave.
    ops += [
        shape("banner", "series-banner", 1430, y + 18, 200, 74, fill=GOLD, fold=0.18),
        text("series-label", "SERIES L", 1472, y + 34, 34, HEAD, NAVY),
        # Group distortion needs shape/path children, so only the cloth is warped, not the lettering.
        {"type": "distort", "target": "series-banner", "kind": "flag", "amount": 0.12, "frequency": 1.5,
         "phase": 0.2},
    ]
    return ops


def build():
    p = Project(W, H, NAVY)
    install_font(p, "Barlow Condensed", 700, role="heading")
    install_font(p, "Barlow Condensed", 500)
    install_font(p, "IBM Plex Mono", 400, role="body")
    install_font(p, "IBM Plex Mono", 600)
    p.apply(sheet(), detail="brief")
    p.apply(header(), detail="brief")
    p.apply(beams(), detail="brief")
    p.apply(lantern(), detail="brief")
    p.apply(construction(), detail="brief")
    pending = callouts()
    p.apply([op for op in pending if "_leader" not in op], detail="brief")
    p.apply([op for op in resolve_leaders(p, pending) if op.get("type") == "pen"], detail="brief")
    p.apply(panels(), detail="brief")
    p.apply(title_block(), detail="brief")
    return p


def spatial_report(p):
    """Measure what the drawing promises: aligned callouts and panels, ink bounds, free space."""
    def relations(names):
        result = p.spatial(targets=names, mode="relations", tolerance=0.5)
        return [{"a": r.get("a", r.get("from")), "b": r.get("b", r.get("to")), "alignments": r["alignments"],
                 "vertical_gap": r.get("vertical_gap"), "horizontal_gap": r.get("horizontal_gap")}
                for r in result["relations"]]

    report = {side: relations([f"num-{n}-disc" for n, *_r, s in CALLOUTS if s == side]) for side in ("left", "right")}
    report["panels"] = relations(["panel-0", "panel-1", "panel-2"])
    title = p.spatial(target="title", mode="canvas", bounds="ink")["layers"][0]
    report["title_ink"] = {"bounds": title["bounds"], "thirds": title["canvas"]["thirds"]}
    # Room left in the left callout column once the background art is ignored.
    background = ["paper", "drafting-grid", "paper-tooth", "beam-left", "beam-right", "glow", "border",
                  "border-inner", "ray-3", "centreline"]
    free = p.spatial(mode="free", region=[150, 470, 560, 1220], targets=background, limit=3)
    report["free_left_column"] = free["rectangles"]
    return report


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    p = build()
    p.save(OUT / "fresnel-lantern.vixl")
    p.export(OUT / "fresnel-lantern.png", overwrite=True)
    p.export(OUT / "fresnel-lantern-preview.jpg", scale=0.4, quality=85, overwrite=True)
    p.export(OUT / "fresnel-lantern.svg", overwrite=True)
    p.export(OUT / "fresnel-lantern.pdf", overwrite=True)
    # Legibility is judged at 900 px wide (the poster seen across a room), not a 320 px thumbnail.
    findings = check_design(p, thumbnail_width=900)
    (OUT / "fresnel-lantern.check.json").write_text(json.dumps(findings, indent=2, default=str))
    (OUT / "fresnel-lantern.spatial.json").write_text(json.dumps(spatial_report(p), indent=2, default=str))
    print("layers:", len(p.inspect()["layers"]))
    print("check:", "passed" if findings["passed"] else "issues", findings["errors"], "errors",
          findings["warnings"], "warnings")


if __name__ == "__main__":
    main()
