"""Balanced and runt-free wrapping, tab stops with leaders, table leaders and layout accent words (craft plan 4a–4c)."""

import io
import re
import zipfile

import pytest

from vixl import Project
from vixl.errors import VixlError
from vixl.text import plan_glyphs
from vixl.text_metrics import drawn_lines
from vixl.variety import document_defaults

RUNT = "The gulls are sleeping on the silver stone"


def boxed(text, width, size=40, canvas=(900, 400), **layout):
    layout.setdefault("wrap", "greedy")
    p = Project(*canvas)
    p.apply([{"type": "text", "name": "t", "text": text, "size": size, "color": "#000000", "x": 20, "y": 20},
             {"type": "text-layout", "target": "t", "width": width, **layout}])
    return p


def rows(p, name="t"):
    return [(text, width) for _, text, width in drawn_lines(p, p.layer(name))]


def pptx_xml(p, tmp_path, name="out.pptx"):
    path = tmp_path / name
    p.export(str(path), overwrite=True)
    with zipfile.ZipFile(path) as archive:
        return archive.read("ppt/slides/slide1.xml").decode()


def test_balance_keeps_the_line_count_and_evens_the_lines():
    greedy, balanced = rows(boxed(RUNT, 760)), rows(boxed(RUNT, 760, wrap="balance"))
    assert [t for t, _ in greedy] == ["The gulls are sleeping on the silver", "stone"]
    assert len(balanced) == len(greedy)
    assert " ".join(t for t, _ in balanced) == RUNT
    widths = [w for _, w in balanced]
    assert max(widths) < max(w for _, w in greedy)
    assert min(widths) / max(widths) > 0.8


def test_pretty_pulls_a_word_down_instead_of_leaving_one_alone():
    lines = rows(boxed(RUNT, 760, wrap="pretty"))
    assert [t for t, _ in lines] == ["The gulls are sleeping on the", "silver stone"]
    # Nothing to fix: a two-word last line stays as greedy set it.
    assert rows(boxed(RUNT, 470, wrap="pretty")) == rows(boxed(RUNT, 470))


def test_rich_text_wraps_the_same_way():
    for wrap in ("balance", "pretty"):
        p = boxed(RUNT, 760, wrap=wrap)
        plain = [t for t, _ in rows(p)]
        p.apply({"type": "text-style", "target": "t", "match": "gulls", "color": "#ff0000"})
        assert p.layer("t").get("rich") and [t for t, _ in rows(p)] == plain


def test_balanced_breaks_are_shared_by_every_export(tmp_path):
    p = boxed(RUNT, 760, wrap="balance")
    lines = [t for t, _ in rows(p)]
    glyphs = plan_glyphs(p, p.layer("t"))
    assert len({round(g[3]) for g in glyphs}) == len(lines)  # PDF draws from the same placed glyphs
    import pypdfium2

    p.export(str(tmp_path / "out.pdf"), overwrite=True)
    text = pypdfium2.PdfDocument(str(tmp_path / "out.pdf"))[0].get_textpage().get_text_range()
    assert [line.strip() for line in text.splitlines() if line.strip()] == lines
    xml = pptx_xml(p, tmp_path)
    runs = re.search(r"<a:p>.*?</a:p>", xml.split("<p:txBody>")[1]).group(0)
    assert runs.count("<a:br/>") == len(lines) - 1
    assert [t.strip() for t in re.findall(r"<a:t>([^<]*)</a:t>", runs)] == lines
    p.apply({"type": "text-style", "target": "t", "match": "gulls", "color": "#ff0000"})
    rich = pptx_xml(p, tmp_path, "rich.pptx").split("<p:txBody>")[1]
    assert rich.count("<a:br/>") == len(lines) - 1


def test_greedy_text_is_left_for_powerpoint_to_wrap(tmp_path):
    assert "<a:br/>" not in pptx_xml(boxed(RUNT, 760), tmp_path)


