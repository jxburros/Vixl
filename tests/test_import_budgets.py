"""Cumulative budgets of the editable SVG and PDF imports (#818, #819, #822): a small file cannot multiply into
unbounded parsing, raster work, network requests or allocations."""

import base64
import ctypes
import hashlib
import io
import json
import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape

from PIL import Image
import pytest

from vixl import Project, VixlError
from vixl.imports import import_document
from vixl.model import Limits
from vixl.svg import METADATA
from vixl import svg_import
from vixl.svg_import import MAX_STYLE_RULES, MAX_STYLE_WORK, Converter, svg_operations

SVG = '<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="40" height="40">'


def limit_error(call):
    with pytest.raises(VixlError) as caught:
        call()
    assert caught.value.code == "resource_limit", caught.value
    return caught.value


# --- #818: stylesheets -------------------------------------------------------------------------------------------------


def test_svg_stylesheet_rule_count_is_capped_while_parsing():
    rules = "".join(f".c{i}{{fill:#000}}" for i in range(MAX_STYLE_RULES + 1))
    data = f'{SVG}<style>{rules}</style><rect class="c0" width="4" height="4"/></svg>'.encode()
    error = limit_error(lambda: svg_operations(data, Project(40, 40), "art"))
    assert error.details["limit"] == MAX_STYLE_RULES and "svg_mode='appearance'" in str(error)
    # The cap counts the rules of every <style> element together.
    half = "".join(f".c{i}{{fill:#000}}" for i in range(MAX_STYLE_RULES // 2 + 1))
    data = f'{SVG}<style>{half}</style><style>{half}</style><rect width="4" height="4"/></svg>'.encode()
    limit_error(lambda: svg_operations(data, Project(40, 40), "art"))


def test_svg_rules_are_only_compared_with_elements_they_can_match():
    """4,000 class rules and 1,000 elements: 4 million comparisons before the index, one per element with it."""
    rules = "".join(f".c{i}{{fill:#{i:06x}}}" for i in range(4000))
    shapes = "".join(f'<rect class="c{i}" x="{i % 40}" y="{i // 40}" width="1" height="1"/>' for i in range(1000))
    converter = Converter(f"{SVG}<style>{rules}</style>{shapes}</svg>".encode(), Project(40, 40), "art")
    operations = converter.convert()
    assert [op["fill"] for op in operations[:3]] == ["#000000", "#000001", "#000002"]
    assert len(operations) == 1000 and converter.style_work <= 2 * 1000


def test_svg_rule_matching_work_is_budgeted():
    """Rules every element matches cannot be indexed away: the comparisons are charged and the import stops."""
    count = 2000
    assert count * 1500 > MAX_STYLE_WORK
    rules = "".join(f"*{{stroke-width:{i}}}" for i in range(count))
    shapes = "".join(f'<rect x="{i % 40}" y="{i // 40}" width="1" height="1"/>' for i in range(1500))
    data = f"{SVG}<style>{rules}</style>{shapes}</svg>".encode()
    error = limit_error(lambda: svg_operations(data, Project(40, 40), "art", fallback=True))
    assert error.details["limit"] == MAX_STYLE_WORK


def test_svg_cascade_order_survives_the_rule_index():
    style = ("rect{fill:#111111} .a{fill:#222222} .a.b{fill:#333333} #one{fill:#444444} *{stroke:#555555} "
             ".b{fill:#666666} rect.a{fill:#777777}")
    shapes = ('<rect id="one" class="a b" width="4" height="4"/><rect class="a b" width="4" height="4"/>'
              '<rect class="b a" x="4" width="4" height="4"/><rect class="a" width="4" height="4"/>'
              '<rect class="b" width="4" height="4"/><rect width="4" height="4"/><circle class="a" r="2"/>')
    operations = svg_operations(f"{SVG}<style>{style}</style>{shapes}</svg>".encode(), Project(40, 40), "art")
    assert [op["fill"] for op in operations] == ["#444444", "#333333", "#333333", "#777777", "#666666", "#111111",
                                                 "#222222"]
    assert {op["stroke"] for op in operations} == {"#555555"}


# --- #818: embedded rasters and raster fallbacks --------------------------------------------------------------------


def png(color, size=(8, 8)):
    buffer = io.BytesIO()
    Image.new("RGBA", size, color).save(buffer, "PNG")
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode()


def test_svg_embedded_raster_is_decoded_and_stored_once_for_every_use(monkeypatch):
    from vixl import assets

    calls = {"decode": 0, "add": 0}
    decode, add_image = assets.decode, assets.add_image

    def counted_decode(*args, **kwargs):
        calls["decode"] += 1
        return decode(*args, **kwargs)

    def counted_add(*args, **kwargs):
        calls["add"] += 1
        return add_image(*args, **kwargs)

    monkeypatch.setattr(assets, "decode", counted_decode)
    monkeypatch.setattr(assets, "add_image", counted_add)
    uses = "".join(f'<use xlink:href="#photo" x="{i % 20}" y="{i // 20}"/>' for i in range(200))
    href = png("#cc3311")
    data = (f'{SVG}<defs><image id="photo" width="8" height="8" xlink:href="{href}"/></defs>{uses}'
            f'<image x="30" width="8" height="8" href="{href}"/></svg>').encode()
    project = Project(40, 40)
    operations = svg_operations(data, project, "art")
    images = [op for op in operations if op["type"] == "add"]
    assert len(images) == 201 and len({op["asset"] for op in images}) == 1
    assert calls == {"decode": 1, "add": 1}
    assert images[1]["x"] == 1 and images[-1]["x"] == 30


def test_svg_decoded_image_pixels_share_one_budget():
    images = "".join(f'<image x="{i}" width="8" height="8" href="{png((i, 0, 0, 255), (20, 20))}"/>' for i in range(6))
    data = f"{SVG}{images}</svg>".encode()
    project = Project(40, 40, limits=Limits(max_load_pixels=5 * 400))
    error = limit_error(lambda: svg_operations(data, project, "art", fallback=True))
    assert error.details["limit"] == 2000 and error.details["field"] == "svg"
    assert len(svg_operations(data, Project(40, 40, limits=Limits(max_load_pixels=6 * 400)), "art")) == 6


def unsupported(count):
    shapes = "".join(f'<rect x="{i % 40}" y="{i // 40}" width="1" height="1" filter="url(#f)"/>' for i in range(count))
    return f'{SVG}<defs><filter id="f"><feGaussianBlur stdDeviation="0.1"/></filter></defs>{shapes}</svg>'.encode()


def test_svg_raster_fallbacks_share_a_cumulative_pixel_budget(monkeypatch):
    """Each fallback renders the whole canvas: the canvas area times the fallbacks is what is bounded."""
    from vixl import imports

    renders = []
    render = imports.render_svg
    monkeypatch.setattr(imports, "render_svg", lambda tree, w, h: renders.append(w * h) or render(tree, w, h))
    project = Project(40, 40, limits=Limits(max_load_pixels=5 * 1600))
    error = limit_error(lambda: svg_operations(unsupported(8), project, "art", fallback=True))
    assert "svg_mode='appearance'" in str(error) and error.details["limit"] == 8000
    assert renders == [1600] * 5  # the sixth is refused before it is drawn
    report = {}
    svg_operations(unsupported(5), Project(40, 40, limits=Limits(max_load_pixels=5 * 1600)), "art", fallback=True,
                   report=report)
    assert len(report["rasterized"]) == 5


def test_svg_auto_import_reports_the_raster_budget_instead_of_falling_back():
    project = Project(40, 40, limits=Limits(max_load_pixels=3 * 1600))
    error = limit_error(lambda: import_document(project, unsupported(4), "svg", svg_mode="auto"))
    assert error.details["field"] == "svg" and not project.state["layers"]


# --- #819: embedded font records -------------------------------------------------------------------------------------


def own_svg(fonts):
    """A checksum-valid Vixl SVG whose embedded document names ``fonts`` (the digest does not cover the metadata)."""
    p = Project(60, 40, "#ffffff")
    p.apply({"type": "shape", "shape": "rectangle", "name": "box", "width": 20, "height": 10, "fill": "#123456"})
    data = p.export(format="SVG")
    match = METADATA.search(data)
    document = json.loads(ET.fromstring(match.group(0)).text)
    document["vixl"]["fonts"] = fonts
    metadata = '<metadata id="vixl-document">' + escape(json.dumps(document)) + "</metadata>"
    return data[:match.start()] + metadata.encode() + data[match.end():]


def record(index, family="Inter", weight=400):
    name = f"fonts/{hashlib.sha256(str(index).encode()).hexdigest()}.ttf"
    return name, {"family": family, "weight": weight, "italic": False, "registered": [f"face-{index}"],
                  "source": "google"}


@pytest.fixture
def font_requests(tmp_path, monkeypatch):
    """An empty font cache and a Google Fonts that answers 404; returns the requests made."""
    import httpx

    from vixl import typefaces

    monkeypatch.setenv("VIXL_FONT_CACHE", str(tmp_path / "fonts"))
    monkeypatch.delenv("VIXL_OFFLINE", raising=False)
    requests = []

    def handler(request):
        requests.append(str(request.url))
        return httpx.Response(404)

    real = httpx.Client
    monkeypatch.setattr(typefaces.httpx, "Client",
                        lambda *args, **kwargs: real(transport=kwargs.get("transport") or httpx.MockTransport(handler)))
    return requests


def test_more_font_records_than_the_limit_make_no_lookup(font_requests, monkeypatch):
    lookups = []
    monkeypatch.setattr(svg_import, "google_font", lambda *args: lookups.append(args) or (None, None))
    limit = Limits().max_load_fonts
    data = own_svg(dict(record(i, family=f"Family {i}") for i in range(limit + 1)))
    project = Project(10, 10)
    result = import_document(project, data, "svg", install_fonts=True)
    assert lookups == [] and font_requests == []
    # The embedded document is refused; the SVG's visible elements import instead, and the result says why.
    assert result["mode"] == "editable" and any("fonts; at most 64" in w for w in result["warnings"])
    with pytest.raises(VixlError) as caught:
        svg_import.embedded_project(svg_import.embedded_payload(data)[0], Project(10, 10), data, install_fonts=True)
    assert caught.value.code == "resource_limit" and caught.value.details["field"] == "max_load_fonts"
    assert lookups == [] and font_requests == []


def test_font_records_naming_one_style_share_one_lookup(font_requests):
    data = own_svg(dict(record(i) for i in range(40)))
    result = import_document(Project(10, 10), data, "svg", install_fonts=True)
    assert result["mode"] == "document" and set(result["fonts"].values()) == {"fallback"}
    assert len(font_requests) == 1  # one stylesheet request for Inter 400, not forty


@pytest.mark.parametrize("surface", ["python", "step", "rest", "host"])
def test_service_imports_do_not_install_fonts_by_default(surface, font_requests, tmp_path, monkeypatch):
    data = own_svg(dict([record(1)]))
    if surface == "python":
        result = import_document(Project(10, 10), data, "svg")
    elif surface == "step":
        from types import SimpleNamespace

        from vixl import steps

        (tmp_path / "in.svg").write_bytes(data)
        target = Project(10, 10)
        session = SimpleNamespace(resolve=lambda path: tmp_path / path, limits=target.limits)
        _, result, _ = steps.run(session, target, {"type": "import-document", "path": "in.svg"}, 0)
    elif surface == "rest":
        from fastapi.testclient import TestClient
        from vixl.interfaces import create_app

        Project(10, 10).save(tmp_path / "doc.vixl")
        response = TestClient(create_app(tmp_path / "doc.vixl")).post("/import", params={"format": "svg"}, content=data)
        assert response.status_code == 200, response.text
        result = response.json()
    else:
        from fastapi.testclient import TestClient
        from vixl.host import create_host_app

        with TestClient(create_host_app(tmp_path / "host", "t" * 32),
                        headers={"Authorization": "Bearer " + "t" * 32}) as client:
            made = client.post("/w/team/documents", json={"name": "d", "width": 10, "height": 10})
            assert made.status_code == 201, made.text
            response = client.post(f"/w/team/documents/{made.json()['id']}/import", params={"format": "svg"},
                                   content=data)
        assert response.status_code == 200, response.text
        result = response.json()
    assert font_requests == []
    assert result["fonts"] == {"face-1": "fallback"} and any("install_fonts" in w for w in result["warnings"])


def test_cli_svg_import_installs_fonts_unless_told_not_to(font_requests, tmp_path, monkeypatch):
    from vixl.cli import dispatch

    source = tmp_path / "in.svg"
    source.write_bytes(own_svg(dict([record(1)])))
    for name in ("a.vixl", "b.vixl", "c.vixl"):
        Project(10, 10).save(tmp_path / name)
    dispatch(["--project", str(tmp_path / "a.vixl"), "import", str(source)])
    assert len(font_requests) == 1
    dispatch(["--project", str(tmp_path / "b.vixl"), "import", str(source), "--no-install-fonts"])
    assert len(font_requests) == 1
    dispatch(["--project", str(tmp_path / "c.vixl"), "import", str(source), "--install-fonts"])
    assert len(font_requests) == 2


# --- #822: PDF -------------------------------------------------------------------------------------------------------

pdf = pytest.importorskip("vixl.plugins.pdf_import.pdf_import")


def test_pdf_string_refuses_a_huge_reported_length_before_allocating(monkeypatch):
    calls = []

    def reported(*args):
        calls.append(args)
        return 2 ** 31 - 1

    monkeypatch.setattr(ctypes, "create_string_buffer", lambda size: pytest.fail(f"allocated {size} bytes"))
    error = limit_error(lambda: pdf._string(None, reported, "object", utf16=True))
    assert error.details["limit"] == pdf.MAX_STRING_BYTES and len(calls) == 1


def test_pdf_segment_count_is_checked_before_any_segment_is_read():
    error = limit_error(lambda: pdf._segments(None, "path", lambda obj: 10 ** 9,
                                              lambda *args: pytest.fail("read a segment")))
    assert error.details["limit"] == pdf.MAX_PATH_SEGMENTS
    reader = pdf.PageReader(Project(10, 10), b"", "page", 1)
    reader.segments_read = pdf.MAX_SEGMENTS - 10
    limit_error(lambda: pdf._segments(None, "path", lambda obj: 11, lambda *args: pytest.fail("read a segment"),
                                      charge=reader.charge_segments))


class Forms:
    """A stand-in for ``pypdfium2.raw``: every object is a form holding ``fanout`` more forms."""

    def __init__(self, fanout):
        self.fanout, self.collected = fanout, 0

    def FPDFPageObj_GetType(self, obj):
        return pdf.FORM

    def FPDFPageObj_GetMatrix(self, obj, matrix):
        return False

    def FPDFPageObj_GetClipPath(self, obj):
        return None

    def FPDFFormObj_CountObjects(self, obj):
        return self.fanout

    def FPDFFormObj_GetObject(self, obj, index):
        self.collected += 1
        return object()

    FS_MATRIX = staticmethod(lambda: None)


def reader_over(raw):
    from fontTools.misc.transform import Transform

    reader = pdf.PageReader(Project(10, 10), b"", "page", 1)
    reader.raw = raw
    return reader, Transform()


def test_pdf_form_nesting_depth_is_limited():
    raw = Forms(1)
    reader, matrix = reader_over(raw)
    error = limit_error(lambda: reader.read_object(object(), matrix, 0))
    assert error.details["limit"] == pdf.MAX_FORM_DEPTH and raw.collected == pdf.MAX_FORM_DEPTH
    assert "svg_mode='appearance'" in str(error)


def test_pdf_nested_forms_share_one_object_budget():
    raw = Forms(1500)  # the first form of each level alone: 1,500 objects a level, fourteen levels
    reader, matrix = reader_over(raw)
    error = limit_error(lambda: reader.read_object(object(), matrix, 0))
    assert error.details["limit"] == pdf.MAX_OBJECTS and raw.collected <= pdf.MAX_OBJECTS
    # A reported count over the budget is refused before any handle is collected.
    raw = Forms(10 ** 9)
    reader, matrix = reader_over(raw)
    limit_error(lambda: reader.read_object(object(), matrix, 0))
    assert raw.collected == 0


def shaded_page(runs):
    """A Vixl PDF whose page alternates gradients (shadings: drawn as images) with editable shapes."""
    p = Project(160, 100, "#ffffff")
    operations = []
    for index in range(runs):
        operations += [{"type": "gradient", "name": f"sky{index}", "width": 30, "height": 30, "x": 5 + 12 * index,
                        "y": 10, "start": "#e63946", "end": "#1d3557"},
                       {"type": "shape", "shape": "ellipse", "name": f"sun{index}", "width": 10, "height": 10,
                        "x": 5 + 12 * index, "y": 60, "fill": "#e9c46a"}]
    p.apply(operations)
    return p.export(format="PDF")


def test_pdf_fallback_renders_share_a_cumulative_pixel_budget():
    pytest.importorskip("pypdfium2")
    data = shaded_page(4)
    allowed = Project(10, 10, limits=Limits(max_load_pixels=4 * 16000))
    result = import_document(allowed, data, "pdf")
    assert len(result["rasterized"]) == 4
    project = Project(10, 10, limits=Limits(max_load_pixels=3 * 16000))
    error = limit_error(lambda: import_document(project, data, "pdf"))
    assert error.details["limit"] == 48000 and error.details["field"] == "pdf"
    assert "svg_mode='appearance'" in str(error) and not project.state["layers"]


def test_pdf_image_pixels_count_towards_the_budget():
    pytest.importorskip("pypdfium2")
    from vixl.assets import add_image

    p = Project(160, 100, "#ffffff")
    for index in range(3):
        asset = add_image(p, Image.new("RGBA", (50, 40), (40 * index, 90, 200, 255)))
        p.apply({"type": "add", "asset": asset, "name": f"tile{index}", "x": 10 + 50 * index, "y": 10})
    data = p.export(format="PDF")
    assert import_document(Project(10, 10, limits=Limits(max_load_pixels=3 * 2000)), data, "pdf")["layers"]["image"] == 3
    limit_error(lambda: import_document(Project(10, 10, limits=Limits(max_load_pixels=3 * 2000 - 1)), data, "pdf"))


def test_svg_fallback_renders_are_charged_for_the_images_they_decode_again():
    """A masked group holding an image is drawn by resvg, which decodes the image for every such group."""
    href = png("#cc3311", (30, 30))
    groups = "".join(f'<g mask="url(#m)"><image x="{i}" width="8" height="8" href="{href}"/></g>' for i in range(4))
    data = (f'{SVG}<defs><mask id="m"><rect width="40" height="40" fill="white"/></mask></defs>{groups}</svg>').encode()
    cost = 1600 + 900  # the canvas and the image, per fallback
    report = {}
    svg_operations(data, Project(40, 40, limits=Limits(max_load_pixels=4 * cost)), "art", fallback=True, report=report)
    assert len(report["rasterized"]) == 4
    project = Project(40, 40, limits=Limits(max_load_pixels=4 * cost - 1))
    limit_error(lambda: svg_operations(data, project, "art", fallback=True))
