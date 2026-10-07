"""Craft defaults: text size and leading, safe area, primitive fills/strokes/corners, irregularity strength,
diagram colours and template scaling (house-style decisions B3, B4, B6, B7, C5, D7, E2, E7, E8, F4)."""

from PIL import Image
import pytest

from vixl import Project
from vixl.craft import LINE_HEIGHT, NEUTRAL_FILL, natural_height
from vixl.errors import VixlError
from vixl.text import font_data


def pitch(project, layer):
    """Distance between baselines of a plain text layer."""
    return natural_height(font_data(project, layer), layer["size"]) + layer["spacing"]


# Text size (#408) and leading (#421, #282)

def test_default_text_size_is_proportional_to_the_canvas_and_reported():
    sizes = []
    for side in (1080, 4000):
        project = Project(side, side, background="#ffffff")
        result = project.apply({"type": "text", "name": "t", "text": "Hello"})
        size = project.layer("t")["size"]
        assert result["defaults"][0]["size"] == size
        assert size >= 0.022 * side  # the scale-aware minimum for minor text
        sizes.append(size)
    assert sizes[1] / sizes[0] == pytest.approx(4000 / 1080, rel=0.03)


def test_default_text_size_follows_the_type_scale():
    project = Project(1080, 1080)
    project.apply([{"type": "type-scale", "base": 33, "ratio": "major-third"}, {"type": "text", "name": "t", "text": "x"},
                   {"type": "rich-text", "name": "r", "markdown": "**x** y"}])
    assert project.layer("t")["size"] == project.layer("r")["size"] == 33


@pytest.mark.parametrize("size, stage", [(28, "body"), (40, "lead"), (60, "heading"), (120, "display"), (20, "caption")])
def test_plain_text_leading_follows_the_line_height_table(size, stage):
    project = Project(1080, 1080)
    project.apply({"type": "text", "name": "t", "text": "One\nTwo", "size": size})
    layer = project.layer("t")
    assert layer["line_height"] == LINE_HEIGHT[stage]
    assert pitch(project, layer) == pytest.approx(LINE_HEIGHT[stage] * size, abs=0.03 * size)


def test_line_height_follows_a_new_size_and_spacing_overrides_it():
    project = Project(1080, 1080)
    project.apply([{"type": "text", "name": "t", "text": "One\nTwo", "size": 40, "line_height": 1.45},
                   {"type": "text-set", "target": "t", "size": 80}])
    layer = project.layer("t")
    assert pitch(project, layer) == pytest.approx(1.45 * 80, abs=1)
    project.apply({"type": "text-set", "target": "t", "spacing": 2})
    assert project.layer("t")["spacing"] == 2 and "line_height" not in project.layer("t")


def test_display_type_can_take_negative_spacing():
    project = Project(1080, 1080)
    project.apply({"type": "text", "name": "t", "text": "TIGHT\nTYPE", "size": 100, "spacing": -30})
    assert project.layer("t")["spacing"] == -30
    with pytest.raises(VixlError):
        project.apply({"type": "text-set", "target": "t", "spacing": -150})


def test_rich_text_leading_is_a_multiple_of_the_size():
    from vixl.richtext import layout

    project = Project(1080, 1080)
    project.apply({"type": "rich-text", "name": "r", "markdown": "First line\nSecond line", "size": 30})
    layer = project.layer("r")
    assert layer["rich"]["line_basis"] == "size" and layer["rich"]["line_height"] == LINE_HEIGHT["body"]
    lines = layout(project, layer).lines
    assert lines[1][1] - lines[0][1] == pytest.approx(LINE_HEIGHT["body"] * 30, abs=0.5)


def test_legacy_rich_text_keeps_its_leading():
    from vixl.richtext import layout

    project = Project(1080, 1080)
    project.apply({"type": "text", "name": "r", "text": "First\nSecond", "size": 30, "spacing": 4})
    layer = project.layer("r")
    layer["rich"] = {"spans": [{"text": "First\nSecond"}], "paragraphs": [{}, {}]}
    lines = layout(project, layer).lines
    natural = natural_height(font_data(project, layer), 30)
    assert lines[1][1] - lines[0][1] == pytest.approx(natural * 1.2 + 4, abs=0.5)


def test_converting_plain_text_to_rich_keeps_its_line_pitch():
    from vixl.richtext import layout

    project = Project(1080, 1080)
    project.apply({"type": "text", "name": "t", "text": "Alpha beta\nGamma", "size": 36})
    before = pitch(project, project.layer("t"))
    project.apply({"type": "text-style", "target": "t", "match": "beta", "bold": True})
    lines = layout(project, project.layer("t")).lines
    assert lines[1][1] - lines[0][1] == pytest.approx(before, abs=1)


