"""Merch and print mockups (#444): garments, bags, stickers and pins with named print areas, a garment colour, print
finishes and print-ready art per area."""

import base64
import io
import json
import math

import numpy as np
import pytest
from PIL import Image

from vixl import Project, VixlError, resources
from vixl.interfaces import Session
from vixl.plugins.brand_kit import finishes, mockups, print_art
from vixl.plugins.brand_kit.mockups import BUILTINS, placements
from vixl.workflows import dispatch

GARMENTS = ("tee", "long-sleeve", "crewneck", "hoodie")
STANDARD_AREAS = {"front-chest", "full-front", "back", "sleeve-l", "sleeve-r", "hem-tag", "inside-neck"}
WAVE_ONE = ("tee", "long-sleeve", "hoodie", "tote", "sticker", "sticker-kiss-cut", "enamel-pin", "poster-wall")
WAVE_TWO = ("crewneck", "cap", "beanie", "socks", "patch", "button")
TEAL = (0x2A, 0x9D, 0x8F)


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    monkeypatch.setenv("VIXL_RESOURCES", str(tmp_path / "global.json"))
    Project(600, 600, "#2a9d8f").save(tmp_path / "teal.vixl")
    disc = Project(600, 600, "transparent")
    disc.apply([{"type": "shape", "shape": "ellipse", "name": "disc", "x": 60, "y": 60, "width": 480, "height": 480,
                 "fill": "#d62828"}])
    disc.save(tmp_path / "disc.vixl")
    flat = Project(600, 600, "transparent")
    flat.apply([{"type": "shape", "shape": "rectangle", "name": "a", "x": 0, "y": 0, "width": 300, "height": 300,
                 "fill": "#d62828"},
                {"type": "shape", "shape": "rectangle", "name": "b", "x": 300, "y": 0, "width": 300, "height": 300,
                 "fill": "#fcbf49"},
                {"type": "shape", "shape": "rectangle", "name": "c", "x": 0, "y": 300, "width": 300, "height": 300,
                 "fill": "#003049"},
                {"type": "shape", "shape": "ellipse", "name": "d", "x": 330, "y": 330, "width": 240, "height": 240,
                 "fill": "#2a9d8f"}])
    flat.save(tmp_path / "flat.vixl")
    return tmp_path


def session(workspace):
    return Session(workspace / "teal.vixl", workspace=workspace)


def loaded(workspace, path):
    project = Project.load(workspace / path)
    project._workspace = workspace
    return project


def quad_size(corners):
    top = math.dist(corners[0], corners[1])
    side = math.dist(corners[0], corners[3])
    return top, side


def test_every_wave_one_product_is_there_and_wave_two_too():
    assert set(WAVE_ONE + WAVE_TWO) <= set(BUILTINS)


@pytest.mark.parametrize("name", [n for n in BUILTINS if any(p.get("print_size_mm") for p in placements(BUILTINS[n]).values())])
def test_print_areas_keep_the_aspect_of_their_print_size(name):
    for area, record in placements(BUILTINS[name]).items():
        if not record.get("print_size_mm"):
            continue
        top, side = quad_size(record["corners"])
        width, height = record["print_size_mm"]
        assert top / side == pytest.approx(width / height, rel=0.02), (name, area)
        assert record["corners"] and len(record["corners"]) == 4


@pytest.mark.parametrize("name", GARMENTS)
def test_garments_have_the_standard_areas_a_colour_and_base_layers(name):
    spec = BUILTINS[name]
    assert set(spec["areas"]) == STANDARD_AREAS and list(spec["areas"])[0] == "front-chest"
    assert spec["garment_color"].startswith("#") and "front-body" in spec["base"] and "back-body" in spec["base"]
    assert all(spec["areas"][a]["surface"] == "base" and spec["areas"][a]["clip_path"] for a in spec["areas"])
    names = {op["name"] for op in spec["operations"] if "name" in op}
    assert set(spec["base"]) <= names


def test_goods_have_their_areas():
    assert set(BUILTINS["tote"]["areas"]) == {"front"} and BUILTINS["tote"]["areas"]["front"]["print_size_mm"] == [280, 330]
    for name in ("sticker", "sticker-kiss-cut", "enamel-pin", "patch", "button"):
        assert set(BUILTINS[name]["areas"]) == {"face"}
    assert set(BUILTINS["socks"]["areas"]) == {"sock-l", "sock-r"} and set(BUILTINS["cap"]["areas"]) == {"front-panel"}
    assert set(BUILTINS["beanie"]["areas"]) == {"cuff"}
    assert BUILTINS["poster-wall"]["slots"][0]["print_size_mm"] == [297, 420]


