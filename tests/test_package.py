"""Deliverable packaging (#573): campaign outputs and exported files in one zip with a manifest."""

import hashlib
import json
import os
import shutil
import zipfile

import pytest

from vixl import Project
from vixl.cli import main
from vixl.errors import VixlError
from vixl.interfaces import Session
from vixl.plugins.workspace_qa import package
from vixl.plugins.workspace_qa.reproduce import write_lock
from vixl.production import capture_recipe, run
from vixl.timeline import export_timeline
from vixl.workflows import describe, dispatch

needs_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="MP4 export needs ffmpeg")
SUITE = {"version": 1, "rules": [{"id": "logo", "kind": "assert", "expression": "layer.logo.bounds within canvas"}]}


def banner(extra_inputs=None):
    p = Project(160, 100, "#102030")
    p.apply([
        {"type": "text", "name": "title", "text": "Hello", "size": 24, "x": 10, "y": 10},
        {"type": "shape", "name": "logo", "shape": "rectangle", "width": 10, "height": 10, "fill": "red", "x": 140,
         "y": 80},
    ])
    inputs = {"title": {"type": "string", "default": "Hello", "maxLength": 60}, **(extra_inputs or {})}
    p = capture_recipe(p, {"version": 1, "inputs": inputs}, {"title": {"target": "title", "field": "text"}})
    p.apply([{"type": "suite-set", "name": "quality", "suite": SUITE},
             {"type": "artboard", "name": "narrow", "x": 0, "y": 0, "width": 100, "height": 100}])
    return p


def campaign(tmp_path, rows=("One", "Two", "One")):
    """A run of three rows on the main canvas and the narrow artboard: the artboard variants are held."""
    p = banner()
    p.save(tmp_path / "banner.vixl")
    run(p, {"rows": [{"title": title} for title in rows], "artboards": [None, "narrow"]}, tmp_path / "out")
    return Session(None, workspace=tmp_path)


def build(session, **request):
    return dispatch(session, "package", {"production": "out/production.json", "source": "banner.vixl",
                                         "output": "delivery.zip", "name": "{doc}_{row}.{ext}", **request})


def members(path):
    with zipfile.ZipFile(path) as archive:
        return {name: archive.read(name) for name in archive.namelist()}


def sha(data):
    return hashlib.sha256(data).hexdigest()


# --- a package from a campaign run -------------------------------------------------------------------------------

def test_a_campaign_package_holds_the_passing_outputs_a_manifest_and_the_report(tmp_path):
    session = campaign(tmp_path)
    result = build(session)
    assert result["written"] and result["files"] == 2 and result["names"] == ["banner_1.png", "banner_2.png"]
    contents = members(tmp_path / "delivery.zip")
    assert set(contents) == {"banner_1.png", "banner_2.png", "SHA256SUMS", "manifest.json", "proof.html",
                             "report/check-report.json", "report/check-report.md"}
    manifest = json.loads(contents["manifest.json"])
    assert manifest["format"] == "vixl-package" and manifest["vixl_version"]
    # The outputs the run held are listed with their reason and are not in the package.
    assert [(h["id"], h["artboard"], h["status"]) for h in manifest["held"]] == [
        ("0002", "narrow", "needs_review"), ("0004", "narrow", "needs_review"), ("0006", "narrow", "needs_review")]
    assert all("logo" in h["reason"] and h["rules"] == ["logo"] for h in manifest["held"])
    assert not any("narrow" in name for name in contents)
    first = manifest["files"][0]
    assert first["source"] == {"document": "banner.vixl", "revision": sha((tmp_path / "banner.vixl").read_bytes())}
    assert first["variant"] == {"id": "0001", "row": 1}
    assert first["dimensions"] == {"width": 160, "height": 100} and first["color"]["space"] == "RGB"
    assert first["check"] == {"source": "production", "state": "validated", "validation": "passed",
                              "review": "not_required", "validated_by": ["suite quality"]}
    assert manifest["validation"] == {"files": 2, "validated": 2, "needs_review": 0, "unvalidated": 0,
                                      "fraction_validated": 1.0}
    assert manifest["visual_review"] == {"status": "not_reviewed"}
    assert manifest["inputs"]["kind"] == "production" and manifest["inputs"]["path"] == "out/production.json"
    report = json.loads(contents["report/check-report.json"])
    assert report["totals"]["passed"] == 2 and report["totals"]["needs_review"] == 3
    assert "0002 (held)" in contents["report/check-report.md"].decode()
    assert b"banner_1.png" in contents["proof.html"] and b"Content-Security-Policy" in contents["proof.html"]
    assert result["outcome"]["state"] == "needs_review" and result["outcome"]["validation"] == "passed"
    assert "3 output(s) held and left out" in result["outcome"]["review_reasons"]