def test_headings_balance_by_default():
    def heading(**layout):
        p = Project(900, 400)
        document_defaults(p, seed=3)
        p.apply([{"type": "text", "name": "t", "text": RUNT, "stage": "h1", "x": 20, "y": 20},
                 {"type": "text-layout", "target": "t", "width": 700, **layout}])
        return p.layer("t")["text_layout"]

    assert heading()["wrap"] == "balance"
    assert heading(wrap="greedy")["wrap"] == "greedy"
    p = Project(900, 400)
    document_defaults(p, seed=3)
    p.apply([{"type": "text", "name": "body", "text": RUNT, "stage": "body", "x": 20, "y": 20},
             {"type": "text-layout", "target": "body", "width": 700}])
    assert "wrap" not in p.layer("body")["text_layout"]


def test_a_wrap_survives_a_new_box():
    p = boxed(RUNT, 760, wrap="pretty")
    p.apply({"type": "text-layout", "target": "t", "width": 700})
    assert p.layer("t")["text_layout"]["wrap"] == "pretty"


def test_layout_headlines_balance_in_new_documents():
    p = Project(1080, 1080)
    document_defaults(p, seed=3)
    p.apply({"type": "layout-apply", "name": "hero-statement", "title": "Lighthouse nights on the quay",
             "seed": 3, "unfilled": "omit"})
    assert p.layer("headline")["text_layout"].get("wrap") == "balance"


def test_wrap_aliases_and_validation():
    p = Project(400, 200)
    p.apply({"type": "text", "name": "t", "text": "Hello there", "size": 30})
    result = p.apply({"type": "text-layout", "target": "t", "width": 200, "wrap": "balanced"})
    assert p.layer("t")["text_layout"]["wrap"] == "balance" and result["normalized"]
    with pytest.raises(VixlError):
        p.apply({"type": "text-layout", "target": "t", "width": 200, "wrap": "zigzag"})


MENU = "Latte\t4.50\nFlat white\t12.25\nTea\t3"


def menu(stops, width=400):
    p = Project(500, 300)
    p.apply([{"type": "text", "name": "menu", "text": MENU, "size": 24, "color": "#000000", "tabs": stops,
              "x": 20, "y": 20},
             {"type": "text-layout", "target": "menu", "width": width}])
    return p


def glyph_x(p, line):
    """(text, x) of each glyph on one line of the menu layer."""
    from vixl.text import placed_glyphs

    return [(glyph[5], glyph[2]) for glyph in placed_glyphs(p, p.layer("menu")) if glyph[6] == line]


def test_right_and_decimal_tab_stops_line_up():
    p = menu([{"at": 300, "align": "right"}])
    ends = []
    for line in range(3):
        glyphs = glyph_x(p, line)
        ends.append(glyphs[-1][1])
    assert max(ends) - min(ends) < 15  # right edges share the stop (last glyph origins, digits are equal width)
    p = menu([{"at": 300, "align": "decimal"}])
    points = [x for line in range(2) for text, x in glyph_x(p, line) if text == "."]
    assert len(points) == 2 and abs(points[0] - points[1]) < 0.5
    assert "\t" in p.layer("menu")["text"]


def test_leaders_fill_the_gap_and_line_up():
    p = menu([{"at": "90%", "align": "right", "leader": "."}])
    dots = {line: [x for text, x in glyph_x(p, line) if text == "."] for line in range(3)}
    assert all(len(found) > 10 for found in dots.values())
    # The leader grid starts at the line origin, so dots in every row share x positions.
    shared = set(round(x, 3) for x in dots[0]) & set(round(x, 3) for x in dots[2])
    assert len(shared) > 5


def test_tab_stops_in_pptx(tmp_path):
    xml = pptx_xml(menu([{"at": 300, "align": "decimal", "leader": "."}]), tmp_path)
    assert xml.count('algn="dec"') == 3 and "<a:tabLst>" in xml
    texts = re.findall(r"<a:t>([^<]*)</a:t>", xml)
    assert texts[0].startswith("Latte ....") and texts[0].endswith("\t4.50")


def test_tab_row_extracts_as_text_from_pdf():
    pypdf = pytest.importorskip("pypdf")
    p = menu([{"at": 300, "align": "decimal", "leader": "."}])
    reader = pypdf.PdfReader(io.BytesIO(p.export(format="PDF")))
    lines = reader.pages[0].extract_text().splitlines()
    assert re.fullmatch(r"Latte \.+ 4\.50", lines[0])
    assert re.fullmatch(r"Flat white \.+ 12\.25", lines[1])


