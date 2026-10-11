"""Third set of logo builds: split-flap board, liquid fill, napkin sketch, beat build with sound,
kaleidoscope and fireworks. Run through build.py, which registers these."""

import math
import random

from build import BLUE, CHARCOAL, LOWER, LOWER_PIXELS, PIXELS, UPPER, UPPER_PIXELS, WORD, centre, finish, layer, load
from build_more import LOGO_LAYERS, ease_in_out_cubic, key, rect, stage, text, tween
from vixl.typefaces import install_font

PALE = "#e6ebf4"
LIGHT_BLUE = "#6a9aff"  # the kit's blue for dark backgrounds


def raster_copy(p, name="Raster"):
    """One flattened raster of the whole logo, for builds that slice or clip it."""
    p.apply([{"type": "duplicate", "target": n, "name": f"R {n}"} for n in LOGO_LAYERS])
    p.apply([{"type": "merge-layers", "targets": [f"R {n}" for n in LOGO_LAYERS], "name": name}])
    return name


# 14. Split-flap: a departures board of tiles clatters through random colours and lands on the logo.
def split_flap():
    p = load()
    rng = random.Random(14)
    raster = raster_copy(p)
    cols, rows = 10, 3
    x0, y0, x1, y1 = 66, 52, 1014, 430
    gap = 5
    tw, th = (x1 - x0 - gap * (cols - 1)) / cols, (y1 - y0 - gap * (rows - 1)) / rows
    junk_colors = [CHARCOAL, BLUE, LIGHT_BLUE, "#c9d2e0", "#ffffff", "#8a93a6"]
    ops = []
    tiles = []
    for r in range(rows):
        for c in range(cols):
            x, y = round(x0 + c * (tw + gap), 1), round(y0 + r * (th + gap), 1)
            name = f"T{r}_{c}"
            tiles.append((name, r, c))
            ops += [rect(f"{name} bg", x, y, tw, th, "#eef1f6", radius=6),
                    {"type": "duplicate", "target": raster, "name": f"{name} slice"},
                    rect(f"{name} junk", x, y, tw, th, CHARCOAL, radius=6),
                    rect(f"{name} split", x, y + th / 2 - 1, tw, 2, "#ffffff", opacity=0.9)]
    p.apply(ops)
    ops = []
    for name, r, c in tiles:
        ops += [{"type": "top", "target": f"{name} bg"}, {"type": "top", "target": f"{name} slice"},
                {"type": "clip", "target": f"{name} slice", "base": f"{name} bg"},
                {"type": "top", "target": f"{name} junk"}, {"type": "top", "target": f"{name} split"},
                {"type": "group", "name": name,
                 "targets": [f"{name} bg", f"{name} slice", f"{name} junk", f"{name} split"]}]
    ops += [{"type": "hide", "target": raster}]
    p.apply(ops)
    ops = [key(n, "opacity", 0, 0, "hold") for n in LOGO_LAYERS]
    flip = 150
    last = 0
    for name, r, c in tiles:
        t = 150 + c * 75 + r * 110 + int(rng.uniform(0, 120))
        flips = 3 + rng.randrange(4)
        ops += [key(f"{name} junk", "opacity", 0, 0, "hold"), key(f"{name} slice", "opacity", 0, 0, "hold"),
                key(name, "scale-y", 0, 1, "hold")]
        for k in range(flips):
            mid = t + flip // 2
            ops += [key(name, "scale-y", t, 1, "ease-in-quad"), key(name, "scale-y", mid, 0.04, "ease-out-quad"),
                    key(name, "scale-y", t + flip, 1, "hold")]
            if k < flips - 1:
                ops += [key(f"{name} junk", "opacity", mid, 1, "hold"),
                        key(f"{name} junk", "fill", mid, rng.choice(junk_colors), "hold")]
            else:
                ops += [key(f"{name} junk", "opacity", mid, 0, "hold"), key(f"{name} slice", "opacity", mid, 1, "hold")]
            t += flip
        last = max(last, t)
    # The board closes up: tiles fade out over the vector logo, so the gaps disappear.
    end = last + 350
    ops += [key(n, "opacity", end, 1, "hold") for n in LOGO_LAYERS]
    ops += [tween(name, "opacity", end, 350, 0, 1, "ease-in-out") for name, *_ in tiles]
    p.apply(ops)
    return finish(p)


