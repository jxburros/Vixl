"""Agent-experience fixes from one illustration session and one batch script (#794, #797-#802)."""

import asyncio
import io
import json
import shutil
import subprocess

import pytest
from PIL import Image, ImageChops

from vixl import Project, VixlError
from vixl.interfaces import Session
from vixl.mcp_tools import build_server


def call(server, tool, **arguments):
    """The JSON result of one MCP tool call and the images it returned."""
    content = asyncio.run(server.call_tool(tool, arguments))
    content = content[0] if isinstance(content, tuple) else content
    values = [json.loads(item.text) for item in content if getattr(item, "text", None)]
    images = [item for item in content if getattr(item, "data", None)]
    return (values[0] if values else None), images


def call_error(server, tool, **arguments):
    with pytest.raises(Exception) as raised:  # noqa: PT011 - the SDK's ToolError carries our JSON
        asyncio.run(server.call_tool(tool, arguments))
    message = str(raised.value)
    return json.loads(message[message.index("{"):])


@pytest.fixture
def server(tmp_path):
    made = build_server(Session(workspace=tmp_path))
    call(made, "vixl_document", action="create", path="a.vixl", width=1080, height=1080, background="#bde0fe",
         house_style="off")
    return made


SCENE = [
    {"type": "shape", "shape": "ellipse", "name": "wheel", "x": 240, "y": 620, "width": 200, "height": 200,
     "fill": "transparent", "stroke": "#1b1b1b", "stroke_width": 12},
    {"type": "shape", "shape": "rectangle", "name": "speed-lines", "x": 5, "y": 400, "width": 30, "height": 100,
     "fill": "#333333"},
]


# ---------------------------------------------------------------- #794 text width/height


def test_text_width_and_height_are_a_text_layout_box():
    one = Project(800, 600, "white")
    result = one.apply({"type": "text", "name": "bram-name", "text": "Bram", "x": 220, "y": 424, "size": 22,
                        "align": "center", "width": 180}, detail="compact")
    two = Project(800, 600, "white")
    two.apply([{"type": "text", "name": "bram-name", "text": "Bram", "x": 220, "y": 424, "size": 22, "align": "center"},
               {"type": "text-layout", "target": "bram-name", "width": 180}])
    keys = ("x", "y", "width", "height", "auto_size", "text_layout", "align")
    assert {k: one.layer("bram-name").get(k) for k in keys} == {k: two.layer("bram-name").get(k) for k in keys}
    assert one.layer("bram-name")["width"] == 180 and not one.layer("bram-name")["auto_size"]
    assert any("text-layout box" in note and "width 180" in note for note in result["normalized"])
    # The label is centred in its column, not at the left of it.
    ink = next(iter(result["changes"]["layers"].values()))["ink_bounds"]
    assert abs((ink[0] + ink[2] / 2) - (220 + 90)) < 1.5


def test_text_box_centres_wraps_and_edits_in_place():
    p = Project(800, 600, "white")
    p.apply({"type": "text", "name": "c", "text": "Centred words that wrap here", "x": "center", "y": "center",
             "size": 22, "width": 120, "height": 200})
    assert p.bounds("c") == (340.0, 200.0, 120.0, 200.0)  # centred as the box, not as the unwrapped line
    assert len(p.inspect("c")["baselines"]) > 1
    p.apply({"type": "text", "target": "c", "width": 300})
    assert p.layer("c")["text_layout"]["width"] == 300 and p.bounds("c")[2] == 300
    with pytest.raises(VixlError) as raised:  # text-set still points to text-layout
        p.apply({"type": "text-set", "target": "c", "width": 100})
    assert "text-layout" in str(raised.value)


def test_cli_text_takes_the_box(tmp_path, monkeypatch, capsys):
    from vixl.cli import main

    monkeypatch.chdir(tmp_path)
    Project(800, 600, "white").save(tmp_path / "a.vixl")
    main(["--json", "-p", "a.vixl", "text", "add", "Bram", "--name", "bram-name", "--x", "220", "--y", "424", "--size", "22",
          "--align", "center", "--width", "180"])
    capsys.readouterr()
    layer = Project.load(tmp_path / "a.vixl").layer("bram-name")
    assert layer["width"] == 180 and layer["text_layout"]["width"] == 180 and layer["align"] == "center"


# ---------------------------------------------------------------- #798 shapes, paths and the stroke advisory


