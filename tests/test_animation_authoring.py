"""Behavioral regressions for motion, rigs, compositing, captions and audio authoring."""
import io
import math
import shutil
import wave
import numpy as np
import pytest
from vixl.project import Project
from vixl.errors import VixlError
from vixl.timeline import project_at, render_at


def ball():
    p = Project(240, 180, '#203040')
    p.apply({'type': 'shape', 'name': 'ball', 'shape': 'ellipse', 'width': 20, 'height': 20, 'x': 100, 'y': 120, 'fill': '#eeaa44'})
    return p


def hero():
    p = Project(500, 450)
    p.apply({'type': 'character', 'name': 'hero', 'x': 100, 'y': 70})
    return p


def test_compact_keyframes_are_editable_and_atomic():
    p = ball()
    p.apply({'type': 'keyframes', 'target': 'ball', 'property': 'x', 'keys': [{'time': 0, 'value': 10}, {'time': 1000, 'value': 110}]})
    assert project_at(p, 500).layer('ball')['x'] == 60
    before = p.state.copy()
    with pytest.raises(VixlError):
        p.apply({'type': 'keyframes', 'target': 'ball', 'property': 'opacity', 'keys': [{'time': 0, 'value': .5}, {'time': 100, 'value': 9}]})
    assert p.state == before


def test_bounce_uses_gravity_and_dissipates_energy():
    p = ball()
    p.apply({'type': 'motion', 'target': 'ball', 'recipe': 'bounce', 'amount': 80, 'gravity': 1000, 'restitution': .5, 'duration': 2000, 'samples': 100})
    assert project_at(p, 0).layer('ball')['y'] == 40
    assert project_at(p, 200).layer('ball')['y'] == pytest.approx(60, abs=.02)
    assert project_at(p, 400).layer('ball')['y'] == pytest.approx(120, abs=.05)
    assert project_at(p, 1900).layer('ball')['y'] == pytest.approx(120, abs=.1)


def test_motion_path_speed_and_stagger():
    p = ball()
    p.apply({'type': 'duplicate', 'target': 'ball', 'name': 'other'})
    p.apply({'type': 'motion', 'targets': ['ball', 'other'], 'recipe': 'follow-path', 'points': [[0, 0], [80, 0], [80, 20]], 'duration': 1000, 'easing': 'linear', 'samples': 20, 'stagger': 100})
    assert project_at(p, 500).layer('ball')['x'] == pytest.approx(50)
    assert project_at(p, 500).layer('other')['x'] == pytest.approx(40)
    assert project_at(p, 900).layer('ball')['y'] == pytest.approx(10)


@pytest.mark.parametrize('recipe', ['orbit', 'shake', 'wiggle', 'spring', 'breathing', 'blink', 'hover'])
def test_motion_generators_are_bounded_and_render(recipe):
    p = ball()
    p.apply({'type': 'motion', 'target': 'ball', 'recipe': recipe, 'duration': 1000, 'samples': 20})
    assert p.state['timeline']['tracks']
    assert render_at(p, 350).size == (240, 180)


def test_motion_review_flags_instant_linear_starts():
    from vixl.motion import findings
    p = ball()
    p.apply({'type': 'animate', 'target': 'ball', 'property': 'x', 'to': 20, 'duration': 100, 'easing': 'linear'})
    assert findings(p)[0]['code'] == 'linear-motion'


def test_character_saved_instances_independent_and_portable(tmp_path):
    from vixl.characters import findings
    p = hero()
    p.apply([{'type': 'character-save', 'target': 'hero', 'name': 'hero-template'}, {'type': 'character-load', 'template': 'hero-template', 'name': 'friend', 'x': 300, 'scale': .7, 'colors': {'skin': '#7c5036'}}])
    a, b = p.layer('hero')['character'], p.layer('friend')['character']
    assert not set(a['parts'].values()) & set(b['parts'].values())
    assert p.layer(a['parts']['head'])['fill'] != p.layer(b['parts']['head'])['fill']
    p.save(tmp_path / 'cast.vixl')
    loaded = Project.load(tmp_path / 'cast.vixl')
    assert not findings(loaded)
    assert loaded.state['character_library']['hero-template']
    assert loaded.render().size == (500, 450)


