import json
import subprocess
import sys

import numpy as np
from PIL import Image
import pypdf
import pytest

from vixl import Project
from vixl.checks import check_design
from vixl.commands import compile_command
from vixl.errors import VixlError
from vixl.interfaces import Session
from vixl import links


def make_tile(path, text="Tile", fill="#336699", size=(200, 100)):
    tile = Project(*size, "#ffffff")
    tile.apply([
        {"type": "variable", "name": "who", "value": "world"},
        {"type": "solid", "name": "bg", "color": fill},
        {"type": "text", "name": "t", "text": text + " ${who}", "size": 28, "color": "white", "x": 8, "y": 30},
    ])
    tile.save(path)
    return tile


def host_at(tmp_path, name="host.vixl", size=(600, 300)):
    host = Project(*size, "#eeeeee")
    host.save(tmp_path / name)
    return host


def pixels(image):
    return np.asarray(image.convert("RGBA"), dtype=int)


def test_link_renders_the_source_like_an_image_layer(tmp_path):
    make_tile(tmp_path / "tile.vixl")
    host = host_at(tmp_path)
    host.apply({"type": "link", "source": "tile.vixl", "name": "tile", "x": 40, "y": 30})
    layer = host.layer("tile")
    assert layer["type"] == "link" and (layer["width"], layer["height"]) == (200, 100)
    assert layer["source"] == "tile.vixl" and layer["source_size"] == [200, 100] and len(layer["source_hash"]) == 64
    direct = Project.load(tmp_path / "tile.vixl").render()
    drawn = host.render().crop((40, 30, 240, 130))
    assert np.abs(pixels(drawn) - pixels(direct)).max() <= 1
    assert host.render().getpixel((5, 5))[:3] == (238, 238, 238)


def test_width_alone_keeps_the_source_aspect_and_scaled_render_stays_crisp(tmp_path):
    make_tile(tmp_path / "tile.vixl")
    host = host_at(tmp_path)
    host.apply({"type": "link", "source": "tile.vixl", "name": "big", "width": 400})
    assert (host.layer("big")["width"], host.layer("big")["height"]) == (400, 200)
    scaled = host.render().crop((0, 0, 400, 200))
    reference = Project.load(tmp_path / "tile.vixl")
    reference.apply([{"type": "canvas", "width": 400, "height": 200}, {"type": "resize", "target": "bg", "width": 400, "height": 200},
                     {"type": "text-set", "target": "t", "size": 56}, {"type": "move", "target": "t", "x": 16, "y": 60}])
    assert np.abs(pixels(scaled) - pixels(reference.render())).mean() < 2  # re-rendered at 2×, not enlarged pixels


def test_fit_modes_position_and_crop(tmp_path):
    src = Project(200, 100, "#ffffff")
    src.apply([{"type": "solid", "name": "l", "color": "#ff0000", "width": 100, "height": 100},
               {"type": "solid", "name": "r", "color": "#0000ff", "width": 100, "height": 100, "x": 100}])
    src.save(tmp_path / "halves.vixl")
    host = host_at(tmp_path, size=(300, 300))
    host.apply([{"type": "link", "source": "halves.vixl", "name": "fill", "width": 100, "height": 100, "fit": "fill"},
                {"type": "link", "source": "halves.vixl", "name": "fit", "x": 100, "width": 100, "height": 100, "fit": "fit"},
                {"type": "link", "source": "halves.vixl", "name": "stretch", "x": 200, "width": 100, "height": 100,
                 "fit": "stretch"},
                {"type": "link", "source": "halves.vixl", "name": "left", "y": 100, "width": 100, "height": 100,
                 "fit": "fill", "position": "left"},
                {"type": "link", "source": "halves.vixl", "name": "crop", "x": 100, "y": 100, "width": 100, "height": 100,
                 "crop": {"x": 100, "y": 0, "width": 100, "height": 100}}])
    image = host.render()
    red, blue = (255, 0, 0, 255), (0, 0, 255, 255)
    assert image.getpixel((20, 50)) == red and image.getpixel((80, 50)) == blue      # fill: centered, both halves cropped
    assert image.getpixel((150, 10)) == (238, 238, 238, 255) or image.getpixel((150, 10))[3] == 0  # fit: letterboxed
    assert image.getpixel((120, 50)) == red and image.getpixel((180, 50)) == blue   # fit: whole canvas, 2:1 inside 1:1
    assert image.getpixel((210, 50)) == red and image.getpixel((290, 50)) == blue   # stretch: distorted to the box
    assert image.getpixel((90, 150)) == red                                         # position left: the red half
    assert image.getpixel((110, 150)) == blue and image.getpixel((190, 250)) == (238, 238, 238, 255)
    assert host.layer("crop")["crop"] == [100, 0, 200, 100]
    assert image.getpixel((110, 110)) == blue and image.getpixel((190, 190)) == blue  # crop: only the blue half


