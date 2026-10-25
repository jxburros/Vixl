"""The locale check: run the design checks and suites once per locale and report a locale x finding matrix.

For each locale a candidate copy of the document gets that locale's variable values, its font fallbacks and, for a
right-to-left locale, a mirrored layout (``mirror.py``); nothing is saved. The source locale is checked the same
way first, and a locale's findings that the source has too are left out of its row (they are the master's own,
and appear in the source row). Findings fall into these kinds:

- ``overflow``: text cut off by its box or running off the canvas (``bounds``), or a failed ``text-fit`` rule;
- ``fonts``: characters no font can draw (an error) or fallback glyphs (a warning);
- ``untranslated``: a value equal to the source's, unless its key or value is in ``same_ok``;
- ``missing-key``: a key other locales have and this one lacks (the source text would show);
- ``line-count``: a text layer sets in a different number of lines than in the source and a ``hierarchy`` rule
  that passes in the source fails;
- ``design`` and ``suites``: any other new design finding or failed suite rule.

``fail_on`` (error, warning or never) decides ``passed``. ``markdown`` renders the matrix and then the per-locale
findings through the workspace report's Markdown renderer (``workspace_checks.markdown``).
"""

from copy import deepcopy
from pathlib import Path

from ...errors import VixlError, require
from .locales import DEFAULT_MIN_SIZE, DEFAULT_SOURCE, OPTIONS, fit_policy, is_rtl, load_strings, locale_table, \
    missing_keys, options, select

KINDS = ("overflow", "fonts", "untranslated", "missing-key", "line-count", "design", "suites")
LEVELS = ("error", "warning", "never")
MAX_FINDINGS = 200


def request_options(request):
    return {key: request[key] for key in OPTIONS if key in request}


def strings_path(project, value):
    """A strings CSV path inside the document's workspace."""
    workspace = Path(getattr(project, "_workspace", None) or Path.cwd()).resolve()
    require(isinstance(value, str) and value, "strings is a CSV path", field="strings")
    path = (workspace / value).resolve()
    try:
        path.relative_to(workspace)
    except ValueError:
        raise VixlError("path_outside_workspace", "strings must be inside the workspace", field="strings") from None
    require(path.is_file(), f"The strings CSV does not exist: {value}", "not_found", field="strings")
    return path


def request_strings(project, request):
    if not request.get("strings"):
        return None
    loaded = load_strings(strings_path(project, request["strings"]), key_column=request.get("key_column", "key"),
                          languages=request.get("languages"))
    loaded["path"] = request["strings"]
    return loaded


def localized(project, code, table, opts, *, fit=False):
    """``(candidate, notes)``: a copy of ``project`` with locale ``code``'s values, its font fallbacks, a mirrored
    layout when it is right to left, and with ``fit`` the shrink policy applied to text that overflows."""
    from ...render import LayerCache
    from .mirror import mirror

    candidate = project.clone()
    candidate._cache, candidate._decoded = LayerCache(), {}
    candidate.state.setdefault("variables", {}).update(deepcopy(table.get(code, {})))
    notes = {"rtl": is_rtl(code, opts)}
    fonts = opts.get("fonts", {}).get(code)
    if fonts:
        current = candidate.state.get("font_fallbacks", [])
        candidate.apply({"type": "font-fallbacks", "fonts": [*fonts, *(f for f in current if f not in fonts)]},
                        detail="compact")
        notes["fonts"] = list(fonts)
    if notes["rtl"] and opts.get("mirror", True):
        notes["mirrored"] = mirror(candidate)
    if fit:
        notes["repairs"] = shrink(candidate, opts)
    return candidate, notes


def shrink(candidate, opts):
    """Apply ``fit-text`` (down to ``min_size``) to each boxed text layer that overflows and whose fit policy is
    shrink. Returns one repair record per layer tried."""
    from ...checks import boxed_text_overflow
    from ...render import resolved_layers

    minimum = opts.get("min_size", DEFAULT_MIN_SIZE)
    repairs = []
    for layer in resolved_layers(candidate):
        if layer["type"] != "text" or not layer.get("visible", True) or fit_policy(opts, layer) != "shrink":
            continue
        if not boxed_text_overflow(candidate, layer):
            continue
        size = int(layer["size"])
        record = {"layer": layer["name"], "action": "fit-text", "from": layer["size"]}
        if size < minimum:
            repairs.append({**record, "failed": f"already below min_size {minimum}"})
            continue
        try:
            candidate.apply({"type": "fit-text", "target": layer["id"], "width": max(1, round(layer["width"])),
                             "height": max(1, round(layer["height"])), "minimum": minimum, "maximum": size},
                            detail="compact")
        except VixlError as exc:
            repairs.append({**record, "failed": str(exc)})
            continue
        repairs.append({**record, "to": candidate.layer(layer["id"])["size"]})
    return repairs


