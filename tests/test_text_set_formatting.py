"""text-set keeps rich-text formatting, reports what it drops, and is told apart from text-style."""

import asyncio
import hashlib
import json
from pathlib import Path

import pytest

import vixl
from vixl import Project, VixlError
from vixl.interfaces import mcp_server
from vixl.richtext import layout
from vixl.schema import operation_schema

DEJAVU = Path(vixl.__file__).parent / "data" / "DejaVuSans.ttf"


def event_poster():
    p = Project(600, 400, "white")
    p.apply([
        {"type": "rich-text", "name": "highlights", "markdown": "- Live brass band\n- Street food\n- Lantern parade",
         "size": 28, "color": "black", "width": 500, "x": 20, "y": 20},
        {"type": "rich-text", "name": "kicker", "markdown": "[SUMMER NIGHT MARKET]{tracking=6 bold}", "size": 20,
         "color": "black", "x": 20, "y": 250},
    ])
    return p


# --- #57: text-set keeps the formatting of a rich-text layer -----------------------------------------


def test_text_set_keeps_bullets_and_letter_spacing():
    p = event_poster()
    result = p.apply([
        {"type": "text-set", "target": "highlights", "text": "Live brass band\nFire dancers at 8 pm\nLantern parade"},
        {"type": "text-set", "target": "kicker", "text": "WINTER NIGHT MARKET"},
    ])
    assert "warnings" not in result
    highlights, kicker = p.layer("highlights"), p.layer("kicker")
    assert highlights["text"].split("\n")[1] == "Fire dancers at 8 pm"
    assert highlights["rich"]["paragraphs"] == [{"list": "bullet", "level": 0}] * 3
    assert "".join(g.text for g in layout(p, highlights).glyphs).startswith("•Live")
    assert kicker["rich"]["spans"] == [{"text": "WINTER NIGHT MARKET", "tracking": 6.0, "bold": True}]
    assert p.check(checks=["bounds"])["errors"] == 0
    assert p.render().getchannel("A").getbbox() is not None


def test_text_set_carries_span_styles_by_word():
    p = Project(800, 200, "white")
    p.apply({"type": "rich-text", "name": "line", "markdown": "**Date:** June 21 at *noon*", "color": "black"})
    p.apply({"type": "text-set", "target": "line", "text": "Date: July 4 at noon"})
    assert p.layer("line")["rich"]["spans"] == [{"text": "Date:", "bold": True}, {"text": " July 4 at "},
                                                {"text": "noon", "italic": True}]
    # Inserted words take the style of the text before them.
    p.apply({"type": "text-set", "target": "line", "text": "Date: July 4 at high noon"})
    assert p.layer("line")["rich"]["spans"][-1] == {"text": "noon", "italic": True}
    # Replaced words take the style of the words they replace.
    p.apply({"type": "rich-text", "name": "title", "markdown": "[Hello]{bold color=#f00}", "color": "black"})
    p.apply({"type": "text-set", "target": "title", "text": "Goodbye for now"})
    assert p.layer("title")["rich"]["spans"] == [{"text": "Goodbye for now", "bold": True, "color": "#f00"}]


def test_text_set_matches_lines_and_inherits_list_settings():
    p = Project(600, 400, "white")
    p.apply({"type": "rich-text", "name": "list", "color": "black", "width": 400,
             "markdown": "# Menu\n- soup\n  - leeks\n- bread\n3. tea"})
    before = p.layer("list")["rich"]["paragraphs"]
    # A line inserted after a nested bullet continues that list; the other lines keep their own settings.
    result = p.apply({"type": "text-set", "target": "list", "text": "Menu\nsoup\nleeks\nsalad\nbread\ntea"})
    paragraphs = p.layer("list")["rich"]["paragraphs"]
    assert paragraphs[:3] == before[:3] and paragraphs[3] == {"list": "bullet", "level": 1}
    assert paragraphs[4] == before[3] and paragraphs[5] == before[4] and "warnings" not in result
    first = p.layer("list")["rich"]["spans"][0]
    assert first["text"] == "Menu" and first["bold"]  # the heading keeps its style
    # Removing the only numbered line says what formatting went with it.
    result = p.apply({"type": "text-set", "target": "list", "text": "Menu\nsoup\nleeks\nsalad\nbread"})
    (warning,) = result["warnings"]
    assert "dropped" in warning and "number list" in warning and "rich-text" in warning
    assert [para.get("list") for para in p.layer("list")["rich"]["paragraphs"]] == [None, "bullet", "bullet", "bullet", "bullet"]


def test_text_set_reports_dropped_character_styles():
    p = Project(600, 200, "white")
    p.apply({"type": "rich-text", "name": "t", "color": "black", "markdown": "plain [loud]{bold color=#f00} plain"})
    result = p.apply({"type": "text-set", "target": "t", "text": "just plain"}, dry_run=True)
    (warning,) = result["warnings"]
    assert "bold+color #f00 on 'loud'" in warning
    assert p.layer("t")["text"] == "plain loud plain"  # a dry run changes nothing
    p.apply({"type": "text-set", "target": "t", "text": "just plain"})
    assert p.layer("t")["rich"]["spans"] == [{"text": "just plain"}]


