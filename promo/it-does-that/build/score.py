"""The soundtrack, written as a Vixl document: one ``audio-track`` operation per instrument.

Every sound comes from Vixl's built-in synthesizer (kick, snare, hihat, bass, piano, bell, whoosh, pop),
so the score is an editable ``score.vixl`` like the scenes, and ``export_audio`` mixes it to WAV.
120 BPM in A minor, vi-IV-I-V (Am F C G), one chord per bar. Shot 10 draws these same notes as a
piano roll, so ``tracks()`` is the single source for both.
"""
from __future__ import annotations

from pathlib import Path

from film import BEAT, HERE

BAR = 4 * BEAT
EIGHTH = BEAT // 2
CHORDS = [  # (bass root, chord tones) per bar, MIDI
    (45, (57, 60, 64)),  # Am
    (41, (57, 60, 65)),  # F
    (48, (55, 60, 64)),  # C
    (43, (55, 59, 62)),  # G
]
# A pentatonic bell motif, two bars long: (eighth index, midi).
MOTIF = [(0, 76), (3, 79), (6, 81), (8, 84), (11, 81), (14, 79)]
MOTIF_B = [(0, 81), (2, 79), (4, 76), (7, 74), (10, 76), (14, 72)]


def note(start, duration, midi, velocity=1.0):
    return {"start": int(start), "duration": int(duration), "midi": midi, "velocity": round(velocity, 3)}


def tracks(cuts: list[int], total: int) -> list[dict]:
    """``audio-track`` operations for a film whose shots start at ``cuts`` (ms) and that lasts ``total`` ms."""
    drums_in, drums_out = cuts[1], cuts[-1]
    bars = range(0, total // BAR + 1)
    kick, snare, hats, bass, keys, bells, whoosh, pops = ([] for _ in range(8))
    for b in bars:
        t0 = b * BAR
        root, chord = CHORDS[b % 4]
        for e in range(8):
            t = t0 + e * EIGHTH
            if t >= total - 200:
                break
            groove = drums_in <= t < drums_out
            if groove and e in (0, 3, 4):
                kick.append(note(t, 260, 36, 1.0 if e != 3 else 0.7))
            if groove and e in (2, 6):
                snare.append(note(t, 200, 38, 0.85))
            if groove:
                hats.append(note(t, 60, 42, 0.55 if e % 2 else 0.32))
            if t < drums_out:
                bass.append(note(t, EIGHTH - 40, root + (12 if e in (3, 7) else 0), 0.9 if e % 2 == 0 else 0.6))
            if e in (1, 5) and t < drums_out:
                for m in chord:
                    keys.append(note(t, 380, m, 0.42))
        if b * BAR < drums_out:
            motif = MOTIF if (b // 2) % 2 == 0 else MOTIF_B
            if b % 2 == 0:
                for e, m in motif:
                    t = t0 + e * EIGHTH
                    if t < drums_out:
                        bells.append(note(t, 700, m, 0.5))
    # Shot changes: a whoosh into each cut and a pop on the beat after it.
    for c in cuts[1:]:
        whoosh.append(note(max(0, c - 380), 520, 60, 0.75))
        pops.append(note(c + BEAT, 120, 84, 0.5))
    # The end card: a held A-minor-add9 on keys and a last bell arpeggio.
    end = cuts[-1]
    for i, m in enumerate((57, 60, 64, 71)):
        keys.append(note(end + i * 40, total - end - 400, m, 0.55))
    for i, m in enumerate((69, 72, 76, 83)):
        bells.append(note(end + 250 + i * EIGHTH, 1600, m, 0.55))
    bass.append(note(end, total - end - 300, 33, 0.9))
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
        track("bells", "bell", bells, 0.20, pan=0.3),
        track("whoosh", "whoosh", whoosh, 0.30),
        track("pops", "pop", pops, 0.22),
    ]


def build(cuts: list[int], total: int):
    """Write ``score.vixl`` and ``audio/score.wav``; return the WAV path and the mix report."""
    from vixl import Project
    from vixl.audio import export_audio

    p = Project(320, 180, "#252B39")
    p.apply([{"type": "timeline-set", "duration": total, "fps": 30, "loop_mode": "off"},
             {"type": "text", "name": "about", "text": "Soundtrack for 'It does that?'", "x": 16, "y": 70,
              "size": 16, "color": "#FFFFFF"}] + tracks(cuts, total), detail="brief")
    p.save(str(HERE / "score.vixl"), overwrite=True)
    out = HERE / "audio"
    out.mkdir(exist_ok=True)
    wav = out / "score.wav"
    report = export_audio(p, str(wav), overwrite=True)
    return Path(wav), report
