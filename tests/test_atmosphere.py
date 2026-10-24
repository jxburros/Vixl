"""Scene atmosphere operations: reflection, haze, star-field, string-lights and bokeh."""

import numpy as np
import pytest

from vixl import Project, VixlError
from vixl.plugins.atmosphere.atmosphere import _boxes
from vixl.geometry import bezier_points
from vixl.targets import mode


def children(project, name):
    group = project.layer(name)
    return [layer for layer in project.state["layers"] if layer.get("parent") == group["id"]]


def geometry(project, name):
    return [(layer["name"], layer["type"], round(layer["x"], 3), round(layer["y"], 3), round(layer["width"], 3),
             layer.get("opacity")) for layer in children(project, name)]


def night(width=800, height=600):
    p = Project(width, height, "#0b1730")
    p.apply([
        {"type": "gradient", "name": "sky", "width": width, "height": height, "direction": "vertical",
         "stops": [{"offset": 0, "color": "#060e1c"}, {"offset": 1, "color": "#1d3157"}]},
        {"type": "text", "name": "title", "text": "Harbor Lights", "size": 72, "color": "#fbf1dc", "x": 150,
         "y": 180},
        {"type": "text", "name": "date", "text": "Saturday", "size": 32, "color": "#f4c56a", "x": 320, "y": 300},
    ])
    return p


def test_new_operations_are_classified():
    assert mode("reflection") == "joint"
    for kind in ("haze", "star-field", "string-lights", "bokeh"):
        assert mode(kind) == "one"
    p = Project(300, 200, "#000000")
    result = p.apply([{"type": "starfield", "count": 5}, {"type": "fairy_lights", "from": [0, 20], "to": [300, 20]}])
    assert p.layer("stars") and p.layer("string-lights")
    assert any("'starfield' → 'star-field'" in text for text in result["normalized"])


def test_star_field_keeps_clear_of_every_text_box_and_is_seeded():
    p = night()
    result = p.apply({"type": "star-field", "count": 160, "seed": 7, "clearance": 12})
    assert any("star-field" in text for text in result["normalized"])
    stars = children(p, "stars")
    assert len(stars) >= 100
    texts = _boxes(p, [p.layer("title"), p.layer("date")])
    for box in _boxes(p, stars):
        for t in texts:
            apart = box[2] + 12 <= t[0] + 1e-6 or box[0] - 12 >= t[2] - 1e-6 or \
                box[3] + 12 <= t[1] + 1e-6 or box[1] - 12 >= t[3] - 1e-6
            assert apart, (box, t)
    again = night()
    again.apply({"type": "star-field", "count": 160, "seed": 7, "clearance": 12})
    assert geometry(again, "stars") == geometry(p, "stars")
    other = night()
    other.apply({"type": "star-field", "count": 160, "seed": 8, "clearance": 12})
    assert geometry(other, "stars") != geometry(p, "stars")


def test_star_field_sits_on_the_backdrop_under_the_copy():
    p = night()
    p.apply({"type": "star-field", "count": 40, "seed": 1})
    order = [layer["name"] for layer in p.state["layers"] if not layer.get("parent")]
    assert order == ["sky", "stars", "title", "date"]
    stars = children(p, "stars")
    assert len(stars) == 40
    assert {layer["type"] for layer in stars} == {"shape"}


def test_star_field_and_bokeh_take_a_layer_as_their_region():
    p = Project(600, 600, "#000000")
    p.apply([{"type": "solid", "name": "sky", "x": 0, "y": 0, "width": 600, "height": 200, "color": "#0b1730"},
             {"type": "star-field", "target": "sky", "count": 50, "seed": 3},
             {"type": "bokeh", "target": "sky", "count": 5, "seed": 3}])
    for name in ("stars", "bokeh"):
        for box in _boxes(p, children(p, name)):
            centre = (box[1] + box[3]) / 2
            assert 0 <= centre <= 200, (name, box)


def test_star_field_thins_toward_the_bottom_of_the_region():
    p = Project(600, 600, "#000000")
    p.apply({"type": "star-field", "count": 300, "fade": 1, "seed": 2})
    ys = [box[1] for box in _boxes(p, children(p, "stars"))]
    top = sum(1 for y in ys if y < 300)
    assert top > 1.8 * (len(ys) - top)


