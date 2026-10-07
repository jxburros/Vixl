import json

import pytest

from vixl import Project, VixlError
from vixl.layouts import LAYOUTS, assign_roles
from vixl.sizes import SIZES, catalog, resolve


def test_named_print_sizes_resolve_with_dpi_bleed_and_orientation():
    letter = resolve("letter")
    assert (letter["width"], letter["height"], letter["dpi"]) == (2550, 3300, 300)
    bled = resolve("letter", bleed=True)
    assert bled["bleed"] == 37.5 and bled["width"] == 2550 + 75 and bled["trim"] == [2550, 3300]
    # Trim + 2 x bleed is the physical size, not one pixel more from rounding each side (#306).
    assert (resolve("business-card", bleed=True)["width"], resolve("business-card", bleed=True)["height"]) == (1125, 675)
    a4 = resolve("a4", bleed=True, orientation="landscape", dpi=72)
    assert (a4["width"], a4["height"], a4["bleed"]) == (859, 612, 8.5)
    landscape = resolve("a4", orientation="landscape", dpi=150)
    assert landscape["width"] > landscape["height"] and landscape["dpi"] == 150
    assert resolve("instagram-portrait")["width"] == 1080 and "dpi" not in resolve("instagram-portrait")
    assert resolve("thumbnail")["size"] == "youtube-thumbnail"  # alias
    with pytest.raises(VixlError, match="did you mean"):
        resolve("leter")
    with pytest.raises(VixlError, match="dpi applies to print"):
        resolve("favicon", dpi=300)


def test_every_catalog_size_fits_default_limits():
    from vixl.model import Limits

    for name in SIZES:
        info = resolve(name)
        Limits().size(info["width"], info["height"])
    assert {item["category"] for item in catalog()["sizes"]} >= {"print", "social", "icons", "logos", "stationery"}
    assert catalog("icons")["sizes"] and all(item["category"] == "icons" for item in catalog("icons")["sizes"])


def test_sized_documents_record_print_metadata_and_guides(tmp_path):
    p = Project.sized("business-card", bleed=True)
    c = p.state["canvas"]
    assert c["size"] == "business-card" and c["dpi"] == 300 and c["bleed"] == 37.5 and c["safe"] > 0
    assert {"trim-left", "safe-right"} <= set(p.state["guides"])
    assert len(p.nodes) == 1  # metadata belongs to the first revision
    p.apply({"type": "text", "name": "name", "text": "Name"})
    p.apply({"type": "constrain", "target": "name", "constraints": {"left": "guide:safe-left.left"}})
    assert p.inspect("name")["resolved_bounds"][0] == pytest.approx(p.state["guides"]["safe-left"]["position"], abs=0.5)
    p.save(tmp_path / "card.vixl")
    loaded = Project.load(tmp_path / "card.vixl")
    assert loaded.state["canvas"]["physical"]["unit"] == "in"
    # A custom resize drops trim/safe metadata and generated guides; dpi stays.
    loaded.apply({"type": "canvas", "width": 500, "height": 500})
    assert "size" not in loaded.state["canvas"] and loaded.state["canvas"]["dpi"] == 300
    assert not any(g.get("generated") for g in loaded.state.get("guides", {}).values())
    # The guide a layer is anchored to survives as an ordinary guide.
    assert set(loaded.state["guides"]) == {"safe-left"}


def test_canvas_operation_and_artboards_accept_named_sizes():
    p = Project(10, 10)
    p.apply({"type": "canvas", "size": "postcard", "orientation": "portrait", "bleed": True})
    c = p.state["canvas"]
    assert c["height"] > c["width"] and c["bleed"] > 0
    p.apply({"type": "canvas", "preset": "story"})  # old preset names still work
    assert (p.state["canvas"]["width"], p.state["canvas"]["height"]) == (1080, 1920)
    p.apply({"type": "artboard", "name": "square", "preset": "instagram-square"})
    assert p.state["artboards"]["square"]["width"] == 1080
    with pytest.raises(VixlError, match="named size"):
        p.apply({"type": "canvas", "width": 100, "bleed": True})


def test_cli_new_with_named_size(tmp_path, monkeypatch, capsys):
    from vixl.cli import main

    monkeypatch.chdir(tmp_path)
    assert main(["new", "a5", "--landscape", "--bleed", "--dpi", "150", "-o", "flyer.vixl"]) == 0
    canvas = json.loads(capsys.readouterr().out)["canvas"]
    assert canvas["size"] == "a5" and canvas["width"] > canvas["height"] and canvas["dpi"] == 150
    assert main(["sizes", "show", "letter", "--bleed"]) == 0
    assert json.loads(capsys.readouterr().out)["bleed"] == 37.5
    assert main(["canvas", "size", "instagram-story"]) == 0
    capsys.readouterr()
    assert main(["layout", "show", "golden-section"]) == 0
    assert "golden ratio proportion" in json.loads(capsys.readouterr().out)["principles"]
    assert main(["layout", "apply", "story-vertical", "--set", "title=Hello", "--seed", "2"]) == 0
    capsys.readouterr()
    assert main(["layers"]) == 0
    assert "headline" in capsys.readouterr().out


