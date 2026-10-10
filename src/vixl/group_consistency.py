"""Cross-document checks: do the members of a group agree with each other?

Every check in ``checks.py`` looks at one document. These compare comparable properties across
several documents (a project group or a glob) and report the members that differ from the group:
the majority value, or a ``reference`` member's value when one is named.

- layout: placement of brand layers (default: layers named ``*logo*`` or with role ``logo``) as an
  anchor (top-left ... bottom-right), an offset from that anchor and a size, all in fractions of the
  canvas's short side so a story and a square compare;
- type: font families, the headline-to-body size ratio and the type-scale ratio;
- color: swatch values (against the group's ``shared.swatches`` first) and the applied palette;
- structure: layers most members have, and required layers (``required``, brand.json
  ``required_elements``);
- copy: declared facts (prices, names, dates, URLs, legal lines) read from variables, from text
  layers named after the fact, or by pattern from all text, with near-miss spellings of declared
  names.

Findings look like ``check`` issues (check, severity, action, message) plus the property, the
expected value, the member's value and the documents involved.
"""

from collections import Counter
import fnmatch
import re
from statistics import median

from .errors import VixlError, require

CHECKS = ("layout", "type", "color", "structure", "copy")
DEFAULT_LAYERS = ("*logo*",)
OFFSET_TOLERANCE = 0.03
SIZE_TOLERANCE = 0.2
RATIO_TOLERANCE = 0.15
MAX_PATTERN = 500
MAX_FACTS = 50
MONTHS = ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
          "November", "December")


def _finding(check, prop, message, *, documents, expected=None, value=None, action="fix", severity="warning", **extra):
    item = {"check": f"group-{check}", "property": prop, "severity": severity, "action": action, "message": message,
            "documents": documents}
    if expected is not None:
        item["expected"] = expected
    if value is not None:
        item["value"] = value
    item.update(extra)
    return item


def _visible_layers(project):
    """``inspect`` rows of drawn layers, with canvas bounds."""
    rows = project.inspect()["layers"]
    by_id = {layer["id"]: layer for layer in project.state["layers"]}

    def shown(ident):
        while ident:
            layer = by_id.get(ident, {})
            if not layer.get("visible", True):
                return False
            ident = layer.get("parent")
        return True

    return [row for row in rows if shown(row["id"])], by_id


def _expected(values, reference, label):
    """The value members should have: the reference member's, else a strict majority, else None."""
    if reference is not None:
        return values.get(reference), "reference"
    counts = Counter(values.values())
    if not counts:
        return None, label
    value, count = counts.most_common(1)[0]
    if count * 2 > len(values):
        return value, "majority"
    return None, "no majority"


def _no_majority(check, prop, values, describe=str):
    groups = {}
    for document, value in values.items():
        groups.setdefault(describe(value), []).append(document)
    text = "; ".join(f"{value} in {', '.join(docs)}" for value, docs in groups.items())
    return _finding(check, prop, f"{prop} differs with no majority: {text}. Pick one, or name a reference member.",
                    documents=sorted(values), action="review", values=groups)


# Layout -----------------------------------------------------------------------------------------

def _placement(box, width, height):
    x, y, w, h = box
    short = min(width, height)
    cx, cy = x + w / 2, y + h / 2
    col = 0 if cx < width / 3 else 1 if cx > 2 * width / 3 else 0.5
    row = 0 if cy < height / 3 else 1 if cy > 2 * height / 3 else 0.5
    from .geometry import ANCHORS

    anchor = next(name for name, point in ANCHORS.items() if point == (col, row))
    dx = x / short if col == 0 else (width - x - w) / short if col == 1 else (cx - width / 2) / short
    dy = y / short if row == 0 else (height - y - h) / short if row == 1 else (cy - height / 2) / short
    return {"anchor": anchor, "offset": [round(dx, 4), round(dy, 4)], "size": round((w * h) ** 0.5 / short, 4)}


def _describe_place(place):
    return (f"{place['anchor']} (offset {place['offset'][0]:.0%}, {place['offset'][1]:.0%} of the short side, "
            f"size {place['size']:.0%})")


