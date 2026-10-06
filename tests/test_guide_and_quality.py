"""Issue #79: a guide for non-poster work, image-slot next steps, palette role reasoning and check actions;
issue #88: the start-here recipe."""

import asyncio
import json
from pathlib import Path

import pytest

from vixl import Project, VixlError
from vixl import briefs
from vixl.layouts import LAYOUTS, describe, next_steps
from vixl.looks import LOOKS
from vixl.operations import OPERATION_TYPES
from vixl.render import EFFECTS
from vixl.sizes import catalog as size_catalog
from vixl.style_catalog import STYLES

ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------------------------
# #79 (1) and #88: the guide and the start-here recipe


def test_guide_without_a_brief_gives_the_recipe_and_every_kind():
    result = briefs.guide()
    assert len(result["start_here"]) == 5
    assert "layout" in result["start_here"][1] and "vixl_fonts" in result["start_here"][2] and "vixl_check" in result["start_here"][4]
    assert {"logo", "app-icon", "character", "scene", "pattern", "mandala", "diagram", "social-card", "slides"} <= set(result["kinds"])
    assert "not default to a poster" in result["tip"]


@pytest.mark.parametrize("brief, kind", [
    ("a mascot for a coffee brand", "character"),
    ("mandala with 12 petals", "mandala"),
    ("an icon for my notes app", "app-icon"),
    ("sunset over mountains illustration", "scene"),
    ("seamless dots pattern", "pattern"),
    ("make me a wordmark and logo", "logo"),
    ("instagram story about our sale", "social-card"),
    ("quarterly pitch deck", "slides"),
    ("infographic with statistics", "diagram"),
    ("8-bit sprite", "pixel-art"),
    ("registration form", "form"),
])
def test_free_text_briefs_find_their_kind(brief, kind):
    result = briefs.guide(brief)
    assert result["matched"] == kind
    assert result["operations"] and result["example"] and result["start_here"]
    assert all(isinstance(a, str) for a in result["alternatives"])


def test_guide_errors_name_the_kinds_and_special_briefs_work():
    with pytest.raises(VixlError) as caught:
        briefs.guide("zzzz qqqq")
    assert caught.value.code == "no_match" and "logo" in caught.value.details["allowed"]
    assert briefs.guide("character")["kind"] == "character"
    assert briefs.guide("start here")["start_here"]
    index = briefs.guide("operations")["operations"]
    listed = {name for group, items in index.items() if not group.startswith("Effects") for name in items}
    assert listed == set(OPERATION_TYPES) - set(EFFECTS) - {n for n in OPERATION_TYPES if n in EFFECTS}
    assert all(summary for group, items in index.items() if not group.startswith("Effects") for summary in items.values())
    assert {"radial-repeat", "look", "style-set"} <= listed
    assert set(index["Effects (also {type: <name>})"]) == set(EFFECTS)


def test_every_kind_references_real_operations_layouts_looks_styles_and_sizes():
    sizes = {s["name"] for s in size_catalog()["sizes"]}
    for kind, entry in briefs.KINDS.items():
        assert entry["summary"] and entry["approach"] and entry["keywords"] and entry["example"], kind
        assert set(entry["operations"]) <= set(OPERATION_TYPES), (kind, set(entry["operations"]) - set(OPERATION_TYPES))
        assert set(entry["layouts"]) <= set(LAYOUTS), kind
        assert set(entry["looks"]) <= set(LOOKS), kind
        assert set(entry["styles"]) <= set(STYLES), kind
        assert set(entry["sizes"]) <= sizes, (kind, set(entry["sizes"]) - sizes)
        for op in entry["example"]:
            assert op["type"] in OPERATION_TYPES, (kind, op["type"])


@pytest.mark.parametrize("kind", sorted(briefs.KINDS))
def test_every_example_in_the_guide_runs(kind):
    project = Project(800, 600, "#ffffff")
    ops = briefs.KINDS[kind]["example"]
    result = project.apply(ops, detail="compact")
    assert result["success"]
    image = project.render()
    assert image.getbbox() is not None


