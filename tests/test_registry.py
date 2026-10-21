"""The core operation registry (#631): every operation type has exactly one module that executes it."""

import pytest

from vixl import operations, plugins, registry
from vixl.inplace import IN_PLACE_TYPES

# Types that both add a layer (their feature module) and edit a targeted one in place (inplace.py).
DUAL = {"adjustment", "frame", "shape", "symbol-instance"}


def test_every_operation_type_has_one_handler():
    table = registry.operation_modules()
    plugin_types = set(plugins.operation_types())
    base = set(operations.BASE_TYPES) | set(operations.COLOR_TYPES)
    handled_by_modules = set(table)
    assert not handled_by_modules & plugin_types
    # move, resize and scale are listed with the base operations and executed by transforms (``also``).
    assert handled_by_modules & base == {"move", "resize", "scale"}
    assert set(operations.OPERATION_TYPES) == handled_by_modules | plugin_types | base
    assert set(IN_PLACE_TYPES) - base == DUAL and DUAL <= handled_by_modules


def test_a_type_claimed_twice_is_an_error(monkeypatch):
    twice = registry.CORE_OPERATION_MODULES + (registry.OperationModule("emojis", "TYPES", "emojis"),)
    monkeypatch.setattr(registry, "CORE_OPERATION_MODULES", twice)
    registry.operation_modules.cache_clear()
    try:
        with pytest.raises(RuntimeError, match="claimed by emojis and emojis"):
            registry.operation_modules()
    finally:
        monkeypatch.undo()
        registry.operation_modules.cache_clear()


def test_dispatch_reaches_the_module_and_keeps_its_result():
    from vixl import Project

    project = Project(100, 100)
    project.apply([{"type": "shape", "shape": "rectangle", "name": "box", "width": 10, "height": 10},
                   {"type": "skew", "target": "box", "x": 10}])  # transforms
    assert project.layer("box").get("skew_x") == 10
    project.apply({"type": "shape", "target": "box", "fill": "#123456"})  # in place, not a second layer
    assert len(project.state["layers"]) == 1 and project.layer("box")["fill"] == "#123456"
