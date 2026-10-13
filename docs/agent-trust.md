# Outcomes, diagnostics and repair

How Vixl tells an agent what happened, what is wrong, how to fix it, and what it can prove. Every
surface (CLI, Python, REST, MCP) returns the same fields.

## Outcome states

A successful render or a finished job is not an approved deliverable. Results answer three separate
questions under `outcome`:

| Field | Values | Meaning |
| --- | --- | --- |
| `execution` | `completed`, `failed`, `cancelled`, `pending` | Did the work run? |
| `validation` | `passed`, `failed`, `incomplete`, `not_run` | Did the required checks pass? `incomplete`: a required rule could not be measured. `not_run`: nothing required was checked. |
| `review` | `required`, `not_required` | Does someone still need to look? `review_reasons` says why. |
| `state` | `execution_failed`, `cancelled`, `pending`, `validation_failed`, `unvalidated`, `needs_review`, `validated` | One-word summary, worst first. |
| `accepted` | list | Findings the document marked as deliberate (`layer-intent`), each with its rule, layers and reason. Acceptance covers only those findings. |
| `validated_by` | list | What validated it: `design checks`, `suite NAME`, `reference image`, `lockfile render hash`, `layout repair`, `protected edit`. |

Where it appears:

- **`vixl_check` / `vixl check` / `Project.check`**: validation fails on any `fix` finding; `review` findings
  (and unmeasured coverage) need review. A clean check is `validated`.
- **`vixl_apply` / `POST /operations`**: `completed` + `not_run` (`unvalidated`) unless `check` or
  `suites` ran; then it merges their outcomes.
- **Suites** (`vixl_apply(workflow='check')`, `act`, `group-apply`): a failed error rule fails validation, a rule that
  cannot be measured makes it `incomplete`, a failed warning rule needs review.
- **Production** (`run`): each output has its own `outcome`; with no suites a clean output is `unvalidated`
  (only bounds and flow ran). The report's `outcome` is the worst state with a count per state.
- **Jobs** (`status`): execution follows the job status; a production job's validation comes from its
  outputs. A job left `needs_review` by an uncertain remote request did not complete.
- **Exports** (`vixl_export`, `vixl_export(kind='batch')`): always `unvalidated` (exports run no checks); export
  warnings are review reasons; a batch reports each file and an overall summary.
- **Proof pages**: each checked document shows its state next to the check badge, and the result lists it.

Migration: `passed`, `errors`, `by_action`, `status` and `needs_review` are unchanged. Read `outcome.state`
when you need to know whether a deliverable meets its brief rather than whether a call succeeded.

## Actionable findings

Each design-check finding carries:

- `rule`: a stable ID, `check.code` (below), or the check name.
- `layers` (names) and `layer_ids`; `box`, the first layer's canvas box; `region` or `bounds` where the
  check measured one; `page` in a multi-page document.
- `measured`: `{actual, expected, unit}` where the rule has a measurement.
- `repair` on `fix` findings: `{kind, available, operations, reason}`. The operations are canonical, validate
  against the operation schema and can be dry-run (`vixl_apply(..., dry_run=true)`). Nothing is
  applied. `available: false` explains the next step instead.

| Rule | Measured | Suggested repair |
| --- | --- | --- |
| `bounds.text-overflow` | needed size vs text box | `fit-text` in the box, never below the minimum size |
| `bounds.cut-off` | layer box vs canvas | text: `move` back inside the canvas (relative, anchor kept) |
| `bounds.off-canvas`, `bounds.bleed`, `bounds.tile-wrap`, `bounds.gradient-edge` | layer box vs canvas | none (bleeds and wraps are informational) |
| `contrast.text-contrast` | contrast vs required | `text-set` colour moved toward the role ink (`@ink`, else black or white) |
| `contrast.unmeasurable` | | none: move the text onto the canvas, then recheck |
| `safe_area.outside` | layer box vs safe area | `move` back inside the safe area |
| `safe_area.reserved-zone` | | none |
| `overlap.text-text`, `overlap.text-object` | overlapping pixels | none mechanical; `repair-layout` tries moves |
| `overlap.decoration-text` (review) | decoration pixels inside the text's glyph area | none: move the decoration, or `layer-intent allow_overlap` |
| `blanks.unfilled` | | held for review: copy is never guessed |

