"""Deliverable packages (#573): the outputs of a campaign run or a set of exported files, in one zip with a manifest.

``package`` takes the finished outputs of a campaign run (``production``: its ``production.json``) or exported files
(``files``: paths and globs), names them from a template (a name two files would share is refused before anything is
checked or written), drops byte-identical copies, and writes one zip holding the files, ``manifest.json``, ``SHA256SUMS``,
the check report (``report/check-report.json`` and ``.md``, rendered by ``workspace_checks.render``) and a proof page.
Outputs the run held for review are listed under ``held`` and left out; so are outputs a reviewer rejected on the
proof page.

Per file the manifest records the source document and its revision (the SHA-256 of the saved ``.vixl``), the export
settings, the check outcome, the SHA-256, the dimensions, the colour space and the stream metadata read back from the
encoded file. Per package it records the Vixl version, the validation coverage, the visual-review status and, when a
render lockfile is given, the reproduction summary of #512. A run record from the pipeline runner becomes one more
entry of ``INPUTS``: a collector returns the same candidates, held entries and input description for each kind.

The zip is staged and published atomically, and never replaces an existing file unless ``overwrite`` is true. Its
entries have fixed timestamps and a fixed order, so the same inputs give the same archive members.
"""

from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import zipfile
import zlib

from ...assets import open_image
from ...errors import VixlError, require
from ...production import blocking_rules, file_digest, publish_file, read_json

DEFAULT_NAME = "{brand}_{doc}_{artboard}_{w}x{h}.{ext}"
TOKENS = ("brand", "doc", "artboard", "w", "h", "size", "ext", "format", "locale", "row", "id")
LAYOUTS = ("flat", "by-format", "by-artboard")
MAX_FILES = 1000
MAX_PROOF = 200
RESERVED = ("manifest.json", "sha256sums", "proof.html", "report/check-report.json", "report/check-report.md")
STORED = (".png", ".jpg", ".jpeg", ".webp", ".avif", ".gif", ".mp4", ".webm", ".zip", ".pptx")
SKIP_DIRS = (".vixl-groups", ".vixl-checks", ".vixl-ci", ".vixl-branches", ".vixl-cache", ".vixl-runs", ".git")
DECISIONS = ("approved", "rejected", "pending")
RASTER = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".tif", ".tiff", ".avif", ".bmp", ".ico")
STATE_OF_STATUS = {"passed": "validated", "needs_review": "needs_review", "failed": "validation_failed",
                   "error": "execution_failed"}
FIELDS = {
    "output": {"type": "string", "description": "The package to write: a new .zip path in the workspace."},
    "production": {"type": "string", "description": "A campaign run's production.json. Its completed outputs are "
                   "packaged; the variants it held for review are listed under held and left out."},
    "files": {"type": "array", "minItems": 1, "maxItems": MAX_FILES, "items": {"type": ["string", "object"]},
              "description": "Exported files to package: workspace paths or globs, or {path, source} to name the "
                             "document a file was exported from. Give production or files."},
    "source": {"type": "string", "description": "The .vixl document the outputs were made from: its revision digest "
               "goes into the manifest, and with files its checks into the report."},
    "name": {"type": "string", "default": DEFAULT_NAME, "description": "File name template: {brand} {doc} {artboard} "
             "{w} {h} {size} {ext} {locale} {row} {id}. A name two files would share is refused with the list."},
    "brand": {"type": "string", "description": "Value of {brand} (default: the name in the workspace brand.json)."},
    "locale": {"type": "string", "description": "Value of {locale} for outputs whose row has no locale value."},
    "layout": {"type": "string", "enum": list(LAYOUTS), "default": "flat",
               "description": "flat puts every file at the top; by-format and by-artboard use a folder each."},
    "check": {"type": "boolean", "default": True, "description": "Include the check report: the checks of the source "
              "documents of files, or what a production run recorded for each output."},
    "proof": {"type": "boolean", "default": True, "description": "Include an offline proof page (proof.html)."},
    "lock": {"type": ["string", "object"], "description": "A render lockfile (reproduce write_lock) of the source "
             "document, or {source: lockfile} for several: its reproduction check goes into the manifest."},
    "decisions": {"type": ["string", "object"], "description": "The proof page's downloaded decisions JSON (or its "
                  "path): approved files are marked, rejected ones held, the rest pending."},
    "export_settings": {"type": "object", "description": "Export settings to record per format, "
                        "e.g. {\"png\": {\"scale\": 2}}."},
    "dry_run": {"type": "boolean", "default": False, "description": "Plan the names, de-duplication and held list "
                "without running checks or writing the package."},
    "overwrite": {"type": "boolean", "default": False, "description": "Replace an existing package."},
}
SUMMARY = ("Package a campaign run's outputs (production.json) or exported files into one zip: names from a template, "
           "duplicates dropped by hash, a manifest with source revision, export settings, check status, SHA-256, "
           "dimensions, colour and stream metadata, the check report and proof page, held outputs listed and left "
           "out. Refuses name collisions and existing packages.")


