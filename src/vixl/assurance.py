"""Portable design contracts. Checks never mutate artwork or their own expectations."""

from copy import deepcopy
import hashlib
import json

import numpy as np

from .errors import VixlError, require
from .model import finite


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


RULE_FIELDS = {
    "container": {"target"},
    "palette": {"palette", "colors", "tolerance", "max_fraction", "alpha_min", "region"},
    "assert": {"expression"},
    "design": {"options"},
    "property": {"target", "field", "expected", "tolerance"},
    "gap": {"before", "after", "axis", "expected", "tolerance"},
    "unchanged": {"target", "snapshot"},
    "pixels": {"region", "asset", "tolerance"},
    "text-fit": {"target", "minimum"},
    "alpha": {"minimum", "maximum"},
}


def validate_suite(suite):
    require(
        isinstance(suite, dict) and set(suite) <= {"version", "rules", "sampling", "description"},
        "Invalid check suite",
    )
    require(suite.get("version", 1) == 1, "Unsupported check suite version")
    rules = suite.get("rules")
    require(isinstance(rules, list) and 0 < len(rules) <= 256, "Suite needs 1–256 rules")
    ids = set()
    for rule in rules:
        require(isinstance(rule, dict) and rule.get("kind") in RULE_FIELDS, "Unknown check kind")
        require(not set(rule) - RULE_FIELDS[rule["kind"]] - {"kind", "id", "severity"}, "Unknown check field")
        ident = rule.get("id")
        require(isinstance(ident, str) and ident and ident not in ids, "Check IDs must be unique")
        ids.add(ident)
        require(rule.get("severity", "error") in ("error", "warning"), "Invalid check severity")
        if "tolerance" in rule:
            finite(rule["tolerance"], "tolerance", 0, 1e9)
    sampling = suite.get("sampling", {"mode": "still"})
    require(isinstance(sampling, dict) and set(sampling) <= {"mode", "count", "times"}, "Invalid sampling")
    require(sampling.get("mode", "still") in ("still", "sampled", "all", "times"), "Invalid sampling mode")
    count = sampling.get("count", 8)
    require(type(count) is int and 2 <= count <= 3600, "Sample count must be 2–3600")
    if sampling.get("mode") == "times":
        require(
            isinstance(sampling.get("times"), list) and 0 < len(sampling["times"]) <= 3600,
            "Explicit sampling needs 1–3600 times",
        )
    require(len(json.dumps(suite, allow_nan=False)) <= 1024 * 1024, "Suite too large", "resource_limit")


def capture(project, targets=(), regions=()):
    from .assets import add_image

    rules = []
    selected = {project.layer(target)["id"] for target in targets}
    # Protect group descendants too, so changing a child cannot pass unnoticed.
    while True:
        expanded = selected | {
            layer["id"] for layer in project.state["layers"] if layer.get("parent") in selected
        }
        if expanded == selected:
            break
        selected = expanded
    for layer in project.state["layers"]:
        if layer["id"] not in selected:
            continue
        rules.append(
            {
                "id": f"preserve-{layer['name']}",
                "kind": "unchanged",
                "target": layer["id"],
                "snapshot": deepcopy(layer),
            }
        )
    image = project.render() if regions else None
    for i, region in enumerate(regions):
        x, y, w, h = region_box(project, region)
        asset = add_image(project, image.crop((x, y, x + w, y + h)))
        rules.append(
            {
                "id": f"region-{i + 1}",
                "kind": "pixels",
                "region": [x, y, w, h],
                "asset": asset,
                "tolerance": 0,
            }
        )
    suite = {"version": 1, "rules": rules}
    validate_suite(suite)
    return suite


def region_box(project, region):
    require(
        isinstance(region, list) and len(region) == 4 and all(type(v) is int for v in region),
        "Region needs integer [x,y,width,height]",
    )
    x, y, w, h = region
    c = project.state["canvas"]
    require(
        x >= 0 and y >= 0 and w > 0 and h > 0 and x + w <= c["width"] and y + h <= c["height"],
        "Region must be inside canvas",
    )
    return x, y, w, h