def _layout(projects, reference, patterns, offset_tol, size_tol):
    findings, compared = [], []
    placements = {}
    for document, project in projects.items():
        rows, by_id = _visible_layers(project)
        canvas = project.state["canvas"]
        matched = {row["id"] for row in rows
                   if any(fnmatch.fnmatchcase(row["name"].lower(), p.lower()) for p in patterns)
                   or by_id.get(row["id"], {}).get("role") == "logo"}
        for row in rows:
            if row["id"] not in matched:
                continue
            # A layer inside a matched group is part of that group's placement.
            parent, nested = row.get("parent"), False
            while parent:
                nested = nested or parent in matched
                parent = by_id.get(parent, {}).get("parent")
            if nested:
                continue
            box = row.get("canvas_bounds") or row.get("resolved_bounds")
            if not box or box[2] <= 0 or box[3] <= 0:
                continue
            placements.setdefault(row["name"], {}).setdefault(
                document, _placement(box, canvas["width"], canvas["height"]))
    for name, values in sorted(placements.items()):
        if len(values) < 2 or (reference is not None and reference not in values):
            continue
        compared.append(name)
        anchors = {doc: place["anchor"] for doc, place in values.items()}
        anchor, basis = _expected(anchors, reference, "majority")
        if anchor is None:
            findings.append(_no_majority("layout", f"{name}.anchor", anchors))
            continue
        if reference is not None:
            expected = values[reference]
        else:
            same = [place for place in values.values() if place["anchor"] == anchor]
            expected = {"anchor": anchor, "offset": [round(median(p["offset"][0] for p in same), 4),
                                                     round(median(p["offset"][1] for p in same), 4)],
                        "size": round(median(p["size"] for p in same), 4)}
        for document, place in values.items():
            if document == reference:
                continue
            reasons = []
            if place["anchor"] != expected["anchor"]:
                reasons.append("anchor")
            elif any(abs(a - b) > offset_tol for a, b in zip(place["offset"], expected["offset"])):
                reasons.append("offset")
            if expected["size"] and abs(place["size"] / expected["size"] - 1) > size_tol:
                reasons.append("size")
            if reasons:
                findings.append(_finding(
                    "layout", f"{name}.placement",
                    f"'{name}' in {document} sits at {_describe_place(place)}; the group's {basis} is "
                    f"{_describe_place(expected)}", documents=[document], document=document, layer=name,
                    expected=expected, value=place, differs=reasons))
    return findings, compared


# Type -------------------------------------------------------------------------------------------

def font_name(project, stored):
    """A text layer's font as people name it: the registered name of an embedded font, else the family
    (the file name without its extension)."""
    from pathlib import PurePosixPath

    names = sorted(name for name, asset in project.state.get("fonts", {}).items() if asset == stored)
    if names:
        return names[0]
    text = str(stored)
    return PurePosixPath(text).stem if text.lower().endswith((".ttf", ".otf", ".woff", ".woff2")) else text


def _type_profile(project):
    rows, by_id = _visible_layers(project)
    texts = [by_id[row["id"]] for row in rows if row["type"] == "text" and by_id.get(row["id"], {}).get("text")]
    fonts = tuple(sorted({font_name(project, layer.get("font", "")) for layer in texts}))
    sizes = [(float(layer.get("size", 0)), len(str(layer.get("text", "")))) for layer in texts if layer.get("size")]
    profile = {"fonts": fonts}
    distinct = sorted({size for size, _ in sizes}, reverse=True)
    if len(distinct) >= 2:
        body = max(sizes, key=lambda item: (item[1], -item[0]))[0]
        profile["headline_ratio"] = round(distinct[0] / body, 3) if body else None
        steps = [a / b for a, b in zip(distinct, distinct[1:]) if b]
        profile["scale_ratio"] = round((distinct[0] / distinct[-1]) ** (1 / len(steps)), 3) if steps else None
    return profile


