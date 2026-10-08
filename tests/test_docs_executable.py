"""Docs are executable: the `vixl …` commands and JSON operation blocks in docs/ and skills/ run here.

Blocks are found automatically, so a new or edited example is tested without touching this file.

Shell blocks (```bash, sh, shell, console)
    The lines that start with `vixl` run in order in one fresh temporary workspace (other lines such as pip, git or
    cd are not run). A command without shell syntax runs in-process through `vixl.cli.main`; one with pipes,
    redirects or `$(…)` runs through bash with `vixl` on PATH. The workspace holds the inputs in `SEED_FILES`, the
    repository's `docs/assets/generated/*.json` and the blocks of the same page marked `save` (below).

    A command on a document the block made with `vixl new` must succeed. Any other command is a snippet against a
    document the reader already has: it runs against a stand-in document (`STAND_IN` layers; it is the current
    document, and is copied to each `-p FILE.vixl` the block names without creating it) and may fail on context the
    snippet does not set up (a missing layer, selection or saved frame), but not with a usage error (`MISUSE`: an
    unknown command, option, field or value) or a crash.

JSON blocks (```json)
    Each block must parse (comments after `//` or `#` are allowed). Operation objects (`{"type": …}`), lists of
    them and requests with an `operations` list are validated against the operation schema, then applied in order to
    a fresh document (the request's width/height, else 1200x800) in a seeded workspace. Applying may fail only on
    context defined elsewhere (`CONTEXT_ERRORS`, a missing input file).

What does not run, and why
    - A line that is a synopsis rather than a command (`[--flag]`, `a|b` alternatives, `…`, CAPITAL placeholders).
    - Commands in `SKIP_COMMANDS` (servers, the interactive shell, the network, AI providers), commands with a URL
      argument, video and audio commands when ffmpeg is missing, and the rest of a block after a command reports
      that it needs the network (font downloads).
    - Files in `SKIP_FILES`.

Markers: an HTML comment on the last non-blank line before a fence.
    `<!-- docs-test: skip REASON -->`  do not run this block (the reason is required; keep these rare).
    `<!-- docs-test: continue -->`     run this shell block after the previous shell block of the page, in the same
                                       workspace (walkthroughs that build one document over several blocks).
    `<!-- docs-test: save FILE -->`    write this block's text to FILE in the workspace of every shell block of the
                                       page ("save this as hello-ops.json").
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from icc_helper import cmyk_profile  # noqa: E402

pytestmark = pytest.mark.docs
ROOT = Path(__file__).resolve().parent.parent
DOC_DIRS = ("docs", "skills")
SHELL_LANGS = {"bash", "sh", "shell", "console", "zsh"}
TIMEOUT = 120

SKIP_FILES = {
    "docs/product-spec.md": "the original design specification; its command sketches predate the CLI "
                            "(docs/coverage.md describes what is implemented)",
}
# First word after `vixl` and its global options -> why the command is not run.
SKIP_COMMANDS = {
    "<shell>": "starts the interactive shell",
    "mcp": "starts an MCP server that waits for a client",
    "serve": "starts the REST server",
    "view": "starts the local viewer server",
    "session": "reads requests from stdin until it closes",
    "update": "contacts the release server",
    "updates": "contacts the release server",
    "generate": "needs an image provider",
    "ai": "needs an image provider",
    "ocr": "needs an AI provider",
    "detect": "needs an AI provider",
    "models": "lists a provider's models over the network",
}
MEDIA = re.compile(r"\.(mp4|webm|mp3|wav|m4a|ogg|lrc)\b|lyric-video")
URL = re.compile(r"^https?://")
NEEDS_NETWORK = re.compile(r"download failed|check network access|ConnectError|Set \w+_API_KEY|Unknown provider", re.I)
# A failure that means the example itself is wrong, whatever document it runs against.
MISUSE = re.compile(
    r"Unknown editing command|Unknown command|unrecognized arguments|the following arguments are required|"
    r"invalid choice|expected one argument|must be one of|Unknown field|Unknown operation type|No kind of work matches|"
    r"Traceback \(most recent call last\)|Expecting (value|property name)|Unterminated string|Extra data")
# Errors that only say a JSON snippet's context is defined elsewhere.
CONTEXT_ERRORS = {
    "layer_not_found", "page_not_found", "frame_not_found", "animation_not_found", "missing_asset", "missing_file",
    "missing_image", "missing_font", "missing_variable",
}
CONTEXT_MESSAGES = re.compile(
    r"not found|unknown (layer|swatch|palette|style|symbol|page|master|pattern|brush|font|variable|animation)|"
    r"has no pages|save at least one animation frame", re.I)

# Inputs the examples name, written into every workspace (images are drawn; *.icc is a small CMYK press profile).
SEED_IMAGES = {
    "photo.jpg": (640, 480), "photo.png": (640, 480), "portrait.jpg": (480, 640), "portrait.png": (480, 640),
    "photos/portrait.jpg": (480, 640), "image.png": (400, 300), "logo.png": (256, 256), "sketch.jpg": (1600, 1000),
    "replacement.jpg": (400, 500),
}
SEED_PROFILES = ("printer.icc", "press.icc")
STAND_IN_NAME = ".stand-in.vixl"
STAND_IN_SIZE = (1200, 900)
STAND_IN = {
    "background": {"type": "solid", "color": "#203040"},
    "portrait": {"type": "add", "path": "portrait.png", "x": 100, "y": 100},
    "photo": {"type": "add", "path": "photo.png", "x": 200, "y": 80},
    "hero": {"type": "shape", "shape": "rounded-rectangle", "width": 400, "height": 260, "x": 300, "y": 300,
             "fill": "#2a9d8f"},
    "logo": {"type": "shape", "shape": "star", "width": 120, "height": 120, "x": 40, "y": 40, "fill": "#e8885c"},
    "badge": {"type": "shape", "shape": "ellipse", "width": 160, "height": 160, "x": 900, "y": 60, "fill": "#2563eb"},
    "card": {"type": "shape", "shape": "rounded-rectangle", "width": 300, "height": 400, "x": 600, "y": 200,
             "fill": "#1f2a3d"},
    "title": {"type": "text", "text": "Summer Sale", "size": 72, "color": "#ffffff", "x": 80, "y": 520},
    "headline": {"type": "text", "text": "Launch day", "size": 56, "color": "#ffffff", "x": 80, "y": 620},
    "subtitle": {"type": "text", "text": "Every weekend in July", "size": 32, "color": "#ffffff", "x": 80, "y": 700},
}

FENCE = re.compile(r"^\s*(`{3,}|~{3,})\s*([\w+-]*)")
MARKER = re.compile(r"^\s*<!--\s*docs-test:\s*(skip|continue|save)\b:?\s*(.*?)\s*-->\s*$")


@dataclass
class Block:
    path: str
    line: int
    lang: str
    body: list
    marker: tuple | None = None

    @property
    def id(self):
        return f"{self.path}:{self.line}"

    @property
    def kind(self):
        return self.marker[0] if self.marker else None


def parse(path):
    lines = path.read_text(encoding="utf-8").splitlines()
    rel = path.relative_to(ROOT).as_posix()
    found, i = [], 0
    while i < len(lines):
        match = FENCE.match(lines[i])
        if not match:
            i += 1
            continue
        fence, lang = match.groups()
        end = i + 1
        while end < len(lines) and not lines[end].strip().startswith(fence):
            end += 1
        before = next((lines[k] for k in range(i - 1, -1, -1) if lines[k].strip()), "")
        marker = MARKER.match(before)
        found.append(Block(rel, i + 1, lang.lower(), lines[i + 1:end], marker.groups() if marker else None))
        i = end + 1
    return found


def all_blocks():
    found = []
    for folder in DOC_DIRS:
        for path in sorted((ROOT / folder).rglob("*.md")):
            if path.relative_to(ROOT).as_posix() not in SKIP_FILES:
                found.extend(parse(path))
    return found


def shell_commands(block):
    """The block's `vixl` command lines, with continuations joined and `$ ` prompts removed."""
    joined, current = [], ""
    for raw in block.body:
        text = raw.rstrip()
        if text.endswith("\\"):
            current += text[:-1].strip() + " "
            continue
        joined.append((current + text.strip()).strip())
        current = ""
    joined.append(current.strip())
    commands = []
    for text in joined:
        if text.startswith("$ "):
            text = text[2:]
        if re.match(r"vixl(\s|$)", text):
            commands.append(text)
    return commands


