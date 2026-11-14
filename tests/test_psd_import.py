"""Layered PSD import: a third-party file, Vixl's own PSD round trip, and hostile files.

``tests/fixtures/psd/layered.psd`` was written by psd-tools (not by Vixl's writer): 96x64, 8-bit RGB, with a
half-opaque layer stored raw, a group at 80 % opacity holding a masked layer and a layer with a non-ASCII name, a
multiply layer and a hidden layer. ``layered-reference.png`` is psd-tools' own composite of that file.
"""

import asyncio
import os
import random
import struct
import subprocess
import sys
import tracemalloc
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from vixl import psd_reader
from vixl.errors import VixlError
from vixl.imports import import_document
from vixl.model import Limits
from vixl.project import Project
from vixl.psd_export import Record, write
from vixl.render import render

FIXTURES = Path(__file__).parent / "fixtures" / "psd"
LAYERED = (FIXTURES / "layered.psd").read_bytes()
EXPECTED = (VixlError,)


def empty():
    return Project(10, 10, "transparent")


def built(records, size=(40, 30)):
    """PSD bytes of ``records`` (bottom to top) from Vixl's writer, for cases a fixture does not cover."""
    return write(records, Image.new("RGBA", size, "#336699"))


def tile(width, height, colour):
    pixels = np.empty((height, width, 4), np.uint8)
    pixels[:] = colour
    return pixels


def patched(data, offset, fmt, *values):
    return data[:offset] + struct.pack(fmt, *values) + data[offset + struct.calcsize(fmt):]


def layer_count_offset(data):
    resources = struct.unpack(">I", data[30:34])[0]
    return 34 + resources + 8


def test_third_party_psd_imports_names_order_visibility_opacity_and_mask():
    p = empty()
    result = import_document(p, LAYERED, "psd")
    assert result["mode"] == "layers" and result["canvas"] == "adopted" and result["size"] == [96, 64]
    assert result["layers"] == {"image": 6, "group": 1} and "not_applied" not in result
    canvas = p.state["canvas"]
    assert (canvas["width"], canvas["height"]) == (96, 64)
    layers = {layer["name"]: layer for layer in p.state["layers"]}
    top_level = [layer["name"] for layer in p.state["layers"] if not layer.get("parent")]
    assert top_level == ["Sky", "Sun", "Ground", "Shade", "Hidden note"]  # bottom to top, as in the file
    ground = layers["Ground"]
    assert ground["type"] == "group" and ground["opacity"] == pytest.approx(0.8)
    members = [layer["name"] for layer in p.state["layers"] if layer.get("parent") == ground["id"]]
    assert members == ["Hill", "Rock é"]
    assert layers["Sun"]["opacity"] == pytest.approx(128 / 255, abs=1e-3)
    assert layers["Shade"]["blend"] == "multiply" and layers["Sky"]["blend"] == "normal"
    assert layers["Hidden note"]["visible"] is False and layers["Sky"]["visible"] is True
    assert (layers["Sun"]["x"], layers["Sun"]["y"]) == (58, 6)
    # The hill's triangular mask is the layer's mask; a mask that shows everything (the writer adds one to every
    # layer) is not kept.
    mask = layers["Hill"]["mask"]
    assert mask and mask["enabled"] and not layers["Sky"]["mask"] and not layers["Rock é"]["mask"]
    shape = np.asarray(p.image(mask["asset"], "L"))
    assert shape.shape == (24, 60) and shape[23, 30] == 255 and shape[0, 0] == 0
    reference = np.asarray(Image.open(FIXTURES / "layered-reference.png").convert("RGBA")).astype(int)
    assert np.abs(np.asarray(render(p)).astype(int) - reference).max() <= 2


def test_import_is_one_revision_and_undo_removes_it():
    p = empty()
    before = len(p.nodes)
    import_document(p, LAYERED, "psd")
    assert len(p.nodes) == before + 1
    assert p.find_layer("Hill")["mask"]
    p.undo()
    assert not p.state["layers"]
    p.redo()
    assert p.find_layer("Hill")["mask"]  # the mask is part of the revision, not an edit after it


