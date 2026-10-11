"""Shared pieces for "It does that?": the promo kit, re-pointed at this film's folder.

The brand constants, operation builders and motion shorthands come from ``promo/build/kit.py`` so both
promo films share one look. Scenes here save to ``promo/it-does-that/scenes``; generated inputs
(the sketch photo, the badge run, the emoji master) go to ``work/``, which is not committed, and are
embedded in the scene masters.
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.append(str(HERE.parent / "build"))  # after this folder, so our score.py wins

import kit  # noqa: E402
from kit import *  # noqa: E402,F401,F403
from kit import BLUE, MONO, MUTED, SKY, WHITE, chip, rich  # noqa: E402

WORK = HERE / "work"
WORK.mkdir(exist_ok=True)
BPM = 120
BEAT = 60_000 // BPM  # ms

# Accents for the art in the shots; the frame itself stays in the Digital Shift palette.
CORAL = "#FF8A65"
MINT = "#5FD3B4"
GOLD = "#FFC94D"
LILAC = "#B79BFF"
PAPER = "#F7F5F0"
INK = "#1A1F2B"


class Scene(kit.Scene):
    def build(self):
        p = self.project()
        p.compact()
        p.save(str(HERE / "scenes" / f"{self.name}.vixl"), overwrite=True)
        return p


def rel(path: Path) -> str:
    """Repository-relative path for ``frame`` sources (kit runs from the repository root)."""
    return str(Path(path).resolve().relative_to(kit.ROOT))


def kicker(sc, number, label, t=0):
    sc.add(chip("kicker", f"{number} / 09   {label}", 120, 70, size=24, fg=SKY, bg="#3575EE26", font=MONO))
    sc.fade("kicker", t, dur=300)


def headline(sc, spans, t=150, y=140, size=66, width=1680):
    sc.add(rich("headline", spans, 120, y, size, width, WHITE, kit.HEAD, line_height=1.05))
    sc.words("headline", t, "fade-up", "word", 480, 60)


def caption(sc, name, value, x, y, t, size=26, color=MUTED, font=MONO):
    sc.add(kit.text(name, value, x, y, size, color, font))
    sc.fade(name, t, dur=350, rise=12)


def exit_all(sc, names, t, dur=450, start=1):
    """Fade every named layer out together from opacity ``start``, so cuts land on a clean frame."""
    for name in names:
        sc.keys(name, "opacity", [(t, start), (t + dur, 0)], "ease-in-cubic")


__all__ = [n for n in dir(kit) if not n.startswith("_")] + [
    "Scene", "WORK", "HERE", "BPM", "BEAT", "CORAL", "MINT", "GOLD", "LILAC", "PAPER", "INK", "rel", "kicker",
    "headline", "caption", "exit_all", "BLUE"]
