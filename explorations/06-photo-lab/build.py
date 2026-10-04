"""Vixl photo lab: a non-destructive photo-editing pipeline on a synthesized photograph.

Run from the repository root:

    python explorations/06-photo-lab/build.py

Everything is written to explorations/06-photo-lab/output/ (wiped first). No AI provider,
no network except Google Fonts downloads (cached in explorations/06-photo-lab/.cache/).
"""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "output"
WORK = OUT / "work"
PHOTOS = HERE / "photos"
os.environ["VIXL_RESOURCES"] = str(OUT / "resources.json")
os.environ["VIXL_FONT_CACHE"] = str(HERE / ".cache" / "fonts")
os.environ["VIXL_NO_UPDATE"] = "1"

import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402

from vixl import Project  # noqa: E402
from vixl.checks import compare  # noqa: E402
from vixl.interfaces import Session  # noqa: E402
from vixl.measure import measure  # noqa: E402
from vixl.typefaces import install_font  # noqa: E402
from vixl.workflows import dispatch  # noqa: E402

sys.path.insert(0, str(HERE))
from synth import second_photo, source_photo  # noqa: E402

W, H = 1200, 800
LOG = []
METRICS = {}


def step(project, label, ops):
    """Apply one atomic batch and keep a compact log entry."""
    ops = ops if isinstance(ops, list) else [ops]
    result = project.apply(ops, detail="compact")
    LOG.append({"step": label, "operations": [o["type"] if o["type"] != "effect" else "effect:" + o["name"] for o in ops],
                "normalized": result.get("normalized")})
    return result


def fx_ids(project, target):
    return {e["name"]: e["id"] for e in project.layer(target)["effects"]}


def stats(project, region=None):
    """Luma mean / percentiles and RGB means from vixl's measure() (histogram='full')."""
    m = measure(project, region=region, histogram="full")
    hist = m["histogram"]
    rgb = [np.array(hist[c], float) for c in ("red", "green", "blue")]
    def pct(h, q):
        c = np.cumsum(h) / h.sum()
        return int(np.searchsorted(c, q))
    mean_hist = sum(rgb) / 3
    return {
        "mean_rgb": [round(v, 1) for v in m["average"]["rgb"]],
        "luma_mean": round(0.2126 * m["average"]["rgb"][0] + 0.7152 * m["average"]["rgb"][1] + 0.0722 * m["average"]["rgb"][2], 1),
        "p2": pct(mean_hist, 0.02), "p50": pct(mean_hist, 0.5), "p98": pct(mean_hist, 0.98),
        "clipped_black_pct": round(100 * sum(h[0] for h in rgb) / (3 * mean_hist.sum()), 2),
        "clipped_white_pct": round(100 * sum(h[255] for h in rgb) / (3 * mean_hist.sum()), 2),
        "rg_balance": round(m["average"]["rgb"][0] - m["average"]["rgb"][2], 1),
        "_hist": mean_hist.tolist(),
    }


