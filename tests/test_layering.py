"""Module layering of the core (#632): no module imports a module of a higher layer, function-local imports included.

The layers, lowest first: leaf modules that import nothing of Vixl's above them, the document core, the features,
and the interfaces (CLI, REST, MCP). ``layering_baseline.json`` lists the imports that break the rule today; it may
only shrink. When an import goes away, remove its entry; never add one."""

import json
from pathlib import Path

from _imports import SRC, _imports, _module

LEAF = {"errors", "constants", "hashing", "model", "house_style", "sdk_compat", "untrusted"}
CORE = {"history", "fileio", "normalize", "schema", "validation", "targets", "project", "operations", "registry",
        "render"}
INTERFACES = {"cli", "cli_summary", "commands", "interfaces", "mcp_actions", "mcp_runtime", "mcp_tools", "workflows",
              "steps", "session", "design_cli", "feature_cli", "finishing_cli", "resource_cli", "__main__"}
BASELINE = Path(__file__).with_name("layering_baseline.json")


def layer(name):
    top = name.split(".")[0]
    if top in LEAF:
        return 0
    if top in CORE:
        return 1
    if top in INTERFACES:
        return 3
    return 2


def modules():
    """Every core module (plugins and the conversion kit have their own boundaries) and its own name."""
    for path in sorted((SRC / "vixl").rglob("*.py")):
        parts, _ = _module(path)
        if parts[:2] in (["vixl", "plugins"], ["vixl", "convert"]) or len(parts) < 2:
            continue
        yield path, ".".join(parts[1:])


def violations():
    known = {name for _, name in modules()}
    found = set()
    for path, name in modules():
        for target in _imports(path):
            if target[:1] != ("vixl",) or len(target) < 2:
                continue
            imported = ".".join(target[1:])
            if imported not in known:
                imported = target[1]  # ``from .render import color`` names a module attribute, not a module
            if imported in known and imported != name and layer(imported) > layer(name):
                found.add(f"{name} -> {imported}")
    return found


def test_no_module_imports_a_higher_layer_beyond_the_baseline():
    baseline = set(json.loads(BASELINE.read_text(encoding="utf-8")))
    found = violations()
    new = sorted(found - baseline)
    assert not new, f"Imports of a higher layer (move the code down, or behind a registry): {new}"
    gone = sorted(baseline - found)
    assert not gone, f"Fixed layering violations still listed in {BASELINE.name}; remove them: {gone}"

