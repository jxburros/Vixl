import hashlib
import io
import json
from pathlib import Path
import zipfile

import pytest
from PIL import Image

from vixl import Project, VixlError
from vixl.commands import compile_command
from vixl.history import diff, patch
from vixl.model import Limits


def test_path_source_size_places_and_resizes_unchanged_geometry(tmp_path):
    p = Project(160, 160, 'transparent')
    path = 'M0 0 H220 V380 H0 Z'
    p.apply({'type': 'shape', 'shape': 'path', 'name': 'mark', 'path': path,
             'path_view': [220, 380], 'width': 30, 'height': 52, 'x': 10, 'y': 12, 'fill': 'red'})
    assert p.layer('mark')['path'] == path
    info = p.inspect('mark')
    assert info['source_bounds'] == [0, 0, 220, 380]
    assert info['path_local_bounds'] == pytest.approx([0, 0, 30, 52])
    from vixl.proxy import scaled_project
    assert scaled_project(p, .5).render().getbbox() == (5, 6, 20, 32)
    assert p.render().getbbox() == (10, 12, 40, 64)
    assert p.bounds('mark') == (10, 12, 30, 52)
    p.apply({'type': 'resize', 'target': 'mark', 'width': 60, 'height': 104})
    assert p.render().getbbox() == (10, 12, 70, 116)
    assert p.layer('mark')['path_view'] == [220, 380]
    for fmt in ('svg', 'pdf'):
        p.export(tmp_path / f'mark.{fmt}')
    import pypdfium2
    page = pypdfium2.PdfDocument(str(tmp_path / 'mark.pdf'))[0]
    image = page.render(scale=1, fill_color=(0, 0, 0, 0)).to_pil().convert('RGBA')
    mask = image.convert('RGB').point(lambda v: v)
    from PIL import ImageChops
    assert ImageChops.difference(mask, Image.new('RGB', image.size, 'white')).getbbox() == (10, 12, 70, 116)
    p.save(tmp_path / 'mark.vixl')
    assert Project.load(tmp_path / 'mark.vixl').render().tobytes() == p.render().tobytes()
    p.apply({'type': 'shape', 'target': 'mark', 'path_view': [440, 760]})
    assert p.render().getbbox() == (10, 12, 40, 64)


def test_path_source_cli_and_invalid_requests_are_atomic():
    op = compile_command('shape path --path "M0 0 H220 V380 H0 Z" --path-view 220 380 --width 30 --height 52')
    assert op['path_view'] == [220, 380]
    p = Project(80, 80)
    for view in ([0, 10], [10], [-2, 3], [1, 2, 3], [True, 10]):
        before = json.dumps(p.state)
        with pytest.raises(VixlError):
            p.apply({'type': 'shape', 'shape': 'path', 'path': 'M0 0 L10 10', 'path_view': view})
        assert json.dumps(p.state) == before
    with pytest.raises(VixlError, match='path shapes only'):
        p.apply({'type': 'shape', 'shape': 'rectangle', 'path_view': [10, 10]})


@pytest.mark.parametrize('before,after', [
    ({'a': 1, 'b': 2}, {'b': 2, 'a': 1}),
    ({'a': 1, 'c': 3}, {'a': 1, 'b': 2, 'c': 3}),
    ({'layers': [{'id': 'x', 'a': 1, 'b': 2}]}, {'layers': [{'b': 2, 'a': 1, 'id': 'x'}]}),
])
def test_delta_preserves_json_key_order(before, after):
    assert json.dumps(patch(before, diff(before, after))) == json.dumps(after)
    assert json.dumps(patch(after, diff(after, before))) == json.dumps(before)


def test_undo_redo_serializes_identical_state(tmp_path):
    p = Project(40, 40)
    p.apply({'type': 'shape', 'shape': 'rectangle', 'name': 'box', 'fill': 'red'})
    p.apply({'type': 'layer-intent', 'target': 'box', 'alt': 'Red square'})
    p.save(tmp_path / 'before.vixl')
    p.undo()
    p.redo()
    p.save(tmp_path / 'after.vixl')
    with zipfile.ZipFile(tmp_path / 'before.vixl') as a, zipfile.ZipFile(tmp_path / 'after.vixl') as b:
        assert a.read('project.json') == b.read('project.json')


def test_archive_aggregate_pixel_budget_precedes_decode(tmp_path, monkeypatch):
    p = Project(20, 20)
    for color in ('red', 'blue'):
        data = io.BytesIO()
        Image.new('RGB', (20, 20), color).save(data, format='PNG')
        p.import_image(data=data.getvalue(), name=color)
    p.save(tmp_path / 'images.vixl')
    import vixl.project
    monkeypatch.setattr(vixl.project, 'decode', lambda *a, **k: pytest.fail('decoded before aggregate guard'))
    with pytest.raises(VixlError) as error:
        Project.load(tmp_path / 'images.vixl', limits=Limits(max_load_pixels=700))
    assert error.value.code == 'resource_limit'
    assert error.value.details['field'] == 'max_load_pixels'


def test_archive_font_budget_precedes_freetype(tmp_path, monkeypatch):
    p = Project(20, 20)
    font = Path(__file__).resolve().parents[1] / 'src/vixl/data/DejaVuSans.ttf'
    data = font.read_bytes()
    asset = f'fonts/{hashlib.sha256(data).hexdigest()}.ttf'
    p.assets[asset] = data
    p.apply({'type': 'font-register', 'name': 'test', 'asset': asset})
    p.save(tmp_path / 'fonts.vixl')
    from PIL import ImageFont
    monkeypatch.setattr(ImageFont, 'truetype', lambda *a, **k: pytest.fail('parsed before font guard'))
    with pytest.raises(VixlError) as error:
        Project.load(tmp_path / 'fonts.vixl', limits=Limits(max_load_fonts=0))
    assert error.value.code == 'resource_limit'
    assert error.value.details['field'] == 'max_load_fonts'


