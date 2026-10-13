"""The finishing pass at the end of the agent loop (craft plan 3a): one craft checklist in the guidance registry,
reachable from vixl_guide, vixl_resource_get and vixl_capabilities, and the loop text that points at it."""

import asyncio
import json
from pathlib import Path

from vixl import briefs
from vixl.capabilities import lookup
from vixl.guidance import GUIDANCE
from vixl.interfaces import mcp_server

ROOT = Path(__file__).resolve().parents[1]
CHECKLIST = ("one focal point", "accent colour is used once or twice", "no dead band", "one left edge per column",
             "the motif names the subject", "nothing reads as a placeholder")


def call(server, name, arguments):
    result = asyncio.run(server.call_tool(name, arguments))
    content = result[0] if isinstance(result, tuple) else result
    return json.loads(content[0].text)


def test_the_craft_checklist_lives_in_the_finishing_guidance():
    text = GUIDANCE["finishing"]
    for item in CHECKLIST:
        assert item in text, item
    # The loop after the checks pass, in order.
    order = ["checks=['composition']", "Critique", "one vixl_operations_apply batch", "region=[x, y, w, h]",
             "vixl_export_file"]
    assert [text.index(step) for step in order] == sorted(text.index(step) for step in order)
    assert "max_width=w, max_height=h" in text
    # No other guidance entry carries a second copy of the checklist.
    assert [name for name, other in GUIDANCE.items() if "one left edge per column" in other] == ["finishing"]


def test_finishing_guidance_resolves_by_name_alias_resource_and_capabilities(tmp_path):
    from vixl.resources import get

    assert briefs.guide("finishing")["text"] == get("guidance", "finishing") == GUIDANCE["finishing"]
    for alias in ("craft", "craft checklist", "critique", "finishing pass", "polish"):
        assert briefs.guide(alias)["guidance"] == "finishing"
    assert "finishing" in briefs.guide()["guidance"]
    assert "finishing" in lookup("testing")["guidance"] and "finishing" in lookup("critique")["guidance"]
    assert {"poster", "social-card", "slides"} <= set(briefs.guide("finishing")["kinds"])
    assert "finishing" in briefs.guide("poster")["guidance"]
    server = mcp_server(workspace=tmp_path)
    assert call(server, "vixl_guide", {"brief": "craft"})["text"] == GUIDANCE["finishing"]
    assert call(server, "vixl_resource_get", {"kind": "guidance", "name": "finishing"})["value"] == GUIDANCE["finishing"]
    assert "finishing" in call(server, "vixl_capabilities", {"topic": "testing"})["guidance"]


def test_start_here_ends_with_the_finishing_pass_and_keeps_finish_as_a_look():
    steps = briefs.START_HERE
    finish = next(step for step in steps if step.startswith("Finish:"))
    assert "look" in finish and "not the finishing pass" in finish
    last = steps[-1]
    assert last.startswith("Finishing pass after tests pass") and "vixl_guide('finishing')" in last
    order = ["vixl_check and the suites", "checks=['composition']", "critique", "one fix batch", "real-size look",
             "vixl_render_preview(region=", "vixl_export_file"]
    assert [last.index(step) for step in order] == sorted(last.index(step) for step in order)
    assert briefs.guide("poster")["start_here"][-1] == last


def test_mcp_instructions_and_skill_describe_the_finishing_pass(tmp_path):
    text = mcp_server(workspace=tmp_path).instructions
    start = text.index("6) finishing pass")
    assert text.index("vixl_check(checks=['composition'])", start) < text.index("a short critique", start) \
        < text.index("one fix batch", start) < text.index("vixl_render_preview", start) < text.index("vixl_export_file", start)
    skill = (ROOT / "skills/vixl/SKILL.md").read_text(encoding="utf-8")
    start = skill.index("6. **Finishing pass, then export**")
    section = skill[start:skill.index("## Tests: why, when and how")]
    assert 'vixl_guide("finishing")' in section and "max_width=w, max_height=h" in section
    assert section.index("Check composition") < section.index("Critique") < section.index("Fix") \
        < section.index("Look at real size") < section.index("Export")
    # SKILL.md names the checklist; its items are the ones the registry holds.
    for item in ("one focal point", "no dead band", "one left edge per column", "the motif names the subject",
                 "nothing reads as a placeholder"):
        assert item in section and item in GUIDANCE["finishing"]
