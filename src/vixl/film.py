"""Bounded scene/shot assembly with camera motion, captions, transitions and audio."""

from contextlib import ExitStack
import io
import math
from pathlib import Path
import shutil
import subprocess
import tempfile
import zipfile

from PIL import Image

from .automation import bounded_object
from .errors import VixlError, require
from .model import Limits, finite
from .production import publish_file


def local_path(root, value):
    require(isinstance(value, str) and value, "Expected workspace path")
    path = (Path(root) / value).resolve()
    require(path.is_relative_to(Path(root).resolve()), "Film source is outside workspace", "forbidden")
    return path


MAX_FRAMES = 3600


def audio_duration(path):
    """The length of an audio (or video) file's first audio stream in milliseconds, read with
    ffprobe."""
    ffprobe = shutil.which("ffprobe")
    require(ffprobe, "Reading audio length needs ffprobe (part of ffmpeg) on PATH", "codec_error")
    command = [ffprobe, "-v", "error", "-select_streams", "a:0", "-show_entries", "stream=duration:format=duration",
               "-of", "json", str(path)]
    try:
        result = subprocess.run(command, capture_output=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise VixlError("codec_error", f"ffprobe could not read the audio: {exc}") from exc
    require(result.returncode == 0, "ffprobe could not read the audio file", "codec_error",
            detail=result.stderr.decode("utf-8", "replace").strip()[:300])
    import json

    try:
        info = json.loads(result.stdout or b"{}")
    except ValueError as exc:
        raise VixlError("codec_error", "ffprobe returned unreadable output") from exc
    streams = info.get("streams") or []
    require(streams, "The file has no audio stream", "codec_error")
    for value in (streams[0].get("duration"), (info.get("format") or {}).get("duration")):
        try:
            seconds = float(value)
        except (TypeError, ValueError):
            continue
        if math.isfinite(seconds) and seconds > 0:
            return int(round(seconds * 1000))
    raise VixlError("codec_error", "ffprobe could not determine the audio length")


def plan(spec, limits=None, streamed=False):
    """Validate a film spec. ``streamed`` (MP4/WebM output) lifts the 3,600-frame cap: those
    formats encode frame by frame, so only the 10-minute duration bounds them."""
    limits = limits or Limits()
    bounded_object(
        spec,
        {"version", "width", "height", "fps", "shots", "captions", "audio", "quality", "sample_rate"},
        "Unknown film field",
    )
    require(spec.get("version", 1) == 1, "Unsupported film version")
    require({"width", "height", "shots"} <= spec.keys(), "Film needs width, height and shots")
    width, height, fps = spec["width"], spec["height"], spec.get("fps", 30)
    limits.size(width, height)
    finite(fps, "fps", 1, 60)
    require(spec.get("quality", "final") in ("draft", "final"), "Invalid film quality")
    shots = spec.get("shots")
    require(isinstance(shots, list) and 0 < len(shots) <= 100, "Film needs 1–100 shots")
    duration, result = 0, []
    for index, shot in enumerate(shots):
        bounded_object(
            shot,
            {"source", "duration", "trim", "transition", "camera", "variables", "artboard"},
            "Unknown shot field",
        )
        require(isinstance(shot.get("source"), str), "Shot needs a source")
        require("duration" in shot, "Shot needs a duration")
        frames = max(1, math.ceil(finite(shot["duration"], "shot duration", 10, 600000) * fps / 1000))
        transition = shot.get("transition", 0)
        overlap = round(finite(transition, "crossfade duration", 0, 2000) * fps / 1000)
        require(index > 0 or overlap == 0, "First shot cannot have an incoming transition")
        require(
            overlap < frames and (not result or overlap < result[-1]["frames"] - result[-1]["overlap"]),
            "Transitions cannot consume a shot or create a three-shot overlap",
        )
        finite(shot.get("trim", 0), "trim", 0, 600000)
        if "camera" in shot:
            bounded_object(shot["camera"], {"from", "to"}, "Invalid camera")
            for pose in shot["camera"].values():
                require(isinstance(pose, list) and len(pose) == 3, "Camera pose is [center-x,center-y,zoom]")
                finite(pose[0], "camera x", 0, 1)
                finite(pose[1], "camera y", 0, 1)
                finite(pose[2], "camera zoom", 1, 16)
        start = duration - overlap
        result.append({**shot, "start_frame": start, "frames": frames, "overlap": overlap})
        duration = start + frames
    require(duration / fps <= 600, "Film exceeds the 10 minute limit", "resource_limit")
    require(streamed or duration <= MAX_FRAMES,
            f"Film has {duration} frames; ZIP output holds at most {MAX_FRAMES}. Render MP4/WebM, which have no "
            "frame cap, or lower fps or duration", "resource_limit")
    require(
        isinstance(spec.get("captions", []), list) and isinstance(spec.get("audio", []), list),
        "Captions and audio must be arrays",
    )
    for caption in spec.get("captions", []):
        from .captions import validate_caption
        validate_caption(caption)
        require(
            isinstance(caption.get("text"), str) and len(caption["text"]) <= 10000, "Invalid caption text"
        )
        require({"start", "end"} <= caption.keys(), "Caption needs start and end times")
        finite(caption["start"], "caption start", 0, 600000)
        finite(caption["end"], "caption end", 0, 600000)
        require(0 <= caption["start"] < caption["end"] <= duration * 1000 / fps, "Invalid caption interval")
    require(
        len(spec.get("captions", [])) <= 1000 and len(spec.get("audio", [])) <= 8,
        "Too many captions/audio tracks",
    )
    for track in spec.get("audio", []):
        from .audio import validate_track
        validate_track(track)
        require("asset" not in track, "Film audio uses source paths or synth; embedded assets need a timeline project")
        finite(track.get("start", 0), "audio start", 0, 600000)
    from .audio import check_rate
    check_rate(spec.get("sample_rate"))
    return {
        "version": 1,
        "width": width,
        "height": height,
        "fps": fps,
        "frames": duration,
        "duration": duration * 1000 / fps,
        "shots": result,
    }


def clip_frames(path, shot, size, fps):
    ffmpeg = shutil.which("ffmpeg")
    require(ffmpeg, "Video clips need ffmpeg on PATH", "missing_dependency")
    w, h = size
    command = [
        ffmpeg,
        "-v",
        "error",
        "-ss",
        str(shot.get("trim", 0) / 1000),
        "-i",
        str(path),
        "-an",
        "-vf",
        f"scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,fps={fps}",
        "-frames:v",
        str(shot["frames"]),
        "-f",
        "rawvideo",
        "-pix_fmt",
        "rgba",
        "pipe:1",
    ]
    with tempfile.TemporaryFile() as errors:
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=errors)
        try:
            for _ in range(shot["frames"]):
                data = process.stdout.read(w * h * 4)
                require(
                    len(data) == w * h * 4,
                    "Video clip is shorter than requested or cannot be decoded",
                    "codec_error",
                )
                yield Image.frombytes("RGBA", size, data)
        finally:
            process.stdout.close()
            if process.poll() is None:
                process.kill()
            process.wait(timeout=10)


