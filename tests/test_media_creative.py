"""Behavioral coverage for creative media review, textures and reference-driven checks."""
import shutil
import wave

import numpy as np
from PIL import Image
import pytest

from vixl.errors import VixlError
from vixl.project import Project
from vixl import film, natural_guidance as guidance, textures
from vixl.media_analysis import analyze_samples, audio_analyze, video_sample


def image_shots(tmp_path):
    Image.new("RGBA", (40, 30), "red").save(tmp_path / "red.png")
    Image.new("RGBA", (40, 30), "blue").save(tmp_path / "blue.png")
    return {"width":40,"height":30,"fps":10,"shots":[
        {"source":"red.png","duration":1000},
        {"source":"blue.png","duration":1000,"transition":400}]}


def test_film_seek_matches_full_crossfade_and_region(tmp_path):
    spec = image_shots(tmp_path)
    full = list(film.frames(spec,tmp_path))
    subset = list(film.frames(spec,tmp_path,start_frame=7,end_frame=9,region=[5,4,12,10]))
    assert len(subset)==2 and subset[0].size==(12,10)
    assert subset[0].tobytes()==full[7].crop((5,4,17,14)).tobytes()
    red,_,blue,_=subset[0].getpixel((0,0))
    assert red>0 and blue>0
    result=film.preview(spec,tmp_path,tmp_path/"scrub.png",time=700,region=[5,4,12,10])
    assert result["frames"]==1 and result["quality"]=="draft"
    assert Image.open(tmp_path/"scrub.png").tobytes()==subset[0].tobytes()


def test_film_camera_crop_and_interval_zip(tmp_path):
    im=Image.new("RGBA",(40,30),"red")
    im.paste("blue",(20,0,40,30))
    im.save(tmp_path/"split.png")
    spec={"width":40,"height":30,"fps":10,"shots":[{"source":"split.png","duration":1000,
          "camera":{"from":[.75,.5,2],"to":[.75,.5,2]}}]}
    frame=next(film.frames(spec,tmp_path,start_frame=8,end_frame=9))
    assert frame.getpixel((20,15))[:3]==(0,0,255)
    report=film.export(spec,tmp_path,tmp_path/"interval.zip",start=400,end=700)
    assert report["frames"]==3 and report["start"]==400
    result=film.preview(spec,tmp_path,tmp_path/"loop.gif",start=400,end=700)
    assert result["frames"]==3
    with pytest.raises(VixlError):
        film.preview(spec,tmp_path,tmp_path/"bad.png",time=1200)


def test_static_film_renders_document_once_and_never_evaluates_timeline(tmp_path,monkeypatch):
    project=Project(40,30)
    project.apply({"type":"solid","color":"green"})
    project.save(tmp_path/"still.vixl")
    spec={"width":40,"height":30,"fps":10,"shots":[{"source":"still.vixl","duration":10000}]}
    import vixl.proxy
    original=vixl.proxy.render_preview
    calls=[]
    def counted(*args,**kwargs):
        calls.append(1)
        return original(*args,**kwargs)
    monkeypatch.setattr(vixl.proxy,"render_preview",counted)
    monkeypatch.setattr(film,"_state_key",lambda *_:pytest.fail("Static scene should skip state hashing"))
    assert len(list(film.frames(spec,tmp_path,start_frame=90,end_frame=100)))==10
    assert len(calls)==1


