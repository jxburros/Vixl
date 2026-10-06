"""FORTY-THREE: a 13-second animated short (picture and sound) made only with Vixl 0.20.0.

Run from the repo root:

    python explorations/13-forty-three-film/build.py            # build, preview, export, review
    python explorations/13-forty-three-film/build.py --draft    # quick draft-quality film only

The sequel to the 12-lamplighter-comic pages. Wren is authored once in a cast document,
saved as a reusable character, and loaded into each shot. The shots use the 0.20 motion
and film tools:

* shot A, the quay: depth-based parallax planes, camera choreography, a walk cycle, lamps that
  light as Wren passes (compact keyframe arrays), a sweeping lighthouse beam, deterministic dust;
* shot B, the storm: an animated wave distortion (distort:phase), compact-keyframe rain and
  lightning flashes, a rocking boat (motion recipes), camera shake, sparks;
* shot C, the lens room: viseme lip-sync, a speech bubble that follows Wren's head, breathing and
  blinking, crawling dashed lens rings (dash_offset), cut-paper texture at a 12 fps cadence,
  point lighting, a vignette and a rack focus.

The film spec joins the shots with crossfades, typewriter/fade captions and a synthesized
score (piano, bells, wind, thunder, rain). The script previews frames and a loop before the
full render, then reviews the export with video sampling and audio analysis.

Outputs go to explorations/13-forty-three-film/output/.
"""

import json
import os
import random
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OUT = HERE / "output"
SHOTS = OUT / "shots"
os.environ.setdefault("VIXL_NO_UPDATE", "1")
os.chdir(ROOT)
sys.path.insert(0, str(ROOT / "src"))

from vixl import Project  # noqa: E402
from vixl.audio import export_audio  # noqa: E402
from vixl.checks import check_design  # noqa: E402
from vixl.film import export as export_film, preview as preview_film  # noqa: E402
from vixl.media_analysis import audio_analyze, video_sample  # noqa: E402
from vixl.natural_guidance import natural_palette  # noqa: E402
from vixl.timeline import contact_sheet  # noqa: E402
from vixl.typefaces import install_font  # noqa: E402

W, H, FPS = 960, 540, 24
INK = "#15171C"
WARM = "#FFE7A3"
FLAME = "#FFB547"
GOLD = "#F6C453"
SKY = natural_palette("sky", "dusk")["colors"]
NIGHT = natural_palette("sky", "night")["colors"]
WATER = natural_palette("water", "night")["colors"]

SHOT_A, SHOT_B, SHOT_C = 4800, 4000, 5200
FADE = 500


def shape(kind, name, x, y, w, h, **kw):
    return {"type": "shape", "shape": kind, "name": name, "x": x, "y": y, "width": w, "height": h, **kw}


def rel(path):
    return str(Path(path).resolve().relative_to(ROOT))


# Cast ------------------------------------------------------------------------------------------------
def build_cast():
    """Wren, authored once: a standard-parts character with a widened right shoulder for reaching."""
    p = Project(400, 400, "transparent")
    p.apply({"type": "character", "name": "wren", "x": 100, "y": 40, "height": 320,
             "colors": {"outfit": "#2F4A3A", "skin": "#C99A74", "hair": "#1F2B3A"}}, detail="brief")
    bones = p.layer("wren")["character"]["bones"]
    p.apply([{"type": "character-rig", "target": "wren", "bones": {
        "right-upper-arm": {"origin": bones["right-upper-arm"]["origin"], "length": bones["right-upper-arm"]["length"],
                            "limits": [-185, 185]},
        "right-lower-arm": {"parent": "right-upper-arm", "length": bones["right-lower-arm"]["length"],
                            "limits": [-150, 150]},
        "right-hand": {"parent": "right-lower-arm", "length": bones["right-hand"]["length"], "limits": [-70, 70]}}},
        {"type": "character-save", "target": "wren", "name": "wren"}], detail="brief")
    path = SHOTS / "cast.vixl"
    p.save(path)
    return rel(path)


def load_wren(cast, x, y, scale, name="wren"):
    return {"type": "character-load", "name": name, "source": cast, "template": "wren", "x": x, "y": y,
            "scale": scale}


# Shot A: the quay --------------------------------------------------------------------------------------
LAMPS_X = [380, 640, 900, 1160]  # world x on the near plane
WALK = (240, 1240)  # wren's x from 0 ms to SHOT_A


