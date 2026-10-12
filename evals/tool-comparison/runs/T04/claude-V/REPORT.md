# T04 Logo and icon kit: Tidewick (lane V, Vixl)

I made all of the artwork with Vixl through its MCP tools: `vixl_compose`, `vixl_operations_apply`, `vixl_import_image`, `vixl_export_file` and `vixl_export_batch`. I didn't hand-write SVG, draw pixels or use an image generator. `src/gen.py` and `src/sheet.py` are small Python scripts that write the Vixl operation lists (JSON) the documents are built from. That way all the lockups share the same mark geometry.

## The design

- **Mark:** a navy disc. Inside it, in amber, is a lamp flame (the "wick" in Tidewick) with two light beams pointing left and right, which makes it read as a lighthouse lamp. One thick wave sits below it for the harbor water. It uses two colors, navy `#14263b` and amber `#f2a541`. There are no anchors or ship wheels. Each part is a vector path drawn on a 512 × 512 grid.
- **Lettering:** the wordmark "Tidewick" is set in Fraunces 700, a warm, soft serif. The tagline "COFFEE BY THE HARBOR" is set in Work Sans 400, in capitals with about 0.12 em letter-spacing. Both are open-licence Google Fonts, installed through `vixl_font_pair fraunces-work-sans`.
- **Iteration:** my first mark had a teardrop flame over two thin waves. Its preview read as a water drop (it looked like a plumbing logo), and at 16 px it blurred into stripes. I added the beams, enlarged the flame, thickened the beams and cut the water to one heavy wave so the mark holds up at 16 px.

## Files

| File | What it is | How it was made |
| --- | --- | --- |
| `logo-horizontal.svg` | 1240 × 400, transparent background. Mark on the left, wordmark to its right, tagline beneath the wordmark. Navy and amber | `src/logo-horizontal.vixl` (built with `vixl_compose` from `src/horizontal.json`), exported with `svg_policy="strict"` |
| `logo-stacked.svg` | 900 × 655, transparent. Mark centred above the wordmark and tagline (both centred on the canvas) | `src/logo-stacked.vixl` from `src/stacked.json`, strict SVG |
| `mark.svg` | 512 × 512, transparent. The full-colour mark | `src/mark.vixl` from `src/mark.json`, strict SVG |
| `mark-mono.svg` | 512 × 512, transparent. Navy only: one compound path, with the flame, beams and wave cut out of the disc (pathfinder subtract, even-odd) | `src/mark-mono.vixl` from `src/mark-mono.json`, strict SVG |
| `favicon.ico` | Contains 16, 32 and 48 px images (checked with Pillow) | `vixl_export_file` from `src/mark.vixl` with `icon_sizes=[16,32,48]`. Transparent outside the disc |
| `app-icon-1024.png` | 1024 × 1024, RGB with no alpha channel, square corners. Navy fills the whole square; the flame, beams and wave are amber (the square takes the disc's place) | `src/app-icon.vixl` from `src/app-icon.json`, exported with `alpha="flatten"` |
| `logo-sheet.png` | 1600 × 1200, RGB. Top half on cream `#f7f1e5`, bottom half on navy | `src/logo-sheet.vixl` (see below) |

**SVG checks.** None of the four SVGs contains `<image>` or `<text>` elements. All lettering is outlined glyph paths (28 paths in each lockup), so the files don't need the fonts installed. Strict policy would have refused the export if any raster had been embedded. I also rendered each SVG on its own with resvg (`resvg_py`), outside Vixl, and it matched the Vixl previews.

**What's on the sheet.** Each half has:
- the horizontal lockup and the stacked lockup
- the colour mark
- the one-colour mark
- the mark at its actual size: 64, 32 and 16 px

The cream half also shows the app icon at 96 px, and each item has a small label.

## Different from the brief, or my own choices

- **Versions on navy.** The brief gives no reversed colours. On the navy half I swapped the mark to an amber disc with navy flame, beams and wave (still two colours). The wordmark there is cream and the tagline amber. The one-colour mark on navy is shown in **cream** (a knock-out), because a navy mark disappears on navy. These reversed versions appear only on the sheet; the brief didn't ask for separate files.
- **Variables for reversing.** The colours in the lockups and the mark are Vixl document variables (`disc`, `fg`, `ink`, `tag`). The reversed versions on the sheet are exports of the same documents with different variable values, not separate artwork.
- **App icon.** I left out the disc and put the amber parts straight onto a full navy square, because a circle inside a square tile looked cramped. The amber parts are about 20 px below the optical centre at 1024 px (the content of the 512 grid sits slightly low). It is barely visible and I left it.
- **Real sizes on the sheet.** The 64, 32 and 16 px marks are Vixl link layers to `src/mark.vixl`, rendered at those exact pixel sizes on whole-pixel positions. They are not the ICO's own bitmaps, but they use the same renderer and size.
- **Lockups on the sheet are pre-rendered images.** The lockups on the sheet are PNGs exported by Vixl at the sheet scale (`src/sheet-*.png`) and then imported. My first attempt used live link layers. In those, the letter-spaced tagline rendered wider than it should and was cut off ("COFFEE BY THE HAR"). Exporting the same documents at the same scale with `vixl_export_file(scale=…)` drew it correctly. This looks like a Vixl bug: letter-spacing (`tracking`) seems not to be scaled when a link layer draws a text document at a smaller scale. The ordinary preview looked a little off too, but measured pixel bounds at scale 1 and 0.5 were correct.
- **Extra files.** `src/` holds the editable `.vixl` sources, the operation JSON and the generator scripts. They aren't deliverables.

## Not sure about

- **16 px legibility.** At 16 px the mark reads as a disc with a bright lamp, a bar on each side and a wave line. The flame's inner notch and the thin tip disappear. It is recognisable but soft. 32 px and up are clear.
- **Tagline size.** At 40 px in the lockups it is fine at those sizes, but it gets small if the horizontal lockup is shown below about 300 px wide. Vixl's thumbnail check flagged this as informational only.
- **Font licence.** Fraunces and Work Sans are SIL Open Font License fonts. The SVGs contain only outlines, so no font files are shipped.
- **Labels.** The sheet labels use British spelling ("One-colour mark").
- **Check warnings left as they are.** Vixl's design checks pass with no "fix" findings. The remaining warnings are safe-area notes on the sheet's full-bleed navy half and on two lockup images that sit 20 px from the top edge. I left those as intended.
