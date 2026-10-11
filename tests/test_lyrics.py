"""Lyric video workflow: LRC parsing, timing, the generated timeline, export and surfaces."""

import json
import shutil
import subprocess
import wave

import pytest

from vixl import Project
from vixl.errors import VixlError
from vixl.lyrics import background_for, build, parse_lrc, timing, validate_template

needs_ffmpeg = pytest.mark.skipif(not (shutil.which("ffmpeg") and shutil.which("ffprobe")), reason="ffmpeg not installed")

LRC = """[ti:Streetlights]
[ar:Example Artist]
[al:Night Drive]

[00:01.00]Streetlights hum like they know my name
[00:03.50]Every window's got a different flame
[00:05.30][Chorus]
[00:05.30]And I keep on driving
[00:07.80]
[00:08.10][00:09.40]This line repeats in the fire
"""


def write_audio(path, seconds=12, rate=8000):
    with wave.open(str(path), "wb") as audio:
        audio.setparams((1, 2, rate, 0, "NONE", "not compressed"))
        audio.writeframes(b"\0\0" * int(rate * seconds))


def template(path, **extra):
    p = Project(160, 90, "#101018")
    p.apply([
        {"type": "variable", "name": "title", "value": "T"},
        {"type": "solid", "name": "bg-default", "color": "#203040"},
        {"type": "solid", "name": "bg-chorus", "color": "#602030"},
        {"type": "text", "name": "intro", "text": "${title}", "size": 12, "color": "white", "x": 10, "y": 10},
        {"type": "text", "name": "lyric", "text": "Lyric", "size": 12, "color": "white", "x": 8, "y": 30},
        {"type": "text-layout", "target": "lyric", "width": 144, "height": 36, "fit": True},
        {"type": "text", "name": "lyric-next", "text": "next", "size": 8, "color": "#aaaaaa", "x": 8, "y": 72},
        {"type": "text", "name": "section-label", "text": "S", "size": 8, "color": "white", "x": 8, "y": 2},
        {"type": "shape", "shape": "star", "name": "cue-fire", "width": 16, "height": 16, "x": 140, "y": 2, "fill": "orange"},
        *extra.get("operations", []),
    ])
    p.save(path, overwrite=True)
    return p


@pytest.fixture
def workspace(tmp_path):
    (tmp_path / "song.lrc").write_text(LRC, encoding="utf-8")
    write_audio(tmp_path / "song.wav")
    template(tmp_path / "style.vixl")
    return tmp_path


def request(**extra):
    return {"audio": "song.wav", "lyrics": "song.lrc", "template": "style.vixl", **extra}


# Parser --------------------------------------------------------------------------------------


def test_parser_reads_timestamps_tags_sections_and_breaks():
    parsed = parse_lrc(LRC)
    assert parsed["metadata"] == {"title": "Streetlights", "artist": "Example Artist", "album": "Night Drive"}
    times = [(line["time"], line["text"]) for line in parsed["lines"]]
    assert times[0] == (1000, "Streetlights hum like they know my name")
    # Two timestamps before one text expand into two lines; an empty text is a break.
    assert (7800, "") in times and (8100, "This line repeats in the fire") in times
    assert (9400, "This line repeats in the fire") in times
    assert parsed["sections"] == [{"time": 5300, "label": "Chorus", "name": "chorus", "source_line": 7}]


def test_parser_fractions_long_minutes_offsets_words_bom_and_crlf():
    text = "﻿[offset:-250]\r\n[75:01.5]a\r\n[00:02.25]b\r\n[00:03.125]<00:03.20>c <00:03.60>d\r\n[00:04.00][Verse 2]\r\n"
    parsed = parse_lrc(text.encode("utf-8"))
    assert parsed["offset"] == -250
    lines = {line["text"]: line for line in parsed["lines"]}
    assert lines["b"]["time"] == 2250 and lines["a"]["time"] == 75 * 60_000 + 1500
    assert lines["c d"]["time"] == 3125
    assert lines["c d"]["words"] == [{"time": 3200, "text": "c"}, {"time": 3600, "text": "d"}]
    assert parsed["sections"][0]["name"] == "verse-2"
    assert [line["text"] for line in parsed["lines"]] == ["b", "c d", "a"]


def test_parser_warns_about_unknown_tags():
    parsed = parse_lrc("[by:me]\n[00:01.00]hi\n")
    assert parsed["warnings"][0]["code"] == "unknown_tag" and parsed["warnings"][0]["source_line"] == 1


@pytest.mark.parametrize(
    "text, code, line",
    [
        ("[00:01.00]ok\nno timestamp here\n", "lrc_parse", 2),
        ("[00:01.00]ok\n[0x:01.00]bad\n", "lrc_parse", 2),
        ("[00:01.00]one\n[00:01.00]two\n", "lrc_conflict", 2),
        ("[ti:Only tags]\n[00:01.00]\n", "lrc_empty", None),
    ],
)
def test_parser_errors_carry_codes_and_lines(text, code, line):
    with pytest.raises(VixlError) as error:
        parse_lrc(text)
    assert error.value.code == code
    assert error.value.details.get("source_line") == line


def test_positive_offset_shows_lyrics_earlier():
    parsed = parse_lrc("[offset:+500]\n[00:02.00]x\n")
    result = timing(parsed, {"lead": 0}, 10_000)
    assert result["lines"][0]["start"] == 1500
    later = timing(parse_lrc("[00:02.00]x\n"), {"lead": 0, "offset": -300}, 10_000)
    assert later["lines"][0]["start"] == 2300


# Timing --------------------------------------------------------------------------------------


def test_timing_lead_gap_hold_and_last_line():
    parsed = parse_lrc("[00:01.00]a\n[00:03.00]b\n[00:20.00]c\n")
    lines = timing(parsed, {"lead": 200, "gap": 100, "max_hold": 5000}, 30_000)["lines"]
    a, b, c = lines
    assert (a["show"], a["hide"]) == (800, 2700)        # hides gap before b shows (3000 - 200 - 100)
    assert (b["show"], b["hide"]) == (2800, 8000)       # max_hold ends it long before c
    assert (c["show"], c["hide"]) == (19800, 25000)     # the last line also stops at max_hold
    short = timing(parsed, {"max_hold": 60000}, 22_000)["lines"]
    assert short[-1]["hide"] == 22_000                  # or at the end of the video