# Inspecting a delivered file --------------------------------------------------------------------

def _ffprobe(path):
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return None
    command = [ffprobe, "-v", "error", "-show_entries", "stream=codec_type,codec_name,width,height,r_frame_rate,"
               "nb_frames,duration,pix_fmt,channels,sample_rate:format=format_name,duration", "-of", "json", str(path)]
    try:
        done = subprocess.run(command, capture_output=True, timeout=120)
        return json.loads(done.stdout or b"{}") if done.returncode == 0 else None
    except (OSError, subprocess.SubprocessError, ValueError):
        return None


def _seconds(*values):
    for value in values:
        try:
            seconds = float(value)
        except (TypeError, ValueError):
            continue
        if seconds >= 0:
            return seconds
    return None


def _rate(value):
    try:
        top, _, bottom = str(value).partition("/")
        return round(float(top) / float(bottom or 1), 3)
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def _whole(value):
    return int(value) if str(value).isdigit() else None


def _video_facts(path):
    info = _ffprobe(path)
    if info is None:
        return {}
    streams = info.get("streams") or []
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
    container = info.get("format") or {}
    facts = {"stream": {"container": container.get("format_name")}}
    if video:
        seconds = _seconds(video.get("duration"), container.get("duration"))
        facts["width"], facts["height"] = video.get("width"), video.get("height")
        facts["color"] = {"space": "RGB" if "rgb" in str(video.get("pix_fmt")) else "YUV", "pix_fmt": video.get("pix_fmt")}
        facts["stream"]["video"] = {"codec": video.get("codec_name"), "fps": _rate(video.get("r_frame_rate")),
                                    "frames": _whole(video.get("nb_frames")),
                                    "duration_ms": None if seconds is None else round(seconds * 1000)}
    if audio:
        facts["stream"]["audio"] = {"codec": audio.get("codec_name"), "channels": audio.get("channels"),
                                    "sample_rate": _whole(audio.get("sample_rate"))}
    return facts


def _pdf_spaces(data):
    """The colour spaces a PDF names, plus those its (text) content streams paint with: rg/RG is RGB, k/K CMYK and
    g/G gray. Vixl's own vector PDFs set colours by operator, so the names alone would show nothing."""
    spaces = [name for name in ("DeviceCMYK", "DeviceRGB", "DeviceGray", "ICCBased") if f"/{name}".encode() in data]
    for match in list(re.finditer(rb"stream\r?\n(.*?)\r?\nendstream", data, re.S))[:200]:
        try:
            text = zlib.decompressobj().decompress(match.group(1), 2_000_000)
        except zlib.error:
            text = match.group(1)[:2_000_000]
        head = text[:300]
        if not head or sum(32 <= byte < 127 or byte in (9, 10, 13) for byte in head) < 0.95 * len(head):
            continue
        for operator, name in ((rb"rg|RG", "DeviceRGB"), (rb"k|K", "DeviceCMYK"), (rb"g|G", "DeviceGray")):
            if name not in spaces and re.search(rb"(?:^|\s)(?:" + operator + rb")(?:\s|$)", text):
                spaces.append(name)
    return spaces


def _pdf_facts(path):
    data = path.read_bytes()
    spaces = _pdf_spaces(data)
    facts = {"color": {"space": "CMYK" if "DeviceCMYK" in spaces else "RGB" if set(spaces) & {"DeviceRGB", "ICCBased"}
                       else "Gray" if spaces else "unknown", "color_spaces": spaces}}
    try:
        import pypdfium2

        document = pypdfium2.PdfDocument(data)
        try:
            width, height = document[0].get_size()
            facts.update(pages=len(document), width=round(width, 2), height=round(height, 2), unit="pt")
        finally:
            document.close()
    except Exception:  # noqa: BLE001 - page facts stay best-effort without pypdfium2 or for a PDF it cannot open
        pass
    return facts


def _raster_facts(path):
    with open_image(path) as image:
        facts = {"width": image.width, "height": image.height}
        mode = image.mode
        facts["color"] = {"space": "CMYK" if mode == "CMYK" else "Gray" if mode in ("L", "LA", "1") else "RGB",
                          "mode": mode, "alpha": "A" in mode or "transparency" in image.info,
                          "icc_profile": bool(image.info.get("icc_profile"))}
        if image.info.get("dpi"):
            facts["dpi"] = round(float(image.info["dpi"][0]))
        frames = getattr(image, "n_frames", 1)
        if frames > 1:
            milliseconds = 0
            for index in range(frames):
                image.seek(index)
                milliseconds += int(image.info.get("duration") or 0)
            facts["stream"] = {"container": str(image.format).lower(), "frames": frames, "loop": image.info.get("loop"),
                               "duration_ms": milliseconds}
    return facts