def test_joint_limits_and_ik_keep_chain_connected():
    from vixl.characters import pose
    p = hero()
    p.apply({'type': 'character-pose', 'target': 'hero', 'angles': {'left-upper-arm': 200}})
    assert p.layer('hero')['character']['bones']['left-upper-arm']['angle'] == 100
    p.apply({'type': 'character-pose', 'target': 'hero', 'angles': {'left-upper-arm': 0}})
    group = p.layer('hero')
    current = pose(p, group, {})
    ox, oy = current['left-upper-arm'][0]
    p.apply({'type': 'character-ik', 'target': 'hero', 'chain': ['left-upper-arm', 'left-lower-arm'], 'point': [ox + 40, oy + 50]})
    solved = pose(p, p.layer('hero'), {})
    origin, angle, length = solved['left-lower-arm']
    endpoint = [origin[0] + math.sin(math.radians(angle)) * length, origin[1] + math.cos(math.radians(angle)) * length]
    assert endpoint == pytest.approx([ox + 40, oy + 50], abs=1e-6)
    # Positive solved angles turn the downward-pointing artwork toward +x.
    assert p.layer('hero/left-lower-arm')['rotation'] == pytest.approx(-angle)


def test_rig_cycle_is_rejected_atomically():
    p = hero()
    before = p.state.copy()
    with pytest.raises(VixlError, match='cycle'):
        p.apply({'type': 'character-rig', 'target': 'hero', 'bones': {'a': {'part': 'left-upper-arm', 'parent': 'b', 'length': 30}, 'b': {'part': 'left-lower-arm', 'parent': 'a', 'length': 30}}})
    assert p.state == before


@pytest.mark.parametrize('cycle', ['walk', 'run', 'idle', 'ride', 'react'])
def test_retargeted_cycle_changes_limb_pose(cycle):
    p = hero()
    p.apply({'type': 'character-cycle', 'target': 'hero', 'cycle': cycle, 'duration': 1000, 'samples': 8})
    assert p.state['timeline']['tracks']
    assert project_at(p, 250).layer('hero/left-upper-arm')['rotation'] != p.layer('hero/left-upper-arm')['rotation']
    render_at(p, 250)


def test_visemes_differ_and_explicit_cues_win():
    p = hero()
    p.apply({'type': 'character-lipsync', 'target': 'hero', 'text': 'anything', 'duration': 1000, 'cues': [{'time': 0, 'viseme': 'M'}, {'time': 500, 'viseme': 'O'}]})
    assert project_at(p, 100).layer('hero/mouth')['height'] < project_at(p, 600).layer('hero/mouth')['height']
    assert project_at(p, 1000).layer('hero/mouth')['height'] == p.layer('hero/mouth')['height']


def test_camera_parallax_focus_and_nonmutating_render():
    p = ball()
    p.apply([{'type': 'duplicate', 'target': 'ball', 'name': 'far'}, {'type': 'layer-depth', 'target': 'far', 'depth': 4}, {'type': 'camera', 'from': [0, 0, 1], 'to': [40, 0, 1], 'duration': 1000, 'focus': 1, 'aperture': 2}])
    frame = project_at(p, 1000)
    assert frame.layer('ball')['x'] == 60
    assert frame.layer('far')['x'] == 90
    assert frame.layer('far')['effects'][-1]['amount'] == 6
    assert p.layer('ball')['x'] == 100


def test_particles_repeat_deterministically_and_obey_gravity():
    p = Project(120, 120)
    p.apply({'type': 'particles', 'name': 'sparks', 'preset': 'sparks', 'count': 3, 'x': 30, 'y': 20, 'spread': [0, 0], 'velocity': [10, 0], 'gravity': 100, 'life': 2000, 'duration': 1000, 'turbulence': 0, 'seed': 12})
    frame = project_at(p, 500)
    assert frame.layer('sparks/0')['x'] == 35
    assert frame.layer('sparks/0')['y'] == 32.5
    assert np.array_equal(np.asarray(render_at(p, 500)), np.asarray(render_at(p, 500)))
    assert not project_at(p, 1000).layer('sparks/0')['visible']


def test_paper_held_cadence_has_grain_and_preserves_document():
    p = ball()
    p.apply([{'type': 'motion', 'target': 'ball', 'recipe': 'hover', 'duration': 1000}, {'type': 'cut-paper', 'target': 'ball', 'fps': 10, 'jitter': 0, 'grain': .1}])
    a, b, c = [np.asarray(render_at(p, time)) for time in (110, 190, 210)]
    assert np.array_equal(a, b)
    assert not np.array_equal(a, c)
    assert p.layer('ball')['y'] == 120
    from vixl.scene import paper_image
    from PIL import Image
    textured = np.asarray(paper_image(Image.new('RGBA', (40, 40), '#b69970'), p.layer('ball')))
    assert textured[5:-5, 5:-5, 0].std() > 10


