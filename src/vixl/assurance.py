"""Portable design contracts. Checks never mutate artwork or their own expectations."""

from copy import deepcopy
import json
import math

import numpy as np

from .hashing import legacy_hash
from .errors import VixlError, require
from .model import finite


def digest(value):
    # Stored in suite and library records and compared later, so the encoding stays as it was.
    return legacy_hash(value, allow_nan=False)


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
    "text": {"target", "pattern", "contains", "forbid", "min_characters", "max_characters", "min_words", "max_words",
             "case", "brand", "spelling"},
    "budget": {"max_layers", "max_fonts", "max_bytes", "min_ppi", "max_ppi", "max_render_ms", "proxy"},
}
# The limits a budget rule sets (proxy only says how large max_render_ms renders).
BUDGET_LIMITS = ("max_layers", "max_fonts", "max_bytes", "min_ppi", "max_ppi", "max_render_ms")
# Measurements list at most this many worst offenders per limit.
WORST = 5
# Fields that may hold a reference to another document ({"ref": "doc.vixl#layer.field"} or
# {"ref": "doc.vixl#suite:rule-id"}); one suite run resolves at most MAX_REFS of them, nested ones included.
REF_FIELDS = ("expected", "to", "ratio")
MAX_REFS = 8
POSITIONS = ("left-of", "right-of", "above", "below", "inside", "contains", "overlapping", "apart")
EDGES = ("left", "center-x", "right", "top", "center-y", "bottom")
GRIDS = ("thirds", "golden", "center")


SAMPLING_FIELDS = {"mode", "count", "times", "artboards", "pages", "comps", "include_hidden"}


def validate_suite(suite):
    require(
        isinstance(suite, dict) and set(suite) <= {"version", "rules", "sampling", "description", "extends"},
        "Invalid check suite",
    )
    require(suite.get("version", 1) == 1, "Unsupported check suite version")
    # A suite that extends a library suite holds only local overrides and additions (it may hold none).
    extends = suite.get("extends")
    if extends is not None:
        from .design import named

        named(extends)
    rules = suite.get("rules")
    require(isinstance(rules, list) and (0 if extends else 1) <= len(rules) <= 256, "Suite needs 1–256 rules")
    ids, refs = set(), 0
    for rule in rules:
        require(isinstance(rule, dict) and rule.get("kind") in RULE_FIELDS, "Unknown check kind")
        require(not set(rule) - RULE_FIELDS[rule["kind"]] - COMMON_FIELDS, "Unknown check field")
        ident = rule.get("id")
        require(isinstance(ident, str) and ident and ident not in ids, "Check IDs must be unique")
        ids.add(ident)
        for field, value in rule.items():
            if is_ref(value):
                require(field in REF_FIELDS, f"rule {ident!r}: a ref is accepted in {', '.join(REF_FIELDS)}; "
                                             f"not in {field}", field=field)
                parse_ref(value["ref"], f"rule {ident!r}: {field}")
                refs += 1
        require(rule.get("severity", "error") in ("error", "warning"), "Invalid check severity")
        if "pages" in rule:
            _validate_pages(rule["pages"], f"rule {ident!r}: pages")
        if "tolerance" in rule:
            finite(rule["tolerance"], "tolerance", 0, 1e9)
        if not extends:
            # An override may change one field of a library rule; it is checked once merged (``resolve``).
            _validate_fields(rule)
    require(refs <= MAX_REFS, f"A suite holds at most {MAX_REFS} refs to other documents; this one has {refs}",
            "resource_limit", field="ref")
    sampling = suite.get("sampling", {"mode": "still"})
    require(isinstance(sampling, dict) and set(sampling) <= SAMPLING_FIELDS, "Invalid sampling")
    for axis in ("artboards", "pages", "comps"):
        value = sampling.get(axis)
        require(value is None or value == "all" or _name_list(value),
                f"sampling {axis} is 'all' or a list of names", field=axis)
    require(type(sampling.get("include_hidden", False)) is bool, "sampling include_hidden is true or false")
    require(sampling.get("mode", "still") in ("still", "sampled", "all", "times"), "Invalid sampling mode")
    count = sampling.get("count", 8)
    require(type(count) is int and 2 <= count <= 3600, "Sample count must be 2–3600")
    if sampling.get("mode") == "times":
        require(
            isinstance(sampling.get("times"), list) and 0 < len(sampling["times"]) <= 3600,
            "Explicit sampling needs 1–3600 times",
        )
    require(len(json.dumps(suite, allow_nan=False)) <= 1024 * 1024, "Suite too large", "resource_limit")


# Fields every rule kind may carry besides its own.
COMMON_FIELDS = {"kind", "id", "severity", "pages"}


def _name_list(value):
    return (isinstance(value, list) and 0 < len(value) <= 500
            and all(isinstance(v, (str, int)) and not isinstance(v, bool) for v in value))