The minimum size of a `fit-text` repair is the document's `text-fit` suite rule for that layer, else 12 px,
and for social and poster pieces the house style's minimum share of the short side. At most ten fix
findings get a suggestion per check. `offset` and `limit` page the findings; `passed`, the counts and
`outcome` still cover them all. Invalid operations keep their structured errors (`operation_index`, `field`,
`suggestions`).

## Visual feedback

`vixl_apply(check=..., preview={...})` takes two more preview options:

- `overlay: true` outlines each fix finding on the returned PNG, labelled `index rule · layer ID`;
  `feedback.overlay` lists the same boxes in document pixels (`region`) and preview pixels (`box`), with
  `feedback.scale`, `size`, `bytes` and `max_bytes` (512 KB by default).
- `focus: N` zooms the preview to listed finding `N` with a margin (a detail crop); without `overlay` it is a
  clean view of that spot.

`vixl_render(overlay=true)` runs `vixl_check` and returns the same boxes beside the picture. The
proof workflow takes `overlay: true` to mark the thumbnails of checked documents. Overlays are drawn on a
copy of the preview: the document and its exports never change. The change summary is the apply result's
`changes.layers`, keyed by layer ID.

## Built-in repairs

`repair: true` (or a list of kinds: `fit-text`, `contrast-ink`, `safe-area-nudge`) applies the suggested
repair for each fix finding, one candidate at a time, and keeps a repair only when its finding is gone and
no other fix finding or suite failure appeared. Unfilled blanks are held. At most ten repairs run.

- `vixl_apply(repair=true)`: after the batch; kept repairs are one more undoable history entry.
- `vixl_check(repair=true)` / `vixl check --repair` / `Project.check(repair=True)` / `Project.repair()`: the
  document is repaired and saved as one undoable step, then checked.
- `vixl_apply(workflow='act') {repair: true}`: when a suite fails, repairs the candidate (its `text-fit` and
  `contrast` rules and the bounds, contrast and safe-area findings) and commits only if every suite passes.
- `group-apply {repair: true}`: repairs each member before its suites run; each document reports `repairs`.
- Campaign `repair_actions: ["auto"]` runs the same map (named actions still work).

The report lists `applied` (rule, kind, operations, reason), `held`, `unrepaired` (with the reason) and
`remaining`, and `passed` says whether the checks now pass.

## Layout repair

`vixl_apply(workflow='repair-layout')` is a bounded search for failures with no single fix: text overflow, overlap,
spacing (suite `spacing` rules), safe area and contrast. For each failure it tries the built-in repair first,
then other candidates (a taller or wider text box, moves clear of the other layer, equal gaps), applies each
to a copy and accepts it only if the failure is gone, nothing new fails, no `protected` layer changes and no
text drops below `minimum_size`. The accepted candidate with the least disruption (movement, box and font
size change) is kept. `max_candidates` (24), `max_iterations` (4) and `time_budget` (20 s) bound it.

It is a dry run by default. It changes the document only when every targeted failure is resolved; an
infeasible request leaves the document unchanged and lists `unsatisfied` constraints. `attempts` records every
candidate with its result and reason, and the same input gives the same plan. Fix findings it does not
address (fonts, blanks) are listed under `out_of_scope`.