def test_tab_stop_validation_and_removal():
    with pytest.raises(VixlError):
        menu([{"at": 300, "align": "middle"}])
    with pytest.raises(VixlError):
        menu([{"at": "far"}])
    p = menu([{"at": 300}])
    p.apply({"type": "text-set", "target": "menu", "tabs": []})
    assert "tabs" not in p.layer("menu")
    result = p.apply({"type": "text-set", "target": "menu", "tab_stops": [{"at": 200}]})
    assert p.layer("menu")["tabs"] == [{"at": 200}] and result["normalized"]


def table(tmp_path=None, leader="."):
    p = Project(600, 300)
    p.apply({"type": "table", "name": "menu", "x": 20, "y": 20, "width": 500, "borders": "none",
             "table": [["Drink", "Price"], ["Latte", 4.5], ["Flat white", 12.25], ["Tea", 3]],
             "columns": [{"width": "1fr", "leader": leader}, {"align": "decimal", "format": "0.00"}]})
    return p


def test_table_column_leaders(tmp_path):
    p = table()
    group = p.layer("menu")
    parts = {layer["table_part"]: layer for layer in p.state["layers"] if layer.get("parent") == group["id"]}
    assert group["table"]["summary"]["leaders"] == 3
    for row in (1, 2, 3):
        dots, name, price = parts[f"leader-{row}-0"], parts[f"cell-{row}-0"], parts[f"cell-{row}-1"]
        assert set(dots["text"]) == {"."}
        assert name["x"] + name["width"] < dots["x"] < dots["x"] + dots["width"] < price["x"]
    assert "leader-0-0" not in parts  # the header row gets none
    texts = re.findall(r"<a:t>([^<]*)</a:t>", pptx_xml(p, tmp_path))
    assert any(t.startswith("Latte ...") for t in texts)
    p.apply({"type": "table", "target": "menu", "columns": [{"width": "1fr"}, {"align": "decimal"}]})
    assert not any(layer.get("table_part", "").startswith("leader") for layer in p.state["layers"])


def test_accent_words_style_the_headline():
    p = Project(1080, 1080)
    result = p.apply({"type": "layout-apply", "name": "hero-statement", "seed": 3, "unfilled": "omit",
                      "title": "Winter warmers for a winterland quay", "accent": ["winter", "Sledge"]})
    assert any("accent_words" in note for note in result["normalized"])
    headline = p.layer("headline")
    spans = headline["rich"]["spans"]
    assert spans[0] == {"text": "Winter", "color": "@accent-text"}
    assert all(span.get("color") is None for span in spans[1:])  # 'winterland' is not the word
    assert p.state["layout"]["accent_words"] == {"styled": ["winter"], "missing": ["Sledge"]}
    assert any("Sledge" in warning for warning in result["warnings"])
    assert not [issue for issue in p.check()["issues"] if issue.get("code") == "text-overflow"]


def roles(p):
    p.apply({"type": "palette-apply", "name": "slate"})
    return p


def test_accent_words_style_plain_text_and_text_set():
    p = roles(Project(900, 300))
    result = p.apply({"type": "text", "name": "t", "text": "Winter warmers for a winterland quay", "size": 40,
                      "x": 20, "y": 20, "accents": "winter"})
    assert any("accent_words" in note for note in result["normalized"])
    assert p.layer("t")["rich"]["spans"][:2] == [{"text": "Winter", "color": "@accent-text"},
                                                {"text": " warmers for a winterland quay"}]
    result = p.apply({"type": "text-set", "target": "t", "accent_words": ["quay", "sledge"]})
    spans = p.layer("t")["rich"]["spans"]
    assert spans[-1] == {"text": "quay", "color": "@accent-text"} and spans[0]["color"] == "@accent-text"
    assert any("sledge" in warning for warning in result["warnings"])
    assert "accent_words" not in p.layer("t")  # an edit, not a stored field
    p.render()


def test_accent_words_need_the_palette_roles_and_skip_accent_colored_text():
    with pytest.raises(VixlError, match="accent-text"):
        Project(400, 200).apply({"type": "text", "text": "Winter quay", "accent_words": ["winter"]})
    p = roles(Project(400, 200))
    result = p.apply({"type": "text", "name": "t", "text": "Winter quay", "color": "@accent-text",
                      "accent_words": ["winter"]})
    assert not p.layer("t").get("rich") and any("already set in the accent color" in w for w in result["warnings"])


