"""Bounded lyric delivery checks and explicit review of an editable build."""

from copy import deepcopy
import hashlib
import math

from ...errors import VixlError, require
from ...hashing import content_hash
from ... import outcomes

MAX_SAMPLES = 400


def _signature(project):
    from .lyrics import RECORD, _fingerprint

    return content_hash({"state": _fingerprint(project.state),
                         "sources": (project.state.get(RECORD) or {}).get("sources"),
                         "assets": {name: hashlib.sha256(data).hexdigest()
                                    for name, data in sorted(project.assets.items())}})


def review(request, root, limits=None):
    """Record a person's decision, tied to this build's content; never run implicitly on export."""
    from ...project import Project
    from ..film.film import file_sha256, local_path
    from .lyrics import RECORD

    require(isinstance(request.get("build"), str), "review needs a build path", field="build")
    approve, changes = request.get("approve", False), request.get("changes_requested", False)
    require(type(approve) is bool and type(changes) is bool and approve != changes,
            "Choose approve or changes_requested", field="approve")
    findings = request.get("findings", [])
    require(isinstance(findings, list) and len(findings) <= 100 and
            all(isinstance(item, str) and len(item) <= 2000 for item in findings),
            "findings must be at most 100 short strings", field="findings")
    path = local_path(root, request["build"])
    project = Project.load(path, limits=limits)
    require(isinstance(project.state.get(RECORD), dict), "The document has no lyric build record", field="build")
    record = project.state[RECORD]
    paths = record.get("source_paths") or {}
    require({"audio", "lyrics"} <= paths.keys(), "Rebuild before review to record the audio and lyric source identities",
            field="build")
    source_hashes = {name: file_sha256(local_path(root, paths[name])) for name in ("audio", "lyrics")}
    require(all(source_hashes[name] == (record.get("sources") or {}).get(name) for name in source_hashes),
            "The audio or lyrics changed after this build; rebuild before review", "build_stale", field="build")
    decision = {"status": "approved" if approve else "changes_requested", "findings": findings,
                "signature": _signature(project), "sources": source_hashes, "scope": "build"}
    project.state[RECORD]["review"] = decision
    project._record([], "Review lyric video build")
    project.save(path)
    return {"build": request["build"], "review": deepcopy(decision), "validated": False,
            "outcome": outcomes.make(reasons=["export with full verification to validate delivery"])}


def _review(project, sources=None):
    from .lyrics import RECORD

    record = project.state.get(RECORD) or {}
    decision = record.get("review") or {}
    same_sources = not sources or all(sources.get(name) == digest for name, digest in decision.get("sources", {}).items())
    if (same_sources and decision.get("signature") == _signature(project)
            and decision.get("status") in ("approved", "changes_requested")):
        return {key: deepcopy(decision[key]) for key in ("status", "findings", "scope")}
    return {"status": "pending", "findings": [], "scope": "build",
            **({"reason": "The build or its sources changed after review"} if decision else {})}


def _finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def _coverage(times, start, end, fps):
    intervals = []
    for time in sorted(set(times)):
        begin, finish = max(start, time), min(end, time + 1000 / fps)
        if finish <= begin:
            continue
        if intervals and begin <= intervals[-1][1]:
            intervals[-1][1] = max(finish, intervals[-1][1])
        else:
            intervals.append([begin, finish])
    unsampled, cursor = [], start
    for begin, finish in intervals:
        if begin > cursor:
            unsampled.append([round(cursor, 3), round(begin, 3)])
        cursor = finish
    if cursor < end:
        unsampled.append([round(cursor, 3), round(end, 3)])
    return {"checked_ms": round(sum(b - a for a, b in intervals), 3),
            "sampled_ms": sorted(set(times)), "unsampled_intervals": unsampled}


def _visible(frame, layer):
    layers = {item["id"]: item for item in frame.state["layers"]}
    seen = set()
    while layer:
        if not layer.get("visible", True) or layer.get("opacity", 1) <= 0 or layer["id"] in seen:
            return False
        seen.add(layer["id"])
        layer = layers.get(layer.get("parent"))
    return True