def test_non_poster_examples_render_distinct_pictures():
    """The point of the guide: ten requests for 'cool things' are not ten layouts."""
    pictures = set()
    for kind in ("character", "scene", "pattern", "mandala", "pixel-art", "app-icon"):
        project = Project(800, 600, "#ffffff")
        project.apply(briefs.KINDS[kind]["example"])
        pictures.add(hash(project.render().tobytes()))
    assert len(pictures) == 6


def test_mcp_exposes_the_guide_and_the_start_here_instructions(tmp_path):
    from vixl.interfaces import Session
    from vixl.mcp_tools import build_server

    server = build_server(Session(workspace=tmp_path))
    names = {tool.name for tool in asyncio.run(server.list_tools())}
    assert {"vixl_guide", "vixl_styles"} <= names
    text = server.instructions
    assert text.startswith("Edit layered image documents") and "START HERE" in text
    start = text.index("START HERE")
    assert text.index("vixl_layouts_list", start) < text.index("vixl_fonts", start) < text.index("vixl_check", start)
    assert "vixl_guide" in text[start:start + 400] and "not freehand shapes" in text

    async def call(tool, **arguments):
        result = await server.call_tool(tool, arguments)
        content = result[0] if isinstance(result, tuple) else result
        return json.loads(content[0].text)

    assert asyncio.run(call("vixl_guide", brief="mascot"))["matched"] == "character"
    assert "start_here" in asyncio.run(call("vixl_guide"))
    assert set(asyncio.run(call("vixl_guide", brief="looks"))["looks"]) == set(LOOKS)
    compact = build_server(Session(workspace=tmp_path), tools="compact", schema="slim")
    assert "vixl_guide" not in {tool.name for tool in asyncio.run(compact.list_tools())}
    assert "vixl_guide(brief)" not in compact.instructions and "START HERE" in compact.instructions


def test_skill_and_docs_carry_the_start_here_recipe():
    skill = (ROOT / "skills/vixl/SKILL.md").read_text()
    assert "Start here" in skill and "vixl_guide" in skill and "layout-apply" in skill
    assert skill.index("layout-apply") < skill.index("vixl_font_pair") < skill.index("vixl_check")
    for path in ("docs/styles.md", "docs/looks.md"):
        assert (ROOT / path).exists()


# ---------------------------------------------------------------------------------------------
# #79 (3): layouts with image slots explain how to fill them


def test_image_slot_lists_every_way_to_fill_it():
    slot = describe("product-card")["slots"]["image"]
    assert {option["option"] for option in slot["fill_with"]} == {"import", "resource", "draw", "ai"}
    assert "next_steps" in slot["hint"] and "AI" in slot["hint"]
    assert "fill_with" not in describe("product-card")["slots"]["title"]


def test_layout_apply_returns_next_steps_for_unfilled_image_slots():
    project = Project(1080, 1350, "#ffffff")
    result = project.apply({"type": "layout-apply", "name": "product-card", "title": "Desk lamp", "body": "Warm light.",
                            "caption": "$49", "cta": "Shop", "label": "New", "seed": 4}, detail="compact")
    assert "image" in result["unfilled_slots"]
    steps = result["next_steps"]
    image = next(step for step in steps if step["slot"] == "image")
    assert image["layer"] in {layer["name"] for layer in project.state["layers"]}
    x, y, w, h = image["bounds"]
    assert w > 100 and h > 100 and image["aspect_ratio"] == pytest.approx(w / h, abs=0.01)
    options = {option["option"]: option["how"] for option in image["options"]}
    assert "vixl_import_image" in options["import"] and "replace-contents" in options["import"]
    assert "shape" in options["draw"] and "organic" in options["draw"] and "vixl_ai_generate" in options["ai"]
    # Filling every slot leaves nothing to do.
    full = Project(1080, 1350, "#ffffff")
    from PIL import Image
    from vixl.assets import add_image

    asset = add_image(full, Image.new("RGBA", (400, 400), "#336699"))
    done = full.apply({"type": "layout-apply", "name": "product-card", "title": "Desk lamp", "body": "Warm light.", "caption": "$49",
                       "cta": "Shop", "label": "New", "image": asset, "seed": 4}, detail="compact")
    assert not done["unfilled_slots"] and "next_steps" not in done
    assert next_steps(full) == []


