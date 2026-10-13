"""Key-value lists, the chart value legend that shares their geometry, section-header and footer-rule clearance,
rolled pill and date-highlight details, and new charts inside the safe area."""

import pytest

from vixl.containers import measure
from vixl.craft import spacing_unit
from vixl.errors import VixlError
from vixl.layouts import DENSITY_SPACING
from vixl.project import Project
from vixl.typefaces import roll
from vixl.variety import document_defaults

DRINKS = [{"label": "Drip", "value": 15900}, {"label": "Espresso", "value": 11960},
          {"label": "Cold brew", "value": 2510}, {"label": "Tea", "value": 5260}]


def kids(p, name):
    ident = p.layer(name)["id"]
    return {layer["kv_part"]: layer for layer in p.state["layers"] if layer.get("parent") == ident}


def right(layer):
    return layer["x"] + layer["width"]


def test_key_value_list_aligns_columns_on_shared_edges_with_rules_between_rows():
    p = Project(800, 600, "#ffffff")
    p.apply({"type": "key-value-list", "name": "shares", "x": 40, "y": 40, "width": 360, "rows": DRINKS,
             "shares": "auto", "number_format": "#,##0"})
    parts = kids(p, "shares")
    labels = [parts[f"label-{i}"] for i in range(4)]
    values = [parts[f"value-{i}"] for i in range(4)]
    shares = [parts[f"share-{i}"] for i in range(4)]
    assert [x["text"] for x in values] == ["15,900", "11,960", "2,510", "5,260"]
    assert [x["text"] for x in shares] == ["44.6%", "33.6%", "7.0%", "14.8%"]
    assert {x["x"] for x in labels} == {0}
    assert len({right(x) for x in values}) == 1 and {right(x) for x in shares} == {360}
    rules = sorted((x for key, x in parts.items() if key.startswith("rule-")), key=lambda x: x["y"])
    assert len(rules) == 3 and all(rule["width"] == 360 for rule in rules)
    summary = p.layer("shares")["key_values"]["summary"]
    # One rhythm: every single-line row is as tall as the others, padded by the spacing unit.
    assert len(set(summary["row_heights"])) == 1 and summary["unit"] == 8
    for rule, below in zip(rules, labels[1:]):
        assert below["y"] - (rule["y"] + rule["height"]) >= summary["unit"] - 1
    assert p.layer("shares")["width"] == 360


def test_key_value_list_restyles_in_place_and_takes_items_text():
    p = Project(800, 600, "#ffffff")
    p.apply({"type": "key-value-list", "name": "list", "items": "Rent | $1,200\nFood | $420 | 18%"})
    ids = {key: layer["id"] for key, layer in kids(p, "list").items()}
    assert kids(p, "list")["share-1"]["text"] == "18%" and "share-0" not in ids
    p.apply({"type": "key-value-list", "target": "list", "width": 500, "rules": False, "font_size": 20})
    after = kids(p, "list")
    assert not any(key.startswith("rule-") for key in after)
    assert all(after[key]["id"] == ident for key, ident in ids.items() if not key.startswith("rule-"))
    assert right(after["share-1"]) == 500 and after["label-0"]["size"] == 20
    with pytest.raises(VixlError, match="label | value | share"):
        p.apply({"type": "key-value-list", "items": "a | b | c | d"})
    with pytest.raises(VixlError, match="needs rows"):
        p.apply({"type": "key-value-list", "name": "empty"})


