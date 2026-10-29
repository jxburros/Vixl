"""Reviewable lyric alignment records; all public times are audio-relative milliseconds."""

import base64
from copy import deepcopy
import hashlib
import json
import re

from ...assets import read_bounded
from ...automation import bounded_object
from ...errors import VixlError, require
from ...model import finite, is_number
from ...production import write_bytes
from ..film.film import audio_duration, local_path
from .lyrics import MAX_LINES, MAX_LINE_CHARS, MAX_LRC_BYTES, MAX_VIDEO_MS, TIMESTAMP, parse_lrc

MAX_RECORD = 4 * 1024 * 1024
ALIGN_FIELDS = {"audio", "lyrics", "output", "provider", "replace_lines", "confidence", "replace"}
EDIT_FIELDS = {"timing", "output", "edits", "replace"}
EXPORT_FIELDS = {"timing", "output", "replace"}


def _same(a, b):
    require(isinstance(a, str) and isinstance(b, str), "Alignment text must be a string", "provider_error")
    return " ".join(a.split()) == " ".join(b.split())


def _path(root, request, key):
    require(isinstance(request.get(key), str) and request[key], f"{key} needs a workspace-relative path", field=key)
    return local_path(root, request[key])


def _output(root, request):
    path = _path(root, request, "output")
    require(isinstance(request.get("replace", False), bool), "replace must be true or false", field="replace")
    require(request.get("replace", False) or not path.exists(),
            "Output already exists; choose another path or pass replace: true", "file_exists", field="output")
    return path


def _save(path, value, *, replace=False):
    from ...calls import check_cancelled
    check_cancelled()
    data = json.dumps(value, ensure_ascii=False, indent=2).encode()
    require(len(data) <= MAX_RECORD, "Timing record exceeds 4 MiB", "resource_limit")
    write_bytes(path, data, replace=replace)


def findings(record):
    """Validate shape strictly, but retain questionable times as actionable review findings."""
    require(isinstance(record, dict) and record.get("version") == 1,
            "Expected a version 1 lyric timing record", field="timing")
    duration = finite(record.get("duration_ms"), "duration_ms", 1, MAX_VIDEO_MS)
    threshold = finite(record.get("confidence_threshold", 0.7), "confidence_threshold", 0, 1)
    lines = record.get("lines")
    require(isinstance(lines, list) and 1 <= len(lines) <= MAX_LINES, "Timing needs 1–1000 lines", field="timing")
    metadata = record.get("metadata", {})
    require(isinstance(metadata, dict) and all(key in ("title", "artist", "album") and isinstance(value, str)
            and len(value) <= 1000 for key, value in metadata.items()), "Invalid timing metadata")
    require(isinstance(record.get("sources", {}), dict), "Timing sources must be an object")
    sections = record.get("sections", [])
    require(isinstance(sections, list) and len(sections) <= 100, "Invalid timing section list")
    from .lyrics import slug
    for i, section in enumerate(sections):
        require(isinstance(section, dict) and isinstance(section.get("label"), str) and
                1 <= len(section["label"]) <= 80 and is_number(section.get("time")) and
                0 <= section["time"] < duration, "Invalid timing section")
        section.setdefault("name", slug(section["label"]))
        section.setdefault("source_line", i + 1)
        require(isinstance(section["name"], str) and section["name"] and type(section["source_line"]) is int,
                "Invalid timing section name or source line")
    warnings = []

    def warn(code, index, message, *, word=None, blocking=True):
        warnings.append({"code": code, "index": index, "message": message, "blocking": blocking,
                         **({"word": word} if word is not None else {})})

    previous = -1
    for i, line in enumerate(lines):
        require(isinstance(line, dict) and line.get("index") == i, "Timing lines need consecutive zero-based indices")
        require(isinstance(line.get("text"), str) and 0 < len(line["text"]) <= MAX_LINE_CHARS,
                "Timing lines need nonempty text of at most 500 characters")
        start, end = line.get("start"), line.get("end")
        require(all(is_number(v) and abs(v) < 1e9 for v in (start, end)), "Timing values must be finite milliseconds")
        if start < 0 or end <= start or end > duration:
            warn("invalid_range", i, "Line needs 0 <= start < end <= audio duration")
        if start < previous:
            warn("non_monotonic", i, "Line starts before the previous line ends")
        previous = end
        confidence = line.get("confidence")
        require(confidence is None or is_number(confidence) and 0 <= confidence <= 1, "Confidence must be 0–1 or null")
        if confidence is not None and confidence < threshold:
            warn("low_confidence", i, "Review this line's alignment confidence", blocking=False)
        if line.get("matched") is False:
            warn("unmatched_line", i, "Provider did not match this source line")
        words = line.setdefault("words", [])
        require(isinstance(words, list) and len(words) <= MAX_LINE_CHARS, "Invalid word timing list")
        previous_word = start
        for j, word in enumerate(words):
            require(isinstance(word, dict) and isinstance(word.get("text"), str) and word["text"], "Words need text")
            a, b = word.get("start"), word.get("end")
            require(all(is_number(v) and abs(v) < 1e9 for v in (a, b)), "Word times must be finite milliseconds")
            if a < start or b <= a or b > end:
                warn("invalid_word_range", i, "Word must lie inside its line", word=j)
            if a < previous_word:
                warn("non_monotonic_word", i, "Word starts before the previous word ends", word=j)
            previous_word = b
            confidence = word.get("confidence")
            require(confidence is None or is_number(confidence) and 0 <= confidence <= 1, "Confidence must be 0–1 or null")
            if confidence is not None and confidence < threshold:
                warn("low_confidence", i, "Review this word's alignment confidence", word=j, blocking=False)
        if words and not _same(" ".join(w["text"] for w in words), line["text"]):
            warn("word_text_mismatch", i, "Timed words do not reproduce the source line")
    return warnings