def inspect_file(path):
    """What the encoded file itself says: size, dimensions, colour space, frames or streams. It reads headers rather
    than pixels, and video through ffprobe. A file that cannot be read keeps its size and an ``unreadable`` note."""
    path = Path(path)
    suffix = path.suffix.lower()
    facts = {"format": suffix.lstrip(".") or "file", "bytes": path.stat().st_size}
    try:
        if suffix in RASTER:
            facts.update(_raster_facts(path))
        elif suffix in (".mp4", ".webm", ".mov"):
            facts.update(_video_facts(path))
        elif suffix == ".pdf":
            facts.update(_pdf_facts(path))
        elif suffix == ".svg":
            head = path.read_bytes()[:4096].decode("utf-8", "replace")
            box = re.search(r'viewBox="\s*[-\d.]+[\s,]+[-\d.]+[\s,]+([\d.]+)[\s,]+([\d.]+)', head)
            size = [re.search(rf'<svg[^>]*\s{side}="([\d.]+)(?:px)?"', head) for side in ("width", "height")]
            if all(size):
                facts.update(width=float(size[0][1]), height=float(size[1][1]))
            elif box:
                facts.update(width=float(box[1]), height=float(box[2]))
            facts["color"] = {"space": "RGB", "vector": True}
        elif suffix == ".psd":
            header = path.read_bytes()[:26]
            if header[:4] == b"8BPS":
                modes = {1: "Gray", 3: "RGB", 4: "CMYK"}
                facts.update(height=int.from_bytes(header[14:18], "big"), width=int.from_bytes(header[18:22], "big"),
                             color={"space": modes.get(int.from_bytes(header[24:26], "big"), "unknown")})
        elif suffix == ".pptx":
            with zipfile.ZipFile(path) as archive:
                facts["pages"] = sum(1 for name in archive.namelist() if re.fullmatch(r"ppt/slides/slide\d+\.xml", name))
    except Exception as exc:  # noqa: BLE001 - decoders raise many kinds of error for damaged files; the package notes it
        facts["unreadable"] = f"{type(exc).__name__}: {str(exc)[:120]}"
    return facts


# Collecting inputs ------------------------------------------------------------------------------

def _candidate(path, workspace, **extra):
    return {"path": path, "workspace": workspace, "id": None, "row": None, "artboard": None, "values": {}, "source": None,
            "outcome": None, "checks": None, "export_check": None, "sha256": None, **extra}


def _reason(result):
    """Why a variant that has no output was held, and the rules that held it."""
    status = result.get("status")
    if status == "needs_review":
        rules = list(dict.fromkeys(blocking_rules(result.get("checks") or {})))
        reasons = (result.get("outcome") or {}).get("review_reasons") or []
        detail = f": {', '.join(rules[:5])}" if rules else f": {reasons[0]}" if reasons else ""
        return "held for review" + detail, rules
    if status == "failed":
        error = result.get("error") or {}
        return f"the variant failed: {error.get('message') or error.get('error') or 'no detail recorded'}", []
    return f"the variant was {status or 'not completed'}", []


def _production(session, request):
    """Candidates, held entries and a description of the input for a campaign run's production.json."""
    path = session.resolve(request["production"])
    require(path.is_file() and path.suffix == ".json", f"{request['production']} is not a production.json file",
            "not_found", field="production")
    report = read_json(path)
    require(isinstance(report, dict) and report.get("version") == 1 and isinstance(report.get("results"), list),
            "production is a campaign run's production.json", field="production")
    require(report.get("status") != "running", "The campaign run is still marked running; let it finish or run it "
            "again to resume, then package", "invalid_request", field="production")
    candidates, held = [], []
    for result in sorted((r for r in report["results"] if isinstance(r, dict)), key=lambda r: str(r.get("id"))):
        item = {"id": result.get("id"), "row": result.get("row"), "artboard": result.get("artboard"),
                "status": result.get("status")}
        if result.get("status") not in ("completed", "reused"):
            reason, rules = _reason(result)
            held.append({**item, "reason": reason, **({"rules": rules} if rules else {})})
            continue
        name = str(result.get("output") or "")
        file = path.parent / name
        if not name or Path(name).name != name or not file.is_file():
            held.append({**item, "reason": f"the output file {name or '(none)'} is missing"})
        elif result.get("sha256") and file_digest(file) != result["sha256"]:
            held.append({**item, "reason": f"{name} changed after the run: its checksum differs from production.json"})
        else:
            candidates.append(_candidate(
                file, session.relative(file), id=result.get("id"), row=result.get("row"), artboard=result.get("artboard"),
                values=result.get("values") or {}, source=request.get("source"), outcome=result.get("outcome"),
                checks=result.get("checks"), export_check=result.get("export_check"), sha256=result.get("sha256")))
    info = {"kind": "production", "path": request["production"], "status": report.get("status"),
            **{key: report[key] for key in ("quality", "profile", "count") if key in report}}
    return candidates, held, info


