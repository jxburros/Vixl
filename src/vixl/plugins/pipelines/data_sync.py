"""Sync from a data source (#572): bind a CSV to a project group, a campaign spec or a merge sheet, and on every sync
change, check and re-export only what the changed rows affect.

``bind`` is ``{data: CSV, key: COLUMN, to: {group: NAME} | {spec: campaign.json} | {merge: sheets.vixl}}``. Each sync
compares the CSV with the snapshot of the last sync (``.vixl-runs/data/<name>.json``) by ``key``: rows ``added``,
``changed`` (with the changed columns) and ``removed``.

- **Group.** A member is bound to the row whose key equals its own variable of the key's name (``sku: A1``). A member
  is affected when its row was added or changed in a column it uses (a ``${column}`` reference or a variable of that
  name). Its new values are applied as ``variable`` operations on a candidate copy, which is checked next to the
  original (design checks and suites) and render-diffed; candidates that pass are committed together through a
  journal (``group-recover`` with the binding's journal name rolls an interrupted commit back), and then ``exports``
  (``{path: "out/{doc}.png", ...}``) are written again for them only. A candidate that fails is held and keeps its old
  row in the snapshot, so the next sync tries it again. Unchanged members and their exports are not touched.
- **Campaign spec.** ``campaign.json`` is ``{source, output, spec}``; the CSV rows become the spec's ``rows`` (existing
  keys keep their place, new keys are appended, so variant ids stay stable) and the campaign runs again in its output
  folder, where the production fingerprints reuse every variant whose row did not change.
- **Merge sheet.** The sheet document's recorded merge (``merge-impose`` ``rerun``) runs again with the new data when
  any row changed; otherwise it is reused.

``dry_run`` reports the row diff and the planned outputs and writes nothing (not even the snapshot).
"""

import csv
from datetime import datetime, timezone
import io
from pathlib import Path
import re

from ...design import named
from ...errors import VixlError, require

SNAPSHOTS = ".vixl-runs/data"
MAX_ROWS = 10000
MAX_BYTES = 16 * 1024 * 1024
REQUEST = {"bind", "name", "dry_run", "exports", "fail_on", "suites", "overwrite"}
REFERENCE = re.compile(r"\$\{([\w.-]+)\}")
TOKENS = ("doc", "dir", "key")


def _now():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def read_rows(session, data, key):
    """``(order, {key: row})`` from a CSV; every row needs a unique, non-empty key."""
    from ...assets import read_bounded

    path = session.resolve(data)
    require(path.is_file() and path.suffix.lower() == ".csv", f"{data} is not a CSV file", "not_found",
            field="bind.data")
    text = read_bounded(path, MAX_BYTES).decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    require(reader.fieldnames and key in reader.fieldnames, f"{data} has no column {key!r}", field="bind.key",
            allowed=list(reader.fieldnames or []))
    order, rows = [], {}
    for number, row in enumerate(reader, 2):
        require(len(rows) < MAX_ROWS, f"At most {MAX_ROWS} rows", "resource_limit", field="bind.data")
        value = (row.get(key) or "").strip()
        require(value, f"{data} line {number}: the key column {key!r} is empty", field="bind.data")
        require(value not in rows, f"{data} line {number}: key {value!r} occurs twice", field="bind.data")
        order.append(value)
        rows[value] = {name: (cell if cell is not None else "") for name, cell in row.items() if name is not None}
    return order, rows


def row_diff(previous, rows):
    """``{added, changed: {key: [columns]}, removed, unchanged}`` between two ``{key: row}`` maps."""
    added = [key for key in rows if key not in previous]
    removed = [key for key in previous if key not in rows]
    changed, unchanged = {}, []
    for key in rows:
        if key in previous:
            columns = sorted(name for name in set(rows[key]) | set(previous[key])
                             if rows[key].get(name) != previous[key].get(name))
            if columns:
                changed[key] = columns
            else:
                unchanged.append(key)
    return {"added": added, "changed": changed, "removed": removed, "unchanged": unchanged}


def referenced(state):
    """Variable names a document uses: ``${name}`` references anywhere in its state, and its own variables."""
    import json

    return set(REFERENCE.findall(json.dumps(state))) | set(state.get("variables") or {})


