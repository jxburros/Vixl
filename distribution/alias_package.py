"""Write the source of `vixl`, the PyPI meta-package that makes `pip install vixl` work (#753).

    python distribution/alias_package.py --out build/alias      # then: python -m build build/alias

It holds no code: it depends on `vixl-engine` at exactly its own version and passes the `pdf`, `server` and
`anthropic` extras through, so `pip install 'vixl[server]'` means `pip install 'vixl-engine[server]'`. The project
is generated, like the agent bundles, so its version cannot drift from the release. Publishing it needs the `vixl`
name on PyPI (docs/reference/releases.md, "The `vixl` alias on PyPI").

Needs no installed package: the release workflow runs it from a bare checkout.
"""

import argparse
import json
from pathlib import Path
import re
import shutil
import sys
import tomllib

ROOT = Path(__file__).resolve().parents[1]
NAME = "vixl"
ENGINE = "vixl-engine"
EXTRAS = ("pdf", "server", "anthropic")
README = """# vixl

This package installs [`vixl-engine`](https://pypi.org/project/vixl-engine/), the Vixl design engine for AI agents,
at the same version. It contains no code of its own; the command and the Python import are both `vixl`.

```bash
python -m pip install vixl          # the same as: python -m pip install vixl-engine
vixl --version
```

Documentation, source and the licence terms (PolyForm Small Business License 1.0.0; source-available, not open
source): <https://github.com/jxburros/Vixl>.
"""


def source_version(root=ROOT):
    text = (root / "src/vixl/__init__.py").read_text(encoding="utf-8")
    return re.search(r'^__version__ = "([^"]+)"$', text, flags=re.MULTILINE).group(1)


def pyproject(version, root=ROOT):
    source = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    engine = source["project"]
    extras = [extra for extra in EXTRAS if extra in engine["optional-dependencies"]]
    quoted = json.dumps  # TOML basic strings and JSON strings agree for this content
    lines = [
        "[build-system]",
        f"requires = {quoted(source['build-system']['requires'])}",
        'build-backend = "hatchling.build"',
        "",
        "[project]",
        f"name = {quoted(NAME)}",
        f"version = {quoted(version)}",
        f"description = {quoted('Installs vixl-engine, the Vixl design engine for AI agents (import and command: vixl).')}",
        'readme = "README.md"',
        f"license = {quoted(engine['license'])}",
        'license-files = ["LICENSE"]',
        f"requires-python = {quoted(engine['requires-python'])}",
        f"dependencies = [{quoted(f'{ENGINE}=={version}')}]",
        "",
        "[project.optional-dependencies]",
        *(f"{extra} = [{quoted(f'{ENGINE}[{extra}]=={version}')}]" for extra in extras),
        "",
        "[project.urls]",
        *(f"{key} = {quoted(value)}" for key, value in engine["urls"].items()),
        "",
        "# No modules: the wheel carries metadata only.",
        "[tool.hatch.build.targets.wheel]",
        "bypass-selection = true",
        "",
        "[tool.hatch.build.targets.sdist]",
        'include = ["/README.md", "/LICENSE", "/pyproject.toml"]',
        "",
    ]
    return "\n".join(lines)


def write(output, version=None, root=ROOT):
    version = version or source_version(root)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    (output / "pyproject.toml").write_text(pyproject(version, root), encoding="utf-8")
    (output / "README.md").write_text(README, encoding="utf-8")
    shutil.copy(root / "LICENSE", output / "LICENSE")
    return output


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, required=True, help="directory to write the project into")
    parser.add_argument("--version", help="release version (default: the source version)")
    a = parser.parse_args(argv)
    print(write(a.out, a.version))
    return 0


if __name__ == "__main__":
    sys.exit(main())