ALL = all_blocks()
SHELL_BLOCKS = [b for b in ALL if b.lang in SHELL_LANGS and shell_commands(b)]
JSON_BLOCKS = [b for b in ALL if b.lang == "json"]


def unquoted(command):
    text = re.sub(r"'[^']*'|\"(?:\\.|[^\"\\])*\"", "''", command)
    return re.split(r"(?:^|\s)#", text, maxsplit=1)[0]


def synopsis(command):
    """True when the line documents syntax instead of being a command to run."""
    text = unquoted(command)
    return bool(re.search(r"\[-|\[[A-Z]|…|\.\.\.|\w\|\w|(?<![\w@#$/.-])[A-Z][A-Z_]+\b(?![.\w])|(?<=\s)[A-Z](?=\s|$)",
                          text))


def without_comment(command):
    """The command without its trailing comment: a `#` that starts a word outside quotes, as bash reads it
    (shlex's comment handling also cuts `petals=#f2a1b8`)."""
    quote = None
    for i, c in enumerate(command):
        if quote:
            if c == quote:
                quote = None
        elif c in "'\"":
            quote = c
        elif c == "#" and (i == 0 or command[i - 1].isspace()):
            return command[:i].rstrip()
    return command


def words_of(command):
    try:
        return shlex.split(without_comment(command))
    except ValueError:
        return command.split()


