"""Behavioral coverage for saved design contracts and resumable production."""

from copy import deepcopy
import json
import zipfile

import pytest
from PIL import Image

from vixl import Project
from vixl.errors import VixlError
from vixl.interfaces import Session, create_app
from vixl.production import Library, capture_recipe, plan, run
from vixl.jobs import Queue
from vixl.workflows import dispatch


def document():
    p = Project(160, 100, "#102030")
    p.apply(
        [
            {"type": "text", "name": "title", "text": "Hello", "size": 24, "x": 10, "y": 10},
            {
                "type": "shape",
                "name": "logo",
                "shape": "rectangle",
                "width": 10,
                "height": 10,
                "fill": "red",
                "x": 140,
                "y": 80,
            },
        ]
    )
    return p


def suite():
    return {
        "version": 1,
        "rules": [{"id": "logo", "kind": "assert", "expression": "layer.logo.bounds within canvas"}],
    }


def recipe(p):
    return capture_recipe(
        p,
        {"version": 1, "inputs": {"title": {"type": "string", "default": "Hello", "maxLength": 60}}},
        {"title": {"target": "title", "field": "text"}},
    )


def test_contract_roundtrip_and_checked_action_rollback(tmp_path):
    p = document()
    p.apply({"type": "suite-set", "name": "quality", "suite": suite()})
    p.save(tmp_path / "p.vixl")
    p = Project.load(tmp_path / "p.vixl")
    assert p.check_suite("quality")["passed"]
    before, head = deepcopy(p.state), p.head
    result = p.act({"type": "move", "target": "logo", "x": 159}, suites=["quality"])
    assert not result["committed"] and not result["success"]
    assert p.state == before and p.head == head
    result = p.act({"type": "move", "target": "logo", "x": 120}, suites=["quality"])
    assert result["committed"] and result["bounds"]["logo"][0] == 120
    p.undo()
    assert p.state == before


def test_contract_cannot_be_weakened_by_repair():
    p = document()
    p.apply({"type": "suite-set", "name": "quality", "suite": suite()})
    changed = suite()
    changed["rules"][0]["expression"] = "canvas.width == 160"
    op = {"type": "suite-set", "name": "quality", "suite": changed}
    with pytest.raises(VixlError, match="rewrite suites"):
        p.act(op, suites=["quality"])
    with pytest.raises(VixlError, match="Actions cannot"):
        p.apply({"type": "action-define", "name": "cheat", "action": {"operations": [op]}})
    assert p.check_suite("quality")["passed"]


def test_unmeasurable_is_review_not_pass():
    p = document()
    report = p.check_suite(
        {"rules": [{"id": "missing", "kind": "property", "target": "absent", "field": "size", "expected": 1}]}
    )
    assert report["status"] == "needs_review" and not report["passed"]


def test_saved_baselines_detect_real_changes_and_keep_pixels(tmp_path):
    p = document()
    p.apply({"type": "suite-capture", "name": "protected", "targets": ["logo"], "regions": [[0, 0, 5, 5]]})
    p.save(tmp_path / "p.vixl")
    p = Project.load(tmp_path / "p.vixl")
    assert p.check_suite("protected")["passed"]
    p.apply({"type": "move", "target": "logo", "x": 130})
    assert p.check_suite("protected")["status"] == "failed"
    with pytest.raises(VixlError, match="Baseline already"):
        p.apply({"type": "suite-capture", "name": "protected", "targets": ["logo"]})


def test_motion_role_stagger_relative_steps_and_interval_checks():
    p = document()
    p.apply(
        [
            {"type": "role-set", "name": "items", "targets": ["title", "logo"]},
            {
                "type": "motion-define",
                "name": "reveal",
                "motion": {
                    "steps": [
                        {
                            "id": "entry",
                            "role": "items",
                            "preset": "fade-in",
                            "duration": 200,
                            "stagger": 100,
                        },
                        {
                            "role": "items",
                            "property": "translate-x",
                            "from": 0,
                            "to": 100,
                            "after": "entry",
                            "duration": 200,
                        },
                    ]
                },
            },
            {"type": "motion-apply", "name": "reveal"},
        ]
    )
    tracks = p.state["timeline"]["tracks"]
    assert len(tracks) == 4
    starts = sorted(t["keys"][0]["time"] for t in tracks if t["property"] == "opacity")
    assert starts == [0, 100]
    spec = suite()
    spec["sampling"] = {"mode": "times", "times": [0, 500]}
    result = p.check_suite(spec)
    assert result["status"] == "failed"
    assert any(r["time"] == 500 and r["status"] == "failed" for r in result["results"])


