"""Crafted inputs must be refused before the work they ask for is done: untrusted input is charged while it is
processed, so a small hostile file fails fast instead of running long, and hostile or broken input from outside
(archives, paths) fails as a VixlError that names no absolute path."""

import asyncio
import json
import struct
import time
import tracemalloc
import zipfile

import pytest
from mcp.server.fastmcp.exceptions import ToolError

from vixl import Project, VixlError
from vixl.history import patch
from vixl.interfaces import Session
from vixl.mcp_tools import build_server
from vixl.model import Limits
from vixl.project import MAX_DELTA_CHAIN
from vixl.svg_import import MAX_RASTERIZED, svg_operations


def rewritten(tmp_path, project, edit):
    project.save(tmp_path / "doc.vixl")
    with zipfile.ZipFile(tmp_path / "doc.vixl") as archive:
        files = {name: archive.read(name) for name in archive.namelist()}
    data = json.loads(files["project.json"])
    edit(data)
    files["project.json"] = json.dumps(data).encode()
    with zipfile.ZipFile(tmp_path / "bad.vixl", "w", zipfile.ZIP_DEFLATED) as archive:
        for name, payload in files.items():
            archive.writestr(name, payload)
    return tmp_path / "bad.vixl"


def boxed():
    p = Project(16, 16)
    p.apply({"type": "solid", "name": "box", "color": "red", "width": 4, "height": 4})
    p.apply({"type": "move", "target": "box", "x": 1, "y": 0})
    return p


def list_delta(order, changes=None):
    return {"$": "o", "s": {"layers": {"$": "l", "k": "id", "o": order, "s": changes or {}}}}


def test_repeated_key_list_delta_is_refused_before_copying(tmp_path):
    p = boxed()
    box = p.layer("box")["id"]
    path = rewritten(tmp_path, p, lambda data: data["nodes"][data["head"]].update(delta=list_delta([box] * 200_000)))
    tracemalloc.start()
    start = time.perf_counter()
    try:
        with pytest.raises(VixlError) as error:
            # A small byte limit keeps the reader's own buffer (sized by the limit) out of the peak.
            Project.load(path, limits=Limits(max_project_bytes=8 * 1024 * 1024))
        elapsed = time.perf_counter() - start
        peak = tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()
    assert error.value.code == "invalid_project"
    assert "invalid list delta" in str(error.value)
    # Copying the layer 200,000 times takes seconds and hundreds of megabytes.
    assert elapsed < 2.0
    assert peak < 50 * 1024 * 1024


def test_list_delta_key_that_is_neither_kept_nor_added_is_invalid(tmp_path):
    p = boxed()
    path = rewritten(tmp_path, p, lambda data: data["nodes"][data["head"]].update(delta=list_delta(["missing"])))
    with pytest.raises(VixlError) as error:
        Project.load(path)
    assert error.value.code == "invalid_project"
    assert "neither kept nor added" in str(error.value)


def test_list_delta_bounds_and_changes_outside_the_order():
    before = [{"id": "a"}, {"id": "b"}]
    with pytest.raises(VixlError, match="more than 1 items"):
        patch(before, {"$": "l", "k": "id", "o": ["a", "b"], "s": {}}, max_items=1)
    with pytest.raises(VixlError, match="repeats a key"):
        patch(before, {"$": "l", "k": "id", "o": ["a", "a"], "s": {}})
    with pytest.raises(VixlError, match="not in the order"):
        patch(before, {"$": "l", "k": "id", "o": ["a"], "s": {"b": {"$": "o", "s": {}}}})
    assert patch(before, {"$": "l", "k": "id", "o": ["b", "a"], "s": {}}) == before[::-1]


