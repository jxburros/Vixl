"""Which core module executes each operation type.

Each feature module keeps its operation types in a tuple and executes them with one function, the same shape a
plugin has. ``CORE_OPERATION_MODULES`` lists them; ``operations.execute`` runs its shared steps (canonical type,
fan-out over ``targets``, the ``opacity``/``rotation`` creation fields, plugins, in-place edits, the stack guard)
and then hands the operation to the module named here. No type is claimed by two modules: the four types that
both add a layer and edit one in place (``adjustment``, ``frame``, ``shape``, ``symbol-instance``) go to
``inplace`` when they name a ``target`` (``operations.execute`` decides that first) and to ``design`` otherwise.
The operations every document has (``add``, ``move`` ...) stay in ``operations.py`` itself.

Adding a module: give it a types tuple and an ``execute(project, op)``, and add a line here.
"""

from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache
from importlib import import_module
from typing import Any


@dataclass(frozen=True)
class OperationModule:
    types_module: str  # Where the types tuple lives (a light schema module, so listing types loads no feature code).
    types_attribute: str
    module: str  # Where the function that executes them lives.
    function: str = "execute"
    also: tuple[str, ...] = ()  # Types the module executes that are listed elsewhere (the base list in operations.py).
    returns: bool = True  # False: the operation's result is None whatever the function returns.

    def types(self) -> tuple[str, ...]:
        return tuple(getattr(import_module(f"vixl.{self.types_module}"), self.types_attribute)) + self.also

    def __call__(self, project: Any, op: Any) -> Any:
        result = getattr(import_module(f"vixl.{self.module}"), self.function)(project, op)
        return result if self.returns else None


def _module(name: str, attribute: str = "TYPES", function: str = "execute", **options: Any) -> OperationModule:
    return OperationModule(name, attribute, name, function, **options)


CORE_OPERATION_MODULES = (
    _module("emojis"),
    _module("merging"),
    _module("scene"),
    _module("captions"),
    _module("vector_paths"),
    _module("audio"),
    _module("textures"),
    _module("motion"),
    _module("objects"),
    _module("pack_assets"),
    _module("accessibility"),
    _module("transforms", also=("move", "resize", "scale")),
    _module("stacks"),
    _module("selectors"),
    _module("diecut"),
    _module("path_split"),
    _module("pages"),
    _module("forms"),
    _module("links"),
    _module("codes"),
    _module("finishing"),
    _module("textflow"),
    _module("richtext"),
    _module("guides"),
    _module("irregular"),
    _module("authoring"),
    _module("containers"),
    _module("creative"),
    _module("automation", returns=False),
    _module("resources", "RESOURCE_TYPES", "execute_resource", returns=False),
    _module("pixel", "PIXEL_TYPES", "execute_pixel", returns=False),
    _module("animation", "ANIMATION_TYPES", "execute_animation", returns=False),
    _module("brushes", "BRUSH_TYPES", "execute_brush", returns=False),
    _module("timeline", "TIMELINE_TYPES", "execute_timeline", returns=False),
    _module("layouts", "LAYOUT_TYPES", "execute_layout", returns=False),
    OperationModule("design_schema", "TYPES", "design", "execute_design", returns=False),
)


@lru_cache(maxsize=None)
def operation_modules() -> dict[str, OperationModule]:
    """``{type: OperationModule}`` for every core feature type; a type claimed by two modules is an error."""
    table: dict[str, OperationModule] = {}
    for entry in CORE_OPERATION_MODULES:
        for kind in entry.types():
            if kind in table:
                raise RuntimeError(f"Operation {kind!r} is claimed by {table[kind].module} and {entry.module}")
            table[kind] = entry
    return table


# Modules that add operation schemas (``schemas(add)``, or ``module:function``), in the order the published schema
# lists them; the base operations come first, from schema.py itself.
SCHEMA_SOURCES = (
    "design_schema", "pixel_schema", "brushes", "timeline", "layouts", "automation", "creative", "emojis",
    "authoring", "plugins", "containers", "stacks", "irregular", "guides", "richtext", "pages", "forms", "selectors",
    "links", "codes", "diecut", "path_split", "finishing", "textflow", "schema:palette_schemas", "scene", "captions",
    "merging", "vector_paths", "audio", "textures", "motion", "objects", "pack_assets", "accessibility", "transforms",
)


def add_schemas(add: Callable[..., None]) -> None:
    """Let every module in ``SCHEMA_SOURCES`` add its operation schemas through ``add``."""
    for source in SCHEMA_SOURCES:
        module, _, function = source.partition(":")
        getattr(import_module(f"vixl.{module}"), function or "schemas")(add)
