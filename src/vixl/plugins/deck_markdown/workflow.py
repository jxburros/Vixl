"""The deck-from-markdown workflow action."""

from .deck_markdown import ACTIONS, FIELD_TYPES as _TYPES, dispatch  # noqa: F401

FIELD_TYPES = {"deck-from-markdown": _TYPES}