def test_rotation_flip_opacity_and_effects_apply_like_any_layer(tmp_path):
    make_tile(tmp_path / "tile.vixl")
    host = host_at(tmp_path)
    host.apply([{"type": "link", "source": "tile.vixl", "name": "t", "x": 100, "y": 100},
                {"type": "rotate", "target": "t", "value": 90}, {"type": "opacity", "target": "t", "value": 0.5}])
    bounds = host.inspect("t")["resolved_bounds"]
    assert list(bounds[2:]) == [100, 200]
    inside = host.render().getpixel((112, 112))
    assert 130 < inside[0] < 160 and inside[2] > inside[0]  # half transparent blue over light grey
    host.apply({"type": "grayscale", "target": "t"})
    r, g, b, _ = host.render().getpixel((112, 112))
    assert abs(r - g) < 3 and abs(g - b) < 3


def test_variables_override_source_variables_and_read_host_variables(tmp_path):
    make_tile(tmp_path / "tile.vixl")
    host = host_at(tmp_path)
    host.apply([{"type": "variable", "name": "greeting", "value": "Vixl"},
                {"type": "link", "source": "tile.vixl", "name": "a", "variables": {"who": "${greeting}"}},
                {"type": "link", "source": "tile.vixl", "name": "b", "y": 120, "variables": {"who": "plain"}}])
    reference = Project.load(tmp_path / "tile.vixl")
    reference.state["variables"]["who"] = "Vixl"
    assert np.abs(pixels(host.render().crop((0, 0, 200, 100))) - pixels(reference.render())).max() <= 1
    assert host.render(variables={"greeting": "Other"}).crop((0, 0, 200, 100)).tobytes() != host.render().crop((0, 0, 200, 100)).tobytes()
    with pytest.raises(VixlError, match="Undefined variable"):
        host.apply({"type": "link-set", "target": "a", "variables": {"who": "${nope}"}})
        host.render()


def test_artboard_and_page_of_the_source(tmp_path):
    src = Project(400, 200, "#ffffff")
    src.apply([{"type": "solid", "name": "bg", "color": "#ff0000"},
               {"type": "artboard", "name": "square", "width": 100, "height": 100, "background": "#00ff00", "x": 1000, "y": 1000},
               {"type": "page", "action": "add", "name": "two"},
               {"type": "solid", "name": "bg2", "color": "#0000ff"},
               {"type": "page", "action": "select", "page": 1}])
    src.save(tmp_path / "multi.vixl")
    host = host_at(tmp_path, size=(500, 300))
    host.apply([{"type": "link", "source": "multi.vixl", "name": "first", "width": 100},
                {"type": "link", "source": "multi.vixl", "name": "second", "x": 150, "width": 100, "source_page": "two"},
                {"type": "link", "source": "multi.vixl", "name": "board", "x": 300, "artboard": "square"}])
    assert host.layer("board")["width"] == 100 and host.layer("second")["source_page"] == "two"
    image = host.render()
    assert image.getpixel((50, 25))[:3] == (255, 0, 0)
    assert image.getpixel((200, 25))[:3] == (0, 0, 255)
    assert image.getpixel((350, 50))[:3] == (0, 255, 0)
    for bad, message in (({"artboard": "nope"}, "no artboard 'nope'"), ({"source_page": "nope"}, "nope")):
        with pytest.raises(VixlError, match=message):
            host.apply({"type": "link", "source": "multi.vixl", **bad})
    plain = host_at(tmp_path, "plain.vixl")
    make_tile(tmp_path / "tile.vixl")
    with pytest.raises(VixlError, match="has no pages"):
        plain.apply({"type": "link", "source": "tile.vixl", "source_page": 2})


