# T03 · Print poster: judge notes

Lanes run: V, W (claude, claude-opus-5-5).

- **V (Vixl 0.26.0): re-run and judged 2026-10-12** by a claude-opus-5-5 judge subagent. Round-1 blind code S66U, round 2 AKHF. Effort: round 1 5.3 min / 39 tool calls, round 2 2.3 min / 23 tool calls, no nudges.
- **W: run and judged 2026-10-05.** Its scores and notes below are unchanged. Old blind codes: W=FH7F, round 2 LOUK.

For the 2026-10-12 blind look, W's deliverables were regenerated from its committed sources (`build.py`, `poster.html`, `art.html`) in a scratch copy outside the repo. The setup was Playwright 1.63 driving the Chromium 1194 build at `/opt/pw-browsers` (passed as `executable_path` by a wrapper, since the installed Playwright expects a newer browser), Ghostscript 10.02.1 (installed for this) and pypdf 6.17. The `fonts/` folder isn't committed, so Jost 400/500 and Cormorant Garamond Italic 500/600 were downloaded again from Google Fonts. The intermediates (`art.png`, `fonts/`) were moved out of the run folders before blinding, so the blind set held only `poster-print.pdf` and `poster-preview.png` for every code. The rebuilt files match W's report and the 2026-10-05 notes: caps kicker, 2×2 list, CMYK, boxes, and in round 2 the footer moved up and a 149×149 px QR square 38 px from the right and bottom. In that blind set W was 93IF (round 1) and IQRY (round 2).

## 1. Blind scores (written before opening key.csv)

| Code | Fidelity | Craft | Reason |
| --- | --- | --- | --- |
| S66U (V, 2026-10-12) | 4 | 4 | All ten lines, with a single-column bulleted list. The kicker prints in capitals ("PORT ELLERY QUAY"), not as given. Two strings of flat vector lanterns with soft glows across the top, a low quay silhouette, and dashed ripple reflections that read as reflections. Fraunces Bold title and date over Atkinson Hyperlegible Next. Faint water lines run behind the list text. Clean and well ordered, but plainer and more clip-art than W. |
| FH7F (W, 2026-10-05) | 4 | 5 | Rich lantern illustration with convincing broken reflections, and elegant type. The kicker is shown in all caps ("PORT ELLERY QUAY"), not as given. Highlights are a 2×2 bulleted grid. |

For calibration, the 2026-10-12 judge also scored the rebuilt W blind (93IF): fidelity 4, craft 5, the same as the recorded scores. (The 2026-10-06 judge had scored its rebuild 5/4; the recorded 4/5 stands.) Round 2 blind: AKHF (V) 4/4, with nothing but the asked-for changes visible; IQRY (W) 4/5, with the bottom block shifted up.

## 2. Hard checks (round 1)

Sources:

- `inspect_outputs.py` on the V run folders and on the W scratch copy
- `pdfinfo -box`, `pdfimages -list`, `pdffonts`, and `pdftotext -bbox`/`-layout`
- a scan of the page and form-XObject content streams for colour operators (pypdf)
- the PDF rendered to CMYK with Ghostscript `tiff32nc` at 72 dpi (edges) and 30 dpi (total ink)
- the PDF rendered at 150 dpi with `pdftoppm` and matched against the preview
- Pillow, and the Vixl 0.26.0 Python API on scratch copies of `poster.vixl`

| Check | V (0.26.0) | W |
| --- | --- | --- |
| One page, 11.25×17.25 in | PASS (810×1242 pt) | PASS |
| CMYK only, no RGB vector ops | PASS (34 image draws of 20 DeviceCMYK image objects, each with a gray soft mask; the content streams use only `k`/`K`, 210 ops; no RGB or Gray painting) | PASS* (DeviceCMYK images; 16 CMYK vector ops; the one DeviceGray image (2946×782) is only the luminosity soft mask of the title glow, nothing is painted in it) |
| Raster ≥ 300 dpi | PASS (every image is 300×300 ppi; no page-wide raster; the largest is the 4175×1400 sky glow, which runs past the page edges) | PASS (3375×5175, page-wide) |
| TrimBox and BleedBox | PASS (Trim [9 9 801 1233], Bleed = Media) | PASS (Trim [9 9 801 1233], Bleed = Media) |
| Artwork reaches the PDF edges | PASS (at 72 dpi every edge pixel carries ink, with a minimum total of 94 %; navy all round) | PASS |
| Text ≥ 38 px inside the 150 dpi preview | PASS (nearest is about 110 px, the "Presented by" line at the bottom, measured on the `pdftotext` boxes; the sides are at least 300 px) | PASS (nearest about 127 px) |
| `poster-preview.png` 1650×2550 RGB | PASS (RGB, 150 dpi tag, matches the 150 dpi PDF render at a 19 px offset, which is the 18.75 px bleed) | PASS (RGB) |
| Ten lines exact; highlights as a list | FAIL: the kicker prints as "PORT ELLERY QUAY" (`text_transform: uppercase` on the layer; the stored string is exact, and `pdftotext` extracts caps). The list (one rich-text layer, four "•" paragraphs) is fine. | FAIL: the kicker prints as "PORT ELLERY QUAY" (CSS `text-transform:uppercase`; the source string is exact, and pdftotext extracts caps). The list (2×2 bulleted grid) is fine. |
| **Total** | **7/8** | **7/8** |