def test_operations_reference_opens_with_shapes_by_kind(server):
    listing, _ = call(server, "vixl_reference", topic="operations")
    assert list(listing)[0] == "shapes"
    shapes = listing["shapes"]
    assert "not an operation type" in shapes["rule"] and "default to 0" in shapes["path"] and "pen" in shapes["pen_or_path"]
    kinds = {(op["type"], op.get("shape")) for op in shapes["examples"]}
    assert {("shape", "rectangle"), ("shape", "ellipse"), ("shape", "path"), ("pen", None)} <= kinds
    p = Project(1080, 1080, "white")
    p.apply(shapes["examples"])  # every listed example is a valid operation
    path = p.layer("frame")
    assert (path["x"], path["y"]) == (0, 0) and p.bounds("frame")[2:] == (700.0, 720.0)


def test_path_defaults_and_pen_are_documented_in_the_schema(server):
    schema, _ = call(server, "vixl_reference", topic="operations", name=["shape.path", "pen"])
    assert "x and y default to 0" in schema["shape.path"]["schema"]["description"]
    assert "use pen" in schema["shape.path"]["schema"]["description"]
    pen = schema["pen"]
    assert "canvas" in pen["properties"]["points"]["description"]
    assert pen["examples"] and all(example["type"] == "pen" for example in pen["examples"])
    p = Project(800, 600, "white")
    p.apply(pen["examples"])
    assert p.bounds("hill")[0] <= 0 and p.layer("hill")["shape"] == "path"


def test_guessed_paint_types_explain_that_they_are_fields(server):
    error = call_error(server, "vixl_apply", operations=[{"type": "fill", "color": "#ff0000"}])
    assert error["error"] == "unknown_operation" and error["suggestions"] == ["shape", "solid"]
    assert "field, not an operation" in error["message"] and "type: shape" in error["message"]
    # Shape kinds sent as the type keep working, reported under normalized.
    result, _ = call(server, "vixl_apply", operations=[{"type": "ellipse", "name": "dot", "x": 500, "y": 500,
                                                        "width": 40, "height": 40, "fill": "#111111"}])
    assert any("'ellipse' → 'shape'" in note for note in result["normalized"])


def test_stroke_width_advisory_reads_the_edited_layer():
    p = Project(800, 600, "white")
    p.apply([{"type": "shape", "shape": "path", "name": "beak", "path": "M 100 100 L 300 100 L 200 300 Z",
              "fill": "transparent", "stroke": "#000000", "stroke_width": 4},
             {"type": "shape", "shape": "rectangle", "name": "flat", "x": 400, "y": 100, "width": 100, "height": 100,
              "fill": "#888888"}])
    edited = p.apply({"type": "shape", "target": "beak", "stroke_width": 8,
                      "path": "M 100 100 L 320 100 L 200 300 Z"}, detail="compact")
    assert not edited.get("warnings")  # the layer already has a stroke colour
    unstroked = p.apply({"type": "shape", "target": "flat", "stroke_width": 8}, detail="compact")
    assert unstroked["warnings"] == ["operation: shape 'flat': stroke_width draws nothing without a stroke colour; add stroke"]
    created = p.apply({"type": "shape", "shape": "rectangle", "name": "new", "x": 600, "y": 100, "width": 50,
                       "height": 50, "fill": "#888888", "stroke_width": 3}, detail="compact")
    assert any("'new': stroke_width draws nothing" in warning for warning in created["warnings"])


# ---------------------------------------------------------------- #799 decoration and export verdicts


def test_role_on_creation_makes_the_safe_area_finding_informational(server):
    result, _ = call(server, "vixl_apply", operations=SCENE, check=True)
    finding = next(item for item in result["check"]["issues"] if item["rule"] == "safe_area.outside")
    assert finding["action"] == "review" and "role decoration" in finding["message"]
    assert result["outcome"]["state"] == "needs_review"
    marked, _ = call(server, "vixl_apply", check=True, operations=[
        {"type": "shape", "target": "speed-lines", "role": "decoration"},
        {"type": "shape", "shape": "rectangle", "name": "ground", "x": 0, "y": 1000, "width": 1080, "height": 120,
         "fill": "#7cb518", "role": "background"},
        {"type": "pen", "name": "streak", "points": [[2, 300], [40, 310], [10, 330]], "stroke": "#333333",
         "stroke_width": 3, "role": "decoration"}])
    assert marked["outcome"]["state"] == "validated", marked["outcome"]
    accepted = {name for item in marked["outcome"]["accepted"] for name in item["layers"]}
    assert {"speed-lines", "streak"} <= accepted
    inspected, _ = call(server, "vixl_document", target="ground")
    assert inspected["role"] == "background"
    # Text is content whatever it is called: role stays the type stage there.
    with pytest.raises(VixlError):
        Project(200, 200).apply({"type": "text", "text": "x", "role": "decoration"})


