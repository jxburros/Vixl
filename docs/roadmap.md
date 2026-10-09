# Development plan

[Documentation home](README.md) · [House style decisions](house-style.md) · [Releases](releases.md) · [Changelog](../CHANGELOG.md)

This plan orders the open issues after 0.24.0. Each issue was rated for **complexity** (C1 a few hours, C2 about a
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

## What 0.23.0 settled

0.23.0 shipped the whole "defaults and speed" plan:

- **House-style foundation:** the default-change policy and `house_style_version` stamp (#430), the sparse-brief
  diversity and quality eval (#431), house style as data in `src/vixl/data/house-style.json` (#401), the purpose tier
  (#403) and safe, bold and avant-garde tiers gated by variety level (#405).
- **Rolled defaults made visible:** #389, #390, #391, #392, #393, #394, #397, #398, #399 and #285.
- **Craft defaults:** #408, #409 + #370, #410, #411, #418, #421 + #282, #426, #420, #425, #428, #400, #413 and #414,
  plus density by purpose from #412 (decision E4).
- **Speed:** #284 + #300, #327, #335 and #341, held by `pytest -m perf` time budgets.
- **Common agent paths:** #339, #351, #368, #357, #358, #382 (the `part:` field waits for #374) and #385.
- **QA findings:** #290, #294, #296, #297, #298, #301, #303, #304, #372, #280, #293, #347, #311, #338, #306, #288,
  #352, #354, #355, #360, #361, #362, #366, #323, #325, #292, #302, #307, #312, #346, #359, #363 and #365, plus #313
  and #324.
- **Executable docs:** `tests/test_docs_executable.py` runs the `vixl` commands and JSON operation blocks in `docs/`
  and `skills/`.

## What 0.24.0 settled

0.24.0 shipped authoring reliability and reusable delivery:

- **Type and layout from the plan:** one spacing scale with `gap: "2u"` units (#407), weighted alignment (#415),
  sixteen more font pairings in house style 3 (#416), the long-measure review finding (#423), one scale-aware minor
  text minimum (#424), contrast-driven background mixing (#402) and easing by intent with seamless default loops
  (#429), plus weight-aware large-text contrast and underfilled tall canvases (#499).
- **Delivery:** deterministic `pack`/`unpack` project folders (#511), `app-animation-package` (#510) and
  `screen-capture` (#259, which this plan had suggested closing).
- **Items from the decision list and Later:** three video templates with character-pose `time` keyframes (#179,
  #472), paint `drip`, `relief` and `light_angle` (#258), irregular image frames through `frame_shape` or an SVG
  `outline` (#266, the frame part), browser blend modes in SVG (#231) and editable re-import of simple gradient
  rectangles and stroked paths from Vixl's own SVG (#334, partly).
- **Review semantics:** `check.passed` is false for any finding that needs a fix, grouped under `by_action` (#464).
- **Emoji:** the offline VIXL Line library, custom packs and `emoji-*` workflows; see [Emojis](emojis.md).

## Rules for every release below

- **Default changes follow #430**: they apply to new documents only (new `design_defaults` carry
  `house_style_version`), and each changelog line gives the override that restores the old result.
- **Default changes are gated by #431**: `python -m evals.house_style --compare evals/house-style-baseline.json` runs
  before and after, and a change may not lower quality or diversity at any variety level.
- **Speed claims are tested**: a changelog figure is a `pytest -m perf` time budget (`tests/test_perf.py`), not an
  assertion.
- **Docs are executable**: `tests/test_docs_executable.py` runs the `vixl …` commands and JSON operation blocks in
  `docs/` and `skills/`; new blocks are picked up automatically.

## 0.25.0: objects, data and documents

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

#406 (text stages, C4 P4), #412 (expressive layouts, C3 P4), #422 (tiered styles, C3 P3), #417 (layout grids as
guides, C2 P2), #404 (accent count, C3 P2), #427 (illustration defaults, after #379 and #380, C3 P3).

### Fonts (#191 phase 1 + #419)

Replace the DejaVu fallback with a broad-coverage open font and fetch CJK faces on demand (C2 + C4, P3–P4).
Emoji artwork, editable masters, custom packs and destination exports are now implemented; see [Emojis](emojis.md).
Color emoji font support remains subject to the text engine's font format limits.

## Later

| Issue | What | C | P | Note |
| --- | --- | --- | --- | --- |
| #210 | `adapt-layout` that needs no hand fixes | 4 | 4 | Reuse #407, #409 and #424; 0.24.0 added explicit `recompose: true` |
| #171 | Translated variants with an overflow check | 3 | 3 | |
| #172 | Device and print mockups | 3 | 3 | Procedural, licence-clean templates |
| #266 | Non-rectangular canvas | 3 | 3 | Irregular image frames shipped in 0.24.0; a page clip shape in every exporter remains |
| #218 | Drawing pipeline polish | 3 | 2 | Split into its six items first |
| #334 | Editable round trip of Vixl's own SVG | 4 | 2 | 0.24.0 re-imports simple gradient rectangles and stroked paths |
| #177 | Lottie export | 5 | 3 | After motion features settle |
| #166 | PPTX font embedding | 4 | 3 | Re-scope: warnings and licences shipped; PDF is the fidelity route |
| #214 | Remainder of a partly shipped issue: bind chart data across charts and into text | 3 | 3 | |

## Needs a decision or a spec

None open: #179 and #258 were specified and shipped in 0.24.0, and #259 shipped as an explicit local `screen-capture`
workflow.
