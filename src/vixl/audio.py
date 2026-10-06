"""Deterministic score/SFX synthesis and bounded WAV mixing, with millisecond timing."""
import hashlib
import io
import math
from pathlib import Path
import subprocess
import wave
import numpy as np
from .errors import VixlError, require
from .model import finite

TYPES = ("audio-track", "audio-remove")
INSTRUMENTS = ("sine", "triangle", "square", "saw", "piano", "bell", "bass", "kick", "snare", "hihat", "noise", "whoosh", "pop", "click", "splash")
RATE = 24000


def schemas(add):
    from .motion_schema import documented
    add = documented(add)
    from .schema import S, N
    add("audio-track", {"name": S, "source": S, "asset": S, "synth": {"type": ["object", "string"]},
        "notes": {"type": "array", "maxItems": 1000, "items": {"type": "object"}}, "duration": N,
        "start": {"type": ["number", "string"]}, "trim": N, "volume": N, "fade_in": N, "fade_out": N, "envelope": {"type": "object"}, "pan": N, "seed": {"type": "integer"}}, ["name"], anyOf=[{"required": ["source"]}, {"required": ["asset"]}, {"required": ["synth"]}])
    add("audio-remove", {"name": S}, ["name"])


def validate_track(track):
    allowed = {"name", "source", "asset", "synth", "notes", "duration", "start", "trim", "volume", "fade_in", "fade_out", "envelope", "pan", "seed"}
    require(isinstance(track, dict) and not set(track) - allowed, "Unknown audio track field")
    require(sum(k in track for k in ("source", "asset", "synth")) == 1, "Audio track needs exactly one source, asset or synth")
    for key in ("source", "asset"):
        if key in track:
            require(isinstance(track[key], str) and track[key], "Audio source must be a nonempty string")
    for key, default, low, high in (("volume", 1, 0, 4), ("trim", 0, 0, 600000), ("fade_in", 0, 0, 600000), ("fade_out", 0, 0, 600000), ("pan", 0, -1, 1), ("duration", 1000, 10, 600000)):
        finite(track.get(key, default), key, low, high)
    if not isinstance(track.get("start", 0), str):
        finite(track.get("start", 0), "audio start", 0, 600000)
    if "synth" in track:
        synth = {"instrument": track["synth"]} if isinstance(track["synth"], str) else track["synth"]
        require(isinstance(synth, dict) and set(synth) <= {"instrument", "frequency", "duration", "seed", "envelope"}, "Invalid synth fields")
        require(synth.get("instrument", "sine") in INSTRUMENTS, "Unknown instrument or sound effect")
        finite(synth.get("frequency", 440), "frequency", 20, 10000)
        finite(synth.get("duration", track.get("duration", 1000)), "synth duration", 10, 600000)
    seed = track.get("seed", 0)
    require(isinstance(seed, int) and not isinstance(seed, bool) and 0 <= seed < 2 ** 63, "Seed must be a nonnegative 63-bit integer")
    if isinstance(track.get("synth"), dict) and "seed" in track["synth"]:
        seed = track["synth"]["seed"]
        require(isinstance(seed, int) and not isinstance(seed, bool) and 0 <= seed < 2 ** 63, "Seed must be a nonnegative 63-bit integer")
    notes = track.get("notes", [])
    require(isinstance(notes, list) and len(notes) <= 1000, "Score supports at most 1000 notes")
    for note in notes:
        require(isinstance(note, dict) and set(note) <= {"start", "duration", "frequency", "midi", "velocity", "instrument"}, "Invalid score note")
        finite(note.get("start", 0), "note start", 0, 600000)
        finite(note.get("duration", 250), "note duration", 10, 600000)
        finite(note.get("velocity", 1), "velocity", 0, 1)
        finite(note.get("frequency", 440), "frequency", 20, 10000)
        if "midi" in note:
            finite(note["midi"], "MIDI pitch", 0, 127)
        require(note.get("instrument", "sine") in INSTRUMENTS, "Unknown score instrument")
    require(sum(note.get("duration", 250) for note in notes) <= 3600000, "Score exceeds synthesis work budget", "resource_limit")
    for envelope in (track.get("envelope", {}), (track.get("synth") or {}).get("envelope", {}) if isinstance(track.get("synth"), dict) else {}):
        require(isinstance(envelope, dict) and set(envelope) <= {"attack", "decay", "sustain", "release"}, "Invalid ADSR envelope")
        for key, value in envelope.items():
            finite(value, key, 0, 1 if key == "sustain" else 600000)


