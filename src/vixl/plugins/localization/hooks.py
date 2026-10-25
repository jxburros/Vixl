"""Registry hooks for localization: the document record's validation and the locale variant check."""


def validate_state(project, state):
    from .locales import validate

    validate(project, state)


def check_variants(project, request):
    """``vixl check --locales`` and the workflow ``check`` field ``locales``: the locale check report, or None when
    the request names no locales."""
    if request.get("locales") is None:
        return None
    from .locale_check import check_locales, markdown

    report = check_locales(project, {key: value for key, value in request.items() if key != "format"})
    if request.get("format") == "markdown":
        report["markdown"] = markdown(report)
    return report
