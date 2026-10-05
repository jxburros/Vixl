import asyncio
from copy import deepcopy
import io
import json
import shutil

from PIL import Image, ImageSequence
import pytest

from vixl import Project
from vixl.errors import VixlError

# Pixel layout of the test sprite: a coat (palette symbol Y) in a 8×8 grid, plus one leg pixel per pose.
COAT = ["........", ".YYYY...", ".YyyY...", ".YYYY...", "........", "........", "........", "........"]
PALETTE = {".": "transparent", "Y": "#f5c518", "y": "#c88a12", "L": "#202020"}
POSES = {  # frame name -> (duration, leg x)
    "idle1": (400, 1),
    "idle2": (400, 2),
    "walk1": (120, 3),
    "walk2": (120, 4),
    "walk3": (120, 5),
    "wave1": (250, 6),
}


def keeper():
    """An 8×8 document with a coat layer shared by every pose and a leg layer that moves per pose."""
    p = Project(8, 8, "transparent")
    p.apply(
        [
            {"type": "pixel-art", "name": "coat", "palette": PALETTE, "rows": COAT},
            {"type": "pixel-art", "name": "legs", "palette": PALETTE, "rows": ["L"], "x": 0, "y": 7},
        ]
    )
    for name, (duration, x) in POSES.items():
        p.apply({"type": "move", "target": "legs", "x": x})
        p.apply({"type": "frame-save", "name": name, "duration": duration})
    return p


def define(p):
    p.apply(
        [
            {"type": "animation-set", "name": "idle", "order": ["idle1", "idle2"]},
            {"type": "animation-set", "name": "walk", "order": ["walk1", "walk2", "walk3", "walk2"], "duration": 100},
            {"type": "animation-set", "name": "wave", "order": ["wave1", "walk1"], "durations": [250, 150], "loop": 3},
        ]
    )


def frames_of(path):
    image = Image.open(path)
    return [(frame.convert("RGBA").copy(), frame.info["duration"]) for frame in ImageSequence.Iterator(image)]


def coat_colour(p, name):
    return p.render_frame(name).getpixel((1, 1))


def test_named_animations_keep_their_own_order_timing_and_loop():
    p = keeper()
    define(p)
    info = p.inspect_animation()
    # The default animation (every saved frame, saved order) is untouched.
    assert [f["name"] for f in info["frames"]] == list(POSES) and info["total_duration"] == 1410
    animations = {a["name"]: a for a in info["animations"]}
    assert [f["name"] for f in animations["walk"]["frames"]] == ["walk1", "walk2", "walk3", "walk2"]
    assert [f["duration"] for f in animations["walk"]["frames"]] == [100] * 4
    assert animations["walk"]["total_duration"] == 400 and animations["walk"]["loop"] == 0
    # `durations` is per entry, `loop` is per animation, and a frame may play in several animations.
    assert [f["duration"] for f in animations["wave"]["frames"]] == [250, 150] and animations["wave"]["loop"] == 3
    # Without an override an entry plays for its saved frame's duration.
    p.apply({"type": "animation-set", "name": "idle", "loop": 2})
    assert [f["duration"] for f in p.inspect_animation()["animations"][0]["frames"]] == [400, 400]
    p.apply({"type": "animation-set", "name": "wave", "delete": True})
    assert [a["name"] for a in p.inspect_animation()["animations"]] == ["idle", "walk"]
    assert [f["name"] for f in p.inspect_animation()["frames"]] == list(POSES)


