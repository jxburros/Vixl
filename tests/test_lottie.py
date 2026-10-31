"""Lottie interchange: native geometry, sampled motion, explicit animated fallbacks and strict limits."""

import gzip
import json
from pathlib import Path
import zipfile

import jsonschema
import numpy as np
import pytest

from vixl import Project
from vixl.errors import VixlError
from vixl.plugins.lottie.lottie import curve_at, subcurve
from vixl.timeline import bezier_curve, easing_function, export_timeline, render_at


def animated(width=160, height=120):
    p = Project(width, height, 'white')
    p.apply([
        {'type': 'shape', 'shape': 'ellipse', 'name': 'dot', 'x': 10, 'y': 25, 'width': 35, 'height': 35,
         'fill': '#e04020'},
        {'type': 'timeline-set', 'duration': 1000, 'fps': 10, 'loop': 1},
        {'type': 'animate', 'target': 'dot', 'property': 'x', 'from': 10, 'to': 100,
         'duration': 1000, 'easing': 'ease-in-out'},
    ])
    return p


def data_for(p, tmp_path, **options):
    path = tmp_path / 'motion.json'
    report = export_timeline(p, path, overwrite=True, **options)
    return json.loads(path.read_text()), report


def test_json_schema_and_native_easing(tmp_path):
    p = animated()
    before = json.dumps(p.state, sort_keys=True)
    data, report = data_for(p, tmp_path, strict=True)
    schema = json.loads((Path(__file__).parents[1] / 'src/vixl/data/lottie-export.schema.json').read_text())
    jsonschema.validate(data, schema)
    assert report['sampling'] == 'frame' and report['fallbacks'] == []
    assert report['frames'] == 10 and report['size'] == [160, 120]
    assert report['motion'] == {'eased': 1, 'baked': 0, 'instances': 0} and report['warnings'] == []
    layer = next(layer for layer in data['layers'] if layer['nm'] == 'dot')
    assert layer['ty'] == 4 and layer['ks']['a']['k'][:2] == [17.5, 17.5]
    first, last = layer['ks']['p']['k']
    # The export ends at 900 ms, so its one key is the source ease-in-out cut to 0-90 % of its span.
    expected = subcurve(bezier_curve('ease-in-out'), 0, 0.9)
    assert [*first['o']['x'], *first['o']['y'], *first['i']['x'], *first['i']['y']] == pytest.approx(expected, abs=1e-6)
    assert first['t'] == 0 and last == {'t': 9, 's': pytest.approx([render_pose(p, 900)['x'] + 17.5, 42.5, 0]), 'h': 1}
    for frame in range(10):
        eased = curve_at(expected, frame / 9)
        x = first['s'][0] + (last['s'][0] - first['s'][0]) * eased
        assert x == pytest.approx(render_pose(p, frame * 100)['x'] + 17.5, abs=1e-3)
    assert json.dumps(p.state, sort_keys=True) == before
    with pytest.raises(VixlError, match='already exists'):
        export_timeline(p, tmp_path / 'motion.json')


def test_curves_are_cut_at_other_tracks_keys_and_non_bezier_spans_stay_per_frame(tmp_path):
    p = animated()
    p.apply([{'type': 'animate', 'target': 'dot', 'property': 'rotation', 'from': 0, 'to': 270, 'duration': 600,
              'easing': 'ease-out-back'},
             {'type': 'animate', 'target': 'dot', 'property': 'opacity', 'from': 1, 'to': 0.2, 'start': 300,
              'duration': 500, 'easing': 'bounce-out'}])
    data, report = data_for(p, tmp_path)
    layer = next(layer for layer in data['layers'] if layer['nm'] == 'dot')
    rotation = layer['ks']['r']['k']
    # The opacity key at 300 ms splits the rotation's one source segment in two eased spans.
    assert [key['t'] for key in rotation] == [0, 3, 6] and 'o' in rotation[0] and 'o' in rotation[1]
    assert rotation[-1]['s'] == [270.0]
    opacity = layer['ks']['o']['k']
    assert all(key.get('h') == 1 for key in opacity) and len(opacity) >= 5
    assert report['motion']['baked'] >= 1 and 'per-frame keys' in report['warnings'][0]
    jsonschema.validate(data, json.loads((Path(__file__).parents[1] / 'src/vixl/data/lottie-export.schema.json').read_text()))


