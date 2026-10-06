# T09 · One campaign, six sizes: judging

- **V lane:** re-run on Vixl 0.20.0, judged 2026-10-06 (claude-code-subagent judge, claude-opus-5-5).
- **W lane:** run and judged 2026-10-05. Its scores and notes are unchanged.

Runs: `claude-V` (Vixl MCP) and `claude-W` (web code + Chromium), each with `round2/`.

## 0. Regeneration (2026-10-06)

Only W's sources are committed, so its PNGs were rebuilt in a scratch copy outside the repo by
running `render.py` (Playwright Chromium from `/opt/pw-browsers`) in `claude-W/` and
`claude-W/round2/`.

- The `fonts/` folder that `campaign.html` loads was not committed. I re-downloaded the same two
  Google Fonts latin subsets (Fraunces variable, DM Sans variable) as woff2 into the scratch copy.
- After that, `render.py`'s own font-loaded assertion passed. Its text-extent printout (story text
  y 741–1549) matches the 2026-10-05 numbers.

V's deliverables are committed and were judged as they are.

## 1. Blind scores

New blind pass on 2026-10-06, written before opening `key.csv`. All four runs were in the blind set.

| Code | Fidelity | Craft | Reason |
| --- | --- | --- | --- |
| 9UC2 | 5 | 3 | All copy in every size. Amber lamp with soft halo, three thin wavy tide lines, bold serif headline + geometric sans. Clean and consistent, but generic. The story has a large empty band between the text and the waves, and the lamp is crammed into the top-right corner of the square |
| X5IW | 5 | 3 | Round 2 of the 9UC2 look. New copy reflows cleanly; nothing else visibly changed |
| EVVX | 5 | 4 | Steaming-cup lamp in halo rings, layered filled waves, amber accent word, coral pill URL. More distinctive. Stray star dots touch the copy on the square and story |
| I8XP | 5 | 4 | Round 2 of the EVVX look, with the new copy |

Key: 9UC2 = claude-V, X5IW = claude-V/round2, EVVX = claude-W, I8XP = claude-W/round2.

These W blind scores agree with the 2026-10-05 W scores (fidelity 5, craft 4). The earlier W blind
codes were ILEV (round 1) and TT4F (round 2).

## 2. Hard checks (round 1)

Sources:

- **V:** `inspect_outputs.py`, the text layers in the `.vixl` files, the embedded font names, and
  pixel measurements of the lamp discs.
- **W:** the 2026-10-05 results.

| Check | claude-V (Vixl 0.20.0) | claude-W (2026-10-05) |
| --- | --- | --- |
| Six files at exact sizes | PASS: 1080², 1080×1920, 1600×900, 1920×1005, 728×90, 600×200. All opaque RGB, with `.vixl` sources | PASS: same |
| Copy exact on 4 large; small two carry headline + line 3 | PASS: all four lines verbatim, including "·" and "Café". The menu line is one stored string that wraps in its box on the square, story and X post. Leaderboard and email: headline + line 3. No added copy | PASS: verbatim. Line 2 wraps with "·" at the line end (disclosed) |
| Story: no text in top/bottom 250 px | PASS: text layers span y 680–1288. Only the lamp halo (from y=50) and tide lines 3–5 (y 1660–1890) are in the zones | PASS: text y≈741–1549 |
| Nothing stretched/letterboxed | PASS: lamp discs measure 160×160 (story) and 48×48 (leaderboard). Every lamp layer has width = height. Tide lines are redrawn per size | PASS |
| One family (palette, type, motif) | PASS: the five brand swatches only; Fraunces Bold + Work Sans 400/600 (embedded) in all six; lamp + halo + tide lines in all six (coral rule left out of the leaderboard) | PASS |
| Leaderboard readable at 100 % | PASS: 32 px headline, 18 px date, cream/amber on navy | PASS: 29 px headline, 14 px date |
| **Total** | **6/6** | **6/6** |

## 3. Report honesty (round 1)

- **claude-V: yes.** These claims all match the files:
  - the tool list and the fonts (Fraunces 700, Work Sans 400/600);
  - the per-size menu wrapping (one line on Facebook only) and the headline break after "Winter";
  - the story text range (680–1288), the halo at y=50 and tide lines 3–5 at y 1660–1890;
  - the leaderboard rule left out and the email date raised to 19 px;
  - the leaderboard date at 18 px, the thumbnail warnings it kept, and the RGB sizes.

  It also says adapt-layout made the first version of the other five sizes and that every layer
  was then moved, resized or reset by hand. The document history confirms this (see section 6).
- **claude-W: yes** (2026-10-05). Sizes, text extents, the extra dark-navy band, the trailing "·"
  wraps and the hard-edged leaderboard waves are all disclosed and accurate.

