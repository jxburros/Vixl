# Rebuild log: T13-T16 (all runs except claude-V)

All runs were rebuilt by running the committed source scripts inside this mirror. No fonts were downloaded: every font the sources name (P052, URW Gothic, DejaVu Sans/Serif) was already installed locally, which matches what the REPORTs say (local system fonts, no web fonts).

Environment: Pillow, NumPy, ImageMagick 6.9.12-98, ffmpeg 6.1.1 (with libass), Playwright Chromium at `/opt/pw-browsers/chromium` (chromium-1194).

## T13 claude-C (round 1): rebuilt yes
- Command: `python3 make_keeper.py` (in the run folder). No source edits.
- `keeper-sheet.png`: 192 x 32 RGBA. 13 opaque colours (the script prints this).
- `keeper-sheet.json`: byte-identical to the committed file.
- `keeper-idle.gif`: 256 x 256, 2 frames, 400 ms each, loop=0.
- `keeper-walk.gif`: 256 x 256, 4 frames, 120 ms each, loop=0.
- Matches the REPORT.

## T13 claude-C/round2: rebuilt yes
- Command: `python3 make_keeper.py` (in round2/). No source edits.
- `keeper-sheet.png`: 256 x 32 RGBA, 13 opaque colours. The coat is red, and the wave frames have the raised hand.
- `keeper-sheet.json`: byte-identical to the committed file.
- `keeper-idle.gif`: 256 x 256, 2 frames at 400 ms. `keeper-walk.gif`: 256 x 256, 4 frames at 120 ms. `keeper-wave.gif`: 256 x 256, 2 frames at 250 ms. All three have loop=0.
- Matches the REPORT.

## T14 claude-T (round 1): rebuilt yes
- Command: `python3 build.py`. No source edits.
- `lighthouse.ass`: byte-identical to the committed file.
- `assets/bg_title.png`, `bg_verse.png`, `bg_chorus.png`, `beam.png`, `glow.png`: regenerated.
- `lighthouse.mp4`: 1280 x 720, H.264 High, yuv420p, 30 fps, 960 frames, AAC-LC 44.1 kHz mono. Video, audio and container are each 32.000 s.
- Differences from the REPORT:
  - The star field in `bg_verse.png` comes from ImageMagick's unseeded `+noise Random`, so the stars are placed differently from the original render. The design and the commands are unchanged.
  - ffprobe reports the AAC stream at about 140 kb/s. The REPORT gives 160 kb/s, which is the `-b:a` setting.
  - The `Next` style is DejaVu Sans italic, but no DejaVu Sans Oblique face is installed here. libass therefore synthesizes the slant. The REPORT says rendering depends on the installed fonts.

## T14 claude-T/round2: rebuilt yes
- Command: `python3 round2/build.py`. No source edits.
- `lighthouse.ass`: byte-identical to the committed file.
- `assets/*.png`: regenerated (the same five files).
- `lighthouse.mp4`: 1280 x 720, H.264 High, yuv420p, 30 fps, 960 frames, AAC-LC 44.1 kHz mono, 32.000 s.
- The same three notes as round 1 apply: the random stars, the measured AAC rate of about 140 kb/s, and the synthesized italic.

## T15 claude-C (round 1): rebuilt yes
- Command: `PYTHONPATH=<scratch>/pylib python3 make_pattern.py`. The REPORT says pycairo 1.29.2 was pip-installed, and it was not installed here. I installed it with `pip install --target <scratchpad>/pylib pycairo==1.29.2` (system cairo 1.18.0). No source edits.
- `tile.png`: 1024 x 1024 RGB. `tile.svg`: 1024 x 1024 viewBox with 303 `<path>` elements. `preview-3x3.png`: 3072 x 3072. `mug-wrap.png`: 2550 x 1050, with the label text in P052 Bold.
- The script printed counts of kelp 8, wave 8, shell 12 and dot 140, and edge diffs of L/R 3.18 and T/B 0.54. These match the REPORT.

## T15 claude-C/round2: rebuilt yes
- Same pycairo setup as round 1. No source edits.
- `tile.png`: 1024 x 1024. `tile.svg`: 197 `<path>` elements, which matches the REPORT. `preview-3x3.png`: 3072 x 3072. `mug-wrap.png`: 2550 x 1050.
- The script printed counts of kelp 5, wave 5, shell 8 and dot 93, and edge diffs of L/R 1.78 and T/B 0.24. These match the REPORT.

## T15 claude-W (round 1): rebuilt yes
- Commands: `python3 make_pattern.py tile.svg`, then `python3 render.py`.
- Source edit to `render.py`, line 32: `p.chromium.launch()` was changed to `p.chromium.launch(executable_path="/opt/pw-browsers/chromium")`. The default launch fails here because the browser is missing.
- `tile.svg`: 1024 x 1024. The script placed kelp 7, wave 8, shell 13 and dot 130, with 10 wrapped copies.
- `tile.png`: 1024 x 1024. `preview-3x3.png`: 3072 x 3072. `mug-wrap.png`: 2550 x 1050, with "Tidewick" in P052 Bold.
- Seam check: col0/col1023 2.27, col0/col1 1.74, row0/row1023 2.39, row0/row1 2.91. These are exactly the REPORT's numbers.

## T15 claude-W/round2: rebuilt yes
- Same `render.py` launch edit as round 1.
- The script placed kelp 5, wave 5, shell 9 and dot 87 (47 + 40), with 6 wrapped copies.
- `tile.png`: 1024 x 1024. `preview-3x3.png`: 3072 x 3072. `mug-wrap.png`: 2550 x 1050.
- Seam check: 3.68 / 2.76 / 1.22 / 1.85. These are exactly the REPORT's numbers.
- All shells are amber.

## T16 claude-W (round 1): rebuilt yes
- Command: `python3 render.py` (in the run folder).
- Source edits to `render.py`:
  - The `launch()` call now sets `executable_path="/opt/pw-browsers/chromium"`.
  - The `goto` URL `file:///home/user/Vixl/evals/tool-comparison/runs/T16/claude-W/menu.html` now points to the same path inside the mirror.
- `menu.pdf`: 1 page, 612 x 1008 pt. Fonts P052-Roman, P052-Italic and URWGothic-Demi are embedded as Type 3, as the REPORT says.
- `menu-preview.png`: 1275 x 2100.
- The script printed one decimal x of 655.56, no overflow, a doc height of 1344 and a minimum font of 12.67 px. These match the REPORT.

## T16 claude-W/round2: rebuilt yes
- The same two `render.py` edits, with the URL pointing to `round2/menu.html`.
- `menu.pdf`: 1 page, 612 x 1008 pt. `menu-preview.png`: 1275 x 2100.
- `pdftotext` shows "Oat milk +$0.75" and no "Drip refill". The prices are +$0.25.
- The script printed one decimal x of 655.56, no overflow and a doc height of 1344. These match the REPORT.

## Not rebuilt
None.
