# T15 Seamless pattern — claude, lane W (web code + headless Chromium)

## Files
| File | How it was made |
| --- | --- |
| `tile.svg` | Vector tile, 1024 × 1024 (viewBox 0 0 1024 1024), written by `make_pattern.py` (Python, fixed seed 15, so it regenerates identically). Cream `#f7f1e5` background rect + motifs clipped to the tile. |
| `tile.png` | 1024 × 1024 px, `tile.svg` inlined into an HTML page and screenshotted in headless Chromium (Python Playwright) by `render.py`. |
| `preview-3x3.png` | 3072 × 3072 px, a 3072 px div with `tile.svg` as a 1024 px repeating CSS background, screenshotted in Chromium (`render.py`). |
| `mug-wrap.png` | 2550 × 1050 px, same repeating background (`background-position:center`), plus a centered cream `#f7f1e5` label div exactly 600 × 300 px at x 975–1575, y 375–675, border-radius 40 px, 6 px navy border (inside the 600 × 300 box), text "Tidewick" in navy `#14263b`, P052 Bold (a Palatino clone installed locally) at 118 px. Rendered in Chromium (`render.py`). |
| `make_pattern.py` | Editable source for the pattern: motif builders + placement. Run `python3 make_pattern.py tile.svg`. |
| `render.py` | Editable source for the rasters/mug layout. Run `python3 render.py`. |

## Method
- Motifs, all drawn as SVG paths: **kelp fronds** (wavy stem + 6 alternating leaf blades + float bulb; 7 of them, radius 78–105 px), **curling waves** (swell into a spiral curl with two echo lines and foam droplets; 8, radius 58–78), **spiral shells** (filled logarithmic spiral with spiral line and ridges; 13, radius 24–42), **scattered dots** (130, radius 2.5–9).
- Colours used only from the brief: navy, amber, sea-foam, coral on cream. Colours are cycled per motif type.
- Placement: dart-throwing (Poisson-disc style) using **toroidal distance**, so spacing is even across the wrap and there is no grid. Each motif gets a random rotation (kelp ±55°, waves ±40° to keep them readable; shells 0–360°) and random size within its range.
- Seamlessness: every motif whose bounding radius crosses an edge is drawn again shifted by ±1024 in x and/or y (10 wrapped copies in this seed), and the tile is clipped to 0–1024. So anything leaving one edge re-enters exactly on the opposite edge.

## Checks done
- Pixel check on `tile.png`: mean abs RGB difference between column 0 and column 1023 is 2.27 (adjacent columns 0/1: 1.74); row 0 vs row 1023 is 2.39 (adjacent rows 0/1: 2.91). So the wrap boundary looks just like any interior boundary, i.e. no seam.
- Looked at a crop of `preview-3x3.png` around a tile corner: kelp and shells cross the seams with no break.
- Rendered `tile.svg` with Inkscape too: mean abs difference from the Chromium `tile.png` is 0.16/255, so the SVG renders the same outside a browser.

## Deviations / choices
- The mug label has a 6 px navy outline (drawn inside the 600 × 300 box) so it reads against the cream ground; the brief only asked for a cream label. Pattern motifs run right up to the label edge (there is no extra cream margin).
- The mug wrap is a crop of the repeating tile centered on the wrap; 2550 px is not a multiple of 1024, so the wrap's left and right ends do **not** join seamlessly where they meet around a real mug. The brief didn't ask for that.
- The label font is P052 Bold, a locally installed URW Palatino clone. No web fonts were fetched. `tile.svg` holds no text.
- No DPI metadata is set on `mug-wrap.png`. It is 2550 × 1050 px, which is 8.5 × 3.5 in at 300 dpi.

## Unsure
- How "evenly spread" will be judged: there are a few small open cream gaps (e.g. upper middle of the tile) by design of the random placement.
- The wave motif is stylised (curl + echo lines); at small scale it may read as a hook as much as a wave.

## Timing
Start 22:20:50 UTC, end 22:22:43 UTC (2026-10-05), about 2 minutes. Tool calls: 12.
