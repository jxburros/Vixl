"""The built-in repair map: one known mechanical repair per kind of finding.

``suggest`` turns a finding into canonical operations without changing anything (#524 diagnostics);
``auto_repair`` applies those suggestions to a candidate and keeps each only when the checks then show
its finding resolved with nothing new failing (#571); ``layout.repair_layout`` uses the same map as the
first of several candidates (#518). Campaign ``repair_actions`` run through ``campaign`` here too.

| Rule | Repair |
| --- | --- |
| ``bounds.text-overflow``, suite ``text-fit`` | ``fit-text`` in the text's box, never below the minimum size |
| ``contrast.text-contrast``, suite ``contrast`` | text colour moved toward the role ink (``@ink``, else black or white) |
| ``safe_area.outside``, ``bounds.cut-off`` (text) | a relative ``move`` back inside the safe area or canvas |
| ``blanks.unfilled`` | held for review: the copy is never guessed |
"""

import math

from .errors import VixlError, require

REPAIR_KINDS = ("fit-text", "contrast-ink", "safe-area-nudge", "hold")
SUGGEST_LIMIT = 10  # Fix findings a check annotates with a repair; the rest say how to ask for more.
MAX_REPAIRS = 10
INK_STEPS = (0.25, 0.5, 0.75, 1.0)
FIT_TEXT_MINIMUM = 12  # fit-text's own default smallest size.


def kind_for(rule):
    if rule in ("bounds.text-overflow", "suite.text-fit"):
        return "fit-text"
    if rule in ("contrast.text-contrast", "suite.contrast"):
        return "contrast-ink"
    if rule in ("safe_area.outside", "bounds.cut-off"):
        return "safe-area-nudge"
    if rule.startswith("blanks"):
        return "hold"
    return None


def unavailable(reason, kind=None):
    return {"kind": kind, "available": False, "operations": [], "reason": reason}


def _raw(project, finding):
    ids = finding.get("layer_ids") or []
    try:
        return project.layer(ids[0] if ids else finding["layers"][0])
    except (VixlError, IndexError, KeyError):
        return None


def _resolved(project, layer):
    from .render import resolved_layers

    return next((x for x in resolved_layers(project) if x["id"] == layer["id"]), layer)


def minimum_size(project, layer, minimum=None):
    """The smallest size a repair may set: the rule's ``minimum`` when given, else the larger of fit-text's
    default and, for social and poster pieces, the house style's minimum share of the short side."""
    if minimum is not None:
        return max(1, math.ceil(minimum))
    from .house_style import purpose_for, rule

    canvas = project.state["canvas"]
    floor = FIT_TEXT_MINIMUM
    purpose = project.state.get("design_defaults", {}).get("purpose") or purpose_for(canvas.get("size"))
    if purpose in ("social", "poster") and not (canvas.get("physical") and canvas.get("dpi")):
        floor = max(floor, math.ceil(rule("minimum_text")["minor_share_of_short_side"]
                                     * min(canvas["width"], canvas["height"])))
    for suite in project.state.get("suites", {}).values():
        for item in suite.get("rules", []):
            if item.get("kind") == "text-fit" and item.get("minimum") is not None:
                try:
                    if project.layer(item["target"])["id"] == layer["id"]:
                        floor = max(floor, math.ceil(item["minimum"]))
                except VixlError:
                    continue
    return floor


def _fit_text(project, finding, layer):
    from .automation import text_fits

    if layer["type"] != "text":
        return unavailable("fit-text needs a text layer", "fit-text")
    resolved = _resolved(project, layer)
    width, height = int(resolved.get("width", 0)), int(resolved.get("height", 0))
    if width < 1 or height < 1:
        return unavailable("the text has no box to fit", "fit-text")
    low = minimum_size(project, layer, finding.get("minimum"))
    size = layer.get("size", 0)
    if size <= low:
        return unavailable(f"the text is already at its minimum size ({low} px); enlarge its box instead "
                           "(workflow repair-layout)", "fit-text")
    try:
        fits = text_fits(project, layer, low, width, height)
    except Exception:  # noqa: BLE001 - text that cannot be measured has no mechanical repair
        fits = False
    if not fits:
        return unavailable(f"the text does not fit its {width}×{height} box even at the minimum size ({low} px); "
                           "enlarge the box or shorten the copy (workflow repair-layout tries box changes)",
                           "fit-text")
    return {"kind": "fit-text", "available": True,
            "operations": [{"type": "fit-text", "target": layer["id"], "width": width, "height": height,
                            "minimum": low, "maximum": int(size)}],
            "reason": f"shrink the text to fit its {width}×{height} box, not below {low} px"}