def test_chart_value_legend_is_a_key_value_list_with_names_values_and_shares():
    p = Project(1000, 700, "#ffffff")
    p.apply({"type": "chart", "name": "share", "kind": "donut", "x": 0, "y": 0, "width": 1000, "height": 700,
             "categories": [r["label"] for r in DRINKS], "series": [{"name": "Cups", "values": [r["value"] for r in DRINKS]}],
             "legend_values": True})
    layers = {layer["chart_part"]: layer for layer in p.state["layers"] if "chart_part" in layer}
    assert [layers[f"legend-share-{i}"]["text"] for i in range(4)] == ["44.6%", "33.6%", "7.0%", "14.8%"]
    assert [layers[f"legend-value-{i}"]["text"] for i in range(4)] == ["15,900", "11,960", "2,510", "5,260"]
    assert len({right(layers[f"legend-value-{i}"]) for i in range(4)}) == 1
    assert sum(key.startswith("legend-rule-") for key in layers) == 3
    # The list pairs names with numbers and shares, so automatic labels around the ring are not repeated.
    assert not any(key.startswith("slice-label-") for key in layers)
    # The same rows as a standalone list have the same geometry.
    q = Project(1000, 700, "#ffffff")
    q.apply({"type": "key-value-list", "name": "kv", "rows": [[r["label"], f"{r['value']:,}"] for r in DRINKS],
             "shares": "auto", "font_size": layers["legend-label-0"]["size"], "colors": ["#000000"]})
    kv = kids(q, "kv")
    origin = layers["legend-swatch-0"]
    for i in range(4):
        for key in ("label", "value", "share"):
            chart_part, own = layers[f"legend-{key}-{i}"], kv[f"{key}-{i}"]
            assert (chart_part["x"] - origin["x"], chart_part["y"] - layers["legend-label-0"]["y"]) == \
                   (own["x"], own["y"] - kv["label-0"]["y"])


def test_forced_value_labels_still_show_around_the_ring():
    p = Project(1000, 700, "#ffffff")
    p.apply({"type": "chart", "name": "pie", "kind": "pie", "categories": ["a", "b"], "legend_values": True,
             "value_labels": "percent", "series": [{"name": "s", "values": [1, 3]}]})
    assert any(layer.get("chart_part", "").startswith("slice-label-") for layer in p.state["layers"])


def test_key_value_list_container_fills_and_reflows():
    p = Project(1080, 1080, "#ffffff")
    p.apply({"type": "palette-apply", "name": "slate"})
    p.apply({"type": "container-place", "name": "shares", "resource": "key-value-list", "width": 600, "height": 400,
             "variables": {"title": "Share", "items": "Drip | 15,900 | 44.6%\nTea | 5,260 | 14.8%"}})
    group = p.layer("shares/items")
    assert group["key_values"]["rows"][1] == {"label": "Tea", "value": "5,260", "share": "14.8%"}
    assert group["width"] == round(0.86 * 600)
    p.apply({"type": "resize", "target": "shares", "width": 400, "height": 260})
    assert p.layer("shares/items")["width"] == round(0.86 * 400)
    p.apply({"type": "container-fill", "target": "shares", "variables": {"items": "A | 1\nB | 2\nC | 3"}})
    assert len(p.layer("shares/items")["key_values"]["rows"]) == 3
    assert measure(p)["passed"]


def test_a_new_chart_starts_inside_the_safe_area():
    p = Project.sized("instagram-post", seed=5, workspace_fonts=False)
    assert p.state["canvas"].get("safe")
    p.apply({"type": "chart", "name": "cups", "kind": "bar", "title": "Cups sold", "categories": ["Jan", "Feb", "Mar"],
             "series": [{"name": "Cups", "values": [1200, 1100, 1250]}, {"name": "Tea", "values": [300, 320, 350]}]})
    report = p.check(checks=["safe_area", "bounds"])
    assert not [issue for issue in report["issues"] if issue["check"] == "safe_area"], report["issues"]
    group = p.layer("cups")
    assert group["x"] > p.state["canvas"]["safe"] and group["width"] < p.state["canvas"]["width"]
    # Explicit geometry is kept as given.
    p.apply({"type": "chart", "name": "full", "x": 0, "y": 0, "width": 1080, "height": 1080, "categories": ["a"],
             "series": [{"name": "s", "values": [1]}]})
    assert (p.layer("full")["x"], p.layer("full")["width"]) == (0, 1080)


def test_rolled_details_are_seeded_and_leave_the_rest_of_the_roll_alone():
    for seed in range(40):
        new = roll(seed, purpose="social", canvas=(1080, 1080))["direction"]
        assert new["cta"] in ("pill", "button") and new["date"] in ("highlight", "plain")
        assert roll(seed, purpose="social", canvas=(1080, 1080))["direction"]["cta"] == new["cta"]
    rolled = [roll(seed, purpose="social", canvas=(1080, 1080))["direction"] for seed in range(80)]
    assert {d["cta"] for d in rolled} == {"pill", "button"} and {d["date"] for d in rolled} == {"highlight", "plain"}
    assert roll(3, locks={"cta": "button", "date": "plain"})["direction"]["cta"] == "button"


