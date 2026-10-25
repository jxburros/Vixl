"""The spelling plugin (#554): unknown words with suggestions, skipped tokens, allow lists, language packs."""

import gzip
import hashlib
import json

import pytest

from vixl import Project, VixlError, packs, plugins
from vixl.plugins.spelling import spelling


def document(tmp_path, *texts, brand=None):
    if brand is not None:
        (tmp_path / "brand.json").write_text(json.dumps(brand))
    p = Project(900, 120 * max(1, len(texts)), "white")
    p._workspace = tmp_path
    p.apply([{"type": "text", "name": f"t{i}", "text": text, "x": 10, "y": 10 + 110 * i, "size": 24,
              "color": "#111111"} for i, text in enumerate(texts)])
    return p


def spelling_issues(p):
    return [item for item in p.check(checks=["spelling"])["issues"] if item["check"] == "spelling"]


def test_spelling_is_an_optional_check_declared_by_the_plugin():
    from vixl.checks import CHECKS, OPTIONAL_CHECKS

    assert "spelling" in plugins.optional_checks() and "spelling" in OPTIONAL_CHECKS and "spelling" not in CHECKS
    assert plugins.manifest("spelling")["hooks"]["spell"]


def test_misspelling_gives_a_review_finding_with_a_suggestion(tmp_path):
    p = document(tmp_path, "We recieve your order", "Doors open at six")
    found = spelling_issues(p)
    assert len(found) == 1
    item = found[0]
    assert item["code"] == "unknown-word" and item["action"] == "review" and item["severity"] == "warning"
    assert item["word"] == "recieve" and item["layers"] == ["t0"]
    assert "receive" in item["suggestions"] and len(item["suggestions"]) <= 3
    assert item["lang"] == "en"
    # Not part of the default checks.
    assert not [i for i in p.check()["issues"] if i["check"] == "spelling"]


def test_urls_handles_hex_numbers_and_acronyms_are_ignored(tmp_path):
    p = document(tmp_path, "Visit https://zqxv.example/path or zqxvshop.com, mail hi@zqxv.io, follow @zqxvhq",
                 "Colour #ff00aa #zqxvlaunch 4K mp3 2026 NASA FAQ ZQXV well-known it’s don't USA's")
    assert spelling_issues(p) == []


def test_allow_lists_suppress_unknown_words(tmp_path):
    p = document(tmp_path, "Zqxvly brews Glorbnik tea in Flumptown")
    assert {i["word"] for i in spelling_issues(p)} == {"Zqxvly", "Glorbnik", "Flumptown"}
    (tmp_path / "brand.json").write_text(json.dumps({
        "words": {"allow": ["Zqxvly"]},
        "facts": {"city": {"values": ["Flumptown"]}}}))
    assert [i["word"] for i in spelling_issues(p)] == ["Glorbnik"]
    (tmp_path / ".vixl").mkdir()
    (tmp_path / ".vixl" / "dictionary.txt").write_text("# product names\nglorbnik\n")
    assert spelling_issues(p) == []


def test_forbid_stays_fix_and_allowed_phrases_are_skipped(tmp_path):
    brand = {"words": {"forbid": ["cheap"], "prefer": {"utilize": "use"}, "allow": ["Cheap Eats Co", "Utilize Labs"]}}
    p = document(tmp_path, "Cheap deals", "Dinner at Cheap Eats Co by Utilize Labs", brand=brand)
    issues = p.check(checks=["brand"])["issues"]
    forbidden = [i for i in issues if i.get("code") == "forbidden-word"]
    assert [i["layers"] for i in forbidden] == [["t0"]] and forbidden[0]["action"] == "fix"
    assert not [i for i in issues if i.get("code") == "preferred-word"]
    with pytest.raises(VixlError, match="allow"):
        document(tmp_path, "x", brand={"words": {"allow": "Cheap Eats"}}).check(checks=["brand"])


def test_bundled_english_runs_with_downloads_off(tmp_path, monkeypatch):
    monkeypatch.setenv("VIXL_PACK_DOWNLOAD", "off")
    monkeypatch.setenv("VIXL_PACK_DIR", str(tmp_path / "packs"))
    p = document(tmp_path, "Teh launch")
    assert [i["word"] for i in spelling_issues(p)] == ["Teh"]
    assert spelling.BUNDLED["en"].stat().st_size < 1024 * 1024
    with gzip.open(spelling.BUNDLED["en"], "rt", encoding="utf-8") as f:
        header = f.read(4000)
    assert "SCOWL" in header and "Permission to use, copy, modify, distribute and sell" in header


def test_missing_language_pack_is_a_review_finding_never_a_pass(tmp_path, monkeypatch):
    monkeypatch.setenv("VIXL_PACK_DOWNLOAD", "off")
    monkeypatch.setenv("VIXL_PACK_DIR", str(tmp_path / "packs"))
    source = tmp_path / "fr.txt.gz"
    source.write_bytes(gzip.compress("# test list\nbonjour\nle\nmonde\n".encode()))
    monkeypatch.setitem(packs.PACKS, "spelling-fr", {
        "file": "words.txt.gz", "path": "spelling/fr/words.txt.gz", "commit": "0" * 40,
        "sha256": hashlib.sha256(source.read_bytes()).hexdigest(), "bytes": source.stat().st_size,
        "description": "French word list", "install": "Download {url} and install it with vixl.packs.install."})
    p = document(tmp_path, "Bonjour le mondd")
    p.apply([{"type": "accessibility", "lang": "fr-FR"}])
    found = spelling_issues(p)
    assert len(found) == 1 and found[0]["code"] == "dictionary-unavailable" and found[0]["action"] == "review"
    assert found[0]["pack"] == "spelling-fr"
    packs.install("spelling-fr", source)
    assert [(i["code"], i["word"]) for i in spelling_issues(p)] == [("unknown-word", "mondd")]
    # A language with no published pack is also unavailable, not a pass.
    p.apply([{"type": "accessibility", "lang": "xx"}])
    assert [i["code"] for i in spelling_issues(p)] == ["dictionary-unavailable"]


def test_text_suite_rule_flags_unknown_words(tmp_path):
    p = document(tmp_path, "Our definately great offer", brand={"words": {"allow": ["Zqxvly"]}})
    p.apply([{"type": "suite-set", "name": "copy", "suite": {"rules": [
        {"id": "spelling", "kind": "text", "spelling": True}]}}])
    rule = p.check_suite("copy")["results"][0]
    assert rule["status"] == "failed" and rule["unknown_words"][0]["word"] == "definately"
    assert "definitely" in rule["unknown_words"][0]["suggestions"]
    p.apply([{"type": "text-set", "target": "t0", "text": "Zqxvly offers"}])
    assert p.check_suite("copy")["results"][0]["status"] == "passed"
    p.apply([{"type": "accessibility", "lang": "xx"}])
    assert p.check_suite("copy")["results"][0]["status"] == "needs_review"
