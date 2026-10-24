"""The hierarchy codes of the composition family (#649): flat_hierarchy, single_weight, no_focal and accent_unused.
Each has a positive and a negative case; they are review findings with suggestions and no automatic repair."""

from pathlib import Path

import vixl
from vixl import Project
from vixl.composition import CODES, THRESHOLDS
from vixl.fonts import import_font
from vixl.plugins.layout_repair.layout_repair import repair_layout

from test_composition import doc, found, panel, text

DATA = Path(vixl.__file__).parent / "data"
NEW = ("flat_hierarchy", "single_weight", "no_focal", "accent_unused")


def only(p, code):
    return [x for x in found(p, hierarchy=True) if x["code"] == code]


def faced(*ops, fonts=("noto",), **options):
    """A document with registered, non-fallback faces (the bundled Noto Sans and DejaVu Sans files)."""
    p = Project(1000, 1000, "white")
    p.apply({"type": "type-scale", "base": 20})
    files = {"noto": "NotoSans-Regular.ttf", "dejavu": "DejaVuSans.ttf"}
    for name in fonts:
        import_font(p, DATA / files[name], name)
    p.apply(list(ops))
    return p


def test_the_hierarchy_codes_extend_the_family():
    assert set(NEW) <= set(CODES)
    assert THRESHOLDS["hierarchy_ratio"] == 1.6 and THRESHOLDS["focal_margin"] == 0.15


# --- flat_hierarchy -----------------------------------------------------------------------------


def test_flat_hierarchy_when_the_largest_text_is_near_the_body_size():
    p = doc(text("title", 100, 100, 26), text("subtitle", 100, 180, 22), text("note", 100, 260, 20))
    (finding,) = only(p, "flat_hierarchy")
    assert finding["action"] == "review" and finding["rule"] == "composition.flat_hierarchy"
    assert finding["layers"][0] == "title"
    assert finding["measured"] == {"actual": 1.3, "expected": 1.6, "unit": "ratio"}
    assert finding["values"]["largest"] == 26 and finding["values"]["body"] == 20 and finding["values"]["raise_to"] == 40
    assert finding["threshold"] == {"min_ratio": 1.6, "min_blocks": 2}
    # Review findings never fail the plain check.
    assert p.check(checks=["composition"])["passed"]


def test_a_clear_step_a_lone_block_and_a_row_of_cards_are_not_flat():
    assert not only(doc(text("title", 100, 100, 48), text("subtitle", 100, 190, 22), text("note", 100, 260, 20)),
                    "flat_hierarchy")
    assert not only(doc(text("title", 100, 100, 26)), "flat_hierarchy")
    assert not only(doc(text("title", 100, 100, 32), text("note", 100, 180, 20)), "flat_hierarchy")  # exactly 1.6
    cards = [panel(f"card-{i}", 100, 150, x=60 + 300 * i, width=280) for i in range(3)]
    labels = [text(f"label-{i}", 80 + 300 * i, 140, 24) for i in range(3)]
    assert not only(doc(*cards, *labels), "flat_hierarchy")
    # The same three lines in no card at all are one flat page.
    assert only(doc(*[text(f"line-{i}", 80, 100 + 80 * i, 24) for i in range(3)]), "flat_hierarchy")


def test_a_larger_span_in_rich_text_counts_as_the_largest_size():
    p = doc({"type": "rich-text", "name": "title", "markdown": "Open [House]{size=64}", "x": 100, "y": 100, "size": 24,
             "color": "#111111"}, text("note", 100, 260, 20))
    assert not only(p, "flat_hierarchy")


# --- single_weight ------------------------------------------------------------------------------


def run(prefix, font, y0=100):
    return [text(f"{prefix}-{i}", 100, y0 + 120 * i, 48 if i == 0 else 24, font=font) for i in range(3)]


def test_single_weight_when_every_block_is_one_face_and_weight():
    p = faced(*run("line", "noto"))
    (finding,) = only(p, "single_weight")
    assert finding["action"] == "review" and finding["measured"] == {"actual": 1, "expected": 2, "unit": "count"}
    assert finding["values"]["family"] == "Noto Sans" and finding["values"]["weight"] == 400
    assert finding["values"]["blocks"] == 3 and finding["threshold"]["min_blocks"] == 3


