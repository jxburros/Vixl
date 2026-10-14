"""The render parity harness (evals/render_parity) without a browser: every case builds its document and
markup, and the exact references and metrics measure what they claim."""

import math
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from evals.render_parity import cases, ideal, metrics  # noqa: E402
from evals.render_parity.browser import page  # noqa: E402


@pytest.mark.parametrize("case", cases.CASES, ids=lambda case: case.name)
def test_every_case_builds_its_document_and_markup(case):
    project = case.build()
    assert (project.state["canvas"]["width"], project.state["canvas"]["height"]) == (case.width, case.height)
    html = page(case.html(project), case.width, case.height, case.background, case.css, cases.FONTS)
    assert "@font-face" in html and "window.__ready" in html


def test_exact_references_have_the_right_area():
    disc = ideal.supersample(ideal.ellipse(20.3, 20.6, 12, 12), 41, 41)
    assert disc.sum() == pytest.approx(math.pi * 144, rel=0.002)
    square = ideal.supersample(ideal.polygon([(2.5, 2.5), (12.5, 2.5), (12.5, 12.5), (2.5, 12.5)]), 16, 16)
    assert square.sum() == pytest.approx(100, abs=1e-9)
    line = ideal.supersample(ideal.segment(0, 5.5, 20, 5.5, 1), 20, 10)
    assert line[5].tolist() == [1.0] * 20


def test_metrics_find_a_shift_banding_and_blur():
    a = np.zeros((10, 60))
    a[:, 20:24] = 1
    b = np.roll(a, 1, axis=1) * 0.5 + a * 0.5  # half a pixel to the right
    assert metrics.local_shift(a, b, (10, 0, 40, 10)) == pytest.approx(0.5, abs=0.1)
    steps = np.repeat(np.arange(10), 40)[None, :].repeat(20, axis=0) / 255
    smooth = np.linspace(0, 10, 400)[None, :].repeat(20, axis=0) / 255
    assert metrics.banding(steps) > 0.2 > metrics.banding(smooth)
    edge = ideal.gaussian(np.repeat((np.arange(80) >= 40)[None, :].astype(float), 30, axis=0), 3)[15, 20:60]
    assert metrics.sigma_from_rise(metrics.rise_10_90(edge)) == pytest.approx(3, rel=0.05)
