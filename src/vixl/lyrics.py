"""Lyric videos: a song, a user-timed LRC file and a styled template become a synced MP4/WebM.

Vixl does no audio analysis; every timestamp comes from the LRC file. ``parse_lrc`` reads the
file, ``plan`` turns it into show/hide times, ``build`` writes those times as an ordinary
keyframed timeline onto a copy of the template, and ``export`` renders that document with the
film exporter and the song as its audio track.

Template contract (layer names; only ``lyric`` is required):

``lyric``          text layer showing the current line
``lyric-next``     text layer showing the upcoming line
``section-label``  text layer showing the current section label
``intro``          layer or group visible before the first lyric
``bg-<section>``   visible only during that section (``bg-chorus``); ``bg-default`` otherwise
``cue-<words>``    visible while the current line contains those words (``cue-fire``,
                   ``cue-city-lights``), so lyrics can drive graphics; it can fade, slide or
                   sweep instead of cutting on and off (``cue_animation``)

A built document records the options and sources it was built from (``state["lyric_build"]``), so
``export`` can render a hand-edited build as it is instead of rebuilding it from the template.
"""

from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import re

from .errors import VixlError, require
from .model import Limits, finite

MAX_LINES = 1000
MAX_LINE_CHARS = 500
MAX_SECTIONS = 100
MAX_LRC_BYTES = 1024 * 1024
MAX_VIDEO_MS = 600_000
METADATA = {"ti": "title", "ar": "artist", "al": "album"}
TIMESTAMP = re.compile(r"\[(\d{1,4}):([0-5]?\d)(?:[.:](\d{1,3}))?\]")
TAG = re.compile(r"\[([A-Za-z#][\w#]*):(.*)\]\s*$")
WORD = re.compile(r"<(\d{1,4}):([0-5]?\d)(?:[.:](\d{1,3}))?>")
SECTION = re.compile(r"\[([^\[\]]{1,80})\]")
SLUG = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
ENTRY = ("fade-in", "slide-in-left", "slide-in-right", "slide-in-up", "slide-in-down", "pop-in", "zoom-in", "typewriter", "none")
EXIT = ("fade-out", "slide-out-left", "slide-out-right", "slide-out-up", "slide-out-down", "pop-out", "zoom-out", "none")
SHORT_NAMES = {
    "fade": ("fade-in", "fade-out"),
    "pop": ("pop-in", "pop-out"),
    "zoom": ("zoom-in", "zoom-out"),
    "slide-left": ("slide-in-left", "slide-out-left"),
    "slide-right": ("slide-in-right", "slide-out-right"),
    "slide-up": ("slide-in-up", "slide-out-up"),
    "slide-down": ("slide-in-down", "slide-out-down"),
    "cut": ("none", "none"),
}
CUE_ENTRY = tuple(kind for kind in ENTRY if kind != "typewriter")
CUE_MOTIONS = ("none", "sweep")
RECORD = "lyric_build"  # The document state key that records how a build was made.
REQUEST_FIELDS = {
    "audio", "lyrics", "template", "build", "output", "fps", "quality", "offset", "lead", "gap",
    "max_hold", "animation", "cue_animation", "next_line", "camera", "start", "end", "check", "replace",
    "rebuild", "width", "height", "sample_rate",
}


def _ms(minutes, seconds, fraction):
    fraction = fraction or ""
    return int(minutes) * 60_000 + int(seconds) * 1000 + (int(fraction.ljust(3, "0")) if fraction else 0)


def slug(text):
    """``Verse 2`` → ``verse-2``: lower-cased words joined by hyphens."""
    return "-".join(re.findall(r"[a-z0-9]+", text.lower()))