def test_keyframes_between_frames_are_sampled_so_their_curves_survive(tmp_path):
    p = animated()
    p.apply({'type': 'animate', 'target': 'dot', 'property': 'opacity', 'from': 1, 'to': 0.3, 'start': 150,
             'duration': 500, 'easing': 'ease-out'})
    data, report = data_for(p, tmp_path, strict=True)
    opacity = next(layer for layer in data['layers'] if layer['nm'] == 'dot')['ks']['o']['k']
    # Keys at 150 and 650 ms fall between the 10 fps frames, so they get their own fractional key times.
    assert [key['t'] for key in opacity] == [0, 1.5, 6.5] and 'o' in opacity[1]
    # The opacity fade, and the x motion cut in three by the fade's keys.
    assert report['motion'] == {'eased': 4, 'baked': 0, 'instances': 0}
    assert data['op'] == 10 and report['frames'] == 10


def test_position_splits_when_axes_follow_different_curves(tmp_path):
    p = animated()
    p.apply({'type': 'animate', 'target': 'dot', 'property': 'y', 'from': 10, 'to': 70, 'duration': 1000,
             'easing': 'linear'})
    data, report = data_for(p, tmp_path, strict=True)
    position = next(layer for layer in data['layers'] if layer['nm'] == 'dot')['ks']['p']
    assert position['s'] is True and report['motion']['baked'] == 0
    assert position['x']['k'][0]['o']['x'] != position['y']['k'][0]['o']['x']
    assert position['y']['k'][0]['o'] == {'x': [0.0], 'y': [0.0]}


def test_subcurve_reproduces_the_source_easing_inside_its_span():
    for name in ('ease', 'ease-in-out-back', 'cubic-bezier(0.2, 0.9, 0.1, 1.4)'):
        curve = bezier_curve(name)
        ease = easing_function(name)
        for start, end in ((0, 1), (0.25, 0.75), (0, 0.4), (0.6, 1)):
            part = subcurve(curve, start, end)
            low, high = ease(start), ease(end)
            for x in np.linspace(0, 1, 11):
                assert low + (high - low) * curve_at(part, x) == pytest.approx(ease(start + (end - start) * x), abs=1e-6)
    assert subcurve(bezier_curve('linear'), 0.3, 0.3) is None


def render_pose(p, time):
    from vixl.timeline import project_at
    return project_at(p, time).layer('dot')


def test_containers_are_self_contained_and_deterministic(tmp_path):
    p = animated(512, 512)
    for suffix in ('lottie', 'tgs'):
        first, second = tmp_path / f'one.{suffix}', tmp_path / f'two.{suffix}'
        export_timeline(p, first)
        export_timeline(p, second)
        assert first.read_bytes() == second.read_bytes()
        if suffix == 'lottie':
            with zipfile.ZipFile(first) as archive:
                manifest = json.loads(archive.read('manifest.json'))
                assert manifest['animations'] == [{'id': 'animation'}]
                data = json.loads(archive.read('animations/animation.json'))
        else:
            data = json.loads(gzip.decompress(first.read_bytes()))
        assert data['w'] == 512 and data['fr'] == 10


def test_tgs_refuses_size_duration_and_rasterization_before_writing(tmp_path):
    path = tmp_path / 'invalid.tgs'
    with pytest.raises(VixlError, match='512'):
        export_timeline(animated(), path)
    p = animated(512, 512)
    p.apply({'type': 'timeline-set', 'duration': 3100})
    with pytest.raises(VixlError, match='3 seconds'):
        export_timeline(p, path)
    p.apply({'type': 'timeline-set', 'duration': 3000})
    with pytest.raises(VixlError, match='quantization'):
        export_timeline(p, path, fps=12.1)
    p.apply([{'type': 'timeline-set', 'duration': 1000}, {'type': 'blur', 'target': 'dot', 'value': 3}])
    with pytest.raises(VixlError, match='strict'):
        export_timeline(p, path)
    assert not path.exists()