def _expand(session, pattern):
    pattern = str(pattern).strip().replace("\\", "/")
    require(pattern and not Path(pattern).is_absolute() and ".." not in Path(pattern).parts,
            "files are workspace-relative paths or globs", "forbidden", field="files")
    if not any(ch in pattern for ch in "*?["):
        path = session.resolve(pattern)
        require(path.is_file(), f"No file at {pattern}", "not_found", field="files")
        return [path]
    found = []
    for path in sorted(session.workspace.glob(pattern)):
        relative = path.relative_to(session.workspace)
        if path.is_file() and not any(part in SKIP_DIRS for part in relative.parts[:-1]) \
                and path.resolve().is_relative_to(session.workspace):
            found.append(path.resolve())
    return found


def _files(session, request):
    candidates, seen = [], set()
    for index, entry in enumerate(request["files"]):
        if isinstance(entry, str):
            entry = {"path": entry}
        require(isinstance(entry, dict) and isinstance(entry.get("path"), str) and set(entry) <= {"path", "source"},
                f"files[{index}] is a path or glob, or {{path, source}}", field=f"files[{index}]")
        matches = _expand(session, entry["path"])
        require(matches, f"files[{index}]: nothing matched {entry['path']}", "not_found", field=f"files[{index}]")
        for path in matches:
            if path not in seen:
                seen.add(path)
                candidates.append(_candidate(path, session.relative(path),
                                             source=entry.get("source", request.get("source"))))
    patterns = [entry if isinstance(entry, str) else entry["path"] for entry in request["files"]]
    return candidates, [], {"kind": "files", "patterns": patterns}


# A run record from the pipeline runner (`.vixl-runs/<id>/run.json`) is one more collector with this signature.
INPUTS = {"production": _production, "files": _files}


def collect(session, request):
    given = [key for key in INPUTS if request.get(key) is not None]
    require(len(given) == 1, f"Give exactly one input: {' or '.join(INPUTS)}", field="production",
            allowed=list(INPUTS))
    return INPUTS[given[0]](session, request)


# Names ------------------------------------------------------------------------------------------

def slug(value, limit=60):
    return re.sub(r"[^A-Za-z0-9.]+", "-", str(value or "")).strip("-.")[:limit]


def fill(template, tokens):
    """The file name for ``template``. A token with no value disappears with one separator next to it."""
    template = template.replace("{w}x{h}", "{size}")
    empty = []

    def value(match):
        text = tokens.get(match.group(1)) or ""
        if not text:
            empty.append(match.group(1))
        return text

    name = re.sub(r"\{(\w+)\}", value, template)
    if empty:
        stem, dot, suffix = name.rpartition(".")
        if not dot:
            stem, suffix = name, ""
        name = re.sub(r"([_-])[_-]+", r"\1", stem).strip("_-") + (dot + suffix if dot else "")
    return name


def check_template(template):
    require(isinstance(template, str) and 0 < len(template) <= 200 and not re.search(r"[/\\\0]", template)
            and not template.startswith("."), "name is a file name template without folders", field="name")
    unknown = sorted(set(re.findall(r"\{(\w*)\}", template)) - set(TOKENS))
    require(not unknown, f"name uses unknown field(s) {unknown}; use {', '.join('{' + t + '}' for t in TOKENS)}",
            field="name", allowed=list(TOKENS))
    require(not re.search(r"[{}]", re.sub(r"\{\w+\}", "", template)), "name has an unmatched brace", field="name")
    return template


def _brand(session, request):
    if request.get("brand") is not None:
        return str(request["brand"])
    from ...brand import load_raw

    try:
        return str(load_raw(session.workspace).get("name") or "")
    except VixlError:
        return ""


