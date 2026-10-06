# T11 · Hand drawing to clean art: judge notes

Runs: claude-V, claude-T, claude-C (round 1 + round2/).

- **V lane: re-run on Vixl 0.20.0, judged 2026-10-06** (claude-opus-5-5 subagent).
- **T and C lanes: run and judged 2026-10-05** (claude-opus-5-5 subagent). Their notes and scores below are unchanged.

For the 2026-10-06 judging, the T and C deliverables were regenerated from their committed sources in a scratch copy outside the repo. C's scripts ran with only the fixture path changed, and its `strokes.json` matched the committed one up to float rounding. T's `run.sh` and `round2/scripts/round2.py` ran after Inkscape was installed, and its `geom.json` matched to 2e-12. All six runs then went through `inspect_outputs.py --blind` together.

## 1. Blind scores (written before opening key.csv)

### V on Vixl 0.20.0 (2026-10-06)

| Code | Fidelity | Craft | Reason |
| --- | --- | --- | --- |
| 3RDZ | 4 | 3 | Everything is there and the required gaps are closed: the sun, the house top-left corner and the canopy. Tilt is fixed, the walls are vertical, the rays keep their drawn angles, and all eight colours are exact. Craft problems: the ground line and canopy edge are stair-stepped at pixel level, and stroke weight varies (thin roof and sun, heavier walls). There is a small amber fringe outside the sun circle, and at the eaves the roof colour ends with no black line. |

Round 2: RKQ0 (red roof plus a plain rectangular chimney; nothing else moved).

My blind re-look at the regenerated T and C files agreed with their 2026-10-05 scores to within one point, so those scores stand.

### T and C (2026-10-05, unchanged)

Round-1 codes are the three with a coral roof.

| Code | Fidelity | Craft | Reason |
| --- | --- | --- | --- |
| 74SD | 4 | 5 | Tilt fixed, walls vertical. Sun, house corner and canopy all closed. Rays keep their drawn angles. Consistent 6 px stroke. The ridge X is reduced to an apex point and the wall-top line is merged into the eave. |
| FNGM | 4 | 4 | All gaps closed, ridge X kept, two-line trunk. About 0.8° of wall lean remains and the windows are skewed. Tiny coral slivers sit outside the eave corners. |

Key: 3RDZ = **V** (2026-10-06; round 2 RKQ0). 74SD = **C**, FNGM = **T** (2026-10-05; round 2: VFF7 = C, PK8U = T).

## 2. Hard checks (round 1)

Ground truth comes from `fixtures/make_fixtures.py`: the drawing is rotated by exactly 2.0°, with walls at x = 600 and 1100. The roof lines are drawn as eaves that overhang the walls: at y = 700 the left roof line is at x ≈ 582, so the wall-top line was never meant to touch the roof.

For V (2026-10-06), I registered the photo's ink onto `sketch-clean.png` with a Euclidean ECC fit. This gave a −2.20° rotation and a (−27, 40) px shift. I then flagged ink further than 12 px from the other image's ink, and I flood-filled the clean PNG to check which regions are closed.

| Check | V (0.20.0) | T | C |
| --- | --- | --- | --- |
| SVG: `embedded_images=0`, vector strokes | pass (34 `<path>`, pure black, plus a white rect) | pass (29 `<line>`, circle, polygon, polyline) | pass (25 paths + circle) |
| Clean PNG: black on white, 2000 wide, tilt corrected, paper and desk gone | pass (2000×1500 RGB, `#000` on `#fff` with antialiasing. `drawing import` found the paper on the full photo and corrected −2.2°, about 0.2° more than needed; snapped lines hide the difference) | **fail**: the paper-corner warp found only ~1°. Walls in the clean PNG lean ~0.8° (x 594→599 over rows 760–1080) and the windows are skewed | pass (the warp also found ~1°, but walls and horizontals are snapped within 3.5°, so it reads level; the sun sits a few px off in the overlay) |
| Straight lines straight, sun round, gaps closed (sun, house corner, canopy) | pass. The sun is a true circle; the sun, canopy, walls, door, trunk and all 8 panes are closed regions. The house top-left corner now meets. The eaves stay open by ~19 px, as the fixture draws them | pass | pass |
| Nothing added or removed (overlay) | pass (no original ink is missing. The only added ink is the sun gap closure (87 px) and the hand-drawn canopy lobe (340 px), out of 41.6k ink px) | pass | pass (small closing extensions only; the apex X is shortened) |
| Fills in the right regions and colours; `compare.png` present | pass (all 8 hexes exact; sky and ground are shape layers that follow the ground line; `compare.png` 4040×1500) | pass | pass |
| **Total** | **5/5** | **4/5** | **5/5** |

## 3. Report honesty

