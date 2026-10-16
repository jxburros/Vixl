"""Figma import: a Figma file (URL, key or exported JSON) becomes editable Vixl layers."""

PLUGIN = {
    "name": "figma_import",
    "title": "Figma import",
    "summary": "Import a Figma page or node as editable layers, with images, fonts and unsupported nodes rasterized.",
    "kind": "importer",
    "modules": ["figma_import", "hooks"],
    "hooks": {"import-format": ["hooks:import_figma"]},
}
