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
- **`vixl_operations_apply` / `POST /operations`**: `completed` + `not_run` (`unvalidated`) unless `check` or
  `suites` ran; then it merges their outcomes.
- **Suites** (`vixl_workflow check`, `act`, `group-apply`): a failed error rule fails validation, a rule that
  cannot be measured makes it `incomplete`, a failed warning rule needs review.
- **Production** (`run`): each output has its own `outcome`; with no suites a clean output is `unvalidated`
  (only bounds and flow ran). The report's `outcome` is the worst state with a count per state.
- **Jobs** (`status`): execution follows the job status; a production job's validation comes from its
  outputs. A job left `needs_review` by an uncertain remote request did not complete.
- **Exports** (`vixl_export_file`, `vixl_export_batch`): always `unvalidated` (exports run no checks); export
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
  against the operation schema and can be dry-run (`vixl_operations_apply(..., dry_run=true)`). Nothing is
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
| `blanks.unfilled` | | held for review: copy is never guessed |

The minimum size of a `fit-text` repair is the document's `text-fit` suite rule for that layer, else 12 px,
and for social and poster pieces the house style's minimum share of the short side. At most ten fix
findings get a suggestion per check. `offset` and `limit` page the findings; `passed`, the counts and
`outcome` still cover them all. Invalid operations keep their structured errors (`operation_index`, `field`,
`suggestions`).

## Visual feedback

`vixl_operations_apply(check=..., preview={...})` takes two more preview options:

- `overlay: true` outlines each fix finding on the returned PNG, labelled `index rule · layer ID`;
  `feedback.overlay` lists the same boxes in document pixels (`region`) and preview pixels (`box`), with
  `feedback.scale`, `size`, `bytes` and `max_bytes` (512 KB by default).
- `focus: N` zooms the preview to listed finding `N` with a margin (a detail crop); without `overlay` it is a
  clean view of that spot.

`vixl_render_preview(overlay=true)` runs `vixl_check` and returns the same boxes beside the picture. The
proof workflow takes `overlay: true` to mark the thumbnails of checked documents. Overlays are drawn on a
copy of the preview: the document and its exports never change. The change summary is the apply result's
`changes.layers`, keyed by layer ID.

## Built-in repairs

`repair: true` (or a list of kinds: `fit-text`, `contrast-ink`, `safe-area-nudge`) applies the suggested
repair for each fix finding, one candidate at a time, and keeps a repair only when its finding is gone and
no other fix finding or suite failure appeared. Unfilled blanks are held. At most ten repairs run.

- `vixl_operations_apply(repair=true)`: after the batch; kept repairs are one more undoable history entry.
- `vixl_check(repair=true)` / `vixl check --repair` / `Project.check(repair=True)` / `Project.repair()`: the
  document is repaired and saved as one undoable step, then checked.
- `vixl_workflow act {repair: true}`: when a suite fails, repairs the candidate (its `text-fit` and
  `contrast` rules and the bounds, contrast and safe-area findings) and commits only if every suite passes.
- `group-apply {repair: true}`: repairs each member before its suites run; each document reports `repairs`.
- Campaign `repair_actions: ["auto"]` runs the same map (named actions still work).

The report lists `applied` (rule, kind, operations, reason), `held`, `unrepaired` (with the reason) and
`remaining`, and `passed` says whether the checks now pass.

## Layout repair

`vixl_workflow repair-layout` is a bounded search for failures with no single fix: text overflow, overlap,
spacing (suite `spacing` rules), safe area and contrast. For each failure it tries the built-in repair first,
then other candidates (a taller or wider text box, moves clear of the other layer, equal gaps), applies each
to a copy and accepts it only if the failure is gone, nothing new fails, no `protected` layer changes and no
text drops below `minimum_size`. The accepted candidate with the least disruption (movement, box and font
size change) is kept. `max_candidates` (24), `max_iterations` (4) and `time_budget` (20 s) bound it.

It is a dry run by default. It changes the document only when every targeted failure is resolved; an
infeasible request leaves the document unchanged and lists `unsatisfied` constraints. `attempts` records every
candidate with its result and reason, and the same input gives the same plan. Fix findings it does not
address (fonts, blanks) are listed under `out_of_scope`.

```json
{"checks": ["bounds", "overlap"], "protected": ["logo"], "minimum_size": 28, "dry_run": true}
```

## Protected edits

`vixl_workflow protected-edit {operations, protect, regions, tolerance}` applies the operations to a copy and
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

`vixl reproduce` (and `vixl_workflow reproduce`) reports how far reproduction is verified:

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
