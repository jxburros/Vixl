"""The document rules of the conversion kit: each one rewrites a state saved by an older Vixl for the current code.

A rule reads the saved release and the mode from the context and records what it did with ``ctx.change`` and what it
could not do (or, in ``current`` mode, what will look different) with ``ctx.warn``. ``RULES`` is the ordered table;
``docs/converting.md`` describes every rule ID (a test keeps them in step).
"""

from copy import deepcopy
import re

from . import strokes

# The first release that saves documents in the current form. Documents from older releases are converted.
CURRENT_SINCE = (0, 27, 0)
RENDER_CHANGES = (0, 21, 0)  # effects before transforms, temperature/tint scale, unfilled open shapes, lookup effect
GROWING_TEXT = (0, 24, 0)  # width-only text boxes grow to their lines (#452)
PRECISE_BLEED = (0, 23, 0)
# House-style version a document without a stamp was made with (the removed code read 2 as the default).
UNSTAMPED_HOUSE_STYLE = 2
# Old temperature and tint were offsets on encoded RGB: temperature ±v/10000 on red and blue, tint +v/200 on red and
# blue and -v/100 on green. The current ones are luma-keeping gains. These factors match the red-blue (temperature)
# and red-green (tint) difference they give a mid grey, which is the best a single number can do.
TEMPERATURE_FACTOR = 0.1185
TINT_FACTOR = 17.6
DIAGRAM_LEADING = 0.18  # diagrams before 0.23 added 0.18 × size to the font's own line pitch


def parse_version(text):
    match = re.match(r"(\d+)\.(\d+)(?:\.(\d+))?", str(text or ""))
    return tuple(int(part or 0) for part in match.groups()) if match else None


class Context:
    """What the rules need: the mode, the release that saved the document, a scratch project over the state (for
    colours, fonts and measurement) and the report lists."""

    def __init__(self, look, saved, project, stroke_model, quiet=False):
        self.look = look
        self.saved = saved
        self.project = project
        self.stroke_model = stroke_model
        self.quiet = quiet
        self.changes = []
        self.warnings = []
        defaults = project.state.get("design_defaults") or {}
        stamp = defaults.get("house_style_version")
        self.house_style = stamp if isinstance(stamp, int) else UNSTAMPED_HOUSE_STYLE

    @property
    def preserve(self):
        return self.look == "preserve"

    def older(self, version):
        """Whether the document was saved before ``version`` (an unknown release counts as older)."""
        return self.saved is None or self.saved < version

    def change(self, change, reason, layer=None, field=None, **values):
        if not self.quiet:
            self.changes.append(_entry(change, reason, layer, field, values))

    def warn(self, change, reason, layer=None, field=None, **values):
        if not self.quiet:
            self.warnings.append(_entry(change, reason, layer, field, values))


def _entry(change, reason, layer, field, values):
    entry = {"change": change}
    if layer is not None:
        entry["layer"] = layer.get("name") or layer.get("id")
    if field is not None:
        entry["field"] = field
    entry["reason"] = reason
    entry.update({key: deepcopy(value) for key, value in values.items()})
    return entry


def layers(state):
    """Every layer dict in the state: the page's layers and those kept in pages, masters and symbols."""
    found = []

    def walk(value):
        if isinstance(value, list):
            if value and all(isinstance(item, dict) and isinstance(item.get("id"), str)
                             and item["id"].startswith("lyr_") and "type" in item for item in value):
                found.extend(value)
            for item in value:
                walk(item)
        elif isinstance(value, dict):
            for item in value.values():
                walk(item)

    walk(state)
    seen, unique = set(), []
    for layer in found:
        if id(layer) not in seen:
            seen.add(id(layer))
            unique.append(layer)
    return unique


# --- rules ----------------------------------------------------------------------------------------------------------

