"""Every row of docs/use-cases.md has its own ID, and the evidence file refers only to IDs that exist."""

from collections import Counter
from pathlib import Path
import re

DOCS = Path(__file__).resolve().parent.parent / "docs"


def test_use_case_ids_are_unique():
    ids = re.findall(r"^\| ([A-Z]+-\d+) \|", (DOCS / "use-cases.md").read_text(encoding="utf-8"), re.M)
    assert ids
    assert [key for key, count in Counter(ids).items() if count > 1] == []


def test_evidence_refers_to_existing_use_cases():
    known = set(re.findall(r"^\| ([A-Z]+-\d+) \|", (DOCS / "use-cases.md").read_text(encoding="utf-8"), re.M))
    evidence = (DOCS / "project" / "use-case-evidence.md").read_text(encoding="utf-8")
    assert set(re.findall(r"\b(?:AGT|HUM|DEV)-\d+\b", evidence)) <= known
