from __future__ import annotations

from collections.abc import Callable
from os import PathLike
from typing import Any, ParamSpec, TypeVar

P = ParamSpec("P")
R = TypeVar("R")


class VixlError(Exception):
    def __init__(self, code: str, message: str, **details: Any) -> None:
        super().__init__(message)
        self.code = code
        self.details = details

    def as_dict(self) -> dict[str, Any]:
        return {"error": self.code, "message": str(self), **self.details}


class Cancelled(VixlError):
    """A call stopped because its caller cancelled it (code ``cancelled``). Services tell a cancelled job from a
    failed one by this type, never by the message text."""

    def __init__(self, message: str = "Call cancelled", **details: Any) -> None:
        super().__init__("cancelled", message, **details)


def require(condition: object, message: str, code: str = "invalid_operation", **details: Any) -> None:
    if not condition:
        raise Cancelled(message, **details) if code == "cancelled" else VixlError(code, message, **details)


# Error text names the command a reader can run. Messages are written once; these rewrites give each surface its own
# spelling of a hint, so a CLI user is not sent to an MCP tool and an agent is not sent to a shell command.
_FOR_MCP = (
    (r"vixl layout show NAME", "vixl_reference('layouts', name=…)"),
    (r"vixl layout list", "vixl_reference('layouts')"),
    (r"vixl font pairings / font pair, or font install",
     "vixl_reference('fonts') then a font-pair step in vixl_apply, or font-install"),
    (r"vixl font pair random", "a font-pair step in vixl_apply"),
    (r"vixl font pairings", "vixl_reference('fonts')"),
)
_FOR_CLI = (
    (r"vixl_reference\('operations', name=\['([\w-]+)'\]\)", r"vixl capabilities \1"),
    (r"vixl_reference\('operations', name=\[(?:…|\.\.\.)\]\)", "vixl schema"),
    (r"vixl_reference\('operations'(?:, name=[^()]*)?\)", "vixl schema"),
    (r"vixl_reference\('layouts', name=…\)", "vixl layout show NAME"),
    (r"vixl_reference\('layouts'\)", "vixl layout list"),
    (r"vixl_reference\('capabilities', name='([\w-]+)'[^()]*\)", r"vixl capabilities \1"),
    (r"vixl_reference\('capabilities'[^()]*\)", "vixl capabilities"),
    (r"vixl_reference\('(fonts|sizes|styles|looks|brushes|roll)'[^()]*\)", r"vixl \1"),
    (r"vixl_reference\('workflows'[^()]*\)", "vixl workflow --help"),
    (r"vixl_reference\('([\w-]+)'[^()]*\)", r"vixl guide \1"),
    (r"vixl_reference\(\)", "vixl guide"),
    (r"vixl_apply\(workflow='([\w-]+)'[^()]*\)", r"vixl workflow \1"),
    (r"vixl_document\(action='(inspect|layers|history|undo|redo|checkpoint|compact)'[^()]*\)", r"vixl \1"),
    (r"vixl_document\(action='create'[^()]*\)", "vixl new"),
    (r"vixl_document\(action='open'[^()]*\)", "vixl open FILE"),
    (r"vixl_document\(action='(checkout|branch|notes)'[^()]*\)", r"vixl \1"),
    (r"vixl_document\(action='(begin|commit|rollback)'[^()]*\)", r"vixl transaction \1"),
    (r"vixl_document\(action='list'[^()]*\)", "ls"),
    (r"vixl_document\(action='close'[^()]*\)", "nothing (the CLI keeps no open documents)"),
    (r"vixl_(check|render|export|apply)(?:\([^()]*\))?", r"vixl \1"),
)


def for_surface(value: Any, surface: str | None) -> Any:
    """``value`` (an error payload, or any string, list or dict in it) with hints spelled for ``surface``."""
    import re

    rules = _FOR_MCP if surface == "mcp" else _FOR_CLI if surface == "cli" else ()
    if isinstance(value, str):
        for pattern, replacement in rules:
            value = re.sub(pattern, replacement, value)
        return value
    if isinstance(value, dict):
        return {key: for_surface(item, surface) for key, item in value.items()}
    if isinstance(value, list):
        return [for_surface(item, surface) for item in value]
    return value


OUT_OF_MEMORY = "Not enough memory for this operation; use a smaller canvas, scale or batch"