# 15. Liquid fill: the V's and the name are empty glass that fills up with sloshing liquid.
def wave_path(width, height, wavelength=120, amp=12):
    d = [f"M0 {amp}"]
    for i in range(int(width / wavelength)):
        x = i * wavelength
        d.append(f"C {x + wavelength / 4} {-amp + amp}, {x + wavelength / 4} {-amp + amp}, {x + wavelength / 2} {amp}")
        d.append(f"S {x + wavelength * 3 / 4} {3 * amp}, {x + wavelength} {amp}")
    d.append(f"L{width} {height} L0 {height} Z")
    return " ".join(d)


def liquid_fill():
    p = load()
    rng = random.Random(15)
    plan = [(LOWER, BLUE, 0, 1700), (UPPER, CHARCOAL, 700, 1700), (WORD, CHARCOAL, 1700, 1500)]
    ops = []
    for part, color, start, dur in plan:
        item = layer(p, part)
        ops += [{"type": "duplicate", "target": part, "name": f"{part} glass"}]
    p.apply(ops)
    ops = []
    for part, color, start, dur in plan:
        item = layer(p, part)
        glass = f"{part} glass"
        ops.append({"type": "text", "target": glass, "color": PALE} if part == WORD else
                   {"type": "shape", "target": glass, "fill": PALE})
        width = item["width"] + 480 + 1080  # room for the surface to travel sideways while it rises
        ops.append({"type": "shape", "shape": "path", "name": f"{part} liquid", "x": item["x"] - 240 - 1080,
                    "y": item["y"] + item["height"] + 4, "width": width, "height": item["height"] + 40,
                    "path": wave_path(width, item["height"] + 40), "fill": color})
        for b in range(6):
            size = rng.choice([6, 8, 10])
            ops.append({"type": "shape", "shape": "ellipse", "name": f"{part} bubble {b}",
                        "x": item["x"] + rng.uniform(0.15, 0.85) * item["width"],
                        "y": item["y"] + item["height"] - 10, "width": size, "height": size, "fill": "#ffffff",
                        "opacity": 0.55})
    p.apply(ops)
    ops = []
    for part, color, start, dur in plan:
        glass = f"{part} glass"
        ops += [{"type": "top", "target": glass}, {"type": "top", "target": f"{part} liquid"},
                {"type": "clip", "target": f"{part} liquid", "base": glass}]
        for b in range(6):
            ops += [{"type": "top", "target": f"{part} bubble {b}"},
                    {"type": "clip", "target": f"{part} bubble {b}", "base": glass}]
    for part in LOGO_LAYERS:
        ops.append({"type": "top", "target": part})
    p.apply(ops)
    ops = [key(n, "opacity", 0, 0, "hold") for n in LOGO_LAYERS]
    end = 0
    for part, color, start, dur in plan:
        item = layer(p, part)
        glass = f"{part} glass"
        ops.append(tween(glass, "opacity", max(0, start - 400), 300, 1, 0, "ease-out"))
        rise = item["height"] + 4 + 30
        ops.append(tween(f"{part} liquid", "translate-y", start, dur, -rise, 0, "ease-in-out-sine"))
        # Slosh: the surface travels sideways one wavelength every 600 ms.
        ops += [key(f"{part} liquid", "translate-x", 0, 0, "linear"),
                key(f"{part} liquid", "translate-x", start + dur + 200, 120 * round((start + dur + 200) / 600))]
        for b in range(6):
            t = start + int(rng.uniform(0.2, 0.7) * dur)
            ops += [tween(f"{part} bubble {b}", "translate-y", t, 700, -item["height"], 0, "ease-in-quad"),
                    key(f"{part} bubble {b}", "opacity", 0, 0, "hold"), key(f"{part} bubble {b}", "opacity", t, 0.55, "hold"),
                    key(f"{part} bubble {b}", "opacity", t + 700, 0, "hold")]
        done = start + dur
        ops += [key(part, "opacity", done, 1, "hold")]
        end = max(end, done)
    # Drops: the six loose pixels drip into place last.
    for i, name in enumerate(UPPER_PIXELS + LOWER_PIXELS):
        t = end - 300 + i * 90
        ops += [key(name, "opacity", t, 1, "hold"),
                tween(name, "translate-y", t, 380, 0, -220, "bounce-out")]
    p.apply(ops)
    return finish(p)


