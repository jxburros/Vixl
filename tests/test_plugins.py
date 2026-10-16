"""Built-in plugins: valid manifests, declared dependencies, and the core/plugin boundary (docs/reference/plugins.md)."""

import ast
from pathlib import Path
import re

import pytest

from vixl import plugins

SRC = Path(__file__).resolve().parents[1] / "src"
PLUGIN_ROOT = SRC / "vixl" / "plugins"

# Core modules that still import plugin modules directly, and why. A plugin can ship separately only when no
# entry names it. Remove an entry when its import moves behind a registry hook; add one only with a reason.
KNOWN_COUPLINGS = {
    ("accessibility", "charts.charts"): "chart series colors in the accessibility report",
    ("checks", "charts.charts"): "chart text contrast and series colors inside the contrast check",
    ("pptx_export", "charts.chart_pptx"): "native PowerPoint charts",
    ("pptx_export", "charts.table_pptx"): "native PowerPoint tables",
    ("containers", "charts.key_values"): "containers fit key-value lists when they reflow",
    ("convert.rules", "charts.charts"): "converted documents reuse the chart style",
    ("audio", "film.media_analysis"): "audio tracks probe media duration",
    ("jobs", "film.film"): "the job queue runs film jobs",
    ("jobs", "lyrics.lyrics"): "the job queue runs lyric video jobs",
    ("jobs", "ai.ai"): "the job queue runs generation and video jobs",
    ("cli", "ai.ai"): "vixl ai, ask, generate, detect and ocr commands",
    ("cli", "ai.models"): "vixl models",
    ("interfaces", "ai.ai"): "the REST AI endpoint",
    ("mcp_tools", "ai.ai"): "the MCP AI action",
    ("mcp_tools", "ai.models"): "MCP model discovery",
    ("cli", "imposition.imposition"): "vixl merge",
    ("cli", "workspace_qa.reproduce"): "vixl reproduce",
    ("cli", "workspace_qa.workspace_checks"): "vixl check --all and --group",
    ("group_consistency", "workspace_qa.workspace_checks"): "group checks load the group's documents",
    ("feature_cli", "drawing.drawing"): "vixl drawing report and compare",
    ("feature_cli", "organic.organic"): "vixl organics",
    ("parts", "drawing.drawing"): "the connected-parts check uses the drawing erode and dilate",
    ("mcp_actions", "characters.characters"): "MCP character export",
    ("timeline", "characters.characters"): "timeline frames pose characters",
    ("resources", "brand_kit.mockups"): "the resource library validates mockup templates",
}


def _module(path):
    parts = list(path.relative_to(SRC).with_suffix("").parts)
    if parts[-1] == "__init__":
        return parts[:-1], True
    return parts, False


def _imports(path):
    """Absolute module paths imported by ``path`` (relative imports resolved, from-imported submodules included)."""
    parts, is_pkg = _module(path)
    package = parts if is_pkg else parts[:-1]
    found = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            found.update(tuple(alias.name.split(".")) for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = package[: len(package) - node.level + 1] if node.level else []
            target = base + (node.module.split(".") if node.module else [])
            found.add(tuple(target))
            found.update(tuple(target + [alias.name]) for alias in node.names)
    return found


def _plugin_module(target):
    """``plugin.module`` for an import of a plugin module, else None (the registry and external are core API)."""
    if len(target) >= 4 and target[:2] == ("vixl", "plugins") and target[2] in plugins.BUILTIN:
        return f"{target[2]}.{target[3]}"
    if len(target) == 3 and target[:2] == ("vixl", "plugins") and target[2] in plugins.BUILTIN:
        return f"{target[2]}.__init__"
    return None


def core_edges():
    edges = set()
    for path in sorted((SRC / "vixl").rglob("*.py")):
        parts, _ = _module(path)
        if parts[:2] == ["vixl", "plugins"]:
            continue
        for target in _imports(path):
            owner = _plugin_module(target)
            if owner:
                edges.add((".".join(parts[1:]), owner))
    return edges


def test_core_reaches_plugins_only_through_the_registry():
    edges = core_edges()
    unexpected = sorted(edges - KNOWN_COUPLINGS.keys())
    assert not unexpected, ("Core modules import plugin modules directly; use a registry role or hook "
                            f"(docs/reference/plugins.md) or justify the import in KNOWN_COUPLINGS: {unexpected}")
    stale = sorted(KNOWN_COUPLINGS.keys() - edges)
    assert not stale, f"These couplings are gone; remove them from KNOWN_COUPLINGS: {stale}"


def test_plugin_imports_of_other_plugins_are_declared():
    for name in plugins.BUILTIN:
        used = set()
        for path in (PLUGIN_ROOT / name).glob("*.py"):
            for target in _imports(path):
                owner = _plugin_module(target)
                if owner and owner.split(".")[0] != name:
                    used.add(owner.split(".")[0])
        assert used <= set(plugins.manifest(name).get("requires", ())), (name, sorted(used))


@pytest.mark.parametrize("name", plugins.BUILTIN)
def test_manifest_is_complete_and_matches_the_package(name):
    m = plugins.manifest(name)
    assert set(m) <= plugins.MANIFEST_KEYS
    assert m["kind"] in plugins.KINDS and m["title"] and m["summary"].endswith(".")
    files = {p.stem for p in (PLUGIN_ROOT / name).glob("*.py")} - {"__init__"}
    assert set(m["modules"]) == files
    for role in plugins.ROLES:
        assert set(m.get(role, ())) <= files, (name, role)
    for point, references in m.get("hooks", {}).items():
        assert point in plugins.HOOKS, (name, point)
        for reference in references:
            assert callable(plugins._resolve(name, reference)), (name, reference)
    assert set(m.get("requires", ())) <= set(plugins.BUILTIN) - {name}
    source = (PLUGIN_ROOT / name / "__init__.py").read_text(encoding="utf-8")
    assert not re.search(r"^\s*(import|from)\s", source, re.M), "A plugin __init__ holds only its manifest"


def test_every_plugin_package_is_registered():
    packages = {p.parent.name for p in PLUGIN_ROOT.glob("*/__init__.py")}
    assert packages == set(plugins.BUILTIN)


def test_plugin_operations_and_actions_do_not_shadow_core_ones():
    from vixl.operations import OPERATION_TYPES

    owned = plugins.operation_types()
    assert len(OPERATION_TYPES) == len(set(OPERATION_TYPES))
    assert set(owned) <= set(OPERATION_TYPES)
    from vixl.workflows import ACTIONS

    assert set(plugins.workflow_actions()) <= set(ACTIONS)


def test_every_operation_and_action_is_reachable_through_its_plugin():
    from vixl.schema import operation_schema

    schema_types = {v["properties"]["type"]["const"] for v in operation_schema()["properties"]["operations"]["items"]["oneOf"]}
    assert set(plugins.operation_types()) <= schema_types
    from vixl.workflows import describe

    described = describe()["actions"]
    for action in plugins.workflow_actions():
        assert described[action]["summary"], action


def test_docs_table_matches_the_registry():
    text = (SRC.parent / "docs" / "reference" / "plugins.md").read_text(encoding="utf-8")
    assert plugins.markdown_table() in text


def test_a_plugin_operation_runs_through_the_registry():
    from vixl import Project

    p = Project(400, 300)
    p.apply([{"type": "comic-layout", "name": "page", "panels": [{"caption": "One"}, {"caption": "Two"}]}])
    assert p.layer("page/panel-1") and p.layer("page/panel-2")
