"""Workflow actions for workspace-wide checks and edits, proofs and reproducibility."""

from pathlib import Path

from ...errors import require

ACTIONS = {
    "proof": ({"items", "output", "title", "check", "decisions", "max_size", "overwrite", "overlay"}, {"items", "output"}),
    "protected-edit": ({"operations", "protect", "regions", "tolerance", "structural", "pixels", "dry_run"},
                       {"operations"}),
    "reproduce": ({"reference", "tolerance", "max_fraction", "lock", "write_lock", "overwrite"}, set()),
    "check-all": ({"documents", "group", "checks", "suite", "suites", "fail_on", "profile", "waivers", "workers",
                   "changed_since", "base",
                   "work", "since_last", "history", "group_checks", "reference", "facts", "outputs", "overwrite"},
                  set()),
    "replace-across": ({"name", "documents", "replace", "dry_run", "suites", "accept", "reject", "decisions", "review",
                        "overwrite", "journal"}, {"replace"}),
}


def dispatch(session, action, request, document=None):
    if action == "proof":
        from .proof import proof_page

        for field in ("check", "decisions", "overwrite", "overlay"):
            require(type(request.get(field, False)) is bool, f"{field} must be boolean", field=field)
        result = proof_page(request["items"], request["output"], resolve=session.resolve,
                            title=request.get("title"), check=request.get("check", True),
                            decisions=request.get("decisions", False), max_size=request.get("max_size", 1200),
                            overwrite=request.get("overwrite", False), limits=session.limits,
                            overlay=request.get("overlay", False))
        result["output"] = session.relative(Path(result["output"]))
        return result
    if action == "protected-edit":
        from ...io_policy import service_check
        from .protected_edit import protected_edit

        for field in ("structural", "pixels"):
            require(type(request.get(field, True)) is bool, f"{field} must be boolean", field=field)
        dry_run = request.get("dry_run", False)
        with session.project(write=not dry_run, document=document) as project:
            return protected_edit(project, request["operations"], protect=request.get("protect", []),
                                  regions=request.get("regions", []), tolerance=request.get("tolerance", 0),
                                  structural=request.get("structural", True), pixels=request.get("pixels", True),
                                  dry_run=dry_run, validator=service_check)
    if action == "reproduce":
        from .reproduce import read_lock, reproduce, write_lock

        require(type(request.get("overwrite", False)) is bool, "overwrite must be boolean", field="overwrite")
        with session.project(document=document) as project:
            result = {}
            if request.get("write_lock"):
                write_lock(project, session.resolve(request["write_lock"]), overwrite=request.get("overwrite", False))
                result["lock_written"] = request["write_lock"]
            result.update(reproduce(
                project, reference=session.resolve(request["reference"]) if request.get("reference") else None,
                tolerance=request.get("tolerance", 0), max_fraction=request.get("max_fraction", 0.0),
                locked=read_lock(session.resolve(request["lock"])) if request.get("lock") else None,
                limits=session.limits))
            if result.get("reference"):
                result["reference"]["path"] = request["reference"]
            return result
    if action == "check-all":
        from .workspace_checks import run

        return run(session, request)
    from .replace_across import run

    return run(session, request)
