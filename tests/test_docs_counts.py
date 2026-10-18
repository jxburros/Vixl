"""Counts quoted in the docs match the code, so a catalog that grows does not leave a stale number behind."""

import contextlib
import io
import json
import re
from pathlib import Path

from vixl.cli import main
from vixl.schema import operation_schema

ROOT = Path(__file__).resolve().parent.parent


def _json(*args):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        try:
            main(["--json", *args])
        except SystemExit:
            pass
    return json.loads(out.getvalue())


def _actual():
    from vixl.artistic import ARTISTIC_DEFAULTS

    return {
        "operation types": len(operation_schema()["properties"]["operations"]["items"]["oneOf"]),
        "named sizes": len(_json("sizes")["sizes"]),
        "layouts": len(_json("layouts")["layouts"]),
        "templates": len(_json("template", "list")["names"]),
        "palettes": len(_json("palette", "list")["names"]),
        "design styles": _json("styles", "list")["count"],
        "looks": len(_json("looks")["looks"]),
        "brushes": len(_json("brushes")["brushes"]),
        "artistic filters": len(ARTISTIC_DEFAULTS),
        "organic presets": len(_json("organics")["presets"]),
    }


def test_coverage_counts_match_the_catalogs():
    text = (ROOT / "docs" / "reference" / "coverage.md").read_text(encoding="utf-8")
    line = re.search(r"^Counts at .*?(?=\n\n)", text, flags=re.S | re.M).group(0).replace("\n", " ")
    quoted = {name: int(number) for number, name in re.findall(r"\*\*(\d+)\*\* ([a-z ]+?)(?=[,.]| and )", line)}
    assert quoted == _actual(), "docs/reference/coverage.md counts are stale; update the 'Counts at' line"


def test_named_size_counts_elsewhere_match():
    expected = _actual()["named sizes"]
    stale = []
    for path in [ROOT / "README.md", *(ROOT / "docs").rglob("*.md"), *(ROOT / "skills").rglob("*.md")]:
        if path.name in ("CHANGELOG.md", "implementation-plan.md") or path.name == "coverage.md":
            continue
        for number in re.findall(r"\b(\d+) (?:named sizes|print, social)", path.read_text(encoding="utf-8")):
            if int(number) != expected:
                stale.append(f"{path.relative_to(ROOT)}: {number}")
    assert not stale, f"docs quote a named-size count other than {expected}: {stale}"


def test_tool_list_size_quoted_in_docs_matches_the_baseline():
    baseline = json.loads((ROOT / "tests" / "mcp_surface_baseline.json").read_text(encoding="utf-8"))
    chars = baseline["servers"]["default"]["total_chars"]
    for name in ("README.md", "docs/reference/interfaces.md"):
        text = (ROOT / name).read_text(encoding="utf-8")
        quoted = int(re.search(r"about ([\d,]+) characters of tool list", text).group(1).replace(",", ""))
        assert abs(quoted - chars) <= 150, f"{name} quotes {quoted} characters; the tool list is {chars}"