def test_export_takes_the_verdict_of_a_complete_check_of_the_same_revision(server):
    call(server, "vixl_apply", operations=[{**SCENE[0]}, {**SCENE[1], "role": "decoration"}])
    unchecked, _ = call(server, "vixl_export", path="out/unchecked.png")
    assert unchecked["outcome"]["state"] == "unvalidated" and unchecked["last_check"] in ("not_run", "stale")
    check, _ = call(server, "vixl_check")
    assert check["passed"] and check["outcome"]["state"] == "validated"
    exported, _ = call(server, "vixl_export", path="out/a.png")
    assert exported["outcome"]["state"] == "validated" and exported["outcome"]["review"] == "not_required"
    assert exported["outcome"]["validated_by"] == [f"design checks at {exported['last_check']['revision']}"]
    assert exported["last_check"] == {"revision": exported["last_check"]["revision"], "passed": True, "fix": 0,
                                      "review": 0, "complete": True}
    # An export of something the check did not see is not validated by it.
    variant, _ = call(server, "vixl_export", path="out/wheel.png", isolate=["wheel"])
    assert variant["outcome"]["validation"] == "not_run" and "isolate" in variant["outcome"]["review_reasons"][0]
    # A check of some checks or some layers cannot approve an export.
    call(server, "vixl_check", checks=["bounds"])
    partial, _ = call(server, "vixl_export", path="out/partial.png")
    assert partial["outcome"]["validation"] == "not_run" and "only some checks or layers" in partial["outcome"]["review_reasons"][0]
    call(server, "vixl_check", targets=["wheel"])
    assert call(server, "vixl_export", path="out/targets.png")[0]["outcome"]["validation"] == "not_run"
    # An edit makes the check stale.
    call(server, "vixl_check")
    call(server, "vixl_apply", operations=[{"type": "move", "target": "wheel", "x": 260}])
    stale, _ = call(server, "vixl_export", path="out/stale.png")
    assert stale["last_check"] == "stale" and stale["outcome"]["state"] == "unvalidated"


def test_export_reports_review_and_fix_findings_of_the_last_check(server):
    call(server, "vixl_apply", operations=SCENE, check=True)  # apply's check counts as the last check
    review, _ = call(server, "vixl_export", path="review.png")
    assert review["outcome"]["state"] == "needs_review" and review["outcome"]["validation"] == "passed"
    assert review["outcome"]["review_reasons"] == ["design check: 1 review finding(s) (safe_area.outside)"]
    assert [item["rule"] for item in review["last_check"]["top"]] == ["safe_area.outside"]
    call(server, "vixl_apply", check=True, operations=[
        {"type": "text", "name": "off", "text": "cut off by the edge", "x": 1000, "y": 500, "size": 60, "color": "#111111"}])
    failed, _ = call(server, "vixl_export", path="failed.png")
    assert failed["outcome"]["state"] == "validation_failed" and failed["last_check"]["fix"] >= 1


# ---------------------------------------------------------------- #800 response size


def test_sizes_reference_is_a_compact_index_until_filtered(server):
    index, _ = call(server, "vixl_reference", topic="sizes")
    assert len(json.dumps(index)) < 6000
    assert index["sizes"]["social"]["instagram-square"] == [1080, 1080] and "category='social'" in index["next"]
    assert "description" not in json.dumps(index["sizes"])
    square, _ = call(server, "vixl_reference", topic="sizes", name="square social")
    assert {item["name"] for item in square["sizes"]} == {"instagram-square", "instagram-post"}
    assert all(item["description"] for item in square["sizes"])
    by_pixels, _ = call(server, "vixl_reference", topic="sizes", name="1080x1080")
    assert {"instagram-square", "video-square"} <= {item["name"] for item in by_pixels["sizes"]}
    social, _ = call(server, "vixl_reference", topic="sizes", category="social")
    assert social["sizes"] and all(item["category"] == "social" for item in social["sizes"])


