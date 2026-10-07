### Changed defaults

- **`${page}` and `${pages}` skip hidden pages**, so a four-page deck with one hidden page reads 1 / 3 to 3 / 3 in PDF, HTML and PowerPoint; a hidden page shows the number the next shown page has. To count hidden pages again, give each page its own variable (`page set NAME --variables '{"n": 3}'`) and write `${n}` (#280).
- **Print sizes with bleed keep their physical size**: the bleed is kept to the half pixel, so `vixl new business-card --bleed` is 1125 × 675 px (3.75 × 2.25 in at 300 dpi), not 1126 × 676, and the stored `bleed` can be fractional (37.5). Documents made before keep their canvas and still export at the exact page size. For the old canvas, pass a custom `bleed` that rounds up, or resize with `canvas` (#306).
- **`drawing smooth` keeps the corners that `straighten` made**: lines and polylines from `straighten` are left as they are. Pass `settings: {"corners": "round"}` to smooth them as before; the `drawing` check then warns that their corners became curves (#312).
- **A TIFF of a canvas without a dpi is tagged 72 dpi** (× the export scale), the resolution a PDF export assumes, instead of carrying no resolution tags. Pass `dpi` to choose another (#338).
- **Diagram back edges go around nodes**: in `radial` and `mindmap` layouts a cycle's back edge that would run through nodes, or lie on its tree edge, is routed around them, and extra edges in every layout attach beside connectors already on a side. Give such an edge `from_port`/`to_port` to place it yourself (#346).

### Added

- **`$${name}` writes a literal `${name}`** in text, rich text and text flows; the missing-variable error names the escape (#293).
- **`confetti` with `count`** scatters that many non-overlapping slips at `seed`-chosen places and angles; without `count` it is one slip as before (#302).
- **`color scale A B [C…] --count N --space S`** returns N steps between the colours; one colour still gives the 50–950 ramp, and `--count` with one colour is an error (#363).
- **Colours outside sRGB are reported**: `color info`/`convert` (and `vixl_color`) add `clipped` (`chroma` or `clamp`) and a warning, for example for `oklch(70% 0.4 30)` (#363).
- **The diagram check reports edges drawn on top of each other** (a pair that reads as one line or a two-headed arrow); edges from one source or into one target may still share a trunk (#346).
- **`vixl layers --full`**: `vixl layers` now abbreviates long path data, path nodes and point lists to their size and a pointer to `vixl inspect LAYER`; `--full` prints them (#292).

### Fixes

- PPTX draws skewed and affine-transformed layers as pictures of the render and lists them under `raster_fallbacks` (`skew`, `affine transform`), instead of writing them unskewed with no warning (#311).
- Images above the pixel limit import: with `max_pixels` or `downsample` an `add` may read a source up to four times the limit (a 108 MP camera file under the default 40 MP) and shrinks it while decoding; `vixl import`, `vixl_import_image` and REST `/assets` downsample such a file on their own and report `downsampled` with a warning. Pillow's 89 MP guard no longer stops imports below Vixl's own limit, and a plain `add` of a too-large file names its size and both remedies (#323).
- REST refuses a body whose `Content-Length` is over the route's limit with `413 resource_limit` before reading it, and the error names the limit (#325).
- `vixl_compose` says when it makes the new document the active one: the result carries `active_document` and, when another document was active, a warning naming it; the docs describe the switch (#307).
- `--dry-run` reports the layer, page and effect IDs the real apply then creates, also across CLI processes (#359).
- `rgb()` colours with channels outside 0–255 are clamped to hex in operations and reported under `normalized` (#365).
- The docs list the text metrics (`ink_bounds`, `baseline`, …) that `detail: "brief"` returns for new text layers (#347).
- A crisp scaled raster export (`scale` above 1) records the dpi of the requested scale (canvas dpi × scale) rather than the canvas dpi.
