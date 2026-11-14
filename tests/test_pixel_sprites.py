"""Sprites drawn, mirrored and laid out as a sheet inside Vixl (#791, #792), and images enlarged pixel by pixel
(#793)."""

import io
import json

import pytest
from PIL import Image

from vixl import Project
from vixl.errors import VixlError

PALETTE = {".": "transparent", "#": "#222222", "h": "#aa5500", "s": "#ffcc99"}


def sprite(project, rows=None, **fields):
    project.apply({"type": "pixel-art", "name": "hero", "palette": PALETTE, "shading": False, "outline": False,
                   **({"rows": rows} if rows else {"width": 8, "height": 8}), **fields})
    return project


def rows(project, target="hero"):
    return project.inspect_pixels(target)["rows"]


# ---------------------------------------------------------------------------------------------- #791 pixel-draw


def test_ellipse_is_filled_and_symmetric():
    p = sprite(Project(8, 8, "white"))
    p.apply({"type": "pixel-draw", "target": "hero", "tool": "ellipse", "x": 1, "y": 2, "width": 6, "height": 4,
             "color": "s"})
    assert rows(p) == ["........", "........", "..ssss..", ".ssssss.", ".ssssss.", "..ssss..", "........", "........"]
    q = sprite(Project(8, 8, "white"))
    q.apply({"type": "pixel-draw", "target": "hero", "tool": "ellipse", "x": 0, "y": 0, "width": 7, "height": 7,
             "color": "#"})
    drawn = rows(q)[:7]
    assert drawn == drawn[::-1] and all(row[:7] == row[:7][::-1] for row in drawn)
    assert drawn[0][:7] == "..###.." and drawn[3][:7] == "#######"


def test_ellipse_needs_its_box_inside_the_grid():
    p = sprite(Project(8, 8, "white"))
    with pytest.raises(VixlError, match="Ellipse requires width/height"):
        p.apply({"type": "pixel-draw", "target": "hero", "tool": "ellipse", "x": 1, "y": 1, "color": "s"})
    with pytest.raises(VixlError, match="outside grid"):
        p.apply({"type": "pixel-draw", "target": "hero", "tool": "ellipse", "x": 4, "y": 4, "width": 6, "height": 2,
                 "color": "s"})


def test_only_paints_the_cells_that_hold_the_listed_symbols():
    p = sprite(Project(4, 3, "white"), ["hhs.", "hss.", "...."])
    p.apply({"type": "pixel-draw", "target": "hero", "tool": "rect", "x": 0, "y": 0, "width": 4, "height": 3,
             "color": "#", "only": ["h"]})
    assert rows(p) == ["##s.", "#ss.", "...."]
    p.apply({"type": "pixel-draw", "target": "hero", "tool": "fill", "x": 3, "y": 0, "color": "s", "only": ["s"]})
    assert rows(p) == ["##s.", "#ss.", "...."]  # the flood region is transparent, which only leaves alone
    with pytest.raises(VixlError, match="only is a list of palette symbols"):
        p.apply({"type": "pixel-draw", "target": "hero", "x": 0, "y": 0, "color": "#", "only": ["q"]})


def test_pixel_transform_flips_the_stored_rows():
    p = sprite(Project(4, 3, "white"), ["h...", "hs..", "###."])
    p.apply({"type": "pixel-transform", "target": "hero", "flip": "horizontal"})
    assert rows(p) == ["...h", "..sh", ".###"]
    p.apply({"type": "pixel-transform", "target": "hero", "flip": "vertical"})
    assert rows(p) == [".###", "..sh", "...h"]
    p.apply({"type": "pixel-transform", "target": "hero", "flip": "both"})
    assert rows(p) == ["h...", "hs..", "###."]


def test_pixel_transform_shifts_drop_wrap_or_fill():
    start = ["h...", "hs..", "###."]
    p = sprite(Project(4, 3, "white"), start)
    p.apply({"type": "pixel-transform", "target": "hero", "shift": [1, 1]})
    assert rows(p) == ["....", ".h..", ".hs."]
    p = sprite(Project(4, 3, "white"), start)
    p.apply({"type": "pixel-transform", "target": "hero", "shift": [-1, 0], "fill": "s"})
    assert rows(p) == ["...s", "s..s", "##.s"]
    p = sprite(Project(4, 3, "white"), start)
    p.apply({"type": "pixel-transform", "target": "hero", "shift": [1, -1], "wrap": True})
    assert rows(p) == [".hs.", ".###", ".h.."]
    p.apply({"type": "pixel-transform", "target": "hero", "flip": "horizontal", "shift": [0, 9]})
    assert rows(p) == ["...."] * 3  # flip first, then a shift past the grid empties it


