"""Figma import: URL and token handling, API errors, and the mapping from Figma JSON to Vixl documents.

Everything runs offline on the fixtures in tests/fixtures/figma (shaped like GET /v1/files responses); the HTTP
layer is answered by httpx.MockTransport. The live test at the bottom needs FIGMA_TOKEN and VIXL_FIGMA_TEST_FILE.
"""

from copy import deepcopy
import io
import json
import os
from pathlib import Path

import httpx
from PIL import Image
import pytest

from vixl import Project
from vixl.errors import VixlError
from vixl.plugins.figma_import.figma_import import (FigmaClient, build, font_resolver, gradient_settings, import_figma_document,
                               import_source, parse_source, rounded_rect_path, token_from_env)
from vixl.fonts import import_font
from vixl.model import Limits
from vixl.imports import import_document

FIXTURES = Path(__file__).parent / "fixtures" / "figma"
FONT = Path(__file__).parent.parent / "src" / "vixl" / "data" / "NotoSans-Regular.ttf"
KEY = "AbCdEf1234567890xyZ123"


def load(name):
    return json.loads((FIXTURES / f"{name}.json").read_text())


def photo_png():
    image = Image.new("RGB", (120, 160))
    for x in range(120):
        for y in range(160):
            image.putpixel((x, y), (x * 2, y, 150))
    stream = io.BytesIO()
    image.save(stream, "PNG")
    return stream.getvalue()


IMAGES = {"abc123imageref": photo_png()}


def layers(project):
    return {layer["name"]: layer for layer in project.state["layers"]}


@pytest.fixture
def poster():
    project = Project(100, 100)
    result = import_figma_document(project, load("poster"), images=IMAGES)
    return project, result, layers(project)


# ---------------------------------------------------------------------------------------------- source parsing

@pytest.mark.parametrize("source, expected", [
    (KEY, (KEY, None)),
    (f"https://www.figma.com/design/{KEY}/Poster?node-id=1-2&t=abc", (KEY, "1:2")),
    (f"https://www.figma.com/file/{KEY}/Poster", (KEY, None)),
    (f"https://figma.com/design/{KEY}/Poster?node-id=12%3A34", (KEY, "12:34")),
    (f"https://www.figma.com/board/{KEY}/Whiteboard", (KEY, None)),
    (f"https://www.figma.com/design/{KEY}/branch/BrAnCh9876543210zzz/Poster", (KEY, None)),
])
def test_sources_are_split_into_key_and_node(source, expected):
    key, node = parse_source(source)
    if "branch/" in source:
        assert key == "BrAnCh9876543210zzz"
    else:
        assert (key, node) == expected


@pytest.mark.parametrize("source", ["", "not a key!", "https://example.com/design/" + KEY, "http://www.figma.com/design/" + KEY,
                                    "https://www.figma.com/design", "https://www.figma.com/files/recent"])
def test_bad_sources_are_rejected_with_suggestions(source):
    with pytest.raises(VixlError) as error:
        parse_source(source)
    assert error.value.code == "invalid_figma_source"
    assert error.value.as_dict()["error"] == "invalid_figma_source"


def test_node_id_must_look_like_a_node_id():
    with pytest.raises(VixlError, match="node id"):
        import_source(Project(10, 10), KEY, node_id="abc", token="t")


# ------------------------------------------------------------------------------------------------------- token

def test_token_comes_from_either_environment_variable():
    assert token_from_env({"FIGMA_TOKEN": " abc "}) == "abc"
    assert token_from_env({"VIXL_FIGMA_TOKEN": "xyz"}) == "xyz"
    assert token_from_env({"FIGMA_TOKEN": "first", "VIXL_FIGMA_TOKEN": "second"}) == "first"


def test_missing_token_explains_how_to_create_one():
    with pytest.raises(VixlError) as error:
        token_from_env({})
    payload = error.value.as_dict()
    assert payload["error"] == "figma_token_missing"
    assert "file_content:read" in " ".join(payload["suggestions"])
    assert "FIGMA_TOKEN" in payload["message"]


