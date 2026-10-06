# T10 round 2: Vixl lane (claude-V)

Requested changes, applied to all three deliverables: a little warmer, slightly less contrast, caption changed to "Port Ellery, October evening".

All editing was done in Vixl through its MCP tools. Python was used only to read the exported files and compare statistics. Nothing outside `round2/` was changed by this round: the round-1 `.vixl` files were copied into `round2/` with `cp`, and every edit was made on those copies.

## Files (same names as round 1)

| File | Size | Notes |
| --- | --- | --- |
| `coast-edited.jpg` | 1556 x 1002, JPEG q95 | Corrected photo, now warmer and softer |
| `coast-instagram.jpg` | 1080 x 1350, JPEG q92 | Same 4:5 crop as round 1 |
| `coast-caption.png` | 1600 x 900, PNG RGB | Same crop and shade, new caption text |
| `coast-edit.vixl` | | Editable master |
| `coast-instagram.vixl`, `coast-caption.vixl` | | Link layers now point at `round2/coast-edit.vixl`, not the round-1 master |

## How

1. **Warmth and contrast, once, in the master** (`round2/coast-edit.vixl`, layer `photo`). Two non-destructive effects were appended after the existing denoise, white-balance LUT, levels and gamma:
   - `temperature` 250: adds about +6 to red and subtracts about 6 from blue (Vixl's temperature is an additive R+/B- shift of value/10000).
   - `contrast` -12: contrast factor 0.88, pulling tones about 12% toward the mean.
   I first tried `temperature` 0.15 and saw it had almost no effect (scale is about 100 = visible), so I changed it to 250 with `effect-set`. Both effects stay editable and can be turned off.
2. **Derived files.** Because the Instagram and caption documents are live `link` layers, I only had to repoint each link (`link` operation, `source` = `round2/coast-edit.vixl`). Both inherit the new grade automatically. The crops are unchanged.
3. **Caption.** `text-set` on layer `caption` changed the text to "Port Ellery, October evening". Font, size (DM Serif Display 64 px), colour, shadow and placement (80 px from the left, 72 px from the bottom) are unchanged. The line is now 798 px wide instead of 731, so it ends at about x=878, just left of the rock under the figure.
4. **Checks.** `vixl_check` on the caption document passed with no issues (contrast, overlap, bounds, legibility, links). I compared the master against round 1 in a side-by-side preview and previewed the caption layout. I exported all three files with `vixl_export_batch` using the round-1 formats and quality settings.

## Measured result (round 1 → round 2)

| File | Mean RGB | Mean R−B | Luma std (contrast) | Luma p1 / p99 |
| --- | --- | --- | --- | --- |
| coast-edited.jpg | (88, 53, 70) → (89, 53, 62) | 17.8 → 27.3 | 52.6 → 46.4 (−12%) | 1.6/216 → 8/197 |
| coast-instagram.jpg | (101, 64, 74) → (101, 63, 66) | 26.5 → 34.7 | 60.5 → 53.3 (−12%) | 0.3/223 → 6/203 |
| coast-caption.png | (95, 57, 70) → (95, 56, 62) | 25.6 → 32.6 | 55.6 → 50.2 (−10%) | 0.8/215 → 5/197 |

Every image is warmer: blue drops by about 8 levels and red holds or rises slightly. Each has about 10–12% less tonal spread. Blacks lift a few levels, so the silhouettes are very dark brown instead of pure black, and highlights come down about 20 levels. The image still reads as dusk.

## Notes

- I kept the amounts small to match "a little" and "slightly". If you want more of either, change one number in the master (`temperature` or `contrast` effect on `photo`), and both derived files follow when re-exported.
- The temperature shift is additive, so it also warms the deepest shadows a little. That is part of the softer look.
