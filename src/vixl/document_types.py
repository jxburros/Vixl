"""Static types of the JSON document model, for annotations only (nothing here is checked at run time).

Documents are plain dicts so they serialise as they are; these ``TypedDict``s name the keys most code reads.
``total=False``: a layer type adds its own keys, and older documents may lack newer ones.
"""

from collections.abc import Mapping
from typing import Any, TypedDict

JSON = Any  # A JSON value: dict, list, str, int, float, bool or None.
Operation = Mapping[str, Any]


class Layer(TypedDict, total=False):
    id: str
    name: str
    type: str
    x: float
    y: float
    width: float
    height: float
    rotation: float
    flip_x: bool
    flip_y: bool
    opacity: float
    blend: str
    visible: bool
    effects: list[dict[str, Any]]
    mask: dict[str, Any] | None
    constraints: dict[str, Any]
    parent: str


class Canvas(TypedDict, total=False):
    width: int
    height: int
    background: str
    color_mode: str
    safe: float
    dpi: float


class State(TypedDict, total=False):
    canvas: Canvas
    layers: list[Layer]
    active_layer: str | None
    selection: Any
    variables: dict[str, Any]
    presets: dict[str, Any]
