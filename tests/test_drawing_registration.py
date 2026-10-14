"""Drawing fills register to their lines: no halo between a fill and its line, no bulge through a bridged
break, and a ground line that stops short of the paper's sides still divides sky from ground (#218, T11)."""

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from vixl import Project, drawing

SKY, GROUND, ROOF, LEAF = (217, 236, 242), (168, 213, 200), (226, 114, 91), (90, 143, 90)


def sketch(path, size=(500, 360)):
    """A pen sketch: a ground line that stops 40 px short of both sides, a house standing on it whose
    left roof line stops 9 px short of the wall, a round tree, and a sun with a ray pointing at the
    top edge."""
    w, h = size
    ink = Image.new("L", size, 0)
    d = ImageDraw.Draw(ink)
    d.line([(40, 260), (460, 262)], fill=255, width=5)
    d.rectangle([150, 170, 260, 261], outline=255, width=5)
    d.line([(157, 162), (205, 110)], fill=255, width=5)
    d.line([(205, 110), (268, 170)], fill=255, width=5)
    d.line([(158, 170), (260, 170)], fill=255, width=5)
    d.ellipse([320, 150, 400, 230], outline=255, width=5)
    d.ellipse([400, 40, 440, 80], outline=255, width=5)
    d.line([(420, 34), (420, 14)], fill=255, width=4)
    ink = ink.filter(ImageFilter.GaussianBlur(0.6))
    alpha = np.asarray(ink, float)[..., None] / 255 * 0.9
    rgb = 232 * (1 - alpha) + np.array([40, 40, 50]) * alpha
    Image.fromarray(np.clip(rgb, 0, 255).astype(np.uint8)).save(path)
    return path


def drawn(tmp_path):
    p = Project(500, 360, "#ffffff")
    p.apply([{"type": "drawing", "action": "import", "path": str(sketch(tmp_path / "sketch.png")), "name": "art",
              "x": 0, "y": 0, "width": 500, "height": 360, "settings": {"sheet": False, "deskew": False}},
             {"type": "drawing", "action": "vectorize", "target": "art"}])
    return p


def colour_mask(image, rgb, tolerance=6):
    return (np.abs(np.asarray(image, int)[..., :3] - rgb).max(axis=-1) <= tolerance)


def test_fills_meet_their_lines_without_a_halo(tmp_path):
    p = drawn(tmp_path)
    # A hand-added smooth stroke, as an agent closes a shape: its fill must follow the curve it draws.
    p.apply({"type": "drawing", "action": "stroke", "target": "art", "name": "art/arc",
             "points": [[320, 262], [328, 300], [422, 300], [430, 262]], "settings": {"width": 5}})
    p.apply({"type": "drawing", "action": "fill", "target": "art",
             "points": [[360, 190, "#5a8f5a"], [370, 280, "#e2725b"]]})
    image = p.render().convert("RGB")
    a = np.asarray(image, int)
    dark = a.max(axis=-1) < 140
    near_line = drawing.dilate(dark, 2) & ~dark
    pale = a.min(axis=-1) > 225
    # A halo is paper showing between a fill and its line: pale pixels that touch both.
    for rgb in (LEAF, ROOF):
        fill = colour_mask(image, rgb)
        assert fill.sum() > 1000
        assert not (near_line & pale & drawing.dilate(fill, 2)).any(), rgb
    # And the fill never shows past its line's centre: the far side of the tree's outline is unfilled paper.
    assert not colour_mask(image, LEAF)[150:230, 401:410].any()


def test_a_bridged_break_ends_the_fill_on_the_line_between_its_ends(tmp_path):
    p = drawn(tmp_path)
    p.apply({"type": "drawing", "action": "fill", "target": "art", "settings": {"edge_closes": True, "edge_reach": 0},
             "points": [[205, 150, "#e2725b"], [20, 20, "#d9ecf2"]]})
    image = p.render().convert("RGB")
    roof, sky = colour_mask(image, ROOF), colour_mask(image, SKY)
    assert roof[140:165, 190:230].all()
    # The roof's left line stops short of the wall corner. The roof fills its corner right up to the line's end
    # (the sky used to reach in there and the roof stopped in a rounded end), and the two fills meet across the
    # break with nothing pale between them.
    for x, y in ((158, 164), (159, 165), (159, 166)):
        assert roof[y, x], (x, y)
    ys, xs = np.mgrid[0:360, 0:500]
    under_roof = (ys > 162 - (xs - 157) * 52 / 48 + 4) & (ys < 167) & (xs > 152) & (xs < 175)
    assert not sky[under_roof].any()
    assert not roof[:, :147].any() and not roof[172:, :].any()
    pale = np.asarray(image, int).min(axis=-1) > 225
    assert not pale[150:169, 140:170].any()


def test_edge_closes_splits_sky_from_ground_when_the_ground_line_stops_short(tmp_path):
    p = drawn(tmp_path)
    report = drawing.report(p, "art")
    assert len(report["edge_regions"]) >= 2, "the ground line's ends are carried to the edges"
    p.apply({"type": "drawing", "action": "fill", "target": "art", "settings": {"edge_closes": True},
             "points": [[20, 20, "#d9ecf2"], [20, 330, "#a8d5c8"]]})
    image = p.render().convert("RGB")
    sky, ground = colour_mask(image, SKY), colour_mask(image, GROUND)
    for x in (5, 20, 480, 495):
        assert sky[30, x] and sky[250, x] and ground[275, x] and ground[350, x], x
    # The extension is not drawn: beyond the line's ends the two fills meet with no ink between them.
    assert not (np.asarray(image, int).max(axis=-1) < 140)[:, :30].any()
    assert sky[:, 470:].sum() > 0 and ground[:, 470:].sum() > 0
    # The sun's ray points at the top edge, but it does not cut the sky in two.
    assert sky[5, 380:460].all()
    # edge_reach: 0 keeps sky and ground one region.
    q = drawn(tmp_path)
    q.apply({"type": "drawing", "action": "fill", "target": "art", "settings": {"edge_closes": True, "edge_reach": 0},
             "points": [[20, 20, "#d9ecf2"]]})
    assert colour_mask(q.render().convert("RGB"), SKY)[350, 20]
