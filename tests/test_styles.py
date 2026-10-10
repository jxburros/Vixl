"""Style tags: the curated catalog, the style-set tag and the premade checks (issue #87)."""

import asyncio
import json
from pathlib import Path

import pytest

import vixl
from vixl import Project, VixlError
from vixl.fonts import import_font
from vixl import styles, typefaces
from vixl.effect_workflows import SUITES  # noqa: F401  (keeps import order stable with other suites)
from vixl.layouts import LAYOUTS
from vixl.looks import LOOKS
from vixl.render import EFFECTS
from vixl.resources import PALETTES
from vixl.style_catalog import STYLES

FONT = Path(vixl.__file__).parent / "data" / "DejaVuSans.ttf"
STATUSES = {"passed", "failed", "skipped", "disabled"}


@pytest.fixture(scope="module")
def fonts(tmp_path_factory):
    """Distinct font files (the bundled font plus padding) so each registered name is its own typeface."""
    folder = tmp_path_factory.mktemp("fonts")
    paths = {}
    for i, name in enumerate(("inter-400", "inter-700", "playfair-display-700", "space-mono-400", "cinzel-700",
                              "archivo-black-900", "caveat-400")):
        path = folder / f"{name}.ttf"
        path.write_bytes(FONT.read_bytes() + b"\0" * (i + 1))
        paths[name] = path
    return paths


def doc(fonts, width=1080, height=1350, background="#ffffff"):
    project = Project(width, height, background)
    for name, path in fonts.items():
        import_font(project, path, name)
    return project


def statuses(project, style):
    report = project.check(checks=["style"], style=style)["style"]
    return {rule["id"].split("/", 1)[1]: rule["status"] for rule in report["rules"]}


def test_catalog_has_a_curated_set_of_complete_styles():
    assert 20 <= len(STYLES) <= 30
    required = {"title", "summary", "era", "keywords", "best_for", "principles", "palettes", "palette_names", "type",
                "layout", "imagery", "do", "dont", "checks"}
    seen = set()
    for name, entry in STYLES.items():
        assert name == name.lower() and " " not in name
        assert required <= set(entry), f"{name}: {required - set(entry)}"
        assert len(entry["summary"]) > 60 and len(entry["principles"]) >= 3, name
        assert len(entry["keywords"]) >= 4 and entry["best_for"], name
        assert len(entry["do"]) >= 3 and len(entry["dont"]) >= 2, name
        assert len(entry["palettes"]) >= 1, name
        for palette in entry["palettes"]:
            assert 2 <= len(palette["swatches"]) <= 8 and palette["note"], name
            for swatch in palette["swatches"]:
                from vixl.render import color

                assert len(color(swatch)) == 4
        assert set(entry["palette_names"]) <= set(PALETTES), name
        guidance = entry["type"]
        assert guidance["categories"] and guidance["families"] and guidance["pairings"] and guidance["weights"], name
        for family in guidance["families"]:
            assert typefaces.find_font(family), f"{name}: {family!r} is not in the font catalog"
        known = {p["name"] for p in typefaces.pairings()}
        assert set(guidance["pairings"]) <= known, f"{name}: {set(guidance['pairings']) - known}"
        assert set(guidance["categories"]) <= {e["category"] for e in typefaces.fonts()}, name
        assert entry["layout"]["grid"] and entry["layout"]["alignment"] and entry["layout"]["negative_space"], name
        assert set(entry["layout"]["layouts"]) <= set(LAYOUTS), name
        assert set(entry["imagery"]["looks"]) <= set(LOOKS), name
        assert set(entry["imagery"]["effects"]) <= set(EFFECTS), name
        assert entry["imagery"]["advice"] and entry["imagery"]["avoid"], name
        assert len(entry["checks"]) >= 3, f"{name}: at least three premade checks"
        ids = [rule["id"] for rule in entry["checks"]]
        assert len(ids) == len(set(ids)), f"{name}: duplicate rule ids"
        for rule in entry["checks"]:
            assert rule["kind"] in styles.RULES, f"{name}: {rule['kind']}"
            assert rule["severity"] in styles.SEVERITIES and rule["summary"] and rule["fix"]
            assert isinstance(rule["params"], dict)
        seen |= set(entry["keywords"])
    wanted = {"swiss", "brutalist", "neo-brutalist", "minimalist", "scandinavian", "bauhaus", "art-deco", "mid-century-modern",
              "memphis", "retro-futurism", "vaporwave", "y2k", "editorial", "corporate-flat", "material", "glassmorphism",
              "grunge-zine", "japanese-minimal", "vintage-letterpress", "hand-drawn", "maximalist", "cyberpunk", "kawaii",
              "line-art", "risograph", "data-viz"}
    assert wanted <= set(STYLES)


