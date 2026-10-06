"""Fill-in-the-blank layouts and templates, the typeface catalog and installs, and seeded rolls."""

import json

import httpx
import pytest

from vixl import Project, VixlError
from vixl.checks import check_design
from vixl.cli import main
from vixl.layouts import LAYOUTS, catalog, slot_spec
from vixl.resources import create_template
from vixl import typefaces


def blank_checks(project):
    return [issue for issue in check_design(project)["issues"] if issue["check"] == "blanks"]


def test_unused_layout_slot_is_rejected_with_the_slots_it_does_use():
    p = Project(1080, 1080)
    with pytest.raises(VixlError) as caught:
        p.apply({"type": "layout-apply", "name": "event-poster", "title": "Night Market", "subtitle": "Fridays"})
    error = caught.value.as_dict()
    assert error["error"] == "unused_slot" and error["field"] == "subtitle"
    assert "label" in error["suggestions"] and "subtitle" not in error["suggestions"]
    assert p.state["layers"] == []


def test_unfilled_slots_render_as_blanks_never_as_invented_sample_copy():
    p = Project(1080, 1080)
    p.apply({"type": "layout-apply", "name": "event-poster", "title": "Night Market", "seed": 4})
    texts = " ".join(layer["text"] for layer in p.state["layers"] if layer["type"] == "text")
    for invented in ("June 21", "Riverside", "example.com", "RSVP"):
        assert invented not in texts
    assert "[Date]" in texts and "Night Market" in texts
    record = p.state["layout"]
    assert {b["slot"] for b in record["blanks"]} == {"label", "body", "cta", "caption"}
    assert any("Fill the blank slots" in note for note in record["notes"])
    issues = blank_checks(p)
    assert issues and all(issue["severity"] == "error" for issue in issues)
    assert not check_design(p)["passed"]


def test_filling_blanks_by_reapplying_with_the_same_seed_clears_them():
    p = Project(1080, 1080)
    p.apply({"type": "layout-apply", "name": "event-poster", "title": "Night Market", "seed": 4})
    first = {k: v for k, v in p.state["layout"].items() if k in ("palette", "mode", "density", "type_scale")}
    p.apply(
        {
            "type": "layout-apply",
            "name": "event-poster",
            "seed": 4,
            "replace": True,
            "title": "Night Market",
            "label": "Fri · Oct 9",
            "body": "6–11 pm\nPier 4",
            "cta": "Join us",
            "caption": "market.example",
        }
    )
    assert {k: p.state["layout"][k] for k in first} == first
    assert "blanks" not in p.state["layout"]
    assert blank_checks(p) == []


def test_editing_a_blank_layer_directly_fills_it():
    p = Project(1080, 1080)
    p.apply({"type": "layout-apply", "name": "quote-card", "seed": 2})
    names = [b["layer"] for b in p.state["layout"]["blanks"]]
    for name in names:
        p.apply({"type": "text-set", "target": name, "text": "Real copy"})
    assert blank_checks(p) == []


def test_unfilled_omit_leaves_optional_copy_out():
    p = Project(1080, 1080)
    p.apply({"type": "layout-apply", "name": "event-poster", "title": "Night Market", "seed": 4, "unfilled": "omit"})
    assert "blanks" not in p.state["layout"]
    assert all("[" not in layer.get("text", "") for layer in p.state["layers"])


def test_image_placeholder_is_a_blank_until_an_asset_is_supplied():
    p = Project(1200, 800)
    p.apply({"type": "layout-apply", "name": "split-screen", "title": "Hello", "subtitle": "There", "cta": "Go", "label": "Kick", "seed": 2})
    assert [b["slot"] for b in p.state["layout"]["blanks"]] == ["image"]
    assert [i["slot"] for i in blank_checks(p)] == ["image"]


@pytest.mark.parametrize("name", sorted(LAYOUTS))
def test_every_layout_documents_its_slots_and_builds_blank(name):
    spec = slot_spec(LAYOUTS[name])
    assert spec and all(item["label"] and item["hint"] for item in spec.values())
    p = Project(1080, 1080)
    p.apply({"type": "layout-apply", "name": name, "seed": 1})
    for layer in p.state["layers"]:
        if layer["type"] == "text":
            assert not layer["text"].startswith("[") or layer["id"] in p.state["blanks"]
    assert catalog()["layouts"][name]["slots"].keys() == spec.keys()