SC = "Small Caps"


def small_caps(font=None, **extra):
    p = Project(600, 200, "white")
    if font:
        from pathlib import Path

        import vixl
        from vixl.fonts import import_font

        import_font(p, str(Path(vixl.__file__).parent / "data" / "NotoSans-Regular.ttf"), "noto")
    p.apply({"type": "text", "name": "t", "text": SC, "size": 40, "color": "#000000", "x": 20, "y": 20,
             "text_transform": "small-caps", "font": "noto" if font else "DejaVuSans.ttf", **extra})
    return p


def drawn(p, name="t"):
    from vixl.render import resolved_layers
    from vixl.richtext import fitted

    layer = next(item for item in resolved_layers(p) if item["name"] == name)
    return fitted(p, layer).glyphs


def test_small_caps_are_synthesized_when_the_font_has_no_smcp():
    p = small_caps()
    glyphs = [g for g in drawn(p) if g.name != "space"]
    # DejaVu Sans has no small capitals: lowercase letters are its capitals at 0.7 of the size.
    assert [(g.name, g.size) for g in glyphs] == [("S", 40), ("M", 28), ("A", 28), ("L", 28), ("L", 28),
                                                  ("C", 40), ("A", 28), ("P", 28), ("S", 28)]
    assert p.layer("t")["text"] == SC  # the stored text keeps its case
    plain = Project(600, 200, "white")
    plain.apply({"type": "text", "name": "t", "text": SC.upper(), "size": 40, "x": 20, "y": 20, "font": "DejaVuSans.ttf"})
    assert p.layer("t")["height"] < plain.layer("t")["height"] + 1 and p.layer("t")["width"] < plain.layer("t")["width"]


def test_small_caps_use_the_fonts_own_smcp_glyphs():
    glyphs = [g for g in drawn(small_caps(font="noto")) if g.name != "space"]
    assert [g.name for g in glyphs] == ["S", "m.sc", "a.sc", "l.sc", "l.sc", "C", "a.sc", "p.sc", "s.sc"]
    assert {g.size for g in glyphs} == {40}


def test_small_caps_on_rich_text_spans_and_text_style():
    p = Project(600, 200, "white")
    p.apply({"type": "rich-text", "name": "t", "markdown": "In [small caps]{small-caps} now", "size": 30,
             "font": "DejaVuSans.ttf"})  # no smcp, so the small capitals are synthesized
    assert {"text": "small caps", "small_caps": True} in p.layer("t")["rich"]["spans"]
    result = p.apply({"type": "rich-text", "name": "s", "size": 30, "spans": [{"text": "Note ", "smallCaps": True}]})
    assert p.layer("s")["rich"]["spans"][0]["small_caps"] and result["normalized"]
    p.apply({"type": "text-style", "target": "t", "match": "now", "small_caps": True})
    assert p.layer("t")["rich"]["spans"][-1] == {"text": "now", "small_caps": True}
    p.apply({"type": "text-style", "target": "t", "match": "now", "small_caps": False})
    assert "small_caps" not in p.layer("t")["rich"]["spans"][-1]
    sizes = {g.text: g.size for g in drawn(p) if g.text.strip()}
    assert sizes["I"] == 30 and sizes["S"] == 21 and sizes["n"] == 30


def test_small_caps_aliases():
    p = Project(400, 200)
    result = p.apply({"type": "text", "name": "t", "text": "x", "font_variant": "smallcaps"})
    assert p.layer("t")["text_transform"] == "small-caps" and len(result["normalized"]) == 2
    p.apply({"type": "text-set", "target": "t", "text_transform": "none"})
    assert "text_transform" not in p.layer("t")


def test_small_caps_agree_in_every_export(tmp_path):
    import pypdfium2

    p = small_caps()
    glyphs = drawn(p)
    p.export(str(tmp_path / "out.pdf"), overwrite=True)
    # Synthesized small capitals are capitals, and a PDF reads them as drawn.
    assert pypdfium2.PdfDocument(str(tmp_path / "out.pdf"))[0].get_textpage().get_text_range().strip() == "SMALL CAPS"
    svg = p.export(format="SVG", svg_document=False).decode()
    assert svg.count("<path") == len([g for g in glyphs if g.name != "space"])
    xml = pptx_xml(p, tmp_path)
    # PowerPoint sets the run's own text in small caps.
    assert 'cap="small"' in xml and re.findall(r"<a:t>([^<]*)</a:t>", xml) == [SC]


