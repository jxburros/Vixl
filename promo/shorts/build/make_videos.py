#!/usr/bin/env python3
"""Build the ten Vixl shorts: one editable master and one score per short, then one vertical MP4 each.

    python make_videos.py               # every short: work/, scenes/, scores/, audio/, specs/, the MP4s
    python make_videos.py 03 07         # only the shorts whose names start with these prefixes
    python make_videos.py --scenes      # only rebuild the scene masters

Each MP4 is assembled by Vixl's own ``film-export`` workflow from the .vixl timeline and the mixed score.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import score  # noqa: E402
import shorts  # noqa: E402
from short import FPS, HERE, H, W  # noqa: E402


def main():
    wanted = [a for a in sys.argv[1:] if not a.startswith("--")]
    for make in shorts.SHORTS:
        sc = make()
        if wanted and not any(sc.name.startswith(w) for w in wanted):
            continue
        sc.build()
        print("built", sc.name, f"{sc.duration / 1000:g} s", flush=True)
        if "--scenes" in sys.argv:
            continue
        wav, report = score.build(sc)
        print("score", sc.name, report.get("peak", ""), flush=True)
        spec = {"version": 1, "width": W, "height": H, "fps": FPS,
                "shots": [{"source": f"scenes/{sc.name}.vixl", "duration": sc.duration}],
                "audio": [{"source": f"audio/{sc.name}.wav", "start": 0, "volume": 1.0}]}
        output = f"vixl-short-{sc.name}.mp4"
        (HERE / "specs").mkdir(exist_ok=True)
        request = HERE / "specs" / f"{sc.name}.json"
        request.write_text(json.dumps({"output": output, "spec": spec}, indent=2) + "\n")
        (HERE / output).unlink(missing_ok=True)
        subprocess.run(["vixl", "workflow", "film-export", "--request", str(request), "--workspace", str(HERE)],
                       check=True, stdout=subprocess.DEVNULL)
        print("video", output, flush=True)


if __name__ == "__main__":
    main()
