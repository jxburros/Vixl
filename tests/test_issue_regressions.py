"""Regression cases from the 0.23 authoring field reports."""
import json

import pytest
from PIL import Image

from vixl import Project
from vixl.cli import main, read_json


def test_schema_filters_operations(capsys):
    assert main(['--json', 'schema', 'text', 'shape']) == 0
    result = json.loads(capsys.readouterr().out)
    assert set(result) == {'text', 'shape'}
    assert result['text']['properties']['type']['const'] == 'text'


def test_json_inline_and_large_atomic_input(tmp_path):
    payload = {'operations': [{'type': 'text', 'text': 'x' * 1100000}]}
    path = tmp_path / 'batch.json'
    path.write_text(json.dumps(payload))
    assert read_json(path) == payload
    assert read_json('{"kind":"suites"}') == {'kind': 'suites'}


@pytest.mark.parametrize('effect', ['halftone', 'crosshatch', 'pixelate'])
def test_cell_effect_preview_matches_export(effect):
    from vixl.proxy import render_preview
    p = Project(240, 240, 'white')
    p.apply([{'type':'gradient', 'name':'g', 'start':'#333333','end':'#eeeeee'},
             {'type':'effect','name':effect,'amount':16}])
    actual = render_preview(p, 80, 80)
    expected = p.render().resize(actual.size, Image.Resampling.LANCZOS)
    assert actual.tobytes() == expected.tobytes()


def test_gif_warning_with_identical_frames(tmp_path):
    from vixl.timeline import export_timeline
    p = Project(64, 64, 'white')
    p.apply([{'type':'shape','shape':'ellipse','name':'dot','width':20,'height':20,'fill':'red'},
             {'type':'timeline-set','duration':1000,'fps':10}])
    result = export_timeline(p, tmp_path/'a.gif', max_bytes=1)
    assert result['frames'] < result['rendered_frames']
    assert result['warnings']


def test_width_only_box_grows_after_text_set():
    p = Project(400, 400, 'white')
    p.apply([{'type':'text','name':'t','text':'Short','size':24,'color':'black'},
             {'type':'text-layout','width':100}])
    old = p.layer('t')['height']
    p.apply({'type':'text-set','text':'A much longer sentence that needs several wrapped lines.'})
    assert p.layer('t')['height'] > old * 2
    assert not [x for x in p.check(checks=['bounds'])['issues'] if x.get('action') == 'fix']


def test_compaction_keeps_automatic_rich_variants():
    from vixl.compaction import _current_references
    fonts = {'family-400':'fonts/a.ttf','family-700':'fonts/b.ttf','family-400-italic':'fonts/c.ttf',
             'unrelated-400':'fonts/d.ttf'}
    used, names = _current_references({'fonts': fonts, 'layers':[{'font':'family-400','rich':{'spans':[{'text':'bold','bold':True}]}}]})
    assert names == {'family-400','family-700','family-400-italic'}
    assert 'fonts/b.ttf' in used


def test_shape_stroke_color_animation_alias():
    from vixl.timeline import project_at
    p = Project(100, 100)
    p.apply([{'type':'shape','shape':'rectangle','name':'s','width':40,'height':40,'stroke':'red','stroke_width':4},
             {'type':'animate','property':'stroke_color','to':'blue','duration':1000}])
    assert project_at(p, 1000).layer('s')['stroke'] in ('blue', '#0000ffff', '#0000ff')


def test_hidden_trailing_page_number_is_bounded():
    from vixl.pages import numbering
    pages = [{'id':'1'}, {'id':'2','hidden':True}]
    assert numbering({'pages':pages}, pages[-1]) == (1, 1)


def test_all_pages_python_export(tmp_path):
    p = Project(300, 200, 'white')
    p.apply([{'type':'page','action':'add','name':'first'}, {'type':'page','action':'add','name':'second'}])
    p.export(tmp_path/'sheet.png', pages='all')
    assert (tmp_path/'sheet.png').is_file()


def test_template_accepts_rolled_glow():
    from vixl.container_library import finish_template
    p = Project(100, 100)
    finish_template(p, 'glow', set())


def test_grouping_preserves_child_stroke():
    p = Project(300, 300)
    p.apply({'type':'shape','shape':'rectangle','name':'s','x':60,'y':60,'width':100,'height':100,
             'fill':'transparent','stroke':'black','stroke_width':20})
    before = p.render()
    p.apply({'type':'group','name':'g','targets':['s']})
    assert p.render().tobytes() == before.tobytes()


