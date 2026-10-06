"""The agent-facing surface: check findings and a preview from one apply call (#180), one guidance registry that
vixl_guide, vixl_resource_get and vixl_capabilities share (#236), starting points that lead to rigs, loops and
irregular placement (#236, #185, #216, #256), and a tool list without duplicates (#255)."""

import asyncio
import base64
import json

import pytest
from fastapi.testclient import TestClient

from vixl import Project, briefs
from vixl.capabilities import TOPICS, lookup
from vixl.checks import apply_reviewed
from vixl.errors import VixlError
from vixl.guidance import GUIDANCE
from vixl.interfaces import create_app, mcp_server

TEXT = {"type": "text", "size": 40, "color": "black"}


def contents(server, name, arguments):
    async def run():
        result = await server.call_tool(name, arguments)
        return result[0] if isinstance(result, tuple) else result

    return asyncio.run(run())


def call(server, name, arguments):
    return json.loads(contents(server, name, arguments)[0].text)


@pytest.fixture
def server(tmp_path):
    server = mcp_server(workspace=tmp_path)
    call(server, "vixl_document_create", {"path": "a.vixl", "width": 400, "height": 300, "background": "white"})
    call(server, "vixl_operations_apply", {"operations": [
        {**TEXT, "text": "Title", "name": "a", "x": 10, "y": 20},
        {"type": "shape", "shape": "rectangle", "name": "deco", "x": 380, "y": 250, "width": 60, "height": 60, "fill": "#123456"}]})
    return server


# ---------------------------------------------------------------------------------------------
# #180: one call applies, checks and previews


def test_apply_with_check_and_preview_matches_the_separate_calls(server, tmp_path):
    content = contents(server, "vixl_operations_apply", {
        "operations": [{**TEXT, "text": "Cut off by the edge", "name": "new", "x": 300, "y": 200}],
        "check": True, "preview": True})
    result = json.loads(content[0].text)
    assert result["success"] and result["document"] == "a.vixl"
    image = content[1]
    assert image.mimeType == "image/png"
    separate = contents(server, "vixl_render_preview", {"max_width": 512, "max_height": 512, "max_bytes": 524288})
    assert base64.b64decode(image.data) == base64.b64decode(separate[0].data)

    full = call(server, "vixl_check", {})
    check = result["check"]
    assert {k: check[k] for k in ("passed", "errors", "warnings", "info")} == {k: full[k] for k in ("passed", "errors", "warnings", "info")}
    # The new layer's findings and every 'fix' finding, but not the review-only crop of the untouched deco.
    kept = [(i["check"], i["layers"]) for i in check["issues"]]
    expected = [(i["check"], i["layers"]) for i in full["issues"] if i["action"] == "fix" or "new" in i["layers"]]
    assert sorted(map(str, kept)) == sorted(map(str, expected))
    assert ("bounds", ["new"]) in kept
    assert ("bounds", ["deco"]) in [(i["check"], i["layers"]) for i in full["issues"]] and ("bounds", ["deco"]) not in kept
    assert check["omitted"] == len(full["issues"]) - len(kept)
    assert all(check["issues"][i]["action"] == action for action, ids in check["by_action"].items() for i in ids)


def test_apply_check_names_dry_run_and_bad_options(server, tmp_path):
    before = (tmp_path / "a.vixl").read_bytes()
    content = contents(server, "vixl_operations_apply", {
        "operations": [{**TEXT, "text": "Off", "name": "new", "x": 380, "y": 10}], "dry_run": True,
        "check": ["bounds"], "preview": {"max_width": 200}})
    result = json.loads(content[0].text)
    assert result["dry_run"] and result["check"]["checked"]["checks"] == ["bounds"]
    assert [i["layers"] for i in result["check"]["issues"]] == [["new"]]
    assert len(content) == 2 and (tmp_path / "a.vixl").read_bytes() == before  # The candidate was checked, not saved.
    for options in ({"check": ["nonsense"]}, {"preview": {"zoom": 2}}):
        with pytest.raises(Exception, match="check|preview"):
            contents(server, "vixl_operations_apply", {"operations": [{**TEXT, "text": "x", "name": "z"}], **options})
    assert "z" not in {x["name"] for x in Project.load(tmp_path / "a.vixl").state["layers"]}
    plain = contents(server, "vixl_operations_apply", {"operations": [{**TEXT, "text": "y", "name": "y"}]})
    assert len(plain) == 1 and "check" not in json.loads(plain[0].text)