# --------------------------------------------------------------------------- selections
# Canvas-coordinate selection recipes, measured on the straightened frame (horizon y≈487).
DARK = "#0a080c"  # silhouette colour in the raw frame
SELECTIONS = {
    "sky: rect minus colour, feather 14": [
        {"type": "select", "shape": "rect", "x": 0, "y": 0, "width": W, "height": 490},
        {"type": "select", "shape": "color", "color": DARK, "tolerance": 20, "mode": "subtract"},
        {"type": "select", "shape": "rect", "x": 0, "y": 0, "width": W, "height": 490, "mode": "intersect", "feather": 14},
    ],
    "sun: ellipse, feather 60": [
        {"type": "select", "shape": "ellipse", "x": 210, "y": 255, "width": 320, "height": 320, "feather": 60},
    ],
    "sea: lasso minus ellipse": [
        {"type": "select", "shape": "lasso", "points": [[0, 490], [W, 490], [W, 800], [530, 800], [500, 700], [0, 690]], "feather": 6},
        {"type": "select", "shape": "ellipse", "x": 300, "y": 470, "width": 260, "height": 330, "mode": "subtract", "feather": 30},
    ],
    "land: wand + wand, x 2-subpath path": [
        {"type": "select", "shape": "wand", "x": 1000, "y": 450, "tolerance": 20},
        {"type": "select", "shape": "wand", "x": 150, "y": 740, "tolerance": 20, "mode": "add"},
        {"type": "select", "shape": "path", "path": "M0 630 L545 630 L545 800 L0 800 Z M760 340 L1200 340 L1200 494 L760 494 Z",
         "mode": "intersect", "feather": 2},
    ],
    "lamp: global wand x rect": [
        {"type": "select", "shape": "wand", "x": 1125, "y": 250, "tolerance": 60, "contiguous": False},
        {"type": "select", "shape": "rect", "x": 1090, "y": 230, "width": 70, "height": 40, "mode": "intersect", "feather": 3},
    ],
    "figure: path x colour": [
        {"type": "select", "shape": "path",
         "path": "M244 480 L258 476 L292 512 C296 498 324 496 328 512 C336 520 342 540 342 580 L340 652 L284 652 L282 590 C278 560 280 540 286 532 Z"},
        {"type": "select", "shape": "color", "color": DARK, "tolerance": 22, "mode": "intersect"},
    ],
}
COLORS = ["#4cc9f0", "#ffd166", "#06d6a0", "#ef476f", "#f8f9fa", "#c77dff"]


MASKS = {}


def build_masks(project):
    """Run every selection recipe once on the straightened frame and keep the mask asset IDs."""
    for key, ops in SELECTIONS.items():
        step(project, f"select {key}", ops)
        MASKS[key] = project.state["selection"]
        sel = np.asarray(project.image(MASKS[key], "L"), float)
        METRICS.setdefault("selection_coverage_pct", {})[key] = round(100 * sel.mean() / 255, 2)
    step(project, "select none", {"type": "select", "shape": "none"})


def select(project, key):
    """Re-activate a stored selection mask (select shape=asset)."""
    return step(project, f"reselect {key}", {"type": "select", "shape": "asset", "asset": MASKS[key]})


# --------------------------------------------------------------------------- fonts
def fonts(project):
    for family, weight in (("DM Serif Display", 400), ("Space Grotesk", 500), ("JetBrains Mono", 400)):
        install_font(project, family, weight)
    return {"title": "dm-serif-display-400", "label": "space-grotesk-500", "mono": "jetbrains-mono-400"}


