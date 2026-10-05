import io
import zipfile

import numpy as np
import pytest

from vixl import Project
from vixl.commands import compile_command
from vixl.errors import VixlError
from vixl.forms import FieldValueError, coerce, fill, fill_data, summary, with_values


def form(path=None):
    p = Project.sized("letter", "#ffffff")
    p.apply([
        {"type": "text", "name": "title", "text": "Event registration", "x": 225, "y": 225, "size": 96, "color": "#111"},
        {"type": "text", "name": "name-label", "text": "Full name", "x": 225, "y": 520, "size": 42, "color": "#333"},
        {"type": "field", "name": "full_name", "kind": "text", "label_layer": "name-label",
         "x": 225, "y": 580, "width": 2100, "height": 125, "required": True, "max_length": 80, "size": 42},
        {"type": "field", "name": "email", "kind": "text", "format": "email", "label": "Email address",
         "x": 225, "y": 840, "width": 2100, "height": 125, "required": True, "size": 42},
        {"type": "field", "name": "plan-annual", "key": "plan", "kind": "radio", "option": "annual",
         "label": "Annual", "group_label": "Membership plan", "x": 225, "y": 1100, "width": 60, "height": 60},
        {"type": "field", "name": "plan-monthly", "key": "plan", "kind": "radio", "option": "monthly",
         "label": "Monthly", "x": 225, "y": 1200, "width": 60, "height": 60},
        {"type": "field", "name": "newsletter", "kind": "checkbox", "label": "Send me the newsletter",
         "x": 225, "y": 1400, "width": 60, "height": 60},
        {"type": "field", "name": "size", "kind": "dropdown", "label": "T-shirt size",
         "options": ["S", "M", {"value": "L", "label": "Large"}], "x": 225, "y": 1600, "width": 600, "height": 125, "size": 42},
        {"type": "field", "name": "signature", "kind": "signature", "label": "Signature",
         "x": 225, "y": 2900, "width": 1200, "height": 160},
    ])
    if path:
        p.save(path)
    return p


def test_field_operations_aliases_and_defaults():
    p = Project.sized("letter", "#ffffff")
    result = p.apply([{"type": "input", "kind": "textbox", "name": "a", "label": "A", "fill": "#eee"},
                      {"type": "form-field", "kind": "textarea", "name": "b", "label": "B", "y": 400},
                      {"type": "field", "kind": "select", "name": "c", "label": "C", "options": ["x"], "y": 1200},
                      {"type": "field", "kind": "tickbox", "name": "d", "label": "D", "y": 1600}])
    assert any("'input'" in note for note in result["normalized"])
    kinds = {layer["name"]: layer["field"]["kind"] for layer in p.state["layers"]}
    assert kinds == {"a": "text", "b": "multiline", "c": "dropdown", "d": "checkbox"}
    a = p.layer("a")
    assert a["appearance"]["fill"] == "#eee" and a["field"]["key"] == "a"
    assert p.layer("d")["width"] == p.layer("d")["height"] == round(14 * 300 / 72)
    assert a["height"] == round(a["size"] * 1.5 + 2 * a["padding"])


@pytest.mark.parametrize("ops, message", [
    ([{"type": "field", "kind": "text", "name": "x"}], "accessible name"),
    ([{"type": "field", "kind": "text", "name": "x", "label": "X", "key": "bad.key"}], "no dots"),
    ([{"type": "field", "kind": "text", "name": "x", "label": "X"}, {"type": "field", "kind": "text", "name": "y", "key": "x",
      "label": "Y"}], "used more than once"),
    ([{"type": "variable", "name": "x", "value": 1}, {"type": "field", "kind": "text", "name": "x", "label": "X"}], "variable"),
    ([{"type": "field", "kind": "dropdown", "name": "x", "label": "X", "options": ["a", "a"]}], "unique"),
    ([{"type": "field", "kind": "text", "name": "x", "label": "X", "comb": True}], "max_length"),
    ([{"type": "field", "kind": "text", "name": "x", "label": "X", "max_length": 3, "default": "toolong"}], "max_length"),
    ([{"type": "field", "kind": "radio", "name": "a", "key": "g", "option": "one", "label": "A", "required": True},
      {"type": "field", "kind": "radio", "name": "b", "key": "g", "option": "two", "label": "B", "y": 200}], "agree"),
    ([{"type": "field", "kind": "number", "name": "x", "label": "X", "default": "abc"}], "number"),
])
def test_field_validation(ops, message):
    p = Project.sized("letter", "#ffffff")
    with pytest.raises(VixlError) as error:
        p.apply(ops)
    assert message in str(error.value)


