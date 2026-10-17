# Render parity

[Documentation home](../README.md) · [Exporting](../guides/output/exporting.md)

How close Vixl's PNG renders are to a browser engine and to exact geometry, which differences are
defects, and what was fixed. The harness is [`evals/render_parity`](../../evals/render_parity/README.md):
`python -m evals.render_parity` (needs `pip install playwright`) writes side-by-side and difference
images and a JSON/Markdown report to `render-parity-results/`.

## Method

28 cases render the same content twice: as Vixl operations, and as HTML/CSS or inline SVG in headless
Chromium 141 at 1x, with the bundled `NotoSans-Regular.ttf` loaded through `@font-face`, the same sizes,
colours and positions, and `--font-render-hinting=none`. Text markup copies Vixl's first baseline and pen
position, so shaping and rasterization are compared, not defaults such as line height. Where geometry has
a closed form (circles, rounded rectangles, polygons, strokes, ramps, Gaussian blur, compositing formulas,
area-average downscaling) both renders are also measured against an exact 16 x 16 supersampled
reference, which separates a Vixl defect from a browser's own choice.

Measurements: glyph pen positions from Chromium's layout (DOM ranges) against Vixl's; per-glyph ink
shift from column-profile cross-correlation; ink box, total ink and edge sharpness; line breaks and
pitch; coverage error (rms, max, bias) on the whole image and along edges; distinct levels, longest flat
run and a banding score for gradients (deviation from a straight ramp after a 9 x 9 average); per-patch
blend colours; fitted blur sigma; aliasing left in fine stripes and a zone plate after downscaling.
Numbers below are 0-255 levels unless marked; "exact" is the supersampled reference.

## Findings

