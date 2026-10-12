# T06 · Fillable PDF form — judge notes

Runs: claude-V (Vixl 0.26.0, re-run and judged 2026-10-12) and claude-C (reportlab + pypdf, run and
judged 2026-10-05). Judge: claude-opus-5-5 subagent each time. The C scores and notes are carried
over unchanged from 2026-10-05.

For the 2026-10-12 judging, C's deliverables were regenerated from its committed `make_form.py`
(round 1 and round 2) in a scratch copy outside the repo. Both scripts ran cleanly ("ok"), and the
outputs match the facts recorded on 2026-10-05 (14 and 15 fields, same flags, options, widget order,
/Tabs /R). V's committed PDFs and `.vixl` files were inspected as they are; `vixl check` was run only
on scratch copies.

## 1. Blind scores (written before opening key.csv)

2026-10-12 blind set. C is included only for calibration; its scores were not changed.

| Code | Round | Fidelity | Craft | Reason |
| --- | --- | --- | --- | --- |
| XFVA | r1 | 5 | 5 | Every key, label, header, footer and "We need:" group; en dashes; embedded Plus Jakarta Sans, navy/amber; sample fully visible, pieces on 3 lines. Nit: the signature value is set about twice the size of the other values |
| 36MI | r1 | 5 | 4 | Same coverage plus helper hints (max 80, 1 to 6, optional); plainer Helvetica (not embedded) |
| HGGK | r2 | 5 | 4 | Instagram to the right of Email in the same row, Phone alone on the next row (empty right half); 30-minute slots; footer kept in place, lower block tightened |
| G7KI | r2 | 5 | 4 | Instagram squeezed into the Email row (three up); 30-minute slots; nothing else moved |

Key: XFVA = claude-V, 36MI = claude-C, HGGK = claude-V/round2, G7KI = claude-C/round2.

No post-key adjustment. The blind scores for C match the stored ones (5/4).

Earlier blind sets, for the record: 2026-10-06 CF0G = claude-V on 0.20.0 (5/5); 2026-10-05 UIL4 =
claude-C (5/4), TBL6 = claude-V on 0.18.0 (5/4, lowered to fidelity 4 after the key because the PDF
enforced none of the email, range or date rules).

## 2. Hard checks (round 1)

V measured on 2026-10-12 with `inspect_outputs.py`, a pypdf dump of every widget (flags, /MaxLen,
/Opt, /TU, /DA, /AA actions, rects in /Annots order), a pypdf fill of the blank round-2 form rendered
with poppler, and pdftotext/renders of both samples. C as judged 2026-10-05, re-confirmed from the
regenerated files.

| Check | V (0.26.0) | C |
| --- | --- | --- |
| 14 fields, exact keys | PASS | PASS |
| Kinds | PASS: act_type /Btn radio (Ff 0xC002), states music/poetry/comedy/other; pieces multiline (Ff 0x1000); slot /Ch combo (Ff 0x20002); 5 checkboxes, on-state /Yes; signature is now a real /Sig field (allowed by the brief) | PASS: same flags |
| Required = exactly the 6 | PASS: Ff bit 2 only on performer_name, email, act_type, slot, signature, date | PASS; reportlab's default required checkboxes cleared |
| performer_name max_length=80 | PASS (extra, disclosed limits: phone 25, performers 1, pieces 300) | PASS |
| Dropdown options exact, en dashes | PASS: 7:00–7:45, 7:45–8:30, 8:30–9:15, 9:15–10:00 (U+2013) | PASS, en dashes written by pypdf after reportlab |
| widget_order = reading order | PASS: performer_name, email, phone, act_type, performers, slot (right of performers), needs_*, pieces, photo_consent, signature, date; page /Tabs /S | PASS, /Tabs /R |
| Sample: no fields, all values visible | PASS: no AcroForm, no /Annots; long name on one line at full size, pieces on 3 lines, phone empty, signature drawn | PASS |
| **Total** | **7/7** | **7/7** |

Extra V measurements: email has a validate script (`name@host`), performers has
`AFNumber_Keystroke/Format` plus a 1–6 validate script, date has `AFDate_KeystrokeEx("yyyy-mm-dd")`.
Tooltips (/TU) are now clean ("Email", "Date (YYYY-MM-DD)", no " *"). Typed values still come out in
Helvetica (/DA `/Helv 10.56 Tf`), while the form and the flattened sample use Plus Jakarta Sans
(disclosed). `vixl check` on a scratch copy passes with only the two waived full-bleed header shapes,
and the safe area is now 75 px (0.25 in).

## 3. Report honesty

