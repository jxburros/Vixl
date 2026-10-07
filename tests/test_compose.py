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
    assert result["steps"] == ["request", "create", "layout", "style", "look", "operations", "check", "preview",
                               "save", "export"]
    assert result["document"] == "card.vixl" and result["layout"]["seed"] == 3
    assert "issues" in result["check"] and image[:8] == b"\x89PNG\r\n\x1a\n"
    assert Image.open(tmp_path / "out/card.png").size == (1080, 1080) and (tmp_path / "out/card.pdf").is_file()
    project = Project.load(tmp_path / "card.vixl")
    assert project.layer("dot") and project.state.get("style")


def test_compose_says_when_it_replaces_the_active_document(tmp_path):
    session = Session(workspace=tmp_path)
    first, _ = compose(session, path="first.vixl", width=200, height=100)
    assert first["active_document"] is True and not first.get("warnings")
    session.create(tmp_path / "jazz.vixl", 300, 200)
    result, _ = compose(session, path="card.vixl", width=200, height=100)
    assert session.path == tmp_path / "card.vixl" and result["active_document"] is True
    assert any("card.vixl is now the active document" in w and "document='jazz.vixl'" in w for w in result["warnings"])


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