def test_a_second_face_two_blocks_or_the_proofing_font_are_not_single_weight():
    mixed = [text("title", 100, 100, 48, font="dejavu"), *run("line", "noto", 200)[1:], text("more", 100, 400, 24, font="noto")]
    assert not only(faced(*mixed, fonts=("noto", "dejavu")), "single_weight")
    assert not only(faced(*run("line", "noto")[:2]), "single_weight")  # two blocks
    # The bundled proofing font is the fonts check's finding, not a typographic choice.
    assert not only(doc(*[text(f"line-{i}", 100, 100 + 120 * i, 48 if i == 0 else 24) for i in range(3)]),
                    "single_weight")


def test_bold_in_rich_text_is_a_second_weight():
    plain = run("line", "noto")
    rich = {"type": "rich-text", "name": "line-2", "markdown": "A **bold** word", "x": 100, "y": 340, "size": 24,
            "color": "#111111", "font": "noto"}
    assert only(faced(*plain), "single_weight")
    assert not only(faced(*plain[:2], rich), "single_weight")


def test_two_registered_names_for_one_font_file_cannot_be_told_apart():
    p = faced(*run("line", "noto"))
    asset = p.state["fonts"]["noto"]
    p.state["fonts"]["noto-bold"] = asset
    p.state["typography"] = {"heading": "noto-bold", "body": "noto"}
    assert not only(p, "single_weight")


# --- no_focal -----------------------------------------------------------------------------------


def test_no_focal_when_the_two_heaviest_blocks_weigh_the_same():
    p = doc(text("one", 100, 100, 72), text("two", 100, 300, 72), text("note", 100, 600, 20))
    (finding,) = only(p, "no_focal")
    assert finding["action"] == "review" and finding["layers"] == ["one", "two"]
    assert finding["measured"]["unit"] == "ratio" and finding["measured"]["actual"] >= 0.85
    assert finding["threshold"] == {"max_share": 0.85, "min_blocks": 3}


def test_one_block_that_leads_a_series_or_a_picture_is_not_a_rivalry():
    assert not only(doc(text("one", 100, 100, 72), text("two", 100, 300, 44), text("note", 100, 600, 20)), "no_focal")
    # Three equal blocks are a series (a list, a row of cards), not two rivals.
    assert not only(doc(text("one", 100, 100, 72), text("two", 100, 300, 72), text("three", 100, 500, 72)), "no_focal")
    # Two blocks alone are not judged.
    assert not only(doc(text("one", 100, 100, 72), text("two", 100, 300, 72)), "no_focal")
    # A page carried by art (a large shape) is judged by the art, not by its two lines of type.
    art = panel("art", 100, 380, x=100, width=800)
    assert not only(doc(text("one", 100, 40, 72), art, text("two", 100, 520, 72), text("note", 100, 900, 20)), "no_focal")


def test_a_big_number_over_a_longer_line_leads():
    p = doc({**text("number", 100, 100, 105), "text": "94%"},
            {**text("subtitle", 100, 300, 60), "text": "of readers finish the guide"},
            {**text("label", 100, 500, 24), "text": "COMPLETION"})
    assert not only(p, "no_focal")


def test_initials_set_in_a_mark_are_part_of_the_mark_not_a_line_of_type():
    disc = {"type": "shape", "name": "mark", "shape": "ellipse", "x": 100, "y": 100, "width": 260, "height": 260,
            "fill": "#335577"}
    initial = {**text("initial", 160, 140, 190, font="noto"), "text": "N", "color": "#ffffff"}
    word = {**text("wordmark", 100, 420, 126, font="noto"), "text": "Northwind"}
    tag = {**text("tagline", 100, 600, 48, font="noto"), "text": "Coffee roasters"}
    p = faced(disc, initial, word, tag)
    assert not only(p, "no_focal")
    # Counted as type it would make three blocks in one face; without it the lockup has two.
    assert not only(p, "single_weight")
    # The same letter outside any mark is a block like the rest.
    free = faced({**initial, "color": "#111111"}, word, tag)
    assert only(free, "single_weight")


