"""Every place Vixl reaches past the public API of the MCP SDK (FastMCP).

FastMCP has no public setter for the advertised server version or for the instructions after construction, no
public tool registry, and no hook around a registered tool's ``run``. Vixl needs all four, so the private
attributes are read here and nowhere else. When an SDK release renames one, the call fails with
``missing_dependency`` naming the tested range instead of an ``AttributeError`` deep inside a tool call. The
``minimum-versions`` CI job runs the suite against the oldest and the newest SDK the pins allow.
"""

from typing import Any

from .errors import VixlError

TESTED = "mcp>=1.21.1,<2"


def _private(owner: Any, name: str) -> Any:
    if not hasattr(owner, name):
        raise VixlError("missing_dependency",
                        f"This version of the mcp SDK has no {type(owner).__name__}.{name}; Vixl is tested with "
                        f"{TESTED}: pip install '{TESTED}'", attribute=name)
    return getattr(owner, name)


def low_level(server: Any) -> Any:
    """The low-level ``mcp.server.lowlevel.Server`` behind a FastMCP server."""
    return _private(server, "_mcp_server")


def set_server_version(server: Any, version: str) -> None:
    """Advertise ``version`` as ``serverInfo.version`` (FastMCP reports the SDK's own version otherwise)."""
    low_level(server).version = version


def tool_manager(server: Any) -> Any:
    """FastMCP's tool registry (``get_tool``, ``list_tools``, ``call_tool``)."""
    return _private(server, "_tool_manager")


def append_instructions(server: Any, text: str) -> None:
    """Add ``text`` to the instructions the server sends in ``initialize``."""
    server_ = low_level(server)
    server_.instructions = (server_.instructions or "") + text


def instructions(server: Any) -> str:
    return str(low_level(server).instructions or "")


def wrap_tool_run(registered: Any, run: Any) -> None:
    """Replace a registered tool's ``run`` coroutine. ``Tool`` is a pydantic model and ``run`` a method, not a field,
    so pydantic's ``__setattr__`` refuses the assignment."""
    _private(registered, "run")
    object.__setattr__(registered, "run", run)