def test_over_long_delta_chain_is_invalid(tmp_path):
    p = Project(16, 16)
    p.apply({"type": "solid", "name": "box", "color": "red", "width": 4, "height": 4})

    def lengthen(data):
        # Turn every snapshot after the root into an empty delta, making one chain of every revision.
        parent = None
        for ident in list(data["nodes"]):
            node = data["nodes"][ident]
            if parent is not None:
                node.pop("state", None)
                node["delta"] = node.get("delta") or {"$": "o", "s": {}}
            parent = ident
        root = next(iter(data["nodes"]))
        last = root
        for index in range(MAX_DELTA_CHAIN + 1):
            ident = f"rev_crafted{index:04d}"
            data["nodes"][ident] = {"id": ident, "parent": last, "operations": [], "label": None,
                                    "delta": {"$": "o", "s": {}}}
            last = ident
        data["head"] = last
        data["redo_stack"] = []
        for name in data.get("branches", {}):
            data["branches"][name] = last

    with pytest.raises(VixlError) as error:
        Project.load(rewritten(tmp_path, p, lengthen))
    assert error.value.code == "invalid_project"
    assert "delta chain" in str(error.value)


def test_oversized_history_snapshot_is_refused_before_reconstruction(tmp_path):
    p = boxed()
    box = p.state["layers"][0]

    def grow(data):
        root = next(iter(data["nodes"].values()))
        root["state"]["layers"] = [dict(box, id=f"lay_{i:06d}") for i in range(5000)]

    with pytest.raises(VixlError) as error:
        Project.load(rewritten(tmp_path, p, grow))
    assert error.value.code == "invalid_project"
    assert "snapshot" in str(error.value)


SVG = '<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="40" height="40">'


def use_fanout(levels=5, ways=10):
    """A ~1 KB SVG whose ``<use>`` tree expands to ``ways ** levels`` shapes."""
    parts = [SVG, '<defs><rect id="l0" width="1" height="1" fill="#000"/>']
    for level in range(1, levels + 1):
        uses = "".join(f'<use xlink:href="#l{level - 1}"/>' for _ in range(ways))
        parts.append(f'<g id="l{level}">{uses}</g>')
    parts.append(f'</defs><use xlink:href="#l{levels}"/></svg>')
    return "".join(parts).encode()


@pytest.mark.parametrize("fallback", [False, True])
def test_svg_use_fanout_fails_fast(fallback):
    data = use_fanout()
    assert len(data) < 1600
    start = time.perf_counter()
    with pytest.raises(VixlError) as caught:
        svg_operations(data, Project(40, 40), "art", fallback=fallback)
    assert caught.value.code == "resource_limit"
    assert caught.value.details.get("field") == "svg"
    assert time.perf_counter() - start < 5  # it ran for minutes before the expansion was charged


def test_svg_use_within_budget_still_expands():
    operations = svg_operations(use_fanout(levels=2, ways=10), Project(40, 40), "art")
    assert sum(op["type"] == "shape" for op in operations) == 100


def unsupported(count):
    shapes = "".join(f'<rect x="{i % 40}" y="{i // 40}" width="1" height="1" filter="url(#f)"/>' for i in range(count))
    return (f'{SVG}<defs><filter id="f"><feGaussianBlur stdDeviation="0.1"/></filter></defs>{shapes}</svg>').encode()


def test_svg_raster_fallback_is_capped():
    report = {}
    svg_operations(unsupported(MAX_RASTERIZED), Project(40, 40), "art", fallback=True, report=report)
    assert len(report["rasterized"]) == MAX_RASTERIZED
    with pytest.raises(VixlError) as caught:
        svg_operations(unsupported(100), Project(40, 40), "art", fallback=True)
    assert caught.value.code == "resource_limit"
    assert "svg_mode='appearance'" in str(caught.value)


def patch_member(data, name, *, flags=0, method=None):
    """``data`` (a ZIP archive) with ``name``'s general-purpose flags or compression method rewritten in both its
    local header and its central directory entry."""
    data = bytearray(data)
    encoded = name.encode()
    for signature, flag_at, method_at, name_at in ((b"PK\x03\x04", 6, 8, 30), (b"PK\x01\x02", 8, 10, 46)):
        start = 0
        while (start := data.find(signature, start)) != -1:
            if data[start + name_at:start + name_at + len(encoded)] == encoded:
                current = struct.unpack_from("<H", data, start + flag_at)[0]
                struct.pack_into("<H", data, start + flag_at, current | flags)
                if method is not None:
                    struct.pack_into("<H", data, start + method_at, method)
            start += 4
    return bytes(data)