def test_every_rule_kind_is_used_by_some_style():
    used = {rule["kind"] for entry in STYLES.values() for rule in entry["checks"]}
    assert set(styles.RULES) == used


def test_listing_search_and_get():
    everything = styles.listing()
    assert everything["count"] == len(STYLES)
    names = {row["name"] for row in styles.listing("poster")["styles"]}
    assert {"swiss", "brutalist"} <= names
    assert [row["name"] for row in styles.listing("glass blur frosted")["styles"]] == ["glassmorphism"]
    full = styles.describe("Art Deco")
    assert full["name"] == "art-deco" and full["checks"][0]["id"].startswith("art-deco/")
    assert styles.describe("japanese minimal")["name"] == "japanese-minimal"
    with pytest.raises(VixlError) as caught:
        styles.describe("swis")
    assert caught.value.code == "unknown_style" and "swiss" in caught.value.details["suggestions"]


# Every rule evaluates, on empty, text-only and rich documents


def rich(fonts):
    project = doc(fonts)
    project.apply([
        {"type": "gradient", "name": "sky", "start": "#1e3a8a", "end": "#fdba74"},
        {"type": "text", "name": "headline", "text": "A bold statement here", "size": 120, "color": "#ffffff", "x": 80, "y": 100,
         "font": "playfair-display-700", "align": "center"},
        {"type": "text", "name": "copy", "text": "Supporting copy sits lower on the page.", "size": 30, "color": "#e2e8f0", "x": 80,
         "y": 500, "font": "inter-400"},
        {"type": "shape", "shape": "rounded-rectangle", "name": "card", "x": 80, "y": 640, "width": 400, "height": 240, "radius": 20,
         "fill": "#ffffff", "stroke": "#111111", "stroke_width": 3},
        {"type": "shape", "shape": "star", "name": "spark", "x": 600, "y": 700, "width": 160, "height": 160, "fill": "#facc15"},
        {"type": "rotate", "target": "spark", "value": 17},
        {"type": "look", "target": "spark", "look": "glow"},
        {"type": "look", "target": "card", "look": "hard-shadow"},
        {"type": "look", "target": "sky", "look": "grain"},
    ])
    return project


@pytest.mark.parametrize("name", sorted(STYLES))
def test_every_rule_of_every_style_evaluates(fonts, name):
    cases = {
        "empty": doc(fonts),
        "text only": doc(fonts),
        "rich": rich(fonts),
    }
    cases["text only"].apply({"type": "text", "name": "t", "text": "Hello world", "size": 60, "color": "#000000", "x": 50, "y": 50})
    for label, project in cases.items():
        report = project.check(checks=["style"], style=name)["style"]
        assert len(report["rules"]) == len(STYLES[name]["checks"]), (name, label)
        for rule in report["rules"]:
            assert rule["status"] in STATUSES, (name, label, rule)
            assert isinstance(rule["measured"], dict) and "detail" in rule
        assert sum(report["summary"].values()) == len(report["rules"])


# A compliant and a non-compliant document per style