def _review(record):
    structural = findings(record)
    analysis = record.get("analysis_warnings", [])
    require(isinstance(analysis, list) and len(analysis) <= 1000 and all(isinstance(w, dict) for w in analysis),
            "analysis_warnings must be a bounded list of findings", field="timing")
    record["warnings"] = structural + analysis
    record["valid"] = not any(w.get("blocking", False) for w in record["warnings"])
    record["review"] = {"status": "pending"}
    return record


def load(path):
    try:
        record = json.loads(read_bounded(path, MAX_RECORD))
    except (ValueError, UnicodeDecodeError) as exc:
        raise VixlError("invalid_timing", "Timing file must contain valid JSON") from exc
    return _review(record)


def _source(path):
    raw = read_bounded(path, MAX_LRC_BYTES)
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise VixlError("invalid_timing", "Lyrics must be UTF-8") from exc
    if any(TIMESTAMP.match(line.strip()) for line in text.splitlines()):
        parsed = parse_lrc(text)
        lines = [{**line, "time": line["time"] - parsed["offset"]} for line in parsed["lines"] if line["text"]]
        return lines, parsed, raw
    lines = [{"text": " ".join(line.split()), "source_line": i + 1} for i, line in enumerate(text.splitlines()) if line.strip()]
    require(1 <= len(lines) <= MAX_LINES and all(len(line["text"]) <= MAX_LINE_CHARS for line in lines),
            "Lyrics need 1–1000 lines of at most 500 characters")
    return lines, {"metadata": {}, "sections": [], "offset": 0}, raw