def test_scale_preserves_explicit_pivot():
    p = Project(400, 400)
    p.apply([{'type':'shape','shape':'rectangle','name':'s','x':100,'y':100,'width':200,'height':200},
             {'type':'pivot','value':'center'}, {'type':'scale','value':0.5}])
    s = p.layer('s')
    assert s['x'] + s['width']/2 == 200
    assert s['y'] + s['height']/2 == 200


def test_poster_check_sees_content_between_blank_endpoints():
    from vixl.timeline import poster_findings
    p = Project(100, 100)
    p.apply([{'type':'shape','shape':'ellipse','name':'dot','width':20,'height':20,'fill':'red'},
             {'type':'timeline-set','duration':1000},
             {'type':'keyframe','property':'opacity','time':0,'value':0},
             {'type':'keyframe','property':'opacity','time':500,'value':1},
             {'type':'keyframe','property':'opacity','time':1000,'value':0}])
    assert any(item[0] == 'empty-poster' for item in poster_findings(p))


def test_path_integer_and_float_frames_paint_the_same_overflow():
    images = []
    for size in (150, 150.0):
        p = Project(500, 500, 'white')
        p.apply({'type': 'shape', 'shape': 'path', 'path': 'M0 0 L300 0 L300 300 Z',
                 'width': size, 'height': size, 'x': 40, 'y': 40, 'fill': 'red'})
        images.append(p.render())
    assert images[0].tobytes() == images[1].tobytes()
    assert images[0].getpixel((300, 100))[:3] == (255, 0, 0)


def test_radial_center_roundtrip_and_svg(tmp_path):
    p = Project(101, 101, 'white')
    p.apply({'type': 'gradient', 'name': 'spot', 'direction': 'radial', 'center': [0.2, 0.3],
             'start': 'red', 'end': 'blue'})
    assert p.render().getpixel((20, 30))[:3] == (255, 0, 0)
    p.save(tmp_path / 'radial.vixl')
    assert Project.load(tmp_path / 'radial.vixl').layer('spot')['center'] == [0.2, 0.3]
    p.export(tmp_path / 'radial.svg')
    import re
    transform = re.search(r'gradientTransform="translate\(([^)]+)\)', (tmp_path / 'radial.svg').read_text())[1]
    assert [float(x) for x in transform.split()] == pytest.approx([20.2, 30.3])


def test_pen_target_keeps_identity_and_placement():
    p = Project(200, 200, 'white')
    p.apply({'type': 'pen', 'name': 'line', 'points': [[10, 10], [70, 10]], 'smooth': False})
    ident = p.layer('line')['id']
    p.apply({'type': 'pen', 'target': 'line', 'points': [[10, 10], [70, 50]], 'smooth': False})
    assert len(p.state['layers']) == 1 and p.layer('line')['id'] == ident
    assert p.render().getpixel((70, 49))[:3] != (255, 255, 255)


def test_gif_shared_palette_preserves_single_pixel_accents():
    import io
    from vixl.animation import gif_bytes
    frame = Image.new('RGBA', (800, 800), '#888888')
    frame.putpixel((1, 1), (255, 40, 10, 255))
    encoded = gif_bytes([frame], [100], 0, colors=256, dither='ordered')
    with Image.open(io.BytesIO(encoded)) as decoded:
        assert decoded.convert('RGB').getpixel((1, 1)) == (255, 40, 10)


def test_layout_emits_columns_and_baseline_guides():
    p = Project(800, 800, 'white')
    p.apply({'type': 'layout-apply', 'name': 'hero-statement', 'title': 'Hello', 'unfilled': 'omit', 'seed': 4})
    grids = {g.get('grid') for g in p.state['guides'].values()}
    assert {'layout-columns', 'layout-baseline'} <= grids


def test_production_checks_clipping_without_suites(tmp_path):
    from vixl.production import run
    p = Project(100, 100, 'white')
    p.apply({'type': 'text', 'text': 'Do not publish clipped text', 'x': 90, 'y': 10, 'size': 30})
    report = run(p, {'rows': [{}]}, tmp_path)
    assert report['status'] == 'needs_review'
    assert not list(tmp_path.glob('*.png'))