def name_files(session, request, files):
    """``{id(file): package path}``, or a refusal that lists every name two files would share."""
    template = check_template(request.get("name", DEFAULT_NAME))
    layout = request.get("layout", "flat")
    brand = slug(_brand(session, request))
    names, owners = {}, {}
    for item in files:
        facts, source, values = item["facts"], item["source"], item["values"]
        width, height = facts.get("width"), facts.get("height")
        known = width is not None and height is not None and facts.get("unit") is None
        ext = "jpg" if facts["format"] == "jpeg" else facts["format"]
        tokens = {"brand": brand, "doc": slug(Path(source).stem if source else item["path"].stem),
                  "artboard": slug(item["artboard"]), "w": str(round(width)) if known else "",
                  "h": str(round(height)) if known else "", "size": f"{round(width)}x{round(height)}" if known else "",
                  "ext": ext, "format": ext,
                  "locale": slug(values.get("locale") or values.get("lang") or request.get("locale")),
                  "row": str(item["row"]) if item["row"] is not None else "", "id": slug(item["id"])}
        name = fill(template, tokens)
        if not name or name.startswith("."):
            name = item["path"].name
        if layout == "by-format":
            name = f"{slug(ext)}/{name}"
        elif layout == "by-artboard":
            name = f"{tokens['artboard'] or 'default'}/{name}"
        names[id(item)] = name
        owners.setdefault(name.lower(), []).append(item["workspace"])
    clashes = sorted({(name, tuple(owners[name.lower()])) for name in names.values()
                      if len(owners[name.lower()]) > 1 or name.lower() in RESERVED})
    if clashes:
        listed = [{"name": name, "sources": list(sources)} for name, sources in clashes]
        shown = "; ".join(f"{c['name']} <- {', '.join(c['sources'][:3])}" for c in listed[:5])
        longer = template.replace(".{ext}", "_{id}.{ext}") if ".{ext}" in template else template + "_{id}"
        raise VixlError("output_collision", f"{len(listed)} package file name(s) would be used twice or are reserved: "
                        f"{shown}. Add {{id}}, {{row}} or {{artboard}} to name, or choose a layout.", field="name",
                        collisions=listed[:50], suggestions=[f'name: "{longer}"', "layout: by-format"])
    return names


# Checks and review ------------------------------------------------------------------------------

def _production_check(item):
    outcome = item["outcome"] or {}
    check = {"source": "production", "state": outcome.get("state", "unvalidated")}
    for key in ("validation", "review", "validated_by", "review_reasons"):
        if outcome.get(key):
            check[key] = outcome[key]
    return check


def _document_checks(session, files):
    """The check-all report over the files' source documents, or None when no file names one."""
    sources = sorted({item["source"] for item in files if item["source"]})
    if not sources:
        return None
    from .workspace_checks import run

    return run(session, {"documents": sources, "history": False})


def _production_report(files, held, info):
    """A check-all shaped result of what the run recorded for each output, so that it renders like any check report."""
    from ... import __version__

    documents = []
    for item in files:
        outcome = item["outcome"] or {}
        design = (item["checks"] or {}).get("design") or {}
        documents.append({"path": item["name"], "status": "needs_review" if outcome.get("state") == "needs_review"
                          else "passed", "errors": design.get("errors", 0), "warnings": design.get("warnings", 0),
                          "fix": 0, "failing": [], "findings": [], "finding_ids": [], "outcome": outcome.get("state")})
    for entry in held:
        documents.append({"path": f"{entry.get('id') or entry.get('path') or '?'} (held)",
                          "status": "failed" if entry["status"] in ("failed", "rejected", "error") else "needs_review",
                          "errors": 0, "warnings": 0, "fix": 0, "failing": [entry["reason"]], "findings": [],
                          "finding_ids": []})
    totals = Counter(entry["status"] for entry in documents)
    failing = sum(1 for entry in documents if entry["failing"])
    time = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    return {"version": 1, "vixl_version": __version__, "time": time, "fail_on": info.get("profile") or "recorded",
            "count": len(documents), "source": "production",
            "totals": {"passed": totals["passed"], "failed": totals["failed"], "needs_review": totals["needs_review"],
                       "error": 0, "failing": failing, "errors": sum(e["errors"] for e in documents),
                       "warnings": sum(e["warnings"] for e in documents), "fix": 0, "by_check": {}},
            "documents": documents, "passed": not failing}


def _decisions(session, request):
    value = request.get("decisions")
    if value is None:
        return None
    if isinstance(value, str):
        value = read_json(session.resolve(value))
    require(isinstance(value, dict) and isinstance(value.get("items"), list),
            "decisions is a proof page's downloaded decisions JSON (or its path)", field="decisions")
    found = {}
    for item in value["items"]:
        require(isinstance(item, dict) and isinstance(item.get("path"), str), "decisions items need a path",
                field="decisions")
        decision = item.get("decision", "pending")
        require(decision in DECISIONS, f"a decision is one of {', '.join(DECISIONS)}", field="decisions")
        found[item["path"]] = {"decision": decision, "note": item.get("note") or None}
    return found


