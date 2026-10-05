# T06 · Fillable PDF form — judge notes

Judge: claude-opus-5-5 subagent, 2026-10-05. Runs: claude-V (Vixl), claude-C (reportlab + pypdf).

## 1. Blind scores (written before opening key.csv)

| Code | Round | Fidelity | Craft | Reason |
| --- | --- | --- | --- | --- |
| UIL4 | r1 | 5 | 4 | Every label, header, footer and "We need:" group present; sample fully visible; tidy bold labels, red asterisks, hints; empty lower third |
| TBL6 | r1 | 5 | 4 | Same coverage; display-font header, visible dropdown chevron; photo consent not marked optional; some dead space |
| AYFY | r2 | – | – | Instagram after Email, slot 8:30–9:00, @driftwoodquartet |
| WYZ8 | r2 | – | – | Same |

Key: UIL4 = claude-C, TBL6 = claude-V, AYFY = claude-C/round2, WYZ8 = claude-V/round2.

Post-key adjustment: V fidelity lowered 5 → 4 because the PDF enforces none of the brief's rules for email format, performers 1–6 (number) or the date (plain text fields, no actions). This is disclosed and isn't visible in a blind look. C carries AcroForm JavaScript for all three.

## 2. Hard checks (round 1)

| Check | V | C |
| --- | --- | --- |
| 14 fields, exact keys | PASS | PASS |
| Kinds (radio music/poetry/comedy/other; pieces multiline; slot dropdown; checkboxes) | PASS: act_type /Btn radio, export values music/poetry/comedy/other; pieces Ff 4096; slot /Ch combo (Ff 131074); 5 checkboxes | PASS: same flags |
| Required = exactly the 6 | PASS: Ff bit 2 only on performer_name, email, act_type, slot, signature, date; checkboxes 0 | PASS: same; reportlab's default required checkboxes cleared |
| performer_name max_length=80 | PASS (also added phone 24, signature 60: extra limits, disclosed) | PASS (reportlab's MaxLen 100 removed elsewhere) |
| Dropdown options exact with en dashes | PASS: 7:00–7:45, 7:45–8:30, 8:30–9:15, 9:15–10:00 (U+2013) | PASS: same, en dashes written by pypdf after reportlab (trap avoided) |
| widget_order follows reading order | PASS: annots order = reading order (no /Tabs key on the page) | PASS: same order, /Tabs /R |
| Sample: no form_fields, all values visible, long name uncut, pieces on 3 lines | PASS: no AcroForm, 0 annots; all values visible in render and text | PASS: same |
| **Total** | **7/7** | **7/7** |

## 3. Report honesty

- V: **yes**. Signature as text, unenforced email/range/date rules, extra max lengths, worst-case overflow warning and Helvetica for typed input are all stated accurately.
- C: **yes**. The en-dash workaround, cleared reportlab defaults, JS-only validation and the sample being drawn rather than flattened from the form are all stated accurately.

## 4. Round 2 (required `instagram` after Email; 30-minute slots; sample with 8:30–9:00 and @driftwoodquartet)

| | V | C |
| --- | --- | --- |
| Result | 15 fields; instagram /Tx required (MaxLen 31 added); widget order performer_name, email, instagram, phone, …; 6 new options with en dashes; sample flattened, shows @driftwoodquartet and 8:30–9:00 | 15 fields; instagram /Tx required; same order; 6 options with en dashes; sample flattened, shows both values |
| Drift (field-rect diff r1→r2) | Only email narrowed, phone shifted, instagram added | Only email narrowed, phone shifted, instagram added |
| Editability | **5**: duplicated email field + label in one batch, then field-set | **5**: 4 small script edits |
| Revision | **5** | **5** |

Vixl-specific gaps seen: no PDF-side validation (format/range/date) in the fillable export; `required` refused on signature-kind fields; no `max_length` for multiline fields; the round-2 worst-case check flagged 6 overflow errors where round 1 flagged 1 (the run believed the check got stricter); the preview with `values=` drew oversized clipped text (export correct).
