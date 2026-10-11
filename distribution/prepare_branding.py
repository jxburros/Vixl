"""Refresh packaged artwork from the Ripple logo kit (requires Pillow)."""

from pathlib import Path
import shutil

from PIL import Image


def prepare():
    root = Path(__file__).resolve().parents[1]
    kit = root / "assets/brand/ripple"
    data = root / "src/vixl/data/brand"
    data.mkdir(parents=True, exist_ok=True)
    for filename in ("favicon-dark.svg", "horizontal-reverse.svg"):
        shutil.copyfile(kit / "SVG" / filename, data / filename)
    # Sizes up to 64 px come from the kit's simplified small-size icon; the detailed ripple blurs there.
    with Image.open(kit / "Icons/app-icon-dark.png") as image, Image.open(kit / "Icons/app-icon-dark-96.png") as small:
        small = small.convert("RGBA")
        image.save(root / "distribution/windows/vixl.ico",
                   sizes=[(size, size) for size in (16, 24, 32, 48, 64, 128, 256)],
                   append_images=[(small if size <= 64 else image).resize((size, size), Image.LANCZOS)
                                  for size in (16, 24, 32, 48, 64, 128, 256)])


if __name__ == "__main__":
    prepare()