# --- accent_unused ------------------------------------------------------------------------------


def accented(*ops, style="rule"):
    p = Project.new(width=1000, height=1000, purpose="poster", house_style="off")
    p.state["design_defaults"] = {"direction": {"accent": style}}
    p.apply([{"type": "swatch", "name": "accent", "color": "#e63946"}, {"type": "swatch", "name": "accent-text",
                                                                          "color": "#b0202e"}, *ops])
    return p


def three(**extra):
    return [text("title", 100, 100, 48, **extra), text("subtitle", 100, 200, 24), text("note", 100, 260, 24)]


def test_accent_unused_when_the_direction_has_an_accent_nothing_draws():
    p = accented(*three())
    (finding,) = only(p, "accent_unused")
    assert finding["action"] == "review" and finding["layers"] == []
    assert finding["values"] == {"accent": "#e63946", "style": "rule"}
    assert finding["measured"] == {"actual": 0, "expected": 1, "unit": "count"}


def test_any_visible_use_of_the_accent_satisfies_it():
    assert not only(accented(*three(color="@accent-text")), "accent_unused")
    bar = {"type": "shape", "name": "bar", "shape": "rectangle", "x": 100, "y": 60, "width": 120, "height": 8,
           "fill": "@accent"}
    assert not only(accented(*three(), bar), "accent_unused")
    # The colour itself counts as well as the reference to it.
    assert not only(accented(*three(color="#E63946")), "accent_unused")
    # A hidden layer does not.
    assert only(accented(*three(), bar, {"type": "hide", "target": "bar"}), "accent_unused")
    # A direction without an accent, a canvas painted with it, or a bare note ask nothing.
    assert not only(accented(*three(), style="none"), "accent_unused")
    assert not only(accented(*three()[:2]), "accent_unused")
    painted = accented(*three())
    painted.apply({"type": "canvas", "background": "@accent"})
    assert not only(painted, "accent_unused")
    assert not only(doc(*three()), "accent_unused")  # no direction at all


def test_a_waiver_turns_the_hierarchy_finding_informational():
    p = accented(*three())
    p.apply({"type": "waiver", "check": "composition", "reason": "a monochrome page on purpose"})
    assert all(x["action"] == "informational" for x in only(p, "accent_unused"))


# --- repair -------------------------------------------------------------------------------------


def test_repair_changes_nothing_for_a_hierarchy_finding_and_lists_suggestions():
    p = doc(text("title", 100, 100, 26), text("subtitle", 100, 180, 22), text("note", 100, 260, 20))
    assert only(p, "flat_hierarchy")
    before = p.state["layers"]
    result = repair_layout(p, checks=["composition"], dry_run=False)
    assert not result["selected"] and not result["operations"] and p.state["layers"] == before
    (left,) = [x for x in result["reviews_remaining"] if x["rule"] == "composition.flat_hierarchy"]
    assert left["reason"].startswith("not auto-repairable") and "judgement" in left["reason"]
    assert any("raise 'title'" in hint and '"size": 40' in hint for hint in left["suggestions"])
    skipped = [x for x in result["attempts"] if x["rule"] == "composition.flat_hierarchy"]
    assert skipped and skipped[0]["result"] == "skipped" and skipped[0]["suggestions"] == left["suggestions"]


def test_each_hierarchy_code_has_suggestions():
    from vixl.plugins.layout_repair.composition_repair import candidates, suggestions

    samples = {
        "flat_hierarchy": doc(text("title", 100, 100, 26), text("subtitle", 100, 180, 22), text("note", 100, 260, 20)),
        "single_weight": faced(*run("line", "noto")),
        "no_focal": doc(text("one", 100, 100, 72), text("two", 100, 300, 72), text("note", 100, 600, 20)),
        "accent_unused": accented(*three()),
    }
    for code, p in samples.items():
        (finding,) = only(p, code)
        assert candidates(p, finding)[0] == [] and suggestions(finding), code
    assert suggestions({"code": "dead_band"}) == []
