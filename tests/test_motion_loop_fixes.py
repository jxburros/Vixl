"""Motion, loop and animation-export fixes from the 0.22.0 QA pass: recipe durations in seamless loops,
staggered repeats, bounce contact, finding wording, size warnings, WebP timing and loop counts, and the
front-facing walk."""

import io

from PIL import Image
import pytest

from vixl.animation import size_warnings
from vixl.characters import findings as character_findings
from vixl.motion import findings as motion_findings
from vixl.project import Project
from vixl.spatial import canvas_boxes
from vixl.timeline import export_timeline, project_at, sample_track, seam_findings


def loop(duration=2000, fps=10):
    p = Project(300, 200, '#ffffff')
    p.apply({'type': 'timeline-set', 'duration': duration, 'fps': fps, 'loop_mode': 'seamless'})
    p.apply({'type': 'shape', 'name': 'blob', 'shape': 'ellipse', 'x': 100, 'y': 50, 'width': 60, 'height': 60,
             'fill': '#00aa00', 'stroke': '#000000', 'stroke_width': 3})
    p.apply({'type': 'shape', 'name': 'leaf', 'shape': 'rectangle', 'x': 20, 'y': 20, 'width': 30, 'height': 60, 'fill': '#0088ff'})
    return p


def tracks(p, name):
    layer = p.layer(name)['id']
    return [t for t in p.state['timeline']['tracks'] if t['target'] == layer]


# --- #290 line-boil and wiggle fill a seamless loop and close it

def test_line_boil_and_wiggle_default_to_the_rest_of_the_timeline():
    p = loop()
    p.apply({'type': 'motion', 'recipe': 'line-boil', 'target': 'blob'})
    p.apply({'type': 'motion', 'recipe': 'wiggle', 'target': 'leaf'})
    boil = [t for t in p.state['timeline']['tracks'] if t['property'] == 'visible']
    assert len(boil) == 3 and all(t['keys'][-1]['time'] == 2000 for t in boil)
    assert tracks(p, 'leaf')[0]['keys'][-1]['time'] == 2000
    assert p.state['timeline']['duration'] == 2000
    assert not seam_findings(p)


def test_line_boil_fits_whole_cycles_into_a_seamless_loop():
    p = loop(2400, 24)
    out = p.apply({'type': 'motion', 'recipe': 'line-boil', 'target': 'blob', 'fps': 7, 'duration': 2400})
    assert 'whole cycle' in str(out['warnings'])
    assert not [f for f in motion_findings(p) if f['code'].startswith('loop-seam')]
    shown = [sum(sample_track(p, t, time) for t in p.state['timeline']['tracks']) for time in range(0, 2400, 50)]
    assert set(shown) == {1}, 'exactly one drawing shows at every moment'


def test_wiggle_in_a_seamless_loop_rounds_to_whole_cycles():
    p = loop()
    out = p.apply({'type': 'motion', 'recipe': 'wiggle', 'target': 'leaf', 'frequency': 2.2, 'amount': 10})
    assert '2.2 -> 2 per second' in str(out['warnings'])
    track = tracks(p, 'leaf')[0]
    assert track['keys'][-1]['value'] == pytest.approx(track['keys'][0]['value'], abs=1e-6)


def test_wiggle_keeps_its_one_second_default_outside_the_rest_of_the_timeline_when_asked():
    p = loop()
    p.apply({'type': 'motion', 'recipe': 'wiggle', 'target': 'leaf', 'duration': 1000})
    assert tracks(p, 'leaf')[0]['keys'][-1]['time'] == 1000


# --- #294 a staggered repeat that fills the loop wraps around it

def test_staggered_repeat_wraps_around_a_seamless_loop():
    p = Project(400, 200, '#ffffff')
    p.apply({'type': 'timeline-set', 'duration': 2400, 'fps': 24, 'loop_mode': 'seamless'})
    for i in range(3):
        p.apply({'type': 'shape', 'name': f'd{i + 1}', 'shape': 'ellipse', 'x': 50 + 100 * i, 'y': 100, 'width': 30,
                 'height': 30, 'fill': '#ff0000'})
    out = p.apply({'type': 'animate-preset', 'targets': ['d1', 'd2', 'd3'], 'preset': 'float', 'duration': 800,
                   'repeat': 3, 'stagger': 120, 'close': True})
    assert p.state['timeline']['duration'] == 2400
    assert 'cannot be closed' not in str(out.get('warnings'))
    first, second, third = (tracks(p, name)[0] for name in ('d1', 'd2', 'd3'))
    for time in range(0, 2400, 37):
        assert sample_track(p, second, (time + 120) % 2400) == pytest.approx(sample_track(p, first, time), abs=0.05)
        assert sample_track(p, third, (time + 240) % 2400) == pytest.approx(sample_track(p, first, time), abs=0.05)
    assert not seam_findings(p)


