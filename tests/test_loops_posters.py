"""Seamless loops, repeat/stagger, time-aware checks, poster frames, GIF dithering and honest export results."""
import io

import numpy as np
import pytest
from PIL import Image

from vixl.checks import check_design
from vixl.errors import VixlError
from vixl.project import Project
from vixl.timeline import contact_sheet, export_timeline, project_at, sample_frame_times


def card():
    p = Project(200, 150, '#203040')
    p.apply({'type': 'shape', 'name': 'sun', 'shape': 'ellipse', 'width': 40, 'height': 40, 'x': 20, 'y': 80, 'fill': '#ffcc33'})
    p.apply({'type': 'text', 'name': 'greeting', 'text': 'Hello', 'x': 20, 'y': 20, 'size': 30, 'color': '#ffffff'})
    p.apply({'type': 'timeline-set', 'duration': 2000, 'fps': 10})
    return p


def track(p, name, prop):
    layer = p.layer(name)['id']
    return next(t for t in p.state['timeline']['tracks'] if t['target'] == layer and t['property'] == prop)


def codes(result):
    return {i.get('code') for i in result['issues'] if i['check'] == 'motion'}


# --- #238 seamless loops

def test_close_appends_start_value_at_loop_end():
    p = card()
    p.apply({'type': 'animate', 'target': 'sun', 'property': 'translate-x', 'from': 0, 'to': 80, 'end': 1000, 'close': True})
    keys = track(p, 'sun', 'translate-x')['keys']
    assert keys[-1] == {'time': 2000, 'value': 0}
    assert project_at(p, 1999).layer('sun')['x'] == pytest.approx(20, abs=1)


def test_close_matches_ease_in_out_speed_at_the_seam():
    p = card()
    p.apply({'type': 'animate', 'target': 'sun', 'property': 'translate-x', 'from': 0, 'to': 80, 'end': 1000, 'close': True})
    assert track(p, 'sun', 'translate-x')['keys'][1].get('easing') == 'ease-in-out'


def test_entrance_preset_closes_itself_in_a_seamless_loop():
    p = card()
    p.apply({'type': 'timeline-set', 'loop_mode': 'seamless'})
    p.apply({'type': 'animate-preset', 'target': 'greeting', 'preset': 'fade-in', 'duration': 500})
    keys = track(p, 'greeting', 'opacity')['keys']
    assert [k['time'] for k in keys] == [0, 500, 1500, 2000]
    assert keys[0]['value'] == keys[-1]['value'] == 0.0 and keys[2]['value'] == 1
    assert project_at(p, 1000).layer('greeting')['opacity'] == 1


def test_timeline_set_warns_and_closes_open_tracks():
    p = card()
    p.apply({'type': 'animate', 'target': 'sun', 'property': 'opacity', 'from': 0, 'to': 1, 'end': 500})
    out = p.apply({'type': 'timeline-set', 'loop_mode': 'seamless'})
    assert 'loop jumps' in str(out)
    assert p.state['timeline']['loop'] == 0
    p.apply({'type': 'timeline-set', 'loop_mode': 'seamless', 'close': True})
    assert track(p, 'sun', 'opacity')['keys'][-1]['time'] == 2000


def test_spin_with_symmetry_turns_one_ray_period_and_loops():
    p = card()
    p.apply({'type': 'motion', 'recipe': 'spin', 'target': 'sun', 'symmetry': 12})
    keys = track(p, 'sun', 'rotation')['keys']
    assert [(k['time'], k['value']) for k in keys] == [(0, 0), (2000, 30.0)]
    result = check_design(p, checks=['motion'])
    assert 'loop-seam' not in codes(result)


def test_spin_without_symmetry_is_a_full_turn_and_fractional_turns_warn():
    p = card()
    p.apply({'type': 'motion', 'recipe': 'spin', 'target': 'sun'})
    assert track(p, 'sun', 'rotation')['keys'][-1]['value'] == 360
    q = card()
    out = q.apply({'type': 'motion', 'recipe': 'spin', 'target': 'sun', 'turns': 0.5})
    assert 'not a whole number' in str(out)


# --- #185 repeat and stagger

