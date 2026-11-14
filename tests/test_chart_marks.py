"""Chart editing by data: marks addressed by series and category, and chart emphasis (highlight, mute, callout)."""

import io
import json
import zipfile

import pytest

from vixl import Project
from vixl.commands import compile_command
from vixl.errors import VixlError
from vixl.plugins.charts.charts import resolve_mark, series_colors
from vixl.schema import validate_operation

MONTHS = ["Jan", "Feb", "Mar", "Apr"]
DRINKS = {"categories": MONTHS, "series": [{"name": "Tea", "values": [10, 20, 30, 25]},
                                           {"name": "Coffee", "values": [30, 40, 35, 50]}]}
TEA = {"categories": MONTHS, "series": [DRINKS["series"][0]]}
SHUFFLED = {"categories": ["Apr", "Mar", "Feb", "Jan"], "series": [{"name": "Coffee", "values": [50, 35, 40, 30]},
                                                                    {"name": "Tea", "values": [25, 30, 20, 10]}]}
KINDS = ("bar", "stacked-bar", "percent-bar", "horizontal-bar", "stacked-horizontal-bar", "percent-horizontal-bar",
         "line", "area", "stacked-area", "pie", "donut")


def radial(kind):
    return kind in ("pie", "donut")


def make(kind="bar", data=None, **options):
    p = Project(900, 560, "#ffffff")
    data = data or (TEA if radial(kind) else DRINKS)
    p.apply({"type": "chart", "name": "Sales", "kind": kind, "title": "Cups", "x": 0, "y": 0, "width": 900,
             "height": 560, **data, **options})
    return p


def children(p):
    ident = p.layer("Sales")["id"]
    return [layer for layer in p.state["layers"] if layer.get("parent") == ident]


def part(p, key):
    return next(layer for layer in children(p) if layer["chart_part"] == key)


def shuffled(kind):
    if not radial(kind):
        return SHUFFLED
    return {"categories": SHUFFLED["categories"], "series": [SHUFFLED["series"][1]]}


# Marks addressed by series and category (#778)

@pytest.mark.parametrize("kind, mark", [("bar", "bar"), ("stacked-bar", "bar"), ("line", "marker"), ("donut", "slice")])
def test_a_series_and_category_address_names_the_same_layer_before_and_after_a_reorder(kind, mark):
    p = make(kind)
    address = {"chart": "Sales", "series": "Tea", "category": "Mar"}
    (ident,) = resolve_mark(p, address)
    layer = p.layer(ident)
    assert layer["chart_part"] == (f"{mark}-2" if radial(kind) else f"{mark}-0-2")
    assert layer["chart_mark"] == {"part": "point" if mark == "marker" else mark, "series": "Tea", "category": "Mar"}
    assert layer["name"].endswith("Mar")
    p.apply({"type": "opacity", "target": address, "value": 0.5})  # an operation takes the address as its target
    assert p.layer(ident)["opacity"] == 0.5
    before = (layer["x"], layer["y"])

    p.apply({"type": "chart-data", "target": "Sales", **shuffled(kind)})  # the rows and the series change places
    assert resolve_mark(p, address) == [ident], "the address still names the layer of Tea in March"
    layer = p.layer(ident)
    assert layer["chart_part"] == (f"{mark}-1" if radial(kind) else f"{mark}-1-1"), "its key is its new position"
    assert layer["chart_mark"]["category"] == "Mar" and layer["opacity"] == 0.5
    assert (layer["x"], layer["y"]) != before, "and it is drawn where March now is"
    names = [x["name"] for x in children(p)]
    assert len(set(names)) == len(names) and not [name for name in names if name.endswith(" 2 2")], \
        "layers that change places swap names cleanly"
    if not radial(kind):
        assert p.layer("Sales/category label 2")["text"] == "Mar"
    with pytest.raises(VixlError, match="Unknown category 'Dec'; categories: Apr, Mar, Feb, Jan") as caught:
        resolve_mark(p, {"chart": "Sales", "series": "Tea", "category": "Dec"})
    assert caught.value.details["allowed"] == ["Apr", "Mar", "Feb", "Jan"]