def line_counts(project):
    """{layer name: lines} for every visible text layer, as it is drawn (fitted size, wrapping box)."""
    from ...render import document_variables, resolved_layers
    from ...text import UnsupportedText, font_data, lines, plan
    from ...variables import layer_text

    counts = {}
    variables = document_variables(project)
    for layer in resolved_layers(project):
        if layer["type"] != "text" or not layer.get("visible", True):
            continue
        settings = layer.get("text_layout") or {}
        if settings.get("path") or settings.get("warp", "none") != "none":
            continue
        try:
            size = plan(project, layer).size or layer["size"]
            width = layer["width"] if "width" in settings else None
            counts[layer["name"]] = len(lines(font_data(project, layer), layer_text(layer, variables), size, width,
                                              settings.get("wrap", "greedy")))
        except (VixlError, UnsupportedText, ValueError, KeyError):
            continue
    return counts


def suite_names(project, request):
    from ...assurance import effective

    value = request.get("suites", True)
    if value is False:
        return []
    available = effective(project)
    if value is True or value is None:
        return list(available)
    require(isinstance(value, list) and all(isinstance(v, str) for v in value), "suites is a list of suite names",
            field="suites")
    unknown = [name for name in value if name not in available]
    require(not unknown, f"Unknown suite(s) {unknown}; attached or inherited: {', '.join(available) or 'none'}",
            field="suites", suggestions=sorted(available))
    return list(value)


def evaluate(candidate, request, suites):
    options = {"checks": request["checks"]} if request.get("checks") else {}
    report = candidate.check(**options)
    reports = {name: candidate.check_suite(name) for name in suites}
    if request.get("suite") is not None:
        reports["inline"] = candidate.check_suite(request["suite"])
    rules = {}
    for name, suite in reports.items():
        for rule in suite.get("results", []):
            rules[(name, rule.get("id"))] = rule
    definitions = {name: name for name in suites}
    if request.get("suite") is not None:
        definitions["inline"] = request["suite"]
    return {"issues": report.get("issues", []), "rules": rules, "lines": line_counts(candidate),
            "suites": reports, "suite_rules": _suite_rules(candidate, definitions)}


def _suite_rules(candidate, definitions):
    """{(suite, rule id): rule definition} for the suites that ran, to read a rule's kind and targets."""
    from ...assurance import resolve

    found = {}
    for name, suite in definitions.items():
        try:
            suite, _ = resolve(candidate, suite)
        except (VixlError, TypeError):
            continue
        for rule in suite.get("rules", []):
            found[(name, rule["id"])] = rule
    return found


def _issue_key(issue):
    return issue.get("check"), issue.get("code"), issue.get("severity"), tuple(issue.get("layers", ()))


def _text_ids(candidate):
    return {layer["id"] for layer in candidate.state["layers"] if layer["type"] == "text"}


def classify(issue, text_ids):
    if issue.get("check") == "fonts":
        return "fonts"
    if issue.get("check") == "bounds" and issue.get("layer_ids") and set(issue["layer_ids"]) <= text_ids:
        return "overflow"
    return "design"


def finding(locale, kind, severity, message, layers=(), **extra):
    return {"locale": locale, "kind": kind, "severity": severity, "message": f"{locale}: {message}",
            "layers": list(layers), **extra}


