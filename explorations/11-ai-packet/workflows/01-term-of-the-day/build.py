"""AI term of the day: one card template, a CSV of terms, twelve cards and a contact sheet.

Run from the repository root:

    python explorations/11-ai-packet/workflows/01-term-of-the-day/build.py

Steps (all through the `vixl` CLI, so each one can be copied into a shell):
  1. `vixl new instagram-portrait` beside the packet brand.json (palette + fonts come from the brand)
  2. `vixl apply template.json`: variables + fixed-size text boxes + a small neural-network motif
  3. `vixl check` and a check suite on the template, filled with the *longest* row of the CSV
  4. `vixl render --data terms.csv`: one PNG per row, with a design check per row
  5. `vixl workflow run`: the same rows as a checked production run, which also writes a contact sheet
"""

import csv
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
BRAND = HERE.parent / "brand" / "brand.json"
OUT = HERE / "output"
TIMINGS = {}


def vixl(*args, cwd=OUT, check=True):
    """Run one vixl command, print it, time it and return parsed JSON (or text)."""
    cmd = ["vixl", *map(str, args)]
    print("$", " ".join(cmd), flush=True)
    t = time.perf_counter()
    res = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    TIMINGS.setdefault(args[2] if args[0] == "-p" else args[0], []).append(round(time.perf_counter() - t, 2))
    if check and res.returncode != 0:
        print(res.stdout[-3000:], res.stderr[-3000:])
        raise SystemExit(f"command failed: {' '.join(cmd)}")
    try:
        return json.loads(res.stdout)
    except json.JSONDecodeError:
        return res.stdout


def network_motif(x0, y0, w, h):
    """A tiny three-layer neural network: dots joined by lines, one highlighted path."""
    cols = [3, 4, 2]
    pts = []
    for ci, n in enumerate(cols):
        x = x0 + ci * w / (len(cols) - 1)
        pts.append([(x, y0 + (ri + 0.5) * h / n) for ri in range(n)])
    ops, names = [], []
    hot = {(0, 1), (1, 2), (2, 0)}  # (column, row) nodes on the highlighted path
    k = 0
    for ci in range(len(cols) - 1):
        for ai, a in enumerate(pts[ci]):
            for bi, b in enumerate(pts[ci + 1]):
                lit = (ci, ai) in hot and (ci + 1, bi) in hot
                name = f"motif-edge-{k}"
                k += 1
                # pen, not shape line + from/to: a from/to line gets a canvas-sized box (see NOTES.md)
                ops.append({"type": "pen", "name": name,
                            "points": [[round(a[0]), round(a[1])], [round(b[0]), round(b[1])]],
                            "stroke": "@accent" if lit else "@muted",
                            "stroke_width": 5 if lit else 2, "line_cap": "round"})
                names.append(name)
    r = 14
    for ci, col in enumerate(pts):
        for ri, (x, y) in enumerate(col):
            name = f"motif-node-{ci}-{ri}"
            ops.append({"type": "shape", "shape": "ellipse", "name": name,
                        "x": round(x - r), "y": round(y - r), "width": 2 * r, "height": 2 * r,
                        "fill": "@accent" if (ci, ri) in hot else "@ink"})
            names.append(name)
    ops.append({"type": "group", "name": "motif", "targets": names})
    ops.append({"type": "layer-intent", "target": "motif", "role": "decoration"})
    return ops


