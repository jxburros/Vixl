"""Form regressions from the T06 evaluation: preview/export parity (#82), worst-case check
explanations (#81) and field rules (#77)."""

import numpy as np
import pytest
from PIL import Image

from vixl import Project
from vixl.forms import with_values
from vixl.proxy import render_preview

BOXES = {"name": (225, 580, 2100, 125), "short": (225, 840, 700, 100), "notes": (225, 1100, 1400, 360),
         "pick": (225, 1600, 800, 125)}


def signup():
    p = Project.sized("letter", "#ffffff")
    p.apply([
        {"type": "field", "name": "name", "kind": "text", "label": "Name", "size": 42, "x": 225, "y": 580, "width": 2100,
         "height": 125},
        {"type": "field", "name": "short", "kind": "text", "label": "Short", "size": 42, "x": 225, "y": 840, "width": 700,
         "height": 100, "min_size": 24},
        {"type": "field", "name": "notes", "kind": "multiline", "label": "Notes", "size": 36, "x": 225, "y": 1100,
         "width": 1400, "height": 360},
        {"type": "field", "name": "pick", "kind": "dropdown", "label": "Pick", "size": 42, "x": 225, "y": 1600, "width": 800,
         "height": 125, "options": ["Small", {"value": "L", "label": "Large and wide"}]},
    ])
    return p


VALUES = {"name": "Ada Lovelace", "short": "A value that is far too long for this small box",
          "notes": "First line\nSecond line is somewhat longer and wraps around", "pick": "L"}


def ink(image, box, scale):
    """Bounding box (left, top, right, bottom) of the dark pixels inside a field box, inset past its
    border; antialiasing and rounding move a glyph edge a pixel, so images are compared by extents."""
    x, y, w, h = (round(v * scale) for v in (box[0] + 20, box[1] + 20, box[2] - 40, box[3] - 40))
    dark = np.asarray(image.convert("L"))[y:y + h, x:x + w] < 140
    if not dark.any():
        return None
    rows, columns = np.where(dark.any(axis=1))[0], np.where(dark.any(axis=0))[0]
    return columns[0], rows[0], columns[-1], rows[-1]


def assert_same_ink(a, b, box, scale, key, tolerance=3):
    first, second = ink(a, box, scale), ink(b, box, scale)
    assert first is not None and second is not None, f"{key}: a value is drawn in both"
    assert max(abs(int(u) - int(v)) for u, v in zip(first, second)) <= tolerance, (key, first, second)


def test_preview_values_match_the_filled_export():
    p = signup()
    preview = render_preview(p, 1024, 1024, values=VALUES).convert("RGB")
    scale = preview.width / p.state["canvas"]["width"]
    assert scale < 0.75, "this size takes the reduced-resolution preview path"
    full = with_values(p, VALUES).render().convert("RGB").resize(preview.size, Image.Resampling.LANCZOS)
    for key, box in BOXES.items():
        assert_same_ink(preview, full, box, scale, key)


def test_preview_values_match_the_flattened_pdf():
    pdfium = pytest.importorskip("pypdfium2")
    p = signup()
    preview = render_preview(p, 1024, 1024, values=VALUES).convert("RGB")
    scale = preview.width / p.state["canvas"]["width"]
    page = pdfium.PdfDocument(p.export(format="PDF", values=VALUES))[0]
    raster = page.render(scale=preview.width / page.get_width()).to_pil().convert("RGB").resize(preview.size)
    for key, box in BOXES.items():
        assert_same_ink(preview, raster, box, scale, key)


def test_enlarged_and_default_values_follow_the_same_rules():
    p = signup()
    p.apply({"type": "field-set", "target": "name", "default": "Default value"})
    small = render_preview(p, 600, 600).convert("RGB")  # a default value, drawn from a proxy
    full = p.render().convert("RGB").resize(small.size, Image.Resampling.LANCZOS)
    assert_same_ink(small, full, BOXES["name"], small.width / 2550, "name")
