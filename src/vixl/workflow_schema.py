"""Typed, described request fields for every workflow action, and the check-suite object.

``vixl_workflow_schema`` publishes these so an agent can build a request from the tool surface
alone. They are descriptive: ``workflows.dispatch`` and the owning modules still validate.
"""

from copy import deepcopy

from .logo_package import field_types as _logo_package_types

STR = {"type": "string"}
PATH = {"type": "string", "description": "Workspace-relative path."}
COLOR = {"type": "string", "description": "Any Vixl color: name, #hex, rgb()/hsl()/…, or @swatch."}
STRINGS = {"type": "array", "items": STR}
REGION = {"type": "array", "items": {"type": "integer"}, "minItems": 4, "maxItems": 4,
          "description": "Integer [x, y, width, height] inside the canvas."}
SCALAR = {"type": ["string", "number", "boolean"]}

LOGO_PACKAGE_TYPES = _logo_package_types()

# Check suite (assert-rule format). Rule fields per kind live in assurance.RULE_FIELDS; each
# rule needs a unique id and a kind, and may set severity.
RULE_KINDS = ("container", "palette", "assert", "design", "property", "gap", "unchanged", "pixels", "text-fit", "alpha")
RULE_PROPERTIES = {
    "id": {"type": "string", "description": "Unique rule ID within the suite; shown in results."},
    "kind": {"type": "string", "enum": list(RULE_KINDS),
             "description": "What the rule measures: assert (expression), property, gap, text-fit, design "
                            "(checks.py options), palette, container, unchanged, pixels or alpha."},
    "severity": {"type": "string", "enum": ["error", "warning"], "default": "error",
                 "description": "A failed warning needs review instead of failing the suite."},
    "expression": {"type": "string",
                   "description": "assert: bounded assertion, e.g. 'layer.logo.bounds within canvas', "
                                  "'canvas.width >= 1080', 'text.title.font-size >= 24', 'layer.logo.opacity == 1'."},
    "target": {"type": "string", "description": "Layer ID or name (property and text-fit; container may omit it)."},
    "field": {"type": "string", "description": "property: the layer field to read, e.g. 'color', 'x', 'opacity'."},
    "expected": {"type": ["string", "number", "boolean", "array", "object", "null"],
                 "description": "property: required value; gap: required distance in pixels."},
    "tolerance": {"type": "number", "minimum": 0,
                  "description": "Allowed difference: numbers for property/gap (default gap 1 px), 0–255 colour "
                                 "distance for palette, 0–255 channel difference for pixels."},
    "before": {"type": "string", "description": "gap: the first sibling layer."},
    "after": {"type": "string", "description": "gap: the second sibling layer."},
    "axis": {"type": "string", "enum": ["horizontal", "vertical"], "default": "vertical",
             "description": "gap: direction of the distance."},
    "minimum": {"type": "number", "description": "text-fit: smallest allowed font size; alpha: lowest fraction "
                                                  "of non-opaque pixels."},
    "maximum": {"type": "number", "description": "alpha: highest fraction (0–1) of pixels with alpha below 255."},
    "options": {"type": "object", "description": "design: arguments for the design check, e.g. {checks: "
                                                  "['bounds', 'contrast'], safe_area: '5%', min_contrast: 4.5}."},
    "palette": {"type": "string", "description": "palette: name of a palette (defaults to the applied one)."},
    "colors": {"type": "array", "items": STR, "minItems": 2,
               "description": "palette: allowed colors, instead of a palette name."},
    "max_fraction": {"type": "number", "minimum": 0, "maximum": 1, "default": 0.01,
                     "description": "palette: share of pixels allowed outside the palette."},
    "alpha_min": {"type": "integer", "minimum": 1, "maximum": 255, "default": 1,
                  "description": "palette: lowest alpha that counts as drawn."},
    "region": {**REGION, "description": "palette/pixels: [x, y, width, height] to measure (default whole canvas)."},
    "snapshot": {"type": "object", "description": "unchanged: captured layer (written by suite-capture)."},
    "asset": {"type": "string", "description": "pixels: embedded baseline image asset (written by suite-capture)."},
}
SUITE = {
    "type": "object",
    "description": "Check suite: rules measured against the rendered document; checks never change it.",
    "properties": {
        "version": {"type": "integer", "enum": [1], "default": 1, "description": "Suite format version."},
        "description": {"type": "string", "description": "What the suite protects."},
        "rules": {
            "type": "array", "minItems": 1, "maxItems": 256,
            "description": "One entry per requirement, e.g. {id: 'logo-inside', kind: 'assert', expression: "
                           "'layer.logo.bounds within canvas'}.",
            "items": {"type": "object", "properties": RULE_PROPERTIES, "required": ["id", "kind"]},
        },
        "sampling": {
            "type": "object", "description": "Which animation times to check (default still).",
            "properties": {
                "mode": {"type": "string", "enum": ["still", "sampled", "all", "times"], "default": "still",
                         "description": "still: the current frame; sampled: evenly spaced; all: every frame; times: listed."},
                "count": {"type": "integer", "minimum": 2, "maximum": 3600, "default": 8,
                          "description": "sampled: evenly spaced samples (plus every keyframe time)."},
                "times": {"type": "array", "items": {"type": ["number", "string"]}, "minItems": 1,
                          "maxItems": 3600, "description": "times: ms, '500ms', '1.5s' or marker names."},
            },
        },
    },
    "required": ["rules"],
    "examples": [{"version": 1, "rules": [
        {"id": "logo-inside", "kind": "assert", "expression": "layer.logo.bounds within canvas"},
        {"id": "title-fits", "kind": "text-fit", "target": "title", "minimum": 24},
    ]}],
}

