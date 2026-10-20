# Choose and verify an export

[Documentation home](../../README.md) · [Color and print](../finishing/color-and-print.md)

Keep the `.vixl` master. Export a separate deliverable appropriate to where it will be
viewed, printed or edited. Inspect the exported file as well as the preview: other viewers
can substitute fonts, emphasize form fields or handle animation differently.

## Format guide

| Need | Output | Behavior and requirements |
| --- | --- | --- |
| Web image with transparency | PNG | Full-color pixels and alpha; broadly supported |
| Photograph or flattened artwork | JPEG | Lossy RGB or CMYK; transparent pixels composite onto a background |
| Smaller web artwork | WebP; AVIF where supported | Encoded image; confirm support in the consuming system |
| Print raster | TIFF or JPEG with CMYK | Supply the printer's ICC profile for controlled separations |
| Scalable supported geometry | SVG | Shapes/text/gradients and supported effects; appearance policy may embed raster fallbacks; carries the editable document ([round trip](#svg-round-trip)) |
| Print or selectable-text pages | PDF | Vector pages where supported; effects can fall back to raster; CMYK PDF stays vector (DeviceCMYK) |
| Editable presentation | PPTX | Real text, supported shapes, images, notes; unsupported appearances become pictures |
| Layered handoff to Photoshop and similar editors | PSD | One 8-bit RGBA pixel layer per layer with names, opacity, visibility, blend modes and layer groups, plus the flattened composite; text is pixels, not editable type |
| Interactive form | Fillable PDF | AcroForm widgets over artwork; RGB output; verify target PDF viewer |
| A font drawn in the document | TTF, OTF, WOFF (WOFF2 with `brotli`) | The document's font design as an installable font; see [making a font](../text/custom-fonts.md) |
| Icons | ICO or icon set | Multiple destination sizes; inspect the smallest icons |
| Motion | WebP, GIF, APNG, sheet or frame ZIP | Offline timeline export; GIF has limited colors |
| Encoded video / audio workflows | MP4 / WebM | ffmpeg required; external generated video also needs a configured gateway |
| Browser presentation of artwork | HTML | Standalone appearance export; title, alt and caption use the same resolved variables as the image; see [studio](../automation/studio.md#svg-import-and-html-export) |
| Logo hand-off | The `logo-package` workflow | Variants, lockups, SVG/PDF/PNG 1x–3x, icons, social images, usage sheet, zip; see [logo packages](../automation/production.md#logo-packages) |
| Legacy print (EPS) | Not produced | Vixl does not write EPS; give the printer the PDF (or the SVG) |

The authoritative options are `vixl export --help`, `vixl export-timeline --help` and
the [interface reference](../../reference/interfaces.md). Export format support can depend on installed codecs.

## Image output and alpha

```bash
vixl -p campaign.vixl export campaign.png
vixl -p campaign.vixl export campaign.jpg --background '#ffffff'
vixl -p chart.vixl export chart.svg --svg-policy strict
```

Strict SVG rejects layers or effects that require embedded raster content; use the
reported layers to simplify the design, or choose appearance policy if raster content is
acceptable. See [design tools](../shapes/design-tools.md) and [artistic filters](../images/artistic-filters.md)
for supported native effects and fallback behavior.

**Since 0.19.0:** CLI/MCP image exports default to `alpha=auto`, producing RGB
when every pixel is opaque and RGBA when needed. `--alpha keep` forces RGBA;
`--alpha flatten --background '#ffffff'` composites onto white. Applies to PNG, WebP,
TIFF and AVIF. Since 0.22.1 Python `Project.export` defaults to `alpha="auto"` too; pass `alpha="keep"` for RGBA.
These options are available in [0.19.0](../../../CHANGELOG.md#0190) and later.

```python
# Requires 0.19.0 or later for the alpha argument:
project.export("opaque.png", alpha="auto")
project.export("transparent.png", alpha="keep")
project.export("flattened.png", alpha="flatten", background="#ffffff")
```

## Print: physical size, bleed and color

Start with a print size so Vixl can retain dpi, trim, bleed and safe-area metadata.

```bash
vixl new letter --bleed -o flyer.vixl
# Add artwork that extends into the bleed, and keep critical content inside the safe area.
vixl -p flyer.vixl check --checks print color_vision
vixl -p flyer.vixl export flyer.pdf --cmyk --icc printer.icc
```

`printer.icc` is the profile supplied for your actual press/paper. Without an ICC profile,
CMYK uses a device-naive GCR approximation with optional ink limiting. Documents edit in
RGBA8 sRGB; CMYK is an export setting, not an editing space. Spot colors and RAW development
are outside the implementation. A proof image helps assess separations but does not replace
a printer proof. See [color and print](../finishing/color-and-print.md) for ink limits and simulations.

A document made from a print size exports a PDF page of exactly trim plus bleed on every side, with a
TrimBox and BleedBox, including when the bleed is a fraction of a pixel (raster PDFs too). Verify the
PDF's page dimensions and boxes when print precision matters, and record the source revision alongside
your output.

## Pages, forms and motion

```bash
vixl -p slides.vixl export slides.pdf
vixl -p slides.vixl export slides.pptx
vixl -p slides.vixl export slide.png --pages all
vixl -p registration.vixl export registration.pdf --fillable
vixl -p motion.vixl export-timeline --out motion.webp --fps 12
```

PowerPoint references font families, so install those fonts on the receiving system.
Multi-page vector PDF embeds supported TrueType subsets with Unicode mappings.
Export reports can list `raster_fallbacks` and `fonts`; inspect those before promising
fully editable content. [Slides](slides.md) documents these details.

For fillable forms, test interactive entry and tab order. Filled copies can be flattened
or remain editable; values are validated and do not mutate the blank master.
[Forms](forms.md) describes entry-font limitations and validation.

For motion, check time coverage and final playback. `render --time 1s` produces one pose;
`timeline-sheet` produces an overview; `export-timeline` produces the sequence. Pixel-frame
animations use `export-animation` instead. See [motion tutorial](../../tutorials/motion.md).

## Layered PSD for designer handoff

```bash
vixl -p poster.vixl export poster.psd
```

`vixl_export(path="poster.psd")`, `Project.export("poster.psd")` and the REST export
(`format: "PSD"`) write an 8-bit RGB Photoshop file (version 1 PSD, PackBits-compressed
channels) that opens in Photoshop, Photopea, GIMP, Affinity and Krita:

- Each layer is one pixel layer, rendered in canvas space with its effects, layer styles,
  mask and clipping, and cropped to what it draws. The layer keeps its name, opacity and
  visibility (hidden layers are written hidden); blend modes map to Photoshop's (`normal`,
  `multiply`, `screen`, `overlay`, `darken`, `lighten`, `difference`, `add` as Linear Dodge,
  `subtract`). A non-transparent canvas background becomes a bottom `Background` layer.
- Groups become layer groups with their children inside. A group Vixl transforms or filters
  as a whole (rotation, flip, skew, a resized box, effects, styles, clip, mask, repeat,
  distortion) cannot be expressed as a Photoshop group and is written as one pixel layer.
- The file also carries the flattened composite, identical to the PNG render, which viewers
  without layer support (and Pillow) show.
- Not preserved: text is rasterized, not editable type (the result lists the layers under
  `text_as_pixels` and in `warnings`); shapes and paths are pixels, not vector layers;
  adjustment layers are applied in the composite only (`adjustments_in_composite_only`);
  group-turned or filtered groups are listed under `flattened_groups`. Kinetic text and other
  timeline motion export the resting document (or one frame with `time`).
- One page of a multi-page document (`page`); CMYK, proofing, profiles, artboards and comps do
  not apply. Each side is at most 30 000 px. Exports refuse to overwrite unless `overwrite` is set.

## Handoff checklist

- Keep the master, final exports and content/source assets required for further editing.
- Confirm dimensions, transparency/background, physical print size and expected page/frame count.
- Review text, contrast and smallest output size; run relevant checks and examine their findings.
- Inspect exported files in their destination viewer, including fonts, widgets and playback.
- Record version, source revision when applicable, export settings and font/source licenses.

For repeated output families, use [production workflows](../automation/production.md) to retain manifests,
checks, render decisions and resume information. To send a set of exports for sign-off, write a
[proof page](../automation/production.md#proof-pages): one offline HTML file with thumbnails, metadata, findings and
approve/reject decisions; `vixl diff A B` shows what changed between two exports.

## Python export consistency

`Project.export`, `Project.export_animation`, `export_timeline` and MCP `vixl_export`
protect existing files by default (`overwrite=False`). Pass `overwrite=True`
for repeatable builds that intentionally replace outputs; CLI render/export and
saved-frame animation commands accept `--overwrite`.

Raster exports accept `page="all"` or `pages=["cover", "results"]` to write one
contact sheet. `width` is the width of each page tile (default 480), `columns`
controls the grid, and `labels=False` hides page labels. PDF/PPTX `pages` still
selects actual document pages.

```python
p.export("overview.png", page="all", width=320, columns=3, overwrite=True)
```

## Proof and export diagnostics

A proof continues past a document that cannot render, recording its error alongside successful items. The report's `failed` list must be empty before approval. Preview images are embedded once and reused for the zoom view, reducing HTML size. Contact sheets downsample full page renders, so small previews preserve the page's actual wrapping.

Python `Project.export(..., pages="all")` selects all visible pages; for a raster export it writes the contact sheet. CMYK PDF export without an ICC profile reports that conversion is unprofiled. Supply the intended printer profile for managed colour output.

**One object or layer alone.** `isolate=["guitar"]` (CLI `--isolate guitar`) exports only those layers, object
paths (`person/guitar`) or `object:KIND`, cropped to their ink plus `padding` pixels on a transparent canvas, in
every format; a `.vixl` path writes a portable object document for `object-place source=`. SVG, PowerPoint and
PSD keep declared [objects](../shapes/objects.md) as named groups, and every format carries alt text and the document
language ([accessibility](accessibility.md)).

SVG export writes `multiply`, `screen`, `overlay`, `darken`, `lighten` and `difference` layers as native `mix-blend-mode` groups inside an isolated root, keeping every shape and text vector. `add`, `subtract` and other backdrop-dependent operations still rasterize the document and report the fallback; strict mode rejects them.

**Strokes land in the same place in every format.** A closed shape (rectangle, rounded rectangle, capsule, ellipse,
polygon, star, shortcut or catalog shape) strokes `inside` by default: the stroke's outer edge is the outline, so a
10 px stroke on a rectangle covers the 10 px just inside its box edge and the fill runs under it. Paths, arcs, lines and
open shapes stroke `center`. An explicit `stroke_align` (`inside`, `center`, `outside`) means the same with or without
dashes, width profiles or markers, in PNG, SVG, PDF and PPTX; a rounded corner keeps its `radius` on the outside. A
`rectangle` created with a `radius` is stored as a `rounded-rectangle` (reported under `normalized`), so its corners are round in
every output. See [vector shapes and strokes](../shapes/vector-paths.md#strokes) and [render parity](../../project/render-parity.md).

## SVG round trip

An SVG Vixl exports carries the document it shows, so importing it back gives the same editable document: the same
layers with their IDs and names, live text in its fonts, groups, effects, layer styles, masks and every other field.
Use SVG as an interchange file without losing the master.

```bash
vixl new 1080x1350 -o poster.vixl
vixl -p poster.vixl text add 'Spring fair' --name title --size 96
vixl -p poster.vixl export poster.svg
vixl new 1080x1350 -o copy.vixl
vixl -p copy.vixl import poster.svg
```

- The SVG holds `<metadata id="vixl-document">` with the page's document JSON (the [file format](../../reference/file-format.md)'s
  `state`, a multi-page document's exported page as a single page) and a SHA-256 digest of the rest of the SVG.
  Every layer's group also carries `data-vixl-id` (its layer ID) and `data-layer` (its name). Browsers and other
  editors ignore the metadata; the SVG draws exactly as before.
- Each file the page uses is stored once. An image the page shows as it is (its own size, no effects) is drawn by
  an `<image>` holding the file's own bytes, and the metadata points at that element. Other files (images of hidden
  layers, images drawn resized or with effects, masks, brushes, patterns) are stored in the metadata as base64.
- Fonts are never stored in the SVG, only named: family, weight, style and source (a bundled face, a Google Fonts
  family, or a file you imported). A blank document is a few KB, and a published SVG does not redistribute font
  files. On import each font is found again: the same file already in the document, the bundled face, a font the
  document registers under the same name (or with the same family and style), then the Google Fonts style from the
  font cache, downloading it when the cache does not have it (`install_fonts=False` in Python keeps the import
  offline). The result's `fonts` says how each registered font was found. A font none of these supplies (an
  imported file you do not have registered) is drawn with the bundled DejaVu Sans and listed in `warnings`; the
  import does not fail, and importing and registering the font under the same name restores it. Everything except
  the font files round-trips exactly.
- Importing into a document without layers takes the embedded canvas and resources too, so the result equals the
  exported page. Importing into a document with layers places the layers as one group at their original position
  (names the document already uses are prefixed with the group's name).
- When the SVG was edited after export (the digest no longer matches), when its stored files exceeded 32 MiB and
  were left out, or when the embedded document does not pass the checks a `.vixl` file must pass, the import reads
  the SVG's visible elements instead and says why in `warnings`.
- `svg_document=False` (Python, REST) leaves the metadata out, for example for a web asset. HTML exports and
  presentation slides never carry it.

## Importing SVG and PDF

`vixl import FILE.svg` / `FILE.pdf` (MCP `import-document` step, REST `POST /import`, Python
`vixl.imports.import_document`) adds the file's content to the current document as one revision. `svg_mode` chooses
how, for SVG and PDF alike:

| `svg_mode` | SVG | PDF |
| --- | --- | --- |
| `editable` (default) | Vixl's own SVG: the embedded document. Other SVG: editable layers; an unsupported element fails the import. | The page as editable layers; objects Vixl cannot represent become image layers. |
| `auto` | As `editable`, but an unsupported element becomes an image layer of just that element (listed in `rasterized`); an unreadable stylesheet imports the whole SVG as one image. | As `editable`. |
| `appearance` | The whole SVG as one image layer, its source kept in the archive. | The page as one image at `dpi` (default 144). |

**Other SVG.** `rect`, `circle`, `ellipse`, `line`, `polyline`, `polygon` and `path` become path shape layers with
their fill (nonzero or even-odd), stroke, stroke width, caps, joins, dashes and opacity; transforms are applied to
the geometry. `<text>` and `<tspan>` become live text layers (size, colour, `text-anchor`, rotation, letter spacing;
lines that share an `x` become one multi-line layer). A font family the document has registered (by registered name
or by the font's own family name) is used, else the default face with a warning; a text with mixed span styles takes
its first style. `<g>` elements with an `id`, `data-layer` or Inkscape label, or with opacity, become groups (a group
of one layer passes its name and opacity to it). Linear and radial gradients become gradient layers on rectangles
(and radial glows on circles) and gradient overlays on other shapes. Embedded PNG, JPEG and WebP `<image>` data
becomes an image layer. `<use>` and `<symbol>` are expanded, and `<style>` rules with type, class and ID selectors
apply. Filters, masks, clip paths, patterns, markers, skewed text and external references are not editable: `auto`
draws each such element as an image layer. External resources are never fetched.

Untrusted SVG is charged while it is read, so a small file cannot run for minutes. An import that would walk more
than four times the batch limit of elements (40,000 by default, `<use>` copies counted where they expand) or make
more than one batch of layers fails at once with `resource_limit`, before the work is done. `auto` draws at most 64
elements as image layers; an SVG with more fails with `resource_limit`: import it with `svg_mode: "appearance"`
instead, which draws the whole file as one image.

**PDF.** A page's text objects become live text layers with their text, size, colour, position and rotation;
consecutive lines of one style that share a left edge, centre or right edge become one multi-line layer, and a text
outline pass becomes the layer's `stroke_color` and `stroke_width`. Fonts are matched as described under
[PDF fonts](#pdf-fonts) below. Path objects become path shape layers (fill and even-odd
fill, stroke, width, caps, joins, dashes); a stroke painted right after a fill of the same path joins that layer, and
so does one that runs half its width inside the fill's outline (how Vixl writes an inside stroke), which becomes
`stroke_align: "inside"`.
Image objects become image layers at their position, size and rotation. Shadings, clipped objects, patterns,
mirrored text and other content Vixl cannot represent are drawn, run by run in stacking order, as image layers
(listed in `rasterized`). Into a document without layers the page size becomes the canvas and a full-page backdrop
its background (white otherwise). A PDF Vixl exported maps back to the pixels it was made at (it records `VixlDPI`);
other PDFs map one point to one pixel, and `dpi` applies to `appearance` imports only. Rotated pages, form fields,
annotations, blend modes and transparency groups are not read as such: rotated pages import as one image, and
the others as what pdfium reports for each object.

### SVG fonts

An SVG that is not Vixl's own names fonts by family. `font_map` (CLI `--font-map SRC=NAME`, REST `font_map=SRC=NAME`) maps those families to registered fonts or roles, first, exactly as for PDF, and fails with `missing_font` for an unregistered target. Vixl's own SVG names its fonts by identity and ignores `font_map`; `install_fonts` (default true) applies to it and never downloads with `VIXL_OFFLINE=1`.

### PDF fonts

A PDF embeds only the glyphs it uses (a subset), so its fonts cannot be registered as they are. Each PDF font is
found again, in this order:

1. `font_map`: `{"Literata": "literata-400", "Literata Bold": "literata-700"}` maps a PDF family (with `Bold`,
   `Italic` or `Bold Italic` for a style) to a font registered in the document or a role such as `heading`. CLI:
   `--font-map SRC=NAME`, repeatable. A target that is not registered fails with `missing_font`.
2. A font the document registers under that family name in the same style.
3. For a PDF Vixl exported: its document information lists each embedded face (`VixlFonts`: BaseFont to family,
   weight, italic and the SHA-256 of the whole font file). The same file already in the document is used, then the
   style from the font cache (`VIXL_FONT_CACHE`), which is registered as `family-weight[-italic]`. For other PDFs the
   family and style the PDF names are looked up in the font cache.
4. With `install_fonts: true` (CLI `--install-fonts`), a Google Fonts download. Nothing is downloaded by default,
   and with `VIXL_OFFLINE=1` the download is refused and reported as a warning.
5. A registration of the family in another style, or the bundled DejaVu Sans when the PDF names it.

Anything else uses the document's default face, with a warning. The result's `fonts` lists one
`{source, used, how}` entry per PDF font, where `how` is `mapped`, `registered`, `cache`, `installed` or `default`;
only `default` entries warn. Registered fonts and the imported layers are one revision.

<!-- docs-test: skip needs a PDF file and registered Literata fonts -->
```bash
vixl import report.pdf --font-map "Literata=literata-400" --font-map "Literata Bold=literata-700"
```

Mapping changes the face, not the layout: line breaks and widths follow the mapped font. When the exact appearance
matters, import with `svg_mode: "appearance"` (one image), or keep the `.vixl` or SVG master, which carry the
document itself.
