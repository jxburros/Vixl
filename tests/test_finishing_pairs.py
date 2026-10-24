"""The finishing pairs of the skill (skills/vixl/references/finishing-pairs.md): each pair's generic page has the
composition finding it names, and its fix operations close it without opening another."""

import json
from pathlib import Path
import re

import pytest

import vixl
from vixl import Project
from vixl.composition import CODES
from vixl.fonts import import_font

ROOT = Path(__file__).resolve().parent.parent
PAGE = ROOT / "skills" / "vixl" / "references" / "finishing-pairs.md"
DATA = Path(vixl.__file__).parent / "data"
PAIRS = [json.loads(block) for block in re.findall(r"```json\n(.*?)\n```", PAGE.read_text(encoding="utf-8"), re.S)]


def page(pair):
    """The 1200 x 800 page of a pair; one that needs a heading and a body face gets two distinct bundled ones."""
    if pair.get("create"):
        return Project.new(width=1200, height=800, **pair["create"])
    project = Project(1200, 800, "white")
    if pair["finding"] == "single_weight":
        import_font(project, DATA / "NotoSans-Regular.ttf", "noto")
        import_font(project, DATA / "DejaVuSans.ttf", "dejavu")
        project.state["typography"] = {"heading": "dejavu", "body": "noto"}
    return project


def codes(project):
    return {x["code"] for x in project.check(checks=["composition"], waivers=False)["issues"]
            if x["check"] == "composition"}


def test_the_page_has_four_to_six_pairs_that_each_name_a_composition_code():
    assert 4 <= len(PAIRS) <= 6
    assert all(pair["finding"] in CODES for pair in PAIRS)
    assert len({pair["finding"] for pair in PAIRS}) == len(PAIRS)
    assert {"flat_hierarchy", "single_weight", "no_focal", "accent_unused"} <= {pair["finding"] for pair in PAIRS}


@pytest.mark.parametrize("pair", PAIRS, ids=[pair["finding"] for pair in PAIRS])
def test_the_fix_closes_the_gap_the_generic_page_has(pair):
    project = page(pair)
    project.apply(pair["generic"])
    before = codes(project)
    assert pair["finding"] in before
    project.apply(pair["fix"])
    after = codes(project)
    assert pair["finding"] not in after
    assert after <= before - {pair["finding"]}, "the fix opened another finding"
    # Nothing but the bundled proofing font (no pairing is installed here) needs fixing.
    assert {x["check"] for x in project.check()["issues"] if x["action"] == "fix"} <= {"fonts"}
