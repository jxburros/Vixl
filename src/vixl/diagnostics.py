"""Bounded diagnostic views for agent calls; filtering never changes the overall verdict."""

from collections import Counter
from fnmatch import fnmatchcase

from .errors import require


def matches(value, patterns):
    return not patterns or any(fnmatchcase(value, pattern) for pattern in patterns)


def page(records, offset, limit):
    require(type(offset) is int and offset >= 0, "offset must be a nonnegative integer", field="offset")
    require(type(limit) is int and 1 <= limit <= 200, "limit must be 1–200", field="limit")
    end = min(offset + limit, len(records))
    return records[offset:end], {
        "total": len(records),
        "offset": offset,
        "limit": limit,
        "next_offset": end if end < len(records) else None,
    }


def validation_report(report, *, detail="summary", targets=None, severity=None, offset=0, limit=50):
    require(detail in ("summary", "full"), "detail must be summary or full", field="detail")
    require(
        severity is None or severity in ("error", "warning", "info"), "Unknown severity", field="severity"
    )
    records = report["checks"]
    counts = Counter(item["severity"] for item in records if not item["passed"])
    selected = [
        item
        for item in records
        if (detail == "full" or not item["passed"])
        and matches(item.get("layer", ""), targets)
        and (severity is None or item["severity"] == severity)
    ]
    visible, pagination = page(selected, offset, limit)
    return {
        **report,
        "checks": visible,
        "summary": {
            "checked": len(records),
            "passed": sum(item["passed"] for item in records),
            "errors": counts["error"],
            "warnings": counts["warning"],
            "info": counts["info"],
        },
        "pagination": pagination,
    }


def timeline_report(
    project,
    *,
    detail="summary",
    targets=None,
    properties=None,
    start=None,
    end=None,
    offset=0,
    limit=50,
    key_offset=0,
    key_limit=50,
):
    from .timeline import attachment_report, default_timeline, parse_time
    import math

    require(detail in ("summary", "full"), "detail must be summary or full", field="detail")
    timeline = project.state.get("timeline") or default_timeline()
    duration = timeline["duration"]
    start = 0 if start is None else parse_time(start, duration, timeline.get("markers", {}))
    end = duration if end is None else parse_time(end, duration, timeline.get("markers", {}))
    require(0 <= start <= end <= duration, "Time range must lie within the timeline", field="start")
    names = {layer["id"]: layer["name"] for layer in project.state["layers"]}
    tracks = []
    total_keys = 0
    for track in timeline.get("tracks", []):
        name = names.get(track["target"], track["target"])
        if targets and not (matches(name, targets) or matches(track["target"], targets)):
            continue
        if not matches(track["property"], properties):
            continue
        keys = [key for key in track["keys"] if start <= key["time"] <= end]
        if not keys:
            continue
        total_keys += len(keys)
        item = {
            "target": track["target"],
            "layer": name,
            "property": track["property"],
            "key_count": len(keys),
            "start": keys[0]["time"],
            "end": keys[-1]["time"],
        }
        if "attach" in track:
            item["attached_to"] = names.get(track["attach"]["to"], track["attach"]["to"])
        if detail == "full":
            item["keys"], item["key_pagination"] = page(keys, key_offset, key_limit)
        tracks.append(item)
    visible, pagination = page(tracks, offset, limit)
    markers = [(name, time) for name, time in timeline.get("markers", {}).items() if start <= time <= end]
    return {
        "duration": duration,
        "fps": timeline["fps"],
        "frames": max(1, math.ceil(duration * timeline["fps"] / 1000)),
        "loop": timeline.get("loop", 0),
        "tracks": visible,
        "pagination": pagination,
        "summary": {"tracks": len(tracks), "keys": total_keys},
        "range": [start, end],
        "markers": dict(markers[:limit]),
        "marker_count": len(markers),
        **({"attachments": attachments} if (attachments := attachment_report(project)) else {}),
    }


# What each rule measured, read from the fields its finding already carries: (actual field, expected, unit).
MEASURES = {
    "bounds.text-overflow": ("needs", "box_size", "px"),
    "contrast.text-contrast": ("contrast", "required", ":1"),
    "safe_area.outside": ("bounds", "safe_area", "box"),
    "bounds.cut-off": ("bounds", "canvas", "box"),
    "bounds.off-canvas": ("bounds", "canvas", "box"),
    "overlap.text-text": ("pixels", None, "px"),
    "overlap.text-object": ("pixels", None, "px"),
    "legibility": ("thumbnail_size", "min_thumbnail_text", "px"),
}


def annotate(project, issues, *, page=None, min_thumbnail_text=None, repairs=True):
    """Make findings actionable in place (#524): ``measured`` (actual versus expected), the ``page`` in a
    multi-page document, and for fix findings a ``repair`` suggestion of canonical operations from the
    built-in map (repair.suggest). Suggestions are recommendations: nothing is applied."""
    from .render import resolved_layers

    canvas = project.state["canvas"]
    sizes = None
    for item in issues:
        if page is not None and "page" not in item:
            item["page"] = page
        spec = MEASURES.get(item.get("rule")) or MEASURES.get(item.get("check"))
        if spec and spec[0] in item:
            actual, expected, unit = spec
            if expected == "box_size":
                if sizes is None:
                    sizes = {x["id"]: [x.get("width"), x.get("height")] for x in resolved_layers(project)}
                value = sizes.get((item.get("layer_ids") or [None])[0])
            elif expected == "canvas":
                value = [0, 0, canvas["width"], canvas["height"]]
            elif expected == "min_thumbnail_text":
                value = min_thumbnail_text
            else:
                value = item.get(expected) if expected else None
            item["measured"] = {"actual": item[actual], "expected": value, "unit": unit}
    if repairs:
        from .repair import annotate as suggest_repairs

        suggest_repairs(project, issues)
    return issues


def page_findings(report, offset=0, limit=None):
    """One page of a check report's findings. ``passed``, the counts and ``outcome`` still describe every
    finding; ``by_action`` indexes the returned page."""
    if limit is None and not offset:
        return report
    from .checks import ACTIONS

    visible, pagination = page(report["issues"], offset, 50 if limit is None else limit)
    return {**report, "issues": visible, "pagination": pagination,
            "by_action": {action: [i for i, x in enumerate(visible) if x.get("action") == action] for action in ACTIONS}}
