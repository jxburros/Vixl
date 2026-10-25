"""Post-export checks (#557): exported files are read back and compared with delivery specs."""

import asyncio
import io
import json
import subprocess
import sys
import zipfile
import zlib

import pytest
from PIL import Image

from vixl import Project, VixlError
from vixl import export_checks
from vixl.export_checks import inspect, presets, resolve_spec, verify
from vixl.interfaces import Session
from vixl.mcp_tools import build_server, export_file


def pdf(objects, root=1):
    """A small PDF from ``{number: body}`` (a body is the object text; a tuple is (dictionary, stream bytes))."""
    out = io.BytesIO()
    out.write(b"%PDF-1.7\n")
    offsets = {}
    for number, body in sorted(objects.items()):
        offsets[number] = out.tell()
        if isinstance(body, tuple):
            head, data = body
            out.write(b"%d 0 obj\n%s\nstream\n" % (number, head.replace(b"LEN", str(len(data)).encode())))
            out.write(data + b"\nendstream\nendobj\n")
        else:
            out.write(b"%d 0 obj\n%s\nendobj\n" % (number, body))
    xref = out.tell()
    count = max(objects) + 1
    out.write(b"xref\n0 %d\n0000000000 65535 f \n" % count)
    for number in range(1, count):
        out.write(b"%010d 00000 n \n" % offsets.get(number, 0))
    out.write(b"trailer\n<< /Size %d /Root %d 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (count, root, xref))
    return out.getvalue()


def helvetica_pdf(trim=None, bleed=None):
    """One Letter page drawing text in Helvetica, a font PDF viewers substitute (it is not embedded)."""
    content = b"BT /F1 24 Tf 72 700 Td (Not embedded) Tj ET"
    boxes = b""
    if trim:
        boxes += b" /TrimBox [%s]" % " ".join(map(str, trim)).encode()
    if bleed:
        boxes += b" /BleedBox [%s]" % " ".join(map(str, bleed)).encode()
    return pdf({
        1: b"<< /Type /Catalog /Pages 2 0 R >>",
        2: b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        3: b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 630 810]%s /Resources << /Font << /F1 4 0 R >> >> "
           b"/Contents 5 0 R >>" % boxes,
        4: b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        5: (b"<< /Length LEN >>", content),
    })


def no_pdfium(monkeypatch):
    monkeypatch.setattr(export_checks, "_pdfium_pages", lambda data, ink: None)


def letter(**kw):
    p = Project.sized("letter", "white", **kw)
    p.apply({"type": "text", "name": "head", "text": "Poster", "size": 120, "x": 200, "y": 300, "color": "black"})
    return p


def codes(report):
    return [item["code"] for item in report["issues"] if item["action"] == "fix"]


# ------------------------------------------------------------------------------------------------- PDF


@pytest.mark.parametrize("reader", ["pypdfium2", "byte-scan"])
def test_a_pdf_with_an_unembedded_font_is_a_finding(tmp_path, monkeypatch, reader):
    if reader == "byte-scan":
        no_pdfium(monkeypatch)
    else:
        pytest.importorskip("pypdfium2")
    path = tmp_path / "flyer.pdf"
    path.write_bytes(helvetica_pdf())
    report = verify(path, "office-pdf")
    assert report["facts"]["reader"] == reader
    assert report["facts"]["fonts_unembedded"] == ["Helvetica"]
    assert codes(report) == ["font-not-embedded"] and not report["passed"]
    finding = report["issues"][0]
    assert finding["check"] == "export" and finding["rule"] == "export.font-not-embedded"
    assert finding["severity"] == "error" and "Helvetica" in finding["message"]
    assert report["outcome"]["state"] == "validation_failed"


