"""Aetherling Spirits: a data-driven trading-card set built with Vixl.

Run from the repository root:

    python explorations/07-trading-cards/build.py

Everything is written to explorations/07-trading-cards/output/ (wiped first).
"""

import atexit
import csv
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "output"
if OUT.exists():
    shutil.rmtree(OUT)
OUT.mkdir(parents=True)
# Keep all Vixl resource/job state inside this exploration's folder.
os.environ["VIXL_RESOURCES"] = str(OUT / ".vixl-resources.json")
os.environ["VIXL_NO_UPDATE"] = "1"
sys.path.insert(0, str(HERE))

from PIL import Image  # noqa: E402

from vixl import Project  # noqa: E402
from vixl.assets import add_encoded  # noqa: E402
from vixl.interfaces import Session  # noqa: E402
from vixl.workflows import dispatch  # noqa: E402

from art import make_art  # noqa: E402
from cards import CARDS, ELEMENT_COLORS, RARITY  # noqa: E402
from template import ABILITY_BOX, FLAVOR_BOX, NAME_BOX, CW, CH, build_template  # noqa: E402

T0 = time.time()
LOG = []


def log(*parts):
    line = f"[{time.time() - T0:6.1f}s] " + " ".join(str(p) for p in parts)
    print(line, flush=True)
    LOG.append(line)


def slug(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:32] or "card"


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False))


# ---------------------------------------------------------------- 1. creature art
(OUT / "art").mkdir()
art_files = {}
for i, card in enumerate(CARDS):
    name, element, seed = card[0], card[1], card[-1]
    path = OUT / "art" / f"{i + 1:02d}-{slug(name)}.jpg"
    make_art(seed, element, path)
    art_files[i] = path
for element in ELEMENT_COLORS:
    path = OUT / "art" / f"element-{element.lower()}.jpg"
    make_art(100 + len(element), element, path)
    art_files[element] = path
log("art: painted", len(art_files), "creature scenes with Vixl paint/pen/shape ops")

# ---------------------------------------------------------------- 2. template
(OUT / "template").mkdir()
template = build_template(art_files[0].read_bytes())
asset_ids = {key: add_encoded(template, path.read_bytes())[0] for key, path in art_files.items()}

FIT_ACTIONS = {
    # repair actions: bake a fitted size (fit-text) so text-fit rules can measure it
    "fit-name": [{"type": "fit-text", "target": "card-name", "width": NAME_BOX[2], "height": NAME_BOX[3],
                  "minimum": 22, "maximum": 50}],
    "fit-rules": [
        {"type": "fit-text", "target": "ability", "width": ABILITY_BOX[2], "height": ABILITY_BOX[3],
         "minimum": 16, "maximum": 27},
        {"type": "fit-text", "target": "flavor", "width": FLAVOR_BOX[2], "height": FLAVOR_BOX[3],
         "minimum": 14, "maximum": 24},
    ],
}
SUITE = {
    "version": 1,
    "rules": [
        # minimum sizes in px at 300 dpi: name >= 7 pt, ability >= 5.5 pt, flavor >= 5 pt
        {"id": "name-fits", "kind": "text-fit", "target": "card-name", "minimum": 29},
        {"id": "ability-fits", "kind": "text-fit", "target": "ability", "minimum": 23},
        {"id": "flavor-fits", "kind": "text-fit", "target": "flavor", "minimum": 21},
        {"id": "trim-width", "kind": "property", "target": "canvas", "field": "width", "expected": CW},
        {"id": "trim-height", "kind": "property", "target": "canvas", "field": "height", "expected": CH},
        # `property` compares the *resolved* font (the embedded asset path), not the registered name or
        # the "heading" role, so the expected value is filled in below from state["fonts"].
        {"id": "name-font", "kind": "property", "target": "card-name", "field": "font", "expected": None},
        {"id": "name-to-art", "kind": "gap", "before": "name-bar", "after": "art", "axis": "vertical",
         "expected": 14},
        {"id": "art-to-type", "kind": "gap", "before": "art", "after": "type-bar", "axis": "vertical",
         "expected": 18},
        {"id": "rules-box-palette", "kind": "palette", "region": [64, 724, 622, 184],
         "colors": ["#f4ead2", "#14100c", "#5b4a36", "#a99a80"], "tolerance": 40, "max_fraction": 0.04},
        {"id": "art-inside", "kind": "assert", "expression": "layer.art.bounds within canvas"},
        {"id": "name-contrast", "kind": "design",
         "options": {"checks": ["contrast", "bounds"], "targets": ["card-name", "ability"]}},
    ],
}
SUITE["rules"][5]["expected"] = template.state["fonts"]["cinzel-700"]
template.apply(
    [{"type": "action-define", "name": k, "action": {"operations": v}} for k, v in FIT_ACTIONS.items()]
    + [{"type": "suite-set", "name": "card-qa", "suite": SUITE},
       {"type": "variable", "name": "art", "value": asset_ids[0]}]
    # Project.save() prunes embedded assets nothing references, so keep the art pool alive
    # through (otherwise unused) variables.
    + [{"type": "variable", "name": f"pool_{key}".lower(), "value": asset}
       for key, asset in asset_ids.items()],
    detail="compact",
)
template_path = OUT / "template" / "aetherling-card.vixl"
template.save(template_path)
session = Session(str(template_path), workspace=str(OUT))
# attach the built-in "no-placeholders" starter suite next to the custom one
dispatch(session, "suite-use", {"name": "no-placeholders"})
template = Project.load(template_path)
template.export(str(OUT / "template" / "template-standard.webp"), quality=85)
template.export(str(OUT / "template" / "template-holo.webp"), comp="holo", quality=85)
log("template: saved", template_path.relative_to(HERE), "with", len(template.state["layers"]), "layers")