def _validate_pages(value, where):
    # Like the coverage axes: 'all', one page, or a list of page names, ids or 1-based numbers.
    single = isinstance(value, (str, int)) and not isinstance(value, bool)
    require(single or _name_list(value), f"{where} is 'all', a page name or number, or a list of them",
            field="pages")


def rule_pages(project, rule):
    """The page ids a rule is limited to (its ``pages`` field), or None when it runs on every page. Unknown pages
    raise, so a typo reads as needs_review rather than silently skipping the rule."""
    from .pages import find_page

    value = rule.get("pages")
    if value is None or value == "all":
        return None
    refs = value if isinstance(value, list) else [value]
    return {find_page(project.state, ref, "pages")["id"] for ref in refs}


def _validate_fields(rule):
    """Shape checks for the measured rule kinds, so a malformed rule fails when the suite is attached
    rather than reading as needs_review on every run."""
    kind, where = rule["kind"], f"rule {rule.get('id')!r}"
    # A ref is checked once it is resolved (``resolve_refs``), against the value it reads.
    original, rule = rule, {key: value for key, value in rule.items() if not is_ref(value)}
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
        require(isinstance(rule.get("to"), str) or is_ref(original.get("to")),
                f"{where}: needs to (a layer or 'canvas')", field="to")
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
        require(isinstance(rule.get("expected"), str) or is_ref(original.get("expected")),
                f"{where}: expected is a color", field="expected")
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
    if kind == "text":
        from .copy_checks import validate_text_rule

        validate_text_rule(rule, where)
    if kind == "budget":
        validate_budget(rule, where)


def validate_budget(rule, where):
    """The limits of a budget rule (or of the workspace ``budget`` the budget design check reads)."""
    require(any(name in rule for name in BUDGET_LIMITS), f"{where}: set {', '.join(BUDGET_LIMITS)}",
            field="max_layers")
    for name in ("max_layers", "max_fonts", "max_bytes"):
        if name in rule:
            require(type(rule[name]) is int and rule[name] >= 0, f"{where}: {name} is a whole number", field=name)
    for name in ("min_ppi", "max_ppi"):
        if name in rule:
            finite(rule[name], f"{where}: {name}", 1, 100000)
    if "min_ppi" in rule and "max_ppi" in rule:
        require(rule["min_ppi"] <= rule["max_ppi"], f"{where}: min_ppi is at most max_ppi", field="max_ppi")
    if "max_render_ms" in rule:
        finite(rule["max_render_ms"], f"{where}: max_render_ms", 1, 600000)
        # Render time depends on the machine, so it is an advisory rule of its own, never mixed with the
        # limits that fail a run.
        others = [name for name in BUDGET_LIMITS if name in rule and name != "max_render_ms"]
        require(not others, f"{where}: max_render_ms is advisory; put {', '.join(others)} in another budget rule",
                field="max_render_ms")
    if "proxy" in rule:
        require("max_render_ms" in rule, f"{where}: proxy sets the render size of max_render_ms", field="proxy")
        require(type(rule["proxy"]) is int and 64 <= rule["proxy"] <= 4096,
                f"{where}: proxy is the longest side in pixels, 64-4096", field="proxy")


# References to other documents (#558) ------------------------------------------------------------------------------

def is_ref(value):
    return isinstance(value, dict) and set(value) == {"ref"}


def parse_ref(text, where="ref"):
    """(document path, kind, target) of a ref string: ``doc.vixl#layer.field`` reads a field of a layer (or of
    ``canvas``) of that document, as resolved for drawing; ``doc.vixl#suite:rule-id`` reads the same field of a
    rule of that document's suite ``suite`` (an attached or inherited suite name)."""
    require(isinstance(text, str) and 0 < len(text) <= 700 and "\0" not in text,
            f"{where}: ref is text such as 'master.vixl#logo.fill' or 'master.vixl#brand:title-size'", field="ref")
    path, sep, fragment = text.partition("#")
    require(sep and path.strip() and fragment, f"{where}: ref {text!r} needs a document and a target after '#'",
            field="ref")
    require(path.lower().endswith(".vixl"), f"{where}: ref {text!r} names a .vixl document", field="ref")
    if ":" in fragment:
        suite, _, rule = fragment.partition(":")
        require(suite and rule, f"{where}: ref {text!r} names a suite and a rule id (#suite:rule-id)", field="ref")
        return path, "rule", (suite, rule)
    layer, dot, name = fragment.rpartition(".")
    require(dot and layer and name, f"{where}: ref {text!r} names a layer and a field (#layer.field)", field="ref")
    return path, "field", (layer, name)


def ref_memo(project):
    """The per-run state ``resolve_ref`` shares between refs: resolved values and the count against MAX_REFS."""
    return {"origin": project, "values": {}, "count": 0, "read": []}