@pytest.mark.parametrize("reader", ["pypdfium2", "byte-scan"])
def test_vixl_pdfs_embed_their_fonts_and_keep_trim_and_bleed(tmp_path, monkeypatch, reader):
    if reader == "byte-scan":
        no_pdfium(monkeypatch)
    else:
        pytest.importorskip("pypdfium2")
    path = tmp_path / "poster.pdf"
    letter(bleed=True).export(path, color_space="cmyk")
    report = verify(path, "print-letter-bleed")
    facts = report["facts"]
    assert facts["pages"] == 1 and facts["page_size"] == [612.0, 792.0]
    assert facts["page_boxes"][0]["trim_box"] == [9.0, 9.0, 621.0, 801.0]
    assert facts["fonts"] and not facts["fonts_unembedded"] and facts["color"]["space"] == "CMYK"
    assert facts["ink"]["max"] <= 300
    assert report["passed"] and report["spec"] == "print-letter-bleed"
    if reader == "byte-scan":
        assert report["outcome"]["validation"] == "passed"  # a pure CMYK file states its ink without rendering


def test_a_wrong_or_missing_bleed_box_is_a_finding(tmp_path):
    no_bleed = tmp_path / "no-bleed.pdf"
    letter().export(no_bleed, color_space="cmyk")
    report = verify(no_bleed, "print-letter-bleed")
    assert "bleed-box" in codes(report)
    assert "TrimBox or BleedBox" in next(i["message"] for i in report["issues"] if i["code"] == "bleed-box")
    wrong = tmp_path / "wrong.pdf"
    # 0.25 in of bleed on the left and bottom, none on the right and top.
    wrong.write_bytes(helvetica_pdf(trim=[18, 18, 630, 810], bleed=[0, 0, 630, 810]))
    report = verify(wrong, {"bleed": "0.125in", "trim": "letter"})
    finding = next(i for i in report["issues"] if i["code"] == "bleed-box")
    assert finding["actual"] == [18.0, 18.0, 0.0, 0.0] and finding["expected"] == 9.0


def test_rgb_pdf_against_a_cmyk_spec_and_ink_over_the_limit(tmp_path):
    pytest.importorskip("pypdfium2")
    rgb = tmp_path / "rgb.pdf"
    letter(bleed=True).export(rgb)
    assert codes(verify(rgb, "print-letter-bleed")) == ["color"]
    p = letter(bleed=True)
    p.apply({"type": "shape", "name": "block", "shape": "rectangle", "x": 0, "y": 0, "width": 2625, "height": 900,
             "fill": "#000000"})
    rich = tmp_path / "rich.pdf"
    p.export(rich, color_space="cmyk", black_generation=0)
    report = verify(rich, {"preset": "print-letter-bleed", "ink_limit": 250})
    assert codes(report) == ["ink-limit"] and report["facts"]["ink"]["max"] > 250
    assert report["spec"] == "print-letter-bleed+inline"


def test_ink_without_a_renderer_is_unmeasured_never_a_pass(tmp_path, monkeypatch):
    no_pdfium(monkeypatch)
    path = tmp_path / "rgb.pdf"
    letter(bleed=True).export(path)
    report = verify(path, {"ink_limit": 300})
    assert report["passed"] and report["outcome"]["validation"] == "incomplete"
    assert [i["code"] for i in report["issues"]] == ["unmeasured"]


def test_fillable_pdf_has_its_form_fields(tmp_path):
    p = Project(600, 400, "white")
    p.apply({"type": "field", "kind": "text", "name": "email", "key": "email", "label": "Email", "x": 20, "y": 20, "width": 300, "height": 40})
    path = tmp_path / "form.pdf"
    p.export(path, fillable=True)
    assert inspect(path)["forms"]["fields"] >= 1
    assert verify(path, {"fillable": True})["passed"]
    flat = tmp_path / "flat.pdf"
    p.export(flat)
    assert codes(verify(flat, {"fillable": True})) == ["fillable"]