def main():
    if OUT.exists():
        shutil.rmtree(OUT)
    WORK.mkdir(parents=True)
    PHOTOS.mkdir(exist_ok=True)
    # Saved like a camera would: high-quality JPEG (Vixl embeds the original bytes).
    src1, src2 = PHOTOS / "coast-raw.jpg", PHOTOS / "lake-raw.jpg"
    source_photo().save(src1, quality=93)
    second_photo().save(src2, quality=93)

    # ================================================================ 1. import & geometry
    p = Project(W, H, background="#0b0b10")
    step(p, "import raw frame", [{"type": "add", "path": str(src1), "name": "photo"},
                                 {"type": "resize", "target": "photo", "width": W},
                                 {"type": "align", "target": "photo", "alignment": "center"}])
    p.checkpoint("original")
    # Crop out the dark sensor border, mirror the composition, straighten the 2.2° tilt
    # (the flip mirrors the tilt, so the correction is clockwise), scale to cover the canvas.
    step(p, "crop / flip / straighten", [
        {"type": "crop", "target": "photo", "x": 40, "y": 40, "width": 1500, "height": 1000},
        {"type": "flip", "target": "photo", "direction": "horizontal"},
        {"type": "rotate", "target": "photo", "value": 2.2},
        {"type": "resize", "target": "photo", "width": 1290},
        {"type": "align", "target": "photo", "alignment": "center"},
    ])
    p.checkpoint("straightened")
    build_masks(p)

    # ================================================================ 2. global tone
    step(p, "global tone stack", [
        {"type": "select", "shape": "none"},
        {"type": "auto-tone", "target": "photo"},
        {"type": "auto-contrast", "target": "photo"},
        {"type": "levels", "target": "photo", "black": 4, "white": 240},
        {"type": "curves", "target": "photo", "points": [[0, 0], [60, 52], [128, 136], [196, 216], [255, 255]]},
        {"type": "exposure", "target": "photo", "amount": 0.12},
        {"type": "shadows", "target": "photo", "amount": 5},
        {"type": "highlights", "target": "photo", "amount": -8},
        {"type": "temperature", "target": "photo", "amount": 500},
        {"type": "tint", "target": "photo", "amount": -1},
        {"type": "saturation", "target": "photo", "amount": 12},
        {"type": "sharpen", "target": "photo", "amount": 1.4},
    ])
    # Per-channel auto-tone pushes this sunset to electric blue/magenta (see README); measure it, then disable it.
    with_auto_tone = stats(p)
    step(p, "effect-disable auto-tone (index 1)", {"type": "effect-disable", "target": "photo", "effect": 1})
    without_auto_tone = stats(p)
    METRICS["auto_tone_effect"] = {"with": {k: v for k, v in with_auto_tone.items() if k != "_hist"},
                                   "disabled": {k: v for k, v in without_auto_tone.items() if k != "_hist"}}
    ids = fx_ids(p, "photo")
    # Effect-stack management by stable fx_ ID and by 1-based index.
    step(p, "effect-set temperature 500→700", {"type": "effect-set", "target": "photo", "effect": ids["temperature"], "amount": 700})
    step(p, "effect-disable sharpen (index 11)", {"type": "effect-disable", "target": "photo", "effect": 11})
    no_sharpen = p.render()
    step(p, "effect-enable sharpen", {"type": "effect-enable", "target": "photo", "effect": ids["sharpen"]})
    sharp = p.render()
    METRICS["sharpen_toggle_mean_abs_diff"] = round(float(np.abs(np.asarray(sharp, float) - np.asarray(no_sharpen, float)).mean()), 3)
    # There is no effect-reorder operation; emulate "move auto-tone to the end" with remove + re-add,
    # measure the difference, then undo the experiment (one batch = one undo step).
    before_reorder = stats(p)
    step(p, "reorder experiment: auto-contrast to end", [
        {"type": "effect-remove", "target": "photo", "effect": ids["auto-contrast"]},
        {"type": "auto-contrast", "target": "photo"},
    ])
    after_reorder = stats(p)
    METRICS["reorder_auto_contrast_last"] = {"luma_mean_first": before_reorder["luma_mean"], "luma_mean_last": after_reorder["luma_mean"],
                                         "p2_first": before_reorder["p2"], "p2_last": after_reorder["p2"]}
    p.undo()
    LOG.append({"step": "undo reorder experiment", "operations": ["undo"]})
    step(p, "preset-save coastal-base (global stack)", {"type": "preset-save", "name": "coastal-base", "target": "photo"})
    p.checkpoint("toned")

    # ================================================================ 3. local, selection-scoped edits
    select(p, "sky: rect minus colour, feather 14")
    step(p, "sky: graduated filter", [
        {"type": "highlights", "target": "photo", "amount": -22},
        {"type": "saturation", "target": "photo", "amount": 18},
        {"type": "curves", "target": "photo", "points": [[0, 0], [90, 78], [255, 255]]},
    ])
    sky_mask = MASKS["sky: rect minus colour, feather 14"]
    select(p, "sun: ellipse, feather 60")
    step(p, "sun: warm bloom", [{"type": "exposure", "target": "photo", "amount": 0.35},
                                {"type": "temperature", "target": "photo", "amount": 260}])
    select(p, "sea: lasso minus ellipse")
    step(p, "sea: cool & deepen", [{"type": "temperature", "target": "photo", "amount": -900},
                                   {"type": "contrast", "target": "photo", "amount": 12},
                                   {"type": "exposure", "target": "photo", "amount": -0.15}])
    select(p, "land: wand + wand, x 2-subpath path")
    step(p, "land: lift blacks", [{"type": "shadows", "target": "photo", "amount": 7},
                                  {"type": "saturation", "target": "photo", "amount": -25}])
    select(p, "lamp: global wand x rect")
    step(p, "lamp: brighten", [{"type": "exposure", "target": "photo", "amount": 0.8}])

    # Subject cut-out layer from the path ∩ colour selection, given a warm rim light.
    select(p, "figure: path x colour")
    step(p, "subject cut-out + rim light", [
        {"type": "duplicate", "target": "photo", "name": "subject"},
        {"type": "mask", "target": "subject", "action": "from-selection"},
        {"type": "layer-style", "target": "subject", "name": "outer-glow", "settings": {"color": "#ffb36b", "blur": 10, "opacity": 0.75}},
    ])
    # Alpha selection of the masked cut-out → invert → intersect an ellipse → warm halo on the photo.
    step(p, "halo: alpha → invert → intersect ellipse", [
        {"type": "select", "shape": "alpha", "target": "subject"},
        {"type": "select", "shape": "invert"},
        {"type": "select", "shape": "ellipse", "x": 160, "y": 420, "width": 280, "height": 300, "mode": "intersect", "feather": 40},
        {"type": "exposure", "target": "photo", "amount": 0.3},
        {"type": "temperature", "target": "photo", "amount": 180},
        {"type": "select", "shape": "none"},
    ])

    # Golden-hour light: radial gradient, screen blend, masked to the sky selection.
    step(p, "golden-hour gradient masked to sky", [
        {"type": "gradient", "name": "golden-hour", "direction": "radial", "width": 900, "height": 700, "x": -80, "y": 70,
         "stops": [{"offset": 0, "color": "#ffb45a"}, {"offset": 0.45, "color": "#ff7a4a66"}, {"offset": 1, "color": "#ff7a4a00"}]},
        {"type": "blend", "target": "golden-hour", "value": "screen"},
        {"type": "opacity", "target": "golden-hour", "value": 0.55},
        {"type": "select", "shape": "asset", "asset": sky_mask},
        {"type": "select", "shape": "ellipse", "x": 210, "y": 255, "width": 320, "height": 320, "mode": "add", "feather": 30},
        {"type": "mask", "target": "golden-hour", "action": "from-selection"},
        {"type": "select", "shape": "none"},
        {"type": "reorder", "target": "golden-hour", "below": "subject"},
    ])
    # Mask toggles: disable → measure → enable.
    sky_region = [0, 0, W, 300]
    with_mask = stats(p, sky_region)["luma_mean"]
    step(p, "mask disable", {"type": "mask", "target": "golden-hour", "action": "disable"})
    without_mask = stats(p, [0, 600, W, 200])["luma_mean"]
    step(p, "mask enable", {"type": "mask", "target": "golden-hour", "action": "enable"})
    METRICS["golden_hour_mask"] = {"sea_luma_with_mask": stats(p, [0, 600, W, 200])["luma_mean"], "sea_luma_mask_disabled": without_mask,
                                   "sky_luma_with_mask": with_mask}
    p.checkpoint("local")

    # ================================================================ 4. LUT + adjustment layers
    n = 17
    g = np.linspace(0, 1, n)
    values = []
    for b in g:
        for gg in g:
            for r in g:
                l = 0.2126 * r + 0.7152 * gg + 0.0722 * b
                # teal shadows, orange highlights, gentle filmic shoulder
                t = l
                tint = np.array([0.0, 0.10, 0.16]) * (1 - t) ** 2 + np.array([0.12, 0.04, -0.08]) * t ** 2
                rgb = np.array([r, gg, b]) + tint
                rgb = rgb / (1 + 0.15 * rgb)
                values.append([round(float(v), 4) for v in np.clip(rgb * 1.12, 0, 1)])
    step(p, "teal-orange LUT on adjustment layer", [
        {"type": "lut", "name": "teal-orange", "size": n, "values": values},
        {"type": "adjustment", "name": "grade", "effects": [{"name": "contrast", "amount": 6}]},
        {"type": "lookup", "target": "grade", "name": "teal-orange", "amount": 0.6},
    ])
    step(p, "film-finish adjustment layer", [
        {"type": "adjustment", "name": "film-finish", "effects": [
            {"name": "grain", "amount": 0.015, "seed": 3},
            {"name": "vignette", "strength": 0.45, "radius": 0.9},
        ]},
    ])
    # Undo / redo demonstration with a deliberately bad edit.
    step(p, "bad edit: posterize 2 bits", {"type": "posterize", "target": "photo", "amount": 2})
    p.undo()
    p.redo()
    p.undo()
    LOG.append({"step": "undo → redo → undo the posterize", "operations": ["undo", "redo", "undo"]})
    assert all(e["name"] != "posterize" for e in p.layer("photo")["effects"])
    p.checkpoint("graded")

    # ================================================================ 5. branch: monochrome print
    p.branch("mono")
    step(p, "mono branch", [
        {"type": "adjustment", "name": "mono", "effects": [
            {"name": "grayscale"},
            {"name": "curves", "points": [[0, 8], [70, 52], [180, 205], [255, 248]]},
            {"name": "duotone", "amount": 35, "shadow_color": "#1b1a24", "highlight_color": "#f3e6cf"},
        ]},
        {"type": "reorder", "target": "mono", "below": "film-finish"},
    ])
    p.checkpoint("mono-final")
    p.checkout("main")
    assert p.current_branch == "main" and not any(l["name"] == "mono" for l in p.state["layers"])
    p.save(OUT / "lab.vixl")

    # Exports + comparisons (render_compare equivalent from vixl.checks.compare)
    p.at("original").export(str(OUT / "before.jpg"), quality=90)
    p.export(str(OUT / "after.jpg"), quality=90)
    p.at("mono-final").export(str(OUT / "after-mono.jpg"), quality=90)
    img, summary = compare(p, "toned", "local", max_width=1200, max_height=800, mode="diff")
    img.convert("RGB").save(OUT / "compare-diff.jpg", quality=85)
    METRICS["compare_toned_vs_local_diff"] = summary
    METRICS["compare_original_vs_graded"] = compare(p, "original", "graded", max_width=600, max_height=400)[1]
    img, summary = compare(p, "graded", "mono-final", max_width=1600, max_height=560)
    img.convert("RGB").save(OUT / "compare-branches.jpg", quality=85)
    METRICS["compare_graded_vs_mono"] = summary
    stages = ["original", "straightened", "toned", "local", "graded"]
    strip = Image.new("RGB", (5 * 320 + 4 * 6, 213), "#0b0b10")
    for i, ref in enumerate(stages):
        strip.paste(p.at(ref).render().convert("RGB").resize((320, 213), Image.Resampling.LANCZOS), (i * 326, 0))
    strip.save(OUT / "history-strip.jpg", quality=88)
    # CLI: `vixl compare` between a checkpoint and a branch of the saved document, plus `vixl histogram`.
    cli = ["vixl", "--json", "-p", str(OUT / "lab.vixl")]
    subprocess.run(cli + ["compare", "straightened", "mono", "--out", str(WORK / "cli-compare.png")], check=True, capture_output=True)
    Image.open(WORK / "cli-compare.png").convert("RGB").resize((1200, 400), Image.Resampling.LANCZOS).save(OUT / "cli-compare.jpg", quality=85)
    (WORK / "cli-compare.png").unlink()
    hist = subprocess.run(cli + ["histogram", "--region", "0", "0", str(W), "490"], check=True, capture_output=True, text=True)
    METRICS["cli_histogram_sky_after_keys"] = sorted(json.loads(hist.stdout).keys())

    # ================================================================ 6. measurements
    regions = {"full": None, "sky": [0, 0, W, 300], "horizon": [0, 380, W, 100], "sea": [560, 520, 600, 260], "sun": [330, 375, 80, 80]}
    METRICS["regions"] = {}
    for name, region in regions.items():
        # Full frame vs the raw import; regions vs the straightened frame so the pixels line up.
        b = stats(p.at("original" if region is None else "straightened"), region)
        a = stats(p, region)
        METRICS["regions"][name] = {"region": region, "before": {k: v for k, v in b.items() if k != "_hist"},
                                    "after": {k: v for k, v in a.items() if k != "_hist"}}
        if name == "full":
            hist_before, hist_after = b["_hist"], a["_hist"]

    # ================================================================ 7. preset transfer to a second photo
    q = Project(W, H, background="#000")
    step(q, "lake: import", [{"type": "add", "path": str(src2), "name": "photo"}])
    q.checkpoint("imported")
    q.state["presets"]["coastal-base"] = p.state["presets"]["coastal-base"]  # carried over explicitly (see README)
    step(q, "lake: preset-apply coastal-base", [{"type": "select", "shape": "none"},
                                                 {"type": "preset-apply", "name": "coastal-base", "target": "photo",
                                                  "overrides": {"temperature": 900, "saturation": -10}}])
    q.save(OUT / "lake.vixl")
    img, summary = compare(q, "imported", "head", max_width=1600, max_height=560)
    img.convert("RGB").save(OUT / "preset-transfer.jpg", quality=85)
    METRICS["preset_transfer"] = {"compare": summary, "before": {k: v for k, v in stats(q.at("imported")).items() if k != "_hist"},
                                  "after": {k: v for k, v in stats(q).items() if k != "_hist"}}

    after_png = WORK / "after.png"
    p.export(str(after_png))
    straight_png = WORK / "straight.png"
    p.at("straightened").export(str(straight_png))

    global LAB
    LAB = p
    build_selection_map(straight_png)
    build_diptych(hist_before, hist_after)
    union = np.maximum(np.asarray(p.image(MASKS["land: wand + wand, x 2-subpath path"], "L")),
                       np.asarray(p.image(MASKS["figure: path x colour"], "L")))
    Image.fromarray(union).save(WORK / "silhouette-mask.png")
    build_contact_sheet(OUT / "after.jpg")

    (OUT / "metrics.json").write_text(json.dumps(METRICS, indent=1))
    (OUT / "edit-log.json").write_text(json.dumps(LOG, indent=1, ensure_ascii=False))
    shutil.rmtree(WORK)  # intermediates only; the kept documents are copied to output/
    print(json.dumps({k: METRICS[k] for k in ("compare_original_vs_graded", "golden_hour_mask", "reorder_auto_contrast_last")}, indent=1))


