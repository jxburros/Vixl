# Development plan

[Documentation home](../README.md) · [House style decisions](house-style.md) · [Releases](../reference/releases.md) · [Changelog](../../CHANGELOG.md)

This plan ordered the open issues after 0.24.0. Releases 0.25.0 to 0.32.0 have shipped since: the "What … settled"
sections record what each one settled, and the open work is under Craft and Later. Each issue was rated for **complexity** (C1 a few hours, C2 about a
day, C3 several days, C4 one to two weeks, C5 several weeks or open-ended) and **payoff** (P1 cosmetic or rare, P2 a
narrow workflow, P3 a common workflow, P4 changes results for most agents, P5 first impression or correctness of
output). Issues that share a cause or a code path are grouped so they ship together, and each group names one
addition that costs little while that code is open.

The order is a recommendation. Re-rate an issue when it is picked up; move it when its cost or value changes.

The [implementation plan](implementation-plan.md) covers every issue open on 2026-10-16, with its status, cause, steps,
tests and ratings, and a release order across all of them.
Its steps 0 to 6 are done (housekeeping, release blockers, security and project hygiene, check noise, layout and
agent cost in 0.28.0; concurrency, structure and rendering speed in 0.29.0, with the speed
decisions in [render performance](render-performance.md); craft, objects and brand packages in 0.31.0, apart from
the blind craft re-judge; step 7, multi-document automation and hosting, in 0.32.0). Step 8 motion and media work is recorded in the
Unreleased [changelog](../../CHANGELOG.md) and the implementation plan; remaining validation and deferred work are explicit there.

## What 0.22.1 settled

