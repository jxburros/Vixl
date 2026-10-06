# T10 Photo correction: Vixl lane (claude-V)

I did all the editing in Vixl through its MCP tools. Python was used only to measure the input and check the exports: horizon angle, wedge edges, channel statistics and noise. The original `evals/tool-comparison/fixtures/coast-raw.jpg` was only imported and never written to. Its mtime is unchanged and git shows no change.

## Files

| File | What it is |
| --- | --- |
| `coast-edited.jpg` | 1556 x 1002, JPEG q95. The corrected, levelled photo. |
| `coast-instagram.jpg` | 1080 x 1350, JPEG q92. A portrait crop of the corrected photo. |
| `coast-caption.png` | 1600 x 900, PNG (RGB). The corrected photo with the caption, on a subtle dark gradient. |
| `coast-edit.vixl` | Editable master. The raw photo is embedded unchanged, with a non-destructive rotation, a LUT lookup and an effect stack. |
| `coast-instagram.vixl` | Editable. A live `link` layer to `coast-edit.vixl`, with crop {x 620, y 0, w 802, h 1002}. |
| `coast-caption.vixl` | Editable. A live link to `coast-edit.vixl` with crop {x 0, y 63, w 1556, h 875}, plus a gradient layer and a text layer. |

Because the crops are link layers, any change to the master's corrections shows up in both derived documents.

## Problems found (measured on the raw file)

- **Tilt.** I fitted a line to the sky-to-sea edge at 19 columns. The horizon falls left to right by 2.22° (slope 0.0388), dropping from y≈633 at x=620 to y≈670 at x=1570. The frame also shows dark corner wedges from that rotation: up to about 29 px at the top right and about 16 px on the left.
- **Exposure.** The image is underexposed. Mean luminance is about 51, the 99th percentile is about 153, and the brightest values reach only about 180–199 out of 255.
- **Colour.** There is a green cast. The sun core measures RGB (179, 199, 175), so green is about 20 above red and blue. The lighthouse lamp is (179, 185, 121), and the glow at the horizon looks yellow-green.
- **Noise.** There is visible grain: the high-pass standard deviation in a flat patch of sky is about 4.0 per channel, at roughly the same level in every channel.

## Corrections applied (in `coast-edit.vixl`, layer `photo`)

1. **Rotation: -2.22°**, which is 2.22° counter-clockwise, about the layer centre. Vixl stores this as rotation 357.78. I then centred the layer on the canvas.
   - Check: after the edit, the horizon edge sits at y=608 in all 17 columns I sampled between x=600 and x=1510, a fitted slope of 0.0°.
2. **Crop to 1556 x 1002, centred.** This is the largest axis-aligned rectangle that fits inside the rotated frame (1562 x 1007), with about 3 px of safety margin on each side so no rotation wedge or blurred edge remains.
   - Check: the corners and edges of the output hold image content, not black fill.
   - I did not keep the 3:2 aspect ratio. Keeping it would have meant cutting down to 1513 x 1009, and the brief says to crop only as much as levelling requires.
3. **Denoise:** Vixl's edge-preserving (non-local means) `denoise` with luminance 90, chroma 90 and search 5 (the default).
   - Result: high-pass sky noise went from 4.03 to 1.70, after adjusting for the tonal stretch (about 70% less).
   - Birds, the figure's outline and the lighthouse edges stay sharp; I checked this in a zoomed preview.
4. **White balance: a per-channel gain** of R ×1.00, G ×0.90, B ×1.00. This is applied as a 2x2x2 Vixl LUT named `wb-green-cast`, through the `lookup` operation.
   - Result: the sun core goes from (179, 199, 175) to about (180, 178, 170), which is neutral to slightly warm. The horizon glow is now yellow-orange instead of green-yellow.
   - I tried and rejected `tint` (an additive shift that turned the blacks magenta) and `auto-color` (it stretched each channel separately, killed the sunset palette and clipped 7% of pixels).
5. **Exposure: `levels`** with black 3 and white 195 (about ×1.33 gain, roughly +0.4 EV), then **`gamma` 1.1**.
   - Result: mean RGB went from (62, 42, 50) to (88, 53, 70). The sun core is now about (236, 229, 220). Under 0.001% of pixels clip.
   - The silhouettes stay near black and the scene still reads as dusk, not daylight.

I did not paint, clone, add, remove or move anything in the scene.

## Derived images

- **Instagram (1080 x 1350).**
  - Source region: x 620–1422, full height (802 x 1002, which is 4:5), scaled ×1.347.
  - Composition: the sun sits at the centre, the waving figure on the rock is right of centre, and the horizon is a little below the middle, with the glint path leading up to the sun.
  - The lighthouse is outside this crop. It is 1400 px from the figure, so there is no 4:5 crop that keeps both at this size.
  - Note: the corrected photo is only 1002 px tall, so this crop is **upscaled about 1.35x**. That is unavoidable for a 1350 px-tall output that stays the same photograph.
- **Caption (1600 x 900).**
  - Source region: x 0–1556, y 63–938, scaled ×1.028. Only sky above and dark water below are trimmed.
  - Gradient layer `caption-shade`: covers y 500–900, running from transparent to black at 30% (offset 0.6) and black at 55% at the bottom edge.
  - Caption: "Port Ellery at golden hour" in DM Serif Display 400, 64 px, colour #fbf3e6. It is placed bottom-left, 80 px from the left and 72 px from the bottom (bounds 80, 767, 731 x 61), with a soft drop shadow (blur 10, dy 2, opacity 0.45).
  - `vixl_check` passed with no issues. `vixl_measure` reports text contrast of at least 13.8:1.

## Choices and uncertainties

- **Colour correction.** I read the cast as green because the sun and the lamp, the most nearly neutral highlights, have green above red and blue. I kept the warm and purple sunset palette and did not neutralise the whole frame.
- **Tilt.** The angle (2.22°) is measured from the horizon edge. The true tilt could be a few hundredths of a degree different.
- **Output size.** `coast-edited.jpg` is 1556 x 1002 rather than 1600 x 1067, because of the crop that levelling requires.
- **Denoise strength.** This is a judgement call: a faint residual grain remains, which I left on purpose to avoid a plastic look.
- **Link paths.** The `.vixl` link layers point to the master with a workspace-relative path (`evals/tool-comparison/runs/T10/claude-V/coast-edit.vixl`).
