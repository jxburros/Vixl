# T04 · Tidewick logo kit (Lane V: Vixl)

All artwork was built and exported with the Vixl MCP tools (`vixl_document_create`,
`vixl_operations_apply`, `vixl_import_document`, `vixl_font_pair`, `vixl_export_file`/`vixl_export_batch`,
`vixl_render_preview`, `vixl_check`). I didn't hand-write any SVG, HTML or pixels, and I didn't use an image generator.
I used Python (PIL, resvg_py) only to check the outputs: rendering the exported SVGs, reading the ICO sizes, and
zooming into the small marks.

## Concept

The name is "Tide" plus "wick": a candle or lamp flame in lamp amber with a navy core, set above one bold navy wave.
The flame leans slightly so it reads as a flame and not as a water drop. There are no anchors or ship wheels.
The mark uses two colors (navy `#14263b` and amber `#f2a541`). Type is Fraunces 700 for the wordmark
"Tidewick" and Work Sans 400 for the all-caps tagline "COFFEE BY THE HARBOR". Both are open-licensed
Google Fonts, installed with `vixl_font_pair` (pairing `fraunces-work-sans`).

## Files

| File | What it is / how it was made |
| --- | --- |
| `mark.svg` | 512 × 512 transparent canvas. The flame and its core are `pen` Bézier paths, and the wave is a parametric `wave` shape with a 58 px round-capped stroke. Navy + amber. Exported with `svg_policy="strict"`. |
| `mark-mono.svg` | The same geometry in navy only. The flame core is a real hole (a `pathfinder` subtract, even-odd compound path), so the core still shows on a single-color print. Strict SVG. |
| `logo-horizontal.svg` | 1164 × 392, transparent. I exported `mark.svg`, re-imported it as editable paths (`vixl_import_document`), grouped it and scaled it ×0.62 on the left. The wordmark is 160 px Fraunces 700 and the tagline 40 px Work Sans beneath it. Margins are about 50 px. Strict SVG. |
| `logo-stacked.svg` | 834 × 627, transparent. The same mark group is centered above the wordmark and tagline. Strict SVG. |
| `favicon.ico` | Contains 16, 32 and 48 px images. I checked this with PIL. The source is `src/favicon.vixl`, a 512 px navy square with the mark at ×0.92, flame amber and wave cream, exported with `icon_sizes=[16,32,48]`. |
| `app-icon-1024.png` | 1024 × 1024, mode RGB, so there is no alpha channel. It is a navy square with square corners and the mark at ×1.25 centered, with the wave in cream. Exported with `alpha="flatten"`. |
| `logo-sheet.png` | 1600 × 1200, RGB. The left half is cream and the right half navy. Each half shows the horizontal logo, the stacked logo, the color mark, the mono mark and an "ACTUAL SIZE" row with the mark at real 16, 32 and 64 px. Each item is a live `link` layer to the source `.vixl` files. The navy half passes `variables: {ink: "#f7f1e5"}`, so the navy parts render in cream. |
| `src/*.vixl` | Editable Vixl sources for every file above. In mark, mark-mono and both logos, the navy color comes from the variable `${ink}`. |

On the SVGs:
- All four were exported with `svg_policy="strict"`. They contain no `<image>`, `<text>` or `@font-face`.
- Lettering is converted to glyph outlines (`<path>`), so they don't need the fonts to be installed.
- I rendered each one with resvg to confirm it looks right.

## Deviations and choices

- **Reversed versions on navy use cream.** On the navy half of the sheet, the favicon and the app icon, the parts
  that are navy on light backgrounds (wave, wordmark, tagline) become cream `#f7f1e5`, and the flame stays amber.
  Each version still uses at most two colors on its background. A navy-only mark can't be seen on navy, so on the
  navy half the "mono" mark is shown as a one-color cream knockout. I didn't deliver that as a separate file.
- **Favicon and app icon are on a navy tile.** A transparent favicon would lose the navy wave on dark browser
  tabs. The mark geometry is the same as `mark.svg`; only the wave is recolored cream.
- **"Real size" on the sheet** means the full 512 px `mark.svg` square drawn at 16, 32 and 64 px. The mark itself
  fills about 86–95 % of that square. The favicon fills its tile a little more (scale 0.92).
- `vixl_check` on the sheet flagged the small labels (15–18 px) as hard to read at a 320 px thumbnail
  width. I left them: the sheet is a reference meant to be viewed at full size.
- Margins and sizes of the logo canvases were my own choice; the brief didn't set any.

## Unsure about

- **16 px legibility.** At 16 px the flame, core and wave are still recognizable, but the navy core is only about 2 px and
  blurs into the flame. It reads as "amber flame over a wave" rather than showing detail. At 32 and 48 px it is clear.
- **Variable colors in the sources.** The navy color in the sources is the variable `${ink}`. The exported SVGs contain
  the resolved `rgb(20,38,59)`; I checked that no `${` is left in them. Anyone editing the `.vixl` files needs to know
  about the variable.
- **Flame/drop ambiguity.** With the lean, the shape reads as a flame next to the wave, but on its own the mono mark could
  still be read by some people as a drop.
