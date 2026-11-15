"""Guide roles from a printer's template and the safe_area check that reads them (#727)."""

import pytest

from vixl import Project, VixlError
from vixl.checks import check_design

# A 1000 x 400 wrap: back panel (with a barcode notch cut out of its safe area), a spine between two folds, front.
BACK = "M 40 40 L 440 40 L 440 360 L 300 360 L 300 280 L 180 280 L 180 360 L 40 360 Z"


def wrap():
    p = Project(1000, 400, "white")
    p.apply([
        {"type": "guide", "name": "safe-back", "kind": "path", "d": BACK, "role": "safe"},
        {"type": "guide", "name": "safe-front", "rect": [560, 40, 400, 320], "role": "safe"},
        {"type": "guide", "name": "barcode", "rect": [180, 280, 120, 80], "role": "keep-out"},
        {"type": "guide", "name": "fold-left", "axis": "x", "position": 480, "role": "fold"},
        {"type": "guide", "name": "fold-right", "axis": "x", "position": 520, "role": "fold"},
        {"type": "guide", "name": "board", "rect": [10, 10, 980, 380], "role": "trim"},
    ])
    return p


def text(p, name, x, y, words="Title", size=24, **extra):
    p.apply({"type": "text", "name": name, "text": words, "x": x, "y": y, "size": size, "color": "#111111", **extra})


def findings(p, code=None):
    issues = check_design(p, checks=["safe_area"])["issues"]
    return [i for i in issues if i["check"] == "safe_area" and (code is None or i.get("code") == code)]


def test_guides_carry_roles_and_rect_writes_a_closed_path(tmp_path):
    p = wrap()
    guides = p.state["guides"]
    assert guides["safe-front"] == {"kind": "path", "d": "M 560 40 L 960 40 L 960 360 L 560 360 Z", "role": "safe"}
    assert guides["fold-left"] == {"axis": "x", "position": 480, "role": "fold"}
    p.save(tmp_path / "wrap.vixl")
    assert Project.load(tmp_path / "wrap.vixl").state["guides"] == guides
    from vixl.guides import describe

    assert describe(p)["guides"]["barcode"]["role"] == "keep-out"


def test_role_spellings_are_normalized_and_bad_roles_refused():
    p = Project(400, 300, "white")
    result = p.apply({"type": "guide", "name": "code", "rect": [10, 10, 50, 30], "role": "Keep_Out"})
    assert p.state["guides"]["code"]["role"] == "keep-out"
    assert any("keep-out" in note for note in result.get("normalized", []))
    with pytest.raises(VixlError, match="closed path"):
        p.apply({"type": "guide", "name": "edge", "axis": "x", "position": 20, "role": "safe"})
    with pytest.raises(VixlError):
        p.apply({"type": "guide", "name": "edge", "axis": "x", "position": 20, "role": "gutter"})
    with pytest.raises(VixlError, match="positive size"):
        p.apply({"type": "guide", "name": "box", "rect": [10, 10, 0, 30]})


def test_content_inside_its_panel_passes_and_role_free_guides_change_nothing():
    p = wrap()
    text(p, "front-title", 600, 80)
    text(p, "back-blurb", 60, 80)
    text(p, "spine", 487, 100, words="S", size=20)
    # The spine has no safe outline of its own, so only that layer is reported.
    assert [(i["code"], i["layers"]) for i in findings(p)] == [("outside-safe-guides", ["spine"])]
    plain = Project(1000, 400, "white")
    plain.apply({"type": "guide", "name": "g", "rect": [560, 40, 400, 320]})
    text(plain, "anywhere", 100, 100)
    assert findings(plain) == []


def test_safe_guides_replace_the_size_presets_safe_area_unless_one_is_passed():
    p = Project(1000, 400, "white")
    text(p, "corner", 4, 4)
    assert [i["code"] for i in findings(p)] == ["outside"]  # the canvas's own safe area
    p.apply({"type": "guide", "name": "panel", "rect": [0, 0, 500, 400], "role": "safe"})
    assert findings(p) == []
    explicit = check_design(p, checks=["safe_area"], safe_area=40)["issues"]
    assert [i["code"] for i in explicit if i["check"] == "safe_area"] == ["outside"]


