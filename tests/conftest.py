import os
import tempfile

# The first text in a new document installs the rolled font pairing from the cache or the network. Tests never
# download: the ones that exercise automatic fonts set VIXL_AUTO_FONTS themselves and stub the font source. The
# weekly docs-online workflow sets VIXL_DOCS_ONLINE=1 to keep its own VIXL_AUTO_FONTS and use the real sources.
if not os.environ.get("VIXL_DOCS_ONLINE"):
    os.environ["VIXL_AUTO_FONTS"] = "off"
# Font names never match the fonts installed on the machine running the suite; tests/test_system_fonts.py builds its own.
os.environ.setdefault("VIXL_SYSTEM_FONTS", "off")
# Exports of saved documents use the per-user disk render cache: keep the suite's entries out of the real one.
os.environ["VIXL_RENDER_CACHE"] = tempfile.mkdtemp(prefix="vixl-render-cache-")

# The emoji artwork and the fonts (the Vixl Originals a roll may pick) are content packs (vixl.packs) pinned to
# VixlPacks. Fetch them once before the tests run (one worker downloads, the others wait on the lock), then forbid
# downloads inside tests.
from pathlib import Path  # noqa: E402

from filelock import FileLock  # noqa: E402
import pytest  # noqa: E402

from vixl import packs  # noqa: E402

for _pack in ("emojis", "fonts"):
    if not packs.status(_pack)["installed"] and packs.downloads_allowed():
        packs.directory().mkdir(parents=True, exist_ok=True)
        with FileLock(str(Path(packs.directory()) / f".{_pack}.lock")):
            if not packs.status(_pack)["installed"]:
                try:
                    packs.install(_pack)
                except Exception as exc:  # offline: the tests that need the artwork skip below
                    print(f"{_pack} pack unavailable: {exc}")
os.environ["VIXL_PACK_DOWNLOAD"] = "off"
EMOJI_PACK = packs.status("emojis")["installed"]


def pytest_collection_modifyitems(config, items):
    """Tests marked emoji_pack need the artwork. CI sets VIXL_REQUIRE_PACKS=1 so a missing pack fails them."""
    if EMOJI_PACK or os.environ.get("VIXL_REQUIRE_PACKS"):
        return
    skip = pytest.mark.skip(reason="emoji artwork pack unavailable (vixl emoji artwork --download)")
    for item in items:
        if "emoji_pack" in item.keywords:
            item.add_marker(skip)
