"""One dataset drives charts, tables and rendered text through an atomic apply."""

from copy import deepcopy

import pytest

from vixl import Project
from vixl.commands import compile_command
from vixl.errors import VixlError
from vixl.plugins.charts.datasets import derive_data
from vixl.render import document_variables, resolved_layers
from vixl.variables import substitute

DATA = [["Month", "Tea", "Coffee"], ["Jan", 10, 30], ["Feb", 20, 40]]


def make():
    project = Project(1200, 900, "white")
    project.apply([
        {"type": "dataset", "name": "sales", "table": DATA},
        {"type": "chart", "name": "bars", "data": "sales", "width": 450, "height": 350},
        {"type": "chart", "name": "shares", "kind": "donut", "data": "sales",
         "derive": {"kind": "share", "by": "series"}, "x": 600, "width": 450, "height": 350},
        {"type": "table", "name": "table", "data": "sales", "y": 450, "width": 500},
        {"type": "text", "name": "total", "text": "Sold ${data.sales.total|number}: ${data.sales.max.label}",
         "size": 24, "x": 600, "y": 550},
    ])
    return project


def shown(project):
    return next(layer["text"] for layer in resolved_layers(project) if layer["name"] == "total")


def test_one_cell_updates_every_dependent_and_keeps_generated_ids():
    p = make()
    ids = {layer["name"]: layer["id"] for layer in p.state["layers"]}
    assert shown(p) == "Sold 100: Feb"
    p.apply({"type": "dataset", "name": "sales", "set": [{"category": "Jan", "series": "Tea", "value": 70}]})
    assert p.layer("bars")["chart"]["series"][0]["values"] == [70, 20]
    assert p.layer("shares")["chart"]["series"][0]["values"] == [90 / 160, 70 / 160]
    assert p.layer("table")["table"]["rows"][1] == ["Jan", 70, 30]
    assert shown(p) == "Sold 160: Jan"
    assert all(ids[layer["name"]] == layer["id"] for layer in p.state["layers"] if layer["name"] in ids)
    p.render()


def test_source_chart_follows_data_transitively_and_cycle_is_atomic():
    p = make()
    p.apply({"type": "dataset", "name": "fractions", "from": "shares"})
    p.apply({"type": "dataset", "name": "sales", "set": [{"category": "Jan", "series": "Tea", "value": 70}]})
    assert document_variables(p)["data.fractions.share.Tea"] == 90 / 160
    before = deepcopy(p.state)
    with pytest.raises(VixlError, match="cycle"):
        p.apply({"type": "dataset", "name": "sales", "from": "shares"})
    assert p.state == before
    with pytest.raises(VixlError):
        p.apply({"type": "dataset", "name": "fractions", "set": [{"category": "Tea", "value": 1}]})
    p.apply({"type": "dataset", "name": "fractions", "table": [["Part", "amount"], ["Tea", 1]]})
    assert "source" not in p.state["datasets"]["fractions"]


def test_csv_reload_is_explicit_portable_and_within_workspace(tmp_path):
    path = tmp_path / "sales.csv"
    path.write_text("Month,Tea,Coffee\nJan,10,30\nFeb,20,40\n")
    p = Project(600, 400, "white")
    p._workspace = tmp_path
    p.apply({"type": "dataset", "name": "sales", "csv": "sales.csv"})
    path.write_text("Month,Tea,Coffee\nJan,100,30\nFeb,20,40\n")
    assert document_variables(p)["data.sales.total"] == 100
    p.apply({"type": "dataset", "name": "sales", "action": "reload"})
    assert document_variables(p)["data.sales.total"] == 190
    p.save(tmp_path / "data.vixl")
    path.unlink()
    loaded = Project.load(tmp_path / "data.vixl")
    assert document_variables(loaded)["data.sales.total"] == 190
    before = deepcopy(p.state)
    with pytest.raises(VixlError, match="outside the workspace"):
        p.apply({"type": "dataset", "name": "sales", "csv": "../private.csv"})
    assert p.state == before


@pytest.mark.parametrize("kind,by,categories,values", [
    ("sum", "series", ["Tea", "Coffee"], [30, 70]),
    ("sum", "category", ["Jan", "Feb"], [40, 60]),
    ("max", "series", ["Tea", "Coffee"], [20, 40]),
    ("max", "category", ["Jan", "Feb"], [30, 40]),
    ("share", "category", ["Jan", "Feb"], [0.4, 0.6]),
])
def test_derivations(kind, by, categories, values):
    from vixl.plugins.charts.charts import table_from_rows

    names, series = derive_data(*table_from_rows(DATA), {"kind": kind, "by": by})
    assert names == categories and series == [{"name": kind, "values": values}]


def test_invalid_derived_data_leaves_source_and_dependents_unchanged():
    p = make()
    before = deepcopy(p.state)
    with pytest.raises(VixlError, match="non-negative"):
        p.apply({"type": "dataset", "name": "sales", "set": [{"category": "Jan", "series": "Tea", "value": -1}]})
    assert p.state == before
    for op in ({"type": "dataset", "name": "sales", "action": "remove"},
               {"type": "chart-data", "target": "bars", "set": [{"category": "Jan", "series": "Tea", "value": 5}]},
               {"type": "table-data", "target": "table", "set": [{"row": 1, "column": 2, "value": 5}]}):
        with pytest.raises(VixlError):
            p.apply(op)
        assert p.state == before