def lit_time(x):
    """When Wren's walk reaches a lamp."""
    return round((x - 60 - WALK[0]) / (WALK[1] - WALK[0]) * SHOT_A)


def lamp(name, x, base, height):
    s = height / 300
    lw, lh = 44 * s, 60 * s
    lx, ly = x - lw / 2, base - height
    return [
        shape("rectangle", f"{name}-post", x - 5 * s, ly + lh, 10 * s, height - lh, fill=INK),
        shape("isosceles-triangle", f"{name}-cap", lx - 6 * s, ly - 18 * s, lw + 12 * s, 20 * s, fill=INK),
        shape("ellipse", f"{name}-glow", x - 80 * s, ly - 50 * s, 160 * s, 160 * s, fill="#FFC85A55"),
        {"type": "look", "target": f"{name}-glow", "look": "glow", "color": WARM, "amount": 0.8},
        shape("notched-rectangle", f"{name}-dark", lx, ly, lw, lh, fill="#4A5068", stroke=INK, stroke_width=3,
              notch=6 * s),
        shape("notched-rectangle", f"{name}-lit", lx, ly, lw, lh, fill=WARM, stroke=INK, stroke_width=3,
              notch=6 * s),
        shape("flame", f"{name}-flame", x - 9 * s, ly + 14 * s, 18 * s, 32 * s, fill=FLAME),
    ]


def build_shot_a(cast):
    p = Project(W, H, "#20294A")
    install_font(p, "Bangers", 400)
    world = W + 520  # wide enough for the pan
    ops = [
        # Far plane (depth 6): sky and a headland lighthouse with a sweeping beam.
        {"type": "gradient", "name": "sky", "width": world, "height": H, "direction": "vertical", "x": -40,
         "stops": [{"offset": 0, "color": NIGHT[0]}, {"offset": 0.5, "color": SKY[1]},
                   {"offset": 0.8, "color": SKY[3]}, {"offset": 1, "color": SKY[4]}]},
        shape("crescent", "moon", 120, 60, 70, 70, fill="#FFF3C8"),
        shape("ellipse", "headland", 520, 300, 700, 120, fill="#28304D"),
        shape("rectangle", "far-tower", 900, 236, 20, 80, fill="#E9E4D4"),
        shape("rectangle", "far-beam", 910, 228, 420, 22, fill="#FFE7A3AA"),
        {"type": "distort", "target": "far-beam", "kind": "corner-pin",
         "corners": [[0, 9], [420, 0], [420, 22], [0, 13]]},
        {"type": "pivot", "target": "far-beam", "value": [0, 0.5]},
        {"type": "keyframes", "target": "far-beam", "property": "rotation",
         "keys": [{"time": 0, "value": -14, "easing": "ease-in-out"}, {"time": 2400, "value": 14,
                                                                       "easing": "ease-in-out"},
                  {"time": 4800, "value": -14}]},
        {"type": "group", "name": "far", "targets": ["sky", "moon", "headland", "far-tower", "far-beam"]},
        {"type": "layer-depth", "target": "far", "depth": 6},
        # Mid plane (depth 2.2): the sea and a row of houses.
        shape("rectangle", "sea", -40, 310, world, 60, fill=WATER[1]),
        shape("wave", "sea-wave", -40, 306, world, 10, amplitude=3, wavelength=46, stroke="#9FB3D988",
              stroke_width=2, fill="transparent"),
    ]
    mid = ["sea", "sea-wave"]
    for i in range(7):
        x, hh = 40 + i * 190, 120 + (i * 37) % 60
        ops += [shape("house", f"house-{i}", x, 330 - hh, 120, hh, fill=["#7B3F2F", "#6E4A3A", "#8A5A3C"][i % 3]),
                {"type": "drawn-texture", "target": f"house-{i}", "name": f"house-{i}-hatch", "preset": "hatch",
                 "color": "#1B2440", "seed": 10 + i, "strength": 0.45},
                shape("rounded-rectangle", f"window-{i}", x + 30, 330 - hh * 0.6, 26, 32, fill=WARM,
                      radius=[13, 13, 2, 2])]
        mid += [f"house-{i}", f"house-{i}-hatch", f"window-{i}"]
    ops += [{"type": "group", "name": "mid", "targets": mid}, {"type": "layer-depth", "target": "mid", "depth": 2.2}]
    # Near plane (depth 1): quay, lamps and Wren.
    ops += [shape("rectangle", "quay", -40, 330, world + 200, H - 330, fill="#4C4558"),
            {"type": "pattern-fill", "target": "quay", "name": "cobbles", "pattern": "stone", "scale": 1.1,
             "colors": ["#5D566B", "#3A3446"], "opacity": 0.7, "seed": 3}]
    near = ["quay", "cobbles"]
    for i, x in enumerate(LAMPS_X):
        ops += lamp(f"lamp-{i}", x, 470, 260)
        near += [f"lamp-{i}-{part}" for part in ("post", "cap", "glow", "dark", "lit", "flame")]
    ops += [{"type": "group", "name": "near", "targets": near}, {"type": "layer-depth", "target": "near", "depth": 1}]
    p.apply(ops, detail="brief")
    # Each lamp lights when Wren arrives: compact keyframe arrays on opacity, plus a spark burst.
    lights = []
    for i, x in enumerate(LAMPS_X):
        t = lit_time(x)
        for part in ("glow", "lit", "flame"):
            lights.append({"type": "keyframes", "target": f"lamp-{i}-{part}", "property": "opacity",
                           "keys": [{"time": 0, "value": 0}, {"time": max(0, t), "value": 0},
                                    {"time": t + 160, "value": 1, "easing": "ease-out"}]})
        lights.append({"type": "particles", "name": f"spark-{i}", "preset": "sparks", "count": 10, "x": x,
                       "y": 230, "spread": [30, 10], "life": 700, "start": max(0, t), "duration": 800,
                       "size": 2, "color": GOLD, "seed": 30 + i})
    p.apply(lights, detail="brief")
    # Wren walks the quay: a reusable cycle plus a move across the near plane.
    p.apply([load_wren(cast, WALK[0], 250, 0.66),
             {"type": "character-cycle", "target": "wren", "cycle": "walk", "duration": SHOT_A, "period": 900},
             {"type": "keyframes", "target": "wren", "property": "x",
              "keys": [{"time": 0, "value": WALK[0]}, {"time": SHOT_A, "value": WALK[1]}]},
             {"type": "particles", "name": "dust", "preset": "dust", "count": 24, "x": 700, "y": 260,
              "spread": [1400, 260], "life": 3200, "duration": SHOT_A, "size": 1.5, "color": "#FFF3C8AA",
              "seed": 11},
             # The camera pans with the walk; the far plane barely moves, the near plane moves 1:1.
             {"type": "camera", "from": [0, 0, 1], "to": [520, -10, 1.06], "start": 0, "duration": SHOT_A,
              "easing": "ease-in-out"},
             {"type": "lighting", "ambient": 0.92, "vignette": 0.28, "saturation": 1.05},
             {"type": "timeline-set", "duration": SHOT_A, "fps": FPS}], detail="brief")
    return p


