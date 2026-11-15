"""The glyph cache (#584) reuses rasterised glyphs between labels and must give exactly the whole-layer pixels."""

import random
import threading

import pytest
import resvg_py

from vixl import Project, glyph_cache, vector_raster
from vixl import render as R
from vixl.text import render_text

LATIN = "The quick brown fox jumps over the lazy dog AVATAR Typography WAVE fjord office waffle rn ff".split()
CYRILLIC = "Съешь же ещё этих мягких французских булок да выпей чаю Привет мир".split()
ARABIC = "مرحبا بالعالم نص عربي للتجربة السلام عليكم".split()


@pytest.fixture(autouse=True)
def fresh_caches(monkeypatch):
    monkeypatch.delenv("VIXL_GLYPH_CACHE", raising=False)
    glyph_cache.CACHE.reset()
    vector_raster.CACHE.clear()
    vector_raster.CACHE.bytes = 0
    yield
    glyph_cache.CACHE.reset()


@pytest.fixture
def rasteriser(monkeypatch):
    calls = []
    original = resvg_py.svg_to_bytes
    monkeypatch.setattr(resvg_py, "svg_to_bytes", lambda **kw: calls.append(1) or original(**kw))
    return calls


def text_layers(texts, **fields):
    p = Project(1200, 800, "white")
    p.apply([{"type": "text", "name": f"t{i}", "text": text, "size": 14, "x": 10, "y": 10, "color": "#123456",
              **fields} for i, text in enumerate(texts)], detail="brief")
    return p, [layer for layer in R.resolved_layers(p) if layer["type"] == "text"]


def cached(project, layer):
    """The layer drawn with the glyph cache and no whole-layer raster to fall back on."""
    vector_raster.CACHE.clear()
    vector_raster.CACHE.bytes = 0
    return render_text(project, layer).tobytes()


def whole(project, layer, monkeypatch):
    """The layer drawn as one SVG, the way every text layer was drawn before the cache."""
    with monkeypatch.context() as patch:
        patch.setenv("VIXL_GLYPH_CACHE", "off")
        return render_text(project, layer).tobytes()


def test_labels_that_share_glyphs_cost_about_one_rasteriser_call_per_distinct_glyph(rasteriser, monkeypatch):
    p, layers = text_layers([f"Label {i}" for i in range(500)])
    images = [render_text(p, layer).tobytes() for layer in layers]
    # 35 distinct glyphs-at-a-place (L, a, b, e, l and ten digits at three places). A glyph is drawn alone the
    # second time it comes up, so each costs at most two calls; without the cache this is 500.
    assert len(rasteriser) <= 70, len(rasteriser)
    assert all(image == whole(p, layer, monkeypatch) for image, layer in zip(images, layers))
    before = len(rasteriser)
    assert [render_text(p, layer).tobytes() for layer in layers[200:300]] == images[200:300]
    assert len(rasteriser) == before


@pytest.mark.parametrize("size", [9, 12, 13.5, 16, 24, 48])
def test_assembled_text_equals_the_whole_layer_svg_on_latin_cyrillic_and_arabic(size, monkeypatch):
    rng = random.Random(4)
    texts = [" ".join(rng.choice(words) for _ in range(rng.randrange(1, 4)))
             for words in (LATIN, CYRILLIC, ARABIC) for _ in range(25)]
    p, layers = text_layers(texts + texts, size=size)
    assembled = []
    original = glyph_cache.stencil

    def counting(*args):
        mask = original(*args)
        if glyph_cache.enabled():
            assembled.append(mask is not None)
        return mask

    monkeypatch.setattr(glyph_cache, "stencil", counting)
    for _ in range(3):  # First seen, drawn alone, then served from the cache.
        for layer in layers:
            assert cached(p, layer) == whole(p, layer, monkeypatch), layer["text"]
    # Most of them were put together from cached glyphs; where two glyphs share a pixel the layer is drawn whole.
    assert sum(assembled[-len(layers):]) > len(layers) // 2


def test_a_changed_font_size_or_place_gives_new_pixels(monkeypatch):
    drawn = []
    boxed = {"text_layout": {"width": 101}, "width": 101, "height": 30}
    for fields, changed in (({}, {}), ({"size": 15}, {}), ({"size": 22}, {}), ({"font": "DejaVu Sans"}, {}),
                            ({}, {**boxed, "align": "center"}), ({}, {**boxed, "align": "right"})):
        p, layers = text_layers([f"Label {i}" for i in range(3)], **fields)
        layers = [{**layer, **changed} for layer in layers]
        for _ in range(3):
            images = [cached(p, layer) for layer in layers]
        assert images == [whole(p, layer, monkeypatch) for layer in layers], (fields, changed)
        drawn.append(images[1])
    assert len(set(drawn)) == len(drawn)
    # Every variant was served from cached glyphs, each under its own keys.
    assert len({matrix[:4] for _, matrix in glyph_cache.CACHE}) >= 4


