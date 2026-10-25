"""The workspace dependency graph (step 7 foundation F3): links, brand.json, groups, merge data and suites."""

import json
import os

from vixl import Project
from vixl.interfaces import Session
from vixl.workflows import dispatch
from vixl.plugins.workspace_qa import dependents
from vixl.plugins.workspace_qa.dependents import INDEX


def plain(path, color="#336699"):
    p = Project(80, 40, "white")
    p.apply({"type": "shape", "shape": "rectangle", "name": "r", "x": 0, "y": 0, "width": 80, "height": 40,
             "fill": color})
    path.parent.mkdir(parents=True, exist_ok=True)
    p.save(path, overwrite=True)
    return p


def linking(path, *sources, workspace):
    p = Project(300, 200, "white", workspace=workspace)
    p.path = str(path)
    for index, source in enumerate(sources):
        p.apply({"type": "link", "source": source, "name": f"l{index}", "x": 10 * index, "y": 0})
    path.parent.mkdir(parents=True, exist_ok=True)
    p.save(path, overwrite=True)
    return p


def test_reverse_index_covers_links_brand_groups_merge_data_and_suites(tmp_path):
    plain(tmp_path / "logo.vixl")
    linking(tmp_path / "cards/one.vixl", "logo.vixl", workspace=tmp_path)
    linking(tmp_path / "cards/two.vixl", "../logo.vixl", workspace=tmp_path)
    sheet = plain(tmp_path / "sheet.vixl")
    sheet.state["merge"] = {"version": 1, "template": "cards/one.vixl", "data": "rows.csv", "sheet": {}}
    sheet.apply({"type": "suite-set", "name": "local", "suite": {"extends": "delivery", "rules": []}})
    sheet.save(tmp_path / "sheet.vixl", overwrite=True)
    (tmp_path / "rows.csv").write_text("title\nA\n")
    (tmp_path / "brand.json").write_text(json.dumps({"name": "Acme", "suites": ["delivery"]}))
    session = Session(None, workspace=tmp_path)
    dispatch(session, "group-define", {"name": "cards", "documents": ["cards/one.vixl", "cards/two.vixl"]})

    built = dependents.graph(session)
    reverse = built["reverse"]
    assert {(i["document"], i["kind"]) for i in reverse["logo.vixl"]} == {("cards/one.vixl", "link"),
                                                                          ("cards/two.vixl", "link")}
    assert {i["document"] for i in reverse["brand.json"]} == {"logo.vixl", "cards/one.vixl", "cards/two.vixl",
                                                               "sheet.vixl"}
    assert {i["document"] for i in reverse[".vixl-groups/cards.json"]} == {"cards/one.vixl", "cards/two.vixl"}
    assert reverse["rows.csv"] == [{"document": "sheet.vixl", "kind": "data"}]
    assert reverse["cards/one.vixl"] == [{"document": "sheet.vixl", "kind": "template"}]
    assert {i["document"] for i in reverse["suite:delivery"]} >= {"sheet.vixl", "logo.vixl"}
    assert built["groups"]["cards"]["documents"] == ["cards/one.vixl", "cards/two.vixl"]
    # The public helpers.
    assert [d["document"] for d in dependents.dependents(session, "rows.csv")] == ["sheet.vixl"]
    found = dependents.dependents(session, "logo.vixl", kinds=["link"])
    assert [(d["document"], d["depth"]) for d in found] == [("cards/one.vixl", 1), ("cards/two.vixl", 1),
                                                            ("sheet.vixl", 2)]
    assert dependents.dependents(session, "logo.vixl", kinds=["link"], nested=False)[-1]["document"] == "cards/two.vixl"
    assert dependents.tree(session, "logo.vixl")["dependents"][0]["document"] == "cards/one.vixl"


def test_the_index_is_cached_by_mtime_and_skips_workspace_folders(tmp_path):
    plain(tmp_path / "a.vixl")
    linking(tmp_path / "b.vixl", "a.vixl", workspace=tmp_path)
    plain(tmp_path / ".vixl-checks/work/base/b.vixl")
    first = dependents.graph(tmp_path)
    assert set(first["documents"]) == {"a.vixl", "b.vixl"}
    index = json.loads((tmp_path / INDEX).read_text())
    assert set(index["documents"]) == {"a.vixl", "b.vixl"}
    # A cached entry is reused while the file's size and mtime hold, and re-read when they change.
    index["documents"]["b.vixl"]["edges"] = [["link", "cached.vixl"]]
    (tmp_path / INDEX).write_text(json.dumps(index))
    assert "cached.vixl" in dependents.graph(tmp_path)["reverse"]
    stat = (tmp_path / "b.vixl").stat()
    os.utime(tmp_path / "b.vixl", ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000))
    assert "cached.vixl" not in dependents.graph(tmp_path)["reverse"]
    (tmp_path / "b.vixl").unlink()
    dependents.graph(tmp_path)
    assert set(json.loads((tmp_path / INDEX).read_text())["documents"]) == {"a.vixl"}


def test_unreadable_documents_and_registered_readers(tmp_path):
    plain(tmp_path / "a.vixl")
    (tmp_path / "broken.vixl").write_bytes(b"not a zip")

    def reader(state, path, workspace):
        return [("data", "feed.json")] if state["canvas"]["width"] == 80 else []

    dependents.register(reader)
    try:
        built = dependents.graph(tmp_path)
        assert "error" in built["documents"]["broken.vixl"]
        assert built["reverse"]["feed.json"] == [{"document": "a.vixl", "kind": "data"}]
    finally:
        dependents._READERS.remove(reader)
    assert "feed.json" not in dependents.graph(tmp_path)["reverse"]  # the reader set is part of the cache key