def test_pattern_periodicity_transform_and_custom_roundtrip(tmp_path):
    project=Project(64,64)
    for name in textures.PATTERNS:
        spacing=16
        im=textures.pattern_image(project,(64,64),{"pattern":name,"spacing":spacing})
        assert im.size==(64,64)
        # Checker and scales have a two-cell period; all others divide it.
        assert np.max(np.abs(np.asarray(im)[:32,:32].astype(int)-np.asarray(im)[32:,32:].astype(int)))<=1
    project.apply({"type":"solid","name":"tile","width":8,"height":8,"color":"green"})
    project.apply({"type":"pattern-define","name":"green","target":"tile","seamless":True})
    project.apply({"type":"shape","name":"shape","shape":"ellipse","width":32,"height":32,"fill":"red"})
    project.apply({"type":"pattern-fill","target":"shape","pattern":"green","name":"fill","scale":2,"rotation":30})
    assert project.layer("shape")["type"]=="shape"
    assert project.image(project.layer("fill")["asset"]).getpixel((16,16))[:3]==(0,128,0)
    project.save(tmp_path/"tile.vixl")
    restored=Project.load(tmp_path/"tile.vixl")
    assert textures.catalog(restored)["custom"]==["green"]
    assert restored.render().tobytes()==project.render().tobytes()


def test_drawn_texture_seed_alpha_and_pressure(tmp_path):
    original=Image.new("RGBA",(80,80),"white")
    original.putpixel((0,0),(255,255,255,0))
    for preset in textures.DRAWN:
        a=textures.drawn_image(original,preset,seed=4)
        b=textures.drawn_image(original,preset,seed=4)
        c=textures.drawn_image(original,preset,seed=5)
        assert a.tobytes()==b.tobytes() and a.tobytes()!=c.tobytes()
        assert a.getpixel((0,0))[3]==0
        assert 0 < np.asarray(a.getchannel("A")).std()
    project=Project(80,80)
    project.apply({"type":"shape","shape":"ellipse","name":"base","width":80,"height":80,"fill":"white"})
    project.apply({"type":"drawn-texture","target":"base","preset":"charcoal","name":"handmade"})
    assert project.layer("base")["type"]=="shape"
    assert project.layer("handmade")["provenance"]["type"]=="drawn-texture"
    project.undo()
    assert len(project.state["layers"])==1


def test_clone_alignment_opacity_frozen_sampling_and_undo(tmp_path):
    image=Image.new("RGBA",(40,20),"white")
    image.paste("red",(0,0,10,20))
    image.paste("blue",(10,0,20,20))
    strokes=[[[25,10]],[[35,10]]]
    aligned=textures.clone_image(image,image,[5,10],strokes,size=6,hardness=1)
    restarted=textures.clone_image(image,image,[5,10],strokes,size=6,hardness=1,aligned=False)
    assert aligned.getpixel((35,10))[:3]==(0,0,255)
    assert restarted.getpixel((35,10))[:3]==(255,0,0)
    faded=textures.clone_image(image,image,[5,10],[[[25,10]]],size=6,hardness=1,opacity=.5)
    assert 120<=faded.getpixel((25,10))[1]<=130
    image.save(tmp_path/"source.png")
    project=Project(40,20)
    project.apply({"type":"add","path":str(tmp_path/"source.png"),"name":"photo"})
    before=project.render().tobytes()
    project.apply({"type":"clone-stamp","target":"photo","source":[5,10],"points":[[25,10]],"size":6,"hardness":1})
    assert project.render().getpixel((25,10))[:3]==(255,0,0)
    project.undo()
    assert project.render().tobytes()==before
    project.redo()
    assert project.render().getpixel((25,10))[:3]==(255,0,0)


def test_guidance_checks_catch_light_anatomy_perspective_and_values():
    assert guidance.natural_palette("foliage")["colors"]==guidance.PALETTES["foliage"]
    assert guidance.natural_palette("foliage","night")["colors"]!=guidance.PALETTES["foliage"]
    light=guidance.check({"kind":"lighting","light":[0,0],"objects":[{"position":[10,10],"shadow":[-4,-4],"lit":"black","shade":"white"}]})
    assert {f["code"] for f in light["findings"]}=={"shadow-toward-light","inverted-light-value"}
    good=guidance.check({"kind":"lighting","light":[0,0],"objects":[{"position":[10,10],"shadow":[4,4],"lit":"white","shade":"black"}]})
    assert good["passed"]
    anatomy=guidance.check({"kind":"anatomy","head_units":11,"joints":[{"name":"elbow","angle":240}],"limbs":[{"upper":100,"lower":10}]})
    assert len(anatomy["findings"])==3
    perspective=guidance.check({"kind":"perspective","horizon":100,"vanishing":[[0,150]],"objects":[{"depth":1,"size":100},{"depth":2,"size":50},{"depth":4,"size":100}]})
    assert {f["code"] for f in perspective["findings"]}=={"inconsistent-horizon","inconsistent-depth-scale"}
    assert len(guidance.check({"kind":"illustration","values":[.45,.5],"silhouette_contrast":.05})["findings"])==2