def test_stagger_that_fits_the_loop_is_still_a_plain_delay():
    p = Project(400, 200, '#ffffff')
    p.apply({'type': 'timeline-set', 'duration': 2000, 'loop_mode': 'seamless'})
    for name in ('a', 'b'):
        p.apply({'type': 'shape', 'name': name, 'shape': 'ellipse', 'width': 30, 'height': 30, 'fill': '#ff0000'})
    p.apply({'type': 'animate-preset', 'targets': ['a', 'b'], 'preset': 'fade-in', 'duration': 500, 'stagger': 120})
    assert [k['time'] for k in tracks(p, 'b')[0]['keys']] == [120, 620, 1500, 2000]


# --- #296 an all-identical timeline keeps its length in WebP

def test_static_timeline_exports_a_webp_that_keeps_its_duration(tmp_path):
    p = Project(64, 64, '#203040')
    p.apply({'type': 'timeline-set', 'duration': 1000, 'fps': 10})
    p.apply({'type': 'shape', 'name': 'b', 'shape': 'rectangle', 'width': 10, 'height': 10, 'x': 5, 'y': 5, 'fill': '#ff0000'})
    p.apply({'type': 'keyframe', 'target': 'b', 'property': 'x', 'time': 500, 'value': 5})
    for name in ('s.webp', 's.gif'):
        result = export_timeline(p, tmp_path / name)
        assert result['frames'] == 1 and result['duration'] == 1000 and result['frame_durations'] == [1000]
    with Image.open(tmp_path / 's.webp') as image:
        image.load()
        assert image.info['duration'] == 1000
        assert image.convert('RGB').getpixel((8, 8)) == pytest.approx((255, 0, 0), abs=8)


# --- #297 the bounce lands on a frame

def test_bounce_has_a_key_on_the_ground_at_each_contact_frame():
    p = Project(300, 200)
    p.apply({'type': 'timeline-set', 'duration': 2000, 'fps': 20})
    p.apply({'type': 'shape', 'name': 'ball', 'shape': 'ellipse', 'x': 100, 'y': 100, 'width': 30, 'height': 30, 'fill': '#ff0000'})
    p.apply({'type': 'motion', 'recipe': 'bounce', 'target': 'ball', 'amount': 150, 'gravity': 980, 'restitution': .65,
             'duration': 2000})
    keys = tracks(p, 'ball')[0]['keys']
    grounded = [k['time'] for k in keys if k['value'] == 0]
    assert grounded[:2] == [550, 1250]  # contacts at 553 and 1272 ms, on the nearest 50 ms frame
    assert all(k['value'] <= 0 for k in keys)


# --- #298 findings name layers and round values

def test_seam_and_linear_findings_name_the_layer():
    p = loop()
    p.apply({'type': 'animate', 'target': 'leaf', 'property': 'translate-y', 'from': 0, 'to': -5.599712345, 'duration': 700, 'easing': 'linear'})
    messages = [f['message'] for f in motion_findings(p)]
    seam = next(m for m in messages if m.startswith('Loop seam'))
    assert "translate-y on 'leaf' ends at -5.6 but starts at 0" in seam and 'lyr_' not in seam
    assert any("Two-key linear translate-y on 'leaf'" in m for m in messages)


def test_spin_is_not_reported_as_linear_motion():
    p = loop()
    p.apply({'type': 'motion', 'recipe': 'spin', 'target': 'leaf'})
    assert 'linear-motion' not in {f['code'] for f in motion_findings(p)}


# --- #301 size warnings agree with the settings in use

def test_size_warnings_respect_a_met_target_and_the_dither_in_use():
    big = b'x' * 1_879_995
    assert size_warnings('gif', big) and 'pass target_bytes; or export' in size_warnings('gif', big)[0]
    assert not size_warnings('gif', big, budget=2_000_000)
    banding = size_warnings('gif', b'x' * 400_000, gradients=True, dither='ordered')
    assert banding and "pass dither" not in banding[0]
    assert "pass dither: 'ordered'" in size_warnings('gif', b'x' * 400_000, gradients=True, dither='none')[0]
    worse = size_warnings('gif', big, webp=lambda: 3_463_542)[0]
    assert 'or export MP4 (a WebP of these frames measured no smaller: 3,463,542 bytes).' in worse


def test_a_missed_target_is_reported_once(tmp_path):
    p = Project(160, 120, '#203040')
    p.apply({'type': 'shape', 'name': 'b', 'shape': 'ellipse', 'width': 40, 'height': 40, 'fill': '#ffcc33'})
    p.apply({'type': 'timeline-set', 'duration': 1000, 'fps': 10})
    p.apply({'type': 'animate', 'target': 'b', 'property': 'x', 'from': 0, 'to': 100, 'easing': 'linear'})
    result = export_timeline(p, tmp_path / 'tiny.webp', target_bytes=50)
    assert sum('target' in w for w in result['warnings']) == 1


# --- #303 a pendulum turning around at the seam is not a speed kink

