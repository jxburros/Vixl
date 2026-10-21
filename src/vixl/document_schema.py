"""The published JSON Schema of a ``.vixl`` document's ``project.json`` (see docs/reference/file-format.md).

The schema is generated from this module's field registries and the model's own constants (layer types, roles,
blend modes, canvas keys, history node keys, page fields), and shipped as ``data/vixl-document.schema.json``.
Tests keep the three in step: the shipped file must equal ``document_schema()``, every ``.vixl`` in the repository
must validate against it, and every layer and document field the code reads or writes must be described here.
Run ``python -m vixl.document_schema`` to rewrite the shipped file after changing a registry."""

import json
from pathlib import Path

SCHEMA_ID = "https://github.com/jxburros/Vixl/blob/main/src/vixl/data/vixl-document.schema.json"
SCHEMA_PATH = Path(__file__).parent / "data" / "vixl-document.schema.json"
ARCHIVE_FOLDERS = ("assets", "masks", "fonts", "sources", "emoji-sources")
ASSET_PATTERN = r"^(assets|masks|fonts|sources|emoji-sources)/[0-9a-f]{64}\.[a-z0-9]{2,5}$"

STRING, NUMBER, INTEGER, BOOLEAN, OBJECT, ARRAY = "string", "number", "integer", "boolean", "object", "array"
COLOR = "color"  # a colour string: CSS, #hex, @swatch reference, ${variable} …
ASSET = "asset"  # an archive member path such as assets/<sha256>.png
LAYER_ID = "layer-id"
POINT = "point"  # [x, y]
BOX = "box"  # [x0, y0, x1, y1] or [x, y, w, h]


def _type(kind):
    if kind == COLOR:
        return {"type": "string"}
    if kind == ASSET:
        return {"type": "string", "pattern": ASSET_PATTERN}
    if kind == LAYER_ID:
        return {"type": "string"}
    if kind == POINT:
        return {"type": "array", "items": {"type": "number"}, "minItems": 2, "maxItems": 2}
    if kind == BOX:
        return {"type": "array", "items": {"type": "number"}, "minItems": 4, "maxItems": 4}
    if isinstance(kind, tuple):
        types = []
        for item in kind:
            types.append({COLOR: "string", ASSET: "string", LAYER_ID: "string"}.get(item, item))
        return {"type": sorted(set(types))}
    return {"type": kind}


# Layer fields: name → (type, description). The first block is every layer's (``model.new_layer``).
COMMON_LAYER_FIELDS = {
    "id": (STRING, "Stable layer ID (lyr_ + 16 hex digits); unique in the document and never reused."),
    "name": (STRING, "Unique, non-empty layer name; operations address a layer by ID or name."),
    "type": (STRING, "Layer type; see the type list."),
    "width": (NUMBER, "Width in pixels (in the parent group's content pixels for a child layer)."),
    "height": (NUMBER, "Height in pixels."),
    "x": (NUMBER, "Left edge of the unrotated box, in canvas pixels (parent content pixels for a child layer)."),
    "y": (NUMBER, "Top edge of the unrotated box."),
    "rotation": (NUMBER, "Clockwise rotation in degrees around the pivot (default the box centre)."),
    "flip_x": (BOOLEAN, "Mirror horizontally."),
    "flip_y": (BOOLEAN, "Mirror vertically."),
    "opacity": (NUMBER, "Layer opacity, 0 (clear) to 1 (opaque)."),
    "blend": (STRING, "Blend mode with what is beneath."),
    "visible": (BOOLEAN, "Whether the layer draws."),
    "effects": (ARRAY, "Effect stack, applied in order in the layer's own frame before flip, rotation and skew."),
    "mask": ((OBJECT, "null"), "Raster mask {asset: masks/<sha256>.png, enabled} or null."),
    "constraints": (OBJECT, "Layout constraints: anchor → pixels or an expression over other layers."),
}

