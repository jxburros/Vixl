"""A tiny numpy synthesiser: score, sound effects and dialogue blips for "The Germ King".

Everything is generated from code (no samples), so the soundtrack is reproducible
like the picture. ``build_audio`` returns (music, sfx) mono float arrays at 44.1 kHz.
"""
from __future__ import annotations

import random
import wave

import numpy as np

SR = 44100


def mtof(m: float) -> float:
    return 440.0 * 2 ** ((m - 69) / 12)


# ----------------------------------------------------------------------- primitives
def osc(f, n: int, kind: str = "sine") -> np.ndarray:
    f = np.full(n, float(f)) if np.ndim(f) == 0 else np.asarray(f, float)
    ph = 2 * np.pi * np.cumsum(f) / SR
    if kind == "sine":
        return np.sin(ph)
    saw = 2 * ((ph / (2 * np.pi)) % 1) - 1
    if kind == "saw":
        return saw
    if kind == "square":
        return np.sign(np.sin(ph))
    return 2 * np.abs(saw) - 1  # triangle


def tt(n: int) -> np.ndarray:
    return np.arange(n) / SR


def lp(x: np.ndarray, fc: float) -> np.ndarray:
    a = 1 - np.exp(-2 * np.pi * fc / SR)
    k = min(len(x), int(8 / a) + 1)
    return np.convolve(x, a * (1 - a) ** np.arange(k))[: len(x)]


def hp(x: np.ndarray, fc: float) -> np.ndarray:
    return x - lp(x, fc)


def adsr(n: int, a: float = 0.01, r: float = 0.05) -> np.ndarray:
    e = np.ones(n)
    na, nr = max(1, int(a * SR)), max(1, int(r * SR))
    e[:na] = np.linspace(0, 1, na)[: len(e[:na])]
    e[-nr:] *= np.linspace(1, 0, nr)[-len(e[-nr:]):]
    return e


class Track:
    def __init__(self, seconds: float):
        self.buf = np.zeros(int(seconds * SR) + SR * 3)

    def add(self, t: float, x: np.ndarray, gain: float = 1.0):
        i = int(t * SR)
        if i < 0:
            x, i = x[-i:], 0
        j = min(len(self.buf), i + len(x))
        if j > i:
            self.buf[i:j] += x[: j - i] * gain


# ----------------------------------------------------------------------- instruments
def marimba(f, d=0.35):
    n = int(d * SR)
    t = tt(n)
    return (np.sin(2 * np.pi * f * t) + 0.45 * np.sin(2 * np.pi * 4 * f * t) * np.exp(-t / 0.035)) * np.exp(-t / (d / 3.2))


def pluck(f, d=0.3):
    n = int(d * SR)
    t = tt(n)
    x = np.sin(2 * np.pi * f * t) + 0.4 * np.sin(4 * np.pi * f * t) + 0.15 * np.sin(6 * np.pi * f * t)
    return x * np.exp(-t / (d / 3)) * np.minimum(1, t / 0.004)


def brass(f, d, bright=2200.0, vib=True):
    n = int(d * SR)
    t = tt(n)
    fv = f * (1 + (0.004 * np.sin(2 * np.pi * 5.5 * t) * np.minimum(1, t / 0.25) if vib else 0))
    x = osc(fv, n, "saw") + 0.5 * osc(fv * 1.004, n, "square")
    return lp(x, bright) * adsr(n, 0.05, min(0.12, d / 3)) * 0.6


def tuba(f, d):
    n = int(d * SR)
    return lp(osc(f, n, "saw") + 0.6 * osc(f, n, "square"), 480) * adsr(n, 0.015, 0.05) * 1.4


def bass(f, d=0.4):
    n = int(d * SR)
    return osc(f, n, "tri") * np.exp(-tt(n) / (d / 2.5)) * np.minimum(1, tt(n) / 0.005)


def pad(freqs, d, a=0.4, r=0.5):
    n = int(d * SR)
    x = sum(osc(f, n, "sine") + 0.3 * osc(f * 2, n, "sine") for f in freqs)
    return x * adsr(n, a, r) / len(freqs)


def kick():
    n = int(0.35 * SR)
    t = tt(n)
    return np.sin(2 * np.pi * np.cumsum(45 + 105 * np.exp(-t / 0.03)) / SR) * np.exp(-t / 0.11)