def _snapshot_path(session, name):
    return session.resolve(f"{SNAPSHOTS}/{named(name)}.json")


def _validate(request):
    from ...automation import bounded_object

    bounded_object(request, REQUEST, "Unknown data-sync field")
    bind = request.get("bind")
    require(isinstance(bind, dict) and set(bind) == {"data", "key", "to"}, "bind is {data, key, to}", field="bind")
    require(isinstance(bind["data"], str) and isinstance(bind["key"], str) and bind["key"], "bind.data is a CSV path "
            "and bind.key a column name", field="bind")
    to = bind["to"]
    require(isinstance(to, dict) and len(set(to) & {"group", "spec", "merge"}) == 1
            and set(to) <= {"group", "spec", "merge", "source", "output"},
            "bind.to is {group: NAME}, {spec: campaign.json} or {merge: sheets.vixl}", field="bind.to")
    require(not (set(to) & {"source", "output"}) or "spec" in to, "source and output go with spec", field="bind.to")
    for flag in ("dry_run", "overwrite", "suites"):
        if flag in request:
            require(type(request[flag]) is bool, f"{flag} must be boolean", field=flag)
    exports = request.get("exports")
    if exports is not None:
        require("group" in to, "exports re-export the members of a group binding", field="exports")
        require(isinstance(exports, list) and 0 < len(exports) <= 16
                and all(isinstance(t, dict) and isinstance(t.get("path"), str) and "document" not in t
                        for t in exports), "exports is a list of export targets {path: 'out/{doc}.png', ...}",
                field="exports")
    return bind


def run(session, request):
    """The ``data-sync`` workflow action."""
    from ...production import read_json

    bind = _validate(request)
    name = named(request.get("name") or Path(bind["data"]).stem)
    order, rows = read_rows(session, bind["data"], bind["key"])
    snapshot_path = _snapshot_path(session, name)
    snapshot = read_json(snapshot_path) if snapshot_path.is_file() else None
    if snapshot is not None:
        require(snapshot.get("binding", {}).get("to") == bind["to"] and snapshot["binding"].get("key") == bind["key"],
                f"The binding {name!r} was made for another target or key; give a new name", field="name")
    previous = (snapshot or {}).get("rows") or {}
    diff = row_diff(previous, rows)
    result = {"name": name, "data": bind["data"], "key": bind["key"], "dry_run": request.get("dry_run", False),
              "snapshot": session.relative(snapshot_path), "first_sync": snapshot is None,
              "rows": {"total": len(rows), "added": diff["added"], "changed": diff["changed"],
                       "removed": diff["removed"], "unchanged": len(diff["unchanged"])}}
    to = bind["to"]
    if "group" in to:
        synced, outputs, extra = _group(session, request, bind, name, rows, previous, diff, snapshot)
    elif "spec" in to:
        synced, outputs, extra = _spec(session, request, bind, order, rows, previous, diff, snapshot)
    else:
        synced, outputs, extra = _merge(session, request, bind, rows, previous, diff)
    result.update(extra)
    if not result["dry_run"]:
        from ...production import file_digest, write_json

        write_json(snapshot_path, {"version": 1, "binding": bind, "updated": _now(),
                                   "data_sha256": file_digest(session.resolve(bind["data"])),
                                   "order": [key for key in (snapshot or {}).get("order", []) if key in synced]
                                   + [key for key in order if key not in (snapshot or {}).get("order", [])
                                      and key in synced],
                                   "rows": synced, "outputs": outputs})
        result["written"] = True
    else:
        result["written"] = False
    return result


# Groups ---------------------------------------------------------------------------------------

