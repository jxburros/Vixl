# Checked production for agents

Mockups: `vixl_apply(workflow='mockup', request={"design": "poster.vixl", "mockup": "poster-wall", "output": "wall.vixl"})` places
a design in a phone, laptop, browser, poster-wall, business-card or mug template as a live, corner-pinned link
(a list of templates and `"output": "folder"` makes one each; `export: ["png"]` renders them). `mockup-list` lists
templates, their slots and print areas; `mockup-save` adds the workspace's own. See `docs/guides/output/linked-documents.md#mockups`.

Merch: the same workflow shows a design on a product, `vixl_apply(workflow='mockup', request={"mockup": "tee", "output":
"tee.vixl", "place": {"front-chest": "logo.vixl", "back": "art.vixl"}, "garment_color": "#14161c", "finish": "screen"})`.
Products: tee, long-sleeve, crewneck, hoodie (areas front-chest, full-front, back, sleeve-l, sleeve-r, hem-tag, inside-neck),
tote (front), sticker, sticker-kiss-cut, enamel-pin, patch, button (face), cap, beanie, socks. `garment_color` recolours only
the base layers; `finish` is screen, puff, embroidery, enamel, woven or none. `vixl_apply(workflow='print-art', request={
"mockup": "tee", "output": "print", "place": {...}, "dpi": 300, "spot_colors": 3, "underbase": true})` then writes each
area at its `print_size_mm` × dpi (PNG, an editable source, film-positive separations as PNG or PDF pages, and a white
underbase for dark garments only). See `docs/guides/output/merch-mockups.md`.

Localization: `locales-set {locales: {de: {headline: "..."}}, same_ok, fonts, fit: shrink|flag, min_size, rtl}` stores
per-locale variable values. `vixl_apply(workflow='locale-check', request={"locales": "all", "strings": "strings.csv"})`
(or `check` with `locales`, `vixl check --locales de,ja`) checks each locale on a copy and returns a locale x finding
`matrix` (overflow, fonts, untranslated, missing-key, line-count, design, suites). `workflow='localize'` writes
`<master>.<code>.vixl` and `formats` exports into `output_dir` for passing locales, holds failing ones (`held`), mirrors
ar/he/fa, and on re-run rebuilds only locales whose fingerprint changed; `spec` adds a locale axis to a campaign. A
strings CSV has a `key` column and one column per locale; an empty cell is a missing key and holds the locale. See
`docs/guides/automation/localization.md`.

