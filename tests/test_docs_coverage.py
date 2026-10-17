from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent.parent


def test_coverage_page_has_a_row_for_the_latest_release():
    """docs/reference/coverage.md records the release each area arrived in; a release without a row is stale."""
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    released = re.findall(r"^## (\d+)\.(\d+)(?:\.\d+)?\s*$", changelog, flags=re.MULTILINE)  # skips "Unreleased"
    assert released, "CHANGELOG.md has no version headings"
    major, minor = released[0]
    coverage = (ROOT / "docs" / "reference" / "coverage.md").read_text(encoding="utf-8")
    rows = set(re.findall(r"^\| [^|]*\((\d+\.\d+)\) \|", coverage, flags=re.MULTILINE))
    assert f"{major}.{minor}" in rows, f"docs/reference/coverage.md has no '({major}.{minor})' row for the latest release"


PERSONAL_PATH = re.compile(
    r"[A-Za-z]:\\{1,2}Users\\{1,2}(?!(?:you|USERNAME)\b)\w+"
    r"|/(?:home|Users)/(?!(?:you|user)\b)\w+/"
)


def test_no_personal_paths():
    """Examples use C:\\Users\\you or /home/you, never a path copied from a real machine."""
    files = [ROOT / "README.md", ROOT / "CONTRIBUTING.md", *ROOT.glob("docs/**/*.md"), *ROOT.glob("skills/**/*.md")]
    # The implementation plan quotes the offending path from the issue that removed it.
    files = [path for path in files if path.name != "implementation-plan.md"]
    hits = [
        f"{path.relative_to(ROOT)}:{number}: {match.group(0)}"
        for path in files
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        for match in PERSONAL_PATH.finditer(line)
    ]
    assert not hits, "personal paths in docs: " + "; ".join(hits)


def _released_sections():
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    sections = re.split(r"^(?=## )", changelog, flags=re.MULTILINE)
    return [(section.splitlines()[0][3:], section) for section in sections if re.match(r"## \d+\.\d+", section)]


def test_breaking_releases_open_with_an_upgrade_list():
    """See docs/reference/releases.md#release-notes."""
    missing = [version for version, section in _released_sections()
               if "(breaking)" in section and "\n### Upgrading from " not in section]
    assert not missing, f"CHANGELOG sections marked (breaking) without '### Upgrading from': {missing}"


def test_release_notes_carry_no_internal_plan_ids():
    """Released notes describe behaviour; plan steps and eval brief numbers mean nothing to a reader. Inline code
    (a command such as `--tests T02,T08`) is exempt."""
    plan_id = re.compile(r"craft plan \d|\bT\d\d\b")
    hits = []
    for version, section in _released_sections():
        for line in section.splitlines():
            match = plan_id.search(re.sub(r"`[^`]*`", "", line))
            if match:
                hits.append(f"{version}: {match.group(0)!r} in {line.strip()[:80]}")
    assert not hits, "internal plan IDs in CHANGELOG.md: " + "; ".join(hits)