def test_object_streams_are_read_by_the_byte_scan(monkeypatch):
    no_pdfium(monkeypatch)
    font = b"<< /Type /Font /Subtype /TrueType /BaseFont /Arial /FontDescriptor 5 0 R >>"
    descriptor = b"<< /Type /FontDescriptor /FontName /Arial >>"
    header = b"4 0 5 %d " % (len(font) + 1)
    stream = header + font + b" " + descriptor
    data = pdf({
        1: b"<< /Type /Catalog /Pages 2 0 R >>",
        2: b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        3: b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 200] >>",
        6: (b"<< /Type /ObjStm /N 2 /First %d /Filter /FlateDecode /Length LEN >>" % len(header),
            zlib.compress(stream)),
    })
    facts = inspect("compressed.pdf", data=data)
    assert facts["fonts_unembedded"] == ["Arial"] and facts["pages"] == 1


# ------------------------------------------------------------------------------------------------- raster


def test_png_over_max_bytes_and_raster_facts(tmp_path):
    path = tmp_path / "banner.png"
    p = Project(1920, 600, "#336699")
    p.apply({"type": "text", "name": "t", "text": "Sale", "size": 200, "x": 100, "y": 100})
    p.export(path)
    facts = inspect(path)
    assert facts["width"] == 1920 and facts["height"] == 600 and facts["format"] == "png"
    assert facts["color"] == {"space": "RGB", "mode": "RGB", "alpha": False, "icc_profile": False}
    assert len(facts["sha256"]) == 64
    report = verify(path, {"preset": "web-banner", "max_bytes": 1000})
    assert codes(report) == ["max-bytes"]
    finding = report["issues"][0]
    assert finding["expected"] == 1000 and finding["actual"] == facts["bytes"]
    assert verify(path, "web-banner")["passed"]


def test_instagram_feed_size_alpha_and_format(tmp_path):
    square = tmp_path / "post.jpg"
    Project(1080, 1080, "white").export(square)
    assert verify(square, "instagram-feed")["passed"]
    clear = tmp_path / "clear.png"
    Project(1080, 2000, "transparent").export(clear)
    assert sorted(codes(verify(clear, "instagram-feed"))) == ["alpha", "aspect"]
    assert codes(verify(clear, {"formats": ["jpg"]})) == ["format"]


def test_a_file_whose_name_lies_about_its_format(tmp_path):
    path = tmp_path / "photo.png"
    Image.new("RGB", (10, 10), "red").save(path, "JPEG")
    assert codes(verify(path)) == ["format-mismatch"]


# ------------------------------------------------------------------------------------------------- PPTX


def test_pptx_keeps_editable_text(tmp_path):
    p = Project(1920, 1080, "white")
    p.apply({"type": "text", "name": "title", "text": "Quarterly", "size": 120, "x": 100, "y": 100})
    path = tmp_path / "deck.pptx"
    p.export(path)
    facts = inspect(path)
    assert facts["slides"] == 1 and facts["text_frames"] >= 1 and facts["charts"] == 0
    expect = export_checks.expectations(p)
    assert expect["text"] == 1
    assert verify(path, "slides-pptx", expect=expect)["passed"]
    # The same deck with its text runs removed: the text became pictures.
    flat = tmp_path / "flat.pptx"
    with zipfile.ZipFile(path) as source, zipfile.ZipFile(flat, "w") as target:
        for item in source.infolist():
            data = source.read(item)
            if item.filename.startswith("ppt/slides/slide"):
                data = data.replace(b"Quarterly", b"")
            target.writestr(item, data)
    assert codes(verify(flat, "slides-pptx", expect=expect)) == ["editable-text"]


# ------------------------------------------------------------------------------------------------- HTML, SVG


def test_html_with_an_external_url(tmp_path):
    page = tmp_path / "page.html"
    page.write_text('<!doctype html><html><head><link rel="stylesheet" href="https://cdn.example.com/a.css">'
                    '<style>body{background:url("bg.png")}</style></head><body>'
                    '<a href="https://example.com/more">More</a><img src="data:image/png;base64,AAAA">'
                    '<aside class="notes" hidden>Say hello</aside></body></html>', encoding="utf-8")
    facts = inspect(page)
    assert facts["remote"] == 1 and facts["external_count"] == 2 and facts["links"] == 1 and facts["notes"] == 1
    report = verify(page, "web-html")
    assert sorted(codes(report)) == ["linked-file", "remote-resource"]
    assert "cdn.example.com" in next(i["message"] for i in report["issues"] if i["code"] == "remote-resource")
    assert codes(verify(page, {"notes": False})) == ["notes"]


