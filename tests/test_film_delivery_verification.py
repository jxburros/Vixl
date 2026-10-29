"""Delivery checks distinguish encoding, cue coverage, sampled design checks and human review."""

from copy import deepcopy
import hashlib
import shutil
import wave

import pytest

from vixl import Project
from vixl.errors import VixlError
from vixl.plugins.film import film
from vixl.plugins.lyrics import lyrics
from vixl.plugins.lyrics.verification import review, verify

needs_ffmpeg = pytest.mark.skipif(not (shutil.which("ffmpeg") and shutil.which("ffprobe")),
                                  reason="ffmpeg and ffprobe are required")
MEDIA = {"passed": True, "status": "passed", "checks": [{"check": "decode", "passed": True}]}


@pytest.fixture
def built(tmp_path):
    if not (shutil.which("ffmpeg") and shutil.which("ffprobe")):
        pytest.skip("ffmpeg and ffprobe are required")
    with wave.open(str(tmp_path / "song.wav"), "wb") as audio:
        audio.setparams((1, 2, 8000, 0, "NONE", "not compressed"))
        audio.writeframes(b"\0\0" * 16000)
    (tmp_path / "song.lrc").write_text("[00:00.10]Hello\n[00:00.70]Hello\n[00:01.30]Bye\n")
    template = Project(160, 90, "black")
    template.apply({"type": "text", "name": "lyric", "text": "Template", "size": 16,
                    "x": 20, "y": 30, "color": "white"})
    template.save(tmp_path / "template.vixl")
    request = {"audio": "song.wav", "lyrics": "song.lrc", "template": "template.vixl", "build": "build.vixl",
               "fps": 10, "lead": 0, "animation": {"in": "none", "out": "none"}}
    report = lyrics.build(request, tmp_path)
    return tmp_path, request, report, Project.load(tmp_path / "build.vixl")


def test_every_chorus_occurrence_is_checked_and_full_coverage_is_explicit(built):
    _, _, report, project = built
    assert lyrics.check_lines(project, report)["checked_lines"] == 3
    result = verify(report, project, mode="full", media=MEDIA)
    text_checks = [item for item in result["structural"]["checks"] if item["check"] == "cue_text"]
    assert len(text_checks) == 3 and all(item["passed"] for item in text_checks)
    assert len(result["visual_sampled"]["frames"]) <= 4 * len(report["lines"])
    assert result["coverage"]["checked_ms"] < report["duration_ms"]
    assert result["coverage"]["unsampled_intervals"]
    assert result["review"]["status"] == "pending" and not result["validated"]
    assert result["outcome"]["state"] == "needs_review"


def test_cue_text_and_invalid_timing_fail_even_when_media_passes(built):
    _, _, report, project = built
    broken = deepcopy(report)
    broken["lines"][-1]["hide"] = report["video_ms"] + 1
    result = verify(broken, project, media=MEDIA)
    assert not result["structural"]["passed"] and not result["validated"]
    assert any(item["check"] == "cue_timing" and not item["passed"] for item in result["structural"]["checks"])
    project.apply({"type": "keyframe", "target": "lyric", "property": "text", "time": 100, "value": "Wrong"})
    result = verify(report, project, media=MEDIA)
    assert any(item["check"] == "cue_text" and item["actual"] == "Wrong" and not item["passed"]
               for item in result["structural"]["checks"])
    assert result["outcome"]["state"] == "validation_failed"


def test_review_is_explicit_persisted_and_invalidated_by_edits(built):
    root, _, report, project = built
    assert verify(report, project, mode="full", media=MEDIA)["review"]["status"] == "pending"
    decision = review({"build": "build.vixl", "approve": True}, root)
    assert decision["review"]["status"] == "approved" and not decision["validated"]
    project = Project.load(root / "build.vixl")
    verified = verify(report, project, mode="full", media=MEDIA)
    assert verified["validated"], verified
    assert not verify(report, project, mode="basic", media=MEDIA)["validated"]
    project.apply({"type": "move", "target": "lyric", "x": 24})
    assert verify(report, project, mode="full", media=MEDIA)["review"]["status"] == "pending"
    review({"build": "build.vixl", "changes_requested": True, "findings": ["Adjust timing"]}, root)
    declined = Project.load(root / "build.vixl")
    result = verify(report, declined, mode="full", media=MEDIA)
    assert result["review"]["status"] == "changes_requested" and not result["validated"]
    with pytest.raises(VixlError):
        review({"build": "build.vixl", "approve": True, "changes_requested": True}, root)