def test_checksums_match_the_files_and_the_run_record(tmp_path):
    session = campaign(tmp_path)
    build(session)
    contents = members(tmp_path / "delivery.zip")
    manifest = json.loads(contents["manifest.json"])
    recorded = {r["id"]: r["sha256"] for r in json.loads((tmp_path / "out" / "production.json").read_text())["results"]
                if "sha256" in r}
    for entry in manifest["files"]:
        assert sha(contents[entry["name"]]) == entry["sha256"] and entry["bytes"] == len(contents[entry["name"]])
        assert recorded[entry["variant"]["id"]] == entry["sha256"]
    sums = dict(line.split("  ")[::-1] for line in contents["SHA256SUMS"].decode().splitlines())
    assert sums == {entry["name"]: entry["sha256"] for entry in manifest["files"]}
    assert manifest["totals"] == {"files": 2, "bytes": sum(e["bytes"] for e in manifest["files"]), "held": 3,
                                  "duplicates": 1}


def test_identical_outputs_are_packaged_once(tmp_path):
    session = campaign(tmp_path)
    result = build(session)
    assert result["duplicates"] == [next(f"out/{p.name}" for p in sorted((tmp_path / "out").glob("0005-*.png")))]
    manifest = json.loads(members(tmp_path / "delivery.zip")["manifest.json"])
    kept = manifest["files"][0]
    assert kept["variant"]["id"] == "0001" and kept["duplicates"] == [{"path": result["duplicates"][0], "id": "0005"}]


def test_a_naming_collision_is_refused_up_front_with_the_list(tmp_path):
    session = campaign(tmp_path)
    with pytest.raises(VixlError) as caught:
        build(session, name="{doc}.{ext}")
    error = caught.value
    assert error.code == "output_collision" and "banner.png" in str(error)
    assert error.details["collisions"][0]["name"] == "banner.png" and len(error.details["collisions"][0]["sources"]) == 2
    assert error.details["suggestions"][0] == 'name: "{doc}_{id}.{ext}"'
    assert not (tmp_path / "delivery.zip").exists()
    with pytest.raises(VixlError, match="reserved"):
        build(session, name="manifest.json")
    # The default template has no row, so a campaign of several rows needs one added.
    with pytest.raises(VixlError, match="used twice"):
        dispatch(session, "package", {"production": "out/production.json", "source": "banner.vixl", "output": "x.zip"})
    assert os.listdir(tmp_path / "out") and not (tmp_path / "x.zip").exists()
    # Without a source document {doc} is the output's own file name, which is already unique.
    unnamed = dispatch(session, "package", {"production": "out/production.json", "output": "x.zip"})
    assert unnamed["names"][0].startswith("0001-") and unnamed["names"][0].endswith("_160x100.png")


def test_the_package_never_overwrites_unless_asked(tmp_path):
    session = campaign(tmp_path)
    build(session)
    before = (tmp_path / "delivery.zip").read_bytes()
    with pytest.raises(VixlError) as caught:
        build(session)
    assert caught.value.code == "output_exists" and (tmp_path / "delivery.zip").read_bytes() == before
    again = build(session, overwrite=True, layout="by-format")
    assert again["written"] and "png/banner_1.png" in members(tmp_path / "delivery.zip")
    assert sorted(path.name for path in tmp_path.iterdir()) == ["banner.vixl", "delivery.zip", "out"]