def test_production_reuse_skips_checks_and_detects_output_tampering(tmp_path, monkeypatch):
    from vixl.production import run
    p = Project(100, 100, 'white')
    p.apply({'type': 'shape', 'shape': 'rectangle', 'width': 20, 'height': 20, 'x': 20, 'y': 20})
    spec = {'rows': [{}]}
    first = run(p, spec, tmp_path)
    assert first['status'] == 'completed'
    def forbidden(*args, **kwargs):
        raise AssertionError('checks should not repeat for identical verified output')
    monkeypatch.setattr(Project, 'check', forbidden)
    second = run(p, spec, tmp_path)
    assert second['results'][0]['status'] == 'reused'
    (tmp_path / second['results'][0]['output']).write_bytes(b'changed')
    assert run(p, spec, tmp_path)['status'] == 'needs_review'


def test_small_explicit_chart_range_has_multiple_ticks():
    from vixl.charts import nice_scale
    assert len(nice_scale(0, 0.01, 2, fixed_max=0.01)[3]) >= 2


def test_pattern_ghost_outside_is_intentional():
    p = Project(100, 100, 'white')
    p.apply([{'type': 'shape', 'name': 'ghost', 'shape': 'ellipse', 'width': 10, 'height': 10, 'x': 130},
             {'type': 'group', 'name': 'tile', 'targets': ['ghost']}])
    p.layer('tile')['pattern_scatter'] = {'seed': 1}
    issues = p.check(checks=['bounds'])['issues']
    assert any(i['layers'] == ['ghost'] and i['action'] == 'informational' for i in issues)


def test_body_measure_is_review_not_a_false_pass_or_error():
    from vixl.craft import body_size
    p = Project(2400, 600, 'white')
    p.apply({'type': 'text', 'name': 'body', 'text': 'i' * 120, 'size': body_size(p)})
    report = p.check(checks=['legibility'], thumbnail_width=None)
    assert any(i.get('code') == 'measure' and i['action'] == 'review' for i in report['issues'])
    assert report['passed']


def test_endpoint_line_has_a_tight_box():
    p = Project(2000, 2000, 'white')
    p.apply({'type': 'shape', 'shape': 'line', 'name': 'rule', 'from': [400, 500], 'to': [650, 500],
             'stroke': 'black', 'stroke_width': 4})
    layer = p.layer('rule')
    assert (layer['x'], layer['y'], layer['width'], layer['height']) == (400, 500, 250, 1)
    assert p.render().getpixel((500, 500))[:3] == (0, 0, 0)


def test_adaptation_can_recompose_saved_copy():
    p = Project(1080, 1080, 'white')
    op = {'type': 'layout-apply', 'name': 'hero-statement', 'title': 'A readable headline',
          'subtitle': 'The same copy in a new size', 'seed': 12, 'unfilled': 'omit'}
    p.apply(op)
    p.apply({'type': 'adapt-layout', 'size': 'story', 'recompose': True})
    direct = Project.sized('story', background='white', design=False)
    direct.apply(op)
    first = [(x['text'], x['size'], x['x'], x['y']) for x in p.state['layers'] if x['type'] == 'text']
    second = [(x['text'], x['size'], x['x'], x['y']) for x in direct.state['layers'] if x['type'] == 'text']
    assert first == second


def test_swimlane_diagram_stays_inside_a_small_area():
    p = Project(800, 600, 'white')
    p.apply({'type': 'diagram-from-text', 'name': 'lanes', 'text': 'Customer: Ask -> Pay\nShop: Deliver -> Finish',
             'lanes': True, 'x': 30, 'y': 40, 'width': 200, 'height': 100})
    box = p.inspect('lanes')['resolved_bounds']
    assert box[0] >= 30 and box[1] >= 40
    assert box[0] + box[2] <= 231 and box[1] + box[3] <= 141


@pytest.mark.parametrize('name', ['video-tip', 'video-launch', 'video-event'])
def test_short_video_templates_are_editable_seamless_and_visible(name):
    from vixl.resources import TEMPLATES, validate
    from vixl.timeline import project_at, seam_findings
    validate('templates', TEMPLATES[name])
    p = Project(540, 540, 'white')
    p.apply({'type': 'template-apply', 'name': name, 'seed': 1,
             'variables': {'title': 'A useful idea', 'subtitle': 'Explain the benefit.', 'cta': 'Learn more'}})
    assert len([x for x in p.state['layers'] if x['type'] == 'text']) == 3
    assert not seam_findings(p)
    assert project_at(p, 2000).render().tobytes() != project_at(p, 0).render().tobytes()
    assert project_at(p, 2000).check(checks=['bounds'])['passed']


