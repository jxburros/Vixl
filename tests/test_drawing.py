import math
from copy import deepcopy

import numpy as np
import pytest
from PIL import Image, ImageDraw, ImageFilter

from vixl import Project
from vixl import drawing
from vixl.errors import VixlError
from vixl.trace import simplify


def photo(path=None, tilt=0.0, size=(600, 450), seed=3, desk=None, cloud=False):
    """A photographed sketch: a wobbly rounded rectangle, a hand-drawn circle, a near-horizontal
    line with a gap, a zigzag, dust, uneven lighting and paper grain. ``cloud`` draws a bumpy
    loop of seven rounded lobes in place of the circle. With a ``desk`` colour the whole page is
    photographed at ``tilt`` degrees, so the darker desk shows in the corners (otherwise only the
    drawing is tilted on the page)."""
    rng = np.random.default_rng(seed)
    w, h = size
    ink = Image.new("L", size, 0)
    d = ImageDraw.Draw(ink)

    def line(points, width=4, jitter=0.8):
        pts = [(x + rng.normal(0, jitter), y + rng.normal(0, jitter)) for x, y in points]
        d.line(pts, fill=255, width=width, joint="curve")

    def along(corners, steps=30):
        out = []
        for (x0, y0), (x1, y1) in zip(corners, corners[1:]):
            out += [(x0 + (x1 - x0) * t / steps, y0 + (y1 - y0) * t / steps) for t in range(steps)]
        return out + [corners[-1]]

    r = 12  # rounded corners
    box = [(80 + r, 80), (300 - r, 82), (300, 80 + r), (301, 230 - r), (300 - r, 230), (80 + r, 229), (80, 230 - r),
           (81, 80 + r), (80 + r, 80)]
    line(along(box, 12))
    if cloud:
        line([(460 + (52 + 18 * abs(math.sin(3.5 * a))) * math.cos(a), 150 + (52 + 18 * abs(math.sin(3.5 * a))) * math.sin(a))
              for a in np.linspace(0, 2 * math.pi, 140)], 4, 0.6)
    else:
        line([(460 + 70 * math.cos(a), 150 + 70 * math.sin(a)) for a in np.linspace(0, 2 * math.pi, 80)], 4, 0.6)
    line(along([(60, 330), (260, 333)], 40), 4)
    line(along([(290, 334), (540, 331)], 40), 4)
    line(along([(80, 400), (130, 370), (180, 400), (230, 370), (280, 400)], 8), 3)
    for _ in range(25):
        x, y = rng.uniform(0, w), rng.uniform(0, h)
        d.ellipse([x - 1, y - 1, x + 1, y + 1], fill=200)
    ink = ink.filter(ImageFilter.GaussianBlur(0.7))
    if tilt and desk is None:
        ink = ink.rotate(tilt, resample=Image.Resampling.BICUBIC)
    yy, xx = np.mgrid[0:h, 0:w]
    paper = 230 - 60 * (xx / w) * (yy / h) + rng.normal(0, 3, (h, w))
    alpha = np.asarray(ink, float)[..., None] / 255 * 0.85
    rgb = paper[..., None] * (1 - alpha) + np.array([55, 55, 70]) * alpha
    image = Image.fromarray(np.clip(rgb, 0, 255).astype(np.uint8))
    if desk is not None:
        image = image.rotate(tilt, resample=Image.Resampling.BICUBIC, fillcolor=desk)
    if path:
        image.save(path, quality=90)
    return image


@pytest.fixture
def sketch(tmp_path):
    path = tmp_path / "sketch.jpg"
    photo(path)
    return path


def built(sketch, straighten=True):
    p = Project(800, 600, "#ffffff")
    p.apply({"type": "drawing", "action": "import", "path": str(sketch), "name": "art", "x": 0, "y": 0})
    p.apply({"type": "drawing", "action": "vectorize", "target": "art"})
    if straighten:
        p.apply({"type": "drawing", "action": "straighten", "target": "art"})
    return p


