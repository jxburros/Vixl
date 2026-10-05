# T09 · One campaign, six sizes: judging (claude-code-subagent judge, 2026-10-05)

Runs: `claude-V` (Vixl MCP) and `claude-W` (web code + Chromium), each with `round2/`.

## 1. Blind scores (written before opening `blind/T09/key.csv`)

| Code | Fidelity | Craft | Reason |
| --- | --- | --- | --- |
| AVLB | 5 | 4 | All copy exact, every size laid out for its shape, sun + layered-wave motif consistent; clean but somewhat generic; back wave is an off-palette navy/sea-foam mix |
| ILEV | 5 | 4 | All copy exact (line 2 wraps with a dangling "·"), display serif + pill CTA + steaming lamp with halo rings, richer look; a faint ring passes behind the story headline; leaderboard wave chip ends in a hard edge |
| M5Z5 | 5 | 4 | (round-2 of the AVLB look) new headline and item correct everywhere, layouts intact |
| TT4F | 5 | 4 | (round-2 of the ILEV look) new copy correct; on the square the headline colon now runs into the halo rings |

Key: AVLB = claude-V, ILEV = claude-W, M5Z5 = claude-V/round2, TT4F = claude-W/round2.

## 2. Hard checks (round 1)

Inspector: all 12 PNGs have exact sizes (V RGBA with `.vixl` sources; W RGB with `campaign.html` + `render.py`).
Text checked from the `.vixl` text layers (V) and `campaign.html` (W), plus visual inspection. Story zones checked by cropping y 0–250 and 1670–1920.

| Check | claude-V | claude-W |
| --- | --- | --- |
| Six files at exact sizes | PASS: 1080², 1080×1920, 1600×900, 1920×1005, 728×90, 600×200 | PASS: same |
| Copy exact on 4 large; small two carry headline + line 3 | PASS: all four lines verbatim incl. "·" (U+00B7) and "Café"; leaderboard/email = headline + line 3. Note: adds an extra "TIDEWICK CAFÉ" eyebrow label on every size (disclosed) | PASS: verbatim; line 2 wraps with "·" at line end on square/X/FB (disclosed); no added copy |
| Story: no text in top/bottom 250 px | PASS: text spans y≈380–1387; only lamp glow and waves in zones | PASS: text y≈741–1549; only halo rings, stars and waves in zones |
| Nothing stretched/letterboxed | PASS: lamp is a true circle in all six; per-size layouts | PASS: per-size layout functions; circles round |
| One family (palette, type, motif) | PASS: Young Serif + Rubik, lamp + 3 wave bands in all six (one tint band) | PASS: Fraunces + DM Sans, lamp/steam/halo + 4 wave bands in all six (one darker navy band) |
| Leaderboard readable at 100 % | PASS: ~29 px headline, ~13 px date line, good contrast | PASS: 29 px headline, 14 px date line |
| **Total** | **6/6** | **6/6** |

## 3. Report honesty (round 1)

- **claude-V: yes.** File list, fonts, text extents (380–1387), the tint band, the added label and the 320 px thumbnail warnings all match the files.
- **claude-W: yes.** Sizes, text extents, extra dark-navy band, trailing "·" wraps and hard-edged leaderboard waves all disclosed and accurate. (Halo rings are amber at low opacity, which it describes.)

## 4. Round 2 (headline "Winter Menu: now pouring"; "Spiced honey cortado")

Pixel diff r1→r2 (fuzz 2 %): every changed region is confined to the text block in both lanes; motif, background and waves are untouched.

- **claude-V (editability 5, revision 5).** Copied the six `.vixl` files and edited the existing `headline` (rich-text) and `menu` (text-set) layers in place; ~3 min. To keep margins, the menu line was shrunk 33→31 px (square) and 34→32 px (story) and the email headline 38→34 px; all disclosed. Correct copy in all six (leaderboard/email have no menu line in r1 either). New thumbnail-legibility warning at 9.2–9.5 px for the shrunk menu line is noted in its report. Story text still outside the zones. Nothing else moved.
- **claude-W (editability 5, revision 4).** Two-constant `sed` edit of `campaign.html` plus the email headline; re-render; added a nowrap span after seeing a bad wrap. Correct copy in all six, layout numbers unchanged. Collateral: the wider "Winter Menu:" line now collides with the lamp's halo rings on the square (colon overlaps the outer rings at x≈720–760, y≈130–190) and still crosses the ring in the story; the report says it looked at all renders but does not mention this. Minor, low-contrast, but a new collision.

## Summary

| Lane | Hard | Fid | Craft | Honest | Edit | Rev |
| --- | --- | --- | --- | --- | --- | --- |
| V | 6/6 | 5 | 4 | yes | 5 | 5 |
| W | 6/6 | 5 | 4 | yes | 5 | 4 |
