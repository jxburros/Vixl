# Field report: building an AI literacy packet with Vixl 0.23.0

The brief was a packet that teaches, explores, demystifies, explains and encourages AI use. I built it with Vixl 0.23.0 to test both new and older features. It holds 4 illustrations, 4 creative pieces plus a logo package, 5 professional documents, 5 animations and 6 reusable workflows. Each piece rebuilds from its folder's `build.py`.

The work was split into four slices. Each one logged its friction as it went, with commands, exact error text and repros:
[illustrations/NOTES.md](illustrations/NOTES.md) (covers creative as well), [documents/NOTES.md](documents/NOTES.md), [animations/NOTES.md](animations/NOTES.md), [workflows/NOTES.md](workflows/NOTES.md).
This report summarises those notes. Findings marked **(re-verified)** were reproduced a second time, independently, while this report was written.

## The short version

- **The output is good.** Most pieces would pass as professional work with little or no hand-finishing:
  - the neural-network illustration,
  - the AI 101 deck,
  - the term-of-the-day cards,
  - the kinetic type and the robot animation.
- **Errors, checks and suites are the best parts.**
  - Errors name the field and the fix.
  - `workflow act` with a suite refused bad edits with exact numbers.
  - Forms and exports are honest about what they wrote.
- **The 0.23 house style is a real improvement.** The variety levels now change the result, and the loop/motion fixes in 0.23 worked the first time.
- **Biggest problems:**
  1. The MCP server in this repo does not start (it pins an unreleased tag).
  2. A handful of geometry bugs: groups cut off strokes, `scale` ignores the pivot, rotation drifts.
  3. A GIF export crash.
  4. Rolled "large" headlines split words mid-word while `check` passes them.
  5. Text-reflow gaps whenever variables or longer copy are involved.
  6. GIF colour loss.
  7. Slow MP4 export and slow checks.

## What is in the packet

| Folder | Pieces | Vixl features used |
| --- | --- | --- |
| [illustrations/](illustrations/) | Inside a neural network (1920×1200), Byte the AI-helper mascot (rig with pivots, plus 3 poses), "AI reads in tokens" seamless tile and card, The training loop (brain made of circuits) | pen paths, pathfinder, radial-repeat, pattern-scatter (seam score), scatter along a path, glow and soft-halo looks, pivots, strict SVG export |
| [creative/](creative/) | "AI, demystified" poster (best of 10 rolled seeds, then hand-finished), "5 AI myths, busted" Instagram carousel, AI Explorers Club logo and logo package (104 files), sticker sheet | `roll` with tiers and `--lock`, layouts, masters/pages with `${page}`, live `link` layers (one mascot reused in 7 places), `tear`, watercolor/sketch/risograph/duotone looks, `logo-package` |
| [documents/](documents/out/) | AI 101 deck (9 slides plus a hidden backup slide; PDF, editable PPTX, HTML presenter), two-page "What is AI, really?" handout (vector PDF, QR code), fillable "My first AI experiment" worksheet filled from CSV, Responsible-AI checklist (CMYK PDF with bleed), 4 merged certificates with crop marks | pages and masters, speaker notes, native PPTX chart, diagram-from-text, rich text, text flow over columns and pages, form fields with rules, `form-fill`, `merge-impose`, `check deck/form/print` |
| [animations/](animations/out/) | Neural network "thinking" loop, "Ask. Iterate. Verify." kinetic type, robot helper (walk, wave, speech bubble), "How a chatbot predicts the next word" explainer, "AI-curious" sticker loop | keyframes and easing, `animate-preset draw-on`, `text-animate` presets, `motion` wiggle/line-boil/pulse, seamless loops with wrapped staggers, `character` with the 0.23 front-view walk, MP4/GIF/WebP export, contact sheets |
| [workflows/](workflows/) | 01 term-of-the-day cards from CSV (12 cards, contact sheet, 4-up print PDF); 02 one message at six sizes (adapt vs recompose); 03 suite-gated edit pipeline with `vixl diff`; 04 proof page for the whole packet; 05 variety study (house style 1 vs 2 × low/medium/high); 06 throughput (100 cards) and REST smoke test | brand.json, variables, `render --data`, `merge`, production runs, suites, `workflow act`, `diff`, `proof`, `roll --house-style`, REST `/compose` `/render` `/check` |

The proof page, [workflows/04-proof-page/output/ai-packet-proof.html](workflows/04-proof-page/output/ai-packet-proof.html), is one offline page for reviewing 29 of the outputs, with approve and reject buttons.

## What worked well