def test_ack_names_the_changed_layers_and_the_open_findings(server):
    ops = [{"type": "shape", "shape": "ellipse", "name": f"dot {i}", "x": 200 + 60 * i, "y": 500, "width": 40,
            "height": 40, "fill": "#333333"} for i in range(8)]
    ack, _ = call(server, "vixl_apply", operations=[*ops, SCENE[1]], check=True, detail="ack")
    assert ack["changed"] == 9 and ack["changed_layers"] == [*(f"dot {i}" for i in range(8)), "speed-lines"]
    assert ack["check"]["issues"] == [{"rule": "safe_area.outside", "action": "review", "layers": ["speed-lines"],
                                       "message": ack["check"]["issues"][0]["message"]}]
    assert "changes" not in ack and "changed_layers" in ack["untrusted"]
    assert len(json.dumps(ack)) < 1100
    # A changed (not added) layer is named too, and a clean check adds no issues.
    moved, _ = call(server, "vixl_apply", operations=[{"type": "move", "target": "dot 3", "x": 400},
                                                      {"type": "shape", "target": "speed-lines", "role": "decoration"}],
                    check=True, detail="ack")
    assert set(moved["changed_layers"]) == {"dot 3", "speed-lines"} and "issues" not in moved["check"]


def test_check_results_do_not_repeat_themselves(server):
    call(server, "vixl_apply", operations=SCENE)
    report, _ = call(server, "vixl_check")
    assert "summary" not in report and len(report["top"]) == 1  # one group: top already says it
    assert report["checked"]["checks"].startswith("default (") and report["checked"]["layers_total"] == 2
    assert report["verdict"].endswith("review findings still need attention")
    named, _ = call(server, "vixl_check", checks=["bounds", "safe_area"])
    assert named["checked"]["checks"] == ["bounds", "safe_area"]  # an explicit list is echoed
    applied, _ = call(server, "vixl_apply", operations=[{"type": "move", "target": "wheel", "x": 250}], check=True)
    assert applied["check"]["checked"]["checks"].startswith("default (")
    call(server, "vixl_apply", operations=[{"type": "shape", "target": "speed-lines", "role": "decoration"}])
    clean, _ = call(server, "vixl_check")
    assert clean["verdict"] == "Passed: no errors and no fix findings"
    # The Python report is unchanged: programs read the list and the summary.
    p = Project(300, 300)
    assert isinstance(p.check()["checked"]["checks"], list) and "summary" in p.check()


# ---------------------------------------------------------------- #801 where files go


def test_local_server_names_its_workspace_and_warns_about_ignored_sources(tmp_path):
    if shutil.which("git") is None:
        pytest.skip("needs git")
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / ".gitignore").write_text("*.vixl\n!design/*.vixl\n")
    session = Session(workspace=tmp_path)
    session.local = True
    local = build_server(session)
    created, _ = call(local, "vixl_document", action="create", path="pelican.vixl", width=200, height=200)
    assert created["workspace"] == str(tmp_path.resolve())
    assert created["git"].startswith("ignored") and ".gitignore" in created["git"]
    tracked, _ = call(local, "vixl_document", action="create", path="design/pelican.vixl", width=200, height=200)
    assert tracked["workspace"] == str(tmp_path.resolve()) and "git" not in tracked
    assert call(local, "vixl_document", action="open", path="pelican.vixl")[0]["workspace"] == str(tmp_path.resolve())
    assert call(local, "vixl_document", action="list")[0]["workspace"] == str(tmp_path.resolve())
    composed, _ = call(local, "vixl_apply", create={"path": "card.vixl", "width": 300, "height": 300}, check=False)
    assert composed["workspace"] == str(tmp_path.resolve()) and composed["git"].startswith("ignored")


def test_other_servers_keep_the_workspace_private(tmp_path):
    remote = build_server(Session(workspace=tmp_path))
    created, _ = call(remote, "vixl_document", action="create", path="a.vixl", width=200, height=200)
    assert "workspace" not in created and "git" not in created
    listing, _ = call(remote, "vixl_document", action="list")
    assert listing["workspace"] == "." and str(tmp_path) not in json.dumps(listing)
    from vixl.interfaces import mcp_server

    assert mcp_server.__kwdefaults__["local"] is False  # only the stdio CLI turns it on


# ---------------------------------------------------------------- #802 placement aid


def picture(item):
    import base64

    return Image.open(io.BytesIO(base64.b64decode(item.data))).convert("RGBA")


