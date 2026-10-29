"""Per-occurrence lyric layouts remain editable and reproduce their source text."""

import shutil
import wave

import pytest

from vixl import Project
from vixl.plugins.lyrics.lyrics import build
from vixl.plugins.lyrics.verification import review, verify
from vixl.timeline import project_at

pytestmark = pytest.mark.skipif(not (shutil.which("ffmpeg") and shutil.which("ffprobe")), reason="ffmpeg needed")


@pytest.fixture
def source(tmp_path):
    with wave.open(str(tmp_path / "song.wav"), "wb") as audio:
        audio.setparams((1, 2, 8000, 0, "NONE", "not compressed"))
        audio.writeframes(b"\0\0" * 8000 * 12)
    (tmp_path / "song.lrc").write_text("[00:00.500][Verse]\n[00:00.500]One line\n[00:02.000]Another line\n"
                                      "[00:04.000][Chorus]\n[00:04.000]A setup | a payoff\n[00:06.000]Bright flame\n"
                                      "[00:08.000][Chorus]\n[00:08.000]A setup | a payoff\n[00:10.000]Bright flame\n")
    project = Project(320, 180, "black")
    project.apply([{"type": "text", "name": "lyric", "text": "Placeholder", "size": 16, "color": "white", "x": 16, "y": 20},
                   {"type": "text-layout", "target": "lyric", "width": 288, "height": 120}])
    project.save(tmp_path / "template.vixl")
    return tmp_path, {"audio": "song.wav", "lyrics": "song.lrc", "template": "template.vixl", "build": "built.vixl"}


def test_choruses_choose_deterministic_variants_and_keep_text(source):
    root, request = source
    rules = [{"match": {"contains": "setup"}, "variant": [
        {"layout": {"kind": "stack", "fit": {"min_size": 10, "max_size": 32}}},
        {"layout": {"kind": "setup-payoff", "fit": {"min_size": 10, "max_size": 32}}}], "assign": "cycle"}]
    report = build({**request, "compositions": rules}, root)
    built = Project.load(root / "built.vixl")
    first, second = report["lines"][2], report["lines"][4]
    assert first["composition"]["variant"] == "stack"
    assert second["composition"]["variant"] == "setup-payoff"
    assert [first["composition"]["occurrence"], second["composition"]["occurrence"]] == [1, 2]
    frame = project_at(built, first["settled"])
    assert frame.layer(first["composition"]["group"])["visible"]
    assert not frame.layer("lyric")["visible"]
    assert not frame.layer(second["composition"]["group"])["visible"]
    report_check = verify(report, built, media={"passed": True, "status": "passed"})
    assert report_check["structural"]["passed"], [c for c in report_check["structural"]["checks"] if not c.get("passed")]
    assert not built.check(checks=["bounds"])["errors"]
    again = build({**request, "build": "again.vixl", "compositions": rules}, root)
    assert [line.get("composition", {}).get("variant") for line in report["lines"]] == [
        line.get("composition", {}).get("variant") for line in again["lines"]]


def test_approved_cue_style_overrides_survive_rebuild(source):
    root, request = source
    request = {**request, "compositions": [{"match": {"cue": 2}, "layout": {"kind": "stack"}}]}
    report = build(request, root)
    built = Project.load(root / "built.vixl")
    ident = report["lines"][2]["composition"]["text_layers"][0]
    built.apply({"type": "text-set", "target": ident, "color": "#ff8800"})
    built.save(root / "built.vixl")
    review({"build": "built.vixl", "approve": True}, root)
    (root / "song.lrc").write_text((root / "song.lrc").read_text().replace("[00:04.000]", "[00:04.100]"))
    rebuilt = build({**request, "rebuild": True}, root)
    updated = Project.load(root / "built.vixl")
    new_id = rebuilt["lines"][2]["composition"]["text_layers"][0]
    assert updated.layer(new_id)["color"] == "#ff8800"
    assert updated.state["lyric_build"]["overrides"][new_id]["fields"]["color"] == "#ff8800"
    assert "review" not in updated.state["lyric_build"]
    rebuilt_again = build({**request, "rebuild": True}, root)
    again = Project.load(root / "built.vixl")
    assert again.layer(rebuilt_again["lines"][2]["composition"]["text_layers"][0])["color"] == "#ff8800"


def test_cue_preview_reuses_built_timing(source):
    from vixl.plugins.lyrics.compositions import preview
    root, request = source
    build(request, root)
    result = preview({"build": "built.vixl", "cue": 2, "output": "cue.png"}, root)
    assert (root / "cue.png").is_file()
    assert result