def _tone(instrument, frequency, duration, rng, envelope=None, rate=RATE):
    n = max(1, round(duration * rate / 1000))
    t = np.arange(n, dtype=np.float64) / rate
    phase = math.tau * frequency * t
    if instrument in ("sine", "bass"):
        signal = np.sin(phase)
        if instrument == "bass":
            signal = (signal + 0.2 * np.sin(phase * 2)) / 1.2
    elif instrument in ("triangle", "square", "saw"):
        # Band-limited additive oscillators avoid aliasing at high pitches.
        signal = np.zeros(n)
        for harmonic in range(1, min(64, int(rate / 2 / frequency)) + 1):
            if instrument in ("triangle", "square") and harmonic % 2 == 0:
                continue
            weight = (-1) ** ((harmonic - 1) // 2) / harmonic ** 2 if instrument == "triangle" else 1 / harmonic
            signal += weight * np.sin(phase * harmonic)
        peak = np.max(np.abs(signal))
        signal /= max(peak, 1)
    elif instrument in ("piano", "bell"):
        signal = sum(np.sin(phase * harmonic) * np.exp(-t * decay) * amplitude for harmonic, decay, amplitude in ((1, 2, 0.65), (2 if instrument == "piano" else 2.76, 4, 0.25), (3 if instrument == "piano" else 5.4, 7, 0.1)))
    elif instrument in ("kick", "pop"):
        high, low = (140, 45) if instrument == "kick" else (900, 220)
        sweep = low * t + (high - low) * (1 - np.exp(-t * 30)) / 30
        signal = np.sin(math.tau * sweep) * np.exp(-t * (12 if instrument == "kick" else 35))
    elif instrument == "click":
        signal = rng.uniform(-1, 1, n) * np.exp(-t * 250)
    else:
        signal = rng.uniform(-1, 1, n)
        if instrument in ("hihat", "snare"):
            signal = (signal - np.roll(signal, 1)) / 2
            signal *= np.exp(-t * (45 if instrument == "hihat" else 18))
        elif instrument == "whoosh":
            smooth = np.convolve(signal, np.ones(8) / 8, mode="same")
            signal = smooth * np.sin(np.linspace(0, math.pi, n)) ** 2
        elif instrument == "splash":
            signal *= np.exp(-t * 5) * (0.6 + 0.4 * np.sin(t * 53) ** 2)
    env = {"attack": 5, "decay": 80, "sustain": 0.7, "release": min(80, duration / 4), **(envelope or {})}
    attack, decay, release = [max(0, round(env[k] * rate / 1000)) for k in ("attack", "decay", "release")]
    gain = np.full(n, env["sustain"])
    attack = min(n, attack)
    if attack:
        gain[:attack] = np.linspace(0, 1, attack)
    decay = min(n - attack, decay)
    if decay:
        gain[attack:attack + decay] = np.linspace(1, env["sustain"], decay)
    release = min(n, release)
    if release:
        gain[-release:] *= np.linspace(1, 0, release)
    return (signal * gain * 0.7).astype(np.float32)


def synthesize(track, rate=RATE):
    validate_track(track)
    settings = {"instrument": track["synth"]} if isinstance(track["synth"], str) else track["synth"]
    duration = track.get("duration", settings.get("duration", 1000))
    notes = track.get("notes") or [{"duration": duration, "frequency": settings.get("frequency", 440)}]
    duration = max(duration, max(note.get("start", 0) + note.get("duration", 250) for note in notes))
    finite(duration, "score duration", 10, 600000)
    samples = np.zeros(round(duration * rate / 1000), dtype=np.float32)
    rng = np.random.default_rng(track.get("seed", settings.get("seed", 0)))
    for note in notes:
        frequency = 440 * 2 ** ((note["midi"] - 69) / 12) if "midi" in note else note.get("frequency", settings.get("frequency", 440))
        tone = _tone(note.get("instrument", settings.get("instrument", "sine")), frequency, note.get("duration", 250), rng, track.get("envelope", settings.get("envelope")), rate)
        start = round(note.get("start", 0) * rate / 1000)
        count = min(len(tone), len(samples) - start)
        samples[start:start + count] += tone[:count] * note.get("velocity", 1)
    return np.column_stack([samples, samples])


def wav_bytes(samples, rate=RATE):
    stream = io.BytesIO()
    with wave.open(stream, "wb") as wav:
        wav.setnchannels(1 if samples.ndim == 1 else samples.shape[1])
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(np.rint(np.clip(samples, -1, 1) * 32767).astype("<i2").tobytes())
    return stream.getvalue()


def read_audio(data, rate=RATE):
    try:
        with wave.open(io.BytesIO(data), "rb") as wav:
            channels, width, source_rate, frames = wav.getnchannels(), wav.getsampwidth(), wav.getframerate(), wav.getnframes()
            require(channels in (1, 2) and width in (1, 2, 3, 4), "WAV needs mono/stereo PCM")
            require(frames / source_rate <= 600, "Audio exceeds 10 minutes", "resource_limit")
            raw = wav.readframes(frames)
            if width == 1:
                values = (np.frombuffer(raw, dtype=np.uint8).astype(np.float32) - 128) / 128
            elif width == 3:
                b = np.frombuffer(raw, dtype=np.uint8).reshape(-1, 3).astype(np.int32)
                integer = b[:, 0] | (b[:, 1] << 8) | (b[:, 2] << 16)
                values = ((integer ^ 0x800000) - 0x800000).astype(np.float32) / 8388608
            else:
                values = np.frombuffer(raw, dtype=f"<i{width}").astype(np.float32) / 2 ** (8 * width - 1)
            values = values.reshape(-1, channels)
            if channels == 1:
                values = np.repeat(values, 2, axis=1)
            if source_rate != rate and len(values):
                positions = np.arange(round(len(values) * rate / source_rate)) * source_rate / rate
                values = np.column_stack([np.interp(positions, np.arange(len(values)), values[:, c]) for c in range(2)]).astype(np.float32)
            return values
    except (wave.Error, EOFError, ValueError) as exc:
        raise VixlError("invalid_audio", "Audio must be a readable PCM WAV file") from exc


def mix_tracks(tracks, duration, *, root=None, project=None, rate=RATE):
    finite(duration, "audio duration", 10, 600000)
    require(len(tracks) <= 32, "At most 32 audio tracks")
    result = np.zeros((round(duration * rate / 1000), 2), dtype=np.float32)
    for track in tracks:
        validate_track(track)
        if "synth" in track:
            data = synthesize(track, rate)
        elif "asset" in track:
            require(project is not None and track["asset"] in project.assets, "Missing audio asset")
            data = read_audio(project.assets[track["asset"]], rate)
        else:
            from .film import local_path
            from .assets import read_bounded
            require(root is not None, "Audio sources need a workspace")
            source = local_path(root, track["source"])
            if source.suffix.lower() == ".wav":
                data = read_audio(read_bounded(source, 64 * 1024 * 1024), rate)
            else:
                import shutil
                ffmpeg = shutil.which("ffmpeg")
                require(ffmpeg, "Compressed audio import needs ffmpeg", "missing_dependency")
                from .media_analysis import probe
                info, _ = probe(source)
                streams = [stream for stream in info.get("streams", []) if stream.get("codec_type") == "audio"]
                require(streams, "Media has no audio stream")
                channels = min(2, streams[0].get("channels", 2))
                command = [ffmpeg, "-v", "error", "-i", str(source), "-vn", "-t", "600", "-ac", str(channels), "-ar", str(rate), "-f", "f32le", "pipe:1"]
                decoded = subprocess.run(command, capture_output=True, timeout=90)
                require(decoded.returncode == 0, "Audio decode failed", "codec_error")
                data = np.frombuffer(decoded.stdout, dtype="<f4").reshape(-1, channels).copy()
                if channels == 1:
                    data = np.repeat(data, 2, axis=1)
        trim = round(track.get("trim", 0) * rate / 1000)
        data = data[trim:].copy()
        if "duration" in track:
            data = data[:round(track["duration"] * rate / 1000)]
        data *= track.get("volume", 1)
        pan = track.get("pan", 0)
        data[:, 0] *= min(1, 1 - pan)
        data[:, 1] *= min(1, 1 + pan)
        for key, tail in (("fade_in", False), ("fade_out", True)):
            n = min(len(data), round(track.get(key, 0) * rate / 1000))
            if n:
                envelope = np.linspace(0, 1, n) if not tail else np.linspace(1, 0, n)
                if tail:
                    data[-n:] *= envelope[:, None]
                else:
                    data[:n] *= envelope[:, None]
        from .timeline import parse_time
        settings = project.state.get("timeline", {}) if project else {}
        start = round(parse_time(track.get("start", 0), duration, settings.get("markers")) * rate / 1000)
        n = min(len(data), len(result) - start)
        if n > 0:
            result[start:start + n] += data[:n]
    return result


def prepare_tracks(tracks, directory, duration, *, root=None, project=None):
    """One pre-mixed legacy film track. Keeps root checks on imports and stages generated WAVs."""
    mixed = mix_tracks(tracks, duration, root=root, project=project)
    path = Path(directory) / "vixl-score.wav"
    path.write_bytes(wav_bytes(mixed))
    return [{"source": str(path), "start": 0, "trim": 0, "volume": 1}]


def execute(project, op):
    from .design import named
    name = named(op["name"])
    tracks = project.state.setdefault("audio_tracks", [])
    if op["type"] == "audio-remove":
        tracks[:] = [track for track in tracks if track["name"] != name]
        return
    track = {k: v for k, v in op.items() if k not in ("type", "target")}
    validate_track(track)
    if "source" in track:
        # Imports become embedded assets; saved projects remain portable.
        from .film import local_path
        from .assets import read_bounded
        root = getattr(project, "_workspace", None)
        require(root is not None, "Set the project workspace before importing audio; synth and asset tracks need no workspace")
        data = read_bounded(local_path(root, track.pop("source")), project.limits.max_asset_bytes)
        read_audio(data)
        asset = "assets/" + hashlib.sha256(data).hexdigest() + ".wav"
        project.assets[asset] = data
        track["asset"] = asset
    if "asset" in track:
        require(track["asset"] in project.assets, "Missing audio asset")
        read_audio(project.assets[track["asset"]])
    from .timeline import _timeline, parse_time
    timeline = _timeline(project)
    track["start"] = parse_time(track.get("start", 0), timeline["duration"], timeline.get("markers"))
    tracks[:] = [t for t in tracks if t["name"] != name]
    require(len(tracks) < 32, "At most 32 audio tracks")
    tracks.append(track)


def export_audio(project, path):
    duration = project.state.get("timeline", {}).get("duration", 1000)
    samples = mix_tracks(project.state.get("audio_tracks", []), duration, project=project)
    clipped = int(np.count_nonzero(np.abs(samples) > 1))
    with Path(path).open("xb") as stream:
        stream.write(wav_bytes(samples))
    return {"output": str(path), "duration": duration, "sample_rate": RATE, "clipped_samples": clipped}