def test_a_failure_while_building_leaves_nothing_behind(tmp_path, monkeypatch):
    session = campaign(tmp_path)
    before = sorted(os.listdir(tmp_path))
    monkeypatch.setattr("vixl.plugins.workspace_qa.proof.proof_page",
                        lambda *args, **kwargs: (_ for _ in ()).throw(VixlError("invalid_request", "proof broke")))
    with pytest.raises(VixlError, match="proof broke"):
        build(session)
    assert sorted(os.listdir(tmp_path)) == before
    monkeypatch.undo()
    monkeypatch.setattr(package, "publish_file", lambda *args, **kwargs: (_ for _ in ()).throw(FileExistsError()))
    with pytest.raises(VixlError) as caught:
        build(session)
    assert caught.value.code == "output_exists" and sorted(os.listdir(tmp_path)) == before


def test_a_dry_run_plans_the_names_and_writes_nothing(tmp_path):
    session = campaign(tmp_path)
    plan = build(session, dry_run=True)
    assert plan["dry_run"] and not plan["written"] and plan["names"] == ["banner_1.png", "banner_2.png"]
    assert len(plan["held"]) == 3 and len(plan["duplicates"]) == 1
    assert not (tmp_path / "delivery.zip").exists()
    with pytest.raises(VixlError, match="used twice"):
        build(session, dry_run=True, name="{doc}.{ext}")


def test_outputs_that_changed_or_vanished_after_the_run_are_held(tmp_path):
    session = campaign(tmp_path)
    outputs = sorted((tmp_path / "out").glob("*.png"))
    by_id = {path.name[:4]: path for path in outputs}
    by_id["0003"].write_bytes(by_id["0003"].read_bytes() + b"x")
    by_id["0005"].unlink()
    result = build(session)
    held = {entry["id"]: entry["reason"] for entry in result["held"]}
    assert "checksum differs" in held["0003"] and "is missing" in held["0005"]
    assert result["files"] == 1 and result["names"] == ["banner_1.png"]


def test_an_unfinished_run_and_missing_inputs_are_refused(tmp_path):
    session = campaign(tmp_path)
    path = tmp_path / "out" / "production.json"
    record = json.loads(path.read_text())
    path.write_text(json.dumps({**record, "status": "running"}))
    with pytest.raises(VixlError, match="still marked running"):
        build(session)
    path.write_text(json.dumps({**record, "results": [r for r in record["results"] if r["status"] != "completed"]}))
    with pytest.raises(VixlError) as caught:
        build(session)
    assert "Nothing to package" in str(caught.value) and len(caught.value.details["held"]) == 3
    with pytest.raises(VixlError, match="exactly one input"):
        dispatch(session, "package", {"output": "x.zip"})
    with pytest.raises(VixlError, match="exactly one input"):
        dispatch(session, "package", {"output": "x.zip", "production": "out/production.json", "files": ["out/*.png"]})
    with pytest.raises(VixlError, match=".zip"):
        dispatch(session, "package", {"output": "x.tar", "production": "out/production.json"})
    with pytest.raises(VixlError, match="not a .vixl"):
        build(session, source="out/contact-sheet.png")


def test_the_manifest_carries_a_recorded_export_check(tmp_path):
    session = campaign(tmp_path)
    path = tmp_path / "out" / "production.json"
    record = json.loads(path.read_text())
    first = next(r for r in record["results"] if r["id"] == "0001")
    first["export_check"] = {"passed": True, "findings": []}
    path.write_text(json.dumps(record))
    build(session)
    manifest = json.loads(members(tmp_path / "delivery.zip")["manifest.json"])
    assert manifest["files"][0]["export_check"] == {"passed": True, "findings": []}
    assert "export_check" not in manifest["files"][1]


# --- exported files ----------------------------------------------------------------------------------------------

def exported(tmp_path):
    good, bad = banner(), banner()
    bad.apply({"type": "move", "target": "logo", "x": 159})
    good.save(tmp_path / "good.vixl")
    bad.save(tmp_path / "bad.vixl")
    (tmp_path / "exports").mkdir()
    good.export(tmp_path / "exports" / "good.png")
    good.export(tmp_path / "exports" / "good.pdf")
    bad.export(tmp_path / "exports" / "bad.png")
    return Session(None, workspace=tmp_path)