def _ref_key(origin, path):
    """A referenced document as reports name it: workspace-relative when inside the workspace."""
    from pathlib import Path

    from .links import stored_source

    workspace = getattr(origin, "_workspace", None)
    if workspace:
        try:
            return path.relative_to(Path(workspace).resolve()).as_posix()
        except ValueError:
            pass
    return stored_source(origin, path)


def ref_target(project, value):
    """The absolute path of the document a ref (a ``{"ref": ...}`` value or its string) names, resolved like a link
    source (the document's folder, then the workspace; outside files are refused unless the project allows
    linked files). It opens nothing, so the workspace dependency graph can read a suite's references cheaply."""
    from .links import locate

    path, _, _ = parse_ref(value["ref"] if is_ref(value) else value)
    return locate(project, path)


def suite_refs(suite):
    """[(rule id, field, ref string)] for every ref a suite's rules hold (none are resolved)."""
    return [(rule.get("id"), field, value["ref"]) for rule in suite.get("rules", []) for field, value in rule.items()
            if is_ref(value)]


def resolve_ref(project, value, field, chain=(), memo=None):
    """(value, references) for a ref ``{"ref": ...}`` read for ``field`` of a rule. ``references`` lists
    {path, digest} of every document read (nested rule refs included), ``digest`` being ``assurance.digest`` of
    its state. Documents are opened read-only through the link source cache. ``chain`` holds the
    (path, suite, rule) entries already being resolved: a rule ref back into it raises ``link_cycle`` and one
    deeper than ``links.MAX_DEPTH`` raises ``link_depth``, in the shape ``links.check_cycle`` uses (code, message,
    ``source``, ``chain``). A missing document, layer, field, suite or rule raises, so the rule needs review."""
    from .links import MAX_DEPTH, locate, open_source

    memo = memo if memo is not None else ref_memo(project)
    text = value["ref"]
    source, kind, target = parse_ref(text)
    path = locate(project, source)
    key = (str(path), kind, target, field)

    def names(entries):
        return [f"{item[0]}#{item[1]}:{item[2]}" for item in entries]

    if kind == "rule":
        entry = (str(path), *target)
        if entry in chain:
            stack = names((*chain, entry))
            raise VixlError("link_cycle", "Suite references form a cycle: " + " → ".join(stack), source=text,
                            chain=stack)
        if len(chain) >= MAX_DEPTH:
            stack = names((*chain, entry))
            raise VixlError("link_depth", f"Suite references nest more than {MAX_DEPTH} levels deep: "
                            + " → ".join(stack), source=text, chain=stack)
    if key in memo["values"]:
        found, references = memo["values"][key]
        return deepcopy(found), list(references)
    memo["count"] += 1
    require(memo["count"] <= MAX_REFS, f"A suite run reads at most {MAX_REFS} refs to other documents (nested refs "
                                       "count)", "resource_limit", source=text)
    try:
        child, _ = open_source(project, path, source)
    except VixlError:
        missing = {"path": _ref_key(memo["origin"], path), "digest": None}
        if missing not in memo["read"]:
            memo["read"].append(missing)
        raise
    references = [{"path": _ref_key(memo["origin"], path), "digest": digest(child.state)}]
    if references[0] not in memo["read"]:
        memo["read"].append(references[0])
    if kind == "field":
        from .render import resolved_layers

        layer_ref, name = target
        if layer_ref == "canvas":
            record = child.state["canvas"]
        else:
            try:
                ident = child.layer(layer_ref)["id"]
            except (VixlError, KeyError) as exc:
                raise VixlError("not_found", f"ref {text!r}: {source} has no layer {layer_ref!r}", source=text) from exc
            record = next(item for item in resolved_layers(child) if item["id"] == ident)
        require(name in record, f"ref {text!r}: {layer_ref!r} in {source} has no field {name!r}", "not_found",
                source=text)
        found = deepcopy(record[name])
    else:
        suite_name, rule_id = target
        try:
            suite, _ = resolve(child, suite_name)
        except VixlError as exc:
            raise VixlError("not_found", f"ref {text!r}: {source} has no suite {suite_name!r}", source=text) from exc
        rule = next((item for item in suite["rules"] if item["id"] == rule_id), None)
        require(rule is not None, f"ref {text!r}: suite {suite_name!r} in {source} has no rule {rule_id!r}",
                "not_found", source=text)
        require(field in rule, f"ref {text!r}: rule {rule_id!r} in {source} sets no {field}", "not_found",
                source=text)
        found = deepcopy(rule[field])
        if is_ref(found):
            found, nested = resolve_ref(child, found, field, (*chain, (str(path), suite_name, rule_id)), memo)
            references += [item for item in nested if item not in references]
    memo["values"][key] = (deepcopy(found), list(references))
    return found, references