def test_timing_breaks_clamping_sections_and_windows():
    parsed = parse_lrc(LRC)
    result = timing(parsed, {"lead": 150}, 12_000)
    lines = result["lines"]
    driving = next(line for line in lines if line["text"] == "And I keep on driving")
    assert driving["hide"] == 7800 and driving["section"] == "chorus"
    assert lines[0]["section"] is None
    assert result["sections"] == [{"label": "Chorus", "name": "chorus", "source_line": 7, "start": 5300, "end": 12_000}]
    clamped = timing(parse_lrc("[00:01.00]a\n[00:01.01]b\n"), {"lead": 0, "gap": 50}, 5_000)
    a, b = clamped["lines"]
    assert a["hide"] > a["show"] and b["show"] >= a["hide"]
    window = timing(parsed, {"start": 3000, "end": 6000}, 12_000)
    assert (window["start"], window["end"]) == (3000, 6000)
    with pytest.raises(VixlError) as error:
        timing(parsed, {}, 4_000)
    assert error.value.code == "lyrics_beyond_audio"


def test_short_lines_warn_and_lead_clamp_warns():
    parsed = parse_lrc("[00:01.00]a\n[00:01.20]b\n[00:05.00]c\n")
    result = timing(parsed, {"lead": 150, "animation": {"duration": 300}}, 9_000)
    assert any(w["code"] == "short_line" for w in result["warnings"])


# Template contract ---------------------------------------------------------------------------


def test_template_validation(tmp_path):
    p = Project(50, 50)
    assert validate_template(p)["errors"][0]["code"] == "template_invalid"
    p.apply([{"type": "solid", "name": "lyric"}])
    assert "must be a text layer" in validate_template(p)["errors"][0]["message"]
    q = Project(50, 50)
    q.apply([
        {"type": "text", "name": "lyric", "text": "x"},
        {"type": "solid", "name": "lyric-next"},
        {"type": "solid", "name": "bg-Bad_Name"},
    ])
    messages = " ".join(e["message"] for e in validate_template(q)["errors"])
    assert "lyric-next" in messages and "bg-Bad_Name" in messages
    r = Project(50, 50)
    r.apply([{"type": "text", "name": "lyric", "text": "x"}, {"type": "solid", "name": "bg-verse"}])
    report = validate_template(r, [{"name": "verse-2"}, {"name": "bridge"}])
    assert [w["section"] for w in report["warnings"]] == ["bridge"]
    assert background_for({"verse": 1, "default": 2}, "verse-2") == "verse"
    assert background_for({"default": 2}, "bridge") == "default"


# Build ---------------------------------------------------------------------------------------


@needs_ffmpeg
def test_build_writes_an_editable_timeline(workspace):
    from vixl.timeline import project_at

    report = build(request(build="song-lyrics.vixl"), workspace)
    assert report["build"] == "song-lyrics.vixl" and report["frames"] == 288
    project = Project.load(workspace / "song-lyrics.vixl")
    assert project.state["variables"]["title"] == "Streetlights"
    timeline = project.state["timeline"]
    names = {layer["id"]: layer["name"] for layer in project.state["layers"]}
    tracks = {(names[t["target"]], t["property"]): t["keys"] for t in timeline["tracks"]}
    first = report["lines"][0]
    text_keys = {k["time"]: k["value"] for k in tracks[("lyric", "text")]}
    assert text_keys[0] == "" and text_keys[first["show"]] == first["text"]
    assert [k["value"] for k in tracks[("lyric-next", "text")]][1] == report["lines"][1]["text"]
    assert {k["time"]: k["value"] for k in tracks[("section-label", "text")]}[5300] == "Chorus"
    assert {k["time"]: k["value"] for k in tracks[("intro", "visible")]} == {0: True, first["show"]: False}
    assert "chorus-1" in timeline["markers"] and "line-001" in timeline["markers"]

    def at(time):
        frame = project_at(project, time)
        return {layer["name"]: layer for layer in frame.state["layers"]}

    assert at(500)["intro"]["visible"] and at(500)["lyric"]["opacity"] == 0
    middle = at(first["show"] + 1000)
    assert middle["lyric"]["text"] == first["text"] and middle["lyric"]["opacity"] == 1
    assert middle["bg-default"]["visible"] and not middle["bg-chorus"]["visible"]
    chorus = at(6000)
    assert chorus["bg-chorus"]["visible"] and not chorus["bg-default"]["visible"]
    assert chorus["lyric"]["text"] == "And I keep on driving" and not chorus["cue-fire"]["visible"]
    assert at(7900)["lyric"]["opacity"] == 0   # the instrumental break hides the lyric
    assert at(8600)["cue-fire"]["visible"]      # cue layers follow the words being sung
    # Re-running refuses to overwrite unless asked.
    with pytest.raises(VixlError):
        build(request(build="song-lyrics.vixl"), workspace)
    assert build(request(build="song-lyrics.vixl", replace=True), workspace)["build"]


@needs_ffmpeg
def test_long_line_rewraps_inside_its_fitted_box(workspace):
    from vixl.timeline import project_at

    (workspace / "long.lrc").write_text("[00:01.00]" + "a very long lyric line that cannot fit on one row " * 3 + "\n")
    report = build(request(lyrics="long.lrc", build="long.vixl", animation={"in": "none", "out": "none"}), workspace)
    project = Project.load(workspace / "long.vixl")
    frame = project_at(project, report["lines"][0]["show"] + 10)
    layer = frame.layer("lyric")
    assert layer["text"].startswith("a very long")
    box = frame.inspect("lyric")["resolved_bounds"]
    from vixl.render import layer_image

    image = layer_image(frame, layer, box)
    ink = image.getchannel("A").getbbox()
    assert ink and ink[2] <= box[2] and ink[3] <= box[3]


@needs_ffmpeg
def test_cut_and_slide_animations(workspace):
    from vixl.timeline import project_at

    report = build(request(build="cut.vixl", animation={"in": "slide-up", "out": "none", "duration": 200}), workspace)
    project = Project.load(workspace / "cut.vixl")
    line = report["lines"][1]
    start = {layer["name"]: layer for layer in project_at(project, line["show"] + 20).state["layers"]}
    settled = {layer["name"]: layer for layer in project_at(project, line["show"] + 400).state["layers"]}
    assert start["lyric"]["y"] > settled["lyric"]["y"]
    # A cut holds full opacity until the hide time, then drops to zero.
    before = {layer["name"]: layer for layer in project_at(project, line["hide"] - 5).state["layers"]}
    assert before["lyric"]["opacity"] == 1


# Export, frame cap and surfaces --------------------------------------------------------------