def lookup_field(ctx, state):
    """Before 0.21 a layer's LUT was a ``lookup`` field; it is a ``lookup`` effect at the end of the stack."""
    luts = state.get("luts") or {}
    for layer in layers(state):
        old = layer.pop("lookup", None)
        if not old:
            continue
        if not isinstance(old, dict) or old.get("name") not in luts:
            ctx.warn("lookup-field", "The layer named a LUT the document does not hold; the lookup was dropped",
                     layer, "lookup")
            continue
        layer.setdefault("effects", []).append({"id": f"fx_lut_{layer['id'][4:]}", "name": "lookup",
                                                "lut": old["name"], "amount": old.get("amount", 1), "enabled": True,
                                                "selection": None})
        ctx.change("lookup-field", "The lookup field became a lookup effect at the end of the effect stack, where it "
                   "rendered", layer, "effects", lut=old["name"])


def house_style_version(ctx, state):
    """Documents no longer record the house-style version they were rolled with."""
    removed = []

    def walk(value, path):
        if isinstance(value, dict):
            for key in list(value):
                if key in ("house_style_version", "_house_style_version"):
                    removed.append(("/".join(path + [key]), value.pop(key)))
                else:
                    walk(value[key], path + [key])
        elif isinstance(value, list):
            for index, item in enumerate(value):
                walk(item, path + [str(index)])

    walk(state, [])
    for path, value in removed:
        ctx.change("house-style-version", "House-style versioning was removed; every document uses the current "
                   "house style", field=path, before=value)
    direction = (state.get("design_defaults") or {}).get("direction")
    if removed and direction and ctx.house_style < 4:
        ctx.warn("house-style-version", f"The document was rolled with house style {ctx.house_style}: a new roll "
                 "or layout-apply from its stored seed gives the current house style's result (layouts, pairings, "
                 "palettes and details such as pills and highlighted dates). What is already on the canvas is "
                 "unchanged.")


def open_shape_fill(ctx, state):
    """Before 0.21 open shapes (lines, waves, open paths) with a stroke and no fill were filled white."""
    if not ctx.older(RENDER_CHANGES):
        return
    for layer in layers(state):
        if layer.get("type") != "shape" or "fill" in layer or strokes.closed(layer):
            continue
        if not strokes.stroke_visible(ctx.project, layer):
            continue
        if ctx.preserve:
            layer["fill"] = "white"
            ctx.change("open-shape-fill", "Open shapes with a stroke and no fill were filled white before 0.21; the "
                       "white fill is now explicit", layer, "fill", after="white")
        else:
            ctx.warn("open-shape-fill", "This open shape was filled white before 0.21 and is now unfilled", layer)


def effects_before_transform(ctx, state):
    if not ctx.older(RENDER_CHANGES):
        return
    for layer in layers(state):
        turned = (layer.get("rotation", 0) or 0) % 360 or layer.get("flip_x") or layer.get("flip_y") \
            or layer.get("skew_x") or layer.get("skew_y") or layer.get("affine")
        if turned and any(isinstance(e, dict) and e.get("enabled", True) for e in layer.get("effects") or []):
            ctx.warn("effects-before-transform", "Effects now run in the layer's own frame before rotate, flip and "
                     "skew, so blur room, shadows and spatial filters turn with the layer; there is no automatic "
                     "equivalent of the old order", layer, "effects")


