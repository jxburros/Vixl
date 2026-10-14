"""Deleting swatches without breaking their users, and pen paths with opacity in every output."""

import io

import numpy as np
from PIL import Image
import pytest

from vixl import Project
from vixl.errors import VixlError


def referenced():
    p = Project(120, 80, background="white")
    p.apply([
        {"type": "swatch", "name": "brand", "color": "#cc0000"},
        {"type": "swatch", "name": "light", "color": "lighten(@brand, 10%)"},
        {"type": "swatch", "name": "brand-dark", "color": "#330000"},
        {"type": "style-define", "name": "Heading", "settings": {"size": 12, "color": "@brand"}},
        {"type": "variable", "name": "tone", "value": "@brand"},
        {"type": "shape", "shape": "rectangle", "name": "box", "width": 40, "height": 40, "fill": "@brand"},
        {"type": "gradient", "name": "sky", "start": "mix(@brand, white, 30%)", "end": "@brand-dark", "width": 40,
         "height": 40, "x": 60},
        {"type": "text", "name": "handle", "text": "Follow @brand", "color": "black", "y": 50},
    ])
    return p


def test_delete_unused_swatch_and_undo_restores_it():
    p = referenced()
    p.apply({"type": "swatch", "name": "brand-dark", "delete": True, "detach": True})
    assert "brand-dark" not in p.state["swatches"]
    p.apply({"type": "swatch", "name": "light", "delete": True})
    assert set(p.state["swatches"]) == {"brand"}
    p.undo()
    assert p.state["swatches"]["light"] == "lighten(@brand, 10%)"


def test_delete_refuses_while_swatch_is_used_and_names_the_users():
    p = referenced()
    before = p.state["swatches"].copy()
    with pytest.raises(VixlError) as caught:
        p.apply({"type": "swatch", "name": "brand", "delete": True})
    error = caught.value
    assert error.code == "swatch_in_use"
    used = error.details["used_by"]
    assert "layer 'box'" in used and "layer 'sky'" in used
    assert {"swatches.light", "character_styles.Heading", "variables.tone"} <= set(used)
    # Text that merely contains @brand, and the similarly named @brand-dark, are not uses.
    assert "layer 'handle'" not in used
    assert error.details["suggestions"][0]["detach"] is True
    assert p.state["swatches"] == before


def test_detach_writes_the_color_into_each_use_and_renders_the_same():
    p = referenced()
    pixels = p.render().tobytes()
    p.apply({"type": "swatch", "name": "brand", "delete": True, "detach": True})
    assert "brand" not in p.state["swatches"]
    layers = {layer["name"]: layer for layer in p.state["layers"]}
    assert layers["box"]["fill"] == "#cc0000"
    assert layers["sky"]["start"] == "mix(#cc0000, white, 30%)"
    assert layers["sky"]["end"] == "@brand-dark"
    assert layers["handle"]["text"] == "Follow @brand"
    assert p.state["swatches"]["light"] == "lighten(#cc0000, 10%)"
    assert p.state["character_styles"]["Heading"]["color"] == "#cc0000"
    assert p.state["variables"]["tone"] == "#cc0000"
    assert p.render().tobytes() == pixels
    p.undo()
    assert p.state["swatches"]["brand"] == "#cc0000"
    assert p.layer("box")["fill"] == "@brand"


def test_delete_unknown_swatch_and_cli(tmp_path, monkeypatch):
    p = referenced()
    with pytest.raises(VixlError, match="Unknown swatch: @nope"):
        p.apply({"type": "swatch", "name": "nope", "delete": True})
    from vixl.cli import dispatch

    monkeypatch.chdir(tmp_path)
    dispatch(["new", "30x30", "-o", "p.vixl"])
    dispatch(["swatch", "brand", "red"])
    dispatch(["swatch", "brand", "--delete"])
    assert "brand" not in Project.load(tmp_path / "p.vixl").state.get("swatches", {})


PEN = {"type": "pen", "name": "line", "points": [[10, 30], [110, 30]], "smooth": False, "stroke": "#0000ff",
       "stroke_width": 12}


@pytest.mark.parametrize("value", [0.5, "50%"])
def test_pen_takes_opacity(value):
    p = Project(120, 60, background="white")
    result = p.apply({**PEN, "opacity": value})
    assert p.layer("line")["opacity"] == 0.5
    pixel = p.render().convert("RGB").getpixel((60, 30))
    assert abs(pixel[0] - 128) <= 2 and abs(pixel[2] - 255) <= 1
    if isinstance(value, str):
        assert result["normalized"]
    p.apply({"type": "pen", "target": "line", "points": [[10, 30], [110, 30]], "smooth": False, "opacity": 1})
    assert p.layer("line")["opacity"] == 1


def test_pen_opacity_rejects_a_bare_percentage():
    with pytest.raises(VixlError, match="0–1 scale"):
        Project(60, 60).apply({**PEN, "opacity": 50})


def test_pen_opacity_matches_in_svg_and_pdf(tmp_path):
    import resvg_py

    p = Project(120, 60, background="white")
    p.apply({**PEN, "opacity": 0.5})
    raster = np.asarray(p.render().convert("RGB"), dtype=int)[30, 60]
    p.export(tmp_path / "pen.svg")
    svg = Image.open(io.BytesIO(resvg_py.svg_to_bytes(svg_string=(tmp_path / "pen.svg").read_text())))
    assert np.abs(np.asarray(svg.convert("RGB"), dtype=int)[30, 60] - raster).max() <= 3
    pdfium = pytest.importorskip("pypdfium2")
    p.export(tmp_path / "pen.pdf")
    page = pdfium.PdfDocument(str(tmp_path / "pen.pdf"))[0].render(scale=1).to_pil().convert("RGB")
    assert np.abs(np.asarray(page, dtype=int)[30, 60] - raster).max() <= 3


def test_pen_cli_opacity():
    from vixl.commands import compile_command

    op = compile_command(["pen", "--points", "[[0, 0], [10, 10]]", "--opacity", "40%"])
    assert op["opacity"] == "40%"


def test_mcp_apply_deletes_swatches_and_reports_users(tmp_path):
    import asyncio
    import json

    from vixl.interfaces import Session
    from vixl.mcp_tools import build_server

    server = build_server(Session(workspace=tmp_path))

    def call(tool, **arguments):
        async def run():
            result = await server.call_tool(tool, arguments)
            content = result[0] if isinstance(result, tuple) else result
            return json.loads(content[0].text)

        return asyncio.run(run())

    call("vixl_document", action="create", path="d.vixl", width=60, height=60)
    call("vixl_apply", operations=[
        {"type": "swatch", "name": "brand", "color": "red"},
        {"type": "pen", "name": "line", "points": [[5, 30], [55, 30]], "stroke": "@brand", "opacity": "50%"},
    ])
    with pytest.raises(Exception) as caught:
        call("vixl_apply", operations=[{"type": "swatch", "name": "brand", "delete": True}])
    assert "swatch_in_use" in str(caught.value) and "line" in str(caught.value)
    assert call("vixl_apply", operations=[{"type": "swatch", "name": "brand", "delete": True, "detach": True}])["success"]
