"""The repair-layout workflow action."""

ACTIONS = {
    "repair-layout": ({"checks", "suites", "protected", "minimum_size", "max_candidates", "max_iterations",
                       "time_budget", "dry_run"}, set()),
}


def dispatch(session, action, request, document=None):
    from .layout_repair import repair_layout

    dry_run = request.get("dry_run", True)
    with session.project(write=not dry_run, document=document) as project:
        return repair_layout(project, checks=request.get("checks"), suites=request.get("suites", []),
                             protected=request.get("protected", []), minimum_size=request.get("minimum_size"),
                             max_candidates=request.get("max_candidates", 24),
                             max_iterations=request.get("max_iterations", 4),
                             time_budget=request.get("time_budget", 20), dry_run=dry_run)