def test_scale_aware_social_minimum():
    p = Project.sized('instagram-square', 'white', design=False)
    p.apply({'type': 'text', 'text': 'Caption', 'size': 21, 'color': 'black', 'x': 100, 'y': 100})
    report = p.check(checks=['legibility'])
    assert not report['passed']
    p.apply({'type': 'text-set', 'size': 24})
    assert p.check(checks=['legibility'])['passed']


def test_contact_sheet_reuses_native_frames_for_export(tmp_path, monkeypatch):
    from vixl.render_cache import enable
    from vixl.timeline import contact_sheet, _frames
    import vixl.render as renderer
    p = Project(1920, 1080, 'white')
    p.apply([{'type': 'shape', 'shape': 'ellipse', 'name': 'dot', 'width': 100, 'height': 100},
             {'type': 'animate', 'property': 'x', 'to': 600, 'duration': 1000}])
    enable(p, tmp_path / 'cache')
    contact_sheet(p, times=[0, 500, 1000])
    def forbidden(*args, **kwargs):
        raise AssertionError('Cached frame should bypass layer rendering')
    monkeypatch.setattr(renderer, 'layer_surface', forbidden)
    assert len(list(_frames(p, [0, 500, 1000], 1))) == 3


@pytest.mark.parametrize('blend', ['screen', 'multiply', 'overlay', 'difference'])
def test_svg_native_blend_preserves_vectors_and_appearance(blend):
    import io
    import numpy as np
    import resvg_py
    from vixl.svg import export_svg
    p = Project(240, 140, '#234567')
    p.apply([{'type': 'shape', 'shape': 'rectangle', 'name': 'base', 'fill': '#662233', 'x': 20, 'y': 20,
              'width': 130, 'height': 100},
             {'type': 'shape', 'shape': 'rectangle', 'name': 'blend', 'fill': '#338855',
              'x': 80, 'y': 20, 'width': 130, 'height': 100},
             {'type': 'blend', 'value': blend},
             {'type': 'text', 'text': 'Vector', 'size': 20, 'x': 15, 'y': 5}])
    svg = export_svg(p, svg_policy='strict')
    assert b'<image' not in svg and b'mix-blend-mode' in svg
    actual = Image.open(io.BytesIO(resvg_py.svg_to_bytes(svg_string=svg.decode()))).convert('RGB')
    expected = p.render().convert('RGB')
    assert np.max(np.abs(np.array(actual.getpixel((100, 80)), dtype=int) - expected.getpixel((100, 80)))) <= 2


def test_tall_layout_uses_width_and_flags_tiny_content():
    p = Project(1080, 1920, 'white')
    p.apply({'type': 'layout-apply', 'name': 'quiet-editorial', 'seed': 1,
             'title': 'A useful announcement for everyone', 'body': 'Clear information for the whole team.'})
    headline = next(x for x in p.state['layers'] if x['type'] == 'text' and 'headline' in x['name'])
    assert headline['width'] > 600
    p = Project(1080, 1920, 'white')
    p.apply({'type': 'text', 'text': 'Tiny block', 'size': 24, 'x': 300, 'y': 600})
    assert any(x.get('code') == 'underfill' for x in p.check(checks=['content'])['issues'])


def test_paint_physics_controls_are_independent_and_repeatable(tmp_path):
    import numpy as np
    from vixl.brushes import brush_settings, stroke_alpha
    stroke = {'points': [[60, 60], [200, 60]], 'size': 30, 'seed': 3}
    flat = stroke_alpha(stroke, brush_settings({}, 'round'), (220, 260))
    wet = stroke_alpha(stroke, brush_settings({}, 'round', {'drip': 2}), (220, 260))
    assert np.nonzero(wet)[0].max() > np.nonzero(flat)[0].max() + 10
    assert np.array_equal(wet, stroke_alpha(stroke, brush_settings({}, 'round', {'drip': 2}), (220, 260)))
    p = Project(260, 220)
    p.apply({'type': 'paint', **stroke, 'color': '#888888', 'settings': {'relief': 1}})
    image = p.render()
    pixels = np.asarray(image)
    values = pixels[:, :, 0][pixels[:, :, 3] > 100]
    assert values.min() < 120 and values.max() > 160
    p.save(tmp_path / 'paint.vixl')
    assert Project.load(p.path).render().tobytes() == image.tobytes()


