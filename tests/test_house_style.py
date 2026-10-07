"""The house style as data, the purpose tier, tiered pools and the rolls that read them (#388)."""

from collections import Counter
import json
import random

import pytest

from vixl import Project, house_style
from vixl.briefs import KINDS, NO_DIRECTION, guide
from vixl.layouts import LAYOUTS, RATIOS, assign_roles
from vixl.looks import LOOKS
from vixl.style_catalog import STYLES
from vixl.typefaces import pairings, roll, roll_document
from vixl.variety import document_defaults, tier_weights


def _rolls(n, **options):
    return [roll(seed, **options) for seed in range(n)]


# --- the data file (#401) ------------------------------------------------------------------------


def test_house_style_data_names_only_real_entries_and_covers_every_catalog():
    assert set(house_style.entries("pairings")) == {p["name"] for p in pairings()}
    assert set(house_style.entries("layouts")) == set(LAYOUTS)
    assert set(house_style.entries("styles")) == set(STYLES)
    assert set(house_style.entries("looks")) == set(LOOKS)
    from vixl.resources import PALETTES
    assert set(house_style.entries("palettes")) <= set(PALETTES)
    assert set(house_style.data()["purposes"]) == set(house_style.PURPOSES)
    from vixl.sizes import SIZES
    categories = {entry["category"] for entry in SIZES.values()}
    for purpose in house_style.PURPOSES:
        profile = house_style.profile(purpose)
        assert set(profile["kinds"]) <= set(KINDS), purpose
        assert set(profile["size_categories"]) <= categories, purpose
        assert set(profile["pairings"]["prefer"]) <= set(house_style.entries("pairings")), purpose
        assert set(profile["layouts"]["prefer"]) <= set(LAYOUTS), purpose
        assert set(profile["styles"]["prefer"]) <= set(STYLES), purpose
        assert set(profile["look"]["weights"]) - {"none"} <= set(LOOKS), purpose
        assert set(profile["type_scales"]) <= set(RATIOS) and 0 <= profile["dark"] <= 1, purpose
    for kind in house_style.KINDS:
        assert {meta["tier"] for meta in house_style.entries(kind).values()} <= {*house_style.TIERS, "explicit"}


def test_craft_signature_and_rules_are_data():
    craft = house_style.craft()
    assert craft["corner"] == "sharp" and craft["shadow"] == "offset" and craft["label_case"] == "upper"
    assert craft["line_height"] == {"display": 1.0, "heading": 1.1, "lead": 1.35, "body": 1.45, "caption": 1.3}
    assert "sharp corners" in craft["signature"] and craft["contrast"]["text"] == 4.5


def test_rolls_read_the_house_data(monkeypatch):
    # Changing a value in the data changes the rolls: the modules do not keep their own copy.
    data = house_style._data()
    monkeypatch.setitem(data["purposes"]["form"], "dark", 1.0)
    monkeypatch.setitem(data["purposes"]["form"], "type_scales", ["golden"])
    for result in _rolls(20, purpose="form"):
        assert result["direction"]["mode"] == "dark" and result["direction"]["type_scale"] == "golden"
    monkeypatch.setitem(data["craft"], "corner", "pill")
    assert {r["direction"]["corner"] for r in _rolls(20, purpose="document", variety="low")} >= {"pill"}


def test_house_style_is_readable_from_cli_and_resource_view():
    from vixl.finishing_cli import standalone

    summary = standalone("house", [])
    assert summary["version"] == house_style.VERSION and summary["pools"]["palettes"]["safe"] >= 30
    assert standalone("house", ["show", "slides"])["profile"]["purpose"] == "slides"
    assert house_style.show("instagram-post")["purpose"] == "social"


# --- the purpose tier (#403) ---------------------------------------------------------------------


@pytest.mark.parametrize("value,purpose", [
    ("poster", "poster"), ("social-card", "social"), ("stationery", "document"), ("instagram-post", "social"),
    ("slide", "slides"), ("favicon", "logo"), ("video-1080p", "motion"), ("letter", "document"), ("web", "social"),
    ("diagram", "diagram"), ("form", "form"), ("logos", "logo"), ("nonsense", None)])
def test_purpose_comes_from_purpose_kind_size_or_category(value, purpose):
    assert house_style.purpose_for(value) == purpose


