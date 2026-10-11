#!/usr/bin/env python3
"""Build "Brew": eleven editable scene masters, a synthesised score, one MP4.

    python make_video.py            # scenes/*.vixl, audio/*.wav, film-spec.json, ../brew.mp4
    python make_video.py --scenes   # only rebuild the scene masters

The film is assembled by Vixl's own ``film-export`` workflow from the .vixl timelines.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import potion as P  # noqa: E402
import shots as S  # noqa: E402
from kit import FPS, H, W  # noqa: E402
from vixl import Project  # noqa: E402
from vixl.typefaces import install_font  # noqa: E402

OUTPUT = "brew.mp4"
CHECKS = ["bounds", "overlap", "contrast", "fonts"]


def measured_checks():
    """Check the hero poster at its real 1080 x 1350 size, so shot 3 quotes Vixl's own report."""
    project = Project(1080, 1350, S.NIGHT)
    install_font(project, "Inter Tight", 800, role="heading")
    install_font(project, "Inter", 600)
    project.apply(P.flat(P.harvest("p", 0, 0, 1080, 1350)), detail="brief")
    report = project.check(checks=CHECKS)
    fixes = [i for i in report["issues"] if i["action"] == "fix"]
    if fixes:
        raise RuntimeError(f"The hero poster should have nothing to fix: {fixes}")
    layers = [layer for layer in project.state["layers"] if layer["type"] != "group"]
    return {"checks": len(CHECKS), "fixes": len(fixes), "layers": len(layers)}


def scenes():
    out = []
    for make in S.SCENES:
        out.append(make(measured_checks()) if make is S.s03_ready else make())
    return out


def main():
    built = scenes()
    for scene in built:
        scene.build()
        print("built", scene.name, flush=True)
    if "--scenes" in sys.argv:
        return
    import score

    shots = [(sc.name, sc.duration) for sc in built]
    starts, t = {}, 0
    for name, ms in shots:
        starts[name] = t
        t += ms
    audio_dir = S.BREW_DIR / "audio"
    audio_dir.mkdir(exist_ok=True)
    score.write_all(audio_dir, starts, t / 1000)
    spec = {"version": 1, "width": W, "height": H, "fps": FPS,
            "shots": [{"source": f"scenes/{name}.vixl", "duration": ms} for name, ms in shots],
            "audio": [{"source": "audio/music.wav", "start": 0, "volume": 0.7},
                      {"source": "audio/effects.wav", "start": 0, "volume": 0.4}]}
    (S.BREW_DIR / "film-spec.json").write_text(json.dumps({"output": OUTPUT, "spec": spec}, indent=2) + "\n")
    out = S.BREW_DIR / OUTPUT
    if out.exists():
        out.unlink()
    subprocess.run(["vixl", "workflow", "film-export", "--request", str(S.BREW_DIR / "film-spec.json"),
                    "--workspace", str(S.BREW_DIR)], check=True)


if __name__ == "__main__":
    main()
