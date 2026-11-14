"""Layered PSD export: structure read back with a small reader, composite opened by Pillow."""

import os
import struct
import subprocess
import sys

import numpy as np
import pytest
from PIL import Image

from vixl.errors import VixlError
from vixl.project import Project
from vixl.psd_export import packbits
from vixl.render import render


def parse(data):
    """A small PSD reader: header fields and layer records (bottom to top) with name, unicode name,
    box, blend key, opacity, visibility and section type."""
    view = memoryview(data)
    assert bytes(view[:4]) == b"8BPS"
    version, channels, height, width, depth, mode = struct.unpack(">H6xHIIHH", view[4:26])
    pos = 26
    pos += 4 + struct.unpack(">I", view[pos:pos + 4])[0]  # colour mode data
    pos += 4 + struct.unpack(">I", view[pos:pos + 4])[0]  # image resources
    pos += 4  # layer and mask information length
    info_length = struct.unpack(">I", view[pos:pos + 4])[0]
    pos += 4
    layers = []
    if info_length:
        count = abs(struct.unpack(">h", view[pos:pos + 2])[0])
        pos += 2
        for _ in range(count):
            top, left, bottom, right, nchannels = struct.unpack(">iiiiH", view[pos:pos + 18])
            pos += 18
            channel_info = [struct.unpack(">hI", view[pos + 6 * i:pos + 6 * i + 6]) for i in range(nchannels)]
            pos += 6 * nchannels
            signature, key, opacity, _, flags, _ = struct.unpack(">4s4sBBBB", view[pos:pos + 12])
            assert signature == b"8BIM"
            pos += 12
            extra = struct.unpack(">I", view[pos:pos + 4])[0]
            pos += 4
            end = pos + extra
            pos += 4 + struct.unpack(">I", view[pos:pos + 4])[0]  # layer mask data
            pos += 4 + struct.unpack(">I", view[pos:pos + 4])[0]  # blending ranges
            length = view[pos]
            name = bytes(view[pos + 1:pos + 1 + length]).decode("mac_roman")
            pos += (1 + length + 3) // 4 * 4
            record = {"name": name, "box": (left, top, right, bottom), "blend": key.decode("ascii"), "opacity": opacity,
                      "visible": not flags & 2, "channels": channel_info, "section": None}
            while pos < end:
                _, tag, size = struct.unpack(">4s4sI", view[pos:pos + 12])
                body = bytes(view[pos + 12:pos + 12 + size])
                if tag == b"luni":
                    chars = struct.unpack(">I", body[:4])[0]
                    record["unicode_name"] = body[4:4 + 2 * chars].decode("utf-16-be")
                elif tag == b"lsct":
                    record["section"] = struct.unpack(">I", body[:4])[0]
                elif tag == b"TySh":
                    record["type"] = body
                pos += 12 + size
            pos = end
            layers.append(record)
        for record in layers:
            planes = {}
            for ident, size in record["channels"]:
                planes[ident] = bytes(view[pos:pos + size])
                pos += size
            record["planes"] = planes
    return {"version": version, "channels": channels, "width": width, "height": height, "depth": depth, "mode": mode,
            "layers": layers}


def tree(layers):
    """Nest parsed records (bottom to top) into ``[{name, children?}]`` from top to bottom."""
    stack = [[]]
    for record in layers:
        if record["section"] == 3:
            stack.append([])
        elif record["section"] in (1, 2):
            members = stack.pop()
            stack[-1].append({"name": record.get("unicode_name", record["name"]), "children": members[::-1]})
        else:
            stack[-1].append({"name": record.get("unicode_name", record["name"])})
    return stack[0][::-1]


def unpackbits(data, length):
    out, i = bytearray(), 0
    while len(out) < length:
        n = data[i]
        i += 1
        if n < 128:
            out += data[i:i + n + 1]
            i += n + 1
        elif n > 128:
            out += bytes([data[i]]) * (257 - n)
            i += 1
    return bytes(out)


