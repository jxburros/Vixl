"""QR codes and barcodes as native vector shapes (#168)."""

import io
import zipfile

import numpy as np
import pypdfium2
import pytest
import segno

from vixl import Project
from vixl.checks import check_design
from vixl.codes import code128_modules, code128_values, ean13_modules, outline
from vixl.errors import VixlError
from vixl.render import resolved_layers
from vixl.targets import mode

MODULE = 6


def qr_project(data="https://vixl.dev/r/42", **extra):
    p = Project(240, 240, "#ffffff")
    p.apply({"type": "qr", "name": "q", "data": data, "module": MODULE, "x": 0, "y": 0, **extra})
    return p


def sampled(image, size, quiet, module=MODULE, origin=(0, 0)):
    """The dark/light matrix read back from module centres of a rendered code."""
    pixels = np.asarray(image.convert("L"), dtype=int)
    return [[pixels[origin[1] + round((quiet + r + 0.5) * module), origin[0] + round((quiet + c + 0.5) * module)] < 128
             for c in range(size)] for r in range(size)]


def segno_matrix(data, error="m"):
    return [[bool(cell) for cell in row] for row in segno.make(data, error=error, micro=False, boost_error=False).matrix]


def test_qr_is_one_vector_path_that_matches_segno_in_raster_and_pdf():
    p = qr_project()
    code = p.layer("q code")
    assert code["type"] == "shape" and code["shape"] == "path" and code["code"]["kind"] == "qr"
    expected = segno_matrix("https://vixl.dev/r/42")
    size = len(expected)
    assert code["path_view"] == [size + 8, size + 8] and code["width"] == (size + 8) * MODULE
    assert sampled(p.render(), size, 4) == expected
    from vixl.pdf_export import export_pdf

    data = export_pdf(p, None, content="vector")
    assert b"/Image" not in data
    document = pypdfium2.PdfDocument(data)
    page = document[0].render(scale=1).to_pil()
    assert sampled(page, size, 4) == expected
    document.close()


def test_svg_and_pptx_draw_the_code_as_paths_not_images():
    from vixl.pptx_export import export_pptx
    from vixl.svg import export_svg

    p = qr_project(error="H", quiet=2, color="#102030", background="#fafafa")
    svg = export_svg(p)
    svg = svg.decode() if isinstance(svg, bytes) else svg
    assert "<image" not in svg and svg.count("<path") >= 1 and "rgb(16,32,48)" in svg
    data = export_pptx(p)
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        slide = archive.read("ppt/slides/slide1.xml").decode()
    assert "<a:custGeom>" in slide and "<p:pic>" not in slide


def test_outline_holes_wind_the_other_way_so_both_fill_rules_agree():
    ring = [[True, True, True], [True, False, True], [True, True, True]]
    path = outline(ring)
    assert path.count("M") == 2  # the outer square and the hole
    diagonal = [[True, False], [False, True]]
    assert outline(diagonal).count("M") == 2  # touching corners stay two squares
    from vixl.geometry import path_polygons

    def area(points):
        return sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(points, points[1:] + points[:1])) / 2

    outer, hole = (area(poly) for poly in path_polygons(path))
    assert outer * hole < 0 and abs(outer) == 9 and abs(hole) == 1


def test_qr_options_error_quiet_colours_and_size():
    p = qr_project(data="HELLO", error="H", quiet=1, color="navy", background="#ffff00", size=150)
    code, group = p.layer("q code"), p.layer("q")
    assert group["type"] == "group" and (code["width"], code["height"]) == (150, 150)
    expected = segno_matrix("HELLO", "h")
    assert code["path_view"][0] == len(expected) + 2
    image = p.render()
    assert image.getpixel((2, 2))[:3] == (255, 255, 0) and image.getpixel((200, 200))[:3] == (255, 255, 255)
    bare = qr_project(background="none")
    assert [layer["name"] for layer in bare.state["layers"]] == ["q"]
    with pytest.raises(VixlError):
        qr_project(error="X")


def test_data_with_variables_is_encoded_per_render_for_merges():
    p = Project(300, 300, "#ffffff")
    p.apply([{"type": "variable", "name": "id", "value": "1"},
             {"type": "qr", "name": "q", "data": "https://vixl.dev/t/${id}", "module": 4}])
    first = sampled(p.render(), len(segno_matrix("https://vixl.dev/t/1")), 4, 4)
    assert first == segno_matrix("https://vixl.dev/t/1")
    layer = next(item for item in resolved_layers(p, {"id": "777"}) if item["name"] == "q code")
    assert layer["path"] != p.layer("q code")["path"]
    assert p.render(variables={"id": "777"}) != p.render()
    p.apply({"type": "variable", "name": "sku", "value": "400638133393"})
    p.apply({"type": "barcode", "name": "ean", "data": "${sku}", "symbology": "ean13", "y": 200, "background": "none"})
    with pytest.raises(VixlError, match="check digit"):
        p.render(variables={"sku": "4006381333932"})