def swiss_ok(fonts):
    project = doc(fonts)
    project.apply([
        {"type": "text", "name": "title", "text": "Grid systems", "size": 140, "color": "#111111", "x": 90, "y": 120,
         "font": "inter-700", "align": "left"},
        {"type": "text", "name": "body", "text": "Objective layout on a grid.", "size": 36, "color": "#111111", "x": 90, "y": 360,
         "font": "inter-400", "align": "left"},
        {"type": "shape", "shape": "rectangle", "name": "bar", "x": 90, "y": 500, "width": 300, "height": 24, "fill": "#e30613"},
        {"type": "text", "name": "caption", "text": "Spring 2026", "size": 24, "color": "#111111", "x": 90, "y": 1200,
         "font": "inter-400", "align": "left"},
    ])
    return project


def swiss_bad(fonts):
    project = doc(fonts)
    project.apply([
        {"type": "text", "name": "title", "text": "Grid systems", "size": 80, "color": "#111111", "x": 90, "y": 120,
         "font": "playfair-display-700", "align": "center"},
        {"type": "text", "name": "body", "text": "Objective layout on a grid.", "size": 40, "color": "#2255cc", "x": 300, "y": 360,
         "font": "space-mono-400", "align": "right"},
        {"type": "text", "name": "note", "text": "A third face", "size": 30, "color": "#111111", "x": 90, "y": 900,
         "font": "inter-400", "align": "left"},
        {"type": "shape", "shape": "rounded-rectangle", "name": "bar", "x": 133, "y": 500, "width": 300, "height": 24,
         "fill": "#e30613", "radius": 8},
        {"type": "shape", "shape": "star", "name": "star", "x": 640, "y": 700, "width": 200, "height": 200, "fill": "#00aa55"},
        {"type": "rotate", "target": "star", "value": 20},
        {"type": "layer-style", "target": "star", "name": "drop-shadow", "settings": {"blur": 12, "dx": 4, "dy": 4}},
    ])
    return project


def test_swiss_compliant_and_non_compliant_documents(fonts):
    good = statuses(swiss_ok(fonts), "swiss")
    assert set(good.values()) == {"passed"}, good
    bad = statuses(swiss_bad(fonts), "swiss")
    assert bad == {"max-typefaces": "failed", "text-align": "failed", "edge-alignment": "failed", "tilt": "failed",
                   "shadows": "failed", "hue-count": "failed"}
    result = swiss_bad(fonts).check(checks=["style"], style="swiss")
    messages = [issue["message"] for issue in result["issues"] if issue["check"] == "style"]
    assert any("3 typefaces" in m for m in messages) and any("drop shadow" in m for m in messages)
    assert result["errors"] == 0 and result["warnings"] == 6 and result["passed"]
    assert all(issue["action"] == "review" and issue["rule"].startswith("swiss/") for issue in result["issues"])


def test_brutalist_checks_weight_contrast_corners_shadows_and_gradients(fonts):
    good = doc(fonts, background="#ffffff")
    good.apply([
        {"type": "text", "name": "head", "text": "NO MERCY", "size": 130, "color": "#000000", "x": 60, "y": 100,
         "font": "archivo-black-900"},
        {"type": "shape", "shape": "rectangle", "name": "slab", "x": 60, "y": 600, "width": 900, "height": 300, "fill": "#000000"},
        {"type": "look", "target": "slab", "look": "hard-shadow"},
    ])
    assert set(statuses(good, "brutalist").values()) == {"passed"}, statuses(good, "brutalist")
    bad = doc(fonts, background="#cccccc")
    bad.apply([
        {"type": "text", "name": "head", "text": "gentle", "size": 80, "color": "#999999", "x": 60, "y": 100, "font": "inter-400"},
        {"type": "shape", "shape": "rounded-rectangle", "name": "pill", "x": 60, "y": 600, "width": 600, "height": 200,
         "radius": 40, "fill": "#bbbbbb"},
        {"type": "look", "target": "pill", "look": "soft-shadow"},
        {"type": "gradient", "name": "glow-bg", "start": "#cccccc", "end": "#dddddd"},
    ])
    result = statuses(bad, "brutalist")
    assert result == {"min-weight": "failed", "high-contrast": "failed", "no-rounded-corners": "failed",
                      "shadows": "failed", "gradients": "failed"}