def resolve_refs(project, rule, memo=None, suite_name=None):
    """(rule with every ref replaced by the value it reads, references). Raises like ``resolve_ref``; the
    resolved rule is shape-checked as an attached rule is."""
    from pathlib import Path

    resolved, references = deepcopy(rule), []
    here = str(Path(project.path).resolve()) if getattr(project, "path", None) else None
    chain = ((here, suite_name, rule.get("id")),) if here and suite_name else ()
    for field in REF_FIELDS:
        if is_ref(rule.get(field)):
            resolved[field], found = resolve_ref(project, rule[field], field, chain, memo)
            references += [item for item in found if item not in references]
    _validate_fields(resolved)
    return resolved, references


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


# Rule kinds whose ``target`` is a glob or a container query rather than one layer.
_PATTERN_TARGETS = {"count", "container", "design", "palette", "assert", "budget", "text"}


def rule_layers(rule):
    """The layer names a rule references: ``target``, ``before``, ``after``, ``to`` (unless it is the canvas) and
    ``targets``."""
    names = [rule.get(key) for key in ("before", "after", "to")]
    if rule.get("kind") not in _PATTERN_TARGETS:
        names.append(rule.get("target"))
    targets = rule.get("targets")
    names += targets if isinstance(targets, list) else []
    return [name for name in dict.fromkeys(names) if isinstance(name, str) and name != "canvas"]


def rule_result(project, rule):
    from .render import resolved_layers, resolve_layout

    kind = rule["kind"]
    if kind == "container":
        from .containers import measure
        report = measure(project, rule.get("target"))
        return report["passed"], report
    if kind == "palette":
        from .palette_checks import measure
        report = measure(project, **{k: v for k, v in rule.items() if k not in COMMON_FIELDS})
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
    from .copy_checks import shown_layers

    names = [layer["name"] for layer in shown_layers(project, rule.get("target", "*"), rule.get("layer_type"))]
    return _within(len(names), rule), {"count": len(names), "layers": names[:20],
                                       "minimum": rule.get("minimum"), "maximum": rule.get("maximum")}


def _text(project, rule):
    from .copy_checks import text_rule

    return text_rule(project, rule)


def document_bytes(project):
    """What saving the document writes before compression: its JSON (with undo history) plus embedded files."""
    manifest = project.manifest()
    manifest.pop("asset_hashes")
    return len(json.dumps(manifest, allow_nan=False, separators=(",", ":")).encode()) + sum(map(len, project.assets.values()))


def _budget(project, rule):
    """Production budgets (``measure_budget``); a render-time rule reads as advisory: a warning to review."""
    detail, problems = measure_budget(project, rule)
    if problems:
        detail["problems"] = [item["message"] for item in problems][:20]
    if "max_render_ms" in rule:
        detail.update(advisory=True, action="review")
    return not problems, detail