# Shot B: the storm ---------------------------------------------------------------------------------------
FLASHES = [1100, 2700]


def build_shot_b():
    p = Project(W, H, "#0B0E16")
    rng = random.Random(64)
    ops = [
        {"type": "gradient", "name": "sky", "width": W + 80, "height": 340, "x": -40, "y": -20,
         "direction": "vertical", "stops": [{"offset": 0, "color": "#07090F"}, {"offset": 1, "color": "#3C4560"}]},
        shape("cloud", "cloud-1", -60, -40, 460, 220, fill="#2A3245"),
        shape("cloud", "cloud-2", 330, -70, 520, 240, fill="#252C3E"),
        shape("cloud", "cloud-3", 690, -30, 380, 210, fill="#2E3650"),
        *[{"type": "drawn-texture", "target": f"cloud-{i}", "name": f"cloud-{i}-charcoal", "preset": "charcoal",
           "color": "#0B0E16", "seed": 50 + i, "strength": 0.6} for i in (1, 2, 3)],
        shape("lightning", "bolt-1", 400, 60, 60, 230, fill="#F3F0FF"),
        shape("lightning", "bolt-2", 560, 90, 36, 160, fill="#D9D4FF"),
        # Lighthouse, dark until it is relit near the end of the shot.
        shape("rectangle", "tower", 730, 120, 110, 330, fill="#E9E4D4"),
        {"type": "pattern-fill", "target": "tower", "name": "tower-stripes", "pattern": "stripes", "spacing": 56,
         "rotation": 90, "colors": ["#B33A3A", "#00000000"], "opacity": 0.95},
        {"type": "distort", "target": "tower", "kind": "corner-pin",
         "corners": [[18, 0], [92, 0], [110, 330], [0, 330]]},
        shape("rounded-rectangle", "lantern-dark", 742, 60, 86, 64, fill="#3A4258", radius=[30, 30, 0, 0],
              stroke=INK, stroke_width=4),
        shape("rounded-rectangle", "lantern-lit", 742, 60, 86, 64, fill=WARM, radius=[30, 30, 0, 0],
              stroke=INK, stroke_width=4),
        shape("rectangle", "beam", 220, 40, 540, 130, fill="#FFF3B055"),
        {"type": "distort", "target": "beam", "kind": "corner-pin",
         "corners": [[0, 0], [540, 50], [540, 80], [0, 130]]},
        shape("rectangle", "gallery", 732, 122, 106, 10, fill=INK),
        shape("rectangle", "rock", 670, 430, 330, 140, fill="#1E2230"),
    ]
    # Sea bands bent by an animated wave distortion: distort:phase is an ordinary timeline track.
    for i in range(4):
        y = 300 + i * 60
        ops += [shape("rectangle", f"sea-{i}", -60, y, W + 120, 90, fill=WATER[i % 2] if i else "#0F1A33",
                      stroke="#9FB3D9" if i % 2 else "#7F93BD", stroke_width=2),
                {"type": "distort", "target": f"sea-{i}", "kind": "wave", "amount": 0.08 + i * 0.03,
                 "frequency": 3 + i, "phase": 0},
                {"type": "keyframes", "target": f"sea-{i}", "property": "distort:phase",
                 "keys": [{"time": 0, "value": i * 0.8}, {"time": SHOT_B, "value": i * 0.8 + (5 - i) * 2.2}]}]
    ops += [
        # The boat rocks (keyframe array on rotation) and bobs (hover recipe).
        shape("rounded-rectangle", "hull", 190, 330, 120, 40, fill="#5A3B22", radius=[0, 0, 30, 30], stroke=INK,
              stroke_width=3),
        shape("isosceles-triangle", "sail", 226, 230, 48, 104, fill="#E9E4D4", stroke=INK, stroke_width=3),
        {"type": "group", "name": "boat", "targets": ["hull", "sail"]},
        {"type": "pivot", "target": "boat", "value": [0.5, 0.95]},
        {"type": "keyframes", "target": "boat", "property": "rotation",
         "keys": [{"time": t, "value": (-9 if k % 2 else 9), "easing": "ease-in-out"}
                  for k, t in enumerate(range(0, SHOT_B + 1, 700))]},
        {"type": "motion", "target": "boat", "recipe": "hover", "amount": 10, "period": 1400, "duration": SHOT_B},
    ]
    # Lightning: two flashes on a full-frame sheet and the bolts, as compact keyframe arrays.
    flash_keys = [{"time": 0, "value": 0}]
    for t in FLASHES:
        flash_keys += [{"time": t - 1, "value": 0}, {"time": t, "value": 0.85}, {"time": t + 70, "value": 0.15},
                       {"time": t + 130, "value": 0.7}, {"time": t + 420, "value": 0, "easing": "ease-out"}]
    ops += [shape("rectangle", "flash", 0, 0, W, H, fill="#EEF0FF"),
            {"type": "keyframes", "target": "flash", "property": "opacity", "keys": flash_keys},
            {"type": "keyframes", "target": "bolt-1", "property": "opacity", "keys": flash_keys},
            {"type": "keyframes", "target": "bolt-2", "property": "opacity",
             "keys": [{"time": 0, "value": 0}, {"time": FLASHES[1] - 1, "value": 0},
                      {"time": FLASHES[1], "value": 1}, {"time": FLASHES[1] + 420, "value": 0}]}]
    # The lighthouse relights at 3.2 s.
    for target in ("lantern-lit", "beam"):
        ops.append({"type": "keyframes", "target": target, "property": "opacity",
                    "keys": [{"time": 0, "value": 0}, {"time": 3200, "value": 0},
                             {"time": 3500, "value": 1, "easing": "ease-out"}]})
    # Rain: tapered pens in a group that falls 64 px every 220 ms, written as one keyframe array.
    for i in range(160):
        x, y, length = rng.uniform(-60, W + 20), rng.uniform(-80, H), rng.uniform(26, 58)
        ops.append({"type": "pen", "name": f"rain-{i}", "x": x, "y": y, "fill": "transparent",
                    "points": [[0, 0], [length * 0.3, length]], "stroke": "#C9D6F0", "stroke_width": 2,
                    "line_cap": "round", "taper_start": 0.1})
    rain_keys = []
    for t in range(0, SHOT_B + 1, 220):
        rain_keys += [{"time": t, "value": -64}, {"time": min(SHOT_B, t + 219), "value": 0}]
    ops += [{"type": "group", "name": "rain", "targets": [f"rain-{i}" for i in range(160)]},
            {"type": "opacity", "target": "rain", "value": 0.5},
            {"type": "keyframes", "target": "rain", "property": "y", "keys": rain_keys},
            {"type": "particles", "name": "spray", "preset": "bubbles", "count": 18, "x": 300, "y": 380,
             "spread": [500, 60], "velocity": [0, -40], "life": 1200, "duration": SHOT_B, "size": 2,
             "color": "#DCE6FF99", "seed": 5},
            {"type": "camera", "from": [0, 0, 1], "to": [20, 10, 1.1], "duration": SHOT_B, "shake": 5, "seed": 9},
            {"type": "lighting", "ambient": 0.92, "vignette": 0.4, "saturation": 0.9},
            {"type": "timeline-set", "duration": SHOT_B, "fps": FPS}]
    p.apply(ops, detail="brief")
    return p