def _ratio_findings(prop, values, reference, tol, label):
    findings = []
    values = {doc: value for doc, value in values.items() if value}
    if len(values) < 2 or (reference is not None and reference not in values):
        return findings
    expected = values[reference] if reference is not None else round(median(values.values()), 3)
    basis = "reference" if reference is not None else "median"
    for document, value in values.items():
        if document != reference and abs(value / expected - 1) > tol:
            findings.append(_finding("type", prop, f"{document} has a {label} of {value:g}; the group's {basis} is "
                                     f"{expected:g}", documents=[document], document=document, expected=expected,
                                     value=value))
    return findings


def _type(projects, reference, tol):
    profiles = {doc: _type_profile(project) for doc, project in projects.items()}
    findings = []
    fonts = {doc: profile["fonts"] for doc, profile in profiles.items() if profile["fonts"]}
    if len(fonts) >= 2 and (reference is None or reference in fonts):
        expected, basis = _expected(fonts, reference, "majority")
        if expected is None:
            findings.append(_no_majority("type", "fonts", fonts, lambda v: ", ".join(v)))
        else:
            for document, value in fonts.items():
                if value != expected and document != reference:
                    findings.append(_finding(
                        "type", "fonts", f"{document} uses {', '.join(value)}; the group's {basis} is "
                        f"{', '.join(expected)}", documents=[document], document=document, expected=list(expected),
                        value=list(value), missing=sorted(set(expected) - set(value)),
                        extra=sorted(set(value) - set(expected))))
    for prop, label in (("headline_ratio", "headline-to-body size ratio"), ("scale_ratio", "type-scale ratio")):
        findings += _ratio_findings(prop, {doc: p.get(prop) for doc, p in profiles.items()}, reference, tol, label)
    return findings


# Color ------------------------------------------------------------------------------------------

def _rgba(value, state):
    from .design import resolve_color
    from .render import color

    try:
        return tuple(color(resolve_color(value, state)))
    except (VixlError, ValueError, TypeError, KeyError):
        return None


def _close(a, b, tolerance=2):
    return a is not None and b is not None and all(abs(x - y) <= tolerance for x, y in zip(a, b))


def _color(projects, reference, shared):
    findings = []
    names = sorted({name for project in projects.values() for name in project.state.get("swatches", {})})
    for name in names:
        values = {doc: project.state["swatches"][name] for doc, project in projects.items()
                  if name in project.state.get("swatches", {})}
        resolved = {doc: _rgba(value, projects[doc].state) for doc, value in values.items()}
        if name in shared:
            expected_rgba, expected, basis = _rgba(shared[name], {"variables": {}, "swatches": {}}), shared[name], "shared swatch"
        elif reference is not None:
            if reference not in values:
                continue
            expected_rgba, expected, basis = resolved[reference], values[reference], "reference"
        else:
            if len(values) < 2:
                continue
            groups = []
            for doc, rgba in resolved.items():
                for group in groups:
                    if _close(group[0], rgba):
                        group[1].append(doc)
                        break
                else:
                    groups.append((rgba, [doc]))
            best = max(groups, key=lambda g: len(g[1]))
            if len(best[1]) * 2 <= len(values):
                findings.append(_no_majority("color", f"swatch.{name}", values))
                continue
            expected_rgba, expected, basis = best[0], values[best[1][0]], "majority"
        for document, rgba in resolved.items():
            if document != reference and not _close(rgba, expected_rgba):
                findings.append(_finding(
                    "color", f"swatch.{name}", f"@{name} is {values[document]} in {document}; the group's {basis} is "
                    f"{expected}", documents=[document], document=document, expected=expected, value=values[document],
                    fix={"type": "swatch", "name": name, "color": expected}))
    palettes = {doc: (project.state.get("palette_roles") or {}).get("palette") for doc, project in projects.items()}
    palettes = {doc: value for doc, value in palettes.items() if value}
    if len(palettes) >= 2 and (reference is None or reference in palettes):
        expected, basis = _expected(palettes, reference, "majority")
        if expected is None:
            findings.append(_no_majority("color", "palette", palettes))
        else:
            for document, value in palettes.items():
                if value != expected and document != reference:
                    findings.append(_finding("color", "palette", f"{document} uses palette {value}; the group's {basis} "
                                             f"is {expected}", documents=[document], document=document,
                                             expected=expected, value=value))
    return findings


