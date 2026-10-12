# T02 · Social post with exact copy: judge notes

- **V lane:** re-run on Vixl 0.26.0 and judged 2026-10-12 by a claude-opus-5-5 subagent. Effort: round 1 took 2.5 min and 21 tool calls, round 2 took 2.0 min and 21 tool calls, with no nudges.
- **W lane:** run and judged 2026-10-05. Its scores and notes below are unchanged.
- Only W's sources are committed, so for the blind look I rebuilt W's PNGs in a scratch copy outside the repo. I used its `render.py` with Playwright 1.63 pointed at the installed Chromium 1194 (`executable_path`, changed in the scratch copy only, because Playwright 1.63 expects a newer browser build). Its `fonts/` folder was not committed, so I downloaded the same Google Fonts files again (Fraunces 800, DM Sans 500 and 700). The rebuilt render printed the same text positions as before (kicker 96, "Open Mic" 137, URL 89 px from the edge), so it matches what was judged.
- **Blind codes for this pass:** V r1 = LXEA, V r2 = U1F0, W r1 = SV3Q, W r2 = 28A5 (rebuilt). Earlier passes: 2026-10-06 V = BWGN / K8DY, W = DHH2 / PYYD; 2026-10-05 V = 4058 / XQHG, W = HF3D / O4UN (round 1 / round 2).

## 1. Blind scores (written before opening key.csv)

| Code | Run | Fidelity | Craft | Reason |
| --- | --- | --- | --- | --- |
| LXEA | V r1 (2026-10-12) | 5 | 4 | A left-set Fraunces headline on two lines, a coral microphone with a warm glow at the right, the date in serif on a full-width amber bar, two sans detail lines, three sea-foam wave lines and the URL. The hierarchy is clear and all six lines are exact. The bottom third (waves and URL) and the space right of the address lines feel empty, and the mic is a little generic. |
| U1F0 | V r2 (2026-10-12) | 5 | 4 (post), 3 (story) | The post gains the host line in the empty space under the headline, and nothing else seems to move. The story looks like the post block shifted down about 210 px on a taller canvas: the headline is the same size and there are empty navy bands of about 300 px at the top and bottom. It reads as a shifted copy more than a re-layout. |
| SV3Q | W r1 (rebuilt, reference only) | 5 | 4 | The richest art of the runs (string lights, mic, harbour band, cream footer, coral pill). The leading is tight: the "p" in "Open" nearly touches "Night". |
| 28A5 | W r2 (rebuilt, reference only) | 5 | 4 | The host line is inserted and the lower block moves down. The story is a real re-layout with a larger headline, but the cream band at its bottom is large and empty. |

W keeps its 2026-10-05 scores (5/5). As on 2026-10-06, my blind look at the rebuilt W gave craft 4 because of the tight headline leading. I list it only to show that these passes score a little harder than the first one, not to change W's scores.

## 2. Hard checks (round 1)

| Check | V (0.26.0, 2026-10-12) | W (2026-10-05) |
| --- | --- | --- |
| `post.png` 1080×1350 | PASS (RGB, 853 colours) | PASS (RGB) |
| Six lines exact (É, en dash, middle dots) | PASS. I read the text layers out of `post.vixl` code point by code point: U+00C9 in the kicker, U+00B7 in the date and the CTA, U+2013 in the date. There are exactly six text layers, with nothing added. The headline is the single string "Open Mic Night" and wraps in a 916 px box. | PASS. HTML text has U+00C9, U+00B7, U+2013. Headline is two spans in one h1 |
| "Open Mic Night" most prominent | PASS. The headline is Fraunces 700 at 160 px; the next largest line is the date at 48 px, on the amber bar. | PASS |
| All text ≥ 60 px from the edges | PASS. I measured the ink of each text layer against its own background: left 82 (address), top 92 (kicker), right 141 (the date ends at x 938), bottom 109 (the URL ends at y 1240). | PASS (measured: nearest 89 px, the URL from the bottom) |
| Readable at 25 % (270×338) | PASS. Every line is readable, including the 30 px kicker and URL. | PASS |
| **Total** | **5/5** | **5/5** |

