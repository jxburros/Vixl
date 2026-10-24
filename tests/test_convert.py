"""The conversion kit (vixl.convert): documents saved by older releases, and saved MCP calls from the 51-tool server.

The fixtures in tests/fixtures/convert/<revision>/ were saved and rendered by that revision's own code
(scripts/convert_fixtures.py). A converted document must open, match the published schema and, in preserve mode,
render like the old PNG within the tolerance below.
"""

import io
import json
from pathlib import Path
import zipfile

import numpy as np
from PIL import Image
import pytest

from vixl.convert import RULES, TOOLS, convert_batch, convert_file, convert_project, convert_state
from vixl.convert import strokes
from vixl.convert.documents import convert_directory, read_archive
from vixl.document_schema import validate_manifest
from vixl.errors import VixlError
from vixl.project import Project

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "convert"
DOCUMENTS = sorted(FIXTURES.glob("*/*.vixl"))

# A pixel differs when a channel moves by more than DIFFERENT levels. At most SHARE % of pixels may differ, and the
# mean difference stays under MEAN levels. Anti-aliased edges, the in-place drawing and gradient dithering of render
# parity (docs/project/render-parity.md) move single edge pixels and flat ramps by a few levels, which these numbers absorb;
# a lost fill, a moved stroke, a cut-off line or a colour shift of a whole area does not fit in them.
DIFFERENT, SHARE, MEAN = 32, 0.5, 2.0
# Measured differences with no stored field behind them (docs/reference/converting.md, "What is not converted"): (share, mean).
EXCEPTIONS = {
    "irregular": (2.5, MEAN),  # irregular ink ribbons are drawn in place since render parity (0.8 % from afaee33)
    ("v0.10.0", "text"): (5.0, 5.0),  # glyphs sit about a pixel higher than 0.10 set them (since 0.20)
    # Thick strokes: the old raster renderer supersampled shapes with Pillow and put their anti-aliased edges up to
    # half a pixel off the exact outline the flush rule now draws (1.2-2 % of these pixels, all on stroke edges).
    "shapes": (2.5, 3.0),
}


def render(project):
    return np.asarray(Image.open(io.BytesIO(project.export(format="PNG"))).convert("RGBA"), dtype=np.int16)


def difference(project, png):
    old = np.asarray(Image.open(png).convert("RGBA"), dtype=np.int16)
    new = render(project)
    assert old.shape == new.shape
    channel = np.abs(old - new).max(axis=2)
    return float((channel > DIFFERENT).mean() * 100), float(channel.mean())


def allowed(path):
    revision, name = path.parent.name, path.stem
    return EXCEPTIONS.get((revision, name), EXCEPTIONS.get(name, (SHARE, MEAN)))


def manifest_of(path):
    with zipfile.ZipFile(path) as archive:
        return json.loads(archive.read("project.json"))


def changes(report, kind=None):
    return [entry for entry in report["changes"] if kind is None or entry["change"] == kind]


@pytest.mark.parametrize("path", DOCUMENTS, ids=lambda p: f"{p.parent.name}/{p.stem}")
def test_fixtures_convert_open_validate_and_keep_their_look(path, tmp_path):
    output = tmp_path / "converted.vixl"
    report = convert_file(path, output)
    assert report["output"] == str(output)
    project = Project.load(output)
    assert validate_manifest(manifest_of(output)) == []
    share, mean = difference(project, path.with_suffix(".png"))
    most, average = allowed(path)
    assert share <= most and mean <= average, (report["changes"], share, mean)


@pytest.mark.parametrize("path", DOCUMENTS, ids=lambda p: f"{p.parent.name}/{p.stem}")
def test_current_mode_converts_without_baking_and_lists_what_changes(path, tmp_path):
    report = convert_file(path, tmp_path / "current.vixl", look="current")
    Project.load(tmp_path / "current.vixl")
    baked = {"open-shape-fill", "text-box-height", "irregular-strength", "diagram-line-height", "chart-padding",
             "heading-wrap", "scatter-distribution", "closed-stroke-geometry", "styled-stroke-align"}
    # An explicit centred alignment is only a difference once the renderer strokes closed shapes inside.
    quiet = {"styled-stroke-align"} if strokes.engine_model() == "inset" else set()
    assert not baked & {entry["change"] for entry in report["changes"]}
    preserved = convert_file(path, dry_run=True)
    for entry in changes(preserved):
        if entry["change"] in baked - quiet:
            assert any(w["change"] == entry["change"] and w.get("layer") == entry.get("layer")
                       for w in report["warnings"]), entry


