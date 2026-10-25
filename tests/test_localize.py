"""localize (#576, #171): one checked variant per locale, held locales, fit policy, RTL and re-runs."""

import json

import pytest

from vixl import Project
from vixl.errors import VixlError
from vixl.interfaces import Session
from vixl.workflows import dispatch

LOCALES = {
    "de": {"headline": "Sommerschlussverkauf mit riesigen Rabatten", "cta": "Jetzt kaufen"},
    "fr": {"headline": "Soldes d'été", "cta": "Acheter"},
    "es": {"headline": "Rebajas", "cta": "Comprar"},
    "ar": {"headline": "تخفيضات الصيف", "cta": "تسوق الآن"},
}


@pytest.fixture(autouse=True)
def no_local_faces(monkeypatch):
    monkeypatch.setattr("vixl.typefaces.local_script_faces", lambda families: [])


def master(path, locales=LOCALES, color="#ff6a00", **options):
    p = Project(400, 300, "white")
    p.apply([
        {"type": "variable", "name": "headline", "value": "Summer sale"},
        {"type": "variable", "name": "cta", "value": "Shop now"},
        {"type": "text", "name": "headline", "text": "${headline}", "size": 32, "x": 20, "y": 20},
        {"type": "text-layout", "target": "headline", "width": 300, "height": 50},
        {"type": "text", "name": "cta", "text": "${cta}", "size": 18, "x": 20, "y": 120},
        {"type": "shape", "shape": "rectangle", "name": "logo", "x": 20, "y": 220, "width": 60, "height": 40,
         "fill": color},
        {"type": "locales-set", "locales": locales, **options},
    ])
    p.save(path, overwrite=True)
    return path


@pytest.fixture
def workspace(tmp_path):
    return Session(None, workspace=tmp_path)


def localize(workspace, **request):
    return dispatch(workspace, "localize", request, "master.vixl")


def test_four_languages_with_one_rtl_give_four_variants_and_an_overflow_report(workspace, tmp_path):
    master(tmp_path / "master.vixl", fit="shrink")
    report = localize(workspace, formats=["png"])
    assert report["counts"] == {"completed": 4, "reused": 0, "held": 0} and report["passed"]
    names = sorted(p.name for p in (tmp_path / "localized").iterdir())
    assert names == sorted(["localize.json", *(f"master.{c}.{ext}" for c in LOCALES for ext in ("vixl", "png"))])
    de = report["results"]["de"]
    assert de["repairs"][0]["layer"] == "headline" and de["repairs"][0]["to"] < 32  # the overflow, shrunk
    ar = report["results"]["ar"]
    assert ar["rtl"] and any(m["layer"] == "logo" for m in ar["mirrored"])
    derived = Project.load(tmp_path / "localized/master.ar.vixl")
    assert derived.layer("logo")["x"] == 320 and derived.state["variables"]["cta"] == "تسوق الآن"
    assert "locales" not in derived.state  # the derived document is the localized copy, not a master


def test_five_locales_with_one_overflowing_hold_it_and_name_it(workspace, tmp_path):
    master(tmp_path / "master.vixl", {**LOCALES, "it": {"headline": "Saldi", "cta": "Compra"}})
    report = localize(workspace)
    assert report["counts"]["held"] == 1 and report["counts"]["completed"] == 4
    assert report["held"][0]["locale"] == "de" and "headline" in report["held"][0]["findings"][0]
    assert "de" in report["message"] and report["status"] == "needs_review"
    assert not (tmp_path / "localized/master.de.vixl").exists()
    assert (tmp_path / "localized/master.it.vixl").exists()


def test_missing_keys_are_reported_and_held(workspace, tmp_path):
    master(tmp_path / "master.vixl", {"de": {"headline": "Sommer", "cta": "Kaufen"}})
    (tmp_path / "strings.csv").write_text("key,de,fr\nheadline,Sommer,Été\ncta,Kaufen,\n", encoding="utf-8")
    report = localize(workspace, strings="strings.csv", output_dir="out")
    fr = report["results"]["fr"]
    assert fr["status"] == "held" and fr["missing"] == ["cta"] and "missing key" in fr["reason"]
    assert report["strings"]["missing"] == [{"key": "cta", "locale": "fr", "row": 3}]
    assert report["results"]["de"]["status"] == "completed"


def test_fit_policy_shrink_versus_flag(workspace, tmp_path):
    master(tmp_path / "master.vixl", {"de": LOCALES["de"]})
    flagged = localize(workspace, fit="flag", output_dir="flag")
    assert flagged["results"]["de"]["status"] == "held" and "repairs" not in flagged["results"]["de"]
    shrunk = localize(workspace, fit="shrink", min_size=14, output_dir="shrink")
    assert shrunk["results"]["de"]["status"] == "completed"
    size = Project.load(tmp_path / "shrink/master.de.vixl").layer("headline")["size"]
    assert 14 <= size < 32
    # Per layer: only the named layer shrinks; a minimum it cannot reach still holds the locale.
    held = localize(workspace, fit={"headline": "shrink"}, min_size=30, output_dir="floor")
    assert held["results"]["de"]["status"] == "held"
    assert "cannot fit" in held["results"]["de"]["repairs"][0]["failed"]


def test_rerun_after_a_master_change_touches_only_affected_locales(workspace, tmp_path):
    master(tmp_path / "master.vixl", {k: LOCALES[k] for k in ("fr", "es", "ar")})
    first = localize(workspace, formats=["png"])
    assert first["counts"]["completed"] == 3
    stamp = (tmp_path / "localized/master.es.png").stat().st_mtime_ns
    again = localize(workspace, formats=["png"])
    assert again["counts"] == {"completed": 0, "reused": 3, "held": 0}
    # A new French translation rebuilds French only.
    changed = {k: LOCALES[k] for k in ("fr", "es", "ar")}
    changed["fr"] = {"headline": "Grandes soldes", "cta": "Acheter"}
    master(tmp_path / "master.vixl", changed)
    third = localize(workspace, formats=["png"])
    assert third["counts"] == {"completed": 1, "reused": 2, "held": 0}
    assert third["results"]["fr"]["status"] == "completed"
    assert (tmp_path / "localized/master.es.png").stat().st_mtime_ns == stamp
    # A change to the shared artwork rebuilds every locale.
    master(tmp_path / "master.vixl", changed, color="#0066cc")
    assert localize(workspace, formats=["png"])["counts"]["completed"] == 3
    record = json.loads((tmp_path / "localized/localize.json").read_text())
    assert set(record["locales"]) == {"fr", "es", "ar"}


def test_files_it_did_not_write_are_refused_unless_overwrite(workspace, tmp_path):
    master(tmp_path / "master.vixl", {"fr": LOCALES["fr"]})
    (tmp_path / "localized").mkdir()
    (tmp_path / "localized/master.fr.vixl").write_text("mine")
    with pytest.raises(VixlError, match="did not write"):
        localize(workspace)
    assert localize(workspace, overwrite=True)["results"]["fr"]["status"] == "completed"


def test_locale_axis_on_a_campaign_spec(workspace, tmp_path):
    master(tmp_path / "master.vixl", {k: LOCALES[k] for k in ("fr", "es")})
    report = localize(workspace, documents=False, spec={"rows": [{"cta": "A"}, {"cta": "B"}], "format": "png"})
    for code in ("fr", "es"):
        campaign = report["results"][code]["campaign"]
        assert campaign["count"] == 2 and campaign["directory"] == code
        assert len(list((tmp_path / "localized" / code).glob("*.png"))) >= 2
    with pytest.raises(VixlError, match="Nothing to write"):
        localize(workspace, documents=False)
