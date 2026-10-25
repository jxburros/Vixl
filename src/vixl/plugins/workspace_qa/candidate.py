"""Evaluate a candidate copy of a document, and commit it only when it is clean.

A candidate is a second copy of a saved document. A change (a function or a list of operations) is applied to the
copy, never saved; the copy runs ``vixl check`` and its attached suites (``workspace_checks.check_document``), and
its render is diffed against the document as saved (``image_diff.diff_images``). ``commit`` publishes the
candidates that passed through the project-group journal (``project_groups.commit``), so an interrupted
publication is rolled back with ``group-recover`` under the journal's name.

Public API (other plugins call these): ``load(session, document)``, ``evaluate(session, document, change, ...)``,
``evaluate_all(session, documents, change, ...)`` and ``commit(session, journal, evaluations)``.
"""

from contextlib import ExitStack
from pathlib import Path

from ...errors import VixlError, require

APPLY = ("never", "if-passing")


class Evaluation:
    """One evaluated candidate: ``report`` (JSON-ready), the saved ``original`` and the changed ``candidate``
    Projects, and the document's ``path``."""

    def __init__(self, path, original, candidate, report):
        self.path, self.original, self.candidate, self.report = path, original, candidate, report

    @property
    def passed(self):
        return self.report["status"] == "passed"

    @property
    def changed(self):
        return self.report.get("changed", False)


def load(session, document):
    """``(path, original, candidate)``: two independent copies of the saved document ``document``."""
    from ...project import Project

    path = document if isinstance(document, Path) else session.resolve(document)
    require(path.is_file() and path.suffix == ".vixl", f"{document} is not a .vixl document", "not_found",
            field="document")
    original = Project.load(path, limits=session.limits)
    candidate = Project.load(path, limits=session.limits)
    original._workspace = candidate._workspace = session.workspace
    require(candidate.transaction is None, f"{session.relative(path)} has an open transaction; commit it first")
    return path, original, candidate


def _apply(candidate, change):
    if change is None:
        return None
    if callable(change):
        return change(candidate)
    from ...io_policy import service_check
    from ...service_fonts import checker

    return candidate.apply(list(change), validator=checker(candidate, service_check), detail="compact")


def _diff(original, candidate, threshold):
    from ...image_diff import diff_images

    image, stats = diff_images(original.render().convert("RGBA"), candidate.render().convert("RGBA"),
                               threshold=threshold)
    return {key: stats[key] for key in ("changed_fraction", "changed_pixels", "changed_region", "identical")
            if key in stats}


def evaluate(session, document, change=None, *, request=None, fail_on="error", diff=True, threshold=8,
             loaded=None):
    """Apply ``change`` (``fn(candidate) -> result`` or a list of operations) to a copy of ``document`` and judge
    it: ``Evaluation.report`` is ``{document, status (passed, failed or error), changed, failing, check, diff,
    result}``. ``request`` holds the check options of ``check-all`` (``checks``, ``suites``, ``profile``,
    ``waivers``); a finding at ``fail_on`` or a suite that does not pass fails it. ``loaded`` reuses the
    ``(path, original, candidate)`` of ``load``; ``original`` may be None when the saved file cannot be opened (a
    converted copy), and the report then has no render diff."""
    from ...hashing import content_hash
    from .workspace_checks import check_document, failing

    request = dict(request or {})
    path, original, candidate = loaded or load(session, document)
    relative = session.relative(path)
    report = {"document": relative}
    try:
        result = _apply(candidate, change)
    except VixlError as exc:
        report.update(status="error", error=exc.as_dict(), changed=False)
        return Evaluation(path, original, candidate, report)
    # No original: the saved file cannot be opened by this release (a candidate made by the conversion kit).
    report["changed"] = original is None or (content_hash(candidate.state, default=str)
                                             != content_hash(original.state, default=str))
    if result is not None and not hasattr(result, "state"):
        report["result"] = result
    record = check_document(session, relative, request, project=candidate)
    record["failing"] = failing(record, fail_on)
    report["check"] = record
    report["failing"] = record["failing"]
    report["status"] = "error" if record.get("status") == "error" else "failed" if record["failing"] else "passed"
    if diff and record.get("status") != "error" and original is None:
        report["diff"] = {"error": "the saved document cannot be opened, so there is no render to compare"}
    elif diff and record.get("status") != "error":
        try:
            report["diff"] = _diff(original, candidate, threshold)
        except (VixlError, OSError, ValueError) as exc:
            report["diff"] = {"error": str(exc)[:300]}
    return Evaluation(path, original, candidate, report)


def commit(session, journal, evaluations):
    """Publish the candidates of ``evaluations`` (Evaluations, or ``{path: Project}``) through the journal
    ``journal``; all or none. Returns the published workspace paths."""
    from ...design import named
    from ..teamwork.project_groups import commit as publish

    journal = named(journal)
    if isinstance(evaluations, dict):
        chosen = dict(evaluations)
    else:
        chosen = {item.path: item.candidate for item in evaluations}
    publish(session, journal, chosen)
    return sorted(session.relative(path) for path in chosen)


def evaluate_all(session, documents, change, *, request=None, fail_on="error", apply="never", journal="candidates",
                 diff=True, progress=None):
    """Evaluate ``change`` on every document of ``documents`` (workspace paths) under their file locks. With
    ``apply: "if-passing"`` the candidates that pass and changed are published together through ``journal``
    (``group-recover`` rolls back an interrupted publication). ``change`` may be a function of
    ``(candidate, document)`` or a list of operations. Returns ``{documents, passes, fails, changed, published}``
    and the Evaluations."""
    from ...design import named
    from ...fileio import file_lock

    require(apply in APPLY, f"apply is one of {', '.join(APPLY)}", field="apply", allowed=list(APPLY))
    journal = named(journal)
    require(not session.resolve(f".vixl-groups/{journal}.transaction.json").exists(),
            f"Recover the interrupted edit first (group-recover {journal})")
    paths = [document if isinstance(document, Path) else session.resolve(document) for document in documents]
    evaluations = []
    with session._mutex, ExitStack() as stack:
        for path in paths:
            stack.enter_context(file_lock(str(path)))
        for index, path in enumerate(paths):
            relative = session.relative(path)
            step = (lambda candidate, relative=relative: change(candidate, relative)) if callable(change) else change
            try:
                evaluation = evaluate(session, path, step, request=request, fail_on=fail_on, diff=diff)
            except VixlError as exc:
                evaluation = Evaluation(path, None, None, {"document": relative, "status": "error",
                                                           "error": exc.as_dict(), "changed": False})
            evaluations.append(evaluation)
            if progress:
                progress(index + 1, len(paths), relative)
        published = []
        if apply == "if-passing":
            chosen = [item for item in evaluations if item.passed and item.changed]
            published = commit(session, journal, chosen) if chosen else []
    reports = [item.report for item in evaluations]
    summary = {"documents": reports, "passes": [r["document"] for r in reports if r["status"] == "passed"],
               "fails": [r["document"] for r in reports if r["status"] != "passed"],
               "changed": [r["document"] for r in reports if (r.get("diff") or {}).get("changed_pixels")],
               "published": published, "journal": journal, "apply": apply}
    return summary, evaluations
