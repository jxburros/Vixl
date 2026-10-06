import asyncio
import io
import json
import subprocess
import sys

import numpy as np
from PIL import Image
import pypdf
import pypdfium2
import pytest

from vixl import Project
from vixl.errors import VixlError
from vixl.imposition import cell_geometry, layout, mark_shapes, sheet_spec, slots
from vixl.interfaces import Session, mcp_server
from vixl.workflows import describe, dispatch

HEADER = "first_name,last_name,role,company,bar,bar_ink\n"
ROWS = [
    "Mara,Quinn,SPEAKER,Tidewick Café,#f2a541,#14263b",
    "Niamh,O'Brien,ATTENDEE,Northlight Ceramics,#a8d5c8,#14263b",
    "Zoë,Ångström-Okonkwo,SPEAKER,Saltmarsh Records,#f2a541,#14263b",
    "Sam,Okafor,STAFF,,#14263b,#ffffff",
    "Jo,Li,ATTENDEE,Independent,#a8d5c8,#14263b",
    "Ana Lucía,Gómez,SPONSOR,Faro Print Co.,#e2725b,#14263b",
    "Kwame,Mensah-Bonsu,SPEAKER,Driftwood Studio,#f2a541,#14263b",
]


def badge(path, **layout_options):
    """A 4 × 3 in, 300 dpi badge with variables for the name, the role and the bar colour."""
    p = Project(1200, 900, "#fffdf7")
    p.apply([
        {"type": "canvas", "dpi": 300},
        *({"type": "variable", "name": k, "value": v} for k, v in {
            "bar": "#a8d5c8", "bar_ink": "#14263b", "first_name": "Bartholomew", "last_name": "Featherstonehaugh",
            "company": "Port Ellery Museum", "role": "ATTENDEE"}.items()),
        {"type": "solid", "name": "bar", "color": "${bar}", "width": 1200, "height": 210, "y": 690},
        {"type": "text", "name": "event", "text": "HARBOR MAKERS SUMMIT 2026", "size": 34, "x": 80, "y": 60, "color": "#14263b"},
        {"type": "text", "name": "first", "text": "${first_name}", "size": 120, "x": 80, "y": 180, "color": "#14263b"},
        {"type": "text", "name": "last", "text": "${last_name}", "size": 70, "x": 80, "y": 340, "color": "#14263b"},
        {"type": "text", "name": "company", "text": "${company}", "size": 40, "x": 80, "y": 480, "color": "#444444"},
        {"type": "text", "name": "role", "text": "${role}", "size": 70, "x": 80, "y": 740, "color": "${bar_ink}"},
    ])
    if layout_options.get("boxed"):
        p.apply({"type": "text-layout", "target": "last", "width": 700, "height": 90})
    p.save(path)
    return p


def workspace(tmp_path, rows=ROWS, header=HEADER, **options):
    badge(tmp_path / "badge.vixl", **options)
    (tmp_path / "badges.csv").write_text(header + "\n".join(rows) + "\n", encoding="utf-8")
    return Session(None, workspace=tmp_path)


def merge(session, **request):
    request.setdefault("template", "badge.vixl")
    request.setdefault("data", "badges.csv")
    return dispatch(session, "merge-impose", request)


def pdf_pages(path):
    return pypdf.PdfReader(str(path)).pages


def raster(path, page=0, dpi=300):
    document = pypdfium2.PdfDocument(str(path))
    try:
        return np.asarray(document[page].render(scale=dpi / 72).to_pil().convert("RGB"), dtype=int)
    finally:
        document.close()


def test_merge_writes_a_vector_print_pdf_with_selectable_text(tmp_path):
    session = workspace(tmp_path)
    report = merge(session, output="print.pdf", sheet={"slug": "{template} · {first}-{last} · {page}/{pages}"})
    assert report["valid"] == 7 and report["invalid"] == [] and report["errors"] == [] and report["warnings"] == []
    assert report["raster_fallbacks"] == {} and report["fonts"] == 1 and report["pages"] == 2 and report["output"] == "print.pdf"
    grid = report["layout"]["grid"]
    assert (grid["cols"], grid["rows"], grid["per_page"]) == (2, 3, 6) and report["layout"]["item"]["trim"] == [4.0, 3.0]
    pages = pdf_pages(tmp_path / "print.pdf")
    assert len(pages) == 2 and all((float(p.mediabox.width), float(p.mediabox.height)) == (612, 792) for p in pages)
    first, second = (page.extract_text() for page in pages)
    for text in ("Mara", "Quinn", "Tidewick Café", "Niamh", "O'Brien", "Zoë", "Ångström-Okonkwo", "SPEAKER", "badge · 1-6 · 1/2"):
        assert text in first
    assert "Kwame" in second and "Mensah-Bonsu" in second and "badge · 7-7 · 2/2" in second
    assert second.count("HARBOR MAKERS SUMMIT 2026") == 1 and first.count("HARBOR MAKERS SUMMIT 2026") == 6
    assert first.index("Mara") < first.index("Niamh") < first.index("Zoë")  # reading order, left to right and down


