"""Pack image assets: the ``assets`` resource kind, its install-time checks and ``asset-place`` (#530)."""

import base64
import io
import json

import pytest
from PIL import Image

from vixl import Project, VixlError
from vixl import pack_assets, resources
from vixl.interfaces import Session
from vixl.studio import dispatch


def png(width=40, height=20, color="red"):
    stream = io.BytesIO()
    Image.new("RGBA", (width, height), color).save(stream, format="PNG")
    return stream.getvalue()


def asset(data=None, media_type="png", **extra):
    return {"data_base64": base64.b64encode(data if data is not None else png()).decode(), "media_type": media_type,
            **extra}


SVG = (b'<svg xmlns="http://www.w3.org/2000/svg" width="10" height="20" viewBox="0 0 10 20">'
       b'<rect width="10" height="20" fill="#00ff00"/></svg>')


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    monkeypatch.setenv("VIXL_RESOURCES", str(tmp_path / "global.json"))
    return tmp_path


def document(workspace, width=400, height=300):
    p = Project(width, height)
    p._workspace = workspace
    return p


def test_saved_asset_keeps_a_small_record_and_its_bytes_beside_the_library(workspace):
    data = png()
    resources.register("assets", "badge", asset(data, credit="Studio A", license="CC BY 4.0"), workspace=workspace)
    library = json.loads((workspace / ".vixl-resources.json").read_text())
    record = library["assets"]["badge"]
    assert "data_base64" not in record and record["width"] == 40 and record["height"] == 20
    assert record["credit"] == "Studio A" and record["bytes"] == len(data)
    stored = workspace / ".vixl-resources-assets" / f"{record['sha256']}.png"
    assert stored.read_bytes() == data
    assert pack_assets.resolved("badge", workspace)[1] == data
    # Replacing the asset removes the bytes no record names any more.
    resources.register("assets", "badge", asset(png(color="blue")), workspace=workspace)
    assert not stored.exists()


def test_asset_place_embeds_once_records_provenance_and_scales_by_aspect(workspace):
    data = png()
    resources.register("assets", "badge", asset(data, credit="Studio A"), workspace=workspace)
    p = document(workspace)
    p.apply([{"type": "asset-place", "resource": "badge", "x": 10, "y": 20, "width": 80},
             {"type": "asset-place", "resource": "badge", "name": "second", "x": 200, "y": 150, "anchor": "center"}])
    first, second = p.layer("badge"), p.layer("second")
    assert (first["x"], first["y"], first["width"], first["height"]) == (10, 20, 80, 40)
    assert (second["x"], second["y"], second["width"], second["height"]) == (180, 140, 40, 20)
    assert first["provenance"]["resource"] == "badge" and first["provenance"]["credit"] == "Studio A"
    assert first["provenance"]["sha256"] == pack_assets.hashlib.sha256(data).hexdigest()
    # The same asset placed twice is stored once (the asset store is content-addressed).
    assert first["asset"] == second["asset"]
    assert len([name for name in p.assets if name.startswith("assets/")]) == 1
    assert p.render().getpixel((50, 40))[:3] == (255, 0, 0)


def test_svg_asset_is_rendered_at_the_placed_size_and_keeps_its_source(workspace):
    resources.register("assets", "mark", asset(SVG, "svg"), workspace=workspace)
    p = document(workspace)
    p.apply({"type": "asset-place", "resource": "mark", "height": 200, "x": "center", "y": 0})
    layer = p.layer("mark")
    assert (layer["width"], layer["height"]) == (100, 200) and layer["x"] == 150
    assert p.image(layer["asset"]).size == (100, 200)
    assert p.assets[layer["provenance"]["source"]] == SVG
    assert p.render().getpixel((200, 100))[:3] == (0, 255, 0)