def test_one_document_exports_each_animation_separately(tmp_path):
    p = keeper()
    define(p)
    idle = p.export_animation(tmp_path / "keeper-idle.gif", animation="idle", scale=8)
    walk = p.export_animation(tmp_path / "keeper-walk.gif", animation="walk", scale=8)
    assert idle["animation"] == "idle" and walk["size"] == [64, 64]
    idle_frames = frames_of(tmp_path / "keeper-idle.gif")
    assert [d for _, d in idle_frames] == [400, 400] and Image.open(tmp_path / "keeper-idle.gif").info["loop"] == 0
    walk_frames = frames_of(tmp_path / "keeper-walk.gif")
    # walk1, walk2, walk3, walk2 at 100 ms each: the repeated frame is a real fourth frame.
    assert [d for _, d in walk_frames] == [100, 100, 100, 100]
    assert walk_frames[1][0].tobytes() == walk_frames[3][0].tobytes()
    assert walk_frames[0][0].tobytes() != walk_frames[1][0].tobytes()
    # Each frame is the nearest-neighbour enlargement of its saved frame.
    expected = p.render_frame("walk3", 8).convert("RGBA")
    assert walk_frames[2][0].tobytes() == expected.tobytes()
    # Without `animation` every saved frame still plays with its own duration, as before.
    p.export_animation(tmp_path / "all.gif")
    assert [d for _, d in frames_of(tmp_path / "all.gif")] == [d for d, _ in POSES.values()]
    # Looping follows the animation: APNG counts plays, so loop=3 extra repetitions is 4 plays.
    p.export_animation(tmp_path / "wave.png", animation="wave")
    assert Image.open(tmp_path / "wave.png").info["loop"] == 4
    with pytest.raises(VixlError, match="Unknown animation: wlak.*walk") as caught:
        p.export_animation(tmp_path / "bad.gif", animation="wlak")
    assert caught.value.details["suggestions"][0] == "walk"
    assert not (tmp_path / "bad.gif").exists()


def test_sprite_sheet_lists_every_frame_and_the_named_animations(tmp_path):
    p = keeper()
    define(p)
    p.export_animation(tmp_path / "sheet.png", format="sheet", columns=6)
    sheet = json.loads((tmp_path / "sheet.json").read_text())
    assert [f["name"] for f in sheet["frames"]] == list(POSES) and sheet["width"] == 48 and sheet["loop"] == 0
    assert sheet["frames"][2] == {"name": "walk1", "duration": 120, "x": 16, "y": 0, "width": 8, "height": 8}
    assert sheet["animations"]["walk"]["total_duration"] == 400
    assert [f["name"] for f in sheet["animations"]["walk"]["frames"]] == ["walk1", "walk2", "walk3", "walk2"]
    assert sheet["animations"]["wave"]["loop"] == 3
    # A sheet of one animation holds only its distinct frames, in order of first use.
    p.export_animation(tmp_path / "walk.png", format="sheet", animation="walk")
    walk = json.loads((tmp_path / "walk.json").read_text())
    assert [f["name"] for f in walk["frames"]] == ["walk1", "walk2", "walk3"]
    assert walk["animation"] == "walk" and list(walk["animations"]) == ["walk"]
    assert Image.open(tmp_path / "walk.png").size == (16, 16)
    # A document without named animations writes the sheet it always did.
    plain = keeper()
    plain.export_animation(tmp_path / "plain.png", format="sheet")
    assert "animations" not in json.loads((tmp_path / "plain.json").read_text())


def test_webp_export_is_lossless_for_crisp_pixels(tmp_path):
    p = keeper()
    define(p)
    result = p.export_animation(tmp_path / "idle.webp", animation="idle", scale=4)
    assert result["format"] == "webp" and result["size"] == [32, 32]
    frames = frames_of(tmp_path / "idle.webp")
    assert [d for _, d in frames] == [400, 400]
    for (image, _), name in zip(frames, ("idle1", "idle2")):
        assert image.tobytes() == p.render_frame(name, 4).tobytes()
    assert Image.open(tmp_path / "idle.webp").info["loop"] == 0
    with pytest.raises(VixlError, match="WEBP output filename"):
        p.export_animation(tmp_path / "idle.gif", format="webp")


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="MP4/WebM export needs ffmpeg")
def test_video_export_repeats_frames_on_a_common_tick(tmp_path):
    p = keeper()
    define(p)
    walk = p.export_animation(tmp_path / "walk.mp4", animation="walk", scale=4)
    assert (walk["frames"], walk["fps"], walk["duration"], walk["animation"]) == (4, 10.0, 400, "walk")
    assert (tmp_path / "walk.mp4").stat().st_size > 0
    # 400, 120 and 250 ms frames only share a 10 ms tick: 100 fps, 1410 ms is 141 frames.
    both = p.export_animation(tmp_path / "all.webm", scale=2)
    assert (both["fps"], both["frames"], both["duration"], both["format"]) == (100.0, 141, 1410, "webm")
    # Frames that agree on a coarser tick use it: 400 ms and 120 ms share 40 ms, so 25 fps.
    p.apply({"type": "animation-set", "name": "mixed", "order": ["idle1", "walk1"]})
    assert p.export_animation(tmp_path / "mixed.mp4", animation="mixed")["fps"] == 25.0
    with pytest.raises(VixlError, match="already exists"):
        p.export_animation(tmp_path / "walk.mp4", animation="walk")
    with pytest.raises(VixlError, match="Columns apply only"):
        p.export_animation(tmp_path / "x.mp4", columns=2)