def test_empty_cells_are_empty_values_not_missing_ones(tmp_path):
    session = workspace(tmp_path)
    report = merge(session, output="print.pdf")
    assert report["errors"] == []
    text = "\n".join(page.extract_text() for page in pdf_pages(tmp_path / "print.pdf"))
    after_sam = text[text.index("Okafor"):].split("HARBOR")[0]
    assert "STAFF" in after_sam and "Port Ellery" not in text and "Bartholomew" not in text  # no sample text leaks


def test_the_pdf_matches_the_sheet_document_and_marks_sit_in_the_margins(tmp_path):
    session = workspace(tmp_path)
    report = merge(session, output="print.pdf", sheet_document="print.vixl", sheet={"cols": 2, "rows": 3})
    assert report["sheet_document"] == "print.vixl"
    image = raster(tmp_path / "print.pdf")
    assert image.shape[1] == 2550 and image.shape[0] in (3300, 3301)
    image = image[:3300]
    # Grid 8 × 9 in centred on Letter: origin (0.25 in, 1 in); marks at the three vertical cut lines (x = 75, 1275, 2475).
    for x in (75, 1275, 2475):
        assert image[250:280, x - 1:x + 2].min() < 60 and image[285:295, x - 1:x + 2].min() > 200  # a mark, then a gap
    assert image[299:302, 25:50].min() < 60 and image[400, 25:50].min() > 200  # a horizontal mark at the first row edge
    assert image[2:200, 2:60].min() > 200  # the corner, outside every mark, stays blank
    sheet = Project.load(tmp_path / "print.vixl")
    assert len(sheet.state["pages"]) == 2 and sheet.state["canvas"]["dpi"] == 300
    sheet.apply({"type": "page", "action": "select", "page": 1})
    boxes = {layer["name"]: (layer["x"], layer["y"], layer["width"], layer["height"]) for layer in sheet.state["layers"]
             if layer["type"] == "link"}
    assert boxes["row-1"] == (75, 300, 1200, 900) and boxes["row-2"] == (1275, 300, 1200, 900)
    assert boxes["row-3"] == (75, 1200, 1200, 900) and boxes["row-6"] == (1275, 2100, 1200, 900)
    # The raster of the sheet document matches the vector PDF.
    drawn = np.asarray(sheet.render(page=1).convert("RGB"), dtype=int)
    assert np.abs(drawn - image).mean() < 3


def test_sheet_document_keeps_cells_as_live_links_and_follows_template_edits(tmp_path):
    session = workspace(tmp_path)
    merge(session, sheet_document="print.vixl", sheet={"slug": "{template} {page}/{pages}"})
    sheet = Project.load(tmp_path / "print.vixl")
    sheet.apply({"type": "page", "action": "select", "page": 1})
    link = sheet.layer("row-1")
    assert link["type"] == "link" and link["source"] == "badge.vixl" and link["variables"]["first_name"] == "Mara"
    assert link["variables"]["company"] == "Tidewick Café" and sheet.layer("row-4")["variables"]["company"] == ""
    assert sheet.state["merge"]["template"] == "badge.vixl" and sheet.state["merge"]["data"] == "badges.csv"
    before = np.asarray(sheet.render(page=1).convert("RGB"), dtype=int)
    template = Project.load(tmp_path / "badge.vixl")
    template.state["layers"][0]["fill"] = "#00ff00"  # the bar stops following the ${bar} variable
    template.save()
    after = np.asarray(Project.load(tmp_path / "print.vixl").render(page=1).convert("RGB"), dtype=int)
    assert np.abs(after - before).sum() > 0 and tuple(after[1100, 1175]) == (0, 255, 0)  # the sheet follows the template
    from vixl import links

    assert {item["state"] for item in links.status(Project.load(tmp_path / "print.vixl"))} == {"stale"}