## 4. Round 2 (headline "Winter Menu: now pouring"; "Spiced honey cortado")

- **claude-V (editability 5, revision 5).**
  - **Method:** copied the six `.vixl` files, then ran `text-set` on the existing `headline` and
    `menu` layers. Layer IDs, fonts, colors and positions were kept.
  - **Size changes:** only two, both disclosed.
    - Email headline 36→32 px, moved down 4 px so the baseline stays put.
    - Leaderboard headline 32→29 px, moved down 3 px, so it clears the lamp and the tide lines.
  - **Pixel diff r1→r2** (per channel > 8): every change is inside the headline rows and the
    first menu row. Bounding boxes:
    - square x 90–930, y 280–662
    - story y 680–1087
    - X post y 92–481
    - Facebook y 120–555
    - leaderboard x 92–480, y 15–45
    - email x 36–473, y 30–64

    The lamp, halo, rule, tide lines, date and URL did not change.
  - **Result:** the copy is correct in all six. Story text still spans y 680–1288. The round-2
    report matches the files.
- **claude-W (editability 5, revision 4)** (2026-10-05).
  - **Method:** a two-constant `sed` edit of `campaign.html` plus the email headline, then a
    re-render. It added a nowrap span after seeing a bad wrap.
  - **Result:** correct copy in all six, and the layout numbers did not change.
  - **Collateral:** the wider "Winter Menu:" line now collides with the lamp's halo rings on the
    square (the colon overlaps the outer rings at x≈720–760, y≈130–190). It still crosses a ring
    in the story. The report does not mention this.

## 5. Changes since the Vixl 0.18.0 run

| | Hard | Fid | Craft | Honest | Edit | Rev |
| --- | --- | --- | --- | --- | --- | --- |
| V on 0.18.0 (2026-10-05, AVLB) | 6/6 | 5 | 4 | yes | 5 | 5 |
| V on 0.20.0 (2026-10-06, 9UC2) | 6/6 | 5 | 3 | yes | 5 | 5 |

- **Same as before:** the hard checks, honesty and round-2 scores. Round 2 is again a clean
  in-place text edit with only disclosed font-size tweaks.
- **Look:** the new run is a different design.
  - Fraunces + Work Sans, line-drawn tide waves and a glowing lamp, instead of Young Serif +
    Rubik with filled wave bands.
  - It no longer adds the "TIDEWICK CAFÉ" label, so the copy is now strictly the brief's.
  - It scored one point lower on craft: tidy but plainer, with dead space in the story.
- **Exports** are now opaque RGB (RGBA before).
- **Workflow:** this run used `vixl_adapt_layout` to make the other five sizes from the square. Its
  output needed a manual re-layout of every layer in every size (section 6).

## 6. Vixl product notes (adapt-layout, from the `.vixl` history)

Each adapted document records the `adapt-layout` revision followed by the agent's manual fixes.

**What adapt-layout produced:**

- **Leaderboard (728×90):** the headline at 10 px. The menu, date and URL at 3 px. The lamp at
  12 px. Tide lines squashed from 1120×50 to 731×4.
- **Email (600×200):** the headline at 23 px. The other lines at 6–7 px. Tide lines squashed to
  607×9.
- **X post and Facebook:**
  - The headline and body were re-centered (headline at x=389 and x=494), but the coral rule was
    left at the left margin (x=78 and x=87), so the text group split apart.
  - Tide lines were scaled unevenly (1120×50 → 1633×42, i.e. ×1.46 wide but ×0.84 tall), so the
    waves were stretched.
- **Story (1080×1920):** the layers were spread down the canvas. The date and URL landed at
  y 1592–1682, inside the bottom 250 px safe zone, with a 400 px gap after the menu line.

**Manual work after adapt-layout:**

| Size | Operations | Layers touched |
| --- | --- | --- |
| Email | 13 | 10 |
| Facebook | 15 | 10 |
| Leaderboard | 16 | 10 |
| Story | 21 | 12 |
| X post | 44 | 10 |

That is every layer in every size. Removing lines and redrawing the tide shapes was expected for
the two small sizes. But the uneven wave stretching and the rule left behind happened in all four
landscape and banner sizes, and adapt-layout put story text into the safe zone.

## Summary

| Lane | Date | Hard | Fid | Craft | Honest | Edit | Rev |
| --- | --- | --- | --- | --- | --- | --- | --- |
| V (Vixl 0.20.0) | 2026-10-06 | 6/6 | 5 | 3 | yes | 5 | 5 |
| W | 2026-10-05 | 6/6 | 5 | 4 | yes | 5 | 4 |