def test_text_slots_get_a_reapply_hint_and_the_documented_fill_works():
    project = Project(1080, 1350, "#ffffff")
    result = project.apply({"type": "layout-apply", "name": "product-card", "title": "Desk lamp", "seed": 4}, detail="compact")
    text = next(step for step in result["next_steps"] if step["slot"] != "image")
    assert "replace=true" in text["how"] and "seed=4" in text["how"]
    # The 'import' route from the steps: replace-contents on the placeholder frame with an embedded asset.
    from PIL import Image
    from vixl.assets import add_image

    asset = add_image(project, Image.new("RGBA", (300, 300), "#cc3333"))
    frame = next(step["layer"] for step in result["next_steps"] if step["slot"] == "image")
    project.apply({"type": "replace-contents", "target": frame, "asset": asset})
    blanks = [issue for issue in project.check(checks=["blanks"])["issues"] if issue["check"] == "blanks" and "image" in issue["message"]]
    assert not blanks


# ---------------------------------------------------------------------------------------------
# #79 (4): palette roles are explained and can keep the order given

ORDER = ["#0f172a", "#1e293b", "#38bdf8", "#f472b6"]


def layout_op(**extra):
    return {"type": "layout-apply", "name": "hero-statement", "title": "Hello", "subtitle": "World", "label": "New", "cta": "Go",
            "seed": 3, **extra}


def test_layout_apply_echoes_the_role_mapping_and_why_the_palette_was_rearranged():
    project = Project(1080, 1080, "#ffffff")
    result = project.apply(layout_op(palette=ORDER), detail="compact")
    layout = result["layout"]
    roles = {entry["role"]: entry for entry in layout["roles"]}
    assert set(roles) == {"background", "surface", "ink", "muted", "accent", "accent-text", "on-accent"}
    assert layout["mode"] == "light" and layout["mode_source"] == "inherited from the canvas background"
    # The dark first color was demoted to ink; the lightest became the ground: the surprise the report describes.
    assert roles["background"]["source"] != "palette[0]" and roles["ink"]["source"] == "palette[0]"
    assert "because mode is light" in roles["background"]["reason"]
    assert any("keep_order" in note for note in layout["notes"])


def test_keep_order_honours_background_surface_accents():
    project = Project(1080, 1080, "#ffffff")
    result = project.apply(layout_op(palette=ORDER, keep_order=True), detail="compact")
    layout = result["layout"]
    roles = {entry["role"]: entry for entry in layout["roles"]}
    assert roles["background"]["color"] == "#0f172a" and roles["background"]["source"] == "palette[0]"
    assert roles["surface"]["color"] == "#1e293b" and roles["surface"]["source"] == "palette[1]"
    assert roles["accent"]["color"] == "#38bdf8" and roles["accent"]["source"] == "palette[2]"
    assert layout["mode"] == "dark" and layout["mode_source"] == "taken from the first palette color"
    from vixl.colors import contrast_ratio, parse

    assert contrast_ratio(parse(roles["ink"]["color"])[:3], parse(roles["background"]["color"])[:3]) >= 7
    assert project.state["swatches"]["background"] == "#0f172a"
    assert not any("keep_order" in note for note in layout.get("notes", []))


def test_explicit_colors_still_win_and_are_reported_as_explicit():
    project = Project(1080, 1080, "#ffffff")
    result = project.apply(layout_op(palette="ocean", colors={"background": "#101010", "accent": "#ff00aa"}), detail="compact")
    roles = {entry["role"]: entry for entry in result["layout"]["roles"]}
    assert roles["background"]["source"] == "explicit" and roles["accent"]["color"] == "#ff00aa"


