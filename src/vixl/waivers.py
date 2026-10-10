"""Waivers: recorded acceptance of a check finding or a suite rule, with a reason and an optional expiry.

One record shape serves every scope::

    {"check": "contrast", "reason": "decorative watermark", "expires": "2026-12-31"}
    {"rule": "headline-size", "suite": "brief", "reason": "...", "expires": "..."}

- **layer** (``layer-intent waive``, or the ``waiver`` operation with a target): stored on the layer as
  ``waive``; it covers that layer's findings of the check, and those of the layers inside it when it is a
  group. ``with`` (overlap only) limits an overlap waiver to the named partner layers.
- **document** (the ``waiver`` operation without a target): stored in ``state["waivers"]``; it covers a design
  check's findings anywhere in the document, or one suite rule.
- **workspace** (``waivers`` in ``.vixl-checks.json``): shared by every document of the workspace; ``target``
  names a layer there. A project group writes its shared waivers into each member as document waivers.

A waived finding is never dropped: its severity becomes ``info``, its action ``informational``, and it carries
``waived`` (the record, its scope and the original severity and action). A waiver applies through the day named
by ``expires``; after that the finding is back with its own severity, carries ``waiver_expired``, and an
``expired waiver`` finding (action ``fix``) asks to fix the finding or renew the waiver, so ``check --strict``
fails until someone decides again.
"""

from datetime import date, datetime, timezone

from .errors import require

FIELDS = {"check", "rule", "suite", "target", "with", "reason", "expires"}
MAX_WAIVERS = 256
MAX_REASON = 500


def check_names():
    from .checks import CHECKS, OPTIONAL_CHECKS
    from .deck import DECK_CHECKS

    return (*CHECKS, *OPTIONAL_CHECKS, *DECK_CHECKS, "coverage")


def today():
    return datetime.now(timezone.utc).date()


def parse_date(value, field="expires"):
    require(isinstance(value, str), f"{field} is a date such as '2026-12-31'", field=field)
    try:
        return date.fromisoformat(value)
    except ValueError:
        require(False, f"{field} must be a date such as '2026-12-31', got {value!r}", field=field)


def expired(record, now=None):
    return "expires" in record and parse_date(record["expires"]) < (now or today())


def record(value, *, scope, field="waive"):
    """A validated waiver record (a check name alone is shorthand for ``{"check": name}``). ``scope`` is
    ``layer``, ``document`` or ``workspace``; the layer and partner references are left as given."""
    if isinstance(value, str):
        value = {"check": value}
    require(isinstance(value, dict), f"{field}: each waiver is a check name or {{check, reason, expires}}", field=field)
    unknown = sorted(set(value) - FIELDS)
    require(not unknown, f"{field}: unknown waiver field(s) {unknown}; use {', '.join(sorted(FIELDS))}", field=field)
    require(("check" in value) != ("rule" in value), f"{field}: a waiver names one check or one suite rule", field=field)
    if "check" in value:
        names = check_names()
        require(value["check"] in names, f"{field}: unknown check {value['check']!r}; use one of {', '.join(names)}",
                field=field)
        require("suite" not in value, f"{field}: suite goes with rule, not check", field=field)
    else:
        require(isinstance(value["rule"], str) and value["rule"], f"{field}: rule is a suite rule id", field=field)
        require(scope != "layer", f"{field}: a suite rule is waived for the document (the waiver operation "
                "without a target), not on a layer", field=field)
        require(isinstance(value.get("suite", ""), str), f"{field}: suite is a suite name", field=field)
        require("target" not in value and "with" not in value, f"{field}: a rule waiver takes no target", field=field)
    if "with" in value:
        require(value.get("check") == "overlap", f"{field}: with names overlap partners, so it needs check 'overlap'",
                field=field)
        require(isinstance(value["with"], list) and value["with"] and all(isinstance(x, str) for x in value["with"]),
                f"{field}: with is a list of layer names", field=field)
    if "target" in value:
        require(scope == "workspace", f"{field}: target belongs to the waiver operation or the workspace file",
                field=field)
        require(isinstance(value["target"], str) and value["target"], f"{field}: target is a layer name", field=field)
    if "reason" in value:
        require(isinstance(value["reason"], str) and len(value["reason"]) <= MAX_REASON,
                f"{field}: reason is text of at most {MAX_REASON} characters", field=field)
    if "expires" in value:
        parse_date(value["expires"], f"{field}.expires")
    return dict(value)