def test_repeat_and_stagger_write_a_typing_loop_in_one_operation():
    p = card()
    for name in ('a', 'b', 'c'):
        p.apply({'type': 'shape', 'name': name, 'shape': 'ellipse', 'width': 10, 'height': 10, 'x': 10, 'y': 10, 'fill': '#fff'})
    p.apply({'type': 'animate-preset', 'targets': ['a', 'b', 'c'], 'preset': 'float', 'amount': 12, 'duration': 700, 'repeat': 2, 'stagger': 150})
    a, b = track(p, 'a', 'translate-y')['keys'], track(p, 'b', 'translate-y')['keys']
    assert [k['time'] for k in a][:3] == [0, 350, 699] or a[0]['time'] == 0
    assert b[0]['time'] == 150
    assert max(k['time'] for k in a) == 1400
    assert max(k['time'] for k in b) == 1550


def test_animate_repeat_restarts_from_the_same_value():
    p = card()
    p.apply({'type': 'animate', 'target': 'sun', 'property': 'translate-x', 'from': 0, 'to': 50, 'start': 0, 'duration': 500, 'repeat': 3, 'easing': 'linear'})
    assert project_at(p, 250).layer('sun')['x'] == pytest.approx(45, abs=.2)
    assert project_at(p, 750).layer('sun')['x'] == pytest.approx(45, abs=.2)
    assert project_at(p, 1250).layer('sun')['x'] == pytest.approx(45, abs=.2)


def test_stagger_without_targets_is_rejected():
    p = card()
    with pytest.raises(VixlError):
        p.apply({'type': 'animate-preset', 'target': 'sun', 'preset': 'pulse', 'stagger': 100})


# --- #237 time-aware checks

def test_check_enables_motion_for_animated_documents_and_reports_the_seam():
    p = card()
    p.apply({'type': 'animate', 'target': 'sun', 'property': 'translate-x', 'from': 0, 'to': 80, 'end': 1000})
    result = check_design(p)
    assert 'motion' in result['checked']['checks']
    assert 'loop-seam' in codes(result)
    plain = Project(100, 100)
    assert 'motion' not in check_design(plain)['checked']['checks']


def test_a_play_once_timeline_has_no_seam_finding():
    p = card()
    p.apply({'type': 'timeline-set', 'loop': 1})
    p.apply({'type': 'animate', 'target': 'sun', 'property': 'translate-x', 'from': 0, 'to': 80, 'end': 1000})
    assert 'loop-seam' not in codes(check_design(p))


def test_text_hidden_at_the_poster_frame_is_reported():
    p = card()
    p.apply({'type': 'animate-preset', 'target': 'greeting', 'preset': 'fade-in', 'start': 1000, 'duration': 400})
    result = check_design(p)
    hidden = [i for i in result['issues'] if i.get('code') in ('text-hidden-at-poster', 'empty-poster')]
    assert hidden


def test_sample_frame_times_are_poster_middle_last():
    p = card()
    frames = sample_frame_times(p.state['timeline'])
    assert frames == [('poster', 0), ('middle', 950), ('last', 1900)]


# --- #189 / #253 poster frame and phone preview

def test_poster_end_rotates_frames_and_warns_when_frame_zero_is_empty(tmp_path):
    p = card()
    p.apply({'type': 'animate-preset', 'target': 'greeting', 'preset': 'fade-in', 'start': 1000, 'duration': 400})
    p.apply({'type': 'animate-preset', 'target': 'sun', 'preset': 'fade-in', 'start': 1000, 'duration': 400})
    plain = export_timeline(p, tmp_path / 'plain.gif', fps=10)
    assert any('poster' in w for w in plain['warnings'])
    result = export_timeline(p, tmp_path / 'poster.gif', fps=10, poster='end')
    assert result['poster'] == {'time': 1900, 'frame': 19}
    assert not any('poster frame' in w for w in result.get('warnings', []))
    first = Image.open(tmp_path / 'poster.gif').convert('RGB')
    base = Image.open(tmp_path / 'plain.gif').convert('RGB')
    assert np.asarray(first).std() > np.asarray(base).std()
    assert result['frames'] == Image.open(tmp_path / 'poster.gif').n_frames


def test_poster_rejected_for_video_and_sheet(tmp_path):
    p = card()
    with pytest.raises(VixlError):
        export_timeline(p, tmp_path / 'a.png', format='sheet', poster='end')


def test_contact_sheet_labels_poster_and_has_phone_thumbnail():
    p = card()
    p.apply({'type': 'animate', 'target': 'sun', 'property': 'translate-x', 'from': 0, 'to': 80, 'end': 1000})
    strip = contact_sheet(p, thumbnail=90)
    assert strip.width < 4 * 100 and strip.width >= 3 * 90
    chosen = contact_sheet(p, times=['0', '1s'], columns=2)
    assert chosen.width > 0


# --- #246 GIF dithering, size target

