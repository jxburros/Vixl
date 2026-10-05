"""Agent-facing creative, reusable-resource and concurrent-project contracts."""

from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor

import numpy as np
from PIL import Image
import pytest

from vixl import Project
from vixl.assets import add_image
from vixl.errors import VixlError
from vixl.interfaces import Session, service_check, create_app
from vixl.workflows import dispatch
from vixl.resources import get, register, create_template, BUILTINS
from vixl.imports import import_document
from vixl.palette_checks import measure
from vixl.collaboration import merge_states


@pytest.fixture
def session(tmp_path, monkeypatch):
    monkeypatch.setenv("VIXL_RESOURCES", str(tmp_path / "global.json"))
    session = Session(workspace=tmp_path)
    session.create("main.vixl", 80, 60)
    session.apply(
        [
            {
                "type": "shape",
                "shape": "rectangle",
                "name": "artwork",
                "width": 20,
                "height": 20,
                "fill": "red",
            },
            {"type": "text", "name": "title", "text": "Test", "size": 12, "x": 30},
        ]
    )
    return session


def selection_pixels(project):
    return np.asarray(project.image(project.state["selection"], "L"))


def test_wand_contiguity_tolerance_alpha_and_combination():
    p = Project(10, 6)
    image = Image.new("RGBA", (10, 6), "blue")
    for x in (1, 2, 7, 8):
        for y in (1, 2):
            image.putpixel((x, y), (250, 0, 0, 255))
    image.putpixel((2, 2), (245, 1, 0, 255))
    p.apply({"type": "add", "asset": add_image(p, image)})
    p.apply({"type": "select", "shape": "wand", "x": 1, "y": 1, "tolerance": 6}, check=service_check)
    assert (selection_pixels(p) > 0).sum() == 4
    p.apply({"type": "select", "shape": "wand", "x": 1, "y": 1, "tolerance": 6, "contiguous": False})
    assert (selection_pixels(p) > 0).sum() == 8
    p.apply({"type": "select", "shape": "wand", "x": 7, "y": 1, "mode": "subtract"})
    assert (selection_pixels(p) > 0).sum() == 4
    before = deepcopy(p.state)
    with pytest.raises(VixlError):
        p.apply({"type": "select", "shape": "wand", "x": -1, "y": 1})
    assert before == p.state
    transparent = Project(3, 3)
    transparent.apply({"type": "select", "shape": "wand", "x": 0, "y": 0})
    assert selection_pixels(transparent).min() == 255


@pytest.mark.parametrize(
    "shape,geometry", [("lasso", {"points": [[1, 1], [8, 1], [1, 8]]}), ("path", {"path": "M1 1L8 1L1 8z"})]
)
def test_lasso_and_path_masks(shape, geometry):
    p = Project(10, 10)
    p.apply({"type": "solid", "color": "red"})
    p.apply({"type": "select", "shape": shape, **geometry}, check=service_check)
    p.apply({"type": "mask", "action": "from-selection"})
    assert p.render().getpixel((2, 2))[3] == 255
    assert p.render().getpixel((8, 8))[3] == 0


def test_pen_handles_freehand_edit_undo_roundtrip(tmp_path):
    p = Project(60, 60)
    p.apply(
        {
            "type": "pen",
            "name": "curve",
            "nodes": [{"point": [5, 5], "out": [5, 50]}, {"point": [50, 5], "in": [50, 50]}],
            "stroke": "red",
        },
        check=service_check,
    )
    # The box fits the nodes and stroke; the path is stored relative to it.
    layer = p.layer()
    assert layer["path"] == "M2 2 C2 47 47 47 47 2" and (layer["x"], layer["y"]) == (3, 3)
    original = deepcopy(p.layer())
    p.apply(
        {
            "type": "pen",
            "target": "curve",
            "points": [[5, 5], [50, 5], [25, 50]],
            "closed": True,
            "fill": "blue",
        }
    )
    assert p.render().getpixel((25, 20))[2] > 200
    p.save(tmp_path / "pen.vixl")
    assert Project.load(tmp_path / "pen.vixl").layer()["path"].endswith("Z")
    p.undo()
    assert p.layer() == original


