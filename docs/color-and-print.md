# Color language and print output

Vixl documents are RGBA8 sRGB. Every color field accepts a rich color language that resolves to sRGB, and print output is separated to CMYK when you export. This keeps editing simple and predictable while still producing press-ready files.

## Writing colors

Anywhere a color is accepted (`color`, `fill`, `stroke`, gradient stops, swatches, keyframes, layout overrides), you can write:

| Form | Examples |
| --- | --- |
| Names | `tomato`, `rebeccapurple` (148 CSS names) and 938 public-domain [xkcd survey](https://xkcd.com/color/rgb/) names such as `dusty rose`, `sage green` or `xkcd:green`. CSS names win when both define a name. |
| Hex | `#abc`, `#abcd`, `#aabbcc`, `#aabbccdd` |
| sRGB | `rgb(37 99 235)`, `rgb(37, 99, 235, 0.5)`, `rgba(…)`, `rgb(14% 39% 92% / 50%)` |
| Cylindrical | `hsl(220 83% 53%)`, `hsv(…)`/`hsb(…)`, `hwb(220 15% 8%)` |
| Perceptual | `lab(45 20 -70)` (CIE Lab, D50 as in CSS), `lch(45 72 290)`, `oklab(0.55 -0.02 -0.19)`, `oklch(0.55 0.2 263)` |
| Wide gamut | `color(display-p3 1 0 0)`, `color(rec2020 0 1 0)`, `color(srgb-linear …)`, `color(xyz-d65 …)`, `color(xyz-d50 …)` |
| Print | `cmyk(0 100 100 0)`, `cmyk(0%, 100%, 100%, 0%)`, `device-cmyk(0.2 0 0 0.2 / 50%)`. Plain numbers above 1 are read as percentages. |
| Other | `gray(50%)`, `kelvin(2700)` (blackbody light, 1000–40000 K), `transparent` |
| Mixing | `color-mix(in oklab, red 30%, blue)` with spaces `srgb`, `srgb-linear`, `oklab`, `oklch`, `lab`, `lch`, `hsl`, `hwb`, `xyz` |
| Modifiers | `lighten(c, 10%)`, `darken(c, 10%)`, `saturate(c, 20%)`, `desaturate(c, 50%)`, `mix(a, b, 25%)`, `tint(c, 30%)`, `shade(c, 30%)`, `tone(c, 30%)`, `alpha(c, 0.5)` (also `fade`/`opacity`), `rotate(c, 30deg)` (also `spin`/`hue-rotate`), `complement(c)`, `invert(c)`, `grayscale(c)`, `readable(bg[, candidates…])` |
| Swatches | `@brand`, and swatches inside expressions: `mix(@brand, white, 20%)`. A swatch may be defined from another swatch, so one definition can retint a whole document. |

Lightness and saturation modifiers work in OKLCH, so they look even across hues. Colors outside sRGB (wide-gamut, extreme Lab/OKLCH) are gamut-mapped by reducing chroma at constant lightness and hue, not by clipping. Unknown names suggest close matches.

## Color tools

```bash
vixl color '#2563eb'                          # hex, rgb, hsl, hwb, oklch, lab, cmyk, names, contrast
vixl color convert 'oklch(0.7 0.15 30)' --to cmyk
vixl color harmony '#2563eb' --scheme triadic  # complementary, analogous, triadic, split-complementary,
                                               # tetradic, square, monochromatic, tints, shades, tones
vixl color scale '#2563eb'                     # 50–950 ramp; the base keeps its own step
vixl color mix '#2563eb' white --amount 0.3 --space oklch
vixl color contrast white '#2563eb'            # WCAG ratio with AA/AAA verdicts
vixl color names sage                          # search names
```

Operations that store colors in the document:

```json
{"type": "palette-generate", "name": "brand", "color": "#2563eb", "scheme": "scale"}
{"type": "palette-generate", "name": "pair", "color": "@brand-500", "scheme": "split-complementary"}
{"type": "swatch", "name": "brand-soft", "color": "mix(@brand-500, white, 70%)"}
```

`scale` creates `brand-50` … `brand-950`; harmonies create `NAME-1` … `NAME-n`. MCP agents use `vixl_color(action, colors, …)`; REST clients `POST /color`.

## Print output

Start print work from a physical size so the canvas carries dpi, bleed and a safe area:

```bash
vixl new letter --bleed -o flyer.vixl          # 2626 × 3376 px: 8.5 × 11 in at 300 dpi + ⅛ in bleed
vixl new business-card --bleed --landscape -o card.vixl
```

Export formats:

| Output | Command |
| --- | --- |
| PDF (RGB) | `vixl export flyer.pdf` |
| CMYK PDF/TIFF/JPEG | `vixl export flyer.pdf --cmyk`, `vixl export flyer.tif --cmyk --ink-limit 300` |
| Press separation with the printer's profile | `vixl export flyer.pdf --cmyk --icc ISOcoated_v2.icc --intent relative` |
| Soft proof (how print will look) | `vixl export proof.png --proof [--icc PROFILE.icc]` |
| Explicit resolution metadata | `--dpi 300` (defaults to the canvas dpi × scale) |

Without a profile, CMYK uses a predictable device-naive separation with gray-component replacement: `--black-generation` (0–1, default 1, full GCR) and `--ink-limit` (total area coverage in percent) control it. With `--icc`, LittleCMS converts sRGB to the profile's CMYK with the chosen rendering intent (`perceptual`, `relative`, `saturation`, `absolute`) and embeds the profile; the profile decides black generation, and `--ink-limit`, when given, still caps total coverage by reducing C, M and Y. Vixl does not bundle press profiles; use the one your printer supplies. Alpha is flattened onto `--background` (white by default).

`vixl check --checks print` reports:

- total ink coverage above `--ink-limit` (default 300%), with the affected region;
- raster images below `--min-ppi` (default 200) at the canvas dpi;
- type smaller than 6 pt;
- text outside the live area (bleed + safe inset);
- layers that stop at the trim instead of extending into the bleed.

## Accessibility and color vision

`--simulate protanopia|deuteranopia|tritanopia|achromatopsia` (CLI export/render), `simulate=` (MCP preview/export) and `vixl check --checks color_vision` use Machado et al. (2009) matrices to show or detect text whose contrast collapses for color-blind readers. Fix such text with a lightness difference, not a different hue.

## Boundaries

Documents remain 8-bit RGBA sRGB: there is no CMYK editing, spot color, overprint control, trapping or high-bit-depth pipeline. CMYK values written in documents are converted to sRGB, so exact plate values are not preserved through export; use an ICC profile for accurate separations.