@pytest.mark.parametrize("change", [{"flags": 1}, {"method": 99}], ids=["encrypted", "method-99"])
def test_encrypted_and_method99_archives_are_invalid_project(tmp_path, change):  # #676
    path = tmp_path / "doc.vixl"
    Project(40, 30, "#ffffff").save(path)
    path.write_bytes(patch_member(path.read_bytes(), "project.json", **change))
    with pytest.raises(VixlError) as raised:
        Project.load(path)
    assert raised.value.code == "invalid_project"
    assert "unsupported or encrypted ZIP member" in str(raised.value)


def call_error(server, name, **arguments):
    with pytest.raises(ToolError) as raised:
        asyncio.run(server.call_tool(name, arguments))
    message = str(raised.value)
    return message, json.loads(message[message.index("{"):])


def test_nul_path_is_invalid_input(tmp_path):  # #676
    session = Session(workspace=tmp_path)
    with pytest.raises(VixlError) as raised:
        session.resolve("a\0b.vixl")
    assert raised.value.code == "invalid_input" and raised.value.details["field"] == "path"
    server = build_server(Session(workspace=tmp_path))
    message, error = call_error(server, "vixl_document", action="open", path="a\0b.vixl")
    assert error["error"] == "invalid_input" and str(tmp_path) not in message


def test_document_list_hides_absolute_workspace(tmp_path):  # #676
    server = build_server(Session(workspace=tmp_path))
    content = asyncio.run(server.call_tool("vixl_document", {"action": "list"}))
    text = content[0].text if isinstance(content, list) else content[0][0].text
    assert json.loads(text)["workspace"] == "." and str(tmp_path) not in text


def test_mcp_os_errors_show_paths_relative_to_the_workspace(tmp_path, monkeypatch):  # #676
    from vixl import assets

    def unreadable(path, limit):
        raise PermissionError(13, "Permission denied", str(path))

    monkeypatch.setattr(assets, "read_bounded", unreadable)
    server = build_server(Session(workspace=tmp_path))
    asyncio.run(server.call_tool("vixl_document", {"action": "create", "path": "a.vixl", "width": 20, "height": 20}))
    message, error = call_error(server, "vixl_apply", operations=[{"type": "import-image", "path": "art/photo.png"}])
    assert error["error"] == "io_error" and error["message"] == "Permission denied: art/photo.png"
    assert str(tmp_path) not in message


def test_friendly_shows_a_file_outside_the_workspace_by_basename_only(tmp_path):  # #676
    from vixl.errors import friendly

    inside = FileNotFoundError(2, "No such file or directory", str(tmp_path / "art" / "a.png"))
    outside = FileNotFoundError(2, "No such file or directory", "/srv/private/b.png")
    assert str(friendly(inside, relative_to=tmp_path)) == "No such file: art/a.png (the folder art does not exist)"
    assert str(friendly(outside, relative_to=tmp_path)) == "No such file: b.png"
    assert str(friendly(outside)).startswith("No such file: /srv/private/b.png")  # The CLI shows what the user typed.


EPS = (b"%!PS-Adobe-3.0 EPSF-3.0\n%%BoundingBox: 0 0 16 16\n%%EndComments\n"
       b"newpath 0 0 moveto 16 16 lineto stroke showpage\n%%EOF\n")


def test_eps_bytes_are_not_decoded():  # #677
    # A fresh interpreter: another test may already have loaded every Pillow plugin into this one.
    import subprocess
    import sys
    from pathlib import Path

    import vixl

    script = (
        "import sys\n"
        "from vixl.assets import decode, image_size\n"
        "from vixl.errors import VixlError\n"
        "from vixl.model import Limits\n"
        "for read in (lambda: decode(sys.stdin.buffer.read(), Limits()), lambda: image_size(EPS, Limits())):\n"
        "    try:\n"
        "        read()\n"
        "    except VixlError as exc:\n"
        "        assert exc.code == 'invalid_image', exc.code\n"
        "    else:\n"
        "        raise SystemExit('decoded EPS')\n"
        "assert 'PIL.EpsImagePlugin' not in sys.modules, 'EPS decoder loaded'\n"
        "print('ok')\n"
    ).replace("EPS,", repr(EPS) + ",")
    env = {**__import__("os").environ, "PYTHONPATH": str(Path(vixl.__file__).parent.parent)}
    done = subprocess.run([sys.executable, "-c", script], input=EPS, capture_output=True, env=env, timeout=60)
    assert done.returncode == 0 and done.stdout.strip() == b"ok", done.stderr.decode()


