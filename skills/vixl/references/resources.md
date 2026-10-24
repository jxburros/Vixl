# Design resources and vector export

Vixl is a headless design engine for AI agents. People can drive the same CLI, Python, REST and MCP interfaces. No GUI or interactive approval is required for editing.

## Discover before designing

```bash
vixl commands --json
vixl shapes --json
vixl export --help
vixl validate --help
vixl palette list
vixl template list
vixl guidance list
```

These commands work without an open document. CLI edits return compact new values keyed by stable layer ID by default (in a terminal the CLI prints a one-line summary instead; piped output, `--json` and `VIXL_JSON=1` print the JSON). Use `--detail full` for before/after snapshots. Prefer atomic `apply` batches, Python, or a persistent MCP/REST session for repeated edits; services reuse the loaded document between requests.

## Palettes

The library includes 74 named palettes, from `midnight`, `ocean`, `forest`, `sunset`, and `pastel` to `mono`, `nordic`, and `accessible-blue`. Palette names describe starting points; measure actual foreground/background contrast for the combinations you choose.

```bash
vixl palette show ocean
vixl palette apply ocean
vixl shape capsule --name label --width 200 --height 80 --fill @ocean-2
vixl palette add brand brand-colors.json
vixl palette apply brand --prefix company
```

Custom palette files are JSON arrays of 2–256 color strings, for example `["#123456", "#abcdef"]`. Applying creates editable named swatches (`ocean-1` through `ocean-5`) and sets the contrast-checked role swatches (`@background`, `@surface`, `@ink`, `@muted`, `@accent`, `@accent-text`, `@on-accent`), keeping the document's light or dark mode. Layers that use role swatches, which includes every layout and built-in template, recolor at once; layers with literal colors keep them. Pass `"roles": false` (operation) to add only the numbered swatches. Refer to swatches with `@NAME`.

## Templates

Simple built-in templates: `social-square`, `story`, `thumbnail`, `poster`, `business-card`, and transparent `logo`.
`vixl template list` also shows eight modular templates ([studio](studio.md)), 26 use-case templates for social,
marketing, print, business and slides, and the editable six-second animated loops `video-tip`, `video-launch` and
`video-event` (title, subtitle and cta variables).

```bash
vixl template show social-square
vixl template new social-square -o campaign.vixl --set title='New launch' --set subtitle='Available today'
vixl template new logo -o logo.vixl --set accent='#e76f51'   # or omit accent to roll one
vixl template add my-card card-template.json
vixl template apply my-card --set title='Next variant'
```

`new` creates a correctly sized document and refuses to overwrite a file. `apply` inserts template operations into the current document without resizing its canvas; duplicate layer names fail atomically. Custom JSON:

```json
{
  "width": 640,
  "height": 360,
  "background": "transparent",
  "defaults": {"accent": "#2563eb"},
  "operations": [
    {"type": "shape", "shape": "triangle", "name": "mark", "width": 100, "height": 100, "fill": "${accent}"}
  ]
}
```

