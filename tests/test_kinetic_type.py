"""Per-character, per-word and per-line text animation (text-animate)."""

import numpy as np
import pytest
from PIL import Image

from vixl.checks import check_design
from vixl.errors import VixlError
from vixl.kinetic import assign, ranks, unit_poses
from vixl.project import Project
from vixl.render import render
from vixl.timeline import export_timeline, inspect_timeline, project_at, render_at


def card(text="Hello world", **extra):
    p = Project(360, 160, "#ffffff")
    p.apply([{"type": "text", "name": "title", "text": text, "size": 40, "color": "#111111", "x": 20, "y": 40, **extra},
             {"type": "timeline-set", "duration": 2000, "fps": 10}])
    return p


def poses(p, time, unit="char"):
    return (project_at(p, time).layer("title").get("_kinetic") or {}).get(unit)


def ink_box(image):
    alpha = np.asarray(image.convert("L")) < 200
    ys, xs = np.nonzero(alpha)
    return xs.min(), ys.min(), xs.max(), ys.max()


def test_units_follow_glyph_clusters_words_and_lines():
    units, counts = assign([("a", 0), ("b", 0), (" ", 0), ("c", 0), ("", 0), ("d", 1)])
    assert units == [(0, 0, 0), (1, 0, 0), None, (2, 1, 0), (2, 1, 0), (3, 2, 1)]
    assert counts == {"char": 4, "word": 3, "line": 2}


def test_per_unit_offsets_and_opacity_at_given_times():
    p = card()
    p.apply({"type": "text-animate", "target": "title", "preset": "fade-up", "unit": "char", "duration": 400,
             "stagger": 100, "easing": "linear", "distance": 20})
    at = poses(p, 200)
    assert len(at) == 10  # "Hello world": ten visible characters
    assert at[0][0] == pytest.approx(0.5) and at[0][2] == pytest.approx(10)
    assert at[1][0] == pytest.approx(0.25) and at[1][2] == pytest.approx(15)
    assert at[2][0] == pytest.approx(0) and at[2][2] == pytest.approx(20)
    assert poses(p, 1300) is None  # 9 x 100 + 400 ms: every unit rests


def test_stagger_ordering_by_direction():
    assert ranks("forward", 4) == [0, 1, 2, 3]
    assert ranks("reverse", 4) == [3, 2, 1, 0]
    assert ranks("center", 5) == [2, 1, 0, 1, 2]
    assert ranks("edges", 5) == [0, 1, 2, 1, 0]
    random = ranks("random", 8, seed=3)
    assert sorted(random) == list(range(8)) and random == ranks("random", 8, seed=3) and random != ranks("random", 8, seed=4)
    spec = {"preset": "fade", "unit": "word", "start": 0, "duration": 300, "stagger": 100, "direction": "reverse",
            "easing": "linear"}
    opacity = [pose[0] for pose in unit_poses(spec, 3, 150, 2000, 40)]
    assert opacity[2] > opacity[1] > opacity[0] == 0


def test_stagger_accepts_a_percentage_of_duration():
    p = card()
    p.apply({"type": "text-animate", "target": "title", "preset": "fade", "unit": "word", "duration": 400, "stagger": "50%"})
    assert inspect_timeline(p)["text_animations"][0]["stagger_ms"] == 200


@pytest.mark.parametrize("preset", ["fade-up", "pop", "slide-left", "wave", "typewriter", "color-sweep"])
def test_rest_state_equals_the_static_render(preset):
    p = card()
    p.apply({"type": "text-animate", "target": "title", "preset": preset, "unit": "word", "duration": 300})
    assert np.array_equal(np.asarray(render(p)), np.asarray(render_at(p, 2000)))


def test_mid_frame_moves_glyphs_without_exploding_the_layer():
    p = card()
    count = len(p.state["layers"])
    p.apply({"type": "text-animate", "target": "title", "preset": "fade-down", "unit": "line", "duration": 1000,
             "distance": 30, "easing": "linear"})
    assert len(p.state["layers"]) == count and p.layer("title")["text"] == "Hello world"
    rest, moving = ink_box(render(p)), ink_box(render_at(p, 500))
    assert moving[1] == pytest.approx(rest[1] - 15, abs=2)  # half of 30 px, upwards, drawn past the layer box
    assert moving[0] == pytest.approx(rest[0], abs=1)


def test_rich_text_animates_per_word():
    p = Project(360, 160, "#203040")
    p.apply([{"type": "rich-text", "name": "title", "markdown": "Hello **bold** world", "size": 40, "x": 20, "y": 40},
             {"type": "timeline-set", "duration": 2000}])
    p.apply({"type": "text-animate", "target": "title", "preset": "pop", "unit": "word", "duration": 400})
    assert len(poses(p, 150, "word")) == 3
    assert not np.array_equal(np.asarray(render(p)), np.asarray(render_at(p, 150)))
    assert np.array_equal(np.asarray(render(p)), np.asarray(render_at(p, 2000)))