def _group(session, request, bind, name, rows, previous, diff, snapshot):
    from ..workspace_qa.workspace_checks import members
    from .candidate import commit, evaluate, load

    key = bind["key"]
    paths, _ = members(session, {"group": bind["to"]["group"]})
    old_outputs = (snapshot or {}).get("outputs") or {}
    touched = set(diff["added"]) | set(diff["changed"])
    entries, candidates, synced = [], {}, dict(previous)
    for key_value in diff["removed"]:
        synced.pop(key_value, None)
    held_keys = set()
    for path in paths:
        relative = session.relative(path)
        project = load(session, relative)
        value = project.state.get("variables", {}).get(key)
        entry = {"document": relative, "key": value}
        uses = referenced(project.state)
        if value is None:
            entries.append({**entry, "status": "unbound", "reason": f"the document has no variable {key!r}"})
            continue
        value = str(value)
        if value not in rows:
            entries.append({**entry, "status": "removed" if value in diff["removed"] else "no_row",
                            "reason": "its row was removed from the data" if value in diff["removed"]
                            else "the data has no row with its key"})
            continue
        columns = sorted(set(rows[value]) - {key})
        if value not in touched:
            entries.append({**entry, "status": "unchanged", "outputs": old_outputs.get(relative, [])})
            continue
        wanted = [column for column in (columns if value in diff["added"] else diff["changed"][value])
                  if column in uses and column != key]
        if not wanted:
            entries.append({**entry, "status": "unaffected", "reason": "the changed columns are not used by it",
                            "outputs": old_outputs.get(relative, [])})
            continue
        candidate = project.clone()
        candidate.apply([{"type": "variable", "name": column, "value": rows[value][column]} for column in wanted],
                        detail="compact")
        check = {"suites": request.get("suites", True)}
        evaluated = evaluate(session, relative, candidate, request=check, fail_on=request.get("fail_on", "error"))
        entry.update(columns=wanted, check=evaluated["after"], diff=evaluated.get("diff"),
                     newly_failing=evaluated["newly_failing"])
        if evaluated["passed"]:
            entry["status"] = "updated"
            candidates[relative] = candidate
        else:
            entry["status"] = "held"
            entry["reason"] = "the updated document fails its checks"
            held_keys.add(value)
        entries.append(entry)
    for value in touched:
        if value not in held_keys:
            synced[value] = rows[value]
    outputs = {member: list(items) for member, items in old_outputs.items()}
    planned = {relative: _planned(session, request, relative, value, old_outputs.get(relative, []))
               for relative, value in ((e["document"], e["key"]) for e in entries if e["status"] == "updated")}
    refused = [item["path"] for items in planned.values() for item in items if not item["replace_allowed"]]
    extra = {"documents": entries, "journal": f"data-sync-{name}",
             "counts": {status: sum(1 for e in entries if e["status"] == status)
                        for status in sorted({e["status"] for e in entries})}}
    if request.get("dry_run", False):
        extra["planned_exports"] = planned
        if refused:
            extra["refused"] = refused
        return synced, outputs, extra
    require(not refused, f"Re-export would replace file(s) data-sync did not write: {', '.join(refused[:5])}; set "
            "overwrite: true", "output_exists", field="exports")
    if candidates:
        extra["published"] = commit(session, f"data-sync-{name}", candidates)
    for relative, items in planned.items():
        if items:
            outputs[relative] = _export(session, request, relative, items)
            next(e for e in entries if e["document"] == relative)["outputs"] = outputs[relative]
    return synced, outputs, extra


def _planned(session, request, relative, value, old):
    tokens = {"doc": Path(relative).stem, "dir": Path(relative).parent.as_posix(), "key": re.sub(r"[^\w.-]+", "-", value)}
    owned = {item["path"]: item["sha256"] for item in old}
    found = []
    for target in request.get("exports") or []:
        unknown = sorted(set(re.findall(r"\{(\w*)\}", target["path"])) - set(TOKENS))
        require(not unknown, f"exports path uses unknown field(s) {unknown}; use {{doc}}, {{dir}} or {{key}}",
                field="exports")
        path = session.relative(session.resolve(re.sub(r"\{(\w+)\}", lambda m: tokens[m.group(1)], target["path"])))
        file = session.resolve(path)
        from ...production import file_digest

        mine = path in owned and file.is_file() and file_digest(file) == owned[path]
        found.append({"path": path, "target": target, "exists": file.exists(),
                      "replace_allowed": not file.exists() or mine or request.get("overwrite", False)})
    return found


def _export(session, request, relative, items):
    from ...export_batch import export_batch
    from ...io_policy import export_file
    from ...production import file_digest

    targets = [{**item["target"], "path": item["path"], "overwrite": item["exists"]} for item in items]
    result = export_batch(session, export_file, targets, document=relative)
    failed = [item["error"] for item in result["results"] if item.get("error")]
    if failed:
        raise VixlError("export_failed", f"Re-export of {relative} failed: {failed[0].get('message')}",
                        field="exports", errors=failed[:5])
    return [{"path": item["path"], "sha256": file_digest(session.resolve(item["path"]))} for item in items]


