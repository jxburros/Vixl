"""Shared pieces for "The Stack": the promo kit, re-pointed at this film's folder.

The brand constants, operation builders and motion shorthands come from ``promo/build/kit.py`` so every
promo film shares one look. Scenes here save to ``promo/the-stack/scenes``.
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.append(str(HERE.parent / "build"))  # after this folder, so our score.py wins

import kit  # noqa: E402
from kit import *  # noqa: E402,F401,F403
from kit import MONO, MUTED, SKY, WHITE, chip, rich  # noqa: E402

BPM = 100
BEAT = 60_000 // BPM  # ms

# One accent per repository, so each project keeps its colour from its own shot to the stack diagram.
STUDIO = "#F2A93B"   # AI Server Studio
RUNTIME = "#5FD38D"  # JX-Runtime
ONYX = "#B79BFF"     # Onyx Engine
MOCK = "#FF8A65"     # Mock-LLM
VIXL = SKY
PAPER = "#F4EFE4"    # the journal pages
INK = "#2A2620"


class Scene(kit.Scene):
    def build(self):
        p = self.project()
        p.compact()
        p.save(str(HERE / "scenes" / f"{self.name}.vixl"), overwrite=True)
        return p


def rel(path: Path) -> str:
    """Repository-relative path for ``frame`` sources (kit runs from the repository root)."""
    return str(Path(path).resolve().relative_to(kit.ROOT))


def kicker(sc, label, color=SKY, t=0):
    sc.add(chip("kicker", label, 120, 70, size=24, fg=color, bg=f"{color}26", font=MONO))
    sc.fade("kicker", t, dur=300)


def headline(sc, spans, t=150, y=140, size=64, width=1680):
    sc.add(rich("headline", spans, 120, y, size, width, WHITE, kit.HEAD, line_height=1.05))
    sc.words("headline", t, "fade-up", "word", 480, 60)


def caption(sc, name, value, x, y, t, size=26, color=MUTED, font=MONO):
    sc.add(kit.text(name, value, x, y, size, color, font))
    sc.fade(name, t, dur=350, rise=12)


def exit_all(sc, names, t, dur=450, start=1):
    """Fade every named layer out together, so cuts land on a clean frame."""
    for name in names:
        sc.keys(name, "opacity", [(t, start), (t + dur, 0)], "ease-in-cubic")


__all__ = [n for n in dir(kit) if not n.startswith("_")] + [
    "Scene", "HERE", "BPM", "BEAT", "STUDIO", "RUNTIME", "ONYX", "MOCK", "VIXL", "PAPER", "INK", "rel",
    "kicker", "headline", "caption", "exit_all"]
