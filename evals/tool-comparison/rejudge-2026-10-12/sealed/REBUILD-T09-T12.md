# Rebuild of T09–T12 non-Vixl deliverables

Rebuilt in the scratch mirror from the committed sources. claude-V was not touched. Paths below are relative to `evals/tool-comparison/runs/`. Fixture `coast-raw.jpg` md5 was `0adf9cb287cbfd00da4750dad81f245a` before and after (as both T10 REPORTs state).

Every run was rebuilt (8 of 8). No run needed GIMP or darktable.

## T09/claude-W (round 1): rebuilt yes
- Command: `python3 render.py`.
- Outputs: instagram-square.png 1080×1080, instagram-story.png 1080×1920, x-post.png 1600×900, facebook-event.png 1920×1005, leaderboard.png 728×90, email-header.png 600×200.
- Source edit: `render.py` `p.chromium.launch()` → `p.chromium.launch(executable_path="/opt/pw-browsers/chromium")`. The default launch failed because no Playwright-managed browser was present.
- Fonts downloaded into `fonts/`. They were not committed, and REPORT.md names them. CSS request: `https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght,SOFT@9..144,100..900,0..100&family=DM+Sans:opsz,wght@9..40,100..1000&display=swap`, sent with a Chrome UA. The latin subsets:
  - `fonts/Fraunces-latin.woff2` ← https://fonts.gstatic.com/s/fraunces/v38/6NUI8FyLNQOQZAnv9bYEvCeYdG9Ea92uemAO8Uik.woff2
  - `fonts/DMSans-latin.woff2` ← https://fonts.gstatic.com/s/dmsans/v17/rP2Hp2ywxg089UriCZOIHQ.woff2
  - Caveat: the original agent's exact files (version and axis set) are unknown. These are the current Google Fonts variable latin files. The HTML uses the `opsz` and `SOFT` axes, so I requested those axes, and `WONK` was left at its default. render.py's `document.fonts.check` assertion passed.
- Differences from REPORT: none found. render.py printed the text boxes. Story text spans y 741–1549, as the REPORT says.

## T09/claude-W/round2: rebuilt yes
- Command: `python3 render.py` in `round2/`.
- Outputs: the same six PNGs at the same sizes as round 1 (listed above).
- Source edit: the same Chromium `executable_path` edit in `round2/render.py`.
- Fonts: the same two files, copied into `round2/fonts/`.
- Differences from REPORT: none found. The measured text boxes match the REPORT exactly: square 105/796/760, story 741/990/1549, X 74/1000/651, Facebook 102/1190/762, leaderboard 15/604/72, email 19/456/159.

## T10/claude-C (round 1): rebuilt yes
- Command: `python3 edit_coast.py`.
- Outputs: coast-edited.jpg 1509×1005 (q95), coast-instagram.jpg 1080×1350 (q95), coast-caption.png 1600×900.
- Source edits: none.
- Differences from REPORT: none found. The printed values match the REPORT: crop rect, WB gains R 0.892 / G 1.099 / B 1.061, Instagram crop box (578,0,1382,1005), caption crop box (0,78,1509,927), text box (72,765)–(917,828). Mean RGB of coast-edited is 101.3/84.5/99.2, against 101/85/99 in round2/REPORT.

## T10/claude-C/round2: rebuilt yes
- Command: `python3 round2/edit_coast.py`.
- Outputs: coast-edited.jpg 1509×1005, coast-instagram.jpg 1080×1350, coast-caption.png 1600×900.
- Source edits: none.
- Differences from REPORT: none found. The contrast pivot is 0.379 and the text box is (72,765)–(990,828). For coast-edited: means 104.3/86.3/93.1, luma std 51.3, p1/p99 12/209. All match the REPORT.

## T10/claude-T (round 1): rebuilt yes
- Command: `bash build.sh`, using ffmpeg and ImageMagick 6.
- Outputs: coast-edited.jpg 1558×1004 (q95), coast-instagram.jpg 1080×1350 (q92), coast-caption.png 1600×900.
- Source edits: none.
- Differences from REPORT: none found. Mean RGB of coast-edited is 98.4/58.8/74.4, which matches the REPORT's round-1 figure exactly.

## T10/claude-T/round2: rebuilt yes
- Command: `bash round2/build.sh`.
- Outputs: coast-edited.jpg 1558×1004, coast-instagram.jpg 1080×1350, coast-caption.png 1600×900.
- Source edits: none.
- Differences from REPORT: none found. coast-edited means 102.0/61.3/73.4 and coast-instagram means 115.5/72.0/77.1, both matching the REPORT exactly.