def test_the_changes_a_release_needs_are_reported():
    def ids(revision, name, look="preserve"):
        return {entry["change"] for entry in convert_file(FIXTURES / revision / f"{name}.vixl", dry_run=True,
                                                          look=look)["changes"]}

    assert {"archive-format", "text-box-height"} <= ids("v0.10.0", "text")
    assert {"lookup-field", "temperature-tint-scale"} <= ids("v0.20.0", "effects")
    assert {"open-shape-fill", "styled-stroke-align"} <= ids("v0.20.0", "shapes")
    assert ids("v0.20.0", "chart") == {"chart-padding", "proofing-font"}
    assert "diagram-line-height" in ids("v0.20.0", "diagram")
    assert "irregular-strength" in ids("v0.22.1", "irregular")
    assert ids("v0.26.0", "designed") == {"house-style-version", "proofing-font"}  # its chart names no face
    assert ids("afaee33", "designed") == {"house-style-version", "proofing-font"}
    assert "lookup-field" not in ids("v0.22.1", "effects")  # converted on load by 0.21 to 0.26 already
    report = convert_file(FIXTURES / "v0.20.0" / "effects.vixl", dry_run=True)
    lookup = changes(report, "lookup-field")[0]
    assert lookup["layer"] == "sky" and lookup["field"] == "effects" and lookup["reason"]
    assert report["counts"] == {"changes": len(report["changes"]), "warnings": len(report["warnings"])}


def test_conversion_is_needed_for_the_old_look(tmp_path):
    # Opening the same documents with only the format bumped loses the lookup, the white fills and the clipped text.
    for name in ("effects", "shapes", "text"):
        path = FIXTURES / "v0.20.0" / f"{name}.vixl"
        manifest, assets = read_archive(path)
        naive = tmp_path / f"{name}.vixl"
        with zipfile.ZipFile(naive, "w") as archive:
            archive.writestr("project.json", json.dumps(manifest))
            for member, data in assets.items():
                archive.writestr(member, data)
        before, before_mean = difference(Project.load(naive), path.with_suffix(".png"))
        after, after_mean = difference(convert_project(path), path.with_suffix(".png"))
        assert after < before or after_mean < before_mean / 4, name


def test_format_one_archives_need_the_kit():
    path = FIXTURES / "v0.10.0" / "shapes.vixl"
    assert manifest_of(path)["format_version"] == 1
    with pytest.raises(VixlError, match="Unsupported project format"):
        Project.load(path)
    assert convert_project(path).state["canvas"]["width"] == 240


def test_preserve_keeps_the_old_look_through_later_edits():
    # A chart redraws from its recipe on every chart edit: preserve stored the old padding, current did not.
    path = FIXTURES / "v0.20.0" / "chart.vixl"
    results = {}
    for look in ("preserve", "current"):
        project = convert_project(path, look=look)
        project.apply([{"type": "chart", "target": "sales", "kind": "bar"}])
        results[look] = difference(project, path.with_suffix(".png"))[0]
    assert results["preserve"] <= SHARE < results["current"]
    # Regrowing an irregular outline from its recipe keeps the natural strength it was drawn with (and, with the
    # flush stroke rule, the source box it was traced from).
    path = FIXTURES / "v0.22.1" / "irregular.vixl"
    for look in ("preserve", "current"):
        project = convert_project(path, look=look)
        project.apply([{"type": "irregular", "target": "card", "seed": 3}])
        results[look] = difference(project, path.with_suffix(".png"))[0]
    assert results["preserve"] <= EXCEPTIONS["irregular"][0] < results["current"]


def test_pre_021_document_pins_fills_and_rescales_effects():
    report = convert_file(ROOT / "tests" / "fixtures" / "saved-by-0.20.vixl", dry_run=True)
    pinned = {entry["layer"] for entry in changes(report, "open-shape-fill")}
    assert pinned == {"squiggle rule", "open path"}  # the closed path keeps its own fill rule
    assert changes(report, "temperature-tint-scale")[0]["after"] == round(20 * 0.1185, 1)
    assert [w["layer"] for w in report["warnings"] if w["change"] == "effects-before-transform"] == ["tilted card"]


