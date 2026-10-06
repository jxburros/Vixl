from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent.parent


def test_coverage_page_has_a_row_for_the_latest_release():
    """docs/coverage.md records the release each area arrived in; a release without a row is stale."""
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    released = re.findall(r"^## (\d+)\.(\d+)(?:\.\d+)?\s*$", changelog, flags=re.MULTILINE)  # skips "Unreleased"
    assert released, "CHANGELOG.md has no version headings"
    major, minor = released[0]
    coverage = (ROOT / "docs" / "coverage.md").read_text(encoding="utf-8")
    rows = set(re.findall(r"^\| [^|]*\((\d+\.\d+)\) \|", coverage, flags=re.MULTILINE))
    assert f"{major}.{minor}" in rows, f"docs/coverage.md has no '({major}.{minor})' row for the latest release"
