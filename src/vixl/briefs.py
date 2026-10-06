"""What to make, and with which tools: a map from a brief to operations, layouts, looks and styles.

Layouts are text compositions, so "make ten cool things" drifts toward ten posters. This module is
the other half: for each kind of brief (icon, character, scene, pattern, mandala, logo, diagram,
social card, slides …) it names the approach, the operations that build it, the layouts, looks and
styles that suit it, the checks to run, and a small working example. ``guide`` answers either a
kind name or a free-text brief; with no argument it returns the start-here recipe and every kind.
"""

import re

from .errors import VixlError

START_HERE = [
    "Size: pick a named size (vixl_sizes_list) and vixl_document_create(size=…).",
    "Structure: for anything with text, vixl_layouts_list then layout-apply, filling every slot it lists (seed makes it repeatable). "
    "For art without a text frame (icons, characters, scenes, patterns), build from shape, pen, pathfinder, organic and radial-repeat.",
    "Type: vixl_fonts then vixl_font_pair (the bundled font is a proofing fallback).",
    "Finish: apply a look (glow, soft-shadow, hard-shadow, gradient, grain, paper …) so flat shapes read as finished; "
    "tag a style (vixl_styles) when the brief names a look.",
    "Check: vixl_check, fix the 'fix' findings, glance at 'review', then vixl_render_preview and vixl_export_file.",
]