def test_seed_random_is_recorded_and_thin_parameters_encourage_rolling():
    p = Project(1080, 1080)
    p.apply({"type": "layout-apply", "name": "hero-statement", "title": "Hi", "seed": "random"})
    record = p.state["layout"]
    assert isinstance(record["seed"], int)
    assert set(record["rolled"]) >= {"palette", "mode", "density"}
    assert any("roll of the dice" in note for note in record["notes"])
    p2 = Project(1080, 1080)
    p2.apply({"type": "layout-apply", "name": "hero-statement", "title": "Hi", "subtitle": "x", "label": "y", "cta": "z",
              "palette": "sage", "mode": "dark", "type_scale": "golden", "density": "airy", "align": "left", "accent": "rule"})
    assert p2.state["layout"]["rolled"] == []
    assert not any("roll of the dice" in note for note in p2.state["layout"].get("notes", []))


def test_layouts_use_document_typography_and_flag_the_fallback_font():
    p = Project(1080, 1080)
    p.apply({"type": "layout-apply", "name": "hero-statement", "title": "Hi", "unfilled": "omit", "seed": 3})
    assert p.state["layout"]["fonts"] == "fallback"
    assert any(issue["check"] == "fonts" for issue in check_design(p)["issues"])


def test_builtin_templates_use_blanks_and_seeded_colors():
    a = create_template("social-square", {"title": "Launch"}, seed=7)
    b = create_template("social-square", {"title": "Launch"}, seed=7)
    assert a.state["template"]["rolled"] == b.state["template"]["rolled"]
    assert [x["slot"] for x in a.state["template"]["blanks"]] == ["subtitle"]
    assert "Your subtitle" not in json.dumps(a.state["layers"])
    assert [i["slot"] for i in blank_checks(a)] == ["subtitle"]
    fixed = create_template("social-square", {"title": "A", "subtitle": "B", "background": "#000000", "foreground": "#ffffff"})
    assert isinstance(fixed.state["template"]["seed"], int) and blank_checks(fixed) == []
    rolled = create_template("logo")
    assert rolled.state["template"]["rolled"]["accent"].startswith("#")


