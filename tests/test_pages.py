import io
import re
import zipfile

import pytest

from vixl import Project
from vixl.commands import compile_command
from vixl.errors import VixlError


def deck():
    p = Project(960, 540, "#ffffff")
    p.apply([
        {"type": "master", "action": "add", "name": "std", "background": "#f4f4f4"},
        {"type": "shape", "shape": "rectangle", "name": "band", "width": 960, "height": 12, "x": 0, "y": 528, "fill": "#123"},
        {"type": "text", "text": "${page} / ${pages}", "name": "num", "size": 14, "x": 880, "y": 500, "color": "#333"},
        {"type": "page", "action": "add", "name": "cover", "master": "std"},
        {"type": "text", "text": "Quarterly Review", "name": "title", "size": 60, "x": 60, "y": 200, "color": "#111"},
        {"type": "page", "action": "add", "name": "results", "master": "std", "notes": "Revenue up 42%"},
        {"type": "text", "text": "Results", "name": "title", "size": 44, "x": 60, "y": 50, "color": "#111"},
        {"type": "rich-text", "name": "body", "markdown": "Revenue grew **42%**\n- Faster *checkout*\n- New markets",
         "size": 28, "width": 500, "x": 60, "y": 140, "color": "#222"},
        {"type": "page", "action": "add", "name": "close", "master": "std", "notes": "Questions"},
        {"type": "text", "text": "Thanks", "name": "title", "size": 44, "x": 60, "y": 50, "color": "#111"},
    ])
    return p


def test_first_page_add_keeps_existing_content_on_page_one():
    p = Project(200, 100)
    p.apply({"type": "text", "text": "Hello", "name": "hello"})
    p.apply({"type": "page", "action": "add", "name": "second"})
    pages = p.inspect()["pages"]
    assert [page["name"] for page in pages] == ["page-1", "second"]
    assert p.state["layers"] == []
    p.apply({"type": "page", "action": "select", "page": 1})
    assert [layer["name"] for layer in p.state["layers"]] == ["hello"]


def test_pages_keep_their_own_layers_and_operations_can_target_a_page():
    p = deck()
    assert p.inspect()["pages"][-1]["active"]
    p.apply({"type": "text", "text": "Hi", "name": "extra", "page": "cover"})
    assert p.state["page"] == next(page["id"] for page in p.state["pages"] if page["name"] == "cover")
    names = {page["name"]: page["layers"] for page in p.inspect()["pages"]}
    assert names["cover"] == 2 and names["results"] == 2 and names["close"] == 1
    p.apply({"type": "page", "action": "select", "page": "results"})
    assert sorted(layer["name"] for layer in p.state["layers"]) == ["body", "title"]


def test_master_layers_draw_underneath_with_page_variables():
    p = deck()
    from vixl.render import view_page

    view = view_page(p, "results")
    names = [layer["name"] for layer in view.state["layers"]]
    assert names[:2] == ["band", "num"] and "body" in names
    assert view.state["variables"]["page"] == 2 and view.state["variables"]["pages"] == 3
    assert view.state["canvas"]["background"] == "#f4f4f4"
    image = p.render(page="results").convert("RGB")
    assert image.getpixel((5, 5)) == (244, 244, 244)
    assert image.getpixel((480, 533)) == (17, 34, 51)


def test_master_layer_name_collisions_are_prefixed():
    p = deck()
    p.apply([{"type": "master", "action": "select", "name": "std"},
             {"type": "text", "text": "Footer", "name": "title", "size": 10, "x": 10, "y": 500}])
    from vixl.render import view_page

    names = [layer["name"] for layer in view_page(p, "results").state["layers"]]
    assert "master:std/title" in names and "title" in names


def test_duplicate_page_gets_fresh_ids_and_settings():
    p = deck()
    p.apply({"type": "page", "action": "add", "name": "copy", "duplicate": "results"})
    record = next(page for page in p.state["pages"] if page["name"] == "copy")
    assert record.get("notes") == "Revenue up 42%"
    original = {layer["id"] for layer in next(pg for pg in p.state["pages"] if pg["name"] == "results")["content"]["layers"]}
    copied = {layer["id"] for layer in p.state["layers"]}
    assert copied and not (copied & original)


