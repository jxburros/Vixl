"""A printer's template (PNG or PSD) imported as role guides, saved as a guide set and enforced by check (#727)."""

import importlib.util
from pathlib import Path
import shutil
import struct

import numpy as np
from PIL import Image
import pytest

from vixl import Project, VixlError
from vixl.checks import check_design
from vixl.interfaces import Session
from vixl.workflows import describe, dispatch

FIXTURES = Path(__file__).parent / "fixtures" / "print"
_spec = importlib.util.spec_from_file_location("make_template", FIXTURES / "make_template.py")
template = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(template)

COLORS = {template.TRIM: "trim", template.SAFE: "safe", template.KEEP_OUT: "keep-out", template.FOLD: "fold"}


def workspace(tmp_path, size=(1000, 400), name="wrap.vixl"):
    shutil.copy(FIXTURES / "wrap-template.png", tmp_path / "template.png")
    Project(*size, "white").save(tmp_path / name)
    return Session(str(tmp_path / name), workspace=str(tmp_path))


def numbers(d):
    return [float(v) for v in d.replace("M", "").replace("L", "").replace("Z", "").split()]


def close(d, expected, by=1):
    """The outline ``d`` has the corners ``expected`` (any start, either direction), within ``by`` pixels."""
    values = numbers(d)
    corners = list(zip(values[::2], values[1::2]))
    return len(corners) == len(expected) and all(
        any(abs(x - ex) <= by and abs(y - ey) <= by for x, y in corners) for ex, ey in expected)


def box(rect):
    left, top, right, bottom = rect
    return [(left, top), (right, top), (right, bottom), (left, bottom)]


def findings(p):
    return [i for i in check_design(p, checks=["safe_area"])["issues"] if i["check"] == "safe_area"]


def test_template_png_imports_into_role_tagged_guides(tmp_path):
    session = workspace(tmp_path)
    result = dispatch(session, "guides-import", {"source": "template.png", "colors": COLORS})
    assert result["applied"] and result["counts"] == {"fold": 2, "keep-out": 1, "safe": 2, "trim": 1}
    guides = Project.load(tmp_path / "wrap.vixl").state["guides"]
    assert guides == result["guides"] and sorted(guides) == ["fold-1", "fold-2", "keep-out-1", "safe-1", "safe-2",
                                                              "trim-1"]
    assert {name: guide["role"] for name, guide in guides.items()} == {
        "fold-1": "fold", "fold-2": "fold", "keep-out-1": "keep-out", "safe-1": "safe", "safe-2": "safe",
        "trim-1": "trim"}
    # The back cover's safe area keeps its barcode notch: eight corners, numbered left to right.
    assert close(guides["safe-1"]["d"], template.BACK) and close(guides["safe-2"]["d"], box(template.FRONT))
    assert close(guides["keep-out-1"]["d"], box(template.BARCODE)) and close(guides["trim-1"]["d"], box(template.BOARD))
    assert [guides[name]["axis"] for name in ("fold-1", "fold-2")] == ["x", "x"]
    assert [abs(guides[name]["position"] - x) <= 1 for name, x in zip(("fold-1", "fold-2"), template.FOLDS)] == [True] * 2
    # Whole pixels (#699), and the lettering drawn in the line colours is not read as lines.
    assert all(float(v).is_integer() for guide in guides.values() if "d" in guide for v in numbers(guide["d"]))
    assert any("stray" in warning for warning in result.get("warnings", []))


def test_check_flags_text_in_the_keep_out_notch_and_outside_the_front_safe_area(tmp_path):
    session = workspace(tmp_path)
    dispatch(session, "guides-import", {"source": "template.png", "colors": COLORS})
    p = Project.load(tmp_path / "wrap.vixl")
    p.apply([
        {"type": "text", "name": "blurb", "text": "A quiet book", "x": 60, "y": 100, "size": 24, "color": "#111"},
        {"type": "text", "name": "isbn", "text": "ISBN 978-0", "x": 205, "y": 310, "size": 16, "color": "#111"},
        {"type": "text", "name": "title", "text": "Overhanging title", "x": 800, "y": 100, "size": 30, "color": "#111"},
    ])
    by_layer = {}
    for item in findings(p):
        by_layer.setdefault(item["layers"][0], set()).add((item["code"], item.get("guide")))
    assert "blurb" not in by_layer
    assert ("keep-out", "keep-out-1") in by_layer["isbn"]
    assert by_layer["title"] == {("outside-safe-guide", "safe-2")}
    p.apply({"type": "move", "target": "title", "x": 600, "y": 100})
    p.apply({"type": "remove", "target": "isbn"})
    assert findings(p) == []


