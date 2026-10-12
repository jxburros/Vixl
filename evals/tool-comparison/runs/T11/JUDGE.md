# T11 · Hand drawing to clean art: judge notes

Runs: claude-V, claude-T, claude-C (round 1 + round2/).

- **V lane: re-run on Vixl 0.26.0, judged 2026-10-12** (claude-opus-5-5 subagent). Round 1 took 3.8 min and 39 tool calls; round 2 took 2.0 min and 28 tool calls.
- **T and C lanes: run and judged 2026-10-05** (claude-opus-5-5 subagent). Their notes and scores below are unchanged.

For the 2026-10-12 judging, the T and C deliverables were regenerated from their committed sources in a scratch copy outside the repo:
- C's four scripts ran unchanged once scikit-image was installed. Its `strokes.json` matched the committed one to 1.4e-12.
- T's `run.sh` and `round2/scripts/round2.py` ran once Inkscape and ImageMagick were installed, with the round-2 render commands from its report. Its `geom.json` matched to 2.0e-12.

All six runs then went through `inspect_outputs.py --blind` together. The blinding leaks: V's 2000×1532 size and the T and C work files (`bin.png`, `norm.png`, `work_*.png`) give away the lanes.

## 1. Blind scores (written before opening key.csv)

### V on Vixl 0.26.0 (2026-10-12)

| Code | Fidelity | Craft | Reason |
| --- | --- | --- | --- |
| PI41 | 4 | 3 | **What's right.** Everything is there, and the sun, the house top-left corner and the canopy are closed. The tilt is fixed: the walls lean only 0.2–0.6°. The rays keep their drawn angles, and all eight colours are exact.<br>**Fidelity misses.** The ground line has been extended to both canvas edges with two flat lines. There is a visible kink at each join, and this changes the composition a little. A hand-drawn lobe closes the canopy gap.<br>**Craft problems.** The stroke weight is mixed: the roof is thin and the walls are heavy. The ground and canopy outlines are jittery, with a kink where the added lobe meets the canopy. A white sliver sits between the canopy fill and its line on the left. The roof colour runs past the line ends at the eaves, and the windows are slightly keystoned. |

Round 2: EZ3J (red roof plus a plain rectangular chimney; nothing else moved).

My blind re-look at the regenerated T and C files agreed with their 2026-10-05 scores (SPS7 4/5, ODB3 4/4), so those scores stand.

### T and C (2026-10-05, unchanged)

Round-1 codes are the three with a coral roof.

| Code | Fidelity | Craft | Reason |
| --- | --- | --- | --- |
| 74SD | 4 | 5 | Tilt fixed, walls vertical. Sun, house corner and canopy all closed. Rays keep their drawn angles. Consistent 6 px stroke. The ridge X is reduced to an apex point and the wall-top line is merged into the eave. |
| FNGM | 4 | 4 | All gaps closed, ridge X kept, two-line trunk. About 0.8° of wall lean remains and the windows are skewed. Tiny coral slivers sit outside the eave corners. |

Key: PI41 = **V** (2026-10-12; round 2 EZ3J). 74SD = **C**, FNGM = **T** (2026-10-05; round 2: VFF7 = C, PK8U = T). The same C and T files were SPS7 and ODB3 in the 2026-10-12 blind set (round 2: HDZO = C, ULNQ = T).

## 2. Hard checks (round 1)

Ground truth comes from `fixtures/make_fixtures.py`:
- The drawing is rotated by exactly 2.0°, with the walls at x = 600 and 1100. The windows are drawn as rectangles.
- The roof lines are drawn as eaves that overhang the walls: at y = 700 the left roof line is at x ≈ 582, so the wall-top line was never meant to touch the roof.
- The ground line runs from x = 150 to 1850 and does not reach the paper's edges.

For V (2026-10-12), I first registered the photo's ink onto `sketch-clean.png` with an affine ECC fit (correlation 0.962). The fit gave a −2.20° rotation and a 1.029 scale, which is the group's 0.972 scale-down. I then:
- flagged ink further than 12 px from the other image's ink;
- listed the closed white regions of the clean PNG;
- measured the wall, door and window sides row by row.