def verify(report, project, *, mode="basic", media=None, sources=None):
    """Check each occurrence's timing/text and, in full mode, up to four frames per cue.

    Pixel checks cover the sampled source frames, not every frame or the encoded film's appearance.
    Only an explicit current build review and successful full checks can validate a delivery.
    """
    from ...timeline import project_at
    from ...render import document_variables
    from ...variables import substitute
    from .lyrics import RECORD, line_plans, section_match

    require(mode in ("basic", "full"), "verify must be basic or full", field="verify")
    media = media if media is not None else report.get("verification", {})
    lines = report.get("lines", [])
    start, end = report.get("start", 0), report.get("end", 0)
    duration = (project.state.get("timeline") or {}).get("duration", 0)
    animation = ((project.state.get(RECORD) or {}).get("options") or {}).get("animation") or {
        "in": "fade-in", "out": "fade-out", "duration": 300}
    roles = report.get("template", {})
    structural, samples, visual, brand = [], [], [], []
    if sources:
        structural.append({"check": "source_identity", "changed": sources.get("changed_during_export", []),
                           "passed": not sources.get("changed_during_export")})
    valid = []
    previous_show = previous_hide = -1
    for line in lines:
        show, hide = line.get("show"), line.get("hide")
        passed = (_finite(show) and _finite(hide) and 0 <= show < hide <= duration and
                  show >= previous_show and hide >= previous_hide)
        structural.append({"check": "cue_timing", "line": line.get("index"), "show": show, "hide": hide,
                           "duration": duration, "passed": passed})
        if passed:
            valid.append(line)
        if _finite(show) and _finite(hide):
            previous_show, previous_hide = show, hide
    plans = line_plans(valid, animation)
    for line, plan in zip(valid, plans):
        show, hide = line["show"], line["hide"]
        if hide <= start or show >= end:
            continue
        settled = min(hide - 1, line.get("settled", show + plan[2]))
        if animation.get("unit") == "word":
            settled = min(hide - 1, max([settled, *(word["time"] for word in line.get("words", []))]))
        at = max(show, min(hide - 1, settled))
        chosen = section_match(roles.get("lyrics", {}), line.get("section"))
        ident = roles.get("lyrics", {}).get(chosen, roles.get("lyric"))
        composition = line.get("composition") or {}
        expected = composition.get("text", line["text"])
        actual, visible, error = None, False, None
        try:
            frame = project_at(project, at)
            layers = {item["id"]: item for item in frame.state["layers"]}
            selected = [layers.get(target) for target in composition.get("text_layers", [ident])]
            if selected and all(selected):
                variables = document_variables(frame)
                values = [substitute(layer.get("text", ""), variables) for layer in selected]
                actual = " ".join(value.strip() for value in values) if composition else values[0]
                visible = all(_visible(frame, layer) for layer in selected)
        except VixlError as exc:
            error = exc.code
        structural.append({"check": "cue_text", "line": line.get("index"), "time": at,
                           "expected": expected, "actual": actual, "visible": visible,
                           "passed": actual == expected and visible, **({"error": error} if error else {})})
        if mode == "full":
            for when in dict.fromkeys((show, (show + at) / 2, at, min(hide - 1, plan[4] - 1))):
                when = max(start, min(end - 1, when))
                if len(samples) >= MAX_SAMPLES:
                    break
                samples.append({"line": line.get("index"), "time": when})
    for sample in samples:
        try:
            frame = project_at(project, sample["time"])
            findings = frame.check(checks=["bounds", "overlap", "contrast", "safe_area", "blanks", "brand"])
            branded = [issue for issue in findings["issues"] if issue.get("check") == "brand"]
            other = [issue for issue in findings["issues"] if issue.get("check") != "brand"]
            visual.append({**sample, "issues": other, "outcome": outcomes.from_findings(other)})
            brand.append({**sample, "issues": branded, "outcome": outcomes.from_findings(branded)})
        except VixlError as exc:
            visual.append({**sample, "issues": [{"check": "render", "action": "fix", "code": exc.code}],
                           "outcome": outcomes.make(validation="failed")})
    coverage = _coverage([sample["time"] for sample in samples], start, end, report.get("fps", 24))
    structural_passed = bool(structural) and all(item["passed"] for item in structural)
    visual_passed = bool(visual) and all(item["outcome"]["validation"] == "passed" for item in visual)
    brand_passed = bool(brand) and all(item["outcome"]["validation"] == "passed" for item in brand)
    decision = _review(project, sources)
    unreviewed = []
    if mode != "full":
        unreviewed.extend(["full decode", "visual and brand frame sampling"])
    if len(samples) == MAX_SAMPLES and len(valid) * 4 > MAX_SAMPLES:
        unreviewed.append("additional cue frames beyond the 400 sample limit")
    if decision["status"] != "approved":
        unreviewed.extend(["visual appearance between sampled frames", "audio/lyric synchronization"])
    failed = (not structural_passed or media.get("passed") is False or
              any(item["outcome"]["validation"] == "failed" for item in visual + brand))
    decoded = any(item.get("check") == "decode" and item.get("passed") is True for item in media.get("checks", []))
    complete = mode == "full" and decoded and media.get("passed") is True and visual_passed and brand_passed
    reasons = list(unreviewed)
    if decision["status"] != "approved":
        reasons.append("build review " + decision["status"])
    reasons += [reason for item in visual + brand for reason in item["outcome"]["review_reasons"]]
    outcome = outcomes.make(validation="failed" if failed else "passed" if complete else "incomplete",
                            reasons=reasons, validated_by=["encoded media", "cue timing and text"] +
                            (["sampled visual and brand checks"] if samples else []))
    passed = not failed and media.get("passed") is True
    return {**media, "mode": mode, "execution": "completed", "passed": passed,
            "status": "failed" if failed else media.get("status", "skipped"),
            "structural": {"passed": structural_passed, "checks": structural},
            "visual_sampled": {"status": "passed" if visual_passed else "failed" if visual else "not_run",
                               "frames": visual},
            "brand": {"status": "passed" if brand_passed else "failed" if brand else "not_run", "frames": brand},
            "coverage": coverage, "sources": sources or {}, "unreviewed": unreviewed,
            "review": decision, "outcome": outcome, "validated": outcome["state"] == "validated"}