def test_a_saved_guide_set_reproduces_the_guides_on_a_new_document(tmp_path):
    session = workspace(tmp_path)
    result = dispatch(session, "guides-import", {"source": "template.png", "colors": COLORS, "save": "acme-wrap",
                                                 "description": "Acme hardcover journal wrap"})
    assert result["saved"] == {"kind": "guide-sets", "name": "acme-wrap"}
    assert "acme-wrap" in dispatch(session, "resource-list", {"kind": "guide-sets"})["names"]
    stored = dispatch(session, "resource-get", {"kind": "guide-sets", "name": "acme-wrap"})["value"]
    assert (stored["width"], stored["height"], stored["source"]) == (1000, 400, "template.png")
    fresh = Project(1000, 400, "white", workspace=tmp_path) if "workspace" in Project.__init__.__code__.co_varnames \
        else Project(1000, 400, "white")
    fresh._workspace = str(tmp_path)
    fresh.apply({"type": "guide-set", "name": "acme-wrap"})
    assert fresh.state["guides"] == result["guides"]
    fresh.undo()
    assert not fresh.state.get("guides")
    # The same product at twice the resolution: scaled, still on whole pixels.
    double = Project(2000, 800, "white")
    double._workspace = str(tmp_path)
    double.apply([{"type": "guide", "name": "old", "rect": [0, 0, 10, 10], "role": "safe"},
                  {"type": "guide", "name": "mine", "axis": "x", "position": 7},
                  {"type": "guide-set", "name": "acme-wrap", "replace": True, "prefix": "acme"}])
    assert sorted(double.state["guides"]) == ["acme-fold-1", "acme-fold-2", "acme-keep-out-1", "acme-safe-1",
                                              "acme-safe-2", "acme-trim-1", "mine"]
    assert double.state["guides"]["acme-fold-1"]["position"] == 2 * result["guides"]["fold-1"]["position"]
    assert numbers(double.state["guides"]["acme-safe-2"]["d"]) == [2 * v for v in numbers(result["guides"]["safe-2"]["d"])]
    wrong = Project(1000, 1000, "white")
    wrong._workspace = str(tmp_path)
    with pytest.raises(VixlError, match="proportions differ"):
        wrong.apply({"type": "guide-set", "name": "acme-wrap"})
    with pytest.raises(VixlError):
        wrong.apply({"type": "guide-set", "name": "no-such-set"})


def test_listing_colours_first_changes_nothing_and_dry_run_reports_only(tmp_path):
    session = workspace(tmp_path)
    listing = dispatch(session, "guides-import", {"source": "template.png"})
    assert not listing["applied"] and listing["size"] == [1000, 400]
    assert {entry["color"] for entry in listing["colors_found"][:4]} == set(COLORS)
    dry = dispatch(session, "guides-import", {"source": "template.png", "colors": COLORS, "dry_run": True,
                                              "save": "not-saved"})
    assert not dry["applied"] and len(dry["guides"]) == 6 and "saved" not in dry
    assert not Project.load(tmp_path / "wrap.vixl").state.get("guides")
    assert "not-saved" not in dispatch(session, "resource-list", {"kind": "guide-sets"})["names"]


def test_solid_lines_at_another_size_scale_onto_the_canvas(tmp_path):
    session = workspace(tmp_path)
    template.draw(scale=3, dash=0, width=3, lettering=False).save(tmp_path / "big.png")
    result = dispatch(session, "guides-import", {"source": "big.png", "colors": COLORS, "name": "acme"})
    assert result["scale"] == [pytest.approx(1 / 3, abs=1e-5)] * 2
    guides = result["guides"]
    assert sorted(guides) == ["acme-fold-1", "acme-fold-2", "acme-keep-out-1", "acme-safe-1", "acme-safe-2",
                              "acme-trim-1"]
    assert close(guides["acme-safe-1"]["d"], template.BACK) and close(guides["acme-keep-out-1"]["d"],
                                                                      box(template.BARCODE))
    tall = workspace(tmp_path, size=(1000, 800), name="tall.vixl")
    with pytest.raises(VixlError, match="proportions differ"):
        dispatch(tall, "guides-import", {"source": "template.png", "colors": COLORS})
    stretched = dispatch(tall, "guides-import", {"source": "template.png", "colors": COLORS, "fit": "stretch"})
    assert close(stretched["guides"]["safe-2"]["d"], [(x, 2 * y) for x, y in box(template.FRONT)], by=2)