def role_ink(project):
    """The document's ``@ink`` swatch as RGB, or None."""
    from .design import resolve_color
    from .render import color

    if "ink" not in project.state.get("swatches", {}):
        return None
    try:
        return color(resolve_color("@ink", project.state))[:3]
    except (VixlError, ValueError):
        return None


def _hex(rgb):
    return "#" + "".join(f"{max(0, min(255, round(v))):02x}" for v in rgb)


def _backdrop(project, layer, region):
    """The median colour behind the text in ``region``: the document rendered without the layer."""
    import numpy as np

    from .render import view_page

    hidden = view_page(project).clone()
    for item in hidden.state["layers"]:
        if item["id"] == layer["id"]:
            item["visible"] = False
    image = hidden.render().convert("RGB")
    x, y, w, h = (int(v) for v in region)
    crop = np.asarray(image.crop((max(0, x), max(0, y), max(x + 1, x + w), max(y + 1, y + h))))
    return tuple(float(v) for v in np.median(crop.reshape(-1, 3), axis=0))


def _contrast_ink(project, finding, layer):
    from .colors import contrast_ratio
    from .design import resolve_color
    from .render import color

    if layer["type"] != "text":
        return unavailable("contrast-ink needs a text layer", "contrast-ink")
    required = finding.get("required") or finding.get("expected") or 4.5
    region = finding.get("region") or finding.get("weakest_region") or finding.get("box")
    if not region:
        return unavailable("the finding has no measured region", "contrast-ink")
    try:
        current = color(resolve_color(layer.get("color", "black"), project.state))[:3]
        backdrop = _backdrop(project, layer, region)
    except Exception as exc:  # noqa: BLE001 - an unmeasurable backdrop has no mechanical repair
        return unavailable(f"the backdrop could not be measured ({exc})", "contrast-ink")

    def ratio(rgb):
        return contrast_ratio(tuple(v / 255 for v in rgb), tuple(v / 255 for v in backdrop))

    ink = role_ink(project)
    source = "@ink"
    if ink is None or ratio(ink) < required:
        ink = max(((0, 0, 0), (255, 255, 255)), key=ratio)
        source = "black" if ink == (0, 0, 0) else "white"
    # A margin over the requirement: the check reads the tenth-percentile glyph pixel, not the median.
    for step in INK_STEPS:
        mixed = tuple(a + (b - a) * step for a, b in zip(current, ink))
        if ratio(mixed) >= required * 1.15 or step == 1.0:
            break
    if ratio(mixed) < required:
        return unavailable(f"even the role ink ({source}) does not reach {required:g}:1 on this backdrop; "
                           "add an outline or a panel behind the text", "contrast-ink")
    return {"kind": "contrast-ink", "available": True,
            "operations": [{"type": "text-set", "target": layer["id"], "color": _hex(mixed)}],
            "reason": f"move the text colour {round(step * 100)}% toward the role ink ({source}): about "
                      f"{ratio(mixed):.1f}:1 against the backdrop, needs {required:g}:1"}


def _nudge(project, finding, layer):
    if finding.get("rule") == "bounds.cut-off" and layer["type"] != "text":
        return unavailable("artwork crossing the edge may be deliberate; mark it with layer-intent allow_crop "
                           "or move it", "safe-area-nudge")
    box = finding.get("bounds") or finding.get("box")
    canvas = project.state["canvas"]
    area = finding.get("safe_area") or [0, 0, canvas["width"], canvas["height"]]
    if not box:
        return unavailable("the finding has no measured bounds", "safe-area-nudge")
    x, y, w, h = box
    ax, ay, aw, ah = area
    if w > aw + 0.5 or h > ah + 0.5:
        return unavailable(f"the layer ({round(w)}×{round(h)}) is larger than the area ({round(aw)}×{round(ah)}); "
                           "shrink it first", "safe-area-nudge")
    dx = ax - x if x < ax else (ax + aw) - (x + w) if x + w > ax + aw else 0
    dy = ay - y if y < ay else (ay + ah) - (y + h) if y + h > ay + ah else 0
    dx, dy = math.ceil(dx) if dx > 0 else math.floor(dx), math.ceil(dy) if dy > 0 else math.floor(dy)
    if not dx and not dy:
        return unavailable("the layer is already inside the area", "safe-area-nudge")
    return {"kind": "safe-area-nudge", "available": True,
            "operations": [{"type": "move", "target": layer["id"], "x": dx, "y": dy, "relative": True}],
            "reason": f"move the layer by ({dx}, {dy}) px back inside the "
                      f"{'safe area' if finding.get('safe_area') else 'canvas'}, keeping its anchor"}