def test_revision_is_one_rerun_of_the_recorded_merge(tmp_path):
    session = workspace(tmp_path)
    merge(session, output="print.pdf", sheet_document="print.vixl")
    with pytest.raises(VixlError) as error:
        merge(session, output="print.pdf")
    assert error.value.code == "output_exists" and "replace" in str(error.value)
    # An 8th badge and a new Sponsor colour in the data, then one rerun of the recorded merge.
    rows = [row.replace("#e2725b,#14263b", "#6b3f69,#ffffff") for row in ROWS] + ["Iris,Van der Berg,SPEAKER,Lowtide Labs,#f2a541,#14263b"]
    (tmp_path / "badges.csv").write_text(HEADER + "\n".join(rows) + "\n", encoding="utf-8")
    report = dispatch(session, "merge-impose", {"rerun": "print.vixl"})
    assert report["valid"] == 8 and report["pages"] == 2 and report["sheet_document"] == "print.vixl" and report["output"] == "print.pdf"
    text = "\n".join(page.extract_text() for page in pdf_pages(tmp_path / "print.pdf"))
    assert "Iris" in text and "Van der Berg" in text
    sheet = Project.load(tmp_path / "print.vixl")
    assert len(sheet.state["pages"]) == 2
    sheet.apply({"type": "page", "action": "select", "page": 1})
    assert sheet.layer("row-6")["variables"]["bar"] == "#6b3f69"
    narrower = dispatch(session, "merge-impose", {"rerun": "print.vixl", "sheet": {"cols": 1, "rows": 3}})
    assert narrower["pages"] == 3 and narrower["layout"]["grid"]["cols"] == 1
    with pytest.raises(VixlError, match="not made by merge-impose"):
        dispatch(session, "merge-impose", {"rerun": "badge.vixl"})


def test_validation_reports_every_row_before_writing(tmp_path):
    rows = [ROWS[0], "Tyrannosaurus-Rex-Jr,Featherstonehaugh-Villanueva-Smythe-Whitmore,STAFF,Acme,#f2a541,#14263b",
            "花子,山田,SPEAKER,Kumo,#f2a541,#14263b", ROWS[3]]
    session = workspace(tmp_path, rows, boxed=True)
    report = merge(session, output="print.pdf", dry_run=True)
    assert report["dry_run"] and report["rows"] == 4 and report["valid"] == 2 and report["invalid"] == [2, 3]
    codes = {(e["row"], e["code"]) for e in report["errors"]}
    assert (2, "overflow") in codes and (3, "missing_glyphs") in codes
    assert all("Tyrannosaurus" not in e["message"] and "花子" not in e["message"] for e in report["errors"])  # names, never values
    overflow = next(e for e in report["errors"] if e["code"] == "overflow")
    assert overflow["layer"] == "last" and "700×90" in overflow["message"]
    assert not (tmp_path / "print.pdf").exists()
    with pytest.raises(VixlError) as error:
        merge(session, output="print.pdf")
    assert error.value.code == "merge_invalid" and error.value.details["report"]["invalid"] == [2, 3]
    assert not (tmp_path / "print.pdf").exists()
    written = merge(session, output="print.pdf", skip_invalid=True)
    assert written["valid"] == 2 and written["invalid"] == [2, 3] and written["pages"] == 1
    text = pdf_pages(tmp_path / "print.pdf")[0].extract_text()
    assert "Mara" in text and "Sam" in text and "Tyrannosaurus" not in text


def test_missing_and_unknown_columns_are_named_with_suggestions(tmp_path):
    session = workspace(tmp_path, ["Mara,Quinn,SPEAKR,Tidewick,#f2a541"], header="first_name,last_name,rol,company,bar\n")
    report = merge(session, dry_run=True)
    columns = {(e["code"], e["column"]): e["message"] for e in report["errors"]}
    assert ("missing_column", "role") in columns and "did you mean 'rol'" in columns[("missing_column", "role")]
    assert ("missing_column", "bar_ink") in columns and report["valid"] == 1  # a data-level problem, not a bad row
    assert report["unknown_columns"] == ["rol"]
    assert [(w["code"], w["column"]) for w in report["warnings"]] == [("unknown_column", "rol")]
    assert "did you mean 'role'" in report["warnings"][0]["message"]
    with pytest.raises(VixlError) as error:
        merge(session, output="print.pdf")
    assert error.value.code == "merge_invalid" and not (tmp_path / "print.pdf").exists()
    relaxed = merge(session, output="print.pdf", defaults="warn", variables={"role": "GUEST", "bar_ink": "#000000"})
    assert relaxed["errors"] == [] and "GUEST" in pdf_pages(tmp_path / "print.pdf")[0].extract_text()
    strict = merge(session, dry_run=True, unknown="error", variables={"role": "x", "bar_ink": "#000"})
    assert [e["code"] for e in strict["errors"]] == ["unknown_column"]
    ignored = merge(session, dry_run=True, unknown="ignore", defaults="ignore")
    assert ignored["errors"] == [] and ignored["warnings"] == []