def test_history_is_converted_with_the_document(tmp_path):
    path = FIXTURES / "v0.20.0" / "effects.vixl"
    convert_file(path, tmp_path / "kept.vixl")
    project = Project.load(tmp_path / "kept.vixl")
    assert len(project.nodes) == len(manifest_of(path)["nodes"])
    project.undo(3)  # restoring an earlier revision validates it
    assert not any("lookup" in layer for layer in project.state["layers"])
    report = convert_file(path, tmp_path / "dropped.vixl", history="drop")
    dropped = Project.load(tmp_path / "dropped.vixl")
    assert len(dropped.nodes) == 1 and report["history"] == {"revisions": len(project.nodes), "kept": False}
    assert dropped.state == Project.load(tmp_path / "kept.vixl").state


def test_nothing_is_overwritten_without_overwrite(tmp_path):
    source = FIXTURES / "v0.20.0" / "chart.vixl"
    output = tmp_path / "chart.vixl"
    output.write_bytes(b"keep me")
    with pytest.raises(VixlError) as error:
        convert_file(source, output)
    assert error.value.code == "output_exists" and output.read_bytes() == b"keep me"
    with pytest.raises(VixlError):
        convert_file(source, source, overwrite=True)  # never onto the source
    convert_file(source, output, overwrite=True)
    Project.load(output)
    # Folders: an existing file fails that file only; the others convert.
    out = tmp_path / "out"
    (out / "v0.20.0").mkdir(parents=True)
    (out / "v0.20.0" / "chart.vixl").write_bytes(b"keep me")
    result = convert_directory(FIXTURES, out)
    assert [Path(item["source"]).name for item in result["failed"]] == ["chart.vixl"]
    assert (out / "v0.20.0" / "chart.vixl").read_bytes() == b"keep me"
    assert result["summary"]["converted"] == len(DOCUMENTS) - 1
    with pytest.raises(VixlError):
        convert_directory(FIXTURES, FIXTURES / "inside")


def test_workspace_variety_settings_lose_the_house_style_pin(tmp_path):
    source = tmp_path / "docs"
    (source / ".vixl").mkdir(parents=True)
    (source / ".vixl" / "variety.json").write_text(json.dumps({"variety": "low", "house_style": 2}))
    result = convert_directory(source, tmp_path / "out")
    assert json.loads((tmp_path / "out" / ".vixl" / "variety.json").read_text()) == {"variety": "low"}
    assert result["summary"]["by_change"] == {"house-style-version": 1}
    (source / ".vixl" / "variety.json").write_text(json.dumps({"house_style": "off"}))
    result = convert_directory(source, tmp_path / "kept")
    assert json.loads((tmp_path / "kept" / ".vixl" / "variety.json").read_text()) == {"house_style": "off"}
    assert result["summary"]["by_change"] == {}


def test_folder_conversion_skips_the_workspace_settings_folder(tmp_path):
    """`.vixl/` (where a workspace keeps rolls and variety settings) matches `*.vixl` but holds no documents."""
    source = tmp_path / "workspace"
    (source / ".vixl").mkdir(parents=True)
    (source / ".vixl" / "rolls.json").write_text("{}")
    (source / ".cache" / "old.vixl").parent.mkdir()
    (source / ".cache" / "old.vixl").write_bytes(b"not a document")
    Project(40, 30, "white").save(source / "poster.vixl")
    result = convert_directory(source, tmp_path / "out")
    assert result["failed"] == []
    assert result["summary"]["converted"] == 1
    assert (tmp_path / "out" / "poster.vixl").is_file()


def test_cli_converts_and_summarizes(tmp_path, monkeypatch, capsys):
    from vixl.cli import main
    from vixl.cli_summary import summarize

    monkeypatch.chdir(tmp_path)
    source = FIXTURES / "v0.20.0" / "effects.vixl"
    main(["--json", "convert", str(source), "-o", "new.vixl", "--report", "report.json"])
    result = json.loads(capsys.readouterr().out)
    assert result["summary"]["by_change"]["lookup-field"] == 1
    assert json.loads((tmp_path / "report.json").read_text()) == result
    Project.load(tmp_path / "new.vixl")
    text = summarize(result, "convert")
    assert text.startswith("converted effects.vixl (saved by 0.20.0) → new.vixl  3 changes")
    assert main(["convert", str(source), "-o", "new.vixl"]) == 1  # exists: refused
    assert "exists" in capsys.readouterr().err