0.22.1 fixed the highest-payoff QA findings: export parity (#279, #305, #309, #318, #330), renderability after apply
(#281, #289, #295, #331, #371), the logo package (#287, #291), text defaults (#283, #395), one alpha default (#396,
#315), the error sweep and CLI parity (#277, #278, #299, #308, #310, #314, #316, #317, #319, #320, #321, #322, #326,
#328, #329, #336, #342, #345, #349, #353, #356, #364, #367, #369), release hygiene (#286, #333) and documentation drift
(#337, #340, #343, #344, #348, #350, #373). It also brought the house-style decision record and the 0.22.0 QA report
onto main, and closed the feature requests that 0.22.0 had already shipped.

## What 0.23.0 settled

0.23.0 shipped the whole "defaults and speed" plan:

- **House-style foundation:** the default-change policy (#430), the sparse-brief
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
- **Emoji:** the offline VIXL Line library, custom packs and `emoji-*` workflows; see [Emojis](../guides/text/emojis.md).

## What 0.25.0 settled

0.25.0 shipped the checks, objects and content plan below:

- **Checks and repair:** workspace-wide checks (`check --all`, run history, `--since-last`), outcome states, located
  findings with suggested repairs, `repair-layout`, `protected-edit`, waivers and the `draft`/`review`/`final` profiles
  (#518, #520, #524, #525, #562, #563, #566).
- **Objects and accessibility:** declared objects with a kind taxonomy, isolated review and export, an editable object
  library, object identity and alt text in the exports (#374, #375, #377, #381, #384, #386, #175).
- **Content workflows:** `table` (#169), `deck-from-markdown` (#170), `mockup` (#172), `die-cut` and logo tracing
  (#443, #444), and proportional `adapt-layout` with safe zones (#210).
- **Brand and type:** text stages (#406), brand presets and compliance (#436, #555), `brand-board` (#581) and the
  bundled Noto fallback faces (#419).
- **Host integration:** `vixl catalog export` (#536) and per-call limits (#542).

## What 0.26.0 settled

0.26.0 added eighteen editable promo video templates, `path_view` for native path data (#610), archive load budgets
(#635), `--out` and `-o` on every output command with a compact command index (#639), a generated interface
capability matrix (#640) and native opaque blending (#585). Showcases and media moved to VixlExamples.

## What 0.27.0 settled

0.27.0 was a breaking release:

- **One agent surface:** the MCP server went from 51 tools to seven, with a size ratchet ([MCP tool surface](../reference/mcp-toolsets.md)).
- **An open format:** the published `.vixl` format and JSON Schema, SVG that re-imports as the same document (#334),
  editable SVG, PDF and Figma import (Figma export is #662), and a conversion kit ([Converting](../reference/converting.md))
  in place of the compatibility code for older releases.
- **Rendering parity:** strokes inside and flush with closed shapes, in-place drawing of text and vector shapes, dithered
  gradients ([Render parity](render-parity.md)); terminal summaries in the CLI.
- **The craft plan, built:** see Craft below.

## What 0.28.0 settled

0.28.0 completed steps 2 and 3 of the [implementation plan](implementation-plan.md):

- **Security and hygiene:** a network policy (`VIXL_OFFLINE`, `VIXL_FETCH_HOSTS`, fail-closed fetches behind a proxy),
  REST and token hardening, https-only remote AI providers, restricted image decoders, `untrusted` document text in
  results, SHA-pinned workflows with an approved publish step, signed Windows updates, governance files and a
  development lockfile (#668, #672, #673, #674, #675, #677, #621, #624, #682, #683, #678, #692 part A).
- **Checks, layout and cost:** per-page suite rules, reported production holds, the event-poster footer, poster type
  and spacing at use size, runt and overlap noise, roll fallbacks, capped brief apply results, the CLI's schema and
  suggestions, deferred font installs, a 9 KB agent skill (#679, #680, #684, #686, #689, #693, #637, #698, #700, #701,
  #702, #710, #711, #712, #713).
- **Before it:** built-in plugins and the emoji content pack, making fonts, use-size legibility and the docs
  reorganization.

## What 0.29.0 settles

0.29.0 completes step 4 of the [implementation plan](implementation-plan.md) and adds gradient fills on shapes
(#744):

- **Concurrency and service limits:** typed cancellation and one module for private SDK access (#685), default
  limits and a hard timeout for network servers (#623), one lock per document (#629), cheaper applies and saves
  (#630).
- **Structure:** one content-hash encoding (#634), a layering test (#632), a core operation registry (#631) and
  strict types on the core leaves (#633).
- **Speed:** a render pool for GIL-releasing layers (#590), incremental lit scenes and per-pixel adjustments (#595)
  and worker processes for long timeline exports (#717). #588 is deferred, #584 waits on a parity decision, and
  #591 and #593 are closed with numbers ([render performance](render-performance.md)).

## What 0.31.0 settles

0.31.0 completes steps 5 and 6 of the [implementation plan](implementation-plan.md), except the blind craft re-judge,
which needs a paid agent run and judges:

- **Craft:** small caps, hanging punctuation, accent words on plain text and the callout, band and labelled-rule
  containers (#652, #650); four hierarchy findings, a `variations` contact sheet and a craft grader in the agent eval
  (#649, #656); zero to three rolled accents and palettes weighted by the brief's words (#404, #654); flex and grid
  stacks, recomposition by default, focal crops and alternative arrangements in `adapt-layout` (#653, #519); fog and
  nine more motif themes with five catalog shapes (#655, #651); the house illustration finish for organic forms and
  `object-plan` (#427); Noto Sans as the proofing face, with CJK, Devanagari and Thai drawn from faces already on the
  machine (#419).
- **Objects:** build knowledge per kind, the `object` check, the outline policy and `object-plan` (#376, #378, #379,
  #380).
- **Brand packages:** image assets in packs, text line anchors and safe arithmetic in templates, and logos by purpose,
  brand elements, brand styles and `vixl brand init|pack|install` (#530, #529, #436).
- **Delivery and content:** merch mockups with print areas, finishes and print-ready art (#444), portable character
  packages in one object library (#521), render lockfiles over every page, frame and export, and deliverable
  packages (#512, #573).

## What 0.32.0 settled

Step 7 of the [implementation plan](implementation-plan.md#step-7-multi-document-automation-and-hosting), shipped
in 0.32.0, adds checks and automation across many documents (#549) and `vixl host` (#535), plus fonts
installed on the machine:

- **Foundations:** one `job-complete` event for durable jobs, check-all and pipeline runs, and plugin job kinds (F2);
  the run record and pipeline runner (F1, #568); the workspace dependency graph (F3) and "evaluate a copy, commit only
  if clean" (F4) in `workspace_qa`.
- **Checks across documents:** suite rules that reference another document (#558), render-time and over-resolution
  budgets and the `budget` check (#564), post-export checks with delivery specs and `vixl check-file` (#557),
  approved baselines (#559), link impact (#560), the locale check (#565), spelling with brand word lists (#554) and
  logo variants on approved backgrounds (#555).
- **Automation:** pipelines with resumable run records (#568), completion webhooks (#579), watch mode with save,
  source, brand, data and schedule triggers (#569, which absorbs the schedule part of #577), data sync (#572),
  localized variants with right-to-left mirroring (#576, folding in #171) and bulk structure upgrades (#578).
- **Hosting:** `vixl host` with workspaces, revisioned documents, compose, preview, check, export jobs, catalogs, a
  `studio` tool profile and a published API schema (#537-#541, #543); the brand route and Design Profile mapping
  (#545); a `studio` AI provider against a proposed gateway contract (#544); a container image (#546) and a per-user
  Windows host task (#547).
- **Fonts:** any font installed on the machine works by family, style or PostScript name, is embedded in the
  document, and is listed in the CLI, MCP, REST and Python API.
- **Already shipped, to close with evidence:** #567 (JUnit and SARIF), #577 (run history; its schedule is in #569),
  #542 (per-call limits) and #555 (now with logo variants).

Open decisions from this step: Studio's gateway contract and its detection path for the Windows host task (#544,
#547); whether the release workflow should trigger the container build (#546); an admin Windows service (not built).

## Step 8: motion and media (unreleased)

Implemented with focused regression coverage: appearance-preserving ungroup (#611), independent nested animation
instances (#513), film/lyric delivery verification and explicit review (#613), reviewable provider-assisted lyric
alignment (#523), per-cue compositions and preserved edits (#612), shared datasets and bound text (#214), and the drawing-pipeline remainder (#218).

The export-speed track has budgets, measured worker selection, VP9 settings, fast frame ZIPs, opaque-frame handling,
scalar frame copies and draft/final presets (items 1–6 and 8). Fade-cache changes (7) and hardware encoding (9)
remain deferred; software encoding stays the default. See the [step 8 implementation record](implementation-plan.md#step-8-motion-and-media)
for feature-specific limits. Lottie JSON/dotLottie/TGS is reference-tested and keeps Bezier easing as curves and
linked instances as time-remapped precompositions (#177, 0.33.1). Figma interchange and its offline import plugin are implemented;
live Figma visual review remains pending.

## Rules for every release below

- **Pre-release: breaking changes are allowed; note them in the changelog.** Default changes must still pass the
  house-style quality/diversity eval (#431): `python -m evals.house_style --compare evals/house-style-baseline.json`
  runs before and after, and a change may not lower quality or diversity at any variety level.
- **Speed claims are tested**: a changelog figure is a `pytest -m perf` time budget (`tests/test_perf.py`), not an
  assertion.
- **Docs are executable**: `tests/test_docs_executable.py` runs the `vixl …` commands and JSON operation blocks in
  `docs/` and `skills/`; new blocks are picked up automatically.

## 0.25.0: objects, data and documents

This section is the original plan, kept for its ratings. Most of it shipped in 0.25.0 (see above), and tab stops
shipped in 0.27.0; the changelog records which issues landed.

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
then the remainder of #214 (C4 P3). The table layer and #213 have shipped: text takes left, right, centre and
decimal tab stops with dot leaders, and table columns take a `leader` (craft plan 4b). Add one named dataset (CSV or inline) that tables, charts and text bind to,
formatted with the merge-field filters that shipped in 0.22.0; it makes #214 mostly wiring.

### Markdown builds (#170 + #332)

`deck-from-markdown` (C3 P5) is orchestration over compose, pages, masters and layouts. Ship a report variant in the
same workflow (pages, text flow, charts), which is what the `report` brief kind (#332, C2 P3) should recommend.

### Type and layout

#406 (text stages, C4 P4), #412 (expressive layouts, C3 P4), #422 (tiered styles, C3 P3), #417 (layout grids as
guides, C2 P2), #404 (accent count, C3 P2), #427 (illustration defaults, after #379 and #380, C3 P3).

### Fonts (#191 phase 1 + #419)

Noto Sans, Noto Sans Symbols, Symbols 2 and Math are bundled behind DejaVu Sans, so Latin, Greek, Cyrillic and symbol
text renders without tofu offline. Noto Sans became the proofing face in 0.31.0, and CJK, Devanagari and Thai text
draws from a matching face already on the machine; a pinned CJK content pack in VixlPacks is still open (C2, P3).
Emoji artwork, editable masters, custom packs and destination exports are now implemented; see [Emojis](../guides/text/emojis.md).
Color emoji font support remains subject to the text engine's font format limits.

## Craft

The [craft plan](craft-plan.md) orders the work on the quality of finished pieces that came out of the 2026-10-13
blind re-judging: composition checks and repair, a finishing pass in the agent loop, typography, components,
scene effects and tool finish, measured by re-judging the Vixl lane. Every item was built in 0.27.0, and the remainders of the craft issues
(#649 to #656, #404, #419, #427) in 0.31.0; none is judged yet, which is the open step
(`python -m evals.craft_rerun`, [evals/README.md](../../evals/README.md#craft-re-run)). #648 and #388 close when a
re-judge is published.

## Later

| Issue | What | C | P | Note |
| --- | --- | --- | --- | --- |
| #266 | Non-rectangular canvas | 3 | 3 | Irregular image frames shipped in 0.24.0; a page clip shape in every exporter remains |
| #166 | PPTX font embedding | 4 | 3 | Re-scope: warnings and licences shipped; PDF is the fidelity route |
| — | Animation export speed: an export perf budget, faster VP9 settings, measured worker count, cheaper frame setup and fades, encoder presets, opt-in hardware encoding | 1–3 | 2–3 | Step 8 of the [implementation plan](implementation-plan.md#step-8-motion-and-media); numbers in [render performance](render-performance.md#animation-export-2026-10-22) |

## Needs a decision or a spec

None open: #179 and #258 were specified and shipped in 0.24.0, and #259 shipped as an explicit local `screen-capture`
workflow.