# Structure --------------------------------------------------------------------------------------

def _structure(projects, reference, required):
    findings = []
    names = {doc: {layer["name"] for layer in project.state["layers"]} for doc, project in projects.items()}
    if reference is not None:
        expected = set(names[reference])
        basis = "reference"
    else:
        counts = Counter(name for found in names.values() for name in found)
        expected = {name for name, count in counts.items() if count * 2 > len(names)} if len(names) >= 3 else set()
        basis = "majority"
    for document, found in names.items():
        if document == reference:
            continue
        missing_required = sorted(set(required) - found)
        missing_common = sorted(expected - found - set(required))
        if missing_required:
            findings.append(_finding("structure", "required", f"{document} lacks required layer(s) "
                                     f"{', '.join(missing_required)}", documents=[document], document=document,
                                     expected=list(required), value=missing_required, severity="error"))
        if missing_common:
            findings.append(_finding("structure", "layers", f"{document} lacks {', '.join(missing_common)}, which the "
                                     f"group's {basis} has", documents=[document], document=document,
                                     value=missing_common, action="review"))
    return findings


# Copy -------------------------------------------------------------------------------------------

def date_pattern(fmt):
    """A regex for a date format such as 'MMM D' or 'YYYY-MM-DD' (tokens YYYY YY MMMM MMM MM M DD D)."""
    require(isinstance(fmt, str) and 0 < len(fmt) <= 40, "facts: format is a short date format like 'MMM D'",
            field="facts")
    tokens = {"YYYY": r"\d{4}", "YY": r"\d{2}", "MMMM": "(?:" + "|".join(MONTHS) + ")",
              "MMM": "(?:" + "|".join(m[:3] for m in MONTHS) + r")\.?", "MM": r"\d{2}", "M": r"\d{1,2}",
              "DD": r"\d{2}", "D": r"\d{1,2}"}
    out, index = [], 0
    while index < len(fmt):
        for token in ("YYYY", "MMMM", "MMM", "YY", "MM", "DD", "M", "D"):
            if fmt.startswith(token, index):
                out.append(tokens[token])
                index += len(token)
                break
        else:
            out.append(re.escape(fmt[index]))
            index += 1
    return r"(?<![\w])" + "".join(out) + r"(?![\w])"


def validate_facts(facts, field="facts"):
    require(isinstance(facts, dict) and len(facts) <= MAX_FACTS,
            f"{field} maps fact names to {{pattern|values|format|value, layers?}} (at most {MAX_FACTS})", field=field)
    compiled = {}
    for name, spec in facts.items():
        where = f"{field}.{name}"
        require(isinstance(spec, dict), f"{where} must be an object", field=where)
        unknown = set(spec) - {"pattern", "values", "format", "value", "layers", "ignore_case"}
        require(not unknown, f"{where}: unknown field(s) {sorted(unknown)}; use pattern, values, format, value, layers, "
                "ignore_case", field=where)
        kinds = [key for key in ("pattern", "values", "format") if key in spec]
        require(len(kinds) <= 1, f"{where}: give one of pattern, values or format", field=where)
        flags = re.IGNORECASE if spec.get("ignore_case") else 0
        entry = {"name": name, "layers": spec.get("layers", [name]), "value": spec.get("value")}
        require(isinstance(entry["layers"], list) and all(isinstance(v, str) for v in entry["layers"]),
                f"{where}.layers must be a list of layer names", field=where)
        if "values" in spec:
            values = spec["values"]
            require(isinstance(values, list) and values and all(isinstance(v, str) and v.strip() for v in values),
                    f"{where}.values must be a list of the accepted spellings", field=where)
            entry["values"] = values
            entry["regex"] = re.compile("|".join(r"(?<!\w)" + re.escape(v) + r"(?!\w)" for v in values),
                                        flags | re.IGNORECASE)
        else:
            pattern = spec.get("pattern") if "pattern" in spec else date_pattern(spec["format"]) if "format" in spec else None
            if pattern is not None:
                require(isinstance(pattern, str) and 0 < len(pattern) <= MAX_PATTERN,
                        f"{where}.pattern must be a regex of at most {MAX_PATTERN} characters", field=where)
                try:
                    entry["regex"] = re.compile(pattern, flags)
                except re.error as exc:
                    raise VixlError("invalid_request", f"{where}.pattern is not a valid regex: {exc}", field=where) from exc
        require("regex" in entry or entry["value"] is not None,
                f"{where} needs pattern, values, format or value", field=where)
        compiled[name] = entry
    return compiled