# --- strokes ---------------------------------------------------------------------------------------------------------

def box(**fields):
    return {"id": "lyr_0000000000000001", "name": "box", "type": "shape", "shape": "rectangle", "x": 10, "y": 20,
            "width": 100, "height": 60, "stroke": "#000000", "stroke_width": 10, "fill": "#ffffff", **fields}


def state_with(*layers):
    return {"canvas": {"width": 400, "height": 300, "background": "white", "color_mode": "rgba8"},
            "layers": list(layers), "active_layer": None, "selection": None, "variables": {}, "presets": {}}


def test_flush_strokes_move_box_shapes_in_by_half_a_stroke():
    layers = [box(), box(name="rounded", id="lyr_0000000000000002", shape="rounded-rectangle"),
              box(name="explicit", id="lyr_0000000000000003", shape="rounded-rectangle", radius=12),
              box(name="turned", id="lyr_0000000000000004", rotation=30),
              box(name="hexagon", id="lyr_0000000000000005", shape="polygon", sides=6),
              box(name="thin", id="lyr_0000000000000006", width=8, height=8),
              box(name="unstroked", id="lyr_0000000000000007", stroke="transparent"),
              box(name="dashed", id="lyr_0000000000000008", shape="ellipse", dash="dashed"),
              box(name="cornered", id="lyr_0000000000000009", radius=6)]
    state = state_with(*layers)
    state["comps"] = {"before": {"lyr_0000000000000001": {"x": 30, "y": 40, "visible": True}}}
    ctx = convert_state(state, {}, saved=(0, 26, 0), stroke_model="flush")
    by = {layer["name"]: layer for layer in state["layers"]}
    assert {k: by["box"][k] for k in ("x", "y", "width", "height")} == {"x": 15, "y": 25, "width": 90, "height": 50}
    assert state["comps"]["before"]["lyr_0000000000000001"] == {"x": 35, "y": 45, "visible": True}
    assert by["rounded"]["radius"] == 12  # the default a fifth of the old short side, now stored
    assert by["explicit"]["radius"] == 12  # the outer corner keeps its radius
    turned = by["turned"]
    from vixl.render import transformed_size

    old_w, old_h = transformed_size(box(rotation=30))
    new_w, new_h = transformed_size(turned)
    assert (turned["x"] + new_w / 2, turned["y"] + new_h / 2) == pytest.approx((10 + old_w / 2, 20 + old_h / 2))
    assert (turned["width"], turned["height"]) == (90, 50)
    assert by["hexagon"]["x"] == 10 and by["unstroked"]["x"] == 10 and by["dashed"]["x"] == 10
    assert by["dashed"]["stroke_align"] == "center"
    assert by["hexagon"]["line_join"] == "round" and "stroke_align" not in by["hexagon"]
    assert by["cornered"]["shape"] == "rounded-rectangle" and by["cornered"]["radius"] == 6
    assert {"thin"} == {w["layer"] for w in ctx.warnings if w["change"] == "thick-stroke"}
    assert by["thin"]["width"] == 8 and any(w["layer"] == "thin" for w in ctx.warnings)
    moved = {entry["layer"] for entry in ctx.changes if entry["change"] == "closed-stroke-geometry"}
    assert moved == {"box", "rounded", "explicit", "turned", "cornered"}


def test_inset_engine_leaves_boxes_and_current_mode_only_warns():
    state = state_with(box())
    convert_state(state, {}, saved=(0, 26, 0), stroke_model="inset")
    assert state["layers"][0]["x"] == 10
    state = state_with(box())
    ctx = convert_state(state, {}, saved=(0, 26, 0), stroke_model="flush", look="current")
    assert state["layers"][0]["x"] == 10 and ctx.warnings[0]["change"] == "closed-stroke-geometry"
    state = state_with(box())
    convert_state(state, {}, saved=(0, 27, 0), stroke_model="flush")  # saved by a current release
    assert state["layers"][0]["x"] == 10