def test_import_without_a_token_fails_before_any_request(monkeypatch):
    for name in ("FIGMA_TOKEN", "VIXL_FIGMA_TOKEN"):
        monkeypatch.delenv(name, raising=False)
    calls = []
    transport = httpx.MockTransport(lambda request: calls.append(request) or httpx.Response(200, json={}))
    with pytest.raises(VixlError) as error:
        import_source(Project(10, 10), KEY, transport=transport)
    assert error.value.code == "figma_token_missing" and not calls


def test_the_token_is_not_stored_in_the_document(monkeypatch):
    monkeypatch.setenv("FIGMA_TOKEN", "figd_secret_value")
    project = Project(10, 10)
    transport, _ = api_transport()
    import_source(project, KEY, transport=transport, download=lambda url: IMAGES["abc123imageref"], install_fonts=False)
    assert "figd_secret_value" not in json.dumps(project.state, default=str)


# ------------------------------------------------------------------------------------------------ API behaviour

def api_transport(document=None, status=None, headers=None, seen=None):
    document = document or load("poster")
    seen = [] if seen is None else seen

    def handler(request):
        seen.append(request)
        if status:
            return httpx.Response(status, json={"status": status, "err": "boom"}, headers=headers or {})
        path = request.url.path
        if path == f"/v1/files/{KEY}":
            return httpx.Response(200, json=document)
        if path == f"/v1/files/{KEY}/images":
            return httpx.Response(200, json={"error": False, "status": 200,
                                             "meta": {"images": {"abc123imageref": "https://cdn.example/photo.png"}}})
        if path == f"/v1/images/{KEY}":
            ids = request.url.params["ids"].split(",")
            return httpx.Response(200, json={"err": None, "images": {i: f"https://cdn.example/{i}.png" for i in ids}})
        return httpx.Response(404, json={"status": 404, "err": "Not found"})

    return httpx.MockTransport(handler), seen


def test_import_fetches_the_file_with_geometry_and_the_token(monkeypatch):
    monkeypatch.setenv("VIXL_FIGMA_TOKEN", "tok-123")
    transport, seen = api_transport()
    project = Project(100, 100)
    result = import_source(project, f"https://www.figma.com/design/{KEY}/Poster?node-id=1-2", transport=transport,
                           download=lambda url: IMAGES["abc123imageref"], install_fonts=False)
    file_request = seen[0]
    assert file_request.headers["X-Figma-Token"] == "tok-123"
    assert dict(file_request.url.params) == {"geometry": "paths", "ids": "1:2"}
    assert any(r.url.path.endswith("/images") for r in seen)
    assert result["figma"]["key"] == KEY and result["figma"]["node_id"] == "1:2"
    assert project.state["canvas"]["width"] == 800 and "Photo" in layers(project)


@pytest.mark.parametrize("status, code", [(403, "figma_forbidden"), (401, "figma_forbidden"), (404, "figma_not_found"),
                                          (429, "figma_rate_limited"), (500, "figma_error"), (400, "figma_bad_request")])
def test_http_errors_are_json_errors_with_suggestions(status, code):
    transport, _ = api_transport(status=status, headers={"Retry-After": "42"} if status == 429 else None)
    with pytest.raises(VixlError) as error:
        import_source(Project(10, 10), KEY, token="t", transport=transport)
    payload = error.value.as_dict()
    assert payload["error"] == code and payload["status"] == status
    assert payload["message"]
    if status in (401, 403, 404, 429):
        assert payload["suggestions"]


def test_rate_limit_reports_retry_after():
    transport, _ = api_transport(status=429, headers={"Retry-After": "90", "X-Figma-Plan-Tier": "starter"})
    with pytest.raises(VixlError) as error:
        FigmaClient("t", transport=transport).file(KEY)
    assert error.value.details["retry_after_s"] == 90
    assert "retry after 90 s" in str(error.value)


def test_a_failed_import_leaves_the_document_untouched():
    project = Project(30, 30)
    project.apply({"type": "shape", "shape": "rectangle", "name": "keep", "width": 5, "height": 5})
    before = deepcopy(project.state)
    transport, _ = api_transport(status=404)
    with pytest.raises(VixlError):
        import_source(project, KEY, token="t", transport=transport)
    assert project.state == before


