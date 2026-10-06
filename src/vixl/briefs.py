"""What to make, and with which tools: a map from a brief to operations, layouts, looks and styles.

Layouts are text compositions, so "make ten cool things" drifts toward ten posters. This module is
the other half: for each kind of brief (icon, character, scene, pattern, mandala, logo, diagram,
social card, slides …) it names the approach, the operations that build it, the layouts, looks and
styles that suit it, the checks to run, and a small working example. ``guide`` answers a kind name, a
guidance name (``guidance.py``: natural-motion, imperfection …) or a free-text brief; with no argument it
returns the start-here recipe, every kind and every guidance name.
"""

import re

from .errors import VixlError

START_HERE = [
    "Sparse briefs use fresh seeds and curated safe choices. Keep the returned seed to reproduce a direction, "
    "pass explicit palette/font/style choices to lock them, or set .vixl/variety.json to {variety: fixed, seed: 0}.",
    "Size: pick a named size (vixl_sizes_list) and vixl_document_create(size=…).",
    "Structure: for anything with text, vixl_layouts_list then layout-apply, filling every slot it lists (seed makes it repeatable). "
    "For art without a text frame (icons, characters, scenes, patterns), build from shape, pen, pathfinder, organic and radial-repeat.",
    "Type: vixl_fonts then vixl_font_pair (the bundled font is a proofing fallback).",
    "Finish: apply a look (glow, soft-shadow, hard-shadow, gradient, grain, paper …) so flat shapes read as finished; "
    "tag a style (vixl_styles) when the brief names a look.",
    "Check: vixl_check, fix the 'fix' findings, glance at 'review', then vixl_render_preview and vixl_export_file. "
    "vixl_operations_apply(check=true, preview=true) returns the findings and a small preview with the edit itself.",
]
# Art without a text frame: a rolled direction (palette, layout-apply steps) would steer these toward a poster.
NO_DIRECTION = {"character", "scene", "pattern", "mandala", "animation", "pixel-art", "hand-drawing"}

