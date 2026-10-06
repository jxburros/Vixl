# T03 · Print poster: judge notes

Lanes run: V, W (claude, claude-opus-5-5).

- **V (Vixl 0.20.0): re-run and judged 2026-10-06** by a claude-opus-5-5 judge subagent. Round-1 blind code QN2Q, round 2 UMJZ.
- **W: run and judged 2026-10-05.** Its scores and notes below are unchanged. Old blind codes: W=FH7F, round 2 LOUK.

For the 2026-10-06 blind look, W's deliverables were regenerated from its committed sources (`build.py`, `poster.html`, `art.html`) in a scratch copy outside the repo. The setup was Playwright 1.56 with the Chromium at `/opt/pw-browsers` and Ghostscript 10.02. The `fonts/` folder isn't committed, so Jost 400/500 and Cormorant Garamond Italic 500/600 were downloaded again from Google Fonts. The rebuilt files match W's report and the 2026-10-05 notes: caps kicker, 2×2 list, CMYK, boxes, and in round 2 the footer moved up. In that blind set W was F9TJ (round 1) and 883R (round 2). The blinding was partial: W's folder also holds `art.png`.

## 1. Blind scores (written before opening key.csv)

| Code | Fidelity | Craft | Reason |
| --- | --- | --- | --- |
| QN2Q (V, 2026-10-06) | 5 | 4 | Copy exact, with a single-column bulleted list. Clean flat vector lanterns with glow, a quay skyline and a lighthouse. The striped, blurred reflections are a little mechanical, close to clip art. DM Serif Display title over DM Sans. Solid, but plainer than W. |
| FH7F (W, 2026-10-05) | 4 | 5 | Rich lantern illustration with convincing broken reflections, and elegant type. The kicker is shown in all caps ("PORT ELLERY QUAY"), not as given. Highlights are a 2×2 bulleted grid. |

For calibration, the 2026-10-06 judge also scored the rebuilt W blind (F9TJ): fidelity 5, craft 4. The recorded W scores (4/5) stand. The fidelity 4 reflects the caps kicker, which the rule applied here also fails in hard check 8.

## 2. Hard checks (round 1)

Sources:

- `inspect_outputs.py` on the scratch copy
- `pdfinfo -box`, `pdfimages -list`, `pdffonts`, and `pdftotext -bbox`/`-layout`
- edges of the PDF rendered to CMYK at 72 dpi with Ghostscript `tiff32nc`
- the PDF rendered at 150 dpi and matched against the preview
- Pillow

| Check | V (0.20.0) | W |
| --- | --- | --- |
| One page, 11.25×17.25 in | PASS (810×1242 pt) | PASS |
| CMYK only, no RGB vector ops | PASS (14 DeviceCMYK images, each with a gray soft mask; 106 CMYK vector ops; no RGB or Gray painting) | PASS* (DeviceCMYK images; 16 CMYK vector ops; the one DeviceGray image (2946×782) is only the luminosity soft mask of the title glow, nothing is painted in it) |
| Raster ≥ 300 dpi | PASS (every image is 300×300 ppi; no page-wide raster; the largest is the 2600×1700 sky glow) | PASS (3375×5175, page-wide) |
| TrimBox and BleedBox | PASS (Trim [9 9 801 1233], Bleed = Media) | PASS (Trim [9 9 801 1233], Bleed = Media) |
| Artwork reaches the PDF edges | PASS (at 72 dpi every edge pixel carries ink, with a minimum total of 102 %; navy all round) | PASS |
| Text ≥ 38 px inside the 150 dpi preview | PASS (nearest is about 105 px, the "Presented by" line at the bottom; the sides are about 150 px) | PASS (nearest about 127 px) |
| `poster-preview.png` 1650×2550 RGB | PASS (RGB, 150 dpi, matches the PDF trim at an 18 px offset) | PASS (RGB) |
| Ten lines exact; highlights as a list | PASS (pdftotext matches all ten lines in mixed case; a true four-item "•" rich-text list) | FAIL: the kicker prints as "PORT ELLERY QUAY" (CSS `text-transform:uppercase`; the source string is exact, and pdftotext extracts caps). The list (2×2 bulleted grid) is fine. |
| **Total** | **8/8** | **7/8** |

\* DeviceGray appears in `image_colorspaces`, but only as an SMask group, so this is not colour content.

Extra V facts:

- Text is live vector type, with DM Sans and DM Serif Display embedded as subsets.
- Maximum total ink is about 230 % (Ghostscript at 30 dpi), under the 300 % limit set.
- The PDF Title metadata is "Port Ellery Quay", taken from the kicker.

## 3. Report honesty

- **V (2026-10-06): yes.** The files match the report:
  - layer counts (131 in round 1, 133 in round 2)
  - the boxes, DeviceCMYK only, every image at 300 ppi with a gray soft mask, and embedded subset fonts
  - the 18 px preview offset and RGB preview
  - the 38 px bleed rounding, now handled by scaling about 0.03 % instead of cropping
  - the soft-mask transparency (not PDF/X-1a), the ink limit with no ICC profile, and the auto-set PDF Title

  One number is wrong. It says "all text is at least about 290 px (about 0.97 in) inside the trim". The bottom "Presented by" line is about 0.70 in inside (about 105 px in the preview). The pass/fail result is the same.

  It also discloses that `vixl_check` could not measure the title's contrast. That is reproduced in section 5.
