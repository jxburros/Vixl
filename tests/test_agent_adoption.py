"""End-to-end regression coverage for installation and collaborative agent workflows."""

import asyncio
import base64
from copy import deepcopy
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from vixl import Project, VixlError
from vixl.interfaces import Session, create_app, mcp_http_app, mcp_server, serve_mcp
from vixl.imports import import_document
from vixl.typefaces import roll_document

FONT = Path(__file__).parents[1] / "src/vixl/data/DejaVuSans.ttf"


def brand(workspace):
    kit = {
        "name": "Example",
        "palette": {
            "background": "#ffffff",
            "surface": "#eeeeee",
            "ink": "#111111",
            "muted": "#444444",
            "accent": "#0044aa",
            "accent-text": "#0044aa",
            "on-accent": "#ffffff",
        },
        "minimum_contrast": 7,
        "fonts": {
            role: {"name": "brand-" + role, "data_base64": base64.b64encode(FONT.read_bytes()).decode()}
            for role in ("heading", "body")
        },
    }
    (workspace / "brand.json").write_text(json.dumps(kit))
    return kit


def test_layout_reports_missing_slots_in_compact_and_dry_run():
    p = Project(800, 1000)
    head = p.head
    result = p.apply(
        {"type": "layout-apply", "name": "event-poster", "title": "Launch"}, dry_run=True, detail="compact"
    )
    assert {"cta", "caption"} <= set(result["unfilled_slots"])
    assert result["layout"]["blanks"] and p.head == head and not p.state["layers"]


def test_rolled_shadow_look_keeps_to_the_brand_palette(tmp_path):
    # Seed 16 rolls the soft-shadow look; its shadow used to be black, outside the brand palette.
    brand(tmp_path)
    session = Session(workspace=tmp_path)
    session.create("design.vixl", 800, 800, seed=16)
    session.apply([{"type": "layout-apply", "name": "hero-statement", "title": "Launch", "unfilled": "omit"}])
    with session.project() as p:
        assert p.state["design_defaults"]["direction"]["look"] == "soft-shadow"
        assert not p.check(checks=["brand"])["issues"]


def test_workspace_brand_layout_template_check_and_roll(tmp_path):
    kit = brand(tmp_path)
    (tmp_path / "nested").mkdir()
    session = Session(workspace=tmp_path)
    session.create("nested/design.vixl", 800, 800)
    result = session.apply(
        [{"type": "layout-apply", "name": "hero-statement", "title": "Launch", "unfilled": "omit"}]
    )
    assert result["unfilled_slots"] == []
    with session.project() as p:
        assert p.state["swatches"]["accent"] == kit["palette"]["accent"]
        assert p.state["typography"]["heading"] == "brand-heading"
        assert p.layer("headline")["font"] in p.assets
        assert not p.check(checks=["brand"])["issues"]
        direction = roll_document(p, seed=1)
        assert direction["brand_fonts"]["heading"] == "brand-heading"
        assert direction["operation"]["colors"] == kit["palette"]
    session.apply([{"type": "text", "name": "offbrand", "text": "Bad", "color": "red", "size": 20}])
    assert any(i["check"] == "brand" for i in session.check(checks=["brand"])["issues"])
    kit["required_elements"] = ["logo"]
    (tmp_path / "brand.json").write_text(json.dumps(kit))
    assert session.check(checks=["brand"])["errors"] == 1
    from vixl.resources import create_template

    template = create_template("social-square", {"title": "Hello", "subtitle": "World"}, workspace=tmp_path)
    assert template.state["swatches"]["background"] == "#ffffff"
    assert template.state["typography"]["body"] == "brand-body"


