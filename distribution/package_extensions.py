"""Build a Claude Code plugin ZIP and a Claude Desktop MCPB (requires installed uv)."""

import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]


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
        "description": "Editable design documents with live review and workspace brands.",
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
                "args": [
                    "--from",
                    f"https://github.com/jxburros/Vixl/archive/refs/tags/v{__version__}.tar.gz",
                    "vixl",
                    "mcp",
                    "--workspace",
                    "${user_config.workspace}",
                    "--tools",
                    "core",
                    "--schema",
                    "slim",
                ],
            },
        },
        "compatibility": {"platforms": ["darwin", "win32", "linux"]},
    }
    with zipfile.ZipFile(output / "vixl.mcpb", "w", zipfile.ZIP_DEFLATED) as archive:
        archive.write(ROOT / "assets/brand/digital-shift/Icons/app-icon-dark.png", "icon.png")
        archive.writestr("manifest.json", json.dumps(manifest, indent=2) + "\n")
        archive.writestr("server.py", "from vixl.cli import main\nmain()\n")
        for path in sorted((ROOT / "skills/vixl").rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(ROOT))
        archive.writestr(
            "README.md",
            "Install uv first. Open vixl.mcpb in Claude Desktop and choose a workspace. "
            "The first launch installs the versioned GitHub source release; PyPI setup is not required. "
            "The bundled skill is reference material; Desktop uses the MCP server instructions.\n",
        )
    with zipfile.ZipFile(output / "vixl-claude-code.zip", "w", zipfile.ZIP_DEFLATED) as archive:
        for relative in (".claude-plugin/plugin.json", ".mcp.json"):
            archive.write(ROOT / relative, relative)
        for path in sorted((ROOT / "skills/vixl").rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(ROOT))
    return [output / "vixl.mcpb", output / "vixl-claude-code.zip"]


if __name__ == "__main__":
    for path in build():
        print(path)
