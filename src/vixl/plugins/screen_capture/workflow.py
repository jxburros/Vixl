"""The screen-capture workflow action."""

from .screen_capture import FIELDS

ACTIONS = {"screen-capture": (set(FIELDS), {"output"})}
FIELD_TYPES = {"screen-capture": FIELDS}
SUMMARIES = {"screen-capture": "Explicitly capture the local desktop, a pixel rectangle, or a Windows HWND to a PNG."}


def dispatch(session, action, request, document=None):
    from .screen_capture import capture

    return capture(session, request)