def test_design_check_flags_rows_that_break_the_design(tmp_path):
    rows = [ROWS[0], "Sam,Okafor,STAFF,Acme,#ffffff,#ffffff"]  # white role text on a white bar
    session = workspace(tmp_path, rows)
    report = merge(session, dry_run=True, check="design")
    assert report["invalid"] == [2] and any(e["code"] == "design" and e["row"] == 2 for e in report["errors"])
    assert merge(session, dry_run=True)["invalid"] == []


def test_layout_geometry_gutter_bleed_and_marks():
    card = Project.sized("business-card", "#ffffff", bleed=True)
    canvas = card.state["canvas"]
    plan = layout(canvas, {"size": "letter", "gutter": 0.25, "margin": 0.5})
    assert (plan["cols"], plan["rows"]) == (2, 4) and plan["trim"] == (1050, 600) and plan["bleed"] == 38
    assert plan["origin"] == (187.5, 337.5)  # the 2175 × 2625 px grid centred inside the 0.5 in margins
    # A corner copy bleeds fully on its two outer sides; the sides it shares with neighbours get half the gutter.
    trim, bleeds, box, crop = cell_geometry(plan, 0, 0, {(0, 0), (1, 0), (0, 1)})
    assert trim == (187.5, 337.5, 1050, 600) and bleeds == (38, 38, 37.5, 37.5) and box == (150, 300, 1125, 675)
    # The crop maps the rounded box back onto the template, so the trim edge stays at the template's bleed offset.
    assert crop == pytest.approx([0.5, 0.5, 1125.5, 675.5])
    assert cell_geometry(plan, 0, 0, {(0, 0)})[1] == (38, 38, 38, 38)  # no neighbour: full bleed
    with pytest.raises(VixlError, match="only 0.1267 in"):
        layout(canvas, {"bleed": 0.5})
    shapes = mark_shapes(plan, 2, 4)
    names = {shape[0] for shape in shapes}
    assert {"crop-top-1", "crop-top-4", "crop-bottom-4", "crop-left-8", "crop-right-8"} <= names  # two edges per column and row
    page_w, page_h = plan["page"]
    ox, oy = plan["origin"]
    offset = plan["marks"]["offset"]
    for name, kind, x, y, w, h in shapes:
        assert kind == "solid" and x >= 0 and y >= 0 and x + w <= page_w and y + h <= page_h
        if name.startswith("crop-top"):
            assert y + h <= oy - offset + 1
        elif name.startswith("crop-left"):
            assert x + w <= ox - offset + 1
        assert offset >= plan["bleed"]  # marks start outside the bleed


def test_mark_geometry_follows_the_cut_lines():
    badge_canvas = {"width": 1200, "height": 900, "dpi": 300}
    plan = layout(badge_canvas, {"cols": 2, "rows": 3})
    shapes = {s[0]: s for s in mark_shapes(plan, 2, 3)}
    # Gutter 0: the shared edge is one cut line, so a 2-column grid has three vertical cut lines.
    assert sorted(n for n in shapes if n.startswith("crop-top")) == ["crop-top-1", "crop-top-2", "crop-top-3"]
    assert sorted(n for n in shapes if n.startswith("crop-left")) == ["crop-left-1", "crop-left-2", "crop-left-3", "crop-left-4"]
    ox, oy = plan["origin"]
    top = shapes["crop-top-2"]
    assert top[2] + top[4] / 2 == pytest.approx(ox + 1200, abs=1) and top[3] + top[5] == pytest.approx(oy - plan["marks"]["offset"], abs=1)
    gapped = layout(badge_canvas, {"cols": 2, "rows": 3, "gutter": [0.1, 0.1], "margin": 0.2})
    assert len([n for n in {s[0] for s in mark_shapes(gapped, 2, 3)} if n.startswith("crop-top")]) == 4  # two edges per column