def test_roll_apply_is_one_undo_step_and_atomic(tmp_path, monkeypatch):
    brand(tmp_path)
    p = Project(800, 800)
    p._workspace = tmp_path
    before, head = deepcopy(p.state), p.head
    result = roll_document(
        p, seed=1, apply=True, locks={"layout": "hero-statement"}, slots={"title": "Hello"}
    )
    assert result["applied"]["success"] and p.layer("headline")["text"] == "Hello"
    p.save(tmp_path / "roll.vixl")
    p = Project.load(tmp_path / "roll.vixl")
    p.undo()
    assert p.state == before and p.head == head
    p.redo()
    before, head = deepcopy(p.state), p.head
    with pytest.raises(VixlError):
        roll_document(p, seed=2, apply=True, slots={"not_a_slot": "Oops"})
    assert p.state == before and p.head == head
    # A font download failure must leave both document and history untouched.
    (tmp_path / "brand.json").unlink()

    def fail(*args, **kwargs):
        raise VixlError("font_download_failed", "Offline")

    monkeypatch.setattr("vixl.typefaces.fetch_font", fail)
    with pytest.raises(VixlError, match="Offline"):
        roll_document(p, seed=1, apply=True)
    assert p.state == before and p.head == head


def test_cli_roll_apply_and_review_notes(tmp_path, monkeypatch):
    from vixl.cli import dispatch

    monkeypatch.chdir(tmp_path)
    brand(tmp_path)
    Project(800, 800).save(tmp_path / "design.vixl")
    result, _ = dispatch(
        [
            "-p",
            "design.vixl",
            "roll",
            "--apply",
            "--seed",
            "1",
            "--lock",
            "layout=hero-statement",
            "--set",
            "title=Hello",
        ]
    )
    assert result["applied"]["success"]
    result, _ = dispatch(["-p", "design.vixl", "notes", "add", "Make the title smaller"])
    assert result["notes"][0]["text"] == "Make the title smaller"


def test_viewer_refresh_and_notes_are_shared_with_mcp(tmp_path):
    path = tmp_path / "design.vixl"
    Project(100, 100).save(path)
    with TestClient(create_app(path, token="secret")) as client:
        viewer = client.get("/view")
        assert viewer.status_code == 200 and "Connecting…" in viewer.text
        assert 'rel="icon"' in viewer.text and 'alt="Vixl"' in viewer.text
        assert viewer.text.count("data:image/svg+xml;base64,") == 2
        assert "__VIXL_" not in viewer.text
        assert client.get("/review").status_code == 401
        client.headers["Authorization"] = "Bearer secret"
        head = client.get("/review").json()["head"]
        p = Project.load(path)
        p.apply({"type": "solid", "color": "red", "name": "red"})
        p.save()
        review = client.get("/review").json()
        assert review["head"] != head and review["layers"][0]["name"] == "red"
        assert client.get("/render").headers["content-type"] == "image/png"
        note = client.post("/notes", json={"text": "Title too big"}).json()["notes"][0]
        assert (
            client.post(
                "/notes", json={"text": "bad"}, headers={"Origin": "https://evil.example"}
            ).status_code
            == 403
        )
    server = mcp_server(path, workspace=tmp_path)

    async def read():
        content = await server.call_tool("vixl_review_notes", {})
        if isinstance(content, tuple):
            content = content[0]
        return json.loads(content[0].text)

    assert asyncio.run(read())["notes"][0]["id"] == note["id"]
    with TestClient(create_app(path)) as client:
        assert client.post("/notes/" + note["id"] + "/resolve").json()["notes"][0]["resolved"]


def rpc(response):
    assert response.status_code == 200, response.text
    if response.headers.get("content-type", "").startswith("text/event-stream"):
        return json.loads(next(line[6:] for line in response.text.splitlines() if line.startswith("data: ")))
    return response.json()