MAX_SUPERSAMPLE = 4


def supersample(shot, size, limits):
    """How many times larger than the output a camera shot's source is drawn: its closest zoom, so a
    2x zoom crops a 2x render instead of enlarging output pixels; bounded by MAX_SUPERSAMPLE and the
    pixel budget."""
    camera = shot.get("camera")
    if not camera:
        return 1.0
    zoom = max(camera.get(key, [0.5, 0.5, 1])[2] for key in ("from", "to"))
    budget = math.sqrt(limits.max_pixels / (size[0] * size[1]))
    return max(1.0, min(zoom, MAX_SUPERSAMPLE, budget))


def _scaled(size, factor):
    return size if factor <= 1 else (round(size[0] * factor), round(size[1] * factor))


def _native_factor(source, size, cover=False):
    """The most a raster source can be supersampled before it is only being enlarged."""
    if not source:
        return 1.0
    ratios = (source[0] / size[0], source[1] / size[1])
    return max(1.0, min(ratios) if cover else max(ratios))


def _video_size(path):
    try:
        from .media_analysis import probe

        info, _ = probe(path)
    except VixlError:
        return None
    stream = next((s for s in info.get("streams", []) if s.get("codec_type") == "video"), None)
    return (stream["width"], stream["height"]) if stream and stream.get("width") and stream.get("height") else None


