"""Render lockfile version 2 (#512): pages, artboards and frames, recorded exports, toolchain and secrets."""

import json
import shutil
import sys
from copy import deepcopy
from pathlib import Path

import pytest

from vixl import Project
from vixl.cli import main
from vixl.errors import VixlError
from vixl.interfaces import Session
from vixl.plugins.workspace_qa import export_lock
from vixl.plugins.workspace_qa.reproduce import lock, read_lock, reproduce, write_lock
from vixl.workflows import dispatch

sys.path.insert(0, str(Path(__file__).parent))
from icc_helper import cmyk_profile  # noqa: E402

needs_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="MP4 export needs ffmpeg")


def deck():
    p = Project(300, 200, "#ffffff")
    for name in ("cover", "results", "close"):
        p.apply([{"type": "page", "action": "add", "name": name},
                 {"type": "text", "text": name.title(), "name": "title", "size": 30, "x": 20, "y": 40, "color": "#111111"}])
    p.apply({"type": "page", "action": "select", "page": 1})
    return p


def moving():
    p = Project(160, 120, "#ffffff")
    p.apply([{"type": "shape", "shape": "ellipse", "name": "ball", "x": 10, "y": 40, "width": 40, "height": 40,
              "fill": "#2a9d8f"},
             {"type": "timeline-set", "duration": 600, "fps": 10},
             {"type": "animate", "target": "ball", "property": "x", "from": 0, "to": 100, "easing": "linear"}])
    return p


def poster():
    p = Project(320, 200, "#ffffff")
    p.apply([{"type": "text", "text": "Sale", "name": "headline", "size": 44, "x": 20, "y": 30, "color": "#111111"},
             {"type": "shape", "shape": "ellipse", "name": "dot", "x": 200, "y": 60, "width": 80, "height": 80,
              "fill": "#2a9d8f"}])
    return p


def located(result, *kinds):
    return [(item["kind"], item["name"]) for item in result["drift"] if item["kind"] in kinds]


# --- targets -----------------------------------------------------------------------------------------------------

def test_a_three_page_document_locks_each_page_and_a_changed_page_is_located():
    p = deck()
    locked = lock(p)
    assert locked["version"] == 2
    assert [(t["kind"], t["name"]) for t in locked["targets"]] == [("page", "page 1"), ("page", "page 2"),
                                                                 ("page", "page 3")]
    assert reproduce(p, locked=locked)["reproduction"] == "reference-verified"
    p.apply({"type": "text-set", "target": "title", "text": "Changed", "page": 2})
    result = reproduce(p, locked=locked)
    assert result["reproduction"] == "drifted"
    assert located(result, "page") == [("page", "page 2")]
    moved = next(item for item in result["input_drift"] if item["kind"] == "page")
    assert moved["locked"] != moved["current"] and len(moved["locked"]) == 64


def test_artboards_are_locked_and_a_changed_artboard_is_located():
    p = poster()
    p.apply([{"type": "artboard", "name": "wide", "x": 0, "y": 0, "width": 320, "height": 100},
             {"type": "artboard", "name": "tall", "x": 0, "y": 0, "width": 100, "height": 200}])
    locked = lock(p)
    assert [(t["kind"], t["name"], t["size"]) for t in locked["targets"]] == [
        ("artboard", "wide", [320, 100]), ("artboard", "tall", [100, 200])]
    p.apply({"type": "artboard", "name": "tall", "x": 100, "y": 0, "width": 100, "height": 200})
    assert located(reproduce(p, locked=locked), "artboard") == [("artboard", "tall")]


def test_animated_documents_lock_sampled_frames():
    p = moving()
    default = lock(p)
    assert [(t["kind"], t["time"]) for t in default["targets"]] == [("frame", 0), ("frame", 200), ("frame", 400)]
    assert [t["time"] for t in lock(p, frames=2)["targets"]] == [0, 300]
    assert [t["time"] for t in lock(p, times=["50%", "0.5s", 100])["targets"]] == [100, 300, 500]
    assert lock(poster())["targets"] == []
    with pytest.raises(VixlError, match="frames is a whole number"):
        lock(p, frames=999)
    p.apply({"type": "animate", "target": "ball", "property": "x", "from": 0, "to": 50, "easing": "linear"})
    result = reproduce(p, locked=default)
    assert located(result, "frame") == [("frame", "200 ms"), ("frame", "400 ms")]