def compare(code, candidate, current, baseline, table, source, opts, strings=None, source_row=False):
    """The findings locale ``code`` adds over the source (every finding, for the source row itself)."""
    found = []
    known = set() if source_row else {_issue_key(i) for i in baseline["issues"]}
    text_ids = _text_ids(candidate)
    for issue in current["issues"]:
        if issue.get("severity") not in ("error", "warning") or issue.get("waived") or _issue_key(issue) in known:
            continue
        kind = classify(issue, text_ids)
        extra = {"check": issue.get("check")}
        if issue.get("code"):
            extra["code"] = issue["code"]
        if issue.get("missing"):
            extra["missing"] = issue["missing"]
        found.append(finding(code, kind, issue["severity"], issue["message"], issue.get("layers", ()), **extra))
    changed_lines = {name: (baseline["lines"].get(name), count) for name, count in current["lines"].items()
                     if name in baseline["lines"] and baseline["lines"][name] != count}
    for key, rule in current["rules"].items():
        if rule.get("status") not in ("failed", "needs_review"):
            continue
        before = baseline["rules"].get(key, {})
        if not source_row and before.get("status") == rule.get("status"):
            continue
        definition = current["suite_rules"].get(key, {})
        kind = definition.get("kind") or rule.get("kind")
        severity = "error" if rule["status"] == "failed" and rule.get("severity", "error") == "error" else "warning"
        targets = [t for t in definition.get("targets", [definition.get("target")]) if t]
        names = [candidate.layer(t)["name"] for t in targets if candidate.find_layer(t) is not None]
        label = f"suite {key[0]} rule {key[1]!r}"
        if key[1] == "missing-glyphs":
            continue  # The design check's fonts finding already names the characters and layers.
        if kind == "text-fit":
            found.append(finding(code, "overflow", severity, f"{label}: {', '.join(names) or 'text'} does not fit "
                                 f"({rule.get('message') or rule['status']})", names, rule=key[1], suite=key[0]))
        elif kind == "hierarchy" and not source_row and any(name in changed_lines for name in names):
            moved = [f"{name!r} sets in {changed_lines[name][1]} line(s) ({changed_lines[name][0]} in {source})"
                     for name in names if name in changed_lines]
            found.append(finding(code, "line-count", severity, f"{'; '.join(moved)}, and the hierarchy {label} "
                                 "no longer holds", names, rule=key[1], suite=key[0],
                                 lines={name: list(changed_lines[name]) for name in names if name in changed_lines}))
        else:
            found.append(finding(code, "suites", severity, f"{label} {rule['status']}"
                                 + (f": {rule['message']}" if rule.get("message") else ""), names, rule=key[1],
                                 suite=key[0]))
    if source_row:
        return found, changed_lines
    same_ok = set(opts.get("same_ok", []))
    source_values = table.get(source, {})
    for key in missing_keys(table, code, strings):
        found.append(finding(code, "missing-key", "error", f"no value for {key!r}; the {source} text would show",
                             (), key=key))
    for key, value in table.get(code, {}).items():
        original = source_values.get(key)
        if (isinstance(value, str) and value.strip() and value == original and key not in same_ok
                and value not in same_ok):
            found.append(finding(code, "untranslated", "warning", f"{key!r} is the same as in {source} ({value[:60]!r}); "
                                 "translate it or list it in same_ok", (), key=key))
    return found, changed_lines


def status(findings, fail_on):
    errors = sum(1 for f in findings if f["severity"] == "error")
    warnings = sum(1 for f in findings if f["severity"] == "warning")
    failing = [f for f in findings if fail_on != "never" and (f["severity"] == "error" or fail_on == "warning")]
    state = "failed" if errors else "needs_review" if warnings else "passed"
    return {"status": state, "errors": errors, "warnings": warnings, "failing": len(failing)}