def test_figure_and_perspective_workflows_produce_valid_operations():
    project=Project(800,800)
    figure=guidance.figure_plan({"height":600})
    project.apply(figure["operations"])
    assert project.layer("figure")["type"]=="group" and len(figure["parts"])==7
    perspective=guidance.perspective_guides({"width":800,"height":800,"points":3,"depths":[1,2,4]})
    project.apply(perspective["operations"])
    assert [s["size"] for s in perspective["sizes"]]==[100,50,25]
    assert "perspective-horizon" in project.state["guides"]


def test_audio_analysis_silence_clipping_beat_sync_and_short_audio():
    rate=22050
    samples=np.zeros(rate*3)
    for start in (.5,1,1.5,2,2.5):
        i=int(start*rate)
        samples[i:i+500]=np.sin(np.arange(500)*2*np.pi*440/rate)*1.1
    report,spectrum=analyze_samples(samples,rate,events=[500,1000])
    assert report["clipped_samples"]>0 and report["silence"][0]["start"]==0
    assert report["onset_count"]>=4 and 110<report["estimated_bpm"]<130
    assert abs(report["sync"][0]["delta"])<60 and spectrum.ndim==2
    brief,_=analyze_samples(np.zeros(10),rate)
    assert brief["onsets"]==[] and brief["estimated_bpm"] is None


@pytest.mark.skipif(not shutil.which("ffmpeg") or not shutil.which("ffprobe"),reason="ffmpeg needed")
def test_visible_video_samples_and_audio_spectrogram(tmp_path):
    spec=image_shots(tmp_path)
    film.export(spec,tmp_path,tmp_path/"movie.mp4")
    report=video_sample(tmp_path/"movie.mp4",tmp_path/"sheet.png",times=[0,700,1400],width=64)
    assert report["count"]==3 and Image.open(report["images"][0]).width==192
    report=video_sample(tmp_path/"movie.mp4",tmp_path/"frames",times=[0,1400],width=64,contact_sheet=False)
    assert len(report["images"])==2
    with wave.open(str(tmp_path/"tone.wav"),"wb") as out:
        out.setparams((1,2,22050,0,"NONE","not compressed"))
        out.writeframes((np.sin(np.arange(22050)*2*np.pi*440/22050)*16000).astype("<i2").tobytes())
    report=audio_analyze(tmp_path/"tone.wav",tmp_path/"spectrum.png")
    assert -7<report["peak_dbfs"]<-5
    assert Image.open(report["spectrogram"]).size==(960,352)


def test_workflow_discovery_and_resource_reading(tmp_path):
    from vixl.interfaces import Session
    from vixl.resources import get, catalog
    from vixl.workflows import dispatch, describe
    session = Session(workspace=tmp_path)
    assert "natural-color-light" in catalog("guidance")
    assert "OpenStax" in get("guidance", "anatomy-proportions")
    actions = describe()["actions"]
    for action in ("film-preview", "video-sample", "audio-analyze", "guide-check", "figure-plan", "pattern-list"):
        assert action in actions
    assert "paper" in dispatch(session, "pattern-list", {})["builtins"]
    report = dispatch(session, "guide-check", {"spec": {"kind": "illustration", "values": [0, 1]}})
    assert report["passed"]