@needs_ffmpeg
def test_export_draft_mp4_with_audio(workspace):
    from vixl.lyrics import export

    result = export(request(build="b.vixl", output="song.mp4", quality="draft", fps=8, start=1000, end=4000, check=True), workspace)
    assert result["video"]["frames"] == 24
    probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,duration", "-of", "json",
                            str(workspace / "song.mp4")], capture_output=True, check=True)
    streams = json.loads(probe.stdout)["streams"]
    assert {s["codec_type"] for s in streams} == {"video", "audio"}
    assert abs(float(next(s for s in streams if s["codec_type"] == "video")["duration"]) - 3.0) < 0.2
    assert result["checks"]["checked_lines"] >= 1


@needs_ffmpeg
def test_streamed_video_has_no_3600_frame_cap(tmp_path):
    from vixl.film import export as film_export, plan as film_plan

    p = Project(16, 16, "black")
    p.apply([{"type": "solid", "name": "dot", "color": "white", "width": 4, "height": 4},
             {"type": "animate", "target": "dot", "property": "x", "to": 12, "duration": 61_000}])
    p.save(tmp_path / "long.vixl")
    spec = {"width": 16, "height": 16, "fps": 60, "quality": "draft", "shots": [{"source": "long.vixl", "duration": 61_000}]}
    with pytest.raises(VixlError) as error:
        film_plan(spec)
    assert error.value.code == "resource_limit"
    assert film_plan(spec, streamed=True)["frames"] == 3660
    assert film_export(spec, tmp_path, tmp_path / "long.mp4")["frames"] == 3660
    with pytest.raises(VixlError) as error:
        p.state["timeline"]["fps"] = 60
        from vixl.timeline import export_timeline
        export_timeline(p, tmp_path / "long.gif")
    assert error.value.code == "resource_limit"


@needs_ffmpeg
def test_workflow_rest_and_job_surfaces(workspace):
    from fastapi.testclient import TestClient
    from vixl.interfaces import Session, create_app
    from vixl.jobs import Queue
    from vixl.workflows import describe, dispatch

    actions = describe()["actions"]
    assert {"lyric-video-plan", "lyric-video-build", "lyric-video-export"} <= set(actions)
    assert "build" in actions["lyric-video-build"]["required"]
    session = Session(workspace=workspace)
    assert dispatch(session, "lyric-video-plan", request())["sections"][0]["name"] == "chorus"
    client = TestClient(create_app(workspace / "style.vixl"))
    response = client.post("/workflow/lyric-video-plan", json=request())
    assert response.status_code == 200 and response.json()["lines"]
    assert client.post("/workflow/lyric-video-export", json=request(build="x.vixl", output="x.mp4")).status_code == 403

    queue = Queue(workspace)
    job = queue.submit({"kind": "lyric-video", "output": "job.mp4",
                        "request": request(build="job.vixl", quality="draft", fps=4, end=3000)})
    (workspace / "song.lrc").write_text("[00:01.00]changed after submit\n")
    done = queue.work_one(job["id"])
    assert done["status"] == "completed", done
    assert (workspace / "job.mp4").exists() and (workspace / "job.vixl").exists()
    built = Project.load(workspace / "job.vixl")
    texts = [k["value"] for t in built.state["timeline"]["tracks"] if t["property"] == "text" for k in t["keys"]]
    assert "Streetlights hum like they know my name" in texts
    cancelled = queue.submit({"kind": "lyric-video", "output": "never.mp4", "request": request(build="never.vixl")})
    queue.cancel(cancelled["id"])
    assert queue.work_one(cancelled["id"])["status"] == "cancelled"


# Breaks, repeated lines, cue animation and rebuilding ------------------------------------------


def frame(project, time):
    from vixl.timeline import project_at

    return {layer["name"]: layer for layer in project_at(project, time).state["layers"]}


def keys(project, name, prop):
    ident = project.layer(name)["id"]
    track = next((t for t in project.state["timeline"]["tracks"] if t["target"] == ident and t["property"] == prop), None)
    return [(k["time"], k["value"]) for k in track["keys"]] if track else []


@needs_ffmpeg
def test_empty_timestamp_clears_the_next_line_preview(workspace):
    report = build(request(build="b.vixl", lead=0, animation={"duration": 200}), workspace)
    driving = next(line for line in report["lines"] if line["text"] == "And I keep on driving")
    assert driving["break_at"] == 7800 and driving["hide"] == 7800
    built = Project.load(workspace / "b.vixl")
    # Before the break the preview shows the line after it; during the break nothing does.
    assert frame(built, 6000)["lyric-next"]["text"] == "This line repeats in the fire"
    assert frame(built, 7000)["lyric-next"]["opacity"] == 1
    assert 0 < frame(built, 7700)["lyric-next"]["opacity"] < 1  # it fades out with the lyric
    for time in (7800, 7900, 8000):
        assert frame(built, time)["lyric"]["opacity"] == 0
        assert frame(built, time)["lyric-next"]["text"] == ""
    # It returns with the first line after the break, previewing the line after that.
    assert frame(built, 8100)["lyric"]["text"] == "This line repeats in the fire"
    assert frame(built, 8100)["lyric-next"]["opacity"] < 0.01
    assert frame(built, 8400)["lyric-next"]["opacity"] == 1 and frame(built, 8400)["lyric-next"]["text"] == "This line repeats in the fire"
    # A cut (no animations) clears the text alone.
    cut = build(request(build="cut.vixl", lead=0, animation={"in": "none", "out": "none"}), workspace)
    assert cut["lines"][2]["break_at"] == 7800
    plain = Project.load(workspace / "cut.vixl")
    assert frame(plain, 7900)["lyric-next"]["text"] == "" and keys(plain, "lyric-next", "opacity") == []
    # The preview still clears at the empty timestamp when max_hold hid the line earlier.
    held = build(request(build="held.vixl", lead=0, max_hold=1500), workspace)
    assert held["lines"][2]["hide"] == 6800 and held["lines"][2]["break_at"] == 7800


