"""Generate the inputs the shots show, by running the real Vixl features on them.

Nothing here is mocked up: the sketch is cleaned and vectorized by the drawing pipeline, the badge run is
a ``merge-impose`` of a CSV with live QR codes, and the emoji is the bundled editable master. The numbers
on screen (lines kept, sheets, emoji count) are read from these results.
"""
from __future__ import annotations

import csv
import json
import subprocess
import sys
from functools import cache

from film import INK, ROOT, WORK

sys.path.insert(0, str(ROOT / "examples"))

FIRST = ["Ada", "Grace", "Alan", "Edsger", "Barbara", "Ken", "Margaret", "Donald", "Frances", "Radia",
         "Hedy", "Claude", "Katherine", "Tim", "Sophie", "Linus", "Joan", "Dennis", "Annie", "Guido"]
LAST = ["Okafor", "Lindqvist", "Moreau", "Tanaka", "Silva", "Novak", "Haddad", "Kowalski", "Reyes", "Chen",
        "Byrne", "Osei", "Ferreira", "Nakamura", "Duarte", "Weiss", "Kaur", "Ivanova", "Mensah", "Park"]
ORGS = ["Northwind Press", "Atlas Studio", "Kite & Co.", "Orbital Labs", "Pine Ridge Museum", "Lumen Health",
        "Harbor Bikes", "Field Notes Radio"]
BADGES = 200


def vixl(*args, cwd=WORK):
    out = subprocess.run(["vixl", "--json", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout
    return json.loads(out)


@cache
def sketch():
    """The drawing pipeline from examples/build_drawing_pipeline.py: photo, cleaned, finished, report."""
    import build_drawing_pipeline as dp

    photo = dp.sketch_photo()
    cleaned, finished, _compared, report = dp.pipeline(photo)
    paths = {}
    for key, image in (("photo", photo), ("cleaned", cleaned), ("finished", finished)):
        paths[key] = WORK / f"sketch-{key}.png"
        image.convert("RGB").save(paths[key])
    return paths, report


@cache
def badges():
    """A 3.5 x 2.25 in badge template with ${name}, ${org} and a QR of ${id}, merged from a CSV and imposed."""
    from vixl import Project

    t = Project(1050, 675, "#FFFFFF")
    t.state["canvas"]["dpi"] = 300
    t.apply([
        {"type": "variable", "name": "name", "value": "Ada Okafor"},
        {"type": "variable", "name": "org", "value": "Atlas Studio"},
        {"type": "variable", "name": "id", "value": "0001"},
        {"type": "shape", "shape": "rectangle", "name": "band", "x": 0, "y": 0, "width": 1050, "height": 150,
         "fill": "#3575EE"},
        {"type": "shape", "shape": "rectangle", "name": "stripe", "x": 0, "y": 150, "width": 1050, "height": 14,
         "fill": "#FFC94D"},
        {"type": "text", "name": "event", "text": "VIXLCONF  ·  2026", "x": 56, "y": 48, "size": 56,
         "color": "#FFFFFF"},
        {"type": "text", "name": "who", "text": "${name}", "x": 56, "y": 250, "size": 76, "color": INK},
        {"type": "text", "name": "org", "text": "${org}", "x": 56, "y": 370, "size": 44, "color": "#5A6377"},
        {"type": "text", "name": "badge-no", "text": "No. ${id}", "x": 56, "y": 560, "size": 34, "color": "#8A93A6"},
        {"type": "qr", "name": "code", "data": "https://vixl.example/badge/${id}", "x": 760, "y": 300,
         "size": 250, "color": INK},
    ], detail="brief")
    t.save(str(WORK / "badge.vixl"), overwrite=True)
    with open(WORK / "people.csv", "w", newline="") as f:
        out = csv.writer(f)
        out.writerow(["id", "name", "org"])
        for i in range(BADGES):
            out.writerow([f"{i + 1:04d}", f"{FIRST[i % 20]} {LAST[(i * 7 + i // 20) % 20]}", ORGS[(i * 3) % 8]])
    request = {"template": "badge.vixl", "data": "people.csv", "output": "sheets.vixl", "replace": True,
               "sheet": {"size": "letter", "cols": 2, "rows": 4, "margin": 0.5, "gutter": 0.25,
                         "crop_marks": True, "registration": True, "slug": "VixlConf badges  ·  sheet {page} of {pages}"}}
    (WORK / "merge.json").write_text(json.dumps(request))
    result = vixl("workflow", "merge-impose", "--request", "merge.json", "--workspace", ".")
    sheets = []
    for page in (1, 2, 3):
        path = WORK / f"sheet-{page}.png"
        path.unlink(missing_ok=True)
        vixl("-p", "sheets.vixl", "--allow-linked", "render", "--page", str(page), "--out", path.name)
        sheets.append(path)
    with open(WORK / "people.csv") as f:
        rows = list(csv.reader(f))
    return {"sheets": sheets, "pages": result["pages"], "rows": result["rows"], "valid": result["valid"],
            "errors": len(result["errors"]), "csv": rows[:7]}


@cache
def emoji(symbol="\N{UNICORN FACE}"):
    """The bundled editable master of one emoji, plus its catalog entry and the catalog size."""
    listing = vixl("emoji", "list")
    path = WORK / "emoji.vixl"
    vixl("emoji", "get", symbol, "--out", path.name, "--overwrite")
    entry = next(e for e in vixl("emoji", "list", "--query", "unicorn")["entries"] if e["emoji"] == symbol)
    return path, entry, listing["unicode_count"]
