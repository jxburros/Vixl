import os
import tempfile

# The first text in a new document installs the rolled font pairing from the cache or the network. Tests never
# download: the ones that exercise automatic fonts set VIXL_AUTO_FONTS themselves and stub the font source. The
# weekly docs-online workflow sets VIXL_DOCS_ONLINE=1 to keep its own VIXL_AUTO_FONTS and use the real sources.
if not os.environ.get("VIXL_DOCS_ONLINE"):
    os.environ["VIXL_AUTO_FONTS"] = "off"
# Exports of saved documents use the per-user disk render cache: keep the suite's entries out of the real one.
os.environ["VIXL_RENDER_CACHE"] = tempfile.mkdtemp(prefix="vixl-render-cache-")

# The emoji artwork is a content pack (vixl.packs) pinned to VixlExamples. Fetch it once before the
# tests run (one worker downloads, the others wait on the lock), then forbid downloads inside tests.
from pathlib import Path  # noqa: E402

from filelock import FileLock  # noqa: E402
import pytest  # noqa: E402

from vixl import packs  # noqa: E402

if not packs.status("emojis")["installed"] and packs.downloads_allowed():
    packs.directory().mkdir(parents=True, exist_ok=True)
    with FileLock(str(Path(packs.directory()) / ".emojis.lock")):
        if not packs.status("emojis")["installed"]:
            try:
                packs.install("emojis")
            except Exception as exc:  # offline: the tests that need the artwork skip below
                print(f"emoji pack unavailable: {exc}")
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
