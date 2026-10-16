"""Layout repair: several candidate edits per design finding, ranked by least disruption."""

PLUGIN = {
    "name": "layout_repair",
    "title": "Layout repair",
    "summary": "repair-layout: try ranked candidate fixes for failing checks and keep the least disruptive one.",
    "kind": "workflows",
    "modules": ["layout_repair", "composition_repair", "workflow"],
    "workflows": ["workflow"],
}
