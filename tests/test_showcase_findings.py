"""Defects found while making a batch of showcase pieces (poster, report, deck, logo package, scene, cards,
form, loop, mandala, flowchart): each test fails without its fix."""

import pytest

from vixl import Project
from vixl.errors import VixlError

WAVE = [[40, 10], [60, 50], [40, 90], [50, 90], [70, 50], [50, 10]]


def test_a_filled_pen_path_has_no_stroke_unless_asked():
    p = Project(120, 120, background="white")
    p.apply({"type": "pen", "name": "wave", "points": WAVE, "closed": True, "fill": "#2f3e46"})
    layer = p.layer("wave")
    assert layer.get("stroke") in (None, "transparent", "none") and not layer.get("stroke_width")
    p.apply({"type": "pen", "name": "line", "points": [[10, 10], [100, 100]]})
    line = p.layer("line")
    assert line["stroke"] == "black" and line["stroke_width"] == 2  # an unfilled path still shows
    p.apply({"type": "pen", "name": "edged", "points": WAVE, "closed": True, "fill": "red", "stroke": "blue"})
    assert p.layer("edged")["stroke"] == "blue"


def test_a_pathfinder_of_a_filled_pen_exports_as_vector_svg(tmp_path):
    p = Project(120, 120, background="transparent")
    p.apply([{"type": "shape", "shape": "ellipse", "name": "bean", "x": 20, "y": 0, "width": 80, "height": 110,
              "fill": "#c2581c"},
             {"type": "pen", "name": "crease", "points": WAVE, "closed": True, "fill": "black"},
             {"type": "pathfinder", "name": "mark", "targets": ["bean", "crease"], "mode": "subtract"}])
    p.export(tmp_path / "mark.svg", svg_policy="strict")  # strict refuses raster fallbacks
    assert "<image" not in (tmp_path / "mark.svg").read_text()


def test_pen_restyles_a_layer_without_new_points():
    p = Project(120, 120, background="white")
    p.apply({"type": "pen", "name": "wave", "points": WAVE, "closed": True, "fill": "#2f3e46"})
    before = dict(p.layer("wave"))
    p.apply({"type": "pen", "target": "wave", "opacity": 0.5, "fill": "#ff0000"})
    after = p.layer("wave")
    assert after["opacity"] == 0.5 and after["fill"] == "#ff0000"
    assert after["path"] == before["path"] and after["x"] == before["x"] and after["width"] == before["width"]
    with pytest.raises(VixlError):
        p.apply({"type": "pen", "name": "empty", "fill": "red"})


@pytest.mark.parametrize("shape", ["ring", "donut"])
def test_ring_and_donut_take_inner_radius(shape):
    p = Project(200, 200, background="white")
    p.apply({"type": "shape", "shape": shape, "name": "r", "x": 0, "y": 0, "width": 200, "height": 200,
             "fill": "#ff0000", "inner_radius": 0.9})
    image = p.render().convert("RGB")
    assert image.getpixel((100, 4)) == (255, 0, 0)  # in the 10 px band
    assert image.getpixel((100, 30)) == (255, 255, 255)  # inside the hole (radius 70 < 90)
    p.apply({"type": "shape", "target": "r", "thickness": 40})  # an explicit thickness still wins
    assert p.render().convert("RGB").getpixel((100, 30)) == (255, 0, 0)


def test_text_hidden_under_a_layer_painted_above_it_is_a_fix_finding():
    p = Project(600, 400, background="white")
    p.apply([{"type": "text", "name": "words", "text": "Hidden words", "size": 40, "color": "black", "x": 100, "y": 150},
             {"type": "shape", "shape": "rectangle", "name": "band", "x": 0, "y": 100, "width": 600, "height": 200,
              "fill": "#333355"},
             {"type": "layer-intent", "target": "band", "decorative": True}])
    found = [x for x in p.check(checks=["overlap"])["issues"] if x.get("code") == "hidden-text"]
    assert found and found[0]["action"] == "fix" and found[0]["layers"] == ["words", "band"]
    p.apply({"type": "reorder", "target": "words", "above": "band"})
    assert not [x for x in p.check(checks=["overlap"])["issues"] if x.get("code") == "hidden-text"]
    # A translucent veil over the words does not hide them.
    p.apply({"type": "shape", "shape": "rectangle", "name": "veil", "x": 0, "y": 100, "width": 600, "height": 200,
             "fill": "#ffffff", "opacity": 0.3})
    assert not [x for x in p.check(checks=["overlap"])["issues"] if x.get("code") == "hidden-text"]


