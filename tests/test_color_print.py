import io
import json
import sys
from pathlib import Path

from PIL import Image
import pytest

from vixl import Project, VixlError
from vixl.colors import (
    contrast_ratio,
    describe,
    harmony,
    parse,
    scale,
    search_names,
    simulate_vision,
    srgb_to_cmyk,
    to_rgba8,
)
from vixl.render import color

sys.path.insert(0, str(Path(__file__).parent))
from icc_helper import cmyk_profile  # noqa: E402


@pytest.mark.parametrize(
    "value,expected",
    [
        ("red", (255, 0, 0, 255)),
        ("#abc", (170, 187, 204, 255)),
        ("rgb(10 20 30 / 0.5)", (10, 20, 30, 128)),
        ("cmyk(0, 100, 100, 0)", (255, 0, 0, 255)),
        ("device-cmyk(0% 100% 100% 0%)", (255, 0, 0, 255)),
        ("cmyk(0 0 0 100%)", (0, 0, 0, 255)),
        ("oklch(0.6279 0.2577 29.23)", (255, 0, 0, 255)),
        ("oklab(1 0 0)", (255, 255, 255, 255)),
        ("lab(54.29 80.8 69.89)", (255, 0, 0, 255)),  # CSS lab() is D50
        ("hwb(0 0% 0%)", (255, 0, 0, 255)),
        ("gray(50%)", (128, 128, 128, 255)),
        ("color(srgb 0 0 1)", (0, 0, 255, 255)),
        ("alpha(red, 0.5)", (255, 0, 0, 128)),
        ("mix(black, white, 0%)", (0, 0, 0, 255)),
        ("transparent", (0, 0, 0, 0)),
        ("dusty rose", (192, 115, 122, 255)),
        ("dusty-rose", (192, 115, 122, 255)),
        ("xkcd:green", (21, 176, 26, 255)),
    ],
)
def test_color_language_parses_css_print_and_names(value, expected):
    result = to_rgba8(value)
    assert all(abs(a - b) <= 1 for a, b in zip(result, expected)), result


def test_css_names_keep_priority_over_survey_names_and_pillow_fast_path():
    assert color("green") == (0, 128, 0, 255)  # CSS green, not xkcd green
    assert color("hsl(120, 100%, 25%)") == (0, 128, 0, 255)


def test_color_functions_mix_lighten_and_gamut_map():
    assert to_rgba8("color-mix(in srgb, red 50%, blue)")[:3] == (128, 0, 128)
    light, dark = parse("lighten(#336699, 20%)"), parse("darken(#336699, 20%)")
    base = parse("#336699")
    assert sum(light[:3]) > sum(base[:3]) > sum(dark[:3])
    # Display-P3 red is outside sRGB; it maps in by chroma reduction rather than clipping hue.
    p3 = to_rgba8("color(display-p3 1 0 0)")
    assert p3[0] == 255 and p3[1] < 80 and p3[2] < 80
    assert to_rgba8("readable(#111)")[:3] == (255, 255, 255)
    assert to_rgba8("complement(#ff0000)") != to_rgba8("#ff0000")
    assert 2000 < sum(to_rgba8("kelvin(6500)")[:3]) * 10 < 7700


def test_bad_colors_explain_themselves():
    with pytest.raises(VixlError, match="did you mean"):
        color("dustyros")
    with pytest.raises(VixlError, match="needs an amount"):
        color("lighten(red)")
    with pytest.raises(VixlError, match="Unclosed"):
        color("oklch(0.5 0.1")


def test_describe_harmony_scale_and_names():
    info = describe("#2563eb")
    assert info["hex"] == "#2563eb" and len(info["cmyk"]) == 4 and info["readable_text"] == "white"
    assert info["names"] and info["css"]["oklch"].startswith("oklch(")
    assert len(harmony("tomato", "triadic")) == 3
    assert len(harmony("tomato", "tints", 4)) == 4
    ramp = scale("#2563eb")
    assert list(ramp) == ["50", "100", "200", "300", "400", "500", "600", "700", "800", "900", "950"]
    lightness = [sum(parse(v)[:3]) for v in ramp.values()]
    assert lightness == sorted(lightness, reverse=True)
    assert "#2563eb" in ramp.values()
    assert any(item["name"] == "sage" for item in search_names("sage"))