@needs_ffmpeg
def test_identical_consecutive_lines_hold_instead_of_fading_again(workspace):
    from vixl.lyrics import plan

    report = build(request(build="b.vixl", lead=100, animation={"duration": 200}), workspace)
    first, second = report["lines"][3], report["lines"][4]
    assert first["text"] == second["text"] and second["repeat"] and "repeat" not in first
    assert first["hide"] == second["show"]
    built = Project.load(workspace / "b.vixl")
    opacity = keys(built, "lyric", "opacity")
    # One entry at the first showing and one exit after the second: nothing in between dips to zero.
    between = [v for t, v in opacity if first["show"] + 200 <= t <= second["hide"] - 200]
    assert between and all(v == 1.0 for v in between)
    assert [v for t, v in keys(built, "lyric", "text") if first["show"] < t < second["hide"]] == []
    assert frame(built, second["show"])["lyric"]["opacity"] == 1 and frame(built, second["show"] - 1)["lyric"]["opacity"] == 1
    assert frame(built, second["hide"] - 20)["lyric"]["opacity"] < 1  # the exit comes after the repeat
    assert plan(request(lead=100), workspace)["lines"][4]["repeat"]
    # A gap between lines does not blank a repeated line; a break or max_hold between them still does.
    gapped = build(request(build="gap.vixl", lead=100, gap=300, animation={"duration": 200}), workspace)
    assert gapped["lines"][4]["repeat"] and gapped["lines"][3]["hide"] == gapped["lines"][4]["show"]
    (workspace / "r.lrc").write_text("[00:01.00]a\n[00:02.00]\n[00:03.00]a\n[00:06.00]b\n[00:09.00]b\n")
    split = build(request(lyrics="r.lrc", build="r.vixl", lead=0, max_hold=2000), workspace)
    assert [line.get("repeat", False) for line in split["lines"]] == [False, False, False, False]
    # Warnings count only the animation a line actually plays: the middle repeat plays none.
    (workspace / "s.lrc").write_text("[00:01.00]same\n[00:01.30]same\n[00:01.60]same\n[00:05.00]end\n")
    short = build(request(lyrics="s.lrc", build="s.vixl", lead=0, animation={"duration": 300}), workspace)
    assert not [w for w in short["warnings"] if w["code"] == "short_line" and w["index"] == 1]


@needs_ffmpeg
def test_cue_layers_can_fade_and_sweep(workspace):
    build(request(build="plain.vixl", lead=0), workspace)
    cut = Project.load(workspace / "plain.vixl")
    assert keys(cut, "cue-fire", "opacity") == [] and keys(cut, "cue-fire", "rotation") == []
    assert keys(cut, "cue-fire", "visible") == [(0, False), (8100, True), (12000, False)]
    cue = {"in": "fade-in", "out": "fade-out", "duration": 200, "motion": "sweep", "amount": 10, "period": 1000}
    build(request(build="cue.vixl", lead=0, cue_animation=cue), workspace)
    built = Project.load(workspace / "cue.vixl")
    assert keys(built, "cue-fire", "visible") == [(0, False), (8100, True), (12000, False)]  # one window for both lines
    opacity = keys(built, "cue-fire", "opacity")
    assert opacity[0] == (8100, 0.0) and (8300, 1.0) in opacity and (11800, 1.0) in opacity and opacity[-1] == (12000, 0.0)
    swing = keys(built, "cue-fire", "rotation")
    assert swing[0] == (8100, -10.0) and swing[1] == (8600, 10.0) and swing[2] == (9100, -10.0)
    assert swing[-1][0] == 12000 and -10 <= swing[-1][1] <= 10  # the last key is where the swing has got to
    assert frame(built, 8100)["cue-fire"]["opacity"] == 0 and frame(built, 8400)["cue-fire"]["opacity"] == 1
    assert frame(built, 8200)["cue-fire"]["visible"] and frame(built, 11500)["cue-fire"]["visible"]
    assert frame(built, 8350)["cue-fire"]["rotation"] != frame(built, 8850)["cue-fire"]["rotation"]
    # A cue shown again starts from rest, whatever the last exit left it at.
    build(request(build="slide.vixl", lead=0, cue_animation={"in": "none", "out": "slide-out-up", "duration": 200}), workspace)
    slide = Project.load(workspace / "slide.vixl")
    assert keys(slide, "cue-fire", "translate-y")[0] == (8100, 0.0)
    for bad, message in (
        ({"motion": "spin"}, "motion must be one of"),
        ({"in": "typewriter"}, "cue_animation.in"),
        ({"sparkle": 1}, "cue_animation takes"),
        ({"period": 50}, "period"),
    ):
        with pytest.raises(VixlError, match=message):
            build(request(build="bad.vixl", cue_animation=bad), workspace)


@needs_ffmpeg
def test_a_cut_entry_after_a_slide_out_starts_from_rest(workspace):
    report = build(request(build="b.vixl", lead=0, animation={"in": "none", "out": "slide-out-left", "duration": 200}), workspace)
    built = Project.load(workspace / "b.vixl")
    rest = built.layer("lyric")["x"]
    second = report["lines"][1]
    assert frame(built, second["show"] + 50)["lyric"]["x"] == rest
    assert frame(built, second["hide"] - 20)["lyric"]["x"] < rest


@needs_ffmpeg
def test_export_keeps_hand_edits_to_the_build(workspace):
    import numpy as np
    from PIL import Image

    from vixl.lyrics import export

    fields = dict(build="b.vixl", quality="draft", fps=4, start=1000, end=2000)
    first = export(request(**fields, output="one.mp4"), workspace)
    assert "build_reused" not in first and first["keyframes"] > 0
    built = Project.load(workspace / "b.vixl")
    record = built.state["lyric_build"]
    assert record["options"]["lead"] == 150 and record["options"]["fps"] == 4
    assert set(record["sources"]) == {"lyrics", "template", "audio_ms"}

    def pixel(video):
        out = workspace / "shot.png"
        out.unlink(missing_ok=True)
        subprocess.run(["ffmpeg", "-v", "error", "-i", str(workspace / video), "-frames:v", "1", str(out)], check=True)
        return np.asarray(Image.open(out).convert("RGB"))[2, 2]

    assert pixel("one.mp4")[0] < 80
    # Hand edit: the background goes red. The same request renders the edited document, even with
    # replace set for the video, and leaves the build file alone.
    built.apply({"type": "keyframe", "target": "bg-default", "property": "fill", "time": 0, "value": "#ff0000"})
    built.save(workspace / "b.vixl")
    before = (workspace / "b.vixl").read_bytes()
    second = export(request(**fields, output="two.mp4"), workspace)
    assert second["build_reused"] is True and any(w["code"] == "build_reused" for w in second["warnings"])
    assert (workspace / "b.vixl").read_bytes() == before
    assert pixel("two.mp4")[0] > 200
    third = export(request(**fields, output="two.mp4", replace=True), workspace)
    assert third["build_reused"] is True and pixel("two.mp4")[0] > 200
    # Settings that would change the build are refused instead of silently ignored, and no file changes.
    with pytest.raises(VixlError) as stale:
        export(request(**fields, output="three.mp4", lead=400, replace=True), workspace)
    assert stale.value.code == "build_stale" and stale.value.details["changed"] == ["lead"]
    assert not (workspace / "three.mp4").exists() and (workspace / "b.vixl").read_bytes() == before
    # Rendering choices that are not part of the build do not count.
    export(request(**fields, output="four.mp4", width=80, height=45), workspace)
    # rebuild: true builds it again from the template, discarding the edit.
    again = export(request(**fields, output="five.mp4", lead=400, rebuild=True), workspace)
    assert "build_reused" not in again and pixel("five.mp4")[0] < 80
    assert Project.load(workspace / "b.vixl").state["lyric_build"]["options"]["lead"] == 400


