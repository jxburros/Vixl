"""Each short's soundtrack, written as a Vixl document: one ``audio-track`` operation per instrument.

Every sound comes from Vixl's built-in synthesizer, so each score is an editable ``scores/NN-name.vixl``
and ``export_audio`` mixes it to WAV. 120 BPM; each short gets its own key and four-chord loop, the drums
enter with the action, a whoosh leads into every section and the end card holds the tonic.
Short 10 draws its own notes as a piano roll, so ``tracks()`` is the single source for both.
"""
from __future__ import annotations

from pathlib import Path

from short import BEAT, HERE

BAR = 4 * BEAT
EIGHTH = BEAT // 2
# Four-chord loops as (root offset, chord tones as offsets) from the key's tonic, one chord per bar.
LOOPS = [
    [(0, (0, 3, 7)), (-4, (-4, 0, 3)), (3, (-5, 3, 7)), (-2, (-2, 2, 5))],   # i  VI  III VII
    [(0, (0, 4, 7)), (7, (2, 7, 11)), (9, (0, 4, 9)), (5, (0, 5, 9))],        # I  V   vi  IV
    [(0, (0, 3, 7)), (5, (0, 5, 8)), (-4, (-4, 0, 3)), (-5, (-1, 2, 7))],     # i  iv  VI  V
    [(0, (0, 4, 7)), (9, (0, 4, 9)), (5, (0, 5, 9)), (7, (2, 7, 11))],        # I  vi  IV  V
]
KEYS = [57, 60, 55, 62, 53, 58, 52, 59, 56, 61]  # tonic per short (MIDI), so no two shorts sound alike
MOTIF = [(0, 12), (3, 15), (6, 19), (8, 24), (11, 19), (14, 15)]  # eighth index, offset from the tonic


def note(start, duration, midi, velocity=1.0):
    return {"start": int(start), "duration": int(duration), "midi": int(midi), "velocity": round(velocity, 3)}


def tracks(short) -> list[dict]:
    """``audio-track`` operations for ``short``, cued to its section starts."""
    total = short.duration
    loop = LOOPS[(short.number - 1) % len(LOOPS)]
    tonic = KEYS[(short.number - 1) % len(KEYS)]
    minor = loop[0][1][1] == 3
    cuts = sorted(a for a, _ in short.sections.values())
    drums_in, end = short.sections["action"][0], short.sections["end"][0]
    kick, snare, hats, bass, keys, bells, whoosh, pops = ([] for _ in range(8))
    for b in range(total // BAR + 1):
        t0 = b * BAR
        root, chord = loop[b % 4]
        for e in range(8):
            t = t0 + e * EIGHTH
            if t >= end:
                break
            groove = t >= drums_in
            if groove and e in (0, 3, 4):
                kick.append(note(t, 260, 36, 1.0 if e != 3 else 0.7))
            if groove and e in (2, 6):
                snare.append(note(t, 200, 38, 0.85))
            if groove:
                hats.append(note(t, 60, 42, 0.55 if e % 2 else 0.32))
            bass.append(note(t, EIGHTH - 40, tonic - 24 + root + (12 if e in (3, 7) else 0),
                             (0.9 if e % 2 == 0 else 0.6) * (1 if groove else 0.6)))
            if e in (1, 5):
                for m in chord:
                    keys.append(note(t, 380, tonic + m, 0.42))
        if b % 2 == 0 and t0 >= drums_in:
            for e, m in MOTIF:
                t = t0 + e * EIGHTH
                if t < end:
                    bells.append(note(t, 700, tonic + m - (1 if minor is False and m in (15,) else 0), 0.5))
    for c in cuts[1:]:
        whoosh.append(note(max(0, c - 380), 520, 60, 0.75))
        pops.append(note(c + BEAT, 120, 84, 0.5))
    third = 3 if minor else 4
    for i, m in enumerate((0, third, 7, 14)):
        keys.append(note(end + i * 40, total - end - 300, tonic + m, 0.55))
    for i, m in enumerate((12, 12 + third, 19, 26)):
        bells.append(note(end + 250 + i * EIGHTH, 1500, tonic + m, 0.55))
    bass.append(note(end, total - end - 300, tonic - 24, 0.9))
    kick.append(note(end, 400, 36, 1.0))

    def track(name, synth, notes, volume, **extra):
        return {"type": "audio-track", "name": name, "start": 0, "duration": total, "synth": synth,
                "notes": notes, "volume": volume, **extra}

    return [
        track("kick", "kick", kick, 0.62),
        track("snare", "snare", snare, 0.30),
        track("hats", "hihat", hats, 0.16, pan=0.25),
        track("bass", {"instrument": "bass", "envelope": {"attack": 4, "decay": 120, "sustain": 0.6, "release": 60}},
              bass, 0.42),
        track("keys", {"instrument": "piano", "envelope": {"attack": 6, "decay": 300, "sustain": 0.3, "release": 250}},
              keys, 0.20, pan=-0.2),
        track("bells", "bell", bells, 0.18, pan=0.3),
        track("whoosh", "whoosh", whoosh, 0.30),
        track("pops", "pop", pops, 0.22),
    ]


def build(short):
    """Write ``scores/NN-name.vixl`` and ``audio/NN-name.wav``; return the WAV path and the mix report."""
    from vixl import Project
    from vixl.audio import export_audio

    p = Project(320, 180, "#252B39")
    p.apply([{"type": "timeline-set", "duration": short.duration, "fps": 30, "loop_mode": "off"},
             {"type": "text", "name": "about", "text": f"Soundtrack for Vixl short {short.name}", "x": 16, "y": 70,
              "size": 16, "color": "#FFFFFF"}] + tracks(short), detail="brief")
    (HERE / "scores").mkdir(exist_ok=True)
    p.save(str(HERE / "scores" / f"{short.name}.vixl"), overwrite=True)
    out = HERE / "audio"
    out.mkdir(exist_ok=True)
    wav = out / f"{short.name}.wav"
    report = export_audio(p, str(wav), overwrite=True)
    return Path(wav), report
