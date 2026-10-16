"""The composition check family (craft plan 2a and 2c): dead bands, margin drift, uneven rhythm, crowding and
clumped scatter as review findings, on by default and failing the final profile unless waived."""

from vixl import Project
from vixl.checks import CHECKS
from vixl.composition import CODES, THRESHOLDS


def doc(*ops, size=(1000, 1000), body=20):
    p = Project(*size, "white")
    p.apply([{"type": "type-scale", "base": body}, *ops])  # body 20: a 10 px spacing unit
    return p


def found(p, **options):
    report = p.check(checks=["composition"], **options)
    return [x for x in report["issues"] if x["check"] == "composition"]


def codes(p):
    return sorted(x["code"] for x in found(p))


def text(name, x, y, size=24, **extra):
    return {"type": "text", "name": name, "text": name.title(), "x": x, "y": y, "size": size, "color": "#111111",
            **extra}


def panel(name, y, height=150, x=100, width=800):
    return {"type": "shape", "name": name, "shape": "rectangle", "x": x, "y": y, "width": width, "height": height,
            "fill": "#335577"}


def test_composition_is_a_default_family_of_review_findings():
    assert "composition" in CHECKS
    p = doc(text("title", 60, 60), text("subtitle", 72, 100))
    (finding,) = [x for x in p.check()["issues"] if x["check"] == "composition"]
    assert finding["action"] == "review" and finding["severity"] == "warning"
    assert finding["code"] in CODES and finding["rule"] == "composition.margin_drift"
    # Machine-usable for repair: layers, a region, what was measured against which threshold.
    assert set(finding["layer_ids"]) == {p.layer("title")["id"], p.layer("subtitle")["id"]}
    assert finding["region"] and len(finding["region"]) == 4
    assert finding["measured"] == {"actual": 12, "expected": 0, "unit": "px"}
    assert finding["values"]["margin"] == 60 and finding["values"]["edge"] == 72
    assert finding["threshold"] == {"tolerance_px": THRESHOLDS["drift_tolerance_px"], "window_px": 20}
    assert finding["spacing_unit"] == 10
    # Review findings do not fail the plain check.
    assert p.check(checks=["composition"])["passed"]


def card(name, y, height=150):
    """A panel with a line of type in it: dead bands are judged in layouts of type, not in pictures."""
    return [panel(name, y, height), {**text(f"{name}-label", 120, y + 20), "color": "#ffffff"}]


def test_dead_band_between_blocks_and_its_fix():
    stacked = [*card("a", 50), *card("b", 230), *card("c", 410)]
    holed = doc(*stacked, *card("d", 800))
    (band,) = found(holed)
    assert band["code"] == "dead_band" and band["values"]["height"] == 240
    assert band["region"][1] == 560 and band["layers"] == ["c", "d"]
    assert codes(doc(*stacked, *card("d", 590), *card("e", 770, 180))) == []


def test_sparse_frames_pictures_and_decoration_do_not_make_dead_bands():
    # A title and a line on an open page: the space is the design.
    assert codes(doc(*card("a", 50, 100), *card("b", 800, 100))) == []
    # A picture without type is not judged for bands.
    assert codes(doc(panel("a", 50), panel("b", 230), panel("c", 410), panel("d", 800))) == []
    # Space closed off by a marked decoration is that decoration's setting.
    marked = doc(*card("a", 50), *card("b", 230), *card("c", 410), panel("d", 800),
                 {"type": "layer-intent", "target": "d", "role": "decoration"})
    assert codes(marked) == []


def test_margin_drift_flags_near_misses_only():
    assert codes(doc(text("title", 60, 60), text("subtitle", 60, 100))) == []
    # Further apart than two spacing units is a deliberate indent, not drift.
    assert codes(doc(text("title", 60, 60), text("subtitle", 90, 100))) == []
    # A list hangs its markers, and a label after an icon follows the icon.
    assert codes(doc(text("title", 60, 60), {**text("item", 72, 100), "text": "• First item"})) == []
    assert codes(doc(text("title", 60, 60), text("label", 76, 100),
                     {"type": "shape", "name": "dot", "shape": "ellipse", "x": 60, "y": 104, "width": 10,
                      "height": 10, "fill": "#111111"})) == []
    # Text inside a card is aligned to the card, not to the page margin.
    assert codes(doc(text("title", 60, 60), panel("card", 100, 120, 60, 400), text("label", 76, 120))) == []
    # Right-aligned text drifts against the right edge of a rule.
    footer = doc({"type": "shape", "name": "rule", "shape": "rectangle", "x": 60, "y": 900, "width": 880,
                  "height": 2, "fill": "#111111"},
                 {"type": "text", "name": "folio", "text": "4 / 6", "x": 820, "y": 920, "size": 18,
                  "color": "#111111", "align": "right"},
                 {"type": "text-layout", "target": "folio", "width": 104})
    (drift,) = found(footer)
    assert drift["code"] == "margin_drift" and drift["values"]["axis"] == "right"