def temperature_tint(ctx, state):
    """Before 0.21 temperature and tint used an additive scale; the current ones are luma-keeping gains."""
    if not ctx.older(RENDER_CHANGES):
        return
    for layer in layers(state):
        for effect in layer.get("effects") or []:
            if not isinstance(effect, dict) or effect.get("name") not in ("temperature", "tint"):
                continue
            amount = effect.get("amount", 0)
            if not isinstance(amount, (int, float)):
                continue
            name = effect["name"]
            if ctx.preserve:
                factor = TEMPERATURE_FACTOR if name == "temperature" else TINT_FACTOR
                new = max(-100, min(100, round(amount * factor, 1)))
                effect["amount"] = int(new) if float(new).is_integer() else new
                ctx.change("temperature-tint-scale", f"{name} moved to the multiplicative -100…100 scale: "
                           f"{amount} on the old scale is about {effect['amount']} on the new one (approximate)",
                           layer, f"effects.{name}.amount", before=amount, after=effect["amount"])
                if new != round(amount * factor, 1):
                    ctx.warn("temperature-tint-scale", f"The old {name} {amount} is stronger than the new scale "
                             "reaches; it was capped at ±100", layer, f"effects.{name}.amount")
            elif abs(amount) > 100:
                effect["amount"] = 100 if amount > 0 else -100
                ctx.change("temperature-tint-scale", f"{name} {amount} is outside the new -100…100 scale and was "
                           "capped", layer, f"effects.{name}.amount", before=amount, after=effect["amount"])
            else:
                ctx.warn("temperature-tint-scale", f"{name} {amount} reads on the new scale: temperature looks "
                         "stronger and tint weaker than before", layer, f"effects.{name}.amount")
    timeline_effects = [track for track in _tracks(state) if str(track.get("property", "")).startswith("effect:")]
    if timeline_effects:
        ctx.warn("temperature-tint-scale", "Keyframed effect amounts were not rescaled; check animated temperature "
                 "and tint")


def text_box_height(ctx, state):
    """Before 0.24 a text box given only a width kept its height and cut off lines that did not fit; it now grows."""
    if not ctx.older(GROWING_TEXT):
        return
    from ..checks import boxed_text_need

    for layer in layers(state):
        settings = layer.get("text_layout")
        if layer.get("type") != "text" or not isinstance(settings, dict) or "width" not in settings \
                or "height" in settings:
            continue
        try:
            need = boxed_text_need(ctx.project, layer)
        except Exception as exc:  # noqa: BLE001 - a font the text engine cannot read
            ctx.warn("text-box-height", f"Could not measure the text ({exc}); its box may now grow", layer)
            continue
        if not need or need[1] <= layer.get("height", 0) + 1:
            continue
        if ctx.preserve:
            settings["height"] = layer["height"]
            ctx.change("text-box-height", "The box kept its height and cut off the lines below it; the height is "
                       "now explicit so it still does (check reports the overflow)", layer, "text_layout.height",
                       after=layer["height"])
        else:
            ctx.warn("text-box-height", f"The box grows from {layer['height']} to about {need[1]} px, so lines that "
                     "were cut off now show", layer)


def irregular_strength(ctx, state):
    """Irregular and tear recipes stored before 0.23 have no strength and were drawn at natural; the default is now
    subtle. The drawn geometry is stored, so only a later edit of the recipe is affected."""
    for layer in layers(state):
        for key in ("irregular", "tear"):
            record = layer.get(key)
            recipe = record.get("recipe") if isinstance(record, dict) else None
            if not isinstance(recipe, dict) or "strength" in recipe:
                continue
            if ctx.preserve:
                recipe["strength"] = "natural"
                ctx.change("irregular-strength", f"The {key} recipe was made at the old default strength; it is now "
                           "explicit (the default is subtle)", layer, f"{key}.recipe.strength", after="natural")
            else:
                ctx.warn("irregular-strength", f"Editing this {key} redraws it at the subtle default instead of "
                         "natural", layer)


