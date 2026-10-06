"""HALO launch film: an 8-second kinetic-typography product launch built with Vixl.

Run from the repo root:  python explorations/03-kinetic-launch/build.py
Everything is written to explorations/03-kinetic-launch/output/.
"""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "output"
os.environ["VIXL_RESOURCES"] = str(HERE / ".state" / "resources.json")
os.environ.setdefault("VIXL_NO_UPDATE", "1")

from vixl import Project  # noqa: E402
from vixl.typefaces import install_font  # noqa: E402
from vixl.timeline import contact_sheet, export_timeline, inspect_timeline, render_at  # noqa: E402

W = H = 1080
FPS = 30

# Palette ---------------------------------------------------------------------------------------
INK = "#0D0A1C"        # night background
INK_2 = "#1B1142"      # background after the reveal
PAPER = "#F4F1EA"      # off-white type
LIME = "#C8FF3D"       # product accent
CORAL = "#FF6A4D"      # secondary accent
LAVENDER = "#B7A6FF"   # tertiary / UI
DIM = "#3A3363"        # tracks and rules

LOG = []


def apply(project, ops, label):
    result = project.apply(ops, detail="compact")
    LOG.append({"step": label, "operations": len(ops) if isinstance(ops, list) else 1,
                "normalized": result.get("normalized", [])})
    return result


def bounds(project, name):
    return project.inspect(name)["bounds"] if "bounds" in project.inspect(name) else None


def layer_bounds(project):
    from vixl.render import resolve_layout

    ids = {layer["id"]: layer["name"] for layer in project.state["layers"]}
    return {ids[k]: v for k, v in resolve_layout(project).items() if k in ids}


def cli(*args, check=True):
    """Run the vixl CLI (some features are exercised through it on purpose)."""
    proc = subprocess.run(["vixl", *args], capture_output=True, text=True)
    if check and proc.returncode != 0:
        raise RuntimeError(f"vixl {' '.join(args)} failed:\n{proc.stdout}\n{proc.stderr}")
    return proc