def test_an_address_names_labels_totals_legend_entries_and_whole_series():
    p = make("stacked-bar", total_labels=True, value_labels=True)

    def names(**address):
        return [p.layer(ident)["name"] for ident in resolve_mark(p, {"chart": "Sales", **address})]

    assert names(series="Coffee", category="Feb", part="value") == ["Sales/value Coffee Feb"]
    assert names(category="Feb", part="total") == ["Sales/total Feb"]
    assert names(category="Feb", part="category-label") == ["Sales/category label 2"]
    assert names(series="Coffee", part="legend") == ["Sales/legend swatch 2", "Sales/legend label 2"]
    assert names(category="Feb") == ["Sales/bar Tea Feb", "Sales/bar Coffee Feb"]
    assert len(names(series="Tea")) == 4 and len(names()) == 8
    line = make("line")
    assert [line.layer(i)["chart_part"] for i in resolve_mark(line, {"chart": "Sales", "series": "Tea"})] == [
        "line-0-0", "marker-0-0", "marker-0-1", "marker-0-2", "marker-0-3"]
    donut = make("donut")
    assert [donut.layer(i)["chart_part"] for i in resolve_mark(donut, {"chart": "Sales", "category": "Feb", "part": "legend"})] == [
        "legend-swatch-1", "legend-label-1"]


def test_an_address_that_names_nothing_or_is_malformed_says_why():
    p = make("line", value_labels=False)
    for address, message in [
        ({"chart": "Sales", "series": "Tea", "category": "Jan", "part": "value"}, "draws no value"),
        ({"chart": "Sales", "category": "Jan", "part": "line"}, "belongs to a series"),
        ({"chart": "Sales", "series": "Milk"}, "Unknown series 'Milk'; series: Tea, Coffee"),
        ({"chart": "Sales", "part": "pixel"}, "part must be one of"),
        ({"chart": "Sales", "row": "Jan"}, "takes chart, series, category and part"),
        ({"chart": "Nope"}, "does not exist"),
        ({"sheet": "Sales"}, "no plugin resolves"),
    ]:
        with pytest.raises(VixlError, match=message):
            p.apply({"type": "opacity", "target": address, "value": 0.5})
    with pytest.raises(VixlError, match="small object of names"):
        validate_operation({"type": "opacity", "target": {"chart": ["Sales"]}, "value": 0.5})
    with pytest.raises(VixlError, match="small object of names"):
        validate_operation({"type": "opacity", "target": {}, "value": 0.5})


def test_an_address_fans_out_where_the_operation_takes_several_layers_and_not_where_it_takes_one():
    p = make("bar")
    p.apply({"type": "opacity", "target": {"chart": "Sales", "category": "Jan"}, "value": 0.4})
    assert sorted(layer["name"] for layer in children(p) if layer["opacity"] == 0.4) == [
        "Sales/bar Coffee Jan", "Sales/bar Tea Jan"]
    p.apply({"type": "opacity", "value": 0.6, "targets": [{"chart": "Sales", "series": "Tea", "category": "Feb"},
                                                           "Sales/bar Coffee Apr"]})
    assert sorted(layer["name"] for layer in children(p) if layer["opacity"] == 0.6) == [
        "Sales/bar Coffee Apr", "Sales/bar Tea Feb"]
    with pytest.raises(VixlError, match="rename takes one layer; this address names 2"):
        p.apply({"type": "rename", "target": {"chart": "Sales", "category": "Jan"}, "name": "x"})
    p.apply({"type": "rename", "target": {"chart": "Sales", "series": "Tea", "category": "Jan"}, "name": "tea-jan"})
    assert p.layer("tea-jan")["chart_part"] == "bar-0-0"
    # A chart drawn earlier in the same batch can be addressed: the address is read when the operation runs.
    q = Project(900, 560, "#ffffff")
    q.apply([{"type": "chart", "name": "Sales", "width": 900, "height": 560, "x": 0, "y": 0, **DRINKS},
             {"type": "blend", "target": {"chart": "Sales", "series": "Tea", "category": "Mar"}, "mode": "multiply"}])
    assert part(q, "bar-0-2")["blend"] == "multiply"


