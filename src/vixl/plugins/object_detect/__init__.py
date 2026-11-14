"""Object detection: propose which layers of an existing document form which objects, and of what kind."""

PLUGIN = {
    "name": "object_detect",
    "title": "Object detection",
    "summary": "object-detect: propose groupings and kinds for undeclared objects from recipes, names and touching "
               "ink; a dry run unless apply is set, and offline unless a provider is named.",
    "kind": "workflows",
    "modules": ["detect", "workflow", "commands"],
    "workflows": ["workflow"],
    "hooks": {"cli-command": ["commands:command"]},
    "requires": ["ai"],
}
