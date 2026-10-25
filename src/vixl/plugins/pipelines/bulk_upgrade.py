"""Bulk structure upgrades (#578): convert, rename and re-role many documents, optionally re-apply their layout, with
checks and a render diff before and after, as a dry run by default and a journalled commit.

For each document of ``documents`` (globs) or ``group``:

1. ``convert`` (default true): the conversion kit (``vixl.convert``) upgrades a document saved by an earlier release;
   its changes and warnings are reported.
2. ``map``: ``{"Title*": {"rename": "headline", "role": "headline"}}`` renames every layer whose name matches the
   pattern (``fnmatch``, case-sensitive) and adds it to the role, as ``rename`` and ``role-set`` operations.
3. ``template``: re-applies that layout (``layout-apply`` with ``replace``), filling its slots (title, subtitle, body,
   label, cta, caption, items) from the text of the layers of the role with the slot's name (``headline`` fills
   title), else of a text layer with that name, so the copy survives.

The upgraded copy is checked next to the original (design checks and suites) and the renders are diffed. A copy
that fails a check the original passed (at ``fail_on``) is held. ``dry_run`` (the default) writes nothing; otherwise
the upgraded documents are published together through a journal, which ``group-recover`` with ``journal`` rolls back
after an interruption.
"""

from fnmatch import fnmatchcase

from ...design import named
from ...errors import VixlError, require

REQUEST = {"documents", "group", "convert", "look", "map", "template", "dry_run", "journal", "fail_on", "suites"}
SLOTS = ("title", "subtitle", "body", "label", "cta", "caption", "items")
ALIASES = {"headline": "title", "heading": "title", "kicker": "label", "eyebrow": "label", "button": "cta",
           "subheading": "subtitle", "footer": "caption"}
MAX_DOCUMENTS = 500


def _validate(request):
    from ...automation import bounded_object

    bounded_object(request, REQUEST, "Unknown bulk-upgrade field")
    require(request.get("documents") is not None or request.get("group") is not None,
            "Give documents (globs) or a group", field="documents")
    for flag in ("convert", "dry_run", "suites"):
        if flag in request:
            require(type(request[flag]) is bool, f"{flag} must be boolean", field=flag)
    require(request.get("look", "preserve") in ("preserve", "current"), "look is preserve or current", field="look")
    mapping = request.get("map", {})
    require(isinstance(mapping, dict) and len(mapping) <= 100, "map is {layer name pattern: {rename, role}}",
            field="map")
    for pattern, change in mapping.items():
        require(isinstance(pattern, str) and pattern and isinstance(change, dict) and change
                and set(change) <= {"rename", "role"}, f"map[{pattern!r}] is {{rename?, role?}}", field="map")
        if "rename" in change:
            require(isinstance(change["rename"], str) and change["rename"].strip(), f"map[{pattern!r}].rename is a "
                    "layer name", field="map")
        if "role" in change:
            named(change["role"])
    if request.get("template") is not None:
        require(isinstance(request["template"], str) and request["template"], "template is a layout name",
                field="template")


def mapping_operations(project, mapping):
    """``(operations, renamed, roles)``: ``rename`` and ``role-set`` operations for the layers ``mapping`` matches."""
    operations, renamed, roles = [], [], {}
    for layer in project.state["layers"]:
        for pattern, change in mapping.items():
            if not fnmatchcase(layer["name"], pattern):
                continue
            if change.get("rename") and change["rename"] != layer["name"]:
                operations.append({"type": "rename", "target": layer["id"], "name": change["rename"]})
                renamed.append({"from": layer["name"], "to": change["rename"]})
            if change.get("role"):
                roles.setdefault(change["role"], []).append(layer["id"])
            break
    existing = project.state.get("roles") or {}
    for role, ids in roles.items():
        targets = list(dict.fromkeys([*existing.get(role, []), *ids]))
        operations.append({"type": "role-set", "name": role, "targets": targets})
    return operations, renamed, {role: len(ids) for role, ids in roles.items()}


