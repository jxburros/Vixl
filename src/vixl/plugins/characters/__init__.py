"""Characters: portable standard-part characters, constrained rigs and retargetable motion cycles."""

PLUGIN = {
    "name": "characters",
    "title": "Characters",
    "summary": "Standard-part characters with planar rigs, poses and retargetable walk, idle and other cycles.",
    "kind": "operations",
    "modules": ["characters", "hooks"],
    "operations": ["characters"],
    "hooks": {"check": ["hooks:check"]},
}