KINDS = {
    "poster": {
        "title": "Poster, flyer or cover",
        "keywords": ["poster", "flyer", "cover", "event", "announcement", "headline", "typographic", "print"],
        "summary": "A message-first composition: one focal headline, supporting copy and a clear action.",
        "approach": ["Create the document from a print or poster size.", "layout-apply a text layout, fill every slot, then refine.",
                     "Pair fonts, set a palette, and roll a few seeds to compare previews."],
        "operations": ["layout-apply", "palette-apply", "text", "look", "layer-style"],
        "layouts": ["hero-statement", "typographic-poster", "event-poster", "big-number", "diagonal-band"],
        "looks": ["grain", "paper", "hard-shadow"], "styles": ["swiss", "brutalist", "editorial", "risograph"],
        "sizes": ["poster-18x24", "a3", "instagram-portrait"],
        "example": [{"type": "layout-apply", "name": "hero-statement", "title": "Make it simple", "subtitle": "One idea, said well.",
                     "palette": "midnight", "seed": 7}],
    },
    "social-card": {
        "title": "Social post, story or thumbnail",
        "keywords": ["social", "instagram", "post", "story", "thumbnail", "youtube", "tiktok", "reel", "carousel", "card"],
        "summary": "A small, fast-read graphic: legible at thumbnail size, with safe zones for platform UI.",
        "approach": ["Start from the platform size.", "Use a layout built for the format (story-vertical, thumbnail-bold, quote-card).",
                     "Check thumbnail legibility and safe areas."],
        "operations": ["layout-apply", "text-layout", "look", "page"],
        "layouts": ["story-vertical", "thumbnail-bold", "quote-card", "big-number", "product-card"],
        "looks": ["soft-shadow", "outline", "glow"], "styles": ["neo-brutalist", "minimalist", "y2k"],
        "sizes": ["instagram-post", "story", "youtube-thumbnail", "linkedin-post"],
        "example": [{"type": "layout-apply", "name": "quote-card", "title": "Design is how it works.", "subtitle": "Someone Wise",
                     "palette": "sunset", "seed": 3}],
    },
    "banner-ad": {
        "title": "Banner, ad or header",
        "keywords": ["banner", "ad", "advert", "header", "hero", "leaderboard", "cta", "web"],
        "summary": "A wide strip with a headline on one side and a call to action on the other.",
        "approach": ["Pick the exact ad or header size.", "layout-apply banner or z-pattern with a call to action.",
                     "Keep copy short and contrast high."],
        "operations": ["layout-apply", "gradient", "shape", "look"],
        "layouts": ["banner", "z-pattern", "split-screen"], "looks": ["gradient", "soft-shadow"],
        "styles": ["corporate-flat", "material"], "sizes": ["leaderboard", "web-banner", "linkedin-banner", "email-header"],
        "example": [{"type": "layout-apply", "name": "banner", "title": "Your offer in one line", "subtitle": "A short detail",
                     "cta": "Get started", "palette": "ocean", "seed": 2}],
    },
    "logo": {
        "title": "Logo, wordmark or monogram",
        "keywords": ["logo", "wordmark", "monogram", "brand", "identity", "emblem", "badge", "mark", "lockup"],
        "summary": "A simple, scalable mark with clear space; judged small and in one color.",
        "approach": ["Start from a logo size.", "layout-apply a logo layout for the lockup, or draw a mark with shape/pathfinder and set a wordmark.",
                     "Test at small sizes and in one color; export SVG."],
        "operations": ["layout-apply", "shape", "pathfinder", "text", "pen", "layer-style", "radial-repeat"],
        "layouts": ["logo-horizontal", "logo-stacked", "monogram", "emblem", "minimal-mark"],
        "looks": ["outline", "gradient"], "styles": ["minimalist", "line-art", "bauhaus", "art-deco"],
        "sizes": ["logo", "logo-horizontal", "logo-stacked", "logo-badge"],
        "example": [{"type": "layout-apply", "name": "monogram", "title": "Northwind Studio", "palette": "midnight", "seed": 4}],
    },
    "app-icon": {
        "title": "App icon or favicon",
        "keywords": ["icon", "app icon", "favicon", "glyph", "ios", "android", "pictogram", "symbol"],
        "summary": "One recognizable glyph on a rounded tile, designed for 16-1024 px.",
        "approach": ["Create the icon size.", "layout-apply app-icon for a keyline-correct tile, or build the glyph from shapes and pathfinder.",
                     "Preview small, then vixl_export_icons for the full set."],
        "operations": ["layout-apply", "shape", "pathfinder", "gradient", "layer-style", "look", "pixel-art"],
        "layouts": ["app-icon", "monogram", "minimal-mark"], "looks": ["gradient", "soft-shadow", "glow"],
        "styles": ["minimalist", "material", "glassmorphism", "pixel-art"], "sizes": ["app-icon", "favicon", "ios-app-icon"],
        "example": [{"type": "layout-apply", "name": "app-icon", "title": "Notes", "palette": "ocean", "seed": 5}],
    },
    "character": {
        "title": "Character or mascot",
        "keywords": ["character", "mascot", "creature", "animal", "robot", "monster", "face", "cartoon", "avatar", "sticker"],
        "summary": "A friendly figure assembled from ellipses and rounded shapes, with features that read at a glance.",
        "approach": ["Square or sticker canvas.", "Block the body, head and limbs with ellipse and rounded-rectangle shapes.",
                     "Add eyes, cheeks and mouth; merge shapes with pathfinder where outlines should be one piece.",
                     "Outline and finish with a look; group the figure so it moves as one."],
        "operations": ["shape", "pen", "pathfinder", "group", "organic", "look", "layer-style", "animate-preset"],
        "layouts": ["emblem", "centered-axis"], "looks": ["outline", "soft-shadow", "hard-shadow"],
        "styles": ["kawaii", "neo-brutalist", "hand-drawn", "line-art"], "sizes": ["sticker", "profile-picture", "discord-emoji"],
        "example": [
            {"type": "shape", "shape": "ellipse", "name": "body", "x": 140, "y": 160, "width": 240, "height": 260, "fill": "#ffd23f"},
            {"type": "shape", "shape": "ellipse", "name": "eye-left", "x": 200, "y": 250, "width": 34, "height": 44, "fill": "#222222"},
            {"type": "shape", "shape": "ellipse", "name": "eye-right", "x": 286, "y": 250, "width": 34, "height": 44, "fill": "#222222"},
            {"type": "shape", "shape": "ellipse", "name": "cheek-left", "x": 170, "y": 300, "width": 42, "height": 26, "fill": "#ff8fab"},
            {"type": "shape", "shape": "ellipse", "name": "cheek-right", "x": 308, "y": 300, "width": 42, "height": 26, "fill": "#ff8fab"},
            {"type": "group", "name": "mascot", "targets": ["body", "eye-left", "eye-right", "cheek-left", "cheek-right"]},
            {"type": "look", "target": "mascot", "look": "soft-shadow"},
        ],
    },
    "scene": {
        "title": "Scene or illustration",
        "keywords": ["scene", "illustration", "landscape", "sunset", "mountains", "forest", "sky", "city", "poster art", "background", "nature"],
        "summary": "Depth from layered flat shapes: sky gradient, sun, hills and foreground, with organic forms for plants.",
        "approach": ["Fill the canvas with a sky gradient.", "Stack hills and buildings back to front, darker toward the foreground.",
                     "Add a sun or moon with a glow; plant organic trees, flowers or ferns.", "Finish with grain; check the preview."],
        "operations": ["gradient", "shape", "pen", "organic", "organic-shape", "look", "layer-style", "paint", "radial-repeat"],
        "layouts": ["photo-caption", "rule-of-thirds"], "looks": ["glow", "grain", "paper", "watercolor", "gradient"],
        "styles": ["retro-futurism", "mid-century-modern", "hand-drawn", "risograph"], "sizes": ["instagram-post", "web-hero", "poster-18x24"],
        "example": [
            {"type": "gradient", "name": "sky", "direction": "vertical", "start": "#1e3a8a", "end": "#fdba74"},
            {"type": "shape", "shape": "ellipse", "name": "sun", "x": 520, "y": 220, "width": 160, "height": 160, "fill": "#fde68a"},
            {"type": "look", "target": "sun", "look": "glow", "color": "#fde68a"},
            {"type": "shape", "shape": "ellipse", "name": "hill", "x": -200, "y": 460, "width": 1000, "height": 500, "fill": "#14532d"},
            {"type": "layer-intent", "target": "hill", "allow_crop": True},
            {"type": "organic", "preset": "pine", "name": "tree", "x": 120, "y": 300, "width": 140, "height": 260},
        ],
    },
    "pattern": {
        "title": "Pattern, texture or background",
        "keywords": ["pattern", "texture", "tile", "wallpaper", "seamless", "repeat", "grid", "dots", "stripes", "background", "gradient"],
        "summary": "A motif repeated on a grid, or a textured field: repeat for rows, group and repeat again for columns.",
        "approach": ["Draw one motif.", "repeat it along x, group the row, then repeat the group along y.",
                     "Or fill with gradient layers and apply grain, paper or halftone looks."],
        "operations": ["shape", "repeat", "repeat-blend", "group", "arrange-grid", "gradient", "look", "radial-repeat"],
        "layouts": [], "looks": ["grain", "paper", "halftone", "duotone"], "styles": ["memphis", "risograph", "minimalist"],
        "sizes": ["web-hero", "photo-square", "phone-wallpaper"],
        "example": [
            {"type": "shape", "shape": "ellipse", "name": "dot", "x": 20, "y": 20, "width": 40, "height": 40, "fill": "#f97316"},
            {"type": "repeat", "target": "dot", "count": 8, "dx": 60, "dy": 0},
            {"type": "group", "name": "row", "targets": ["dot"]},
            {"type": "repeat", "target": "row", "count": 6, "dx": 0, "dy": 60},
        ],
    },
    "mandala": {
        "title": "Mandala, rosette or sunburst",
        "keywords": ["mandala", "rosette", "sunburst", "symmetry", "radial", "kaleidoscope", "flower", "snowflake", "ornament", "circular"],
        "summary": "One petal or ray repeated around a center, with optional mirroring for kaleidoscope symmetry.",
        "approach": ["Draw one petal (ellipse, leaf or star) off-center.", "radial-repeat it N times around the canvas center; mirror for dihedral symmetry.",
                     "Repeat the idea at smaller radius with a different shape, then add a center disc."],
        "operations": ["shape", "organic-shape", "radial-repeat", "group", "look", "pathfinder"],
        "layouts": ["emblem", "centered-axis"], "looks": ["glow", "gradient", "outline"],
        "styles": ["art-deco", "art-nouveau", "line-art", "vaporwave"], "sizes": ["photo-square", "instagram-post"],
        "example": [
            {"type": "shape", "shape": "ellipse", "name": "petal", "x": 380, "y": 120, "width": 40, "height": 150, "fill": "#7c3aed"},
            {"type": "radial-repeat", "target": "petal", "count": 12, "cx": "50%", "cy": "50%", "name": "outer-ring"},
            {"type": "look", "target": "outer-ring", "look": "glow", "color": "#c4b5fd"},
        ],
    },
    "diagram": {
        "title": "Diagram, infographic or data card",
        "keywords": ["diagram", "infographic", "chart", "data", "statistic", "flow", "process", "timeline", "graph", "stats", "dashboard", "number"],
        "summary": "Information first: shapes, connectors and labels on a grid, with a single highlight color.",
        "approach": ["Use big-number or bento-grid for headline figures.", "Build custom diagrams from shapes on a guide or grid (guide kind circle + place for radial layouts).",
                     "Align and distribute; keep text above 12 px; check alignment."],
        "operations": ["layout-apply", "shape", "text", "guide", "grid", "place", "distribute", "align", "arrange-grid"],
        "layouts": ["big-number", "bento-grid", "f-pattern", "slide-content"], "looks": ["soft-shadow"],
        "styles": ["data-viz", "corporate-flat", "swiss"], "sizes": ["instagram-post", "slide", "a4"],
        "example": [{"type": "layout-apply", "name": "big-number", "label": "Customer satisfaction", "title": "94%",
                     "subtitle": "would recommend us.", "body": "Survey of 2,000 customers.", "palette": "accessible-blue", "seed": 1}],
    },
    "slides": {
        "title": "Slide deck or carousel",
        "keywords": ["slide", "slides", "deck", "presentation", "keynote", "pitch", "carousel", "powerpoint", "pages"],
        "summary": "Pages of one document sharing a master: title, content and closing slides.",
        "approach": ["Start from slide size and add pages.", "layout-apply slide-title then slide-content per page.",
                     "Use a master for repeated footers; check with the deck checks; export PDF or PPTX."],
        "operations": ["page", "master", "layout-apply", "rich-text", "text-layout"],
        "layouts": ["slide-title", "slide-content", "f-pattern", "split-screen"], "looks": [],
        "styles": ["corporate-flat", "editorial", "minimalist"], "sizes": ["slide", "slide-4x3", "instagram-portrait"],
        "example": [{"type": "layout-apply", "name": "slide-title", "title": "Quarterly review", "subtitle": "Q3 results",
                     "caption": "Company · 2026", "palette": "midnight", "seed": 2}],
    },
    "stationery": {
        "title": "Business card, letterhead or stationery",
        "keywords": ["business card", "letterhead", "stationery", "envelope", "invoice", "menu", "price list", "certificate", "invitation"],
        "summary": "Print documents with trim, bleed and safe areas, and small, precise type.",
        "approach": ["Use a print size (bleed and safe guides come with it).", "layout-apply business-card, letterhead, framed or price-list.",
                     "Run print checks and export CMYK PDF."],
        "operations": ["layout-apply", "canvas", "text", "shape"],
        "layouts": ["business-card", "letterhead", "framed", "price-list", "centered-axis"], "looks": ["paper"],
        "styles": ["vintage-letterpress", "minimalist", "art-deco"], "sizes": ["business-card", "letterhead", "certificate", "menu"],
        "example": [{"type": "layout-apply", "name": "business-card", "title": "Alex Morgan", "subtitle": "Creative Director",
                     "body": "alex@example.com | +1 555 0100", "palette": "slate", "seed": 6}],
    },
    "form": {
        "title": "Form or fillable document",
        "keywords": ["form", "fillable", "registration", "application", "survey", "checkbox", "field", "pdf form"],
        "summary": "Field layers with keys and labels that export as fillable PDF fields and fill in batches.",
        "approach": ["Lay out labels with text; add field layers with keys.", "Run the form checks; export fillable PDF; fill rows from CSV."],
        "operations": ["field", "field-set", "form", "text", "shape", "align", "distribute"],
        "layouts": ["letterhead"], "looks": [], "styles": ["corporate-flat"], "sizes": ["letter", "a4"],
        "example": [{"type": "text", "text": "Full name", "name": "name-label", "size": 24, "color": "#111111", "x": 80, "y": 80},
                    {"type": "field", "kind": "text", "key": "full_name", "label": "Full name", "x": 80, "y": 120, "width": 400, "height": 44}],
    },
    "animation": {
        "title": "Animation, GIF or video",
        "keywords": ["animation", "animate", "gif", "motion", "video", "loop", "lyric", "kinetic", "sprite", "timeline", "bounce"],
        "summary": "Keyframes and presets on layers, previewed as a contact sheet and exported as GIF, MP4 or WebM.",
        "approach": ["Build the still design first.", "animate-preset for entrances and loops; keyframe for custom motion.",
                     "vixl_timeline_preview, then vixl_export_timeline."],
        "operations": ["timeline-set", "animate-preset", "animate", "keyframe", "marker", "frame-save", "animation-set"],
        "layouts": [], "looks": ["glow"], "styles": ["pixel-art", "retro-futurism"], "sizes": ["video-1080p", "video-square", "story"],
        "example": [{"type": "text", "text": "Hello", "name": "greeting", "size": 96, "color": "#ffffff", "x": "center", "y": "center"},
                    {"type": "animate-preset", "targets": ["greeting"], "preset": "pop-in", "start": 0, "duration": "600ms"}],
    },
    "pixel-art": {
        "title": "Pixel art or sprite",
        "keywords": ["pixel", "sprite", "8-bit", "16-bit", "retro game", "tile", "bitmap"],
        "summary": "A small grid of hand-placed colors with a fixed palette, scaled by whole numbers.",
        "approach": ["Use a sprite size or small canvas.", "pixel-art from character rows and a palette; pixel-draw to edit.",
                     "frame-save per animation frame; export with sampling nearest."],
        "operations": ["pixel-art", "pixel-draw", "pixel-palette", "frame-save", "animation-set"],
        "layouts": [], "looks": [], "styles": ["pixel-art"], "sizes": ["sprite-32", "sprite-64", "icon-64"],
        "example": [{"type": "pixel-art", "name": "heart", "palette": {".": "transparent", "#": "#e11d48"},
                     "rows": [".##.##.", "#######", "#######", ".#####.", "..###..", "...#..."]}],
    },
    "hand-drawing": {
        "title": "Hand drawing or sketch cleanup",
        "keywords": ["sketch", "hand drawn", "drawing", "scan", "trace", "vectorize", "ink", "doodle", "line drawing"],
        "summary": "Import a scan, clean and vectorize it, straighten, then fill and restyle: all editable.",
        "approach": ["drawing import, clean, vectorize.", "straighten or smooth strokes; fill regions with color points.", "Run check drawing."],
        "operations": ["drawing", "paint-layer", "paint", "pen", "organic"],
        "layouts": [], "looks": ["sketch", "watercolor", "paper"], "styles": ["hand-drawn", "line-art"], "sizes": ["a4", "photo-square"],
        "example": [{"type": "paint-layer", "name": "ink"},
                    {"type": "paint", "brush": "ink", "points": [[100, 100], [200, 160], [300, 100]], "size": 6, "color": "#111111"}],
    },
    "photo-composition": {
        "title": "Photo with caption or overlay",
        "keywords": ["photo", "image", "picture", "caption", "overlay", "cover", "portrait", "product", "magazine"],
        "summary": "A photograph as the hero, with a scrim or panel keeping text legible.",
        "approach": ["vixl_import_image for the photo.", "layout-apply photo-caption, split-screen or product-card with image=<asset>.",
                     "Adjust with effects (duotone, contrast); check contrast over the image."],
        "operations": ["layout-apply", "replace-contents", "frame", "effect", "mask", "clip"],
        "layouts": ["photo-caption", "split-screen", "product-card", "rule-of-thirds", "editorial-grid"],
        "looks": ["duotone", "film", "grain"], "styles": ["editorial", "scandinavian"], "sizes": ["instagram-post", "photo-5x7", "blog-featured"],
        "example": [{"type": "layout-apply", "name": "photo-caption", "label": "Travel", "title": "A caption headline",
                     "subtitle": "Keep text on the scrim.", "palette": "forest", "seed": 2}],
    },
}

