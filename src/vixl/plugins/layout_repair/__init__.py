"""Layout repair: several candidate edits per design finding, ranked by residual dead-band share, then disruption."""

PLUGIN = {
    "name": "layout_repair",
    "title": "Layout repair",
    "summary": "repair-layout: try ranked candidate fixes for failing checks and prefer the smallest residual dead band, then least disruption; dry runs report proposed outcomes.",
    "kind": "workflows",
    "modules": ["layout_repair", "composition_repair", "workflow"],
    "workflows": ["workflow"],
}
