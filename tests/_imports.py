"""Static import graph of the ``vixl`` package, shared by the plugin-boundary and layering tests."""

import ast
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"


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