def parse_lrc(text):
    """Parse standard (and enhanced) LRC text.

    Returns ``{"metadata", "offset", "lines", "sections", "warnings"}``. Lines are sorted by time;
    each is ``{"time", "text", "words", "source_line"}`` with ``text == ""`` for an instrumental
    break. Sections are ``{"time", "label", "name", "source_line"}``."""
    if isinstance(text, bytes):
        require(len(text) <= MAX_LRC_BYTES, "LRC file exceeds 1 MiB", "resource_limit", field="lyrics")
        try:
            text = text.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise VixlError("lrc_parse", "LRC files must be UTF-8", field="lyrics") from exc
    require(isinstance(text, str), "LRC text must be a string", "lrc_parse", field="lyrics")
    require(len(text.encode("utf-8")) <= MAX_LRC_BYTES, "LRC file exceeds 1 MiB", "resource_limit", field="lyrics")
    text = text.lstrip("﻿")
    metadata, warnings, events, offset = {}, [], [], 0
    for number, raw in enumerate(text.replace("\r\n", "\n").replace("\r", "\n").split("\n"), 1):
        line = raw.strip()
        if not line:
            continue
        stamps = []
        while True:
            match = TIMESTAMP.match(line)
            if not match:
                break
            stamps.append(_ms(*match.groups()))
            line = line[match.end():].lstrip()
        if not stamps:
            tag = TAG.match(line)
            if tag and not TIMESTAMP.match(line):
                key, value = tag[1].lower(), tag[2].strip()
                if key in METADATA:
                    metadata[METADATA[key]] = value
                elif key == "offset":
                    require(re.fullmatch(r"[+-]?\d{1,7}", value), f"Line {number}: offset must be whole milliseconds",
                            "lrc_parse", field="lyrics", source_line=number)
                    offset = int(value)
                else:
                    warnings.append({"code": "unknown_tag", "source_line": number,
                                     "message": f"Ignored LRC tag [{tag[1]}:…] on line {number}"})
                continue
            if line.startswith("[") and re.match(r"\[\d", line):
                raise VixlError("lrc_parse", f"Line {number}: malformed timestamp; use [mm:ss.xx] or [mm:ss.xxx]",
                                field="lyrics", source_line=number)
            raise VixlError("lrc_parse", f"Line {number} has text but no timestamp", field="lyrics", source_line=number)
        require(not re.match(r"\[\d", line), f"Line {number}: malformed timestamp; use [mm:ss.xx] or [mm:ss.xxx]",
                "lrc_parse", field="lyrics", source_line=number)
        # Enhanced LRC word tags: kept for later karaoke styling, stripped from the displayed line.
        words, plain, cursor = [], [], 0
        for match in WORD.finditer(line):
            plain.append(line[cursor:match.start()])
            if words:
                words[-1]["text"] += line[cursor:match.start()]
            words.append({"time": _ms(*match.groups()), "text": ""})
            cursor = match.end()
        plain.append(line[cursor:])
        if words:
            words[-1]["text"] += line[cursor:]
        content = re.sub(r"\s+", " ", "".join(plain)).strip()
        require(len(content) <= MAX_LINE_CHARS, f"Line {number} exceeds {MAX_LINE_CHARS} characters",
                "resource_limit", field="lyrics", source_line=number)
        section = SECTION.fullmatch(content)
        for stamp in stamps:
            if section:
                events.append({"kind": "section", "time": stamp, "label": section[1].strip(),
                               "name": slug(section[1]), "source_line": number})
            else:
                events.append({"kind": "line", "time": stamp, "text": content, "source_line": number,
                               "words": [{**w, "text": w["text"].strip()} for w in words if w["text"].strip()]})
    lines = sorted((e for e in events if e["kind"] == "line"), key=lambda e: (e["time"], e["source_line"]))
    sections = sorted((e for e in events if e["kind"] == "section"), key=lambda e: (e["time"], e["source_line"]))
    unique = []
    for line in lines:
        if unique and unique[-1]["time"] == line["time"]:
            require(unique[-1]["text"] == line["text"],
                    f"Lines {unique[-1]['source_line']} and {line['source_line']} give different lyrics at the same time",
                    "lrc_conflict", field="lyrics", source_line=line["source_line"])
            continue
        unique.append(line)
    require(any(line["text"] for line in unique), "The LRC file has no timed lyric lines", "lrc_empty", field="lyrics")
    require(len(unique) <= MAX_LINES, f"At most {MAX_LINES} lyric lines", "resource_limit", field="lyrics")
    require(len(sections) <= MAX_SECTIONS, f"At most {MAX_SECTIONS} sections", "resource_limit", field="lyrics")
    for item in sections:
        require(item["name"], f"Line {item['source_line']}: section label needs letters or digits",
                "lrc_parse", field="lyrics", source_line=item["source_line"])
    return {
        "metadata": metadata,
        "offset": offset,
        "lines": [{k: v for k, v in line.items() if k != "kind"} for line in unique],
        "sections": [{k: v for k, v in item.items() if k != "kind"} for item in sections],
        "warnings": warnings,
    }


def validate_template(project, sections=()):
    """Check a template against the naming contract. Returns ``{"errors", "warnings", "roles"}``;
    errors use the ``template_invalid`` code."""
    errors, warnings, roles = [], [], {"backgrounds": {}, "cues": {}}
    by_name = {layer["name"]: layer for layer in project.state["layers"]}
    lyric = by_name.get("lyric")
    if lyric is None:
        errors.append({"code": "template_invalid", "field": "lyric",
                       "message": "The template needs a text layer named 'lyric'"})
    elif lyric["type"] != "text":
        errors.append({"code": "template_invalid", "field": "lyric",
                       "message": f"'lyric' must be a text layer, not {lyric['type']}"})
    else:
        roles["lyric"] = lyric["id"]
    for name in ("lyric-next", "section-label"):
        layer = by_name.get(name)
        if layer is None:
            continue
        if layer["type"] != "text":
            errors.append({"code": "template_invalid", "field": name,
                           "message": f"{name!r} must be a text layer, not {layer['type']}"})
        else:
            roles[name] = layer["id"]
    if "intro" in by_name:
        roles["intro"] = by_name["intro"]["id"]
    for name, layer in by_name.items():
        for prefix, key in (("bg-", "backgrounds"), ("cue-", "cues")):
            if name.startswith(prefix):
                rest = name[len(prefix):]
                if not SLUG.fullmatch(rest):
                    errors.append({"code": "template_invalid", "field": name,
                                   "message": f"{name!r} must be {prefix}<slug>: lower-case words joined by hyphens"})
                else:
                    roles[key][rest] = layer["id"]
    for section in dict.fromkeys(s["name"] for s in sections):
        if background_for(roles["backgrounds"], section) is None:
            warnings.append({"code": "unmatched_section", "section": section,
                             "message": f"Section {section!r} has no bg-{section} layer and no bg-default exists"})
    return {"errors": errors, "warnings": warnings, "roles": roles}


def background_for(backgrounds, section):
    """The background layer key for a section: an exact match, then the label without a trailing
    number (``verse-2`` → ``bg-verse``), then ``bg-default``."""
    if section:
        if section in backgrounds:
            return section
        base = re.sub(r"-\d+$", "", section)
        if base in backgrounds:
            return base
    return "default" if "default" in backgrounds else None