def test_fit_text_enforces_minimum_and_is_atomic():
    p = document()
    p.apply({"type": "fit-text", "target": "title", "width": 70, "height": 35, "minimum": 12})
    result = p.check_suite({"rules": [{"id": "fits", "kind": "text-fit", "target": "title", "minimum": 12}]})
    assert result["passed"]
    before = deepcopy(p.state)
    with pytest.raises(VixlError, match="cannot fit"):
        p.apply({"type": "fit-text", "target": "title", "width": 1, "height": 1, "minimum": 12})
    assert before == p.state


def test_grid_and_adaptation_do_not_clip():
    p = document()
    p.apply({"type": "arrange-grid", "targets": ["title", "logo"], "columns": 1, "gap": 10, "x": 5, "y": 5})
    bounds = p.inspect()["layers"]
    assert bounds[1]["y"] > bounds[0]["y"]
    p.apply({"type": "adapt-layout", "targets": ["title", "logo"], "width": 100, "height": 200, "margin": 5})
    before = deepcopy(p.state)
    with pytest.raises(VixlError):
        p.apply({"type": "adapt-layout", "targets": ["title", "logo"], "width": 20, "height": 20})
    assert before == p.state


def test_typed_recipe_batch_resume_and_selective_rebuild(tmp_path):
    p = recipe(document())
    spec = {"rows": [{"title": "One"}, {"title": "Two"}], "workers": 2}
    first = run(p, spec, tmp_path)
    assert first["status"] == "completed", first
    assert (tmp_path / "contact-sheet.png").exists()
    second = run(p, spec, tmp_path)
    assert [r["status"] for r in second["results"]] == ["reused", "reused"]
    spec["rows"][1]["title"] = "Three"
    third = run(p, spec, tmp_path)
    assert [r["status"] for r in third["results"]] == ["reused", "completed"]
    assert third["results"][0]["sha256"] == first["results"][0]["sha256"]
    assert third["results"][1]["sha256"] != first["results"][1]["sha256"]
    assert p.layer("title")["text"] == "${title}"


def test_recipe_invalid_values_and_failed_checks_do_not_publish(tmp_path):
    p = recipe(document())
    p.apply({"type": "suite-set", "name": "quality", "suite": suite()})
    p.apply({"type": "move", "target": "logo", "x": 159})
    result = run(p, {"rows": [{"title": "Fine"}, {"title": 123}]}, tmp_path)
    assert [r["status"] for r in result["results"]] == ["needs_review", "failed"]
    assert not list(tmp_path.glob("*.png"))


def test_bounded_repair_retains_suite(tmp_path):
    p = document()
    p.apply(
        [
            {"type": "suite-set", "name": "quality", "suite": suite()},
            {
                "type": "action-define",
                "name": "fix-logo",
                "action": {"operations": [{"type": "move", "target": "logo", "x": 120}]},
            },
            {"type": "move", "target": "logo", "x": 159},
        ]
    )
    result = run(p, {"repair_actions": ["fix-logo"]}, tmp_path)
    assert result["status"] == "completed"
    assert result["results"][0]["repairs"] == ["fix-logo"]
    assert p.layer("logo")["x"] == 159


def test_plan_reports_cartesian_size_and_rejects_explosion():
    assert (
        plan(
            {
                "rows": [{"name": "a"}, {"name": "b"}],
                "matrix": {"color": ["red", "blue"]},
                "artboards": ["story", "square"],
            }
        )["count"]
        == 8
    )
    with pytest.raises(VixlError, match="10000"):
        plan({"matrix": {"a": list(range(100)), "b": list(range(100)), "c": [1, 2]}})


def test_draft_final_preserves_source_and_uses_no_provider(tmp_path):
    p = Project(1280, 720, "red")
    p.save(tmp_path / "p.vixl")
    session = Session(tmp_path / "p.vixl")
    draft = dispatch(session, "preview", {"output": "draft.png", "quality": "draft"})
    final = dispatch(session, "preview", {"output": "final.png", "quality": "final"})
    assert draft["size"] == [640, 360] and final["size"] == [1280, 720]
    assert draft["generation_calls"] == final["generation_calls"] == 0
    assert Project.load(tmp_path / "p.vixl").state == p.state