def snare(rng):
    n = int(0.22 * SR)
    t = tt(n)
    noise = hp(rng.standard_normal(n), 1200)
    return (noise * 0.8 + np.sin(2 * np.pi * 190 * t) * 0.5) * np.exp(-t / 0.06)


def hat(rng):
    n = int(0.05 * SR)
    return hp(rng.standard_normal(n), 6000) * np.exp(-tt(n) / 0.012) * 0.5


def cymbal(rng, d=1.4):
    n = int(d * SR)
    return hp(rng.standard_normal(n), 5000) * np.exp(-tt(n) / (d / 4))


def timp(f, d=0.6):
    n = int(d * SR)
    t = tt(n)
    return np.sin(2 * np.pi * np.cumsum(f * (1 + 0.25 * np.exp(-t / 0.05))) / SR) * np.exp(-t / (d / 3))


def ping(f, d=0.8):
    n = int(d * SR)
    t = tt(n)
    return (np.sin(2 * np.pi * f * t) + 0.3 * np.sin(4 * np.pi * f * t)) * np.exp(-t / (d / 4)) * np.minimum(1, t / 0.003)


def sweep(f0, f1, d, kind="sine", vib=0.0):
    n = int(d * SR)
    t = tt(n)
    f = f0 * (f1 / f0) ** (t / d)
    if vib:
        f = f * (1 + vib * np.sin(2 * np.pi * 6 * t))
    return osc(f, n, kind)


def whoosh(rng, d, up=True):
    n = int(d * SR)
    t = tt(n) / d
    e = np.sin(np.pi * (t if up else 1 - t) ** 1.5) ** 2
    return (lp(rng.standard_normal(n), 3500) - lp(rng.standard_normal(n), 400)) * e


def sneeze(rng, pitch=1.0):
    """'Ah-CHOO': a hiss, a falling whistle and a low boom."""
    n = int(0.7 * SR)
    t = tt(n)
    hiss = hp(rng.standard_normal(n), 600) * np.exp(-t / 0.16) * np.minimum(1, t / 0.01)
    whistle = osc(1100 * pitch * np.exp(-t / 0.18) + 200 * pitch, n, "saw")
    whistle = lp(whistle, 2500) * np.exp(-t / 0.13) * 0.5
    boom = np.sin(2 * np.pi * 62 * t) * np.exp(-t / 0.22) * 0.9
    return hiss * 0.9 + whistle + boom


def boing(f0=250, f1=720, d=0.28):
    return sweep(f0, f1, d, vib=0.02) * np.exp(-tt(int(d * SR)) / (d * 0.7)) * np.minimum(1, tt(int(d * SR)) / 0.004)


def blip(rng, voice: str):
    d = 0.07
    n = int(d * SR)
    if voice == "pip":
        f = rng.uniform(520, 780)
        x = osc(f, n, "tri")
    elif voice == "germ":
        f = rng.uniform(760, 1100)
        x = osc(f, n, "sine")
    else:  # elders: low and grumbly
        f = rng.uniform(110, 190)
        x = lp(osc(f, n, "saw"), 900)
    return x * adsr(n, 0.006, 0.03) * 0.5


