# T10 Photo correction — lane C (claude-C)

All outputs were made by one Python script, `edit_coast.py` (OpenCV + NumPy + Pillow), which reads
`evals/tool-comparison/fixtures/coast-raw.jpg` and never writes to it (the fixture is unchanged per git;
md5 0adf9cb287cbfd00da4750dad81f245a). Re-running `python3 edit_coast.py` regenerates every file.

## Files
| File | Size | How it was made |
| --- | --- | --- |
| `coast-edited.jpg` | 1509 × 1005, JPEG q95 | full pipeline below |
| `coast-instagram.jpg` | 1080 × 1350, JPEG q95 | crop box (578, 0, 1382, 1005) of coast-edited (804 × 1005, 4:5, full height), Lanczos upscaled ×1.343 |
| `coast-caption.png` | 1600 × 900, PNG | crop box (0, 78, 1509, 927) of coast-edited (16:9, full width, vertically centred), Lanczos upscaled ×1.060, then gradient + caption |
| `edit_coast.py` | — | editable source; all adjustment amounts are constants at the top |

## Problems found and corrections applied (in order)
1. **Noise** (visible grain in flat sky; high-pass std in a sky patch 3.96 in raw): OpenCV
   `fastNlMeansDenoisingColored`, h=8 (luma), hColor=10, template 7, search 21. Applied on the raw before any
   other step. Sky-patch high-pass std drops to ~0.55. Water ripple texture is kept.
2. **Tilted horizon**: measured by fitting a line to the sky/sea edge (x 600–1585) — slope 0.0381, i.e. the horizon
   fell ~2.2° to the right (independent fit of the headland/water edge gave ~2.2° too). The raw also had black
   wedge borders from the tilt. Rotated **2.2° counter-clockwise** about the centre (Lanczos). After correction the
   detected horizon sits at row 609 across the whole width (±1 px) and the headland/water edge at row 613 everywhere.
3. **Crop for leveling only**: largest centred rectangle with the original 3:2 aspect that contains no empty/black
   wedge pixels (computed from the rotation geometry) minus a 2 px safety margin: x=45, y=31, 1509 × 1005
   (94.3 % of the linear size). Corners checked: no black left.
4. **Color cast** (raw channel means R 62 / G 42 / B 50 — strong magenta/red cast, green suppressed): gray-world
   gains measured on mid-tones (luma 0.12–0.85, excludes black land and the sun), then applied at 50 % strength to
   keep the warm sunset mood. Final gains: **R × 0.892, G × 1.099, B × 1.061**.
5. **Exposure** (underexposed; raw 99th percentile only ~185, median ~41): levels stretch on luma with black point at
   the 0.5th percentile (0.0054 ≈ 1.4/255) and white point at the 99.7th percentile (0.643 ≈ 164/255), then
   **gamma 0.80** (mid-tone lift). Output median luma rises from ~41 to ~78; the sun core clips as it naturally would.
6. **Saturation** × 1.05 (HSV S channel) — mild, to recover colour after the cast removal.

Nothing was painted, added, removed or moved; only global tone/colour, denoise, rotation and crops.

## Instagram crop
4:5 at full height (804 px wide), horizontal centre at 65 % of the width: keeps the sun, sun glitter, the figure
and the rock, with the horizon at ~61 % height. The lighthouse/headland (left 37 % of the frame) cannot fit a 4:5
crop together with the sun and figure, so it is left out; the centre was chosen so no sliver of the headland tip
touches the left edge. One bird remains in frame.

## Caption image
16:9 crop, then a dark gradient overlay: alpha = 0.72 × ((y − 0.55·H)/(0.45·H))^1.5 × clamp(1.15 − x/W, 0.35, 1),
i.e. darkest in the bottom-left, fading to zero above 55 % height and lighter toward the right. Text
"Port Ellery at golden hour" in DejaVu Serif 64 px, colour #FFF6E8, with a 2 px offset soft black shadow (alpha 110),
left margin 72 px, bottom margin 72 px; text bounding box (72, 765)–(917, 828).

## Deviations / uncertainties
- Both derived images are **upscaled** from the corrected photo (Instagram ×1.34, caption ×1.06) because the
  corrected photo is only 1005 px tall / 1509 px wide; the source resolution does not allow 1350 px / 1600 px
  natively.
- "Full resolution" for coast-edited means no resampling beyond the rotation; the crop reduces it from 1600 × 1067
  to 1509 × 1005, which is what removing the tilt wedges requires.
- The rotation angle is a measurement (2.18°–2.24° depending on edge used); 2.2° was chosen and the result verified
  level to within 1 px over 1500 px (< 0.04°).
- Gray-world white balance at 50 % is a judgement call; a full correction would neutralise the sunset too much.
- Light residual speckle remains in the darkest water at bottom-left (only visible when brightened strongly).
- Font: DejaVu Serif (system font; no font choice in the brief).

## Timing
Start: Mon Oct  5 22:21:54 UTC 2026 — End: Mon Oct  5 22:24:30 UTC 2026. Tool calls: 20.