def test_text_flow_body_leading():
    project = Project(1200, 1200, background="#ffffff")
    project.apply({"type": "text-flow", "name": "story", "text": "word " * 200,
                   "frames": [{"x": 100, "y": 100, "width": 400, "height": 900}]})
    frame = next(layer for layer in project.state["layers"] if layer["type"] == "text")
    assert frame["size"] == 31  # body size for a 1200 px canvas
    assert pitch(project, frame) == pytest.approx(1.45 * frame["size"], abs=0.03 * frame["size"])


def test_layout_body_and_subtitle_leading_is_not_loose():
    project = Project.sized("instagram-square")
    project.apply({"type": "layout-apply", "name": "slide-title", "seed": 1, "unfilled": "omit",
                   "title": "A fairly long title that wraps over lines",
                   "subtitle": "A subtitle that also needs to wrap over two lines for testing leading"})
    subtitle = project.layer("subtitle")
    assert pitch(project, subtitle) <= 1.5 * subtitle["size"]  # #282 measured about 1.9


# Safe area (#409, #370)

def test_custom_size_documents_get_a_five_percent_safe_area():
    assert Project(1000, 1000).state["canvas"]["safe"] == 50
    project = Project(1000, 1000)
    project.apply({"type": "canvas", "width": 2000, "height": 800})
    assert project.state["canvas"]["safe"] == 40
    # A named size keeps its own safe area, including an explicit none.
    assert "safe" not in Project.sized("favicon-32").state["canvas"]
    assert Project.sized("instagram-square").state["canvas"]["safe"] == 60


@pytest.mark.parametrize("size", ["instagram-square", "story", "1080x1080"])
@pytest.mark.parametrize("name, slots, count", [
    ("meme-top-bottom", {"title": "When the build passes", "caption": "on the first try"}, 1),
    ("meme-four-panel", {"items": "Idea\nPrototype\nScope creep\nRewrite"}, 4),
    ("meme-comparison", {"items": "By hand\nFrom the schema"}, 2),
    ("meme-labelled", {"items": "Me\nNew framework\nWorking code"}, 1),
    ("meme-reaction", {"caption": "Me reading my own code"}, 1),
    ("meme-caption-above", {"title": "Me explaining the meeting"}, 1),
])
def test_memes_pass_their_own_safe_area_check(size, name, slots, count):
    from vixl.assets import add_image

    project = Project(1080, 1080) if size[0].isdigit() else Project.sized(size)
    assets = [add_image(project, Image.new("RGB", (64, 64), "#c96")) for _ in range(count)]
    images = {"images": assets} if count > 1 else {"image": assets[0]}
    project.apply({"type": "layout-apply", "name": name, "seed": 1, **slots, **images})
    issues = [i for i in project.check()["issues"] if i["check"] == "safe_area" and i["severity"] != "info"]
    assert not issues, [i["message"] for i in issues]


def _social_sizes():
    from vixl.sizes import SIZES

    return [name for name, entry in SIZES.items() if entry["category"] in ("social", "web")]


def _rollable_on(size):
    """Layouts a social roll can pick for this size (tier, purpose, orientation), plus app-icon."""
    from vixl import house_style
    from vixl.sizes import SIZES
    from vixl.variety import orientation

    shape = orientation(SIZES[size]["width"], SIZES[size]["height"])
    for name, meta in sorted(house_style.entries("layouts").items()):
        rollable = meta["tier"] != "explicit" and "social" in meta.get("purposes", [])
        if (rollable or name == "app-icon") and shape in meta.get("orientations", [shape]):
            yield name, shape


@pytest.mark.parametrize("size", _social_sizes())
def test_layouts_pass_their_own_safe_area_check_on_social_and_web_sizes(size):  # #409, #370
    from vixl.layouts import places

    copy = {"title": "Summer Night Market", "subtitle": "Food, music and late shopping", "label": "June 21",
            "cta": "Free entry"}
    failures = []
    for index, (name, shape) in enumerate(_rollable_on(size)):
        # A roll only picks a layout that places all the copy it was given; try the full brief, then less.
        slots = next((dict((k, copy[k]) for k in keys) for keys in (("cta", "label", "subtitle", "title"),
                      ("subtitle", "title"), ("title",)) if places(name, shape, keys)), None)
        if slots is None:
            continue
        project = Project.sized(size, design=False)
        project.apply({"type": "layout-apply", "name": name, "seed": index % 3, "unfilled": "omit", **slots})
        failures += [f"{name}: {i['message']}" for i in project.check(checks=["safe_area"])["issues"]
                     if i["check"] == "safe_area" and i["severity"] != "info"]
    assert not failures, failures


