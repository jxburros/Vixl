"""Characters: portable standard-part characters, constrained rigs, retargetable motion cycles and packages."""

PLUGIN = {
    "name": "characters",
    "title": "Characters",
    "summary": "Standard-part characters with planar rigs, poses and retargetable walk, idle and other cycles, shared "
               "as .vixlchar packages with named expressions, poses and motions.",
    "kind": "operations",
    "modules": ["characters", "hooks", "package", "workflow"],
    "operations": ["characters"],
    "workflows": ["workflow"],
    "hooks": {"check": ["hooks:check"]},
}