def test_string_lights_hang_bulbs_along_a_sagging_wire():
    p = Project(800, 400, "#101820")
    result = p.apply({"type": "string-lights", "from": [0, 50], "to": [800, 50], "sag": 80, "count": 8, "hang": 0,
                      "jitter": 0, "glow": 0.5, "seed": 1})
    assert any("8 bulbs" in text for text in result["normalized"])
    parts = children(p, "string-lights")
    wire = [layer for layer in parts if layer["name"].endswith("/wire")]
    assert len(wire) == 1
    curve = bezier_points([(0, 50), (800 / 3, 50 + 160 * 2 / 3), (1600 / 3, 50 + 160 * 2 / 3), (800, 50)],
                          np.linspace(0, 1, 2001))
    # The lowest point of the wire is the sag below the chord.
    assert abs(curve[:, 1].max() - 130) < 0.5
    groups = [layer for layer in project_layers(p) if layer["type"] == "group" and "/bulb-" in layer["name"]]
    assert groups == []  # bulbs are flat parts of one group, not nested groups
    caps = [layer for layer in parts if layer["name"].endswith("/cap")]
    assert len(caps) == 8
    for box in _boxes(p, caps):
        top_centre = np.array([(box[0] + box[2]) / 2, box[1]])
        assert np.min(np.hypot(*(curve - top_centre).T)) < 1.5
    xs = sorted((box[0] + box[2]) / 2 for box in _boxes(p, caps))
    gaps = np.diff(xs)
    assert gaps.max() - gaps.min() < 0.25 * gaps.mean()  # evenly spaced along the arc


def project_layers(p):
    return p.state["layers"]


def test_string_lights_follow_an_existing_path_and_keep_it_as_the_wire():
    p = Project(600, 400, "#101820")
    p.apply({"type": "pen", "name": "line", "nodes": [{"point": [40, 300], "out": [200, 60]},
                                                      {"point": [560, 280], "in": [400, 60]}],
             "fill": "transparent", "stroke": "#333333", "stroke_width": 3})
    p.apply({"type": "string-lights", "target": "line", "count": 6, "hang": 20, "jitter": 0, "bulb": "lantern",
             "colors": ["#f4b942", "#d9534f"]})
    parts = children(p, "string-lights")
    assert not any(layer["name"].endswith("/wire") for layer in parts)
    curve = bezier_points([(40, 300), (200, 60), (400, 60), (560, 280)], np.linspace(0, 1, 4001))
    hangers = [layer for layer in parts if layer["name"].endswith("/hanger")]
    assert len(hangers) == 6
    for box in _boxes(p, hangers):
        top = np.array([(box[0] + box[2]) / 2, box[1]])
        assert np.min(np.hypot(*(curve - top).T)) < 2
    bodies = [layer for layer in parts if layer["name"].endswith("/body")]
    assert [layer["fill"] for layer in bodies] == ["#f4b942", "#d9534f"] * 3
    order = [layer["name"] for layer in p.state["layers"] if not layer.get("parent")]
    assert order.index("string-lights") == order.index("line") + 1


def test_string_lights_are_seeded():
    def build(seed):
        p = Project(500, 300, "#000000")
        p.apply({"type": "string-lights", "from": [0, 40], "to": [500, 60], "count": 5, "seed": seed})
        return geometry(p, "string-lights")

    assert build(3) == build(3)
    assert build(3) != build(4)


def test_haze_sits_behind_its_light_and_is_centred_on_it():
    p = Project(600, 400, "#0b1730")
    p.apply({"type": "shape", "shape": "ellipse", "name": "lamp", "x": 280, "y": 180, "width": 40, "height": 40,
             "fill": "#ffcf6e"})
    p.apply({"type": "haze", "target": "lamp", "strength": 0.5})
    order = [layer["name"] for layer in p.state["layers"] if not layer.get("parent")]
    assert order.index("haze") == order.index("lamp") - 1
    band = p.layer("haze/band")
    x0, y0, x1, y1 = _boxes(p, [band])[0]
    assert abs((x0 + x1) / 2 - 300) < 1 and abs((y0 + y1) / 2 - 200) < 1
    assert x1 - x0 > 2 * (y1 - y0)  # a band, wider than tall
    assert band["direction"] == "radial" and band["falloff"] == "gaussian"
    assert band["stops"][0]["color"].lower().startswith("#ffcf6e")
    image = np.asarray(p.render().convert("RGB")).astype(int)
    assert image[200, 200].sum() > image[20, 20].sum()  # glow reaches beyond the lamp


