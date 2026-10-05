# T10 round 2: warmer, slightly less contrast, new caption (lane T)

All three deliverables were rebuilt from the untouched original (`fixtures/coast-raw.jpg`, md5 still `0adf9cb287cbfd00da4750dad81f245a`), so no JPEG was re-compressed on top of round 1. Nothing outside `round2/` was changed.

## Files in round2/
| File | Size | Change from round 1 |
| --- | --- | --- |
| `coast-edited.jpg` | 1558 x 1004, JPEG q95 4:4:4 | warmer, slightly less contrast |
| `coast-instagram.jpg` | 1080 x 1350, JPEG q92 | same grade (same 803x1004+595+0 window as before) |
| `coast-caption.png` | 1600 x 900 PNG | same grade, caption now **"Port Ellery, October evening"** |
| `build.sh` | script | copy of round-1 `build.sh` with the edits below; re-run to rebuild all three |

## What changed in build.sh
Every round-1 step (denoise, white-balance gains, gamma 1.10, +8% saturation, -2.2 deg rotation, 1558x1004 crop, sharpening, Instagram crop, gradient, font, position and shadow) is unchanged. I added two steps straight after the saturation step and before rotation:
1. **Warmer:** a second per-channel gain, `-color-matrix "1.03 0 0  0 1 0  0 0 0.95"`, so red x1.03 and blue x0.95 (variables `WARM_R`, `WARM_B`).
2. **Less contrast:** `+sigmoidal-contrast 2x50%`. This is ImageMagick's inverse sigmoidal curve at strength 2 around mid-grey (variable `SOFTEN`). It flattens the tone curve gently and doesn't clip anything.
3. **Caption:** the text is now a variable, `CAPTION="Port Ellery, October evening"`, used for both the shadow and the cream text layers. The font (DejaVu Sans Bold 64 pt), position (+80+72 bottom-left) and gradient are the same. The new text fits within about 1100 px, so it still lies over the gradient.

Housekeeping: `SRC` now points at `../../../../fixtures/coast-raw.jpg` because the script sits one folder deeper. I also dropped the JPEG-only `-quality/-sampling-factor` flags from the PNG write, which round 1 had flagged as meaningless for a PNG.

## Measured effect (ImageMagick means, 0-255)
| File | Mean R | Mean G | Mean B | Std dev (contrast) |
| --- | --- | --- | --- | --- |
| round 1 `coast-edited.jpg` | 98.4 | 58.8 | 74.4 | 54.6 |
| round 2 `coast-edited.jpg` | 102.0 | 61.3 | 73.4 | 53.2 |
| round 1 `coast-instagram.jpg` | 112.1 | 70.0 | 78.5 | 61.1 |
| round 2 `coast-instagram.jpg` | 115.5 | 72.0 | 77.1 | 59.4 |

In `coast-edited.jpg`, R-B rose from 24.0 to 28.6 (warmer) and the standard deviation fell by about 2.6% (less contrast). I kept these changes small on purpose, since the request said "a little" and "slightly". Side-by-side previews look the same scene, just a touch warmer and softer, and the caption reads clearly over the dark water and gradient.

## Uncertainties
- How much is "a little warmer" and "slightly less contrast" is my judgment. To go further, raise `WARM_R`, lower `WARM_B`, or raise the `SOFTEN` strength (for example `3x50%`) and re-run `build.sh`.
- The Instagram crop window and the caption-card framing were reused unchanged from round 1.

## Tool calls
8 tool calls in total for this round: 4 Bash (read report/brief, read script, build, measure), 2 image Reads for visual checks, 1 Bash to write this report, and the final hand-back.
