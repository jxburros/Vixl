"""Sync from a data source (#572): a CSV bound to a group, a campaign spec or a merge sheet; row diff against the last
snapshot and affected-only apply, check and re-export."""

import json

import pytest

from vixl import Project
from vixl.errors import VixlError
from vixl.interfaces import Session
from vixl.workflows import dispatch

ROWS = [("A1", "$10", "Lamp"), ("A2", "$20", "Desk"), ("A3", "$30", "Chair")]


def member(path, sku):
    p = Project(160, 100, "#ffffff")
    p.apply([{"type": "variable", "name": "sku", "value": sku}, {"type": "variable", "name": "price", "value": "$0"},
             {"type": "text", "name": "price", "text": "Now ${price}", "size": 20, "x": 10, "y": 10,
              "color": "#000000"}])
    p.save(path)


def write_csv(path, rows):
    path.write_text("sku,price,name\n" + "".join(f"{sku},{price},{name}\n" for sku, price, name in rows))


@pytest.fixture
def group(tmp_path):
    for index, (sku, _, _) in enumerate(ROWS, 1):
        member(tmp_path / f"p{index}.vixl", sku)
    write_csv(tmp_path / "prices.csv", ROWS)
    session = Session(None, workspace=tmp_path)
    dispatch(session, "group-define", {"name": "shelf", "documents": ["p1.vixl", "p2.vixl", "p3.vixl"]})
    return session


def sync(session, **extra):
    return dispatch(session, "data-sync", {"bind": {"data": "prices.csv", "key": "sku", "to": {"group": "shelf"}},
                                           "exports": [{"path": "out/{doc}.png"}], **extra})


def by_doc(result):
    return {entry["document"]: entry for entry in result["documents"]}


def test_changing_one_row_updates_and_re_exports_only_the_member_that_uses_it(group):
    first = sync(group)
    assert first["first_sync"] and sorted(first["rows"]["added"]) == ["A1", "A2", "A3"]
    assert {doc: e["status"] for doc, e in by_doc(first).items()} == {"p1.vixl": "updated", "p2.vixl": "updated",
                                                                      "p3.vixl": "updated"}
    assert Project.load(group.resolve("p2.vixl")).state["variables"]["price"] == "$20"
    stamps = {name: group.resolve(f"out/{name}.png").stat().st_mtime_ns for name in ("p1", "p2", "p3")}
    write_csv(group.resolve("prices.csv"), [ROWS[0], ("A2", "$25", "Desk"), ("A3", "$30", "Armchair")])
    second = sync(group)
    assert second["rows"]["changed"] == {"A2": ["price"], "A3": ["name"]} and second["rows"]["unchanged"] == 1
    statuses = {doc: e["status"] for doc, e in by_doc(second).items()}
    # A3 changed only a column its member does not use.
    assert statuses == {"p1.vixl": "unchanged", "p2.vixl": "updated", "p3.vixl": "unaffected"}
    assert second["published"] == ["p2.vixl"]
    assert Project.load(group.resolve("p2.vixl")).state["variables"]["price"] == "$25"
    after = {name: group.resolve(f"out/{name}.png").stat().st_mtime_ns for name in ("p1", "p2", "p3")}
    assert after["p1"] == stamps["p1"] and after["p3"] == stamps["p3"] and after["p2"] != stamps["p2"]
    snapshot = json.loads(group.resolve(".vixl-runs/data/prices.json").read_text())
    assert snapshot["rows"]["A2"]["price"] == "$25" and snapshot["outputs"]["p2.vixl"][0]["path"] == "out/p2.png"


def test_added_and_removed_rows_are_reported(group):
    sync(group)
    write_csv(group.resolve("prices.csv"), [ROWS[1], ROWS[2], ("A4", "$40", "Shelf")])
    result = sync(group)
    assert result["rows"]["added"] == ["A4"] and result["rows"]["removed"] == ["A1"]
    entries = by_doc(result)
    assert entries["p1.vixl"]["status"] == "removed" and "removed" in entries["p1.vixl"]["reason"]
    assert Project.load(group.resolve("p1.vixl")).state["variables"]["price"] == "$10"  # left as it was


def test_the_dry_run_writes_nothing(group):
    before = {p.name: p.read_bytes() for p in group.workspace.glob("*.vixl")}
    result = sync(group, dry_run=True)
    assert result["dry_run"] and result["written"] is False
    assert sorted(result["planned_exports"]) == ["p1.vixl", "p2.vixl", "p3.vixl"]
    assert {p.name: p.read_bytes() for p in group.workspace.glob("*.vixl")} == before
    assert not group.resolve(".vixl-runs").exists() and not group.resolve("out").exists()


def test_a_member_whose_new_values_fail_its_checks_is_held_and_retried(group):
    p = Project.load(group.resolve("p2.vixl"))
    p.apply({"type": "suite-set", "name": "short", "suite": {"version": 1, "rules": [
        {"id": "short-price", "kind": "text", "target": "price", "max_characters": 8}]}})
    p.save()
    write_csv(group.resolve("prices.csv"), [ROWS[0], ("A2", "$2000000", "Desk"), ROWS[2]])
    result = sync(group)
    entries = by_doc(result)
    assert entries["p2.vixl"]["status"] == "held" and entries["p1.vixl"]["status"] == "updated"
    assert Project.load(group.resolve("p2.vixl")).state["variables"]["price"] == "$0"
    assert not group.resolve("out/p2.png").exists()
    assert "A2" not in json.loads(group.resolve(".vixl-runs/data/prices.json").read_text())["rows"]
    assert by_doc(sync(group))["p2.vixl"]["status"] == "held"  # tried again on the next sync


