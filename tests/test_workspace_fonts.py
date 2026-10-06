"""Workspace default fonts: brand.json pairing/fonts embedded at document creation."""

import base64
import json
from pathlib import Path

import pytest

from vixl import Project
from vixl.errors import VixlError
from vixl.interfaces import Session

FONT = Path(__file__).parents[1] / "src/vixl/data/DejaVuSans.ttf"


def mcp(workspace):
    import asyncio

    from vixl.mcp_tools import build_server

    server = build_server(Session(workspace=workspace))

    def call(name, **arguments):
        result = asyncio.run(server.call_tool(name, arguments))
        content = result[0] if isinstance(result, tuple) else result
        return json.loads(content[0].text)

    return call


@pytest.fixture
def offline_fonts(monkeypatch):
    from vixl import typefaces

    fetched = []

    def fetch(family, weight=400, italic=False, *, client=None, source=None):
        fetched.append((family, weight))
        if source is not None:
            source.update(origin="cache")
        return FONT.read_bytes(), family

    monkeypatch.setattr(typefaces, "fetch_font", fetch)
    return fetched


def test_create_embeds_workspace_pairing_and_reports_it(tmp_path, offline_fonts):
    (tmp_path / "brand.json").write_text(json.dumps({"pairing": "source-serif-sans"}))
    session = Session(workspace=tmp_path)
    created = session.create("a.vixl", 400, 300)
    report = created["workspace_fonts"]
    assert report["source"] == "brand.json" and report["pairing"] == "source-serif-sans"
    assert set(report["applied"]) == {"heading", "body"}
    with session.project() as p:
        typography = p.state["typography"]
        assert typography["heading"] == report["applied"]["heading"]["name"]
        assert p.state["fonts"][typography["body"]] in p.assets  # embedded: the file stays portable
        assert len(p.nodes) == 1  # part of creation, not an undoable step
    loaded = Project.load(tmp_path / "a.vixl")
    assert loaded.state["fonts"][loaded.state["typography"]["heading"]] in loaded.assets


def test_explicit_pairing_or_opt_out_skips_workspace_fonts(tmp_path, offline_fonts):
    (tmp_path / "brand.json").write_text(json.dumps({"pairing": "source-serif-sans"}))
    session = Session(workspace=tmp_path)
    created = session.create("b.vixl", 400, 300, workspace_fonts=False)
    assert "workspace_fonts" not in created
    with session.project() as p:
        assert not p.state.get("fonts")
    assert not offline_fonts


def test_mcp_create_with_font_pairing_ignores_workspace_default(tmp_path, offline_fonts):
    (tmp_path / "brand.json").write_text(json.dumps({"pairing": "source-serif-sans"}))
    call = mcp(tmp_path)
    created = call("vixl_document_create", path="c.vixl", width=300, height=300, font_pairing="inter-single-ui")
    assert "workspace_fonts" not in created and created["typography"]["pairing"] == "inter-single-ui"


def test_offline_workspace_pairing_still_creates_the_document(tmp_path, monkeypatch):
    from vixl import typefaces

    def fail(*args, **kwargs):
        raise VixlError("font_download_failed", "Offline")

    monkeypatch.setattr(typefaces, "fetch_font", fail)
    (tmp_path / "brand.json").write_text(json.dumps({"pairing": "source-serif-sans"}))
    created = Session(workspace=tmp_path).create("d.vixl", 300, 300)
    assert "Offline" in created["workspace_fonts"]["error"]
    assert (tmp_path / "d.vixl").exists()


def test_font_tools_write_workspace_defaults(tmp_path, offline_fonts):
    call = mcp(tmp_path)
    paired = call("vixl_font_pair", pairing="source-serif-sans", scope="workspace")
    assert paired["workspace"]["path"] == "brand.json"
    assert json.loads((tmp_path / "brand.json").read_text())["pairing"] == "source-serif-sans"
    with pytest.raises(Exception, match="role"):
        call("vixl_font_install", family="Inter", scope="workspace")
    installed = call("vixl_font_install", family="Inter", weight=700, role="heading", scope="workspace")
    assert installed["workspace"]["role"] == "heading"
    kit = json.loads((tmp_path / "brand.json").read_text())
    assert kit["pairing"] == "source-serif-sans" and kit["fonts"]["heading"]["name"] == "inter-700"
    created = call("vixl_document_create", path="e.vixl", width=300, height=300)
    applied = created["workspace_fonts"]["applied"]
    assert applied["heading"] == {"name": "inter-700", "from": "fonts"}
    assert applied["body"]["from"] == "pairing"
    # A later pairing replaces the embedded role fonts and says so.
    again = call("vixl_font_pair", pairing="inter-single-ui", scope="workspace")
    assert again["workspace"]["replaced"] == ["fonts.heading"]
    assert "fonts" not in json.loads((tmp_path / "brand.json").read_text())


def test_cli_new_and_workspace_scope(tmp_path, monkeypatch, offline_fonts):
    from vixl.cli import dispatch

    monkeypatch.chdir(tmp_path)
    result, _ = dispatch(["font", "pair", "source-serif-sans", "--scope", "workspace"])
    assert result["workspace"]["pairing"] == "source-serif-sans"
    created, _ = dispatch(["new", "300x200", "-o", "x.vixl"])
    assert created["workspace_fonts"]["pairing"] == "source-serif-sans"
    bare, _ = dispatch(["new", "300x200", "-o", "y.vixl", "--no-workspace-fonts"])
    assert "workspace_fonts" not in bare
    assert not Project.load(tmp_path / "y.vixl").state.get("fonts")


def test_embedded_brand_font_overrides_one_pairing_role(tmp_path, offline_fonts):
    data = base64.b64encode(FONT.read_bytes()).decode()
    (tmp_path / "brand.json").write_text(json.dumps({"pairing": "source-serif-sans",
                                                     "fonts": {"body": {"name": "brand-body", "data_base64": data}}}))
    p = Project(600, 600, workspace=tmp_path)
    p.apply({"type": "layout-apply", "name": "hero-statement", "title": "Hi", "unfilled": "omit"})
    assert p.state["typography"]["body"] == "brand-body"
    assert p.state["typography"]["heading"] != "brand-body" and offline_fonts
