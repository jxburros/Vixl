import pytest

from vixl import cli, interfaces
from vixl.errors import VixlError


class _Server:
    def run(self):
        pass


@pytest.fixture
def captured(monkeypatch):
    seen = {}

    def fake(path=None, limits=None, **kwargs):
        seen.update(kwargs)
        return _Server()

    monkeypatch.setattr(interfaces, "mcp_server", fake)
    return seen


def test_vixl_mcp_serves_the_design_tools_by_default(tmp_path, captured):
    cli.dispatch(["mcp", "--workspace", str(tmp_path)])
    assert captured["tools"] == "default" and "schema" not in captured


def test_vixl_mcp_ai_flag_and_retired_modes(tmp_path, captured):
    cli.dispatch(["mcp", "--workspace", str(tmp_path), "--tools", "ai"])
    assert captured["tools"] == "ai"
    for retired in (["--tools", "core"], ["--schema", "slim"]):
        with pytest.raises(VixlError, match="usage|unrecognized|invalid"):
            cli.dispatch(["mcp", "--workspace", str(tmp_path), *retired])


def test_screen_capture_flag_reaches_server(tmp_path, captured):
    cli.dispatch(["mcp", "--workspace", str(tmp_path), "--allow-screen-capture"])
    assert captured["allow_screen_capture"] is True