- **Errors.** Unknown fields list the accepted names, and a failing batch reports every bad operation at once. Nothing applies half-way.
- **Suites and `workflow act`.**
  - It refused a teammate's change and my own first "fix", with exact numbers: contrast 4.14:1, a size ratio of 0.889, a −80 px overlap, a 2.4 px edge margin.
  - Suites caught problems the generic check passed.
  - This is the strongest reason to use Vixl for team or unattended work.
- **Forms.**
  - The fillable PDF has real field actions: date, number range and pattern.
  - Accessible names are clean, the typing font is embedded, and the language and title are set.
  - `form-fill` errors name the row and the key, never the value.
- **Export honesty.** Every report said whether anything fell back to raster (nothing did). PPTX listed unembedded fonts with their licences and wrote a native chart, notes and the hidden slide. SVG matched PNG with no embedded rasters.
- **0.23 loop and motion fixes**, all working first time:
  - wiggle and line-boil lasting the whole loop and closing it, with a rounding warning;
  - staggers wrapping round the loop end, reported under `normalized`;
  - exact WebP loop counts;
  - bounce contact keys on the frame grid;
  - a front-view walk that reads as walking.
- **House style 2.** Over 24 rolls, variety levels now matter: under house style 1 a seed gave the same layout, palette and pairing at every level. Dark mode, sharp corners and stronger type contrast appear. The 0.23 `watercolor` and `sketch` looks are good.
- **Live `link` layers.** One mascot document fed the poster, five carousel slides and the stickers, including in PDFs.
- **Speed where it counts.**

  | Step | Time |
  | --- | --- |
  | Card apply | 1.9 s |
  | `compose` | 1.5 s |
  | REST `/render` with variables | 0.25 s |
  | REST `/compose` dry run | 0.36 s |
  | Deck build and export | about 1 s |
  | 100 cards through a Python render loop | 21 s (211 ms each) |

- **Reproducible rolls.** Python gave exactly the CLI's result for all 10 seeds.

## What was tough to use

- **Rigging your own artwork as a `character`.**
  - Bone origins are relative to the character group's box, and that is undocumented; the first try put the arms 20–70 px off the shoulders.
  - `character-rig` silently resets every part's pivot.
  - There is no pose keyframe and no wave cycle. Baked poses become separate x/y/rotation keys, so a hand came off the wrist between keys until a key was baked every frame.
  - The illustration slice could not bind Byte at all: "Layers must share a parent", for the nested structure the mascot guide recommends.
- **Making variable templates reflow.**
  - `stack` and width-only `text-layout` boxes are measured at apply time and do not reflow under `render --data` / `render --set`.
  - `text-set` with longer copy warns "is cut off" instead of growing the box.
  - The only working technique was per-row production `actions` re-running `text-layout`, and that is not documented as a reflow technique.
  - Layouts size their boxes from the unresolved `${placeholder}`, so layouts and variable templates don't combine.
- **Diagrams at presentation size.**
  - Labels wrap at a fixed ~170 px whatever the font or node size, and break words ("paramete/rs").
  - To get bigger labels you have to ask for a smaller `size`.
  - Swimlanes run past their area.
  - The deck's flowchart ended up small on its slide because of this.
- **Seamless loops play every entrance back out automatically.** With mixed presets the exit was jumbled. A clean shared fade-out needed `mode: in` on each `text-animate` and `close: false` on each preset.
- **Palette roles on a fresh document.**
  - A new design document has no `@role` swatches until a layout runs, so `@accent` is an error and unfilled shapes come out grey, even though the palette is stored in `design_defaults`.
  - `palette-apply` does not recolour the canvas.
  - Diagrams therefore don't get the documented `palette` theme.
- **Small units and schema text.**
  - `marker_size` has no unit and values 1–5 silently draw nothing.
  - `stroke_color` is listed as animatable but fails on shapes.
  - A `pen` layer can't be edited in place as `pen`.
  - `vixl schema` can't print one operation.
  - Text has no letter-spacing, and radial gradients have no centre setting.
- **`check(checks=["deck"])` runs only the deck check.** A carousel looked clean until a plain `check()` found six legibility fixes. The two-check habit isn't obvious from the docs.

## What didn't work right

Bugs, with the slice that found each one; repros are in the linked notes.

