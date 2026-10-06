"""Proof pages: one self-contained, offline HTML page for reviewing a set of documents and exports.

Each item shows a thumbnail (click to enlarge, no script needed), its format, size and colour
metadata, the ``vixl_check`` findings of a document, and optionally a before/after comparison.
With ``decisions`` every item gets approve/reject and a note, and a button downloads the choices as
a JSON file: a static page cannot write files, so the reviewer sends that file back.

The page loads nothing: images are data URIs, and the Content-Security-Policy allows only those
images, inline styles and the one inline script whose hash it names.
"""

import base64
import hashlib
import io
from datetime import datetime, timezone
from html import escape
from pathlib import Path

from .errors import VixlError, require
from .image_diff import RASTER, VISUAL, load_visual
from .model import Limits

MAX_ITEMS = 200
MAX_ISSUES = 30
IMAGE_BYTES = 450_000
DECISION_SCRIPT = """
document.getElementById('download').addEventListener('click', function () {
  var items = [];
  document.querySelectorAll('article[data-path]').forEach(function (card) {
    var chosen = card.querySelector('input[type=radio]:checked');
    var note = card.querySelector('textarea');
    items.push({id: card.id, path: card.dataset.path, label: card.dataset.label,
                decision: chosen ? chosen.value : 'pending', note: note ? note.value : ''});
  });
  var body = document.body.dataset;
  var data = {proof: body.title, page: body.file, generated: body.generated,
              decided: new Date().toISOString(), items: items};
  var link = document.createElement('a');
  link.href = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], {type: 'application/json'}));
  link.download = body.decisions;
  document.body.appendChild(link);
  link.click();
  link.remove();
});
""".strip()


def _items(items):
    require(isinstance(items, list) and 0 < len(items) <= MAX_ITEMS, f"Give 1-{MAX_ITEMS} items", field="items")
    normalized = []
    for index, item in enumerate(items):
        if isinstance(item, str):
            item = {"path": item}
        require(isinstance(item, dict) and isinstance(item.get("path"), str),
                f"items[{index}] must be a path or {{path, label?, before?, note?}}", field=f"items[{index}]")
        unknown = sorted(set(item) - {"path", "label", "before", "note"})
        require(not unknown, f"items[{index}]: unknown field(s) {unknown}; use path, label, before, note",
                field=f"items[{index}]")
        normalized.append(item)
    return normalized


def _data_uri(image, max_size):
    from PIL import Image

    from .proxy import encode_png

    image = image.convert("RGBA")
    image.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
    return "data:image/png;base64," + base64.b64encode(encode_png(image, IMAGE_BYTES)).decode("ascii")


def _pdf_metadata(data):
    spaces = [name for name in ("DeviceCMYK", "DeviceRGB", "DeviceGray", "ICCBased") if f"/{name}".encode() in data]
    meta = {"color": ", ".join(spaces) or "unknown"}
    try:
        import pypdfium2

        document = pypdfium2.PdfDocument(data)
        try:
            width, height = document[0].get_size()
            meta.update(pages=len(document), page_size=f"{width:g} × {height:g} pt")
        finally:
            document.close()
    except Exception:  # metadata stays best-effort without pypdfium2 or for odd PDFs
        pass
    return meta


