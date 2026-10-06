# T06 · Fillable PDF form (lane V, Vixl)

All of the visual work went through the Vixl MCP tools: `vixl_document_create`, `vixl_font_pair`, `vixl_operations_apply`, `vixl_check`, `vixl_render_preview` and `vixl_export_file`. I wrote no SVG, HTML or pixels myself. The only scripts were checks afterwards: pypdf to read the field dictionaries, and pdftoppm/pypdf to render the sample and pull its text.

## Files

| File | How it was made |
| --- | --- |
| `signup-form.vixl` | The editable Vixl source. It was created at US Letter size (2550 × 3300 px at 300 dpi). I then added two batches of operations: shapes, text layers, 17 `field` layers and a `form` op, followed by a `field-set` and move fix-up. |
| `signup-form.pdf` | The blank fillable form, made with `vixl_export_file(fillable=true)`. It is one page, vector artwork, with 14 field keys (17 widgets, because the four radio buttons are separate widgets). |
| `signup-sample.pdf` | The sample fill, flattened, made with `vixl_export_file(values={…}, fill_mode="flatten")`. It has no AcroForm and no annotations, so no fields are left. |
| `REPORT.md` | This file. |

## Design

- **Page.** The header is a navy `#14263b` band with an amber `#f2a541` rule under it. The title "Open Mic Sign-up" is set in Work Sans Bold, white. The subtitle "Tidewick Café · Thursdays 7–10 pm" is set in Bitter, amber. The footer is an amber rule with the brief's footer line centred under it.
- **Fonts.** The type pairing is Work Sans and Bitter, installed with `vixl_font_pair`.
- **Fields.** Each field has a visible label above it. Required fields are marked with " *", and a "* required" note sits top right. The fields have light-grey boxes. The signature is a line to write on.

## Field check (read back from the PDF with pypdf)

| Key | PDF type and flags |
| --- | --- |
| `performer_name` | Text, Required, MaxLen 80 |
| `email` | Text, Required, MaxLen 80. A validate script checks the `name@host` form. |
| `phone` | Text, optional, MaxLen 21 |
| `act_type` | Radio group with options `music` / `poetry` / `comedy` / `other`. Required, tooltip "Type of act". |
| `performers` | Text field with number actions: `AFNumber_Keystroke`/`Format` with 0 decimals, plus a validate script for the range 1–6. MaxLen 1. |
| `needs_mic`, `needs_amp`, `needs_keyboard`, `needs_projector` | Checkboxes (on value `Yes`), sitting under a visible "We need:" heading |
| `pieces` | Multiline text, box sized for 3 lines, MaxLen 300 |
| `slot` | Combo box with the four slots exactly as written (en dashes). Required. |
| `photo_consent` | Checkbox, optional |
| `signature` | Text, Required, MaxLen 40 |
| `date` | Text with `AFDate_KeystrokeEx`/`FormatEx` set to `yyyy-mm-dd`. Required. |

- **Tab order.** The page declares `/Tabs /S`, and the widgets are annotated in reading order: performer_name, email, phone, act_type, performers, the four needs_* boxes, pieces, slot, photo_consent, signature, date.
- **Two fields share a row.** Email and phone are side by side, and so are signature and date. In each pair the left field comes first in the tab order.
- **`vixl_check`.** With `sample="worst"` it passes: 0 errors, 0 warnings.

## Sample fill

`pypdf` reads all the brief's values back from `signup-sample.pdf` as text, and none of them are cut off:

- The long performer name is drawn at the field's normal 44 px size.
- Pieces are drawn one per line, on three lines.
- Phone is left empty.
- Music, mic, amp and photo consent are ticked or selected. Keyboard and projector are not ticked.

I also looked at a 60 dpi render of the sample to confirm this.

## Choices and deviations

- **Signature is a text field, not a PDF signature field.** The brief allows either. I used text because Vixl's `signature` kind can't take a fill value, and the sample needs "B. Okonkwo-Fitzgerald" drawn in. It is still required, but it can't hold a digital signature.
- **Limits I added.** The brief gives no length for these, so I chose them.
  - Phone: max 21. This is the longest worst-case value that fits the box.
  - Email: max 80.
  - Pieces: max 300.
  - Signature: max 40. This is the most that fits at the smallest size I allowed.
- **Smaller minimum text size for two fields.** For `performer_name` and `email`, the smallest size the value can shrink to is 25 px (6 pt) instead of 30 px. At that size, the worst case passes the overflow check: 80 "W" characters for the name, 64 for the email. Real values never shrink that far; the sample name renders at full size.
- **Number of performers.** Vixl writes it as a PDF text field with number format and range actions, because PDF has no separate number field type. Viewers that don't run JavaScript (some browser viewers) won't enforce the 1–6 range or the email format. Vixl does enforce them when it fills a form.
- **Field tooltips (accessible names) come from the visible labels.** Fields whose label is a text layer above them get that text as their tooltip, so it includes the " *" marker (e.g. "Email *", "Date * (YYYY-MM-DD)"). The checkbox tooltips are "We need: Microphone" and so on, so the group context gets read out. The visible text next to each checkbox is a separate text layer.
- **What people type in a viewer uses Helvetica.** Vixl's fillable PDF uses Helvetica for typed entries. The flattened sample uses the form's Bitter font.

## Unsure about

- I haven't tested the fillable PDF by hand in Acrobat, Preview or a browser. I only read its structure with pypdf.
- How the dropdown's en dashes look when someone picks an option in a viewer depends on that viewer's Helvetica coverage. Helvetica does include the en dash.
