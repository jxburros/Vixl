"""Pixel sprites get a shading ramp and an outline by default in new documents (craft plan 7e, T13 flat silhouette)."""

import numpy as np
import pytest

from vixl import Project
from vixl.commands import compile_command
from vixl.errors import VixlError

ROWS = [
    "................",
    ".....yyyyy......",
    "....yyyyyyy.....",
    "....yyssssy.....",
    "....yysesss.....",
    "....yyssssy.....",
    "...yyyyyyyyy....",
    "...yyyyyyyyy....",
    "...yyyyyyyyys...",
    "...yyyyyyyyys...",
    "...yyyyyyyyy....",
    "....nnn.nnn.....",
    "....nnn.nnn.....",
    "....nnn.nnn.....",
    "....bbb.bbbb....",
    "................",
]
PALETTE = {".": "transparent", "y": "#f4c430", "s": "#f2c79b", "e": "#1e1a2a", "n": "#2b3a67", "b": "#5a3a22"}


def sprite(version=4, **extra):
    p = Project(16, 16)
    p.state["design_defaults"] = {"house_style_version": version}
    p.apply({"type": "pixel-art", "name": "keeper", "rows": ROWS, "palette": PALETTE, **extra})
    return p


def colours(image):
    a = np.asarray(image.convert("RGBA"))
    return {tuple(int(v) for v in px[:3]) for px in a.reshape(-1, 4) if px[3] == 255}


def flat(p):
    """The sprite exactly as its stored rows and palette draw it."""
    from vixl.render import color

    keys = {k: color(v) for k, v in PALETTE.items()}
    return np.array([[keys[ch] for ch in row] for row in ROWS], dtype=np.uint8)


def test_new_sprites_get_a_shading_ramp_and_an_outline():
    p = sprite()
    layer = p.layer("keeper")
    assert layer["shading"] is True and layer["outline"] is True
    assert layer["pixels"] == ROWS, "the stored rows stay as drawn"
    image = p.render()
    a = np.asarray(image)
    assert set(np.unique(a[..., 3])) == {0, 255}, "alpha stays binary"
    assert 5 < len(colours(image)) <= 16
    # A 1 px outline in the darkest palette colour rings the silhouette.
    assert tuple(a[0, 5, :3]) == (0x1e, 0x1a, 0x2a) and tuple(a[6, 2, :3]) == (0x1e, 0x1a, 0x2a)
    # The coat is no longer one flat colour: it has a darker band and a lighter one.
    coat = a[6:11, 3:12, :3].reshape(-1, 3)
    tones = {tuple(px) for px in coat} - {(0xf2, 0xc7, 0x9b)}
    assert len(tones) >= 3
    drawn = p.inspect_pixels("keeper")["drawn"]
    assert len(drawn["rows"]) == 16 and set("".join(drawn["rows"])) <= set(drawn["palette"])


def test_older_documents_and_explicit_overrides_keep_the_flat_sprite():
    for p in (sprite(version=3), sprite(shading=False, outline=False)):
        assert "shading" not in p.layer("keeper") and "outline" not in p.layer("keeper")
        assert np.array_equal(np.asarray(p.render()), flat(p))
    only_outline = sprite(shading=False)
    assert len(colours(only_outline.render())) == 5
    p = sprite()
    p.apply({"type": "pixel-palette", "target": "keeper", "shading": False, "outline": False})
    assert np.array_equal(np.asarray(p.render()), flat(p))
    old = sprite(version=3)
    old.apply({"type": "pixel-palette", "target": "keeper", "shading": {"light": "top-right", "colors": 8}, "outline": "#000000"})
    image = old.render()
    assert len(colours(image)) <= 8 and (0, 0, 0) in colours(image)


def test_a_palette_swap_carries_into_the_ramp():
    p = sprite()
    before = colours(p.render())
    p.apply({"type": "pixel-palette", "target": "keeper", "colors": {"y": "#d63a2f"}})
    after = colours(p.render())
    yellows = {c for c in after if c[0] > 200 and c[1] > 150 and c[2] < 120}
    assert not yellows, "no yellow shadow or highlight is left behind"
    assert after != before


def test_hand_drawn_outlines_and_ramps_are_respected_and_the_colour_cap_holds():
    rows = ["........", ".oooooo.", ".oaaaao.", ".oaddao.", ".oaaaao.", ".oooooo.", "........", "........"]
    p = Project(8, 8)
    p.state["design_defaults"] = {"house_style_version": 4}
    p.apply({"type": "pixel-art", "name": "box", "rows": rows, "palette": {".": "transparent", "o": "#111111",
                                                                          "a": "#3a7bd5", "d": "#1f4f99"}})
    a = np.asarray(p.render())
    assert a[0].max() == 0 and a[:, 0].max() == 0, "an outlined sprite gets no second outline"
    many = {chr(65 + i): f"#{(i * 15) % 256:02x}{(80 + i * 9) % 256:02x}{(200 - i * 11) % 256:02x}" for i in range(16)}
    big = [".........."] + ["." + "".join(chr(65 + (x + y) % 16) * 1 for x in range(8)) + "." for y in range(8)] + [".........."]
    q = Project(10, 10)
    q.state["design_defaults"] = {"house_style_version": 4}
    q.apply({"type": "pixel-art", "name": "busy", "rows": big, "palette": {".": "transparent", **many}})
    assert len(colours(q.render())) <= 16


def test_svg_and_schema_follow_the_finish():
    p = sprite()
    svg = p.export(format="SVG").decode()
    ramp = colours(p.render()) - colours(sprite(version=3).render())
    assert ramp and all(("#%02x%02x%02x" % c) in svg or ("rgb(%d,%d,%d)" % c) in svg for c in ramp)
    with pytest.raises(VixlError, match="shading"):
        sprite(shading={"light": "left"})
    op = compile_command(["pixel-palette", "keeper", "--shading", "false", "--outline", "#000000"])
    assert op == {"type": "pixel-palette", "target": "keeper", "shading": False, "outline": "#000000"}
