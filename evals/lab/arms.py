"""The three arms of a lab run: the same model and brief, with different tools.

- ``bare``: no tools. The model answers in text; fenced code blocks (SVG, HTML, Markdown ...) are saved as files.
- ``code``: the fair control. File tools, ``run_python`` (a sandboxed subprocess with whatever drawing and document
  libraries are installed) and, when Playwright is installed, ``render_page`` to see HTML and SVG.
- ``vixl``: Vixl's MCP tools (the real server, in-process) plus the same file tools, so the only difference from
  ``code`` is Vixl in place of Python.

Every arm gets the same opening system prompt; only the paragraph describing its tools differs.
"""

import json
from pathlib import Path
import re
import threading

from . import previews, sandbox

BASE_SYSTEM = (
    "You are working in a fresh, empty workspace folder on the user's computer. Make what the user asks for and save "
    "every deliverable as a file in the workspace, using workspace-relative paths. When your tools let you look at "
    "your work, check it before you finish. When everything is saved, reply with a short summary that names the "
    "deliverable files."
)

ARMS = {
    "bare": {"label": "Bare", "description": "No tools: the model writes SVG, HTML or Markdown in its reply."},
    "code": {"label": "Code tools", "description": "Files, sandboxed Python and an HTML/SVG renderer: the fair control."},
    "vixl": {"label": "Vixl", "description": "Vixl's MCP tools plus the same file tools."},
}

TEXT_SUFFIXES = {".svg", ".html", ".htm", ".css", ".js", ".md", ".txt", ".csv", ".json", ".xml", ".py", ".tsv",
                 ".yaml", ".yml"}
LANGUAGE_SUFFIX = {"svg": ".svg", "html": ".html", "htm": ".html", "css": ".css", "markdown": ".md", "md": ".md",
                   "csv": ".csv", "json": ".json", "txt": ".txt", "text": ".txt", "xml": ".xml", "tsv": ".tsv",
                   "yaml": ".yaml", "yml": ".yaml", "javascript": ".js", "js": ".js"}
READ_LIMIT = 20000
VIXL_LOCK = threading.Lock()  # one Vixl tool call at a time across sessions: the servers share process state
SKILL = Path(__file__).resolve().parents[2] / "skills" / "vixl" / "SKILL.md"


class ToolError(Exception):
    pass


def inside(workspace, relative):
    """The resolved path of ``relative`` inside ``workspace``; refuses anything that leaves it."""
    if not isinstance(relative, str) or not relative.strip():
        raise ToolError("path must be a non-empty workspace-relative string")
    root = Path(workspace).resolve()
    target = (root / relative).resolve()
    if target != root and root not in target.parents:
        raise ToolError(f"{relative!r} is outside the workspace")
    return target


def text(value):
    return [{"type": "text", "text": value}]


def schema(properties, required=()):
    return {"type": "object", "properties": properties, "required": list(required), "additionalProperties": False}


class FileTools:
    def __init__(self, workspace):
        self.workspace = Path(workspace)

    def definitions(self):
        return [
            {"name": "list_files", "description": "List the files in the workspace with their sizes.",
             "input_schema": schema({})},
            {"name": "read_file", "description": "Read a text file from the workspace.",
             "input_schema": schema({"path": {"type": "string", "description": "Workspace-relative path."}},
                                    ["path"])},
            {"name": "write_file",
             "description": "Write a text file (SVG, HTML, CSS, Markdown, CSV, JSON ...) in the workspace, "
                            "creating folders as needed and replacing an existing file.",
             "input_schema": schema({"path": {"type": "string", "description": "Workspace-relative path."},
                                     "content": {"type": "string", "description": "The whole file's text."}},
                                    ["path", "content"])},
            {"name": "view_image",
             "description": "Look at a file in the workspace as an image: PNG, JPEG, WebP, GIF, PDF (one page)"
                            + (", SVG and HTML" if previews.playwright_available() else "")
                            + ". Returns the image scaled to fit 1024 px.",
             "input_schema": schema({"path": {"type": "string", "description": "Workspace-relative path."},
                                     "page": {"type": "integer", "description": "PDF page, from 0."}}, ["path"])},
        ]

    def call(self, name, arguments):
        if name == "list_files":
            files = previews.deliverables(self.workspace)
            return text("\n".join(f"{f['path']}  ({f['size']} bytes)" for f in sorted(files, key=lambda f: f["path"]))
                        or "The workspace is empty.")
        path = inside(self.workspace, arguments.get("path"))
        if name == "write_file":
            content = arguments.get("content")
            if not isinstance(content, str):
                raise ToolError("content must be a string")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            return text(f"Wrote {path.relative_to(self.workspace.resolve()).as_posix()} ({len(content)} characters).")
        if not path.is_file():
            raise ToolError(f"no file {arguments.get('path')!r} in the workspace")
        if name == "read_file":
            data = path.read_bytes()
            try:
                value = data.decode("utf-8")
            except UnicodeDecodeError:
                raise ToolError(f"{arguments['path']} is a binary file ({len(data)} bytes); use view_image") from None
            return text(value if len(value) <= READ_LIMIT else value[:READ_LIMIT] + "\n… (truncated)")
        if name == "view_image":
            try:
                image = previews.load_image(path, arguments.get("page") or 0)
            except previews.PreviewError as exc:
                raise ToolError(str(exc)) from None
            return [previews.image_block(previews.png_bytes(image, previews.MODEL_SIDE)),
                    {"type": "text", "text": f"{arguments['path']}: {image.size[0]}x{image.size[1]} px"}]
        raise ToolError(f"unknown tool {name}")


