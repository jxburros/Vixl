# Field notes: Vixl 0.23.0, "useful workflows" slice (AI educational packet)

Tester: an agent using the CLI and Python API only (the Vixl MCP server failed to connect in this
session: `vixl (CONNECTION_CLOSED): "Connection closed"`). Machine: shared Linux container.
All commands were run from the repository root or the workflow folder named in each section.
Logged in the order things happened; the summary below was written at the end.

## Summary

**Worked well**
- `workflow act` as a gate: refuses a change atomically and says why, with numbers (contrast 4.14, ratio 0.889,
  overlap −80 px, 2.4 px margin). It caught my own bad fix as well as the teammate's request.
- Check suites in general: `hierarchy`, `relation`, `contrast`, `text-fit`, `design` rules caught real
  problems the plain `check` passed (collapsed hierarchy on story sizes, overlap after a resize).
- `render --data` checks every row and reports clipping honestly; `merge` makes a print-ready 4-up vector PDF
  in about a second, with a useful dry run.
- Production `actions` re-run `text-layout` per row, the only way to make a variable template reflow.
- `vixl diff --mode side-by-side`, `compose` (one call, 1.5 s), REST `/render` with variables (0.25 s) and
  `/compose` dry runs, the proof page's decisions JSON.
- House style 2 is visibly better than 1 for a sparse brief, and variety levels finally mean something.
- `--dry-run` returns the same layer IDs the real apply creates; `reparent` keeps appearance; `color scale
  --count` and the `layer-intent` flags work as described.

**Bugs and misleading results (details and repros in the log)**
1. `shape line` with `from`/`to` gets a canvas-sized box: suite relations go wrong and rendering got ~20× slower
   (12-row merge 222 s vs 10 s). No warning.
2. Suite `contrast` rule and `vixl info --target` report 2.85:1 for 4.81:1 text placed at fractional y
   (`baseline_y` produces those); the design check passes the same text.
3. Bold-tier / `headline: large` layouts break words mid-word ("anythi / ng.", "Unders / tand") and `check`
   passes them.
4. Layout `label`s are uppercased before variables resolve (`${num}` → `Undefined variable: NUM`), and layouts
   size their boxes from the unresolved `${placeholder}`.
5. A new design document has no `@role` swatches until a layout runs, so `@accent` is an error and unfilled
   shapes are grey even though the document has a rolled (or brand) palette.
6. On 9:16 sizes the safe layouts use a ~500 px column and fit the headline down to the subtitle's size;
   `check` passes. `modern-bulletin`'s rule strikes through its label on wide sizes (reported only as 1.00:1
   contrast, or not at all).
7. A proof page fails entirely on one unreadable item, and embeds every image twice as PNG (39 MB for 64 items
   at the default size).
8. `workflow run` without suites reports clipped output as `completed`; a rerun with nothing changed still
   takes 70 % of the original time; production leaves a 7 MB render cache in its output folder.
9. Small previews can show text clipping that the full render does not have.
10. CLI `vixl compare` rejects `previous` and `head~1`; `vixl check` says `passed: true` alongside `fix` findings.

## Log

### Setup
- `vixl new --purpose social --seed 7 -o t1.vixl --json`: 1.5 s including a font download
  (`creation.fonts.origin: "download"`). `creation` is clear: size from purpose, background from palette.
- With a workspace `brand.json` that names `"pairing": "lexend-atkinson"` (no embedded fonts),
  `vixl new instagram-portrait --seed 3` reports
  `"fonts": {"installed": false, "reason": "the workspace fonts apply"}`, which reads as "no fonts were
  installed". In fact the document does have Lexend + Atkinson embedded (`inspect` shows `typography`
  and `fonts`). Meanwhile `vixl manifest` lists `"dependencies": {"fonts": []}` for the same document.
  Two surfaces disagree with the document; minor but confusing when auditing a template.