@pytest.mark.parametrize("name", sorted(LAYOUTS))
def test_every_layout_builds_editable_layers_on_varied_canvases(name):
    for size in ("instagram-square", "youtube-thumbnail", "business-card", "leaderboard", "favicon"):
        p = Project.sized(size)
        p.apply({"type": "layout-apply", "name": name, "seed": 3}, detail="compact")
        record = p.state["layout"]
        assert record["name"] == name and record["layers"]
        assert {"background", "ink", "accent", "accent-text", "muted", "on-accent"} <= set(p.state["swatches"])
        assert "body" in p.state["character_styles"]
        assert p.render().size == (p.state["canvas"]["width"], p.state["canvas"]["height"])


def test_layouts_vary_by_seed_and_content_but_repeat_for_the_same_inputs():
    def apply(seed=None, title="A headline"):
        p = Project.sized("instagram-portrait")
        op = {"type": "layout-apply", "name": "hero-statement", "title": title}
        if seed is not None:
            op["seed"] = seed
        p.apply(op, detail="compact")
        return {k: v for k, v in p.state["layout"].items() if k != "layers"}, p.state["swatches"]

    assert apply(5) == apply(5)  # Same inputs, same design (layer IDs aside).
    records = {json.dumps(apply(seed)[0], sort_keys=True) for seed in range(8)}
    assert len(records) >= 5
    assert apply(title="One")[0]["seed"] != apply(title="Two")[0]["seed"]


def test_layout_respects_content_options_and_contrast():
    p = Project.sized("instagram-square")
    p.apply(
        {
            "type": "layout-apply",
            "name": "centered-axis",
            "title": "Opening night",
            "subtitle": "Doors at seven",
            "cta": "Get tickets",
            "palette": "ocean",
            "mode": "dark",
            "type_scale": "golden",
            "density": "airy",
            "seed": 1,
        },
        detail="compact",
    )
    record = p.state["layout"]
    assert record["palette"] == "ocean" and record["mode"] == "dark" and record["type_scale"] == "golden"
    assert record["contrast"] >= 7
    names = {layer["name"] for layer in p.state["layers"]}
    assert {"headline", "subtitle", "cta", "cta-button"} <= names
    report = p.check(checks=["contrast", "overlap", "bounds"])
    assert report["errors"] == 0, report["issues"]


def test_layout_name_conflicts_prefix_and_replace():
    p = Project.sized("instagram-square")
    p.apply({"type": "layout-apply", "name": "big-number", "seed": 1})
    with pytest.raises(VixlError, match="prefix or replace"):
        p.apply({"type": "layout-apply", "name": "big-number", "seed": 1})
    p.apply({"type": "layout-apply", "name": "quote-card", "seed": 1, "prefix": "b-"})
    assert any(layer["name"].startswith("b-") for layer in p.state["layers"])
    count = len(p.state["layers"])
    p.apply({"type": "layout-apply", "name": "quote-card", "seed": 2, "prefix": "b-", "replace": True})
    assert len(p.state["layers"]) <= count
    with pytest.raises(VixlError, match="did you mean"):
        p.apply({"type": "layout-apply", "name": "hero-statment"})


def test_layout_image_slot_accepts_an_asset_and_is_replaceable():
    from PIL import Image

    from vixl.assets import add_image

    p = Project.sized("instagram-square")
    asset = add_image(p, Image.new("RGBA", (40, 30), "red"))
    p.apply({"type": "layout-apply", "name": "split-screen", "image": asset, "seed": 2})
    frame = p.layer("image")
    assert frame["type"] == "frame" and frame["asset"] == asset
    p.apply({"type": "layout-apply", "name": "photo-caption", "prefix": "p-", "seed": 2})
    placeholder = p.layer("p-image")
    p.apply({"type": "replace-contents", "target": "p-image", "asset": asset})
    assert p.layer("p-image")["asset"] == asset and placeholder["type"] == "frame"


def test_role_assignment_meets_contrast_targets_for_every_pool_palette():
    import random

    from vixl.colors import contrast_ratio, parse
    from vixl.layouts import PALETTE_POOL

    for palette in PALETTE_POOL:
        for mode in ("light", "dark"):
            roles = assign_roles({"palette": palette, "mode": mode}, random.Random(1))
            bg, surface = parse(roles["background"])[:3], parse(roles["surface"])[:3]
            assert contrast_ratio(parse(roles["ink"])[:3], bg) >= 7, (palette, mode)
            for role in ("muted", "accent-text"):
                assert min(contrast_ratio(parse(roles[role])[:3], bg), contrast_ratio(parse(roles[role])[:3], surface)) >= 4.5
            assert contrast_ratio(parse(roles["accent"])[:3], bg) >= 3
            assert contrast_ratio(parse(roles["on-accent"])[:3], parse(roles["accent"])[:3]) >= 3


def test_type_scale_operation_defines_modular_styles():
    p = Project(100, 100)
    p.apply({"type": "type-scale", "base": 16, "ratio": "perfect-fourth", "prefix": "t-"})
    styles = p.state["character_styles"]
    assert styles["t-body"]["size"] == 16 and styles["t-lead"]["size"] == 21 and styles["t-caption"]["size"] == 12
    with pytest.raises(VixlError):
        p.apply({"type": "type-scale", "ratio": 5})
