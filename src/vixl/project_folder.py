"""Deterministic, current-state-only source folders for reviewing designs in Git."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path, PurePosixPath
import tempfile
import zipfile

from .assets import read_bounded
from .errors import require
from .production import write_bytes
from .model import Limits


def _asset_name(name):
    path = PurePosixPath(name)
    require(len(path.parts) == 2 and path.parts[0] in ('assets', 'fonts', 'masks', 'sources', 'emoji-sources')
            and path.parts[1] not in ('', '.', '..') and '\\' not in name,
            f'Unsafe asset path: {name}', 'invalid_project')
    return name


def unpack(source, directory, *, limits=None):
    """Write a source folder without history/volatile session data; refuse an existing directory."""
    from .project import Project
    project = Project.load(source, limits=limits)
    directory = Path(directory).absolute()
    require(not directory.exists(), f'Output directory already exists: {directory}', 'output_exists')
    directory.parent.mkdir(parents=True, exist_ok=True)
    project._rebase_links(directory / 'source.vixl')
    state = deepcopy(project.state)
    # Assets referenced only by undo history do not belong in a source snapshot.
    from .compaction import _current_references
    referenced = _current_references(project.state)[0]
    referenced |= set(state.get('fonts', {}).values())
    assets = {name: data for name, data in project.assets.items() if name in referenced}
    document = {'format': 'vixl-source', 'version': 1, 'state': state,
                'asset_hashes': {name: hashlib.sha256(data).hexdigest() for name, data in sorted(assets.items())}}
    with tempfile.TemporaryDirectory(dir=directory.parent, prefix='.vixl-source-') as staging:
        root = Path(staging) / 'source'
        root.mkdir()
        (root / 'project.json').write_text(json.dumps(document, ensure_ascii=False, sort_keys=True,
                                                    indent=2, allow_nan=False) + '\n', encoding='utf-8')
        for name, data in assets.items():
            target = root / _asset_name(name)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        root.rename(directory)
    return {'directory': str(directory), 'assets': len(assets), 'history': 'current-state-only'}


def pack(directory, output, *, limits=None, overwrite=False):
    """Validate a source snapshot with the archive loader, then publish deterministic ZIP bytes."""
    from .project import Project, FORMAT_VERSION
    from . import __version__
    limits = limits or Limits()
    directory = Path(directory).resolve()
    document = directory / 'project.json'
    require(document.is_file() and not document.is_symlink(), 'Missing or unsafe project.json', 'invalid_project')
    raw = read_bounded(document, limits.max_project_bytes)
    source = json.loads(raw)
    require(isinstance(source, dict) and set(source) == {'format', 'version', 'state', 'asset_hashes'}
            and source['format'] == 'vixl-source' and source['version'] == 1,
            'Unsupported source folder format', 'invalid_project')
    hashes = source['asset_hashes']
    require(isinstance(hashes, dict) and len(hashes) <= 9999, 'Invalid asset manifest', 'invalid_project')
    assets, total = {}, len(raw)
    for name, expected in hashes.items():
        path = directory / _asset_name(name)
        require(path.is_file() and not path.is_symlink() and not path.parent.is_symlink()
                and path.resolve().is_relative_to(directory), f'Missing or unsafe asset: {name}', 'missing_asset')
        data = read_bounded(path, limits.max_asset_bytes)
        total += len(data)
        require(total <= limits.max_project_bytes, 'Expanded project exceeds byte limit', 'resource_limit')
        require(hashlib.sha256(data).hexdigest() == expected, f'Asset checksum mismatch: {name}', 'invalid_project')
        assets[name] = data
    ident = 'rev_' + hashlib.sha256(json.dumps(source['state'], sort_keys=True, allow_nan=False).encode()).hexdigest()[:16]
    metadata = {'format_version': FORMAT_VERSION, 'vixl_version': __version__, 'state': source['state'],
                'nodes': {ident: {'id': ident, 'parent': None, 'operations': [], 'label': 'Pack source folder',
                                  'state': source['state']}}, 'head': ident, 'branches': {'main': ident},
                'checkpoints': {}, 'current_branch': 'main', 'redo_stack': [], 'transaction': None,
                'asset_hashes': hashes}
    output = Path(output).absolute()
    require(output.suffix == '.vixl', 'Project filenames must end in .vixl')
    require(overwrite or not output.exists(), f'Output already exists: {output}', 'output_exists')
    # Load from beside project.json so relative links resolve from the source folder.
    with tempfile.NamedTemporaryFile(dir=directory, suffix='.vixl', delete=False) as stream:
        staged = Path(stream.name)
    try:
        _archive(staged, metadata, assets)
        candidate = Project.load(staged, limits=limits)
        candidate._rebase_links(output)
        if candidate.state != metadata['state']:
            metadata['state'] = candidate.state
            metadata['nodes'][ident]['state'] = candidate.state
        _archive(staged, metadata, assets)
        Project.load(staged, limits=limits)
        write_bytes(output, staged.read_bytes(), replace=overwrite)
    finally:
        staged.unlink(missing_ok=True)
    return {'path': str(output), 'assets': len(assets), 'history': 'current-state-only'}


def _archive(path, metadata, assets):
    entries = {'project.json': json.dumps(metadata, ensure_ascii=False, sort_keys=True,
                                         separators=(',', ':'), allow_nan=False).encode(), **assets}
    with zipfile.ZipFile(path, 'w') as archive:
        for name, data in sorted(entries.items()):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, data)