# ---------------------------------------------------------------- 3. CSV
rows = []
for i, (name, element, rarity, kind, cost, atk, df, spd, ab_name, ability, flavor, seed) in enumerate(CARDS):
    main, dark, light = ELEMENT_COLORS[element]
    badge, pips = RARITY[rarity]
    rows.append({
        "name": name, "cost": str(cost), "element": element, "element_color": main, "element_dark": dark,
        "element_light": light, "kind": kind, "rarity": rarity, "rarity_color": badge, "rarity_pips": pips,
        "ability_name": ab_name, "ability": ability, "flavor": flavor, "atk": str(atk), "def": str(df),
        "spd": str(spd), "set_no": f"{i + 1:03d}", "edition": "First Edition",
        "art": os.path.relpath(art_files[i], OUT / "data"),
    })
(OUT / "data").mkdir()
csv_path = OUT / "data" / "cards.csv"
with csv_path.open("w", newline="", encoding="utf-8") as stream:
    writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
log("csv: wrote", len(rows), "rows ->", csv_path.relative_to(HERE))

# Agent-side lint: the built-in "no-placeholders" suite only knows layout/template blanks.
PLACEHOLDER = re.compile(r"\[[A-Z ]+\]|\bTBD\b|\bTODO\b|lorem ipsum", re.I)
lint = {i + 1: sorted({k for k, v in r.items() if isinstance(v, str) and PLACEHOLDER.search(v)})
        for i, r in enumerate(rows)}
lint = {k: v for k, v in lint.items() if v}