def _render_document(candidate, target, size, shot):
    """A .vixl frame covering ``target``. A supersampled camera shot renders the document scaled up
    (a geometric copy, so text and vectors stay sharp) instead of enlarging a native render."""
    from .design_render import artboard_project
    from .proxy import render_preview, scaled_project

    if target != size:
        document = artboard_project(candidate, shot.get("artboard"), None, shot.get("variables"))
        canvas = document.state["canvas"]
        scale = max(target[0] / canvas["width"], target[1] / canvas["height"])
        if scale > 1:
            scaled = scaled_project(document, scale)
            if scaled is not None:
                return scaled.render()
    return render_preview(candidate, *target, variables=shot.get("variables"), artboard=shot.get("artboard"))


def _state_key(project):
    import hashlib
    import json

    return hashlib.sha256(json.dumps(project.state, sort_keys=True, default=str).encode()).digest()


def frames(spec, root, *, limits=None, cancelled=lambda: False, streamed=False,
           start_frame=0, end_frame=None, region=None):
    from .project import Project
    from .render_cache import enable
    from .timeline import animated as timeline_animated, project_at
    from .assets import decode, read_bounded

    settings = plan(spec, limits, streamed)
    limits = limits or Limits()
    size = (settings["width"], settings["height"])
    if spec.get("quality") == "draft":
        ratio = min(1, 640 / max(size))
        size = tuple(max(1, round(n * ratio)) for n in size)
    end_frame = settings["frames"] if end_frame is None else end_frame
    require(isinstance(start_frame, int) and isinstance(end_frame, int) and
            0 <= start_frame < end_frame <= settings["frames"], "Invalid film frame interval")
    crop = preview_region(region, settings, size)
    sources, clips, targets = {}, {}, {}
    # The last rendered frame per document shot: a frame whose animated state is unchanged
    # (a lyric held on screen, a pause) reuses it instead of rendering again.
    memo = {}
    with ExitStack() as stack:
        for frame in range(start_frame, end_frame):
            require(not cancelled(), "Film cancelled", "cancelled")
            active = [
                (i, s)
                for i, s in enumerate(settings["shots"])
                if s["start_frame"] <= frame < s["start_frame"] + s["frames"]
            ]
            images = []
            for i, shot in active:
                local = frame - shot["start_frame"]
                path = local_path(root, shot["source"])
                if i not in sources:
                    factor = supersample(shot, size, limits)
                    if path.suffix.lower() == ".vixl":
                        sources[i] = enable(Project.load(path, limits=limits), Path(root) / ".vixl-cache")
                    elif path.suffix.lower() in (".mp4", ".webm", ".mov"):
                        factor = min(factor, _native_factor(_video_size(path) if factor > 1 else None, size))
                        targets[i] = _scaled(size, factor)
                        clips[i] = clip_frames(path, {**shot, "trim": shot.get("trim", 0) + local * 1000 / settings["fps"],
                                                     "frames": shot["frames"] - local}, targets[i], settings["fps"])
                        stack.callback(clips[i].close)
                        sources[i] = None
                    else:
                        from PIL import ImageOps
                        decoded = decode(read_bounded(path, limits.max_asset_bytes), limits)
                        factor = min(factor, _native_factor(decoded.size, size, cover=True))
                        targets[i] = _scaled(size, factor)
                        sources[i] = ImageOps.fit(decoded, targets[i], method=Image.Resampling.LANCZOS)
                    targets.setdefault(i, _scaled(size, factor))
                source, target = sources[i], targets[i]
                if i in clips:
                    image = next(clips[i])
                elif isinstance(source, Project):
                    animated = bool(timeline_animated(source.state.get("timeline")) or
                                    source.state.get("camera") or source.state.get("stop_motion") or
                                    any("particle" in layer for layer in source.state["layers"]))
                    candidate = project_at(source, shot.get("trim", 0) + local * 1000 / settings["fps"]) if animated else source
                    key = _state_key(candidate) if animated else b"static"
                    if i in memo and memo[i][0] == key:
                        image = memo[i][1].copy()
                    else:
                        image = _render_document(candidate, target, size, shot)
                        memo[i] = (key, image.copy())
                else:
                    image = source.copy()
                from PIL import ImageOps

                image = ImageOps.fit(image, target, method=Image.Resampling.LANCZOS)
                if shot.get("camera"):
                    poses = shot["camera"]
                    start, end = poses.get("from", [0.5, 0.5, 1]), poses.get("to", [0.5, 0.5, 1])
                    t = local / max(1, shot["frames"] - 1)
                    x, y, zoom = [a + (b - a) * t for a, b in zip(start, end)]
                    w, h = size[0] / zoom, size[1] / zoom
                    left = min(max(0, x * size[0] - w / 2), size[0] - w)
                    top = min(max(0, y * size[1] - h / 2), size[1] - h)
                    # The source was drawn ``target / size`` times larger, so the window is cut from
                    # real detail instead of enlarging output-size pixels.
                    sx, sy = target[0] / size[0], target[1] / size[1]
                    image = image.resize(size, Image.Resampling.BICUBIC,
                                         box=(left * sx, top * sy, (left + w) * sx, (top + h) * sy))
                elif image.size != size:
                    image = image.resize(size, Image.Resampling.LANCZOS)
                images.append(image)
            image = images[0]
            if len(images) == 2:
                incoming = active[-1][1]
                amount = (frame - incoming["start_frame"] + 1) / (incoming["overlap"] + 1)
                image = Image.blend(image, images[1], amount)
            now = frame * 1000 / settings["fps"]
            captions = [c for c in spec.get("captions", []) if c["start"] <= now < c["end"]]
            if captions:
                overlay = Project(*size, limits=limits)
                scale = size[0] / settings["width"]
                from .captions import apply_caption
                for j, caption in enumerate(captions):
                    apply_caption(overlay, caption, now, scale, j)
                image.alpha_composite(overlay.render())
            yield image.crop(crop) if crop else image
            # Release completed sources; long films do not keep every decoded image in memory.
            for i in list(sources):
                shot = settings["shots"][i]
                if frame + 1 >= shot["start_frame"] + shot["frames"]:
                    sources.pop(i)
                    targets.pop(i, None)
                    memo.pop(i, None)
                    if i in clips:
                        clips.pop(i).close()