def test_apply_review_is_skipped_when_the_edit_used_up_the_budget():
    project = Project(200, 100, "white")
    result, image = apply_reviewed(project, [{**TEXT, "text": "Hi", "name": "hi"}], check=True, preview=True, budget=-1)
    assert image is None and "check" not in result and "check and preview" in result["review_skipped"]
    assert project.layer("hi")  # The edit itself still applied.


def test_apply_preview_replays_without_applying_twice(server, tmp_path):
    arguments = {"operations": [{**TEXT, "text": "Once", "name": "once"}], "preview": True, "request_id": "r-1"}
    assert len(contents(server, "vixl_operations_apply", arguments)) == 2
    again = json.loads(contents(server, "vixl_operations_apply", arguments)[0].text)
    assert again["replayed"]
    assert [x["name"] for x in Project.load(tmp_path / "a.vixl").state["layers"]].count("once") == 1


def test_a_slow_apply_with_preview_becomes_a_job_whose_result_says_where_the_image_went(tmp_path, monkeypatch):
    import time

    from mcp.shared.memory import create_connected_server_and_client_session

    from vixl.interfaces import Session

    original = Session.apply_reviewed

    def slow(self, *args, **kwargs):
        time.sleep(0.6)
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Session, "apply_reviewed", slow)
    server = mcp_server(workspace=tmp_path)
    server.vixl_runtime.inline_seconds = 0.2
    server.vixl_runtime.session.create("a.vixl", 200, 100)

    async def main():
        async with create_connected_server_and_client_session(server._mcp_server) as client:
            async def ask(name, **arguments):
                result = await client.call_tool(name, arguments)
                return json.loads(result.content[0].text)

            pointer = await ask("vixl_operations_apply", operations=[{**TEXT, "text": "Hi", "name": "hi"}], preview=True)
            assert pointer["status"] == "running"
            return await ask("vixl_job", action="result", id=pointer["job"], wait=10)

    done = asyncio.run(main())
    assert done["result"]["success"] and "vixl_render_preview" in done["note"]


def test_rest_and_cli_apply_return_findings_and_a_preview(tmp_path):
    from vixl.cli import main

    path = tmp_path / "rest.vixl"
    Project(200, 100, "white").save(path)
    body = TestClient(create_app(path)).post("/operations", json={
        "operations": [{**TEXT, "text": "Long text off the edge", "name": "t"}], "check": ["bounds"], "preview": True}).json()
    assert body["check"]["issues"][0]["check"] == "bounds"
    assert base64.b64decode(body["preview_base64"]).startswith(b"\x89PNG")
    ops = tmp_path / "ops.json"
    ops.write_text(json.dumps([{"type": "shape", "shape": "rectangle", "name": "box", "width": 50, "height": 50, "fill": "red"}]))
    assert main(["--project", str(path), "apply", str(ops), "--check", "bounds", "--preview", str(tmp_path / "p.png")]) == 0
    assert (tmp_path / "p.png").read_bytes().startswith(b"\x89PNG") and Project.load(path).layer("box")


# ---------------------------------------------------------------------------------------------
# #236 / #255: one guidance registry


def test_every_guidance_name_resolves_through_guide_resources_and_capabilities(tmp_path):
    from vixl.resources import catalog, get

    assert set(GUIDANCE) <= set(catalog("guidance"))
    named = {name for _, names in TOPICS.values() for name in names}
    named |= {name for entry in briefs.KINDS.values() for name in entry.get("guidance", [])}
    assert named <= set(GUIDANCE), named - set(GUIDANCE)
    for name in named:
        found = briefs.guide(name)
        # A guidance named like a kind of work (logo) comes inline with that kind.
        assert (found["principles"] if name in briefs.KINDS else found["text"]) == get("guidance", name) == GUIDANCE[name]
    assert set(lookup("animation")["guidance"]) >= {"looping-motion", "natural-motion", "character-rigging"}
    assert "docs/" not in json.dumps(lookup("animation"))
    assert set(briefs.guide()["guidance"]) >= set(GUIDANCE)
    assert briefs.guide("natural-motion")["kinds"] == ["animation"]
    # User additions join the same registry.
    from vixl.resources import register

    register("guidance", "house-style", "Two colors and wide margins.", workspace=tmp_path)
    assert briefs.guide("house-style", workspace=tmp_path)["text"] == "Two colors and wide margins."