def test_inline_replacement_detaches_and_removal_is_allowed_after_detaching():
    p = make()
    p.apply([
        {"type": "chart", "target": "bars", "table": DATA},
        {"type": "chart", "target": "shares", "table": [["x", "y"], ["a", 1]]},
        {"type": "table", "target": "table", "table": DATA},
        {"type": "delete", "target": "total"},
        {"type": "dataset", "name": "sales", "action": "remove"},
    ])
    assert "datasets" not in p.state
    assert "data" not in p.layer("bars")["chart"]


def test_missing_key_is_a_fix_and_escaped_dotted_fields_stay_literal():
    p = make()
    p.layer("total")["text"] = "${data.sales.unknown}"
    report = p.check(checks=["placeholders"])
    finding = next(f for f in report["issues"] if f.get("code") == "undefined-variable")
    assert finding["action"] == "fix" and finding["variable"] == "data.sales.unknown"
    assert substitute("$${data.sales.total} / ${data.sales.total|number}", document_variables(p)) == "${data.sales.total} / 100"
    assert substitute("${data.sales.unknown|default:Pending}", document_variables(p)) == "Pending"


def test_slugs_are_stable_and_collisions_are_refused():
    p = Project(400, 300)
    p.apply({"type": "dataset", "name": "sales", "table": [["Month", "Cold brew"], ["First quarter", 20]]})
    assert document_variables(p)["data.sales.Cold-brew.First-quarter"] == 20
    with pytest.raises(VixlError, match="colliding"):
        p.apply({"type": "dataset", "name": "sales", "table": [["Month", "A B", "A-B"], ["Jan", 1, 2]]})


def test_cli_parity_and_saved_schema(tmp_path):
    import jsonschema
    import json
    import zipfile
    from vixl.document_schema import document_schema

    op = compile_command(["dataset", "sales", "--table", json.dumps(DATA)])
    p = Project(600, 400)
    p.apply(op)
    p.apply(compile_command(["chart", "donut", "--data", "sales", "--derive", '{"kind":"share","by":"series"}']))
    p.apply(compile_command(["table", "--data", "sales"]))
    p.save(tmp_path / "shared.vixl")
    with zipfile.ZipFile(tmp_path / "shared.vixl") as archive:
        jsonschema.validate(json.loads(archive.read("project.json")), document_schema())
    assert Project.load(tmp_path / "shared.vixl").state["datasets"] == p.state["datasets"]


def test_source_on_another_page_resolves_in_static_exports(tmp_path):
    import io
    from pypdf import PdfReader

    p = Project(600, 400, "white")
    p.apply([
        {"type": "chart", "name": "source", "table": DATA, "width": 500, "height": 300},
        {"type": "dataset", "name": "sales", "from": "source"},
        {"type": "page", "action": "add", "name": "summary"},
        {"type": "text", "name": "callout", "text": "Sales: ${data.sales.total}", "size": 30, "x": 50, "y": 50},
    ])
    from vixl.pages import page_project
    assert document_variables(page_project(p, 2))["data.sales.total"] == 100
    assert b"<svg" in p.export(format="SVG")
    pdf = PdfReader(io.BytesIO(p.export(format="PDF")))
    assert "Sales: 100" in pdf.pages[1].extract_text()


def test_invalid_saved_dataset_and_missing_cells_are_reported():
    from vixl.validation import check_state

    p = Project(400, 300)
    p.apply({"type": "dataset", "name": "sales", "table": [["Month", "Tea"], ["Jan", None]]})
    assert "data.sales.Tea.Jan" not in document_variables(p)
    p.state["datasets"]["sales"]["series"][0]["values"] = [True]
    with pytest.raises(VixlError, match="number or null"):
        check_state(p, p.state)


def test_dataset_edit_refreshes_inactive_pages_and_native_chart_exports(tmp_path):
    import io
    import zipfile
    from vixl.pages import page_project

    p = Project(600, 400, "white")
    p.apply([
        {"type": "dataset", "name": "sales", "table": DATA},
        {"type": "chart", "name": "bars", "data": "sales", "width": 500, "height": 300},
        {"type": "page", "action": "add", "name": "summary"},
        {"type": "text", "name": "callout", "text": "${data.sales.total}", "size": 30},
    ])
    active = p.state["page"]
    p.apply({"type": "dataset", "name": "sales", "set": [{"category": "Jan", "series": "Tea", "value": 70}]})
    assert p.state["page"] == active
    first = page_project(p, 1)
    assert first.layer("bars")["chart"]["series"][0]["values"] == [70, 20]
    with zipfile.ZipFile(io.BytesIO(p.export(format="PPTX"))) as archive:
        charts = [archive.read(name) for name in archive.namelist() if name.startswith("ppt/charts/") and name.endswith(".xml")]
    assert any(b">70<" in chart for chart in charts)
    p.save(tmp_path / "pages.vixl")
    assert page_project(Project.load(tmp_path / "pages.vixl"), 1).layer("bars")["chart"]["series"][0]["values"] == [70, 20]
    before = deepcopy(p.state)
    with pytest.raises(VixlError):
        p.apply([{"type": "delete", "target": "callout"}, {"type": "dataset", "name": "sales", "action": "remove"}])
    assert p.state == before