@pytest.mark.parametrize(
    "path",
    [
        "M5 5h30v30h-30z",
        "M5 5 30 5 30 30z",
        "M5 5Q10 25 25 25T45 5",
        "M5 25A20 20 0 0 1 45 25",
        "M5 5C5 30 20 30 20 5S40 0 40 20",
    ],
)
def test_full_svg_path_language(path):
    p = Project(50, 50)
    p.apply(
        {
            "type": "shape",
            "shape": "path",
            "path": path,
            "stroke": "red",
            "stroke_width": 2,
            "fill": "transparent",
        }
    )
    assert p.render().getbbox()
    assert path.encode() in p.export(format="SVG")


def test_palette_strict_roles_are_portable_and_pixels_detect_drift(tmp_path):
    p = Project(10, 10)
    p.apply(
        [
            {"type": "palette-define", "name": "brand", "colors": ["#102030", "#f0f0f0", "#cc3344"]},
            {"type": "palette-apply", "name": "brand"},
            {"type": "solid", "color": "@accent"},
        ]
    )
    allowed = set(p.state["palettes"]["brand"])
    assert set(p.state["swatches"].values()) <= allowed
    p.save(tmp_path / "palette.vixl")
    p = Project.load(tmp_path / "palette.vixl")
    assert measure(p, tolerance=0, max_fraction=0)["passed"]
    p.apply({"type": "solid", "name": "drift", "width": 2, "height": 2, "color": "lime"})
    report = measure(p, tolerance=0, max_fraction=0)
    assert report["outside_pixels"] == 4 and not report["passed"]
    suite = {"rules": [{"id": "brand", "kind": "palette", "tolerance": 0, "max_fraction": 0}]}
    p.apply({"type": "suite-set", "name": "brand", "suite": suite})
    assert p.check_suite("brand")["status"] == "failed"
    assert measure(p, region=[3, 3, 7, 7], tolerance=0)["passed"]


def test_palette_antialias_tolerance_and_no_vacuous_pass():
    p = Project(4, 4, "#fc0000")
    assert measure(p, colors=["red", "blue"], tolerance=3)["passed"]
    assert not measure(p, colors=["red", "blue"], tolerance=2)["passed"]
    empty = Project(4, 4)
    report = empty.check_suite({"rules": [{"id": "palette", "kind": "palette", "colors": ["red", "blue"]}]})
    assert report["status"] == "needs_review"


@pytest.mark.parametrize("name", [name for name in BUILTINS["templates"] if name.startswith("modular-")])
def test_modular_templates_render_and_roundtrip(name, tmp_path):
    p = create_template(name)
    assert p.render().getbbox()
    assert p.state["containers"]
    p.save(tmp_path / "template.vixl")
    assert Project.load(tmp_path / "template.vixl").state == p.state


def test_container_swaps_keep_identity_position_and_enforce_rules(tmp_path):
    p = create_template("modular-split", workspace=tmp_path)
    group = deepcopy(p.layer("slot-2"))
    p.apply({"type": "container-swap", "target": "slot-2", "resource": "organic-mark"})
    assert p.layer("slot-2")["id"] == group["id"]
    assert p.layer("slot-2")["x"] == group["x"]
    assert p.layer("slot-2/mark")["shape"] == "heart"
    different = get("containers", "organic-mark")
    different["width"] = 400
    register("containers", "different", different, workspace=tmp_path)
    before = deepcopy(p.state)
    with pytest.raises(VixlError, match="same size"):
        p.apply({"type": "container-swap", "target": "slot-2", "resource": "different"})
    assert before == p.state
    with pytest.raises(VixlError, match="bounds"):
        p.apply(
            {
                "type": "container-swap",
                "target": "slot-1",
                "resource": "headline-left",
                "variables": {"title": "Too long " * 100},
            }
        )
    assert before == p.state