def align(request, root, limits=None):
    """Call one configured adapter, preserving supplied line starts unless replace_lines is explicit."""
    bounded_object(request, ALIGN_FIELDS, "Unknown lyric alignment field")
    destination = _output(root, request)
    audio, lyrics = _path(root, request, "audio"), _path(root, request, "lyrics")
    require(destination not in (audio, lyrics), "Timing output cannot replace an input", field="output")
    replace = request.get("replace_lines", False)
    require(isinstance(replace, bool), "replace_lines must be true or false", field="replace_lines")
    require(request.get("provider") is None or isinstance(request["provider"], str), "provider must be a configured name", field="provider")
    threshold = finite(request.get("confidence", 0.7), "confidence", 0, 1)
    lines, parsed, lyric_bytes = _source(lyrics)
    duration = audio_duration(audio)
    require(0 < duration <= MAX_VIDEO_MS, "Alignment audio must be at most 10 minutes", "resource_limit")
    from ..ai.models import route
    try:
        backend = route("align", request.get("provider"))
    except VixlError as exc:
        if exc.code not in ("provider_not_configured", "unsupported_capability"):
            raise
        raise VixlError("missing_dependency", "Configure an align HTTP or command provider in providers.json; "
                        "see docs/reference/providers.md#lyric-alignment") from exc
    kind = backend.config.get("type", "http")
    require(kind in ("http", "command"), "Alignment needs an HTTP or command provider; see docs/reference/providers.md#lyric-alignment",
            "missing_dependency")
    audio_bytes = read_bounded(audio, 64 * 1024 * 1024)
    payload = {"audio": base64.b64encode(audio_bytes).decode(), "audio_format": audio.suffix.lstrip("."),
               "duration_ms": duration, "units": "milliseconds", "lines": [{"index": i, "text": line["text"],
               **({"start": line["time"]} if "time" in line else {})} for i, line in enumerate(lines)]}
    if backend.config.get("model"):
        payload["model"] = backend.config["model"]
    answer = backend.invoke("align", payload)
    returned = answer.get("lines")
    require(isinstance(returned, list) and len(returned) <= MAX_LINES, "Align provider must return lines[]", "provider_error")
    indexed = {}
    for i, line in enumerate(returned):
        require(isinstance(line, dict), "Alignment lines must be objects", "provider_error")
        index = line.get("index", i)
        require(type(index) is int and 0 <= index < len(lines) and index not in indexed,
                "Alignment line indices must be unique source indices", "provider_error")
        indexed[index] = line
    built = []
    for i, source in enumerate(lines):
        value = indexed.get(i, {})
        preserved = "time" in source and not replace
        start = source["time"] if preserved else value.get("start", source.get("time", 0))
        end = (lines[i + 1].get("time", duration) if i + 1 < len(lines) else duration) if preserved else value.get("end", start)
        words = value.get("words", [])
        require(isinstance(words, list) and all(isinstance(w, dict) for w in words), "Alignment words must be objects", "provider_error")
        built.append({"index": i, "text": source["text"], "start": start, "end": end,
                      "source": "lrc" if preserved else "aligned", "confidence": value.get("confidence"),
                      "matched": bool(value) and _same(value.get("text", source["text"]), source["text"]),
                      "words": [{"text": w.get("text"), "start": w.get("start"), "end": w.get("end"),
                                 "confidence": w.get("confidence"), "source": "aligned"} for w in words]})
    from ..film.media_analysis import audio_analyze
    silence = audio_analyze(audio, min_silence=1000)["silence"]
    record = {"version": 1, "units": "milliseconds", "duration_ms": duration, "confidence_threshold": threshold,
              "metadata": parsed["metadata"], "sections": [{**s, "time": s["time"] - parsed["offset"]} for s in parsed["sections"]],
              "sources": {"audio_sha256": hashlib.sha256(audio_bytes).hexdigest(), "lyrics_sha256": hashlib.sha256(lyric_bytes).hexdigest()},
              "provenance": {"provider": backend.name, "type": kind}, "lines": built,
              "analysis_warnings": [{"code": "silence", **gap, "blocking": False,
                                     "message": "Detected silence; review any lyric timing across this interval"} for gap in silence]}
    # Only a configured model identifier is provenance; never copy provider payloads, argv, URLs or credentials.
    if isinstance(backend.config.get("model"), str):
        record["provenance"]["model"] = backend.config["model"][:200]
    _review(record)
    _save(destination, record, replace=request.get("replace", False))
    return {"output": request["output"], **record}


