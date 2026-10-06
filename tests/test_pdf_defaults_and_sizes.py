"""The PDF content mode is predictable and reported, and deck PDFs are the size of their PowerPoint slides."""

import asyncio
import io
import json
import subprocess
import sys

import pytest

from vixl import Project, VixlError
from vixl.interfaces import Session
from vixl.mcp_tools import build_server, export_file

pypdf = pytest.importorskip("pypdf")
pptx = pytest.importorskip("pptx")


def _page(data, number=0):
    return pypdf.PdfReader(io.BytesIO(data)).pages[number]


def _infographic():
    p = Project(1200, 1800, "#f7f1e5")  # a plain screen canvas: no pages, no print size
    p.apply([{"type": "text", "name": "title", "text": "Cups sold in 2025", "size": 80, "x": 50, "y": 50, "color": "#14263b"},
             {"type": "shape", "name": "bar", "shape": "rectangle", "x": 50, "y": 300, "width": 500, "height": 100,
              "fill": "#e2725b"}])
    return p


def _deck():
    p = Project(1920, 1080, "white")
    p.apply([{"type": "text", "name": "title", "text": "Tidewick Cafe", "size": 120, "x": 100, "y": 100, "color": "black"},
             {"type": "page", "action": "add", "name": "two"},
             {"type": "text", "name": "title", "text": "Second slide", "size": 120, "x": 100, "y": 100, "color": "black"}])
    return p


# #50: the default mode


def test_default_pdf_is_vector_for_every_kind_of_document():
    """The first export of a plain document used to be an image, a paged or print-size one vector."""
    plain, deck, poster = _infographic(), _deck(), Project.sized("poster-11x17", "white", bleed=True)
    poster.apply({"type": "text", "name": "head", "text": "Poster", "size": 120, "x": 100, "y": 100, "color": "black"})
    for project, word in ((plain, "Cups sold"), (deck, "Tidewick"), (poster, "Poster")):
        report = {}
        data = project.export(format="PDF", report=report)
        assert word in _page(data).extract_text(), "real text, not pixels"
        assert not list(_page(data).images)
        assert report["content"] == "vector" and "default" in report["content_reason"]


def test_edited_copy_exports_in_the_same_mode_as_the_original():
    """The T08 revision: re-exporting an edited copy gave a raster PDF where round 1 was vector."""
    original = _infographic()
    revised = original.clone()
    revised.apply({"type": "text-set", "target": "title", "text": "Cups sold in December"})
    reports = []
    for project in (original, revised):
        report = {}
        project.export(format="PDF", report=report)
        reports.append(report)
    assert reports[0]["content"] == reports[1]["content"] == "vector"
    assert reports[0]["content_reason"] == reports[1]["content_reason"]


def test_export_result_states_which_mode_was_used_and_why():
    p = _infographic()
    report = {}
    assert not list(_page(p.export(format="PDF", pdf_content="raster", report=report)).extract_text().strip())
    assert report["content"] == "raster" and report["content_reason"] == "requested with pdf_content"
    report = {}
    p.export(format="PDF", pdf_content="vector", report=report)
    assert report["content"] == "vector" and report["content_reason"] == "requested with pdf_content"
    # A scaled export is a larger image; the report says so and how to get a vector PDF.
    report = {}
    scaled = p.export(format="PDF", scale=2, report=report)
    assert report["content"] == "raster" and "scale 2" in report["content_reason"] and "pdf_content" in report["content_reason"]
    assert list(_page(scaled).images)
    # Features that only exist as pixels (artboards, soft proofs, profiles) export raster and say so.
    report = {}
    p.export(format="PDF", proof=True, report=report)
    assert report["content"] == "raster" and "proof" in report["content_reason"]


def test_vector_cannot_be_combined_with_raster_only_options():
    with pytest.raises(VixlError, match="pdf_content=vector cannot be combined with proof"):
        _infographic().export(format="PDF", pdf_content="vector", proof=True)
    with pytest.raises(VixlError, match="vector or raster"):
        _infographic().export(format="PDF", pdf_content="image")