# Fields that mean the same thing in every action. ``describe`` shows an action's override first.
COMMON = {
    "dry_run": {"type": "boolean", "description": "Validate and report without writing."},
    "replace": {"type": "boolean", "default": False, "description": "Overwrite an existing output or package."},
    "workers": {"type": "integer", "minimum": 1, "maximum": 4, "default": 1, "description": "Parallel workers."},
    "output": PATH,
    "directory": {**PATH, "description": "Workspace-relative folder."},
    "spec": {"type": "object", "description": "Specification object; see the action's docs."},
    "job": {"type": "object", "description": "Job description; see submit."},
    "operations": {"type": "array", "items": {"type": "object"}, "minItems": 1, "maxItems": 1000,
                   "description": "Operation objects, as for vixl_operations_apply."},
    "id": {"type": "string", "description": "Job or library item ID returned by an earlier call."},
    "name": {"type": "string", "description": "Resource name: 1–100 letters, numbers, _ or -."},
    "suites": {"type": "array", "items": STR, "description": "Names of attached suites to enforce; omitted "
                                                              "means none."},
    "variables": {"type": "object", "additionalProperties": SCALAR,
                  "description": "Variable overrides {name: string|number|boolean}."},
    "target": {"type": "string", "description": "Layer ID or unique name."},
    "kind": {"type": "string", "enum": ["palettes", "templates", "guidance", "containers", "shapes", "suites",
                                        "workflows"], "description": "Resource category."},
    "start": {"type": "boolean", "default": False, "description": "Start a background worker after submitting."},
}

