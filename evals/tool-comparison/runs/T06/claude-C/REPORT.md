# T06 Fillable PDF form (lane C, claude)

## Files
| File | How it was made |
| --- | --- |
| `signup-form.pdf` | Blank fillable form, US Letter portrait (612 x 792 pt), one page. Layout and AcroForm fields drawn with reportlab 5.0.1 (`canvas.acroForm`), then post-processed with pypdf 6.19 (JavaScript actions, field flags, real dropdown options, tab order). |
| `signup-sample.pdf` | Sample fill, flattened. Made by the same script, which draws the same layout with the sample values as plain vector text and shapes in place of the widgets. It has no `/AcroForm` and no annotations, so nothing is editable. |
| `make_form.py` | Editable source. `python3 make_form.py` regenerates both PDFs. |

## What's in the form
- Header: navy band, "Open Mic Sign-up" with "Tidewick Café · Thursdays 7–10 pm" in amber under it, and a thin amber rule. Footer: amber rule, then "Return this form at the counter or email it to openmic@tidewick.example". The brand colors are #14263b and #f2a541.
- All 14 keys use the exact names from the brief. Each has a visible label, and required fields get an amber `*` plus the note "Fields marked * are required."
  - `performer_name`: text, Required flag, `/MaxLen 80`.
  - `email`: text, Required, plus a validate script (regex `x@y.z`) that warns and rejects a bad address.
  - `phone`: text, optional (labelled "optional").
  - `act_type`: radio group with export values `music`, `poetry`, `comedy`, `other`. Required, NoToggleToOff, nothing selected at the start.
  - `performers`: text field with AFNumber keystroke/format scripts and a validate script that only accepts a whole number from 1 to 6. The label hint says "1 to 6".
  - `needs_mic`, `needs_amp`, `needs_keyboard`, `needs_projector`: checkboxes under the group label "We need:", with item labels Microphone / Guitar amp / Keyboard / Projector. All optional.
  - `pieces`: multiline text, 62 pt tall (3 lines at 11 pt), hint "one per line, up to 3".
  - `slot`: combo box (dropdown), Required. `/Opt` is exactly `7:00–7:45`, `7:45–8:30`, `8:30–9:15`, `9:15–10:00` with real en dashes, and no value is preselected (`/V` and `/DV` are empty).
  - `photo_consent`: checkbox with the full label text and "(optional)".
  - `signature`: plain text field, Required, hint "type your full name".
  - `date`: text field, Required, with `AFDate_KeystrokeEx/FormatEx("yyyy-mm-dd")` scripts and hint "YYYY-MM-DD".
- Tab order: widgets are created in reading order (top to bottom, left to right within a row), so the page's `/Annots` array runs performer_name, email, phone, act_type x4, performers, needs_* x4, pieces, slot, photo_consent, signature, date. The page sets `/Tabs /R` (row order). I checked the order with pypdf.

## Sample fill
All values from the brief are there. Phone is empty. The radio shows Music. Mic and amp are ticked; keyboard and projector are not. The pieces are on three lines. The slot is 8:30–9:15, photo consent is ticked, and the signature and date are filled in. The script checks that each value fits its box (an assert on text width, shrinking the type if needed). In the end every value fit at 11 pt, including the 55-character performer name. I rendered both PDFs with pdftoppm and checked them by eye.

## Deviations and choices
- **Flattening method:** the sample isn't a filled copy of signup-form.pdf flattened afterwards. It's drawn directly from the shared layout code, so it matches the form pixel for pixel without depending on a flattening library. Widgets are redrawn as vector shapes: a box with a vector checkmark, a circle with a dot, and a dropdown box with a chevron.
- **Signature** is a text field, not a `/Sig` digital-signature field. The brief allows either, and a text field is easier to fill and print.
- **Date** and **number** are AcroForm text fields with Acrobat JavaScript formatting and validation. PDF has no native date or number field types. Viewers that don't run JS (pdf.js partly, Preview, poppler) will accept any text there. The same goes for the email check.
- reportlab can't encode an en dash in a field appearance stream. So the dropdown is created with placeholder options and a blank appearance, and pypdf then rewrites `/Opt` with the real en-dash strings. `NeedAppearances` is not set, so viewers use reportlab's appearance streams. When a value is picked, viewers regenerate the dropdown's appearance themselves.
- reportlab marks checkboxes Required by default and gives every text field `/MaxLen 100`. Post-processing clears Required on all checkboxes and removes MaxLen everywhere except `performer_name`.

## Unsure about
- In poppler's render of the blank form, the radio circles come out slightly smaller and lower than their labels. This is reportlab's radio appearance stream, and other viewers may draw it differently.
- I didn't test in Acrobat (none available). The JS validation is standard Acrobat API, but I didn't run it.
- When the dropdown is empty, some viewers may show the first option (7:00–7:45) as if it were chosen, even though `/V` is empty.

## Timing
Start 2026-10-05 22:18:46 UTC; end 2026-10-05 22:21 UTC (about 3 minutes). Tool calls: 12 (including this report and the hand-back).