def test_files_are_packaged_with_the_checks_of_their_source_documents(tmp_path):
    session = exported(tmp_path)
    result = dispatch(session, "package", {
        "files": [{"path": "exports/good.*", "source": "good.vixl"}, {"path": "exports/bad.png", "source": "bad.vixl"}],
        "output": "delivery.zip", "name": "{doc}.{ext}", "brand": "Acme Co."})
    assert result["names"] == ["good.pdf", "good.png"]
    assert [(h["path"], h["status"]) for h in result["held"]] == [("exports/bad.png", "failed")]
    assert "bad.vixl failed its checks" in result["held"][0]["reason"]
    contents = members(tmp_path / "delivery.zip")
    manifest = json.loads(contents["manifest.json"])
    png, pdf = (next(f for f in manifest["files"] if f["format"] == fmt) for fmt in ("png", "pdf"))
    assert png["check"]["source"] == "check-all" and png["check"]["status"] in ("passed", "needs_review")
    assert pdf["dimensions"]["unit"] == "pt" and pdf["dimensions"]["pages"] == 1 and pdf["color"]["space"] == "RGB"
    report = json.loads(contents["report/check-report.json"])
    assert [d["path"] for d in report["documents"]] == ["bad.vixl", "good.vixl"]
    assert manifest["inputs"] == {"kind": "files", "patterns": ["exports/good.*", "exports/bad.png"]}
    assert (tmp_path / "exports" / "good.png").read_bytes() == contents["good.png"]
    # Nothing was written to the workspace's check history by packaging.
    assert not (tmp_path / ".vixl-checks").exists()


def test_files_without_a_source_are_unvalidated_and_named_from_the_brand_and_size(tmp_path):
    session = exported(tmp_path)
    (tmp_path / "brand.json").write_text(json.dumps({"name": "Acme"}))
    result = dispatch(session, "package", {"files": ["exports/good.png"], "output": "p.zip"})
    assert result["names"] == ["Acme_good_160x100.png"]
    manifest = json.loads(members(tmp_path / "p.zip")["manifest.json"])
    assert manifest["files"][0]["check"] == {"source": "none", "state": "unvalidated", "status": "not_checked"}
    assert "source" not in manifest["files"][0] and manifest["check_report"] is None
    assert result["outcome"]["validation"] == "not_run"
    assert "report/check-report.json" not in members(tmp_path / "p.zip")


def test_file_inputs_are_workspace_relative_and_must_exist(tmp_path):
    session = exported(tmp_path)
    for files in (["../outside.png"], ["/etc/passwd"], ["exports/nothing-*.png"], ["exports/missing.png"],
                  [{"path": "exports/good.png", "extra": 1}]):
        with pytest.raises(VixlError):
            dispatch(session, "package", {"files": files, "output": "p.zip"})
    first = dispatch(session, "package", {"files": ["exports/*.png"], "output": "exports/p.zip", "name": "{doc}.{ext}"})
    assert first["names"] == ["bad.png", "good.png"]
    # A package that already sits in the folder is never packaged into itself.
    again = dispatch(session, "package", {"files": ["exports/*"], "output": "exports/p.zip", "overwrite": True,
                                          "name": "{doc}.{ext}"})
    assert again["names"] == ["bad.png", "good.pdf", "good.png"]


def test_template_tokens_collapse_and_layouts_group_files(tmp_path):
    assert package.fill("{brand}_{doc}_{artboard}_{w}x{h}.{ext}", {"doc": "poster", "w": "100", "h": "50", "ext": "png",
                                                                     "size": "100x50"}) == "poster_100x50.png"
    assert package.fill("{doc}_{w}x{h}.{ext}", {"doc": "doc", "ext": "pdf"}) == "doc.pdf"
    assert package.fill("{doc}-{locale}-{row}.{ext}", {"doc": "d", "locale": "fr", "row": "3", "ext": "png"}) == "d-fr-3.png"
    for bad in ("{nope}.png", "a/b.png", "{doc.png", ".hidden", "", "x" * 300):
        with pytest.raises(VixlError):
            package.check_template(bad)
    session = campaign(tmp_path)
    result = build(session, layout="by-artboard", name="{doc}_{row}.{ext}")
    assert result["names"] == ["default/banner_1.png", "default/banner_2.png"]
    assert package.slug("Acme Co. / New!") == "Acme-Co.-New"