def test_minimalist_negative_space_colors_typefaces_words_and_margins(fonts):
    good = doc(fonts, background="#fafaf8")
    good.apply({"type": "text", "name": "line", "text": "Less, but better", "size": 64, "color": "#1a1a1a", "x": 160, "y": 600,
                "font": "inter-400"})
    assert set(statuses(good, "minimalist").values()) == {"passed"}, statuses(good, "minimalist")
    bad = doc(fonts, background="#fafaf8")
    bad.apply([
        {"type": "shape", "shape": "rectangle", "name": "a", "x": 0, "y": 0, "width": 1080, "height": 900, "fill": "#ff0000"},
        {"type": "shape", "shape": "rectangle", "name": "b", "x": 20, "y": 920, "width": 500, "height": 400, "fill": "#00aa00"},
        {"type": "shape", "shape": "rectangle", "name": "c", "x": 560, "y": 920, "width": 500, "height": 400, "fill": "#0000ff"},
        {"type": "shape", "shape": "rectangle", "name": "d", "x": 300, "y": 300, "width": 300, "height": 300, "fill": "#ffaa00"},
        {"type": "text", "name": "words", "text": " ".join(["word"] * 60), "size": 20, "color": "#333333", "x": 10, "y": 10,
         "font": "playfair-display-700"},
        {"type": "text", "name": "more", "text": "and more", "size": 20, "color": "#333333", "x": 10, "y": 60, "font": "inter-400"},
    ])
    got = statuses(bad, "minimalist")
    assert got["min-negative-space"] == "failed" and got["max-colors"] == "failed" and got["max-typefaces"] == "failed"
    assert got["max-words"] == "failed" and got["margins"] == "failed"


def test_art_deco_symmetry_and_centered_text(fonts):
    good = doc(fonts, background="#0b0b0d")
    good.apply([
        {"type": "shape", "shape": "rectangle", "name": "left", "x": 200, "y": 300, "width": 120, "height": 600, "fill": "#d4af37"},
        {"type": "shape", "shape": "rectangle", "name": "right", "x": 760, "y": 300, "width": 120, "height": 600, "fill": "#d4af37"},
        {"type": "text", "name": "title", "text": "GRAND", "size": 120, "color": "#f5e6b3", "x": "center", "y": 100,
         "font": "cinzel-700", "align": "center"},
    ])
    got = statuses(good, "art-deco")
    assert got["symmetry"] == "passed" and got["text-align"] == "passed" and got["tilt"] == "passed", got
    bad = doc(fonts, background="#0b0b0d")
    bad.apply([
        {"type": "shape", "shape": "rectangle", "name": "left", "x": 100, "y": 300, "width": 120, "height": 600, "fill": "#d4af37"},
        {"type": "text", "name": "title", "text": "GRAND", "size": 120, "color": "#f5e6b3", "x": 700, "y": 100,
         "font": "cinzel-700", "align": "left"},
    ])
    got = statuses(bad, "art-deco")
    assert got["symmetry"] == "failed" and got["text-align"] == "failed"


def test_art_deco_sunburst_and_centred_type_pass_their_own_checks(fonts):  # #355
    poster = doc(fonts, background="#0b0b0d")
    poster.apply([
        {"type": "shape", "shape": "rectangle", "name": "ray", "x": 534, "y": 260, "width": 12, "height": 300, "fill": "#d4af37"},
        {"type": "radial-repeat", "target": "ray", "count": 32, "cx": 540, "cy": 560, "name": "sunburst"},
        {"type": "text", "name": "title", "text": "THE GRAND BALLROOM", "size": 84, "color": "#f5e6b3", "x": "center",
         "y": 920, "font": "cinzel-700", "align": "center"},
        {"type": "text", "name": "date", "text": "Saturday the ninth of June", "size": 40, "color": "#d4af37", "x": "center",
         "y": 1080, "font": "cinzel-700", "align": "center"},
    ])
    report = poster.check(checks=["style"], style="art-deco")["style"]
    got = {rule["id"].split("/", 1)[1]: rule for rule in report["rules"]}
    assert got["symmetry"]["status"] == "passed", got["symmetry"]
    assert got["tilt"]["status"] == "passed", got["tilt"]
    # A tilted headline still counts against "upright".
    poster.apply({"type": "rotate", "target": "title", "value": 20})
    poster.apply({"type": "rotate", "target": "date", "value": -15})
    assert statuses(poster, "art-deco")["tilt"] == "failed"