def _review(decisions, item):
    """``(review, note)`` of a file: matched by package name, workspace path or file name."""
    if decisions is None:
        return "not_reviewed", None
    for key in (item["name"], item["workspace"], Path(item["workspace"]).name):
        if key in decisions:
            return decisions[key]["decision"], decisions[key]["note"]
    return "pending", None


def _reproduction(session, request, sources):
    lock = request.get("lock")
    if lock is None:
        return None
    from .reproduce import read_lock, reproduce

    if isinstance(lock, str):
        require(len(sources) == 1, "lock names one lockfile, so give a single source document (or lock as "
                "{source: lockfile})", field="lock")
        lock = {sources[0]: lock}
    require(isinstance(lock, dict) and lock and all(isinstance(path, str) for path in lock.values()),
            "lock is a lockfile path or {source: lockfile}", field="lock")
    found = {}
    for source, path in {session.relative(session.resolve(name)): path for name, path in lock.items()}.items():
        locked = read_lock(session.resolve(path))
        with session.project(document=source) as project:
            found[source] = {"lockfile": path, **reproduce(
                project, locked=locked, verify_exports=bool(locked.get("exports")) and locked.get("version", 1) >= 2,
                limits=session.limits, resolve=session.resolve, report=True)}
    return found


# Building ---------------------------------------------------------------------------------------

def _entry(item, revisions, settings, check):
    facts = item["facts"]
    entry = {
        "name": item["name"], "sha256": item["sha256"], "bytes": facts["bytes"], "format": facts["format"],
        "source": {"document": item["source"], "revision": revisions[item["source"]]} if item["source"] else None,
        "variant": {key: item[key] for key in ("id", "row", "artboard") if item[key] is not None} or None,
        "export": {"format": facts["format"], **(settings.get(facts["format"]) or {})},
        "check": check, "review": item["review"],
        "dimensions": {key: facts[key] for key in ("width", "height", "unit", "pages", "dpi") if key in facts} or None,
        "color": facts.get("color"), "stream": facts.get("stream"), "export_check": item["export_check"],
        "duplicates": item["duplicates"], "unreadable": facts.get("unreadable"),
    }
    return {key: value for key, value in entry.items() if value not in (None, [])}


def _file_check(item, document_status):
    if item["outcome"] is not None or item["checks"] is not None:
        return _production_check(item)
    row = document_status.get(item["source"])
    if row is not None:
        return {"source": "check-all", "state": STATE_OF_STATUS.get(row["status"], "unvalidated"), "status": row["status"],
                "errors": row.get("errors", 0), "warnings": row.get("warnings", 0)}
    return {"source": "none", "state": "unvalidated", "status": "not_checked"}


def _write(staged, entries, kept, extras, manifest):
    with zipfile.ZipFile(staged, "w") as archive:
        def add(name, source=None, payload=None, expected=None):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = 0o644 << 16
            info.compress_type = zipfile.ZIP_STORED if name.lower().endswith(STORED) else zipfile.ZIP_DEFLATED
            if payload is not None:
                archive.writestr(info, payload)
                return
            digest = hashlib.sha256()
            with source.open("rb") as stream, archive.open(info, "w", force_zip64=source.stat().st_size > 2 ** 31) as sink:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(chunk)
                    sink.write(chunk)
            # The manifest and SHA256SUMS promise this checksum, so a file that changed while it was read stops the package.
            require(digest.hexdigest() == expected, f"{source.name} changed while the package was being written",
                    "invalid_request", field="files")

        for entry, item in zip(entries, kept):
            add(entry["name"], source=item["path"], expected=entry["sha256"])
        add("SHA256SUMS", payload="".join(f"{entry['sha256']}  {entry['name']}\n" for entry in entries).encode("utf-8"))
        add("manifest.json", payload=json.dumps(manifest, indent=2, ensure_ascii=False).encode("utf-8"))
        for name, payload in sorted(extras.items()):
            add(name, payload=payload)