def test_disk_cache_reuse_invalidation_and_corruption(tmp_path):
    from vixl.render_cache import enable

    p = enable(document(), tmp_path)
    original = p.render().tobytes()
    fresh = p.clone()
    fresh._cache = {}
    assert fresh.render().tobytes() == original
    assert fresh._disk_cache.hits > 0
    p.apply({"type": "move", "target": "logo", "x": 120})
    assert p.render().tobytes() != original
    for file in tmp_path.glob("*.png"):
        file.write_bytes(b"corrupt")
    p._cache = {}
    assert p.render().size == (160, 100)


def test_library_roundtrip_reuses_embedded_assets(tmp_path):
    p = document()
    library = Library(tmp_path / "library")
    saved = library.save(p, "hero", "Reusable red logo", ["campaign"])
    assert library.search("red campaign")[0]["id"] == saved["id"]
    loaded = library.load(saved["id"], limits=p.limits)
    assert loaded.render().tobytes() == p.render().tobytes()
    target = Project(160, 100)
    library.place(target, saved["id"], "placed")
    assert target.layer("placed")["type"] == "raster"
    assert target.render().tobytes() == p.render().tobytes()
    with pytest.raises(VixlError):
        library.load("../../outside")


def test_jobs_snapshot_cancel_resume_and_restart(tmp_path):
    p = recipe(document())
    p.save(tmp_path / "source.vixl")
    queue = Queue(tmp_path)
    job = queue.submit(
        {
            "kind": "production",
            "source": "source.vixl",
            "output": "campaign",
            "spec": {"rows": [{"title": "One"}]},
        }
    )
    p.apply({"type": "move", "target": "logo", "x": 20})
    p.save()
    frozen = Project.load(tmp_path / job["payload"]["source"])
    assert frozen.layer("logo")["x"] == 140
    queue.cancel(job["id"])
    assert Queue(tmp_path).work_one(job["id"])["status"] == "cancelled"
    queue.resume(job["id"])
    assert Queue(tmp_path).work_one(job["id"])["status"] == "completed"
    assert Queue(tmp_path).status(job["id"])["progress"]["done"] == 1


def test_uncertain_image_request_never_repeats(tmp_path):
    p = document()
    p.save(tmp_path / "source.vixl")
    queue = Queue(tmp_path)
    job = queue.submit(
        {
            "kind": "generate",
            "source": "source.vixl",
            "output": "generated.vixl",
            "provider": "configured",
            "request": {"prompt": "A tree", "width": 160, "height": 100},
        }
    )
    job.update(status="running", request_started=True)
    queue.save(job)
    result = Queue(tmp_path).work_one(job["id"])
    assert result["status"] == "needs_review"
    with pytest.raises(VixlError, match="uncertain"):
        queue.resume(job["id"])


def test_video_gateway_polls_same_remote_job(tmp_path, monkeypatch):
    import base64

    calls = []

    class Backend:
        def json(self, method, route, **kwargs):
            calls.append((method, route))
            if method == "POST":
                return {"id": "remote-1", "status": "running"}
            return {
                "id": "remote-1",
                "status": "completed",
                "format": "mp4",
                "video_base64": base64.b64encode(b"\x00\x00\x00\x18ftypisom").decode(),
            }

    monkeypatch.setattr(Queue, "video_backend", staticmethod(lambda name: Backend()))
    queue = Queue(tmp_path)
    job = queue.submit(
        {
            "kind": "video",
            "provider": "studio",
            "request": {"prompt": "A tree", "width": 128, "height": 128, "duration": 2},
            "output": "tree.mp4",
        }
    )
    result = queue.work_one(job["id"])
    assert result["status"] == "waiting" and result["remote_id"] == "remote-1"
    queue.resume(job["id"])
    result = Queue(tmp_path).work_one(job["id"])
    assert result["status"] == "completed"
    assert calls == [("POST", "/video/jobs"), ("GET", "/video/jobs/remote-1")]