def test_single_weight_black_display_faces_count_as_heavy(fonts, tmp_path):  # #355
    project = doc(fonts)
    path = tmp_path / "archivo-black-400.ttf"
    path.write_bytes(FONT.read_bytes() + b"\0" * 40)
    import_font(project, path, "archivo-black-400")
    project.apply({"type": "text", "name": "head", "text": "NO MERCY", "size": 130, "color": "#000000", "x": 60, "y": 100,
                   "font": "archivo-black-400"})
    rule = {r["id"].split("/", 1)[1]: r for r in project.check(checks=["style"], style="brutalist")["style"]["rules"]}
    assert rule["min-weight"]["status"] == "passed", rule["min-weight"]


def test_line_art_wants_outlined_shapes_with_one_stroke_weight(fonts):
    good = doc(fonts, background="#fbfaf7")
    good.apply([
        {"type": "shape", "shape": "ellipse", "name": "head", "x": 300, "y": 300, "width": 300, "height": 300, "fill": "transparent",
         "stroke": "#1c1c1c", "stroke_width": 4},
        {"type": "shape", "shape": "rectangle", "name": "body", "x": 350, "y": 620, "width": 200, "height": 300,
         "fill": "transparent", "stroke": "#1c1c1c", "stroke_width": 4},
    ])
    assert set(statuses(good, "line-art").values()) == {"passed"}, statuses(good, "line-art")
    bad = doc(fonts, background="#fbfaf7")
    bad.apply([
        {"type": "shape", "shape": "ellipse", "name": "head", "x": 300, "y": 300, "width": 300, "height": 300, "fill": "#222222",
         "stroke": "#1c1c1c", "stroke_width": 2},
        {"type": "shape", "shape": "rectangle", "name": "body", "x": 350, "y": 620, "width": 200, "height": 300,
         "fill": "transparent", "stroke": "#1c1c1c", "stroke_width": 9},
        {"type": "look", "target": "head", "look": "soft-shadow"},
    ])
    got = statuses(bad, "line-art")
    assert got["stroke-style"] == "failed" and got["uniform-stroke"] == "failed" and got["shadows"] == "failed"


def test_cyberpunk_wants_a_dark_ground_and_glow(fonts):
    good = doc(fonts, background="#0a0a1a")
    good.apply([
        {"type": "shape", "shape": "rectangle", "name": "neon", "x": 200, "y": 400, "width": 600, "height": 40, "fill": "#ff2bd6"},
        {"type": "look", "target": "neon", "look": "neon"},
        {"type": "text", "name": "t", "text": "NIGHT CITY", "size": 140, "color": "#00f0ff", "x": 100, "y": 700, "font": "space-mono-400"},
    ])
    assert set(statuses(good, "cyberpunk").values()) == {"passed"}, statuses(good, "cyberpunk")
    bad = doc(fonts, background="#f5f5f5")
    bad.apply({"type": "shape", "shape": "rectangle", "name": "plain", "x": 200, "y": 400, "width": 600, "height": 40, "fill": "#ff2bd6"})
    got = statuses(bad, "cyberpunk")
    assert got["dark-background"] == "failed" and got["glow"] == "failed"


