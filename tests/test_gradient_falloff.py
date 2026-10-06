"""Radial gradient falloff, PPTX radial parity, the soft-halo look and the gradient-edge finding."""

import io
import math
import re
import zipfile

import numpy as np
import pytest

from vixl import Project
from vixl.design import gradient_stops
from vixl.errors import VixlError
from vixl.svg import export_svg


def halo(falloff="gaussian", size=201):
    p = Project(size, size)
    p.apply({"type": "gradient", "name": "halo", "width": size, "height": size, "direction": "radial",
             "start": "#ffffff", "end": "#ffffff00", "falloff": falloff})
    return p


def test_linear_falloff_keeps_the_stops():
    layer = {"start": "red", "end": "blue"}
    assert gradient_stops(layer, {}) == [{"offset": 0, "color": "red"}, {"offset": 1, "color": "blue"}]


@pytest.mark.parametrize("falloff, curve", [
    ("gaussian", lambda t: 1 - (1 - math.exp(-4.5 * t * t)) / (1 - math.exp(-4.5))),
    ("quadratic", lambda t: 1 - t * t),
    ("ease", lambda t: (1 - t) ** 2),
    ("smooth", lambda t: 1 - t * t * (3 - 2 * t)),
])
def test_raster_follows_the_falloff_curve(falloff, curve):
    alpha = np.asarray(halo(falloff).render().getchannel("A"), dtype=float) / 255
    row = alpha[100]
    for t in (0.25, 0.5, 0.75):
        assert abs(row[100 + round(100 * t)] - curve(t)) < 0.03, (falloff, t)
    # The ramp ends at the inscribed ellipse: edge midpoints and corners are transparent.
    assert row[0] < 0.01 and row[-1] < 0.01 and alpha[0, 0] == 0


def test_falloff_is_the_same_in_svg_pdf_and_pptx():
    p = halo()
    expected = gradient_stops(p.layer("halo"), p.state)
    assert len(expected) > 20
    svg = export_svg(p).decode()
    assert len(re.findall(r"<stop ", svg)) == len(expected)
    xml = zipfile.ZipFile(io.BytesIO(p.export(format="PPTX"))).read("ppt/slides/slide1.xml").decode()
    positions = [int(v) for v in re.findall(r'<a:gs pos="(\d+)"', xml)]
    assert len(positions) == len(expected) + 1


def test_pptx_radial_gradient_ends_at_the_inscribed_ellipse():
    p = Project(200, 100)
    p.apply({"type": "gradient", "name": "g", "direction": "radial", "start": "red", "end": "blue"})
    xml = zipfile.ZipFile(io.BytesIO(p.export(format="PPTX"))).read("ppt/slides/slide1.xml").decode()
    stops = re.findall(r'<a:gs pos="(\d+)"><a:srgbClr val="(\w+)"', xml)
    # PowerPoint's circle path reaches 100% at the corners: the last real stop sits at 1/sqrt(2).
    assert stops == [("0", "FF0000"), ("70711", "0000FF"), ("100000", "0000FF")]
    assert 'path="circle"' in xml


def test_opaque_falloff_gradient_stays_vector_in_pdf():
    pypdf = pytest.importorskip("pypdf")
    p = Project(100, 100)
    p.apply({"type": "gradient", "name": "g", "direction": "radial", "start": "white", "end": "black", "falloff": "smooth"})
    page = pypdf.PdfReader(io.BytesIO(p.export(format="PDF"))).pages[0]
    assert "/Shading" in page["/Resources"]


def test_unknown_falloff_is_rejected():
    with pytest.raises(VixlError) as error:
        halo("bouncy")
    assert "falloff" in str(error.value.as_dict())


def test_soft_halo_look_fades_a_gradient_and_comes_off_again():
    p = Project(300, 300)
    p.apply([{"type": "gradient", "name": "g", "width": 200, "height": 120, "x": 50, "y": 90, "start": "gold", "end": "white"},
             {"type": "look", "target": "g", "look": "soft-halo"}])
    layer = p.layer("g")
    assert layer["direction"] == "radial" and layer["falloff"] == "gaussian"
    alpha = np.asarray(p.render().getchannel("A"))
    assert alpha[150, 150] > 150 and alpha[90, 150] < 4 and alpha[150, 50] < 4
    assert not [i for i in p.check()["issues"] if i.get("code") == "gradient-edge"]
    p.apply({"type": "look", "target": "g", "look": "soft-halo", "remove": True})
    layer = p.layer("g")
    assert layer["direction"] == "vertical" and "falloff" not in layer and "stops" not in layer
    p.apply({"type": "shape", "name": "sun", "shape": "ellipse", "width": 40, "height": 40, "fill": "gold"})
    p.apply({"type": "look", "target": "sun", "look": "soft-halo"})
    assert "outer-glow" in p.layer("sun")["styles"]


def test_gradient_edge_finding_reports_a_visible_box():
    p = Project(400, 400)
    p.apply([{"type": "solid", "name": "bg", "color": "navy"},
             {"type": "gradient", "name": "band", "width": 200, "height": 200, "x": 100, "y": 100,
              "start": "gold", "end": "#ffd70000", "direction": "horizontal"},
             {"type": "gradient", "name": "glow", "width": 200, "height": 200, "x": 100, "y": 100,
              "start": "gold", "end": "#ffd70000", "direction": "radial"},
             {"type": "gradient", "name": "scrim", "width": 400, "height": 200, "x": 0, "y": 200,
              "start": "#00000000", "end": "black"}])
    found = [i for i in p.check()["issues"] if i.get("code") == "gradient-edge"]
    assert [i["layers"] for i in found] == [["band"]]
    assert found[0]["sides"] == ["top", "bottom", "left"] and found[0]["action"] == "review"