def test_marked_decoration_and_waivers_silence_a_finding():
    decorated = doc(text("title", 60, 60), text("subtitle", 72, 100),
                    {"type": "layer-intent", "target": "subtitle", "role": "decoration"})
    assert codes(decorated) == []
    waived = doc(text("title", 60, 60), text("subtitle", 72, 100),
                 {"type": "layer-intent", "target": "subtitle",
                  "waive": [{"check": "composition", "reason": "optical indent for the quote mark"}]})
    (finding,) = found(waived)
    assert finding["action"] == "informational" and finding["waived"]["reason"].startswith("optical")


def test_uneven_rhythm_is_a_group_split_apart():
    def name_block(g1, g2):
        return doc(text("first", 100, 100, 80), text("last", 100, 100 + 62 + g1, 60),
                   text("company", 100, 100 + 62 + g1 + 46 + g2, 30))

    (finding,) = found(name_block(60, 12))
    assert finding["code"] == "uneven_rhythm" and finding["values"]["gaps"][0] > finding["values"]["gaps"][1]
    assert finding["layers"] == ["first", "last", "company"]
    # The middle line closer to the line it belongs with is the intended grouping.
    assert codes(name_block(12, 40)) == []
    # A capitalised kicker sits tight to what it labels.
    kicker = doc({**text("kicker", 100, 100, 18), "text": "SATURDAY"}, text("title", 100, 124, 60),
                 text("subtitle", 100, 230, 28))
    assert codes(kicker) == []


def test_crowding_under_a_rule_and_its_fix():
    def menu(gap):
        return doc(text("heading", 100, 100, 40),
                   {"type": "shape", "name": "rule", "shape": "rectangle", "x": 100, "y": 150, "width": 600,
                    "height": 4, "fill": "#cc8800"},
                   text("item", 100, 154 + gap, 24))

    (finding,) = found(menu(2))
    assert finding["code"] == "crowding" and finding["layers"] == ["rule", "item"]
    assert finding["threshold"] == {"min_gap_px": 5}
    assert codes(menu(12)) == []


def scatter(points):
    p = doc(*[{"type": "shape", "name": f"m{i}", "shape": "ellipse", "x": x, "y": y, "width": 60, "height": 60,
               "fill": "#335577"} for i, (x, y) in enumerate(points)], size=(1024, 1024))
    p.apply({"type": "group", "name": "tile", "targets": [f"m{i}" for i in range(len(points))]})
    p.layer("tile")["pattern_scatter"] = {"width": 1024, "height": 1024, "seed": 1, "count": len(points)}
    return p