# Lyric-video request fields (docs/lyric-video.md); identical for plan, build and export.
LYRIC = {
    "audio": {**PATH, "description": "The song (any ffmpeg-readable audio)."},
    "lyrics": {**PATH, "description": "Timed LRC file."},
    "template": {**PATH, "description": "A .vixl template with bg-*, lyric-line and optional lyric-next layers."},
    "build": {**PATH, "description": "Where lyric-video-build writes the keyframed .vixl document."},
    "output": {**PATH, "description": "lyric-video-export: the .mp4 or .webm to write."},
    "fps": {"type": "number", "minimum": 1, "maximum": 60, "default": 24, "description": "Frames per second."},
    "quality": {"type": "string", "enum": ["draft", "final"], "default": "final",
                "description": "draft renders at most 640 px wide."},
    "offset": {"type": "number", "default": 0, "description": "ms added to the LRC offset; positive shows "
                                                              "lyrics earlier."},
    "lead": {"type": "number", "minimum": 0, "maximum": 10000, "default": 150,
             "description": "ms a line shows before its timestamp."},
    "gap": {"type": "number", "minimum": 0, "maximum": 10000, "default": 0,
            "description": "ms a line hides before the next one shows."},
    "max_hold": {"type": "number", "minimum": 100, "default": 8000, "description": "Longest a line stays up, ms."},
    "animation": {"type": "object", "description": "Line entrance/exit.", "properties": {
        "in": {"type": "string", "default": "fade-in", "description": "fade-in, slide-in-left|right|up|down, "
                                                                      "pop-in, zoom-in, typewriter or none."},
        "out": {"type": "string", "default": "fade-out", "description": "fade-out, slide-out-*, pop-out, "
                                                                         "zoom-out or none."},
        "duration": {"type": "number", "minimum": 0, "maximum": 5000, "default": 300, "description": "ms."},
        "distance": {"type": "number", "minimum": 0, "description": "Slide distance in pixels."}}},
    "next_line": {"type": "boolean", "default": True, "description": "Fill lyric-next with the upcoming line."},
    "camera": {"type": "object", "description": "Slow camera move: {from, to}, each [center-x, center-y, zoom] "
                                               "(0–1, 0–1, 1–16).",
               "properties": {"from": {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3,
                                       "description": "Start pose [center-x, center-y, zoom]."},
                              "to": {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3,
                                     "description": "End pose [center-x, center-y, zoom]."}}},
    "start": {"type": "number", "minimum": 0, "default": 0, "description": "Song position to start at, ms."},
    "end": {"type": "number", "minimum": 1, "description": "Song position to stop at, ms (default the end)."},
    "check": {"type": "boolean", "default": True, "description": "Run the design checks on the build."},
    "replace": {"type": "boolean", "default": False, "description": "Overwrite an existing build or output."},
    "width": {"type": "integer", "minimum": 16, "maximum": 4096, "description": "Video width (default template)."},
    "height": {"type": "integer", "minimum": 16, "maximum": 4096, "description": "Video height (default template)."},
}

