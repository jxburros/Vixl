"""Palette and decoration from the brief (#654): motif themes carry moods, a keyword table adds more, and a roll of a
brief weights (never filters) the palettes with those moods and suggests the theme's motif."""

from collections import Counter

from vixl import house_style
from vixl.briefs import KINDS, brief_moods, guide
from vixl.guidance import motif_registry, motifs
from vixl.typefaces import BRIEF_KEYS, roll, roll_document

WARM = {"warm", "earthy", "cozy", "rustic", "crafted"}


def palette_moods():
    return {mood for meta in house_style.entries("palettes").values() for mood in meta.get("mood", [])}


def test_every_motif_theme_names_palette_moods():
    known = palette_moods()
    for name, theme in motif_registry().items():
        assert len(set(theme["moods"]) & known) >= 2, name
    assert {"warm", "earthy"} <= set(motif_registry()["coffee"]["moods"])
    assert motifs("a winter coffee night")[0]["moods"]


def test_the_keyword_table_lives_in_the_house_style():
    table = house_style.mood_keywords()
    assert set(table) <= palette_moods()
    assert "cozy" in table["warm"] and house_style.moods()["brief_weight"] == 3


def test_brief_moods_come_from_themes_and_keywords():
    found = brief_moods("A poster for a cozy coffee morning")
    assert {"warm", "earthy", "fresh"} <= set(found["moods"])
    assert found["words"][:1] == ["coffee"] and {"cozy", "morning"} <= set(found["words"])
    first = motif_registry()["coffee"]["elements"][0]
    assert found["motif"]["theme"] == "coffee" and found["motif"]["element"] == first["element"]
    assert found["motif"]["shapes"] == first["shapes"]
    # A mood word alone counts; a theme-less brief has no motif.
    assert brief_moods("a playful flyer") == {"moods": ["playful"], "words": ["playful"], "motif": None}
    assert brief_moods("a flyer for our annual meeting") is None


def test_a_brief_with_no_match_rolls_exactly_as_before():
    for seed in range(30):
        assert roll(seed, brief_moods=None) == roll(seed) == roll(seed, brief_moods={"moods": []})
    item = KINDS["poster"]
    recommend = {"layouts": item["layouts"], "looks": item["looks"], "styles": item["styles"]}
    for seed in (1, 2, 3):
        plain = roll_document(seed=seed, kind="poster", recommend=recommend)
        assert guide("a poster for our annual meeting", seed=seed)["direction"] == plain


def test_brief_moods_weight_the_palette_and_keep_its_spread():
    meta = house_style.entries("palettes")

    def picks(brief):
        return Counter(guide(brief, seed=seed)["direction"]["direction"]["palette"] for seed in range(60))

    coffee, neutral = picks("a poster for a coffee shop opening"), picks("a poster for a shop opening")

    def warm(counter):
        return sum(n for name, n in counter.items() if WARM & set(meta[name].get("mood", [])))

    assert warm(coffee) > warm(neutral) + 6
    # Weighting, not filtering: the spread of palettes stays wide.
    assert len(coffee) >= 0.8 * len(neutral)


def test_the_direction_reports_the_moods_and_a_motif_without_adding_layers():
    result = guide("a poster for a winter coffee night market", seed=4)
    direction = result["direction"]["direction"]
    assert direction["mood_source"] == "brief"
    assert {"coffee", "winter", "night market"} <= set(direction["mood_words"])
    assert "warm" in direction["brief_moods"]
    assert direction["motif_suggestion"]["theme"] == result["motifs"][0]["theme"]
    # The motif is a suggestion: layout-apply never sees the brief's keys, and the rolled decoration shape stays.
    assert not set(BRIEF_KEYS) & set(result["direction"]["operation"]["direction"])
    assert direction["motif"] in ("none", "rule", "ellipse", "rectangle")
    assert "mood_source" not in guide("a poster for our annual meeting", seed=4)["direction"]["direction"]