@needs_ffmpeg
def test_export_rebuilds_an_unedited_or_unrecorded_build_only_when_allowed(workspace):
    from vixl.lyrics import export

    fields = dict(build="b.vixl", quality="draft", fps=4, start=1000, end=2000)
    export(request(**fields, output="a.mp4"), workspace)
    # Unedited and still matching: reused, quietly.
    same = export(request(**fields, output="b.mp4"), workspace)
    assert same["build_reused"] is True and not any(w["code"] == "build_reused" for w in same["warnings"])
    # Unedited but the settings changed: a rebuild needs replace (or rebuild), as before.
    with pytest.raises(VixlError, match="already exists"):
        export(request(**fields, output="c.mp4", lead=300), workspace)
    changed = export(request(**fields, output="c.mp4", lead=300, replace=True), workspace)
    assert "build_reused" not in changed
    assert Project.load(workspace / "b.vixl").state["lyric_build"]["options"]["lead"] == 300
    # A build with no record (made by an earlier version) is rebuilt only with replace.
    legacy = Project.load(workspace / "b.vixl")
    del legacy.state["lyric_build"]
    legacy.save(workspace / "b.vixl")
    with pytest.raises(VixlError, match="already exists"):
        export(request(**fields, output="d.mp4", lead=300), workspace)
    assert "build_reused" not in export(request(**fields, output="d.mp4", lead=300, replace=True), workspace)
    # Changing the lyrics file also makes a build stale.
    (workspace / "song.lrc").write_text(LRC.replace("flame", "fire"), encoding="utf-8")
    with pytest.raises(VixlError, match="already exists"):
        export(request(**fields, output="e.mp4", lead=300), workspace)


@needs_ffmpeg
def test_build_record_tracks_edits_and_the_workflow_schema_lists_the_new_fields(workspace):
    from vixl.lyrics import _fingerprint, plan
    from vixl.workflows import describe

    build(request(build="b.vixl"), workspace)
    built = Project.load(workspace / "b.vixl")
    # Opening a build never changes its fingerprint, so only edits are detected.
    assert _fingerprint(built.state) == built.state["lyric_build"]["state"]
    built.apply({"type": "opacity", "target": "lyric", "value": 0.5})
    assert _fingerprint(built.state) != built.state["lyric_build"]["state"]
    props = describe()["actions"]["lyric-video-export"]["properties"]
    assert "sweep" in props["cue_animation"]["description"] and props["rebuild"]["type"] == "boolean"
    assert plan(request(cue_animation={"motion": "sweep"}), workspace)["lines"]



# Per-section styles (#221) ---------------------------------------------------------------------


def section_template(workspace):
    template(workspace / "style.vixl", operations=[
        {"type": "text", "name": "lyric-chorus", "text": "C", "size": 16, "color": "#ffd166", "x": 8, "y": 20},
        {"type": "text", "name": "next-chorus", "text": "n", "size": 8, "color": "#ffd166", "x": 8, "y": 80},
    ])


@needs_ffmpeg
def test_section_text_layers_take_over_for_their_section(workspace):
    from vixl.timeline import project_at

    section_template(workspace)
    report = build(request(build="b.vixl"), workspace)
    assert set(report["template"]["lyrics"]) == {"chorus"} and set(report["template"]["nexts"]) == {"chorus"}
    project = Project.load(workspace / "b.vixl")

    def at(time):
        return {layer["name"]: layer for layer in project_at(project, time).state["layers"]}

    verse, chorus = at(2000), at(6000)
    assert verse["lyric"]["visible"] and not verse["lyric-chorus"]["visible"]
    assert verse["lyric-next"]["visible"] and not verse["next-chorus"]["visible"]
    assert chorus["lyric-chorus"]["visible"] and not chorus["lyric"]["visible"]
    assert chorus["lyric-chorus"]["text"] == "And I keep on driving" and chorus["lyric-chorus"]["opacity"] == 1
    assert chorus["next-chorus"]["visible"] and not chorus["lyric-next"]["visible"]
    assert at(8600)["lyric-chorus"]["text"] == "This line repeats in the fire"


@needs_ffmpeg
def test_section_styles_restyle_the_lyric_and_survive_rebuilds(workspace):
    from vixl.lyrics import export
    from vixl.timeline import project_at

    styles = {"chorus": {"size": 20, "color": "#ff0000", "y": 40}}
    build(request(build="b.vixl", section_styles=styles), workspace)
    project = Project.load(workspace / "b.vixl")
    verse, chorus = project_at(project, 2000).layer("lyric"), project_at(project, 6000).layer("lyric")
    assert (verse["size"], verse["color"], verse["y"]) == (12, "#ffffff", 30)
    assert (chorus["size"], chorus["color"].lower(), chorus["y"]) == (20, "#ff0000", 40)
    assert project.state["lyric_build"]["options"]["section_styles"] == styles
    # A hand-edited build made with other section styles is stale; rebuild applies the new ones.
    fields = dict(build="b.vixl", quality="draft", start=5000, end=6500)
    project.apply({"type": "opacity", "target": "intro", "value": 0.5})
    project.save(workspace / "b.vixl")
    with pytest.raises(VixlError) as stale:
        export(request(**fields, output="a.mp4", section_styles={"chorus": {"size": 24}}), workspace)
    assert stale.value.details["changed"] == ["section_styles"]
    export(request(**fields, output="a.mp4", section_styles={"chorus": {"size": 24}}, rebuild=True), workspace)
    assert project_at(Project.load(workspace / "b.vixl"), 6000).layer("lyric")["size"] == 24