# =================================================================== selection map
def build_selection_map(straight_png):
    s = Project(W, H, background="#0b0b10")  # same canvas as the lab so wand/colour/feather match; grown later
    f = fonts(s)
    step(s, "map: base", [{"type": "add", "path": str(straight_png), "name": "base"}])
    # Hidden overlays first, and the recipes replayed before the base is darkened, so wand/colour
    # selections sample exactly the pixels the lab document sampled.
    for i, key in enumerate(SELECTIONS):
        step(s, f"map: overlay {i}", [{"type": "solid", "name": f"sel-{i}", "color": COLORS[i], "width": W, "height": H},
                                      {"type": "hide", "target": f"sel-{i}"}])
    for i, key in enumerate(SELECTIONS):
        step(s, f"map: select {key}", SELECTIONS[key] + [{"type": "mask", "target": f"sel-{i}", "action": "from-selection"}])
        mine = np.asarray(s.image(s.state["selection"], "L"), int)[:H]
        METRICS.setdefault("selection_map_max_diff", {})[key] = int(np.abs(mine - np.asarray(LAB.image(MASKS[key], "L"), int)).max())
    ops = [{"type": "select", "shape": "none"}, {"type": "canvas", "width": W, "height": H + 110},
           {"type": "grayscale", "target": "base"}, {"type": "brightness", "target": "base", "amount": -45}]
    for i, key in enumerate(SELECTIONS):
        x, y = 24 + (i % 3) * 390, H + 26 + (i // 3) * 40
        ops += [{"type": "show", "target": f"sel-{i}"}, {"type": "opacity", "target": f"sel-{i}", "value": 0.62},
                {"type": "shape", "shape": "ellipse", "name": f"dot-{i}", "width": 14, "height": 14, "x": x, "y": y + 4, "fill": COLORS[i]},
                {"type": "text", "name": f"lbl-{i}", "text": key, "size": 16, "color": "#e9e4da", "font": f["label"], "x": x + 24, "y": y}]
    ops += [{"type": "text", "name": "title", "text": "Selections to masks", "size": 32, "color": "#f6ecd7", "font": f["title"], "x": 24, "y": 22},
            {"type": "layer-style", "target": "title", "name": "drop-shadow", "settings": {"blur": 6, "dy": 2, "opacity": 0.7}}]
    step(s, "map: legend", ops)
    s.save(OUT / "selections.vixl")
    s.export(str(OUT / "selections.jpg"), quality=88)


# =================================================================== diptych
def build_diptych(hist_before, hist_after):
    DW, DH = 2000, 1120
    d = Project(DW, DH, background="#0e0d12")
    f = fonts(d)
    pw, ph, top = 960, 640, 150
    ops = [
        {"type": "add", "path": str(OUT / "before.jpg"), "name": "before"},
        {"type": "resize", "target": "before", "width": pw}, {"type": "move", "target": "before", "x": 26, "y": top},
        {"type": "add", "path": str(OUT / "after.jpg"), "name": "after"},
        {"type": "resize", "target": "after", "width": pw}, {"type": "move", "target": "after", "x": DW - 26 - pw, "y": top},
        {"type": "text", "name": "title", "text": "Photo Lab — before / after", "size": 54, "color": "#f6ecd7", "font": f["title"], "x": 26, "y": 34},
        {"type": "text", "name": "sub", "text": "One synthesized raw frame · crop, flip, straighten · 6 selection recipes · 30+ stacked effects · LUT · 2 adjustment layers — all still editable",
         "size": 19, "color": "#a9a3b8", "font": f["label"], "x": 28, "y": 104},
        {"type": "text", "name": "lb", "text": "BEFORE  camera original", "size": 18, "color": "#e9e4da", "font": f["label"], "x": 26, "y": top + ph + 16},
        {"type": "text", "name": "la", "text": "AFTER  graded (checkpoint 'graded')", "size": 18, "color": "#e9e4da", "font": f["label"], "x": DW - 26 - pw, "y": top + ph + 16},
    ]
    for side, hist, x0 in (("b", hist_before, 26), ("a", hist_after, DW - 26 - pw)):
        bins = np.add.reduceat(np.array(hist), np.arange(0, 256, 4))  # 64 bins
        peak = bins[1:-1].max()  # ignore clipped end bins for scaling
        hy, hh = top + ph + 60, 150
        ops.append({"type": "shape", "shape": "rectangle", "name": f"hbg-{side}", "x": x0, "y": hy, "width": pw, "height": hh, "fill": "#17151d"})
        bw = pw / 64
        for i, v in enumerate(bins):
            hgt = max(1, min(hh, round(hh * v / peak)))
            shade = f"oklch({0.35 + 0.6 * i / 63:.3f} 0.06 {60 + 0.4 * i:.0f})"
            ops.append({"type": "shape", "shape": "rectangle", "name": f"h{side}{i}", "x": round(x0 + i * bw + 1), "y": hy + hh - hgt,
                        "width": max(1, round(bw - 2)), "height": hgt, "fill": shade})
    rb, ra = METRICS["regions"]["full"]["before"], METRICS["regions"]["full"]["after"]
    def line(r):
        return (f"luma mean {r['luma_mean']:>5}   p2 {r['p2']:>3}   median {r['p50']:>3}   p98 {r['p98']:>3}   "
                f"R−B {r['rg_balance']:>6}   clip {r['clipped_black_pct']}% / {r['clipped_white_pct']}%")
    ops += [{"type": "text", "name": "sb", "text": line(rb), "size": 15, "color": "#a9a3b8", "font": f["mono"], "x": 26, "y": top + ph + 222},
            {"type": "text", "name": "sa", "text": line(ra), "size": 15, "color": "#a9a3b8", "font": f["mono"], "x": DW - 26 - pw, "y": top + ph + 222},
            {"type": "text", "name": "hcap", "text": "histograms: mean of R, G, B channel histograms from vixl measure(histogram='full'), 64 bins, end bins clipped to frame",
             "size": 14, "color": "#6f6a7d", "font": f["label"], "x": 26, "y": DH - 40}]
    step(d, "diptych", ops)
    d.save(OUT / "diptych.vixl")
    d.export(str(OUT / "diptych.jpg"), quality=88)


# =================================================================== contact sheet
FILTERS = ["sepia", "duotone", "solarize", "pixelate", "halftone", "crosshatch", "ink-blot", "stamp", "photocopy",
           "pencil-sketch", "charcoal", "find-edges", "emboss", "oil-paint", "watercolor", "swirl", "ripple", "wave", "glass"]
WORKFLOWS = [("neon-sign", {"color": "#00f5d4"}, True), ("vintage-print", {}, False), ("comic-poster", {}, False),
             ("cut-paper", {"color": "#e76f51"}, True), ("ink-illustration", {}, False)]


def build_contact_sheet(after_png):
    cols, tw, th, gap, lab, head = 6, 300, 200, 16, 40, 128
    rows = 4
    SW = gap + cols * (tw + gap)
    SH = head + rows * (th + lab + gap) + 40
    c = Project(SW, SH, background="#0e0d12")
    f = fonts(c)
    res = c.apply({"type": "add", "path": str(after_png), "name": "src"}, detail="full")
    asset = c.layer("src")["asset"]
    ops = [{"type": "remove", "target": "src"}, {"type": "select", "shape": "none"},
           {"type": "text", "name": "title", "text": "19 artistic filters + 5 effect workflows", "size": 44, "color": "#f6ecd7", "font": f["title"], "x": gap, "y": 26},
           {"type": "text", "name": "sub", "text": "Every tile is a live layer of one .vixl document: the graded photo (one embedded asset) resized to 300×200, then one filter at its documented default.",
            "size": 17, "color": "#a9a3b8", "font": f["label"], "x": gap + 2, "y": 84}]
    tiles = []
    for i, name in enumerate(FILTERS + [w[0] for w in WORKFLOWS]):
        r, k = divmod(i, cols)
        x, y = gap + k * (tw + gap), head + r * (th + lab + gap)
        tiles.append((name, x, y))
        lid = f"t-{name}"
        ops += [{"type": "add", "asset": asset, "name": lid}, {"type": "resize", "target": lid, "width": tw, "height": th},
                {"type": "move", "target": lid, "x": x, "y": y}]
        if name in FILTERS:
            ops.append({"type": "effect", "target": lid, "name": name})
            caption, kind = name, "filter"
        else:
            caption, kind = name, "workflow"
        ops += [{"type": "text", "name": f"l-{name}", "text": caption, "size": 17, "color": "#f6ecd7", "font": f["label"], "x": x + 2, "y": y + th + 9},
                {"type": "text", "name": f"k-{name}", "text": kind, "size": 12, "color": "#ffb36b" if kind == "workflow" else "#7d7890",
                 "font": f["mono"], "x": x + tw - 8 * len(kind) - 4, "y": y + th + 13}]
    step(c, "sheet: tiles", ops)
    # Style-based workflows act on a silhouette cut-out above a dimmed tile.
    for name, variables, cutout in WORKFLOWS:
        _, x, y = next(t for t in tiles if t[0] == name)
        if cutout:
            # Union of the lab's land + figure selection masks, imported as a layer mask (mask import).
            step(c, f"sheet: {name} cut-out", [
                {"type": "duplicate", "target": f"t-{name}", "name": f"c-{name}"},
                {"type": "mask", "target": f"c-{name}", "action": "import", "path": str(WORK / "silhouette-mask.png")},
                {"type": "brightness", "target": f"t-{name}", "amount": -40},
                {"type": "text-set", "target": f"l-{name}", "text": f"{name} (silhouettes)"},
            ])
    c.save(WORK / "sheet.vixl")
    session = Session("sheet.vixl", workspace=WORK)
    for name, variables, cutout in WORKFLOWS:
        target = f"c-{name}" if cutout else f"t-{name}"
        r = dispatch(session, "effect-run", {"name": name, "variables": {"target": target, **variables}, "dry_run": False})
        LOG.append({"step": f"workflow effect-run {name}", "operations": ["effect-run"], "result_keys": sorted(r.keys())})
    wf = dispatch(session, "resource-get", {"kind": "workflows", "name": "vintage-print"})
    METRICS["workflow_resource_vintage_print"] = wf
    c = Project.load(WORK / "sheet.vixl")
    c.export(str(OUT / "contact-sheet.jpg"), quality=90)
    shutil.copy(WORK / "sheet.vixl", OUT / "contact-sheet.vixl")


if __name__ == "__main__":
    main()
