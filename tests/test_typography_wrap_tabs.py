"""Balanced and runt-free wrapping, tab stops with leaders, table leaders and layout accent words (craft plan 4a–4c)."""

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