@pytest.mark.skipif(not shutil.which("ffmpeg") or not shutil.which("ffprobe"),reason="ffmpeg needed")
def test_clip_scrubbing_and_interval_synth_audio(tmp_path):
    from vixl.media_analysis import probe
    spec = image_shots(tmp_path)
    spec["audio"] = [{"synth": "sine", "duration": 1600}]
    film.export(spec, tmp_path, tmp_path / "sound.mp4")
    clip = {"width": 40, "height": 30, "fps": 10, "shots": [{"source": "sound.mp4", "duration": 1500}]}
    sampled = next(film.frames(clip, tmp_path, start_frame=12, end_frame=13))
    assert sampled.getpixel((20, 15))[2] > 240
    film.preview(spec, tmp_path, tmp_path / "interval.mp4", start=500, end=800)
    info, duration = probe(tmp_path / "interval.mp4")
    assert 290 <= duration <= 350
    assert any(s["codec_type"] == "audio" for s in info["streams"])


def test_film_document_camera_without_tracks_is_animated(tmp_path):
    project = Project(80, 60)
    project.apply([
        {"type": "solid", "name": "square", "width": 20, "height": 20, "x": 40, "y": 20, "color": "red"},
        {"type": "camera", "from": [0, 0, 1], "to": [20, 0, 1], "duration": 1000},
    ])
    project.save(tmp_path / "camera.vixl")
    spec = {"width": 80, "height": 60, "fps": 10, "shots": [{"source": "camera.vixl", "duration": 1000}]}
    frames = list(film.frames(spec, tmp_path))
    assert frames[0].tobytes() != frames[-1].tobytes()


@pytest.mark.skipif(not shutil.which("ffmpeg") or not shutil.which("ffprobe"),reason="ffmpeg needed")
def test_mcp_video_sample_and_film_preview_deliver_image_blocks(tmp_path):
    import asyncio
    from vixl.interfaces import Session
    from vixl.mcp_tools import build_server
    spec = image_shots(tmp_path)
    film.export(spec, tmp_path, tmp_path / "sample.mp4")
    server = build_server(Session(workspace=tmp_path))
    async def invoke(action, request):
        result = await server.call_tool("vixl_workflow", {"action": action, "request": request})
        return result[0] if isinstance(result, tuple) else result
    blocks = asyncio.run(invoke("video-sample", {"source": "sample.mp4", "output": "contact.png", "times": [0, 700]}))
    assert any(block.type == "image" for block in blocks)
    blocks = asyncio.run(invoke("film-preview", {"spec": spec, "time": 700, "output": "frame.png"}))
    assert any(block.type == "image" for block in blocks)


def test_draft_proxy_preserves_point_light_position_and_radius():
    from vixl.proxy import render_preview, scaled_project
    project = Project(800, 600, "black")
    project.apply({"type": "lighting", "ambient": 0, "lights": [{"x": 600, "y": 300, "intensity": 1}]})
    preview = render_preview(project, 200, 150)
    red = np.asarray(preview)[:, :, 0]
    assert np.unravel_index(np.argmax(red), red.shape)[0] in range(72, 79)
    assert np.unravel_index(np.argmax(red), red.shape)[1] in range(147, 154)
    proxy = scaled_project(project, .25)
    assert proxy.state["lighting"]["lights"][0]["radius"] == 50
    assert project.state["lighting"]["lights"][0]["x"] == 600


