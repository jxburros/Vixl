"""How data-sync and bulk-upgrade use the shared candidate evaluation (``workspace_qa.candidate``, foundation F4).

The change is evaluated on an unsaved copy and committed through the project-group journal by ``workspace_qa``; this
module adds only what both actions report on top of it: the original's own check next to the copy's (``before`` and
``after``, and the findings that are ``newly_failing``), and the file locks that keep every document of the action
from being saved by anyone else between its evaluation and the commit.
"""

from contextlib import contextmanager, ExitStack


@contextmanager
def locked(session, relatives):
    """Hold the write lock of every document in ``relatives`` (in a stable order) for the whole block."""
    from ...fileio import file_lock

    with session._mutex, ExitStack() as stack:
        for relative in sorted(set(relatives)):
            stack.enter_context(file_lock(str(session.resolve(relative))))
        yield


def brief(record, messages):
    return {"status": record.get("status"), "errors": record.get("errors", 0), "warnings": record.get("warnings", 0),
            "failing": messages[:10], **({"error": record["error"]} if record.get("error") else {}),
            "suites": {name: suite["status"] for name, suite in (record.get("suites") or {}).items()}}


def judge(session, evaluation, *, request, before=None, fail_on="error"):
    """``{before, after, diff, passed, newly_failing}`` of an ``Evaluation``; ``before`` is the original's check
    record (checked here when not given)."""
    from ..workspace_qa.workspace_checks import check_document, failing

    relative = evaluation.report["document"]
    if before is None:
        before = check_document(session, relative, request)
    record = evaluation.report.get("check")
    if record is None:  # the change itself failed
        error = evaluation.report.get("error") or {}
        record = {"status": "error", "error": str(error.get("message") or error)[:500]}
    before_failing, after_failing = failing(before, fail_on), failing(record, fail_on)
    result = {"before": brief(before, before_failing), "after": brief(record, after_failing),
              "passed": evaluation.passed,
              "newly_failing": [message for message in after_failing if message not in before_failing]}
    if evaluation.report.get("diff") is not None:
        diff = evaluation.report["diff"]
        result["diff"] = {"unavailable": diff["error"]} if "error" in diff else diff
    return result
