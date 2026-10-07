# Development plan

[Documentation home](README.md) · [House style decisions](house-style.md) · [Releases](releases.md) · [Changelog](../CHANGELOG.md)

This plan orders the open issues after 0.22.1. Each issue was rated for **complexity** (C1 a few hours, C2 about a
day, C3 several days, C4 one to two weeks, C5 several weeks or open-ended) and **payoff** (P1 cosmetic or rare, P2 a
narrow workflow, P3 a common workflow, P4 changes results for most agents, P5 first impression or correctness of
output). Issues that share a cause or a code path are grouped so they ship together, and each group names one
addition that costs little while that code is open.

The order is a recommendation. Re-rate an issue when it is picked up; move it when its cost or value changes.

## What 0.22.1 settled

0.22.1 fixed the highest-payoff QA findings: export parity (#279, #305, #309, #318, #330), renderability after apply
(#281, #289, #295, #331, #371), the logo package (#287, #291), text defaults (#283, #395), one alpha default (#396,
#315), the error sweep and CLI parity (#277, #278, #299, #308, #310, #314, #316, #317, #319, #320, #321, #322, #326,
#328, #329, #336, #342, #345, #349, #353, #356, #364, #367, #369), release hygiene (#286, #333) and documentation drift
(#337, #340, #343, #344, #348, #350, #373). It also brought the house-style decision record and the 0.22.0 QA report
onto main, and closed the feature requests that 0.22.0 had already shipped.

## Rules for every release below

- **Default changes follow #430**: they apply to new documents only, and each changelog line gives the override that
  restores the old result. Before the first house-style default changes, stamp a `house_style_version` in
  `design_defaults` so old documents keep their defaults and tests can pin a version.
- **Default changes are gated by #431**: the diversity and quality eval runs before and after, and a change may not
  lower quality or diversity at any variety level.
- **Speed claims are tested**: add `pytest -m perf` with time budgets (one move on 4,096 layers, the overlap check on
  dense text, a 100k-character text flow) when #284 lands, so a changelog figure is a test, not an assertion.
- **Docs are executable**: add a test that runs the `vixl …` commands and JSON operation blocks in `docs/` and
  `skills/` in a temporary workspace. #373 and #343 would have failed it.

## 0.23.0: defaults and speed

Theme: what Vixl produces from a sparse brief looks designed, and edits on large documents stay fast.

### 1. House-style foundation (do first)

| Issue | What | C | P |
| --- | --- | --- | --- |
| #430 | Default-change policy, plus the `house_style_version` stamp | 1 | 3 |
| #431 | Diversity and quality eval for sparse briefs (gates the rest) | 3 | 4 |
| #401 | House style as data (`house-style.json`, one loader) | 4 | 5 |
| #403 | Purpose tier in the defaults precedence | 3 | 4 |
| #405 | Safe, bold and avant-garde tiers gated by variety level | 3 | 4 |

### 2. Make today's rolled defaults visible (bugs under #388)

| Issue | What | C | P |
| --- | --- | --- | --- |
| #389 | Rolled accent is drawn in safe compositions | 2 | 3 |
| #390 | Rolled density changes margins and scale | 2 | 3 |
| #391 | Roll filters act on the pools actually rolled | 2 | 3 |
| #392 | `layout-apply` inherits the whole stored direction | 2 | 3 |
| #393 | Variety levels differ; rolled looks are visible; all safe styles roll | 2 | 4 |
| #394 | One creation path for CLI, Python and MCP (`--seed`, `--variety`) | 2 | 4 |
| #397 | Diagrams follow the palette and dark mode | 2 | 3 |
| #398 | Simple templates scale with the canvas | 2 | 3 |
| #399 | Brief recommendations agree with the attached roll | 2 | 3 |
| #285 | Playful rolls look playful (closes with #391, #393, #405) | 3 | 4 |

### 3. Craft defaults

| Issue | What | C | P |
| --- | --- | --- | --- |
| #408 | Default text size from the type scale | 1 | 4 |
| #409 + #370 | 5% default safe area; layouts pass their own check (full-bleed uses `allow_crop`) | 2 | 4 |
| #410 | Primitive fills, strokes and corners from the palette roles | 2 | 4 |
| #411 | Palette background by default; transparent for marks | 2 | 3 |
| #418 | Install the rolled pairing at creation | 2 | 5 |
| #421 + #282 | One line-height table; negative spacing for display type | 2 | 4 |
| #426 | Dark, saturated, duotone and earthy safe palettes | 2 | 4 |
| #420, #425, #428 | Look by purpose, subtle irregularity, split and pattern backgrounds | 1 each | 2–3 |
| #400, #413, #414 | Mode, size and pairing weighted by purpose | 1–2 | 2–3 |

### 4. Speed

| Issue | What | C | P |
| --- | --- | --- | --- |
| #284 + #300 | Apply cost independent of unrelated layers: incremental inspect, cached text metrics | 4 | 5 |
| #327 | Overlap check without a full-canvas surface per text candidate | 3 | 3 |
| #335 | Linear long-word breaking in text-flow | 2 | 2 |
| #341 | A clean `resource_limit` on memory pressure; smaller full-canvas buffers | 4 | 2 |

### 5. Common agent paths

| Issue | What | C | P |
| --- | --- | --- | --- |
| #339 | `text-layout` with only a width grows its height | 2 | 4 |
| #351 | `diagram-from-text` fits its box | 2 | 4 |
| #368 | Compose image slots accept paths and URLs (one-call memes) | 2 | 4 |
| #357, #358 | Compose background and style shape the layout | 1–3 | 3–4 |
| #382 | `reparent` layers into or out of a group (independent object groundwork) | 3 | 5 |
| #385 | `layer-intent` CLI flags and inspect fields | 1 | 2 |

### 6. Remaining QA findings

Small, independent fixes; take them alongside the bundle whose code they touch.

| Area | Issues |
| --- | --- |
| Motion | #290, #294, #296, #297, #298, #301, #303, #304, #372 |
| Text and pages | #280, #293, #347 |
| Export | #311 (PPTX skew), #338 (TIFF dpi), #306 (bleed rounding) |
| Looks and checks | #288, #352, #354, #355, #360, #361, #362, #366 |
| Import and limits | #323 (very large images), #325 (early 413) |
| Other | #292, #302, #307, #312, #346, #359, #363, #365 |

## 0.24.0: objects, data and documents

### Objects (#257)

Order: #374 (declare an object) → #377 (inspect, isolate, export one) → #379 (outline policy) → #375 (kind registry) →
#376 (build knowledge) → #380 (`object-plan`) → #378 (object check) → #381 (editable object library, closes BLK-24) →
#386 (docs). #383 (detection) is the lowest payoff and can wait.

| Issue | C | P |
| --- | --- | --- |
| #374 | 4 | 4 |
| #377 | 3 | 4 |
| #379 | 3 | 4 |
| #375 | 4 | 3 |
| #376 | 3 | 3 |
| #380 | 4 | 4 |
| #378 | 4 | 3 |
| #381 | 4 | 4 |
| #383 | 4 | 2 |
| #386 | 2 | 3 |

### Export metadata (#175 + #384)

Alt text and object identity both write per-layer metadata into SVG `title`/`desc`, PPTX `name`/`descr`, PDF `/Alt`
and PSD layer names. Build one metadata hook per writer and use an object's label as its default alt text. C3 each,
P4 and P3.

### Data model (#213 → #169 → #214)

Tab stops and decimal alignment first (#213, C3 P3): the table layer needs them. Then the table layer (#169, C4 P5),
then the remainder of #214 (C4 P3). Add one named dataset (CSV or inline) that tables, charts and text bind to,
formatted with the merge-field filters that shipped in 0.22.0; it makes #214 mostly wiring.

### Markdown builds (#170 + #332)

`deck-from-markdown` (C3 P5) is orchestration over compose, pages, masters and layouts. Ship a report variant in the
same workflow (pages, text flow, charts), which is what the `report` brief kind (#332, C2 P3) should recommend.

### Type and layout

#406 (text stages, C4 P4), #412 (expressive layouts, C3 P4), #422 (tiered styles, C3 P3), #407 (one spacing scale,
C3 P3), #415 (alignment distribution, C3 P2), #416 (more pairings, C2 P3), #417 (layout grids as guides, C2 P2), #423
(75-character measure, C2 P3), #424 (one minimum text size, C2 P3), #404 (accent count, C3 P2), #402 (contrast-driven
background mixing, C2 P3), #427 (illustration defaults, after #379 and #380, C3 P3), #429 (easing by intent, C2 P3).

### Fonts (#191 phase 1 + #419)

Replace the DejaVu fallback with a broad-coverage open font and fetch colour emoji and CJK faces on demand, in one
change (C2 + C4, P3–P4). Make the fonts check name uncovered characters now; emoji phases 2–4 are a separate epic.

## Later

| Issue | What | C | P | Note |
| --- | --- | --- | --- | --- |
| #210 | `adapt-layout` that needs no hand fixes | 4 | 4 | After #407, #409 and #424, which it should reuse |
| #171 | Translated variants with an overflow check | 3 | 3 | |
| #172 | Device and print mockups | 3 | 3 | Procedural, licence-clean templates |
| #231 | Per-layer `mix-blend-mode` in SVG | 3 | 3 | |
| #266 | Non-rectangular canvas | 3 | 3 | Needs a page clip shape in every exporter |
| #218 | Drawing pipeline polish | 3 | 2 | Split into its six items first |
| #334 | Editable round trip of Vixl's own SVG | 4 | 2 | #305 removed one blocker |
| #177 | Lottie export | 5 | 3 | After motion features settle |
| #166 | PPTX font embedding | 4 | 3 | Re-scope: warnings and licences shipped; PDF is the fidelity route |
| #214, #230, #237 | Remainders of partly shipped issues | 2–4 | 2–3 | Split each remainder into its own issue |

## Needs a decision or a spec

- **#179** (more video templates), **#258** (paint physics): name the concrete templates or effects and their
  acceptance before scheduling.
- **#194** (full CMYK): CMYK import and CMYK PDF, TIFF and JPEG export exist; say what is still missing, or close.
- **#256** (irregularity engine): fold the remaining intent into #425 and #427, then close.
- **#259** (screen capture): out of scope for a document engine and raises permission questions; importing a
  screenshot file already works. Suggest closing.