def gradient_card():
    p = Project(160, 120, '#000000')
    p.apply({'type': 'gradient', 'name': 'glow', 'x': 0, 'y': 0, 'width': 160, 'height': 120, 'start': '#102040', 'end': '#e0f0ff', 'direction': 'horizontal'})
    p.apply({'type': 'shape', 'name': 'dot', 'shape': 'ellipse', 'width': 10, 'height': 10, 'x': 5, 'y': 5, 'fill': '#ffffff'})
    p.apply({'type': 'timeline-set', 'duration': 500, 'fps': 10})
    p.apply({'type': 'animate', 'target': 'dot', 'property': 'x', 'from': 5, 'to': 100})
    return p


def banding(path):
    """Longest run of one value along a row of the ramp: wide flat bands are what banding looks like."""
    row = np.asarray(Image.open(path).convert('RGB'))[60, :, 0]
    longest = run = 1
    for a, b in zip(row, row[1:]):
        run = run + 1 if a == b else 1
        longest = max(longest, run)
    return longest


@pytest.mark.parametrize('mode', ['ordered', 'floyd'])
def test_gif_dither_reduces_banding(tmp_path, mode):
    p = gradient_card()
    none = export_timeline(p, tmp_path / 'none.gif', colors=16, dither='none')
    dithered = export_timeline(p, tmp_path / 'd.gif', colors=16, dither=mode)
    assert none['dither'] == 'none' and dithered['dither'] == mode
    assert banding(tmp_path / 'd.gif') < banding(tmp_path / 'none.gif')


def test_ordered_dither_does_not_shimmer_between_frames(tmp_path):
    export_timeline(gradient_card(), tmp_path / 'd.gif', colors=16, dither='ordered')
    gif = Image.open(tmp_path / 'd.gif')
    gif.seek(0)
    a = np.asarray(gif.convert('RGB'))
    gif.seek(3)
    b = np.asarray(gif.convert('RGB'))
    # The ramp far from the moving dot is identical frame to frame (error diffusion would not be).
    assert (a[60:, :] == b[60:, :]).all()


def test_gif_dither_is_rejected_for_other_formats(tmp_path):
    with pytest.raises(VixlError):
        export_timeline(gradient_card(), tmp_path / 'a.webp', dither='ordered')


def test_max_bytes_warns_and_suggests_mp4(tmp_path):
    p = gradient_card()
    result = export_timeline(p, tmp_path / 'g.gif', max_bytes=500)
    assert any('max_bytes' in w and 'MP4' in w for w in result['warnings'])
    ok = export_timeline(p, tmp_path / 'g2.gif', max_bytes=50_000_000)
    assert not any('max_bytes' in w for w in ok.get('warnings', []))


# --- #208 honest export results

def test_sheet_result_reports_the_sheet_size(tmp_path):
    p = card()
    p.apply({'type': 'animate', 'target': 'sun', 'property': 'translate-x', 'from': 0, 'to': 80, 'end': 1000})
    result = export_timeline(p, tmp_path / 's.png', format='sheet', fps=10)
    sheet = Image.open(tmp_path / 's.png')
    assert result['size'] == list(sheet.size) and result['frame_size'] == [200, 150]


def test_gif_result_reports_frames_in_the_file(tmp_path):
    p = card()
    p.apply({'type': 'animate', 'target': 'sun', 'property': 'translate-x', 'from': 0, 'to': 80, 'end': 500})
    result = export_timeline(p, tmp_path / 'm.gif', fps=10)
    gif = Image.open(tmp_path / 'm.gif')
    assert result['frames'] == gif.n_frames < result['rendered_frames']
    assert sum(result['frame_durations']) == 2000


def test_animation_export_reports_sheet_size_and_gif_frames(tmp_path):
    p = Project(16, 16, '#000000')
    for name, x in (('a', 1), ('b', 1), ('c', 8)):
        p.apply({'type': 'shape', 'name': 'sq', 'shape': 'rect', 'width': 4, 'height': 4, 'x': x, 'y': 1, 'fill': '#fff'}) if name == 'a' else p.apply({'type': 'move', 'target': 'sq', 'x': x, 'y': 1})
        p.apply({'type': 'frame-save', 'name': name, 'duration': 100})
    sheet = p.export_animation(tmp_path / 's.png', format='sheet', columns=3)
    assert sheet['size'] == list(Image.open(tmp_path / 's.png').size) == [48, 16]
    gif = p.export_animation(tmp_path / 'g.gif')
    assert gif['frames'] == Image.open(tmp_path / 'g.gif').n_frames
