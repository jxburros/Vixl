"""Reduced previews must not show seams between layers that meet at an edge in the full render."""

import numpy as np
import pytest
from PIL import Image, ImageDraw

from vixl import Project
from vixl.proxy import render_preview, scaled_project

TILE = 349   # 1047 px canvas previewed at 349 px: every tile is 116.33 preview pixels
COUNT = 3


def tile(path):
    """A tile that repeats seamlessly: dark discs wrapped over every edge, on a light ground."""
    image = Image.new("RGB", (TILE, TILE), (247, 241, 229))
    draw = ImageDraw.Draw(image)
    for x, y, r in ((0, 0, 70), (TILE, 0, 70), (0, TILE, 70), (TILE, TILE, 70), (TILE // 2, TILE // 2, 55), (100, 260, 30)):
        draw.ellipse([x - r, y - r, x + r, y + r], fill=(20, 38, 59))
    image.save(path)


def seams(project, size=TILE):
    """How far the preview strays from the downscaled full render along each tile boundary,
    against how far it strays elsewhere (both in levels of 0-255)."""
    export = project.render().convert("RGB")
    preview = render_preview(project, size, size).convert("RGB")
    reference = export.resize(preview.size, Image.Resampling.LANCZOS)
    diff = np.abs(np.asarray(preview, float) - np.asarray(reference, float)).max(axis=2)
    step = preview.width / COUNT
    edges = [round(step * i) for i in range(1, COUNT)]
    near = np.zeros(preview.width, bool)
    for edge in edges:
        near[edge - 1:edge + 2] = True
    return (max(diff.mean(axis=0)[near].max(), diff.mean(axis=1)[near].max()),
            max(np.median(diff.mean(axis=0)[~near]), np.median(diff.mean(axis=1)[~near])))


@pytest.fixture
def source(tmp_path):
    path = tmp_path / "tile.png"
    tile(path)
    return str(path)


def test_repeated_tiles_have_no_seams_in_a_reduced_preview(source):
    p = Project(TILE * COUNT, TILE * COUNT, "#f7f1e5")
    p.apply({"type": "add", "name": "row", "path": source, "x": 0, "y": 0})
    p.apply({"type": "repeat", "target": "row", "count": COUNT, "dx": TILE})
    for i in range(1, COUNT):
        p.apply([{"type": "duplicate", "target": "row", "name": f"row{i}"},
                 {"type": "move", "target": f"row{i}", "x": 0, "y": i * TILE}])
    export = np.asarray(p.render().convert("RGB"))
    assert (export[:TILE, :TILE] == export[TILE:2 * TILE, TILE:2 * TILE]).all(), "the export is the tile, repeated"
    worst, ordinary = seams(p)
    assert worst < ordinary + 1.0, f"a preview seam: {worst:.2f} along the tile edges against {ordinary:.2f} elsewhere"


def test_tiles_placed_one_by_one_have_no_seams_in_a_reduced_preview(source):
    p = Project(TILE * COUNT, TILE * COUNT, "#f7f1e5")
    for i in range(COUNT):
        for j in range(COUNT):
            p.apply({"type": "add", "name": f"tile-{i}{j}", "path": source, "x": i * TILE, "y": j * TILE})
    worst, ordinary = seams(p)
    assert worst < ordinary + 1.0, f"a preview seam: {worst:.2f} along the tile edges against {ordinary:.2f} elsewhere"


def test_bands_that_meet_leave_no_background_between_them_at_any_scale():
    for size, scale in ((1000, 0.3413), (777, 0.33), (1024, 0.5 - 1e-6), (1031, 0.29)):
        p = Project(size, size, "#ffffff")
        edges = [0, 111, 333, 500, 723, size]
        for i, (top, bottom) in enumerate(zip(edges, edges[1:])):
            p.apply({"type": "solid", "name": f"band{i}", "x": 0, "y": top, "width": size, "height": bottom - top, "color": "#000000"})
        image = np.asarray(scaled_project(p, scale).render().convert("L"))
        assert image.max() == 0, f"background shows between layers that meet, at scale {scale}"