def test_rotate_duplicate_and_remove_rules():
    p = form()
    with pytest.raises(VixlError):
        p.apply({"type": "rotate", "target": "email", "value": 10})
    with pytest.raises(VixlError):
        p.apply({"type": "flip", "target": "email", "direction": "horizontal"})
    p.apply({"type": "duplicate", "target": "email"})
    assert p.layer("email copy")["field"]["key"] == "email-2"
    p.apply({"type": "duplicate", "target": "plan-annual"})
    copy = p.layer("plan-annual copy")["field"]
    assert copy["key"] == "plan" and copy["option"] == "annual-2"
    p.apply({"type": "remove", "target": "name-label"})
    assert "label_layer" not in p.layer("full_name")["field"]
    issues = p.check(checks=["form"])["issues"]
    assert any("accessible name" in issue["message"] for issue in issues)


@pytest.mark.parametrize("record, raw, expected", [
    ({"kind": "text"}, 42, ("42", "42")),
    ({"kind": "multiline"}, "a\r\nb", ("a\nb", "a\nb")),
    ({"kind": "number", "format": {"decimals": 2}}, "3.5", (3.5, "3.50")),
    ({"kind": "number"}, 7, (7.0, "7")),
    ({"kind": "date", "format": {"display": "D/M/YYYY"}}, "2026-03-09", ("2026-03-09", "9/3/2026")),
    ({"kind": "checkbox"}, "YES", (True, "x")),
    ({"kind": "checkbox"}, "", (False, "")),
    ({"kind": "checkbox"}, "x", (True, "x")),
    ({"kind": "dropdown", "options": ["S", {"value": "L", "label": "Large"}]}, "L", ("L", "Large")),
    ({"kind": "dropdown", "options": ["S"], "editable": True}, "XL", ("XL", "XL")),
    ({"kind": "signature"}, "", (None, "")),
])
def test_coercion(record, raw, expected):
    assert coerce({"key": "k", **record}, raw) == expected


@pytest.mark.parametrize("record, raw, code", [
    ({"kind": "text"}, "a\nb", "invalid_format"),
    ({"kind": "text", "max_length": 2}, "abc", "too_long"),
    ({"kind": "text", "format": "digits"}, "12a", "invalid_format"),
    ({"kind": "text", "format": "email"}, "no at", "invalid_format"),
    ({"kind": "number", "format": {"min": 0, "max": 10}}, 11, "invalid_number"),
    ({"kind": "number"}, "ten", "invalid_number"),
    ({"kind": "date"}, "2026-02-30", "invalid_date"),
    ({"kind": "date"}, "09/03/2026", "invalid_date"),
    ({"kind": "checkbox"}, "maybe", "invalid_format"),
    ({"kind": "dropdown", "options": ["S"]}, "XL", "invalid_option"),
    ({"kind": "radio", "option": "a"}, "b", "invalid_option"),
    ({"kind": "signature"}, "Ada", "invalid_format"),
])
def test_coercion_errors(record, raw, code):
    with pytest.raises(FieldValueError) as error:
        coerce({"key": "k", **record}, raw)
    assert error.value.code == code


