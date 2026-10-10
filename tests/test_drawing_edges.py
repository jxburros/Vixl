"""Drawing pipeline: the canvas edge can close a fill region, and clean keeps the paper's extent (#218)."""

import numpy as np
import pytest
from PIL import Image, ImageDraw, ImageFilter

from vixl import Project
from vixl import drawing
from vixl.errors import VixlError


def landscape(path, size=(500, 360)):
    """A ground line from edge to edge, a hill on it and a sun in the sky, drawn small in the middle of
    plenty of paper."""
    w, h = size
    ink = Image.new("L", size, 0)
    d = ImageDraw.Draw(ink)
    d.line([(0, 250), (w, 252)], fill=255, width=4)
    d.arc([140, 170, 360, 330], 180, 360, fill=255, width=4)
    d.ellipse([380, 60, 440, 120], outline=255, width=4)
    ink = ink.filter(ImageFilter.GaussianBlur(0.6))
    alpha = np.asarray(ink, float)[..., None] / 255 * 0.85
    rgb = 228 * (1 - alpha) + np.array([50, 50, 60]) * alpha
    Image.fromarray(np.clip(rgb, 0, 255).astype(np.uint8)).save(path)
    return path


def imported(tmp_path, **settings):
    p = Project(500, 360, "#ffffff")
    p.apply({"type": "drawing", "action": "import", "path": str(landscape(tmp_path / "scene.png")), "name": "art",
             "x": 0, "y": 0, "width": 500, "height": 360, **({"settings": settings} if settings else {})})
    return p


def test_clean_keeps_the_papers_extent_by_default():
    image = Image.new("RGB", (400, 300), (230, 230, 230))
    ImageDraw.Draw(image).ellipse([150, 100, 250, 200], outline=(40, 40, 40), width=4)
    kept = drawing.clean(image, {"sheet": False})
    assert kept["crop"] == [0, 0, 400, 300] and kept["mask"].shape == (300, 400)
    cropped = drawing.clean(image, {"sheet": False, "crop": True})
    assert cropped["crop"][2] < 200 and cropped["crop"][3] < 200


def test_edge_closes_fills_sky_and_ground_bounded_by_the_canvas_edge(tmp_path):
    p = imported(tmp_path)
    report = drawing.report(p, "art")
    assert report["edge_regions"], "sky and ground touch the drawing's edge"
    with pytest.raises(VixlError) as error:
        p.apply({"type": "drawing", "action": "fill", "target": "art", "points": [[20, 20, "#9cd3f0"]]})
    assert "edge_closes" in str(error.value)
    p.apply({"type": "drawing", "action": "fill", "target": "art", "settings": {"edge_closes": True},
             "points": [[20, 20, "#9cd3f0"], [20, 330, "#5a8f3c"]]})
    image = p.render().convert("RGB")
    assert image.getpixel((20, 20)) == (156, 211, 240)
    assert image.getpixel((480, 20)) == (156, 211, 240), "the sky reaches the far corner"
    assert image.getpixel((20, 330)) == (90, 143, 60) and image.getpixel((480, 340)) == (90, 143, 60)
    assert image.getpixel((250, 230)) != (156, 211, 240), "the hill stays out of the sky"
    assert image.getpixel((410, 90)) != (156, 211, 240), "so does the sun"
