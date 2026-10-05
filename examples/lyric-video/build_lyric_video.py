"""Build the lyric-video example: a styled template, a synthesized song and a rendered MP4.

    python examples/lyric-video/build_lyric_video.py [--draft]

Writes lighthouse-style.vixl, lighthouse.wav, lighthouse-lyrics.vixl and lighthouse.mp4 next to
this script. MP4 export needs ffmpeg and ffprobe on PATH. The lyrics are original and the melody
is generated here, so the example carries no third-party audio.
"""

import json
import math
from pathlib import Path
import sys
import wave

import numpy as np

from vixl import Project
from vixl import lyrics

HERE = Path(__file__).resolve().parent


def template(path):
    """The style template. Layer names follow the lyric-video contract (docs/lyric-video.md)."""
    p = Project(1280, 720, "#0b1726")
    p.apply([
        {"type": "variable", "name": "title", "value": "Title"},
        {"type": "variable", "name": "artist", "value": "Artist"},
        {"type": "swatch", "name": "ink", "color": "#f4efe6"},
        {"type": "gradient", "name": "bg-default", "start": "#0b1726", "end": "#1d3b57"},
        {"type": "gradient", "name": "bg-chorus", "start": "#2a1240", "end": "#c2563b"},
        {"type": "gradient", "name": "bg-verse", "start": "#0d2a2a", "end": "#1f5f5b"},
        # A beam that only appears while a line mentions the lighthouse.
        {"type": "shape", "shape": "triangle", "name": "cue-lighthouse", "width": 900, "height": 260,
         "x": 380, "y": 40, "fill": "rgba(255, 220, 120, 0.22)"},
        {"type": "text", "name": "intro", "text": "${title}\n${artist}", "size": 64, "color": "@ink",
         "align": "center", "x": 0, "y": 0},
        {"type": "constrain", "target": "intro", "constraints": {"center-x": "canvas.center-x", "center-y": "canvas.center-y"}},
        {"type": "text", "name": "lyric", "text": "Lyric", "size": 60, "color": "@ink", "align": "center", "x": 140, "y": 270},
        {"type": "text-layout", "target": "lyric", "width": 1000, "height": 170, "fit": True},
        {"type": "text", "name": "lyric-next", "text": "Next", "size": 30, "color": "rgba(244, 239, 230, 0.6)",
         "align": "center", "x": 140, "y": 500},
        {"type": "text-layout", "target": "lyric-next", "width": 1000, "height": 60, "fit": True},
        {"type": "text", "name": "section-label", "text": "Verse", "size": 26, "color": "@ink", "x": 64, "y": 48},
    ])
    p.save(path)


def melody(path, seconds=32, rate=22050):
    """A gentle arpeggio, generated so the example needs no audio files."""
    notes = [220.0, 277.18, 329.63, 440.0, 329.63, 277.18]
    t = np.arange(int(seconds * rate)) / rate
    beat = 0.5
    index = (t // beat).astype(int) % len(notes)
    frequency = np.array(notes)[index]
    envelope = np.exp(-3 * (t % beat))
    signal = 0.25 * envelope * np.sin(2 * math.pi * frequency * t) + 0.08 * np.sin(2 * math.pi * 110 * t)
    with wave.open(str(path), "wb") as audio:
        audio.setparams((1, 2, rate, 0, "NONE", "not compressed"))
        audio.writeframes((np.clip(signal, -1, 1) * 32767).astype("<i2").tobytes())


def main():
    draft = "--draft" in sys.argv
    for name in ("lighthouse-style.vixl", "lighthouse-lyrics.vixl", "lighthouse.mp4", "lighthouse.wav"):
        (HERE / name).unlink(missing_ok=True)
    template(HERE / "lighthouse-style.vixl")
    melody(HERE / "lighthouse.wav")
    request = {
        "audio": "lighthouse.wav",
        "lyrics": "lighthouse.lrc",
        "template": "lighthouse-style.vixl",
        "build": "lighthouse-lyrics.vixl",
        "output": "lighthouse.mp4",
        "fps": 24,
        "quality": "draft" if draft else "final",
        "animation": {"in": "slide-up", "out": "fade-out", "duration": 350},
        "camera": {"from": [0.5, 0.5, 1], "to": [0.5, 0.5, 1.06]},
    }
    report = lyrics.plan(request, HERE)
    print(json.dumps({k: report[k] for k in ("duration_ms", "frames", "sections", "warnings")}, indent=2))
    result = lyrics.export(request, HERE)
    print(json.dumps({"build": result["build"], "video": result["video"]}, indent=2))


if __name__ == "__main__":
    main()