### Workflow 1: term-of-the-day cards (template + CSV)
- **Bug: layout `label` is uppercased before variables resolve.**
  `layout-apply framed ... "label":"AI term of the day · ${num}"` with a defined variable `num` fails:
  `ERROR: operations[4] (layout-apply): Undefined variable: NUM. Define it with a variable operation, add
  |default:TEXT, or write $${NUM} for the literal text ${NUM}`. The house-style "uppercase labels" rule
  transforms the raw string, placeholder included. Workaround: name the variable in capitals (`NUM`).
  Repro: `vixl new instagram-portrait -o c.vixl` then apply
  `[{"type":"variable","name":"num","value":"08"},{"type":"layout-apply","name":"framed","title":"T","label":"Day ${num}"}]`.
- **Layouts size their text boxes from the unresolved placeholder.** `layout-apply` with
  `"subtitle":"${definition}"` (definition = 130 characters) builds a one-line 723x35 box for the literal
  `${definition}` and immediately fails its own check: `'subtitle' does not fit its 723×35 text box at 37 px
  and is cut off (it needs 707×134)`. So layouts and variable templates do not combine; I built the card
  by hand instead.
- **Auto-grown boxes and `stack` do not reflow at render time.** A `text-layout` with only `width` (the 0.23
  "grows its height" change) and a `stack` column are measured once, at apply time, from the placeholder
  text. `vixl render --set term='Large language model' --set definition='…long…'` then clips the text to the
  placeholder's one-line height, silently (no warning in the render result). `render --data` *does* report it
  per row (`'term' does not fit its 900×78 text box … it needs 779×178`), which is the saving grace.
  Workaround that works: fixed `width` + `height` boxes sized for the longest copy (text wraps per row).
- **No `@role` swatches on a new design document.** `vixl new instagram-portrait --seed 11` beside the
  brand stores the brand palette in `design_defaults.direction.palette`, but `inspect` shows
  `"swatches": null`. The first `{"type":"solid",…,"color":"@accent"}` fails with
  `ERROR: operations[5] (solid): Unknown swatch: @accent`, and a shape with no fill gets the no-palette grey
  (`defaults: [{'layer': 'r', 'fill': '#8c8c8c'}]`) and text gets `#111111`, not `@ink`. Same without a
  brand (`vixl new --purpose social --seed 7`). The changelog says unfilled shapes use `@accent`
  "when the document has a palette"; a rolled palette apparently does not count until a `layout-apply` /
  `palette-apply` writes the swatches. Workaround: emit one `swatch` op per brand role.
- **Big perf trap: `shape line` with `from`/`to` gets a canvas-sized box.** I drew a 26-edge
  neural-network motif with `{"type":"shape","shape":"line","from":[790,967],"to":[875,959]}`. It renders
  in the right place, but each layer's box is `x 0, y 0, 1080×1350` (`from`/`to` are documented as "Arrow
  point in local layer pixels"). Consequences: (1) the group around them is canvas-sized, so suite
  `relation` rules fail nonsensically (`motif-in-panel`: positions `overlapping, contains`, distance -290);
  (2) everything got ~20× slower: `vixl check` 13.6 s, a plain `vixl render` 6.4 s, `render --data` of 12
  rows **222 s**. Switching the edges to `pen` with `points` (bounds `[787, 897, 91, 73]`) brought the same
  steps to 1.2 s / ~0.8 s / **10.2 s**. No warning anywhere that the line's box is the whole canvas.
- `render --data` checks every row by default and is honest about clipping. `workflow run` (production)
  runs **no** design check unless you attach suites: an earlier scratch run with clipped text reported
  `"status": "completed"`, `"checks": {}`. Easy to read as "all good".
