# Tests, outcomes and composition checks

Why and how to test a design while building it; the loop that uses these tests is in [workflow](workflow.md).

## Tests: why, when and how

A preview is a small, downsampled picture; you cannot see a 1 px crop, a 4.2:1 contrast or gaps of 20
and 24 px in it, and the next batch can quietly undo a fix. Tests measure those exactly and keep
measuring as edits pile up. Use them for what can be measured and the preview for what cannot (taste,
likeness, mood). `vixl_reference("testing")` is the full method; every `vixl_reference(kind)` answer has a
`tests` plan (a starter suite and rules to adapt).

1. **Before building**, turn each requirement of the brief into a rule and attach the suite in the
   first batch (`suite-set`), or start from a starter suite (`vixl_apply(workflow='suite-use', request={name})`):
   `social-card`, `composition`, `slide-deck`, `logo`, `motion-loop`, `character`, `fillable-form`,
   `diagram`, `print-ready`, `accessible`, `delivery`, `palette`, `opaque`, `no-placeholders`, `containers`.
2. **While building**, pass `check=true, suites=true` to `vixl_apply`; fix failures as they appear.
3. **Before every preview and export**, run `vixl_check` and `vixl_apply(workflow='check', request={suite: NAME})`
   (or an inline suite object); preview once they pass.
4. **A failing rule means change the design.** Never loosen a rule or its tolerance to pass; pick
   tolerances when you write the rule. Use `severity: "warning"` for preferences.
5. **When they pass, start the finishing pass** (step 6 of [Start here](workflow.md#start-here-the-default-path)): composition check, a critique against
   the craft checklist, one fix batch and a real-size look at two regions. Tests catch what is wrong;
   the finishing pass catches what is merely correct.

| Requirement | Rule |
| --- | --- |
| Headline clearly dominates | `{kind: hierarchy, targets: [title, subtitle, body], ratio: 1.25}` |
| Text readable | `{kind: contrast, target: title, minimum: 4.5}`, `{kind: text-fit, target, minimum}` |
| Evenly spaced cards | `{kind: spacing, targets: [card-1, card-2, card-3], axis: horizontal}` (`expected` for an exact gap) |
| Logo 48 px from the edges | `{kind: relation, target: logo, to: canvas, position: inside, minimum: 48}` |
| Caption under the photo, left-aligned | `{kind: relation, target: caption, to: photo, position: below, align: [left], maximum: 24}` |
| Price never touches the product | `{kind: relation, target: price, to: product, position: apart, minimum: 8}` |
| Quiet area for the headline | `{kind: ink, region: [x, y, w, h], maximum: 0.02}` |
| Balanced / subject on a thirds point | `{kind: balance, tolerance: 0.1}`, `{kind: focal, target: subject, grid: thirds}` |
| Brand colour exact | `{kind: color, point: [x, y], expected: "@brand"}` or `palette` |
| Exactly three bullets, no text on an icon | `{kind: count, target: "bullet-*", minimum: 3, maximum: 3}`, `{kind: count, layer_type: text, maximum: 0}` |
| Headline ≤ 40 characters, must say "Terms apply", never "free" | `{kind: text, target: headline, max_characters: 40}`, `{kind: text, contains: "Terms apply"}`, `{kind: text, forbid: "(?i)\\bfree\\b"}` |
| At most 3 fonts, images print at 240 ppi | `{kind: budget, max_fonts: 3, min_ppi: 240}` |
| A finished part must not change | `suite-capture` (unchanged and pixels rules) |
| Holds through an animation | add `sampling: {mode: sampled, count: 8}` |
| Holds on every format | add `sampling: {artboards: "all", pages: "all"}` (results name their `variant`) |

Each result carries the measurement (gaps, margins, ratio, centre, colour), so a failure says what to
change. A rule that cannot be measured (a missing layer) is `needs_review`, never a pass; a rule about a layer
on another page is `not_applicable` on the pages that lack it (neutral, not counted). A
passing suite proves only its own rules. Rule fields: `vixl_reference('workflows').definitions.suite`.
From an approved design, `vixl_apply(workflow='suite-infer', request={name})` proposes an explained, tolerant suite to
review; library suites a group or brand.json lists under `suites` are inherited by every member, and
`vixl_apply(workflow='check', request={})` runs every attached and inherited suite.

## Read the outcome, then repair

Results carry `outcome`: `execution`, `validation` (passed, failed,
incomplete, not_run) and `review` with reasons; `state` is `validated` only when required checks ran and
passed with nothing left to review. An apply without checks, an export or a production output without suites
is `unvalidated`, not approved. Fix findings carry a stable `rule` (`bounds.text-overflow`,
`contrast.text-contrast`, `safe_area.outside` …), `layer_ids`, `measured` actual versus expected and a suggested
`repair` (operations to dry-run; nothing is applied). `repair=true` on `vixl_apply`, `vixl_check` and
workflow `act` / `group-apply` applies the built-in repair (fit-text within the minimum, ink toward `@ink`,
nudge inside the safe area; blanks are held) and keeps only repairs that leave nothing new failing.
`preview={overlay: true}` (with `check`) marks the findings on the preview; `focus: N` zooms to one. For
overflow or overlap with no single fix use workflow `repair-layout` (`protected`, `minimum_size`; dry run by
default, unchanged when infeasible); `protected-edit` commits an edit only if protected layers and regions are
unchanged; `vixl reproduce --reference PNG` or `--lock FILE` verifies an approved render.

## Composition checks

**Composition is checked by default.** `vixl_check(checks=["composition"])` (CLI `vixl check --checks composition`)
reports craft as `review` findings with a `code`: `dead_band` (an empty band much larger than the document's own
gaps), `margin_drift` (stacked blocks a few pixels off one edge or centre axis), `uneven_rhythm` (a line further
from the line it belongs with than from the next, or a small block floating midway between two others), `crowding` (a rule, band or heading under half a spacing unit
above text) and `clumped_scatter`. Each names its layers, `region`, measured `values` and `threshold`, in spacing
units of half the body size. They do not fail a plain check but fail `profile="final"`: fix them, or waive a
deliberate one with a reason (`{type: waiver, check: composition, reason}`). Marked decoration, backgrounds,
edge-to-edge gradient fills, layers under 30% opacity and bleeding art are not judged; text is measured by its glyphs. Workflow `repair-layout` repairs them after any failures, when its `checks` include
`composition` (the default set does): it snaps a drifting edge to the margin, re-spaces a stack, opens a crowded gap
to a spacing unit, spreads a dead band over the other gaps (or moves the blocks beside it) and thins or re-seeds a
clumped `pattern-scatter` tile. Each candidate is kept only if its finding is gone and no finding of any check is new,
and the least disruptive wins; drawings move whole, chips and glows move with their layer. What it cannot repair is
listed under `reviews_remaining` with the reason, and never blocks the repair of failures.
