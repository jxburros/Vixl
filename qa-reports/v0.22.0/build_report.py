"""Build the Vixl 0.22.0 QA report with Vixl itself (Python API of the installed release wheel).

Usage: venv/bin/python build_report.py QA_DIR OUT_DIR
"""
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

from PIL import Image

from vixl import Project

QA = Path(sys.argv[1]).resolve()
OUT = Path(sys.argv[2]).resolve()
OUT.mkdir(parents=True, exist_ok=True)
THUMBS = OUT / "thumbs"
THUMBS.mkdir(exist_ok=True)
VIXL = str(Path(sys.executable).with_name("vixl"))
CONTENT = json.loads((Path(__file__).with_name("content.json")).read_text())

W, H, M = 1240, 1754, 90
INK, MUTED, PAPER, NAVY, AMBER, RULE = "#111827", "#4b5563", "#ffffff", "#0b1020", "#f59e0b", "#e5e7eb"
SEV = {"high": "#dc2626", "medium": "#ea580c", "low": "#ca8a04", "ux": "#2563eb", "docs": "#7c3aed", "pass": "#059669"}
SEV_ORDER = ["high", "medium", "low", "ux", "docs", "pass"]
AREAS = CONTENT["areas"]

findings = {}
for key in AREAS:
    path = QA / key / "findings.json"
    findings[key] = json.loads(path.read_text()) if path.exists() else []


def esc(text):
    text = str(text).replace("\\", "/")
    for ch in "*_[]~#`{}":
        text = text.replace(ch, "\\" + ch)
    return " ".join(text.split()).replace("$\\{", "$\u200b\\{")


def clip(text, n):
    text = str(text)
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


