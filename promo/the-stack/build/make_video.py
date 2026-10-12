#!/usr/bin/env python3
"""Build "The Stack": fourteen editable scene masters, a score written as a Vixl document, one MP4.

    python make_video.py            # scenes/*.vixl, score.vixl, audio/score.wav, film-spec.json, the MP4
    python make_video.py --scenes   # only rebuild the scene masters

The film is assembled by Vixl's own ``film-export`` workflow from the .vixl timelines.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import scenes as S  # noqa: E402
import score  # noqa: E402
from film import FPS, HERE, H, W  # noqa: E402

OUTPUT = "the-stack.mp4"


def main():
    built = S.all_scenes()
    for scene in built:
        scene.build()
        print("built", scene.name, flush=True)
    if "--scenes" in sys.argv:
        return
    starts, total = S.cuts()
    wav, report = score.build(starts, total, S.quiet_spans())
    print("score", report, flush=True)
    spec = {"version": 1, "width": W, "height": H, "fps": FPS,
            "shots": [{"source": f"scenes/{sc.name}.vixl", "duration": sc.duration} for sc in built],
            "audio": [{"source": "audio/score.wav", "start": 0, "volume": 1.0}]}
    (HERE / "film-spec.json").write_text(json.dumps({"output": OUTPUT, "spec": spec}, indent=2) + "\n")
    (HERE / OUTPUT).unlink(missing_ok=True)
    subprocess.run(["vixl", "workflow", "film-export", "--request", str(HERE / "film-spec.json"),
                    "--workspace", str(HERE)], check=True)


if __name__ == "__main__":
    main()
