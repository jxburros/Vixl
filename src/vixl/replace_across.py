"""Find and replace across documents: text, colors, fonts and images (``replace-across``).

A dry run (the default) lists every match per document (layer, field, before and after) and can
write a before/after review page whose downloaded decisions feed back as ``decisions``. Applying
publishes the changed documents through the project-group journal (``project_groups.commit``), so
an interrupted run is rolled back with ``group-recover`` under the group's name (or ``journal`` for
a glob). With ``suites`` a document is published only when its suites pass; the others are
reported as needs_review and left untouched.
"""

from contextlib import ExitStack
import hashlib
import re

from .errors import VixlError, require

KINDS = ("text", "color", "font", "asset")
MATCHES = ("substring", "word", "regex")
FITS = ("keep-box", "stretch")
COLOR_FIELDS = ("color", "fill", "stroke", "stroke_color", "start", "end")
MAX_RULES = 50
MAX_PATTERN = 500


def _rules(rules):
    require(isinstance(rules, list) and 0 < len(rules) <= MAX_RULES,
            f"replace is a list of 1-{MAX_RULES} rules like {{text, with}}, {{color, with}}, {{font, with}} or "
            "{asset, with}", field="replace")
    parsed = []
    for index, rule in enumerate(rules):
        where = f"replace[{index}]"
        require(isinstance(rule, dict), f"{where} must be an object", field=where)
        kinds = [kind for kind in KINDS if kind in rule]
        require(len(kinds) == 1, f"{where} needs exactly one of {', '.join(KINDS)}", field=where)
        kind = kinds[0]
        allowed = {kind, "with"} | {"text": {"match", "ignore_case", "variables"}, "color": {"tolerance", "swatches"},
                                    "font": set(), "asset": {"fit"}}[kind]
        unknown = sorted(set(rule) - allowed)
        require(not unknown, f"{where}: unknown field(s) {unknown}; allowed {sorted(allowed)}", field=where)
        require(isinstance(rule[kind], str) and rule[kind], f"{where}.{kind} must be a non-empty string", field=where)
        require(isinstance(rule.get("with"), str), f"{where}.with must be a string", field=f"{where}.with")
        entry = {"index": index, "kind": kind, "find": rule[kind], "with": rule["with"]}
        if kind == "text":
            match = rule.get("match", "substring")
            require(match in MATCHES, f"{where}.match is one of {', '.join(MATCHES)}", field=f"{where}.match")
            flags = re.IGNORECASE if rule.get("ignore_case") else 0
            if match == "regex":
                require(len(rule["text"]) <= MAX_PATTERN, f"{where}.text is at most {MAX_PATTERN} characters",
                        field=where)
                try:
                    pattern = re.compile(rule["text"], flags)
                except re.error as exc:
                    raise VixlError("invalid_request", f"{where}.text is not a valid regex: {exc}", field=where) from exc
                replacement = rule["with"]
            else:
                body = re.escape(rule["text"])
                pattern = re.compile(rf"(?<!\w){body}(?!\w)" if match == "word" else body, flags)
                replacement = rule["with"].replace("\\", "\\\\")
            entry.update(pattern=pattern, replacement=replacement, variables=rule.get("variables", True))
        elif kind == "color":
            tolerance = rule.get("tolerance", 0)
            require(isinstance(tolerance, (int, float)) and not isinstance(tolerance, bool) and 0 <= tolerance <= 255,
                    f"{where}.tolerance is 0-255 per channel", field=f"{where}.tolerance")
            from .group_consistency import _rgba

            target = _rgba(rule["color"], {"variables": {}, "swatches": {}})
            require(target is not None, f"{where}.color is not a color", field=f"{where}.color")
            entry.update(rgba=target, tolerance=tolerance, swatches=rule.get("swatches", True))
        elif kind == "asset":
            fit = rule.get("fit", "keep-box")
            require(fit in FITS, f"{where}.fit is one of {', '.join(FITS)}", field=f"{where}.fit")
            entry["fit"] = fit
        parsed.append(entry)
    return parsed


def _walk(layers):
    for layer in layers:
        yield layer
        yield from _walk(layer.get("children", []))


def _text_changes(project, rule):
    changes, operations = [], []
    for layer in _walk(project.state["layers"]):
        if layer.get("type") != "text" or not isinstance(layer.get("text"), str):
            continue
        new, count = rule["pattern"].subn(rule["replacement"], layer["text"])
        if count and new != layer["text"]:
            changes.append({"layer": layer["name"], "field": "text", "before": layer["text"], "after": new,
                            "count": count})
            operations.append({"type": "text-set", "target": layer["id"], "text": new})
    if rule["variables"]:
        for name, value in project.state.get("variables", {}).items():
            if isinstance(value, str):
                new, count = rule["pattern"].subn(rule["replacement"], value)
                if count and new != value:
                    changes.append({"variable": name, "field": "value", "before": value, "after": new, "count": count})
                    operations.append({"type": "variable", "name": name, "value": new})
    return changes, operations