Templates fix structure, not content or look. Built-in templates have no sample copy: an unsupplied `title` or `subtitle` renders as a `[Headline]`/`[Subheading]` blank that `check` reports as an error. Unsupplied colors are rolled from a seeded palette with checked contrast (`template-apply` accepts `seed`, an integer or `"random"`; an omitted seed is fresh, or the document's own design seed when it has one, unless workspace variety is fixed). The result reports `rolled`, `seed` and `blanks`. Custom templates can do the same with `"blanks": {"title": "[Headline]"}` and `"roll": {"accent": "accent"}`, which map variables to placeholder text or to a color role (`background`, `surface`, `ink`, `muted`, `accent`, `accent-text`, `on-accent`).

Parameters can replace strings or whole typed values. Templates contain bounded canonical operations, not scripts or executable code. They cannot load files, import fonts, or recursively invoke templates. Import image/font assets explicitly first, or save an image as an `assets` resource (`{data_base64, media_type: png|jpeg|svg|webp, credit, license}`, at most 2 MiB, checked on save) and place it with `{"type": "asset-place", "resource": NAME, "x": …, "y": …, "width": …, "anchor": …}`, which templates may use. A field whose whole value starts with `=` is arithmetic after its variables are filled (`"x": "=${pad} + 76.34 * ${k}"`: numbers, `+ - * / // %`, parentheses, `min`, `max`, `round`, `abs`), reported under `normalized`; `==` writes a literal `=`. Template text may set `font` to a typography role or text stage (`heading`, `body`, `h2`, `label`, a brand role such as `hand`) or a registered font name, never a file, or set `stage`; text that names neither takes the heading role when it is the largest and body otherwise. `"proportional": true` on a template scales its positions, sizes and font sizes from its own `width`/`height` to the canvas by one factor (and stretches a full-template `solid` to the canvas), so it keeps its relative layout on any size. The user library is stored in `~/.config/vixl/resources.json`; set `VIXL_RESOURCES` to isolate it in automation.

## Overall and style-specific guidance

```bash
vixl guidance apply overall
vixl guidance apply minimal --style minimal
vixl guidance add brand brand-guide.txt
vixl guidance apply brand --style brand
vixl guidance import campaign campaign-guide.txt --style campaign
vixl guidance remove campaign --style campaign
```

`add` stores plain text in the reusable library; `import` attaches file text directly to the document. Guidance is retained in `design_guidance`, survives save/open and participates in undo, and is included in `ask` planning requests alongside the operation schema and current preview. It guides the external planner; deterministic drawing commands do not infer or enforce aesthetic rules. Imported guidance and image text are treated as data, and returned plans still pass Vixl's safety and operation validation.

## Fonts

```bash
vixl font import ./Brand-Regular.ttf --name brand
vixl font import https://example.com/fonts/Brand-Regular.otf --name brand
vixl font list
vixl text add 'Brand headline' --font brand --name title --size 64
```

The explicit import validates and embeds a TTF/OTF font (maximum 16 MiB) under a registered name. Later text creation needs no internet or original file. HTTPS imports accept direct font-file URLs (public hosts only; at most 5 redirects, each hop checked again). Google Fonts stylesheet URLs, WOFF/WOFF2, and HTML are not font files. Download an authorized TTF/OTF from the font's source and retain its license where needed. No font downloads happen implicitly during rendering. Existing `text add ... --font FILE` local imports remain supported.

## Shape shortcuts and editable paths

`vixl shapes` lists the full catalog. In addition to rectangles, ellipses, polygons, stars and lines, shortcuts include triangles, diamonds, arrows, chevrons, crosses, hearts, speech bubbles, shields, trapezoids, parallelograms, pentagons, hexagons, octagons and capsules.

```bash
vixl shape heart --name mark --width 180 --height 180 --fill '#e76f51'
vixl shape path --name curve --width 200 --height 100 --fill '#2563eb' --path 'M0 0 C0 100 200 100 200 0 L200 100 L0 100 Z'
```

Paths retain editable SVG geometry, including relative/repeated coordinates, arcs, smooth Bézier commands and multiple contours. Coordinates are in the layer's initial width/height; resizing scales that coordinate system. SVG files import editably only when every feature is supported; `svg_mode` `appearance`/`auto` keeps the rest as a raster layer (see [studio](studio.md)). Raster previews sample curves with bounded antialiasing; SVG retains exact Bézier commands.

Positions refer to the top-left of the transformed bounding box. Rotation expands that box, so align/constrain after rotating, or inspect `resolved_bounds` before positioning. For clean logo joins, use a single path or a deliberate pathfinder union/subtraction rather than overlapping rotated bars by guesswork.

## Transparent PNG, JPG and SVG

```bash
vixl new 512x512 --background transparent -o mark.vixl
vixl shape diamond --name mark --width 256 --height 256 --x 128 --y 128 --fill '#2563eb'
vixl export mark.png
vixl export mark.jpg --background white --quality 95
vixl export mark.svg
vixl export - --format SVG
```

PNG preserves canvas/layer alpha. `canvas background transparent` changes an existing canvas; remove or hide opaque background layers too. JPEG flattens transparency against the chosen `--background`. PNG, JPEG/JPG, WebP, TIFF, AVIF and SVG are available from Python/CLI; MCP picks the format from the filename; REST `POST /export` returns the selected bytes.

SVG exports solids, shapes, paths, gradients, pixel-grid cells, nested groups and pathfinder booleans of opaque, unstroked shapes as scalable geometry (one compound path, no masks). PNG/SVG share HarfBuzz shaping, bidi/script runs and outlined glyph layout: ligatures, combining marks, Unicode scripts covered by the font, multiline wrapping/fitting, path text and warp presets retain outlines. Common color effects, blur, drop shadows, glow, stroke, color overlays, vector clipping and supported full-opacity adjustments stay SVG-native. Unsupported appearances use isolated layer fallbacks where compositing permits; unsupported backdrop-dependent blends/adjustments may rasterize the document. SVG metadata identifies responsible layers/effects, and the file carries the editable document in `<metadata id="vixl-document">`, so importing it back restores the layers (docs/guides/output/exporting.md, SVG round trip). Add `--svg-policy strict` (Python/REST/MCP: `svg_policy="strict"`) to reject any embedded raster content before writing the file. Strict mode allows SVG filters; it does not promise paths-only output. Photographs, bitmap/color fonts, unsupported Unicode isolate controls, artistic textures/distortions, pixel masks/selections, LUTs, repeats, HSV hue and partial/translucent gradient overlays can need fallbacks. Raster profiles do not apply to SVG. See the artistic filter reference for exact settings and boundaries.

## Agent interfaces

Python can use `vixl.resources.catalog/get/register/create_template` and `vixl.fonts.import_font`. The structured operations `palette-apply`, `template-apply`, `guidance`, and `font-register` share the normal atomic edit/history engine. Example:

```json
{"operations": [
  {"type": "palette-apply", "name": "ocean"},
  {"type": "guidance", "name": "minimal", "style": "minimal"},
  {"type": "shape", "shape": "arrow", "name": "next", "width": 80, "height": 40, "fill": "@ocean-2"}
]}
```

Guidance texts are not separate tools. They live in one registry (`vixl/guidance.py`, plus user additions): list them with `vixl_reference('guidance')` or `vixl_reference()`, and read one with `vixl_reference("natural-motion")` or `vixl_reference('guidance', name="overall")` (CLI `vixl guidance list`, `vixl guide natural-motion`). Besides the design principles (overall, typography, color, layout, print …) it holds craft references: `natural-motion`, `looping-motion`, `character-rigging`, `cut-paper`, `audio-composition`, `anatomy-proportions`, `natural-color-light`, `illustration-perspective`, `drawn-textures`, `film-review`, `imperfection` (when to use `irregular` and `tear`), `multi-part-objects` (declared objects with kinds and named parts, overlapping parts, consistent outlines, the object tree, `isolate` part sheets, the `connected` check and reuse with `object-save`/`object-place`), `motifs` (the concrete things to draw for a setting) and `finishing` (the finishing pass after the checks pass; `vixl_reference('craft')` returns it too). The tool references `batches`, `checks`, `exports` and `testing` are guidance names as well. Object kinds are a resource kind of their own: `vixl_reference('objects')`, `vixl_reference('objects', name="dog")` (inherited parts, connections, proportions, chain) and `vixl_apply(workflow='resource-save', request={kind: "objects", name, value: {parent, …}})` for a workspace or user kind; CLI `vixl objects [QUERY]`, `vixl objects show dog`. The guide's kinds and `vixl_reference('capabilities')` topics name the entries that apply.

MCP reads resources with `vixl_reference` (topics `palettes`, `templates`, `guidance`, `objects`, `house-style`; `name` reads one), saves them with `vixl_apply(workflow='resource-save', request={kind, name, value})`, creates documents from templates with `vixl_document(action='create', template=NAME)` and imports fonts with an `import-font` step (`path` or an `https://` `url`, under the same fetch policy as image URLs: no credentials, no private hosts, at most 5 redirects); the `--tools ai` server adds `vixl_models_list`. Font file paths and template destinations stay inside the server workspace. Use a registered font by name in an operation (`{"type": "text", "font": "brand", ...}`); generic service operations continue to reject arbitrary filesystem font paths. REST adds GET/POST `/resources/{kind}/{name}`, GET `/resources/{kind}`, POST `/fonts?name=brand` with raw font bytes, and POST `/export` with JSON options such as `{"format":"SVG"}`. REST font uploads are limited to 16 MiB.

## Sizes, layouts and new guidance (0.13)

Named sizes (`vixl sizes`, `vixl_reference('sizes')`) and principled layouts (`vixl layout list`, `vixl_reference('layouts')`) complement palettes and templates: templates reproduce a fixed design, layouts generate a structured, seed-varied design for the actual canvas. Built-in guidance adds `typography`, `color`, `layout`, `accessibility`, `print`, `icon`, `motion`, `brush` and `image-rights` to `overall`, `minimal`, `editorial`, `playful`, `logo` and `pixel-art`; store one in the document with `{"type":"guidance","name":"print","style":"print"}` so planners and later edits follow it. See [design-system.md](design-system.md).


### Field-report corrections

Use one workspace brand.json with pinned fonts/pairing and all seven palette roles across independently rolled documents. A shared seed alone does not establish a shared brand. Workspace guidance resolves through the same resource catalog as palettes/templates.

Promo video templates: `video-promo-kinetic`, `video-promo-editorial`, `video-promo-neon`,
`video-promo-spotlight`, `video-promo-split`, `video-promo-stat`. Base names are square; suffix
`-story` (1080×1920) or `-wide` (1920×1080) selects a native layout. Six-second editable loops
accept `title`, `subtitle`, `cta`, and optional `background`, `foreground`, `accent`, `on_accent`
color variables; otherwise colors use seeded palette roles. Check bounds, contrast and a contact
sheet with supplied copy; use a visible poster near 2.5s (the loop begins on the background).
