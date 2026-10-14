"""The house-style off switch: ``house_style: "off"`` on every creation surface and in ``.vixl/variety.json``
gives a document with no rolled direction, and layout-apply then uses neutral defaults."""

import asyncio
import base64
import json

import pytest

from vixl import Project, VixlError, creation, house_style
from vixl.compose import compose
from vixl.interfaces import Session, mcp_server
from vixl.typefaces import roll_document

LAYOUT = {"name": "hero-statement", "title": "Launch day", "subtitle": "Doors open at nine", "unfilled": "omit"}
ROLLED = ("pairing", "layout", "layout_seed", "style", "container", "tier", "margin")


def mcp(server, name, arguments):
    result = asyncio.run(server.call_tool(name, arguments))
    content = result[0] if isinstance(result, tuple) else result
    return json.loads("".join(getattr(item, "text", "") for item in content))


def cli(*argv):
    from vixl.cli import dispatch

    result, _ = dispatch(["--json", *argv])
    return result


def assert_neutral(defaults):
    assert defaults["house_style"] == "off"
    assert defaults["direction"] == house_style.neutral()["direction"]
    assert not set(ROLLED) & set(defaults["direction"])
    direction = defaults["direction"]
    assert (direction["palette"], direction["mode"], direction["look"], direction["motif"], direction["accent"],
            direction["background_treatment"], direction["corner"]) == ("mono", "light", "none", "none", "none",
                                                                        "flat", "sharp")