def test_interface_matrix_matches_enforced_registry():
    from vixl.interface_capabilities import REST_WORKFLOWS, markdown_table
    from vixl.workflows import ACTIONS
    assert REST_WORKFLOWS <= ACTIONS.keys()
    text = (Path(__file__).resolve().parents[1] / 'docs/reference/interfaces.md').read_text()
    actual = text.split('<!-- interface-capabilities:start -->\n')[1].split('\n<!-- interface-capabilities:end -->')[0]
    assert actual == markdown_table()


@pytest.mark.parametrize('color,passing', [('#d4241c', True), ('#e8deca', False)])
def test_nested_rotated_styled_text_contrast_uses_glyph_coverage(color, passing):
    from vixl.measure import measure
    p = Project(800, 300, '#efe6d2')
    p.apply([
        {'type': 'text', 'name': 'title', 'text': 'SIGNAL', 'size': 45, 'color': color, 'x': 200.25, 'y': 100.75},
        {'type': 'layer-style', 'target': 'title', 'name': 'stroke', 'settings': {'color': '#efe6d2', 'width': 2}},
        {'type': 'layer-style', 'target': 'title', 'name': 'drop-shadow',
         'settings': {'color': 'black', 'dx': 2, 'dy': 2, 'opacity': .4, 'blur': 0}},
        {'type': 'shape', 'shape': 'rectangle', 'name': 'bar', 'x': 430.5, 'y': 100.75,
         'width': 200, 'height': 65, 'fill': '#112244'},
        {'type': 'text', 'name': 'tag', 'text': 'NOW', 'size': 39, 'color': '#efe6d2', 'x': 440.25, 'y': 104.5},
        {'type': 'group', 'name': 'tag-group', 'targets': ['bar', 'tag']},
    ])
    plain = measure(p, target='title', histogram='none')['contrast']
    p.apply([{'type': 'group', 'name': 'inner', 'targets': ['title']},
             {'type': 'group', 'name': 'lockup', 'targets': ['inner', 'tag-group']},
             {'type': 'rotate', 'target': 'lockup', 'angle': 352}])
    rotated = measure(p, target='title', histogram='none')['contrast']
    assert abs(rotated['p10'] - plain['p10']) < .35
    findings = [f for f in p.check(checks=['contrast'])['issues'] if 'title' in f.get('layers', [])]
    assert bool(findings) is not passing


@pytest.mark.parametrize('mode', ['multiply', 'screen', 'darken', 'lighten', 'difference', 'add', 'subtract'])
def test_opaque_blends_cover_all_channel_pairs_within_one_step(mode):
    import numpy as np
    from vixl.render import composite
    x, y = np.meshgrid(np.arange(256, dtype=np.float64), np.arange(256, dtype=np.float64))
    formulas = {'multiply': x*y/255, 'screen': x+y-x*y/255, 'darken': np.minimum(x,y),
                'lighten': np.maximum(x,y), 'difference': abs(x-y), 'add': np.minimum(255,x+y),
                'subtract': np.maximum(0,x-y)}
    bottom = Image.fromarray(x.astype('uint8')).convert('RGBA')
    top = Image.fromarray(y.astype('uint8')).convert('RGBA')
    actual = np.array(composite(bottom, top, mode))
    expected = np.floor(formulas[mode]+.5).astype('int16')
    assert np.max(abs(actual[:,:,0].astype('int16') - expected)) <= 1
    assert (actual[:,:,3] == 255).all()


def test_transparent_blends_keep_alpha_equation():
    from vixl.render import composite
    bottom = Image.new('RGBA', (1, 1), (200, 100, 50, 128))
    top = Image.new('RGBA', (1, 1), (100, 200, 50, 128))
    assert composite(bottom, top, 'multiply').getpixel((0, 0)) == (126, 126, 37, 192)


def test_cli_short_output_and_legacy_spelling(tmp_path, monkeypatch):
    from vixl.cli import dispatch
    monkeypatch.chdir(tmp_path)
    dispatch(['new', '20x20', '-o', 'doc.vixl'])
    dispatch(['render', '-o', 'render.png'])
    dispatch(['export', '--out', 'export.png'])
    dispatch(['save', '-o', 'copy.vixl'])
    dispatch(['unpack', 'copy.vixl', '-o', 'folder'])
    dispatch(['pack', 'folder', '--out', 'packed.vixl'])
    (tmp_path / 'empty.vixlscript').write_text('grayscale\n')
    result, _ = dispatch(['batch', 'render.png', '--run', 'empty.vixlscript', '--output', 'batch'])
    assert result[0]['normalized'][0]['to'] == '--out'
    assert (tmp_path / 'batch/render.png').is_file()
    assert Project.load(tmp_path / 'packed.vixl').render().size == (20, 20)


def test_cli_help_is_compact_and_keeps_detailed_reference():
    from vixl.cli import dispatch
    help_text, _ = dispatch(['--help'])
    assert len(help_text.splitlines()) < 40
    assert 'vixl COMMAND --help' in help_text and 'vixl commands --json' in help_text
    detailed, _ = dispatch(['help', '--full'])
    assert len(detailed) > len(help_text)
