"""Hand drawings: import a sketch or photographed drawing, clean it, vectorize it and build on it."""

PLUGIN = {
    "name": "drawing",
    "title": "Hand drawing",
    "summary": "Import, clean, vectorize, straighten, fill and restyle hand drawings and photographed sketches.",
    "kind": "operations",
    "modules": ["drawing", "paper", "gaps", "hooks", "workflow"],
    "operations": ["drawing"],
    "commands": ["drawing"],
    "workflows": ["workflow"],
    "hooks": {"validate-layer": ["hooks:validate_layer"], "check": ["hooks:check"]},
    "requires": ["ai", "organic"],
}