def test_page_move_rename_hide_remove_and_undo():
    p = deck()
    p.apply({"type": "page", "action": "move", "page": "close", "index": 1})
    assert [page["name"] for page in p.state["pages"]] == ["close", "cover", "results"]
    p.apply({"type": "page", "action": "set", "page": "close", "rename": "end", "hidden": True, "transition": "fade"})
    record = next(page for page in p.state["pages"] if page["name"] == "end")
    assert record["hidden"] and record["transition"] == "fade"
    count = len(p.state["pages"])
    p.apply({"type": "page", "action": "remove", "page": "end"})
    assert len(p.state["pages"]) == count - 1
    p.undo()
    assert len(p.state["pages"]) == count
    with pytest.raises(VixlError):
        p.apply({"type": "page", "action": "select", "page": "missing"})


def test_pages_survive_save_and_load(tmp_path):
    p = deck()
    p.save(tmp_path / "deck.vixl")
    loaded = Project.load(tmp_path / "deck.vixl")
    assert [page["name"] for page in loaded.inspect()["pages"]] == [page["name"] for page in p.inspect()["pages"]]
    assert loaded.render(page="results").tobytes() == p.render(page="results").tobytes()


def test_vector_pdf_has_one_page_per_page_with_selectable_text(tmp_path):
    pypdf = pytest.importorskip("pypdf")
    p = deck()
    report = {}
    data = p.export(tmp_path / "deck.pdf", report=report)
    assert data == p.export(format="PDF"), "PDF output is deterministic"
    reader = pypdf.PdfReader(io.BytesIO(data))
    assert len(reader.pages) == 3
    text = reader.pages[1].extract_text()
    assert "Results" in text and "42%" in text and "Faster checkout" in text and "2 / 3" in text
    assert report["pages"] == 3 and report["raster_fallbacks"] == {}
    subset = pypdf.PdfReader(io.BytesIO(p.export(format="PDF", pages="2-3")))
    assert len(subset.pages) == 2


def test_page_numbers_skip_hidden_pages(tmp_path):
    pypdf = pytest.importorskip("pypdf")
    from vixl.render import view_page

    p = deck()
    p.apply([{"type": "page", "action": "add", "name": "appendix", "master": "std", "after": "results", "hidden": True},
             {"type": "page", "action": "select", "page": "cover"}])
    assert [page["name"] for page in p.state["pages"]] == ["cover", "results", "appendix", "close"]
    reader = pypdf.PdfReader(io.BytesIO(p.export(tmp_path / "deck.pdf")))
    numbers = [re.search(r"\d / \d", page.extract_text()).group() for page in reader.pages]
    assert numbers == ["1 / 3", "2 / 3", "3 / 3"]
    hidden = view_page(p, "appendix").state["variables"]
    assert (hidden["page"], hidden["pages"]) == (3, 3)
    assert (p.state["variables"]["page"], p.state["variables"]["pages"]) == (1, 3)


def test_raster_pdf_pages():
    pypdf = pytest.importorskip("pypdf")
    p = deck()
    reader = pypdf.PdfReader(io.BytesIO(p.export(format="PDF", pdf_content="raster", pages=["results"])))
    assert len(reader.pages) == 1 and not reader.pages[0].extract_text().strip()


def test_pptx_export_has_editable_slides_and_notes():
    p = deck()
    report = {}
    data = p.export(format="PPTX", report=report)
    assert data == p.export(format="PPTX"), "PowerPoint output is deterministic"
    names = zipfile.ZipFile(io.BytesIO(data)).namelist()
    assert {"ppt/slides/slide1.xml", "ppt/slides/slide3.xml", "ppt/notesSlides/notesSlide2.xml"} <= set(names)
    assert report["slides"] == 3 and report["notes"] == 2 and report["raster_fallbacks"] == {}
    pptx = pytest.importorskip("pptx")
    deck_file = pptx.Presentation(io.BytesIO(data))
    slides = list(deck_file.slides)
    assert slides[1].shapes.title.text == "Results"
    texts = [shape.text_frame.text for shape in slides[1].shapes if shape.has_text_frame]
    assert any("Faster checkout" in t for t in texts) and "2 / 3" in texts
    body = next(shape for shape in slides[1].shapes if shape.name == "body")
    runs = [run for paragraph in body.text_frame.paragraphs for run in paragraph.runs]
    assert any(run.text == "42%" and run.font.bold for run in runs)
    assert any(run.text == "checkout" and run.font.italic for run in runs)
    assert slides[1].notes_slide.notes_text_frame.text == "Revenue up 42%"
    assert deck_file.slide_height == 6858000


