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
        {"version", "width", "height", "fps", "shots", "captions", "audio", "quality"},
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
        bounded_object(caption, {"text", "start", "end", "x", "y", "size", "color"}, "Unknown caption field")
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
        bounded_object(track, {"source", "start", "trim", "volume"}, "Unknown audio field")
        require(isinstance(track.get("source"), str) and track["source"], "Audio track needs a source")
        finite(track.get("volume", 1), "volume", 0, 4)
        finite(track.get("start", 0), "audio start", 0, 600000)
        finite(track.get("trim", 0), "audio trim", 0, 600000)
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


def _state_key(project):
    import hashlib
    import json

    return hashlib.sha256(json.dumps(project.state, sort_keys=True, default=str).encode()).digest()


def frames(spec, root, *, limits=None, cancelled=lambda: False, streamed=False):
    from .project import Project
    from .render_cache import enable
    from .timeline import project_at
    from .proxy import render_preview
    from .assets import decode, read_bounded

    settings = plan(spec, limits, streamed)
    limits = limits or Limits()
    size = (settings["width"], settings["height"])
    if spec.get("quality") == "draft":
        ratio = min(1, 640 / max(size))
        size = tuple(max(1, round(n * ratio)) for n in size)
    sources, clips = {}, {}
    # The last rendered frame per document shot: a frame whose animated state is unchanged
    # (a lyric held on screen, a pause) reuses it instead of rendering again.
    memo = {}
    with ExitStack() as stack:
        for frame in range(settings["frames"]):
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
                    if path.suffix.lower() == ".vixl":
                        sources[i] = enable(Project.load(path, limits=limits), Path(root) / ".vixl-cache")
                    elif path.suffix.lower() in (".mp4", ".webm", ".mov"):
                        clips[i] = clip_frames(path, shot, size, settings["fps"])
                        stack.callback(clips[i].close)
                        sources[i] = None
                    else:
                        sources[i] = decode(read_bounded(path, limits.max_asset_bytes), limits)
                source = sources[i]
                if i in clips:
                    image = next(clips[i])
                elif isinstance(source, Project):
                    candidate = project_at(source, shot.get("trim", 0) + local * 1000 / settings["fps"])
                    key = _state_key(candidate)
                    if i in memo and memo[i][0] == key:
                        image = memo[i][1].copy()
                    else:
                        image = render_preview(
                            candidate, *size, variables=shot.get("variables"), artboard=shot.get("artboard")
                        )
                        memo[i] = (key, image.copy())
                else:
                    image = source.copy()
                from PIL import ImageOps

                image = ImageOps.fit(image, size, method=Image.Resampling.LANCZOS)
                if shot.get("camera"):
                    poses = shot["camera"]
                    start, end = poses.get("from", [0.5, 0.5, 1]), poses.get("to", [0.5, 0.5, 1])
                    t = local / max(1, shot["frames"] - 1)
                    x, y, zoom = [a + (b - a) * t for a, b in zip(start, end)]
                    w, h = size[0] / zoom, size[1] / zoom
                    left = min(max(0, x * size[0] - w / 2), size[0] - w)
                    top = min(max(0, y * size[1] - h / 2), size[1] - h)
                    image = image.resize(size, Image.Resampling.BICUBIC, box=(left, top, left + w, top + h))
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
                overlay.apply(
                    [
                        {
                            "type": "text",
                            "name": f"caption-{j}",
                            "text": c["text"],
                            "size": max(1, round(c.get("size", 40) * scale)),
                            "color": c.get("color", "white"),
                            "x": c.get("x", 20) * scale,
                            "y": c.get("y", settings["height"] - 80) * scale,
                        }
                        for j, c in enumerate(captions)
                    ]
                )
                image.alpha_composite(overlay.render())
            yield image
            # Release completed sources; long films do not keep every decoded image in memory.
            for i in list(sources):
                shot = settings["shots"][i]
                if frame + 1 >= shot["start_frame"] + shot["frames"]:
                    sources.pop(i)
                    memo.pop(i, None)
                    if i in clips:
                        clips.pop(i).close()


def export(spec, root, output, *, limits=None, cancelled=lambda: False, progress=lambda value: None):
    import json

    output = Path(output)
    require(output.suffix.lower() in (".zip", ".mp4", ".webm"), "Film output must be ZIP, MP4 or WebM")
    streamed = output.suffix.lower() in (".mp4", ".webm")
    settings = plan(spec, limits, streamed)
    require(not output.exists(), "Film output already exists")
    require(output.suffix != ".zip" or not spec.get("audio"), "Audio requires MP4/WebM output")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output.parent, prefix=".film-") as temp:
        staged = Path(temp) / output.name
        stream = frames(spec, root, limits=limits, cancelled=cancelled, streamed=streamed)

        def tracked():
            try:
                for i, image in enumerate(stream):
                    progress({"done": i + 1, "total": settings["frames"]})
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
                    json.dumps({"version": 1, "fps": settings["fps"], "frames": settings["frames"]}),
                )
        else:
            from .timeline import _video

            size = (settings["width"], settings["height"])
            if spec.get("quality") == "draft":
                ratio = min(1, 640 / max(size))
                size = tuple(max(1, round(n * ratio)) for n in size)
            _video(staged, tracked(), settings["fps"], output.suffix[1:], 90, False, settings["frames"], size)
            if spec.get("audio"):
                mixed = Path(temp) / ("mixed" + output.suffix)
                command = [shutil.which("ffmpeg"), "-v", "error", "-i", str(staged)]
                filters = []
                for i, track in enumerate(spec["audio"], 1):
                    path = local_path(root, track["source"])
                    command.extend(["-ss", str(track.get("trim", 0) / 1000), "-i", str(path)])
                    delay = round(track.get("start", 0))
                    filters.append(f"[{i}:a]volume={track.get('volume', 1)},adelay={delay}:all=1[a{i}]")
                labels = "".join(f"[a{i}]" for i in range(1, len(spec["audio"]) + 1))
                filters.append(labels + f"amix=inputs={len(spec['audio'])}:normalize=0,apad[a]")
                command.extend(
                    [
                        "-filter_complex",
                        ";".join(filters),
                        "-map",
                        "0:v",
                        "-map",
                        "[a]",
                        "-c:v",
                        "copy",
                        "-c:a",
                        "aac" if output.suffix == ".mp4" else "libopus",
                        "-t",
                        str(settings["duration"] / 1000),
                        str(mixed),
                    ]
                )
                result = subprocess.run(command, capture_output=True, timeout=600)
                require(result.returncode == 0, "Audio mix failed", "codec_error")
                staged = mixed
        require(not cancelled(), "Film cancelled", "cancelled")
        publish_file(output, staged)
    return {
        "version": 1,
        "output": str(output),
        "frames": settings["frames"],
        "duration": settings["duration"],
        "quality": spec.get("quality", "final"),
    }
