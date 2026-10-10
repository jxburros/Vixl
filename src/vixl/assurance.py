"""Portable design contracts. Checks never mutate artwork or their own expectations."""

from copy import deepcopy
import hashlib
import json
import math

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
    "spacing": {"targets", "axis", "expected", "tolerance"},
    "relation": {"target", "to", "position", "align", "minimum", "maximum", "tolerance", "bounds"},
    "contrast": {"target", "minimum"},
    "color": {"point", "region", "expected", "tolerance"},
    "ink": {"region", "background", "tolerance", "minimum", "maximum"},
    "balance": {"expected", "tolerance", "region", "background"},
    "hierarchy": {"targets", "ratio"},
    "count": {"target", "layer_type", "minimum", "maximum"},
    "focal": {"target", "grid", "tolerance"},
}
POSITIONS = ("left-of", "right-of", "above", "below", "inside", "contains", "overlapping", "apart")
EDGES = ("left", "center-x", "right", "top", "center-y", "bottom")
GRIDS = ("thirds", "golden", "center")


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
        _validate_fields(rule)
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


def _validate_fields(rule):
    """Shape checks for the measured rule kinds, so a malformed rule fails when the suite is attached
    rather than reading as needs_review on every run."""
    kind, where = rule["kind"], f"rule {rule.get('id')!r}"
    for name in ("minimum", "maximum", "ratio"):
        if name in rule:
            finite(rule[name], f"{where}: {name}", 0, 1e9)
    if kind in ("spacing", "hierarchy"):
        targets = rule.get("targets")
        require(isinstance(targets, list) and len(targets) >= 2 and all(isinstance(t, str) for t in targets),
                f"{where}: targets needs two or more layer names", field="targets")
    if kind in ("relation", "contrast", "focal"):
        require(isinstance(rule.get("target"), str), f"{where}: needs a target layer", field="target")
    if kind == "relation":
        require(isinstance(rule.get("to"), str), f"{where}: needs to (a layer or 'canvas')", field="to")
        require(rule.get("position", "apart") in POSITIONS, f"{where}: position is one of {', '.join(POSITIONS)}",
                field="position")
        align = rule.get("align", [])
        require(isinstance(align, list) and set(align) <= set(EDGES),
                f"{where}: align lists edges from {', '.join(EDGES)}", field="align")
        require(rule.get("bounds", "box") in ("box", "ink"), f"{where}: bounds is box or ink", field="bounds")
    if kind == "spacing":
        require(rule.get("axis", "vertical") in ("horizontal", "vertical"), f"{where}: axis is horizontal or vertical",
                field="axis")
    if kind == "color":
        require(("point" in rule) != ("region" in rule), f"{where}: give point or region", field="point")
        require(isinstance(rule.get("expected"), str), f"{where}: expected is a color", field="expected")
    if kind == "balance" and "expected" in rule:
        point = rule["expected"]
        require(isinstance(point, list) and len(point) == 2 and all(type(v) in (int, float) and 0 <= v <= 1 for v in point),
                f"{where}: expected is [x, y] as fractions of the canvas (0-1)", field="expected")
    if kind == "focal":
        require(rule.get("grid", "thirds") in GRIDS, f"{where}: grid is one of {', '.join(GRIDS)}", field="grid")
    if kind == "relation":
        require(any(name in rule for name in ("position", "align", "minimum", "maximum")),
                f"{where}: set position, align, minimum or maximum", field="position")
    if kind in ("ink", "count"):
        require("minimum" in rule or "maximum" in rule, f"{where}: set minimum or maximum", field="minimum")
    if kind == "count":
        require(isinstance(rule.get("target", "*"), str), f"{where}: target is a layer name or glob", field="target")


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
        # Only a text-layout width wraps lines; auto-sized text is measured as it is drawn.
        wrap = "width" in layer.get("text_layout", {})
        fits = text_fits(project, layer, layer["size"], layer["width"], layer["height"], wrap=wrap)
        return fits and layer["size"] >= rule.get("minimum", 1), {"actual_size": layer["size"], "fits": fits}
    if kind == "pixels":
        x, y, w, h = region_box(project, rule["region"])
        current = project.render().crop((x, y, x + w, y + h))
        baseline = project.image(rule["asset"])
        require(current.size == baseline.size, "Baseline region size changed")
        delta = int(np.abs(np.asarray(current).astype(int) - np.asarray(baseline).astype(int)).max())
        return delta <= rule.get("tolerance", 0), {"actual": delta, "expected": rule.get("tolerance", 0)}
    if kind == "alpha":
        alpha = np.asarray(project.render().getchannel("A"))
        actual = float((alpha < 255).mean())
        return rule.get("minimum", 0) <= actual <= rule.get("maximum", 1), {"nonopaque_fraction": actual}
    return MEASURED[kind](project, rule)


def _within(value, rule):
    return rule.get("minimum", -math.inf) <= value <= rule.get("maximum", math.inf)