def test_removing_a_category_keeps_the_layers_of_the_others():
    p = make("bar")
    before = {(layer["chart_mark"]["series"], layer["chart_mark"]["category"]): layer["id"]
              for layer in children(p) if layer["chart_part"].startswith("bar-")}
    p.apply({"type": "chart-data", "target": "Sales", "remove_categories": ["Feb"]})
    after = {(layer["chart_mark"]["series"], layer["chart_mark"]["category"]): layer["id"]
             for layer in children(p) if layer["chart_part"].startswith("bar-")}
    assert after == {key: ident for key, ident in before.items() if key[1] != "Feb"}


def test_documents_from_before_marks_were_stored_resolve_and_keep_their_layers(tmp_path):
    p = make("bar")
    ids = {layer["chart_part"]: layer["id"] for layer in children(p)}
    for layer in children(p):
        layer.pop("chart_mark", None)
    (ident,) = resolve_mark(p, {"chart": "Sales", "series": "Coffee", "category": "Apr"})
    assert ident == ids["bar-1-3"], "the address reads the chart's data, not the stored mark"
    p.apply({"type": "chart-data", "target": "Sales", "set": [{"category": "Apr", "series": "Coffee", "value": 45}]})
    assert {layer["chart_part"]: layer["id"] for layer in children(p)} == ids
    assert part(p, "bar-1-3")["chart_mark"] == {"part": "bar", "series": "Coffee", "category": "Apr"}
    path = tmp_path / "chart.vixl"
    p.save(path)
    assert part(Project.load(path), "bar-1-3")["chart_mark"]["category"] == "Apr"


# Chart emphasis (#779)

def focus_marks(p, kind):
    """(the mark in focus for Tea in March, a mark out of focus) for a chart of ``kind``."""
    if radial(kind):
        return part(p, "slice-2"), part(p, "slice-0")
    if "bar" in kind:
        return part(p, "bar-0-2"), part(p, "bar-0-0")
    if kind == "line":
        return part(p, "focus-0-2"), part(p, "marker-0-0")
    return part(p, "focus-0-2"), part(p, "area-1")


@pytest.mark.parametrize("kind", KINDS)
def test_emphasis_survives_a_data_change_and_focus_empty_restores_the_chart(kind):
    p = make(kind)
    plain = p.render().tobytes()
    colors = p.layer("Sales")["chart"]["summary"]["colors"]
    tea = colors[2] if radial(kind) else colors[0]
    p.apply({"type": "chart-emphasis", "target": "Sales", "focus": ["Mar"], "series": "Tea",
             "annotate": "Best: ${value}"})
    assert p.render().tobytes() != plain
    strong, weak = focus_marks(p, kind)
    assert strong["fill"] == tea and weak["fill"] not in colors, "the focus keeps its colour, the rest is muted"
    assert part(p, "callout-2")["text"] == "Best: 30"
    ident = strong["id"]

    p.apply({"type": "chart-data", "target": "Sales", "set": [{"category": "Mar", "series": "Tea", "value": 44}]})
    strong, weak = focus_marks(p, kind)
    assert strong["id"] == ident and strong["fill"] == tea and weak["fill"] not in colors
    assert part(p, "callout-2")["text"] == "Best: 44", "the callout follows the value"
    assert p.layer("Sales")["chart"]["emphasis"]["focus"] == ["Mar"]

    p.apply({"type": "chart-data", "target": "Sales", **shuffled(kind)})  # March moves to the second place
    callout = part(p, "callout-1")
    assert callout["text"] == "Best: 30" and callout["chart_mark"]["category"] == "Mar"

    p.apply({"type": "chart-data", "target": "Sales", **(TEA if radial(kind) else DRINKS)})
    p.apply({"type": "chart-emphasis", "target": "Sales", "focus": []})
    assert "emphasis" not in p.layer("Sales")["chart"] and "emphasis" not in p.layer("Sales")["chart"]["summary"]
    assert not [layer for layer in children(p) if layer["chart_part"].startswith(("callout-", "focus-"))]
    assert p.render().tobytes() == plain, "focus: [] gives back the chart's own pixels"