def test_layout_errors_say_what_to_change():
    canvas = {"width": 1200, "height": 900, "dpi": 300}
    with pytest.raises(VixlError, match="3 cols of 4 in items need 12 in but only 7.5.* are free"):
        layout(canvas, {"cols": 3, "margin": 0.5})
    with pytest.raises(VixlError, match="Crop marks need .* between the grid and the left edge"):
        layout(canvas, {"cols": 2, "rows": 3, "margin": 0.1, "align": "top-left"})
    assert layout(canvas, {"cols": 2, "rows": 3, "margin": 0.1, "align": "top-left", "crop_marks": False})["per_page"] == 6
    with pytest.raises(VixlError, match="does not fit inside the margins"):
        layout(canvas, {"width": 3, "height": 2, "unit": "in"})
    with pytest.raises(VixlError, match="screen size"):
        layout(canvas, {"size": "slide"})
    with pytest.raises(VixlError, match="Did you mean 'gutter'"):
        sheet_spec({"gutters": 0.1})
    with pytest.raises(VixlError, match="slug can use"):
        sheet_spec({"slug": "{nope}"})
    with pytest.raises(VixlError, match="bleed"):
        sheet_spec({"bleed": -1})
    assert layout(canvas, {"size": "a4", "orientation": "landscape"})["unit"] == "mm"
    assert layout(canvas, {"size": "a4"})["page"] == (2480, 3508)
    custom = layout(canvas, {"width": 11, "height": 8.5, "unit": "in", "orientation": "portrait"})
    assert custom["page"] == (2550, 3300)


def test_order_alignment_copies_and_no_marks(tmp_path):
    plan = layout({"width": 1200, "height": 900, "dpi": 300}, {"cols": 2, "rows": 3, "order": "columns"})
    assert slots(plan, 4) == [(0, 0, 0), (0, 0, 1), (0, 0, 2), (0, 1, 0)]
    session = workspace(tmp_path, ROWS[:2])
    report = merge(session, output="print.pdf", sheet_document="print.vixl", copies=3,
                   sheet={"cols": 2, "rows": 3, "align": "top-left", "crop_marks": False, "margin": 0.25})
    assert report["layout"]["copies"] == 6 and report["pages"] == 1 and report["layout"]["grid"]["origin"] == [0.25, 0.25]
    sheet = Project.load(tmp_path / "print.vixl")
    assert [layer["name"] for layer in sheet.state["layers"]] == ["row-1", "row-1-copy-2", "row-1-copy-3", "row-2",
                                                                  "row-2-copy-2", "row-2-copy-3"]
    assert sheet.layer("row-1")["x"] == 75 and sheet.layer("row-1")["y"] == 75
    text = pdf_pages(tmp_path / "print.pdf")[0].extract_text()
    assert text.count("Mara") == 3 and text.count("Niamh") == 3
    # A dry run is not stopped by outputs that already exist; the page of a metric size is exact.
    assert merge(session, output="print.pdf", dry_run=True)["dry_run"]
    a4 = merge(session, output="a4.pdf", sheet={"size": "a4", "cols": 1, "rows": 3, "margin": 5})
    page = pdf_pages(tmp_path / "a4.pdf")[0]
    assert (float(page.mediabox.width), float(page.mediabox.height)) == pytest.approx((595.276, 841.89), abs=0.01)
    assert a4["layout"]["page"]["unit"] == "mm" and a4["layout"]["grid"]["margin"] == [5.0, 5.0, 5.0, 5.0]


def test_bleed_gutter_and_exact_page_boxes(tmp_path):
    card = Project.sized("business-card", "#ffffff", bleed=True)
    card.apply([{"type": "variable", "name": "brand", "value": "#336699"}, {"type": "variable", "name": "who", "value": "Ada"},
                {"type": "solid", "name": "ink", "color": "${brand}"},
                {"type": "text", "name": "name", "text": "${who}", "size": 80, "x": 150, "y": 250, "color": "#ffffff"}])
    card.save(tmp_path / "card.vixl")
    (tmp_path / "cards.csv").write_text("who,brand\nAda Lovelace,#336699\nGrace Hopper,#993366\nAlan Turing,#339966\n")
    session = Session(None, workspace=tmp_path)
    report = dispatch(session, "merge-impose", {"template": "card.vixl", "data": "cards.csv", "output": "cards.pdf",
                                                "sheet_document": "cards.vixl",
                                                "sheet": {"size": "letter", "gutter": 0.5, "margin": 0.4}})
    assert report["layout"]["item"]["bleed"] == pytest.approx(0.1267, abs=1e-3) and report["layout"]["grid"]["cols"] == 2
    page = pdf_pages(tmp_path / "cards.pdf")[0]
    assert (float(page.mediabox.width), float(page.mediabox.height)) == (612, 792)
    assert "Ada Lovelace" in page.extract_text()
    sheet = Project.load(tmp_path / "cards.vixl")
    link = sheet.layer("row-1")
    # Each copy's box is trim plus bleed on every side (no neighbour closer than twice the bleed here).
    assert (link["width"], link["height"]) == (1126, 676) and link["crop"] == [0, 0, 1126, 676]
    assert link["fit"] == "stretch"
    # With the bleed lowered, only part of the template's bleed is printed.
    narrow = dispatch(session, "merge-impose", {"template": "card.vixl", "data": "cards.csv", "sheet_document": "narrow.vixl",
                                                "sheet": {"bleed": 0.0625, "gutter": 0.5, "margin": 0.4}})
    assert narrow["layout"]["item"]["bleed"] == pytest.approx(0.0625, abs=1e-3)
    small = Project.load(tmp_path / "narrow.vixl").layer("row-1")
    assert 1050 + 2 * 18 <= small["width"] <= 1050 + 2 * 19 and 18 <= small["crop"][0] <= 20