def test_source_changes_flow_into_renders_and_links_report_stale(tmp_path):
    make_tile(tmp_path / "tile.vixl", fill="#336699")
    host = host_at(tmp_path)
    host.apply({"type": "link", "source": "tile.vixl", "name": "t"})
    assert host.render().getpixel((190, 90))[:3] == (0x33, 0x66, 0x99)
    assert [item["state"] for item in links.status(host)] == ["ok"]
    make_tile(tmp_path / "tile.vixl", fill="#cc3300")
    assert host.render().getpixel((190, 90))[:3] == (0xCC, 0x33, 0x00)  # live: no refresh needed
    (item,) = links.status(host)
    assert item["state"] == "stale" and item["revision"] != item["recorded"] and "changed since" in item["message"]
    report = links.report(host)
    assert report["stale"] == 1 and report["count"] == 1
    host.apply({"type": "link-refresh"})
    assert [item["state"] for item in links.status(host)] == ["ok"]
    assert host.layer("t")["source_hash"] == links.status(host)[0]["revision"] + host.layer("t")["source_hash"][12:]


def test_missing_source_is_named_in_every_surface(tmp_path):
    make_tile(tmp_path / "tile.vixl")
    host = host_at(tmp_path)
    host.apply({"type": "link", "source": "tile.vixl", "name": "t"})
    (tmp_path / "tile.vixl").unlink()
    with pytest.raises(VixlError) as error:
        host.render()
    assert error.value.code == "link_missing" and "tile.vixl" in str(error.value) and str(tmp_path) in str(error.value)
    (item,) = links.status(host)
    assert item["state"] == "missing" and "tile.vixl" in item["message"]
    result = check_design(host)
    issues = [i for i in result["issues"] if i["check"] == "links"]
    assert result["passed"] is False and issues and "tile.vixl" in issues[0]["message"]
    with pytest.raises(VixlError, match="not found: nothing.vixl"):
        host.apply({"type": "link", "source": "nothing.vixl"})
    assert host.inspect()["links"][0]["state"] == "missing"


def test_stale_and_size_changes_show_up_in_check(tmp_path):
    make_tile(tmp_path / "tile.vixl")
    host = host_at(tmp_path)
    host.apply({"type": "link", "source": "tile.vixl", "name": "t"})
    assert [i for i in check_design(host)["issues"] if i["check"] == "links"] == []
    make_tile(tmp_path / "tile.vixl", size=(300, 100))
    issues = [i for i in check_design(host)["issues"] if i["check"] == "links"]
    assert {i["severity"] for i in issues} == {"warning"} and any("300×100" in i["message"] for i in issues)


def test_cycles_are_rejected_when_linking_and_when_drawing(tmp_path):
    a = make_tile(tmp_path / "a.vixl")
    b = make_tile(tmp_path / "b.vixl")
    a.apply({"type": "link", "source": "b.vixl", "name": "to-b"})
    a.save()
    with pytest.raises(VixlError) as error:
        b.apply({"type": "link", "source": "a.vixl", "name": "to-a"})
    assert error.value.code == "link_cycle" and "b.vixl → a.vixl → b.vixl" in str(error.value)
    with pytest.raises(VixlError, match="cannot link to itself"):
        a.apply({"type": "link", "source": "a.vixl"})
    # A cycle made behind the engine's back (editing the files) is still caught at render time.
    b.state["layers"].append({**a.state["layers"][-1], "id": "lyr_cycle", "name": "to-a", "source": "a.vixl"})
    b.save()
    with pytest.raises(VixlError) as error:
        Project.load(tmp_path / "a.vixl").render()
    assert error.value.code == "link_cycle" and "a.vixl → b.vixl → a.vixl" in str(error.value)
    assert links.status(Project.load(tmp_path / "a.vixl"))[0]["state"] == "cycle"