def template_ops(defaults):
    W, M = 1080, 80
    ops = [{"type": "variable", "name": k, "value": v} for k, v in defaults.items()]
    # A new document stores the brand palette in design_defaults but defines no @role swatches
    # until a layout or palette-apply runs, so define them from brand.json.
    palette = json.loads(BRAND.read_text())["palette"]
    ops += [{"type": "swatch", "name": role, "color": color} for role, color in palette.items()]
    ops += [
        {"type": "solid", "name": "top-bar", "x": 0, "y": 0, "width": W, "height": 18, "color": "@accent"},
        {"type": "layer-intent", "target": "top-bar", "role": "decoration"},
        {"type": "text", "name": "label", "text": "AI TERM OF THE DAY", "font": "heading", "size": 34,
         "color": "@accent-text", "x": M, "y": 88},  # integer y: see the fractional-y contrast bug in NOTES.md
        {"type": "text", "name": "number", "text": "No. ${NUM} / 12", "font": "body", "size": 34,
         "color": "@muted", "align": "right", "baseline_y": 112},
        {"type": "constrain", "target": "number", "constraints": {"right": f"canvas.right-{M}"}},
        {"type": "solid", "name": "rule-top", "x": M, "y": 146, "width": W - 2 * M, "height": 3, "color": "@ink"},
        {"type": "solid", "name": "category-dot", "x": M, "y": 202, "width": 22, "height": 22, "color": "@accent"},
        {"type": "text", "name": "category", "text": "${category|upper}", "font": "heading", "size": 34,
         "color": "@accent-text", "x": M + 36, "baseline_y": 225},
        # Width-only boxes grow to their text, but only when text-layout runs; the production run
        # re-runs them per row through the "reflow" action so the definition follows the term.
        {"type": "text", "name": "term", "text": "${term}", "font": "heading", "size": 104,
         "color": "@ink", "x": M, "y": 262, "line_height": 1.05},
        {"type": "text-layout", "target": "term", "width": W - 2 * M},
        {"type": "text", "name": "definition", "text": "${definition}", "font": "body", "size": 44,
         "color": "@ink", "x": M},
        {"type": "text-layout", "target": "definition", "width": W - 2 * M},
        {"type": "constrain", "target": "definition", "constraints": {"top": "term.bottom+56"}},
        {"type": "solid", "name": "try-panel", "x": M, "y": 880, "width": W - 2 * M, "height": 290,
         "color": "@surface"},
        {"type": "text", "name": "try-label", "text": "TRY IT", "font": "heading", "size": 34,
         "color": "@ink", "x": M + 40, "y": 920},
        {"type": "text", "name": "tryit", "text": "${tryit}", "font": "body", "size": 36,
         "color": "@ink", "x": M + 40, "y": 975},
        {"type": "text-layout", "target": "tryit", "width": 600, "height": 170},
        {"type": "text", "name": "footer", "text": "AI Field Guide", "font": "heading", "size": 34,
         "color": "@ink", "x": M, "baseline_y": 1240},
        {"type": "text", "name": "footer-motto", "text": "learn it · try it · question it", "font": "body",
         "size": 34, "color": "@muted", "align": "right", "baseline_y": 1240},
        {"type": "constrain", "target": "footer-motto", "constraints": {"right": f"canvas.right-{M}"}},
        {"type": "action-define", "name": "reflow", "action": {"operations": [
            {"type": "text-layout", "target": "term", "width": W - 2 * M},
            {"type": "text-layout", "target": "definition", "width": W - 2 * M}]}},
    ]
    ops += network_motif(790, 935, 170, 190)
    return ops


