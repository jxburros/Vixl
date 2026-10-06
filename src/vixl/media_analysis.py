"""Bounded media inspection: visible video samples and numeric, explicitly non-LUFS audio analysis."""
import io
import json
import math
from pathlib import Path
import shutil
import subprocess

import numpy as np
from PIL import Image, ImageDraw, ImageOps

from .errors import VixlError, require
from .model import finite
from .production import write_bytes

ACTIONS = {
    "film-preview": ({"spec", "output", "time", "start", "end", "shot", "region", "loop"}, {"spec", "output"}),
    "video-sample": ({"source", "output", "times", "interval", "start", "end", "width", "contact_sheet"}, {"source", "output"}),
    "audio-analyze": ({"source", "output", "window", "silence_db", "min_silence", "events"}, {"source"}),
}
FIELD_TYPES = {
    "source": {"type": "string", "description": "Workspace-relative media input."},
    "output": {"type": "string", "description": "New output image, sample directory, or preview file."},
    "spec": {"type": "object", "description": "Film spec; preview defaults to draft quality."},
    "time": {"type": "number", "minimum": 0, "description": "Film scrub time in milliseconds."},
    "start": {"type": "number", "minimum": 0, "description": "Start in milliseconds."},
    "end": {"type": "number", "minimum": 0, "description": "End in milliseconds (exclusive)."},
    "shot": {"type": "integer", "minimum": 0, "description": "Zero-based film shot index."},
    "region": {"type": "array", "items": {"type": "number"}, "minItems": 4, "maxItems": 4,
               "description": "[x,y,width,height] in original film pixels."},
    "loop": {"type": "integer", "minimum": 0, "maximum": 100, "description": "GIF loops; zero repeats forever."},
    "times": {"type": "array", "items": {"type": "number", "minimum": 0}, "minItems": 1, "maxItems": 64,
              "description": "Video sample times in milliseconds."},
    "interval": {"type": "number", "exclusiveMinimum": 0, "description": "Video sample spacing in milliseconds."},
    "width": {"type": "integer", "minimum": 32, "maximum": 1024, "description": "Maximum video thumbnail width/height."},
    "contact_sheet": {"type": "boolean", "default": True, "description": "Return a labeled image contact sheet."},
    "window": {"type": "number", "minimum": 20, "maximum": 5000, "description": "RMS bin duration in milliseconds; output has at most 1200 bins."},
    "silence_db": {"type": "number", "minimum": -100, "maximum": 0, "description": "RMS silence threshold in dBFS."},
    "min_silence": {"type": "number", "minimum": 0, "description": "Minimum silent run in milliseconds."},
    "events": {"type": "array", "maxItems": 100, "items": {"type": "number", "minimum": 0},
               "description": "Video event timestamps in milliseconds to compare with nearest audio onset."},
}