LAYER_FIELDS = {
    # Placement, structure and transforms
    "parent": ((LAYER_ID, "null"), "ID of the group (or other container) that holds this layer; absent or null at "
               "the top level."),
    "content_width": (NUMBER, "group: width of the coordinate space its children are laid out in."),
    "content_height": (NUMBER, "group: height of the coordinate space its children are laid out in."),
    "pivot": (POINT, "Rotation and scale origin as [x, y] fractions of the box (default [0.5, 0.5])."),
    "skew_x": (NUMBER, "Horizontal skew in degrees (-90 to 90 exclusive)."),
    "skew_y": (NUMBER, "Vertical skew in degrees (-90 to 90 exclusive)."),
    "affine": (ARRAY, "An exact 2×3 placement matrix for free transforms that x/y/rotation/skew cannot express."),
    "snap_to_pixel": (BOOLEAN, "Round the drawn position to whole pixels."),
    "clip": (LAYER_ID, "ID of the layer whose alpha clips this one."),
    "auto_size": (BOOLEAN, "text: the box follows the text (true) or the text wraps in a fixed box (false)."),
    "text_layout": (OBJECT, "text: the fixed box {width, height} text wraps in, and how it fits."),
    "role": (STRING, "Layout role: content, decoration, background or title."),
    "tags": (ARRAY, "Free-form tags (selectors, adapt rules such as optional)."),
    "stack": (OBJECT, "Auto-layout stack settings of a group: direction, gap, alignment, padding."),
    "hide_if_empty": (BOOLEAN, "Skip the layer (and its stack slot) while its text is empty after variables."),
    "repeat": (OBJECT, "Repeat settings: count and per-copy offsets (dx, dy, dw, dh, rotation, colour ramp)."),
    "radial": (OBJECT, "group made by radial-repeat: {count, center [x, y], sweep, start_angle, mirror}."),
    "symbol": (STRING, "symbol: name of the symbol master in state.symbols it instances."),
    "linked": (BOOLEAN, "raster: the asset is a link to a file outside the archive (allow_linked)."),
    "asset_variable": (STRING, "Variable naming the image asset to draw (variable data merge)."),
    "container": (OBJECT, "Container record of a template slot group."),
    "container_layout": (OBJECT, "Layout a container computed for its contents."),
    "container_variable": (STRING, "Variable a container slot is bound to."),
    "container_font_size": (NUMBER, "Font size a container fitted its text to."),
    "container_local": (OBJECT, "Container-local placement before fitting."),
    "image_slot": (OBJECT, "An image slot of a container: fit and focus of the image it holds."),
    "provenance": (OBJECT, "Where the layer came from (import, AI provider, SVG appearance source …)."),
    "pen_origin": (POINT, "Pen-tool origin of a drawn path, in canvas pixels."),
    "part_of": (LAYER_ID, "ID of the layer this decoration belongs to (irregular edges, labels …)."),
    "source_id": (LAYER_ID, "ID of the layer a scattered or repeated copy was made from."),
    "recolor": (OBJECT, "Colour substitutions applied to a placed copy."),
    # Fill, stroke and geometry
    "fill": (COLOR, "Fill colour (shape, solid, pathfinder)."),
    "color": (COLOR, "Text or field text colour."),
    "stroke": (COLOR, "Stroke colour; transparent for none."),
    "stroke_width": (NUMBER, "Stroke width in pixels (text: outline width)."),
    "stroke_color": (COLOR, "text: outline colour."),
    "shape": (STRING, "shape: rectangle, rounded-rectangle, capsule, ellipse, line, polygon, star, path or a "
              "catalog shape (arrow, speech bubble, heart …)."),
    "path": (STRING, "shape path: SVG path data (M L H V C S Q T A Z) in path_view coordinates."),
    "path_view": (POINT, "shape path: [width, height] of the coordinate box path is written in."),
    "radius": ((NUMBER, STRING, ARRAY), "Corner radius: pixels, a percentage string of the shorter side, or four "
               "corner radii [top-left, top-right, bottom-right, bottom-left] (catalog shapes read a bare number "
               "as a fraction)."),
    "sides": (INTEGER, "polygon and star: number of sides or points."),
    "inner_radius": (NUMBER, "star: inner radius as a fraction of the outer."),
    "start_angle": (NUMBER, "wedge and arc: start angle in degrees."),
    "end_angle": (NUMBER, "wedge and arc: end angle in degrees."),
    "closed": (BOOLEAN, "path: close the outline."),
    "trim_start": (NUMBER, "Stroke trim start, 0–1 of the outline length."),
    "trim_end": (NUMBER, "Stroke trim end, 0–1 of the outline length."),
    "dash": ((ARRAY, STRING), "Dash pattern lengths in pixels, or the preset dashed or dotted."),
    "dash_offset": (NUMBER, "Dash pattern offset in pixels."),
    "dash_fit": (BOOLEAN, "Fit the dash pattern to corners and open ends (default true); false keeps exact lengths."),
    "line_cap": (STRING, "Stroke cap: butt, round or square."),
    "line_join": (STRING, "Stroke join: miter, round or bevel."),
    "miter_limit": (NUMBER, "Miter limit for mitred joins."),
    "stroke_align": (STRING, "Stroke position on the outline: inside (default for closed shapes), center (default "
                     "for paths, arcs, lines and open shapes) or outside."),
    "strokes": (ARRAY, "paint: brush strokes {brush, points, …}; shape: extra strokes drawn over the outline."),
    "width_profile": (ARRAY, "Variable stroke width profile along the path."),
    "taper_start": (NUMBER, "Stroke taper at the start, 0–1."),
    "taper_end": (NUMBER, "Stroke taper at the end, 0–1."),
    "marker_start": (STRING, "Marker at the path start (arrow, dot …)."),
    "marker_end": (STRING, "Marker at the path end."),
    "marker_size": (NUMBER, "Marker length and width in local pixels."),
    "marker_style": (STRING, "Marker drawing style."),
    "distort": (OBJECT, "Envelope distortion of the geometry (arc, wave, perspective …)."),
    "vector_geometry": (OBJECT, "Cached outline geometry of a vector stroke."),
    "organic": (OBJECT, "Organic shape recipe {preset, seed, naturalness}."),
    "irregular": (OBJECT, "Irregular (torn, rough) edge recipe and its source geometry."),
    "tear": (OBJECT, "Torn-edge record: the tear recipe, mask or path mode and its rim and fibre layers."),
    "die_cut": (OBJECT, "A die-cut outline record: the layers it surrounds and the offset distance."),
    "reflection": (OBJECT, "A reflection layer's settings (horizon, sources), kept so it can be re-rendered."),
    "cut_paper": (OBJECT, "Cut-paper look settings (grain, edge texture)."),
    "export_fallback": (STRING, "Reason vector exports draw this layer as an image."),
    # Catalog shape parameters (shape_catalog.py)
    "corner_style": (STRING, "Catalog shape: corner style."),
    "point_radius": (NUMBER, "Catalog shape: radius of star points."),
    "valley_radius": (NUMBER, "Catalog shape: radius of star valleys."),
    "rotation_offset": (NUMBER, "Catalog shape: rotation of the generated outline in degrees."),
    "head_length": (NUMBER, "Arrow: head length."),
    "head_width": (NUMBER, "Arrow: head width."),
    "shaft_width": (NUMBER, "Arrow: shaft width."),
    "heads": (STRING, "Arrow: which ends carry heads."),
    "head_style": (STRING, "Arrow: head style."),
    "curve": (NUMBER, "Catalog shape: curvature."),
    "from": (POINT, "Connector or arrow start point."),
    "to": (POINT, "Connector or arrow end point."),
    "control": (POINT, "Connector or arrow control point."),
    "thickness": (NUMBER, "Catalog shape: band thickness."),
    "count": (INTEGER, "Catalog shape: number of repeated elements (rays, teeth, petals …)."),
    "depth": (NUMBER, "Catalog shape: depth; scene layers: depth for parallax and lighting."),
    "hole": (NUMBER, "Catalog shape: hole size."),
    "fold": (NUMBER, "Catalog shape: folded corner size."),
    "pointer_size": (NUMBER, "Callout: pointer size."),
    "pointer_position": (NUMBER, "Callout: pointer position along its side, 0–1."),
    "pointer_side": (STRING, "Callout: side the pointer is on."),
    "exponent": (NUMBER, "Superellipse exponent."),
    "apex": (NUMBER, "Catalog shape: apex position."),
    "step": (NUMBER, "Catalog shape: step size."),
    "arms": (INTEGER, "Catalog shape: number of arms."),
    "teeth": (INTEGER, "Gear: number of teeth."),
    "amplitude": (NUMBER, "Wave: amplitude."),
    "wavelength": (NUMBER, "Wave: wavelength."),
    "phase": (NUMBER, "Wave: phase."),
    "ray_length": (NUMBER, "Burst: ray length."),
    "rating": (NUMBER, "Rating shape: filled amount."),
    "notch": (NUMBER, "Catalog shape: notch size."),
    "peel": (NUMBER, "Catalog shape: peeled corner size."),
    "frame_shape": (STRING, "Frame shape of a framed catalog shape."),
    "angle": (NUMBER, "gradient: angle in degrees for angled gradients; catalog shapes: an angle parameter."),
    "petals": (INTEGER, "Flower: number of petals."),
    "taper": (NUMBER, "Catalog shape: taper."),
    "smooth": (NUMBER, "Catalog shape: smoothing."),
    "seed": ((INTEGER, STRING), "Random seed of a generated shape."),
    "cleft": (NUMBER, "Heart: cleft depth."),
    "tip": (NUMBER, "Catalog shape: tip sharpness."),
    "body": (NUMBER, "Catalog shape: body proportion."),
    "slant": (NUMBER, "Catalog shape: slant."),
    # Gradients
    "start": (COLOR, "gradient: start colour."),
    "end": (COLOR, "gradient: end colour."),
    "stops": (ARRAY, "gradient: colour stops [{offset 0–1, color}] (2–32)."),
    "direction": (STRING, "gradient: horizontal, vertical, radial or angled."),
    "center": (POINT, "Radial gradient centre as [x, y] fractions of the layer."),
    "falloff": (STRING, "gradient: interpolation (linear, smooth, ease, quadratic, gaussian)."),
    # Text
    "text": (STRING, "text: the plain text (also the text of rich text); ${variables} are substituted."),
    "size": (NUMBER, "text and field: font size in pixels."),
    "font": (STRING, "Font: a registered font name (state.fonts), a fonts/ archive member or a bundled font file name; a role is in font_role."),
    "font_role": (STRING, "Typography role the font follows (heading, body …)."),
    "align": (STRING, "Text alignment: left, center or right (fields too)."),
    "spacing": (NUMBER, "text: extra line spacing in pixels; catalog shapes: spacing parameter."),
    "line_height": (NUMBER, "text: distance between baselines as a multiple of the size."),
    "tracking": (NUMBER, "text: letter spacing in pixels."),
    "text_transform": (STRING, "text: none, uppercase, lowercase or capitalize, applied when drawing."),
    "tabs": (ARRAY, "text: tab stops [{at, align, leader}]."),
    "stage": (STRING, "text: type stage (display, h1 … caption) it was set with."),
    "rich": (OBJECT, "Rich text: spans, paragraphs and their styles (see docs/guides/text/rich-text.md)."),
    "character_style": (STRING, "text: named character style applied (state.character_styles)."),
    "paragraph_style": (STRING, "text: named paragraph style applied (state.paragraph_styles)."),
    "literal_text": (BOOLEAN, "Intent: the text is literal (not copy to check or rewrite)."),
    # Images, frames and masks
    "asset": (ASSET, "raster and frame: the image member of the archive."),
    "crop": (BOX, "Crop box [x0, y0, x1, y1] in source pixels (link and frame layers)."),
    "fit": (STRING, "How an image or linked document fills the box (fill, fit, stretch …)."),
    "position": (POINT, "Focus [x, y] fractions used when fit crops."),
    # Layer styles, looks and appearance
    "styles": (OBJECT, "Layer styles by name (drop-shadow, stroke, outer-glow, color-overlay, gradient-overlay), "
               "each with its settings and enabled."),
    "looks": (OBJECT, "Applied looks (finishes) by name, listing the styles and effects each added."),
    "appearance": (OBJECT, "field: widget appearance (style, fill, stroke, radius …)."),
    # Pathfinder
    "mode": (STRING, "pathfinder: union, subtract, intersect, exclude, divide, minus-back, trim or merge."),
    "operands": (ARRAY, "pathfinder: the layers it combines (embedded copies)."),
    # Pixel art
    "pixels": (ARRAY, "pixel: rows of palette keys."),
    "palette": (OBJECT, "pixel: palette key → colour."),
    "outline": ((OBJECT, STRING, BOOLEAN), "pixel: generated outline: true, a colour or settings."),
    "shading": ((OBJECT, BOOLEAN), "pixel: generated shading: true or {light, colors, highlight}."),
    # Paint
    "surface": (POINT, "paint: [width, height] of the surface strokes are recorded on."),
    # Forms
    "field": (OBJECT, "field: the form field record {key, kind, label, options, required …}."),
    "padding": (NUMBER, "field: inner padding in pixels."),
    "value": ((ARRAY, STRING, "null"), "field: value drawn in a filled export (render copies only)."),
    # Linked documents
    "source": ((STRING, OBJECT), "link: path of the linked document, relative to the document's folder."),
    "source_page": ((INTEGER, STRING), "link: page of the linked document to show."),
    "source_hash": (STRING, "link: SHA-256 of the linked file when it was last placed or updated."),
    "source_size": (ARRAY, "link: [width, height] of the linked page."),
    "artboard": (STRING, "link: artboard of the linked document to show."),
    "variables": (OBJECT, "link: variable values passed to the linked document."),
    "corner_pin": (ARRAY, "link: four corner points for a perspective placement."),
    # Structured content
    "chart": (OBJECT, "group: the chart record (kind, data, options) its parts are drawn from."),
    "chart_part": (STRING, "Which part of a chart this layer is."),
    "table": (OBJECT, "group: the table record (rows, columns, styles)."),
    "table_part": (STRING, "Which part of a table this layer is."),
    "key_values": (OBJECT, "group: a key-value list record."),
    "kv_part": (STRING, "Which part of a key-value list this layer is."),
    "code": ((OBJECT, "null"), "shape: QR code or barcode record {kind, data …}."),
    "drawing": (OBJECT, "A hand-drawing pipeline record (source, cleanup, vectorize settings)."),
    "drawing_strokes": (ARRAY, "Vectorized strokes of a drawing."),
    "drawing_role": (STRING, "Role of this layer in a drawing (line, fill …)."),
    "object": (OBJECT, "group: object declaration {kind, label, notes, references, version}."),
    "object_part": (OBJECT, "This layer's part name {name, side} inside its object."),
    "character": (OBJECT, "group: character rig (parts, bones, poses)."),
    "character_part": (STRING, "Which part of a character this layer is."),
    "character_color": (STRING, "Character colour role of this part."),
    "particle": (OBJECT, "Particle emitter settings."),
    "bubble": (OBJECT, "Speech bubble geometry and tail."),
    "caption": (OBJECT, "Caption metadata (timing, text layer)."),
    # Intent flags read by checks
    "alt": (STRING, "Alternative text (exports carry it to SVG title, PDF /Alt and PPTX descr)."),
    "decorative": (BOOLEAN, "Accessibility: the layer is decoration (exports mark it as an artifact)."),
    "allow_overlap": (ARRAY, "IDs of layers this one may overlap without a check finding."),
    "allow_crop": (BOOLEAN, "Intent: the canvas edge may crop the layer."),
    "color_vision_safe": (BOOLEAN, "Intent: colour is not the only cue."),
    "detached_ok": (BOOLEAN, "Intent: the layer may sit apart from the composition."),
    "waive": (ARRAY, "Check findings waived on this layer."),
}