def test_cli_layout_show_lists_slots_and_unused_slot_errors(tmp_path, capsys, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert main(["layout", "show", "event-poster"]) == 0
    shown = json.loads(capsys.readouterr().out)
    assert shown["slots"]["label"]["label"] == "Date"
    assert main(["new", "400x400", "-o", "a.vixl"]) == 0
    capsys.readouterr()
    assert main(["--project", "a.vixl", "layout", "apply", "event-poster", "--set", "subtitle=x"]) != 0
    assert main(["--project", "a.vixl", "layout", "apply", "event-poster", "--set", "title=x", "--seed", "random"]) == 0


# -- Typefaces ------------------------------------------------------------------------------


def test_catalog_and_pairings_are_consistent():
    families = {f["family"]: f for f in typefaces.fonts()}
    assert len(families) >= 60
    for entry in families.values():
        assert entry["weights"] and all(100 <= w <= 900 and w % 100 == 0 for w in entry["weights"])
        assert entry["category"] in ("sans-serif", "serif", "monospace", "display", "handwriting")
    names = [p["name"] for p in typefaces.pairings()]
    assert len(names) == len(set(names)) >= 30
    for pairing in typefaces.pairings():
        for part in ("heading", "body"):
            family = families[pairing[part]["family"]]
            assert pairing[part]["weight"] in family["weights"], (pairing["name"], part)
        assert pairing["why"] and pairing["relationship"] in ("contrast", "superfamily", "concord")
    assert "x-height" in typefaces.principles().lower()


def test_font_filters_and_show():
    serif = typefaces.list_fonts(category="serif")["fonts"]
    assert serif and all(typefaces.find_font(f["family"])["category"] == "serif" for f in serif)
    first = typefaces.pairings()[0]
    shown = typefaces.show_font(first["heading"]["family"])
    assert first["name"] in shown["pairings"]
    with pytest.raises(VixlError) as caught:
        typefaces.show_font("Definitely Not A Font")
    assert caught.value.code == "unknown_font"


def fake_google(requests):
    from pathlib import Path

    font = (Path(typefaces.__file__).parent / "data" / "DejaVuSans.ttf").read_bytes()

    def handler(request):
        requests.append(str(request.url))
        if request.url.host == "fonts.googleapis.com":
            return httpx.Response(200, text="@font-face { src: url(https://fonts.gstatic.com/s/x/v1/abc.ttf) format('truetype'); }")
        assert request.url.host == "fonts.gstatic.com"
        return httpx.Response(200, content=font)

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_pair_installs_embeds_and_sets_typography_with_cache(tmp_path, monkeypatch):
    monkeypatch.setenv("VIXL_FONT_CACHE", str(tmp_path / "cache"))
    requests = []
    p = Project(1080, 1080)
    pairing = typefaces.pairings()[0]
    result = typefaces.pair_fonts(p, pairing["name"], client=fake_google(requests))
    assert result["pairing"] == pairing["name"]
    typography = p.state["typography"]
    assert set(typography) == {"heading", "body"}
    assert all(name in p.state["fonts"] for name in typography.values())
    assert len(requests) == 4 or pairing["heading"] == pairing["body"]
    p.apply({"type": "layout-apply", "name": "hero-statement", "title": "Hi", "unfilled": "omit", "seed": 3})
    assert p.state["layout"]["fonts"] == {"heading": typography["heading"], "body": typography["body"]}
    assert not any(issue["check"] == "fonts" for issue in check_design(p)["issues"])
    # A second document reuses the cache without network access.
    again = []
    q = Project(100, 100)
    typefaces.pair_fonts(q, pairing["name"], client=fake_google(again))
    assert again == []
    # The fonts are embedded: the saved document renders without the cache.
    p.save(tmp_path / "doc.vixl")
    loaded = Project.load(tmp_path / "doc.vixl")
    assert loaded.state["typography"] == typography and loaded.render().size == (1080, 1080)


def test_install_rejects_unknown_weights_and_bad_names(tmp_path, monkeypatch):
    monkeypatch.setenv("VIXL_FONT_CACHE", str(tmp_path))
    entry = next(f for f in typefaces.fonts() if len(f["weights"]) < 9)
    missing = next(w for w in range(100, 1000, 100) if w not in entry["weights"])
    with pytest.raises(VixlError) as caught:
        typefaces.install_font(Project(10, 10), entry["family"], missing, client=fake_google([]))
    assert caught.value.code == "unavailable_weight"
    with pytest.raises(VixlError):
        typefaces.install_font(Project(10, 10), "../etc/passwd", 400, client=fake_google([]))
    with pytest.raises(VixlError):
        Project(10, 10).apply({"type": "font-register", "name": "nope", "role": "heading"})


def test_roll_is_reproducible_lockable_and_applicable():
    a, b = typefaces.roll(42), typefaces.roll(42)
    assert a == b and a["seed"] == 42
    assert typefaces.roll(43)["direction"] != a["direction"]
    locked = typefaces.roll(7, locks={"palette": "sage", "layout": "quote-card"})
    assert locked["direction"]["palette"] == "sage" and locked["operation"]["name"] == "quote-card"
    with pytest.raises(VixlError):
        typefaces.roll(1, locks={"colour": "red"})
    posters = {typefaces.roll(seed, purpose="poster")["direction"]["layout"] for seed in range(30)}
    assert all("poster" in " ".join(LAYOUTS[name]["best_for"]) for name in posters)
    tall = {typefaces.roll(seed, canvas=(1080, 1920))["direction"]["layout"] for seed in range(40)}
    assert "banner" not in tall
    p = Project(1080, 1080)
    op = {**a["operation"], "title": "Hello"}
    p.apply(op)
    assert p.state["layout"]["name"] == a["direction"]["layout"]
    random_roll = typefaces.roll("random")
    assert isinstance(random_roll["seed"], int)


def test_cli_fonts_pairings_and_roll(capsys):
    assert main(["fonts", "--category", "monospace"]) == 0
    assert json.loads(capsys.readouterr().out)["count"] >= 1
    assert main(["font", "pairings", "--mood", "editorial"]) == 0
    capsys.readouterr()
    assert main(["roll", "--seed", "5", "--for", "poster", "--size", "instagram-post"]) == 0
    rolled = json.loads(capsys.readouterr().out)
    assert rolled["seed"] == 5 and rolled["operation"]["type"] == "layout-apply"