def test_purpose_is_resolved_stored_and_reported():
    p = Project.sized("instagram-post")
    defaults = document_defaults(p, seed=3)
    assert defaults["purpose"] == "social" and defaults["purpose_source"] == "size"
    assert defaults["house_style_version"] == house_style.VERSION
    rolled = roll_document(p, seed=3)
    assert rolled["purpose"] == "social" and rolled["purpose_source"] == "document"
    assert roll_document(p, seed=3, purpose="slides")["purpose_source"] == "explicit"
    assert guide("poster", seed=4)["direction"]["purpose_source"] == "brief kind"


def test_same_seed_differs_by_purpose_and_brand_still_wins(tmp_path):
    poster = [r["direction"] for r in _rolls(30, purpose="poster")]
    document = [r["direction"] for r in _rolls(30, purpose="document")]
    assert sum(a["type_scale"] != b["type_scale"] or a["pairing"] != b["pairing"] for a, b in zip(poster, document)) > 20
    (tmp_path / "brand.json").write_text(json.dumps({"pairing": "playfair-lato", "palette": {"background": "#ffffff"}}))
    for seed in range(5):
        branded = roll_document(workspace=tmp_path, seed=seed, purpose="slides")
        assert branded["direction"]["pairing"] == "playfair-lato"
        assert branded["operation"]["colors"] == {"background": "#ffffff"}


# --- tiers gated by level, weighted by purpose (#405, #393) ----------------------------------------


@pytest.mark.parametrize("level", ["low", "medium", "high"])
def test_tier_distribution_matches_the_configured_weights(level):
    weights = tier_weights(level)
    total = sum(weights.values())
    counts = Counter(r["tier"] for r in _rolls(200, variety=level))
    for tier in house_style.TIERS:
        expected = weights.get(tier, 0) / total
        assert abs(counts[tier] / 200 - expected) <= 0.08, (level, tier, counts)
    if level == "low":
        assert set(counts) == {"safe"}


def test_every_rolled_choice_reports_its_tier():
    result = roll(11, variety="high", purpose="poster")
    assert set(result["tiers"]) == {"pairing", "palette", "layout", "style", "look"}
    for kind, name in (("pairings", "pairing"), ("palettes", "palette"), ("layouts", "layout")):
        assert result["tiers"][name] == house_style.tier_of(kind, result["direction"][name], "poster")
        assert result["tiers"][name] != "explicit"


def test_variety_levels_visibly_differ_and_every_safe_style_rolls():
    low, high = _rolls(80, variety="low", purpose="poster"), _rolls(80, variety="high", purpose="poster")

    def spread(rows, key):
        return len({r["direction"][key] for r in rows})

    assert spread(high, "palette") > spread(low, "palette")
    assert spread(high, "layout") > spread(low, "layout")
    assert {r["direction"]["background_treatment"] for r in low} <= {"flat", "gradient"}
    assert {"split", "pattern"} <= {r["direction"]["background_treatment"] for r in high}
    amounts_low = {r["direction"]["look_amount"] for r in low if r["direction"]["look"] != "none"}
    amounts_high = {r["direction"]["look_amount"] for r in high if r["direction"]["look"] != "none"}
    assert max(amounts_low) < min(amounts_high)
    styles = {r["direction"]["style"] for r in _rolls(300, variety="low")}
    assert styles == set(house_style.names("styles", "safe"))


# --- palette pools (#426) ------------------------------------------------------------------------


def test_safe_pool_has_dark_saturated_duotone_and_earthy_palettes():
    entries = house_style.entries("palettes")
    safe_families = Counter(meta.get("family") for meta in entries.values() if meta["tier"] == "safe")
    assert all(safe_families[family] >= 3 for family in ("dark", "saturated", "duotone", "earthy")), safe_families
    assert house_style.names("palettes", "bold") and house_style.names("palettes", "avant-garde")
    # Curated legacy palettes joined the tiers and kept their names.
    assert entries["midnight"]["tier"] == "safe" and entries["neon"]["tier"] == "avant-garde"
    medium = Counter(r["tiers"]["palette"] for r in _rolls(200, variety="medium"))
    assert medium["bold"] > 0 and medium["safe"] > medium["bold"]


@pytest.mark.parametrize("name", sorted(n for n, m in house_style.entries("palettes").items() if m["tier"] != "explicit"))
def test_every_rollable_palette_passes_the_role_contrast_pass(name):
    from vixl.colors import contrast_ratio, parse

    def ratio(a, b):
        return contrast_ratio(parse(a)[:3], parse(b)[:3])

    for mode in house_style.palette_modes(name):
        roles = assign_roles({"palette": name, "mode": mode}, random.Random(0))
        assert ratio(roles["ink"], roles["background"]) >= 7, (name, mode)
        for role in ("muted", "accent-text"):
            assert min(ratio(roles[role], roles["background"]), ratio(roles[role], roles["surface"])) >= 4.5, (name, mode, role)