def test_the_row_values_name_the_locale(tmp_path):
    p = banner({"locale": {"type": "string", "default": "en"}})
    p.save(tmp_path / "banner.vixl")
    run(p, {"rows": [{"title": "Hola", "locale": "es"}, {"title": "Bonjour", "locale": "fr"}]}, tmp_path / "out")
    session = Session(None, workspace=tmp_path)
    result = dispatch(session, "package", {"production": "out/production.json", "source": "banner.vixl",
                                           "output": "p.zip", "name": "{doc}_{locale}.{ext}"})
    assert result["names"] == ["banner_es.png", "banner_fr.png"]


# --- visual review and reproduction ------------------------------------------------------------------------------

def test_downloaded_decisions_set_the_visual_review_status(tmp_path):
    session = campaign(tmp_path)
    decisions = {"items": [{"path": "banner_1.png", "decision": "approved"},
                           {"path": "out/0003-nothing.png", "decision": "rejected", "note": "wrong crop"}]}
    partial = build(session, decisions=decisions)
    assert partial["visual_review"] == {"status": "pending", "approved": 1, "pending": 1, "rejected": 0}
    (tmp_path / "decisions.json").write_text(json.dumps({"items": [
        {"path": "banner_1.png", "decision": "approved"},
        {"path": next(f"out/{p.name}" for p in (tmp_path / "out").glob("0003-*.png")), "decision": "rejected",
         "note": "wrong crop"}]}))
    result = build(session, decisions="decisions.json", overwrite=True)
    assert result["names"] == ["banner_1.png"]
    assert result["visual_review"] == {"status": "approved", "approved": 1, "pending": 0, "rejected": 1}
    rejected = next(h for h in result["held"] if h["status"] == "rejected")
    assert rejected["reason"] == "rejected in visual review" and rejected["note"] == "wrong crop"
    manifest = json.loads(members(tmp_path / "delivery.zip")["manifest.json"])
    assert manifest["files"][0]["review"] == "approved" and result["outcome"]["validation"] == "passed"
    with pytest.raises(VixlError, match="decision is one of"):
        build(session, decisions={"items": [{"path": "a", "decision": "maybe"}]}, overwrite=True)
    with pytest.raises(VixlError, match="downloaded decisions"):
        build(session, decisions={"nope": []}, overwrite=True)


def test_the_reproduction_check_of_a_lockfile_goes_into_the_manifest(tmp_path):
    session = campaign(tmp_path)
    source = Project.load(tmp_path / "banner.vixl")
    write_lock(source, tmp_path / "banner.lock.json", exports=["png"])
    result = build(session, lock="banner.lock.json")
    summary = result["reproduction"]["banner.vixl"]
    assert summary["lockfile"] == "banner.lock.json" and summary["reproducible"] and summary["byte_identical"] is True
    assert summary["format"] == "vixl-reproduction" and summary["lock"]["exports"] == 1
    manifest = json.loads(members(tmp_path / "delivery.zip")["manifest.json"])
    assert manifest["reproduction"]["banner.vixl"]["reproduction"] == "reference-verified"
    # A document that changed since the lock fails the check; the package is still written, and says so.
    source.apply({"type": "text-set", "target": "title", "text": "Changed"})
    source.save(tmp_path / "banner.vixl")
    drifted = build(session, lock="banner.lock.json", overwrite=True)
    assert drifted["reproduction"]["banner.vixl"]["reproducible"] is False
    assert drifted["outcome"]["validation"] == "failed"
    assert "reproduction check failed for banner.vixl" in drifted["outcome"]["review_reasons"]
    with pytest.raises(VixlError, match="single source"):
        dispatch(session, "package", {"files": ["out/0001-*.png"], "output": "q.zip", "lock": "banner.lock.json",
                                      "name": "{doc}.{ext}"})


# --- stream metadata ---------------------------------------------------------------------------------------------

def test_animated_images_report_their_frames(tmp_path):
    p = Project(160, 120, "#ffffff")
    p.apply([{"type": "shape", "shape": "ellipse", "name": "ball", "x": 10, "y": 40, "width": 40, "height": 40,
              "fill": "#2a9d8f"},
             {"type": "timeline-set", "duration": 600, "fps": 10},
             {"type": "animate", "target": "ball", "property": "x", "from": 0, "to": 100, "easing": "linear"}])
    (tmp_path / "exports").mkdir()
    export_timeline(p, tmp_path / "exports" / "loop.gif")
    facts = package.inspect_file(tmp_path / "exports" / "loop.gif")
    assert facts["width"] == 160 and facts["stream"]["frames"] == 6 and facts["stream"]["container"] == "gif"
    assert facts["stream"]["duration_ms"] == 600


