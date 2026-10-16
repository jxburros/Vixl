"""Registry hooks for hand drawings."""


def validate_layer(layer, state, project):
    if "drawing" in layer or "drawing_strokes" in layer:
        from .drawing import validate

        validate(layer, state, project)


def check(checks, candidate, resolved, issue, **context):
    if "drawing" in checks:
        from .drawing import check_drawings

        check_drawings(candidate, list(resolved.values()), issue)
