"""The localization plugin's locale check (#565): locale tables, strings CSVs, group locales and the matrix."""

import json

import pytest

from vixl import Project
from vixl.errors import VixlError
from vixl.interfaces import Session
from vixl.plugins.localization.locales import load_strings
from vixl.plugins.localization.mirror import flip_constraints, mirror
from vixl.workflows import dispatch



@pytest.fixture(autouse=True)
def no_local_faces(monkeypatch):
    """Japanese must not find a CJK face installed on the test machine."""
    monkeypatch.setattr("vixl.typefaces.local_script_faces", lambda families: [])


def master(path, locales=None, **options):
    p = Project(400, 300, "white")
    p.apply([
        {"type": "variable", "name": "headline", "value": "Summer sale"},
        {"type": "variable", "name": "cta", "value": "Shop now"},
        {"type": "text", "name": "headline", "text": "${headline}", "size": 32, "x": 20, "y": 20},
        {"type": "text-layout", "target": "headline", "width": 300, "height": 50},
        {"type": "text", "name": "cta", "text": "${cta}", "size": 18, "x": 20, "y": 120},
        {"type": "locales-set", "locales": locales or {
            "de": {"headline": "Sommerschlussverkauf mit riesigen Rabatten", "cta": "Jetzt kaufen"},
            "fr": {"headline": "Soldes d'été", "cta": "Acheter"},
        }, **options},
    ])
    path.parent.mkdir(parents=True, exist_ok=True)
    p.save(path, overwrite=True)
    return path


@pytest.fixture
def workspace(tmp_path):
    return Session(None, workspace=tmp_path)


def check(workspace, **request):
    return dispatch(workspace, "locale-check", request, "master.vixl")


def test_german_overflow_is_named_with_the_locale_and_the_layer(workspace, tmp_path):
    master(tmp_path / "master.vixl")
    report = check(workspace)
    assert report["locales"] == ["de", "fr"]
    de = report["results"]["de"]
    assert de["status"] == "failed" and report["passed"] is False
    overflow = [f for f in de["findings"] if f["kind"] == "overflow"]
    assert overflow and overflow[0]["layers"] == ["headline"] and overflow[0]["message"].startswith("de: ")
    assert report["matrix"]["de"]["overflow"] == 1 and report["matrix"]["fr"]["overflow"] == 0
    assert report["results"]["fr"]["status"] == "passed"
    # The master itself is checked as the source row, and nothing was saved.
    assert report["results"]["en"]["source"] is True
    assert Project.load(tmp_path / "master.vixl").state["variables"]["headline"] == "Summer sale"


def test_japanese_text_in_a_latin_font_is_a_fonts_error_for_ja(workspace, tmp_path):
    master(tmp_path / "master.vixl", {"ja": {"headline": "夏のセール", "cta": "今すぐ購入"}})
    report = check(workspace, locales="ja")
    fonts = [f for f in report["results"]["ja"]["findings"] if f["kind"] == "fonts"]
    assert fonts and fonts[0]["severity"] == "error" and fonts[0]["locale"] == "ja"
    assert report["matrix"]["ja"]["fonts"] >= 1


def test_untranslated_values_are_flagged_unless_same_ok(workspace, tmp_path):
    master(tmp_path / "master.vixl", {"fr": {"headline": "Summer sale", "cta": "Acheter"}})
    found = check(workspace)["results"]["fr"]["findings"]
    assert [(f["kind"], f["key"]) for f in found] == [("untranslated", "headline")]
    assert found[0]["severity"] == "warning"
    assert check(workspace, same_ok=["headline"])["results"]["fr"]["findings"] == []


def test_missing_keys_are_errors(workspace, tmp_path):
    master(tmp_path / "master.vixl", {"de": {"headline": "Sommer", "cta": "Kaufen"}, "fr": {"headline": "Été"}})
    fr = check(workspace)["results"]["fr"]
    assert fr["missing"] == ["cta"] and fr["status"] == "failed"
    assert any(f["kind"] == "missing-key" and f["severity"] == "error" for f in fr["findings"])


