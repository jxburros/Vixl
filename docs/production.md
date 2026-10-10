# Checked production workflows

[Documentation home](README.md) · [Getting started](getting-started.md) · [Visual gallery](gallery.md)

Vixl can save a design's requirements, turn an editable document into a typed recipe,
produce variations, reuse render work, and assemble films. These are local, headless
features: no GUI or model is needed for checks, templates, motion or rendering.

Run `python examples/build_production_demo.py --output examples/output/production`
for a complete offline example with a six-image campaign, an animated WebP, a shot
sequence and a reusable library component.

## Interfaces

Canonical operations work through `Project.apply`, `vixl apply`, REST `/operations`,
and `vixl_operations_apply`. `vixl schema` / `vixl_operation_schema` describe their fields.
New commands have document-independent `--help`.

Production workflows share one additional entry point:

```text
vixl workflow schema
vixl -p campaign.vixl workflow check --request checks.json --workspace .
vixl -p campaign.vixl workflow run --request production.json --workspace .
```

MCP: `vixl_workflow_schema()` and `vixl_workflow(action, request, document?)`.
Python: `vixl.workflows.dispatch(Session(...), action, request)` or the functions below.
Every path is relative to the session's workspace and must stay within it. The CLI
defaults the workspace to its current directory; use an explicit project path.
The fixed-project REST service exposes `GET /workflow/schema` and
`POST /workflow/check|act|plan|film-plan`. Filesystem/library/job actions require
CLI, Python or a workspace-scoped MCP session. This preserves REST's existing scope.

`vixl_compose` (CLI `vixl compose --request req.json`) builds a new document in one atomic call (create, font pairing,
layout, style, look, operations, check, preview, save, exports); see [interfaces](interfaces.md#build-a-piece-in-one-call).
To check documents in pull requests, see [CI](ci.md).

### Source folders for Git review

`vixl unpack design.vixl design-source` writes a readable, deterministic folder: `project.json`
(`format: vixl-source`, the current state and a SHA-256 per asset) plus the assets under `assets/`,
`fonts/`, `masks/`, `sources/` and `emoji-sources/`. It keeps registered fonts, drops undo history
and assets only history referenced, and refuses an existing directory. Edit and review that folder
as ordinary text, then `vixl pack design-source reviewed.vixl [--overwrite]` validates paths, sizes
and hashes, loads the result as a project and writes it with one history entry. Python:
`vixl.project_folder.pack` / `unpack`.

### Screen capture

`screen-capture` is an explicit workflow that saves the interactive local desktop to a PNG; rendering
never captures the screen. Request fields: `output` (.png), optional `bbox` `[left, top, right, bottom]`
(negative monitor coordinates allowed), or on Windows `window` (an HWND) and `all_screens`, and
`overwrite`. Headless sessions or a denied OS screen-recording permission fail with `capture_unavailable`.

```text
vixl workflow screen-capture --request '{"output":"screen.png","bbox":[0,0,800,600]}' --workspace .
```

## Design check suites

Attach a suite with an explicit `suite-set` operation:

```json
{"type":"suite-set","name":"delivery","suite":{
  "version":1,
  "rules":[
    {"id":"logo-inside","kind":"assert","expression":"layer.logo.bounds within canvas"},
    {"id":"title-fits","kind":"text-fit","target":"title","minimum":24},
    {"id":"title-color","kind":"property","target":"title","field":"color","expected":"#ffffff"}
  ]
}}
```

The tool surface describes this object, so no repository docs are needed to write one:
`vixl_operation_schema(types=["suite-set"])` and `vixl_workflow_schema().definitions.suite` give every
rule field a type, enum and one-line description (with an example), and `vixl_workflow_schema` does the
same for every action's request fields and for the `job`, `spec`, `recipe` and plugin `manifest` objects.
The `check` action also accepts an inline suite object instead of a name.

Run `project.check_suite("delivery")` or workflow `check` with
`{"suite":"delivery"}`. Results include the suite hash, actual measurements,
rule IDs, times, and `passed`, `failed`, or `needs_review`. Missing/unmeasurable
targets and warnings never count as a clean pass. Checks do not modify the document.
CLI checks and failed synchronous production return a nonzero exit code.

Rules:

| Kind | Fields and meaning |
| --- | --- |
| `palette` | `colors` or `palette`, `tolerance`, `max_fraction`, `alpha_min`, optional `region`; rendered-pixel adherence |
| `container` | optional `target`; audits template container bounds, padding, flow/grid and item limits |
| `assert` | `expression`: existing bounded assertion language |
| `design` | `options`: arguments for `Project.check`, including targets, safe area and contrast |
| `property` | `target` (or `canvas`), `field`, `expected`, optional numeric `tolerance` |
| `gap` | `before`, `after`, `axis` horizontal/vertical, `expected`, `tolerance` (default 1px); siblings only |
| `unchanged` | `target`, captured `snapshot`; preserves layer structure, not its variable-resolved pixels |
| `pixels` | `region` [x,y,w,h], embedded baseline `asset`, `tolerance` (maximum RGBA channel difference, 0–255) |
| `text-fit` | `target`, `minimum`; measures unwarped text with baked font size (a text-layout box wraps it; auto-sized text is measured as drawn, unwrapped); use `fit-text` first |
| `alpha` | `minimum`/`maximum`: permitted fraction of pixels with alpha below 255 |
| `spacing` | `targets` (2+ siblings), `axis`, optional `expected`, `tolerance` (default 1px); equal or exact gaps, as `vixl_measure_spacing` |
| `relation` | `target`, `to` (a layer or `canvas`), and any of `position` (`left-of`, `right-of`, `above`, `below`, `inside`, `contains`, `overlapping`, `apart`), `align` (edges such as `left`, `center-x`, `top`), `minimum`/`maximum` (the gap, or the smallest margin when inside), `tolerance`, `bounds` box/ink |
| `contrast` | `target`, `minimum` (default 4.5); WCAG ratio of the tenth-percentile glyph pixel against what is drawn under it (an outline style counts), as the `contrast` design check reads it |
| `color` | `point` [x,y] or `region`, `expected` colour (any Vixl colour, including `@swatch`), `tolerance` (largest RGB channel difference, default 12) |
| `ink` | `minimum`/`maximum` drawn fraction of `region` (default canvas); `tolerance` 0–255 (default 24); without `background`, the canvas colour and backdrop layers (role `background`, or a top-level full-canvas solid, gradient, image or rectangle) do not count |
| `balance` | optional `expected` [x,y] as fractions (default centre), `tolerance` (default 0.1), `region`, `background`; the ink-weighted visual centre |
| `hierarchy` | `targets` (text, most to least important), `ratio` (default 1.2); each rendered font size (after fitting) is at least `ratio` times the next |
| `count` | `target` name, glob or `group:NAME` (default `*`), optional `layer_type`, `minimum`/`maximum`; counts visible layers |
| `focal` | `target`, `grid` thirds/golden/center, `tolerance` px (default 5% of the shorter side); the layer's centre is near a power point |

Every rule has a unique `id` and optional `severity` (`error` or `warning`). Each result carries what
it measured (gaps, margins, ratios, the visual centre, the sampled colour), so a failure says what to change.

### When to test

A preview is a small downsampled picture; tests measure what it hides and keep measuring as edits accumulate.
Write the brief's requirements as a suite before building (each `vixl_guide(kind)` answer lists a starter
suite and rules to adapt under `tests`; `vixl_guide("testing")` is the method), run it with every batch
(`vixl_operations_apply(..., check=true, suites=true)`, CLI `vixl apply ops.json --check --suites`, REST
`POST /operations` with `"suites": true`), and run `vixl_check` plus the suites before every preview and
export. Fix the design when a rule fails; never loosen the rule.
`suite-capture` creates an initial structural/pixel baseline, refusing to replace one:

```json
{"type":"suite-capture","name":"protected","targets":["logo"],"regions":[[0,0,20,20]]}
```

Suites default to still-state checking. Add `sampling`:

- `{"mode":"sampled","count":8}`: evenly spaced times plus all keyframe times.
- `{"mode":"times","times":[0,"500ms","reveal"]}`: explicit times/markers.
- `{"mode":"all"}`: every frame at the document's timeline frame rate (no duplicated endpoint).

Reports disclose exact coverage. Sampling cannot prove that unsampled intervals are
correct. Production `fps` overrides are applied before checking. At most 50,000
rule/time evaluations are allowed per run. Structural checks do not judge composition,
subject identity or aesthetics; visually review the initial design and material changes.

`Project.act(operations, suites=["delivery"])` applies operations to a candidate,
runs the suites, returns checks and resulting bounds, and commits only on a clean pass.
`dry_run=True` never commits. Workflow `act` uses the same request fields.
Checked actions cannot change suite definitions. Contract changes remain explicit
`apply` operations and participate in undo/history.

## Waivers and check profiles

Some findings are deliberate: a faint watermark numeral behind a title, a title bar that runs into the safe margin.
A **waiver** accepts one on the record, with a reason and an optional expiry, instead of loosening the check or
silencing it. Every scope uses the same record, `{check or rule, reason, expires}`:

```json
[{"type": "layer-intent", "target": "ghost", "waive": [{"check": "contrast", "reason": "ghost numeral", "expires": "2030-12-31"}]},
 {"type": "waiver", "check": "contrast", "target": "tagline", "reason": "decorative watermark, approved by brand", "expires": "2030-12-31"},
 {"type": "waiver", "check": "fonts", "reason": "proofing font until the brand fonts arrive"},
 {"type": "waiver", "rule": "headline-size", "suite": "brief", "reason": "client asked for a smaller headline"}]
```

- **Layer**: `layer-intent waive` (check names or records; it replaces the layer's waivers, `[]` clears them) or
  the `waiver` operation with a `target`. It covers the layer's findings of that check and, on a group, those of
  the layers inside it. An `overlap` waiver can name its partners with `with`; `allow_overlap` and `allow_crop`
  remain the shorthand for an accepted overlap pair and a deliberate crop. `allow_low_contrast: true` on
  `layer-intent` is read as `waive: ["contrast"]`.
- **Document**: the `waiver` operation without a target covers the check everywhere in the document, or (with
  `rule`, and optionally `suite`) one suite rule. `remove: true` deletes a waiver. The operation needs a `reason`.
- **Workspace**: `waivers` in `.vixl-checks.json` (below) apply to every document; `target` names a layer.
  A project group's `shared.waivers` are written into each member (see [Studio](studio.md#shared-groups-and-concurrent-agents)).

A waived finding is never dropped. It stays in `issues` with severity `info`, action `informational` and
`waived` (scope, reason, expiry, and the severity and action it had), and the report's `waivers` lists every active
and expired waiver with the number of findings it `matched`. A waived suite result has status `waived`. A waiver
applies through the day named by `expires`. After that the finding is back with its own severity and carries
`waiver_expired`, and an expired-waiver finding (code `waiver-expired`, action `fix`) asks you to fix the finding or
renew the waiver, so `check --strict` fails until someone decides again. `check --no-waivers`
(`vixl_check(waivers=false)`) shows every finding as if nothing were waived. Proof pages list each document's
waivers and mark waived findings, and `group-show` lists the waivers of every member.

A **check profile** says how strict a run is, so the same document can be sketched and shipped under one set of
checks. Three are built in:

| Profile | `fail_on` | Adds | Suites |
| --- | --- | --- | --- |
| `draft` | `error`: only errors fail | | none |
| `review` | `fix`: any finding whose action is fix fails (the plain `check` verdict) | | all attached |
| `final` | `review`: fix and review findings fail | `color_vision` | all attached |

`check --profile final` (`vixl_check(profile="final")`, `profile` on production `run`, on `group-apply` and on the
[CI action](ci.md)) runs the profile's checks and suites; its `fail_on` decides `passed`, and the report's `profile`
names the profile, its `fail_on`, the indexes of the `failing` findings and each suite's status (a failed suite
fails every level but `never`; a suite needing review fails `warning` and `review`). `fail_on` is `error`,
`warning` (errors and warnings), `fix`, `review` or `never`. A workspace adds profiles, or overrides fields of the
built-in ones, in `.vixl-checks.json` at its root; a project group's `profiles` override both for that group:

```json
{"profiles": {"final": {"fail_on": "review", "optional": ["color_vision", "print"], "suites": "all"},
              "social": {"fail_on": "fix", "checks": ["bounds", "contrast", "safe_area", "legibility"]}},
 "waivers": [{"check": "safe_area", "target": "title-bar", "reason": "full-bleed bar by design", "expires": "2030-12-31"}]}
```

A profile has `fail_on`, `checks` (default: the standard checks), `optional` (opt-in checks added to them),
`suites` (`"all"`, `"none"` or a list of names) and `description`. The report's `outcome` follows the profile: what
its `fail_on` fails is a validation failure, other fix and review findings stay review reasons, and waived findings
are listed under `outcome.accepted`.

## Reusable actions and motion

Higher-level operations:

- `fit-text`: target, width, height, minimum/maximum font size. Wraps and fits within
  the range or fails atomically. It measures the text as it is drawn and as the bounds check
  measures it (rich spans and their own sizes, tracking, text case, leading), so a fitted layer
  passes `check`. Shared character/paragraph styles are baked locally
  so fitting one item does not resize every use of a shared style.
- `arrange-grid`: targets, columns, gap, x/y. Places unique sibling layers in cells
  sized for the largest item; it does not resize content.
