"""Required signatures, multiline limits, validation rules as PDF actions and tab order (T06
evaluation, #77). Forms are letter pages at 72 dpi (one pixel per point) so the tests stay quick."""

import io
import json
import shutil
import subprocess

import pytest

from vixl import Project
from vixl.commands import compile_command
from vixl.errors import VixlError
from vixl.form_rules import check_pattern, scripts
from vixl.forms import FieldValueError, coerce, fill, with_values


def contract():
    p = Project.sized("letter", "#ffffff", dpi=72)
    p.apply([
        {"type": "field", "name": "email", "kind": "text", "format": "email", "label": "Email", "x": 54, "y": 48,
         "width": 288, "height": 26, "required": True},
        {"type": "field", "name": "performers", "kind": "number", "format": {"decimals": 0, "min": 1, "max": 6},
         "label": "Performers", "x": 54, "y": 96, "width": 96, "height": 26},
        {"type": "field", "name": "when", "kind": "date", "label": "Date", "x": 54, "y": 144, "width": 144, "height": 26},
        {"type": "field", "name": "code", "kind": "text", "pattern": "[A-Z]{2}-[0-9]{4}", "message": "Use AB-1234",
         "label": "Code", "x": 54, "y": 192, "width": 144, "height": 26},
        {"type": "field", "name": "pieces", "kind": "multiline", "max_length": 300, "label": "Pieces", "x": 54, "y": 240,
         "width": 288, "height": 96},
        {"type": "field", "name": "sig", "kind": "signature", "required": True, "label": "Signature", "x": 54, "y": 384,
         "width": 288, "height": 38},
    ])
    return p


def widgets(p):
    pypdf = pytest.importorskip("pypdf")
    reader = pypdf.PdfReader(io.BytesIO(p.export(format="PDF", fillable=True)))
    return reader, {a.get_object()["/T"]: a.get_object() for a in reader.pages[0]["/Annots"]}


def scripts_of(p):
    return {key: {event: action["/JS"] for event, action in field["/AA"].items()}
            for key, field in widgets(p)[1].items() if "/AA" in field}


def test_signature_fields_can_be_required():
    p = contract()
    assert widgets(p)[1]["sig"]["/FT"] == "/Sig" and widgets(p)[1]["sig"]["/Ff"] & 2
    p.apply({"type": "field-set", "target": "sig", "required": False})
    assert not widgets(p)[1]["sig"].get("/Ff")
    p.apply({"type": "field-set", "target": "sig", "required": True})
    # A signature is signed in a viewer, so a fill needs every other required field but not that one.
    assert fill(p, {"email": "a@b.c"})["warnings"] == []
    # A sample signature is drawn into a flattened fill, but never set as the PDF field's value.
    assert fill(p, {"email": "a@b.c", "sig": "Ada"})["warnings"] == []
    with pytest.raises(VixlError):
        fill(p, {"email": "a@b.c", "sig": "Ada"}, format="PDF", mode="editable")
    with pytest.raises(VixlError) as error:
        fill(p, {})
    assert [e["key"] for e in error.value.details["errors"]] == ["email"]


def test_multiline_fields_take_max_length():
    p = contract()
    assert widgets(p)[1]["pieces"]["/Ff"] & 4096 and widgets(p)[1]["pieces"]["/MaxLen"] == 300
    with pytest.raises(FieldValueError) as error:
        coerce(p.layer("pieces")["field"], "x" * 301)
    assert error.value.code == "too_long"
    assert coerce(p.layer("pieces")["field"], "line\nline")[1] == "line\nline"
    with pytest.raises(VixlError) as error:
        p.apply({"type": "field-set", "target": "pieces", "comb": True})
    assert "comb" in str(error.value)
    with pytest.raises(VixlError) as error:
        p.apply({"type": "field-set", "target": "sig", "max_length": 5})
    assert "multiline" in str(error.value)


