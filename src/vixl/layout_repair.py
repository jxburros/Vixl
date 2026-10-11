"""Bounded layout repair (#518): several candidate edits per failure, ranked by least disruption.

For text overflow, overlap, spacing and safe-area failures it tries the built-in repair (repair.suggest)
first, then other geometric candidates (a taller or wider text box, moves clear of the other layer, equal
gaps). Every candidate is applied to a copy and evaluated against the same design checks and suites; it
is accepted only if its failure is gone, nothing new fails, protected layers are untouched and no text
drops below ``minimum_size``. The least disruptive accepted candidate is kept and the next failure is
tried, within ``max_candidates``, ``max_iterations`` and ``time_budget``. The document changes only when
every targeted failure is resolved and ``dry_run`` is false; otherwise it is left as it was and the result
lists the unsatisfied constraints. Candidate order is fixed, so the same input gives the same plan.
"""

import math
import time

from .errors import VixlError, require
from .repair import _key, suggest, suite_findings

REPAIRABLE = ("bounds.text-overflow", "suite.text-fit", "overlap.text-text", "overlap.text-object", "safe_area.outside",
              "bounds.cut-off", "contrast.text-contrast", "suite.contrast", "suite.spacing")
GAP = 8  # Clearance a move leaves between two layers it separates.


def _spacing_findings(project, reports):
    findings = []
    for name, report in reports.items():
        rules = {rule["id"]: rule for rule in project.state.get("suites", {}).get(name, {}).get("rules", [])}
        for result in report.get("results", []):
            rule = rules.get(result["id"])
            if result["status"] == "failed" and rule and rule["kind"] == "spacing":
                try:
                    layers = [project.layer(ref) for ref in rule["targets"]]
                except VixlError:
                    continue
                findings.append({"rule": "suite.spacing", "check": "suite", "suite": name, "suite_rule": rule["id"],
                                 "layers": [x["name"] for x in layers], "layer_ids": [x["id"] for x in layers],
                                 "axis": rule.get("axis", "vertical"), "expected": rule.get("expected"),
                                 "action": "fix", "severity": rule.get("severity", "error")})
    return findings


def _state(project, checks, suites):
    from .checks import check_design

    report = check_design(project, checks=checks, repairs=False) if checks is not False else {"issues": []}
    reports = {name: project.check_suite(name) for name in suites}
    fixes = [item for item in report["issues"] if item.get("action") == "fix"]
    fixes += suite_findings(project, reports) + _spacing_findings(project, reports)
    failing = {name for name, item in reports.items() if item["status"] == "failed"}
    return fixes, failing


def _move(ident, dx, dy):
    return [{"type": "move", "target": ident, "x": round(dx), "y": round(dy), "relative": True}]