def test_film_crossfade_frames_and_atomic_cancellation(tmp_path):
    from vixl.film import export, frames

    Image.new("RGBA", (32, 32), "red").save(tmp_path / "red.png")
    Image.new("RGBA", (32, 32), "blue").save(tmp_path / "blue.png")
    spec = {
        "version": 1,
        "width": 32,
        "height": 32,
        "fps": 10,
        "shots": [
            {"source": "red.png", "duration": 500},
            {"source": "blue.png", "duration": 500, "transition": 200},
        ],
    }
    rendered = list(frames(spec, tmp_path))
    assert len(rendered) == 8
    assert rendered[0].getpixel((0, 0)) == (255, 0, 0, 255)
    assert rendered[3].getpixel((0, 0))[0] > 0 and rendered[3].getpixel((0, 0))[2] > 0
    assert rendered[-1].getpixel((0, 0)) == (0, 0, 255, 255)
    export(spec, tmp_path, tmp_path / "film.zip")
    with zipfile.ZipFile(tmp_path / "film.zip") as archive:
        assert len(archive.namelist()) == 9
        assert json.loads(archive.read("timing.json"))["frames"] == 8
    with pytest.raises(VixlError, match="cancelled"):
        export(spec, tmp_path, tmp_path / "cancelled.zip", cancelled=lambda: True)
    assert not (tmp_path / "cancelled.zip").exists()


def test_workspace_escape_and_rest_scope(tmp_path):
    from fastapi.testclient import TestClient

    p = document()
    p.save(tmp_path / "p.vixl")
    session = Session(tmp_path / "p.vixl")
    with pytest.raises(VixlError, match="outside"):
        dispatch(session, "preview", {"output": "../escape.png"})
    client = TestClient(create_app(tmp_path / "p.vixl"))
    result = client.post("/workflow/check", json={"suite": suite()})
    assert result.status_code == 200 and result.json()["passed"]
    result = client.post("/workflow/run", json={"spec": {}, "output": "output"})
    assert result.status_code == 403


def test_cli_check_failure_exit_and_discovery(tmp_path):
    from vixl.cli import main, dispatch as cli

    p = document()
    p.apply({"type": "move", "target": "logo", "x": 159})
    p.save(tmp_path / "p.vixl")
    request = tmp_path / "request.json"
    request.write_text(json.dumps({"suite": suite()}))
    assert (
        main(
            [
                "-p",
                str(tmp_path / "p.vixl"),
                "workflow",
                "check",
                "--workspace",
                str(tmp_path),
                "--request",
                str(request),
            ]
        )
        == 1
    )
    value, _ = cli(["workflow", "schema"])
    assert "submit" in value["actions"]


def test_mcp_has_production_tools(tmp_path):
    import asyncio
    from vixl.interfaces import mcp_server

    server = mcp_server(workspace=tmp_path)
    tools = asyncio.run(server.list_tools())
    assert {"vixl_workflow", "vixl_workflow_schema"} <= {t.name for t in tools}


def test_new_layers_in_actions_still_reuse_identical_outputs(tmp_path):
    p = document()
    p.apply(
        {
            "type": "action-define",
            "name": "badge",
            "action": {
                "operations": [{"type": "solid", "name": "badge", "width": 10, "height": 10, "color": "blue"}]
            },
        }
    )
    spec = {"actions": ["badge"]}
    assert run(p, spec, tmp_path)["status"] == "completed"
    assert run(p, spec, tmp_path)["results"][0]["status"] == "reused"


def test_row_inputs_override_artboard_defaults(tmp_path):
    p = recipe(document())
    p.apply(
        {"type": "artboard", "name": "square", "width": 160, "height": 160, "variables": {"title": "Board"}}
    )
    report = run(p, {"rows": [{"title": "Row"}], "artboards": ["square"]}, tmp_path)
    assert report["status"] == "completed"
    from vixl.design_render import artboard_project

    expected = artboard_project(p, "square", variables={"title": "Row"}).render()
    with Image.open(tmp_path / report["results"][0]["output"]) as actual:
        assert actual.tobytes() == expected.tobytes()