def test_animation_set_errors_say_how_to_fix_them():
    p = keeper()
    before = deepcopy(p.state)
    cases = [
        ({"type": "animation-set", "order": ["idle1", "idle2"]}, "named animation"),
        ({"type": "animation-set", "name": "idel", "order": ["idle1", "idl2"]}, "did you mean 'idle2'"),
        ({"type": "animation-set", "name": "ghost", "loop": 1}, "pass order to define it"),
        ({"type": "animation-set", "name": "ghost", "delete": True}, "Unknown animation: ghost"),
        ({"type": "animation-set", "name": "a", "order": ["idle1"], "duration": 100, "durations": [100]}, "not both"),
        ({"type": "animation-set", "name": "a", "order": ["idle1", "idle2"], "durations": [100]}, "one value per frame"),
        ({"type": "animation-set", "name": "a", "order": ["idle1"], "duration": 15}, "multiple"),
        ({"type": "animation-set", "name": "bad name!", "order": ["idle1"]}, "Resource names"),
        ({"type": "animation-set", "duration": 100}, "pass name"),
        ({"type": "animation-set", "name": "a", "order": ["idle1"], "delete": True}, "cannot be combined"),
        ({"type": "animation-set", "name": "a", "order": []}, "at least|1–1024|non-empty|too short"),
    ]
    for op, message in cases:
        with pytest.raises(VixlError, match=message):
            p.apply(op)
        assert p.state == before
    # The guessed spelling `frames` is read as `order` and reported.
    result = p.apply({"type": "animation-set", "name": "idle", "frames": ["idle1", "idle2"]}, detail="compact")
    assert any("'frames' → 'order'" in note for note in result["normalized"])
    # A frame that a named animation plays cannot disappear underneath it.
    with pytest.raises(VixlError, match="used by animation.*idle"):
        p.apply({"type": "frame-delete", "name": "idle1"})
    p.apply([{"type": "animation-set", "name": "idle", "delete": True}, {"type": "frame-delete", "name": "idle1"}])
    assert "idle1" not in [f["name"] for f in p.inspect_animation()["frames"]]


def test_named_animations_persist_undo_and_replace_cleanly(tmp_path):
    p = keeper()
    define(p)
    p.save(tmp_path / "keeper.vixl")
    loaded = Project.load(tmp_path / "keeper.vixl")
    assert loaded.inspect_animation() == p.inspect_animation()
    # Redefining with an order replaces the animation, including its old timing.
    loaded.apply({"type": "animation-set", "name": "walk", "order": ["walk3", "walk1"]})
    walk = next(a for a in loaded.inspect_animation()["animations"] if a["name"] == "walk")
    assert [f["duration"] for f in walk["frames"]] == [120, 120]
    loaded.undo()
    assert loaded.inspect_animation() == p.inspect_animation()
    # Re-saving a frame in place keeps the animations that play it.
    loaded.apply({"type": "frame-save", "name": "walk2", "duration": 200})
    walk = next(a for a in loaded.inspect_animation()["animations"] if a["name"] == "walk")
    assert [f["duration"] for f in walk["frames"]] == [100] * 4
    # Documents saved before named animations existed still load and export unchanged.
    legacy = keeper()
    assert "animations" not in legacy.state["animation"]
    legacy.save(tmp_path / "legacy.vixl")
    assert Project.load(tmp_path / "legacy.vixl").inspect_animation() == legacy.inspect_animation()