def test_label_counts_components_with_diagonal_contact():
    mask = np.zeros((10, 10), bool)
    mask[1, 1] = mask[2, 2] = mask[3, 3] = True  # one diagonal component
    mask[6:8, 6:9] = True
    labels, count = drawing.label(mask)
    assert count == 2 and labels[1, 1] == labels[3, 3] != labels[6, 6]
    assert drawing.label(np.zeros((4, 4), bool))[1] == 0


def test_thin_and_trace_give_one_stroke_per_line():
    mask = np.zeros((80, 120), bool)
    mask[38:43, 10:110] = True
    strokes = drawing.strokes_from_mask(mask)
    assert len(strokes) == 1 and not strokes[0]["closed"] and 4 <= strokes[0]["width"] <= 6
    ring = Image.new("L", (100, 100))
    ImageDraw.Draw(ring).rectangle([20, 20, 80, 80], outline=255, width=4)
    loops = drawing.strokes_from_mask(np.asarray(ring) > 0)
    assert len(loops) == 1 and loops[0]["closed"]


def test_clean_flattens_paper_removes_dust_and_corrects_tilt():
    result = drawing.clean(photo(tilt=3.0))
    assert 2.0 <= abs(result["angle"]) <= 4.0
    alpha = np.asarray(result["ink"].getchannel("A"))
    labels, count = drawing.label(result["mask"])
    assert count <= 8, "dust specks are removed; each drawn line stays"
    assert (alpha > 0).mean() < 0.1, "the paper and its lighting become transparent"
    assert result["crop"][2] < 600 and result["crop"][3] < 450, "cropped to the drawing"
    original = drawing.clean(photo(), {"ink": "original", "deskew": False})
    rgb = np.asarray(original["ink"])[..., :3][original["mask"]]
    assert abs(float(rgb.mean()) - 60) < 40, "original ink colour is kept"


def test_the_desk_around_a_tilted_page_is_not_ink(tmp_path):
    image = photo(tilt=2.0, desk=(96, 84, 72))
    result = drawing.clean(image)
    assert result["sheet"] and 1.5 <= abs(result["angle"]) <= 2.5, "the page is found and its tilt corrected"
    assert not drawing.clean(photo())["sheet"], "paper filling the frame shows no edge, however uneven the light"

    def rim(settings):
        mask = drawing.clean(image, {"crop": False, **settings})["mask"].copy()
        mask[12:-12, 12:-12] = False
        return mask

    assert not rim({}).any(), "nothing along the page's edge or on the desk is ink"
    assert rim({"sheet": False}).any(), "sheet: false keeps the desk"
    path = tmp_path / "tilted.jpg"
    image.save(path, quality=90)
    p = built(path, straighten=False)
    group = p.layer("art")
    records = [r for layer in p.state["layers"] for r in layer.get("drawing_strokes", [])]
    assert 4 <= len(records) <= 8
    for record in records:
        points = np.asarray(record["points"])
        assert record["width"] < 8 and points.min() > 12, "no stroke traces the page's edge"
        assert points[:, 0].max() < group["content_width"] - 12 and points[:, 1].max() < group["content_height"] - 12


def test_import_keeps_the_original_and_draws_clean_ink(sketch):
    p = Project(800, 600, "#ffffff")
    p.apply({"type": "drawing", "action": "import", "path": str(sketch), "name": "art"})
    names = [layer["name"] for layer in p.state["layers"]]
    assert names == ["art/original", "art/ink", "art"]
    assert not p.layer("art/original")["visible"]
    group = p.layer("art")
    assert group["drawing"]["source"] in p.assets and group["drawing"]["reference"] in p.assets
    image = np.asarray(p.render().convert("L"))
    assert image.min() < 80 and np.median(image) == 255
    report = drawing.report(p, "art")
    assert report["preserved"] == 1.0 and report["added"] == 0.0


def test_vectorize_traces_editable_strokes(sketch):
    p = built(sketch, straighten=False)
    strokes = [layer for layer in p.state["layers"] if "drawing_strokes" in layer]
    assert 4 <= len(strokes) <= 8
    assert not p.layer("art/ink")["visible"]
    assert all(layer["shape"] == "path" and layer["line_cap"] == "round" for layer in strokes)
    assert drawing.report(p, "art")["preserved"] > 0.97
    svg = p.export(format="SVG").decode()
    assert "<image" not in svg and svg.count("<path") >= len(strokes), "hidden photo and ink; strokes are vectors"


