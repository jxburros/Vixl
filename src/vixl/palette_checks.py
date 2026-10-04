"""Full-resolution palette compliance with bounded memory and explicit coverage."""

import numpy as np

from .errors import require
from .model import finite


def measure(project, *, palette=None, colors=None, tolerance=8, max_fraction=0.01, alpha_min=1, region=None):
    from .resources import get, validate
    from .render import color
    from .assurance import region_box

    require(not (palette and colors), "Choose palette or colors")
    if colors is None:
        palette = palette or project.state.get("active_palette")
        require(palette, "Choose a palette or apply one first")
        colors = project.state.get("palettes", {}).get(palette) or get(
            "palettes", palette, workspace=getattr(project, "_workspace", None)
        )
    validate("palettes", colors)
    tolerance = finite(tolerance, "tolerance", 0, 255)
    max_fraction = finite(max_fraction, "max_fraction", 0, 1)
    alpha_min = finite(alpha_min, "alpha_min", 1, 255)
    image = project.render()
    if region is not None:
        x, y, w, h = region_box(project, region)
        image = image.crop((x, y, x + w, y + h))
    pixels = np.asarray(image).reshape(-1, 4)
    allowed = np.array([color(c)[:3] for c in colors], dtype=np.int16)
    total = outside = maximum = 0
    examples = []
    for start in range(0, len(pixels), 32768):
        chunk = pixels[start : start + 32768]
        chunk = chunk[chunk[:, 3] >= alpha_min, :3].astype(np.int16)
        if not len(chunk):
            continue
        distances = np.full(len(chunk), 255, dtype=np.int16)
        for rgb in allowed:
            distances = np.minimum(distances, np.abs(chunk - rgb).max(axis=1))
        bad = distances > tolerance
        total += len(chunk)
        outside += int(bad.sum())
        maximum = max(maximum, int(distances.max()))
        if len(examples) < 8:
            examples.extend(list(dict.fromkeys("#%02x%02x%02x" % tuple(c) for c in chunk[bad][:8])))
            examples = list(dict.fromkeys(examples))[:8]
    require(total > 0, "No visible pixels in palette check; lower alpha_min or choose another region")
    fraction = outside / total
    return {
        "passed": fraction <= max_fraction,
        "palette": palette,
        "colors": colors,
        "pixels_checked": total,
        "outside_pixels": outside,
        "outside_fraction": fraction,
        "max_fraction": max_fraction,
        "tolerance": tolerance,
        "maximum_distance": maximum,
        "examples": examples,
        "metric": "maximum RGB channel distance (0–255); alpha below alpha_min excluded",
    }
