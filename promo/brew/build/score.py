"""The score for "Brew": a 120 BPM i-VI-III-VII in D minor, built from the promo's numpy instruments.

A bubbling, drum-free intro while the potion brews, an impact when the poster comes out of the pot,
a groove through the middle, a quiet bed under the last quote and bells on the end card.
``write_all`` writes ``music.wav`` and ``effects.wav`` (48 kHz, 16-bit stereo).
"""
from __future__ import annotations

import importlib.util
import random
from pathlib import Path

import numpy as np

_spec = importlib.util.spec_from_file_location("promo_score", Path(__file__).resolve().parents[2] / "build" / "score.py")
base = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(base)

BEAT, BAR, SR = base.BEAT, base.BAR, base.SR
Bus, bass, bell, chime, clap, hat, impact, kick, pad, pluck, pop, riser, tick, whoosh = (
    base.Bus, base.bass, base.bell, base.chime, base.clap, base.hat, base.impact, base.kick, base.pad, base.pluck,
    base.pop, base.riser, base.tick, base.whoosh)

CHORDS = [(50, [50, 53, 57]), (46, [46, 50, 53]), (53, [53, 57, 60]), (48, [48, 52, 55])]
REVEAL = 3400  # ms into 02-moon: the poster leaves the pot


def music(total, starts):
    s = {k: v / 1000 for k, v in starts.items()}
    reveal = s["02-moon"] + REVEAL / 1000
    groove_from, groove_to, outro = s["03-ready"], s["10-fun"], s["11-end"]
    bright_from, bright_to = s["05-eight"], s["07-direction"]
    drums, low, keys = Bus(total + 3), Bus(total + 3), Bus(total + 3)
    duck = np.ones(len(drums.buf))
    for bar in range(int(np.ceil(total / BAR))):
        t0 = bar * BAR
        root, chord = CHORDS[bar % 4]
        intro = t0 < groove_from
        groove = groove_from <= t0 < groove_to
        quiet = groove_to <= t0 < outro
        bright = bright_from <= t0 < bright_to
        if t0 >= outro:
            keys.add(t0, pad([62, 65, 69, 74], 4.0, 1800), 0.9)
            for i, n in enumerate((74, 77, 81, 86)):
                keys.add(t0 + i * 0.12, bell(n, 3.0), 0.5, pan=-0.4 + i * 0.27)
            continue
        keys.add(t0, pad([n + 12 for n in chord], BAR + 0.4, 1000 if intro or quiet else 1500),
                 0.9 if intro or quiet else 0.7)
        tones = chord + [chord[0] + 12]
        if intro or quiet:  # music-box bells, one per beat, wandering up the chord
            for b, idx in enumerate((0, 2, 1, 3)):
                keys.add(t0 + b * BEAT, bell(tones[idx] + 24, 1.2), 0.32, pan=-0.3 + 0.2 * b)
            if intro and t0 >= 4 * BAR:
                for e in range(8):
                    low.add(t0 + e * BEAT / 2, bass(root - 12, BEAT / 2 * 0.9), 0.45)
            continue
        pattern = [0, 1, 2, 1, 2, 3, 2, 1] * 2
        for st, idx in enumerate(pattern):
            note = tones[idx] + 12 + (12 if bright and st % 4 == 2 else 0)
            keys.add(t0 + st * BEAT / 4, pluck(note, 0.3, 1.4 if bright else 1.0), 0.6, pan=0.35 if st % 2 else -0.35)
        for e in range(8):
            low.add(t0 + e * BEAT / 2, bass(root - 12 + (12 if e % 4 == 3 else 0), BEAT / 2 * 0.95), 0.9)
        if groove:
            for b in range(4):
                bt = t0 + b * BEAT
                drums.add(bt, kick(), 0.95)
                i, n = int(bt * SR), int(0.22 * SR)
                duck[i:i + n] = np.minimum(duck[i:i + n], 0.45 + 0.55 * np.linspace(0, 1, n) ** 0.7)
                if b in (1, 3):
                    drums.add(bt, clap(), 0.6, pan=0.05)
                drums.add(bt + BEAT / 2, hat(bright and b == 3), 0.55, pan=0.25)
                drums.add(bt + BEAT / 4, hat(), 0.22, pan=-0.25)
                drums.add(bt + 3 * BEAT / 4, hat(), 0.22, pan=-0.25)
    keys.add(reveal - 3.0, riser(3.0), 0.3)
    drums.add(reveal, impact(), 0.75)
    keys.add(outro - 3.0, riser(3.0), 0.26)
    drums.add(outro, impact(), 0.75)
    for k in range(4):  # roll into the groove
        drums.add(groove_from - BEAT * 2 + k * BEAT / 2, clap(), 0.25 + 0.1 * k)
    keys.buf = base.reverb(keys.buf, 2.2, 0.35)
    return drums.buf + (low.buf + keys.buf) * duck[:, None]


