"""Hand-lettered work stays live text (#728): per-span rise, rotate and scale, and the seeded ``hand_set`` option."""

import io
import zipfile

import numpy as np
import pytest

from vixl import Project
from vixl.errors import VixlError
from vixl.imports import render_svg, sanitize_svg
from vixl.richtext import fitted
from vixl.render import resolved_layers

HAND = {"seed": 4, "rise": 6, "rotate": 7, "scale": 0.15}


def text_project(text="Fresh bread daily", color="#222222", **fields):
    p = Project(520, 160, "#f4efe6")
    p.apply({"type": "text", "name": "t", "text": text, "size": 44, "x": 30, "y": 40, "color": color, **fields})
    return p


def glyphs(p, name="t"):
    """The drawn glyphs of a text layer that the rich engine lays out, grouped by word."""
    layer = next(item for item in resolved_layers(p) if item["name"] == name)
    words, current = [], []
    for glyph in fitted(p, layer).glyphs:
        if glyph.text == " ":
            words.append(current)
            current = []
        else:
            current.append(glyph)
    return [word for word in [*words, current] if word]


def difference(a, b):
    return float(np.abs(np.asarray(a.convert("RGB"), dtype=int) - np.asarray(b.convert("RGB"), dtype=int)).mean())


def svg_image(p):
    root, width, height = sanitize_svg(p.export(format="SVG"), p.limits)
    return render_svg(root, width, height)


def pdf_page(p, report=None):
    import pypdfium2

    document = pypdfium2.PdfDocument(io.BytesIO(p.export(format="PDF", report=report)))
    try:
        page = document[0]
        return page.render(scale=1).to_pil(), page.get_textpage().get_text_range()
    finally:
        document.close()


def test_hand_set_varies_each_word_and_the_layer_stays_plain_editable_text():
    p = text_project(hand_set=HAND)
    layer = p.layer("t")
    assert layer["type"] == "text" and layer["text"] == "Fresh bread daily" and "rich" not in layer
    assert layer["hand_set"] == HAND
    words = glyphs(p)
    assert len(words) == 3
    baselines = [word[0].y for word in words]
    turns = [word[0].turn[0] for word in words]
    sizes = [word[0].size for word in words]
    assert len({round(v, 2) for v in baselines}) == 3 and max(baselines) - min(baselines) <= 12
    assert len({round(v, 2) for v in turns}) == 3 and all(abs(v) <= 7 for v in turns)
    assert len({round(v, 2) for v in sizes}) == 3 and all(44 * 0.85 <= v <= 44 * 1.15 for v in sizes)
    # Every letter of a word shares the word's lift, turn and size.
    assert all(len({(g.y, g.size, g.turn) for g in word}) == 1 for word in words)
    assert difference(p.render(), text_project().render()) > 0.5


def test_the_variation_is_seeded_and_stable_when_the_text_is_edited():
    first = text_project(hand_set=HAND)
    assert first.render().tobytes() == text_project(hand_set=HAND).render().tobytes()
    assert difference(first.render(), text_project(hand_set={**HAND, "seed": 5}).render()) > 0.3
    before = [(round(w[0].y, 3), w[0].turn[0], w[0].size) for w in glyphs(first)]
    first.apply({"type": "text-set", "target": "t", "text": "Fresh rolls daily"})
    assert first.layer("t")["hand_set"] == HAND and first.layer("t")["text"] == "Fresh rolls daily"
    after = [(round(w[0].y, 3), w[0].turn[0], w[0].size) for w in glyphs(first)]
    assert after == before, "each word keeps its numbers when another word's letters change"
    # Undo and redo, and a save and load, draw the same lettering.
    image = first.render().tobytes()
    first.undo()
    first.redo()
    assert first.render().tobytes() == image


def test_hand_set_by_letter_and_removal():
    p = text_project("wobble", hand_set={"seed": 2, "unit": "glyph", "rise": 4, "rotate": 9, "tracking": 3})
    letters = glyphs(p)[0]
    assert len({round(g.y, 2) for g in letters}) > 3 and len({g.turn[0] for g in letters}) > 3
    assert p.layer("t")["width"] != text_project("wobble").layer("t")["width"]
    p.apply({"type": "text-set", "target": "t", "hand_set": False})
    assert "hand_set" not in p.layer("t")
    assert p.render().tobytes() == text_project("wobble").render().tobytes()
    assert p.layer("t")["width"] == text_project("wobble").layer("t")["width"]