@pytest.mark.parametrize("name", list(WAVE_ONE + WAVE_TWO))
def test_placing_art_fills_the_area_and_leaves_the_rest(workspace, name):
    s = session(workspace)
    spec = BUILTINS[name]
    every = placements(spec)
    area = next(iter(every))
    dispatch(s, "mockup", {"mockup": name, "output": "m.vixl", "place": {area: "teal.vixl"}, "finish": "none"})
    project = loaded(workspace, "m.vixl")
    links = [layer for layer in project.state["layers"] if layer["type"] == "link"]
    assert [layer["name"].removeprefix("design-") for layer in links] == [area]
    assert project.state["mockup"]["placed"] == {area: "teal.vixl"}
    image = project.render().convert("RGB")
    corners = every[area]["corners"]
    cx, cy = (sum(c[0] for c in corners) / 4, sum(c[1] for c in corners) / 4)
    assert np.abs(np.array(image.getpixel((round(cx), round(cy)))) - TEAL).max() < 40
    others = [a for a in every if a != area]
    for other in others:
        # The areas nobody placed a design in carry no link: nothing teal is drawn on them.
        assert f"design-{other}" not in [layer["name"] for layer in project.state["layers"]]


def test_a_bare_design_fills_the_slots_or_the_main_area(workspace):
    s = session(workspace)
    dispatch(s, "mockup", {"design": "teal.vixl", "mockup": ["tee", "poster-wall", "tote"], "output": "bare"})
    for item, expected in (("tee", ["front-chest"]), ("poster-wall", ["poster"]), ("tote", ["front"])):
        names = [layer["name"] for layer in loaded(workspace, f"bare/{item}.vixl").state["layers"] if layer["type"] == "link"]
        assert names == expected


def test_art_is_clipped_to_the_area_path(workspace):
    s = session(workspace)
    template = {"description": "A round window", "width": 600, "height": 600, "background": "#ffffff",
                "areas": {"window": {"corners": [[100, 100], [500, 100], [500, 500], [100, 500]],
                                     "print_size_mm": [100, 100], "surface": "#eeeeee",
                                     "clip_path": "M300 100 A200 200 0 1 0 300.1 100 Z"}}}
    dispatch(s, "mockup-save", {"name": "window", "value": template})
    dispatch(s, "mockup", {"mockup": "window", "output": "w.vixl", "place": {"window": "teal.vixl"}})
    image = loaded(workspace, "w.vixl").render().convert("RGB")
    assert np.abs(np.array(image.getpixel((300, 300))) - TEAL).max() < 30  # in the circle: the design
    assert image.getpixel((112, 112)) == (255, 255, 255)  # in the quad's corner, outside the clip path: bare
    link = loaded(workspace, "w.vixl").layer("window")
    assert link["clip"]


def test_place_names_must_be_areas_of_the_template(workspace):
    s = session(workspace)
    with pytest.raises(VixlError, match="no area 'front'") as caught:
        dispatch(s, "mockup", {"mockup": "tee", "output": "x.vixl", "place": {"front": "teal.vixl"}})
    assert "front-chest" in caught.value.details["allowed"] and "front-chest" in caught.value.details["suggestions"]
    with pytest.raises(VixlError, match="design must be"):
        dispatch(s, "mockup", {"mockup": "tee", "output": "x.vixl", "place": {"back": "nope.vixl"}})
    with pytest.raises(VixlError, match="Give a design"):
        dispatch(s, "mockup", {"mockup": "tee", "output": "x.vixl"})
    with pytest.raises(VixlError):
        dispatch(s, "mockup", {"mockup": "tee", "output": "x.vixl", "place": {"back": {"fit": "fit"}}})


def test_place_takes_a_per_area_fit_and_finish(workspace):
    s = session(workspace)
    dispatch(s, "mockup", {"mockup": "tee", "output": "x.vixl", "fit": "stretch",
                           "place": {"front-chest": "teal.vixl", "back": {"design": "flat.vixl", "fit": "fit",
                                                                       "finish": "puff"}}})
    project = loaded(workspace, "x.vixl")
    assert project.layer("front-chest")["fit"] == "stretch" and project.layer("back")["fit"] == "fit"
    assert project.layer("back")["styles"]["drop-shadow"] and "styles" not in project.layer("front-chest")