Discover actions with `vixl_reference('workflows')` or `vixl workflow schema`.
Full reference: [production workflows](https://github.com/jxburros/Vixl/blob/main/docs/guides/automation/production.md).

1. Inspect the base document and create explicit `suite-set` rules for its requirements.
   Use `suite-capture` for protected layer structures/pixel regions. Do not overwrite
   baselines during an ordinary repair. Rule kinds: `assert`, `property`, `gap`, `spacing`,
   `relation`, `text-fit`, `contrast`, `hierarchy`, `color`, `palette`, `ink`, `balance`, `focal`,
   `count`, `text` (the drawn copy: `contains`, `forbid`/`pattern` regexes, `min_/max_characters`,
   `min_/max_words`, `case`, `brand`, `spelling: true` for unknown words with suggestions), `budget` (`max_layers`, `max_fonts`, `max_bytes`, `min_ppi`, `max_ppi`; `max_render_ms` + `proxy` in a rule of its own, always an advisory review), `alpha`,
   `design`, `container`, `unchanged`, `pixels`. `expected`, `to` and `ratio` may be `{ref: "master.vixl#layer.field"}` or `{ref: "master.vixl#suite:rule-id"}` to read a master document each run (at most 8; a missing one needs review) (fields:
   `vixl_reference('workflows').definitions.suite`; method: `vixl_reference("testing")`). Run suites with each
   batch (`vixl_apply(suites=true)`) and before every preview. `sampling` (or `check`'s request)
   takes `artboards`/`pages`/`comps` (`"all"` or names) to cover every variant in one run; each result names
   its `variant`. `suite-infer` proposes an explained starter suite from an approved document (`apply: true`
   saves it to the library, `group` makes a group inherit it, `from_group` infers across members).
   Library suites listed under `suites` in `group-define` or brand.json are inherited by reference; a
   document overrides a rule by `id` with a suite that has `extends: NAME`. Workflow `check` with no
   `suite` runs every attached and inherited suite.
2. Use `fit-text`, `arrange-grid`, or `adapt-layout` (an unedited `layout-apply` document is rebuilt from its recipe
   at the new size by default; `recompose: true` forces it after edits and replaces them; `arrangements` keeps the
   best-scoring re-arrangement) for predictable layout tasks;
   save a bounded sequence with `action-define`. `role-set`, `motion-define`, and
   `motion-apply` produce editable staggered/relative animation tracks.
3. Workflow `act` accepts operations, suites, dry_run and repair. It returns measurements and
   commits only if checks pass (`repair: true` first tries the built-in repair map on the candidate).
   `check` reports failed or needs_review; neither is a pass. Over pages, a rule about a layer on another page
   is `not_applicable` there and counts for nothing, as is a rule limited by its `pages` field to other pages. Every result has an `outcome`.
4. Workflow `capture` saves a `.vixl` recipe from explicit typed inputs and text/color
   bindings. Include defaults and difficult examples. Image slots use embedded asset IDs.
5. Workflow `plan` accepts a spec with rows, matrix, artboards, format and quality.
   Inspect its count before `run`, which also needs an output directory. Every output
   gets checks; up to three named repair_actions can run without changing the suites (`auto` runs the
   built-in repair map). A row that leaves a variable undefined or draws placeholder copy is `needs_review`,
   with findings naming the variant and `row`. `export_check` (`true`, a delivery spec preset such as
   `instagram-feed`, or inline fields) reads each written output back; the report is the result's `export_check` in
   `production.json`, and an output that fails it is held for review and not published.
6. For long production, call `submit` with `start:true`, then `status` with its returned
   ID. The source is snapshotted. `cancel` is cooperative; `resume` preserves remote IDs.
   Never blindly repeat an uncertain provider request.
7. Reuse components with library-save/search/open/place. Open preserves the editable
   document; place inserts its rendered snapshot. Preview draft/final without regenerating
   image assets. Persistent caches are enabled by production, workflow previews, timeline and film exports,
   and CLI `export`/`render` of saved documents (`vixl cache info|clear`; `VIXL_RENDER_CACHE=off`,
   `VIXL_CACHE_MAX_MB`). Sequences store a whole frame only when it is requested a second time, so moving
   films do not fill the cache; static layers are reused either way.
8. Film plans accept shots from stills, `.vixl` timelines or video clips, camera poses,
   crossfades, captions and explicit audio tracks. MP4/WebM/audio need ffmpeg. Generated
   video requires an explicitly configured HTTP job gateway; other image providers do
   not automatically gain video support.

9. Lyric videos: `lyric-video-plan` validates a song, an LRC file (timestamps, `[Section]`
   markers) and a template document with a `lyric` text layer (optional `lyric-next`,
   `section-label`, `intro`, `outro`, `bg-<section>`, `cue-<words>`, and `lyric-<section>`/`next-<section>` text
   layers that take over for one section) and reports the timed lines (with `settled` and `exit` times),
   `cues` and `section_windows` (`[[start, end], …]`); `lyric-video-build` writes an editable keyframed
   document and keeps the template's own keyframes except on the layer properties it writes
   (`template_track_replaced` warns); `lyric-video-export` renders the
   MP4/WebM with the song as audio, rendering an existing hand-edited build as it is (`rebuild: true`
   rebuilds; `build_stale` if the settings changed under edits), and reads the file back with ffprobe
   (`verification`: size, fps, frames, duration, audio rate/channels, frame quantisation). An empty timestamp clears the lyric and the
   preview, a line sung twice in a row holds instead of re-fading, and `cue_animation` (`in`/`out`,
   `motion: "sweep"`, `replay`, per-layer overrides in `cues: {"cue-fire": {…}}`) animates `cue-*` layers.
   `lead_in`/`tail` (ms) add silence for a title card (`intro`) and an end card (`outro`, shown from the last
   line's hide time); `end_at_audio` ends the last line with the song. `section_styles` (`{chorus: {size, color, x, y}}`) restyles
   the lyric per section; `sample_rate` sets the audio rate (default the song's). `segments: 10000` renders in
   parts that a re-run resumes; long songs also run as the `lyric-video` job kind. See
   `docs/guides/motion/lyric-video.md`. Every export verifies cue timing/text per occurrence; `verify: "full"`
   also decodes the entire file and samples up to four visual/brand frames per cue (400 total), with explicit
   unsampled coverage and source hashes. Export leaves review pending. After human review, `lyric-video-review`
   (`build`, `approve: true` or `changes_requested: true`, optional `findings`) records a decision that expires
   when the build changes. Only full passing verification with current approval can return `validated: true`.
10. Form filling: `form-fill` fills the open form from `values` (one copy) or a `data` CSV (one
   file per row, or `combine` into one PDF); the `form-fill` job kind freezes the form and the data
   and deletes the data copy when done. See `docs/guides/output/forms.md`.

11. Print merge: `merge-impose` (`vixl_apply(workflow='merge-impose', request={template, data, sheet, output, sheet_document}, document=)`)
   imposes a template and a CSV on print sheets: a vector-text PDF (selectable text) and/or an editable sheet `.vixl` of live
   `link` layers. Run it with `dry_run` first: the report names missing/unknown columns, overflowing text, tofu glyphs and the
   grid. `{"rerun": "sheet.vixl"}` repeats it after the data changes. See `docs/guides/output/imposition.md`.
12. Linked documents: a `link` layer shows another `.vixl` live (`fit`, `position`, `crop`, `artboard`, `source_page`,
   `variables`); `vixl_apply(workflow='links', request={})` reports ok/stale/missing with each resolved `path`, `link-refresh`
   records the seen revision, `links-relink {from, to}` follows moved sources, `link-embed` freezes it. Keep sources
   beside the document so the folder can be copied (`check` notes sources outside it). Use it instead of exporting a PNG and importing it into a derived design. See
   `docs/guides/output/linked-documents.md`.
13. Logo packages: `vixl_apply(workflow='logo-package', request={output, source?, trace?, mark?, wordmark?, variants?, png_sizes?,
   cmyk?, icons?, social?, proof?, zip?, overwrite?})` writes `source/` (.vixl per variant), `svg/` (strict), `pdf/` (RGB,
   `-cmyk` with `cmyk: true`), `png/` (`NAME-<width>w@1x|2x|3x.png`), `icons/` (favicon.ico, web manifest …),
   `social/` (avatar 800×800, og-image 1200×630), `usage.html` and `package.json`. Lockups need top-level `mark` and
   `wordmark` layers. Mono variants turn every visible colour into one ink, drop shadows/effects and silhouette
   images; `on-light`/`on-dark` fall back to the one-colour logo when the colour logo lacks 3:1 contrast. Read
   `report` and preview before handing it over. No EPS. Existing files are never replaced without `overwrite`.
14. Brand boards: `vixl_apply(workflow='brand-board', request={output, preset?, title?, document?, overwrite?})` draws the
   workspace `brand.json` (or a preset) as a guidelines document (.pdf, .pptx, .html or .vixl): cover, colour roles with
   contrast pairs, the text-stage ladder, logos with clear space and do/don't rules. `vixl brand validate` checks the
   brand first.
15. Proof pages: `vixl_apply(workflow='proof', request={items: [path | {path, label?, before?, note?}], output: "proof.html",
   decisions?, check?, title?})` writes one self-contained HTML page (no network; strict CSP). `.vixl` items show their
   `vixl_check` findings; `before` (another file, or a revision such as `previous`) adds a diff; `decisions: true` adds
   approve/reject and a button that downloads `<page>-decisions.json`, which the reviewer sends back. `vixl diff A B
   --out d.png` gives the same pixel diff on the command line.
   Many documents at once: `vixl_apply(workflow='check-all', request={documents?: [globs], group?, profile?, fail_on?, waivers?,
   changed_since?, since_last?, outputs?: {json|markdown|junit|sarif|github|proof: path}})` (CLI `vixl check --all GLOB`
   or `--group NAME`, `--profile final`) checks them in parallel (findings plus attached suites, or the profile's
   checks and suites; group consistency on a group; each document's waivers apply) into one report: `status` per
   document, `totals`, `failing` at `fail_on` (error|warning|fix|review|never; default the profile's level, else
   error) and `passed`. Every run is
   recorded in `.vixl-checks/history/`; `since_last` lists newly failing (with the cause: document or Vixl version),
   newly passing and still failing documents.
16. App animation packages: `vixl_apply(workflow='app-animation-package', request={states, default_state, output, themes?, transitions?,
   format?})`. `states` maps names to `{source: "x.vixl", loop?, interruptible?, on_complete?, poster?, variables?, themes?}`;
   `themes` map names to variable overrides (default light and dark; bind colours in the sources to `${variables}`);
   `transitions` are `{from, event, to}`; `format` is `webp` (default), `gif` or `apng`; `output` must be a new directory.
   The package holds each editable master, an animation per state and theme, reduced-motion PNGs, a versioned
   `manifest.json` and a standalone `index.html` consumer. Sources must be self-contained: freeze external links
   (`link-embed`) and embed fonts first. Missing states and ambiguous transitions fail before anything is written.
17. Screen capture: `vixl_apply(workflow='screen-capture', request={output: "shot.png", bbox?: [left, top, right, bottom], window?: HWND,
   all_screens?, overwrite?})` grabs the local desktop (a rectangle, or a Windows window handle; not both) to a PNG. It
   needs an interactive desktop and any OS permission; it is not part of rendering.
18. Source folders for Git review: CLI `vixl unpack design.vixl design-source` and `vixl pack design-source reviewed.vixl`
   (see [cli](cli.md)).
19. Delivery packages: `vixl_apply(workflow='package', request={production: "out/production.json" | files: [path | glob |
   {path, source}], output: "delivery.zip", source?, name?, brand?, layout?, check?, proof?, lock?, decisions?,
   export_settings?, dry_run?, overwrite?})` (CLI `vixl package --production out/production.json --source doc.vixl
   --out delivery.zip`) writes one zip: the completed outputs of a campaign run (or the files) named from `name`
   (`{brand}_{doc}_{artboard}_{w}x{h}.{ext}`; also `{locale}` `{row}` `{id}`; two files with one name refuse the whole
   package, so a campaign of rows needs `{row}`), identical files once, `manifest.json` (per file: source document and
   `revision`, export settings, check state, `sha256`, dimensions, colour, codec/fps/duration read from the encoded file;
   per package: `vixl_version`, `validation` coverage, `visual_review`, `held`, `reproduction`), `SHA256SUMS`,
   `report/check-report.json|md` and `proof.html`. Variants the run held (and files whose source fails its checks, or
   that the proof page's `decisions` JSON rejects) are listed under `held` and left out; nothing left is an error.
   `lock` is the source's render lockfile: its `reproduce` summary goes into the manifest. Stage with `dry_run: true`;
   an existing package is kept unless `overwrite: true`. The `outcome` stays `needs_review` until nothing is held and
   every file is validated and visually reviewed.
20. Render locks: `vixl reproduce --write-lock doc.lock.json --export png "jpg:quality=85" mp4` records every page,
   artboard and sampled frame (`--frames N`, `--times …`), the variables and seeds, and each export's bytes and decoded
   pixels with the ffmpeg version or ICC profile; `vixl reproduce --lock doc.lock.json --export` encodes them again and
   reports `byte_identical` (decides PNG, SVG, PDF, HTML, PPTX, PSD, TIFF) and `visually_equivalent` (decides JPEG, WebP,
   AVIF, GIF, MP4, WebM; `--export-tolerance`, `--export-visual`) per export, with `page 2`, `jpg.quality`, `mp4.ffmpeg`
   drift located. Workflow `reproduce` takes `exports`, `verify_exports`, `frames`, `times`, `report`. No credential
   enters a lock. Byte-exact output across machines is not promised (fonts, zlib, encoder versions).
21. Approved baselines: `vixl_apply(workflow='approve', request={group?, clear?, author?})` (CLI `vixl approve
   [--group NAME] [--clear]`) stores per page and artboard a render hash and a 256 px reference, who (`author`, else
   `VIXL_AUTHOR`, else agent) and when, in `NAME.vixl.approval/` or `.vixl-groups/GROUP.approval/` (at most 64 views).
   The `approval` check then runs with the standard checks whenever approval data exists: a changed view is a
   `warning`/`review` finding with `changed_fraction` and a `diff` image (needs_review in check-all; fails at
   `fail_on` warning or review). Approve again to accept the change; `clear` removes it. `group-apply` and
   `replace-across` dry runs and campaign `run` list `approved_members_changed`; proof pages show a badge.
22. Link impact: `vixl_apply(workflow='link-impact', request={source, documents?, group?, apply?: "if-passing",
   checks?, suites?, profile?, fail_on?, resize?, outputs?})` (CLI `vixl links impact SOURCE.vixl [--group|--glob]
   [--apply]`) finds every document that links to `source` (nested up to 4 levels, from a cached reverse index in
   `.vixl-checks/links-index.json`), refreshes its links on an unsaved copy (a resized source keeps the link's scale),
   runs check + suites and diffs the render. Report: `passes`, `fails` (failing findings and suite `rules`),
   `changed`, `tree`, `cycles`; formats as check-all. Read-only unless `apply`, which saves only passers through the
   `link-impact` journal (`group-recover`).
23. Pipelines: save `{version: 1, targets: {documents?: [globs], group?}, on_fail?: hold|stop, inputs?: [data files],
   steps: [{act|check|repair|export|export_check|approve: {...}}, ..., {proof|package: {output, ...}}]}` with
   `resource-save` kind `pipelines`, then `vixl_apply(workflow='pipeline-run', request={pipeline: NAME | {...}, run?,
   documents?, group?, dry_run?, notify?})`. The first call is a dry run (planned steps and outputs, nothing written);
   `dry_run: false` runs each document through its steps (`act`/`repair` change a working copy in `.vixl-runs/RUN/work`,
   never the source; `export` paths take `{doc}`), holds a document whose step fails (`held` with findings) and goes
   on, then writes the proof and package of what passed. Outcomes: `passed`, `held`, `visual-review-needed`, `failed`.
   The record `.vixl-runs/RUN/run.json` has input digests (document, brand.json, links (nested too), data; a check
   also keys on its suite file, library suites and `.vixl-checks.json`), per-step logs and outputs with SHA-256;
   running the same `run` again reuses every step whose inputs are unchanged. Exports never replace a file the run did
   not write for that document unless the step says `overwrite: true`, and two documents never write the same file.
   CLI: `vixl pipeline run NAME [--dry-run | --execute] [--run ID] [--glob GLOB… | --group NAME]`. Job kind `pipeline`: `submit`
   `{kind: "pipeline", output: ".vixl-runs/RUN", request: {pipeline}}`. `package` also takes `run: ".vixl-runs/RUN/run.json"`.
24. Data sync: `vixl_apply(workflow='data-sync', request={bind: {data: "prices.csv", key: "sku", to: {group} | {spec:
   "campaign.json"} | {merge: "sheets.vixl"}}, exports?, dry_run?})` diffs the CSV against the last snapshot
   (`.vixl-runs/data/NAME.json`: rows added, changed, removed) and updates only what changed rows affect: group members
   bound by their `sku` variable get the new variables on a checked copy, committed through a journal and re-exported;
   a campaign re-runs with fingerprint reuse; a merge sheet re-merges. Members that fail checks are held and retried.
25. Completion webhooks: `notify: {url, secret_env}` on `submit`, `pipeline-run` and `check-all`, or a default in
   `.vixl/notify.json` (`{url?, secret_env?, allow: [hosts]}`; only allowed hosts receive anything). One signed POST
   (`X-Vixl-Signature: sha256=…`, `X-Vixl-Delivery`) of kind, id, status, state, counts and report path, never
   document content; 3 retries; nothing offline.
26. Bulk upgrades: `vixl_apply(workflow='bulk-upgrade', request={documents | group, convert?, map?: {"Title*": {rename,
   role}}, template?, dry_run?, journal?})` converts, renames/re-roles and optionally re-applies a layout, with checks
   and a render diff before and after; dry run by default, `dry_run: false` commits through a journal
   (`group-recover` with `journal`).
27. Watch mode: `.vixl/watch.json` `{version: 1, triggers: [{on: save|source-change|brand-change|data-change|schedule,
   run?: check|check-all|link-impact|pipeline|data-sync, documents?, group?, pipeline?, binding?, every?: "24h",
   at?: "06:00" (UTC), request?: {action options}}]}`. `vixl watch` polls (1 s, content digests), debounces 500 ms,
   coalesces repeated events and runs one job per document at a time; `vixl watch --once` (or
   `vixl_apply(workflow='watch', request={ticks?, config? | watch?})`) makes one bounded pass against the state in
   `.vixl-runs/watch/` and returns `runs` (trigger, files, documents, passed, failing). Check runs record history and
   fire the completion webhook; a pipeline whose run-record digests match is skipped (`up-to-date`). The first start
   only records the files; a schedule's first period starts then.

MCP paths must remain inside the workspace. REST exposes check/act/plan/film-plan for
its single project; filesystem, library and queue operations use CLI/Python/MCP.
Checks certify only their declared rules and sampled times. Review the initial design,
material visual changes and unresolved/unsupported measurements.


### Field-report corrections

Production without suites still checks bounds and flow; clipping returns needs_review and a clean output is completed but `unvalidated`. With spec `profile` ("final"), every variant must pass that check profile (its checks, suites and fail_on), which also counts as validation. For variable reflow, define an action that reapplies the layout with replace=true and stable seed/prefix, then include it in recipe/actions. Generated layer IDs and manual edits can change. Unchanged, checksum-verified output can bypass repeated checks. See docs/guides/automation/production.md.

MCP desktop capture is disabled by default. Start the server with `--allow-screen-capture` or `VIXL_ALLOW_SCREEN_CAPTURE=1` to enable it for that server; this grants connected agents access to the interactive desktop. Capture output paths are relative to the workspace.

Campaign runs with explicit `quality: "final"` default to the final check profile. Set `profile: "draft"`
explicitly to keep draft blocking rules at full resolution; reports identify the effective profile. Held outputs are
never written: the run reports `withheld` (count, profile, fail_on, variants, top blocking `rules`) and a `message`.
Each result's `checks` is `{suites: {name: suite report}, design: report or null, placeholders: report or null}`. The `final`
profile also checks `composition` and fails on `review` findings, so a `final` campaign or `check-all` run fails on
unresolved composition findings unless they are waived with a reason or repaired (`repair-layout`).

For unsynchronized lyric text, `lyrics-align` explicitly calls a configured HTTP/command alignment provider
and saves a reviewable timing JSON. Review its warnings and per-word confidence, repair with
`lyrics-timing-edit`, and optionally write enhanced LRC with `lyrics-timing-export`. Build with `timing`
in place of `lyrics`; `animation: {in: "typewriter", unit: "word"}` uses the recorded word times.
No provider configuration or executable is accepted from a document or request. Timing edits do not
re-run inference. See the lyric-video guide's Aligned timing section and the provider setup reference.

Use lyric `compositions` rules for per-occurrence layouts: match section/occurrence/cue/contains and
cycle or seed choices among named template groups or single/stack/setup-payoff layouts. Layouts fit
phrases (`|` marks a break), use kinetic entrances, optionally attach a saved object at text ink/baseline
anchors, and add bounded part motion. `lyrics-preview` reviews one built cue. Approved per-cue field
overrides survive rebuilds with the same lyric source; rebuilds need fresh review.