def rule_result(project, rule):
    from .render import resolved_layers, resolve_layout

    kind = rule["kind"]
    if kind == "container":
        from .containers import measure
        report = measure(project, rule.get("target"))
        return report["passed"], report
    if kind == "palette":
        from .palette_checks import measure
        report = measure(project, **{k: v for k, v in rule.items() if k not in ("kind", "id", "severity")})
        return report["passed"], report
    if kind == "assert":
        from .validation import assert_rule

        return assert_rule(project, rule["expression"]), {"expected": rule["expression"]}
    if kind == "design":
        report = project.check(**rule.get("options", {}))
        return (False if report["errors"] else None if report["warnings"] else True), report
    if kind == "unchanged":
        layer = project.layer(rule["target"])
        return layer == rule["snapshot"], {"expected": digest(rule["snapshot"]), "actual": digest(layer)}
    if kind == "property":
        target = rule["target"]
        layer = (
            project.state["canvas"]
            if target == "canvas"
            else next(x for x in resolved_layers(project) if x["id"] == project.layer(target)["id"])
        )
        require(rule["field"] in layer, "Unknown measured property")
        actual, expected = layer[rule["field"]], rule["expected"]
        numeric = type(actual) in (int, float) and type(expected) in (int, float)
        passed = abs(actual - expected) <= rule.get("tolerance", 0) if numeric else actual == expected
        return passed, {"expected": expected, "actual": actual}
    if kind == "gap":
        a, b = project.layer(rule["before"]), project.layer(rule["after"])
        require(a.get("parent") == b.get("parent"), "Gap checks require siblings")
        require(rule.get("axis", "vertical") in ("horizontal", "vertical"), "Invalid gap axis")
        axis = 0 if rule.get("axis", "vertical") == "horizontal" else 1
        bounds = resolve_layout(project)
        actual = bounds[b["id"]][axis] - bounds[a["id"]][axis] - bounds[a["id"]][axis + 2]
        return abs(actual - rule["expected"]) <= rule.get("tolerance", 1), {
            "expected": rule["expected"],
            "actual": actual,
        }
    if kind == "text-fit":
        from .automation import text_fits

        layer = next(x for x in resolved_layers(project) if x["id"] == project.layer(rule["target"])["id"])
        require(layer["type"] == "text", "text-fit requires text")
        # A fitted/warped layer can conceal its effective font size; do not falsely certify it.
        require(
            not layer.get("text_layout", {}).get("fit")
            and not layer.get("text_layout", {}).get("path")
            and layer.get("text_layout", {}).get("warp", "none") == "none",
            "Use fit-text to bake measurable fitting before checking",
        )
        fits = text_fits(project, layer, layer["size"], layer["width"], layer["height"])
        return fits and layer["size"] >= rule.get("minimum", 1), {"actual_size": layer["size"], "fits": fits}
    if kind == "pixels":
        x, y, w, h = region_box(project, rule["region"])
        current = project.render().crop((x, y, x + w, y + h))
        baseline = project.image(rule["asset"])
        require(current.size == baseline.size, "Baseline region size changed")
        delta = int(np.abs(np.asarray(current).astype(int) - np.asarray(baseline).astype(int)).max())
        return delta <= rule.get("tolerance", 0), {"actual": delta, "expected": rule.get("tolerance", 0)}
    alpha = np.asarray(project.render().getchannel("A"))
    actual = float((alpha < 255).mean())
    return rule.get("minimum", 0) <= actual <= rule.get("maximum", 1), {"nonopaque_fraction": actual}


def run_suite(project, suite, *, variables=None, artboard=None, mode=None):
    from .design_render import artboard_project
    from .timeline import frame_times, project_at, parse_time

    if isinstance(suite, str):
        require(suite in project.state.get("suites", {}), f"Unknown suite: {suite}")
        suite = project.state["suites"][suite]
    validate_suite(suite)
    project = artboard_project(project.clone(), artboard, None, variables)
    sampling = suite.get("sampling", {})
    mode = mode or sampling.get("mode", "still")
    require(mode in ("still", "sampled", "all", "times"), "Unknown coverage mode")
    timeline = project.state.get("timeline", {"duration": 1000, "fps": 30})
    if mode == "still":
        times = [None]
    elif mode == "all":
        times, _ = frame_times(project)
    elif mode == "times":
        times = [parse_time(t, timeline["duration"], timeline.get("markers")) for t in sampling["times"]]
    else:
        times = sorted(
            set(
                [
                    i * timeline["duration"] / (sampling.get("count", 8) - 1)
                    for i in range(sampling.get("count", 8))
                ]
                + [k["time"] for t in timeline.get("tracks", []) for k in t["keys"]]
            )
        )
    require(len(times) * len(suite["rules"]) <= 50000, "Check workload exceeds limit", "resource_limit")
    results = []
    for time in times:
        frame = project if time is None else project_at(project, time)
        for rule in suite["rules"]:
            try:
                passed, detail = rule_result(frame, rule)
                status = "passed" if passed else "needs_review" if passed is None else "failed"
            except (VixlError, KeyError, TypeError, ValueError, StopIteration) as exc:
                status, detail = "needs_review", {"message": str(exc)}
            results.append(
                {
                    "id": rule["id"],
                    "status": status,
                    "severity": rule.get("severity", "error"),
                    "time": time,
                    **detail,
                }
            )
    errors = sum(r["status"] == "failed" and r["severity"] == "error" for r in results)
    review = sum(
        r["status"] == "needs_review" or (r["status"] == "failed" and r["severity"] == "warning")
        for r in results
    )
    return {
        "version": 1,
        "suite_hash": digest(suite),
        "passed": errors == 0 and review == 0,
        "status": "failed" if errors else "needs_review" if review else "passed",
        "errors": errors,
        "needs_review": review,
        "coverage": {"mode": mode, "times": times},
        "results": results,
    }
