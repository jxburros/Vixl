# Checked production workflows

[Documentation home](../../README.md) · [Getting started](../../getting-started.md) · [Visual gallery](../../gallery.md)

Vixl can save a design's requirements, turn an editable document into a typed recipe,
produce variations, reuse render work, and assemble films. These are local, headless
features: no GUI or model is needed for checks, templates, motion or rendering.

Run `python examples/build_production_demo.py --output examples/output/production`
for a complete offline example with a six-image campaign, an animated WebP, a shot
sequence and a reusable library component.

## Interfaces

Canonical operations work through `Project.apply`, `vixl apply`, REST `/operations`,
and `vixl_apply`. `vixl schema` / `vixl_reference('operations')` describe their fields.
New commands have document-independent `--help`.

Production workflows share one additional entry point:

```text
vixl workflow schema
vixl -p campaign.vixl workflow check --request checks.json --workspace .
vixl -p campaign.vixl workflow run --request production.json --workspace .
```

MCP: `vixl_reference('workflows')` and `vixl_apply(workflow=ACTION, request={…}, document?)`.
Python: `vixl.workflows.dispatch(Session(...), action, request)` or the functions below.
Every path is relative to the session's workspace and must stay within it. The CLI
defaults the workspace to its current directory; use an explicit project path.
The fixed-project REST service exposes `GET /workflow/schema` and `POST /workflow/ACTION` for
`check`, `act`, `plan`, `film-plan`, `lyric-video-plan`, `organic-catalog`, `form-fill`, `drawing-report`, `links`,
`repair-layout`, `protected-edit` and the resource actions of the [studio guide](studio.md) (`resource-*`, `shape-save`,
`suite-use`, `effect-run`, `palette-check`). Filesystem/library/job actions require
CLI, Python or a workspace-scoped MCP session. This preserves REST's existing scope.

