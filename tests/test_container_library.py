"""Responsive content, semantic swaps, shaped image slots, hug boxes and comic pages."""

from copy import deepcopy

from PIL import Image
import pytest

from vixl.assets import add_image, decode
from vixl.containers import measure
from vixl.errors import VixlError
from vixl.project import Project
from vixl.render import resolve_layout, render
from vixl.resources import CONTAINERS, TEMPLATES, create_template


def populated(name, *, variant=None, size=(480, 320)):
    p = Project(1000, 800)
    asset = add_image(p, Image.new("RGBA", (1200, 1200), "#739aaf"))
    item = CONTAINERS[name]
    values = {
        k: asset if k == "photo" else "42" if k in ("value", "price") else "Clear message"
        for k in item["defaults"]
    }
    p.apply(
        [
            {"type": "palette-apply", "name": "slate"},
            {
                "type": "container-place",
                "name": "card",
                "resource": name,
                "variables": values,
                "width": size[0],
                "height": size[1],
                "seed": 12,
                **({"variant": variant} if variant else {}),
            },
        ]
    )
    return p


def test_hug_background_remeasures_variable_content_and_nested_stacks():
    p = Project(600, 300)
    p.apply(
        [
            {"type": "variable", "name": "label", "value": "Go"},
            {"type": "text", "name": "copy", "text": "${label}", "size": 24},
            {
                "type": "stack",
                "name": "button",
                "targets": ["copy"],
                "size": "hug",
                "background": "#336699",
                "stroke": "#111111",
                "radius": 16,
                "padding": {"left": 18, "right": 22, "top": 8, "bottom": 10},
            },
            {"type": "text", "name": "after", "text": "Next", "size": 24},
            {
                "type": "stack",
                "name": "row",
                "targets": ["button", "after"],
                "size": "hug",
                "direction": "horizontal",
                "gap": 12,
            },
        ]
    )
    first = resolve_layout(p)
    bid = p.layer("button")["id"]
    after = p.layer("after")["id"]
    before = first[bid][2]
    assert first[after][0] == before + 12
    p.apply({"type": "variable", "name": "label", "value": "A much longer action"})
    bounds = resolve_layout(p)
    bg = p.layer("button/background")["id"]
    assert bounds[bid][2] > before
    assert bounds[bg][2:] == bounds[bid][2:]
    assert bounds[after][0] == bounds[bid][2] + 12
    assert render(p).getbbox()


@pytest.mark.parametrize(
    "name",
    [
        name
        for name in CONTAINERS
        if name
        in (
            "stat",
            "testimonial",
            "feature-icon",
            "cta",
            "pricing-tier",
            "profile",
            "timeline-step",
            "list-block",
            "badge",
            "ribbon",
            "photo-caption",
            "product-card",
            "section-header",
        )
    ],
)
def test_library_containers_fit_and_render(name):
    p = populated(name)
    assert measure(p)["passed"], measure(p)
    assert render(p).getbbox()


def test_variants_keep_slots_images_and_direct_text_edits():
    p = populated("profile", variant="left")
    p.apply({"type": "text-set", "target": "card/name", "text": "Ana Rivera"})
    source = p.layer("card/photo")["image_slot"]["source"]
    ident = p.layer("card")["id"]
    original = p.layer("card/photo")["x"]
    p.apply({"type": "container-variant", "target": "card", "variant": "centered"})
    assert p.layer("card")["id"] == ident
    assert p.layer("card/name")["text"] == "Ana Rivera"
    assert p.layer("card/photo")["image_slot"]["source"] == source
    assert p.layer("card/photo")["x"] != original
    assert measure(p)["passed"]
    p.apply({"type": "container-fill", "target": "card", "variables": {"name": "Sam"}})
    assert p.layer("card/name")["text"] == "Sam"


def test_adaptive_resize_reflows_without_stretching_text_and_is_atomic():
    p = populated("profile", variant="split")
    ids = [layer["id"] for layer in p.state["layers"]]
    original = p.layer("card/name")["size"]
    p.apply({"type": "resize", "target": "card", "width": 720, "height": 500})
    assert [layer["id"] for layer in p.state["layers"]] == ids
    assert p.layer("card/name")["size"] == original
    assert p.layer("card")["content_width"] == 720
    assert measure(p)["passed"]
    before = deepcopy(p.state)
    with pytest.raises(VixlError, match="bounds"):
        p.apply({"type": "resize", "target": "card", "width": 100})
    assert p.state == before


