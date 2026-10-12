# T06 Fillable PDF form: Vixl run (lane V)

All visual work was done with the Vixl MCP tools (`vixl_document_create`, `vixl_operations_apply`,
`vixl_render_preview`, `vixl_check`, `vixl_export_file`). Small Python (pypdf) and `pdftoppm` were used only to
read back and check the exported PDFs.

## Files

| File | How it was made |
| --- | --- |
| `signup-form.vixl` | Editable source. `vixl_document_create(size="letter", purpose="form", background="#ffffff", seed=6)` (US Letter portrait, 2550 x 3300 px at 300 dpi; the rolled Plus Jakarta Sans pairing was installed), then the batch in `build-ops.json` plus two small follow-up batches (see below). |
| `build-ops.json` | The main operation batch (45 operations: header band, text labels, 17 field layers, footer, a check suite), applied with `vixl_operations_apply(operations_path=...)`. Kept as a readable record of the build. |
| `signup-form.pdf` | `vixl_export_file(fillable=true)`: vector page artwork with real AcroForm fields. |
| `signup-sample.pdf` | `vixl_export_file(values={...}, fill_mode="flatten")`: the sample fill drawn into the artwork; no form fields remain (pypdf finds no AcroForm and no annotations). |

## Form contents

- Header: navy (`#14263b`) band with "Open Mic Sign-up" (white) and "Tidewick Café · Thursdays 7–10 pm" (amber `#f2a541`), amber stripe under it.
- Footer: amber rule and "Return this form at the counter or email it to openmic@tidewick.example".
- Every field has a visible text label, also used as the field's accessible name (PDF tooltip `/TU`). Required fields show `*` in the label and a note "Fields marked * are required." sits under the header.
- PDF fields (14 names, exactly the brief's keys):
  - `performer_name` text, required, MaxLen 80.
  - `email` text, required, email-format validate script (`name@host`).
  - `phone` text, optional.
  - `act_type` radio group with export values `music`, `poetry`, `comedy`, `other`, required; group label "Type of act".
  - `performers` number: integer keystroke/format actions and a 1–6 range validation, MaxLen 1.
  - `needs_mic`, `needs_amp`, `needs_keyboard`, `needs_projector` checkboxes under the visible group label "We need:".
  - `pieces` multiline text, box sized for 3 lines at 44 px (about 10.5 pt).
  - `slot` dropdown (combo box) with the four options exactly as written (en dashes), required.
  - `photo_consent` checkbox, optional.
  - `signature` PDF signature field (`/Sig`), required.
  - `date` date field, required, `yyyy-mm-dd` keystroke/format actions; the label says "(YYYY-MM-DD)".
- Tab order: reading order (`form tab_order: reading`), confirmed with `vixl_render_preview(show_fields=true)` (1 performer_name … 14 date) and by the widget order in the PDF page's `/Annots` (page has `/Tabs /S`).

## Checks

- `vixl_check` (default checks, including `form`): no fix or review findings. The two full-bleed header shapes were reported outside the safe area; I waived those with `layer-intent` (deliberate full bleed, no text there).
- Check suite `brief` (extends the built-in `fillable-form` suite, which runs `form` with worst-case sample values, plus my rules for the header/footer copy, footer margin, type hierarchy and field-layer count = 17) passes.
- The first worst-case run failed: 80 W's did not fit `performer_name` at the 28 px minimum, and `phone` (I had set max 30) did not fit. Fix: `performer_name` may shrink to 26 px (keeps the brief's 80-character limit); `phone` max length lowered to 25.
- Sample PDF rendered with `pdftoppm` and inspected: every value is fully visible (the long performer name fits on one line at the field's normal size; all three piece titles show on their own lines; signature, date, slot, checked boxes and the Music radio are drawn).

## Choices and differences from the brief

- `phone` has a 25-character limit the brief did not ask for (needed so the worst-case value fits the box).
- `performers` also has MaxLen 1 (a single digit 1–6). Its export value in the sample is `4`.
- Signature: a real PDF signature field in the blank form. In the flattened sample the signature text "B. Okonkwo-Fitzgerald" is drawn in the document's body font (Plus Jakarta Sans); I did not install a handwriting font.
- In the fillable PDF, people type in Helvetica (Vixl's default `entry_font: standard`), while labels and the flattened sample use Plus Jakarta Sans.
- `phone` was passed as an empty value in the sample, so it stays blank.
- Checkbox export value is the default `Yes`; radio export values are the option keys.

## Unsure about

- Validation scripts (email, number range, date) only work in viewers that run PDF JavaScript (Acrobat and some others); browser viewers show the fields without enforcing them.
- The `required` flag on the signature field marks it for the viewer; whether a viewer enforces it depends on that viewer.
- I did not test the fillable PDF in Acrobat, a browser or Preview; I checked its structure with pypdf only.