## 3. Report honesty

- **V: yes.** Every claim I checked matches the files:
  - **Round 1:**
    - The fonts and sizes match `post.vixl`: Fraunces 700 at 160 px (headline) and 48 px (date), Work Sans 400 at 38 px (address, CTA) and 30 px (kicker, URL).
    - Nearest text ink 82 px from the left and 92 px from the top, URL ending about y 1240: I measured 82, 92 and 1240.
    - The wave strokes' round caps reach about 63 px from the sides: I measured 63 px on both sides. It says so openly and correctly calls them decoration.
    - The `brief` suite has 18 rules, as stated. `vixl check` on the file gives only the `legibility.runt` review finding the report mentions.
  - **Round 2:**
    - "Nothing else moved" in the post is true: the r2 `post.vixl` is the r1 file plus one `host` layer and the new date text, and the pixel diff is confined to x 86–939, y 508–731 (the host line and the date line).
    - The host layer is where it says: x 82, y 508, Work Sans 38 px in `@accent`. The headline ink ends at y 474 (it says about 475).
    - Every story position it lists (date band 900, address 1070, CTA 1132, waves 1330/1386/1442, URL 1560, kicker 303, headline 371, host 719) matches `story.vixl`.
    - "0 non-background pixels in the top 250 and bottom 250 rows, first ink at 303, last at 1588": I measured the same.
    - It says adapt-layout put the URL at y 1782, inside the bottom band. I reproduced that exactly when the target is given as `1080x1920` (see section 5).
    - It says plainly that the story is "re-spaced, not re-composed", and that an `assert` rule it tried is not supported.
- **W: yes.** Its measured margins and font coverage match the files.

## 4. Round 2 (date → Nov 19, host line under the headline, 1080×1920 story)

- **V (0.26.0).**
  - **Post.** The agent copied `post.vixl`, changed the date with `text-set` on the existing layer and added a `host` text layer at y 508, in the empty space under the headline and left of the mic. Nothing else was moved: every other layer has the same geometry as in round 1.
  - **Pixel diff, r1 against r2 `post.png`.** 4,935 changed pixels, all inside x 86–939, y 508–731: the new host line and the "12" → "19" in the date. The kicker, headline, mic, glow, date bar, details, waves and URL are unchanged. This is cleaner than the 0.18.0 and 0.20.0 runs, which both shifted the lower block down to make room. The copy is exact in both `.vixl` files.
  - **Story.** It is not stretched or letterboxed, but it is only a light re-layout:
    - The canvas is 1080×1920 and the scale is 1.0. The headline stays at 160 px, and the mic and glow keep their size.
    - The top block (kicker, headline, host, mic) is the post's, moved down 211 px. The lower block is re-spaced: date bar +250, address +258, CTA +260, waves +310, URL +348.
    - All text sits in y 303–1588, clear of the top 250 px and the bottom 250 px. Sides are ≥ 82 px.
    - The result leaves about 300 px of empty navy at the top and 330 px at the bottom. The 0.20.0 story enlarged the headline to 188 px and re-hung the lamp; this one does not.
  - **Editability 5, revision 4.** Round 2 was a clean in-place edit with nothing else moved. The revision loses a point because the story is the post translated and re-spaced rather than re-composed for the tall format, which is exactly what TESTS.md asks the judge to check.
- **W.** The date and host are correct. The headline was nudged up 18 px (61k changed pixels above y=780), which is small collateral; the lower block moved down to make room. The story is a real re-layout, with text in y 300–1653. **Editability 5, revision 4.**

## 5. Changes since earlier Vixl runs