`vixl_apply(create=…)` (CLI `vixl compose --request req.json`) builds a new document in one atomic call (create, font pairing,
layout, style, look, operations, check, preview, save, exports); see [interfaces](../../reference/interfaces.md#build-a-piece-in-one-call).
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
Over MCP the action is off until the server owner starts `vixl mcp` with `--allow-screen-capture` (or
`VIXL_ALLOW_SCREEN_CAPTURE=1`).

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
`vixl_reference('operations', name=["suite-set"])` and `vixl_reference('workflows').definitions.suite` give every
rule field a type, enum and one-line description (with an example), and `vixl_reference('workflows')` does the
same for every action's request fields and for the `job`, `spec`, `recipe` and plugin `manifest` objects.
The `check` action also accepts an inline suite object instead of a name.

Run `project.check_suite("delivery")` or workflow `check` with
`{"suite":"delivery"}`. Results include the suite hash, actual measurements,
rule IDs, times, and `passed`, `failed`, or `needs_review`. Missing/unmeasurable
targets and warnings never count as a clean pass. Checks do not modify the document.
CLI checks and failed synchronous production return a nonzero exit code.
Workflow `check` without `suite` runs every attached and inherited suite (`suites: [...]` narrows
them) and returns each report under `suites`, with overall `passed`/`status`.

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
| `spacing` | `targets` (2+ siblings), `axis`, optional `expected`, `tolerance` (default 1px); equal or exact gaps, as `vixl_check(action='spacing')` |
| `relation` | `target`, `to` (a layer or `canvas`), and any of `position` (`left-of`, `right-of`, `above`, `below`, `inside`, `contains`, `overlapping`, `apart`), `align` (edges such as `left`, `center-x`, `top`), `minimum`/`maximum` (the gap, or the smallest margin when inside), `tolerance`, `bounds` box/ink |
| `contrast` | `target`, `minimum` (default 4.5); WCAG ratio of the tenth-percentile glyph pixel against what is drawn under it (an outline style counts), as the `contrast` design check reads it |
| `color` | `point` [x,y] or `region`, `expected` colour (any Vixl colour, including `@swatch`), `tolerance` (largest RGB channel difference, default 12) |
| `ink` | `minimum`/`maximum` drawn fraction of `region` (default canvas); `tolerance` 0–255 (default 24); without `background`, the canvas colour and backdrop layers (role `background`, or a top-level full-canvas solid, gradient, image or rectangle) do not count |
| `balance` | optional `expected` [x,y] as fractions (default centre), `tolerance` (default 0.1), `region`, `background`; the ink-weighted visual centre |
| `hierarchy` | `targets` (text, most to least important), `ratio` (default 1.2); each rendered font size (after fitting) is at least `ratio` times the next |
| `count` | `target` name, glob or `group:NAME` (default `*`), optional `layer_type`, `minimum`/`maximum`; counts visible layers |
| `focal` | `target`, `grid` thirds/golden/center, `tolerance` px (default 5% of the shorter side); the layer's centre is near a power point |
| `text` | `target` name, glob or `group:NAME` (default `*`), and any of `pattern` (regular expression each selected layer must match), `contains` (phrase or list that must appear somewhere in their copy), `forbid` (regular expression or list none may match), `min_characters`/`max_characters`, `min_words`/`max_words` (per layer; line breaks do not count as characters), `case` sensitive/insensitive (for pattern, contains and forbid), `brand: true` (also forbid brand.json `words.forbid`, skipping `words.allow` phrases), `spelling: true` (words the spelling dictionary does not know fail the rule and are listed under `unknown_words` with suggestions; a missing dictionary needs review); measures the drawn text after variables, so `variables`, artboards and campaign rows are checked with their own copy; results list each layer's text, characters and words |
| `budget` | any of `max_layers` (drawn layers, as `count` counts them), `max_fonts` (distinct fonts drawn by text), `max_bytes` (the document's JSON with undo history plus embedded files, before compression), `min_ppi` (lowest effective resolution of a placed image at the canvas dpi, 300 when unset, as the `print` check measures it), `max_ppi` (over-resolution: a placed image above this effective resolution, or with over 4× the source pixels it needs at it, carries pixels no output shows), `max_render_ms` with optional `proxy` (the warm time of a proxy render, longest side `proxy` px, default 1024; cold and warm are both reported). Results list `worst` per limit: the five top-level layers with the most drawn layers, the fonts drawn by the fewest layers, the lowest or highest image ppi, each as `{layer, value}`. Render time depends on the machine, so a `max_render_ms` rule is always a `warning` with `action: review` and `advisory: true`, and goes in a budget rule of its own |

Every rule has a unique `id` and optional `severity` (`error` or `warning`). Each result carries what
it measured (gaps, margins, ratios, the visual centre, the sampled colour), so a failure says what to change.

```json
{"type":"suite-set","name":"copy","suite":{"rules":[
  {"id":"headline-short","kind":"text","target":"headline","max_characters":40},
  {"id":"has-disclaimer","kind":"text","contains":"Terms apply"},
  {"id":"no-free","kind":"text","forbid":"(?i)\\bfree\\b"},
  {"id":"light","kind":"budget","max_layers":120,"max_fonts":3,"max_bytes":20000000,"min_ppi":240,"max_ppi":1200},
  {"id":"quick","kind":"budget","max_render_ms":400,"proxy":1024}
]}}
```

The same limits run without a suite as the opt-in `budget` design check (`vixl check --checks budget`), at the
workspace defaults (`max_layers` 500, `max_fonts` 4, `max_bytes` 100 MB, `max_ppi` 1200) that `budget` in
`.vixl-checks.json` overrides field by field. Each finding is a `review` warning naming the limit, its value and
the `worst` offenders; render time is left to suites.

### Rules that reference another document

Where a rule compares against a value (`expected`, a relation's `to`, a hierarchy's `ratio`), it can read that
value from another document each time it runs, so a master or brand document sets it once:

- `{"ref": "master.vixl#brand.fill"}` reads a field of a layer (or `canvas`) as the master draws it.
- `{"ref": "master.vixl#brand:type-scale"}` reads the same field of rule `type-scale` in the master's suite
  `brand` (attached or inherited); that rule may itself hold a ref.

```json
{"type":"suite-set","name":"campaign","suite":{"rules":[
  {"id":"brand-red","kind":"color","point":[40,40],"expected":{"ref":"master.vixl#brand.fill"}},
  {"id":"type-scale","kind":"hierarchy","targets":["headline","body"],"ratio":{"ref":"master.vixl#brand:type-scale"}}
]}}
```

Paths resolve like link sources (the document's folder, then the workspace; services never read outside it), and
referenced documents are opened read-only. A suite holds at most 8 refs and one run reads at most 8 (nested refs
count, a document read twice counts once); rule refs nest at most 4 deep, and a cycle is refused with the
`link_cycle` error shape (`code`, `chain`). A missing document, layer, field, suite or rule makes the rule
`needs_review`, never a pass. Each result lists `references: [{path, digest}]` (the digest of the referenced
state), the report lists them all, and `check-all` keeps them per document, so `--since-last` names a changed
master as the cause (`cause: reference`, `changed_references`) when the dependent itself did not change.

### Coverage over artboards, pages and comps

One run can cover every variant of a design. In a suite, add `artboards`, `pages` and `comps` to
`sampling` (each `"all"` or a list of names; pages also by number); workflow `check` takes the same
fields at run time, and `vixl_check`/`vixl check`/REST `POST /check` take them for the design checks:

```json
{"type":"suite-set","name":"every-format","suite":{
  "rules":[{"id":"title-inside","kind":"relation","target":"title","to":"canvas","position":"inside"}],
  "sampling":{"mode":"still","artboards":"all","pages":"all","comps":["light","dark"]}
}}
```

```bash
vixl check --artboards all --pages all --comps light dark
```

Every combination is checked. Each suite result and each design finding names its `variant`
(`{"artboard":"story"}`; design messages start with `[artboard story]`), `groups` (suites) or `variants`
(design checks) give each variant's status, and `coverage` lists exactly what was covered. Pages hidden
from export are skipped unless `include_hidden` is set. The 50,000-evaluation cap counts every
variant × time × rule.

In a multi-page document a rule names layers that live on one page. On a page that lacks a layer the rule
references (`target`, `to`, `before`, `after`, `targets`) while another page or a master has it, the rule does not
run: its result is `not_applicable` with `reason: "layer on another page"` and the `layers` it missed, and it counts
neither as a failure nor as a review (nor towards a waiver). A name that exists on no page stays `needs_review`, so a
typo still surfaces. Design checks with `targets` over pages work the same way: a target on another page is left out
for that page and listed under the variant's `skipped_targets` (a page with none of the targets is
`status: "not_applicable"`).

To hold a rule to some pages only, give it `pages` (page names, ids or 1-based numbers, or one of them):

```json
{"rules": [{"id": "cover-title", "kind": "text-fit", "target": "title", "minimum": 24, "pages": ["Cover", 2]}],
 "sampling": {"pages": "all"}}
```

On every other page the rule is `not_applicable` with `reason: "rule limited to pages Cover, 2"` and does not count.
Without a page axis it follows the document's current page. A page that does not exist makes the rule
`needs_review` on every page, so a misspelt page name never silently switches the rule off.

### Library suites shared by a group or the workspace

`suite-use` copies a library suite into one document. To hold many documents to one contract, refer
to it instead:

- `group-define` takes `suites: ["delivery", "brand-basics"]`; every member inherits them by reference.
- brand.json `suites: [...]` does the same for every document in the workspace.
- `suite-use` with `reference: true` attaches `{"extends": NAME, "rules": []}` to one document.

Inherited suites run in workflow `check` (no `suite`), `run` (unless the spec lists `suites`),
`group-apply` (unless the request lists `suites`) and `vixl_apply(suites=true)`, and always
use the library's current version: edit the library suite (`resource-save`) and every member's next
check uses it, without touching member files. A member overrides a rule by `id`, or adds rules, with a
suite that extends the library suite:

```json
{"type":"suite-set","name":"delivery-local","suite":{"extends":"delivery","rules":[
  {"id":"title-fits","kind":"text-fit","severity":"warning"},
  {"id":"has-cta","kind":"count","target":"cta","minimum":1}
]}}
```

An override keeps the library rule's `kind` and replaces only the fields it sets. Reports name the
`library`, its `library_hash` (so a run is reproducible), where the suite came from (`source`:
`document`, `group:NAME` or `workspace`), the `overrides` (`[{id, fields}]`) and `added` rule ids. The
workspace file `.vixl-suite-passes.json` remembers the library version each document last passed; a
report on a newer version carries `contract_changed`.

### Starter suite from an approved design

Workflow `suite-infer` (`{"name":"festival"}`) reads the approved open document and proposes a tolerant
suite: `hierarchy` from the rendered type sizes (10% headroom), `relation` rules for the order of the
text roles and for the headline and logo inside the canvas (with centre alignment where it holds),
`count` for those required layers and the number of text layers, `contrast` for each text role (the
WCAG level, or a review-only warning when the approved design is lower), `text` limits from the current
copy plus headroom, and a `palette` from the colours in use. Each rule comes with an explanation of what
was measured under `explanations`; delete or tighten rules before relying on them. The suite is returned,
never attached; `apply: true` saves it as a library suite (`replace: true` overwrites one) and `group:
NAME` makes that group inherit it. `from_group: NAME` infers from every member of a group and keeps only
the rules every member proposes and passes, with each limit set to the strictest value all of them meet.

### When to test

A preview is a small downsampled picture; tests measure what it hides and keep measuring as edits accumulate.
Write the brief's requirements as a suite before building (each `vixl_reference(kind)` answer lists a starter
suite and rules to adapt under `tests`; `vixl_reference("testing")` is the method), run it with every batch
(`vixl_apply(..., check=true, suites=true)`, CLI `vixl apply ops.json --check --suites`, REST
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
| `final` | `review`: fix and review findings fail | `color_vision`, `composition` | all attached |

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

`final` keeps `composition` even when a workspace narrows its `checks`, so unresolved [composition
reviews](../layout/guides.md#composition) (dead bands, margin drift, uneven rhythm, crowding, clumped scatter, and flat
hierarchy, a single weight, no focal point or an unused accent) fail shipping
until they are fixed or waived with a reason. Only a workspace that narrows `checks` and also sets `final.optional`
replaces the built-in `optional` list (`color_vision`, `composition`); name `composition` in it to keep the gate.

`.vixl-checks.json` may also set `budget`, the limits of the opt-in `budget` check for the workspace (any of
`max_layers`, `max_fonts`, `max_bytes`, `min_ppi`, `max_ppi`), for example `{"budget": {"max_layers": 300, "max_fonts": 3}}`.

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
  where each layer moved (see [operations](../../reference/operations.md#bulk-edits-and-resizing-a-whole-layout-019)).
  A document built by `layout-apply` and not edited since is instead rebuilt from its saved recipe at the
  new size by default; `recompose: true` forces that after edits (replacing the generated layers and the edits
  to them; it fails when there is no saved recipe) and `recompose: false` never does it. `arrangements`
  (`stack-vertical`, `side-by-side`, `hero-top`, `proportional`) builds each candidate arrangement of the
  content, scores it with the composition, legibility, bounds and overlap checks and keeps the best, with an
  `outcome`. Every result says `recomposed` and why.
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

Rows can be assembled from a CSV by a caller; existing `render --data` remains available. For languages, `localize`
runs the same spec once per locale on a localized copy (its values, fonts, fit and right-to-left mirroring), so a
campaign gains a locale axis; see [localization](localization.md).
There are at most 10,000 outputs, ten variation axes and four concurrent workers.
Row fields cannot also occur in the matrix. Explicit row values override artboard defaults.
All attached suites run unless an explicit `suites` list selects others. With `profile` (for example `"final"`),
every variant must also pass that [check profile](#waivers-and-check-profiles): it picks the design checks, the
suites (unless `suites` is given) and `fail_on`, and `production.json` names it. An explicit `quality: "final"` selects the `final` check profile unless `profile` overrides it.
Omitting both fields keeps the existing checks (render quality still defaults to final). To request final-resolution
output with draft blocking rules, set `quality: "final", profile: "draft"`.

Optional `actions` run before checks; `motion` applies a saved sequence.
At most three named `repair_actions` are tried in order, stopping when checks pass. The name `auto` runs the
built-in repair map instead (fit-text, contrast ink, safe-area nudge; see
[outcomes, diagnostics and repair](../../reference/agent-trust.md#built-in-repairs)); its operations are reported under
`repair_operations`.
Failed/unmeasurable outputs are held for review; successful outputs remain available.

`export_check` reads each written output back before it is published: `true` runs the default delivery checks, a
preset name (`instagram-feed`, `web-banner`, `display-ad` ...) or inline fields check it against a
[delivery spec](../output/exporting.md#verify-the-delivered-file). Each result records the report as `export_check`
in `production.json`. An output that fails it is held for review like a failed check and is not published, and its
rules (`export.max-bytes`, `export.size` ...) count in `withheld`. A passing export check joins the validation of
outputs whose suites or profile validated them; on its own it never validates the design.

```json
{"output":"campaign","spec":{"rows":[{"title":"Launch"}],"format":"jpg","export_check":"instagram-feed"}}
```

A held output is never written, and the run says so instead of leaving an empty directory unexplained: the report
(and `production.json`) gains `withheld` (`count`, the effective `profile` and its `fail_on`, the held `variants`,
and the `rules` that blocked most often, each with the number of variants it held) and a `message` such as
`3 variants withheld by profile final (fail_on review); no output was written for them. Fix the findings, waive them
with a reason, or set profile: review`. A run that holds nothing has neither field. Because `quality: "final"`
implies the `final` profile, which fails on review findings, this is the usual reason a final run writes nothing.

Each result's `checks` has one shape:

```json
{"suites": {"delivery": {"status": "passed", "results": []}},
 "design": {"passed": true, "issues": []},
 "placeholders": null}
```

`suites` maps each suite that ran to its suite report (`results`, one per rule); `design` is the design check report
(`issues`; with a profile it carries `profile`), or `null` when suites alone checked the output; `placeholders` is the
placeholders report of a row that left template copy or an undefined variable (the run stops there for that
variant), otherwise `null`.

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
first; see [imposition](../output/imposition.md). Variant production fingerprints include the revisions of any documents a design
[links](../output/linked-documents.md), so a changed source re-renders the variants that use it.

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
`{path, label?, before?, note?}`; up to 200. `overlay: true` outlines each `fix` finding on a checked document's
thumbnail, labelled with its rule and layer ID.

The page is a single file that works offline: every image is a data URI, and its Content-Security-Policy allows only
those images, inline styles and, with `decisions: true`, the one inline script it names by hash. That script adds
approve/reject and a note per item and a **Download decisions (JSON)** button: a static page cannot write files, so
it downloads `<page>-decisions.json` (`{proof, page, generated, decided, items: [{id, path, label, decision, note}]}`)
for the reviewer to send back. Without `decisions` the page has no script at all. An existing page is replaced only
with `overwrite: true`.

A missing file fails the call, but an item that cannot be previewed or checked becomes a card with its error and
is listed in the result's `failed` (`[{path, error}]`); `checked` gives each document's `passed`, errors and
warnings. Each thumbnail is embedded once and reused by the enlarged view (`max_size`, 128–2400 px, default 1200).
A document approved with `approve` (below) gets a badge: approved, or changed since approval with the changed share.

## Approved baselines

Once a design is signed off, `approve` records how it looks, and every later check tells you what moved:

```bash
vixl approve --author "Ada"          # the current document
vixl approve --group launch           # every member of a project group
vixl approve --clear                  # remove the approval
```

Over MCP or REST it is the workflow action `approve` (`vixl_apply(workflow='approve', request={"author": "Ada"})`),
with `group` and `clear` as on the command line.

For each page and artboard (or the canvas, when there are neither) `approve` stores the render hash and a reference
PNG of at most 256 px a side, with the document's state digest, the revisions of its linked sources, who approved it
(`author`, else the `VIXL_AUTHOR` environment variable, else `agent`) and when. A document's approval lives beside it
in `NAME.vixl.approval/`; a group's in `.vixl-groups/GROUP.approval/`, one folder per member. At most 64 views are
recorded; a document with more is refused. Approving again replaces the earlier approval (that is how you unapprove
a change), and `clear` removes it. The folder is small and meant to be committed with the document.

The `approval` check then runs by itself whenever the standard checks run on a document with approval data (a plain
`vixl check`, `check-all`, `apply` with `check`, a check profile), and by name (`check --checks approval`) otherwise.
An unchanged document is settled from its state digest without rendering. A page or artboard whose render no longer
matches is a `warning` with action `review` (code `changed`): it names the view, who approved it and when, the
`changed_fraction` of the reference preview and a `diff` image (written to the approval's `diff/` folder). Asked for
by name, an approved document gets an `approved` note and one never approved a `never-approved` note.

Approval also shows where a change would land: a `group-apply` or `replace-across` dry run lists
`approved_members_changed` (each approved member the change moves away from its approval, with the views and the
changed fraction), and a [campaign run](#variant-production-and-draftfinal) from an approved template lists the
template's approved views that changed since approval.

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

### Documents that link to a changed source

`link-impact` (`vixl links impact SOURCE.vixl`) checks every document that links to a changed source, as a refreshed
copy, before anything is saved: the dependents that pass, those that fail (with their findings and rule results) and
how much each one's render changed. `--apply` then saves only the passers, through a journal. See
[link impact](../output/linked-documents.md#link-impact).

## Delivery packages

`package` (CLI `vixl package`) turns finished outputs into one zip that a client or a downstream system can trust: the
files, a manifest that says where each came from and what it was checked against, checksums, the check report and a
proof page. It takes the outputs of a [campaign run](#variant-production-and-draftfinal) (`production`, its
`production.json`) or exported files (`files`: paths and globs, or `{path, source}`).

```bash
vixl package --production out/production.json --source banner.vixl --out delivery.zip --name "{doc}_{row}_{artboard}.{ext}"
vixl package --files "exports/*.png" "exports/*.pdf" --source poster.vixl --out poster-delivery.zip --dry-run
```

```json
{"production": "out/production.json", "source": "banner.vixl", "output": "delivery.zip",
 "name": "{brand}_{doc}_{row}_{artboard}.{ext}", "layout": "by-format",
 "lock": "banner.lock.json", "decisions": "review/round-2-decisions.json"}
```

**Names.** `name` is a template of `{brand}` (the `brand` field, else the name in the workspace `brand.json`), `{doc}`
(the source document's name, else the output's own), `{artboard}`, `{w}`, `{h}` (or `{size}`: `1080x1350`), `{ext}`,
`{locale}` (a `locale` or `lang` value of the row, else the `locale` field), `{row}` and `{id}`. The default is
`{brand}_{doc}_{artboard}_{w}x{h}.{ext}`; a field with no value disappears with the separator next to it. Two files
that would get the same name (compared without regard to case) refuse the whole package before anything is checked or
written, with every clash listed under `collisions` and a longer template suggested; a campaign of several rows needs
`{row}` or `{id}`. `layout` is `flat` (default), `by-format` or `by-artboard` (one folder each).

**What goes in.** Each completed output of a run once: outputs with identical bytes are packaged once, and the kept
file lists the others under `duplicates`. A variant the run held for review (`needs_review`), failed or cancelled, an
output whose file is missing or no longer matches the checksum in `production.json`, a file whose source document fails
its checks (with `files` and `source`), and a file rejected on the proof page are listed under `held` with the reason
and the rules, and are not in the zip. If nothing is left the call fails and lists them.

The zip holds the files, `manifest.json`, `SHA256SUMS` (`sha256sum -c` format), `proof.html` (an offline
[proof page](#proof-pages), up to 200 files) and, with `check` (default), `report/check-report.json` and `.md`. For
a run the report lists what each output's checks recorded and the held ones; for `files` with a source it is the
[check-all](#checking-many-documents) report over the source documents (it never writes the check history). The
manifest records:

| | |
| --- | --- |
| Package | `vixl_version`, `created`, the `inputs`, `naming`, `held`, `duplicates`, `totals`, the `outcome`, `validation` (coverage: files validated, needing review or with no required check, and the validated fraction) and `visual_review` |
| Each file | `name`, `sha256`, `bytes`, `format`, `source` (the document and its `revision`, the SHA-256 of the saved `.vixl`), `variant` (id, row, artboard), `export` settings (from `export_settings` by format), `check` (state and what validated it), `review`, `dimensions` (pixels, or `pt` and `pages` for a PDF), `color` (space, mode, alpha, ICC profile), `stream` (container, codec, fps, frames, duration, audio) read back from the encoded file, and a run's recorded `export_check` |

`decisions` takes the JSON a [proof page](#proof-pages) with `decisions: true` downloads (or its path): each file is
`approved`, `rejected` (held) or `pending`, and `visual_review` is `not_reviewed` without decisions, `pending`, or
`approved` once every packaged file is. `lock` is the render lockfile of the source document (or `{source: lockfile}`):
the package runs [`reproduce`](../../reference/agent-trust.md#reproduction) against it, re-encoding the exports it
recorded, and stores the compact `reproduction` summary; a failed check does not stop the package but fails its
`outcome`. The `outcome` is `needs_review` while anything is held, not fully validated or not visually reviewed, so a
written package is never read as an approved delivery by itself.

`dry_run` plans the names, duplicates and held list and writes nothing. The zip is staged and published atomically, its
entries have fixed timestamps, and an existing package is never replaced unless `overwrite: true`. A package inside the
folder being packaged is left out of itself.

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
`package.json` (the file list, settings and report). Files go through the same export path as `vixl_export(kind='batch')`.
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
`.pdf`, `.pptx` or `.html` (and the editable `.vixl` with `document`). See [brands](../layout/brands.md#brand-board).

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
writes and evictions (see [troubleshooting](../../troubleshooting.md#find-out-why-a-render-is-slow)).
Linked files and plugin effects bypass persistent caching; dependent groups are cached
at whole-frame level rather than incorrectly treating a group as an independent leaf.
There is no dirty-region compositor or GPU renderer.

Workflow `preview` takes `output` (.png), `quality` (draft/final) and optional `time`.

Library actions take a workspace-relative `directory`:

- `library-save`: name, description, tags. Saves a versioned, self-contained `.vixl` component.
- `library-search`: query. Matches all terms across name, description and tags.
- `library-open`: id, output. Opens an editable copy with its embedded assets and recipes.
- `library-place`: id, name, `as`. Inserts the component as an editable group of its layers (new IDs,
  with the fonts and images it uses); `as: "image"` inserts one raster snapshot instead.

The original library document remains editable. A placed component is an independent copy, not a live
cross-document symbol (link the component with `link` for that); a single object is reused the same way
with `object-save` / `object-place` (see [objects](../shapes/objects.md#save-and-place-editable-objects)). Components may hold isolated characters, masks, palettes,
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

Over MCP, `vixl_job(action='status' | 'result' | 'cancel', id=JOB, wait=SECONDS)` follows a durable job by its
32-character id from `submit`, as `status` and `cancel` do; `resume` stays a workflow action. The same tool follows the
in-memory job id (`{status: running, job}`) that any call returns when it runs past the inline limit (about 40 seconds)
or is sent with `as_job: true` ([long calls](../../reference/interfaces.md#long-calls-retries-and-progress)).

Job kinds:

- `production`: source, spec, output directory.
- `film`: spec, output ZIP/MP4/WebM.
- `generate`: source, explicit provider, request (prompt, width, height, optional model,
  negative_prompt, seed, strength and generate mode), output `.vixl`.
- `video`: explicit provider, request, output MP4/WebM (gateway contract below).
- `lyric-video`: request, output MP4/WebM ([lyric videos](../motion/lyric-video.md)).
- `form-fill`: source, request, output ([forms](../output/forms.md)).

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

Limits: 100 shots, 1,000 captions, eight audio tracks, ten minutes, 60fps, and 3,600 frames for ZIP output
(MP4/WebM stream frames and have no frame cap).
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

Without named suites, production runs the attached and inherited suites, or bounds and text-flow checks when there are none, and returns `needs_review` for failures rather than publishing clipped text; a clean output with no suite is `completed` with `outcome.state` `unvalidated`, because no suite validated it. Each result and the report carry an `outcome` ([outcome states](../../reference/agent-trust.md#outcome-states)). Every variant is also checked for leftover template copy (`placeholders`); a row that leaves a variable undefined, or draws placeholder copy, is `needs_review` with findings that name the variant and its input `row`. Add suites for the rest of the design contract. Unchanged runs reuse an output only when inputs, fonts, linked sources, settings and checks match and the output's SHA-256 still agrees. Layer caches use the user cache directory, not the deliverables directory.

The `app-animation-package` workflow packages named source documents, theme variables, explicit transitions, one-shot/looping behavior, reduced-motion PNGs and editable masters. Its generated manifest and standalone consumer are documented in [animation authoring](../motion/animation-authoring.md#app-animation-packages). Package outputs are new directories and external links must be frozen first.

Contrast checks reuse exact byte-channel transfer values rather than recalculating the sRGB power function for every pixel. The poster performance regression exercises the complete design check; expensive effects and complex documents can still cost more.