def test_raster_fallback_is_animated_and_strict_refuses_it(tmp_path):
    p = animated()
    p.apply({'type': 'blur', 'target': 'dot', 'value': 4})
    data, report = data_for(p, tmp_path)
    assert report['fallbacks'] == [{'layer': 'dot', 'reason': 'layer effects', 'animated': True}]
    images = [asset for asset in data['assets'] if 'p' in asset]
    assert len(images) > 1
    layers = [layer for layer in data['layers'] if layer['ty'] == 2]
    assert len(layers) == 10 and layers[-1]['ip'] == 9
    assert layers[5]['ks']['o']['k'][-1] == {'t': 6, 's': [0], 'h': 1}
    with pytest.raises(VixlError, match='layer effects'):
        export_timeline(p, tmp_path / 'strict.json', strict=True)
    assert not (tmp_path / 'strict.json').exists()


def test_outlined_text_and_group_precomp(tmp_path):
    p = animated()
    p.apply([
        {'type': 'text', 'name': 'title', 'text': 'Hello', 'size': 20, 'x': 30, 'y': 70, 'color': '#104090'},
        {'type': 'group', 'name': 'card', 'targets': ['dot', 'title']},
        {'type': 'animate', 'target': 'card', 'property': 'opacity', 'from': 0.2, 'to': 1, 'duration': 1000},
    ])
    data, report = data_for(p, tmp_path, strict=True)
    assert not report['fallbacks']
    comp = next(asset for asset in data['assets'] if 'layers' in asset)
    text = next(layer for layer in comp['layers'] if layer['nm'] == 'title')
    assert text['ty'] == 4 and text['shapes']
    assert any(layer['ty'] == 0 for layer in data['layers'])


def test_open_path_remains_unfilled(tmp_path):
    p = Project(128, 96, 'white')
    p.apply({'type': 'shape', 'shape': 'path', 'name': 'line', 'path': 'M0 0 L80 0 L40 60',
             'width': 80, 'height': 60, 'x': 10, 'y': 10, 'stroke': 'blue', 'stroke_width': 4})
    data, report = data_for(p, tmp_path, fps=1, strict=True)
    line = next(layer for layer in data['layers'] if layer['nm'] == 'line')
    assert not report['fallbacks']
    assert not any(item['ty'] == 'fl' for group in line['shapes'] for item in group['it'])


def test_shear_and_clipped_glyphs_report_losses(tmp_path):
    p = animated()
    p.apply({'type': 'skew', 'target': 'dot', 'x': 25, 'y': 10})
    _, report = data_for(p, tmp_path)
    assert any('affine shear' in fallback['reason'] for fallback in report['fallbacks'])
    with pytest.raises(VixlError, match='affine shear'):
        export_timeline(p, tmp_path / 'strict.json', strict=True)


def test_unsupported_options_and_audio_do_not_silently_disappear(tmp_path):
    for options in ({'preset': 'draft'}, {'poster': 'end'}, {'quality': 20}, {'target_bytes': 1024}):
        with pytest.raises(VixlError):
            export_timeline(animated(), tmp_path / 'out.json', **options)


def test_canvas_swatches_are_resolved(tmp_path):
    p = animated()
    p.apply([{'type': 'swatch', 'name': 'paper', 'color': '#ffff00'},
             {'type': 'canvas', 'background': '@paper'}])
    data, _ = data_for(p, tmp_path)
    background = next(layer for layer in data['layers'] if layer['nm'] == 'Canvas background')
    assert background['shapes'][-1]['c'] == {'a': 0, 'k': [1, 1, 0]}


