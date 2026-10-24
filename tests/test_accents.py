"""The accent count of a roll (#404): one accent usually, two often, none or three rarely; accent-2 and accent-3
with their text variants; layouts that spread the accent-bearing layers over them; accent_unused for each."""

from collections import Counter
import random

import pytest

from vixl import Project, house_style
from vixl.colors import contrast_ratio, parse, srgb_to_oklab, to_polar
from vixl.errors import VixlError
from vixl.layouts import accent_plan, assign_roles
from vixl.palette_roles import extra_accents, hue_distance
from vixl.typefaces import roll, roll_document

ACCENT_KEYS = ("accent_count", "accent_representation")
PAINT = ("fill", "stroke", "color")
COPY = {"title": "Summer Night Market", "subtitle": "Food, music and late shopping", "label": "June 21",
        "cta": "Free entry"}


def ratio(a, b):
    return contrast_ratio(parse(a)[:3], parse(b)[:3])


def hue(color):
    return to_polar(srgb_to_oklab(parse(color)[:3]))[2]


def drawn_roles(p):
    """The accent fill roles a visible layer of ``p`` takes (a text colour in accent-N-text counts for accent-N)."""
    found = set()
    for layer in p.state["layers"]:
        for key in PAINT:
            value = layer.get(key)
            if isinstance(value, str) and value.startswith("@accent"):
                found.add(value[1:].removesuffix("-text"))
    return found


@pytest.fixture(scope="module")
def fonts():
    from evals.house_style import offline_fonts

    with offline_fonts():
        yield


def rolled(tmp_path, seed, count, representation="skewed", size="instagram-post", purpose="poster", copy=COPY):
    p = Project.sized(size)
    result = roll_document(p, workspace=tmp_path, seed=seed, purpose=purpose, apply=True, slots=copy,
                           locks={"accents": count, "accent_representation": representation})
    return p, result


# --- the roll -----------------------------------------------------------------------------------------------------


def test_accent_count_follows_the_configured_weights():
    weights = house_style.accents()["count_weights"]
    rolls = [roll(seed)["direction"] for seed in range(800)]
    counts = Counter(direction["accent_count"] for direction in rolls)
    for count, weight in weights.items():
        assert abs(counts[int(count)] / len(rolls) - weight) < 0.04, (count, counts)
    shares = Counter(direction["accent_representation"] for direction in rolls)
    assert abs(shares["skewed"] / len(rolls) - 0.5) < 0.06
    # A purpose may override the weights: a mark rolls one or two colours, never three.
    marks = Counter(roll(seed, purpose="logo")["direction"]["accent_count"] for seed in range(300))
    assert set(marks) <= {0, 1, 2} and marks[1] > marks[0] + marks[2]


def test_the_accent_roll_has_its_own_stream_so_seeds_keep_what_they_rolled():
    for seed in range(40):
        free, locked = roll(seed)["direction"], roll(seed, locks={"accents": 1})["direction"]
        assert {k: v for k, v in free.items() if k not in ACCENT_KEYS} == {
            k: v for k, v in locked.items() if k not in ACCENT_KEYS}
        assert locked["accent_count"] == 1


def test_locks_take_accents_as_the_short_name_for_accent_count():
    assert roll(3, locks={"accents": 3})["direction"]["accent_count"] == 3
    assert roll(3, locks={"accent_count": 0})["direction"]["accent_count"] == 0
    assert roll(3, locks={"accent_representation": "equal"})["direction"]["accent_representation"] == "equal"
    for bad in ({"accents": 4}, {"accents": "two"}, {"accent_representation": "loud"},
                {"accents": 2, "accent_count": 3}):
        with pytest.raises(VixlError):
            roll(3, locks=bad)
    # The count travels to layout-apply in the direction; it is not a layout-apply field of its own.
    operation = roll(3, locks={"accents": 2})["operation"]
    assert operation["direction"]["accent_count"] == 2 and "accent_count" not in operation


# --- the roles ------------------------------------------------------------------------------------------------------