def records(values, *, scope, field="waive"):
    require(isinstance(values, list) and len(values) <= MAX_WAIVERS,
            f"{field} is a list of at most {MAX_WAIVERS} waivers", field=field)
    out = [record(value, scope=scope, field=field) for value in values]
    keys = [key(item) for item in out]
    require(len(set(keys)) == len(keys), f"{field}: one waiver per check (or rule)", field=field)
    return out


def key(item):
    return item.get("check") or ("rule", item.get("suite"), item["rule"]), item.get("target")


def execute(project, op):
    """The ``waiver`` operation: add, replace (same check or rule) or, with ``remove``, delete one waiver.
    With a target it is stored on the layer, otherwise on the document."""
    remove = op.get("remove", False)
    fields = {k: op[k] for k in FIELDS - {"target"} if k in op}
    if op.get("target"):
        layer = project.layer(op["target"])
        item = record(fields, scope="layer", field="waiver")
        if "with" in item:
            item["with"] = [project.layer(name)["id"] for name in item["with"]]
        kept = [x for x in layer.get("waive", []) if key(x) != key(item)]
        if not remove:
            require(item.get("reason"), "A waiver records why: give reason", field="reason")
            kept.append(item)
        if kept:
            layer["waive"] = kept
        else:
            layer.pop("waive", None)
        return
    item = record(fields, scope="document", field="waiver")
    kept = [x for x in project.state.get("waivers", []) if key(x) != key(item)]
    if not remove:
        require(item.get("reason"), "A waiver records why: give reason", field="reason")
        kept.append(item)
    require(len(kept) <= MAX_WAIVERS, f"At most {MAX_WAIVERS} document waivers", field="waiver")
    if kept:
        project.state["waivers"] = kept
    else:
        project.state.pop("waivers", None)


def set_layer(project, layer, values):
    """``layer-intent waive``: replace the layer's waivers (an empty list clears them)."""
    items = records(values, scope="layer")
    for item in items:
        if "with" in item:
            item["with"] = [project.layer(name)["id"] for name in item["with"]]
    if items:
        layer["waive"] = items
    else:
        layer.pop("waive", None)


def validate_state(state):
    """Saved waivers keep the record shape (used by the document validator)."""
    records(state.get("waivers", []), scope="document", field="waivers")
    for layer in state.get("layers", []):
        if "waive" in layer:
            records(layer["waive"], scope="layer", field=f"layer {layer.get('name')!r} waive")


def workspace_waivers(project):
    from .policy import for_project

    return records(for_project(project).get("waivers", []), scope="workspace", field=".vixl-checks.json waivers")


class _Index:
    """Every waiver that applies to a document, with the layer lookups the matching needs."""

    def __init__(self, project, now=None):
        self.now = now or today()
        # Inactive pages keep their layers in their record; the active page's layers win a name clash.
        layers = [layer for page in project.state.get("pages") or [] if isinstance(page, dict)
                  for layer in (page.get("content") or {}).get("layers", [])]
        layers += project.state.get("layers", [])
        self.by_id = {layer["id"]: layer for layer in layers if isinstance(layer, dict) and "id" in layer}
        self.by_name = {layer["name"]: layer for layer in layers if isinstance(layer, dict) and "name" in layer}
        self.entries = []
        for layer in self.by_id.values():
            for item in layer.get("waive", []):
                self.entries.append({"scope": "layer", "layer": layer["id"], "record": item})
        for item in project.state.get("waivers", []):
            self.entries.append({"scope": "document", "record": item})
        try:
            shared = workspace_waivers(project)
        except Exception:  # noqa: BLE001 - an unreadable workspace file must not hide the document's own findings.
            shared = []
        for item in shared:
            self.entries.append({"scope": "workspace", "record": item})
        for entry in self.entries:
            entry["expired"] = expired(entry["record"], self.now)
            entry["matched"] = 0

    def chain(self, name):
        layer = self.by_name.get(name)
        seen = set()
        while layer is not None and layer["id"] not in seen:
            seen.add(layer["id"])
            yield layer
            layer = self.by_id.get(layer.get("parent"))

    def matches(self, entry, item):
        rec = entry["record"]
        if rec.get("check") != item.get("check"):
            return False
        names = item.get("layers") or ([item["layer"]] if item.get("layer") else [])
        if entry["scope"] == "layer":
            for name in names:
                if any(layer["id"] == entry["layer"] for layer in self.chain(name)):
                    partners = rec.get("with")
                    if not partners:
                        return True
                    others = {layer["id"] for other in names if other != name for layer in self.chain(other)}
                    if others & set(partners):
                        return True
            return False
        target = rec.get("target")
        return target is None or any(layer["name"] == target for name in names for layer in self.chain(name))

    def label(self, entry):
        rec = {k: v for k, v in entry["record"].items() if k != "with"}
        if entry["record"].get("with"):
            rec["with"] = [self.by_id[x]["name"] if x in self.by_id else x for x in entry["record"]["with"]]
        out = {"scope": entry["scope"], **rec}
        if entry["scope"] == "layer":
            out["layer"] = self.by_id[entry["layer"]]["name"]
        return out