def test_neo_brutalist_needs_hard_shadows_and_outlines(fonts):
    good = doc(fonts, background="#fffdf5")
    good.apply([
        {"type": "shape", "shape": "rounded-rectangle", "name": "card", "x": 100, "y": 200, "width": 600, "height": 400, "radius": 16,
         "fill": "#ffd23f", "stroke": "#111111", "stroke_width": 4},
        {"type": "look", "target": "card", "look": "hard-shadow"},
        {"type": "text", "name": "t", "text": "Ship it", "size": 120, "color": "#111111", "x": 120, "y": 700, "font": "archivo-black-900"},
    ])
    assert set(statuses(good, "neo-brutalist").values()) == {"passed"}, statuses(good, "neo-brutalist")
    bad = doc(fonts, background="#fffdf5")
    bad.apply([
        {"type": "shape", "shape": "rounded-rectangle", "name": "card", "x": 100, "y": 200, "width": 600, "height": 400, "radius": 16,
         "fill": "#ffd23f"},
        {"type": "look", "target": "card", "look": "soft-shadow"},
    ])
    got = statuses(bad, "neo-brutalist")
    assert got["shadows"] == "failed" and got["min-stroke-width"] == "failed"


def test_style_set_tags_validates_clears_and_persists(fonts, tmp_path):
    project = doc(fonts)
    result = project.apply({"type": "style-set", "style": "Swiss"}, detail="compact")
    assert project.state["style"] == {"names": ["swiss"]}
    assert result["changes"]["style"] == {"names": ["swiss"]}
    project.apply({"type": "style-set", "style": ["minimalist", "scandinavian"], "options": {"max-words": False}})
    assert project.state["style"]["names"] == ["minimalist", "scandinavian"]
    path = tmp_path / "tagged.vixl"
    project.save(path)
    assert Project.load(path).state["style"]["options"] == {"max-words": False}
    project.undo()
    assert project.state["style"] == {"names": ["swiss"]}
    project.apply({"type": "style-set", "style": None})
    assert "style" not in project.state
    for bad, text in (({"type": "style-set", "style": "swis"}, "did you mean 'swiss'"),
                      ({"type": "style-set", "style": "swiss", "options": {"nope": False}}, "Unknown rule"),
                      ({"type": "style-set", "style": "swiss", "options": {"max-typefaces": {"limit": 3}}}, "Unknown setting"),
                      ({"type": "style-set", "style": "swiss", "options": {"max-typefaces": {"severity": "fatal"}}}, "severity"),
                      ({"type": "style-set", "style": ["swiss", "bauhaus", "memphis", "y2k"]}, "up to 3")):
        with pytest.raises(VixlError) as caught:
            project.apply(bad)
        assert text in str(caught.value), (bad, str(caught.value))
    # A corrupted tag in an archive is rejected on load.
    project.apply({"type": "style-set", "style": "swiss"})
    project.state["style"] = {"names": ["nope"]}
    from vixl.validation import check_state

    with pytest.raises(VixlError):
        check_state(project, project.state)


def test_options_relax_or_tighten_rules(fonts):
    project = swiss_bad(fonts)
    project.apply({"type": "style-set", "style": "swiss", "options": {
        "max-typefaces": {"max": 3}, "tilt": False, "shadows": {"severity": "error"}, "hue-count": {"enabled": False}}})
    result = project.check(checks=["style"])
    report = {rule["id"]: rule for rule in result["style"]["rules"]}
    assert report["swiss/max-typefaces"]["status"] == "passed"
    assert report["swiss/tilt"]["status"] == "disabled" and report["swiss/hue-count"]["status"] == "disabled"
    assert report["swiss/shadows"]["status"] == "failed" and report["swiss/shadows"]["severity"] == "error"
    assert result["errors"] == 1 and not result["passed"]
    shadow = next(issue for issue in result["issues"] if issue["rule"] == "swiss/shadows")
    assert shadow["severity"] == "error" and shadow["action"] == "fix" and shadow["layers"] == ["star"]


def test_style_check_without_a_tag_and_with_an_override(fonts):
    project = swiss_bad(fonts)
    result = project.check(checks=["style"])
    assert result["style"]["rules"] == [] and "No style is set" in result["issues"][0]["message"]
    other = project.check(checks=["style"], style=["brutalist"])
    assert other["style"]["styles"] == ["brutalist"] and any(issue["rule"].startswith("brutalist/") for issue in other["issues"])
    # Style checks are opt-in: the default check set never evaluates the tag.
    project.apply({"type": "style-set", "style": "swiss"})
    assert "style" not in project.check()
    assert "style" in project.check(checks=["bounds", "style"])