def splash():
    t = base.t_axis(0.5)
    body = base.spectral(base.rng.standard_normal(len(t)), 300, 2600) * np.exp(-t / 0.09)
    return body * 0.5


def effects(total, starts):
    fx = Bus(total + 3)
    rng = random.Random(2)
    for c in sorted(starts.values())[1:]:
        fx.add(c / 1000 - 0.3, whoosh(0.5), 0.7)

    def at(scene, ms):
        return (starts[scene] + ms) / 1000

    for scene, until in (("01-ingredients", 8000), ("02-moon", 3400)):  # the brew bubbling
        t = 300
        while t < until:
            fx.add(at(scene, t), pop(rng.choice((60, 63, 65, 67, 70))), 0.28, pan=rng.uniform(-0.5, 0.5))
            t += rng.randint(180, 520)
    for i, t in enumerate((150, 240, 800, 940, 1080, 1220)):  # the opening question pops in word by word
        fx.add(at("00-hook", t), pop(72 + 3 * i), 0.55, pan=-0.3 + 0.12 * i)
    for i in range(5):
        fx.add(at("00-hook", 1300 + i * 120), bell(96 + (i % 3) * 3, 0.6), 0.35, pan=-0.5 + 0.25 * i)
    for scene, ms in starts.items():  # the fun meter ticks up in every shot
        if scene not in ("10-fun", "11-end"):
            fx.add(at(scene, 3000 if scene == "00-hook" else 1400), tick(100), 0.45, pan=0.7)
    fx.add(at("10-fun", 2600), impact(), 0.35)
    fx.add(at("10-fun", 2600), chime((91, 96, 100)), 0.6, pan=0.6)
    for i in range(7):
        land = 2200 + i * 560 + 760
        fx.add(at("01-ingredients", land - 700), whoosh(0.55), 0.35, pan=-0.4 if i % 2 else 0.4)
        fx.add(at("01-ingredients", land), splash(), 0.9)
        fx.add(at("01-ingredients", land + 40), pop(55 + 2 * i), 0.7)
    for k in range(5):
        fx.add(at("02-moon", 600 * k), whoosh(0.5), 0.25, pan=-0.3 if k % 2 else 0.3)
    fx.add(at("02-moon", REVEAL), chime((86, 89, 93)), 0.8)
    fx.add(at("02-moon", 4500), pop(79), 0.5)
    for i in range(5):
        fx.add(at("03-ready", 900 + i * 380), tick(96 + (i % 3)), 0.6)
    fx.add(at("03-ready", 1200), whoosh(0.4), 0.4)
    fx.add(at("03-ready", 3600), chime((81, 86, 89)), 0.5)
    for t in (1000, 3000, 5000):
        fx.add(at("04-adjust", t), pop(84), 0.6)
        fx.add(at("04-adjust", t + 600), chime((86, 89, 93)), 0.55)
    for i in range(8):
        fx.add(at("05-eight", 900 + i * 170), pop(72 + 2 * i), 0.5, pan=-0.45 + 0.13 * i)
    fx.add(at("05-eight", 5300), chime((84, 88, 91)), 0.7)
    for r, t0 in enumerate((300, 3000, 5700)):
        for i in range(0, 20, 2):
            fx.add(at("06-rounds", t0 + i * 35), tick(94 + (i // 2) % 5), 0.35, pan=-0.5 + i * 0.05)
        fx.add(at("06-rounds", t0 + 1500), chime((84 + r * 2, 88 + r * 2, 91 + r * 2)), 0.6)
        fx.add(at("06-rounds", t0 + 2400), pop(76), 0.5)
    fx.add(at("06-rounds", 8200), chime((88, 91, 96)), 0.5)
    for i in range(3):
        fx.add(at("07-direction", 500 + i * 900), whoosh(0.4), 0.4)
        fx.add(at("07-direction", 1400 + i * 900), pop(70 + 5 * i), 0.6)
    for i in range(7):
        fx.add(at("08-bottles", 600 + i * 330), pop(74 + 2 * i), 0.5, pan=-0.45 + 0.15 * i)
    fx.add(at("08-bottles", 5400), whoosh(0.7), 0.5)
    for i in range(9):
        fx.add(at("09-self", 400 + i * 150), pop(72 + i), 0.4, pan=-0.4 + 0.1 * i)
    fx.add(at("09-self", 4000), chime((79, 84, 88)), 0.5)
    fx.add(at("09-self", 5500), pop(88), 0.6)
    return fx.buf


def write_all(directory: Path, starts: dict, total: float):
    base.write_wav(directory / "music.wav", base.fade(music(total, starts), total), 0.85)
    base.write_wav(directory / "effects.wav", base.fade(effects(total, starts), total), 0.8)
