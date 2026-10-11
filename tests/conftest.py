import os
import tempfile

# Document creation installs the rolled font pairing from the cache or the network. Tests never download:
# the ones that exercise automatic fonts set VIXL_AUTO_FONTS themselves and stub the font source.
os.environ["VIXL_AUTO_FONTS"] = "off"
# Exports of saved documents use the per-user disk render cache: keep the suite's entries out of the real one.
os.environ["VIXL_RENDER_CACHE"] = tempfile.mkdtemp(prefix="vixl-render-cache-")
