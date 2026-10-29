"""JSON document model and resource policy; no interface dependencies."""

from collections.abc import Iterator
from contextlib import contextmanager
import contextvars
from dataclasses import dataclass, asdict
import math
import random
from typing import Any, TypeGuard, TypeVar
import uuid

from .errors import require
from .document_types import Canvas, State

T = TypeVar("T")

# Layers in one document (or page). Lists that name layers (targets, refs) share this bound; documents with more
# layers than an older release allowed do not open in that release.
MAX_LAYERS = 4096
# Every layer type a document may hold; validation, the published document schema (document_schema.py) and the
# file-format docs read this list.
LAYER_TYPES = ("raster", "text", "solid", "gradient", "shape", "group", "frame", "adjustment", "pathfinder", "symbol",
               "pixel", "paint", "field", "link")
LAYER_ROLES = ("content", "decoration", "background", "title")
# layer-intent priority: what adapt-layout may hide at another size (unset counts as required).
LAYER_PRIORITIES = ("required", "optional", "decorative")
# Layers whose box a layer-intent focal point is measured in.
FOCAL_TYPES = ("raster", "frame")


@dataclass(frozen=True)
class Limits:
    max_pixels: int = 40_000_000
    max_dimension: int = 16384
    max_layers: int = MAX_LAYERS
    max_asset_bytes: int = 64 * 1024 * 1024
    max_project_bytes: int = 256 * 1024 * 1024
    max_operations: int = 10000
    max_history: int = 2000
    max_load_pixels: int = 160_000_000
    max_load_fonts: int = 64
    max_nested_frames: int = 256

    def size(self, width: float, height: float, *, vector: bool = False) -> None:
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
_IDS: contextvars.ContextVar[random.Random | None] = contextvars.ContextVar("vixl_ids", default=None)


_ATOMS = (str, int, float, bool, type(None))


def copy_tree(value: T) -> T:
    """A deep copy of JSON-shaped data (dicts, lists, strings, numbers, booleans, None), about five times faster
    than ``copy.deepcopy``, which every apply pays several times on the whole document state. Other values are
    deep-copied as usual. Unlike ``deepcopy`` it does not keep two references to one list or dict as one: state
    never holds such aliases (it round-trips through JSON)."""
    kind = type(value)
    if isinstance(value, dict) and kind is dict:
        return {key: item if type(item) in _ATOMS else copy_tree(item)  # type: ignore[return-value]
                for key, item in value.items()}
    if isinstance(value, list) and kind is list:
        return [item if type(item) in _ATOMS else copy_tree(item) for item in value]  # type: ignore[return-value]
    if kind in _ATOMS:
        return value
    from copy import deepcopy

    return deepcopy(value)


def uid(prefix: str, *, fresh: bool = False) -> str:
    source = None if fresh else _IDS.get()
    return f"{prefix}_{source.getrandbits(64):016x}" if source else f"{prefix}_{uuid.uuid4().hex[:16]}"


@contextmanager
def seeded_ids(seed: object) -> Iterator[None]:
    token = _IDS.set(random.Random(seed))  # type: ignore[arg-type]
    try:
        yield
    finally:
        _IDS.reset(token)


def is_number(value: object) -> TypeGuard[int | float]:
    """A finite int or float; ``True`` and ``False`` are not numbers here."""
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def is_int(value: object) -> TypeGuard[int]:
    """An int that is not a bool."""
    return isinstance(value, int) and not isinstance(value, bool)


def finite(value: Any, name: str = "value", low: float | None = None, high: float | None = None) -> Any:
    require(is_number(value), f"{name} must be a finite number")
    require(low is None or value >= low, f"{name} must be at least {low}")
    require(high is None or value <= high, f"{name} must be at most {high}")
    return value


def new_state(width: int, height: int, background: str) -> State:
    from .house_style import safe_area

    canvas: Canvas = {"width": width, "height": height, "background": background, "color_mode": "rgba8"}
    # A size that defines no safe area gets the craft default; a named size replaces it with its own.
    if safe_area(width, height):
        canvas["safe"] = safe_area(width, height)
    return {
        "canvas": canvas,
        "layers": [],
        "active_layer": None,
        "selection": None,
        "variables": {},
        "presets": {},
    }


def new_layer(name: str, kind: str, width: float, height: float, **kwargs: Any) -> dict[str, Any]:
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


def policy_dict(limits: Limits) -> dict[str, Any]:
    return asdict(limits)
