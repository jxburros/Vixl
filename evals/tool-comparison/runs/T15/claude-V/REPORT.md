# T15 · Seamless pattern: Lane V (Vixl)

All artwork was made with the Vixl MCP tools (`vixl_document_create`, `vixl_operations_apply`, `vixl_export_file`). I didn't hand-draw any pixels, SVG or HTML, and I didn't use an image generator. The one script I wrote only read the exported PNG/SVG files to check them.

## Files

| File | What it is | How it was made |
| --- | --- | --- |
| `tile.vixl` | Editable source of the tile | 1024 × 1024 document with a cream `#f7f1e5` canvas. The motifs are drawn as editable layers. Two `pattern-scatter` groups use toroidal (wrap-around) Poisson-disc placement: `dots` (cream background plus 45 dots, seed 31) and `motifs` above it (16 kelp/shell/wave copies, seed 5, scale 1.15 ± 30 %, rotation ± 70°). Motifs that cross an edge get wrapped "ghost" copies on the opposite edge. The original motif layers are hidden in the file and stay editable; running `{type: pattern-scatter, target: motifs}` (or `dots`) rebuilds a layer after a motif is edited. |
| `tile.png` | 1024 × 1024 RGB, one seamless tile | `vixl_export_file` from `tile.vixl` |
| `tile.svg` | Same tile as vector, 1024 × 1024 viewBox | `vixl_export_file` from `tile.vixl`. It contains only vector paths, with no `<image>` raster fallbacks. Wrapped copies run past the edge and are clipped by the viewBox. |
| `preview-3x3.vixl` | Source of the preview | 3072 × 3072 document with nine live `link` layers to `tile.vixl` at 1024 px offsets |
| `preview-3x3.png` | 3072 × 3072, the tile repeated 3 × 3 | `vixl_export_file` from `preview-3x3.vixl` |
| `mug-wrap.vixl` | Source of the mug wrap | 2550 × 1050 document at 300 dpi. Six `link` layers to `tile.vixl` (3 × 2 grid, offset −261, −499 so the repeat is centred on the wrap; marked `allow_crop`). On top sit a 600 × 300 rounded-rectangle label (radius 40, cream fill) at x 975, y 375, which is centred, and the text "Tidewick" in navy `#14263b`, 100 px Noto Serif Bold, centred in the label. |
| `mug-wrap.png` | 2550 × 1050 RGB, 300 dpi metadata | `vixl_export_file` from `mug-wrap.vixl` |

## Motifs (all in the brief's palette)
- **Kelp fronds** (navy and sea-foam): each is a group of tapered `pen` strokes, a wavy stipe with three long blades. I tried Vixl's organic `frond` preset first, but it read as a fern, so I replaced it.
- **Small spiral shells** (coral and amber, with a navy outline and chamber lines): the organic `shell` preset, which draws a nautilus-style spiral.
- **Curling waves** (amber and navy): an open stroked path that ends in a curl, with round caps and no fill.
- **Scattered dots**: ellipses in all four motif colours, in two sizes each, with ± 30 % size jitter.

## Checks I ran (script reads only)
- **Sizes:** tile 1024 × 1024, preview 3072 × 3072 and mug 2550 × 1050 (dpi 300) are all correct.
- **Seam:**
  - The mean colour difference across the wrap is 1.96 left/right and 0.48 top/bottom.
  - Inside the tile, the difference between neighbouring columns or rows averages 1.38 to 1.49.
  - So the edge changes no more than the inside does, and Vixl's own seam report said `seamless: true` for both scatter groups.
- **The preview is exact:** `preview-3x3.png` matches `tile.png` tiled 3 × 3 pixel for pixel (largest difference 0).
- **Colours:** the main colours in `tile.png` are exactly `#f7f1e5`, `#14263b`, `#a8d5c8`, `#f2a541` and `#e2725b`, apart from anti-aliased edge pixels.
- **Text check:** `vixl_check` on the mug wrap passed with no `fix` findings. The only `review` items say the text overlaps the pattern links, which is expected because the label sits on top of the pattern.

## Choices and differences from the brief
- **Label outline:** the label has a 4 px navy outline as well as its cream fill. Without it, a cream label on a cream background had no visible edge. If a strict "cream label only" is wanted, remove the stroke in `mug-wrap.vixl` (`{type: shape, target: label, stroke: "transparent"}`).
- **Font:** the brief doesn't name one. I used Noto Serif Bold, the heading font the document rolled on creation.
- **Pattern scale on the mug:** the tile is used at full size (1024 px = about 3.4 in at 300 dpi), so the wrap shows about 2.5 repeats across. I did not rescale it.
- **Two scatter passes:** `pattern-scatter` picks motifs uniformly at random and won't accept the same source twice, so it can't weight dots more heavily than large motifs. I split them into two passes. As a result, a few dots sit partly on or behind a large motif. This is deliberate and reads as scattered, but the two passes don't keep a minimum distance from each other.
- **Seeds:** I picked the seeds by eye from a few candidates. Two earlier seeds bunched the large motifs or left a large empty band.

## Things I'm unsure about
- **Visible repeat:** in the 3 × 3 preview, two sea-foam kelp fronds in the same column of the tile line up vertically. That column repeats, so at a glance there is a faint vertical rhythm. It isn't a seam, but a strict reviewer might call it a slightly visible repeat.
- **Waves:** only three wave copies landed in the tile (two navy, one amber), so waves are the least frequent motif.
- **Linked sources:** `preview-3x3.vixl` and `mug-wrap.vixl` link to `tile.vixl` by workspace path. If they are moved without it, they need `links-relink` or `link-embed`. The exported PNGs are self-contained.