def check_locales(project, request, *, strings=None):
    """The locale check report for ``project`` (see the module docstring). ``request`` takes ``locales`` (all,
    a comma-separated string or a list), ``checks``, ``suites`` (true, false or names), ``suite`` (an inline
    suite), ``variables``, ``fail_on``, ``strings`` (a CSV in the workspace, with ``key_column`` and
    ``languages``) and the locale options (``source``, ``same_ok``, ``fonts``, ``rtl``, ``mirror``, ``fit``,
    ``min_size``). A ``shrink`` fit policy checks the locales as ``localize`` builds them, after fit-text."""
    fail_on = request.get("fail_on", "error")
    require(fail_on in LEVELS, f"fail_on is one of {', '.join(LEVELS)}", field="fail_on", allowed=list(LEVELS))
    if request.get("variables"):
        require(isinstance(request["variables"], dict), "variables is {name: value}", field="variables")
        project = project.clone()
        project.state.setdefault("variables", {}).update(deepcopy(request["variables"]))
    opts = options(project, request_options(request))
    if strings is None:
        strings = request_strings(project, request)
    table, sources = locale_table(project, strings, opts)
    source = opts.get("source", DEFAULT_SOURCE)
    codes = select(request.get("locales"), table, source)
    suites = suite_names(project, request)
    fit = opts.get("fit", "flag") != "flag"
    base, _ = localized(project, source, table, {**opts, "mirror": False}, fit=fit)
    baseline = evaluate(base, request, suites)
    rows = {source: compare(source, base, baseline, baseline, table, source, opts, strings, source_row=True)[0]}
    results = {source: {"source": True, **status(rows[source], fail_on), "findings": rows[source]}}
    for code in codes:
        candidate, notes = localized(project, code, table, opts, fit=fit)
        current = evaluate(candidate, request, suites)
        found, lines = compare(code, candidate, current, baseline, table, source, opts, strings)
        rows[code] = found
        results[code] = {**status(found, fail_on), "findings": found,
                         "missing": [f["key"] for f in found if f["kind"] == "missing-key"],
                         **({"lines": {name: list(pair) for name, pair in lines.items()}} if lines else {}),
                         **{key: value for key, value in notes.items() if value}}
    matrix = {code: {kind: sum(1 for f in found if f["kind"] == kind) for kind in KINDS} for code, found in rows.items()}
    every = [f for found in rows.values() for f in found]
    failing = sum(results[code]["failing"] for code in results)
    report = {
        "check": "locales",
        "source": source,
        "locales": codes,
        "kinds": list(KINDS),
        "matrix": matrix,
        "results": results,
        "findings": every[:MAX_FINDINGS],
        "count": len(every),
        "fail_on": fail_on,
        "passed": failing == 0,
        "status": "failed" if any(r["status"] == "failed" for r in results.values()) else
                  "needs_review" if any(r["status"] == "needs_review" for r in results.values()) else "passed",
        "sources": sources,
    }
    if strings is not None:
        report["strings"] = {"path": strings.get("path"), "keys": len(strings["keys"]),
                             "languages": strings["languages"], "missing": strings["missing"][:MAX_FINDINGS]}
    document = getattr(project, "path", None)
    if document:
        report["document"] = Path(document).name
    return report


def markdown(report):
    """The matrix as a Markdown table, then each locale's findings through ``workspace_checks.markdown``."""
    from ..workspace_qa.workspace_checks import markdown as workspace_markdown

    kinds = [kind for kind in report["kinds"] if any(row.get(kind) for row in report["matrix"].values())]
    lines = [f"## Vixl locale check{' · `' + report['document'] + '`' if report.get('document') else ''}", "",
             f"Source `{report['source']}` · {len(report['locales'])} locale(s) · fail on `{report['fail_on']}`", ""]
    header = ["Locale", *kinds, "Status"]
    lines += ["| " + " | ".join(header) + " |", "| --- | " + " | ".join("---:" for _ in kinds) + " | --- |"]
    for code, row in report["matrix"].items():
        result = report["results"][code]
        label = f"`{code}`" + (" (source)" if result.get("source") else "") + (" RTL" if result.get("rtl") else "")
        lines.append("| " + " | ".join([label, *(str(row[kind]) for kind in kinds), result["status"]]) + " |")
    documents = []
    for code, result in report["results"].items():
        failing = [f["message"] for f in result["findings"]
                   if report["fail_on"] != "never" and (f["severity"] == "error" or report["fail_on"] == "warning")]
        documents.append({"path": f"{report.get('document') or 'document'}#{code}", "errors": result["errors"],
                          "warnings": result["warnings"], "fix": 0, "status": result["status"], "failing": failing})
    totals = {state: sum(1 for d in documents if d["status"] == state) for state in ("passed", "needs_review", "failed")}
    detail = workspace_markdown({"documents": documents, "fail_on": report["fail_on"], "count": len(documents),
                                 "totals": {**totals, "error": 0}})
    detail = detail.replace("## Vixl document check", "### Per locale", 1)
    return "\n".join(lines) + "\n\n" + detail