def test_image_slot_cover_focal_contain_mask_and_resolution(tmp_path):
    image = Image.new("RGBA", (400, 200), "red")
    image.paste("blue", (200, 0, 400, 200))
    p = Project(800, 600)
    p._workspace = tmp_path
    image.save(tmp_path / "portrait.png")
    p.apply(
        [
            {"type": "palette-apply", "name": "slate"},
            {"type": "container-place", "name": "card", "resource": "photo-caption", "seed": 2},
        ]
    )
    assert "unfilled_image" in {v["rule"] for v in measure(p)["violations"]}
    p.apply(
        {
            "type": "container-fill",
            "target": "card",
            "variables": {"photo": "portrait.png", "caption": "A portrait"},
        }
    )
    assert "image_resolution" in {v["rule"] for v in measure(p)["violations"]}
    asset = add_image(p, image)
    p.apply(
        {
            "type": "image-slot",
            "name": "right",
            "asset": asset,
            "width": 100,
            "height": 100,
            "focal": [1, 0.5],
            "mask_shape": "circle",
        }
    )
    crop = decode(p.assets[p.layer("right")["asset"]], p.limits)
    assert crop.getpixel((50, 50))[:3] == (0, 0, 255)
    assert crop.getpixel((0, 0))[3] == 0
    p.apply(
        {"type": "image-slot", "name": "fit", "asset": asset, "width": 100, "height": 100, "fit": "contain"}
    )
    crop = decode(p.assets[p.layer("fit")["asset"]], p.limits)
    assert crop.getpixel((50, 0))[3] == 0
    assert crop.getpixel((10, 50))[3] == 255


@pytest.mark.parametrize("name", [name for name, item in TEMPLATES.items() if item.get("category")])
def test_use_case_templates_declare_slots_sizes_checks_and_reproducible_choices(name):
    item = TEMPLATES[name]
    assert item["slots"] and item["sizes"] and item["combinations"]
    p = create_template(name, seed=19)
    assert p.state["template"]["seed"] == 19
    assert p.state["suites"]["container-layout"]
    if name == "social-carousel":
        assert len(p.state["pages"]) == 3
    else:
        assert len(p.state["containers"]) == len(item["grid"]["resources"])


def test_template_columns_follow_canvas_and_palette_look_variants():
    p = Project(1800, 1200)
    p.apply(
        {
            "type": "template-apply",
            "name": "marketing-features",
            "columns": 2,
            "palette": "coffee",
            "look": "paper",
            "seed": 42,
        }
    )
    boxes = [layer for layer in p.state["layers"] if "container" in layer]
    assert len(boxes) == 6
    assert boxes[2]["x"] == boxes[0]["x"] and boxes[2]["y"] > boxes[0]["y"]
    assert boxes[0]["width"] > 480
    assert p.state["template"]["rolled"]["palette"] == "coffee"
    assert p.layer("background")["looks"]["paper"]


def test_comic_reading_order_spans_captions_and_embedded_art():
    p = Project(1000, 900)
    asset = add_image(p, Image.new("RGBA", (1000, 1000), "#89aabb"))
    p.apply(
        {
            "type": "comic-layout",
            "reading_order": "rtl",
            "panels": [
                {"image": asset, "caption": "The beginning"},
                {"image": asset, "caption": "An unexpected turn"},
                {"image": asset, "caption": "The ending", "span": 2},
            ],
        }
    )
    records = p.state["comic"]["panels"]
    assert records[0]["bounds"][0] > records[1]["bounds"][0]
    assert records[2]["bounds"][2] > records[0]["bounds"][2]
    assert p.layer("comic/panel-3/caption")["text"] == "The ending"
    assert render(p).size == (1000, 900)


def test_slot_sources_and_hug_geometry_survive_save_reload(tmp_path):
    p = populated("profile", variant="split")
    source = p.layer("card/photo")["image_slot"]["source"]
    p.save(tmp_path / "profile.vixl")
    loaded = Project.load(tmp_path / "profile.vixl")
    assert source in loaded.assets
    loaded.apply({"type": "resize", "target": "card", "width": 650, "height": 450})
    assert measure(loaded)["passed"]


