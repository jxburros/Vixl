"""Motifs a brief implies (vixl_reference's motifs field) and the catalog shapes that draw them."""

import asyncio
import io
import json

import numpy as np
import pytest
import resvg_py
from PIL import Image

from vixl import Project
from vixl.briefs import guide
from vixl.guidance import GUIDANCE, motif_registry, motifs
from vixl.objects import registry
from vixl.operations import OPERATION_TYPES
from vixl.plugins.organic.organic import PRESETS
from vixl.schema import operation_schema, validate_operation


def shapes_allowed():
    shape = {v["properties"]["type"]["const"]: v for v in
             operation_schema()["properties"]["operations"]["items"]["oneOf"]}["shape"]["properties"]["shape"]
    return set(shape.get("enum") or [e for option in shape.get("anyOf", []) for e in option.get("enum", [])])


def themes(brief):
    return {item["theme"]: item for item in guide(brief).get("motifs", [])}


def drawn_by(item):
    return {name for element in item["elements"]
            for name in element.get("shapes", []) + element.get("operations", []) + element.get("organic_presets", [])}


def test_coffee_brief_names_a_cup_with_steam_not_a_disc():
    found = themes("Instagram post for a harbor-side café's winter menu: flat white, cardamom bun")
    assert "coffee" in found
    cup = found["coffee"]["elements"][0]
    assert {"cup", "steam"} <= set(cup["shapes"]) and cup["object"] == "cup"
    assert "disc" in cup["instead_of"]


def test_lighthouse_brief_puts_the_lighthouse_in_filled_layered_water():
    result = guide("An animated intro: a lighthouse rises above three layered waves")
    found = {item["theme"]: item for item in result["motifs"]}
    assert "coast" in found
    elements = found["coast"]["elements"]
    water = next(e for e in elements if "water" in e.get("organic_presets", []))
    assert "line" in water["instead_of"]
    lighthouse = next(e for e in elements if "lighthouse" in e.get("shapes", []))
    assert "in the sea" in lighthouse["element"] and "bar" in lighthouse["instead_of"]
    assert {"reflection", "haze"} <= drawn_by(found["coast"])


def test_winter_market_brief_names_string_lights_and_the_sea_brief_water():
    found = themes("A print poster for a winter night market on the water with lanterns")
    assert {"market", "coast"} <= set(found)
    assert {"string-lights", "star-field", "lantern"} <= drawn_by(found["market"])
    assert "water" in drawn_by(found["coast"])


def test_night_city_brief_is_a_scene_with_skyline_motifs():
    result = guide("night city")
    assert result["matched"] == "scene"
    found = {item["theme"]: item for item in result["motifs"]}
    assert {"star-field", "reflection", "bokeh"} <= drawn_by(found["night-city"])
    assert "equal boxes" in found["night-city"]["elements"][0]["instead_of"]


def test_lake_brief_gets_the_water_preset_and_briefs_without_a_setting_get_no_motifs():
    assert "water" in drawn_by(themes("a calm lake at dawn")["lake"])
    assert "motifs" not in guide("a quarterly report with charts")
    assert motifs("Café") and motifs("cafe")[0]["theme"] == "coffee"
    assert motifs("sports report") == []  # 'port' only matches as a whole word


def test_guide_motifs_lists_every_theme_and_the_text_lives_in_the_registry():
    result = guide("motifs")
    assert result["text"] == GUIDANCE["motifs"]
    assert set(result["themes"]) == set(motif_registry())
    assert "motifs" in guide("scene")["guidance"]


def test_every_motif_names_real_shapes_presets_kinds_and_operations():
    allowed = shapes_allowed()
    kinds = registry()
    for name, theme in motif_registry().items():
        assert theme["title"] and theme["keywords"] and theme["elements"], name
        for element in theme["elements"]:
            assert element["element"] and element["instead_of"] and element["draw"], (name, element)
            assert set(element.get("shapes", [])) <= allowed, (name, element.get("shapes"))
            assert set(element.get("organic_presets", [])) <= set(PRESETS), name
            assert set(element.get("operations", [])) <= set(OPERATION_TYPES), (name, element.get("operations"))
            if "object" in element:
                assert element["object"] in kinds, (name, element["object"])
            if "example" in element:
                p = Project(1080, 1080, "#14263b")
                for op in element["example"]:
                    validate_operation(json.loads(json.dumps(op)))
                assert p.apply(element["example"])["success"]


def test_vixl_reference_returns_motifs_for_a_brief(tmp_path):
    from vixl.interfaces import Session
    from vixl.mcp_tools import build_server

    server = build_server(Session(workspace=tmp_path))
    result = asyncio.run(server.call_tool("vixl_reference", {"topic": "a coffee shop poster"}))
    content = result[0] if isinstance(result, tuple) else result
    data = json.loads(content[0].text)
    assert data["motifs"][0]["theme"] == "coffee"


@pytest.mark.parametrize("kind", ["cup", "steam", "lighthouse", "lantern"])
def test_motif_shapes_draw_the_same_in_svg_and_raster(kind):
    p = Project(200, 260, "#ffffff")
    p.apply({"type": "shape", "shape": kind, "name": "it", "x": 20, "y": 10, "width": 160, "height": 240,
             "fill": "#14263b"})
    raster = np.asarray(p.render().convert("L")) < 128
    svg = p.export(format="SVG", svg_policy="strict").decode()
    drawn = np.asarray(Image.open(io.BytesIO(resvg_py.svg_to_bytes(svg_string=svg))).convert("L")) < 128
    assert raster.sum() > 1500
    assert (raster & drawn).sum() / (raster | drawn).sum() > 0.98


def test_cup_handle_and_lighthouse_window_are_holes():
    p = Project(200, 200, "#ffffff")
    p.apply({"type": "shape", "shape": "cup", "name": "cup", "x": 0, "y": 0, "width": 200, "height": 200,
             "fill": "#000000"})
    image = np.asarray(p.render().convert("L"))
    assert image[87, 146] > 200  # inside the handle ring
    assert image[60, 60] < 50  # the body is solid
    q = Project(200, 400, "#ffffff")
    q.apply({"type": "shape", "shape": "lighthouse", "name": "tower", "x": 0, "y": 0, "width": 200, "height": 400,
             "fill": "#000000"})
    image = np.asarray(q.render().convert("L"))
    assert image[98, 100] > 200  # the lantern room window
    assert image[200, 100] < 50  # the tower