def test_mask_gradient_fades_a_layer_out():
    p = Project(200, 100, background="black")
    p.apply([{"type": "shape", "shape": "rectangle", "name": "beam", "x": 0, "y": 0, "width": 200, "height": 100,
              "fill": "#ffffff"},
             {"type": "mask", "target": "beam", "action": "gradient"}])
    image = p.render().convert("L")
    left, middle, right = (image.getpixel((x, 50)) for x in (2, 100, 197))
    assert left > 240 and 100 < middle < 160 and right < 15
    p.apply({"type": "mask", "target": "beam", "action": "gradient", "direction": "vertical",
             "stops": [{"offset": 0, "color": "#ffffffff"}, {"offset": 1, "color": "#ffffff00"}]})
    image = p.render().convert("L")
    assert image.getpixel((100, 2)) > 240 and image.getpixel((100, 97)) < 15  # a transparent stop hides too


@pytest.mark.parametrize("recipe,extra", [("hover", {"amount": 14, "period": 2400}),
                                          ("breathing", {"amount": 6, "period": 1200}),
                                          ("spin", {"turns": 1, "symmetry": 4})])
def test_stagger_in_a_seamless_loop_offsets_the_cycle_not_the_timeline(recipe, extra):
    from vixl.timeline import sample_track

    p = Project(300, 200, background="white")
    p.apply([{"type": "shape", "shape": "star", "name": f"s{i}", "x": 20 + 80 * i, "y": 80, "width": 40, "height": 40,
              "fill": "red"} for i in range(3)])
    p.apply({"type": "timeline-set", "duration": 2400, "fps": 24})
    result = p.apply({"type": "motion", "recipe": recipe, "targets": ["s0", "s1", "s2"], "stagger": 300,
                      "duration": 2400, **extra})
    timeline = p.state["timeline"]
    assert timeline["duration"] == 2400 and not result.get("warnings")
    assert not [x for x in p.check(checks=["motion"])["issues"] if x["action"] == "fix"]
    # The second target is the first one 300 ms later.
    prop = {"hover": "translate-y", "breathing": "scale-y", "spin": "rotation"}[recipe]
    first, second = ([t for t in timeline["tracks"] if t["target"] == p.layer(n)["id"] and t["property"] == prop][0]
                     for n in ("s0", "s1"))
    for time in (300, 900, 1500):
        a, b = sample_track(p, first, time - 300), sample_track(p, second, time)
        if recipe == "spin":
            a, b = a % 90, b % 90  # four-fold symmetry
        assert abs(a - b) < 0.02 * max(1, abs(a))


def test_a_motion_that_lengthens_the_timeline_warns_once():
    p = Project(300, 200, background="white")
    p.apply([{"type": "shape", "shape": "ellipse", "name": f"s{i}", "x": 20 + 80 * i, "y": 80, "width": 30,
              "height": 30, "fill": "red"} for i in range(3)])
    p.apply({"type": "timeline-set", "duration": 2400, "fps": 24, "loop_mode": "off"})
    result = p.apply({"type": "motion", "recipe": "hover", "targets": ["s0", "s1", "s2"], "amount": 14,
                      "period": 2400, "stagger": 300, "duration": 2400})
    grown = [w for w in result["warnings"] if w.startswith("timeline duration changed")]
    assert len(grown) == 1 and grown[0].startswith("timeline duration changed 2400 -> 3000 ms")
    assert "to keep 2400 ms" in grown[0]