def _output_size(spec, settings, region=None):
    """The encoded frame size: the film's, at most 640 px for drafts, then the preview region."""
    size = (settings["width"], settings["height"])
    if spec.get("quality") == "draft":
        ratio = min(1, 640 / max(size))
        size = tuple(max(1, round(n * ratio)) for n in size)
    crop = preview_region(region, settings, size)
    if crop:
        size = (crop[2] - crop[0], crop[3] - crop[1])
    return size


def _mux_audio(spec, root, video, temp, settings, first, last, suffix):
    """Mix the film's audio tracks and mux them, cut to frames ``first``–``last``, under ``video``.
    Returns the muxed file's path and the mix format."""
    mixed = Path(temp) / ("mixed" + suffix)
    command = [shutil.which("ffmpeg"), "-v", "error", "-i", str(video)]
    from .audio import prepare_tracks
    tracks, sound = prepare_tracks(spec["audio"], temp, settings["duration"], root=root,
                                   sample_rate=spec.get("sample_rate"),
                                   encoder="opus" if suffix.lower() == ".webm" else None)
    filters = []
    for i, track in enumerate(tracks, 1):
        path = Path(track["source"])
        command.extend(["-ss", str(track.get("trim", 0) / 1000), "-i", str(path)])
        delay = round(track.get("start", 0))
        filters.append(f"[{i}:a]volume={track.get('volume', 1)},adelay={delay}:all=1[a{i}]")
    labels = "".join(f"[a{i}]" for i in range(1, len(tracks) + 1))
    filters.append(labels + f"amix=inputs={len(tracks)}:normalize=0,apad,atrim=start={first / settings['fps']}:end={last / settings['fps']},asetpts=PTS-STARTPTS[a]")
    command.extend([
        "-filter_complex", ";".join(filters), "-map", "0:v", "-map", "[a]", "-c:v", "copy",
        "-c:a", "aac" if suffix == ".mp4" else "libopus", "-ar", str(sound["sample_rate"]),
        "-t", str((last - first) / settings["fps"]), str(mixed),
    ])
    result = subprocess.run(command, capture_output=True, timeout=600)
    require(result.returncode == 0, "Audio mix failed", "codec_error")
    return mixed, sound


