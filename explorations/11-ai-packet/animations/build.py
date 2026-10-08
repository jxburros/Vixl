"""AI packet: slick animations, built with Vixl 0.23.

Run from the repo root:
    python explorations/11-ai-packet/animations/build.py            # every piece
    python explorations/11-ai-packet/animations/build.py neural     # one piece (neural, kinetic, robot, nextword, badge)

Writes .vixl sources and GIF/WebP/MP4 exports plus contact sheets next to this file (out/).
"""

import json
import math
import os
import random
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"
os.environ.setdefault("VIXL_NO_UPDATE", "1")

from vixl import Project  # noqa: E402
from vixl.typefaces import install_font  # noqa: E402
from vixl.timeline import contact_sheet, export_timeline  # noqa: E402

TIMES = {}

# Shared packet palette --------------------------------------------------------------------------
NIGHT = "#0B1026"
NIGHT_2 = "#141B3D"
LINE = "#26305C"
CYAN = "#5EEAD4"
VIOLET = "#A78BFA"
AMBER = "#FBBF24"
CORAL = "#FB7185"
PAPER = "#F5F3FF"
MUTED = "#94A3B8"


def apply(p, ops):
    res = p.apply(ops, detail="compact")
    for w in res.get("warnings", []) or []:
        print("   warning:", str(w)[:300])
    return res


def timed(label, fn, *a, **k):
    t0 = time.time()
    r = fn(*a, **k)
    TIMES[label] = round(time.time() - t0, 2)
    print(f"   {label}: {TIMES[label]} s")
    return r


def export(p, name, **opts):
    path = OUT / name
    if name.endswith(".gif"):
        # Workaround: a GIF over 1 MB whose identical frames merge crashes in the size warning's WebP trial
        # (IndexError, see NOTES.md); a large soft max_bytes skips that warning.
        opts.setdefault("max_bytes", 10_000_000)
    if path.exists():
        path.unlink()
    res = timed(f"export {name}", export_timeline, p, path, **opts)
    for w in res.get("warnings", []) or []:
        print("   export warning:", str(w)[:300])
    print(f"   {name}: {path.stat().st_size / 1024:.0f} KB")
    return res


def save(p, name):
    path = OUT / name
    if path.exists():
        path.unlink()
    p.save(str(path))


def check(name, checks=("motion",)):
    """Run the CLI check on a saved source and print the findings."""
    proc = subprocess.run(["vixl", "--json", "-p", str(OUT / name), "check", "--checks", *checks],
                          capture_output=True, text=True)
    try:
        report = json.loads(proc.stdout)
    except json.JSONDecodeError:
        print(proc.stdout[-2000:], proc.stderr[-2000:])
        return None
    findings = report.get("findings", report.get("issues", []))
    print(f"   check {name} {checks}: {len(findings)} findings")
    for f in findings[:25]:
        print("     -", f.get("action"), f.get("code") or f.get("kind"), ":", str(f.get("message"))[:220])
    return report


def sheet(p, name, **kw):
    img = contact_sheet(p, **kw)
    img.convert("RGB").save(OUT / name, quality=80)


# ================================================================================================
# 1. Neural network "thinking" loop
# ================================================================================================

