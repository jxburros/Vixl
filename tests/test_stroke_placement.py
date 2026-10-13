"""PNG, SVG, PDF and PowerPoint put a shape's stroke in the same place: inside a closed shape, flush with its
outline, and where an explicit stroke_align says (geometry.stroke_inset)."""

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


def build(kind, width=100, **fields):
    project = Project(200, 180, background="#ffffff")
    project.apply([{"type": "shape", "name": "s", **BOX, "width": width, **SHAPES[kind], "fill": "transparent",
                    "stroke": "#ff0000", "stroke_width": 10, **fields}])
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


CLOSED = ["rectangle", "rounded-rectangle", "ellipse", "polygon", "star"]


@pytest.mark.parametrize("kind", CLOSED)
def test_closed_shapes_stroke_inside_and_flush_with_their_outline(kind):
    """A closed shape's stroke runs from its outline inward: fill and stroke in one colour cover exactly
    the shape's unstroked silhouette (outer edge on the outline, rounded corners keep their radius)."""
    def shape(stroked):
        project = Project(200, 180, background="#ffffff")
        project.apply([{"type": "shape", "name": "s", **BOX, "width": 100, **SHAPES[kind], "fill": "#ff0000",
                        "stroke": "#ff0000" if stroked else "transparent", "stroke_width": 10}])
        return renders(project)

    plain, stroked = shape(False), shape(True)
    for name in plain:
        assert np.abs(box(stroked[name]) - box(plain[name])).max() <= 1, (name, box(stroked[name]), box(plain[name]))
        # No ink outside the silhouette (bar rasterizer differences on its edge); along the edge the
        # stroke's anti-aliasing adds to the fill's.
        assert stroked[name][plain[name] == 0].max() <= 0.15, name
        assert np.abs(stroked[name] - plain[name]).max() <= 0.5, name


def test_box_shape_strokes_start_at_the_box_edge():
    for kind in ("rectangle", "rounded-rectangle", "ellipse"):
        for name, image in renders(build(kind)).items():
            assert box(image).tolist() == [50, 50, 149, 129], (kind, name)
            # A 10 px stroke covers 0-10 px in from each side (crossings at pixel index edge - 0.5).
            for profile, expected in ((image[90, :], [49.5, 59.5, 139.5, 149.5]),
                                      (image[:, 100], [49.5, 59.5, 119.5, 129.5])):
                assert np.abs(edges(profile) - expected).max() <= 1, (kind, name, edges(profile))


def test_rounded_corners_keep_the_outer_radius_and_shrink_the_inner_one():
    # radius 20, stroke 10: the outer edge has radius 20 and the inner one 10, both centred at (70, 70).
    for name, image in renders(build("rounded-rectangle")).items():
        diagonal = np.array([image[i, i] for i in range(45, 80)])
        found = edges(diagonal) + 45 + 0.5
        expected = [70 - 20 / np.sqrt(2), 70 - 10 / np.sqrt(2)]
        assert np.abs(found - expected).max() <= 1, (name, found, expected)


def test_a_stroke_wider_than_the_shape_fills_it():
    project = Project(120, 120, background="#ffffff")
    project.apply([{"type": "shape", "name": "s", "shape": "ellipse", "x": 30, "y": 30, "width": 60, "height": 40,
                    "fill": "transparent", "stroke": "#ff0000", "stroke_width": 30}])
    for name, image in renders(project).items():
        assert box(image).tolist() == [30, 30, 89, 69], name
        assert image[50, 60] > 0.99, name


@pytest.mark.parametrize("align, edge", [("inside", 50), ("center", 45), ("outside", 40)])
@pytest.mark.parametrize("kind", ["rectangle", "ellipse"])
def test_explicit_stroke_align_means_the_same_in_every_renderer(kind, align, edge):
    images = renders(build(kind, stroke_align=align))
    for name, image in images.items():
        # The ink's outer edge, and its 10 px width, across the middle row.
        assert np.abs(edges(image[90, :])[:2] - [edge - 0.5, edge + 9.5]).max() <= 1, (name, edges(image[90, :]))
    if align == "inside":
        default = renders(build(kind))
        for name, image in images.items():
            assert np.abs(image - default[name]).max() <= 0.3, name


def test_inside_stroke_of_a_thin_ellipse_stays_in_its_box():
    # Tighter curves than the stroke width at the ends used to throw spikes past the box.
    project = Project(240, 100, background="#ffffff")
    project.apply([{"type": "shape", "name": "s", "shape": "ellipse", "x": 20, "y": 30, "width": 190, "height": 40,
                    "fill": "transparent", "stroke": "#ff0000", "stroke_width": 12}])
    for name, image in renders(project).items():
        assert box(image).tolist() == [20, 30, 209, 69], name


def test_a_rectangle_with_a_radius_keeps_square_corners():
    project = build("rectangle", radius=20)
    for name, image in renders(project).items():
        assert image[50, 50] > 0.9, name


def test_trimmed_rectangle_stroke_runs_from_the_box_edge():
    project = build("rectangle", trim_end=50)
    for name, image in {"png": ink(project.render()), "svg": renders(project)["svg"]}.items():
        # The top edge is drawn (the trim starts at the top-left corner, clockwise): 0-10 px in.
        assert np.abs(edges(image[:, 100]) - [49.5, 59.5]).max() <= 1, (name, edges(image[:, 100]))


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


def pptx_frame(tmp_path, project, name):
    project.export(tmp_path / f"{name}.pptx")
    package = zipfile.ZipFile(tmp_path / f"{name}.pptx")
    emu = int(re.search(r'sldSz cx="(\d+)"', package.read("ppt/presentation.xml").decode())[1]) / 200
    shape = package.read("ppt/slides/slide1.xml").decode().split("<p:sp>")[-1]
    found = re.search(r'<a:off x="(\d+)" y="(\d+)"/><a:ext cx="(\d+)" cy="(\d+)"', shape).groups()
    assert round(int(re.search(r'<a:ln w="(\d+)"', shape)[1]) / emu, 3) == 10
    return tuple(round(int(v) / emu, 3) for v in found), shape


def test_pptx_outlines_follow_the_same_inset(tmp_path):
    # PowerPoint centres a stroke on the outline, so the outline is drawn where the stroke's centre runs.
    expected = {"rectangle": (55, 55, 90, 70), "rounded-rectangle": (55, 55, 90, 70), "ellipse": (55, 55, 90, 70),
                "polygon": (55, 55, 90, 70), "line": (55, 55, 90, 70), "open-path": (50, 50, 100, 80)}
    for kind, frame in expected.items():
        assert pptx_frame(tmp_path, build(kind), kind)[0] == frame, kind
    # Radius 20 less half the stroke, over the frame's shorter side.
    assert 'fmla="val 21429"' in pptx_frame(tmp_path, build("rounded-rectangle"), "radius")[1]
    for align, frame in (("center", (50, 50, 100, 80)), ("outside", (45, 45, 110, 90))):
        assert pptx_frame(tmp_path, build("rectangle", stroke_align=align), align)[0] == frame, align