def diagram_line_height(ctx, state):
    """Diagrams made before 0.23 have no line height and set label leading at 0.18 × size over the font's pitch."""
    from ..craft import natural_height
    from ..text import font_data

    for name, record in (state.get("diagrams") or {}).items():
        spec = record.get("spec") if isinstance(record, dict) else None
        if not isinstance(spec, dict) or "line_height" in spec:
            continue
        if not ctx.preserve:
            ctx.warn("diagram-line-height", f"Diagram {name!r}: the next diagram-set sets its labels at the caption "
                     "line height", field=f"diagrams.{name}")
            continue
        font = spec.get("font", "DejaVuSans.ttf")
        try:
            if spec.get("font_role"):
                from ..render import resolve_font

                font, _ = resolve_font(ctx.project, spec["font_role"])
            elif font == "DejaVuSans.ttf" and (state.get("typography") or {}).get("body"):
                from ..render import resolve_font

                font, _ = resolve_font(ctx.project, "body")
            pitch = natural_height(font_data(ctx.project, {"font": font, "text": "x"}), 100) / 100
        except Exception:  # noqa: BLE001 - the old code fell back to fixed leading too
            pitch = 1.164  # DejaVu Sans
        spec["line_height"] = round(pitch + DIAGRAM_LEADING, 3)
        ctx.change("diagram-line-height", "The label leading the diagram was laid out with is now an explicit line "
                   "height (the default is the caption line height)", field=f"diagrams.{name}.spec.line_height",
                   after=spec["line_height"])


def chart_padding(ctx, state):
    """Charts in documents made before house style 3 were padded 0.8 × their font size; the padding is now two
    spacing units. Charts redraw from their recipe on every chart edit."""
    if ctx.house_style >= 3:
        return
    from ..charts import Style

    for layer in layers(state):
        recipe = layer.get("chart")
        if layer.get("type") != "group" or not isinstance(recipe, dict) or "padding" in recipe:
            continue
        if not ctx.preserve:
            ctx.warn("chart-padding", "The next chart edit pads the chart by two spacing units instead of 0.8 × "
                     "its font size", layer)
            continue
        try:
            size = Style(ctx.project, recipe, layer.get("content_width", layer["width"]),
                         layer.get("content_height", layer["height"])).fs
        except Exception as exc:  # noqa: BLE001
            ctx.warn("chart-padding", f"Could not work out the chart's font size ({exc}); its padding may change "
                     "on the next chart edit", layer)
            continue
        recipe["padding"] = int(round(size * 0.8))
        ctx.change("chart-padding", "The chart's padding is now explicit, so a chart edit keeps the old spacing",
                   layer, "chart.padding", after=recipe["padding"])


def heading_wrap(ctx, state):
    """Before house style 4 a heading's text box broke lines greedily; a new box on a heading now balances them."""
    if ctx.house_style >= 4:
        return
    from ..text import is_heading

    for layer in layers(state):
        settings = layer.get("text_layout")
        if layer.get("type") != "text" or not isinstance(settings, dict) or "width" not in settings \
                or "wrap" in settings:
            continue
        try:
            heading = is_heading(ctx.project, layer)
        except Exception:  # noqa: BLE001
            heading = False
        if not heading:
            continue
        if ctx.preserve:
            settings["wrap"] = "greedy"
            ctx.change("heading-wrap", "The heading's line breaks are greedy, as they were drawn; resizing its box "
                       "would otherwise balance them", layer, "text_layout.wrap", after="greedy")
        else:
            ctx.warn("heading-wrap", "Resizing this heading's box balances its lines", layer)


def scatter_distribution(ctx, state):
    """pattern-scatter tiles made before progressive layout have no distribution; a rebuild now lays them out
    progressively, which moves every copy."""
    for layer in layers(state):
        recipe = layer.get("pattern_scatter")
        if not isinstance(recipe, dict) or "distribution" in recipe:
            continue
        if ctx.preserve:
            recipe["distribution"] = "poisson"
            ctx.change("scatter-distribution", "The tile's layout is now explicit, so a rebuild keeps its copies "
                       "where they are", layer, "pattern_scatter.distribution", after="poisson")
        else:
            ctx.warn("scatter-distribution", "Rebuilding this tile lays it out progressively; every copy moves", layer)