def test_variables_and_seeds_are_locked_and_located():
    p = poster()
    p.apply([{"type": "variable", "name": "price", "value": "$5"},
             {"type": "grain", "target": "dot", "seed": 7, "amount": 0.2}])
    locked = lock(p)
    assert locked["variables"]["count"] == 1 and "price" in locked["variables"]["names"]
    assert "$5" not in json.dumps(locked)
    assert list(locked["seeds"]["values"].values()) == [7]
    p.apply([{"type": "variable", "name": "price", "value": "$6"}, {"type": "variable", "name": "new", "value": "x"}])
    assert {name for _, name in located(reproduce(p, locked=locked), "variables")} == {"price", "new"}
    rows = [{"city": "Oslo"}, {"city": "Rome"}]
    assert lock(p, variables=rows)["variables"]["count"] == 2
    assert lock(p, variables=rows)["variables"]["sha256"] != lock(p, variables=rows[:1])["variables"]["sha256"]


def test_a_version_1_lock_still_verifies():
    p = deck()
    legacy = {key: value for key, value in lock(p).items() if key not in ("targets", "variables", "seeds")}
    legacy["version"] = 1
    assert reproduce(p, locked=legacy)["reproduction"] == "reference-verified"
    p.apply({"type": "text-set", "target": "title", "text": "Changed", "page": 2})
    moved = reproduce(p, locked=legacy)
    assert moved["reproduction"] == "drifted" and located(moved, "document") == [("document", "document")]
    with pytest.raises(VixlError, match="version 1"):
        reproduce(p, locked=legacy, verify_exports=True)
    with pytest.raises(VixlError, match="Unsupported lockfile"):
        reproduce(p, locked={**legacy, "version": 3})


# --- exports -----------------------------------------------------------------------------------------------------

def test_exports_are_recorded_with_byte_and_visual_hashes():
    p = poster()
    locked = lock(p, exports=["png", "jpg:quality=80", "svg", "pdf"])
    png, jpg, svg, pdf = locked["exports"]
    assert [e["format"] for e in locked["exports"]] == ["png", "jpg", "svg", "pdf"]
    assert png["deterministic"] and svg["deterministic"] and pdf["deterministic"] and not jpg["deterministic"]
    assert jpg["options"] == {"color_space": "rgb", "quality": 80, "scale": 1}
    for entry in (png, jpg):
        assert len(entry["sha256"]) == 64 and len(entry["visual_sha256"]) == 64 and entry["size"] == [320, 200]
        assert len(entry["signature"]) == 1 and len(entry["signature"][0]) == export_lock.GRID ** 2 * 6
    assert reproduce(p, locked=locked)["reproduction"] == "reference-verified"
    result = reproduce(p, locked=locked, verify_exports=True)
    assert result["reproduction"] == "reference-verified" and result["reproducible"]
    assert result["byte_identical"] is True and result["visually_equivalent"] is True
    assert [item["compared"] for item in result["exports"]] == ["bytes", "pixels", "bytes", "bytes"]
    assert all(item["byte_identical"] and item["passed"] for item in result["exports"])


def test_changing_the_export_quality_is_export_setting_drift():
    p = poster()
    locked = lock(p, exports=["jpg:quality=80", "png"])
    result = reproduce(p, locked=locked, exports=["jpg:quality=70"])
    assert result["reproduction"] == "drifted"
    assert result["input_drift"] == [{"kind": "export-setting", "name": "jpg.quality", "format": "jpg",
                                      "option": "quality", "locked": 80, "current": 70}]
    assert result["environment_drift"] == []
    # An unset option means its default: a bare "jpg" differs from a locked quality 80 too.
    assert [item["name"] for item in reproduce(p, locked=locked, exports=["jpg"])["drift"]] == ["jpg.quality"]
    # The png was not named, so it still verifies with its locked settings.
    assert [item["format"] for item in result["exports"]] == ["jpg", "png"] and result["exports"][1]["passed"]
    added = reproduce(p, locked=locked, exports=["svg"])
    assert ("export-setting", "svg") in located(added, "export-setting") and not added["reproducible"]


