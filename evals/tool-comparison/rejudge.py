"""Build a blind judging package for the tool comparison: every lane of every test, both rounds.

    python evals/tool-comparison/rejudge.py RUNS OUT [--tests T01 T03] [--seed N]

RUNS is a `runs/` folder in which every lane's deliverables exist (the non-Vixl lanes commit only
their sources, so rebuild them first). OUT receives:

- `package/<test>/`: what a judge sees. `brief.md`, `round2-request.md`, `scores-template.json`, and
  one folder per lane under a random four-letter code, with `r1/` and `r2/` inside. Each round has
  `files/` (the deliverables named in the brief, with producer metadata stripped), `views/` (images
  to judge from) and `facts.json` (measured sizes, pages, frames, fonts, fields).
- `sealed/key.csv`: which code is which lane. Judges must not open it.

The views put every lane on an equal footing, which is the point of the package:
- vector files (SVG, PDF, PPTX) are rendered at a common size, so nothing is judged from a thumbnail;
- rasters are never upscaled with smoothing: large ones get a fitted overview plus 1:1 crops, and
  images 128 px or smaller also get a nearest-neighbour enlargement, labelled as such;
- animations become a contact sheet of evenly spaced frames, with timestamps.

Needs Pillow, pypdf, Playwright with Chromium, pdftoppm, LibreOffice (PPTX) and ffmpeg.
"""

import argparse
import csv
import io
import json
import os
from pathlib import Path
import random
import re
import shutil
import string
import struct
import subprocess
import sys
import tempfile
import zipfile

from PIL import Image, ImageDraw, ImageSequence

sys.path.insert(0, str(Path(__file__).resolve().parent))
from inspect_outputs import file_facts  # noqa: E402

KIT = Path(__file__).resolve().parent
DELIVERABLE = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".pdf", ".pptx", ".ico", ".mp4", ".json"}
SKIP_DIRS = {"round2", "src", "build", "px", "fonts", "node_modules", "__pycache__", "scratch", "work", "tmp"}
FIT = 1600  # longest side of an overview view
CROP = 900  # side of a 1:1 detail crop
SMALL = 128  # rasters at or below this also get a nearest-neighbour enlargement
CHROMIUM = os.environ.get("CHROMIUM", "/opt/pw-browsers/chromium")


def brief_path(test):
    return next(KIT.glob(f"briefs/{test}-*.md"))


def deliverable_names(test, round2=True):
    """File names the brief asks for, plus, for round 2, any the change request adds."""
    text = brief_path(test).read_text(encoding="utf-8") + (round2_request(test) if round2 else "")
    names = []
    for token in re.findall(r"`([^`\s]+)`", text):
        if Path(token).suffix.lower() in DELIVERABLE and "fixtures/" not in token:
            names.append(re.sub(r"-\d\d\.png$", "-*.png", token))
    return list(dict.fromkeys(names))


def round2_request(test):
    lines = (KIT / "TESTS.md").read_text(encoding="utf-8").splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith(f"## {test} "))
    quote, inside = [], False
    for line in lines[start + 1:]:
        if line.startswith("## "):
            break
        if line.strip() == "**Round 2**":
            inside = True
            continue
        if inside and line.startswith(">"):
            quote.append(line[1:].strip())
        elif inside and quote:
            break
    return " ".join(quote)


def find_deliverables(run, names):
    found = []
    candidates = [p for p in run.rglob("*") if p.is_file() and not SKIP_DIRS & set(p.relative_to(run).parts[:-1])]
    for name in names:
        matches = sorted((p for p in candidates if p.relative_to(run).match(name) or p.match(Path(name).name)),
                         key=lambda p: (len(p.relative_to(run).parts), str(p)))
        if "*" in name:
            found.extend(matches)
        elif matches:
            found.append(matches[0])
    return list(dict.fromkeys(found))


# Metadata stripping: keep every pixel, glyph and field; drop what names the producing tool.

def strip_png(data):
    out, pos = [data[:8]], 8
    while pos < len(data):
        length = struct.unpack(">I", data[pos:pos + 4])[0]
        kind = data[pos + 4:pos + 8]
        chunk = data[pos:pos + 12 + length]
        if kind not in (b"tEXt", b"zTXt", b"iTXt", b"tIME"):
            out.append(chunk)
        pos += 12 + length
    return b"".join(out)


