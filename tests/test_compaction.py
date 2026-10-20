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


def test_the_unused_files_note_keeps_a_profile_verdict(tmp_path):
    p, _ = document(tmp_path / "doc.vixl")
    # Review findings only (a bar under the text): they fail the final profile but no plain check.
    p.apply([{"type": "move", "target": "t", "x": 60, "y": 60},
             {"type": "shape", "shape": "rectangle", "name": "bar", "x": 50, "y": 70, "width": 200,
              "height": 20, "fill": "#cccccc"},
             {"type": "reorder", "target": "bar", "below": "t"}])
    report = p.check(profile="final")
    assert any("unused_assets" in item for item in report["issues"])
    assert not any(item["action"] == "fix" for item in report["issues"])
    assert report["profile"]["failing"] and not report["passed"]
    assert report["outcome"]["validation"] == "failed"
    assert report["by_action"]["informational"]  # the note is still indexed


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


def register(p, name):
    data = renamed(name)
    asset = f"fonts/{hashlib.sha256(data).hexdigest()}.ttf"
    p.assets[asset] = data
    p.apply({"type": "font-register", "name": name, "asset": asset})
    return asset


def test_save_can_prune_fonts_no_revision_draws_and_keeps_undo(tmp_path):
    p, replaced = document(tmp_path / "doc.vixl")
    spare, used = p.state["fonts"]["spare-font"], p.state["fonts"]["used-font"]
    before_render, revisions = p.render().tobytes(), len(p.nodes)
    p.save()
    assert spare in zipfile.ZipFile(tmp_path / "doc.vixl").namelist()  # off by default
    assert p.prune_fonts(dry_run=True)["fonts_unregistered"] == ["spare-font"] and spare in p.assets
    p.save(prune_fonts=True)
    names = zipfile.ZipFile(tmp_path / "doc.vixl").namelist()
    assert spare not in names and used in names and replaced in names
    loaded = Project.load(tmp_path / "doc.vixl")
    assert "spare-font" not in loaded.state["fonts"] and len(loaded.nodes) == revisions
    assert loaded.render().tobytes() == before_render
    undone = 0
    for _ in range(revisions):  # every earlier revision still restores, without the spare registration
        try:
            loaded.undo()
        except VixlError:
            break
        undone += 1
        assert "spare-font" not in loaded.state.get("fonts", {})
        loaded.render()
    assert undone == revisions - 1
    loaded.redo(len(loaded.redo_stack))
    assert loaded.render().tobytes() == before_render


def test_prune_fonts_keeps_fonts_drawn_in_history_by_fallbacks_or_by_another_name(tmp_path):
    p, _ = document(tmp_path / "doc.vixl")
    spare = p.state["fonts"]["spare-font"]
    old = register(p, "old-font")
    p.apply({"type": "text-set", "target": "t", "font": "old-font"})
    p.apply({"type": "text-set", "target": "t", "font": "used-font"})
    fallback = register(p, "fallback-font")
    p.apply({"type": "font-fallbacks", "fonts": ["fallback-font"]})
    # A second name for the drawn file counts as drawn (layers store the file), so it stays too.
    p.apply({"type": "font-register", "name": "alias", "asset": p.state["fonts"]["used-font"]})
    report = p.prune_fonts()
    assert report["fonts_unregistered"] == ["spare-font"]
    assert [item["asset"] for item in report["assets_dropped"]] == [spare]
    assert {"old-font", "fallback-font", "used-font", "alias"} <= set(p.state["fonts"])
    assert old in p.assets and fallback in p.assets and p.state["fonts"]["used-font"] in p.assets
    p.undo(4)  # back to when old-font was drawn
    assert p.layer("t")["font"] == old
    p.save()
    assert "spare-font" not in Project.load(tmp_path / "doc.vixl").state["fonts"]


def test_prune_fonts_over_the_cli_and_refuses_open_transactions(tmp_path, monkeypatch):
    from vixl.cli import dispatch

    p, _ = document(tmp_path / "doc.vixl")
    p.begin()
    with pytest.raises(VixlError, match="transaction"):
        p.save(prune_fonts=True)
    monkeypatch.chdir(tmp_path)
    result, _ = dispatch(["-p", "doc.vixl", "save", "--prune-fonts"])
    assert result["pruned"]["fonts_unregistered"] == ["spare-font"] and result["pruned"]["bytes_dropped"] > 0
    assert "spare-font" not in Project.load(tmp_path / "doc.vixl").state["fonts"]