def test_a_category_focus_keeps_every_series_of_it_and_the_callout_speaks_for_the_category():
    p = make("bar", value_labels=True)
    p.apply({"type": "chart-emphasis", "target": "Sales", "focus": ["Feb", "Apr"],
             "annotate": "${category}: ${value} (${percent})"})
    colors = p.layer("Sales")["chart"]["summary"]["colors"]
    assert [part(p, f"bar-{s}-1")["fill"] for s in (0, 1)] == colors
    assert part(p, "bar-0-0")["fill"] not in colors and part(p, "bar-1-2")["fill"] not in colors
    assert part(p, "callout-1")["text"] == "Feb: 60 (25%)" and part(p, "callout-3")["text"] == "Apr: 75 (31.3%)"
    # Labels beside muted bars step back; those of the focus stay in the chart's ink. Every label is still drawn.
    assert part(p, "value-0-1")["color"] != part(p, "value-0-0")["color"]
    assert sum(1 for layer in children(p) if layer["chart_part"].startswith("value-")) == 8
    assert [swatch["fill"] for swatch in (part(p, "legend-swatch-0"), part(p, "legend-swatch-1"))] == colors
    assert not [i for i in p.check(checks=["overlap", "bounds", "contrast"])["issues"] if i["severity"] != "info"]


def test_a_series_focus_mutes_the_other_lines():
    p = make("line")
    colors = p.layer("Sales")["chart"]["summary"]["colors"]
    p.apply({"type": "chart-emphasis", "target": "Sales", "series": "Coffee"})
    assert part(p, "line-1-0")["stroke"] == colors[1] and part(p, "line-0-0")["stroke"] not in colors
    assert part(p, "legend-swatch-0")["fill"] == part(p, "line-0-0")["stroke"]
    assert series_colors(p, {layer["id"]: layer for layer in p.state["layers"]})[0][1][0][1] == (0x00, 0x72, 0xb2), \
        "checks that compare series still see the series' own colours"
    p.apply({"type": "chart-emphasis", "target": "Sales", "series": None, "focus": ["Jan"]})  # the settings merge
    assert p.layer("Sales")["chart"]["emphasis"] == {"focus": ["Jan"]}
    assert part(p, "line-0-0")["stroke"] == colors[0] and part(p, "marker-0-1")["fill"] != colors[0]


def test_mute_modes_and_opacity():
    p = make("bar", TEA)
    p.apply({"type": "chart-emphasis", "target": "Sales", "focus": ["Mar"]})
    assert part(p, "bar-0-0")["fill"] == "#a6cee4"  # 35 % of #0072b2 over white
    result = p.apply({"type": "chart-emphasis", "target": "Sales", "opacity": "60%"})
    assert any("opacity '60%' → 0.6" in note for note in result["normalized"])
    assert part(p, "bar-0-0")["fill"] == "#66aad1" and p.layer("Sales")["chart"]["emphasis"]["focus"] == ["Mar"]
    p.apply({"type": "chart-emphasis", "target": "Sales", "mute": "desaturate"})
    r, g, b = (int(part(p, "bar-0-0")["fill"][i:i + 2], 16) for i in (1, 3, 5))
    assert r == g == b and part(p, "bar-0-2")["fill"] == "#0072b2"
    dark = Project(900, 560, "#101418")
    dark.apply({"type": "chart", "name": "Sales", "x": 0, "y": 0, "width": 900, "height": 560, **TEA})
    dark.apply({"type": "chart-emphasis", "target": "Sales", "focus": ["Mar"]})
    faded = part(dark, "bar-0-0")["fill"]
    assert int(faded[1:3], 16) < 0x30, "fade goes toward the chart's background, dark here"


def test_emphasis_follows_the_data_when_its_focus_is_removed():
    p = make("bar")
    p.apply({"type": "chart-emphasis", "target": "Sales", "focus": ["Feb", "Mar"], "annotate": "${value}"})
    result = p.apply({"type": "chart-data", "target": "Sales", "remove_categories": ["Feb"]})
    assert p.layer("Sales")["chart"]["emphasis"]["focus"] == ["Mar"]
    assert any("no longer has 'Feb'" in warning for warning in result["warnings"])
    result = p.apply({"type": "chart-data", "target": "Sales", "remove_categories": ["Mar"]})
    assert "emphasis" not in p.layer("Sales")["chart"]
    assert any("nothing left in focus" in warning for warning in result["warnings"])
    assert part(p, "bar-0-0")["fill"] == "#0072b2"


