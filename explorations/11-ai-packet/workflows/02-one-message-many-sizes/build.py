"""One message, many sizes: the packet brand + one announcement adapted to six formats, two ways.

Run from the repository root:

    python explorations/11-ai-packet/workflows/02-one-message-many-sizes/build.py

A. `vixl compose` builds the master (instagram-portrait) from brand.json + a layout + the copy.
B. "adapt": copy the master and run `vixl adapt-layout --size NAME` on each copy (the CLI equivalent of
   MCP `vixl_adapt_layout`): one design, rescaled and re-anchored.
C. "recompose": run the same compose request (same seed, layout, copy) at each size, so the layout is
   built natively for that canvas.
Every output gets `vixl check` (design findings) and the same small suite; a sheet compares A and B/C.
"""

import json
import shutil
import subprocess
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
BRAND = HERE.parent / "brand" / "brand.json"
OUT = HERE / "output"
SIZES = ["instagram-square", "story", "linkedin-post", "x-header", "slide", "letter"]
COPY = {
    "title": "Understand the AI you use.",
    "subtitle": "A free classroom packet: 12 key terms, hands-on activities and an honest look at "
                "what AI can and can't do.",
    "label": "AI Field Guide",
    "cta": "Get the packet",
}
LAYOUT = {"name": "modern-bulletin", "seed": 5, "direction": {"look": "none"}, **COPY}
# Recompose tries these in order per size and keeps the first that has no `fix` finding and passes the suite.
# The last entry shrinks the base size: on 9:16 every safe layout sets a 493 px column whose fitted headline
# is no bigger than the subtitle (see NOTES.md), and a smaller body restores the hierarchy.
FALLBACKS = [("modern-bulletin", {}), ("offset-column", {}), ("quiet-editorial", {}),
             ("modern-bulletin", {"base_size": 28})]
SUITE = {"version": 1, "rules": [
    {"id": "title-dominates", "kind": "hierarchy", "targets": ["headline", "subtitle"], "ratio": 1.4},
    {"id": "title-contrast", "kind": "contrast", "target": "headline", "minimum": 4.5},
    {"id": "subtitle-contrast", "kind": "contrast", "target": "subtitle", "minimum": 4.5},
    {"id": "title-inside", "kind": "relation", "target": "headline", "to": "canvas", "position": "inside", "minimum": 24},
    {"id": "cta-inside", "kind": "relation", "target": "cta", "to": "canvas", "position": "inside", "minimum": 24},
    {"id": "title-above-subtitle", "kind": "relation", "target": "headline", "to": "subtitle", "position": "above"},
    {"id": "no-overlap", "kind": "design", "options": {"checks": ["overlap", "contrast", "bounds"]}},
]}
TIMINGS = {}


def vixl(*args, check=True, label=None):
    cmd = ["vixl", *map(str, args)]
    print("$", " ".join(cmd), flush=True)
    t = time.perf_counter()
    res = subprocess.run(cmd, cwd=OUT, capture_output=True, text=True)
    TIMINGS.setdefault(label or args[0], []).append(round(time.perf_counter() - t, 2))
    if check and res.returncode != 0:
        print(res.stdout[-2000:], res.stderr[-2000:])
        raise SystemExit(f"failed: {' '.join(cmd)}")
    try:
        return json.loads(res.stdout)
    except json.JSONDecodeError:
        return {"stdout": res.stdout[-2000:], "stderr": res.stderr[-2000:], "code": res.returncode}


def qa(doc):
    """Design check + suite; returns a short summary."""
    check = vixl("-p", doc, "check", "--json", check=False, label="check")
    (OUT / "suite.json").write_text(json.dumps({"suite": SUITE}))
    suite = vixl("-p", doc, "workflow", "check", "--request", "suite.json", check=False, label="suite")
    fixes = [i["message"] for i in check.get("issues", []) if i.get("action") == "fix"]
    failed = [r["id"] for r in suite.get("results", []) if r.get("status") != "passed"]
    return {"check_passed": check.get("passed"), "fix": fixes, "suite_status": suite.get("status"),
            "suite_not_passed": failed}


def compose(path, size, preview, layout_name="modern-bulletin", extra=None):
    req = {"path": path, "size": size, "seed": 5, "layout": {**LAYOUT, "name": layout_name, **(extra or {})},
           "check": True,
           "preview": True}
    (OUT / "req.json").write_text(json.dumps(req))
    return vixl("compose", "--request", "req.json", "--preview", preview, label="compose")