def test_lighting_changes_rgb_preserving_alpha():
    p = ball()
    before = np.asarray(p.render())
    p.apply({'type': 'lighting', 'ambient': .6, 'lights': [{'x': 10, 'y': 10, 'radius': 20, 'intensity': .4, 'color': '#ffdd99'}], 'vignette': .5})
    after = np.asarray(p.render())
    assert not np.array_equal(before[:, :, :3], after[:, :, :3])
    assert np.array_equal(before[:, :, 3], after[:, :, 3])


@pytest.mark.parametrize('style', ['speech', 'thought', 'shout', 'whisper'])
def test_bubble_tail_follows_anchor(style):
    from vixl.captions import prepare_bubbles
    p = ball()
    p.apply({'type': 'speech-bubble', 'name': 'bubble', 'text': 'Hello!', 'anchor': 'ball', 'style': style, 'x': 10, 'y': 10, 'size': 16, 'max_width': 100})
    before = prepare_bubbles(p).layer('bubble/tail')['path']
    p.apply({'type': 'move', 'target': 'ball', 'x': 190})
    after = prepare_bubbles(p).layer('bubble/tail')['path']
    assert before != after
    assert p.layer('bubble/body')['width'] < 100
    p.render()


def test_styled_caption_typing_and_overflow_review():
    from vixl.captions import findings
    p = Project(300, 200)
    p.apply({'type': 'caption', 'name': 'subtitle', 'text': 'A typed caption', 'x': 15, 'y': 175, 'size': 25, 'max_width': 220, 'style': {'bold': True, 'italic': True}, 'box': True, 'start': 100, 'end': 1100, 'animation': 'typewriter'})
    assert project_at(p, 100).layer('subtitle/text')['text'] == ''
    assert 0 < len(project_at(p, 500).layer('subtitle/text')['text']) < len('A typed caption')
    assert not project_at(p, 1200).layer('subtitle')['visible']
    assert findings(p)[0]['code'] == 'text-overflow'
    render_at(p, 500)


def test_audio_synthesis_frequency_fades_and_seed():
    from vixl.audio import synthesize, mix_tracks, wav_bytes, read_audio, DEFAULT_RATE as RATE
    tone = synthesize({'synth': {'instrument': 'sine', 'frequency': 440}, 'duration': 1000})
    spectrum = np.abs(np.fft.rfft(tone[:, 0]))
    assert np.argmax(spectrum) == 440
    mixed = mix_tracks([{'synth': 'sine', 'duration': 500, 'start': 250, 'volume': .5, 'fade_in': 100, 'fade_out': 100, 'pan': 1}], 1000)
    assert not mixed[:int(RATE * .25)].any()
    assert not mixed[:, 0].any()
    assert np.max(np.abs(mixed)) <= .36
    raw = wav_bytes(mixed)
    with wave.open(io.BytesIO(raw)) as w:
        assert w.getnframes() == RATE
    decoded = read_audio(raw)
    assert decoded.shape == mixed.shape
    assert np.max(np.abs(decoded - mixed)) < 1e-4
    a = synthesize({'synth': 'splash', 'duration': 200, 'seed': 7})
    b = synthesize({'synth': 'splash', 'duration': 200, 'seed': 7})
    assert np.array_equal(a, b)


def test_audio_marker_sync_import_and_roundtrip(tmp_path):
    from vixl.audio import wav_bytes, synthesize, export_audio
    source = tmp_path / 'tone.wav'
    source.write_bytes(wav_bytes(synthesize({'synth': 'bell', 'duration': 200})))
    p = ball()
    p._workspace = tmp_path
    p.apply([{'type': 'marker', 'name': 'impact', 'time': 500}, {'type': 'audio-track', 'name': 'bell', 'source': 'tone.wav', 'start': 'impact', 'fade_out': 50}])
    assert p.state['audio_tracks'][0]['start'] == 500
    assert p.state['audio_tracks'][0]['asset'] in p.assets
    p.save(tmp_path / 'sound.vixl')
    loaded = Project.load(tmp_path / 'sound.vixl')
    export_audio(loaded, tmp_path / 'mix.wav')
    with wave.open(str(tmp_path / 'mix.wav')) as w:
        assert w.getnframes() / w.getframerate() == 3
    with pytest.raises(VixlError):
        p.apply({'type': 'audio-track', 'name': 'escape', 'source': '../escape.wav'})