OPERATION_GROUPS = {
    "Create layers": ["add", "solid", "gradient", "text", "shape", "pen", "organic", "organic-shape", "paint-layer", "paint", "pixel-art",
                      "rich-text", "frame", "symbol", "symbol-instance", "field", "drawing", "adjustment"],
    "Arrange and transform": ["move", "resize", "scale", "rotate", "pivot", "flip", "crop", "align", "distribute", "constrain", "unconstrain",
                              "reorder", "raise", "lower", "top", "bottom", "group", "ungroup", "clip", "duplicate", "rename", "remove",
                              "hide", "show", "select-layer", "arrange-grid", "adapt-layout", "fit-text", "text-layout"],
    "Repeat and symmetry": ["repeat", "repeat-blend", "radial-repeat", "place", "snap", "guide", "grid", "pathfinder", "path-fit"],
    "Finish and style": ["look", "layer-style", "effect", "style-set", "style-define", "style-apply", "type-scale", "swatch", "palette-apply",
                         "palette-generate", "palette-define", "opacity", "blend", "mask", "lookup", "lut"],
    "Compose from layouts": ["layout-apply", "template-apply", "container-place", "container-swap", "container-reflow", "shape-place"],
    "Time and pages": ["timeline-set", "keyframe", "animate", "animate-preset", "marker", "page", "master", "frame-save", "frame-apply",
                       "animation-set"],
    "Document and checks": ["canvas", "variable", "artboard", "guidance", "font-register", "font-fallbacks", "layer-intent", "suite-set",
                            "suite-capture", "recipe-set", "action-define", "action-apply", "comp-save", "comp-apply"],
}


