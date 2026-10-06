"""Visual regression tests: render fixtures and compare with the references in ``golden/``.

Run ``pytest -m visual``. After an intended render change run ``VIXL_UPDATE_GOLDEN=1 pytest tests/visual``
and commit the updated references with the change (see CONTRIBUTING.md). References are generated on Linux.
"""

import io

import pytest
from PIL import Image

from golden_compare import check_png, check_text, pdf_to_image, pptx_snapshot
from visual_fixtures import FIXTURES, PDF_FIXTURES, PPTX_FIXTURES, SVG_FIXTURES

pytestmark = pytest.mark.visual


@pytest.mark.parametrize("name", sorted(FIXTURES))
def test_png(name):
    check_png(name, FIXTURES[name]().render())


@pytest.mark.parametrize("name", SVG_FIXTURES)
def test_svg(name):
    data = FIXTURES[name]().export(format="SVG")
    check_text(f"{name}.svg", data.decode("utf-8") if isinstance(data, bytes) else data, "snapshot")


@pytest.mark.parametrize("name", PDF_FIXTURES)
def test_pdf_rendered(name):
    data = FIXTURES[name]().export(format="PDF")
    check_png(f"{name}.pdf", pdf_to_image(data, scale=1))


@pytest.mark.parametrize("name", PPTX_FIXTURES)
def test_pptx_structure(name):
    data = FIXTURES[name]().export(format="PPTX")
    check_text(f"{name}.pptx", pptx_snapshot(data), "snapshot")


def test_fixtures_are_small_and_cover_each_area():
    assert 15 <= len(FIXTURES) <= 30
    for name, build in FIXTURES.items():
        with Image.open(io.BytesIO(build().export(format="PNG"))) as image:
            assert max(image.size) <= 256, name