def test_saved_shape_and_custom_test_reuse(session):
    dispatch(session, "shape-save", {"name": "brand-mark", "target": "artwork"})
    session.create("other.vixl", 80, 60)
    session.apply(
        {"type": "shape-place", "resource": "brand-mark", "name": "reused", "width": 10, "height": 10}
    )
    with session.project() as p:
        assert p.layer()["fill"] == "red" and p.layer()["width"] == 10
    suite = {
        "rules": [{"id": "size", "kind": "property", "target": "reused", "field": "width", "expected": 10}]
    }
    dispatch(session, "resource-save", {"kind": "suites", "name": "my-test", "value": suite})
    dispatch(session, "suite-use", {"name": "my-test"})
    assert dispatch(session, "check", {"suite": "my-test"})["passed"]
    session.apply({"type": "resize", "target": "reused", "width": 12})
    assert not dispatch(session, "check", {"suite": "my-test"})["passed"]


@pytest.mark.parametrize("name", list(BUILTINS["workflows"]))
def test_saved_effect_workflows_are_atomic_and_undoable(session, name):
    with session.project() as p:
        before = deepcopy(p.state)
    dispatch(session, "effect-run", {"name": name, "dry_run": True})
    with session.project() as p:
        assert p.state == before
    dispatch(session, "effect-run", {"name": name})
    with session.project(write=True) as p:
        assert p.state != before and p.render().getbbox()
        p.undo()
        assert p.state == before


def test_svg_appearance_static_features_source_and_html(tmp_path):
    svg = b"""<svg xmlns="http://www.w3.org/2000/svg" width="40" height="20">
    <defs><linearGradient id="g"><stop stop-color="red"/><stop offset="1" stop-color="blue"/></linearGradient></defs>
    <g opacity="0.5"><rect width="40" height="20" rx="4" fill="url(#g)"/></g></svg>"""
    p = Project(40, 20)
    result = import_document(p, svg, "svg", svg_mode="auto")
    assert result["mode"] == "appearance"
    assert p.assets[result["source"]] == svg
    assert 120 <= p.render().getpixel((20, 10))[3] <= 130
    p.save(tmp_path / "import.vixl")
    p = Project.load(tmp_path / "import.vixl")
    assert p.assets[result["source"]] == svg
    html = p.export(tmp_path / "design.html")
    assert b"<!doctype html>" in html and b"data:image/svg+xml;base64," in html
    assert b"<script" not in html and b"Content-Security-Policy" in html
    p.apply({"type": "text", "text": "</title><script>alert(1)</script>", "size": 3})
    assert b"<script>" not in p.export(format="HTML")


@pytest.mark.parametrize(
    "payload",
    [
        '<image href="file:///etc/passwd"/>',
        '<image href="https://example.com/x.png"/>',
        "<script>alert(1)</script>",
        "<foreignObject/>",
        '<rect onclick="alert(1)"/>',
        '<style>@import "https://example.com/x";</style>',
        '<rect fill="url(file:///etc/passwd)"/>',
        '<image href="data:image/svg+xml;base64,PHN2Zy8+"/>',
        '<animate attributeName="x"/>',
    ],
)
def test_svg_appearance_rejects_external_or_active_content_atomically(payload):
    p = Project(10, 10)
    before = deepcopy(p.state)
    with pytest.raises(VixlError):
        import_document(
            p, f'<svg width="10" height="10">{payload}</svg>'.encode(), "svg", svg_mode="appearance"
        )
    assert p.state == before and not p.assets


def test_two_agents_merge_independent_edits_and_new_layers(session):
    for branch in ("a", "b"):
        dispatch(session, "branch-fork", {"branch": branch, "output": f"{branch}.vixl", "author": branch})

    def work(branch):
        other = Session(f"{branch}.vixl", workspace=session.workspace)
        target = "artwork" if branch == "a" else "title"
        other.apply(
            [
                {"type": "move", "target": target, "y": 5},
                {"type": "solid", "name": branch, "width": 2, "height": 2, "color": "blue"},
            ]
        )
        return dispatch(other, "branch-merge", {"branch": branch, "dry_run": False})

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(work, ["a", "b"]))
    assert all(result["can_merge"] for result in results)
    with session.project(document="main.vixl") as p:
        assert p.layer("artwork")["y"] == p.layer("title")["y"] == 5
        assert {layer["name"] for layer in p.state["layers"]} == {"artwork", "title", "a", "b"}
        assert len(p.state["merged_branches"]) == 2