def test_vixl_html_and_svg_exports_are_self_contained(tmp_path):
    p = letter()
    for name in ("page.html", "page.svg"):
        p.export(tmp_path / name)
        report = verify(tmp_path / name)
        assert report["passed"] and report["facts"]["external_count"] == 0, name
    svg = tmp_path / "linked.svg"
    svg.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10">'
                   '<image href="https://example.com/x.png" width="10" height="10"/></svg>', encoding="utf-8")
    assert codes(verify(svg)) == ["remote-resource"]
    assert codes(verify(svg, {"text_as_text": True})) == ["text-as-text"]


# ------------------------------------------------------------------------------------------------- specs


def test_specs_are_data_and_typos_suggest_the_preset():
    assert {"print-letter-bleed", "instagram-feed", "web-banner", "default"} <= set(presets())
    with pytest.raises(VixlError, match="did you mean 'web-banner'"):
        resolve_spec("web-baner")
    with pytest.raises(VixlError, match="max_bytes"):
        resolve_spec({"max_byte": 10})
    assert resolve_spec({"preset": "instagram-feed", "max_bytes": 5})[1]["max_bytes"] == 5


def test_verification_is_read_only(tmp_path):
    path = tmp_path / "a.pdf"
    path.write_bytes(helvetica_pdf())
    before = (path.read_bytes(), path.stat().st_mtime_ns)
    verify(path, "print-letter-bleed")
    assert (path.read_bytes(), path.stat().st_mtime_ns) == before


# ------------------------------------------------------------------------------------------------- wiring


def test_project_export_reports_the_check_or_raises_without_a_report(tmp_path):
    p = Project(1080, 1080, "white")
    report = {}
    p.export(tmp_path / "a.png", spec={"max_bytes": 10}, report=report)
    assert report["export_check"]["passed"] is False and (tmp_path / "a.png").exists()
    with pytest.raises(VixlError) as caught:
        p.export(tmp_path / "b.png", spec={"max_bytes": 10})
    assert caught.value.code == "export_check_failed" and (tmp_path / "b.png").exists()
    data = p.export(format="JPEG", check=True, report=(report := {}))
    assert data[:2] == b"\xff\xd8" and report["export_check"]["passed"] and "path" not in report["export_check"]
    # The export's own budget becomes a requirement.
    p.export(tmp_path / "c.png", check=True, max_bytes=10, report=(report := {}))
    assert codes(report["export_check"]) == ["max-bytes"]
    with pytest.raises(VixlError, match="Unknown delivery spec"):
        p.export(tmp_path / "d.png", spec="nope")
    assert not (tmp_path / "d.png").exists()


def test_mcp_export_and_batch_return_export_check(tmp_path):
    session = Session(workspace=tmp_path)
    session.create("post.vixl", 1080, 1080, "white")
    result = export_file(session, "post.jpg", document="post.vixl", spec="instagram-feed")
    assert result["export_check"]["passed"] and result["export_check"]["path"] == "post.jpg"
    assert result["outcome"]["validation"] == "passed" and result["outcome"]["review"] == "required"
    answer = asyncio.run(build_server(session).call_tool(
        "vixl_export", {"path": "big.png", "document": "post.vixl", "options": {"spec": {"max_bytes": 10}}}))
    payload = json.loads(answer[0].text) if isinstance(answer, list) else json.loads(answer[0][0].text)
    assert payload["export_check"]["passed"] is False
    assert payload["outcome"]["state"] == "validation_failed"
    batch = asyncio.run(build_server(session).call_tool("vixl_export", {"document": "post.vixl", "options": {
        "targets": [{"path": "one.png", "check": True}, {"path": "two.webp", "spec": "instagram-feed"}]}}))
    payload = json.loads(batch[0].text) if isinstance(batch, list) else json.loads(batch[0][0].text)
    first, second = payload["results"]
    assert first["export_check"]["passed"] and codes(second["export_check"]) == ["format"]