# 16. Napkin sketch: pencil construction lines, a wobbly hand-drawn logo, ink, then a snap to vector.
def sketch():
    p = load()
    install_font(p, "Caveat", 700)
    p.apply([{"type": "canvas", "background": "#f6f1e6"}])
    up, lo = layer(p, UPPER), layer(p, LOWER)
    guides = [("Guide top", (60, up["y"]), (1040, up["y"])), ("Guide mid", (60, lo["y"] + 6), (1040, lo["y"] + 6)),
              ("Guide base", (60, lo["y"] + lo["height"]), (1040, lo["y"] + lo["height"])),
              ("Guide diag", (up["x"] - 20, up["y"] - 20), (lo["x"] + lo["width"] + 20, lo["y"] + lo["height"] + 20))]
    ops = []
    for name, (ax, ay), (bx, by) in guides:
        x, y = min(ax, bx), min(ay, by)
        ops.append({"type": "shape", "shape": "path", "name": name, "x": x, "y": y,
                    "path": f"M{ax - x} {ay - y} L{bx - x} {by - y}", "fill": "none", "stroke": "#8fb3e8",
                    "stroke_width": 1.5})
    for part in (UPPER, LOWER):
        for k in (1, 2):
            ops += [{"type": "duplicate", "target": part, "name": f"{part} pencil {k}"},
                    {"type": "shape", "target": f"{part} pencil {k}", "fill": "none", "stroke": "#4a4a55",
                     "stroke_width": 2.2 if k == 1 else 1.4}]
        ops += [{"type": "duplicate", "target": part, "name": f"{part} ink"}]
    for pix in PIXELS:
        ops += [{"type": "duplicate", "target": pix, "name": f"{pix} ink"}]
    word = layer(p, WORD)
    ops.append(text("Script", "Vixl", word["x"] + 10, word["y"] - 30, 200, "#4a4a55", "caveat-700"))
    p.apply(ops)
    ops = []
    seed = 1
    for name, *_ in guides:
        ops.append({"type": "irregular", "target": name, "seed": seed, "strength": "natural"}); seed += 1
    for part in (UPPER, LOWER):
        for k in (1, 2):
            ops.append({"type": "irregular", "target": f"{part} pencil {k}", "seed": seed, "strength": "natural",
                        "amount": 0.8 if k == 1 else 0.5}); seed += 1
        ops.append({"type": "irregular", "target": f"{part} ink", "seed": seed, "strength": "natural"}); seed += 1
    for pix in PIXELS:
        ops.append({"type": "irregular", "target": f"{pix} ink", "seed": seed, "strength": "rough"}); seed += 1
    p.apply(ops)
    ops = [key(n, "opacity", 0, 0, "hold") for n in LOGO_LAYERS]
    t = 0
    for name, *_ in guides:  # quick ruled guides
        ops += [key(name, "trim_end", 0, 0), tween(name, "trim_end", t, 380, 100, 0, "ease-out-quad")]
        t += 220
    for part, begin in ((UPPER, 900), (LOWER, 1500)):
        for k, lag in ((1, 0), (2, 260)):
            ops.append(tween(f"{part} pencil {k}", "trim_end", begin + lag, 900, 100, 0, "ease-in-out-sine"))
    ops += [key("Script", "opacity", 0, 0, "hold"), key("Script", "opacity", 2400, 1, "hold"),
            {"type": "text-animate", "target": "Script", "preset": "typewriter", "unit": "char", "start": 2400,
             "duration": 500}]
    # Ink: the shapes are filled in, slightly wobbly, like marker on paper.
    ink = 3000
    for i, part in enumerate((UPPER, LOWER)):
        ops += [key(f"{part} ink", "opacity", 0, 0, "hold"),
                tween(f"{part} ink", "opacity", ink + i * 250, 250, 1, 0, "ease-out")]
    for i, pix in enumerate(PIXELS):
        ops += [key(f"{pix} ink", "opacity", 0, 0, "hold"), key(f"{pix} ink", "opacity", ink + 400 + i * 70, 1, "hold")]
    # Snap: everything hand-made gives way to the crisp vector, and the paper turns white.
    snap = 4200
    hand = [n for n, *_ in guides] + [f"{part} pencil {k}" for part in (UPPER, LOWER) for k in (1, 2)]
    hand += [f"{part} ink" for part in (UPPER, LOWER)] + [f"{pix} ink" for pix in PIXELS] + ["Script"]
    ops += [tween(n, "opacity", snap, 260, 0, easing="ease-in") for n in hand]
    ops += [tween(n, "opacity", snap, 200, 1, 0, "ease-out") for n in LOGO_LAYERS]
    ops += [tween("canvas", "background", snap, 400, "#ffffff", "#f6f1e6", "ease-in-out"),
            {"type": "group", "name": "Logo", "targets": LOGO_LAYERS}]
    p.apply(ops)
    p.apply([key("Logo", "scale", snap, 0.97, "ease-out-back"), key("Logo", "scale", snap + 350, 1)])
    return finish(p)


