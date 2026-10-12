# T04 · Logo and icon kit: judge's notes

Lanes: V = Vixl MCP, W = hand-written SVG + Chromium. All runs were made by Claude subagents (claude-opus-5-5).

- **V** was re-run on Vixl 0.26.0 and judged on 2026-10-12 (judge: Claude, claude-opus-5-5, as a subagent).
  Effort: round 1 took 8.5 min and 87 tool calls, round 2 took 3.0 min and 40 tool calls, with no nudges.
- **W** was run and judged on 2026-10-05. Its scores and notes below are unchanged from that judging.

Only W's sources are committed, so for the 2026-10-12 judging I regenerated W's round-1 and round-2 deliverables
from `claude-W/build/` and `claude-W/round2/build/` (`make.py`, then `render.py` with Playwright Chromium) in a
scratch copy outside the repo. Both rounds rebuilt without errors. All experiments on V's sources also ran on
scratch copies (a mirror of the workspace layout, so the round-1 sheet's workspace-path links resolve).

## 1. Blind scores

### V on Vixl 0.26.0 (2026-10-12, written down before opening key.csv)

I ran `inspect_outputs.py --blind` over the scratch copy (V and regenerated W, both rounds). I rendered every SVG
with resvg on cream, looked at each sheet, and checked each mark and the favicon's 16 px layer at 16 × 16 px,
enlarged with nearest-neighbour. As before, the rounds were easy to tell apart from the brand text, and W's codes
carry a `build/` folder, so this pass was only partly blind.

| Code | Fidelity | Craft | Reason |
| --- | --- | --- | --- |
| ADHZ | 5 | 4 | All seven files. A navy disc holding an amber flame with two trapezoid beams, over one heavy amber wave: lamp, lighthouse light and water. Fraunces-style serif wordmark with a light tracked caps tagline. The sheet is clean, with every version on both halves and 16/32/64 at real size. Minus: the beams are blunt wedges (a bit bow-tie), the reversed amber disc on navy reads slightly like a face, at 16 px the mark is a disc with a bright blob, two bars and a stripe (recognizable but soft), and the "Stacked lockup" label sits about 3 px above the app icon tile. |
| A4WX (r2) | 5 | 4 | The same mark with "Tidewick & Co." and "COFFEE · BAKERY · HARBOR". The mark is untouched and the sheet is laid out again, which also fixes the crowded label. The horizontal lockup is very wide (3.9:1), and its tagline is small next to the long wordmark. |
| E8TQ | 4 | 3 | (regenerated W r1, for reference only) Drop, rays and a double wave. Generic DejaVu serif. The bottom wave in mark.svg and mark-mono.svg touches the viewBox edge and is clipped. At 16 px the rays and the two waves turn into texture. |
| SH0I | 4 | 3 | (regenerated W r2, for reference only) Same as E8TQ, renamed. The stacked lockup is top-light; the horizontal mark is small next to the long name. |

Key: ADHZ = V r1, A4WX = V r2, E8TQ = W r1, SH0I = W r2. My blind W scores are a point lower than the
2026-10-05 scores, the same as the 2026-10-06 judge's. I left W's official scores as they were, as instructed.

### Earlier blind scores of V (2026-10-06, Vixl 0.20.0, replaced)

| Code | Fidelity | Craft | Reason |
| --- | --- | --- | --- |
| YYOO | 5 | 4 | (V on Vixl 0.20.0, replaced) A leaning amber flame with a navy core over one bold navy wave, with no disc. It read at 16 px (flame over wave). Fraunces-style serif wordmark with a light caps tagline; clean sheet. Minus: the flame alone can read as a drop, and the bottom of the sheet is sparse. |
| J6JO (r2) | 5 | 4 | (V on Vixl 0.20.0, replaced) The same mark with the new name and tagline; very wide horizontal lockup. |

### Earlier blind scores (2026-10-05)

I rendered every SVG in headless Chromium (Playwright, from a data: URI, so nothing loaded from disk) and in Inkscape 1.x. The two renderers differ by less than 1 % RMSE on every round-1 SVG. There are no `<text>` elements anywhere, so system fonts can't change the output. I also checked each mark at 16 × 16 px in Chromium and at the 16 px favicon layer.

| Code | Fidelity | Craft | Reason |
| --- | --- | --- | --- |
| Q9L3 | 5 | 4 | Every deliverable is there, and the sheet shows every version on both cream and navy plus real-size 16/32/64 marks. The drop with rays over waves reads as lamp light on water and still reads at 16 px. Mono uses the same silhouette. The wordmark serif looks generic and default, and the sheet has dead space. |
| VPK7 | 4 | 4 | (V on Vixl 0.18.0, replaced) Better type pairing and a more polished sheet. The flame in a disc over a wave reads as lamp plus water. But the navy half of the sheet leaves out the mono mark. The mark's identity shifts between a disc and no disc. The wave ribbon ends bluntly inside the disc. The outlined mono mark turns to mush at 16 px. |
| ALT7 (r2) | 5 | 4 | Name and tagline are updated in every lockup, the mark is untouched, and the long name balances in both lockups. |
| MLJ5 (r2) | 4 | 4 | (V on Vixl 0.18.0, replaced) Name and tagline are updated. The sheet has the same omission as VPK7. The mark is unchanged. |

Key: Q9L3 = W r1, VPK7 = V r1, ALT7 = W r2, MLJ5 = V r2.

## 2. Hard checks (round 1)

V is from `inspect_outputs.py` plus my own measurements (2026-10-12). W is from 2026-10-05.

| Check | V (claude-V, Vixl 0.26.0) | W (claude-W) |
| --- | --- | --- |
| All seven files exist | PASS | PASS |
| SVGs: embedded_images=0, text_elements=0 | PASS: all four are 0/0, with no `@font-face`, no comments and no leftover `${` | PASS: all 0/0 |
| Same render without the fonts | PASS: glyphs are outlined (28 paths per lockup). resvg vs Chromium (data: URI) differ on at most 0.038 % of pixels in every SVG of both rounds. | PASS: outlined glyphs; Chromium and Inkscape agree (RMSE < 1 %) |
| favicon.ico has 16/32/48 | PASS | PASS |
| app-icon 1024², RGB, square corners | PASS: mode RGB, all four corners navy (20,38,59), full bleed. The amber parts are centered horizontally (x 191–833) and sit at y 255–754. | PASS: RGB, corner pixels are navy (20,38,59) |
| logo-sheet 1600×1200 with every version on cream and navy, plus 16/32/64 | PASS: 1600×1200 RGB. Both halves show horizontal, stacked, mark and mono (a cream knockout on navy), and the mark at 16/32/64 px (link layers at those exact sizes). The cream half also shows the app icon. | PASS: every version on both halves, with color and mono at 1:1 at 16/32/64 |
| Mark recognizable at 16 px, ≤ 2 colors, mono navy only | PASS: at 16 px it reads as a navy disc with a bright lamp, a bar on each side and a wave line; the flame notch is lost. mark.svg fills are rgb(20,38,59) and rgb(242,165,65) only. mark-mono.svg is one rgb(20,38,59) even-odd path with the flame, beams and wave cut out. | PASS: the drop and waves read at 16 px. mark.svg is #14263b and #f2a541; mark-mono.svg is #14263b only. |
| Wordmark and tagline spelled exactly | PASS: "Tidewick"; the tagline is stored as "Coffee by the harbor" and drawn in caps with `text_transform: uppercase` (disclosed) | PASS: "Tidewick", "COFFEE BY THE HARBOR". The letters are exact, set in all caps as a style; the report discloses this. |
| **Total** | **8/8** | **8/8** |

## 3. Report honesty

- **V (2026-10-12): yes.** I checked the claims against the files and the `.vixl` sources (with the `vixl` CLI):
  canvas sizes (1240×400, 900×655, 512²), 28 glyph paths per lockup and one compound path in the mono mark,
  Fraunces 172 px and Work Sans 40 px with tracking 5, the document variables (`disc`, `fg`, `ink`, `tag`) and
  the sheet's 11 link layers with reversed variable values on the navy half, the 16/32/64 links at exact pixel
  sizes, the four pre-rendered lockup PNGs (760×245 and 460×335), ICO 16/32/48, the RGB modes, and strict SVGs with
  no `<text>` or `<image>`. Rendering `src/logo-sheet.vixl` matches `logo-sheet.png` pixel for pixel. The design
  check has no "fix" findings, as claimed: 3 safe-area reviews and 1 informational legibility note. The tracking bug
  the report describes is real (see "Vixl bugs and gaps reproduced"). Small inexactnesses: the two cream lockup images sit 40 px from the top,
  not 20 px; and "about 20 px below the optical centre" for the app icon is a judgement call (the amber bounding box
  is centered at y 504.5 of 1024, so it is 7.5 px above the geometric centre).
- **V round 2: yes.** The canvases are 1554×400 and 1140×627. The wordmark is 150 px (horizontal) and 140 px
  (stacked), the tagline baseline is 296, the stacked mark moved 120 px right, and the right margin is 51 px.
  My resvg ink measurements agree with the report within 2 px (horizontal ink 50–1503; stacked wordmark 55–1081,
  tagline 239–895, both centered at 567–568). Mark, mono, favicon and app icon are byte-identical to round 1. The
  sheet's 11 links now point at `round2/src/` (stored as document-relative `mark.vixl` etc.), the horizontal lockup
  image is 940 px wide and the stacked one 460 px, and the stacked labels moved up (y 385 → 303). Small
  inexactnesses: "vixl_check passes on both lockups with no findings" leaves out one informational legibility note
  on the horizontal tagline at thumbnail size; and the mark-to-wordmark gap is about 51–53 px of ink in both rounds,
  not "about 59 px" (it is the same in both rounds, which is the point of the claim).
- **W (2026-10-05): yes.** The report's file modes (RGB app icon, ICO sizes), the sheet contents, the DejaVu fonts, the all-caps tagline, the three-color app icon tile and the cream favicon tile all match the files. It flags its own odd 2-minute timing instead of hiding it.

## 4. Round 2 ("Tidewick & Co." / "Coffee · Bakery · Harbor")

- **Mark unchanged:** V's mark.svg, mark-mono.svg, favicon.ico and app-icon-1024.png are byte-identical to round 1 (`cmp`),
  and so are their `.vixl` sources. In both lockups, the mark region renders with 0 changed pixels against round 1
  (the stacked one after allowing for its 120 px re-centering), and the sheet's mark, mono and 16/32/64 areas on both
  halves have 0 changed pixels. W's mark.svg and mark-mono.svg differ from round 1 only in `<title>`, and the path data is identical. W's favicon.ico and app-icon-1024.png are byte-identical to round 1. W's lockups keep the mark and fonts; only the viewBox width and the glyph paths changed.
- **V (2026-10-12):** it copied the sources to `round2/src/` and changed only the wordmark and tagline with `text-set`.
  The longer name didn't fit, so it reduced the wordmark from 172 px to 150 px (horizontal) and 140 px (stacked),
  widened both canvases, moved the stacked mark to stay centered and re-exported. The tagline keeps its font, size,
  tracking and caps. The sheet needed more work: because its lockups are pre-rendered PNGs (the workaround for the
  tracking bug), the agent re-exported four lockup PNGs, removed the old image layers, imported and placed the new
  ones, moved the stacked labels, and relinked the 11 mark/mono/app-icon links to `round2/src/`. No mark or size
  sample moved. Every file is still editable (live text in the lockups, live links for the marks).
  editability 4 (lockups changed in place; the sheet's lockup images had to be redone by hand), revision 5.
- **W (2026-10-05):** copied `build/`, changed the two strings and the titles in `make.py`, escaped `&` in titles, widened one display width in `sheet.html`, and reran. The tagline stays in caps, consistent with round 1 and disclosed. The stacked lockup is a little top-light with the longer name. editability 5, revision 5.

## Summary

| Lane | Date | Hard | Fidelity | Craft | Honest | Editability | Revision | Minutes (r1 / r2) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| V (Vixl 0.26.0) | 2026-10-12 | 8/8 | 5 | 4 | yes | 4 | 5 | 8.5 / 3.0 |
| W | 2026-10-05 | 8/8 | 5 | 4 | yes | 5 | 5 | — |

Findings:
- On 0.26.0, Vixl again passes every hard check: outlined strict SVGs that agree across renderers, a true RGB app
  icon, a complete sheet, and a two-color mark with a one-path navy mono.
- Vixl still has the better type (Fraunces and Work Sans via `vixl_font_pair`), and it now keeps the tagline text
  exact and draws the caps with `text_transform`.
- The new mark puts the flame, beams and wave inside a disc. It holds together at 16 px but is softer there than
  0.20.0's open flame-over-wave mark, and it is closer to the disc design of the 0.18.0 run.
- Live link layers can't be trusted to draw letter-spaced text at a reduced scale (see "Vixl bugs and gaps reproduced"). The agent noticed,
  worked around it with pre-rendered PNGs, and disclosed it, but the workaround cost round 2 a manual rebuild of the
  sheet's lockups.

## Changes since earlier Vixl runs

| | 0.18.0 (2026-10-05) | 0.20.0 (2026-10-06) | 0.26.0 (2026-10-12) |
| --- | --- | --- | --- |
| Hard checks | 6/8 | 8/8 | 8/8 |
| Fidelity / craft | 4 / 4 | 5 / 4 | 5 / 4 |
| Report honest | yes | yes | yes |
| Editability / revision | 5 / 5 | 5 / 5 | 4 / 5 |

Scores are flat against 0.20.0 apart from editability. The 0.26.0 agent went back to a disc mark (flame with two
beams over one wave inside a navy disc), which reads as a lighthouse lamp but is softer at 16 px than 0.20.0's open
flame-over-wave. The tagline is now stored exactly and uppercased by a style. On 0.20.0 the whole sheet was live
links, so round 2 only had to repoint them. On 0.26.0 the lockups on the sheet are pre-rendered PNGs, because live
links drew the tracked tagline too wide, so round 2 had to re-export and swap four images (editability 5 → 4).
Round 2 also shrank the wordmark to fit the longer name instead of only widening the canvas. The SVG exports still
carry no-op `stroke="rgb(0,0,0)" stroke-opacity="0.0" stroke-width="1"` attributes on every shape.

## Vixl bugs and gaps reproduced (2026-10-12, on scratch copies)

- **Link layers and scaled previews ignore `tracking` when they scale a text document (confirmed).** A 760×245 link
  layer to a copy of `src/logo-horizontal.vixl` (scale 0.613) draws the tagline 609 px wide (x 35–644), while
  `vixl render --scale 0.6129` of the same document draws it 566 px wide (x 35–601), which is the correct scaled
  width. A 460×335 link to the stacked lockup (scale 0.511) draws the tagline 338 px wide against 297 px exported.
  It grows to the right, so the tagline goes off-center and is clipped when the frame is tight (the agent's "COFFEE BY
  THE HAR"). `proxy.preview_png` at 620 px wide (scale 0.5) shows the same: the tagline ends at x 538 instead of
  about 490. Cause: `proxy._scale_layer` (used by `links.py` and `render_preview` through `scaled_project`) scales
  text `size`, `spacing` and rich-text span `tracking`, but not a plain text layer's top-level `tracking`.
- **`vixl dependencies` doesn't list link-layer sources.** On `src/logo-sheet.vixl`, which has 11 link layers,
  `"linked"` is empty: `validation.dependencies` only looks at raster layers' `linked` field, not link layers'
  `source`. It also lists the same font file 11 times.
- **Link sources are stored as workspace paths.** The round-1 sheet stores `evals/tool-comparison/runs/T04/claude-V/src/mark.vixl`,
  so a copied sheet still points at the old sources (the same as on 0.20.0). The round-2 agent's `links-relink`
  stored document-relative paths, which travel with the folder.
- **Minor:** no-op strokes in SVG export (above); `vixl_check` keeps flagging the sheet's 18 px labels as thumbnail
  legibility notes (now informational, not "fix").