@pytest.mark.parametrize('direction,extra', [('horizontal', {}), ('angled', {'angle': 35}), ('radial', {'center': [0.3, 0.6]})])
def test_own_svg_simple_gradients_roundtrip_editably(direction, extra):
    from vixl.svg import export_svg
    from vixl.imports import svg_operations
    import numpy as np
    p = Project(240, 160)
    p.apply({'type': 'gradient', 'name': 'g', 'width': 180, 'height': 100, 'x': 20, 'y': 20,
             'start': 'red', 'end': '#0000ff00', 'direction': direction, **extra})
    q = Project(240, 160)
    q.apply(svg_operations(export_svg(p), q, 'roundtrip'))
    assert q.state['layers'][0]['type'] == 'gradient'
    assert np.max(np.abs(np.asarray(p.render(), dtype=int) - np.asarray(q.render(), dtype=int))) <= 1


def test_own_svg_stroked_path_roundtrip_editably():
    from vixl.svg import export_svg
    from vixl.imports import svg_operations
    p = Project(240, 160)
    p.apply({'type': 'shape', 'shape': 'path', 'path': 'M0 0 L100 60 L160 0',
             'stroke': 'red', 'stroke_width': 8, 'x': 20, 'y': 30})
    q = Project(240, 160)
    q.apply(svg_operations(export_svg(p), q, 'roundtrip'))
    assert all(x['type'] == 'shape' for x in q.state['layers'])
    import io
    import resvg_py
    reference = Image.open(io.BytesIO(resvg_py.svg_to_bytes(svg_string=export_svg(p).decode())))
    assert all(abs(a - b) <= 1 for a, b in zip(q.render().getbbox(), reference.getbbox()))


def test_pose_keys_keep_joint_attachment_between_keys(tmp_path):
    import math
    from vixl.timeline import project_at
    p = Project(640, 480, 'white')
    p.apply([{'type': 'character', 'name': 'actor', 'x': 150, 'y': 60},
             {'type': 'character-pose', 'target': 'actor', 'time': 0,
              'angles': {'right-upper-arm': -60, 'right-lower-arm': 100}},
             {'type': 'character-pose', 'target': 'actor', 'time': 1000,
              'angles': {'right-upper-arm': 60, 'right-lower-arm': -100}}])
    before = json.dumps(p.state, sort_keys=True)
    for time in range(0, 1001, 125):
        frame = project_at(p, time)
        bones = frame.layer('actor')['character']['bones']
        for name in ('right-upper-arm', 'right-lower-arm'):
            child_name = 'right-lower-arm' if name == 'right-upper-arm' else 'right-hand'
            parent, child = (frame.layer(bones[n]['layer']) for n in (name, child_name))
            pivots = [(x['x'] + x['pivot'][0] * x['width'], x['y'] + x['pivot'][1] * x['height'])
                      for x in (parent, child)]
            assert math.dist(*pivots) == pytest.approx(bones[name]['length'], abs=1e-7)
    assert json.dumps(p.state, sort_keys=True) == before
    p.save(tmp_path / 'pose.vixl')
    assert project_at(Project.load(p.path), 500).render().tobytes() == project_at(p, 500).render().tobytes()


def test_tiny_marker_size_warns_in_pixels():
    p = Project(200, 100)
    result = p.apply({'type': 'shape', 'shape': 'line', 'width': 100, 'height': 1,
                      'stroke_width': 5, 'marker_end': 'triangle', 'marker_size': 2})
    assert 'local pixels' in str(result.get('warnings'))


def test_fast_luminance_preserves_contrast_values():
    import numpy as np
    from vixl.measure import luminance
    pixels = np.random.default_rng(2).integers(0, 256, (128, 128, 3), dtype=np.uint8)
    assert np.allclose(luminance(pixels), luminance(pixels.astype(float)), rtol=0, atol=1e-15)