| # | Problem | Found in |
| --- | --- | --- |
| 1 | **The repo's `.mcp.json` MCP server fails to start.** It runs `uvx --from …/refs/tags/v0.23.0.tar.gz`, but the latest release is v0.22.1, so the fetch is a 404. The same unreleased URL is in README.md, docs/getting-started.md and docs/ci.md. A local `vixl mcp` works. **(re-verified)** | coordinator |
| 2 | **A group cuts off its children's strokes** at their geometric boxes: a 20 px stroke on the edge of its box renders 10 px once grouped, and `check` says nothing. **(re-verified: 20 px vs 10 px)** | illustrations #1 |
| 3 | **`scale` ignores the pivot** and always shrinks toward the top-left. **(re-verified: bbox stays at 100,100–199,199)** | illustrations #2 |
| 4 | **`rotate` without an explicit pivot drifts** instead of turning about the centre, although the docs say centre is the default. **(re-verified: centre moves from 200,200 to 206,256)** | illustrations #3 |
| 5 | **GIF export crashes with `IndexError`** when the timeline has identical consecutive frames and the GIF exceeds 1 MB or `max_bytes`. The size warning's trial WebP gets merged durations but unmerged frames. **(re-verified with the 64×64 repro)** | animations |
| 6 | **Rolled "large" headlines split words mid-word with no hyphen**, and `check` passes them: "demysti/fied", "de/mysti/fied" on 9 of 10 poster rolls (see `creative/poster-roll-comparison.jpg`); "anythi/ng." in 2 of 12 house-style-2 social rolls. | illustrations, workflows |
| 7 | **`vixl compact` changes the design.** It deletes the bold/italic faces that rich text resolves automatically as "unused", then reports the design unchanged. | documents #1 |
| 8 | **Markdown text flows ignore the 0.23 line-height table** (about 2× leading). With `paragraph_spacing > 0` they overfill their frames, failing Vixl's own bounds check. | documents #2–4 |
| 9 | **Chart value-axis ticks collapse** to a single "0%" tick with `max` and a large `font_size`. | documents #5 |
| 10 | **A trailing hidden page shows "10 / 9"** in the render and the PPTX. | documents #6 |
| 11 | **`halftone` ignores `color` and the fill**: always black dots on white. | illustrations #4 |
| 12 | **Arrowheads ignore stroke trim**, so the head floats ahead of a draw-on line. | animations |
| 13 | **`shape line` with `from`/`to` gets a canvas-sized box.** Relation rules give nonsense and a 12-row merge took 222 s instead of 10 s, with no warning. Paths in canvas coordinates have the same issue (21–23 s first render with 78 paths, 2 s with tight boxes). | workflows, illustrations #7 |
| 14 | **Suite `contrast` and `vixl info --target` misread text at fractional y** (which `baseline_y` produces): the same text reads 4.81:1 at y=88 and 2.85:1 at y=87.724. | workflows |
| 15 | **Layout `label`s are uppercased before variables resolve**, so `${num}` becomes `Undefined variable: NUM`. | workflows |
| 16 | **The built-in contact sheet (`export(page="all")`) re-wraps text at thumbnail size**, so a line that fits on the page is clipped in the sheet. The packet's carousel sheet is now assembled with Pillow for this reason. | creative follow-up |
| 17 | **Proof page:** one unreadable item (a `.vixl` with a missing linked file) aborts the whole page, and images are embedded twice (39 MB at the default image size). | workflows |
| 18 | **Smaller issues:**<br>• `check` says `passed: true` alongside `fix` findings.<br>• `vixl compare` rejects `previous` and `head~1`.<br>• An export range that isn't a whole number of frames fails with "lower fps".<br>• Python `export(pages="all")` fails although the CLI form is documented.<br>• `reparent` shifts pixels by about 1 px.<br>• Production runs without suites report clipped output as `completed`. | various |

### Checks that missed or misfired

- **False positives:**
  - A `hard-shadow` look on a group with text makes that text measure 1.00:1 contrast.
  - Wrapped copies in a pattern tile raise `fix` findings that `allow_crop` doesn't silence.
  - Loop-seam findings flag children of a group faded to 0 and strokes trimmed to nothing; there were 93 identical lines on one piece.
  - A standard slide footer is a safe-area `fix`.
- **Misses:**
  - Linked layers are not in the overlap check.
  - `empty-poster` missed a blank frame 0 because the last frame was also blank.
  - `modern-bulletin`'s rule runs through its label on wide sizes (visible in `workflows/02…/comparison-sheet.jpg`, x-header and slide rows) and is reported only as 1.00:1 contrast or not at all.
  - On 9:16 sizes the safe layouts use a ~500 px column, so the story version is a small block in an empty canvas, and `check` passes it.