QUOTE = "“Hang the quote,” she said."


def hanging(text=QUOTE, align="left", width=None, x=40, **extra):
    p = Project(700, 300, "white")
    p.apply({"type": "text", "name": "t", "text": text, "size": 36, "color": "#000000", "x": x, "y": 20,
             "align": align, **extra})
    if width:
        p.apply({"type": "text-layout", "target": "t", "width": width})
    return p


def test_a_hanging_quote_sits_left_of_the_text_box():
    import numpy as np

    off, on = hanging(), hanging(hanging_punctuation=True)
    quote, letter = drawn(on)[:2]
    assert quote.text == "“" and quote.hung and quote.x < -10  # left of the box edge
    assert letter.text == "H" and not letter.hung and abs(letter.x) < 4  # the letters start at the edge
    # The box starts at the letters, so the layer is narrower by the quote, and the quote is drawn in the margin.
    assert on.layer("t")["width"] < off.layer("t")["width"] - 10
    assert (np.asarray(on.render().convert("L"))[:, :40] < 128).any()
    assert not (np.asarray(off.render().convert("L"))[:, :40] < 128).any()


def test_hanging_punctuation_in_boxed_and_aligned_lines():
    p = hanging("Words “quoted” and more", width=150, hanging_punctuation=True)
    rows = {}
    for glyph in drawn(p):
        rows.setdefault(glyph.line, []).append(glyph)
    starts = [row[0] for row in rows.values()]
    # A wrapped line that starts with a quote hangs it, and the quoted word fits whole thanks to it.
    assert [g.hung for g in starts] == [False, True, False, False] and starts[1].x < -10
    assert "".join(g.text for g in rows[1]) == "“quoted”"
    right = hanging("— “The end.”", align="right", width=330, hanging_punctuation=True)
    glyphs = drawn(right)
    tail = [g for g in glyphs if g.hung]
    assert [g.text for g in tail] == [".", "”"] and tail[-1].x > 330 - 5
    centred = drawn(hanging("“Centred.”", align="center", width=330, hanging_punctuation=True))
    letters = [g for g in centred if not g.hung]
    assert centred[0].hung and centred[-1].hung and len(letters) == 7


def test_text_without_hanging_marks_keeps_the_plain_engine():
    from vixl.render import resolved_layers

    p = hanging("No quotes here", hanging_punctuation=True)
    assert not next(item for item in resolved_layers(p) if item["name"] == "t").get("rich")
    result = p.apply({"type": "text-set", "target": "t", "hang_quotes": False})
    assert "hanging_punctuation" not in p.layer("t") and result["normalized"]


def test_bounds_and_fit_text_use_the_hung_extents():
    def bounds(p):
        return [issue.get("code") for issue in p.check(checks=["bounds"])["issues"] if issue["check"] == "bounds"]

    assert "cut-off" in bounds(hanging(x=4, hanging_punctuation=True))
    assert "cut-off" not in bounds(hanging(x=4))
    # fit-text measures the letters between the edges: the hung quote does not need room in the box.
    sizes = {}
    for hang in (False, True):
        p = hanging("“A quote that fills”", x=60, **({"hanging_punctuation": True} if hang else {}))
        p.apply({"type": "fit-text", "target": "t", "width": 420, "height": 60, "minimum": 12, "maximum": 90})
        sizes[hang] = p.layer("t")["size"]
    assert sizes[True] > sizes[False]


def test_hanging_punctuation_in_pptx(tmp_path):
    xml = pptx_xml(hanging(width=500, hanging_punctuation=True), tmp_path)
    paragraph = re.search(r"<a:pPr[^>]*>", xml.split("<p:txBody>")[1]).group(0)
    margin, indent = (int(re.search(rf'{key}="(-?\d+)"', paragraph).group(1)) for key in ("marL", "indent"))
    assert 'hangingPunct="1"' in paragraph and margin == -indent > 0
    assert "hangingPunct" not in pptx_xml(hanging(width=500), tmp_path, "plain.pptx")