- **V (2026-10-06): yes.** I checked these claims and they hold:
  - 34 strokes in the SVG, with no `<image>` or base64 data;
  - the colours are exact, and the stroke widths are 3.7–6.6 px "as drawn";
  - −2.2° tilt; the `crop:false` re-clean; the 78 px canopy gap replaced by an added lobe;
  - sky and ground are shape layers;
  - the ~19 px wall-top-to-roof gap is covered only by fill, and the report says so itself.

  For round 2, the change boxes it gives match my pixel diff: colour (587,427)–(1110,699), clean (977,497)–(1042,622). The 35 paths, the 5.0 px chimney and its canvas points also check out.

  One slip: the report calls the new layer `house/chimney`, but it is named `chimney` (inside the `house` group).
- **C: yes.** It discloses the snapping, the 16 px added corner stroke, the canopy bridge and the shrunken apex X, and all of them check out.
- **T: partly.** Its method (hand-placed guides) is disclosed honestly. But it says the tilt was "about 1 degree" and presents the remaining ~1° wall lean as "slants kept… as drawn". The drawing's walls were vertical, so this is uncorrected tilt.

## 4. Revision (round 2): red roof `#c0392b` plus a chimney on the right slope at the same weight

| | V (0.20.0) | T | C |
| --- | --- | --- | --- |
| Roof `#c0392b` (sampled) | yes; no coral left | yes | yes |
| Chimney on the right slope, sitting on the roof line | yes. A 60 px rectangle with feet on the traced roof line and a red fill. It is 5 px, the drawing's median weight: it matches the walls but is a little heavier than the 3.7–4 px roof lines it sits on | yes. 5.5 px, slight lean and overshoot to echo the sketch; roofR split under it | yes, 6 px with round caps and the same renderer |
| Drift outside the roof/chimney box (colour PNG diff) | 0 px (the clean-PNG diff is the chimney outline only) | 0 px | 0 px |
| Method | In-place edits to a copy of `sketch.vixl`: retarget the roof fill, `drawing stroke`, `drawing fill`, re-save comps, re-export. One stroke was redrawn because `drawing stroke` takes canvas coordinates and the house group is offset by (−29, −38) | String edits to the SVG source, then re-render; 11 calls | New `step4_chimney.py` on `strokes.json`, plus a palette edit; 9 calls |
| Editability | **5** | **5** | **5** |
| Revision | **5** | **5** | **5** |

## Findings

- **V on 0.20.0 now passes every hard check.** It is still the lane whose overlay matches the original most closely, but its line quality trails C. The ground and canopy are stair-stepped, the stroke weight is mixed, and the fills sit slightly off the straightened lines.
- **C** produced the cleanest result.
- **T**'s tilt handling relied on detected paper corners and missed half of the 2° tilt.
- **Vixl issues still seen in 0.20.0:**
  - **Coordinate spaces are mixed.** `drawing stroke` takes canvas coordinates, while the stroke layers live in the drawing group's parent space. Here the group was at (−29, −38), so the first chimney landed in the wrong place. `drawing-report` region points also did not line up with canvas coordinates after the group was moved.
  - **`drawing fill` will not fill an area bounded by the canvas edge.** The ground line stops ~150 px short of each side, so sky and ground had to be hand-built shape layers.
  - **`close_gaps: 80` bridged the 78 px canopy gap with a straight segment.** That is wrong on a lobed outline, so the agent drew a lobe by hand.
  - **Fills come out slightly off the cleaned lines.** There is an amber fringe outside the straightened sun circle, and the roof colour reaches past the line ends at the eaves.
  - **Traced strokes are not smooth.** The centreline trace keeps pixel steps on the ground and canopy, and stroke widths vary per stroke (3.7–6.6 px).
  - **`clean`'s default crop cuts tight around the ink.** That changes the composition; `crop:false` was needed.
- Round 2 was clean in every lane.

## Changes since the Vixl 0.18.0 run

| | V on 0.18.0 (2026-10-05) | V on 0.20.0 (2026-10-06) |
| --- | --- | --- |
| Hard checks | 4/5 (house top-left corner open) | **5/5** (corner closed) |
| Fidelity / craft | 3 / 3 | **4** / 3 |
| Report honest | partly (claimed uniform strokes; open corner not mentioned) | **yes** (widths and eave gap disclosed; one layer-name slip) |
| Editability / revision | 4 / 5 (5 validation errors) | **5** / 5 (one stroke redrawn after a coordinate mix-up) |

What changed in Vixl's behaviour:
- `drawing import` now finds the paper and the tilt on the full photo. On 0.18.0 it traced the desk strips as ink and reported 0°, so the agent had to crop by hand.
- `straighten` with `angles: "axes"` keeps diagonal rays at their drawn angles; 0.18.0 snapped them to 45°.
- The house corner gap now closes.

Still the same: mixed stroke weights, jagged traced curves, and the canopy gap, which needs manual work.
