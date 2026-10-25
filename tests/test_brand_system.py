"""Brand system: font roles with any name, text stages, palette extras, presets, compliance rules and
brand validation (#436 phase 1, #406, #555)."""

import base64
import hashlib
import io
import json
from pathlib import Path

import pytest
from fontTools.ttLib import TTFont

from vixl import Project, VixlError
from vixl.brand import for_project, load, report

FONT = (Path(__file__).parents[1] / "src/vixl/data/DejaVuSans.ttf").read_bytes()
PALETTE = {"background": "#ffffff", "surface": "#eeeeee", "ink": "#111111", "muted": "#444444",
           "accent": "#0044aa", "accent-text": "#0044aa", "on-accent": "#ffffff"}


def renamed(family):
    """DejaVu Sans under another family name: distinct bytes, so each role gets its own embedded face."""
    font = TTFont(io.BytesIO(FONT))
    for record in font["name"].names:
        if record.nameID in (1, 4, 16):
            record.string = family
    out = io.BytesIO()
    font.save(out)
    return out.getvalue()


def spec(family):
    return {"name": family.lower(), "data_base64": base64.b64encode(renamed(family)).decode()}


def write(workspace, kit):
    (workspace / "brand.json").write_text(json.dumps(kit))
    return kit


def document(workspace, width=800, height=800):
    p = Project(width, height)
    p._workspace = workspace
    return p


def asset_of(p, name):
    return p.state["fonts"][name]


def register(p, family, role=None):
    data = renamed(family)
    asset = f"fonts/{hashlib.sha256(data).hexdigest()}.ttf"
    p.assets[asset] = data
    p.apply({"type": "font-register", "name": family.lower(), "asset": asset, **({"role": role} if role else {})})


# --- font roles and text stages (#406, #436 item 1) ------------------------------------------------------


def test_text_stages_follow_heading_and_body_and_accept_their_own_face():
    p = Project(1000, 1000)
    register(p, "Heady", "heading")
    register(p, "Bodo", "body")
    p.apply([{"type": "text", "text": "plain", "name": "plain"},
             {"type": "text", "text": "Big", "size": 200, "name": "big"},
             {"type": "text", "text": "note", "stage": "label", "name": "label"},
             {"type": "text", "text": "Title", "role": "h1", "name": "title"}])
    heading, body = asset_of(p, "heady"), asset_of(p, "bodo")
    assert p.layer("plain")["font"] == body and p.layer("plain")["font_role"] == "body"
    # From the title step up, plain text takes a heading stage (B2).
    assert p.layer("big")["font"] == heading and p.layer("big")["font_role"] in ("h2", "h1", "display")
    assert p.layer("label")["font"] == body and p.layer("label")["text"] == "NOTE"
    title = p.layer("title")
    assert title["font"] == heading and title["font_role"] == "h1"
    assert title["size"] > p.layer("plain")["size"] and title["line_height"] == 1.1
    # Registering a face for one stage moves only the text on that stage.
    register(p, "Shout", "h1")
    assert p.layer("title")["font"] == asset_of(p, "shout")
    assert p.layer("big")["font"] in (heading, asset_of(p, "shout"))
    assert p.layer("plain")["font"] == body
    # text-set can move a layer to another stage.
    p.apply({"type": "text-set", "target": "plain", "stage": "h2"})
    assert p.layer("plain")["font"] == heading and p.layer("plain")["font_role"] == "h2"
    p.apply({"type": "text", "target": "label", "stage": "caption"})
    assert p.layer("label")["font_role"] == "caption"


def test_any_role_name_registers_and_unknown_stage_is_an_error():
    p = Project(600, 600)
    register(p, "Hand", "hand")
    p.apply({"type": "text", "text": "dear diary", "font": "hand", "name": "note"})
    assert p.layer("note")["font"] == asset_of(p, "hand") and p.layer("note")["font_role"] == "hand"
    with pytest.raises(VixlError):
        p.apply({"type": "text", "text": "x", "stage": "h7"})
    with pytest.raises(VixlError, match="role"):
        p.apply({"type": "font-register", "name": "hand", "role": "Not A Role"})


def test_markdown_headings_use_the_h_stages():
    p = Project(800, 800)
    register(p, "Heady", "heading")
    register(p, "Bodo", "body")
    p.apply({"type": "rich-text", "name": "story", "markdown": "# Big news\nBody copy", "width": 600, "size": 90})
    # Rich text is running copy: body face at any size, headings on the h stages.
    assert p.layer("story")["font"] == asset_of(p, "bodo")
    spans = p.layer("story")["rich"]["spans"]
    heading = next(span for span in spans if span["text"] == "Big news")
    assert heading["font"] == asset_of(p, "heady") and "bold" not in heading
    assert all("font" not in span for span in spans if "Body copy" in span["text"])
    p.apply({"type": "text-flow", "name": "flow", "markdown": "## Section\nwords and more words",
             "frames": [{"x": 0, "y": 0, "width": 400, "height": 400}]})
    flowed = [layer for layer in p.state["layers"] if layer.get("rich") and layer["name"] != "story"]
    assert any(span.get("font") == asset_of(p, "heady") for layer in flowed for span in layer["rich"]["spans"])