def test_shared_edges_split_the_gutter_between_neighbours():
    canvas = Project.sized("business-card", "#ffffff", bleed=True).state["canvas"]
    plan = layout(canvas, {"size": "letter", "cols": 2, "rows": 2, "gutter": 0.05, "margin": 0.5})
    occupied = {(0, 0), (1, 0), (0, 1), (1, 1)}
    gutter = plan["gutter"][0]
    left_item = cell_geometry(plan, 0, 0, occupied)
    right_item = cell_geometry(plan, 1, 0, occupied)
    assert left_item[1][2] == pytest.approx(gutter / 2) and right_item[1][0] == pytest.approx(gutter / 2)
    gap_left = left_item[2][0] + left_item[2][2]
    gap_right = right_item[2][0]
    assert gap_left <= gap_right + 1  # the printed areas of two copies never overlap by more than rounding


def test_image_columns_are_validated_and_embedded(tmp_path):
    Image.new("RGB", (40, 40), "#ff0000").save(tmp_path / "red.png")
    Image.new("RGB", (40, 40), "#0000ff").save(tmp_path / "blue.png")
    photo = Project(300, 200, "#ffffff")
    photo.apply([{"type": "canvas", "dpi": 300}, {"type": "variable", "name": "who", "value": "Sample"},
                 {"type": "text", "name": "name", "text": "${who}", "size": 30, "x": 10, "y": 150, "color": "#000"}])
    from vixl.assets import add_encoded

    asset, _ = add_encoded(photo, (tmp_path / "red.png").read_bytes())
    photo.apply([{"type": "variable", "name": "photo", "value": asset}, {"type": "add", "asset": asset, "name": "pic"}, {"type": "resize", "target": "pic", "width": 300, "height": 140},
                 {"type": "replace-contents", "target": "pic", "variable": "photo"}])
    photo.save(tmp_path / "photo.vixl")
    (tmp_path / "people.csv").write_text("who,photo\nAda,red.png\nGrace,blue.png\n")
    session = Session(None, workspace=tmp_path)
    report = dispatch(session, "merge-impose", {"template": "photo.vixl", "data": "people.csv", "sheet_document": "people.vixl",
                                                "sheet": {"size": "letter", "margin": 0.5}})
    assert report["variables"]["images"] == ["photo"] and report["errors"] == []
    sheet = Project.load(tmp_path / "people.vixl")
    assert sheet.layer("row-2")["variables"]["photo"] == "blue.png"
    drawn = sheet.render()
    ox, oy = round(report["layout"]["grid"]["origin"][0] * 300), round(report["layout"]["grid"]["origin"][1] * 300)
    assert drawn.getpixel((ox + 150, oy + 60))[:3] == (255, 0, 0)
    second = [layer for layer in sheet.state["layers"] if layer["name"] == "row-2"][0]
    assert drawn.getpixel((second["x"] + 150, second["y"] + 60))[:3] == (0, 0, 255)
    (tmp_path / "bad.csv").write_text("who,photo\nAda,missing.png\nGrace,\n")
    bad = dispatch(session, "merge-impose", {"template": "photo.vixl", "data": "bad.csv", "dry_run": True})
    assert [(e["row"], e["code"]) for e in bad["errors"]] == [(1, "missing_image"), (2, "missing_image")]
    outside = tmp_path.parent / "outside.png"
    Image.new("RGB", (4, 4)).save(outside)
    (tmp_path / "evil.csv").write_text(f"who,photo\nAda,../{outside.name}\n")
    evil = dispatch(session, "merge-impose", {"template": "photo.vixl", "data": "evil.csv", "dry_run": True})
    assert evil["errors"][0]["code"] == "missing_image" and "outside the workspace" in evil["errors"][0]["message"]