def test_values_render_and_never_touch_the_document(tmp_path):
    from vixl.render_cache import enable

    p = form()
    before = p.render()
    head = p.head
    view = with_values(p, {"full_name": "Ada Lovelace", "email": "ada@example.com", "plan": "annual", "newsletter": True})
    enable(p, tmp_path / "cache")
    after = view.render()
    assert p.head == head and not hasattr(p, "_form_values")
    region = (225, 580, 2325, 705)
    assert np.asarray(before.crop(region)).std() < np.asarray(after.crop(region)).std()
    assert view._disk_cache is None
    p.render()  # the plain document may use the cache
    with_values(p, {"full_name": "Grace", "email": "g@h.i"}).render()
    cached = list((tmp_path / "cache").rglob("*.png"))
    assert all(b"Grace" not in path.read_bytes() for path in cached)


def test_field_values_are_variables():
    p = form()
    p.apply({"type": "text", "name": "greeting", "text": "Hello ${full_name}", "x": 225, "y": 3100, "size": 42,
             "color": "#000"})
    view = with_values(p, {"full_name": "Ada", "email": "a@b.c"})
    from vixl.render import resolved_layers

    greeting = next(layer for layer in resolved_layers(view) if layer["name"] == "greeting")
    assert greeting["text"] == "Hello Ada"
    issues = p.check(checks=["form"])["issues"]
    assert any("greeting" in issue["message"] and "fillable" in issue["message"] for issue in issues)


def test_overflow_modes():
    p = Project.sized("letter", "#ffffff")
    p.apply([{"type": "field", "kind": "text", "name": key, "label": key, "width": 400, "height": 80, "size": 40,
              "overflow": mode, "y": 200 * i} for i, (key, mode) in enumerate((("s", "shrink"), ("c", "clip"), ("e", "error")))])
    long = "A rather long value for a small box"
    shrink = with_values(p, {"s": "Somewhat long text"})
    from vixl.forms import overflow_report

    assert overflow_report(shrink) == []
    reports = {r["key"]: r["code"] for r in overflow_report(with_values(p, {"s": long * 3, "c": long, "e": long}))}
    assert reports == {"s": "overflow", "c": "clipped", "e": "overflow"}


def test_fill_single_and_batch(tmp_path):
    pypdf = pytest.importorskip("pypdf")
    p = form()
    report = fill(p, {"full_name": "Ada Lovelace", "email": "ada@example.com", "size": "L"}, tmp_path / "ada.pdf")
    text = pypdf.PdfReader(tmp_path / "ada.pdf").pages[0].extract_text()
    assert "Ada Lovelace" in text and "Large" in text and report["warnings"] == []
    with pytest.raises(VixlError) as error:
        fill(p, {"full_name": "Ada"}, tmp_path / "missing.png")
    assert error.value.details["errors"][0]["code"] == "missing_required"
    assert "Ada" not in str(error.value)
    with pytest.raises(VixlError) as error:
        fill(p, {"full_name": "Ada", "email": "a@b.c", "nmae": "typo"}, tmp_path / "typo.png")
    assert error.value.details["errors"][0]["code"] == "unknown_key"

    rows = tmp_path / "rows.csv"
    rows.write_text("full_name,email,plan\nAda Lovelace,ada@example.com,annual\n,bob@example.com,weekly\n"
                    "Grace Hopper,grace@example.com,monthly\n")
    with pytest.raises(VixlError) as error:
        fill_data(p, rows, tmp_path / "out")
    errors = error.value.details["report"]["errors"]
    assert {(e["row"], e["key"], e["code"]) for e in errors} == {(2, "plan", "invalid_option"), (2, "full_name", "missing_required")}
    assert not (tmp_path / "out").exists()
    dry = fill_data(p, rows, dry_run=True)
    assert dry["valid"] == 2 and dry["invalid"] == [2]
    result = fill_data(p, rows, tmp_path / "out", name="{full_name}", skip_invalid=True, format="png")
    assert sorted(path.name for path in (tmp_path / "out").iterdir()) == ["Ada-Lovelace.png", "Grace-Hopper.png"]
    assert len(result["outputs"]) == 2
    combined = fill_data(p, rows, combine=tmp_path / "all.pdf", skip_invalid=True)
    reader = pypdf.PdfReader(tmp_path / "all.pdf")
    assert len(reader.pages) == 2 and "Grace Hopper" in reader.pages[1].extract_text() and combined["valid"] == 2
    collide = tmp_path / "same.csv"
    collide.write_text("full_name,email\nAda,a@b.c\nAda,c@d.e\n")
    with pytest.raises(VixlError) as error:
        fill_data(p, collide, tmp_path / "same", name="{full_name}")
    assert "both be named" in str(error.value)