def _distance(a, b, limit):
    """Levenshtein distance, or limit + 1 once it is certainly larger."""
    if abs(len(a) - len(b)) > limit:
        return limit + 1
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        current = [i]
        for j, cb in enumerate(b, 1):
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (ca != cb)))
        if min(current) > limit:
            return limit + 1
        previous = current
    return previous[-1]


def _texts(project):
    rows, by_id = _visible_layers(project)
    return [(row["name"], str(by_id[row["id"]].get("text", ""))) for row in rows
            if row["type"] == "text" and by_id.get(row["id"], {}).get("text")]


def _read_fact(project, fact):
    """``(values, source)``: from a variable, else text layers named for the fact, else a regex over all text."""
    variables = project.state.get("variables", {})
    if fact["name"] in variables and not isinstance(variables[fact["name"]], (dict, list)):
        return [str(variables[fact["name"]])], "variable"
    texts = _texts(project)
    named = [text for name, text in texts if name in fact["layers"]]
    if named:
        if fact.get("regex") is not None:
            found = [m.group(0) for text in named for m in fact["regex"].finditer(text)]
            return (found or [text.strip() for text in named]), "layer"
        return [text.strip() for text in named], "layer"
    if fact.get("regex") is None:
        return [], None
    return [m.group(0) for _, text in texts for m in fact["regex"].finditer(text)], "text"


