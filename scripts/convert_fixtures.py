"""Generate the conversion-kit fixtures: small documents saved and rendered by older Vixl releases.

    python -m scripts.convert_fixtures                 # every release in RELEASES
    python -m scripts.convert_fixtures v0.20.0 v0.26.0  # some of them

For each git revision the script extracts that revision's ``src`` into a temporary folder (``git archive``), runs
itself there with ``--build`` under that code, and writes ``tests/fixtures/convert/<revision>/<doc>.vixl`` plus
``<doc>.png`` (the old code's own render) and ``manifest.json`` (the release, and the operations each document holds
or skipped because that release did not have them). The tests convert these documents with the current code and
compare their renders with the PNGs. Existing files are replaced only with ``--overwrite``.
"""

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "tests" / "fixtures" / "convert"
# v0.10.0 writes archive format 1; v0.20.0 predates the 0.21 render changes (lookup field, open-shape fill, the old
# temperature/tint scale); v0.22.1 predates the 0.23 strength and leading defaults; v0.26.0 is the last release with
# house-style versioning; afaee33 is main before the compatibility code was removed.
RELEASES = ("v0.10.0", "v0.20.0", "v0.22.1", "v0.26.0", "afaee33")

SPRITE = ["..####..", ".#oooo#.", "#oo##oo#", "#oooooo#", "#o#oo#o#", "#oo##oo#", ".#oooo#.", "..####.."]
LUT = [[r / 1, g / 1, b / 1] for b in (0, 1) for g in (0, 1) for r in (0, 1)]
WARM_LUT = [[min(1, r * 0.9 + 0.1), g * 0.95, b * 0.7] for r, g, b in LUT]

# name: (width, height, operations). Operations an older release lacks are skipped and recorded.
DOCS = {
    "shapes": (240, 160, [
        {"type": "shape", "shape": "rectangle", "name": "rect", "x": 8, "y": 8, "width": 70, "height": 46,
         "fill": "#ffd166", "stroke": "#073b4c", "stroke_width": 8},
        {"type": "shape", "shape": "rounded-rectangle", "name": "rounded", "x": 86, "y": 8, "width": 70, "height": 46,
         "radius": 16, "fill": "#06d6a0", "stroke": "#073b4c", "stroke_width": 6},
        {"type": "shape", "shape": "capsule", "name": "pill", "x": 164, "y": 8, "width": 68, "height": 30,
         "fill": "#118ab2", "stroke": "#073b4c", "stroke_width": 6},
        {"type": "shape", "shape": "ellipse", "name": "oval", "x": 8, "y": 64, "width": 70, "height": 46,
         "fill": "#ef476f", "stroke": "#073b4c", "stroke_width": 10},
        {"type": "shape", "shape": "polygon", "name": "hexagon", "x": 90, "y": 62, "width": 52, "height": 52, "sides": 6,
         "fill": "#ffd166", "stroke": "#073b4c", "stroke_width": 6},
        {"type": "shape", "shape": "ellipse", "name": "dashed", "x": 156, "y": 52, "width": 76, "height": 56,
         "fill": "#ffffff", "stroke": "#ef476f", "stroke_width": 6, "dash": [12, 6]},
        {"type": "shape", "shape": "line", "name": "rule", "x": 8, "y": 120, "width": 224, "height": 8,
         "stroke": "#073b4c", "stroke_width": 4},
        {"type": "shape", "shape": "path", "name": "open path", "x": 150, "y": 118, "width": 80, "height": 36,
         "path": "M 4 32 L 40 4 L 76 32", "stroke": "#073b4c", "stroke_width": 4},
        {"type": "shape", "shape": "rectangle", "name": "tilted", "x": 20, "y": 130, "width": 60, "height": 20,
         "fill": "#118ab2", "stroke": "#073b4c", "stroke_width": 4, "rotation": 10},
    ]),
    "text": (240, 160, [
        {"type": "text", "name": "title", "text": "Spring market on the square", "x": 10, "y": 8, "size": 22,
         "color": "#1d3557"},
        {"type": "text-layout", "target": "title", "width": 200},
        {"type": "text", "name": "body", "text": "Fresh bread, flowers and music every Saturday morning.",
         "x": 10, "y": 96, "size": 13, "color": "#333333"},
        {"type": "text-layout", "target": "body", "width": 210},
    ]),
    "chart": (240, 160, [
        {"type": "chart", "name": "sales", "kind": "bar", "categories": ["Q1", "Q2", "Q3", "Q4"],
         "series": [{"name": "2025", "values": [3, 5, 4, 6]}], "x": 0, "y": 0, "width": 240, "height": 160},
    ]),
    "sprite": (96, 64, [
        {"type": "pixel-art", "name": "coin", "rows": SPRITE, "palette": {".": "transparent", "#": "#5c3c00",
                                                                          "o": "#f4c430"}, "x": 8, "y": 8},
        {"type": "resize", "target": "coin", "width": 48, "height": 48},
        {"type": "keyframe", "target": "coin", "property": "x", "time": 0, "value": 8},
        {"type": "keyframe", "target": "coin", "property": "x", "time": 1000, "value": 40},
    ]),
    "irregular": (240, 160, [
        {"type": "shape", "shape": "rectangle", "name": "card", "x": 20, "y": 20, "width": 90, "height": 70,
         "fill": "#f1faee", "stroke": "#1d3557", "stroke_width": 3},
        {"type": "irregular", "target": "card", "seed": 3},
        {"type": "shape", "shape": "rectangle", "name": "paper", "x": 130, "y": 20, "width": 90, "height": 110,
         "fill": "#e9c46a"},
        {"type": "tear", "target": "paper", "seed": 5, "edges": ["bottom"]},
    ]),
    "effects": (240, 160, [
        {"type": "gradient", "name": "sky", "start": "#457b9d", "end": "#f4a261", "width": 240, "height": 160},
        {"type": "lut", "name": "warm", "size": 2, "values": WARM_LUT},
        {"type": "lookup", "target": "sky", "name": "warm", "amount": 0.8},
        {"type": "shape", "shape": "ellipse", "name": "sun", "x": 150, "y": 20, "width": 60, "height": 60,
         "fill": "#e9c46a"},
        {"type": "effect", "target": "sun", "name": "temperature", "amount": 40},
        {"type": "shape", "shape": "rectangle", "name": "card", "x": 30, "y": 70, "width": 80, "height": 50,
         "fill": "#2a9d8f"},
        {"type": "effect", "target": "card", "name": "tint", "amount": 4},
    ]),
    "diagram": (240, 160, [
        {"type": "diagram", "name": "flow", "x": 0, "y": 0, "width": 240, "height": 160,
         "nodes": [{"id": "a", "label": "Idea"}, {"id": "b", "label": "Sketch the plan"}, {"id": "c", "label": "Ship"}],
         "edges": [{"from": "a", "to": "b"}, {"from": "b", "to": "c"}]},
    ]),
}