def neural():
    W = H = 1080
    DUR, FPS = 4800, 30
    p = Project(W, H, NIGHT)
    install_font(p, "Space Grotesk", 700, role="heading")
    install_font(p, "Inter", 500, role="body")

    layers_x = [190, 420, 660, 890]
    counts = [3, 5, 5, 2]
    gap = 118
    cy = 655
    nodes = []  # per column: list of (name, x, y)
    for c, (x, n) in enumerate(zip(layers_x, counts)):
        col = []
        for i in range(n):
            y = cy + (i - (n - 1) / 2) * gap
            col.append((f"n{c}-{i}", x, y))
        nodes.append(col)

    ops = [
        {"type": "gradient", "name": "glow-bg", "direction": "radial", "start": "#1C2766", "end": NIGHT,
         "falloff": "smooth", "x": -140, "y": 0, "width": 1360, "height": 1240},
    ]
    # Dim static wiring
    for c in range(3):
        for a in nodes[c]:
            for b in nodes[c + 1]:
                ops.append({"type": "pen", "name": f"w-{a[0]}-{b[0]}", "points": [[a[1], a[2]], [b[1], b[2]]],
                            "smooth": False, "stroke": LINE, "stroke_width": 3, "fill": "transparent"})
    apply(p, ops)

    # Two waves through different paths: (column, from index, to index)
    rnd = random.Random(7)
    waves = [
        {"t0": 200, "color": CYAN, "path": [[0, 1, 2], [1, 3, 4], [1, 2, 3], [0]], "out": 0},
        {"t0": 2600, "color": VIOLET, "path": [[1, 2], [0, 2, 3], [0, 2, 4], [1]], "out": 1},
    ]
    STEP = 500          # one hop between columns
    TRAVEL = 460        # head of the worm crosses the wire
    TAIL = 170          # tail follows this much later
    fired = {}          # node name -> list of fire times
    signal_ops, key_ops = [], []
    for wi, wave in enumerate(waves):
        active = wave["path"]
        for c in range(3):
            t = wave["t0"] + c * STEP
            for i in active[c]:
                for j in active[c + 1]:
                    a, b = nodes[c][i], nodes[c + 1][j]
                    name = f"s{wi}-{a[0]}-{b[0]}"
                    signal_ops.append({"type": "pen", "name": name, "points": [[a[1], a[2]], [b[1], b[2]]],
                                       "smooth": False, "stroke": wave["color"], "stroke_width": 7,
                                       "fill": "transparent", "line_cap": "round",
                                       "trim_start": 0, "trim_end": 0})
                    key_ops += [
                        {"type": "keyframe", "target": name, "property": "trim_end", "time": 0, "value": 0, "easing": "hold"},
                        {"type": "keyframe", "target": name, "property": "trim_end", "time": t, "value": 0,
                         "easing": "ease-in-out-sine"},
                        {"type": "keyframe", "target": name, "property": "trim_end", "time": t + TRAVEL, "value": 100, "easing": "hold"},
                        {"type": "keyframe", "target": name, "property": "trim_start", "time": 0, "value": 0, "easing": "hold"},
                        {"type": "keyframe", "target": name, "property": "trim_start", "time": t + TAIL, "value": 0,
                         "easing": "ease-in-out-sine"},
                        {"type": "keyframe", "target": name, "property": "trim_start", "time": t + TAIL + TRAVEL,
                         "value": 100, "easing": "hold"},
                    ]
                    fired.setdefault(b[0], []).append((t + TRAVEL - 60, wave["color"]))
            if c == 0:
                for i in active[0]:
                    fired.setdefault(nodes[0][i][0], []).append((t - 150, wave["color"]))

    # Nodes: halo (pulses outward), ring, core (lights up)
    node_ops = []
    for col in nodes:
        for name, x, y in col:
            node_ops += [
                {"type": "shape", "name": f"{name}-halo", "shape": "ellipse", "width": 60, "height": 60,
                 "x": x - 30, "y": y - 30, "fill": "transparent", "stroke": CYAN, "stroke_width": 4, "opacity": 0},
                {"type": "shape", "name": f"{name}-ring", "shape": "ellipse", "width": 60, "height": 60,
                 "x": x - 30, "y": y - 30, "fill": NIGHT_2, "stroke": "#4B5A9B", "stroke_width": 4},
                {"type": "shape", "name": f"{name}-core", "shape": "ellipse", "width": 34, "height": 34,
                 "x": x - 17, "y": y - 17, "fill": CYAN, "opacity": 0},
            ]
    apply(p, signal_ops + node_ops)
    apply(p, [{"type": "layer-style", "targets": [o["name"] for o in signal_ops], "name": "outer-glow",
               "settings": {"color": "#7DF9FF", "blur": 14, "opacity": 0.55}}])

    for name, events in fired.items():
        events = sorted(events)
        halo_keys = [(0, 0, 1, "hold")]
        core_keys = [(0, 0, "hold")]
        for t, color in events:
            halo_keys += [(t, 0.9, 1.0, "ease-out-cubic"), (t + 650, 0, 2.1, "hold")]
            core_keys += [(t, 0, "ease-out-cubic"), (t + 140, 1, "ease-in-out-sine"), (t + 700, 0, "hold")]
        for (t, op, sc, e) in halo_keys:
            key_ops += [{"type": "keyframe", "target": f"{name}-halo", "property": "opacity", "time": t, "value": op, "easing": e},
                        {"type": "keyframe", "target": f"{name}-halo", "property": "scale", "time": t, "value": sc, "easing": e}]
        for (t, op, e) in core_keys:
            key_ops.append({"type": "keyframe", "target": f"{name}-core", "property": "opacity", "time": t, "value": op, "easing": e})
        # colour of the core follows the wave that lights it
        for t, color in events:
            key_ops.append({"type": "keyframe", "target": f"{name}-core", "property": "fill", "time": max(0, t - 20), "value": color, "easing": "hold"})
            key_ops.append({"type": "keyframe", "target": f"{name}-halo", "property": "stroke", "time": max(0, t - 20), "value": color, "easing": "hold"})

    ops = [{"type": "timeline-set", "duration": DUR, "fps": FPS, "loop_mode": "seamless"}] + key_ops
    ops.append({"type": "timeline-set", "close": True})
    apply(p, ops)

    # Type
    apply(p, [
        {"type": "text", "name": "kicker", "text": "INSIDE THE MODEL", "font": "inter-500", "size": 26,
         "color": CYAN, "x": 110, "y": 120},
        {"type": "text", "name": "title", "text": "Signals light up\npatterns it has learned", "font": "space-grotesk-700",
         "size": 60, "color": PAPER, "x": 110, "y": 160},
        {"type": "text", "name": "in-label", "text": "input", "font": "inter-500", "size": 26, "color": MUTED,
         "x": layers_x[0] - 32, "y": 960},
        {"type": "text", "name": "out-label", "text": "output", "font": "inter-500", "size": 26, "color": MUTED,
         "x": layers_x[3] - 40, "y": 960},
    ])
    # Output read-outs: the answer each wave arrives at
    ops = []
    for k, (word, color, wave) in enumerate([("cat", CYAN, waves[0]), ("dog", VIOLET, waves[1])]):
        name, x, y = nodes[3][k]
        t = wave["t0"] + 2 * STEP + TRAVEL - 60
        ops.append({"type": "text", "name": f"answer-{word}", "text": word, "font": "space-grotesk-700", "size": 34,
                    "color": color, "x": x + 50, "y": y - 22, "opacity": 0.3})
        ops += [{"type": "keyframe", "target": f"answer-{word}", "property": "opacity", "time": tt, "value": v, "easing": e}
                for tt, v, e in [(0, 0.3, "hold"), (t - 40, 0.3, "ease-out-cubic"), (t + 160, 1, "hold"),
                                 (t + 420, 1, "ease-in-out-sine"), (t + 760, 0.3, "hold")]]
        ops += [{"type": "keyframe", "target": f"answer-{word}", "property": "translate-x", "time": tt, "value": v, "easing": e}
                for tt, v, e in [(0, 0, "hold"), (t - 40, 0, "ease-out-back"), (t + 300, 8, "ease-in-out-sine"), (t + 760, 0, "hold")]]
    apply(p, ops)
    save(p, "neural-network.vixl")
    check("neural-network.vixl")
    timed("neural sheet", sheet, p, "neural-network-sheet.jpg", count=16, columns=4, max_width=1600)
    if os.environ.get("QUICK"):
        return p
    export(p, "neural-network.mp4")
    export(p, "neural-network.gif", scale=0.4, fps=20, dither="none")
    return p


# ================================================================================================
# 2. Kinetic type: Ask. Iterate. Verify.
# ================================================================================================

