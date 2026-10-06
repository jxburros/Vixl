"""Curated safe defaults, reproducible sparse briefs, and workspace diversity (#158–161)."""

import json
from pathlib import Path

import pytest

from vixl import Project
from vixl.briefs import guide
from vixl.layouts import LAYOUTS, SAFE_COMPOSITIONS
from vixl.resources import create_template
from vixl.safe_catalog import SAFE_PALETTES, catalog
from vixl.typefaces import roll, roll_document
from vixl.variety import document_defaults


def test_safe_catalog_has_large_explicit_pools_without_novelty_fonts():
    result = catalog()
    assert len([x for x in result["palettes"].values() if x["safe"]]) >= 20
    assert len([x for x in result["layouts"].values() if x["safe"]]) >= 15
    assert result["palettes"]["neon"]["safe"] is False
    assert result["looks"]["soft-shadow"]["safe"] and not result["looks"]["neon"]["safe"]
    assert not next(x for x in result["pairings"] if x["name"] == "great-vibes-eb-garamond")["safe"]
    assert all(LAYOUTS[n]["safe"] for n in SAFE_COMPOSITIONS)


@pytest.mark.parametrize("size,reading_width", [("og-image", 600), ("instagram-portrait", 540), ("slide", 1280)])
def test_every_safe_palette_and_layout_renders_and_passes_reading_checks(size, reading_width):
    # Exercise each entry across the primary social/phone/slide sizes. The text, including
    # caption and call to action, must stay readable after actual raster rendering.
    combinations = [("quiet-editorial", name) for name in SAFE_PALETTES]
    combinations += [(name, "chalk-indigo") for name in SAFE_COMPOSITIONS]
    for layout, palette in combinations:
        p = Project.sized(size)
        p.apply({"type": "layout-apply", "name": layout, "palette": palette, "seed": 14,
                 "title": "Clear ideas", "subtitle": "A useful update", "label": "News", "cta": "Read more", "unfilled": "omit"})
        assert p.render().getbbox(), (size, layout, palette)
        result = p.check(checks=["contrast", "legibility"], thumbnail_width=reading_width)
        assert not result["issues"], (size, layout, palette, result["issues"])