def test_dark_only_palettes_roll_only_in_dark_mode():
    for result in _rolls(200, variety="high"):
        assert result["direction"]["mode"] in house_style.palette_modes(result["direction"]["palette"])


# --- pairing, type scale and mode by purpose (#414, #400) ------------------------------------------


def test_slides_roll_ui_sans_pairings_and_tight_scales():
    prefer = set(house_style.profile("slides")["pairings"]["prefer"])
    rows = _rolls(100, purpose="slides")
    assert sum(r["direction"]["pairing"] in prefer for r in rows) >= 70
    assert all(RATIOS[r["direction"]["type_scale"]] <= 1.25 for r in rows)
    posters = _rolls(100, purpose="poster")
    assert all(RATIOS[r["direction"]["type_scale"]] >= 1.5 for r in posters)


@pytest.mark.parametrize("purpose", ["document", "form", "slides", "poster", "social", "motion"])
def test_dark_share_follows_the_purpose(purpose):
    share = sum(r["direction"]["mode"] == "dark" for r in _rolls(200, purpose=purpose)) / 200
    assert abs(share - house_style.profile(purpose)["dark"]) <= 0.08, (purpose, share)


# --- finishing and backgrounds by purpose (#420, #428) ----------------------------------------------


def test_posters_get_a_visible_look_and_forms_none():
    posters = _rolls(60, purpose="poster")
    finished = [r for r in posters if r["direction"]["look"] != "none"]
    assert len(finished) >= 30 and all(r["direction"]["look_amount"] >= 0.25 for r in finished)
    assert {r["direction"]["look"] for r in _rolls(60, purpose="form", variety="high")} == {"none"}


def test_rolled_shadow_reaches_a_visible_layer():
    p = Project(1080, 1350)
    p.apply({"type": "layout-apply", "name": "open-letter", "seed": 2, "palette": "chalk-indigo", "mode": "light",
             "title": "Market", "cta": "Free entry", "unfilled": "omit",
             "direction": {"look": "hard-shadow", "look_amount": 0.25, "corner": "sharp"}})
    shadowed = [layer for layer in p.state["layers"] if "hard-shadow" in layer.get("looks", {})]
    assert shadowed and all(layer["type"] == "shape" for layer in shadowed)
    assert shadowed[0]["looks"]["hard-shadow"]["amount"] == 0.25


def test_split_and_pattern_backgrounds_roll_at_medium_for_social_only():
    social = {r["direction"]["background_treatment"] for r in _rolls(120, purpose="social")}
    assert {"split", "pattern"} & social
    document = {r["direction"]["background_treatment"] for r in _rolls(120, purpose="document")}
    assert document <= {"flat", "gradient"}


# --- filters and moods act on the rolled pools (#391, #285) ------------------------------------------


def test_mood_steers_palettes_layouts_and_tiers():
    playful, calm = _rolls(50, mood="playful"), _rolls(50, mood="calm")
    assert Counter(r["direction"]["palette"] for r in playful) != Counter(r["direction"]["palette"] for r in calm)
    assert Counter(r["direction"]["layout"] for r in playful) != Counter(r["direction"]["layout"] for r in calm)
    bold = sum(r["tier"] != "safe" for r in playful)
    assert bold > sum(r["tier"] != "safe" for r in calm) and bold >= 15
    palettes = house_style.entries("palettes")
    assert sum("playful" in palettes[r["direction"]["palette"]]["mood"] for r in playful) > \
        sum("playful" in palettes[r["direction"]["palette"]]["mood"] for r in calm)


def test_playful_posters_use_expressive_layouts():
    rows = _rolls(60, purpose="poster", mood="playful")
    expressive = [r for r in rows if not LAYOUTS[r["direction"]["layout"]].get("safe_composition")]
    assert len(expressive) >= 20


def test_canvas_filter_acts_on_rolled_layouts():
    wide = {r["direction"]["layout"] for r in _rolls(150, variety="high", canvas=(1500, 500), purpose="social")}
    assert "story-vertical" not in wide and "letterhead" not in wide
    tall = {r["direction"]["layout"] for r in _rolls(150, variety="high", canvas=(1080, 1920), purpose="social")}
    assert "banner" not in tall and "story-vertical" in tall