def measure_budget(project, rule):
    """(measurements, problems) for the budget limits in ``rule``: drawn layers (as the count rule counts them),
    distinct fonts drawn, the saved size, the effective resolution of placed images (as the print check measures
    it: too low for ``min_ppi``, wastefully high for ``max_ppi``) and the proxy render time. Each problem is
    {limit, message, layers (ids)}; ``worst`` lists the top offenders per limit as {layer, value}."""
    from .checks import effective_ppi
    from .copy_checks import shown_layers
    from .render import resolved_layers
    from .richtext import fonts_used
    from .spatial import canvas_boxes

    detail, problems, worst = {}, [], {}
    shown = shown_layers(project)
    ids = {layer["id"] for layer in shown}
    every = {layer["id"]: layer for layer in project.state["layers"]}
    if "max_layers" in rule:
        detail["layers"] = len(shown)
        # Where the layers pile up: drawn layers under each top-level layer.
        piles = {}
        for layer in shown:
            top = layer
            while top.get("parent") in every:
                top = every[top["parent"]]
            piles[top["id"]] = piles.get(top["id"], 0) + 1
        ranked = sorted(piles.items(), key=lambda item: -item[1])[:WORST]
        worst["max_layers"] = [{"layer": every[ident]["name"], "value": count} for ident, count in ranked]
        if len(shown) > rule["max_layers"]:
            problems.append({"limit": "max_layers", "layers": [ident for ident, _ in ranked],
                             "message": f"{len(shown)} layers drawn; at most {rule['max_layers']}"})
    resolved = [item for item in resolved_layers(project) if item["id"] in ids]
    if "max_fonts" in rule:
        from .checks import FALLBACK_FONT

        reverse = {asset: name for name, asset in project.state.get("fonts", {}).items()}
        users = {}
        for item in resolved:
            if item["type"] == "text":
                for font in fonts_used(item, FALLBACK_FONT):
                    users.setdefault(reverse.get(font, font), []).append(item)
        fonts = sorted(users)
        detail["fonts"] = fonts
        # The fonts drawn by the fewest layers are the cheapest to drop.
        ranked = sorted(users.items(), key=lambda item: (len(item[1]), item[0]))[:WORST]
        worst["max_fonts"] = [{"font": font, "layer": items[0]["name"], "value": len(items)} for font, items in ranked]
        if len(fonts) > rule["max_fonts"]:
            problems.append({"limit": "max_fonts", "layers": [items[0]["id"] for _, items in ranked],
                             "message": f"{len(fonts)} fonts drawn; at most {rule['max_fonts']}"})
    if "max_bytes" in rule:
        size = document_bytes(project)
        detail["document_bytes"] = size
        if size > rule["max_bytes"]:
            problems.append({"limit": "max_bytes", "layers": [],
                             "message": f"The document is {size} bytes; at most {rule['max_bytes']} (history compact "
                                        "drops undo history and unused files)"})
    if "min_ppi" in rule or "max_ppi" in rule:
        dpi = project.state["canvas"].get("dpi") or 300
        boxes = canvas_boxes(project)
        placed = []
        for item in resolved:
            ppi = effective_ppi(project, item, boxes[item["id"]], dpi)
            if ppi is not None:
                placed.append((item, ppi, boxes[item["id"]]))
        detail["dpi"] = dpi
        if "min_ppi" in rule:
            low = sorted((entry for entry in placed if entry[1] < rule["min_ppi"]), key=lambda entry: entry[1])
            detail["low_resolution"] = [{"layer": item["name"], "effective_ppi": round(ppi)} for item, ppi, _ in low[:20]]
            worst["min_ppi"] = [{"layer": item["name"], "value": round(ppi)}
                                for item, ppi, _ in sorted(placed, key=lambda entry: entry[1])[:WORST]]
            problems += [{"limit": "min_ppi", "layers": [item["id"]],
                          "message": f"{item['name']!r} prints at about {round(ppi)} ppi; at least {rule['min_ppi']:g}"}
                         for item, ppi, _ in low]
        if "max_ppi" in rule:
            high = []
            for item, ppi, box in placed:
                source = _source_pixels(project, item)
                # The pixels the placement needs at max_ppi; a source with over 4x that area carries pixels no
                # output shows, even when one side alone stays under the limit.
                needed = max(box[2], 1) * max(box[3], 1) * (rule["max_ppi"] / dpi) ** 2
                if ppi > rule["max_ppi"] or source > 4 * needed:
                    high.append({"layer": item["name"], "id": item["id"], "effective_ppi": round(ppi),
                                 "source_pixels": source, "placed_pixels": round(box[2] * box[3])})
            high.sort(key=lambda entry: -entry["effective_ppi"])
            detail["over_resolution"] = [{k: v for k, v in entry.items() if k != "id"} for entry in high[:20]]
            worst["max_ppi"] = [{"layer": item["name"], "value": round(ppi)}
                                for item, ppi, _ in sorted(placed, key=lambda entry: -entry[1])[:WORST]]
            problems += [{"limit": "max_ppi", "layers": [entry["id"]],
                          "message": f"{entry['layer']!r} places about {entry['effective_ppi']} ppi "
                                     f"({entry['source_pixels']} source pixels in {entry['placed_pixels']} placed); at "
                                     f"most {rule['max_ppi']:g} (downsample it with image-resize, or place it larger)"}
                         for entry in high]
    if "max_render_ms" in rule:
        from time import perf_counter

        from .proxy import render_preview

        size = rule.get("proxy", 1024)
        timings = []
        for _ in range(2):  # cold, then warm (caches filled); the warm time is compared
            began = perf_counter()
            render_preview(project, size, size)
            timings.append((perf_counter() - began) * 1000)
        detail.update(render_ms={"cold": round(timings[0], 1), "warm": round(timings[1], 1)}, proxy=size)
        if timings[1] > rule["max_render_ms"]:
            problems.append({"limit": "max_render_ms", "layers": [],
                             "message": f"A {size} px proxy render takes about {timings[1]:.0f} ms warm "
                                        f"({timings[0]:.0f} ms cold); at most {rule['max_render_ms']:g} ms (the cost "
                                        "check names the slow layers)"})
    if worst:
        detail["worst"] = worst
    return detail, problems


def _source_pixels(project, layer):
    """Source pixels a placed raster or frame draws (its crop when cropped)."""
    if layer.get("crop"):
        x0, y0, x1, y1 = layer["crop"]
        return int((x1 - x0) * (y1 - y0))
    width, height = project.image(layer["asset"]).size
    return width * height


# The workspace defaults of the budget design check (``check --checks budget``); the workspace check policy
# (.vixl-checks.json ``budget``) overrides them field by field.
DEFAULT_BUDGET = {"max_layers": 500, "max_fonts": 4, "max_bytes": 100_000_000, "max_ppi": 1200}