def subcommand(words):
    k = 1
    while k < len(words) and words[k].startswith("-"):
        k += 2 if words[k] in ("-p", "--project", "--workspace", "--max-memory", "--max-pixels") else 1
    return words[k] if k < len(words) else "<shell>"


def skip_reason(command):
    if synopsis(command):
        return "a synopsis, not a command"
    words = words_of(command)
    name = subcommand(words)
    if name == "<shell>" and ("--version" in words or "--help" in words or "-h" in words):
        return None
    if name in SKIP_COMMANDS:
        return SKIP_COMMANDS[name]
    if any(URL.match(word) for word in words[1:]) and name in ("import", "add", "layer", "font", "fonts", "frame"):
        return "downloads from the network"
    if MEDIA.search(command) and shutil.which("ffmpeg") is None:
        return "needs ffmpeg"
    return None


def project_argument(words):
    for flag in ("-p", "--project"):
        if flag in words[:-1]:
            return words[words.index(flag) + 1]
    return None


def shell_syntax(command):
    return bool(re.search(r"[|<>;&`*?]|\$\(|\$\{?\w", unquoted(command)))


# ---------------------------------------------------------------- workspace


def seed(workspace, page):
    from PIL import Image, ImageDraw

    generated = workspace / "docs" / "assets" / "generated"
    generated.mkdir(parents=True)
    for source in (ROOT / "docs" / "assets" / "generated").glob("*.json"):
        shutil.copy(source, generated / source.name)
    for name, size in SEED_IMAGES.items():
        image = Image.new("RGB", size, "#8aa4c8")
        draw = ImageDraw.Draw(image)
        draw.ellipse([size[0] * 0.2, size[1] * 0.2, size[0] * 0.8, size[1] * 0.8], fill="#d9734e", outline="#111111",
                     width=6)
        draw.rectangle([0, size[1] * 0.75, size[0], size[1]], fill="#2d4a3e")
        (workspace / name).parent.mkdir(parents=True, exist_ok=True)
        image.save(workspace / name)
    for name in SEED_PROFILES:
        (workspace / name).write_bytes(cmyk_profile())
    for block in ALL:
        if block.path == page and block.kind == "save":
            target = workspace / block.marker[1]
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("\n".join(block.body) + "\n", encoding="utf-8")


def build_stand_in(workspace):
    from vixl import Project

    with contextlib.chdir(workspace):
        project = Project(*STAND_IN_SIZE, "#ffffff", workspace=str(workspace))
        project.apply([{**spec, "name": name} for name, spec in STAND_IN.items()])
        project.save(workspace / STAND_IN_NAME)
    (workspace / ".vixl-session.json").write_text(json.dumps({"project": str(workspace / STAND_IN_NAME)}))


@pytest.fixture
def offline(tmp_path, monkeypatch):
    """No provider keys, no updater, a private HOME, and any network request fails at once."""
    for key in list(os.environ):
        if key.endswith("_API_KEY") or key.startswith("VIXL_"):
            monkeypatch.delenv(key)
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("VIXL_NO_UPDATE", "1")
    for key in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY", "all_proxy"):
        monkeypatch.setenv(key, "http://127.0.0.1:9")
    for key in ("NO_PROXY", "no_proxy"):
        monkeypatch.delenv(key, raising=False)
    shim = tmp_path / "bin"
    shim.mkdir()
    (shim / "vixl").write_text(f'#!/bin/sh\nexec "{sys.executable}" -m vixl "$@"\n', encoding="utf-8")
    (shim / "vixl").chmod(0o755)
    monkeypatch.setenv("PATH", f"{shim}{os.pathsep}{os.environ.get('PATH', '')}")
    monkeypatch.setenv("PYTHONPATH", os.pathsep.join(filter(None, [str(ROOT / "src"), os.environ.get("PYTHONPATH")])))
    return tmp_path


