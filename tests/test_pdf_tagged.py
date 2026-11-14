"""Tagged PDF: a structure tree from reading order and alt text, behind ``export(tagged=True)`` (#719)."""

import hashlib
import io
import re

from PIL import Image
import pypdf
import pytest

from vixl import Project, VixlError


def photo(p, name="photo", x=20, y=150):
    buffer = io.BytesIO()
    Image.new("RGB", (60, 40), "#3a6").save(buffer, "PNG")
    from vixl.assets import add_encoded

    asset, _ = add_encoded(p, buffer.getvalue())
    p.apply({"type": "add", "name": name, "asset": asset, "x": x, "y": y})


def poster():
    p = Project(400, 300, "white")
    p.apply([
        {"type": "text", "name": "body", "text": "Collected on the north ridge", "size": 14, "x": 20, "y": 90,
         "color": "#111111"},
        {"type": "text", "name": "title", "text": "Field notes", "size": 48, "x": 20, "y": 20, "color": "#111111"},
        {"type": "shape", "shape": "star", "name": "sparkle", "x": 330, "y": 20, "width": 40, "height": 40,
         "fill": "#fc0"},
        {"type": "shape", "shape": "rectangle", "name": "rule", "x": 20, "y": 120, "width": 300, "height": 2,
         "fill": "#888"},
    ])
    photo(p)
    p.apply([{"type": "accessibility", "lang": "en-GB"},
             {"type": "layer-intent", "target": "photo", "alt": "A fern"},
             {"type": "layer-intent", "target": "sparkle", "decorative": True}])
    return p


def tree(data):
    """(reader, [per page: [(tag, element)] in structure order])."""
    reader = pypdf.PdfReader(io.BytesIO(data))
    root = reader.trailer["/Root"]["/StructTreeRoot"]
    document = root["/K"].get_object()
    assert document["/S"] == "/Document"
    pages = []
    for section in document["/K"]:
        section = section.get_object()
        assert section["/S"] == "/Sect"
        pages.append([(kid.get_object()["/S"][1:], kid.get_object()) for kid in section["/K"]])
    return reader, pages


def marked(reader, page=0):
    """[(tag, mcid)] of the page's marked content, in drawing order."""
    content = reader.pages[page].get_contents().get_data().decode("latin-1")
    return [(tag, int(mcid)) for tag, mcid in re.findall(r"/(\w+) <</MCID (\d+)>> BDC", content)]


def test_untagged_output_is_unchanged_and_tagged_is_opt_in():
    p = poster()
    plain = p.export(format="PDF")
    assert plain == p.export(format="PDF", tagged=False)
    assert b"StructTreeRoot" not in plain and b"MarkInfo" not in plain
    reader = pypdf.PdfReader(io.BytesIO(plain))
    assert b"MCID" not in reader.pages[0].get_contents().get_data()
    # The untagged writer's bytes for a font-free page, as they were before tagging existed.
    flat = Project(120, 80, "white")
    flat.apply({"type": "shape", "shape": "rectangle", "name": "box", "x": 10, "y": 10, "width": 50, "height": 30,
                "fill": "#336699"})
    assert hashlib.sha256(flat.export(format="PDF", title="t")).hexdigest() == UNTAGGED_SHA256


UNTAGGED_SHA256 = "5d293be5a7d6b9e53ca5d2e34a46a0b61c7cfb27e96b0346688c59c515b50c13"