def test_without_typography_stages_keep_the_proofing_font_quietly():
    p = Project(600, 600)
    result = p.apply({"type": "text", "text": "Title", "stage": "h1", "name": "t"}, detail="compact")
    assert p.layer("t")["font"] == "NotoSans-Regular.ttf" and "font_role" not in p.layer("t")
    assert not any("proofing" in w for w in result.get("warnings", []))


# --- brand.json: roles, stages, extras, presets (#436 phase 1) ------------------------------------------


def brand_kit(**extra):
    return {"name": "JXG", "palette": dict(PALETTE),
            "fonts": {"heading": spec("Anton"), "body": spec("Typer"), "hand": spec("Hand")}, **extra}


def test_brand_fonts_take_any_role_and_stages_map_onto_them(tmp_path):
    write(tmp_path, brand_kit(stages={"display": "hand", "label": {"font": "heading", "case": "upper"}}))
    p = document(tmp_path)
    p.apply({"type": "layout-apply", "name": "hero-statement", "title": "Launch", "unfilled": "omit"})
    assert p.state["typography"]["hand"] == "hand"
    assert p.state["type_stages"]["display"] == {"font": "hand"}
    headline = p.layer("headline")
    assert headline["font"] == asset_of(p, "hand") and headline["font_role"] == "display"
    p.apply([{"type": "text", "text": "dear diary", "font": "hand", "name": "note", "color": "@ink"},
             {"type": "text", "text": "tag", "stage": "label", "name": "tag", "color": "@ink"}])
    assert p.layer("tag")["font"] == asset_of(p, "anton")
    assert not [i for i in p.check(checks=["brand"])["issues"] if "Font" in i["message"]]


def test_palette_extra_colors_are_approved_and_become_swatches(tmp_path):
    write(tmp_path, brand_kit(palette={**PALETTE, "extra": {"wood": "#d2a465"}}))
    p = document(tmp_path)
    p.apply({"type": "layout-apply", "name": "hero-statement", "title": "Launch", "unfilled": "omit"})
    assert p.state["swatches"]["wood"] == "#d2a465"
    p.apply({"type": "shape", "shape": "rectangle", "name": "match", "width": 40, "height": 40, "fill": "@wood"})
    assert not [i for i in p.check(checks=["brand"])["issues"] if "palette" in i["message"]]
    p.apply({"type": "shape", "shape": "rectangle", "name": "off", "width": 40, "height": 40, "fill": "#ff00ff"})
    assert [i for i in p.check(checks=["brand"])["issues"] if i["layers"] == ["off"]]


def test_gradient_fill_stops_are_checked_against_the_palette(tmp_path):
    write(tmp_path, brand_kit(palette=PALETTE))
    p = document(tmp_path)
    p.apply({"type": "shape", "shape": "rectangle", "name": "ramp", "width": 40, "height": 40, "fill": "#0044aa",
             "fill_gradient": {"start": "#0044aa", "end": "#eeeeee"}})
    assert not [i for i in p.check(checks=["brand"])["issues"] if i["layers"] == ["ramp"]]
    p.apply({"type": "shape", "target": "ramp", "fill": "#0044aa", "fill_gradient": {"start": "#0044aa", "end": "#ff00ff"}})
    assert [i for i in p.check(checks=["brand"])["issues"] if i["layers"] == ["ramp"]]


def test_extra_color_max_fraction(tmp_path):
    write(tmp_path, {"palette": {**PALETTE, "extra": [{"color": "#d2a465", "max_fraction": 0.1}]}})
    p = document(tmp_path, 200, 200)
    p.apply([{"type": "solid", "color": "#ffffff"},
             {"type": "shape", "shape": "rectangle", "width": 200, "height": 100, "fill": "#d2a465"}])
    issues = [i for i in p.check(checks=["brand"])["issues"] if "extra-1" in i["message"]]
    assert issues and issues[0]["max_fraction"] == 0.1 and issues[0]["fraction"] == pytest.approx(0.5, abs=0.02)