SUITE = {
    "version": 1,
    "rules": [
        {"id": "term-dominates", "kind": "hierarchy", "targets": ["term", "definition", "tryit"], "ratio": 1.2},
        {"id": "term-contrast", "kind": "contrast", "target": "term", "minimum": 4.5},
        {"id": "definition-contrast", "kind": "contrast", "target": "definition", "minimum": 4.5},
        {"id": "tryit-contrast", "kind": "contrast", "target": "tryit", "minimum": 4.5},
        {"id": "label-contrast", "kind": "contrast", "target": "label", "minimum": 4.5},
        {"id": "definition-readable", "kind": "text-fit", "target": "definition", "minimum": 36},
        {"id": "tryit-readable", "kind": "text-fit", "target": "tryit", "minimum": 28},
        {"id": "term-above-definition", "kind": "relation", "target": "term", "to": "definition",
         "position": "above", "minimum": 8},
        {"id": "definition-clear-of-panel", "kind": "relation", "target": "definition", "to": "try-panel",
         "position": "above", "minimum": 24},
        {"id": "motif-in-panel", "kind": "relation", "target": "motif", "to": "try-panel", "position": "inside",
         "minimum": 16},
        {"id": "tryit-clear-of-motif", "kind": "relation", "target": "tryit", "to": "motif", "position": "apart",
         "minimum": 24},
        {"id": "footer-inside", "kind": "relation", "target": "footer", "to": "canvas", "position": "inside",
         "minimum": 60},
        {"id": "nothing-cut-off", "kind": "design", "options": {"checks": ["bounds", "overlap", "contrast"]}},
        {"id": "one-term", "kind": "count", "target": "term", "layer_type": "text", "minimum": 1, "maximum": 1},
    ],
}


