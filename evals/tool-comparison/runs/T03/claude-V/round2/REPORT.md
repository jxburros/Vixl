# T03 round 2: Harbor Lights poster revisions (lane V, Vixl)

All edits were made with the Vixl MCP tools (`vixl_document_open`, `vixl_document_inspect`, `vixl_operations_apply`, `vixl_check`, `vixl_render_preview`, `vixl_export_file`). I wrote no pixels, SVG or HTML. Shell commands only copied the source file and read the outputs (`pdfinfo`, `pdftotext`, `pdfimages`, `pdffonts`, PIL).

## What changed

| Change | How |
| --- | --- |
| The kicker now reads **"Old Customs House Square"** (was "Port Ellery Quay"). | `text-set` on the existing `kicker` layer, so it keeps its font, size, colour, spacing and `text_transform: uppercase`. It prints as "OLD CUSTOMS HOUSE SQUARE". The layer is auto-sized, so it grew from 821 to 1323 px wide. I re-centred it on the canvas with `align` (`center-x`, relative to canvas). |
| The fourth highlight now reads **"Fire dancers at 8 pm"** (was "Live brass band"). | `text-set` on the `highlights` rich-text layer. The four bulleted paragraphs and the 1.5 line height are unchanged. |
| A new **1 × 1 in white square** with **"QR"** centred in it. | A new `qr-box` layer: a `rectangle`, 300 × 300 px at 300 dpi (= 1 in), fill `#ffffff`, at x 2962, y 4762. Its right edge is at 3262 and its bottom edge at 5062. The safe area runs to 3262.5 and 5062.5 (0.25 in inside the trim plus 37.5 px of bleed), so the square sits in the bottom-right corner of the safe area, 0.5 px inside both edges. I first placed it exactly on the corner (2962.5 / 4762.5), but `vixl_check` rounds boxes outward and flagged it as 1 px outside the safe area, so I moved it in by half a pixel. A new `qr-label` text layer reads "QR", in the heading font (Fraunces 700), 120 px (about 29 pt), colour `#0b1a2e` (the poster's navy). I centred it on the box with `align` (`center`, relative to `qr-box`). The ink box includes the Q's tail, so that alignment left the capitals about 9.5 px above centre. I moved the label down 9.5 px (to y 4870), which centres the cap height (84 px) in the square. |

Nothing else in the design changed: the layers, the positions of all other elements, the `brief` suite and the `trim` artboard are all as they were. The document now has 240 layers (238 before).

## Files (same names and print spec as round 1)

- `poster.vixl` is a copy of round 1's source with the edits above applied.
- `poster-print.pdf` was made with `vixl_export_file(color_space="cmyk", ink_limit=300)`. It is 1 page, 810 × 1242 pt (11.25 × 17.25 in), with MediaBox = BleedBox and **TrimBox 9 9 801 1233** (11 × 17 in). It has live text and 2 embedded fonts (Atkinson Hyperlegible Next and Fraunces Bold). Its only images are the 34 glow gradients, as CMYK images with gray soft masks, as before; there are no RGB images. The white square is vector DeviceCMYK.
- `poster-preview.png` is the `trim` artboard exported with `scale=0.5, dpi=150, alpha=flatten`: **1650 × 2550 px, RGB, 150 dpi**. I sampled the pixels inside the square and they read pure white (255, 255, 255).

## Checks

- After each batch, `vixl_check` passed with no fix or review findings. It ran bounds, overlap, contrast, safe_area, legibility, placeholders, fonts and print (`min_ppi=300`). The 27 informational findings are the intentional bleed crops from round 1.
- The document's `brief` suite (19 rules: contrast, safe margin, kicker above title, title hierarchy, at most 2 fonts, 300 ppi) **passed**. "QR" uses the heading font, so the poster still has only 2 fonts.
- `pdftotext` returns every line, including "OLD CUSTOMS HOUSE SQUARE", "• Fire dancers at 8 pm" and "QR". No "Port Ellery Quay" or "Live brass band" remains.
- I looked at a full preview and a zoomed preview of the corner with the safe and trim guides drawn.

## Notes

- **No ICC profile**, as in round 1. The CMYK output uses Vixl's GCR approximation with a 300 % ink limit.
- The "QR" square is a placeholder, as requested. It holds no scannable code. Vixl has a `qr` operation that can drop a real code into the same 300 × 300 box once there is a URL.
- The kicker's tracking stays at 0, as in round 1 (see that report for the reason).
- The shared Vixl server wrote an untracked `.vixl-suite-passes.json` at the repository root when the suites ran. It is server bookkeeping, not a deliverable, and I left it alone.