PRODUCTION_SPEC = {
    "type": "object", "description": "Variant plan; see docs/production.md.",
    "properties": {
        "version": {"type": "integer", "enum": [1], "description": "Spec format version."},
        "rows": {"type": "array", "items": {"type": "object"}, "maxItems": 10000,
                 "description": "Input rows {variable: value}; one set of outputs per row."},
        "matrix": {"type": "object", "description": "{variable: [choices]}; every combination is produced "
                                                    "(up to 10 axes, 100 choices each)."},
        "artboards": {"type": "array", "items": STR, "maxItems": 100, "description": "Artboard names to render."},
        "kind": {"type": "string", "enum": ["image", "timeline"], "default": "image",
                 "description": "Stills or animation per variant."},
        "format": {"type": "string", "enum": ["png", "jpg", "webp", "svg", "gif", "mp4", "webm", "zip"],
                   "description": "image: png/jpg/webp/svg; timeline: gif/webp/mp4/webm/zip."},
        "quality": {"type": "string", "enum": ["draft", "final"], "default": "final",
                    "description": "draft renders a 640 px proxy."},
        "suites": {"type": "array", "items": STR, "description": "Suites to check (default all attached)."},
        "actions": {"type": "array", "items": STR, "description": "Saved actions to run before checks."},
        "repair_actions": {"type": "array", "items": STR, "maxItems": 3,
                           "description": "Saved actions tried in order when checks fail."},
        "workers": {"type": "integer", "minimum": 1, "maximum": 4, "default": 1, "description": "Parallel renders."},
        "motion": {"type": "string", "description": "Saved motion to apply."},
        "fps": {"type": "number", "minimum": 1, "maximum": 60, "description": "Timeline fps override."},
    },
}
FILM_SPEC = {
    "type": "object", "description": "Shot sequence; see docs/production.md.",
    "properties": {
        "version": {"type": "integer", "enum": [1], "description": "Spec format version."},
        "width": {"type": "integer", "minimum": 1, "description": "Frame width in pixels."},
        "height": {"type": "integer", "minimum": 1, "description": "Frame height in pixels."},
        "fps": {"type": "number", "minimum": 1, "maximum": 60, "default": 30, "description": "Frames per second."},
        "quality": {"type": "string", "enum": ["draft", "final"], "default": "final",
                    "description": "draft renders half-size proxies."},
        "shots": {"type": "array", "minItems": 1, "maxItems": 100, "description": "Shots in order.", "items": {
            "type": "object", "required": ["source", "duration"], "properties": {
                "source": {**PATH, "description": "A .vixl document (or media) in the workspace."},
                "duration": {"type": "number", "minimum": 10, "description": "Shot length, ms."},
                "trim": {"type": "number", "minimum": 0, "description": "Start offset into the source, ms."},
                "transition": {"type": "number", "minimum": 0, "maximum": 2000, "description": "Crossfade, ms."},
                "camera": {"type": "object", "description": "{from, to} poses [center-x, center-y, zoom]."},
                "variables": {"type": "object", "description": "Variable overrides for the shot."},
                "artboard": {"type": "string", "description": "Artboard to render."}}}},
        "captions": {"type": "array", "maxItems": 1000, "description": "Overlay text with start/end ms.",
                     "items": {"type": "object", "required": ["text", "start", "end"]}},
        "audio": {"type": "array", "maxItems": 8, "description": "Audio tracks {source, start, trim, volume}.",
                  "items": {"type": "object", "required": ["source"]}},
    },
    "required": ["width", "height", "shots"],
}
JOB = {
    "type": "object", "required": ["kind", "output"],
    "description": "Background job: kind plus the fields it needs (production/film: spec; lyric-video/form-fill: "
                   "request; video/generate: provider and request).",
    "properties": {
        "kind": {"type": "string", "enum": ["production", "film", "generate", "video", "lyric-video", "form-fill"],
                 "description": "Which kind of work to queue."},
        "output": {**PATH, "description": "Where the result is written (must be new, except production folders)."},
        "source": {**PATH, "description": "Source .vixl document; production, generate and form-fill need it."},
        "spec": {"type": "object", "description": "production or film specification (see plan / film-plan)."},
        "request": {"type": "object", "description": "lyric-video, form-fill, video or generate request fields."},
        "provider": {"type": "string", "description": "video/generate: explicit configured provider."},
    },
}
RECIPE = {
    "type": "object", "description": "Document recipe: typed inputs plus optional actions and examples.",
    "properties": {
        "version": {"type": "integer", "enum": [1], "description": "Recipe format version."},
        "description": {"type": "string", "description": "What the recipe makes."},
        "inputs": {"type": "object", "description": "{input name: {type, default, required, enum, minimum, "
                                                    "maximum, maxLength}}; type is string, number, integer, "
                                                    "boolean, color or asset.",
                   "additionalProperties": {"type": "object", "properties": {
                       "type": {"type": "string", "enum": ["string", "number", "integer", "boolean", "asset", "color"],
                                "default": "string", "description": "Kind of value."},
                       "default": {**SCALAR, "description": "Value used when none is given."},
                       "required": {"type": "boolean", "default": True, "description": "Fail when no value or default."},
                       "enum": {"type": "array", "description": "Allowed values."},
                       "minimum": {"type": "number", "description": "Lowest number."},
                       "maximum": {"type": "number", "description": "Highest number."},
                       "maxLength": {"type": "integer", "minimum": 1, "description": "Longest string."}}}},
        "actions": {"type": "array", "items": STR, "maxItems": 100, "description": "Saved actions run on instantiate."},
        "examples": {"type": "array", "items": {"type": "object"}, "maxItems": 100,
                     "description": "Sample input values, each checked against every attached suite."},
    },
}
MANIFEST = {
    "type": "object", "required": ["api_version", "name", "version", "resources"],
    "description": "Plugin pack: resources namespaced by the pack name (docs/studio.md).",
    "properties": {
        "api_version": {"type": "integer", "enum": [1], "description": "Plugin API version (1)."},
        "name": {"type": "string", "description": "Pack name; resource names must start with '<name>-'."},
        "version": {"type": "string", "pattern": r"^\d+\.\d+\.\d+$", "description": "major.minor.patch."},
        "description": {"type": "string", "description": "What the pack provides."},
        "dependencies": {"type": "object", "additionalProperties": {"type": "string"},
                         "description": "{pack name: exact version}."},
        "resources": {"type": "object", "minProperties": 1, "description": "{category: {name: value}}.",
                      "additionalProperties": {"type": "object"}},
    },
}

