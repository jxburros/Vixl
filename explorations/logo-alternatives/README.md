# Vixl logo alternatives

Eight directions to compare with the current Digital Shift logo (`assets/brand/digital-shift`).
Every concept is an editable `.vixl` document built with the Vixl Python API; `build.py` regenerates
them, each PNG, and `output/contact-sheet.png`.

| Concept | Relation to the current logo | Idea |
| --- | --- | --- |
| A · Overprint | Close | The paired Vs as solid shapes; the overlap is its own colour (layering) instead of loose pixels |
| B · Half pixel | Close | One V, so the mark matches the wordmark's first letter; one arm dissolves into pixels |
| C · Layer stack | Related | Layer bars that shorten downwards into a V |
| D · Bezier | New | The V as a selected vector path with anchors and handles |
| E · Prompt | New | Terminal prompt and block cursor for an agent-first tool |
| F · Tile | New | App-icon monogram, one blue pixel escaping the tile |
| G · Wordmark | New | Lettering only: square pixel i-dot and a two-layer x |
| H · Editorial | New | Heavy serif with a pixel full stop |

```
python explorations/logo-alternatives/build.py
```

## Round two: two Vs that make an X, and reflections

`build_x.py` (run with `PYTHONPATH=explorations/logo-alternatives`) builds these and `output/contact-sheet-x.png`.
The X is two straight bars, so its top V and bottom V line up into one letter; the bottom V is the top V
turned half a turn, like the original kit.

| Concept | Idea |
| --- | --- |
| I · Clean X | The two Vs meet tip to tip; each has a pixel end, on opposite corners |
| J · Overprint X | A straightened into a true X; each V runs past the waist and the overlap is light blue |
| K · Shifted seam | The blue V slips one pixel sideways across a hairline gap (closest to the original) |
| L · Half pixel X | B's dissolving arm on the top-left, mirrored to the bottom-right |
| M · Reflection | Geometric "vixl" with one mirror line: x is a v plus its reflection, l is an i plus its reflection |
| N · Water | "vi" on a waterline; with its reflection the pair reads "Xl" |

## Round three: refining M

`build_m.py` (same `PYTHONPATH`) builds these and `output/contact-sheet-m.png`. Any l with a detached
square on top reads as an i, so every variant keeps the l one solid stroke.

| Concept | Idea |
| --- | --- |
| M2 · Only the x | The reflection lives in the x; the l is a plain stem |
| M7 · Waterline | x and l are cut at one waterline; everything under it is the blue reflection |
| M8 · Seam | One colour; a hairline cut along the waterline (the l can read as "!") |
| M9 · Both ways | v reflects down into the x; the i's stem reflects up into the l |
| M10 · Ghost | Waterline with a faint same-ink reflection |
| M11 · Lighter | Waterline with thinner strokes and more air |

## Round four: M7 with a reflection that does more

`build_r.py` builds these and `output/contact-sheet-r.png`. Above the waterline the letters are vectors;
below it the reflection carries something of Vixl's own. Pixelating the reflection itself was tried and
dropped: it fills the thin notch between the x's legs, and the x stops reading.

| Concept | Idea |
| --- | --- |
| R1 · Pixel tail | The blue reflection runs out into fading pixels under the baseline |
| R2 · Ripple | The reflection breaks into drifting bands, like water (the l can read as "!") |
| R3 · Scanlines | The reflection drawn in thinning scanlines |
| R4 · Shift | The reflection slips sideways, the offset of the original Digital Shift mark |
| R5 · Symbol + wordmark | The x on its own, large, as the symbol and favicon |
| R6 · On dark | R1 reversed out of charcoal |
