# T10 · Photo correction (lane V, Vixl MCP)

**Timing:** start 22:16:25 UTC, end 22:20:47 UTC (2026-10-05), about 4.5 minutes of wall time. I made about 48 tool calls in total (Vixl MCP, Bash checks, Read/Write and ToolSearch).

All visual work was done with Vixl MCP tools. I used short Python/PIL scripts only to measure the input and check the outputs: horizon position, region colors, noise and border extents. The original `evals/tool-comparison/fixtures/coast-raw.jpg` was never written to. Git shows it unchanged.

## Problems found in the raw (1600 x 1067)

These figures come from measuring the pixels:

- **Tilt.** The horizon falls from y~632 at x=600 to y~670 at x=1580. That is a slope of about 0.0388, or **2.22 deg**, lower on the right. The raw also has dark wedge borders along its edges, left over from an earlier tilt.
- **Underexposure.** The 99th percentile of luminance was 153, and no channel went above about 200, so there were no real highlights.
- **Color cast.** Highlights and midtones had a green cast. The sun core measured RGB (179, 199, 176) and the horizon glow (179, 180, 88), so green was higher than red in what should be warm white and gold.
- **Noise.** The flat sky had a per-channel standard deviation of about 4.5-5 (8-bit levels), with chroma blotches.

## Files

| File | How it was made |
| --- | --- |
| `coast-edit.vixl` | **Editable source** for the correction. It holds the photo layer with its rotation and effects, a multiply color-balance layer and a tone adjustment layer, and every setting can still be changed. |
| `coast-edited.jpg` | **1562 x 1007**, exported from `coast-edit.vixl` as a JPEG at quality 95. |
| `_master.png` | The same corrected image as a lossless PNG. It is the shared intermediate that the Instagram and caption documents import, so the derived files avoid a second round of JPEG compression. |
| `coast-instagram.vixl` / `coast-instagram.jpg` | **1080 x 1350**. Imports `_master.png`, scaled to 2094 x 1350 (factor 1.3406) and moved to x = -912. That is a crop of the corrected photo starting at source x ~680 and 806 px wide, at full height. JPEG quality 95. |
| `coast-caption.vixl` / `coast-caption.png` | **1600 x 900**, described in the caption section below. |

### Corrections in `coast-edit.vixl`, in stack order

1. **Leveling.** Photo layer `rotate` by **-2.22 deg** (stored as 357.78, counter-clockwise), centered on the canvas. After rotation the horizon measures y = 610 at x = 800, 1200 and 1540, so it is level.
2. **Crop.** The canvas is cropped to **1562 x 1007** at offset (19, 30) of the original frame (photo layer at x -40, y -62). This is the largest axis-aligned rectangle that fits inside a 1600 x 1067 frame rotated by 2.22 deg, so nothing more was cut than leveling needs. It removes the rotation wedges and the raw's own dark border wedges. I checked the corners for leftover border pixels and found none.
3. **Noise reduction** on the photo layer: `gaussian-blur` with amount **1.4** (sigma in px), then `sharpen` with amount **1.6** (PIL sharpness factor) to restore edges. Vixl has no dedicated denoise filter, so this is a blur-then-sharpen approximation.
4. **Color balance.** A solid layer `color-balance` filled with **rgb(255, 219, 242)** in **multiply** blend. This applies per-channel gains of R x1.00, G x0.86, B x0.95, which removes the green cast without lifting the shadows.
5. **Exposure and tone.** An adjustment layer `tone` with:
   - **levels** black 3, white 185;
   - **gamma 1.12**;
   - **saturation +6%**.

After correction:
- The sun core is about (247, 210, 160), a warm white.
- The horizon glow is about (247, 211, 113), gold and orange.
- Silhouettes stay near neutral black, about (4, 2, 8).
- Upper sky is a deep blue-violet, about (27, 20, 81).
- The 99th percentile of luminance went from 153 to 198.

### Caption (`coast-caption.vixl` -> `coast-caption.png`)

- **Photo:** `_master.png` scaled to 1600 x 1032 (factor 1.0243) and moved to y = -66, which is a vertically centered crop.
- **Shade:** gradient layer `caption-shade`, 1600 x 380 at y = 520, vertical, running from black at 0 opacity at the top to black at 0.55 opacity at the bottom.
- **Caption:** text layer reading "Port Ellery at golden hour".
  - Newsreader 400 at 64 px, color #fbf3e6. The font came from the `schibsted-newsreader` pairing, picked with `vixl_font_pair` using mood "editorial" and seed 7.
  - Constrained to the bottom-left, 80 px from the left edge and 72 px from the bottom, so its box is 80, 765, 699 x 63.
  - A soft drop shadow: blur 6, dy 2, opacity 0.35.
- **Check:** `vixl_check` passed with no errors. Its only warning was that the full-bleed gradient extends outside the 4% safe area, which is intended. The average background behind the text is about RGB (61, 53, 61), well below the cream text.
- **Format:** the PNG is saved as RGBA but is fully opaque.

## Choices and differences from the brief

- **Edited size.** `coast-edited.jpg` is 1562 x 1007, not 1600 x 1067. Leveling needs that crop, and I did not change the aspect ratio further, so it is 1.551 rather than 1.4995.
- **Instagram crop.** The 1080 x 1350 crop has to scale the 1007 px-tall photo up by 1.34x, so it is slightly softer than native resolution. I framed it on the sun and the figure. The lighthouse could not fit together with the figure in a 4:5 crop at this height.
- **Caption crop.** The caption image needs a slight 1.024x upscale to fill 1600 px of width, and about 66 px are trimmed from both the top and the bottom.
- **Intermediate file.** The Instagram and caption documents are built from the flattened `_master.png`, not by nesting the correction document. To change the correction there, re-export `_master.png` and replace the asset.

## Uncertainties

- **Denoise.** Some fine grain remains in the sky, and blur 1.4 slightly softens the bird and figure edges. Stronger noise reduction would have cost more detail.
- **Color.** The color balance was judged against the sun and highlights reading as warm white. How warm a golden-hour photo should look is partly a matter of taste.
- **Rotation angle.** The 2.22 deg came from fitting the horizon edge across x = 600-1580. After correction the horizon is level to within 1 px across the frame.