def test_sample_budget_respects_document_limits(tmp_path):
    from dataclasses import replace

    p = animated()
    p.limits = replace(p.limits, max_project_bytes=4000)
    with pytest.raises(VixlError, match='budget'):
        export_timeline(p, tmp_path / 'out.json')
    assert not (tmp_path / 'out.json').exists()


def test_raster_budget_is_checked_before_retaining_images(tmp_path, monkeypatch):
    from vixl.plugins.lottie import lottie

    p = animated()
    p.apply({'type': 'blur', 'target': 'dot', 'value': 3})
    monkeypatch.setattr(lottie, 'MAX_RASTER_BYTES', 100)
    with pytest.raises(VixlError, match='raster assets'):
        export_timeline(p, tmp_path / 'out.json')
    assert not (tmp_path / 'out.json').exists()


def test_cancelled_export_has_no_partial_file(tmp_path):
    with pytest.raises(VixlError, match='cancelled'):
        export_timeline(animated(), tmp_path / 'out.json', cancelled=lambda: True)
    assert not (tmp_path / 'out.json').exists()


def test_cancellation_after_sampling_still_prevents_output(tmp_path):
    done = []
    with pytest.raises(VixlError, match='cancelled'):
        export_timeline(animated(), tmp_path / 'out.json', progress=done.append,
                        cancelled=lambda: bool(done and done[-1]['done'] == done[-1]['total']))
    assert not (tmp_path / 'out.json').exists()


def test_cli_and_rest_export_interchange(tmp_path, capsys):
    from fastapi.testclient import TestClient
    from vixl.cli import main
    from vixl.interfaces import create_app

    project = animated()
    path = tmp_path / 'motion.vixl'
    project.save(path)
    assert main(['-p', str(path), 'export-timeline', '--out', str(tmp_path / 'motion.lottie'), '--strict']) == 0
    assert json.loads(capsys.readouterr().out)['fallbacks'] == []
    with TestClient(create_app(path)) as client:
        response = client.post('/timeline/export', json={'format': 'json', 'strict': True})
        assert response.status_code == 200, response.text
        assert response.headers['content-type'] == 'application/json'
        assert response.json()['op'] == 10
        response = client.post('/timeline/export', json={'format': 'lottie'})
        assert response.status_code == 200 and response.content.startswith(b'PK')


def test_mcp_infers_dotlottie_and_accepts_json_strict(tmp_path):
    import asyncio
    from mcp.shared.memory import create_connected_server_and_client_session
    from vixl.interfaces import mcp_server

    animated().save(tmp_path / 'motion.vixl')

    async def run():
        server = mcp_server(workspace=tmp_path)
        async with create_connected_server_and_client_session(server._mcp_server) as client:
            for name, kind in [('motion.lottie', None), ('motion.json', 'timeline')]:
                args = {'path': name, 'document': 'motion.vixl', 'strict': True}
                if kind:
                    args['kind'] = kind
                result = await client.call_tool('vixl_export', args)
                assert not result.isError, result.content[0].text
                assert json.loads(result.content[0].text)['fallbacks'] == []
                assert (tmp_path / name).exists()

    asyncio.run(run())