def test_rulers_and_bounds_label_document_coordinates_on_the_preview_only(server, tmp_path):
    call(server, "vixl_apply", operations=SCENE)
    _, plain = call(server, "vixl_render")
    info, aided = call(server, "vixl_render", rulers=True, bounds=True)
    assert info["rulers"] == {"step": 100, "from": [0, 0], "to": [1080, 1080]}
    assert info["bounds"] == [{"name": "wheel", "bounds": [240.0, 620.0, 200.0, 200.0]},
                              {"name": "speed-lines", "bounds": [5.0, 400.0, 30.0, 100.0]}]
    before, after = picture(plain[0]), picture(aided[0])
    assert before.size == after.size
    changed = ImageChops.difference(before, after).getbbox()
    assert changed is not None and changed[2] - changed[0] > before.width * 0.9  # grid lines span the preview
    # A grid line sits where its label says: x = 500 of 1080 on this preview.
    column = round(500 * after.width / 1080)
    assert after.getpixel((column, after.height // 2)) != before.getpixel((column, before.height // 2))
    # The aid never reaches an export or the document.
    exported, _ = call(server, "vixl_export", path="clean.png")
    with Image.open(tmp_path / "clean.png") as clean:
        assert clean.convert("RGBA").resize(before.size).getpixel((column, before.height // 2)) == \
            before.getpixel((column, before.height // 2))
    assert call(server, "vixl_document")[0]["layer_count"] == 2


def test_rulers_keep_absolute_coordinates_in_a_region_and_in_apply_previews(server):
    call(server, "vixl_apply", operations=SCENE)
    info, images = call(server, "vixl_render", rulers=50, bounds=["wheel"], region=[200, 600, 300, 300])
    assert info["rulers"] == {"step": 50, "from": [200, 600], "to": [500, 900]} and len(images) == 1
    assert info["bounds"] == [{"name": "wheel", "bounds": [240.0, 620.0, 200.0, 200.0]}]
    _, images = call(server, "vixl_apply", operations=[{"type": "move", "target": "wheel", "x": 250}],
                     preview={"rulers": True, "bounds": True})
    assert len(images) == 1
    assert call_error(server, "vixl_render", rulers=1)["field"] == "rulers"
    assert call_error(server, "vixl_render", bounds=["missing"])["error"] == "layer_not_found"
    assert call_error(server, "vixl_render", rulers=True, overlay=True)["field"] == "overlay"
    from vixl.feedback import ruler_step

    assert [ruler_step(span) for span in (64, 300, 1080, 4000)] == [10, 25, 100, 500]


def test_cli_render_draws_rulers_and_bounds(tmp_path, monkeypatch, capsys):
    from vixl.cli import main

    monkeypatch.chdir(tmp_path)
    p = Project(400, 300, "white")
    p.apply({"type": "shape", "shape": "ellipse", "name": "wheel", "x": 100, "y": 100, "width": 80, "height": 80,
             "fill": "#222222"})
    p.save(tmp_path / "a.vixl")
    main(["--json", "-p", "a.vixl", "render", "--out", "plain.png"])
    capsys.readouterr()
    main(["--json", "-p", "a.vixl", "render", "--out", "placed.png", "--show-rulers", "--show-bounds"])
    result = json.loads(capsys.readouterr().out)
    assert result["rulers"]["step"] == 50 and result["bounds"] == [{"name": "wheel", "bounds": [100.0, 100.0, 80.0, 80.0]}]
    with Image.open(tmp_path / "plain.png") as plain, Image.open(tmp_path / "placed.png") as placed:
        assert plain.size == placed.size == (400, 300)
        assert ImageChops.difference(plain.convert("RGBA"), placed.convert("RGBA")).getbbox() is not None
    main(["--json", "-p", "a.vixl", "render", "--out", "step.png", "--show-rulers", "100", "--show-bounds", "wheel"])
    assert json.loads(capsys.readouterr().out)["rulers"]["step"] == 100


# ---------------------------------------------------------------- #797 short guide


def test_guide_brief_is_the_first_step_only(server, capsys):
    from vixl.briefs import guide, quick_start
    from vixl.cli import main

    full = guide("a pelican riding a bicycle")
    short = quick_start(full, "a pelican riding a bicycle")
    assert len(json.dumps(short)) < len(json.dumps(full)) / 3
    assert short["first_step"] == full["approach"][0] and short["steps"] == len(full["approach"])
    assert "vixl guide a pelican riding a bicycle" in short["more"]
    poster = quick_start(guide("poster"), "poster")
    assert poster["create"]["size"] and poster["kind"] == "poster" and "direction" not in poster
    assert "first_step" in quick_start(guide(None)) and "text" in quick_start(guide("finishing"), "finishing")
    main(["--json", "guide", "--brief", "poster"])
    printed = json.loads(capsys.readouterr().out)
    assert printed["kind"] == "poster" and "layouts" not in printed
    main(["--json", "guide", "poster"])
    assert "layouts" in json.loads(capsys.readouterr().out)
    brief, _ = call(server, "vixl_reference", topic="a poster for a jazz night", options={"detail": "brief"})
    assert "first_step" in brief and "direction" not in brief and len(json.dumps(brief)) < 1500