def test_pixel_transform_errors_name_the_field():
    p = Project(4, 3, "white")
    p.apply({"type": "pixel-art", "name": "solid", "palette": {"a": "red", "b": "blue"}, "rows": ["ab", "ba"]})
    with pytest.raises(VixlError, match="no transparent symbol") as caught:
        p.apply({"type": "pixel-transform", "target": "solid", "shift": [1, 0]})
    assert caught.value.details["field"] == "fill"
    with pytest.raises(VixlError):
        p.apply({"type": "pixel-transform", "target": "solid"})
    with pytest.raises(VixlError, match="wrap brings the cells back"):
        p.apply({"type": "pixel-transform", "target": "solid", "shift": [1, 0], "wrap": True, "fill": "a"})


def test_duplicate_then_transform_builds_a_mirrored_frame_and_fans_out_over_targets():
    p = sprite(Project(8, 3, "white"), ["h...", "hs..", "###."])
    p.apply([{"type": "duplicate", "target": "hero", "name": "hero-right"},
             {"type": "pixel-transform", "target": "hero-right", "flip": "horizontal"},
             {"type": "move", "target": "hero-right", "x": 4}])
    assert rows(p) == ["h...", "hs..", "###."] and rows(p, "hero-right") == ["...h", "..sh", ".###"]
    image = p.render().convert("RGB")
    assert image.getpixel((0, 0)) == image.getpixel((7, 0)) == (170, 85, 0)
    p.apply({"type": "pixel-transform", "targets": ["hero", "hero-right"], "shift": [0, 1]})
    assert rows(p)[0] == rows(p, "hero-right")[0] == "...."


def test_flipped_rows_keep_the_light_where_the_layer_flip_mirrors_it():
    art = ["..ssssss", "..ssssss", "..ssssss", "..ssssss", "..ssssss", "..ssssss"]
    p = Project(16, 6, "white")
    p.apply({"type": "pixel-art", "name": "a", "palette": PALETTE, "rows": art, "outline": False,
             "shading": {"light": "top-left"}})
    p.apply({"type": "pixel-transform", "target": "a", "flip": "horizontal"})
    drawn = p.inspect_pixels("a")["drawn"]["rows"]
    # The shadow band still sits on the right of the body (light from the top left), now next to the gap.
    assert drawn[2][5] != drawn[2][2] and drawn[2][5] != "." and drawn[2][0] == drawn[2][2]


# ---------------------------------------------------------------------------------------------- #792 sprite sheets


def sheet(clips=None):
    p = Project(10, 10, "transparent")
    p.apply({"type": "sprite-sheet", "cell": [8, 12], "rows": ["down", "left", "right", "up"], "columns": 4,
             **({"clips": clips} if clips is not None else {})})
    return p


def test_sprite_sheet_fits_the_canvas_and_places_sprites_by_cell():
    p = sheet()
    assert (p.state["canvas"]["width"], p.state["canvas"]["height"]) == (32, 48)
    p.apply([{"type": "pixel-art", "name": "left-2", "palette": PALETTE, "width": 8, "height": 12, "cell": ["left", 2]},
             {"type": "pixel-art", "name": "small", "palette": PALETTE, "width": 4, "height": 4, "x": 2, "y": 8,
              "cell": [3, 0]}])
    assert (p.layer("left-2")["x"], p.layer("left-2")["y"]) == (16, 12)
    assert (p.layer("small")["x"], p.layer("small")["y"]) == (2, 44)
    p.apply([{"type": "duplicate", "target": "left-2", "name": "right-2"},
             {"type": "move", "target": "right-2", "cell": ["right", 2]}])
    assert (p.layer("right-2")["x"], p.layer("right-2")["y"]) == (16, 24)


def test_cell_errors_say_what_is_available():
    p = sheet()
    with pytest.raises(VixlError, match="Unknown sheet row 'north'; rows: down, left, right, up"):
        p.apply({"type": "pixel-art", "palette": PALETTE, "width": 8, "height": 12, "cell": ["north", 0]})
    with pytest.raises(VixlError, match="columns 0-3"):
        p.apply({"type": "pixel-art", "palette": PALETTE, "width": 8, "height": 12, "cell": ["up", 4]})
    with pytest.raises(VixlError, match="does not fit the 8x12 cell"):
        p.apply({"type": "pixel-art", "palette": PALETTE, "width": 8, "height": 12, "x": 1, "cell": ["up", 0]})
    with pytest.raises(VixlError, match="no sprite sheet"):
        Project(8, 8, "white").apply({"type": "pixel-art", "palette": PALETTE, "cell": ["up", 0]})


