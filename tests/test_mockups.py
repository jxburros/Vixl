"""Device and print mockups (#172): a design placed into templates as a live, corner-pinned link."""

import numpy as np
import pytest

from vixl import Project
from vixl.errors import VixlError
from vixl.interfaces import Session
from vixl.links import corner_pin, perspective_coefficients
from vixl.mockups import BUILTINS
from vixl.workflows import dispatch


@pytest.fixture
def workspace(tmp_path):
    poster = Project(600, 900, "#d62828")
    poster.apply([{"type": "shape", "shape": "rectangle", "name": "band", "x": 0, "y": 600, "width": 600,
                   "height": 300, "fill": "#003049"}])
    poster.save(tmp_path / "poster.vixl")
    post = Project(1080, 1080, "#2a9d8f")
    post.save(tmp_path / "post.vixl")
    return tmp_path


def session(workspace):
    return Session(workspace / "poster.vixl", workspace=workspace)


def test_every_builtin_template_builds_and_renders(workspace):
    s = session(workspace)
    result = dispatch(s, "mockup", {"design": "post.vixl", "mockup": list(BUILTINS), "output": "mockups"})
    assert result["count"] == len(BUILTINS) == 6
    for row in result["mockups"]:
        p = Project.load(workspace / row["path"])
        p._workspace = workspace
        links = [layer for layer in p.state["layers"] if layer["type"] == "link"]
        assert len(links) == len(row["slots"]) and all(layer.get("corner_pin") for layer in links)
        assert all(layer["clip"] for layer in links)  # clipped to the slot's surface
        image = p.render()
        slot = BUILTINS[row["mockup"]]["slots"][0]
        cx = round(sum(c[0] for c in slot["corners"]) / 4)
        cy = round(sum(c[1] for c in slot["corners"]) / 4)
        r, g, b = image.getpixel((cx, cy))[:3]
        assert g > r and g > 100, row["mockup"]  # the teal design shows in the middle of the slot


def test_poster_in_one_call_and_edits_show_on_the_next_render(workspace):
    s = session(workspace)
    result = dispatch(s, "mockup", {"design": "poster.vixl", "mockup": "poster-wall", "output": "wall.vixl"})
    assert result["mockups"][0]["path"] == "wall.vixl"
    mockup = Project.load(workspace / "wall.vixl")
    mockup._workspace = workspace
    link = mockup.layer("poster")
    assert link["source"] == "poster.vixl"
    x0, y0 = BUILTINS["poster-wall"]["slots"][0]["corners"][0]
    probe = (x0 + 100, y0 + 50)
    assert mockup.render().getpixel(probe)[:3][0] > 150  # red top of the poster
    poster = Project.load(workspace / "poster.vixl")
    poster.apply({"type": "solid", "name": "repaint", "color": "#2b9348"})
    poster.save(workspace / "poster.vixl", overwrite=True)
    again = Project.load(workspace / "wall.vixl")
    again._workspace = workspace
    r, g, b = again.render().getpixel(probe)[:3]
    assert g > r  # the edited design, without touching the mockup


def test_perspective_slot_warps_the_design_into_its_quad(workspace):
    s = session(workspace)
    dispatch(s, "mockup", {"design": "post.vixl", "mockup": "business-card", "output": "card.vixl",
                           "shade": False, "gloss": False})
    p = Project.load(workspace / "card.vixl")
    p._workspace = workspace
    p.apply({"type": "hide", "target": "card-surface"})
    p.apply({"type": "clip", "target": "card", "release": True})
    alpha = np.asarray(p.render().convert("RGB"))
    teal = (np.abs(alpha.astype(int) - (0x2a, 0x9d, 0x8f)).sum(axis=2) < 40)
    ys, xs = np.nonzero(teal)
    corners = BUILTINS["business-card"]["slots"][0]["corners"]
    assert xs.min() == pytest.approx(min(c[0] for c in corners), abs=4)
    assert xs.max() == pytest.approx(max(c[0] for c in corners), abs=4)
    # The top edge is slanted like the slot's: the design's top-left is lower than its top-right.
    left = ys[xs == corners[0][0] + 10].min()
    right = ys[xs == corners[1][0] - 10].min()
    assert left == pytest.approx(corners[0][1], abs=4) and right == pytest.approx(corners[1][1], abs=4)