# Shot C: the lens room ------------------------------------------------------------------------------------
LINE = "Some lights you keep by hand."
LINE_START, LINE_DURATION = 900, 2600


def build_shot_c(cast):
    p = Project(W, H, "#0F1E33")
    install_font(p, "Comic Neue", 700)
    cx, cy = 640, 270
    ops = [shape("sunburst", "burst", cx - 520, cy - 520, 1040, 1040, fill="#FFD27A26", count=36),
           {"type": "keyframes", "target": "burst", "property": "rotation",
            "keys": [{"time": 0, "value": 0}, {"time": SHOT_C, "value": 24}]}]
    rings = []
    for i, (rw, rh) in enumerate([(430, 470), (350, 390), (270, 310), (190, 230), (110, 150)]):
        name = f"ring-{i}"
        ops.append(shape("lens", name, cx - rw / 2, cy - rh / 2, rw, rh, fill="#7FB2FF14",
                         stroke="#E8F1FF" if i % 2 == 0 else "#7FB2FF", stroke_width=4 if i % 2 == 0 else 3,
                         dash=[16, 10] if i % 2 else [60, 14]))
        # Dashes crawl around each ring: dash_offset is a numeric timeline property.
        ops.append({"type": "keyframes", "target": name, "property": "dash_offset",
                    "keys": [{"time": 0, "value": 0}, {"time": SHOT_C, "value": (140 if i % 2 else -90) * (i + 1)}]})
        rings.append(name)
    ops += [shape("flame", "flame", cx - 34, cy - 60, 68, 104, fill=FLAME),
            shape("teardrop", "core", cx - 14, cy - 4, 28, 44, fill="#FFF6D0"),
            {"type": "pivot", "target": "flame", "value": [0.5, 1]},
            {"type": "motion", "target": "flame", "recipe": "wiggle", "property": "rotation", "amount": 5,
             "frequency": 3, "duration": SHOT_C},
            {"type": "group", "name": "lens", "targets": ["burst", *rings, "flame", "core"]},
            {"type": "layer-depth", "target": "lens", "depth": 1.6},
            {"type": "particles", "name": "sparks", "preset": "sparks", "count": 16, "x": cx, "y": cy - 40,
             "spread": [60, 20], "velocity": [0, -60], "gravity": -20, "life": 1500, "duration": SHOT_C, "size": 2,
             "color": GOLD, "seed": 21}]
    p.apply(ops, detail="brief")
    # Wren, larger, in the foreground: lip-sync, a following bubble, breathing and blinking.
    p.apply([load_wren(cast, 150, 60, 1.5),
             {"type": "layer-depth", "target": "wren", "depth": 1},
             {"type": "character-pose", "target": "wren", "angles": {"right-upper-arm": -120,
                                                                      "right-lower-arm": -20}},
             {"type": "motion", "target": "wren", "recipe": "breathing", "amount": 0.015, "period": 2600,
              "duration": SHOT_C},
             {"type": "motion", "target": "wren/left-eye", "recipe": "blink", "duration": SHOT_C, "period": 2200},
             {"type": "motion", "target": "wren/right-eye", "recipe": "blink", "duration": SHOT_C, "period": 2200},
             {"type": "character-lipsync", "target": "wren", "text": LINE, "start": LINE_START,
              "duration": LINE_DURATION},
             {"type": "speech-bubble", "name": "line", "text": LINE, "anchor": "wren/head", "x": 350, "y": 22,
              "font": "comic-neue-700", "size": 28, "max_width": 340, "padding": 18, "fill": "#FFFFFF",
              "stroke": INK},
             {"type": "keyframes", "target": "line", "property": "opacity",
              "keys": [{"time": 0, "value": 0}, {"time": LINE_START - 200, "value": 0},
                       {"time": LINE_START, "value": 1}, {"time": LINE_START + LINE_DURATION + 600, "value": 1},
                       {"time": LINE_START + LINE_DURATION + 900, "value": 0}]},
             # Cut paper on Wren: grain, rough edges, a paper shadow and a held 12 fps cadence.
             {"type": "cut-paper", "targets": ["wren"], "grain": 0.02, "roughness": 0.4, "thickness": 3, "fps": 12,
              "jitter": 0.3, "seed": 17},
             # A warm point light at the flame, and a rack focus from Wren to the lens.
             {"type": "lighting", "ambient": 0.82, "vignette": 0.42,
              "lights": [{"x": cx, "y": cy, "radius": 420, "color": "#FFD9A0", "intensity": 0.5}]},
             {"type": "camera", "from": [0, 0, 1], "to": [30, 0, 1.08], "start": 300, "duration": SHOT_C - 600,
              "focus": 1, "focus_to": 1.6, "aperture": 3},
             {"type": "timeline-set", "duration": SHOT_C, "fps": FPS}], detail="brief")
    return p


