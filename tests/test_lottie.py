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
from vixl.timeline import export_timeline, render_at


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


def test_json_schema_and_sampled_easing(tmp_path):
    p = animated()
    before = json.dumps(p.state, sort_keys=True)
    data, report = data_for(p, tmp_path, strict=True)
    schema = json.loads((Path(__file__).parents[1] / 'src/vixl/data/lottie-export.schema.json').read_text())
    jsonschema.validate(data, schema)
    assert report['sampling'] == 'frame' and report['fallbacks'] == []
    assert report['frames'] == 10 and report['size'] == [160, 120]
    layer = next(layer for layer in data['layers'] if layer['nm'] == 'dot')
    assert layer['ty'] == 4 and layer['ks']['p']['a'] == 1
    for key in layer['ks']['p']['k']:
        assert key['s'][0] == pytest.approx(render_pose(p, key['t'] * 100)['x'])
    assert json.dumps(p.state, sort_keys=True) == before
    with pytest.raises(VixlError, match='already exists'):
        export_timeline(p, tmp_path / 'motion.json')


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