def test_full_sampling_is_bounded_and_reports_unchecked_frames(built, monkeypatch):
    _, _, report, project = built
    project.state["timeline"]["duration"] = 12_000
    project.state["timeline"]["tracks"] = []
    project.layer("lyric")["text"] = "Hello"
    report.update(start=0, end=12_000, video_ms=12_000,
                  lines=[{"index": i, "show": i * 100, "hide": (i + 1) * 100,
                          "text": "Hello"} for i in range(110)])
    project.state["lyric_build"]["options"]["animation"] = {"in": "fade-in", "out": "none", "duration": 30}
    monkeypatch.setattr(Project, "check", lambda *args, **kwargs: {"passed": True, "issues": []})
    result = verify(report, project, mode="full", media=MEDIA)
    assert len(result["visual_sampled"]["frames"]) == 400
    assert any("400" in text for text in result["unreviewed"])


def test_missing_audio_cannot_validate_delivery(built, monkeypatch):
    _, _, report, project = built
    monkeypatch.setattr(film, "_probe_media", lambda *_: {"streams": [{"codec_type": "video", "width": 160,
        "height": 90, "r_frame_rate": "10/1", "nb_frames": "20", "duration": "2"}]})
    media = film.verify_video("movie.mp4", {"width": 160, "height": 90, "fps": 10, "frames": 20,
                                           "sample_rate": 8000, "channels": 1})
    assert not media["validated"]
    result = verify(report, project, media=media)
    assert not result["validated"] and result["outcome"]["state"] == "validation_failed"


@needs_ffmpeg
def test_export_records_source_hashes_transcode_and_pending_review(built):
    root, request, _, _ = built
    result = lyrics.export({**request, "output": "movie.mp4", "verify": "full"}, root)
    verified = result["verification"]
    assert verified["review"]["status"] == "pending" and not result["validated"]
    assert next(item for item in verified["checks"] if item["check"] == "decode")["passed"]
    assert verified["sources"]["lyrics"] == hashlib.sha256((root / "song.lrc").read_bytes()).hexdigest()
    assert verified["sources"]["audio"] == hashlib.sha256((root / "song.wav").read_bytes()).hexdigest()
    assert verified["sources"]["build"] == hashlib.sha256((root / "build.vixl").read_bytes()).hexdigest()
    transcode = verified["sources"]["audio_transcode"]
    assert transcode["output"]["codec"] == "aac" and transcode["sources"][0]["codec"] == "pcm_s16le"
    assert transcode["trim"] == {"start_ms": 0, "end_ms": 2000}
    movie = root / "movie.mp4"
    movie.write_bytes(movie.read_bytes()[:movie.stat().st_size // 2])
    damaged = film.verify_video(movie, result["video"], decode=True)
    assert not damaged["passed"] and not damaged["validated"]
    assert not next(item for item in damaged["checks"] if item["check"] == "decode")["passed"]


def test_review_workflow_schema_and_dispatch(built):
    from vixl.interfaces import Session
    from vixl.workflows import describe, dispatch

    root, _, _, _ = built
    schema = describe()["actions"]
    assert schema["lyric-video-export"]["properties"]["verify"]["enum"] == ["basic", "full"]
    result = dispatch(Session(workspace=root), "lyric-video-review", {"build": "build.vixl", "approve": True})
    assert result["review"]["status"] == "approved"


def test_same_duration_audio_replacement_requires_a_new_review(built):
    root, request, report, project = built
    review({"build": "build.vixl", "approve": True}, root)
    reviewed = Project.load(root / "build.vixl")
    assert verify(report, reviewed, mode="full", media=MEDIA)["review"]["status"] == "approved"
    with wave.open(str(root / "song.wav"), "wb") as audio:
        audio.setparams((1, 2, 8000, 0, "NONE", "not compressed"))
        audio.writeframes(b"\x01\x00" * 16000)
    changed_sources = {"audio": film.file_sha256(root / "song.wav"), "lyrics": film.file_sha256(root / "song.lrc")}
    changed = verify(report, reviewed, mode="full", media=MEDIA, sources=changed_sources)
    assert changed["review"]["status"] == "pending" and not changed["validated"]
    with pytest.raises(VixlError, match="changed"):
        review({"build": "build.vixl", "approve": True}, root)
    result = lyrics.export({**request, "output": "new-audio.mp4", "replace": True, "verify": "full"}, root)
    assert result["verification"]["review"]["status"] == "pending" and not result["validated"]


def test_sources_changed_during_render_fail_verification(built, monkeypatch):
    root, request, _, _ = built
    original = film.export

    def export_and_change_source(*args, **kwargs):
        result = original(*args, **kwargs)
        (root / "song.lrc").write_text("[00:00.10]Changed during render\n")
        return result

    monkeypatch.setattr(film, "export", export_and_change_source)
    result = lyrics.export({**request, "output": "changed.mp4"}, root)
    assert result["verification"]["sources"]["changed_during_export"] == ["lyrics"]
    assert result["outcome"]["state"] == "validation_failed" and not result["validated"]