- `adapt-layout` with `targets`: targets, width, height, margin/gap. Explicit vertical reflow in the
  given priority order. Refuses content that cannot fit; this is not a general constraint solver.
  Without `targets` the same verb re-lays out every layer proportionally at another size and reports
  where each layer moved (see [operations](operations.md#bulk-edits-and-resizing-a-whole-layout-019)).
  `recompose: true` instead re-applies the document's saved `layout-apply` recipe at the new size,
  replacing the generated layers (and manual edits to them); it fails when there is no saved recipe.
- Existing `replace-contents` preserves a frame's placement, effects and identity.

An `action-define` stores bounded canonical operations under a name; `action-apply`
executes them as one edit. Actions cannot access host files, recursively invoke actions
or templates, or change suites/definitions. They may use the high-level operations above.

```json
{"type":"action-define","name":"fit-headline","action":{"operations":[
  {"type":"fit-text","target":"title","width":600,"height":140,"minimum":24,"maximum":72}
]}}
```

Motion recipes bind reusable sequences to semantic roles. Roles retain stable layer IDs:

```json
{"operations":[
  {"type":"role-set","name":"cards","targets":["card-1","card-2","card-3"]},
  {"type":"motion-define","name":"reveal","motion":{"steps":[
    {"id":"enter","role":"cards","preset":"fade-in","duration":"400ms","stagger":"100ms"},
    {"role":"cards","property":"translate-y","from":0,"to":-10,"after":"enter","duration":"200ms"}
  ]}},
  {"type":"motion-apply","name":"reveal","speed":1.5,"start":"500ms"}
]}
```

Steps support preset or property animation, start, duration, easing, amount/distance,
stagger, and `after` an earlier step ID. Speed scales all recipe durations and offsets;
`roles` on motion-apply overrides bindings. Missing roles and invalid dependencies fail
atomically. Output is ordinary editable timeline tracks. Nested motion compositions
and automatic character rigging are not supplied.

## Typed templates and document recipes

Existing JSON templates remain compatible. They can additionally carry `inputs`,
`roles`, `suites`, `actions`, `motions`, and `recipe` metadata. Supply representative
`defaults` for operation validation. Input types: string, color, embedded asset ID,
number, integer, boolean; optional enum, minimum, maximum, maxLength and default.
Unknown inputs fail. Template metadata is attached using the same canonical operations.

A portable document recipe preserves embedded assets, fonts, layers and motion.
Use workflow `capture`:

```json
{
  "output":"card-recipe.vixl",
  "recipe":{"version":1,"inputs":{
    "title":{"type":"string","default":"New release","maxLength":100}
  },"actions":["fit-headline"],"examples":[{"title":"A much longer headline"}]},
  "bindings":{"title":{"target":"title","field":"text"}}
}
```

Bindings support existing text/color fields. Set up image slots with the existing
`replace-contents` variable binding. Capture needs defaults for required inputs and
checks every example against all attached suites before saving. It does not infer
which fields should vary: the agent explicitly supplies that intent.

Python: `capture_recipe(project, recipe, bindings)` returns a new Project;
`instantiate(project, values)` creates a variant without modifying the original.

## Variant production and draft/final

Workflow `plan` takes `{"spec": ...}` and returns the complete output count and matrix
before any rendering. `run` adds `"output":"campaign"`:

```json
{"output":"campaign","spec":{
  "version":1,
  "rows":[{"title":"First release"},{"title":"Second release"}],
  "matrix":{"accent":["#ff8800","#00aacc"]},
  "artboards":["square","story"],
  "quality":"final","format":"png","workers":2,
  "suites":["delivery"],"repair_actions":["fit-headline"]
}}
```

Rows can be assembled from a CSV by a caller; existing `render --data` remains available.
There are at most 10,000 outputs, ten variation axes and four concurrent workers.
Row fields cannot also occur in the matrix. Explicit row values override artboard defaults.
All attached suites run unless an explicit `suites` list selects others. With `profile` (for example `"final"`),
every variant must also pass that [check profile](#waivers-and-check-profiles): it picks the design checks, the
suites (unless `suites` is given) and `fail_on`, and `production.json` names it. Without a profile, `quality` does
not change which checks run.

Optional `actions` run before checks; `motion` applies a saved sequence.
At most three named `repair_actions` are tried in order, stopping when checks pass. The name `auto` runs the
built-in repair map instead (fit-text, contrast ink, safe-area nudge; see
[outcomes, diagnostics and repair](agent-trust.md#built-in-repairs)); its operations are reported under
`repair_operations`.
Failed/unmeasurable outputs are held for review; successful outputs remain available.

Image formats: PNG, JPG, WebP, SVG. For animation use `kind:"timeline"` with
GIF, WebP, MP4, WebM or ZIP; optional `fps` overrides timeline settings.
Draft stills use a 640px proxy. Draft timelines use half-size proxy frames and default
to 12fps. Final output retains document resolution and frame rate. Checks measure the
source design, not a downscaled draft. Proxy-unsupported effects fall back to a full
render. Draft/final rendering never regenerates AI assets.

`production.json` records each output's input/render fingerprint, checksum, checks,
repairs and status. Run again in the same directory to reuse verified unchanged results
and retry incomplete ones. Changed variants get new fingerprinted filenames; existing
unrelated files are never overwritten. A contact sheet includes up to 100 raster outputs.
Keep output order stable when resuming: variant IDs derive from row/matrix/board order.
Completed files are published atomically; a crash before recording completion can require
rerendering that one variant. Old output versions are retained.

## Print merge

`merge-impose` merges a template and a CSV into print sheets (n-up, crop marks, bleed) with vector text, validating every row
first; see [imposition](imposition.md). Variant production fingerprints include the revisions of any documents a design
[links](linked-documents.md), so a changed source re-renders the variants that use it.

## Proof pages

`proof` writes one HTML page for reviewing a set of documents and exports, for a client, a teammate or a pull
request:

```json
{"items": ["poster.vixl", {"path": "out/poster.png", "before": "out/poster-v1.png", "note": "Brighter headline"},
           {"path": "poster.vixl", "label": "Since last round", "before": "round-1"}],
 "output": "review/round-2.html", "title": "Poster, round 2", "decisions": true}
```

```text
vixl workflow proof --request proof.json --workspace .
```

Each item gets a thumbnail (click it to enlarge), its format, byte size, pixel size, colour mode (PNG/JPEG/TIFF
mode, ICC profile, the PDF colour spaces it uses, a document's canvas and dpi) and, for `.vixl` documents, the
`vixl_check` findings (`check: false` skips them), with waived findings marked and the document's
[waivers](#waivers-and-check-profiles) listed with their reasons and expiry dates. `before` adds a before/after pair with the changed share: it is
another file, or a revision of a `.vixl` item (`previous`, `head~2`, a checkpoint or branch). Items are paths or
`{path, label?, before?, note?}`; up to 200.

The page is a single file that works offline: every image is a data URI, and its Content-Security-Policy allows only
those images, inline styles and, with `decisions: true`, the one inline script it names by hash. That script adds
approve/reject and a note per item and a **Download decisions (JSON)** button: a static page cannot write files, so
it downloads `<page>-decisions.json` (`{proof, page, generated, decided, items: [{id, path, label, decision, note}]}`)
for the reviewer to send back. Without `decisions` the page has no script at all. An existing page is replaced only
with `overwrite: true`.

A missing file fails the call, but an item that cannot be previewed or checked becomes a card with its error and
is listed in the result's `failed` (`[{path, error}]`); `checked` gives each document's `passed`, errors and
warnings. Each thumbnail is embedded once and reused by the enlarged view (`max_size`, 128–2400 px, default 1200).

## Checking many documents

`check-all` checks a set of documents in one call and returns one report; `vixl check --all` is the same on the
command line, and the [GitHub Action](ci.md) runs it.

```bash
vixl check --all "designs/**/*.vixl" --fail-on warning
vixl check --all "designs/**/*.vixl" --profile final
vixl check --group launch --since-last
vixl check --all --changed-since origin/main --format sarif --write junit=out/junit.xml
```

```json
{"documents": ["designs/**/*.vixl"], "fail_on": "error", "workers": 4, "since_last": true,
 "outputs": {"markdown": "out/checks.md", "sarif": "out/vixl.sarif", "proof": "out/checks.html"}}
```

Documents come from `documents` (globs or paths, default `**/*.vixl`; `.vixl-*` folders are skipped), a project
`group`, or both; `changed_since` keeps only those changed (committed, staged, unstaged or untracked) since a git
revision. Each document gets the `vixl_check` findings (`checks` to choose) plus its attached suites (`suites: false`
skips them) and an optional inline `suite` (an object, or a `.json` file), in `workers` parallel threads (1–8). On a
group the [group consistency checks](studio.md#group-consistency-checks) run as well (`group_checks`).

The result has, per document, `status` (`passed`, `failed` for errors or a failed suite, `needs_review` for warnings,
`fix` findings or a suite that needs review, `error` when it could not be checked), counts (`errors`, `warnings`,
`fix`, `by_check`), the top ten `findings`, suite rule results and `failing`: the findings that reach `fail_on`.
`fail_on` is the CI action's level: `error`, `warning` (or error), `fix` (any finding whose action is `fix`),
`review` (fix or review findings) or `never`; a suite that does not pass counts at every level but `never`. With
`profile` (`--profile`) every document is checked under that [check profile](#waivers-and-check-profiles) (its
checks and suites; a group's `profiles` apply to its members), `fail_on` defaults to the profile's own level, and the
report names the `profile`. Each document's waivers apply (`waivers: false`, `--no-waivers`, ignores them): waived
findings stay in `findings` as informational with `waived`, never reach a level, and each document lists its
`waivers`, which the Markdown summary repeats. `totals` sums them and `passed` is false when
any document (or group finding) reaches the level, which is also the command's exit code. `base` pixel-diffs each
document against its version at a git revision (`diff.changed_fraction`, or `new`), keeping base copies and diff
images in `work`.

`outputs` writes the report as `json`, `markdown` (the CI summary table), `junit` (one testsuite per document, one
testcase per check and suite rule, failures carry the messages), `sarif` (SARIF 2.1.0: one result per finding with
the check or `suite/NAME/RULE` as `ruleId`, the severity as level, the `.vixl` path as location and the layers as
logical locations), `github` (workflow annotation lines: `::error file=…,title=Vixl contrast::…`) and `proof` (a
[proof page](#proof-pages)). Existing files are kept unless `overwrite: true`. On the command line `--format` prints
one of them (markdown by default, json with `--json`) and `--write FORMAT=PATH` writes others.

### History and newly failing documents

Every run records a history entry in `.vixl-checks/history/` (the Vixl version, each document's status, checksum
and finding IDs; the last 200 entries are kept; `history: false` skips it). `since_last` compares the run with the
previous one over the same documents and settings:

- `newly_failing`: documents that reached `fail_on` now but not before, each with `new_findings` and a `cause`:
  `document` when the file changed, `vixl version` when only Vixl changed (`version_changed`), else `unknown`;
- `newly_passing`, `still_failing`, and documents `added` or `removed` since then.

After an upgrade, `vixl check --all --since-last` therefore names the documents that the new version judges
differently. Vixl does not schedule runs itself: run it from CI on a schedule (a cron workflow), or after an update.

## Logo packages

`logo-package` turns one logo into the folder a brand hand-off needs:

```json
{"output": "brand/acme", "mark": "symbol", "wordmark": "name", "png_sizes": [256, 512], "cmyk": true, "zip": true}
```

| Input | Meaning |
| --- | --- |
| `source` | The logo: the open document (default), a `.vixl`, a PNG/JPEG/WEBP (placed as an image) or an SVG (imported). `trace: true` traces a raster with the drawing `vectorize` action (outline mode, one colour) so SVG and the mono variants are vector |
| `variants` | Any of `full-color`, `mono-black`, `mono-white`, `on-light`, `on-dark` (default all). `light`/`dark` set the backgrounds (`#ffffff`, `#111111`) |
| `mark`, `wordmark` | Top-level layers (names or IDs). Together they build the `mark`, `horizontal` and `stacked` lockups (`lockups` picks some) with `clear_space` (default 0.25 of the mark's height) around and between the parts. Without them the whole logo is one `logo` lockup, trimmed to its content plus clear space |
| `png_sizes` | Base widths; each is written at 1x, 2x and 3x (`png/NAME-512w@2x.png`) |
| `cmyk` | Also `pdf/NAME-cmyk.pdf` |
| `icons` | `web` (default: favicon.ico, PNG favicons, Apple touch icon, Android icons, web manifest), `apple`, `android`, `windows`, `all` or `false`; built from the mark |
| `social` | `social/avatar.png` (800×800) and `social/og-image.png` (1200×630) on the light background (default true) |
| `proof`, `zip` | `usage.html`, the usage sheet (a proof page with a usage note per variant; default true); `zip: true` writes `<output>.zip` (or give a path) |

The folder holds `source/` (an editable `.vixl` per lockup and variant), `svg/` (strict SVG: a variant with raster
content is skipped and listed under `report.skipped`), `pdf/`, `png/`, `icons/`, `social/`, `usage.html` and
`package.json` (the file list, settings and report). Files go through the same export path as `vixl_export_batch`.
Nothing is overwritten unless `overwrite: true`, and a failure removes the files the call wrote.

Recolouring is a heuristic, and `report.variants` says what it did per variant: mono variants turn every visible
fill, stroke, text and gradient colour into one ink, drop shadows, glows and effects, and make images a silhouette
of their alpha (an opaque image first loses the background colour found in its corners). Detail separated only by
colour merges, so review the mono variants. `on-light` and `on-dark` keep the colour logo when its average colour
has at least 3:1 contrast with the background and otherwise use the one-colour logo (`reversed` explains it).

There is no EPS output: EPS cannot carry transparency and most tools that once needed it accept PDF or SVG. Hand
over the PDF (print) or SVG (web, sign makers).

## Brand boards

`brand-board` draws the workspace `brand.json` (or one of its presets) as a guidelines document: cover, colour
roles with contrast pairs, the text-stage ladder, logos with their clear space, and do/don't rules. It writes a
`.pdf`, `.pptx` or `.html` (and the editable `.vixl` with `document`). See [brands](brands.md#brand-board).

## Persistent rendering cache and library

Production variants, timeline exports, contact sheets and `vixl export`/`vixl render` of a saved document use a
bounded persistent PNG cache in the per-user cache directory (`~/.cache/vixl/render`, or `VIXL_RENDER_CACHE`),
so output folders stay clean and a second export of an unchanged document reads its frame back instead of
drawing it. `VIXL_RENDER_CACHE=off` turns the disk cache off; `VIXL_CACHE_MAX_MB` sets its size cap (default
256; the least recently used PNGs go first). `vixl cache info` reports the directory, entries, bytes and cap,
and `vixl cache clear` empties it.
Workflow `preview` and film document shots cache in the workspace's `.vixl-cache`. Direct Python callers may use
`vixl.render_cache.enable(project, directory)`. Within a session, rendered layers (and composited groups, keyed
on their whole subtree) are also kept in a bounded in-memory cache keyed by content and size, so a layer that
only moves between timeline frames is not redrawn; the MCP and REST servers keep a document's caches when they
reload it after it changed on disk.
Keys include render dependencies, font bytes, engine source/version and imaging library
versions. Unchanged layers and sampled frames can survive across sessions. Cache corruption
or an unavailable cache falls back to rendering.

Sequences (timeline exports, contact sheets and film shots) store a whole frame only the second time it is
requested, in that export or an earlier one (a small ledger beside the cache remembers recent frames): a film
whose motion never stops draws each frame once and would otherwise fill the cache with one-use PNGs, while held
frames and re-exports of unchanged stretches are still kept. Layers are always stored, so a static grain
background or header is drawn once per export. A frame of a timeline shares every layer it does not animate
with the document, and top-level groups that draw nothing at that time (hidden or at zero opacity, such as the
inactive cues of a lyric film) are left out of it unless another layer or the document refers to them; the
pixels are the same either way. `VIXL_PROFILE=1` reports the cache's hits, misses, writes, skipped frame
writes and evictions (see [troubleshooting](troubleshooting.md#find-out-why-a-render-is-slow)).
Linked files and plugin effects bypass persistent caching; dependent groups are cached
at whole-frame level rather than incorrectly treating a group as an independent leaf.
There is no dirty-region compositor or GPU renderer.

Workflow `preview` takes `output` (.png), `quality` (draft/final) and optional `time`.

Library actions take a workspace-relative `directory`:

- `library-save`: name, description, tags. Saves a versioned, self-contained `.vixl` component.
- `library-search`: query. Matches all terms across name, description and tags.
- `library-open`: id, output. Opens an editable copy with its embedded assets and recipes.
- `library-place`: id, name. Inserts the rendered component as an embedded raster layer.

The original library document remains editable. In-place placement is a raster snapshot,
not a live cross-document symbol. Components may hold isolated characters, masks, palettes,
timelines and backgrounds. Search uses explicit metadata, not an embedding service.

## Durable jobs

Workflow `submit` accepts:

```json
{"start":true,"workers":2,"job":{
  "kind":"production","source":"card-recipe.vixl","output":"campaign",
  "spec":{"rows":[{"title":"First release"}],"quality":"final"}
}}
```

`source` defaults to the active document for production/image generation. Jobs snapshot
their source before returning. Film jobs snapshot shot/audio files too. Job records and
inputs live in `.vixl-jobs`; submitted resource limits survive background execution.

`status`, `cancel`, `resume` take `{"id":"..."}`. `work` processes ready jobs once;
`start` launches a hidden worker until the queue is idle. Both accept workers 1–4.
For an external service supervisor: `vixl workflow worker --workspace . --workers 2`.
Per-job locks prevent two workers executing the same job. After a process crash, start
a worker again. Local production resumes. Cancellation is cooperative between outputs/
frames and does not claim to cancel external inference. Encoding/audio mixing may finish
their current bounded operation before cancellation is observed.

Job kinds:

- `production`: source, spec, output directory.
- `film`: spec, output ZIP/MP4/WebM.
- `generate`: source, explicit provider, request (prompt, width, height, optional model,
  negative_prompt, seed, strength and generate mode), output `.vixl`.
- `video`: explicit provider, request, output MP4/WebM (gateway contract below).

An interrupted synchronous image request becomes `needs_review` and is never blindly
repeated. Pollable video jobs keep their remote ID. Network failures back off; after
60 worker attempts they need review. Resume preserves remote identity. Background workers
are not an OS service and do not auto-start after a machine reboot.

## Films: scenes, shots, captions and sound

Workflow `film-plan` takes `{"spec": ...}`; `film-export` also takes `output`.

```json
{"output":"promo.mp4","spec":{
  "version":1,"width":1280,"height":720,"fps":24,
  "shots":[
    {"source":"intro.vixl","duration":2000,"camera":{"from":[0.5,0.5,1],"to":[0.5,0.5,1.15]}},
    {"source":"product.png","duration":2000,"transition":400},
    {"source":"generated-shot.mp4","duration":3000,"trim":500,"transition":400}
  ],
  "captions":[{"text":"Available now","start":3000,"end":5000,"x":60,"y":600,"size":48}],
  "audio":[{"source":"music.wav","start":0,"trim":0,"volume":0.6}]
}}
```

Times are milliseconds. Shots accept still images, `.vixl` timelines and MP4/WebM/MOV
clips. `.vixl` shots also accept variables/artboard. Sources are fitted to the output;
still/document aspect mismatches use a centered crop, video clips are letterboxed.
Camera poses are normalized center-x/center-y plus zoom (1–16); motion interpolates
linearly. A zoomed shot stays sharp: its source is drawn up to its closest zoom times larger
(`.vixl` documents re-render at that scale, images and clips are fitted from their full
resolution), at most 4x and within the pixel budget, and the camera window is cut from
that. `transition` is incoming crossfade duration (0–2000ms). Transitions overlap
shot durations and cannot create a three-shot overlap. Captions use global film time.
Clip audio is not implicitly retained: add explicit audio tracks to control the mix.
The mix is written at the highest source sample rate (up to 48 kHz; 48 kHz for synthesized
tracks), mono when every source is mono and unpanned; `sample_rate` (Hz) on the spec chooses
another. The result reports `sample_rate` and `channels`.

Limits: 100 shots, 1,000 captions, eight audio tracks, 3,600 frames, ten minutes, 60fps.
MP4/WebM, clip decoding and audio mixing require ffmpeg on PATH. ZIP exports stream PNG
frames plus timing.json and do not support audio. Draft films cap dimensions at 640px;
set their fps explicitly. Output is staged and published only after completion.

## Generated-video gateway

Video uses an opt-in HTTP gateway configured locally with `type:"http"` and
`capabilities:["video"]`, plus URL and optional `key_env`. It is a documented integration
contract, not a claim that every existing image adapter implements native video APIs.
Only environment-variable references are stored in provider configuration; credentials
are never copied into job payloads. No redirects or arbitrary output URL downloads.

1. POST `/video/jobs` with `client_id` (persistent Vixl job ID), prompt, width, height,
   duration **in seconds**, optional model and base64 source_image. The gateway must
   make repeated client_id submissions idempotent.
2. Response: `{"id":"remote-id","status":"queued"}` (or running/completed/failed).
3. GET `/video/jobs/{id}` polls the same job. GET `/video/jobs/by-key/{client_id}` recovers
   uncertain initial submission without starting another generation.
4. Completion adds `format:"mp4"|"webm"` and `video_base64`, bounded by asset limits and
   checked for matching container type. Failure is explicit; no placeholder media.

The Vixl video job request uses `source_asset` with an optional source `.vixl` document
for image-to-video conditioning. Remote cancellation is not part of this contract.
Tests use a fake gateway; live inference needs a configured service and is not exercised
by the offline suite. Providers can vary in timing, output quality and consistency.

See [the studio guide](studio.md) for starter suites, saved effects, modular containers, project groups, plugins and agent branch/merge actions.

## Reflowing variable copy during production

Changing variables updates text and width-only wrapping boxes. It does not rerun an entire layout automatically. For a template whose neighbouring layers must move, define an action containing `layout-apply` with `replace: true`, the same layout name, prefix, seed and `${variable}` copy slots. Name that action in the recipe's `actions` array or the production request's `actions` array. Production substitutes each row's variables before running the action, so layout measurement sees the actual copy. Prefer width-only text boxes when just the paragraph height should grow. An explicitly fixed height remains a constraint and may produce overflow.

Recomposition replaces the layout-generated layers. Manual edits, layer IDs used by external bindings, custom animation tracks and adjustments to those generated layers may not survive. Store such content outside the generated prefix or rebuild it in the action. Check the longest row and every target size.

Without named suites, production runs bounds and text-flow checks and returns `needs_review` for failures rather than publishing clipped text; a clean output is `completed` with `outcome.state` `unvalidated`, because no suite validated it. Each result and the report carry an `outcome` ([outcome states](agent-trust.md#outcome-states)). Add suites for the rest of the design contract. Unchanged runs reuse an output only when inputs, fonts, linked sources, settings and checks match and the output's SHA-256 still agrees. Layer caches use the user cache directory, not the deliverables directory.

The `app-animation-package` workflow packages named source documents, theme variables, explicit transitions, one-shot/looping behavior, reduced-motion PNGs and editable masters. Its generated manifest and standalone consumer are documented in [animation authoring](animation-authoring.md#app-animation-packages). Package outputs are new directories and external links must be frozen first.

Contrast checks reuse exact byte-channel transfer values rather than recalculating the sRGB power function for every pixel. The poster performance regression exercises the complete design check; expensive effects and complex documents can still cost more.
