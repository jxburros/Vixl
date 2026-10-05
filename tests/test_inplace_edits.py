"""Creation operations aimed at an existing layer edit it in place."""

import pytest

from vixl import Project, VixlError


def pixel(project, x, y):
    return project.render().convert("RGBA").getpixel((x, y))


def document():
    p = Project(200, 100, "white")
    p.apply(
        [
            {"type": "shape", "shape": "rectangle", "name": "bar", "x": 10, "y": 10, "width": 40, "height": 30,
             "fill": "#ff7f50"},
            {"type": "text", "name": "headline", "text": "Hello", "size": 20, "color": "black", "x": 80, "y": 10},
            {"type": "gradient", "name": "sky", "x": 0, "y": 60, "width": 200, "height": 40,
             "start": "#000000", "end": "#ffffff"},
            {"type": "solid", "name": "panel", "color": "#112233", "x": 150, "y": 0, "width": 50, "height": 50},
        ]
    )
    return p


# shape / solid / gradient / text with a target ------------------------------------------------


def test_shape_with_target_changes_fill_stroke_and_geometry_in_place():
    p = document()
    ident = p.layer("bar")["id"]
    result = p.apply({"type": "shape", "target": "bar", "fill": "#6b3f69", "stroke": "#000000",
                      "stroke_width": 2, "width": 60, "x": 20})
    assert result["success"]
    layers = p.state["layers"]
    assert [x["name"] for x in layers] == ["bar", "headline", "sky", "panel"]
    bar = p.layer("bar")
    assert bar["id"] == ident and bar["type"] == "shape"
    assert (bar["fill"], bar["stroke"], bar["stroke_width"]) == ("#6b3f69", "#000000", 2)
    # Only the geometry that was given changes: width and x, not height or y.
    assert (bar["x"], bar["y"], bar["width"], bar["height"]) == (20, 10, 60, 30)
    assert pixel(p, 40, 25) == (0x6b, 0x3f, 0x69, 255)
    p.undo()
    assert p.layer("bar")["fill"] == "#ff7f50"


def test_shape_with_target_changes_the_kind_and_corner_radius():
    p = document()
    p.apply({"type": "shape", "target": "bar", "shape": "rounded-rectangle", "radius": 6})
    bar = p.layer("bar")
    assert (bar["shape"], bar["radius"]) == ("rounded-rectangle", 6)
    assert len(p.state["layers"]) == 4


def test_shape_with_target_only_needs_the_fields_to_change():
    p = document()
    p.apply({"type": "shape", "target": "bar", "fill": "navy"})
    assert p.layer("bar")["fill"] == "navy" and p.layer("bar")["shape"] == "rectangle"


def test_gradient_with_target_recolors_the_gradient():
    p = document()
    ident = p.layer("sky")["id"]
    p.apply({"type": "gradient", "target": "sky", "start": "#010203", "end": "#a0b0c0", "direction": "horizontal"})
    sky = p.layer("sky")
    assert len(p.state["layers"]) == 4 and sky["id"] == ident
    assert (sky["start"], sky["end"], sky["direction"]) == ("#010203", "#a0b0c0", "horizontal")
    assert pixel(p, 0, 80)[:3] == (1, 2, 3) and pixel(p, 199, 80)[:3] == (0xa0, 0xb0, 0xc0)


def test_gradient_stops_replace_and_start_end_recolor_the_ends_of_existing_stops():
    p = document()
    stops = [{"offset": 0, "color": "#000000"}, {"offset": 0.5, "color": "#ff0000"}, {"offset": 1, "color": "#ffffff"}]
    p.apply({"type": "gradient", "target": "sky", "stops": stops, "direction": "horizontal"})
    assert p.layer("sky")["stops"] == stops
    p.apply({"type": "gradient", "target": "sky", "start": "#0000ff", "end": "#00ff00"})
    sky = p.layer("sky")
    assert [s["color"] for s in sky["stops"]] == ["#0000ff", "#ff0000", "#00ff00"]
    assert pixel(p, 0, 80)[:3] == (0, 0, 255) and pixel(p, 199, 80)[:3] == (0, 255, 0)


def test_gradient_recolor_through_colors_alias_is_normalized():
    p = document()
    result = p.apply({"type": "gradient", "target": "sky", "colors": ["#111111", "#eeeeee"]})
    assert p.layer("sky")["start"] == "#111111" and any("colors" in note for note in result["normalized"])


def test_solid_with_target_changes_color_and_size():
    p = document()
    p.apply({"type": "solid", "target": "panel", "color": "#ff0000", "height": 20})
    panel = p.layer("panel")
    assert (panel["fill"], panel["width"], panel["height"]) == ("#ff0000", 50, 20)
    assert len(p.state["layers"]) == 4


def test_text_with_target_edits_the_text_layer_instead_of_adding_one():
    p = document()
    ident = p.layer("headline")["id"]
    p.apply({"type": "text", "target": "headline", "size": 40})
    assert len(p.state["layers"]) == 4
    headline = p.layer("headline")
    assert headline["id"] == ident and headline["size"] == 40 and headline["text"] == "Hello"
    p.apply({"type": "text", "target": "headline", "text": "Bye", "color": "#ff0000", "x": 100, "y": 50, "name": "title"})
    title = p.layer("title")
    assert title["id"] == ident and title["text"] == "Bye" and title["color"] == "#ff0000"
    assert p.inspect("title")["resolved_bounds"][:2] == (100, 50)