def test_strings_csv_loader(tmp_path):
    path = tmp_path / "strings.csv"
    path.write_text("key,notes,en,de,pt_BR\nheadline,hero,Sale,Angebot,Promoção\ncta,,Buy,,Comprar\n",
                    encoding="utf-8")
    loaded = load_strings(path)
    assert loaded["languages"] == ["en", "de", "pt-BR"]  # notes is not a locale; pt_BR is canonical pt-BR
    assert loaded["locales"]["de"] == {"headline": "Angebot"}
    assert loaded["missing"] == [{"key": "cta", "locale": "de", "row": 3}]
    assert load_strings(path, languages=["de"])["languages"] == ["de"]
    path.write_text("key,de\nheadline,A\nheadline,B\n", encoding="utf-8")
    with pytest.raises(VixlError, match="listed twice"):
        load_strings(path)
    with pytest.raises(VixlError, match="no 'id' column"):
        load_strings(path, key_column="id")


def test_strings_csv_values_win_and_empty_cells_are_missing_keys(workspace, tmp_path):
    master(tmp_path / "master.vixl", {"de": {"headline": "Sommer", "cta": "Kaufen"}})
    (tmp_path / "strings.csv").write_text("key,de,ja\nheadline,Sale DE,夏\ncta,Kauf,\n", encoding="utf-8")
    report = check(workspace, strings="strings.csv", locales="de,ja")
    assert report["strings"]["languages"] == ["de", "ja"]
    assert report["results"]["de"]["missing"] == []
    assert "cta" in report["results"]["ja"]["missing"]
    with pytest.raises(VixlError, match="inside the workspace"):
        check(workspace, strings="../strings.csv")


def test_line_count_change_that_breaks_a_hierarchy_rule(workspace, tmp_path):
    p = Project(400, 300, "white")
    p.apply([
        {"type": "variable", "name": "title", "value": "Sale"},
        {"type": "text", "name": "title", "text": "${title}", "size": 40, "x": 20, "y": 20},
        {"type": "text-layout", "target": "title", "width": 360, "height": 100, "fit": True},
        {"type": "text", "name": "body", "text": "Every item reduced", "size": 20, "x": 20, "y": 200},
        {"type": "suite-set", "name": "type", "suite": {"version": 1, "rules": [
            {"id": "scale", "kind": "hierarchy", "targets": ["title", "body"], "ratio": 1.8}]}},
        {"type": "locales-set", "locales": {"de": {"title": "Ausverkauf aller Sommerartikel im ganzen Laden jetzt"},
                                            "fr": {"title": "Soldes"}}},
    ])
    p.save(tmp_path / "master.vixl")
    report = check(workspace)
    de = report["results"]["de"]
    line = [f for f in de["findings"] if f["kind"] == "line-count"]
    assert line and line[0]["layers"] == ["title", "body"] and line[0]["rule"] == "scale"
    assert de["lines"]["title"][0] == 1 and de["lines"]["title"][1] > 1
    assert report["matrix"]["fr"]["line-count"] == 0


def test_group_locales_fill_in_and_document_values_win(workspace, tmp_path):
    master(tmp_path / "master.vixl", {"de": {"headline": "Sommer", "cta": "Kaufen"}})
    dispatch(workspace, "group-define", {"name": "launch", "documents": ["master.vixl"]})
    result = dispatch(workspace, "group-locales", {"name": "launch", "locales": {
        "de": {"headline": "Gruppe"}, "it": {"headline": "Saldi", "cta": "Compra"}}})
    assert result["locales"] == ["de", "it"]
    report = check(workspace)
    assert set(report["locales"]) == {"de", "it"} and report["sources"]["groups"] == ["launch"]
    # Redefining the group keeps its locale table.
    dispatch(workspace, "group-define", {"name": "launch", "documents": ["master.vixl"]})
    assert "it" in json.loads((tmp_path / ".vixl-groups/launch.json").read_text())["locales"]
    with pytest.raises(VixlError, match="Unknown project group"):
        dispatch(workspace, "group-locales", {"name": "missing", "locales": {}})