def layer_fields(project, skip=()):
    keep = ("type", "shape", "fill", "stroke", "stroke_width", "opacity", "blend", "x", "y", "width", "height", "path",
            "stops", "fill_gradient", "visible", "styles")
    return {layer["name"]: {**{k: json.dumps(layer.get(k), sort_keys=True, default=str) for k in keep},
                            "effects": json.dumps([{k: v for k, v in e.items() if k != "id"} for e in layer["effects"]],
                                                  sort_keys=True)}
            for layer in project.state["layers"] if layer["name"] not in skip}


def test_garment_color_recolours_only_the_base_layers(workspace):
    s = session(workspace)
    place = {"full-front": "teal.vixl", "sleeve-l": "teal.vixl"}
    dispatch(s, "mockup", {"mockup": "tee", "output": "light.vixl", "place": place})
    dispatch(s, "mockup", {"mockup": "tee", "output": "red.vixl", "place": place, "garment_color": "#c1121f"})
    light, red = loaded(workspace, "light.vixl"), loaded(workspace, "red.vixl")
    assert red.state["mockup"]["garment_color"] == "#c1121f" and light.state["mockup"]["garment_color"] == "#f1efe9"
    before, after = layer_fields(light), layer_fields(red)
    assert before.keys() == after.keys()
    changed = {name for name in before if before[name] != after[name]}
    spec = BUILTINS["tee"]
    surfaces = {"full-front-surface", "sleeve-l-surface"}
    assert changed == set(spec["base"]) | surfaces
    assert all(json.loads(after[name]["fill"]) == "#c1121f" for name in changed)
    # The shading is the same layers over a different colour: darker lower down, redder everywhere.
    image = red.render().convert("RGB")
    r, g, b = image.getpixel((330, 700))
    assert r > g + 60 and r > b + 60
    top, bottom = image.getpixel((330, 450)), image.getpixel((330, 850))
    assert sum(bottom) < sum(top)


def test_garment_color_needs_a_template_with_one(workspace):
    s = session(workspace)
    with pytest.raises(VixlError, match="no garment colour"):
        dispatch(s, "mockup", {"mockup": "phone", "output": "x.vixl", "design": "teal.vixl", "garment_color": "#000000"})
    with pytest.raises(VixlError):
        dispatch(s, "mockup", {"mockup": "tee", "output": "x.vixl", "design": "teal.vixl", "garment_color": "not a colour"})


def test_the_listing_shows_areas_print_sizes_and_garment_colours(workspace):
    listed = dispatch(session(workspace), "mockup-list", {})["mockups"]
    assert listed["tee"]["areas"]["sleeve-l"]["print_size_mm"] == [76, 76] and listed["tee"]["garment_color"] == "#f1efe9"
    assert listed["tee"]["slots"] == [] and listed["poster-wall"]["slots"] == ["poster"]
    assert listed["enamel-pin"]["areas"]["face"]["finish"] == "enamel"


def test_templates_with_areas_save_and_validate(workspace):
    s = session(workspace)
    area = {"corners": [[10, 10], [110, 10], [110, 110], [10, 110]], "print_size_mm": [50, 50]}
    template = {"width": 200, "height": 200, "operations": [{"type": "shape", "shape": "rectangle", "name": "body",
                                                              "x": 0, "y": 0, "width": 200, "height": 200,
                                                              "fill": "#ffffff"}],
                "areas": {"front": area}, "base": ["body"], "garment_color": "#223344"}
    dispatch(s, "mockup-save", {"name": "mini", "value": template})
    assert dispatch(s, "mockup-list", {})["mockups"]["mini"]["areas"]["front"]["print_size_mm"] == [50, 50]
    dispatch(s, "mockup", {"mockup": "mini", "output": "mini.vixl", "place": {"front": "teal.vixl"},
                           "garment_color": "#aa0000"})
    assert loaded(workspace, "mini.vixl").layer("body")["fill"] == "#aa0000"
    for bad, message in (
            ({"areas": {"Front Chest": area}}, "Area name"),
            ({"areas": {"front": {**area, "print_size_mm": [0, 5]}}}, "print_size_mm"),
            ({"areas": {"front": {"corners": area["corners"]}}}, "print_size_mm"),
            ({"areas": {"front": {**area, "clip_path": "nonsense"}}}, "[Pp]ath"),
            ({"areas": {"front": {**area, "finish": "glitter"}}}, "finish"),
            ({"areas": {"front": {**area, "cut": {"mode": "laser"}}}}, "cut"),
            ({"base": ["missing"]}, "base names layers"),
            ({"areas": {}}, "needs 1"),
            ({"slots": [{"name": "front", "corners": area["corners"]}]}, "unique")):
        with pytest.raises(VixlError, match=message):
            dispatch(s, "mockup-save", {"name": "bad", "value": {**template, **bad}})


