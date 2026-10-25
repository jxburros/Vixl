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


NEW_THEMES = {
    "bakery": "A poster for a village bakery: sourdough, croissants and Saturday buns",
    "garden": "Spring plant sale at the community garden: herbs, seedlings and houseplants",
    "winter": "A Christmas card with snowflakes and a warm winter message",
    "sport": "Registration flyer for the city marathon and fun run",
    "tech": "Landing page art for a developer tool launch: a startup's new API",
    "wellness": "Yoga and meditation retreat weekend, with spa treatments",
    "travel": "Instagram carousel for a backpacking trip: itinerary and passport stamps",
    "books": "Book club night at the library: a new novel and poetry reading",
    "party": "Invitation to a kids' birthday party with balloons and confetti",
}


@pytest.mark.parametrize("theme", sorted(NEW_THEMES))
def test_new_themes_match_their_briefs_and_answer_the_three_questions(theme):
    found = themes(NEW_THEMES[theme])
    assert theme in found
    elements = found[theme]["elements"]
    assert len(elements) >= 3
    # The object, what it emits or reflects, and what frames it: each is a drawn element with its replaced
    # placeholder, and the first one names a catalog shape or preset that draws the object.
    assert elements[0].get("shapes") or elements[0].get("organic_presets")
    assert any({"haze", "reflection", "bokeh", "star-field", "string-lights", "look"} & set(e.get("operations", []))
               or "steam" in e.get("shapes", []) for e in elements[1:])
    assert all(e["instead_of"] and e["draw"] for e in elements)


def test_the_guidance_text_asks_the_three_questions_and_names_the_new_shapes():
    text = GUIDANCE["motifs"]
    for fragment in ("what is the object", "emit or reflect", "frames it"):
        assert fragment in text
    for shape in ("microphone", "snowflake", "leaf", "book", "balloon"):
        assert shape in text
    assert "form fog" in text


def test_bakery_is_its_own_theme_and_coffee_keeps_the_cup():
    assert motifs("sourdough bakery")[0]["theme"] == "bakery"
    assert "bakery" not in motif_registry()["coffee"]["keywords"]
    assert motifs("a cafe menu")[0]["theme"] == "coffee"


def test_new_theme_keywords_stay_whole_words_and_ignore_common_documents():
    assert motifs("a passport renewal checklist")[0]["theme"] == "travel"
    for brief in ("a quarterly report with charts", "pie chart of cookie consent by third party", "customer journey map",
                  "press release for the board"):
        assert motifs(brief) == [], brief


def test_the_coast_and_lake_themes_draw_fog_with_the_haze_operation():
    for name in ("coast", "lake"):
        fog = [e for e in motif_registry()[name]["elements"] if "form fog" in e["draw"]]
        assert len(fog) == 1 and "haze" in fog[0]["operations"], name
        assert "behind" in fog[0]["draw"] or name == "lake"
        assert fog[0]["example"][0]["form"] == "fog"
    assert any("fog" in e["element"] or "mist" in e["element"] for e in motif_registry()["coast"]["elements"])


def test_the_music_theme_draws_the_microphone_with_its_own_shape():
    mic = motif_registry()["music"]["elements"][1]
    assert mic["shapes"] == ["microphone"] and "capsule" not in mic["draw"]
    assert "capsule" in mic["instead_of"]  # the composed stand-in it replaces


NEW_SHAPES = {"microphone": 0.43, "snowflake": 1.0, "leaf": 0.63, "book": 1.335, "balloon": 0.585}
# Cut-outs each shape has (a grille slot, a vein, a line of text, a highlight): subpaths wound against the body.
CUTOUTS = {"microphone": 4, "snowflake": 0, "leaf": 7, "book": 8, "balloon": 1}


@pytest.mark.parametrize("height", [96, 240])
@pytest.mark.parametrize("kind", sorted(NEW_SHAPES))
def test_new_motif_shapes_draw_the_same_in_svg_and_raster_at_their_own_proportions(kind, height):
    width = round(height * NEW_SHAPES[kind])
    p = Project(width + 20, height + 20, "#ffffff")
    p.apply({"type": "shape", "shape": kind, "name": "it", "x": 10, "y": 10, "width": width, "height": height,
             "fill": "#14263b"})
    raster = np.asarray(p.render().convert("L")) < 128
    svg = p.export(format="SVG", svg_policy="strict").decode()
    assert "<image" not in svg
    drawn = np.asarray(Image.open(io.BytesIO(resvg_py.svg_to_bytes(svg_string=svg))).convert("L")) < 128
    assert raster.sum() > 0.1 * width * height
    assert (raster & drawn).sum() / (raster | drawn).sum() > 0.96