| | 0.18.0 (2026-10-05) | 0.20.0 (2026-10-06) | 0.26.0 (2026-10-12) |
| --- | --- | --- | --- |
| Hard checks | 5/5 | 5/5 | 5/5 |
| Fidelity / craft | 4 / 4 | 5 / 4 | 5 / 4 |
| Report honest | yes | yes | yes |
| Editability / revision | 5 / 5 | 5 / 5 | 5 / 4 |
| Effort (r1 / r2) | | | 2.5 / 2.0 min, 21 / 21 tool calls |

The round-1 post is at the 0.20.0 level: exact copy, RGB, the Fraunces pairing, clear hierarchy, still a little sparse (craft 4). The decoration changed from a pendant lamp to a microphone with a glow, and the date now sits on an amber bar. Round 2 got better on the post: the host line went into existing empty space and nothing else moved at all, where both earlier runs shifted the lower block. It got worse on the story: 0.20.0 re-composed it (bigger headline, lamp hung lower), while this run translated the post down and re-spaced the lower half at scale 1.0, so revision drops from 5 to 4. The two story safe-zone gaps reported for 0.20.0 are fixed for named sizes, but the agent gave the target as `1080x1920` and so did not benefit.

- **Fixed since 0.20.0** (reproduced on a scratch copy of `round2/post.vixl`):
  - **`adapt-layout` to a named story size keeps text out of the UI bands.** With `--sizes story` (and `instagram-story`) the kicker lands at y 303 and the URL box ends at y 1670, exactly on the bottom band's edge. In 0.20.0 the kicker stayed at y 130 and the URL landed in y 1688–1724.
  - **The canvas safe area is per side and checked by default.** The adapted story records `safe: {left 60, top 250, right 60, bottom 250}`. After I moved the URL to y 1782, a plain `vixl check` reported `safe_area.outside` as a `fix` finding. In 0.20.0 the canvas stored one inset for all four sides and `check` ignored it unless `safe_area=` was passed.
- **Product gaps that remain or are new in 0.26.0** (none of them changed a score, because the agent worked around each one):
  1. **A `WIDTHxHEIGHT` target that matches a story is not treated as one.** `adapt-layout --sizes 1080x1920` on the same file gives `safe: 54` (the 5 % custom-size default), leaves the URL at y 1782 inside the bottom 250 px, and returns no warning. This is the path the agent took, and the shipped `story.vixl` still carries `safe: 54` and no size name, so `vixl check` on it does not guard the story bands. Matching 1080×1920 to the story preset, or at least warning, would have saved the agent its manual re-spacing.
  2. **`adapt-layout` re-anchors but does not re-compose.** Even with the named `story` size the result is at scale 1.0 with the headline unchanged; the extra 570 px go into gaps. That is what the agent shipped, and it is why revision is 4.
  3. **The `event-poster` layout still breaks the date badly and fails its own check.** I reproduced it with `layout apply event-poster --seed 7 --mode dark` on `instagram-portrait` with the brief's copy. The headline now wins (124 px against the date's 74 px; in 0.20.0 it was 104 against 82), but the date wraps as "Thursday, November / 12 · 7–10 pm", splitting the month from the day, in a 275 px block. The layout's own `caption` slot is set at 22 px, and `check` on the fresh layout reports it as a `fix` finding with an unformatted number: "aim for at least 23.759999999999998 px".
  4. **The layout's rolled palette silently replaces an explicit background.** In the same repro, `vixl new instagram-portrait --background "#14263b"` followed by `layout apply … --mode dark` renders an olive `#423b25` background (the `@background` swatch), while `canvas.background` still says `#14263b`. The agent avoided this by passing the brand colours as the layout roles.
  5. **Assertions cannot compare a layer edge.** `vixl assert "layer.kicker.bounds.top >= 250"`, `"layer.kicker.top >= 250"` and `"layer.kicker.y >= 250"` all fail with `invalid_assertion`, "Unsupported assertion; see docs/commands.md", with no suggestion. Only forms like `layer.kicker.bounds within canvas` work. So a story-band rule cannot live in a document's suite as an `assert`; the agent fell back to `vixl_check avoid=` and a pixel read.
