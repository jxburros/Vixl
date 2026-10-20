from pathlib import Path
import re
import subprocess
import sys
import tomllib

ROOT = Path(__file__).resolve().parent.parent


def _dependencies():
    config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return config["project"]["dependencies"]


def test_pydantic_is_declared_with_the_floor_mcp_requires():
    """The MCP code imports pydantic directly, so it is a direct dependency; mcp 1.21 needs pydantic 2.11."""
    entry = next((item for item in _dependencies() if re.match(r"pydantic\b", item)), None)
    assert entry, "pydantic is imported by the MCP modules but not declared in pyproject.toml"
    assert re.search(r">=\s*2\.11\b", entry) and "<3" in entry, entry


def test_shapely_stays_required_but_imports_lazily():
    """Core vector operations need shapely, so it is a required dependency (docs/reference/releases.md,
    "Dependencies"). It must stay out of start-up: importing the package and rendering a plain document must not
    load it."""
    assert any(re.match(r"shapely\b", item) for item in _dependencies())
    code = (
        "import sys\n"
        "sys.modules['shapely'] = None\n"
        "import vixl.cli, vixl.interfaces, vixl.project\n"
        "from vixl import Project\n"
        "project = Project(64, 48)\n"
        "project.apply([{'type': 'rect', 'x': 2, 'y': 2, 'width': 30, 'height': 20, 'fill': '#ff0000'}])\n"
        "project.render()\n"
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=ROOT,
                            env={**__import__("os").environ, "PYTHONPATH": str(ROOT / "src")})
    assert result.returncode == 0, result.stderr
