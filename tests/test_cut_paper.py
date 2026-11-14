"""Cut-paper scenes: undirected grain with texture controls (#748), textures that are effects on the layer they
texture and so follow it (#747), and stop-motion jitter applied when a piece is composited, so a new hold reuses
the drawn pieces (#754)."""

import numpy as np
import pytest

from vixl import Project, design_render, frame_workers, scene, textures
from vixl.errors import VixlError
from vixl.timeline import project_at, render_at, render_scaled


def sheet(size=480, **paper):
    p = Project(size + 40, size + 40, "#ffffff")
    p.apply([{"type": "shape", "name": "sheet", "shape": "rectangle", "width": size, "height": size, "x": 20, "y": 20,
              "fill": "#93cbe6", "stroke_width": 0},
             {"type": "cut-paper", "target": "sheet", "grain": 0.065, "roughness": 0.4, "thickness": 2, "seed": 3,
              "jitter": 0, **paper}])
    return p


def interior(p, margin=40):
    pixels = np.asarray(p.render().convert("RGB"), dtype=float).mean(axis=2)
    return pixels[margin:-margin, margin:-margin]


# --- #748: grain ---

def test_grain_has_no_direction():
    # The grain had one random value per row across the full width: row means varied 4.4 times as much as
    # column means (a variance ratio near 20) and large pieces read as scanlines.
    rows = columns = 0
    for seed in range(6):
        paper = interior(sheet(seed=seed))
        row, column = paper.mean(axis=1).var(), paper.mean(axis=0).var()
        # One sheet holds only a dozen mottling cells each way, so its two variances differ by chance; streaks
        # differed by far more.
        assert max(row, column) / min(row, column) < 5, (seed, row, column)
        rows, columns = rows + row, columns + column
        # Still grain: fine tooth and soft mottling, not a flat fill.
        assert 6 < paper.std() < 25
    assert max(rows, columns) / min(rows, columns) < 1.5, (rows, columns)


def test_grain_is_seeded_and_the_same_on_every_frame_of_a_hold():
    assert sheet().render().tobytes() == sheet().render().tobytes()
    assert sheet().render().tobytes() != sheet(seed=4).render().tobytes()
    p = sheet(jitter=0.35, fps=10)
    p.apply({"type": "timeline-set", "duration": 1000, "fps": 30})
    assert render_at(p, 105).tobytes() == render_at(p, 190).tobytes()  # one hold
    # Across holds the piece moves by its jitter, and the grain moves with it: the same paper, not new noise.
    first, second = project_at(p, 105).layer("sheet"), project_at(p, 205).layer("sheet")
    assert first["_jitter"] != second["_jitter"] and first["cut_paper"] == second["cut_paper"]


