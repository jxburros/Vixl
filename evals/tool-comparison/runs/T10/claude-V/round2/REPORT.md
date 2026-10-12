# T10 round 2: warmer, softer, new caption (lane V, Vixl via MCP)

Requested: a little warmer, slightly less contrast, caption "Port Ellery, October evening", on all three deliverables.
All editing was done with the Vixl MCP tools. A short read-only PIL script compared round 1 and round 2 statistics.
Nothing outside `round2/` was changed. The fixture `coast-raw.jpg` is untouched (sha256 still `86ec0e7c…cc7a4c`).

## How

1. I copied the three round-1 `.vixl` files into `round2/`. The two derived documents link to `coast.vixl` by a relative path, so in `round2/` they pick up `round2/coast.vixl`, not the round-1 master. Vixl reported those links as stale once the master changed, which confirms the link points at the round-2 master.
2. **Master (`coast.vixl`, layer `photo`).** I added two non-destructive effects at the end of the existing stack. The round-1 corrections (denoise, white-balance, levels, curves, the −2.2° rotation and the crop) are unchanged:
   - `temperature` amount **22**: a warmer white point. Black stays black.
   - `contrast` amount **−12**: contrast is lowered around the layer average.
   The two grade effects are separate from the cast correction, so either one can be tuned or switched off later. I first tried temperature 15, measured the result, and raised it to 22 because 15 was barely visible.
3. **Instagram (`coast-instagram.vixl`).** I ran `link-refresh` on the `photo` link layer. The crop and fit are the same as round 1.
4. **Caption card (`coast-caption.vixl`).**
   - I ran `text-set` on `caption`, changing it to "Port Ellery, October evening". The font, size, colour and position are unchanged. The box width grew from 665 to 728 px.
   - I updated the attached `caption` test suite so its text rule expects the new wording.
   - I refreshed the photo link.
5. I exported all three with `vixl_export_batch`: both JPEGs at q95 and the PNG, at the same sizes as round 1.

## Result (measured on the exported files)

| File | Mean RGB, round 1 → round 2 | R/B ratio (warmth) | Luma std. dev. (contrast) |
| --- | --- | --- | --- |
| `coast-edited.jpg` 1512×1008 | (91.5, 55.6, 74.3) → (89.6, 55.2, 69.2) | 1.232 → 1.294 | 55.9 → 49.6 (−11 %) |
| `coast-instagram.jpg` 1080×1350 | (103.7, 66.1, 78.4) → (100.7, 64.6, 72.7) | 1.323 → 1.386 | 63.3 → 56.2 (−11 %) |
| `coast-caption.png` 1600×900 | (103.0, 62.1, 76.3) → (99.6, 60.6, 70.7) | 1.350 → 1.409 | 57.9 → 52.2 (−10 %) |

On the master, the red 5th–95th percentile spread narrowed from 6–237 to 12–221. The deepest blacks now sit at about 7 instead of 0, and the brightest highlight drops from 255 to 232. That is the expected side effect of lowering contrast.

## Checks on the caption card

- `vixl_check`: passed. There were no fix or review findings, only the two informational notes about the scrim bleeding off the edge, which is intentional.
- `caption` suite: 3 of 3 rules pass (contrast ≥ 4.5, at least 48 px inside the canvas, contains "Port Ellery, October evening").
- `vixl_measure` caption contrast: minimum 13.9:1, mean 16.7:1. Round 1 was 14.7:1 and 17.0:1; the slight drop comes from the lifted shadows.

## Notes

- "A little" and "slightly" are judgment calls. Both changes are deliberately modest (about 5 % on R/B and about 10 % on luma spread). To go further, raise `temperature` or make `contrast` more negative on `photo` in `round2/coast.vixl`, then re-export. Both derived files follow through their links.
- The caption PNG is 1.8 MB. Vixl warns that some messaging apps recompress files that large. I kept PNG to match the round-1 file name.