def test_baked_attach_track_turning_at_the_seam_has_no_speed_note():
    p = Project(400, 300, '#ffffff')
    p.apply({'type': 'timeline-set', 'duration': 2000, 'fps': 24, 'loop_mode': 'seamless'})
    p.apply({'type': 'shape', 'name': 'arm', 'shape': 'rectangle', 'x': 190, 'y': 50, 'width': 20, 'height': 120, 'fill': '#333333'})
    p.apply({'type': 'pivot', 'target': 'arm', 'value': [0.5, 0]})
    p.apply({'type': 'animate', 'target': 'arm', 'property': 'rotation', 'from': -30, 'to': 30, 'end': 1000, 'easing': 'ease-in-out', 'close': True})
    p.apply({'type': 'shape', 'name': 'sword', 'shape': 'rectangle', 'x': 195, 'y': 165, 'width': 10, 'height': 60, 'fill': '#888888'})
    p.apply({'type': 'motion', 'recipe': 'attach', 'target': 'sword', 'follow': 'arm', 'anchor': 'bottom', 'close': True})
    assert not [item for item in seam_findings(p) if item['kind'] == 'speed']


def test_a_sharp_turn_at_the_seam_is_still_a_speed_note():
    p = loop()
    p.apply({'type': 'animate', 'target': 'leaf', 'property': 'translate-x', 'from': 0, 'to': 100, 'end': 1000, 'easing': 'linear', 'close': True})
    assert [item['kind'] for item in seam_findings(p)] == ['speed']


# --- #304 a front-facing walk steps instead of doing the splits

def walker(**cycle):
    p = Project(600, 450, '#ffffff')
    p.apply({'type': 'timeline-set', 'duration': 2000, 'fps': 24})
    p.apply({'type': 'character', 'name': 'hero', 'x': 200, 'y': 40, 'height': 320})
    p.apply({'type': 'character-cycle', 'target': 'hero', 'cycle': 'walk', 'duration': 2000, **cycle})
    return p


def test_front_facing_walk_lifts_the_feet_and_keeps_the_legs_together():
    p = walker()
    left, right = p.layer('hero/left-foot')['id'], p.layer('hero/right-foot')['id']
    gaps, lifts = [], []
    for time in range(0, 2000, 85):
        boxes = canvas_boxes(project_at(p, time))
        gaps.append(boxes[right][0] - boxes[left][0])
        lifts.append(abs(boxes[right][1] - boxes[left][1]))
    rest = canvas_boxes(p)
    assert max(gaps) - min(gaps) < 10 and max(lifts) > 10
    assert max(abs(g - (rest[right][0] - rest[left][0])) for g in gaps) < 10
    assert not character_findings(p)


def test_side_gait_on_the_front_facing_character_is_a_finding():
    p = walker(view='side')
    found = [f for f in character_findings(p) if f.get('code') == 'front-view-leg-swing']
    assert found and "'hero' faces the viewer" in found[0]['message']


# --- #372 WebP plays as often as GIF and APNG

def plays(path):
    with Image.open(path) as image:
        return image.info.get('loop')


def test_webp_loop_count_matches_gif_and_apng(tmp_path):
    p = Project(64, 64, '#ffffff')
    p.apply({'type': 'shape', 'name': 'b', 'shape': 'rectangle', 'width': 10, 'height': 10, 'fill': '#ff0000'})
    p.apply({'type': 'timeline-set', 'duration': 500, 'fps': 10, 'loop': 2})
    p.apply({'type': 'animate', 'target': 'b', 'property': 'translate-x', 'from': 0, 'to': 40})
    for name in ('l.gif', 'l.png', 'l.webp'):
        export_timeline(p, tmp_path / name)
    assert plays(tmp_path / 'l.gif') == 2  # NETSCAPE: repetitions after the first play
    assert plays(tmp_path / 'l.png') == 3 and plays(tmp_path / 'l.webp') == 3  # total plays
    p.apply({'type': 'move', 'target': 'b', 'x': 0})
    p.apply({'type': 'frame-save', 'name': 'a'})
    p.apply({'type': 'move', 'target': 'b', 'x': 20})
    p.apply({'type': 'frame-save', 'name': 'c'})
    p.apply({'type': 'animation-set', 'loop': 2})
    p.export_animation(tmp_path / 'f.webp')
    assert plays(tmp_path / 'f.webp') == 3


def test_identical_pixel_frames_keep_their_length_in_webp(tmp_path):
    p = Project(16, 16, '#ffffff')
    p.apply({'type': 'shape', 'name': 'b', 'shape': 'rectangle', 'width': 4, 'height': 4, 'fill': '#ff0000'})
    p.apply({'type': 'frame-save', 'name': 'a', 'duration': 300})
    p.apply({'type': 'frame-save', 'name': 'c', 'duration': 200})
    result = p.export_animation(tmp_path / 'same.webp')
    data = (tmp_path / 'same.webp').read_bytes()
    with Image.open(io.BytesIO(data)) as image:
        image.load()
        assert image.info['duration'] == 500
    assert result['frames'] == 1
