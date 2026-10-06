"""The MCP tools expose in-place edits, one-sided resize, roll's unfilled option and stacks."""

import asyncio
import json

import numpy as np
import pytest
from PIL import Image

from vixl import Project
from vixl.interfaces import mcp_server


def call(server, name, arguments):
    async def run():
        try:
            result = await server.call_tool(name, arguments)
        except Exception as exc:  # FastMCP surfaces tool failures as ToolError
            return True, str(exc)
        content = result[0] if isinstance(result, tuple) else result
        return False, "".join(getattr(item, "text", "") for item in content)

    return asyncio.run(run())


def ok(server, name, arguments):
    failed, text = call(server, name, arguments)
    assert not failed, text
    return json.loads(text) if text.startswith("{") else text


@pytest.fixture
def server(tmp_path):
    server = mcp_server(workspace=tmp_path)
    ok(server, "vixl_document_create", {"path": "a.vixl", "width": 400, "height": 300, "background": "white"})
    return server


def layers(tmp_path):
    return {x["name"]: x for x in Project.load(tmp_path / "a.vixl").state["layers"]}


def test_shape_target_edits_in_place_and_one_sided_resize_reports_it(server, tmp_path):
    ok(server, "vixl_operations_apply", {"operations": [
        {"type": "shape", "shape": "rectangle", "name": "bar", "width": 40, "height": 30, "fill": "#ff7f50"}]})
    ident = layers(tmp_path)["bar"]["id"]
    ok(server, "vixl_operations_apply", {"operations": [{"type": "shape", "target": "bar", "fill": "#6b3f69"}]})
    result = ok(server, "vixl_operations_apply", {"operations": [{"type": "resize", "target": "bar", "height": 90}]})
    bar = layers(tmp_path)
    assert list(bar) == ["bar"] and bar["bar"]["id"] == ident and bar["bar"]["fill"] == "#6b3f69"
    assert (bar["bar"]["width"], bar["bar"]["height"]) == (40, 90)
    assert any("only height" in note for note in result["normalized"])
    failed, text = call(server, "vixl_operations_apply", {"operations": [
        {"type": "text", "target": "bar", "size": 12}]})
    assert failed and "text-set" not in text and "shape" in text  # Names the operation that edits a shape.
    schema = ok(server, "vixl_operation_schema", {"types": ["shape", "resize", "stack"]})
    assert "in place" in schema["shape"]["properties"]["target"]["description"]
    assert "keep_aspect" in schema["resize"]["properties"] and "justify" in schema["stack"]["properties"]


def test_stack_and_hide_if_empty_through_mcp(server, tmp_path):
    ok(server, "vixl_operations_apply", {"operations": [
        {"type": "variable", "name": "company", "value": "Acme"}]})
    ok(server, "vixl_text_add", {"text": "Sam", "name": "first", "size": 40, "color": "black"})
    ok(server, "vixl_text_add", {"text": "${company}", "name": "company", "size": 20, "color": "black",
                                 "hide_if_empty": True})
    ok(server, "vixl_operations_apply", {"operations": [
        {"type": "stack", "name": "names", "targets": ["first", "company"], "gap": 10, "width": 400, "height": 300,
         "align": "center", "justify": "center"}]})
    assert layers(tmp_path)["company"]["hide_if_empty"] is True
    full = tmp_path / "full.png"
    short = tmp_path / "short.png"
    ok(server, "vixl_export_file", {"path": "full.png"})
    ok(server, "vixl_export_file", {"path": "short.png", "variables": {"company": ""}})

    def rows(path):
        return np.nonzero((np.asarray(Image.open(path).convert("L")) < 128).any(axis=1))[0]

    top_full, bottom_full = rows(full)[[0, -1]]
    top_short, bottom_short = rows(short)[[0, -1]]
    assert bottom_short < bottom_full and top_short > top_full
    assert abs((top_short + bottom_short) / 2 - 150) < 25  # Re-centred with the company line gone.
    failed, text = call(server, "vixl_operations_apply", {"operations": [
        {"type": "move", "target": "first", "x": 1, "y": 1}]})
    assert failed and "stack_managed" in text


def test_roll_apply_passes_check_with_unfilled_omit(server, monkeypatch):
    def fake_pair(project, pairing=None, **kwargs):  # Skip the font download; the proofing font will do.
        project.state["typography"] = {"body": "DejaVuSans.ttf", "heading": "DejaVuSans.ttf"}
        return {"origin": "cache", "heading": {"name": "DejaVuSans.ttf"}, "body": {"name": "DejaVuSans.ttf"}}

    monkeypatch.setattr("vixl.typefaces.pair_fonts", fake_pair)
    ok(server, "vixl_document_create", {"path": "b.vixl", "width": 800, "height": 800})
    rolled = ok(server, "vixl_roll", {
        "seed": 12, "apply": True, "locks": {"layout": "hero-statement", "palette": "ocean"},
        "slots": {"title": "Launch", "subtitle": "A new beginning", "cta": "Learn more"}})
    assert rolled["applied"]["layout"]["omitted"] == ["label"]
    report = ok(server, "vixl_check", {"checks": ["blanks"]})
    assert report["errors"] == 0
    ok(server, "vixl_document_create", {"path": "c.vixl", "width": 800, "height": 800})
    blank = ok(server, "vixl_roll", {
        "seed": 12, "apply": True, "unfilled": "blank", "locks": {"layout": "hero-statement", "palette": "ocean"},
        "slots": {"title": "Launch"}})
    assert "label" in blank["applied"]["unfilled_slots"]