def test_sparse_layout_template_and_guide_return_fresh_reproducible_choices(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    a, b = Project(1080, 1080), Project(1080, 1080)
    op = {"type": "layout-apply", "name": "quiet-editorial", "title": "A sparse brief", "unfilled": "omit"}
    a.apply(op)
    b.apply(op)
    assert a.state["layout"]["seed"] != b.state["layout"]["seed"]
    copy = Project(1080, 1080)
    copy.apply({**op, "seed": a.state["layout"]["seed"]})
    assert copy.state["layout"]["palette"] == a.state["layout"]["palette"]
    assert copy.render().tobytes() == a.render().tobytes()
    first = create_template("social-square", {"title": "Launch"}, workspace=tmp_path)
    second = create_template("social-square", {"title": "Launch"}, workspace=tmp_path)
    assert first.state["template"]["seed"] != second.state["template"]["seed"]
    reproduction = create_template("social-square", {"title": "Launch"}, workspace=tmp_path, seed=first.state["template"]["seed"])
    assert reproduction.state["template"]["rolled"] == first.state["template"]["rolled"]
    first = guide("a poster for a bake sale", workspace=tmp_path)
    second = guide("a poster for a bake sale", workspace=tmp_path)
    assert first["direction"]["seed"] != second["direction"]["seed"]
    assert any("Sparse briefs" in step for step in first["start_here"])


def test_fixed_workspace_controls_layouts_templates_and_placement(tmp_path):
    policy = tmp_path / ".vixl"
    policy.mkdir()
    (policy / "variety.json").write_text(json.dumps({"variety": "fixed", "seed": 29}))
    records = []
    for _ in range(2):
        p = Project(1080, 1080, workspace=tmp_path)
        p.apply({"type": "layout-apply", "name": "quiet-editorial", "title": "Fixed", "unfilled": "omit"})
        p.apply({"type": "container-place", "resource": "feature-icon", "name": "feature"})
        records.append((p.state["layout"]["seed"], p.state["layout"]["palette"], p.layer("feature")["container"]["seed"], p.layer("feature")["container"]["variant"]))
    assert records[0] == records[1] and records[0][0] == records[0][2] == 29
    a = create_template("social-square", {"title": "Fixed"}, workspace=tmp_path)
    b = create_template("social-square", {"title": "Fixed"}, workspace=tmp_path)
    assert a.state["template"]["seed"] == b.state["template"]["seed"] == 29


def test_recent_history_diversifies_unseeded_rolls_but_never_changes_seed_replay(tmp_path):
    fixed = roll_document(workspace=tmp_path, seed=14)
    recent = [roll_document(workspace=tmp_path) for _ in range(40)]
    for before, after in zip(recent, recent[1:]):
        assert before["direction"]["palette"] != after["direction"]["palette"]
        assert before["direction"]["layout"] != after["direction"]["layout"]
    assert len(json.loads((tmp_path / ".vixl" / "rolls.json").read_text())) == 32
    assert roll_document(workspace=tmp_path, seed=14) == fixed


def test_brand_and_explicit_locks_win_over_sparse_choices(tmp_path):
    (tmp_path / "brand.json").write_text(json.dumps({"pairing": "source-serif-sans", "palette": {
        "background": "#ffffff", "ink": "#222222", "accent": "#345678"}}))
    p = Project(1080, 1080)
    defaults = document_defaults(p, seed=7, workspace=tmp_path)
    assert defaults["direction"]["pairing"] == "source-serif-sans"
    p.apply({"type": "layout-apply", "name": "quiet-editorial", "title": "Brand", "unfilled": "omit"})
    assert p.state["swatches"]["accent"] == "#345678"
    assert p.state["swatches"]["background"] == "#ffffff" and p.state["swatches"]["ink"] == "#222222"
    locked = roll_document(p, seed=7, locks={"pairing": "inter-single-ui", "palette": "chalk-indigo", "corner": "sharp"})
    assert locked["direction"]["pairing"] == "inter-single-ui"
    assert locked["direction"]["palette"] == "chalk-indigo" and locked["direction"]["corner"] == "sharp"


def test_defaults_belong_to_creation_but_later_choices_remain_undoable(tmp_path):
    p = Project.sized("og-image", workspace=tmp_path)
    chosen = document_defaults(p, seed=11)
    assert len(p.nodes) == 1
    p.save(tmp_path / "defaults.vixl")
    loaded = Project.load(tmp_path / "defaults.vixl")
    assert loaded.state["design_defaults"] == chosen and len(loaded.nodes) == 1
    document_defaults(loaded, seed=12)
    assert len(loaded.nodes) == 2
    loaded.undo()
    assert loaded.state["design_defaults"] == chosen


@pytest.mark.parametrize("contrast", ["moderate", "strong"])
def test_weight_contrast_locks_select_actual_font_weights(contrast):
    result = roll(8, locks={"weight_contrast": contrast})
    from vixl.typefaces import get_pairing

    pairing = get_pairing(result["direction"]["pairing"])
    difference = pairing["heading"]["weight"] - pairing["body"]["weight"]
    assert (difference >= 300) == (contrast == "strong")
    assert result["direction"]["weight_contrast"] == contrast


def test_dimensions_apply_and_explicit_component_preserves_supplied_copy():
    result = roll(8, locks={"container": "feature-icon", "container_variant": "centered", "look": "subtle-grain",
                           "background_treatment": "gradient", "corner": "round", "motif": "ellipse", "margin": 0.1})
    assert {"container", "container_variant", "motif", "look", "type_scale", "weight_contrast", "density", "margin", "corner", "background_treatment", "color_assignment"} <= result["direction"].keys()
    p = Project(1080, 1080)
    p.apply({**result["operation"], "title": "Our feature", "body": "A useful benefit", "subtitle": "More detail", "unfilled": "omit"})
    group = p.layer("component")
    assert group["container"]["resource"] == "feature-icon" and group["container"]["variant"] == "centered"
    texts = {layer.get("text") for layer in p.state["layers"]}
    assert {"Our feature", "A useful benefit", "More detail"} <= texts
    assert p.layer("background")["type"] == "gradient"
    assert "subtle-grain" in p.layer("background")["looks"]
    assert p.layer("direction-motif")["shape"] == "ellipse"
    assert p.state["layout"]["margin"] == 108


def test_roll_apply_installs_chosen_pairing_and_returns_check(monkeypatch, tmp_path):
    from vixl import typefaces

    installed = []
    font_data = (Path(typefaces.DATA) / "DejaVuSans.ttf").read_bytes()
    monkeypatch.setattr(typefaces, "fetch_font", lambda *args, **kwargs: (font_data, "test-font"))
    original = typefaces.pair_fonts

    def pair(project, pairing, **kwargs):
        installed.append(pairing)
        return original(project, pairing, **kwargs)

    monkeypatch.setattr(typefaces, "pair_fonts", pair)
    p = Project(1080, 1080, workspace=tmp_path)
    result = roll_document(p, seed=21, apply=True, slots={"title": "A chosen direction"})
    assert installed == [result["direction"]["pairing"]]
    assert p.state["fonts"] and p.state["typography"] and "check" in result
