#!/usr/bin/env python3
"""Build "Vixl in 60 seconds": eleven editable scene masters, a synthesised score, one MP4.

    python make_video.py            # scenes/*.vixl, audio/*.wav, film-spec.json, ../vixl-in-60-seconds.mp4
    python make_video.py --scenes   # only rebuild the scene masters

The film is assembled by Vixl's own ``film-export`` workflow from the .vixl timelines.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import scenes as S  # noqa: E402
from kit import FPS, H, PROMO, W, WHITE, Scene  # noqa: E402

OUTPUT = "vixl-in-60-seconds.mp4"


def measured_contrast():
    """Run the real contrast check on the poster with its dim dates line, so shot 5 quotes Vixl's own numbers."""
    sc = Scene("contrast-probe", 1000)
    sc.add(S.flat(S.poster("p", 0, 0, 640, 800, dates_color=S.DIM_DATES)))
    report = sc.project().check(checks=["contrast"])
    issue = next(i for i in report["issues"] if i["check"] == "contrast" and "'p-dates'" in i["message"])
    before = re.search(r"contrast is ([\d.]+):1", issue["message"]).group(1)
    needs = re.search(r"needs ([\d.]+):1", issue["message"]).group(1)
    fixed = Scene("contrast-probe", 1000)
    fixed.add(S.flat(S.poster("p", 0, 0, 640, 800, dates_color=WHITE)))
    report = fixed.project().check(checks=["bounds", "overlap", "contrast", "fonts"])
    fixes = [i for i in report["issues"] if i["action"] == "fix"]
    if fixes:
        raise RuntimeError(f"The fixed poster should pass every check: {fixes}")
    return before, needs


def scenes():
    out = []
    for make in S.SCENES:
        out.append(make(*measured_contrast()) if make is S.s05_check else make())
    return out


def schedule(shots):
    starts, t = [], 0
    for name, ms in shots:
        starts.append(t)
        t += ms
    return starts, t


def main():
    built = scenes()
    for scene in built:
        scene.build()
        print("built", scene.name, flush=True)
    if "--scenes" in sys.argv:
        return
    import score

    shots = [(sc.name, sc.duration) for sc in built]
    starts, total = schedule(shots)
    audio_dir = PROMO / "audio"
    audio_dir.mkdir(exist_ok=True)
    score.write_all(audio_dir, dict(zip([n for n, _ in shots], starts)), total / 1000)
    spec = {"version": 1, "width": W, "height": H, "fps": FPS,
            "shots": [{"source": f"scenes/{name}.vixl", "duration": ms} for name, ms in shots],
            "audio": [{"source": "audio/music.wav", "start": 0, "volume": 0.7},
                      {"source": "audio/effects.wav", "start": 0, "volume": 0.35}]}
    request = {"output": OUTPUT, "spec": spec}
    (PROMO / "film-spec.json").write_text(json.dumps(request, indent=2) + "\n")
    out = PROMO / OUTPUT
    if out.exists():
        out.unlink()
    subprocess.run(["vixl", "workflow", "film-export", "--request", str(PROMO / "film-spec.json"),
                    "--workspace", str(PROMO)], check=True)


if __name__ == "__main__":
    main()
