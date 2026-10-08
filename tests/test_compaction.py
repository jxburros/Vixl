"""Unused embedded files are reported, and dropped only by an explicit compact."""

import hashlib
import io
import zipfile
from pathlib import Path

import pytest
from PIL import Image

from vixl import Project
from vixl.compaction import unused_assets
from vixl.errors import VixlError
from vixl.interfaces import Session

FONT = Path(__file__).parents[1] / "src" / "vixl" / "data" / "DejaVuSans.ttf"


def png(color):
    buffer = io.BytesIO()
    Image.new("RGBA", (40, 40), color).save(buffer, "PNG")
    return buffer.getvalue()


def renamed(family):
    from fontTools.ttLib import TTFont

    font = TTFont(FONT)
    for record in font["name"].names:
        if record.nameID in (1, 16):
            record.string = family
    buffer = io.BytesIO()
    font.save(buffer)
    return buffer.getvalue()


def document(path):
    p = Project(400, 300, "white")
    for name in ("used-font", "spare-font"):
        data = renamed(name)
        asset = f"fonts/{hashlib.sha256(data).hexdigest()}.ttf"
        p.assets[asset] = data
        p.apply({"type": "font-register", "name": name, "asset": asset})
    p.apply({"type": "text", "name": "t", "text": "Hello", "font": "used-font", "size": 30, "color": "black"})
    from vixl.assets import add_encoded

    first, _ = add_encoded(p, png("red"))
    p.apply({"type": "add", "name": "photo", "asset": first})
    second, _ = add_encoded(p, png("blue"))
    p.apply({"type": "add", "name": "photo2", "asset": second})
    p.apply({"type": "delete", "target": "photo"})
    p.save(path)
    return p, first


def test_unused_files_are_reported_as_an_info_finding(tmp_path):
    p, replaced = document(tmp_path / "doc.vixl")
    found = unused_assets(p)
    kinds = {item["asset"]: item for item in found["assets"]}
    assert kinds[replaced]["reason"] == "history" and kinds[replaced]["kind"] == "image"
    assert found["fonts"] == ["spare-font"] and found["bytes"] == sum(item["bytes"] for item in found["assets"])
    report = p.check()
    notes = [item for item in report["issues"] if "unused_assets" in item]
    assert len(notes) == 1 and notes[0]["severity"] == "info" and notes[0]["action"] == "informational"
    assert "spare-font" in notes[0]["message"] and "compact" in notes[0]["message"]
    assert report["passed"] or report["errors"]  # info never fails a check
    assert not [item for item in p.check(checks=["contrast"])["issues"] if "unused_assets" in item]


def test_save_alone_keeps_history_and_its_files(tmp_path):
    p, replaced = document(tmp_path / "doc.vixl")
    p.save()
    assert replaced in zipfile.ZipFile(tmp_path / "doc.vixl").namelist()
    p.undo()
    assert any(layer["name"] == "photo" for layer in p.state["layers"])


def test_compact_is_explicit_reported_and_keeps_the_design(tmp_path):
    p, replaced = document(tmp_path / "doc.vixl")
    p.checkpoint("before")
    before_render = p.render().tobytes()
    size_before = (tmp_path / "doc.vixl").stat().st_size
    planned = p.compact(dry_run=True)
    assert planned["dry_run"] and replaced in {item["asset"] for item in planned["assets_dropped"]}
    assert len(p.nodes) > 1 and replaced in p.assets  # a dry run changes nothing
    report = p.compact()
    assert report["revisions_dropped"] >= 5 and report["checkpoints_dropped"] == ["before"]
    assert report["fonts_unregistered"] == ["spare-font"] and report["bytes_dropped"] > 0
    assert len(p.nodes) == 1 and not p.checkpoints and "spare-font" not in p.state["fonts"]
    assert p.render().tobytes() == before_render
    with pytest.raises(VixlError):
        p.undo()
    p.save()
    assert (tmp_path / "doc.vixl").stat().st_size < size_before
    assert replaced not in zipfile.ZipFile(tmp_path / "doc.vixl").namelist()
    assert not unused_assets(Project.load(tmp_path / "doc.vixl"))["assets"]


def test_compact_can_keep_fonts_and_refuses_open_transactions(tmp_path):
    p, _ = document(tmp_path / "doc.vixl")
    assert p.compact(fonts=False)["fonts_unregistered"] == []
    assert "spare-font" in p.state["fonts"]
    p.save()
    assert "spare-font" in Project.load(tmp_path / "doc.vixl").state["fonts"]
    p.begin()
    with pytest.raises(VixlError, match="transaction"):
        p.compact()


def test_history_compact_over_mcp_and_cli(tmp_path, monkeypatch):
    document(tmp_path / "doc.vixl")
    session = Session(workspace=tmp_path)
    session.open("doc.vixl")
    dry = session.history("compact", dry_run=True)
    assert dry["compact"]["dry_run"] and len(dry["nodes"]) > 1
    done = session.history("compact")
    assert len(done["nodes"]) == 1 and done["compact"]["bytes_dropped"] > 0
    from vixl.cli import dispatch

    document(tmp_path / "other.vixl")
    monkeypatch.chdir(tmp_path)
    result, _ = dispatch(["-p", "other.vixl", "compact", "--keep-fonts"])
    assert result["fonts_unregistered"] == [] and len(Project.load(tmp_path / "other.vixl").nodes) == 1