def test_extra_accents_come_from_the_palette_when_its_hue_is_distinct_else_by_rotation():
    # cobalt-tangerine has an orange far from its blue accent; chalk-indigo only tints of its indigo.
    two = assign_roles({"palette": "cobalt-tangerine", "mode": "light", "direction": {"accent_count": 2}},
                       random.Random(0))
    sources = {entry["role"]: entry for entry in two["_explain"]}
    # The orange is darkened until it reads 3:1 on the light background, so its source is derived from it.
    assert sources["accent-2"]["reason"].startswith("next most colorful palette color") and "3:1" in sources[
        "accent-2"]["reason"]
    assert hue_distance(hue(two["accent-2"]), hue("#ff7a1a")) < 10
    three = assign_roles({"palette": "chalk-indigo", "mode": "light", "direction": {"accent_count": 3}},
                         random.Random(0))
    explained = {entry["role"]: entry for entry in three["_explain"]}
    assert explained["accent-2"]["source"] == "derived" and "turned" in explained["accent-2"]["reason"]
    hues = [hue(three[role]) for role in ("accent", "accent-2", "accent-3")]
    assert min(hue_distance(a, b) for i, a in enumerate(hues) for b in hues[i + 1:]) >= 25
    indigo, tint, orange = parse("#5267aa"), parse("#9faed5"), parse("#e07a2f")
    assert extra_accents([tint], indigo, 3, derive=False) == []
    assert [source for _, source in extra_accents([tint, orange], indigo, 3)] == ["palette", "derived"]
    # The first accent is what a one-accent roll gets.
    one = assign_roles({"palette": "chalk-indigo", "mode": "light"}, random.Random(0))
    assert all(one[role] == three[role] for role in ("background", "ink", "accent", "accent-text", "on-accent"))


@pytest.mark.parametrize("name", sorted(n for n, m in house_style.entries("palettes").items() if m["tier"] != "explicit"))
def test_every_rollable_palette_gives_readable_extra_accents(name):
    fill, text = house_style.craft("contrast")["fill"], house_style.craft("contrast")["text"]
    for mode in house_style.palette_modes(name):
        roles = assign_roles({"palette": name, "mode": mode, "direction": {"accent_count": 3}}, random.Random(0))
        for role in ("accent-2", "accent-3"):
            assert min(ratio(roles[role], roles["background"]), ratio(roles[role], roles["surface"])) >= fill, (name, mode)
            assert min(ratio(roles[f"{role}-text"], roles["background"]),
                       ratio(roles[f"{role}-text"], roles["surface"])) >= text, (name, mode, role)


def test_fixed_colours_get_no_invented_accent():
    # A brand (colors) fixes the roles: a second accent comes from the palette or colors, never by rotation.
    reds = ["#fbf3e4", "#f2c9b8", "#2a0a10", "#c8102e", "#7a0a1c"]
    given = {"accent": "#c8102e"}
    roles = assign_roles({"palette": reds, "mode": "light", "colors": given, "direction": {"accent_count": 2}},
                         random.Random(0))
    assert "accent-2" not in roles
    roles = assign_roles({"palette": reds, "mode": "light", "direction": {"accent_count": 2},
                          "colors": {**given, "accent-2": "#0b6e4f"}}, random.Random(0))
    assert roles["accent-2"] == "#0b6e4f" and ratio(roles["accent-2-text"], roles["background"]) >= 4.5
    p = Project(1080, 1080)
    p.apply({"type": "layout-apply", "name": "hero-statement", "palette": reds, "colors": given, "seed": 4,
             "direction": {"accent_count": 2}, **COPY})
    record = p.state["layout"]["accents"]
    assert record["drawn"] == ["accent"] and "no further accent" in record["note"]
    assert "accent-2" not in p.state["swatches"]


def test_no_accent_takes_ink_and_muted():
    roles = assign_roles({"palette": "cobalt-tangerine", "mode": "light", "direction": {"accent_count": 0}},
                         random.Random(0))
    assert roles["accent"] == roles["ink"] and roles["accent-text"] == roles["muted"]
    assert ratio(roles["on-accent"], roles["accent"]) >= 4.5
    reasons = {entry["role"]: entry["reason"] for entry in roles["_explain"]}
    assert "accent_count 0" in reasons["accent"]


# --- layouts -------------------------------------------------------------------------------------------------------


def test_accent_plan_follows_the_shares_and_covers_every_accent():
    sizes = list(range(10, 0, -1))
    skewed = accent_plan(0, sizes, [0.7, 0.3], "skewed")
    assert Counter(skewed) == {0: 7, 1: 3} and skewed[:7] == [0] * 7  # the first accent on the largest
    equal = accent_plan(0, sizes, [0.5, 0.5], "equal")
    assert Counter(equal) == {0: 5, 1: 5} and equal[:4] == [0, 1, 0, 1]
    three = accent_plan(2, sizes, [0.6, 0.25, 0.15], "skewed")
    counts = Counter(three)
    counts[0] += 2  # the anchored elements keep the first accent
    assert all(abs(counts[role] / 12 - share) <= 0.1 for role, share in enumerate([0.6, 0.25, 0.15])), counts
    # Too few elements for the shares: each accent still gets one.
    assert sorted(accent_plan(1, [5, 1], [0.6, 0.25, 0.15], "skewed")) == [1, 2]
    assert sorted(accent_plan(0, [3, 2, 1], [0.6, 0.25, 0.15], "equal")) == [0, 1, 2]


