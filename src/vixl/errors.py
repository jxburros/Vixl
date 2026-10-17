class VixlError(Exception):
    def __init__(self, code: str, message: str, **details):
        super().__init__(message)
        self.code = code
        self.details = details

    def as_dict(self):
        return {"error": self.code, "message": str(self), **self.details}


def require(condition, message, code="invalid_operation", **details):
    if not condition:
        raise VixlError(code, message, **details)


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
    (r"vixl_reference\('layouts', name=…\)", "vixl layout show NAME"),
    (r"vixl_reference\('layouts'\)", "vixl layout list"),
)


def for_surface(value, surface):
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


def memory_guard(function):
    """Report running out of memory (a large canvas, a numpy allocation) as a ``resource_limit`` VixlError. The
    error is raised after the failed call's frames are released, so the memory they held is free again."""
    import functools

    @functools.wraps(function)
    def guarded(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except MemoryError:
            pass
        raise VixlError("resource_limit", OUT_OF_MEMORY)

    return guarded


def shown_path(filename, relative_to=None):
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


def friendly(exc, relative_to=None, filename=None):
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