def test_true_uses_amounts_that_follow_the_size_and_bad_settings_are_refused():
    p = text_project(hand_set=True)
    assert p.layer("t")["hand_set"] == {}
    assert difference(p.render(), text_project().render()) > 0.3
    still = text_project(hand_set={"rise": 0, "rotate": 0, "scale": 0, "tracking": 0})
    assert still.render().tobytes() == text_project().render().tobytes()
    for bad in ({"rotate": 90}, {"unit": "line"}, {"wobble": 1}, {"seed": 1.5}):
        with pytest.raises(VixlError):
            text_project(hand_set=bad)
    result = text_project().apply({"type": "text-set", "target": "t", "hand_lettered": {"seed": 3}})
    assert result.get("normalized")


def test_raster_svg_and_pdf_draw_the_same_hand_set_text_and_pdf_keeps_it_as_text():
    p = text_project(hand_set=HAND)
    p.apply({"type": "text", "name": "letters", "text": "by letter", "x": 30, "y": 100, "size": 36, "color": "#b23a48",
             "hand_set": {"seed": 2, "unit": "glyph", "rotate": 9}})
    image = p.render()
    assert difference(image, svg_image(p)) < 0.05
    report = {}
    page, text = pdf_page(p, report)
    assert report["raster_fallbacks"] == {} and report["content"] == "vector"
    assert "Fresh bread daily" in text and "by letter" in text
    plain = text_project()
    baseline = difference(plain.render(), pdf_page(plain)[0])
    assert difference(image, page) < 2 * baseline + 0.5
    # The turned words are where the renderer put them: drawing the PDF without the turn would differ far more.
    assert difference(image, page) < difference(image, plain.render()) / 2


def test_text_checks_still_read_a_hand_set_layer():
    faint = text_project(color="#efe9df", hand_set=HAND)
    contrast = [i for i in faint.check(checks=["contrast"])["issues"] if i["check"] == "contrast"]
    assert contrast and contrast[0]["layers"] == ["t"]
    reference = [i for i in text_project(color="#efe9df").check(checks=["contrast"])["issues"] if i["check"] == "contrast"]
    assert [i.get("code") for i in contrast] == [i.get("code") for i in reference]
    fonts = [(i["check"], i["layers"]) for i in text_project(hand_set=HAND).check(checks=["fonts"])["issues"]]
    assert fonts == [("fonts", ["t"])]  # the proofing-font finding, as for the same layer without hand_set
    assert fonts == [(i["check"], i["layers"]) for i in text_project().check(checks=["fonts"])["issues"]]
    # A hand-set layer pushed off the canvas is still a text layer the bounds check reports.
    off = text_project(hand_set=HAND)
    off.apply({"type": "move", "target": "t", "x": 400, "y": 40})
    assert any(i["check"] == "bounds" and i.get("layers") == ["t"] for i in off.check(checks=["bounds"])["issues"])