def export(spec, root, output, *, limits=None, cancelled=lambda: False, progress=lambda value: None,
           start=None, end=None, shot=None, region=None, frame_range=None):
    """Render a film to ZIP, MP4 or WebM. ``start``/``end`` (ms) or ``shot`` render part of it;
    ``frame_range`` (first, last) selects frames exactly, as segmented renders do."""
    import json

    output = Path(output)
    require(output.suffix.lower() in (".zip", ".mp4", ".webm"), "Film output must be ZIP, MP4 or WebM")
    streamed = output.suffix.lower() in (".mp4", ".webm")
    selected = start is not None or end is not None or shot is not None or frame_range is not None
    settings = plan(spec, limits, streamed or selected)
    if frame_range is not None:
        first, last = frame_range
        require(start is None and end is None and shot is None, "Choose frame_range or an interval, not both")
        require(isinstance(first, int) and isinstance(last, int) and 0 <= first < last <= settings["frames"],
                "Invalid film frame interval")
    else:
        first, last = preview_interval(settings, start=start, end=end, shot=shot)
    count = last - first
    require(streamed or count <= MAX_FRAMES, "ZIP preview exceeds the frame budget", "resource_limit")
    require(not output.exists(), "Film output already exists")
    require(output.suffix != ".zip" or not spec.get("audio"), "Audio requires MP4/WebM output")
    output.parent.mkdir(parents=True, exist_ok=True)
    sound = None
    with tempfile.TemporaryDirectory(dir=output.parent, prefix=".film-") as temp:
        staged = Path(temp) / output.name
        stream = frames(spec, root, limits=limits, cancelled=cancelled, streamed=streamed or selected,
                        start_frame=first, end_frame=last, region=region)

        def tracked():
            try:
                for i, image in enumerate(stream):
                    progress({"done": i + 1, "total": count})
                    yield image
            finally:
                stream.close()

        if output.suffix.lower() == ".zip":
            with zipfile.ZipFile(staged, "w", zipfile.ZIP_STORED) as archive:
                for i, image in enumerate(tracked()):
                    buffer = io.BytesIO()
                    image.save(buffer, format="PNG")
                    archive.writestr(f"{i:06d}.png", buffer.getvalue())
                archive.writestr(
                    "timing.json",
                    json.dumps({"version": 1, "fps": settings["fps"], "frames": count, "start": first * 1000 / settings["fps"]}),
                )
        else:
            from .timeline import _video

            size = _output_size(spec, settings, region)
            _video(staged, tracked(), settings["fps"], output.suffix[1:],
                   60 if spec.get("quality") == "draft" else 90, False, count, size)
            if spec.get("audio"):
                staged, sound = _mux_audio(spec, root, staged, temp, settings, first, last, output.suffix)
        require(not cancelled(), "Film cancelled", "cancelled")
        publish_file(output, staged)
    result = {
        "version": 1,
        "output": str(output),
        "frames": count,
        "duration": count * 1000 / settings["fps"],
        "start": first * 1000 / settings["fps"],
        "quality": spec.get("quality", "final"),
        **(sound or {}),
    }
    if streamed:
        # The encoder pads odd sizes to even ones (yuv420p needs them), so this is the file's size.
        width, height = _output_size(spec, settings, region)
        result.update(width=width + width % 2, height=height + height % 2, fps=settings["fps"])
    return result


def _segment_key(spec, root, per, suffix, limits):
    """What a segmented render's parts depend on: the spec without its audio, the part length, the
    format, the Vixl version and the content of every shot source (a document's state and assets,
    not its file bytes, which change with every save)."""
    import hashlib
    import json

    from . import __version__
    from .project import Project

    digest = hashlib.sha256()
    body = {"spec": {k: v for k, v in spec.items() if k != "audio"}, "per": per, "suffix": suffix.lower(),
            "version": __version__}
    digest.update(json.dumps(body, sort_keys=True, default=str).encode())
    for shot in spec["shots"]:
        path = local_path(root, shot["source"])
        if path.suffix.lower() == ".vixl":
            project = Project.load(path, limits=limits)
            digest.update(json.dumps(project.state, sort_keys=True, default=str).encode())
            for name in sorted(project.assets):
                digest.update(name.encode() + hashlib.sha256(project.assets[name]).digest())
        else:
            with path.open("rb") as source:
                for block in iter(lambda: source.read(1 << 20), b""):
                    digest.update(block)
    return digest.hexdigest()


