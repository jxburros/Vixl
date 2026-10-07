"""JSON document model and resource policy; no interface dependencies."""

from contextlib import contextmanager
import contextvars
from dataclasses import dataclass, asdict
import math
import random
import uuid

from .errors import require

# Layers in one document (or page). Lists that name layers (targets, refs) share this bound; documents with more
# layers than an older release allowed do not open in that release.
MAX_LAYERS = 4096


@dataclass(frozen=True)
class Limits:
    max_pixels: int = 40_000_000
    max_dimension: int = 16384
    max_layers: int = MAX_LAYERS
    max_asset_bytes: int = 64 * 1024 * 1024
    max_project_bytes: int = 256 * 1024 * 1024
    max_operations: int = 10000
    max_history: int = 2000

    def size(self, width, height, *, vector=False):
        if vector:
            finite(width, "width")
            finite(height, "height")
        else:
            require(isinstance(width, int) and isinstance(height, int), "Dimensions must be integers")
        require(
            0 < width <= self.max_dimension and 0 < height <= self.max_dimension,
            f"Dimensions must be 1–{self.max_dimension}",
            "resource_limit",
        )
        require(width * height <= self.max_pixels, "Image exceeds pixel limit", "resource_limit")


# Inside Project.apply IDs come from a generator seeded by the document and the batch, so a dry run reports the IDs
# the real apply then creates.
_IDS = contextvars.ContextVar("vixl_ids", default=None)


def uid(prefix, *, fresh=False):
    source = None if fresh else _IDS.get()
    return f"{prefix}_{source.getrandbits(64):016x}" if source else f"{prefix}_{uuid.uuid4().hex[:16]}"


@contextmanager
def seeded_ids(seed):
    token = _IDS.set(random.Random(seed))
    try:
        yield
    finally:
        _IDS.reset(token)


def finite(value, name="value", low=None, high=None):
    require(
        isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value),
        f"{name} must be a finite number",
    )
    require(low is None or value >= low, f"{name} must be at least {low}")
    require(high is None or value <= high, f"{name} must be at most {high}")
    return value


def new_state(width, height, background):
    return {
        "canvas": {"width": width, "height": height, "background": background, "color_mode": "rgba8"},
        "layers": [],
        "active_layer": None,
        "selection": None,
        "variables": {},
        "presets": {},
    }


def new_layer(name, kind, width, height, **kwargs):
    return {
        "id": uid("lyr"),
        "name": name,
        "type": kind,
        "width": width,
        "height": height,
        "x": 0,
        "y": 0,
        "rotation": 0,
        "flip_x": False,
        "flip_y": False,
        "opacity": 1.0,
        "blend": "normal",
        "visible": True,
        "effects": [],
        "mask": None,
        "constraints": {},
        **kwargs,
    }


def policy_dict(limits):
    return asdict(limits)