def test_text_that_does_not_repeat_costs_one_call_per_layer_as_before(rasteriser):
    rng = random.Random(2)
    texts = ["".join(rng.choice("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ") for _ in range(9))
             for _ in range(60)]
    p, layers = text_layers(texts)
    for layer in layers:
        render_text(p, layer)
    assert len(rasteriser) == len(layers)


def test_the_switch_turns_the_cache_off(rasteriser, monkeypatch):
    monkeypatch.setenv("VIXL_GLYPH_CACHE", "off")
    p, layers = text_layers([f"Label {i}" for i in range(30)])
    for layer in layers:
        render_text(p, layer)
    assert len(rasteriser) == 30 and not glyph_cache.CACHE and not glyph_cache.CACHE.seen


def test_stroked_and_placed_text_keep_the_svg_path(monkeypatch):
    monkeypatch.setattr(glyph_cache, "stencil", lambda *a: pytest.fail("the glyph cache drew this text"))
    p, layers = text_layers(["Label 1", "Label 2"])
    for layer in layers:
        render_text(p, {**layer, "stroke_width": 2, "stroke_color": "red"})
        render_text(p, layer, (80, 30), (1, 0, 0, 1, 0.5, 0.25))


def test_a_full_cache_evicts_and_stays_exact(monkeypatch):
    monkeypatch.setattr(glyph_cache.CACHE, "budget", 600)
    p, layers = text_layers([f"Label {i}" for i in range(120)])
    for _ in range(2):
        for layer in layers:
            assert cached(p, layer) == whole(p, layer, monkeypatch)
    assert glyph_cache.CACHE.bytes <= 600


def test_a_glyph_whose_canvas_would_be_large_is_left_to_the_whole_layer(rasteriser, monkeypatch):
    p, layers = text_layers(["Wide label"] * 3, size=120)
    for layer in layers:
        assert cached(p, layer) == whole(p, layer, monkeypatch)
    assert glyph_cache.LARGE in glyph_cache.CACHE.values()


def test_outline_boxes_cover_every_command_glyph_outlines_use():
    assert glyph_cache.outline_box("M10,20 L30,5 H-4 V50 Q1,2 3,60 Z") == (-4, 2, 30, 60)
    assert glyph_cache.outline_box("M0,0 C1,1 2,2 9,3 Z M5,5 L6,-7") == (0, -7, 9, 5)
    assert glyph_cache.outline_box("") is None and glyph_cache.outline_box("M1,1 a5,5 0 0 1 3,3") is None


def test_documents_render_the_same_with_and_without_the_cache_from_several_threads(monkeypatch):
    def document():
        p = Project(900, 700, "#fdf6e3")
        p.apply([{"type": "text", "name": f"t{i}", "text": f"Row {i // 6} · item {i}", "size": 13 + i % 3,
                  "x": 20 + (i % 6) * 145, "y": 20 + (i // 6) * 26, "color": ("#123", "rgba(200,30,30,0.6)")[i % 2]}
                 for i in range(150)], detail="brief")
        p.apply({"type": "opacity", "targets": [f"t{i}" for i in range(0, 150, 5)], "value": 0.5}, detail="brief")
        return p

    monkeypatch.setenv("VIXL_GLYPH_CACHE", "off")
    expected = R.render(document()).tobytes()
    monkeypatch.delenv("VIXL_GLYPH_CACHE")
    vector_raster.CACHE.clear()
    vector_raster.CACHE.bytes = 0
    results = []
    threads = [threading.Thread(target=lambda: results.append(R.render(document()).tobytes())) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert results == [expected] * 4
    assert glyph_cache.CACHE


def test_a_label_repeated_word_for_word_uses_the_whole_layer_raster_it_already_has(rasteriser):
    p, layers = text_layers(["Same words"] * 4, size=30)
    images = {render_text(p, layer).tobytes() for layer in layers}
    assert len(images) == 1 and len(rasteriser) == 1


def test_a_text_box_of_fractional_size_keeps_the_svg_path(monkeypatch):
    p, layers = text_layers(["Label 1"] * 3)
    boxed = [{**layer, "text_layout": {"width": 90.5}, "width": 90.5, "height": 30.25} for layer in layers]
    images = [cached(p, layer) for layer in boxed]
    assert images == [whole(p, layer, monkeypatch) for layer in boxed] and not glyph_cache.CACHE