def _animation(request):
    settings = request.get("animation", {})
    require(isinstance(settings, dict) and not set(settings) - {"in", "out", "duration", "distance"},
            "animation takes in, out, duration and distance", field="animation")
    entry, exit_ = settings.get("in", "fade-in"), settings.get("out", "fade-out")
    entry = SHORT_NAMES.get(entry, (entry,))[0]
    exit_ = SHORT_NAMES.get(exit_, (None, exit_))[1]
    require(entry in ENTRY, f"animation.in must be one of {', '.join(ENTRY)}", field="animation.in", allowed=list(ENTRY))
    require(exit_ in EXIT, f"animation.out must be one of {', '.join(EXIT)}", field="animation.out", allowed=list(EXIT))
    duration = finite(settings.get("duration", 300), "animation.duration", 0, 5000)
    distance = settings.get("distance")
    if distance is not None:
        finite(distance, "animation.distance", 0, 100000)
    return {"in": entry, "out": exit_, "duration": round(duration), "distance": distance}


def _cue_animation(request):
    """How a ``cue-*`` layer enters, leaves and moves while its words are sung. The default is the
    original cut on and off."""
    settings = request.get("cue_animation", {})
    allowed = {"in", "out", "duration", "distance", "motion", "amount", "period"}
    require(isinstance(settings, dict) and not set(settings) - allowed,
            f"cue_animation takes {', '.join(sorted(allowed))}", field="cue_animation")
    entry, exit_ = settings.get("in", "none"), settings.get("out", "none")
    entry = SHORT_NAMES.get(entry, (entry,))[0]
    exit_ = SHORT_NAMES.get(exit_, (None, exit_))[1]
    require(entry in CUE_ENTRY, f"cue_animation.in must be one of {', '.join(CUE_ENTRY)}", field="cue_animation.in", allowed=list(CUE_ENTRY))
    require(exit_ in EXIT, f"cue_animation.out must be one of {', '.join(EXIT)}", field="cue_animation.out", allowed=list(EXIT))
    motion = settings.get("motion", "none")
    require(motion in CUE_MOTIONS, f"cue_animation.motion must be one of {', '.join(CUE_MOTIONS)}", field="cue_animation.motion",
            allowed=list(CUE_MOTIONS))
    distance = settings.get("distance")
    if distance is not None:
        finite(distance, "cue_animation.distance", 0, 100000)
    return {
        "in": entry,
        "out": exit_,
        "duration": round(finite(settings.get("duration", 300), "cue_animation.duration", 0, 5000)),
        "distance": distance,
        "motion": motion,
        "amount": finite(settings.get("amount", 12), "cue_animation.amount", 0, 180),
        "period": round(finite(settings.get("period", 2800), "cue_animation.period", 200, 60000)),
    }


def _number(request, key, default, low, high):
    value = request.get(key, default)
    if value is None:
        return None
    return finite(value, key, low, high)


def timing(parsed, request, duration):
    """Show/hide times (song milliseconds) for each lyric line, plus sections and warnings.

    A line shows ``lead`` ms before its timestamp and hides ``gap`` ms before the next line shows
    (or at an empty-text break, after ``max_hold``, or at the end of the video)."""
    lead = _number(request, "lead", 150, 0, 10000)
    gap = _number(request, "gap", 0, 0, 10000)
    max_hold = _number(request, "max_hold", 8000, 100, MAX_VIDEO_MS)
    offset = parsed["offset"] + _number(request, "offset", 0, -MAX_VIDEO_MS, MAX_VIDEO_MS)
    start = round(_number(request, "start", 0, 0, MAX_VIDEO_MS))
    end = request.get("end")
    end = duration if end is None else round(finite(end, "end", 1, MAX_VIDEO_MS))
    require(end <= duration, f"end ({end} ms) is after the end of the audio ({duration} ms)", field="end")
    require(start < end, "start must be before end", field="start")
    animation = _animation(request)
    cue = _cue_animation(request)
    warnings = list(parsed["warnings"])
    events = [{**line, "time": max(0, line["time"] - offset)} for line in parsed["lines"]]
    for line in events:
        if line["time"] >= duration:
            raise VixlError("lyrics_beyond_audio",
                            f"Line {line['source_line']} starts at {line['time']} ms, after the end of the audio "
                            f"({duration} ms)", field="lyrics", source_line=line["source_line"])
    sections = []
    for item in parsed["sections"]:
        time = max(0, item["time"] - offset)
        if time >= duration:
            raise VixlError("lyrics_beyond_audio", f"Section on line {item['source_line']} starts after the end of the audio",
                            field="lyrics", source_line=item["source_line"])
        sections.append({**item, "time": time})
    for item in sections:
        item["start"] = item.pop("time")
    for i, item in enumerate(sections):
        item["end"] = sections[i + 1]["start"] if i + 1 < len(sections) else max(item["start"], end)

    def section_at(time):
        current = None
        for item in sections:
            if item["start"] <= time:
                current = item["name"]
        return current

    lines, previous_hide, carried = [], 0, False
    for i, line in enumerate(events):
        if not line["text"]:
            continue
        nxt = events[i + 1] if i + 1 < len(events) else None
        show = line["time"] - lead
        if show < previous_hide:
            if line["time"] - lead >= 0 and lead:
                warnings.append({"code": "lead_clamped", "index": len(lines),
                                 "message": f"Line {len(lines)} would overlap the previous line, so it shows "
                                            f"{previous_hide - show} ms later than lead asks"})
            show = previous_hide
        show = max(0, show)
        candidates = [line["time"] + max_hold, end]
        follow = None
        if nxt is not None:
            # The next line shows ``lead`` early; an empty-text break hides at its own timestamp.
            follow = (nxt["time"] - lead if nxt["text"] else nxt["time"]) - gap
            candidates.append(follow)
        hide = min(candidates)
        handed_on = follow is not None and hide == follow  # The next line, not max_hold or the end, ends this one.
        if hide <= show:
            hide = min(show + max(1, round(1000 / 60)), max(end, show + 1))
        item = {
            "index": len(lines),
            "text": line["text"],
            "start": line["time"],
            "show": round(show),
            "hide": round(hide),
            "section": section_at(line["time"]),
            "source_line": line["source_line"],
            **({"words": line["words"]} if line["words"] else {}),
        }
        if carried:
            # Sung again straight after itself: the line stays up, with no exit and no new entry.
            item["repeat"] = True
            lines[-1]["hide"] = max(lines[-1]["hide"], item["show"])
        if nxt is not None and not nxt["text"] and nxt["time"] - gap < end:
            item["break_at"] = round(max(hide, nxt["time"] - gap))  # An empty timestamp follows: the screen clears here.
        lines.append(item)
        carried = handed_on and nxt["text"] == line["text"]
        previous_hide = hide
    for i, item in enumerate(lines):
        span = item["hide"] - item["show"]
        entering, leaving = not item.get("repeat"), not (i + 1 < len(lines) and lines[i + 1].get("repeat"))
        needed = (animation["duration"] if entering and animation["in"] != "none" else 0) + (
            animation["duration"] if leaving and animation["out"] != "none" else 0)
        if needed and span < needed:
            warnings.append({"code": "short_line", "index": item["index"],
                             "message": f"Line {item['index']} is shown for {span} ms; shorter than its in+out "
                                        f"animation ({needed} ms), so both were shortened"})
    return {
        "start": start,
        "end": end,
        "lead": lead,
        "gap": gap,
        "max_hold": max_hold,
        "offset": offset,
        "animation": animation,
        "cue_animation": cue,
        "lines": lines,
        "sections": sections,
        "warnings": warnings,
    }


