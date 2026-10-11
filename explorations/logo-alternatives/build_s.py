"""Round five: variations on R2 (ripple), the favourite.

Each keeps the waterline wordmark and the rippled reflection on both the x and the l, and changes one
thing: how many bands, how they drift, how deep the reflection goes, its colour, or whether it moves.

Run from the repository root: PYTHONPATH=explorations/logo-alternatives python explorations/logo-alternatives/build_s.py
"""

from build import BLUE, H, INK, OUT, PAPER, SKY, W, contact_sheet, path, poly
from build_m import wordmark
from build_r import clip, ripple_reflection
from vixl import Project
from vixl.timeline import export_timeline

PALE = "#A9C4FF"
MID = "#5B8FF5"


def bands_for(count, first=0.34, gap_growth=1.6):
    """`count` bands over a 95-unit reflection: the first band is attached to the waterline and the
    rest thin out while the gaps between them grow, so the reflection fades towards the baseline."""
    weights = [first] + [(1 - first) * (0.62 ** i) for i in range(count - 1)]
    gaps = [2.5 * (gap_growth ** i) for i in range(count - 1)]
    scale = (95 - sum(gaps)) / sum(weights)
    bands, y = [], 0.0
    for i, w in enumerate(weights):
        h = w * scale
        bands.append((round(y, 2), round(y + h, 2)))
        y += h + (gaps[i] if i < len(gaps) else 0)
    return tuple(bands)


def deep_reflection(depth=3, pitch=13, thick=6, shifts=(5, -4, 3), colours=(MID, SKY, PALE)):
    """Keep the reflection whole down to the baseline, then let ripples carry on below it."""
    def draw(name, points, x, y, fill, extra):
        height = max(py for _, py in points)
        ops = [path(name, poly(points), x, y, fill, **extra)]
        foot = clip(points, height - thick, height)
        for k in range(depth):
            dy = height + 6 + k * pitch - (height - thick)
            band = [(px + shifts[k % len(shifts)], py + dy) for px, py in foot]
            ops.append(path(f"{name} ripple {k + 1}", poly([(round(px, 2), round(py, 2)) for px, py in band]),
                            x, y, colours[min(k, len(colours) - 1)], **extra))
        return ops
    return draw


VARIANTS = [
    ("s1-r2", "S1 · R2 as it was", "Four bands, alternating drift",
     dict(reflect=ripple_reflection())),
    ("s2-calm", "S2 · Calm water", "Five thin bands, small drift; the l reads less like \"!\"",
     dict(reflect=ripple_reflection(bands=bands_for(5), shifts=(0, 3, -3, 2, -2),
                                    colours=(BLUE, BLUE, MID, SKY, PALE)))),
    ("s3-bold", "S3 · Bold water", "Three wide bands; holds up best at small sizes",
     dict(reflect=ripple_reflection(bands=((0, 44), (50, 74), (82, 95)), shifts=(0, 7, -6),
                                    colours=(BLUE, MID, SKY)))),
    ("s4-current", "S4 · Current", "Every band drifts the same way, further each time: motion",
     dict(reflect=ripple_reflection(shifts=(0, 5, 10, 15)))),
    ("s5-deep", "S5 · Deep water", "The x is whole; the ripples continue under the baseline",
     dict(reflect=deep_reflection(), bounds=(0, 0, -264, 50))),
    ("s6-mono", "S6 · One colour", "The same ripple in charcoal: print, stamps, embossing",
     dict(reflection=INK, reflect=ripple_reflection(colours=(INK, INK, INK, INK)))),
    ("s7-fade", "S7 · Fade", "Bands step from blue to pale as the gaps widen",
     dict(reflect=ripple_reflection(bands=bands_for(5, gap_growth=1.9), shifts=(0, 5, -4, 4, -3),
                                    colours=(BLUE, MID, SKY, PALE, "#CFDDFF")))),
]


def animated():
    """S8: the ripple moves. Each band sways sideways on its own phase; a seamless two-second loop."""
    p = Project(W, H, background=PAPER)
    names = wordmark(p, l_mode="split", reflect=ripple_reflection(shifts=(0, 0, 0, 0)))
    moving = [n for n in names if " band " in n and not n.endswith("band 1")]
    ops = [{"type": "timeline-set", "duration": 2000, "loop_mode": "seamless"}]
    for name in moving:
        band = int(name.rsplit(" ", 1)[1])
        ops.append({"type": "keyframes", "target": name, "property": "translate-x",
                    "sample": {"fn": "sin", "period": 2000, "amplitude": 2 + 2 * band, "offset": 0,
                               "phase": 0.25 * band, "samples": 24, "duration": 2000}})
    p.apply(ops)
    return p


def main():
    made = []
    for slug, label, note, options in VARIANTS:
        p = Project(W, H, background=PAPER)
        wordmark(p, l_mode="split", **options)
        p.save(str(OUT / f"{slug}.vixl"), overwrite=True)
        p.export(str(OUT / f"{slug}.png"), overwrite=True)
        made.append((slug, label, note, OUT / f"{slug}.png"))
        print("built", slug)
    p = animated()
    p.save(str(OUT / "s8-moving.vixl"), overwrite=True)
    p.export(str(OUT / "s8-moving.png"), overwrite=True)
    export_timeline(p, str(OUT / "s8-moving.gif"), fps=24, overwrite=True)
    made.append(("s8-moving", "S8 · Moving water", "Animated: the bands sway on a loop (see s8-moving.gif)",
                 OUT / "s8-moving.png"))
    print("built s8-moving")
    contact_sheet(made, name="contact-sheet-s", title="Variations on R2",
                  subtitle="Same waterline and ripple; one thing changes in each")


if __name__ == "__main__":
    main()