def test_straighten_lines_corners_and_circles(sketch):
    p = built(sketch, straighten=False)
    p.apply({"type": "drawing", "action": "straighten", "target": "art", "settings": {"angles": "axes"}})
    kinds = drawing.report(p, "art")["stroke_kinds"]
    assert kinds.get("circle") == 1 and kinds.get("line", 0) >= 2 and kinds.get("polyline", 0) >= 1
    records = [r for layer in p.state["layers"] for r in layer.get("drawing_strokes", [])]
    box = next(r for r in records if r.get("kind") == "polyline" and r["closed"])
    assert len(box["points"]) == 4, "rounded corners become four sharp corners"
    for a, b in zip(box["points"], box["points"][1:] + box["points"][:1]):
        angle = math.degrees(math.atan2(b[1] - a[1], b[0] - a[0])) % 90
        assert min(angle, 90 - angle) < 0.01, "sides snap to horizontal and vertical"
    lines = [r for r in records if r.get("kind") == "line"]
    assert all(abs(r["points"][0][1] - r["points"][1][1]) < 0.01 for r in lines[:2])
    zigzag = next(r for r in records if r.get("kind") == "polyline" and not r["closed"])
    assert len(zigzag["points"]) >= 5, "a zigzag keeps its alternating corners"
    assert drawing.report(p, "art")["preserved"] > 0.9


def test_straighten_options(sketch):
    p = built(sketch, straighten=False)
    before = deepcopy([layer.get("drawing_strokes") for layer in p.state["layers"]])
    p.apply({"type": "drawing", "action": "straighten", "target": "art",
             "settings": {"circles": False, "polylines": False, "angles": "none"}})
    kinds = drawing.report(p, "art")["stroke_kinds"]
    assert "circle" not in kinds and "polyline" not in kinds
    p.apply({"type": "drawing", "action": "straighten", "target": "art", "settings": {"close_gaps": 40}})
    joined = [r for layer in p.state["layers"] for r in layer.get("drawing_strokes", []) if r.get("kind") == "line"]
    assert joined
    with pytest.raises(VixlError):
        p.apply({"type": "drawing", "action": "straighten", "target": "art", "settings": {"angles": "guides"}})
    with pytest.raises(VixlError):
        p.apply({"type": "drawing", "action": "straighten", "target": "art", "settings": {"bogus": 1}})
    assert before != [layer.get("drawing_strokes") for layer in p.state["layers"]]


def test_straighten_keeps_the_lobes_of_a_cloud(tmp_path):
    path = tmp_path / "cloud.jpg"
    photo(path, cloud=True)
    p = built(path, straighten=False)
    x, y = p.layer("art")["drawing"]["crop"][:2]
    layers = [layer for layer in p.state["layers"] if "drawing_strokes" in layer]
    cloud = min(layers, key=lambda layer: np.hypot(*(np.mean(layer["drawing_strokes"][0]["points"], axis=0) - (460 - x, 150 - y))))
    drawn = deepcopy(cloud["drawing_strokes"])
    assert len(drawn) == 1 and drawn[0]["closed"]
    p.apply({"type": "drawing", "action": "straighten", "target": "art", "settings": {"close_gaps": 30}})
    assert p.layer(cloud["name"])["drawing_strokes"] == drawn, "the rounded lobes stay as drawn: no straight segments, no circle"
    kinds = drawing.report(p, "art")["stroke_kinds"]
    assert kinds.get("line", 0) >= 2 and kinds.get("polyline", 0) >= 2, "the lines, box and zigzag are still straightened"


