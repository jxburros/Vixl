# Craft plan

> **Archived 2026-10-31.** This plan is kept as history and is no longer maintained. The current plan is [ROADMAP.md](../../../ROADMAP.md) at the repository root.


[Documentation home](../../README.md) · [Development plan](roadmap.md) · [House style decisions](../house-style.md)

This plan is about the quality of what agents make with Vixl: whether a finished piece reads as designed, not just
correct. It comes from the [blind re-judging of the tool comparison](https://github.com/jxburros/VixlExamples/blob/main/eval-results/2026-10-13-blind-rejudging.md)
and uses the same complexity (C1–C5) and payoff (P1–P5) ratings as the [development plan](roadmap.md).

## Where craft stands

The re-judging scored every lane blind with three judges plus a human calibration set.

- **On scores alone, Vixl's craft is level with web code**: mean craft 3.81 against 3.78. The earlier gap was mostly
  web-code scores that had never been re-judged.
- **Side by side, judges still prefer web code.** Asked which they would publish, they picked web code over Vixl in
  16 of 27 calls, and web code won 6 of the 9 tests the two lanes share. Most margins were slight. The human
  calibration made the same picks.
- **Vixl's lowest craft sub-scores are motif (3.67) and spacing (3.78).** Hierarchy, type, color and finish are 4.1
  to 4.4.
- **Correctness is not the problem.** Vixl passes 92 of 96 hard checks, and every report is honest.

The judges' reasons for picking another lane over Vixl fall into four groups, in this order of frequency:

| Cause | Tests | What the judges saw |
| --- | --- | --- |
| Spacing, rhythm and alignment | T02, T07, T08, T15, T16 | A loose lower half; uneven gaps in a name block; two left margins; a dead band; a crowded donut label; rules pressed onto the first row; a ragged price column; lumpy pattern spread |
| Flat scenes and generic motifs | T03, T12 | Dash reflections, a placeholder skyline, thin line waves, a banded beam, a plain disc standing in for a lamp |
| Tool finish | T10, T11, T13, T15 | Grain left in a crop; fill halos and blobs at line joins; a flat sprite silhouette; a scatter that re-rolls on any count change |
| Data presentation | T08, T16 | Names, numbers and percentages not paired in one list; prices not right-aligned |

## Why it happens

This is the state before 0.27.0; the [Status](#status) table below records what has landed since.

- **The agent loop ends when the checks pass.** SKILL.md step 5 and `briefs.START_HERE` go from passing checks to a
  preview to export. No step asks for a critique or a polish pass, and the "Finish" step means "apply a look".
- **The checks don't see composition.** The default `vixl_check` families cover bounds, overlap, contrast, safe area,
  legibility and fit. Nothing flags dead bands, inconsistent margins, uneven rhythm or crowding unless the agent
  writes its own suite rules. The style rules that come close (`rule_margins`, `rule_edge_alignment`,
  negative-space rules) only run on a style-tagged document.
- **Detail costs a tool call each.** Web code gets a pill, a rule with a label or an accent word from one line of
  CSS. In Vixl each is an operation whose schema the agent has to recall, so effort goes to correctness first. Vixl's
  median round-1 run took 31.5 calls against web code's 15.
- **Some primitives are missing:**
  - balanced line wrapping and runt control for single text layers;
  - tab stops and dot leaders;
  - reflection, haze, star-field and bokeh effects;
  - a key–value list component;
  - thinning a scatter in place.
- **Nothing measures craft between releases.** The agent evals grade function, and the house-style eval scores
  diversity and fix-free quality. A craft regression is invisible until the next full tool comparison.

## Goals

Measured by re-running the Vixl lane of the tool comparison and judging it blind against the same web-code runs,
with the [re-judging kit](https://github.com/jxburros/VixlExamples/blob/main/evals/tool-comparison/rejudge-2026-10-12/README.md):

- **Primary:** Vixl wins at least half of the "which would you publish?" calls against web code (today 11 of 27).
- **Supporting:**
  - Vixl's mean spacing sub-score is at least 4.2 (today 3.78) and its motif sub-score at least 4.0 (today 3.67).
  - Mean craft is at least 4.0 (today 3.81).
  - Hard checks stay at 92 of 96 or better, and median round-1 tool calls stay at or below 31.5.

## Workstreams

In order. Each item names the evidence it answers.

### 1. Measure craft (first, because everything else is judged by it)

| Item | What | C | P |
| --- | --- | --- | --- |
| 1a | **Keep the eval sources.** Commit the Vixl lane's `.vixl` documents for tool-comparison runs (VixlExamples, where the kit lives, does not ignore `*.vixl`, so the re-run in 1c only has to keep them). Without them, editability can only be judged from output diffs, and the new checks below can't be backtested | 1 | 4 |
| 1b | **Backtest set.** The 16 round-1 Vixl documents, each with the defects the judges named (from `rejudge-2026-10-12/scores/`) as expected findings. Every new check in workstream 2 reports how many of those it catches and how many false findings it adds | 2 | 5 |
| 1c | **Craft re-run as a routine.** A script that re-runs the Vixl lane on the 16 briefs, packages it with `rejudge.py` beside the fixed other-lane runs, and prints the judge prompt, so a release can be judged in an afternoon | 2 | 4 |
| 1d | **Craft in the agent evals.** Add the new composition findings (2a) to `evals/house_style.py`'s quality score, so `--compare` against the baseline catches craft regressions on every default change | 2 | 4 |

### 2. Composition checks and repair (the largest cause)

| Item | What | C | P |
| --- | --- | --- | --- |
| 2a | **A `composition` check family, on by default as review findings:** <br>• dead bands: an empty band over a set share of the canvas between content blocks or between content and an edge, from `spatial` `free` rectangles (T02, T03, T08, T12); <br>• margin drift: text blocks whose left (or right) edges are within one spacing unit of each other but not equal, which generalizes `rule_edge_alignment` without a style tag (T08); <br>• uneven rhythm: stacked siblings whose gaps differ by more than the spacing scale allows (T07, T08); <br>• crowding: a rule, band or heading closer to its next block than half a spacing unit (T16); <br>• clumped scatter: cell variance of a scatter above a threshold (T15) | 3 | 5 |
| 2b | **`repair-layout` for composition findings:** snap drifting edges to the dominant one, re-space a stack to the spacing scale, and redistribute a dead band by moving the lower block or growing the gap between groups. It ranks candidates by least disruption, as it does now | 4 | 5 |
| 2c | **`profile="final"` includes `composition`**, so shipping fails on unresolved composition reviews unless they are waived with a reason | 1 | 4 |

### 3. A finishing pass in the agent loop

| Item | What | C | P |
| --- | --- | --- | --- |
| 3a | **Rewrite the end of the loop** in SKILL.md, `briefs.START_HERE` and the guidance registry: checks pass → `check composition` → a short critique against a craft checklist → one fix batch → a real-size look at two regions with `vixl_render` `region` → export. The checklist lives once in `guidance.py` (`vixl guide finishing`) | 2 | 5 |
| 3b | **Make the critique cheap:** `vixl_apply` with `check=true` already returns findings and a preview, so return the composition findings with it, plus the two lowest-scoring regions as crops | 2 | 4 |

### 4. Typography

| Item | What | C | P |
| --- | --- | --- | --- |
| 4a | **Balanced wrap** (`wrap: "balance"`) for headings and short text, and a runt rule (no one-word last line) for body text on single layers. Default for headings in the house style, following the #430 policy (T09 story breaks, T14 "waves break / stone / alone") | 3 | 4 |
| 4b | **Tab stops and dot leaders** (BLK-07): tab stops on text and a `leader` option on table columns, so menus and price lists stop drawing leaders by hand (T16) | 3 | 3 |
| 4c | **Accent words in layouts:** a headline slot takes `accent: ["Winter"]` and styles the match with the accent swatch through the existing span styling (the two-tone headlines that won T09 and T03) | 2 | 3 |

### 5. Components

| Item | What | C | P |
| --- | --- | --- | --- |
| 5a | **`key-value-list`** in the container library: label, value and optional share in aligned columns with rules between rows. Charts use it for `legend_values` and summaries (T08) | 2 | 4 |
| 5b | **Section-header spacing:** the eyebrow + title + rule container and the layouts' rule accents get a minimum clearance before the first row (T16 crowding) | 1 | 3 |
| 5c | **Pills and highlighted words as layout defaults** where a layout has a call to action or a date line, chosen by the rolled direction (T02, T09) | 2 | 3 |

### 6. Motif and atmosphere

| Item | What | C | P |
| --- | --- | --- | --- |
| 6a | **Scene effects as single operations:** <br>• `reflection`: mirror, ripple and fade below a horizon (T03); <br>• `haze`: a soft glow band behind a light source; <br>• `star-field`: seeded particles that keep clear of text; <br>• `string-lights`: bulbs repeated along a path with glow (T02, T03); <br>• `bokeh` | 3 each | 4 |
| 6b | **Specific motifs from the brief:** `vixl_reference` names the concrete elements a brief implies (a cup with steam, not a disc; a lighthouse in the sea, not on a bar) and the shape catalog or object kinds that draw them. Ties to #427 illustration defaults and the object work (#374–#381) | 3 | 4 |
| 6c | **Filled layered water** as a scene preset, because line waves read as unfinished next to filled bands (T09, T12) | 2 | 3 |

### 7. Tool finish

| Item | What | C | P |
| --- | --- | --- | --- |
| 7a | **`pattern-scatter` thins in place:** with the same seed, a lower `count` removes points rather than re-rolling them, and an explicit `thin` keeps the survivors. Round 2 of T15 kept 87 % of the pattern on 0.20.0 and 7 % on 0.26.0 | 2 | 4 |
| 7b | **Drawing fills register to their lines:** grow fills under strokes so no halo shows, and let `edge_closes` split regions whose dividing line stops short of the edge (T11). Part of #218 | 3 | 3 |
| 7c | **Crops take the cleaned master:** derived crops (Instagram, caption) are cut from the denoised and corrected layer, not re-processed separately (T10 grain) | 2 | 3 |
| 7d | **New charts respect the safe area:** a new chart starts inside the safe area with padding from the spacing scale, so it doesn't fail `vixl_check` on creation | 1 | 3 |
| 7e | **Sprite silhouettes:** pixel characters get a shading ramp and an outline pass by default (T13) | 2 | 2 |

## Order

This was the planned order; every item has landed in 0.27.0 (see [Status](#status)).

- **Next release:** 1a, 1b, 2a, 2c, 3a, 7a and 7d. Measurement, the new checks, the finishing pass and the two cheap
  tool fixes. Then run 1c and judge the Vixl lane again: this tells us how much the loop and checks alone recover.
- **After that:** 2b, 3b, 4a, 5a and 5b. Repair, cheaper critique, balanced wrap and the data list.
- **Then:** 6a, 6b, 4b, 4c, 5c, 6c, 7b, 7c and 7e, re-judging after each group.

Related issues in the [development plan](roadmap.md): #210 (`adapt-layout` with no hand fixes), #213 (tab stops),
#214 (data binding), #218 (drawing polish), #404 (accent count), #412 (expressive layouts) and #427 (illustration
defaults).

## Status

Every item below is built; none is judged yet. The goals above are measured by a blind re-judging, which needs a
paid agent run (`python -m evals.craft_rerun`, 1c) and judges, so no craft gain is claimed until then.

| Item | State | Where |
| --- | --- | --- |
| 1a | Built: the re-run copies every `.vixl` document, its operation batches and the tool-call trace into `src/` beside each run's outputs, and the lane rule asks the agent to save its documents | `evals/craft_rerun.py` |
| 1b | Built, as reconstructions: the round-1 sources were never committed, so the 16 documents (20 files) are rebuilt from each run's ops, its SVG or measurements of its published outputs, with the judges' 21 composition defects and 48 others as expected findings | `evals/craft_backtest/`, `python -m evals.craft_backtest` |
| 1c | Built, not yet run: re-runs the Vixl lane on the 16 briefs, packages it with `rejudge.py` beside the fixed lanes and prints the judge prompt | `python -m evals.craft_rerun` ([evals/README.md](../../../evals/README.md#craft-re-run)) |
| 1d | Built: `no_composition_findings` is part of the house-style quality score; it caught the first false finding of 2a during this work. The task harness also has a `craft` check (the composition checks on the finished document, scored 0-1), four sparse craft briefs whose reference solutions score 1.0 with floors in `evals/baseline.json`, and an optional `--judge` rubric score by a model (off by default, never in CI, not yet run) | `evals/house_style.py`, `evals/harness.py`, `evals/judge.py` ([evals README](../../../evals/README.md#craft-grader-and-judge)) |
| 2a | Built: the `composition` family, a default family of review findings. Backtest: 12 of 21 judged defects caught, 0 false findings (dead band 5/10, margin drift 4/5, uneven rhythm 2/4, crowding 1/1, clumped scatter 0/1) | `src/vixl/composition.py`, [guides](../../guides/layout/guides.md) |
| 2a (#649) | Built: four more `composition` codes, review findings with suggestions and no automatic repair: `flat_hierarchy`, `single_weight`, `no_focal`, `accent_unused`. Backtest: 0 caught of 0 expected and 0 false findings for each, because no judged defect of the reconstructions is a hierarchy one; the reconstructions are also set in the proofing font and carry no rolled direction, so `single_weight` and `accent_unused` cannot fire on them. The closest `flat_hierarchy` call is 2.13 times the body (limit 1.6). House-style eval before and after: `no composition` 1.0 at low, medium and high, no regressions | `src/vixl/composition.py`, [guides](../../guides/layout/guides.md#composition), [backtest](../../../evals/craft_backtest/README.md) |
| 2b | Built: `repair-layout` repairs composition findings; on the backtest it resolves 18 of 23 findings with no new finding | `src/vixl/plugins/layout_repair/composition_repair.py`, [agent trust](../../reference/agent-trust.md) |
| 2c | Built: the `final` profile runs `composition` | `src/vixl/policy.py` |
| 3a | Built: the finishing pass ends the loop in SKILL.md, `START_HERE` and the MCP instructions; the checklist lives once, as guidance `finishing` | `src/vixl/guidance.py` |
| 3a (#649) | Built: a `variations` workflow (2-4 seeded rolls rendered on copies, a labelled contact sheet, the `roll` step per seed; the document is unchanged) and a skill reference of six generic-versus-finished pairs with the operations that close each gap | `src/vixl/variations.py`, [safe variety](../../guides/layout/safe-variety.md#comparing-variations), `skills/vixl/references/finishing-pairs.md` |
| 3b | Built: `check=true` returns every composition finding and the two weakest regions, with real-size crops when `preview` is also asked for | `src/vixl/critique.py` |
| 4a | Built: `wrap: "balance"` and `"pretty"`; headings balance by default | [typography](../../guides/text/typography.md#line-breaking) |
| 4b | Built: tab stops with leaders on text, `leader` on table columns | [typography](../../guides/text/typography.md) |
| 4c | Built: `accent_words` on `layout-apply` | [sizes and layouts](../../guides/layout/sizes-and-layouts.md) |
| 5a | Built: `key-value-list`, which chart `legend_values` also draws | [charts](../../guides/output/charts.md), [containers](../../guides/layout/containers-and-templates.md) |
| 5b | Built: one spacing unit of rule clearance (footer rules, `section-header`). T16's own crowding came from a table's header rule, which this does not change | [house style](../house-style.md#current-defaults) |
| 5c | Built: rolled `cta` pills and `date` highlights | [safe variety](../../guides/layout/safe-variety.md) |
| 6a | Built: `reflection`, `haze`, `star-field`, `string-lights`, `bokeh` | [atmosphere](../../guides/finishing/atmosphere.md) |
| 6b | Built: `vixl_reference` returns `motifs` from one registry, with new catalog shapes (cup, steam, lighthouse, lantern) | `src/vixl/data/motifs.json` |
| 6c | Built: organic preset `water` | [organic](../../guides/shapes/organic.md) |
| 7a | Built: progressive `pattern-scatter` (40 → 32 copies keeps all 32 in place) and `thin` | `src/vixl/scatter.py` |
| 7b | Built: fills register to rendered strokes; `edge_closes` carries short lines to the edge (`edge_reach`) | [drawing](../../guides/images/drawing.md) |
| 7c | Built: an enlarged photo runs its leading `denoise` at its own pixels, so linked crops show the cleaned master | `src/vixl/render.py` |
| 7d | Built: a new chart fills the safe area, inset by two spacing units | [charts](../../guides/output/charts.md) |
| 7e | Built: shading ramp and outline on new `pixel-art` | [pixel art](../../guides/motion/pixel-animation-spacing.md) |

Known gaps from the backtest: dead bands crossed by thin lines (T12 waves, T03 ripples), space beside a lone footnote
(T08) and clumping that is about similar motifs lining up rather than density (T15) are not caught yet.

## Rules

- Every default change follows the #430 policy and the #431 gate, as in the [development plan](roadmap.md#rules-for-every-release-below).
- A new check lands with its backtest numbers from 1b: what it catches among the judges' defects, and how many false
  findings it adds on the 16 documents.
- Craft claims in the changelog cite a blind re-judging, not a self-assessment.
