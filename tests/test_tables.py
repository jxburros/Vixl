"""Data-bound tables (#169): rows or a CSV become an ordinary group of vector layers kept in sync."""

import io

import pytest

from vixl import Project
from vixl.commands import compile_command
from vixl.errors import VixlError
from vixl.schema import validate_operation

MENU = [["Item", "Price"], ["Espresso", 3.25], ["Flat white", 12.5], ["Tea", 8], ["Seasonal pour-over", 6.75]]


def make(**options):
    p = Project(900, 700, "#ffffff")
    p.apply({"type": "table", "name": "Menu", "x": 40, "y": 40, "width": 520, "table": MENU, **options})
    return p


def children(p, name="Menu"):
    ident = p.layer(name)["id"]
    return [layer for layer in p.state["layers"] if layer.get("parent") == ident]


def cell(p, row, column, name="Menu"):
    return next(layer for layer in children(p, name) if layer.get("table_part") == f"cell-{row}-{column}")


def right_edge(layer):
    return layer["x"] + layer["width"]


def test_table_is_a_group_of_ordinary_vector_layers():
    p = make()
    group = p.layer("Menu")
    assert group["type"] == "group" and group["table"]["rows"][0] == ["Item", "Price"]
    assert group["width"] == 520 and group["height"] == sum(group["table"]["summary"]["row_heights"])
    assert {layer["type"] for layer in children(p)} == {"shape", "text"}
    assert cell(p, 1, 0)["text"] == "Espresso" and cell(p, 0, 1)["text"] == "Price"
    # Numeric columns right-align by default; text columns left-align.
    assert group["table"]["summary"]["aligns"] == ["left", "right"]
    assert len({right_edge(cell(p, i, 1)) for i in range(1, 5)}) == 1
    assert len({cell(p, i, 0)["x"] for i in range(5)}) == 1
    assert p.inspect()["layers"]
    p.render()


def test_decimal_alignment_lines_up_the_points_of_a_price_list():
    p = make(columns=[{}, {"align": "decimal"}])
    from vixl.charts import Kit, Style

    style = Style(p, {}, 900, 700)
    kit = Kit(p, {}, style)
    size = cell(p, 1, 1)["size"]
    points = []
    for row in range(1, 5):
        layer = cell(p, row, 1)
        whole = layer["text"].split(".")[0]
        points.append(layer["x"] + kit.width(whole, size))
    assert max(points) - min(points) <= 1.0, points  # "8" ends where the others' points are
    assert right_edge(cell(p, 3, 1)) < right_edge(cell(p, 1, 1))  # so it does not reach the right edge
    formatted = make(columns=[{}, {"align": "decimal", "format": "$0.00"}])
    assert cell(formatted, 3, 1)["text"] == "$8.00" and cell(formatted, 2, 1)["text"] == "$12.50"


def test_table_data_updates_cells_and_rows_without_layout_drift_and_keeps_ids():
    p = make(columns=[{}, {"align": "decimal", "format": "$0.00"}], zebra=True)
    before = {layer["table_part"]: (layer["id"], layer["x"], layer["y"]) for layer in children(p)}
    p.apply({"type": "table-data", "target": "Menu", "set": [{"row": "Tea", "column": "Price", "value": 8.5}]})
    after = {layer["table_part"]: (layer["id"], layer["x"], layer["y"]) for layer in children(p)}
    assert set(after) == set(before)
    assert all(after[key][0] == before[key][0] for key in before)  # same layer IDs
    assert all(after[key][1:] == before[key][1:] for key in before if key != "cell-3-1")  # nothing else moved
    assert cell(p, 3, 1)["text"] == "$8.50" and right_edge(cell(p, 3, 1)) == right_edge(cell(p, 1, 1))
    p.apply({"type": "table-data", "target": "Menu", "append": [{"Item": "Mocha", "Price": 4.5}],
             "remove_rows": ["Espresso"]})
    rows = p.layer("Menu")["table"]["rows"]
    assert [row[0] for row in rows] == ["Item", "Flat white", "Tea", "Seasonal pour-over", "Mocha"]
    p.apply({"type": "table-data", "target": "Menu", "add_columns": [{"name": "Size", "values": ["M", "S", "L", "M"]}]})
    assert p.layer("Menu")["table"]["summary"]["columns"] == 3 and cell(p, 0, 2)["text"] == "Size"
    p.apply({"type": "table-data", "target": "Menu", "remove_columns": ["Size"]})
    assert p.layer("Menu")["table"]["summary"]["columns"] == 2


def test_csv_bound_table_reloads(tmp_path):
    data = tmp_path / "prices.csv"
    data.write_text("Plan,Seats,Price\nStarter,1,9\nTeam,10,49\n", encoding="utf-8")
    p = Project(800, 600, "#ffffff")
    p._workspace = tmp_path
    p.apply({"type": "table", "name": "Plans", "csv": "prices.csv", "csv_columns": ["Plan", "Price"]})
    assert p.layer("Plans")["table"]["rows"] == [["Plan", "Price"], ["Starter", "9"], ["Team", "49"]]
    ident = cell(p, 1, 1, "Plans")["id"]
    data.write_text("Plan,Seats,Price\nStarter,1,12\nTeam,10,49\nScale,50,199\n", encoding="utf-8")
    p.apply({"type": "table-data", "target": "Plans", "reload": True})
    assert cell(p, 1, 1, "Plans")["text"] == "12" and cell(p, 1, 1, "Plans")["id"] == ident
    assert cell(p, 3, 0, "Plans")["text"] == "Scale"