def test_screen_capture_workflow_is_explicit_bounded_and_refuses_overwrite(tmp_path, monkeypatch):
    from PIL import ImageGrab
    from vixl.interfaces import Session
    from vixl.workflows import dispatch
    from vixl.errors import VixlError
    calls = []
    def grab(**options):
        calls.append(options)
        return Image.new('RGB', (40, 30), 'red')
    monkeypatch.setattr(ImageGrab, 'grab', grab)
    session = Session(workspace=tmp_path)
    result = dispatch(session, 'screen-capture', {'output': 'capture.png', 'bbox': [-20, 0, 20, 30]})
    assert result['width'] == 40 and calls == [{'all_screens': False, 'bbox': (-20, 0, 20, 30)}]
    assert Image.open(tmp_path / 'capture.png').getpixel((0, 0)) == (255, 0, 0, 255)
    with pytest.raises(VixlError):
        dispatch(session, 'screen-capture', {'output': 'capture.png'})
    with pytest.raises(VixlError):
        dispatch(session, 'screen-capture', {'output': 'bad.png', 'bbox': [1, 2, 0, 3]})
    assert len(calls) == 1


def test_new_house_short_timelines_are_seamless_and_easing_follows_intent():
    from vixl.motion import findings
    p = Project.sized('instagram-square', 'white', seed=1, workspace_fonts=False)
    p.apply([{'type': 'shape', 'name': 'dot', 'shape': 'ellipse', 'width': 200, 'height': 200, 'x': 300, 'y': 300},
             {'type': 'animate-preset', 'target': 'dot', 'preset': 'fade-in'}])
    assert p.state['timeline']['loop_mode'] == 'seamless'
    assert not [i for i in findings(p) if i['code'].startswith('loop-seam')]
    q = Project(200, 200)
    q.apply([{'type': 'shape', 'shape': 'ellipse', 'width': 40, 'height': 40},
             {'type': 'animate-preset', 'preset': 'fade-out'}])
    assert q.state['timeline']['tracks'][0]['keys'][0]['easing'] == 'ease-in'
    q.apply({'type': 'animate', 'property': 'x', 'to': 60, 'intent': 'entrance'})
    assert q.state['timeline']['tracks'][-1]['keys'][0]['easing'] == 'ease-out'


def test_shared_spacing_units_for_stacks_and_charts():
    from vixl.craft import body_size, space
    from vixl.charts import Style
    p = Project.sized('instagram-square', 'white', seed=1, workspace_fonts=False)
    p.apply([{'type': 'text', 'name': 'a', 'text': 'One', 'size': 30},
             {'type': 'text', 'name': 'b', 'text': 'Two', 'size': 30},
             {'type': 'stack', 'name': 'copy', 'targets': ['a', 'b'], 'gap': '2u'}])
    assert p.layer('copy')['stack']['gap'] == space(2, body_size(p))
    chart = Style(p, {'font_size': 21}, 700, 500)
    assert chart.pad == space(2, 21)
    q = Project(1080, 1080, 'white')
    q.apply({'type': 'layout-apply', 'name': 'quiet-editorial', 'title': 'Heading', 'body': 'Body', 'gap': '2u', 'seed': 1})
    assert q.state['layout']['recipe']['gap'] == '2u'


def test_irregular_frame_preserves_mask_after_content_replacement(tmp_path):
    from vixl.assets import add_image
    p = Project(100, 100)
    red = add_image(p, Image.new('RGBA', (100, 100), 'red'))
    blue = add_image(p, Image.new('RGBA', (100, 100), 'blue'))
    p.apply({'type': 'frame', 'name': 'shaped', 'asset': red, 'width': 100, 'height': 100,
             'outline': 'M50 0 L100 50 L50 100 L0 50 Z'})
    assert p.render().getpixel((0, 0))[3] == 0
    assert p.render().getpixel((50, 50)) == (255, 0, 0, 255)
    p.apply({'type': 'replace-contents', 'target': 'shaped', 'asset': blue})
    p.save(tmp_path / 'frame.vixl')
    q = Project.load(p.path)
    assert q.render().getpixel((0, 0))[3] == 0
    assert q.render().getpixel((50, 50)) == (0, 0, 255, 255)
    q.export(tmp_path / 'frame.png')
    assert Image.open(tmp_path / 'frame.png').getpixel((0, 0))[3] == 0
