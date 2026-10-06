"""Motion findings from frames sampled over time (#237)."""

from vixl import Project
from vixl.motion import MAX_SAMPLES, _sample_times, rendered_seam_findings, time_findings
from vixl.timeline import export_timeline


def codes(project):
    return {item["code"]: item for item in time_findings(project)}


def scene(ball_on_top=True):
    p = Project(300, 200, "white")
    ball = {"type": "shape", "name": "ball", "shape": "ellipse", "width": 30, "height": 30, "x": 0, "y": 80, "fill": "red"}
    title = {"type": "text", "name": "title", "text": "Title", "size": 32, "color": "black", "x": 110, "y": 80}
    p.apply([title, ball] if ball_on_top else [ball, title])
    p.apply([{"type": "timeline-set", "duration": 2000, "fps": 10},
             {"type": "keyframes", "target": "ball", "property": "x",
              "keys": [{"time": 0, "value": 0}, {"time": 1000, "value": 270}, {"time": 2000, "value": 0}]}])
    return p


def test_a_layer_moving_over_text_is_reported_with_its_times():
    found = codes(scene())
    item = found["moving-over-text"]
    assert item["text"] == "title" and 0 < item["times"][0] < item["times"][1] < 2000
    assert "moving-over-text" not in codes(scene(ball_on_top=False))


def test_text_hidden_for_most_of_a_loop_is_reported():
    p = Project(200, 100, "white")
    p.apply([{"type": "text", "name": "tag", "text": "Sale", "size": 20, "color": "black", "x": 10, "y": 10},
             {"type": "timeline-set", "duration": 2000, "fps": 10},
             {"type": "keyframes", "target": "tag", "property": "opacity",
              "keys": [{"time": 0, "value": 0, "easing": "hold"}, {"time": 1500, "value": 1, "easing": "hold"},
                       {"time": 2000, "value": 0}]}])
    item = codes(p)["text-mostly-hidden"]
    assert "75%" in item["message"]
    p.apply({"type": "timeline-set", "loop": 1})
    assert "text-mostly-hidden" not in codes(p)


def test_parts_that_start_on_one_centre_and_drift_apart():
    p = Project(200, 200, "white")
    p.apply([{"type": "shape", "name": "eye", "shape": "ellipse", "width": 40, "height": 40, "x": 80, "y": 80, "fill": "white", "stroke": "black"},
             {"type": "shape", "name": "pupil", "shape": "ellipse", "width": 10, "height": 10, "x": 95, "y": 95, "fill": "black"},
             {"type": "group", "name": "face", "targets": ["eye", "pupil"]},
             {"type": "timeline-set", "duration": 1000, "fps": 10},
             {"type": "keyframes", "target": "pupil", "property": "translate-x",
              "keys": [{"time": 0, "value": 0}, {"time": 500, "value": 30}, {"time": 1000, "value": 0}]}])
    item = codes(p)["parts-drift"]
    assert {item["other"], "pupil", "eye"} == {"pupil", "eye"} and "30 px apart" in item["message"]


def test_rendered_seam_compares_the_last_and_first_frames():
    p = Project(120, 80, "white")
    p.apply([{"type": "shape", "name": "box", "shape": "rectangle", "width": 30, "height": 30, "x": 0, "y": 20, "fill": "blue"},
             {"type": "timeline-set", "duration": 1000, "fps": 10},
             {"type": "keyframes", "target": "box", "property": "x", "keys": [{"time": 0, "value": 0}, {"time": 1000, "value": 90}]}])
    timeline = p.state["timeline"]
    jump = rendered_seam_findings(p, timeline)
    assert jump and jump[0]["code"] == "loop-seam-render" and jump[0]["seam_difference"] > jump[0]["frame_difference"]
    p.apply({"type": "keyframes", "target": "box", "property": "x", "keys": [{"time": 500, "value": 90}, {"time": 1000, "value": 0}]})
    assert not rendered_seam_findings(p, p.state["timeline"])


def test_sampling_is_bounded():
    assert len(_sample_times({"duration": 600_000})) == MAX_SAMPLES
    assert _sample_times({"duration": 1000})[:3] == [0, 100, 200]


def test_gif_export_reports_the_loop_seam(tmp_path):
    p = Project(100, 60, "white")
    p.apply([{"type": "shape", "name": "dot", "shape": "ellipse", "width": 10, "height": 10, "x": 0, "y": 20, "fill": "red"},
             {"type": "timeline-set", "duration": 500, "fps": 10},
             {"type": "keyframes", "target": "dot", "property": "x", "keys": [{"time": 0, "value": 0}, {"time": 500, "value": 80}]}])
    result = export_timeline(p, tmp_path / "dot.gif")
    assert any(w.startswith("Loop seam") for w in result["warnings"])
    part = export_timeline(p, tmp_path / "part.gif", start=100, end=400)
    assert not any(w.startswith("Loop seam") for w in part.get("warnings", []))