When `checks` include `composition` (the default set does), the [composition](guides.md#composition) review
findings are repaired after the failures, with geometric candidates of their own:

| Code | Candidates (least disruptive accepted wins) |
| --- | --- |
| `margin_drift` | snap the stray edges to the margin the most blocks share; or move the margin to the stray edge |
| `uneven_rhythm` | move the middle line to the line it belongs with (or halfway, for lines of one size); close the stack up; snap the gaps to whole spacing units |
| `crowding` | open the gap under the rule, band or heading to one spacing unit, or just past half a unit: push the text down (alone or with the rest of its column) or lift the rule (alone or with what is above it) |
| `dead_band` | between blocks: spread the band over the frame's other gaps in proportion to their size, move the blocks below up (all the way to the typical gap, or half), or move the blocks above down by half; at an edge: spread the content into the band, or centre it in its frame |
| `clumped_scatter` | a `pattern-scatter` tile is thinned in place or re-seeded from its recipe; any other scatter is listed as not auto-repairable |

A composition candidate is accepted only if its finding is gone and no finding of any check (fix or review) is new,
and while composition is checked no candidate for a failure may add a composition finding either. Moves never touch
backgrounds or art that bleeds off the canvas; a drawing made of touching shapes moves whole or not at all, and a
chip that hugs a line of text or a glow around a layer moves with it. Composition findings left over go under
`reviews_remaining` with the reason (not auto-repairable, no candidate passed, or the search stopped); they never
make a repair infeasible. A failure left unrepaired still keeps the whole plan uncommitted, composition repairs
included (`selected` lists them; fix the failure, or name `checks` without its family). Each finding tried counts
against `max_iterations`, so raise it for a page with many findings. To leave composition alone, name `checks`
without it.

On the [craft backtest](../evals/craft_backtest/README.md#repair) (`python -m evals.craft_backtest --repair`, the
default checks, up to 20 iterations), the plan resolves 19 of the 22 composition findings (17 of the 20 that catch a
defect the judges named) with no new finding of any check: every crowding and uneven-rhythm finding, 9 of 10 margin
drifts and 3 of 5 dead bands. It leaves a band beside a drawing that spans it (T02), a band in the logo sheet's dark
half (T04) and chart titles that would leave the safe area to meet the margin (T08).

```json
{"checks": ["bounds", "overlap"], "protected": ["logo"], "minimum_size": 28, "dry_run": true}
```

## Protected edits

`vixl_apply(workflow='protected-edit') {operations, protect, regions, tolerance}` applies the operations to a copy and
commits only when:

- every protected layer (and everything in a protected group) keeps all its fields (`structural`), so a
  changed word or position is caught even when it looks the same; and
- the pixels each protected layer covers fully, and each protected region (`[x, y, width, height]` in
  document pixels), change by at most `tolerance` per channel (`pixels`), which catches changes made through
  effects, parents, layers drawn on top or blending.

`guarantees` lists each check with its status and measurements (`changed_fields`, `max_delta`,
`changed_pixels`, `changed_region`). A violation leaves the document unchanged. A layer that draws no opaque
pixels is `unmeasured` and needs review, never counted as preserved. The baseline stays in memory and the
report holds no layer contents or provider settings.

## Reproduction

`vixl reproduce` (and `vixl_apply(workflow='reproduce')`) reports how far reproduction is verified:

| `reproduction` | Meaning |
| --- | --- |
| `renderable` | It renders here; nothing to compare with. |
| `environment-matched` | A lockfile was given and nothing it records drifted. |
| `reference-verified` | The render matches a reference image within `--tolerance`/`--max-fraction`, or the lockfile's exact render hash. |
| `reference-mismatch`, `drifted` | It does not; `outcome.validation` is `failed` and the CLI exits with an error. |

`--write-lock FILE` writes a lockfile: Vixl version and engine hash, Python and the imaging, shaping and
encoding packages, font and embedded-asset hashes, linked sources, the document hash, canvas settings and the
render hash. `--lock FILE` verifies it and lists each drifted item (`environment_drift`, `input_drift`).
Lockfiles hold versions and hashes only, no credentials. Byte-identical renders across machines are not
guaranteed (text rasterisation differs by platform), so compare with a reference image and a declared
tolerance where exact hashes are too strict. Remote AI inference is not replayed: generated pixels are embedded
assets and are locked like any other input.

```bash
vixl new 400x300 -o trust.vixl
vixl -p trust.vixl check --checks bounds contrast --repair
vixl -p trust.vixl export approved.png
vixl -p trust.vixl reproduce --reference approved.png --write-lock trust.lock.json
vixl -p trust.vixl reproduce --lock trust.lock.json
```

Not yet covered: export settings (colour profile, video encoder) are not part of the lockfile, and a
mismatching lock does not say which pixels moved (pass a reference image for that).

## Desktop capture permission

MCP desktop capture is disabled by default. Start the server with `--allow-screen-capture` or `VIXL_ALLOW_SCREEN_CAPTURE=1` to enable it for that server; this grants connected agents access to the interactive desktop. Capture output paths are relative to the workspace.