def test_pptx_needs_a_slide_sized_canvas():
    with pytest.raises(VixlError):
        Project(4000, 100).export(format="PPTX")  # 7.5 in tall would make it 300 in wide


def test_deck_checks_find_cross_page_problems():
    p = deck()
    p.apply([
        {"type": "page", "action": "select", "page": "close"},
        {"type": "move", "target": "title", "x": 300, "y": 50},
        {"type": "page", "action": "select", "page": "results"},
        {"type": "text", "text": "tiny caption", "name": "caption", "size": 12, "x": 60, "y": 400, "color": "#222"},
        {"type": "text", "text": " ".join(["word"] * 70), "name": "wall", "size": 20, "x": 60, "y": 300, "color": "#222"},
    ])
    result = p.check(checks=["title_position", "words", "min_font", "notes", "type_scale", "empty"],
                     deck={"min_font": 18})
    checks = {issue["check"] for issue in result["issues"]}
    assert {"words", "min_font", "notes"} <= checks
    words = next(issue for issue in result["issues"] if issue["check"] == "words")
    assert words["page"] == "results" and words["words"] > 60
    small = [issue for issue in result["issues"] if issue["check"] == "min_font"]
    assert any(issue["layers"] == ["caption"] for issue in small)
    assert not any(issue["layers"] == ["num"] for issue in small), "master layers are chrome"
    assert result["checked"]["pages"] == 3


def test_deck_title_position_flags_the_odd_title():
    p = Project(960, 540, "#ffffff")
    for index, x in enumerate((60, 60, 60, 200), 1):
        p.apply([{"type": "page", "action": "add", "name": f"s{index}"},
                 {"type": "text", "text": f"Slide {index}", "name": "title", "size": 44, "x": x, "y": 50, "color": "#111"}])
    result = p.check(checks=["title_position"])
    flagged = [issue["page"] for issue in result["issues"] if issue["check"] == "title_position"]
    assert flagged == ["s4"]


def test_deck_type_scale_flags_near_duplicate_sizes():
    p = Project(960, 540, "#ffffff")
    p.apply([{"type": "page", "action": "add", "name": "a"},
             {"type": "text", "text": "One", "size": 30, "x": 10, "y": 10, "color": "#000"},
             {"type": "page", "action": "add", "name": "b"},
             {"type": "text", "text": "Two", "size": 32, "x": 10, "y": 10, "color": "#000"}])
    result = p.check(checks=["type_scale"])
    assert any("almost the same" in issue["message"] for issue in result["issues"])


def test_deck_check_requires_pages():
    with pytest.raises(VixlError):
        Project(100, 100).check(checks=["deck"])


def test_contact_sheet_and_preview_of_all_pages():
    from vixl.deck import contact_sheet
    from vixl.proxy import render_preview

    p = deck()
    sheet = contact_sheet(p, width=200, columns=2)
    assert sheet.width == 2 * 200 + 3 * 16
    preview = render_preview(p, 600, 600, page="all")
    assert preview.width <= 600 and preview.height <= 600


def test_page_cli_commands_compile():
    assert compile_command("page add intro --master std --after 2 --notes 'a\\nb'") == {
        "type": "page", "action": "add", "name": "intro", "master": "std", "after": 2, "notes": "a\nb"}
    assert compile_command("page select 3") == {"type": "page", "action": "select", "page": 3}
    assert compile_command("master add std --from 1") == {"type": "master", "action": "add", "name": "std", "from": "1"}
    assert compile_command("page set intro --hidden --transition fade") == {
        "type": "page", "action": "set", "page": "intro", "hidden": True, "transition": "fade"}


def test_parse_pages():
    from vixl.pages import parse_pages

    assert parse_pages("1-3,5,intro") == [1, 2, 3, 5, "intro"]
    with pytest.raises(VixlError):
        parse_pages(" , ")