def test_text_outside_the_front_safe_area_and_in_the_keep_out_notch_is_flagged():
    p = wrap()
    text(p, "front-title", 880, 80, words="Overhanging")
    text(p, "price", 200, 300, words="9.99", size=20)
    by_layer = {i["layers"][0]: i for i in findings(p)}
    outside = by_layer["front-title"]
    assert outside["code"] == "outside-safe-guide" and outside["guide"] == "safe-front"
    assert outside["severity"] == "error" and "safe guide 'safe-front'" in outside["message"]
    # The notch is cut out of the back panel's safe outline and is a keep-out of its own: both name the layer.
    codes = {(i["code"], i["guide"]) for i in findings(p) if i["layers"] == ["price"]}
    assert codes == {("outside-safe-guide", "safe-back"), ("keep-out", "barcode")}
    assert all(i["severity"] == "error" for i in findings(p) if i["layers"] == ["price"])


def test_non_rectangular_safe_outline_is_judged_by_its_shape_not_its_box():
    p = wrap()
    text(p, "beside-notch", 60, 300, words="ok", size=20)  # inside the back outline, left of the notch
    assert findings(p) == []
    p.apply({"type": "move", "target": "beside-notch", "x": 165, "y": 300})  # now it runs into the notch
    assert {i["code"] for i in findings(p)} == {"outside-safe-guide", "keep-out"}


def test_strokes_and_effects_count_as_ink():
    p = wrap()
    p.apply({"type": "shape", "shape": "rectangle", "name": "badge", "x": 570, "y": 50, "width": 60, "height": 40,
             "fill": "#cc0000"})
    assert findings(p) == []
    p.apply({"type": "layer-style", "target": "badge", "name": "drop-shadow", "settings": {"dx": 0, "dy": 0, "blur": 6}})
    shadow = findings(p)
    assert [(i["code"], i["severity"]) for i in shadow] == [("outside-safe-guide", "warning")]
    assert shadow[0]["bounds"][0] < 560
    text(p, "soft", 566, 200, words="Glow")
    assert [i["layers"] for i in findings(p)] == [["badge"]]
    p.apply({"type": "effect", "target": "soft", "name": "blur", "amount": 4})
    assert sorted(i["layers"][0] for i in findings(p, "outside-safe-guide")) == ["badge", "soft"]


def test_backdrops_run_under_safe_areas_and_keep_outs_but_partial_intrusions_warn():
    p = wrap()
    p.apply({"type": "shape", "shape": "rectangle", "name": "back-art", "x": 0, "y": 0, "width": 480, "height": 400,
             "fill": "#dde6f0"})
    assert findings(p) == []
    p.apply({"type": "shape", "shape": "ellipse", "name": "sticker", "x": 270, "y": 250, "width": 60, "height": 60,
             "fill": "#ffcc00"})
    assert {(i["code"], i["severity"]) for i in findings(p)} == {("outside-safe-guide", "warning"),
                                                                 ("keep-out", "warning")}
    p.apply({"type": "layer-intent", "target": "sticker", "allow_crop": True})
    assert {i["severity"] for i in findings(p)} == {"info"}


def test_text_crossing_a_fold_is_a_review_finding():
    p = wrap()
    text(p, "wraparound", 400, 100, words="Across the spine")
    fold = findings(p, "crosses-fold")
    assert sorted(i["guide"] for i in fold) == ["fold-left", "fold-right"]
    assert {i["severity"] for i in fold} == {"warning"} and {i["action"] for i in fold} == {"review"}
    p.apply({"type": "remove", "target": "wraparound"})
    p.apply({"type": "shape", "shape": "rectangle", "name": "band", "x": 0, "y": 180, "width": 1000, "height": 20,
             "fill": "#333333"})
    assert findings(p, "crosses-fold") == [], "artwork may wrap around the spine"


def test_cli_compiles_rect_and_role():
    from vixl.commands import compile_command

    assert compile_command("guide notch --rect 180 280 120 80 --role keep-out") == {
        "type": "guide", "name": "notch", "rect": [180.0, 280.0, 120.0, 80.0], "role": "keep-out"}
    assert compile_command("guide spine x 480 --role fold")["role"] == "fold"