def describe(path, limits, *, check=True, max_size=1200):
    """Thumbnail, metadata and (for documents) check findings of one file."""
    from PIL import Image

    suffix = path.suffix.lower()
    data = path.read_bytes() if suffix != ".vixl" else None
    meta = {"format": suffix.lstrip(".").upper() or "file", "bytes": path.stat().st_size}
    record = {"meta": meta}
    if suffix == ".vixl":
        from .project import Project

        project = Project.load(path, limits=limits)
        canvas = project.state["canvas"]
        meta.update(size=f"{canvas['width']} × {canvas['height']} px", layers=len(project.state["layers"]))
        if canvas.get("dpi"):
            meta["dpi"] = canvas["dpi"]
        if project.state.get("pages"):
            meta["pages"] = len(project.state["pages"])
        meta["color"] = "RGB document" + (f", {canvas['background']} background" if canvas.get("background") else "")
        from .proxy import render_preview

        record["image"] = _data_uri(render_preview(project, max_size, max_size), max_size)
        if check:
            report = project.check()
            record["check"] = {
                "passed": report.get("passed", True),
                "errors": report.get("errors", 0), "warnings": report.get("warnings", 0),
                "issues": [{key: issue.get(key) for key in ("severity", "action", "check", "message", "layer")
                            if issue.get(key) is not None} for issue in report.get("issues", [])[:MAX_ISSUES]],
                **({"omitted": len(report["issues"]) - MAX_ISSUES} if len(report.get("issues", [])) > MAX_ISSUES else {}),
            }
        return record
    if suffix == ".svg":
        text = data.decode("utf-8", "replace")
        import re

        box = re.search(r'viewBox="([^"]+)"', text)
        if box:
            meta["view_box"] = box.group(1)
        meta["color"] = "RGB (vector)"
        image = load_visual(path, limits, data=data)
        meta["size"] = f"{image.width} × {image.height} px"
        record["image"] = _data_uri(image, max_size)
        return record
    if suffix == ".pdf":
        meta.update(_pdf_metadata(data))
        try:
            record["image"] = _data_uri(load_visual(path, limits, data=data), max_size)
        except VixlError as exc:
            record["note"] = exc.args[0]
        return record
    if suffix in RASTER:
        with Image.open(io.BytesIO(data)) as source:
            meta.update(size=f"{source.width} × {source.height} px", color=source.mode)
            if source.info.get("dpi"):
                meta["dpi"] = round(float(source.info["dpi"][0]))
            if source.info.get("icc_profile"):
                meta["icc_profile"] = True
            if getattr(source, "n_frames", 1) > 1:
                meta["frames"] = source.n_frames
        record["image"] = _data_uri(load_visual(path, limits, data=data), max_size)
        return record
    record["note"] = "No preview for this format"
    return record


def _before_after(path, before, limits, resolve, max_size):
    from .image_diff import diff_images

    require(isinstance(before, str) and before, "before is a file or a revision", field="before")
    candidate = resolve(before) if Path(before).suffix.lower() in VISUAL else None
    if candidate is not None:
        require(candidate.is_file(), f"before {before!r} is not a file", "not_found", field="before")
        left, label = load_visual(candidate, limits), before
    else:
        require(path.suffix.lower() == ".vixl", f"before {before!r} is not a file; a revision (head~1, a checkpoint) "
                "needs a .vixl item", field="before")
        from .project import Project

        project = Project.load(path, limits=limits)
        left, label = project.at(before).render().convert("RGBA"), f"revision {project.resolve_ref(before)}"
    right = load_visual(path, limits)
    image, stats = diff_images(left, right, mode="diff")
    return {"before": _data_uri(left, max_size), "diff": _data_uri(image, max_size), "label": label,
            "changed_fraction": stats["changed_fraction"], "changed_region": stats["changed_region"]}


