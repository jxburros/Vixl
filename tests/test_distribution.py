from pathlib import Path
import tomllib


def test_source_distribution_includes_only_package_sources_and_metadata():
    root = Path(__file__).resolve().parent.parent
    config = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    includes = config["tool"]["hatch"]["build"]["targets"]["sdist"]["include"]
    assert set(includes) == {"/src/vixl", "/pyproject.toml", "/README.md", "/LICENSE"}
    assert all((root / path.lstrip("/")).exists() for path in includes)


def _package_extensions():
    import importlib.util

    location = Path(__file__).resolve().parents[1] / "distribution/package_extensions.py"
    spec = importlib.util.spec_from_file_location("package_extensions", location)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _doc_launch_lines(root):
    """`vixl mcp` command lines and MCP `args` arrays in fenced blocks of the user docs and the skill."""
    import json
    import re
    import shlex

    files = [root / "README.md", *sorted((root / "docs").rglob("*.md")), *sorted((root / "skills").rglob("*.md"))]
    for path in files:
        if "project" in path.relative_to(root).parts:
            continue
        fenced = False
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if line.lstrip().startswith("```"):
                fenced = not fenced
                continue
            if not fenced:
                continue
            where = f"{path.relative_to(root)}:{number}"
            for match in re.finditer(r'"args":\s*(\[[^\]]*\])', line):
                args = json.loads(match.group(1))
                if "mcp" in args:
                    yield where, args
            if "vixl mcp" in line and '"args"' not in line:
                command = line.split(" #", 1)[0]
                if "[" in command or "|" in command:
                    continue  # usage synopsis, not a command
                yield where, shlex.split(command, posix=True)


def test_shipped_launch_args_parse(tmp_path):
    import json
    import re
    import zipfile

    from vixl.cli import mcp_parser
    from vixl.interfaces import mcp_server

    root = Path(__file__).resolve().parent.parent
    module = _package_extensions()
    outputs = module.build(tmp_path / "dist")
    sources = []
    for output in outputs:
        with zipfile.ZipFile(output) as archive:
            if output.suffix == ".mcpb":
                manifest = json.loads(archive.read("manifest.json"))
                sources.append(("vixl.mcpb manifest.json", manifest["server"]["mcp_config"]["args"]))
            else:
                bundled = json.loads(archive.read(".mcp.json"))
                sources.append(("vixl-claude-code.zip .mcp.json", bundled["mcpServers"]["vixl"]["args"]))
    checked_in = json.loads((root / ".mcp.json").read_text(encoding="utf-8"))
    sources.append((".mcp.json", checked_in["mcpServers"]["vixl"]["args"]))
    plugin = json.loads((root / ".claude-plugin/plugin.json").read_text(encoding="utf-8"))
    pointed = json.loads((root / plugin["mcpServers"]).read_text(encoding="utf-8"))
    sources += [(f"plugin.json -> {name}", server["args"]) for name, server in pointed["mcpServers"].items()]
    documented = list(_doc_launch_lines(root))
    assert any(where.startswith("README.md") for where, _ in documented)
    sources += documented

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    for where, args in sources:
        assert "mcp" in args, where
        rest = args[args.index("mcp") + 1:]
        rest = [re.sub(r"\$\{[^}]*\}", str(workspace), item) for item in rest]
        try:
            parsed = mcp_parser().parse_args(rest)
        except Exception as error:
            raise AssertionError(f"{where}: {args} does not start the server: {error}") from error
        if not parsed.http and where in {"vixl.mcpb manifest.json", ".mcp.json"}:
            mcp_server(workspace=str(workspace), tools=parsed.tools)
    assert checked_in["mcpServers"]["vixl"]["args"] == module.launch_args(".")


def test_launch_args_reject_removed_flags():
    import pytest

    from vixl.cli import mcp_parser
    from vixl.errors import VixlError

    with pytest.raises(VixlError):
        mcp_parser().parse_args(["--workspace", ".", "--tools", "core", "--schema", "slim"])