def test_restyle_with_target_and_options():
    p = make()
    p.apply({"type": "table", "target": "Menu", "header_fill": "#1d3557", "borders": "all", "zebra": "#f1f5f9"})
    parts = {layer["table_part"] for layer in children(p)}
    assert {"header-band", "rule-col-1", "rule-left", "band-2"} <= parts
    assert cell(p, 0, 0)["color"] in ("#ffffff", "#FFFFFF")  # header text reads on the dark band
    p.apply({"type": "table", "target": "Menu", "borders": "none", "zebra": None, "header_fill": None})
    assert not any(key.startswith(("rule-", "band-", "header-")) for key in (l["table_part"] for l in children(p)))


def test_fractional_and_fixed_column_widths():
    p = make(columns=[{"width": "2fr"}, {"width": "1fr"}])
    widths = p.layer("Menu")["table"]["summary"]["column_widths"]
    assert sum(widths) == 520 and abs(widths[0] - 2 * widths[1]) <= 2
    p = make(columns=[{"width": 400}, {}])
    assert p.layer("Menu")["table"]["summary"]["column_widths"][0] == 400


def test_long_text_wraps_and_the_row_grows():
    p = Project(900, 700, "#ffffff")
    p.apply({"type": "table", "name": "Specs", "width": 360,
             "table": [["Feature", "Notes"], ["Battery", "Lasts all day with the screen on and a little more besides"]]})
    heights = p.layer("Specs")["table"]["summary"]["row_heights"]
    assert heights[1] > heights[0] * 1.5
    assert "\n" in cell(p, 1, 1, "Specs")["text"]


def test_too_narrow_a_table_warns():
    p = Project(900, 700, "#ffffff")
    result = p.apply({"type": "table", "name": "T", "width": 60, "table": [["Name", "Description"], ["Extraordinary", "x"]]})
    assert any("needs about" in w for w in result.get("warnings", []))
    assert p.layer("T")["table"]["summary"]["overflow"] is True


def test_errors_say_what_to_fix():
    p = make()
    with pytest.raises(VixlError) as caught:
        p.apply({"type": "table", "table": [["a", "b"], ["c"]]})
    assert "every row needs 2" in str(caught.value)
    with pytest.raises(VixlError) as caught:
        p.apply({"type": "table-data", "target": "Menu", "set": [{"row": "Te", "column": "Price", "value": 1}]})
    assert "Tea" in str(caught.value)
    with pytest.raises(VixlError):
        p.apply({"type": "table-data", "target": "Menu"})


def test_aliases_are_normalized():
    p = Project(600, 400, "#ffffff")
    result = p.apply({"type": "table", "rows": [["A", "B"], [1, 2]], "striped": True})
    assert result["success"] and p.layer("table")["table"]["zebra"] is True


def test_document_round_trip(tmp_path):
    p = make(columns=[{}, {"align": "decimal"}])
    p.save(tmp_path / "menu.vixl")
    again = Project.load(tmp_path / "menu.vixl")
    assert again.layer("Menu")["table"]["rows"] == p.layer("Menu")["table"]["rows"]


def test_vector_exports_keep_the_table_as_text(tmp_path):
    p = make()
    svg = p.export(tmp_path / "t.svg", format="SVG")
    assert b"<image" not in svg
    report = {}
    pdf = p.export(tmp_path / "t.pdf", format="PDF", pdf_content="vector", report=report)
    assert report["raster_fallbacks"] == {}
    pypdf = pytest.importorskip("pypdf")
    text = pypdf.PdfReader(io.BytesIO(pdf)).pages[0].extract_text()
    assert "Espresso" in text and "12.5" in text


def test_pptx_export_has_a_native_table():
    pptx = pytest.importorskip("pptx")
    p = Project(1280, 720, "#ffffff")
    p.apply([{"type": "page", "action": "add", "name": "prices"},
             {"type": "table", "name": "Menu", "x": 80, "y": 120, "width": 700, "table": MENU, "header_fill": "#1d3557",
              "columns": [{}, {"align": "decimal", "format": "$0.00"}]}])
    report = {}
    data = p.export(format="PPTX", report=report)
    assert data == p.export(format="PPTX")
    presentation = pptx.Presentation(io.BytesIO(data))
    tables = [shape for slide in presentation.slides for shape in slide.shapes if shape.has_table]
    assert len(tables) == 1
    table = tables[0].table
    assert len(table.rows) == 5 and len(table.columns) == 2
    assert table.cell(0, 0).text == "Item" and table.cell(2, 1).text == "$12.50"
    assert report["tables"]["1"][0]["native"] is True
    assert not report.get("raster_fallbacks")


def test_rotated_table_exports_as_shapes():
    pptx = pytest.importorskip("pptx")
    p = make()
    p.apply({"type": "rotate", "target": "Menu", "value": 10})
    report = {}
    data = p.export(format="PPTX", report=report)
    presentation = pptx.Presentation(io.BytesIO(data))
    assert not any(shape.has_table for slide in presentation.slides for shape in slide.shapes)
    assert report["tables"]["1"][0]["native"] is False


def test_cli_compiles_table_commands():
    op = compile_command(["table", "--table", '[["A","B"],[1,2]]', "--align", "left,decimal", "--zebra", "--width", "300"])
    assert op == {"type": "table", "table": [["A", "B"], [1, 2]], "zebra": True, "width": 300,
                  "columns": [{"align": "left"}, {"align": "decimal"}]}
    validate_operation(op)
    op = compile_command(["table-data", "--target", "Menu", "--set", "Tea:Price=9.5", "--remove-row", "2"])
    assert op == {"type": "table-data", "target": "Menu", "set": [{"row": "Tea", "column": "Price", "value": 9.5}],
                  "remove_rows": [2]}
    validate_operation(op)