# Primitive fills, strokes and corners (#410)

def test_primitives_use_the_palette_roles():
    project = Project(800, 600)
    project.apply([{"type": "swatch", "name": role, "color": value} for role, value in
                   (("accent", "#c0392b"), ("surface", "#eeeeee"), ("ink", "#111111"))])
    result = project.apply([{"type": "shape", "shape": "rectangle", "name": "box", "width": 200, "height": 100},
                            {"type": "solid", "name": "panel"},
                            {"type": "shape", "shape": "ellipse", "name": "ring", "width": 200, "height": 200,
                             "stroke_width": 3}])
    assert project.layer("box")["fill"] == "@accent"
    assert project.layer("panel")["fill"] == "@surface"
    assert project.layer("ring")["stroke"] == "@ink"
    assert {"layer": "box", "fill": "@accent"} in result["defaults"]


def test_without_a_palette_fills_are_neutral_and_strokes_proportional():
    project = Project(800, 600, background="#ffffff")
    project.apply([{"type": "shape", "shape": "rectangle", "name": "box", "width": 400, "height": 200, "stroke": "#000"},
                   {"type": "solid", "name": "panel"}])
    assert project.layer("box")["fill"] == project.layer("panel")["fill"] == NEUTRAL_FILL
    assert project.layer("box")["stroke_width"] == 3  # 1.5% of the 200 px short side


def test_open_shapes_stay_unfilled_in_every_renderer(tmp_path):
    from vixl.geometry import default_fill

    project = Project(400, 400, background="#ffffff")
    project.apply([{"type": "shape", "shape": "path", "name": "curve", "path": "M10 10 C100 300 200 -100 300 200"},
                   {"type": "shape", "shape": "line", "name": "rule", "x": 20, "y": 350, "width": 300, "height": 4}])
    for name in ("curve", "rule"):
        layer = project.layer(name)
        assert "fill" not in layer and layer["stroke"] and default_fill(layer) == "transparent"
    project.export(tmp_path / "a.svg")
    svg = (tmp_path / "a.svg").read_text()
    assert "rgb(140,140,140)" not in svg and "rgb(17,17,17)" in svg


def test_new_rounded_shapes_inherit_the_document_corner_style():
    project = Project(800, 600)
    project.apply({"type": "shape", "shape": "rounded-rectangle", "name": "soft", "width": 200, "height": 100})
    assert project.layer("soft")["radius"] == 8  # the house style is sharp, so a rounded shape is softly rounded
    project.state["design_defaults"] = {"seed": 1, "variety": "medium", "direction": {"corner": "round"}}
    project.apply({"type": "shape", "shape": "rounded-rectangle", "name": "round", "width": 200, "height": 100})
    assert project.layer("round")["radius"] == 25


@pytest.mark.parametrize("corner, radius", [(None, 0), ("pill", 0.5), ("soft", 0.08)])
def test_layout_buttons_inherit_the_document_corner_style(corner, radius):
    project = Project.sized("instagram-portrait", design=False)
    if corner:
        project.state["design_defaults"] = {"seed": 1, "variety": "medium", "direction": {"corner": corner}}
    for seed in range(4):
        trial = project.clone()
        trial.apply({"type": "layout-apply", "name": "quiet-editorial", "seed": seed, "title": "Open studio",
                     "cta": "Book a visit", "unfilled": "omit"})
        button = trial.layer("cta-button")
        # Without a stored direction the house corner (sharp) applies, not a random pill/rounded/square.
        assert button.get("radius", 0) == pytest.approx(button["height"] * radius, abs=1)


def test_containers_and_directions_inherit_the_corner_style():
    project = Project(1200, 900)
    project.apply([{"type": "swatch", "name": role, "color": value} for role, value in
                   (("ink", "#111111"), ("accent", "#c0392b"), ("on-accent", "#ffffff"), ("muted", "#555555"))])
    project.state["design_defaults"] = {"seed": 1, "variety": "medium", "direction": {"corner": "sharp"}}
    project.apply({"type": "container-place", "name": "card", "resource": "cta", "variant": "default",
                   "width": 600, "height": 300})
    part = project.layer("card/button-background")
    assert part["shape"] == "rectangle" and not part.get("radius")
    project.state["design_defaults"]["direction"]["corner"] = "pill"
    project.apply({"type": "container-place", "name": "pill", "resource": "cta", "variant": "default",
                   "width": 600, "height": 300})
    assert project.layer("pill/button-background")["radius"] == pytest.approx(300 * 0.27 * 0.5, abs=1)
    # A direction without a corner falls back to the house corner, sharp (E8), not soft.
    plain = Project(800, 800)
    plain.apply({"type": "layout-apply", "name": "soft-panel", "seed": 2, "title": "Hello", "unfilled": "omit",
                 "direction": {"look": "none"}})
    assert plain.layer("quiet-panel")["shape"] == "rectangle" and not plain.layer("quiet-panel").get("radius")