# Film ------------------------------------------------------------------------------------------------------
def score():
    """Eight synthesized tracks: piano theme, bells on each lamp, wind, thunder, rain and a final chime."""
    total = SHOT_A + SHOT_B + SHOT_C - 2 * FADE
    b_start = SHOT_A - FADE
    c_start = b_start + SHOT_B - FADE
    theme = [(0, 64), (400, 67), (800, 71), (1200, 69), (1800, 67), (2200, 64), (2600, 62), (3200, 64)]
    piano = [{"start": t, "duration": 380, "midi": m} for t, m in theme]
    piano += [{"start": c_start + 400 + t, "duration": 420, "midi": m - 2} for t, m in theme]
    piano += [{"start": c_start + 3900, "duration": 1200, "midi": 60}, {"start": c_start + 3900, "duration": 1200,
                                                                       "midi": 64}]
    bells = [{"start": max(0, lit_time(x)), "duration": 900, "midi": 84 + i * 2} for i, x in enumerate(LAMPS_X)]
    thunder = [{"start": b_start + t + 120, "duration": 900, "midi": 36} for t in FLASHES]
    return [
        {"name": "piano", "synth": "piano", "notes": piano, "duration": total, "volume": 0.45, "fade_out": 600},
        {"name": "bells", "synth": "bell", "notes": bells, "duration": SHOT_A, "volume": 0.3, "pan": 0.2},
        {"name": "wind", "synth": "whoosh", "start": b_start - 200, "duration": SHOT_B + 400, "volume": 0.35,
         "fade_in": 400, "fade_out": 600},
        {"name": "rain", "synth": "noise", "start": b_start, "duration": SHOT_B, "volume": 0.08, "fade_in": 300,
         "fade_out": 500},
        {"name": "thunder", "synth": "kick", "notes": thunder, "start": 0, "duration": total, "volume": 0.7},
        {"name": "relight", "synth": "bell", "start": b_start + 3250, "duration": 1200, "volume": 0.35,
         "notes": [{"start": 0, "duration": 1200, "midi": 79}]},
        {"name": "chime", "synth": "bell", "start": c_start + LINE_START + LINE_DURATION + 200, "duration": 1500,
         "volume": 0.3, "notes": [{"start": 0, "duration": 1500, "midi": 88}], "fade_out": 800},
    ]