# 17. Beat build: the logo assembles in time to a synthesized 120 bpm beat (the MP4 has the sound).
def beat_build():
    p = load()
    beat = 500
    p.apply([{"type": "group", "name": "Mark", "targets": [UPPER, LOWER] + PIXELS}] +
            [{"type": "shape", "shape": "ellipse", "name": f"Count {i}", "x": 581 + i * 26, "y": 240, "width": 14,
              "height": 14, "fill": "#c9d2e0"} for i in range(2)])
    ops = [key(n, "opacity", 0, 0, "hold") for n in LOGO_LAYERS]
    for i in range(2):  # a metronome for the two-beat count-in: one dot per beat, then they clear
        dot = f"Count {i}"
        ops += [key(dot, "opacity", 0, 0, "hold"), key(dot, "opacity", i * beat, 1, "hold"),
                key(dot, "fill", i * beat, BLUE, "ease-out"), key(dot, "fill", i * beat + 250, "#c9d2e0", "hold"),
                key(dot, "scale", i * beat, 1.5, "ease-out-cubic"), key(dot, "scale", i * beat + 250, 1, "hold"),
                key(dot, "opacity", 2 * beat - 250, 1, "ease-in"), key(dot, "opacity", 2 * beat - 50, 0, "hold")]
    # Two beats of hi-hat count-in, then the parts land on the beat.
    land_up, land_lo = 2 * beat, 3 * beat
    ops += [key(UPPER, "opacity", land_up - 200, 1, "hold"),
            tween(UPPER, "translate-y", land_up - 200, 200, 0, -330, "ease-in-cubic"),
            key(LOWER, "opacity", land_lo - 200, 1, "hold"),
            tween(LOWER, "translate-y", land_lo - 200, 200, 0, 330, "ease-in-cubic")]
    pixel_times = [4 * beat + i * beat // 4 for i in range(3)] + [5 * beat + i * beat // 4 for i in range(3)]
    for name, t in zip(UPPER_PIXELS + LOWER_PIXELS, pixel_times):
        ops += [key(name, "opacity", t, 1, "hold"), key(name, "scale", 0, 0, "hold"),
                key(name, "scale", t, 0, "ease-out-back"), key(name, "scale", t + 160, 1)]
    word_start = 6 * beat
    ops += [key(WORD, "opacity", word_start, 1, "hold"),
            {"type": "text-animate", "target": WORD, "preset": "pop", "unit": "char", "start": word_start - 60,
             "duration": 220, "stagger": beat // 2}]
    final = 8 * beat
    kicks = [land_up, land_lo, 4 * beat, 5 * beat, 6 * beat, 7 * beat, final]
    for t in kicks:  # every kick squashes the mark a little
        ops += [key("Mark", "scale", t, 0.95, "ease-out-cubic"), key("Mark", "scale", t + 180, 1)]
        ops += [key("canvas", "background", t, "#eef3ff", "ease-out"), key("canvas", "background", t + 220, "#ffffff", "hold")]
    ops += [key("canvas", "background", 0, "#ffffff", "hold"),
            key("Mark", "scale", final, 1.08, "ease-out-back"), key("Mark", "scale", final + 400, 1)]
    p.apply(ops)

    def hits(times, midi, dur=120, velocity=1.0):
        return [{"start": t, "duration": dur, "midi": midi, "velocity": velocity} for t in times]
    hats = [i * beat // 2 for i in range(17)]
    word_notes = [60, 64, 67, 72]
    audio = [
        {"type": "audio-track", "name": "hats", "synth": "hihat", "notes": hits(hats, 80, 60, 0.6), "volume": 0.6},
        {"type": "audio-track", "name": "kick", "synth": "kick", "notes": hits(kicks, 36, 250), "volume": 0.6},
        {"type": "audio-track", "name": "snare", "synth": "snare", "notes": hits([land_lo, 7 * beat], 38, 200),
         "volume": 0.5},
        {"type": "audio-track", "name": "bells", "synth": "bell",
         "notes": hits(pixel_times, 0, 300)[:0] + [{"start": t, "duration": 400, "midi": m, "velocity": 0.8}
                                                    for t, m in zip(pixel_times, [84, 88, 91, 79, 76, 72])],
         "volume": 0.35},
        {"type": "audio-track", "name": "piano", "synth": "piano",
         "notes": [{"start": word_start + i * beat // 2, "duration": 400, "midi": m} for i, m in enumerate(word_notes)]
         + [{"start": final, "duration": 1600, "midi": m, "velocity": 0.45} for m in (48, 60, 64, 67, 72)],
         "volume": 0.35, "fade_out": 400},
        {"type": "audio-track", "name": "crash", "synth": "noise", "start": final, "duration": 900,
         "envelope": {"attack": 2, "decay": 600, "sustain": 0.0, "release": 200}, "volume": 0.12},
    ]
    p.apply(audio)
    return finish(p)


# 18. Kaleidoscope: eight copies of the mark spin as a mandala, then fold into one and slide aside.
def kaleidoscope():
    W, H = 1600, 900
    p = stage(W, H, "#ffffff")
    mark = [UPPER, LOWER] + PIXELS
    p.apply([{"type": "group", "name": "Mark 0", "targets": mark}])
    m = layer(p, "Mark 0")
    mx, my = m["x"] + m["width"] / 2, m["y"] + m["height"] / 2
    dx = W / 2 - mx  # the mandala spins in the middle of the frame, then slides to the logo's place
    copies = 8
    p.apply([{"type": "duplicate", "target": "Mark 0", "name": f"Mark {k}"} for k in range(1, copies)])
    p.apply([{"type": "lower", "target": f"Mark {k}"} for k in range(1, copies)] +
            [{"type": "blend", "target": f"Mark {k}", "mode": "multiply"} for k in range(1, copies)])
    fold, slide = 2600, 3100
    ops = []
    for k in range(copies):
        name = f"Mark {k}"
        start = -180 + k * 360 / copies
        ops += [key(name, "rotation", 0, start - 90, "ease-out-cubic"), key(name, "rotation", 900, start, "linear"),
                key(name, "rotation", 1600, start + 60, "ease-in-out-cubic"), key(name, "rotation", fold, 360 if start + 60 > 180 else 0),
                key(name, "scale", 0, 0.1, "ease-out-back"), key(name, "scale", 900, 0.9, "ease-in-out-cubic"),
                key(name, "scale", fold, 1),
                key(name, "translate-x", 0, dx, "hold"), key(name, "translate-x", slide, dx, "ease-in-out-cubic"),
                key(name, "translate-x", slide + 700, 0)]
        if k:
            ops += [key(name, "opacity", 0, 0.9, "hold"), key(name, "opacity", fold - 200, 0.9, "ease-in"),
                    key(name, "opacity", fold + 100, 0)]
    ops += [{"type": "text-animate", "target": WORD, "preset": "slide-left", "unit": "char", "start": slide + 250,
             "duration": 550, "stagger": 70, "distance": 200}]
    p.apply(ops)
    return finish(p)


# 19. Fireworks: rockets climb a night sky and burst; the biggest burst leaves the logo behind.
SPARKS = 36


def fireworks():
    W, H = 1600, 900
    p = stage(W, H, "#0b1020", cy=430)
    recolor = [{"type": "shape", "target": UPPER, "fill": "#ffffff"}, {"type": "shape", "target": LOWER, "fill": LIGHT_BLUE},
               {"type": "text", "target": WORD, "color": "#ffffff"}]
    recolor += [{"type": "shape", "target": n, "fill": "#ffffff"} for n in UPPER_PIXELS]
    recolor += [{"type": "shape", "target": n, "fill": LIGHT_BLUE} for n in LOWER_PIXELS]
    p.apply(recolor)
    rng = random.Random(19)
    mark_c = ((layer(p, UPPER)["x"] + layer(p, LOWER)["x"] + 288) / 2 + 0, (layer(p, UPPER)["y"] + layer(p, LOWER)["y"] + 173) / 2)
    shots = [((360, 260), 300, "#ffd36a"), ((1300, 220), 800, "#ff7ab8"), (mark_c, 1500, LIGHT_BLUE)]
    ops = []
    for i, ((x, y), t, color) in enumerate(shots):
        ops += [rect(f"Rocket {i}", x - 4, y - 4, 8, 14, color, radius=3)]
        for j in range(8):
            ops.append(rect(f"Trail {i}_{j}", x - 2, y - 2, 4, 4, color, opacity=0.8))
        for j in range(SPARKS):
            ops.append(rect(f"Spark {i}_{j}", x - 2.5, y - 2.5, 5, 5, color, radius=2))
        ops.append({"type": "shape", "shape": "ellipse", "name": f"Flash {i}", "x": x - 40, "y": y - 40, "width": 80,
                    "height": 80, "fill": color})
    p.apply(ops)
    ops = [key(n, "opacity", 0, 0, "hold") for n in LOGO_LAYERS]
    for i, ((x, y), t, color) in enumerate(shots):
        climb = 600
        rise = H + 40 - y
        ops += [key(f"Rocket {i}", "opacity", 0, 0, "hold"), key(f"Rocket {i}", "opacity", t, 1, "hold"),
                key(f"Rocket {i}", "opacity", t + climb, 0, "hold"),
                tween(f"Rocket {i}", "translate-y", t, climb, 0, rise, "ease-out-quad"),
                tween(f"Rocket {i}", "translate-x", t, climb, 0, rng.uniform(-60, 60), "ease-out-quad")]
        for j in range(8):  # the trail: sparks dropped along the climb that fade where they fell
            u = j / 8
            tj = t + int(climb * u)
            yj = rise * (1 - u) ** 2
            ops += [key(f"Trail {i}_{j}", "opacity", 0, 0, "hold"), key(f"Trail {i}_{j}", "opacity", tj, 0.8, "ease-in"),
                    key(f"Trail {i}_{j}", "opacity", tj + 350, 0, "hold"),
                    key(f"Trail {i}_{j}", "translate-y", 0, round(yj, 1), "hold")]
        ops += [key(f"Flash {i}", "opacity", 0, 0, "hold"), key(f"Flash {i}", "opacity", t + climb, 0.55, "ease-out"),
                key(f"Flash {i}", "opacity", t + climb + 250, 0),
                key(f"Flash {i}", "scale", t + climb, 0.2, "ease-out-cubic"), key(f"Flash {i}", "scale", t + climb + 250, 1.6)]
        # The burst: sparks fly out radially, slow down, droop under gravity and fade. (A particles emitter has
        # one velocity for every particle, so a radial burst is built by hand.)
        boom_t = t + climb
        reach = 150 if i < 2 else 240
        for j in range(SPARKS):
            a = 2 * math.pi * j / SPARKS + rng.uniform(-0.08, 0.08)
            d = reach * rng.uniform(0.6, 1.0)
            name = f"Spark {i}_{j}"
            ops += [key(name, "opacity", 0, 0, "hold"), key(name, "opacity", boom_t, 1, "hold"),
                    key(name, "opacity", boom_t + 500, 1, "ease-in"), key(name, "opacity", boom_t + 1100, 0)]
            for k in range(7):
                u = k / 6
                e = 1 - (1 - u) ** 3
                tk = boom_t + int(1100 * u)
                ops += [key(name, "translate-x", tk, round(math.cos(a) * d * e, 1)),
                        key(name, "translate-y", tk, round(math.sin(a) * d * e + 90 * u * u, 1))]
    # The big burst leaves the logo behind: the mark pops out of the flash, the pixels scatter, the name sparkles in.
    boom = shots[2][1] + 600
    for part in (UPPER, LOWER):
        ops += [key(part, "opacity", boom, 1, "hold"), key(part, "scale", 0, 0.2, "hold"),
                key(part, "scale", boom, 0.2, "ease-out-back"), key(part, "scale", boom + 500, 1)]
    for i, name in enumerate(PIXELS):
        cx, cy = centre(p, name)
        ops += [key(name, "opacity", boom + 80, 1, "hold"),
                tween(name, "translate-x", boom + 80, 600, 0, mark_c[0] - cx, "ease-out-back"),
                tween(name, "translate-y", boom + 80, 600, 0, mark_c[1] - cy, "ease-out-back")]
    ops += [key(WORD, "opacity", boom + 400, 1, "hold"),
            {"type": "text-animate", "target": WORD, "preset": "color-sweep", "unit": "char", "start": boom + 400,
             "duration": 700, "stagger": 110, "from": "#ffd36a"},
            {"type": "text-animate", "target": WORD, "preset": "fade-up", "unit": "char", "start": boom + 400,
             "duration": 500, "stagger": 110}]
    p.apply(ops)
    return finish(p)


EXTRA = {
    "14-split-flap": split_flap,
    "15-liquid-fill": liquid_fill,
    "16-napkin-sketch": sketch,
    "17-beat-build": beat_build,
    "18-kaleidoscope": kaleidoscope,
    "19-fireworks": fireworks,
}