# Fields that appear only on ``inspect`` output or render copies, never in a saved document.
# Fields render and timeline code put on throwaway copies of a layer while drawing; never saved.
TRANSIENT = ("_kinetic", "_distort_groups", "_style")
INSPECT_ONLY = ("resolved_bounds", "canvas_bounds", "content_bounds", "coordinate_space", "collapsed",
                "drawn_bounds", "path_nodes", "source_bounds", "path_local_bounds")

# Document state: name → (type, description). The first block is every document's (``model.new_state``).
STATE_FIELDS = {
    "canvas": (OBJECT, "Canvas size, background and print settings."),
    "layers": (ARRAY, "Layers bottom to top (of the active page in a paged document)."),
    "active_layer": ((LAYER_ID, "null"), "ID of the active layer, or null."),
    "selection": ((ASSET, "null"), "The pixel selection mask (masks/<sha256>.png), or null."),
    "variables": (OBJECT, "Document variables (${name} substitution)."),
    "presets": (OBJECT, "Saved operation presets."),
    # Pages
    "pages": (ARRAY, "Pages of a multi-page document; the active page's content lives at the top level."),
    "page": ((STRING, "null"), "ID of the active page."),
    "masters": (OBJECT, "Master pages by name: {background, content}."),
    # Resources and design system
    "fonts": (OBJECT, "Registered fonts: name → fonts/<sha256>.<ext> archive member."),
    "font_fallbacks": (ARRAY, "Fallback font members tried for missing glyphs."),
    "typography": (OBJECT, "Typography: heading/body roles, type scale."),
    "type_stages": (OBJECT, "Type stage overrides (display, h1 … caption)."),
    "swatches": (OBJECT, "Named colours (@name references)."),
    "palettes": (OBJECT, "Named palettes: name → list of colours."),
    "active_palette": (STRING, "Name of the palette applied last."),
    "palette_roles": (OBJECT, "Colour roles assigned from the active palette."),
    "character_styles": (OBJECT, "Named character styles."),
    "paragraph_styles": (OBJECT, "Named paragraph styles."),
    "brushes": (OBJECT, "Custom brushes by name."),
    "patterns": (OBJECT, "Named fill patterns."),
    "luts": (OBJECT, "Colour lookup tables by name."),
    "maps": (OBJECT, "Variable maps (value lookups)."),
    "symbols": (OBJECT, "Symbol masters: name → master layer ID."),
    "object_library": (OBJECT, "Saved objects (object-save) for object-place."),
    "character_library": (OBJECT, "Saved characters."),
    "emojis": (OBJECT, "Custom emoji artwork registry."),
    "emoji_template": (OBJECT, "Emoji template settings."),
    "emoji_artwork": (OBJECT, "Emoji artwork record of an emoji document."),
    "design_defaults": (OBJECT, "Design defaults the document was created with (rolled house style)."),
    "design_guidance": (OBJECT, "Named design guidance texts."),
    "brand_preset": (STRING, "Brand preset applied."),
    "style": ((OBJECT, STRING), "Design style tag and its check options."),
    # Layout aids
    "guides": (OBJECT, "Ruler guides by name: {axis, position, grid or generated}."),
    "grids": (OBJECT, "Layout grids by name."),
    "active_grid": (STRING, "Name of the active grid."),
    "layout": (OBJECT, "The layout template applied and its slots."),
    "template": (OBJECT, "Template record of a document made from a template."),
    "artboards": (OBJECT, "Artboards: name → {x, y, width, height, background, variables, targets}."),
    "comps": (OBJECT, "Layer comps: saved visibility and position states."),
    "containers": (OBJECT, "Container records of template slots."),
    "blanks": (OBJECT, "Blank placeholders awaiting content."),
    "flows": (ARRAY, "Text flows threading text through several layers."),
    "diagrams": (OBJECT, "Diagram records (nodes, edges, layout)."),
    "roles": (OBJECT, "Named layer roles bound for actions and recipes."),
    "snap_to_pixel": (BOOLEAN, "Round every layer's drawn position to whole pixels."),
    # Automation, checks and review
    "suites": (OBJECT, "Check suites: named sets of rules (suite-set)."),
    "waivers": (ARRAY, "Waived check findings."),
    "actions": (OBJECT, "Recorded actions (operation lists) by name."),
    "recipe": (OBJECT, "Automation recipe."),
    "accessibility": (OBJECT, "Document language and title."),
    "font_design": (OBJECT, "Custom font being drawn: family, metrics in pixels, kerning and glyphs (char → layers, origin, advance)."),
    "page_accessibility": (OBJECT, "Page language and reading order."),
    "form": (OBJECT, "Form settings (title, language, submit)."),
    "merged_branches": (ARRAY, "Branches merged into this document."),
    "merge": (OBJECT, "Merge-impose record of a generated sheet."),
    "placeholders": (ARRAY, "Placeholder listing (inspect output only)."),
    # Motion and media
    "timeline": (OBJECT, "Keyframe timeline: duration, fps, tracks, markers."),
    "animation": (OBJECT, "Frame animation settings and frames."),
    "motions": (OBJECT, "Motion recipes applied."),
    "stop_motion": (OBJECT, "Stop-motion settings."),
    "audio_tracks": (ARRAY, "Audio tracks (assets/<sha256>.wav)."),
    "particles": (OBJECT, "Particle system settings."),
    "lighting": (OBJECT, "Scene lighting and colour grading."),
    "camera": (OBJECT, "Scene camera."),
    "comic": (OBJECT, "Comic page record (panels, reading order)."),
    "lyric_build": (OBJECT, "Options and sources a lyric video document was built from."),
    "mockup": (OBJECT, "Mockup record (template, design, slots)."),
    "deck_markdown": (OBJECT, "Markdown source a deck was built from."),
}