def test_poster_check_sees_text_hidden_by_unit_opacity():
    p = card()
    p.apply({"type": "text-animate", "target": "title", "preset": "fade-up", "unit": "char", "duration": 300})
    codes = {i.get("code") for i in check_design(p, checks=["motion"])["issues"]}
    assert "empty-poster" in codes  # the only layer is hidden by its letters' opacity
    p.apply([{"type": "shape", "shape": "rectangle", "name": f"box{i}", "x": 10 * i, "y": 120, "width": 8, "height": 8,
              "fill": "#333333"} for i in range(10)])
    codes = {i.get("code") for i in check_design(p, checks=["motion"])["issues"]}
    assert "text-hidden-at-poster" in codes


def test_seamless_loop_plays_units_out_again():
    p = card()
    p.apply({"type": "timeline-set", "loop_mode": "seamless"})
    p.apply({"type": "text-animate", "target": "title", "preset": "fade", "unit": "word", "duration": 300})
    assert p.state["timeline"]["text_animations"][0]["mode"] == "in-out"
    assert poses(p, 1000) is None
    assert all(pose[0] < 0.01 for pose in poses(p, 2000, "word"))
    codes = {i.get("code") for i in check_design(p, checks=["motion"])["issues"]}
    assert "loop-seam" not in codes
    out = p.apply({"type": "text-animate", "target": "title", "preset": "fade", "unit": "word", "duration": 300, "mode": "in"})
    assert "jumps at the seam" in str(out["warnings"])
    codes = {i.get("code") for i in check_design(p, checks=["motion"])["issues"]}
    assert "loop-seam" in codes


def test_repeating_wave_cycles_through_the_timeline():
    p = card()
    p.apply({"type": "text-animate", "target": "title", "preset": "wave", "unit": "char", "duration": 500,
             "stagger": 50, "repeat": True, "amount": 10})
    assert poses(p, 1250) is not None and poses(p, 1750) is not None
    assert min(pose[2] for pose in poses(p, 1250)) < -5


def test_long_animation_extends_the_timeline_and_says_so():
    p = card()
    out = p.apply({"type": "text-animate", "target": "title", "preset": "fade", "unit": "char", "duration": 500, "stagger": 200})
    assert p.state["timeline"]["duration"] == 9 * 200 + 500
    assert "timeline duration changed 2000 -> 2300" in str(out["warnings"])


def test_inspect_lists_text_animations_and_remove_clears_them():
    p = card()
    p.apply({"type": "text-animate", "target": "title", "preset": "typewriter", "duration": 1000})
    item = inspect_timeline(p)["text_animations"][0]
    assert item["layer"] == "title" and item["units"] == 10 and item["stagger_ms"] == 100
    p.apply({"type": "text-animate", "target": "title", "remove": True})
    assert "text_animations" not in p.state["timeline"]


def test_removing_the_layer_prunes_its_animation_and_documents_round_trip(tmp_path):
    p = card()
    p.apply({"type": "text-animate", "target": "title", "preset": "pop", "unit": "word"})
    p.save(tmp_path / "k.vixl")
    again = Project.load(tmp_path / "k.vixl")
    assert again.state["timeline"]["text_animations"] == p.state["timeline"]["text_animations"]
    p.apply({"type": "remove", "target": "title"})
    assert "text_animations" not in p.state["timeline"]


def test_rejects_layers_it_cannot_animate_per_unit():
    p = card()
    p.apply({"type": "shape", "shape": "rectangle", "name": "box", "width": 20, "height": 20})
    with pytest.raises(VixlError, match="text layer"):
        p.apply({"type": "text-animate", "target": "box", "preset": "fade"})
    with pytest.raises(VixlError, match="repeat"):
        p.apply({"type": "text-animate", "target": "title", "preset": "fade", "repeat": True})


def test_gif_export_animates_units_and_still_exports_show_rest(tmp_path):
    p = card()
    p.apply({"type": "text-animate", "target": "title", "preset": "fade", "unit": "char", "duration": 400, "stagger": 100})
    export_timeline(p, tmp_path / "k.gif", fps=10)
    with Image.open(tmp_path / "k.gif") as gif:
        first = np.asarray(gif.convert("L"))
        gif.seek(gif.n_frames - 1)
        last = np.asarray(gif.convert("L"))
    assert first.min() > 200 and last.min() < 100  # hidden on the first frame, drawn on the last
    p.export(tmp_path / "still.png")
    assert np.array_equal(np.asarray(Image.open(tmp_path / "still.png").convert("RGB")), np.asarray(render(p).convert("RGB")))
    p.export(tmp_path / "x.svg")
    assert 'opacity="0' not in (tmp_path / "x.svg").read_text()


def test_kinetic_text_inside_an_animated_group_composes():
    p = card()
    p.apply([{"type": "group", "targets": ["title"], "name": "g"},
             {"type": "animate", "target": "g", "property": "translate-x", "from": 0, "to": 100, "duration": 2000},
             {"type": "text-animate", "target": "title", "preset": "fade-up", "unit": "word", "duration": 400}])
    frame = project_at(p, 2000)
    assert frame.layer("title").get("_kinetic") is None
    assert ink_box(render_at(p, 2000))[0] == pytest.approx(ink_box(render(p))[0] + 100, abs=2)
