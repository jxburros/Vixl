# Choose and verify an export

[Documentation home](README.md) · [Color and print](color-and-print.md)

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
| Scalable supported geometry | SVG | Shapes/text/gradients and supported effects; appearance policy may embed raster fallbacks |
| Print or selectable-text pages | PDF | Vector pages where supported; effects can fall back to raster; CMYK PDF is raster |
| Editable presentation | PPTX | Real text, supported shapes, images, notes; unsupported appearances become pictures |
| Interactive form | Fillable PDF | AcroForm widgets over artwork; RGB output; verify target PDF viewer |
| Icons | ICO or icon set | Multiple destination sizes; inspect the smallest icons |
| Motion | WebP, GIF, APNG, sheet or frame ZIP | Offline timeline export; GIF has limited colors |
| Encoded video / audio workflows | MP4 / WebM | ffmpeg required; external generated video also needs a configured gateway |
| Browser presentation of artwork | HTML | Standalone appearance export; see [studio](studio.md#svg-import-and-html-export) |
| Logo hand-off | The `logo-package` workflow | Variants, lockups, SVG/PDF/PNG 1x–3x, icons, social images, usage sheet, zip; see [logo packages](production.md#logo-packages) |
| Legacy print (EPS) | Not produced | Vixl does not write EPS; give the printer the PDF (or the SVG) |

The authoritative options are `vixl export --help`, `vixl export-timeline --help` and
the [interface reference](interfaces.md). Export format support can depend on installed codecs.

## Image output and alpha

```bash
vixl -p campaign.vixl export campaign.png
vixl -p campaign.vixl export campaign.jpg --background '#ffffff'
vixl -p chart.vixl export chart.svg --svg-policy strict
```

Strict SVG rejects layers or effects that require embedded raster content; use the
reported layers to simplify the design, or choose appearance policy if raster content is
acceptable. See [design tools](design-tools.md) and [artistic filters](artistic-filters.md)
for supported native effects and fallback behavior.

**Since 0.19.0:** CLI/MCP image exports default to `alpha=auto`, producing RGB
when every pixel is opaque and RGBA when needed. `--alpha keep` forces RGBA;
`--alpha flatten --background '#ffffff'` composites onto white. Applies to PNG, WebP,
TIFF and AVIF. Python `Project.export` retains `alpha="keep"` by default for compatibility.
These options are available in [0.19.0](../CHANGELOG.md#0190) and later.

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
a printer proof. See [color and print](color-and-print.md) for ink limits and simulations.

Latest source fixes raster PDF physical dimensions and TrimBox/BleedBox handling, including
fractional bleed pixels. Verify the PDF's page dimensions and boxes when print precision
matters, and record the source revision alongside your output.

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
animations use `export-animation` instead. See [motion tutorial](tutorials/motion.md).

## Handoff checklist

- Keep the master, final exports and content/source assets required for further editing.
- Confirm dimensions, transparency/background, physical print size and expected page/frame count.
- Review text, contrast and smallest output size; run relevant checks and examine their findings.
- Inspect exported files in their destination viewer, including fonts, widgets and playback.
- Record version, source revision when applicable, export settings and font/source licenses.

For repeated output families, use [production workflows](production.md) to retain manifests,
checks, render decisions and resume information. To send a set of exports for sign-off, write a
[proof page](production.md#proof-pages): one offline HTML file with thumbnails, metadata, findings and
approve/reject decisions; `vixl diff A B` shows what changed between two exports.
# Python export consistency

`Project.export`, `Project.export_animation`, `export_timeline` and the MCP export
tools protect existing files by default (`overwrite=False`). Pass `overwrite=True`
for repeatable builds that intentionally replace outputs; CLI render/export and
saved-frame animation commands accept `--overwrite`.

Raster exports accept `page="all"` or `pages=["cover", "results"]` to write one
contact sheet. `width` is the width of each page tile (default 480), `columns`
controls the grid, and `labels=False` hides page labels. PDF/PPTX `pages` still
selects actual document pages.

```python
p.export("overview.png", page="all", width=320, columns=3, overwrite=True)
```