def test_presets_extend_the_base_and_documents_select_one(tmp_path):
    flames = {"palette": {"accent": "#d2a465", "accent-text": "#8a5a1c"}, "fonts": {"body": spec("Anton")},
              "minimum_contrast": 3}
    write(tmp_path, brand_kit(presets={"flames": flames, "embers": {"extends": "flames", "palette": {"ink": "#222222"}}}))
    base = load(tmp_path)
    embers = load(tmp_path, "embers")
    assert base["palette"]["accent"] == "#0044aa" and "preset" not in base
    assert embers["palette"]["accent"] == "#d2a465" and embers["palette"]["ink"] == "#222222"
    assert embers["palette"]["background"] == "#ffffff" and embers["minimum_contrast"] == 3
    assert embers["fonts"]["heading"]["name"] == "anton" and embers["fonts"]["body"]["name"] == "anton"
    p = document(tmp_path)
    p.apply({"type": "brand-preset", "name": "flames"})
    assert p.state["brand_preset"] == "flames" and for_project(p)["palette"]["accent"] == "#d2a465"
    assert p.state["typography"]["body"] == "anton" and p.state["swatches"]["accent"] == "#d2a465"
    p.apply({"type": "layout-apply", "name": "hero-statement", "title": "Launch", "unfilled": "omit"})
    assert p.state["swatches"]["accent"] == "#d2a465"
    p.apply({"type": "brand-preset", "name": "none"})
    assert "brand_preset" not in p.state and for_project(p)["palette"]["accent"] == "#0044aa"
    with pytest.raises(VixlError, match="Unknown brand preset"):
        p.apply({"type": "brand-preset", "name": "missing"})


def test_preset_cycles_and_unknown_fields_are_rejected(tmp_path):
    write(tmp_path, {"presets": {"a": {"extends": "b"}, "b": {"extends": "a"}}})
    with pytest.raises(VixlError, match="cycle"):
        load(tmp_path)
    write(tmp_path, {"presets": {"a": {"presets": {}}}})
    with pytest.raises(VixlError, match="may set"):
        load(tmp_path)


def test_templates_may_name_a_role_or_stage_but_not_a_font_file(tmp_path):
    from vixl.resources import create_template, register as save

    write(tmp_path, brand_kit())
    template = {"width": 600, "height": 400, "operations": [
        {"type": "text", "name": "tag", "text": "small but heading", "size": 14, "font": "heading"},
        {"type": "text", "name": "aside", "text": "a note", "size": 30, "font": "hand"},
        {"type": "text", "name": "kicker", "text": "kicker", "stage": "label"},
        {"type": "text", "name": "big", "text": "Largest", "size": 60}]}
    save("templates", "roles", template, workspace=tmp_path)
    p = create_template("roles", workspace=tmp_path)
    assert p.layer("tag")["font"] == asset_of(p, "anton")
    assert p.layer("aside")["font"] == asset_of(p, "hand")
    assert p.layer("kicker")["text"] == "KICKER" and p.layer("kicker")["font"] == asset_of(p, "typer")
    assert p.layer("big")["font"] == asset_of(p, "anton")
    bad = {**template, "operations": [{"type": "text", "text": "x", "font": "../fonts/evil.ttf"}]}
    with pytest.raises(VixlError, match="font"):
        save("templates", "bad", bad, workspace=tmp_path)


# --- compliance rules (#555) -----------------------------------------------------------------------------


def test_allowed_fonts_name_the_layer_and_the_families(tmp_path):
    write(tmp_path, brand_kit(fonts={"heading": spec("Anton"), "body": spec("Typer"), "allowed": ["Anton", "Typer"]}))
    p = document(tmp_path)
    p.apply({"type": "layout-apply", "name": "hero-statement", "title": "Launch", "unfilled": "omit"})
    assert not [i for i in p.check(checks=["brand"])["issues"] if "brand font" in i["message"]]
    register(p, "Comic")
    p.apply({"type": "text", "text": "off brand", "font": "comic", "name": "rogue", "color": "@ink"})
    found = [i for i in p.check(checks=["brand"])["issues"] if "brand font" in i["message"]]
    assert len(found) == 1 and found[0]["layers"] == ["rogue"] and found[0]["severity"] == "error"
    assert found[0]["allowed"] == ["Anton", "Typer"] and "Comic" in found[0]["message"]
    assert found[0]["action"] == "fix"


def test_strict_colors_with_tolerance(tmp_path):
    write(tmp_path, {"palette": dict(PALETTE), "colors": {"strict": True, "tolerance": 6}})
    p = document(tmp_path, 200, 200)
    p.apply([{"type": "solid", "color": "#ffffff"},
             {"type": "shape", "shape": "rectangle", "name": "near", "width": 20, "height": 20, "fill": "#0346ae"},
             {"type": "shape", "shape": "rectangle", "name": "far", "width": 20, "height": 20, "fill": "#e01010"}])
    issues = [i for i in p.check(checks=["brand"])["issues"] if i["check"] == "brand"]
    assert [i["layers"] for i in issues] == [["far"]] and issues[0]["severity"] == "error"