def template_operation(project, template):
    """The ``layout-apply`` that re-applies ``template`` with the copy of the document's roles in its slots."""
    layers = {layer["id"]: layer for layer in project.state["layers"]}
    slots = {}
    for role, ids in (project.state.get("roles") or {}).items():
        slot = ALIASES.get(role, role)
        if slot not in SLOTS or slot in slots:
            continue
        texts = [layers[i].get("text") for i in ids if i in layers and isinstance(layers[i].get("text"), str)]
        if texts:
            slots[slot] = texts[0]
    for layer in project.state["layers"]:  # Then text layers named after a slot, as layout-apply names them.
        slot = ALIASES.get(layer["name"], layer["name"])
        if slot in SLOTS and slot not in slots and isinstance(layer.get("text"), str):
            slots[slot] = layer["text"]
    record = project.state.get("layout") or {}
    op = {"type": "layout-apply", "name": template, "replace": True, **slots}
    if record.get("name") == template and record.get("seed") is not None:
        op["seed"] = record["seed"]
    return op, sorted(slots)


def run(session, request):
    """The ``bulk-upgrade`` workflow action."""
    from ...convert import convert_project
    from ..workspace_qa.workspace_checks import check_document, members
    from .candidate import commit, evaluate, load

    _validate(request)
    dry_run = request.get("dry_run", True)
    journal = named(request.get("journal", "bulk-upgrade"))
    paths, _ = members(session, {key: request[key] for key in ("documents", "group") if key in request})
    require(len(paths) <= MAX_DOCUMENTS, f"At most {MAX_DOCUMENTS} documents per upgrade", "resource_limit",
            field="documents")
    check = {"suites": request.get("suites", True)}
    fail_on = request.get("fail_on", "error")
    entries, candidates = [], {}
    for path in paths:
        relative = session.relative(path)
        entry = {"document": relative}
        before = check_document(session, relative, check)
        try:
            if request.get("convert", True):
                candidate = convert_project(path, look=request.get("look", "preserve"))
                report = candidate.conversion
                entry["conversion"] = {"saved_by": report.get("saved_by"),
                                       "changes": sorted({c["change"] for c in report["changes"]}),
                                       "warnings": len(report["warnings"])}
                changed = bool(report["changes"])
            else:
                candidate, changed = load(session, relative), False
            candidate._workspace = session.workspace
            operations, renamed, roles = mapping_operations(candidate, request.get("map", {}))
            if operations:
                candidate.apply(operations, detail="compact")
            if request.get("template"):
                op, filled = template_operation(candidate, request["template"])
                candidate.apply(op, detail="compact")
                entry["template"] = {"name": request["template"], "slots": filled}
            entry.update(renamed=renamed, roles=roles)
        except (VixlError, OSError, ValueError, KeyError) as exc:
            entries.append({**entry, "status": "failed", "error": str(exc)[:500]})
            continue
        if not (changed or operations or request.get("template")):
            entries.append({**entry, "status": "unchanged", "before": {"status": before.get("status")}})
            continue
        evaluated = evaluate(session, relative, candidate, request=check, before=before, fail_on=fail_on)
        entry.update(before=evaluated["before"], after=evaluated["after"], diff=evaluated.get("diff"),
                     newly_failing=evaluated["newly_failing"])
        if evaluated["newly_failing"]:
            entry.update(status="held", reason="the upgraded document fails a check the original passed"
                         if before.get("status") != "error" else "the upgraded document fails its checks, and the "
                         "original could not be checked to compare")
        else:
            entry["status"] = "upgraded"
            candidates[relative] = candidate
        entries.append(entry)
    counts = {status: sum(1 for e in entries if e["status"] == status) for status in sorted({e["status"] for e in entries})}
    result = {"dry_run": dry_run, "journal": journal, "count": len(entries), "counts": counts, "documents": entries}
    if dry_run:
        result["written"] = False
        result["next"] = "Run again with dry_run: false to publish the upgraded documents"
        return result
    result["published"] = commit(session, journal, candidates) if candidates else []
    result["written"] = bool(candidates)
    result["recover"] = {"workflow": "group-recover", "request": {"name": journal}}
    return result