CSS = """
:root{color-scheme:light dark;--bg:#f4f4f6;--card:#fff;--ink:#1d1d22;--muted:#5f5f6b;--line:#d9d9e0;--ok:#1b7f3b;
--bad:#b3261e;--warn:#8a5a00}
@media (prefers-color-scheme:dark){:root{--bg:#141418;--card:#1f1f25;--ink:#ececf1;--muted:#a3a3b0;--line:#34343d;
--ok:#5bd17f;--bad:#ff8a80;--warn:#f5c35b}}
*{box-sizing:border-box}body{margin:0;font:15px/1.45 system-ui,-apple-system,"Segoe UI",sans-serif;background:var(--bg);
color:var(--ink)}header,main,footer{max-width:1240px;margin:0 auto;padding:16px}h1{margin:8px 0 4px;font-size:1.6rem}
.sub{color:var(--muted);margin:0}main{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:16px}
article{background:var(--card);border:1px solid var(--line);border-radius:10px;overflow:hidden;display:flex;
flex-direction:column}.thumb{display:grid;place-items:center;height:220px;padding:8px;
background:repeating-conic-gradient(#0000000d 0 25%,#0000 0 50%) 0 0/16px 16px}
.thumb img{max-width:100%;max-height:100%;object-fit:contain}.body{padding:12px;display:grid;gap:8px}
h2{margin:0;font-size:1rem;overflow-wrap:anywhere}dl{display:grid;grid-template-columns:auto 1fr;gap:2px 10px;
margin:0;font-size:.85rem}dt{color:var(--muted)}dd{margin:0;overflow-wrap:anywhere}
.badge{display:inline-block;font-size:.78rem;font-weight:600;padding:1px 8px;border-radius:99px;border:1px solid}
.pass{color:var(--ok)}.fail{color:var(--bad)}.warnc{color:var(--warn)}ul{margin:0;padding-left:18px;font-size:.84rem}
.compare{display:grid;grid-template-columns:1fr 1fr;gap:6px}.compare img{width:100%}.compare figcaption{font-size:.75rem;
color:var(--muted)}figure{margin:0}.zoom{display:none;position:fixed;inset:0;background:#000d;z-index:9;
padding:24px;place-items:center}.zoom:target{display:grid}.zoom img{max-width:100%;max-height:calc(100vh - 80px);
object-fit:contain;background:#fff}.zoom a{color:#fff;position:absolute;top:12px;right:20px;font-size:1.1rem}
fieldset{border:1px solid var(--line);border-radius:8px;margin:0;padding:6px 10px;display:flex;gap:12px;flex-wrap:wrap}
textarea{width:100%;min-height:48px;font:inherit;background:var(--bg);color:var(--ink);border:1px solid var(--line);
border-radius:6px}button{font:inherit;padding:8px 16px;border-radius:8px;border:1px solid var(--line);cursor:pointer}
.note{color:var(--muted);font-size:.85rem}
""".strip()


def _card(index, item, record, decisions):
    ident = f"item-{index + 1}"
    label = item.get("label") or Path(item["path"]).name
    meta = record["meta"]
    rows = "".join(f"<dt>{escape(str(key).replace('_', ' '))}</dt><dd>{escape(str(value))}</dd>"
                   for key, value in meta.items())
    parts = [f'<article id="{ident}" data-path="{escape(item["path"])}" data-label="{escape(label)}">']
    if record.get("image"):
        parts.append(f'<a class="thumb" href="#zoom-{ident}" title="Enlarge"><img src="{record["image"]}" '
                     f'alt="{escape(label)}"></a>')
    else:
        parts.append(f'<div class="thumb"><span class="note">{escape(record.get("note", "No preview"))}</span></div>')
    parts.append(f'<div class="body"><h2>{escape(label)}</h2><div class="note">{escape(item["path"])}</div>')
    if item.get("note"):
        parts.append(f"<p>{escape(item['note'])}</p>")
    parts.append(f"<dl>{rows}</dl>")
    report = record.get("check")
    if report is not None:
        state = "pass" if report["passed"] and not report["warnings"] else "warnc" if report["passed"] else "fail"
        text = "check passed" if state == "pass" else f"{report['errors']} error(s), {report['warnings']} warning(s)"
        parts.append(f'<div><span class="badge {state}">{escape(text)}</span></div>')
        if report["issues"]:
            lines = "".join(
                f"<li><b>{escape(issue.get('severity', ''))}</b> {escape(issue.get('check', ''))}: "
                f"{escape(issue.get('message', ''))}{' (' + escape(issue['layer']) + ')' if issue.get('layer') else ''}</li>"
                for issue in report["issues"])
            more = f"<li>… {report['omitted']} more</li>" if report.get("omitted") else ""
            parts.append(f"<ul>{lines}{more}</ul>")
    compare = record.get("compare")
    if compare:
        region = compare["changed_region"]
        parts.append(
            f'<div class="compare"><figure><img src="{compare["before"]}" alt="before"><figcaption>before: '
            f'{escape(compare["label"])}</figcaption></figure><figure><img src="{compare["diff"]}" alt="changes">'
            f'<figcaption>{compare["changed_fraction"]:.2%} changed'
            f'{" in " + escape(str(region)) if region else ""}</figcaption></figure></div>')
    if decisions:
        parts.append(
            f'<fieldset><legend>Decision</legend>'
            f'<label><input type="radio" name="{ident}" value="approved"> Approve</label>'
            f'<label><input type="radio" name="{ident}" value="rejected"> Reject</label></fieldset>'
            f'<textarea aria-label="Note for {escape(label)}" placeholder="Note (optional)"></textarea>')
    parts.append("</div></article>")
    if record.get("image"):
        parts.append(f'<div class="zoom" id="zoom-{ident}"><a href="#{ident}">Close ✕</a>'
                     f'<img src="{record["image"]}" alt="{escape(label)}, enlarged"></div>')
    return "".join(parts)


