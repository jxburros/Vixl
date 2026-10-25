"""Exports recorded in a render lockfile (#512): what was asked for, what came out and how to compare it again.

An export is named like the CLI's ``--export FORMAT[:option=value,...]`` (or ``{format, options}``). Recording one
encodes it in memory, hashes the bytes (``sha256``), decodes the result and hashes the pixels or sampled frames
(``visual_sha256``), and keeps a 16x16 block-average ``signature`` of each sampled frame. Verifying runs the same export
again and reports two answers separately:

- ``byte_identical``: the bytes match. This is the verdict for formats that Vixl or a lossless encoder writes
  deterministically (``EXACT``: PNG, SVG, PDF, HTML, PPTX, PSD, TIFF, ICO, APNG).
- ``visually_equivalent``: the decoded pixels or frames match exactly, or every block average of the signature moved by
  at most the tolerance. This is the verdict for lossy encoders whose bytes depend on the encoder version and build
  (JPEG, WebP, AVIF, GIF, MP4, WebM), unless the caller asks for it everywhere.

The signature is a coarse thumbnail: it catches a changed colour, layout or picture, not a one-pixel shift (the exact
decoded hash does that). Only options from ``STILL_OPTIONS`` and ``TIMELINE_OPTIONS`` are recorded, as typed scalars, so
free text from the environment cannot end up in a lockfile. An ICC profile is recorded by the path given and its SHA-256
under ``toolchain``.
"""

import difflib
import hashlib
import re
import shutil
import subprocess
import tempfile
from functools import lru_cache
from pathlib import Path

from PIL import Image

from ...assets import open_image, read_bounded
from ...errors import VixlError, require
from ...model import is_int, is_number
from ...normalize import EXPORT_FORMAT_ALIASES

# format: (kind, byte_exact). "still" goes through Project.export, "timeline" through export_timeline.
FORMATS = {
    "png": ("still", True), "svg": ("still", True), "pdf": ("still", True), "html": ("still", True),
    "pptx": ("still", True), "psd": ("still", True), "tiff": ("still", True), "ico": ("still", True),
    "jpg": ("still", False), "webp": ("still", False), "avif": ("still", False),
    "apng": ("timeline", True), "gif": ("timeline", False), "mp4": ("timeline", False), "webm": ("timeline", False),
}
SUFFIX = {"apng": "png"}
VIDEO = ("mp4", "webm")
TRUE, FALSE = ("true", "yes", "on", "1"), ("false", "no", "off", "0")
GRID = 16
SAMPLES = 5
DEFAULT_TOLERANCE = 8
ICC_BYTES = 16 * 1024 * 1024
STILL_OPTIONS = {
    "quality": ("int", 1, 100), "scale": ("number", 0.01, 16), "profile": ("str",), "background": ("str",),
    "sampling": ("enum", ("smooth", "nearest")), "color_space": ("enum", ("rgb", "cmyk")), "icc_profile": ("path",),
    "intent": ("enum", ("perceptual", "relative", "saturation", "absolute")), "black_generation": ("number", 0, 1),
    "ink_limit": ("number", 100, 400), "proof": ("bool",),
    "simulate": ("enum", ("protanopia", "deuteranopia", "tritanopia", "achromatopsia")),
    "dpi": ("number", 36, 2400), "alpha": ("enum", ("auto", "keep", "flatten")), "page": ("page",), "pages": ("str",),
    "pdf_content": ("enum", ("vector", "raster")), "svg_policy": ("enum", ("appearance", "strict")),
    "svg_document": ("bool",), "artboard": ("str",), "comp": ("str",), "time": ("time",), "title": ("str",),
}
TIMELINE_OPTIONS = {
    "fps": ("number", 1, 60), "scale": ("number", 0.05, 16), "start": ("time",), "end": ("time",),
    "background": ("str",), "quality": ("int", 1, 100), "colors": ("int", 2, 256),
    "dither": ("enum", ("auto", "none", "ordered", "floyd")), "poster": ("time",),
    "preset": ("enum", ("chat", "web", "email")),
}
# What an unset option means, so "jpg" and "jpg:quality=90" are the same export and a changed quality is not.
DEFAULTS = {
    "png": {"scale": 1, "alpha": "auto"}, "jpg": {"scale": 1, "quality": 90, "color_space": "rgb"},
    "webp": {"scale": 1, "quality": 90, "alpha": "auto"}, "avif": {"scale": 1, "quality": 90, "alpha": "auto"},
    "tiff": {"scale": 1, "alpha": "auto", "color_space": "rgb"}, "pdf": {"scale": 1, "color_space": "rgb"},
    "svg": {"scale": 1}, "html": {"scale": 1}, "pptx": {}, "psd": {}, "ico": {"scale": 1, "alpha": "auto"},
    "gif": {"scale": 1, "colors": 256, "dither": "auto"}, "apng": {"scale": 1},
    "mp4": {"scale": 1, "quality": 90}, "webm": {"scale": 1, "quality": 90},
}