def test_logo_clear_space_and_minimum_size(tmp_path):
    write(tmp_path, {"palette": dict(PALETTE), "logo": {"clear_space": 0.5, "min_size": "10mm"}})
    p = document(tmp_path, 1000, 1000)
    p.state["canvas"]["dpi"] = 300
    p.apply([{"type": "solid", "color": "#ffffff", "name": "paper"},
             {"type": "shape", "shape": "rectangle", "name": "logo", "x": 100, "y": 100, "width": 200, "height": 100,
              "fill": "#0044aa"},
             {"type": "text", "name": "crowd", "text": "too close", "x": 320, "y": 110, "size": 20, "color": "#111111"},
             {"type": "text", "name": "fine", "text": "far away", "x": 100, "y": 600, "size": 20, "color": "#111111"}])
    issues = [i for i in p.check(checks=["brand"])["issues"] if "logo" in i["message"].lower()]
    crowd = [i for i in issues if "crowd" in i["layers"]]
    assert len(crowd) == 1 and crowd[0]["severity"] == "error" and crowd[0]["required"] == 50
    assert crowd[0]["gap"] == pytest.approx(20, abs=1) and crowd[0]["action"] == "fix"
    assert not [i for i in issues if "fine" in i["layers"] or "paper" in i["layers"]]
    small = [i for i in issues if "minimum" in i["message"]]
    assert small and small[0]["minimum"] == pytest.approx(118.11, abs=0.1) and small[0]["measured"] == 100


def variant_document(tmp_path, ground):
    write(tmp_path, {"palette": {**PALETTE, "extra": {"brand-dark": "#102040"}},
                     "logo": {"variants": {"reversed": {"layers": "logo-rev*", "backgrounds": ["dark", "@brand-dark"]},
                                           "full": {"layers": ["logo-full"], "backgrounds": ["light"]}}}})
    p = document(tmp_path, 600, 400)
    p.apply([{"type": "solid", "color": ground, "name": "paper"},
             {"type": "shape", "shape": "rectangle", "name": "logo-rev-mark", "x": 40, "y": 40, "width": 120,
              "height": 60, "fill": "#ffffff"},
             {"type": "shape", "shape": "rectangle", "name": "panel", "x": 300, "y": 200, "width": 300, "height": 200,
              "fill": "#102040"},
             {"type": "shape", "shape": "rectangle", "name": "logo-rev-corner", "x": 400, "y": 260, "width": 120,
              "height": 60, "fill": "#ffffff"}])
    return p


def test_reversed_logo_on_light_background_is_a_fix(tmp_path):
    p = variant_document(tmp_path, "#ffffff")
    found = [i for i in p.check(checks=["brand"])["issues"] if i.get("code") == "logo-variant-background"]
    # The mark sits on white paper; the corner copy sits on the approved brand-dark panel.
    assert [i["layers"] for i in found] == [["logo-rev-mark"]]
    assert found[0]["action"] == "fix" and found[0]["severity"] == "error"
    assert found[0]["tone"] == "light" and found[0]["background"] == "#ffffff"
    assert found[0]["variant"] == "reversed" and found[0]["approved"] == ["dark", "@brand-dark"]
    dark = variant_document(tmp_path, "#1a1a1a")
    assert not [i for i in dark.check(checks=["brand"])["issues"] if i.get("code") == "logo-variant-background"]


def test_logo_variants_are_validated(tmp_path):
    write(tmp_path, {"palette": dict(PALETTE),
                     "logo": {"variants": {"reversed": {"layers": "logo-rev*", "backgrounds": ["@brand-dark"]}}}})
    with pytest.raises(VixlError, match="brand-dark"):
        load(tmp_path)
    write(tmp_path, {"logo": {"variants": {"reversed": {"layers": "logo-rev*"}}}})
    with pytest.raises(VixlError, match="backgrounds"):
        load(tmp_path)


def test_brand_rules_run_as_a_suite_design_rule(tmp_path):
    write(tmp_path, {"palette": dict(PALETTE), "colors": {"strict": True}})
    p = document(tmp_path, 200, 200)
    p.apply([{"type": "solid", "color": "#ffffff"},
             {"type": "shape", "shape": "rectangle", "name": "far", "width": 20, "height": 20, "fill": "#e01010"},
             {"type": "suite-set", "name": "brand", "suite": {"rules": [
                 {"id": "brand", "kind": "design", "options": {"checks": ["brand"]}}]}}])
    assert not p.check_suite("brand")["passed"]


# --- brand validate --------------------------------------------------------------------------------------


def test_brand_validate_flags_missing_roles_fonts_logos_and_guidance(tmp_path):
    from vixl.resources import register as save

    kit = brand_kit(stages={"h1": "shout"}, logos=[{"name": "logo", "data_base64": base64.b64encode(b"nope").decode()}],
                    presets={"flames": {"fonts": {"body": {"name": "broken", "data_base64": "AAAA"}}}})
    kit["palette"].pop("muted")
    write(tmp_path, kit)
    save("guidance", "voice", "Inks: #111111 and the wood tone #d2a465.", workspace=tmp_path)
    result = report(tmp_path)
    assert not result["valid"]
    assert any("stages.h1" in e and "shout" in e for e in result["errors"])
    assert any("logo 'logo'" in e for e in result["errors"])
    assert any(e.startswith("preset flames: fonts.body") for e in result["errors"])
    assert any("muted" in w for w in result["warnings"])
    assert any("#d2a465" in w for w in result["warnings"])
    assert set(result["brands"]) == {"base", "flames"}
    kit = brand_kit(palette={**PALETTE, "extra": {"wood": "#d2a465"}})
    write(tmp_path, kit)
    clean = report(tmp_path)
    assert clean["valid"] and not clean["warnings"], clean