def test_merge_conflict_preview_resolution_stale_head_and_undo(session):
    dispatch(session, "branch-fork", {"branch": "a", "output": "a.vixl"})
    session.apply({"type": "move", "target": "artwork", "x": 5}, document="main.vixl")
    session.apply({"type": "move", "target": "artwork", "x": 10}, document="a.vixl")
    result = dispatch(session, "branch-merge", {"branch": "a"})
    assert not result["can_merge"] and len(result["conflicts"]) == 1
    resolution = {result["conflicts"][0]["path"]: "theirs"}
    preview = dispatch(session, "branch-merge", {"branch": "a", "resolutions": resolution})
    assert preview["can_merge"]
    with pytest.raises(VixlError, match="changed since"):
        dispatch(
            session,
            "branch-merge",
            {"branch": "a", "resolutions": resolution, "expected_head": "stale", "dry_run": False},
        )
    dispatch(
        session,
        "branch-merge",
        {"branch": "a", "resolutions": resolution, "expected_head": preview["source_head"], "dry_run": False},
    )
    with session.project(write=True, document="main.vixl") as p:
        assert p.layer("artwork")["x"] == 10
        p.undo()
        assert p.layer("artwork")["x"] == 5


def test_merge_delete_vs_edit_and_independent_dictionary_additions():
    p = Project(10, 10)
    p.apply({"type": "solid", "name": "a"})
    base, ours, theirs = deepcopy(p.state), deepcopy(p.state), deepcopy(p.state)
    ours["layers"] = []
    theirs["layers"][0]["x"] = 2
    _, conflicts = merge_states(base, ours, theirs)
    assert conflicts and conflicts[0]["deleted"]["ours"]
    ours, theirs = deepcopy(base), deepcopy(base)
    ours["swatches"], theirs["swatches"] = {"a": "red"}, {"b": "blue"}
    merged, conflicts = merge_states(base, ours, theirs)
    assert not conflicts and merged["swatches"] == {"a": "red", "b": "blue"}


def test_group_shared_parameters_dry_run_and_validation_rollback(session):
    session.create("second.vixl", 20, 20)
    dispatch(
        session,
        "group-define",
        {
            "name": "campaign",
            "documents": ["main.vixl", "second.vixl"],
            "shared": {"variables": {"headline": "Launch"}, "swatches": {"brand": "blue"}},
        },
    )
    paths = [session.resolve(name) for name in ("main.vixl", "second.vixl")]
    before = [path.read_bytes() for path in paths]
    dispatch(session, "group-apply", {"name": "campaign"})
    assert [path.read_bytes() for path in paths] == before
    with pytest.raises(VixlError):
        dispatch(
            session,
            "group-apply",
            {
                "name": "campaign",
                "dry_run": False,
                "operations": [{"type": "move", "target": "artwork", "x": 7}],
            },
        )
    assert [path.read_bytes() for path in paths] == before
    dispatch(session, "group-apply", {"name": "campaign", "dry_run": False})
    for path in paths:
        p = Project.load(path)
        assert p.state["variables"]["headline"] == "Launch" and p.state["swatches"]["brand"] == "blue"
        p.undo()
        assert "headline" not in p.state["variables"]


def pack(name="demo", version="1.0.0"):
    return {
        "api_version": 1,
        "name": name,
        "version": version,
        "resources": {"palettes": {f"{name}-brand": ["black", "white"]}},
    }