def operations_index():
    """Operations grouped by what they are for, each with its one-line summary; anything not grouped is listed under 'other'."""
    from .render import EFFECTS
    from .schema_docs import SUMMARIES
    from .operations import OPERATION_TYPES

    grouped = {name for names in OPERATION_GROUPS.values() for name in names}
    rest = sorted(set(OPERATION_TYPES) - grouped - set(EFFECTS))
    groups = {**OPERATION_GROUPS, **({"Other": rest} if rest else {})}
    return {title: {name: SUMMARIES.get(name, "") for name in names if name in OPERATION_TYPES}
            for title, names in groups.items()} | {"Effects (also {type: <name>})": sorted(EFFECTS)}


def _words(text):
    return {w for w in re.findall(r"[a-z0-9]+", text.lower()) if len(w) > 1}


def match(text):
    """Kinds ranked by how well ``text`` fits their keywords (best first), with scores."""
    wanted = _words(text)
    lowered = text.lower()
    scored = []
    for kind, entry in KINDS.items():
        score = 0
        for keyword in entry["keywords"]:
            if keyword in lowered:
                score += 3 if " " in keyword or keyword == kind else 2
            elif _words(keyword) & wanted:
                score += 1
        if kind.replace("-", " ") in lowered:
            score += 3
        if score:
            scored.append((score, kind))
    return [kind for score, kind in sorted(scored, key=lambda s: (-s[0], s[1]))]


