"""PNG, SVG, PDF and PowerPoint put a shape's stroke in the same place (geometry.stroke_inset)."""

import io
import re
import zipfile

import numpy as np
import pytest
from PIL import Image

from vixl import Project

BOX = {"x": 50, "y": 50, "height": 80}
SHAPES = {
    "rectangle": {"shape": "rectangle"},
    "rounded-rectangle": {"shape": "rounded-rectangle", "radius": 20},
    "ellipse": {"shape": "ellipse"},
    "polygon": {"shape": "polygon", "sides": 6},
    "star": {"shape": "star"},
    "line": {"shape": "line"},
    "open-path": {"shape": "path", "path": "M 0 0 L 100 80 L 100 0"},
    "closed-path": {"shape": "path", "path": "M 0 0 L 100 0 L 100 80 L 0 80 Z"},
}


def build(kind, width=100):
    project = Project(200, 180, background="#ffffff")
    project.apply([{"type": "shape", "name": "s", **BOX, "width": width, **SHAPES[kind], "fill": "transparent",
                    "stroke": "#ff0000", "stroke_width": 10}])
    return project


def ink(image):
    """Stroke coverage (0-1) from the green channel of red ink on white."""
    return 1 - np.asarray(image.convert("RGB"))[:, :, 1].astype(float) / 255


def renders(project):
    import resvg_py

    pdfium = pytest.importorskip("pypdfium2")
    svg = project.export(format="SVG").decode()
    pdf = pdfium.PdfDocument(project.export(format="PDF"))[0].render(scale=1).to_pil()
    return {
        "png": ink(project.render()),
        "svg": ink(Image.open(io.BytesIO(resvg_py.svg_to_bytes(svg_string=svg)))),
        "pdf": ink(pdf),
    }


def box(coverage):
    ys, xs = np.nonzero(coverage > 0.5)
    return np.array([xs.min(), ys.min(), xs.max(), ys.max()])


def edges(profile):
    """Sub-pixel positions where a coverage profile crosses one half."""
    found = []
    for i in range(len(profile) - 1):
        a, b = profile[i] - 0.5, profile[i + 1] - 0.5
        if a * b < 0:
            found.append(i + a / (a - b))
    return np.array(found)


@pytest.mark.parametrize("width", [100, 100.5])
@pytest.mark.parametrize("kind", list(SHAPES))
def test_every_export_strokes_where_png_does(kind, width):
    images = renders(build(kind, width))
    png = images.pop("png")
    for name, image in images.items():
        assert np.abs(box(image) - box(png)).max() <= 1, (name, box(image), box(png))
        # The stroke's edges along the middle row and column land within a pixel of the PNG's.
        for take in (lambda a: a[90, :], lambda a: a[:, 100]):
            ours, theirs = edges(take(png)), edges(take(image))
            assert len(ours) == len(theirs), (name, ours, theirs)
            assert np.abs(ours - theirs).max() <= 1, (name, ours, theirs)
        assert abs(image.sum() - png.sum()) <= 0.05 * png.sum(), name


def test_rectangle_and_ellipse_strokes_sit_inside_their_box():
    for kind in ("rectangle", "ellipse"):
        coverage = renders(build(kind))
        for name, image in coverage.items():
            # The whole shape is inset by half the stroke, and the stroke drawn inward from there.
            assert box(image).tolist() == [55, 55, 144, 124], (kind, name)


@pytest.mark.parametrize("kind", ["open-path", "closed-path"])
def test_png_draws_a_paths_whole_stroke_past_its_box(kind):
    coverage = ink(build(kind).render())
    x0, y0, x1, y1 = box(coverage)
    # The stroke is centred on the path, so half of it lies outside the 50..150 x 50..130 box.
    assert x0 <= 47 and y0 <= 47 and x1 >= 153 and y1 >= 133
    if kind == "closed-path":
        assert coverage[90, 45:55].min() > 0.9 and coverage[90, 145:155].min() > 0.9


def test_turned_stroked_path_keeps_its_whole_stroke():
    project = Project(300, 300, background="#ffffff")
    project.apply([{"type": "shape", "name": "s", "shape": "path", "path": "M 0 0 L 100 0 L 100 80 L 0 80 Z",
                    "x": 100, "y": 110, "width": 100, "height": 80, "fill": "transparent", "stroke": "#ff0000",
                    "stroke_width": 10, "rotation": 90}])
    assert box(ink(project.render())).tolist() == [105, 95, 194, 204]


def test_pptx_outlines_follow_the_same_inset(tmp_path):
    expected = {"rectangle": (60, 60, 80, 60), "ellipse": (60, 60, 80, 60), "polygon": (55, 55, 90, 70),
                "line": (55, 55, 90, 70), "open-path": (50, 50, 100, 80)}
    for kind, frame in expected.items():
        project = build(kind)
        project.export(tmp_path / f"{kind}.pptx")
        package = zipfile.ZipFile(tmp_path / f"{kind}.pptx")
        emu = int(re.search(r'sldSz cx="(\d+)"', package.read("ppt/presentation.xml").decode())[1]) / 200
        shape = package.read("ppt/slides/slide1.xml").decode().split("<p:sp>")[-1]
        found = re.search(r'<a:off x="(\d+)" y="(\d+)"/><a:ext cx="(\d+)" cy="(\d+)"', shape).groups()
        assert tuple(round(int(v) / emu, 3) for v in found) == frame, kind
        assert round(int(re.search(r'<a:ln w="(\d+)"', shape)[1]) / emu, 3) == 10