def test_irregular_source_shapes_move_with_the_stroke_rule():
    record = {"recipe": {"seed": 1, "strength": "subtle"}, "source": {k: v for k, v in box().items()
                                                                      if k not in ("id", "name", "type")}}
    state = state_with(box(shape="path", path="M0 0 L10 0 L10 10 Z", irregular=record))
    convert_state(state, {}, saved=(0, 26, 0), stroke_model="flush")
    assert state["layers"][0]["irregular"]["source"]["x"] == 15 and state["layers"][0]["x"] == 10


def test_engine_stroke_model_is_measured():
    assert strokes.engine_model() in ("inset", "flush")


def test_rules_without_a_fixture():
    heading = {"id": "lyr_00000000000000a1", "name": "headline", "type": "text", "text": "A long headline here",
               "x": 0, "y": 0, "width": 200, "height": 40, "size": 32, "font_role": "heading",
               "text_layout": {"width": 200}}
    tile = {"id": "lyr_00000000000000a2", "name": "tile", "type": "group", "x": 0, "y": 0, "width": 100,
            "height": 100, "pattern_scatter": {"seed": 1, "count": 10}}
    sky = {"id": "lyr_00000000000000a3", "name": "sky", "type": "solid", "x": 0, "y": 0, "width": 10, "height": 10,
           "color": "red", "lookup": {"name": "gone", "amount": 1}}
    state = state_with(heading, tile, sky)
    state["design_defaults"] = {"seed": 1, "house_style_version": 3, "direction": {"layout": "balanced-announcement", "house_style_version": 3}}
    state["canvas"].update(width=2626, height=3376, dpi=300,
                           physical={"unit": "in", "width": 8.5, "height": 11, "bleed": 0.125})
    ctx = convert_state(state, {}, saved=(0, 22, 0))
    assert heading["text_layout"]["wrap"] == "greedy"
    assert tile["pattern_scatter"]["distribution"] == "poisson"
    assert "lookup" not in sky and sky.get("effects") is None
    assert "house_style_version" not in state["design_defaults"]
    assert "house_style_version" not in state["design_defaults"]["direction"]
    warned = {entry["change"] for entry in ctx.warnings}
    assert {"lookup-field", "pdf-bleed", "house-style-version"} <= warned
    # A house-style-4 document already wraps headings balanced; nothing to keep.
    heading["text_layout"].pop("wrap")
    state["design_defaults"]["house_style_version"] = 4
    convert_state(state, {}, saved=(0, 26, 0))
    assert "wrap" not in heading["text_layout"]


# --- tool calls ------------------------------------------------------------------------------------------------------

AI = {"vixl_models_list": {}, "vixl_ai_generate": {"prompt": "a cat"}, "vixl_ai_remove": {},
      "vixl_ai_content_aware_fill": {"prompt": "sky"}, "vixl_ai_select_subject": {},
      "vixl_ai_remove_background": {"layer": "photo"}, "vixl_ai_select_object": {"label": "dog"},
      "vixl_ai_plan": {"prompt": "poster"}, "vixl_ai_analyze": {"capability": "describe"},
      "vixl_ai_upscale": {"layer": "photo"}, "vixl_ai_regenerate": {"layer": "photo", "prompt": "night"},
      "vixl_ai_extend": {"prompt": "sea", "left": 100}}
