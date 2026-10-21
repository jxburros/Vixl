# Import from Figma

[Documentation home](../../README.md) · [Providers](../../reference/providers.md) · [Interfaces](../../reference/interfaces.md) · [Use cases](../../use-cases.md)

Vixl reads a Figma file with **your** personal access token and turns a page or a single frame into an editable
Vixl document: layers stay layers, text stays live text, rounded rectangles keep their radius, and gradients,
shadows, groups and auto layout map to their Vixl counterparts. Whatever cannot map is listed in a report instead of
disappearing silently. Exporting a Vixl document back to Figma is tracked in
[issue 662](https://github.com/jxburros/Vixl/issues/662).

Vixl contains no Figma credentials. The token is read from the environment, used for the import, and is never
written to a document, a project folder, a job record or the provider configuration.

## Set up a token

1. In Figma open **Settings → Security → Personal access tokens** and choose **Generate new token**.
2. Give it a name and the **`file_content:read`** scope. Nothing else is needed; the import only reads.
3. Copy the token (Figma shows it once) and put it in the environment that runs Vixl:

```bash
export FIGMA_TOKEN=figd_...          # or VIXL_FIGMA_TOKEN
```

`FIGMA_TOKEN` wins when both are set. The token's account must be able to open the file in Figma.

## Import

A file URL, a frame URL (`node-id=`) or a bare file key all work. `https://www.figma.com/design/KEY/Name`
and the older `/file/KEY/Name` are the same file; `1-2` in a URL is node `1:2`; a branch URL imports that branch.

<!-- docs-test: skip needs a Figma token and network access -->
```bash
vixl new 800x600 -o poster.vixl
vixl -p poster.vixl import "https://www.figma.com/design/KEY/Poster?node-id=1-2"
vixl -p poster.vixl import KEY --format figma --node 1:2
vixl -p poster.vixl import KEY --format figma --rasterize-unsupported
vixl -p poster.vixl import exported-file.json --format figma     # JSON saved from GET /v1/files/KEY, no token needed
```

Python and REST use the same entry as the SVG and PDF imports:

```python
from vixl import Project
from vixl.imports import import_document

project = Project(100, 100)
result = import_document(project, b"https://www.figma.com/design/KEY/Poster?node-id=1-2", "figma")
print(result["figma"]["root"], len(result["report"]))
```

`POST /import?format=figma&node_id=1-2&rasterize_unsupported=false` takes the URL or key as the request body (`page`
is a page name or number); the server reads the token from its own environment. In MCP, an `import-document` step in
`vixl_apply` takes `format="figma"` with `source` set to the URL or key (and `node_id`, `page`, `rasterize_unsupported`).

Options (Python keyword arguments, `--node`/`--rasterize-unsupported` and the query parameters above):

| Option | Meaning |
| --- | --- |
| `node_id` | Import this node (`1:2`) instead of a page. A frame, group, component, instance or section becomes the document; any other node gets a canvas the size of the node. |
| `page` | The Figma page to import, by 1-based number or name (default: the first page). `--page` on the command line takes the number. |
| `rasterize_unsupported` | For nodes with no editable equivalent (sticky notes, tables, connectors ...) fetch a PNG render and place it as an image layer. Default: skip and report. |
| `install_fonts` | Python only, default true: install missing families that Google Fonts offers through the font cache. Others are substituted. |

## What you get

One frame (selected with a node id, or the only frame on the page) becomes the whole document, sized to the frame.
A page with several frames becomes one canvas that holds them all at their Figma positions, each frame as a group with
an [artboard](../shapes/design-tools.md) of its own size (`render --artboard NAME` exports one). An empty document is resized to the imported
frame or page; a project that already has layers keeps its canvas and receives the import as additional layers. When
the document is empty and the frame's only fill is one opaque solid colour with square corners and no stroke, that
colour becomes the canvas background instead of a `<name> background` layer.

The result is the usual compact apply result plus:

- `figma`: file name, version, the imported root or artboards, the page list and counts (`layers`, `group`, `stack`).
- `report`: one `{node_id, name, type, what_was_lost}` entry per lossy decision.
- `warnings`: a one-line summary when the report is not empty.

Figma layer names are kept. Vixl layer names are unique, so repeated names get a numeric suffix (`Tile`, `Tile 2`).

## Mapping

| Figma | Vixl |
| --- | --- |
| Page (CANVAS) | the imported page; the others are listed in `figma.pages` |
| Top-level frame(s) | the document (one frame) or groups with artboards (several) |
| FRAME, GROUP, COMPONENT, COMPONENT_SET, INSTANCE, SECTION | group with the same name and child order; a frame's own fill and stroke become a `<name> background` layer under its children |
| Auto-layout frame | `stack` (direction, gap, padding, alignment) when positions reproduce; otherwise a plain group at the Figma positions (reported) |
| RECTANGLE | rectangle or rounded rectangle (`cornerRadius`); `rectangleCornerRadii` that differ draw a path |
| ELLIPSE | ellipse (arcs and rings use their geometry) |
| LINE | stroked path |
| VECTOR, BOOLEAN_OPERATION, STAR, POLYGON | path layer from `fillGeometry` (SVG path data scaled with `path_view`); stroke-only vectors keep an editable stroke |
| TEXT | live text: characters, font, weight, size, tracking, line height, alignment, case, colour, fixed box width; style runs become `text-style` spans (bold, italic, size, colour, tracking, underline, strike, font) |
| Solid fill | fill colour, paint opacity folded into its alpha |
| Linear and radial gradient | the shape's `fill_gradient`, built from the gradient handles (exact for linear; radial when circular), transparent stops included |
| Image fill | image frame clipped to the node's outline; `FILL` is cover, `FIT` is contain |
| Several fills | one layer per fill inside a group named after the node |
| Stroke | colour, weight, inside/centre/outside alignment, caps, joins, dashes |
| Opacity, blend mode | layer opacity; `NORMAL`, `MULTIPLY`, `SCREEN`, `OVERLAY`, `DARKEN`, `LIGHTEN`, `DIFFERENCE` and `LINEAR_DODGE` (`add`) |
| Drop shadow | `drop-shadow` layer style (Figma blur radius is halved: Vixl's blur is a Gaussian sigma) |
| Layer blur | `blur` effect (radius halved) |
| `visible: false` | hidden layer |
| Rotation, mirroring | rotation about the layer's centre and a horizontal flip, from `relativeTransform` |

Positions are taken from `relativeTransform`, composed down the tree and expressed relative to the imported root, so
nested and rotated nodes land where Figma draws them.

## Fonts

Text asks for the family, weight and italic that Figma used. Vixl looks for a registered `family-weight` font, then
(with `install_fonts`) for the nearest weight of a Google Fonts family, then falls back to the bundled proofing font
with bold and italic synthesised, and says so in the report. Register your own files first with
`vixl font import FILE --name inter-700` (the name is the lower-case family, a hyphen and the weight; add `-italic`)
and the import uses them. A substitute font is wider or narrower than the original, so fixed text boxes are left to
grow in height and centred or right-aligned text keeps its anchor.

## Known losses

Everything below is reported; the layer is still imported unless the entry says it was skipped.

- **Masks**: a mask layer is skipped and the layers it clipped are drawn unmasked.
- **Clipping**: frames that clip their content do not clip in Vixl; only the root frame is clipped by the canvas.
- **Inner shadows, background blur, noise and texture effects, shadow spread, extra drop shadows**: dropped (a Vixl layer carries one drop shadow).
- **Blend modes** without a Vixl counterpart (colour dodge/burn, soft/hard light, exclusion, hue, saturation, colour, luminosity): drawn as normal.
- **Gradients**: angular and diamond become a flat colour; elliptical or rotated radial gradients become circular; gradient strokes use their first stop.
- **Image fills**: tile, stretch and crop scale modes become cover; image filters and rotation are ignored; an image whose bytes could not be downloaded is skipped.
- **Fills on text**: images and gradients become a flat colour; lists, paragraph spacing and indent, hyperlinks, per-range case, small caps, justified alignment and vertical alignment in fixed boxes are not applied; font sizes are whole pixels.
- **Strokes**: per-side weights use the largest; only the top stroke paint is kept.
- **Even-odd fill rule**: Vixl fills with the non-zero rule, so overlapping contours can fill where Figma cut a hole.
- **Transforms**: skew is dropped; a rotated or mirrored root frame is straightened.
- **Auto layout**: wrapping layouts, space-between, baseline alignment, absolutely positioned children and rotated children stay plain groups at their Figma positions. A stack reflows when its content changes, which Figma's fixed export does not; sizes are the Figma sizes.
- **Root frame**: its opacity, effects and blend mode cannot apply to the document.
- **Unsupported node types** (sticky notes, connectors, tables, widgets, embeds, media): skipped, or imported as a PNG render with `rasterize_unsupported`.
- Component properties, variants logic, prototyping links, variables and styles are not imported; instances arrive as the groups Figma resolved.

## Errors

Errors are JSON with `error`, `message` and `suggestions`, like the rest of Vixl.

| `error` | Cause |
| --- | --- |
| `figma_token_missing` | neither `FIGMA_TOKEN` nor `VIXL_FIGMA_TOKEN` is set |
| `figma_forbidden` | 401/403: the token is invalid, expired, lacks `file_content:read`, or cannot open the file |
| `figma_not_found` | 404: wrong file key or node id |
| `figma_rate_limited` | 429: `retry_after_s` holds Figma's `Retry-After`; import one frame instead of the whole file |
| `figma_error`, `figma_bad_request`, `figma_unreachable` | other API failures and network errors |
| `invalid_figma_source` | the argument is not a Figma URL or file key |
| `invalid_figma_document` | the JSON is not a Figma file, or the page or node is empty |
| `figma_empty` | the selected frame or page held nothing Vixl could import; the report names the skipped nodes |
| `resource_limit` | the import needs more operations (default 10,000) or image fills (200) than allowed: import one frame |

A failed import changes nothing: the whole import is one atomic batch, so `vixl undo` removes it in a single step.

## Network use

The import calls `GET /v1/files/KEY?geometry=paths` (with `ids=` for a node), `GET /v1/files/KEY/images` for image
fill URLs, and, with `rasterize_unsupported`, `GET /v1/images/KEY`. Image bytes download from the URLs Figma returns
under Vixl's [bounded fetch policy](../../reference/architecture.md) (HTTPS only, public addresses only, size-capped). With
`install_fonts`, missing Google Fonts families come from the font cache or Google Fonts as for
[`font install`](../text/typography.md).