def layer_pixels(record):
    """Decode a parsed record's RLE channels into an RGBA array of its box."""
    left, top, right, bottom = record["box"]
    width, height = right - left, bottom - top
    result = np.zeros((height, width, 4), np.uint8)
    for ident, data in record["planes"].items():
        assert struct.unpack(">H", data[:2])[0] == 1
        counts = struct.unpack(f">{height}H", data[2:2 + 2 * height])
        offset = 2 + 2 * height
        for row, count in enumerate(counts):
            result[row, :, 3 if ident == -1 else ident] = np.frombuffer(unpackbits(data[offset:offset + count], width), np.uint8)
            offset += count
    return result


def poster():
    p = Project(240, 160, "#f1f5f9")
    p.apply([
        {"type": "shape", "shape": "rectangle", "name": "card", "x": 20, "y": 20, "width": 120, "height": 80, "fill": "#2563eb"},
        {"type": "shape", "shape": "ellipse", "name": "spot", "x": 100, "y": 40, "width": 80, "height": 80, "fill": "#f97316"},
        {"type": "blend", "target": "spot", "mode": "multiply"},
        {"type": "opacity", "target": "spot", "value": 0.5},
        {"type": "text", "name": "Title é", "text": "Hi", "size": 30, "color": "#111111", "x": 30, "y": 110},
        {"type": "shape", "shape": "rectangle", "name": "a", "x": 160, "y": 10, "width": 30, "height": 30, "fill": "red"},
        {"type": "shape", "shape": "rectangle", "name": "b", "x": 200, "y": 10, "width": 30, "height": 30, "fill": "green"},
        {"type": "group", "targets": ["a", "b"], "name": "badges"},
        {"type": "blend", "target": "b", "mode": "add"},
        {"type": "hide", "target": "a"},
        {"type": "shape", "shape": "rectangle", "name": "c", "x": 10, "y": 130, "width": 20, "height": 20, "fill": "black"},
        {"type": "shape", "shape": "rectangle", "name": "d", "x": 40, "y": 130, "width": 20, "height": 20, "fill": "black"},
        {"type": "group", "targets": ["c", "d"], "name": "turned"},
        {"type": "rotate", "target": "turned", "angle": 10},
        {"type": "drop-shadow", "target": "card"},
    ])
    return p


def test_packbits_round_trips_runs_and_literals():
    noise = np.random.default_rng(1).integers(0, 256, 999, dtype=np.uint8).tobytes()
    for row in (bytes(300), bytes(range(256)) + bytes(10), b"ab" * 5 + b"c" * 200 + b"xyz", noise, b"q"):
        assert unpackbits(packbits(row), len(row)) == row


def test_psd_layers_names_blends_groups_and_dimensions(tmp_path):
    p = poster()
    report = {}
    data = p.export(tmp_path / "poster.psd", report=report)
    assert (tmp_path / "poster.psd").read_bytes() == data
    psd = parse(data)
    assert (psd["width"], psd["height"], psd["depth"], psd["mode"], psd["channels"]) == (240, 160, 8, 3, 4)
    names = [r.get("unicode_name", r["name"]) for r in psd["layers"]]
    assert names == ["Background", "card", "spot", "Title é", "</Layer group>", "a", "b", "badges", "turned"]
    by_name = {r.get("unicode_name", r["name"]): r for r in psd["layers"]}
    assert by_name["spot"]["blend"] == "mul " and by_name["spot"]["opacity"] == 128
    assert by_name["b"]["blend"] == "lddg" and by_name["card"]["blend"] == "norm"
    assert by_name["a"]["visible"] is False and by_name["b"]["visible"] is True
    assert by_name["badges"]["section"] == 1 and by_name["</Layer group>"]["section"] == 3
    assert by_name["turned"]["section"] is None  # rotated as a whole: one pixel layer
    assert by_name["card"]["box"][2] > 140  # the drop shadow is part of the layer's pixels
    assert tree(psd["layers"])[1] == {"name": "badges", "children": [{"name": "b"}, {"name": "a"}]}
    assert report["layers"] == 7 and report["groups"] == 1
    title = next(layer for layer in p.state["layers"] if layer["name"] == "Title é")
    assert report["text_as_pixels"] == [{"layer": "Title é", "id": title["id"], "reason": "psd_text is pixels"}]
    assert "editable_text" not in report and report["flattened_groups"] == ["turned"]
    assert "not editable type" in " ".join(report["warnings"])
    # A default export is pixel layers only: no type-tool block anywhere in the file.
    assert b"TySh" not in data and all("type" not in record for record in psd["layers"])