# Calls as agents made them on 0.26, at least one for every earlier tool name.
CALLS = [
    ("vixl_document_create", {"path": "a.vixl", "size": "instagram-post", "seed": 3, "variety": "low",
                              "font_pairing": "random", "workspace_fonts": False, "background": "white"}),
    ("vixl_document_open", {"path": "a.vixl", "upgrade": "accept"}),
    ("vixl_document_close", {"document": "a.vixl"}),
    ("vixl_document_inspect", {"target": "title", "detail": "full", "object": "dog"}),
    ("vixl_workspace_list", {"directory": "art", "offset": 0, "limit": 20}),
    ("vixl_template_create", {"path": "t.vixl", "name": "event-poster", "variables": {"title": "Hi"}}),
    ("vixl_history", {"action": "list", "offset": 0, "limit": 5}),
    ("vixl_history", {"action": "undo", "count": 2}),
    ("vixl_history", {"action": "checkpoint", "ref": "v1"}),
    ("vixl_history", {"action": "compact", "dry_run": True}),
    ("vixl_review_notes", {"action": "add", "text": "Bigger title"}),
    ("vixl_review_notes", {"action": "resolve", "note_id": "note_1"}),
    ("vixl_operations_apply", {"operations": [{"type": "solid", "color": "red"}], "dry_run": True,
                               "detail": "compact", "check": True, "preview": True, "suites": True, "repair": True}),
    ("vixl_compose", {"path": "b.vixl", "size": "story", "layout": "poster-classic", "font_pairing": "random",
                      "style": "swiss", "look": "grain", "operations": [{"type": "solid", "color": "red"}],
                      "check": True, "strict": True, "exports": ["b.png"], "overwrite": True, "seed": 2}),
    ("vixl_workflow", {"action": "proof", "request": {"items": ["a.png"], "output": "proof.html"}}),
    ("vixl_adapt_layout", {"sizes": ["story", "a4"], "formats": ["png"], "overwrite": True, "report": "layers",
                           "options": {"recompose": True}}),
    ("vixl_resource_add", {"kind": "palettes", "name": "mine", "value": ["#ffffff", "#000000"]}),
    ("vixl_import_image", {"path": "photo.jpg", "name": "photo", "credit": "Me", "license": "CC0",
                           "document": "a.vixl"}),
    ("vixl_import_document", {"format": "svg", "path": "logo.svg", "svg_mode": "auto"}),
    ("vixl_import_font", {"name": "Brand", "path": "brand.ttf"}),
    ("vixl_font_pair", {"pairing": "random", "seed": 3, "scope": "workspace"}),
    ("vixl_font_install", {"family": "Inter", "weight": 700, "role": "heading"}),
    ("vixl_styles", {"action": "list", "query": "bold"}),
    ("vixl_styles", {"action": "get", "name": "swiss"}),
    ("vixl_styles", {"action": "apply", "name": "swiss", "palette": True}),
    ("vixl_styles", {"action": "check", "name": "swiss"}),
    ("vixl_roll", {"purpose": "poster", "seed": 3, "apply": True, "slots": {"title": "Hi"}}),
    ("vixl_roll", {"purpose": "poster", "seed": 3, "locks": {"palette": "sage"}}),
    ("vixl_text_add", {"text": "Hello", "x": 10, "y": 10, "size": 24}),
    ("vixl_check", {"checks": ["contrast"], "min_contrast": 4.5, "targets": ["title"], "profile": "final"}),
    ("vixl_validate", {"profile": "print", "detail": "full", "severity": "error"}),
    ("vixl_measure", {"point": [1, 1], "histogram": "none"}),
    ("vixl_measure_spacing", {"targets": ["a", "b"], "axis": "horizontal", "expected": 10}),
    ("vixl_spatial", {"target": "title", "mode": "relations"}),
    ("vixl_pixels_inspect", {"target": "coin"}),
    ("vixl_render_preview", {"max_width": 400, "region": [0, 0, 10, 10], "page": 1, "guides": True,
                             "simulate": "deuteranopia"}),
    ("vixl_render_compare", {"before": "head~1", "mode": "diff"}),
    ("vixl_timeline_preview", {"time": "1s", "max_width": 400}),
    ("vixl_timeline_inspect", {"detail": "full", "targets": ["coin"]}),
    ("vixl_animation_preview", {"name": "walk", "scale": 2}),
    ("vixl_animation_inspect", {}),
    ("vixl_export_file", {"path": "a.pdf", "dpi": 300, "color_space": "cmyk", "overwrite": True}),
    ("vixl_export_batch", {"targets": [{"path": "a.png"}], "overwrite": True, "stop_on_error": True}),
    ("vixl_export_animation", {"path": "a.gif", "format": "gif", "scale": 2}),
    ("vixl_export_timeline", {"path": "a.mp4", "fps": 24}),
    ("vixl_export_audio", {"path": "a.wav", "sample_rate": 44100}),
    ("vixl_export_icons", {"directory": "icons", "icon_set": "apple"}),
    ("vixl_export_character", {"target": "hero", "output": "hero.vixl"}),
    ("vixl_guide", {"brief": "poster for a jazz night", "seed": 1}),
    ("vixl_guide", {}),
    ("vixl_capabilities", {"topic": "text", "fields": True}),
    ("vixl_operation_schema", {"types": ["text", "shape"]}),
    ("vixl_workflow_schema", {}),
    ("vixl_sizes_list", {"category": "social", "search": "story"}),
    ("vixl_layouts_list", {"name": "poster-classic"}),
    ("vixl_fonts", {"view": "font", "family": "Inter"}),
    ("vixl_fonts", {"view": "pairing", "pairing": "inter-tight-inter"}),
    ("vixl_fonts", {"category": "serif"}),
    ("vixl_brushes_list", {}),
    ("vixl_color", {"action": "convert", "colors": ["red"], "to": "hex"}),
    ("vixl_resources_list", {"kind": "palettes"}),
    ("vixl_resource_get", {"kind": "palettes", "name": "sage"}),
    ("vixl_job", {"action": "status", "id": "job_1"}),
    *AI.items(),
]