def test_mcp_guide_returns_guidance_and_capabilities_is_its_own_tool(server):
    assert "anticipation" in call(server, "vixl_guide", {"brief": "natural-motion"})["text"]
    assert call(server, "vixl_resource_get", {"kind": "guidance", "name": "imperfection"})["value"] == GUIDANCE["imperfection"]
    # The old vixl_guide('capabilities …') alias duplicated vixl_capabilities; it is gone and points there.
    with pytest.raises(VixlError, match=r"vixl_capabilities\(topic='animation'\)"):
        briefs.guide("capabilities animation")
    from vixl.finishing_cli import standalone

    cli = standalone("capabilities", ["animation"])  # vixl capabilities animation: the CLI's own command now
    assert "fields" in cli["operations"]["motion"] and "looping-motion" in cli["guidance"]
    assert standalone("guide", ["looping-motion"])["guidance"] == "looping-motion"
    assert "loop" in " ".join(call(server, "vixl_capabilities", {"topic": "loop"})["topics"] + ["loop"])
    assert call(server, "vixl_capabilities", {"topic": "loop"})["topics"] == ["animation"]


def test_tool_list_has_no_duplicate_text_tool_and_names_the_split_tools(server):
    tools = {tool.name: tool for tool in asyncio.run(server.list_tools())}
    assert "vixl_text_add" not in tools
    assert "Keyframed motion: vixl_timeline_inspect" in tools["vixl_animation_inspect"].description
    assert "Saved frames" in tools["vixl_timeline_inspect"].description
    assert "vixl_check" in tools["vixl_validate"].description
    assert {"check", "preview"} <= set(tools["vixl_operations_apply"].inputSchema["properties"])


# ---------------------------------------------------------------------------------------------
# #236, #185, #216, #256: the starting points


def test_animation_and_character_guides_lead_to_rigs_loops_and_checks():
    animation = briefs.guide("animation")
    text = json.dumps(animation)
    assert "direction" not in animation  # No poster palette/layout-apply block for art briefs.
    for term in ("motion", "pivot", "stagger", "period", "frame 0", "vixl_check", "vixl_timeline_preview", "character-cycle",
                 "middle and last"):
        assert term in text, term
    assert {"motion", "pivot", "character-cycle", "keyframes"} <= set(animation["operations"])
    assert "looping-motion" in animation["guidance"]
    assert any(op["type"] == "motion" for op in animation["example"])
    assert not any(op["type"] == "animate-preset" for op in animation["example"])
    character = briefs.guide("character")
    text = json.dumps(character)
    assert "direction" not in character and "ellipses and rounded shapes" not in text
    for term in ("pivot", "group", "joint", "character-rig", "irregular"):
        assert term in text, term
    assert {"pivot", "group", "irregular"} <= {op["type"] for op in character["example"]}
    assert briefs.guide("a looping typing indicator with bouncing dots")["matched"] == "animation"
    assert "direction" in briefs.guide("poster")  # Text compositions keep their rolled direction.


def test_looping_example_returns_to_its_first_frame():
    from vixl.timeline import project_at

    project = Project(800, 600, "#ffffff")
    project.apply(briefs.KINDS["animation"]["example"])
    duration = project.state["timeline"]["duration"]
    assert duration == 2000
    first, last = project_at(project, 0).render(), project_at(project, duration).render()
    assert first.tobytes() == last.tobytes()


def test_pattern_guide_scatters_instead_of_making_a_grid():
    pattern = briefs.guide("pattern")
    assert "repeat" not in {op["type"] for op in pattern["example"]}
    assert any(rule["rule"] == "scatter" for op in pattern["example"] if op["type"] == "organic"
               for part in op["parts"] for rule in part["rules"])
    assert "irregular" in json.dumps(pattern["approach"]) and "imperfection" in pattern["guidance"]


def test_irregularity_is_recommended_where_it_belongs():
    from vixl.style_catalog import STYLES

    for kind in ("character", "scene", "pattern", "hand-drawing"):
        assert "irregular" in KIND_OPERATIONS(kind), kind
    assert "tear" in KIND_OPERATIONS("scene")
    for style in ("hand-drawn", "kawaii", "grunge-zine"):
        assert "irregular" in STYLES[style]["imagery"]["advice"] or "tear" in STYLES[style]["imagery"]["advice"], style
    for kind in ("logo", "app-icon", "diagram"):
        assert "irregular" not in KIND_OPERATIONS(kind), kind
    text = GUIDANCE["imperfection"]
    assert "Do not use it on logos" in text and "subtle" in text and "tear" in text


def KIND_OPERATIONS(kind):
    entry = briefs.KINDS[kind]
    return set(entry["operations"]) | {op["type"] for op in entry["example"]}