def test_clone_sample_all_and_pattern_selection(tmp_path):
    Image.new("RGBA", (40, 20), "white").save(tmp_path / "photo.png")
    project = Project(40, 20)
    project.apply([
        {"type": "add", "path": str(tmp_path / "photo.png"), "name": "photo"},
        {"type": "solid", "name": "red-source", "width": 8, "height": 20, "color": "red"},
        {"type": "clone-stamp", "target": "photo", "source": [4, 10], "points": [[30, 10]],
         "size": 6, "hardness": 1, "sample_all": True},
    ])
    assert project.image(project.layer("photo")["asset"]).getpixel((30, 10))[:3] == (255, 0, 0)
    project.apply([
        {"type": "select", "shape": "rect", "x": 0, "y": 0, "width": 8, "height": 20},
        {"type": "pattern-define", "name": "selection-tile", "selection": True},
    ])
    tile = project.state["patterns"]["selection-tile"]
    assert (tile["width"], tile["height"]) == (8, 20)
    assert project.image(tile["asset"]).getpixel((4, 10))[:3] == (255, 0, 0)


def test_render_cache_inserts_do_not_rescan_every_frame(tmp_path, monkeypatch):
    from pathlib import Path
    from vixl.render_cache import RenderCache
    scans = []
    original = Path.glob
    def tracked(path, pattern):
        if path == tmp_path and pattern == "*.png":
            scans.append(1)
        return original(path, pattern)
    monkeypatch.setattr(Path, "glob", tracked)
    cache = RenderCache(tmp_path)
    frame = Image.new("RGBA", (16, 16), "red")
    for i in range(100):
        cache.put(f"frame-{i}", frame)
    assert len(scans) == 1
    assert cache._bytes == sum(path.stat().st_size for path in original(tmp_path, "*.png"))


def test_render_cache_shared_writers_keep_byte_budget_and_lru(tmp_path):
    import os
    from vixl.render_cache import RenderCache
    from vixl.model import Limits
    first, second = RenderCache(tmp_path, budget=420), RenderCache(tmp_path, budget=420)
    image = Image.new("RGBA", (16, 16), "red")
    first.put("first", image)
    second.put("second", image)
    # Make the earlier access order unambiguous, then verify that a cache hit
    # refreshes the oldest entry before eviction, without sleeps or clock ties.
    os.utime(tmp_path / "first.png", ns=(1_000_000_000, 1_000_000_000))
    os.utime(tmp_path / "second.png", ns=(2_000_000_000, 2_000_000_000))
    assert first.get("first", Limits()) is not None
    for key in ("third", "fourth", "fifth"):
        second.put(key, image)
    assert first.get("first", Limits()) is not None
    assert second.get("second", Limits()) is None
    for i in range(20):
        (first if i % 2 else second).put(f"frame-{i}", image)
        assert sum(p.stat().st_size for p in tmp_path.glob("*.png")) <= 420
    assert len(list(tmp_path.glob("*.png"))) >= 4


def test_render_cache_shared_usage_survives_directory_timestamp_collisions(tmp_path, monkeypatch):
    from vixl.render_cache import RenderCache
    # Model a filesystem whose directory timestamp never changes during the run.
    monkeypatch.setattr(RenderCache, "_signature", lambda self: [1, 2, 3])
    first, second = RenderCache(tmp_path, budget=420), RenderCache(tmp_path, budget=420)
    image = Image.new("RGBA", (16, 16), "red")
    for i in range(25):
        cache = first if i % 2 else second
        cache.put(f"frame-{i}", image)
        total = sum(p.stat().st_size for p in tmp_path.glob("*.png"))
        assert total <= 420
        assert cache._bytes == total


def test_render_cache_recovers_interrupted_usage_ledger(tmp_path):
    import json
    from vixl.render_cache import RenderCache
    cache = RenderCache(tmp_path, budget=420)
    image = Image.new("RGBA", (16, 16), "red")
    cache.put("first", image)
    # Simulate interruption after writing a PNG but before committing usage.
    image.save(tmp_path / "uncommitted.png")
    usage = tmp_path.parent / (tmp_path.name + ".usage.json")
    usage.write_text(json.dumps({"version": 1, "dirty": True}))
    recovered = RenderCache(tmp_path, budget=420)
    recovered.put("third", image)
    assert recovered._bytes == sum(p.stat().st_size for p in tmp_path.glob("*.png"))
    assert json.loads(usage.read_text())["dirty"] is False
