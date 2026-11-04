"""Payload budgets from the Token Project (#615, #628): the start-here recipe, a kind's guide and the
layout-apply result stay under the sizes measured after each shrink, so a regrowth fails here."""

import json

from vixl import Project, briefs

# Measured after the change: guide('poster') 6,620-6,875 characters over a dozen rolls (7,973 before, 7,521 at
# the 0.30.5 measurement); a hero-statement layout-apply result at detail=brief 3,151 (3,714 before), its layout
# block 1,862 (2,321).
GUIDE_POSTER_BUDGET = 7_000
LAYOUT_APPLY_BUDGET = 3_500
LAYOUT_BLOCK_BUDGET = 2_000

HERO = {"type": "layout-apply", "name": "hero-statement", "title": "Make it simple", "subtitle": "One idea, said well.",
        "label": "Open call", "cta": "Join in", "palette": "midnight", "seed": 7}


def test_start_here_opens_with_the_one_call_route():
    steps = briefs.guide(None)["start_here"]
    first = steps[0]
    assert "vixl_apply(create=" in first and "preview=true" in first and "layout: {name:" in first and "suites" in first
    # Step by step is for edits and for art without a text frame only.
    by_hand = next(step for step in steps if step.startswith("Step by step only"))
    assert "edits" in by_hand and "without a text frame" in by_hand and "radial-repeat" in by_hand
    assert steps.index(by_hand) > steps.index(first)


def test_a_kind_points_to_the_recipe_instead_of_repeating_it():
    poster = briefs.guide("poster")
    assert poster["start_here"] == briefs.START_HERE_POINTER and "vixl_reference()" in poster["start_here"]
    assert len(json.dumps(poster)) <= GUIDE_POSTER_BUDGET
    assert briefs.guide("a mascot for a coffee brand")["start_here"] == briefs.START_HERE_POINTER
    assert briefs.guide("dog")["start_here"] == briefs.START_HERE_POINTER
    # Only the recipe itself carries the steps.
    assert briefs.guide("start here")["start_here"] == briefs.START_HERE


def test_layout_apply_result_returns_the_recipe_once_and_drops_the_direction_notes_and_fingerprint():
    brief = Project(1080, 1350).apply([HERO], detail="brief")
    block = brief["layout"]
    assert block["recipe"]["name"] == "hero-statement" and block["seed"] == 7
    assert not {"direction", "notes", "fingerprint", "layers", "principles"} & set(block)
    assert json.dumps(brief).count('"recipe"') == 1
    assert len(json.dumps(brief)) <= LAYOUT_APPLY_BUDGET and len(json.dumps(block)) <= LAYOUT_BLOCK_BUDGET
    for detail in ("compact", "full"):
        full = Project(1080, 1350).apply([HERO], detail=detail)["layout"]
        assert {"notes", "fingerprint", "layers", "principles"} <= set(full)
    # The rolled direction comes back with compact or full detail when the operation carried one.
    rolled = Project(1080, 1350).apply([{**HERO, "direction": {"cta": "pill"}}], detail="compact")["layout"]
    assert rolled["direction"]["cta"] == "pill"
    assert "direction" not in Project(1080, 1350).apply([{**HERO, "direction": {"cta": "pill"}}], detail="brief")["layout"]