def test_text_set_warns_when_spans_keep_their_own_color_or_size():
    p = Project(600, 200, "white")
    p.apply({"type": "rich-text", "name": "t", "color": "black", "size": 30, "markdown": "a [b]{color=#f00 size=50} c"})
    result = p.apply({"type": "text-set", "target": "t", "color": "#0000ff", "size": 40})
    (warning,) = result["warnings"]
    assert "1 span(s) set their own color and keep it" in warning and "1 span(s) set their own size" in warning
    assert "text-style" in warning and p.layer("t")["color"] == "#0000ff"
    p.apply({"type": "text-style", "target": "t", "color": "#0000ff"})  # the supported way to recolor everything
    assert {span.get("color") for span in p.layer("t")["rich"]["spans"]} == {"#0000ff"}
    plain = Project(200, 100)
    plain.apply({"type": "text", "name": "p", "text": "hi"})
    assert "warnings" not in plain.apply({"type": "text-set", "target": "p", "color": "red", "text": "hello"})


def test_text_set_on_stale_or_plain_layers_is_unchanged():
    p = Project(300, 100)
    p.apply({"type": "text", "name": "t", "text": "one"})
    p.apply({"type": "text-set", "target": "t", "text": "two", "size": 20})
    assert p.layer("t")["text"] == "two" and "rich" not in p.layer("t")
    p.apply({"type": "rich-text", "name": "r", "markdown": "**x** y"})
    p.layer("r")["text"] = "edited elsewhere"  # a record that no longer matches is not carried
    result = p.apply({"type": "text-set", "target": "r", "text": "fresh"})
    assert "rich" not in p.layer("r") and "warnings" not in result


# --- #58: text-set versus text-style ----------------------------------------------------------------


def test_text_style_without_a_range_on_plain_text_acts_as_text_set():
    p = Project(300, 100, "white")
    p.apply({"type": "text", "name": "t", "text": "Hello", "color": "black", "size": 30})
    result = p.apply({"type": "text-style", "target": "t", "color": "#444444", "size": 36})
    layer = p.layer("t")
    assert layer["color"] == "#444444" and layer["size"] == 36 and "rich" not in layer
    assert any("text-style on 't'" in note and "text-set" in note for note in result["normalized"])
    with pytest.raises(VixlError):  # the same size limits as styled text
        p.apply({"type": "text-style", "target": "t", "size": 0})
    # With a range, or with anything that needs spans, it still makes rich text.
    p.apply({"type": "text-style", "target": "t", "match": "ell", "color": "#f00"})
    assert p.layer("t")["rich"]["spans"][1] == {"text": "ell", "color": "#f00"}
    p.apply({"type": "text", "name": "u", "text": "Hi", "color": "black"})
    p.apply({"type": "text-style", "target": "u", "color": "#f00", "bold": True})
    assert p.layer("u")["rich"]["spans"] == [{"text": "Hi", "color": "#f00", "bold": True}]
    p.apply({"type": "text", "name": "v", "text": "Hi", "color": "black"})
    p.apply({"type": "text-style", "target": "v", "size": 30.5})  # not a whole-pixel size: spans carry it
    assert p.layer("v")["rich"]["spans"] == [{"text": "Hi", "size": 30.5}]


def test_schema_and_errors_say_which_operation_to_use():
    variants = {v["properties"]["type"]["const"]: v for v in operation_schema()["properties"]["operations"]["items"]["oneOf"]}
    assert "whole text layer" in variants["text-set"]["description"] and "text-style" in variants["text-set"]["description"]
    assert "text-set" in variants["text-style"]["description"] and "range" in variants["text-style"]["description"]
    assert "text-style" in variants["text-set"]["properties"]["color"]["description"]
    assert "rich-text" in variants["text-set"]["properties"]["text"]["description"]
    p = Project(200, 100)
    p.apply({"type": "text", "name": "t", "text": "x"})
    with pytest.raises(VixlError) as caught:
        p.apply({"type": "text-set", "target": "t", "match": "x", "bold": True})
    assert "Unknown field(s) 'bold', 'match'" in str(caught.value) and "use text-style" in str(caught.value)
    with pytest.raises(VixlError) as caught:
        p.apply({"type": "text-style", "target": "t", "text": "new words"})
    assert "use text-set to change the layer's text" in str(caught.value) and "rich-text" in str(caught.value)


def test_mcp_explains_the_split_in_the_tool_description_and_schema_lookup(tmp_path):
    server = mcp_server(workspace=tmp_path)

    async def run():
        tools = {t.name: t for t in await server.list_tools()}
        result = await server.call_tool("vixl_operation_schema", {"types": ["text-set", "text-style"]})
        content = result[0] if isinstance(result, tuple) else result
        return tools, "".join(getattr(item, "text", "") for item in content)

    tools, text = asyncio.run(run())
    assert "text-set changes a whole text layer" in tools["vixl_operations_apply"].description
    schemas = json.loads(text)
    assert "text-style" in schemas["text-set"]["description"] and "text-set" in schemas["text-style"]["description"]
    inline = json.dumps(tools["vixl_operations_apply"].inputSchema)
    assert "Change a whole text layer" not in inline  # prose stays out of tools/list; vixl_operation_schema has it


def test_text_set_font_goes_through_the_batch_font_rules(tmp_path):
    from vixl.interfaces import Session

    session = Session(workspace=tmp_path)
    session.create("doc.vixl", 300, 100)
    data = DEJAVU.read_bytes()
    with session.project(write=True) as project:
        asset = f"fonts/{hashlib.sha256(data).hexdigest()}.ttf"
        project.assets[asset] = data
        project.apply({"type": "font-register", "name": "mine", "asset": asset})
    session.apply([{"type": "rich-text", "name": "r", "markdown": "[a]{font=mine} b"}])
    result = session.apply([{"type": "text-set", "target": "r", "font": "mine", "text": "a c"}])
    assert result["success"] and any("font and keep it" in w for w in result.get("warnings", []))
