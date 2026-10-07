"""Large canvases: smaller full-canvas buffers, and a clean resource_limit when memory runs out (#341)."""

import math
import tracemalloc

import numpy as np
import pytest
from PIL import Image

from vixl import Project, VixlError
from vixl import design_render
from vixl.errors import memory_guard


def reference_gradient(project, layer, size):
    """gradient_image before #341: whole-canvas float64 arrays."""
    from vixl.design import gradient_stops, resolve_color
    from vixl.render import color

    w, h = size
    stops = gradient_stops(layer, project.state)
    offsets = [s["offset"] for s in stops]
    colors = np.array([color(resolve_color(s["color"], project.state)) for s in stops], dtype=float)
    direction = layer.get("direction", "vertical")
    x = np.linspace(0, 1, w)[None, :]
    y = np.linspace(0, 1, h)[:, None]
    if direction == "radial":
        ramp = np.sqrt((2 * x - 1) ** 2 + (2 * y - 1) ** 2)
    elif direction == "angled":
        a = math.radians(layer.get("angle", 0))
        dx, dy = math.cos(a), math.sin(a)
        ramp = ((x - 0.5) * dx + (y - 0.5) * dy) / (abs(dx) + abs(dy)) + 0.5
    else:
        ramp = np.broadcast_to(x if direction == "horizontal" else y, (h, w))
    colors[:, :3] *= colors[:, 3:] / 255
    arr = np.stack([np.interp(ramp, offsets, colors[:, i]) for i in range(4)], axis=-1)
    arr[:, :, :3] *= 255 / np.maximum(arr[:, :, 3:], 1)
    return Image.fromarray(np.uint8(np.clip(arr, 0, 255) + 0.5))


def gradient_layer(**options):
    p = Project(300, 200, "white")
    p.apply({"type": "gradient", "name": "g", **options})
    return p, p.layer("g")


@pytest.mark.parametrize("options", [
    {"start": "#123456", "end": "#abcdef80"},
    {"start": "red", "end": "transparent", "direction": "horizontal"},
    {"start": "red", "end": "blue", "direction": "radial"},
    {"start": "#00ff0040", "end": "black", "direction": "angled", "angle": 33},
    {"stops": [{"offset": 0, "color": "red"}, {"offset": 0.3, "color": "#ffffff00"}, {"offset": 1, "color": "navy"}],
     "direction": "angled", "angle": 200},
])
@pytest.mark.parametrize("size", [(300, 200), (1, 1), (7, 1300), (1500, 3)])
def test_gradients_are_unchanged(options, size):
    p, layer = gradient_layer(**options)
    expected = reference_gradient(p, layer, size)
    actual = design_render.gradient_image(p, layer, size)
    assert actual.mode == expected.mode and actual.size == expected.size
    assert np.array_equal(np.asarray(actual), np.asarray(expected))


@pytest.mark.parametrize("direction", ["vertical", "radial", "angled"])
def test_a_large_gradient_needs_no_float_copies_of_the_canvas(direction):
    p, layer = gradient_layer(start="#123456", end="#abcdef", direction=direction)
    size = (2400, 2400)  # 5.8 MP: 23 MB as RGBA bytes; the old float64 arrays peaked at over 500 MB.
    tracemalloc.start()
    try:
        design_render.gradient_image(p, layer, size)
        peak = tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()
    assert peak < 120 * 2**20


def out_of_memory(*args, **kwargs):
    raise MemoryError("Unable to allocate 1.19 GiB for an array with shape (16384, 2441, 4) and data type float64")


def test_running_out_of_memory_is_a_resource_limit(monkeypatch, tmp_path):
    monkeypatch.setattr(design_render, "gradient_image", out_of_memory)
    p = Project(401, 299, "#fedcba")  # A size and colour no other test renders, so no cache holds the result.
    p.apply({"type": "gradient", "name": "g", "start": "#010203", "end": "#040506"})
    calls = {"render": p.render, "export": lambda: p.export(str(tmp_path / "out.png")),
             "apply": lambda: p.apply({"type": "rasterize", "target": "g"})}
    for name, call in calls.items():
        with pytest.raises(VixlError) as error:
            call()
        assert error.value.code == "resource_limit" and "memory" in str(error.value), name
        assert not isinstance(error.value.__context__, MemoryError)


def test_memory_guard_keeps_other_errors_and_results():
    assert memory_guard(lambda: 42)() == 42
    with pytest.raises(ValueError):
        memory_guard(lambda: int("x"))()


def test_mcp_tools_report_running_out_of_memory_as_a_resource_limit(monkeypatch, tmp_path):
    from test_agent_interface import call

    from vixl.interfaces import mcp_server

    server = mcp_server(workspace=tmp_path)
    call(server, "vixl_document_create", {"path": "a.vixl", "width": 67, "height": 61, "background": "#0a0b0c"})
    failed, text, _ = call(server, "vixl_operations_apply", {"operations": [
        {"type": "gradient", "name": "g", "start": "#0d0e0f", "end": "#101112"}]})
    assert not failed, text
    monkeypatch.setattr(design_render, "gradient_image", out_of_memory)
    failed, text, _ = call(server, "vixl_render_preview", {})
    assert failed and "resource_limit" in text and "memory" in text
