"""Alignment stays reviewable, bounded and separate from the editable lyric build."""

from copy import deepcopy
import json
import shutil
import sys
import wave

import pytest

from vixl import Project
from vixl.errors import VixlError
from vixl.plugins.lyrics import timing

pytestmark = pytest.mark.skipif(not (shutil.which("ffmpeg") and shutil.which("ffprobe")), reason="ffmpeg needed")


@pytest.fixture
def aligned(tmp_path, monkeypatch):
    with wave.open(str(tmp_path / "song.wav"), "wb") as audio:
        audio.setparams((1, 2, 8000, 0, "NONE", "not compressed"))
        audio.writeframes(b"\0\0" * 8000 * 4)
    (tmp_path / "song.txt").write_text("hello world\nhello world\n")
    payload = {"lines": [{"index": i, "text": "hello world", "start": 500 + i * 1500,
                         "end": 1500 + i * 1500, "confidence": 0.9, "words": [
                             {"text": "hello", "start": 500 + i * 1500, "end": 900 + i * 1500, "confidence": 0.9},
                             {"text": "world", "start": 1000 + i * 1500, "end": 1500 + i * 1500, "confidence": 0.9}]}
                        for i in range(2)], "token": "never-store-this"}
    script = tmp_path / "aligner.py"
    script.write_text("import json, sys\nr = json.load(sys.stdin)\nassert r['units'] == 'milliseconds'\n"
                      "assert len(r['lines']) == 2\nprint(" + repr(json.dumps(payload)) + ")\n")
    config = tmp_path / "providers.json"
    config.write_text(json.dumps({"default": "aligner", "providers": {"aligner": {
        "type": "command", "command": [sys.executable, str(script)], "model": "local-aligner",
        "key_env": "ALIGN_SECRET", "capabilities": ["align"]}}}))
    monkeypatch.setenv("VIXL_PROVIDERS", str(config))
    monkeypatch.delenv("VIXL_AI_PROVIDER", raising=False)
    monkeypatch.setenv("ALIGN_SECRET", "never-store-this")
    request = {"audio": "song.wav", "lyrics": "song.txt", "output": "song.timing.json"}
    result = timing.align(request, tmp_path)
    return tmp_path, result, script


def test_command_alignment_preserves_occurrences_and_safe_provenance(aligned):
    root, result, _ = aligned
    assert result["valid"]
    assert [line["start"] for line in result["lines"]] == [500, 2000]
    assert result["review"]["status"] == "pending"
    saved = (root / "song.timing.json").read_text()
    assert "never-store-this" not in saved and "ALIGN_SECRET" not in saved and "command" not in saved.split('"type":')[0]
    assert result["provenance"] == {"provider": "aligner", "type": "command", "model": "local-aligner"}
    with pytest.raises(VixlError, match="already exists"):
        timing.align({"audio": "song.wav", "lyrics": "song.txt", "output": "song.timing.json"}, root)


def test_lrc_starts_are_preserved_unless_explicitly_replaced(aligned):
    root, _, _ = aligned
    (root / "source.lrc").write_text("[00:00.400]hello world\n[00:01.900]hello world\n")
    request = {"audio": "song.wav", "lyrics": "source.lrc", "output": "lrc.timing.json"}
    kept = timing.align(request, root)
    assert [line["start"] for line in kept["lines"]] == [400, 1900]
    assert all(line["source"] == "lrc" for line in kept["lines"])
    replaced = timing.align({**request, "output": "replaced.json", "replace_lines": True}, root)
    assert [line["start"] for line in replaced["lines"]] == [500, 2000]


def test_invalid_alignment_is_written_for_review_and_cannot_build(aligned):
    root, result, _ = aligned
    record = deepcopy(result)
    record["lines"][1].update(start=100, end=5000, matched=False, confidence=0.2)
    record["lines"][0]["words"][1]["start"] = 400
    (root / "invalid.json").write_text(json.dumps(record))
    invalid = timing.load(root / "invalid.json")
    assert not invalid["valid"]
    assert {w["code"] for w in invalid["warnings"]} >= {
        "invalid_range", "non_monotonic", "unmatched_line", "low_confidence", "invalid_word_range", "non_monotonic_word"}
    with pytest.raises(VixlError, match="Fix invalid timing"):
        timing.export({"timing": "invalid.json", "output": "invalid.lrc"}, root)
    assert not (root / "invalid.lrc").exists()


def test_edits_never_rerun_alignment_and_lrc_roundtrips(aligned):
    root, _, script = aligned
    script.unlink()
    edited = timing.edit({"timing": "song.timing.json", "output": "edited.json",
                          "edits": [{"line": 0, "shift": 100}, {"line": 1, "word": 0, "end": 2350}]}, root)
    assert edited["valid"]
    assert edited["lines"][0]["start"] == 600
    assert edited["lines"][0]["words"][0]["start"] == 600
    assert edited["lines"][1]["words"][0]["source"] == "edited"
    timing.export({"timing": "edited.json", "output": "edited.lrc"}, root)
    parsed = timing.parse_lrc((root / "edited.lrc").read_bytes())
    assert [line["time"] for line in parsed["lines"]] == [600, 2000]
    assert parsed["lines"][0]["words"] == [{"time": 600, "text": "hello"}, {"time": 1100, "text": "world"}]
    again = timing.edit({"timing": "edited.json", "output": "edited.json", "replace": True,
                         "edits": [{"line": 0, "shift": 10}]}, root)
    assert again["lines"][0]["start"] == 610


