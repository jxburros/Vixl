"""The brand-board workflow: brand guidelines drawn from brand.json (#581)."""

import base64
import io
import json

import pytest
from PIL import Image

from vixl import Project, VixlError
from vixl.interfaces import Session
from vixl.workflows import describe, dispatch

from test_brand_system import PALETTE, spec


def logo_png():
    image = Image.new("RGBA", (200, 80), (0, 68, 170, 255))
    buffer = io.BytesIO()
    image.save(buffer, "PNG")
    return base64.b64encode(buffer.getvalue()).decode()


def kit():
    return {
        "name": "Northwind",
        "palette": {**PALETTE, "muted": "#9a9a9a", "extra": {"wood": {"color": "#d2a465", "max_fraction": 0.1}}},
        "fonts": {"heading": spec("Anton"), "body": spec("Typer"), "hand": spec("Hand"), "allowed": ["Anton", "Typer"]},
        "stages": {"display": "hand"},
        "logos": [{"name": "logo", "data_base64": logo_png()}],
        "logo": {"clear_space": 0.5, "min_size": "10mm"},
        "colors": {"strict": True, "tolerance": 4},
        "minimum_contrast": 4.5,
        "required_elements": ["logo"],
        "presets": {"night": {"palette": {"background": "#111111", "ink": "#f5f5f5", "surface": "#222222"}}},
    }


def test_brand_board_draws_every_decision_and_exports_pdf(tmp_path):
    (tmp_path / "brand.json").write_text(json.dumps(kit()))
    session = Session(workspace=tmp_path)
    result = dispatch(session, "brand-board", {"output": "guide/brand.pdf", "document": "guide/brand.vixl"})
    assert result["pages"] == ["cover", "palette", "type-headings", "type-text", "logos", "rules"]
    assert (tmp_path / "guide/brand.pdf").read_bytes().startswith(b"%PDF")
    assert sorted(result["files"]) == ["guide/brand.pdf", "guide/brand.vixl"]
    board = Project.load(tmp_path / "guide/brand.vixl")
    from vixl.pages import page_content, page_list

    layers = {page["name"]: {layer["name"]: layer for layer in page_content(board, page)["layers"]}
              for page in page_list(board)}
    assert layers["palette"]["swatch-accent"]["fill"] == "@accent" and "extra-1" in layers["palette"]
    # muted (#9a9a9a) on white fails 4.5:1, and the rules page says so.
    assert "too low" in layers["palette"]["pair-muted-background-ratio"]["text"]
    display = layers["type-headings"]["type-headings-display"]
    assert display["font"] == board.state["fonts"]["hand"] and display["font_role"] == "display"
    assert "role hand" in layers["type-headings"]["type-headings-display-meta"]["text"]
    assert "logo-1-clear-1" in layers["logos"] and "logo-1-on-2" in layers["logos"]
    dont = layers["rules"]["rules-2"]["text"]
    assert "Anton, Typer" in dont and "muted text on background" in dont and "10mm" in dont and "wood" in dont
    assert "0.5 × the logo height" in layers["rules"]["rules-1"]["text"]
    with pytest.raises(VixlError, match="exists"):
        dispatch(session, "brand-board", {"output": "guide/brand.pdf"})
    night = dispatch(session, "brand-board", {"output": "guide/night.vixl", "preset": "night"})
    assert night["preset"] == "night"
    assert Project.load(tmp_path / "guide/night.vixl").state["swatches"]["background"] == "#111111"
    assert "brand-board" in describe()["actions"]


def test_brand_board_needs_a_brand(tmp_path):
    with pytest.raises(VixlError, match="brand.json"):
        dispatch(Session(workspace=tmp_path), "brand-board", {"output": "b.pdf"})


def test_brand_board_and_validate_accept_tiered_contrast_and_facts(tmp_path):
    # minimum_contrast tiers (#527) and group facts are valid brand.json fields next to the brand-system ones.
    brand = {**kit(), "minimum_contrast": {"text": 4.5, "large_text": 3.0}, "facts": {"product": {"value": "Vixl"}}}
    (tmp_path / "brand.json").write_text(json.dumps(brand))
    session = Session(workspace=tmp_path)
    result = dispatch(session, "brand-board", {"output": "guide/brand.vixl"})
    board = Project.load(tmp_path / "guide/brand.vixl")
    from vixl.pages import page_content, page_list

    texts = [layer.get("text", "") for page in page_list(board) for layer in page_content(board, page)["layers"]]
    assert result["pages"] and any("4.5:1" in text for text in texts)