def test_every_surface_makes_the_same_neutral_document(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    by_cli = cli("new", "1080x1350", "--seed", "7", "--house-style", "off", "-o", "cli.vixl")
    report = {}
    by_new = Project.new(width=1080, height=1350, seed=7, house_style="off", report=report)
    by_python = Project(1080, 1350, seed=7, house_style="off")
    by_mcp = mcp(mcp_server(workspace=tmp_path), "vixl_document",
                 {"action": "create", "path": "mcp.vixl", "width": 1080, "height": 1350, "seed": 7,
                  "house_style": "off", "verbose": True})
    by_session = Session(None, workspace=tmp_path).create("s.vixl", 1080, 1350, seed=7, house_style="off")
    defaults = by_cli["design_defaults"]
    assert_neutral(defaults)
    assert defaults == by_new.state["design_defaults"] == by_python.state["design_defaults"] \
        == by_mcp["design_defaults"] == by_session["design_defaults"]
    assert by_cli["creation"] == report["creation"] == by_mcp["creation"] == by_session["creation"]
    terse = mcp(mcp_server(workspace=tmp_path), "vixl_document",
                {"action": "create", "path": "terse.vixl", "house_style": "off"})
    assert terse["creation"]["house_style"] == "off" and terse["canvas"]["background"] == "#ffffff"
    created = report["creation"]
    assert created["house_style"] == "off" and created["background"] == "#ffffff"
    assert created["background_from"] == "neutral" and created["fonts"]["installed"] is False
    assert "typography" not in by_new.state and not by_new.state.get("fonts")
    # Craft still applies: the canvas safe area is there.
    assert by_new.state["canvas"]["safe"] == Project(1080, 1350, seed=7).state["canvas"]["safe"]
    sized = Project.sized("instagram-portrait", seed=7, house_style="off")
    assert_neutral(sized.state["design_defaults"])
    assert sized.state["design_defaults"]["purpose"] == "social"
    assert sized.state["canvas"]["background"] == "#ffffff"
    # Marks stay transparent; an explicit background still wins.
    assert Project.sized("favicon", house_style="off").state["canvas"]["background"] == "transparent"
    assert Project(purpose="logo", house_style="off").state["canvas"]["background"] == "transparent"
    assert Project(house_style="off", background="#102030").state["canvas"]["background"] == "#102030"


def test_compose_on_every_surface_follows_the_neutral_direction(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    python = Project(1080, 1080, seed=9, house_style="off")
    python.apply({"type": "layout-apply", **LAYOUT})
    record = python.state["layout"]
    assert (record["palette"], record["mode"], record["type_scale"], record["density"], record["accent"]) == (
        "mono", "light", "perfect-fourth", "balanced", "none")
    assert record["rolled"] == ["align"] and record["direction"]["look"] == "none"
    assert {layer["name"] for layer in python.state["layers"]} == {"background", "headline", "subtitle"}

    request = {"width": 1080, "height": 1080, "seed": 9, "house_style": "off", "layout": LAYOUT, "check": False}
    create = {key: value for key, value in request.items() if key != "check"}
    mcp(mcp_server(workspace=tmp_path), "vixl_apply", {"create": {"path": "m.vixl", **create}, "check": False})
    session = Session(None, workspace=tmp_path)
    compose(session, path="c.vixl", **request)
    (tmp_path / "req.json").write_text(json.dumps({"path": "cli.vixl", **request}))
    cli("compose", "--request", "req.json", "--workspace", str(tmp_path))
    for name in ("m.vixl", "c.vixl", "cli.vixl"):
        made = Project.load(tmp_path / name)
        assert made.state["design_defaults"] == python.state["design_defaults"]
        assert {k: v for k, v in made.state["layout"].items() if k != "layers"} == \
            {k: v for k, v in record.items() if k != "layers"}
        assert made.render().tobytes() == python.render().tobytes()
        assert made.state["canvas"]["background"] == "#ffffff"

    from fastapi.testclient import TestClient
    from vixl.interfaces import create_app

    dry, image = compose(Session(None, workspace=tmp_path), dry_run=True, preview=True,
                         **{k: v for k, v in request.items() if k != "check"})
    with TestClient(create_app(str(tmp_path / "m.vixl"))) as client:
        response = client.post("/compose", json={**request, "preview": True})
    assert response.status_code == 200, response.text
    rest = response.json()
    assert rest["creation"] == dry["creation"] and rest["creation"]["house_style"] == "off"
    assert base64.b64decode(rest["preview_base64"]) == image


def test_workspace_setting_turns_the_house_style_off_everywhere(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".vixl").mkdir()
    (tmp_path / ".vixl" / "variety.json").write_text(json.dumps({"house_style": "off"}))
    made = cli("new", "--seed", "3", "-o", "w.vixl")
    assert_neutral(made["design_defaults"])
    assert made["creation"]["house_style"] == "off"
    assert_neutral(mcp(mcp_server(workspace=tmp_path), "vixl_document",
                       {"action": "create", "path": "m.vixl", "seed": 3, "verbose": True})["design_defaults"])
    assert_neutral(Project.new(seed=3, workspace=tmp_path).state["design_defaults"])
    result, _ = compose(Session(None, workspace=tmp_path), dry_run=True, seed=3, check=False)
    assert result["creation"]["house_style"] == "off"
    # An explicit "on" overrides the workspace and rolls the current house style.
    on = Project.new(seed=3, workspace=tmp_path, house_style="on").state["design_defaults"]
    assert "house_style" not in on and on["direction"].get("pairing")
    # Nothing was rolled for the neutral documents, so only the explicit "on" one joined the roll history.
    assert len(json.loads((tmp_path / ".vixl" / "rolls.json").read_text())) == 0 \
        if (tmp_path / ".vixl" / "rolls.json").exists() else True
    # An explicit roll still works and rolls the current version.
    document = Project.load(tmp_path / "w.vixl")
    rolled = roll_document(document, seed=11, apply=True, slots={"title": "Rolled anyway"})
    assert rolled["direction"].get("pairing") and rolled["direction"].get("layout")
    assert document.state["layout"]["palette"] == rolled["direction"]["palette"]


def test_explicit_fields_win_over_the_neutral_direction(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    p = Project(1080, 1080, seed=4, house_style="off")
    p.apply({"type": "layout-apply", **LAYOUT, "palette": "sunset", "mode": "dark", "accent": "rule",
             "direction": {"corner": "pill", "look": "grain", "look_amount": 0.2}})
    record = p.state["layout"]
    assert (record["palette"], record["mode"], record["accent"]) == ("sunset", "dark", "rule")
    assert record["direction"]["corner"] == "pill" and record["direction"]["look"] == "grain"
    # A fresh seed asks for a fresh choice instead of the stored direction.
    fresh = Project(1080, 1080, seed=4, house_style="off")
    fresh.apply({"type": "layout-apply", **LAYOUT, "seed": 77})
    assert "direction" not in fresh.state["layout"] or fresh.state["layout"]["direction"] == {}


def test_default_stays_on_and_bad_values_are_refused(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    report = {}
    p = Project.new(seed=5, report=report)
    defaults = p.state["design_defaults"]
    assert "house_style" not in defaults and defaults["direction"].get("pairing")
    assert "house_style" not in report["creation"] and report["creation"]["background_from"] == "palette"
    assert Project.new(seed=5, house_style="on").state["design_defaults"] == defaults
    with pytest.raises(VixlError, match="house_style"):
        Project.new(house_style="maybe")
    with pytest.raises(VixlError, match="house_style"):
        Session(None, workspace=tmp_path).create("bad/x.vixl", house_style="no")
    assert not (tmp_path / "bad").exists()
    (tmp_path / ".vixl").mkdir()
    (tmp_path / ".vixl" / "variety.json").write_text(json.dumps({"house_style": "none"}))
    with pytest.raises(VixlError, match="'off'"):
        Project.new(workspace=tmp_path)


def test_house_style_off_keeps_the_workspace_brand_fonts_and_background(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from vixl import typefaces

    font = base64.b64encode((typefaces.DATA / "DejaVuSans.ttf").read_bytes()).decode()
    (tmp_path / "brand.json").write_text(json.dumps({
        "palette": {"background": "#fdf6e3", "ink": "#073642", "accent": "#b58900"},
        "fonts": {role: {"name": "House", "data_base64": font} for role in ("heading", "body")}}))
    report = {}
    p = Project.new(seed=2, workspace=tmp_path, house_style="off", report=report)
    assert p.state["canvas"]["background"] == "#fdf6e3"
    assert report["creation"]["fonts"] == {"installed": False, "reason": "the workspace fonts apply"}
    assert report["workspace_fonts"] and p.state["typography"]["body"]