def export_segments(spec, root, output, segment, *, limits=None, cancelled=lambda: False, progress=lambda value: None,
                    work=None):
    """Render an MP4/WebM film in parts of ``segment`` ms, then join them and add the audio once.

    Each finished part is kept in ``work`` (default ``.<output name>.parts`` beside the output), so
    running the same render again after a crash or a cancel skips the parts already there. Parts
    from a different spec, source or Vixl version are discarded. The folder is removed once the
    output is published."""
    import json

    limits = limits or Limits()
    output = Path(output)
    suffix = output.suffix.lower()
    require(suffix in (".mp4", ".webm"), "Segmented film output must be MP4 or WebM")
    require(not output.exists(), "Film output already exists")
    ffmpeg = shutil.which("ffmpeg")
    require(ffmpeg, "MP4/WebM export needs ffmpeg on PATH", "missing_dependency")
    settings = plan(spec, limits, True)
    fps, total = settings["fps"], settings["frames"]
    per = max(1, round(finite(segment, "segments", 1000, 600000) * fps / 1000))
    parts = [(first, min(first + per, total)) for first in range(0, total, per)]
    work = Path(work) if work is not None else output.parent / f".{output.name}.parts"
    key = _segment_key(spec, root, per, suffix, limits)
    manifest = work / "manifest.json"
    if work.exists():
        try:
            same = json.loads(manifest.read_text(encoding="utf-8")).get("key") == key
        except (OSError, ValueError, AttributeError):
            same = False
        if not same:
            shutil.rmtree(work)
    work.mkdir(parents=True, exist_ok=True)
    manifest.write_text(json.dumps({"version": 1, "key": key, "frames_per_part": per, "parts": len(parts)}),
                        encoding="utf-8")
    video_spec = {k: v for k, v in spec.items() if k != "audio"}
    paths, reused, done = [], 0, 0
    for i, (first, last) in enumerate(parts):
        require(not cancelled(), "Film cancelled", "cancelled")
        part = work / f"part-{i:04d}{suffix}"
        paths.append(part)
        if part.exists():
            # A part is published only once it is complete, so one that exists is whole.
            reused += 1
        else:
            export(video_spec, root, part, limits=limits, cancelled=cancelled, frame_range=(first, last),
                   progress=lambda value, base=done: progress({"done": base + value["done"], "total": total}))
        done += last - first
        progress({"done": done, "total": total})
    sound = None
    with tempfile.TemporaryDirectory(dir=output.parent, prefix=".film-") as temp:
        listing = Path(temp) / "parts.txt"
        listing.write_text("".join("file '" + str(p.resolve()).replace("'", "'\\''") + "'\n" for p in paths),
                           encoding="utf-8")
        staged = Path(temp) / ("joined" + suffix)
        joined = subprocess.run([ffmpeg, "-v", "error", "-f", "concat", "-safe", "0", "-i", str(listing), "-c", "copy",
                                 str(staged)], capture_output=True, timeout=600)
        require(joined.returncode == 0, "Joining the rendered parts failed", "codec_error",
                detail=joined.stderr.decode("utf-8", "replace").strip()[:300])
        if spec.get("audio"):
            staged, sound = _mux_audio(spec, root, staged, temp, settings, 0, total, suffix)
        require(not cancelled(), "Film cancelled", "cancelled")
        publish_file(output, staged)
    shutil.rmtree(work, ignore_errors=True)
    width, height = _output_size(spec, settings)
    return {
        "version": 1,
        "output": str(output),
        "frames": total,
        "duration": total * 1000 / fps,
        "start": 0.0,
        "quality": spec.get("quality", "final"),
        **(sound or {}),
        "width": width + width % 2,
        "height": height + height % 2,
        "fps": fps,
        "segments": {"parts": len(parts), "reused": reused, "rendered": len(parts) - reused, "frames_per_part": per},
    }