def test_straighten_keeps_the_curve_of_a_mixed_stroke_and_the_corners_of_a_neat_box():
    def traced(draw):
        mask = Image.new("L", (400, 400))
        draw(ImageDraw.Draw(mask))
        (stroke,) = drawing.strokes_from_mask(np.asarray(mask) > 0)
        return simplify(stroke["points"], 0.75, stroke["closed"]), stroke["closed"]

    settings = {"tolerance": 4, "angles": [0, 45, 90, 135], "angle_tolerance": 6, "circles": True, "corner": 24}
    arch = [(200 + 80 * math.cos(a), 200 + 80 * math.sin(a)) for a in np.linspace(math.pi, 2 * math.pi, 50)]
    window = traced(lambda d: d.line(arch + [(280, 360), (120, 360), (120, 200)], fill=255, width=5, joint="curve"))
    points, closed, kind = drawing.straighten_stroke(*window, **settings)
    points = np.asarray(points)
    top, sill = points[points[:, 1] < 195], points[points[:, 1] > 340]
    assert kind == "polyline" and closed
    assert len(top) > 20 and np.abs(np.hypot(top[:, 0] - 200, top[:, 1] - 200) - 80).max() < 3, "the arch stays round"
    assert len(sill) == 2 and abs(sill[0, 1] - sill[1, 1]) < 0.01, "the sill is one level side between sharp corners"
    box = traced(lambda d: d.rounded_rectangle([60, 80, 340, 300], radius=12, outline=255, width=5))
    points, closed, kind = drawing.straighten_stroke(*box, **settings)
    assert kind == "polyline" and len(points) == 4, "a neatly drawn box keeps its corners and is no circle"


def test_snap_angle():
    start, end, snapped = drawing.snap_angle((0, 0), (100, 4), [0, 90], 5)
    assert snapped == 0 and abs(start[1] - end[1]) < 1e-9
    assert drawing.snap_angle((0, 0), (100, 30), [0, 90], 5)[2] is None


def test_fill_regions_under_the_lines(sketch):
    p = built(sketch)
    regions = drawing.report(p, "art")["regions"]
    assert len(regions) >= 2
    inside = max(regions, key=lambda r: r["area"])
    p.apply({"type": "drawing", "action": "fill", "target": "art", "points": [[*inside["point"], "#ffcc00"]]})
    fill = p.layer("art/fill-1")
    names = [layer["name"] for layer in p.state["layers"]]
    assert names.index("art/fill-1") < names.index("art/s001"), "fills sit under the lines"
    image = p.render().convert("RGB")
    assert image.getpixel(tuple(int(v) for v in inside["point"])) == (255, 204, 0)
    with pytest.raises(VixlError) as error:
        p.apply({"type": "drawing", "action": "fill", "target": "art", "points": [[5, 5, "red"]]})
    assert "outside" in str(error.value) or "line" in str(error.value)
    assert fill["fill"] == "#ffcc00"


def test_fill_and_stroke_points_in_group_space_follow_a_moved_drawing(sketch):
    p = built(sketch)
    p.apply({"type": "move", "target": "art", "x": p.layer("art")["x"] + 37, "y": p.layer("art")["y"] + 21})
    report = drawing.report(p, "art")
    assert report["space"] == "canvas" and report["group"]["offset"][0] == pytest.approx(p.layer("art")["x"], abs=0.1)
    inside = max(report["regions"], key=lambda r: r["area"])
    assert inside["point"][0] == pytest.approx(inside["group_point"][0] + report["group"]["offset"][0], abs=0.2)
    p.apply({"type": "drawing", "action": "fill", "target": "art", "space": "group",
             "points": [[*inside["group_point"], "#ffcc00"]]})
    assert p.render().convert("RGB").getpixel(tuple(int(v) for v in inside["point"])) == (255, 204, 0)
    p.apply({"type": "drawing", "action": "stroke", "target": "art", "space": "group", "name": "art/local",
             "points": [[10, 10], [60, 10]], "settings": {"smooth": False}})
    p.apply({"type": "drawing", "action": "stroke", "target": "art", "name": "art/canvas",
             "points": [[10, 10], [60, 10]], "settings": {"smooth": False}})
    local, canvas = (p.layer(name)["drawing_strokes"][0]["points"][0] for name in ("art/local", "art/canvas"))
    assert local == [10, 10]
    assert canvas[0] == pytest.approx(10 - report["group"]["offset"][0], abs=0.01)


