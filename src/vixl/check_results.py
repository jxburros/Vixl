"""Compact check verdicts and revision-bound delivery status; never a substitute for a fresh check."""

import json
from copy import deepcopy


def summarize(issues):
    groups = {}
    for item in issues:
        key = (item["rule"], item["action"])
        repair = item.get("repair") or {}
        fix = repair.get("reason") or item.get("hint") or item.get("message", "Review this finding")
        if key not in groups:
            groups[key] = {"rule": key[0], "action": key[1], "count": 0, "layers": [], "fix": fix,
                           "_severity": 2, "_cheap": False}
        group = groups[key]
        group["count"] += 1
        group["_severity"] = min(group["_severity"], {"error": 0, "warning": 1}.get(item["severity"], 2))
        group["_cheap"] |= bool(repair.get("operations"))
        for layer in item.get("layers", []) or ([item["layer"]] if item.get("layer") else []):
            if layer not in group["layers"] and len(group["layers"]) < 3:
                group["layers"].append(layer)
    ranked = sorted(groups.values(), key=lambda g: ({"fix": 0, "review": 1, "informational": 2}[g["action"]],
                                                    g["_severity"], not g["_cheap"], g["rule"]))
    summary = [{k: v for k, v in group.items() if not k.startswith("_")} for group in ranked]
    blocking = list(dict.fromkeys(x["rule"] for x in issues if x["action"] == "fix" or x["severity"] == "error"))
    verdict = ("Failed: " + ", ".join(blocking) + "; passed requires no errors and no fix findings" if blocking
               else "Passed: no errors and no fix findings; review findings still need attention")
    return {"verdict": verdict, "top": summary[:3], "summary": summary}


def _path(project):
    if not project.path:
        return None
    from .hashing import content_hash
    from .render_cache import user_cache_dir

    root = user_cache_dir()
    return root / "checks" / (content_hash(str(project.path.resolve())) + ".json") if root is not None else None


def remember(project, report):
    from .hashing import content_hash

    summary = {"revision": project.head, "fix": len(report.get("by_action", {}).get("fix", [])),
               "review": len(report.get("by_action", {}).get("review", [])), "top": report.get("top", []),
               "passed": report["passed"], "profile": report.get("profile"),
               "suites": report.get("suites", report.get("profile", {}).get("suites", {})),
               "checked": report.get("checked", {}), "state_hash": content_hash(project.state)}
    project._last_check = deepcopy(summary)
    path = _path(project)
    if path is not None:
        import os
        from .fileio import temporary

        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            fd, temp = temporary(path.parent)
            try:
                with os.fdopen(fd, "w") as stream:
                    json.dump(summary, stream)
                os.replace(temp, path)
            finally:
                if os.path.exists(temp):
                    os.unlink(temp)
        except OSError:
            pass  # A read-only cache must not make checking fail.


def last_check(project):
    value = getattr(project, "_last_check", None)
    if value is None:
        path = _path(project)
        if path is not None and path.is_file():
            try:
                value = json.loads(path.read_text())
            except (OSError, ValueError):
                value = None
    if not isinstance(value, dict) or "revision" not in value:
        return "not_run"
    from .hashing import content_hash

    if value["revision"] != project.head or value.get("state_hash") != content_hash(project.state):
        return "stale"
    return {k: deepcopy(v) for k, v in value.items() if k != "state_hash"}


def delivery(project, report, *, strict=False, check_status=None):
    from .errors import require
    from .policy import for_project

    status = last_check(project)
    if strict:
        # Strict delivery checks now: an absent, stale or selectively cached check cannot approve an export.
        result = project.check()
        status = last_check(project)
        require(result["passed"], "Design checks failed; resolve fix findings before strict export",
                "design_check_failed", last_check=status)
    enabled = for_project(project).get("export_check_status", True) if check_status is None else check_status
    if enabled:
        report["last_check"] = status