def film_spec(paths, quality="final"):
    b_start = SHOT_A - FADE
    c_start = b_start + SHOT_B - FADE
    return {
        "version": 1, "width": W, "height": H, "fps": FPS, "quality": quality,
        "shots": [
            {"source": paths["a"], "duration": SHOT_A},
            {"source": paths["b"], "duration": SHOT_B, "transition": FADE},
            {"source": paths["c"], "duration": SHOT_C, "transition": FADE},
        ],
        "captions": [
            {"text": "Port Halloran. The night after.", "start": 300, "end": 3200, "animation": "typewriter",
             "x": 40, "y": 470, "size": 30, "font": "comic-neue-700", "color": "#FFF1C2",
             "box": {"color": "#15171CCC", "padding": 12}},
            {"text": "Then the storm took the power.", "start": b_start + 300, "end": b_start + 2400,
             "animation": "fade", "x": 40, "y": 470, "size": 30, "font": "comic-neue-700", "color": "#FFF1C2",
             "box": {"color": "#15171CCC", "padding": 12}},
            {"text": "FORTY-THREE", "start": c_start + 4100, "end": c_start + SHOT_C - 50, "animation": "fade",
             "x": 380, "y": 400, "size": 96, "font": "bangers-400", "color": GOLD,
             "style": {"stroke_color": INK, "stroke_width": 4, "tracking": 2}},
        ],
        "audio": score(),
    }


