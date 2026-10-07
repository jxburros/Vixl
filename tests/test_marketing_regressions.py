"""Public Python regressions from the marketing-kit build (#120–132)."""

import io
import zipfile
from pathlib import Path

import numpy as np
from PIL import Image
import pytest

from vixl import Project
from vixl.errors import VixlError


def test_editable_svg_roundtrip_accepts_inert_defs_and_export_metadata():
    from vixl.imports import import_document

    original = Project(100, 80)
    original.apply({"type": "shape", "shape": "rectangle", "width": 30, "height": 20,
                    "x": 12, "y": 14, "fill": "red"})
    svg = original.export(format="SVG")
    assert b"<defs" in svg
    restored = Project(100, 80)
    import_document(restored, svg, "svg")
    assert restored.layer()["type"] == "shape"
    assert np.array_equal(np.asarray(original.render()), np.asarray(restored.render()))
    unused = svg.replace(b"<defs />", b'<defs><filter id="unused"><feGaussianBlur stdDeviation="3" /></filter></defs>')
    import_document(Project(100, 80), unused, "svg")


def test_referenced_svg_definitions_suggest_appearance_import():
    from vixl.imports import import_document

    data = b'<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20"><defs><linearGradient id="g" /></defs><rect width="20" height="20" fill="url(#g)" /></svg>'
    with pytest.raises(VixlError, match="svg_mode='appearance'") as error:
        import_document(Project(20, 20), data, "svg")
    assert error.value.code == "unsupported_svg"


def test_actual_brand_svg_roundtrips_editably_with_nested_viewports():
    import resvg_py
    from vixl.imports import import_document

    data = (Path(__file__).parents[1] / "assets/brand/digital-shift/SVG/horizontal-reverse.svg").read_bytes()
    p = Project(1200, 500)
    import_document(p, data, "svg")
    assert len(p.state["layers"]) == 12 and all(layer["type"] == "shape" for layer in p.state["layers"])
    expected = Image.open(io.BytesIO(resvg_py.svg_to_bytes(svg_string=data.decode()))).convert("RGBA")
    difference = np.abs(np.asarray(expected, dtype=int) - np.asarray(p.render(), dtype=int))
    assert difference.mean() < 0.1


def test_nested_svg_clipping_cannot_silently_drop_the_clip():
    from vixl.imports import import_document

    data = b'<svg xmlns="http://www.w3.org/2000/svg" width="50" height="50"><svg width="10" height="10"><rect width="20" height="20" /></svg></svg>'
    with pytest.raises(VixlError, match="Clipped nested SVG"):
        import_document(Project(50, 50), data, "svg")


def tiny_dot_pages():
    p = Project(1920, 1080, "white")
    p.apply([
        {"type": "master", "action": "add", "name": "dots"},
        {"type": "shape", "shape": "ellipse", "name": "dot", "width": 3, "height": 3, "fill": "black"},
        {"type": "repeat", "target": "dot", "count": 15, "dx": 17},
        {"type": "group", "name": "row", "targets": ["dot"]},
        {"type": "repeat", "target": "row", "count": 8, "dy": 17},
        {"type": "page", "action": "add", "name": "one", "master": "dots"},
        {"type": "page", "action": "add", "name": "two", "master": "dots"},
    ])
    return p


def test_tiny_repeat_contact_sheet_and_all_page_preview():
    from vixl.deck import contact_sheet
    from vixl.proxy import render_preview

    p = tiny_dot_pages()
    sheet = contact_sheet(p, width=240)
    assert sheet.width > 480 and np.asarray(sheet)[30:200, 16:240, :3].min() < 50
    preview = render_preview(p, 480, 480, page="all")
    assert preview.width <= 480 and preview.height <= 480


@pytest.mark.parametrize("kind", ["text", "rich-text"])
@pytest.mark.parametrize("prefix", ["    ", "\u00a0\u00a0\u00a0\u00a0", "\t"])
def test_whitespace_preserves_actual_indent_and_metrics(kind, prefix):
    p = Project(400, 100)
    for name, text in (("plain", "ab"), ("indented", prefix + "ab")):
        content = {"text": text} if kind == "text" else {"spans": [{"text": text}]}
        p.apply({"type": kind, "name": name, "size": 20, **content})
    plain, indented = p.inspect("plain"), p.inspect("indented")
    assert indented["ink_bounds"][0] - plain["ink_bounds"][0] > 20
    assert indented["line_bounds"][2] - plain["line_bounds"][2] > 20
    assert indented["ink_bounds"][2:] == pytest.approx(plain["ink_bounds"][2:])


@pytest.mark.parametrize("kind", ["text", "rich-text"])
def test_text_metrics_describe_ink_lines_and_baselines(kind):
    p = Project(400, 200)
    content = {"text": "Hi\nab"} if kind == "text" else {"spans": [{"text": "Hi\nab"}]}
    result = p.apply({"type": kind, "name": "t", "size": 20, "x": 30, "y": 40, **content}, detail="brief")
    layer = p.inspect("t")
    assert 0 < layer["x_height"] < layer["cap_height"] <= layer["ascent"]
    assert layer["descent"] > 0
    assert len(layer["baselines"]) == 2 and layer["baseline"] == layer["baselines"][0]
    assert layer["line_bounds"][3] > layer["ink_bounds"][3]
    assert layer["ink_bounds"][0] >= 30 and layer["ink_bounds"][1] >= 40
    added = next(iter(result["changes"]["layers"].values()))
    assert added["baseline"] == layer["baseline"]
    assert added["ink_bounds"] == layer["ink_bounds"]