def walk(value, seen, found):
    import pypdf

    if isinstance(value, pypdf.generic.IndirectObject):
        if value.idnum in seen:
            return
        seen.add(value.idnum)
        value = value.get_object()
    if isinstance(value, dict):
        for key, item in value.items():
            found.add(key)
            walk(item, seen, found)
    elif isinstance(value, list):
        for item in value:
            walk(item, seen, found)


def test_fillable_pdf_structure():
    pypdf = pytest.importorskip("pypdf")
    p = form()
    p.apply({"type": "form", "lang": "en-US", "title": "Registration"})
    data = p.export(format="PDF", fillable=True)
    assert data == p.export(format="PDF", fillable=True), "fillable PDFs are byte-identical"
    assert b"NeedAppearances" not in data
    reader = pypdf.PdfReader(io.BytesIO(data))
    fields = reader.get_fields()
    assert set(fields) == {"full_name", "email", "plan", "newsletter", "size", "signature"}
    assert fields["full_name"]["/FT"] == "/Tx" and fields["full_name"]["/Ff"] & 2 and fields["full_name"]["/TU"] == "Full name"
    assert fields["plan"]["/FT"] == "/Btn" and fields["plan"]["/Ff"] & (1 << 15) and fields["plan"]["/TU"] == "Membership plan"
    assert fields["size"]["/FT"] == "/Ch" and fields["size"]["/Ff"] & (1 << 17)
    assert [list(pair) for pair in fields["size"]["/Opt"]] == [["S", "S"], ["M", "M"], ["L", "Large"]]
    assert fields["signature"]["/FT"] == "/Sig"
    root = reader.trailer["/Root"]
    assert root["/Lang"] == "en-US" and reader.metadata.title == "Registration"
    assert root["/ViewerPreferences"]["/DisplayDocTitle"]
    annots = [a.get_object() for a in reader.pages[0]["/Annots"]]
    order = [a.get("/T") or a["/Parent"]["/T"] for a in annots]
    assert order == ["full_name", "email", "plan", "plan", "newsletter", "size", "signature"]
    rect = [float(v) for v in annots[0]["/Rect"]]
    assert rect == pytest.approx([54.0, 792 - (580 + 125) * 0.24, (225 + 2100) * 0.24, 792 - 580 * 0.24], abs=0.01)
    keys = set()
    walk(reader.trailer, set(), keys)
    assert not keys & {"/A", "/AA", "/OpenAction", "/JS", "/JavaScript", "/URI", "/SubmitForm", "/Launch"}


def test_hostile_strings_round_trip():
    pypdf = pytest.importorskip("pypdf")
    hostile = "a(b)c\\d>>e endstream <x> /Name 日本語 😀"
    p = Project.sized("letter", "#ffffff")
    p.apply([{"type": "field", "kind": "dropdown", "name": "pick", "label": hostile, "options": [hostile, "plain"],
              "editable": True},
             {"type": "field", "kind": "radio", "name": "r1", "key": "r", "option": "a(b)#c", "label": hostile,
              "group_label": hostile, "y": 400},
             {"type": "field", "kind": "radio", "name": "r2", "key": "r", "option": "two", "label": "two", "y": 600}])
    data = p.export(format="PDF", fillable=True)
    reader = pypdf.PdfReader(io.BytesIO(data))
    fields = reader.get_fields()
    assert fields["pick"]["/TU"] == hostile and fields["pick"]["/Opt"][0][0] == hostile
    states = [list(kid.get_object()["/AP"]["/N"]) for kid in reader.trailer["/Root"]["/AcroForm"]["/Fields"][1].get_object()["/Kids"]]
    assert "/a(b)#c" in states[0]
    assert hostile.encode("utf-8") not in data and b"(b)" not in data, "strings are always hex"