def sheet(report):
    """Adapt vs recompose, one row per size, built as a Vixl document of frames and captions."""
    cell_w, cell_h, gap, m, head, cap = 520, 380, 40, 70, 210, 96
    W = 2 * m + 2 * cell_w + gap + 300
    H = head + len(SIZES) * (cell_h + cap) + 40
    vixl("new", f"{W}x{H}", "-o", "sheet.vixl", "--seed", "1", "--json", label="new")
    palette = json.loads(BRAND.read_text())["palette"]
    ops = [{"type": "swatch", "name": k, "color": v} for k, v in palette.items()]
    ops += [{"type": "text", "name": "sheet-title", "text": "One message, six sizes", "font": "heading", "size": 60,
             "color": "@ink", "x": m, "y": 60},
            {"type": "text", "name": "col-a", "text": "A · adapt-layout (master rescaled)", "font": "heading",
             "size": 30, "color": "@accent-text", "x": m + 300, "y": 150},
            {"type": "text", "name": "col-b", "text": "B · recompose (layout rebuilt per size)", "font": "heading",
             "size": 30, "color": "@accent-text", "x": m + 300 + cell_w + gap, "y": 150}]
    for i, size in enumerate(SIZES):
        y = head + i * (cell_h + cap)
        ops.append({"type": "text", "name": f"size-{i}", "text": size, "font": "heading", "size": 30,
                    "color": "@ink", "x": m, "y": y + 10})
        for j, mode in enumerate(("adapt", "recompose")):
            x = m + 300 + j * (cell_w + gap)
            r = report[mode][size]
            verdict = (f"{r['layout']}: " if mode == "recompose" else "") + ("check ok" if not r["fix"] else f"{len(r['fix'])} fix finding(s)") + \
                (", suite passed" if r["suite_status"] == "passed" else f", suite {r['suite_status']}")
            ops += [{"type": "solid", "name": f"well-{i}-{j}", "x": x, "y": y, "width": cell_w, "height": cell_h,
                     "color": "@surface"},
                    {"type": "frame", "name": f"img-{i}-{j}", "path": f"png/{mode}-{size}.png", "x": x + 10,
                     "y": y + 10, "width": cell_w - 20, "height": cell_h - 20, "fit": "fit",
                     "downsample": "placed@2x"},
                    {"type": "text", "name": f"verdict-{i}-{j}", "text": verdict, "font": "body", "size": 26,
                     "color": "@ink" if not r["fix"] and r["suite_status"] == "passed" else "@accent-text",
                     "x": x, "y": y + cell_h + 14}]
    (OUT / "sheet.json").write_text(json.dumps(ops, indent=1))
    vixl("-p", "sheet.vixl", "apply", "sheet.json", label="apply")
    vixl("-p", "sheet.vixl", "export", "comparison-sheet.jpg", "--quality", "85", label="export")
    (OUT / "sheet.vixl").unlink()


def main():
    if OUT.exists():
        shutil.rmtree(OUT)
    for d in ("adapt", "recompose", "png"):
        (OUT / d).mkdir(parents=True)
    shutil.copy(BRAND, OUT / "brand.json")
    for d in ("adapt", "recompose"):
        shutil.copy(BRAND, OUT / d / "brand.json")

    master = compose("master.vixl", "instagram-portrait", "png/master.png")
    report = {"master": {"compose_check": master["check"]["passed"], **qa("master.vixl")}, "adapt": {}, "recompose": {}}
    vixl("-p", "master.vixl", "export", "png/master.png", "--overwrite", label="export")

    for size in SIZES:
        a = f"adapt/{size}.vixl"
        shutil.copy(OUT / "master.vixl", OUT / a)
        res = vixl("-p", a, "adapt-layout", "--size", size, label="adapt-layout")
        vixl("-p", a, "export", f"png/adapt-{size}.png", label="export")
        report["adapt"][size] = {"warnings": res.get("warnings"), **qa(a)}

        attempts = []
        for name, extra in FALLBACKS:
            r = f"recompose/{size}.vixl"
            (OUT / r).unlink(missing_ok=True)
            compose(r, size, f"png/recompose-{size}-preview.png", name, extra)
            (OUT / f"png/recompose-{size}-preview.png").unlink(missing_ok=True)
            result = {"layout": name + "".join(f" +{k} {v}" for k, v in (extra or {}).items()), **qa(r)}
            attempts.append(result)
            if not result["fix"] and result["suite_status"] == "passed":
                break
        vixl("-p", r, "export", f"png/recompose-{size}.png", label="export")
        report["recompose"][size] = {**result, "attempts": attempts}

    (OUT / "report.json").write_text(json.dumps(report, indent=1))
    (OUT / "timings.json").write_text(json.dumps(TIMINGS, indent=1))
    sheet(report)
    shutil.rmtree(OUT / "png")  # the sheet and the .vixl copies are the record; re-export any size with vixl export
    for mode in ("adapt", "recompose"):
        for size, r in report[mode].items():
            print(f"{mode:9} {size:17} check={r['check_passed']} fix={len(r['fix'])} suite={r['suite_status']} "
                  f"{r['suite_not_passed']}")


if __name__ == "__main__":
    main()