def build():
    if OUT.exists():
        shutil.rmtree(OUT)
    (OUT / "frames").mkdir(parents=True)
    (HERE / ".state").mkdir(exist_ok=True)

    p = Project(W, H, INK)

    # ---- Type: Bricolage Grotesque 800 (display) + Figtree (body) + DM Mono (UI labels) ------
    fonts = [
        install_font(p, "Bricolage Grotesque", 800, role="heading"),
        install_font(p, "Figtree", 500, role="body"),
        install_font(p, "DM Mono", 500),
    ]
    MONO = "dm-mono-500"

    # ---- Static scaffolding --------------------------------------------------------------------
    apply(p, [
        {"type": "swatch", "name": "lime", "color": LIME},
        {"type": "swatch", "name": "coral", "color": CORAL},
        {"type": "swatch", "name": "paper", "color": PAPER},
        # Soft radial glow behind the product (revealed later).
        {"type": "gradient", "name": "glow", "direction": "radial", "width": 960, "height": 960,
         "x": 60, "y": -100,
         "stops": [{"offset": 0, "color": "#7B5CFF70"}, {"offset": 0.5, "color": "#3B238F30"},
                   {"offset": 1, "color": "#0D0A1C00"}]},
        # Tick bezel: a 90-point star minus a disc (pathfinder subtract) leaves only the ticks.
        {"type": "shape", "shape": "star", "name": "tick-star", "sides": 90, "inner_radius": 0.93,
         "width": 660, "height": 660, "x": 210, "y": 50, "fill": "#B7A6FF80"},
        {"type": "shape", "shape": "ellipse", "name": "tick-hole", "width": 626, "height": 626,
         "x": 227, "y": 67, "fill": "white"},
        {"type": "pathfinder", "name": "ticks", "targets": ["tick-star", "tick-hole"], "mode": "subtract"},
        # The ring itself (centre 540, 380).
        {"type": "shape", "shape": "ellipse", "name": "ring", "width": 560, "height": 560,
         "x": 260, "y": 100, "fill": "transparent", "stroke": LIME, "stroke_width": 26},
        {"type": "layer-style", "target": "ring", "name": "outer-glow",
         "settings": {"color": LIME, "blur": 28, "opacity": 0.55}},
        {"type": "select", "shape": "none"},
        {"type": "effect", "target": "ring", "name": "blur", "amount": 0},
        # A small satellite that orbits on the ring.
        {"type": "shape", "shape": "ellipse", "name": "satellite", "width": 36, "height": 36,
         "x": 522, "y": 95, "fill": CORAL},
        {"type": "layer-style", "target": "satellite", "name": "outer-glow",
         "settings": {"color": CORAL, "blur": 14, "opacity": 0.8}},
        # Pivot the satellite about the ring centre so `rotation` makes it orbit.
        # (px pivots are stored as box fractions limited to +-10, so the dot can't be tiny.)
        {"type": "pivot", "target": "satellite", "value": [18, 285], "units": "px"},
    ], "scaffold")

    # Drifting sparks.
    sparks = [(110, 170, 10, LAVENDER), (930, 230, 14, LIME), (180, 820, 12, CORAL),
              (880, 760, 9, PAPER), (70, 520, 7, LIME), (1000, 520, 11, LAVENDER),
              (620, 980, 8, LAVENDER), (400, 90, 9, CORAL)]
    apply(p, [
        {"type": "shape", "shape": "ellipse", "name": f"spark-{i}", "width": s, "height": s,
         "x": x, "y": y, "fill": c + "C0"}
        for i, (x, y, s, c) in enumerate(sparks)
    ], "sparks")

    # ---- Persistent UI chrome --------------------------------------------------------------------
    apply(p, [
        {"type": "text", "name": "brandmark", "text": "HALO  /  LAUNCH FILM", "font": MONO, "size": 22,
         "color": LAVENDER, "x": 72, "y": 62},
        {"type": "text", "name": "timecode", "text": "T+00.00", "font": MONO, "size": 22,
         "color": LAVENDER, "x": 800, "y": 62},
        {"type": "constrain", "target": "timecode", "constraints": {"right": "canvas.right-72", "top": 62}},
        {"type": "shape", "shape": "rectangle", "name": "track", "width": 936, "height": 4,
         "x": 72, "y": 1012, "fill": DIM},
        {"type": "shape", "shape": "rectangle", "name": "progress", "width": 936, "height": 4,
         "x": 72, "y": 1012, "fill": LIME},
        {"type": "pivot", "target": "progress", "value": "left"},
    ], "chrome")

    # ---- Scene A: three words --------------------------------------------------------------------
    words = [("SLEEP.", PAPER), ("MOVE.", LIME), ("RECOVER.", CORAL)]
    ops = [{"type": "text", "name": "kicker", "text": "01 — ONE RING TRACKS IT ALL", "font": MONO,
            "size": 26, "color": LAVENDER, "x": 78, "y": 236}]
    for i, (word, colour) in enumerate(words):
        ops.append({"type": "text", "name": f"word-{i}", "text": word, "font": "heading", "size": 196,
                    "color": colour, "x": 66, "y": 300 + i * 176})
    ops += [
        {"type": "shape", "shape": "rectangle", "name": "sweep", "width": 520, "height": 10,
         "x": 78, "y": 868, "fill": LIME},
        {"type": "pivot", "target": "sweep", "value": "left"},
    ]
    apply(p, ops, "scene A")

    # ---- Scene B: HALO, letter by letter ----------------------------------------------------------
    word, size = "HALO", 156
    probe = []
    for i in range(1, len(word) + 1):
        probe.append({"type": "text", "name": f"probe-{i}", "text": word[:i], "font": "heading",
                      "size": size, "x": 0, "y": 0})
    apply(p, probe, "measure")
    lb = layer_bounds(p)
    widths = [lb[f"probe-{i}"][2] for i in range(1, len(word) + 1)]
    total = widths[-1]
    x0 = (W - total) // 2
    letter_y = 380 - lb[f"probe-{len(word)}"][3] // 2
    apply(p, [{"type": "remove", "target": f"probe-{i}"} for i in range(1, len(word) + 1)], "measure cleanup")
    ops = []
    for i, ch in enumerate(word):
        offset = 0 if i == 0 else widths[i - 1]
        ops.append({"type": "text", "name": f"letter-{ch}", "text": ch, "font": "heading", "size": size,
                    "color": PAPER, "x": x0 + offset, "y": letter_y})
    ops += [
        {"type": "layer-style", "target": "letter-O", "name": "color-overlay", "settings": {"color": LIME}},
        # The letters share a group so one blur effect covers the whole word.
        {"type": "group", "name": "wordmark", "targets": [f"letter-{c}" for c in word]},
        {"type": "select", "shape": "none"},
        {"type": "effect", "target": "wordmark", "name": "blur", "amount": 0},
        # "GEN 1" badge
        {"type": "shape", "shape": "rounded-rectangle", "name": "badge-bg", "width": 150, "height": 54,
         "radius": 27, "x": 712, "y": 168, "fill": CORAL},
        {"type": "text", "name": "badge-label", "text": "GEN 1", "font": MONO, "size": 26, "color": INK,
         "x": 712, "y": 168},
        {"type": "constrain", "target": "badge-label",
         "constraints": {"center-x": "badge-bg.center-x", "center-y": "badge-bg.center-y"}},
        {"type": "group", "name": "badge", "targets": ["badge-bg", "badge-label"]},
    ]
    apply(p, ops, "scene B")

    # ---- Scene C: tagline, spec chips, CTA (constrained layout) ------------------------------------
    apply(p, [
        {"type": "text", "name": "tagline", "text": "Your whole day, in one ring.", "font": "body",
         "size": 44, "color": PAPER, "x": 0, "y": 0},
        # The tagline hangs off the ring; chips and CTA chain off the tagline/canvas.
        {"type": "constrain", "target": "tagline",
         "constraints": {"center-x": "canvas.center-x", "top": "ring.bottom+46"}},
    ], "tagline")

    chips = ["7-DAY BATTERY", "TITANIUM", "2.4 G"]
    ops, chip_w = [], []
    for i, label in enumerate(chips):
        ops.append({"type": "text", "name": f"chip-label-{i}", "text": label, "font": MONO, "size": 24,
                    "color": PAPER, "x": 0, "y": 0})
    apply(p, ops, "chip labels")
    lb = layer_bounds(p)
    chip_w = [lb[f"chip-label-{i}"][2] + 56 for i in range(len(chips))]
    gap = 18
    row = sum(chip_w) + gap * (len(chips) - 1)
    cx, chip_y = (W - row) // 2, 0
    ops = []
    for i, w in enumerate(chip_w):
        ops += [
            {"type": "shape", "shape": "rounded-rectangle", "name": f"chip-bg-{i}", "width": w, "height": 50,
             "radius": 25, "x": cx, "y": chip_y, "fill": "#FFFFFF10", "stroke": LAVENDER, "stroke_width": 2},
            {"type": "constrain", "target": f"chip-bg-{i}",
             "constraints": {"left": cx, "top": "tagline.bottom+30"}},
            {"type": "constrain", "target": f"chip-label-{i}",
             "constraints": {"center-x": f"chip-bg-{i}.center-x", "center-y": f"chip-bg-{i}.center-y"}},
        ]
        cx += w + gap
    ops += [{"type": "raise", "target": f"chip-label-{i}"} for i in range(len(chips))]
    for i in range(len(chips)):
        ops.append({"type": "group", "name": f"chip-{i}", "targets": [f"chip-bg-{i}", f"chip-label-{i}"]})
    apply(p, ops, "chips")

    apply(p, [
        {"type": "shape", "shape": "rounded-rectangle", "name": "cta-pill", "width": 460, "height": 84,
         "radius": 42, "x": 305, "y": 870, "fill": LIME},
        {"type": "text", "name": "cta-label", "text": "PRE-ORDER  ·  10.24", "font": "heading", "size": 34,
         "color": INK, "x": 0, "y": 0},
        {"type": "constrain", "target": "cta-pill",
         "constraints": {"center-x": "canvas.center-x", "bottom": "canvas.bottom-100"}},
        {"type": "constrain", "target": "cta-label",
         "constraints": {"center-x": "cta-pill.center-x", "center-y": "cta-pill.center-y"}},
    ], "cta")

    # Finishing adjustment layer: vignette over everything (animated vignette strength).
    apply(p, [
        {"type": "adjustment", "name": "finish", "effects": [
            {"name": "vignette", "strength": 0.35, "radius": 0.9}]},
    ], "finish")

    # ============================================================================================
    # TIMELINE
    # ============================================================================================
    D = 8000
    apply(p, [
        {"type": "timeline-set", "duration": D, "fps": FPS, "loop": 0},
        {"type": "marker", "name": "words", "time": "300ms"},
        {"type": "marker", "name": "words-out", "time": "1.85s"},
        {"type": "marker", "name": "reveal", "time": "2.2s"},
        {"type": "marker", "name": "tagline", "time": "4s"},
        {"type": "marker", "name": "specs", "time": "5.1s"},
        {"type": "marker", "name": "cta", "time": "5.9s"},
        {"type": "marker", "name": "hero", "time": "90%"},
    ], "timeline + markers")

    # -- reusable motion recipes (production workflow) --
    apply(p, [
        {"type": "role-set", "name": "words", "targets": [f"word-{i}" for i in range(3)]},
        {"type": "role-set", "name": "letters", "targets": [f"letter-{c}" for c in word]},
        {"type": "role-set", "name": "chips", "targets": [f"chip-{i}" for i in range(3)]},
        {"type": "role-set", "name": "sparks", "targets": [f"spark-{i}" for i in range(len(sparks))]},
        # Staggered rise-in, short hold, staggered exit upwards.
        {"type": "motion-define", "name": "rise-and-leave", "motion": {
            "description": "Stacked words rise in one after another, hold, then leave upwards.",
            "steps": [
                {"id": "in", "role": "words", "preset": "slide-in-up", "distance": 150,
                 "duration": "650ms", "stagger": "170ms", "easing": "ease-out-expo"},
                {"id": "out", "role": "words", "preset": "slide-out-up", "distance": 170,
                 "duration": "380ms", "stagger": "90ms", "easing": "ease-in-back", "after": "in",
                 "start": "420ms"},
            ]}},
        # Letters drop from above with a spring and fade in.
        {"type": "motion-define", "name": "drop-in", "motion": {
            "steps": [
                {"role": "letters", "property": "translate-y", "from": -300, "to": 0,
                 "duration": "1000ms", "stagger": "95ms", "easing": "spring"},
                {"role": "letters", "preset": "fade-in", "duration": "260ms", "stagger": "95ms"},
            ]}},
        # Chips pop with a back easing.
        {"type": "motion-define", "name": "pop-row", "motion": {
            "steps": [{"role": "chips", "preset": "pop-in", "duration": "480ms", "stagger": "130ms",
                       "easing": "ease-out-back"}]}},
        # Sparks drift.
        {"type": "motion-define", "name": "drift", "motion": {
            "steps": [{"role": "sparks", "preset": "float", "amount": 22, "duration": "2600ms",
                       "stagger": "210ms"}]}},
        {"type": "motion-apply", "name": "rise-and-leave", "start": "words"},
        {"type": "motion-apply", "name": "drop-in", "start": "reveal"},
        {"type": "motion-apply", "name": "pop-row", "start": "specs"},
        {"type": "motion-apply", "name": "drift", "start": 0},
        {"type": "motion-apply", "name": "drift", "start": "2.6s", "speed": 1.3},
        {"type": "motion-apply", "name": "drift", "start": "5.2s", "speed": 1.6},
    ], "motion recipes")

    ops = [
        # Canvas background shifts colour at the reveal, and drifts back for the end card.
        {"type": "animate-preset", "target": "canvas", "preset": "color-shift", "to": INK_2,
         "start": "reveal", "duration": "1.6s"},
        {"type": "keyframe", "target": "canvas", "property": "background", "time": "hero", "value": "#160E36"},
        # Kicker typewriter and fade.
        {"type": "animate-preset", "target": "kicker", "preset": "typewriter", "start": "100ms",
         "duration": "900ms"},
        {"type": "animate-preset", "target": "kicker", "preset": "fade-out", "start": "words-out",
         "duration": "300ms"},
        # Sweep underline: wipes in with a custom bezier, wipes out with steps.
        {"type": "keyframe", "target": "sweep", "property": "scale-x", "time": 0, "value": 0},
        {"type": "keyframe", "target": "sweep", "property": "scale-x", "time": "700ms", "value": 0,
         "easing": "cubic-bezier(0.8, 0, 0.1, 1)"},
        {"type": "keyframe", "target": "sweep", "property": "scale-x", "time": "1.5s", "value": 1,
         "easing": "steps(6)"},
        {"type": "keyframe", "target": "sweep", "property": "scale-x", "time": "2.1s", "value": 0},
        {"type": "animate", "target": "sweep", "property": "fill", "from": LIME, "to": CORAL,
         "start": "1.2s", "duration": "600ms", "easing": "ease-in-out-sine"},
        # Word 2 changes colour while holding; word 3 gets a letter-spacing squeeze via `size`.
        {"type": "animate", "target": "word-1", "property": "color", "to": LAVENDER, "start": "1.3s",
         "duration": "400ms"},
        {"type": "animate", "target": "word-2", "property": "size", "from": 150, "to": 196,
         "start": "640ms", "duration": "700ms", "easing": "ease-out-quart"},
        # --- reveal ---
        {"type": "animate", "target": "glow", "property": "opacity", "from": 0, "to": 1, "start": "reveal",
         "duration": "1.2s", "easing": "ease-out-sine"},
        {"type": "animate-preset", "target": "glow", "preset": "pulse", "start": "4.4s",
         "duration": "1.8s", "amount": 1.08},
        {"type": "animate-preset", "target": "ring", "preset": "fade-in", "start": "reveal", "duration": "250ms"},
        {"type": "animate", "target": "ring", "property": "scale", "from": 0, "to": 1, "start": "reveal",
         "duration": "1.4s", "easing": "elastic-out"},
        {"type": "animate", "target": "ring", "property": "effect:1", "from": 40, "to": 0,
         "start": "reveal", "duration": "900ms", "easing": "ease-out-cubic"},
        {"type": "animate", "target": "ring", "property": "stroke", "to": LAVENDER, "start": "hero",
         "duration": "700ms"},
        {"type": "animate-preset", "target": "ticks", "preset": "fade-in", "start": "2.7s",
         "duration": "800ms"},
        {"type": "animate-preset", "target": "ticks", "preset": "spin", "start": "2.7s", "duration": "5.3s",
         "amount": 0.25},
        {"type": "animate-preset", "target": "satellite", "preset": "fade-in", "start": "3.3s",
         "duration": "400ms"},
        {"type": "animate", "target": "satellite", "property": "rotation", "from": -40, "to": 500,
         "start": "3.3s", "end": D, "easing": "cubic-bezier(0.3, 0.1, 0.25, 1)"},
        # Wordmark: blur in (group effect amount).
        {"type": "keyframe", "target": "wordmark", "property": "effect:1",
         "time": "reveal", "value": 22, "easing": "ease-out-quad"},
        {"type": "keyframe", "target": "wordmark", "property": "effect:1", "time": "3.5s", "value": 0},
        # Spec labels flash lime together (same keys on several layers via `targets`).
        {"type": "keyframe", "targets": [f"chip-label-{i}" for i in range(3)], "property": "color",
         "time": "6.3s", "value": PAPER, "easing": "ease-out"},
        {"type": "keyframe", "targets": [f"chip-label-{i}" for i in range(3)], "property": "color",
         "time": "6.6s", "value": LIME, "easing": "ease-in"},
        {"type": "keyframe", "targets": [f"chip-label-{i}" for i in range(3)], "property": "color",
         "time": "7.1s", "value": PAPER},
        # Badge: pop with a spring, snap tilt with `hold`, then bounce.
        {"type": "animate-preset", "target": "badge", "preset": "pop-in", "start": "3.5s",
         "duration": "700ms", "easing": "spring"},
        {"type": "keyframe", "target": "badge", "property": "rotation", "time": "3.5s", "value": 0,
         "easing": "hold"},
        {"type": "keyframe", "target": "badge", "property": "rotation", "time": "4.1s", "value": -9},
        {"type": "animate-preset", "target": "badge", "preset": "bounce", "start": "6.7s",
         "duration": "800ms", "amount": 26},
        # Tagline types on; constrained layer, animated via translate-y.
        {"type": "animate-preset", "target": "tagline", "preset": "typewriter", "start": "tagline",
         "duration": "1.1s"},
        {"type": "animate", "target": "tagline", "property": "translate-y", "from": 24, "to": 0,
         "start": "tagline", "duration": "600ms", "easing": "ease-out-cubic"},
        {"type": "animate-preset", "target": "tagline", "preset": "fade-in", "start": "tagline",
         "duration": "300ms"},
        # Battery counter ticks up (stepped text keys).
        *[{"type": "keyframe", "target": "chip-label-0", "property": "text",
           "time": 5100 + i * 90, "value": f"{i + 1}-DAY BATTERY"} for i in range(7)],
        # CTA: rises with back easing, pulses, changes colour.
        {"type": "animate-preset", "targets": ["cta-pill", "cta-label"], "preset": "slide-in-up",
         "start": "cta", "duration": "750ms", "distance": 140, "easing": "ease-out-back"},
        {"type": "animate-preset", "targets": ["cta-pill", "cta-label"], "preset": "pulse",
         "start": "6.9s", "duration": "600ms", "amount": 1.07},
        {"type": "animate-preset", "target": "cta-pill", "preset": "color-shift", "to": CORAL,
         "start": "hero", "duration": "500ms"},
        # Chrome: stepped progress bar, ticking timecode, closing vignette.
        {"type": "animate", "target": "progress", "property": "scale-x", "from": 0, "to": 1, "start": 0,
         "end": D, "easing": "steps(16)"},
        *[{"type": "keyframe", "target": "timecode", "property": "text", "time": t,
           "value": f"T+{t / 1000:05.2f}"} for t in range(0, D + 1, 250)],
        {"type": "animate", "target": "finish", "property": "effect:1", "from": 0.2, "to": 0.6,
         "start": "hero", "duration": "800ms", "easing": "ease-in-sine"},
    ]
    apply(p, ops, "timeline tracks")

    # Time-sampled check suite for the end card (static `check` only sees the rest frame).
    apply(p, [{"type": "suite-set", "name": "end-card", "suite": {
        "version": 1,
        "sampling": {"mode": "times", "times": ["hero", "7.9s"]},
        "rules": [
            {"id": "cta-inside", "kind": "assert", "expression": "layer.cta-pill.bounds within canvas"},
            {"id": "badge-inside", "kind": "assert", "expression": "layer.badge.bounds within canvas"},
            {"id": "end-contrast", "kind": "design",
             "options": {"checks": ["contrast", "safe_area"], "safe_area": "5%",
                         "targets": ["tagline", "cta-label", "chip-label-0", "chip-label-1", "chip-label-2"]}},
        ]}}], "suite")
    return p