def test_export_and_overwrite_rules(workspace):
    s = session(workspace)
    result = dispatch(s, "mockup", {"design": "post.vixl", "mockup": ["phone", "laptop"], "output": "out",
                                    "export": ["png"]})
    assert (workspace / "out" / "phone.png").exists() and (workspace / "out" / "laptop.png").exists()
    assert all(row["exports"] for row in result["mockups"])
    with pytest.raises(VixlError, match="already exists"):
        dispatch(s, "mockup", {"design": "post.vixl", "mockup": ["phone"], "output": "out"})
    with pytest.raises(VixlError, match="Unknown mockup"):
        dispatch(s, "mockup", {"design": "post.vixl", "mockup": "phon", "output": "x.vixl"})
    with pytest.raises(VixlError, match="design must be"):
        dispatch(s, "mockup", {"design": "missing.vixl", "mockup": "phone", "output": "x.vixl"})


def test_user_templates_in_the_workspace_catalog(workspace):
    s = session(workspace)
    template = {"description": "Square tile", "width": 800, "height": 800, "background": "#ffffff",
                "operations": [{"type": "shape", "shape": "rectangle", "name": "tile", "x": 90, "y": 90,
                                "width": 620, "height": 620, "fill": "#333333"}],
                "slots": [{"name": "art", "corners": [[100, 100], [700, 100], [700, 700], [100, 700]], "shade": False}]}
    dispatch(s, "mockup-save", {"name": "tile", "value": template})
    listed = dispatch(s, "mockup-list", {})["mockups"]
    assert listed["tile"]["slots"] == ["art"] and not listed["tile"]["builtin"] and listed["phone"]["builtin"]
    dispatch(s, "mockup", {"design": "post.vixl", "mockup": "tile", "output": "tile.vixl"})
    assert Project.load(workspace / "tile.vixl").layer("art")["type"] == "link"
    with pytest.raises(VixlError):
        dispatch(s, "mockup-save", {"name": "phone", "value": template})
    with pytest.raises(VixlError):
        dispatch(s, "mockup-save", {"name": "bad", "value": {**template, "slots": [{"name": "a", "corners": [[0, 0]]}]}})


def test_corner_pin_validation_and_math():
    assert corner_pin([[0, 0], [10, 0], [10, 10], [0, 10]]) == [[0, 0], [10, 0], [10, 10], [0, 10]]
    with pytest.raises(VixlError):
        corner_pin([[0, 0], [10, 10], [10, 0], [0, 10]])  # crossed: not convex
    coefficients = perspective_coefficients((100, 50), [[0, 0], [100, 0], [100, 50], [0, 50]])
    assert np.allclose(coefficients, [1, 0, 0, 0, 1, 0, 0, 0], atol=1e-9)


def test_corner_pinned_link_exports_as_a_reported_picture_in_pdf(workspace):
    p = Project(400, 400, "#ffffff")
    p.path = workspace / "doc.vixl"
    p._workspace = workspace
    p.apply({"type": "link", "name": "art", "source": "post.vixl", "width": 300, "height": 300, "x": 50, "y": 50,
             "corner_pin": [[20, 0], [300, 30], [280, 300], [0, 270]]})
    report = {}
    p.export(workspace / "doc.pdf", format="PDF", pdf_content="vector", report=report)
    reasons = [item["reason"] for items in report["raster_fallbacks"].values() for item in items] \
        if isinstance(report["raster_fallbacks"], dict) else [item["reason"] for item in report["raster_fallbacks"]]
    assert "corner-pinned linked document" in reasons
    p.apply({"type": "link", "target": "art", "corner_pin": None})
    assert "corner_pin" not in p.layer("art")