def test_fillable_pdf_matches_the_png_and_fills_elsewhere():
    pdfium = pytest.importorskip("pypdfium2")
    pypdf = pytest.importorskip("pypdf")
    p = form()
    p.apply({"type": "field-set", "target": "newsletter", "default": True})
    data = p.export(format="PDF", fillable=True)
    document = pdfium.PdfDocument(data)
    document.init_forms()
    image = document[0].render(scale=300 / 72, may_draw_forms=True).to_pil().convert("RGB").crop((0, 0, 2550, 3300))
    png = p.render().convert("RGB")
    assert np.abs(np.asarray(image, float) - np.asarray(png, float)).mean() < 2
    writer = pypdf.PdfWriter(clone_from=pypdf.PdfReader(io.BytesIO(data)))
    writer.update_page_form_field_values(writer.pages[0], {"full_name": "Ada Lovelace"}, auto_regenerate=False)
    buffer = io.BytesIO()
    writer.write(buffer)
    filled = pdfium.PdfDocument(buffer.getvalue())
    filled.init_forms()
    after = np.asarray(filled[0].render(scale=1, may_draw_forms=True).to_pil().convert("L"))
    before = np.asarray(document[0].render(scale=1, may_draw_forms=True).to_pil().convert("L"))
    inside = (slice(145, 164), slice(60, 550))  # within the full_name box, 139–169 × 54–558 pt
    assert before[inside].min() > 200 and after[inside].min() < 128, "the typed value shows inside its box"


def test_editable_prefill():
    pypdf = pytest.importorskip("pypdf")
    p = form()
    data = p.export(format="PDF", fillable=True, values={"full_name": "Ada", "email": "a@b.c", "plan": "monthly"})
    fields = pypdf.PdfReader(io.BytesIO(data)).get_fields()
    assert fields["full_name"]["/V"] == "Ada" and fields["plan"]["/V"] == "/monthly"
    with pytest.raises(VixlError):
        p.export(format="PDF", fillable=True, values={"full_name": "Zoë 日本", "email": "a@b.c"})


def test_form_checks():
    p = form()
    assert p.check(checks=["form"])["passed"]
    p.apply([{"type": "field", "kind": "text", "name": "clash", "label": "Clash", "x": 300, "y": 600, "width": 300,
              "height": 125, "size": 42},
             {"type": "field", "kind": "checkbox", "name": "tiny", "label": "Tiny", "x": 1500, "y": 1400, "width": 20,
              "height": 20},
             {"type": "field", "kind": "text", "name": "faint", "label": "Faint", "x": 225, "y": 2400, "width": 600,
              "height": 125, "size": 42, "appearance": {"stroke": "#f2f2f2", "fill": "#ffffff"}},
             {"type": "form", "tab_order": "explicit"}])
    issues = p.check(checks=["form"])["issues"]
    messages = " | ".join(issue["message"] for issue in issues)
    assert "overlap" in messages and "smaller than 10 pt" in messages and "contrast" in messages
    assert "Explicit tab order" in messages
    worst = p.check(checks=["form"], sample="worst")["issues"]
    assert any("does not fit" in issue["message"] for issue in worst)
    pixel = Project(400, 300, "#ffffff")
    pixel.apply({"type": "field", "kind": "text", "name": "x", "label": "X", "width": 200, "height": 40})
    assert any("physical size" in issue["message"] for issue in pixel.check(checks=["form"])["issues"])


def test_svg_shows_fields_as_vectors():
    p = form()
    svg = p.export(format="SVG").decode()
    assert "<image" not in svg


def test_summary_and_tab_order():
    p = form()
    fields = summary(p)
    assert [f["key"] for f in fields] == ["full_name", "email", "plan", "plan", "newsletter", "size", "signature"]
    assert [f["tab"] for f in fields] == [1, 2, 3, 3, 4, 5, 6]
    assert fields[0]["rect_pt"] == pytest.approx([54.0, 622.8, 558.0, 652.8])
    from vixl.changes import summarize

    assert summarize(p)["fields"][0]["key"] == "full_name"