def run(command, workspace):
    """(exit code, stdout + stderr) of one documented command."""
    if shell_syntax(command):
        result = subprocess.run(["bash", "-o", "pipefail", "-c", command], cwd=workspace, capture_output=True,
                                text=True, timeout=TIMEOUT, stdin=subprocess.DEVNULL)
        return result.returncode, result.stdout + result.stderr
    from vixl.cli import main

    streams = [io.TextIOWrapper(io.BytesIO(), encoding="utf-8") for _ in range(2)]
    saved = sys.stdin, sys.stdout, sys.stderr
    sys.stdin, sys.stdout, sys.stderr = io.TextIOWrapper(io.BytesIO(b""), encoding="utf-8"), *streams
    try:
        with contextlib.chdir(workspace):
            try:
                code = main(words_of(command)[1:])
            except SystemExit as exc:  # --help
                code = exc.code if isinstance(exc.code, int) else 0
    finally:
        sys.stdin, sys.stdout, sys.stderr = saved
    output = []
    for stream in streams:
        stream.flush()
        output.append(stream.buffer.getvalue().decode("utf-8", "replace"))
    return code or 0, "".join(output)


def chain(block):
    """The block, after the earlier blocks of its page that it continues."""
    page = [b for b in SHELL_BLOCKS if b.path == block.path]
    position = page.index(block)
    blocks = [block]
    while blocks[0].kind == "continue" and position > 0:
        position -= 1
        blocks.insert(0, page[position])
    return blocks


def execute(commands, workspace):
    """Run (where, command) pairs in one workspace; return (failure message or None, commands run, skip reasons)."""
    build_stand_in(workspace)
    created, current_created = set(), False  # documents made here with `vixl new`
    ran, skipped = 0, set()
    for where, command in commands:
        reason = skip_reason(command)
        if reason:
            skipped.add(reason)
            continue
        words = words_of(command)
        document = project_argument(words)
        if subcommand(words) == "new":
            output_path = next((words[i + 1] for i, w in enumerate(words[:-1]) if w in ("-o", "--out")), None)
            created.add(os.path.normpath(output_path or ""))
            current_created = strict = True
        elif document:
            strict = os.path.normpath(document) in created
            if not strict and document.endswith(".vixl") and not (workspace / document).exists():
                (workspace / document).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy(workspace / STAND_IN_NAME, workspace / document)
        else:
            strict = current_created
        code, output = run(command, workspace)
        ran += 1
        if code == 0:
            continue
        if NEEDS_NETWORK.search(output):
            skipped.add("needs the network (the rest of the block depends on it)")
            break
        if not strict and not MISUSE.search(output):
            continue
        return (f"{where}: `{command}` exited {code}{'' if strict else ' with a usage error'}:\n{output[-3000:]}",
                ran, skipped)
    return None, ran, skipped


@pytest.mark.parametrize("block", SHELL_BLOCKS, ids=lambda b: b.id)
def test_shell_block_runs(block, offline):
    if os.name == "nt":
        pytest.skip("the examples are POSIX shell")
    if block.kind == "skip":
        pytest.skip(block.marker[1])
    workspace = offline / "work"
    workspace.mkdir()
    seed(workspace, block.path)
    failure, ran, skipped = execute([(part.id, c) for part in chain(block) for c in shell_commands(part)], workspace)
    if failure:
        pytest.fail(failure)
    if not ran:
        pytest.skip("; ".join(sorted(skipped)))


@pytest.mark.skipif(os.name == "nt", reason="the examples are POSIX shell")
def test_the_runner_catches_stale_examples(offline):
    """The two documentation bugs this test was written for (#373, #343), and a stale option in a snippet."""
    cases = {
        "#373": ["vixl new 1920x1080 -o deck.vixl",
                 "vixl -p deck.vixl shape --shape rectangle --name band --width 1920 --height 24 --fill '#1d3557'"],
        "#343": ["vixl new 640x360 -o lyric.vixl", "vixl -p lyric.vixl text add '${title} / ${artist}' --name intro"],
        "snippet": ["vixl blend portrait multiplyy"],
    }
    for name, commands in cases.items():
        workspace = offline / name.strip("#")
        workspace.mkdir()
        seed(workspace, None)
        failure, _, _ = execute([(name, command) for command in commands], workspace)
        assert failure and name in failure, (name, failure)
    workspace = offline / "fine"
    workspace.mkdir()
    seed(workspace, None)
    assert execute([("ok", "vixl align logo center"), ("ok", "vixl opacity missing-layer 0.5")], workspace)[0] is None