@pytest.mark.parametrize("value, match", [
    (asset(png(), "jpeg"), "file signature"),
    (asset(b"not an image at all", "png"), "file signature"),
    (asset(b"\x89PNG\r\n\x1a\n" + b"\0" * 64, "png"), "decode"),
    (asset(b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>', "svg"), "Active SVG"),
    (asset(b'<svg xmlns="http://www.w3.org/2000/svg"><image href="file:///etc/passwd"/></svg>', "svg"),
     "internal or embedded"),
    (asset(png(), "gif"), "media_type"),
    ({"data_base64": "@@@", "media_type": "png"}, "base64"),
    ({**asset(), "path": "/etc/passwd"}, "Unknown asset field"),
])
def test_install_rejects_bad_magic_malformed_and_malicious_assets(workspace, value, match):
    with pytest.raises(VixlError, match=match):
        resources.register("assets", "bad", value, workspace=workspace)
    assert not (workspace / ".vixl-resources.json").exists()


def test_install_rejects_oversize_and_overlarge_images(workspace, monkeypatch):
    noisy = Image.effect_noise((1100, 1100), 100).convert("RGB")
    stream = io.BytesIO()
    noisy.save(stream, format="PNG", compress_level=0)
    assert len(stream.getvalue()) > pack_assets.MAX_ASSET_BYTES
    with pytest.raises(VixlError, match="MiB") as error:
        resources.register("assets", "big", asset(stream.getvalue()), workspace=workspace)
    assert error.value.code == "resource_limit"
    with pytest.raises(VixlError) as error:
        resources.register("assets", "wide", asset(png(17000, 1)), workspace=workspace)
    assert error.value.code == "resource_limit"


def test_plugin_pack_carries_assets_under_a_pack_cap_and_removal_deletes_them(workspace, monkeypatch):
    session = Session(workspace=workspace)
    manifest = {"api_version": 1, "name": "acme", "version": "1.0.0",
                "resources": {"assets": {"acme-badge": asset()}}}
    dispatch(session, "plugin-install", {"manifest": manifest})
    record = resources.get("assets", "acme-badge", workspace=workspace)
    stored = workspace / ".vixl-resources-assets" / f"{record['sha256']}.png"
    assert stored.exists()
    assert dispatch(session, "resource-get", {"kind": "assets", "name": "acme-badge"})["value"] == record
    dispatch(session, "plugin-remove", {"name": "acme"})
    assert not stored.exists()
    monkeypatch.setattr(pack_assets, "MAX_PACK_BYTES", 100)
    with pytest.raises(VixlError, match="at most 0 MiB of assets"):
        dispatch(session, "plugin-install", {"manifest": manifest})
    assert not (workspace / ".vixl-resources-assets").exists() or not any(
        (workspace / ".vixl-resources-assets").iterdir())


def test_template_with_asset_place_scales_proportionally(workspace):
    resources.register("assets", "badge", asset(), workspace=workspace)
    resources.register("templates", "badge-card", {
        "width": 1000, "height": 1000, "proportional": True,
        "operations": [{"type": "asset-place", "resource": "badge", "x": 100, "y": 200, "width": 400}],
    }, workspace=workspace)
    for size, expected in ((1000, (100, 200, 400, 200)), (500, (50, 100, 200, 100))):
        p = document(workspace, size, size)
        p.apply({"type": "template-apply", "name": "badge-card"})
        layer = p.layer("badge")
        assert (layer["x"], layer["y"], layer["width"], layer["height"]) == expected


def test_brand_required_element_is_satisfied_by_a_placed_asset(workspace):
    resources.register("assets", "seal", asset(), workspace=workspace)
    (workspace / "brand.json").write_text(json.dumps({"required_elements": ["seal"]}))
    p = document(workspace)
    missing = [i for i in p.check(checks=["brand"])["issues"] if "Required brand element" in i["message"]]
    assert missing
    p.apply({"type": "asset-place", "resource": "seal", "name": "corner-mark"})
    assert not [i for i in p.check(checks=["brand"])["issues"] if "Required brand element" in i["message"]]


def test_missing_or_changed_bytes_are_reported(workspace):
    resources.register("assets", "badge", asset(), workspace=workspace)
    record = resources.get("assets", "badge", workspace=workspace)
    (workspace / ".vixl-resources-assets" / f"{record['sha256']}.png").write_bytes(png(color="blue"))
    with pytest.raises(VixlError) as error:
        document(workspace).apply({"type": "asset-place", "resource": "badge"})
    assert error.value.code == "missing_asset"