def build(session, request):
    """The ``package`` workflow action: see the module docstring."""
    from ... import __version__, calls
    from ...outcomes import make

    for key, default in (("check", True), ("proof", True), ("dry_run", False), ("overwrite", False)):
        require(type(request.get(key, default)) is bool, f"{key} must be boolean", field=key)
    require(request.get("layout", "flat") in LAYOUTS, f"layout is one of {', '.join(LAYOUTS)}", field="layout",
            allowed=list(LAYOUTS))
    settings = request.get("export_settings", {})
    require(isinstance(settings, dict), "export_settings maps a format to its settings", field="export_settings")
    output = session.resolve(request["output"])
    require(output.suffix.lower() == ".zip", "output is a .zip file", field="output")
    require(request.get("overwrite", False) or not output.exists(), f"{request['output']} already exists; set "
            "overwrite=true", "output_exists", field="output")
    candidates, held, info = collect(session, request)
    candidates = [item for item in candidates if item["path"] != output]
    require(len(candidates) + len(held) <= MAX_FILES, f"At most {MAX_FILES} files per package", "resource_limit",
            field="files")
    for item in candidates:
        if item["source"]:
            item["source"] = session.relative(session.resolve(item["source"]))
    default = session.relative(session.resolve(request["source"])) if request.get("source") else None
    sources = sorted({item["source"] for item in candidates if item["source"]} | ({default} if default else set()))
    revisions = {}
    for source in sources:
        path = session.resolve(source)
        require(path.suffix.lower() == ".vixl" and path.is_file(), f"source {source} is not a .vixl document",
                "not_found", field="source")
        revisions[source] = hashlib.sha256(path.read_bytes()).hexdigest()
    kept, duplicates, first = [], [], {}
    for index, item in enumerate(sorted(candidates, key=lambda c: (str(c["id"] or ""), c["workspace"]))):
        calls.check_cancelled()
        item["sha256"] = item["sha256"] or file_digest(item["path"])
        item["facts"] = inspect_file(item["path"])
        if item["sha256"] in first:
            first[item["sha256"]]["duplicates"].append({"path": item["workspace"], **({"id": item["id"]} if item["id"] else {})})
            duplicates.append(item["workspace"])
            continue
        item["duplicates"] = []
        first[item["sha256"]] = item
        kept.append(item)
        calls.progress(index + 1, len(candidates), item["workspace"])
    names = name_files(session, request, kept)
    for item in kept:
        item["name"] = names[id(item)]
    documents, document_status = None, {}
    if request.get("check", True) and not request.get("dry_run") and info["kind"] == "files":
        documents = _document_checks(session, kept)
        document_status = {entry["path"]: entry for entry in (documents or {}).get("documents", [])}
    decisions = _decisions(session, request)
    final = []
    for item in kept:
        row = document_status.get(item["source"])
        item["review"], item["review_note"] = _review(decisions, item)
        if row is not None and row["status"] in ("failed", "error"):
            held.append({"path": item["workspace"], "status": row["status"], "rules": row.get("failing", [])[:10],
                         "reason": f"its source document {item['source']} failed its checks"})
        elif item["review"] == "rejected":
            held.append({"path": item["workspace"], "status": "rejected", "reason": "rejected in visual review",
                         **({"note": item["review_note"]} if item["review_note"] else {})})
        else:
            final.append(item)
    require(final, f"Nothing to package: {len(held)} output(s) are held", "invalid_request", field="output",
            held=held[:50])
    final.sort(key=lambda item: item["name"])
    if info["kind"] == "production" and request.get("check", True) and not request.get("dry_run"):
        documents = _production_report(final, held, info)
    entries = [_entry(item, revisions, settings, _file_check(item, document_status)) for item in final]
    counts = Counter(entry["check"]["state"] for entry in entries)
    total = len(entries)
    coverage = {"files": total, "validated": counts["validated"], "needs_review": counts["needs_review"],
                "unvalidated": total - counts["validated"] - counts["needs_review"],
                "fraction_validated": round(counts["validated"] / total, 3)}
    reviews = Counter(entry["review"] for entry in entries)
    visual = ({"status": "not_reviewed"} if decisions is None else
              {"status": "approved" if reviews["approved"] == total else "pending", "approved": reviews["approved"],
               "pending": reviews["pending"], "rejected": sum(1 for entry in held if entry["status"] == "rejected")})
    plan = {"names": [entry["name"] for entry in entries], "held": held, "duplicates": duplicates}
    if request.get("dry_run"):
        return {"dry_run": True, "output": request["output"], "files": total, **plan, "validation": coverage,
                "visual_review": visual, "written": False}
    reproduction = _reproduction(session, request, sources)
    reasons = []
    if held:
        reasons.append(f"{len(held)} output(s) held and left out")
    if coverage["validated"] < total:
        reasons.append(f"{total - coverage['validated']} file(s) not fully validated")
    if visual["status"] == "not_reviewed":
        reasons.append("no visual review decisions were given")
    elif visual["status"] == "pending":
        reasons.append(f"{visual['pending']} file(s) await visual review")
    failed = [source for source, summary in (reproduction or {}).items() if not summary["reproducible"]]
    if failed:
        reasons.append(f"reproduction check failed for {', '.join(failed)}")
    outcome = make("completed", "failed" if failed else "passed" if coverage["validated"] == total else
                   "incomplete" if coverage["validated"] else "not_run", reasons)
    with tempfile.TemporaryDirectory(prefix="vixl-package-") as staging:
        staging = Path(staging)
        extras = {}
        if documents is not None:
            from .workspace_checks import render

            extras["report/check-report.json"] = render(documents, "json").encode("utf-8")
            extras["report/check-report.md"] = render(documents, "markdown").encode("utf-8")
        if request.get("proof", True):
            from .proof import proof_page

            where = {entry["name"]: item["path"] for entry, item in zip(entries, final)}
            items = [{"path": entry["name"], "note": entry["check"]["state"].replace("_", " ")}
                     for entry in entries[:MAX_PROOF]]
            proof_page(items, staging / "proof.html", resolve=where.__getitem__, title="Vixl delivery proof",
                       check=False, limits=session.limits)
            extras["proof.html"] = (staging / "proof.html").read_bytes()
        manifest = {
            "format": "vixl-package", "version": 1, "vixl_version": __version__,
            "created": datetime.now(timezone.utc).replace(microsecond=0).isoformat(), "inputs": info,
            "naming": {"template": request.get("name", DEFAULT_NAME), "layout": request.get("layout", "flat")},
            "files": entries, "held": held, "duplicates": duplicates, "validation": coverage, "visual_review": visual,
            "outcome": outcome,
            "check_report": ({"json": "report/check-report.json", "markdown": "report/check-report.md",
                              "passed": documents["passed"], "source": documents.get("source", "check-all"),
                              "held": len(held)}
                             if documents is not None else None),
            "proof": ({"page": "proof.html", "items": min(total, MAX_PROOF), "of": total} if "proof.html" in extras
                      else None),
            "reproduction": reproduction,
            "totals": {"files": total, "bytes": sum(entry["bytes"] for entry in entries), "held": len(held),
                       "duplicates": len(duplicates)},
        }
        _write(staging / "package.zip", entries, final, extras, manifest)
        try:
            publish_file(output, staging / "package.zip", replace=request.get("overwrite", False))
        except FileExistsError as exc:
            raise VixlError("output_exists", f"{request['output']} already exists; set overwrite=true",
                            field="output") from exc
    return {"output": request["output"], "bytes": output.stat().st_size, "sha256": file_digest(output), "files": total,
            **plan, "validation": coverage, "visual_review": visual, "check_report": manifest["check_report"],
            "proof": manifest["proof"], "reproduction": reproduction, "outcome": outcome, "written": True}


