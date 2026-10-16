"""Brand kit deliverables: a logo delivery package, a brand guidelines board and device or print mockups."""

PLUGIN = {
    "name": "brand_kit",
    "title": "Brand kit",
    "summary": "Logo packages, brand guideline boards and device or print mockups from a brand.json and a logo.",
    "kind": "workflows",
    "modules": ["logo_package", "brand_board", "mockups", "workflow"],
    "workflows": ["workflow"],
    "requires": ["drawing", "workspace_qa"],
}
