"""Print PDF page geometry (exact trim + bleed, TrimBox/BleedBox) and RGB/RGBA raster export."""

import asyncio
import io
import subprocess
import sys

from PIL import Image
import pytest

from vixl import Project, VixlError
from vixl.interfaces import Session
from vixl.mcp_tools import build_server, export_file

pypdf = pytest.importorskip("pypdf")


def _boxes(data):
    page = pypdf.PdfReader(io.BytesIO(data)).pages[0]
    keys = set(page)  # pypdf's box getters fill in missing boxes, so record what the file has first
    return {name: [round(float(v), 4) for v in getattr(page, name)] for name in ("mediabox", "trimbox", "bleedbox")}, keys


def _poster():
    p = Project.sized("poster-11x17", "white", bleed=True)
    assert p.state["canvas"]["bleed"] == 37.5  # 0.125 in at 300 dpi, kept to the half pixel (#306)
    p.apply({"type": "solid", "name": "panel", "color": "navy", "width": "100%", "height": "100%"})
    return p


@pytest.mark.parametrize("options", [{}, {"color_space": "cmyk"}, {"pdf_content": "raster"}])
def test_single_page_print_pdf_is_exact_trim_plus_bleed_with_boxes(options):
    boxes, page = _boxes(_poster().export(format="PDF", **options))
    assert boxes["mediabox"] == [0, 0, 810, 1242]  # 11.25 × 17.25 in
    assert boxes["bleedbox"] == [0, 0, 810, 1242]
    assert boxes["trimbox"] == [9, 9, 801, 1233]  # 11 × 17 in, 0.125 in in from every edge
    assert "/TrimBox" in page and "/BleedBox" in page


def test_documents_with_the_old_rounded_up_bleed_still_export_at_the_physical_size():
    p = _poster()
    assert (p.state["canvas"]["width"], p.state["canvas"]["height"]) == (3375, 5175)
    p.state["canvas"].update(width=3376, height=5176, bleed=38)  # as stored before 0.23
    boxes, _ = _boxes(p.export(format="PDF"))
    assert boxes["mediabox"] == [0, 0, 810, 1242] and boxes["trimbox"] == [9, 9, 801, 1233]


def test_multi_page_and_metric_print_pdfs_are_exact():
    p = Project.sized("a4", "white", bleed=True)
    p.apply([{"type": "text", "name": "front", "text": "Front", "size": 60},
             {"type": "page", "action": "add", "name": "back"},
             {"type": "text", "name": "back-text", "text": "Back", "size": 60}])
    reader = pypdf.PdfReader(io.BytesIO(p.export(format="PDF")))
    assert len(reader.pages) == 2
    mm = 72 / 25.4
    for page in reader.pages:
        assert [float(v) for v in page.mediabox] == pytest.approx([0, 0, 216 * mm, 303 * mm], abs=1e-3)
        assert [float(v) for v in page.trimbox] == pytest.approx([3 * mm, 3 * mm, 213 * mm, 300 * mm], abs=1e-3)


def test_pdf_without_bleed_has_no_print_boxes_and_explicit_dpi_still_maps_pixels():
    plain = Project(200, 100, "white")
    boxes, page = _boxes(plain.export(format="PDF", pdf_content="vector"))
    assert boxes["mediabox"] == [0, 0, 200, 100] and "/TrimBox" not in page
    poster = _poster()
    boxes, _ = _boxes(poster.export(format="PDF", dpi=150))
    w, h = poster.state["canvas"]["width"], poster.state["canvas"]["height"]
    assert boxes["mediabox"] == [0, 0, round(w * 72 / 150, 4), round(h * 72 / 150, 4)]


def test_png_alpha_modes():
    opaque = Project(20, 10, "white")
    opaque.apply({"type": "solid", "name": "fill", "color": "tomato", "width": 10, "height": 10})
    assert Image.open(io.BytesIO(opaque.export(format="PNG", alpha="keep"))).mode == "RGBA"
    auto = Image.open(io.BytesIO(opaque.export(format="PNG")))  # auto is the default on every interface
    assert auto.mode == "RGB" and auto.getpixel((2, 2)) == (255, 99, 71)

    clear = Project(20, 10, "transparent")
    clear.apply({"type": "solid", "name": "fill", "color": "tomato", "width": 10, "height": 10})
    assert Image.open(io.BytesIO(clear.export(format="PNG", alpha="auto"))).mode == "RGBA"
    flat = Image.open(io.BytesIO(clear.export(format="PNG", alpha="flatten", background="#102030")))
    assert flat.mode == "RGB" and flat.getpixel((15, 5)) == (16, 32, 48) and flat.getpixel((2, 2)) == (255, 99, 71)
    for fmt in ("WEBP", "TIFF"):
        assert Image.open(io.BytesIO(clear.export(format=fmt, alpha="flatten"))).mode == "RGB"
    assert Image.open(io.BytesIO(opaque.export(format="PNG", alpha="keep"))).mode == "RGBA"
    with pytest.raises(VixlError, match="alpha"):
        opaque.export(format="PNG", alpha="drop")


def test_mcp_export_file_writes_rgb_png_for_opaque_documents(tmp_path):
    session = Session(workspace=tmp_path)
    session.create("icon.vixl", 32, 32, "#f7f1e5")
    session.create("sticker.vixl", 32, 32, "transparent")
    server = build_server(session)

    def call(**arguments):
        return asyncio.run(server.call_tool("vixl_export_file", arguments))

    call(path="icon.png", document="icon.vixl")
    call(path="sticker.png", document="sticker.vixl")
    call(path="sticker-rgb.png", document="sticker.vixl", alpha="flatten", background="#14263b")
    assert Image.open(tmp_path / "icon.png").mode == "RGB"
    assert Image.open(tmp_path / "sticker.png").mode == "RGBA"
    flat = Image.open(tmp_path / "sticker-rgb.png")
    assert flat.mode == "RGB" and flat.getpixel((0, 0)) == (20, 38, 59)
    export_file(session, "kept.png", document="icon.vixl", alpha="keep")
    assert Image.open(tmp_path / "kept.png").mode == "RGBA"


def test_cli_export_alpha_flag(tmp_path):
    for args in (["new", "16x16", "--background", "white", "-o", "a.vixl"], ["export", "auto.png"],
                 ["export", "keep.png", "--alpha", "keep"]):
        result = subprocess.run([sys.executable, "-m", "vixl", *args], cwd=tmp_path, capture_output=True, timeout=20)
        assert result.returncode == 0, result.stderr.decode()
    assert Image.open(tmp_path / "auto.png").mode == "RGB"
    assert Image.open(tmp_path / "keep.png").mode == "RGBA"