def kinetic():
    DUR, FPS = 7500, 30
    p = Project.sized("instagram-portrait", background=NIGHT, design=False)
    install_font(p, "Space Grotesk", 700, role="heading")
    install_font(p, "Inter", 500, role="body")
    HEAD, BODY = "space-grotesk-700", "inter-500"
    X = 110
    rows = [("ask", "Ask.", CYAN, 330), ("iterate", "Iterate.", VIOLET, 560), ("verify", "Verify.", AMBER, 790)]
    ops = [
        {"type": "timeline-set", "duration": DUR, "fps": FPS, "loop": 0},
        {"type": "marker", "name": "ask", "time": 300},
        {"type": "marker", "name": "iterate", "time": 1300},
        {"type": "marker", "name": "verify", "time": 2300},
        {"type": "marker", "name": "tagline", "time": 3200},
        {"type": "text", "name": "kicker", "text": "3 HABITS FOR WORKING WITH AI", "font": BODY, "size": 30,
         "color": MUTED, "x": X, "y": 170},
    ]
    for key, word, color, y in rows:
        ops.append({"type": "text", "name": key, "text": word, "font": HEAD, "size": 176, "color": PAPER,
                    "x": X, "y": y, "line_height": 1.0})
    # Icons to the right of each word, drawn on with trim
    IX = 800
    ops += [
        {"type": "shape", "name": "icon-ask", "shape": "speech-bubble", "width": 170, "height": 150, "x": IX,
         "y": 350, "fill": "transparent", "stroke": CYAN, "stroke_width": 12, "line_cap": "round", "line_join": "round"},
    ]
    # circular arrow: an open SVG arc in the layer's own pixels, plus a separate arrowhead
    r = 72
    a0, a1 = math.radians(-60), math.radians(235)
    x0, y0 = r + 8 + r * math.cos(a0), r + 8 + r * math.sin(a0)
    x1, y1 = r + 8 + r * math.cos(a1), r + 8 + r * math.sin(a1)
    ops.append({"type": "shape", "name": "icon-iterate", "shape": "path",
                "path": f"M{x0:.1f} {y0:.1f} A{r} {r} 0 1 1 {x1:.1f} {y1:.1f}", "x": IX + 5, "y": 575,
                "fill": "transparent", "stroke": VIOLET, "stroke_width": 12, "line_cap": "round"})
    # arrowhead at the arc's end, pointing along the clockwise tangent
    ex, ey = IX + 5 + x1, 575 + y1
    tang = a1 + math.pi / 2
    def pt(d, side):
        return [ex + d * math.cos(tang) + side * math.cos(tang + math.pi / 2),
                ey + d * math.sin(tang) + side * math.sin(tang + math.pi / 2)]
    ops.append({"type": "pen", "name": "icon-iterate-head", "points": [pt(-26, -26), pt(4, 0), pt(-26, 26)],
                "smooth": False, "fill": "transparent", "stroke": VIOLET, "stroke_width": 12, "line_cap": "round",
                "line_join": "round"})
    ops += [
        {"type": "shape", "name": "icon-verify-ring", "shape": "ellipse", "width": 160, "height": 160, "x": IX + 5,
         "y": 805, "fill": "transparent", "stroke": AMBER, "stroke_width": 12},
        {"type": "pen", "name": "icon-verify-check", "points": [[IX + 48, 888], [IX + 76, 915], [IX + 128, 857]],
         "smooth": False, "fill": "transparent", "stroke": AMBER, "stroke_width": 14, "line_cap": "round",
         "line_join": "round"},
        {"type": "shape", "name": "rule", "shape": "rectangle", "width": 860, "height": 4, "x": X, "y": 1060,
         "fill": LINE},
        {"type": "text", "name": "tagline", "text": "You steer. The model drafts.\nYou check what comes back.",
         "font": BODY, "size": 44, "color": PAPER, "x": X, "y": 1100, "line_height": 1.3},
    ]
    apply(p, ops)
    apply(p, [{"type": "group", "name": "iter-g", "targets": ["icon-iterate", "icon-iterate-head"]},
              {"type": "group", "name": "ver-g", "targets": ["icon-verify-ring", "icon-verify-check"]}])
    names = [o["name"] for o in ops if o.get("name") and o["type"] in ("text", "shape", "pen")]
    names = [n for n in names if n not in ("icon-iterate", "icon-iterate-head", "icon-verify-ring", "icon-verify-check")]
    apply(p, [{"type": "group", "name": "card", "targets": names + ["iter-g", "ver-g"]}])

    # Motion: each word in, then its icon draws on, then the word takes its colour.
    # Entrances play "in" only (no automatic play-back); one shared exit fades the whole card.
    motion_ops = [
        {"type": "text-animate", "target": "kicker", "preset": "typewriter", "unit": "char", "start": 0, "duration": 700},
        {"type": "text-animate", "target": "ask", "preset": "pop", "unit": "char", "start": "ask", "duration": 450, "stagger": 60},
        {"type": "animate-preset", "target": "icon-ask", "preset": "draw-on", "start": 650, "duration": 700, "easing": "ease-out-cubic"},
        {"type": "text-animate", "target": "iterate", "preset": "slide-left", "unit": "char", "start": "iterate", "duration": 500, "stagger": 45},
        {"type": "animate-preset", "target": "icon-iterate", "preset": "draw-on", "start": 1650, "duration": 700, "easing": "ease-out-cubic"},
        {"type": "animate-preset", "target": "icon-iterate-head", "preset": "pop-in", "start": 2250, "duration": 300},
        {"type": "text-animate", "target": "verify", "preset": "fade-up", "unit": "char", "start": "verify", "duration": 500, "stagger": 50},
        {"type": "animate-preset", "target": "icon-verify-ring", "preset": "draw-on", "start": 2600, "duration": 600, "easing": "ease-out-cubic"},
        {"type": "animate-preset", "target": "icon-verify-check", "preset": "draw-on", "start": 3000, "duration": 350, "easing": "ease-out-cubic"},
        {"type": "animate-preset", "target": "rule", "preset": "slide-in-left", "start": "tagline", "duration": 600, "distance": 200},
        {"type": "text-animate", "target": "tagline", "preset": "fade-up", "unit": "word", "start": 3300, "duration": 500, "stagger": 70},
    ]
    # a gentle staggered pulse through the icons while the card holds
    motion_ops.append({"type": "animate-preset", "targets": ["icon-ask", "iter-g", "ver-g"], "preset": "pulse",
                       "start": 4700, "duration": 700, "stagger": 180, "amount": 1.12})
    for op in motion_ops:
        if op["type"] == "text-animate":
            op["mode"] = "in"
        else:
            op["close"] = False
    apply(p, motion_ops)
    apply(p, [
        {"type": "keyframe", "target": "card", "property": "opacity", "time": 0, "value": 1, "easing": "hold"},
        {"type": "keyframe", "target": "card", "property": "opacity", "time": 6800, "value": 1, "easing": "ease-in-cubic"},
        {"type": "keyframe", "target": "card", "property": "opacity", "time": 7300, "value": 0, "easing": "hold"},
        {"type": "keyframe", "target": "card", "property": "translate-y", "time": 6800, "value": 0, "easing": "ease-in-cubic"},
        {"type": "keyframe", "target": "card", "property": "translate-y", "time": 7300, "value": -40, "easing": "hold"},
    ])
    for key, word, color, y in rows:
        t0 = {"ask": 300, "iterate": 1300, "verify": 2300}[key]
        apply(p, [{"type": "text-animate", "target": key, "preset": "color-sweep", "unit": "char", "start": t0 + 500,
                   "duration": 300, "stagger": 30, "from": PAPER, "mode": "in"},
                  {"type": "keyframe", "target": key, "property": "color", "time": 0, "value": color}])
    save(p, "kinetic-ask-iterate-verify.vixl")
    check("kinetic-ask-iterate-verify.vixl")
    timed("kinetic sheet", sheet, p, "kinetic-sheet.jpg", count=16, columns=4, max_width=1600)
    if os.environ.get("QUICK"):
        return p
    export(p, "kinetic-ask-iterate-verify.mp4")
    export(p, "kinetic-ask-iterate-verify.webp", scale=0.5, fps=20, poster="5.5s")
    return p


