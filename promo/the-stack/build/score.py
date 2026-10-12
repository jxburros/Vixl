"""The soundtrack, written as a Vixl document: one ``audio-track`` operation per instrument.

Every sound comes from Vixl's built-in synthesizer, so the score is an editable ``score.vixl`` like the
scenes, and ``export_audio`` mixes it to WAV. 100 BPM in D major, I-V-vi-IV (D A Bm G), one chord per
bar: warmer and slower than the other promos, because half of this film is a journal.
"""
from __future__ import annotations

from pathlib import Path

from film import BEAT, HERE

BAR = 4 * BEAT
EIGHTH = BEAT // 2
CHORDS = [  # (bass root, chord tones) per bar, MIDI
    (38, (62, 66, 69)),  # D
    (45, (61, 64, 69)),  # A
    (47, (62, 66, 71)),  # Bm
    (43, (62, 67, 71)),  # G
]
# A D-major pentatonic bell motif, two bars long: (eighth index, midi).
MOTIF = [(0, 78), (2, 81), (5, 83), (8, 86), (11, 83), (14, 81)]
MOTIF_B = [(0, 83), (3, 81), (6, 78), (8, 76), (11, 78), (14, 74)]


def note(start, duration, midi, velocity=1.0):
    return {"start": int(start), "duration": int(duration), "midi": midi, "velocity": round(velocity, 3)}


def tracks(cuts: list[int], total: int, quiet: list[tuple[int, int]] = ()) -> list[dict]:
    """``audio-track`` operations for a film whose shots start at ``cuts`` (ms) and last ``total`` ms.

    ``quiet`` spans (start, end) drop the drums and bells so the journal pages breathe.
    """
    drums_in, drums_out = cuts[1], cuts[-1]
    kick, snare, hats, bass, keys, bells, whoosh, pops = ([] for _ in range(8))

    def is_quiet(t):
        return any(a <= t < b for a, b in quiet)

    for b in range(0, total // BAR + 1):
        t0 = b * BAR
        root, chord = CHORDS[b % 4]
        for e in range(8):
            t = t0 + e * EIGHTH
            if t >= total - 200:
                break
            groove = drums_in <= t < drums_out and not is_quiet(t)
            if groove and e in (0, 5):
                kick.append(note(t, 260, 36, 1.0 if e == 0 else 0.7))
            if groove and e in (2, 6):
                snare.append(note(t, 200, 38, 0.8))
            if groove:
                hats.append(note(t, 60, 42, 0.5 if e % 2 else 0.3))
            if t < drums_out and (groove or e in (0, 4)):
                bass.append(note(t, (EIGHTH if groove else BEAT * 2) - 40, root, 0.85 if e % 2 == 0 else 0.6))
            if t < drums_out and e in ((1, 5) if groove else (0,)):
                for m in chord:
                    keys.append(note(t, 380 if groove else BAR - 200, m, 0.4 if groove else 0.32))
        if t0 < drums_out and b % 2 == 0 and not is_quiet(t0):
            for e, m in (MOTIF if (b // 2) % 2 == 0 else MOTIF_B):
                t = t0 + e * EIGHTH
                if t < drums_out:
                    bells.append(note(t, 700, m, 0.45))
    for c in cuts[1:]:
        whoosh.append(note(max(0, c - 380), 520, 60, 0.6))
        pops.append(note(c + BEAT, 120, 86, 0.4))
    end = cuts[-1]
    for i, m in enumerate((62, 66, 69, 76)):  # Dadd9 on the end card
        keys.append(note(end + i * 40, total - end - 400, m, 0.5))
    for i, m in enumerate((74, 78, 81, 88)):
        bells.append(note(end + 300 + i * EIGHTH, 1800, m, 0.5))
    bass.append(note(end, total - end - 300, 38, 0.9))
    kick.append(note(end, 400, 36, 1.0))

    def track(name, synth, notes, volume, **extra):
        return {"type": "audio-track", "name": name, "start": 0, "duration": total, "synth": synth,
                "notes": notes, "volume": volume, **extra}

    return [
        track("kick", "kick", kick, 0.55),
        track("snare", "snare", snare, 0.26),
        track("hats", "hihat", hats, 0.14, pan=0.25),
        track("bass", {"instrument": "bass", "envelope": {"attack": 4, "decay": 120, "sustain": 0.6, "release": 80}},
              bass, 0.40),
        track("keys", {"instrument": "piano", "envelope": {"attack": 6, "decay": 400, "sustain": 0.35, "release": 400}},
              keys, 0.22, pan=-0.2),
        track("bells", "bell", bells, 0.18, pan=0.3),
        track("whoosh", "whoosh", whoosh, 0.26),
        track("pops", "pop", pops, 0.2),
    ]


def build(cuts: list[int], total: int, quiet=()):
    """Write ``score.vixl`` and ``audio/score.wav``; return the WAV path and the mix report."""
    from vixl import Project
    from vixl.audio import export_audio

    p = Project(320, 180, "#252B39")
    p.apply([{"type": "timeline-set", "duration": total, "fps": 30, "loop_mode": "off"},
             {"type": "text", "name": "about", "text": "Soundtrack for 'The Stack'", "x": 16, "y": 70,
              "size": 16, "color": "#FFFFFF"}] + tracks(cuts, total, quiet), detail="brief")
    p.save(str(HERE / "score.vixl"), overwrite=True)
    out = HERE / "audio"
    out.mkdir(exist_ok=True)
    wav = out / "score.wav"
    report = export_audio(p, str(wav), overwrite=True)
    return Path(wav), report