def test_palette_apply_reports_roles_keeps_order_and_takes_explicit_maps():
    project = Project(800, 600, "#ffffff")
    project.apply({"type": "palette-define", "name": "mine", "colors": ORDER})
    kept = project.apply({"type": "palette-apply", "name": "mine", "keep_order": True}, detail="compact")["changes"]["palette_roles"]
    mapping = {entry["role"]: entry for entry in kept["roles"]}
    assert kept["keep_order"] and mapping["background"]["color"] == "#0f172a" and mapping["accent"]["source"] == "palette[2]"
    assert kept["mode"] == "dark" and "first palette color" in kept["mode_source"]
    assert project.state["swatches"]["background"] == "#0f172a" and project.state["swatches"]["surface"] == "#1e293b"
    auto = project.apply({"type": "palette-apply", "name": "mine"}, detail="compact")["changes"]["palette_roles"]
    assert not auto["keep_order"] and auto["mode_source"] and any("keep_order" in note for note in auto["notes"])
    explicit = project.apply({"type": "palette-apply", "name": "mine", "roles": {"background": 1, "accent": 3, "ink": "#ffffff"}},
                             detail="compact")["changes"]["palette_roles"]
    got = {entry["role"]: entry for entry in explicit["roles"]}
    assert got["background"]["color"] == "#1e293b" and got["background"]["source"] == "explicit"
    assert got["accent"]["color"] == "#f472b6" and got["ink"]["color"] == "#ffffff"
    assert project.state["swatches"]["background"] == "#1e293b"
    for bad, text in (({"nope": 0}, "Unknown role"), ({"background": 9}, "out of range"), ({"background": "not-a-color"}, "color")):
        with pytest.raises(VixlError) as caught:
            project.apply({"type": "palette-apply", "name": "mine", "roles": bad})
        assert text in str(caught.value)
    # roles: false still means no role swatches at all.
    bare = Project(100, 100)
    bare.apply({"type": "palette-define", "name": "p", "colors": ORDER})
    bare.apply({"type": "palette-apply", "name": "p", "roles": False})
    assert "background" not in bare.state["swatches"] and "palette_roles" not in bare.state


def test_palette_generate_never_assigns_roles_and_reports_its_swatches():
    """The surprise in the report came from palette-apply / layout-apply; palette-generate only adds numbered swatches."""
    project = Project(100, 100)
    result = project.apply({"type": "palette-generate", "name": "brand", "color": "#2563eb"}, detail="compact")
    assert set(result["changes"]["swatches"]) == {f"brand-{n}" for n in (50, 100, 200, 300, 400, 500, 600, 700, 800, 900, 950)}
    assert "background" not in project.state["swatches"] and "palette_roles" not in project.state


# ---------------------------------------------------------------------------------------------
# #79 (5): findings grouped by action, intentional crops marked


def crop_doc():
    project = Project(800, 600, "#ffffff")
    project.apply([
        {"type": "text", "name": "small", "text": "tiny print", "size": 8, "color": "#111111", "x": 40, "y": 40},
        {"type": "shape", "shape": "ellipse", "name": "sun", "x": -80, "y": 380, "width": 300, "height": 300, "fill": "#f97316"},
        {"type": "shape", "shape": "ellipse", "name": "moon", "x": 600, "y": 450, "width": 300, "height": 300, "fill": "#94a3b8"},
        {"type": "text", "name": "word", "text": "BLEED", "size": 220, "color": "#111111", "x": -60, "y": 100},
    ])
    return project


def issue_for(result, layer):
    return next(i for i in result["issues"] if layer in i["layers"] and i["check"] == "bounds")


def test_unmarked_edge_crops_are_review_and_say_how_to_mark_them():
    result = crop_doc().check(checks=["bounds", "legibility"])
    sun = issue_for(result, "sun")
    assert sun["severity"] == "warning" and sun["action"] == "review" and "allow_crop" in sun["message"]
    word = issue_for(result, "word")
    assert word["severity"] == "error" and word["action"] == "fix"
    small = next(i for i in result["issues"] if i["check"] == "legibility")
    assert small["action"] == "fix"