# Per-action overrides and fields only one action (or family) uses.
ACTION_FIELDS = {
    "check": {
        "suite": {"anyOf": [STR, SUITE], "description": "Name of an attached suite, or an inline suite object."},
        "mode": {"type": "string", "enum": ["still", "sampled", "all", "times"],
                 "description": "Override the suite's coverage: still frame, sampled times, every frame or times."},
        "variables": {**COMMON["variables"], "description": "Variable overrides applied before checking."},
        "artboard": {"type": "string", "description": "Check this artboard's variant of the document."},
    },
    "act": {
        "operations": {**COMMON["operations"], "description": "Operations applied to a candidate; committed only "
                                                              "if every suite passes."},
        "suites": {**COMMON["suites"], "description": "Attached suites that must pass for the change to commit."},
        "dry_run": {"type": "boolean", "description": "Apply and check without committing."},
    },
    "capture": {
        "recipe": RECIPE,
        "bindings": {"type": "object", "description": "{input name: {target: layer, field: text|color|fill|start|end}}.",
                     "additionalProperties": {"type": "object", "required": ["target", "field"], "properties": {
                         "target": {"type": "string", "description": "Layer ID or name."},
                         "field": {"type": "string", "enum": ["text", "color", "fill", "start", "end"],
                                   "description": "The layer field the input fills."}}}},
        "output": {**PATH, "description": "New .vixl file for the recipe document."},
    },
    "plan": {"spec": PRODUCTION_SPEC},
    "run": {"spec": PRODUCTION_SPEC, "output": {**PATH, "description": "Folder for the outputs and production.json."}},
    "preview": {
        "output": {**PATH, "description": "A .png to write."},
        "quality": {"type": "string", "enum": ["draft", "final"], "default": "draft",
                    "description": "draft is a 640 px proxy; final is full size."},
        "time": {"type": ["number", "string"], "description": "Timeline frame: ms, '1.5s' or a marker name."},
    },
    "library-save": {
        "directory": {**PATH, "description": "Component library folder."},
        "name": {"type": "string", "maxLength": 80, "description": "Component name."},
        "description": {"type": "string", "maxLength": 10000, "description": "What the component is for."},
        "tags": {"type": "array", "items": STR, "description": "Search tags."},
    },
    "library-search": {"directory": {**PATH, "description": "Component library folder."},
                       "query": {"type": "string", "default": "", "description": "Words to match (empty lists all)."}},
    "library-open": {"directory": {**PATH, "description": "Component library folder."},
                     "id": {"type": "string", "description": "Component ID from library-search."},
                     "output": {**PATH, "description": "New .vixl file to write."}},
    "library-place": {"directory": {**PATH, "description": "Component library folder."},
                      "id": {"type": "string", "description": "Component ID from library-search."},
                      "name": {"type": "string", "description": "Name for the placed group layer."}},
    "submit": {"job": JOB, "start": COMMON["start"], "workers": COMMON["workers"]},
    "status": {"id": {"type": "string", "description": "Job ID from submit."}},
    "cancel": {"id": {"type": "string", "description": "Job ID from submit."}},
    "resume": {"id": {"type": "string", "description": "Job ID from submit."}},
    "film-plan": {"spec": FILM_SPEC},
    "film-export": {"spec": FILM_SPEC, "output": {**PATH, "description": "The .mp4, .webm, .gif, .webp or .zip."}},
    "lyric-video-plan": LYRIC, "lyric-video-build": LYRIC, "lyric-video-export": LYRIC,
    "drawing-report": {"target": {"type": "string", "description": "Drawing layer ID or name."}},
    "drawing-compare": {"target": {"type": "string", "description": "Drawing layer ID or name."},
                        "output": {**PATH, "description": "A new .png comparison image."}},
    "proof": {
        "items": {"type": "array", "minItems": 1, "maxItems": 200,
                  "items": {"type": ["string", "object"], "properties": {
                      "path": {**PATH, "description": "A .vixl document or an export (PNG, JPEG, WEBP, TIFF, GIF, "
                               "SVG, PDF, ICO)."},
                      "label": {"type": "string", "description": "Card title (default the file name)."},
                      "before": {"type": "string", "description": "Before/after: another file, or a revision of a "
                                 ".vixl item (previous, head~1, a checkpoint)."},
                      "note": {"type": "string", "description": "Text shown on the card."}}},
                  "description": "What to review: paths, or {path, label?, before?, note?}."},
        "output": {**PATH, "description": "The .html page to write (self-contained, works offline)."},
        "title": {"type": "string", "default": "Proof", "description": "Page heading."},
        "check": {"type": "boolean", "default": True, "description": "Run vixl_check on .vixl items and show the "
                  "findings."},
        "decisions": {"type": "boolean", "default": False, "description": "Add approve/reject and a note per item, "
                      "and a button that downloads them as <page>-decisions.json."},
        "max_size": {"type": "integer", "minimum": 128, "maximum": 2400, "default": 1200,
                     "description": "Longest side of each embedded image, px (shown small, enlarged on click)."},
        "overwrite": {"type": "boolean", "default": False, "description": "Replace an existing page."},
    },
    "logo-package": LOGO_PACKAGE_TYPES,
    "resource-list": {},
    "resource-get": {"name": {"type": "string", "description": "Resource name from resource-list."}},
    "resource-save": {"name": {"type": "string", "description": "Name for the saved resource."},
                      "value": {"type": ["array", "object", "string"],
                                "description": "Palette: array of colors; template/suite/workflow/shape: object; "
                                               "guidance: text."}},
    "shape-save": {"target": {"type": "string", "description": "Shape or path layer to save."},
                   "name": {"type": "string", "description": "Name for the saved shape."}},
    "suite-use": {"name": {"type": "string", "description": "Saved suite to copy into the document."},
                  "as": {"type": "string", "description": "Name to attach it under (default the same name)."}},
    "effect-run": {"name": {"type": "string", "description": "Saved effect workflow."},
                   "variables": {**COMMON["variables"], "description": "Values for the workflow's variables."},
                   "dry_run": {"type": "boolean", "description": "Report the operations without applying."}},
    "palette-check": {
        "palette": {"type": "string", "description": "Palette name (default the applied palette)."},
        "colors": {"type": "array", "items": STR, "minItems": 2, "description": "Allowed colors, instead of a palette."},
        "tolerance": {"type": "number", "minimum": 0, "maximum": 255, "default": 8,
                      "description": "Allowed per-channel distance from a palette color."},
        "max_fraction": {"type": "number", "minimum": 0, "maximum": 1, "default": 0.01,
                         "description": "Share of pixels allowed outside the palette."},
        "alpha_min": {"type": "integer", "minimum": 1, "maximum": 255, "default": 1,
                      "description": "Lowest alpha that counts as drawn."},
        "region": REGION,
    },
    "branch-fork": {"branch": {"type": "string", "description": "New branch name."},
                    "output": {**PATH, "description": "The branch's .vixl copy (must be new)."},
                    "author": {"type": "string", "default": "agent", "description": "Recorded author."}},
    "branch-status": {"branch": {"type": "string", "description": "Branch name."}},
    "branch-merge": {"branch": {"type": "string", "description": "Branch to merge into the open document."},
                     "resolutions": {"type": "object", "additionalProperties": {"enum": ["ours", "theirs"]},
                                     "description": "{conflict path: ours|theirs}."},
                     "dry_run": {"type": "boolean", "default": True,
                                 "description": "Report conflicts without merging (default true)."},
                     "expected_head": {"type": "string", "description": "Refuse if the document's head moved."}},
    "group-define": {"name": {"type": "string", "description": "Group name."},
                     "documents": {"type": "array", "items": PATH, "minItems": 1, "maxItems": 100,
                                   "description": ".vixl files in the group."},
                     "shared": {"type": "object", "description": "Parameters applied to every document.",
                                "properties": {"variables": {"type": "object", "additionalProperties": SCALAR,
                                                            "description": "Variables {name: value} set in each document."},
                                               "swatches": {"type": "object", "additionalProperties": COLOR,
                                                            "description": "Swatches {name: color} set in each document."}}}},
    "group-show": {"name": {"type": "string", "description": "Group name."}},
    "group-apply": {"name": {"type": "string", "description": "Group name."},
                    "operations": {**COMMON["operations"], "description": "Bulk operations applied to each member."},
                    "suites": {**COMMON["suites"], "description": "Suites every member must pass."},
                    "dry_run": {"type": "boolean", "default": True,
                                "description": "Check without saving (default true)."}},
    "group-recover": {"name": {"type": "string", "description": "Group whose interrupted edit to roll back."}},
    "plugin-install": {"manifest": MANIFEST, "replace": {"type": "boolean", "default": False,
                                                          "description": "Upgrade an installed pack."}},
    "plugin-remove": {"name": {"type": "string", "description": "Plugin pack to remove."}},
    "work": {"workers": {**COMMON["workers"], "description": "Workers to run in the foreground."}},
    "start": {"workers": {**COMMON["workers"], "description": "Workers to start in the background."}},
}