def _candidates(project, finding, boxes, minimum):
    """``(name, operations)`` in a fixed order: the built-in repair first, then the alternatives."""
    from .render import resolved_layers

    rule, ids = finding["rule"], finding.get("layer_ids") or []
    out = []
    first = suggest(project, {**finding, "minimum": max(minimum or 0, finding.get("minimum") or 0) or None})
    if first.get("available"):
        out.append((f"map:{first['kind']}", first["operations"]))
    canvas = project.state["canvas"]
    if rule in ("bounds.text-overflow", "suite.text-fit") and ids:
        layer = next((x for x in resolved_layers(project) if x["id"] == ids[0]), None)
        need = finding.get("needs")
        if layer is not None and need:
            x, y, w, h = boxes[ids[0]]
            if need[1] > layer["height"] and y + need[1] <= canvas["height"]:
                out.append(("taller-box", [{"type": "text-layout", "target": ids[0], "width": int(layer["width"]),
                                            "height": int(math.ceil(need[1]))}]))
            room = canvas["width"] - x
            if room > layer["width"]:
                out.append(("wider-box", [{"type": "text-layout", "target": ids[0], "width": int(room),
                                           "height": int(layer["height"])}]))
    if rule.startswith("overlap.") and len(ids) == 2:
        # Move the later (upper) layer first, then the other: right, left, down, up past the other's ink.
        for mover, other in ((ids[1], ids[0]), (ids[0], ids[1])):
            a, b = boxes[mover], boxes[other]
            for name, dx, dy in (("right", b[0] + b[2] - a[0] + GAP, 0), ("left", b[0] - a[0] - a[2] - GAP, 0),
                                 ("down", 0, b[1] + b[3] - a[1] + GAP), ("up", 0, b[1] - a[1] - a[3] - GAP)):
                nx, ny = a[0] + dx, a[1] + dy
                if nx >= 0 and ny >= 0 and nx + a[2] <= canvas["width"] and ny + a[3] <= canvas["height"]:
                    out.append((f"move-{name}:{mover}", _move(mover, dx, dy)))
    if rule == "suite.spacing" and len(ids) >= 2:
        axis = 1 if finding.get("axis", "vertical") == "vertical" else 0
        ordered = sorted(ids, key=lambda ident: boxes[ident][axis])
        gaps = [boxes[b][axis] - boxes[a][axis] - boxes[a][axis + 2] for a, b in zip(ordered, ordered[1:])]
        for label, target in (("expected", finding.get("expected")), ("median", sorted(gaps)[len(gaps) // 2])):
            if target is None:
                continue
            operations, shift = [], 0.0
            for (a, b), gap in zip(zip(ordered, ordered[1:]), gaps):
                shift += target - gap
                if round(shift):
                    operations += _move(b, shift if axis == 0 else 0, shift if axis == 1 else 0)
            if operations:
                out.append((f"equal-gaps:{label}", operations))
    return out


def _disruption(before, after, boxes_before, boxes_after):
    """How much a candidate changes: movement plus half the size change of every layer's box, and four
    points per pixel of font size changed."""
    score = 0.0
    for ident, box in boxes_before.items():
        other = boxes_after.get(ident)
        if other is None:
            score += 1000
            continue
        score += abs(other[0] - box[0]) + abs(other[1] - box[1]) + 0.5 * (abs(other[2] - box[2]) + abs(other[3] - box[3]))
    sizes = {x["id"]: x.get("size") for x in before.state["layers"] if x["type"] == "text"}
    for layer in after.state["layers"]:
        if layer["id"] in sizes and layer.get("size") is not None and sizes[layer["id"]] is not None:
            score += 4 * abs(layer["size"] - sizes[layer["id"]])
    return round(score, 2)


def _protected(project, refs):
    ids = {project.layer(ref)["id"] for ref in refs}
    while True:
        grown = ids | {x["id"] for x in project.state["layers"] if x.get("parent") in ids}
        if grown == ids:
            return ids
        ids = grown


def repair_layout(project, *, checks=None, suites=(), protected=(), minimum_size=None, max_candidates=24,
                  max_iterations=4, time_budget=20, dry_run=True):
    """Plan (and unless ``dry_run``, apply) a bounded layout repair. Returns ``{feasible, committed, selected,
    attempts, operations, unsatisfied, bounds}``; see the module docstring."""
    from .spatial import canvas_boxes

    require(type(max_candidates) is int and 1 <= max_candidates <= 200, "max_candidates must be 1-200",
            field="max_candidates")
    require(type(max_iterations) is int and 1 <= max_iterations <= 20, "max_iterations must be 1-20",
            field="max_iterations")
    require(isinstance(time_budget, (int, float)) and 0 < time_budget <= 300, "time_budget must be 0-300 seconds",
            field="time_budget")
    require(minimum_size is None or (isinstance(minimum_size, (int, float)) and 1 <= minimum_size <= 1000),
            "minimum_size must be 1-1000 px", field="minimum_size")
    require(isinstance(protected, (list, tuple)), "protected is a list of layer IDs or names", field="protected")
    started = time.monotonic()
    suites = list(suites or [])
    locked = _protected(project, protected)
    work = project.clone()
    fixes, failing = _state(work, checks, suites)
    initial = [{"rule": item["rule"], "layers": item.get("layers", [])} for item in fixes]
    attempts, selected, given_up = [], [], set()
    evaluated, stopped = 0, None
    for _ in range(max_iterations):
        targets = [item for item in fixes if item["rule"] in REPAIRABLE and _key(item) not in given_up]
        if not targets:
            break
        finding = targets[0]
        if locked & set(finding.get("layer_ids") or []) and not set(finding.get("layer_ids") or []) - locked:
            given_up.add(_key(finding))
            attempts.append({"rule": finding["rule"], "layers": finding.get("layers", []), "candidate": None,
                             "result": "skipped", "reason": "every layer it concerns is protected"})
            continue
        boxes, layout_boxes = canvas_boxes(work, "ink"), canvas_boxes(work)
        best = None
        for name, operations in _candidates(work, finding, boxes, minimum_size):
            if evaluated >= max_candidates:
                stopped = "max_candidates"
                break
            if time.monotonic() - started > time_budget:
                stopped = "time_budget"
                break
            record = {"rule": finding["rule"], "layers": finding.get("layers", []), "candidate": name,
                      "operations": operations}
            attempts.append(record)
            touched = {op.get("target") for op in operations}
            if touched & locked:
                record.update(result="rejected", reason="it changes a protected layer")
                continue
            evaluated += 1
            trial = work.clone()
            try:
                trial.apply(operations, detail="compact")
            except VixlError as exc:
                record.update(result="rejected", reason=f"it could not be applied: {exc}")
                continue
            if any(trial.layer(ident) != work.layer(ident) for ident in locked):
                record.update(result="rejected", reason="it changed a protected layer")
                continue
            small = [x["name"] for x in trial.state["layers"] if x["type"] == "text" and minimum_size
                     and x.get("size", minimum_size) < minimum_size and x.get("size") != work.layer(x["id"]).get("size")]
            if small:
                record.update(result="rejected", reason=f"text below {minimum_size} px: {', '.join(small)}")
                continue
            after, after_failing = _state(trial, checks, suites)
            keys = {_key(item) for item in after}
            new = [item["rule"] for item in after if _key(item) not in {_key(x) for x in fixes}]
            if _key(finding) in keys:
                record.update(result="rejected", reason="the failure remains")
            elif new or after_failing - failing:
                record.update(result="rejected", reason="it introduces " + ", ".join(new + sorted(after_failing - failing)))
            else:
                score = _disruption(work, trial, layout_boxes, canvas_boxes(trial))
                record.update(result="valid", disruption=score)
                if best is None or score < best[0]:
                    best = (score, name, operations, trial, after, after_failing)
        if best is not None:
            score, name, operations, work, fixes, failing = best
            for record in attempts:
                if record.get("candidate") == name and record.get("operations") is operations:
                    record["result"] = "selected"
            selected.append({"rule": finding["rule"], "layers": finding.get("layers", []), "candidate": name,
                             "operations": operations, "disruption": score})
        else:
            given_up.add(_key(finding))
        if stopped:
            break
    unsatisfied = [{"rule": item["rule"], "layers": item.get("layers", []), **(
        {"message": item["message"]} if item.get("message") else {})} for item in fixes if item["rule"] in REPAIRABLE]
    # Fix findings layout repair does not address (missing fonts, blanks ...) are reported, not counted against it.
    other = [{"rule": item["rule"], "layers": item.get("layers", [])} for item in fixes if item["rule"] not in REPAIRABLE]
    feasible = not unsatisfied and not failing
    operations = [op for item in selected for op in item["operations"]]
    committed = feasible and bool(operations) and not dry_run
    if committed:
        project.apply(operations, detail="compact")
    from .outcomes import make

    return {
        "feasible": feasible, "committed": committed, "dry_run": dry_run,
        "selected": selected, "operations": operations if feasible else [],
        "attempts": attempts, "initial": initial, "unsatisfied": unsatisfied,
        "failing_suites": sorted(failing), **({"out_of_scope": other[:20]} if other else {}),
        "bounds": {"candidates": evaluated, "max_candidates": max_candidates, "max_iterations": max_iterations,
                   "time_budget": time_budget, "elapsed_s": round(time.monotonic() - started, 2),
                   **({"stopped": stopped} if stopped else {})},
        "outcome": make("completed", "passed" if feasible else "failed",
                        [f"{item['rule']}: {', '.join(item['layers'])}" for item in unsatisfied],
                        validated_by=["layout repair"]),
        **({"note": "Not applied: the original is unchanged because constraints remain unsatisfied."}
           if not feasible else {"note": "Dry run: apply operations (or rerun with dry_run false) to commit."}
           if dry_run and operations else {}),
    }