- **`adapt-layout` (rescale the master) left `fix` findings on 5 of 6 sizes.** Re-running the layout per size passed on all 6, after a layout swap for LinkedIn and a smaller base size for the story.

### Quality and performance

- **GIF colour.** The shared GIF palette is built from a downsampled montage, so small bright accents go grey even at 256 colours: an amber light became beige and a coral heart became mauve. The size warnings steer you to `ordered` dither, which makes it worse. Every GIF here uses `dither="none"` at about 2.2× the size.
- **MP4 export** runs at about 0.4–0.75 s per 1080p frame (robot: 210 frames in 2–2.5 min), with nothing shared between the contact sheet and the export.
- **Transparent WebP** is 2–3× larger than opaque, and `quality` barely changes it.
- **Checks take 5–27 s** on a poster and 5–9 s per document. `merge --check design` takes 10 s for 4 copies, versus 0.5 s without.
- **Production reruns** with nothing changed still take 70% of the original time, and leave a 7 MB render cache in the output folder.
- **A CMYK PDF without an ICC profile** dulls colours noticeably, with no warning.

## What was not used, and why

- **MCP tools** (`vixl_compose`, `vixl_adapt_layout`, `vixl_render_preview`, `vixl_timeline_preview` …): the server failed to connect (bug 1), so everything ran through the CLI, Python and REST. `vixl_adapt_layout` has no CLI twin that writes several sizes in one call.
- **AI provider features** (generate, inpaint, OCR, plan): no provider was configured. The packet doesn't need generated images.
- **Camera, depth, lighting, particles, audio tracks, lip-sync, cut-paper:** they didn't suit flat educational graphics; particles would fight readable text.
- **`organic`:** its generators are plants and creatures, so the brain was built with pathfinder.
- **`irregular`:** the mascot was kept crisp for animation.
- **`tear`:** used only on the BUSTED stamps.
- **`compose`:** one-shot; rolling and comparing seeds first suited the poster better.
- **Layouts, rolls and looks for the documents:** each document rolled a different direction (Inter, Libre Baskerville, peach backgrounds) when one brand was wanted across five documents. Hand layout with a shared palette was more predictable, and the house style says no look for documents.
- **Signature and comb form fields, editable prefills:** not needed for a worksheet.
- **Durable jobs, `capture`/`instantiate` recipes:** 100 cards finished synchronously in about 70 s; production `actions` covered the rest.
- **APNG, sprite sheets, the `chat`/`web`/`email` GIF presets:** the presets cut colours, which damages accents.
- **The GitHub Action:** workflow 3 reproduces its check, diff and proof steps locally; nothing was pushed to CI.

## Suggested fixes, in priority order

1. **Release v0.23.0**, or pin `.mcp.json` and the install docs to an existing tag. Today the repo's own MCP configuration and quick-install commands fail.
2. **Fix group stroke clipping, `scale` about the pivot, and the default rotation centre.** They silently change artwork and `check` sees none of them.
3. **Fix the GIF `IndexError`.** Pass the merged frames to `webp_trial`, or catch the error there.
4. **Stop large rolled headlines from breaking words.** Shrink to fit the longest word, or hyphenate. Add a `check` rule for mid-word breaks.
5. **Text reflow:**
   - grow width-only boxes on `text-set`;
   - reflow `stack` and boxes under `render --data`;
   - resolve variables before layout uppercase and measuring.
6. **Diagram label wrapping** that follows node size and never breaks words.
7. **Make `compact` keep the faces rich text uses.** Fix Markdown flow leading.
8. **GIF palette from full-resolution frames**, or a per-accent reserve. Stop suggesting `ordered` dither when it costs colours.
9. **Give `shape line`/`from`/`to` and canvas-coordinate paths tight boxes.**
10. **Check coverage:**
    - include linked layers in overlap;
    - drop the `hard-shadow` contrast false positive;
    - flag tiny content on tall canvases;
    - document that `checks=[…]` replaces rather than adds.

## How the packet was verified

Every piece was checked with the relevant `vixl check` (design, deck, form `--sample worst`, print, motion, character) or a suite, and fixed until only review or informational findings were left. Every render, PDF page, contact sheet and animation frame was looked at, and visible problems were sent back for fixes. One example: carousel slide 4 led to bug 16. Content claims are kept to well-known facts. Charted numbers and probabilities are labelled illustrative.

### Known leftovers

- `workflows/02…/comparison-sheet.jpg` clips its last caption ("suite pass…").
- That sheet shows the `modern-bulletin` rule-through-label and tiny-story problems described above; they are left visible on purpose.
- The HTML presenter was checked structurally, not in a browser.
