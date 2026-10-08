"""One creation path: design defaults, purpose sizes, palette backgrounds and fonts at creation (#394, #411, #413,
#418), and rolled directions that show when applied (#389, #390, #392)."""

import asyncio
import json
from pathlib import Path

import httpx
import pytest

from vixl import Project, VixlError
from vixl import creation, typefaces
from vixl.interfaces import Session, mcp_server
from vixl.sizes import paper_size, purpose_size
from vixl.typefaces import get_pairing, roll, slug


def mcp(server, name, arguments):
    result = asyncio.run(server.call_tool(name, arguments))
    content = result[0] if isinstance(result, tuple) else result
    return json.loads("".join(getattr(item, "text", "") for item in content))


def cli(*argv):
    from vixl.cli import dispatch

    result, _ = dispatch(["--json", *argv])
    return result


def test_cli_python_mcp_and_session_roll_identical_design_defaults(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    by_cli = cli("new", "1080x1350", "--seed", "41", "--variety", "low", "-o", "cli.vixl")["design_defaults"]
    by_python = Project(1080, 1350, seed=41, variety="low").state["design_defaults"]
    by_new = Project.new(width=1080, height=1350, seed=41, variety="low").state["design_defaults"]
    by_mcp = mcp(mcp_server(workspace=tmp_path), "vixl_document_create",
                 {"path": "mcp.vixl", "width": 1080, "height": 1350, "seed": 41, "variety": "low"})["design_defaults"]
    by_session = Session(None, workspace=tmp_path).create("session.vixl", 1080, 1350, seed=41,
                                                          variety="low")["design_defaults"]
    assert by_cli == by_python == by_new == by_mcp == by_session
    assert by_cli["seed"] == 41 and by_cli["variety"] == "low"
    assert Project.load("cli.vixl").state["design_defaults"] == by_cli
    sized = Project.sized("instagram-portrait", seed=41, variety="low").state["design_defaults"]
    # A named size implies its purpose, which weights the roll (house style purpose tier).
    assert sized["purpose"] == "social" and sized["purpose_source"] == "size"
    assert (sized["seed"], sized["variety"]) == (41, "low")


def test_creation_is_one_revision_and_plain_canvas_keeps_the_old_result(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    p = Project(seed=3)
    assert len(p.nodes) == 1 and p.state["design_defaults"]["seed"] == 3
    plain = Project(64, 32)
    assert plain.state["canvas"]["background"] == "transparent" and "design_defaults" not in plain.state
    plain = Project.sized("instagram-square", design=False)
    assert plain.state["canvas"]["background"] == "transparent" and "design_defaults" not in plain.state
    # An unseeded Python roll leaves no history behind unless a workspace is named.
    Project()
    assert not (tmp_path / ".vixl" / "rolls.json").exists()
    Project(workspace=tmp_path)
    assert (tmp_path / ".vixl" / "rolls.json").exists()


def test_purpose_picks_the_size_and_nothing_gives_1080_square(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    slides = Project(purpose="slides", seed=1)
    assert (slides.state["canvas"]["width"], slides.state["canvas"]["height"]) == (1920, 1080)
    assert slides.state["canvas"]["size"] == "slide" and slides.state["design_defaults"]["purpose"] == "slides"
    blank = Project(seed=1)
    assert (blank.state["canvas"]["width"], blank.state["canvas"]["height"]) == (1080, 1080)
    social = Project.new(purpose="social", seed=1)
    assert (social.state["canvas"]["width"], social.state["canvas"]["height"]) == (1080, 1350)
    result = mcp(mcp_server(workspace=tmp_path), "vixl_document_create", {"path": "deck.vixl", "purpose": "slides"})
    assert result["canvas"]["width"] == 1920 and result["creation"]["size_from"] == "purpose"
    result = mcp(mcp_server(workspace=tmp_path), "vixl_document_create", {"path": "any.vixl"})
    assert (result["canvas"]["width"], result["canvas"]["height"]) == (1080, 1080)
    assert result["creation"]["size_from"] == "default"
    made = cli("new", "--purpose", "icon", "-o", "icon.vixl")
    assert made["canvas"]["size"] == "app-icon" and made["canvas"]["width"] == 1024
    composed = Session(None, workspace=tmp_path)
    from vixl.compose import compose

    result, _ = compose(composed, dry_run=True, purpose="story", check=False)
    assert result["creation"]["size"] == "story"
    with pytest.raises(VixlError, match="Unknown purpose"):
        Project(purpose="slids")
    with pytest.raises(VixlError, match="Give width and height"):
        Project(width=100)


def test_print_purposes_follow_the_paper_of_the_locale(monkeypatch):
    assert paper_size({"LANG": "en_US.UTF-8"}) == "letter"
    assert paper_size({"LANG": "de_DE.UTF-8"}) == "a4"
    assert paper_size({"LC_PAPER": "en_GB.UTF-8", "LANG": "en_US.UTF-8"}) == "a4"
    assert paper_size({"LANG": "C.UTF-8"}) == "letter"
    monkeypatch.setenv("LC_ALL", "fr_FR.UTF-8")
    assert purpose_size("document") == "a4" and purpose_size("poster") == "poster-18x24"


def test_design_documents_get_the_palette_background_and_marks_stay_transparent(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from vixl.layouts import assign_roles
    import random

    social = Project.sized("instagram-portrait", seed=12)
    direction = social.state["design_defaults"]["direction"]
    expected = assign_roles({"palette": direction["palette"], "mode": direction["mode"]}, random.Random(12))["background"]
    assert social.state["canvas"]["background"] == expected
    assert social.render().getpixel((5, 5))[3] == 255
    assert Project.sized("favicon", seed=12).state["canvas"]["background"] == "transparent"
    assert Project(purpose="logo", seed=12).state["canvas"]["background"] == "transparent"
    assert Project(800, 800, purpose="emblem", seed=12).state["canvas"]["background"] == "transparent"
    assert Project.sized("instagram-portrait", "transparent", seed=12).state["canvas"]["background"] == "transparent"
    made = cli("new", "favicon", "-o", "f.vixl")
    assert made["canvas"]["background"] == "transparent" and made["creation"]["background_from"] == "mark"
    made = cli("new", "story", "--seed", "12", "-o", "s.vixl")
    assert made["creation"]["background_from"] == "palette" and made["canvas"]["background"].startswith("#")
    made = cli("new", "story", "--background", "transparent", "-o", "t.vixl")
    assert made["canvas"]["background"] == "transparent"


def _cache_pairing(cache, name):
    font = (Path(typefaces.DATA) / "DejaVuSans.ttf").read_bytes()
    item = get_pairing(name)
    for role in ("heading", "body"):
        (cache / f"{slug(item[role]['family'])}-{item[role]['weight']}.ttf").write_bytes(font)


def test_rolled_pairing_is_installed_from_the_cache_without_network(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cache = tmp_path / "cache"
    cache.mkdir()
    monkeypatch.setenv("VIXL_FONT_CACHE", str(cache))
    monkeypatch.setenv("VIXL_AUTO_FONTS", "on")
    monkeypatch.setattr(creation, "network_client", lambda: pytest.fail("the cache must be enough"))
    pairing = Project(seed=8, workspace_fonts=False).state["design_defaults"]["direction"]["pairing"]
    _cache_pairing(cache, pairing)
    report = {}
    p = Project.new(seed=8, report=report)
    fonts = report["creation"]["fonts"]
    assert fonts["installed"] and fonts["origin"] == "cache" and fonts["pairing"] == pairing
    assert p.state["typography"]["heading"] and p.state["typography"]["body"] and len(p.nodes) == 1
    p.apply({"type": "layout-apply", "name": "quiet-editorial", "title": "Real fonts", "unfilled": "omit"})
    assert not [i for i in p.check(checks=["fonts"])["issues"] if i["check"] == "fonts"]
    made = cli("new", "--seed", "8", "-o", "cli.vixl")
    assert made["creation"]["fonts"]["installed"]
    assert not cli("new", "--seed", "8", "--no-fonts", "-o", "bare.vixl")["creation"].get("fonts")


def test_offline_creation_warns_once_and_falls_back_quickly(tmp_path, monkeypatch):
    monkeypatch.setenv("VIXL_FONT_CACHE", str(tmp_path / "empty"))
    monkeypatch.setenv("VIXL_AUTO_FONTS", "on")
    monkeypatch.setattr(creation, "_offline", False)
    attempts = []

    def offline():
        attempts.append(1)

        def refuse(request):
            raise httpx.ConnectError("no route", request=request)

        return httpx.Client(transport=httpx.MockTransport(refuse))

    monkeypatch.setattr(creation, "network_client", offline)
    first, second = {}, {}
    p = Project.new(seed=2, report=first)
    Project.new(seed=3, report=second)
    assert attempts == [1]
    assert not first["creation"]["fonts"]["installed"] and "warning" in first["creation"]["fonts"]
    assert "warning" not in second["creation"]["fonts"] and second["creation"]["fonts"]["next_step"]
    assert "typography" not in p.state and len(p.nodes) == 1
    monkeypatch.setenv("VIXL_AUTO_FONTS", "off")
    assert Project.new(seed=2, report=first) and first["creation"]["fonts"]["reason"] == "VIXL_AUTO_FONTS=off"


def test_rolled_accent_is_drawn_in_safe_compositions():
    renders = []
    for accent in ("none", "dot"):
        result = roll(31, locks={"layout": "centered-note", "accent": accent})
        p = Project(1080, 1080)
        p.apply({**result["operation"], "title": "One message", "unfilled": "omit"})
        renders.append(p.render().tobytes())
        assert any(layer["name"] == "accent" for layer in p.state["layers"]) == (accent != "none")
    assert renders[0] != renders[1]


def test_rolled_density_changes_margins_and_gaps():
    built = {}
    for density in ("airy", "dense"):
        result = roll(17, locks={"layout": "quiet-editorial", "density": density, "margin": 0.085})
        p = Project(1080, 1080)
        p.apply({**result["operation"], "title": "Space", "subtitle": "Room to breathe", "unfilled": "omit"})
        built[density] = p.state["layout"]["margin"]
    assert built["airy"] > built["dense"]
    from vixl.layouts import DENSITY_CHOICES

    assert DENSITY_CHOICES.count("balanced") == 2


def test_sparse_layout_apply_inherits_the_whole_stored_direction(tmp_path, monkeypatch):
    from vixl.typefaces import roll_document

    font = (Path(typefaces.DATA) / "DejaVuSans.ttf").read_bytes()
    monkeypatch.setattr(typefaces, "fetch_font", lambda family, weight=400, *a, **k: (font, family))
    monkeypatch.setenv("VIXL_AUTO_FONTS", "cache")
    rolled = Project(1080, 1080, workspace=tmp_path)
    roll = roll_document(rolled, seed=23, apply=True, slots={"title": "Same direction"})
    created = Project(1080, 1080, seed=23)
    assert created.state["typography"] == rolled.state["typography"]
    created.apply({"type": "layout-apply", "name": roll["direction"]["layout"], "title": "Same direction",
                   "unfilled": "omit"})
    same = ("margin", "density", "palette", "mode", "type_scale", "accent", "seed")
    assert {k: created.state["layout"][k] for k in same} == {k: rolled.state["layout"][k] for k in same}
    assert created.state["layout"]["direction"]["corner"] == roll["direction"]["corner"]
    assert created.state["layout"]["direction"]["look"] == roll["direction"]["look"]
    explicit = Project(1080, 1080, seed=23, workspace_fonts=False)
    explicit.apply({"type": "layout-apply", "name": "quiet-editorial", "title": "Mine", "unfilled": "omit",
                    "direction": {"corner": "pill"}, "accent": "none"})
    assert explicit.state["layout"]["direction"]["corner"] == "pill" and explicit.state["layout"]["accent"] == "none"
