import json
import zipfile

from PIL import Image
import pytest

from vixl import Project
from vixl.errors import VixlError
from vixl.interfaces import Session
from vixl.logo_package import recolor
from vixl.workflows import describe, dispatch


@pytest.fixture
def session(tmp_path):
    session = Session(workspace=tmp_path)
    session.create("logo.vixl", 800, 400)
    session.apply([
        {"type": "shape", "shape": "ellipse", "name": "mark", "x": 40, "y": 100, "width": 200, "height": 200,
         "fill": "#e63946", "stroke": "#1d3557", "stroke_width": 8},
        {"type": "text", "name": "word", "text": "Brand", "x": 300, "y": 160, "size": 90, "color": "#457b9d"},
        {"type": "look", "target": "mark", "look": "soft-shadow"},
    ])
    return session


def colors(path):
    import numpy as np

    pixels = np.asarray(Image.open(path).convert("RGBA")).reshape(-1, 4)
    return {tuple(int(v) for v in pixel[:3]) for pixel in pixels[pixels[:, 3] == 255]}


def test_logo_package_writes_variants_lockups_and_every_format(session, tmp_path):
    result = dispatch(session, "logo-package", {"output": "pkg", "mark": "mark", "wordmark": "word", "cmyk": True,
                                                "png_sizes": [128], "zip": True})
    root = tmp_path / "pkg"
    assert result["lockups"] == ["mark", "horizontal", "stacked"] and len(result["variants"]) == 5
    for name in ("svg/horizontal-full-color.svg", "pdf/stacked-mono-black.pdf", "pdf/mark-on-dark-cmyk.pdf",
                 "png/horizontal-mono-white-128w@3x.png", "icons/favicon.ico", "icons/apple-touch-icon.png",
                 "social/avatar.png", "social/og-image.png", "usage.html", "package.json",
                 "source/stacked-on-light.vixl"):
        assert (root / name).is_file(), name
    # 1x/2x/3x of each base width; strict SVG; CMYK PDF really is CMYK.
    assert [Image.open(root / f"png/mark-full-color-128w@{n}x.png").width for n in (1, 2, 3)] == [128, 256, 384]
    assert b"<image" not in (root / "svg/horizontal-mono-black.svg").read_bytes()
    assert b"/DeviceCMYK" in (root / "pdf/mark-on-dark-cmyk.pdf").read_bytes()
    assert Image.open(root / "social/og-image.png").size == (1200, 630)
    # Mono variants are one ink; the horizontal lockup is wider than tall, the stacked one taller than wide.
    assert colors(root / "png/horizontal-mono-black-128w@1x.png") == {(0, 0, 0)}
    assert colors(root / "png/horizontal-mono-white-128w@1x.png") == {(255, 255, 255)}
    horizontal, stacked = (Project.load(root / f"source/{n}-full-color.vixl").state["canvas"] for n in ("horizontal", "stacked"))
    assert horizontal["width"] > horizontal["height"] and stacked["height"] > stacked["width"]
    assert result["report"]["variants"]["mark-mono-black"]["effects_dropped"]
    assert "No EPS" in result["report"]["formats"]
    manifest = json.loads((root / "package.json").read_text())
    assert manifest["files"] and "usage" in manifest
    with zipfile.ZipFile(tmp_path / "pkg.zip") as archive:
        assert "svg/stacked-mono-white.svg" in archive.namelist()
    html = (root / "usage.html").read_text(encoding="utf-8")
    assert "dark photos" in html and "default-src 'none'" in html
    # Nothing is overwritten without overwrite=true.
    with pytest.raises(VixlError, match="already exist"):
        dispatch(session, "logo-package", {"output": "pkg", "mark": "mark", "wordmark": "word", "png_sizes": [128]})
    again = dispatch(session, "logo-package", {"output": "pkg", "mark": "mark", "wordmark": "word", "png_sizes": [128],
                                                "overwrite": True, "social": False, "icons": False, "proof": False})
    assert again["count"] < result["count"]