@needs_ffmpeg
@pytest.mark.parametrize("styles, words", [
    ({"chorus": {"font": "Inter"}}, "lyric-chorus"),
    ({"chorus": {"weight": 700}}, "size, color, x, y"),
    ({"Chorus!": {"size": 20}}, "section name"),
    ({"chorus": {"size": 0}}, "1–4096"),
])
def test_section_styles_are_checked(workspace, styles, words):
    from vixl.lyrics import plan

    with pytest.raises(VixlError, match=words):
        plan(request(section_styles=styles), workspace)


def test_section_text_layers_must_be_text():
    p = Project(50, 50)
    p.apply([{"type": "text", "name": "lyric", "text": "x"}, {"type": "solid", "name": "lyric-chorus"}])
    assert "'lyric-chorus' must be a text layer" in validate_template(p)["errors"][0]["message"]


def test_fit_warnings_flag_lines_too_wide_for_an_unwrapped_lyric():
    from vixl.lyrics import fit_warnings

    lines = parse_lrc(LRC)["lines"]
    p = Project(160, 90, "#101018")
    p.apply({"type": "text", "name": "lyric", "text": "Lyric", "size": 12, "color": "white", "x": 8, "y": 30})
    wide = fit_warnings(p, {"lyric": p.layer("lyric")["id"]}, lines)
    assert wide and wide[0]["code"] == "lyric_too_wide" and "text-layout" in wide[0]["message"]
    # A lyric with a text-layout box wraps long lines instead, so it does not warn.
    p.apply({"type": "text-layout", "target": "lyric", "width": 144, "height": 36, "fit": True})
    assert fit_warnings(p, {"lyric": p.layer("lyric")["id"]}, lines) == []


@needs_ffmpeg
def test_plan_reports_lines_too_wide_for_an_unwrapped_lyric(tmp_path):
    from vixl.lyrics import plan

    (tmp_path / "song.lrc").write_text(LRC, encoding="utf-8")
    write_audio(tmp_path / "song.wav")
    p = Project(160, 90, "#101018")
    p.apply([{"type": "solid", "name": "bg-default", "color": "#203040"},
             {"type": "text", "name": "lyric", "text": "Lyric", "size": 12, "color": "white", "x": 8, "y": 30}])
    p.save(tmp_path / "style.vixl")
    assert [w for w in plan(request(), tmp_path)["warnings"] if w["code"] == "lyric_too_wide"]


# Section backgrounds, template motion, per-cue animation, lead-in and end card, long renders ---------


def test_a_template_without_backgrounds_gets_one_note_instead_of_a_warning_per_section():
    p = Project(50, 50)
    p.apply([{"type": "text", "name": "lyric", "text": "x"}, {"type": "solid", "name": "backdrop"}])
    sections = [{"name": "verse"}, {"name": "chorus"}, {"name": "chorus"}, {"name": "bridge"}]
    report = validate_template(p, sections)
    assert report["warnings"] == []
    assert [note["code"] for note in report["notes"]] == ["no_section_backgrounds"]
    assert report["notes"][0]["severity"] == "info"
    assert validate_template(p, [])["notes"] == []
    # One bg-* layer shows the template wants per-section backgrounds, so gaps warn again.
    p.apply({"type": "solid", "name": "bg-chorus"})
    report = validate_template(p, sections)
    assert [w["section"] for w in report["warnings"]] == ["verse", "bridge"] and report["notes"] == []


@needs_ffmpeg
def test_plan_reports_the_background_note_once(tmp_path):
    from vixl.lyrics import plan

    (tmp_path / "song.lrc").write_text(LRC + "[00:10.00][Bridge]\n", encoding="utf-8")
    write_audio(tmp_path / "song.wav")
    p = Project(160, 90, "#101018")
    p.apply([{"type": "text", "name": "lyric", "text": "Lyric", "size": 12, "color": "white", "x": 8, "y": 30},
             {"type": "text-layout", "target": "lyric", "width": 144, "height": 36, "fit": True}])
    p.save(tmp_path / "style.vixl")
    report = plan(request(), tmp_path)
    assert not [w for w in report["warnings"] if w["code"] == "unmatched_section"]
    assert [n["code"] for n in report["notes"]] == ["no_section_backgrounds"]


def motion_template(workspace, *operations):
    template(workspace / "style.vixl", operations=[
        {"type": "shape", "shape": "rectangle", "name": "flame", "width": 10, "height": 10, "x": 2, "y": 60, "fill": "red"},
        {"type": "keyframe", "target": "flame", "property": "rotation", "time": 0, "value": 0},
        {"type": "keyframe", "target": "flame", "property": "rotation", "time": 11000, "value": 90},
        {"type": "keyframe", "target": "cue-fire", "property": "rotation", "time": 0, "value": 0},
        {"type": "keyframe", "target": "cue-fire", "property": "rotation", "time": 500, "value": 20},
        {"type": "keyframe", "target": "lyric", "property": "opacity", "time": 0, "value": 0.5},
        *operations,
    ])


@needs_ffmpeg
def test_template_motion_survives_the_build(workspace):
    motion_template(workspace)
    report = build(request(build="b.vixl", lead=0), workspace)
    built = Project.load(workspace / "b.vixl")
    # A layer the build does not drive keeps its keys; so does a cue layer's own property.
    assert keys(built, "flame", "rotation") == [(0, 0), (11000, 90)]
    assert keys(built, "cue-fire", "rotation") == [(0, 0), (500, 20)]
    assert frame(built, 5500)["flame"]["rotation"] == pytest.approx(45, abs=1)
    # What the build writes wins, and says so.
    assert keys(built, "lyric", "opacity")[0] == (0, 0.0)
    replaced = next(w for w in report["warnings"] if w["code"] == "template_track_replaced")
    assert replaced["tracks"] == [{"layer": "lyric", "property": "opacity"}]
    assert report["template_tracks"] == {"kept": 2, "replaced": 1}


@needs_ffmpeg
def test_replay_restarts_a_cue_layers_own_keys_in_each_window(workspace):
    (workspace / "two.lrc").write_text("[00:01.00]fire one\n[00:03.00]calm\n[00:06.00]fire two\n[00:09.00]calm\n")
    motion_template(workspace)
    report = build(request(lyrics="two.lrc", build="b.vixl", lead=0, cue_animation={"replay": True}), workspace)
    assert report["cues"]["cue-fire"] == [[1000, 3000], [6000, 9000]]
    built = Project.load(workspace / "b.vixl")
    assert keys(built, "cue-fire", "rotation") == [(1000, 0), (1500, 20), (6000, 0), (6500, 20)]
    assert 0 < frame(built, 1250)["cue-fire"]["rotation"] < 20
    assert frame(built, 6250)["cue-fire"]["rotation"] == frame(built, 1250)["cue-fire"]["rotation"]
    assert keys(built, "flame", "rotation") == [(0, 0), (11000, 90)]  # replay is for cue layers only


