# T06 round 2 · Fillable PDF form (lane V, Vixl)

I made every change through the Vixl MCP tools. The source was a copy of `../signup-form.vixl`, opened with `vixl_document_open`. I then used `vixl_operations_apply` for two atomic batches, `vixl_check` with `sample="worst"`, and `vixl_export_batch` for both PDFs. I didn't write any SVG, HTML or pixels myself. Afterwards I used pypdf, pdftotext and a 60 dpi pdftoppm render to read the outputs back. Nothing outside `round2/` was changed.

## Files

| File | How it was made |
| --- | --- |
| `signup-form.vixl` | The round-1 source copied here, then edited with two operation batches (see below). |
| `signup-form.pdf` | Made with `vixl_export_file` (through `vixl_export_batch`) with `fillable=true`. It is one page, vector, with 15 field keys and 18 widgets. |
| `signup-sample.pdf` | Made with `values={…}` and `fill_mode="flatten"`. It has no AcroForm and no annotations. |
| `REPORT.md` | This file. |

## What changed

1. **New field `instagram`.** It is a text field, required, labelled "Instagram handle *" (the " *" follows the round-1 convention for required fields).
   - The label is a duplicate of the Email label with its text changed. The field copies the Email box style: Bitter at 44 px, a `#f6f7f9` fill, a `#6b7a8c` stroke and radius 10.
   - I added two rules the brief didn't ask for:
     - `max_length` 31, which is "@" plus Instagram's 30-character limit.
     - `pattern` `@?[A-Za-z0-9._]{1,30}`, with a message. In the PDF this becomes a validate action that viewers which run JavaScript enforce.
2. **Layout change, to give the handle room.**
   - My first try put Instagram in Phone's old 700 px slot next to Email. `vixl_check` (worst case) failed it: 31 "W" characters need 980 px even at the smallest shrink size, and the box only holds 660 px.
   - So the layout is now:
     - **Email:** its own full-width row (2100 px, the same width as Performer name).
     - **The next row:** Instagram (1300 px) on the left and Phone (700 px) on the right.
   - Everything from "Type of act" to Signature/Date moved down 240 px.
   - The footer rule and footer text moved down 170 px. The footer text now ends at y=3251, inside the 38 px safe margin (3262).
   - Nothing was resized except Email, which was widened.
3. **Slot options.** I changed them with `field-set` to `7:00–7:30`, `7:30–8:00`, `8:00–8:30`, `8:30–9:00`, `9:00–9:30`, `9:30–10:00`, all with real en dashes (U+2013). The field is still a required combo box.
4. **Tab order.** It still comes from reading order (`form.tab_order = reading`, page `/Tabs /S`). Read back from the PDF, the widgets are annotated in this order:
   1. performer_name
   2. email
   3. instagram
   4. phone
   5. act_type (×4)
   6. performers
   7. needs_mic, needs_amp, needs_keyboard, needs_projector
   8. pieces
   9. slot
   10. photo_consent
   11. signature
   12. date

   Instagram comes right after Email and before Phone.
5. **Sample.** I re-exported the sample with the brief's values, plus `instagram: @driftwoodquartet` and `slot: 8:30–9:00`. pdftotext and the render show every value in full: the long performer name at full size, the three pieces on three lines, Phone empty, Music, mic, amp and photo consent ticked, and keyboard and projector not ticked.

## Checks

- **`vixl_check(sample="worst")`:** 0 errors, 0 warnings. This is after the re-layout; before it, the check failed on Instagram's overflow.
- **pypdf read of the form:**
  - `instagram` is `/Tx`, with Ff 2 (required), MaxLen 31, a `/AA /V` pattern script, and the tooltip "Instagram handle *".
  - `slot` is `/Ch` with the 6 options above.
  - Every other field keeps its round-1 type, flags and actions.

## Unchanged from round 1 / still true

Everything listed under "Choices and deviations" in `../REPORT.md` still applies. That includes:

- The signature is a text field.
- The length limits I chose.
- Values typed in a viewer are drawn in Helvetica.
- I haven't tested the form by hand in Acrobat, Preview or a browser.

## Unsure about

- The handle pattern accepts a handle with or without the leading "@". It does not check Instagram's other rules, such as no trailing dot.
- Making Email a full-width row was a layout choice so the required handle fits worst-case input. A narrower Instagram box with a lower `max_length` (20, as the check suggested) would have kept the old row shape, but it would have rejected some valid 21–30 character handles.