- V: **yes**. Every claim I could check matches: 45 operations in `build-ops.json`, 17 field layers
  and 14 keys, each flag and MaxLen, the JS actions, the /Sig signature, /Tabs /S, Helvetica for
  typed input, no AcroForm or annotations in the sample. The round-2 report matches a diff of the two
  `.vixl` files exactly: 12 operations; instagram and its label added at x 1425 (900 px wide);
  email 1225 → 1125 px; phone moved to x 225, y 1295 and widened to 1125 px; act type to pieces moved
  down 255 px; the gaps around photo consent tightened from 90/110 px to 65 px; signature and date
  170 → 150 px tall; header and footer unchanged. It also notes that text extraction lists the
  Instagram value last (true; see section 6 for the cause).
- C: **yes** (2026-10-05). The en-dash workaround, cleared reportlab defaults, JS-only validation
  and the sample being drawn rather than flattened from the form are all stated accurately.

## 4. Round 2 (required `instagram` after Email; 30-minute slots; sample with 8:30–9:00 and @driftwoodquartet)

| | V (0.26.0) | C |
| --- | --- | --- |
| Result | 15 fields; instagram /Tx required, MaxLen 31, pattern validate script, /TU "Instagram handle"; widget order performer_name, email, instagram, phone, …; 6 options with en dashes, still required; sample flattened (no AcroForm, no annots) with @driftwoodquartet and 8:30–9:00, all visible | 15 fields; instagram /Tx required; same order; 6 options with en dashes; sample flattened, shows both values |
| Drift | Phone moved to its own row (empty right half); everything from act type to pieces moved down 255 px; photo-consent gaps tightened to 65 px and signature/date boxes 20 px shorter so the footer could stay put (footer text still ends 0.62 in from the bottom edge; signature line 70 px above the footer rule). The new label and field were appended above the footer in the stack, so the content stream (and an untagged-PDF reader) gives "Instagram handle *" after the footer text | Only email narrowed, phone shifted, instagram added |
| Editability | **5**: the round-1 `.vixl` was edited in place with one 12-operation batch; the worst-case form check caught the first Instagram width and the run widened the box instead of loosening the rule | **5**: 4 small script edits |
| Revision | **4**: everything asked is right and the footer stays put, but the lower block was compressed and the static text order is now wrong (Vixl's own accessibility check flags it; the default check doesn't run it) | **5** |

## 5. Changes since earlier Vixl runs

| | 0.18.0 (2026-10-05) | 0.20.0 (2026-10-06) | 0.26.0 (2026-10-12) |
| --- | --- | --- | --- |
| Hard checks | 7/7 | 7/7 | 7/7 |
| Fidelity / craft | 4 (blind 5; no email, range or date enforcement in the PDF) / 4 | 5 / 5 (embedded Work Sans + Bitter) | 5 / 5 (embedded Plus Jakarta Sans; real /Sig signature) |
| Report honest | yes | yes | yes |
| Editability / revision | 5 / 5 | 5 / 4 (footer pushed to 12 pt from the edge) | 5 / 4 (footer kept; lower block compressed, Instagram label out of content order) |

The 0.20.0 round-2 problem is gone: the safe area is now 75 px (0.25 in), and the round-2 edit kept
the footer where it was instead of pushing it toward the edge. Two gaps listed on 0.20.0 are fixed:
the tooltips no longer carry the visual " *", and the `signature` field kind now flattens a value, so
the form has a real /Sig field while the sample still shows the signature. Still open: typed input is
drawn in Helvetica rather than the form's font. Round 1 is level with 0.20.0 (7/7, 5/5) and still
ahead of C on craft; C keeps the cleaner round 2. Effort on 0.26.0: 2.5 min / 22 tool calls (r1),
2.4 min / 25 tool calls (r2).

## 6. Vixl issues seen (0.26.0)

- The fillable export's /DA is still `/Helv 10.56 Tf`, so values typed in a viewer (or filled with
  pypdf) don't match the form's Plus Jakarta Sans or the flattened sample.
- New layers land at the top of the stack, after the footer, and export writes text in stack order.
  In round 2, `pdftotext -raw` on both PDFs gives "Return this form …" before "Instagram handle *".
  `vixl check --checks accessibility` reports it ("Exports read 'footer' before 'instagram-label'"),
  but the default `vixl_check` set (bounds … codes, including `form`) doesn't run `accessibility`, so
  the run never saw the warning.
- A flattened `signature` field with no size set draws the value at about twice the size of the other
  values (pdftotext word boxes 26 pt tall against 13 pt for the date), so the signature looks like the
  loudest item in the lower half.