def test_bokeh_discs_are_soft_gradients_with_screen_blend():
    p = Project(600, 400, "#101010")
    p.apply({"type": "bokeh", "count": 9, "seed": 5})
    discs = children(p, "bokeh")
    assert len(discs) == 9
    assert {layer["type"] for layer in discs} == {"gradient"}
    assert {layer["blend"] for layer in discs} == {"screen"}
    assert all(layer["stops"][-1]["color"].endswith("00") for layer in discs)
    again = Project(600, 400, "#101010")
    again.apply({"type": "bokeh", "count": 9, "seed": 5})
    assert geometry(again, "bokeh") == geometry(p, "bokeh")


def scene():
    p = Project(400, 400, "#000000")
    p.apply([
        {"type": "solid", "name": "water", "x": 0, "y": 200, "width": 400, "height": 200, "color": "#0a1830"},
        {"type": "shape", "shape": "rectangle", "name": "tower", "x": 100, "y": 120, "width": 40, "height": 80,
         "fill": "#ff0000"},
        {"type": "text", "name": "caption", "text": "Quay", "size": 40, "color": "#ffffff", "x": 250, "y": 120},
    ])
    return p


def test_reflection_mirrors_what_stands_above_the_horizon_into_the_water():
    p = scene()
    result = p.apply({"type": "reflection", "horizon": 200, "squash": 1, "ripple": 0, "breakup": 0, "fade": 0,
                      "blur": 0, "opacity": 1})
    assert any("'tower'" in text and "caption" not in text for text in result["normalized"])
    layer = p.layer("reflection")
    assert layer["type"] == "raster" and layer["reflection"]["horizon"] == 200
    image = np.asarray(p.render().convert("RGB")).astype(int)
    # The tower spans y 120-200 above the waterline, so its mirror spans 200-280 below it.
    assert image[220, 120][0] > 150 and image[220, 120][2] < 120
    assert image[270, 120][0] > 120
    assert image[300, 120][0] < 40  # nothing beyond the tower's height
    assert all(image[y, x].tolist() == [10, 24, 48] for y in (235, 250, 265) for x in (265, 290, 310))  # no caption
    order = [item["name"] for item in p.state["layers"]]
    assert order.index("reflection") > order.index("water") and order.index("reflection") < order.index("caption")