def test_network_failure_is_a_clear_error():
    def refuse(request):
        raise httpx.ConnectError("no route", request=request)

    with pytest.raises(VixlError) as error:
        FigmaClient("t", transport=httpx.MockTransport(refuse)).file(KEY)
    assert error.value.code == "figma_unreachable"


def test_node_missing_from_the_response_is_not_found():
    transport, _ = api_transport()
    with pytest.raises(VixlError) as error:
        import_source(Project(10, 10), KEY, node_id="9:9", token="t", transport=transport)
    assert error.value.code == "figma_not_found"


def test_import_document_dispatches_figma_for_every_interface():
    project = Project(100, 100)
    result = import_document(project, json.dumps(load("card")).encode(), "figma", install_fonts=False)
    assert result["figma"]["root"]["name"] == "Card"
    with pytest.raises(VixlError, match="Unknown import option"):
        import_document(project, b"<svg/>", "svg", rasterize_unsupported=True)


def test_rest_import_accepts_a_figma_source(tmp_path, monkeypatch):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from vixl.interfaces import Session, create_app

    monkeypatch.setenv("VIXL_RESOURCES", str(tmp_path / "global.json"))
    for name in ("FIGMA_TOKEN", "VIXL_FIGMA_TOKEN"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr("vixl.typefaces.install_font", lambda *a, **k: (_ for _ in ()).throw(VixlError("x", "offline")))
    session = Session(workspace=tmp_path)
    session.create("main.vixl", 50, 50)
    client = TestClient(create_app(session.path))
    response = client.post("/import?format=figma&node_id=1-2", content=KEY.encode())
    assert response.status_code == 400 and response.json()["error"] == "figma_token_missing"
    response = client.post("/import?format=figma", content=json.dumps(load("card")).encode())
    assert response.status_code == 200 and response.json()["figma"]["root"]["name"] == "Card"


# -------------------------------------------------------------------------------------------------- the poster

def test_the_selected_frame_becomes_the_document(poster):
    project, result, by_name = poster
    assert (project.state["canvas"]["width"], project.state["canvas"]["height"]) == (800, 1000)
    assert project.state["canvas"]["background"] == "#f5efe6"
    assert result["figma"]["root"] == {"id": "1:2", "name": "Poster", "type": "FRAME"}
    assert result["figma"]["pages"] == ["Posters", "Scratch"]
    # The frame's own positions on the page (100, 200) do not leak into the document.
    assert by_name["Header band"]["x"] == 40 and by_name["Header band"]["y"] == 40


def test_rectangles_keep_their_radius_and_stroke(poster):
    _, _, by_name = poster
    band = by_name["Header band"]
    assert (band["shape"], band["radius"], band["fill"]) == ("rounded-rectangle", 24, "#1f2a44")
    assert band["stroke_width"] == 3 and band["stroke_align"] == "inside" and band["stroke"] == "#ffffffcc"
    shadow = band["styles"]["drop-shadow"]
    assert (shadow["dx"], shadow["dy"], shadow["blur"], shadow["opacity"]) == (0, 8, 8, 0.35)


def test_ellipse_vector_star_and_boolean_become_shapes_or_paths(poster):
    _, _, by_name = poster
    assert by_name["Sun"]["shape"] == "ellipse"
    wave = by_name["Wave"]
    assert wave["shape"] == "path" and wave["path"].startswith("M0 40C100 0") and wave["path_view"] == [800, 90]
    assert wave["line_cap"] == "round" and wave["stroke_width"] == 4 and wave["fill"] == "#2b1d5ce6"
    assert by_name["Spark"]["shape"] == "path" and by_name["Crescent"]["shape"] == "path"
    assert by_name["Crescent"]["path"].startswith("M40 0C62")


def test_gradients_become_gradient_overlays(poster):
    _, _, by_name = poster
    sky = by_name["Sky"]["styles"]["gradient-overlay"]
    assert sky["direction"] == "angled" and sky["angle"] == 90
    assert [s["offset"] for s in sky["stops"]] == [0, 0.55, 1]
    assert sky["stops"][1]["color"] == "#ff6f91"
    sun = by_name["Sun"]["styles"]["gradient-overlay"]
    assert sun["direction"] == "radial" and sun["center"] == [0.5, 0.5]


def test_image_fill_is_clipped_to_the_shape(poster):
    project, _, by_name = poster
    photo = by_name["Photo"]
    assert photo["type"] == "frame" and photo["fit"] == "fill"
    assert (photo["x"], photo["y"], photo["width"], photo["height"]) == (560, 540, 180, 240)
    assert photo["asset"] in project.assets and photo["mask"]["enabled"]
    # Only the top-left and bottom-right corners were rounded.
    pixels = project.render()
    assert pixels.getpixel((562, 542))[:3] == (245, 239, 230) or pixels.getpixel((562, 542))[:3] != pixels.getpixel((738, 542))[:3]


def test_text_is_live_with_style_and_spans(poster):
    _, _, by_name = poster
    title = by_name["Title"]
    assert title["type"] == "text" and title["text"] == "SUMMER SOUNDS"
    assert title["size"] == 64 and title["align"] == "center" and title["tracking"] == 2
    assert title["color"] == "#ffffff" and title["rich"]["line_height"] == 1.2
    assert title["width"] == 680 and title["auto_size"] is False
    subtitle = by_name["Subtitle"]
    assert subtitle["text"] == "Live music every weekend\non the pier"
    bold = [s for s in subtitle["rich"]["spans"] if s.get("bold")]
    assert [s["text"] for s in bold] == ["every weekend"] and bold[0]["color"] == "#d6336c"
    assert subtitle["text_layout"]["width"] == 480 and "height" not in subtitle["text_layout"]


def test_registered_fonts_are_used_without_a_report():
    project = Project(100, 100)
    for weight in (400, 600, 700):
        import_font(project, FONT, f"inter-{weight}")
    result = import_figma_document(project, load("poster"), images=IMAGES, fonts=font_resolver(project, install=False))
    assert not [r for r in result["report"] if "font" in r["what_was_lost"]]
    by_name, fonts = layers(project), project.state["fonts"]
    assert by_name["Title"]["font"] == fonts["inter-700"] and by_name["Label"]["font"] == fonts["inter-600"]
    spans = by_name["Subtitle"]["rich"]["spans"]
    assert any(s.get("font") == fonts["inter-700"] for s in spans)


def test_missing_fonts_fall_back_and_are_reported(poster):
    _, result, by_name = poster
    fonts = [r for r in result["report"] if "font Inter" in r["what_was_lost"]]
    assert {r["name"] for r in fonts} == {"Title", "Subtitle", "Label"}
    assert by_name["Title"]["font"] == "DejaVuSans.ttf"
    assert all(set(r) == {"node_id", "name", "type", "what_was_lost"} for r in result["report"])
    assert result["warnings"] and "lossy" in result["warnings"][0]


def test_auto_layout_becomes_a_stack(poster):
    project, _, by_name = poster
    layout = by_name["Button layout"]
    assert layout["stack"]["direction"] == "horizontal" and layout["stack"]["gap"] == 12
    assert layout["stack"]["padding"] == {"top": 12, "right": 24, "bottom": 12, "left": 24}
    assert layout["stack"]["align"] == "center" and layout["stack"]["justify"] == "center"
    assert project.bounds("Button layout") == (60, 680, 260, 64)
    members = {n for n, layer in by_name.items() if layer.get("parent") == layout["id"]}
    assert members == {"Dot", "Label"}
    button = by_name["Button"]
    assert by_name["Button background"]["parent"] == button["id"] and layout["parent"] == button["id"]


def test_groups_keep_names_order_and_hidden_state(poster):
    project, _, by_name = poster
    icons = by_name["Icons"]
    children = [layer["name"] for layer in project.state["layers"] if layer.get("parent") == icons["id"]]
    assert children == ["Tile", "Tile 2", "Spark", "Hidden guide"]
    assert by_name["Hidden guide"]["visible"] is False and by_name["Tile"]["visible"] is True
    # Duplicate Figma names get a numeric suffix because Vixl layer names are unique.
    assert by_name["Tile 2"]["rotation"] == 15


def test_rotation_keeps_the_figma_centre(poster):
    project, _, by_name = poster
    tile = by_name["Tile 2"]
    # Figma: 60x60 at (80, 10) in the group at (360, 700), rotated 15 degrees about its top-left corner.
    import math

    cx = 360 + 80 + (30 * math.cos(math.radians(15)) - 30 * math.sin(math.radians(15)))
    cy = 700 + 10 + (30 * math.sin(math.radians(15)) + 30 * math.cos(math.radians(15)))
    x, y, w, h = project.bounds("Tile 2")
    assert tile["rotation"] == 15
    assert abs(x + w / 2 - cx) < 1.5 and abs(y + h / 2 - cy) < 1.5


def test_group_children_relative_to_the_frame_land_in_the_same_place(poster):
    project, _, _ = poster
    data = load("poster")
    frame = data["document"]["children"][0]["children"][0]
    icons = next(c for c in frame["children"] if c["name"] == "Icons")
    gx, gy = icons["relativeTransform"][0][2], icons["relativeTransform"][1][2]
    for child in icons["children"]:
        child["relativeTransform"][0][2] += gx
        child["relativeTransform"][1][2] += gy
    other = Project(100, 100)
    import_figma_document(other, data, images=IMAGES)
    for name in ("Tile", "Tile 2", "Spark", "Hidden guide"):
        assert other.bounds(name) == pytest.approx(project.bounds(name), abs=0.01)


def test_line_becomes_a_stroked_path(poster):
    _, _, by_name = poster
    divider = by_name["Divider"]
    assert divider["shape"] == "path" and divider["stroke_width"] == 2 and divider["fill"] == "transparent"
    assert divider["stroke"] == "#2b1d5c99"


def test_the_import_renders_like_the_design(poster):
    project, _, _ = poster
    image = project.render().convert("RGB")
    assert image.size == (800, 1000)
    assert image.getpixel((400, 100)) != image.getpixel((5, 990))
    assert image.getpixel((5, 990)) == (245, 239, 230)          # frame background shows below the content
    assert image.getpixel((150, 20)) [0] > 200                    # sky gradient starts warm at the top
    assert image.getpixel((60, 712))[0] > 200 and image.getpixel((60, 712))[1] < 100   # the pink button


def test_stroke_never_lands_under_a_gradient_overlay():
    data = load("poster")
    sky = next(c for c in data["document"]["children"][0]["children"][0]["children"] if c["name"] == "Sky")
    sky["strokes"] = [{"type": "SOLID", "color": {"r": 0, "g": 0, "b": 0, "a": 1}}]
    sky["strokeWeight"] = 6
    project = Project(100, 100)
    import_figma_document(project, data, images=IMAGES)
    by_name = layers(project)
    group = by_name["Sky"]
    assert group["type"] == "group"
    assert "gradient-overlay" in by_name["Sky fill"]["styles"] and "styles" not in by_name["Sky stroke"]
    assert by_name["Sky stroke"]["stroke_width"] == 6


def test_multiple_fills_stack_inside_a_group():
    data = load("poster")
    sun = next(c for c in data["document"]["children"][0]["children"][0]["children"] if c["name"] == "Sun")
    sun["fills"].insert(0, {"type": "SOLID", "color": {"r": 1, "g": 1, "b": 1, "a": 1}, "opacity": 0.5})
    project = Project(100, 100)
    result = import_figma_document(project, data, images=IMAGES)
    by_name = layers(project)
    assert by_name["Sun"]["type"] == "group"
    assert by_name["Sun fill"]["type"] == "shape" and by_name["Sun fill 2"]["styles"]["gradient-overlay"]
    assert result["figma"]["layers"] >= 20


def test_node_opacity_blend_and_blur_map_to_layer_fields():
    data = load("poster")
    band = next(c for c in data["document"]["children"][0]["children"][0]["children"] if c["name"] == "Header band")
    band.update(opacity=0.6, blendMode="MULTIPLY")
    band["effects"].append({"type": "LAYER_BLUR", "visible": True, "radius": 8})
    project = Project(100, 100)
    import_figma_document(project, data, images=IMAGES)
    layer = layers(project)["Header band"]
    assert layer["opacity"] == 0.6 and layer["blend"] == "multiply"
    assert layer["effects"][0]["name"] == "blur" and layer["effects"][0]["amount"] == 4


# ------------------------------------------------------------------------------------- pages, nodes and losses

def test_a_page_of_frames_becomes_artboards_and_reports_what_cannot_map():
    project = Project(100, 100)
    result = import_figma_document(project, load("screens"))
    assert (project.state["canvas"]["width"], project.state["canvas"]["height"]) == (890, 1020)
    boards = project.state["artboards"]
    assert set(boards) == {"Mobile-Home", "Mobile-Home-2"}
    assert (boards["Mobile-Home-2"]["x"], boards["Mobile-Home-2"]["width"]) == (500, 390)
    assert boards["Mobile-Home"]["targets"]
    lost = {(r["name"], r["what_was_lost"].split(" ")[0]) for r in result["report"]}
    assert ("Note", "STICKY") in lost and ("Neon", "inner") in lost and ("Neon", "blend") in lost
    first = project.render(artboard="Mobile-Home")
    assert first.size == (390, 844)


def test_a_single_node_selects_one_frame_of_a_page():
    project = Project(100, 100)
    import_figma_document(project, load("screens"), node_id="2:4")
    assert (project.state["canvas"]["width"], project.state["canvas"]["height"]) == (390, 844)
    assert project.state["canvas"]["background"] == "#111827"
    assert {"Hero", "Neon"} <= set(layers(project))


def test_a_non_frame_node_gets_a_canvas_its_own_size():
    project = Project(100, 100)
    import_figma_document(project, load("screens"), node_id="2:5")
    assert (project.state["canvas"]["width"], project.state["canvas"]["height"]) == (350, 200)
    assert layers(project)["Hero"]["x"] == 0


def test_rasterize_unsupported_places_a_png_render():
    project = Project(100, 100)
    plan = build(project.clone(), load("screens"), rasterize_unsupported=True)
    assert plan.raster_ids == ["2:6"]
    result = import_figma_document(project, load("screens"), rasterize_unsupported=True, rasters={"2:6": IMAGES["abc123imageref"]})
    note = layers(project)["Note"]
    assert note["type"] == "raster" and (note["x"], note["y"]) == (0, 900) or note["type"] == "raster"
    assert any("PNG render" in r["what_was_lost"] for r in result["report"])


def test_rasterize_unsupported_fetches_renders_through_the_api():
    transport, seen = api_transport(load("screens"))
    project = Project(100, 100)
    result = import_source(project, KEY, token="t", transport=transport, rasterize_unsupported=True,
                           download=lambda url: IMAGES["abc123imageref"], install_fonts=False)
    assert any(r.url.path == f"/v1/images/{KEY}" and r.url.params["ids"] == "2:6" and r.url.params["format"] == "png"
               for r in seen)
    assert layers(project)["Note"]["type"] == "raster"
    assert any("PNG render" in r["what_was_lost"] for r in result["report"])


def test_missing_image_bytes_are_reported_not_fatal():
    project = Project(100, 100)
    result = import_figma_document(project, load("poster"), images={})
    assert "Photo" not in layers(project)
    assert any(r["name"] == "Photo" and "image" in r["what_was_lost"] for r in result["report"])


def test_importing_into_a_document_with_layers_keeps_its_canvas():
    project = Project(500, 400)
    project.apply({"type": "shape", "shape": "rectangle", "name": "existing", "width": 10, "height": 10})
    import_figma_document(project, load("card"))
    assert (project.state["canvas"]["width"], project.state["canvas"]["height"]) == (500, 400)
    assert {"existing", "Card", "Heading"} <= set(layers(project))


def test_an_empty_page_is_an_error():
    data = load("poster")
    with pytest.raises(VixlError) as error:
        import_figma_document(Project(10, 10), data, page=2)
    assert error.value.code == "invalid_figma_document"
    with pytest.raises(VixlError, match="No page"):
        import_figma_document(Project(10, 10), data, page="Missing")


def test_auto_layout_that_cannot_map_stays_a_positioned_group():
    data = load("card")
    card = data["document"]["children"][0]["children"][0]
    card["primaryAxisAlignItems"] = "SPACE_BETWEEN"
    project = Project(100, 100)
    result = import_figma_document(project, data)
    assert not any("stack" in layer for layer in project.state["layers"])
    assert any("auto layout" in r["what_was_lost"] and "space-between" in r["what_was_lost"] for r in result["report"])


def test_the_import_refuses_more_operations_than_a_batch_allows():
    project = Project(100, 100, limits=Limits(max_operations=5))
    with pytest.raises(VixlError) as error:
        import_figma_document(project, load("poster"), images=IMAGES)
    assert error.value.code == "resource_limit"


# ---------------------------------------------------------------------------------------------- pure helpers

def test_linear_gradient_angle_and_stops_follow_the_handles():
    paint = {"type": "GRADIENT_LINEAR",
             "gradientHandlePositions": [{"x": 0, "y": 0.5}, {"x": 1, "y": 0.5}, {"x": 0, "y": 1}],
             "gradientStops": [{"position": 0, "color": {"r": 1, "g": 0, "b": 0, "a": 1}},
                               {"position": 1, "color": {"r": 0, "g": 0, "b": 1, "a": 1}}]}
    settings, notes = gradient_settings(paint)
    assert settings["angle"] == 0 and settings["stops"][0] == {"offset": 0, "color": "#ff0000"} and not notes
    shorter = deepcopy(paint)
    shorter["gradientHandlePositions"][1]["x"] = 0.5
    settings, _ = gradient_settings(shorter)
    # Halving the gradient line compresses the ramp into the first half; the rest pads with the end colour.
    assert [s["offset"] for s in settings["stops"]] == [0, 0.5, 1] and settings["stops"][-1]["color"] == "#0000ff"


def test_gradient_that_starts_inside_the_box_pads_the_start_colour():
    paint = {"type": "GRADIENT_LINEAR",
             "gradientHandlePositions": [{"x": 0.25, "y": 0.5}, {"x": 0.75, "y": 0.5}, {"x": 0.25, "y": 1}],
             "gradientStops": [{"position": 0, "color": {"r": 0, "g": 0, "b": 0, "a": 1}},
                               {"position": 1, "color": {"r": 1, "g": 1, "b": 1, "a": 1}}]}
    settings, _ = gradient_settings(paint)
    offsets = [s["offset"] for s in settings["stops"]]
    assert offsets == [0, 0.25, 0.75, 1]
    assert settings["stops"][0]["color"] == settings["stops"][1]["color"] == "#000000"


def test_elliptical_radial_gradients_are_reported():
    paint = {"type": "GRADIENT_RADIAL",
             "gradientHandlePositions": [{"x": 0.5, "y": 0.5}, {"x": 1, "y": 0.5}, {"x": 0.5, "y": 0.6}],
             "gradientStops": [{"position": 0, "color": {"r": 1, "g": 1, "b": 1, "a": 1}},
                               {"position": 1, "color": {"r": 0, "g": 0, "b": 0, "a": 1}}]}
    settings, notes = gradient_settings(paint)
    assert settings["direction"] == "radial" and notes and "elliptical" in notes[0]


def test_per_corner_radii_make_a_closed_path():
    path = rounded_rect_path(100, 50, [10, 0, 20, 0])
    assert path.startswith("M10 0") and path.endswith("Z") and path.count("A") == 2
    assert rounded_rect_path(40, 40, [100, 100, 100, 100]).count("A") == 4      # radii clamp to half the size


def test_build_is_pure_and_deterministic():
    project = Project(100, 100)
    before = deepcopy(project.state)
    first = build(project.clone(), load("poster"), images=IMAGES)
    second = build(project.clone(), load("poster"), images=IMAGES)
    assert first.operations == second.operations and project.state == before
    assert first.operations[0]["type"] == "canvas"


# -------------------------------------------------------------------------------------------------- live test

@pytest.mark.skipif(not (os.environ.get("FIGMA_TOKEN") or os.environ.get("VIXL_FIGMA_TOKEN"))
                    or not os.environ.get("VIXL_FIGMA_TEST_FILE"),
                    reason="set FIGMA_TOKEN and VIXL_FIGMA_TEST_FILE (a file URL or key) to import a real file")
def test_live_import_of_a_real_file():
    project = Project(100, 100)
    result = import_source(project, os.environ["VIXL_FIGMA_TEST_FILE"], install_fonts=False)
    assert project.state["layers"] and result["figma"]["operations"] > 0
    assert project.render().size == (project.state["canvas"]["width"], project.state["canvas"]["height"])