def strip_jpeg(data):
    out, pos = [data[:2]], 2
    while pos < len(data):
        marker = data[pos:pos + 2]
        if marker[0] != 0xFF or marker[1] == 0xDA:
            out.append(data[pos:])
            break
        length = struct.unpack(">H", data[pos + 2:pos + 4])[0]
        if marker[1] not in (0xE1, 0xFE):  # APP1 (Exif/XMP) and COM
            out.append(data[pos:pos + 2 + length])
        pos += 2 + length
    return b"".join(out)


def strip_svg(text):
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    text = re.sub(r"<metadata\b.*?</metadata>", "", text, flags=re.S)
    text = re.sub(r"<sodipodi:namedview\b.*?(/>|</sodipodi:namedview>)", "", text, flags=re.S)
    text = re.sub(r'\s(?:inkscape|sodipodi):[\w-]+="[^"]*"', "", text)
    text = re.sub(r'\sxmlns:(?:inkscape|sodipodi)="[^"]*"', "", text)
    return text.replace("matplotlib.", "")


def strip_pdf(src, dst):
    from pypdf import PdfReader, PdfWriter
    from pypdf.generic import DictionaryObject, NameObject

    writer = PdfWriter(clone_from=PdfReader(str(src)))
    title = (writer.metadata or {}).get("/Title")
    writer.metadata = None
    writer.add_metadata({"/Producer": "", "/Creator": "", **({"/Title": title} if title else {})})
    for ref in range(1, len(writer._objects) + 1):  # XMP packets can sit on pages, images and fonts too
        try:
            obj = writer.get_object(ref)
        except Exception:  # noqa: BLE001 - freed or unreadable slots
            continue
        if isinstance(obj, DictionaryObject):
            obj.pop(NameObject("/Metadata"), None)
    writer.compress_identical_objects(remove_identicals=False, remove_orphans=True)
    with open(dst, "wb") as handle:
        writer.write(handle)


def strip_pptx(src, dst):
    with zipfile.ZipFile(src) as zin, zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename == "docProps/app.xml":
                data = re.sub(rb"<Application>.*?</Application>", b"<Application></Application>", data)
                data = re.sub(rb"<AppVersion>.*?</AppVersion>", b"", data)
            elif item.filename == "docProps/core.xml":
                data = re.sub(rb"<(dc:creator|cp:lastModifiedBy)>.*?</\1>", rb"<\1></\1>", data)
            zout.writestr(item, data)


def copy_stripped(src, dst):
    dst.parent.mkdir(parents=True, exist_ok=True)
    suffix = src.suffix.lower()
    if suffix == ".png":
        dst.write_bytes(strip_png(src.read_bytes()))
    elif suffix in (".jpg", ".jpeg"):
        dst.write_bytes(strip_jpeg(src.read_bytes()))
    elif suffix == ".svg":
        dst.write_text(strip_svg(src.read_text(encoding="utf-8")), encoding="utf-8")
    elif suffix == ".pdf":
        strip_pdf(src, dst)
    elif suffix == ".pptx":
        strip_pptx(src, dst)
    elif suffix == ".mp4":
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-map", "0", "-map_metadata", "-1",
                        "-c", "copy", "-fflags", "+bitexact", str(dst)], check=True)
    else:
        shutil.copy2(src, dst)


# Views

def save_view(image, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path)