def budget_findings(project, limits=None):
    """Findings of the budget design check: the budget rule's limits without a suite. ``limits`` defaults to
    ``DEFAULT_BUDGET`` under the workspace policy's ``budget``. Render time is left to suites (it is advisory)."""
    if limits is None:
        from .policy import for_project

        limits = {**DEFAULT_BUDGET, **for_project(project).get("budget", {})}
    detail, problems = measure_budget(project, limits)
    findings = []
    for item in problems:
        finding = {"message": item["message"], "layers": item["layers"], "limit": item["limit"],
                   "maximum" if item["limit"].startswith("max") else "minimum": limits[item["limit"]]}
        if item["limit"] in detail.get("worst", {}):
            finding["worst"] = detail["worst"][item["limit"]]
        findings.append(finding)
    return findings


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
            "balance": _balance, "hierarchy": _hierarchy, "count": _count, "focal": _focal, "text": _text,
            "budget": _budget}


def validate_library_names(names, where):
    """A list of library suite names (``suites`` on a group or in brand.json)."""
    from .design import named

    require(isinstance(names, list) and len(names) <= 32, f"{where} lists at most 32 library suite names",
            field="suites")
    for name in names:
        named(name)
    require(len(set(names)) == len(names), f"{where} names each suite once", field="suites")
    return names


def library(project, name):
    """A named suite from the suite library (built-in, plugin and workspace suites)."""
    from .resources import get

    return get("suites", name, workspace=getattr(project, "_workspace", None))


def document_key(project):
    """The document's workspace-relative path, or None when it is unsaved or outside the workspace."""
    from pathlib import Path

    workspace = getattr(project, "_workspace", None)
    document = getattr(project, "_document", None) or project
    if not workspace or not document.path:
        return None
    try:
        return Path(document.path).resolve().relative_to(Path(workspace).resolve()).as_posix()
    except ValueError:
        return None


def inherited(project):
    """{library suite name: where it comes from}: suites the document's project groups (``group:NAME``) and the
    workspace brand.json (``workspace``) attach to every member by reference."""
    from pathlib import Path

    workspace = getattr(project, "_workspace", None)
    if not workspace:
        return {}
    found = {}
    key = document_key(project)
    directory = Path(workspace) / ".vixl-groups"
    if key and directory.is_dir():
        from .production import read_json

        for path in sorted(directory.glob("*.json")):
            if path.name.endswith(".transaction.json"):
                continue
            try:
                group = read_json(path)
            except VixlError:
                continue
            if key in group.get("documents", []):
                for name in group.get("suites", []):
                    found.setdefault(name, f"group:{group['name']}")
    from .brand import load

    for name in load(workspace).get("suites", []):
        found.setdefault(name, "workspace")
    return found


def effective(project):
    """{name: source} of every suite the document is held to: its attached suites ('document') and the inherited
    library suites that no attached suite already extends."""
    attached = project.state.get("suites", {})
    extended = {suite.get("extends") for suite in attached.values()} - {None}
    found = {name: "document" for name in attached}
    for name, source in inherited(project).items():
        if name not in attached and name not in extended:
            found[name] = source
    return found


def resolve(project, suite):
    """(suite to run, provenance) for a suite name or object. A name is an attached suite, else an inherited
    library suite. A suite that ``extends`` a library suite runs the library's current rules with its own rules
    applied on top: one with a library rule's ``id`` overrides that rule's fields, any other is added."""
    info = {}
    if isinstance(suite, str):
        name = suite
        attached = project.state.get("suites", {})
        if name in attached:
            suite = attached[name]
            info["source"] = "document"
        else:
            sources = inherited(project)
            require(name in sources, f"Unknown suite: {name}", field="suite",
                    suggestions=sorted({*attached, *sources}))
            suite, info["source"] = {"extends": name, "rules": []}, sources[name]
    validate_suite(suite)
    base = suite.get("extends")
    if not base:
        return suite, info
    original = library(project, base)
    require(not original.get("extends"), f"Library suite {base!r} cannot itself extend another suite")
    rules = {rule["id"]: deepcopy(rule) for rule in original["rules"]}
    overrides, added = [], []
    for rule in suite["rules"]:
        if rule["id"] in rules:
            require(rules[rule["id"]]["kind"] == rule["kind"],
                    f"Override {rule['id']!r} must keep the library rule's kind ({rules[rule['id']]['kind']})",
                    field="kind")
            changed = sorted(k for k, v in rule.items() if k not in ("id", "kind") and rules[rule["id"]].get(k) != v)
            rules[rule["id"]].update(deepcopy(rule))
            if changed:
                overrides.append({"id": rule["id"], "fields": changed})
        else:
            rules[rule["id"]] = deepcopy(rule)
            added.append(rule["id"])
    merged = {"version": 1, "rules": list(rules.values())}
    for key in ("description", "sampling"):
        value = suite.get(key, original.get(key))
        if value is not None:
            merged[key] = deepcopy(value)
    validate_suite(merged)
    info.update(library=base, library_hash=digest(original))
    if overrides:
        info["overrides"] = overrides
    if added:
        info["added"] = added
    return merged, info