def test_stickers_are_cut_around_the_art(workspace):
    s = session(workspace)
    dispatch(s, "mockup", {"mockup": ["sticker", "sticker-kiss-cut"], "output": "stickers", "place": {"face": "disc.vixl"}})
    for name, line in (("sticker", "#ffffff"), ("sticker-kiss-cut", "#9aa1ad")):
        project = loaded(workspace, f"stickers/{name}.vixl")
        order = [layer["name"] for layer in project.state["layers"]]
        cut = project.layer("face-cut")
        assert order.index("face-cut") < order.index("face") and cut["fill"] == "#ffffff" and cut["stroke"] == line
        assert cut["die_cut"]["targets"] == [project.layer("face")["id"]] and cut["styles"]["drop-shadow"]
        assert "face-surface" not in order and "clip" not in project.layer("face")
        # The vinyl border runs a few millimetres outside the disc, and the corners of the quad stay bare.
        image = project.render().convert("RGB")
        quad = BUILTINS[name]["areas"]["face"]["corners"]
        cx, cy = 600, (quad[0][1] + quad[2][1]) / 2
        radius = (quad[1][0] - quad[0][0]) * 0.4 / 0.6 * 0.6  # the disc fills 480 of 600 px of the quad
        edge = round(cy - radius * 1.0)
        assert image.getpixel((600, edge - 6)) == (255, 255, 255) or name == "sticker-kiss-cut"
        corner = image.getpixel((round(quad[0][0] + 6), round(quad[0][1] + 6)))
        assert corner != (255, 255, 255) or name == "sticker-kiss-cut"


def test_enamel_pin_has_a_metal_rim_and_the_enamel_finish_by_default(workspace):
    s = session(workspace)
    dispatch(s, "mockup", {"mockup": "enamel-pin", "output": "pin.vixl", "place": {"face": "disc.vixl"}})
    project = loaded(workspace, "pin.vixl")
    rim, art = project.layer("face-cut"), project.layer("face")
    assert rim["fill_gradient"]["stops"][0]["color"] == "#f4dc8e" and rim["die_cut"]["distance"] > 0
    assert art["styles"]["stroke"]["color"] == "#c9a24a"  # the enamel finish's metal line
    assert any(effect["name"] == "saturation" for effect in art["effects"])
    for finish in ("screen", "none"):
        dispatch(s, "mockup", {"mockup": "enamel-pin", "output": f"{finish}.vixl", "place": {"face": "disc.vixl"},
                               "finish": finish})
        assert "stroke" not in loaded(workspace, f"{finish}.vixl").layer("face").get("styles", {})
    assert not loaded(workspace, "none.vixl").layer("face")["effects"]


@pytest.fixture
def window(workspace):
    template = {"width": 600, "height": 600, "background": "#ffffff",
                "areas": {"face": {"corners": [[100, 100], [500, 100], [500, 500], [100, 500]],
                                   "print_size_mm": [100, 100], "surface": "#f4f4f4", "shade": False, "gloss": False}}}
    dispatch(session(workspace), "mockup-save", {"name": "window", "value": template})
    return workspace


