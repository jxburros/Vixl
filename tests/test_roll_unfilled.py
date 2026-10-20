"""A roll that applies its direction leaves unfilled slots out, so the applied direction passes check."""

import pytest

from vixl import Project, VixlError
from vixl.checks import check_design
from vixl.typefaces import roll_document

LOCKS = {"layout": "hero-statement", "palette": "ocean"}
SLOTS = {"title": "Launch", "subtitle": "A new beginning", "cta": "Learn more"}


def blank_issues(project):
    return [issue for issue in check_design(project)["issues"] if issue["check"] == "blanks"]


@pytest.fixture(autouse=True)
def offline_fonts(monkeypatch):
    # The pairing's fonts are not needed to lay the direction out; skip the download.
    monkeypatch.setattr(
        "vixl.typefaces.pair_fonts",
        lambda project, pairing=None, **kwargs: {
            "origin": "cache", "heading": {"name": "DejaVuSans.ttf"}, "body": {"name": "DejaVuSans.ttf"}},
    )


def apply_roll(**options):
    p = Project(800, 800)
    p.state["typography"] = {"body": "DejaVuSans.ttf", "heading": "DejaVuSans.ttf"}
    result = roll_document(p, seed=12, apply=True, locks=LOCKS, **options)
    return p, result


def test_applied_roll_with_slots_omits_the_rest_and_passes_check():
    p, result = apply_roll(slots=SLOTS)
    assert result["operation"]["unfilled"] == "omit"
    assert blank_issues(p) == [] and check_design(p)["errors"] == 0
    names = {layer["name"] for layer in p.state["layers"]}
    assert "label" not in names and {"headline", "subtitle", "cta"} <= names
    layout = result["applied"]["layout"]
    assert layout["omitted"] == ["label"] and result["applied"]["unfilled_slots"] == []
    assert any("Left out unfilled slots (label)" in note for note in layout["notes"])


def test_unfilled_blank_keeps_placeholders_that_check_rejects():
    p, result = apply_roll(slots=SLOTS, unfilled="blank")
    assert "unfilled" not in result["operation"]
    assert [issue["layers"] for issue in blank_issues(p)] == [["label"]]
    assert result["applied"]["unfilled_slots"] == ["label"]


def test_roll_without_slots_still_returns_the_missing_slots_as_blanks():
    p, result = apply_roll()
    assert "label" in result["applied"]["unfilled_slots"] and blank_issues(p)
    p2, result2 = apply_roll(unfilled="omit")
    assert result2["applied"]["unfilled_slots"] == [] and blank_issues(p2) == []


def test_omitted_composition_matches_a_plain_layout_apply_with_unfilled_omit():
    p, result = apply_roll(slots=SLOTS)
    q = Project(800, 800)
    q.state["typography"] = {"body": "DejaVuSans.ttf", "heading": "DejaVuSans.ttf"}
    q.apply({**result["operation"], **SLOTS})
    assert [(x["name"], x["x"], x["y"], x["width"], x["height"]) for x in p.state["layers"]] == [
        (x["name"], x["x"], x["y"], x["width"], x["height"]) for x in q.state["layers"]
    ]


def test_roll_apply_is_still_one_undo_step():
    p = Project(800, 800)
    p.state["typography"] = {"body": "DejaVuSans.ttf", "heading": "DejaVuSans.ttf"}
    before, head = p.state["layers"], p.head
    roll_document(p, seed=12, apply=True, locks=LOCKS, slots=SLOTS)
    assert p.state["layers"]
    p.undo()
    assert p.state["layers"] == before and p.head == head


def test_unknown_unfilled_value_is_rejected():
    with pytest.raises(VixlError, match="unfilled"):
        roll_document(Project(800, 800), seed=1, apply=True, slots=SLOTS, unfilled="hide")


def test_layout_apply_schema_lists_the_unfilled_choices():
    from vixl.schema import operation_schema

    variants = {
        v["properties"]["type"]["const"]: v for v in operation_schema()["properties"]["operations"]["items"]["oneOf"]
    }
    assert variants["layout-apply"]["properties"]["unfilled"]["enum"] == ["blank", "omit"]
    with pytest.raises(VixlError, match="unfilled"):
        Project(800, 800).apply({"type": "layout-apply", "name": "hero-statement", "title": "Hi", "unfilled": "hide"})


def test_cli_roll_unfilled_flag(tmp_path, monkeypatch):
    from vixl.cli import dispatch

    monkeypatch.chdir(tmp_path)
    Project(800, 800).save(tmp_path / "design.vixl")
    result, _ = dispatch(["-p", "design.vixl", "roll", "--seed", "3", "--lock", "layout=hero-statement",
                          "--set", "title=Hello", "--unfilled", "blank"])
    assert "unfilled" not in result["operation"]
    result, _ = dispatch(["-p", "design.vixl", "roll", "--seed", "3", "--lock", "layout=hero-statement",
                          "--set", "title=Hello"])
    assert result["operation"]["unfilled"] == "omit"


ALL_SLOTS = {"title": "Hi", "subtitle": "x", "label": "y", "cta": "Go", "body": "b", "caption": "c", "items": "a"}


def portrait():
    p = Project(1080, 1350)
    p.state["typography"] = {"body": "DejaVuSans.ttf", "heading": "DejaVuSans.ttf"}
    return p


def test_apply_with_slots_no_layout_places_keeps_the_previewed_layout():  # #700
    preview = roll_document(portrait(), seed=11, purpose="social", mood="friendly")
    chosen = preview["direction"]["layout"]
    p = portrait()
    with pytest.raises(VixlError) as raised:
        roll_document(p, seed=11, purpose="social", mood="friendly", apply=True, slots=ALL_SLOTS)
    assert raised.value.code == "unused_slot" and chosen in str(raised.value)
    assert raised.value.details["suggestions"] and set(raised.value.details["suggestions"]) <= set(ALL_SLOTS)
    assert p.state["layers"] == []  # nothing was applied
    # The roll itself names the pool it fell back to.
    direction = roll_document(portrait(), seed=11, purpose="social", mood="friendly", slots=ALL_SLOTS)["direction"]
    assert direction["layout"] == chosen and direction["pool"] == "preview"


def test_a_content_set_some_layout_places_still_picks_one_that_places_it():  # #700
    from vixl.layouts import places

    p = portrait()
    result = roll_document(p, seed=11, purpose="social", mood="friendly", apply=True, slots={"title": "Hi", "cta": "Go"})
    assert result["direction"]["pool"] == "content" and "pool" not in result["operation"]["direction"]
    assert places(result["direction"]["layout"], "portrait", ("cta", "title"))
    assert {"headline", "cta"} <= {layer["name"] for layer in p.state["layers"]}


def test_a_roll_no_layout_fits_names_the_nearest_layouts(monkeypatch):  # #700
    from vixl import variety
    from vixl.typefaces import roll

    pool = variety.tier_pool
    # No rollable layout in any pool (as when locks rule every one out).
    monkeypatch.setattr(variety, "tier_pool", lambda kind, *rest: [] if kind == "layouts" else pool(kind, *rest))
    with pytest.raises(VixlError) as raised:
        roll(11, purpose="social", canvas=(1080, 1350), content=("title", "items"))
    assert raised.value.details["field"] == "slots"
    suggestions = raised.value.details["suggestions"]
    assert 0 < len(suggestions) <= 3 and all({"layout", "places"} <= set(entry) for entry in suggestions)
    assert all("title" in entry["places"] for entry in suggestions)