def test_brand_cli(tmp_path, monkeypatch):
    from vixl.cli import dispatch

    write(tmp_path, brand_kit(presets={"flames": {"palette": {"accent": "#d2a465"}}}))
    monkeypatch.chdir(tmp_path)
    shown, _ = dispatch(["brand", "show", "--preset", "flames"])
    assert shown["palette"]["accent"] == "#d2a465" and shown["stages"]["h1"] == "heading"


# --- logos, elements, styles and brand packages (#436 remainder) -----------------------------------------


def png_base64(color="red", size=(40, 20)):
    from PIL import Image

    stream = io.BytesIO()
    Image.new("RGBA", size, color).save(stream, format="PNG")
    return base64.b64encode(stream.getvalue()).decode()


def logo(name, purpose, color="red", **extra):
    return {"name": name, "data_base64": png_base64(color), "purpose": purpose, **extra}


def test_a_single_logo_is_placed_by_its_place_inside_the_safe_area(tmp_path):
    write(tmp_path, {"palette": dict(PALETTE), "logos": [
        logo("mark", "icon", place={"anchor": "bottom-right", "margin": 0.05, "width_fraction": 0.25})]})
    p = document(tmp_path, 800, 600)
    p.apply({"type": "layout-apply", "name": "hero-statement", "title": "Launch", "unfilled": "omit"})
    mark = p.layer("mark")
    assert (mark["width"], mark["height"]) == (200, 100)
    assert (mark["x"], mark["y"]) == (800 - 30 - 200, 600 - 30 - 100)
    assert mark["provenance"]["purpose"] == "icon"
    assert p.state["layers"][-1]["name"] == "mark"  # kept above the generated background


def test_multi_logo_brands_add_only_auto_logos(tmp_path):
    logos = [logo("icon", "icon"), logo("wordmark", "wordmark", "blue")]
    write(tmp_path, {"palette": dict(PALETTE), "logos": logos})
    p = document(tmp_path)
    p.apply({"type": "layout-apply", "name": "hero-statement", "title": "Launch", "unfilled": "omit"})
    names = {layer["name"] for layer in p.state["layers"]}
    assert not {"icon", "wordmark"} & names  # several logos are variants: none is added on its own
    write(tmp_path, {"palette": dict(PALETTE), "logos": [logos[0], {**logos[1], "auto": True}]})
    p = document(tmp_path)
    p.apply({"type": "layout-apply", "name": "hero-statement", "title": "Launch", "unfilled": "omit"})
    names = {layer["name"] for layer in p.state["layers"]}
    assert "wordmark" in names and "icon" not in names


def test_brand_logo_places_by_purpose_and_moves_instead_of_duplicating(tmp_path):
    write(tmp_path, {"palette": dict(PALETTE), "logo": {"clear_space": 0.5},
                     "logos": [logo("icon", "icon"), logo("wordmark", "wordmark", "blue",
                                                         place={"width_fraction": 0.5, "safe": False})]})
    p = document(tmp_path, 1000, 500)
    p.apply({"type": "brand-logo", "purpose": "wordmark", "anchor": "top-right", "margin": 0})
    word = p.layer("wordmark")
    assert (word["x"], word["y"], word["width"], word["height"]) == (500, 0, 500, 250)
    p.apply({"type": "brand-logo", "purpose": "wordmark", "anchor": "bottom-left", "margin": 0})
    assert [layer["name"] for layer in p.state["layers"]].count("wordmark") == 1
    assert (p.layer("wordmark")["x"], p.layer("wordmark")["y"]) == (0, 250)
    p.apply({"type": "brand-logo", "purpose": "icon", "name": "corner-icon"})
    icon = p.layer("corner-icon")
    assert (icon["x"], icon["y"], icon["width"]) == (0, 0, 40)  # a logo without place keeps its own position
    p.apply({"type": "text", "text": "crowding", "name": "crowd", "x": 45, "y": 0, "size": 12, "color": "#111111"})
    clear = [i for i in p.check(checks=["brand"])["issues"] if "clear space" in i["message"]]
    assert any("corner-icon" in i["layers"] for i in clear)  # brand-logo layers are logos for the logo rules
    with pytest.raises(VixlError, match="no avatar logo"):
        p.apply({"type": "brand-logo", "purpose": "avatar"})