def test_film_camera_captions_and_video_audio_codec(tmp_path, monkeypatch):
    import shutil
    import wave
    from vixl.film import frames, export

    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        helper = pytest.importorskip("imageio_ffmpeg")
        ffmpeg = helper.get_ffmpeg_exe()
    original_which = shutil.which
    monkeypatch.setattr(shutil, "which", lambda name: ffmpeg if name == "ffmpeg" else original_which(name))
    image = Image.new("RGB", (64, 64), "red")
    for x in range(32, 64):
        for y in range(64):
            image.putpixel((x, y), (0, 0, 255))
    image.save(tmp_path / "source.png")
    with wave.open(str(tmp_path / "audio.wav"), "wb") as audio:
        audio.setparams((1, 2, 8000, 8000, "NONE", "not compressed"))
        audio.writeframes(b"\0" * 16000)
    spec = {
        "width": 64,
        "height": 64,
        "fps": 10,
        "shots": [
            {
                "source": "source.png",
                "duration": 1000,
                "camera": {"from": [0.25, 0.5, 2], "to": [0.75, 0.5, 2]},
            }
        ],
        "captions": [{"text": "Hi", "start": 200, "end": 600, "size": 12, "x": 5, "y": 5}],
        "audio": [{"source": "audio.wav"}],
    }
    pictures = list(frames(spec, tmp_path))
    assert pictures[0].getpixel((0, 0))[:3] == (255, 0, 0)
    assert pictures[-1].getpixel((63, 0))[:3] == (0, 0, 255)
    report = export(spec, tmp_path, tmp_path / "film.mp4")
    assert report["frames"] == 10 and (tmp_path / "film.mp4").stat().st_size > 1000
    # A generated/previously encoded clip can itself become a later shot.
    clip = {"width": 64, "height": 64, "fps": 10, "shots": [{"source": "film.mp4", "duration": 500}]}
    assert len(list(frames(clip, tmp_path))) == 5


def test_mcp_executes_contract_workflow(tmp_path):
    import asyncio
    from vixl.interfaces import mcp_server

    p = document()
    p.save(tmp_path / "p.vixl")
    server = mcp_server(tmp_path / "p.vixl")

    async def invoke():
        return await server.call_tool("vixl_workflow", {"action": "check", "request": {"suite": suite()}})

    blocks = asyncio.run(invoke())
    if isinstance(blocks, tuple):
        blocks = blocks[0]
    assert json.loads(blocks[0].text)["passed"]


def test_template_typed_inputs_motion_and_suites(tmp_path, monkeypatch):
    from vixl.resources import register, create_template

    monkeypatch.setenv("VIXL_RESOURCES", str(tmp_path / "resources.json"))
    register(
        "templates",
        "typed",
        {
            "width": 100,
            "height": 100,
            "defaults": {"title": "Hi"},
            "inputs": {"title": {"type": "string", "maxLength": 20}},
            "operations": [{"type": "text", "name": "title", "text": "${title}", "size": 15}],
            "suites": {
                "quality": {"rules": [{"id": "exists", "kind": "assert", "expression": "layer.title.exists"}]}
            },
            "roles": {"headline": ["title"]},
            "motions": {"entry": {"steps": [{"role": "headline", "preset": "fade-in", "duration": 200}]}},
        },
    )
    p = create_template("typed", {"title": "Changed"})
    assert p.check_suite("quality")["passed"]
    p.apply({"type": "motion-apply", "name": "entry"})
    assert p.state["timeline"]["tracks"]
    with pytest.raises(VixlError):
        create_template("typed", {"title": 1})


def test_cancelled_image_result_is_preserved_and_resume_does_not_regenerate(tmp_path, monkeypatch):
    from vixl import ai

    p = document()
    p.save(tmp_path / "source.vixl")
    queue = Queue(tmp_path)
    job = queue.submit(
        {
            "kind": "generate",
            "source": "source.vixl",
            "output": "generated.vixl",
            "provider": "configured",
            "request": {"prompt": "A tree", "width": 160, "height": 100},
        }
    )
    calls = []

    def generate(project, request, provider):
        calls.append(1)
        project.apply({"type": "solid", "name": "generated", "width": 20, "height": 20, "color": "green"})
        queue.cancel(job["id"])
        return {"layer": project.layer("generated")["id"]}

    monkeypatch.setattr(ai, "generate", generate)
    monkeypatch.setattr(ai, "provider", lambda name: object())
    first = queue.work_one(job["id"])
    assert first["status"] == "cancelled" and queue.checkpoint_path(first).exists()
    assert not (tmp_path / "generated.vixl").exists()
    queue.resume(job["id"])
    assert Queue(tmp_path).work_one(job["id"])["status"] == "completed"
    assert Project.load(tmp_path / "generated.vixl").layer("generated")
    assert len(calls) == 1