def validate_call(tool, args):
    """Check a converted call against the current server's action schemas and step schemas, without running it."""
    from vixl.convert.batches import ADVERTISED, AI_TOOLS
    from vixl.mcp_actions import ACTIONS, known, merged, model
    from vixl.steps import is_step, parse

    if tool in AI_TOOLS:
        return
    assert tool in ADVERTISED, tool
    args = dict(args)
    assert set(args) <= ADVERTISED[tool], (tool, args)
    if tool == "vixl_job":
        return
    options = args.pop("options", None)
    if tool == "vixl_apply":
        action = "workflow" if "workflow" in args else "create" if "create" in args else "batch"
    elif tool == "vixl_export":
        action = args.pop("kind")
    elif tool == "vixl_reference":
        topic = args.pop("topic", "start")
        action = topic if topic in ACTIONS["vixl_reference"] else "guide"
        if action == "guide":
            args["name"] = topic
    else:
        action = args.pop("action", next(iter(ACTIONS[tool])))
    known(tool, action)
    values = merged(options, **args)
    model(tool, action).model_validate(values)
    for index, op in enumerate(values.get("operations") or []):
        if is_step(op):
            parse(op, index)


def test_every_earlier_tool_is_mapped_and_its_calls_validate():
    assert len(TOOLS) == 64 and {name for name, _ in CALLS} == set(TOOLS)
    for name, arguments in CALLS:
        converted, report = convert_batch({"tool": name, "arguments": arguments})
        validate_call(converted["tool"], converted["arguments"])
        if name not in AI and name != "vixl_job":
            assert report["changes"][0]["change"] == "tool" and report["changes"][0]["before"] == name


def test_batch_shapes_prefixes_and_reports():
    calls = [{"tool": "vixl_import_image", "arguments": {"path": "p.jpg"}},
             {"type": "tool_use", "name": "mcp__vixl__vixl_render_preview", "input": {"max_width": 300}},
             {"jsonrpc": "2.0", "method": "tools/call", "params": {"name": "vixl_capabilities",
                                                                   "arguments": {"topic": "text"}}},
             {"tool": "vixl_aply", "arguments": {}},
             {"tool": "vixl_apply", "arguments": {"operations": [{"type": "layout-apply", "name": "poster-classic",
                                                                  "_house_style_version": 3}]}}]
    converted, report = convert_batch(calls)
    assert converted[0] == {"tool": "vixl_apply", "arguments": {"operations": [{"type": "import-image",
                                                                                "path": "p.jpg"}]}}
    assert converted[1]["name"] == "mcp__vixl__vixl_render"
    assert converted[1]["input"] == {"action": "preview", "options": {"max_width": 300}}
    assert converted[2]["params"] == {"name": "vixl_reference", "arguments": {"topic": "capabilities",
                                                                              "name": "text"}}
    assert converted[3] == calls[3]
    assert converted[4]["arguments"]["operations"] == [{"type": "layout-apply", "name": "poster-classic"}]
    assert [w["change"] for w in report["warnings"]] == ["unmapped-tool"]
    assert {c["change"] for c in report["changes"]} == {"tool", "operation-field"}
    # Calls already for the seven tools pass through unchanged.
    again, second = convert_batch(converted)
    assert again == converted and second["changes"] == []