@pytest.mark.parametrize("finish", list(finishes.FINISHES))
def test_each_finish_is_an_ordinary_look_stack_on_the_design(window, finish):
    s = session(window)
    dispatch(s, "mockup", {"mockup": "window", "output": "plain.vixl", "place": {"face": "flat.vixl"}})
    dispatch(s, "mockup", {"mockup": "window", "output": "done.vixl", "place": {"face": "flat.vixl"}, "finish": finish})
    plain, done = loaded(window, "plain.vixl"), loaded(window, "done.vixl")
    art = done.layer("face")
    assert not plain.layer("face")["effects"] and art["effects"]
    expected = {"screen": "gaussian-blur", "puff": "emboss", "embroidery": "emboss", "enamel": "saturation",
                "woven": "emboss"}[finish]
    assert expected in [effect["name"] for effect in art["effects"]]
    assert len(done.state["layers"]) >= len(plain.state["layers"])
    helpers = [layer["name"] for layer in done.state["layers"] if "-finish-" in layer["name"]]
    assert helpers == sorted(helpers, key=lambda n: done.state["layers"].index(done.layer(n))) or helpers
    a, b = np.asarray(plain.render().convert("RGB"), float), np.asarray(done.render().convert("RGB"), float)
    assert np.abs(a - b).mean() > 0.3  # the finish changes how the print looks
    assert b[100:500, 100:500].std() > 10  # and the art is still there


def test_finishes_clip_their_helper_layers_to_the_design(window):
    s = session(window)
    dispatch(s, "mockup", {"mockup": "window", "output": "emb.vixl", "place": {"face": "disc.vixl"},
                           "finish": "embroidery"})
    project = loaded(window, "emb.vixl")
    face = project.layer("face")
    threads = project.layer("face-finish-threads")
    assert threads["clip"] == face["id"] and threads["blend"] == "multiply"
    image = project.render().convert("RGB")
    assert image.getpixel((110, 110)) == (244, 244, 244)  # the quad's corner is outside the disc: no threads there


def test_hatch_lines_stay_in_their_box():
    from vixl.geometry import path_extents

    d = finishes.hatch_path(200, 120, 6, 52)
    x0, y0, x1, y1 = path_extents(d)
    assert x0 >= -0.1 and y0 >= -0.1 and x1 <= 200.1 and y1 <= 120.1
    assert d.count("M") > 30


def test_a_template_can_use_a_pack_asset_as_its_product_photo(workspace):
    data = io.BytesIO()
    Image.new("RGBA", (60, 40), "#8d99ae").save(data, format="PNG")
    resources.register("assets", "label", {"data_base64": base64.b64encode(data.getvalue()).decode(),
                                           "media_type": "png", "credit": "Studio A"}, workspace=workspace)
    s = session(workspace)
    template = {"width": 400, "height": 300, "background": "#ffffff",
                "operations": [{"type": "asset-place", "resource": "label", "x": 20, "y": 20, "width": 120,
                                "name": "label"}],
                "areas": {"face": {"corners": [[160, 40], [360, 40], [360, 240], [160, 240]],
                                   "print_size_mm": [50, 50]}}}
    dispatch(s, "mockup-save", {"name": "labelled", "value": template})
    dispatch(s, "mockup", {"mockup": "labelled", "output": "l.vixl", "place": {"face": "teal.vixl"}})
    project = loaded(workspace, "l.vixl")
    assert project.layer("label")["provenance"]["resource"] == "label"
    assert project.layer("label")["x"] == 20
    template["operations"][0]["resource"] = "missing"
    dispatch(s, "mockup-save", {"name": "unlabelled", "value": template})
    with pytest.raises(VixlError, match="not found") as caught:
        dispatch(s, "mockup", {"mockup": "unlabelled", "output": "u.vixl", "place": {"face": "teal.vixl"}})
    assert caught.value.code == "missing_asset"


# print-art


def pixel_count(image):
    return image.size


def printed_colours(path):
    with Image.open(path) as opened:
        pixels = np.asarray(opened.convert("RGBA"))
    visible = pixels[pixels[..., 3] >= 128][:, :3]
    return {tuple(int(c) for c in row) for row in np.unique(visible, axis=0)}