def test_gcr_cmyk_and_ink_limit():
    assert srgb_to_cmyk((0, 0, 0)) == (0.0, 0.0, 0.0, 1.0)
    c, m, y, k = srgb_to_cmyk((0.2, 0.1, 0.1), black=0.5, ink_limit=2.5)
    assert c + m + y + k <= 2.5 + 1e-9


def test_swatch_expressions_and_palette_generation():
    p = Project(8, 8)
    p.apply(
        [
            {"type": "swatch", "name": "brand", "color": "oklch(0.55 0.2 260)"},
            {"type": "swatch", "name": "brand-soft", "color": "mix(@brand, white, 70%)"},
            {"type": "palette-generate", "name": "brand", "color": "@brand", "scheme": "scale"},
            {"type": "palette-generate", "name": "pair", "color": "#2563eb", "scheme": "complementary"},
            {"type": "solid", "color": "lighten(@brand-soft, 5%)"},
        ]
    )
    assert "brand-500" in p.state["swatches"] and "pair-2" in p.state["swatches"]
    assert p.render().getpixel((1, 1))[3] == 255
    with pytest.raises(VixlError):
        p.apply({"type": "swatch", "name": "loop", "color": "mix(@loop, red, 1%)"})


def _document():
    p = Project.sized("postcard", "white", bleed=True)
    p.apply(
        [
            {"type": "solid", "name": "panel", "color": "cmyk(100%, 0%, 0%, 0%)", "width": 600, "height": 400, "x": 0, "y": 0},
            {"type": "text", "name": "headline", "text": "Hello", "size": 120, "color": "black", "x": 700, "y": 300},
        ]
    )
    return p


def test_cmyk_export_pdf_tiff_jpeg_and_dpi():
    p = _document()
    tiff = Image.open(io.BytesIO(p.export(format="TIFF", color_space="cmyk", ink_limit=300)))
    assert tiff.mode == "CMYK" and round(tiff.info["dpi"][0]) == 300
    c, m, y, k = tiff.getpixel((10, 10))
    assert c > 240 and m < 10 and y < 10
    jpeg = Image.open(io.BytesIO(p.export(format="JPEG", color_space="cmyk")))
    assert jpeg.mode == "CMYK"
    pdf = p.export(format="PDF", color_space="cmyk")  # vector: colours are DeviceCMYK operators (k/K), not an image
    assert pdf.startswith(b"%PDF") and b"/DeviceCMYK" not in pdf
    assert b"/DeviceCMYK" in p.export(format="PDF", color_space="cmyk", pdf_content="raster")
    assert p.export(format="PDF").startswith(b"%PDF")
    with pytest.raises(VixlError, match="CMYK export supports"):
        p.export(format="PNG", color_space="cmyk")
    with pytest.raises(VixlError, match="SVG export is RGB"):
        p.export(format="SVG", color_space="cmyk")


def test_icc_profile_separation_embeds_profile_and_soft_proof():
    p = _document()
    profile = cmyk_profile()
    data = p.export(format="TIFF", color_space="cmyk", icc_profile=profile, intent="perceptual")
    image = Image.open(io.BytesIO(data))
    assert image.mode == "CMYK" and image.info.get("icc_profile")
    proof = Image.open(io.BytesIO(p.export(format="PNG", proof=True, icc_profile=profile)))
    assert proof.mode == "RGBA"
    with pytest.raises(VixlError, match="not CMYK|readable ICC"):
        p.export(format="TIFF", color_space="cmyk", icc_profile=b"not a profile")