| Check | V (0.26.0) | T | C |
| --- | --- | --- | --- |
| SVG: `embedded_images=0`, vector strokes | pass (36 `<path>`, all `rgb(0,0,0)`, round caps, plus a white rect) | pass (29 `<line>`, circle, polygon, polyline) | pass (25 paths + circle) |
| Clean PNG: black on white, 2000 wide, tilt corrected, paper and desk gone | pass (2000×1532 RGB, black on white with antialiasing. `drawing import` found the paper and corrected −2.2°, 0.2° more than needed. The lines keep their drawn angles, so the walls lean slightly: the left wall moves 610→608.5 and the right wall 1097.5→1094 over 360 rows) | **fail**: the paper-corner warp found only ~1°. Walls in the clean PNG lean ~0.8° (x 594→599 over rows 760–1080) and the windows are skewed | pass (the warp also found ~1°, but walls and horizontals are snapped within 3.5°, so it reads level; the sun sits a few px off in the overlay) |
| Straight lines straight, sun round, gaps closed (sun, house corner, canopy) | pass. The sun is a true circle, and the sun, canopy, walls, door, trunk and all 8 panes are closed regions. The house corner meets. The eaves stay open, as the fixture draws them. The windows are slightly keystoned (sides lean 2–3 px over 70 px) because short wobbly sides keep their "drawn" angle | pass | pass |
| Nothing added or removed (overlay) | **fail**. No original ink is missing. The added ink (2.0k px out of 40.6k) is the sun gap closure (78 px), the hand-drawn canopy lobe (338 px) and two straight ground-line extensions out to the canvas edges (796 + 806 px, about 165 px long each in the clean PNG). The extensions are in `sketch-clean.png` and the SVG as well as the colour version, so the line art now runs edge to edge where the drawing stops short. They are disclosed. The 0.20.0 run kept them out of the line art by building sky and ground as shape layers | pass | pass (small closing extensions only; the apex X is shortened) |
| Fills in the right regions and colours; `compare.png` present | pass (all 8 hexes exact; sky and ground are `drawing fill` layers with `edge_closes`; `compare.png` 4060×1572) | pass | pass |
| **Total** | **4/5** | **4/5** | **5/5** |

The "nothing added" fail is the strictest reading of the brief, which says "Don't … change the composition". The extensions are short, straight and disclosed, but they are line work the artist didn't draw. T and C coloured the sky and ground past the line ends without adding ink.

## 3. Report honesty

- **V (2026-10-12): yes.** I checked these claims and they hold:
  - 33 traced strokes plus 3 added ones (`canopy-gap`, `ground-left`, `ground-right`, all inside the `house` group), 36 `<path>` in the SVG, no `<image>`;
  - 16 fills; all eight sampled colours are exact;
  - −2.2° tilt; the 2058 × 1576 cleaned paper scaled to 2000 × 1532; `compare.png` 4060 × 1572 at 3.1 MB;
  - stroke widths 3.7–6.6 px, median 5.1;
  - `drawing report` gives preserved 0.9999 and added 0.0577, and `check drawing` passes with no findings (I re-ran both on a copy);
  - the ground ends about 180 px from each edge (the extensions are 188 px in canvas units).

  The ground extensions and the canopy bridge are disclosed as additions.

  For round 2, these claims check out:
  - `house/fill-2` recoloured in place, and the new layer is named `chimney`, as the report says;
  - 37 strokes, 17 fills, a 3.7 px stroke, about 58 px wide;
  - `vixl_check` shows only the edge-run warnings it mentions.

  One soft spot: round 1 lists the "slightly skewed right window" under details kept as drawn. The fixture draws both windows as rectangles. The skew comes from straightening each wobbly side at its own angle.
- **C: yes.** It discloses the snapping, the 16 px added corner stroke, the canopy bridge and the shrunken apex X, and all of them check out.
- **T: partly.** Its method (hand-placed guides) is disclosed honestly. But it says the tilt was "about 1 degree" and presents the remaining ~1° wall lean as "slants kept… as drawn". The drawing's walls were vertical, so this is uncorrected tilt.

## 4. Revision (round 2): red roof `#c0392b` plus a chimney on the right slope at the same weight

| | V (0.26.0) | T | C |
| --- | --- | --- | --- |
| Roof `#c0392b` (sampled) | yes; no coral left (0 px, against 64.8k in round 1) | yes | yes |
| Chimney on the right slope, sitting on the roof line | yes. An open three-segment polyline about 58 px wide. Both feet land on the roof line with no gap or overshoot, and it has a red fill. It is 3.7 px, matching the roof lines it meets (the walls are heavier) | yes. 5.5 px, slight lean and overshoot to echo the sketch; roofR split under it | yes, 6 px with round caps and the same renderer |
| Drift outside the roof/chimney box (colour PNG diff) | 0 px. The colour diff stays inside the roof box (602,455)–(1106,717); the clean-PNG diff is the chimney outline only, in (987,527)–(1053,654); the SVG gains one path | 0 px | 0 px |
| Method | In-place edits to a copy of `drawing.vixl`, each done once with no coordinate mix-up: retarget the roof fill, add a `drawing stroke` with `space: "group"` points worked out from the roof line's endpoints, add a `drawing fill`, then re-export. In `compare.vixl` it used `replace-contents` | String edits to the SVG source, then re-render; 11 calls | New `step4_chimney.py` on `strokes.json`, plus a palette edit; 9 calls |
| Editability | **5** | **5** | **5** |
| Revision | **5** | **5** | **5** |