def test_rolls_only_pick_layouts_that_place_the_supplied_copy():
    copy = {"title": "Summer Night Market", "subtitle": "Food and music", "label": "June 21", "cta": "Free entry"}
    for seed in range(12):
        p = Project(1080, 1350)
        result = roll_document(p, seed=seed, purpose="poster", variety="high", slots=copy)
        p.apply({**result["operation"], **copy})


# --- brief recommendations agree with the roll (#399) ----------------------------------------------


@pytest.mark.parametrize("kind", sorted(set(KINDS) - NO_DIRECTION))
def test_brief_recommendations_and_attached_roll_agree(kind):
    result = guide(kind, seed=5)
    notes = result["recommendations"]
    chosen = result["direction"]["direction"]
    for key, name in (("layouts", "layout"), ("looks", "look"), ("styles", "style")):
        assert notes[key]["rolled"] == chosen[name]
        assert notes[key]["in_recommendations"] == (chosen[name] in KINDS[kind][key])
        assert all(item["name"] in KINDS[kind][key] for item in notes[key]["alternatives"])
    assert "alternatives" in notes["note"]


def test_high_variety_poster_briefs_usually_roll_a_recommended_layout():
    hits = sum(guide("poster", seed=seed, variety="high")["recommendations"]["layouts"]["in_recommendations"]
               for seed in range(20))
    assert hits >= 8


# --- default-change policy (#430) ------------------------------------------------------------------


def test_version_one_replays_the_old_rolls():
    # Recorded with 0.22.1 before the house-style change.
    p = Project.sized("poster-18x24", dpi=40)
    old = roll_document(p, seed=1000, purpose="poster", variety="low", house_style_version=1)["direction"]
    assert (old["palette"], old["layout"], old["mode"], old["pairing"], old["look"], old["style"]) == \
        ("cream-marigold", "quiet-editorial", "dark", "lexend-atkinson", "none", "corporate-flat")
    p = Project.sized("slide")
    old = roll_document(p, seed=1012, purpose="slides", variety="low", house_style_version=1)["direction"]
    assert (old["palette"], old["layout"], old["mode"], old["pairing"], old["look"], old["style"]) == \
        ("mist-pine", "calm-cover", "light", "eb-garamond-single", "none", "editorial")
    assert "look_amount" not in old


def test_workspace_can_pin_the_house_style_version(tmp_path):
    (tmp_path / ".vixl").mkdir()
    (tmp_path / ".vixl" / "variety.json").write_text(json.dumps({"house_style": 1}))
    p = Project(1080, 1080)
    defaults = document_defaults(p, seed=8, workspace=tmp_path)
    assert defaults["house_style_version"] == 1
    assert defaults["direction"]["palette"] in house_style.legacy(1)["palettes"]
    # A document keeps the version it was made with, whatever the workspace says later.
    (tmp_path / ".vixl" / "variety.json").write_text(json.dumps({"house_style": 2}))
    assert roll_document(p, seed=8, workspace=tmp_path)["house_style_version"] == 1


def test_old_directions_keep_their_faint_look_amount():
    p = Project(800, 800)
    p.apply({"type": "layout-apply", "name": "open-letter", "seed": 2, "palette": "chalk-indigo", "title": "Old",
             "cta": "Go", "unfilled": "omit", "direction": {"look": "soft-shadow", "corner": "soft"}})
    looks = [layer["looks"]["soft-shadow"]["amount"] for layer in p.state["layers"] if "soft-shadow" in layer.get("looks", {})]
    assert looks == [0.1]


# --- the eval (#431) -------------------------------------------------------------------------------


def test_house_style_eval_subset_scores_quality_and_diversity():
    from evals.house_style import BRIEFS, evaluate

    briefs = [BRIEFS[2], BRIEFS[7], BRIEFS[13], BRIEFS[44]]
    result, runs = evaluate(briefs, ("low", "high"))
    for level in ("low", "high"):
        quality = result["scores"][level]["quality"]
        assert quality["no_fix_findings"] == 1.0, result["scores"][level]["fix_findings"]
        assert quality["fonts_installed"] == 1.0 and quality["contrast_pass"] == 1.0
        assert quality["min_ink_contrast"] >= 7
    assert {row["tier"] for row in runs if row["level"] == "low"} == {"safe"}
