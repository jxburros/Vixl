"""Evaluate a changed document before it is saved, and commit a set of them through one journal.

This is the candidate-evaluate pattern of the implementation plan (F4) in a small local form for data-sync and
bulk-upgrade: the change is made on a copy that is never saved over the source, the copy is checked (design checks
and its suites, as ``check-all`` checks a document) next to the original, the two renders are diffed, and only the
accepted copies are published with ``project_groups.commit``, whose journal ``group-recover`` rolls back. When the
shared F4 helper lands in ``workspace_qa`` this module should call it instead.
"""

from contextlib import ExitStack
import shutil
import uuid

from ...errors import VixlError

STAGING = ".vixl-runs/staging"


def load(session, relative):
    from ...project import Project

    project = Project.load(session.resolve(relative), limits=session.limits)
    project._workspace = session.workspace
    return project


def check_candidate(session, relative, candidate, request=None):
    """The check-all record of an unsaved ``candidate`` of ``relative``, checked from a staging copy (saving into
    another folder keeps its relative link sources pointing at the same files)."""
    from ..workspace_qa.workspace_checks import check_document

    folder = session.resolve(f"{STAGING}/{uuid.uuid4().hex}")
    staged = folder / relative
    try:
        staged.parent.mkdir(parents=True, exist_ok=True)
        copy = candidate.clone()
        copy.path, copy._revision = session.resolve(relative), None
        copy.save(staged)
        record = check_document(session, session.relative(staged), request or {})
    finally:
        shutil.rmtree(folder, ignore_errors=True)
        for parent in (folder.parent, folder.parent.parent):  # Leave no empty .vixl-runs behind a dry run.
            try:
                parent.rmdir()
            except OSError:
                break
    record["path"] = relative
    return record


def _render(project):
    try:
        return project.render().convert("RGBA")
    except (VixlError, OSError, ValueError) as exc:
        return exc


def evaluate(session, relative, candidate, *, request=None, before=None, fail_on="error", diff=True):
    """``{document, before, after, diff, passed, newly_failing}`` for ``candidate``, a changed copy of the document at
    ``relative``. ``before`` is the original's record (checked here when not given)."""
    from ...image_diff import diff_images
    from ..workspace_qa.workspace_checks import check_document, failing

    request = request or {}
    if before is None:
        before = check_document(session, relative, request)
    after = check_candidate(session, relative, candidate, request)
    before_failing, after_failing = failing(before, fail_on), failing(after, fail_on)
    result = {"document": relative, "before": _brief(before, before_failing), "after": _brief(after, after_failing),
              "passed": not after_failing,
              "newly_failing": [message for message in after_failing if message not in before_failing]}
    if diff:
        try:
            original = load(session, relative)
            old, new = _render(original), _render(candidate)
        except (VixlError, OSError, ValueError) as exc:
            old, new = exc, None
        if isinstance(old, Exception) or isinstance(new, Exception) or new is None:
            problem = old if isinstance(old, Exception) else new
            result["diff"] = {"unavailable": str(problem)[:300] if problem is not None else "no render"}
        else:
            _, stats = diff_images(old, new)
            result["diff"] = {key: stats[key] for key in ("changed_fraction", "changed_pixels", "changed_region",
                                                          "identical", "resized") if key in stats}
    return result


def _brief(record, messages):
    return {"status": record.get("status"), "errors": record.get("errors", 0), "warnings": record.get("warnings", 0),
            "failing": messages[:10], **({"error": record["error"]} if record.get("error") else {}),
            "suites": {name: suite["status"] for name, suite in (record.get("suites") or {}).items()}}


def commit(session, name, candidates):
    """Publish ``candidates`` ({workspace-relative path: Project}) all or none, journalled under ``name`` so that
    ``group-recover`` with that name rolls an interrupted publication back."""
    from ...fileio import file_lock
    from ..teamwork.project_groups import commit as publish

    paths = {session.resolve(relative): project for relative, project in candidates.items()}
    with session._mutex, ExitStack() as stack:
        for target in paths:
            stack.enter_context(file_lock(str(target)))
        publish(session, name, paths)
    return sorted(candidates)