def test_chains_are_limited_in_depth(tmp_path):
    make_tile(tmp_path / "doc0.vixl")
    names = ["doc0.vixl"]
    for i in range(1, links.MAX_DEPTH + 1):
        doc = Project(200, 100, "#ffffff")
        doc.save(tmp_path / f"doc{i}.vixl")
        doc.apply({"type": "link", "source": names[-1], "name": "inner"})
        doc.save()
        names.append(f"doc{i}.vixl")
    deepest = Project.load(tmp_path / names[-1])
    assert deepest.render().size == (200, 100)  # exactly MAX_DEPTH levels of links
    too_deep = Project(200, 100, "#ffffff")
    too_deep.save(tmp_path / "too-deep.vixl")
    with pytest.raises(VixlError) as error:
        too_deep.apply({"type": "link", "source": names[-1], "name": "inner"})
    assert error.value.code == "link_depth" and "levels deep" in str(error.value)
    # A chain made by editing the file is refused when drawn, whatever is cached.
    too_deep.state["layers"].append({**deepest.state["layers"][-1], "id": "lyr_deep", "name": "inner", "source": names[-1]})
    too_deep.save()
    for _ in range(2):
        with pytest.raises(VixlError) as error:
            Project.load(tmp_path / "too-deep.vixl").render()
        assert error.value.code == "link_depth" and "doc0.vixl" in str(error.value)
    assert links.status(Project.load(tmp_path / "too-deep.vixl"))[0]["state"] == "error"


def test_services_keep_links_inside_the_workspace(tmp_path):
    workspace = tmp_path / "ws"
    workspace.mkdir()
    make_tile(workspace / "tile.vixl")
    make_tile(tmp_path / "outside.vixl")
    (workspace / "sub").mkdir()
    make_tile(workspace / "sub" / "deep.vixl")
    (workspace / "escape.vixl").symlink_to(tmp_path / "outside.vixl")
    session = Session(None, workspace=workspace)
    session.create("host.vixl", 400, 300)
    session.apply({"type": "link", "source": "sub/deep.vixl", "name": "deep"})
    session.apply({"type": "link", "source": "tile.vixl", "name": "ok", "y": 120})
    for source in ("../outside.vixl", str(tmp_path / "outside.vixl"), "escape.vixl", "sub/../../outside.vixl"):
        with pytest.raises(VixlError) as error:
            session.apply({"type": "link", "source": source, "name": "bad"})
        assert error.value.code == "forbidden" and "outside the workspace" in str(error.value)
    with pytest.raises(VixlError, match="Linked sources are .vixl documents"):
        session.apply({"type": "link", "source": "tile.png"})
    # `path` is a filesystem field services refuse; the link-specific alias maps onto the confined `source`.
    result = session.apply({"type": "link", "path": "tile.vixl", "name": "aliased", "y": 200})
    assert any("'path' → 'source'" in note for note in result["normalized"])
    with session.project() as project:
        assert project.allow_linked is False
        assert project.render().size == (400, 300)
        # A hand-edited document cannot make the service read outside either.
        project.layer("ok")["source"] = "../outside.vixl"
        with pytest.raises(VixlError) as error:
            project.render()
        assert error.value.code == "forbidden"
    # The Python/CLI opt-in permits outside files.
    opted = Project.load(workspace / "host.vixl", allow_linked=True)
    opted.state["layers"][0]["source"] = str(tmp_path / "outside.vixl")
    assert opted.render().size == (400, 300)