def render_page(items, records, *, title, file_name, decisions):
    generated = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    script_hash = base64.b64encode(hashlib.sha256(DECISION_SCRIPT.encode()).digest()).decode()
    policy = ("default-src 'none'; img-src data:; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'"
              + (f"; script-src 'sha256-{script_hash}'" if decisions else ""))
    failed = sum(1 for record in records if record.get("check") and not record["check"]["passed"])
    checked = sum(1 for record in records if record.get("check") is not None)
    summary = f"{len(items)} item(s)" + (f" · {checked} checked, {failed} with errors" if checked else "")
    stem = Path(file_name).stem
    cards = "".join(_card(index, item, record, decisions) for index, (item, record) in enumerate(zip(items, records)))
    footer = ""
    if decisions:
        footer = (f'<footer><button id="download" type="button">Download decisions (JSON)</button> '
                  f'<span class="note">Saves {escape(stem)}-decisions.json; send that file back. The page itself '
                  f'cannot save anything.</span></footer><script>{DECISION_SCRIPT}</script>')
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="{policy}">
<meta name="generator" content="Vixl proof page"><title>{escape(title)}</title><style>{CSS}</style></head>
<body data-title="{escape(title)}" data-file="{escape(file_name)}" data-generated="{generated}" data-decisions="{escape(stem)}-decisions.json">
<header><h1>{escape(title)}</h1><p class="sub">{escape(summary)} · generated {generated} · click a thumbnail to enlarge</p></header>
<main>{cards}</main>{footer}</body></html>""".encode("utf-8")


def proof_page(items, output, *, resolve=None, title=None, check=True, decisions=False, max_size=1200,
               overwrite=False, limits=None):
    """Write the proof page for ``items`` (paths, or {path, label, before, note}) to ``output`` (.html).
    ``resolve`` maps an item path to a file (the workspace resolver for services; default: the path as
    given). ``before`` is another file, or a revision of a .vixl item (previous, head~1, a checkpoint)."""
    resolve = resolve or (lambda value: Path(value))
    limits = limits or Limits()
    items = _items(items)
    destination = Path(output) if isinstance(output, Path) else resolve(output)
    require(destination.suffix.lower() in (".html", ".htm"), "The proof page must be an .html file", field="output")
    require(overwrite or not destination.exists(), f"{output} already exists; set overwrite=true", field="output")
    require(isinstance(max_size, int) and 128 <= max_size <= 2400, "max_size must be 128-2400 pixels", field="max_size")
    records = []
    for index, item in enumerate(items):
        from . import calls

        calls.check_cancelled()
        path = resolve(item["path"])
        require(path.is_file(), f"items[{index}]: no file at {item['path']}", "not_found", field=f"items[{index}].path")
        try:
            record = describe(path, limits, check=check, max_size=max_size)
            if item.get("before") is not None:
                record["compare"] = _before_after(path, item["before"], limits, resolve, max_size)
        except VixlError as exc:
            raise VixlError(exc.code, f"items[{index}] ({item['path']}): {exc}", **exc.details) from exc
        records.append(record)
        calls.progress(index + 1, len(items), item["path"])
    page = render_page(items, records, title=title or "Proof", file_name=destination.name, decisions=decisions)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("wb" if overwrite else "xb") as stream:
        stream.write(page)
    return {
        "output": str(destination), "items": len(items), "bytes": len(page), "decisions": decisions,
        "checked": [{"path": item["path"], **{k: record["check"][k] for k in ("passed", "errors", "warnings")}}
                    for item, record in zip(items, records) if record.get("check") is not None],
        **({"decision_file": f"{destination.stem}-decisions.json"} if decisions else {}),
    }

