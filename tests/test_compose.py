import asyncio
import json
import subprocess
import sys

from PIL import Image
import pytest

from vixl import Project
from vixl.compose import compose, run
from vixl.errors import VixlError
from vixl.interfaces import Session

LAYOUT = {"name": "hero-statement", "title": "Hello", "subtitle": "One idea, said well.", "label": "New", "cta": "Go",
          "seed": 3}


def test_compose_builds_saves_and_exports_in_one_call(tmp_path):
    session = Session(workspace=tmp_path)
    result, image = compose(session, path="card.vixl", size="instagram-post", layout=LAYOUT,
                            look={"look": "grain", "target": "background"}, style="swiss",
                            operations=[{"type": "shape", "shape": "ellipse", "name": "dot", "x": 10, "y": 10,
                                         "width": 40, "height": 40, "fill": "red"}],
                            preview=True, exports=["out/card.png", {"path": "out/card.pdf"}])
    # The style's own font pairing is installed when the call names none (or noted when it cannot be fetched).
    assert result["steps"] == ["request", "create", "fonts", "layout", "style", "look", "operations", "check",
                               "preview", "save", "export"]
    assert result["fonts"]["pairing"] == "inter-single-ui"
    assert result["document"] == "card.vixl" and result["layout"]["seed"] == 3
    assert "issues" in result["check"] and image[:8] == b"\x89PNG\r\n\x1a\n"
    assert Image.open(tmp_path / "out/card.png").size == (1080, 1080) and (tmp_path / "out/card.pdf").is_file()
    project = Project.load(tmp_path / "card.vixl")
    assert project.layer("dot") and project.state.get("style")


def test_a_failing_step_is_named_and_nothing_is_written(tmp_path):
    session = Session(workspace=tmp_path)
    with pytest.raises(VixlError) as caught:
        compose(session, path="bad.vixl", width=200, height=100, layout=LAYOUT,
                operations=[{"type": "shape", "shape": "nope"}], exports=["bad.png"])
    error = caught.value.as_dict()
    assert error["step"] == "operations" and error["operation_index"] == 0 and error["message"].startswith("operations:")
    assert not (tmp_path / "bad.vixl").exists() and not (tmp_path / "bad.png").exists()
    with pytest.raises(VixlError) as caught:
        compose(session, path="bad.vixl", width=200, height=100, layout={"name": "no-such-layout"})
    assert caught.value.details["step"] == "layout"
    # Export targets are checked before anything is built.
    (tmp_path / "taken.png").write_bytes(b"x")
    with pytest.raises(VixlError) as caught:
        compose(session, path="bad.vixl", width=200, height=100, exports=["taken.png"])
    assert caught.value.details["step"] == "export" and not (tmp_path / "bad.vixl").exists()
    with pytest.raises(VixlError) as caught:
        compose(session, path="bad.vixl", width=200, height=100, colour="red")
    assert caught.value.details["step"] == "request"


def test_strict_check_and_dry_run_save_nothing(tmp_path):
    session = Session(workspace=tmp_path)
    operations = [{"type": "text", "name": "faint", "text": "Barely there", "x": 10, "y": 10, "size": 14,
                   "color": "#eeeeee"}]
    with pytest.raises(VixlError) as caught:
        compose(session, path="s.vixl", width=300, height=100, background="white", operations=operations, strict=True)
    assert caught.value.details["step"] == "check" and caught.value.details["report"]["issues"]
    result, _ = compose(session, width=300, height=100, background="white", operations=operations, dry_run=True)
    assert result["dry_run"] and result["check"]["errors"] and not (tmp_path / "s.vixl").exists()


def test_image_slots_take_workspace_paths_in_one_call(tmp_path):
    (tmp_path / "memes").mkdir()
    Image.new("RGB", (64, 48), "#2266aa").save(tmp_path / "memes/img0.png")
    Image.new("RGB", (64, 48), "#aa6622").save(tmp_path / "memes/img1.png")
    session = Session(workspace=tmp_path)
    result, _ = compose(session, path="meme.vixl", width=400, height=400,
                        layout={"name": "meme-top-bottom", "image": "memes/img0.png", "title": "Top", "caption": "Bottom"})
    imported = result["layout"]["imported"]
    assert [entry["path"] for entry in imported] == ["memes/img0.png"] and imported[0]["sha256"]
    project = Project.load(tmp_path / "meme.vixl")
    frames = [layer for layer in project.state["layers"] if layer.get("asset") == imported[0]["asset"]]
    assert frames and "image" not in project.state["layout"].get("blanks", [])
    assert project.render().getpixel((200, 200))[:3] == (0x22, 0x66, 0xAA)
    result, _ = compose(session, path="pair.vixl", width=400, height=400,
                        layout={"name": "meme-comparison", "images": ["memes/img0.png", "memes/img1.png"],
                                "items": "No\nYes"})
    assert len(result["layout"]["imported"]) == 2
    # Paths stay inside the workspace, and a missing file names the slot.
    for bad, code in (("../outside.png", "forbidden"), ("memes/none.png", "not_found")):
        with pytest.raises(VixlError) as caught:
            compose(session, path="bad.vixl", width=200, height=200, layout={"name": "meme-top-bottom", "image": bad})
        assert caught.value.code == code and caught.value.details["step"] == "layout"
    assert not (tmp_path / "bad.vixl").exists()