def test_embed_freezes_the_link_into_an_image(tmp_path):
    make_tile(tmp_path / "tile.vixl", fill="#336699")
    host = host_at(tmp_path)
    host.apply([{"type": "link", "source": "tile.vixl", "name": "t", "x": 10, "y": 10, "width": 100},
                {"type": "rotate", "target": "t", "value": 10}])
    before = host.render()
    host.apply({"type": "link-embed", "target": "t"})
    frozen = host.layer("t")
    assert frozen["type"] == "raster" and frozen["provenance"]["type"] == "linked-document"
    assert frozen["provenance"]["source"] == "tile.vixl" and "source" not in frozen and "source_hash" not in frozen
    assert np.abs(pixels(host.render()) - pixels(before)).max() <= 2
    assert "links" not in host.inspect()
    make_tile(tmp_path / "tile.vixl", fill="#cc3300")
    assert np.abs(pixels(host.render()) - pixels(before)).max() <= 2  # no longer follows the source
    with pytest.raises(VixlError, match="not a linked document layer"):
        host.apply({"type": "link-embed", "target": "t"})


def test_link_set_changes_settings_and_validates_against_the_source(tmp_path):
    make_tile(tmp_path / "a.vixl", fill="#ff0000")
    make_tile(tmp_path / "b.vixl", fill="#0000ff")
    host = host_at(tmp_path)
    host.apply({"type": "link", "source": "a.vixl", "name": "t", "variables": {"who": "x"}})
    host.apply({"type": "link-set", "target": "t", "source": "b.vixl", "fit": "fit", "position": [0, 1]})
    layer = host.layer("t")
    assert layer["source"] == "b.vixl" and layer["fit"] == "fit" and layer["position"] == [0, 1]
    assert host.render().getpixel((190, 90))[:3] == (0, 0, 255)
    host.apply({"type": "link-set", "target": "t", "variables": None, "crop": {"x": 0, "y": 0, "width": 100, "height": 50}})
    assert "variables" not in host.layer("t") and host.layer("t")["crop"] == [0, 0, 100, 50]
    host.apply({"type": "link-set", "target": "t", "crop": None})
    assert "crop" not in host.layer("t")
    with pytest.raises(VixlError, match="exceeds"):
        host.apply({"type": "link-set", "target": "t", "crop": {"x": 150, "y": 0, "width": 100, "height": 50}})
    with pytest.raises(VixlError, match="something to change"):
        host.apply({"type": "link-set", "target": "t"})
    with pytest.raises(VixlError, match="not a linked document layer"):
        host.apply([{"type": "solid", "name": "plain"}, {"type": "link-set", "target": "plain", "fit": "fit"}])
    with pytest.raises(VixlError):
        host.apply({"type": "link", "source": "a.vixl", "position": "middle-ish"})


def test_vector_pdf_keeps_linked_text_selectable(tmp_path):
    make_tile(tmp_path / "tile.vixl", text="Badge")
    host = host_at(tmp_path)
    host.apply([{"type": "link", "source": "tile.vixl", "name": "one", "x": 20, "y": 20},
                {"type": "link", "source": "tile.vixl", "name": "two", "x": 260, "y": 20, "width": 300,
                 "variables": {"who": "Ada"}},
                {"type": "link", "source": "tile.vixl", "name": "turned", "x": 100, "y": 180, "width": 100, "height": 50,
                 "variables": {"who": "Rot"}},
                {"type": "rotate", "target": "turned", "value": 15}])
    report = {}
    data = host.export(None, format="PDF", pdf_content="vector", report=report)
    assert report["raster_fallbacks"] == {} and report["fonts"] == 1
    text = pypdf.PdfReader(__import__("io").BytesIO(data)).pages[0].extract_text()
    assert "Badge world" in text and "Badge Ada" in text and "Badge Rot" in text
    import pypdfium2

    page = pypdfium2.PdfDocument(data)[0]
    drawn = np.asarray(page.render(scale=1).to_pil().convert("RGB"), dtype=int)
    reference = pixels(host.render())[:, :, :3]
    assert drawn.shape == reference.shape and np.abs(drawn - reference).mean() < 3


