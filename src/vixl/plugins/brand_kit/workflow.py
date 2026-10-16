"""Workflow actions for brand deliverables: logo-package, brand-board and the mockup actions."""

from . import mockups
from .brand_board import FIELDS as BRAND_BOARD_FIELDS, field_types as brand_board_types
from .logo_package import FIELDS as LOGO_PACKAGE_FIELDS, field_types as logo_package_types

ACTIONS = {
    "logo-package": (LOGO_PACKAGE_FIELDS, {"output"}),
    "brand-board": (BRAND_BOARD_FIELDS, {"output"}),
    **mockups.ACTIONS,
}
FIELD_TYPES = {
    "logo-package": logo_package_types(),
    "brand-board": brand_board_types(),
    **{action: {key: mockups.FIELD_TYPES[key] for key in fields} for action, (fields, _) in mockups.ACTIONS.items()},
}


def dispatch(session, action, request, document=None):
    if action == "logo-package":
        from .logo_package import build

        return build(session, request, document)
    if action == "brand-board":
        from .brand_board import build

        return build(session, request, document)
    return mockups.dispatch(session, action, request, document)