def contact_sheet(rows, passed):
    """A reviewable sheet built with Vixl itself: the production run's own sheet is 800 px wide and
    labels cards by variant ID, so this one uses frames + captions on a brand canvas."""
    cols, cw, ch, gap, m, head = 4, 400, 500, 40, 80, 230
    W = 2 * m + cols * cw + (cols - 1) * gap
    H = head + 3 * (ch + 92) + 40
    vixl("new", f"{W}x{H}", "-o", "contact-sheet.vixl", "--seed", "1", "--json")
    palette = json.loads(BRAND.read_text())["palette"]
    ops = [{"type": "swatch", "name": k, "color": v}
           for k, v in palette.items()]
    ops += [{"type": "text", "name": "sheet-title", "text": "AI term of the day: 12 cards", "font": "heading",
             "size": 64, "color": "@ink", "x": m, "y": 70},
            {"type": "text", "name": "sheet-sub", "text": "Built from terms.csv with one Vixl template. " +
             (f"All {passed} cards passed the 'card' check suite." if passed == len(rows)
             else f"{passed} of {len(rows)} cards passed the 'card' check suite."), "font": "body", "size": 30, "color": "@muted",
             "x": m, "y": 158}]
    for i, row in enumerate(rows):
        x = m + (i % cols) * (cw + gap)
        y = head + (i // cols) * (ch + 92)
        slug = f"{row['NUM']}-{row['term'].lower().replace(' ', '-')}"
        ops += [{"type": "frame", "name": f"card-{row['NUM']}", "path": f"cards/{slug}.png", "x": x, "y": y,
                 "width": cw, "height": ch, "fit": "fill", "downsample": "placed@2x"},
                {"type": "layer-style", "target": f"card-{row['NUM']}", "name": "stroke",
                 "settings": {"size": 2, "color": "@surface"}},
                {"type": "text", "name": f"caption-{row['NUM']}", "text": f"{row['NUM']} · {row['term']}",
                 "font": "body", "size": 28, "color": "@ink", "x": x, "y": y + ch + 20}]
    (OUT / "contact-sheet.json").write_text(json.dumps(ops, indent=1))
    vixl("-p", "contact-sheet.vixl", "apply", "contact-sheet.json")
    vixl("-p", "contact-sheet.vixl", "export", "contact-sheet.jpg", "--quality", "86")
    (OUT / "contact-sheet.vixl").unlink()  # 2.6 MB of embedded card images; rebuild it from contact-sheet.json


def main():
    if OUT.exists():
        shutil.rmtree(OUT)
    (OUT / "cards").parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(BRAND, OUT / "brand.json")
    shutil.copy(HERE / "terms.csv", OUT / "terms.csv")
    rows = list(csv.DictReader(open(HERE / "terms.csv", encoding="utf-8")))
    longest = max(rows, key=lambda r: len(r["definition"]) + len(r["tryit"]) + 4 * len(r["term"]))

    vixl("new", "instagram-portrait", "--seed", "11", "-o", "card.vixl", "--json")
    ops = template_ops(longest)
    ops.append({"type": "suite-set", "name": "card", "suite": SUITE})
    (OUT / "template.json").write_text(json.dumps(ops, indent=1))
    res = vixl("-p", "card.vixl", "apply", "template.json", "--check", "--suites", "--preview", "template-preview.png")
    (OUT / "reports").mkdir(exist_ok=True)
    (OUT / "reports" / "template-apply.json").write_text(json.dumps(
        {k: v for k, v in res.items() if k != "changes"}, indent=1))

    check = vixl("-p", "card.vixl", "check", "--json", check=False)
    (OUT / "suite-request.json").write_text(json.dumps({"suite": "card"}))
    suite = vixl("-p", "card.vixl", "workflow", "check", "--request", "suite-request.json", check=False)
    (OUT / "reports" / "template-check.json").write_text(json.dumps({"check": check, "suite": suite}, indent=1))

    # 1) Quick proof: classic CSV merge, one PNG per row with a design check per row. Text boxes keep
    #    the size measured for the template's default (longest) row, so short rows leave gaps.
    t = time.perf_counter()
    merged = vixl("-p", "card.vixl", "render", "--data", "terms.csv", "--out", "quick-proof")
    TIMINGS["render --data (12 rows)"] = round(time.perf_counter() - t, 2)
    (OUT / "reports" / "render-data.json").write_text(json.dumps(merged, indent=1))

    # 2) Final cards: a checked production run. Each row runs the "reflow" action (text boxes are
    #    re-measured for that row's copy), then the "card" suite; failures are held for review.
    spec = {"output": "production", "spec": {"version": 1, "rows": rows, "quality": "final",
                                             "format": "png", "workers": 2, "actions": ["reflow"],
                                             "suites": ["card"]}}
    (OUT / "production.json").write_text(json.dumps(spec, indent=1))
    t = time.perf_counter()
    prod = vixl("-p", "card.vixl", "workflow", "run", "--request", "production.json", check=False)
    TIMINGS["workflow run (12 rows, 2 workers)"] = round(time.perf_counter() - t, 2)
    (OUT / "reports" / "production-run.json").write_text(json.dumps(prod, indent=1))
    (OUT / "cards").mkdir()
    for row, r in zip(rows, prod["results"]):
        print(row["NUM"], r["status"], r.get("checks", {}).get("card", {}).get("status"))
        if r["status"] == "completed":
            shutil.copy(OUT / "production" / r["output"],
                        OUT / "cards" / f"{row['NUM']}-{row['term'].lower().replace(' ', '-')}.png")
    # 3) Print: 4-up Letter sheets with crop marks, vector text (3.6 × 4.5 in cards, 3 pages, ~21 KB).
    merge = vixl("-p", "card.vixl", "merge", "--data", "terms.csv", "--out", "print-sheets.pdf",
                 "--size", "letter", "--cols", "2", "--rows", "2")
    (OUT / "reports" / "print-merge.json").write_text(json.dumps(merge, indent=1))
    contact_sheet(rows, sum(r["status"] == "completed" for r in prod["results"]))
    # Keep the folder small: the named copies in cards/ and the manifest are what matter. The production
    # run also leaves a render cache (.cache, ~7 MB) inside its output folder.
    shutil.copy(OUT / "production" / "production.json", OUT / "reports" / "production-manifest.json")
    shutil.rmtree(OUT / "production")
    for i, png in enumerate(sorted((OUT / "quick-proof").glob("*.png"))):
        if i not in (4, 8):  # keep one long-term and one short-term row to show the fixed-box gap
            png.unlink()
    (OUT / ".vixl-session.json").unlink(missing_ok=True)
    (OUT / "reports" / "timings.json").write_text(json.dumps(TIMINGS, indent=1))
    print(json.dumps(TIMINGS, indent=1))


if __name__ == "__main__":
    sys.exit(main())