def test_inline_rows_and_constants(tmp_path):
    session = workspace(tmp_path)
    rows = [{"first_name": "Ada", "last_name": "Lovelace", "role": "SPEAKER", "company": None, "bar": "#f2a541", "bar_ink": "#000"}]
    report = dispatch(session, "merge-impose", {"template": "badge.vixl", "rows": rows, "output": "inline.pdf"})
    assert report["valid"] == 1 and "Ada" in pdf_pages(tmp_path / "inline.pdf")[0].extract_text()
    with pytest.raises(VixlError, match="not both"):
        merge(session, rows=rows, dry_run=True)
    with pytest.raises(VixlError, match="Give output"):
        merge(session)
    partial = dispatch(session, "merge-impose", {"template": "badge.vixl", "rows": [{"first_name": "Ada"}, {"first_name": "Bo"}],
                                                 "variables": {"last_name": "X", "role": "R", "company": "C", "bar": "#fff",
                                                               "bar_ink": "#000"}, "dry_run": True})
    assert partial["errors"] == [] and partial["valid"] == 2


def test_outputs_and_paths_stay_inside_the_workspace(tmp_path):
    workspace_dir = tmp_path / "ws"
    workspace_dir.mkdir()
    session = workspace(workspace_dir)
    for field, value in (("output", "../escape.pdf"), ("sheet_document", "../escape.vixl"), ("data", "../badges.csv"),
                         ("template", "../badge.vixl")):
        request = {"template": "badge.vixl", "data": "badges.csv", "output": "ok.pdf", **{field: value}}
        with pytest.raises(VixlError) as error:
            dispatch(session, "merge-impose", request)
        assert error.value.code == "forbidden"
    assert not (tmp_path / "escape.pdf").exists() and not (workspace_dir / "ok.pdf").exists()
    with pytest.raises(VixlError, match="output is a .pdf"):
        merge(session, output="print.png")
    with pytest.raises(VixlError, match="does not exist"):
        merge(session, output="missing/print.pdf")
    with pytest.raises(VixlError, match="Data file does not exist"):
        merge(session, data="nope.csv", dry_run=True)


def test_skip_invalid_with_everything_invalid_and_page_artboard_selection(tmp_path):
    session = workspace(tmp_path, ["花子,山田,SPEAKER,Kumo,#f2a541,#14263b"])
    with pytest.raises(VixlError, match="No valid rows"):
        merge(session, output="print.pdf", skip_invalid=True)
    template = Project.load(tmp_path / "badge.vixl")
    template.apply({"type": "artboard", "name": "front", "width": 600, "height": 450, "background": "#ffffff"})
    template.save()
    with pytest.raises(VixlError, match="no artboard 'back'"):
        merge(session, dry_run=True, artboard="back")
    report = merge(session, dry_run=True, artboard="front")
    assert report["layout"]["item"]["trim"] == [2.0, 1.5] and report["layout"]["grid"]["cols"] == 4  # the artboard is the item


def test_cli_merge_and_rerun(tmp_path):
    workspace(tmp_path)

    def run(*args):
        return subprocess.run([sys.executable, "-m", "vixl", *args], cwd=tmp_path, capture_output=True, timeout=120)

    dry = run("merge", "badge.vixl", "--data", "badges.csv", "--dry-run")
    assert dry.returncode == 0, dry.stderr
    assert json.loads(dry.stdout)["layout"]["grid"]["per_page"] == 6 and not (tmp_path / "print.pdf").exists()
    done = run("merge", "badge.vixl", "--data", "badges.csv", "--out", "print.pdf", "--sheet-document", "print.vixl", "--cols", "1",
               "--rows", "3", "--margin", "0.5", "--slug", "{template} {page}/{pages}", "--registration")
    assert done.returncode == 0, done.stderr
    report = json.loads(done.stdout)
    assert report["pages"] == 3 and report["output"] == "print.pdf" and report["layout"]["marks"]["registration"]
    again = run("merge", "badge.vixl", "--data", "badges.csv", "--out", "print.pdf")
    assert again.returncode == 1
    (tmp_path / "badges.csv").write_text(HEADER + "\n".join(ROWS[:2]) + "\n", encoding="utf-8")
    rerun = run("merge", "--rerun", "print.vixl", "--out", "print.pdf", "--replace")
    assert rerun.returncode == 0, rerun.stderr
    assert json.loads(rerun.stdout)["pages"] == 1 and len(pdf_pages(tmp_path / "print.pdf")) == 1
    missing = run("merge", "badge.vixl", "--out", "x.pdf", "--json")
    assert missing.returncode == 1 and json.loads(missing.stderr)["error"] == "invalid_operation"
    helped = run("merge", "--help")
    assert helped.returncode == 0 and b"--sheet-document" in helped.stdout
    (tmp_path / "request.json").write_text(json.dumps({"template": "badge.vixl", "data": "badges.csv", "output": "via-workflow.pdf"}))
    flow = run("workflow", "merge-impose", "--request", "request.json", "--workspace", ".")
    assert flow.returncode == 0, flow.stderr
    assert json.loads(flow.stdout)["output"] == "via-workflow.pdf" and (tmp_path / "via-workflow.pdf").exists()


