import json

import pytest
from PIL import Image

from vixl import Project
from vixl.assets import add_image
from vixl.errors import VixlError
from vixl.project_folder import pack, unpack


def test_source_roundtrip_determinism_and_edit(tmp_path):
    p = Project(200, 100, 'white')
    asset = add_image(p, Image.new('RGBA', (20, 20), 'red'))
    p.apply([{'type': 'add', 'asset': asset, 'name': 'icon'},
             {'type': 'text', 'name': 'title', 'text': 'Hello', 'x': 30, 'size': 24}])
    p.save(tmp_path / 'input.vixl')
    directory = tmp_path / 'source'
    unpack(p.path, directory)
    pack(directory, tmp_path / 'first.vixl')
    pack(directory, tmp_path / 'second.vixl')
    assert (tmp_path / 'first.vixl').read_bytes() == (tmp_path / 'second.vixl').read_bytes()
    q = Project.load(tmp_path / 'first.vixl')
    assert q.state == p.state and q.assets == p.assets
    assert q.render().tobytes() == p.render().tobytes()
    path = directory / 'project.json'
    before = path.read_text()
    path.write_text(before.replace('Hello', 'World'))
    pack(directory, tmp_path / 'changed.vixl')
    assert Project.load(tmp_path / 'changed.vixl').layer('title')['text'] == 'World'


@pytest.mark.parametrize('attack', ['missing', 'unsafe', 'hash', 'symlink'])
def test_source_folder_rejects_bad_assets(tmp_path, attack):
    directory = tmp_path / 'source'
    directory.mkdir()
    name = '../secret' if attack == 'unsafe' else 'assets/test.png'
    payload = {'format': 'vixl-source', 'version': 1, 'state': {}, 'asset_hashes': {name: '0' * 64}}
    (directory / 'project.json').write_text(json.dumps(payload))
    if attack in ('hash', 'symlink'):
        (directory / 'assets').mkdir()
        target = directory / name
        if attack == 'symlink':
            secret = tmp_path / 'secret'
            secret.write_bytes(b'secret')
            try:
                target.symlink_to(secret)
            except OSError:
                pytest.skip('symlink creation unavailable')
        else:
            target.write_bytes(b'bad bytes')
    with pytest.raises(VixlError):
        pack(directory, tmp_path / 'out.vixl')
    assert not (tmp_path / 'out.vixl').exists()


def test_source_folder_keeps_registered_unused_fonts(tmp_path):
    import hashlib
    from vixl.text import primary_font_data
    p = Project(200, 100, 'white')
    data = primary_font_data(p, {})
    asset = f'fonts/{hashlib.sha256(data).hexdigest()}.ttf'
    p.assets[asset] = data
    p.apply({'type': 'font-register', 'name': 'spare-font', 'asset': asset})
    p.save(tmp_path / 'font.vixl')
    unpack(p.path, tmp_path / 'source')
    pack(tmp_path / 'source', tmp_path / 'packed.vixl')
    q = Project.load(tmp_path / 'packed.vixl')
    assert q.state['fonts'] == p.state['fonts'] and q.assets == p.assets