# ---------------------------------------------------------------- 4. render the set from CSV (CLI)
# The holo set skips Vixl's per-row design check; the standard set keeps it (default) and runs in the
# background because a full design check of this 13-text-layer card is slow (see README).
standard_dir, holo_dir = OUT / "set" / "standard", OUT / "set" / "holo"
standard_proc = subprocess.Popen(
    ["vixl", "--json", "-p", str(template_path), "render", "--data", str(csv_path), "--out", str(standard_dir)],
    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
atexit.register(lambda: standard_proc.poll() is None and standard_proc.kill())  # never orphan it
# Every CLI command -- even a read-only `render --data` -- holds the project's write lock for its whole
# run, and a second command gives up after 10 s, so render the holo set from a copy.
holo_copy = OUT / "template" / "_holo-render-copy.vixl"
shutil.copy(template_path, holo_copy)
holo = subprocess.run(
    ["vixl", "--json", "-p", str(holo_copy), "render", "--data", str(csv_path), "--out", str(holo_dir),
     "--comp", "holo", "--no-check"], capture_output=True, text=True)
holo_copy.unlink()
log("render --data --comp holo:", "ok" if holo.returncode == 0 else (holo.stdout + holo.stderr)[-500:])

# ---------------------------------------------------------------- 5. recipe capture
# The recipe uses static text boxes (fit:false) so the text-fit rules can measure them; the
# fit-name / fit-rules actions are the repair path.
source = Project.load(template_path)
source.apply(
    [{"type": "text-layout", "target": t, "width": box[2], "height": box[3], "fit": False}
     for t, box in (("card-name", NAME_BOX), ("ability", ABILITY_BOX), ("flavor", FLAVOR_BOX))]
    + [{"type": "artboard", "name": r.lower(), "width": CW, "height": CH,
        "variables": {"rarity": r, "rarity_color": RARITY[r][0], "rarity_pips": RARITY[r][1]}}
       for r in RARITY],
    detail="compact",
)
source.path, source._revision = None, None
source_path = OUT / "template" / "recipe-source.vixl"
source.save(source_path)
session = Session(str(source_path), workspace=str(OUT))


def text_input(default=None, max_length=200, required=True):
    spec = {"type": "string", "maxLength": max_length}
    if default is not None:
        spec["default"] = default
    if not required:
        spec["required"] = False
    return spec


recipe = {
    "version": 1,
    "inputs": {
        "name": text_input("Cinderwisp", 120),
        "cost": {"type": "string", "default": "1", "enum": [str(n) for n in range(0, 11)]},
        "element": {"type": "string", "default": "Ember", "enum": list(ELEMENT_COLORS)},
        "element_color": {"type": "color", "default": "#ff6b35"},
        "element_dark": {"type": "color", "default": "#2a0905"},
        "element_light": {"type": "color", "default": "#ffd166"},
        "kind": text_input("Spirit — Wisp", 60),
        # rarity inputs have no default so artboard variables can supply them
        "rarity": {"type": "string", "enum": list(RARITY), "required": False},
        "rarity_color": {"type": "color", "required": False},
        "rarity_pips": text_input(None, 8, required=False),
        "ability_name": text_input("Kindle", 40),
        "ability": text_input(None, 600, required=False),
        "flavor": text_input(None, 600, required=False),
        "atk": text_input("2", 2), "def": text_input("1", 2), "spd": text_input("4", 2),
        "set_no": text_input("001", 3), "edition": text_input("First Edition", 30),
        "art": {"type": "asset", "default": asset_ids[0]},
    },
    "examples": [
        {"name": "Tidecaller Maru", "element": "Tide", "element_color": "#2ec4ff", "element_dark": "#03182b",
         "element_light": "#c9f6ff", "art": asset_ids[1]},
    ],
}
captured = dispatch(session, "capture", {"output": "recipe/card-recipe.vixl", "recipe": recipe})
log("capture:", captured["output"], "inputs:", len(captured["recipe"]["inputs"]))

# A recipe example that cannot pass the suites is refused at capture time (record the error).
bad_recipe = json.loads(json.dumps(recipe))
bad_recipe["examples"] = [{"name": CARDS[5][0]}]
try:
    dispatch(session, "capture", {"output": "recipe/should-not-exist.vixl", "recipe": bad_recipe})
    capture_refusal = "accepted (unexpected)"
except Exception as exc:  # noqa: BLE001
    capture_refusal = f"{type(exc).__name__}: {str(exc)[:200]}"
log("capture with a long-name example:", capture_refusal)

recipe_session = Session("recipe/card-recipe.vixl", workspace=str(OUT))

# ---------------------------------------------------------------- 6. variation matrix: element x rarity x edition
element_rows = []
for element in ("Ember", "Tide", "Storm"):
    main, dark, light = ELEMENT_COLORS[element]
    element_rows.append({"name": f"{element} Warden", "element": element, "element_color": main,
                         "element_dark": dark, "element_light": light, "art": asset_ids[element],
                         "kind": "Spirit — Warden", "ability_name": "Ward",
                         "ability": f"Other {element} spirits you control get +1 DEF.",
                         "flavor": f"Every {element.lower()} shrine keeps one awake."})
matrix_spec = {
    "version": 1,
    "rows": element_rows,
    "artboards": [r.lower() for r in RARITY],
    "matrix": {"edition": ["First Edition", "Unlimited"]},
    "quality": "draft",
    "format": "webp",
    "workers": 2,
    "suites": ["card-qa", "no-placeholders"],
    "repair_actions": ["fit-name", "fit-rules"],
}
planned = dispatch(recipe_session, "plan", {"spec": matrix_spec})
write_json(OUT / "production" / "matrix-plan.json", planned)
log("plan: matrix count =", planned["count"])
matrix = dispatch(recipe_session, "run", {"output": "production/matrix", "spec": matrix_spec})
log("run matrix:", matrix["status"], {s: sum(r["status"] == s for r in matrix["results"])
                                       for s in {r["status"] for r in matrix["results"]}})

# ---------------------------------------------------------------- 7. durable job: checked production of the CSV set
csv_rows = []
for i, row in enumerate(rows):
    values = {k: v for k, v in row.items() if k != "art"}
    values["art"] = asset_ids[i]
    csv_rows.append(values)
job_spec = {
    # workers=1: with 2 workers a fresh worker process races on the shared font cache (see README)
    "version": 1, "rows": csv_rows, "quality": "final", "format": "webp", "workers": 1,
    "suites": ["card-qa", "no-placeholders"], "repair_actions": ["fit-name", "fit-rules"],
}
submitted = dispatch(recipe_session, "submit", {
    "start": True, "workers": 2,
    "job": {"kind": "production", "source": "recipe/card-recipe.vixl", "output": "production/csv-set",
            "spec": job_spec}})
job_id = submitted["id"]
log("submit: job", job_id, "status", submitted.get("status"))
status_trace = []


def wait_for_job():
    while True:
        status = dispatch(recipe_session, "status", {"id": job_id})
        entry = {k: status.get(k) for k in ("status", "progress", "attempts", "error") if k in status}
        if not status_trace or status_trace[-1] != entry:
            status_trace.append(entry)
            log("status:", entry)
        if status.get("status") not in ("queued", "running", "waiting"):
            return status
        time.sleep(3)


status = wait_for_job()
# With workers=2 the first two variants can race on a cold font cache inside the worker process
# (fontTools "illegal use of getGlyphOrder()", surfaced only as {"error": "AttributeError"}).
# Such crashes are not design failures: resume the job; production reuses verified outputs.
crashed = [r for r in status.get("result", {}).get("results", [])
           if r["status"] == "failed" and r.get("error", {}).get("error") in ("AttributeError", "TTLibError",
                                                                             "KeyError")]
resumed = None
if crashed:
    log("job: retrying", [r["id"] for r in crashed], "after worker crash", [r["error"] for r in crashed])
    resumed = dispatch(recipe_session, "resume", {"id": job_id})
    dispatch(recipe_session, "start", {"workers": 1})
    status = wait_for_job()
write_json(OUT / "production" / "csv-job-status.json",
           {"submitted": {k: v for k, v in submitted.items() if k != "payload"}, "trace": status_trace,
            "crashed_first_pass": crashed, "resumed": bool(resumed),
            "final": {k: v for k, v in status.items() if k not in ("payload", "result")}})

# ---------------------------------------------------------------- 8. collect QA results
standard_out, standard_err = standard_proc.communicate()
log("render --data (standard, with checks):", "ok" if standard_proc.returncode == 0 else standard_err[-500:])
try:
    render_report = json.loads(standard_out)
except ValueError:
    render_report = {"raw": standard_out[-2000:]}
write_json(OUT / "set" / "render-data-report.json", render_report)

csv_manifest = json.loads((OUT / "production" / "csv-set" / "production.json").read_text())
qa = []
for result in csv_manifest["results"]:
    index = int(result["id"]) - 1
    problems = []
    for suite, report in (result.get("checks") or {}).items():
        for rule in report["results"]:
            if rule["status"] != "passed":
                detail = {k: rule[k] for k in ("actual_size", "fits", "actual", "expected", "message") if k in rule}
                problems.append(f"{suite}/{rule['id']}: {rule['status']} {json.dumps(detail, ensure_ascii=False)}")
    if result.get("error"):
        problems.append(f"error: {result['error'].get('error')}: {result['error'].get('message')}")
    qa.append({"row": index + 1, "name": rows[index]["name"], "status": result["status"],
               "repairs": result.get("repairs", []), "problems": problems,
               "placeholder_lint": lint.get(index + 1, []), "output": result.get("output")})
render_rows = render_report if isinstance(render_report, list) else render_report.get("results", [])
for item in render_rows if isinstance(render_rows, list) else []:
    if isinstance(item, dict) and item.get("check") and 0 < item.get("row", 0) <= len(qa):
        qa[item["row"] - 1]["render_data_check"] = [
            f"{x['check']}/{x['severity']}: {x['message']}" for x in item["check"]["issues"]]
write_json(OUT / "qa-report.json", qa)
for item in qa:
    log(f"row {item['row']:2d} {item['status']:12s} repairs={item['repairs']} {item['name'][:40]!r}",
        "| " + "; ".join(p[:110] for p in item["problems"]) if item["problems"] else "")

# ---------------------------------------------------------------- 9. compact the rendered set (PNG -> WebP keeps alpha)
for folder in (standard_dir, holo_dir):
    for png in sorted(folder.glob("*.png")):
        index = int(png.stem) - 1
        if folder == holo_dir and rows[index]["rarity"] not in ("Epic", "Legendary"):
            png.unlink()  # holo foil is only printed on Epic and Legendary cards
            continue
        with Image.open(png) as image:
            image.save(png.with_suffix(".webp"), quality=82, method=6)
        png.unlink()


def card_image(i):
    holo_card = rows[i]["rarity"] in ("Epic", "Legendary")
    return (holo_dir if holo_card else standard_dir) / f"{i + 1:04d}.webp"


# ---------------------------------------------------------------- 10. contact sheet (composite doc + arrange-grid)
from vixl.typefaces import install_font  # noqa: E402

STATUS_COLOR = {"completed": "#2fbf71", "reused": "#2fbf71", "needs_review": "#f2a541", "failed": "#e5484d"}
sheet = Project(4 * 300 + 5 * 40, ((len(rows) + 3) // 4) * 460 + 300, "#101015")
sheet.apply({"type": "canvas", "dpi": 150}, detail="compact")
install_font(sheet, "Cinzel", 700, role="heading")
install_font(sheet, "EB Garamond", 400, role="body")
ops = [
    {"type": "gradient", "name": "bg", "direction": "radial", "width": sheet.state["canvas"]["width"],
     "height": sheet.state["canvas"]["height"], "stops": [{"offset": 0, "color": "#2a2040"},
                                                         {"offset": 1, "color": "#08080c"}]},
    {"type": "text", "name": "title", "text": "Aetherling Spirits \u2014 Set One", "font": "heading", "size": 64,
     "color": "#fff3d6", "x": 40, "y": 40},
    {"type": "text", "name": "subtitle", "font": "body", "size": 28, "color": "#bfb3d9", "x": 44, "y": 128,
     "text": f"{len(rows)} cards rendered from cards.csv \u00b7 holo foil comp on Epic and Legendary \u00b7 "
             "dot = checked-production status"},
]
cards = []
for i in range(len(rows)):
    ops += [{"type": "add", "path": str(card_image(i)), "name": f"card-{i + 1:02d}"},
            {"type": "resize", "target": f"card-{i + 1:02d}", "width": 300, "height": 420}]
    cards.append(f"card-{i + 1:02d}")
ops.append({"type": "arrange-grid", "targets": cards, "columns": 4, "gap": 40, "x": 40, "y": 200})
sheet.apply(ops, detail="compact")
badge_ops = []
for i, name in enumerate(cards):
    x, y = sheet.layer(name)["x"], sheet.layer(name)["y"]
    badge_ops.append({"type": "shape", "name": f"dot-{i + 1:02d}", "shape": "ellipse", "width": 30, "height": 30,
                      "x": x + 300 - 24, "y": y - 8, "fill": STATUS_COLOR.get(qa[i]["status"], "#888888"),
                      "stroke": "#101015", "stroke_width": 4})
legend_y = sheet.state["canvas"]["height"] - 60
for j, (label, color) in enumerate((("passed", "#2fbf71"), ("needs review", "#f2a541"), ("failed", "#e5484d"))):
    badge_ops += [
        {"type": "shape", "name": f"legend-dot-{j}", "shape": "ellipse", "width": 24, "height": 24,
         "x": 44 + j * 260, "y": legend_y + 4, "fill": color},
        {"type": "text", "name": f"legend-{j}", "text": label, "font": "body", "size": 26, "color": "#e8e0f5",
         "x": 80 + j * 260, "y": legend_y},
    ]
sheet.apply(badge_ops, detail="compact")
(OUT / "sheets").mkdir(exist_ok=True)
sheet.export(str(OUT / "sheets" / "contact-sheet.jpg"), quality=85)
log("contact sheet: arrange-grid of", len(cards), "cards")

# ---------------------------------------------------------------- 11. print-ready letter sheet (bleed, CMYK PDF)
press = Project.sized("letter", background="#ffffff", bleed=True)
pc = press.state["canvas"]
install_font(press, "EB Garamond", 400, role="body")
gap = 24
grid_w, grid_h = 3 * CW + 2 * gap, 3 * CH + 2 * gap
x0, y0 = (pc["width"] - grid_w) // 2, (pc["height"] - grid_h) // 2
# Impose the cards that passed checked production first, then fill with the rest.
pick = [q["row"] - 1 for q in qa if q["status"] in ("completed", "reused")]
pick += [q["row"] - 1 for q in qa if q["row"] - 1 not in pick]
ops = [{"type": "solid", "name": "paper", "color": "#ffffff"}]
for k, i in enumerate(pick[:9]):
    cx, cy = x0 + (k % 3) * (CW + gap), y0 + (k // 3) * (CH + gap)
    ops += [{"type": "add", "path": str(card_image(i)), "name": f"print-{k + 1}", "x": cx, "y": cy},
            {"type": "shape", "name": f"cut-{k + 1}", "shape": "rounded-rectangle", "radius": 40, "width": CW,
             "height": CH, "x": cx, "y": cy, "fill": "transparent", "stroke": "cmyk(0%, 100%, 0%, 0%)",
             "stroke_width": 2}]
# Slug line rotated into the left margin (6 pt = 25 px at 300 dpi).
ops += [
    {"type": "text", "name": "slug", "font": "body", "size": 26, "color": "#444444", "x": 0, "y": 0,
     "text": "Aetherling Spirits \u00b7 print sheet 1 \u00b7 3\u00d73 at 2.5\u00d73.5 in \u00b7 "
             "magenta = die line \u00b7 US Letter + 0.125 in bleed"},
    {"type": "rotate", "target": "slug", "value": -90},
    {"type": "constrain", "target": "slug", "constraints": {"center-x": f"canvas.left+{(76 + x0) // 2}",
                                                            "center-y": "canvas.center-y"}},
]
press.apply(ops, detail="compact")
press.save(OUT / "sheets" / "print-sheet.vixl")
press_check = press.check(checks=["print", "bounds", "safe_area"])
write_json(OUT / "sheets" / "print-check.json", press_check)
press.export(str(OUT / "sheets" / "print-sheet-cmyk.pdf"), format="PDF", color_space="cmyk", ink_limit=300,
             quality=60)
press.export(str(OUT / "sheets" / "print-sheet-proof.jpg"), format="JPEG", color_space="rgb", proof=True,
             quality=80, scale=0.4)
log("print sheet:", pc["width"], "x", pc["height"], "px; imposed rows", [i + 1 for i in pick[:9]],
    "; print check errors:", press_check["errors"], "warnings:", press_check["warnings"])

# ---------------------------------------------------------------- 12. tidy: drop caches and job snapshots
for junk in (OUT / "production" / "matrix" / ".cache", OUT / "production" / "csv-set" / ".cache",
             OUT / ".vixl-cache"):
    shutil.rmtree(junk, ignore_errors=True)
for snapshot in (OUT / ".vixl-jobs").glob("**/*.vixl"):
    snapshot.unlink()
(OUT / "template" / "recipe-source.vixl").unlink()
(OUT / "build-log.txt").write_text("\n".join(LOG) + "\n")
total = sum(p.stat().st_size for p in OUT.rglob("*") if p.is_file())
log(f"done: {total / 1e6:.1f} MB in output/")
