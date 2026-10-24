"""Workflow actions for brand deliverables: logo-package, brand-board, the mockup actions and print-art."""

from . import mockups, print_art
from .brand_board import FIELDS as BRAND_BOARD_FIELDS, field_types as brand_board_types
from .logo_package import FIELDS as LOGO_PACKAGE_FIELDS, field_types as logo_package_types

ACTIONS = {
    "logo-package": (LOGO_PACKAGE_FIELDS, {"output"}),
    "brand-board": (BRAND_BOARD_FIELDS, {"output"}),
    **mockups.ACTIONS,
    "print-art": (print_art.FIELDS, print_art.REQUIRED),
}
FIELD_TYPES = {
    "logo-package": logo_package_types(),
    "brand-board": brand_board_types(),
    **{action: {key: mockups.FIELD_TYPES[key] for key in fields} for action, (fields, _) in mockups.ACTIONS.items()},
    "print-art": print_art.FIELD_TYPES,
}
SUMMARIES = {
    "mockup": "Place designs into device, print or merch mockups (phone, laptop, browser, framed poster, business card, "
              "mug, tee, long-sleeve, hoodie, tote, sticker, enamel pin or a saved template) as live, corner-pinned "
              "links: named print areas (place), a garment colour, print finishes; optionally export each.",
    "mockup-list": "List the mockup templates: built-in and the workspace's own, with their slots, print areas "
                   "(physical print size) and default garment colour.",
    "mockup-save": "Save a mockup template (a scene, its four-corner slots and named print areas, base layers and "
                   "garment colour) to the workspace resource library.",
    "print-art": "Write print-ready art for each placed area of a product at its print size and dpi: editable "
                 "sources, PNGs, optional spot-colour separations (PNG or PDF pages) and a white underbase for dark "
                 "garments.",
}


def dispatch(session, action, request, document=None):
    if action == "logo-package":
        from .logo_package import build

        return build(session, request, document)
    if action == "brand-board":
        from .brand_board import build

        return build(session, request, document)
    if action == "print-art":
        return print_art.build(session, request, document)
    return mockups.dispatch(session, action, request, document)