def _fail(message, **details):
    raise VixlError("invalid_request", message, field="exports", **details)


def _coerce(name, value, rule, label):
    kind = rule[0]
    where = f"{label}: {name}"
    if kind == "bool":
        if isinstance(value, str) and value.strip().lower() in TRUE + FALSE:
            value = value.strip().lower() in TRUE
        require(type(value) is bool, f"{where} is true or false", field="exports")
        return value
    if kind in ("int", "number"):
        if isinstance(value, str):
            try:
                value = float(value)
            except ValueError:
                _fail(f"{where} is a number")
        require(is_number(value) and rule[1] <= value <= rule[2], f"{where} is a number from {rule[1]} to {rule[2]}",
                field="exports")
        require(kind == "number" or value == int(value), f"{where} is a whole number", field="exports")
        return int(value) if value == int(value) else float(value)
    if kind == "enum":
        require(value in rule[1], f"{where} is one of {', '.join(rule[1])}", field="exports", allowed=list(rule[1]))
        return value
    if kind == "time":
        if isinstance(value, str) and re.fullmatch(r"\d+(\.\d+)?", value.strip()):
            value = float(value)
        require((is_number(value) and value >= 0) or (isinstance(value, str) and 0 < len(value) <= 40),
                f"{where} is a time in milliseconds, '1.5s', '50%' or a marker name", field="exports")
        return int(value) if is_number(value) and value == int(value) else value
    if kind == "page":
        if isinstance(value, str) and value.isdigit():
            value = int(value)
        require((is_int(value) and value >= 1) or (isinstance(value, str) and 0 < len(value) <= 80),
                f"{where} is a page number or name", field="exports")
        return value
    require(isinstance(value, str) and 0 < len(value) <= 300 and "\0" not in value, f"{where} is a short text",
            field="exports")
    return value


def _split(spec):
    format_, _, rest = spec.partition(":")
    options = {}
    for part in [p for p in rest.split(",") if p.strip()]:
        key, equals, value = part.partition("=")
        require(equals and key.strip(), f"{spec!r}: write options as key=value, separated by commas", field="exports")
        options[key.strip().replace("-", "_")] = value.strip()
    return format_.strip(), options


def parse(spec):
    """One export request as ``{format, kind, byte_exact, options}`` with every option checked, typed and defaulted.
    ``spec`` is ``"jpg:quality=80,scale=2"`` or ``{"format": "jpg", "options": {"quality": 80}}``."""
    if isinstance(spec, str):
        name, options = _split(spec)
    else:
        require(isinstance(spec, dict) and set(spec) <= {"format", "options"} and isinstance(spec.get("format"), str),
                "An export is 'FORMAT[:key=value,...]' or {format, options}", field="exports")
        name, options = spec["format"], spec.get("options") or {}
        require(isinstance(options, dict), "options is an object of export settings", field="exports")
    name = name.lower().lstrip(".")
    name = EXPORT_FORMAT_ALIASES.get(name, name)
    if name not in FORMATS:
        close = difflib.get_close_matches(name, FORMATS, 1, 0.6)
        _fail(f"Unknown export format {name!r}; use {', '.join(FORMATS)}", allowed=list(FORMATS), suggestions=close)
    kind, exact = FORMATS[name]
    animated = name == "webp" and _coerce("animated", options.get("animated", False), ("bool",), name)
    if animated:
        kind, exact = "timeline", False
    table = TIMELINE_OPTIONS if kind == "timeline" else STILL_OPTIONS
    clean = {}
    for key, value in options.items():
        if key == "animated" and name == "webp":
            continue
        if key not in table:
            close = difflib.get_close_matches(key, table, 1, 0.5)
            _fail(f"{name}: unknown option {key!r}" + (f"; did you mean {close[0]!r}?" if close else "")
                  + f". Options: {', '.join(sorted(table))}", allowed=sorted(table), suggestions=close)
        clean[key] = _coerce(key, value, table[key], name)
    if animated:
        clean["animated"] = True
    defaults = DEFAULTS[name] if not animated else {"scale": 1, "quality": 90}
    return {"format": name, "kind": kind, "byte_exact": exact,
            "options": dict(sorted({**{k: v for k, v in defaults.items() if k in table}, **clean}.items()))}