def _probe_media(ffprobe, path):
    """ffprobe's JSON for a file's streams and container, or ``None`` when it cannot read it."""
    import json

    command = [ffprobe, "-v", "error", "-show_entries",
               "stream=codec_type,codec_name,width,height,r_frame_rate,nb_frames,duration,channels,sample_rate"
               ":format=duration", "-of", "json", str(path)]
    try:
        result = subprocess.run(command, capture_output=True, timeout=120)
        return json.loads(result.stdout or b"{}") if result.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return None


def _rate(value):
    try:
        top, _, bottom = str(value).partition("/")
        return float(top) / float(bottom or 1)
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def _seconds(*values):
    for value in values:
        try:
            seconds = float(value)
        except (TypeError, ValueError):
            continue
        if math.isfinite(seconds) and seconds >= 0:
            return seconds
    return None


def verify_video(path, result, *, requested_ms=None):
    """Read an encoded MP4/WebM back with ffprobe and compare it with what the export rendered
    (``result``: its width, height, fps, frames and, with audio, sample_rate and channels).

    Returns ``{"status", "passed", "checks", "video", "audio", "quantization"}``. ``status`` is
    ``passed``, ``failed`` or ``skipped`` (no ffprobe, or nothing to compare); ``quantization``
    reports how far the whole-frame length is from ``requested_ms``, which is expected and at most
    one frame, not drift."""
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return {"status": "skipped", "passed": None, "reason": "ffprobe is not on PATH"}
    if not {"width", "height", "fps", "frames"} <= set(result):
        return {"status": "skipped", "passed": None, "reason": "the export did not report the encoded size"}
    info = _probe_media(ffprobe, path)
    checks = []

    def check(name, expected, actual, passed):
        checks.append({"check": name, "expected": expected, "actual": actual, "passed": bool(passed)})

    if info is None:
        check("readable", True, False, False)
        return {"status": "failed", "passed": False, "checks": checks}
    streams = info.get("streams") or []
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
    fps, frames = result["fps"], result["frames"]
    frame_ms = 1000 / fps
    check("video_stream", True, video is not None, video is not None)
    report = {"status": "failed", "passed": False, "checks": checks}
    if video is not None:
        size = [video.get("width"), video.get("height")]
        check("dimensions", [result["width"], result["height"]], size, size == [result["width"], result["height"]])
        rate = _rate(video.get("r_frame_rate"))
        check("fps", fps, rate, rate is not None and abs(rate - fps) < 0.01)
        seconds = _seconds(video.get("duration"), (info.get("format") or {}).get("duration"))
        counted = int(video["nb_frames"]) if str(video.get("nb_frames", "")).isdigit() else (
            round(seconds * fps) if seconds is not None else None)
        check("frames", frames, counted, counted == frames)
        duration_ms = None if seconds is None else round(seconds * 1000, 3)
        check("duration", round(frames * frame_ms, 3), duration_ms,
              duration_ms is not None and abs(duration_ms - frames * frame_ms) <= frame_ms + 1)
        report["video"] = {"codec": video.get("codec_name"), "width": size[0], "height": size[1], "fps": rate,
                           "frames": counted, "duration_ms": duration_ms}
    wanted = "sample_rate" in result
    check("audio_stream", wanted, audio is not None, (audio is not None) == wanted)
    if audio is not None:
        rate = int(audio["sample_rate"]) if str(audio.get("sample_rate", "")).isdigit() else None
        seconds = _seconds(audio.get("duration"))
        report["audio"] = {"codec": audio.get("codec_name"), "sample_rate": rate, "channels": audio.get("channels"),
                           "duration_ms": None if seconds is None else round(seconds * 1000, 3)}
        if wanted:
            check("sample_rate", result["sample_rate"], rate, rate == result["sample_rate"])
            check("channels", result.get("channels"), audio.get("channels"), audio.get("channels") == result.get("channels"))
    if requested_ms is not None:
        encoded = frames * frame_ms
        delta = round(encoded - requested_ms, 3)
        # Whole frames round the length up by less than one frame: expected, and reported as such.
        report["quantization"] = {"requested_ms": requested_ms, "encoded_ms": round(encoded, 3), "delta_ms": delta,
                                  "frame_ms": round(frame_ms, 3), "within_one_frame": abs(delta) < frame_ms}
        check("quantization", f"under {round(frame_ms, 3)} ms", delta, abs(delta) < frame_ms)
    report["passed"] = all(item["passed"] for item in checks)
    report["status"] = "passed" if report["passed"] else "failed"
    return report