def test_streamable_http_initialization_and_tool_call(tmp_path):
    server = mcp_server(workspace=tmp_path, schema="slim", tools="core")
    with TestClient(mcp_http_app(server, token="secret")) as client:
        assert client.post("/mcp").status_code == 401
        client.headers.update(
            {"Authorization": "Bearer secret", "Accept": "application/json, text/event-stream"}
        )
        response = client.post(
            "/mcp",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-03-26",
                    "capabilities": {},
                    "clientInfo": {"name": "test", "version": "1"},
                },
            },
        )
        assert rpc(response)["result"]["serverInfo"]["name"] == "Vixl"
        client.headers["Mcp-Session-Id"] = response.headers["mcp-session-id"]
        client.headers["MCP-Protocol-Version"] = "2025-03-26"
        assert (
            client.post("/mcp", json={"jsonrpc": "2.0", "method": "notifications/initialized"}).status_code
            == 202
        )
        result = rpc(
            client.post(
                "/mcp",
                json={
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {
                        "name": "vixl_document_create",
                        "arguments": {"path": "http.vixl", "width": 50, "height": 40},
                    },
                },
            )
        )
        assert not result["result"].get("isError") and (tmp_path / "http.vixl").exists()
        assert client.post("/mcp", headers={"Origin": "https://evil.example"}).status_code == 403
    with pytest.raises(VixlError, match="Non-loopback"):
        serve_mcp(server, host="0.0.0.0")


def test_svg_editable_transform_holes_and_undo(tmp_path):
    p = Project(100, 100)
    head = p.head
    result = import_document(
        p,
        b'<svg xmlns="http://www.w3.org/2000/svg"><g transform="translate(10 10)"><path id="mark" fill="red" d="M0 0h80v80H0z M20 20v40h40V20z"/></g></svg>',
        "svg",
    )
    assert result["success"] and p.layer("mark")["type"] == "shape"
    assert p.render().getpixel((50, 50))[3] == 0 and p.render().getpixel((15, 15))[:3] == (255, 0, 0)
    assert p.layer("mark")["x"] == 10
    p.save(tmp_path / "logo.vixl")
    loaded = Project.load(tmp_path / "logo.vixl")
    assert loaded.render().getpixel((50, 50))[3] == 0
    loaded.undo()
    assert loaded.head == head and not loaded.state["layers"]


@pytest.mark.parametrize(
    "svg",
    [
        b'<!DOCTYPE svg [<!ENTITY x "bad">]><svg/>',
        b'<svg><rect width="10" height="10"/><image href="file:///etc/passwd"/></svg>',
        b'<svg><path d="M0 0L10 10" fill="url(https://example.com/a)"/></svg>',
        b'<svg><g opacity="0.5"><rect width="10" height="10"/></g></svg>',
        b'<svg><rect width="10" height="10" style="filter:blur(2px)"/></svg>',
    ],
)
def test_svg_unsupported_features_fail_atomically(svg):
    p = Project(100, 100)
    head = p.head
    with pytest.raises(VixlError):
        import_document(p, svg, "svg")
    assert p.head == head and not p.state["layers"]


def test_pdf_page_import_and_bounds():
    p = Project(100, 100, "red")
    data = p.export(format="PDF")
    target = Project(200, 200)
    result = import_document(target, data, "pdf", dpi=72)
    assert result["warnings"] and target.state["layers"][0]["type"] == "raster"
    assert target.render().getpixel((10, 10))[0] > 240
    head = target.head
    with pytest.raises(VixlError):
        import_document(target, data, "pdf", page=2)
    assert target.head == head


def test_brand_logos_stay_visible_and_defaults_can_be_overridden(tmp_path):
    from io import BytesIO
    from PIL import Image

    kit = brand(tmp_path)
    stream = BytesIO()
    Image.new("RGBA", (12, 12), "red").save(stream, format="PNG")
    kit["logos"] = [
        {"name": "logo", "data_base64": base64.b64encode(stream.getvalue()).decode(), "x": 0, "y": 0}
    ]
    kit["required_elements"] = ["logo"]
    (tmp_path / "brand.json").write_text(json.dumps(kit))
    p = Project(800, 800)
    p._workspace = tmp_path
    p.apply({"type": "layout-apply", "name": "hero-statement", "title": "Hi", "unfilled": "omit"})
    assert p.render().getpixel((3, 3))[:3] == (255, 0, 0)
    p.apply(
        {
            "type": "layout-apply",
            "name": "hero-statement",
            "title": "Again",
            "unfilled": "omit",
            "replace": True,
            "palette": "ocean",
        }
    )
    assert len([layer for layer in p.state["layers"] if layer["name"] == "logo"]) == 1
    assert p.state["layout"]["palette"] == "ocean"
    assert p.state["swatches"]["accent"] != kit["palette"]["accent"]