def test_bytes_and_pixels_are_reported_separately():
    p = poster()
    locked = lock(p, exports=["png", "jpg:quality=80"])
    tampered = deepcopy(locked)
    tampered["exports"][0]["sha256"] = "0" * 64
    result = reproduce(p, locked=tampered, verify_exports=True)
    png = result["exports"][0]
    assert (png["byte_identical"], png["visually_equivalent"], png["passed"]) == (False, True, False)
    assert result["reproduction"] == "export-mismatch" and not result["reproducible"]
    assert result["byte_identical"] is False and result["visually_equivalent"] is True
    assert "export png differs in its bytes" in result["outcome"]["review_reasons"]
    forgiven = reproduce(p, locked=tampered, verify_exports=True, export_visual=True)
    assert forgiven["reproducible"] and forgiven["exports"][0]["compared"] == "pixels"


def test_a_lossy_export_is_equivalent_within_the_tolerance():
    p = poster()
    locked = lock(p, exports=["jpg:quality=80"])

    def shifted(amount):
        tampered = deepcopy(locked)
        entry = tampered["exports"][0]
        entry["sha256"], entry["visual_sha256"] = "0" * 64, "1" * 64
        entry["signature"] = [bytes(min(255, b + amount) for b in bytes.fromhex(s)).hex() for s in entry["signature"]]
        return tampered

    near = reproduce(p, locked=shifted(3), verify_exports=True)
    item = near["exports"][0]
    assert (item["byte_identical"], item["visually_equivalent"], item["passed"]) == (False, True, True)
    assert near["reproducible"] and near["reproduction"] == "reference-verified"
    far = reproduce(p, locked=shifted(40), verify_exports=True)
    assert far["exports"][0]["visually_equivalent"] is False and far["reproduction"] == "export-mismatch"
    assert reproduce(p, locked=shifted(40), verify_exports=True, export_tolerance=60)["reproducible"]


def test_animated_gif_frames_are_decoded_and_compared():
    p = moving()
    locked = lock(p, exports=["gif"])
    entry = locked["exports"][0]
    assert entry["frames"] == 6 and len(entry["signature"]) == 5 and entry["options"]["colors"] == 256
    result = reproduce(p, locked=locked, verify_exports=True)
    assert result["reproducible"] and result["visually_equivalent"] is True
    p.apply({"type": "animate", "target": "ball", "property": "x", "from": 0, "to": 5, "easing": "linear"})
    changed = reproduce(p, locked=locked, verify_exports=True)
    assert changed["exports"][0]["visually_equivalent"] is False and not changed["reproducible"]


@needs_ffmpeg
def test_an_mp4_re_encode_is_visually_equivalent_not_byte_identical():
    p = moving()
    locked = lock(p, exports=["mp4:fps=10"])
    entry = locked["exports"][0]
    assert entry["kind"] == "timeline" and not entry["deterministic"] and entry["frames"] == 6
    assert locked["toolchain"]["ffmpeg"] == export_lock.ffmpeg_version()
    assert reproduce(p, locked=locked, verify_exports=True)["reproducible"]
    # Another ffmpeg build writes other bytes and slightly different pixels.
    other = deepcopy(locked)
    other["exports"][0]["sha256"], other["exports"][0]["visual_sha256"] = "0" * 64, "1" * 64
    other["exports"][0]["signature"] = [bytes(min(255, b + 2) for b in bytes.fromhex(s)).hex()
                                        for s in entry["signature"]]
    result = reproduce(p, locked=other, verify_exports=True)
    item = result["exports"][0]
    assert (item["byte_identical"], item["visually_equivalent"], item["passed"]) == (False, True, True)
    assert result["reproducible"]
    # A different encoder version is located by format and tool.
    other["toolchain"]["ffmpeg"] = "0.0.1"
    drifted = reproduce(p, locked=other, verify_exports=True)
    assert drifted["environment_drift"] == [{"kind": "toolchain", "name": "mp4.ffmpeg", "format": "mp4",
                                            "option": "ffmpeg", "locked": "0.0.1",
                                            "current": export_lock.ffmpeg_version()}]


