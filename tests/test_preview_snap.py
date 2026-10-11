"""Reduced previews place layers on whole pixels instead of resampling each to its fractional place (#587)."""

import numpy as np

import vixl.render as render_module
from vixl import Project
from vixl.proxy import render_preview, scaled_project


def document():
    p = Project(1000, 800, "white")
    p.apply([{"type": "shape", "shape": "rectangle", "name": f"r{i}", "x": 13.3 + 97 * i, "y": 41.7 + 61 * i,
              "width": 70.4, "height": 50.2, "fill": "#224466"} for i in range(8)]
            + [{"type": "shape", "shape": "ellipse", "name": "dot", "x": 500.5, "y": 600.25, "width": 90, "height": 60,
                "fill": "#cc3300", "rotation": 20}]
            + [{"type": "text", "name": f"t{i}", "text": f"Label {i}", "size": 41, "color": "#111111",
                "x": 20.4 + 230 * i, "y": 700.6} for i in range(4)])
    return p


def counting(monkeypatch):
    calls = []
    original = render_module.warp

    def warp(image, size, data, sampling):
        if tuple(data[:2]) == (1, 0) and tuple(data[3:5]) == (0, 1):
            calls.append(data)  # a pure translation: the fractional-placement resample
        return original(image, size, data, sampling)

    monkeypatch.setattr(render_module, "warp", warp)
    return calls


def test_a_reduced_preview_does_no_fractional_placement_warp(monkeypatch):
    p = document()
    calls = counting(monkeypatch)
    preview = render_preview(p, 333, 333)
    assert preview.width <= 333 and not calls
    # The same scaled copy for an export (no snap) still places each layer exactly.
    scaled_project(p, 0.33).render()
    assert calls


def test_snapped_preview_stays_close_to_the_exact_one():
    p = document()
    snapped = np.asarray(scaled_project(p, 0.33, snap=True).render().convert("L"), float)
    exact = np.asarray(scaled_project(p, 0.33).render().convert("L"), float)
    assert snapped.shape == exact.shape
    assert np.abs(snapped - exact).mean() < 2
    # Ink lands within half a pixel of where it belongs.
    for image in (snapped, exact):
        assert (image < 200).sum() > 1000
    ys, xs = np.nonzero(snapped < 128)
    ye, xe = np.nonzero(exact < 128)
    assert abs(xs.mean() - xe.mean()) < 0.5 and abs(ys.mean() - ye.mean()) < 0.5


def test_full_size_render_and_export_keep_exact_placement(monkeypatch):
    p = document()
    calls = counting(monkeypatch)
    p.render()
    assert calls