# ================================================================================================
# 3. Friendly AI-helper robot: walks toward the viewer (front-view walk), waves, says hi
# ================================================================================================

ROBOT_SHELL = "#EEF1FF"
ROBOT_LIMB = "#C7CCF0"
ROBOT_BODY = "#7C6CF2"
ROBOT_DARK = "#1A2150"
ROBOT_FOOT = "#3B4380"


def robot_parts(prefix):
    """Robot artwork in the character's local pixels (about 420 x 610). Returns ops and the parts map."""
    P = lambda n: f"{prefix}-{n}"
    rr = lambda name, x, y, w, h, fill, r=None, **kw: {"type": "shape", "name": P(name), "shape": "rounded-rectangle",
                                                         "x": x, "y": y, "width": w, "height": h, "fill": fill,
                                                         "radius": r if r is not None else min(w, h) / 2, **kw}
    ell = lambda name, cx, cy, w, h, fill, **kw: {"type": "shape", "name": P(name), "shape": "ellipse", "x": cx - w / 2,
                                                  "y": cy - h / 2, "width": w, "height": h, "fill": fill, **kw}
    ops = []
    # limbs first (behind the torso), left then right; centres at x 105 / 315 for arms, 172 / 248 for legs
    for side, ax, lx in (("left", 105, 172), ("right", 315, 248)):
        ops += [
            rr(f"{side}-upper-leg", lx - 22, 440, 44, 72, ROBOT_LIMB),
            rr(f"{side}-lower-leg", lx - 20, 505, 40, 70, ROBOT_LIMB),
            rr(f"{side}-foot", lx - 40, 568, 80, 36, ROBOT_FOOT, r=16),
            rr(f"{side}-upper-arm", ax - 20, 285, 40, 92, ROBOT_LIMB),
            rr(f"{side}-lower-arm", ax - 18, 370, 36, 82, ROBOT_LIMB),
            ell(f"{side}-hand", ax, 470, 52, 52, ROBOT_BODY),
        ]
    # torso: neck, body, chest panel, heart light (one group = one part)
    ops += [
        rr("neck", 188, 250, 44, 30, ROBOT_LIMB, r=8),
        rr("body", 118, 268, 184, 184, ROBOT_BODY, r=44),
        rr("panel", 158, 306, 104, 74, ROBOT_SHELL, r=20),
        ell("heart", 210, 343, 34, 34, CORAL),
        {"type": "group", "name": P("torso"), "targets": [P("neck"), P("body"), P("panel"), P("heart")]},
    ]
    # head: antenna, ears, shell, visor (one group); eyes and mouth are their own parts on top
    ops += [
        {"type": "pen", "name": P("antenna-stem"), "points": [[210, 96], [210, 50]], "smooth": False,
         "stroke": ROBOT_LIMB, "stroke_width": 8, "fill": "transparent", "line_cap": "round"},
        ell("antenna-ball", 210, 42, 30, 30, AMBER),
        rr("ear-l", 68, 150, 30, 64, ROBOT_BODY, r=12),
        rr("ear-r", 322, 150, 30, 64, ROBOT_BODY, r=12),
        rr("shell", 88, 90, 244, 172, ROBOT_SHELL, r=56),
        rr("visor", 114, 118, 192, 118, ROBOT_DARK, r=40),
        {"type": "group", "name": P("head"), "targets": [P("antenna-stem"), P("antenna-ball"), P("ear-l"), P("ear-r"),
                                                         P("shell"), P("visor")]},
        rr("left-eye", 160, 150, 32, 44, CYAN, r=16),
        rr("right-eye", 228, 150, 32, 44, CYAN, r=16),
        {"type": "shape", "name": P("mouth"), "shape": "path", "path": "M4 4 Q26 22 48 4", "x": 186, "y": 202,
         "fill": "transparent", "stroke": CYAN, "stroke_width": 7, "line_cap": "round"},
    ]
    names = ["torso", "head", "left-eye", "right-eye", "mouth"] + [f"{s}-{p}" for s in ("left", "right")
             for p in ("upper-arm", "lower-arm", "hand", "upper-leg", "lower-leg", "foot")]
    return ops, {n: P(n) for n in names}