def test_templates_that_place_their_own_logo_opt_out_of_auto_logos(tmp_path, monkeypatch):
    from vixl.resources import register as save

    monkeypatch.setenv("VIXL_RESOURCES", str(tmp_path / "global.json"))
    write(tmp_path, {"palette": dict(PALETTE), "logos": [logo("icon", "icon", auto=True), logo("wordmark", "wordmark")]})
    base = {"width": 600, "height": 400, "proportional": True, "operations": [
        {"type": "solid", "name": "bg", "color": "@background", "width": 600, "height": 400}]}
    save("templates", "plain", base, workspace=tmp_path)
    save("templates", "own-logo", {**base, "places_logo": True, "operations": [
        *base["operations"], {"type": "brand-logo", "purpose": "wordmark", "anchor": "bottom"}]}, workspace=tmp_path)
    p = document(tmp_path, 600, 400)
    p.apply({"type": "template-apply", "name": "plain"})
    assert "icon" in {layer["name"] for layer in p.state["layers"]}
    p = document(tmp_path, 600, 400)
    p.apply({"type": "template-apply", "name": "own-logo"})
    names = [layer["name"] for layer in p.state["layers"]]
    assert "wordmark" in names and "icon" not in names and names[-1] == "wordmark"
    with pytest.raises(VixlError, match="places_logo"):
        save("templates", "bad", {**base, "places_logo": "yes"}, workspace=tmp_path)


def test_logo_fields_are_validated(tmp_path):
    for bad, match in (({"purpose": "favicon"}, "purpose"), ({"place": {"anchor": "nowhere"}}, "anchor"),
                       ({"place": {"margin": 2}}, "margin"), ({"colour": "red"}, "unknown field")):
        write(tmp_path, {"logos": [{**logo("mark", "icon"), **bad}]})
        with pytest.raises(VixlError, match=match):
            load(tmp_path)


def element_document(tmp_path):
    p = Project(300, 300)
    data = base64.b64decode(png_base64("green", (30, 30)))
    asset = f"assets/{hashlib.sha256(data).hexdigest()}.png"
    p.assets[asset] = data
    p.apply([{"type": "shape", "shape": "ellipse", "name": "flame", "width": 60, "height": 90, "fill": "#e8562a"},
             {"type": "add", "asset": asset, "name": "spark", "x": 15, "y": 30},
             {"type": "group", "name": "flame-mark", "targets": ["flame", "spark"]}])
    p.save(tmp_path / "mark.vixl")
    return asset


def test_brand_elements_place_with_object_place_brand_name(tmp_path):
    from vixl.brand import cli as brand_cli

    asset = element_document(tmp_path)
    write(tmp_path, {"palette": dict(PALETTE)})
    result = brand_cli(["element", "flame", "--from", "mark.vixl", "--object", "flame-mark",
                        "--workspace", str(tmp_path)])
    assert result["assets"] == 1 and "brand:flame" in result["use"]
    p = document(tmp_path, 600, 600)
    p.apply({"type": "object-place", "name": "brand:flame", "x": 100, "y": 50, "width": 120})
    root = p.layer("flame")
    assert root["type"] == "group" and root["width"] == 120 and (root["x"], root["y"]) == (100, 50)
    assert asset in p.assets and p.layer("flame/spark")["asset"] == asset
    with pytest.raises(VixlError, match="Brand element 'smoke' not found"):
        p.apply({"type": "object-place", "name": "brand:smoke"})
    # A file whose bytes no longer match the SHA-256 in its name is refused, here and by brand validate.
    kit = json.loads((tmp_path / "brand.json").read_text())
    kit["elements"]["flame"]["assets"][asset] = png_base64("blue", (30, 30))
    write(tmp_path, kit)
    with pytest.raises(VixlError, match="SHA-256"):
        document(tmp_path).apply({"type": "object-place", "name": "brand:flame"})
    assert any("element 'flame'" in error for error in report(tmp_path)["errors"])


def test_a_custom_brand_style_rule_fires_in_the_style_check(tmp_path):
    write(tmp_path, {"palette": dict(PALETTE), "styles": {"one-voice": {
        "guidance": "One typeface, set flush left.",
        "rules": [{"kind": "max_typefaces", "params": {"max": 1}, "severity": "error",
                   "summary": "One typeface only"},
                  {"kind": "text_align", "params": {"allowed": ["left"]}}]}}})
    p = document(tmp_path, 600, 400)
    register(p, "Anton")
    register(p, "Typer")
    p.apply([{"type": "text", "text": "Title", "font": "anton", "name": "a", "color": "#111111"},
             {"type": "text", "text": "Body", "font": "typer", "name": "b", "y": 100, "color": "#111111"},
             {"type": "style-set", "style": "brand:one-voice"}])
    assert p.state["style"]["names"] == ["brand:one-voice"]
    issues = [i for i in p.check(checks=["style"])["issues"] if i["check"] == "style"]
    assert any(i["rule"] == "brand:one-voice/max-typefaces" and i["severity"] == "error" for i in issues)
    p.apply({"type": "style-set", "style": "brand:one-voice", "options": {"max-typefaces": False}})
    assert not [i for i in p.check(checks=["style"])["issues"] if i.get("rule", "").endswith("max-typefaces")]
    with pytest.raises(VixlError, match="no style 'loud'"):
        p.apply({"type": "style-set", "style": "brand:loud"})
    for bad, match in (({"kind": "nonsense"}, "rule kind"), ({"kind": "max_typefaces", "params": {"maxx": 1}},
                                                               "unknown params")):
        write(tmp_path, {"styles": {"one-voice": {"rules": [bad]}}})
        with pytest.raises(VixlError, match=match):
            load(tmp_path)


