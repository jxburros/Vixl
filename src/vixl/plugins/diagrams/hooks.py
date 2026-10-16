"""Registry hooks for diagrams."""


def validate_state(project, state):
    from .diagrams import validate

    validate(state)


def check(checks, candidate, resolved, local_bounds, projection, issue, **context):
    if "diagram" in checks and candidate.state.get("diagrams"):
        from .diagrams import check_diagrams

        check_diagrams(candidate, resolved, local_bounds, projection, issue)


def after_apply(project):
    if project.state.get("diagrams"):
        from .diagrams import refresh

        refresh(project)


def apply_report(project, operations, result):
    if any(op["type"].startswith("diagram") for op in operations):
        from .diagrams import report

        result["diagram"] = report(project, operations)