@pytest.mark.parametrize("op, message", [
    ({"focus": ["Dec"]}, "Unknown category 'Dec'; categories: Jan, Feb, Mar, Apr"),
    ({"focus": ["Mar"], "series": "Milk"}, "Unknown series 'Milk'"),
    ({"mute": "fade"}, "needs focus"),
    ({"series": "Tea", "annotate": "x"}, "annotate labels the focus categories"),
    ({"focus": ["Mar"], "opacity": 35}, "0–1 scale"),
    ({"focus": ["Mar"], "mute": "blur"}, "mute"),
    ({"target": "Title", "focus": ["Mar"]}, "is not a chart"),
])
def test_bad_emphasis_is_rejected_with_a_reason(op, message):
    p = make("bar")
    p.apply({"type": "text", "name": "Title", "text": "Cups", "x": 10, "y": 10})
    before = json.dumps(p.state, sort_keys=True, default=str)
    with pytest.raises(VixlError, match=message):
        p.apply({"type": "chart-emphasis", "target": "Sales", **op})
    assert json.dumps(p.state, sort_keys=True, default=str) == before
    pie = make("pie")
    with pytest.raises(VixlError, match="the slices of a pie or donut"):
        pie.apply({"type": "chart-emphasis", "target": "Sales", "series": "Tea"})
    p.apply({"type": "table", "name": "Prices", "rows": [["Item", "Price"], ["Tea", 3]], "x": 0, "y": 0})
    with pytest.raises(VixlError, match="is not a chart; chart-emphasis works on bar, line, area, pie and donut"):
        p.apply({"type": "chart-emphasis", "target": "Prices", "focus": ["Tea"]})


def test_forgiving_spellings_and_the_command_line():
    p = make("bar")
    result = p.apply({"type": "chart-emphasis", "target": "Sales", "highlight": "Mar", "callout": "${value}",
                      "mute": "grey"})
    assert p.layer("Sales")["chart"]["emphasis"] == {"focus": ["Mar"], "annotate": "${value}", "mute": "desaturate"}
    assert len(result["normalized"]) == 4
    assert compile_command(["chart-emphasis", "Mar", "Apr", "--target", "Sales", "--series", "Tea", "--opacity", "0.5",
                            "--annotate", "${value}"]) == {
        "type": "chart-emphasis", "focus": ["Mar", "Apr"], "target": "Sales", "series": "Tea", "opacity": 0.5,
        "annotate": "${value}"}
    assert compile_command(["chart-emphasis", "--target", "Sales", "--clear"]) == {
        "type": "chart-emphasis", "target": "Sales", "focus": []}


def test_emphasis_that_cannot_be_told_apart_is_a_color_vision_finding():
    def codes(**options):
        p = make("bar", TEA)
        p.apply({"type": "chart-emphasis", "target": "Sales", "focus": ["Mar"], **options})
        return {i.get("code"): i for i in p.check(checks=["color_vision"])["issues"]}, p

    assert not codes()[0], "the default fade is distinct from the focus and from the background"
    found, p = codes(opacity=0.97)
    assert "look alike" in found["emphasis-indistinct"]["message"] and found["emphasis-indistinct"]["layers"] == ["Sales"]
    assert "emphasis-faint" in codes(opacity=0.03)[0]
    p.apply({"type": "layer-intent", "target": "Sales", "color_vision_safe": True})
    assert not p.check(checks=["color_vision"])["issues"]


def test_a_tampered_emphasis_is_refused():
    p = make("bar")
    p.apply({"type": "chart-emphasis", "target": "Sales", "focus": ["Mar"]})
    p.layer("Sales")["chart"]["emphasis"]["focus"] = ["Dec"]
    with pytest.raises(VixlError, match="focus must list categories"):
        p.apply({"type": "hide", "target": "Sales/title"})


# Exports

def chart_xml(p):
    report = {}
    data = p.export(format="PPTX", report=report)
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        return archive.read("ppt/charts/chart1.xml").decode(), archive.read("ppt/slides/slide1.xml").decode(), report


