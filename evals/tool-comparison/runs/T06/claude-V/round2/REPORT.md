# T06 round 2: Vixl run (lane V)

All visual work used the Vixl MCP tools (`vixl_document_open`, `vixl_operations_apply`, `vixl_render_preview`, `vixl_export_file`). Python (pypdf) and `pdftoppm` were used only to read the old sample's values and to check the new PDFs.

## What changed

1. **New field `instagram`** ("Instagram handle *"): required text field, placed right after Email in the same row (Email left, Instagram handle right). PDF tooltip "Instagram handle". Max length 31 (an optional `@` plus Instagram's 30-character limit), with a pattern check `@?[A-Za-z0-9._]{1,30}` and the message "Enter an Instagram handle such as @yourname (letters, digits, . and _, up to 30)". Like the round 1 email check, the pattern only runs in viewers that run PDF JavaScript.
2. **Phone** moved to its own row under Email, left-aligned with it. The row had no room for three fields.
3. **Slot dropdown options** are now `7:00–7:30`, `7:30–8:00`, `8:00–8:30`, `8:30–9:00`, `9:00–9:30`, `9:30–10:00` (en dashes, as before). `slot` is still a required combo box.
4. **Room for the new row.** Everything from "Type of act" to the pieces box moved down 255 px (one row). To keep the footer where it was, the gaps around the photo-consent row were tightened (90/110 px to 65 px), and the signature and date boxes were made 150 px tall instead of 170 px. Header and footer are unchanged.
5. **Widths.** The first try (Email 1225 px, Instagram 800 px) failed the worst-case form check: 31 W's need 854 px at the 28 px minimum, and the box had 764 px. I changed the layout instead of the rule: Email is now 1125 px wide, Instagram handle is 900 px wide (from x 1425), and Phone is 1125 px wide to match Email.
6. **Tab order** stays `reading`: 1 performer_name, 2 email, 3 instagram, 4 phone, 5 act_type, 6 performers, 7 slot, 8–11 needs_*, 12 pieces, 13 photo_consent, 14 signature, 15 date. I checked this in `vixl_render_preview(show_fields=true)` and in the PDF's `/Annots` order (page `/Tabs /S`).
7. **Check suite `brief`** updated: field count is now 18. New rules: the Instagram label text; `instagram` to the right of `email` with tops aligned; Phone's label below Email and left-aligned; pieces above photo consent; signature above the footer rule. The suite still extends `fillable-form`, which includes the worst-case form check.

## Files (same names as round 1)

| File | How it was made |
| --- | --- |
| `signup-form.vixl` | A copy of the round 1 source, edited with one atomic batch (`build-ops.json`). |
| `build-ops.json` | The round 2 change batch: 12 operations applied to the round 1 document. It does not rebuild the form from scratch; the round 1 `build-ops.json` is still the base. |
| `signup-form.pdf` | `vixl_export_file(fillable=true)`. It has 15 AcroForm fields, including `instagram`, and the slot has 6 options. |
| `signup-sample.pdf` | `vixl_export_file(values=…, fill_mode="flatten")` with the round 1 sample values, except `slot` = `8:30–9:00` and `instagram` = `@driftwoodquartet`. It has no form fields (no AcroForm and no annotations). |

## Checks

- `vixl_check` (default checks, including `form`): passed. The only findings are the two waived full-bleed header shapes from round 1, which are informational.
- Suite `brief`: all 12 rules pass, including the worst-case sample overflow check.
- pypdf on the fillable PDF: 15 fields; `instagram` is `/Tx`, required (Ff 2), with tooltip "Instagram handle"; the slot `/Opt` lists exactly the six new options.
- I rendered the sample at 60 dpi and looked at it. "@driftwoodquartet" and "8:30–9:00" are fully visible, and every other value matches round 1. Microphone, guitar amp and photo consent are checked, and Music is selected.

## Notes

- Phone now sits alone on a row with empty space to its right. I chose this so that Email and Instagram handle stay next to each other in reading order.
- The sample's text extraction lists the Instagram value last, because of how text runs are ordered in the content stream. The visual position and the tab order are correct.