| # | Area | Finding | Severity | Status |
| --- | --- | --- | --- | --- |
| 1 | Layer placement | A layer at a fractional position (text placed with `baseline_y`, centred layers, shapes at `x: 10.4`) was drawn on whole pixels and resampled into place with bicubic: text edges 13% softer than Chromium's (sharpness 0.57 vs 0.66) with 6.6% more ink; against an 8x supersampled reference, 16 px text at offsets 0.1-0.9 px erred 5.6-9.4 rms vs 4.2 on whole pixels. An ellipse and a polygon path erred 3.3 rms against exact (Chromium 2.2). | High | Fixed |
| 2 | Rotation | Turned text and path shapes were rasterized upright, then resampled: 7% softer than Chromium's (0.51 vs 0.55). | Medium | Fixed |
| 3 | Gradients | No dithering: a 600 px ramp over 12 levels (#20242a to #2c3138) drew flat bands 43 px wide (banding score 0.23; Chromium dithers, 0.025). | Medium | Fixed |
| 4 | Shapes | Unstroked ellipses, rounded rectangles and capsules were drawn by Pillow at 4x and Lanczos-reduced: accurate on whole pixels (1.41 rms, better than Chromium's 3.34) but impossible to place exactly without resampling. | Low | Changed (drawn from the outline) |
| 5 | Rasterizer | resvg (tiny-skia) anti-aliases with 4 sub-scanlines per pixel: a horizontal edge at an arbitrary fractional y lands up to 1/8 px off (one row of coverage off by up to ~30 levels). Applies to every vector render, at whole pixels too. A 50 px square path at offsets 0.1-0.9 px averages 3.5 rms drawn from its outline vs 0.8 resampled (a shifted straight edge resamples almost exactly), while a pentagon averages 1.6 vs 2.8 and an ellipse 1.6 vs 3.2. Plain rectangles therefore keep resampling; square paths accept the small error. | Low | Structural, documented |
| 6 | Text gamma | Light-on-dark 12 px text carries 9% less ink than Chromium's (ratio 0.91); dark-on-light is within 2%. Skia boosts the contrast of text masks by luminance; Vixl blends linear coverage in sRGB. | Low | Legitimate difference |
| 7 | Text baseline | Chromium snaps each line's baseline to a whole pixel (ink box 0.25 px lower at 14 px); Vixl keeps the fractional baseline. Most of the 2.5-4 level mean difference on body text. | None | Browser choice |
| 8 | Shaping | Kerning, ligatures (ffi, fi), tracking and wrapping match: pen positions within 0.017 px of Chromium's layout in every case, identical line breaks, no whole-pixel glyph snapping in either (per-glyph ink shift 0.06-0.22 px, p90). | None | No defect |
| 9 | Blur | `blur` matches its sigma (fitted 2.05 for 2, 6.12 for 6) and is closer to exact than Chromium (0.47 vs 1.75 rms at sigma 2). | None | No defect |
| 10 | Drop shadow | 0.37 rms against exact (Chromium 0.64); fitted sigma 6.25 for `blur: 6` (Chromium 5.75), matching the SVG export's `stdDeviation`. | None | No defect |
| 11 | Compositing | All eight blend modes at 100% and 50% opacity within 1 level of the W3C formulas (`add` compared with `plus-lighter`). | None | No defect |
| 12 | Image downscaling | Lanczos with the anti-ring clamp removes detail past the output's Nyquist limit: 3 px stripes shown at 1/4 keep 6.1 levels of aliasing vs 52 in Chromium and in a plain area average. Vixl is the better of the two here. | None | No defect |
| 13 | Gradient endpoints | Vixl puts the end colours on the first and last pixel centres, CSS on the box edges: at most half a level. Radial gradients agree within 2 levels. | None | Legitimate difference |
| 14 | Hairlines | 0.5-2 px strokes on and off the grid match exact coverage (1.35 rms; Chromium 0.79); the remainder is finding 5. | None | No defect |
| 15 | Export consistency | Found in passing: the SVG export strokes rectangles, ellipses and polygons on the box edge, while PNG and PDF stroke a box inset by half the stroke, so the stroke lands one stroke width apart. PNG also cuts the outer half of a path's stroke where it meets the layer box; SVG and PDF draw it. | Medium | Fixed |

## What was fixed

- **Vector layers are drawn in place** (1, 2, 4). Text (plain and rich), path shapes and unstroked
  ellipses, rounded rectangles and capsules with no effects, mask or paper texture are rasterized from
  their outlines straight into their final pixels: fractional position, turn, flip and skew included
  (`render.vector_redraw`, `design_render.vector_drawing`). Layers with effects keep the old order (draw,
  effects in the layer's frame, resample). Results: `baseline_y` text sharpness 0.57 -> 0.67 (Chromium
  0.66), ink +6.6% -> +1.4%; 16 px text at fractional offsets 7.6 -> 4.1 rms mean against the 8x
  reference, the same as on whole pixels; fractional ellipse and polygon 3.3 -> 1.6 rms (Chromium 2.2);
  rotated text sharpness 0.51 -> 0.55. Reduced previews still snap to whole pixels.
  Tests: `tests/test_render_quality.py` (sharpness at fractional positions, exact coverage of a moved
  ellipse and path, rotated text, identity redraw).
- **Gradients are dithered** (3). An ordered dither (interleaved gradient noise, 64 px tile) below one
  level is added before quantizing; whole values are unchanged, so flat colours and end colours stay
  exact. Banding 0.23 -> 0.012, longest flat run 43 -> 13 px. A linear ramp computes one row of colours and
  repeats the 64 px dither period, so a 2400 x 2400 ramp takes about 8 ms (3 ms before dithering, 0.1 s
  when every pixel was dithered); radial and angled ramps still compute every pixel (about 0.15 s). Tests: `tests/test_render_quality.py`.

- **One stroke rule in every export** (15). Every renderer follows `stroke_align`, and closed shapes
  default to `inside` (`geometry.stroke_align`, `geometry.stroke_inset`): the stroke's outer edge is the
  outline, so a 10 px stroke on a rectangle, rounded rectangle, capsule or ellipse covers 0-10 px in from
  the box edge, the fill covers the whole shape under it, and a rounded corner keeps the layer's radius
  outside (inner radius: radius minus the stroke, at least 0). Polygons, stars, shortcuts and catalog
  shapes stroke inside their outline the same way. Paths, arcs, lines and open shapes default to
  `center`; a line's ends sit half a stroke in from its box corners, and an arc builds a half-stroke
  inset into its path, so its rim is flush too. An explicit `stroke_align` means the same with or
  without dashes, profiles or markers. This replaced an earlier rule that drew rectangles, rounded
  rectangles, capsules and ellipses in the box inset by half the stroke and stroked inward from there
  (ink 5-15 px in for a 10 px stroke) and put the centre line of polygon and star strokes half a stroke
  in (round joins), while styled strokes were centred on the box outline by default.
  PNG draws an inside or outside stroke as the band between the filled area and that area shrunk or
  grown by the stroke width (`vector_strokes.aligned_band`, exact for holes and tight curves); SVG and
  PDF draw a native stroke along the outline shrunk by half the stroke (rectangles, rounded rectangles
  and ellipses as elements, polygons and stars as mitred paths) where that draws the same band, and the
  band itself otherwise; PowerPoint, which centres strokes, insets the shape's frame by half the stroke.
  PNG draws a path's or arc's whole stroke: the image holds the box plus the margin the stroke reaches
  past it (miter joins and caps included), instead of cutting the stroke at the box. Measured on a
  10 px stroke: ink boxes and stroke edges in PNG, SVG (resvg) and PDF (pdfium) within 1 px for
  rectangles, rounded rectangles, ellipses, polygons, stars, lines and open and closed paths, at whole
  and fractional sizes, and for explicit `inside`, `center` and `outside`.
  Tests: `tests/test_stroke_placement.py`.

Golden images regenerated for the intended changes: `blend_modes`, `chart_line`, `groups`,
`shapes_and_strokes`, `effect_blur_shadow_glow` (ellipses and rounded shapes drawn from the outline),
`irregular_torn` (a turned path drawn in place), `gradients`, `gradient_to_transparent`,
`effect_lookup_lut` (dither, at most 2 levels); for finding 15, `path_stroke_only` and
`path_open_default_fill` (whole path strokes), `path_stroke_only.pdf` and `shapes_and_strokes.pdf`
(square rectangle corners) and the `shapes_and_strokes`, `path_stroke_only` and `groups` SVG snapshots;
for the flush inside stroke, `shapes_and_strokes`, `path_stroke_only` and `groups` (PNG, PDF, SVG and
PowerPoint snapshots) and `irregular_torn` (a stroked rectangle turned into a path keeps the stroke inside).

## What remains

- **Rasterizer precision (5).** Exact coverage on horizontal edges needs an analytic rasterizer (Skia's
  analytic AA or a FreeType-style area rasterizer). That is a backend change, not made here. The
  measured cost today is at most 1/8 px of edge placement, invisible at 1x, so the recommendation is to
  keep resvg and revisit only if print-resolution exports show it.
- **Text contrast (6).** A luminance-dependent text gamma, as Skia applies, would make small light-on-dark
  text heavier. It is a look, not a correctness fix; it would need a design decision and new goldens.
- Mirrored groups: a turned layer inside a mirrored group is rasterized in the mirrored frame, and
  resvg's anti-aliasing is not mirror-symmetric, so edge pixels can differ by up to 16 levels from the
  same layer outside the group.