def apply(project, report, checks=None, now=None):
    """Apply the document's waivers to a check report in place and return it. Findings already marked
    (``waived`` or ``waiver_expired``) are left alone, so applying twice changes nothing."""
    index = _Index(project, now)
    if not index.entries:
        return report
    from .checks import classify

    issues = report.setdefault("issues", [])
    for item in issues:
        if item.get("waived") or item.get("waiver_expired") or item.get("code") == "waiver-expired":
            continue
        found = [entry for entry in index.entries if "check" in entry["record"] and index.matches(entry, item)]
        active = [entry for entry in found if not entry["expired"]]
        if active:
            entry = active[0]
            entry["matched"] += 1
            item["waived"] = {**index.label(entry), "severity": item["severity"], "action": classify(item)}
            item["severity"], item["action"] = "info", "informational"
        elif found:
            found[0]["matched"] += 1
            item["waiver_expired"] = index.label(found[0])
            item.pop("action", None)
    ran = set(checks or report.get("checked", {}).get("checks") or ())
    known = {(x.get("message"), tuple(x.get("layers", []))) for x in issues if x.get("code") == "waiver-expired"}
    for entry in index.entries:
        rec = entry["record"]
        if not entry["expired"] or "check" not in rec or (ran and rec["check"] not in ran):
            continue
        label = index.label(entry)
        where = f" on {label['layer']!r}" if entry["scope"] == "layer" else (
            f" on {rec['target']!r}" if rec.get("target") else "")
        message = (f"The {entry['scope']} waiver of {rec['check']}{where} expired on {rec['expires']}"
                   + (f" ({rec['reason']})" if rec.get("reason") else "")
                   + "; fix the finding or renew the waiver with a new expires date")
        layers = [label["layer"]] if entry["scope"] == "layer" else ([rec["target"]] if rec.get("target") else [])
        if (message, tuple(layers)) in known:
            continue
        issues.append({"check": rec["check"], "severity": "warning", "layers": layers, "message": message,
                       "code": "waiver-expired", "action": "fix", "waiver": label})
    from .checks import tally

    report.update(tally(issues))
    report["waivers"] = summary(index, "check")
    return report


def apply_suite(project, report, suite_name=None, now=None):
    """Waive failed or needs-review suite results named by a document or workspace rule waiver."""
    index = _Index(project, now)
    entries = [entry for entry in index.entries if "rule" in entry["record"]
               and entry["record"].get("suite") in (None, suite_name)]
    if not entries:
        return report
    for result in report["results"]:
        if result["status"] == "passed":
            continue
        found = [entry for entry in entries if entry["record"]["rule"] == result["id"]]
        active = [entry for entry in found if not entry["expired"]]
        if active:
            active[0]["matched"] += 1
            result["waived"] = {**index.label(active[0]), "status": result["status"]}
            result["status"] = "waived"
        elif found:
            found[0]["matched"] += 1
            result["waiver_expired"] = index.label(found[0])
    results = report["results"]
    errors = sum(r["status"] == "failed" and r["severity"] == "error" for r in results)
    review = sum(r["status"] == "needs_review" or (r["status"] == "failed" and r["severity"] == "warning")
                 for r in results)
    stale = [entry for entry in entries if entry["expired"]]
    # An expired rule waiver needs a decision even when its rule now passes.
    review += sum(1 for entry in stale if not entry["matched"])
    report.update(passed=errors == 0 and review == 0, errors=errors, needs_review=review,
                  status="failed" if errors else "needs_review" if review else "passed")
    report["waivers"] = {"active": [{**index.label(e), "matched": e["matched"]} for e in entries if not e["expired"]],
                         "expired": [{**index.label(e), "matched": e["matched"]} for e in stale]}
    return report


def summary(index, kind):
    entries = [entry for entry in index.entries if kind in entry["record"]]
    return {"active": [{**index.label(e), "matched": e["matched"]} for e in entries if not e["expired"]],
            "expired": [{**index.label(e), "matched": e["matched"]} for e in entries if e["expired"]]}


def listing(project, now=None):
    """Every waiver of a document (layer, document and workspace scope), split into active and expired."""
    index = _Index(project, now)
    return {"active": [index.label(e) for e in index.entries if not e["expired"]],
            "expired": [index.label(e) for e in index.entries if e["expired"]]}