def test_relative_python_link_is_stable_after_save_and_cwd_changes(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    source = Project(20, 20, "red")
    source.save(tmp_path / "tile.vixl")
    p = Project(40, 40)
    p.apply({"type": "link", "source": "tile.vixl", "name": "tile"})
    before = np.asarray(p.render())
    p.save(tmp_path / "output" / "host.vixl")
    monkeypatch.chdir(tmp_path / "output")
    assert np.array_equal(before, np.asarray(p.render()))
    loaded = Project.load("host.vixl", workspace=tmp_path)
    assert np.array_equal(before, np.asarray(loaded.render()))


def test_python_raster_page_selection_exports_contact_sheet(tmp_path):
    from vixl.deck import contact_sheet

    p = tiny_dot_pages()
    original_page = p.state["page"]
    data = p.export(tmp_path / "sheet.png", page="all", width=120, columns=1, labels=False)
    expected = contact_sheet(p, width=120, columns=1, labels=False)
    assert np.array_equal(np.asarray(Image.open(io.BytesIO(data)).convert("RGBA")), np.asarray(expected.convert("RGBA")))
    data = p.export(format="PNG", pages=["two"], width=100)
    assert Image.open(io.BytesIO(data)).size == contact_sheet(p, pages=["two"], width=100).size
    assert p.state["page"] == original_page


@pytest.mark.parametrize("kind", ["static", "saved", "timeline"])
def test_all_python_export_paths_protect_existing_files_and_allow_overwrite(tmp_path, kind):
    from vixl.timeline import export_timeline

    p = Project(16, 16, "red")
    path = tmp_path / ("out.png" if kind == "static" else "out.gif")
    if kind == "saved":
        p.apply({"type": "frame-save", "name": "red"})
    export = p.export if kind == "static" else p.export_animation if kind == "saved" else lambda *a, **kw: export_timeline(p, *a, **kw)
    export(path)
    original = path.read_bytes()
    with pytest.raises(VixlError, match="already exists"):
        export(path)
    assert path.read_bytes() == original
    export(path, overwrite=True)
    assert path.exists()


def text_deck():
    p = Project(1080, 1350, "#223")
    for name in ("cover", "inner", "last"):
        p.apply({"type": "page", "action": "add", "name": name})
        p.apply({"type": "text", "name": "label", "text": "Small label", "size": 26, "color": "white", "x": 20, "y": 20})
    return p


def test_deck_honors_thumbnail_width_and_threshold():
    p = text_deck()
    assert not p.check(checks=["legibility"], thumbnail_width=540)["issues"]
    result = p.check(checks=["legibility", "deck"], thumbnail_width=540)
    assert not [i for i in result["issues"] if i["check"] == "legibility"]
    result = p.check(checks=["legibility", "deck"], thumbnail_width=540, min_thumbnail_text=20)
    assert any(i["check"] == "legibility" for i in result["issues"])


def test_deck_profiles_change_font_and_word_checks():
    p = text_deck()
    projected = p.check(checks=["deck"], deck={"profile": "projected"})
    phone = p.check(checks=["deck"], deck={"profile": "phone"})
    screen = p.check(checks=["deck"], deck={"profile": "screen"})
    assert any(i["check"] == "min_font" for i in projected["issues"])
    for result in (phone, screen):
        assert not [i for i in result["issues"] if i["check"] == "min_font"]
        assert "type_scale" not in result["checked"]["checks"]
        assert result["checked"]["max_words"] > projected["checked"]["max_words"]
    with pytest.raises(VixlError, match="profile"):
        p.check(checks=["deck"], deck={"profile": "unknown"})


def test_transparent_glow_is_decorative_with_explicit_content_override():
    p = Project(300, 200)
    p.apply([{"type": "gradient", "name": "glow", "direction": "radial", "start": "red", "end": "transparent",
              "width": 200, "height": 200, "x": -50, "y": -50},
             {"type": "text", "name": "headline", "text": "Headline", "size": 50, "x": 30, "y": 40}])
    result = p.check(checks=["bounds", "overlap"])
    assert all(i["severity"] == "info" for i in result["issues"] if "glow" in i["layers"])
    p.apply({"type": "layer-intent", "target": "glow", "role": "content"})
    assert any(i["severity"] != "info" and "glow" in i["layers"] for i in p.check(checks=["bounds", "overlap"])["issues"])


@pytest.mark.parametrize("kind", ["add", "frame"])
@pytest.mark.parametrize("options", [{"downsample": "placed@2x"}, {"max_pixels": 20000}])
def test_downsampled_assets_keep_placement_and_original_provenance(tmp_path, kind, options):
    image = Image.fromarray(np.random.default_rng(4).integers(0, 255, (800, 1200, 3), dtype=np.uint8))
    source = tmp_path / "source.jpg"
    image.save(source, quality=90)
    p = Project(300, 200)
    p.apply({"type": kind, "path": str(source), "name": "photo", "width": 120, "height": 80, **options})
    layer = p.layer("photo")
    assert (layer["width"], layer["height"]) == (120, 80)
    embedded = p.image(layer["asset"])
    assert embedded.width <= 240 and embedded.height <= 160
    if "max_pixels" in options:
        assert embedded.width * embedded.height <= options["max_pixels"]
    assert layer["provenance"]["original_path"] == str(source)
    assert layer["provenance"]["original_size"] == [1200, 800]
    assert p.render().size == (300, 200)
    saved = tmp_path / "small.vixl"
    p.save(saved)
    with zipfile.ZipFile(saved) as archive:
        assert [n for n in archive.namelist() if n.startswith("assets/")] == [layer["asset"]]
    assert saved.stat().st_size < source.stat().st_size / 5