def test_build_uses_word_times_and_keeps_editable_tracks(aligned):
    from vixl.plugins.lyrics.lyrics import build
    from vixl.timeline import project_at
    root, _, script = aligned
    script.unlink()
    project = Project(160, 90, "black")
    project.apply([{"type": "text", "name": "lyric", "text": "", "size": 12, "color": "white", "x": 5, "y": 5}])
    project.save(root / "template.vixl")
    result = build({"audio": "song.wav", "timing": "song.timing.json", "template": "template.vixl", "build": "built.vixl",
                    "animation": {"in": "typewriter", "out": "none", "unit": "word"}, "lead_in": 100}, root)
    built = Project.load(root / "built.vixl")
    ident = built.state["layers"][0]["id"]
    def shown(time):
        frame = project_at(built, time)
        return next(layer["text"] for layer in frame.state["layers"] if layer["id"] == ident)
    assert shown(700) == "hello"
    assert shown(1200) == "hello world"
    assert shown(2200) == "hello"
    assert result["lines"][0]["settled"] == 1100
    assert result["lines"][0]["words"][0]["time"] == 600
    assert built.state["timeline"]["tracks"]


def test_workflow_schema_and_cli_expose_timing(aligned):
    from vixl.cli import _dispatch
    from vixl.interfaces import Session
    from vixl.workflows import dispatch, describe
    root, _, _ = aligned
    fields = describe()["actions"]
    assert {"lyrics-align", "lyrics-timing-edit", "lyrics-timing-export"} <= set(fields)
    assert "timing" in fields["lyric-video-build"]["fields"]
    result = dispatch(Session(workspace=root), "lyrics-timing-export", {"timing": "song.timing.json", "output": "workflow.lrc"})
    assert result["lines"] == 2
    result, _ = _dispatch(["lyrics", "timing-export", "song.timing.json", "-o", "cli.lrc", "--workspace", str(root)])
    assert result["lines"] == 2


def test_missing_provider_names_setup_doc(tmp_path, monkeypatch):
    config = tmp_path / "empty.json"
    config.write_text("{}")
    monkeypatch.setenv("VIXL_PROVIDERS", str(config))
    monkeypatch.delenv("VIXL_AI_PROVIDER", raising=False)
    (tmp_path / "song.txt").write_text("hello\n")
    monkeypatch.setattr(timing, "audio_duration", lambda _: 1000)
    with pytest.raises(VixlError, match="docs/reference/providers.md") as error:
        timing.align({"audio": "song.wav", "lyrics": "song.txt", "output": "out.json"}, tmp_path)
    assert error.value.code == "missing_dependency"


def test_sparse_and_malformed_records_fail_cleanly(aligned):
    root, record, _ = aligned
    del record["lines"][0]["words"]
    (root / "sparse.json").write_text(json.dumps(record))
    parsed = timing.parsed(timing.load(root / "sparse.json"), record["duration_ms"])
    assert parsed["lines"][0]["words"] == []
    for invalid in (None, {}, ["unexpected"]):
        record["analysis_warnings"] = invalid
        (root / "bad.json").write_text(json.dumps(record))
        with pytest.raises(VixlError, match="analysis_warnings"):
            timing.load(root / "bad.json")


def test_http_alignment_uses_the_same_contract_without_storing_credentials(aligned, monkeypatch):
    from vixl.plugins.ai.ai import HTTPProvider
    root, original, _ = aligned
    (root / "providers.json").write_text(json.dumps({"default": "gateway", "providers": {"gateway": {
        "type": "http", "url": "https://align.example", "key_env": "ALIGN_SECRET", "capabilities": ["align"]}}}))
    def respond(self, method, route, **kwargs):
        assert method == "POST" and route == "/align"
        assert self.headers["Authorization"] == "Bearer never-store-this"
        assert kwargs["json"]["audio_format"] == "wav"
        assert [line["index"] for line in kwargs["json"]["lines"]] == [0, 1]
        return json.dumps({"lines": original["lines"]}).encode()
    monkeypatch.setattr(HTTPProvider, "request", respond)
    result = timing.align({"audio": "song.wav", "lyrics": "song.txt", "output": "http.json"}, root)
    assert result["valid"] and result["provenance"] == {"provider": "gateway", "type": "http"}
    assert "never-store-this" not in (root / "http.json").read_text()


def test_command_adapter_checks_cancel_before_start_and_bounds_stderr(monkeypatch):
    from vixl.errors import Cancelled
    from vixl.plugins.ai import command_provider
    provider = command_provider.CommandProvider("local", {"command": [sys.executable, "-c", "print('{}')"]})
    def cancelled():
        raise Cancelled()
    monkeypatch.setattr(command_provider, "check_cancelled", cancelled)
    with pytest.raises(Cancelled):
        provider.invoke("align", {})
    monkeypatch.setattr(command_provider, "check_cancelled", lambda: None)
    monkeypatch.setattr(command_provider, "MAX_OUTPUT", 64)
    provider = command_provider.CommandProvider("local", {"command": [sys.executable, "-c",
        "import sys; sys.stderr.write('x'*1000); print('{}')"]})
    with pytest.raises(VixlError, match="exceeds"):
        provider.invoke("align", {})