def test_vixl_psd_round_trips_with_matching_render_and_reported_text(tmp_path):
    source = Project(240, 160, "#f1f5f9")
    source.apply([
        {"type": "shape", "shape": "rectangle", "name": "card", "x": 20, "y": 20, "width": 120, "height": 80, "fill": "#2563eb"},
        {"type": "shape", "shape": "ellipse", "name": "spot", "x": 100, "y": 40, "width": 80, "height": 80, "fill": "#f97316"},
        {"type": "blend", "target": "spot", "mode": "multiply"},
        {"type": "opacity", "target": "spot", "value": 0.5},
        {"type": "text", "name": "Title é", "text": "Hi there", "size": 30, "color": "#111111", "x": 30, "y": 110},
        {"type": "shape", "shape": "rectangle", "name": "a", "x": 160, "y": 10, "width": 30, "height": 30, "fill": "red"},
        {"type": "shape", "shape": "rectangle", "name": "b", "x": 200, "y": 10, "width": 30, "height": 30, "fill": "green"},
        {"type": "group", "targets": ["a", "b"], "name": "badges"},
        {"type": "opacity", "target": "badges", "value": 0.6},
        {"type": "hide", "target": "a"},
    ])
    data = source.export(tmp_path / "poster.psd")
    p = empty()
    result = import_document(p, data, "psd")
    names = [layer["name"] for layer in p.state["layers"] if not layer.get("parent")]
    assert names == ["Background", "card", "spot", "Title é", "badges"]
    assert p.find_layer("a")["visible"] is False and p.find_layer("badges")["opacity"] == pytest.approx(0.6)
    assert p.find_layer("spot")["blend"] == "multiply"
    assert result["text"] == [{"layer": "Title é", "text": "Hi there", "font": "NotoSans-Regular", "size": 30.0,
                               "color": "#111111"}]
    assert "type layer" in " ".join(result["warnings"])
    difference = np.abs(np.asarray(render(p)).astype(int) - np.asarray(render(source)).astype(int))
    assert difference.max() <= 3


def test_import_into_a_document_with_layers_adds_one_group_and_keeps_the_canvas():
    p = Project(200, 100, "#ffffff")
    p.apply({"type": "shape", "shape": "rectangle", "name": "Sky", "x": 0, "y": 0, "width": 10, "height": 10, "fill": "red"})
    result = import_document(p, LAYERED, "psd", "artwork")
    assert result["canvas"] == "kept" and result["group"] == "artwork"
    assert (p.state["canvas"]["width"], p.state["canvas"]["height"]) == (200, 100)
    group = p.find_layer("artwork")
    tops = [layer["name"] for layer in p.state["layers"] if layer.get("parent") == group["id"]]
    assert tops == ["Sky 2", "Sun", "Ground", "Shade", "Hidden note"]  # a taken name gets a number


def test_appearance_mode_and_flat_files_import_the_merged_image():
    p = empty()
    result = import_document(p, LAYERED, "psd", "flat", svg_mode="appearance")
    assert result["mode"] == "appearance" and [layer["name"] for layer in p.state["layers"]] == ["flat"]
    assert np.asarray(render(p)).shape == (64, 96, 4)
    flat = built([])
    p = empty()
    result = import_document(p, flat, "psd")
    assert result["mode"] == "appearance" and "no pixel layers" in result["warnings"][0]
    assert (np.asarray(render(p))[:, :, :3] == (0x33, 0x66, 0x99)).all()


def test_features_the_pixels_do_not_carry_are_reported(monkeypatch):
    from vixl import psd_export

    monkeypatch.setitem(psd_export.BLEND_KEYS, "pass", b"pass")
    monkeypatch.setitem(psd_export.BLEND_KEYS, "hue", b"hue ")
    red = tile(10, 10, (255, 0, 0, 255))
    data = built([
        Record("base", pixels=tile(40, 30, (200, 200, 200, 255)), box=(0, 0, 40, 30)),
        Record(psd_export.GROUP_END, section=3),
        Record("darken me", pixels=red, box=(5, 5, 15, 15), blend="multiply"),
        Record("Through", section=1, blend="pass"),
        Record("tinted", pixels=red, box=(20, 5, 30, 15), blend="hue"),
        Record("levels", pixels=red, box=(0, 0, 10, 10), type_data=bytes(8)),
        Record(psd_export.GROUP_END, section=3),
        Record("Nothing", section=1),
        Record("blank"),
    ])
    data = data.replace(b"8BIMTySh", b"8BIMlevl")
    p = empty()
    result = import_document(p, data, "psd")
    reasons = {item["layer"]: item["reason"] for item in result["not_applied"]}
    assert "pass-through" in reasons["Through"] and "'hue'" in reasons["tinted"]
    assert "levels adjustment" in reasons["levels"] and "empty group" in reasons["Nothing"]
    assert "empty layer" in reasons["blank"]
    assert [layer["name"] for layer in p.state["layers"] if not layer.get("parent")] == ["base", "Through", "tinted"]
    assert "appearance" in " ".join(result["warnings"])
    # A byte-reversed blend key (ImageMagick writes "mron" for "norm") is read as the key it is.
    swapped = built([Record("only", pixels=red, box=(0, 0, 10, 10))]).replace(b"8BIMnorm", b"8BIMmron")
    assert "not_applied" not in import_document(empty(), swapped, "psd")


