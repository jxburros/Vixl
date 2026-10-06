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
    assert report["text_as_pixels"] == ["Title é"] and report["flattened_groups"] == ["turned"]
    assert "not editable type" in " ".join(report["warnings"])


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