def build(out):
    import vixl
    from vixl.project import Project

    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    manifest = {"vixl_version": vixl.__version__, "documents": {}}
    plans = dict(DOCS)
    try:
        designed = Project(240, 160, seed=7, workspace_fonts=False)
    except TypeError:
        designed = None  # Releases before 0.23 have no designed documents.
    for name, (width, height, operations) in plans.items():
        project = Project(width, height, "white")
        made, skipped = [], []
        for op in operations:
            try:
                project.apply([op])
                made.append(op.get("name") or f"{op['type']} {op.get('target', '')}".strip())
            except Exception as exc:  # noqa: BLE001 - an older release lacks the operation or a field
                skipped.append({"operation": op["type"], "name": op.get("name") or op.get("target"),
                                "error": str(exc)[:160]})
        if not made:
            continue
        project.save(str(out / f"{name}.vixl"))
        project.export(str(out / f"{name}.png"))
        manifest["documents"][name] = {"made": made, "skipped": skipped}
    if designed is not None:
        made = []
        for op in ({"type": "text", "name": "headline", "text": "Open studio night", "x": 12, "y": 10, "size": 20},
                   {"type": "text-layout", "target": "headline", "width": 160},
                   {"type": "chart", "name": "visits", "kind": "bar", "categories": ["Fri", "Sat", "Sun"],
                    "series": [{"name": "visits", "values": [12, 30, 18]}], "x": 0, "y": 60, "width": 240,
                    "height": 100}):
            designed.apply([op])
            made.append(op["name"] if "name" in op else op["type"])
        designed.save(str(out / "designed.vixl"))
        designed.export(str(out / "designed.png"))
        manifest["documents"]["designed"] = {"made": made, "skipped": [],
                                             "house_style_version": designed.state["design_defaults"].get(
                                                 "house_style_version")}
    for lock in out.glob("*.lock"):  # file locks some releases leave beside a saved document
        lock.unlink()
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1, sort_keys=True) + "\n")


def generate(revision, overwrite=False):
    target = OUT / revision
    if target.exists():
        if not overwrite:
            print(f"{revision}: {target.relative_to(ROOT)} exists; pass --overwrite to replace it")
            return
        shutil.rmtree(target)
    with tempfile.TemporaryDirectory() as tmp:
        archive = Path(tmp) / "src.tar"
        subprocess.run(["git", "archive", "-o", str(archive), revision, "src"], cwd=ROOT, check=True)
        with tarfile.open(archive) as tar:
            tar.extractall(tmp, filter="data")
        env = dict(os.environ, PYTHONPATH=str(Path(tmp) / "src"), VIXL_AUTO_FONTS="off")
        # Run from the temporary folder so the old code reads no workspace brand or fonts.
        subprocess.run([sys.executable, str(Path(__file__).resolve()), "--build", str(target)], cwd=tmp, env=env,
                       check=True)
    print(f"{revision}: wrote {target.relative_to(ROOT)}")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("revisions", nargs="*", default=list(RELEASES))
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--build", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.build:
        build(args.build)
        return
    for revision in args.revisions:
        generate(revision, args.overwrite)


if __name__ == "__main__":
    main()