def run(arguments, timeout=60):
    executable = shutil.which(arguments[0])
    require(executable, f"{arguments[0]} is required for media analysis", "missing_dependency")
    try:
        result = subprocess.run([executable, *arguments[1:]], capture_output=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise VixlError("codec_error", f"Media analysis failed: {exc}") from exc
    require(result.returncode == 0, "Cannot decode media", "codec_error",
            detail=result.stderr.decode("utf-8", "replace")[:300])
    return result.stdout


def probe(source):
    try:
        info = json.loads(run(["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=codec_type,width,height,channels,sample_rate",
                               "-of", "json", str(source)]))
        duration = float(info["format"]["duration"]) * 1000
        finite(duration, "media duration", 1, 600000)
        return info, duration
    except (ValueError, KeyError, TypeError) as exc:
        raise VixlError("codec_error", "Media duration could not be read") from exc


def save_image(image, output):
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    write_bytes(output, buffer.getvalue())


def video_sample(source, output, *, times=None, interval=None, start=0, end=None, width=320, contact_sheet=True):
    info, duration = probe(source)
    require(any(s.get("codec_type") == "video" for s in info.get("streams", [])), "Media has no video stream")
    require(isinstance(width, int) and not isinstance(width, bool) and 32 <= width <= 1024, "Width must be 32–1024")
    require(isinstance(contact_sheet, bool), "contact_sheet must be boolean")
    finite(start, "start", 0, duration)
    end = duration if end is None else finite(end, "end", 0, duration)
    require(start < end, "Sample range must be nonempty")
    require(times is None or interval is None, "Choose times or interval")
    if times is None:
        interval = finite(interval if interval is not None else max(1, (end - start) / 8), "interval", 1)
        count = math.ceil((end - start) / interval)
        require(count <= 64, "At most 64 video samples; increase interval", "resource_limit")
        times = [start + i * interval for i in range(count)]
    require(isinstance(times, list) and 0 < len(times) <= 64, "Choose 1–64 sample times")
    output = Path(output)
    require(not output.exists(), "Sample output already exists")
    frames = []
    for time in times:
        finite(time, "sample time", 0, duration)
        require(time < duration, "Sample time must precede media end")
        data = run(["ffmpeg", "-v", "error", "-ss", str(time / 1000), "-i", str(source), "-frames:v", "1",
                    "-vf", f"scale={width}:{width}:force_original_aspect_ratio=decrease", "-f", "image2pipe", "-vcodec", "png", "pipe:1"])
        require(data, "No video frame at requested time", "codec_error")
        frames.append(Image.open(io.BytesIO(data)).convert("RGB"))
    if contact_sheet:
        require(output.suffix.lower() == ".png", "Contact sheet output must be PNG")
        columns = min(4, len(frames))
        cell_h = max(f.height for f in frames) + 24
        sheet = Image.new("RGB", (columns * width, math.ceil(len(frames) / columns) * cell_h), "#202329")
        draw = ImageDraw.Draw(sheet)
        for i, (frame, time) in enumerate(zip(frames, times)):
            x, y = (i % columns) * width, (i // columns) * cell_h
            sheet.paste(frame, (x, y))
            draw.text((x + 4, y + cell_h - 19), f"{time / 1000:.3f}s", fill="white")
        save_image(sheet, output)
        outputs = [str(output)]
    else:
        output.mkdir(parents=True)
        outputs = []
        for i, frame in enumerate(frames):
            path = output / f"{i:03d}-{round(times[i]):06d}ms.png"
            save_image(frame, path)
            outputs.append(str(path))
    return {"source": str(source), "times": times, "images": outputs, "duration": duration, "count": len(times)}


def analyze_samples(samples, rate, *, window=100, silence_db=-50, min_silence=200, events=None):
    """RMS/peak dBFS, spectral-flux onsets and a robust inter-onset tempo estimate, not perceptual LUFS."""
    samples = np.asarray(samples, dtype=np.float64)
    require(samples.ndim in (1, 2) and samples.size > 0 and np.isfinite(samples).all(), "Invalid audio samples")
    finite(rate, "sample rate", 1000, 192000)
    finite(window, "window", 20, 5000)
    finite(silence_db, "silence_db", -100, 0)
    finite(min_silence, "min_silence", 0, 600000)
    events = [] if events is None else events
    require(isinstance(events, list) and len(events) <= 100, "At most 100 sync events")
    duration = len(samples) * 1000 / rate
    for time in events:
        finite(time, "event time", 0, duration)
    channels = samples[:, None] if samples.ndim == 1 else samples
    mono = channels.mean(axis=1)
    hop = max(1, round(rate * window / 1000), math.ceil(len(mono) / 1200))
    rms, peak, silent = [], [], []
    for i in range(0, len(mono), hop):
        block = channels[i:i + hop]
        rms.append(float(20 * np.log10(max(1e-6, np.sqrt(np.mean(block * block))))))
        peak.append(float(20 * np.log10(max(1e-6, np.max(np.abs(block))))))
        silent.append(rms[-1] <= silence_db)
    runs, begin = [], None
    for i, quiet in enumerate([*silent, False]):
        if quiet and begin is None:
            begin = i * hop * 1000 / rate
        elif not quiet and begin is not None:
            end = min(duration, i * hop * 1000 / rate)
            if end - begin >= min_silence:
                runs.append({"start": round(begin, 2), "end": round(end, 2)})
            begin = None
    # 46ms STFT windows / 11.6ms hops at 22.05kHz. Bound the spectrogram to ~52k frames.
    fft_size = 1024
    fft_hop = max(256, math.ceil(len(mono) / 6000))
    padded = np.pad(mono, (0, max(0, fft_size - len(mono))))
    windows = np.lib.stride_tricks.sliding_window_view(padded, fft_size)[::fft_hop]
    spectrum = np.abs(np.fft.rfft(windows * np.hanning(fft_size), axis=1)).astype(np.float32)
    flux = np.maximum(0, np.diff(spectrum, axis=0, prepend=np.zeros_like(spectrum[:1]))).mean(axis=1)
    threshold = float(np.median(flux) + 1.5 * np.std(flux))
    onsets = []
    for i, value in enumerate(flux):
        time = i * fft_hop * 1000 / rate
        if value > max(1e-6, threshold) and (not onsets or time - onsets[-1] >= 120):
            if (i == 0 or value >= flux[i - 1]) and (i + 1 == len(flux) or value >= flux[i + 1]):
                onsets.append(round(time, 2))
    gaps = np.diff(onsets)
    plausible = gaps[(gaps >= 250) & (gaps <= 2000)]
    bpm = round(60000 / float(np.median(plausible)), 2) if len(plausible) >= 2 else None
    sync = [{"event": time, "onset": min(onsets, key=lambda t: abs(t-time)),
             "delta": round(min(onsets, key=lambda t: abs(t-time))-time, 2)} for time in events] if onsets else [
                 {"event": time, "onset": None, "delta": None} for time in events]
    result = {"duration": round(duration, 2), "units": "milliseconds; levels are unweighted dBFS (not LUFS)",
              "channels": channels.shape[1], "window": round(hop * 1000 / rate, 3),
              "rms_dbfs": [round(v, 2) for v in rms], "peak_dbfs": round(max(peak), 2),
              "clipped_samples": int(np.count_nonzero(np.abs(channels) >= 0.999)),
              "silence": runs, "onsets": onsets[:500], "onset_count": len(onsets),
              "estimated_bpm": bpm, "beat_method": "spectral-flux onsets; median plausible spacing; heuristic", "sync": sync}
    return result, spectrum


def audio_analyze(source, output=None, **options):
    info, _ = probe(source)
    require(any(s.get("codec_type") == "audio" for s in info.get("streams", [])), "Media has no audio stream")
    audio_stream = next(s for s in info["streams"] if s.get("codec_type") == "audio")
    channel_count = min(2, audio_stream.get("channels", 2))
    data = run(["ffmpeg", "-v", "error", "-i", str(source), "-vn", "-t", "600", "-ac", str(channel_count), "-ar", "22050",
                "-f", "f32le", "pipe:1"], timeout=120)
    samples = np.frombuffer(data, dtype="<f4").reshape(-1, channel_count)
    result, spectrum = analyze_samples(samples, 22050, **options)
    result["source"] = str(source)
    result["input_channels"] = audio_stream.get("channels", channel_count)
    result["downmixed"] = result["input_channels"] > channel_count
    if output is not None:
        require(Path(output).suffix.lower() == ".png", "Spectrogram output must be PNG")
        db = 20 * np.log10(np.maximum(spectrum, 1e-6))
        normalized = np.clip((db - db.max() + 80) / 80, 0, 1)
        raster = Image.fromarray(np.uint8(normalized.T[::-1] * 255))
        raster = ImageOps.colorize(raster.resize((960, 320)), "#101326", "#ffe9a0")
        sheet = Image.new("RGB", (960, 352), "#101326")
        sheet.paste(raster, (0, 0))
        ImageDraw.Draw(sheet).text((8, 330), f"0–{result['duration']/1000:.2f}s horizontal | 0–11025 Hz vertical | relative magnitude (80 dB)", fill="white")
        save_image(sheet, output)
        result["spectrogram"] = str(output)
    return result


def dispatch(session, action, request, document=None):
    if action == "film-preview":
        from .film import preview
        return preview(request["spec"], session.workspace, session.resolve(request["output"]), limits=session.limits,
                       **{k: v for k, v in request.items() if k not in ("spec", "output")})
    options = {k: v for k, v in request.items() if k not in ("source", "output")}
    source = session.resolve(request["source"])
    output = session.resolve(request["output"]) if request.get("output") else None
    return video_sample(source, output, **options) if action == "video-sample" else audio_analyze(source, output, **options)