def preview_interval(settings, *, start=None, end=None, shot=None):
    """Public preview times are milliseconds, consistent with all film/timeline timing."""
    fps = settings["fps"]
    if shot is not None:
        require(start is None and end is None, "Choose shot or interval, not both")
        require(isinstance(shot, int) and not isinstance(shot, bool) and 0 <= shot < len(settings["shots"]),
                "Shot is a zero-based index")
        item = settings["shots"][shot]
        return item["start_frame"], item["start_frame"] + item["frames"]
    start = finite(0 if start is None else start, "start", 0, settings["duration"])
    end = finite(settings["duration"] if end is None else end, "end", 0, settings["duration"])
    require(start < end, "Preview start must be before end")
    return min(settings["frames"] - 1, math.floor(start * fps / 1000)), min(settings["frames"], math.ceil(end * fps / 1000))


def preview_region(region, settings, size):
    if region is None:
        return None
    require(isinstance(region, list) and len(region) == 4, "Region is [x,y,width,height] in film pixels")
    x, y, w, h = [finite(v, "region", 0) for v in region]
    require(w > 0 and h > 0 and x + w <= settings["width"] and y + h <= settings["height"],
            "Preview region must fit inside the film")
    sx, sy = size[0] / settings["width"], size[1] / settings["height"]
    left, top = round(x * sx), round(y * sy)
    return left, top, max(left + 1, round((x + w) * sx)), max(top + 1, round((y + h) * sy))


def preview(spec, root, output, *, time=0, start=None, end=None, shot=None, region=None, loop=0, limits=None):
    """Seek directly to a film frame, or render only the selected interval, camera/crossfades included.

    PNG is a scrubbed frame; GIF loops a bounded interval; MP4/WebM/ZIP export an interval.
    Preview defaults to draft unless quality is explicitly supplied in the film spec.
    """
    spec = {"quality": "draft", **spec}
    settings = plan(spec, limits, streamed=True)
    output = Path(output)
    require(not output.exists(), "Preview output already exists")
    if output.suffix.lower() in (".zip", ".mp4", ".webm"):
        return export(spec, root, output, limits=limits, start=start, end=end, shot=shot, region=region)
    require(output.suffix.lower() in (".png", ".gif"), "Preview output must be PNG, GIF, ZIP, MP4 or WebM")
    if output.suffix.lower() == ".png":
        require(start is None and end is None and shot is None, "PNG preview uses time; intervals use GIF/ZIP/video")
        finite(time, "time", 0, settings["duration"])
        first = min(settings["frames"] - 1, math.floor(time * settings["fps"] / 1000))
        last = first + 1
    else:
        first, last = preview_interval(settings, start=start, end=end, shot=shot)
        require(last - first <= 300, "Loop preview is limited to 300 frames; select a shorter interval", "resource_limit")
        require(isinstance(loop, int) and not isinstance(loop, bool) and 0 <= loop <= 100, "Loop is 0 (forever) or 1–100")
    output.parent.mkdir(parents=True, exist_ok=True)
    stream = frames(spec, root, limits=limits, streamed=True, start_frame=first, end_frame=last, region=region)
    with tempfile.TemporaryDirectory(dir=output.parent, prefix=".preview-") as temp:
        staged = Path(temp) / output.name
        try:
            first_image = next(stream)
            if output.suffix.lower() == ".png":
                first_image.save(staged)
            else:
                require(first_image.width * first_image.height * (last - first) <= 80_000_000,
                        "Loop preview exceeds pixel budget; use a smaller region or video", "resource_limit")
                first_image.save(staged, save_all=True, append_images=list(stream),
                                 duration=1000 / settings["fps"], loop=loop, disposal=2)
        finally:
            stream.close()
        publish_file(output, staged)
    return {"output": str(output), "frames": last - first, "start": first * 1000 / settings["fps"],
            "duration": (last - first) * 1000 / settings["fps"], "quality": spec["quality"],
            "camera": True, "transitions": True}
