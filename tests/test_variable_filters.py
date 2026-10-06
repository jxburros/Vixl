"""Merge field filters: ${name|filter:arg|...} through one substitute() (#215)."""

import pypdf
import pytest

from vixl import Project
from vixl.errors import VixlError
from vixl.imposition import template_variables
from vixl.interfaces import Session
from vixl.render import resolved_layers
from vixl.variables import placeholders, substitute, with_maps
from vixl.workflows import dispatch


def texts(project):
    return {layer["name"]: layer["text"] for layer in resolved_layers(project) if layer["type"] == "text"}


def test_filters_change_case_default_number_and_format():
    values = {"name": "ada lovelace", "empty": "", "n": 1234.5, "count": "7"}
    assert substitute("${name|upper}", values) == "ADA LOVELACE"
    assert substitute("${name|title} / ${name|upper|lower}", values) == "Ada Lovelace / ada lovelace"
    assert substitute("${missing|default:Friend}, ${empty|default:none}", values) == "Friend, none"
    assert substitute("${missing|default:dear friend|upper}", values) == "DEAR FRIEND"
    assert substitute("${n|number:2} ${n|number} ${count|number}", values) == "1,234.50 1,234.5 7"
    assert substitute("[${count|format:03d}] [${name|format:>14}]", values) == "[007] [  ada lovelace]"
    assert substitute("${name}", values) == "ada lovelace"  # unchanged without filters
    with pytest.raises(VixlError, match="Undefined variable: missing"):
        substitute("${missing|upper}", values)
    with pytest.raises(VixlError, match="not a number"):
        substitute("${name|number}", values)


def test_map_filter_reads_document_maps_with_a_star_fallback():
    maps = {"state": {"NY": "New York", "*": "Elsewhere"}, "strict": {"a": "A"}}
    values = with_maps({"code": "NY", "other": "TX"}, maps)
    assert substitute("${code|map:state} ${other|map:state|upper}", values) == "New York ELSEWHERE"
    with pytest.raises(VixlError, match="no entry for 'TX'"):
        substitute("${other|map:strict}", values)
    with pytest.raises(VixlError) as caught:
        substitute("${other|map:nope}", values)
    assert caught.value.code == "missing_map"


def test_unknown_filters_and_maps_are_validation_errors():
    p = Project(300, 120, "white")
    p.apply({"type": "text", "name": "t", "text": "plain"})
    for text, code in (("${a|shout}", "invalid_filter"), ("${a|default}", "invalid_filter"),
                       ("${a|upper:x}", "invalid_filter")):
        with pytest.raises(VixlError) as caught:
            p.apply([{"type": "variable", "name": "a", "value": "x"}, {"type": "text-set", "target": "t", "text": text}])
        assert caught.value.code == code
    with pytest.raises(VixlError) as caught:
        p.apply({"type": "text-set", "target": "t", "text": "${who|default:x|map:cities}"})
    assert caught.value.code == "missing_map"
    p.apply({"type": "variable-map", "name": "cities", "values": {"x": "Oslo"}})
    p.apply({"type": "text-set", "target": "t", "text": "${who|default:x|map:cities}"})
    assert texts(p)["t"] == "Oslo"
    with pytest.raises(VixlError) as caught:
        p.apply({"type": "variable-map", "name": "cities", "delete": True})
    assert caught.value.code == "missing_map"


def test_variable_map_operation_replaces_merges_and_deletes():
    p = Project(300, 120, "white")
    p.apply([{"type": "variable-map", "name": "m", "values": {"a": "1"}},
             {"type": "variable-map", "name": "m", "values": {"b": 2}, "merge": True}])
    assert p.state["maps"] == {"m": {"a": "1", "b": 2}}
    p.apply({"type": "variable-map", "name": "m", "values": {"c": "3"}})
    assert p.state["maps"] == {"m": {"c": "3"}}
    p.apply({"type": "variable-map", "name": "m", "delete": True})
    assert "maps" not in p.state
    with pytest.raises(VixlError):
        p.apply({"type": "variable-map", "name": "bad name", "values": {"a": "b"}})


def test_colours_and_rich_text_go_through_filters():
    p = Project(300, 120, "white")
    p.apply([{"type": "variable", "name": "tier", "value": "gold"},
             {"type": "variable-map", "name": "ink", "values": {"gold": "#d4af37", "*": "#888888"}},
             {"type": "solid", "name": "bar", "color": "${tier|map:ink}", "width": 300, "height": 20},
             {"type": "rich-text", "name": "r", "markdown": "**${tier|upper}** member"}])
    layers = {layer["name"]: layer for layer in resolved_layers(p)}
    assert layers["bar"].get("fill", layers["bar"].get("color")) == "#d4af37"
    assert layers["r"]["text"] == "GOLD member"
    assert p.render().getpixel((5, 5))[:3] == (0xD4, 0xAF, 0x37)


def test_inspect_lists_placeholders_with_their_filters():
    p = Project(300, 120, "white")
    p.apply([{"type": "variable", "name": "first", "value": "ada"},
             {"type": "text", "name": "t", "text": "Hi ${first|title}, from ${city|default:here}"}])
    listing = p.inspect()["placeholders"]
    assert [(i["name"], i["layer_name"], i["field"], i["defined"]) for i in listing] == [
        ("first", "t", "text", True), ("city", "t", "text", True)]
    assert listing[0]["filters"] == [{"filter": "title"}]
    assert listing[1]["filters"] == [{"filter": "default", "argument": "here"}]
    assert placeholders("${a|map:m|default:x}")[0]["filters"][0] == {"filter": "map", "argument": "m"}


def test_template_variables_use_the_name_before_the_filters(tmp_path):
    p = Project(600, 300, "white")
    p.apply([{"type": "canvas", "dpi": 300}, {"type": "variable", "name": "first", "value": "sample"},
             {"type": "text", "name": "t", "text": "${first|upper} ${title|default:Guest}"}])
    used, defaults, _, _ = template_variables(p)
    assert used == {"first", "title"} and defaults == {"first"}
    p.save(tmp_path / "card.vixl")
    (tmp_path / "rows.csv").write_text("first,title\nmara,\nniamh,Dr\n", encoding="utf-8")
    report = dispatch(Session(None, workspace=tmp_path), "merge-impose",
                      {"template": "card.vixl", "data": "rows.csv", "output": "out.pdf", "sheet": {"size": "letter"}})
    assert report["errors"] == [] and report["warnings"] == [], report
    text = pypdf.PdfReader(str(tmp_path / "out.pdf")).pages[0].extract_text()
    assert "MARA Guest" in text and "NIAMH Dr" in text


def test_link_variables_accept_filtered_references(tmp_path):
    source = Project(200, 100, "white")
    source.apply([{"type": "variable", "name": "who", "value": "x"}, {"type": "text", "name": "t", "text": "${who}"}])
    source.save(tmp_path / "src.vixl")
    host = Project(400, 200, "white")
    host.path = tmp_path / "host.vixl"
    host.apply([{"type": "variable", "name": "name", "value": "zoë"},
                {"type": "link", "source": str(tmp_path / "src.vixl"), "name": "l",
                 "variables": {"who": "${name|upper} ${nick|default:-}"}}], )
    from vixl.links import overrides

    layer = next(layer for layer in host.state["layers"] if layer["name"] == "l")
    assert overrides(host, layer) == {"who": "ZOË -"}