def test_cli_apply_runs_session_steps_in_the_batch(tmp_path, monkeypatch, capsys):
    import json

    from PIL import Image

    from vixl.cli import main

    monkeypatch.chdir(tmp_path)
    Image.new("RGB", (20, 10), "red").save(tmp_path / "photo.png")
    assert main(["new", "100x80", "-o", "d.vixl", "--house-style", "off"]) == 0
    (tmp_path / "ops.json").write_text(json.dumps([
        {"type": "import-image", "path": "photo.png", "name": "photo"},
        {"type": "move", "target": "photo", "x": 30, "y": 20}]))
    capsys.readouterr()
    assert main(["-p", "d.vixl", "apply", "ops.json", "--json"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["steps"][0]["type"] == "import-image"
    layer = Project.load(tmp_path / "d.vixl").layer("photo")
    assert (layer["x"], layer["y"]) == (30, 20)
    # A failing item later in the batch leaves the document as it was.
    (tmp_path / "bad.json").write_text(json.dumps([
        {"type": "import-image", "path": "photo.png", "name": "second"}, {"type": "move", "target": "nope", "x": 1}]))
    assert main(["-p", "d.vixl", "apply", "bad.json", "--json"]) != 0
    assert not [x for x in Project.load(tmp_path / "d.vixl").state["layers"] if x["name"] == "second"]


def test_cli_export_writes_motion_formats_from_the_timeline(tmp_path, monkeypatch, capsys):
    import json

    from PIL import Image

    from vixl.cli import main

    monkeypatch.chdir(tmp_path)
    assert main(["new", "60x60", "-o", "d.vixl", "--house-style", "off"]) == 0
    assert main(["-p", "d.vixl", "shape", "ellipse", "--name", "ball", "--width", "20", "--height", "20"]) == 0
    assert main(["-p", "d.vixl", "timeline", "set", "--duration", "500ms"]) == 0
    assert main(["-p", "d.vixl", "keyframe", "ball", "x", "0", "0"]) == 0
    assert main(["-p", "d.vixl", "keyframe", "ball", "x", "250ms", "40"]) == 0
    capsys.readouterr()
    assert main(["-p", "d.vixl", "export", "loop.gif", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["format"] == "gif"
    assert Image.open(tmp_path / "loop.gif").n_frames > 1
    assert main(["-p", "d.vixl", "export", "loop.gif", "--json"]) != 0  # refuses to overwrite
    assert main(["-p", "d.vixl", "export", "loop.gif", "--overwrite", "--json"]) == 0


def test_brief_results_condense_large_new_groups():
    import json

    p = Project(800, 600, background="#112233")
    result = p.apply({"type": "star-field", "count": 140, "seed": 3}, detail="brief")
    group = next(entry for entry in result["changes"]["layers"].values() if entry["name"] == "stars")
    assert group["children_added"] == 140 and len(group["children_sample"]) == 5
    assert len(result["changes"]["layers"]) == 1 and len(json.dumps(result)) < 4000
    assert not result.get("warnings")  # stars on the sky's edge are not crops to report
    full = p.apply({"type": "star-field", "name": "more", "count": 20, "seed": 4}, detail="compact")
    assert len(full["changes"]["layers"]) > 20  # compact still lists every child


@pytest.mark.parametrize("brief,kind", [("a lighthouse on a rocky headland at dusk", "scene"),
                                        ("an ad for running shoes", "banner-ad"),
                                        ("a set of icons for a weather app", "app-icon"),
                                        ("three posters for a film club", "poster")])
def test_briefs_match_whole_words(brief, kind):
    from vixl.briefs import match

    assert match(brief)[0] == kind


def test_create_look_without_target_finishes_the_background_or_shapes(tmp_path):
    from vixl.compose import compose
    from vixl.interfaces import Session

    session = Session(workspace=tmp_path)
    layout = {"name": "event-poster", "seed": 41, "title": "Blue Hour", "body": "9 pm", "label": "Aug 14",
              "cta": "Tickets", "caption": "example.org"}
    compose(session, path="grain.vixl", size="instagram-portrait", layout=layout, look={"look": "grain"},
            check=False)
    finished = {layer["name"] for layer in Project.load(tmp_path / "grain.vixl").state["layers"]
                if any(e["name"] == "grain" for e in layer.get("effects", []))}
    assert finished == {"background"}
    compose(session, path="shadow.vixl", size="instagram-portrait", layout=layout, look={"look": "hard-shadow"},
            check=False)
    shadowed = {layer["name"] for layer in Project.load(tmp_path / "shadow.vixl").state["layers"]
                if (layer.get("styles") or {}).get("drop-shadow")}
    assert shadowed and all(layer_type == "shape" for layer_type in
                            (Project.load(tmp_path / "shadow.vixl").layer(n)["type"] for n in shadowed))


DECK = """# Tidewater Coffee Co-op

From bean to cup on the Gulf coast · Q3 review for members

## Where we are

- **214 member farms** across three growing regions
- Roastery output up **38%** year on year

## Pounds roasted per quarter

```chart line
Quarter,2025,2026
Q1,41200,55800
Q2,46900,63100
Q3,52300,72200
```

## Region scorecard

```csv
Region,Farms,Avg score
Chiapas,92,86.5
Cauca,51,85.2
```

## What we heard

> Being in the co-op means my daughter can stay on the farm and still make a living.
— Lucía Ramírez
"""


def test_deck_from_markdown_fits_the_cover_and_keeps_one_type_scale(tmp_path):
    from vixl.plugins.deck_markdown.deck_markdown import run
    from vixl.interfaces import Session

    (tmp_path / "deck.md").write_text(DECK, encoding="utf-8")
    summary = run(Session(workspace=tmp_path), {"markdown": "deck.md", "output": "deck.vixl"})
    kinds = {(issue["check"], issue["message"].split(" ")[0]) for issue in summary["check"]["issues"]}
    assert not [i for i in summary["check"]["issues"] if i["check"] in ("bounds", "safe_area", "type_scale")], kinds
    p = Project.load(tmp_path / "deck.vixl")
    scale = {round(s["size"]) for s in p.state["character_styles"].values()}
    sizes = {}
    for page in p.state["pages"]:
        p.apply({"type": "page", "action": "select", "page": page["name"]})
        sizes[page["name"]] = {layer["name"]: layer["size"] for layer in p.state["layers"]
                               if layer["type"] == "text" and not layer.get("parent") and layer.get("role") != "decoration"}
    titles = {sizes[name]["title"] for name in ("where-we-are", "pounds-roasted-per-quarter", "region-scorecard")}
    assert len(titles) == 1 and titles <= scale  # one content-title size, on the scale
    assert sizes["where-we-are"]["body"] == p.state["character_styles"]["lead"]["size"]  # few bullets: lead step
    assert sizes["what-we-heard"]["quote"] in scale


def test_a_long_left_to_right_flow_keeps_its_labels_large():
    text = "\n".join(["A([Cherry harvest]) -> B{Ripe?}", "B -> C[Pulp & ferment]: yes", "B -> D[Compost]: no",
                      "C -> E[Sun-dry 2–3 weeks]", "E -> F{Cup score ≥ 84?}", "F -> G[(Co-op green lot)]: yes",
                      "F -> H[Sell locally]: no", "G -> I[/Low-carbon shipping/]", "I -> J[Roast in Mobile]",
                      "J -> K([Café & members])"])
    p = Project(2400, 1350, background="#fbf8f2")
    result = p.apply({"type": "diagram-from-text", "name": "flow", "text": text, "direction": "LR", "x": 120,
                      "y": 330, "width": 2160, "height": 900})
    report = result["diagram"]["flow"]
    assert report["label_size"] >= 26 and report["size"][0] <= 2160
    assert not [x for x in p.check(checks=["diagram", "overlap"])["issues"] if x["action"] == "fix"]
    # Gaps the caller sets are kept as given.
    p.apply({"type": "diagram-set", "name": "flow", "rank_gap": 68, "node_gap": 44})
    assert p.state["diagrams"]["flow"]["spec"]["rank_gap"] == 68


def test_an_empty_middle_between_headline_and_copy_is_a_dead_band():
    p = Project(1000, 1400, background="#101828")
    p.apply([{"type": "text", "name": "headline", "text": "Blue Hour Jazz", "size": 90, "color": "#ffffff",
              "x": 60, "y": 60},
             {"type": "text", "name": "date", "text": "Aug 14 – 16", "size": 60, "color": "#ffffff", "x": 60,
              "y": 1000},
             {"type": "text", "name": "details", "text": "Late sets from 9 pm\nQuayside Stage", "size": 40,
              "color": "#ffffff", "x": 60, "y": 1110}])
    found = [x for x in p.check(checks=["composition"])["issues"] if x.get("code") == "dead_band"]
    assert found and found[0]["values"]["frame_share"] > 0.42
    # Artwork closing the band (a scene under the headline) is a setting, not a hole.
    p.apply({"type": "shape", "shape": "rectangle", "name": "scene", "x": 0, "y": 200, "width": 1000,
             "height": 760, "fill": "#334466"})
    assert not [x for x in p.check(checks=["composition"])["issues"]
                if x.get("code") == "dead_band" and x["values"]["frame_share"] > 0.3]
    # A headline over a single credit line far below is a minimal composition, not a hole.
    q = Project(1000, 1400, background="#101828")
    q.apply([{"type": "text", "name": "headline", "text": "Quiet", "size": 120, "color": "#ffffff", "x": 60, "y": 60},
             {"type": "text", "name": "credit", "text": "Gallery 4 · until May", "size": 32, "color": "#ffffff",
              "x": 60, "y": 1250}])
    assert not [x for x in q.check(checks=["composition"])["issues"] if x.get("code") == "dead_band"]


def test_align_reads_to_as_relative_to():
    p = Project(400, 300, background="white")
    p.apply([{"type": "shape", "shape": "rectangle", "name": "a", "x": 10, "y": 10, "width": 50, "height": 50},
             {"type": "shape", "shape": "rectangle", "name": "b", "x": 200, "y": 100, "width": 80, "height": 50}])
    result = p.apply({"type": "align", "target": "a", "alignment": "right", "to": "b"})
    assert "operation: 'to' → 'relative_to'" in result["normalized"] and p.layer("a")["x"] == 230