def test_validation_rules_are_exported_as_pdf_actions():
    p = contract()
    data = p.export(format="PDF", fillable=True)
    assert data == p.export(format="PDF", fillable=True) and b"NeedAppearances" not in data
    js = scripts_of(p)
    assert set(js) == {"email", "performers", "when", "code"}
    assert all(action["/S"] == "/JavaScript" for field in widgets(p)[1].values() for action in field.get("/AA", {}).values())
    assert list(js["email"]) == ["/V"] and "name@example.com" in js["email"]["/V"]
    assert r"[^@\s]+@[^@\s]+" in js["email"]["/V"]
    assert js["performers"] == {"/K": 'AFNumber_Keystroke(0, 1, 0, 0, "", true);',
                                "/F": 'AFNumber_Format(0, 1, 0, 0, "", true);',
                                "/V": "AFRange_Validate(true, 1, true, 6);"}
    assert js["when"] == {"/K": 'AFDate_KeystrokeEx("yyyy-mm-dd");', "/F": 'AFDate_FormatEx("yyyy-mm-dd");'}
    assert '"^(?:[A-Z]{2}-[0-9]{4})$"' in js["code"]["/V"] and "Use AB-1234" in js["code"]["/V"]
    # Nothing else is active: no links, submit, launch or open actions.
    assert not any(token in data for token in (b"/URI", b"/SubmitForm", b"/Launch", b"/OpenAction", b"/GoTo"))
    # The date display shapes the picture; digits get a keystroke filter; a message replaces the default.
    p.apply([{"type": "field-set", "target": "when", "format": {"display": "D/M/YYYY"}},
             {"type": "field", "name": "zip", "kind": "text", "format": "digits", "label": "Zip", "x": 400, "y": 48,
              "width": 72, "height": 26},
             {"type": "field", "name": "ratio", "kind": "number", "format": {"min": 0.5}, "message": "At least half",
              "label": "Ratio", "x": 400, "y": 96, "width": 72, "height": 26}])
    js = scripts_of(p)
    assert js["when"]["/K"] == 'AFDate_KeystrokeEx("d/m/yyyy");'
    assert list(js["zip"]) == ["/K", "/V"] and "0-9" in js["zip"]["/K"]
    assert list(js["ratio"]) == ["/K", "/V"] and "At least half" in js["ratio"]["/V"] and "AFRange" not in js["ratio"]["/V"]


def test_blank_forms_without_rules_have_no_actions():
    p = Project.sized("letter", "#ffffff", dpi=72)
    p.apply({"type": "field", "name": "name", "kind": "text", "label": "Name", "x": 54, "y": 48, "width": 288, "height": 26})
    data = p.export(format="PDF", fillable=True)
    assert not any(token in data for token in (b"/AA", b"/JS", b"/JavaScript", b"/S /JavaScript"))


