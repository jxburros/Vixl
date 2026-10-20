"""The finishing pass at the end of the agent loop (craft plan 3a): one craft checklist in the guidance registry,
reachable from vixl_reference (by name, as a guidance resource and through capabilities), and the loop text
that points at it."""

import asyncio
import json
import re
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
    order = ['checks=["composition"]', "Critique", "one vixl_apply batch", "region=[x, y, w, h]",
             "vixl_export"]
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
    assert call(server, "vixl_reference", {"topic": "craft"})["text"] == GUIDANCE["finishing"]
    assert call(server, "vixl_reference", {"topic": "guidance", "name": "finishing"})["value"] == GUIDANCE["finishing"]
    assert "finishing" in call(server, "vixl_reference", {"topic": "capabilities", "name": "testing"})["guidance"]


def test_start_here_ends_with_the_finishing_pass_and_keeps_finish_as_a_look():
    steps = briefs.START_HERE
    finish = next(step for step in steps if step.startswith("Finish:"))
    assert "look" in finish and "not the finishing pass" in finish
    last = steps[-1]
    assert last.startswith("Finishing pass after tests pass") and "vixl_reference('finishing')" in last
    order = ["vixl_check and the suites", 'checks=["composition"]', "critique", "one fix batch", "real-size look",
             "vixl_render(region=", "vixl_export"]
    assert [last.index(step) for step in order] == sorted(last.index(step) for step in order)
    assert briefs.guide("poster")["start_here"][-1] == last


def test_mcp_instructions_and_skill_describe_the_finishing_pass(tmp_path):
    # The short server instructions send agents to the start-here loop, which ends with the finishing pass.
    assert "vixl_reference()" in mcp_server(workspace=tmp_path).instructions
    loop = call(mcp_server(workspace=tmp_path), "vixl_reference", {})["start_here"]
    assert loop[-1].startswith("Finishing pass after tests pass")
    skill = (ROOT / "skills/vixl/SKILL.md").read_text(encoding="utf-8")
    start = skill.index("6. **Finishing pass, then export.**")
    section = skill[start:skill.index("## The core loop")]
    # SKILL.md links the checklist instead of repeating it: the registry is its only copy.
    assert "vixl_reference('finishing')" in section and "vixl guide finishing" in section
    assert "max_width=w, max_height=h" in section and 'vixl_check(profile="final")' in section
    for item in CHECKLIST:
        assert item not in skill, item
    # The full loop text (references/workflow.md) keeps the steps in order and also links the checklist.
    workflow = (ROOT / "skills/vixl/references/workflow.md").read_text(encoding="utf-8")
    start = workflow.index("6. **Finishing pass, then export**")
    section = workflow[start:workflow.index("## One call for a new piece")]
    assert "vixl_reference('finishing')" in section and "max_width=w, max_height=h" in section
    assert section.index("Check composition") < section.index("Critique") < section.index("Fix") \
        < section.index("Look at real size") < section.index("Export")


def checklist_items():
    """The first clause of each checklist line in the registry ("one focal point", "no dead band" ...)."""
    text = GUIDANCE["finishing"]
    body = text[text.index("Craft checklist:"):text.index("\n3) Fix")]
    return [re.split(r"[:;,]", line[2:])[0].strip() for line in body.splitlines() if line.startswith("- ")]


def test_no_doc_reproduces_the_finishing_checklist():
    items = checklist_items()
    assert len(items) >= 9 and "one focal point" in items
    # A doc may name an item or two in passing ("no dead band" is also a composition finding); more is a copy.
    # The implementation plan quotes issue text and is a record, not guidance.
    files = [ROOT / "README.md", *ROOT.glob("docs/**/*.md"), *ROOT.glob("skills/**/*.md")]
    copies = {}
    for path in files:
        if path.name == "implementation-plan.md":
            continue
        text = " ".join(path.read_text(encoding="utf-8").split())
        found = [item for item in items if item in text]
        if len(found) > 2:
            copies[str(path.relative_to(ROOT))] = found
    assert not copies, copies