def test_clumped_scatter_against_an_even_one():
    clumped = scatter([(20 + 70 * (i % 4), 20 + 70 * (i // 4)) for i in range(16)])
    (finding,) = found(clumped)
    assert finding["code"] == "clumped_scatter" and finding["values"]["coverage_cv"] > THRESHOLDS["scatter_cv"]
    even = scatter([(64 + 256 * (i % 4), 64 + 256 * (i // 4)) for i in range(16)])
    assert codes(even) == []


def test_pattern_scatter_output_is_not_clumped():
    p = Project(1024, 1024, "white")
    p.apply([{"type": "shape", "name": "m", "shape": "ellipse", "x": 0, "y": 0, "width": 80, "height": 120,
              "fill": "#123456"},
             {"type": "pattern-scatter", "name": "tile", "source": ["m"], "width": 1024, "height": 1024,
              "count": 24, "seed": 3}])
    assert "clumped_scatter" not in codes(p)


def test_final_profile_fails_on_composition_until_waived(tmp_path):
    p = Project(400, 300, "white", workspace=tmp_path)
    p.apply([{"type": "type-scale", "base": 20},
             text("title", 40, 40), text("subtitle", 52, 80),
             {"type": "waiver", "check": "fonts", "reason": "proofing font until the brand fonts arrive"}])
    assert p.check()["passed"] and p.check(profile="draft")["passed"]
    final = p.check(profile="final")
    assert not final["passed"] and "composition" in final["checked"]["checks"]
    assert [final["issues"][i]["check"] for i in final["profile"]["failing"]] == ["composition"]
    p.apply({"type": "waiver", "check": "composition", "reason": "the subtitle is indented on purpose"})
    assert p.check(profile="final")["passed"]


def test_final_profile_keeps_composition_when_a_workspace_narrows_the_checks(tmp_path):
    import json

    (tmp_path / ".vixl-checks.json").write_text(json.dumps({"profiles": {"final": {"checks": ["bounds"]}}}))
    p = Project(400, 300, "white", workspace=tmp_path)
    p.apply([text("title", 40, 40), text("subtitle", 52, 80)])
    assert "composition" in p.check(profile="final")["checked"]["checks"]


def test_check_command_line_and_mcp_select_the_family(tmp_path):
    import asyncio
    import json

    from vixl.cli import main
    from vixl.interfaces import Session
    from vixl.mcp_tools import build_server

    path = tmp_path / "a.vixl"
    doc(text("title", 60, 60), text("subtitle", 72, 100)).save(path)
    assert main(["-p", str(path), "check", "--checks", "composition"]) == 0
    assert main(["-p", str(path), "check", "--checks", "composition", "--profile", "final", "--strict"]) != 0

    async def call():
        server = build_server(Session(workspace=tmp_path))
        result = await server.call_tool("vixl_check", {"checks": ["composition"], "document": "a.vixl"})
        content = result[0] if isinstance(result, tuple) else result
        return json.loads(content[0].text)

    report = asyncio.run(call())
    assert [x["code"] for x in report["issues"]] == ["margin_drift"]


def test_text_in_a_chip_aligns_by_the_chip():
    """A highlighted date line or a pill: the chip's edge sits on the column, the text inside it is padding."""
    chip = {"type": "shape", "name": "date-highlight", "shape": "rectangle", "x": 60, "y": 62, "width": 110,
            "height": 40, "fill": "#ffcc00"}  # Under the share of the canvas that makes a card.
    p = doc(chip, text("date", 72, 70), text("headline", 60, 140, size=48), text("subtitle", 60, 220))
    assert "margin_drift" not in codes(p)
    # The same inset without the chip is drift.
    assert "margin_drift" in codes(doc(text("date", 72, 70), text("headline", 60, 140, size=48),
                                       text("subtitle", 60, 220)))


# The craft-check backtest (2026-10-13): what the eight pieces made through Vixl showed the family missing.


def test_drift_of_two_pixels_or_less_is_not_reported():
    assert not found(doc(text("title", 60, 60), text("subtitle", 62, 100)))
    assert codes(doc(text("title", 60, 60), text("subtitle", 63, 100))) == ["margin_drift"]


def test_signed_values_and_shares_beside_their_data_are_not_margins():
    base = [text("header", 800, 60), text("stat", 800, 300), text("caption", 800, 400)]
    assert codes(doc(*base, {**text("delta", 808, 180), "text": "−9"})) == []
    assert codes(doc(*base, {**text("share", 808, 180), "text": "38%"})) == []
    assert codes(doc(*base, {**text("label", 808, 180), "text": "Ferry"})) == ["margin_drift"]


def lines(*names, start=430, step=60):
    return [text(name, 100, start + i * step) for i, name in enumerate(names)]


def test_faint_layers_and_edge_to_edge_gradient_fills_do_not_close_a_band():
    blocks = [panel("art", 60, 460), *lines("one", "two", "three", start=740, step=50)]
    assert any(x["code"] == "dead_band" and "art" in x["layers"] for x in found(doc(*blocks)))
    smoke = {**panel("smoke", 540, 160), "opacity": 0.15}
    water = {"type": "gradient", "name": "water", "x": 0, "y": 380, "width": 1000, "height": 620,
             "start": "#223344", "end": "#556677"}
    assert any(x["code"] == "dead_band" and "art" in x["layers"] for x in found(doc(*blocks, smoke)))
    assert any(x["code"] == "dead_band" and "art" in x["layers"] for x in found(doc(water, *blocks)))
    # Content drawn in the band does close it.
    assert not any("art" in x["layers"] for x in found(doc(*blocks, panel("photo", 540, 160))))


def test_text_is_spaced_by_its_glyphs_not_its_line_box():
    # A title in a tall text box: the box reaches down to the lines below, its letters end far above them.
    p = doc(panel("art", 60, 440), text("title", 100, 520, size=96), *lines("one", "two", start=900, step=40))
    p.apply({"type": "text-layout", "target": "title", "width": 800, "height": 370})
    assert p.layer("title")["height"] == 370
    assert any(x["code"] == "dead_band" and "title" in x["layers"] and x["region"][1] < 700 for x in found(p))


def test_an_edge_band_counts_at_one_and_three_quarter_times_the_opposite_margin():
    assert THRESHOLDS["edge_band_ratio"] == 1.75
    # A 290 px top band over a bottom margin of about 162 px (1.8 times): an edge band.
    stack = [panel("art", 290, 470), *lines("one", "two", start=780, step=40)]
    assert any(x["code"] == "dead_band" and x["values"].get("edge") == "top" for x in found(doc(*stack)))


def test_a_small_block_floating_midway_is_uneven_rhythm_and_repairable():
    from vixl.plugins.layout_repair.layout_repair import repair_layout

    ops = [text("title", 100, 80, size=96), text("note", 100, 330), panel("tray", 520, 380)]
    p = doc(*ops)
    (item,) = [x for x in found(p) if x["code"] == "uneven_rhythm"]
    assert item["values"]["floating"] == "note" and "floats midway" in item["message"]
    assert item["layers"] == ["title", "note", "tray"]
    # Close to the title, it belongs to it.
    p.apply({"type": "move", "target": "note", "y": 210})
    assert not [x for x in found(p) if x["code"] == "uneven_rhythm"]
    # Repair joins it to a neighbour, one spacing unit away.
    plan = repair_layout(doc(*ops), checks=["composition"], dry_run=True)
    assert plan["selected"] and plan["selected"][0]["candidate"] in ("float-to-above", "float-to-below")


def test_evenly_spaced_lines_of_one_kind_do_not_float():
    p = doc(text("title", 100, 80, size=96), *lines("a", "b", "c", "d", start=330, step=150))
    assert not [x for x in found(p) if x["code"] == "uneven_rhythm"]