def suggest(project, finding):
    """The built-in repair for one finding: ``{kind, available, operations, reason}``. The operations are
    canonical and validate against the operation schema; nothing is applied."""
    from .schema import validate_operation

    rule = finding.get("rule") or finding.get("check", "")
    kind = kind_for(rule)
    if kind is None:
        return unavailable("no mechanical repair for this rule; see the message for the next step")
    if kind == "hold":
        return {"kind": "hold", "available": False, "operations": [],
                "reason": "held for review: supply the real copy or asset (a repair never guesses content)"}
    layer = _raw(project, finding)
    if layer is None:
        return unavailable("the finding names no layer", kind)
    suggestion = {"fit-text": _fit_text, "contrast-ink": _contrast_ink, "safe-area-nudge": _nudge}[kind](
        project, finding, layer)
    if suggestion["available"] and project.state.get("pages") and finding.get("page") is not None:
        for operation in suggestion["operations"]:
            operation["page"] = finding["page"]
    try:
        for operation in suggestion["operations"]:
            validate_operation(dict(operation))
    except VixlError as exc:  # never hand out an operation the schema would refuse
        return unavailable(f"the repair would not validate: {exc}", kind)
    return suggestion


def annotate(project, issues, limit=SUGGEST_LIMIT):
    """Attach ``repair`` suggestions to the first ``limit`` fix findings (in place)."""
    done = 0
    for item in issues:
        if item.get("action") != "fix":
            continue
        if done >= limit:
            item["repair"] = {"available": None, "reason": f"only the first {limit} fix findings get a suggestion; "
                              "check fewer targets or fix these first"}
            continue
        try:
            item["repair"] = suggest(project, item)
        except Exception as exc:  # noqa: BLE001 - a suggestion must never break the check
            item["repair"] = unavailable(f"no suggestion ({type(exc).__name__})")
        done += 1
    return issues


# Suite rules that map onto the same repairs: their results become findings.
def suite_findings(project, reports):
    findings = []
    for name, report in reports.items():
        suite = project.state.get("suites", {}).get(name, {})
        rules = {rule["id"]: rule for rule in suite.get("rules", [])}
        for result in report.get("results", []):
            rule = rules.get(result["id"])
            if result["status"] != "failed" or not rule or rule["kind"] not in ("text-fit", "contrast"):
                continue
            try:
                layer = project.layer(rule["target"])
            except VixlError:
                continue
            finding = {"rule": f"suite.{rule['kind']}", "check": "suite", "suite": name, "suite_rule": rule["id"],
                       "layers": [layer["name"]], "layer_ids": [layer["id"]], "action": "fix", "severity": "error"}
            if rule["kind"] == "text-fit":
                finding["minimum"] = rule.get("minimum")
            else:
                finding.update(required=rule.get("minimum", 4.5), region=result.get("weakest_region"))
            findings.append(finding)
    return findings


def _key(item):
    return item.get("rule"), tuple(item.get("layer_ids") or item.get("layers") or ())


def _state(project, checks, suites):
    from .checks import check_design

    report = check_design(project, checks=checks, repairs=False) if checks is not False else {"issues": []}
    reports = {name: project.check_suite(name) for name in suites}
    fixes = [item for item in report["issues"] if item.get("action") == "fix"] + suite_findings(project, reports)
    failing = {name for name, item in reports.items() if item["status"] == "failed"}
    return fixes, failing, report, reports


def _allowed(kinds):
    if kinds is True or kinds is None:
        return set(REPAIR_KINDS)
    kinds = [kinds] if isinstance(kinds, str) else kinds
    require(isinstance(kinds, list) and set(kinds) <= set(REPAIR_KINDS),
            f"repair is true or a list of {', '.join(REPAIR_KINDS[:-1])}", field="repair")
    return set(kinds) | {"hold"}