def cli(args, options, limits):
    """``vixl package``: the ``package`` workflow action from the command line."""
    from ...commands import Parser
    from ...interfaces import Session

    p = Parser(prog="vixl package", description="Package a campaign run's outputs or exported files into one zip with "
               "a manifest, checksums, the check report and a proof page")
    p.add_argument("--production", help="A campaign run's production.json")
    p.add_argument("--files", nargs="+", metavar="PATH_OR_GLOB", help="Exported files to package")
    p.add_argument("--source", help="The .vixl document the outputs were made from")
    p.add_argument("--out", required=True, help="The package to write (.zip)")
    p.add_argument("--name", help=f"File name template (default {DEFAULT_NAME})")
    p.add_argument("--brand", help="Value of {brand} (default: the brand.json name)")
    p.add_argument("--locale", help="Value of {locale} where a row has none")
    p.add_argument("--layout", choices=LAYOUTS, help="Folders inside the package (default flat)")
    p.add_argument("--lock", action="append", metavar="[SOURCE=]LOCKFILE", help="A render lockfile of the source "
                   "document (repeat as SOURCE=LOCKFILE for several documents)")
    p.add_argument("--decisions", help="The proof page's downloaded decisions JSON")
    p.add_argument("--no-check", action="store_true", help="Leave out the check report")
    p.add_argument("--no-proof", action="store_true", help="Leave out the proof page")
    p.add_argument("--dry-run", action="store_true", help="Show the names, duplicates and held outputs; write nothing")
    p.add_argument("--overwrite", action="store_true", help="Replace an existing package")
    p.add_argument("--workspace", default=".", help="Workspace folder (default: the current folder)")
    a = p.parse_args(args)
    request = {"output": a.out}
    for key in ("production", "files", "source", "name", "brand", "locale", "layout", "decisions"):
        if getattr(a, key) is not None:
            request[key] = getattr(a, key)
    if a.lock:
        pairs = [item.partition("=") for item in a.lock]
        if len(a.lock) == 1 and not pairs[0][1]:
            request["lock"] = a.lock[0]
        else:
            require(all(sep for _, sep, _ in pairs), "Use --lock FILE for one document, or --lock SOURCE=FILE for each",
                    "usage_error")
            request["lock"] = {key: value for key, _, value in pairs}
    for key, flag in (("check", a.no_check), ("proof", a.no_proof)):
        if flag:
            request[key] = False
    for key in ("dry_run", "overwrite"):
        if getattr(a, key):
            request[key] = True
    return build(Session(None, limits, workspace=a.workspace), request)
