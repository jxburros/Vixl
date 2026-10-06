"""Compare the film frame driver against a repository revision; no codec timing claims.

Run: python examples/benchmark_film_static.py afa38bffdb9484f62e77a0357493b2e92a18dddc
Both drivers use the currently installed render engine, isolating frame-loop work.
"""
from pathlib import Path
import json
import statistics
import subprocess
import sys
import tempfile
import time
import types

from vixl import film
from vixl.project import Project


def benchmark(revision):
    source = subprocess.check_output(["git", "show", f"{revision}:src/vixl/film.py"], text=True)
    baseline = types.ModuleType("vixl._baseline_film")
    baseline.__package__ = "vixl"
    exec(compile(source, "baseline_film.py", "exec"), baseline.__dict__)
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        project = Project(1280, 720, "#eee9df")
        project.apply([{"type": "shape", "name": f"shape-{i}", "shape": "ellipse", "width": 80, "height": 80,
                        "x": (i % 12) * 100, "y": (i // 12) * 80, "fill": "#305060"} for i in range(80)])
        project.save(root / "scene.vixl")
        spec = {"width": 1280, "height": 720, "fps": 30, "quality": "draft",
                "shots": [{"source": "scene.vixl", "duration": 10000}]}
        measurements = {"baseline": [], "current": []}
        for _ in range(3):
            for label, module in (("baseline", baseline), ("current", film)):
                started = time.perf_counter()
                for _image in module.frames(spec, root, streamed=True):
                    pass
                measurements[label].append(time.perf_counter() - started)
        return {"baseline_revision": revision, "scene": "80 static ellipses, 1280x720, draft, 300 frames; no encoding",
                "seconds": measurements,
                "median_speedup": statistics.median(measurements["baseline"]) / statistics.median(measurements["current"])}


if __name__ == "__main__":
    print(json.dumps(benchmark(sys.argv[1]), indent=2))