def test_structure_tree_follows_reading_order_and_maps_mcids_one_to_one():
    p = poster()
    report = {}
    data = p.export(format="PDF", tagged=True, report=report)
    assert report["tagged"] is True
    reader, pages = tree(data)
    catalog = reader.trailer["/Root"]
    assert catalog["/MarkInfo"]["/Marked"] is True or catalog["/MarkInfo"]["/Marked"] == True  # noqa: E712
    assert catalog["/Lang"] == "en-GB"
    elements = pages[0]
    # Top to bottom, not stacking order (body was added before title): heading, paragraph, figure.
    assert [tag for tag, _ in elements] == ["H1", "P", "Figure"]
    assert elements[2][1]["/Alt"] == "A fern"
    # Every MCID in the content stream belongs to exactly one element, and the ParentTree maps it back.
    content = marked(reader)
    assert sorted(mcid for _, mcid in content) == list(range(len(content))) == [0, 1, 2]
    by_mcid = {int(element["/K"]): (tag, element) for tag, element in elements}
    assert {mcid: tag for tag, mcid in content} == {mcid: tag for mcid, (tag, _) in by_mcid.items()}
    page = reader.pages[0]
    nums = catalog["/StructTreeRoot"]["/ParentTree"]["/Nums"]
    parents = dict(zip(nums[::2], nums[1::2]))[page["/StructParents"]]
    assert len(parents) == len(content)
    for mcid, ref in enumerate(parents):
        assert ref.get_object() == by_mcid[mcid][1]
        assert ref.get_object()["/Pg"].get_object() == page.get_object()
    # Decorative layers, undescribed shapes and the page background are artifacts: nothing is left unmarked.
    stream = page.get_contents().get_data().decode("latin-1")
    assert stream.count("/Artifact BMC") == 3
    assert stream.count("BDC") + stream.count("BMC") == stream.count("EMC") == 6


def test_explicit_reading_order_wins_and_drawing_order_is_untouched():
    p = poster()
    untouched = marked(pypdf.PdfReader(io.BytesIO(p.export(format="PDF", tagged=True))))
    p.apply({"type": "accessibility", "reading_order": ["photo", "body"]})
    reader, pages = tree(p.export(format="PDF", tagged=True))
    assert [tag for tag, _ in pages[0]] == ["Figure", "P", "H1"]
    assert marked(reader) == untouched


def test_groups_are_transparent_unless_described_and_rasterised_text_keeps_its_words():
    p = Project(400, 300, "white")
    p.apply([
        {"type": "text", "name": "a", "text": "First line", "size": 14, "x": 20, "y": 20, "color": "#111"},
        {"type": "text", "name": "b", "text": "Second line", "size": 14, "x": 20, "y": 60, "color": "#111"},
        {"type": "group", "name": "pair", "targets": ["a", "b"]},
        {"type": "shape", "shape": "ellipse", "name": "c1", "x": 200, "y": 200, "width": 40, "height": 40, "fill": "#c00"},
        {"type": "text", "name": "c2", "text": "42", "size": 14, "x": 210, "y": 212, "color": "#fff"},
        {"type": "group", "name": "badge", "targets": ["c1", "c2"]},
        {"type": "layer-intent", "target": "badge", "alt": "Badge reading 42"},
        {"type": "text", "name": "soft", "text": "Blurred words", "size": 14, "x": 20, "y": 120, "color": "#111"},
        {"type": "effect", "target": "soft", "name": "blur", "radius": 1},
    ])
    reader, pages = tree(p.export(format="PDF", tagged=True))
    tags = [tag for tag, _ in pages[0]]
    assert tags == ["P", "P", "P", "Figure"]
    assert pages[0][2][1]["/ActualText"] == "Blurred words"
    assert pages[0][3][1]["/Alt"] == "Badge reading 42"
    assert len(marked(reader)) == 4  # the described group is one sequence: its parts are not marked again


def test_pages_get_sections_and_raster_pages_one_described_figure():
    p = Project(400, 300, "white")
    p.apply([
        {"type": "text", "name": "one", "text": "Page one", "size": 14, "x": 20, "y": 20, "color": "#111"},
        {"type": "page", "action": "add", "name": "second"},
        {"type": "text", "name": "two", "text": "Page two", "size": 14, "x": 20, "y": 20, "color": "#111"},
    ])
    reader, pages = tree(p.export(format="PDF", tagged=True))
    assert [[tag for tag, _ in page] for page in pages] == [["P"], ["P"]]
    assert [page["/StructParents"] for page in reader.pages] == [0, 1]
    assert pages[1][0][1]["/Pg"].get_object() == reader.pages[1].get_object()
    reader, pages = tree(p.export(format="PDF", tagged=True, pdf_content="raster"))
    assert [[tag for tag, _ in page] for page in pages] == [["Figure"], ["Figure"]]
    assert pages[0][0][1]["/Alt"] == "Page one" and marked(reader, 1) == [("Figure", 0)]