def parse_all(specs):
    require(isinstance(specs, list) and 0 < len(specs) <= 16, "Give 1-16 exports", field="exports")
    return [parse(spec) for spec in specs]


def alias_notes(specs):
    """The ``normalized`` notes for requests that used a format alias (``jpeg``) or hyphenated option names
    (``color-space``); call it after ``parse_all`` accepted the requests."""
    notes = []
    for index, spec in enumerate(specs or []):
        where = f"exports[{index}]"
        if isinstance(spec, str):
            name, _, rest = spec.partition(":")
            keys = [part.partition("=")[0].strip() for part in rest.split(",")]
        else:
            name, keys = str(spec.get("format", "")), []
        name = name.strip().lower().lstrip(".")
        if name in EXPORT_FORMAT_ALIASES:
            notes.append({"field": where, "from": name, "to": EXPORT_FORMAT_ALIASES[name],
                          "reason": "export format alias"})
        notes += [{"field": where, "from": key, "to": key.replace("-", "_"), "reason": "option names use underscores"}
                  for key in keys if "-" in key]
    return notes


def label(entry):
    """The export as it would be typed: ``jpg:quality=80``."""
    defaults = DEFAULTS.get(entry["format"], {})
    shown = {k: v for k, v in entry["options"].items() if defaults.get(k) != v}
    return entry["format"] + (":" + ",".join(f"{k}={str(v).lower() if type(v) is bool else v}"
                                             for k, v in shown.items()) if shown else "")


# Encoding ---------------------------------------------------------------------------------------

def encode(project, entry, *, resolve=Path, limits=None):
    """Encode one export in memory: ``(bytes, info)`` where info holds the frame count and size of a timeline."""
    options = dict(entry["options"])
    if entry["kind"] == "still":
        if "icc_profile" in options:
            options["icc_profile"] = read_bounded(resolve(options["icc_profile"]), ICC_BYTES)
        return project.export(format=entry["format"], **options), {}
    from ...timeline import export_timeline

    options.pop("animated", None)
    suffix = SUFFIX.get(entry["format"], entry["format"])
    with tempfile.TemporaryDirectory(prefix="vixl-lock-") as staging:
        path = Path(staging) / f"export.{suffix}"
        result = export_timeline(project, path, format=entry["format"], **options)
        data = path.read_bytes()
    return data, {key: result[key] for key in ("frames", "fps", "size") if key in result}


# Decoding ---------------------------------------------------------------------------------------

def sample_indexes(count, samples=SAMPLES):
    """Up to ``samples`` frame indexes spread from the first to the last of ``count`` frames."""
    count = max(1, count)
    if count <= samples:
        return list(range(count))
    return sorted({round(i * (count - 1) / (samples - 1)) for i in range(samples)})


def signature(image):
    """A 16x16 block-average thumbnail of ``image`` over white, as hex (3 bytes per block)."""
    base = Image.new("RGBA", image.size, (255, 255, 255, 255))
    base.alpha_composite(image.convert("RGBA"))
    return base.convert("RGB").resize((GRID, GRID), Image.Resampling.BOX).tobytes().hex()


def _animated_frames(data, limits):
    with open_image(data) as source:
        count = getattr(source, "n_frames", 1)
        frames = []
        for index in sample_indexes(count):
            source.seek(index)
            limits.size(*source.size)
            frames.append(source.convert("RGBA"))
    return frames, count


def _video_frames(data, suffix, count, limits):
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return None, count
    indexes = sample_indexes(count)
    select = "select=" + "+".join(f"eq(n\\,{i})" for i in indexes)
    with tempfile.TemporaryDirectory(prefix="vixl-lock-") as staging:
        source = Path(staging) / f"export.{suffix}"
        source.write_bytes(data)
        pattern = str(Path(staging) / "frame-%03d.png")
        command = [ffmpeg, "-v", "error", "-i", str(source), "-vf", select, "-fps_mode", "passthrough", pattern]
        done = subprocess.run(command, capture_output=True, timeout=300)
        if done.returncode and b"fps_mode" in done.stderr:  # ffmpeg before 5.1 spells it -vsync 0
            command[command.index("-fps_mode"):command.index("-fps_mode") + 2] = ["-vsync", "0"]
            done = subprocess.run(command, capture_output=True, timeout=300)
        if done.returncode:
            raise VixlError("codec_error", "ffmpeg could not decode the export: "
                            + done.stderr.decode("utf-8", "replace").strip()[:300])
        frames = []
        for path in sorted(Path(staging).glob("frame-*.png")):
            with open_image(path) as frame:
                limits.size(*frame.size)
                frames.append(frame.convert("RGBA"))
    return frames, count


