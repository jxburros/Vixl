"""Fail when a GitHub Actions `uses:` reference is not pinned to a full commit SHA.

Checks every workflow in .github/workflows and the composite action.yml. A tag or branch can be moved to other code
after review; a 40-hex commit cannot. Local actions (`./path`) and `docker://` images are not GitHub refs and are skipped.

    python scripts/check_workflow_pins.py [repository root]
"""

from pathlib import Path
import re
import sys

USES = re.compile(r"^\s*(?:-\s*)?uses:\s*(['\"]?)([^\s'\"#]+)\1")
PINNED = re.compile(r"@[0-9a-f]{40}$")


def files(root):
    root = Path(root)
    return [*sorted((root / ".github" / "workflows").glob("*.y*ml")), root / "action.yml"]


def unpinned(root):
    """(path, line number, reference) for every `uses:` that is not a full commit SHA."""
    found = []
    for path in files(root):
        if not path.is_file():
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            match = USES.match(line)
            if not match:
                continue
            reference = match.group(2)
            if reference.startswith(("./", "docker://")):
                continue
            if not PINNED.search(reference):
                found.append((path, number, reference))
    return found


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    root = Path(argv[0]) if argv else Path(__file__).resolve().parents[1]
    problems = unpinned(root)
    for path, number, reference in problems:
        print(f"{path.relative_to(root)}:{number}: {reference} is not pinned to a 40-character commit SHA")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