def test_pillow_opens_the_composite_and_reads_the_layers(tmp_path):
    p = poster()
    p.export(tmp_path / "poster.psd")
    with Image.open(tmp_path / "poster.psd") as image:
        assert image.format == "PSD" and image.size == (240, 160)
        composite = np.asarray(image.convert("RGBA")).astype(int)
        assert len(image.layers) == 9
    assert np.abs(composite - np.asarray(render(p)).astype(int)).max() <= 1


def test_recompositing_the_layer_stack_reproduces_the_render(tmp_path):
    from vixl.render import composite

    BLENDS = {"norm": "normal", "mul ": "multiply", "lddg": "add", "scrn": "screen"}
    p = poster()
    psd = parse(p.export(tmp_path / "poster.psd"))
    size = (psd["width"], psd["height"])
    stack = [Image.new("RGBA", size)]
    for record in psd["layers"]:
        if record["section"] == 3:
            stack.append(Image.new("RGBA", size))
            continue
        if record["section"] == 1:
            tile = stack.pop()
        else:
            tile = Image.new("RGBA", size)
            if record["box"][2] > record["box"][0]:
                tile.paste(Image.fromarray(layer_pixels(record), "RGBA"), record["box"][:2])
        if not record["visible"]:
            continue
        tile.putalpha(tile.getchannel("A").point(lambda a: round(a * record["opacity"] / 255)))
        stack[-1] = composite(stack[-1], tile, BLENDS[record["blend"]])
    expected = np.asarray(render(p)).astype(int)
    assert np.abs(np.asarray(stack[0]).astype(int) - expected).max() <= 3


def test_layer_pixels_decode_to_the_layer_drawn_alone(tmp_path):
    p = Project(64, 48, "transparent")
    p.apply({"type": "shape", "shape": "rectangle", "name": "box", "x": 8, "y": 6, "width": 20, "height": 10, "fill": "#ff0000"})
    data = p.export(tmp_path / "box.psd")
    assert parse(data)["layers"][0]["box"] == (8, 6, 28, 16)
    pixels = layer_pixels(parse(data)["layers"][0])
    assert pixels.shape == (10, 20, 4) and (pixels == [255, 0, 0, 255]).all()
    with Image.open(tmp_path / "box.psd") as image:
        assert [(name, box) for name, _, box, _ in image.layers] == [("box", (8, 6, 28, 16))]


def test_psd_export_respects_overwrite_and_rejects_raster_only_options(tmp_path):
    p = poster()
    p.export(tmp_path / "x.psd")
    with pytest.raises(VixlError):
        p.export(tmp_path / "x.psd")
    p.export(tmp_path / "x.psd", overwrite=True)
    with pytest.raises(VixlError, match="PSD"):
        p.export(tmp_path / "y.psd", color_space="cmyk")


def test_rest_export_returns_psd(tmp_path):
    from fastapi.testclient import TestClient
    from vixl.interfaces import create_app

    poster().save(tmp_path / "api.vixl")
    response = TestClient(create_app(tmp_path / "api.vixl")).post("/export", json={"format": "PSD"})
    assert response.status_code == 200 and response.headers["content-type"] == "image/vnd.adobe.photoshop"
    assert len(parse(response.content)["layers"]) == 9


def test_export_file_and_cli_write_psd(tmp_path):
    from vixl.interfaces import Session
    from vixl.mcp_tools import export_file

    poster().save(tmp_path / "doc.vixl")
    session = Session(workspace=tmp_path)
    result = export_file(session, "out.psd", document="doc.vixl")
    assert result["format"] == "PSD" and result["layers"] == 7 and result["warnings"]
    with pytest.raises(VixlError, match="overwrite"):
        export_file(session, "out.psd", document="doc.vixl")
    env = {**os.environ, "PYTHONPATH": os.pathsep.join(sys.path)}
    run = subprocess.run([sys.executable, "-m", "vixl", "-p", str(tmp_path / "doc.vixl"), "export", str(tmp_path / "cli.psd")],
                         capture_output=True, text=True, env=env)
    assert run.returncode == 0, run.stderr
    assert parse((tmp_path / "cli.psd").read_bytes())["width"] == 240


# ------------------------------------------------------------------------------------- editable type layers

