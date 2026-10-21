"""Static types (#633): the modules under strict mypy only grow, and their annotated functions never drop.

``typecheck_baseline.json`` records each strict module and how many of its functions declare a return
type. Add a module to ``[tool.mypy] files`` in pyproject.toml (and its count here) once it checks clean; raise a
count when you annotate more. CI runs mypy itself (the ``typecheck`` job); this test runs it too when installed."""

import ast
import json
from pathlib import Path
import subprocess
import sys
import tomllib

import pytest

ROOT = Path(__file__).resolve().parents[1]
BASELINE = json.loads(Path(__file__).with_name("typecheck_baseline.json").read_text(encoding="utf-8"))["files"]


def strict_files():
    return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["tool"]["mypy"]["files"]


def annotated(path):
    tree = ast.parse((ROOT / path).read_text(encoding="utf-8"))
    return sum(isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.returns is not None
               for node in ast.walk(tree))


def test_strict_modules_only_grow():
    missing = sorted(set(BASELINE) - set(strict_files()))
    assert not missing, f"Modules left strict type checking: {missing}"


def test_annotated_functions_never_drop():
    dropped = {path: (annotated(path), count) for path, count in BASELINE.items() if annotated(path) < count}
    assert not dropped, f"Fewer annotated functions than recorded (now, before): {dropped}"


def test_mypy_passes():
    pytest.importorskip("mypy")
    result = subprocess.run([sys.executable, "-m", "mypy"], cwd=ROOT, capture_output=True, text=True, timeout=600)
    assert result.returncode == 0, result.stdout + result.stderr