def test_print_art_writes_one_file_per_area_at_the_print_size(workspace):
    s = session(workspace)
    result = dispatch(s, "print-art", {"mockup": "tee", "output": "print", "dpi": 100,
                                       "place": {"front-chest": "flat.vixl", "sleeve-l": "disc.vixl"}})
    assert [row["area"] for row in result["areas"]] == ["front-chest", "sleeve-l"]
    for row, (width, height) in zip(result["areas"], ((1000, 1000), (299, 299))):
        assert row["pixels"] == [width, height] and row["dpi"] == 100
        with Image.open(workspace / row["file"]) as image:
            assert image.size == (width, height) and image.mode == "RGBA"
            assert image.info["dpi"][0] == pytest.approx(100, abs=0.1)
        assert (workspace / row["source"]).is_file()
    assert result["files"] == ["print/front-chest.png", "print/sleeve-l.png", "print/source/front-chest.vixl",
                               "print/source/sleeve-l.vixl"]
    # The sources are the editable print documents: the design linked into a canvas of the print size.
    source = loaded(workspace, "print/source/front-chest.vixl")
    assert source.state["canvas"]["width"] == 1000 and source.state["canvas"]["dpi"] == 100
    assert source.layer("art")["type"] == "link"
    with Image.open(workspace / "print/sleeve-l.png") as image:
        pixels = np.asarray(image.convert("RGBA"))
    assert pixels[0, 0, 3] == 0 and pixels[150, 150, 3] == 255  # transparent outside the disc, the red disc inside
    assert tuple(pixels[150, 150, :3]) == (0xD6, 0x28, 0x28)


def test_print_art_refuses_to_overwrite_and_checks_its_input(workspace):
    s = session(workspace)
    request = {"mockup": "tote", "output": "print", "dpi": 72, "place": {"front": "flat.vixl"}}
    dispatch(s, "print-art", request)
    with pytest.raises(VixlError, match="already exist"):
        dispatch(s, "print-art", request)
    assert dispatch(s, "print-art", {**request, "overwrite": True})["areas"][0]["pixels"] == [794, 935]
    with pytest.raises(VixlError, match="no print size"):
        dispatch(s, "print-art", {"mockup": "phone", "output": "p2", "design": "flat.vixl"})
    for bad in ({"dpi": 10}, {"spot_colors": 0}, {"spot_colors": 99}, {"separations": "tiff"}, {"choke_mm": -1},
                {"underbase": "yes"}):
        with pytest.raises(VixlError):
            dispatch(s, "print-art", {**request, "output": "p3", **bad})
    assert not (workspace / "p3").exists()
    with pytest.raises(VixlError, match="one template"):
        dispatch(s, "print-art", {"mockup": ["tote", "tee"], "output": "p4", "design": "flat.vixl"})


def test_print_art_respects_the_pixel_limits(workspace):
    s = session(workspace)
    with pytest.raises(VixlError, match="Dimensions|pixel limit") as caught:
        dispatch(s, "print-art", {"mockup": "tee", "output": "huge", "dpi": 1200, "place": {"full-front": "flat.vixl"}})
    assert caught.value.code == "resource_limit"
    assert not (workspace / "huge").exists()


def test_a_failed_print_art_run_leaves_no_files(workspace, monkeypatch):
    s = session(workspace)

    def boom(*args, **kwargs):
        raise VixlError("invalid_request", "stop")

    monkeypatch.setattr(print_art, "_separations", boom)
    with pytest.raises(VixlError, match="stop"):
        dispatch(s, "print-art", {"mockup": "tee", "output": "print", "dpi": 72, "spot_colors": 2,
                                  "place": {"sleeve-l": "flat.vixl"}})
    assert not list((workspace / "print").rglob("*.*"))


@pytest.mark.parametrize("inks", [1, 2, 3, 4])
def test_spot_separation_gives_at_most_n_colours(workspace, inks):
    s = session(workspace)
    result = dispatch(s, "print-art", {"mockup": "tee", "output": "print", "dpi": 72, "spot_colors": inks,
                                       "place": {"sleeve-l": "flat.vixl"}})
    row = result["areas"][0]
    spot = row["spot"]
    colours = printed_colours(workspace / spot["file"])
    assert 1 <= len(colours) <= inks and spot["colors"] == len(colours) <= inks
    assert [ink["color"] for ink in spot["inks"]] == sorted((ink["color"] for ink in spot["inks"]),
                                                            key=lambda c: -int(c[1:3], 16) * 0.2126 - int(c[3:5], 16) * 0.7152
                                                            - int(c[5:7], 16) * 0.0722)
    # One film positive per ink (black where it prints); together they cover exactly what the art prints.
    covered = np.zeros((215, 215), bool)
    for ink in spot["inks"]:
        with Image.open(workspace / ink["file"]) as sheet:
            film = np.asarray(sheet)
        assert set(np.unique(film)) <= {0, 255} and sheet.mode == "L"
        assert not (covered & (film == 0)).any()  # the inks never overlap
        covered |= film == 0
    with Image.open(workspace / row["file"]) as art:
        assert (covered == (np.asarray(art.convert("RGBA"))[..., 3] >= 128)).all()
    if inks == 4:
        assert {tuple(int(c[i:i + 2], 16) for i in (1, 3, 5)) for c in (ink["color"] for ink in spot["inks"])} >= {
            (0xD6, 0x28, 0x28), (0xFC, 0xBF, 0x49), (0x00, 0x30, 0x49)}