class PythonTools:
    def __init__(self, workspace, scratch, timeout=90):
        self.workspace, self.scratch, self.timeout = Path(workspace), Path(scratch), timeout

    def definitions(self):
        tools = [{"name": "run_python",
                  "description": "Run a Python 3 script with the workspace as the working folder; files it writes "
                                 "stay in the workspace. Installed libraries: "
                                 + (", ".join(sandbox.installed_libraries()) or "the standard library only")
                                 + f". No network{'' if sandbox.network_isolation() else ' is expected'}; no package "
                                 f"installs. Time limit {self.timeout} s. Returns stdout, stderr and the files written.",
                  "input_schema": schema({"code": {"type": "string", "description": "The script."}}, ["code"])}]
        if previews.playwright_available():
            tools.append({
                "name": "render_page",
                "description": "Render an HTML or SVG file from the workspace in a browser, save the screenshot as a "
                               "PNG in the workspace and return it.",
                "input_schema": schema({
                    "path": {"type": "string", "description": "The HTML or SVG file, workspace-relative."},
                    "output": {"type": "string", "description": "PNG path to write; defaults to the file name + .png."},
                    "width": {"type": "integer", "description": "Viewport width in px (default 1280, or the SVG's)."},
                    "height": {"type": "integer",
                               "description": "Viewport height in px; when set, only that area is captured."},
                }, ["path"])})
        return tools

    def call(self, name, arguments):
        if name == "run_python":
            code = arguments.get("code")
            if not isinstance(code, str) or not code.strip():
                raise ToolError("code must be a non-empty string")
            failed, output = sandbox.run_python(code, self.workspace, self.scratch / "python", self.timeout)
            return text(output), failed
        if name == "render_page":
            source = inside(self.workspace, arguments.get("path"))
            if not source.is_file() or previews.kind(source) not in ("html", "svg"):
                raise ToolError("path must name an HTML or SVG file in the workspace")
            default = source.with_suffix(".png").relative_to(self.workspace.resolve()).as_posix()
            output = inside(self.workspace, arguments.get("output") or default)
            if output.suffix.lower() != ".png":
                raise ToolError("output must be a .png path")
            png = previews.screenshot(source, arguments.get("width"), arguments.get("height"))
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(png)
            image = previews.Image.open(output)
            relative = output.relative_to(self.workspace.resolve()).as_posix()
            return [previews.image_block(previews.png_bytes(image, previews.MODEL_SIDE)),
                    {"type": "text", "text": f"Saved {relative} ({image.size[0]}x{image.size[1]} px)."}], False
        raise ToolError(f"unknown tool {name}")


class VixlTools:
    def __init__(self, workspace):
        from evals.harness import Tools

        with VIXL_LOCK:
            self.tools = Tools(workspace)
            self.instructions = self.tools.server.instructions or ""
            self._definitions = self.tools.definitions()

    def definitions(self):
        return self._definitions

    def call(self, name, arguments):
        with VIXL_LOCK:
            failed, blocks = self.tools.call(name, arguments)
        converted = []
        for block in blocks:
            if block.get("type") == "image":
                converted.append({"type": "image", "media_type": block["source"]["media_type"],
                                  "data": block["source"]["data"]})
            else:
                converted.append({"type": "text", "text": block.get("text", "")})
        return converted, failed

    def close(self):
        with VIXL_LOCK:
            self.tools.close()