@pytest.mark.parametrize("count,representation", [(2, "skewed"), (2, "equal"), (3, "skewed"), (3, "equal")])
def test_two_or_three_accents_are_drawn_readable_and_checked(fonts, tmp_path, count, representation):
    seen = 0
    for seed in (11, 12, 13, 14):
        p, result = rolled(tmp_path, seed, count, representation)
        record = p.state["layout"]["accents"]
        assert record["count"] == count and record["representation"] == representation
        drawn = drawn_roles(p)
        # Every accent the layout reports drawn is on the canvas, with its swatches; none other is defined.
        assert set(record["drawn"]) == drawn, (result["direction"]["layout"], record, drawn)
        assert {name for name in p.state["swatches"] if name.startswith("accent-") and name != "accent-text"} == {
            name for role in record["drawn"][1:] for name in (role, f"{role}-text")}
        if len(record["drawn"]) < count:
            assert "not drawn" in record["note"]
        seen += len(record["drawn"]) == count
        issues = p.check()["issues"]
        assert not [x for x in issues if x.get("action") == "fix"], result["direction"]["layout"]
        assert not [x for x in issues if x.get("code") == "accent_unused"]
        swatches = p.state["swatches"]
        for role in record["drawn"][1:]:
            assert ratio(swatches[f"{role}-text"], swatches["background"]) >= 4.5
            assert ratio(swatches[role], swatches["background"]) >= 3
        # The first accent is the one a one-accent roll of the seed draws.
        single, _ = rolled(tmp_path, seed, 1)
        assert single.state["swatches"]["accent"] == p.state["swatches"]["accent"]
    assert seen >= 3


def test_a_shape_with_text_on_it_keeps_the_first_accent(fonts, tmp_path):
    for seed in range(20, 32):
        p, _ = rolled(tmp_path, seed, 3, "equal")
        for layer in p.state["layers"]:
            if layer["name"].endswith(("cta-button", "-highlight")):
                assert layer.get("fill") == "@accent", layer["name"]


def test_zero_accents_draw_in_ink_and_ask_for_no_accent(fonts, tmp_path):
    p, _ = rolled(tmp_path, 5, 0)
    swatches = p.state["swatches"]
    assert swatches["accent"] == swatches["ink"] and swatches["accent-text"] == swatches["muted"]
    assert p.state["layout"]["accents"] == {"count": 0, "representation": "skewed"}
    assert not [x for x in p.check()["issues"] if x.get("code") == "accent_unused" or x.get("action") == "fix"]


def test_an_undrawn_second_accent_is_reported(fonts, tmp_path):
    p, _ = rolled(tmp_path, 12, 2)
    assert "accent-2" in p.state["layout"]["accents"]["drawn"]
    for layer in p.state["layers"]:
        for key in PAINT:
            if layer.get(key) in ("@accent-2", "@accent-2-text"):
                layer[key] = "@ink"
    codes =[x for x in p.check(checks=["composition"])["issues"] if x.get("code") == "accent_unused"]
    assert [x["values"]["role"] for x in codes] == ["accent-2"]
    assert "@accent-2" in codes[0]["message"]


def test_house_style_off_and_explicit_layouts_keep_one_accent():
    p = Project.new(width=1080, height=1080, purpose="poster", house_style="off")
    assert "accent_count" not in p.state["design_defaults"]["direction"]
    p.apply({"type": "layout-apply", "name": "hero-statement", **COPY})
    assert "accents" not in p.state["layout"]
    assert not [name for name in p.state["swatches"] if name in ("accent-2", "accent-3")]


def test_charts_draw_series_in_the_accents_a_layout_drew(fonts, tmp_path):
    p, _ = rolled(tmp_path, 12, 2)
    assert "accent-2" in p.state["swatches"]
    p.apply({"type": "chart", "name": "sales", "kind": "bar", "x": 100, "y": 600, "width": 600, "height": 300,
             "categories": ["A", "B"], "series": [{"name": "2025", "values": [1, 2]}, {"name": "2026", "values": [2, 3]}]})
    fills = {layer.get("fill") for layer in p.state["layers"] if layer["name"].startswith("sales/")}
    assert {"@accent", "@accent-2"} <= fills
