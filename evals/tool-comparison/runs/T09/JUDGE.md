# T09 · One campaign, six sizes: judging

- **V lane:** re-run on Vixl 0.26.0, judged 2026-10-12 (claude-code-subagent judge, claude-opus-5-5).
  Effort: round 1 took 3.9 min and 32 tool calls; round 2 took 1.9 min and 30 tool calls.
- **W lane:** run and judged 2026-10-05. Its scores and notes are unchanged.

Runs: `claude-V` (Vixl MCP) and `claude-W` (web code + Chromium), each with `round2/`.

## 0. Regeneration (2026-10-12)

Only W's sources are committed, so its PNGs were rebuilt in a scratch copy outside the repo by
running `render.py` in `claude-W/` and `claude-W/round2/`. Playwright's Chromium was pointed at
`/opt/pw-browsers/chromium-1194` (scratch copy only).

- The `fonts/` folder that `campaign.html` loads was not committed. I downloaded the same two
  Google Fonts latin subsets (Fraunces variable, DM Sans variable) as woff2 into the scratch copy.
- After that, `render.py`'s own font-loaded assertion passed. Its text-extent printout (story text
  y 741–1549; square 105–760) matches the 2026-10-05 and 2026-10-06 numbers.

V's deliverables (six PNGs and six `.vixl` per round) are in the run folders. They are git-ignored
like all run outputs; only the reports are tracked. They were judged as they are. I re-exported
every `.vixl` from a scratch copy with the `vixl` 0.26.0 CLI, and all 12 PNGs came out
pixel-identical to the delivered ones (max channel difference 0). The sources really are the
sources.

## 1. Blind scores

New blind pass on 2026-10-12, written before opening `key.csv`. All four runs were in the blind set.

| Code | Fidelity | Craft | Reason |
| --- | --- | --- | --- |
| FW1G | 5 | 4 | All copy in every size. Tracked amber "TIDEWICK CAFÉ" label, bold serif headline, short coral rule, then sea-foam / cream / amber detail lines. Glowing amber disc, and layered soft waves (translucent slate, sea-foam, coral line, cream). Clean hierarchy, and each size is properly composed: the story has a centred column, and the banners have waves rising from the bottom-right. Minuses: the disc reads as a sun or moon rather than a lamp; the story date wraps as "…December 1 at / Tidewick Café"; the square's items line is small; an extra brand label goes beyond the four copy lines |
| IKY5 | 5 | 4 | Round 2 of the FW1G look. The new copy sets as a two-line headline everywhere, and the square's disc sits a little higher and further right. Nothing else visibly changed |
| BRPP | 5 | 4 | Steaming-cup lamp in halo rings, layered filled waves, amber accent words, coral pill URL. Richer than FW1G. Stray star dots touch the copy on the square and story |
| 5ME0 | 5 | 4 | Round 2 of the BRPP look, with the new copy. The colon of "Winter Menu:" touches the outer halo ring on the square |

Key: FW1G = claude-V, IKY5 = claude-V/round2, BRPP = claude-W, 5ME0 = claude-W/round2.

These W blind scores agree with the 2026-10-05 W scores (fidelity 5, craft 4). The earlier W blind
codes were ILEV and EVVX (round 1) and TT4F and I8XP (round 2).

## 2. Hard checks (round 1)

Sources:

- **V:** `inspect_outputs.py`, the layers in the `.vixl` files (stored and via `vixl layers`), the
  embedded font names, a `vixl check` rerun on scratch copies, and pixel measurements.
- **W:** the 2026-10-05 results, confirmed on the rebuilt PNGs.