def thumb(src, max_side=1100):
    src = Path(src)
    dst = THUMBS / (src.parent.name + "-" + src.stem + ".png")
    if not dst.exists():
        im = Image.open(src)
        if getattr(im, "n_frames", 1) > 1:
            im.seek(min(im.n_frames - 1, im.n_frames // 2))
        im = im.convert("RGBA")
        im.thumbnail((max_side, max_side))
        bg = Image.new("RGB", im.size, "white")
        bg.paste(im, mask=im.split()[3])
        bg.save(dst, optimize=True)
    return dst


def fit_image(src, name, x, y, w, h, page, frame=True):
    t = thumb(src)
    iw, ih = Image.open(t).size
    s = min(w / iw, h / ih)
    dw, dh = iw * s, ih * s
    ops = []
    if frame:
        ops.append({"type": "shape", "shape": "rectangle", "name": name + "-bg", "x": x, "y": y, "width": w, "height": h,
                    "fill": "#f3f4f6", "page": page})
    ops.append({"type": "add", "path": str(t), "name": name, "x": round(x + (w - dw) / 2, 1), "y": round(y + (h - dh) / 2, 1),
                "width": round(dw), "height": round(dh), "page": page})
    return ops


def text(name, value, x, y, size, color=INK, font="body", page=None, **extra):
    op = {"type": "text", "name": name, "text": value, "x": x, "y": y, "size": size, "color": color, "font": font, **extra}
    if page:
        op["page"] = page
    return op


def rich(name, md, x, y, width, size=19, color=INK, page=None, line_height=1.4):
    return {"type": "rich-text", "name": name, "markdown": md, "x": x, "y": y, "width": int(width), "size": size, "color": color,
            "font": "body", "line_height": line_height, "page": page}


def header(page, kicker, title):
    return [
        text(page + "-kicker", kicker.upper(), M, 92, 18, "#9a3412", "heading", page),
        text(page + "-title", title, M, 124, 46, INK, "heading", page),
        {"type": "shape", "shape": "rectangle", "name": page + "-rule", "x": M, "y": 196, "width": W - 2 * M, "height": 3,
         "fill": INK, "page": page},
    ]


doc = OUT / "vixl-0.22.0-qa-report.vixl"
for f in [doc]:
    if f.exists():
        f.unlink()
subprocess.run([VIXL, "new", f"{W}x{H}", "-o", str(doc), "--background", PAPER, "--dpi", "150"], check=True, capture_output=True)
subprocess.run([VIXL, "-p", str(doc), "font", "pair", CONTENT["pairing"]], check=True, capture_output=True)
p = Project.load(doc)

p.apply([
    {"type": "page", "action": "add", "name": "cover", "background": NAVY},
    {"type": "master", "action": "add", "name": "std"},
    {"type": "shape", "shape": "rectangle", "name": "m-top", "x": 0, "y": 0, "width": W, "height": 14, "fill": AMBER},
    {"type": "shape", "shape": "rectangle", "name": "m-foot-rule", "x": M, "y": H - 92, "width": W - 2 * M, "height": 1, "fill": RULE},
    text("m-foot-left", "Vixl 0.22.0 · QA, stress & exploration report · " + CONTENT["date"], M, H - 78, 15, MUTED),
    {"type": "text", "name": "m-foot-num", "text": "${page} / ${pages}", "x": W - M - 120, "y": H - 78, "size": 15,
     "color": MUTED, "font": "body"},
])

# ---------------------------------------------------------------- cover
c = CONTENT["cover"]
ops = [{"type": "page", "action": "select", "page": "cover"}]
ops += [
    {"type": "shape", "shape": "rectangle", "name": "cv-strip", "x": 0, "y": 0, "width": W, "height": 18, "fill": AMBER, "page": "cover"},
    text("cv-kicker", c["kicker"], M, 110, 22, AMBER, "heading", "cover"),
    rich("cv-title", c["title"], M, 150, W - 2 * M, 74, "#ffffff", "cover", 1.1),
    rich("cv-sub", c["subtitle"], M, 430, W - 2 * M - 40, 26, "#cbd5e1", "cover", 1.45),
]
ops += fit_image(QA / "creative/hero-mandala.png", "cv-hero", 600, 650, 560, 560, "cover", frame=False)
ops += fit_image(QA / "creative/hero-poster.png", "cv-hero2", M, 690, 420, 520, "cover", frame=False)
y = 1300
for i, (num, label) in enumerate(c["stats"]):
    x = M + i * 270
    ops += [
        text(f"cv-stat{i}", num, x, y, 64, AMBER, "heading", "cover"),
        text(f"cv-statl{i}", label, x, y + 86, 18, "#cbd5e1", "body", "cover", ),
    ]
ops += [text("cv-foot", c["footer"], M, H - 110, 17, "#94a3b8", "body", "cover")]
p.apply(ops)

# ---------------------------------------------------------------- summary
def new_page(name):
    p.apply([{"type": "page", "action": "add", "name": name, "master": "std"}])


new_page("summary")
s = CONTENT["summary"]
ops = header("summary", "Executive summary", s["title"])
ops.append(rich("sum-verdict", s["verdict"], M, 230, W - 2 * M, 20, INK, "summary", 1.42))
p.apply(ops)


def bottom(name):
    layer = p.layer(name)
    return layer["y"] + layer["height"]


issues_all = [f for k in AREAS for f in findings[k] if f.get("severity") != "pass"]
sev_count = Counter(f["severity"] for k in AREAS for f in findings[k])
tiles = [(str(sum(len(findings[k]) for k in AREAS)), "checks recorded"), (str(len(issues_all)), "issues logged"),
         (str(sev_count.get("high", 0)), "high severity"), (str(sev_count.get("medium", 0)), "medium severity")]
ty = round(bottom("sum-verdict") + 40)
ops = []
for i, (num, label) in enumerate(tiles):
    x = M + i * 270
    ops += [
        {"type": "shape", "shape": "rounded-rectangle", "name": f"tile{i}", "x": x, "y": ty, "width": 250, "height": 140, "radius": 16,
         "fill": "#f9fafb", "stroke": RULE, "stroke_width": 2, "page": "summary"},
        text(f"tilen{i}", num, x + 24, ty + 16, 56, SEV["high"] if "high" in label else SEV["medium"] if "medium" in label else INK,
             "heading", "summary"),
        text(f"tilel{i}", label, x + 24, ty + 96, 18, MUTED, "body", "summary"),
    ]
ops.append(text("sum-top-h", "Top issues", M, ty + 180, 30, INK, "heading", "summary"))
top_md = "\n".join(
    f"- [**{t['sev'].upper()}**]{{color={SEV[t['sev']]}}} **{esc(t['id'])}** {esc(t['text'])}" for t in s["top"])
size = 18
while True:
    trial = ops + [rich("sum-top", top_md, M, ty + 230, W - 2 * M, size, INK, "summary", 1.36)]
    p.apply(trial, dry_run=True)
    p.apply([rich("sum-top-probe", top_md, M, ty + 230, W - 2 * M, size, INK, "summary", 1.36)])
    fits = bottom("sum-top-probe") <= H - 110
    p.apply([{"type": "remove", "target": "sum-top-probe", "page": "summary"}])
    if fits or size <= 14:
        break
    size -= 1
p.apply(trial)

# ---------------------------------------------------------------- charts / numbers
new_page("numbers")
n = CONTENT["numbers"]
ops = header("numbers", "At a glance", n["title"])
cats = [AREAS[k]["short"] for k in AREAS]
series = []
for sev in SEV_ORDER[:-1]:
    series.append({"name": sev, "values": [sum(1 for f in findings[k] if f.get("severity") == sev) for k in AREAS], "color": SEV[sev]})
ops.append({"type": "chart", "kind": "stacked-horizontal-bar", "name": "chart-areas", "x": M, "y": 230, "width": 620, "height": 520,
            "title": "Issues by area and severity", "categories": cats, "series": series, "legend": "bottom", "font_size": 17,
            "total_labels": True, "page": "numbers"})
slices = [s_ for s_ in SEV_ORDER if sev_count.get(s_)]
ops.append({"type": "chart", "kind": "donut", "name": "chart-sev", "x": 740, "y": 230, "width": 410, "height": 520,
            "title": "All checks by outcome", "categories": slices,
            "series": [{"name": "checks", "values": [sev_count[s_] for s_ in slices]}], "colors": [SEV[s_] for s_ in slices],
            "center_text": str(sum(sev_count.values())), "legend": "bottom", "font_size": 17, "page": "numbers"})
ops.append(text("num-h", "Measured numbers", M, 800, 30, INK, "heading", "numbers"))
ops.append(rich("num-left", n["left"], M, 850, (W - 2 * M) / 2 - 20, 17, INK, "numbers", 1.4))
ops.append(rich("num-right", n["right"], M + (W - 2 * M) / 2 + 20, 850, (W - 2 * M) / 2 - 20, 17, INK, "numbers", 1.4))
p.apply(ops)

# ---------------------------------------------------------------- method
new_page("method")
mth = CONTENT["method"]
ops = header("method", "How we tested", mth["title"])
ops.append({"type": "text-flow", "name": "method-flow", "markdown": mth["body"], "size": 18, "color": INK, "font": "body",
            "frames": [{"x": M, "y": 230, "width": W - 2 * M, "height": 1380, "columns": 2, "gutter": 44, "page": "method"}]})
p.apply(ops)

# ---------------------------------------------------------------- findings (one story through as many pages as it needs)
parts = []
for key, meta in AREAS.items():
    items = findings[key]
    issues = sorted([f for f in items if f.get("severity") != "pass"], key=lambda f: SEV_ORDER.index(f.get("severity", "low")))
    passes = [f for f in items if f.get("severity") == "pass"]
    parts.append(f"# {esc(meta['title'])}\n{esc(meta['blurb'])} *{len(issues)} issues, {len(passes)} notable passes.*")
    for f in issues:
        sev = f.get("severity", "low")
        parts.append(
            f"## {esc(f['id'])} · {esc(f['title'])}\n"
            f"[**{sev.upper()}**]{{color={SEV[sev]}}} · {esc(f.get('area', ''))}\n"
            f"**Steps:** {esc(clip(f.get('steps', ''), 420))}\n"
            f"**Expected:** {esc(clip(f.get('expected', ''), 300))}\n"
            f"**Actual:** {esc(clip(f.get('actual', ''), 520))}")
    if passes:
        parts.append("**Notable passes**\n" + "\n".join(
            f"- [**PASS**]{{color={SEV['pass']}}} **{esc(f['id'])}** {esc(f['title'])}: {esc(clip(f.get('actual', ''), 230))}" for f in passes))
story = "\n\n".join(parts)

frame = {"x": M, "y": 120, "width": W - 2 * M, "height": 1500, "columns": 2, "gutter": 44}
new_page("findings-1")
p.apply([{"type": "text-flow", "name": "findings", "markdown": story, "size": 16, "color": INK, "font": "body",
          "keep_together": True, "orphans": 2, "widows": 2, "frames": [{**frame, "page": "findings-1"}]}])
k = 1
while p.state["flows"]["findings"].get("overflow", {}).get("overflow"):
    k += 1
    new_page(f"findings-{k}")
    p.apply([{"type": "text-flow", "name": "findings", "action": "add-frame", **frame, "page": f"findings-{k}"}])
    if k > 60:
        raise SystemExit("findings flow does not converge")
print("findings pages:", k)

# ---------------------------------------------------------------- gallery
gallery = [(QA / g["path"], g["caption"]) for g in CONTENT["gallery"] if (QA / g["path"]).exists()]
per = 6
cw, ch = (W - 2 * M - 40) / 2, 400
for gi in range(0, len(gallery), per):
    name = f"gallery-{gi // per + 1}"
    new_page(name)
    ops = header(name, "Gallery", "Made with Vixl during testing" if gi == 0 else "Gallery, continued")
    for j, (src, cap) in enumerate(gallery[gi:gi + per]):
        x = M + (j % 2) * (cw + 40)
        y = 230 + (j // 2) * (ch + 90)
        ops += fit_image(src, f"{name}-img{j}", x, y, cw, ch, name)
        ops.append(rich(f"{name}-cap{j}", cap, x, y + ch + 10, cw, 15, MUTED, name, 1.3))
    p.apply(ops)

# ---------------------------------------------------------------- closing
new_page("closing")
cl = CONTENT["closing"]
ops = header("closing", "Colophon", cl["title"])
ops.append({"type": "text-flow", "name": "closing-flow", "markdown": cl["body"], "size": 18, "color": INK, "font": "body",
            "frames": [{"x": M, "y": 230, "width": W - 2 * M, "height": 1380, "columns": 2, "gutter": 44, "page": "closing"}]})
p.apply(ops)

p.save(doc)
print("saved", doc)
