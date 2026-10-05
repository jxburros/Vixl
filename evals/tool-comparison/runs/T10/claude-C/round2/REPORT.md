# T10 round 2 — lane C (claude-C)

Requested changes: a little warmer, slightly less contrast, caption changed to "Port Ellery, October evening",
applied to all three files.

## How
I copied `../edit_coast.py` to `round2/edit_coast.py` and edited only the copy, then re-ran it from the untouched raw
(`fixtures/coast-raw.jpg`, md5 0adf9cb287cbfd00da4750dad81f245a, unchanged). Nothing outside `round2/` was modified.
Edits in the copy:
1. `SRC` path gets one more `../` because the script now lives one folder deeper.
2. **Warmth** (new constants `WARM_R, WARM_G, WARM_B = 1.04, 1.01, 0.94`): per-channel gains applied right after
   the round-1 levels + gamma 0.80 step, before saturation. Red +4 %, green +1 %, blue −6 %.
3. **Contrast** (new constant `CONTRAST = 0.90`): after the warmth step, every channel is pulled toward the image's
   mean value (pivot 0.379 ≈ 97/255): `f = pivot + 0.90 × (f − pivot)`. That's a 10 % reduction.
4. The caption text is now `'Port Ellery, October evening'`. Font, size (DejaVu Serif 64 px), colour #FFF6E8, shadow,
   72 px left/bottom margins and the gradient are unchanged. The new text box is (72, 765)–(990, 828), 73 px wider
   than before because the text is longer.

The other round-1 settings are unchanged: denoise, the 2.2° rotation, the crop (1509 × 1005), the gray-world WB gains
R × 0.892 / G × 1.099 / B × 1.061, the levels, saturation × 1.05, the Instagram crop box (578, 0, 1382, 1005) and the
caption crop box (0, 78, 1509, 927).

## Files (round2/)
| File | Size | Measured change vs round 1 (RGB means; luma std; luma 1st/99th pct) |
| --- | --- | --- |
| `coast-edited.jpg` | 1509 × 1005, q95 | means 101/85/99 → 104/86/93; std 56.8 → 51.3; p1/p99 4/223 → 12/209 |
| `coast-instagram.jpg` | 1080 × 1350, q95 | means 114/97/104 → 116/98/97; std 63.4 → 57.1; p1/p99 4/227 → 12/212 |
| `coast-caption.png` | 1600 × 900 | means 113/92/99 → 115/93/93; std 60.2 → 55.3; p1/p99 4/233 → 11/220 |
| `edit_coast.py` | — | editable source with the round-2 constants |

## Notes / uncertainties
- "A little" and "slightly" are judgement calls. Here they mean about +4 % red / −6 % blue and a 10 % contrast cut.
  Blacks lift from ~4 to ~12 and highlights drop from ~223 to ~209, so the image looks a little softer.
- The longer caption now ends at x = 990. The last word, "evening", runs over the dark foreground rock. It stays
  readable as light text on a dark area. I did not resize the text, so it matches round 1.
- Both derived images are still upscaled from the 1509 × 1005 corrected photo, as in round 1.

Tool calls: 7 (including this report and the final hand-back).
