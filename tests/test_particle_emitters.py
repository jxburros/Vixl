"""particles: one group per emitter, named after it, and one bounds note per emitter (#604)."""

import numpy as np

from vixl import Project
from vixl.spatial import canvas_boxes
from vixl.timeline import project_at, render_at


def sparks(**extra):
    p = Project(400, 300, "#101010")
    p.apply({"type": "particles", "name": "sparks", "preset": "sparks", "count": 70, "x": 200, "y": 300,
             "spread": [380, 10], "seed": 3, **extra})
    return p


def test_the_emitter_is_a_group_named_after_it():
    p = sparks()
    group = p.layer("sparks")
    assert group["type"] == "group"
    children = [layer for layer in p.state["layers"] if layer.get("parent") == group["id"]]
    assert len(children) == 70 and all("particle" in layer for layer in children)
    # It can be targeted, grouped and moved as one thing; the particles move with it.
    p.apply([{"type": "shape", "shape": "rectangle", "name": "title", "x": 10, "y": 10, "width": 50, "height": 20},
             {"type": "group", "name": "cue-1", "targets": ["title", "sparks"]}])
    frame = project_at(p, 400)
    before = canvas_boxes(frame)[frame.layer("sparks/5")["id"]]
    p.apply({"type": "move", "target": "cue-1", "x": p.layer("cue-1")["x"] + 30})
    frame = project_at(p, 400)
    after = canvas_boxes(frame)[frame.layer("sparks/5")["id"]]
    assert np.allclose(np.subtract(after[:2], before[:2]), (30, 0))


def test_particles_follow_their_physics_in_canvas_space():
    p = Project(120, 120)
    p.apply({"type": "particles", "name": "sparks", "preset": "sparks", "count": 3, "x": 30, "y": 20,
             "spread": [0, 0], "velocity": [10, 0], "gravity": 100, "life": 2000, "duration": 1000, "turbulence": 0,
             "seed": 12})
    frame = project_at(p, 500)
    x, y, _, _ = canvas_boxes(frame)[frame.layer("sparks/0")["id"]]
    assert (x, y) == (35, 32.5)
    assert np.array_equal(np.asarray(render_at(p, 500)), np.asarray(render_at(p, 500)))


def test_one_bounds_note_per_emitter_instead_of_one_per_particle():
    p = sparks()
    issues = [issue for issue in p.check(checks=["bounds"])["issues"] if issue["check"] == "bounds"]
    assert len(issues) == 1, issues
    assert issues[0]["layers"] == ["sparks"] and issues[0]["severity"] == "info" and issues[0]["intentional"]
