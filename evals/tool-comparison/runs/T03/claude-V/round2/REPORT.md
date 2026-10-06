# T03 round 2 · Print poster revision (Lane V, Vixl)

All visual edits were made with the Vixl MCP tools on a copy of the round-1 source: `vixl_document_open`, `vixl_operations_apply`, `vixl_check`, `vixl_measure`, `vixl_render_preview` and `vixl_export_batch`. I drew no pixels and wrote no SVG or HTML. I used `cp` once to copy `../poster.vixl` into `round2/`. I used pdfinfo, pdffonts, pdfimages, pdftotext and a short Pillow/numpy script only to check the outputs. Nothing outside `round2/` was changed.

## Files

| File | What it is | How it was made |
| --- | --- | --- |
| `poster.vixl` | Editable source: a copy of round 1 with the three edits below. It now has 133 layers, and all text is still live. | `cp ../poster.vixl`, then one atomic `vixl_operations_apply` batch. I dry-ran the batch first. |
| `poster-print.pdf` | One CMYK page, 810 × 1242 pt (11.25 × 17.25 in). TrimBox is 9 9 801 1233 and BleedBox equals MediaBox. | `vixl_export_file` options through `vixl_export_batch`: `color_space="cmyk", ink_limit=300, dpi=300` (same as round 1). |
| `poster-preview.png` | 1650 × 2550 px, RGB, 150 dpi. It shows the trimmed area only. | Same batch: `artboard="trim", scale=0.5, alpha="flatten"` (same as round 1). |
| `REPORT.md` | This report. | |

## Changes

1. **Kicker.** Changed to "Old Customs House Square".
   - Operation: `text-set` on layer `kicker`, then `align center-x` to re-center it on the canvas. The kicker is an auto-sized, left-aligned layer, so it grew to the right.
   - It is the same font, size (100 px) and gold color. It is now 1272 px wide (x 1052–2324), centered at x 1688.
2. **Highlight 4.** Changed "Live brass band" to "Fire dancers at 8 pm".
   - Operation: `text-set` on layer `highlights` with all four lines.
   - The rich-text bullet list (four `bullet` paragraphs, line height 1.45) was kept. I checked this in the dry-run result before applying, and the PDF text shows four "•" items.
3. **QR placeholder.**
   - Layer `qr-box`: a white (`#ffffff`) rectangle, 300 × 300 px, which is 1 × 1 in at 300 dpi. It sits at x 2963–3263, y 4763–5063.
   - The safe area here is the brief's text rule, 0.25 in (75 px) inside the trim. The trim's right edge is at x 3338 and its bottom edge at y 5138. So the square's right and bottom edges sit exactly on that safe line, and the square sits inside it.
   - Layer `qr-label`: live text "QR" in DM Sans, 120 px, navy `#0b1a2e`. It was centered with `align center relative_to=qr-box`. The ink box centre is (3112.5, 4912.9) against the square's centre at (3113, 4913).
   - The square does not touch any other layer. The nearest is the "Free entry…" line, which ends at x 2490.

Nothing else was moved or restyled. The rows of pixels that differ between the round-1 and round-2 previews are only these three bands: 146–192 (kicker), 2180–2229 (list line 4) and 2361–2513 (QR square).

## Checks

- **`vixl_check`:** passed with 0 errors. It ran bounds, overlap, contrast, safe_area, legibility, blanks, fonts and print, with a 113 px safe area and a 300 ppi minimum.
  - Warnings that remain:
    - The contrast check could not measure `title` because of an internal error (as in round 1).
    - The same internal error hit the new `qr-label`.
  - `vixl_measure` gives `qr-label` a contrast of 15.2:1 at the 10th percentile and 16.3:1 on average against the white square. Its minimum of 1.0 comes from anti-aliased edge pixels.
  - The other findings are informational: art that bleeds off the edge on purpose.
- **QR square, measured in the 150 dpi preview:**
  - The white area is x 1463–1611 and y 2363–2511, which is 149 × 149 px (about 1 in).
  - It is 38 px (0.25 in) from both the right and the bottom trim edges.
- **PDF:**
  - One page, 11.25 × 17.25 in, with TrimBox and BleedBox set.
  - No DeviceRGB anywhere.
  - Every image is CMYK at 300 ppi, with gray soft masks.
  - DM Sans and DM Serif Display are embedded as subsets.
  - `pdftotext` reads the new kicker, the four bullets ending "Fire dancers at 8 pm", and "QR".

## Deviations and uncertainties

- **Print spec:** the same as round 1, so the round-1 notes still apply.
  - The 38 px bleed was rounded, so the artwork is about 300.09 dpi in effect.
  - The CMYK is a device-naive GCR conversion with a 300 % ink limit and no ICC profile.
  - Live transparency is kept, so this is not a flattened PDF/X-1a.
  - There are no crop marks.
- **QR square color:** "white" was taken as RGB `#ffffff`. In the CMYK PDF that becomes no ink (paper white). The "QR" letters are dark navy in all four inks, not pure K.
- **Placeholder only:** the "QR" text is a placeholder, not a scannable code.
- **"Safe area":** I took this as the brief's 0.25 in inside the trim. Vixl's own `safe-*` guides on this document sit 0.125 in inside the trim, at x 3300 and y 5100. A square placed against those guides would sit 0.125 in further out, with its text closer to the trim than the brief allows.
