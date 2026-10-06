"""The form worst-case check is deterministic and explains what it measured (T06 evaluation, #81).

Forms here are letter pages at 72 dpi (612 x 792 px, one pixel per point) so each check is quick."""

from pathlib import Path

import pytest

from vixl import Project
from vixl.errors import VixlError
from vixl.fonts import import_font
from vixl.forms import fill

FONT = Path(__file__).parents[1] / "src" / "vixl" / "data" / "DejaVuSans.ttf"


def page():
    return Project.sized("letter", "#ffffff", dpi=72)


def sign_up(phone_width=288):
    p = page()
    p.apply([
        {"type": "field", "name": "performer_name", "kind": "text", "label": "Name", "size": 10.5, "x": 54, "y": 144,
         "width": 504, "height": 26, "max_length": 80, "min_size": 6.5},
        {"type": "field", "name": "phone", "kind": "text", "label": "Phone", "size": 10.5, "x": 54, "y": 216,
         "width": phone_width, "height": 26, "max_length": 24},
        {"type": "field", "name": "pieces", "kind": "multiline", "label": "Pieces", "size": 9.6, "x": 54, "y": 288,
         "width": 504, "height": 40},
        {"type": "field", "name": "signature", "kind": "text", "label": "Signature", "size": 10.5, "x": 54, "y": 672,
         "width": 288, "height": 26, "max_length": 60},
    ])
    return p


def worst(p):
    return {i["key"]: i for i in p.check(checks=["form"], sample="worst")["issues"] if "key" in i}


def test_results_are_deterministic_and_independent_of_other_fields(tmp_path):
    p = sign_up()
    first = worst(p)
    assert {"performer_name", "signature", "pieces"} <= set(first)
    assert first == worst(p), "the same document gives the same report"
    p.save(tmp_path / "form.vixl")
    assert worst(Project.load(tmp_path / "form.vixl")) == first, "and so does a reloaded copy"
    # Add a field and narrow two others: the fields that did not change keep exactly their result.
    q = sign_up(phone_width=120)
    q.apply([{"type": "field", "name": "instagram", "kind": "text", "label": "Instagram", "size": 10.5, "x": 400, "y": 216,
              "width": 120, "height": 26, "max_length": 31},
             {"type": "resize", "target": "performer_name", "width": 480, "height": 26}])
    after = worst(q)
    for key in ("signature", "pieces"):
        assert after.get(key) == first.get(key), key
    assert {"phone", "instagram"} <= set(after) and after["performer_name"]["measured"]["box_width"] == 480


def test_report_says_what_it_measured():
    issue = worst(sign_up())["signature"]
    measured = issue["measured"]
    assert issue["code"] == "overflow" and measured["status"] == "overflow"
    assert measured["sample"].startswith("WWWW") and measured["characters"] == 60
    assert measured["font"].startswith("DejaVu Sans") and "proofing fallback" in measured["font"]
    assert measured["box_width"] == 288 and measured["inner_width"] == 288 - 2 * measured["padding"]
    assert measured["size"] == 10.5 and measured["size_measured"] == measured["min_size"] == 7.35
    assert measured["rendered_width"] > measured["inner_width"]
    for fragment in ("60 characters", f"{measured['rendered_width']:g} px", f"{measured['inner_width']:g} px",
                     "DejaVu Sans", "smallest size"):
        assert fragment in issue["message"], fragment
    # The suggested limit really is the longest that fits.
    fits = measured["max_length_that_fits"]
    assert 0 < fits < 60
    p = sign_up()
    p.apply({"type": "field-set", "target": "signature", "max_length": fits})
    assert "signature" not in worst(p)
    p.apply({"type": "field-set", "target": "signature", "max_length": fits + 1})
    assert "signature" in worst(p)


def test_report_names_a_registered_font():
    p = page()
    import_font(p, FONT, "body")
    p.apply([{"type": "font-register", "name": "body", "role": "body"},
             {"type": "field", "name": "code", "kind": "text", "label": "Code", "x": 20, "y": 20, "width": 80, "height": 24,
              "max_length": 30}])
    assert p.layer("code")["font"].startswith("fonts/")
    assert "DejaVu Sans Book (registered as body)" in worst(p)["code"]["measured"]["font"]


def test_multiline_worst_case_wraps_and_max_length_can_fix_it():
    p = page()
    p.apply({"type": "field", "name": "pieces", "kind": "multiline", "label": "Pieces", "size": 9.6, "x": 54, "y": 100,
             "width": 336, "height": 72})
    issue = worst(p)["pieces"]
    measured = issue["measured"]
    assert measured["characters"] == 400 and measured["lines"] > 1 and "wrap to" in issue["message"]
    assert measured["longest_word_width"] < measured["inner_width"], "the sample is words, not one unbreakable run"
    fits = measured["max_length_that_fits"]
    assert 0 < fits < 400
    p.apply({"type": "field-set", "target": "pieces", "max_length": fits})
    assert worst(p) == {}, "a max_length that fits clears the error"
    p.apply({"type": "field-set", "target": "pieces", "max_length": fits + 40})
    assert "pieces" in worst(p)


def test_sample_rows_and_fills_report_numbers_never_values(tmp_path):
    p = sign_up(phone_width=72)
    secret = "Wolverine-Wombat-1234567"
    (tmp_path / "rows.csv").write_text(f"phone\n{secret}\n")
    issues = p.check(checks=["form"], sample=str(tmp_path / "rows.csv"))["issues"]
    flagged = [i for i in issues if i.get("key") == "phone"]
    assert flagged and "sample" not in flagged[0]["measured"] and "max_length_that_fits" not in flagged[0]["measured"]
    assert "Wolverine" not in flagged[0]["message"] and flagged[0]["measured"]["characters"] == 24
    with pytest.raises(VixlError) as error:
        fill(p, {"phone": secret}, tmp_path / "out.png")
    assert error.value.details["errors"][0]["measured"]["rendered_width"] > 0
    assert "Wolverine" not in str(error.value) and "Wolverine" not in str(error.value.details)