@pytest.mark.parametrize('case', ['motion', 'text', 'stroke', 'gradient', 'group', 'raster', 'shear'])
def test_optional_reference_player_at_five_frames(tmp_path, case):
    rlottie = pytest.importorskip('rlottie_python')
    p = animated()
    if case == 'text':
        p.apply({'type': 'text', 'name': 'title', 'text': 'Hello Vixl', 'x': 15, 'y': 75, 'size': 22, 'color': '#c0a020'})
    elif case == 'stroke':
        p.apply({'type': 'shape', 'shape': 'rectangle', 'name': 'outline', 'x': 40, 'y': 40,
                 'width': 60, 'height': 30, 'fill': 'red', 'stroke': 'blue', 'stroke_width': 8})
    elif case == 'gradient':
        p.apply({'type': 'gradient', 'name': 'wash', 'width': 80, 'height': 50, 'x': 40, 'y': 55,
                 'start': '#ff0033', 'end': '#3355ff', 'direction': 'angled', 'angle': 37})
    elif case == 'group':
        p.apply([{'type': 'shape', 'shape': 'rectangle', 'name': 'box', 'x': 25, 'y': 30,
                  'width': 40, 'height': 30, 'fill': 'blue'},
                 {'type': 'group', 'name': 'pair', 'targets': ['dot', 'box']},
                 {'type': 'animate', 'target': 'pair', 'property': 'opacity', 'from': 0.2, 'to': 1, 'duration': 1000},
                 {'type': 'animate', 'target': 'pair', 'property': 'rotation', 'from': 0, 'to': 35, 'duration': 1000}])
    elif case == 'raster':
        p.apply([{'type': 'blur', 'target': 'dot', 'value': 3},
                 {'type': 'animate', 'target': 'dot', 'property': 'opacity', 'from': 0.2, 'to': 1, 'duration': 1000}])
    elif case == 'shear':
        p.apply({'type': 'skew', 'target': 'dot', 'x': 25, 'y': 10})
    data, report = data_for(p, tmp_path)
    animation = rlottie.LottieAnimation.from_data(json.dumps(data))
    for index in (0, 2, 5, 7, 9):
        expected = np.asarray(render_at(p, index * 100)).astype(int)
        actual = np.asarray(animation.render_pillow_frame(index)).astype(int)
        diff = np.abs(actual - expected)
        assert diff.mean() < 2, (case, index, diff.mean(), report['fallbacks'])
        assert (diff.max(axis=2) > 32).mean() < 0.015, (case, index, report['fallbacks'])


def linked(tmp_path):
    child = Project(80, 40, 'white')
    child.apply([
        {'type': 'shape', 'name': 'dot', 'shape': 'rectangle', 'width': 10, 'height': 10, 'fill': 'red', 'x': 0, 'y': 10},
        {'type': 'timeline-set', 'duration': 1000, 'fps': 20, 'loop': 1},
        {'type': 'animate', 'target': 'dot', 'property': 'x', 'from': 0, 'to': 60, 'duration': 1000,
         'easing': 'ease-in-out'},
    ])
    child.save(tmp_path / 'child.vixl')
    parent = Project(160, 120, '#eeeeee')
    parent.save(tmp_path / 'host.vixl')
    parent.apply([
        {'type': 'timeline-set', 'duration': 2000, 'fps': 10},
        {'type': 'link', 'source': 'child.vixl', 'name': 'first', 'time': {'offset': 0}},
        {'type': 'animation-instance', 'source': 'child.vixl', 'name': 'second', 'x': 80,
         'time': {'offset': 300, 'speed': 2, 'loop': 'pingpong'}},
        {'type': 'link', 'source': 'child.vixl', 'name': 'third', 'y': 50, 'width': 60, 'height': 30, 'fit': 'fit',
         'time': {'offset': 500, 'before': 'hidden', 'after': 'hidden'}},
        {'type': 'link', 'source': 'child.vixl', 'name': 'fourth', 'x': 90, 'y': 60, 'width': 40, 'height': 40,
         'crop': {'x': 20, 'y': 0, 'width': 40, 'height': 40},
         'time': {'loop': 'loop', 'trim_start': 200, 'trim_end': 700}},
    ])
    parent.save()
    return parent


