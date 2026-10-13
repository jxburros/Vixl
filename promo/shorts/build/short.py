"""The vertical kit for the Vixl shorts: the promo kit re-pointed at a 1080 x 1920 frame.

Brand constants, operation builders and motion shorthands come from ``promo/build/kit.py``, so the shorts
share the look of the two promo films. Each short is one editable master with four sections on one
timeline (hook, in action, why it matters, end card); a section's layers sit in a group that is only
visible inside its window, so the renderer never draws what is off screen.

Times are milliseconds. The score runs at 120 BPM, so a beat is 500 ms and most entrances land on one.
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.append(str(HERE.parent / "build"))  # after this folder, so our score.py wins

import kit  # noqa: E402

kit.W, kit.H = 1080, 1920  # kit.Scene.project and kit.backdrop read these at call time
from kit import (BAD, BLUE, BODY, CHARCOAL, CODE_KEY, CODE_NUM, CODE_STR, DEEP, GOOD, HEAD, LINE, MONO,  # noqa: E402,F401
                 MUTED, PANEL, SEMI, SKY, WHITE, chip, ellipse, glow, group, image, rect, rich, ripple_in, shadow,
                 text, wordmark)

W, H, FPS = kit.W, kit.H, kit.FPS
WORK = HERE / "work"
WORK.mkdir(exist_ok=True)
BEAT = 500
SERIES = 10

# Accents for the art inside the shots; the frame itself stays in the Ripple palette.
CORAL = "#FF8A65"
MINT = "#5FD3B4"
GOLD = "#FFC94D"
LILAC = "#B79BFF"
PAPER = "#F7F5F0"
INK = "#1A1F2B"

# Side gutter and the band social apps leave clear of their own buttons and captions.
GUTTER = 80
SAFE_TOP, SAFE_BOTTOM = 190, 1640


def rel(path: Path) -> str:
    """Repository-relative path for ``frame`` sources (kit runs from the repository root)."""
    return str(Path(path).resolve().relative_to(kit.ROOT))


def centered(name, spans, y, size, color=WHITE, font=HEAD, line_height=1.0, x=GUTTER, width=W - 2 * GUTTER):
    return rich(name, spans, x, y, size, width, color, font, "center", line_height)


def code_line(name, spans, x, y, size=26, width=W - 2 * GUTTER):
    return rich(name, spans, x, y, size, width, WHITE, MONO, line_height=1.25)


def op_spans(pairs):
    """``{"type": "x", "key": value}`` as syntax-coloured spans from [(key, value), ...]."""
    spans = [("{", WHITE)]
    for i, (k, v) in enumerate(pairs):
        if i:
            spans.append((", ", WHITE))
        spans.append((f'"{k}"', CODE_KEY))
        spans.append((": ", WHITE))
        if isinstance(v, str) and not v.startswith("["):
            spans.append((f'"{v}"', CODE_STR))
        else:
            spans.append((str(v).lower() if isinstance(v, bool) else str(v), CODE_NUM))
    spans.append(("}", WHITE))
    return spans


def panel(name, x, y, w, h, fill=DEEP):
    return [rect(name, x, y, w, h, fill, 24, LINE, 2), shadow(name, 40, 18, 0.4)]


class Short(kit.Scene):
    """One vertical short. ``sections`` maps a section name to its (start, end) window in ms."""

    def __init__(self, number: int, slug: str, feature: str, sections: dict[str, tuple[int, int]]):
        self.number, self.slug, self.feature = number, slug, feature
        self.sections = sections
        self.members: dict[str, list[str]] = {name: [] for name in sections}
        super().__init__(f"{number:02d}-{slug}", max(end for _, end in sections.values()))

    def put(self, section: str, *ops):
        """Add ops and file the layers they create under ``section`` (groups file their members away)."""
        self.add(*ops)
        flat = [o for op in ops for o in (op if isinstance(op, list) else [op])]
        grouped = {m for o in flat if o.get("type") == "group" for m in o["targets"]}
        for o in flat:
            if o.get("name") and o["type"] not in ("keyframe", "layer-style", "clip", "text-animate", "path-fit",
                                                  "scale", "pivot", "radial-repeat"):
                self.members[section].append(o["name"])
        self.members[section] = [n for n in self.members[section] if n not in grouped]
        return self

    def adopt(self, section: str, *names):
        """File layers created indirectly (radial-repeat groups, diagram groups) under ``section``."""
        self.members[section].extend(names)

    def project(self):
        # Close each section into a group that is visible only inside its window.
        for section, (t0, t1) in self.sections.items():
            names = list(dict.fromkeys(self.members[section]))
            if not names:
                continue
            gname = f"sec-{section}"
            self.ops.append(group(gname, names))
            self.key(gname, "visible", 0, t0 == 0)
            if t0:
                self.key(gname, "visible", t0, True, "hold")
            if t1 < self.duration:
                self.key(gname, "visible", t1, False, "hold")
        return super().project()

    def build(self):
        p = self.project()
        p.compact()
        (HERE / "scenes").mkdir(exist_ok=True)
        p.save(str(HERE / "scenes" / f"{self.name}.vixl"), overwrite=True)
        return p


# --------------------------------------------------------------------------- shared sections
def frame(sc: Short):
    """The backdrop and series tag, present for the whole short (cuts between sections stay calm)."""
    sc.add(kit.rect("bg-base", 0, 0, W, H, CHARCOAL),
           glow("bg-glow1", 860, 420, 1500, BLUE, "40"),
           glow("bg-glow2", 160, 1500, 1300, SKY, "22"))
    sc.keys("bg-glow1", "translate-y", [(0, 0), (sc.duration, 260)], "linear")
    sc.keys("bg-glow2", "translate-y", [(0, 0), (sc.duration, -200)], "linear")
    # A thin progress bar along the top edge.
    sc.add(rect("progress-track", 0, 0, W, 8, "#FFFFFF14"), rect("progress", 0, 0, W, 8, SKY))
    sc.add({"type": "pivot", "target": "progress", "value": "left"})
    sc.keys("progress", "scale-x", [(0, 0.001), (sc.duration, 1)], "linear")


def tag(sc: Short, section: str, label: str, t: int):
    """The section chip at the top: 03 / 10 · IN ACTION."""
    name = f"tag-{section}"
    sc.put(section, chip(name, f"{sc.number:02d} / {SERIES}   {label}", GUTTER, SAFE_TOP - 40, size=24, fg=SKY,
                         bg="#3575EE26", font=MONO))
    sc.fade(name, t, dur=300)


def hook(sc: Short, line1, line2, reveal, t0=0):
    """The first seconds: the problem in two lines, then the feature name as the answer."""
    t1 = sc.sections["hook"][1]
    tag(sc, "hook", "VIXL SHORTS", t0)
    sc.put("hook", rich("h1", line1, GUTTER, 560, 92, W - 2 * GUTTER, WHITE, HEAD, line_height=1.04))
    sc.words("h1", t0 + 150, "fade-up", "word", 480, 90)
    sc.put("hook", rich("h2", line2, GUTTER, 820, 60, W - 2 * GUTTER, MUTED, SEMI, line_height=1.12))
    sc.words("h2", t0 + 900, "fade-up", "word", 450, 80)
    for name in ("h1", "h2"):
        sc.keys(name, "opacity", [(t0 + 1700, 1), (t0 + 2000, 0.3)], "ease-in-out")
    sc.put("hook", rich("h3", reveal, GUTTER, 1080, 108, W - 2 * GUTTER, WHITE, HEAD, line_height=1.0))
    sc.words("h3", t0 + 1800, "pop", "word", 420, 110)
    for name in ("h1", "h2", "h3"):
        sc.keys(name, "translate-y", [(0, 0), (t1 - 450, 0), (t1, -120)], "ease-in-cubic")
    sc.keys("h3", "opacity", [(t1 - 450, 1), (t1, 0)], "ease-in-cubic")


def headline(sc: Short, section: str, spans, t, y=SAFE_TOP + 50, size=68):
    name = f"head-{section}"
    sc.put(section, rich(name, spans, GUTTER, y, size, W - 2 * GUTTER, WHITE, HEAD, line_height=1.05))
    sc.words(name, t, "fade-up", "word", 460, 60)
    return name


def how(sc: Short, section: str, lines, y, t, size=26, label="HOW IT WORKS", height=None, stagger=220):
    """A code panel near the bottom: the operations or command that produce what is on screen."""
    h = height or 92 + len(lines) * size * 1.5
    sc.put(section, panel(f"how-{section}", GUTTER, y, W - 2 * GUTTER, h))
    sc.put(section, text(f"how-{section}-label", label, GUTTER + 34, y + 24, 20, SKY, MONO))
    sc.fade(f"how-{section}", t, dur=300)
    sc.fade(f"how-{section}-label", t + 100, dur=300)
    names = []
    for i, spans in enumerate(lines):
        name = f"how-{section}-{i}"
        sc.put(section, code_line(name, spans, GUTTER + 34, y + 70 + i * size * 1.5, size, W - 2 * GUTTER - 68))
        sc.fade(name, t + 250 + i * stagger, dur=250)
        sc.slide(name, t + 250 + i * stagger, dx=-24, dur=400)
        names.append(name)
    return names


def why(sc: Short, title, points):
    """Why it matters: three cards, each a claim and the reason behind it."""
    t0, t1 = sc.sections["why"]
    tag(sc, "why", "WHY IT MATTERS", t0)
    headline(sc, "why", title, t0 + 100, size=76)
    y = 560
    for i, (claim, reason) in enumerate(points):
        name = f"why{i}"
        h = 270
        sc.put("why", rect(f"{name}-bg", GUTTER, y, W - 2 * GUTTER, h, PANEL, 28, LINE),
               ellipse(f"{name}-dot", GUTTER + 70, y + 74, 64, 64, BLUE),
               rich(f"{name}-num", f"{i + 1}", GUTTER + 38, y + 52, 34, 64, WHITE, HEAD, "center", 1.2),
               rich(f"{name}-claim", claim, GUTTER + 130, y + 46, 46, W - 2 * GUTTER - 170, WHITE, HEAD,
                    line_height=1.05),
               rich(f"{name}-reason", reason, GUTTER + 130, y + 124, 30, W - 2 * GUTTER - 170, MUTED, BODY,
                    line_height=1.3),
               group(name, [f"{name}-bg", f"{name}-dot", f"{name}-num", f"{name}-claim", f"{name}-reason"]))
        t = t0 + 600 + i * 900
        sc.pop(name, t, 480, 0.88)
        sc.slide(name, t, dy=60, dur=600)
        y += h + 40


def endcard(sc: Short, line, sub):
    t0, _ = sc.sections["end"]
    sc.put("end", glow("end-pulse", W / 2, 640, 1100, BLUE, "55"))
    sc.pop("end-pulse", t0, 700, 0.5)
    ops, names = wordmark("w", (W - 520) / 2, 470, 520)
    sc.put("end", ops)
    for i, name in enumerate(["w-v", "w-i-stem", "w-i-dot", "w-x", "w-l"]):
        sc.pop(name, t0 + i * 90, 360, 0.4)
    ripple_in(sc, [n for n in names if "-band-" in n], t0 + 450, stagger=45)
    sc.put("end", centered("end-line", line, 900, 84, line_height=1.05))
    sc.words("end-line", t0 + 300, "fade-up", "word", 480, 110)
    sc.put("end", centered("end-sub", sub, 1150, 36, MUTED, SEMI, line_height=1.3))
    sc.fade("end-sub", t0 + 900, dur=400, rise=16)
    sc.put("end", centered("end-url", "github.com/jxburros/Vixl", 1360, 42, WHITE, MONO))
    sc.fade("end-url", t0 + 1200, dur=400, rise=16)
    sc.put("end", centered("end-made", "Every frame of this video is an editable Vixl document.", 1500, 26, MUTED,
                           BODY))
    sc.fade("end-made", t0 + 1500, dur=500)

