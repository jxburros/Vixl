"""Brand kit <-> Design Profile mapping (#545): round trips, unmapped paths, the workflow actions and the CLI."""

import json
import shutil
from pathlib import Path

import pytest

from vixl import Project, VixlError
from vixl.brand import load, load_brand_or_profile
from vixl.workflows import brand_profile_cli as cli
from vixl.plugins.brand_kit.design_profile import from_brand, to_brand

FIXTURE = Path(__file__).parent / "fixtures" / "design-profile" / "northwind.json"
PALETTE = {"background": "#ffffff", "surface": "#eeeeee", "ink": "#111111", "muted": "#444444",
           "accent": "#0044aa", "accent-text": "#0044aa", "on-accent": "#ffffff"}


def profile():
    return json.loads(FIXTURE.read_text())


def test_profile_maps_to_brand_and_lists_unmapped_paths():
    kit, unmapped = to_brand(profile())
    assert kit["name"] == "Northwind Studio"
    assert kit["fonts"] == {"heading": {"family": "Inter", "weight": 700},
                            "body": {"family": "Source Serif 4", "weight": 400}}
    assert kit["palette"]["accent-text"] == "#9a3412" and kit["palette"]["on-accent"] == "#ffffff"
    assert kit["palette"]["extra"] == {"brand-dark": "#14213d"}
    assert kit["minimum_contrast"] == {"text": 4.5, "large_text": 3}
    assert kit["stages"] == {"body": {"font": "body", "line_height": 1.5}}
    assert sorted(unmapped) == ["docText.hyphenate", "page.margins", "page.size", "typography.heading.letterSpacing",
                                "voice"]


def test_round_trip_keeps_the_overlapping_fields():
    kit, _ = to_brand(profile())
    again, _ = to_brand(from_brand(kit)[0])
    assert again == kit
    brand = {"name": "B", "palette": {**PALETTE, "extra": {"wood": "#d2a465"}}, "minimum_contrast": 4.5,
             "fonts": {"heading": {"family": "Inter", "weight": 700}, "body": {"family": "Inter", "weight": 400}},
             "stages": {"body": {"font": "body", "line_height": 1.4}, "label": {"font": "heading", "case": "upper"}},
             "words": {"forbid": ["cheap"]}, "logo": {"clear_space": 0.5}}
    exported, unmapped = from_brand(brand)
    assert exported["schemaVersion"] == 2 and exported["colours"]["accentText"] == "#0044aa"
    assert set(unmapped) == {"stages.label", "words", "logo"}
    back, _ = to_brand(exported)
    for field in ("name", "palette", "minimum_contrast", "fonts"):
        assert back[field] == brand[field]
    assert back["stages"] == {"body": brand["stages"]["body"]}


def test_disagreeing_page_colour_is_reported_not_applied():
    data = profile()
    data["page"]["background"] = "#000000"
    kit, unmapped = to_brand(data)
    assert kit["palette"]["background"] == "#fbf8f2" and "page.background" in unmapped
    with pytest.raises(VixlError):
        to_brand({**data, "schemaVersion": 1})


def test_load_brand_or_profile_accepts_both_shapes():
    kit, unmapped = load_brand_or_profile(profile())
    assert kit["name"] == "Northwind Studio" and unmapped
    plain = {"name": "Plain", "palette": dict(PALETTE)}
    assert load_brand_or_profile(plain) == (plain, [])
    with pytest.raises(VixlError):
        load_brand_or_profile({"palette": {"nope": "#fff"}})


def test_brand_check_fires_on_a_design_violating_the_imported_brand(tmp_path):
    shutil.copy(FIXTURE, tmp_path / "profile.json")
    result = cli(["import", "--design-profile", "profile.json", "--workspace", str(tmp_path)])
    assert result["written"] and result["output"] == "brand.json" and "voice" in result["unmapped"]
    assert load(tmp_path)["palette"]["accent"] == "#c2410c"
    p = Project(400, 200, "#fbf8f2")
    p._workspace = tmp_path
    p.apply([{"type": "text", "name": "title", "text": "Hello", "x": 10, "y": 10, "size": 40, "color": "#e01010"}])
    messages = [i["message"] for i in p.check(checks=["brand"])["issues"] if i["check"] == "brand"]
    assert any("palette" in m for m in messages) and any("font" in m.lower() for m in messages)
    with pytest.raises(VixlError, match="exists"):
        cli(["import", "--design-profile", "profile.json", "--workspace", str(tmp_path)])


def test_export_writes_a_profile_and_refuses_to_overwrite(tmp_path):
    (tmp_path / "brand.json").write_text(json.dumps({"name": "B", "palette": dict(PALETTE),
                                                     "logo": {"clear_space": 0.5}}))
    result = cli(["export", "--design-profile", "out/profile.json", "--workspace", str(tmp_path)])
    written = json.loads((tmp_path / "out" / "profile.json").read_text())
    assert written["schemaVersion"] == 2 and written["colours"]["onAccent"] == "#ffffff"
    assert result["unmapped"] == ["logo"]
    with pytest.raises(VixlError, match="exists"):
        cli(["export", "--design-profile", "out/profile.json", "--workspace", str(tmp_path)])
    from vixl.cli import dispatch

    result, _ = dispatch(["brand", "export", "--design-profile", "out/profile.json", "--workspace", str(tmp_path),
                          "--overwrite"])
    assert result["output"] == "out/profile.json"


def test_import_workflow_dry_run_writes_nothing(tmp_path):
    from vixl.interfaces import Session
    from vixl.workflows import dispatch

    result = dispatch(Session(workspace=tmp_path), "brand-import", {"profile": profile(), "dry_run": True})
    assert result["written"] is False and result["brand"]["name"] == "Northwind Studio"
    assert not (tmp_path / "brand.json").exists()


def test_host_put_brand_accepts_brand_json_and_a_design_profile(tmp_path, monkeypatch):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from vixl.host import create_host_app

    monkeypatch.setenv("VIXL_AUTO_FONTS", "off")
    token = "b" * 32
    client = TestClient(create_host_app(tmp_path / "root", token), headers={"Authorization": f"Bearer {token}"})
    assert client.get("/w/team/brand").json()["code"] == "not_found"

    mapped = client.put("/w/team/brand", json=profile())
    assert mapped.status_code == 200, mapped.text
    body = mapped.json()
    assert body["source"] == "design-profile" and "voice" in body["unmapped"]
    assert body["kit"]["name"] == "Northwind Studio" and body["brand"]["palette"]["accent-text"] == "#9a3412"
    written = tmp_path / "root" / "team" / "brand.json"
    assert load(written.parent)["name"] == "Northwind Studio"
    assert client.get("/w/team/brand").json()["digest"] == body["digest"]

    plain = {"name": "Plain", "palette": dict(PALETTE)}
    stale = client.put("/w/team/brand?if_digest=sha256:" + "0" * 64, json=plain)
    assert stale.status_code == 409 and stale.json()["details"]["digest"] == body["digest"]
    replaced = client.put(f"/w/team/brand?if_digest={body['digest']}", json=plain).json()
    assert replaced["source"] == "brand.json" and replaced["unmapped"] == [] and replaced["digest"] != body["digest"]
    assert load(written.parent)["name"] == "Plain"

    invalid = client.put("/w/team/brand", json={"palette": {"nope": "#fff"}})
    assert invalid.status_code == 400 and invalid.json()["code"]
    assert load(written.parent)["name"] == "Plain"  # A refused upload leaves the brand alone.
