import os

# Document creation installs the rolled font pairing from the cache or the network. Tests never download:
# the ones that exercise automatic fonts set VIXL_AUTO_FONTS themselves and stub the font source.
os.environ["VIXL_AUTO_FONTS"] = "off"