def test_scripts_behave_in_a_javascript_engine():
    node = shutil.which("node")
    if not node:
        pytest.skip("node is not installed")
    records = {"email": {"kind": "text", "format": "email"}, "digits": {"kind": "text", "format": "digits"},
               "code": {"kind": "text", "pattern": r"[A-Z]{2}-\d{4}", "message": 'Say "AB-1234"'},
               "free": {"kind": "number"}, "ranged": {"kind": "number", "format": {"min": 1, "max": 6}, "message": "1 to 6"},
               "standard": {"kind": "number", "format": {"decimals": 2, "min": 1, "max": 6}},
               "date": {"kind": "date", "format": {"display": "MM/DD/YYYY"}}}
    harness = """
const scripts = JSON.parse(require('fs').readFileSync(0, 'utf8'));
const probes = {email: {V: ['', 'a@b.co', 'a b@c.d', 'plain']}, digits: {K: ['', '12', '1a'], V: ['', '007', '7x']},
  code: {V: ['', 'AB-1234', 'ab-1234', 'AB-12345']}, free: {K: ['4', '-1.5e3', 'x'], V: ['', '2.5', 'abc']},
  ranged: {V: ['', '1', '6', '0.9', '7']}, standard: {K: ['5'], F: ['5'], V: ['3']}, date: {K: ['x'], F: ['x']}};
const result = {};
for (const [name, events] of Object.entries(probes)) {
  result[name] = {};
  for (const [kind, values] of Object.entries(events)) {
    result[name][kind] = values.map((value) => {
      const calls = [];
      const event = kind === 'K' ? {rc: true, willCommit: false, change: value, value: ''} : {rc: true, willCommit: true, value};
      const record = (n) => (...a) => calls.push(n + '(' + a.map((x) => JSON.stringify(x)).join(', ') + ')');
      new Function('event', 'app', 'AFNumber_Keystroke', 'AFNumber_Format', 'AFRange_Validate', 'AFDate_KeystrokeEx',
                   'AFDate_FormatEx', scripts[name][kind])(event, {alert: (m) => calls.push('alert ' + m)},
                   record('AFNumber_Keystroke'), record('AFNumber_Format'), record('AFRange_Validate'),
                   record('AFDate_KeystrokeEx'), record('AFDate_FormatEx'));
      return [value, event.rc, calls];
    });
  }
}
console.log(JSON.stringify(result));
"""
    done = subprocess.run([node, "-e", harness], input=json.dumps({k: scripts(v) for k, v in records.items()}),
                          capture_output=True, text=True, timeout=60)
    assert done.returncode == 0, done.stderr
    result = json.loads(done.stdout)
    verdicts = {name: {kind: {value: rc for value, rc, _ in rows} for kind, rows in events.items()}
                for name, events in result.items()}
    assert verdicts["email"]["V"] == {"": True, "a@b.co": True, "a b@c.d": False, "plain": False}
    assert verdicts["digits"]["K"] == {"": True, "12": True, "1a": False}
    assert verdicts["digits"]["V"] == {"": True, "007": True, "7x": False}
    assert verdicts["code"]["V"] == {"": True, "AB-1234": True, "ab-1234": False, "AB-12345": False}
    assert verdicts["free"]["K"] == {"4": True, "-1.5e3": True, "x": False}
    assert verdicts["free"]["V"] == {"": True, "2.5": True, "abc": False}
    assert verdicts["ranged"]["V"] == {"": True, "1": True, "6": True, "0.9": False, "7": False}
    alerts = [calls for _, _, calls in result["code"]["V"] if calls]
    assert alerts and all(call == ['alert Say "AB-1234"'] for call in alerts), "the message survives quoting"
    assert result["standard"]["F"][0][2] == ['AFNumber_Format(2, 1, 0, 0, "", true)']
    assert result["date"]["K"][0][2] == ['AFDate_KeystrokeEx("mm/dd/yyyy")']


@pytest.mark.parametrize("pattern", [r"[A-Z]{2}-\d{4}", r"^\d{3}$", r"(\d{3}-){2}\d{4}", r"\(?\d+\)?",
                                     r"[\w.+-]+@[\w-]+\.[a-z]{2,}", r"(?:ab|cd)+", r"a{1,1000}"])
def test_portable_patterns_are_accepted(pattern):
    check_pattern(pattern)


@pytest.mark.parametrize("pattern, reason", [
    ("(a+)+$", "unbounded repeat"), ("(\\w+\\s?)*", "unbounded repeat"), ("(?=a)b", "look-around"),
    ("(a)\\1", "back-references"), ("(?i)abc", "flags"), ("(?P<n>a)", "named groups"), ("\\Aabc\\Z", "\\A"),
    ("a{1,5000}", "1000"), ("(a", "valid"), ("", "1–200"), ("x" * 201, "1–200"), ("a++", "possessive"),
])
def test_unsafe_patterns_are_rejected(pattern, reason):
    with pytest.raises(VixlError) as error:
        check_pattern(pattern)
    assert reason in str(error.value) and error.value.as_dict()["field"] == "pattern"