def test_an_icc_profile_is_recorded_by_hash_and_a_changed_one_is_toolchain_drift(tmp_path):
    (tmp_path / "press.icc").write_bytes(cmyk_profile())
    p = poster()
    resolve = lambda value: tmp_path / value  # noqa: E731
    locked = lock(p, exports=["tiff:color_space=cmyk,icc_profile=press.icc"], resolve=resolve)
    assert locked["exports"][0]["options"]["icc_profile"] == "press.icc"
    assert len(locked["toolchain"]["icc"]["press.icc"]) == 64
    assert reproduce(p, locked=locked, verify_exports=True, resolve=resolve)["reproducible"]
    tampered = deepcopy(locked)
    tampered["toolchain"]["icc"]["press.icc"] = "0" * 64
    result = reproduce(p, locked=tampered, verify_exports=True, resolve=resolve)
    assert [(d["kind"], d["name"]) for d in result["environment_drift"]] == [("toolchain", "tiff.icc_profile")]


def test_bad_export_requests_are_refused_with_the_valid_names():
    with pytest.raises(VixlError, match="did you mean 'quality'"):
        export_lock.parse("jpg:qualty=80")
    with pytest.raises(VixlError, match="Unknown export format 'jgp'"):
        export_lock.parse("jgp")
    with pytest.raises(VixlError, match="from 1 to 100"):
        export_lock.parse("jpg:quality=500")
    with pytest.raises(VixlError, match="key=value"):
        export_lock.parse("jpg:quality")
    assert export_lock.parse({"format": "JPEG", "options": {"quality": "80"}})["options"]["quality"] == 80
    assert export_lock.label(export_lock.parse("jpg:quality=80")) == "jpg:quality=80"
    assert export_lock.label(export_lock.parse("jpg:quality=90")) == "jpg"


def test_exports_cannot_be_verified_without_a_lock():
    with pytest.raises(VixlError, match="needs a lockfile"):
        reproduce(poster(), exports=["png"])
    with pytest.raises(VixlError, match="records no exports"):
        reproduce(poster(), locked=lock(poster()), verify_exports=True)


# --- secrets -----------------------------------------------------------------------------------------------------

def test_no_provider_key_or_secret_value_enters_the_lock(tmp_path, monkeypatch):
    from vixl.plugins.ai import models

    secrets = {"OPENAI_API_KEY": "sk-test-openai-0123456789", "ANTHROPIC_API_KEY": "sk-ant-test-0123456789",
               "GEMINI_API_KEY": "gemini-test-0123456789", "MY_SERVICE_TOKEN": "token-value-0123456789",
               "DB_PASSWORD": "hunter2-hunter2", "ACME_GATEWAY": "gateway-secret-0123456789"}
    for name, value in secrets.items():
        monkeypatch.setenv(name, value)
    providers = tmp_path / "providers.json"
    providers.write_text(json.dumps({"providers": {"acme": {"type": "openai", "url": "https://acme.test/v1",
                                                            "key_env": "ACME_GATEWAY"}}}), encoding="utf-8")
    monkeypatch.setenv("VIXL_PROVIDERS", str(providers))
    assert set(models.configured()) >= {"openai", "acme"}
    p = poster()
    p.layer("headline")["provenance"] = {"provider": "acme"}
    text = json.dumps(lock(p, exports=["png", "jpg:quality=80"]))
    for value in secrets.values():
        assert value not in text
    report = reproduce(p, locked=lock(p), report=True)
    assert all(value not in json.dumps(report) for value in secrets.values())
    # Even free text an export option carries is checked, and the error names the variable, never the value.
    for variable in ("DB_PASSWORD", "ACME_GATEWAY"):
        with pytest.raises(VixlError) as caught:
            lock(p, exports=[f"pdf:title={secrets[variable]}"])
        assert variable in str(caught.value) and secrets[variable] not in str(caught.value)