## Findings

- **V on 0.26.0 drops to 4/5 hard checks, and the cause is a tool gap.** The line art now has two ground extensions running to the canvas edges. `drawing fill` can now use the canvas edge (`edge_closes`), but it still cannot split the sky from the ground when the ground line stops short of the edges. So the agent drew the line out to the edges, and those lines show in the clean PNG and the SVG.
- **Otherwise V is about where it was on 0.20.0.** Its overlay matches the original most closely, and nothing is missing. But the line quality still trails C: the stroke weight is mixed, the ground and canopy are jittery, and fills sit slightly off the lines at the eaves and the canopy.
- **Round 2 was the cleanest V revision so far**: 28 calls, done in place, with no coordinate correction needed.
- **C** produced the cleanest result.
- **T**'s tilt handling relied on detected paper corners and missed half of the 2° tilt.
- **Vixl issues seen in 0.26.0** (each reproduced on a scratch copy):
  - **`edge_closes` doesn't help when the line stops short of the edge.** I removed the sky and ground fills and the two extensions, then ran `drawing report`. It lists a single `edge_regions` entry of 2,757,686 px, with sky and ground merged. There is no way to bridge a line end to the canvas edge without adding ink.
  - **Gap closing is unchanged.** I removed `canopy-gap` and re-ran `straighten`: `close_gaps: "auto"` leaves the ~60 px canopy gap open, and `close_gaps: 80` bridges it with a straight segment across a lobed outline.
  - **`drawing stroke` smooths through its points by default (`smooth: true`).** A probe polyline (100,100) → (300,100) → (300,300) came out as a bowed arch whose top edge rises to y = 83, 14 px outside the points. The chimney example in `docs/drawing.md` uses the default, so it would come out rounded. The round-2 agent turned smoothing off.
  - **Fills don't follow stroke edits.** After removing the `canopy-gap` stroke, its fill lobe stays outside the canopy outline.
  - **The `drawing` check passes with 5.8% added ink**, including the two edge-to-edge lines. It only warns about lost lines.
  - **Traced strokes keep each line's width (3.7–6.6 px) and its jitter, and the fills miss the lines in places.** The roof colour runs past the line ends at the eaves, there is a white sliver inside the canopy line on the left, and there is a 1 px pink tint outside the chimney's left side.
  - **The tilt is still over-corrected by 0.2°** (−2.2° found, 2.0° drawn). Because lines keep their drawn angles, the walls lean 0.2–0.6° and the window sides are keystoned by 2–3 px.
  - **`vectorize` splits each window cross into three strokes** (s024–s029).
- **Fixed since 0.20.0:**
  - `drawing stroke` canvas points now land correctly in a moved and scaled group. A probe stroke from (100,100) to (300,300), 6 px wide, rendered at x 97–303 and y 97–302 in a group scaled by 0.972.
  - `space: "group"` and the both-space region points from `drawing report` let the round-2 agent place the chimney right the first time.

## Changes since earlier Vixl runs

| | V on 0.18.0 (2026-10-05) | V on 0.20.0 (2026-10-06) | V on 0.26.0 (2026-10-12) |
| --- | --- | --- | --- |
| Hard checks | 4/5 (house top-left corner open) | 5/5 (corner closed) | **4/5** (ground line extended to the canvas edges in the line art) |
| Fidelity / craft | 3 / 3 | 4 / 3 | 4 / 3 |
| Report honest | partly (claimed uniform strokes; open corner not mentioned) | yes (widths and eave gap disclosed; one layer-name slip) | yes (additions disclosed; window skew called "as drawn") |
| Editability / revision | 4 / 5 (5 validation errors) | 5 / 5 (one stroke redrawn after a coordinate mix-up) | 5 / 5 (in place, first try, `space: "group"`) |
| Effort (r1 / r2 minutes) | not recorded | not recorded | 3.8 / 2.0 (39 / 28 tool calls) |

What changed in Vixl's behaviour:
- **Coordinates are fixed.** `drawing stroke` and `drawing fill` canvas points now map through moved and scaled groups, and `space: "group"` plus the both-space region points from `drawing report` made round 2 a clean first-try edit.
- **`clean`/`import` now keep the paper's extent by default** (`crop: false`).
- **`drawing fill` gained `edge_closes`,** but only for regions the lines actually close against the edge. With the ground line stopping short, the agent added ink to separate the sky from the ground, where the 0.20.0 agent built shape layers outside the drawing. That choice cost the "nothing added" check.

Still the same:
- mixed stroke weights and jittery traced curves;
- fills a little off the lines;
- the 0.2° tilt over-correction;
- the canopy gap, which `close_gaps` either leaves open or bridges with a straight segment.
