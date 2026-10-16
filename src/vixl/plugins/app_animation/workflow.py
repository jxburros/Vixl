"""The app-animation-package workflow action."""

from .app_animation import FIELDS

ACTIONS = {"app-animation-package": (set(FIELDS), {"states", "default_state", "output"})}
FIELD_TYPES = {"app-animation-package": FIELDS}
SUMMARIES = {"app-animation-package": "Package named animation states, theme variants, reduced-motion images, "
             "editable masters and a sample consumer."}


def dispatch(session, action, request, document=None):
    from .app_animation import package

    return package(session, request)