PAGE_FIELDS_DOC = {
    "id": (STRING, "Stable page ID."),
    "name": (STRING, "Unique page name."),
    "notes": (STRING, "Speaker notes."),
    "master": ((STRING, "null"), "Master page drawn underneath."),
    "background": (COLOR, "Page background colour (else the canvas or master background)."),
    "variables": (OBJECT, "Page variables."),
    "hidden": (BOOLEAN, "Left out of exports unless named."),
    "transition": ((OBJECT, STRING), "Presentation transition."),
    "content": ((OBJECT, "null"), "The page's own state (layers, active_layer, selection, timeline …) while another "
                "page is active; absent on the active page, whose content is at the top level."),
}

NODE_FIELDS = {
    "id": (STRING, "Revision ID (the key it is stored under)."),
    "parent": ((STRING, "null"), "Parent revision ID; null for the root."),
    "operations": (ARRAY, "The operations this revision applied to its parent."),
    "label": ((STRING, "null"), "History label."),
    "state": (OBJECT, "A full state snapshot (every 32nd revision on a chain, and the root)."),
    "delta": ((OBJECT, ARRAY), "A delta from the parent's state (history.diff), instead of state."),
    "squashed": ((INTEGER, ARRAY, BOOLEAN), "Revisions folded into this one by history compaction."),
}