def test_film_styled_caption_and_synth_score(tmp_path):
    from vixl.film import plan, frames
    from PIL import Image
    Image.new('RGB', (120, 80), '#203040').save(tmp_path / 'source.png')
    spec = {'width': 120, 'height': 80, 'fps': 10, 'shots': [{'source': 'source.png', 'duration': 500}], 'captions': [{'text': 'Hi', 'start': 0, 'end': 500, 'x': 5, 'y': 10, 'size': 14, 'style': {'bold': True}, 'box': True, 'animation': 'fade'}], 'audio': [{'synth': 'pop', 'duration': 200, 'start': 100, 'fade_out': 50}]}
    assert plan(spec)['frames'] == 5
    images = list(frames(spec, tmp_path))
    assert len(images) == 5
    assert not np.array_equal(np.asarray(images[0]), np.asarray(images[2]))


@pytest.mark.skipif(not shutil.which('ffmpeg'), reason='ffmpeg is optional')
def test_timeline_video_includes_synthesized_audio(tmp_path):
    from vixl.timeline import export_timeline
    from vixl.film import audio_duration
    p = ball()
    p.apply([{'type': 'timeline-set', 'duration': 300, 'fps': 10}, {'type': 'audio-track', 'name': 'score', 'synth': 'piano', 'duration': 300}])
    output = tmp_path / 'sound.mp4'
    result = export_timeline(p, output)
    assert result['audio_tracks'] == 1
    assert abs(audio_duration(output) - 300) < 70


def test_cross_document_character_asset(tmp_path):
    from vixl.characters import export_character
    p = hero()
    export_character(p, 'hero', tmp_path / 'hero.vixl')
    other = Project(400, 400)
    other._workspace = tmp_path
    other.apply({'type': 'character-load', 'source': 'hero.vixl', 'name': 'visitor', 'scale': .8, 'x': 40})
    assert len(other.layer('visitor')['character']['parts']) >= 17
    assert other.layer('visitor')['x'] == 40
    assert other.render().size == (400, 400)


def test_cut_paper_clear_restores_shadow_and_retains_other_cadence():
    p = ball()
    p.apply([{'type': 'duplicate', 'target': 'ball', 'name': 'other'}, {'type': 'layer-style', 'target': 'ball', 'name': 'drop-shadow', 'settings': {'dx': 7, 'dy': 3, 'opacity': .6}}, {'type': 'cut-paper', 'targets': ['ball', 'other']}])
    p.apply({'type': 'cut-paper', 'target': 'ball', 'clear': True})
    assert p.layer('ball')['styles']['drop-shadow']['dx'] == 7
    assert 'stop_motion' in p.state
    p.apply({'type': 'cut-paper', 'target': 'other', 'clear': True})
    assert 'stop_motion' not in p.state
    assert 'drop-shadow' not in p.layer('other')['styles']


def test_subpixel_vector_scale_remains_visible():
    p = ball()
    p.apply({'type': 'shape', 'name': 'hairline', 'shape': 'rectangle', 'width': .25, 'height': 50, 'fill': 'white'})
    p.apply({'type': 'animate', 'target': 'hairline', 'property': 'scale', 'from': 1, 'to': .5, 'duration': 1000})
    assert project_at(p, 500).layer('hairline')['opacity'] == 1


def test_camera_focus_state_is_cache_stable():
    p = ball()
    p.apply({'type': 'camera', 'focus': 3, 'aperture': 2})
    assert project_at(p, 250).state == project_at(p, 250).state


def test_look_at_resolves_nested_target_coordinates():
    p = ball()
    p.apply([{'type': 'shape', 'shape': 'rectangle', 'name': 'eye', 'width': 10, 'height': 10, 'x': 0, 'y': 0, 'fill': 'white'}, {'type': 'group', 'name': 'face', 'targets': ['eye']}, {'type': 'move', 'target': 'face', 'x': 105, 'y': 15}])
    p.apply({'type': 'motion', 'target': 'ball', 'recipe': 'look-at', 'follow': 'eye', 'samples': 2, 'duration': 1000})
    assert project_at(p, 500).layer('ball')['rotation'] == pytest.approx(270)


def test_caption_overflow_checks_transformed_parent_canvas_space():
    from vixl.captions import findings
    p = Project(300, 200)
    p.apply([{'type': 'caption', 'name': 'subtitle', 'text': 'Inside initially', 'x': 10, 'y': 10, 'size': 16, 'max_width': 140}, {'type': 'group', 'name': 'wrapper', 'targets': ['subtitle']}, {'type': 'move', 'target': 'wrapper', 'x': 260, 'y': 30}])
    assert any(finding['code'] == 'text-overflow' for finding in findings(p))