def test_marked_crops_become_informational_and_the_report_groups_by_action():
    project = crop_doc()
    project.apply({"type": "layer-intent", "target": "sun", "allow_crop": True})
    project.apply({"type": "layer-intent", "target": "word", "allow_crop": True})
    result = project.check(checks=["bounds", "legibility"])
    sun = issue_for(result, "sun")
    assert sun["severity"] == "info" and sun["action"] == "informational" and sun["intentional"] is True
    word = issue_for(result, "word")
    assert word["severity"] == "info" and word["action"] == "informational"
    moon = issue_for(result, "moon")  # not marked
    assert moon["action"] == "review"
    by_action = result["by_action"]
    assert set(by_action) == {"fix", "review", "informational"}
    issues = result["issues"]
    assert {issues[i]["check"] for i in by_action["fix"]} == {"legibility"}
    assert [issues[i]["layers"][0] for i in by_action["informational"]] == ["sun", "word"]
    assert [issues[i]["layers"][0] for i in by_action["review"]] == ["moon"]
    assert (result["errors"], result["warnings"], result["info"]) == (0, 2, 2) and result["passed"]
    assert sorted(i for ids in by_action.values() for i in ids) == list(range(len(issues)))


def test_decoration_and_group_intent_count_as_marked():
    project = crop_doc()
    project.apply({"type": "layer-intent", "target": "sun", "role": "decoration"})
    project.apply({"type": "group", "name": "stage", "targets": ["moon"]})
    project.apply({"type": "layer-intent", "target": "stage", "allow_crop": True})
    result = project.check(checks=["bounds"])
    assert issue_for(result, "sun")["action"] == "informational"
    assert [i for i in result["issues"] if "moon" in i["layers"]][0]["action"] == "informational"
    # Marking text decoration does not hide an error: text is only excused by allow_crop.
    project.apply({"type": "layer-intent", "target": "word", "role": "decoration"})
    assert issue_for(project.check(checks=["bounds"]), "word")["severity"] == "error"
    project.apply({"type": "layer-intent", "target": "sun", "allow_crop": False, "role": "content"})
    assert issue_for(project.check(checks=["bounds"]), "sun")["action"] == "review"
    with pytest.raises(VixlError):
        project.apply({"type": "layer-intent", "target": "sun", "allow_crop": "yes"})


def test_entirely_outside_stays_an_error_and_layouts_mark_their_own_bleeds():
    project = Project(400, 300, "#ffffff")
    project.apply([{"type": "shape", "shape": "rectangle", "name": "gone", "x": 900, "y": 10, "width": 50, "height": 50, "fill": "red"}])
    project.apply({"type": "layer-intent", "target": "gone", "allow_crop": True})
    assert issue_for(project.check(checks=["bounds"]), "gone")["severity"] == "error"
    for seed in (1, 2, 5):
        layout = Project(1080, 1350, "#ffffff")
        layout.apply({"type": "layout-apply", "name": "hero-statement", "title": "T", "subtitle": "S", "label": "L", "cta": "C",
                      "accent": "block", "seed": seed})
        result = layout.check(checks=["bounds"])
        assert all(i["action"] == "informational" for i in result["issues"] if i["check"] == "bounds"), result["issues"]
        assert result["warnings"] == 0


def test_actions_cover_suites_decks_and_the_cli(tmp_path, capsys, monkeypatch):
    project = crop_doc()
    project.apply({"type": "layer-intent", "target": "sun", "allow_crop": True})
    project.apply({"type": "suite-set", "name": "s", "suite": {"version": 1, "rules": [
        {"id": "d", "kind": "design", "options": {"checks": ["bounds"], "targets": ["sun"]}}]}})
    # An intentional crop no longer holds a suite in needs_review.
    assert project.check_suite("s")["status"] == "passed"
    deck = Project(400, 300, "#ffffff")
    deck.apply({"type": "page", "action": "add", "name": "one"})
    deck.apply({"type": "shape", "shape": "ellipse", "name": "blob", "x": -50, "y": 0, "width": 200, "height": 200, "fill": "red"})
    report = deck.check(checks=["deck"])
    assert set(report["by_action"]) == {"fix", "review", "informational"} and "info" in report
    from vixl.cli import main

    monkeypatch.chdir(tmp_path)
    project.save(tmp_path / "c.vixl")
    capsys.readouterr()
    main(["-p", "c.vixl", "layer-intent", "moon", "--allow-crop"])
    capsys.readouterr()
    main(["-p", "c.vixl", "check", "--checks", "bounds"])
    out = json.loads(capsys.readouterr().out)
    assert [i["action"] for i in out["issues"] if i["layers"] == ["moon"]] == ["informational"]