PASSES = ".vixl-suite-passes.json"


def contract_memory(project, name, info, passed):
    """Remember the library version each document last passed and report a library change since then
    ("contract changed since last pass"). Stored in the workspace, never in the document."""
    from pathlib import Path

    from .fileio import file_lock
    from .production import read_json, write_json

    key, workspace = document_key(project), getattr(project, "_workspace", None)
    if not key or not name or "library_hash" not in info:
        return None
    path = Path(workspace) / PASSES
    try:
        with file_lock(str(path)):
            memory = read_json(path) if path.exists() else {}
            last = memory.get(key, {}).get(name)
            if passed and last != info["library_hash"]:
                memory.setdefault(key, {})[name] = info["library_hash"]
                write_json(path, memory)
    except (OSError, VixlError):
        return None
    if last and last != info["library_hash"]:
        return {"message": f"Contract changed since last pass: library suite {info['library']!r} is a new version",
                "last_passed_hash": last, "library_hash": info["library_hash"]}
    return None


def _times(project, sampling, mode):
    from .timeline import frame_times, parse_time

    timeline = project.state.get("timeline", {"duration": 1000, "fps": 30})
    if mode == "still":
        return [None]
    if mode == "all":
        return frame_times(project)[0]
    if mode == "times":
        return [parse_time(t, timeline["duration"], timeline.get("markers")) for t in sampling["times"]]
    count = sampling.get("count", 8)
    return sorted(set([i * timeline["duration"] / (count - 1) for i in range(count)]
                      + [k["time"] for t in timeline.get("tracks", []) for k in t["keys"]]))