def test_ean13_matches_the_published_pattern_and_validates_the_check_digit():
    # 4006381333931, the standard worked example: first digit 4 sets the parity LGLLGG.
    bits, digits = ean13_modules("400638133393")
    assert digits == "4006381333931" and len(bits) == 95
    assert bits == ("101" "0001101" "0100111" "0101111" "0111101" "0001001" "0110011" "01010"
                    "1000010" "1000010" "1000010" "1110100" "1000010" "1100110" "101")
    assert ean13_modules("4006381333931")[1] == "4006381333931"
    with pytest.raises(VixlError) as caught:
        ean13_modules("4006381333932")
    assert caught.value.details["suggestions"] == ["4006381333931"]
    with pytest.raises(VixlError):
        ean13_modules("12345")


def test_code128_values_checksum_and_bars():
    # "PJJ123C" in set B: 103-based checksum from the specification's worked example.
    values = code128_values("PJJ123C")
    assert values[0] == 104 and values[-1] == 106
    assert values[-2] == (104 + sum(i * v for i, v in enumerate(values[1:-2], 1))) % 103
    assert code128_values("123456")[:4] == [105, 12, 34, 56]  # all digits: set C pairs
    mixed = code128_values("AB12345678")
    assert mixed[:3] == [104, 33, 34] and 99 in mixed  # switches to set C for the digit run
    bits = code128_modules("Wikipedia")
    assert bits.startswith("11010010000") and bits.endswith("1100011101011")  # start B and stop
    assert len(bits) == 11 * (len("Wikipedia") + 2) + 13
    with pytest.raises(VixlError):
        code128_values("tab\there")


def test_barcode_layer_renders_bars_with_quiet_zones():
    p = Project(400, 120, "#ffffff")
    p.apply({"type": "barcode", "name": "b", "data": "400638133393", "symbology": "ean13", "module": 2, "height": 80})
    code = p.layer("b code")
    assert code["path_view"] == [11 + 95 + 7, 100] and code["width"] == 226 and code["height"] == 80
    pixels = np.asarray(p.render().convert("L"))[40]
    bits, _ = ean13_modules("400638133393")
    read = "".join("1" if pixels[(11 + i) * 2 + 1] < 128 else "0" for i in range(95))
    assert read == bits
    assert pixels[:22].min() > 200  # the left quiet zone is clear


def test_codes_check_flags_small_modules_low_contrast_and_ink_in_the_quiet_zone():
    p = Project(600, 600, "#ffffff")
    p.apply([{"type": "canvas", "dpi": 300}, {"type": "qr", "name": "tiny", "data": "x", "module": 2, "x": 20, "y": 20},
             {"type": "qr", "name": "pale", "data": "x", "module": 10, "color": "#bbbbbb", "x": 300, "y": 20},
             {"type": "qr", "name": "crowded", "data": "x", "module": 10, "x": 20, "y": 300, "background": "none"},
             {"type": "shape", "shape": "rectangle", "name": "blob", "x": 30, "y": 310, "width": 20, "height": 200,
              "fill": "red"}])
    issues = [item for item in check_design(p, checks=["codes"])["issues"] if item["check"] == "codes"]
    found = {(item["layers"][0], item["severity"], next(k for k in ("module_mm", "contrast", "quiet_zone_ink")
                                                        if k in item)) for item in issues}
    assert ("tiny code", "error", "module_mm") in found
    assert ("pale code", "error", "contrast") in found
    assert ("crowded", "error", "quiet_zone_ink") in found
    clean = qr_project()
    assert not [item for item in check_design(clean, checks=["codes"])["issues"] if item["check"] == "codes"]
    assert "codes" in check_design(clean)["checked"]["checks"]


def test_edit_in_place_and_classification():
    p = qr_project()
    before = p.layer("q code")["id"]
    p.apply({"type": "qr", "target": "q", "data": "changed", "color": "#333333", "background": "#eeeeee"})
    code = p.layer("q code")
    assert code["id"] == before and code["code"]["data"] == "changed" and code["fill"] == "#333333"
    assert p.layer("q background")["fill"] == "#eeeeee"
    assert code["width"] == code["path_view"][0] * MODULE  # module size kept
    with pytest.raises(VixlError, match="edit it with qr"):
        p.apply({"type": "barcode", "target": "q", "data": "1"})
    with pytest.raises(VixlError, match="move"):
        p.apply({"type": "qr", "target": "q", "x": 5})
    assert mode("qr") == mode("barcode") == "each"
    p.apply({"type": "qr", "name": "centred", "data": "c", "module": 2, "x": "center", "y": "center",
             "background": "none"})
    layer = p.layer("centred")
    assert abs(layer["x"] + layer["width"] / 2 - 120) <= 1


def test_text_size_and_data_limits():
    with pytest.raises(VixlError, match="needs data"):
        Project(100, 100).apply({"type": "qr"})
    with pytest.raises(VixlError, match="too much detail"):
        qr_project(data="x" * 1500)


def test_render_is_crisp_at_whole_pixel_modules():
    image = qr_project().render().convert("L")
    values = set(np.unique(np.asarray(image)))
    assert values <= {0, 255}, sorted(values)[:10]