def _near_misses(project, fact):
    """Spellings within a small edit distance of a declared value that are not themselves declared."""
    declared = {value.casefold() for value in fact["values"]}
    misses = []
    for layer, text in _texts(project):
        words = re.findall(r"[\w$€£¥.'’-]+", text)
        for value in fact["values"]:
            size = len(value.split())
            limit = max(1, len(value) // 5)
            for start in range(len(words) - size + 1):
                candidate = " ".join(words[start:start + size]).strip(".")
                if candidate.casefold() in declared:
                    continue
                distance = _distance(candidate.casefold(), value.casefold(), limit)
                if 0 < distance <= limit:
                    misses.append({"layer": layer, "found": candidate, "suggestion": value, "distance": distance})
    return misses


def _copy(projects, reference, facts):
    findings = []
    for fact in facts.values():
        values, sources = {}, {}
        for document, project in projects.items():
            found, source = _read_fact(project, fact)
            if found:
                canonical = sorted(set(found))
                values[document] = canonical[0] if len(canonical) == 1 else " | ".join(canonical)
                sources[document] = source
            if fact.get("values"):
                for miss in _near_misses(project, fact):
                    findings.append(_finding(
                        "copy", fact["name"], f"{document}: '{miss['found']}' in '{miss['layer']}' looks like a "
                        f"misspelling of '{miss['suggestion']}'", documents=[document], document=document,
                        layer=miss["layer"], value=miss["found"], expected=miss["suggestion"],
                        suggestion=miss["suggestion"], severity="error"))
        if fact.get("values"):
            declared = {value.casefold(): value for value in fact["values"]}
            for document, value in values.items():
                parts = value.split(" | ")
                if any(part.casefold() not in declared for part in parts) and sources[document] != "text":
                    findings.append(_finding("copy", fact["name"], f"{fact['name']} is '{value}' in {document}; "
                                             f"declared: {', '.join(fact['values'])}", documents=[document],
                                             document=document, value=value, expected=fact["values"]))
            continue
        if len(values) < 1:
            continue
        if fact.get("value") is not None:
            expected, basis = str(fact["value"]), "declared value"
        elif reference is not None:
            if reference not in values:
                continue
            expected, basis = values[reference], "reference"
        else:
            if len(set(values.values())) <= 1:
                continue
            expected, basis = _expected(values, None, "majority")
        groups = {}
        for document, value in values.items():
            groups.setdefault(value, []).append(document)
        if expected is None:
            findings.append(_no_majority("copy", fact["name"], values))
            continue
        wrong = {value: docs for value, docs in groups.items() if value != expected}
        if not wrong:
            continue
        listing = "; ".join(f"'{value}' in {', '.join(sorted(docs))}" for value, docs in groups.items())
        findings.append(_finding(
            "copy", fact["name"], f"{fact['name']} differs across documents: {listing} (the {basis} is '{expected}')",
            documents=sorted(doc for docs in wrong.values() for doc in docs), expected=expected, values=groups,
            severity="error"))
    return findings


def compare(projects, *, reference=None, checks=None, layers=None, facts=None, shared_swatches=None, required=None,
            tolerance=None):
    """Compare ``projects`` ({document: Project}). Returns {passed, members, findings, compared}."""
    checks = list(checks or CHECKS)
    bad = [check for check in checks if check not in CHECKS]
    require(not bad, f"Unknown group check(s) {bad}; use {', '.join(CHECKS)}", field="checks", allowed=list(CHECKS))
    require(len(projects) >= 2, "Compare at least two documents", field="documents")
    require(reference is None or reference in projects, f"reference {reference!r} is not one of the members",
            field="reference", allowed=sorted(projects))
    tolerance = tolerance or {}
    require(isinstance(tolerance, dict) and set(tolerance) <= {"offset", "size", "ratio"},
            "tolerance is {offset?, size?, ratio?}", field="tolerance")
    patterns = layers or list(DEFAULT_LAYERS)
    require(isinstance(patterns, list) and all(isinstance(p, str) for p in patterns),
            "layers must be a list of layer names or globs", field="layers")
    findings, compared = [], {}
    if "layout" in checks:
        found, names = _layout(projects, reference, patterns, tolerance.get("offset", OFFSET_TOLERANCE),
                               tolerance.get("size", SIZE_TOLERANCE))
        findings += found
        compared["layers"] = names
    if "type" in checks:
        findings += _type(projects, reference, tolerance.get("ratio", RATIO_TOLERANCE))
    if "color" in checks:
        findings += _color(projects, reference, shared_swatches or {})
    if "structure" in checks:
        findings += _structure(projects, reference, required or [])
    if "copy" in checks and facts:
        compiled = validate_facts(facts) if not all(isinstance(v, dict) and "name" in v for v in facts.values()) else facts
        findings += _copy(projects, reference, compiled)
        compared["facts"] = sorted(compiled)
    errors = sum(item["severity"] == "error" for item in findings)
    return {"passed": not any(item["action"] == "fix" for item in findings), "members": sorted(projects),
            "reference": reference, "checks": checks, "errors": errors,
            "warnings": sum(item["severity"] == "warning" for item in findings), "findings": findings,
            "compared": compared}


def facts_for(session, group=None, request_facts=None):
    """Declared facts: brand.json ``facts``, then the group's, then the request's (later ones win)."""
    from .brand import load

    facts = dict(load(session.workspace).get("facts", {}))
    facts.update((group or {}).get("facts", {}))
    facts.update(request_facts or {})
    return facts


def run(session, request):
    """The ``group-check`` workflow action."""
    from .workspace_checks import members, load_projects
    from .brand import load

    paths, group = members(session, request)
    projects = load_projects(session, paths)
    reference = request.get("reference")
    if reference is not None:
        require(isinstance(reference, str), "reference is a member path", field="reference")
        reference = session.relative(session.resolve(reference))
    kit = load(session.workspace)
    required = list(request.get("required", [])) + list(kit.get("required_elements", []))
    result = compare(projects, reference=reference, checks=request.get("checks"), layers=request.get("layers"),
                     facts=facts_for(session, group, request.get("facts")),
                     shared_swatches=((group or {}).get("shared") or {}).get("swatches"),
                     required=required, tolerance=request.get("tolerance"))
    if group:
        result["group"] = group["name"]
    return result