def test_requests_are_validated(tmp_path):
    session = workspace(tmp_path)
    with pytest.raises(VixlError, match="Unknown role"):
        dispatch(session, "guides-import", {"source": "template.png", "colors": {"#00a651": "margin"}})
    with pytest.raises(VixlError, match="Template not found"):
        dispatch(session, "guides-import", {"source": "missing.png", "colors": COLORS})
    with pytest.raises(VixlError, match="read a PSD"):
        dispatch(session, "guides-import", {"source": "template.png", "layers": {"Safe": "safe"}})
    with pytest.raises(VixlError, match="No guide lines"):
        dispatch(session, "guides-import", {"source": "template.png", "colors": {"#123456": "safe"}})
    with pytest.raises(VixlError):
        dispatch(session, "guides-import", {"source": "../outside.png", "colors": COLORS})
    with pytest.raises(VixlError, match="guide set"):
        dispatch(session, "resource-save", {"kind": "guide-sets", "name": "bad", "value": {"guides": {}}})
    properties = describe()["actions"]["guides-import"]["properties"]
    assert all(properties[field].get("description") and "type" in properties[field] for field in properties)


def test_guide_set_save_keeps_a_documents_role_guides(tmp_path):
    session = workspace(tmp_path)
    with pytest.raises(VixlError, match="no guides with a role"):
        dispatch(session, "guide-set-save", {"name": "empty"})
    p = Project.load(tmp_path / "wrap.vixl")
    p.apply([{"type": "guide", "name": "front", "rect": [560, 40, 400, 320], "role": "safe"},
             {"type": "guide", "name": "spine", "axis": "x", "position": 500, "role": "fold"},
             {"type": "guide", "name": "helper", "axis": "y", "position": 200}])
    p.save(tmp_path / "wrap.vixl", overwrite=True)
    session = Session(str(tmp_path / "wrap.vixl"), workspace=str(tmp_path))
    saved = dispatch(session, "guide-set-save", {"name": "hand-made", "description": "Drawn by hand"})
    assert saved["guides"] == ["front", "spine"] and saved["size"] == [1000, 400]
    other = Project(1000, 400, "white")
    other._workspace = str(tmp_path)
    other.apply({"type": "guide-set", "name": "hand-made"})
    assert other.state["guides"] == {"front": p.state["guides"]["front"], "spine": p.state["guides"]["spine"]}


def psd_bytes(tmp_path, rulers=((0, 480), (0, 520), (1, 200))):
    """A PSD of the template: the flattened picture, a layer holding only the safe lines, and ruler guides."""
    from vixl.psd_export import Record, write

    flat = template.draw().convert("RGBA")
    pixels = np.asarray(flat)
    safe = np.zeros_like(pixels)
    green = np.abs(pixels[..., :3].astype(int) - np.array([0, 0xa6, 0x51])).max(axis=2) <= 8
    safe[green] = (20, 20, 20, 255)  # a guide layer in another colour: the layer says what it is, not its ink
    left, top, right, bottom = 30, 30, 970, 370
    records = [Record("Artwork", pixels=pixels.copy(), box=(0, 0, 1000, 400)),
               Record("Safe Area", pixels=safe[top:bottom, left:right].copy(), box=(left, top, right, bottom),
                      visible=False)]
    data = write(records, flat)
    grid = struct.pack(">IIII", 1, 576, 576, len(rulers)) + b"".join(
        struct.pack(">iB", position * 32, direction) for direction, position in rulers)
    block = b"8BIM" + struct.pack(">H", 1032) + b"\0\0" + struct.pack(">I", len(grid)) + grid + b"\0" * (len(grid) % 2)
    length = struct.unpack(">I", data[30:34])[0]
    return data[:30] + struct.pack(">I", length + len(block)) + data[34:34 + length] + block + data[34 + length:]


def test_psd_template_gives_ruler_guides_named_layers_and_the_flattened_picture(tmp_path):
    session = workspace(tmp_path)
    (tmp_path / "template.psd").write_bytes(psd_bytes(tmp_path))
    listing = dispatch(session, "guides-import", {"source": "template.psd"})
    assert listing["layers_found"] == ["Artwork", "Safe Area"] and listing["ruler_guides_found"] == 3
    assert {entry["color"] for entry in listing["colors_found"][:4]} == set(COLORS)
    result = dispatch(session, "guides-import", {
        "source": "template.psd", "layers": {"safe area": "safe"}, "ruler_guides": "fold",
        "colors": {template.KEEP_OUT: "keep-out"}})
    guides = result["guides"]
    assert result["counts"] == {"fold": 3, "keep-out": 1, "safe": 2}
    assert close(guides["safe-1"]["d"], template.BACK) and close(guides["safe-2"]["d"], box(template.FRONT))
    assert close(guides["keep-out-1"]["d"], box(template.BARCODE))
    folds = sorted((g["axis"], g["position"]) for g in guides.values() if g.get("role") == "fold")
    assert folds == [("x", 480), ("x", 520), ("y", 200)]
    with pytest.raises(VixlError, match="no layer 'Spine'"):
        dispatch(session, "guides-import", {"source": "template.psd", "layers": {"Spine": "fold"}})


