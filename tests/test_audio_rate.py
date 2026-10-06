import json
import shutil
import subprocess
import wave

import numpy as np
import pytest

from vixl import Project
from vixl.audio import mix_tracks, plan_mix, read_audio, resample, wav_bytes, export_audio
from vixl.errors import VixlError

needs_ffmpeg = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg is optional")


def tone(rate, frequency=1000, seconds=0.5, channels=1):
    t = np.arange(round(rate * seconds)) / rate
    signal = (0.5 * np.sin(2 * np.pi * frequency * t)).astype(np.float32)
    return np.repeat(signal[:, None], channels, axis=1)


def peak_hz(samples, rate):
    spectrum = np.abs(np.fft.rfft(samples[:, 0] * np.hanning(len(samples))))
    return np.argmax(spectrum) * rate / len(samples)


def write_wav(path, samples, rate):
    path.write_bytes(wav_bytes(samples, rate))
    return path.name


def test_rate_follows_sources_and_mono_is_kept(tmp_path):
    a = write_wav(tmp_path / "a.wav", tone(44100), 44100)
    b = write_wav(tmp_path / "b.wav", tone(22050), 22050)
    assert plan_mix([{"source": a}, {"source": b}], root=tmp_path) == {"sample_rate": 44100, "channels": 1}
    assert plan_mix([{"synth": "sine"}]) == {"sample_rate": 48000, "channels": 1}
    assert plan_mix([{"synth": "sine", "pan": 0.5}])["channels"] == 2
    hi = write_wav(tmp_path / "hi.wav", tone(96000, channels=2), 96000)
    assert plan_mix([{"source": hi}], root=tmp_path) == {"sample_rate": 48000, "channels": 2}
    assert plan_mix([{"source": hi}], root=tmp_path, sample_rate=96000)["sample_rate"] == 96000
    assert plan_mix([{"source": a}], root=tmp_path, encoder="opus")["sample_rate"] == 48000
    mixed = mix_tracks([{"source": a}], 500, root=tmp_path)
    assert mixed.shape == (22050, 1)
    with pytest.raises(VixlError):
        plan_mix([{"synth": "sine"}], sample_rate=1234)


def test_numpy_resampler_keeps_pitch_and_rejects_aliases():
    source = tone(44100, 1000)
    up = resample(source, 44100, 48000, engine="numpy")
    assert len(up) == 24000
    assert abs(peak_hz(up, 48000) - 1000) < 5
    # Steady-state amplitude is preserved (no droop like a box filter).
    assert abs(np.max(np.abs(up[2000:-2000])) - 0.5) < 0.01
    # 20 kHz cannot be represented at 16 kHz: a band-limited resampler removes it instead of
    # folding it to 4 kHz, which linear interpolation does.
    high = tone(44100, 20000)
    down = resample(high, 44100, 16000, engine="numpy")
    assert np.max(np.abs(down[500:-500])) < 0.02
    positions = np.arange(8000) * 44100 / 16000
    linear = np.interp(positions, np.arange(len(high)), high[:, 0])
    assert np.max(np.abs(linear[500:-500])) > 0.1


@needs_ffmpeg
def test_ffmpeg_resampler_matches_length_and_pitch():
    out = resample(tone(22050, 440, channels=2), 22050, 48000, engine="ffmpeg")
    assert out.shape == (24000, 2)
    assert abs(peak_hz(out, 48000) - 440) < 5


def test_read_audio_converts_channels_and_rate():
    raw = wav_bytes(tone(32000), 32000)
    assert read_audio(raw).shape == (16000, 1)
    assert read_audio(raw, 48000, 2).shape == (24000, 2)


def test_export_audio_reports_rate_and_channels(tmp_path):
    p = Project(100, 100)
    p.apply([{"type": "timeline-set", "duration": 500}, {"type": "audio-track", "name": "a", "synth": "bell", "duration": 300}])
    report = export_audio(p, tmp_path / "mix.wav")
    assert report["sample_rate"] == 48000 and report["channels"] == 1
    with wave.open(str(tmp_path / "mix.wav")) as w:
        assert (w.getframerate(), w.getnchannels(), w.getnframes()) == (48000, 1, 24000)
    report = export_audio(p, tmp_path / "mix44.wav", sample_rate=44100)
    with wave.open(str(tmp_path / "mix44.wav")) as w:
        assert w.getframerate() == 44100 == report["sample_rate"]


def stream_info(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries", "stream=sample_rate,channels",
                          "-of", "json", str(path)], capture_output=True, check=True).stdout
    stream = json.loads(out)["streams"][0]
    return int(stream["sample_rate"]), stream["channels"]


@needs_ffmpeg
def test_timeline_and_film_keep_source_rate(tmp_path):
    from vixl.film import export as film_export
    from vixl.timeline import export_timeline
    p = Project(64, 64)
    p.apply([{"type": "timeline-set", "duration": 400, "fps": 10}, {"type": "audio-track", "name": "s", "synth": "piano", "duration": 300}])
    result = export_timeline(p, tmp_path / "t.mp4")
    assert (result["sample_rate"], result["channels"]) == (48000, 1)
    assert stream_info(tmp_path / "t.mp4") == (48000, 1)
    result = export_timeline(p, tmp_path / "t44.mp4", sample_rate=44100)
    assert stream_info(tmp_path / "t44.mp4")[0] == 44100
    with pytest.raises(VixlError):
        export_timeline(p, tmp_path / "t.gif", sample_rate=44100)
    song = write_wav(tmp_path / "song.wav", tone(44100, 440, 1.0, channels=2), 44100)
    from PIL import Image
    Image.new("RGB", (64, 64), "red").save(tmp_path / "still.png")
    spec = {"width": 64, "height": 64, "fps": 10, "shots": [{"source": "still.png", "duration": 500}], "audio": [{"source": song}]}
    report = film_export(spec, tmp_path, tmp_path / "film.mp4")
    assert (report["sample_rate"], report["channels"]) == (44100, 2)
    assert stream_info(tmp_path / "film.mp4") == (44100, 2)
    report = film_export(spec, tmp_path, tmp_path / "film.webm")
    assert report["sample_rate"] == 48000
