#!/usr/bin/env python3
"""Compose the score and assemble the finished film with Vixl's ``film-export`` workflow.

    python build.py          # 1. build the animated scene masters into ../scenes/
    python make_film.py      # 2. synthesise audio, then export ../the-germ-king.mp4

The film is plain Vixl: every shot is an editable .vixl timeline, joined with crossfades,
camera moves and an explicit audio mix by the ``film-plan`` / ``film-export`` workflows.
"""
import json
import math
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import numpy as np  # noqa: E402

import scenes  # noqa: E402
import scenes_b  # noqa: E402
import score  # noqa: E402
from vixlkit import VIXL  # noqa: E402

ROOT = os.path.abspath(os.path.join(HERE, ".."))
FPS = 24
XFADE = 400  # ms of crossfade between shots
OUTPUT = "the-germ-king.mp4"

# (scene master, duration ms, optional slow camera move [from, to])
SHOTS = [
    ("01-council", 9000, [[0.5, 0.5, 1.0], [0.5, 0.53, 1.06]]),
    ("02-shrink", 6000, [[0.5, 0.5, 1.0], [0.4, 0.6, 1.22]]),
    ("03-arrival", 7000, [[0.5, 0.5, 1.0], [0.5, 0.55, 1.06]]),
    ("04-coronation", 7000, [[0.5, 0.5, 1.0], [0.5, 0.52, 1.07]]),
    ("05-march", 5500, [[0.45, 0.5, 1.07], [0.55, 0.5, 1.07]]),
    ("06-sneeze", 5200, [[0.5, 0.5, 1.0], [0.5, 0.5, 1.04]]),
    ("07-aftermath", 9500, [[0.5, 0.5, 1.0], [0.5, 0.5, 1.05]]),
    ("08-title", 4500, None),
]


def schedule():
    """Film start time (s) of each shot, mirroring Vixl's frame-accurate crossfade overlap."""
    starts, frame = {}, 0
    overlap = round(XFADE * FPS / 1000)
    for i, (name, ms, _) in enumerate(SHOTS):
        frame -= overlap if i else 0
        starts[name] = frame / FPS
        frame += math.ceil(ms * FPS / 1000)
    return starts, frame / FPS


def main():
    starts, total = schedule()
    docs = {d.name: d for d in (make() for make in scenes.SCENES + scenes_b.SCENES)}
    talks = {name: doc.talks for name, doc in docs.items()}
    print(f"film length {total:.1f}s; synthesising score ...", flush=True)
    music, sfx = score.build_audio(starts, talks, total)
    os.makedirs(os.path.join(ROOT, "audio"), exist_ok=True)
    for track in (music, sfx):  # fade the last 0.9 s out, the first 80 ms in
        n_out, n_in = int(0.9 * score.SR), int(0.08 * score.SR)
        track[-n_out:] *= np.linspace(1, 0, n_out)
        track[:n_in] *= np.linspace(0, 1, n_in)
    score.write_wav(os.path.join(ROOT, "audio", "score.wav"), music, 0.8)
    score.write_wav(os.path.join(ROOT, "audio", "effects.wav"), sfx, 0.9)

    spec = {
        "version": 1, "width": 1280, "height": 720, "fps": FPS,
        "shots": [],
        "audio": [
            {"source": "audio/score.wav", "start": 0, "volume": 0.5},
            {"source": "audio/effects.wav", "start": 0, "volume": 0.6},
        ],
    }
    for i, (name, ms, camera) in enumerate(SHOTS):
        shot = {"source": f"scenes/{name}.vixl", "duration": ms}
        if i:
            shot["transition"] = XFADE
        if camera:
            shot["camera"] = {"from": camera[0], "to": camera[1]}
        spec["shots"].append(shot)
    request = {"output": OUTPUT, "spec": spec}
    req_path = os.path.join(ROOT, "film-spec.json")
    with open(req_path, "w") as fh:
        json.dump(request, fh, indent=2)
    out = os.path.join(ROOT, OUTPUT)
    if os.path.exists(out):
        os.remove(out)
    print("film-plan ...", flush=True)
    plan_path = os.path.join(ROOT, ".film-plan-request.json")
    with open(plan_path, "w") as fh:
        json.dump({"spec": spec}, fh)
    subprocess.run([VIXL, "workflow", "film-plan", "--request", plan_path, "--workspace", ROOT], check=True)
    os.remove(plan_path)
    print("film-export (this renders every frame) ...", flush=True)
    subprocess.run([VIXL, "workflow", "film-export", "--request", req_path, "--workspace", ROOT], check=True)


if __name__ == "__main__":
    main()