class Toolbox:
    """The tools one session can call. ``call`` returns (is_error, blocks) and never raises."""

    def __init__(self, arm, system, parts):
        self.arm, self.system, self.parts = arm, system, parts
        self.routes = {}
        for part in parts:
            for definition in part.definitions():
                self.routes[definition["name"]] = part

    def definitions(self):
        return [definition for part in self.parts for definition in part.definitions()]

    def call(self, name, arguments):
        part = self.routes.get(name)
        if part is None:
            return True, text(f"There is no tool named {name!r}. Tools: {', '.join(self.routes) or 'none'}.")
        try:
            result = part.call(name, arguments)
        except ToolError as exc:
            return True, text(str(exc))
        except Exception as exc:  # noqa: BLE001 - a broken tool call is reported to the model, never fatal
            return True, text(f"{type(exc).__name__}: {exc}")
        if isinstance(result, tuple):
            blocks, failed = result
            return bool(failed), blocks
        return False, result

    def close(self):
        for part in self.parts:
            getattr(part, "close", lambda: None)()


BARE_TOOLS = (
    "You have no tools in this session. Deliver each file inside your reply as a fenced code block whose info string "
    "is the format and then the file name, for example ```svg poster.svg or ```html page.html. Only text formats "
    "can be delivered (SVG, HTML with inline CSS, Markdown, CSV, JSON, plain text); each block is saved to the "
    "workspace exactly as written."
)


def code_tools_text(parts):
    names = ", ".join(definition["name"] for part in parts for definition in part.definitions())
    return (f"Your tools: {names}. Make files by writing them directly or with Python, and look at the results "
            "with view_image" + (" or render_page" if previews.playwright_available() else "") + ".")


def build(arm, workspace, scratch, skill=True, python_timeout=90):
    workspace, scratch = Path(workspace), Path(scratch)
    if arm == "bare":
        return Toolbox(arm, f"{BASE_SYSTEM}\n\n{BARE_TOOLS}", [])
    if arm == "code":
        parts = [FileTools(workspace), PythonTools(workspace, scratch, python_timeout)]
        return Toolbox(arm, f"{BASE_SYSTEM}\n\n{code_tools_text(parts)}", parts)
    if arm == "vixl":
        vixl = VixlTools(workspace)
        parts = [vixl, FileTools(workspace)]
        system = (f"{BASE_SYSTEM}\n\nYour tools: Vixl's design tools (the vixl_* tools) and list_files, read_file, "
                  "write_file and view_image. There is no shell or Python in this session.\n\n"
                  f"Vixl's server instructions:\n{vixl.instructions}")
        if skill and SKILL.is_file():
            system += f"\n\nThe Vixl agent skill:\n{SKILL.read_text(encoding='utf-8')}"
        return Toolbox(arm, system, parts)
    raise ValueError(f"unknown arm {arm!r}")


FENCE = re.compile(r"```([^\n`]*)\n(.*?)```", re.S)
LOOSE_SVG = re.compile(r"<svg\b.*?</svg>", re.S | re.I)
SAFE = re.compile(r"[^A-Za-z0-9._-]+")


def extract_files(reply, workspace):
    """Save the bare arm's fenced code blocks as files; return the names written."""
    workspace = Path(workspace)
    written, counts = [], {}

    def save(name, content):
        name = SAFE.sub("-", Path(name).name).strip("-.") or "output.txt"
        stem, suffix = Path(name).stem, Path(name).suffix
        candidate, n = name, 1
        while candidate in written:
            n += 1
            candidate = f"{stem}-{n}{suffix}"
        (workspace / candidate).write_text(content, encoding="utf-8")
        written.append(candidate)

    for info, body in FENCE.findall(reply or ""):
        words = info.strip().split()
        language = words[0].lower() if words else ""
        name = next((w for w in words if "." in w and Path(w).suffix.lower() in TEXT_SUFFIXES), "")
        if not name:
            suffix = LANGUAGE_SUFFIX.get(language)
            if suffix is None and body.lstrip().startswith("<svg"):
                suffix = ".svg"
            if suffix is None:
                continue
            counts[suffix] = counts.get(suffix, 0) + 1
            name = f"output{'' if counts[suffix] == 1 else '-' + str(counts[suffix])}{suffix}"
        save(name, body)
    if not written:
        loose = LOOSE_SVG.search(reply or "")
        if loose:
            save("output.svg", loose.group(0))
    return written


def describe_call(name, arguments):
    """A short, readable line for the live log."""
    shown = json.dumps(arguments, ensure_ascii=False, default=str)
    return f"{name}({shown[:300]}{'…' if len(shown) > 300 else ''})"