@needs_ffmpeg
def test_plan_exposes_cue_and_section_windows_and_line_phases(workspace):
    from vixl.lyrics import plan

    report = plan(request(lead=0, animation={"in": "fade-in", "out": "fade-out", "duration": 200}), workspace)
    assert report["cues"] == {"cue-fire": [[8100, 12000]]}
    assert report["section_windows"] == {"chorus": [[5300, 12000]]}
    first = report["lines"][0]
    assert (first["show"], first["settled"], first["exit"], first["hide"]) == (1000, 1200, 3299, 3500)
    # A line held into its repeat has no exit of its own; the repeat has no entry.
    held, repeat = report["lines"][3], report["lines"][4]
    assert held["exit"] == held["hide"] and repeat["settled"] == repeat["show"]


def cue_template(workspace):
    template(workspace / "style.vixl", operations=[
        {"type": "shape", "shape": "ellipse", "name": "cue-driving", "width": 10, "height": 10, "x": 2, "y": 2, "fill": "blue"},
    ])


@needs_ffmpeg
def test_each_cue_layer_can_have_its_own_animation(workspace):
    cue_template(workspace)
    settings = {"in": "fade-in", "out": "fade-out", "duration": 200,
                "cues": {"cue-driving": {"in": "slide-in-down", "duration": 400, "motion": "sweep", "amount": 8}}}
    build(request(build="b.vixl", lead=0, cue_animation=settings), workspace)
    built = Project.load(workspace / "b.vixl")
    # cue-fire uses the shared settings: a 200 ms fade and no sweep.
    assert (8300, 1.0) in keys(built, "cue-fire", "opacity") and keys(built, "cue-fire", "rotation") == []
    # cue-driving slides down over 400 ms and sweeps, and still fades out with the shared exit.
    driving = keys(built, "cue-driving", "translate-y")
    assert driving[0][0] == 5300 and driving[0][1] < 0 and (5700, 0.0) in driving
    assert keys(built, "cue-driving", "rotation")[0] == (5300, -8.0)
    assert keys(built, "cue-driving", "opacity")[-1] == (7800, 0.0)
    assert built.state["lyric_build"]["options"]["cue_animation"]["cues"]["cue-driving"]["duration"] == 400


@needs_ffmpeg
def test_per_cue_overrides_are_checked_and_part_of_the_build(workspace):
    from vixl.lyrics import export, plan

    cue_template(workspace)
    with pytest.raises(VixlError) as error:
        plan(request(cue_animation={"cues": {"cue-cell": {"in": "fade"}}}), workspace)
    assert error.value.details["allowed"] == ["cue-driving", "cue-fire"] and "cue-cell" in str(error.value)
    for bad, words in (({"fire": {}}, "not a cue layer name"), ({"cue-fire": {"cues": {}}}, "takes"),
                       ({"cue-fire": {"motion": "spin"}}, "cue_animation.cues.cue-fire.motion"),
                       ({"cue-fire": {"replay": "yes"}}, "replay")):
        with pytest.raises(VixlError, match=words):
            plan(request(cue_animation={"cues": bad}), workspace)
    fields = dict(build="b.vixl", quality="draft", fps=4, start=1000, end=2000, output="a.mp4")
    build(request(build="b.vixl", fps=4, cue_animation={"cues": {"cue-fire": {"in": "fade"}}}), workspace)
    edited = Project.load(workspace / "b.vixl")
    edited.apply({"type": "opacity", "target": "intro", "value": 0.5})
    edited.save(workspace / "b.vixl")
    with pytest.raises(VixlError) as stale:
        export(request(**fields, cue_animation={"cues": {"cue-fire": {"in": "pop"}}}), workspace)
    assert stale.value.code == "build_stale" and stale.value.details["changed"] == ["cue_animation"]


def test_lead_in_and_tail_pad_the_video_and_move_every_line():
    parsed = parse_lrc("[00:00.10]first\n[00:02.00][Verse]\n[00:02.00]second\n")
    plain = timing(parsed, {"lead": 0, "max_hold": 60000}, 5_000)
    padded = timing(parsed, {"lead": 0, "max_hold": 60000, "lead_in": 3000, "tail": 4000}, 5_000)
    assert [line["show"] for line in padded["lines"]] == [line["show"] + 3000 for line in plain["lines"]]
    assert padded["sections"][0]["start"] == 5000 and padded["sections"][0]["end"] == 12_000
    assert (padded["end"], padded["video_ms"], padded["audio_end"]) == (12_000, 12_000, 8000)
    # The last line holds into the tail unless it should end with the song.
    assert padded["lines"][-1]["hide"] == 12_000
    ended = timing(parsed, {"lead": 0, "max_hold": 60000, "lead_in": 3000, "tail": 4000, "end_at_audio": True}, 5_000)
    assert ended["lines"][-1]["hide"] == 8000
    with pytest.raises(VixlError, match="after the end of the video"):
        timing(parsed, {"lead_in": 1000, "end": 7000}, 5_000)
    with pytest.raises(VixlError) as error:
        timing(parsed, {"lead_in": 60_000, "tail": 60_000}, 590_000)
    assert error.value.code == "resource_limit"


def test_film_spec_starts_the_song_after_the_lead_in():
    from vixl.lyrics import film_spec

    report = {"start": 0, "end": 9000, "video_ms": 9000, "lead_in": 2000, "width": 16, "height": 16, "fps": 10}
    spec = film_spec({"build": "b.vixl", "audio": "song.wav"}, report)
    assert spec["audio"][0]["start"] == 2000 and spec["audio"][0]["trim"] == 0
    later = film_spec({"build": "b.vixl", "audio": "song.wav"}, {**report, "start": 5000})
    assert later["audio"][0]["start"] == 0 and later["audio"][0]["trim"] == 3000


