"""Variety study: the same AI-workshop brief rolled at variety low/medium/high under house style 1 (0.22) and 2 (0.23).

Run from the repository root:

    python explorations/11-ai-packet/workflows/05-variety-study/build.py

For each of 3 variety levels x 2 house-style versions x 4 seeds (the same seeds in every cell, so the
comparison is paired) it creates an instagram-portrait document and runs

    vixl -p D roll --apply --for social --seed S --variety V --house-style H --set title=… …

then `vixl check` and an export. No brand.json here on purpose: a brand would override palette and fonts.
Writes study.json (every choice + check result), summary.json (per cell) and a comparison sheet.
"""

import json
import shutil
import subprocess
import time
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "output"
SEEDS = [11, 23, 37, 41]
LEVELS = ["low", "medium", "high"]
HOUSE = [1, 2]
SLOTS = {
    "title": "Ask an AI anything. Then check it.",
    "subtitle": "A hands-on workshop on prompts, mistakes and good judgement.",
    "label": "AI Field Guide · Workshop",
    "cta": "Thursday 3 pm · Library",
}


def vixl(*args, cwd=None):
    cmd = ["vixl", *map(str, args)]
    t = time.perf_counter()
    res = subprocess.run(cmd, cwd=cwd or OUT, capture_output=True, text=True)
    dt = round(time.perf_counter() - t, 2)
    try:
        return json.loads(res.stdout), dt, res.returncode
    except json.JSONDecodeError:
        return {"error": res.stderr[-800:]}, dt, res.returncode


def main():
    if OUT.exists():
        shutil.rmtree(OUT)
    (OUT / "png").mkdir(parents=True)
    (OUT / "docs").mkdir()
    rows = []
    for house in HOUSE:
        for level in LEVELS:
            for seed in SEEDS:
                key = f"h{house}-{level}-s{seed}"
                doc = f"docs/{key}.vixl"
                # Plain canvas, so the roll alone decides the direction (vixl new would roll house style 2).
                _, t_new, _ = vixl("new", "instagram-portrait", "-o", doc, "--background", "transparent", "--no-fonts")
                sets = [x for k, v in SLOTS.items() for x in ("--set", f"{k}={v}")]
                roll, t_roll, code = vixl("-p", doc, "roll", "--apply", "--for", "social", "--seed", seed,
                                          "--variety", level, "--house-style", house, *sets)
                chk, t_chk, _ = vixl("-p", doc, "check", "--json")
                _, t_exp, _ = vixl("-p", doc, "export", f"png/{key}.jpg", "--scale", "0.5", "--quality", "82")
                d = roll.get("direction", {})
                fixes = [i["message"] for i in chk.get("issues", []) if i.get("action") == "fix"]
                row = {"key": key, "house": house, "variety": level, "seed": seed, "roll_exit": code,
                       "tier": d.get("tier", "safe (v1 pools)"), **{k: d.get(k) for k in (
                           "layout", "pairing", "palette", "mode", "style", "look", "look_amount",
                           "background_treatment", "corner", "headline", "type_scale")},
                       "fonts_origin": (roll.get("fonts") or {}).get("origin"),
                       "check_errors": chk.get("errors"), "fix_findings": fixes,
                       "timings": {"new": t_new, "roll_apply": t_roll, "check": t_chk, "export": t_exp}}
                if code:
                    row["error"] = roll.get("error") or roll
                rows.append(row)
                print(f"{key:18} {row['tier']:16} {str(row['layout']):22} {str(row['palette']):18} "
                      f"{str(row['mode']):5} look={row['look']} fix={len(fixes)} roll={t_roll}s", flush=True)
    (OUT / "study.json").write_text(json.dumps(rows, indent=1))

    summary = {}
    for house in HOUSE:
        for level in LEVELS:
            cell = [r for r in rows if r["house"] == house and r["variety"] == level]
            summary[f"h{house}-{level}"] = {
                "distinct_layouts": len({r["layout"] for r in cell}),
                "distinct_palettes": len({r["palette"] for r in cell}),
                "distinct_pairings": len({r["pairing"] for r in cell}),
                "modes": dict(Counter(r["mode"] for r in cell)),
                "tiers": dict(Counter(r["tier"] for r in cell)),
                "looks": dict(Counter(str(r["look"]) for r in cell)),
                "outputs_with_fix_findings": sum(bool(r["fix_findings"]) for r in cell),
                "mean_roll_apply_s": round(sum(r["timings"]["roll_apply"] for r in cell) / len(cell), 2),
            }
    (OUT / "summary.json").write_text(json.dumps(summary, indent=1))
    print(json.dumps(summary, indent=1))
    sheet(rows)
    shutil.rmtree(OUT / "png")  # 24 renders are all on the sheet; study.json has every choice
    shutil.rmtree(OUT / "docs")  # 24 documents with embedded fonts; study.json + the PNGs are the record


def sheet(rows):
    """Rows: house style x variety; columns: seeds. Built with Vixl frames on a neutral canvas."""
    tw, th, gap, m, head, rowlab, cap = 270, 338, 24, 60, 190, 230, 64
    W = 2 * m + rowlab + len(SEEDS) * tw + (len(SEEDS) - 1) * gap
    H = head + len(HOUSE) * len(LEVELS) * (th + cap + 26) + 40
    vixl("new", f"{W}x{H}", "-o", "sheet.vixl", "--background", "#f4f4f2", "--no-fonts")
    vixl("-p", "sheet.vixl", "font", "pair", "inter-single-ui")
    ops = [{"type": "text", "name": "t", "text": "Variety study: one brief, 24 rolls", "font": "heading", "size": 54,
            "color": "#111111", "x": m, "y": 50},
           {"type": "text", "name": "t2", "text": "Rows: house style 1 (0.22) and 2 (0.23) at variety low / medium / high. "
            "Columns: seeds " + ", ".join(map(str, SEEDS)) + " (same seeds in every row).", "font": "body",
            "size": 24, "color": "#333333", "x": m, "y": 124}]
    i = 0
    for house in HOUSE:
        for level in LEVELS:
            y = head + i * (th + cap + 26)
            ops.append({"type": "text", "name": f"row-{i}", "text": f"house {house}\n{level}", "font": "heading",
                        "size": 32, "color": "#111111", "x": m, "y": y + 10})
            for j, seed in enumerate(SEEDS):
                r = next(r for r in rows if r["house"] == house and r["variety"] == level and r["seed"] == seed)
                x = m + rowlab + j * (tw + gap)
                ops += [{"type": "frame", "name": f"img-{i}-{j}", "path": f"png/{r['key']}.jpg", "x": x, "y": y,
                         "width": tw, "height": th, "fit": "fit"},
                        {"type": "text", "name": f"cap-{i}-{j}",
                         "text": f"{r['layout']} · {r['palette']}\n{r['tier']} · {r['mode']} · look {r['look']}"
                                 + (f" · {len(r['fix_findings'])} fix" if r["fix_findings"] else ""),
                         "font": "body", "size": 17, "color": "#b00020" if r["fix_findings"] else "#333333",
                         "x": x, "y": y + th + 8},
                        {"type": "text-layout", "target": f"cap-{i}-{j}", "width": tw, "height": cap - 8, "fit": True}]
            i += 1
    (OUT / "sheet.json").write_text(json.dumps(ops))
    vixl("-p", "sheet.vixl", "apply", "sheet.json")
    vixl("-p", "sheet.vixl", "export", "variety-sheet.jpg", "--quality", "84")
    (OUT / "sheet.vixl").unlink()


if __name__ == "__main__":
    main()