def test_fillable_widgets_are_form_elements():
    from tests.test_forms import form

    p = form()
    reader, pages = tree(p.export(format="PDF", fillable=True, tagged=True))
    forms = [element for tag, element in pages[0] if tag == "Form"]
    page = reader.pages[0]
    widgets = [annot.get_object() for annot in page["/Annots"]]
    assert len(forms) == len(widgets) == 7
    nums = reader.trailer["/Root"]["/StructTreeRoot"]["/ParentTree"]["/Nums"]
    parents = dict(zip(nums[::2], nums[1::2]))
    for widget in widgets:
        element = parents[widget["/StructParent"]].get_object()
        assert element["/S"] == "/Form" and element["/K"]["/Type"] == "/OBJR"
        assert element["/K"]["/Obj"].get_object() == widget
    assert "Full name" in [element.get("/Alt") for element in forms]
    assert {tag for tag, _ in pages[0]} == {"P", "Form"}  # the labels are paragraphs; field boxes are artifacts
    plain = p.export(format="PDF", fillable=True)
    assert b"StructParent" not in plain and plain == p.export(format="PDF", fillable=True, tagged=False)


def test_tagged_is_refused_where_no_structure_can_be_written(tmp_path):
    p = poster()
    with pytest.raises(VixlError, match="tagged writes a PDF structure tree"):
        p.export(format="PNG", tagged=True)
    with pytest.raises(VixlError, match="tagged cannot be combined with scale"):
        p.export(format="PDF", tagged=True, scale=2)
    with pytest.raises(VixlError, match="tagged cannot be combined with proof"):
        p.export(format="PDF", tagged=True, proof=True)


def test_a_linked_document_is_one_figure_and_a_blended_page_one_described_image(tmp_path):
    tile = Project(200, 100, "#336699")
    tile.apply([{"type": "text", "name": "label", "text": "Tile", "size": 30, "x": 10, "y": 10, "color": "#fff"},
                {"type": "shape", "shape": "ellipse", "name": "dot", "x": 150, "y": 50, "width": 30, "height": 30,
                 "fill": "#fc0"},
                {"type": "layer-intent", "target": "dot", "alt": "Inner dot"}])
    tile.save(tmp_path / "tile.vixl")
    host = Project(600, 300, "white")
    host.save(tmp_path / "host.vixl")
    host.apply([{"type": "link", "source": "tile.vixl", "name": "tile", "x": 40, "y": 30},
                {"type": "layer-intent", "target": "tile", "alt": "A tile"}])
    report = {}
    reader, pages = tree(host.export(None, format="PDF", tagged=True, report=report))
    assert not report["raster_fallbacks"], "the link is drawn as vector artwork"
    assert [(tag, element["/Alt"]) for tag, element in pages[0]] == [("Figure", "A tile")]
    stream = reader.pages[0].get_contents().get_data().decode("latin-1")
    assert marked(reader) == [("Figure", 0)] and "Alt" not in stream  # nothing inside the link is marked again
    host.apply([{"type": "text", "name": "over", "text": "Multiplied", "size": 20, "x": 40, "y": 200, "color": "#111"},
                {"type": "blend", "target": "over", "value": "multiply"}])
    reader, pages = tree(host.export(None, format="PDF", tagged=True))
    assert [(tag, element["/Alt"]) for tag, element in pages[0]] == [("Figure", "Multiplied")]
    assert marked(reader) == [("Figure", 0)]


def test_cli_mcp_and_rest_take_tagged(tmp_path):
    from vixl.cli import main
    from vixl.interfaces import EXPORT_FIELDS
    from vixl.mcp_actions import options_schema

    path = tmp_path / "p.vixl"
    poster().save(path)
    out = tmp_path / "tagged.pdf"
    assert main(["-p", str(path), "export", str(out), "--tagged"]) in (0, None)
    assert "/StructTreeRoot" in pypdf.PdfReader(str(out)).trailer["/Root"]
    assert "tagged" in EXPORT_FIELDS
    field = options_schema("vixl_export", "file")["properties"]["tagged"]
    assert field["type"] == "boolean" and "structure tree" in field["description"]