def decode(entry, data, info, limits):
    """``(frames, count)``: the decoded sample frames (RGBA images) and the frame count of the export, or
    ``(None, count)`` when the format has no decoder here (HTML, PPTX, PSD, an SVG or PDF without its renderer)."""
    name, kind = entry["format"], entry["kind"]
    if kind == "timeline":
        if name in VIDEO:
            return _video_frames(data, name, info.get("frames", 1), limits)
        return _animated_frames(data, limits)
    if name in ("html", "pptx", "psd"):
        return None, 1
    from ...image_diff import load_visual

    try:
        return [load_visual(Path(f"export.{name}"), limits, data=data)], 1
    except (VixlError, OSError, ValueError, RuntimeError):
        return None, 1  # No SVG or PDF renderer here, or a file it cannot draw: the bytes are still compared.


@lru_cache(maxsize=4)
def _ffmpeg_version(path):
    try:
        text = subprocess.run([path, "-version"], capture_output=True, timeout=30).stdout.decode("utf-8", "replace")
    except (OSError, subprocess.TimeoutExpired):
        return None
    found = re.match(r"ffmpeg version (\S+)", text)
    return found.group(1) if found else None


def ffmpeg_version():
    """The version string of the ffmpeg on PATH (``6.1.1``), or None."""
    path = shutil.which("ffmpeg")
    return _ffmpeg_version(path) if path else None


# Recording and comparing ------------------------------------------------------------------------

