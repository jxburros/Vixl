"""Raster quality measured against exact references (see docs/render-parity.md): vector layers placed at
fractional positions or turned are drawn from their outlines, and gradients are dithered."""

import math

import numpy as np
import pytest

from vixl import Project
from vixl.design_render import gradient_image, vector_drawing
from vixl.render import resolved_layers


def coverage(image, background=(255, 255, 255), ink=(0, 0, 0)):
    a = np.asarray(image.convert("RGB"), dtype=np.float64) / 255
    bg, fg = np.array(background) / 255, np.array(ink) / 255
    axis = fg - bg
    return np.clip(((a - bg) @ axis) / (axis @ axis), 0, 1)


def exact_ellipse(cx, cy, r, width, height, n=16):
    """Box-filtered coverage of a disc, from n x n samples per pixel."""
    offsets = (np.arange(n) + 0.5) / n
    xs = (np.arange(width)[:, None] + offsets).ravel()
    out = np.zeros((height, width))
    for row in range(height):
        X, Y = np.meshgrid(xs, row + offsets)
        out[row] = (((X - cx) ** 2 + (Y - cy) ** 2) <= r * r).reshape(n, width, n).mean(axis=(0, 2))
    return out


def sharpness(cov):
    """Mean of the strongest 2% neighbour differences: resampling an edge lowers it."""
    g = np.concatenate([np.abs(np.diff(cov, axis=0)).ravel(), np.abs(np.diff(cov, axis=1)).ravel()])
    return np.sort(g)[-max(1, len(g) // 50):].mean()


def text_project(**place):
    p = Project(220, 60, "#ffffff")
    p.apply([{"type": "text", "text": "Sharp edges, small type", "name": "t", "size": 15, "color": "#000000", **place}])
    return p


@pytest.mark.parametrize("place", [{"x": 10.5, "y": 10}, {"x": 10, "y": 10.5}, {"x": 10, "baseline_y": 30}])
def test_text_at_a_fractional_position_stays_as_sharp_as_on_whole_pixels(place):
    # The layer used to be drawn on whole pixels and resampled (bicubic) into place: about 10% softer
    # edges and 5% more ink at a half-pixel offset.
    whole = coverage(text_project(x=10, y=10).render())
    moved = coverage(text_project(**place).render())
    assert sharpness(moved) > 0.97 * sharpness(whole)
    assert moved.sum() == pytest.approx(whole.sum(), rel=0.01)


def test_shapes_at_fractional_positions_match_their_exact_coverage():
    p = Project(120, 80, "#ffffff")
    p.apply([{"type": "shape", "shape": "ellipse", "name": "dot", "x": 10.5, "y": 20.25, "width": 40, "height": 40,
              "fill": "#000000"}])
    error = (coverage(p.render()) - exact_ellipse(30.5, 40.25, 20, 120, 80)) * 255
    # Resampled into place this was 2.7 levels rms and 50 at worst.
    assert np.sqrt((error**2).mean()) < 1.5
    assert np.abs(error).max() < 32


def test_a_filled_path_at_a_fractional_position_is_drawn_there():
    # A half-pixel move of a vertical edge leaves exactly one half-covered column.
    p = Project(60, 60, "#ffffff")
    p.apply([{"type": "shape", "shape": "path", "name": "bar", "x": 10.5, "y": 10, "width": 20, "height": 40,
              "path": "M0 0 L20 0 L20 40 L0 40 Z", "fill": "#000000"}])
    row = coverage(p.render())[30]
    assert row[10] == pytest.approx(0.5, abs=0.01)
    assert row[11:30].min() > 0.995
    assert row[9] < 0.005 and row[31] < 0.005


def test_rotated_text_is_drawn_from_its_outlines():
    upright = Project(260, 160, "#ffffff")
    upright.apply([{"type": "text", "text": "Rotated text", "name": "t", "size": 28, "x": 40, "y": 60, "color": "#000000"}])
    turned = Project(260, 160, "#ffffff")
    turned.apply([{"type": "text", "text": "Rotated text", "name": "t", "size": 28, "x": 40, "y": 60, "color": "#000000"},
                  {"type": "rotate", "target": "t", "value": 30}])
    a, b = coverage(upright.render()), coverage(turned.render())
    # Turning the drawn text with bicubic resampling kept about 85% of its edge contrast.
    assert sharpness(b) > 0.92 * sharpness(a)
    assert b.sum() == pytest.approx(a.sum(), rel=0.01)


@pytest.mark.parametrize("op", [
    {"type": "text", "text": "Plain glyphs", "size": 18},
    {"type": "rich-text", "markdown": "Some **bold** text", "size": 14},
    {"type": "shape", "shape": "path", "path": "M0 0 L40 0 L20 30 Z", "width": 40, "height": 30, "fill": "#0a0",
     "stroke": "#000", "stroke_width": 2},
    {"type": "shape", "shape": "path", "path": "M0 0 L40 0 L20 30 Z", "width": 40, "height": 30, "fill": "#0a0"},
    {"type": "shape", "shape": "ellipse", "width": 30, "height": 20, "fill": "#a00"},
    {"type": "shape", "shape": "rounded-rectangle", "width": 30, "height": 20, "radius": 6, "fill": "#a00"},
])
def test_vector_redraw_in_place_reproduces_the_drawn_layer(op):
    from vixl.render import layer_ink

    p = Project(100, 60, "#ffffff")
    p.apply([{**op, "name": "v", "x": 5, "y": 5}])
    layer = next(item for item in resolved_layers(p) if item["name"] == "v")
    # The drawn image includes what reaches past the box (a path's stroke); the redraw maps its pixels.
    drawn = layer_ink(p, layer, (5, 5, math.ceil(layer["width"]), math.ceil(layer["height"])))
    again = vector_drawing(p, layer)(drawn.size, (1, 0, 0, 1, 0, 0))
    assert np.array_equal(np.asarray(drawn), np.asarray(again))


def test_subtle_gradients_are_dithered_instead_of_banded():
    p = Project(600, 40, "#000000")
    layer = {"type": "gradient", "direction": "horizontal", "start": "#20242a", "end": "#2c3138", "width": 600, "height": 40}
    blue = np.asarray(gradient_image(p, layer, (600, 40)), dtype=float)[:, :, 2]
    # Undithered, each of the 14 levels was a flat band about 43 px wide.
    runs = max(len(run) for row in blue for run in np.split(row, np.nonzero(np.diff(row))[0] + 1))
    assert runs < 25
    # Averaged over 9 x 9 pixels the ramp is straight: no steps left.
    c = np.cumsum(np.cumsum(np.pad(blue, ((1, 0), (1, 0))), axis=0), axis=1)
    smooth = (c[9:, 9:] - c[:-9, 9:] - c[9:, :-9] + c[:-9, :-9]) / 81
    xs = np.arange(smooth.shape[1])
    line = np.polyval(np.polyfit(xs, smooth.mean(axis=0), 1), xs)
    assert np.sqrt(((smooth - line) ** 2).mean()) < 0.08


def test_dithering_keeps_whole_values_exact():
    p = Project(64, 8, "#000000")
    flat = np.asarray(gradient_image(p, {"type": "gradient", "direction": "horizontal", "start": "#336699",
                                         "end": "#336699"}, (64, 8)))
    assert (flat[..., :3] == (0x33, 0x66, 0x99)).all() and (flat[..., 3] == 255).all()
    ramp = np.asarray(gradient_image(p, {"type": "gradient", "direction": "horizontal", "start": "#000000",
                                         "end": "#ffffff"}, (64, 8)))
    assert (ramp[:, 0, :3] == 0).all() and (ramp[:, -1, :3] == 255).all()


def test_linear_gradient_matches_per_pixel_dither():
    from vixl.design_render import dither

    p = Project(300, 300, "white")
    for direction, w, h in (("vertical", 203, 131), ("horizontal", 131, 203)):
        layer = {"type": "gradient", "direction": direction, "start": "#20242a", "end": "#2c7138"}
        got = np.asarray(gradient_image(p, layer, (w, h)))
        ramp = np.linspace(0, 1, h if direction == "vertical" else w)
        ends = ((0x20, 0x2c), (0x24, 0x71), (0x2a, 0x38), (255, 255))
        rgb = np.stack([np.interp(ramp, [0, 1], pair) for pair in ends], -1)
        line = rgb[:, None, :] if direction == "vertical" else rgb[None, :, :]
        assert (got == np.floor(line + dither((h, w))[..., None]).astype(np.uint8)).all()