def type_document():
    p = Project(400, 300, "#ffffff")
    p.apply([
        {"type": "text", "name": "point", "text": "Hello (world)\nSecond \\ line", "x": 20, "y": 30, "size": 32,
         "color": "#ff0000"},
        {"type": "text", "name": "boxed", "text": "Box text that wraps around", "x": 20, "y": 150, "size": 20,
         "align": "center", "tracking": 2},
        {"type": "text-layout", "target": "boxed", "width": 150, "height": 100},
        {"type": "text", "name": "turned", "text": "Hi", "x": 300, "y": 40, "size": 40},
        {"type": "rotate", "target": "turned", "angle": 90},
        {"type": "text", "name": "inside", "text": "Hi", "x": 300, "y": 250, "size": 18, "align": "right"},
        {"type": "shape", "shape": "rectangle", "name": "r", "x": 280, "y": 240, "width": 10, "height": 10, "fill": "red"},
        {"type": "group", "targets": ["inside", "r"], "name": "grp"},
        {"type": "move", "target": "grp", "x": 200, "y": 220},
    ])
    return p


def test_plain_text_exports_as_type_layers_that_parse_back(tmp_path):
    from vixl.psd_text import parse_type_block

    report = {}
    psd = parse(type_document().export(tmp_path / "type.psd", report=report, psd_text="editable"))
    assert report["editable_text"] == ["point", "boxed", "turned", "inside"] and "text_as_pixels" not in report
    assert not report["warnings"]
    by_name = {r["name"]: r for r in psd["layers"]}
    point = parse_type_block(by_name["point"]["type"])
    assert point["text"] == "Hello (world)\nSecond \\ line"  # parentheses and backslashes survive the escaping
    assert point["font"] == "NotoSans-Regular" and point["size"] == 32 and point["color"] == "#ff0000"
    assert point["align"] == "left" and "box" not in point and point["leading"] > 20
    boxed = parse_type_block(by_name["boxed"]["type"])
    assert boxed["text"] == "Box text that wraps around" and boxed["box"] == (150, 100)
    assert boxed["align"] == "center" and boxed["tracking"] == 100  # 2 px at size 20, in thousandths of an em
    assert boxed["transform"] == (1, 0, 0, 1, 20, 150)  # box text starts at the box's corner
    # A type layer keeps the rendered pixels, so a reader without a text engine still shows the text.
    assert all(by_name[name]["box"][2] > by_name[name]["box"][0] for name in report["editable_text"])
    assert "type" not in by_name["r"]


def test_type_layer_origin_is_where_the_text_is_drawn(tmp_path):
    from vixl.psd_text import parse_type_block

    psd = parse(type_document().export(tmp_path / "type.psd", psd_text="editable"))
    by_name = {r["name"]: r for r in psd["layers"]}

    def origin(name):
        block = parse_type_block(by_name[name]["type"])
        return block["transform"], by_name[name]["box"]

    # Point text: the first baseline's start, at the left of the ink and inside its height.
    (xx, xy, yx, yy, tx, ty), (left, top, right, bottom) = origin("point")
    assert (xx, xy, yx, yy) == (1, 0, 0, 1) and abs(tx - left) <= 3 and top + 15 < ty < top + 32
    # Turned a quarter clockwise the baseline runs down the left edge of the ink, starting at its top.
    (xx, xy, yx, yy, tx, ty), (left, top, right, bottom) = origin("turned")
    assert max(abs(xx), abs(xy - 1), abs(yx + 1), abs(yy)) < 1e-9
    assert abs(tx - left) <= 2 and abs(ty - top) <= 4
    # Inside a moved group, right-aligned: the baseline's end, on the canvas (not in the group's coordinates).
    (xx, xy, yx, yy, tx, ty), (left, top, right, bottom) = origin("inside")
    assert abs(tx - right) <= 3 and abs(ty - bottom) <= 1.5 and left >= 200


