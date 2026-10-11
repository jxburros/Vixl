"""`vixl catalog export`: the versioned catalog bundle host applications sync."""

import json
import re
from pathlib import Path

import jsonschema
import pytest

from vixl import catalog
from vixl.errors import VixlError

SRC = Path(__file__).parents[1] / "src" / "vixl"


@pytest.fixture(scope="module")
def bundle():
    return catalog.export_catalog()


def test_bundle_validates_against_the_checked_in_schema(bundle):
    schema = catalog.schema()
    jsonschema.Draft202012Validator.check_schema(schema)
    jsonschema.Draft202012Validator(schema).validate(bundle)
    assert bundle["catalog_schema_version"] == catalog.CATALOG_SCHEMA_VERSION
    assert set(catalog.SECTIONS) <= set(bundle)


def test_counts_match_the_registries(bundle):
    from vixl.briefs import KINDS
    from vixl.guidance import GUIDANCE
    from vixl.layouts import LAYOUTS, RATIOS
    from vixl.resources import PALETTES, SUITES
    from vixl.sizes import SIZES
    from vixl.style_catalog import STYLES
    from vixl.typefaces import fonts, list_pairings

    expected = {"sizes": len(SIZES), "palettes": len(PALETTES), "layouts": len(LAYOUTS), "briefs": len(KINDS),
                "guidance": len(GUIDANCE), "styles": len(STYLES), "families": len(fonts()),
                "pairings": len(list_pairings()["pairings"]), "type_scales": len(RATIOS)}
    for key, count in expected.items():
        assert bundle["counts"][key] == count, key
    assert len(bundle["sizes"]["items"]) == len(SIZES)
    assert [item["name"] for item in bundle["palettes"]["items"]] == list(PALETTES)
    assert {item["name"] for item in bundle["layouts"]["items"]} == set(LAYOUTS)
    assert {item["kind"] for item in bundle["briefs"]["items"]} == set(KINDS)
    assert [item["name"] for item in bundle["checks"]["suites"]] == list(SUITES)


def test_entries_carry_what_a_host_needs(bundle):
    letter = next(item for item in bundle["sizes"]["items"] if item["name"] == "letter")
    assert letter["unit"] == "in" and letter["dpi"] == 300 and letter["pixels"] == [2550, 3300]
    assert letter["bleed"]["amount"] == 0.125 and letter["safe_pixels"]["left"] == 75
    story = next(item for item in bundle["sizes"]["items"] if item["name"] == "instagram-story")
    assert story["safe_pixels"]["top"] == 250 and "dpi" not in story
    midnight = next(item for item in bundle["palettes"]["items"] if item["name"] == "midnight")
    light = midnight["modes"]["light"]
    assert set(light["roles"]) == set(bundle["palettes"]["roles"])
    assert light["contrast"]["ink_on_background"] >= bundle["palettes"]["contrast_targets"]["text"]
    grid = next(item for item in bundle["layouts"]["items"] if item["name"] == "editorial-grid")
    assert {"title", "body", "image"} <= set(grid["proportions"]) <= set(grid["slots"])
    assert all(0 <= v <= 1 for box in grid["proportions"].values() for v in box)
    poster = next(item for item in bundle["briefs"]["items"] if item["kind"] == "poster")
    assert poster["size_category"] and poster["checks"]["starter_suite"] == "composition"


def test_no_font_binaries_in_the_bundle(bundle):
    text = json.dumps(bundle)
    assert not re.search(r"[A-Za-z0-9+/]{200,}={0,2}", text)  # no base64 payload of any kind
    keys = set()

    def walk(value):
        if isinstance(value, dict):
            keys.update(value)
            for item in value.values():
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    walk(bundle)
    assert not keys & {"data", "data_base64", "file", "bytes", "woff", "woff2", "ttf"}
    assert len(text) < 2_000_000


def test_check_ids_cover_every_check_and_severity():
    from vixl.checks import CHECKS, OPTIONAL_CHECKS
    from vixl.deck import DECK_CHECKS

    declared = catalog.CHECK_INFO
    assert set(CHECKS) | set(OPTIONAL_CHECKS) | set(DECK_CHECKS) <= set(declared)
    # Every literal (check, severity) a finding can be raised with is listed, so hosts can rely on the IDs.
    found = set()
    for path in SRC.glob("*.py"):
        source = path.read_text(encoding="utf-8")
        found |= set(re.findall(r'issue\(\s*"([a-z_]+)",\s*"(error|warning|info)"', source))
        found |= set(re.findall(r'"check":\s*"([a-z_]+)"[^}]{0,200}?"severity":\s*"(error|warning|info)"', source))
    missing = sorted((check, severity) for check, severity in found
                     if check in declared and severity not in declared[check][1])
    assert not missing
    unknown = sorted({check for check, _ in found} - set(declared) - {"checkbox"})
    assert not unknown


def test_check_section_lists_rule_ids_with_severities(bundle):
    checks = bundle["checks"]
    contrast = next(item for item in checks["items"] if item["id"] == "contrast")
    assert contrast["severities"] == ["error"] and contrast["actions"]["error"] == "fix"
    bounds = next(item for item in checks["items"] if item["id"] == "bounds")
    assert bounds["actions"]["info"] == "informational"
    rule = next(rule for rule in checks["style_rules"] if rule["style"] == "swiss" and rule["id"] == "max-typefaces")
    assert rule["severity"] == "warning" and rule["thresholds"] == {"max": 2}
    assert "contrast" in checks["suite_rule_kinds"]
    assert checks["defaults"]["ink_limit"] == 300


def test_export_is_deterministic_and_sections_filter():
    first = catalog.export_catalog(["looks", "guidance"])
    assert set(first) - {"catalog_schema_version", "vixl_version", "schema", "counts"} == {"looks", "guidance"}
    assert first == catalog.export_catalog(["guidance", "looks"])
    with pytest.raises(VixlError, match="Unknown catalog section"):
        catalog.export_catalog(["fonts"])


def test_cli_export_writes_refuses_overwrite_and_prints(tmp_path, capsys):
    from vixl.cli import dispatch, main

    out = tmp_path / "catalog.json"
    result, _ = dispatch(["catalog", "export", "--out", str(out), "--section", "sizes"])
    assert set(result["counts"]) == {"sizes"} and result["bytes"] > 0
    assert json.loads(out.read_text(encoding="utf-8"))["catalog_schema_version"] == 1
    with pytest.raises(VixlError, match="exists"):
        dispatch(["catalog", "export", "--out", str(out)])
    dispatch(["catalog", "export", "--out", str(out), "--overwrite", "--section", "looks"])
    assert "looks" in json.loads(out.read_text(encoding="utf-8"))
    assert main(["catalog", "export", "--json", "--section", "briefs"]) == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["counts"]["briefs"] == 20 and "briefs" in printed
    schema, _ = dispatch(["catalog", "schema"])
    assert schema["title"] == "Vixl design catalog bundle"


def test_release_workflow_attaches_the_bundle():
    workflow = (Path(__file__).parents[1] / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    assert "vixl catalog export --out dist/vixl-catalog.json" in workflow
    assert "vixl catalog schema --out dist/vixl-catalog.schema.json" in workflow
    assert "dist/vixl-catalog*.json" in workflow  # uploaded with the distributions, then published as assets
