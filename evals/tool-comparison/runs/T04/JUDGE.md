# T04 · Logo and icon kit: judge's notes

Lanes: V = Vixl MCP, W = hand-written SVG + Chromium. All runs were made by Claude subagents (claude-opus-5-5).

- **V** was re-run on Vixl 0.20.0 and judged on 2026-10-06 (judge: Claude, claude-opus-5-5, as a subagent).
- **W** was run and judged on 2026-10-05. Its scores and notes below are unchanged from that judging.

Only W's sources are committed, so for the 2026-10-06 judging I regenerated W's round-1 and round-2 deliverables
from `claude-W/build/` and `claude-W/round2/build/` (`make.py`, then `render.py` with Playwright Chromium) in a
scratch copy outside the repo. Both rounds rebuilt without errors.

## 1. Blind scores

### V on Vixl 0.20.0 (2026-10-06, written down before opening key.csv)

I ran `inspect_outputs.py --blind` over the scratch copy (V and regenerated W, both rounds). I rendered every SVG
with resvg, and checked each mark at 16 × 16 px on cream and the 16 px favicon layer, enlarged with nearest-neighbour.
The rounds were easy to tell apart from the brand text, and W's codes carry a `build/` folder, so this pass was
only partly blind.

| Code | Fidelity | Craft | Reason |
| --- | --- | --- | --- |
| YYOO | 5 | 4 | All seven files. A leaning amber flame with a navy core over one bold navy wave: it reads as lamp light over water, and it still reads at 16 px (flame over wave; the core blurs to a dot). Fraunces-style serif wordmark with a light caps tagline. The sheet is clean, with every version on both halves and 16/32/64 at real size. Minus: the flame alone can read as a drop, and the bottom of the sheet is sparse. |
| J6JO (r2) | 5 | 4 | The same mark with "Tidewick & Co." and "COFFEE · BAKERY · HARBOR". The mark is untouched and the sheet is laid out again cleanly. The horizontal lockup is now very wide, and its tagline is small next to the long wordmark. |
| ZPAO | 4 | 3 | (regenerated W r1, for reference only) Flame, rays and a double wave. Generic DejaVu serif. The bottom wave in mark.svg touches the viewBox edge and is clipped by about 1 unit. At 16 px the rays and the two waves turn into texture. |
| BTMG | 4 | 3 | (regenerated W r2, for reference only) Same as ZPAO, renamed. The stacked lockup is top-light. |

Key: YYOO = V r1, J6JO = V r2, ZPAO = W r1, BTMG = W r2. My blind W scores are a point lower than the
2026-10-05 scores. I left W's official scores as they were, as instructed.

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

V is from `inspect_outputs.py` plus my own measurements (2026-10-06). W is from 2026-10-05.

| Check | V (claude-V, Vixl 0.20.0) | W (claude-W) |
| --- | --- | --- |
| All seven files exist | PASS | PASS |
| SVGs: embedded_images=0, text_elements=0 | PASS: all four are 0/0, with no `@font-face` and no comments | PASS: all 0/0 |
| Same render without the fonts | PASS: glyphs are outlined. resvg vs Chromium differ on at most 0.07 % of pixels, and resvg vs cairosvg on at most 0.02 %. | PASS: outlined glyphs; Chromium and Inkscape agree (RMSE < 1 %) |
| favicon.ico has 16/32/48 | PASS | PASS |
| app-icon 1024², RGB, square corners | PASS: mode RGB, all four corners navy (20,38,59), full bleed | PASS: RGB, corner pixels are navy (20,38,59) |
| logo-sheet 1600×1200 with every version on cream and navy, plus 16/32/64 | PASS: 1600×1200 RGB. Both halves show horizontal, stacked, mark and mono (a cream knockout on navy), and the mark at 16/32/64 px. | PASS: every version on both halves, with color and mono at 1:1 at 16/32/64 |
| Mark recognizable at 16 px, ≤ 2 colors, mono navy only | PASS: flame over wave reads at 16 px. mark.svg fills are rgb(20,38,59) and rgb(242,165,65) only. mark-mono.svg is rgb(20,38,59) only, with the core as an even-odd hole. | PASS: the drop and waves read at 16 px. mark.svg is #14263b and #f2a541; mark-mono.svg is #14263b only. |
| Wordmark and tagline spelled exactly | PASS: "Tidewick", "COFFEE BY THE HARBOR" (caps as a style, disclosed) | PASS: "Tidewick", "COFFEE BY THE HARBOR". The letters are exact, set in all caps as a style; the report discloses this. |
| **Total** | **8/8** | **8/8** |

## 3. Report honesty

- **V (2026-10-06): yes.** I checked the claims against the files and the `.vixl` sources (with the `vixl` Python API):
  canvas sizes (512², 1164×392, 834×627), the mark scales in the logos (×0.62), the favicon (×0.92) and the app icon (×1.25,
  centered), Fraunces at 160 px and Work Sans at 40 px, about 50 px margins, ICO 16/32/48, the RGB modes, 14 live link layers
  on the sheet with `ink=#f7f1e5` on the navy half, strict SVGs with no `<text>`, `<image>`, `@font-face` or leftover `${`,
  the 58 px wave stroke, and the pathfinder hole in the mono mark. Rendering the sources matches the exported PNGs
  pixel for pixel. One small inexactness: the report says the navy in mark, mark-mono and the logos "comes from `${ink}`",
  but the flame core is a literal `#14263b`. Only the wave and lettering use the variable. This doesn't change any output.
  The legibility warnings on the sheet labels that the report mentions are real: there are 10, all on the 14–18 px labels.