def closed_stroke_geometry(ctx, state):
    """Plain closed box shapes: the flush stroke model moves the ink half a stroke outward (see strokes.py)."""
    if ctx.stroke_model != "flush" or not ctx.older(CURRENT_SINCE):
        return
    animated = {track.get("target") for track in _tracks(state) if track.get("property") in strokes.GEOMETRY_TRACKS}
    for layer in layers(state):
        holders = [(layer, layer)]
        record = layer.get("irregular")
        if isinstance(record, dict) and isinstance(record.get("source"), dict):
            # The shape an irregular outline was made from comes back when the irregular is removed.
            holders.append(({**record["source"], "type": "shape"}, record["source"]))
        for view, target in holders:
            if not strokes.plain_box(view) or not strokes.stroke_visible(ctx.project, view):
                continue
            field = None if target is layer else "irregular.source"
            if not ctx.preserve:
                ctx.warn("closed-stroke-geometry", "The stroke now runs from the box edge inward instead of starting "
                         "half a stroke in, so the shape looks half a stroke larger", layer, field)
                continue
            fields, problem = strokes.inset_box(view)
            if fields is None:
                ctx.warn("closed-stroke-geometry", f"The stroke could not be kept in place: {problem}", layer, field)
                continue
            before = {key: view.get(key) for key in fields}
            target.update(fields)
            ctx.change("closed-stroke-geometry", "The box moved in by half the stroke on every side, so the flush "
                       "stroke lands where the inset one was", layer, field or "x, y, width, height",
                       before=before, after=fields)
            if target is not layer:
                continue
            if layer["id"] in animated:
                ctx.warn("closed-stroke-geometry", "The layer's position or size is keyframed; the keyframes were "
                         "not shifted", layer, "timeline")
            # Layer comps store their own x/y; they move with the box so applying a comp keeps the stroke in place.
            for comp in _comps(state):
                saved = comp.get(layer["id"])
                if isinstance(saved, dict):
                    for key in ("x", "y"):
                        if isinstance(saved.get(key), (int, float)):
                            saved[key] = strokes.number(saved[key] + fields[key] - before[key])


def styled_stroke_align(ctx, state):
    """A styled stroke on a closed shape was centred on the outline by default; closed shapes now stroke inside."""
    if not ctx.older(CURRENT_SINCE):
        return
    for layer in layers(state):
        if layer.get("type") != "shape" or "stroke_align" in layer or not strokes.closed(layer):
            continue
        if not (strokes.styled(layer) or strokes.catalog(layer)) or not strokes.stroke_visible(ctx.project, layer):
            continue
        if ctx.preserve:
            layer["stroke_align"] = "center"
            ctx.change("styled-stroke-align", "The styled or catalog shape's stroke was centred on the outline by "
                       "default; that is now explicit (closed shapes default to inside)", layer, "stroke_align",
                       after="center")
        elif ctx.stroke_model == "flush":
            ctx.warn("styled-stroke-align", "The styled stroke now sits inside the shape instead of on its outline",
                     layer)


def rectangle_radius(ctx, state):
    """A rectangle with a radius drew rounded in PNG and square in SVG and PDF; a radius now makes a rounded
    rectangle everywhere (normalize does the same for new operations)."""
    if not ctx.older(CURRENT_SINCE):
        return
    for layer in layers(state):
        radius = layer.get("radius")
        if layer.get("type") != "shape" or layer.get("shape") != "rectangle" or not radius or radius == [0, 0, 0, 0]:
            continue
        if ctx.preserve:
            layer["shape"] = "rounded-rectangle"
            ctx.change("rectangle-radius", "A rectangle with a radius is stored as the rounded rectangle it drew as",
                       layer, "shape", before="rectangle", after="rounded-rectangle")
        else:
            ctx.warn("rectangle-radius", "This rectangle has a radius: PNG drew it rounded and SVG and PDF square",
                     layer, "radius")