def test_apply_stores_the_brief_and_palette_as_ordinary_operations(fonts):
    project = doc(fonts)
    ops = styles.apply_operations("art-deco", palette=True)
    assert [op["type"] for op in ops] == ["style-set", "guidance", "palette-define", "palette-apply"]
    project.apply(ops)
    assert project.state["style"]["names"] == ["art-deco"]
    assert "Art Deco" in project.state["design_guidance"]["style"]
    assert project.state["swatches"]["background"].lower() == "#0b0b0d"
    assert project.state["palette_roles"]["roles"][0]["role"] == "background"
    roles = styles.palette_roles(["#0b0b0d", "#d4af37", "#f5e6b3", "#1c1c21"])
    assert roles["background"] == "#0b0b0d" and roles["ink"] == "#f5e6b3" and roles["accent"] == "#d4af37"


def call(server, tool, **arguments):
    async def run():
        result = await server.call_tool(tool, arguments)
        content = result[0] if isinstance(result, tuple) else result
        return json.loads(content[0].text)

    return asyncio.run(run())


def test_mcp_vixl_styles_and_vixl_check(tmp_path, fonts):
    from vixl.interfaces import Session
    from vixl.mcp_tools import build_server

    server = build_server(Session(workspace=tmp_path))
    call(server, "vixl_document_create", path="d.vixl", width=800, height=600)
    listing = call(server, "vixl_styles", query="neon")
    assert "cyberpunk" in {row["name"] for row in listing["styles"]}
    full = call(server, "vixl_styles", action="get", name="swiss")
    assert full["checks"] and full["palettes"] and full["type"]["families"]
    applied = call(server, "vixl_styles", action="apply", name="swiss", palette=True)
    assert applied["success"]
    call(server, "vixl_operations_apply", operations=[
        {"type": "text", "text": "Hello", "name": "t", "size": 60, "color": "#111111", "x": 50, "y": 50, "align": "center"}])
    checked = call(server, "vixl_check", checks=["style"])
    assert checked["style"]["styles"] == ["swiss"]
    again = call(server, "vixl_styles", action="check")
    assert again["style"]["summary"] == checked["style"]["summary"]
    other = call(server, "vixl_check", checks=["style"], style="brutalist")
    assert other["style"]["styles"] == ["brutalist"]
    with pytest.raises(Exception) as caught:
        call(server, "vixl_styles", action="get", name="swis")
    assert "unknown_style" in str(caught.value)
    schema = call(server, "vixl_operation_schema", types=["style-set"])["style-set"]
    assert schema["description"] and schema["properties"]["style"]["description"]


def test_cli_styles_and_style_checks(tmp_path, capsys, monkeypatch):
    from vixl.cli import main

    monkeypatch.chdir(tmp_path)

    def run(*argv):
        capsys.readouterr()
        assert main(list(argv)) in (0, None)
        return json.loads(capsys.readouterr().out)

    assert run("styles", "list", "swiss")["styles"][0]["name"] == "swiss"
    assert run("styles", "show", "memphis")["name"] == "memphis"
    run("new", "400x300", "-o", "s.vixl")
    run("-p", "s.vixl", "style-set", "swiss")
    run("-p", "s.vixl", "text", "add", "Hello", "--name", "t", "--size", "40", "--color", "#111111")
    result = run("-p", "s.vixl", "check", "--checks", "style")
    assert result["style"]["styles"] == ["swiss"]
    result = run("-p", "s.vixl", "check", "--checks", "style", "--style", "brutalist")
    assert result["style"]["styles"] == ["brutalist"]
    assert run("-p", "s.vixl", "styles", "check")["style"]["styles"] == ["swiss"]
    assert run("-p", "s.vixl", "styles", "apply", "minimalist")["success"]
    assert run("-p", "s.vixl", "inspect", "--json") is not None