def main():
    p = build()

    # ---- Save the document (with its whole timeline) ----------------------------------------------
    doc = OUT / "halo-launch.vixl"
    p.save(doc)

    info = inspect_timeline(p)
    (OUT / "timeline.json").write_text(json.dumps(info, indent=1))
    print(f"timeline: {info['duration']} ms, {info['frames']} frames, {len(info['tracks'])} tracks")

    # ---- Previews ---------------------------------------------------------------------------------
    contact_sheet(p, count=int(os.environ.get("SHEET", 16)), columns=4, max_width=1600).convert("RGB").save(OUT / "contact-sheet.jpg", quality=86)
    contact_sheet(p, times=["words", "1.2s", "words-out", "reveal", "3s", "tagline", "specs", "cta", "hero"],
                  columns=3, max_width=1200).convert("RGB").save(OUT / "contact-markers.jpg", quality=86)
    for name, t in [("still-words", "1.4s"), ("still-reveal", "3.4s"), ("still-end", "7.6s")]:
        render_at(p, t).convert("RGB").save(OUT / "frames" / f"{name}.jpg", quality=90)

    # CLI round-trips on the saved file: inspect, check, validate, marker-based contact sheet.
    cli("-p", str(doc), "timeline-sheet", "--out", str(OUT / "cli-sheet-markers.png"),
        "--times", "reveal", "3.2s", "specs", "hero", "--columns", "4")
    check = cli("-p", str(doc), "check", "--json", check=False)
    (OUT / "check.json").write_text(check.stdout or check.stderr)

    suite = p.check_suite("end-card")
    (OUT / "suite-end-card.json").write_text(json.dumps(suite, indent=1, default=str))
    print("suite end-card:", suite.get("status"), suite.get("summary", ""))
    # Per-moment design checks on render copies (project_at) — the rest frame stacks all scenes.
    from vixl.timeline import project_at
    moments = {}
    for t in ["1.4s", "3.6s", "7.5s"]:
        r = project_at(p, t).check(checks=["contrast", "overlap", "bounds"])
        moments[t] = r
    (OUT / "check-moments.json").write_text(json.dumps(moments, indent=1, default=str))

    if os.environ.get("QUICK"):
        return
    # ---- Exports ----------------------------------------------------------------------------------
    exports = [
        ("halo-launch.mp4", dict(scale=0.75)),
        ("halo-launch.gif", dict(scale=0.4, fps=12, colors=48)),
        ("halo-launch.webp", dict(scale=0.5, fps=15, quality=70)),
        ("halo-reveal-apng.png", dict(scale=0.3, fps=10, start="reveal", end="4.2s")),
        ("halo-sprites.png", dict(format="sheet", scale=0.18, fps=3, columns=8)),
    ]
    sizes = {}
    for name, opts in exports:
        res = export_timeline(p, OUT / name, **opts)
        sizes[name] = (OUT / name).stat().st_size
        print(f"{name}: {sizes[name] / 1024:.0f} KB  {json.dumps({k: v for k, v in res.items() if k in ('frames', 'fps', 'size', 'warnings')})}")
    (OUT / "build-log.json").write_text(json.dumps({"steps": LOG, "sizes": sizes}, indent=1))


if __name__ == "__main__":
    sys.exit(main())