def test_brush_defaults_follow_the_stroke_rule():
    project = Project(1000, 800)
    project.apply([{"type": "swatch", "name": "ink", "color": "#202020"}, {"type": "paint-layer", "name": "p"},
                   {"type": "paint", "target": "p", "points": [[10, 10], [200, 200]]}])
    stroke = project.layer("p")["strokes"][0]
    assert stroke["size"] == 12 and stroke["color"] == "@ink"


# Irregularity (#425)

def test_irregular_and_tear_default_to_subtle_and_older_recipes_stay_natural():
    project = Project(600, 600)
    project.apply([{"type": "shape", "shape": "rectangle", "name": "box", "width": 200, "height": 200, "fill": "#333"},
                   {"type": "irregular", "target": "box", "seed": 3},
                   {"type": "tear", "name": "scrap", "as": "path", "seed": 2, "width": 300, "height": 200}])
    assert project.layer("box")["irregular"]["recipe"]["strength"] == "subtle"
    torn = next(layer for layer in project.state["layers"] if layer.get("tear"))
    assert torn["tear"]["recipe"]["strength"] == "subtle"
    legacy = Project(600, 600)
    legacy.apply([{"type": "shape", "shape": "rectangle", "name": "box", "width": 200, "height": 200, "fill": "#333"},
                  {"type": "irregular", "target": "box", "seed": 3}])
    legacy.layer("box")["irregular"]["recipe"].pop("strength")
    legacy.apply({"type": "irregular", "target": "box", "seed": 4})
    assert legacy.layer("box")["irregular"]["recipe"]["strength"] == "natural"


# Diagrams (#397)

def test_diagrams_follow_the_palette_and_dark_mode():
    project = Project(1200, 800, background="#101820")
    project.apply({"type": "layout-apply", "name": "calm-cover", "title": "Hi", "mode": "dark", "seed": 3,
                   "unfilled": "omit"})
    project.apply({"type": "diagram", "name": "d", "text": "Start -> Check -> End", "x": 400, "y": 200,
                   "width": 700, "height": 500})
    assert project.state["diagrams"]["d"]["spec"]["theme"] == "palette"
    fills = {layer.get("fill") for layer in project.state["layers"] if layer.get("name", "").startswith("d/")}
    assert "@surface" in fills
    contrast = [i for i in project.check(checks=["contrast"])["issues"] if i["severity"] == "error"]
    assert not contrast


def test_diagrams_without_a_palette_follow_the_canvas_mode():
    for background, theme in (("#101820", "dark"), ("#ffffff", "light")):
        project = Project(800, 600, background=background)
        project.apply({"type": "diagram", "name": "d", "text": "A -> B"})
        assert project.state["diagrams"]["d"]["spec"]["theme"] == theme
    with pytest.raises(VixlError, match="palette swatches"):
        project.apply({"type": "diagram-set", "name": "d", "theme": "palette"})


# Simple templates (#398)

@pytest.mark.parametrize("name", ["social-square", "story", "thumbnail", "poster", "business-card"])
def test_simple_templates_scale_with_the_canvas(name):
    from vixl.render import resolve_layout
    from vixl.resources import TEMPLATES

    item = TEMPLATES[name]
    shapes = []
    for factor in (0.5, 2):
        w, h = round(item["width"] * factor), round(item["height"] * factor)
        project = Project(w, h)
        project.apply({"type": "template-apply", "name": name, "seed": 1,
                       "variables": {"title": "Title", "subtitle": "Subtitle"}})
        bounds = resolve_layout(project)
        shapes.append([(bounds[layer["id"]][0] / w, bounds[layer["id"]][1] / h, bounds[layer["id"]][3] / h)
                       for layer in project.state["layers"]])
        issues = project.check(checks=["bounds", "legibility"])["issues"]
        assert not [i for i in issues if i["severity"] in ("error", "warning")], issues
    for small, large in zip(*shapes):
        assert small == pytest.approx(large, abs=0.01)