@pytest.mark.parametrize("offset, fmt, value, code", [
    (4, ">H", 2, "unsupported_psd"),  # PSB
    (22, ">H", 16, "unsupported_psd"),  # 16 bits per channel
    (24, ">H", 4, "unsupported_psd"),  # CMYK
    (24, ">H", 1, "unsupported_psd"),  # greyscale
    (0, ">4s", b"8BPX", "invalid_psd"),
    (12, ">H", 0, "invalid_psd"),  # no channels
])
def test_files_outside_the_subset_are_refused(offset, fmt, value, code):
    with pytest.raises(VixlError) as caught:
        import_document(empty(), patched(LAYERED, offset, fmt, value), "psd")
    assert caught.value.code == code


def test_zip_compressed_channels_are_refused():
    data = built([Record("only", pixels=tile(10, 10, (255, 0, 0, 255)), box=(0, 0, 10, 10))])
    document = psd_reader.read(data, Limits())
    offset, _ = document.layers[0].channels[0]
    with pytest.raises(VixlError) as caught:
        import_document(empty(), patched(data, offset, ">H", 2), "psd")
    assert caught.value.code == "unsupported_psd"


def test_oversized_declarations_are_refused_before_any_large_allocation():
    count = layer_count_offset(LAYERED)
    cases = {
        "canvas": patched(LAYERED, 14, ">II", 30000, 30000),
        "layer count": patched(LAYERED, count, ">h", 30000),
        "layer box": patched(LAYERED, count + 2, ">4i", 0, 0, 16000, 16000),
        "tall strip": patched(LAYERED, count + 2, ">4i", 0, 0, 2 ** 30, 1),
    }
    tracemalloc.start()
    try:
        for name, data in cases.items():
            tracemalloc.reset_peak()
            with pytest.raises(VixlError) as caught:
                psd_reader.read(data, Limits())
            assert caught.value.code in ("resource_limit", "invalid_psd"), name
            assert tracemalloc.get_traced_memory()[1] < 1_000_000, name
    finally:
        tracemalloc.stop()
    with pytest.raises(VixlError) as caught:
        import_document(empty(), cases["canvas"], "psd")
    assert caught.value.code == "resource_limit"


def test_layers_are_budgeted_together_not_one_by_one():
    # The canvas and each layer fit a 7,000-pixel budget on their own (96x64 = 6,144); together they do not.
    limits = Limits(max_load_pixels=7000)
    with pytest.raises(VixlError) as caught:
        psd_reader.read(LAYERED, limits)
    assert caught.value.code == "resource_limit" and "together" in str(caught.value)
    with pytest.raises(VixlError) as caught:
        psd_reader.read(LAYERED, Limits(max_layers=3))
    assert caught.value.code == "resource_limit"
    with pytest.raises(VixlError) as caught:
        psd_reader.read(LAYERED, Limits(max_asset_bytes=1000))
    assert caught.value.code == "resource_limit"


def test_a_compressed_row_cannot_decode_past_its_width():
    out = bytearray(4)
    for row in (b"\x81\x05",  # a run of 128 bytes into a row of 4
                b"\x07abcdefgh",  # 8 literal bytes into a row of 4
                b"\xfe\x05"):  # a run of 3: the row is one byte short
        with pytest.raises(VixlError) as caught:
            psd_reader._unpack_rows(row, 0, len(row), [len(row)], 4, out)
        assert caught.value.code == "invalid_psd"
    with pytest.raises(VixlError):
        psd_reader._unpack_rows(b"\xfd\x05", 0, 2, [9], 4, out)  # the row table points past the data
    psd_reader._unpack_rows(b"\xfd\x05", 0, 2, [2], 4, out)
    assert bytes(out) == b"\x05" * 4