def test_locale_records_are_validated():
    p = Project(100, 100, "white")
    with pytest.raises(VixlError, match="not a locale code"):
        p.apply({"type": "locales-set", "locales": {"German": {"a": "b"}}})
    with pytest.raises(VixlError, match="fit is shrink or flag"):
        p.apply({"type": "locales-set", "fit": "squash"})
    p.apply({"type": "locales-set", "locales": {"de_DE": {"a": "b"}}, "source": "en"})
    assert p.state["locales"] == {"de-DE": {"a": "b"}} and p.state["locale_options"] == {"source": "en"}
    p.apply({"type": "locales-set", "locales": {"de-DE": None}, "source": None})
    assert "locales" not in p.state and "locale_options" not in p.state
    from vixl.validation import check_state

    p.state["locales"] = {"de": {"bad key!": "x"}}
    with pytest.raises(VixlError, match="not a variable name"):  # the validate-state hook
        check_state(p, p.state)


def test_workflow_check_field_locales_routes_to_the_plugin(workspace, tmp_path):
    master(tmp_path / "master.vixl")
    report = dispatch(workspace, "check", {"locales": ["de"]}, "master.vixl")
    assert report["check"] == "locales" and report["locales"] == ["de"]
    with pytest.raises(VixlError, match="With locales"):
        dispatch(workspace, "check", {"locales": "all", "mode": "still"}, "master.vixl")
    with pytest.raises(VixlError, match="Unknown locale"):
        dispatch(workspace, "check", {"locales": "es"}, "master.vixl")


def test_markdown_matrix_goes_through_the_workspace_report(workspace, tmp_path):
    master(tmp_path / "master.vixl")
    report = check(workspace, format="markdown", output="locales.md")
    text = (tmp_path / "locales.md").read_text(encoding="utf-8")
    assert text == report["markdown"]
    assert "| Locale | overflow |" in text and "| `de` | 1 |" in text
    assert "### Per locale" in text and "`master.vixl#de`" in text  # the workspace_checks renderer
    with pytest.raises(VixlError, match="exists"):
        check(workspace, output="locales.md")


def test_cli_check_locales(tmp_path, capsys):
    from vixl.cli import main

    path = master(tmp_path / "master.vixl")
    assert main(["--project", str(path), "check", "--locales", "de,fr", "--format", "markdown"]) == 1
    assert "| `de` | 1 |" in capsys.readouterr().out
    assert main(["--json", "--project", str(path), "check", "--locales", "fr"]) == 0
    assert json.loads(capsys.readouterr().out)["results"]["fr"]["status"] == "passed"
    assert main(["--project", str(path), "check", "--strings", "x.csv"]) == 1
    assert "go with --locales" in capsys.readouterr().err


def test_rtl_mirroring_flips_positions_constraints_and_alignment():
    p = Project(400, 200, "white")
    p.apply([
        {"type": "shape", "shape": "rectangle", "name": "logo", "x": 20, "y": 20, "width": 60, "height": 40},
        {"type": "shape", "shape": "rectangle", "name": "band", "x": 0, "y": 150, "width": 400, "height": 50},
        {"type": "text", "name": "title", "text": "مرحبا", "size": 20, "x": 20, "y": 100, "align": "left"},
    ])
    changes = {entry["layer"]: entry for entry in mirror(p)}
    assert p.layer("logo")["x"] == 320 and changes["logo"]["anchor"] == "top-left -> top-right"
    assert p.layer("band")["x"] == 0 and "band" not in changes  # a layer spanning the canvas stays
    assert p.layer("title")["align"] == "right"
    assert flip_constraints({"left": "canvas.left+40", "top": 10, "center-x": "logo.center-x-5", "right": 380},
                            400) == {"right": "canvas.right-40", "top": 10, "center-x": "logo.center-x+5", "left": 20}