- **W: yes.** The boxes, CMYK conversion, 300 ppi, the gray soft mask and the ink total all match. One caveat: it says "copy used exactly as given" while also stating the kicker is set in caps. That is disclosed, but the claim doesn't hold for the printed text.

## 4. Round 2 (kicker → "Old Customs House Square", "Live brass band" → "Fire dancers at 8 pm", 1×1 in white "QR" square in the bottom-right of the safe area, same spec)

**QR square, measured in the preview:**

- V: white area x 1463–1611 and y 2363–2511, about 149×149 px, 38 px from the right and bottom trim.
- W: 149×149 px, 38 px from the right and bottom.

Both are correct, at 1 in and 0.25 in inside the trim. In the V PDF the square is paper white (CMYK 0/0/0/0).

**V (2026-10-06).** The edit was one atomic `vixl_operations_apply` batch on a copy of the source, dry-run first:

- `text-set` on the kicker and the list
- an `align center-x` to re-center the auto-sized kicker
- a white rectangle and a "QR" label centered on it

This time `text-set` kept the rich-text bulleted list, so no undo was needed.

Pixel diff of the round-1 and round-2 previews:

- The changed rows are only 145–193 (kicker), 2180–2229 (list line 4) and 2361–2513 (QR). They match the report's bands.
- Outside them, 155 anti-aliasing pixels next to the kicker differ, by at most 5 levels.
- The 150 dpi renders of the two PDFs show the same three bands.

The print spec is unchanged and all 8 hard checks still pass. Live vector text, the boxes and DeviceCMYK are kept. The PDF Title metadata changed to "Old Customs House Square" (see section 5). "QR" is navy in all four inks, not pure K, which is disclosed. **Editability 5, revision 5.**

**W (2026-10-05).**

- CSS edits and a rebuild; the boxes and CMYK are preserved.
- It moved the whole bottom block (date, list, footer) up about 100 preview px, which wasn't needed to avoid the QR: the footer and QR don't overlap horizontally.
- The QR letters are rich black (C72 M67 Y67 K88), and one Gray vector op appears.
- Both changes are disclosed. The kicker is still in caps.

**Editability 5, revision 4.**

## 5. Vixl product issues seen in the 0.20.0 run

- **The contrast check fails on some text layers.** `check_design(..., checks=["contrast"])` on `round2/poster.vixl` returns two warnings:
  - "Could not measure 'title': boolean index did not match indexed array along axis 1; size of axis is 2696 but size of corresponding boolean axis is 2694"
  - the same error for `qr-label` (axis 0, 98 vs 96)

  This is an off-by-2 mask shape mismatch in the measure path (`src/vixl/checks.py` around line 435, `top_level_contrast`/`measure`). The check still passes with 0 errors, so a real contrast problem on the title would go unreported. The agents worked around it with `vixl_measure`.
- **The PDF Title defaults to the first visible text layer.** It doesn't use the most prominent one (`src/vixl/pdf_export.py` lines 691–694). With `DisplayDocTitle` set, viewers show "Port Ellery Quay" in round 1 and "Old Customs House Square" in round 2, instead of "Harbor Lights".
- **The bleed still rounds to 38 px.** At 300 dpi the 0.125 in bleed becomes 38 px, so the canvas is 3376×5176. The export now scales it to an exact 810×1242 pt page (about 300.09 dpi in effect). That is harmless, but it is still not exact.
- **The default safe guide (`safe: 38`) is 0.125 in inside the trim**, half the 0.25 in this brief asks for. The round-2 agent noticed this and placed the QR square from the brief instead of the guide.

## 6. Changes since the Vixl 0.18.0 run (2026-10-05 → 2026-10-06, lane V)

| | 0.18.0 (GDUE / GIHH) | 0.20.0 (QN2Q / UMJZ) |
| --- | --- | --- |
| Hard checks | 6/8 | **8/8** |
| Fidelity / craft | 5 / 4 | 5 / 4 |
| Report honest | yes | yes (one margin figure overstated) |
| Editability / revision | 4 / 5 | **5** / 5 |

- **Gone:**
  - No TrimBox/BleedBox: they are now written.
  - RGBA preview: the PNG export now has `alpha="flatten"`, so the preview is RGB.
  - CMYK PDF fully rasterised, text included: the CMYK PDF now keeps vector text and shapes in DeviceCMYK, and only glows and reflections are 300 ppi CMYK images with soft masks.
  - The round-2 gotcha where `text-set` wiped the rich-text list: the list survived this time.
  - The bleed-crop workaround (cropping 1 px and losing the size metadata and guides): the export now scales to the exact page size.
- **Remain:**
  - the 38 px bleed rounding (now only a 0.03 % scale)
  - CMYK with no ICC profile shipped
  - live transparency instead of a flattened PDF/X
- **New or newly seen:** the contrast check crashes on the title and the QR label, and the PDF Title is taken from the kicker.
- **Look:** a different but equivalent design (DM Serif/DM Sans, flat lanterns with striped reflections, instead of Marcellus/Lato). Craft is unchanged at 4. W still has the richer illustration, but V now beats W on hard checks (8/8 against 7/8) and on revision (5 against 4).
