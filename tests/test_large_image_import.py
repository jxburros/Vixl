"""Images above the pixel limit import when downsampled, and otherwise fail with the remedy (#323)."""

from io import BytesIO

from PIL import Image
import pytest

from vixl import Project, VixlError
from vixl.image_import import import_image
from vixl.model import Limits

# Pillow's decompression-bomb guard is lowered so a small file stands in for a 108 MP camera image: the source is
# 600,000 pixels, more than twice Pillow's cap (its hard error) and twice the document's 300,000-pixel limit.
SIZE = (1000, 600)


@pytest.fixture
def huge(tmp_path, monkeypatch):
    stream = BytesIO()
    Image.new("RGB", SIZE, "#3366cc").save(stream, format="PNG")
    path = tmp_path / "huge.png"
    path.write_bytes(stream.getvalue())
    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 250_000)
    return path


def project():
    return Project(400, 300, limits=Limits(max_pixels=300_000))


def test_add_with_max_pixels_downsamples_a_source_above_the_limit(huge):
    p = project()
    p.apply({"type": "add", "path": str(huge), "name": "photo", "max_pixels": 100_000})
    layer = p.layer("photo")
    assert layer["provenance"]["original_size"] == list(SIZE)
    embedded = layer["provenance"]["embedded_size"]
    # The source size is above the document's limit, so the layer box is the embedded size.
    assert [layer["width"], layer["height"]] == embedded
    assert embedded[0] * embedded[1] <= 100_000 and embedded[0] >= 400
    assert p.image(layer["asset"]).size == tuple(embedded)
    assert Image.MAX_IMAGE_PIXELS == 250_000  # Pillow's guard is restored


def test_add_without_max_pixels_names_the_limit_and_the_remedy(huge):
    with pytest.raises(VixlError) as caught:
        project().apply({"type": "add", "path": str(huge), "name": "photo"})
    message = str(caught.value)
    assert caught.value.code == "resource_limit"
    assert "1000×600" in message and "max_pixels" in message
    assert "--max-pixels" in message and "decompression bomb" not in message


def test_import_downsamples_to_the_limit_and_says_so(huge):
    p = project()
    result = import_image(p, huge.read_bytes(), "photo")
    assert result["downsampled"]["from"] == list(SIZE)
    width, height = result["downsampled"]["to"]
    assert width * height <= 300_000 and abs(width / height - 1000 / 600) < 0.01
    assert "downsampled" in result["warnings"][0]


def test_a_raised_limit_imports_the_full_image(huge):
    p = Project(400, 300, limits=Limits(max_pixels=1_000_000))
    result = import_image(p, huge.read_bytes(), "photo")
    assert "downsampled" not in result and p.image(result["asset"]).size == SIZE
