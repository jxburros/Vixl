"""Build a Claude Code plugin ZIP and a Claude Desktop MCPB (requires installed uv)."""

import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def package_spec(version=None):
    """The exact PyPI release. A published PyPI version cannot be replaced, unlike a tag archive."""
    if version is None:
        from vixl import __version__ as version
    return f"vixl-engine=={version}"


def published_version():
    """The newest release on PyPI, which the checked-in .mcp.json and the documented install commands pin."""
    return json.loads((ROOT / "distribution/published.json").read_text(encoding="utf-8"))["version"]


def launch_args(workspace, version=None):
    """uvx arguments that start the MCP server; the bundle and .mcp.json both use them."""
    return ["--from", package_spec(version), "vixl", "mcp", "--workspace", workspace]


def build(output=None):
    from vixl import __version__

    output = Path(output or ROOT / "dist")
    output.mkdir(parents=True, exist_ok=True)
    manifest = {
        "manifest_version": "0.3",
        "name": "vixl",
        "display_name": "Vixl",
        "icon": "icon.png",
        "version": __version__,
        "description": "A design engine for AI agents. Real layers, live review, your brands, checked before export.",
        "author": {"name": "Vixl contributors"},
        "homepage": "https://github.com/jxburros/Vixl",
        "user_config": {
            "workspace": {
                "type": "directory",
                "title": "Design workspace",
                "description": "Folder Vixl may read and edit",
                "required": True,
            }
        },
        "server": {
            "type": "python",
            "entry_point": "server.py",
            "mcp_config": {
                "command": "uvx",
                "args": launch_args("${user_config.workspace}"),
            },
        },
        "compatibility": {"platforms": ["darwin", "win32", "linux"]},
    }
    with zipfile.ZipFile(output / "vixl.mcpb", "w", zipfile.ZIP_DEFLATED) as archive:
        archive.write(ROOT / "assets/brand/ripple/Icons/app-icon-dark.png", "icon.png")
        archive.writestr("manifest.json", json.dumps(manifest, indent=2) + "\n")
        archive.writestr("server.py", "from vixl.cli import main\nmain()\n")
        for path in sorted((ROOT / "skills/vixl").rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(ROOT))
        archive.writestr(
            "README.md",
            "Install uv first. Open vixl.mcpb in Claude Desktop and choose a workspace. "
            "The first launch installs this exact vixl-engine version from PyPI. "
            "The bundled skill is reference material; Desktop uses the MCP server instructions.\n",
        )
    with zipfile.ZipFile(output / "vixl-claude-code.zip", "w", zipfile.ZIP_DEFLATED) as archive:
        archive.write(ROOT / ".claude-plugin/plugin.json", ".claude-plugin/plugin.json")
        # The checked-in .mcp.json follows the newest published release (scripts/published_pins.py); a bundle
        # ships with its own release, so it pins that.
        server = json.loads((ROOT / ".mcp.json").read_text(encoding="utf-8"))
        server["mcpServers"]["vixl"]["args"] = launch_args(".")
        archive.writestr(".mcp.json", json.dumps(server, indent=2) + "\n")
        for path in sorted((ROOT / "skills/vixl").rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(ROOT))
    return [output / "vixl.mcpb", output / "vixl-claude-code.zip"]


if __name__ == "__main__":
    for path in build():
        print(path)