def test_brand_styles_join_the_style_lookups_of_their_workspace(tmp_path, monkeypatch):
    from vixl.cli import dispatch

    write(tmp_path, {"styles": {"calm": {"title": "Calm", "guidance": "Quiet and spare.",
                                         "rules": [{"kind": "max_typefaces", "params": {"max": 2}}]}}})
    monkeypatch.chdir(tmp_path)
    listed, _ = dispatch(["styles", "list"])
    assert listed["styles"][0]["name"] == "brand:calm" and listed["styles"][0]["checks"] == ["max-typefaces"]
    shown, _ = dispatch(["styles", "show", "brand:calm"])
    assert shown["title"] == "Calm" and shown["checks"][0]["id"] == "brand:calm/max-typefaces"
    p = document(tmp_path)
    from vixl.styles import apply_operations, brand_styles_of

    p.apply(apply_operations("brand:calm", brand_styles=brand_styles_of(p)))
    assert p.state["style"]["names"] == ["brand:calm"]
    assert "Quiet and spare." in p.state["design_guidance"]["style"]


def test_brand_init_then_validate_round_trip(tmp_path):
    from vixl.brand import cli as brand_cli

    font = tmp_path / "Brand.ttf"
    font.write_bytes(renamed("Brandy"))
    made = brand_cli(["init", "--name", "Acme", "--palette", "ocean", "--pairing", "source-serif-sans",
                      "--font", f"heading={font}", "--workspace", str(tmp_path)])
    assert made["name"] == "Acme" and set(made["palette"]) == set(PALETTE) and made["fonts"] == ["heading"]
    result = report(tmp_path)
    assert result["valid"], result
    assert load(tmp_path)["fonts"]["heading"]["data_base64"]
    with pytest.raises(VixlError, match="already exists"):
        brand_cli(["init", "--workspace", str(tmp_path)])


def brand_workspace(tmp_path, monkeypatch):
    from vixl.resources import register as save

    monkeypatch.setenv("VIXL_RESOURCES", str(tmp_path / "global.json"))
    source = tmp_path / "source"
    source.mkdir()
    write(source, brand_kit(logos=[logo("mark", "icon")], styles={"calm": {"guidance": "Quiet."}}))
    save("palettes", "acme", ["#101010", "#f0f0f0", "#0044aa"], workspace=source)
    save("guidance", "voice", "Short sentences.", workspace=source)
    save("templates", "card", {"width": 400, "height": 300, "operations": [
        {"type": "asset-place", "resource": "seal", "x": 10, "y": 10}]}, workspace=source)
    save("assets", "seal", {"data_base64": png_base64("green"), "media_type": "png", "credit": "Acme"},
         workspace=source)
    return source


def test_pack_then_install_into_an_empty_workspace_reproduces_the_resources(tmp_path, monkeypatch):
    from vixl.brand import cli as brand_cli

    source = brand_workspace(tmp_path, monkeypatch)
    out = tmp_path / "acme.vixlbrand"
    packed = brand_cli(["pack", str(out), "--workspace", str(source)])
    assert packed["resources"] == {"assets": ["seal"], "guidance": ["voice"], "palettes": ["acme"],
                                   "templates": ["card"]}
    again = brand_cli(["pack", str(tmp_path / "again.vixlbrand"), "--workspace", str(source)])
    assert again["sha256"] == packed["sha256"]  # deterministic bytes
    with pytest.raises(VixlError, match="already exists"):
        brand_cli(["pack", str(out), "--workspace", str(source)])
    target = tmp_path / "target"
    target.mkdir()
    installed = brand_cli(["install", str(out), "--workspace", str(target)])
    assert installed["resources"]["assets"] == ["seal"]
    assert load(target) == load(source)
    assert json.loads((target / ".vixl-resources.json").read_text()) == json.loads(
        (source / ".vixl-resources.json").read_text())
    assert sorted(p.name for p in (target / ".vixl-resources-assets").iterdir()) == sorted(
        p.name for p in (source / ".vixl-resources-assets").iterdir())
    p = document(target, 400, 300)
    p.apply({"type": "template-apply", "name": "card"})
    assert p.layer("seal")["provenance"]["credit"] == "Acme"
    # A second install of the same package changes nothing; a different brand.json needs --overwrite.
    brand_cli(["install", str(out), "--workspace", str(target)])
    write(target, {"name": "Other"})
    with pytest.raises(VixlError, match="already exists"):
        brand_cli(["install", str(out), "--workspace", str(target)])
    brand_cli(["install", str(out), "--workspace", str(target), "--overwrite"])
    assert load(target)["name"] == "JXG"


