# T11 round 2: red roof and chimney (lane V, Vixl)

I made both changes in Vixl through its MCP tools. Copies of `sketch.vixl` and `compare.vixl` in `round2/`
were edited in place. All six deliverables were then re-exported from those copies with the same file
names. Nothing outside `round2/` was changed. The only scripts I wrote read the exported files to check them.

## What changed

1. **Roof colour.** I changed the roof fill layer `house/fill-1` from coral `#e2725b` to `#c0392b`
   (operation `shape` with `target`, so the layer keeps its ID).
2. **Chimney.** I added `house/chimney`, made with `drawing stroke`. It is one open stroke with three
   straight sides: up from the right roof slope, across the top, and back down to the slope. It is
   60 px wide. It stands 59 px above the roof line on its left side and 120 px on its right side.
   - The canvas points I used are (980, 559.2), (980, 500), (1040, 500) and (1040, 619.9).
   - Both bottom ends lie on the traced right roof line (`house/s006`). I computed them from that
     stroke's endpoints, so the chimney sits on the roof and does not cross into it. The roof line
     itself is unchanged and forms the chimney's bottom edge.
   - **Line character.** Pure black `#000000`, round caps, unsmoothed straight segments, at exact
     right angles like the straightened walls and windows. The stroke is 5 px (I asked for 5.1 and
     Vixl stored 5.0), which matches the drawing's median stroke weight of 5.1 px.
3. **Chimney colour.** `drawing fill` (`gap: 12`) added `house/fill-15` inside the chimney in the
   same red `#c0392b`. This is my own choice, since the brief gives no colour for the chimney.
4. **Comps.** I re-saved both comps. `lines` hides `house/fill-15` like every other fill, so the
   clean PNG and SVG show only the chimney outline. `color` shows it.
5. **compare.vixl / compare.png.** I imported the new `sketch-color.png` as a layer at (2040, 0) in
   place of the old right-hand image and renamed it `colored`. The original photo on the left is unchanged.

## Checks

- `vixl_check` with the `drawing` and `bounds` checks passed with no issues.
- `drawing-report`: `preserved 0.9999` (unchanged), `added 0.0402` (was 0.0157; the chimney accounts
  for the difference), 35 strokes, stroke width min 3.7 / median 5.1 / max 6.6.
- I sampled `sketch-color.png`. The roof and the chimney are both `rgb(192,57,43)` = `#c0392b`. No
  pixels of the old coral `#e2725b` remain.
- I compared each new file with its round-1 version pixel by pixel.
  - In `sketch-color.png`, the changed pixels all fall inside the box (587,427)–(1111,700), which
    holds the roof and the chimney.
  - In `sketch-clean.png`, they all fall inside (977,497)–(1043,623), which is the chimney outline alone.
- `sketch-lines.svg` (strict policy) now has 35 `<path>` elements (34 plus the chimney), with no
  `<image>` and no base64 data. All files are the same sizes as before: 2000×1500, and 4040×1500 for compare.

## Notes

- The two chimney sides are different heights because the roof slopes. Measured from the roof line,
  the left side is 59 px and the right side 120 px. The top is level.
- I chose 5 px, the drawing's median weight, for the chimney. The roof lines it sits on are a little
  thinner (3.7 and 4.0 px, as traced), so at full zoom the chimney reads slightly heavier than the
  roof. It matches the walls (5.1–5.7 px).
- Mistake I corrected: my first chimney attempt was off by the house group's (−29, −38) offset,
  because `drawing stroke` takes canvas coordinates and I had given it group-local ones. I removed
  that stroke and redrew it. Neither the bad stroke nor its removal appears in the exported files.