def properties(action, fields):
    """``{field: schema}`` for ``fields`` of ``action``: the action's own entry, else the shared one.
    A field with no entry is left out so a test can find it."""
    own = ACTION_FIELDS.get(action, {})
    return {field: deepcopy(own.get(field) or COMMON[field]) for field in sorted(fields)
            if field in own or field in COMMON}


# One line per action: what it does and what it returns.
SUMMARIES = {
    "guide-check": "Check explicit lighting, anatomy, perspective and illustration measurements against advisory rules.",
    "perspective-guides": "Plan vanishing-point guides and scale-by-depth object sizes.",
    "figure-plan": "Plan an editable figure from head units with a named part map.",
    "pattern-list": "List built-in and document-defined repeatable textures and patterns.",
    "pattern-check": "Measure edge discontinuity in a pattern tile before repeating it.",
    "check": "Run an attached or inline check suite against the document; returns passed/failed/needs_review per rule.",
    "act": "Apply operations to a candidate, run suites, and commit only when every suite passes.",
    "capture": "Turn the open document into a portable recipe document with typed inputs; writes a new .vixl.",
    "plan": "Expand a production spec into its full variant list without rendering.",
    "run": "Render every variant of a production spec into a folder, checking suites and resuming if rerun.",
    "preview": "Write a draft (640 px) or final PNG of the document, optionally at a timeline time.",
    "library-save": "Save the open document as a reusable component in a library folder.",
    "library-search": "List library components matching a query.",
    "library-open": "Write a library component out as a new editable .vixl document.",
    "library-place": "Place a library component into the open document as a group layer.",
    "submit": "Queue a durable background job (production, film, video, generate, lyric-video, form-fill).",
    "status": "Report a background job's state and progress.",
    "cancel": "Cooperatively cancel a background job.",
    "resume": "Resume an interrupted or failed background job.",
    "work": "Run queued jobs in the foreground until the queue is empty.",
    "start": "Start background workers for queued jobs.",
    "film-preview": "Preview a film frame, shot or interval with camera and transitions applied.",
    "video-sample": "Sample labelled video frames as a contact sheet or individual images.",
    "audio-analyze": "Measure loudness, peaks, clipping, silence and onset timing; optionally write a spectrogram.",
    "film-plan": "Validate a film spec and report its frames, duration and shots without rendering.",
    "film-export": "Render a shot sequence with captions and audio to a video or animation file.",
    "organic-catalog": "List organic generators, rules and presets with their parameters.",
    "lyric-video-plan": "Validate a lyric-video request and report timed lines, sections and warnings; writes nothing.",
    "lyric-video-build": "Write the keyframed lyric-video document from a song, LRC file and template.",
    "lyric-video-export": "Build the lyric-video document and render it to MP4 or WebM with the song.",
    "form-fill": "Fill the open form with one set of values or a CSV of rows into PDFs or images.",
    "links": "List the open document's linked documents with their revision, whether each is stale or missing, and its size.",
    "merge-impose": "Merge a template and CSV rows onto print sheets (grid, gutters, bleed, crop marks) as a vector PDF or sheet document.",
    "proof": "Write one self-contained offline HTML proof page: thumbnails, format/size/colour metadata, check "
             "findings, optional before/after and approve/reject decisions downloaded as JSON.",
    "logo-package": "Build a logo delivery folder: full-colour, mono and on-light/dark variants, optional mark/"
                    "horizontal/stacked lockups, strict SVG, RGB/CMYK PDF, PNG 1x-3x, icons and favicon, social "
                    "images, a usage sheet and an optional zip. No EPS.",
    "drawing-report": "Measure a hand-drawing layer: strokes, closures, straightness and cleanup suggestions.",
    "drawing-compare": "Write a before/after comparison PNG of a drawing layer.",
    "resource-list": "List built-in and user resources of one category.",
    "resource-get": "Read one named resource.",
    "resource-save": "Save a custom resource in the workspace library.",
    "shape-save": "Save a shape or path layer as a reusable shape resource.",
    "suite-use": "Copy a saved suite into the open document (one undo step).",
    "effect-run": "Run a saved effect workflow on the open document.",
    "palette-check": "Measure how much of the rendered document stays inside a palette.",
    "branch-list": "List branches forked from documents in this workspace.",
    "branch-fork": "Fork the open document into a named branch copy with a merge base.",
    "branch-status": "Compare a branch with the open document: what changed and any conflicts.",
    "branch-merge": "Merge a branch into the open document (dry run by default).",
    "group-list": "List project groups.",
    "group-define": "Define a group of documents with shared variables and swatches.",
    "group-show": "Show a project group's members and shared parameters.",
    "group-apply": "Apply shared parameters or operations to every group member with suite checks (dry run by default).",
    "group-recover": "Roll back an interrupted group edit from its journal.",
    "plugin-list": "List installed plugin packs.",
    "plugin-install": "Install a pack of namespaced palettes, templates, suites and other resources.",
    "plugin-remove": "Remove an installed plugin pack and its resources.",
}


def summary(action):
    return SUMMARIES.get(action, "")