def test_raster_logo_traces_to_vector_and_reports_it(tmp_path):
    image = Image.new("RGBA", (300, 200), (0, 0, 0, 0))
    from PIL import ImageDraw

    ImageDraw.Draw(image).ellipse((40, 40, 160, 160), fill=(200, 30, 60, 255))
    image.save(tmp_path / "logo.png")
    session = Session(workspace=tmp_path)
    plain = dispatch(session, "logo-package", {"source": "logo.png", "output": "raster", "variants": ["full-color"],
                                                "icons": False, "social": False, "proof": False})
    assert "raster" in plain["report"]["source"] and any("svg/" in item for item in plain["report"]["skipped"])
    traced = dispatch(session, "logo-package", {"source": "logo.png", "output": "traced", "trace": True,
                                                 "variants": ["full-color", "mono-white"], "icons": False,
                                                 "social": False, "proof": False})
    assert "traced" in traced["report"]["source"]
    assert (tmp_path / "traced/svg/logo-mono-white.svg").is_file()


def test_failed_package_leaves_no_files(session, tmp_path):
    with pytest.raises(VixlError):
        dispatch(session, "logo-package", {"output": "bad", "mark": "mark", "wordmark": "missing-layer"})
    assert not (tmp_path / "bad").exists() or not any(p.is_file() for p in (tmp_path / "bad").rglob("*"))
    with pytest.raises(VixlError, match="png_sizes"):
        dispatch(session, "logo-package", {"output": "bad", "png_sizes": [2]})


def test_recolor_replaces_colours_and_silhouettes_images():
    project = Project(100, 100)
    from vixl.assets import add_image

    asset = add_image(project, Image.new("RGB", (20, 20), "white"))
    project.apply([{"type": "gradient", "name": "g", "x": 0, "y": 0, "width": 50, "height": 50, "start": "red", "end": "blue"},
                   {"type": "add", "asset": asset, "name": "photo"}])
    report = recolor(project, "#000000")
    gradient = project.layer("g")
    assert gradient["start"] == gradient["end"] == "#000000"
    assert report["images_silhouetted"] == 1 and report["notes"]


def test_logo_package_schema_is_described():
    action = describe()["actions"]["logo-package"]
    assert action["required"] == ["output"]
    assert set(action["properties"]) == set(action["fields"])
    assert "EPS" in action["summary"]


def test_logo_files_drop_the_source_canvas_colour_and_judge_contrast_by_ink(tmp_path):
    session = Session(workspace=tmp_path)
    session.create("fern.vixl", 800, 400, background="#ffffff")
    session.apply([
        {"type": "shape", "shape": "ellipse", "name": "mark", "x": 40, "y": 100, "width": 200, "height": 200,
         "fill": "#163d2e"},
        {"type": "text", "name": "word", "text": "Fernhill", "x": 300, "y": 160, "size": 90, "color": "#163d2e"},
    ])
    result = dispatch(session, "logo-package", {"output": "pkg", "mark": "mark", "wordmark": "word", "png_sizes": [128],
                                                "social": False, "icons": False, "proof": False})
    root = tmp_path / "pkg"
    white = Image.open(root / "png/mark-mono-white-128w@1x.png")
    assert white.mode == "RGBA" and white.getchannel("A").getextrema()[0] == 0
    assert colors(root / "png/mark-mono-white-128w@1x.png") == {(255, 255, 255)}
    assert b"rgb(255,255,255)" not in (root / "svg/horizontal-full-color.svg").read_bytes()
    variants = result["report"]["variants"]
    # Dark green ink reads on the light background, so on-light keeps full colour; on-dark switches to white.
    assert "reversed" not in variants["horizontal-on-light"] and variants["horizontal-on-light"]["contrast"] > 7
    assert "reversed" in variants["horizontal-on-dark"]
