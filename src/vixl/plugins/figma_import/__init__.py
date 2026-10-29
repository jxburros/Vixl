"""Editable Figma interchange and import from a Figma file, URL or key."""

PLUGIN = {
    "name": "figma_import",
    "title": "Figma interchange",
    "summary": "Import Figma files and export editable Figma interchange with embedded images and loss reports.",
    "kind": "importer",
    "modules": ["figma_import", "figma_export", "hooks"],
    "hooks": {"import-format": ["hooks:import_figma"], "export-format": ["hooks:export_figma"]},
}