# ---------------------------------------------------------------- JSON


def strip_comments(text):
    """Remove // and # comments outside JSON strings."""
    out, in_string, i = [], False, 0
    while i < len(text):
        c = text[i]
        if in_string:
            out.append(c)
            if c == "\\" and i + 1 < len(text):
                out.append(text[i + 1])
                i += 2
                continue
            in_string = c != '"'
        elif c == '"':
            in_string = True
            out.append(c)
        elif c == "#" or text.startswith("//", i):
            while i < len(text) and text[i] != "\n":
                i += 1
            continue
        else:
            out.append(c)
        i += 1
    return "".join(out)


def json_values(text):
    decoder, text, values, i = json.JSONDecoder(), strip_comments(text), [], 0
    while True:
        while i < len(text) and text[i] in " \t\r\n,":
            i += 1
        if i >= len(text):
            return values
        value, i = decoder.raw_decode(text, i)
        values.append(value)


def operations_in(values):
    """The operations a block holds and the canvas size its request names, if any."""
    operations, size = [], None
    for value in values:
        if isinstance(value, dict) and isinstance(value.get("operations"), list) and "type" not in value:
            operations.extend(value["operations"])
            if isinstance(value.get("width"), int) and isinstance(value.get("height"), int):
                size = (value["width"], value["height"])
        elif isinstance(value, dict) and isinstance(value.get("type"), str):
            operations.append(value)
        elif isinstance(value, list) and value and all(isinstance(v, dict) and "type" in v for v in value):
            operations.extend(value)
    return operations, size


@pytest.mark.parametrize("block", JSON_BLOCKS, ids=lambda b: b.id)
def test_json_block_validates_and_applies(block, offline, monkeypatch):
    from vixl import Project
    from vixl.errors import VixlError
    from vixl.schema import validate_operation

    if block.kind == "skip":
        pytest.skip(block.marker[1])
    text = "\n".join(block.body)
    try:
        values = json_values(text)
    except json.JSONDecodeError as exc:
        if "…" in text:
            pytest.skip("an elided example (…)")
        pytest.fail(f"{block.id}: not valid JSON: {exc}")
    operations, size = operations_in(values)
    if not operations:
        pytest.skip("not an operation block")
    for index, operation in enumerate(operations):
        try:
            validate_operation(operation, index=index)
        except VixlError as exc:
            pytest.fail(f"{block.id}: operations[{index}] {json.dumps(operation)[:200]}\n{exc.code}: {exc}")
    workspace = offline / "work"
    workspace.mkdir()
    seed(workspace, block.path)
    monkeypatch.chdir(workspace)
    project = Project(*(size or (1200, 800)), "#ffffff", workspace=str(workspace))
    try:
        project.apply(operations)
    except FileNotFoundError:
        pass  # a placeholder input path (assets/….png) the reader supplies
    except VixlError as exc:
        if exc.code not in CONTEXT_ERRORS and not CONTEXT_MESSAGES.search(str(exc)):
            pytest.fail(f"{block.id}: applying the block to a fresh document failed\n{exc.code}: {exc}")


def test_examples_are_found_and_markers_are_well_formed():
    """Guards the parser: if it stopped finding blocks, the tests above would silently vanish."""
    assert len(SHELL_BLOCKS) > 100 and sum(len(shell_commands(b)) for b in SHELL_BLOCKS) > 500
    assert len(JSON_BLOCKS) > 80
    for block in ALL:
        if block.kind in ("skip", "save"):
            assert block.marker[1], f"{block.id}: docs-test {block.kind} needs a {block.kind == 'skip' and 'reason' or 'file name'}"
        if block.kind == "continue":
            assert block in SHELL_BLOCKS and chain(block)[0] is not block, f"{block.id}: nothing to continue"
    for folder in DOC_DIRS:
        for path in (ROOT / folder).rglob("*.md"):
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if "docs-test" in line and line.strip().startswith("<!--"):
                    assert MARKER.match(line), f"{path.relative_to(ROOT)}:{number}: unknown docs-test marker"
