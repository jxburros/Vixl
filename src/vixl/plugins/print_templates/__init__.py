"""Printer's templates: read a template's coloured lines into role guides, and reuse them as guide sets."""

PLUGIN = {
    "name": "print_templates",
    "title": "Print templates",
    "summary": "Import a printer's template (PNG or PSD) as role guides (safe areas, keep-outs, folds, trim) and "
               "save them as reusable guide sets.",
    "kind": "workflows",
    "modules": ["detect", "psd_guides", "guide_sets", "workflow", "commands"],
    "operations": ["guide_sets"],
    "commands": ["guide_sets"],
    "workflows": ["workflow"],
    "hooks": {"resource-kind": ["guide_sets:resource_kind"], "cli-command": ["commands:command"]},
}
