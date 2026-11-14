"""Write the `server.json` that lists Vixl in the official MCP registry (registry.modelcontextprotocol.io).

    python distribution/mcp_registry.py                 # print the entry for the source version
    python distribution/mcp_registry.py --out server.json
    python distribution/mcp_registry.py --version 0.35.0

The entry is generated, like the `.mcpb` manifest, so its two version fields cannot drift from the release. The
registry accepts a PyPI package only when the package's README (its PyPI description) contains the line
`mcp-name: NAME`; README.md carries it in a comment, and `tests/test_install_docs.py` keeps the two in step.
A client that installs from the registry runs `uvx vixl-engine==VERSION mcp --workspace DIR`, which needs the
`vixl-engine` console script (pyproject.toml), so the first version that can be listed is the first one published
with that script.

Needs no installed package: the release workflow runs it from a bare checkout.
"""

import argparse
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "https://static.modelcontextprotocol.io/schemas/2025-12-11/server.schema.json"
NAME = "io.github.jxburros/vixl"  # the io.github.OWNER/ namespace is what GitHub OIDC from this repository may publish
PACKAGE = "vixl-engine"
DESCRIPTION = "A design engine for AI agents: layered, editable designs, checked before export."


def source_version(root=ROOT):
    text = (root / "src/vixl/__init__.py").read_text(encoding="utf-8")
    return re.search(r'^__version__ = "([^"]+)"$', text, flags=re.MULTILINE).group(1)


def entry(version=None):
    version = version or source_version()
    return {
        "$schema": SCHEMA,
        "name": NAME,
        "title": "Vixl",
        "description": DESCRIPTION,
        "repository": {"url": "https://github.com/jxburros/Vixl", "source": "github"},
        "websiteUrl": "https://github.com/jxburros/Vixl",
        "version": version,
        "packages": [{
            "registryType": "pypi",
            "registryBaseUrl": "https://pypi.org",
            "identifier": PACKAGE,
            "version": version,
            "runtimeHint": "uvx",
            "transport": {"type": "stdio"},
            "packageArguments": [
                {"type": "positional", "value": "mcp"},
                {"type": "named", "name": "--workspace", "format": "filepath", "isRequired": True, "default": ".",
                 "description": "Existing folder Vixl may read and edit"},
            ],
        }],
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--version", help="release version (default: the source version)")
    parser.add_argument("--out", type=Path, help="write here instead of printing")
    a = parser.parse_args(argv)
    text = json.dumps(entry(a.version), indent=2) + "\n"
    if a.out:
        a.out.write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