def test_frames_edit_recolours_every_saved_frame_in_one_operation():
    p = keeper()
    assert {coat_colour(p, name) for name in POSES} == {(245, 197, 24, 255)}
    scene_before = deepcopy(p.layer("coat"))
    result = p.apply(
        {
            "type": "frames-edit",
            "operations": [
                {"type": "pixel-palette", "target": "coat", "colors": {"Y": "#d93a2b", "y": "#9c2320"}},
            ],
        },
        detail="compact",
    )
    assert result["changes"]["animation"]["changed"] == list(POSES)
    assert {coat_colour(p, name) for name in POSES} == {(217, 58, 43, 255)}
    assert p.render_frame("idle2").getpixel((2, 2)) == (156, 35, 32, 255)
    # Per-frame differences survive: each pose still has its own leg position.
    assert [p.render_frame(name).getpixel((x, 7))[3] for name, (_, x) in POSES.items()] == [255] * 6
    # The working scene is only edited on request.
    assert p.layer("coat") == scene_before
    p.apply({"type": "frames-edit", "scene": True, "operations": [{"type": "pixel-palette", "target": "coat", "colors": {"Y": "#00ff00"}}]})
    assert p.layer("coat")["palette"]["Y"] == "#00ff00"
    assert {coat_colour(p, name) for name in POSES} == {(0, 255, 0, 255)}


def test_frames_edit_can_target_an_animation_or_listed_frames():
    p = keeper()
    define(p)
    colour = {"type": "pixel-palette", "target": "coat", "colors": {"Y": "#0000ff"}}
    p.apply({"type": "frames-edit", "animation": "walk", "operations": [colour]})
    assert [coat_colour(p, name)[:3] for name in POSES] == [(245, 197, 24)] * 2 + [(0, 0, 255)] * 3 + [(245, 197, 24)]
    p.apply({"type": "frames-edit", "frames": ["idle1", "wave1"], "operations": [colour]})
    assert [coat_colour(p, name)[:3] for name in POSES] == [(0, 0, 255), (245, 197, 24)] + [(0, 0, 255)] * 4
    # Any operation works, not only palette swaps, and several can be batched per frame.
    p.apply(
        {
            "type": "frames-edit",
            "operations": [{"type": "opacity", "target": "coat", "value": 0.5}, {"type": "hide", "target": "legs"}],
        }
    )
    image = p.render_frame("walk1")
    assert image.getpixel((1, 1))[3] == 128 and image.getpixel((3, 7))[3] == 0


def test_frames_edit_is_atomic_and_names_the_failing_frame():
    p = keeper()
    # `wave-only` exists in the last frame alone, so the edit fails there after earlier frames succeeded.
    p.apply({"type": "pixel-art", "name": "wave-only", "rows": ["#"], "palette": {"#": "black"}})
    p.apply({"type": "frame-save", "name": "wave2", "duration": 100})
    before = deepcopy(p.state)
    with pytest.raises(VixlError, match="frame 'idle1'.*wave-only") as caught:
        p.apply({"type": "frames-edit", "operations": [{"type": "hide", "target": "wave-only"}]})
    assert caught.value.details["operation_index"] == 0 and p.state == before
    # A later operation in the same batch failing also discards the whole frames-edit.
    with pytest.raises(VixlError):
        p.apply(
            [
                {"type": "frames-edit", "operations": [{"type": "pixel-palette", "target": "coat", "colors": {"Y": "#000000"}}]},
                {"type": "frame-delete", "name": "ghost"},
            ]
        )
    assert p.state == before
    # A nested operation that breaks a frame's state (a palette symbol the pixels use) is rejected too.
    with pytest.raises(VixlError, match="frame"):
        p.apply({"type": "frames-edit", "frames": ["idle1"], "operations": [{"type": "pixel-palette", "target": "coat", "colors": {"Y": "not-a-colour"}}]})
    assert p.state == before
    dry = p.apply(
        {"type": "frames-edit", "frames": ["idle1"], "operations": [{"type": "pixel-palette", "target": "coat", "colors": {"Y": "#000000"}}]},
        dry_run=True,
    )
    assert dry["dry_run"] and p.state == before
    # Committed edits undo as one history step.
    p.apply({"type": "frames-edit", "operations": [{"type": "pixel-palette", "target": "coat", "colors": {"Y": "#000000"}}]})
    assert coat_colour(p, "idle1") == (0, 0, 0, 255)
    p.undo()
    assert p.state == before


