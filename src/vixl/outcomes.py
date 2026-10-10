"""Outcome states shared by apply, check, act, workflows, production, jobs, exports and proof pages.

A result answers three separate questions, so a finished render is never read as an approved deliverable:

- ``execution``: did the work run? ``completed``, ``failed``, ``cancelled`` or ``pending`` (queued, running,
  waiting).
- ``validation``: did the required checks pass? ``passed``, ``failed``, ``incomplete`` (a required rule could
  not be measured) or ``not_run`` (nothing required was checked).
- ``review``: does someone still have to look? ``required`` or ``not_required``, with ``review_reasons``.

``state`` is the one-word summary: ``execution_failed``, ``cancelled``, ``pending``, ``validation_failed``,
``unvalidated``, ``needs_review`` or ``validated``. ``accepted`` lists findings the document marked as
deliberate (``layer-intent``), each with its rule, layers and reason; acceptance covers only those findings.
"""

EXECUTION = ("completed", "failed", "cancelled", "pending")
VALIDATION = ("passed", "failed", "incomplete", "not_run")
# Worst first: a batch's overall state is the worst of its items.
STATES = ("execution_failed", "cancelled", "pending", "validation_failed", "unvalidated", "needs_review", "validated")
MAX_REASONS = 20


def state_of(execution, validation, review):
    if execution != "completed":
        return {"failed": "execution_failed", "cancelled": "cancelled"}.get(execution, "pending")
    if validation == "failed":
        return "validation_failed"
    if validation == "not_run":
        return "unvalidated"
    if validation == "incomplete" or review == "required":
        return "needs_review"
    return "validated"


def make(execution="completed", validation="not_run", reasons=(), accepted=(), validated_by=()):
    """One outcome. ``reasons`` are short strings naming what still needs a look; a validation that is not
    a pass always needs review, so its reason is added when none is given."""
    assert execution in EXECUTION and validation in VALIDATION
    reasons = list(dict.fromkeys(reasons))
    if execution == "completed" and validation == "not_run" and not reasons:
        reasons = ["no required checks ran"]
    if validation == "incomplete" and not reasons:
        reasons = ["a required check could not be measured"]
    review = "required" if reasons or validation in ("failed", "incomplete", "not_run") else "not_required"
    result = {
        "state": state_of(execution, validation, review),
        "execution": execution,
        "validation": validation,
        "review": review,
        "review_reasons": reasons[:MAX_REASONS],
    }
    if len(reasons) > MAX_REASONS:
        result["review_reasons_omitted"] = len(reasons) - MAX_REASONS
    if accepted:
        result["accepted"] = list(accepted)[:MAX_REASONS]
    if validated_by:
        result["validated_by"] = list(dict.fromkeys(validated_by))
    return result


def _layers(item):
    return item.get("layers") or ([item["layer"]] if item.get("layer") else [])


def describe(item):
    """``rule: layer, layer`` for a finding or a suite rule result."""
    rule = item.get("rule") or item.get("id") or item.get("check", "check")
    layers = _layers(item)
    return f"{rule}: {', '.join(map(str, layers[:3]))}" if layers else str(rule)


def from_findings(issues, execution="completed"):
    """The outcome of a design check: any ``fix`` finding fails validation, ``review`` findings need review,
    and findings the document marked as deliberate are listed as accepted."""
    fixes = [item for item in issues if item.get("action") == "fix" or item.get("severity") == "error"]
    reasons = [describe(item) for item in issues if item.get("action") == "review"]
    accepted = [{"rule": item.get("rule", item.get("check")), "layers": _layers(item),
                 "reason": item.get("message", "")} for item in issues if item.get("intentional")]
    return make(execution, "failed" if fixes else "passed", reasons, accepted, ["design checks"])


def from_suite(report, name=None):
    """The outcome of one check-suite report (``run_suite``): failed error rules fail validation, a rule that
    could not be measured makes it incomplete, failed warning rules need review."""
    results = report.get("results", [])
    unmeasured = [r for r in results if r.get("status") == "needs_review" and r.get("severity", "error") == "error"]
    reasons = [describe(r) + (" (could not be measured)" if r.get("status") == "needs_review" else " (warning)")
               for r in results if r.get("status") == "needs_review"
               or (r.get("status") == "failed" and r.get("severity") == "warning")]
    validation = "failed" if report.get("errors") else "incomplete" if unmeasured else "passed"
    return make("completed", validation, reasons, (), [f"suite {name}" if name else "suite"])


def merge(*outcomes, execution=None):
    """Several outcomes of one output (design checks plus suites) as one. Validation is the worst that ran."""
    outcomes = [item for item in outcomes if item]
    if not outcomes:
        return make(execution or "completed")
    order = {"failed": 0, "incomplete": 1, "passed": 2, "not_run": 3}
    ran = [item["validation"] for item in outcomes if item["validation"] != "not_run"]
    validation = min(ran, key=order.get) if ran else "not_run"
    executions = [item["execution"] for item in outcomes]
    execution = execution or next((e for e in ("failed", "cancelled", "pending") if e in executions), "completed")
    reasons = [r for item in outcomes for r in item["review_reasons"] if not (ran and r == "no required checks ran")]
    accepted = [a for item in outcomes for a in item.get("accepted", [])]
    validated_by = [v for item in outcomes for v in item.get("validated_by", [])]
    return make(execution, validation, reasons, accepted, validated_by)


def of_status(status, *, validation="not_run", reasons=()):
    """Map a legacy job or production ``status`` to an outcome when nothing more specific is known."""
    execution = {"completed": "completed", "reused": "completed", "needs_review": "completed",
                 "failed": "failed", "cancelled": "cancelled"}.get(status, "pending")
    if status == "needs_review" and not reasons:
        reasons = ["marked needs_review"]
    return make(execution, validation, reasons)


def summarize(outcomes):
    """The overall state of a batch (the worst item) with a count per state; items keep their own outcomes."""
    outcomes = list(outcomes)
    counts = {}
    for item in outcomes:
        counts[item["state"]] = counts.get(item["state"], 0) + 1
    worst = min((item["state"] for item in outcomes), key=STATES.index, default="unvalidated")
    return {"state": worst, "total": len(outcomes), "counts": counts,
            "validated": counts.get("validated", 0) == len(outcomes) and bool(outcomes)}