def test_opacity_and_effects_fall_back_to_images_in_pdf_and_svg(tmp_path):
    make_tile(tmp_path / "tile.vixl")
    host = host_at(tmp_path)
    host.apply([{"type": "link", "source": "tile.vixl", "name": "faded", "x": 10, "y": 10},
                {"type": "opacity", "target": "faded", "value": 0.5},
                {"type": "link", "source": "tile.vixl", "name": "blurred", "x": 300, "y": 10},
                {"type": "blur", "target": "blurred", "amount": 2}])
    report = {}
    host.export(None, format="PDF", pdf_content="vector", report=report)
    reasons = {item["layer"]: item["reason"] for item in report["raster_fallbacks"]["1"]}
    assert "opacity" in reasons["faded"] and reasons["blurred"] == "effects"
    svg = host.export(None, format="SVG").decode()
    assert "linked documents are exported as images" in svg and "<image" in svg
    with pytest.raises(VixlError, match="SVG requires raster"):
        host.export(None, format="SVG", svg_policy="strict")


def test_nested_links_render_and_stay_vector(tmp_path):
    make_tile(tmp_path / "tile.vixl", text="Inner")
    middle = Project(300, 150, "#dddddd")
    middle.save(tmp_path / "middle.vixl")
    middle.apply({"type": "link", "source": "tile.vixl", "name": "inner", "x": 50, "y": 25, "variables": {"who": "deep"}})
    middle.save()
    host = host_at(tmp_path)
    host.apply({"type": "link", "source": "middle.vixl", "name": "m", "x": 100, "y": 100})
    assert host.render().getpixel((340, 215))[:3] == (0x33, 0x66, 0x99)
    data = host.export(None, format="PDF", pdf_content="vector")
    assert "Inner deep" in pypdf.PdfReader(__import__("io").BytesIO(data)).pages[0].extract_text()
    # Changing the innermost source flows through both levels.
    make_tile(tmp_path / "tile.vixl", text="Inner", fill="#cc3300")
    assert host.render().getpixel((340, 215))[:3] == (0xCC, 0x33, 0x00)


def test_pages_and_group_membership_work_with_links(tmp_path):
    make_tile(tmp_path / "tile.vixl")
    host = host_at(tmp_path)
    host.apply([{"type": "page", "action": "add", "name": "one"},
                {"type": "link", "source": "tile.vixl", "name": "t", "x": 10, "y": 10},
                {"type": "page", "action": "add", "name": "two"},
                {"type": "link", "source": "tile.vixl", "name": "t2", "x": 20, "y": 20},
                {"type": "group", "name": "g", "targets": ["t2"]}])
    states = {item["layer"]: item.get("on_page") for item in links.status(host)}
    assert states == {"t2": "two", "t": "one"}
    assert host.render(page=1).getpixel((200, 100))[:3] == (0x33, 0x66, 0x99)
    data = host.export(None, format="PDF", pdf_content="vector")
    assert len(pypdf.PdfReader(__import__("io").BytesIO(data)).pages) == 2


def test_inspect_validation_and_save_round_trip(tmp_path):
    make_tile(tmp_path / "tile.vixl")
    host = host_at(tmp_path)
    host.apply({"type": "link", "source": "tile.vixl", "name": "t"})
    info = host.inspect()
    assert info["links"][0]["layer"] == "t" and info["layers"][0]["type"] == "link"
    host.save()
    again = Project.load(tmp_path / "host.vixl")
    assert again.layer("t")["source"] == "tile.vixl"
    again.state["layers"][0]["fit"] = "squish"
    from vixl.validation import check_state

    with pytest.raises(VixlError, match="Invalid link fit"):
        check_state(again, again.state)


