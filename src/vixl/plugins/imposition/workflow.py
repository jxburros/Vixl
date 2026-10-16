"""The merge-impose workflow action."""

from .imposition import ACTIONS, FIELD_TYPES as _TYPES  # noqa: F401  (ACTIONS is the registry entry)

FIELD_TYPES = {"merge-impose": _TYPES}


def dispatch(session, action, request, document=None):
    from .imposition import dispatch as merge_dispatch

    return merge_dispatch(session, request, document)