@pytest.mark.parametrize("kind", sorted(NEW_SHAPES))
def test_new_motif_shapes_are_plain_curves_with_cutouts_wound_against_the_body(kind):
    import re

    from vixl.geometry import path_extents, path_polygons
    from vixl.shape_catalog import path
    from vixl.vector_strokes import area

    w, h = 100 * NEW_SHAPES[kind], 100.0
    data = path({"shape": kind, "width": w, "height": h})
    # Arcs are already cubic curves: the exporters and the renderer flatten one command set.
    assert set(re.findall(r"[A-Za-z]", data)) <= set("MLCZ")
    signs = [area(points) > 0 for points in path_polygons(data)]
    assert sum(1 for s in signs if not s) == CUTOUTS[kind]
    assert signs[0] and sum(signs) >= 1
    x0, y0, x1, y1 = path_extents(data)
    assert x0 >= -0.5 and y0 >= -0.5 and x1 <= w + 0.5 and y1 <= h + 0.5  # inside the box
    assert (x1 - x0) >= 0.78 * w and (y1 - y0) >= (0.9 if kind == "snowflake" else 0.95) * h  # and filling it


@pytest.mark.parametrize("kind", sorted(NEW_SHAPES))
def test_new_motif_shapes_stay_legible_small_and_keep_their_cutouts_large(kind):
    def ink(height):
        width = round(height * NEW_SHAPES[kind])
        p = Project(width, height, "#ffffff")
        p.apply({"type": "shape", "shape": kind, "name": "it", "x": 0, "y": 0, "width": width, "height": height,
                 "fill": "#000000"})
        return np.asarray(p.render().convert("L")) < 128

    small = ink(24)
    assert 0.15 < small.mean() < 0.8, small.mean()  # a mark on the page, not a smudge or a hairline
    large = ink(400)
    # Cut-outs cost ink, so the large drawing is lighter than a solid silhouette of the same outline would be.
    assert 0.1 < large.mean() < small.mean() + 0.2


def test_the_motif_shapes_have_their_cutouts_where_the_drawing_says():
    def shape(kind, w, h):
        p = Project(w, h, "#ffffff")
        p.apply({"type": "shape", "shape": kind, "name": "it", "x": 0, "y": 0, "width": w, "height": h, "fill": "#000000"})
        return np.asarray(p.render().convert("L"))

    mic = shape("microphone", 172, 400)  # 4 px per design unit, the cradle's left edge at x = 6
    assert mic[57, 86] > 200 and mic[40, 86] < 50  # a grille slot, and the solid head above it
    assert mic[300, 86] < 50 and mic[390, 40] < 50  # the stem and the base
    leaf = shape("leaf", 248, 392)  # 4 px per design unit, the top at y = 2
    assert leaf[192, 126] > 200 and leaf[192, 80] < 50  # the midrib, and leaf beside it
    assert leaf[388, 123] < 50 and leaf[390, 60] > 200  # the stem below the blade, nothing beside it
    book = shape("book", 380, 285)  # 4 px per design unit, from (2.5, 8)
    assert book[120, 190] > 200 and book[120, 100] < 50  # the gap at the spine, and a page
    balloon = shape("balloon", 232, 397)  # 4 px per design unit from (2, 0)
    assert (balloon[50:90, 30:70] > 200).sum() > 20 and balloon[132, 116] < 50  # the highlight, and the body
    assert balloon[330, 116] < 50 and balloon[330, 30] > 200  # the knot under the body, nothing beside it


def test_snowflake_thickness_sets_the_arm_width_and_is_listed_for_discovery():
    from vixl.shape_catalog import SHAPE_PARAMETERS

    def ink(**extra):
        p = Project(200, 200, "#ffffff")
        p.apply({"type": "shape", "shape": "snowflake", "name": "it", "x": 0, "y": 0, "width": 200, "height": 200,
                 "fill": "#000000", **extra})
        return (np.asarray(p.render().convert("L")) < 128).sum()

    assert ink(thickness=0.05) < ink() < ink(thickness=0.11)
    assert ink(thickness="11%") == ink(thickness=0.11)
    assert SHAPE_PARAMETERS["snowflake"] == ("thickness",)


def test_motif_shapes_scale_with_their_box_and_export_as_one_outline():
    p = Project(400, 300, "#ffffff")
    p.apply([{"type": "shape", "shape": kind, "name": kind, "x": 10 + 70 * index, "y": 10, "width": 60, "height": 120,
              "fill": "#14263b", "stroke": "#c1121f", "stroke_width": 2} for index, kind in enumerate(sorted(NEW_SHAPES))])
    svg = p.export(format="SVG", svg_policy="strict").decode()
    assert svg.count("<path") >= len(NEW_SHAPES) and "<image" not in svg
    assert p.export(format="PDF").startswith(b"%PDF") and p.export(format="PPTX")[:2] == b"PK"