def test_services_cannot_read_slot_paths_even_inside_workspace(tmp_path):
    from vixl.interfaces import service_check

    p = Project(800, 600)
    p._workspace = tmp_path
    Image.new("RGB", (500, 500)).save(tmp_path / "secret.png")
    with pytest.raises(VixlError, match="embedded"):
        p.apply(
            {
                "type": "container-place",
                "name": "card",
                "resource": "profile",
                "variables": {"photo": "secret.png"},
            },
            check=service_check,
        )
    assert not p.state["layers"]


def test_template_declared_sizes_are_resolvable():
    from vixl.sizes import resolve

    for item in TEMPLATES.values():
        for name in item.get("sizes", []):
            assert resolve(name)["width"] > 0


def test_comic_dialogue_is_editable_and_missing_art_is_reported():
    p = Project(1200, 800)
    p.apply(
        {
            "type": "comic-layout",
            "panels": [{"caption": "The start", "dialogue": [{"text": "Hello!", "style": "thought"}]}, {}],
        }
    )
    assert p.layer("comic/panel-1/dialogue-1")["bubble"]["style"] == "thought"
    assert p.layer("comic/panel-1/dialogue-1/text")["text"] == "Hello!"
    assert not p.check(checks=["blanks"])["passed"]
    assert render(p).size == (1200, 800)


def test_hug_release_freezes_geometry_and_proxy_scales_padding():
    from vixl.proxy import scaled_project

    p = Project(600, 300)
    p.apply(
        [
            {"type": "text", "name": "text", "text": "A clear button", "size": 40},
            {
                "type": "stack",
                "name": "button",
                "targets": ["text"],
                "size": "hug",
                "padding": {"left": 30, "right": 20},
                "background": "#336699",
                "radius": 20,
            },
        ]
    )
    preview = scaled_project(p, 0.5)
    assert preview.layer("button")["stack"]["padding"] == {"left": 15, "right": 10}
    before = render(p).tobytes()
    p.apply({"type": "stack", "target": "button", "remove": True})
    assert render(p).tobytes() == before


def test_fixed_workspace_seed_repeats_container_variant(tmp_path):
    import json

    (tmp_path / ".vixl").mkdir()
    (tmp_path / ".vixl" / "variety.json").write_text(json.dumps({"variety": "fixed", "seed": 19}))
    variants = []
    for _ in range(2):
        p = Project(800, 600, workspace=tmp_path)
        p.apply(
            [
                {"type": "palette-apply", "name": "slate"},
                {"type": "container-place", "name": "card", "resource": "feature-icon"},
            ]
        )
        variants.append(p.layer("card")["container"]["variant"])
        assert p.layer("card")["container"]["seed"] == 19
    assert variants[0] == variants[1]


def test_custom_vertical_container_wraps_text_without_stretch(tmp_path):
    from vixl.resources import register

    item = {
        "width": 480,
        "height": 320,
        "min_width": 240,
        "min_height": 200,
        "rules": {"layout": "vertical", "padding": 20, "gap": 10},
        "operations": [
            {
                "type": "text",
                "name": "copy",
                "text": "Readable text wraps onto several lines in a narrow card.",
                "size": 24,
                "fit_text": "wrap",
            }
        ],
    }
    register("containers", "wrapped", item, workspace=tmp_path)
    p = Project(600, 400, workspace=tmp_path)
    p.apply({"type": "container-place", "name": "card", "resource": "wrapped", "width": 280, "height": 300})
    text = p.layer("card/copy")
    assert text["text_layout"]["width"] == 240
    assert text["height"] > text["size"]
    assert measure(p)["passed"]


def test_carousel_finish_is_applied_to_every_generated_page():
    from vixl.pages import page_content

    p = create_template("social-carousel", seed=3, palette="slate", look="paper")
    selected = p.state["page"]
    for page in p.state["pages"]:
        layers = page_content(p, page)["layers"]
        background = next(layer for layer in layers if layer["name"] == "background")
        assert "paper" in background["looks"]
    assert selected == p.state["pages"][-1]["id"]