def robot_bones(p):
    """Bone origins must be in the character group's local frame (its box starts at the antenna/ears),
    not in the coordinates the artwork was drawn in, so read them back from the grouped layers."""
    def top_centre(name):
        layer = p.layer(name)
        return [layer["x"] + layer["width"] / 2, layer["y"]]
    bones = {}
    for side in ("left", "right"):
        bones[f"{side}-upper-arm"] = {"origin": top_centre(f"bot-{side}-upper-arm"), "length": 85, "limits": [-170, 170]}
        bones[f"{side}-lower-arm"] = {"parent": f"{side}-upper-arm", "length": 82, "limits": [-150, 150]}
        bones[f"{side}-hand"] = {"parent": f"{side}-lower-arm", "length": 52, "limits": [-70, 70]}
        bones[f"{side}-upper-leg"] = {"origin": top_centre(f"bot-{side}-upper-leg"), "length": 65, "limits": [-100, 100]}
        bones[f"{side}-lower-leg"] = {"parent": f"{side}-upper-leg", "length": 63, "limits": [-150, 150]}
        bones[f"{side}-foot"] = {"parent": f"{side}-lower-leg", "length": 36, "limits": [-70, 70]}
    return bones


def bake_pose_keys(p, char, samples):
    """There is no keyframed pose: pose the rig at each sample on the document, read the solved
    x/y/rotation of the arm parts, then write them as keys and restore the rest pose."""
    keys = []
    for t, angles in samples:
        p.apply([{"type": "character-pose", "target": char, "angles": angles}])
        for part in ("right-upper-arm", "right-lower-arm", "right-hand"):
            layer = p.inspect(f"bot-{part}")
            keys.append((t, f"bot-{part}", layer))
    p.apply([{"type": "character-pose", "target": char,
              "angles": {"right-upper-arm": 0, "right-lower-arm": 0, "right-hand": 0}}])
    return keys


def robot():
    W = H = 1080
    DUR, FPS = 7000, 30
    p = Project(W, H, NIGHT)
    install_font(p, "Space Grotesk", 700, role="heading")
    install_font(p, "Inter", 500, role="body")
    ops, parts = robot_parts("bot")
    apply(p, [
        {"type": "gradient", "name": "spot", "direction": "radial", "start": "#25307A", "end": NIGHT,
         "falloff": "smooth", "x": 40, "y": 160, "width": 1000, "height": 1000},
        {"type": "gradient", "name": "floor", "direction": "vertical", "start": NIGHT, "end": "#18204A",
         "x": 0, "y": 800, "width": W, "height": 280},
        {"type": "shape", "name": "shadow", "shape": "ellipse", "x": 330, "y": 878, "width": 420, "height": 56,
         "fill": "#05081A", "opacity": 0.55},
    ] + ops)
    apply(p, [{"type": "character", "name": "bot", "parts": parts, "x": 330, "y": 300}])
    apply(p, [{"type": "character-rig", "target": "bot", "bones": robot_bones(p)}])
    # character-rig resets every bone's pivot to its top centre; tuck the hands onto the wrists instead
    apply(p, [{"type": "pivot", "targets": ["bot-left-hand", "bot-right-hand"], "value": [0.5, 0.3]},
              {"type": "character-pose", "target": "bot", "angles": {}}])
    apply(p, [{"type": "group", "name": "scene-bot", "targets": ["shadow", "bot"]}])
    apply(p, [{"type": "pivot", "target": "scene-bot", "value": "bottom"}])

    T_WALK0, T_WALK1 = 300, 3500
    apply(p, [
        {"type": "timeline-set", "duration": DUR, "fps": FPS, "loop": 0},
        {"type": "marker", "name": "arrive", "time": T_WALK1},
        {"type": "marker", "name": "wave", "time": 3900},
        {"type": "character-cycle", "target": "bot", "cycle": "walk", "view": "front", "start": T_WALK0,
         "duration": T_WALK1 - T_WALK0, "period": 800, "amount": 40},
    ])
    # The walk comes toward us: scale up from far away; ease out as it arrives
    apply(p, [
        {"type": "keyframe", "target": "scene-bot", "property": "scale", "time": 0, "value": 0.62, "easing": "hold"},
        {"type": "keyframe", "target": "scene-bot", "property": "scale", "time": T_WALK0, "value": 0.62, "easing": "ease-in-out-sine"},
        {"type": "keyframe", "target": "scene-bot", "property": "scale", "time": T_WALK1, "value": 1.0},
        {"type": "keyframe", "target": "scene-bot", "property": "translate-y", "time": T_WALK0, "value": -110, "easing": "ease-in-out-sine"},
        {"type": "keyframe", "target": "scene-bot", "property": "translate-y", "time": T_WALK1, "value": 0},
    ])
    # Wave: raise the right arm, wag the forearm three times, lower it. A pose is baked into separate
    # x/y/rotation keys per part, and those interpolate independently (the hand slides along the chord, off
    # the wrist), so sample every frame.
    def wave_angles(t):
        t0, up, wag, down = 3900, 380, 1350, 450
        def smooth(u):
            u = max(0.0, min(1.0, u))
            return u * u * (3 - 2 * u)
        if t < t0 + up + wag:
            lift = smooth((t - t0) / up)
        else:
            lift = 1 - smooth((t - t0 - up - wag) / down)
        w = math.sin(2 * math.pi * 3 * max(0.0, t - t0 - up) / wag) if t0 + up <= t <= t0 + up + wag else 0
        return {"right-upper-arm": 145 * lift + 4 * w * lift, "right-lower-arm": (10 - 28 * w) * lift,
                "right-hand": -12 * w * lift}
    step = 1000 / FPS
    samples = [(round(3900 + i * step), wave_angles(3900 + i * step)) for i in range(int((380 + 1350 + 450) / step) + 2)]
    key_ops = []
    for tt, name, layer in bake_pose_keys(p, "bot", samples):
        for prop in ("x", "y", "rotation"):
            key_ops.append({"type": "keyframe", "target": name, "property": prop, "time": tt, "value": layer[prop],
                            "easing": "linear"})
    apply(p, key_ops)
    # Life: blinking eyes, antenna light pulse, heart glow
    apply(p, [
        {"type": "pivot", "targets": ["bot-left-eye", "bot-right-eye"], "value": "center"},
        {"type": "keyframe", "targets": ["bot-left-eye", "bot-right-eye"], "property": "scale-y", "time": 0, "value": 1},
    ] + [
        {"type": "keyframe", "targets": ["bot-left-eye", "bot-right-eye"], "property": "scale-y", "time": tt, "value": v,
         "easing": "ease-in-out-sine"}
        for t0 in (1600, 5900) for tt, v in ((t0, 1), (t0 + 70, 0.1), (t0 + 160, 1))
    ] + [
        {"type": "animate-preset", "target": "bot-antenna-ball", "preset": "pulse", "start": 0, "duration": 700,
         "repeat": 10, "amount": 1.25},
        {"type": "layer-style", "target": "bot-antenna-ball", "name": "outer-glow", "settings": {"color": AMBER, "blur": 18, "opacity": 0.8}},
        {"type": "layer-style", "target": "bot-heart", "name": "outer-glow", "settings": {"color": CORAL, "blur": 14, "opacity": 0.7}},
    ])
    # Speech bubble + caption
    apply(p, [
        {"type": "speech-bubble", "name": "hello", "text": "Hi! I'm an AI helper.\nAsk me anything.", "font": "inter-500",
         "size": 36, "color": ROBOT_DARK, "x": 640, "y": 150, "max_width": 420, "padding": 26, "anchor": "bot-antenna-ball",
         "fill": ROBOT_SHELL},
        {"type": "text", "name": "caption", "text": "Meet your study buddy", "font": "space-grotesk-700", "size": 52,
         "color": PAPER, "x": "center", "y": 960, "align": "center"},
    ])
    apply(p, [
        {"type": "animate-preset", "target": "hello", "preset": "pop-in", "start": 4100, "duration": 450, "close": False},
        {"type": "text-animate", "target": "caption", "preset": "fade-up", "unit": "word", "start": 500, "duration": 600,
         "stagger": 120, "mode": "in"},
    ])
    # loop: fade the whole scene out and back in
    apply(p, [{"type": "group", "name": "all", "targets": ["scene-bot", "hello", "caption"]}] + [
        {"type": "keyframe", "target": "all", "property": "opacity", "time": tt, "value": v, "easing": "ease-in-out-sine"}
        for tt, v in ((0, 0), (300, 1), (6500, 1), (DUR, 0))
    ])
    save(p, "robot-helper.vixl")
    check("robot-helper.vixl", ("motion", "character"))
    timed("robot sheet", sheet, p, "robot-sheet.jpg", count=16, columns=4, max_width=1600)
    if os.environ.get("QUICK"):
        return p
    export(p, "robot-helper.mp4")
    export(p, "robot-helper.gif", scale=0.4, fps=20, poster="5s", dither="none")
    return p