def test_the_compose_background_survives_a_layout(tmp_path):
    session = Session(workspace=tmp_path)
    layout = {"name": "event-poster", "title": "Night Market", "label": "Fri 12 June", "body": "6 pm\nPier 9",
              "cta": "RSVP", "caption": "example.org", "seed": 4}
    result, _ = compose(session, path="p.vixl", width=600, height=800, background="#10131c", layout=layout)
    assert result["layout"]["background"].startswith("#10131c")
    project = Project.load(tmp_path / "p.vixl")
    assert project.render().getpixel((2, 2))[:3] == (0x10, 0x13, 0x1C)
    assert project.state["layout"]["mode"] == "dark"
    assert not project.check(checks=["contrast"])["errors"]
    # A layout that names its own background role keeps it; transparent keeps the layout from painting one.
    result, _ = compose(session, path="q.vixl", width=600, height=800, background="#10131c",
                        layout={**layout, "colors": {"background": "#fafafa"}})
    assert "background" not in result["layout"]
    assert Project.load(tmp_path / "q.vixl").render().getpixel((2, 2))[:3] == (0xFA, 0xFA, 0xFA)
    compose(session, path="t.vixl", width=600, height=800, background="transparent", layout=layout)
    assert Project.load(tmp_path / "t.vixl").render().getpixel((2, 2))[3] == 0


def test_a_style_shapes_the_layout_and_fonts_so_its_own_check_passes(tmp_path, monkeypatch):
    from vixl import typefaces

    def offline(*args, **kwargs):
        raise VixlError("font_download_failed", "Font download failed (ConnectError); check network access")

    monkeypatch.setattr(typefaces, "fetch_font", offline)
    session = Session(workspace=tmp_path)
    for seed in range(6):
        result, _ = compose(session, dry_run=True, size="instagram-post", style="swiss", check=["style"],
                            layout={"name": "big-number", "title": "87%", "label": "Retention", "seed": seed,
                                    "subtitle": "of users came back within a week", "body": "Source: survey"})
        assert result["layout"]["from_style"]["align"] == "left" and result["layout"]["from_style"]["palette"]
        assert not [issue for issue in result["check"]["issues"] if "swiss" in issue["message"]], result["check"]
        assert result["fonts"]["pairing"] == "inter-single-ui" and result["fonts"]["installed"] is False
    # What the caller chose wins over the style.
    result, _ = compose(session, dry_run=True, size="instagram-post", style="swiss", font_pairing=None,
                        layout={"name": "big-number", "title": "87%", "align": "center", "palette": "mono", "seed": 1})
    assert "from_style" not in result["layout"]


def test_compose_through_mcp_cli_rest_and_python(tmp_path):
    from vixl.mcp_tools import build_server

    server = build_server(Session(workspace=tmp_path), tools="compact")
    assert "vixl_compose" in {tool.name for tool in asyncio.run(server.list_tools())}
    answer = asyncio.run(server.call_tool("vixl_compose", {"path": "m.vixl", "width": 120, "height": 80,
                                                           "operations": [{"type": "solid", "color": "navy"}],
                                                           "exports": ["m.png"], "preview": True}))
    blocks = answer[0] if isinstance(answer, tuple) else answer
    assert json.loads(blocks[0].text)["document"] == "m.vixl" and blocks[1].type == "image"
    assert (tmp_path / "m.png").is_file()

    (tmp_path / "req.json").write_text(json.dumps({"path": "c.vixl", "size": "og-image", "layout": LAYOUT}))
    done = subprocess.run([sys.executable, "-m", "vixl", "--json", "compose", "--request", "req.json", "--preview",
                           "c.png"], cwd=tmp_path, capture_output=True, timeout=120)
    assert done.returncode == 0, done.stderr.decode()
    assert json.loads(done.stdout)["preview"] == "c.png" and (tmp_path / "c.vixl").is_file()

    result = run(tmp_path, path="p.vixl", width=64, height=64, preview=True, check=False)
    assert result["document"] == "p.vixl" and result["preview_png"].startswith(b"\x89PNG")

    from fastapi.testclient import TestClient
    from vixl.interfaces import create_app

    with TestClient(create_app(str(tmp_path / "p.vixl"))) as client:
        response = client.post("/compose", json={"width": 64, "height": 64, "preview": True})
        assert response.status_code == 200 and response.json()["dry_run"] and response.json()["preview_base64"]
        assert client.post("/compose", json={"path": "x.vixl", "width": 64, "height": 64}).status_code == 403