def edit(request, root, limits=None):
    bounded_object(request, EDIT_FIELDS, "Unknown timing edit field")
    destination = _output(root, request)
    record = load(_path(root, request, "timing"))
    edits = request.get("edits")
    require(isinstance(edits, list) and 1 <= len(edits) <= 1000, "edits needs 1–1000 timing edits", field="edits")
    for change in edits:
        bounded_object(change, {"line", "word", "shift", "start", "end"}, "Unknown timing edit field")
        index = change.get("line")
        require(type(index) is int and 0 <= index < len(record["lines"]), "Invalid timing line index")
        line = record["lines"][index]
        target = line
        if "word" in change:
            word = change["word"]
            require(type(word) is int and 0 <= word < len(line["words"]), "Invalid timing word index")
            target = line["words"][word]
        require(bool(set(change) & {"shift", "start", "end"}), "Timing edit needs shift, start or end")
        if "shift" in change:
            amount = finite(change["shift"], "shift", -MAX_VIDEO_MS, MAX_VIDEO_MS)
            for value in [target, *(line["words"] if target is line else [])]:
                value["start"] += amount
                value["end"] += amount
                value["source"] = "edited"
        for field in ("start", "end"):
            if field in change:
                target[field] = finite(change[field], field, 0, MAX_VIDEO_MS)
        target["source"] = "edited"
        line["matched"] = True
    _review(record)
    _save(destination, record, replace=request.get("replace", False))
    return {"output": request["output"], **record}


def stamp(value, word=False):
    value = round(value)
    body = f"{value // 60000:02d}:{value % 60000 // 1000:02d}.{value % 1000:03d}"
    return f"<{body}>" if word else f"[{body}]"


def export(request, root, limits=None):
    bounded_object(request, EXPORT_FIELDS, "Unknown timing export field")
    destination = _output(root, request)
    source = _path(root, request, "timing")
    require(destination != source, "LRC output cannot replace the timing record", field="output")
    record = load(source)
    require(record["valid"], "Fix invalid timing before exporting LRC", "invalid_timing", findings=record["warnings"])
    rows = []
    for key, tag in (("title", "ti"), ("artist", "ar"), ("album", "al")):
        value = record.get("metadata", {}).get(key)
        if value:
            require(not re.search(r"[\[\]\r\n]", value), "LRC metadata cannot contain brackets or newlines")
            rows.append(f"[{tag}:{value}]")
    events = [(section["time"], 0, stamp(section["time"]) + "[" + section["label"] + "]")
              for section in record.get("sections", [])]
    for line in record["lines"]:
        require(not re.search(r"[\[\]<>\r\n]", line["text"]), "LRC cannot encode bracket or newline text losslessly")
        body = " ".join(stamp(w["start"], True) + w["text"] for w in line["words"]) if line["words"] else line["text"]
        events.append((line["start"], 1, stamp(line["start"]) + body))
    rows.extend(row for _, _, row in sorted(events))
    write_bytes(destination, ("\n".join(rows) + "\n").encode(), replace=request.get("replace", False))
    return {"output": request["output"], "lines": len(record["lines"]), "review": {"status": "pending"}}


def parsed(record, duration):
    """Adapt a timing record to the existing LRC build path without executing a provider."""
    record = _review(deepcopy(record))
    require(record["valid"], "Fix invalid timing before building", "invalid_timing", findings=record["warnings"])
    require(abs(record["duration_ms"] - duration) <= 1, "Timing duration does not match the audio", "invalid_timing")
    return {"metadata": record.get("metadata", {}), "offset": 0, "sections": record.get("sections", []),
            "warnings": record["warnings"], "lines": [{"time": line["start"], "end": line["end"],
            "text": line["text"], "source_line": line["index"] + 1,
            "words": [{"time": word["start"], "end": word["end"], "text": word["text"]} for word in line["words"]]}
            for line in record["lines"]]}