# ================================================================================================
# 4. How a chatbot predicts the next word
# ================================================================================================

def measure_words(words, font_family, weight, font, size):
    m = Project(2000, 400, "#000")
    install_font(m, font_family, weight)
    out = {}
    for i, w in enumerate(words):
        m.apply([{"type": "text", "name": f"m{i}", "text": w, "font": font, "size": size, "x": 0, "y": 0}])
        out[w] = m.inspect(f"m{i}")["width"]
    return out


def nextword():
    W, H = 1920, 1080
    DUR, FPS = 10000, 30
    p = Project(W, H, NIGHT)
    install_font(p, "Space Grotesk", 700, role="heading")
    install_font(p, "Inter", 500, role="body")
    HEAD, BODY = "space-grotesk-700", "inter-500"
    TOK = 72
    prompt = ["The", "cat", "sat", "on", "the"]
    rounds = [
        {"cands": [("mat", 0.62), ("sofa", 0.18), ("floor", 0.11), ("moon", 0.02)], "t": 2000},
        {"cands": [(".", 0.58), ("and", 0.21), ("while", 0.09), ("because", 0.04)], "t": 5600},
    ]
    widths = measure_words(prompt + ["mat", "."], "Space Grotesk", 700, HEAD, TOK)

    ops = [
        {"type": "timeline-set", "duration": DUR, "fps": FPS, "loop": 1},
        {"type": "marker", "name": "round1", "time": rounds[0]["t"]},
        {"type": "marker", "name": "round2", "time": rounds[1]["t"]},
        {"type": "marker", "name": "outro", "time": 8300},
        {"type": "text", "name": "kicker", "text": "HOW A CHATBOT WRITES", "font": BODY, "size": 28, "color": CYAN,
         "x": 120, "y": 110},
        {"type": "text", "name": "title", "text": "It predicts the next word, one at a time", "font": HEAD, "size": 64,
         "color": PAPER, "x": 120, "y": 150},
        {"type": "text", "name": "lbl-prompt", "text": "THE TEXT SO FAR", "font": BODY, "size": 30, "color": MUTED,
         "x": 120, "y": 360},
        {"type": "text", "name": "lbl-probs", "text": "WHAT COULD COME NEXT?", "font": BODY, "size": 30, "color": MUTED,
         "x": 1120, "y": 360},
        {"type": "shape", "name": "divider", "shape": "rectangle", "x": 1040, "y": 360, "width": 3, "height": 500,
         "fill": LINE},
    ]
    # Token chips for the prompt, laid out left to right
    x, y, PADX, CH = 120, 430, 28, 106
    chip_names = []
    for i, w in enumerate(prompt + ["mat", "."]):
        cw = widths[w] + 2 * PADX
        chosen = i >= len(prompt)
        name = f"tok{i}"
        ops += [
            {"type": "shape", "name": f"{name}-chip", "shape": "rounded-rectangle", "x": x, "y": y, "width": cw,
             "height": CH, "radius": 18, "fill": NIGHT_2, "stroke": CYAN if chosen else "#3A4682", "stroke_width": 3},
            {"type": "text", "name": f"{name}-word", "text": w, "font": HEAD, "size": TOK, "color": PAPER,
             "within": f"{name}-chip"},
            {"type": "group", "name": name, "targets": [f"{name}-chip", f"{name}-word"]},
        ]
        chip_names.append((name, x, cw))
        x += cw + 14
        if i == 4:
            x, y = 120, y + CH + 18  # wrap: the predicted words start a second line
    # caret that blinks while the model "thinks"
    ops.append({"type": "shape", "name": "caret", "shape": "rectangle", "x": 120, "y": 430 + CH + 18 + 14,
                "width": 6, "height": CH - 28, "fill": CYAN, "opacity": 0})
    apply(p, ops)

    # Probability rows (the words and numbers change between rounds with text keys)
    BX, BW, ROW0, ROWH = 1120, 540, 430, 112
    ops = []
    for r in range(4):
        y = ROW0 + r * ROWH
        w0, p0 = rounds[0]["cands"][r]
        ops += [
            {"type": "text", "name": f"cand{r}", "text": w0, "font": HEAD, "size": 50, "color": PAPER, "x": BX, "y": y},
            {"type": "shape", "name": f"track{r}", "shape": "rounded-rectangle", "x": BX, "y": y + 68, "width": BW,
             "height": 20, "radius": 10, "fill": "#1C2552"},
            {"type": "shape", "name": f"bar{r}", "shape": "rounded-rectangle", "x": BX, "y": y + 68, "width": BW,
             "height": 20, "radius": 10, "fill": VIOLET if r else CYAN},
            {"type": "text", "name": f"pct{r}", "text": f"{round(p0 * 100)}%", "font": HEAD, "size": 44,
             "color": MUTED, "x": BX + BW + 30, "y": y + 42},
        ]
    apply(p, ops)
    apply(p, [{"type": "pivot", "targets": [f"bar{r}" for r in range(4)], "value": "left"},
              {"type": "top", "targets": ["tok5", "tok6"]}])  # the picked word flies over the rows

    k = []
    def key(target, prop, t, v, e="ease-in-out-cubic"):
        k.append({"type": "keyframe", "target": target, "property": prop, "time": round(t), "value": v, "easing": e})

    # Prompt tokens pop in one by one
    tok_ops = [{"type": "animate-preset", "targets": [f"tok{i}" for i in range(5)], "preset": "pop-in",
                "start": 250, "duration": 380, "stagger": 160}]
    # Static copy fades up
    for r_i, rd in enumerate(rounds):
        t = rd["t"]
        # caret blinks while thinking
        key("caret", "opacity", t - 700, 0, "hold")
        for b in range(3):
            key("caret", "opacity", t - 600 + b * 260, 1, "hold")
            key("caret", "opacity", t - 470 + b * 260, 0, "hold")
        for r, (w, prob) in enumerate(rd["cands"]):
            # Text keys hold their first value *before* the first key too, so round 1 needs its own key at 0
            key(f"cand{r}", "text", 0 if r_i == 0 else t - 200, w, "hold")
            key(f"pct{r}", "text", 0 if r_i == 0 else t - 200, f"{round(prob * 100)}%", "hold")
            if r_i:
                key(f"cand{r}", "text", t - 200, w, "hold")
                key(f"pct{r}", "text", t - 200, f"{round(prob * 100)}%", "hold")
            st = t + r * 110
            key(f"bar{r}", "scale-x", st - 1, 0.001, "ease-out-cubic")
            key(f"bar{r}", "scale-x", st + 700, max(prob, 0.012), "hold")
            for target in (f"cand{r}", f"pct{r}"):
                key(target, "opacity", st - 1, 0, "ease-out-cubic")
                key(target, "opacity", st + 400, 1 if r == 0 else 0.75, "hold")
        # the winner is picked: highlight it, then it lands in the text
        pick = t + 1200
        key("pct0", "color", pick - 1, MUTED, "ease-out-cubic")
        key("pct0", "color", pick + 200, CYAN, "hold")
        chip = f"tok{5 + r_i}"
        _, cx, cw = chip_names[5 + r_i]
        # fly from the winning row to its place in the sentence
        dx = BX - cx
        dy = ROW0 - (430 + CH + 18) - 14
        key(chip, "opacity", 0, 0, "hold")
        key(chip, "opacity", pick + 250, 0, "ease-out-cubic")
        key(chip, "opacity", pick + 400, 1, "hold")
        key(chip, "translate-x", pick + 250, dx, "ease-in-out-cubic")
        key(chip, "translate-x", pick + 1150, 0, "hold")
        key(chip, "translate-y", pick + 250, dy, "ease-in-out-cubic")
        key(chip, "translate-y", pick + 1150, 0, "hold")
        key(chip, "scale", pick + 250, 0.8, "ease-out-back")
        key(chip, "scale", pick + 1150, 1, "hold")
        # bars drain away before the next round
        out = pick + 1500
        for r in range(4):
            key(f"bar{r}", "scale-x", out + r * 60, max(rd["cands"][r][1], 0.012), "ease-in-cubic")
            key(f"bar{r}", "scale-x", out + r * 60 + 450, 0.001, "hold")
            for target in (f"cand{r}", f"pct{r}"):
                key(target, "opacity", out + r * 60, 1 if r == 0 else 0.75, "ease-in-cubic")
                key(target, "opacity", out + r * 60 + 350, 0, "hold")
        key("pct0", "color", out + 400, MUTED, "hold")
        if r_i == 0:  # the caret moves to after the new word
            key("caret", "translate-x", out, 0, "hold")
            key("caret", "translate-x", out + 10, cw + 14, "hold")
    for r in range(4):  # start state: bars empty, rows hidden
        key(f"bar{r}", "scale-x", 0, 0.001, "hold")
        key(f"cand{r}", "opacity", 0, 0, "hold")
        key(f"pct{r}", "opacity", 0, 0, "hold")
    key("caret", "opacity", 0, 0, "hold")
    apply(p, tok_ops + k)

    # Outro caption
    apply(p, [
        {"type": "text", "name": "outro", "text": "No lookup, no magic: a very well-trained guess, repeated.",
         "font": BODY, "size": 46, "color": PAPER, "x": 120, "y": 930},
        {"type": "text-animate", "target": "outro", "preset": "fade-up", "unit": "word", "start": "outro",
         "duration": 500, "stagger": 60, "mode": "in"},
        {"type": "text-animate", "target": "lbl-probs", "preset": "fade", "unit": "line", "start": 1500, "duration": 400, "mode": "in"},
    ])
    save(p, "next-word-prediction.vixl")
    check("next-word-prediction.vixl")
    timed("nextword sheet", sheet, p, "next-word-sheet.jpg", count=20, columns=4, max_width=1600)
    if os.environ.get("QUICK"):
        return p
    export(p, "next-word-prediction.mp4")
    return p