KINDS = {
    "comic": {
        "title": "Comic page or sequential panels",
        "keywords": ["comic", "manga", "panels", "storytelling", "speech bubble"],
        "summary": "A panel grid with editable captions and speech bubbles; each panel can hold an image or scene.",
        "approach": ["Create the page size and a comic-layout panel grid.",
                     "Place scene art in panels, then add speech-bubble and caption elements in reading order."],
        "operations": ["comic-layout", "speech-bubble", "caption", "page", "image-slot"],
        "layouts": [], "looks": ["outline", "subtle-grain"], "styles": ["line-art"], "sizes": ["a4", "instagram-portrait"],
        "example": [{"type": "comic-layout", "panels": [{"caption": "An idea begins."}, {"caption": "Then it grows."}], "columns": 2}],
    },
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
        "guidance": ["typography", "layout"],
        "example": [{"type": "layout-apply", "name": "hero-statement", "title": "Make it simple", "subtitle": "One idea, said well.",
                     "label": "Open call", "cta": "Join in", "palette": "midnight", "seed": 7}],
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
    "meme": {
        "title": "Meme or reaction image",
        "keywords": ["meme", "memes", "reaction", "caption", "top text", "bottom text", "four panel", "gif"],
        "summary": "A picture with a few huge stroked words, or labelled panels; text fits its box and reads on any image.",
        "approach": ["Create a social size (instagram-post, story).",
                     "layout-apply a meme layout with image or images set to assets you may use, and short captions.",
                     "Install an OFL Impact-style face (Anton) for the captions; check, preview small, export."],
        "operations": ["layout-apply", "fit-text", "text-set", "animate-preset", "motion"],
        "layouts": ["meme-top-bottom", "meme-caption-above", "meme-comparison", "meme-labelled", "meme-reaction",
                    "meme-four-panel"],
        "looks": ["outline"], "styles": [], "sizes": ["instagram-post", "story", "x-post"],
        "guidance": ["meme"],
        "example": [{"type": "layout-apply", "name": "meme-top-bottom", "title": "When the build passes",
                     "caption": "On the first try", "seed": 1}],
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
        "guidance": ["logo"],
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
        "guidance": ["icon"],
        "example": [{"type": "layout-apply", "name": "app-icon", "title": "Notes", "palette": "ocean", "seed": 5}],
    },
    "character": {
        "title": "Character or mascot",
        "keywords": ["character", "mascot", "creature", "animal", "robot", "monster", "face", "cartoon", "avatar", "sticker", "teddy"],
        "summary": "A figure built from named, grouped parts with pivots at its joints, so it reads as one silhouette and can move.",
        "approach": ["Square or sticker canvas; decide the silhouette and the one gesture it makes.",
                     "character makes a standard rig (torso, head, eyes, mouth, segmented limbs with pivots) to restyle; or draw "
                     "parts with shape, organic and pen, merging outlines with pathfinder.",
                     "Group parts into joints (the head with its features, an arm with its hand) and set a pivot at each joint.",
                     "Give it character: irregular strength subtle on the body parts (not the eyes), texture with drawn-texture "
                     "or cut-paper, then a look.",
                     "character-save keeps a reusable rig; to animate it, vixl_guide('animation')."],
        "operations": ["character", "character-rig", "character-pose", "character-save", "character-load", "shape", "organic",
                       "pen", "pathfinder", "group", "pivot", "irregular", "drawn-texture", "cut-paper", "look", "layer-style"],
        "layouts": ["emblem", "centered-axis"], "looks": ["outline", "soft-shadow", "hard-shadow"],
        "styles": ["kawaii", "neo-brutalist", "hand-drawn", "line-art"], "sizes": ["sticker", "profile-picture", "discord-emoji"],
        "guidance": ["character-rigging", "anatomy-proportions", "imperfection"],
        "example": [
            {"type": "shape", "shape": "ellipse", "name": "body", "x": 290, "y": 270, "width": 220, "height": 240, "fill": "#c8925a"},
            {"type": "shape", "shape": "ellipse", "name": "ear-left", "x": 300, "y": 90, "width": 64, "height": 64, "fill": "#b07a48"},
            {"type": "shape", "shape": "ellipse", "name": "ear-right", "x": 436, "y": 90, "width": 64, "height": 64, "fill": "#b07a48"},
            {"type": "shape", "shape": "ellipse", "name": "head", "x": 300, "y": 100, "width": 200, "height": 190, "fill": "#c8925a"},
            {"type": "shape", "shape": "ellipse", "name": "muzzle", "x": 370, "y": 205, "width": 60, "height": 44, "fill": "#f1d2a8"},
            {"type": "shape", "shape": "ellipse", "name": "eye-left", "x": 355, "y": 165, "width": 24, "height": 30, "fill": "#2b1d14"},
            {"type": "shape", "shape": "ellipse", "name": "eye-right", "x": 421, "y": 165, "width": 24, "height": 30, "fill": "#2b1d14"},
            {"type": "shape", "shape": "rounded-rectangle", "name": "arm", "x": 480, "y": 290, "width": 54, "height": 140,
             "fill": "#b07a48"},
            {"type": "pivot", "target": "arm", "value": "top"},
            {"type": "group", "name": "head-group", "targets": ["ear-left", "ear-right", "head", "muzzle", "eye-left", "eye-right"]},
            {"type": "group", "name": "mascot", "targets": ["arm", "body", "head-group"]},
            {"type": "irregular", "targets": ["body", "head", "ear-left", "ear-right", "arm"], "seed": 7, "strength": "subtle"},
            {"type": "look", "target": "mascot", "look": "soft-shadow"},
        ],
    },
    "scene": {
        "title": "Scene or illustration",
        "keywords": ["scene", "illustration", "landscape", "sunset", "mountains", "forest", "sky", "city", "poster art", "background", "nature"],
        "summary": "Depth from layered flat shapes: sky gradient, sun, hills and foreground, with organic forms for plants.",
        "approach": ["Fill the canvas with a sky gradient.", "Stack hills and buildings back to front, darker toward the foreground.",
                     "Add a sun or moon with a glow; plant organic trees, flowers or ferns.",
                     "For an illustrated rather than computed feel, irregular (subtle) the drawn shapes and tear any paper; keep "
                     "the sky and frame clean.", "Finish with grain; check the preview."],
        "operations": ["gradient", "shape", "pen", "organic", "organic-shape", "irregular", "tear", "look", "layer-style", "paint",
                       "radial-repeat"],
        "layouts": ["photo-caption", "rule-of-thirds"], "looks": ["glow", "grain", "paper", "watercolor", "gradient"],
        "styles": ["retro-futurism", "mid-century-modern", "hand-drawn", "risograph"], "sizes": ["instagram-post", "web-hero", "poster-18x24"],
        "guidance": ["natural-color-light", "illustration-perspective", "imperfection"],
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
        "keywords": ["pattern", "texture", "tile", "wallpaper", "seamless", "repeat", "grid", "dots", "stripes", "background", "gradient",
                     "scatter", "confetti", "terrazzo"],
        "summary": "Motifs scattered irregularly (an even grid reads as a table, not a pattern), or a textured field.",
        "approach": ["Draw one or two motifs, or use organic generators (leaf, petal, blob) as motifs.",
                     "Scatter them: an organic layer with a scatter rule (Poisson-disc spacing, varied size and turn) covers the "
                     "canvas evenly without a grid; vary a set of drawn copies with irregular only [placement, color].",
                     "Use repeat or arrange-grid only when the brief asks for a grid (stripes, checks, polka dots).",
                     "For a seamless tile, pattern-define the result and check its seams (vixl_workflow pattern-check); motifs "
                     "crossing an edge are not wrapped, so keep them inside the tile.",
                     "Or fill with gradient layers and apply grain, paper or halftone looks."],
        "operations": ["organic", "shape", "irregular", "duplicate", "group", "pattern-define", "pattern-fill", "repeat",
                       "arrange-grid", "gradient", "look"],
        "layouts": [], "looks": ["grain", "paper", "halftone", "duotone"], "styles": ["memphis", "risograph", "minimalist"],
        "sizes": ["web-hero", "photo-square", "phone-wallpaper"],
        "guidance": ["imperfection", "drawn-textures"],
        "example": [
            {"type": "solid", "name": "ground", "color": "#fff7ed"},
            {"type": "organic", "name": "scatter", "seed": 11, "x": 0, "y": 0, "width": 800, "height": 600, "stretch": True, "parts": [
                {"name": "leaves", "generator": "leaf", "fill": "#3f7d4e",
                 "rules": [{"rule": "scatter", "count": 26, "within": "square", "scale": 0.09, "size_variation": 0.3}]},
                {"name": "dots", "generator": "blob", "fill": "#f97316",
                 "rules": [{"rule": "scatter", "count": 40, "within": "square", "scale": 0.025, "size_variation": 0.4}]}]},
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
        "guidance": ["print", "typography"],
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
        "keywords": ["animation", "animate", "animated", "gif", "motion", "video", "loop", "looping", "lyric", "kinetic", "sprite",
                     "timeline", "bounce", "pulse", "stagger", "typing", "idle", "wave", "e-card"],
        "summary": "Motion recipes, character cycles and keyframes on a finished still, checked frame by frame, exported as GIF, MP4 or WebM.",
        "approach": ["Build the still first and keep the whole message readable at frame 0; keep moving layers off the text.",
                     "Decide the one gesture and design the loop first: every track returns to its frame-0 value, so the duration "
                     "is a whole number of periods.",
                     "Group parts into joints and set a pivot at each joint before rotating anything.",
                     "Loops and staggered motion are one motion operation (hover, breathing, blink, wiggle, orbit, bounce) with "
                     "period, several targets and stagger; character-cycle for walk/idle/react on a rig; keyframes for custom "
                     "moves; animate-preset for entrances.",
                     "Check: vixl_check(checks=[motion, character]), vixl_timeline_preview at the first, middle and last frames "
                     "(the last should flow into the first), vixl_timeline_inspect for the tracks; then vixl_export_timeline."],
        "operations": ["timeline-set", "motion", "character-cycle", "pivot", "group", "keyframes", "keyframe", "animate-preset",
                       "animate", "marker", "character", "character-rig"],
        "layouts": [], "looks": ["glow"], "styles": ["pixel-art", "retro-futurism"], "sizes": ["video-1080p", "video-square", "story"],
        "guidance": ["looping-motion", "natural-motion", "character-rigging", "motion"],
        "example": [
            {"type": "timeline-set", "duration": 2000, "fps": 24, "loop": 0},
            {"type": "shape", "shape": "ellipse", "name": "body", "x": 320, "y": 230, "width": 160, "height": 180, "fill": "#c8925a"},
            {"type": "shape", "shape": "rounded-rectangle", "name": "arm", "x": 460, "y": 250, "width": 40, "height": 110,
             "fill": "#b07a48"},
            {"type": "pivot", "target": "arm", "value": "top"},
            {"type": "motion", "recipe": "wiggle", "targets": ["arm"], "amount": 25, "frequency": 1, "duration": 2000},
            {"type": "motion", "recipe": "breathing", "targets": ["body"], "amount": 3, "period": 1000, "duration": 2000},
            {"type": "shape", "shape": "ellipse", "name": "dot-1", "x": 340, "y": 450, "width": 24, "height": 24, "fill": "#111827"},
            {"type": "shape", "shape": "ellipse", "name": "dot-2", "x": 388, "y": 450, "width": 24, "height": 24, "fill": "#111827"},
            {"type": "shape", "shape": "ellipse", "name": "dot-3", "x": 436, "y": 450, "width": 24, "height": 24, "fill": "#111827"},
            # Typing dots: phase (in cycles) offsets each dot inside the loop; stagger instead delays each start.
            *({"type": "motion", "recipe": "hover", "targets": [f"dot-{n}"], "amount": 8, "period": 1000, "duration": 2000,
               "phase": -0.15 * (n - 1)} for n in (1, 2, 3)),
        ],
    },
    "pixel-art": {
        "title": "Pixel art or sprite",
        "keywords": ["pixel", "sprite", "8-bit", "16-bit", "retro game", "tile", "bitmap"],
        "summary": "A small grid of hand-placed colors with a fixed palette, scaled by whole numbers.",
        "approach": ["Use a sprite size or small canvas.", "pixel-art from character rows and a palette; pixel-draw to edit.",
                     "frame-save per animation frame; export with sampling nearest."],
        "operations": ["pixel-art", "pixel-draw", "pixel-palette", "frame-save", "animation-set"],
        "layouts": [], "looks": [], "styles": ["pixel-art"], "sizes": ["sprite-32", "sprite-64", "icon-64"],
        "guidance": ["pixel-art"],
        "example": [{"type": "pixel-art", "name": "heart", "x": 260, "y": 160, "palette": {".": "transparent", "#": "#e11d48"},
                     "rows": [".##.##.", "#######", "#######", ".#####.", "..###..", "...#..."]},
                    {"type": "resize", "target": "heart", "width": 280}],
    },
    "hand-drawing": {
        "title": "Hand drawing or sketch cleanup",
        "keywords": ["sketch", "hand drawn", "drawing", "scan", "trace", "vectorize", "ink", "doodle", "line drawing"],
        "summary": "Import a scan, clean and vectorize it, straighten, then fill and restyle: all editable.",
        "approach": ["drawing import, clean, vectorize.", "straighten or smooth strokes; fill regions with color points.",
                     "Drawn from scratch? pen or paint, then irregular (subtle) so vector lines waver like ink.", "Run check drawing."],
        "operations": ["drawing", "paint-layer", "paint", "pen", "organic", "irregular", "drawn-texture"],
        "layouts": [], "looks": ["sketch", "watercolor", "paper"], "styles": ["hand-drawn", "line-art"], "sizes": ["a4", "photo-square"],
        "guidance": ["drawn-textures", "brush", "imperfection"],
        "example": [{"type": "paint-layer", "name": "ink"},
                    {"type": "paint", "brush": "ink", "size": 8, "color": "#111111",
                     "points": [[200, 300], [260, 220], [340, 200], [420, 240], [440, 320], [380, 380], [300, 380]]}],
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
    "Compose from layouts": ["layout-apply", "template-apply", "container-place", "container-swap", "container-reflow", "container-variant", "container-fill", "image-slot", "shape-place"],
    "Time and pages": ["timeline-set", "keyframe", "animate", "animate-preset", "marker", "page", "master", "frame-save", "frame-apply",
                       "animation-set"],
    "Document and checks": ["canvas", "variable", "artboard", "guidance", "font-register", "font-fallbacks", "layer-intent", "suite-set",
                            "suite-capture", "recipe-set", "action-define", "action-apply", "comp-save", "comp-apply"],
}


def operations_index():
    """Operations grouped by what they are for, each with its one-line summary; anything not grouped is listed under 'other'."""
    from .render import EFFECTS
    from .schema import operation_schema
    from .operations import OPERATION_TYPES

    summaries = {v["properties"]["type"]["const"]: v.get("description", "")
                 for v in operation_schema()["properties"]["operations"]["items"]["oneOf"]}

    grouped = {name for names in OPERATION_GROUPS.values() for name in names}
    rest = sorted(set(OPERATION_TYPES) - grouped - set(EFFECTS))
    groups = {**OPERATION_GROUPS, **({"Other": rest} if rest else {})}
    return {title: {name: summaries.get(name, "") for name in names if name in OPERATION_TYPES}
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
    result = {"kind": kind, **{k: v for k, v in item.items() if k != "keywords"},
              "layouts": [{"name": name, "description": LAYOUTS[name]["description"]} for name in item["layouts"]]}
    if kind in item.get("guidance", []):
        # Guidance named like the kind (logo, pixel-art) cannot be asked for by name here, so it comes inline.
        from .guidance import GUIDANCE

        result["principles"] = GUIDANCE[kind]
    if item.get("guidance"):
        result["read_guidance"] = "vixl_guide(brief=NAME) returns each guidance text"
    return result


def _directed(result, kind, seed, variety, workspace):
    if kind not in NO_DIRECTION:
        from .typefaces import roll_document

        result["direction"] = roll_document(workspace=workspace, seed=seed, variety=variety, purpose=kind)
    return result


def guidance(name, *, workspace=None):
    """One named guidance text (built in or user-added) and the kinds of work that point at it, or None."""
    from .resources import catalog

    texts = catalog("guidance", workspace=workspace)
    if name not in texts:
        return None
    result = {"guidance": name, "text": texts[name]}
    kinds = [kind for kind, item in KINDS.items() if name in item.get("guidance", [])]
    if kinds:
        result["kinds"] = kinds
    return result


def guide(brief=None, *, seed=None, variety=None, workspace=None):
    """The start-here recipe and kinds (no ``brief``), one kind, one guidance text, or the best match for a free-text brief."""
    if not brief or not brief.strip():
        from .resources import catalog

        return {"start_here": START_HERE,
                "kinds": {kind: {"title": e["title"], "summary": e["summary"]} for kind, e in KINDS.items()},
                "guidance": sorted(catalog("guidance", workspace=workspace)),
                "also": "vixl_guide(brief=<kind or guidance name>) returns it; vixl_capabilities(topic) returns task-specific "
                        "fields and gotchas; vixl_guide(brief='operations') lists every operation by purpose; vixl_styles lists "
                        "design styles; vixl_layouts_list lists text layouts. A brief such as 'a mascot for a coffee brand' picks "
                        "the closest kind.",
                "tip": "Open-ended brief with no text frame (icon, character, scene, pattern)? Start from shape, organic and radial-repeat, "
                       "then look: do not default to a poster layout."}
    key = re.sub(r"[\s_]+", "-", brief.strip().lower())
    if key in ("safe-pools", "safe", "variety"):
        from .safe_catalog import catalog

        return catalog()
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
        return _directed({**entry(key), "start_here": START_HERE}, key, seed, variety, workspace)
    found = guidance(key, workspace=workspace)
    if found:
        return found
    ranked = match(brief)
    if not ranked:
        raise VixlError("no_match", f"No kind of work matches {brief!r}; kinds: {', '.join(KINDS)}. Call vixl_guide() for the start-here "
                                    "recipe and the guidance names.", field="brief", suggestions=list(KINDS)[:6], allowed=list(KINDS))
    best = ranked[0]
    return _directed({"matched": best, **entry(best), "alternatives": ranked[1:4], "start_here": START_HERE},
                     best, seed, variety, workspace)