# Campaign specs -------------------------------------------------------------------------------

def _coerce(value, kind):
    text = str(value).strip()
    try:
        if kind == "integer":
            return int(text)
        if kind == "number":
            number = float(text)
            return int(number) if number.is_integer() and "." not in text else number
    except ValueError as exc:
        raise VixlError("invalid_value", f"{value!r} is not a {kind}", field="bind.data") from exc
    if kind == "boolean":
        require(text.lower() in ("true", "false", "1", "0", "yes", "no"), f"{value!r} is not a boolean",
                field="bind.data")
        return text.lower() in ("true", "1", "yes")
    return value


def _spec(session, request, bind, order, rows, previous, diff, snapshot):
    from ...production import plan, read_json, run as produce
    from .candidate import load

    to = bind["to"]
    campaign = read_json(session.resolve(to["spec"]))
    require(isinstance(campaign, dict) and isinstance(campaign.get("spec", {}), dict), f"{to['spec']} is a campaign "
            "file {source, output, spec}", field="bind.to.spec")
    source, output = to.get("source") or campaign.get("source"), to.get("output") or campaign.get("output")
    require(isinstance(source, str) and isinstance(output, str), "The campaign needs a source document and an output "
            "folder (in the campaign file or bind.to)", field="bind.to")
    project = load(session, source)
    inputs = (project.state.get("recipe") or {}).get("inputs")
    kept = [key for key in (snapshot or {}).get("order", []) if key in rows]
    ordered = kept + [key for key in order if key not in kept]

    def values(key):
        row = rows[key]
        if inputs is None:
            return dict(row)
        return {name: _coerce(cell, inputs[name].get("type", "string")) for name, cell in row.items() if name in inputs}

    spec = {**campaign.get("spec", {}), "rows": [values(key) for key in ordered]}
    planned = plan(spec)
    by_row = {number: key for number, key in enumerate(ordered, 1)}
    touched = set(diff["added"]) | set(diff["changed"])
    variants = [{"id": v["id"], "row": v["row"], "key": by_row[v["row"]], "artboard": v["artboard"],
                 "affected": by_row[v["row"]] in touched} for v in planned["variants"]]
    extra = {"campaign": to["spec"], "output": output,
             "variants": {"total": len(variants), "affected": [v["id"] for v in variants if v["affected"]]}}
    if request.get("dry_run", False):
        extra["planned"] = variants
        return dict(previous), {}, extra
    report = produce(project, spec, session.resolve(output))
    results = {r["id"]: r for r in report["results"]}
    extra["variants"].update(
        rendered=sorted(i for i, r in results.items() if r["status"] == "completed"),
        reused=sorted(i for i, r in results.items() if r["status"] == "reused"),
        held=sorted(i for i, r in results.items() if r["status"] not in ("completed", "reused")))
    extra["production"] = session.relative(session.resolve(output) / "production.json")
    extra["status"] = report["status"]
    held_rows = {by_row[r["row"]] for r in report["results"] if r["status"] not in ("completed", "reused")}
    synced = {key: (previous[key] if key in held_rows and key in previous else rows[key])
              for key in ordered if key not in held_rows or key in previous}
    return synced, {}, extra


# Merge sheets ---------------------------------------------------------------------------------

def _merge(session, request, bind, rows, previous, diff):
    from ...workflows import dispatch

    sheet = bind["to"]["merge"]
    changed = bool(diff["added"] or diff["changed"] or diff["removed"])
    extra = {"sheet": sheet, "rerun": changed}
    if request.get("dry_run", False) or not changed:
        extra["status"] = "reused" if not changed else "planned"
        return dict(rows) if not request.get("dry_run", False) else dict(previous), {}, extra
    result = dispatch(session, "merge-impose", {"rerun": sheet, "data": bind["data"], "replace": True})
    extra["merge"] = {key: result.get(key) for key in ("output", "sheet_document", "sheets", "copies", "count")
                      if key in result}
    extra["status"] = "updated"
    return dict(rows), {}, extra