def test_pptx_emphasis_is_native_point_colours_with_the_callout_over_the_chart():
    p = make("bar")
    plain, _, _ = chart_xml(p)
    assert "<c:dPt>" not in plain
    p.apply({"type": "chart-emphasis", "target": "Sales", "focus": ["Mar"], "series": "Tea", "annotate": "Best: ${value}"})
    xml, slide, report = chart_xml(p)
    muted = part(p, "bar-0-0")["fill"][1:].upper()
    tea, coffee = xml.split("<c:ser>")[1:]
    assert [f'<c:idx val="{i}"/>' in tea.split("<c:dLbls>")[0] for i in range(4)] == [True, True, False, True]
    assert tea.count(f'val="{muted}"') == 3 and '<a:srgbClr val="0072B2">' in tea
    assert "<c:dPt>" not in coffee and '<a:srgbClr val="E69F00">' not in coffee, "a series out of focus is muted whole"
    assert '<c:dLbl><c:idx val="2"/><c:delete val="1"/></c:dLbl>' in tea, "the callout stands in for the native label"
    assert "Best: 30" in slide and report["charts"]["1"][0]["notes"] == ["callouts are text boxes over the native chart"]
    pptx = pytest.importorskip("pptx")
    chart = next(s for s in pptx.Presentation(io.BytesIO(p.export(format="PPTX"))).slides[0].shapes if s.has_chart).chart
    assert str(chart.plots[0].series[0].format.fill.fore_color.rgb) == "0072B2"
    assert str(chart.plots[0].series[0].points[0].format.fill.fore_color.rgb) == muted

    for kind in ("line", "pie", "stacked-area"):
        q = make(kind)
        q.apply({"type": "chart-emphasis", "target": "Sales", "focus": ["Mar"], "annotate": "${value}"})
        xml, slide, _ = chart_xml(q)
        if kind == "line":
            assert xml.count("<c:dPt>") == 8 and "<c:size" in xml.split("<c:dPt>")[3], "muted markers, larger focus ones"
        elif kind == "pie":
            assert part(q, "slice-0")["fill"][1:].upper() in xml and '<c:dLbl><c:idx val="2"/><c:delete val="1"/>' in xml
        else:
            assert slide.count("<p:sp>") == 3, "an area chart's focus dots and callout sit over it as shapes"
        pptx.Presentation(io.BytesIO(q.export(format="PPTX")))


def test_svg_and_pdf_draw_the_same_emphasis():
    p = make("stacked-bar")
    p.apply({"type": "chart-emphasis", "target": "Sales", "focus": ["Mar"], "annotate": "Best: ${value}"})
    muted = part(p, "bar-1-0")["fill"]
    svg = p.export(format="SVG").decode()
    assert svg.count(muted) >= 3 and svg.count("#e69f00") >= 1
    assert p.export(format="PDF").startswith(b"%PDF")


def test_the_mcp_tools_take_mark_addresses_and_chart_emphasis(tmp_path):
    import asyncio

    from vixl.interfaces import mcp_server

    server = mcp_server(workspace=tmp_path)

    def call(name, arguments):
        async def run():
            try:
                result = await server.call_tool(name, arguments)
            except Exception as exc:  # FastMCP surfaces tool failures as ToolError
                return True, str(exc)
            content = result[0] if isinstance(result, tuple) else result
            return False, "".join(getattr(item, "text", "") for item in content)

        return asyncio.run(run())

    call("vixl_document", {"action": "create", "path": "a.vixl", "width": 900, "height": 560})
    failed, text = call("vixl_apply", {"operations": [
        {"type": "chart", "name": "Sales", "x": 0, "y": 0, "width": 900, "height": 560, **DRINKS},
        {"type": "chart-emphasis", "target": "Sales", "focus": ["Mar"], "annotate": "${value}"},
        {"type": "opacity", "target": {"chart": "Sales", "series": "Tea", "category": "Mar"}, "value": 0.8}]})
    assert not failed, text
    failed, text = call("vixl_apply", {"operations": [
        {"type": "opacity", "target": {"chart": "Sales", "series": "Tea", "category": "Dec"}, "value": 0.8}]})
    assert failed and "Unknown category 'Dec'" in text and '"allowed"' in text
    saved = Project.load(tmp_path / "a.vixl")
    assert part(saved, "bar-0-2")["opacity"] == 0.8 and part(saved, "callout-2")["text"] == "65"
