"""Workflow actions for hand drawings: a report and a side-by-side comparison image."""

from ...errors import require

ACTIONS = {
    "drawing-report": ({"target"}, {"target"}),
    "drawing-compare": ({"target", "output"}, {"target", "output"}),
}


def dispatch(session, action, request, document=None):
    from .drawing import compare, report

    with session.project(document=document) as project:
        result = report(project, request["target"])
        if action == "drawing-compare":
            destination = session.resolve(request["output"])
            require(destination.suffix.lower() == ".png" and not destination.exists(),
                    "Choose a new .png output", field="output")
            compare(project, request["target"]).save(destination)
            result["output"] = session.relative(destination)
        return result
