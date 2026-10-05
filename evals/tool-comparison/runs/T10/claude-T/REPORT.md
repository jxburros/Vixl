# T10 Photo correction: lane T (CLI desktop tools)

**Timing:** started Mon Oct 5 22:16:25 UTC 2026, finished Mon Oct 5 22:19:26 UTC 2026 by the `date` clock. 18 tool calls in total, including one failed attempt to write this report with the Write tool.

Tools used: ffmpeg (`nlmeans` denoise), ImageMagick 6 `convert` (colour, rotation, crop, resize, gradient, text), plus Python/OpenCV used **only to measure** things (horizon angle, colour samples, checks), never to edit pixels. GIMP and darktable-cli are not installed here, so I didn't use them. The original `fixtures/coast-raw.jpg` was only read. Its md5 is still `0adf9cb287cbfd00da4750dad81f245a`.

## Files

| File | What it is |
| --- | --- |
| `coast-edited.jpg` | Corrected photo, horizon level, **1558 x 1004**, JPEG q95 with 4:4:4 chroma |
| `coast-instagram.jpg` | **1080 x 1350** (4:5) portrait crop of the corrected photo, JPEG q92 |
| `coast-caption.png` | **1600 x 900** card with the caption "Port Ellery at golden hour" in the bottom left over a subtle dark gradient |
| `build.sh` | Editable source. All the adjustment amounts are variables at the top, and re-running it rebuilds all three outputs from the untouched original |

## What I found in the original (1600 x 1067)
- **Tilt:** I fitted a line to the sea/sky edge over x = 620-1590, which gave a slope of 0.03858, so **+2.21 deg** (lower on the right). The dark wedge along the left edge has the same tilt (2.19 deg), which fits the whole frame having been rotated about its centre.
- **Exposure:** too dark. The brightest pixels reached only about 186-203 (99.9th percentile) and the mean was 62/255.
- **Colour:** a green/cool cast. The sun core read R179 G199 B174 (green too high), the glow at the horizon was yellow-green, and the image's mean B (51) was higher than its mean R (42), which is wrong for a sunset.
- **Noise:** visible grain. Local standard deviation in a flat 40 px sky patch was 0.0257.

## Corrections, in order (as in `build.sh`)
1. **Denoise:** ffmpeg `nlmeans=s=3:p=7:r=15`, applied to the original before any brightening. The flat-patch noise fell from 0.0257 to 0.0179 and the birds stayed sharp. I also tried s=2 and s=4 and picked 3.
2. **White balance and exposure:** one per-channel gain step, `-color-matrix` **R x1.397, G x1.216, B x1.310**. It maps the sun core to about R250 G242 B228 (warm white), which removes the green cast. It also brightens by about +0.3 to +0.5 EV, depending on the channel.
3. **Midtones:** `-gamma 1.10` to open up the shadows.
4. **Saturation:** `-modulate 100,108,100`, so +8%.
5. **Level:** `-distort SRT -2.2`, which rotates **2.2 deg counter-clockwise** about the image centre (Lanczos filter). Measured afterwards, the horizon slope is -0.08 deg, which is level within measurement noise.
6. **Crop for leveling only:** the largest axis-aligned rectangle centred in the frame that avoids the empty corners after a 2.2 deg rotation of 1600 x 1067 is 1562 x 1007. I took **1558 x 1004**, centred, keeping 2 px of margin against interpolation and JPEG fringing. I checked that all four corners are clean, with no black wedges.
7. **Sharpening:** `-unsharp 0x0.8+0.4+0.02`, a light output sharpen to make up for the softening from denoise and rotation.

After correction the mean RGB is about (98, 59, 74), warm as a sunset should be. Only the sun core reaches 250-255.

## Derived outputs
- **Instagram:** a 4:5 window 803 x 1004 at x=595, y=0, taken from the corrected image, then Lanczos-upscaled x1.345 to 1080 x 1350 with a light unsharp mask. The composition is sun on the upper-third line, horizon at about 61% of the height, and the waving figure and rock in the lower right, with the sun's path on the water leading up to them. I placed the window to the right of the lighthouse headland, so the lighthouse and three of the four birds aren't in this crop. I chose this so the shot centres on the sun and the figure. The first version, at x=560, left a sliver of the headland tip on the left edge, so I moved it to x=595.
- **Caption card:** the corrected photo was scaled to 1600 px wide (1600 x 1031) and cropped to 900 rows from y=66 (no stretching). Over the bottom 405 px I laid a black gradient that runs from 0% opacity at its top to 55% at the bottom, and fades to 35% of that strength towards the right, so it sits mostly behind the text. The caption is set in DejaVu Sans Bold at 64 pt in cream #FFF6E8, placed at offset +80+72 from the bottom-left corner, with a 45%-black drop shadow offset 2 px.

## Deviations and uncertainties
- **Aspect ratio:** `coast-edited.jpg` is 1558 x 1004, roughly 1.55:1 instead of the original 1.50:1. I used the maximum-area crop, so the image is cropped "only as much as leveling requires". Keeping the original aspect would have meant cropping further, to 1514 x 1010.
- **Upscaling:** the Instagram image is upscaled about 1.35x, because the corrected photo is only 1004 px tall and a 4:5 crop at 1350 px tall can't come from it at native resolution.
- **Rotation angle:** I chose 2.2 deg as a round value between the two measurements (2.21 deg from the horizon, 2.19 deg from the frame edge). The remaining error is under 0.1 deg.
- **White-balance target:** using the sun as the neutral reference is my own judgment. A different editor might leave the result a little warmer or cooler.
- **Gradient strength:** it is deliberately subtle. In the busy upper parts of the image the caption is readable mainly because the water behind it is dark, helped by the drop shadow.
- **Caption format:** the caption card is saved as a PNG because the brief names a .png file. `build.sh` passes JPEG-only flags (`-quality 95 -sampling-factor 1x1`) for the PNG as well; for a PNG they don't control JPEG quality.
- **Unused tools:** Inkscape, potrace, GIMP and darktable weren't needed or available; there's nothing to vectorise in this task.