def test_plugin_lifecycle_dependencies_collisions_and_no_partial_install(session):
    manifest = pack()
    dispatch(session, "plugin-install", {"manifest": manifest})
    assert "demo-brand" in dispatch(session, "resource-list", {"kind": "palettes"})["names"]
    with pytest.raises(VixlError, match="belongs to a plugin"):
        dispatch(
            session, "resource-save", {"kind": "palettes", "name": "demo-brand", "value": ["red", "blue"]}
        )
    dependent = pack("child")
    dependent["dependencies"] = {"demo": "1.0.0"}
    dispatch(session, "plugin-install", {"manifest": dependent})
    with pytest.raises(VixlError, match="depend"):
        dispatch(session, "plugin-remove", {"name": "demo"})
    with pytest.raises(VixlError, match="dependent"):
        dispatch(session, "plugin-install", {"manifest": pack(version="2.0.0"), "replace": True})
    invalid = pack("broken")
    invalid["resources"]["palettes"]["broken-bad"] = ["not-a-color", "black"]
    with pytest.raises(VixlError):
        dispatch(session, "plugin-install", {"manifest": invalid})
    assert "broken-brand" not in dispatch(session, "resource-list", {"kind": "palettes"})["names"]
    dispatch(session, "plugin-remove", {"name": "child"})
    dispatch(session, "plugin-remove", {"name": "demo"})
    assert "demo-brand" not in dispatch(session, "resource-list", {"kind": "palettes"})["names"]


def test_python_plugins_require_optin_validate_output_and_isolate_failure(session, monkeypatch):
    import vixl.plugins as plugins

    def handler(document, options):
        document["layers"].clear()
        return [{"type": "opacity", "target": "artwork", "value": options["opacity"]}]

    handler.api_version = 1

    class Entry:
        def load(self):
            return handler

    monkeypatch.setattr(plugins, "entry_points", lambda **kwargs: [Entry()])
    monkeypatch.setattr(plugins, "_ENABLED", False)
    with session.project() as p:
        before = deepcopy(p.state)
        with pytest.raises(VixlError, match="require"):
            plugins.run(p, "test", {"opacity": 0.5})
        plugins.enable_plugins()
        with pytest.raises(VixlError):
            plugins.run(p, "test", {"opacity": -2})
        assert p.state == before
        plugins.run(p, "test", {"opacity": 0.5})
        assert len(p.state["layers"]) == 2 and p.layer("artwork")["opacity"] == 0.5


def test_workspace_resource_symlink_escape_rejected(session, tmp_path):
    outside = tmp_path.parent / (tmp_path.name + "-outside.json")
    outside.write_text("{}")
    try:
        session.resolve(".vixl-resources.json").symlink_to(outside)
    except OSError:
        pytest.skip("This account cannot create symlinks")
    with pytest.raises(VixlError, match="escapes"):
        dispatch(session, "resource-list", {"kind": "palettes"})


def test_rest_html_svg_and_studio_checks(session):
    from fastapi.testclient import TestClient

    client = TestClient(create_app(session.path))
    assert client.post("/workflow/resource-list", json={"kind": "suites"}).status_code == 200
    response = client.post("/export", json={"format": "HTML"})
    assert response.status_code == 200 and response.headers["content-type"].startswith("text/html")
    response = client.post(
        "/import?format=svg&svg_mode=appearance&name=imported",
        content=b'<svg width="5" height="5"><rect width="5" height="5" fill="blue"/></svg>',
    )
    assert response.status_code == 200, response.text
    assert client.post("/workflow/branch-fork", json={"branch": "no", "output": "no.vixl"}).status_code != 200


def test_compact_mcp_has_small_complete_workflow_surface(session):
    import asyncio
    from vixl.mcp_tools import build_server

    server = build_server(session, tools="compact", schema="slim")
    tools = asyncio.run(server.list_tools())
    names = {tool.name for tool in tools}
    assert len(names) <= 12
    assert {"vixl_operations_apply", "vixl_workflow", "vixl_workflow_schema", "vixl_export_file"} <= names
    result = asyncio.run(
        server.call_tool("vixl_workflow", {"action": "resource-list", "request": {"kind": "workflows"}})
    )
    assert "neon-sign" in str(result)


def test_cli_creative_tools_and_workflow_discovery():
    from vixl.commands import compile_command

    assert compile_command("select wand 2 3 --global")["contiguous"] is False
    assert compile_command(["select", "lasso", "[[0,0],[2,0],[0,2]]"])["points"] == [[0, 0], [2, 0], [0, 2]]
    assert compile_command(["pen", "--points", "[[0,0],[2,2]]"])["type"] == "pen"
    assert (
        compile_command(["container-swap", "organic-mark", "--target", "slot-1"])["resource"]
        == "organic-mark"
    )