def test_frames_edit_rejects_what_cannot_run_per_frame():
    p = keeper()
    before = deepcopy(p.state)
    cases = [
        ({"operations": [{"type": "frame-save", "name": "x"}]}, "cannot be nested"),
        ({"operations": [{"type": "frames-edit", "operations": [{"type": "hide", "target": "coat"}]}]}, "cannot be nested"),
        ({"operations": [{"type": "add", "path": "photo.png"}]}, "Filesystem fields"),
        ({"operations": [{"type": "layout-apply", "name": "hero-statement"}]}, "Layouts, templates"),
        ({"operations": [{"type": "hide", "target": "coat", "page": 2}]}, "Layouts, templates"),
        ({"operations": [{"type": "pixel-palette"}]}, "colors"),
        ({"operations": [{"type": "no-such-operation"}]}, "Unknown operation type"),
        ({"operations": [{"type": "hide", "target": "coat"}], "frames": ["idle1"], "animation": "x"}, "not both"),
        ({"operations": [{"type": "hide", "target": "coat"}], "frames": ["idel1"]}, "did you mean 'idle1'"),
        ({"operations": [{"type": "hide", "target": "coat"}], "animation": "nope"}, "Unknown animation"),
        ({"operations": []}, "non-empty"),
    ]
    for body, message in cases:
        with pytest.raises(VixlError, match=message):
            p.apply({"type": "frames-edit", **body})
        assert p.state == before
    empty = Project(4, 4)
    empty.apply({"type": "pixel-art", "name": "a", "rows": ["#"], "palette": {"#": "black"}})
    with pytest.raises(VixlError, match="Save at least one animation frame"):
        empty.apply({"type": "frames-edit", "operations": [{"type": "hide", "target": "a"}]})
    assert "animation" not in empty.state
    # `scene` alone is enough when no frames exist yet.
    empty.apply({"type": "frames-edit", "scene": True, "operations": [{"type": "hide", "target": "a"}]})
    assert empty.layer("a")["visible"] is False


def test_an_operation_with_its_own_operations_list_is_not_a_batch_wrapper():
    p = keeper()
    nested = {"type": "frames-edit", "frames": ["idle1"], "operations": [{"type": "hide", "target": "coat"}]}
    p.apply(nested)
    assert p.layer("coat")["visible"] is True  # only the frame changed, not the working scene
    assert p.render_frame("idle1").getpixel((1, 1))[3] == 0
    # The wrapper form still works.
    p.apply({"operations": [{"type": "hide", "target": "coat"}]})
    assert p.layer("coat")["visible"] is False


def test_cli_exposes_named_animations_and_frames_edit(tmp_path, monkeypatch, capsys):
    from vixl.cli import main

    monkeypatch.chdir(tmp_path)
    assert main(["new", "8x8", "-o", "k.vixl"]) == 0
    assert main(["pixel-art", "--name", "coat", "--palette", json.dumps(PALETTE), "--rows", json.dumps(COAT)]) == 0
    for name, x in (("one", 0), ("two", 1), ("three", 2)):
        assert main(["pixel-draw", "coat", "pixel", str(x), "0", "--color", "L"]) == 0
        assert main(["frame-save", name, "--duration", "100"]) == 0
    assert main(["animation-set", "--name", "pair", "--order", "one", "three", "--durations", "200", "300", "--loop", "1"]) == 0
    assert main(["animation-set", "--name", "solo", "--order", "two", "--duration", "50"]) == 0
    assert main(["animation-set", "--name", "solo", "--delete"]) == 0
    colours = json.dumps([{"type": "pixel-palette", "target": "coat", "colors": {"Y": "#123456"}}])
    assert main(["frames-edit", "--operations", colours, "--animation", "pair"]) == 0
    capsys.readouterr()
    assert main(["animation"]) == 0
    info = json.loads(capsys.readouterr().out)
    assert [a["name"] for a in info["animations"]] == ["pair"] and info["animations"][0]["total_duration"] == 500
    assert main(["export-animation", "--out", "pair.gif", "--animation", "pair", "--scale", "2"]) == 0
    assert json.loads(capsys.readouterr().out)["animation"] == "pair"
    assert [d for _, d in frames_of(tmp_path / "pair.gif")] == [200, 300] and Image.open("pair.gif").info["loop"] == 1
    assert main(["export-animation", "--out", "pair.webp", "--animation", "pair"]) == 0
    capsys.readouterr()
    p = Project.load(tmp_path / "k.vixl")
    assert [p.render_frame(name).getpixel((1, 1))[:3] for name in ("one", "two", "three")] == [
        (18, 52, 86),
        (245, 197, 24),
        (18, 52, 86),
    ]


