"""Project families with shared parameters, checked bulk edits and rollback journals."""

from contextlib import ExitStack
from copy import deepcopy

from .design import named
from .errors import require
from .fileio import file_lock
from .production import read_json, write_json, publish_file, file_digest


def dispatch(session, action, request):
    from .interfaces import service_check
    from .project import Project
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
            suites = request.get("suites", [])
            if suites:
                from .assurance import validate_library_names
                from .resources import get

                validate_library_names(suites, "group-define")
                for suite in suites:
                    get("suites", suite, workspace=session.workspace)
            value = {
                "version": 1,
                "name": name,
                "documents": [session.relative(p) for p in resolved],
                "shared": shared,
                **({"suites": suites} if suites else {}),
            }
            write_json(path, value)
            return value
        require(path.exists(), "Unknown project group")
        group = read_json(path)
        if action == "group-show":
            return {**group, "recovery_required": journal.exists()}
        paths = sorted(session.resolve(p) for p in group["documents"])
        with ExitStack() as stack:
            for target in paths:
                stack.enter_context(file_lock(str(target)))
            if action == "group-recover":
                require(journal.exists(), "No interrupted edit to recover")
                transaction = read_json(journal)
                require(set(transaction) == {session.relative(p) for p in paths}, "Invalid recovery journal")
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
                        backup.parent.parent == path.parent and backup.name.endswith(".before.vixl"),
                        "Invalid recovery backup",
                    )
                    require(file_digest(backup) == entry["before_hash"], "Recovery backup checksum mismatch")
                for target in paths:
                    publish_file(
                        target, session.resolve(transaction[session.relative(target)]["before"]), replace=True
                    )
                journal.unlink()
                cleanup(session, transaction)
                return {"name": name, "recovered": True}
            require(not journal.exists(), "Recover the interrupted group edit first")
            operations = [*shared_ops(group["shared"]), *deepcopy(request.get("operations", []))]
            require(operations, "Provide shared parameters or bulk operations")
            # Members are held to the group's library suites unless the request names the suites to run.
            suites = request.get("suites", group.get("suites", []))
            candidates, report = {}, []
            for target in paths:
                candidate = Project.load(target, limits=session.limits)
                candidate._workspace = session.workspace
                require(candidate.transaction is None, "Commit group member transactions first")
                result = candidate.apply(operations, check=service_check, detail="compact")
                checks = [candidate.check_suite(suite) for suite in suites]
                require(
                    all(check["passed"] for check in checks),
                    "Group checks failed; no documents saved",
                    "check_failed",
                    document=session.relative(target),
                    checks=checks,
                )
                candidates[target] = candidate
                report.append(
                    {"document": session.relative(target), "changes": result["changes"], "checks": checks}
                )
            if not request.get("dry_run", True):
                # Durable file backups keep journals small even for image-heavy projects.
                import tempfile
                from pathlib import Path
                import shutil

                stage = Path(tempfile.mkdtemp(prefix=f".{name}-", dir=path.parent))
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
                            publish_file(
                                target,
                                session.resolve(transaction[session.relative(target)]["after"]),
                                replace=True,
                            )
                    except BaseException:
                        for target in paths:
                            publish_file(
                                target,
                                session.resolve(transaction[session.relative(target)]["before"]),
                                replace=True,
                            )
                        journal.unlink()
                        raise
                    journal.unlink()
                finally:
                    # Keep backups if rollback itself failed or the process was interrupted.
                    if not journal.exists():
                        shutil.rmtree(stage)
            return {"name": name, "dry_run": request.get("dry_run", True), "documents": report}


def shared_ops(shared):
    return [{"type": "variable", "name": k, "value": v} for k, v in shared.get("variables", {}).items()] + [
        {"type": "swatch", "name": k, "color": v} for k, v in shared.get("swatches", {}).items()
    ]


def cleanup(session, transaction):
    import shutil

    for directory in {session.resolve(entry["before"]).parent for entry in transaction.values()}:
        shutil.rmtree(directory)
