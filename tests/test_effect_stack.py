"""The raster effect stack: effects in the layer's own frame (#203), lookup as an effect (#233),
effect-move (#164), resampling without overshoot (#204) and white balance (#205)."""

import json
import zipfile

import numpy as np
import pytest
from PIL import Image, ImageDraw, ImageFilter

from vixl import Project
from vixl.artistic import emboss_kernel
from vixl.assets import add_image
from vixl.errors import VixlError
from vixl.render import channel_gains, layer_ink, resolve_layout


def noisy(size=96, sigma=12, seed=1):
    rng = np.random.default_rng(seed)
    grey = np.clip(128 + rng.normal(0, sigma, (size, size, 1)), 0, 255).repeat(3, axis=2)
    return Image.fromarray(np.uint8(grey)).convert("RGBA")


def grain(image, box=24):
    """Noise left in the middle of an image: deviation from a local median."""
    a = np.asarray(image.convert("L"), dtype=np.float32)
    smooth = np.asarray(image.convert("L").filter(ImageFilter.MedianFilter(5)), dtype=np.float32)
    h, w = a.shape
    return float((a - smooth)[h // 2 - box : h // 2 + box, w // 2 - box : w // 2 + box].std())


def photo_doc(rotation=0, effects=()):
    p = Project(200, 200, "#000000")
    asset = add_image(p, noisy())
    p.apply([{"type": "add", "asset": asset, "name": "photo", "x": 52, "y": 52}])
    if rotation:
        p.apply({"type": "rotate", "target": "photo", "value": rotation})
    if effects:
        p.apply([{**effect, "target": "photo"} for effect in effects])
    return p


def test_denoise_on_a_rotated_layer_removes_as_much_noise_as_upright():  # #203
    left = {rotation: grain(photo_doc(rotation, [{"type": "denoise", "amount": 90}]).render()) for rotation in (0, -2.22)}
    # Denoising after the turn (which smooths the grain the estimate reads) left about 35 % more.
    assert left[-2.22] <= left[0] * 1.15


def test_effects_turn_with_the_layer():  # #203
    # A blur in the layer's frame, then turned 90°, equals the upright blur turned 90°.
    p = Project(120, 120, "transparent")
    image = Image.new("RGBA", (60, 40), "white")
    ImageDraw.Draw(image).rectangle([0, 0, 29, 39], fill="red")
    asset = add_image(p, image)
    p.apply([{"type": "add", "asset": asset, "name": "a", "x": 30, "y": 40},
             {"type": "effect", "target": "a", "name": "vignette", "strength": 0.8, "radius": 0.2}])
    upright = p.render()
    p.apply({"type": "rotate", "target": "a", "value": 90})
    turned = p.render()
    expected = np.asarray(upright.crop(upright.getbbox()).rotate(-90, expand=True))
    assert np.abs(np.asarray(turned.crop(turned.getbbox()), dtype=int) - expected).max() <= 2


def test_selection_stays_in_canvas_space_on_a_turned_layer():  # #203
    p = Project(100, 100, "transparent")
    p.apply([{"type": "solid", "name": "s", "x": 20, "y": 20, "width": 60, "height": 60, "color": "#204060"},
             {"type": "rotate", "target": "s", "value": 90},
             {"type": "select", "shape": "rect", "x": 0, "y": 0, "width": 50, "height": 100},
             {"type": "effect", "target": "s", "name": "invert"}])
    image = p.render()
    assert image.getpixel((30, 50))[:3] == (255 - 0x20, 255 - 0x40, 255 - 0x60)
    assert image.getpixel((70, 50))[:3] == (0x20, 0x40, 0x60)


def test_emboss_light_stays_put_when_a_layer_turns():  # #203
    size, scale, offset, weights = emboss_kernel((-1, 1)).filterargs
    assert (size, scale, offset, tuple(weights)) == ImageFilter.EMBOSS.filterargs
    p = Project(100, 100, "#808080")
    image = Image.new("RGBA", (60, 60), (0, 0, 0, 0))
    ImageDraw.Draw(image).ellipse([10, 10, 49, 49], fill="white")
    asset = add_image(p, image)
    p.apply([{"type": "add", "asset": asset, "name": "disc", "x": 20, "y": 20},
             {"type": "emboss", "target": "disc"}])
    upright = np.asarray(p.render(), dtype=int)
    p.apply({"type": "rotate", "target": "disc", "value": 90})
    turned = np.asarray(p.render(), dtype=int)
    # A round shape embossed under a fixed light looks the same at any angle.
    assert np.abs(turned - upright).mean() < 1.5


def test_blur_on_a_turned_layer_spreads_past_its_box():
    p = Project(160, 160, "transparent")
    p.apply([{"type": "solid", "name": "s", "x": 40, "y": 40, "width": 80, "height": 80, "color": "#000000"},
             {"type": "rotate", "target": "s", "value": 30},
             {"type": "blur", "target": "s", "amount": 6}])
    layer = p.layer("s")
    ink = layer_ink(p, layer, resolve_layout(p)[layer["id"]])
    b = resolve_layout(p)[layer["id"]]
    # Ink stays within the box widened by the blur's reach, and its edges are soft.
    assert ink.width <= b[2] + 2 * 18 + 2 and ink.height <= b[3] + 2 * 18 + 2
    alpha = np.asarray(p.render().getchannel("A"))
    # The turned square's box starts at x = 40; the blur reaches well past it.
    assert np.nonzero(alpha.max(axis=0))[0].min() < 34


def flat_tile():
    image = Image.new("RGBA", (60, 60), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rectangle([4, 4, 55, 55], fill=(240, 240, 240, 255))
    draw.rectangle([18, 18, 41, 41], fill=(40, 120, 90, 255))
    return image


@pytest.mark.parametrize("ops", [
    [{"type": "rotate", "target": "t", "value": 20}],
    [{"type": "resize", "target": "t", "width": 101, "height": 101}],
    [{"type": "resize", "target": "t", "width": 23, "height": 23}, {"type": "rotate", "target": "t", "value": 33}],
    [{"type": "move", "target": "t", "x": 10.4, "y": 20.7}],
])
def test_resampled_flat_shapes_keep_their_palette(ops):  # #204
    p = Project(200, 200, "transparent")
    asset = add_image(p, flat_tile())
    p.apply([{"type": "add", "asset": asset, "name": "t", "x": 30, "y": 30}, *ops])
    layer = p.layer("t")
    ink = np.asarray(layer_ink(p, layer, resolve_layout(p)[layer["id"]]), dtype=int)
    visible = ink[..., 3] > 0
    rgb = ink[..., :3][visible]
    palette = np.array([(240, 240, 240), (40, 120, 90)])
    assert (rgb >= palette.min(0)).all() and (rgb <= palette.max(0)).all()
    # No bright rim: colours lie between the two fills (green channel tracks red).
    t = (rgb[:, 0] - 40) / 200
    assert np.abs(rgb[:, 1] - (120 + 120 * t)).max() <= 3


def test_temperature_and_tint_are_matched_multiplicative_shifts():  # #205
    grey = np.full(3, 128.0)
    warm = grey * channel_gains({"name": "temperature", "amount": 100})
    magenta = grey * channel_gains({"name": "tint", "amount": 100})
    assert warm[0] - warm[2] > 30 and magenta[0] - magenta[1] > 15
    # Similar strength: OKLab chroma of grey within 15 % of each other.
    from vixl.colors import srgb_to_oklab

    def chroma(rgb):
        _, a, b = srgb_to_oklab(tuple(rgb / 255))
        return np.hypot(a, b)

    assert chroma(warm) == pytest.approx(chroma(magenta), rel=0.15)
    p = Project(20, 10, "#000000")
    p.apply([{"type": "solid", "name": "s", "x": 0, "y": 0, "width": 20, "height": 10, "color": "#000000"},
             {"type": "temperature", "target": "s", "amount": 100}, {"type": "tint", "target": "s", "amount": -100}])
    assert p.render().getpixel((5, 5))[:3] == (0, 0, 0)
    with pytest.raises(VixlError):
        p.apply({"type": "temperature", "target": "s", "amount": 300})


def test_white_balance_from_a_neutral_and_from_gains():  # #205
    p = Project(30, 10, "#000000")
    p.apply([{"type": "solid", "name": "cast", "x": 0, "y": 0, "width": 10, "height": 10, "color": "#a08070"},
             {"type": "solid", "name": "black", "x": 10, "y": 0, "width": 10, "height": 10, "color": "#000000"},
             {"type": "white-balance", "target": "cast", "neutral": "#a08070"},
             {"type": "white-balance", "target": "black", "neutral": "#a08070"}])
    r, g, b, _ = p.render().getpixel((5, 5))
    assert max(r, g, b) - min(r, g, b) <= 1
    assert p.render().getpixel((15, 5))[:3] == (0, 0, 0)
    p.apply({"type": "solid", "name": "g", "x": 20, "y": 0, "width": 10, "height": 10, "color": "#808080"})
    p.apply({"type": "white-balance", "target": "g", "gains": [1.0, 0.5, 2.0]})
    assert p.render().getpixel((25, 5))[:3] == (128, 64, 255)
    p.apply({"type": "effect-set", "target": "g", "effect": 1, "amount": 50})
    assert p.render().getpixel((25, 5))[:3] == (128, 90, 181)
    with pytest.raises(VixlError):
        p.apply({"type": "white-balance", "target": "g", "gains": [1, 2]})


def lut_doc():
    p = Project(20, 10, "#000000")
    values = [[1 - r, 1 - g, 1 - b] for b in (0, 1) for g in (0, 1) for r in (0, 1)]
    p.apply([{"type": "solid", "name": "s", "x": 0, "y": 0, "width": 20, "height": 10, "color": "#ff0000"},
             {"type": "lut", "name": "invert", "size": 2, "values": values}])
    return p


def test_lookup_is_an_effect_in_the_stack():  # #233
    p = lut_doc()
    p.apply({"type": "lookup", "target": "s", "name": "invert"})
    effect = p.layer("s")["effects"][-1]
    assert effect["name"] == "lookup" and effect["lut"] == "invert" and effect["amount"] == 1
    assert p.render().getpixel((5, 5))[:3] == (0, 255, 255)
    p.apply({"type": "effect-disable", "target": "s", "effect": "lookup"})
    assert p.render().getpixel((5, 5))[:3] == (255, 0, 0)
    p.apply([{"type": "effect-enable", "target": "s", "effect": "lookup"},
             {"type": "effect", "target": "s", "name": "lookup", "lut": "invert", "amount": 0.5}])
    assert p.render().getpixel((5, 5))[:3] == (128, 128, 128)
    with pytest.raises(VixlError):
        p.apply({"type": "effect", "target": "s", "name": "lookup", "lut": "missing"})


def test_lookup_orders_with_other_effects():  # #233 / #164
    p = lut_doc()
    p.apply([{"type": "lookup", "target": "s", "name": "invert"}, {"type": "brightness", "target": "s", "amount": -50}])
    assert p.render().getpixel((5, 5))[:3] == (0, 127, 127)  # invert, then darken
    p.apply({"type": "effect-move", "target": "s", "effect": "brightness", "to": "top"})
    assert p.render().getpixel((5, 5))[:3] == (128, 255, 255)  # darken, then invert


def test_lookup_saved_as_a_layer_field_loads_as_an_effect(tmp_path):  # #233
    p = lut_doc()
    p.apply({"type": "lookup", "target": "s", "name": "invert", "amount": 0.75})
    expected = p.render()
    path = tmp_path / "old.vixl"
    p.save(path)
    # Rewrite the archive the way 0.20 stored a LUT: a layer field, not an effect.
    with zipfile.ZipFile(path) as archive:
        members = {name: archive.read(name) for name in archive.namelist()}
    metadata = json.loads(members["project.json"])

    def downgrade(state):
        for layer in state["layers"]:
            for effect in [e for e in layer.get("effects", []) if e["name"] == "lookup"]:
                layer["effects"].remove(effect)
                layer["lookup"] = {"name": effect["lut"], "amount": effect["amount"]}
        return state

    downgrade(metadata["state"])
    for ident, node in metadata["nodes"].items():
        node.pop("delta", None)
        node["state"] = downgrade(p._state_at(ident))
    members["project.json"] = json.dumps(metadata).encode()
    with zipfile.ZipFile(path, "w") as archive:
        for name, data in members.items():
            archive.writestr(name, data)
    loaded = Project.load(path)
    layer = loaded.layer("s")
    assert "lookup" not in layer and layer["effects"][-1]["name"] == "lookup"
    assert loaded.render().tobytes() == expected.tobytes()
    loaded.apply({"type": "effect-disable", "target": "s", "effect": "lookup"})
    loaded.undo()
    assert loaded.render().tobytes() == expected.tobytes()


def stacked():
    p = Project(10, 10, "#000000")
    p.apply([{"type": "solid", "name": "s", "x": 0, "y": 0, "width": 10, "height": 10, "color": "#336699"},
             {"type": "blur", "target": "s", "amount": 1}, {"type": "brightness", "target": "s", "amount": 10},
             {"type": "grain", "target": "s", "amount": 0.1}])
    return p


def names(p):
    return [effect["name"] for effect in p.layer("s")["effects"]]


@pytest.mark.parametrize("op, expected", [
    ({"effect": 3, "to": 1}, ["grain", "blur", "brightness"]),
    ({"effect": "blur", "to": "bottom"}, ["brightness", "grain", "blur"]),
    ({"effect": "grain", "to": "top"}, ["grain", "blur", "brightness"]),
    ({"effect": 1, "to": 2}, ["brightness", "blur", "grain"]),
    ({"effect": "blur", "after": "grain"}, ["brightness", "grain", "blur"]),
    ({"effect": "grain", "before": 2}, ["blur", "grain", "brightness"]),
])
def test_effect_move(op, expected):  # #164
    p = stacked()
    p.apply({"type": "effect-move", "target": "s", **op})
    assert names(p) == expected


def test_effect_move_by_id_renders_like_readding_and_undoes():  # #164
    p = stacked()
    ident = p.layer("s")["effects"][2]["id"]
    original = p.render().tobytes()
    p.apply({"type": "effect-move", "target": "s", "effect": ident, "to": "top"})
    assert len(p.nodes) and names(p) == ["grain", "blur", "brightness"]
    moved = p.render().tobytes()
    q = Project(10, 10, "#000000")
    q.apply([{"type": "solid", "name": "s", "x": 0, "y": 0, "width": 10, "height": 10, "color": "#336699"},
             {"type": "grain", "target": "s", "amount": 0.1}, {"type": "blur", "target": "s", "amount": 1},
             {"type": "brightness", "target": "s", "amount": 10}])
    assert q.render().tobytes() == moved
    p.undo()
    assert names(p) == ["blur", "brightness", "grain"] and p.render().tobytes() == original


@pytest.mark.parametrize("op, field", [
    ({"effect": "sepia", "to": 1}, "effect"),
    ({"effect": 9, "to": 1}, "effect"),
    ({"effect": 1, "to": 7}, "to"),
    ({"effect": 1, "before": "nope"}, "before"),
    ({"effect": 1}, "to"),
])
def test_effect_move_errors_name_the_field(op, field):  # #164
    p = stacked()
    with pytest.raises(VixlError) as error:
        p.apply({"type": "effect-move", "target": "s", **op})
    assert error.value.details.get("field") == field


def test_white_balance_exports_as_a_native_svg_filter():  # #205
    p = Project(40, 40, "#ffffff")
    p.apply([{"type": "shape", "shape": "rectangle", "name": "r", "x": 0, "y": 0, "width": 40, "height": 40,
              "fill": "#808080"},
             {"type": "white-balance", "target": "r", "gains": [1, 0.5, 2]},
             {"type": "temperature", "target": "r", "amount": 50}])
    svg = p.export(format="SVG")
    svg = svg.decode() if isinstance(svg, bytes) else svg
    assert "feFuncR" in svg and "<image" not in svg


def test_paper_look_warms_visibly():  # #205: the look relied on the old, near-invisible scale
    p = Project(40, 40, "#808080")
    p.apply([{"type": "solid", "name": "bg", "x": 0, "y": 0, "width": 40, "height": 40, "color": "#808080"},
             {"type": "look", "target": "bg", "look": "paper"}])
    temperature = next(e for e in p.layer("bg")["effects"] if e["name"] == "temperature")
    gains = channel_gains(temperature)
    assert 128 * (gains[0] - gains[2]) >= 6
