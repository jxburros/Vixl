"""Persistence and MCP boundary regressions from the 0.25.1 issue sweep."""
import asyncio
from copy import deepcopy
from dataclasses import replace
import importlib.metadata
import json
import zipfile

from PIL import Image, ImageGrab
import pytest

from vixl import Project, VixlError
from vixl.interfaces import Session, mcp_server
from vixl.mcp_tools import build_server


@pytest.mark.parametrize('field,value', [
    (None, []), (None, None), ('branches', [1]), ('nodes', []),
    ('checkpoints', []), ('state', []), ('asset_hashes', []),
    ('redo_stack', {}), ('transaction', []),
])
def test_malformed_archive_has_structured_error(tmp_path, field, value):
    metadata = Project(16, 16).manifest()
    if field is None:
        metadata = value
    else:
        metadata[field] = value
    path = tmp_path / 'bad.vixl'
    with zipfile.ZipFile(path, 'w') as archive:
        archive.writestr('project.json', json.dumps(metadata))
    with pytest.raises(VixlError) as error:
        Project.load(path)
    assert error.value.code == 'invalid_project'


@pytest.mark.parametrize('exception', [IndexError, AttributeError, ZeroDivisionError])
def test_operation_exception_is_located_and_atomic(monkeypatch, exception):
    from vixl import operations
    project = Project(16, 16)
    before = deepcopy(project.manifest())
    original = operations.execute
    def fail(candidate, operation):
        if operation.get('name') == 'fail':
            raise exception('bad operation data')
        return original(candidate, operation)
    monkeypatch.setattr(operations, 'execute', fail)
    with pytest.raises(VixlError) as error:
        project.apply([{'type': 'solid', 'name': 'ok'}, {'type': 'solid', 'name': 'fail'}])
    assert error.value.code == 'invalid_operation'
    assert error.value.details['operation_index'] == 1
    assert isinstance(error.value.__cause__, exception)
    assert project.manifest() == before


@pytest.mark.parametrize('failure', ['resource_limit', 'write_conflict', 'io'])
def test_failed_save_preserves_document(tmp_path, monkeypatch, failure):
    from vixl import project as project_module
    source = Project(16, 16)
    source.save(tmp_path / 'source.vixl')
    project = Project(32, 32, workspace=tmp_path)
    path = tmp_path / 'host.vixl'
    project.save(path)
    project.apply({'type': 'link', 'source': 'source.vixl', 'name': 'linked'})
    project.save()
    project.assets['assets/unreferenced.png'] = b'unreferenced bytes'
    destination = tmp_path / 'nested' / 'host.vixl'
    if failure == 'resource_limit':
        project.limits = replace(project.limits, max_project_bytes=1)
        destination = path
    elif failure == 'write_conflict':
        path.write_bytes(b'changed by another writer')
        destination = path
    else:
        def fail_replace(*args):
            raise OSError('simulated disk failure')
        monkeypatch.setattr(project_module.os, 'replace', fail_replace)
    before = deepcopy(project.manifest())
    assets = dict(project.assets)
    revision = project._revision
    with pytest.raises(OSError if failure == 'io' else VixlError) as error:
        project.save(destination)
    if failure != 'io':
        assert error.value.code == failure
    assert project.manifest() == before
    assert project.assets == assets
    assert project.path == path and project._revision == revision
    if destination != path:
        assert not destination.exists()


@pytest.mark.parametrize('entry', ['public', 'builder'])
@pytest.mark.parametrize('version', ['2.2.0', '1.21.0', '1.11.0'])
def test_incompatible_mcp_sdk_names_version_and_install_fix(tmp_path, monkeypatch, entry, version):
    monkeypatch.setattr(importlib.metadata, 'version', lambda name: version)
    with pytest.raises(VixlError) as error:
        if entry == 'public':
            mcp_server(workspace=tmp_path)
        else:
            build_server(Session(workspace=tmp_path))
    assert error.value.code == 'missing_dependency'
    assert version in str(error.value) and "pip install 'mcp>=1.21.1,<2'" in str(error.value)


@pytest.mark.parametrize('enabled', [False, True, 'env'])
def test_mcp_screen_capture_requires_server_opt_in(tmp_path, monkeypatch, enabled):
    from mcp.server.fastmcp.exceptions import ToolError
    monkeypatch.delenv('VIXL_ALLOW_SCREEN_CAPTURE', raising=False)
    calls = []
    def grab(**options):
        calls.append(options)
        return Image.new('RGB', (16, 16), 'red')
    monkeypatch.setattr(ImageGrab, 'grab', grab)
    if enabled == 'env':
        monkeypatch.setenv('VIXL_ALLOW_SCREEN_CAPTURE', '1')
    server = mcp_server(workspace=tmp_path, allow_screen_capture=None if enabled == 'env' else enabled)
    # Permission is fixed when the server starts, not by a later environment change.
    monkeypatch.setenv('VIXL_ALLOW_SCREEN_CAPTURE', '0' if enabled else '1')
    async def capture():
        return await server.call_tool('vixl_apply', {'workflow': 'screen-capture', 'request': {'output': 'shot.png'}})
    if not enabled:
        with pytest.raises(ToolError, match='allow-screen-capture'):
            asyncio.run(capture())
        assert calls == [] and not (tmp_path / 'shot.png').exists()
    else:
        result = asyncio.run(capture())
        assert calls and (tmp_path / 'shot.png').exists()
        assert '"output":"shot.png"' in str(result)
        assert str(tmp_path) not in str(result)


@pytest.mark.parametrize('version', ['1.21.1', '1.22.0', '1.26.0rc1'])
def test_supported_mcp_sdk_versions_pass_the_check(monkeypatch, version):
    from vixl.mcp_tools import check_sdk

    monkeypatch.setattr(importlib.metadata, 'version', lambda name: version)
    check_sdk()