def test_separations_as_pdf_pages(workspace):
    pdfium = pytest.importorskip("pypdfium2")
    s = session(workspace)
    result = dispatch(s, "print-art", {"mockup": "tee", "output": "print", "dpi": 100, "spot_colors": 3,
                                       "separations": "pdf", "underbase": True, "garment_color": "#111111",
                                       "place": {"sleeve-l": "flat.vixl"}})
    spot = result["areas"][0]["spot"]
    assert spot["pdf"] == "print/sleeve-l-separations.pdf" and not any("file" in ink for ink in spot["inks"])
    assert spot["pages"][0] == "underbase" and len(spot["pages"]) == spot["colors"] + 1
    assert not list((workspace / "print").glob("sleeve-l-ink*.png"))
    document = pdfium.PdfDocument(str(workspace / spot["pdf"]))
    assert len(document) == spot["colors"] + 1
    page = document[0]
    assert page.get_width() == pytest.approx(76 / 25.4 * 72, abs=1.5)  # the page is the print size


def test_the_underbase_is_for_dark_garments_only(workspace):
    s = session(workspace)
    request = {"mockup": "tee", "output": "dark", "dpi": 72, "underbase": True, "place": {"sleeve-l": "disc.vixl"}}
    dark = dispatch(s, "print-art", {**request, "garment_color": "#101820"})
    assert dark["dark_garment"] and dark["areas"][0]["underbase"]["file"] == "dark/sleeve-l-underbase.png"
    with Image.open(workspace / "dark/sleeve-l-underbase.png") as sheet, Image.open(workspace / "dark/sleeve-l.png") as art:
        base = np.asarray(sheet) == 0
        printed = np.asarray(art.convert("RGBA"))[..., 3] >= 128
    assert base.any() and not (base & ~printed).any() and base.sum() < printed.sum()  # a choke: inside the art
    light = dispatch(s, "print-art", {**request, "output": "light"})
    assert not light["dark_garment"] and "underbase" not in light["areas"][0]
    assert not (workspace / "light/sleeve-l-underbase.png").exists()
    assert "light garment" in light["notes"][0]
    red = dispatch(s, "print-art", {**request, "output": "red", "garment_color": "#c1121f"})
    assert red["dark_garment"] and (workspace / "red/sleeve-l-underbase.png").exists()
    poster = dispatch(s, "print-art", {"mockup": "poster-wall", "output": "poster", "dpi": 72, "underbase": True,
                                       "design": "teal.vixl"})
    assert "not a garment" in poster["notes"][0] and not list((workspace / "poster").glob("*underbase*"))
    assert print_art.is_dark("#000000") and print_art.is_dark("#1f4fbf") and not print_art.is_dark("#ffd60a")
    assert not print_art.is_dark("#cfcfcf")


def test_choke_pulls_the_underbase_in(workspace):
    s = session(workspace)
    sizes = []
    for choke in (0, 1):
        result = dispatch(s, "print-art", {"mockup": "tee", "output": f"c{choke}", "dpi": 150, "underbase": True,
                                           "garment_color": "#000000", "choke_mm": choke,
                                           "place": {"sleeve-l": "disc.vixl"}})
        sizes.append(result["areas"][0]["underbase"]["coverage"])
    assert sizes[0] > sizes[1] > 0


def test_print_art_works_for_a_saved_template_and_a_bare_design(workspace):
    s = session(workspace)
    result = dispatch(s, "print-art", {"mockup": "poster-wall", "output": "poster", "dpi": 100, "design": "flat.vixl"})
    assert result["areas"][0]["area"] == "poster" and result["areas"][0]["pixels"] == [1169, 1654]
    assert "garment_color" not in result