def run_suite(project, suite, *, variables=None, artboard=None, mode=None, page=None, comp=None, artboards=None,
              pages=None, comps=None, include_hidden=None):
    """Run a suite (an attached or inherited name, or an object). ``artboards``/``pages``/``comps`` ('all' or
    lists, also settable in the suite's ``sampling``) run it over every combination; each result then names its
    ``variant`` and ``groups`` gives each variant's status."""
    from .coverage import coverage_record, label, public, requested, variants
    from .design_render import artboard_project
    from .pages import active_page, on_other_page
    from .render import view_page
    from .timeline import project_at

    name = suite if isinstance(suite, str) else None
    suite, info = resolve(project, suite)
    suite_hash = digest(suite)
    suite, unresolved, referenced = _resolved_refs(project, suite, name)
    sampling = suite.get("sampling", {})
    mode = mode or sampling.get("mode", "still")
    require(mode in ("still", "sampled", "all", "times"), "Unknown coverage mode")
    axes = {"artboards": artboards if artboards is not None else sampling.get("artboards"),
            "pages": pages if pages is not None else sampling.get("pages"),
            "comps": comps if comps is not None else sampling.get("comps")}
    multi = requested(**axes)
    hidden = include_hidden if include_hidden is not None else sampling.get("include_hidden", False)
    combos = variants(project, **axes, include_hidden=hidden, artboard=artboard, page=page, comp=comp)
    views = []
    for combo in combos:
        view = view_page(project, combo["page"]) if combo["page"] is not None else project
        candidate = artboard_project(view.clone(), combo["artboard"], combo["comp"], variables)
        # A rule about a layer on another page does not apply to this one (it is not a finding to review).
        elsewhere = {rule["id"]: [ref for ref in rule_layers(rule) if on_other_page(project, view, ref)]
                     for rule in suite["rules"]}
        views.append((combo, candidate, _times(candidate, sampling, mode), elsewhere))
    # Rules limited to some pages (rule-level pages): each holds its page ids, or the error naming an unknown page.
    scoped = {}
    for rule in suite["rules"]:
        if rule.get("pages") is not None:
            try:
                scoped[rule["id"]] = rule_pages(project, rule)
            except VixlError as exc:
                scoped[rule["id"]] = exc
    total = sum(len(times) for _, _, times, _ in views) * len(suite["rules"])
    require(total <= 50000, "Check workload exceeds limit", "resource_limit")
    from .checks import missing_glyphs

    results, groups = [], []
    for combo, candidate, times, elsewhere in views:
        where = {"variant": public(project, combo)} if multi else {}
        start = len(results)
        page_id = combo["page"] if combo["page"] is not None else (active_page(project.state) or {}).get("id")
        for time in times:
            frame = candidate if time is None else project_at(candidate, time)
            for rule in suite["rules"]:
                if rule["id"] in unresolved:
                    exc = unresolved[rule["id"]]
                    results.append({"id": rule["id"], "status": "needs_review", "severity": _severity(rule),
                                    "time": time, **where, "message": str(exc), "code": exc.code,
                                    **({"chain": exc.details["chain"]} if "chain" in exc.details else {}),
                                    "references": referenced.get(rule["id"], [])})
                    continue
                limit = scoped.get(rule["id"])
                if isinstance(limit, VixlError):
                    results.append({"id": rule["id"], "status": "needs_review",
                                    "severity": _severity(rule), "time": time, **where,
                                    "message": str(limit)})
                    continue
                if limit is not None and page_id not in limit:
                    named = rule["pages"] if isinstance(rule["pages"], list) else [rule["pages"]]
                    results.append({"id": rule["id"], "status": "not_applicable",
                                    "severity": _severity(rule), "time": time, **where,
                                    "reason": "rule limited to pages " + ", ".join(map(str, named)),
                                    "pages": named})
                    continue
                if elsewhere.get(rule["id"]):
                    results.append({"id": rule["id"], "status": "not_applicable",
                                    "severity": _severity(rule), "time": time, **where,
                                    "reason": "layer on another page", "layers": elsewhere[rule["id"]]})
                    continue
                try:
                    passed, detail = rule_result(frame, rule)
                    status = "passed" if passed else "needs_review" if passed is None else "failed"
                except (VixlError, KeyError, TypeError, ValueError, StopIteration) as exc:
                    status, detail = "needs_review", {"message": str(exc)}
                if rule["id"] in referenced:
                    detail["references"] = referenced[rule["id"]]
                results.append({"id": rule["id"], "status": status, "severity": _severity(rule),
                                "time": time, **where, **detail})
            # Every suite also fails on characters no font can draw (they render as empty boxes).
            missing = missing_glyphs(frame)
            if missing:
                results.append({"id": "missing-glyphs", "status": "failed", "severity": "error", "time": time,
                                **where, "automatic": True,
                                "message": "Text has characters no font can draw; import a covering font and add it "
                                           "with font-fallbacks", "layers": missing})
        if multi:
            errors, review = _tally(results[start:])
            groups.append({**where["variant"], "label": label(project, combo),
                           "status": "failed" if errors else "needs_review" if review else "passed",
                           "errors": errors, "needs_review": review})
    errors, review = _tally(results)
    times = views[0][2] if len(views) == 1 else list(dict.fromkeys(t for _, _, ts, _ in views for t in ts))
    from .outcomes import from_suite
    from .waivers import apply_suite

    report = {
        "version": 1,
        "suite_hash": suite_hash,
        "passed": errors == 0 and review == 0,
        "status": "failed" if errors else "needs_review" if review else "passed",
        "errors": errors,
        "needs_review": review,
        "coverage": {"mode": mode, "times": times, **(coverage_record(project, combos) if multi else {})},
        "results": results,
    }
    if info:
        report.update(info)
    if referenced:
        report["references"] = list({item["path"]: item for found in referenced.values() for item in found}.values())
    # A rule waiver (the waiver operation with rule) turns that rule's failures into "waived" results; the
    # outcome is computed after, so a waived rule neither fails validation nor asks for review.
    report = apply_suite(project, report, name)
    if multi:
        for group in groups:
            # Waivers can change a result's status, so each variant's tally is taken again.
            mine = [r for r in report["results"]
                    if r.get("variant") and all(group.get(k) == v for k, v in r["variant"].items())]
            errors, review = _tally(mine)
            group.update(status="failed" if errors else "needs_review" if review else "passed", errors=errors,
                         needs_review=review)
        report["groups"] = groups
    report["outcome"] = from_suite(report)
    if info:
        changed = contract_memory(project, name, info, report["passed"])
        if changed:
            report["contract_changed"] = changed
    return report


def _severity(rule):
    # Render time depends on the machine: a budget rule on it is a warning to review whatever it says.
    if rule["kind"] == "budget" and "max_render_ms" in rule:
        return "warning"
    return rule.get("severity", "error")


def _resolved_refs(project, suite, name):
    """(suite with its refs resolved, {rule id: error} for refs that could not be, {rule id: references}). One
    memo serves the whole run, so a document referenced twice is read once and counts once."""
    if not any(is_ref(rule.get(field)) for rule in suite["rules"] for field in REF_FIELDS):
        return suite, {}, {}
    memo, rules, unresolved, referenced = ref_memo(project), [], {}, {}
    for rule in suite["rules"]:
        if not any(is_ref(rule.get(field)) for field in REF_FIELDS):
            rules.append(rule)
            continue
        read = len(memo["read"])
        try:
            resolved, referenced[rule["id"]] = resolve_refs(project, rule, memo, name)
            rules.append(resolved)
        except VixlError as exc:
            # The documents it did read are still named, so a later change to them shows as the cause.
            unresolved[rule["id"]], referenced[rule["id"]] = exc, memo["read"][read:]
            rules.append(rule)
    return {**suite, "rules": rules}, unresolved, referenced


def _tally(results):
    errors = sum(r["status"] == "failed" and r["severity"] == "error" for r in results)
    review = sum(r["status"] == "needs_review" or (r["status"] == "failed" and r["severity"] == "warning")
                 for r in results)
    return errors, review
