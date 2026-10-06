"""REST routes and CLI switches for the catalogs, looks and palette roles."""

import json

from vixl import Project


def test_look_color_falls_back_to_the_stroke_of_an_outline_shape():
    project = Project(400, 300, "#ffffff")
    project.apply({"type": "shape", "shape": "ellipse", "name": "ring", "x": 100, "y": 60, "width": 160, "height": 160,
                   "fill": "transparent", "stroke": "#14b8a6", "stroke_width": 6})
    project.apply({"type": "look", "target": "ring", "look": "glow"})
    assert project.layer("ring")["styles"]["outer-glow"]["color"] == "#14b8a6"


def test_rest_exposes_the_guide_styles_and_looks():
    from fastapi.testclient import TestClient

    from vixl.interfaces import create_app

    import tempfile
    from pathlib import Path

    folder = Path(tempfile.mkdtemp())
    Project(100, 100).save(folder / "d.vixl")
    client = TestClient(create_app(folder / "d.vixl"))
    assert client.get("/guide").json()["start_here"]
    assert client.get("/guide", params={"brief": "a mandala"}).json()["matched"] == "mandala"
    assert client.get("/guide", params={"brief": "zzzz qqqq"}).status_code == 400
    assert client.get("/styles").json()["count"] >= 20
    assert client.get("/styles", params={"query": "neon"}).json()["styles"][0]["name"] == "cyberpunk"
    assert client.get("/styles", params={"name": "swiss"}).json()["name"] == "swiss"
    assert client.get("/styles", params={"name": "swis"}).status_code == 400
    assert "glow" in client.get("/looks").json()["looks"]


def test_cli_palette_and_layout_keep_order(tmp_path, capsys, monkeypatch):
    from vixl.cli import main

    monkeypatch.chdir(tmp_path)

    def run(*argv):
        capsys.readouterr()
        assert main(list(argv)) in (0, None)
        return json.loads(capsys.readouterr().out)

    run("new", "600x600", "-o", "p.vixl")
    run("-p", "p.vixl", "palette-define", "mine", '["#0f172a", "#1e293b", "#38bdf8"]')
    kept = run("-p", "p.vixl", "palette", "apply", "mine", "--keep-order")
    assert kept["changes"]["palette_roles"]["keep_order"] is True
    assert kept["changes"]["swatches"]["background"] == "#0f172a"
    mapped = run("-p", "p.vixl", "palette", "apply", "mine", "--roles", '{"accent": 0}')
    assert {e["role"]: e["source"] for e in mapped["changes"]["palette_roles"]["roles"]}["accent"] == "explicit"
    result = run("-p", "p.vixl", "layout", "apply", "hero-statement", "--set", "title=Hi", "--set", "subtitle=There",
                 "--set", "label=New", "--set", "cta=Go", "--palette", '["#0f172a", "#1e293b", "#38bdf8"]', "--keep-order",
                 "--seed", "2")
    assert result["layout"]["roles"][0]["source"] == "palette[0]" and result["layout"]["mode"] == "dark"
