"""The organic-catalog workflow action."""

ACTIONS = {"organic-catalog": (set(), set())}


def dispatch(session, action, request, document=None):
    from .organic import catalog

    return catalog()