def test_texture_controls_change_the_paper():
    base = interior(sheet())
    coarse = interior(sheet(grain_scale=120))
    bare = interior(sheet(fibers={"count": 0}))
    hairy = interior(sheet(fibers={"count": 40, "length": 30}))
    assert not np.array_equal(base, coarse) and not np.array_equal(base, bare)

    def blocks(pixels, cell=24):
        h, w = (v // cell * cell for v in pixels.shape)
        return pixels[:h, :w].reshape(h // cell, cell, w // cell, cell).mean(axis=(1, 3))

    # A larger grain_scale makes neighbouring 24 px blocks agree: the mottling turns over more slowly.
    def step(pixels):
        means = blocks(pixels)
        return np.abs(np.diff(means, axis=1)).mean() / means.std()

    assert step(coarse) < step(base) * 0.75
    # Fibres are sparse strokes well outside the fine tooth: more of them, more far-out pixels.
    def outliers(pixels):
        return (np.abs(pixels - pixels.mean()) > 2.6 * interior(sheet(fibers={"count": 0})).std()).mean()

    assert outliers(hairy) > 2 * outliers(bare)
    layer = sheet(grain_scale=120, fibers={"count": 40, "length": 30}).layer("sheet")
    assert layer["cut_paper"]["grain_scale"] == 120 and layer["cut_paper"]["fibers"] == {"count": 40, "length": 30}


def test_a_saved_pattern_can_be_the_paper_texture(tmp_path):
    p = Project(300, 300, "#ffffff")
    # A tile of two vertical bands, 8 px each.
    p.apply([{"type": "solid", "name": "dark", "width": 8, "height": 16, "color": "#5a5a5a"},
             {"type": "solid", "name": "light", "width": 8, "height": 16, "x": 8, "color": "#aaaaaa"},
             {"type": "group", "name": "tile", "targets": ["dark", "light"]},
             {"type": "pattern-define", "name": "bands", "target": "tile"},
             {"type": "remove", "target": "tile"},
             {"type": "shape", "name": "sheet", "shape": "rectangle", "width": 260, "height": 260, "x": 20, "y": 20,
              "fill": "#93cbe6", "stroke_width": 0},
             {"type": "cut-paper", "target": "sheet", "grain": 0.06, "roughness": 0, "pattern": "bands", "jitter": 0}])
    assert p.layer("sheet")["cut_paper"]["pattern"] == "bands"
    paper = np.asarray(p.render().convert("RGB"), dtype=float).mean(axis=2)[40:260, 40:260]
    # The tile's bands are the texture: columns differ by the grain strength, rows hardly at all.
    assert paper.mean(axis=0).std() == pytest.approx(255 * 0.06, rel=0.15)
    assert paper.mean(axis=1).std() < 0.5
    p.save(tmp_path / "bands.vixl")
    assert Project.load(tmp_path / "bands.vixl").render().tobytes() == p.render().tobytes()
    with pytest.raises(VixlError, match="Unknown pattern"):
        p.apply({"type": "cut-paper", "target": "sheet", "pattern": "nope"})
    with pytest.raises(VixlError):
        p.apply({"type": "cut-paper", "target": "sheet", "fibers": {"count": 3, "angle": 20}})


def test_cut_paper_texture_fields_are_documented():
    from vixl.schema import operation_schema

    variants = operation_schema()["properties"]["operations"]["items"]["oneOf"]
    properties = next(v for v in variants if v["properties"]["type"]["const"] == "cut-paper")["properties"]
    for name in ("grain_scale", "fibers", "pattern"):
        assert properties[name].get("description"), name
    for name in ("count", "length"):
        assert properties["fibers"]["properties"][name]["description"]


# --- #747: textures follow their layer ---

LOCK = [
    {"type": "shape", "name": "lock", "shape": "rounded-rectangle", "width": 40, "height": 150, "x": 130, "y": 50,
     "fill": "#f2789f", "radius": 12},
    {"type": "pivot", "target": "lock", "value": "top"},
]
SWING = [
    {"type": "keyframes", "target": "lock", "property": "rotation",
     "keys": [{"time": 0, "value": 0}, {"time": 1000, "value": 60}]},
    {"type": "timeline-set", "duration": 1000, "fps": 12},
]
STRIPES = {"type": "pattern-fill", "target": "lock", "pattern": "stripes", "colors": ["#000000", "#ffffff"],
           "opacity": 0.6, "name": "lock-tex"}


def lock(*texture):
    p = Project(300, 300, "#ffffff")
    p.apply([*LOCK, *texture, *SWING])
    return p


def changed(a, b):
    return np.abs(np.asarray(a.convert("RGB"), dtype=int) - np.asarray(b.convert("RGB"), dtype=int)).max(axis=2) > 24


def ink(image, grow=2):
    """Where ``image`` is not white, grown by ``grow`` px: a silhouette with room for its antialiased edge."""
    from PIL import Image, ImageFilter

    mask = np.abs(np.asarray(image.convert("RGB"), dtype=int) - 255).max(axis=2) > 24
    grown = Image.fromarray(np.uint8(mask) * 255).filter(ImageFilter.MaxFilter(2 * grow + 1))
    return np.asarray(grown) > 0


def test_pattern_fill_turns_with_its_animated_layer():
    plain, striped = lock(), lock(STRIPES)
    assert len(striped.state["layers"]) == 1  # no texture layer
    silhouette, start = ink(render_at(plain, 1000)), ink(render_at(plain, 0))  # the lock turned 60 degrees, and at rest
    stripes = changed(render_at(striped, 1000), render_at(plain, 1000))
    # The stripes are inside the rotated silhouette, and a good part of it; where the lock started (and no
    # longer is) nothing is drawn. The sibling raster stayed there as a ghost.
    assert stripes.sum() > 0.2 * silhouette.sum()
    assert not (stripes & ~silhouette).any()
    assert not (stripes & start & ~silhouette).any()
    # They turn with it: a stripe is a run along the lock's width, at 60 degrees to where it was.
    ys, xs = np.nonzero(stripes)
    assert xs.min() < 60 and ys.max() < 150  # swung up and to the left of the pivot at (150, 50)
    report = striped.check(checks=["motion"])
    assert not [issue for issue in report["issues"] if "lock-tex" in issue["message"] or "apart" in issue["message"]]


def test_drawn_texture_follows_too_and_texturing_adds_no_layers():
    hatch = {"type": "drawn-texture", "target": "lock", "preset": "hatch", "color": "#102040", "strength": 1}
    plain, drawn = lock(), lock(hatch)
    assert len(drawn.state["layers"]) == 1
    shape = ink(render_at(plain, 1000))
    marks = changed(render_at(drawn, 1000), render_at(plain, 1000))
    assert marks.sum() > 50 and not (marks & ~shape).any()
    p = Project(400, 200, "#ffffff")
    names = [f"piece{i}" for i in range(12)]
    p.apply([{"type": "shape", "name": name, "shape": "ellipse", "width": 60, "height": 60, "x": 10 + i * 30, "y": 40,
              "fill": "#d08040"} for i, name in enumerate(names)])
    before = len(p.state["layers"])
    p.apply({"type": "pattern-fill", "targets": names, "pattern": "paper", "opacity": 0.5})
    assert len(p.state["layers"]) == before
    assert all(p.layer(name)["effects"][-1]["name"] == "pattern-fill" for name in names)


def test_the_texture_is_an_ordinary_stack_effect():
    p = lock(STRIPES)
    effect = p.layer("lock")["effects"][0]
    assert effect["amount"] == 0.6 and effect["label"] == "lock-tex" and effect["texture"]["pattern"] == "stripes"
    striped = p.render()
    # Its label names it for the effect operations; its amount is its opacity.
    p.apply({"type": "effect-set", "target": "lock", "effect": "lock-tex", "amount": 0.1})
    faint = p.render()
    assert changed(striped, faint).any()
    p.apply({"type": "effect-disable", "target": "lock", "effect": "lock-tex"})
    assert p.render().tobytes() == lock().render().tobytes()
    p.apply([{"type": "effect-enable", "target": "lock", "effect": 1},
             {"type": "blur", "target": "lock", "value": 2},
             {"type": "effect-move", "target": "lock", "effect": "lock-tex", "to": "bottom"}])
    assert [e["name"] for e in p.layer("lock")["effects"]] == ["blur", "pattern-fill"]
    p.apply({"type": "effect-remove", "target": "lock", "effect": "pattern-fill"})
    assert [e["name"] for e in p.layer("lock")["effects"]] == ["blur"]
    with pytest.raises(VixlError, match="pattern-fill operation"):
        p.apply({"type": "effect", "target": "lock", "name": "pattern-fill"})
    # effect-set changes the opacity; the other settings belong to the operation that adds the texture.
    p.apply(STRIPES)
    with pytest.raises(VixlError, match="remove the effect and add it again"):
        p.apply({"type": "effect-set", "target": "lock", "effect": "lock-tex", "seed": 4})
    with pytest.raises(VixlError):
        p.apply({"type": "pattern-fill", "target": "lock", "pattern": "stripes", "opacity": 2})
    with pytest.raises(VixlError, match="Unknown pattern"):
        p.apply({"type": "pattern-fill", "target": "lock", "pattern": "no-such-pattern"})


def test_texture_opacity_animates_and_blend_and_layer_options_work():
    p = lock(STRIPES)
    effect = p.layer("lock")["effects"][0]["id"]
    p.apply({"type": "animate", "target": "lock", "property": f"effect:{effect}", "from": 0, "to": 1,
             "duration": 1000, "easing": "linear"})
    assert render_at(p, 0).tobytes() == render_at(lock(), 0).tobytes()
    assert changed(render_at(p, 1000), render_at(lock(), 1000)).any()
    multiplied = lock({**STRIPES, "blend": "multiply", "opacity": 1})
    assert multiplied.layer("lock")["effects"][0]["texture"]["blend"] == "multiply"
    pixels = np.asarray(multiplied.render().convert("RGB"), dtype=int)
    normal = np.asarray(lock({**STRIPES, "opacity": 1}).render().convert("RGB"), dtype=int)
    assert (pixels <= normal + 1).all() and (pixels < normal - 20).any()  # white stripes keep the pink
    # layer: true is the separate overlay of earlier releases: a second layer that stays behind.
    separate = lock({**STRIPES, "layer": True})
    assert [layer["name"] for layer in separate.state["layers"]] == ["lock", "lock-tex"]
    assert separate.layer("lock")["effects"] == []
    # The same picture at rest (one level of rounding apart: the overlay is composited as its own layer).
    assert np.abs(np.asarray(separate.render(), dtype=int) - np.asarray(lock(STRIPES).render(), dtype=int)).max() <= 2


def test_textures_round_trip_export_and_follow_a_redefined_pattern(tmp_path):
    p = Project(200, 120, "#ffffff")
    p.apply([{"type": "solid", "name": "tile", "width": 8, "height": 8, "color": "#208040"},
             {"type": "pattern-define", "name": "swatch", "target": "tile"},
             {"type": "move", "target": "tile", "x": 180, "y": 100},
             {"type": "shape", "name": "card", "shape": "rounded-rectangle", "width": 120, "height": 70, "x": 20,
              "y": 20, "fill": "#e9c46a", "rotation": 20},
             {"type": "pattern-fill", "target": "card", "pattern": "swatch", "opacity": 0.8},
             {"type": "drawn-texture", "target": "card", "preset": "stipple", "seed": 5}])
    image = p.render()
    assert image.getpixel((80, 60))[1] > image.getpixel((80, 60))[0]  # green over the yellow card
    p.save(tmp_path / "card.vixl")
    restored = Project.load(tmp_path / "card.vixl")
    assert restored.render().tobytes() == image.tobytes()
    # Vector formats keep the textured layer's pixels (a raster fallback that names the effects).
    svg = p.export(format="SVG")
    assert b"data:image/png" in svg and b"pattern and drawn textures are exported as images" in svg
    assert b"pattern-fill" in svg and b"drawn-texture" in svg
    for format_, magic in (("PDF", b"%PDF"), ("PPTX", b"PK")):
        report = {}
        assert p.export(format=format_, report=report).startswith(magic)
        assert "card" in str(report["raster_fallbacks"])
    # The cached card does not outlive its tile: redefining the pattern changes the next render.
    p.apply([{"type": "remove", "target": "tile"},
             {"type": "solid", "name": "tile", "width": 8, "height": 8, "color": "#a02060", "x": 180, "y": 100},
             {"type": "pattern-define", "name": "swatch", "target": "tile"}])
    again = p.render()
    assert again.getpixel((80, 60))[0] > again.getpixel((80, 60))[1]
    # A reduced preview scales the texture with the layer instead of failing or keeping full-size cells.
    from vixl.proxy import render_preview

    assert render_preview(p, 100, 60).size == (100, 60)


def test_stored_texture_effects_are_validated_on_load(tmp_path):
    p = lock(STRIPES)
    p.save(tmp_path / "lock.vixl")
    state = Project.load(tmp_path / "lock.vixl").state
    from vixl.design import validate_design

    broken = Project(300, 300)
    for settings in ({"pattern": "no-such-pattern"}, {"pattern": "stripes", "blend": "burn"}, {"speckle": 1}):
        state["layers"][0]["effects"][0]["texture"] = settings
        with pytest.raises(VixlError):
            validate_design(broken, state)


# --- #754: a new hold reuses the drawn pieces ---

def paper_scene(pieces=24, jitter=0.35):
    p = Project(480, 270, "#dfeaf2")
    names = [f"piece{i}" for i in range(pieces)]
    p.apply([{"type": "shape", "name": "sky", "shape": "rectangle", "width": 500, "height": 290, "x": -10, "y": -10,
              "fill": "#93cbe6", "stroke_width": 0}] +
            [{"type": "shape", "name": name, "shape": ("ellipse", "triangle", "rounded-rectangle")[i % 3],
              "width": 40 + i % 5 * 9, "height": 34 + i % 4 * 8, "x": 12 + i % 8 * 56, "y": 16 + i // 8 * 80,
              "fill": ("#e76f51", "#2a9d8f", "#e9c46a", "#8d6cab")[i % 4]} for i, name in enumerate(names)])
    p.apply([{"type": "pattern-fill", "targets": names[::2], "pattern": "paper", "opacity": 0.5},
             {"type": "group", "name": "cluster", "targets": names[-3:]},
             {"type": "cut-paper", "targets": ["sky", *names[:-3], "cluster"], "grain": 0.06, "roughness": 0.4,
              "thickness": 2, "seed": 3, "jitter": jitter},
             {"type": "timeline-set", "duration": 2000, "fps": 24},
             # Two pieces travel: their place has a new fraction on every hold.
             {"type": "keyframes", "target": "piece1", "property": "x",
              "keys": [{"time": 0, "value": 10}, {"time": 2000, "value": 300.5}]},
             {"type": "keyframes", "target": "cluster", "property": "y",
              "keys": [{"time": 0, "value": 150}, {"time": 2000, "value": 171.3}]}])
    return p


def test_a_new_hold_does_not_draw_the_pieces_again(monkeypatch):
    p = paper_scene()
    calls = {"shape": 0, "paper": 0}
    shape_image, paper_image = design_render.shape_image, scene.paper_image

    def counted_shape(*args, **kwargs):
        calls["shape"] += 1
        return shape_image(*args, **kwargs)

    def counted_paper(image, layer, project=None):
        calls["paper"] += layer.get("cut_paper") is not None
        return paper_image(image, layer, project)

    monkeypatch.setattr(design_render, "shape_image", counted_shape)
    monkeypatch.setattr(scene, "paper_image", counted_paper)
    first = render_at(p, 0)
    assert calls["shape"] >= 25 and calls["paper"] >= 25
    calls.update(shape=0, paper=0)
    held = render_at(p, 40)  # the same 12 fps hold
    assert held.tobytes() == first.tobytes()
    later = render_at(p, 90)  # a new hold: every piece has a new jitter, two have moved
    assert later.tobytes() != first.tobytes()
    # Before, each new hold drew all 25 shapes and their paper again (jitter moved every piece by a fraction of
    # a pixel, which misses the raster cache). Now nothing is drawn again, the travelling pieces included.
    assert calls == {"shape": 0, "paper": 0}
    render_at(p, 180)
    assert calls == {"shape": 0, "paper": 0}


def test_jitter_is_an_offset_on_the_frame_not_a_move_of_the_layer():
    p = paper_scene()
    document = {layer["id"]: (layer["x"], layer["y"]) for layer in p.state["layers"]}
    frame = project_at(p, 500)
    jitters = []
    for layer in frame.state["layers"]:
        if "cut_paper" in layer:
            dx, dy, reach = layer["_jitter"]
            assert abs(dx) <= 0.35 and abs(dy) <= 0.35 and reach == 1
            jitters.append((dx, dy))
            if layer["name"] not in ("piece1",):
                assert (layer["x"], layer["y"]) == document[layer["id"]]
        else:
            assert "_jitter" not in layer
    assert len(set(jitters)) == len(jitters) > 20  # each piece its own
    assert all("_jitter" not in layer for layer in p.state["layers"])  # the document is untouched
    # The offset is visible: a piece's ink lands at a different sub-pixel place on the next hold.
    a, b = (np.asarray(render_at(p, t).convert("RGB"), dtype=int) for t in (500, 600))
    box = (slice(100, 130), slice(120, 200))  # piece10 and piece11, which no track moves
    assert 0 < np.abs(a[box] - b[box]).max() and np.abs(a[box] - b[box]).mean() < 12


def test_rebuilding_a_scene_gives_the_same_jitter():
    # The offsets were seeded by layer IDs, which are random for each new document: running a build script twice
    # gave two different animations.
    a, b = paper_scene(pieces=6), paper_scene(pieces=6)
    assert [layer["id"] for layer in a.state["layers"]] != [layer["id"] for layer in b.state["layers"]]
    for time in (0, 90, 500):
        assert ([layer.get("_jitter") for layer in project_at(a, time).state["layers"]]
                == [layer.get("_jitter") for layer in project_at(b, time).state["layers"]])
        assert render_at(a, time).tobytes() == render_at(b, time).tobytes()


def test_jitter_keeps_full_bleed_pieces_covering_the_canvas_and_jitter_zero_is_unchanged():
    p = paper_scene()
    for time in (0, 90, 180, 270):
        frame = np.asarray(render_at(p, time).convert("RGB"), dtype=int)
        edges = np.concatenate([frame[0], frame[-1], frame[:, 0], frame[:, -1]])
        # The sky reaches 10 px past every edge: no hold may let the canvas colour (#dfeaf2) show through.
        assert (np.abs(edges - np.array([0xdf, 0xea, 0xf2])).max(axis=1) > 12).all(), time
    still = paper_scene(jitter=0)
    assert all("_jitter" not in layer for layer in project_at(still, 90).state["layers"])


def test_large_jitter_moves_by_whole_pixels_too_and_draft_snaps_it():
    p = paper_scene(pieces=6, jitter=3)
    frames = [render_at(p, time) for time in (0, 90, 180)]
    assert len({frame.tobytes() for frame in frames}) == 3
    reach = max(abs(v) for layer in project_at(p, 90).state["layers"] if "_jitter" in layer
                for v in layer["_jitter"][:2])
    assert 1 < reach <= 3
    # draft: whole-pixel placement. Jitter under half a pixel is left out, so holds of a still scene match.
    q = Project(200, 120, "#ffffff")
    q.apply([{"type": "shape", "name": "card", "shape": "ellipse", "width": 90, "height": 60, "x": 40.4, "y": 20.3,
              "fill": "#e76f51"},
             {"type": "cut-paper", "target": "card", "jitter": 0.4, "seed": 2},
             {"type": "timeline-set", "duration": 1000, "fps": 24}])
    assert render_at(q, 0).tobytes() != render_at(q, 500).tobytes()
    assert render_at(q, 0, draft=True).tobytes() == render_at(q, 500, draft=True).tobytes()
    assert render_at(q, 0, draft=True).tobytes() != render_at(q, 0).tobytes()
    from vixl.proxy import render_preview

    assert (render_preview(q, 200, 120, time=0, draft=True).tobytes()
            == render_preview(q, 200, 120, time=500, draft=True).tobytes())


def test_jittered_frames_do_not_depend_on_what_is_cached(monkeypatch):
    p = paper_scene(pieces=9)
    warm = [render_at(p, time).tobytes() for time in (0, 90, 180, 90)]
    assert warm[1] == warm[3]
    cold = []
    for time in (180, 90, 0):
        fresh = p.clone()
        fresh._cache = None  # an empty layer cache, and no previous canvas to patch
        cold.append(render_at(fresh, time).tobytes())
    assert cold == [warm[2], warm[1], warm[0]]
    monkeypatch.setenv("VIXL_RENDER_THREADS", "1")
    single = p.clone()
    single._cache = None
    assert render_at(single, 90).tobytes() == warm[1]


def test_parallel_frame_workers_match_one_process_byte_for_byte():
    p = paper_scene(pieces=9)
    times = [0, 45, 90, 135, 180, 400]
    here = [render_scaled(project_at(p, time, prune=True), 1) for time in times]
    there = list(frame_workers.frames(p, times, 1, 2))
    assert [image.tobytes() for image in there] == [image.tobytes() for image in here]
    half = list(frame_workers.frames(p, times[:3], 0.5, 2))
    assert [image.tobytes() for image in half] == [render_scaled(project_at(p, time, prune=True), 0.5).tobytes()
                                                   for time in times[:3]]


def test_path_geometry_is_kept_between_frames_without_sharing_results():
    from vixl import geometry, vector_strokes

    path = "M0 0 C30 -40 70 -40 100 0 L100 60 L0 60 Z"
    geometry._flattened_path.cache_clear()
    first = geometry.path_polygons(path)
    first[0].append((999, 999))
    first.append([])
    again = geometry.path_polygons(path)
    assert len(again) == 1 and (999, 999) not in again[0] and again == geometry._path_polygons(path)
    assert geometry._flattened_path.cache_info().hits == 1
    commands = geometry.parse_path(path)
    commands[0][1].append(5)
    assert geometry.parse_path(path) == geometry._parse_path(path)
    assert vector_strokes.path_bounds(path) == vector_strokes._path_bounds.__wrapped__(path)
    assert vector_strokes.path_margin([(path, "#000000"), ("", "#000000"), (path, "transparent")], 100, 60) == (0, 30)
    with pytest.raises(VixlError):
        geometry.path_polygons("L0 0")
    huge = "M0 0 " + "L1 1 " * 4000  # longer than the cache keeps
    assert len(huge) > geometry.PATH_CACHE_CHARS and len(geometry.path_polygons(huge)[0]) == 4001


def test_texture_module_names_the_effects_it_adds():
    from vixl.constants import STACK_EFFECTS

    assert set(textures.TEXTURE_EFFECTS) <= set(STACK_EFFECTS)
