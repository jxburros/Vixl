import pytest

from vixl import cli, interfaces


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
    monkeypatch.delenv("VIXL_MCP_TOOLS", raising=False)
    monkeypatch.delenv("VIXL_MCP_SCHEMA", raising=False)
    return seen


def test_vixl_mcp_defaults_to_core_slim(tmp_path, captured):
    cli.dispatch(["mcp", "--workspace", str(tmp_path)])
    assert captured["tools"] == "core"
    assert captured["schema"] == "slim"


def test_vixl_mcp_env_and_flags_override_defaults(tmp_path, captured, monkeypatch):
    monkeypatch.setenv("VIXL_MCP_TOOLS", "all")
    monkeypatch.setenv("VIXL_MCP_SCHEMA", "full")
    cli.dispatch(["mcp", "--workspace", str(tmp_path)])
    assert (captured["tools"], captured["schema"]) == ("all", "full")
    cli.dispatch(["mcp", "--workspace", str(tmp_path), "--tools", "compact", "--schema", "slim"])
    assert (captured["tools"], captured["schema"]) == ("compact", "slim")
