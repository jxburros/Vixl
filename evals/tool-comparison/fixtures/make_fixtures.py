"""Create the generated fixtures for the tool comparison.

    python evals/tool-comparison/fixtures/make_fixtures.py [--sketch]

Writes, next to this script:

- lighthouse.wav  the 32-second song for T14 (standard library only);
- coast-raw.jpg   a copy of explorations/06-photo-lab/photos/coast-raw.jpg for T10;
- sketch.jpg      only with --sketch (needs Pillow): regenerates the committed T11 sketch.

The song is the same synthesized arpeggio as examples/lyric-video, so no third-party audio is used.
"""

import array
import math
from pathlib import Path
import random
import shutil
import sys
import wave

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]


def song(path, seconds=32, rate=22050):
    notes = [220.0, 277.18, 329.63, 440.0, 329.63, 277.18]
    beat = 0.5
    samples = array.array("h")
    for i in range(int(seconds * rate)):
        t = i / rate
        frequency = notes[int(t // beat) % len(notes)]
        envelope = math.exp(-3 * (t % beat))
        value = 0.25 * envelope * math.sin(2 * math.pi * frequency * t)
        value += 0.08 * math.sin(2 * math.pi * 110 * t)
        samples.append(int(max(-1.0, min(1.0, value)) * 32767))
    with wave.open(str(path), "wb") as audio:
        audio.setparams((1, 2, rate, 0, "NONE", "not compressed"))
        audio.writeframes(samples.tobytes())


def sketch(path, seed=11):
    """A phone photo of a pen sketch: house, sun and tree, with gaps, overshoots and a 2° tilt."""
    from PIL import Image, ImageChops, ImageDraw, ImageFilter

    rng = random.Random(seed)
    w, h = 2000, 1500
    ink = Image.new("L", (w, h), 255)
    draw = ImageDraw.Draw(ink)

    def stroke(points, width=5):
        phase = rng.uniform(0, 6.3)
        wobble = []
        for i, (x, y) in enumerate(points):
            d = 2.2 * math.sin(i / 7 + phase) + rng.uniform(-0.6, 0.6)
            wobble.append((x + d, y + d * 0.6))
        draw.line(wobble, fill=rng.randint(30, 60), width=width + rng.choice((-1, 0, 0, 1)), joint="curve")

    def segment(a, b, trim=(0, 0), step=8):
        (x0, y0), (x1, y1) = a, b
        length = math.hypot(x1 - x0, y1 - y0)
        ux, uy = (x1 - x0) / length, (y1 - y0) / length
        start, end = trim[0], length - trim[1]
        n = max(2, int((end - start) / step))
        steps = [start + (end - start) * k / n for k in range(n + 1)]
        stroke([(x0 + ux * d, y0 + uy * d) for d in steps])

    def loop(cx, cy, radius, gap_deg=0.0, lobes=0, lobe_amp=0.0):
        start = rng.uniform(0, 360)
        sweep = 360 - gap_deg
        pts = []
        for k in range(121):
            a = math.radians(start + sweep * k / 120)
            r = radius + lobe_amp * abs(math.sin(lobes * a / 2)) if lobes else radius
            r += rng.uniform(-1.5, 1.5)
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
        stroke(pts)

    # Ground, a slightly wavy line.
    stroke([(150 + x, 1150 + 6 * math.sin(x / 140)) for x in range(0, 1701, 10)])
    # House body: a gap at the top-left corner and an overshoot at the bottom-right.
    segment((600, 700), (600, 1150), trim=(14, 0))
    segment((600, 700), (1100, 700), trim=(10, 0))
    segment((1100, 700), (1100, 1162))
    # Roof, overshooting at the ridge.
    segment((570, 712), (858, 422))
    segment((842, 422), (1132, 712))
    # Door, open at the bottom where it meets the ground, small gap at the top-left.
    segment((800, 1150), (800, 930), trim=(0, 9))
    segment((800, 930), (920, 930))
    segment((920, 930), (920, 1150))
    # Windows with crosses.
    for x0 in (660, 960):
        segment((x0, 770), (x0 + 110, 770))
        segment((x0 + 110, 770), (x0 + 110, 880))
        segment((x0 + 110, 880), (x0, 880), trim=(0, 7))
        segment((x0, 880), (x0, 770))
        segment((x0 + 55, 774), (x0 + 55, 876))
        segment((x0 + 4, 825), (x0 + 106, 825))
    # Sun: an unclosed circle and eight rays.
    loop(1550, 330, 120, gap_deg=24)
    for k in range(8):
        a = math.radians(k * 45 + rng.uniform(-4, 4))
        inner = (1550 + 160 * math.cos(a), 330 + 160 * math.sin(a))
        segment(inner, (1550 + 235 * math.cos(a), 330 + 235 * math.sin(a)))
    # Tree: trunk and a bumpy canopy.
    segment((1400, 1150), (1400, 935))
    segment((1440, 1150), (1440, 935))
    loop(1420, 800, 120, gap_deg=30, lobes=7, lobe_amp=28)

    ink = ink.filter(ImageFilter.GaussianBlur(0.9))

    paper = Image.new("RGB", (w, h), (238, 233, 220))
    grain = Image.effect_noise((w, h), 7).convert("RGB")
    paper = ImageChops.add(paper, grain, scale=1.0, offset=-128)
    # Uneven light: brighter at the top right, a soft shadow towards the bottom left.
    light = Image.new("L", (2, 2))
    light.putdata([228, 255, 196, 236])
    light = light.resize((w, h), Image.Resampling.BILINEAR).convert("RGB")
    paper = ImageChops.multiply(paper, light)
    photo = ImageChops.multiply(paper, ink.convert("RGB"))
    photo = photo.rotate(2.0, resample=Image.Resampling.BICUBIC, fillcolor=(96, 84, 72))
    photo.save(path, quality=80)


def main():
    song(HERE / "lighthouse.wav")
    print("wrote lighthouse.wav")
    source = REPO / "explorations" / "06-photo-lab" / "photos" / "coast-raw.jpg"
    shutil.copyfile(source, HERE / "coast-raw.jpg")
    print("wrote coast-raw.jpg")
    if "--sketch" in sys.argv:
        sketch(HERE / "sketch.jpg")
        print("wrote sketch.jpg")


if __name__ == "__main__":
    main()