# --- the manifest-ready report, workflow and CLI -----------------------------------------------------------------

def test_report_is_a_compact_manifest_ready_dict():
    p = poster()
    locked = lock(p, exports=["png", "jpg:quality=80"])
    report = reproduce(p, locked=locked, verify_exports=True, report=True)
    assert json.loads(json.dumps(report)) == report
    assert report["format"] == "vixl-reproduction" and report["reproducible"] and report["reproduction"] == "reference-verified"
    assert report["lock"]["version"] == 2 and report["lock"]["exports"] == 2 and len(report["lock"]["sha256"]) == 64
    assert report["byte_identical"] is True and report["visually_equivalent"] is True
    assert [e["format"] for e in report["exports"]] == ["png", "jpg"]
    p.apply({"type": "text-set", "target": "headline", "text": "Other"})
    failed = reproduce(p, locked=locked, verify_exports=True, report=True)
    assert not failed["reproducible"] and failed["drift"]["input"] >= 1 and failed["drift"]["items"]
    assert reproduce(p, report=True)["lock"] is None


def test_workflow_records_and_verifies_exports(tmp_path):
    poster().save(tmp_path / "poster.vixl")
    session = Session(tmp_path / "poster.vixl", workspace=tmp_path)
    written = dispatch(session, "reproduce", {"write_lock": "poster.lock.json", "exports": ["png", "jpg:quality=80"]},
                       "poster.vixl")
    assert written["lock_written"] == "poster.lock.json"
    assert [e["format"] for e in read_lock(tmp_path / "poster.lock.json")["exports"]] == ["png", "jpg"]
    result = dispatch(session, "reproduce", {"lock": "poster.lock.json", "verify_exports": True}, "poster.vixl")
    assert result["reproducible"] and result["byte_identical"] is True
    report = dispatch(session, "reproduce", {"lock": "poster.lock.json", "verify_exports": True, "report": True},
                      "poster.vixl")
    assert report["format"] == "vixl-reproduction"
    for bad in ({"exports": ["png"]}, {"verify_exports": True}, {"lock": "poster.lock.json", "frames": 2}):
        with pytest.raises(VixlError):
            dispatch(session, "reproduce", bad, "poster.vixl")
    with pytest.raises(VixlError, match="already exists"):
        dispatch(session, "reproduce", {"write_lock": "poster.lock.json"}, "poster.vixl")


def test_cli_records_and_verifies_exports(tmp_path, capsys):
    poster().save(tmp_path / "doc.vixl")
    base = ["--project", str(tmp_path / "doc.vixl"), "reproduce"]
    lock_path = tmp_path / "doc.lock.json"
    assert main([*base, "--write-lock", str(lock_path), "--export", "png", "jpg:quality=80"]) == 0
    recorded = json.loads(lock_path.read_text())
    assert [e["format"] for e in recorded["exports"]] == ["png", "jpg"]
    assert main([*base, "--lock", str(lock_path), "--export"]) == 0
    assert main([*base, "--lock", str(lock_path), "--export", "jpg:quality=70"]) == 1
    recorded["exports"][0]["sha256"] = "0" * 64
    lock_path.write_text(json.dumps(recorded))
    assert main([*base, "--lock", str(lock_path), "--export"]) == 1
    assert main([*base, "--lock", str(lock_path), "--export", "--export-visual"]) == 0
    capsys.readouterr()
    assert main(["--json", *base, "--lock", str(lock_path), "--export", "--export-visual", "--report"]) == 0
    assert json.loads(capsys.readouterr().out)["format"] == "vixl-reproduction"
    assert main([*base, "--export", "png"]) == 1
    assert main([*base, "--lock", str(lock_path), "--frames", "2"]) == 1
    assert main([*base, "--write-lock", str(tmp_path / "again.json"), "--export"]) == 1
    assert main([*base, "--write-lock", str(lock_path)]) == 1
    assert main([*base, "--write-lock", str(lock_path), "--overwrite", "--frames", "2"]) == 0
    assert write_lock(poster(), tmp_path / "third.json")["version"] == 2
