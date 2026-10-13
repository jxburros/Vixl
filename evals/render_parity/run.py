"""Run the parity cases and write the report: ``python -m evals.render_parity [--out DIR] [-k NAME]``."""

import argparse
import fnmatch
import json
import platform
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from . import cases as case_module
from .browser import Chromium, page


def side_by_side(case, vixl, chrome, reference=None):
    """vixl | chromium | |difference| x4 (| reference, when the case has one), labelled, at 2x when small."""
    images = [("Vixl", vixl.convert("RGB")), ("Chromium", chrome.convert("RGB"))]
    a, b = np.asarray(images[0][1], int), np.asarray(images[1][1], int)
    images.append(("|diff| x4", Image.fromarray(np.uint8(np.clip(np.abs(a - b).max(axis=2) * 4, 0, 255))).convert("RGB")))
    if reference is not None:
        images.append(("Reference", Image.fromarray(np.uint8(np.clip(np.asarray(reference), 0, 1) * 255 + 0.5))))
    scale = 2 if case.width <= 300 else 1
    w, h = case.width * scale, case.height * scale
    sheet = Image.new("RGB", (len(images) * (w + 8) + 8, h + 28), "#808080")
    draw = ImageDraw.Draw(sheet)
    for i, (label, image) in enumerate(images):
        x = 8 + i * (w + 8)
        draw.text((x, 6), label, fill="#ffffff")
        sheet.paste(image.resize((w, h), Image.Resampling.NEAREST), (x, 22))
    return sheet


def run(selected, out, hinting):
    out.mkdir(parents=True, exist_ok=True)
    results = []
    with Chromium(hinting=hinting) as browser:
        for case in selected:
            started = time.perf_counter()
            project = case.build()
            vixl = project.render().convert("RGB")
            html = page(case.html(project), case.width, case.height, case.background, case.css, case_module.FONTS)
            chrome, measured = browser.render(html, case.width, case.height)
            ctx = case_module.Context(case, project, vixl, chrome, measured)
            found = case.analyze(ctx)
            reference = case.reference(project) if case.reference else None
            vixl.save(out / f"{case.name}.vixl.png")
            chrome.save(out / f"{case.name}.chromium.png")
            (out / f"{case.name}.html").write_text(html)
            side_by_side(case, vixl, chrome, reference).save(out / f"{case.name}.compare.png")
            results.append({"name": case.name, "category": case.category, "title": case.title, "note": case.note,
                            "tags": list(case.tags), "metrics": found,
                            "seconds": round(time.perf_counter() - started, 2)})
            print(f"{case.name:32} {summary_line(found)}", flush=True)
        version = browser.version
    import vixl as package

    report = {"chromium": version, "hinting": hinting, "vixl": package.__version__,
              "python": platform.python_version(), "platform": platform.platform(), "cases": results}
    (out / "report.json").write_text(json.dumps(report, indent=1))
    (out / "report.md").write_text(markdown(report))
    return report


def summary_line(found):
    parts = []
    d = found.get("diff")
    if d:
        parts.append(f"mean|d| {d['mean']:.2f} psnr {d['psnr']}")
    for key in ("vs_ideal", "edge_vs_ideal"):
        if key in found:
            parts.append(f"{key} rms vixl {found[key]['vixl']['rms']} chrome {found[key]['chrome']['rms']}")
    if "layout_dx" in found:
        parts.append(f"layout dx max {found['layout_dx']['max']}")
    if "glyph_shift" in found:
        parts.append(f"glyph shift spread {found['glyph_shift']['spread']}")
    if "ink_weight_ratio" in found:
        parts.append(f"ink ratio {found['ink_weight_ratio']}")
    return "; ".join(parts)


def markdown(report):
    lines = [
        "# Render parity report", "",
        f"Chromium {report['chromium']} (font hinting: {report['hinting']}), Vixl {report['vixl']}, "
        f"Python {report['python']} on {report['platform']}.", "",
        "Each case has `NAME.compare.png` (Vixl | Chromium | |difference| x4 | reference where one exists), the two "
        "renders and the HTML. Differences are in 0-255 levels; `vs_ideal` compares coverage with an exact "
        "supersampled reference.", "",
        "| case | category | mean abs diff | PSNR | key measurements |", "| --- | --- | --- | --- | --- |",
    ]
    for result in report["cases"]:
        m = result["metrics"]
        d = m.get("diff", {})
        lines.append(f"| `{result['name']}` | {result['category']} | {d.get('mean', '')} | {d.get('psnr', '')} | "
                     f"{key_points(m)} |")
    lines += ["", "## Details", ""]
    for result in report["cases"]:
        lines += [f"### {result['name']}: {result['title']}", ""]
        if result["note"]:
            lines += [result["note"], ""]
        lines += [f"![{result['name']}]({result['name']}.compare.png)", "", "```json",
                  json.dumps(result["metrics"], indent=1)[:4000], "```", ""]
    return "\n".join(lines)


def key_points(m):
    points = []
    if "layout_dx" in m:
        points.append(f"glyph layout max dx {m['layout_dx']['max']} px")
    if "glyph_shift" in m:
        points.append(f"raster glyph shift spread {m['glyph_shift']['spread']} px")
    if "ink_weight_ratio" in m:
        points.append(f"ink weight Vixl/Chromium {m['ink_weight_ratio']}")
    if "sharpness" in m and isinstance(m["sharpness"], dict) and "vixl" in m["sharpness"]:
        points.append(f"sharpness {m['sharpness']['vixl']} vs {m['sharpness']['chrome']}")
    if "lines" in m:
        points.append(f"lines {m['lines']['vixl']} vs {m['lines']['chrome']}, same breaks {m['lines']['same_breaks']}")
    for key in ("vs_ideal", "edge_vs_ideal"):
        if key in m and "vixl" in m[key]:
            points.append(f"{key} rms {m[key]['vixl']['rms']} vs {m[key]['chrome']['rms']}")
    if "max_error" in m:
        points.append(f"blend max error {m['max_error']['vixl']} vs {m['max_error']['chrome']}")
    for label in ("vixl", "chrome"):
        v = m.get(label)
        if isinstance(v, dict):
            for key in ("sigma_estimate", "fitted_sigma", "banding", "rms_vs_area_average",
                        "rms_vs_ideal", "stripe_alias_std"):
                if key in v:
                    points.append(f"{label} {key} {v[key]}")
            if "vs_ideal" in v:
                points.append(f"{label} rms vs ideal {v['vs_ideal']['rms']}")
    return "; ".join(points)


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m evals.render_parity", description=__doc__)
    parser.add_argument("--out", type=Path, default=Path("render-parity-results"),
                        help="output directory (default: render-parity-results, git-ignored)")
    parser.add_argument("-k", "--case", action="append", default=[],
                        help="run cases whose name matches this glob (repeatable)")
    parser.add_argument("--hinting", default="none", choices=["none", "slight", "medium", "full"],
                        help="Chromium --font-render-hinting (default none: unhinted outlines, like Vixl)")
    parser.add_argument("--list", action="store_true", help="list the cases and exit")
    args = parser.parse_args(argv)
    selected = [c for c in case_module.CASES
                if not args.case or any(fnmatch.fnmatch(c.name, f"*{p}*") for p in args.case)]
    if args.list:
        for c in selected:
            print(f"{c.name:32} {c.category:12} {c.title}")
        return 0
    if not selected:
        print("no case matches", file=sys.stderr)
        return 2
    run(selected, args.out, args.hinting)
    print(f"report: {args.out / 'report.md'}")
    return 0