# ================================================================================================
# 5. "AI-curious" sticker: seamless loop with spin, wiggle, line-boil and wrapped staggered twinkles
# ================================================================================================

def badge():
    W = H = 800
    DUR, FPS = 2400, 24
    p = Project(W, H, "transparent")
    install_font(p, "Space Grotesk", 700, role="heading")
    HEAD = "space-grotesk-700"
    apply(p, [
        {"type": "timeline-set", "duration": DUR, "fps": FPS, "loop_mode": "seamless"},
        {"type": "shape", "name": "seal", "shape": "seal", "count": 18, "x": 110, "y": 110, "width": 580, "height": 580,
         "fill": AMBER, "stroke": PAPER, "stroke_width": 12},
        {"type": "shape", "name": "disc", "shape": "ellipse", "x": 170, "y": 170, "width": 460, "height": 460,
         "fill": NIGHT},
        {"type": "shape", "name": "ring", "shape": "ellipse", "x": 198, "y": 198, "width": 404, "height": 404,
         "fill": "transparent", "stroke": CYAN, "stroke_width": 7},
        {"type": "text", "name": "ai", "text": "AI", "font": HEAD, "size": 220, "color": PAPER, "x": "center", "y": 245,
         "align": "center", "line_height": 1.0},
        {"type": "text", "name": "curious", "text": "curious", "font": HEAD, "size": 70, "color": CYAN, "x": "center",
         "y": 455, "align": "center", "line_height": 1.0},
    ] + [
        {"type": "shape", "name": f"spark{i}", "shape": "sparkle", "x": x, "y": y, "width": s_, "height": s_, "fill": c}
        for i, (x, y, s_, c) in enumerate([(70, 90, 90, PAPER), (630, 60, 70, CYAN), (650, 600, 100, PAPER),
                                            (60, 610, 60, CORAL)])
    ])
    apply(p, [
        {"type": "group", "name": "word", "targets": ["ai", "curious"]},
        {"type": "layer-style", "target": "seal", "name": "drop-shadow",
         "settings": {"color": "#05081A", "dx": 0, "dy": 14, "blur": 18, "opacity": 0.45}},
        {"type": "pivot", "targets": [f"spark{i}" for i in range(4)], "value": "center"},
    ])
    res = apply(p, [
        # 18-lobed seal turns one lobe per loop: seamless by symmetry
        {"type": "motion", "target": "seal", "recipe": "spin", "symmetry": 18, "turns": 1},
        # the word rocks gently; frequency 0.6/s is rounded to whole cycles in the loop
        {"type": "motion", "target": "word", "recipe": "wiggle", "property": "rotation", "amount": 4, "frequency": 0.6},
        # hand-drawn boil on the ring
        {"type": "motion", "target": "ring", "recipe": "line-boil", "fps": 8, "variants": 3, "strength": "natural"},
        # twinkles: one op, staggered, wrapped around the loop end
        {"type": "animate-preset", "targets": [f"spark{i}" for i in range(4)], "preset": "pulse", "duration": 1200,
         "repeat": 2, "stagger": 300, "amount": 1.6},
    ])
    for n in res.get("normalized", []) or []:
        print("   normalized:", str(n)[:300])
    save(p, "ai-curious-badge.vixl")
    check("ai-curious-badge.vixl")
    timed("badge sheet", sheet, p, "ai-curious-sheet.jpg", count=12, columns=6, max_width=1600)
    if os.environ.get("QUICK"):
        return p
    export(p, "ai-curious-badge.webp", scale=0.4, quality=75)
    export(p, "ai-curious-badge.gif", scale=0.4, background=NIGHT, dither="none")
    return p