def record(project, entry, *, resolve=Path, limits=None):
    """Encode ``entry`` and describe the result for a lockfile: hashes, size, frames and signature."""
    from ...model import Limits
    from .reproduce import render_hash

    limits = limits or Limits()
    data, info = encode(project, entry, resolve=resolve, limits=limits)
    result = {"format": entry["format"], "options": dict(entry["options"]), "kind": entry["kind"],
              "deterministic": entry["byte_exact"], "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
    frames, count = decode(entry, data, info, limits)
    if frames:
        result["size"] = list(frames[0].size)
        result["visual_sha256"] = hashlib.sha256("|".join(render_hash(frame) for frame in frames).encode()).hexdigest()
        result["signature"] = [signature(frame) for frame in frames]
        if entry["kind"] == "timeline":
            result["frames"] = count
    else:
        result["visual_sha256"] = None
    return result


def toolchain(entries, *, resolve=Path):
    """The external tools the exports depend on: the ffmpeg version for video, the SHA-256 of each ICC profile."""
    found = {}
    if any(entry["format"] in VIDEO for entry in entries):
        found["ffmpeg"] = ffmpeg_version()
    profiles = {}
    for entry in entries:
        path = entry["options"].get("icc_profile")
        if path:
            try:
                profiles[path] = hashlib.sha256(read_bounded(resolve(path), ICC_BYTES)).hexdigest()
            except (OSError, VixlError):
                profiles[path] = None
    if profiles:
        found["icc"] = dict(sorted(profiles.items()))
    return found


def record_all(project, entries, *, resolve=Path, limits=None):
    """``(records, toolchain)`` for ``entries`` (parsed exports). An export that cannot run keeps its settings and an
    ``error`` instead of hashes, so verification can say which one failed."""
    records = []
    for entry in entries:
        try:
            records.append(record(project, entry, resolve=resolve, limits=limits))
        except (VixlError, OSError, subprocess.SubprocessError) as exc:
            error = exc.as_dict() if isinstance(exc, VixlError) else {"error": type(exc).__name__, "message": str(exc)[:300]}
            records.append({"format": entry["format"], "options": dict(entry["options"]), "kind": entry["kind"],
                            "deterministic": entry["byte_exact"], "error": error})
    return records, toolchain(entries, resolve=resolve)


def plan(locked_exports, requested):
    """What verification runs: ``[(locked index or None, entry)]``. Without ``requested`` every locked export runs with
    its locked settings; a requested export replaces the locked one of the same settings, else the first unmatched
    locked export of its format, and one with no locked counterpart is run and reported as not locked."""
    locked = [{"format": item["format"], "kind": item.get("kind", FORMATS[item["format"]][0]),
               "byte_exact": item.get("deterministic", FORMATS[item["format"]][1]), "options": dict(item["options"])}
              for item in locked_exports]
    if not requested:
        return list(enumerate(locked))
    used, planned = set(), []
    for entry in requested:
        match = next((i for i, item in enumerate(locked) if i not in used and item["format"] == entry["format"]
                      and item["options"] == entry["options"]), None)
        if match is None:
            match = next((i for i, item in enumerate(locked) if i not in used and item["format"] == entry["format"]),
                         None)
        if match is not None:
            used.add(match)
        planned.append((match, entry))
    planned += [(i, item) for i, item in enumerate(locked) if i not in used]
    return sorted(planned, key=lambda pair: (pair[0] is None, pair[0] if pair[0] is not None else 0))


def _difference(locked, current):
    """The largest block-average change between two signature lists, or None when they cannot be compared."""
    old, new = locked.get("signature") or [], current.get("signature") or []
    if not old or len(old) != len(new) or locked.get("size") != current.get("size") \
            or locked.get("frames") != current.get("frames"):
        return None
    return max(abs(a - b) for x, y in zip(old, new) for a, b in zip(bytes.fromhex(x), bytes.fromhex(y)))


def compare(locked, current, *, tolerance=DEFAULT_TOLERANCE, visual_only=False):
    """One export's verdict. ``byte_identical`` and ``visually_equivalent`` (None when a side has no decoded pixels)
    are reported separately; ``passed`` follows the bytes for ``deterministic`` formats and the pixels for lossy ones
    (``visual_only`` makes it the pixels everywhere)."""
    item = {"format": current["format"], "options": current["options"], "deterministic": current.get("deterministic")}
    if "error" in current:
        return {**item, "passed": False, "byte_identical": None, "visually_equivalent": None, "compared": "none",
                "error": current["error"]}
    same_bytes = bool(locked.get("sha256")) and locked.get("sha256") == current["sha256"]
    equivalent, difference = None, None
    if locked.get("visual_sha256") and current.get("visual_sha256"):
        if locked["visual_sha256"] == current["visual_sha256"]:
            equivalent, difference = True, 0
        else:
            difference = _difference(locked, current)
            equivalent = difference is not None and difference <= tolerance
    by_bytes = bool(current.get("deterministic")) and not visual_only
    passed = same_bytes if by_bytes else (equivalent if equivalent is not None else same_bytes)
    return {**item, "passed": passed, "byte_identical": same_bytes, "visually_equivalent": equivalent,
            "compared": "bytes" if by_bytes else "pixels", "tolerance": None if by_bytes else tolerance,
            "max_difference": difference, "bytes": {"locked": locked.get("bytes"), "current": current["bytes"]}}


def drift(locked, current):
    """Located export differences: ``export-setting`` (a requested option differs from the locked one, or the export
    was not locked) and ``toolchain`` (ffmpeg version or ICC profile changed), each named ``FORMAT.OPTION``."""
    found = []
    old_entries = locked.get("exports") or []
    old_chain, new_chain = locked.get("toolchain") or {}, current.get("toolchain") or {}
    for entry in current.get("exports") or []:
        index, name = entry.get("locked_index"), entry["format"]
        if index is None:
            found.append({"kind": "export-setting", "name": name, "format": name, "option": None, "locked": None,
                          "current": label(entry)})
            continue
        before = old_entries[index]
        changed = [key for key in sorted(set(before["options"]) | set(entry["options"]))
                   if before["options"].get(key) != entry["options"].get(key)]
        for key in changed:
            found.append({"kind": "export-setting", "name": f"{name}.{key}", "format": name, "option": key,
                          "locked": before["options"].get(key), "current": entry["options"].get(key)})
        if name in VIDEO and "ffmpeg" in old_chain and old_chain["ffmpeg"] != new_chain.get("ffmpeg"):
            found.append({"kind": "toolchain", "name": f"{name}.ffmpeg", "format": name, "option": "ffmpeg",
                          "locked": old_chain["ffmpeg"], "current": new_chain.get("ffmpeg")})
        path = entry["options"].get("icc_profile")
        if path and path == before["options"].get("icc_profile") and path in (old_chain.get("icc") or {}) \
                and old_chain["icc"][path] != (new_chain.get("icc") or {}).get(path):
            found.append({"kind": "toolchain", "name": f"{name}.icc_profile", "format": name, "option": "icc_profile",
                          "locked": old_chain["icc"][path], "current": (new_chain.get("icc") or {}).get(path)})
    return found
