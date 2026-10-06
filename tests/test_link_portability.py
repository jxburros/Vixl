"""Links in a copied or moved .vixl resolve beside the document first (#212)."""

import shutil

import pytest

from vixl import Project
from vixl.checks import check_design
from vixl.errors import VixlError
from vixl.interfaces import Session
from vixl import links
from vixl.workflows import dispatch


def tile(path, fill):
    path.parent.mkdir(parents=True, exist_ok=True)
    source = Project(100, 50, fill)
    source.save(path)


def host(path, workspace, size=(200, 100)):
    path.parent.mkdir(parents=True, exist_ok=True)
    project = Project(*size, "#ffffff")
    project._workspace = workspace
    project.save(path)
    return project


def test_sources_beside_the_document_are_stored_relative_to_it_and_survive_a_folder_copy(tmp_path):
    tile(tmp_path / "job" / "tile.vixl", "#ff0000")
    project = host(tmp_path / "job" / "card.vixl", tmp_path)
    project.apply({"type": "link", "source": "job/tile.vixl", "name": "t"})
    assert project.layer("t")["source"] == "tile.vixl"
    project.save()
    shutil.copytree(tmp_path / "job", tmp_path / "copy")
    tile(tmp_path / "copy" / "tile.vixl", "#0000ff")  # the copy's own source, not the original's
    copied = Project.load(tmp_path / "copy" / "card.vixl", workspace=tmp_path)
    assert copied.render().getpixel((10, 10))[:3] == (0, 0, 255)
    shutil.copytree(tmp_path / "job", tmp_path / "elsewhere" / "job")  # outside any workspace it still works
    moved = Project.load(tmp_path / "elsewhere" / "job" / "card.vixl")
    assert moved.render().getpixel((10, 10))[:3] == (255, 0, 0)


def test_workspace_relative_sources_of_older_documents_still_resolve(tmp_path):
    tile(tmp_path / "assets" / "tile.vixl", "#00ff00")
    project = host(tmp_path / "pages" / "card.vixl", tmp_path)
    project.apply({"type": "link", "source": "assets/tile.vixl", "name": "t"})
    assert project.layer("t")["source"] == "assets/tile.vixl"  # outside the document's folder: workspace-relative
    project.save()
    loaded = Project.load(tmp_path / "pages" / "card.vixl", workspace=tmp_path)
    assert loaded.render().getpixel((10, 10))[:3] == (0, 255, 0)
    [item] = links.status(loaded)
    assert item["state"] == "ok" and item["resolved_from"] == "workspace"
    assert item["path"] == str((tmp_path / "assets" / "tile.vixl").resolve())


def test_check_reports_sources_outside_the_document_folder(tmp_path):
    tile(tmp_path / "assets" / "tile.vixl", "#00ff00")
    tile(tmp_path / "pages" / "near.vixl", "#00ff00")
    project = host(tmp_path / "pages" / "card.vixl", tmp_path)
    project.apply([{"type": "link", "source": "assets/tile.vixl", "name": "far"},
                   {"type": "link", "source": "pages/near.vixl", "name": "near", "x": 100}])
    findings = [item for item in check_design(project, checks=["links"])["issues"] if item["check"] == "links"]
    assert [(item["severity"], item["layers"]) for item in findings] == [("info", ["far"])]
    assert findings[0]["path"].endswith("tile.vixl") and "links-relink" in findings[0]["message"]
    listing = {item["layer"]: item for item in project.inspect()["links"]}
    assert listing["near"]["resolved_from"] == "document" and listing["near"]["source"] == "near.vixl"


def test_links_relink_rewrites_a_prefix_on_every_page_and_records_revisions(tmp_path):
    for name in ("a", "b"):
        tile(tmp_path / "old" / f"{name}.vixl", "#123456")
    project = host(tmp_path / "card.vixl", tmp_path)
    project.apply([{"type": "page", "action": "add", "name": "one"}, {"type": "page", "action": "add", "name": "two"},
                   {"type": "link", "source": "old/a.vixl", "name": "a", "page": "one"},
                   {"type": "link", "source": "old/b.vixl", "name": "b", "page": "two"}])
    shutil.move(tmp_path / "old", tmp_path / "new")
    tile(tmp_path / "new" / "b.vixl", "#654321")  # a changed file: relinking records its revision
    assert {item["state"] for item in links.status(project)} == {"missing"}
    with pytest.raises(VixlError) as caught:
        project.apply({"type": "links-relink", "from": "ol", "to": "new"})  # whole segments only
    assert caught.value.code == "not_found" and "old/a.vixl" in caught.value.details["suggestions"]
    with pytest.raises(VixlError) as caught:
        project.apply({"type": "links-relink", "from": "old", "to": "nowhere"})
    assert caught.value.code == "link_missing"
    project.apply({"type": "links-relink", "from": "old/", "to": "new"})
    states = links.status(project)
    assert {item["source"] for item in states} == {"new/a.vixl", "new/b.vixl"}
    assert {item["state"] for item in states} == {"ok"}


def test_saving_into_another_folder_keeps_sources_pointing_at_the_same_files(tmp_path):
    tile(tmp_path / "job" / "tile.vixl", "#ff0000")
    project = host(tmp_path / "job" / "card.vixl", tmp_path)
    project.apply({"type": "link", "source": "job/tile.vixl", "name": "t"})
    project.save(tmp_path / "archive" / "card-v2.vixl")
    assert project.layer("t")["source"] == "job/tile.vixl"
    reopened = Project.load(tmp_path / "archive" / "card-v2.vixl", workspace=tmp_path)
    assert reopened.render().getpixel((10, 10))[:3] == (255, 0, 0)
    project.save(tmp_path / "job" / "card-v3.vixl")
    assert project.layer("t")["source"] == "tile.vixl"


def test_merge_sheet_documents_store_the_template_beside_them(tmp_path):
    folder = tmp_path / "badges"
    folder.mkdir()
    template = Project(300, 150, "#ffffff")
    template.apply([{"type": "canvas", "dpi": 300}, {"type": "variable", "name": "name", "value": "Sample"},
                    {"type": "text", "name": "n", "text": "${name}", "size": 30, "color": "black"}])
    template.save(folder / "badge.vixl")
    (folder / "rows.csv").write_text("name\nAda\nBo\n", encoding="utf-8")
    report = dispatch(Session(None, workspace=tmp_path), "merge-impose",
                      {"template": "badges/badge.vixl", "data": "badges/rows.csv", "output": "badges/sheet.vixl",
                       "sheet": {"size": "letter"}})
    assert report["errors"] == []
    sheet = Project.load(folder / "sheet.vixl", workspace=tmp_path)
    assert {item["source"] for item in links.status(sheet)} == {"badge.vixl"}
    shutil.copytree(folder, tmp_path / "elsewhere" / "badges")
    copied = Project.load(tmp_path / "elsewhere" / "badges" / "sheet.vixl")
    assert {item["state"] for item in links.status(copied)} == {"ok"}
