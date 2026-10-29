"""Animation export scheduling, encoder presets and pixel-preserving fast paths."""

from copy import deepcopy
import io
import json
import shutil
import subprocess
import zipfile

import numpy as np
from PIL import Image
import pytest

from vixl import Project, frame_workers, timeline
from vixl.errors import VixlError


def fading():
    p = Project(96, 64, '#163040')
    p.apply([
        {'type': 'shape', 'shape': 'ellipse', 'name': 'dot', 'width': 30, 'height': 30,
         'x': 20, 'y': 12, 'fill': '#f08040'},
        {'type': 'timeline-set', 'duration': 1000, 'fps': 8, 'loop': 1},
        {'type': 'animate', 'target': 'dot', 'property': 'opacity', 'from': 0.2, 'to': 1,
         'duration': 1000, 'easing': 'linear'},
    ])
    return p


def test_scalar_frames_share_bulk_geometry_but_nested_tracks_detach_it():
    p = fading()
    p.apply({'type': 'blur', 'target': 'dot', 'value': 0})
    original = deepcopy(p.state)
    layer = p.layer('dot')
    frame = timeline.project_at(p, 250)
    assert frame.layer('dot') is not layer
    assert frame.layer('dot')['effects'] is layer['effects']
    assert frame.layer('dot')['opacity'] == pytest.approx(0.4)
    effect = layer['effects'][0]['id']
    p.apply({'type': 'animate', 'target': 'dot', 'property': f'effect:{effect}', 'from': 0,
             'to': 4, 'duration': 1000, 'easing': 'linear'})
    original = deepcopy(p.state)
    frame = timeline.project_at(p, 250)
    assert frame.layer('dot')['effects'] is not p.layer('dot')['effects']
    assert frame.layer('dot')['effects'][0]['amount'] == pytest.approx(1)
    assert frame.layer('dot')['opacity'] == pytest.approx(0.4)
    timeline.render_at(p, 750)
    assert p.state == original


def test_automatic_workers_need_a_measured_payoff(monkeypatch):
    p = fading()
    monkeypatch.delenv('VIXL_FRAME_WORKERS', raising=False)
    monkeypatch.setattr(frame_workers.os, 'cpu_count', lambda: 4)
    assert frame_workers.workers_for(p, 300) == 1
    assert frame_workers.workers_for(p, 300, frame_seconds=0.003, frame_bytes=4 * 1280 * 720) == 1
    assert 1 < frame_workers.workers_for(p, 300, frame_seconds=0.2, frame_bytes=4 * 1280 * 720) <= 3
    assert frame_workers.workers_for(p, 300, preview=True, frame_seconds=1) == 1
    monkeypatch.setenv('VIXL_FRAME_WORKERS', '2')
    assert frame_workers.workers_for(p, 300, frame_seconds=0.001) == 2


def test_auto_measures_rendering_and_preserves_frame_order(monkeypatch):
    p = fading()
    calls = []

    def choose(project, count, preview=False, **sample):
        calls.append((count, sample))
        return 2 if sample else 1

    def parallel(project, times, scale, workers, cancelled):
        assert workers == 2
        for time in times:
            yield timeline.render_at(project, time)

    monkeypatch.setattr(frame_workers, 'workers_for', choose)
    monkeypatch.setattr(frame_workers, 'frames', parallel)
    times = [i * 20 for i in range(40)]
    progress = []
    images = list(timeline._frames(p, times, 1, progress=progress.append))
    assert len(images) == len(times)
    assert calls[1][0] == len(times) - frame_workers.CHUNK
    assert calls[1][1]['frame_seconds'] > 0
    assert calls[1][1]['frame_bytes'] == 96 * 64 * 4
    assert [event['done'] for event in progress] == list(range(1, 41))
    assert progress[-1]['timing']['workers'] == 2
    for index in (0, frame_workers.CHUNK - 1, frame_workers.CHUNK, 39):
        assert images[index].tobytes() == timeline.render_at(p, times[index]).tobytes()