def test_campaign_run_records_the_export_check_and_holds_a_failing_output(tmp_path):
    from vixl.production import run

    p = Project(160, 100, "#102030")
    p.apply({"type": "text", "name": "title", "text": "Hello", "size": 24, "x": 10, "y": 10})
    good = run(p, {"rows": [{}], "export_check": {"max_bytes": 1_000_000}},
               tmp_path / "good")
    result = good["results"][0]
    assert result["status"] == "completed" and result["export_check"]["passed"]
    manifest = json.loads((tmp_path / "good" / "production.json").read_text())
    assert manifest["results"][0]["export_check"]["path"] == result["output"]
    held = run(p, {"rows": [{}], "export_check": {"max_bytes": 10}}, tmp_path / "held")
    result = held["results"][0]
    assert result["status"] == "needs_review" and codes(result["export_check"]) == ["max-bytes"]
    assert result["outcome"]["validation"] == "failed" and "output" not in result
    assert not list((tmp_path / "held").glob("0001-*"))
    assert held["withheld"]["rules"][0]["rule"] == "export.max-bytes"
    with pytest.raises(VixlError, match="Unknown delivery spec"):
        run(p, {"rows": [{}], "export_check": "nope"}, tmp_path / "bad")


def test_cli_check_file_exit_code_and_presets(tmp_path):
    path = tmp_path / "a.pdf"
    path.write_bytes(helvetica_pdf())

    def cli(*args):
        return subprocess.run([sys.executable, "-m", "vixl", "--json", "check-file", *args], cwd=tmp_path,
                              capture_output=True, timeout=60)

    done = cli("a.pdf", "--spec", "office-pdf")
    assert done.returncode == 1, done.stderr.decode()
    assert json.loads(done.stdout)["issues"][0]["code"] == "font-not-embedded"
    done = cli("a.pdf", "--spec", '{"pages": 1}')
    assert done.returncode == 0 and json.loads(done.stdout)["passed"]
    listing = cli("--list")
    assert "print-letter-bleed" in json.loads(listing.stdout)["specs"]


def test_proof_pages_read_metadata_through_the_core(tmp_path):
    from vixl.model import Limits
    from vixl.plugins.workspace_qa import proof

    path = tmp_path / "a.pdf"
    letter(bleed=True).export(path, color_space="cmyk")
    meta = proof.describe(path, Limits())["meta"]
    assert meta["color"] == "DeviceCMYK" and meta["pages"] == 1 and meta["page_size"] == "630 × 810 pt"
    assert proof.pdf_metadata is export_checks.pdf_metadata


def test_a_package_lists_an_output_its_export_check_held(tmp_path):
    from vixl.production import run
    from vixl.workflows import dispatch

    p = Project(160, 100, "#102030")
    p.apply({"type": "text", "name": "title", "text": "Hello", "size": 24, "x": 10, "y": 10})
    run(p, {"rows": [{}, {}], "export_check": {"max_bytes": 10}}, tmp_path / "run")
    with pytest.raises(VixlError, match="held") as caught:
        dispatch(Session(None, workspace=tmp_path), "package", {"production": "run/production.json", "output": "p.zip"})
    held = caught.value.details["held"]
    assert [entry["rules"] for entry in held] == [["export.max-bytes"]] * 2
    assert "export.max-bytes" in held[0]["reason"]


def test_package_facts_come_from_the_core_inspector(tmp_path):
    from vixl.plugins.workspace_qa import package

    path = tmp_path / "a.png"
    Project(30, 20, "white").export(path)
    assert package.inspect_file(path) == inspect(path)
