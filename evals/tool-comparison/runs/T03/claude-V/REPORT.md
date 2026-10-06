# T03 · Print poster — Lane V (Vixl)

All visual work was done with the Vixl MCP tools: document create, font pair, operations_apply, check, measure, render_preview and export_file. I drew no pixels and wrote no SVG or HTML. I used Python, pdfinfo, pdfimages, pdffonts, pdftotext and pdftoppm only to check the outputs.

## Files

| File | What it is | How it was made |
| --- | --- | --- |
| `poster.vixl` | Editable source. It has 131 layers, all text is live, and the fonts DM Serif Display and DM Sans are embedded. It also holds an artboard called `trim`, used for the preview. | `vixl_document_create(size="tabloid", bleed=0.125, background="#0b1a2e")`, then `vixl_font_pair("dm-serif-dm-sans")`, then batches through `vixl_operations_apply` |
| `poster-print.pdf` | One CMYK page. MediaBox and BleedBox are 810 × 1242 pt (11.25 × 17.25 in). TrimBox is 9 9 801 1233 (11 × 17 in). | `vixl_export_file(color_space="cmyk", ink_limit=300, dpi=300)` |
| `poster-preview.png` | 1650 × 2550 px, RGB, tagged 150 dpi. It shows the trimmed area only. | `vixl_export_file(artboard="trim", scale=0.5, alpha="flatten")`. The `trim` artboard is x 38, y 38, 3300 × 5100 px on the 3376 × 5176 canvas. |
| `REPORT.md` | This report. | |

## Design

- **Colors:** a navy night sky that gets lighter toward the horizon, and a darker navy gradient for the water. The lanterns are amber `#f5a13a`, vermilion `#e2533b` and pale gold `#f7cf6a`. Text is cream `#fbf1dc` with gold `#f2c46d` accents.
- **Order down the page:**
  - Kicker "Port Ellery Quay" in gold DM Sans.
  - Title "Harbor Lights" in DM Serif Display at 440 px (about 106 pt).
  - Tagline, then the date line in gold.
  - Two drooping strings of paper lanterns (8 and 7). Each lantern has a body, an inner glow, a cap and a base, plus an outer glow, with a soft warm glow in the sky behind them.
  - A dark quay skyline with lit windows and a lighthouse.
  - The water, with a blurred, striped reflection under each lantern and faint ripple lines.
- **Highlights:** the four lines are a real bulleted list (rich-text Markdown list). Below them are a short gold rule, the "Free entry…" line and the "Presented by…" line.
- **Copy:** exactly as given, including "·", the en dash in "4–10 pm" and "Café". Checked with `pdftotext` on the PDF.

## Checks done

- **`vixl_check`:** passed with 0 errors. It ran bounds, overlap, contrast, safe_area, legibility, blanks, fonts and print checks, with a 113 px safe area and a 300 ppi minimum.
  - The remaining warnings were artwork that runs off the edge on purpose: sky, water, horizon line, lantern strings and the end buildings. I marked these with `layer-intent allow_crop`.
  - The contrast check could not measure the title because of an internal error. `vixl_measure` gives the title a 10th-percentile contrast of 15.9:1.
- **Text margin:** all text is at least about 290 px (about 0.97 in) inside the trim; the brief asks for at least 0.25 in.
- **Bleed:** the sky and water gradients fill the whole canvas, including the bleed. In a render of the PDF, every outer edge is dark.
- **Resolution and color:** every raster part of the PDF is CMYK at 300 × 300 ppi with a gray soft mask (`pdfimages`). Those parts are the glows, the blurred reflections and the see-through sky glow. Text, shapes and gradients are vector in DeviceCMYK. There is no DeviceRGB in the PDF.
- **Fonts:** both fonts are embedded as subsets (`pdffonts`).
- **Preview position:** I rendered the PDF at 150 dpi and compared it with the preview. The best match is at an offset of 18 px, against an expected bleed of 18.75 px, so the preview is the trimmed area.

## Deviations and uncertainties

- **Bleed rounding:** Vixl rounded the 0.125 in bleed to 38 px at 300 dpi, so the canvas is 3376 × 5176 px instead of 3375 × 5175.
  - The PDF page is still exactly 11.25 × 17.25 in, with the TrimBox exactly 9 pt in from each edge.
  - So the artwork is scaled by about 0.03 % (about 300.09 dpi in effect).
  - The preview crop starts at pixel 38 instead of 37.5, a shift of 0.25 px at 150 dpi.
- **CMYK conversion:** no ICC profile was supplied and Vixl ships none. The CMYK is Vixl's general-purpose conversion with a 300 % total ink limit, not a press-profile conversion (GRACoL/SWOP). Colors may shift on press, especially the saturated vermilion lanterns. If the printer supplies a profile, re-export with `icc_profile=`.
- **Transparency:** the PDF keeps live transparency (the glow and reflection images use soft masks). It is not a flattened PDF/X-1a. If the printer requires that, re-export with `pdf_content="raster"` to write each page as one CMYK image.
- **Marks:** no crop marks or slug, since the brief did not ask for them. The TrimBox and BleedBox are set.
- **Dark background:** no text is black. The dark navy background is made from all four inks, under the 300 % limit.
- **PDF title:** Vixl automatically set the PDF's Title metadata to "Port Ellery Quay".