def test_multi_page_form():
    pypdf = pytest.importorskip("pypdf")
    p = form()
    p.apply([{"type": "page", "action": "add", "name": "consent"},
             {"type": "field", "kind": "checkbox", "name": "agree", "label": "I agree", "x": 225, "y": 400, "width": 60,
              "height": 60, "required": True},
             {"type": "text", "name": "who", "text": "Signed by ${full_name}", "x": 225, "y": 600, "size": 42, "color": "#000"}])
    reader = pypdf.PdfReader(io.BytesIO(p.export(format="PDF", fillable=True)))
    assert len(reader.pages) == 2 and "agree" in reader.get_fields()
    assert [a.get_object()["/T"] for a in reader.pages[1]["/Annots"]] == ["agree"]
    filled = pypdf.PdfReader(io.BytesIO(p.export(format="PDF", values={"full_name": "Ada", "email": "a@b.c", "agree": "yes"})))
    assert "Signed by Ada" in filled.pages[1].extract_text()
    with pytest.raises(VixlError):
        p.apply({"type": "field", "kind": "text", "name": "dupe", "key": "email", "label": "E", "y": 900})


def test_cli_and_workflow(tmp_path):
    from vixl.cli import dispatch
    from vixl.interfaces import Session
    from vixl.workflows import dispatch as workflow

    assert compile_command("field add phone --kind text --label Phone --required --max-length 12 --x 10") == {
        "type": "field", "key": "phone", "name": "phone", "kind": "text", "label": "Phone", "required": True,
        "max_length": 12, "x": 10}
    assert compile_command("field set phone --options a,b --not-required") == {
        "type": "field-set", "target": "phone", "options": ["a", "b"], "required": False}
    assert compile_command("form settings --tab-order explicit --lang en-GB") == {
        "type": "form", "tab_order": "explicit", "lang": "en-GB"}
    path = tmp_path / "form.vixl"
    form(path)
    listed, _ = dispatch(["-p", str(path), "field", "list"])
    assert listed["fields"][0]["key"] == "full_name"
    result, _ = dispatch(["-p", str(path), "form", "fill", "--set", "full_name=Ada", "--set", "email=a@b.c",
                          "--out", str(tmp_path / "ada.png")])
    assert (tmp_path / "ada.png").exists() and result["warnings"] == []
    dispatch(["-p", str(path), "render", "--out", str(tmp_path / "f.png"), "--show-fields", "--set", "full_name=Ada"])
    dispatch(["-p", str(path), "export", str(tmp_path / "blank.pdf"), "--fillable"])
    assert (tmp_path / "blank.pdf").read_bytes().startswith(b"%PDF")
    (tmp_path / "rows.csv").write_text("full_name,email\nAda,a@b.c\nGrace,g@h.i\n")
    session = Session(path)
    report = workflow(session, "form-fill", {"data": "rows.csv", "combine": "all.pdf"})
    assert report["valid"] == 2 and report["output"] == "all.pdf"
    single = workflow(session, "form-fill", {"values": {"full_name": "Ada", "email": "a@b.c"}, "output": "one.pdf"})
    assert single["output"] == "one.pdf"


def test_form_fill_job_deletes_its_data(tmp_path):
    from vixl.jobs import Queue

    form(tmp_path / "form.vixl")
    (tmp_path / "rows.csv").write_text("full_name,email\nAda,a@b.c\nGrace,g@h.i\n")
    queue = Queue(tmp_path)
    job = queue.submit({"kind": "form-fill", "source": "form.vixl", "output": "filled.zip",
                        "request": {"data": "rows.csv", "format": "png", "name": "{full_name}"}})
    frozen = tmp_path / job["payload"]["request"]["data"]
    assert frozen.exists()
    done = queue.work_one(job["id"])
    assert done["status"] == "completed", done
    assert sorted(zipfile.ZipFile(tmp_path / "filled.zip").namelist()) == ["Ada.png", "Grace.png"]
    assert not frozen.exists(), "the job's copy of the data is deleted"