def test_span_rise_rotate_and_scale_in_markdown_spans_and_text_style():
    p = Project(520, 120, "#f4efe6")
    p.apply({"type": "rich-text", "name": "t", "markdown": "Open [late]{rise=10 rotate=-8 scale=1.5} today", "x": 20,
             "y": 30, "size": 40, "color": "#222222"})
    spans = p.layer("t")["rich"]["spans"]
    assert spans[1] == {"text": "late", "rise": 10.0, "rotate": -8.0, "size": 60.0}
    opened, late, today = glyphs(p)
    assert late[0].y == pytest.approx(opened[0].y - 10) and today[0].y == pytest.approx(opened[0].y)
    assert late[0].turn[0] == -8 and opened[0].turn is None and late[0].size == 60
    # The turn's pivot is the middle of the word's baseline.
    assert late[0].x < late[0].turn[1] < late[-1].x + 60 and late[0].turn[2] == pytest.approx(late[0].y)
    assert difference(p.render(), svg_image(p)) < 0.05

    q = Project(520, 120, "#f4efe6")
    q.apply({"type": "text", "name": "t", "text": "Open late today", "x": 20, "y": 30, "size": 40, "color": "#222222"})
    q.apply({"type": "text-style", "target": "t", "match": "late", "rise": 10, "rotate": -8, "scale": 1.5})
    assert q.layer("t")["rich"]["spans"][1] == {"text": "late", "rise": 10, "rotate": -8, "size": 60.0}
    assert q.layer("t")["text"] == "Open late today"
    q.apply({"type": "text-style", "target": "t", "match": "late", "rise": 0, "rotate": 0})
    assert q.layer("t")["rich"]["spans"][1] == {"text": "late", "size": 60.0}
    with pytest.raises(VixlError):
        q.apply({"type": "text-style", "target": "t", "match": "late", "rotate": 270})
    r = Project(520, 120, "#f4efe6")
    r.apply({"type": "rich-text", "name": "t", "spans": [{"text": "Open "}, {"text": "late", "rise": 10, "scale": 1.5}],
             "size": 40})
    assert r.layer("t")["rich"]["spans"][1] == {"text": "late", "rise": 10, "size": 60.0}


def test_rise_moves_the_highlight_and_underline_with_the_word():
    p = Project(520, 120, "#f4efe6")
    p.apply({"type": "rich-text", "name": "t", "spans": [{"text": "up", "rise": 12, "underline": True, "highlight": "#ffee00"},
                                                        {"text": " flat", "underline": True}], "size": 40, "x": 20, "y": 40})
    layer = next(item for item in resolved_layers(p) if item["name"] == "t")
    rects = fitted(p, layer).rects
    lines = sorted(r[1] for r in rects if r[5] == "underline")
    assert lines[1] - lines[0] == pytest.approx(12)


def test_pptx_draws_hand_set_text_as_a_described_picture_and_scale_alone_stays_text():
    p = text_project(hand_set=HAND)
    report = {}
    data = p.export(format="PPTX", report=report)
    assert report["raster_fallbacks"]["1"] == [{"layer": "t", "reason": "hand-set text (per-word rise, turn or size)"}]
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        xml = archive.read("ppt/slides/slide1.xml").decode()
    assert "<p:pic>" in xml and 'descr="Fresh bread daily"' in xml
    q = Project(520, 120, "#f4efe6")
    q.apply({"type": "rich-text", "name": "t", "markdown": "Open [late]{scale=1.5} today", "size": 40, "x": 20, "y": 30,
             "font": "NotoSans-Regular.ttf"})
    report = {}
    data = q.export(format="PPTX", report=report)
    assert report["raster_fallbacks"] == {}
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        assert "late" in archive.read("ppt/slides/slide1.xml").decode()


def test_hand_set_survives_save_and_load_and_a_reduced_preview(tmp_path):
    p = text_project(hand_set=HAND)
    p.save(tmp_path / "sign.vixl")
    restored = Project.load(tmp_path / "sign.vixl")
    assert restored.layer("t")["hand_set"] == HAND
    assert restored.render().tobytes() == p.render().tobytes()
    from PIL import Image

    with Image.open(io.BytesIO(p.export(format="PNG", scale=0.5))) as half:
        assert difference(half, p.render().resize(half.size, Image.Resampling.BOX)) < 1.5


def test_irregular_points_text_layers_at_hand_set():
    p = text_project()
    with pytest.raises(VixlError, match="hand_set"):
        p.apply({"type": "irregular", "target": "t", "seed": 1})


def test_text_set_by_tab_stops_or_a_warp_is_drawn_as_before():
    tabs = [{"at": 300, "align": "right"}]
    tabbed = text_project("Soup\t4.50", tabs=tabs, hand_set=HAND)
    assert tabbed.layer("t")["hand_set"] == HAND
    assert tabbed.render().tobytes() == text_project("Soup\t4.50", tabs=tabs).render().tobytes()
    warped, plain = text_project(hand_set=HAND), text_project()
    for p in (warped, plain):
        p.apply({"type": "text-layout", "target": "t", "width": 400, "warp": "arc", "amount": 0.3})
    assert warped.render().tobytes() == plain.render().tobytes()