def _inputs(request, root, limits):
    from .assets import read_bounded
    from .film import audio_duration, local_path
    from .project import Project

    from .automation import bounded_object

    bounded_object(request, REQUEST_FIELDS, "Unknown lyric-video request field")
    for key in ("audio", "lyrics", "template"):
        require(isinstance(request.get(key), str) and request[key], f"Lyric videos need {key}", field=key)
    paths = {key: local_path(root, request[key]) for key in ("audio", "lyrics", "template")}
    for key, path in paths.items():
        require(path.is_file(), f"{request[key]!r} does not exist in the workspace", "missing_file", field=key)
    require(paths["template"].suffix == ".vixl", "template must be a .vixl document", field="template")
    parsed = parse_lrc(read_bounded(paths["lyrics"], MAX_LRC_BYTES))
    template = Project.load(paths["template"], limits=limits)
    duration = audio_duration(paths["audio"])
    require(duration <= MAX_VIDEO_MS, "Audio is longer than the 10 minute video limit; pass end to render part of it",
            "resource_limit", field="audio")
    return paths, parsed, template, duration


def _settings(request, template):
    fps = request.get("fps", 24)
    require(isinstance(fps, (int, float)) and not isinstance(fps, bool) and 1 <= fps <= 60, "fps must be 1–60", field="fps")
    quality = request.get("quality", "final")
    require(quality in ("draft", "final"), "quality must be draft or final", field="quality")
    canvas = template.state["canvas"]
    width, height = request.get("width", canvas["width"]), request.get("height", canvas["height"])
    for key, value in (("width", width), ("height", height)):
        require(isinstance(value, int) and 16 <= value <= 4096, f"{key} must be 16–4096 pixels", field=key)
    for key in ("next_line", "check", "rebuild"):
        require(isinstance(request.get(key, True), bool), f"{key} must be true or false", field=key)
    from .audio import check_rate
    check_rate(request.get("sample_rate"))
    camera = request.get("camera")
    if camera is not None:
        require(isinstance(camera, dict) and set(camera) <= {"from", "to"}, "camera takes from and to poses", field="camera")
        for pose in camera.values():
            require(isinstance(pose, list) and len(pose) == 3, "Camera poses are [center-x, center-y, zoom]", field="camera")
            finite(pose[0], "camera x", 0, 1)
            finite(pose[1], "camera y", 0, 1)
            finite(pose[2], "camera zoom", 1, 16)
    return {"fps": fps, "quality": quality, "width": width, "height": height}


def plan(request, root, limits=None):
    """Parse and validate without writing anything: the timed lines, sections, frame count and
    warnings for a request."""
    return _prepare(request, root, limits)[0]


