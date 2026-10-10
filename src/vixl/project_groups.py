"""Project families with shared parameters, checked bulk edits and rollback journals."""

from contextlib import ExitStack
from copy import deepcopy
from pathlib import Path

from .design import named
from .errors import require
from .fileio import file_lock
from .production import read_json, write_json, publish_file, file_digest


def dispatch(session, action, request):
    from .interfaces import service_check
    from .schema import validate_operation

    if action == "group-list":
        directory = session.resolve(".vixl-groups")
        return {
            "groups": [
                read_json(session.resolve(path))
                for path in sorted(directory.glob("*.json"))
                if not path.name.endswith(".transaction.json")
            ]
        }
    name = named(request["name"])
    path = session.resolve(f".vixl-groups/{name}.json")
    journal = session.resolve(f".vixl-groups/{name}.transaction.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    with session._mutex, file_lock(str(path)):
        if action == "group-define":
            require(not journal.exists(), "Recover the interrupted group edit first")
            documents = request["documents"]
            require(isinstance(documents, list) and 0 < len(documents) <= 100, "Group needs 1–100 documents")
            resolved = [session.resolve(p) for p in documents]
            require(len(set(resolved)) == len(resolved), "Group members must be unique")
            require(
                all(p.is_file() and p.suffix == ".vixl" for p in resolved),
                "Group members must be existing .vixl files",
            )
            shared = request.get("shared", {})
            require(
                isinstance(shared, dict) and set(shared) <= {"variables", "swatches"},
                "Shared fields are variables and swatches",
            )
            for key in shared:
                require(isinstance(shared[key], dict), f"Shared {key} must be an object")
            for operation in shared_ops(shared):
                service_check(validate_operation(operation))
            value = {
                "version": 1,
                "name": name,
                "documents": [session.relative(p) for p in resolved],
                "shared": shared,
            }
            if "facts" in request:
                from .group_consistency import validate_facts

                validate_facts(request["facts"])
                value["facts"] = request["facts"]
            write_json(path, value)
            return value
        if action == "group-recover" and not path.exists():
            # Journals of replace-across over a glob have no group definition; the journal lists the files.
            return recover(session, name, None)
        require(path.exists(), "Unknown project group")
        group = read_json(path)
        if action == "group-show":
            return {**group, "recovery_required": journal.exists()}
        paths = sorted(session.resolve(p) for p in group["documents"])
        if action == "group-recover":
            return recover(session, name, paths)
        return apply_group(session, name, group, paths, request)


def apply_group(session, name, group, paths, request):
    from .interfaces import service_check
    from .project import Project
    from .service_fonts import checker

    journal = session.resolve(f".vixl-groups/{name}.transaction.json")
    require(not journal.exists(), "Recover the interrupted group edit first")
    dry_run = request.get("dry_run", True)
    operations = [*shared_ops(group["shared"]), *deepcopy(request.get("operations", []))]
    require(operations, "Provide shared parameters or bulk operations")
    members = [session.relative(p) for p in paths]
    publish = selection(session, request, members)
    candidates, originals, report = {}, {}, []
    with ExitStack() as stack:
        for target in paths:
            stack.enter_context(file_lock(str(target)))
        for target in paths:
            member = session.relative(target)
            original = Project.load(target, limits=session.limits)
            candidate = Project.load(target, limits=session.limits)
            candidate._workspace = original._workspace = session.workspace
            require(candidate.transaction is None, "Commit group member transactions first")
            result = candidate.apply(operations, check=checker(candidate, service_check), detail="compact")
            checks = [candidate.check_suite(suite) for suite in request.get("suites", [])]
            passed = all(check["passed"] for check in checks)
            if not dry_run and member in publish:
                require(passed, "Group checks failed; no documents saved", "check_failed", document=member,
                        checks=checks)
            candidates[target], originals[target] = candidate, original
            report.append({"document": member, "changes": result["changes"], "checks": checks, "passed": passed,
                           "decision": "accepted" if member in publish else "rejected"})
        output = {"name": name, "dry_run": dry_run, "documents": report,
                  "passed": all(entry["passed"] for entry in report)}
        if request.get("review"):
            require(dry_run, "review is written by a dry run; apply with accept/reject or decisions", field="review")
            output.update(write_review(session, request["review"], originals, candidates, report,
                                       title=f"Group change review: {name}", suites=request.get("suites", []),
                                       overwrite=request.get("overwrite", False)))
        if not dry_run:
            chosen = {target: candidate for target, candidate in candidates.items()
                      if session.relative(target) in publish}
            commit(session, name, chosen)
            output["published"] = sorted(session.relative(t) for t in chosen)
            output["untouched"] = sorted(set(members) - set(output["published"]))
        return output


def selection(session, request, members):
    """Members to publish: every member, narrowed by ``accept``, minus ``reject``, or the approved items of a
    proof page's ``decisions`` file (pending and rejected items are left untouched)."""
    accept, reject = request.get("accept"), request.get("reject", [])
    decisions = request.get("decisions")
    for field, value in (("accept", accept), ("reject", reject)):
        if value is not None:
            require(isinstance(value, list) and all(isinstance(v, str) for v in value),
                    f"{field} is a list of member paths", field=field)
    known = set(members)

    def member(value, field):
        relative = session.relative(session.resolve(value))
        require(relative in known, f"{field}: {value!r} is not a member", field=field, allowed=sorted(known))
        return relative

    chosen = set(members) if accept is None else {member(v, "accept") for v in accept}
    chosen -= {member(v, "reject") for v in reject}
    if decisions is not None:
        if isinstance(decisions, str):
            decisions = read_json(session.resolve(decisions))
        require(isinstance(decisions, dict) and isinstance(decisions.get("items"), list),
                "decisions is a proof page's downloaded decisions JSON (or its path)", field="decisions")
        approved = set()
        for item in decisions["items"]:
            require(isinstance(item, dict) and isinstance(item.get("path"), str), "decisions items need a path",
                    field="decisions")
            if item.get("decision") == "approved":
                approved.add(member(item["path"], "decisions"))
        chosen &= approved
    return chosen


def write_review(session, output, originals, candidates, report, *, title, suites=(), overwrite=False):
    """Before/after review of a dry run: an .html proof page with approve/reject per member (its
    downloaded decisions feed ``decisions``), or a .png contact sheet of before | after | diff."""
    import tempfile

    from .image_diff import diff_images
    from .production import contact_sheet, write_bytes

    destination = session.resolve(output)
    suffix = destination.suffix.lower()
    require(suffix in (".html", ".htm", ".png"), "review is an .html proof page or a .png contact sheet",
            field="review")
    require(overwrite or not destination.exists(), f"{output} already exists; set overwrite=true", field="review")
    entries = {entry["document"]: entry for entry in report}
    with tempfile.TemporaryDirectory(prefix="vixl-review-") as folder:
        folder = Path(folder)
        staged, sheet = {}, []
        for index, (target, candidate) in enumerate(candidates.items()):
            member = session.relative(target)
            before, after = originals[target].render().convert("RGBA"), candidate.render().convert("RGBA")
            image, stats = diff_images(before, after, mode="side-by-side")
            entries[member]["changed_fraction"] = stats["changed_fraction"]
            entries[member]["changed_region"] = stats["changed_region"]
            if suffix == ".png":
                name = f"{index:03d}.png"
                image.convert("RGB").save(folder / name)
                state = "unchanged" if not stats["changed_pixels"] else f"{stats['changed_fraction']:.1%}"
                sheet.append({"output": name, "id": Path(member).name, "status": state})
            else:
                copy = candidate.clone()
                copy.path, copy._revision = None, None
                staged[member] = folder / f"{index:03d}.vixl"
                copy.save(staged[member])
        if suffix == ".png":
            done = {"results": sheet}
            contact_sheet(folder, done)
            write_bytes(destination, (folder / done["contact_sheet"]).read_bytes(), replace=overwrite)
            return {"review": session.relative(destination)}
        from .proof import proof_page

        def resolve(value):
            if value in staged:
                return staged[value]
            return session.resolve(value[len("before:"):] if value.startswith("before:") else value)

        items = []
        for member in staged:
            entry = entries[member]
            checks = entry["checks"].items() if isinstance(entry["checks"], dict) else zip(suites, entry["checks"])
            outcome = "; ".join(f"suite {name}: {check['status']}" for name, check in checks)
            items.append({"path": member, "before": f"before:{member}",
                          "note": f"{entry['changed_fraction']:.1%} of pixels changed"
                                  + (f"; {outcome}" if outcome else "")})
        result = proof_page(items, destination, resolve=resolve, title=title, decisions=True, overwrite=overwrite,
                            limits=session.limits)
        return {"review": session.relative(destination), "decision_file": result["decision_file"]}


def commit(session, name, candidates):
    """Publish ``candidates`` ({path: Project}) through a durable journal: all of them, or none after a
    failure; an interrupted publication is undone by ``group-recover`` with ``name``."""
    import tempfile
    import shutil

    if not candidates:
        return
    folder = session.resolve(".vixl-groups")
    folder.mkdir(parents=True, exist_ok=True)
    journal = folder / f"{name}.transaction.json"
    require(not journal.exists(), "Recover the interrupted group edit first")
    paths = list(candidates)
    # Durable file backups keep journals small even for image-heavy projects.
    stage = Path(tempfile.mkdtemp(prefix=f".{name}-", dir=folder))
    transaction = {}
    try:
        for index, (target, candidate) in enumerate(candidates.items()):
            before, after = stage / f"{index}.before.vixl", stage / f"{index}.after.vixl"
            publish_file(before, target)
            candidate.path, candidate._revision = None, None
            candidate.save(after)
            transaction[session.relative(target)] = {
                "before": session.relative(before),
                "after": session.relative(after),
                "before_hash": file_digest(before),
                "after_hash": file_digest(after),
            }
        write_json(journal, transaction)
        try:
            for target in paths:
                publish_file(target, session.resolve(transaction[session.relative(target)]["after"]), replace=True)
        except BaseException:
            for target in paths:
                publish_file(target, session.resolve(transaction[session.relative(target)]["before"]), replace=True)
            journal.unlink()
            raise
        journal.unlink()
    finally:
        # Keep backups if rollback itself failed or the process was interrupted.
        if not journal.exists():
            shutil.rmtree(stage)


def recover(session, name, members):
    """Roll back the interrupted publication journalled under ``name``. ``members`` (paths) bounds which
    files the journal may name; None trusts the journal's own list (glob runs of replace-across)."""
    folder = session.resolve(".vixl-groups")
    journal = folder / f"{name}.transaction.json"
    require(journal.exists(), "No interrupted edit to recover")
    transaction = read_json(journal)
    require(isinstance(transaction, dict) and transaction, "Invalid recovery journal")
    paths = sorted(session.resolve(p) for p in transaction)
    if members is not None:
        require({session.relative(p) for p in paths} <= {session.relative(p) for p in members},
                "Invalid recovery journal")
    with ExitStack() as stack:
        for target in paths:
            stack.enter_context(file_lock(str(target)))
        for target in paths:
            entry = transaction[session.relative(target)]
            require(
                file_digest(target) in (entry["before_hash"], entry["after_hash"]),
                "Document changed after interrupted edit; manual recovery required",
                "stale_revision",
            )
        for target in paths:
            entry = transaction[session.relative(target)]
            backup = session.resolve(entry["before"])
            require(
                backup.parent.parent == folder and backup.name.endswith(".before.vixl"),
                "Invalid recovery backup",
            )
            require(file_digest(backup) == entry["before_hash"], "Recovery backup checksum mismatch")
        for target in paths:
            publish_file(target, session.resolve(transaction[session.relative(target)]["before"]), replace=True)
        journal.unlink()
        cleanup(session, transaction)
    return {"name": name, "recovered": True, "documents": sorted(transaction)}


def shared_ops(shared):
    return [{"type": "variable", "name": k, "value": v} for k, v in shared.get("variables", {}).items()] + [
        {"type": "swatch", "name": k, "color": v} for k, v in shared.get("swatches", {}).items()
    ]


def cleanup(session, transaction):
    import shutil

    for directory in {session.resolve(entry["before"]).parent for entry in transaction.values()}:
        shutil.rmtree(directory)
