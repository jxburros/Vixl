"""Content packs (vixl.packs): pinned downloads, local installs, and rendering when a pack is missing."""

import hashlib

import pytest

from vixl import Project, packs
from vixl.errors import VixlError


@pytest.fixture
def no_pack(tmp_path, monkeypatch):
    """An empty pack directory, downloads off, and no local override: the emoji artwork is unavailable."""
    available = packs.status("emojis")
    monkeypatch.setenv("VIXL_PACK_DIR", str(tmp_path / "packs"))
    monkeypatch.setenv("VIXL_PACK_DOWNLOAD", "off")
    monkeypatch.delenv("VIXL_EMOJIS_PACK", raising=False)
    monkeypatch.setattr(packs, "_failed", {})
    yield available
    packs._failed.clear()


def test_missing_pack_is_reported_with_instructions(no_pack):
    status = packs.status("emojis")
    assert not status["installed"] and status["downloads"] == "off"
    assert status["url"].endswith(f"/{packs.PACKS['emojis']['commit']}/packs/emojis/artwork.zip")
    with pytest.raises(VixlError) as error:
        packs.path("emojis")
    assert error.value.code == "pack_unavailable"
    assert "vixl emoji artwork --download" in str(error.value)
    with pytest.raises(VixlError) as error:
        packs.install("emojis")
    assert error.value.code == "pack_unavailable"


def test_a_file_that_does_not_match_the_pin_is_refused(no_pack, tmp_path):
    fake = tmp_path / "artwork.zip"
    fake.write_bytes(b"not the pack")
    with pytest.raises(VixlError) as error:
        packs.install("emojis", fake)
    assert error.value.code == "pack_mismatch"
    assert not packs.status("emojis")["installed"]


def test_override_points_at_a_local_copy(no_pack, tmp_path, monkeypatch):
    copy = tmp_path / "copy.zip"
    copy.write_bytes(b"x")
    monkeypatch.setenv("VIXL_EMOJIS_PACK", str(copy))
    assert packs.path("emojis") == copy
    assert packs.status("emojis")["source"] == "override"
    monkeypatch.setenv("VIXL_EMOJIS_PACK", str(tmp_path / "missing.zip"))
    with pytest.raises(VixlError, match="missing file"):
        packs.path("emojis")


def test_unknown_pack_is_an_error():
    with pytest.raises(VixlError, match="Unknown content pack"):
        packs.status("fonts")


def test_text_with_emojis_renders_from_fonts_without_the_pack(no_pack):
    from vixl import emojis

    emojis._archive.cache_clear()
    emojis._bundled.cache_clear()
    p = Project(240, 80)
    result = p.apply([{"type": "text", "name": "t", "text": "Hi 😀 :approved:", "size": 32, "x": 4, "y": 4}])
    p.render()
    assert any("emojis content pack is not installed" in w for w in result.get("warnings", []))


@pytest.mark.emoji_pack
def test_install_from_a_verified_copy(no_pack, tmp_path):
    source = no_pack["path"]
    assert hashlib.sha256(open(source, "rb").read()).hexdigest() == packs.PACKS["emojis"]["sha256"]
    installed = packs.install("emojis", source)
    assert installed["installed"] and installed["source"] == "cache"
    assert packs.path("emojis").parent.parent == tmp_path / "packs"


def test_emoji_artwork_workflow_reports_status(no_pack, tmp_path):
    from vixl.interfaces import Session
    from vixl.workflows import dispatch

    result = dispatch(Session(None, workspace=tmp_path), "emoji-artwork", {})
    assert result["pack"] == "emojis" and result["installed"] is False
