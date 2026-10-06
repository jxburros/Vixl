# T15 · Seamless pattern (lane V, Vixl)

All artwork was made with Vixl through its MCP tools (`vixl_operations_apply`, `vixl_export_*`,
`vixl_render_preview`, `vixl_check`, `vixl_font_install`). I didn't draw any pixels, SVG or HTML by hand
and didn't use an image generator. I used Python for two things only. The first was layout arithmetic: a
seeded, toroidal Poisson-style scatter that picked motif centres, sizes and rotations, and then a list of
motifs whose bounds cross an edge. Its output was pasted into Vixl operation batches. The second was
checking the exported files (sizes, seam differences, SVG-vs-PNG comparison). Those scripts lived in the
session scratchpad and are not in this folder.

## Files

| File | What it is | How it was made |
| --- | --- | --- |
| `tile.vixl` | Editable source of the tile (1024 × 1024, cream `#f7f1e5` background) | Contains hidden master motifs `m_*`: a kelp frond (5 Bézier `shape path` layers: tapered stalk and 4 blades) in navy and sea-foam; a curling wave (2 stroked paths) in sea-foam, navy and coral; a spiral shell (`organic` preset `shell`) in coral and amber with navy chamber lines. The placed motifs are `duplicate` + `move` + `scale` + `rotate` + `show` of the masters (20 motifs, counted below), plus 34 `ellipse` dots (8–24 px) in the four ink colours. Most motifs are in group `motifs`. `i18`/`i19` were added after a visual check to fill two gaps and sit outside that group. |
| `tile.png` | 1024 × 1024 RGB, the seamless tile | `vixl_export_file` from `tile.vixl` |
| `tile.svg` | The same tile as vector (strict SVG policy, no embedded raster) | `vixl_export_file` from `tile.vixl` |
| `preview-3x3.vixl` | Editable 3072 × 3072 preview | 9 `link` layers, each drawing `tile.vixl` live at 1024 × 1024 |
| `preview-3x3.png` | 3072 × 3072, the tile repeated 3 × 3 | `vixl_export_file` from `preview-3x3.vixl` |
| `mug-wrap.vixl` | Editable mug wrap, 2550 × 1050 at 300 dpi | 6 `link` layers to `tile.vixl` (group `pattern`, marked `allow_crop`), a `rounded-rectangle` label and a `text` layer |
| `mug-wrap.png` | 2550 × 1050, 300 dpi (8.5 × 3.5 in) | `vixl_export_file` from `mug-wrap.vixl` |

Motifs in the tile: **6 kelp fronds** (i00–i03 navy, i04–i05 sea-foam), **6 curling waves** (i06–i08 sea-foam,
i09 and i19 navy, i10 coral), **8 spiral shells** (i12, i13, i15, i17, i18 coral; i11, i14, i16 amber) and
**34 dots** (dot00–dot33, cycling navy, amber, sea-foam and coral). There are also 7 edge wrap copies (see below).

## How the seamlessness works

Motifs were scattered on a torus, using wrap-around distance, so spacing stays even across the edges.
Every motif whose bounding box crosses an edge has a copy moved by exactly ±1024 px. Seven motifs cross an
edge (kelp i00, i01, i03, i05; coral wave i10; shell i13; dot01), so there are seven `*_w…` wrap copies.
Each copy keeps the canvas clip, so a shape cut off on one edge continues on the opposite edge.
I checked this three ways:
- In `preview-3x3.png`, each of the 9 cells is pixel-identical to `tile.png` (max difference 0).
- Mean colour difference across the left/right edge seam (column 0 vs 1023) is 1.87, and across top/bottom
  it is 1.48. Ordinary adjacent columns and rows inside the tile differ by about 1.5, so the seams look like
  any other pixel step.
- I looked at the seam crossings close up and at the downscaled 3 × 3 view. Motifs run straight across the
  joins.

## Choices and deviations

- **Palette:** only the five brief colours are used. One addition: the shells' spiral and chamber lines
  are navy `#14263b` (2 px at master size).
- **Kelp:** drawn as stylised seaweed fronds (a wavy, tapered stalk with alternating blades). Vixl's
  built-in `frond` preset read as a fern, so I didn't use it.
- **Layout:** evenly scattered with varied sizes (scale 0.45–0.78 of master) and rotations (kelp ±28°,
  waves ±18°, shells at any angle), with no grid.
- **Mug label:** a 600 × 300 px cream rounded rectangle (radius 48), exactly centred at (975, 375). "Tidewick"
  is navy, 104 px, in Fraunces SemiBold (downloaded from Google Fonts through `vixl_font_install`), centred.
  I added a **4 px navy outline** to the label. That wasn't in the brief, but a cream label on a cream
  background would otherwise only show where motifs are cut off.
- **Mug pattern scale:** the tile is drawn at **850 × 850 px** on the mug (not 1024) so that exactly 3 tiles
  span the 2550 px width. The wrap's left and right ends then meet seamlessly when wrapped around the mug.
  The mean difference between column 0 and column 2549 is 0.28. Vertically the 1050 px height shows 1.24
  tiles, starting at the tile's top edge.
- **Export settings:** PNGs are RGB (opaque), not CMYK. The brief asked only for PNG. `mug-wrap.png`
  carries 300 dpi metadata. `tile.png` and `preview-3x3.png` have no dpi set.

## Things I'm unsure about

- In the PNG renders, the sea-foam kelp shows a faint, slightly lighter fringe where its blades overlap
  the stalk (anti-aliasing of overlapping same-colour shapes). The SVG rendered with cairosvg doesn't show
  it. Overall the SVG matches the PNG closely: mean per-pixel difference 1.1/255, and 0.8 % of pixels differ
  by more than 40, all on anti-aliased edges.
- The SVG keeps nested transforms rather than flattened paths. It parses as valid XML and renders correctly
  in cairosvg. I haven't tested it in other editors.
- The preview and mug documents use live `link` layers that point to
  `evals/tool-comparison/runs/T15/claude-V/tile.vixl` (a workspace-relative path). If the folder is moved,
  those `.vixl` files need their links refreshed. The exported PNGs are unaffected.
- The density is fairly airy (cream covers about 92 % of the tile). The navy kelp sits slightly more to
  the left half of the tile.