def memory_guard(function: Callable[P, R]) -> Callable[P, R]:
    """Report running out of memory (a large canvas, a numpy allocation) as a ``resource_limit`` VixlError. The
    error is raised after the failed call's frames are released, so the memory they held is free again."""
    import functools

    @functools.wraps(function)
    def guarded(*args: P.args, **kwargs: P.kwargs) -> R:
        try:
            return function(*args, **kwargs)
        except MemoryError:
            pass
        raise VixlError("resource_limit", OUT_OF_MEMORY)

    return guarded


def shown_path(filename: Any, relative_to: str | PathLike[str] | None = None) -> Any:
    """``filename`` as an error message may show it: relative to ``relative_to`` (a workspace) when it lies inside,
    otherwise only its basename, so a message never reveals where the workspace sits on disk. Unchanged without
    ``relative_to``."""
    import os
    from pathlib import Path

    if relative_to is None or not isinstance(filename, (str, bytes, os.PathLike)):
        return filename
    path = Path(os.fsdecode(filename))
    try:
        root = Path(relative_to).resolve()
        return (path if path.is_absolute() else root / path).resolve().relative_to(root).as_posix()
    except (ValueError, OSError, RuntimeError):
        return path.name


def _missing_folder(filename: Any) -> str | None:
    """The folder of ``filename`` when that folder is what is missing, else None."""
    import os
    from pathlib import Path

    if not isinstance(filename, (str, bytes, os.PathLike)):
        return None
    parent = Path(os.fsdecode(filename)).parent
    try:
        return None if str(parent) in ("", ".") or parent.exists() else str(parent)
    except OSError:
        return None


def _inside(folder: str, root: str | PathLike[str]) -> str | None:
    """``folder`` relative to ``root`` when it lies inside, else None (a message never names folders outside)."""
    from pathlib import Path

    try:
        return Path(folder).resolve().relative_to(Path(root).resolve()).as_posix()
    except (ValueError, OSError, RuntimeError):
        return None


def friendly(exc: BaseException, relative_to: str | PathLike[str] | None = None,
             filename: str | None = None) -> VixlError:
    """A VixlError for an exception raised by the OS, the JSON decoder or Python itself, with a message a person
    can act on instead of a Python repr. VixlErrors pass through. ``relative_to`` (a workspace) shows the file
    relative to it, or only its basename when it lies outside; ``filename`` (the path as the caller wrote it)
    replaces the exception's own."""
    import json

    if isinstance(exc, VixlError):
        return exc
    name = getattr(exc, "filename", None)
    if name is not None:
        name = filename if filename is not None else shown_path(name, relative_to)
    if isinstance(exc, FileNotFoundError):
        folder = _missing_folder(getattr(exc, "filename", None))
        shown = folder if folder is None or relative_to is None else _inside(folder, relative_to)
        if name and shown:
            return VixlError("not_found", f"No such file: {name} (the folder {shown} does not exist)", field="path")
        return VixlError("not_found", f"No such file: {name}" if name else "No such file")
    if isinstance(exc, IsADirectoryError):
        return VixlError("io_error", f"{name} is a folder, not a file")
    if isinstance(exc, PermissionError):
        return VixlError("io_error", f"Permission denied: {name}" if name else "Permission denied")
    if isinstance(exc, UnicodeDecodeError):
        return VixlError("invalid_input", f"The input is not UTF-8 text (byte {exc.start}); save JSON as UTF-8")
    if isinstance(exc, json.JSONDecodeError):
        return VixlError("invalid_json", f"Invalid JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}")
    if isinstance(exc, OSError):
        # str(exc) of an OSError without strerror can hold an absolute path.
        hidden = relative_to is not None or filename is not None
        return VixlError("io_error", exc.strerror or ("Input/output error" if hidden else str(exc)))
    if isinstance(exc, MemoryError):
        return VixlError("resource_limit", OUT_OF_MEMORY)
    return VixlError("invalid_input", str(exc))



def unknown_choice(field: str, got: Any, choices: Any) -> VixlError:
    """A bounded catalog miss, with enough alternatives to recover in one call."""
    import difflib

    names = sorted(choices)
    return VixlError("not_found", f"Unknown {field}: {got}", field=field, got=got,
                     allowed=names[:10], count=len(names),
                     suggestions=difflib.get_close_matches(str(got), names, 3, 0.4))