## T11/claude-C (round 1): rebuilt yes
- Command: `python3 step1_rectify.py && python3 step2_vectorize.py && python3 step3_color.py`.
- Outputs: sketch-clean.png 2000×1485 (grayscale), sketch-lines.svg 2000×1485 (25 `<path>` + 1 `<circle>`, no `<image>`), sketch-color.png 2000×1485 RGB, compare.png 2799×1080.
- Intermediate files: work_ink.png, work_flat.png and work_rectify.json are kept. work_rectify.json is byte-identical to the committed file. work_warp.png was deleted, as the REPORT describes.
- Source edits: none.
- strokes.json: step 2 regenerates it. The regenerated file differs from the committed one only in the last float digits of the circle fit (around 1e-12). Stroke count (26), gap log and all other geometry are identical. I restored the committed `strokes.json` afterwards so the committed source stays unchanged. The deliverables were rendered from the regenerated copy, which is equivalent.
- Differences from REPORT: none. Stroke width is 6.0, the circle is (1552.1, 302.9) r 122.1 with rms 1.38, the gap log is the same, and the regions are assigned with none unassigned. The REPORT's "25 strokes" means the 25 paths; the circle is a 26th element.

## T11/claude-C/round2: rebuilt yes
- Command: `python3 step4_chimney.py && python3 step3_color.py` in `round2/`. It reads round 1's committed `../strokes.json`.
- Outputs: sketch-clean.png 2000×1485, sketch-lines.svg (26 `<path>` + 1 `<circle>`), sketch-color.png 2000×1485, compare.png 2799×1080.
- The regenerated round2/strokes.json is byte-identical to the committed one.
- Source edits: none.
- Differences from REPORT: none. The chimney points match the REPORT, the regions are 2 roof with none unassigned, and the roof pixel is (192,57,43).

## T11/claude-T (round 1): rebuilt yes
- Commands: following `scripts/run.sh`, I ran `python3 s1.py && python3 s2.py && python3 gen.py` inside `scripts/`. That puts bin.png, norm.png and geom.json there, as the REPORT describes. I then moved the two SVGs to the run folder and ran the run.sh inkscape/convert lines from `claude-T/`, where its relative fixture path `../../../fixtures/sketch.jpg` resolves.
- Outputs: sketch-lines.svg, sketch-color.svg, sketch-clean.png 2000×1485 grayscale, sketch-color.png 2000×1485 (RGBA), compare.png 2000×750 (RGBA).
- Source edit: in `scripts/s1.py`, the absolute fixture path `/home/user/Vixl/evals/tool-comparison/fixtures/sketch.jpg` → `<mirror>/evals/tool-comparison/fixtures/sketch.jpg`.
- geom.json: the regenerated file differs from the committed one only in about 2e-12 on the sun fit. I restored the committed `scripts/geom.json`.
- Intermediate files left in `scripts/`: bin.png and norm.png. The REPORT lists bin.png but not norm.png, which s1.py also writes.
- Differences from REPORT:
  - sketch-lines.svg has **30** `<line>` elements, not the 29 the REPORT states. The committed geom.json also has 30 lines (roof 2, walls/top 3, windows 12, door 3, trunk 2, rays 8), so the REPORT miscounted. The output is unchanged by this.
  - The PNGs that Inkscape renders without `-b` (sketch-color.png and compare.png) carry an alpha channel. The REPORT does not say either way.

## T11/claude-T/round2: rebuilt yes
- Commands: `python3 scripts/round2.py` in `round2/`, which reads `../sketch-*.svg`. The render commands are not scripted in round 2, so I ran the round-1 commands the REPORT names, from `round2/`, with the fixture path `../../../../fixtures/sketch.jpg`.
- Outputs: sketch-lines.svg, sketch-color.svg, sketch-clean.png 2000×1485 grayscale, sketch-color.png 2000×1485 (RGBA), compare.png 2000×750.
- Source edits: none.
- Differences from REPORT:
  - sketch-lines.svg has **34** `<line>` elements. The REPORT says "32 (29 + roofR2 + 3 chimney)", but its own arithmetic gives 33, and the real base count is 30, so 34 is correct.
  - The chimney coordinates match the REPORT: sides at x 982/1046, top y 478, feet at y 557/620. No coral remains, and the roof pixel is (192,57,43).

## T12/claude-W (round 1): rebuilt yes
- Command: `python3 render.py`.
- Outputs: intro.mp4 is 1080×1080 h264 yuv420p, 30 fps, 180 frames, 6.000 s, 370,126 B. intro.gif is 540×540, 180 frames, 6.0 s, 1,713,322 B. intro-last-frame.png is 1080×1080. Frames were deleted after encoding, as in the original.
- Source edit: `render.py` `p.chromium.launch()` → `p.chromium.launch(executable_path="/opt/pw-browsers/chromium")`.
- Fonts: none downloaded. P052 and URW Gothic are installed system fonts (urw-base35), as the REPORT says.
- Differences from REPORT: the MP4 is 370 KB, against 368 KB in the REPORT. That is the normal variation of an x264 encode. The GIF's 1.71 MB matches.

## T12/claude-W/round2: rebuilt yes
- Command: `python3 render.py` in `round2/`.
- Outputs: intro.mp4 is 1080×1080 h264 yuv420p, 30 fps, 240 frames, 8.000 s, 435,753 B. intro.gif is 540×540, 240 frames, 8.0 s, 2,166,251 B. intro-last-frame.png is 1080×1080.
- Source edit: the same Chromium `executable_path` edit in `round2/render.py`.
- Differences from REPORT: the MP4 is 436 KB against 438 KB, and the GIF is 2.17 MB against 2.18 MB. These are encode-size differences only. Specs, frame counts and durations match.
