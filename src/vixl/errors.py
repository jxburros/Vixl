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
    (r"vixl layout show NAME", "vixl_layouts_list(name=…)"),
    (r"vixl layout list", "vixl_layouts_list"),
    (r"vixl font pairings / font pair, or font install", "vixl_fonts(view='pairings') then vixl_font_pair, or vixl_font_install"),
    (r"vixl font pair random", "vixl_font_pair()"),
    (r"vixl font pairings", "vixl_fonts(view='pairings')"),
)
_FOR_CLI = (
    (r"vixl_operation_schema\(types=\['([\w-]+)'\]\)", r"vixl capabilities \1"),
    (r"vixl_operation_schema\(types=\[(?:…|\.\.\.)\]\)", "vixl schema"),
    (r"vixl_layouts_list\(name=…\)", "vixl layout show NAME"),
    (r"vixl_layouts_list", "vixl layout list"),
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


def friendly(exc):
    """A VixlError for an exception raised by the OS, the JSON decoder or Python itself, with a message a person
    can act on instead of a Python repr. VixlErrors pass through."""
    import json

    if isinstance(exc, VixlError):
        return exc
    if isinstance(exc, FileNotFoundError):
        return VixlError("not_found", f"No such file: {exc.filename}" if exc.filename else "No such file")
    if isinstance(exc, IsADirectoryError):
        return VixlError("io_error", f"{exc.filename} is a folder, not a file")
    if isinstance(exc, PermissionError):
        return VixlError("io_error", f"Permission denied: {exc.filename}" if exc.filename else "Permission denied")
    if isinstance(exc, UnicodeDecodeError):
        return VixlError("invalid_input", f"The input is not UTF-8 text (byte {exc.start}); save JSON as UTF-8")
    if isinstance(exc, json.JSONDecodeError):
        return VixlError("invalid_json", f"Invalid JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}")
    if isinstance(exc, OSError):
        return VixlError("io_error", exc.strerror or str(exc))
    if isinstance(exc, MemoryError):
        return VixlError("resource_limit", "Not enough memory for this operation; use a smaller canvas, scale or batch")
    return VixlError("invalid_input", str(exc))