def test_mcp_export_file_reports_the_mode(tmp_path):
    session = Session(workspace=tmp_path)
    session.create("info.vixl", 600, 900, "#f7f1e5")
    session.apply([{"type": "text", "name": "title", "text": "Hello", "size": 60, "x": 20, "y": 20, "color": "black"}],
                  document="info.vixl")
    result = export_file(session, "info.pdf", document="info.vixl")
    assert result["content"] == "vector" and "default" in result["content_reason"] and result["fonts"] == 1
    result = asyncio.run(build_server(session).call_tool("vixl_export_file", {"path": "raster.pdf", "document": "info.vixl",
                                                                              "pdf_content": "raster"}))
    assert json.loads(result[0].text)["content"] == "raster"


def test_cli_export_prints_the_mode(tmp_path):
    def run(*args):
        done = subprocess.run([sys.executable, "-m", "vixl", "--json", *args], cwd=tmp_path, capture_output=True, timeout=60)
        assert done.returncode == 0, done.stderr.decode()
        return json.loads(done.stdout)

    run("new", "400x300", "--background", "white", "-o", "a.vixl")
    result = run("-p", "a.vixl", "export", "a.pdf")
    assert result["content"] == "vector" and "content_reason" in result


# #49: deck page size


def _slide_inches(data):
    presentation = pptx.Presentation(io.BytesIO(data))
    return presentation.slide_width / 914400, presentation.slide_height / 914400


def test_deck_pdf_pages_are_the_size_of_the_pptx_slides():
    deck = _deck()
    pdf_report, pptx_report = {}, {}
    pdf = deck.export(format="PDF", report=pdf_report)
    slides = deck.export(format="PPTX", report=pptx_report)
    width, height = _slide_inches(slides)
    assert (round(width, 3), round(height, 3)) == (13.333, 7.5)
    for number in range(2):
        box = _page(pdf, number).mediabox
        assert (float(box.width) / 72, float(box.height) / 72) == pytest.approx((width, height), abs=1e-3)
    assert pdf_report["page_size"] == pptx_report["page_size"] == {"width": 13.333, "height": 7.5, "unit": "in"}


def test_dpi_sets_both_the_pdf_page_and_the_slide_size():
    deck = _deck()
    pdf, slides = deck.export(format="PDF", dpi=96), deck.export(format="PPTX", dpi=96)
    assert _slide_inches(slides) == pytest.approx((20, 11.25))
    assert [float(v) for v in _page(pdf).mediabox] == [0, 0, 1440, 810]
    with pytest.raises(VixlError, match="dpi"):
        deck.export(format="PPTX", dpi=5000)


def test_canvases_with_a_dpi_and_single_screen_pages_keep_their_pdf_size():
    # A physical size wins for both exports (PDF and PPTX at 300 dpi: 6 x 4 in).
    card = Project.sized("postcard", "white")
    card.apply([{"type": "text", "name": "t", "text": "Hi", "size": 80, "x": 50, "y": 50, "color": "black"}])
    width, height = card.state["canvas"]["width"], card.state["canvas"]["height"]
    assert _slide_inches(card.export(format="PPTX")) == pytest.approx((width / 300, height / 300), abs=1e-3)
    assert [float(v) for v in _page(card.export(format="PDF")).mediabox][2:] == pytest.approx(
        [width / 300 * 72, height / 300 * 72], abs=0.01)
    # A single screen page is not a deck: 1 pixel is 1 point unless dpi says otherwise.
    single = Project(1920, 1080, "white")
    assert [float(v) for v in _page(single.export(format="PDF")).mediabox] == [0, 0, 1920, 1080]
    assert [float(v) for v in _page(single.export(format="PDF", dpi=144)).mediabox] == [0, 0, 960, 540]
    assert _slide_inches(single.export(format="PPTX", dpi=144)) == pytest.approx((13.333, 7.5), abs=1e-3)