def polygon_joins(ctx, state):
    """Plain polygons, stars and shortcut shapes kept their box but drew round outer corners; the flush rule mitres
    them."""
    if ctx.stroke_model != "flush" or not ctx.older(CURRENT_SINCE):
        return
    for layer in layers(state):
        if not strokes.plain_corners(layer) or "line_join" in layer or not strokes.stroke_visible(ctx.project, layer):
            continue
        if ctx.preserve:
            layer["line_join"] = "round"
            ctx.change("polygon-joins", "The stroke's corners were round; that is now explicit (the default is "
                       "mitred)", layer, "line_join", after="round")
        else:
            ctx.warn("polygon-joins", "The stroke's outer corners are now sharp instead of round", layer)


def thick_stroke(ctx, state):
    """A plain stroke too wide for its shape drew nothing; it now fills the shape."""
    if ctx.stroke_model != "flush" or not ctx.older(CURRENT_SINCE):
        return
    for layer in layers(state):
        if not (strokes.plain_box(layer) or strokes.plain_corners(layer)):
            continue
        width, height, stroke = layer.get("width"), layer.get("height"), layer.get("stroke_width", 1)
        if not all(isinstance(v, (int, float)) for v in (width, height, stroke)):
            continue
        if stroke >= min(width, height) - 1 and strokes.stroke_visible(ctx.project, layer):
            ctx.warn("thick-stroke", "The stroke is as wide as the shape: it used to draw nothing and now fills the "
                     "whole shape with the stroke colour; hide the layer or thin the stroke for the old look", layer,
                     "stroke_width")


def pdf_bleed(ctx, state):
    """Before 0.23 a fractional bleed was rounded up to whole pixels; PDF export no longer stretches it to fit."""
    if not ctx.older(PRECISE_BLEED):
        return
    from ..sizes import PX, bleed_pixels, to_pixels

    canvas = state.get("canvas") or {}
    physical, dpi = canvas.get("physical"), canvas.get("dpi")
    if not isinstance(physical, dict) or physical.get("unit", PX) == PX or not dpi or not physical.get("bleed"):
        return
    unit, amount = physical["unit"], physical["bleed"]
    exact, rounded = bleed_pixels(amount, unit, dpi), round(to_pixels(amount, unit, dpi))
    width = round(to_pixels(physical["width"], unit, dpi)) + 2 * rounded
    if exact != rounded and canvas.get("width") == width:
        ctx.warn("pdf-bleed", f"The canvas holds a bleed rounded to {rounded} px; a PDF export is now "
                 f"{2 * (rounded - exact)} px larger than the trim plus bleed at {dpi} dpi. Re-create the canvas with "
                 "the canvas operation's size to get the exact bleed", field="canvas.physical")


def _comps(state):
    """Every layer comp (``{layer id: fields}``) in the state, the page's and those kept in pages and masters."""
    found = []

    def walk(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if key == "comps" and isinstance(item, dict):
                    found.extend(comp for comp in item.values() if isinstance(comp, dict))
                else:
                    walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    walk(state)
    return found


def _tracks(state):
    timeline = state.get("timeline")
    return [track for track in (timeline or {}).get("tracks") or [] if isinstance(track, dict)]


# (rule ID, function). The order matters: the lookup effect exists before effects are read, and the house-style
# stamp is read (by the context) before it is removed.
RULES = (
    ("lookup-field", lookup_field),
    ("house-style-version", house_style_version),
    ("open-shape-fill", open_shape_fill),
    ("effects-before-transform", effects_before_transform),
    ("temperature-tint-scale", temperature_tint),
    ("text-box-height", text_box_height),
    ("irregular-strength", irregular_strength),
    ("diagram-line-height", diagram_line_height),
    ("chart-padding", chart_padding),
    ("heading-wrap", heading_wrap),
    ("scatter-distribution", scatter_distribution),
    ("rectangle-radius", rectangle_radius),
    ("closed-stroke-geometry", closed_stroke_geometry),
    ("styled-stroke-align", styled_stroke_align),
    ("polygon-joins", polygon_joins),
    ("thick-stroke", thick_stroke),
    ("pdf-bleed", pdf_bleed),
)