- **Nice discovery: production `actions` re-measure text per row.** A width-only `text-layout` measured at
  apply time does not grow at render time, but an `action-define` holding the same `text-layout` ops, passed
  as `spec.actions: ["reflow"]`, runs after the row's variables are set, so boxes grow per row and a
  `constrain` (`definition.top = term.bottom+40`) follows. This is the only way I found to make a variable
  template reflow. It is not described anywhere as a reflow technique (docs say "Optional `actions` run before
  checks").
- **Bug: suite `contrast` rule and `vixl info --target` fail text at fractional y.** `baseline_y` places text
  at fractional y (here 87.724). Same layer, same colours (`#1d7a74` on `#fbf7ef`, 4.81:1):
  `vixl -p card.vixl move label --y Y` then `vixl -p card.vixl info --target label` gives p10 contrast
  y=87.724 → **2.853**, y=87.5 → 3.408, y=87.2 → 4.686, y=88 → 4.807. The design `contrast` check passes the
  same document, so the suite rule and the design check disagree. The changelog for 0.21 describes the same
  half-pixel bug as fixed for the design check; the suite rule / `info` path seems to still have it. `info`
  also reports `"background": "white"` although the canvas is `#fbf7ef`. Workaround: integer `y`.
- Font legibility check flagged my 28 px labels on a 1080-wide card (`'label' is 8.3 px tall at 320 px wide;
  aim for at least 10 px (font size 34+)`). Fair; raised all small text to 34 px.
- Real catch by the check: `accent-text` (#1d7a74) on the `surface` panel (#efe6d2) is 4.14:1 (`'try-label'
  contrast is 4.14:1 …; needs 4.5:1`). The brand's accent-text is only safe on the background. Used `@ink`.
- The brand check flags `alpha(@ink, 0.25)` strokes as "outside the brand palette" (24 warnings, one per
  edge). Reasonable, if noisy: one finding per layer, no grouping.
- The production run's own contact sheet is 800×540 px for 12 portrait cards, labels them `0001 completed`
  (variant IDs, not row values) and has no options. I built a 1880×2046 sheet with Vixl instead (`frame` +
  captions). A `downsample: "placed@2x"` frame sheet still saves a 2.6 MB `.vixl`, so the script deletes it.
- The production run writes its render cache into the output folder (`production/.cache`, ~7 MB for 12 cards).
  docs/production.md says timelines use the per-user cache "so output folders stay clean"; production stills don't.
- Timings (12 cards, 43 layers each): `apply` template 1.9 s, `check` 1.2 s, `render --data` 10.2 s,
  `workflow run` with 2 workers + suite + reflow action 12.5 s, export of the sheet 1.9 s. Whole build 28 s.

### Workflow 2: one message, six sizes
- `vixl compose --request req.json` with `"preview": "master-preview.png"` in the request fails with
  `ERROR: request: preview is true or an object with page, region, …`. The path goes on the CLI
  (`--preview P.png`) and the request takes `true`. Fine once known; the skill's one-liner
  `vixl compose --request req.json --preview p.png` is right, but I expected the MCP field to accept a path.
- `compose` with a layout `"look": "none"` → `Unknown field(s) 'look' for 'layout-apply'`. The stored roll
  (seed 5) put a grain look on the master and grain dropped the label to 3.84:1. The way to turn it off is
  `"direction": {"look": "none"}` inside the layout; not obvious from the error.
- Layouts name the `title` slot's layer **`headline`**. My suite targeting `title` came back
  `needs_review` for every rule (correctly not a pass, but I lost a run finding out). `layout show` could say so.
- `vixl check` returns `"passed": true` while listing `action: "fix"` findings (warnings such as legibility).
  Gate on `by_action.fix`, not `passed`.
- **adapt-layout vs recompose** (6 sizes, same brand, copy and seed): `adapt-layout --size` (0.7 s each) keeps
  the master's portrait-sized block in the middle of wide canvases and strands the CTA at the far left edge
  (linkedin-post, x-header, slide); it produced 1–6 `fix` findings per size (safe area, 2.8–8.5 px text at
  thumbnail width, `'subtitle' does not fit its 674×248 text box … needs 656×250`) and 2 suite failures.
  Re-running `compose` per size (1.5 s each) built native layouts that passed `check` and the suite on 5/6 sizes
  first time. For a comms team the recompose loop is the one to reuse; adapt-layout suits documents that were
  hand-edited after the layout.
- **Layout bug: `modern-bulletin`'s rule strikes through the label on wide canvases.** On linkedin-post
  (1200×627) the `quiet-rule` runs through `AI FIELD GUIDE`; the check reports it only as contrast
  (`'label' contrast is 1.00:1 … weakest at x 63–328, y 53–55`), not as overlap. On x-header and slide the rule
  touches the label's cap line and nothing is reported. Fallback to `offset-column` fixed linkedin.
- **Layout issue: 9:16 sizes collapse the hierarchy.** On `story` and `instagram-story`, modern-bulletin,
  offset-column, quiet-editorial and wide-statement all set a 493–533 px column (margin 250–272 px on a 1080 px
  canvas; a `direction.margin: 0.08` override still gave 250) and a headline fitted to 62–67 px over a 65 px
  subtitle. `check` passes; only my `hierarchy` rule (ratio 1.4) caught it. `base_size: 28` restores
  62/42 px but the copy then fills a third of the canvas. Visually the weakest of the six outputs.
- **Bug: `direction: {"headline": "large"}` on `story` breaks a word mid-word**: "Unders / tand the / AI you /
  use." at 110 px in the 493 px column, with no hyphen. `check` passes it.
- **Preview ≠ render for wrapped text.** A dry-run compose preview (288 px wide) of the story showed the
  subtitle's last line "can't do." cut off under the CTA; the full-size render of the same document wraps
  and fits fine, and `check` passes. So the small preview can show a defect that isn't there; when a preview
  looks wrong, render a full-size crop before trusting it.
- Timings: compose 1.5 s, check 1.3 s, suite 1.7 s, export 0.8 s, adapt-layout 0.7 s; whole build 67–89 s
  (with fallback attempts).

### Workflow 3: a check-suite-gated pipeline
- `vixl workflow act --request` is the right primitive for a gate: the teammate's request (teal `TRY IT`,
  definition 44 → 32 px, graphic ×1.35) came back `committed: false` with numbers that say what to change:
  `term-dominates` ratios `[3.25, 0.889]` (definition now smaller than the try-it text), `definition-readable`
  `actual_size: 32`, `tryit-clear-of-motif` distance −80 (overlap), `nothing-cut-off` with the design check's
  `'try-label' contrast is 4.14:1`. Exit code 1. Nothing was written.
- It also caught **my own** first fix: the enlarged graphic sat 2.4 px from the panel edge where the suite asks
  for 16 (`motif-in-panel`, distance 2.4). Second attempt (scale 1.15, x 748) committed. Exactly the behaviour
  I want from a gate.
- Pitfall in my first version of the script: after a refused `act`, the document is unchanged, so running the
  gate on it afterwards *passes* (it is still v1). `vixl diff v1 v3` reported `changed_fraction 0.0`, which is
  how I noticed. Gate on `committed`, not on a later check of the same file.
- `vixl diff A B --out d.png --mode side-by-side --max-fraction 0.05` is excellent for review: before | after |
  red diff, and `changed_region [104, 906, 872, 214]` pinpoints the edit. Note that `--max-fraction` measures
  size, not quality: the rejected v2 changed 4.89 % and passed the 5 % threshold. It belongs next to the suite,
  not instead of it.
- Data gate: a 13th CSV row with a 290-character definition fails `render --data`'s row check with a clear
  message (`'definition' does not fit its 920×217 text box at 44 px and is cut off (it needs 916×396)`);
  the shortened row passes. `render --data` exits 0 either way, so the script has to read the per-row JSON.
- Whole pipeline: 23 s (two gates, three `act`s, two diffs, two one-row merges).

### Workflow 5: variety study (house style 1 vs 2, variety low/medium/high, 4 paired seeds = 24 rolls)
Command per cell: `vixl new instagram-portrait -o D --background transparent --no-fonts` then
`vixl -p D roll --apply --for social --seed S --variety V --house-style H --set title=… --set subtitle=…
--set label=… --set cta=…`, `vixl check`, `vixl export`. roll --apply 1.4–2.2 s each (fonts mostly cached);
whole study ~2 min.
- **House style 1: the variety level does almost nothing.** For a given seed, low, medium and high gave the
  *same* layout, palette and pairing (e.g. seed 11 = right-margin · sky-umber · merriweather-source-sans in all
  three rows); only the look (none / soft-shadow / light-paper / subtle-grain) and background treatment changed.
  All 12 were light mode, rounded ("soft") corners, quiet. This matches the house-style decision record's
  diagnosis ("Low and medium differ only in the look pool").
- **House style 2 is visibly better as a default and does differentiate levels.** Low is still safe but
  already has more range than v1 high: framed modern-bulletin with an offset hard shadow, a dark nordic
  wide-statement, sharp corners, real heading/body contrast. Medium brought one bold roll (asymmetric-balance ·
  ocean · glow); high brought 2 bold + 1 avant-garde (centered-axis · peach, asymmetric-balance · neon on
  yellow, hero-statement · retro with Anton). Summary per cell is in `summary.json`. The `tier` and `purpose` are
  reported, which makes the study self-documenting.
- **But: v2 bold rolls break words mid-word, and `check` passes them.** `asymmetric-balance` with
  `headline: large` (medium seed 23 and high seed 23) set "Ask an / AI / anyt / hing." (85 px, 381 px column) and
  "anythi / ng." with no hyphen. Verified at full size (not a preview artefact):
  `vixl -p w.vixl roll --apply --for social --seed 23 --variety high --house-style 2 --set title='Ask an AI
  anything. Then check it.' …` → `check` passed with only informational findings. Same defect as the story
  case in workflow 2. A "word broken across lines" finding in `check` (or never breaking inside a word in the
  fit pass) would stop the most visible failure of the new bold defaults. The label also wraps an orphan
  "· WORKSHOP" line there.
- Same seed, different version = different direction entirely (expected; the stored `house_style_version`
  is what keeps old documents stable).
- Verdict: house style 2 is better for a sparse brief: more contrast between rolls, purposeful dark mode,
  stronger type, the craft rules visibly applied. Its weak spot is the bold tier's large headlines in narrow
  columns; until that is fixed, I would use `--variety low` (or `--lock tier=safe`) for anything automated and
  keep medium/high for human-reviewed exploration.

### Workflow 6: throughput (100 cards) and REST
4-core shared container, the 43-layer card template from workflow 1, 100 CSV rows:

| Path | Total | Per card |
| --- | --- | --- |
| `vixl render --data rows100.csv` (per-row design check, default) | 81.8 s | 818 ms |
| `vixl render --data … --no-check` | 27.6 s | 276 ms |
| `vixl workflow run` (reflow action + 14-rule suite), 1 worker | 126.7 s | 1267 ms |
| same, 4 workers | 68.6 s | 686 ms |
| same request again in the same folder (all outputs unchanged) | 47.7 s | 477 ms |
| Python: `Project.load` once, `p.render(variables=row)` loop, save JPEG | 21.1 s | 211 ms |

- The checked production run is the expensive path but the only one that reflows text per row and gates
  every output on the suite; all 100 completed. 4 workers give 1.85×, not 4×.
- **The rerun is not the near-free resume I expected.** docs/production.md: "Run again in the same directory to
  reuse verified unchanged results". Nothing changed, yet it took 47.7 s (vs 68.6 s), so most of the per-output
  work (presumably re-checking) still runs. Fine for correctness; worth knowing for CI budgets.
- The per-row check in `render --data` triples the time (818 vs 276 ms/card). It is worth it; it is the only
  thing that catches overflow in that path.
- REST (`vixl -p card.vixl serve --port N`): `POST /check` 0.79 s, `POST /render {"variables":{…}}` 0.25 s
  (PNG), `POST /compose` dry run with layout + check + preview 0.36 s (returns `preview_base64`, saves
  nothing, as documented), `POST /preview {"max_width":400}` 0.13 s. All worked first time; the server
  picked up `brand.json` beside the document. A render service for a "card of the day" bot is realistic.
  The REST compose preview of linkedin-post shows the same modern-bulletin rule/label crowding seen in
  workflow 2 and an orphaned "use." on the headline's second line; `check` passed.

### Workflow 4: proof page for the whole packet
`vixl workflow proof --request proof-request.json --workspace explorations/11-ai-packet`, items gathered at
run time from `workflows/*/output` and the sibling folders (illustrations, creative, documents, animations).
- Works and is genuinely useful: one offline file, thumbnails, format/size/colour mode, `check` findings for
  `.vixl` items, a before/after diff with `3.43% changed in [104, 906, 872, 214]`, approve/reject with a
  decisions JSON download, strict CSP. 29 items in 7.9 s with `max_size: 256`.
- **One bad item aborts the whole page.** A sibling's `creative/sticker-sheet.vixl` has a link whose source
  cannot be resolved: `{"error": "link_missing", "message": "items[36] (creative/sticker-sheet.vixl): Linked
  document not found: illustrations/mascot.vixl (looked for …/11-ai-packet/creative/illustrations/mascot.vixl,
  /home/user/Vixl/illustrations/mascot.vixl)"}`. 48 s of work, no page. For a review page, a card saying
  "could not render: link_missing" would be better than failing. My script drops the named item and retries.
  (The link problem itself belongs to the creative folder; reported to show the proof behaviour only.)
- **Size: every image is embedded twice.** Each card's thumbnail and its click-to-enlarge view carry the same
  base64 PNG (84 data URIs for 41 items, identical pairs). With the default `max_size` 1200, 64 items made a
  **39 MB** HTML file; 360 px → 6.6 MB; 256 px → 2.9 MB. Images are always PNG, so photographic or grainy
  items are 150–200 KB even at 344×360. Referencing one data URI from both places (or JPEG for opaque images)
  would roughly halve it; `max_size` also caps the "enlarged" view, so a small page means small zooms.
- `before` accepted a second file path fine. (I did not try revision refs here; see `compare` below.)

### 0.23 features exercised directly
- `vixl color scale '#1d7a74' '#fbf7ef' --count 5` → 5 OKLab steps, clean JSON. Good.
- `vixl layers` vs `layers --full`: the only difference is that long `path_nodes` are abbreviated
  (`"<163 bytes; vixl inspect motif-edge-0 shows it>"`). `layers` is still a 41 KB JSON dump for 43 layers;
  I expected a compact one-line-per-layer view like MCP's compact inspect.
- `vixl apply d.json --dry-run` now returns layer IDs, and they are the **same IDs** the real apply then
  creates (`lyr_4a9b3ad0c8c8e448`, `lyr_9f550874fd4dcb63` both times). Nice for planning follow-up ops.
- `vixl reparent badge-group --into motif` (motif rotated 10°): the badge keeps its canvas position
  (`canvas_bounds [900, 200, 60, 60]`, `rotation -10.0` compensates). A pixel diff before/after shows
  0.43 % changed in `[779, 198, 217, 933]` (the motif's edges re-rasterised after the group box grew),
  i.e. antialiasing-level, not a visible move.
- `vixl layer-intent motif --detached-ok --color-vision-safe` and `layer-intent term --role title` work and
  show up in `inspect`.
- `vixl house` / `house show social`: readable, matches docs/safe-variety.md.
- **`vixl compare` takes no relative refs:** `vixl -p card.vixl compare previous head --out c.png` →
  `ERROR: Unknown history reference: previous`; `head~1` → same error. The MCP/REST docs list `previous`,
  `head~N` for `vixl_render_compare`, and the proof page accepts `previous`. On the CLI you need revision IDs
  from `vixl history`.
- `--house-style 1` on `roll`: worked, and the result reports `house_style_version: 1` (no `tier`/`purpose`).
- `creation` reports: clear on every `vixl new --json` and in compose results (`size_from`, `background_from`,
  `fonts.origin`), apart from the brand-fonts wording noted at the top.
- Print merge (`vixl -p card.vixl merge --data terms.csv --out print-sheets.pdf --size letter --cols 2 --rows 2`):
  `--dry-run` first reported rows, columns, grid, 3 pages and one honest warning (`template_dpi: The template
  has no dpi, so it is placed at one pixel per sheet pixel`), then the real run wrote a 21 KB vector PDF with
  crop marks in 1.2 s. Cards come out 3.6 × 4.5 in. Like `render --data` it does not reflow text per row.
  Gotcha: `--out` outside the document's folder → `ERROR: Path is outside the workspace` (no path in the message).

## Features looked at but not used, and why
- **MCP tools** (`vixl_compose`, `vixl_adapt_layout`, `vixl_render_preview`): the MCP server did not connect
  this session. Used the CLI equivalents (`vixl compose`, a loop of `vixl adapt-layout --size`).
  `vixl_adapt_layout` has no CLI twin that writes several sizes in one call; the loop is 6 commands.
- **Layouts for the card template**: they size text boxes from the `${placeholder}` (see workflow 1).
- **`stack` for the card**: measured at apply time; does not reflow for `render --data` or `render --set`.
- **`capture` / `instantiate` recipes**: overlap with the production run for this use; `actions` in the
  production spec covered the reflow need.
- **Durable jobs (`submit`/`status`)**: 100 cards finished in ~70 s synchronously; not needed.
- **`logo-package`, decks, forms, timelines**: covered by the sibling folders (creative, documents, animations).
- **AI provider features**: none configured; the packet is about AI but nothing here needs generation.
- **GitHub Action (docs/ci.md)**: read it; workflow 3 reproduces its check + diff + proof steps locally. Did not
  push anything (instructions).
- **`vixl roll` without `--apply` previews**: skipped in favour of applying and checking every roll, since the
  check results were part of the study.

## Timings (all on a shared 4-core container)
| Step | Time |
| --- | --- |
| `vixl new` with font download / cached | 1.5 s / 0.5 s |
| Card template apply (43 layers) with `--check --suites --preview` | 1.9 s |
| `vixl check` (43-layer card) | 1.2 s |
| Same three steps with 26 `shape line` + `from`/`to` layers | 15.6 s / 13.6 s check / 6.4 s render |
| `render --data`, 12 rows (good template / line-shape template) | 10.2 s / 222 s |
| `workflow run`, 12 rows, 2 workers, reflow + suite | 12.5 s |
| `compose` (layout + check + preview + save) | 1.5 s |
| `adapt-layout --size` | 0.7 s |
| `roll --apply` (fonts cached) | 1.4–2.2 s |
| `workflow act` (14-rule suite) | ~1.5 s |
| `vixl diff` side-by-side | ~1 s |
| `merge` 12 cards → 3-page PDF | 1.2 s |
| proof page, 29 items (3 `.vixl` checked) / 64 items | 7.9 s / 108 s |
| 100 cards: render --data checked / no-check / production 4 workers / Python loop | 82 / 28 / 69 / 21 s |
| REST: /check, /render, /compose dry run, /preview | 0.79 / 0.25 / 0.36 / 0.13 s |

## Small things
- `vixl new -o X` always writes `.vixl-session.json` in the working folder (it "selects" the new document),
  even when every later command passes `-p`. Scripts that make many documents leave one in each output
  folder; I delete them.
- Seeded rolls (`roll --seed 11 …`) still write `.vixl/rolls.json` into the workspace, although docs say explicit
  seeds ignore roll history.
- `vixl merge`, `vixl compose` and `vixl workflow proof` refuse paths outside the workspace with
  `Path is outside the workspace` but don't name the path or the workspace they resolved.