def test_reflection_fades_and_ripples_with_depth():
    p = scene()
    p.apply({"type": "shape", "shape": "rectangle", "name": "tall", "x": 200, "y": 10, "width": 30, "height": 190,
             "fill": "#ffffff"})
    p.apply({"type": "reflection", "horizon": 200, "targets": ["tall"], "squash": 1, "fade": 1, "breakup": 0,
             "ripple": 0.6, "seed": 2})
    alpha = np.asarray(p.image(p.layer("reflection")["asset"]))[:, :, 3].astype(int)
    rows = alpha.max(axis=1)
    assert rows[2] > rows[len(rows) // 2] > rows[-3]
    columns = [np.nonzero(alpha[i] > 20)[0] for i in range(0, len(alpha) * 2 // 3, 5)]
    starts = [c[0] for c in columns if len(c)]
    assert max(starts) - min(starts) >= 4  # rows are displaced sideways


def test_reflection_is_seeded_and_re_renders_after_the_scene_changes():
    first, second = scene(), scene()
    for p in (first, second):
        p.apply({"type": "reflection", "horizon": 200, "seed": 4})
    a, b = (np.asarray(p.image(p.layer("reflection")["asset"])) for p in (first, second))
    assert a.shape == b.shape and np.array_equal(a, b)
    before = first.layer("reflection")["x"]
    first.apply({"type": "move", "target": "tower", "x": 220, "y": 120})
    first.apply({"type": "reflection", "target": "reflection"})
    assert first.layer("reflection")["x"] > before + 50
    assert first.layer("reflection")["reflection"]["seed"] == 4


def test_reflection_needs_a_horizon_and_something_above_it():
    p = scene()
    with pytest.raises(VixlError, match="horizon"):
        p.apply({"type": "reflection"})
    empty = Project(200, 200, "#000000")
    with pytest.raises(VixlError, match="Nothing lies above"):
        empty.apply({"type": "reflection", "horizon": 100})
    with pytest.raises(VixlError, match="not made by reflection"):
        p.apply({"type": "reflection", "target": "tower", "horizon": 200})


def test_capabilities_topic_lists_the_atmosphere_operations():
    from vixl.capabilities import lookup

    found = lookup("atmosphere")
    assert set(found["operations"]) >= {"reflection", "haze", "star-field", "string-lights", "bokeh"}
    assert "motifs" in found["guidance"]


def test_atmosphere_exports_stay_vector_except_the_reflection():
    p = night()
    p.apply([
        {"type": "star-field", "count": 30, "seed": 1},
        {"type": "string-lights", "from": [0, 40], "to": [800, 40], "count": 6},
        {"type": "bokeh", "count": 4},
        {"type": "haze", "x": 400, "y": 500},
    ])
    svg = p.export(format="SVG")
    assert b"<image" not in svg and b"radialGradient" in svg
    p.apply({"type": "shape", "shape": "rectangle", "name": "pier", "x": 0, "y": 520, "width": 300, "height": 30,
             "fill": "#123456"})
    p.apply({"type": "reflection", "horizon": 550, "targets": ["pier"]})
    assert p.export(format="SVG").count(b"<image") == 1
    assert p.export(format="PDF").startswith(b"%PDF")
    assert p.export(format="PPTX")[:2] == b"PK"


def fog_scene():
    p = Project(480, 320, "#9fbfd8")
    p.apply([
        {"type": "gradient", "name": "sky", "width": 480, "height": 320, "direction": "vertical",
         "stops": [{"offset": 0, "color": "#9fbfd8"}, {"offset": 1, "color": "#e9eef2"}]},
        {"type": "shape", "shape": "triangle", "name": "far-hill", "x": 40, "y": 120, "width": 420, "height": 200,
         "fill": "#7d97ad"},
        {"type": "shape", "shape": "triangle", "name": "near-hill", "x": 160, "y": 200, "width": 380, "height": 140,
         "fill": "#2c4452"},
        {"type": "text", "name": "title", "text": "Misty Morning", "size": 34, "color": "#14263b", "x": 24, "y": 20},
    ])
    return p


def fog_bands(p, name="fog"):
    """Per band (farthest first): canvas centre y, the tone and opacity of its puffs, and their height."""
    from vixl.colors import parse, srgb_to_hsl

    bands = {}
    for layer in children(p, name):
        band = int(layer["name"].split("/")[1].split("-")[1])
        bands.setdefault(band, []).append(layer)
    result = []
    for band in sorted(bands):
        puffs = bands[band]
        boxes = _boxes(p, puffs)
        r, g, b, a = parse(puffs[0]["stops"][0]["color"])
        hue, saturation, light = srgb_to_hsl((r, g, b))
        result.append({"y": float(np.mean([(box[1] + box[3]) / 2 for box in boxes])), "saturation": saturation,
                       "light": light, "alpha": float(np.mean([parse(item["stops"][0]["color"])[3] for item in puffs])),
                       "height": float(np.mean([box[3] - box[1] for box in boxes])), "puffs": len(puffs)})
    return result


def test_fog_stacks_soft_bands_that_wash_out_toward_the_horizon():
    p = fog_scene()
    result = p.apply({"type": "haze", "form": "fog", "layers": 4, "y": 240, "height": 160, "seed": 3})
    assert any("4 bands" in text for text in result["normalized"])
    bands = fog_bands(p)
    assert len(bands) == 4
    ys = [band["y"] for band in bands]
    assert ys == sorted(ys) and ys[0] < 200 < ys[-1] and abs(np.mean(ys) - 240) < 12  # the zone is centred on y
    assert all(a["light"] > b["light"] for a, b in zip(bands, bands[1:]))  # lighter toward the horizon
    assert all(a["saturation"] < b["saturation"] for a, b in zip(bands, bands[1:]))  # and less saturated
    assert all(a["alpha"] > b["alpha"] for a, b in zip(bands, bands[1:]))  # the farthest band is the densest
    assert all(a["height"] < b["height"] for a, b in zip(bands, bands[1:]))  # near bands are taller
    for layer in children(p, "fog"):
        assert layer["type"] == "gradient" and layer["falloff"] == "gaussian" and layer["stops"][-1]["color"].endswith("00")
    assert p.layer("fog")["allow_crop"] is True


@pytest.mark.parametrize("count", [2, 3, 5])
def test_fog_layers_sets_the_number_of_bands_and_density_its_strength(count):
    thin, thick = fog_scene(), fog_scene()
    thin.apply({"type": "haze", "form": "fog", "layers": count, "density": 0.2})
    thick.apply({"type": "haze", "form": "fog", "layers": count, "density": 0.8})
    a, b = fog_bands(thin), fog_bands(thick)
    assert len(a) == len(b) == count
    assert all(y["alpha"] > 2.5 * x["alpha"] for x, y in zip(a, b))
    assert max(band["alpha"] for band in b) <= 0.9  # heavy fog still lets the scene show through


def test_fog_rejects_layer_counts_outside_two_to_five_and_options_of_the_other_forms():
    p = fog_scene()
    for bad in (1, 6):
        with pytest.raises(VixlError, match="layers"):
            p.apply({"type": "haze", "form": "fog", "layers": bad})
    for key, value in (("layers", 3), ("density", 0.5), ("behind", ["near-hill"])):
        with pytest.raises(VixlError, match="only apply to form fog"):
            p.apply({"type": "haze", "x": 200, "y": 200, key: value})
    with pytest.raises(VixlError, match="behind or below"):
        p.apply({"type": "haze", "form": "fog", "behind": ["near-hill"], "below": "far-hill"})
    with pytest.raises(VixlError, match="form"):
        p.apply({"type": "haze", "x": 10, "y": 10, "form": "smoke"})


def test_fog_is_seeded():
    def build(seed):
        p = fog_scene()
        p.apply({"type": "haze", "form": "fog", "seed": seed})
        return geometry(p, "fog")

    assert build(5) == build(5)
    assert build(5) != build(6)


def test_fog_sits_directly_below_the_lowest_named_foreground_layer():
    p = fog_scene()
    p.apply({"type": "haze", "form": "fog", "behind": ["near-hill", "far-hill"]})
    order = [layer["name"] for layer in p.state["layers"] if not layer.get("parent")]
    assert order == ["sky", "fog", "far-hill", "near-hill", "title"]
    # Without behind the fog veils the scene and leaves the copy on top.
    q = fog_scene()
    q.apply({"type": "haze", "form": "fog"})
    assert [layer["name"] for layer in q.state["layers"] if not layer.get("parent")] == \
        ["sky", "far-hill", "near-hill", "fog", "title"]
    # A layer inside a group counts as its group.
    g = fog_scene()
    g.apply({"type": "group", "name": "hills", "targets": ["far-hill", "near-hill"]})
    g.apply({"type": "haze", "form": "fog", "behind": ["near-hill"]})
    assert [layer["name"] for layer in g.state["layers"] if not layer.get("parent")] == ["sky", "fog", "hills", "title"]


def test_fog_veils_what_is_behind_it_and_leaves_the_named_foreground_crisp():
    plain, misty = fog_scene(), fog_scene()
    misty.apply({"type": "haze", "form": "fog", "layers": 3, "density": 0.9, "y": 250, "height": 120,
                 "behind": ["near-hill"], "color": "#ffffff"})
    a, b = (np.asarray(p.render().convert("RGB")).astype(int) for p in (plain, misty))
    assert np.array_equal(a[290:300, 300:320], b[290:300, 300:320])  # the near hill is in front of the fog
    assert b[240:260, 140:240].mean() > a[240:260, 140:240].mean() + 25  # the far hill is veiled
    assert np.array_equal(a[:100], b[:100])  # the fog stays in its zone


def test_fog_takes_its_zone_from_a_target_layer_and_overrides():
    p = fog_scene()
    p.apply({"type": "solid", "name": "valley", "x": 0, "y": 200, "width": 480, "height": 120, "color": "#4f6f80"})
    p.apply({"type": "haze", "form": "fog", "target": "valley", "layers": 3})
    ys = [band["y"] for band in fog_bands(p)]
    assert 200 <= ys[0] < ys[-1] <= 320
    q = fog_scene()
    q.apply({"type": "solid", "name": "valley", "x": 0, "y": 200, "width": 480, "height": 120, "color": "#4f6f80"})
    q.apply({"type": "haze", "form": "fog", "target": "valley", "layers": 3, "height": 60, "y": 150})
    ys = [band["y"] for band in fog_bands(q)]
    assert ys[0] >= 120 and ys[-1] <= 180


def test_fog_exports_stay_vector_and_the_band_form_is_unchanged():
    p = fog_scene()
    p.apply({"type": "haze", "form": "fog", "layers": 5, "behind": ["near-hill"], "seed": 1})
    svg = p.export(format="SVG")
    assert b"<image" not in svg and b"radialGradient" in svg
    assert p.export(format="PDF").startswith(b"%PDF") and p.export(format="PPTX")[:2] == b"PK"
    q = Project(600, 400, "#0b1730")
    q.apply({"type": "shape", "shape": "ellipse", "name": "lamp", "x": 280, "y": 180, "width": 40, "height": 40,
             "fill": "#ffcf6e"})
    q.apply({"type": "haze", "target": "lamp", "form": "band", "strength": 0.5})
    assert [layer["name"] for layer in children(q, "haze")] == ["haze/band", "haze/core"]
