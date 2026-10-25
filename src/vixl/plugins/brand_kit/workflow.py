"""Workflow actions for brand deliverables: logo-package, brand-board, the mockup actions, print-art and
the Design Profile import and export (brand-import, brand-export)."""

import json

from . import mockups, print_art
from .brand_board import FIELDS as BRAND_BOARD_FIELDS, field_types as brand_board_types
from .logo_package import FIELDS as LOGO_PACKAGE_FIELDS, field_types as logo_package_types
from ...errors import require

ACTIONS = {
    "logo-package": (LOGO_PACKAGE_FIELDS, {"output"}),
    "brand-board": (BRAND_BOARD_FIELDS, {"output"}),
    "brand-import": ({"profile", "output", "overwrite", "dry_run"}, {"profile"}),
    "brand-export": ({"output", "preset", "overwrite"}, {"output"}),
    **mockups.ACTIONS,
    "print-art": (print_art.FIELDS, print_art.REQUIRED),
}
PROFILE_TYPES = {
    "profile": {"type": ["string", "object"],
                "description": "brand-import: the Design Profile (schemaVersion 2) as a workspace JSON file or inline; "
                               "a brand.json object is accepted too."},
    "output": {"type": "string", "description": "brand-import: the brand file to write (default brand.json); "
                                                "brand-export: the Design Profile JSON file to write."},
    "overwrite": {"type": "boolean", "default": False, "description": "Replace an existing output file."},
    "dry_run": {"type": "boolean", "default": False,
                "description": "brand-import: report the brand and the unmapped paths without writing."},
    "preset": {"type": "string", "description": "brand-export: export this brand.json preset instead of the base."},
}
FIELD_TYPES = {
    "logo-package": logo_package_types(),
    "brand-board": brand_board_types(),
    **{action: {key: mockups.FIELD_TYPES[key] for key in fields} for action, (fields, _) in mockups.ACTIONS.items()},
    "print-art": print_art.FIELD_TYPES,
    **{action: {key: PROFILE_TYPES[key] for key in ACTIONS[action][0]} for action in ("brand-import", "brand-export")},
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
    "brand-import": "Map a Design Profile (schemaVersion 2: typography, colours, page, docText) to the workspace "
                    "brand.json; lists the profile paths it could not map.",
    "brand-export": "Write the workspace brand.json (or a preset) as a Design Profile; lists the brand fields it "
                    "could not map.",
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
    if action in ("brand-import", "brand-export"):
        return profile_action(session, action, request)
    return mockups.dispatch(session, action, request, document)


def _output(session, request, default, write=True):
    output = request.get("output", default)
    require(isinstance(output, str) and output.lower().endswith(".json"), "output is a .json path", field="output")
    require(type(request.get("overwrite", False)) is bool, "overwrite must be boolean", field="overwrite")
    path = session.resolve(output)
    require(not write or request.get("overwrite", False) or not path.exists(),
            f"{session.relative(path)} exists; set overwrite=true or choose another path", "output_exists", field="output")
    return path


def _write(session, path, data):
    session.make_parent(path)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def profile_action(session, action, request):
    """brand-export writes the workspace brand as a Design Profile; brand-import writes brand.json from one."""
    from ...brand import load, summary
    from ...io_policy import read_json
    from .design_profile import from_brand, load_brand_or_profile

    if action == "brand-export":
        require(request.get("preset") is None or isinstance(request["preset"], str), "preset must be text",
                field="preset")
        kit = load(session.workspace, request.get("preset"))
        require(kit, "brand-export needs a brand.json in the workspace", field="output")
        profile, unmapped = from_brand(kit)
        path = _output(session, request, "design-profile.json")
        _write(session, path, profile)
        return {"output": session.relative(path), "profile": profile, "unmapped": unmapped}
    source = request["profile"]
    require(isinstance(source, (str, dict)), "profile is a workspace JSON file or an inline object", field="profile")
    require(type(request.get("dry_run", False)) is bool, "dry_run must be boolean", field="dry_run")
    dry_run = request.get("dry_run", False)
    data = read_json(session.resolve(source)) if isinstance(source, str) else source
    kit, unmapped = load_brand_or_profile(data)
    path = _output(session, request, "brand.json", write=not dry_run)
    if not dry_run:
        _write(session, path, kit)
    return {"output": session.relative(path), "written": not dry_run, "brand": summary(kit), "unmapped": unmapped}
