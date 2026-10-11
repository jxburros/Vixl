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
    assert p.layer("t")["font"] == "DejaVuSans.ttf" and "font_role" not in p.layer("t")
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