def test_added_strokes_restyle_and_preservation_check(sketch):
    p = built(sketch)
    p.apply({"type": "drawing", "action": "stroke", "target": "art", "points": [[100, 450], [300, 450], [300, 500]],
             "settings": {"smooth": False}})
    report = drawing.report(p, "art")
    assert report["stroke_kinds"]["added"] == 1 and report["added"] > 0
    p.apply({"type": "drawing", "action": "restyle", "target": "art", "color": "#d33", "settings": {"width_scale": 2}})
    assert p.layer("art/s001")["stroke"] == "#d33"
    assert p.check(checks=["drawing"])["passed"]
    for layer in [layer for layer in p.state["layers"] if layer["name"].startswith("art/s00")][:3]:
        p.apply({"type": "remove", "target": layer["name"]})
    issues = p.check(checks=["drawing"])["issues"]
    assert issues and issues[0]["check"] == "drawing" and "original lines" in issues[0]["message"]
    image = drawing.compare(p, "art")
    assert image.mode == "RGB" and image.size == (p.layer("art")["content_width"], p.layer("art")["content_height"])


def test_reclean_keeps_strokes_aligned_and_outline_mode(sketch):
    p = built(sketch)
    group = deepcopy(p.layer("art"))
    p.apply({"type": "drawing", "action": "clean", "target": "art", "settings": {"weight": 1, "margin": 60}})
    after = p.layer("art")
    assert (after["content_width"], after["content_height"]) == (group["content_width"], group["content_height"])
    assert drawing.report(p, "art")["preserved"] > 0.85
    q = Project(800, 600, "#ffffff")
    q.apply([{"type": "drawing", "action": "import", "path": str(sketch), "name": "art"},
             {"type": "drawing", "action": "vectorize", "target": "art", "settings": {"mode": "outline"}}])
    assert q.layer("art/lines")["shape"] == "path"
    assert drawing.report(q, "art")["preserved"] > 0.95
    with pytest.raises(VixlError):
        q.apply({"type": "drawing", "action": "straighten", "target": "art"})


def test_services_import_assets_not_paths(sketch):
    from vixl.interfaces import service_check

    with pytest.raises(VixlError):
        service_check({"type": "drawing", "action": "import", "path": str(sketch)})
    service_check({"type": "drawing", "action": "import", "asset": "assets/x.png"})


def test_cli_workflow_and_ai_colour(sketch, tmp_path):
    from vixl.cli import dispatch
    from vixl.commands import compile_command
    from vixl.interfaces import Session
    from vixl.workflows import dispatch as workflow

    # Tokens, not a shell-style string: a Windows path's backslashes are not escapes.
    assert compile_command(["drawing", "import", str(sketch), "--name", "art", "--x", "10"]) == {
        "type": "drawing", "action": "import", "path": str(sketch), "name": "art", "x": 10}
    assert compile_command("drawing straighten art --strokes art/s001,art/s002 --settings '{\"tolerance\": 3}'") == {
        "type": "drawing", "action": "straighten", "target": "art", "strokes": ["art/s001", "art/s002"],
        "settings": {"tolerance": 3}}
    path = tmp_path / "doc.vixl"
    built(sketch).save(path)
    report, _ = dispatch(["-p", str(path), "drawing", "report", "art"])
    assert report["preserved"] > 0.9
    dispatch(["-p", str(path), "drawing", "compare", "art", "--out", str(tmp_path / "c.png")])
    assert (tmp_path / "c.png").exists()
    session = Session(path)
    assert workflow(session, "drawing-compare", {"target": "art", "output": "d.png"})["output"] == "d.png"

    class Provider:
        name = "fixture"

        def invoke(self, capability, request):
            self.request = request
            return {"image": encoded(Image.new("RGBA", (request["width"], request["height"]), "skyblue")), "seed": 7}

    from vixl.ai import encoded

    provider = Provider()
    p = Project.load(path)
    drawing.ai_color(p, "art", "a sunny watercolour", provider, strength=0.5)
    assert provider.request["mode"] == "img2img" and "Keep every line" in provider.request["prompt"]
    names = [layer["name"] for layer in p.state["layers"]]
    assert names.index("art/color") < names.index("art/s001")
    assert drawing.report(p, "art")["preserved"] > 0.9
    image = p.render().convert("RGB")
    assert image.getpixel((5, 5)) == (135, 206, 235)