def _prepare(request, root, limits=None):
    limits = limits or Limits()
    paths, parsed, template, duration = _inputs(request, root, limits)
    settings = _settings(request, template)
    timed = timing(parsed, request, duration)
    contract = validate_template(template, timed["sections"])
    if contract["errors"]:
        first = contract["errors"][0]
        raise VixlError("template_invalid", first["message"], field=first["field"], errors=contract["errors"])
    warnings = timed["warnings"] + contract["warnings"]
    canvas = template.state["canvas"]
    if canvas["width"] * settings["height"] != canvas["height"] * settings["width"]:
        warnings.append({"code": "size_mismatch",
                         "message": f"The template is {canvas['width']}×{canvas['height']} but the video is "
                                    f"{settings['width']}×{settings['height']}; frames are cropped from the centre"})
    length = timed["end"] - timed["start"]
    frames = max(1, math.ceil(length * settings["fps"] / 1000))
    shown = [line for line in timed["lines"] if line["hide"] > timed["start"] and line["show"] < timed["end"]]
    report = {
        "duration_ms": length,
        "audio_ms": duration,
        "start": timed["start"],
        "end": timed["end"],
        "fps": settings["fps"],
        "frames": frames,
        "width": settings["width"],
        "height": settings["height"],
        "metadata": parsed["metadata"],
        "sections": [{"name": s["name"], "label": s["label"], "start": s["start"], "end": s["end"]} for s in timed["sections"]],
        "lines": timed["lines"],
        "lines_in_window": len(shown),
        "template": {k: v for k, v in contract["roles"].items() if v},
        "warnings": warnings,
    }
    sources = {"lyrics": hashlib.sha256(paths["lyrics"].read_bytes()).hexdigest(), "template": template._revision,
               "audio_ms": duration}
    return report, parsed, template, timed, contract, sources


# ---------------------------------------------------------------------------------------------
# Build




def _entry_keys(kind, show, length, base, distance):
    """Keyframes {property: [(time, value, easing)]} for an entry animation starting at ``show``.
    The settled values hold until the exit starts (or, for a cut, until the line hides)."""
    end = show + length
    if kind == "none" or length <= 0:
        return {"opacity": [(show, base, "hold")]}
    keys = {"opacity": [(show, 0.0, "ease-out"), (end, base, "hold")]}
    if kind.startswith("slide-in"):
        direction = kind.rsplit("-", 1)[1]
        axis = "translate-x" if direction in ("left", "right") else "translate-y"
        # slide-in-left enters from the left; slide-in-up rises from below (the preset convention).
        sign = {"left": -1, "right": 1, "up": 1, "down": -1}[direction]
        keys[axis] = [(show, float(sign * distance), "ease-out-cubic"), (end, 0.0, "hold")]
    elif kind == "pop-in":
        keys["scale"] = [(show, 0.6, "ease-out-back"), (end, 1.0, "hold")]
    elif kind == "zoom-in":
        keys["scale"] = [(show, 0.85, "ease-out"), (end, 1.0, "hold")]
    return keys


def _exit_keys(kind, hide, length, base, distance):
    """Keyframes for an exit animation that ends at ``hide``. The last keys hold until the next
    line's entry, so nothing drifts while the lyric is hidden."""
    start = hide - length
    if kind == "none" or length <= 0:
        return {"opacity": [(hide, 0.0, "hold")]}
    keys = {"opacity": [(start, base, "ease-in"), (hide, 0.0, "hold")]}
    if kind.startswith("slide-out"):
        direction = kind.rsplit("-", 1)[1]
        axis = "translate-x" if direction in ("left", "right") else "translate-y"
        sign = {"left": -1, "right": 1, "up": -1, "down": 1}[direction]
        keys[axis] = [(start, 0.0, "ease-in-cubic"), (hide, float(sign * distance), "hold")]
    elif kind == "pop-out":
        keys["scale"] = [(start, 1.0, "ease-in-back"), (hide, 0.6, "hold")]
    elif kind == "zoom-out":
        keys["scale"] = [(start, 1.0, "ease-in"), (hide, 1.15, "hold")]
    return keys


def contains_phrase(text, phrase):
    """Whether ``text`` contains the hyphen-joined words of ``phrase`` as whole words."""
    words = re.findall(r"[a-z0-9]+", text.lower())
    target = phrase.split("-")
    return any(words[i:i + len(target)] == target for i in range(len(words) - len(target) + 1))


def cue_keys(key, layer, ident, start, end, cue, canvas):
    """Animate one cue layer over a window in which its words are on screen: an entry and exit
    (fade, slide, pop, zoom) and a continuous ``sweep`` (a swing about the layer's pivot, so a
    lighthouse beam turns instead of popping on and off). The default cuts, with no extra keys."""
    span = end - start
    if span <= 0 or (cue["in"] == "none" and cue["out"] == "none" and cue["motion"] == "none"):
        return
    base = layer["opacity"]
    distance = cue["distance"]
    entry_length = cue["duration"] if cue["in"] != "none" else 0
    exit_length = cue["duration"] if cue["out"] != "none" else 0
    if entry_length + exit_length > span:
        ratio = span / (entry_length + exit_length)
        entry_length, exit_length = int(entry_length * ratio), int(exit_length * ratio)

    def reach(kind):
        horizontal = kind.endswith(("left", "right"))
        if distance is not None:
            return distance
        return round(canvas["width" if horizontal else "height"] * 0.06)

    if cue["in"] != "none" or cue["out"] != "none":
        rest = {"opacity": base, "translate-x": 0.0, "translate-y": 0.0, "scale": 1.0}
        entry = _entry_keys(cue["in"], start, entry_length, base, reach(cue["in"]))
        leaving = _exit_keys(cue["out"], end, exit_length, base, reach(cue["out"])) if cue["out"] != "none" else {}
        # A cue shown again starts from rest, whatever the last exit left it at.
        for prop in (set(_entry_keys(cue["in"], 0, 1000, base, 1)) | set(_exit_keys(cue["out"], 1000, 1000, base, 1))) - set(entry):
            entry[prop] = [(start, rest[prop], "hold")]
        for keys in (entry, leaving):
            for prop, values in keys.items():
                for time, value, easing in values:
                    key(ident, prop, time, value, easing)
    if cue["motion"] == "sweep":
        from .timeline import easing_function

        ease = easing_function("ease-in-out-sine")
        angle, half, centre, swing = 0, cue["period"] / 2, layer.get("rotation", 0), cue["amount"]
        while True:
            time, value = start + angle * half, centre + (-swing if angle % 2 == 0 else swing)
            if time + half >= end:
                # The window ends partway through a swing: the last key is where that swing has got to.
                far = centre + (swing if angle % 2 == 0 else -swing)
                key(ident, "rotation", time, value, "ease-in-out-sine")
                key(ident, "rotation", end, value + (far - value) * ease((end - time) / half))
                break
            key(ident, "rotation", time, value, "ease-in-out-sine")
            angle += 1