def test_group_variant_attachment_and_bounded_part_motion(source):
    root, request = source
    template = Project.load(root / "template.vixl")
    template.apply([
        {"type": "shape", "shape": "ellipse", "name": "badge-part", "x": 0, "y": 0, "width": 8, "height": 8, "fill": "orange"},
        {"type": "group", "name": "badge", "targets": ["badge-part"]},
        {"type": "object", "target": "badge", "kind": "guitar"},
        {"type": "object-save", "target": "badge", "name": "badge"},
        {"type": "remove", "target": "badge"},
        {"type": "text", "name": "variant-text", "text": "Placeholder", "size": 20, "color": "white", "x": 20, "y": 30},
        {"type": "text-layout", "target": "variant-text", "width": 230, "height": 70},
        {"type": "shape", "shape": "ellipse", "name": "flame", "x": 20, "y": 120, "width": 15, "height": 15, "fill": "orange"},
        {"type": "group", "name": "hero", "targets": ["variant-text", "flame"]},
    ])
    template.save(root / "template.vixl")
    request = {**request, "compositions": [{"match": {"cue": 3}, "variant": "hero",
        "layout": {"fit": {"min_size": 10, "max_size": 24}},
        "attach": {"symbol": "badge", "to": "baseline", "gap": 3},
        "motion": {"parts": {"flame": {"preset": "flicker", "amplitude": 2}}, "span": "cue"}}]}
    result = build(request, root)
    built = Project.load(root / "built.vixl")
    cue = result["lines"][3]
    motion = next(track for track in built.state["timeline"]["tracks"] if track["target"] == built.layer("composition-0003/flame")["id"])
    assert all(abs(key["value"]) <= 2 for key in motion["keys"])
    assert built.layer("composition-0003/attachment")["parent"] == cue["composition"]["group"]
    from vixl.render import resolve_layout, resolved_layers
    from vixl.text_metrics import inspect_text
    from vixl.checks import group_matrix
    resolved = resolved_layers(built)
    index = {layer["id"]: layer for layer in resolved}
    bounds = resolve_layout(built, layers=resolved)
    text = index[cue["composition"]["text_layers"][0]]
    metrics = inspect_text(built, text, bounds[text["id"]])
    baseline = (group_matrix(text, index, bounds) @ [0, metrics["baselines"][-1], 1])[1]
    attachment = index[built.layer("composition-0003/attachment")["id"]]
    ax, ay, aw, ah = bounds[attachment["id"]]
    bottom = (group_matrix(attachment, index, bounds) @ [ax, ay + ah, 1])[1]
    assert abs(bottom - baseline) <= 1


def test_reused_exports_keep_composition_verification(source):
    from vixl.plugins.lyrics.lyrics import export
    root, request = source
    request = {**request, "fps": 4, "check": False, "compositions": [{"match": {"cue": 2}, "layout": {"kind": "stack"}}]}
    build(request, root)
    first = export({**request, "output": "first.mp4"}, root)
    second = export({**request, "output": "second.mp4"}, root)
    assert first["build_reused"] and second["build_reused"]
    assert first["verification"]["structural"]["passed"]
    assert second["verification"]["structural"]["passed"]


def test_composition_restores_matching_section_variant(source):
    root, request = source
    source_text = (root / "song.lrc").read_text().replace("[Chorus]", "[Chorus 2]", 1)
    (root / "song.lrc").write_text(source_text)
    template = Project.load(root / "template.vixl")
    template.apply({"type": "duplicate", "target": "lyric", "name": "lyric-chorus"})
    template.save(root / "template.vixl")
    result = build({**request, "compositions": [{"match": {"cue": 2}, "layout": {"kind": "stack"}}]}, root)
    frame = project_at(Project.load(root / "built.vixl"), result["lines"][3]["settled"])
    assert frame.layer("lyric-chorus")["visible"]
    assert not frame.layer("lyric")["visible"]


def test_approved_optional_field_removal_survives_rebuild(source):
    root, request = source
    request = {**request, "compositions": [{"match": {"cue": 2}, "layout": {"kind": "stack"}}]}
    result = build(request, root)
    built = Project.load(root / "built.vixl")
    ident = result["lines"][2]["composition"]["text_layers"][0]
    built.layer(ident).pop("text_layout")
    built.save(root / "built.vixl")
    review({"build": "built.vixl", "approve": True}, root)
    rebuilt = build({**request, "rebuild": True}, root)
    updated = Project.load(root / "built.vixl")
    ident = rebuilt["lines"][2]["composition"]["text_layers"][0]
    assert "text_layout" not in updated.layer(ident)
    assert "text_layout" in updated.state["lyric_build"]["overrides"][ident]["remove"]
