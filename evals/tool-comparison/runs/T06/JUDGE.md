# T06 · Fillable PDF form — judge notes

Runs: claude-V (Vixl 0.20.0, re-run and judged 2026-10-06) and claude-C (reportlab + pypdf, run and
judged 2026-10-05). Judge: claude-opus-5-5 subagent both times. The C scores and notes are carried
over unchanged from 2026-10-05.

For the 2026-10-06 judging, C's deliverables were regenerated from its committed `make_form.py`
(round 1 and round 2) in a scratch copy outside the repo. Both scripts ran cleanly, and the outputs
match the facts recorded on 2026-10-05.

## 1. Blind scores (written before opening key.csv)

2026-10-06 blind set. C is included only for calibration; its scores were not changed.

| Code | Round | Fidelity | Craft | Reason |
| --- | --- | --- | --- | --- |
| CF0G | r1 | 5 | 5 | Every key, label, header, footer and "We need:" group; en dashes; embedded Work Sans + Bitter, navy/amber; sample fully visible, pieces on 3 lines. Nit: signature value set slightly larger than the others |
| CXC4 | r1 | 5 | 4 | Same coverage plus helper hints (max 80, 1 to 6, optional); plainer Helvetica (not embedded); blank dropdown has no chevron |
| 9IPB | r2 | 5 | 4 | Instagram after Email (Email now full width, Instagram + Phone below); 30-minute slots; footer pushed to 12 pt from the page edge |
| PGEW | r2 | 5 | 4 | Instagram squeezed into the Email row (three up); 30-minute slots; nothing else moved |

Key: CF0G = claude-V, CXC4 = claude-C, 9IPB = claude-V/round2, PGEW = claude-C/round2.

No post-key adjustment for V this time: the PDF now enforces the email format, the 1–6 range and the
date format itself (see below).

2026-10-05 blind set, for the record: UIL4 = claude-C (5/4), TBL6 = claude-V on 0.18.0 (5/4, lowered
to fidelity 4 after the key because the PDF enforced none of the email, range or date rules).

## 2. Hard checks (round 1)

V measured on 2026-10-06 with `inspect_outputs.py`, a pypdf dump of every widget, a pypdf fill of the
blank form rendered with poppler, and pdftotext/renders of the sample. C as judged 2026-10-05.

| Check | V (0.20.0) | C |
| --- | --- | --- |
| 14 fields, exact keys | PASS | PASS |
| Kinds | PASS: act_type /Btn radio (Ff 0xC002), states music/poetry/comedy/other; pieces multiline (Ff 0x1000); slot /Ch combo (Ff 0x20002); 5 checkboxes, on-state /Yes | PASS: same flags |
| Required = exactly the 6 | PASS: Ff bit 2 only on performer_name, email, act_type, slot, signature, date | PASS; reportlab's default required checkboxes cleared |
| performer_name max_length=80 | PASS (extra, disclosed limits: email 80, phone 21, pieces 300, signature 40) | PASS |
| Dropdown options exact, en dashes | PASS: 7:00–7:45, 7:45–8:30, 8:30–9:15, 9:15–10:00 (U+2013) | PASS, en dashes written by pypdf after reportlab |
| widget_order = reading order | PASS: annots in reading order, page /Tabs /S | PASS, /Tabs /R |
| Sample: no fields, all values visible | PASS: no AcroForm, 0 annots; long name at full size, pieces on 3 lines, phone empty | PASS |
| **Total** | **7/7** | **7/7** |

Extra V measurements: email has a validate script (`name@host`), performers has
`AFNumber_Keystroke/Format` plus a 1–6 validate script, date has `AFDate_KeystrokeEx("yyyy-mm-dd")`.
Filling the blank form with pypdf and rendering it in poppler works for every field, including the
radio and the en-dash dropdown value. Typed values come out in Helvetica, while the form and the
flattened sample use Bitter (disclosed).

## 3. Report honesty

- V: **yes**. Every claim I could check matches: the 17 field layers and 14 keys, each flag and
  MaxLen, the JS actions, the tooltip text (including the " *"), /Tabs /S, Helvetica for typed input,
  and the signature as a text field. The round-2 report's layer changes match a diff of the two
  `.vixl` files exactly: instagram and its label added, email widened 1300 → 2100 px, phone moved to
  the next row, the rows below moved 240 px, and the footer moved 170 px to end at y=3251. It also
  says plainly that the footer now sits inside only a 38 px margin.
- C: **yes** (2026-10-05). The en-dash workaround, cleared reportlab defaults, JS-only validation
  and the sample being drawn rather than flattened from the form are all stated accurately.

## 4. Round 2 (required `instagram` after Email; 30-minute slots; sample with 8:30–9:00 and @driftwoodquartet)

| | V (0.20.0) | C |
| --- | --- | --- |
| Result | 15 fields; instagram /Tx required, MaxLen 31, pattern validate script; widget order performer_name, email, instagram, phone, …; 6 options with en dashes, still required; sample flattened with @driftwoodquartet and 8:30–9:00, all visible | 15 fields; instagram /Tx required; same order; 6 options with en dashes; sample flattened, shows both values |
| Drift | Email widened to full width; Instagram + Phone on a new row; everything below moved down 240 px; footer moved down 170 px, so its text now ends 12 pt (0.17 in) from the bottom edge, close to many printers' unprintable margin | Only email narrowed, phone shifted, instagram added |
| Editability | **5**: the round-1 `.vixl` was edited in place with two operation batches; `vixl_check` caught the worst-case overflow of the first layout and the run re-laid out | **5**: 4 small script edits |
| Revision | **4**: everything asked is right, but the re-layout crowds the footer to the page edge on a form meant to be printed | **5** |

## 5. Changes since the Vixl 0.18.0 run

| | 0.18.0 (2026-10-05) | 0.20.0 (2026-10-06) |
| --- | --- | --- |
| Hard checks | 7/7 | 7/7 |
| Fidelity | 4 (blind 5; no email, range or date enforcement in the PDF) | 5 (email, 1–6 range and date enforced by PDF actions) |
| Craft | 4 | 5 (embedded font pair, cleaner hierarchy) |
| Report honest | yes | yes |
| Editability / revision | 5 / 5 | 5 / 4 (footer pushed to 12 pt from the edge) |

- The gaps noted on 0.18.0 are fixed: the fillable export writes validation and format actions,
  `max_length` works on the multiline field (pieces 300), and the page now declares `/Tabs /S`.
- Still true: the `signature` field kind can't take a fill value, so the run used a text field
  (allowed by the brief). Typed input is drawn in Helvetica, not the form's font.
- On round 1, V now matches C on fidelity (5) and beats it on craft (5 vs 4). C has the cleaner round 2.

## 6. Vixl issues seen (0.20.0)

- `vixl_check` accepted the round-2 footer at 12 pt (49 px at 300 dpi) from the bottom edge. Its
  safe margin is 38 px (about 0.13 in), which is smaller than most office printers' unprintable
  margin of about 0.25 in.
- Tooltips (/TU) built from labels keep the visual " *" marker, for example "Email *" and
  "Date * (YYYY-MM-DD)", so screen readers read "star".
- The fillable export's /DA uses Helvetica, so values typed in a viewer don't match the form's Bitter
  font or the flattened sample.