def test_no_unrestricted_image_open():  # #677
    """Every ``Image.open`` in src/vixl names its formats; untrusted bytes go through ``assets.open_image``."""
    import ast
    from pathlib import Path

    import vixl

    src = Path(vixl.__file__).parent
    offenders = []
    for path in sorted(src.rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "open"
                    and isinstance(node.func.value, ast.Name) and node.func.value.id.endswith("Image")
                    and not any(keyword.arg == "formats" for keyword in node.keywords)):
                offenders.append(f"{path.relative_to(src)}:{node.lineno}")
    assert not offenders, f"Image.open without formats= (use assets.open_image): {offenders}"


def test_pillow_global_unchanged_during_decode(monkeypatch):  # #677
    import io
    import threading

    from PIL import Image

    from vixl.assets import decode

    stream = io.BytesIO()
    Image.new("RGB", (64, 48), "red").save(stream, format="PNG")
    before = Image.MAX_IMAGE_PIXELS
    seen = []
    real_open = Image.open

    def watched(*args, **kwargs):
        seen.append(Image.MAX_IMAGE_PIXELS)
        return real_open(*args, **kwargs)

    monkeypatch.setattr(Image, "open", watched)
    # A downsampling decode reads sources up to 4x the 40 MP limit, above Pillow's own 89 MP default.
    worker = threading.Thread(target=lambda: seen.append(decode(stream.getvalue(), Limits(), target_pixels=1000).size))
    worker.start()
    worker.join()
    assert seen[-1] == (64, 48) and seen[:-1] and set(seen[:-1]) == {before}
    assert Image.MAX_IMAGE_PIXELS == before


def test_read_bounded_refuses_an_oversized_file_without_a_limit_sized_buffer(tmp_path):  # #667
    from vixl.assets import read_bounded

    sparse = tmp_path / "huge.bin"
    with sparse.open("wb") as stream:
        stream.truncate(64 * 1024 * 1024 + 1)
    tracemalloc.start()
    try:
        with pytest.raises(VixlError) as raised:
            read_bounded(sparse, 64 * 1024 * 1024)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert raised.value.code == "resource_limit" and peak < 2 * 1024 * 1024
    small = tmp_path / "small.bin"
    small.write_bytes(b"x" * (3 * 1024 * 1024 + 5))
    assert read_bounded(small, 3 * 1024 * 1024 + 5) == small.read_bytes()


def test_read_bounded_stops_a_stream_one_chunk_past_the_limit(tmp_path, monkeypatch):  # #667
    import io as _io

    from vixl import assets

    class Endless(_io.RawIOBase):
        read_calls = 0

        def readable(self):
            return True

        def fileno(self):
            return -1

        def read(self, size=-1):
            Endless.read_calls += 1
            return b"y" * size

    class Opener:
        def __init__(self, path):
            self.path = path

        def open(self, mode):
            return Endless()

    monkeypatch.setattr(assets, "Path", Opener)
    # A pipe or a growing file reports a size of 0 before it is read.
    monkeypatch.setattr(assets.os, "fstat", lambda fd: type("Stat", (), {"st_size": 0})())
    with pytest.raises(VixlError):
        assets.read_bounded("fifo", 5 * assets.READ_CHUNK)
    assert Endless.read_calls <= 6


def test_mcp_workflow_start_hides_the_absolute_workspace(tmp_path, monkeypatch):  # #676
    import subprocess

    class Child:
        pid = 4242

    Project(40, 40).save(tmp_path / "source.vixl")
    server = build_server(Session(workspace=tmp_path))
    monkeypatch.setattr(subprocess, "Popen", lambda *args, **kwargs: Child())
    job = {"kind": "production", "source": "source.vixl", "output": "campaign", "spec": {}}
    for request in ({"workflow": "start", "request": {}},
                    {"workflow": "submit", "request": {"job": job, "start": True}}):
        content = asyncio.run(server.call_tool("vixl_apply", request))
        text = content[0].text if isinstance(content, list) else content[0][0].text
        assert str(tmp_path) not in text and "4242" in text
