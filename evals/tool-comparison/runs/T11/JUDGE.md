# T11 · Hand drawing to clean art: judge notes

Judge: claude-opus-5-5 subagent, 2026-10-05. Runs: claude-V, claude-T, claude-C (round 1 + round2/).

## 1. Blind scores (written before opening key.csv)

Round-1 codes are the three with a coral roof.

| Code | Fidelity | Craft | Reason |
| --- | --- | --- | --- |
| 74SD | 4 | 5 | Tilt fixed, walls vertical. Sun, house corner and canopy all closed. Rays keep their drawn angles. Consistent 6 px stroke. The ridge X is reduced to an apex point and the wall-top line is merged into the eave. |
| FNGM | 4 | 4 | All gaps closed, ridge X kept, two-line trunk. About 0.8° of wall lean remains and the windows are skewed. Tiny coral slivers sit outside the eave corners. |
| WI9I | 3 | 3 | The house top-left corner gap is **not** closed. The sun rays are regularised to an exact 45° grid. Stroke weight varies (thin roof and sun, thick canopy and trunk lines). The ground line and canopy edge are jagged. |

Key: 74SD = **C**, FNGM = **T**, WI9I = **V** (round 2: VFF7 = C, PK8U = T, 9082 = V).

## 2. Hard checks (round 1)

Ground truth comes from `fixtures/make_fixtures.py`: the drawing is rotated by exactly 2.0°, with walls at x = 600 and 1100. I de-rotated the photo by −2° and overlaid each `sketch-clean.png` on it, fitting scale and offset from the four wall and door verticals.

| Check | V | T | C |
| --- | --- | --- | --- |
| SVG: `embedded_images=0`, vector strokes | pass (34 paths) | pass (29 `<line>`, circle, polygon, polyline) | pass (25 paths + circle) |
| Clean PNG: black on white, 2000 wide, tilt corrected, paper and desk gone | pass (2000×1450; −2.2° corrected after a manual crop) | **fail**: the paper-corner warp found only ~1°. Walls in the clean PNG lean ~0.8° (x 594→599 over rows 760–1080) and the windows are skewed | pass (the warp also found ~1°, but walls and horizontals are snapped within 3.5°, so it reads level; the sun sits a few px off in the overlay) |
| Straight lines straight, sun round, gaps closed (sun, house corner, canopy) | **fail**: the house top-left corner is still open (wall top and top line don't meet, see the zoom). Sun and canopy are closed. | pass | pass |
| Nothing added or removed (overlay) | pass (near pixel-exact overlay; only the 80 px canopy bridge added) | pass | pass (small closing extensions only; the apex X is shortened) |
| Fills in the right regions and colours; `compare.png` present | pass (all 8 hexes exact) | pass | pass |
| **Total** | **4/5** | **4/5** | **5/5** |

## 3. Report honesty

- **C: yes.** It discloses the snapping, the 16 px added corner stroke, the canopy bridge and the shrunken apex X, and all of them check out.
- **T: partly.** Its method (hand-placed guides) is disclosed honestly. But it says the tilt was "about 1 degree" and presents the remaining ~1° wall lean as "slants kept… as drawn". The drawing's walls were vertical, so this is uncorrected tilt.
- **V: partly.** It says lines are "uniform-width vector strokes" and that `straighten close_gaps:30` ran on the house walls. In fact strokes measure 3 to 6 px (the round-2 report itself says the roof is 3 px and the walls 5 px), and the house-corner gap is still open but not mentioned. It does disclose the failed first import.

## 4. Revision (round 2): red roof `#c0392b` plus a chimney on the right slope at the same weight

| | V | T | C |
| --- | --- | --- | --- |
| Roof `#c0392b` (sampled) | yes | yes | yes |
| Chimney on the right slope, sitting on the roof line | yes, 3 px to match V's roof lines | yes. 5.5 px, slight lean and overshoot to echo the sketch; roofR split under it | yes, 6 px with round caps and the same renderer |
| Drift outside the roof/chimney box (colour PNG diff) | 0 px | 0 px | 0 px |
| Method | In-place edits to `sketch.vixl` (refill the roof, `drawing stroke`, then `straighten`); 44 calls including 5 validation errors | String edits to the SVG source, then re-render; 11 calls | New `step4_chimney.py` on `strokes.json`, plus a palette edit; 9 calls |
| Editability | **4** | **5** | **5** |
| Revision | **5** | **5** | **5** |

## Findings
- C produced the cleanest result. T's tilt handling relied on detected paper corners and missed half of the 2° tilt. V was the only lane whose overlay matched the original almost pixel for pixel, but it left a required gap open.
- Vixl-specific gaps:
  - On the full photo, `drawing import` traced the desk strips as ink and reported 0° tilt. The agent had to crop inside the paper by hand first.
  - `straighten close_gaps` did not close the house corner.
  - Centreline vectorisation gave mixed stroke widths of 3 to 6 px.
  - It snapped the sun rays to exact 45° angles, which changes the drawing's character.
- Round 2 was clean in every lane. Vixl's layered document handled it in place, at a higher call count.