def _font_changes(project, rule):
    from .group_consistency import font_name

    changes, operations = [], []
    registered = project.state.get("fonts", {})
    wanted = {rule["find"].casefold(), str(registered.get(rule["find"], "")).casefold()} - {""}
    for layer in _walk(project.state["layers"]):
        stored = str(layer.get("font", ""))
        if layer.get("type") == "text" and (stored.casefold() in wanted
                                            or font_name(project, stored).casefold() == rule["find"].casefold()):
            changes.append({"layer": layer["name"], "field": "font", "before": font_name(project, stored),
                            "after": rule["with"]})
            operations.append({"type": "text-set", "target": layer["id"], "font": rule["with"]})
    return changes, operations


def _literal(value):
    return isinstance(value, str) and not value.startswith("@") and "${" not in value and "(@" not in value


def _color_changes(project, rule):
    """Direct edits ``(owner, key, new)`` of literal color fields within tolerance."""
    from .group_consistency import _close, _rgba

    state = project.state
    edits, changes = [], []
    if _rgba(rule["with"], state) is None:
        raise VixlError("invalid_color", f"replace[{rule['index']}].with {rule['with']!r} is not a color in this "
                        "document (a missing @swatch?)", field=f"replace[{rule['index']}].with")

    def consider(owner, key, label, field):
        value = owner.get(key)
        if _literal(value) and _close(_rgba(value, state), rule["rgba"], rule["tolerance"]):
            edits.append((owner, key, rule["with"]))
            changes.append({**label, "field": field, "before": value, "after": rule["with"]})

    for layer in _walk(state["layers"]):
        for key in COLOR_FIELDS:
            consider(layer, key, {"layer": layer["name"]}, key)
        for index, stop in enumerate(layer.get("stops") or []):
            if isinstance(stop, dict):
                consider(stop, "color", {"layer": layer["name"]}, f"stops[{index}].color")
    if rule["swatches"]:
        for name in list(state.get("swatches", {})):
            if rule["with"].lstrip("@") != name:
                consider(state["swatches"], name, {"swatch": name}, "color")
    return changes, edits


def _asset_matches(session, project, rule):
    """Image layers whose current image came from the file ``rule['find']`` names (by checksum or file name)."""
    from pathlib import PurePosixPath

    digests = set()
    try:
        candidate = session.resolve(rule["find"])
        if candidate.is_file():
            digests.add(hashlib.sha256(candidate.read_bytes()).hexdigest())
    except VixlError:
        pass
    name = PurePosixPath(rule["find"].replace("\\", "/")).name
    found = []
    for layer in _walk(project.state["layers"]):
        if layer.get("type") not in ("raster", "frame") or not isinstance(layer.get("asset"), str):
            continue
        provenance = layer.get("provenance") or {}
        current = provenance.get("checksum") and provenance["checksum"] in layer["asset"]
        if any(digest in layer["asset"] for digest in digests) or (current and provenance.get("checksum") in digests) \
                or (current and provenance.get("original_filename") == name):
            found.append(layer)
    return found


def _asset_changes(session, project, rule, image_cache):
    from .assets import add_image
    from .image_diff import load_visual

    layers = _asset_matches(session, project, rule)
    if not layers:
        return [], []
    if rule["with"] not in image_cache:
        source = session.resolve(rule["with"])
        require(source.is_file(), f"replace[{rule['index']}].with: no file at {rule['with']}", "not_found",
                field=f"replace[{rule['index']}].with")
        image_cache[rule["with"]] = load_visual(source, session.limits)
    image = image_cache[rule["with"]]
    asset = add_image(project, image)
    changes, operations = [], []
    for layer in layers:
        operation = {"type": "replace-contents", "target": layer["id"], "asset": asset}
        operations.append(operation)
        change = {"layer": layer["name"], "field": "asset", "before": rule["find"], "after": rule["with"]}
        if layer["type"] == "frame":
            operation["fit"] = "fit" if rule["fit"] == "keep-box" else "fill"
        elif rule["fit"] == "keep-box":
            box = [layer["x"], layer["y"], layer["width"], layer["height"]]
            scale = min(box[2] / image.width, box[3] / image.height)
            width, height = max(1, round(image.width * scale)), max(1, round(image.height * scale))
            x, y = box[0] + (box[2] - width) / 2, box[1] + (box[3] - height) / 2
            operations += [{"type": "resize", "target": layer["id"], "width": width, "height": height},
                           {"type": "move", "target": layer["id"], "x": x, "y": y}]
            change["box"] = [round(x, 2), round(y, 2), width, height]
        changes.append(change)
    return changes, operations