def test_pattern_rules_validate_fills_defaults_and_samples():
    p = contract()
    record = p.layer("code")["field"]
    assert coerce(record, "AB-1234") == ("AB-1234", "AB-1234")
    for bad in ("ab-1234", "AB-12345", "AB-1234 "):
        with pytest.raises(FieldValueError) as error:
            coerce(record, bad)
        assert error.value.code == "invalid_format" and bad not in error.value.message
    with pytest.raises(VixlError) as error:
        p.apply({"type": "field-set", "target": "code", "default": "nope"})
    assert "pattern" in str(error.value)
    with pytest.raises(VixlError) as error:
        p.apply({"type": "field-set", "target": "pieces", "pattern": "a"})
    assert "text fields" in str(error.value)
    with pytest.raises(VixlError) as error:
        p.apply({"type": "field-set", "target": "code", "pattern": "(a+)+"})
    assert "unbounded repeat" in str(error.value)
    p.apply({"type": "field-set", "target": "code", "default": "ZZ-0001"})
    assert fill(p, {"email": "a@b.c"})["warnings"] == []
    with pytest.raises(VixlError) as error:
        fill(p, {"email": "a@b.c", "code": "x"})
    assert error.value.details["errors"][0]["code"] == "invalid_format"
    # Worst-case samples are for fitting boxes: they need not match the pattern, and still draw.
    assert not any(i.get("code") == "invalid_format" for i in p.check(checks=["form"], sample="worst")["issues"])
    view = with_values(p, {"email": "a@b.c", "code": "AB-1234"}, rules=False)
    assert view.render().size == (612, 792)


def test_dates_a_viewer_cannot_enforce_are_flagged():
    p = contract()
    messages = " | ".join(i["message"] for i in p.check(checks=["form"])["issues"])
    assert "literal text" not in messages
    p.apply({"type": "field-set", "target": "when", "format": {"display": "Day D of M"}})
    assert "literal text" in " | ".join(i["message"] for i in p.check(checks=["form"])["issues"])
    assert "when" not in scripts_of(p)


def test_each_page_declares_its_tab_order():
    pypdf = pytest.importorskip("pypdf")
    p = contract()
    p.apply([{"type": "page", "action": "add", "name": "second"},
             {"type": "field", "name": "agree", "kind": "checkbox", "label": "Agree", "x": 20, "y": 20, "width": 20,
              "height": 20},
             {"type": "page", "action": "add", "name": "plain"},
             {"type": "text", "name": "note", "text": "No fields here", "x": 20, "y": 20, "size": 14}])
    reader = pypdf.PdfReader(io.BytesIO(p.export(format="PDF", fillable=True)))
    assert [page.get("/Tabs") for page in reader.pages] == ["/S", "/S", None]


def test_new_field_settings_are_typed_in_the_schema_and_cli():
    import jsonschema

    from vixl.schema import operation_schema

    assert compile_command("field add code --kind text --pattern [A-Z]{2} --message Capitals") == {
        "type": "field", "key": "code", "name": "code", "kind": "text", "pattern": "[A-Z]{2}", "message": "Capitals"}
    variants = {v["properties"]["type"]["const"]: v
                for v in operation_schema()["properties"]["operations"]["items"]["oneOf"]}
    for name in ("pattern", "message", "max_length", "required"):
        assert variants["field"]["properties"][name]["description"], name
    jsonschema.validate({"type": "field", "kind": "text", "label": "Code", "pattern": "[A-Z]+", "message": "Capitals"},
                        variants["field"])
    jsonschema.validate({"type": "field-set", "target": "code", "pattern": None, "message": None}, variants["field-set"])
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate({"type": "field", "kind": "text", "pattern": 5}, variants["field"])