def test_an_outlined_sprite_never_draws_outside_its_cell():
    p = sheet()
    full = ["s" * 8] * 12  # the silhouette touches every edge of its cell
    p.apply({"type": "pixel-art", "name": "frame", "palette": PALETTE, "rows": full, "outline": True,
             "cell": ["left", 1]})
    alpha = p.render().getchannel("A")
    assert alpha.getbbox() == (8, 12, 16, 24)
    inset = ["." * 8] + ["." + "s" * 6 + "."] * 10 + ["." * 8]
    p.apply({"type": "pixel-art", "name": "inset", "palette": PALETTE, "rows": inset, "outline": True,
             "cell": ["up", 3]})
    drawn = p.inspect_pixels("inset")["drawn"]["rows"]
    assert drawn[0][1:7] != "......"  # the outline is there, inside the cell
    assert p.render().getchannel("A").crop((0, 36, 32, 48)).getbbox() == (24, 0, 32, 12)


def test_sheet_export_writes_named_clips_with_frame_rectangles(tmp_path):
    p = sheet({"walk": {"duration": 120}, "idle": {"frames": [0], "loop": False},
               "wave": {"row": "down", "frames": [1, 2, 1], "durations": [80, 200, 80]}})
    p.apply({"type": "pixel-art", "name": "f", "palette": PALETTE, "rows": ["s" * 8] * 12, "cell": ["left", 2],
             "shading": False, "outline": False})
    result = p.export_animation(tmp_path / "hero.png", format="sheet", scale=2)
    assert result["layout"] == "grid" and result["size"] == [64, 96] and result["frame_size"] == [16, 24]
    assert result["clips"][:5] == ["walk-down", "walk-left", "walk-right", "walk-up", "idle-down"]
    image = Image.open(tmp_path / "hero.png")
    assert image.size == (64, 96) and image.getchannel("A").getbbox() == (32, 24, 48, 48)
    data = json.loads((tmp_path / "hero.json").read_text())
    assert data["format"] == "vixl-sprite-sheet" and data["image"] == "hero.png"
    assert data["cell"] == {"width": 16, "height": 24} and data["rows"] == ["down", "left", "right", "up"]
    clips = {clip["name"]: clip for clip in data["clips"]}
    assert clips["walk-left"]["frames"][2] == {"column": 2, "x": 32, "y": 24, "width": 16, "height": 24,
                                               "duration": 120}
    assert clips["walk-left"]["duration"] == 480 and clips["walk-left"]["loop"] is True
    assert clips["idle-up"]["frames"] == [{"column": 0, "x": 0, "y": 72, "width": 16, "height": 24, "duration": 100}]
    assert clips["idle-up"]["loop"] is False
    assert [frame["column"] for frame in clips["wave"]["frames"]] == [1, 2, 1] and clips["wave"]["duration"] == 360
    with pytest.raises(VixlError, match="already exists"):
        p.export_animation(tmp_path / "hero.png", format="sheet")


def test_sheet_without_clips_plays_each_row_and_aseprite_metadata_tags_them(tmp_path):
    p = sheet()
    p.export_animation(tmp_path / "a.png", format="sheet", metadata="aseprite")
    data = json.loads((tmp_path / "a.json").read_text())
    assert len(data["frames"]) == 16 and data["meta"]["size"] == {"w": 32, "h": 48}
    assert data["frames"][5] == {"filename": "left 1", "frame": {"x": 8, "y": 12, "w": 8, "h": 12}, "rotated": False,
                                 "trimmed": False, "spriteSourceSize": {"x": 0, "y": 0, "w": 8, "h": 12},
                                 "sourceSize": {"w": 8, "h": 12}, "duration": 100}
    assert data["meta"]["frameTags"][1] == {"name": "left", "from": 4, "to": 7, "direction": "forward"}