| Check | claude-V (Vixl 0.26.0) | claude-W (2026-10-05) |
| --- | --- | --- |
| Six files at exact sizes | PASS: 1080², 1080×1920, 1600×900, 1920×1005, 728×90, 600×200. All opaque RGB, with `.vixl` sources | PASS: same |
| Copy exact on 4 large; small two carry headline + line 3 | PASS: all four lines verbatim, including "·" and "Café", each stored as one string. Leaderboard and email: headline + line 3. It adds a "Tidewick Café" brand label (drawn uppercase) on five sizes, beyond the four lines. This is disclosed, and was also passed on the 0.18.0 run | PASS: verbatim. Line 2 wraps with "·" at the line end (disclosed) |
| Story: no text in top/bottom 250 px | PASS: the text layers span y 540–1400. Measured ink outside the lamp is at y 541–1399. Left of x=600 the top 250 px are pure background. Only the lamp and its glow (disc y 110–349) and the waves (from y 1520) are in the zones. `vixl check --avoid` on both bands passes, and the same check fails as expected when the zone is moved onto the headline | PASS: text y≈741–1549 |
| Nothing stretched/letterboxed | PASS: the measured lamp discs are 170², 240², 230², 220², 66², and 34×32 on the leaderboard, where the bottom 2 px pass behind the translucent back wave; the layer is 34×34. Every lamp layer has width = height. Wave paths are drawn separately for each size | PASS |
| One family (palette, type, motif) | PASS: the five brand colours, plus a 35 % sea-foam tint (#48636c) and the glow blends. Fraunces Bold + Work Sans Regular (both embedded) in all six. Lamp + four-layer waves + coral rule in all six (the rule becomes a vertical tick on the two small sizes) | PASS |
| Leaderboard readable at 100 % | PASS: 34 px Fraunces Bold cream headline and a 17 px sea-foam date on navy, clear of the waves | PASS: 29 px headline, 14 px date |
| **Total** | **6/6** | **6/6** |

## 3. Report honesty (round 1 and round 2)

- **claude-V: yes.** These claims all match the files:
  - the fonts (Fraunces 700, Work Sans 400), the colour roles, and the sea-foam date on the two
    small sizes;
  - the story text range (y 540–1400) and the passing avoid-zone check;
  - the leaderboard date at 17 px and the email date at 16 px;
  - the rule turning into a vertical tick, and `allow_crop` on the waves;
  - the glow blur scaled to each size (14 / 24 / 60 / 80 px);
  - the extra brand label;
  - "no fix or review findings": a `vixl check` rerun on all 12 documents gives 0 fix and
    0 review, and only the bleed and thumbnail-size notes it lists.

  It says each size was composed by hand, not with `vixl_adapt_layout`. The document history
  confirms this: each file has one build batch (15–21 ops) and at most one fix batch (6–9 ops),
  with no `adapt-layout`.

  Small slips, with the deliverables unaffected:
  - Round 1 says the headline wraps "on every size". The leaderboard headline is one line with no
    text box.
  - It says "only the five brand colours" are saved as swatches. Each document also carries seven
    auto-generated swatches from `vixl_document_create` (`ink` #fee440, `accent` #f15bb5, …), which
    no layer uses.
  - The round-2 report gives the old headline sizes as story 136 px and Facebook 163 px. The
    round-1 files have 140 and 168, confirmed by the stored size and by cap height in the PNGs
    (100 px and 120 px). The new sizes (128, 156) and the square's 124 → 112 are right.
- **claude-W: yes** (2026-10-05). Sizes, text extents, the extra dark-navy band, the trailing "·"
  wraps and the hard-edged leaderboard waves are all disclosed and accurate.

## 4. Round 2 (headline "Winter Menu: now pouring"; "Spiced honey cortado")

- **claude-V (editability 5, revision 5).**
  - **Method:** copied the six `.vixl` files, then ran `text-set` on the existing `headline` and
    `items` layers. The history shows one 1–2 op text batch per file plus the fixes below. Layer
    IDs, fonts, colours, text boxes and all other positions are unchanged.
  - **Fixes (all disclosed):** the new headline wrapped to three lines on three sizes, and
    `vixl_check` flagged it. The agent shrank the headline so it sets in two lines:
    - square 124 → 112 px;
    - story 140 → 128 px;
    - Facebook 168 → 156 px.

    It also moved the square's lamp from (800, 90) to (840, 60), clear of the colon. The disc is
    still 170². The X post, leaderboard and email needed no change.
  - **Pixel diff r1→r2** (per channel > 8): the changes are only in the headline and items rows,
    plus the square's lamp. Bounding boxes:
    - square y 0–331 (headline + lamp), 342–463 and 584–625 (items);
    - story y 624–891 and 1034–1143;
    - X post y 154–447 and 504–551;
    - Facebook y 184–506 and 586–638;
    - leaderboard x 18–486, y 6–51;
    - email x 30–354, y 46–149.

    The rule, date, URL, label and waves did not change.
  - **Result:** the copy is correct in all six. Story text still spans y 540–1400. `vixl check`
    gives 0 fix and 0 review on all six round-2 files.
- **claude-W (editability 5, revision 4)** (2026-10-05).
  - **Method:** a two-constant `sed` edit of `campaign.html` plus the email headline, then a
    re-render. It added a nowrap span after seeing a bad wrap.
  - **Result:** correct copy in all six, and the layout numbers did not change.
  - **Collateral:** the wider "Winter Menu:" line now collides with the lamp's halo rings on the
    square (the colon overlaps the outer rings at x≈720–760, y≈130–190). It still crosses a ring
    in the story. The report does not mention this. My 2026-10-12 rebuild shows the same.

## 5. Changes since earlier Vixl runs

| | 0.18.0 (2026-10-05) | 0.20.0 (2026-10-06) | 0.26.0 (2026-10-12) |
| --- | --- | --- | --- |
| Blind code | AVLB | 9UC2 | FW1G |
| Hard checks | 6/6 | 6/6 | 6/6 |
| Fidelity / craft | 5 / 4 | 5 / 3 | 5 / 4 |
| Report honest | yes | yes | yes (three small numeric/wording slips) |
| Editability / revision | 5 / 5 | 5 / 5 | 5 / 5 |
| How the sizes were made | composed per size | `adapt-layout`, then every layer re-laid by hand | composed per size (build batch + small fix batch) |
| Effort r1 / r2 | not recorded | not recorded | 3.9 min, 32 calls / 1.9 min, 30 calls |

- **Craft is back to 4.** The 0.26.0 run is a tidier, editorial version of the 0.18.0 approach:
  - Fraunces + Work Sans;
  - a brand label, headline, rule and detail stack;
  - a glowing disc over layered soft waves.

  The story is properly composed this time, with no dead band. The motif is plainer than W's, so
  it stays at 4.
- **Unchanged:** the hard checks, honesty and round-2 scores. Round 2 is again a clean in-place
  text edit, with only disclosed fit fixes.
- **Workflow:** the agent skipped `adapt-layout`, which was the costly path on 0.20.0. It built
  each size directly, then made one small fix batch. That and the clean `vixl_check` results make
  this the cheapest V run so far.
- **Not a product signal:** the agent chose to avoid `adapt-layout`. My scratch test (section 6)
  shows it is still not good enough to start from for a re-layout of this design.

## 6. Vixl product notes (0.26.0)

The run itself hit no tool failures. Two gaps reproduced in scratch copies:

**1. `adapt-layout` is still not a usable start.** I applied `adapt-layout` to a copy of the
delivered square `.vixl`, then ran `vixl check` on each result.

- **Leaderboard (width/height 728×90):**
  - Every text layer shrinks to 12 px, and the lamp to 14 px.
  - The headline gets a 68×19 box and is cut off at "The Winter / Menu is". Check: "does not fit
    its 68×19 text box … needs 68×35".
  - The items, date and URL lines stack 6 px apart and overlap.
  - The waves are scaled to fill the banner, so all the text sits on the pale waves, at contrast
    1.0–1.8:1.
  - `vixl check` catches all of this: 8 fix findings.
- **X post (1600×900):**
  - The headline, rule and detail lines move to x≈418–430, while the brand label stays at x=75, so
    the text group splits. On 0.20.0 it was the rule that was left behind.
  - The waves grow to 356 px tall and run under the URL line.
  - The lamp's disc sits right against the end of the headline's "Winter", and its glow overlaps
    the word.
  - `vixl check` reports nothing (0 fix, 0 review).
- **Story, given as raw 1080×1920:**
  - The label and headline stay at y 110–455, inside the top 250 px. The rule and details drop to
    y 1032–1264, leaving a ~580 px gap.
  - `vixl check` passes, because the canvas keeps its 54 px safe margin.
  - With `size: "instagram-story"`, the 250 px top/bottom safe zones are applied, and the label
    moves to y=250. So the story rule only works when the agent names the size.

**2. `vixl_document_create` seeds an off-brand palette.** Each document starts with a random
house-style direction (`palette: neon`, `style: brutalist`, `pairing: bricolage-figtree`). It also
starts with seven swatches unrelated to the navy background given: `ink` #fee440, `accent` #f15bb5,
`muted` #b9ae50, and others. The agent overrode every colour, so nothing leaked into the
artwork. But any default-coloured text or shape would have come out yellow or pink, and the extra
swatches stay in the saved files next to the five brand swatches.

## Summary

| Lane | Date | Hard | Fid | Craft | Honest | Edit | Rev |
| --- | --- | --- | --- | --- | --- | --- | --- |
| V (Vixl 0.26.0) | 2026-10-12 | 6/6 | 5 | 4 | yes | 5 | 5 |
| W | 2026-10-05 | 6/6 | 5 | 4 | yes | 5 | 4 |
