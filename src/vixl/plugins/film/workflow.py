"""Workflow actions for films and media analysis."""

from . import media_analysis

ACTIONS = {
    "film-plan": ({"spec"}, {"spec"}),
    "film-export": ({"spec", "output"}, {"spec", "output"}),
    **media_analysis.ACTIONS,
}
FIELD_TYPES = {action: media_analysis.FIELD_TYPES for action in media_analysis.ACTIONS}


def dispatch(session, action, request, document=None):
    if action in media_analysis.ACTIONS:
        return media_analysis.dispatch(session, action, request, document)
    from .film import plan, export

    if action == "film-plan":
        return plan(request["spec"], session.limits)
    return export(request["spec"], session.workspace, session.resolve(request["output"]), limits=session.limits)