def main(draft=False):
    if OUT.exists():
        shutil.rmtree(OUT)
    SHOTS.mkdir(parents=True)
    cast = build_cast()
    shots = {"a": build_shot_a(cast), "b": build_shot_b(), "c": build_shot_c(cast)}
    paths = {}
    for key, project in shots.items():
        path = SHOTS / f"shot-{key}.vixl"
        project.save(path)
        paths[key] = rel(path)
        contact_sheet(project, count=8, columns=4, max_width=1600).save(SHOTS / f"shot-{key}-contact.png")
    spec = film_spec(paths, "draft" if draft else "final")
    (OUT / "film.json").write_text(json.dumps(spec, indent=2))
    review = OUT / "review"
    review.mkdir()
    # Preview before the full render: shot middles, both crossfade midpoints and a short loop.
    b_start, c_start = SHOT_A - FADE, SHOT_A + SHOT_B - 2 * FADE
    for label, t in (("a-middle", 2400), ("ab-crossfade", b_start + FADE // 2), ("b-flash", b_start + 2710),
                     ("bc-crossfade", c_start + FADE // 2), ("c-line", c_start + 2000), ("c-title", c_start + 4800)):
        preview_film(spec, str(ROOT), review / f"frame-{label}.png", time=t)
    preview_film(spec, str(ROOT), review / "loop-shot-c.gif", shot=2, loop=0)
    # The film: MP4 with the mixed score, plus the score on its own.
    film = OUT / ("forty-three-draft.mp4" if draft else "forty-three.mp4")
    result = export_film(spec, str(ROOT), film)
    timeline_doc = Project(16, 16, "transparent")
    timeline_doc.apply([{"type": "audio-track", **track} for track in spec["audio"]] +
                       [{"type": "timeline-set", "duration": round(result.get("duration", 13000)) if isinstance(
                           result, dict) else 13000, "fps": FPS}], detail="brief")
    export_audio(timeline_doc, OUT / "forty-three-score.wav")
    # Review the export: a labelled contact sheet of what was rendered, and the score's levels and onsets.
    video_sample(str(film), str(review / "film-contact.png"), interval=1000, width=320)
    events = [lit_time(x) for x in LAMPS_X] + [b_start + t for t in FLASHES]
    audio = audio_analyze(str(film), str(review / "spectrogram.png"), events=events)
    (review / "audio.json").write_text(json.dumps(audio, indent=2, default=str))
    checks = {key: check_design(project, checks=["motion", "character", "captions"])
              for key, project in shots.items()}
    (review / "checks.json").write_text(json.dumps(checks, indent=2, default=str))
    print(json.dumps({"film": rel(film), "export": result if isinstance(result, dict) else str(result),
                      "checks": {k: (v["errors"], v["warnings"]) for k, v in checks.items()},
                      "peak_dbfs": audio.get("peak_dbfs"), "clipping": audio.get("clipping")}, indent=2,
                     default=str)[:3000])


if __name__ == "__main__":
    main(draft="--draft" in sys.argv)