def test_text_a_type_layer_cannot_carry_stays_pixels_with_a_reason(tmp_path):
    p = Project(400, 300, "#ffffff")
    p.apply([
        {"type": "text", "name": "shadow", "text": "Shadow", "x": 10, "y": 10, "size": 20},
        {"type": "drop-shadow", "target": "shadow"},
        {"type": "rich-text", "name": "rich", "x": 10, "y": 100, "width": 200, "height": 40,
         "spans": [{"text": "Bold ", "bold": True}, {"text": "plain"}]},
        {"type": "text", "name": "caps", "text": "Small Caps", "x": 10, "y": 180, "size": 20, "text_transform": "small-caps"},
        {"type": "text", "name": "warp", "text": "Warped", "x": 10, "y": 210, "size": 20},
        {"type": "text-layout", "target": "warp", "width": 200, "height": 60, "warp": "arc"},
        {"type": "text", "name": "clear", "text": "Clear", "x": 10, "y": 250, "size": 20, "color": "#ff000080"},
        {"type": "text", "name": "emoji", "text": "Hi \U0001F600", "x": 200, "y": 250, "size": 20},
        {"type": "text", "name": "plain", "text": "Plain", "x": 200, "y": 10, "size": 20},
        {"type": "text", "name": "upper", "text": "shout", "x": 200, "y": 60, "size": 20, "text_transform": "uppercase"},
    ])
    report = {}
    psd = parse(p.export(tmp_path / "mixed.psd", report=report, psd_text="editable"))
    assert report["editable_text"] == ["plain", "upper"]
    reasons = {item["layer"]: item["reason"] for item in report["text_as_pixels"]}
    assert set(reasons) == {"shadow", "rich", "caps", "warp", "clear", "emoji"}
    assert "styles" in reasons["shadow"] and "rich text" in reasons["rich"] and "small capitals" in reasons["caps"]
    assert "warp" in reasons["warp"] and "translucent" in reasons["clear"] and "emoji" in reasons["emoji"]
    ids = {layer["name"]: layer["id"] for layer in p.state["layers"]}
    assert all(item["id"] == ids[item["layer"]] for item in report["text_as_pixels"])  # each entry locates its layer
    assert "shadow (styles" in " ".join(report["warnings"])
    by_name = {r["name"]: r for r in psd["layers"]}
    assert all("type" not in by_name[name] for name in reasons) and "type" in by_name["plain"]
    from vixl.psd_text import parse_type_block

    assert parse_type_block(by_name["upper"]["type"])["text"] == "SHOUT"  # the text as it is drawn


def test_type_layers_are_opt_in_and_the_default_export_has_no_type_tool_block(tmp_path):
    p = type_document()
    report = {}
    data = p.export(tmp_path / "default.psd", report=report)
    assert b"TySh" not in data and all("type" not in record for record in parse(data)["layers"])
    assert "editable_text" not in report
    assert [item["reason"] for item in report["text_as_pixels"]] == ["psd_text is pixels"] * 4
    assert p.export(tmp_path / "pixels.psd", psd_text="pixels") == data  # the default, spelled out
    assert b"TySh" in p.export(tmp_path / "editable.psd", psd_text="editable")
    with pytest.raises(VixlError, match="psd_text"):
        p.export(tmp_path / "bad.psd", psd_text="vector")
    p.save(tmp_path / "doc.vixl")
    env = {**os.environ, "PYTHONPATH": os.pathsep.join(sys.path)}
    for flags, typed in (([], False), (["--psd-text", "editable"], True)):
        target = tmp_path / f"cli{len(flags)}.psd"
        run = subprocess.run([sys.executable, "-m", "vixl", "-p", str(tmp_path / "doc.vixl"), "export", str(target),
                              *flags], capture_output=True, text=True, env=env)
        assert run.returncode == 0, run.stderr
        assert (b"TySh" in target.read_bytes()) is typed
    from vixl.interfaces import Session
    from vixl.mcp_tools import export_file

    session = Session(workspace=tmp_path)
    result = export_file(session, "mcp.psd", document="doc.vixl")
    assert len(result["text_as_pixels"]) == 4 and "editable_text" not in result
    assert b"TySh" not in (tmp_path / "mcp.psd").read_bytes()
    result = export_file(session, "mcp2.psd", document="doc.vixl", psd_text="editable")
    assert result["editable_text"] == ["point", "boxed", "turned", "inside"]


def test_rest_export_writes_type_layers_only_on_request(tmp_path):
    from fastapi.testclient import TestClient
    from vixl.interfaces import create_app

    type_document().save(tmp_path / "api.vixl")
    client = TestClient(create_app(tmp_path / "api.vixl"))
    assert b"TySh" not in client.post("/export", json={"format": "PSD"}).content
    assert b"TySh" in client.post("/export", json={"format": "PSD", "psd_text": "editable"}).content