def test_install_preset_only_adds_the_brand_as_a_preset(tmp_path, monkeypatch):
    from vixl.brand import cli as brand_cli

    source = brand_workspace(tmp_path, monkeypatch)
    out = tmp_path / "acme.vixlbrand"
    brand_cli(["pack", str(out), "--workspace", str(source)])
    target = tmp_path / "target"
    target.mkdir()
    write(target, {"name": "Home", "palette": dict(PALETTE)})
    result = brand_cli(["install", str(out), "--preset-only", "--as", "acme", "--workspace", str(target)])
    assert result["preset"] == "acme"
    raw = json.loads((target / "brand.json").read_text())
    assert raw["name"] == "Home" and "acme" in raw["presets"] and "logos" in raw["presets"]["acme"]
    assert not (target / ".vixl-resources.json").exists()


def test_install_validates_first_and_rolls_back_on_failure(tmp_path, monkeypatch):
    import zipfile

    from vixl import brand_pack
    from vixl.brand import cli as brand_cli

    source = brand_workspace(tmp_path, monkeypatch)
    out = tmp_path / "acme.vixlbrand"
    brand_cli(["pack", str(out), "--workspace", str(source)])
    target = tmp_path / "target"
    target.mkdir()
    write(target, {"name": "Before"})
    before = (target / "brand.json").read_bytes()
    # A member changed after packing fails its manifest checksum; nothing is written.
    corrupt = tmp_path / "corrupt.vixlbrand"
    with zipfile.ZipFile(out) as original, zipfile.ZipFile(corrupt, "w") as copy:
        for info in original.infolist():
            data = original.read(info)
            copy.writestr(info, data.replace(b"Short sentences.", b"Long sentences!!") if "guidance" in info.filename
                          else data)
    with pytest.raises(VixlError, match="Checksum mismatch"):
        brand_cli(["install", str(corrupt), "--workspace", str(target), "--overwrite"])
    # A path that escapes the package is refused before anything is read.
    escape = tmp_path / "escape.vixlbrand"
    with zipfile.ZipFile(escape, "w") as archive:
        archive.writestr("../brand.json", "{}")
    with pytest.raises(VixlError, match="Unexpected member"):
        brand_cli(["install", str(escape), "--workspace", str(target)])
    assert (target / "brand.json").read_bytes() == before and not (target / ".vixl-resources.json").exists()
    # A failure while writing restores what was there and removes new asset files.
    real = brand_pack._atomic

    def failing(path, data):
        if path.name == "brand.json":
            raise OSError("disk full")
        real(path, data)

    monkeypatch.setattr(brand_pack, "_atomic", failing)
    with pytest.raises(OSError):
        brand_cli(["install", str(out), "--workspace", str(target), "--overwrite"])
    assert (target / "brand.json").read_bytes() == before
    assert not (target / ".vixl-resources.json").exists()
    assert not any((target / ".vixl-resources-assets").iterdir())


def test_validate_flags_style_guidance_colours_and_undefined_template_font_roles(tmp_path, monkeypatch):
    from vixl.resources import register as save

    monkeypatch.setenv("VIXL_RESOURCES", str(tmp_path / "global.json"))
    write(tmp_path, brand_kit(styles={"loud": {"guidance": "Shout in #ff00ff on #ffffff."}}))
    save("templates", "aside", {"width": 300, "height": 200, "operations": [
        {"type": "text", "text": "x", "font": "script"}, {"type": "text", "text": "y", "font": "hand"}]},
        workspace=tmp_path)
    warnings = report(tmp_path)["warnings"]
    assert any("styles.loud" in w and "#ff00ff" in w and "#ffffff" not in w for w in warnings)
    assert any("'script'" in w and "aside" in w for w in warnings)
    assert not any("'hand'" in w for w in warnings)


@pytest.mark.parametrize("extra", [{"wood": "#d2a465"},
                                   {"wood": {"color": "#d2a465", "max_fraction": 0.15}, "ballpoint": "#1f3a93"}])
def test_new_roll_and_layout_in_a_workspace_whose_brand_has_extra_colours(tmp_path, monkeypatch, extra):
    # The rolled palette takes the brand's roles; palette.extra is a table of approved colours, not a role.
    from vixl.cli import main

    (tmp_path / "brand.json").write_text(json.dumps({"palette": {"background": "#fffaf0", "accent": "#c0392b",
                                                                 "extra": extra}}))
    monkeypatch.chdir(tmp_path)
    doc = str(tmp_path / "card.vixl")
    assert main(["new", "400x300", "-o", doc, "--no-fonts"]) == 0
    assert Project.load(doc).state["canvas"]["background"] == "#fffaf0"
    assert main(["--project", doc, "roll", "--apply"]) == 0
    assert main(["--project", doc, "layout", "apply", "event-poster", "--replace"]) == 0
    assert Project.load(doc).state["swatches"]["accent"] == "#c0392b"