@needs_ffmpeg
def test_video_streams_are_read_back_from_the_encoded_file(tmp_path):
    p = Project(160, 120, "#ffffff")
    p.apply([{"type": "shape", "shape": "ellipse", "name": "ball", "x": 10, "y": 40, "width": 40, "height": 40,
              "fill": "#2a9d8f"},
             {"type": "timeline-set", "duration": 600, "fps": 10},
             {"type": "animate", "target": "ball", "property": "x", "from": 0, "to": 100, "easing": "linear"}])
    (tmp_path / "exports").mkdir()
    export_timeline(p, tmp_path / "exports" / "loop.mp4")
    session = Session(None, workspace=tmp_path)
    dispatch(session, "package", {"files": ["exports/loop.mp4"], "output": "v.zip", "name": "{doc}.{ext}", "proof": False})
    entry = json.loads(members(tmp_path / "v.zip")["manifest.json"])["files"][0]
    video = entry["stream"]["video"]
    assert video["codec"] == "h264" and video["fps"] == 10 and video["frames"] == 6 and video["duration_ms"] == 600
    assert entry["dimensions"] == {"width": 160, "height": 120} and entry["color"]["pix_fmt"] == "yuv420p"
    assert "audio" not in entry["stream"]


def test_inspecting_files_reads_headers_and_survives_damage(tmp_path):
    p = banner()
    p.export(tmp_path / "a.pdf")
    p.export(tmp_path / "a.svg")
    p.export(tmp_path / "a.pptx")
    p.export(tmp_path / "a.psd")
    p.export(tmp_path / "a.tiff", color_space="cmyk")
    (tmp_path / "broken.png").write_bytes(b"not a png")
    assert package.inspect_file(tmp_path / "a.pdf")["pages"] == 1
    assert package.inspect_file(tmp_path / "a.svg")["width"] == 160
    assert package.inspect_file(tmp_path / "a.pptx")["pages"] == 1
    assert (package.inspect_file(tmp_path / "a.psd")["width"], package.inspect_file(tmp_path / "a.psd")["color"]) == (
        160, {"space": "RGB"})
    assert package.inspect_file(tmp_path / "a.tiff")["color"]["space"] == "CMYK"
    broken = package.inspect_file(tmp_path / "broken.png")
    assert broken["bytes"] == 9 and "UnidentifiedImageError" in broken["unreadable"]
    assert package.inspect_file(tmp_path / "broken.png")["format"] == "png"


# --- surfaces ----------------------------------------------------------------------------------------------------

def test_the_action_is_described_and_reachable_through_the_cli(tmp_path, capsys):
    action = describe()["actions"]["package"]
    assert action["required"] == ["output"] and "production" in action["fields"] and "files" in action["fields"]
    assert all(action["properties"][field]["description"] for field in action["fields"])
    assert action["properties"]["layout"]["enum"] == ["flat", "by-format", "by-artboard"]
    campaign(tmp_path)
    base = ["--json", "package", "--workspace", str(tmp_path), "--production", "out/production.json", "--source",
            "banner.vixl", "--output", "cli.zip", "--name", "{doc}_{row}.{ext}"]
    assert main([*base, "--dry-run"]) == 0
    assert json.loads(capsys.readouterr().out)["names"] == ["banner_1.png", "banner_2.png"]
    assert not (tmp_path / "cli.zip").exists()
    assert main(base) == 0
    assert json.loads(capsys.readouterr().out)["written"] is True
    assert main(base) == 1 and "already exists" in capsys.readouterr().err
    assert main([*base, "--overwrite", "--no-check", "--no-proof", "--layout", "by-format"]) == 0
    assert sorted(members(tmp_path / "cli.zip")) == ["SHA256SUMS", "manifest.json", "png/banner_1.png",
                                                      "png/banner_2.png"]
    assert main(["package", "--workspace", str(tmp_path), "--files", "out/0001-*.png", "--output", "f.zip",
                 "--name", "{id}.{ext}", "--lock", "a=b", "--lock", "c"]) == 1