def test_link_commands_compile_and_run_from_the_cli(tmp_path):
    op = compile_command("link tile.vixl --name hero --width 50% --x center --fit fit --position top-left "
                         "--crop 0,0,100,50 --artboard card --source-page 2 --set who=Ada --set n=3")
    assert op == {"type": "link", "source": "tile.vixl", "name": "hero", "width": "50%", "x": "center", "fit": "fit",
                  "position": "top-left", "crop": {"x": 0.0, "y": 0.0, "width": 100.0, "height": 50.0},
                  "artboard": "card", "source_page": 2, "variables": {"who": "Ada", "n": "3"}}
    assert compile_command("link-set hero --clear crop --clear source_page --position 0.25,0.75") == {
        "type": "link-set", "target": "hero", "position": [0.25, 0.75], "crop": None, "source_page": None}
    assert compile_command("link-refresh") == {"type": "link-refresh"}
    assert compile_command("link-embed hero") == {"type": "link-embed", "target": "hero"}

    def run(*args):
        return subprocess.run([sys.executable, "-m", "vixl", *args], cwd=tmp_path, capture_output=True, timeout=30)

    make_tile(tmp_path / "tile.vixl")
    assert run("new", "400x200", "-o", "card.vixl").returncode == 0
    done = run("link", "tile.vixl", "--name", "t", "--x", "20", "--y", "10", "--set", "who=CLI")
    assert done.returncode == 0, done.stderr
    listing = json.loads(run("links").stdout)
    assert listing["count"] == 1 and listing["links"][0]["state"] == "ok"
    assert run("export", "out.png").returncode == 0 and Image.open(tmp_path / "out.png").size == (400, 200)
    make_tile(tmp_path / "tile.vixl", fill="#ff0000")
    assert json.loads(run("links").stdout)["stale"] == 1
    assert run("link-refresh").returncode == 0
    assert json.loads(run("links").stdout)["links"][0]["state"] == "ok"
    (tmp_path / "tile.vixl").unlink()
    failed = run("export", "again.png", "--json")
    assert failed.returncode == 1 and json.loads(failed.stderr)["error"] == "link_missing"
    assert "tile.vixl" in json.loads(failed.stderr)["message"]


def test_workflow_links_action_over_mcp_and_rest(tmp_path):
    import asyncio

    from vixl.interfaces import mcp_server
    from vixl.workflows import describe

    assert "links" in describe()["actions"]
    make_tile(tmp_path / "tile.vixl")
    server = mcp_server(workspace=tmp_path)

    async def call(name, arguments):
        result = await server.call_tool(name, arguments)
        content = result[0] if isinstance(result, tuple) else result
        return json.loads("".join(getattr(item, "text", "") for item in content))

    asyncio.run(call("vixl_document_create", {"path": "a.vixl", "width": 300, "height": 200}))
    asyncio.run(call("vixl_operations_apply", {"operations": [{"type": "link", "source": "tile.vixl", "name": "t"}]}))
    listing = asyncio.run(call("vixl_workflow", {"action": "links", "request": {}}))
    assert listing["count"] == 1 and listing["links"][0]["state"] == "ok"
    make_tile(tmp_path / "tile.vixl", fill="#112233")
    assert asyncio.run(call("vixl_workflow", {"action": "links", "request": {}}))["stale"] == 1
    assert asyncio.run(call("vixl_operations_apply", {"operations": [{"type": "link-refresh"}]}))["success"]
    assert asyncio.run(call("vixl_workflow", {"action": "links", "request": {}}))["links"][0]["state"] == "ok"


def test_placement_geometry():
    layer = {"width": 100, "height": 50, "fit": "fill"}
    assert links.placement(layer, (200, 200)) == ((0, 0, 100, 50), (0, 50, 200, 150), 0.5)
    layer["position"] = [0, 0]
    assert links.placement(layer, (200, 200))[1] == (0, 0, 200, 100)
    layer.update(fit="fit", position=[1, 0.5])
    assert links.placement(layer, (200, 200)) == ((50, 0, 50, 50), (0, 0, 200, 200), 0.25)
    layer.update(fit="stretch", crop=[50, 50, 150, 100])
    assert links.placement(layer, (200, 200)) == ((0, 0, 100, 50), (50, 50, 150, 100), 1.0)