def test_sheet_declaration_is_checked_saved_and_removable(tmp_path):
    p = sheet({"walk": {}})
    with pytest.raises(VixlError, match="frames lists column indexes 0-3"):
        p.apply({"type": "sprite-sheet", "clips": {"walk": {"frames": [4]}}})
    with pytest.raises(VixlError, match="same name"):
        p.apply({"type": "sprite-sheet", "clips": {"walk": {}, "walk-up": {"row": "up"}}})
    with pytest.raises(VixlError, match="metadata chooses the JSON of a sprite-sheet grid"):
        Project(8, 8, "white").export_animation(tmp_path / "x.gif", metadata="aseprite")
    p.apply({"type": "sprite-sheet", "columns": 6})  # an update keeps the other fields and refits the canvas
    assert p.state["canvas"]["width"] == 48 and p.state["sprite_sheet"]["rows"][0] == "down"
    p.save(tmp_path / "hero.vixl")
    again = Project.load(tmp_path / "hero.vixl")
    assert again.state["sprite_sheet"] == p.state["sprite_sheet"]
    again.apply({"type": "canvas", "width": 50, "height": 48})
    with pytest.raises(VixlError, match="the sheet's grid is 48x48"):
        again.export_animation(tmp_path / "off.png", format="sheet")
    again.apply({"type": "sprite-sheet", "delete": True})
    assert "sprite_sheet" not in again.state


def test_frame_sheets_of_saved_frames_are_unchanged(tmp_path):
    p = sprite(Project(8, 8, "white"))
    p.apply([{"type": "frame-save", "name": "a"}, {"type": "frame-save", "name": "b"}])
    result = p.export_animation(tmp_path / "frames.png", format="sheet")
    assert "layout" not in result
    assert [frame["name"] for frame in json.loads((tmp_path / "frames.json").read_text())["frames"]] == ["a", "b"]


# ---------------------------------------------------------------------------------------------- #793 sampling


def checker():
    image = Image.new("RGBA", (2, 2))
    image.putdata([(255, 0, 0, 255), (0, 255, 0, 255), (0, 0, 255, 255), (255, 255, 0, 255)])
    stream = io.BytesIO()
    image.save(stream, "PNG")
    return stream.getvalue()


def colours(image, box):
    return len(image.crop(box).convert("RGB").getcolors(4096))


def test_import_with_scale_and_nearest_sampling_keeps_every_pixel_a_block():
    p = Project(16, 16, "white")
    result = p.import_image(data=checker(), name="sprite", scale=6, sampling="nearest")
    assert (result["width"], result["height"], result["sampling"]) == (12, 12, "nearest")
    assert p.layer("sprite")["sampling"] == "nearest"
    image = p.render().convert("RGB")
    assert colours(image, (0, 0, 12, 12)) == 4
    assert image.getpixel((5, 5)) == (255, 0, 0) and image.getpixel((6, 5)) == (0, 255, 0)
    smooth = Project(16, 16, "white")
    smooth.import_image(data=checker(), name="sprite", scale=6)
    assert colours(smooth.render(), (0, 0, 12, 12)) > 4


def test_scale_and_resize_take_sampling_and_the_layer_remembers_it(tmp_path):
    p = Project(32, 32, "white")
    p.import_image(data=checker(), name="sprite")
    p.apply({"type": "scale", "target": "sprite", "value": 4, "sampling": "nearest"})
    assert colours(p.render(), (0, 0, 8, 8)) == 4
    p.apply({"type": "resize", "target": "sprite", "width": 16})  # a later edit keeps the stored choice
    assert colours(p.render(), (0, 0, 16, 16)) == 4
    p.apply({"type": "rotate", "target": "sprite", "value": 90})
    assert colours(p.render(), (0, 0, 16, 16)) == 4
    p.save(tmp_path / "s.vixl")
    assert colours(Project.load(tmp_path / "s.vixl").render(), (0, 0, 16, 16)) == 4
    p.apply({"type": "resize", "target": "sprite", "width": 16, "height": 16, "sampling": "smooth"})
    assert "sampling" not in p.layer("sprite") and colours(p.render(), (0, 0, 16, 16)) > 4


def test_add_takes_scale_and_sampling_and_other_layers_refuse_it(tmp_path):
    (tmp_path / "c.png").write_bytes(checker())
    p = Project(16, 16, "white")
    p.apply({"type": "add", "path": str(tmp_path / "c.png"), "name": "sprite", "scale": 3, "sampling": "nearest"})
    assert (p.layer("sprite")["width"], p.layer("sprite")["sampling"]) == (6, "nearest")
    p.apply({"type": "shape", "name": "box", "shape": "rectangle", "width": 4, "height": 4})
    with pytest.raises(VixlError, match="sampling applies to image") as caught:
        p.apply({"type": "scale", "target": "box", "value": 2, "sampling": "nearest"})
    assert caught.value.details["field"] == "sampling"
    sprite(p).apply({"type": "scale", "target": "hero", "value": 2, "sampling": "nearest"})  # already nearest
    assert "sampling" not in p.layer("hero")