def test_workflow_schema_and_mcp(tmp_path):
    properties = describe()["actions"]["merge-impose"]
    assert set(properties["properties"]) == set(properties["fields"]) and properties["required"] == []
    session = workspace(tmp_path)
    server = mcp_server(workspace=tmp_path)

    async def call(name, arguments):
        try:
            result = await server.call_tool(name, arguments)
        except Exception as exc:  # a ToolError carries the JSON error
            return {"failed": str(exc)}
        content = result[0] if isinstance(result, tuple) else result
        return json.loads("".join(getattr(item, "text", "") for item in content))

    answer = asyncio.run(call("vixl_workflow", {"action": "merge-impose", "document": "badge.vixl",
                                                 "request": {"data": "badges.csv", "output": "print.pdf"}}))
    assert answer["valid"] == 7 and answer["output"] == "print.pdf" and (tmp_path / "print.pdf").exists()
    failed = asyncio.run(call("vixl_workflow", {"action": "merge-impose", "document": "badge.vixl",
                                                 "request": {"data": "badges.csv", "output": "../x.pdf"}}))
    assert "forbidden" in failed["failed"]
    typo = asyncio.run(call("vixl_workflow", {"action": "merge-impose", "document": "badge.vixl",
                                               "request": {"data": "badges.csv", "ouput": "x.pdf"}}))
    assert "Unknown workflow request field" in typo["failed"]
    assert session.workspace == tmp_path


def test_pdf_from_the_sheet_document_is_also_vector_with_selectable_text(tmp_path):
    session = workspace(tmp_path)
    merge(session, sheet_document="print.vixl")
    sheet = Project.load(tmp_path / "print.vixl")
    data = sheet.export(None, format="PDF", pdf_content="vector")
    text = pypdf.PdfReader(io.BytesIO(data)).pages[0].extract_text()
    assert "Mara" in text and "Quinn" in text
    # Export of the editable sheet still supports every other output (a raster PNG of sheet 1 here).
    png = sheet.export(None, format="PNG", page=1)
    assert Image.open(io.BytesIO(png)).size == (2550, 3300)


def test_a_chosen_page_of_a_multi_page_template_is_merged(tmp_path):
    template = Project(600, 300, "#ffffff")
    template.apply([{"type": "canvas", "dpi": 300}, {"type": "variable", "name": "who", "value": "Sample"},
                    {"type": "text", "name": "front", "text": "Front ${who}", "size": 40, "x": 20, "y": 20, "color": "#000000"},
                    {"type": "page", "action": "add", "name": "back"},
                    {"type": "text", "name": "backside", "text": "Back ${who}", "size": 40, "x": 20, "y": 20, "color": "#000000"},
                    {"type": "page", "action": "select", "page": 1}])
    template.save(tmp_path / "card.vixl")
    (tmp_path / "who.csv").write_text("who\nAda\nGrace\n")
    session = Session(None, workspace=tmp_path)
    report = dispatch(session, "merge-impose", {"template": "card.vixl", "data": "who.csv", "page": "back", "output": "back.pdf",
                                                "sheet_document": "back.vixl"})
    text = pdf_pages(tmp_path / "back.pdf")[0].extract_text()
    assert "Back Ada" in text and "Back Grace" in text and "Front" not in text and report["valid"] == 2
    link = Project.load(tmp_path / "back.vixl").state["pages"][0]
    assert link["name"] == "sheet-1"
    sheet = Project.load(tmp_path / "back.vixl")
    assert sheet.layer("row-1")["source_page"] == "back"
    with pytest.raises(VixlError, match="nope"):
        dispatch(session, "merge-impose", {"template": "card.vixl", "data": "who.csv", "page": "nope", "dry_run": True})