def raster_views(image, stem, views, note):
    """Overview, 1:1 crops of large images, and nearest enlargement of small ones."""
    image = image.convert("RGBA") if image.mode in ("P", "LA", "PA") else image
    w, h = image.size
    if max(w, h) <= FIT:
        save_view(image, views / f"{stem}.view.png")
        note.append(f"{stem}.view.png: the image at its real size, {w}×{h}")
    else:
        scale = FIT / max(w, h)
        fit = image.resize((round(w * scale), round(h * scale)), Image.LANCZOS)
        save_view(fit, views / f"{stem}.overview.png")
        note.append(f"{stem}.overview.png: reduced to {fit.width}×{fit.height} from {w}×{h} (judge detail on the crops)")
        cols, rows = (2, 2) if min(w, h) > 2 * CROP else (2, 1) if w >= h else (1, 2)
        for row in range(rows):
            for col in range(cols):
                cx, cy = w * (2 * col + 1) // (2 * cols), h * (2 * row + 1) // (2 * rows)
                box = (max(0, cx - CROP // 2), max(0, cy - CROP // 2), min(w, cx + CROP // 2), min(h, cy + CROP // 2))
                name = f"{stem}.crop-{row + 1}-{col + 1}.png"
                save_view(image.crop(box), views / name)
                note.append(f"{name}: 1:1 pixels, x {box[0]}–{box[2]}, y {box[1]}–{box[3]}")
    if max(w, h) <= SMALL:
        factor = max(2, 512 // max(w, h))
        big = image.convert("RGBA").resize((w * factor, h * factor), Image.NEAREST)
        backed = checker(*big.size, size=factor * 2)
        backed.paste(big, (0, 0), big)
        big = backed
        save_view(big, views / f"{stem}.enlarged-x{factor}-nearest.png")
        note.append(f"{stem}.enlarged-x{factor}-nearest.png: the {w}×{h} image enlarged ×{factor} with hard pixels, over a checkerboard where it is transparent")


def checker(w, h, size=12):
    """Light checkerboard behind transparent pixels, so transparency is visible and not read as black."""
    board = Image.new("RGB", (w, h), "#e6e6e6")
    draw = ImageDraw.Draw(board)
    for y in range(0, h, size):
        for x in range((y // size) % 2 * size, w, 2 * size):
            draw.rectangle((x, y, x + size - 1, y + size - 1), fill="#c8c8c8")
    return board


def contact_sheet(frames, labels, cell=360):
    cols = min(4, len(frames))
    rows = -(-len(frames) // cols)
    w0, h0 = frames[0].size
    scale = min(1, cell / max(w0, h0)) if max(w0, h0) > cell else max(1, cell // max(w0, h0))
    tw, th = int(w0 * scale), int(h0 * scale)
    sheet = Image.new("RGB", (cols * (tw + 8) + 8, rows * (th + 30) + 8), "#808080")
    draw = ImageDraw.Draw(sheet)
    for i, (frame, label) in enumerate(zip(frames, labels)):
        x, y = 8 + (i % cols) * (tw + 8), 8 + (i // cols) * (th + 30)
        method = Image.NEAREST if scale > 1 else Image.LANCZOS
        frame = frame.convert("RGBA").resize((tw, th), method)
        sheet.paste(checker(tw, th), (x, y))
        sheet.paste(frame, (x, y), frame)
        draw.text((x, y + th + 6), label, fill="white")
    return sheet


def gif_views(path, stem, views, note):
    with Image.open(path) as im:
        frames, labels, t = [], [], 0
        for frame in ImageSequence.Iterator(im):
            frames.append(frame.convert("RGBA").copy())
            labels.append(f"{t / 1000:.2f} s")
            t += frame.info.get("duration", 0)
    pick = sorted({round(i * (len(frames) - 1) / 11) for i in range(12)}) if len(frames) > 12 else range(len(frames))
    sheet = contact_sheet([frames[i] for i in pick], [f"frame {i + 1} · {labels[i]}" for i in pick])
    save_view(sheet, views / f"{stem}.frames.png")
    note.append(f"{stem}.frames.png: {len(pick)} of {len(frames)} frames, evenly spaced (open the GIF in files/ to play it)")
    raster_views(frames[0], f"{stem}.first-frame", views, note)


def video_views(path, stem, views, note):
    duration = float(file_facts(path).get("duration_s", 0))
    frames, labels = [], []
    with tempfile.TemporaryDirectory() as tmp:
        for i in range(12):
            t = duration * (i + 0.5) / 12
            out = Path(tmp) / f"{i}.png"
            subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.3f}", "-i", str(path), "-frames:v", "1", str(out)],
                           check=True)
            frames.append(Image.open(out).copy())
            labels.append(f"{t:.2f} s")
    save_view(contact_sheet(frames, labels), views / f"{stem}.frames.png")
    note.append(f"{stem}.frames.png: 12 frames at evenly spaced times (open the MP4 in files/ to watch it)")
    raster_views(frames[len(frames) // 2], f"{stem}.mid-frame", views, note)


def svg_views(path, stem, views, note, browser):
    text = path.read_text(encoding="utf-8")
    match = re.search(r'viewBox="\s*[-\d.]+[\s,]+[-\d.]+[\s,]+([\d.]+)[\s,]+([\d.]+)', text)
    if match:
        vw, vh = float(match.group(1)), float(match.group(2))
    else:
        width = re.search(r'<svg[^>]*\swidth="([\d.]+)', text)
        height = re.search(r'<svg[^>]*\sheight="([\d.]+)', text)
        vw, vh = float(width.group(1)) if width else 1000, float(height.group(1)) if height else 1000
    scale = FIT / max(vw, vh)
    w, h = max(1, round(vw * scale)), max(1, round(vh * scale))
    page = browser.new_page(viewport={"width": w, "height": h})
    with tempfile.TemporaryDirectory() as tmp:
        holder = Path(tmp) / "view.html"  # a file page, so Chromium lets the <img> load a file:// URL
        holder.write_text(f'<html><body style="margin:0;background:#fff"><img src="{path.resolve().as_uri()}" '
                          f'style="width:{w}px;height:{h}px;display:block"></body></html>', encoding="utf-8")
        page.goto(holder.as_uri())
        page.wait_for_function("document.images[0].complete")
        if not page.evaluate("document.images[0].naturalWidth"):
            raise RuntimeError("Chromium could not draw the SVG")
        data = page.screenshot()
    page.close()
    save_view(Image.open(io.BytesIO(data)), views / f"{stem}.render.png")
    note.append(f"{stem}.render.png: the vector drawn by Chromium at {w}×{h} on white "
                f"(its own size is {vw:g}×{vh:g}; vector, so this is sharp, not enlarged)")


def pdf_views(path, stem, views, note, label="PDF"):
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(["pdftoppm", "-r", "100", "-l", "12", "-png", str(path), f"{tmp}/p"], check=True)
        pages = sorted(Path(tmp).glob("p-*.png"))
        for i, page in enumerate(pages, 1):
            im = Image.open(page)
            save_view(im, views / f"{stem}.page-{i}.png")
            note.append(f"{stem}.page-{i}.png: {label} page {i} at 100 dpi ({im.width}×{im.height})")
        subprocess.run(["pdftoppm", "-r", "300", "-l", "4", "-png", str(path), f"{tmp}/h"], check=True)
        for i, page in enumerate(sorted(Path(tmp).glob("h-*.png")), 1):
            im = Image.open(page)
            sub = []
            raster_views(im, f"{stem}.page-{i}.300dpi", Path(tmp) / "x", sub)
            for name in sorted((Path(tmp) / "x").glob(f"{stem}.page-{i}.300dpi.crop-*.png")):
                shutil.move(str(name), views / name.name)
            note.extend(line for line in sub if ".crop-" in line)
            shutil.rmtree(Path(tmp) / "x", ignore_errors=True)


def pptx_views(path, stem, views, note):
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(["soffice", "--headless", "--convert-to", "pdf", "--outdir", tmp, str(path)],
                       check=True, capture_output=True)
        pdf_views(Path(tmp) / f"{path.stem}.pdf", stem, views, note,
                  label="slide, drawn by LibreOffice (fonts and effects can differ from PowerPoint)")


def ico_views(path, stem, views, note):
    with Image.open(path) as im:
        sizes = sorted(im.info.get("sizes", {im.size}))
        for size in sizes:
            im.size = size
            raster_views(im.convert("RGBA").copy(), f"{stem}.{size[0]}px", views, note)


def make_views(src, views, note, browser):
    stem, suffix = src.name, src.suffix.lower()
    if suffix == ".svg":
        svg_views(src, stem, views, note, browser)
    elif suffix == ".pdf":
        pdf_views(src, stem, views, note)
    elif suffix == ".pptx":
        pptx_views(src, stem, views, note)
    elif suffix == ".ico":
        ico_views(src, stem, views, note)
    elif suffix == ".mp4":
        video_views(src, stem, views, note)
    elif suffix == ".gif" and getattr(Image.open(src), "n_frames", 1) > 1:
        gif_views(src, stem, views, note)
    elif suffix in (".png", ".jpg", ".jpeg", ".gif"):
        with Image.open(src) as im:
            raster_views(im.copy(), stem, views, note)


def template(test, codes):
    lane = {
        "fidelity": None, "fidelity_misses": [],
        "craft": None,
        "craft_sub": {"hierarchy": None, "spacing": None, "type": None, "colour": None, "finish": None, "motif": None},
        "defects": [], "craft_notes": "",
        "revision": None, "revision_notes": "",
    }
    pairs = [{"a": a, "b": b, "publish": None, "margin": None, "why": ""}
             for i, a in enumerate(codes) for b in codes[i + 1:]]
    return {"test": test, "judge": "", "lanes": {code: json.loads(json.dumps(lane)) for code in codes},
            "pairwise_round1": pairs}


def build(runs, out, tests, seed):
    from playwright.sync_api import sync_playwright

    rng = random.Random(seed)
    package, sealed = out / "package", out / "sealed"
    sealed.mkdir(parents=True, exist_ok=True)
    key_rows, excluded = [], []
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=CHROMIUM if Path(CHROMIUM).exists() else None)
        for test in tests:
            lanes = sorted(d for d in (runs / test).iterdir() if d.is_dir() and d.name.startswith("claude-"))
            names_by_round = {"r1": deliverable_names(test, round2=False), "r2": deliverable_names(test)}
            for lane in list(lanes):
                if not any(find_deliverables(run, names_by_round[rnd])
                           for rnd, run in (("r1", lane), ("r2", lane / "round2")) if run.is_dir()):
                    lanes.remove(lane)
                    excluded.append(f"{test} {lane.name}: no deliverables in either round, so it is not judged")
            dest = package / test
            shutil.rmtree(dest, ignore_errors=True)
            dest.mkdir(parents=True)
            shutil.copy(brief_path(test), dest / "brief.md")
            shutil.copy(KIT / "JUDGING.md", dest / "JUDGING.md")
            (dest / "round2-request.md").write_text(f"# {test} · round 2 request\n\n> {round2_request(test)}\n",
                                                    encoding="utf-8")
            codes = []
            for lane in rng.sample(lanes, len(lanes)):
                code = None
                while code is None or code in codes:
                    code = "".join(rng.choices(string.ascii_uppercase, k=4))
                codes.append(code)
                key_rows.append((test, code, lane.name))
                for rnd, run in (("r1", lane), ("r2", lane / "round2")):
                    names = names_by_round[rnd]
                    files = find_deliverables(run, names) if run.is_dir() else []
                    base = dest / code / rnd
                    note, facts = [], {}
                    for src in files:
                        rel = src.relative_to(run)
                        target = base / "files" / rel
                        copy_stripped(src, target)
                        facts[str(rel)] = file_facts(target)
                        try:
                            make_views(target, base / "views", note, browser)
                        except Exception as error:  # noqa: BLE001 - a file that can't be viewed is reported
                            note.append(f"{rel}: could not make a view ({type(error).__name__}: {error})"[:300])
                    missing = [n for n in names if not any(Path(str(f.relative_to(run))).match(n) for f in files)]
                    base.mkdir(parents=True, exist_ok=True)
                    (base / "facts.json").write_text(json.dumps(facts, indent=1, ensure_ascii=False), encoding="utf-8")
                    lines = [f"# {code} · {rnd}", ""]
                    if not files:
                        lines.append("No deliverables for this round.")
                    if missing:
                        lines.append("Not delivered: " + ", ".join(missing))
                        lines.append("")
                    lines += [f"- {line}" for line in note]
                    (base / "VIEWS.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
            (dest / "scores-template.json").write_text(json.dumps(template(test, sorted(codes)), indent=1),
                                                       encoding="utf-8")
            print(test, "lanes:", len(codes))
        browser.close()
    if excluded:
        (sealed / "excluded.txt").write_text("\n".join(excluded) + "\n", encoding="utf-8")
        print("\n".join(excluded))
    key = sealed / "key.csv"
    if key.exists():  # keep the codes of tests this run didn't rebuild
        with open(key, newline="", encoding="utf-8") as handle:
            key_rows += [tuple(row) for row in csv.reader(handle) if row and row[0] not in tests and row[0] != "test"]
    with open(key, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["test", "code", "lane"])
        writer.writerows(sorted(key_rows))


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("runs", type=Path)
    parser.add_argument("out", type=Path)
    parser.add_argument("--tests", nargs="*", default=[f"T{i:02d}" for i in range(1, 17)])
    parser.add_argument("--seed", type=int, default=None)
    args = parser.parse_args()
    build(args.runs, args.out, args.tests, args.seed)


if __name__ == "__main__":
    main()