def test_vision_simulation_and_ico_export():
    image = Image.new("RGBA", (2, 1))
    image.putpixel((0, 0), (255, 0, 0, 255))
    image.putpixel((1, 0), (0, 160, 0, 255))
    seen = simulate_vision(image, "deuteranopia")
    a, b = (tuple(v / 255 for v in seen.getpixel((i, 0))[:3]) for i in (0, 1))
    assert contrast_ratio(a, b) < 1.6
    icon = Project.sized("favicon")
    icon.apply({"type": "shape", "shape": "ellipse", "fill": "tomato", "width": 400, "height": 400, "x": 56, "y": 56})
    ico = Image.open(io.BytesIO(icon.export(format="ICO", icon_sizes=[16, 32, 48])))
    assert ico.format == "ICO" and (48, 48) in ico.ico.sizes()
    with pytest.raises(VixlError, match="square"):
        Project(64, 32).export(format="ICO")


def test_print_and_color_vision_checks():
    p = Project.sized("letter", "white", bleed=True)
    trim = p.state["canvas"]["bleed"]
    p.apply(
        [
            {"type": "solid", "name": "short-background", "color": "#fde68a", "width": 2550, "height": 3300, "x": trim, "y": trim},
            {"type": "text", "name": "fine-print", "text": "tiny", "size": 12, "color": "black", "x": 200, "y": 200},
            {"type": "text", "name": "edge", "text": "Edge", "size": 80, "color": "black", "x": 2, "y": 1500},
            {"type": "solid", "name": "dark", "color": "black", "width": 800, "height": 300, "x": 400, "y": 2000},
            {"type": "text", "name": "red-on-black", "text": "Alert", "size": 18, "color": "#ff2020", "x": 450, "y": 2100},
        ]
    )
    report = p.check(checks=["print", "color_vision"])
    messages = " ".join(issue["message"] for issue in report["issues"])
    assert "fine-print" in messages and "pt" in messages
    assert "stops at the trim" in messages
    assert "live area" in messages
    assert any(issue["check"] == "color_vision" and issue["layers"] == ["red-on-black"] for issue in report["issues"])
    plain = p.check()
    assert all(issue["check"] not in ("print", "color_vision") for issue in plain["issues"])


def test_cli_color_and_export_flags(tmp_path, monkeypatch, capsys):
    from vixl.cli import main

    monkeypatch.chdir(tmp_path)
    assert main(["color", "convert", "cmyk(0,100,100,0)", "--to", "hex"]) == 0
    assert json.loads(capsys.readouterr().out)["hex"] == "#ff0000"
    assert main(["color", "contrast", "white", "#2563eb"]) == 0
    assert json.loads(capsys.readouterr().out)["aa_normal"] is True
    assert main(["new", "business-card", "--bleed", "-o", "card.vixl"]) == 0
    capsys.readouterr()
    (tmp_path / "test.icc").write_bytes(cmyk_profile())
    assert main(["export", "card.pdf", "--cmyk", "--icc", "test.icc"]) == 0
    assert (tmp_path / "card.pdf").read_bytes().startswith(b"%PDF")
    assert main(["export", "proof.png", "--proof", "--simulate", "protanopia"]) == 0
    assert main(["export-icons", "--out", "icons"]) == 0
    capsys.readouterr()
    assert (tmp_path / "icons" / "favicon.ico").exists() and (tmp_path / "icons" / "apple-touch-icon.png").exists()
    assert main(["export-icons", "--out", "icons"]) == 1  # never overwrites


def test_css_names_survive_pillows_parsed_color_cache():
    # Pillow rewrites ImageColor.colormap entries as tuples once parsed; CSS must still beat xkcd names.
    from PIL import ImageColor

    from vixl import colors

    ImageColor.getrgb("red")
    for cached in (colors._css_names, colors.named_colors, colors._canonical_names, colors.parse):
        cached.cache_clear()
    assert to_rgba8("red") == (255, 0, 0, 255)