def test_malformed_and_oversized_psds_are_refused_without_large_allocations(tmp_path):
    from vixl.model import Limits
    from vixl.plugins.print_templates.psd_guides import read

    data = psd_bytes(tmp_path)
    for cut in (10, 40, 200, len(data) // 2):
        with pytest.raises(VixlError):
            read(data[:cut], Limits(), ["Safe Area"])
    with pytest.raises(VixlError, match="not a PSD"):
        read(b"GIF89a" + bytes(100), Limits())
    huge = data[:14] + struct.pack(">II", 60000, 60000) + data[22:]
    with pytest.raises(VixlError) as caught:
        read(huge, Limits())
    assert caught.value.code == "resource_limit"
    sixteen = data[:22] + struct.pack(">H", 16) + data[24:]
    with pytest.raises(VixlError, match="flattened PNG"):
        read(sixteen, Limits())
    psb = data[:4] + struct.pack(">H", 2) + data[6:]
    with pytest.raises(VixlError, match="flattened PNG"):
        read(psb, Limits())
    layers_at = 34 + struct.unpack(">I", data[30:34])[0]
    lying = data[:layers_at] + struct.pack(">I", 0x7fffffff) + data[layers_at + 4:]  # a length beyond the file
    with pytest.raises(VixlError, match="truncated"):
        read(lying, Limits())
    session = workspace(tmp_path)
    (tmp_path / "broken.psd").write_bytes(data[:300])
    with pytest.raises(VixlError):
        dispatch(session, "guides-import", {"source": "broken.psd", "colors": COLORS})


def test_detection_joins_boxes_that_share_an_edge_and_leaves_open_lines_open():
    from vixl.plugins.print_templates import detect

    mask = np.zeros((200, 300), dtype=bool)
    for y in (20, 120):
        mask[y, 20:221] = True
    for x in (20, 120, 220):
        mask[20:121, x] = True
    mask[160, 10:290] = True  # a line on its own
    horizontal, vertical = detect.lines(mask, gap=6, minimum=16, thickness=4)
    closed, loose = detect.outlines(horizontal, vertical, reach=6, minimum=16)
    assert closed == [[[20, 20], [120, 20], [120, 120], [20, 120]], [[120, 20], [220, 20], [220, 120], [120, 120]]] \
        or sorted(sorted(map(tuple, face)) for face in closed) == [
            [(20, 20), (20, 120), (120, 20), (120, 120)], [(120, 20), (120, 120), (220, 20), (220, 120)]]
    assert loose == [("h", 160, 10, 289)]
    block = np.zeros((100, 100), dtype=bool)
    block[10:60, 10:90] = True  # a filled patch is not a line
    assert detect.lines(block, gap=6, minimum=16, thickness=4) == ([], [])


def test_cli_and_plugin_registration(tmp_path):
    from vixl import plugins, targets
    from vixl.commands import compile_command

    assert compile_command("guide-set acme-wrap --fit stretch --replace") == {
        "type": "guide-set", "name": "acme-wrap", "fit": "stretch", "replace": True}
    assert targets.mode("guide-set") == "one"
    row = next(row for row in plugins.describe() if row["name"] == "print_templates")
    assert row["operations"] == ["guide-set"] and row["workflows"] == ["guide-set-save", "guides-import"]
    assert Image.open(FIXTURES / "wrap-template.png").size == template.SIZE


def test_command_line_imports_saves_and_applies(tmp_path, monkeypatch, capsys):
    import json

    from vixl.cli import main

    workspace(tmp_path)
    monkeypatch.chdir(tmp_path)
    assert main(["-p", "wrap.vixl", "--json", "guides-import", "template.png"]) == 0
    assert {entry["color"] for entry in json.loads(capsys.readouterr().out)["colors_found"][:4]} == set(COLORS)
    pairs = [part for color, role in COLORS.items() for part in ("--color", f"{color}={role}")]
    assert main(["-p", "wrap.vixl", "--json", "guides-import", "template.png", *pairs, "--save", "acme-wrap"]) == 0
    assert json.loads(capsys.readouterr().out)["counts"]["safe"] == 2
    assert main(["new", "1000x400", "-o", "second.vixl"]) == 0
    assert main(["-p", "second.vixl", "guide-set", "acme-wrap"]) == 0
    assert Project.load(tmp_path / "second.vixl").state["guides"] == Project.load(tmp_path / "wrap.vixl").state["guides"]
    assert main(["-p", "second.vixl", "guide", "spare", "--rect", "600", "60", "40", "40", "--role", "keep-out"]) == 0
    capsys.readouterr()
    assert main(["-p", "second.vixl", "--json", "guide-set-save", "with-spare"]) == 0
    assert "spare" in json.loads(capsys.readouterr().out)["guides"]