def decode_everything(data):
    document = psd_reader.read(data, Limits())
    for layer in document.layers:
        psd_reader.layer_pixels(document, layer)
        psd_reader.mask_pixels(document, layer)
    psd_reader.composite(document)
    return document


def test_truncated_and_corrupted_files_fail_cleanly():
    assert len(decode_everything(LAYERED).layers) == 8  # six layers, the group and its end marker
    for cut in range(0, len(LAYERED), 61):
        try:
            decode_everything(LAYERED[:cut])
        except EXPECTED as exc:
            assert exc.code in ("invalid_psd", "unsupported_psd", "resource_limit"), (cut, exc.code)
    rng = random.Random(514)
    type_layer = Project(120, 60, "#ffffff")
    type_layer.apply({"type": "text", "name": "t", "text": "Type", "x": 10, "y": 10, "size": 24})
    for source in (LAYERED, type_layer.export(None, format="PSD")):
        # Mostly the structural part (header, layer records), where a changed byte reaches the parser.
        span = min(len(source), 4000)
        for _ in range(400):
            data = bytearray(source)
            for _ in range(rng.randint(1, 4)):
                data[rng.randrange(span)] = rng.randrange(256)
            try:
                document = decode_everything(bytes(data))
            except EXPECTED as exc:
                assert exc.code in ("invalid_psd", "unsupported_psd", "resource_limit"), exc.code
                continue
            for layer in document.layers:
                if layer.type_data is not None:
                    from vixl.psd_text import Malformed, parse_type_block

                    try:
                        parse_type_block(layer.type_data)
                    except Malformed:
                        pass


def test_corrupted_files_never_change_the_document():
    rng = random.Random(7)
    for _ in range(25):
        data = bytearray(LAYERED)
        for _ in range(3):
            data[rng.randrange(1500)] = rng.randrange(256)
        p = empty()
        try:
            import_document(p, bytes(data), "psd")
        except EXPECTED:
            assert not p.state["layers"] and p.state["canvas"]["width"] == 10


def test_psd_import_rejects_options_it_does_not_take():
    with pytest.raises(VixlError, match="PSD import"):
        import_document(empty(), LAYERED, "psd", font_map={"A": "b"})
    with pytest.raises(VixlError, match="svg_mode"):
        import_document(empty(), LAYERED, "psd", svg_mode="vector")


def test_cli_imports_a_psd(tmp_path):
    (tmp_path / "art.PSD").write_bytes(LAYERED)
    Project(10, 10, "transparent").save(tmp_path / "doc.vixl")
    env = {**os.environ, "PYTHONPATH": os.pathsep.join(sys.path)}
    run = subprocess.run([sys.executable, "-m", "vixl", "-p", str(tmp_path / "doc.vixl"), "import",
                          str(tmp_path / "art.PSD")], capture_output=True, text=True, env=env)
    assert run.returncode == 0, run.stderr
    loaded = Project.load(tmp_path / "doc.vixl")
    assert loaded.find_layer("Ground")["type"] == "group" and loaded.state["canvas"]["width"] == 96


def test_mcp_step_and_rest_import_a_psd(tmp_path):
    from fastapi.testclient import TestClient

    from vixl.interfaces import Session, create_app
    from vixl.mcp_tools import build_server

    (tmp_path / "art.psd").write_bytes(LAYERED)
    session = Session(workspace=tmp_path)
    session.create("a.vixl", 16, 16)
    server = build_server(session)
    asyncio.run(server.call_tool("vixl_apply", {"operations": [{"type": "import-document", "path": "art.psd"}]}))
    with session.project() as project:
        assert project.find_layer("Hill")["mask"] and project.state["canvas"]["height"] == 64
    Project(10, 10, "transparent").save(tmp_path / "api.vixl")
    client = TestClient(create_app(tmp_path / "api.vixl"))
    response = client.post("/import?format=psd&name=art", content=LAYERED)
    assert response.status_code == 200, response.text
    assert response.json()["layers"] == {"image": 6, "group": 1}
    assert client.post("/import?format=psd", content=LAYERED[:200]).status_code == 400


def test_host_accepts_psd_as_an_import_format():
    from vixl.host import IMPORT_FORMATS

    assert "psd" in IMPORT_FORMATS
