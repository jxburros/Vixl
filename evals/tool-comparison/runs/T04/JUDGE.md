# T04 · Logo and icon kit: judge's notes

Judge: Claude (claude-opus-5-5) as a subagent, 2026-10-05. Lanes: V = Vixl MCP, W = hand-written SVG + Chromium. Both runs were made by Claude subagents.

## 1. Blind scores (written down before opening key.csv)

I rendered every SVG in headless Chromium (Playwright, from a data: URI, so nothing loaded from disk) and in Inkscape 1.x. The two renderers differ by less than 1 % RMSE on every round-1 SVG. There are no `<text>` elements anywhere, so system fonts can't change the output. I also checked each mark at 16 × 16 px in Chromium and at the 16 px favicon layer.

From the content alone I could tell the rounds apart: Q9L3 and VPK7 carry the round-1 brand, and ALT7 and MLJ5 say "Tidewick & Co.". So I scored fidelity and craft on the round-1 codes.

| Code | Fidelity | Craft | Reason |
| --- | --- | --- | --- |
| Q9L3 | 5 | 4 | Every deliverable is there, and the sheet shows every version on both cream and navy plus real-size 16/32/64 marks. The drop with rays over waves reads as lamp light on water and still reads at 16 px. Mono uses the same silhouette. The wordmark serif looks generic and default, and the sheet has dead space. |
| VPK7 | 4 | 4 | Better type pairing and a more polished sheet. The flame in a disc over a wave reads as lamp plus water. But the navy half of the sheet leaves out the mono mark. The mark's identity shifts between a disc and no disc. The wave ribbon ends bluntly inside the disc. The outlined mono mark turns to mush at 16 px. |
| ALT7 (r2) | 5 | 4 | Name and tagline are updated in every lockup, the mark is untouched, and the long name balances in both lockups. |
| MLJ5 (r2) | 4 | 4 | Name and tagline are updated. The sheet has the same omission as VPK7. The mark is unchanged. |

Key: Q9L3 = W r1, VPK7 = V r1, ALT7 = W r2, MLJ5 = V r2.

## 2. Hard checks (round 1), from `inspect_outputs.py runs/T04` and direct inspection

| Check | V (claude-V) | W (claude-W) |
| --- | --- | --- |
| All seven files exist | PASS | PASS |
| SVGs: embedded_images=0, text_elements=0 | PASS: all 0/0. Extra reversed SVGs are 0/0 too. | PASS: all 0/0 |
| Same render without the fonts | PASS: outlined glyphs; Chromium and Inkscape agree (RMSE < 1 %). The round-1 mask problem was fixed before delivery. | PASS: outlined glyphs; Chromium and Inkscape agree (RMSE < 1 %) |
| favicon.ico has 16/32/48 | PASS | PASS |
| app-icon 1024², RGB, square corners | **FAIL**: mode=RGBA. Alpha is 255 everywhere, but strictly RGBA is not RGB. Corners are navy, full bleed. | PASS: RGB, corner pixels are navy (20,38,59) |
| logo-sheet 1600×1200 with every version on cream and navy, plus 16/32/64 | **FAIL**: 1600×1200 and 16/32/64 are present, but mark-mono doesn't appear on the navy half (the report discloses this). | PASS: every version on both halves, with color and mono at 1:1 at 16/32/64 |
| Mark recognizable at 16 px, ≤ 2 colors, mono navy only | PASS: the color mark (navy and amber) is just recognizable at 16 px. mark-mono.svg is rgb(20,38,59) only; its rgb(0,0,0) entries have opacity 0.0. The mono mark is weak at 16 px (ring and outline flame blur). | PASS: the drop and waves read at 16 px. mark.svg is #14263b and #f2a541; mark-mono.svg is #14263b only. |
| Wordmark and tagline spelled exactly | PASS: "Tidewick", "Coffee by the harbor" | PASS: "Tidewick", "COFFEE BY THE HARBOR". The letters are exact, set in all caps as a style; the report discloses this. |
| **Total** | **6/8** | **8/8** |

## 3. Report honesty

- **V: yes.** The report discloses the RGBA app icon (alpha 255), mono missing from the navy half, mono built differently from the color mark (and why), the favicon dropping the inner flame, and that the SVGs weren't browser-tested. Everything I checked matches. The fonts (Fraunces and Work Sans) match what's visible.
- **W: yes.** The report's file modes (RGB app icon, ICO sizes), the sheet contents, the DejaVu fonts, the all-caps tagline, the three-color app icon tile and the cream favicon tile all match the files. It flags its own odd 2-minute timing instead of hiding it.

## 4. Round 2 ("Tidewick & Co." / "Coffee · Bakery · Harbor")

- **Mark unchanged:** V's mark.svg, mark-mono.svg, mark-reversed.svg, favicon.ico and app-icon-1024.png are byte-identical to round 1 (md5). In V's lockups the mark group is identical; only its centering offset moved with the wider canvas. W's mark.svg and mark-mono.svg differ from round 1 only in `<title>`, and the path data is identical. W's favicon.ico and app-icon-1024.png are byte-identical to round 1. W's lockups keep the mark and fonts; only the viewBox width and the glyph paths changed.
- **V:** edited the copied `.vixl` sources in place (`text-set` on wordmark and tagline, canvases widened, center constraint), then re-exported. The sheet was rebuilt by swapping the four lockup rasters; every other layer is unchanged. The tagline uses the requested mixed case. Side effects: the lockups are smaller on the sheet, with the stacked tagline about 11 px, and the RGBA icon issue carries over. editability 5, revision 5.
- **W:** copied `build/`, changed the two strings and the titles in `make.py`, escaped `&` in titles, widened one display width in `sheet.html`, and reran. The tagline stays in caps, consistent with round 1 and disclosed. The stacked lockup is a little top-light with the longer name. editability 5, revision 5.

## Summary

| Lane | Hard | Fidelity | Craft | Honest | Editability | Revision |
| --- | --- | --- | --- | --- | --- | --- |
| V | 6/8 | 4 | 4 | yes | 5 | 5 |
| W | 8/8 | 5 | 4 | yes | 5 | 5 |

Findings:
- Vixl lost two hard checks. One is a tool limitation: its PNG export keeps an alpha channel even on an opaque canvas. The other is an agent choice: it left mono off the navy half.
- Vixl produced better typography, because it could install Google Fonts. W was blocked (403) and fell back to DejaVu.
- W's mark is the stronger small-size symbol, and its mono version is a true silhouette of the color mark.
- Both lanes handled round 2 cleanly and left the mark untouched.
