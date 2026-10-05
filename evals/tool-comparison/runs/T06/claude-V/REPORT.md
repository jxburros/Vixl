# T06 Fillable PDF form (lane V: Vixl via MCP)

## Timing
Start 2026-10-05 22:18:46 UTC, end 2026-10-05 22:26:41 UTC (about 8 minutes). About 37 tool calls in total (Vixl MCP, Bash, Read, ToolSearch).

## Files
| File | How it was made |
| --- | --- |
| `signup-form.vixl` | The editable Vixl source. Made with `vixl_document_create(size="letter")` (2550x3300 px at 300 dpi), then `vixl_font_pair` (Bricolage Grotesque 800 for the title, Figtree 400 for the rest), `vixl_text_add`, and one atomic `vixl_operations_apply` batch: shapes, text, 17 `field` layers and `form` (tab_order `reading`, title, lang `en`). After that, `field-set` tweaks. |
| `signup-form.pdf` | `vixl_export_file(fillable=true)`. US Letter 612x792 pt, vector, with an AcroForm of 14 fields named exactly as the brief's keys. |
| `signup-sample.pdf` | `vixl_export_file(values={...}, fill_mode="flatten")` with the brief's sample values. It has no AcroForm and no annotations, so the values are drawn into the page. |

Checked with pypdf, pdftotext and pdftoppm. Field types: text fields are /Tx, `act_type` is one radio /Btn with export values music/poetry/comedy/other, the checkboxes are /Btn (on value `Yes`), and `slot` is a /Ch combo with the 4 options. Required flags are set on performer_name, email, act_type, slot, signature and date. MaxLen is 80 on performer_name. The widget order (tab order) runs performer_name, email, phone, act_type, performers, needs_mic, needs_amp, needs_keyboard, needs_projector, pieces, slot, photo_consent, signature, date, which is the reading order. In the rendered sample PDF every value is fully visible: the long performer name fits on one line, pieces shows 3 lines, and the date is 2026-11-12.

## Differences from the brief and choices I made
- **`signature` is a required single-line text field, not a signature field.** Vixl refuses `required` on signature-kind fields, and the brief allows "signature or text field".
- **Rules the PDF does not enforce:** the email format, the 1 to 6 range on `performers` and the date format are stored as Vixl field rules (`format: email`, `{decimals:0,min:1,max:6}`, date `YYYY-MM-DD`). Vixl validates them when it fills the form. But the fillable PDF has no JavaScript or actions, so a PDF viewer will not reject a bad email or a 7 typed by hand. The "1 to 6" hint is printed next to the box.
- **Extra limits I added:** `phone` max 24 characters and `signature` max 60. Vixl's worst-case check flagged these fields as able to overflow without a limit.
- **Labels:** required fields show " *" in their label, with a "* required" note at top right. Because the labels are linked to the fields, the PDF tooltips (accessible names) also end in " *". Each checkbox's accessible name is "We need: <item>". "Type of act" is the radio group's question.
- **Title font size:** the brief does not set one, so I picked it. The navy header has an amber rule under it, and an amber rule sits above the footer.

## Unsure or known issues
- `vixl_check(sample="worst")` still reports 1 error: `pieces` (multiline) can overflow with worst-case text. Vixl does not allow `max_length` on multiline fields, so the error cannot be cleared. The sample text fits.
- After I set the field sizes, `vixl_check` raised no other errors or warnings.
- **Vixl bug, preview only:** `vixl_render_preview(values=...)` drew single-line field values oversized and clipped. The exported PDFs draw them correctly, which I confirmed by rasterising them with pdftoppm. The deliverables are affected only to this extent: I judged the result from the PDF rasters, not from Vixl's preview.
- People typing into the fillable PDF get Helvetica (Vixl's design). The flattened sample uses Figtree.
