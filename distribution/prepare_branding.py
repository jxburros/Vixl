"""Refresh packaged artwork from the supplied Digital Shift kit (requires Pillow)."""

from pathlib import Path
import shutil

from PIL import Image


def prepare():
    root = Path(__file__).resolve().parents[1]
    kit = root / "assets/brand/digital-shift"
    data = root / "src/vixl/data/brand"
    data.mkdir(parents=True, exist_ok=True)
    for filename in ("favicon-dark.svg", "horizontal-reverse.svg"):
        shutil.copyfile(kit / "SVG" / filename, data / filename)
    with Image.open(kit / "Icons/app-icon-dark.png") as image:
        image.save(root / "distribution/windows/vixl.ico",
                   sizes=[(size, size) for size in (16, 24, 32, 48, 64, 128, 256)])


if __name__ == "__main__":
    prepare()