COPY = {"title": "Open mic night", "label": "Fri · November 19", "subtitle": "Sign up at the bar from 7 pm",
        "cta": "Save a spot"}


def test_direction_sets_a_pill_call_to_action_and_a_highlighted_date_line():
    p = Project(1080, 1350, "#ffffff")
    p.apply({"type": "layout-apply", "name": "centered-axis", "seed": 7, "palette": "coffee", **COPY,
             "direction": {"cta": "pill", "date": "highlight"}})
    button, label, highlight = p.layer("cta-button"), p.layer("label"), p.layer("label-highlight")
    assert button["shape"] == "rounded-rectangle" and button["radius"] == pytest.approx(button["height"] / 2, abs=1)
    assert label["color"] == "@on-accent" and highlight["fill"] == "@accent"
    assert highlight["x"] <= label["x"] and right(highlight) >= right(label)
    assert highlight["y"] <= label["y"] and highlight["y"] + highlight["height"] >= label["y"] + label["height"]
    report = p.check(checks=["overlap", "contrast", "safe_area"])
    assert not report["issues"], report["issues"]
    # A plain direction keeps the corner-styled button and a plain date.
    q = Project(1080, 1350, "#ffffff")
    q.apply({"type": "layout-apply", "name": "centered-axis", "seed": 7, "palette": "coffee", **COPY,
             "direction": {}})
    assert q.layer("cta-button")["shape"] == "rectangle" and q.find_layer("label-highlight") is None
    with pytest.raises(VixlError, match="direction.cta"):
        q.apply({"type": "layout-apply", "name": "centered-axis", "seed": 7, "replace": True, **COPY,
                 "direction": {"cta": "round"}})


def test_only_a_date_line_is_highlighted():
    p = Project(1080, 1350, "#ffffff")
    p.apply({"type": "layout-apply", "name": "centered-axis", "seed": 7, "palette": "coffee",
             **{**COPY, "label": "New season"}, "direction": {"date": "highlight"}})
    assert p.find_layer("label-highlight") is None


def test_footer_rule_keeps_a_spacing_unit_above_the_copy():
    long = "One supporting sentence that explains why it matters, " * 3

    def gap():
        p = Project(1200, 480, "#ffffff")
        # Copy that fills the banner, so the composition would otherwise end on the footer rule.
        p.apply({"type": "layout-apply", "name": "quiet-invitation", "seed": 2, "palette": "slate", "density": "dense",
                 "title": "A headline that wraps onto two lines here", "subtitle": long, "body": long,
                 "caption": "example.com", "label": "Notice", "cta": "Go now"})
        record = p.state["layout"]
        unit = spacing_unit(record["base_size"] * DENSITY_SPACING[record["density"]])
        copy = [layer for layer in p.state["layers"] if layer["type"] == "text" or layer["name"].endswith("-button")]
        return p.layer("quiet-footer")["y"] - max(layer["y"] + layer["height"] for layer in copy), unit

    clear, unit = gap()
    assert clear >= unit - 1  # one unit, give or take the pixel rounding of the rule


def test_section_header_rule_clears_the_next_row_at_any_height():
    def place():
        p = Project(1080, 1080, "#ffffff")
        document_defaults(p, seed=1)
        # A large body size makes one spacing unit larger than the room the frame leaves under the rule.
        p.apply([{"type": "palette-apply", "name": "slate"}, {"type": "style-define", "name": "body", "kind": "character", "settings": {"size": 80}},
                 {"type": "container-place", "name": "head", "resource": "section-header", "width": 480, "height": 200,
                  "variables": {"eyebrow": "Menu", "title": "Coffee"}}])
        rule = p.layer("head/rule")
        return 200 - (rule["y"] + rule["height"])

    assert place() >= 40  # one unit: half the 80 px body