def test_brand_contrast_cannot_be_lowered_and_paths_stay_scoped(tmp_path):
    kit = brand(tmp_path)
    p = Project(200, 100, "white")
    p._workspace = tmp_path
    p.apply({"type": "text", "text": "Contrast", "color": "#777777", "size": 30})
    assert p.check(checks=["contrast"], min_contrast=1)["errors"] > 0
    outside = tmp_path.parent / (tmp_path.name + "-outside.json")
    outside.write_text(json.dumps(kit))
    (tmp_path / "brand.json").unlink()
    try:
        (tmp_path / "brand.json").symlink_to(outside)
    except OSError:
        pytest.skip("Symlinks unavailable")
    with pytest.raises(VixlError, match="workspace"):
        p.check()


def test_invalid_brand_is_atomic(tmp_path):
    (tmp_path / "brand.json").write_text(
        json.dumps({"fonts": {"heading": {"name": "bad", "data_base64": "!"}}})
    )
    p = Project(200, 100)
    p._workspace = tmp_path
    before, head = deepcopy(p.state), p.head
    with pytest.raises(VixlError):
        p.apply({"type": "layout-apply", "name": "hero-statement", "title": "Hello"})
    assert p.state == before and p.head == head


def test_review_unicode_limit_leaves_valid_file(tmp_path):
    from vixl.review import notes

    path = tmp_path / "design.vixl"
    # A Unicode note uses more bytes than characters; enforce the on-disk read limit.
    with pytest.raises(VixlError, match="byte limit"):
        for _ in range(100):
            notes(path, "add", text="🌟" * 4000)
    assert notes(path)["notes"]


def test_http_rejects_rebinding_host_without_token(tmp_path):
    with TestClient(mcp_http_app(mcp_server(workspace=tmp_path))) as client:
        assert client.post("/mcp", headers={"Host": "evil.example"}).status_code == 400


def test_agent_bundles_include_skill_references(tmp_path):
    import importlib.util
    import zipfile

    location = Path(__file__).parents[1] / "distribution/package_extensions.py"
    spec = importlib.util.spec_from_file_location("package_extensions", location)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    outputs = module.build(tmp_path)
    for output in outputs:
        with zipfile.ZipFile(output) as archive:
            names = set(archive.namelist())
            assert "skills/vixl/SKILL.md" in names
            assert "skills/vixl/references/cli.md" in names
            if output.suffix == ".mcpb":
                manifest = json.loads(archive.read("manifest.json"))
                assert archive.read(manifest["icon"]).startswith(b"\x89PNG\r\n\x1a\n")
                assert "${user_config.workspace}" in manifest["server"]["mcp_config"]["args"]
                from vixl import __version__
                source = f"https://github.com/jxburros/Vixl/archive/refs/tags/v{__version__}.tar.gz"
                assert manifest["server"]["mcp_config"]["args"][1] == source
            else:
                config = json.loads(archive.read(".mcp.json"))
                from vixl import __version__
                assert config["mcpServers"]["vixl"]["args"][1].endswith(f"/v{__version__}.tar.gz")


def test_brand_checks_canvas_gradients_and_hidden_required_elements(tmp_path):
    kit = {"palette": {"ink": "black"}, "required_elements": ["logo"]}
    (tmp_path / "brand.json").write_text(json.dumps(kit))
    p = Project(100, 100, "red")
    p._workspace = tmp_path
    p.apply(
        [
            {"type": "gradient", "name": "gradient", "start": "black", "end": "blue"},
            {
                "type": "shape",
                "shape": "rectangle",
                "name": "logo",
                "fill": "black",
                "width": 10,
                "height": 10,
            },
            {"type": "opacity", "target": "logo", "value": 0},
        ]
    )
    issues = p.check(checks=["brand"])["issues"]
    assert sum(i["severity"] == "warning" for i in issues) == 2
    assert any("missing: logo" in i["message"] for i in issues)
    assert len(roll_document(p, seed=1)["operation"]["palette"]) == 2