- **V round 2: yes.** The canvases are 1608×392 and 1274×627. The mark, mono, favicon and app icon are byte-identical
  to round 1. The 14 links point at `round2/src/`. The link boxes are 640×156 at y=106 and 581×286, centered. The
  stacked wordmark has 50 px side margins, and the vertical positions are unchanged. "vixl_check passes with 0 issues" is
  true for the checks the report names (bounds, overlap, fonts, links). The full check also gives one legibility warning
  on the round-2 horizontal tagline at thumbnail size, which the report doesn't mention.
- **W (2026-10-05): yes.** The report's file modes (RGB app icon, ICO sizes), the sheet contents, the DejaVu fonts, the all-caps tagline, the three-color app icon tile and the cream favicon tile all match the files. It flags its own odd 2-minute timing instead of hiding it.

## 4. Round 2 ("Tidewick & Co." / "Coffee · Bakery · Harbor")

- **Mark unchanged:** V's mark.svg, mark-mono.svg, favicon.ico and app-icon-1024.png are byte-identical to round 1 (`cmp`),
  and so are their `.vixl` sources. In both lockups, the mark region renders with 0 changed pixels against round 1
  (the stacked one after allowing for its new centering offset). W's mark.svg and mark-mono.svg differ from round 1 only in `<title>`, and the path data is identical. W's favicon.ico and app-icon-1024.png are byte-identical to round 1. W's lockups keep the mark and fonts; only the viewBox width and the glyph paths changed.
- **V (2026-10-06):** it copied the sources to `round2/src/` and changed only the wordmark and tagline with `text-set`,
  keeping the same fonts and sizes. It widened both canvases, re-centered the stacked lockup, and re-exported. Because
  the sheet's links are stored as workspace paths (`…/claude-V/src/…`), the copied sheet still pointed at round 1. The
  agent repointed all 14 links to `round2/src/` and resized the two lockup boxes; no other sheet layer moved.
  The tagline stays in caps, consistent with round 1, and every file is still editable (live text, live links).
  editability 5, revision 5.
- **W (2026-10-05):** copied `build/`, changed the two strings and the titles in `make.py`, escaped `&` in titles, widened one display width in `sheet.html`, and reran. The tagline stays in caps, consistent with round 1 and disclosed. The stacked lockup is a little top-light with the longer name. editability 5, revision 5.

## Summary

| Lane | Date | Hard | Fidelity | Craft | Honest | Editability | Revision |
| --- | --- | --- | --- | --- | --- | --- | --- |
| V (Vixl 0.20.0) | 2026-10-06 | 8/8 | 5 | 4 | yes | 5 | 5 |
| W | 2026-10-05 | 8/8 | 5 | 4 | yes | 5 | 5 |

Findings:
- On 0.20.0, Vixl passes every hard check. The app icon exports as true RGB (`alpha="flatten"`), and the sheet shows every version on both halves.
- Vixl still has the better type: Fraunces and Work Sans, installed with `vixl_font_pair`. W fell back to DejaVu.
- V's new mark (one flame, one wave) is simpler than W's (rays and two waves), and it holds up at least as well at 16 px.
- Both lanes handled round 2 cleanly and left the mark untouched. V's sheet is built from live links, which made the
  rename propagate. It also meant 14 links had to be repointed by hand, because the copied sheet still pointed at the
  round-1 sources.

## Changes since the Vixl 0.18.0 run

| | V on 0.18.0 (2026-10-05) | V on 0.20.0 (2026-10-06) |
| --- | --- | --- |
| Hard checks | 6/8 | 8/8 |
| Fidelity / craft | 4 / 4 | 5 / 4 |
| Report honest | yes | yes |
| Editability / revision | 5 / 5 | 5 / 5 |

- **App icon:** it was RGBA (alpha 255) and failed. It is now RGB via `alpha="flatten"`, and it passes.
- **Sheet:** mono was missing from the navy half, which failed. Now every version is on both halves, built from live
  links with a color variable (`ink`) for the reversed versions.
- **Mark:** it was a flame in a navy disc over an amber wave, with an outlined mono mark that blurred at 16 px. It is now
  a flame with a navy core over one navy wave. The mono mark is a solid silhouette with a real hole, and it reads at 16 px.
  The mark is the same in every file. Before, it changed between a version with the disc and one without.
- **SVGs:** both runs export strict, outlined SVGs. The new ones agree across resvg, Chromium and cairosvg (≤ 0.07 % of pixels differ).
- **Round 2:** clean in both runs. The old run swapped rasters on the sheet; the new one repoints live links, so the sheet renders from the edited sources.
- **New minor notes:** the full `vixl_check` flags the sheet's 14–18 px labels as "fix" for thumbnail legibility,
  although the labels are fine at full size. Exported glyph paths carry no-op `stroke="rgb(0, 0, 0)" stroke-width="0.0"` attributes.
