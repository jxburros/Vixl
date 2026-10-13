"""The MCP tool surface is a ratchet: it may shrink, never grow, without a deliberate baseline update.

What every agent pays for in context is the tools/list payload and the server instructions. The baseline
(tests/mcp_surface_baseline.json) records them per server and per tool; `python -m scripts.mcp_surface --update`
lowers it after a reduction and refuses to raise it unless --allow-growth is passed.
"""

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import mcp_surface  # noqa: E402

from vixl.mcp_tools import TOOL_CAP, TOOLS  # noqa: E402


def test_the_surface_does_not_grow_beyond_the_baseline():
    baseline = json.loads(mcp_surface.BASELINE.read_text(encoding="utf-8"))
    current = mcp_surface.measure()
    assert not mcp_surface.growth(current, baseline), (
        "The MCP surface grew; shrink it, or run python -m scripts.mcp_surface --update --allow-growth "
        f"deliberately: {mcp_surface.growth(current, baseline)}")
    assert not mcp_surface.over_cap(current, TOOL_CAP)
    assert baseline["per_tool_cap"] == TOOL_CAP


def test_the_default_server_is_seven_tools_in_a_small_budget():
    current = mcp_surface.measure()["default"]
    assert tuple(sorted(current["tools"])) == tuple(sorted(TOOLS))
    assert current["total_chars"] <= 12000 and current["instructions_chars"] <= 1000


def test_growth_is_refused_without_the_flag(tmp_path, monkeypatch):
    baseline = tmp_path / "baseline.json"
    current = mcp_surface.measure()
    smaller = json.loads(json.dumps(current))
    smaller["default"]["tools"]["vixl_apply"] -= 1
    smaller["default"]["total_chars"] -= 1
    baseline.write_text(json.dumps({"per_tool_cap": TOOL_CAP, "servers": smaller}))
    monkeypatch.setattr(mcp_surface, "BASELINE", baseline)
    monkeypatch.setattr(mcp_surface, "measure", lambda: current)
    assert mcp_surface.main([]) == 1
    assert mcp_surface.main(["--update"]) == 1
    assert json.loads(baseline.read_text())["servers"] == smaller
    assert mcp_surface.main(["--update", "--allow-growth"]) == 0
    assert json.loads(baseline.read_text())["servers"] == current
    assert mcp_surface.main(["--update"]) == 0  # no growth now: lowering or keeping is always allowed