# ----------------------------------------------------------------------- the score
def build_audio(starts: dict[str, float], talks: dict[str, list], total: float, seed: int = 7):
    """starts: scene name -> film time (s). talks: scene name -> [(mouth, t0 ms, t1 ms, step ms)]."""
    rng = np.random.default_rng(seed)
    py = random.Random(seed)
    M, S = Track(total), Track(total)

    def at(scene, local):  # film seconds
        return starts[scene] + local

    # ---------------- 1. council (D minor, pompous) ----------------
    s = "01-council"
    for k, m in enumerate((62, 65, 69, 65, 62)):  # Pip's bouncy walk-in
        M.add(at(s, 0.1 + k * 0.38), marimba(mtof(m + 12), 0.3), 0.32)
    for k in range(int((9.0 - 2.0) / 0.75)):  # oom-pah of the Council
        t = at(s, 2.0 + k * 0.75)
        M.add(t, tuba(mtof(38 if k % 2 == 0 else 33), 0.45), 0.34)
        M.add(t + 0.375, brass(mtof(50), 0.16, 1400, False) + brass(mtof(53), 0.16, 1400, False) + brass(mtof(57), 0.16, 1400, False), 0.1)
    S.add(at(s, 6.88), hp(rng.standard_normal(int(0.18 * SR)), 700) * np.exp(-tt(int(0.18 * SR)) / 0.03), 0.9)  # gavel
    S.add(at(s, 6.88), np.sin(2 * np.pi * 170 * tt(int(0.3 * SR))) * np.exp(-tt(int(0.3 * SR)) / 0.07), 0.8)
    for t in (7.1, 7.75):
        S.add(at(s, t), boing(), 0.35)
    for k, (m, d) in enumerate(((65, 0.26), (64, 0.26), (63, 0.26), (62, 1.0))):  # sad trombone
        M.add(at(s, 8.1 + k * 0.28), brass(mtof(m), d, 1300), 0.3)

    # ---------------- 2. shrink (mystery, rising) ----------------
    s = "02-shrink"
    M.add(at(s, 0.0), pad([mtof(38), mtof(45)], 3.0, 0.6, 0.6), 0.28)
    M.add(at(s, 0.0), lp(osc(mtof(50), int(2.8 * SR), "saw"), 700) * adsr(int(2.8 * SR), 0.5, 0.6), 0.12)
    t, gap, k = 3.0, 0.2, 0
    notes = (62, 65, 69, 74, 77, 81, 86)
    while t < 5.4:
        M.add(at(s, t), ping(mtof(notes[k % 7] + (12 if k >= 7 else 0)), 0.5), 0.22)
        t += gap
        gap = max(0.065, gap * 0.9)
        k += 1
    for _ in range(26):
        S.add(at(s, py.uniform(3.1, 5.5)), ping(py.uniform(2200, 4200), 0.6), 0.08)
    r = sweep(150, 1900, 1.25, "saw")
    S.add(at(s, 4.15), lp(r, 3500) * np.linspace(0, 1, len(r)) ** 2, 0.22)
    S.add(at(s, 5.3), whoosh(rng, 0.7), 0.55)
    for m in (84, 88, 91, 95):
        M.add(at(s, 5.85), ping(mtof(m), 1.8), 0.16)

    # ---------------- 3. arrival (C major, bouncy marimba) ----------------
    s = "03-arrival"
    bars = [[72, 76, 79, 76, 72, 76, 79, 76], [69, 72, 76, 72, 69, 72, 76, 72],
            [65, 69, 72, 69, 65, 69, 72, 69], [67, 71, 74, 71, 67, 71, 74, 67]]
    bass_n = (48, 45, 41, 43)
    step = 60 / 140 / 2
    for b in range(4):
        for i in range(8):
            t = 0.2 + (b * 8 + i) * step
            if t > 6.9:
                break
            M.add(at(s, t), marimba(mtof(bars[b % 4][i]), 0.3), 0.22 if t > 1.5 else 0.12)
            if i % 4 == 0:
                M.add(at(s, t), bass(mtof(bass_n[b % 4] - 12), 0.45), 0.4)
    for b in range(4, 7):  # loop the progression
        for i in range(8):
            t = 0.2 + (b * 8 + i) * step
            if t > 6.9:
                break
            M.add(at(s, t), marimba(mtof(bars[b % 4][i]), 0.3), 0.22)
            if i % 4 == 0:
                M.add(at(s, t), bass(mtof(bass_n[b % 4] - 12), 0.45), 0.4)
    fall = sweep(2000, 260, 0.75)
    S.add(at(s, 0.7), fall * np.linspace(0.3, 1, len(fall)), 0.18)
    S.add(at(s, 1.45), kick(), 0.9)
    S.add(at(s, 1.45), hp(rng.standard_normal(int(0.25 * SR)), 900) * np.exp(-tt(int(0.25 * SR)) / 0.07), 0.4)
    S.add(at(s, 1.6), whoosh(rng, 0.35), 0.3)
    M.add(at(s, 5.0), pad([mtof(60), mtof(64), mtof(67)], 2.0, 0.3, 0.6), 0.2)

    # ---------------- 4. coronation (C major fanfare) ----------------
    s = "04-coronation"
    for t, m, d in ((0.3, 67, 0.18), (0.52, 67, 0.18), (0.74, 67, 0.18), (0.96, 72, 0.7)):
        M.add(at(s, t), brass(mtof(m), d), 0.26)
    M.add(at(s, 0.0), pad([mtof(48), mtof(55), mtof(64)], 3.4, 0.5, 0.5), 0.2)
    for k in range(10):
        S.add(at(s, 3.4 + k * 0.06), timp(mtof(36), 0.3), 0.18 + 0.05 * k)
    for m in (60, 64, 67, 72):
        M.add(at(s, 4.0), brass(mtof(m), 1.4), 0.24)
    S.add(at(s, 4.0), cymbal(rng, 1.8), 0.5)
    S.add(at(s, 4.0), timp(mtof(36), 1.0), 0.9)
    for k in range(8):
        S.add(at(s, 4.05 + k * 0.08), ping(mtof(88 + (k * 3) % 9), 0.9), 0.1)
    beat = 60 / 112
    for k in range(int((7.0 - 4.5) / beat)):
        t = 4.5 + k * beat
        M.add(at(s, t), tuba(mtof(36 if k % 2 == 0 else 43), 0.3), 0.32)
        M.add(at(s, t + beat / 2), brass(mtof(64), 0.14, 1600, False) + brass(mtof(67), 0.14, 1600, False), 0.12)
    crowd = lp(rng.standard_normal(int(2.4 * SR)), 2600) - lp(rng.standard_normal(int(2.4 * SR)), 500)
    S.add(at(s, 4.3), crowd * adsr(len(crowd), 0.5, 0.6), 0.5)

    # ---------------- 5. march (D minor, drums and low brass) ----------------
    s = "05-march"
    b = 0.36
    for k in range(int(5.5 / b)):
        t = k * b
        if k % 2 == 0:
            S.add(at(s, t), kick(), 0.6)
        else:
            S.add(at(s, t), snare(rng), 0.35)
        S.add(at(s, t + b / 2), hat(rng), 0.25)
    riff = (50, 50, 53, 50, 57, 55, 53, 52)
    for k in range(int(5.5 / b)):
        M.add(at(s, k * b), brass(mtof(riff[k % 8]), 0.22, 1400, False), 0.2)
    rum = osc(45, int(1.8 * SR), "sine") * np.linspace(0, 1, int(1.8 * SR)) ** 2
    S.add(at(s, 1.8), rum + lp(rng.standard_normal(len(rum)), 160) * np.linspace(0, 1, len(rum)) ** 2 * 1.5, 0.5)
    for m in (50, 54, 56, 62):
        M.add(at(s, 3.55), brass(mtof(m), 1.0, 1800), 0.2)
    S.add(at(s, 3.55), timp(mtof(38), 1.0), 0.8)
    for t in (3.9, 5.0):
        sn = lp(osc(80, int(0.9 * SR), "saw"), 300) * adsr(int(0.9 * SR), 0.12, 0.3)
        S.add(at(s, t), sn, 0.3)

    # ---------------- 6. sneeze ----------------
    s = "06-sneeze"
    for t in (0.3, 0.9):
        n = int(0.5 * SR)
        S.add(at(s, t), lp(osc(np.linspace(75, 60, n), n, "saw"), 260) * adsr(n, 0.1, 0.2), 0.45)
    for k, m in enumerate((72, 74, 76, 77, 79, 81)):
        M.add(at(s, 0.2 + k * 0.2), marimba(mtof(m), 0.25), 0.16)
    n = int(2.05 * SR)
    t = tt(n)
    riser = osc(220 * (1400 / 220) ** (t / 2.05), n, "sine") * (0.6 + 0.4 * np.sin(2 * np.pi * 8 * t)) * np.linspace(0.05, 1, n) ** 2
    M.add(at(s, 1.3), riser, 0.25)
    for tt0, f, d in ((1.75, 320, 0.5), (2.35, 400, 0.55), (3.0, 520, 0.36)):
        n = int(d * SR)
        v = lp(osc(f * (1 + 0.01 * np.sin(2 * np.pi * 6 * tt(n))), n, "saw"), 1500) * adsr(n, 0.05, 0.1)
        S.add(at(s, tt0), v, 0.3)
    S.add(at(s, 3.38), sneeze(rng, 1.0), 1.0)
    S.add(at(s, 3.38), cymbal(rng, 0.9), 0.25)
    S.add(at(s, 3.5), sweep(1300, 280, 0.9, vib=0.03) * np.exp(-tt(int(0.9 * SR)) / 0.7), 0.2)
    S.add(at(s, 4.3), boing(300, 800, 0.2), 0.2)

    # ---------------- 7. aftermath (F major, wry) ----------------
    s = "07-aftermath"
    for t, p in ((0.4, 1.3), (0.8, 1.0), (1.2, 0.8)):
        S.add(at(s, t), sneeze(rng, p) * 0.5, 0.6)
    S.add(at(s, 1.25), hp(rng.standard_normal(int(0.18 * SR)), 3000) * np.linspace(0, 1, int(0.18 * SR)), 0.3)
    beat = 60 / 90
    walk = (41, 48, 50, 45, 46, 41, 43, 48)
    for k in range(int((9.3 - 1.5) / beat)):
        t = 1.5 + k * beat
        M.add(at(s, t), lp(osc(mtof(walk[k % 8]), int(0.5 * SR), "saw"), 650) * adsr(int(0.5 * SR), 0.03, 0.15), 0.3)
    mel = (69, 72, 77, 76, 74, 72, 69, 67)
    for k, m in enumerate(mel * 2):
        M.add(at(s, 2.0 + k * beat), pluck(mtof(m + 12), 0.4), 0.14)
    for k, m in enumerate((62, 65, 69)):
        M.add(at(s, 6.1 + k * 0.2), pluck(mtof(m), 0.2), 0.3)
    for k, m in enumerate((88, 91, 96)):
        M.add(at(s, 8.35 + k * 0.11), ping(mtof(m), 0.7), 0.16)
    for t in (8.92, 8.95, 8.99):
        S.add(at(s, t), sneeze(rng, py.uniform(0.75, 1.3)) * 0.5, 0.8)

    # ---------------- 8. title (triumphant reprise) ----------------
    s = "08-title"
    sw = hp(rng.standard_normal(int(1.2 * SR)), 1500) * np.linspace(0, 1, int(1.2 * SR)) ** 2
    S.add(at(s, 0.1), sw, 0.3)
    for t, m, d in ((0.3, 67, 0.2), (0.54, 67, 0.2), (0.78, 67, 0.2), (1.02, 72, 0.5), (1.54, 76, 0.9)):
        M.add(at(s, t), brass(mtof(m), d), 0.26)
    for m in (60, 64, 67, 72):
        M.add(at(s, 1.5), brass(mtof(m), 2.4), 0.24)
    S.add(at(s, 1.5), cymbal(rng, 2.0), 0.5)
    S.add(at(s, 1.5), timp(mtof(36), 1.2), 0.9)
    for k in range(10):
        S.add(at(s, 1.55 + k * 0.1), ping(mtof(84 + (k * 4) % 12), 0.9), 0.1)
    beat = 0.5
    for k in range(int((4.4 - 2.2) / beat)):
        t = 2.2 + k * beat
        M.add(at(s, t), tuba(mtof(36 if k % 2 == 0 else 43), 0.3), 0.3)
    for m in (60, 64, 67, 72):
        M.add(at(s, 4.0), brass(mtof(m), 0.9), 0.2)
    S.add(at(s, 4.0), cymbal(rng, 1.0), 0.3)
    S.add(at(s, 4.0), timp(mtof(36), 0.8), 0.7)

    # ---------------- dialogue blips (synced to the flapping mouths) ----------------
    for scene, items in talks.items():
        for mouth, t0, t1, step in items:
            if mouth.startswith("pip"):
                voice = "pip"
            elif mouth.startswith(("e1", "e2", "e3", "big", "giant")):
                voice = "elder"
            else:
                voice = "germ"
            t = t0
            while t < t1:
                S.add(starts[scene] + t / 1000.0, blip(rng, voice), 0.3)
                t += 2 * step
    return M.buf[: int(total * SR)], S.buf[: int(total * SR)]


def write_wav(path: str, x: np.ndarray, peak: float = 0.89):
    ref = max(1e-9, float(np.percentile(np.abs(x), 99.7)))  # soft-limit the rare big transients
    x = np.tanh(x / ref * 1.1)
    x = x / max(1e-9, np.max(np.abs(x))) * peak
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((x * 32767).astype("<i2").tobytes())