def _properties(registry):
    return {name: {**_type(kind), "description": text} for name, (kind, text) in registry.items()}


def document_schema():
    """The JSON Schema (draft 2020-12) of ``project.json``."""
    from .model import LAYER_ROLES, LAYER_TYPES
    from .pages import MASTER_FIELDS, PAGE_FIELDS, SCOPED
    from .project import FORMAT_VERSION, NODE_KEYS
    from .constants import BLENDS
    from .sizes import CANVAS_KEYS, SIDES, UNIT_INCHES

    assert set(PAGE_FIELDS_DOC) == set(PAGE_FIELDS), "document_schema.PAGE_FIELDS_DOC is out of date"
    assert set(NODE_FIELDS) == set(NODE_KEYS), "document_schema.NODE_FIELDS is out of date"
    assert set(MASTER_FIELDS) == {"background", "content"}, "document_schema master fields are out of date"
    layer_props = _properties({**COMMON_LAYER_FIELDS, **LAYER_FIELDS})
    layer_props["type"]["enum"] = list(LAYER_TYPES)
    layer_props["blend"]["enum"] = list(BLENDS)
    layer_props["role"]["enum"] = list(LAYER_ROLES)
    layer_props["opacity"].update(minimum=0, maximum=1)
    layer_props["effects"]["items"] = {"$ref": "#/$defs/effect"}
    layer_props["mask"] = {"anyOf": [{"type": "null"}, {"$ref": "#/$defs/mask"}],
                           "description": COMMON_LAYER_FIELDS["mask"][1]}
    layer = {
        "type": "object",
        "description": "One layer. Fields beyond the common ones depend on the type and on the features used.",
        "properties": layer_props,
        "required": list(COMMON_LAYER_FIELDS),
        "additionalProperties": False,
        "allOf": [
            {"if": {"properties": {"type": {"enum": ["raster", "frame"]}}},
             "then": {"required": ["asset"]}},
            {"if": {"properties": {"type": {"const": "text"}}}, "then": {"required": ["text", "size"]}},
            {"if": {"properties": {"type": {"const": "group"}}},
             "then": {"required": ["content_width", "content_height"]}},
            {"if": {"properties": {"type": {"const": "link"}}}, "then": {"required": ["source"]}},
            {"if": {"properties": {"type": {"const": "symbol"}}}, "then": {"required": ["symbol"]}},
            {"if": {"properties": {"type": {"const": "pathfinder"}}}, "then": {"required": ["mode", "operands"]}},
            {"if": {"properties": {"type": {"const": "pixel"}}}, "then": {"required": ["pixels", "palette"]}},
            {"if": {"properties": {"type": {"const": "field"}}}, "then": {"required": ["field"]}},
        ],
    }
    canvas_props = {
        "width": {"type": "number", "exclusiveMinimum": 0, "description": "Canvas width in pixels."},
        "height": {"type": "number", "exclusiveMinimum": 0, "description": "Canvas height in pixels."},
        "background": {"type": "string", "description": "Background colour; transparent for none."},
        "color_mode": {"const": "rgba8", "description": "Pixel format; always rgba8."},
        "size": {"type": "string", "description": "Named size the canvas was made from (vixl sizes)."},
        "dpi": {"type": "number", "minimum": 36, "maximum": 2400, "description": "Print resolution."},
        "bleed": {"type": "number", "minimum": 0, "description": "Bleed in (whole or half) pixels on each side."},
        "safe": {"anyOf": [{"type": "integer", "minimum": 0},
                           {"type": "object", "propertyNames": {"enum": list(SIDES)},
                            "additionalProperties": {"type": "integer", "minimum": 0}}],
                 "description": "Safe-area inset in pixels (one number or per side)."},
        "physical": {"type": "object", "description": "Physical trim size {width, height, unit, bleed}.",
                     "properties": {"width": {"type": "number"}, "height": {"type": "number"},
                                    "unit": {"enum": list(UNIT_INCHES)}, "bleed": {"type": "number"}},
                     "additionalProperties": False},
    }
    assert set(canvas_props) == set(CANVAS_KEYS), "document_schema canvas fields are out of date"
    state_props = _properties(STATE_FIELDS)
    state_props["canvas"] = {"type": "object", "description": STATE_FIELDS["canvas"][1], "properties": canvas_props,
                             "required": ["width", "height", "background", "color_mode"],
                             "additionalProperties": False}
    state_props["layers"]["items"] = {"$ref": "#/$defs/layer"}
    state_props["pages"]["items"] = {"$ref": "#/$defs/page"}
    state_props["masters"]["additionalProperties"] = {"$ref": "#/$defs/master"}
    state = {
        "type": "object",
        "description": "A document state: the canvas, its layers and every document-level resource.",
        "properties": state_props,
        "required": ["canvas", "layers", "active_layer", "selection", "variables", "presets"],
        "additionalProperties": False,
    }
    content_props = {key: state_props[key] for key in SCOPED}
    page_props = _properties(PAGE_FIELDS_DOC)
    page_props["content"] = {"anyOf": [{"type": "null"}, {"$ref": "#/$defs/page_content"}],
                             "description": PAGE_FIELDS_DOC["content"][1]}
    node_props = _properties(NODE_FIELDS)
    node_props["state"] = {"$ref": "#/$defs/state", "description": NODE_FIELDS["state"][1]}
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": SCHEMA_ID,
        "title": "Vixl document (project.json)",
        "description": "The JSON member project.json of a .vixl archive (a ZIP file). Other members are the "
                       "binary assets it references: " + ", ".join(f"{f}/<sha256>.<ext>" for f in ARCHIVE_FOLDERS)
                       + ". See docs/reference/file-format.md.",
        "type": "object",
        "properties": {
            "format_version": {"const": FORMAT_VERSION, "description": f"Archive format version: {FORMAT_VERSION}. "
                               "Older archives open after vixl convert."},
            "vixl_version": {"type": "string", "description": "Vixl release that saved the file."},
            "state": {"$ref": "#/$defs/state", "description": "The current document state (the history head)."},
            "nodes": {"type": "object", "additionalProperties": {"$ref": "#/$defs/node"},
                      "description": "History revisions by ID (a DAG; branches share ancestors)."},
            "head": {"type": "string", "description": "ID of the current revision."},
            "branches": {"type": "object", "additionalProperties": {"type": "string"},
                         "description": "Branch name → revision ID."},
            "checkpoints": {"type": "object", "additionalProperties": {"type": "string"},
                            "description": "Checkpoint name → revision ID."},
            "current_branch": {"type": ["string", "null"], "description": "The checked-out branch, or null."},
            "redo_stack": {"type": "array", "items": {"type": "string"}, "description": "Revision IDs undo "
                           "stepped back over, newest last."},
            "transaction": {"type": ["object", "null"], "description": "An open transaction {state, operations} "
                            "or null."},
            "asset_hashes": {"type": "object", "propertyNames": {"pattern": ASSET_PATTERN},
                             "additionalProperties": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                             "description": "SHA-256 of every other archive member; the archive holds exactly "
                                            "these members."},
        },
        "required": ["format_version", "state", "nodes", "head", "branches", "checkpoints", "current_branch",
                     "redo_stack", "transaction", "asset_hashes"],
        "additionalProperties": False,
        "$defs": {
            "state": state,
            "layer": layer,
            "page": {"type": "object", "properties": page_props, "required": ["id", "name"],
                     "additionalProperties": False, "description": "One page of a multi-page document."},
            "page_content": {"type": "object", "properties": content_props, "additionalProperties": False,
                             "description": "Page-scoped state of an inactive page or master: "
                                            + ", ".join(SCOPED) + "."},
            "master": {"type": "object", "description": "A master page drawn under the pages that name it.",
                       "properties": {"background": {"type": "string", "description": "Master background colour."},
                                      "content": {"anyOf": [{"type": "null"}, {"$ref": "#/$defs/page_content"}],
                                                  "description": "The master's layers and scoped state."}},
                       "additionalProperties": False},
            "effect": {"type": "object", "description": "One effect of a stack: name, amount and its settings.",
                       "properties": {"id": {"type": "string", "description": "Effect ID (fx_…)."},
                                      "name": {"type": "string", "description": "Effect name (blur, grain, "
                                               "lookup …; vixl_reference('operations') lists them)."},
                                      "enabled": {"type": "boolean", "description": "Whether it applies."},
                                      "selection": {"type": ["string", "null"],
                                                    "description": "A selection mask member it is limited to."},
                                      "amount": {"type": "number", "description": "Strength."}},
                       "required": ["name"]},
            "mask": {"type": "object", "properties": {
                "asset": {"type": "string", "pattern": ASSET_PATTERN, "description": "masks/<sha256>.png member."},
                "enabled": {"type": "boolean", "description": "Whether the mask applies."}},
                "required": ["asset"], "description": "A raster mask."},
            "node": {"type": "object", "properties": node_props, "required": ["id", "parent", "operations"],
                     "additionalProperties": False, "description": "One history revision."},
        },
    }


def schema_text():
    return json.dumps(document_schema(), indent=1, ensure_ascii=False) + "\n"


def write():
    SCHEMA_PATH.write_text(schema_text(), encoding="utf-8", newline="\n")
    return SCHEMA_PATH


def validate_manifest(manifest):
    """Errors (as 'path: message' strings) of a project.json value against the published schema."""
    from jsonschema import Draft202012Validator

    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    return [f"{'/'.join(map(str, error.absolute_path)) or '(root)'}: {error.message}"
            for error in sorted(validator.iter_errors(manifest), key=lambda e: list(map(str, e.absolute_path)))]


if __name__ == "__main__":
    print(write())
