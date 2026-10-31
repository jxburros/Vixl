"""Keep the install pins on the newest *published* release.

The source version (``src/vixl/__init__.py``) advances on every change to main, days before PyPI has it. The
commands a new user copies, and the repository's own ``.mcp.json``, must name a version that exists, so they follow
``distribution/published.json`` instead:

    python scripts/published_pins.py              # check every pin agrees with published.json (offline)
    python scripts/published_pins.py --online     # also check PyPI has the version and the release tag exists
    python scripts/published_pins.py --set 0.34.0 # record a published version and rewrite every pin
    python scripts/published_pins.py --latest     # the same, with the newest version PyPI reports

Run ``--latest`` with each version bump (docs/reference/releases.md). It never moves a pin past the source version.
"""

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
RECORD = "distribution/published.json"
PACKAGE = "vixl-engine"
REPOSITORY = "https://github.com/jxburros/Vixl"
VERSION = r"\d+\.\d+\.\d+"

# (file, pattern): the first group of each pattern is a pinned version; every match must agree.
PINS = (
    (".mcp.json", rf'"{PACKAGE}==({VERSION})"'),
    ("README.md", rf"uvx --from {PACKAGE}==({VERSION}) "),
    ("docs/getting-started.md", rf"pip install '{PACKAGE}==({VERSION})'"),
    ("docs/guides/automation/ci.md", rf"jxburros/Vixl@v({VERSION})\b"),
    ("docs/guides/automation/ci.md", rf"A tag such as `v({VERSION})`"),
    ("docs/guides/automation/ci.md", rf"<40-character-sha>  # v({VERSION})`"),
)


def key(version):
    return tuple(int(part) for part in version.split("."))


def published(root=ROOT):
    return json.loads((root / RECORD).read_text(encoding="utf-8"))["version"]


def source(root=ROOT):
    text = (root / "src/vixl/__init__.py").read_text(encoding="utf-8")
    return re.search(rf'^__version__ = "({VERSION})"$', text, flags=re.MULTILINE).group(1)


def found(root=ROOT):
    """Every pin as ``(file, pattern, [versions])``."""
    return [(name, pattern, re.findall(pattern, (root / name).read_text(encoding="utf-8"))) for name, pattern in PINS]


def problems(root=ROOT):
    """What is wrong with the pins, offline: a missing pin, a pin that disagrees with published.json, or a
    published version ahead of the source."""
    version = published(root)
    result = []
    if key(version) > key(source(root)):
        result.append(f"{RECORD} names {version}, ahead of the source version {source(root)}")
    for name, pattern, versions in found(root):
        if not versions:
            result.append(f"{name}: no pin matches {pattern!r}")
        result += [f"{name}: pins {pin}, but {RECORD} names {version}" for pin in versions if pin != version]
    return result


def online_problems(version):
    """The version must be installable from PyPI and its release tag must exist (the CI action pin uses it)."""
    result = []
    try:
        with urllib.request.urlopen(f"https://pypi.org/pypi/{PACKAGE}/{version}/json", timeout=30) as response:
            if response.status != 200:
                result.append(f"PyPI answered {response.status} for {PACKAGE} {version}")
    except urllib.error.HTTPError as error:
        result.append(f"PyPI has no {PACKAGE} {version} (HTTP {error.code})")
    tags = subprocess.run(["git", "ls-remote", "--tags", REPOSITORY, f"refs/tags/v{version}"],
                          capture_output=True, text=True, timeout=60)
    if tags.returncode != 0 or not tags.stdout.strip():
        result.append(f"{REPOSITORY} has no tag v{version}")
    return result


def latest_on_pypi():
    with urllib.request.urlopen(f"https://pypi.org/pypi/{PACKAGE}/json", timeout=30) as response:
        return json.load(response)["info"]["version"]


def set_version(version, root=ROOT):
    """Record ``version`` as published and rewrite every pin to it."""
    if not re.fullmatch(VERSION, version):
        raise SystemExit(f"Not a release version: {version}")
    if key(version) > key(source(root)):
        raise SystemExit(f"{version} is ahead of the source version {source(root)}")
    (root / RECORD).write_text(json.dumps({"package": PACKAGE, "version": version}, indent=2) + "\n",
                               encoding="utf-8")
    for name, pattern in PINS:
        path = root / name
        text = path.read_text(encoding="utf-8")

        def replace(match):
            start, end = match.span(1)
            whole = match.group(0)
            return whole[:start - match.start()] + version + whole[end - match.start():]

        path.write_text(re.sub(pattern, replace, text), encoding="utf-8")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--set", metavar="VERSION", help="record a published version and rewrite every pin")
    group.add_argument("--latest", action="store_true", help="record the newest version on PyPI")
    parser.add_argument("--online", action="store_true", help="also check PyPI and the release tag")
    parser.add_argument("--root", type=Path, default=ROOT, help=argparse.SUPPRESS)
    a = parser.parse_args(argv)
    if a.set or a.latest:
        version = a.set or latest_on_pypi()
        if a.latest and key(version) > key(source(a.root)):
            version = published(a.root)
        set_version(version, a.root)
        print(f"Install pins follow {PACKAGE} {version}")
    issues = problems(a.root)
    if a.online and not issues:
        issues = online_problems(published(a.root))
    for issue in issues:
        print(issue, file=sys.stderr)
    return 1 if issues else 0


if __name__ == "__main__":
    sys.exit(main())
