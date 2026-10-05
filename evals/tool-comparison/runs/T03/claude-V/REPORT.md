# T03 Print poster — lane V (Vixl MCP)

**Timing:** started 22:16:26 UTC, finished 22:25:53 UTC (about 9.5 minutes, 2026-10-05). About 53 tool calls, including roughly 40 Vixl MCP calls.

## Files

| File | What it is | How it was made |
| --- | --- | --- |
| `poster.vixl` | Editable source: 79 layers (gradients, shapes, live text, a rich-text bulleted list, a reflections group with effects) and a `trim` artboard | `vixl_document_create(size="tabloid", bleed=0.125)`, `vixl_font_pair("marcellus-lato")`, then `vixl_operations_apply` batches and `vixl_text_add` (with the `font` set to the embedded Marcellus or Lato) |
| `poster-print.pdf` | 1 page, MediaBox 810 × 1242 pt (11.25 × 17.25 in). It holds one CMYK image (DeviceCMYK, JPEG q95), 3375 × 5175 px at 300 ppi | `vixl_export_file(color_space="cmyk", ink_limit=300, dpi=300, quality=95)`. This uses Vixl's GCR conversion; no ICC profile was used |
| `poster-preview.png` | 1650 × 2550 px with 150 dpi metadata, showing the trimmed area only | `vixl_export_file(artboard="trim", scale=0.5, dpi=150)`. The `trim` artboard is x=38, y=38, 3300 × 5100 px on the bleed canvas |

## Design
- **Copy:** all ten lines are used exactly as written, with the same case and punctuation. The en dash, middle dots and "é" are kept.
- **Kicker and title:** the kicker "Port Ellery Quay" is gold, letterspaced Marcellus at 120 px. The title "Harbor Lights" is Marcellus at 480 px, about 115 pt.
- **Subtitle, date and list:** the subtitle and date are Lato. The four highlights are a real bulleted list: a rich-text layer with `list: bullet`.
- **Imagery:**
  - Two strings of paper lanterns hang in a curve across the sky. The front string has 9 lanterns with caps, bases, glowing cores and outer glows. The back string has 10 smaller lanterns.
  - Below them is a dark quay silhouette with two masts and a soft warm glow on the horizon.
  - Under each front lantern is a matching reflection in the dark water: a tall ellipse, grouped with the others at 50% opacity, with a ripple and blur.
  - The palette is deep navy and indigo with amber, coral and cream lanterns.
- **Bleed:** the sky and water gradients and the quay silhouettes run to every canvas edge, so they fill the 0.125 in bleed.
- **Text margins:** the smallest text inset from the trim is about 202 px (0.67 in), on the title. The brief asks for at least 0.25 in. `vixl_check` with a safe area of 113 px (38 px bleed plus 75 px) reported no text outside it, no overlap and no contrast problems.

## Deviations and uncertainties
- **Bleed rounding.** Vixl's tabloid size with 0.125 in bleed at 300 dpi rounded the bleed to 38 px, giving a 3376 × 5176 canvas. That made the PDF 810.24 × 1242.24 pt. I cropped the canvas to 3375 × 5175 with a `canvas` operation, which removed 1 px from the right and bottom bleed edges. The page is now exactly 810 × 1242 pt. The bleed is 38 px on the left and top and 37 px on the right and bottom. The printer trims at 0.125 in (37.5 px) from each page edge, so the result is geometrically correct.
  - Side effect: the canvas lost its named-size print metadata and its trim and safe guides. Layers and the `trim` artboard are unaffected.
  - The preview artboard starts at 38 px rather than 37.5 px, an offset of a quarter pixel at 150 dpi.
- **No TrimBox or BleedBox.** All PDF boxes equal the MediaBox (11.25 × 17.25 in). Vixl did not write separate boxes, and the brief only specifies the page size. A printer could need the trim box to be stated: it is 0.125 in inside every edge.
- **Text is raster in the PDF.** Vixl refuses vector content for CMYK PDFs ("CMYK PDF pages are raster"). The whole page, text included, is one 300 ppi CMYK image. Edges are slightly softer than vector type would be, and the JPEG compression is set to quality 95.
- **CMYK conversion.** It is device-naive GCR with a 300% ink limit and no press ICC profile. Saturated amber and coral may shift slightly on press. I did not check the result with a soft-proof preview.
- **The PNG has an alpha channel.** It is RGBA (mode check: alpha is 255 everywhere, fully opaque), not 3-channel RGB. Vixl's PNG export keeps an alpha channel and has no option to drop it. I did not convert it outside Vixl, because the lane rules allow scripts only for reading inputs and checking outputs. If a strict RGB file is required, it needs a one-step flatten.
- **Thumbnail warnings ignored.** `vixl_check` warns that the list, footer and credit text are small at a 320 px thumbnail width. For an 11 × 17 print they are about 25, 23 and 18 pt, so I left them.