def test_mcp_configs_lose_removed_flags():
    config = {"mcpServers": {"vixl": {"command": "vixl", "args": ["mcp", "--tools", "core", "--schema=slim",
                                                                  "--workspace", "."],
                                      "env": {"VIXL_MCP_SCHEMA": "full"}},
                             "ai": {"command": "vixl", "args": ["mcp", "--tools", "ai"]},
                             "other": {"command": "npx", "args": ["--tools", "core"]}}}
    converted, report = convert_batch(config)
    assert converted["mcpServers"]["vixl"] == {"command": "vixl", "args": ["mcp", "--workspace", "."], "env": {}}
    assert converted["mcpServers"]["ai"]["args"] == ["mcp", "--tools", "ai"]
    assert converted["mcpServers"]["other"] == config["mcpServers"]["other"]
    assert {c["change"] for c in report["changes"]} == {"server-flag", "server-env"}


def test_convert_batch_cli_writes_a_new_file(tmp_path, monkeypatch):
    from vixl.convert.cli import convert_batch as cli

    monkeypatch.chdir(tmp_path)
    (tmp_path / "calls.jsonl").write_text(json.dumps({"tool": "vixl_render_preview", "arguments": {}}) + "\n")
    result = cli(["calls.jsonl"])
    written = [json.loads(line) for line in (tmp_path / "calls-converted.jsonl").read_text().splitlines()]
    assert written == [{"tool": "vixl_render", "arguments": {"action": "preview"}}]
    assert result["summary"]["changes"] == 1
    with pytest.raises(VixlError):
        cli(["calls.jsonl"])


# --- documentation and boundaries --------------------------------------------------------------------------------------

def test_docs_describe_every_rule_and_the_generated_tool_table():
    from vixl.convert.batches import markdown_table

    text = (ROOT / "docs" / "reference" / "converting.md").read_text(encoding="utf-8")
    for rule, _ in RULES:
        assert f"| `{rule}` |" in text, rule
    table = text.split("<!-- conversion-table: start -->\n")[1].split("\n<!-- conversion-table: end -->")[0]
    assert table == markdown_table(), "regenerate the table from vixl.convert.batches.markdown_table()"


def test_the_engine_never_imports_the_kit():
    for path in (ROOT / "src" / "vixl").rglob("*.py"):
        if "convert" in path.relative_to(ROOT / "src" / "vixl").parts[:1] or path.name == "convert":
            continue
        text = path.read_text(encoding="utf-8")
        users = "from .convert" in text or "vixl.convert" in text
        assert not users or path.name == "cli.py", path


def test_documents_from_current_releases_pass_through():
    path = FIXTURES / "v0.20.0" / "chart.vixl"
    report = convert_file(path, dry_run=True, saved_by="0.27.0")
    assert report["changes"] == [] and report["warnings"] == [] and report["saved_by"] == "0.27.0"
    assert "padding" not in convert_project(path, saved_by="0.27.0").layer("sales")["chart"]


def test_open_transactions_are_rolled_back(tmp_path):
    project = Project(60, 40)
    project.begin()
    project.apply([{"type": "solid", "name": "pending", "color": "red"}])
    project.save(tmp_path / "open.vixl")
    report = convert_file(tmp_path / "open.vixl", tmp_path / "closed.vixl")
    converted = Project.load(tmp_path / "closed.vixl")
    assert converted.transaction is None and converted.state["layers"] == []
    assert [w["change"] for w in report["warnings"]] == ["transaction"]


def test_version_one_svg_payloads_become_documents(tmp_path):
    source = FIXTURES / "9d0a4ce" / "shapes.svg"
    report = convert_file(source, tmp_path / "shapes.vixl")
    assert report["saved_by"] == "0.26.0"
    share, mean = difference(Project.load(tmp_path / "shapes.vixl"), source.with_suffix(".png"))
    assert share <= EXCEPTIONS["shapes"][0] and mean <= EXCEPTIONS["shapes"][1]
    plain = tmp_path / "plain.svg"
    plain.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="4" height="4"/>')
    with pytest.raises(VixlError, match="no Vixl document"):
        convert_file(plain, dry_run=True)