def test_colour_fonts_hand_set_text_and_inner_styles_stay_pixels(tmp_path):
    import hashlib

    from tests import color_font_helper as fonts

    p = Project(500, 400, "#ffffff")
    data = fonts.colr_v0()
    operations = [
        {"type": "text", "name": "hand", "text": "Hand set", "x": 10, "y": 10, "size": 30, "hand_set": {"seed": 3}},
        {"type": "text", "name": "inner", "text": "Inner", "x": 10, "y": 80, "size": 30},
        {"type": "layer-style", "target": "inner", "name": "inner-shadow", "settings": {}},
        {"type": "text", "name": "plain", "text": "Plain", "x": 10, "y": 150, "size": 30},
    ]
    asset = f"fonts/{hashlib.sha256(data).hexdigest()}.ttf"
    p.assets[asset] = data
    operations = [{"type": "font-register", "name": "color", "asset": asset},
                  {"type": "text", "name": "colour", "text": "AB", "font": "color", "x": 10, "y": 220, "size": 60},
                  *operations]
    p.apply(operations)
    report = {}
    exported = p.export(tmp_path / "new.psd", report=report, psd_text="editable")
    assert report["editable_text"] == ["plain"]
    reasons = {item["layer"]: item["reason"] for item in report["text_as_pixels"]}
    assert "hand set" in reasons["hand"] and "styles" in reasons["inner"]
    assert reasons["colour"] == "a colour font"
    assert exported.count(b"8BIMTySh") == 1


def test_engine_data_and_descriptors_round_trip():
    from vixl.psd_text import Malformed, Reader, descriptor, engine_data, long_value, object_value, parse_engine_data
    from vixl.psd_text import parse_type_block, read_descriptor, text_value, type_block, unit_value

    value = {"A": {"Text": "a (b) \\ c é 漢\r", "N": [1, 2.5, -3], "On": True, "Off": False},
             "List": [{"X": 1}, {"X": 2}], "Empty": [], "F": 0.583}
    assert parse_engine_data(engine_data(value)) == value
    data = descriptor(b"TxLr", [(b"Txt ", text_value("Hi")), (b"TextIndex", long_value(7)),
                                (b"bounds", object_value(b"bounds", [(b"Left", unit_value(1.5))]))])
    assert read_descriptor(Reader(data)) == {"Txt ": "Hi", "TextIndex": 7, "bounds": {"Left": 1.5}}
    block = type_block("One\nTwo", font="Example-Bold", size=18, color=(0, 128, 255), align="right")
    parsed = parse_type_block(block)
    assert parsed["text"] == "One\nTwo" and parsed["font"] == "Example-Bold" and parsed["color"] == "#0080ff"
    assert parsed["align"] == "right"
    # The fixed layout the specification gives: version 1, six doubles, text version 50, descriptor version 16.
    assert struct.unpack(">H", block[:2])[0] == 1 and struct.unpack(">HI", block[50:56]) == (50, 16)
    for cut in range(0, len(block) - 200, 37):
        with pytest.raises(Malformed):
            parse_type_block(block[:cut])
    with pytest.raises(Malformed):
        parse_engine_data(b"<< " * 100)


def test_type_layers_are_read_by_psd_tools(tmp_path):
    psd_tools = pytest.importorskip("psd_tools")
    import io

    document = psd_tools.PSDImage.open(io.BytesIO(type_document().export(tmp_path / "type.psd", psd_text="editable")))
    kinds = {layer.name: layer.kind for layer in document.descendants()}
    assert kinds["point"] == kinds["boxed"] == kinds["turned"] == kinds["inside"] == "type" and kinds["r"] == "pixel"
    point = next(layer for layer in document.descendants() if layer.name == "point")
    assert point.text == "Hello (world)\rSecond \\ line"
    sheet = point.engine_dict["StyleRun"]["RunArray"][0]["StyleSheet"]["StyleSheetData"]
    assert str(point.resource_dict["FontSet"][sheet["Font"]]["Name"]).strip("'") == "NotoSans-Regular"
    assert float(sheet["FontSize"]) == 32