def overview():
    """One contact sheet for the packet: three moments from each piece."""
    from PIL import Image, ImageDraw
    from vixl.timeline import render_at
    picks = [("neural-network.vixl", [700, 1500, 3500]), ("kinetic-ask-iterate-verify.vixl", [1000, 2800, 5500]),
             ("robot-helper.vixl", [1500, 3300, 4800]), ("next-word-prediction.vixl", [1200, 3400, 7800]),
             ("ai-curious-badge.vixl", [0, 800, 1600])]
    CELL = 300
    sheet = Image.new("RGB", (CELL * 3 + 40, (CELL + 20) * len(picks) + 20), "#05081A")
    for row, (name, times) in enumerate(picks):
        p = Project.load(str(OUT / name))
        for col, t in enumerate(times):
            frame = render_at(p, t).convert("RGBA")
            bg = Image.new("RGBA", frame.size, NIGHT)
            frame = Image.alpha_composite(bg, frame).convert("RGB")
            frame.thumbnail((CELL, CELL))
            x = 10 + col * (CELL + 10) + (CELL - frame.width) // 2
            y = 10 + row * (CELL + 20) + (CELL - frame.height) // 2
            sheet.paste(frame, (x, y))
    sheet.save(OUT / "contact-sheet.jpg", quality=88)


PIECES = {"neural": neural, "kinetic": kinetic, "robot": robot, "nextword": nextword, "badge": badge, "overview": overview}

if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    wanted = sys.argv[1:] or list(PIECES)
    for key in wanted:
        print(f"== {key}")
        timed(f"{key} total", PIECES[key])
    print(json.dumps(TIMES, indent=1))
