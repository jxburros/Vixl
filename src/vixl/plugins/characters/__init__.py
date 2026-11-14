"""Characters: portable standard-part characters, constrained rigs, retargetable motion cycles and packages."""

PLUGIN = {
    "name": "characters",
    "title": "Characters",
    "summary": "Standard-part characters (humanoid and four-legged) with planar rigs, poses and retargetable walk, gallop, idle and other cycles, shared "
               "as .vixlchar packages with named expressions, poses and motions.",
    "kind": "operations",
    "modules": ["characters", "hooks", "package", "quadruped", "workflow"],
    "operations": ["characters"],
    "workflows": ["workflow"],
    "hooks": {"check": ["hooks:check"]},
}