def _spacing(project, rule):
    from .spacing import measure_spacing

    report = measure_spacing(project, targets=rule["targets"], axis=rule.get("axis", "vertical"),
                             expected=rule.get("expected"), tolerance=rule.get("tolerance", 1))
    return report["passed"], {"gaps": [round(gap["pixels"], 2) for gap in report["gaps"]],
                              "spread": round(report["spread"], 2), "expected": rule.get("expected"),
                              "tolerance": report["tolerance"]}


def _relation(project, rule):
    from .spatial import _distances, canvas_boxes, relation

    boxes = canvas_boxes(project, rule.get("bounds", "box"))
    canvas = project.state["canvas"]
    a = boxes[project.layer(rule["target"])["id"]]
    b = (0, 0, canvas["width"], canvas["height"]) if rule["to"] == "canvas" else boxes[project.layer(rule["to"])["id"]]
    found = relation(a, b, rule.get("tolerance", 1))
    positions, detail = found["positions"], {"positions": found["positions"], "alignments": found["alignments"]}
    passed = True
    if "position" in rule:
        wanted = rule["position"]
        passed = "overlapping" not in positions if wanted == "apart" else wanted in positions
    missing = [edge for edge in rule.get("align", []) if edge not in found["alignments"]]
    if missing:
        passed = False
        detail["missing_alignments"] = missing
    if "minimum" in rule or "maximum" in rule:
        if "inside" in positions:
            # Inside its container the distance that matters is the smallest margin to the container's edges.
            margins = _distances(a, b)
            distance = min(margins.values())
            detail["margins"] = {side: round(value, 2) for side, value in margins.items()}
        else:
            distance = found["nearest_edge_distance"]
        detail["distance"] = round(distance, 2)
        passed = passed and _within(distance, rule)
    return passed, detail


def _contrast(project, rule):
    from .measure import measure

    report = measure(project, target=rule["target"], histogram="none")["contrast"]
    need = rule.get("minimum", 4.5)
    # The tenth-percentile glyph pixel, as the contrast design check reads it; an outline counts when it carries the text.
    outline = (report.get("outline") or {}).get("p10")
    detail = {"expected": need, "actual": report["p10"], "weakest_region": report["weakest_region"]}
    if outline is not None:
        detail["outline"] = outline
    return max(report["p10"], outline or 0) >= need, detail


def _hex(rgb):
    return "#" + "".join(f"{round(v):02x}" for v in rgb)


def _color(project, rule):
    from .design import resolve_color
    from .render import color

    image = project.render()
    if "point" in rule:
        point = rule["point"]
        require(isinstance(point, list) and len(point) == 2 and all(type(v) is int for v in point),
                "point needs integer [x, y]", field="point")
        require(0 <= point[0] < image.width and 0 <= point[1] < image.height, "point must be inside the canvas")
        actual = np.asarray(image.getpixel(tuple(point))[:3], dtype=float)
    else:
        x, y, w, h = region_box(project, rule["region"])
        pixels = np.asarray(image.crop((x, y, x + w, y + h))).reshape(-1, 4).astype(float)
        weight = pixels[:, 3] / 255
        require(weight.sum() > 0, "Nothing is drawn in the region")
        actual = (pixels[:, :3] * weight[:, None]).sum(axis=0) / weight.sum()
    expected = np.asarray(color(resolve_color(rule["expected"], project.state))[:3], dtype=float)
    distance = float(np.abs(actual - expected).max())
    return distance <= rule.get("tolerance", 12), {"expected": _hex(expected), "actual": _hex(actual),
                                                   "distance": round(distance, 2)}


def _backdrop(project, layer, boxes):
    """A layer that is the page rather than content: marked role background, or a top-level solid,
    gradient, image or rectangle covering the whole canvas."""
    if layer.get("role") == "background":
        return True
    canvas = project.state["canvas"]
    x, y, w, h = boxes[layer["id"]]
    covers = x <= 0 and y <= 0 and x + w >= canvas["width"] and y + h >= canvas["height"]
    plain = layer["type"] in ("solid", "gradient", "image") or (
        layer["type"] == "shape" and layer.get("shape") in ("rectangle", "rounded-rectangle"))
    return covers and plain and not layer.get("parent")


def _ink_weights(project, rule):
    """Per-pixel visual weight (0-1) in the rule's region: how far each pixel is from ``background``, or,
    without one, the coverage of the content drawn without the canvas colour and backdrop layers."""
    from .design import resolve_color
    from .render import color
    from .spatial import canvas_boxes

    if rule.get("background"):
        pixels = np.asarray(project.render()).astype(float)
        base = np.asarray(color(resolve_color(rule["background"], project.state))[:3], dtype=float)
        weights = np.abs(pixels[:, :, :3] - base).max(axis=2) / 255 * pixels[:, :, 3] / 255
    else:
        candidate = project.clone()
        candidate.state["canvas"]["background"] = "transparent"
        boxes = canvas_boxes(candidate)
        for layer in candidate.state["layers"]:
            if _backdrop(candidate, layer, boxes):
                layer["visible"] = False
        weights = np.asarray(candidate.render().getchannel("A")).astype(float) / 255
    if "region" in rule:
        x, y, w, h = region_box(project, rule["region"])
        weights = weights[y:y + h, x:x + w]
    return weights


