"""Untrusted input is charged while it is processed, so a small hostile file fails fast instead of running long."""

import time

import pytest

from vixl import Project
from vixl.errors import VixlError
from vixl.svg_import import MAX_RASTERIZED, svg_operations

SVG = '<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="40" height="40">'


def use_fanout(levels=5, ways=10):
    """A ~1 KB SVG whose ``<use>`` tree expands to ``ways ** levels`` shapes."""
    parts = [SVG, '<defs><rect id="l0" width="1" height="1" fill="#000"/>']
    for level in range(1, levels + 1):
        uses = "".join(f'<use xlink:href="#l{level - 1}"/>' for _ in range(ways))
        parts.append(f'<g id="l{level}">{uses}</g>')
    parts.append(f'</defs><use xlink:href="#l{levels}"/></svg>')
    return "".join(parts).encode()


@pytest.mark.parametrize("fallback", [False, True])
def test_svg_use_fanout_fails_fast(fallback):
    data = use_fanout()
    assert len(data) < 1600
    start = time.perf_counter()
    with pytest.raises(VixlError) as caught:
        svg_operations(data, Project(40, 40), "art", fallback=fallback)
    assert caught.value.code == "resource_limit"
    assert caught.value.details.get("field") == "svg"
    assert time.perf_counter() - start < 5  # it ran for minutes before the expansion was charged


def test_svg_use_within_budget_still_expands():
    operations = svg_operations(use_fanout(levels=2, ways=10), Project(40, 40), "art")
    assert sum(op["type"] == "shape" for op in operations) == 100


def unsupported(count):
    shapes = "".join(f'<rect x="{i % 40}" y="{i // 40}" width="1" height="1" filter="url(#f)"/>' for i in range(count))
    return (f'{SVG}<defs><filter id="f"><feGaussianBlur stdDeviation="0.1"/></filter></defs>{shapes}</svg>').encode()


def test_svg_raster_fallback_is_capped():
    report = {}
    svg_operations(unsupported(MAX_RASTERIZED), Project(40, 40), "art", fallback=True, report=report)
    assert len(report["rasterized"]) == MAX_RASTERIZED
    with pytest.raises(VixlError) as caught:
        svg_operations(unsupported(100), Project(40, 40), "art", fallback=True)
    assert caught.value.code == "resource_limit"
    assert "svg_mode='appearance'" in str(caught.value)
