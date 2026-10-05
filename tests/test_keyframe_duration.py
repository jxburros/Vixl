"""A keyframe past the timeline end: the duration grows, the result says so, and a duration set back sticks."""

import json

from vixl import Project
from vixl.timeline import project_at


def doc():
    p = Project(100, 100, "white")
    p.apply([{"type": "solid", "name": "bar", "color": "red", "width": 20, "height": 10},
             {"type": "text", "name": "words", "text": "hi", "size": 12},
             {"type": "timeline-set", "duration": 8000}])
    return p


def duration(p):
    return p.state["timeline"]["duration"]


def test_key_past_the_end_extends_and_reports_it():
    p = doc()
    result = p.apply({"type": "keyframe", "target": "bar", "property": "opacity", "time": 8400, "value": 0})
    assert duration(p) == 8400
    assert len(result["warnings"]) == 1 and "timeline duration changed 8000 -> 8400 ms" in result["warnings"][0]
    assert "'bar'" in result["warnings"][0]
    # Nothing is reported while keys stay inside the timeline.
    inside = p.apply({"type": "keyframe", "target": "bar", "property": "opacity", "time": 100, "value": 1})
    assert "warnings" not in inside and duration(p) == 8400


def test_animate_and_presets_report_the_growth():
    for operation, end in (
        ({"type": "animate", "target": "bar", "property": "x", "from": 0, "to": 9, "start": 7000, "duration": 2000}, 9000),
        ({"type": "animate-preset", "target": "bar", "preset": "fade-in", "start": 7800, "duration": 600}, 8400),
        ({"type": "animate-preset", "target": "words", "preset": "typewriter", "start": 7800, "duration": 600}, 8400),
    ):
        p = doc()
        result = p.apply(operation)
        assert duration(p) == end
        assert f"8000 -> {end} ms" in result["warnings"][0]


def test_a_duration_set_back_is_not_stretched_again_by_old_keys():
    p = doc()
    p.apply({"type": "keyframe", "target": "bar", "property": "x", "time": 8667, "value": 40})
    assert duration(p) == 8667
    result = p.apply({"type": "timeline-set", "duration": 8000})
    assert duration(p) == 8000 and "past the timeline end (8000 ms)" in result["warnings"][0]
    # The key past the end is still there; a later edit elsewhere must not lengthen the timeline.
    later = p.apply({"type": "keyframe", "target": "bar", "property": "opacity", "time": 1000, "value": 0.5})
    assert duration(p) == 8000 and "warnings" not in later
    keys = [k["time"] for t in p.state["timeline"]["tracks"] if t["property"] == "x" for k in t["keys"]]
    assert keys == [8667]


def test_extend_false_keeps_the_duration_and_the_key():
    p = doc()
    p.apply({"type": "keyframe", "target": "bar", "property": "x", "time": 0, "value": 0})
    result = p.apply({"type": "keyframe", "target": "bar", "property": "x", "time": 8667, "value": 80, "extend": False})
    assert duration(p) == 8000
    assert "past the timeline end (8000 ms)" in result["warnings"][0] and "duration changed" not in result["warnings"][0]
    # The last played frame is still on its way to the key past the end.
    assert 0 < project_at(p, 7999).layer("bar")["x"] < 80
    # animate takes the flag too, and a key inside the timeline needs no note.
    inside = p.apply({"type": "animate", "target": "bar", "property": "opacity", "to": 0, "start": 0, "end": 7000, "extend": False})
    assert "warnings" not in inside


def test_shared_targets_and_batches_report_each_growth():
    p = doc()
    result = p.apply([
        {"type": "keyframe", "targets": ["bar", "words"], "property": "x", "time": 8200, "value": 3},
        {"type": "keyframe", "target": "bar", "property": "y", "time": 9000, "value": 3},
    ])
    assert duration(p) == 9000
    assert [w.split(":")[0] for w in result["warnings"]] == [
        "timeline duration changed 8000 -> 8200 ms", "timeline duration changed 8200 -> 9000 ms"]


def test_dry_run_reports_without_committing():
    p = doc()
    result = p.apply({"type": "keyframe", "target": "bar", "property": "x", "time": 8400, "value": 3}, dry_run=True)
    assert "8000 -> 8400" in result["warnings"][0] and duration(p) == 8000
    assert not hasattr(p, "notices")


def test_schema_documents_extend_and_cli_flag(tmp_path, monkeypatch, capsys):
    from vixl.cli import main
    from vixl.schema import operation_schema

    variants = operation_schema()["properties"]["operations"]["items"]["oneOf"]
    for name in ("keyframe", "animate", "animate-preset"):
        schema = next(v for v in variants if v["properties"]["type"]["const"] == name)
        assert "8000 -> 8400" in schema["properties"]["extend"]["description"]
    monkeypatch.chdir(tmp_path)
    assert main(["new", "40x40", "-o", "d.vixl"]) == 0
    assert main(["solid", "--name", "bar"]) == 0
    assert main(["timeline", "set", "--duration", "2s"]) == 0
    capsys.readouterr()
    assert main(["keyframe", "bar", "opacity", "3s", "0"]) == 0
    assert "timeline duration changed 2000 -> 3000 ms" in json.loads(capsys.readouterr().out)["warnings"][0]
    assert main(["keyframe", "bar", "opacity", "5s", "0", "--no-extend"]) == 0
    assert "past the timeline end (3000 ms)" in json.loads(capsys.readouterr().out)["warnings"][0]
    assert Project.load(tmp_path / "d.vixl").state["timeline"]["duration"] == 3000