def entry(kind):
    from .layouts import LAYOUTS

    item = KINDS[kind]
    return {"kind": kind, **{k: v for k, v in item.items() if k != "keywords"},
            "layouts": [{"name": name, "description": LAYOUTS[name]["description"]} for name in item["layouts"]]}


def guide(brief=None):
    """The start-here recipe and kinds (no ``brief``), one kind, or the best match for a free-text brief."""
    if not brief or not brief.strip():
        return {"start_here": START_HERE,
                "kinds": {kind: {"title": e["title"], "summary": e["summary"]} for kind, e in KINDS.items()},
                "also": "vixl_guide(brief='operations') lists every operation by purpose; vixl_styles lists design styles; "
                        "vixl_layouts_list lists text layouts. A brief such as 'a mascot for a coffee brand' picks the closest kind.",
                "tip": "Open-ended brief with no text frame (icon, character, scene, pattern)? Start from shape, organic and radial-repeat, "
                       "then look: do not default to a poster layout."}
    key = re.sub(r"[\s_]+", "-", brief.strip().lower())
    if key in ("operations", "ops", "operation", "operations-index"):
        return {"operations": operations_index(),
                "next": "vixl_operation_schema(types=[…]) gives each operation's fields, a summary and examples"}
    if key in ("start-here", "start", "recipe"):
        return {"start_here": START_HERE}
    if key == "looks":
        from .looks import catalog

        return {"looks": catalog(), "apply": "{type: look, target: LAYER, look: NAME [, color, amount 0-1, remove: true]}; "
                "amount moves a look between subtle (0) and strong (1); looks are ordinary styles and effects, so they export "
                "to PNG and SVG like hand-added ones (svg: native = SVG filters, raster = embedded raster fallback)"}
    if key == "styles":
        from .styles import listing

        return listing()
    if key in KINDS:
        return {**entry(key), "start_here": START_HERE}
    ranked = match(brief)
    if not ranked:
        raise VixlError("no_match", f"No kind of work matches {brief!r}; kinds: {', '.join(KINDS)}. Call vixl_guide() for the start-here "
                                    "recipe.", field="brief", suggestions=list(KINDS)[:6], allowed=list(KINDS))
    best = ranked[0]
    return {"matched": best, **entry(best), "alternatives": ranked[1:4], "start_here": START_HERE}
