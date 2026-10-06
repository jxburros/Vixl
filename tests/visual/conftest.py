import os
import sys

import pytest

SKIP_REASON = (
    "visual references are generated on Linux (text rendering differs across OSes and FreeType versions); "
    "set VIXL_VISUAL=1 to run anyway"
)


def pytest_collection_modifyitems(config, items):
    if sys.platform == "linux" or os.environ.get("VIXL_VISUAL", "") not in ("", "0"):
        return
    skip = pytest.mark.skip(reason=SKIP_REASON)
    for item in items:
        if "tests/visual" in item.nodeid.replace("\\", "/"):
            item.add_marker(skip)