def _ink(project, rule):
    weights = _ink_weights(project, rule)
    actual = float((weights > rule.get("tolerance", 24) / 255).mean())
    return _within(actual, rule), {"ink_fraction": round(actual, 4), "minimum": rule.get("minimum"),
                                   "maximum": rule.get("maximum")}


def _balance(project, rule):
    weights = _ink_weights(project, rule)
    total = weights.sum()
    require(total > 0, "Nothing is drawn to balance")
    height, width = weights.shape
    center = [float((weights.sum(axis=0) * (np.arange(width) + 0.5)).sum() / total / width),
              float((weights.sum(axis=1) * (np.arange(height) + 0.5)).sum() / total / height)]
    expected = rule.get("expected", [0.5, 0.5])
    offset = [center[0] - expected[0], center[1] - expected[1]]
    tolerance = rule.get("tolerance", 0.1)
    return max(map(abs, offset)) <= tolerance, {"center": [round(v, 4) for v in center], "expected": expected,
                                                "offset": [round(v, 4) for v in offset], "tolerance": tolerance}


def _rendered_size(project, layer):
    from .richtext import active, fitted
    from .text import plan

    require(layer["type"] == "text", f"{layer['name']!r} is not text")
    if active(layer):
        return layer["size"] * fitted(project, layer).size_scale
    return plan(project, layer).size


def _hierarchy(project, rule):
    from .render import resolved_layers

    resolved = {item["id"]: item for item in resolved_layers(project)}
    sizes = [_rendered_size(project, resolved[project.layer(ref)["id"]]) for ref in rule["targets"]]
    ratio = rule.get("ratio", 1.2)
    steps = [a / b if b else math.inf for a, b in zip(sizes, sizes[1:])]
    return all(step >= ratio - 1e-9 for step in steps), {
        "sizes": [round(v, 2) for v in sizes], "ratios": [round(v, 3) for v in steps], "expected": ratio}


def _count(project, rule):
    from .spatial import _select

    index = {layer["id"]: layer for layer in project.state["layers"]}

    def shown(layer):
        while layer:
            if not layer["visible"] or layer["opacity"] <= 0:
                return False
            layer = index.get(layer.get("parent"))
        return True

    try:
        chosen = _select(project, rule.get("target", "*"))
    except VixlError:
        chosen = []
    names = [layer["name"] for layer in chosen
             if shown(layer) and rule.get("layer_type", layer["type"]) == layer["type"]]
    return _within(len(names), rule), {"count": len(names), "layers": names[:20],
                                       "minimum": rule.get("minimum"), "maximum": rule.get("maximum")}


def _focal(project, rule):
    from .spatial import _composition, canvas_boxes

    box = canvas_boxes(project)[project.layer(rule["target"])["id"]]
    grid = rule.get("grid", "thirds")
    nearest = min(_composition(project, box)[grid]["points"], key=lambda item: item["distance"])
    canvas = project.state["canvas"]
    tolerance = rule.get("tolerance", 0.05 * min(canvas["width"], canvas["height"]))
    return nearest["distance"] <= tolerance, {"nearest_point": [round(v, 1) for v in nearest["point"]],
                                              "distance": round(nearest["distance"], 1), "tolerance": tolerance}


MEASURED = {"spacing": _spacing, "relation": _relation, "contrast": _contrast, "color": _color, "ink": _ink,
            "balance": _balance, "hierarchy": _hierarchy, "count": _count, "focal": _focal}


def run_suite(project, suite, *, variables=None, artboard=None, mode=None):
    from .design_render import artboard_project
    from .timeline import frame_times, project_at, parse_time

    name = suite if isinstance(suite, str) else None
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
        from .checks import missing_glyphs

        # Every suite also fails on characters no font can draw (they render as empty boxes).
        missing = missing_glyphs(frame)
        if missing:
            results.append(
                {
                    "id": "missing-glyphs",
                    "status": "failed",
                    "severity": "error",
                    "time": time,
                    "automatic": True,
                    "message": "Text has characters no font can draw; import a covering font and add it "
                    "with font-fallbacks",
                    "layers": missing,
                }
            )
    errors = sum(r["status"] == "failed" and r["severity"] == "error" for r in results)
    review = sum(
        r["status"] == "needs_review" or (r["status"] == "failed" and r["severity"] == "warning")
        for r in results
    )
    report = {
        "version": 1,
        "suite_hash": digest(suite),
        "passed": errors == 0 and review == 0,
        "status": "failed" if errors else "needs_review" if review else "passed",
        "errors": errors,
        "needs_review": review,
        "coverage": {"mode": mode, "times": times},
        "results": results,
    }
    from .waivers import apply_suite

    # A rule waiver (the waiver operation with rule) turns that rule's failures into "waived" results.
    return apply_suite(project, report, name)