def write_timeline(project, timed, roles, request):
    """Replace ``project``'s timeline (a template copy) with the lyric timeline. Returns the
    number of keyframes written."""
    from .timeline import MAX_DURATION, MAX_KEYS, MAX_TRACKS, default_timeline

    state = project.state
    canvas = state["canvas"]
    layers = {layer["id"]: layer for layer in state["layers"]}
    animation = timed["animation"]
    lines = timed["lines"]
    tracks = {}

    def key(target, prop, time, value, easing=None):
        entry = {"time": int(round(time)), "value": value}
        if easing and easing != "linear":
            entry["easing"] = easing
        # A later key at the same time replaces an earlier one, as keyframe does.
        tracks.setdefault((target, prop), {})[entry["time"]] = entry

    lyric = roles["lyric"]
    base = layers[lyric]["opacity"]
    key(lyric, "text", 0, "")
    key(lyric, "opacity", 0, 0.0, "hold")
    distance_x = animation["distance"] if animation["distance"] is not None else round(canvas["width"] * 0.06)
    distance_y = animation["distance"] if animation["distance"] is not None else round(canvas["height"] * 0.06)
    steps_budget = max(1, (MAX_KEYS - 2) // max(1, len(lines)) - 1)
    rest = {"opacity": base, "translate-x": 0.0, "translate-y": 0.0, "scale": 1.0}
    # What the entry and exit move. Every entry puts back whatever it does not set itself, so a cut
    # after a slide-out does not start where the last line left off.
    moved = set(_entry_keys(animation["in"], 0, 1000, base, 1)) | set(_exit_keys(animation["out"], 1000, 1000, base, 1))
    plans = []
    for i, line in enumerate(lines):
        show, hide = line["show"], line["hide"]
        span = hide - show
        # A line repeated straight after itself holds on screen: no exit before it, no entry for it.
        entering = not line.get("repeat")
        leaving = not (i + 1 < len(lines) and lines[i + 1].get("repeat"))
        entry_length = animation["duration"] if entering and animation["in"] != "none" else 0
        exit_length = animation["duration"] if leaving and animation["out"] != "none" else 0
        if entry_length + exit_length > span:
            ratio = span / (entry_length + exit_length)
            entry_length, exit_length = int(entry_length * ratio), int(exit_length * ratio)
        following = lines[i + 1]["show"] if i + 1 < len(lines) else None
        # An exit that ends where the next entry starts finishes 1 ms early, so the exit's end
        # value and the entry's start value are separate keys.
        exit_end = min(hide, following - 1) if following is not None and following <= hide else hide
        exit_end = max(exit_end, show + entry_length)
        plans.append((entering, leaving, entry_length, exit_length, exit_end))
    for i, line in enumerate(lines):
        show = line["show"]
        entering, leaving, entry_length, exit_length, exit_end = plans[i]
        keys_here = []
        if entering:
            if animation["in"] == "typewriter":
                text = line["text"]
                steps = max(1, min(len(text), steps_budget, 24))
                for step in range(steps + 1):
                    key(lyric, "text", show + entry_length * step / steps, text[: round(len(text) * step / steps)])
                entry = {"opacity": [(show, base, "hold")]}
            else:
                key(lyric, "text", show, line["text"])
                distance = distance_x if animation["in"].endswith(("left", "right")) else distance_y
                entry = _entry_keys(animation["in"], show, entry_length, base, distance)
            for prop in moved - set(entry):
                entry[prop] = [(show, rest[prop], "hold")]
            keys_here.append(entry)
        if leaving:
            distance = distance_x if animation["out"].endswith(("left", "right")) else distance_y
            keys_here.append(_exit_keys(animation["out"], exit_end, min(exit_length, exit_end - show - entry_length), base, distance))
        for keys in keys_here:
            for prop, values in keys.items():
                for time, value, easing in values:
                    key(lyric, prop, time, value, easing)
    for prop in ("translate-x", "translate-y", "scale"):
        if (lyric, prop) in tracks and 0 not in tracks[(lyric, prop)]:
            key(lyric, prop, 0, 1.0 if prop == "scale" else 0.0, "hold")
    upcoming = roles.get("lyric-next")
    if upcoming:
        if request.get("next_line", True):
            key(upcoming, "text", 0, "")
            for i, line in enumerate(lines):
                key(upcoming, "text", line["show"], lines[i + 1]["text"] if i + 1 < len(lines) else "")
            base_next = layers[upcoming]["opacity"]
            for i, line in enumerate(lines[:-1]):
                at, following = line.get("break_at"), lines[i + 1]
                if at is None or at >= following["show"]:
                    continue
                # An empty timestamp clears the preview too, until the line after the break shows.
                key(upcoming, "text", at, "")
                fade_in = plans[i + 1][2]
                if animation["out"] != "none" or animation["in"] != "none":
                    # The preview leaves with the lyric's exit and returns with the next entry.
                    fade_out = animation["duration"] if animation["out"] != "none" else 0
                    if fade_out:
                        key(upcoming, "opacity", max(line["show"], at - fade_out), base_next, "ease-in")
                    key(upcoming, "opacity", at, 0.0, "hold")
                    if fade_in:
                        key(upcoming, "opacity", following["show"], 0.0, "ease-out")
                        key(upcoming, "opacity", following["show"] + fade_in, base_next, "hold")
                    else:
                        key(upcoming, "opacity", following["show"], base_next, "hold")
            key(upcoming, "visible", 0, True)
        else:
            key(upcoming, "visible", 0, False)
    label = roles.get("section-label")
    if label:
        key(label, "text", 0, "")
        for item in timed["sections"]:
            key(label, "text", item["start"], item["label"])
    backgrounds = roles["backgrounds"]
    if backgrounds:
        for time, section in [(0, None)] + [(item["start"], item["name"]) for item in timed["sections"]]:
            chosen = background_for(backgrounds, section)
            for name, ident in backgrounds.items():
                key(ident, "visible", time, name == chosen)
    intro = roles.get("intro")
    if intro and lines:
        key(intro, "visible", 0, True)
        key(intro, "visible", lines[0]["show"], False)
    for phrase, ident in roles["cues"].items():
        key(ident, "visible", 0, False)
        windows = []
        for line in lines:
            if contains_phrase(line["text"], phrase):
                # Consecutive matching lines are one window, so the cue does not blink between them.
                if windows and line["show"] <= windows[-1][1]:
                    windows[-1][1] = max(windows[-1][1], line["hide"])
                else:
                    windows.append([line["show"], line["hide"]])
        for window_start, window_end in windows:
            key(ident, "visible", window_start, True)
            key(ident, "visible", window_end, False)
            cue_keys(key, layers[ident], ident, window_start, window_end, timed["cue_animation"], canvas)
    require(len(tracks) <= MAX_TRACKS, "Too many animated template layers", "resource_limit")
    timeline = default_timeline()
    timeline.update(fps=request.get("fps", 24), loop=0)
    for (target, prop), keys in tracks.items():
        require(len(keys) <= MAX_KEYS, f"The lyric timeline needs more than {MAX_KEYS} keys on one track; "
                "use fewer lines or a simpler animation", "resource_limit")
        timeline["tracks"].append({"target": target, "property": prop, "keys": [keys[t] for t in sorted(keys)]})
    last = max(k["time"] for t in timeline["tracks"] for k in t["keys"])
    timeline["duration"] = max(10, min(MAX_DURATION, max(timed["end"], last)))
    counts = {}
    for item in timed["sections"]:
        counts[item["name"]] = counts.get(item["name"], 0) + 1
        timeline["markers"][f"{item['name'][:90]}-{counts[item['name']]}"] = item["start"]
    for line in lines:
        timeline["markers"][f"line-{line['index'] + 1:03d}"] = line["show"]
    state["timeline"] = timeline
    return sum(len(track["keys"]) for track in timeline["tracks"])


def _build_options(request, timed):
    """What shapes the built timeline. Rendering choices (quality, size, camera, the window start)
    are not part of it."""
    return {
        "fps": request.get("fps", 24),
        "offset": timed["offset"],
        "lead": timed["lead"],
        "gap": timed["gap"],
        "max_hold": timed["max_hold"],
        "animation": timed["animation"],
        "cue_animation": timed["cue_animation"],
        "next_line": request.get("next_line", True),
        "end": None if request.get("end") is None else timed["end"],
    }


def _fingerprint(state):
    """A hash of everything in a built document except its build record, to tell a document that
    still is what the build wrote from one that has been edited since."""
    body = {key: value for key, value in state.items() if key != RECORD}
    return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def build(request, root, limits=None):
    """Write the timeline document to ``build`` and return the plan plus its path."""
    from .film import local_path

    limits = limits or Limits()
    root = Path(root)
    require(isinstance(request.get("build"), str) and request["build"].endswith(".vixl"),
            "build must be a .vixl path", field="build")
    destination = local_path(root, request["build"])
    _may_replace(request, destination)
    return _write_build(request, root, limits, _prepare(request, root, limits), destination)


def _may_replace(request, destination):
    require(request.get("replace", False) or request.get("rebuild", False) or not destination.exists(),
            f"{request['build']!r} already exists; choose a new path or pass replace: true (rebuild: true also works)",
            field="build")


def _write_build(request, root, limits, prepared, destination):
    from .film import local_path
    from .validation import check_state

    report, parsed, template, timed, contract, sources = prepared
    require(destination != local_path(root, request["template"]), "build cannot overwrite the template", field="build")
    project = template.clone()
    project.path, project._revision = None, None
    variables = project.state["variables"]
    for name in ("title", "artist", "album"):
        if name in parsed["metadata"]:
            variables[name] = parsed["metadata"][name]
        else:
            variables.setdefault(name, "")
    keys = write_timeline(project, timed, contract["roles"], request)
    project.state[RECORD] = {"version": 1, "options": _build_options(request, timed), "sources": sources,
                             "state": _fingerprint(project.state)}
    check_state(project, project.state)
    project._record([], f"Build lyric video from {Path(request['lyrics']).name}")
    if destination.exists():
        destination.unlink()
    project.save(destination)
    return {**report, "build": request["build"], "keyframes": keys}


def _differences(record, options, sources):
    """How a build's recorded settings and sources differ from what a request now asks for."""
    recorded = record.get("options") or {}
    changed = [name for name, value in options.items() if name != "end" and recorded.get(name) != value]
    # A build made for a window (end) does not cover a longer render; a full build covers any window.
    built_end = recorded.get("end")
    if built_end is not None and (options["end"] is None or options["end"] > built_end):
        changed.append("end")
    for name in ("lyrics", "template"):
        if (record.get("sources") or {}).get(name) != sources[name]:
            changed.append(f"the {name} file")
    if (record.get("sources") or {}).get("audio_ms") != sources["audio_ms"]:
        changed.append("the audio length")
    return changed


def _kept_build(request, limits, prepared, destination):
    """The report for rendering an existing build as it is (hand edits and all), ``None`` when it
    should be built again (a legacy file, or settings that changed on an unedited build; the
    caller then checks that it may replace the file), or a ``build_stale`` error when the build
    has hand edits that a rebuild would discard."""
    from .project import Project

    report, _, _, timed, _, sources = prepared
    try:
        existing = Project.load(destination, limits=limits)
    except (VixlError, OSError, ValueError, KeyError):
        return None
    record = existing.state.get(RECORD)
    if not isinstance(record, dict) or record.get("version") != 1:
        return None
    changed = _differences(record, _build_options(request, timed), sources)
    edited = _fingerprint(existing.state) != record.get("state")
    if changed:
        if edited:
            raise VixlError(
                "build_stale",
                f"{request['build']!r} has hand edits and was built with different inputs ({', '.join(changed)}); "
                "rendering it as it is would ignore the new ones. Pass rebuild: true to build it again (this discards the "
                "edits), choose a new build path, or restore the earlier settings",
                field="build", changed=changed)
        return None
    keyframes = sum(len(track["keys"]) for track in (existing.state.get("timeline") or {}).get("tracks", []))
    warnings = list(report["warnings"])
    if edited:
        warnings.append({"code": "build_reused", "message": f"Rendered {request['build']!r} as it is, with its hand edits; "
                         "pass rebuild: true to build it again from the template"})
    return {**report, "build": request["build"], "keyframes": keyframes, "build_reused": True, "warnings": warnings}


def film_spec(request, report):
    """The single-shot film spec that renders a built lyric document with the song."""
    shot = {"source": request["build"], "duration": max(10, report["end"] - report["start"]), "trim": report["start"]}
    if request.get("camera"):
        shot["camera"] = deepcopy(request["camera"])
    return {
        "version": 1,
        "width": report["width"],
        "height": report["height"],
        "fps": report["fps"],
        "quality": request.get("quality", "final"),
        "shots": [shot],
        "audio": [{"source": request["audio"], "start": 0, "trim": report["start"], "volume": 1}],
        **({"sample_rate": request["sample_rate"]} if request.get("sample_rate") is not None else {}),
    }


def check_lines(project, report, settle=300, limit=200):
    """Design checks on one frame per unique line, once its entry animation has finished."""
    from .timeline import project_at

    findings, seen = [], set()
    for line in report["lines"]:
        if line["text"] in seen or len(seen) >= limit or line["hide"] <= report["start"] or line["show"] >= report["end"]:
            continue
        seen.add(line["text"])
        time = max(line["show"], min(line["hide"] - 1, line["show"] + settle))
        result = project_at(project, time).check(checks=["bounds", "overlap", "contrast", "safe_area", "blanks"])
        if result["issues"]:
            findings.append({"line": line["index"], "time": time, "text": line["text"][:80],
                             "passed": result["passed"], "issues": result["issues"]})
    return {"passed": all(item["passed"] for item in findings), "checked_lines": len(seen), "lines": findings}


def export(request, root, limits=None, *, cancelled=lambda: False, progress=lambda value: None):
    """Build, then render the MP4/WebM with the song as its audio track. A build that already exists
    and still matches the request is rendered as it is, hand edits included (``build_reused``)."""
    from .film import export as film_export, local_path
    from .project import Project

    limits = limits or Limits()
    root = Path(root)
    require(isinstance(request.get("output"), str) and Path(request["output"]).suffix.lower() in (".mp4", ".webm"),
            "output must be an .mp4 or .webm path", field="output")
    output = local_path(root, request["output"])
    require(request.get("replace", False) or not output.exists(),
            f"{request['output']!r} already exists; choose a new path or pass replace: true", field="output")
    require(isinstance(request.get("build"), str) and request["build"].endswith(".vixl"),
            "build must be a .vixl path", field="build")
    destination = local_path(root, request["build"])
    prepared = _prepare(request, root, limits)
    # A build that exists is rendered as it is when it still matches the request, so edits made to
    # it survive; ``rebuild`` builds it again from the template.
    report = None
    if destination.exists() and not request.get("rebuild"):
        report = _kept_build(request, limits, prepared, destination)
    if report is None:
        _may_replace(request, destination)
        report = _write_build(request, root, limits, prepared, destination)
    if output.exists():
        output.unlink()
    result = film_export(film_spec(request, report), root, output, limits=limits, cancelled=cancelled, progress=progress)
    response = {**report, "output": request["output"], "video": result}
    if request.get("check"):
        project = Project.load(local_path(root, request["build"]), limits=limits)
        response["checks"] = check_lines(project, report, _animation(request)["duration"])
    return response