def test_mcp_and_rest_reach_named_animations_and_frames_edit(tmp_path):
    from fastapi.testclient import TestClient
    import jsonschema

    from vixl.interfaces import create_app, mcp_server

    p = keeper()
    define(p)
    p.save(tmp_path / "keeper.vixl")

    async def run():
        server = mcp_server(tmp_path / "keeper.vixl")
        tools = {t.name: t for t in await server.list_tools()}
        schema = tools["vixl_operations_apply"].inputSchema
        jsonschema.validate(
            {
                "operations": [
                    {"type": "frames-edit", "animation": "walk", "operations": [{"type": "hide", "target": "legs"}]},
                    {"type": "animation-set", "name": "walk", "order": ["walk1"], "durations": [100]},
                ]
            },
            schema,
        )
        export = tools["vixl_export_animation"].inputSchema["properties"]
        assert {"animation", "quality"} <= export.keys() and "mp4" in export["format"]["enum"]
        await server.call_tool(
            "vixl_operations_apply",
            {
                "operations": [
                    {"type": "frames-edit", "operations": [{"type": "pixel-palette", "target": "coat", "colors": {"Y": "#ff0000"}}]}
                ]
            },
        )
        await server.call_tool("vixl_export_animation", {"path": "keeper-walk.gif", "animation": "walk", "scale": 4})
        await server.call_tool("vixl_export_animation", {"path": "keeper-idle.webp", "animation": "idle"})
        await server.call_tool("vixl_export_animation", {"path": "sheet.png", "format": "sheet"})
        inspected = await server.call_tool("vixl_animation_inspect", {})
        assert "animations" in json.dumps(inspected, default=str)

    asyncio.run(run())
    assert [d for _, d in frames_of(tmp_path / "keeper-walk.gif")] == [100] * 4
    assert [d for _, d in frames_of(tmp_path / "keeper-idle.webp")] == [400, 400]
    assert "walk" in json.loads((tmp_path / "sheet.json").read_text())["animations"]
    assert Project.load(tmp_path / "keeper.vixl").render_frame("wave1").getpixel((1, 1)) == (255, 0, 0, 255)

    client = TestClient(create_app(tmp_path / "keeper.vixl"))
    assert [a["name"] for a in client.get("/animation").json()["animations"]] == ["idle", "walk", "wave"]
    gif = client.post("/animation/export", json={"format": "gif", "animation": "idle", "scale": 2})
    assert [d for _, d in frames_of_bytes(gif.content)] == [400, 400]
    webp = client.post("/animation/export", json={"format": "webp", "animation": "walk"})
    assert webp.headers["content-type"] == "image/webp" and webp.content[:4] == b"RIFF"
    edit = client.post(
        "/operations",
        json={"operations": [{"type": "frames-edit", "frames": ["idle1"], "operations": [{"type": "hide", "target": "coat"}]}]},
    )
    assert edit.json()["changes"]["animation"]["changed"] == ["idle1"]
    # Service callers cannot read host files through the nested operations either.
    refused = client.post(
        "/operations",
        json={"operations": [{"type": "frames-edit", "operations": [{"type": "add", "path": "/etc/hostname"}]}]},
    )
    assert refused.status_code >= 400 and "Filesystem fields" in refused.text
    if shutil.which("ffmpeg"):
        video = client.post("/animation/export", json={"format": "mp4", "animation": "walk", "scale": 4})
        assert video.headers["content-type"] == "video/mp4" and video.content[4:8] == b"ftyp"


def frames_of_bytes(data):
    return [(frame.convert("RGBA"), frame.info["duration"]) for frame in ImageSequence.Iterator(Image.open(io.BytesIO(data)))]
