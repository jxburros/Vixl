"""PSD import: a layered Photoshop file becomes image layers and groups."""

PLUGIN = {
    "name": "psd_import",
    "title": "PSD import",
    "summary": "Import a layered Photoshop (PSD) file as image layers, groups and layer masks.",
    "kind": "importer",
    "modules": ["psd_import", "hooks"],
    "hooks": {"import-format": ["hooks:import_psd"]},
}