def test_in_place_edit_centers_the_target_not_the_active_layer():
    p = document()
    p.apply({"type": "solid", "name": "last", "color": "red", "width": 10, "height": 10})  # Active layer.
    p.apply({"type": "shape", "target": "bar", "x": "center"})
    assert p.inspect("bar")["resolved_bounds"][0] == (200 - 40) // 2
    assert p.inspect("last")["resolved_bounds"][0] == 0


def test_in_place_percent_sizes_use_the_parent_group():
    p = document()
    p.apply([{"type": "group", "name": "g", "targets": ["bar", "panel"]}])
    content = p.layer("g")["content_width"]
    p.apply({"type": "shape", "target": "bar", "width": "50%"})
    assert p.layer("bar")["width"] == round(content / 2)


def test_creation_without_target_still_adds_layers():
    p = document()
    p.apply({"type": "shape", "shape": "ellipse", "name": "dot", "width": 5, "height": 5})
    assert len(p.state["layers"]) == 5


def test_shape_needs_a_shape_or_a_target():
    p = document()
    with pytest.raises(VixlError) as caught:
        p.apply({"type": "shape", "fill": "red"})
    assert "shape" in str(caught.value) and "target" in str(caught.value)
    with pytest.raises(VixlError) as caught:
        p.apply({"type": "text", "size": 12})
    assert "text" in str(caught.value) and "target" in str(caught.value)


# A target of the wrong kind names the operation to use -----------------------------------------


@pytest.mark.parametrize(
    "operation,hint",
    [
        ({"type": "shape", "target": "headline", "fill": "red"}, "text-set"),
        ({"type": "text", "target": "bar", "size": 12}, "shape"),
        ({"type": "gradient", "target": "bar", "start": "red"}, "shape"),
        ({"type": "solid", "target": "sky", "color": "red"}, "gradient"),
        ({"type": "add", "target": "bar", "asset": "nothing"}, "replace-contents"),
        ({"type": "adjustment", "target": "bar", "effects": [{"name": "grayscale"}]}, "effect"),
    ],
)
def test_target_of_the_wrong_kind_is_rejected_with_the_operation_to_use(operation, hint):
    p = document()
    before = p.state["layers"]
    with pytest.raises(VixlError) as caught:
        p.apply(operation)
    assert hint in str(caught.value) and caught.value.as_dict()["field"] == "target"
    assert p.state["layers"] == before


def test_unknown_target_is_still_an_error():
    p = document()
    with pytest.raises(VixlError):
        p.apply({"type": "shape", "target": "missing", "fill": "red"})


def test_text_with_target_can_be_centered_and_named_in_place():
    p = document()
    p.apply({"type": "text", "target": "headline", "x": "center", "y": "center"})
    x, y, w, h = p.inspect("headline")["resolved_bounds"]
    assert abs(x - (200 - w) / 2) <= 1 and abs(y - (100 - h) / 2) <= 1
    p.apply({"type": "text", "target": "headline", "name": "headline"})  # The same name is not a conflict.
    with pytest.raises(VixlError, match="already exists"):
        p.apply({"type": "text", "target": "headline", "name": "bar"})


def test_path_shape_edited_in_place_keeps_a_valid_path_view():
    p = document()
    p.apply({"type": "shape", "shape": "path", "name": "tri", "path": "M0 0 L10 0 L5 10 Z", "width": 20, "height": 20})
    p.apply({"type": "shape", "target": "tri", "path": "M0 0 L10 10 L0 10 Z", "width": 30, "height": 30, "fill": "red"})
    tri = p.layer("tri")
    assert tri["path"] == "M0 0 L10 10 L0 10 Z" and tri["path_view"] == [30, 30] and tri["fill"] == "red"
    with pytest.raises(VixlError, match="path"):
        p.apply({"type": "shape", "target": "bar", "shape": "path"})


def test_in_place_edit_keeps_effects_constraints_and_stacking():
    p = document()
    p.apply(
        [
            {"type": "layer-style", "target": "bar", "name": "drop-shadow", "settings": {"blur": 2}},
            {"type": "constrain", "target": "bar", "constraints": {"right": "canvas.right-10"}},
            {"type": "shape", "target": "bar", "fill": "#00ff00"},
        ]
    )
    bar = p.layer("bar")
    assert "drop-shadow" in bar["styles"] and bar["constraints"] == {"right": "canvas.right-10"}
    assert [x["name"] for x in p.state["layers"]] == ["bar", "headline", "sky", "panel"]


def test_edit_targets_are_discoverable_in_the_schema_and_cli():
    from vixl.commands import compile_command
    from vixl.schema import operation_schema

    variants = {
        v["properties"]["type"]["const"]: v for v in operation_schema()["properties"]["operations"]["items"]["oneOf"]
    }
    for kind in ("shape", "solid", "gradient", "text"):
        description = variants[kind]["properties"]["target"]["description"]
        assert "in place" in description and kind in description
    assert {"required": ["target"]} in variants["shape"]["anyOf"]
    assert compile_command("shape --target bar --fill red") == {"type": "shape", "target": "bar", "fill": "red"}
    assert compile_command("text add --target headline --size 40") == {"type": "text", "target": "headline", "size": 40}
    assert compile_command("gradient --target sky --start red")["target"] == "sky"
    assert compile_command("solid --target panel --color red")["target"] == "panel"
    p = document()
    p.apply(compile_command("shape --target bar --fill red"))
    assert p.layer("bar")["fill"] == "red" and len(p.state["layers"]) == 4