@pytest.mark.parametrize('mode,alpha', [('RGB', 255), ('RGBA', 255), ('RGBA', 0), ('RGBA', 83)])
def test_mp4_fast_path_keeps_white_alpha_flattening(mode, alpha):
    image = Image.new('RGBA', (16, 16), (47, 123, 220, alpha)).convert(mode)
    expected = Image.new('RGBA', image.size, 'white')
    expected.alpha_composite(image.convert('RGBA'))
    actual = timeline._video_rgb(image)
    assert actual.tobytes() == expected.convert('RGB').tobytes()
    if mode == 'RGB':
        assert actual is image


def test_fast_png_frames_keep_every_pixel(tmp_path):
    p = fading()
    result = timeline.export_timeline(p, tmp_path / 'frames.zip')
    with zipfile.ZipFile(result['output']) as archive:
        for index in range(8):
            data = archive.read(f'frame_{index:05d}.png')
            image = Image.open(io.BytesIO(data)).convert('RGBA')
            assert image.tobytes() == timeline.render_at(p, index * 125).tobytes()


@pytest.mark.skipif(not shutil.which('ffmpeg') or not shutil.which('ffprobe'), reason='ffmpeg is optional')
@pytest.mark.parametrize('format_,preset', [('mp4', 'final'), ('mp4', 'draft'), ('webm', 'final'), ('webm', 'draft')])
def test_video_presets_encode_the_requested_frames(tmp_path, monkeypatch, format_, preset):
    commands = []
    popen = subprocess.Popen

    def record(command, **options):
        commands.append(command)
        return popen(command, **options)

    monkeypatch.setattr(timeline.subprocess, 'Popen', record)
    result = timeline.export_timeline(fading(), tmp_path / f'video.{format_}', preset=preset)
    assert result['preset'] == preset and result['frames'] == 8 and result['size'] == [96, 64]
    command = commands[0]
    if format_ == 'mp4':
        assert command[command.index('-preset') + 1] == ('veryfast' if preset == 'draft' else 'medium')
    else:
        assert command[command.index('-row-mt') + 1] == '1'
        assert command[command.index('-deadline') + 1] == 'good'
        assert command[command.index('-cpu-used') + 1] == ('6' if preset == 'draft' else '4')
    raw = subprocess.run(['ffmpeg', '-v', 'error', '-i', result['output'], '-f', 'rawvideo',
                          '-pix_fmt', 'rgb24', '-'], check=True, capture_output=True).stdout
    frames = np.frombuffer(raw, dtype=np.uint8).reshape((-1, 64, 96, 3))
    assert len(frames) == 8
    expected = np.asarray(timeline.render_at(fading(), 875).convert('RGB')).astype(int)
    assert np.abs(frames[-1].astype(int) - expected).mean() < 8


def test_video_presets_validate_before_writing(tmp_path):
    p = fading()
    for suffix, preset in [('gif', 'draft'), ('mp4', 'chat'), ('zip', 'final'), ('webm', 'fast')]:
        path = tmp_path / f'bad.{suffix}'
        with pytest.raises(VixlError):
            timeline.export_timeline(p, path, preset=preset)
        assert not path.exists()


def test_cli_accepts_video_preset(tmp_path, monkeypatch, capsys):
    from vixl.cli import main

    p = fading()
    path = tmp_path / 'motion.vixl'
    p.save(path)
    received = []

    def encode(path, frames, fps, format, quality, overwrite, count, size, preset):
        received.append(preset)
        return {'preset': preset, 'format': format}

    monkeypatch.setattr(timeline, '_video', encode)
    assert main(['-p', str(path), 'export-timeline', '--out', str(tmp_path / 'draft.mp4'), '--preset', 'draft']) == 0
    assert received == ['draft']
    assert json.loads(capsys.readouterr().out)['preset'] == 'draft'


def test_render_lock_video_presets_are_normalized():
    from vixl.plugins.workspace_qa.export_lock import parse

    assert parse('mp4') == parse('mp4:preset=final')
    assert parse('webm:preset=draft')['options']['preset'] == 'draft'
    with pytest.raises(VixlError):
        parse('mp4:preset=chat')