def test_a_campaign_spec_re_renders_exactly_the_variants_whose_row_changed(tmp_path):
    from vixl.production import capture_recipe

    p = Project(160, 100, "#102030")
    p.apply({"type": "text", "name": "title", "text": "Hello", "size": 20, "x": 10, "y": 10, "color": "#ffffff"})
    p = capture_recipe(p, {"version": 1, "inputs": {"title": {"type": "string", "default": "Hello", "maxLength": 60}}},
                       {"title": {"target": "title", "field": "text"}})
    p.save(tmp_path / "banner.vixl")
    (tmp_path / "campaign.json").write_text(json.dumps({"source": "banner.vixl", "output": "out", "spec": {}}))
    (tmp_path / "titles.csv").write_text("sku,title\nA1,One\nA2,Two\nA3,Three\n")
    session = Session(None, workspace=tmp_path)
    request = {"bind": {"data": "titles.csv", "key": "sku", "to": {"spec": "campaign.json"}}}
    first = dispatch(session, "data-sync", request)
    assert first["variants"]["rendered"] == ["0001", "0002", "0003"]
    report = json.loads((tmp_path / "out" / "production.json").read_text())
    files = {r["id"]: tmp_path / "out" / r["output"] for r in report["results"]}
    stamps = {ident: path.stat().st_mtime_ns for ident, path in files.items()}
    (tmp_path / "titles.csv").write_text("sku,title\nA1,One\nA2,Deux\nA3,Three\n")
    plan = dispatch(session, "data-sync", {**request, "dry_run": True})
    assert plan["variants"]["affected"] == ["0002"] and plan["written"] is False
    second = dispatch(session, "data-sync", request)
    assert second["variants"]["rendered"] == ["0002"] and second["variants"]["reused"] == ["0001", "0003"]
    assert all(files[i].stat().st_mtime_ns == stamps[i] for i in ("0001", "0003"))


def test_a_merge_sheet_runs_again_only_when_its_rows_changed(tmp_path):
    p = Project(300, 200, "#ffffff")
    p.apply([{"type": "variable", "name": "name", "value": "Sample"},
             {"type": "text", "name": "name", "text": "${name}", "size": 20, "x": 10, "y": 10, "color": "#000000"}])
    p.save(tmp_path / "badge.vixl")
    (tmp_path / "people.csv").write_text("id,name\n1,Ada\n2,Grace\n")
    session = Session(None, workspace=tmp_path)
    dispatch(session, "merge-impose", {"template": "badge.vixl", "data": "people.csv", "output": "badges.pdf",
                                       "sheet_document": "badges.vixl", "unknown": "ignore"})
    request = {"bind": {"data": "people.csv", "key": "id", "to": {"merge": "badges.vixl"}}}
    assert dispatch(session, "data-sync", request)["rerun"]  # the first sync makes the snapshot
    assert dispatch(session, "data-sync", request)["status"] == "reused"
    (tmp_path / "people.csv").write_text("id,name\n1,Ada\n2,Hopper\n")
    changed = dispatch(session, "data-sync", request)
    assert changed["rows"]["changed"] == {"2": ["name"]} and changed["status"] == "updated"


def test_a_binding_keeps_its_target(group):
    sync(group)
    with pytest.raises(VixlError, match="another target"):
        dispatch(group, "data-sync", {"bind": {"data": "prices.csv", "key": "sku", "to": {"merge": "x.vixl"}}})


def test_members_that_would_write_the_same_export_are_refused(group):
    member(group.resolve("p4.vixl"), "A1")  # a second member bound to row A1
    dispatch(group, "group-define", {"name": "shelf", "documents": ["p1.vixl", "p2.vixl", "p3.vixl", "p4.vixl"]})
    request = {"bind": {"data": "prices.csv", "key": "sku", "to": {"group": "shelf"}},
               "exports": [{"path": "out/{key}.png"}]}
    plan = dispatch(group, "data-sync", {**request, "dry_run": True})
    assert plan["collisions"] == {"out/A1.png": ["p1.vixl", "p4.vixl"]}
    with pytest.raises(VixlError, match="same export file"):
        dispatch(group, "data-sync", request)
    assert not group.resolve("out").exists()


def test_a_binding_is_a_data_edge_of_the_dependency_graph(group):
    from vixl.plugins.workspace_qa import dependents

    assert dependents.dependents(group, "prices.csv") == []
    sync(group)
    assert [d["document"] for d in dependents.dependents(group, "prices.csv")] == ["p1.vixl", "p2.vixl", "p3.vixl"]
    dispatch(group, "group-define", {"name": "shelf", "documents": ["p1.vixl"]})  # the edge follows the group
    assert [d["document"] for d in dependents.dependents(group, "prices.csv", kinds=["data"])] == ["p1.vixl"]