def test_a_group_of_nearest_images_and_sprites_scales_crisp():
    p = Project(32, 32, "white")
    p.import_image(data=checker(), name="sprite", sampling="nearest")
    p.apply([{"type": "group", "targets": ["sprite"], "name": "cast"},
             {"type": "scale", "target": "cast", "value": 8}])
    box = p.render().convert("RGB").getbbox()
    assert colours(p.render(), (0, 0, 16, 16)) == 4, box


@pytest.mark.parametrize("suffix", [".svg", ".pdf", ".pptx", ".png"])
def test_every_export_keeps_nearest_images_crisp(tmp_path, suffix):
    p = Project(16, 16, "white")
    p.import_image(data=checker(), name="sprite", scale=8, sampling="nearest")
    path = tmp_path / ("out" + suffix)
    p.export(path)
    data = path.read_bytes()
    if suffix == ".svg":
        text = data.decode()
        assert 'image-rendering="pixelated"' in text
        import base64
        import re

        embedded = Image.open(io.BytesIO(base64.b64decode(re.search(r'base64,([^"]+)"', text).group(1))))
        assert embedded.size == (16, 16) and colours(embedded, (0, 0, 16, 16)) == 4
        plain = Project(16, 16, "white")
        plain.import_image(data=checker(), name="sprite", scale=8)
        plain.export(tmp_path / "plain.svg")
        assert "pixelated" not in (tmp_path / "plain.svg").read_text()
    elif suffix == ".pptx":
        import zipfile

        with zipfile.ZipFile(path) as archive:
            media = [name for name in archive.namelist() if name.startswith("ppt/media/")]
            picture = Image.open(io.BytesIO(archive.read(media[0])))
        assert picture.size == (16, 16) and colours(picture, (0, 0, 16, 16)) == 4
    elif suffix == ".pdf":
        import pypdf

        (picture,) = pypdf.PdfReader(io.BytesIO(data)).pages[0].images
        assert picture.image.size == (16, 16) and colours(picture.image, (0, 0, 16, 16)) == 4
    else:
        assert colours(Image.open(path), (0, 0, 16, 16)) == 4


def test_an_agent_draws_places_and_exports_a_sheet_over_mcp(tmp_path):
    """The whole #791-#793 path through the MCP tools: no outside grid library, no hand-computed x/y, no Pillow."""
    import asyncio

    from vixl.interfaces import mcp_server

    (tmp_path / "portrait.png").write_bytes(checker())
    Project(8, 8, "transparent").save(tmp_path / "hero.vixl")

    async def run():
        server = mcp_server(tmp_path / "hero.vixl")
        await server.call_tool("vixl_apply", {"operations": [
            {"type": "sprite-sheet", "cell": [8, 8], "rows": ["left", "right"], "columns": 2},
            {"type": "pixel-art", "name": "left-0", "cell": ["left", 0], "width": 8, "height": 8, "palette": PALETTE,
             "shading": False, "outline": False},
            {"type": "pixel-draw", "target": "left-0", "tool": "ellipse", "x": 0, "y": 1, "width": 5, "height": 6,
             "color": "s"},
            {"type": "duplicate", "target": "left-0", "name": "right-0"},
            {"type": "pixel-transform", "target": "right-0", "flip": "horizontal"},
            {"type": "move", "target": "right-0", "cell": ["right", 0]},
            {"type": "import-image", "path": "portrait.png", "name": "portrait", "scale": 4, "sampling": "nearest"},
            {"type": "move", "target": "portrait", "cell": ["left", 1]},
        ]})
        await server.call_tool("vixl_export", {"kind": "animation", "path": "hero.png", "format": "sheet",
                                               "options": {"scale": 2, "metadata": "aseprite"}})

    asyncio.run(run())
    saved = Project.load(tmp_path / "hero.vixl")
    assert rows(saved, "right-0")[3] == "...sssss" and rows(saved, "left-0")[3] == "sssss..."
    assert saved.layer("portrait")["sampling"] == "nearest" and saved.layer("portrait")["x"] == 8
    sheet_image = Image.open(tmp_path / "hero.png")
    assert sheet_image.size == (32, 32) and colours(sheet_image, (16, 0, 32, 16)) == 4
    tags = json.loads((tmp_path / "hero.json").read_text())["meta"]["frameTags"]
    assert [tag["name"] for tag in tags] == ["left", "right"]