def test_links_export_as_time_remapped_precompositions(tmp_path):
    parent = linked(tmp_path)
    data, report = data_for(parent, tmp_path, strict=True)
    jsonschema.validate(data, json.loads((Path(__file__).parents[1] / 'src/vixl/data/lottie-export.schema.json').read_text()))
    assert report['fallbacks'] == [] and report['motion']['instances'] == 4 and report['motion']['baked'] == 0
    layers = {layer['nm']: layer for layer in data['layers']}
    first, second, third, fourth = (layers[name] for name in ('first', 'second', 'third', 'fourth'))
    assert all(layer['ty'] == 0 and 'tm' in layer for layer in (first, second, third, fourth))
    # The remap points at whole frames of the source composition (one per source time shown) in straight runs;
    # ping-pong at double speed turns at every fifth source frame.
    assert first['tm']['k'][0]['o'] == {'x': [0.0], 'y': [0.0]} and first['tm']['k'][-1]['s'] == pytest.approx([1.0])
    source = next(asset for asset in data['assets'] if asset['id'] == first['refId'])
    dot = next(layer for layer in source['layers'] if layer['nm'] == 'dot')
    assert dot['ks']['p']['k'][0].get('o') and dot['ks']['p']['k'][-1]['t'] == 10
    assert (third['ip'], third['op']) == (5, 16) and 'ip' not in second or second['ip'] == 0
    assert fourth['hasMask'] and fourth['masksProperties'][0]['pt']['k']['v'][0] == [20, 0]
    assert [key['s'][0] for key in second['tm']['k']] == pytest.approx([0, 0, 0.5, 0, 0.5, 0.4])


def test_link_placement_animation_and_corner_pins_fall_back_with_reasons(tmp_path):
    parent = linked(tmp_path)
    ident = parent.state['layers'][0]['id']
    parent.apply({'type': 'animate', 'target': ident, 'property': 'width', 'from': 80, 'to': 40, 'duration': 500})
    _, report = data_for(parent, tmp_path)
    assert {'layer': 'first', 'reason': 'animated link placement', 'animated': True} in report['fallbacks']
    with pytest.raises(VixlError, match='animated link placement'):
        export_timeline(parent, tmp_path / 'strict.json', strict=True)


def test_nested_links_share_parent_time_and_cycles_are_refused(tmp_path):
    linked(tmp_path)
    wrapper = Project(80, 40, 'transparent')
    wrapper.save(tmp_path / 'wrapper.vixl')
    wrapper.apply({'type': 'link', 'source': 'child.vixl', 'time': {'speed': 0.5}})
    wrapper.save()
    still = Project(80, 40, 'transparent')
    still.save(tmp_path / 'still.vixl')
    still.apply({'type': 'link', 'source': 'wrapper.vixl'})
    still.save()
    parent = Project(80, 80, 'white')
    parent.save(tmp_path / 'outer.vixl')
    parent.apply([{'type': 'timeline-set', 'duration': 1000, 'fps': 10},
                  {'type': 'link', 'source': 'still.vixl'},
                  {'type': 'link', 'source': 'wrapper.vixl', 'y': 40, 'time': {'offset': 200}}])
    data, report = data_for(parent, tmp_path, strict=True)
    assert report['fallbacks'] == [] and report['motion']['instances'] == 4
    for frame in (0, 3, 7):
        expected = np.asarray(render_at(parent, frame * 100)).astype(int)
        _assert_player_matches(data, frame, expected)
    loop = Project(40, 40)
    loop.save(tmp_path / 'a.vixl')
    other = Project(40, 40)
    other.save(tmp_path / 'b.vixl')
    loop.apply({'type': 'link', 'source': 'b.vixl'})
    loop.save()
    with pytest.raises(VixlError, match='cycle'):
        other.apply({'type': 'link', 'source': 'a.vixl'})
        other.save()
        export_timeline(loop, tmp_path / 'cycle.json')
    assert not (tmp_path / 'cycle.json').exists()


def _assert_player_matches(data, frame, expected, case=None):
    rlottie = pytest.importorskip('rlottie_python')
    animation = rlottie.LottieAnimation.from_data(json.dumps(data))
    actual = np.asarray(animation.render_pillow_frame(frame)).astype(int)
    diff = np.abs(actual - expected)
    assert diff.mean() < 1, (case, frame, diff.mean())
    assert (diff.max(axis=2) > 32).mean() < 0.005, (case, frame)


@pytest.mark.parametrize('frame', [0, 3, 6, 9, 12, 15, 18])
def test_optional_reference_player_plays_linked_instances(tmp_path, frame):
    parent = linked(tmp_path)
    data, _ = data_for(parent, tmp_path)
    _assert_player_matches(data, frame, np.asarray(render_at(parent, frame * 100)).astype(int))