def edit(session, project, rules, image_cache):
    """Apply ``rules`` to ``project`` (a candidate). Returns the list of matches."""
    from .interfaces import service_check
    from .validation import check_state

    matches, operations, edits = [], [], []
    for rule in rules:
        if rule["kind"] == "text":
            found, ops = _text_changes(project, rule)
        elif rule["kind"] == "font":
            found, ops = _font_changes(project, rule)
        elif rule["kind"] == "asset":
            found, ops = _asset_changes(session, project, rule, image_cache)
        else:
            found, more = _color_changes(project, rule)
            ops = []
            edits += more
        matches += [{"rule": rule["index"], "kind": rule["kind"], **item} for item in found]
        operations += ops
    if edits:
        for owner, key, value in edits:
            owner[key] = value
        check_state(project, project.state)
        project._record([], "Replace colors across documents")
    if operations:
        from .service_fonts import checker

        project.apply(operations, check=checker(project, service_check), detail="compact")
    return matches


def run(session, request):
    """The ``replace-across`` workflow action."""
    from .design import named
    from .fileio import file_lock
    from .project import Project
    from .project_groups import commit, selection, write_review
    from .workspace_checks import members

    rules = _rules(request.get("replace"))
    dry_run = request.get("dry_run", True)
    for field in ("dry_run", "overwrite"):
        require(type(request.get(field, False)) is bool, f"{field} must be boolean", field=field)
    paths, group = members(session, request)
    journal = named(group["name"] if group else request.get("journal", "replace-across"))
    suites = request.get("suites", False)
    require(type(suites) is bool or (isinstance(suites, list) and all(isinstance(s, str) for s in suites)),
            "suites is true (the attached suites) or a list of suite names", field="suites")
    lock = session.resolve(f".vixl-groups/{journal}.json")
    lock.parent.mkdir(parents=True, exist_ok=True)
    require(not session.resolve(f".vixl-groups/{journal}.transaction.json").exists(),
            f"Recover the interrupted edit first (group-recover {journal})")
    with session._mutex, file_lock(str(lock)), ExitStack() as stack:
        for path in paths:
            stack.enter_context(file_lock(str(path)))
        report, originals, candidates, image_cache = [], {}, {}, {}
        for path in paths:
            member = session.relative(path)
            entry = {"document": member}
            try:
                original = Project.load(path, limits=session.limits)
                candidate = Project.load(path, limits=session.limits)
                original._workspace = candidate._workspace = session.workspace
                require(candidate.transaction is None, "Commit the document's transaction first")
                matches = edit(session, candidate, rules, image_cache)
            except VixlError as exc:
                entry.update(status="failed", error=exc.as_dict())
                report.append(entry)
                continue
            entry.update(matches=matches, count=len(matches))
            if not matches:
                entry["status"] = "unchanged"
                report.append(entry)
                continue
            names = list(candidate.state.get("suites", {})) if suites is True else suites or []
            checks = {name: candidate.check_suite(name) for name in names}
            entry["checks"] = checks
            entry["status"] = "changed" if all(check["passed"] for check in checks.values()) else "needs_review"
            originals[path], candidates[path] = original, candidate
            report.append(entry)
        changed = [entry["document"] for entry in report if entry["status"] in ("changed", "needs_review")]
        chosen = selection(session, request, [session.relative(p) for p in paths]) if paths else set()
        output = {"dry_run": dry_run, "journal": journal, "documents": report,
                  "matches": sum(entry.get("count", 0) for entry in report), "changed": len(changed),
                  **({"group": group["name"]} if group else {})}
        if request.get("review"):
            require(dry_run, "review is written by a dry run; apply with accept/reject or decisions", field="review")
            if candidates:
                review_report = [{"document": e["document"], "checks": e.get("checks", {})}
                                 for e in report if e["document"] in changed]
                output.update(write_review(session, request["review"], originals, candidates, review_report,
                                           title="Find and replace review", overwrite=request.get("overwrite", False)))
                for entry in report:
                    for source in review_report:
                        if source["document"] == entry["document"] and "changed_fraction" in source:
                            entry["changed_fraction"] = source["changed_fraction"]
                            entry["changed_region"] = source["changed_region"]
        if not dry_run:
            publish = {path: candidate for path, candidate in candidates.items()
                       if session.relative(path) in chosen and
                       next(e for e in report if e["document"] == session.relative(path))["status"] == "changed"}
            commit(session, journal, publish)
            output["published"] = sorted(session.relative(path) for path in publish)
            for entry in report:
                entry["published"] = entry["document"] in output["published"]
        return output