def test_group_publication_failure_rolls_back_and_crash_journal_recovers(session, monkeypatch):
    import vixl.project_groups as groups

    session.create("second.vixl", 20, 20)
    dispatch(
        session,
        "group-define",
        {
            "name": "family",
            "documents": ["main.vixl", "second.vixl"],
            "shared": {"variables": {"title": "New"}},
        },
    )
    paths = [session.resolve(name) for name in ("main.vixl", "second.vixl")]
    originals = [p.read_bytes() for p in paths]
    publish = groups.publish_file

    def fail_second(path, source, **kwargs):
        if path == paths[1] and str(source).endswith(".after.vixl"):
            raise OSError("Simulated failed publication")
        return publish(path, source, **kwargs)

    monkeypatch.setattr(groups, "publish_file", fail_second)
    with pytest.raises(OSError):
        dispatch(session, "group-apply", {"name": "family", "dry_run": False})
    assert [p.read_bytes() for p in paths] == originals
    assert not session.resolve(".vixl-groups/family.transaction.json").exists()

    def interrupted_rollback(path, source, **kwargs):
        if path in paths and (str(source).endswith(".before.vixl") or path == paths[1]):
            raise OSError("Simulated failed rollback")
        return publish(path, source, **kwargs)

    monkeypatch.setattr(groups, "publish_file", interrupted_rollback)
    with pytest.raises(OSError):
        dispatch(session, "group-apply", {"name": "family", "dry_run": False})
    assert dispatch(session, "group-show", {"name": "family"})["recovery_required"]
    monkeypatch.setattr(groups, "publish_file", publish)
    dispatch(session, "group-recover", {"name": "family"})
    assert [p.read_bytes() for p in paths] == originals


def test_plugin_dependency_cycle_and_pack_upgrade_cleanup(session):
    dispatch(session, "plugin-install", {"manifest": pack("parent")})
    child = pack("child")
    child["dependencies"] = {"parent": "1.0.0"}
    dispatch(session, "plugin-install", {"manifest": child})
    parent = pack("parent")
    parent["dependencies"] = {"child": "1.0.0"}
    with pytest.raises(VixlError, match="cycle"):
        dispatch(session, "plugin-install", {"manifest": parent, "replace": True})
    dispatch(session, "plugin-remove", {"name": "child"})
    parent = pack("parent", "2.0.0")
    parent["resources"]["palettes"] = {"parent-new": ["red", "blue"]}
    dispatch(session, "plugin-install", {"manifest": parent, "replace": True})
    names = dispatch(session, "resource-list", {"kind": "palettes"})["names"]
    assert "parent-new" in names and "parent-brand" not in names


def test_cli_workspace_resources_and_html(session, monkeypatch):
    from vixl.cli import main

    monkeypatch.chdir(session.workspace)
    dispatch(session, "shape-save", {"target": "artwork", "name": "saved"})
    assert main(["-p", "main.vixl", "shape-place", "saved", "--name", "placed"]) == 0
    assert main(["-p", "main.vixl", "export", "output.html"]) == 0
    assert session.resolve("output.html").read_bytes().startswith(b"<!doctype html>")


def test_named_palette_workspace_inheritance_and_custom_template(session):
    register("palettes", "global-palette", ["black", "white"])
    assert "global-palette" in dispatch(session, "resource-list", {"kind": "palettes"})["names"]
    dispatch(
        session, "resource-save", {"kind": "palettes", "name": "global-palette", "value": ["red", "blue"]}
    )
    session.apply({"type": "palette-apply", "name": "global-palette"})
    with session.project() as p:
        assert p.state["palettes"]["global-palette"] == ["red", "blue"]
    assert get("palettes", "global-palette") == ["black", "white"]


def test_modular_blanks_are_detected_then_can_be_filled():
    p = create_template("modular-card")
    assert p.check(checks=["blanks"])["errors"] > 0
    p.apply(
        [
            {"type": "text-set", "target": "slot-1/title", "text": "Ready"},
            {"type": "text-set", "target": "slot-1/body", "text": "Now available"},
        ]
    )
    assert p.check(checks=["blanks"])["errors"] == 0