def test_film_job_freezes_inputs_and_recovers_publication(tmp_path, monkeypatch):
    from vixl import film

    Image.new("RGB", (16, 16), "red").save(tmp_path / "shot.png")
    queue = Queue(tmp_path)
    job = queue.submit(
        {
            "kind": "film",
            "output": "movie.zip",
            "spec": {
                "width": 16,
                "height": 16,
                "fps": 10,
                "shots": [{"source": "shot.png", "duration": 200}],
            },
        }
    )
    Image.new("RGB", (16, 16), "blue").save(tmp_path / "shot.png")
    result = queue.work_one(job["id"])
    assert result["status"] == "completed", result
    import io

    with zipfile.ZipFile(tmp_path / "movie.zip") as archive:
        with Image.open(io.BytesIO(archive.read("000000.png"))) as frame:
            assert frame.getpixel((0, 0))[:3] == (255, 0, 0)
    result["status"] = "running"
    queue.save(result)
    monkeypatch.setattr(
        film, "export", lambda *args, **kwargs: pytest.fail("Already rendered film was repeated")
    )
    assert Queue(tmp_path).work_one(job["id"])["status"] == "completed"


def test_worker_process_completes_durable_job(tmp_path):
    import subprocess
    import sys

    p = document()
    p.save(tmp_path / "source.vixl")
    queue = Queue(tmp_path)
    job = queue.submit({"kind": "production", "source": "source.vixl", "output": "campaign", "spec": {}})
    result = subprocess.run(
        [sys.executable, "-m", "vixl.jobs", str(tmp_path), "1"], capture_output=True, timeout=30
    )
    assert result.returncode == 0, result.stderr.decode()
    assert queue.status(job["id"])["status"] == "completed"


def test_fitting_shared_typography_only_changes_target():
    p = document()
    p.apply(
        [
            {"type": "text", "name": "second", "text": "Hello", "size": 12},
            {"type": "style-define", "name": "Heading", "settings": {"size": 40}},
            {"type": "style-apply", "name": "Heading", "target": "title"},
            {"type": "style-apply", "name": "Heading", "target": "second"},
            {"type": "fit-text", "target": "title", "width": 55, "height": 25, "minimum": 10},
        ]
    )
    from vixl.render import resolved_layers

    layers = {x["name"]: x for x in resolved_layers(p)}
    assert layers["second"]["size"] == 40
    assert layers["title"]["size"] < 40
    assert "character_style" not in p.layer("title")


def test_cache_works_when_frozen_metadata_is_missing(tmp_path, monkeypatch):
    from vixl import render_cache
    from importlib.metadata import PackageNotFoundError

    def missing(package):
        raise PackageNotFoundError(package)

    render_cache.environment.cache_clear()
    monkeypatch.setattr(render_cache, "version", missing)
    try:
        p = render_cache.enable(document(), tmp_path)
        first = p.render().tobytes()
        assert p.render().tobytes() == first
        assert p._disk_cache.hits > 0
    finally:
        render_cache.environment.cache_clear()


def test_protected_group_includes_child_content():
    p = document()
    p.apply(
        [
            {"type": "group", "name": "brand", "targets": ["title", "logo"]},
            {"type": "suite-capture", "name": "brand-check", "targets": ["brand"]},
        ]
    )
    assert p.check_suite("brand-check")["passed"]
    p.apply({"type": "text-set", "target": "title", "text": "Changed"})
    assert not p.check_suite("brand-check")["passed"]


def test_malformed_plans_and_template_metadata_fail_with_structured_errors(tmp_path, monkeypatch):
    from vixl.film import plan as film_plan
    from vixl.resources import register

    monkeypatch.setenv("VIXL_RESOURCES", str(tmp_path / "resources.json"))
    with pytest.raises(VixlError):
        film_plan({"shots": []})
    with pytest.raises(VixlError):
        Queue(tmp_path).submit({"kind": "production", "output": "campaign"})
    with pytest.raises(VixlError):
        register(
            "templates",
            "invalid",
            {
                "width": 10,
                "height": 10,
                "suites": [],
                "operations": [{"type": "solid", "name": "background", "color": "red"}],
            },
        )