def auto_repair(project, *, checks=None, suites=(), kinds=True, max_repairs=MAX_REPAIRS, protected=(),
                dry_run=False):
    """Apply the built-in repair for each fix finding (design ``checks``, plus ``text-fit`` and ``contrast``
    rules of the named ``suites``), one candidate at a time. A repair is kept only when its finding is gone
    and no other fix finding or suite failure appeared; the kept operations are then applied to ``project``
    as one undoable batch (unless ``dry_run``). Returns ``{applied, held, unrepaired, operations, passed}``."""
    allowed = _allowed(kinds)
    require(type(max_repairs) is int and 1 <= max_repairs <= 50, "max_repairs must be 1-50", field="max_repairs")
    suites = list(suites or [])
    protected_ids = {project.layer(ref)["id"] for ref in protected}
    candidate = project.clone()
    fixes, failing, _, _ = _state(candidate, checks, suites)
    applied, held, unrepaired, attempts = [], [], [], 0
    seen = set()
    while attempts < max_repairs:
        pending = [item for item in fixes if _key(item) not in seen]
        if not pending:
            break
        finding = pending[0]
        seen.add(_key(finding))
        entry = {"rule": finding["rule"], "layers": finding.get("layers", []),
                 "layer_ids": finding.get("layer_ids", [])}
        suggestion = suggest(candidate, finding)
        kind = suggestion.get("kind")
        if kind == "hold":
            held.append({**entry, "reason": suggestion["reason"]})
            continue
        if not suggestion["available"] or kind not in allowed:
            unrepaired.append({**entry, "reason": suggestion["reason"] if not suggestion["available"]
                               else f"{kind} repairs were not requested"})
            continue
        if protected_ids & set(entry["layer_ids"]):
            unrepaired.append({**entry, "reason": "the layer is protected"})
            continue
        attempts += 1
        trial = candidate.clone()
        try:
            trial.apply(suggestion["operations"], detail="compact")
            after, after_failing, _, _ = _state(trial, checks, suites)
        except VixlError as exc:
            unrepaired.append({**entry, "reason": f"the repair failed: {exc}"})
            continue
        before_keys = {_key(item) for item in fixes}
        new = [item for item in after if _key(item) not in before_keys]
        if _key(finding) in {_key(item) for item in after}:
            unrepaired.append({**entry, "reason": "the repair did not resolve the finding", "kind": kind})
        elif new or after_failing - failing:
            introduced = [item["rule"] for item in new] + sorted(after_failing - failing)
            unrepaired.append({**entry, "reason": f"the repair introduced {', '.join(introduced)}", "kind": kind})
        else:
            candidate, fixes, failing = trial, after, after_failing
            applied.append({**entry, "kind": kind, "operations": suggestion["operations"],
                            "reason": suggestion["reason"]})
    operations = [operation for item in applied for operation in item["operations"]]
    if operations and not dry_run:
        project.apply(operations, detail="compact")
    remaining = [{"rule": item["rule"], "layers": item.get("layers", [])} for item in fixes]
    return {"applied": applied, "held": held, "unrepaired": unrepaired, "operations": operations,
            "dry_run": dry_run, "passed": not fixes and not failing, "remaining": remaining[:20],
            **({"undo": "one history entry: vixl_history undo (or vixl undo) reverts every repair"}
               if operations and not dry_run else {})}


def campaign(candidate, actions, evaluate):
    """Campaign ``repair_actions``: each name is a document action, or ``auto`` for the built-in map
    (``auto_repair``). Stops as soon as ``evaluate()`` reports every check passed; returns the actions run and the
    last evaluation."""
    checks = evaluate()
    repairs, details = [], []
    from .assurance import digest

    for action in actions:
        if all(r["passed"] for r in checks.values()):
            break
        contract = digest(candidate.state.get("suites", {}))
        if action == "auto":
            names = [name for name in checks if name in candidate.state.get("suites", {})]
            report = auto_repair(candidate, checks=["bounds"] if "design" in checks else False, suites=names)
            details.append(report)
        else:
            candidate.apply({"type": "action-apply", "name": action}, detail="compact")
        require(digest(candidate.state.get("suites", {})) == contract, "Repair changed contracts")
        repairs.append(action)
        checks = evaluate()
    return repairs, checks, details