def test_workflow_request_validation_and_workspace_branch_escape(session):
    for action, request in [
        ("group-apply", {"name": "no", "dry_run": "false"}),
        ("branch-fork", {"branch": "a", "output": "../outside.vixl"}),
        ("plugin-install", {"manifest": {"api_version": 1, "name": "invalid", "version": "1.0.0"}}),
    ]:
        with pytest.raises(VixlError):
            dispatch(session, action, request)
    assert not session.resolve(".vixl-resources.json").exists()


def test_mcp_exact_schemas_retain_geometric_paths(session):
    import asyncio
    from vixl.mcp_tools import build_server

    result = asyncio.run(
        build_server(session).call_tool("vixl_operation_schema", {"types": ["shape", "select", "pen"]})
    )
    text = str(result)
    assert '"path"' in text and '"nodes"' in text


def test_container_rules_are_available_as_persistent_tests():
    p = create_template("modular-card")
    assert p.check_suite("container-layout")["passed"]
    p.apply({"type": "move", "target": "slot-1/body", "x": -10})
    report = p.check_suite("container-layout")
    assert not report["passed"]
    assert {v["rule"] for v in report["results"][0]["violations"]} == {"contain", "vertical"}


def test_saved_resized_path_preserves_intrinsic_size(session):
    session.apply(
        {
            "type": "pen",
            "name": "curve",
            "points": [[0, 0], [40, 40]],
            "smooth": False,
            "width": 40,
            "height": 40,
        }
    )
    session.apply({"type": "resize", "target": "curve", "width": 20, "height": 20})
    dispatch(session, "shape-save", {"target": "curve", "name": "small-curve"})
    session.apply({"type": "shape-place", "resource": "small-curve", "name": "copy"})
    with session.project() as p:
        assert p.layer("copy")["path_view"] == [20, 20]
        assert "L20 20" in p.layer("copy")["path"]


def test_container_reflow_preserves_ids_and_refuses_overflow():
    p = create_template("modular-card")
    old_id = p.layer("slot-1/body")["id"]
    p.apply({"type": "text-set", "target": "slot-1/title", "text": "Hi"})
    p.apply({"type": "container-reflow", "target": "slot-1"})
    assert p.layer("slot-1/body")["id"] == old_id and p.check_suite("container-layout")["passed"]
    p.apply({"type": "text-set", "target": "slot-1/title", "text": "Too wide " * 100})
    before = deepcopy(p.state)
    with pytest.raises(VixlError, match="cannot satisfy"):
        p.apply({"type": "container-reflow", "target": "slot-1"})
    assert p.state == before


def test_custom_suite_file_and_studio_example(tmp_path):
    from pathlib import Path
    import runpy
    from vixl.commands import compile_command

    root = Path(__file__).resolve().parents[1]
    operation = compile_command(
        ["suite-set", "brand", "--file", str(root / "examples/studio/brand-suite.json")]
    )
    assert operation["suite"]["rules"][0]["kind"] == "palette"
    demo = runpy.run_path(str(root / "examples/build_studio_demo.py"))
    reports = demo["build"](tmp_path / "demo")
    assert all(report["passed"] for report in reports.values())
    assert (tmp_path / "demo/campaign.html").exists()


def test_workspace_branch_and_group_discovery_and_base_integrity(session):
    assert dispatch(session, "branch-list", {}) == {"branches": []}
    assert dispatch(session, "group-list", {}) == {"groups": []}
    manifest = dispatch(session, "branch-fork", {"branch": "art", "output": "art.vixl"})
    dispatch(session, "group-define", {"name": "team", "documents": ["main.vixl", "art.vixl"]})
    assert dispatch(session, "branch-list", {})["branches"][0]["branch"] == "art"
    assert dispatch(session, "group-list", {})["groups"][0]["name"] == "team"
    base = Project.load(session.resolve(manifest["base"]))
    base.apply({"type": "move", "target": "artwork", "x": 1})
    base.save()
    with pytest.raises(VixlError, match="base was changed"):
        dispatch(session, "branch-merge", {"branch": "art", "dry_run": False})