@needs_ffmpeg
def test_end_card_and_hidden_intro_warnings(workspace):
    from vixl.lyrics import plan

    template(workspace / "style.vixl", operations=[
        {"type": "text", "name": "outro", "text": "Thanks", "size": 12, "color": "white", "x": 10, "y": 50}])
    # The first line shows at 850 ms and the last one holds to the end: neither card has room.
    codes = [w["code"] for w in plan(request(), workspace)["warnings"]]
    assert "intro_hidden" in codes and "outro_hidden" in codes
    padded = dict(lead_in=3000, tail=4000, end_at_audio=True)
    codes = [w["code"] for w in plan(request(**padded), workspace)["warnings"]]
    assert "intro_hidden" not in codes and "outro_hidden" not in codes
    report = build(request(build="b.vixl", lead=0, animation={"duration": 200}, **padded), workspace)
    assert report["video_ms"] == 19_000 and report["lead_in"] == 3000 and report["template"]["outro"]
    assert report["lines"][-1]["hide"] == 15_000  # the song (12 s) ends 15 s into the video
    built = Project.load(workspace / "b.vixl")
    assert keys(built, "outro", "visible") == [(0, False), (15_000, True)]
    assert frame(built, 14_000)["outro"]["visible"] is False
    assert 0 < frame(built, 15_100)["outro"]["opacity"] < 1  # it fades in like the lyric
    assert frame(built, 16_000)["outro"]["opacity"] == 1
    assert frame(built, 2000)["intro"]["visible"] and frame(built, 2000)["lyric"]["opacity"] == 0
    assert built.state["timeline"]["duration"] == 19_000
    assert built.state["lyric_build"]["options"]["lead_in"] == 3000


def test_camera_poses_follow_the_whole_video_in_every_window():
    from vixl.lyrics import camera_window

    camera = {"from": [0.5, 0.5, 1], "to": [0.3, 0.5, 2]}
    assert camera_window(camera, 0, 10_000, 10_000, 10) == camera  # a full render keeps the requested poses
    first = camera_window(camera, 0, 5000, 10_000, 10)
    second = camera_window(camera, 5000, 5000, 10_000, 10)
    step = (2 - 1) / 99  # zoom per frame over the full video's 100 frames
    assert first["from"] == [0.5, 0.5, 1] and second["to"] == [0.3, 0.5, 2]
    assert first["to"][2] == pytest.approx(1 + 49 * step) and second["from"][2] == pytest.approx(1 + 50 * step)
    assert second["from"][0] - first["to"][0] == pytest.approx(-0.2 / 99)


@needs_ffmpeg
def test_segmented_export_resumes_and_joins_with_the_audio(workspace):
    from vixl.film import export_segments
    from vixl.lyrics import export

    result = export(request(build="b.vixl", output="song.mp4", quality="draft", fps=4, segments=2000, end=7000), workspace)
    assert result["video"]["segments"] == {"parts": 4, "reused": 0, "rendered": 4, "frames_per_part": 8}
    assert result["video"]["frames"] == 28 and result["verification"]["status"] == "passed"
    assert not (workspace / ".song.mp4.parts").exists()  # the parts go once the video is published
    spec = {"version": 1, "width": 160, "height": 90, "fps": 4, "quality": "draft",
            "shots": [{"source": "b.vixl", "duration": 7000}],
            "audio": [{"source": "song.wav", "start": 0, "trim": 0, "volume": 1}]}

    def stop_after_two_parts():
        return (workspace / ".again.mp4.parts" / "part-0001.mp4").exists()

    with pytest.raises(VixlError) as error:
        export_segments(spec, workspace, workspace / "again.mp4", 2000, cancelled=stop_after_two_parts)
    assert error.value.code == "cancelled" and not (workspace / "again.mp4").exists()
    assert sorted(p.name for p in (workspace / ".again.mp4.parts").glob("part-*")) == ["part-0000.mp4", "part-0001.mp4"]
    resumed = export_segments(spec, workspace, workspace / "again.mp4", 2000)
    assert resumed["segments"]["reused"] == 2 and resumed["segments"]["rendered"] == 2 and resumed["frames"] == 28
    probe = subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-show_entries", "stream=codec_type,nb_read_frames",
                            "-of", "json", str(workspace / "again.mp4")], capture_output=True, check=True)
    streams = {s["codec_type"]: s for s in json.loads(probe.stdout)["streams"]}
    assert set(streams) == {"video", "audio"} and int(streams["video"]["nb_read_frames"]) == 28
    # Parts left by a different spec are discarded, not joined.
    (workspace / ".third.mp4.parts").mkdir()
    (workspace / ".third.mp4.parts" / "manifest.json").write_text('{"key": "something else"}')
    (workspace / ".third.mp4.parts" / "part-0000.mp4").write_bytes(b"stale")
    assert export_segments(spec, workspace, workspace / "third.mp4", 2000)["segments"]["reused"] == 0


def test_video_verification_reports_mismatches_and_skips_without_ffprobe(tmp_path, monkeypatch):
    import vixl.film as film

    rendered = {"width": 160, "height": 90, "fps": 24, "frames": 5170, "sample_rate": 48000, "channels": 2}
    probe = {"streams": [{"codec_type": "video", "codec_name": "h264", "width": 160, "height": 90,
                          "r_frame_rate": "24/1", "nb_frames": "5170", "duration": "215.416667"}],
             "format": {"duration": "215.416667"}}
    monkeypatch.setattr(film.shutil, "which", lambda name: "/usr/bin/" + name)
    monkeypatch.setattr(film, "_probe_media", lambda ffprobe, path: probe)
    report = film.verify_video(tmp_path / "x.mp4", rendered, requested_ms=215_400)
    assert report["status"] == "failed"
    assert [c["check"] for c in report["checks"] if not c["passed"]] == ["audio_stream"]
    # 5,170 frames at 24 fps run 16.67 ms past the song: frame quantisation, reported, not a failure.
    assert report["quantization"]["delta_ms"] == pytest.approx(16.667, abs=0.001)
    assert report["quantization"]["within_one_frame"] is True
    probe["streams"].append({"codec_type": "audio", "codec_name": "aac", "sample_rate": "44100", "channels": 2,
                             "duration": "215.4"})
    report = film.verify_video(tmp_path / "x.mp4", rendered, requested_ms=215_400)
    assert [c["check"] for c in report["checks"] if not c["passed"]] == ["sample_rate"]
    assert film.verify_video(tmp_path / "x.mp4", {**rendered, "sample_rate": 44100}, requested_ms=215_400)["passed"]
    monkeypatch.setattr(film, "_probe_media", lambda ffprobe, path: None)
    assert film.verify_video(tmp_path / "x.mp4", rendered)["status"] == "failed"
    monkeypatch.setattr(film.shutil, "which", lambda name: None)
    skipped = film.verify_video(tmp_path / "x.mp4", rendered)
    assert skipped["status"] == "skipped" and skipped["passed"] is None