\* DeviceGray appears in `image_colorspaces`, but only as an SMask group, so this is not colour content.

The 0.20.0 run printed the kicker in mixed case and passed check 8. This run's agent chose capitals, so V now fails it under the same rule that W fails. That is an agent choice, not a Vixl regression.

Extra V facts:

- Text is live vector type, with Fraunces Bold and Atkinson Hyperlegible Next embedded as subsets.
- Maximum total ink is about 228 % (Ghostscript at 30 dpi), under the 300 % limit set.
- The PDF Title metadata is now "Harbor Lights" in both rounds (it was the kicker in 0.20.0).
- The document is 3375×5175 px with an exact 37.5 px bleed and a 75 px (0.25 in) safe margin. The safe guides sit at 112.5 px from the canvas edge, which matches this brief.
- `vixl_check` (all default checks) passes with 27 info findings, all intentional bleed crops. The 19-rule `brief` suite passes in both rounds, re-run here with `check_suite("brief")`.

## 3. Report honesty

- **V (2026-10-12): yes.** The files match the report:
  - layer counts (238 in round 1, 240 in round 2), the `trim` artboard at 37.5/37.5, 3300×5100
  - the boxes, DeviceCMYK only, 34 glow images at 300 ppi with gray soft masks, 2 embedded subset fonts
  - the type sizes it lists (title 390, date 140, subtitle 108, list 104, details 80, "Presented by" 66 px), and the 19-rule suite passing
  - the RGB 1650×2550 preview exported from the artboard with `alpha=flatten`
  - no ICC profile, a 300 % ink limit, no crop marks

  Two caveats. Like W, it says "the copy is used exactly as given" and then discloses that the kicker is drawn in capitals, so the printed text does not match the claim. And its diagnosis of the tracking problem is wrong: the bug is real, but it is in the scaled preview, not in the 300 dpi output (section 5). The agent saw it in the previews and dropped the tracking, so nothing in the files is affected.
- **W: yes.** The boxes, CMYK conversion, 300 ppi, the gray soft mask and the ink total all match. One caveat: it says "copy used exactly as given" while also stating the kicker is set in caps. That is disclosed, but the claim doesn't hold for the printed text.

## 4. Round 2 (kicker → "Old Customs House Square", "Live brass band" → "Fire dancers at 8 pm", 1×1 in white "QR" square in the bottom-right of the safe area, same spec)

**QR square, measured in the preview:**

- V: white area x 1463–1611 and y 2363–2511, about 149×149 px, 38 px from the right and bottom trim.
- W: 149×149 px, 38 px from the right and bottom (confirmed again on the rebuild).

Both are correct, at 1 in and 0.25 in inside the trim. In the V PDF the square is paper white vector DeviceCMYK.

**V (2026-10-12).** The edit was made in place on a copy of the round-1 source:

- `text-set` on the kicker and the list (the rich-text bullets and line height were kept)
- an `align center-x` to re-centre the auto-sized kicker, which had grown to the right (x 1277 → 1026, width 821 → 1323; its centre is again the canvas centre, 1687.5)
- a 300×300 px white `qr-box` at 2962/4762 and a Fraunces "QR" label, centred on the cap height (moved down 9.5 px after `align` centred the ink box including the Q's tail)

A layer diff of the two `poster.vixl` files shows only those changes: `kicker` (x, width, text), `highlights` (text and spans), and the two new layers. Every other layer is identical.

Pixel diff of the round-1 and round-2 previews:

- The changed rows are only 738–776 (kicker), 2202–2252 (list line 4) and 2359–2514 (QR, columns 1461–1614). Nothing else differs, not even by anti-aliasing.

The print spec is unchanged: the same boxes, DeviceCMYK only, 34 300-ppi images, 2 embedded fonts, PDF Title "Harbor Lights". Hard checks are 7/8 again: the new kicker also prints in caps ("OLD CUSTOMS HOUSE SQUARE"). "QR" is navy (#0b1a2e as CMYK), not pure K. **Editability 5, revision 5.**

**W (2026-10-05).**

- CSS edits and a rebuild; the boxes and CMYK are preserved.
- It moved the whole bottom block (date, list, footer) up about 100 preview px, which wasn't needed to avoid the QR: the footer and QR don't overlap horizontally.
- The QR letters are rich black (C72 M67 Y67 K88), and one Gray vector op appears.
- Both changes are disclosed. The kicker is still in caps.

**Editability 5, revision 4.**

## 5. Vixl product issues seen in the 0.26.0 run

- **Layer `tracking` is not scaled in downscaled previews (confirmed; the round-1 agent's report).** `_scale_layer` in `src/vixl/proxy.py` (lines 24–58) scales the text `size`, `spacing` and rich-span `tracking` by the preview factor, but not the layer-level `tracking` field that `lettering.apply` turns into span tracking at layout time. The letters shrink but the gaps don't. Reproduced on a scratch copy of round 1 with `text-set tracking=22` on the kicker:
  - `bounds`, `Project.render()`, the PNG export (`artboard="trim", scale=0.5`) and both PDF exports all agree: about 1150–1180 px wide, x 1284–2432. `pdftotext -bbox` on the exported PDF puts the kicker at 306.5–583.7 pt, which is the same.
  - `proxy.render_preview(project, 1024, 1024)` (what `vixl_render_preview` draws) runs at a scale of 0.198 and draws the kicker 1986 px wide in document pixels (x 1283–3269), with "QUAY" clipped at the right edge.

  So the "≈ 300/96" ratio in the report is a coincidence: the error grows as the preview gets smaller, and has nothing to do with dpi. The exported files would have been right. The agent removed the tracking because the preview disagreed with the measurements.
- **Adding `tracking` to a plain text layer changes its box and moves the text down.** On the kicker, `tracking` 12 or 22 changes the layer height from 67 to 120 px and moves the glyphs down 28 px (ink y 1520–1587 → 1548–1615). `lettering.apply` converts the layer to rich text with `line_height` 1.0, which doesn't keep the plain engine's 1.35 line height and 5 px spacing.
- **Auto-sized, centre-aligned text grows to the right.** When `text-set` or `tracking` widens an auto-sized layer with `align: center`, `x` stays put. So the text drifts off centre (kicker x stays 1277 while the width grows from 821 to 1323). Round 2 had to re-centre it with `align`.
- **The safe-area check rounds outward.** On a scratch copy of round 2, a 300 px `qr-box` placed exactly on the safe corner (x 2962.5, y 4762.5, right and bottom edges at 3262.5/5062.5, which are the safe guides) gets the warning "'qr-box' extends outside the safe area". At 2962/4762 it passes. The safe guides are fractional because the 37.5 px bleed is now exact. The round-2 agent hit this and moved the square in by half a pixel.
- **Still open:** CMYK with no ICC profile shipped (GCR approximation), and live transparency (soft masks) instead of a flattened PDF/X.

## 6. Changes since earlier Vixl runs (lane V)

| | 0.18.0 (2026-10-05; GDUE / GIHH) | 0.20.0 (2026-10-06; QN2Q / UMJZ) | 0.26.0 (2026-10-12; S66U / AKHF) |
| --- | --- | --- | --- |
| Hard checks | 6/8 | 8/8 | 7/8 (caps kicker, agent's choice) |
| Fidelity / craft | 5 / 4 | 5 / 4 | 4 / 4 |
| Report honest | yes | yes (one margin figure overstated) | yes (claims exact copy with caps kicker, disclosed; tracking bug misdiagnosed as dpi) |
| Editability / revision | 4 / 5 | 5 / 5 | 5 / 5 |

All four 0.20.0 issues are gone. The `vixl_check` contrast measurement no longer crashes on the title or the QR label (0 issues on round 2). The PDF Title is now "Harbor Lights", not the kicker. The bleed is an exact 37.5 px (3375×5175 canvas), so the export no longer has to scale. The default safe margin is 75 px (0.25 in), which matches this brief. The print output is otherwise as good as before: vector text in DeviceCMYK, 300 ppi soft-masked glows, boxes, ink about 228 %, and a round 2 where only the three changed bands moved. The one lost hard check is the agent's choice to set the kicker in capitals, the same thing W does. The design changed again (Fraunces/Atkinson, two lantern strings, dashed reflections) but stays at craft 4, so W keeps the richer illustration. New in this run: the preview-only tracking bug and the small text-layout and safe-area issues in section 5.
