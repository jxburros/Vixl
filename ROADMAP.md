# Vixl roadmap

This is the single development plan for Vixl. It replaces the development plan, the implementation plan, the craft
plan and the render-performance decisions that used to live in `docs/project/`; those files are kept, unchanged, in
`docs/project/archive/` as history and are no longer maintained. Everything needed to pick up an item is in this file.

The roadmap was rebuilt on 2026-10-31 against `main` at 0.33.1 and updated for 0.35.0 (stages 1-4 shipped). Every open GitHub issue was read, with its comments,
and checked against the code, the tests and the changelog; several bugs were reproduced. 112 issues that had already
shipped were closed with their evidence. The 51 issues still open, the remainders of closed issues, and the deferred
work that never had an issue are all below.

Issue numbers refer to `jxburros/vixl`. An issue is linked only in the "Close at the end of this stage" line of the stage
that finishes it; elsewhere it is named by number so its history can be found.

## Contents

1. How to use this roadmap
2. Rules for every change
3. Where Vixl stands
4. Owner actions and decisions
5. Stage 1: install path and quick correctness
6. Stage 2: checks that lead with a verdict
7. Stage 3: layouts that pass their own checks
8. Stage 4: token cost and the cheapest path
9. Stage 5: distribution, release wiring and hosting acceptance
10. Stage 6: cut-paper, motion and character animation
11. Stage 7: chart editing by data
12. Stage 8: rendering and export speed
13. Stage 9: interchange, fonts and accessibility
14. Stage 10: craft measurement
15. Stage 11: code structure
16. Stage 12: security hardening from the 2026-11-09 scan
17. Later and exploratory
18. Issue index

## 1. How to use this roadmap

- **Order.** Stages are in the recommended order. Stages 1 to 3 change what most users see first and should go in
  order. Stages 4 to 12 are largely independent and can be interleaved; each lists what it depends on. Stage 11 is
  mechanical refactoring and stage 12 is security hardening; both can run alongside anything.
- **Ratings.** Each item is rated for **complexity** (C1 a few hours, C2 about a day, C3 several days, C4 one to two
  weeks, C5 several weeks or open-ended) and **payoff** (P1 cosmetic or rare, P2 a narrow workflow, P3 a common
  workflow, P4 changes results for most agents, P5 first impression or correctness of output). Re-rate an item when it
  is picked up, and move it when its cost or value changes.
- **Item layout.** Each item gives the problem as it stands on 0.33.1, the remaining work as numbered steps with the
  modules to change, what "done" means (the regression tests), the docs to update, the rating, dependencies and any
  owner decision. File paths are given without line numbers; re-locate code when the item is picked up.
- **Closing issues.** Close an issue when the item that finishes it merges, with a comment naming the release and the
  tests. Each stage ends with the list of issues it closes. Trackers (#615, #535, #648) close when their last child
  does.
- **Keeping it current.** When an item ships, delete it from this file (the changelog is the record) and close its
  issues. When a new issue arrives, add it to the stage it fits, or to "Later", in the same pull request that triages
  it. Do not start a second plan file.

## 2. Rules for every change

These come from `CLAUDE.md`, `CONTRIBUTING.md` and the policies of earlier releases. They apply to every item below.

- **Plugin or core.** Decide before building and say which way it went in the pull request.
  - Core if the renderer, the document model or an exporter must know about it, other core modules need it, it changes
    what every document gets (a default, normalization or an always-on check), or it is part of the
    create/apply/check/render/export loop.
  - Plugin (`src/vixl/plugins/<name>/`, registered in `BUILTIN`) if it is self-contained, writes ordinary layers so
    documents still work without it, serves one domain, or brings its own heavy dependency, tool or network access.
    The core reaches plugins only through registry roles and hooks (`tests/test_plugins.py` fails on new direct
    imports); a missing hook point goes into `vixl.plugins.HOOKS`.
  - Content pack (the VixlPacks repository, fetched by `vixl.packs`, pinned by commit and SHA-256) for large data that
    only some features use.
  - Features that extend an existing plugin go in that plugin's package.
- **A regression test with every fix**, which fails without the fix.
- **Schema.** Every operation field has a type and a description (`schema.field(base, "text")`; shared constants are
  never mutated). Forgiving input and historical spellings are handled in `normalize.py` and reported under
  `normalized`. Opacity is 0-1 everywhere.
- **Targets.** Every new operation goes into the right set in `targets.py` (`EACH`, `JOINT` or one), and the table in
  `docs/reference/operations.md` is regenerated from `vixl.targets.markdown_table()`.
- **Exports agree.** SVG, PDF, PPTX and raster share the same fill and stroke rules; a change to one usually needs the
  others. Exports refuse to overwrite unless `overwrite=True`.
- **Defaults.** Pre-release, breaking changes are allowed and noted in the changelog. A default change must pass the
  house-style quality and diversity eval: run `python -m evals.house_style --compare evals/house-style-baseline.json`
  before and after; a change may not lower quality or diversity at any variety level.
- **New checks** land with craft-backtest numbers (`python -m evals.craft_backtest`): how many judged defects they catch
  and how many false findings they add.
- **Speed claims** are `pytest -m perf` time budgets in `tests/test_perf.py`, not assertions in prose. Parallel output
  must be byte-identical to one worker.
- **Goldens.** After an intended render change, regenerate with `VIXL_UPDATE_GOLDEN=1 pytest tests/visual`, review the
  PNGs and `git diff --stat`, and commit them with the change. Never update goldens to silence an unexplained diff.
- **Docs are executable.** `tests/test_docs_executable.py` runs the `vixl` commands and JSON operation blocks in
  `docs/` and `skills/`. Update the relevant `docs/*.md`, `skills/vixl/SKILL.md` and `skills/vixl/references/*.md`
  when behaviour, fields or defaults change, and grep for removed names.
- **Use-case catalog.** Add or move the row in `docs/use-cases.md` when a use case appears or its cost or blocked
  status changes.
- **Changelog.** Add every user-visible change to the current top section of `CHANGELOG.md`, with `(#NNN)` where an
  issue exists.
- **Versions** stay synchronized (`src/vixl/__init__.py`, plugin manifest, README release line, Dockerfile). The
  install pins (`.mcp.json`, the README and getting-started commands, the action pin in `docs/guides/automation/ci.md`)
  follow the newest published release: run `python scripts/published_pins.py --latest` with each bump. The self-updater and release manifest path (`src/vixl/updater*`,
  `distribution/`) stay stable.
- **No model names, signatures or authorship trailers** in code, docs, artwork or commit and PR text (but see the
  trailer-policy decision in section 4).
- **Showcases, films, marketing media and published eval results** live in the separate VixlExamples repository. Vixl
  never imports from it, downloads from it or tests against it.
- **Tests.** `pytest -n auto` runs the suite (about 4,900 tests); `-m perf`, `-m visual` (Linux only) and `-m docs`
  run the budgets, goldens and executable docs. In a fresh environment the first parallel run can fail while
  `tests/conftest.py` downloads the emoji pack; re-run.

## 3. Where Vixl stands

Releases 0.22 to 0.33.1 shipped the earlier plans in full:

- **0.22-0.24:** export parity and the QA sweep, house style as data with a quality and diversity eval, craft defaults,
  speed budgets, executable docs, text stages, spacing units and project packs.
- **0.25-0.26:** workspace checks, outcome states, located findings and `repair-layout`; declared objects with a kind
  taxonomy; tables, markdown decks, mockups, die-cut and logo tracing; brand presets; promo video templates; archive
  load budgets.
- **0.27:** the seven-tool MCP surface, the published `.vixl` format, editable SVG/PDF/Figma import, render parity, and
  every craft-plan item (composition checks and repair, the finishing pass, balanced wrap, tab stops, components,
  atmosphere effects, motif registry, tool finish).
- **0.28:** security hardening (untrusted-input budgets, network policy, REST and token hardening, restricted decoders,
  SHA-pinned workflows), governance files, check-noise fixes, capped apply results, a 10 KB agent skill.
- **0.29:** per-document locks, default call limits and a hard timeout, cheaper applies, a core operation registry,
  strict types on the core leaves, a render pool, incremental lit scenes and parallel frame ranges.
- **0.31:** the craft remainders (small caps, hanging punctuation, accent words, hierarchy findings, variations, accent
  counts, brief-weighted palettes, flex and grid stacks, recomposing `adapt-layout`, fog and motifs, illustration
  defaults, Noto Sans as the proofing face); objects (build knowledge, `object` check, outline policy, `object-plan`);
  brand packages; merch; character packages; render lockfiles; deliverable packages.
- **0.32:** checks and automation across documents (suite references, budgets, post-export checks, approvals, link
  impact, locale and spelling checks, pipelines, webhooks, watch, data sync, localization, bulk upgrades); `vixl host`
  for AI Server Studio; fonts installed on the machine by name.
- **0.33-0.33.1:** appearance-preserving ungroup, nested animation instances, lyric per-cue compositions, aligned lyric
  timing and verified delivery, shared datasets, the drawing finish, Figma interchange, Lottie export with source easing
  and linked-instance timing, and export-speed items 1-6 and 8.

- **0.33.3-0.35.0:** install pins that follow the published release (stage 1); checks that lead with a verdict
  (stage 2); layouts that pass their own checks, `font-pair apply_to`, reflowing repairs and `layout-apply update`
  (stage 3); the one-call route, scoped references, paged inspection, proposals, authoring shortcuts and a planner
  that sends brief schemas (stage 4).

What is left falls into four kinds of work: release wiring (the container image, signing and directory listings are
undone); the layout exceptions and the paid measurement runs left from stages 3 and 4; the cut-paper, motion and chart
workflows reported in late October need new features; and several shipped features were never exercised for real
(container image, Windows host task, live Figma, the craft re-judge).

## 4. Owner actions and decisions

These need the owner (accounts, keys, money, legal wording or a product call). Most of them unblock an item below; the
item names the decision it waits on. They can be taken at any time and need no code.

### Accounts, keys and settings

| Action | Unblocks | Notes |
| --- | --- | --- |
| Publish 0.33.x to PyPI (approve the `release` environment) | #543 release check, #753, #771 | PyPI's latest is 0.32.0; since 0.33.3 the install pins follow it, so they resolve, but new users get 0.32.0 until a release |
| Enable GitHub private vulnerability reporting (Settings, Security, Advisories) | Governance remainder in stage 5 | `SECURITY.md` sends reporters there, but the API reports it disabled |
| Confirm the `release` environment has required reviewers | #678 | The release workflow uses the environment; `docs/reference/releases.md` "Release rhythm and soak" still calls approval an open decision, which contradicts CONTRIBUTING.md |
| Create a primary and a backup Ed25519 update-signing key; store the primary as `VIXL_UPDATE_SIGNING_KEY` in the `release` environment and keep the backup offline | #756 | Signing code exists in history (backed out in 0.30.1 because no key existed) |
| Point the PyPI Trusted Publisher at `release.yml` (or publish from a non-reusable workflow) | #756 (attestations) | PyPI refused attestations because `release.yml` calls `pypi.yml` as a reusable workflow |
| Claim the `vixl` name on PyPI (currently free) and add a trusted publisher | #753 | A tiny meta-package depending on `vixl-engine` |
| Turn on branch protection on `main` with one required review; add CODEOWNERS | #678 | Or accept the current rules as conventions and close the enforcement part as not planned |
| Make the ghcr package public after the first container push | #546 | |
| Commit `fonts/cjk.zip` and any `spelling-<lang>` lists to VixlPacks | #419 remainder, #554 remainder (stage 9) | Vixl pins the commit and SHA-256 |
| Run a live Figma desktop session with the import plugin | #662 | Three fixtures; see stage 9 |
| Open a Vixl PSD in Photoshop or Photopea | #514 acceptance | Can share the session with the Figma check |
| Supply one or two real AI Server Studio Design Profiles | #545 remainder | |
| Submit the `.mcpb` to the Claude extension directory and list Vixl in MCP directories | #771 | |

### Product and policy decisions

| Decision | Item | Recommendation |
| --- | --- | --- |
| Authorship-trailer policy: make the advisory CI check blocking and configure agent tooling to omit trailers, or allow standard `Co-Authored-By` trailers in commit metadata only | #692 part A | Either is fine; the docs and the CI check must agree. 50 of 189 commits since 2026-10-20 carry trailers |
| Rewrite history to purge dead media (about 600 MB pack for a 31 MB tree) | #692 part B | Do it once, after every open PR is merged or closed, with a mirror backup and an announcement |
| Release cadence (12 releases in 11 days against a documented weekly rhythm with a soak) | #678 | Follow the documented rhythm, or rewrite it to match what is wanted |
| DCO or CLA for contributions; licence notice wording; the commercial-licence contact and process | Governance remainder, #774 | Counsel approves any change to the LICENSE notice line; never edit the PolyForm body |
| Whether docs name competitors (template APIs, design tools) | #772 | Qualitative comparison, no prices |
| Font role tokens on layers (`font: "@heading"`) as a document-model concept | #766 | Ship `apply_to` first; decide tokens later |
| Recommended sizes per layout: curated or derived from `best_for` | #764 | Derived, with curated overrides |
| Pattern texture as an effect on its base layer (document-model change) or a linked sibling | #747 | Effect on the base layer |
| Additive tracks stored in the document or compiled to keys | #750 | Stored and summed at render |
| Whether stop-motion jitter may become a translated cached raster (a pixel change) | #754 | Yes, with reviewed goldens |
| Pixel tolerance for glyph reuse (subpixel quantisation) | #584 | Decide only after the binding route in stage 8 |
| Carry and ship a native rasteriser binding (frozen-build cost) | Stage 8 binding item | Ask resvg_py upstream first |
| Raise the pixel limit for tiled renders | #588 | Decide after measuring |
| Machine-dependent hardware video encoding, opt-in | Stage 8 encoder item | Opt-in and recorded in the export result only |
| A browser (Playwright) dev dependency for a lottie-web check, or rlottie as the reference player | Stage 9 Lottie item | rlottie in CI first |
| `psd-tools` as an optional dependency if the hand-written PSD reader stalls | #514 | Hand-written reader first |
| Colour fonts preferred over the VIXL Line emoji library when both exist | #721 | Keep VIXL Line the default for emoji |
| iMessage stickers in scope (needs an Xcode project) or a PNG/APNG folder with instructions | #722 | Folder with instructions |
| Optical sizes (`opsz`) supported or recorded as not planned | Stage 3 typography item | Not planned unless a catalog face is variable |
| Curated offline font set: which serif, sans and display faces; bundled or a pack | Stage 9 fonts item | A pinned pack if over a few MB |
| Whether tagged PDF becomes the default once stable | #719 | Opt-in first |
| Fund the blind craft re-judge, the tool-call comparison and the competitor lanes (paid agent runs and judges) | #648, #628, #615, #773 | Run once before and once after stage 4, in one budget |
| Run a public hosted MCP service at all, who operates it, and the allowance model | #770 | Decide before any hosted-only engine work |
| Build the optional previewer, and how far (view only, review aids, notes, light edits) | #775 | Steps 1-3 only if pursued |
| Windows: accept the per-user scheduled task or also build a machine-wide service; agree Studio's detection path | #547 | Per-user task, with Studio detecting `%LOCALAPPDATA%` |
| Whether the release workflow triggers the container build | #546 | Yes, after the PyPI job |
| Linear-time regex engine (`google-re2`, optional dependency) or a restricted pattern syntax for service callers | 12.4, #825 | `google-re2` optional, restricted syntax as the fallback |
| Whether service (REST/MCP/Host) SVG imports install fonts by default | 12.2, #819 | Off for service callers, on for the CLI |
| Bump `CURRENT_SINCE` in the conversion kit (documents saved by 0.27-0.30 redraw in Noto on next edit; stored layouts use the old `optional` tag) | Release decision | At the next minor release |

## 5. Stage 1: install path and quick correctness

Shipped in 0.33.3: install pins that follow the newest published release with a CI check that they resolve (#762),
the host API schema in the release inventory (#543), the escaped-variable check crash (#776), the untrusted-input
leftovers of #667 and #676, readable history on the review page (#714 F09), the QA-20 correction and the move of
issue numbers out of the use-case catalog (#686 remainder). The release workflow does not advance the pins itself:
every change to `main` must advance the version, so a commit made by the workflow would need its own bump; the
version-bump step runs `scripts/published_pins.py --latest` instead.

Two follow-ups remain, both after the next release:

- Confirm that the GitHub release lists `vixl-host-api.schema.json` and that it equals `vixl host --schema`, then
  close #543.
- Run `python scripts/published_pins.py --latest` once 0.33.x is on PyPI, so new users get it.
- Optional, from the old docs item: split the 577-word per-layer edit list in `docs/reference/architecture.md`.

**Close at the end of this stage:** [#762](https://github.com/jxburros/vixl/issues/762),
[#776](https://github.com/jxburros/vixl/issues/776), [#543](https://github.com/jxburros/vixl/issues/543) (after the
release check above).

## 6. Stage 2: checks that lead with a verdict

Implemented for 0.34.0 (release pending): verdicts and grouped findings (#725), revision-bound export check status
and strict delivery (#724), inherited and named library suites (#726), honest repair proposals (#765), compact
choice errors (#767), word-break/contrast/print-screen fixes (#720), and export quotes (#769).
The full issue list stays available for compatibility. Export status uses cached checks; strict export runs fresh
checks. Quotes leave encoded byte size unknown and report static raster fallback estimates.

Close #725, #724, #726, #765, #767, #720 and #769 when this stage merges.

## 7. Stage 3: layouts that pass their own checks

Shipped in 0.35.0: dead bands under airy spacing and the stack helper for `f-pattern` and `story-vertical` (3.1,
#680 remainder), the event-poster height distribution and motif rule (3.2, #763), recommended sizes per layout with
`tests/test_layout_quality.py` as the gate (3.3, #764), `font-pair apply_to` with layout text on the heading and body
roles (3.4, #766), the grow-then-fit overflow repair and `layout-apply update: true` (3.5, #768), and body text
wrapping `pretty` by default with the eval unchanged (3.6, #652 remainder; hanging punctuation stays opt-in and optical
sizes are not planned).

What remains is the gate's exception list: 31 of 204 layout × size pairs, each with an issue, to be fixed in the
layouts named there and removed from `EXCEPTIONS` as they pass:

- [#803](https://github.com/jxburros/vixl/issues/803) `rule-of-thirds` (bands around the focal point, subtitle contrast)
- [#804](https://github.com/jxburros/vixl/issues/804) `golden-section` (minor-section bands on letter and story)
- [#805](https://github.com/jxburros/vixl/issues/805) `z-pattern` (headline-to-body band, web-banner overflow)
- [#806](https://github.com/jxburros/vixl/issues/806) `split-screen` (story bands, square hierarchy, thumbnail minimum)
- [#807](https://github.com/jxburros/vixl/issues/807) `banner` and `photo-caption` on a cover (no focal point)
- [#808](https://github.com/jxburros/vixl/issues/808) `editorial-grid` (short example body on a page)
- [#809](https://github.com/jxburros/vixl/issues/809) `emblem`, `price-list`, `big-number` (centred-line drift)
- [#810](https://github.com/jxburros/vixl/issues/810) `minimal-mark` (hierarchy step at seed 2)
- [#811](https://github.com/jxburros/vixl/issues/811) `slide-content` (band before the footer)
- [#812](https://github.com/jxburros/vixl/issues/812) `asymmetric-balance`, `hero-statement` (top edge band)
- [#813](https://github.com/jxburros/vixl/issues/813) `photo-caption` on a story (scrim taller than its copy)
- [#814](https://github.com/jxburros/vixl/issues/814) `business-card` seed 1, `typographic-poster` cover caption

Later (owner decision): font role tokens on layers (`font: "@heading"`), a document-model change; `apply_to` shipped
first. Rating for the remainder: C2, P3 each.

**Close at the end of this stage:** [#763](https://github.com/jxburros/vixl/issues/763),
[#764](https://github.com/jxburros/vixl/issues/764) (the gate exists; the exception issues track the rest),
[#766](https://github.com/jxburros/vixl/issues/766), [#768](https://github.com/jxburros/vixl/issues/768).

## 8. Stage 4: token cost and the cheapest path

Shipped in 0.35.0: the harness token fields and the offline baseline (4.1 steps 1-2), the one-call route first with a
tiered finishing pass and `suites` on create (4.2), the cheap payload wins (4.3), scoped references with brief schemas,
dot paths, reachable definitions, ranked capabilities and `schema_version` / `if_version` (4.4), results and inspection
(ack detail, generated children at the parent, inspect paging and projection, `since`, `report_path`, proposals; 4.5),
batch export preflight and container/template reference specs (4.6), the authoring shortcuts (`defaults`,
`create-many`, structured `slides`, entrance/hold/exit presets, `container-rows`, pixel run lengths, mirror and frame
deltas; 4.7) and the planner shortlist, scoped document, image modes, guidance filter, stable order and cache reporting
(4.8). See the 0.35.0 changelog for the measured shrinks.

What remains needs the owner's paid runs:

### 4.1 Live baseline (#615 step 1, #628 step 4)

- **Remaining work:** re-run the tool comparison (the VixlExamples kit: 16 briefs, three lanes, same model and settings),
  recording round-1 tool calls, minutes, tokens (input, output, cache read) and hard checks, and
  `python -m evals.token_baseline --agent claude` for live token counts (the committed baseline holds character
  counts from an offline replay with `tokens_total` null). Publish in VixlExamples, then tighten `tool_call_budgets`
  in `evals/baseline.json`.
- **Done when:** the baseline file carries live token counts and the budgets are tightened.
- **Rating:** C1, P4. **Depends on:** the paid-run decision.

### 4.9 After-measurement

- Re-run 4.1 with live agents (not replay) and report characters against tokens, cache against context, and schema
  against end-to-end savings. Publish in VixlExamples and link it from `docs/reference/agent-discovery.md`.

Items of #615 done: 01-10, 12-36, 39-41, 43, 48, 51-55, 57, 58, 60, 62. Items covered by shipped work elsewhere: 11 and
45 (responsive adaptation, localization, data sync), 37, 38 and 61 (located findings and repairs), 42 (tab stops), 44
(finishing components), 46, 47 and 50 (object build knowledge and `object-plan`), 49 (shared datasets), 56 (nested
animation instances), 59 (the 10 KB skill), 63 (compact visual feedback), 64 (the craft grader plus 4.1).

**Close at the end of this stage** (after 4.9): [#628](https://github.com/jxburros/vixl/issues/628),
[#615](https://github.com/jxburros/vixl/issues/615).

## 9. Stage 5: distribution, release wiring and hosting acceptance

Several shipped distribution pieces were written but never run (the container workflow has zero runs, the Windows host
task path is never exercised, the host schema never reached a release), the package name is hard to guess, and the
governance rules and practice disagree. Most items need an owner action from section 4; the code parts are small.

### 5.1 A package name agents can guess (#753)

- **Problem:** agents in fresh containers try `pip install vixl`, which fails, and fall back to cloning the repository.
- **Remaining work:**
  1. Docs, no owner action: a plain `python -m pip install vixl-engine` line near the top of the README and
     `docs/getting-started.md`; in SKILL.md and `skills/vixl/references/cli.md` ("Finding vixl"), a row "not installed:
     `pip install vixl-engine` (the import and the command are `vixl`)". `tests/test_docs_executable.py` must not run it
     (network).
  2. Owner: register `vixl` on PyPI as a meta-package that depends on `vixl-engine` at the same version, published by
     `pypi.yml` beside the main package. If PyPI refuses the name, drop this step.
- **Done when:** a docs test asserts the README's first install block contains `vixl-engine`; if the name is claimed,
  `pip install vixl` installs `vixl-engine`.
- **Docs:** README, getting-started, SKILL.md, the CLI reference, the meta-package in `docs/reference/releases.md`.
- **Rating:** C1, P4. **Depends on:** none (the install pins shipped in 0.33.3).

### 5.2 One-click agent install, directories and macOS (#771)

- **Problem:** getting from "heard of Vixl" to "my agent uses it" takes uv plus a guessable package name, the Windows
  installer or a source checkout. A `.mcpb` desktop extension is published with releases (since 0.32.0), but there is no
  directory listing, no MCP registry entry, no macOS installer and no per-client install table.
- **Remaining work:**
  1. README "Install for your agent" table: Claude Desktop (`.mcpb`), Claude Code plugin, Cursor, VS Code, Codex; each
     snippet checked by `tests/test_docs_executable.py` (configuration shape, no network) or the packaging test.
  2. A `server.json` for the official MCP registry, published from `release.yml` after PyPI.
  3. macOS: a Homebrew tap formula (`vixl-engine` in a virtualenv) updated by the release workflow, or a signed and
     notarised `.pkg` (needs an Apple Developer ID); document the update path to match Windows.
  4. Owner: submit the `.mcpb` to the Claude extension directory and list Vixl in the common MCP directories.
- **Done when:** the README table exists and is tested, the registry entry resolves to the current version, and
  `brew install jxburros/vixl/vixl && vixl --version` works on a CI macOS runner.
- **Docs:** README, getting-started, `docs/reference/releases.md`, the CLI reference (finding vixl on macOS).
- **Rating:** C3, P5. **Depends on:** 5.1; owner decisions on directories, the Homebrew tap repository and signing.

### 5.3 Container image built and published by releases (#546)

- **Problem:** `ghcr.io/jxburros/vixl:<version>` does not exist, so AI Server Studio's Docker Compose profile has
  nothing to pull. `distribution/container/Dockerfile` (uid 10001, `/data`, read-only-ready, healthcheck) and
  `.github/workflows/container.yml` (build, smoke test, push on tag, `workflow_call`, `workflow_dispatch`) were written
  without Docker and have never run: the workflow has zero runs, `release.yml` does not call it, and its `push: tags`
  trigger never fires because releases are created with `GITHUB_TOKEN`. The base image is pinned by tag, not digest.
- **Remaining work:**
  1. Add a `container` job to `release.yml` after the `pypi` job (`uses: ./.github/workflows/container.yml` with the
     release version and `permissions: packages: write`); the image installs the published `vixl-engine`, so it must
     follow the PyPI publish.
  2. Run `container.yml` once through `workflow_dispatch` with `push: false` on the current release and fix what the
     first real build and the read-only smoke test (`/host/info` with the token, a compose plus PNG export) reveal.
  3. Pin `python:${PYTHON}` by digest, as actions are pinned, and add it to the dependency-update process.
  4. Owner: after the first push, make the package public and link it to the repository.
  5. Keep `ARG VERSION` in the version-sync list and its test.
- **Done when:** a release produces `VERSION` and `VERSION-full` images whose smoke test passed in CI, and
  `docker run --read-only -e VIXL_HOST_TOKEN=… ghcr.io/jxburros/vixl:VERSION` answers `/host/health`.
- **Docs:** the container section of `docs/reference/releases.md` (how it is triggered), the pull command under
  Hosting in `docs/reference/interfaces.md`, changelog.
- **Rating:** C2, P3. **Depends on:** the owner decision that releases trigger it.

### 5.4 Windows host task exercised on Windows (#547)

- **Problem:** the installer's `studiohost` task (`distribution/windows/vixl.iss` plus `host-task.ps1`) registers a
  per-user scheduled task with `%LOCALAPPDATA%\Vixl\host.json` and a token file, the updater restarts it, and the
  uninstaller removes it, but only unit tests with mocked `schtasks` cover it: the host-task path in
  `distribution/test_windows_install.ps1` runs only with `VIXL_TEST_HOST_TASK=1`, which no workflow sets. The issue
  asked for a Windows service and `%ProgramData%\Vixl\host.json`; which location Studio detects is unconfirmed.
- **Remaining work:**
  1. Owner: accept the per-user task (no admin, runs while the user is logged on) or also build a machine-wide service
     (NSSM/WinSW or a pywin32 wrapper, an admin-only installer task, `%ProgramData%\Vixl\host.json` with ACLs for the
     service account, updater restart through `sc stop/start`).
  2. Agree the detection path with AI Server Studio; if needed write both locations or a pointer file.
  3. Set `VIXL_TEST_HOST_TASK=1` in the `windows` job of `release.yml` (windows-latest can register per-user tasks), or
     run the manual checklist on a clean non-admin account and record the result in `docs/reference/releases.md`.
  4. Confirm a real `vixl update` restarts the task on the new version (`GET /host/info`).
- **Done when:** install, health with and without the token, update restart and uninstall cleanup run on Windows in CI
  or a recorded manual run, and Studio detects the host.
- **Docs:** "Vixl host for AI Server Studio" in `docs/reference/releases.md` (drop "not confirmed"), changelog.
- **Rating:** C2 (task only) or C3 (with a service), P2. **Depends on:** Studio's detection code.

### 5.5 AI Server Studio integration acceptance (remainders of #544 and #545)

- **Problem:** the `studio` AI provider (`src/vixl/plugins/ai/studio_provider.py`) speaks a wire format Vixl proposed
  (`POST URL/v1/<capability>`, documented in `docs/reference/providers.md`) because Studio has not published its
  provider-gateway contract; if Studio's differs, every AI command through `vixl host` fails at integration time. The
  Design Profile mapping (`src/vixl/plugins/brand_kit/design_profile.py`) and its only fixture follow a description of
  Design Profile v2, not a real exported profile, so real field names may land under `unmapped`.
- **Remaining work:**
  1. When Studio publishes its gateway contract, diff it against the `studio` section of `providers.md` and adjust
     paths, field names, image encoding, error codes and the call-context header; vendor the contract as a fixture and
     validate the fake gateway against it in `tests/test_studio_provider.py`.
  2. Owner: one live Studio → Vixl → gateway → Vixl generate/describe round trip from a `vixl host` launched by Studio.
  3. Add one or two real, anonymised Design Profiles under `tests/fixtures/design-profile/`, run
     `vixl brand import --design-profile` on them, and fix mapping gaps while keeping `unmapped` honest; validate exports
     against Studio's profile schema if one is published.
- **Done when:** the provider tests validate against Studio's contract, one live round trip works, and real profiles
  round-trip with only intentional `unmapped` paths and the brand checks fire on a violating design.
- **Docs:** drop the "proposal" wording in `providers.md`; replace "No public Design Profile schema exists" in
  `docs/guides/layout/brands.md`.
- **Rating:** C2, P3. **Depends on:** AI Server Studio publishing its contracts; owner samples.

### 5.6 Signed Windows updates (#756)

- **Problem:** the Windows self-updater takes the expected SHA-256 from `vixl-update.json` in the same GitHub release as
  the runtime ZIP, so anyone who can publish a release (a leaked token or a compromised CI job) can ship a matching
  manifest and payload and get code execution on every auto-updating install. The updater also runs the downloaded
  `vixl-engine.exe` (`probe`) before activating it. Signing was built (908cd41) and backed out in 0.30.1 because no key
  existed. PyPI uploads also carry no attestations.
- **Remaining work:**
  1. Owner: create the keys (section 4).
  2. Revert 03710a5 to restore `src/vixl/updater_sign.py` (a dependency-free RFC 8032 verifier, because the launcher
     freezes `updater.py`), `distribution/sign_manifest.py`, the signing step in the `release.yml` `publish` job and
     `min_launcher`; pin both public keys in `TRUSTED_KEYS`, primary first.
  3. Re-add `vixl-update.json.sig` to the `.release/config.json` assets and its assertion in
     `tests/test_error_messages.py`.
  4. Keep the release guard that refuses to publish while `TRUSTED_KEYS` is empty, but only after step 1, so it cannot
     block releases again; do a `dry_run` release before a real one.
  5. Restore PyPI attestations (owner Trusted Publisher change, then remove `attestations: false`).
  6. Optional later: an Authenticode check on `vixl-engine.exe` before `probe()`, once the installer is signed.
  Keep `src/vixl/updater*` and the manifest path stable.
- **Done when:** `tests/test_updater.py` has unsigned, tampered, wrong-key and valid-signature cases plus the RFC 8032
  vectors; `distribution/test_native_update.py` signs with a test key; a dry-run release produces
  `vixl-update.json.sig` and a real release publishes with it.
- **Docs:** restore "Update signing" in `docs/reference/releases.md` (key custody, rotation through `min_launcher`,
  the backup key), the updater paragraph in `docs/reference/architecture.md`, changelog, `SECURITY.md` scope if needed.
- **Rating:** C2, P4. **Depends on:** the owner keys.

### 5.7 Licence clarity, "is Vixl a fit?" and governance settings (#774, #714 finding F10, remainder of #683)

- **Problem:** on the download path, "free" reads as free for everyone and "source available" as open source, and a
  larger company has no route to a licence. The README licence summary ("fewer than 100 people and under US$1M (2019)
  revenue") does not say both thresholds must hold or that the figure is CPI-adjusted, and the LICENSE `Required
  Notice` has no contact. The adoption constraints found in the 0.27.0 audit are scattered: no bundled model weights (AI
  needs a provider); 8-bit sRGB only, with no RAW, high bit depth, spot colours or trapping; licence eligibility; pip
  installs update through pip and the self-updater is Windows-only; older documents need `vixl convert`. `SECURITY.md`
  points at private vulnerability reporting, which is disabled, and the inbound licence for contributions (DCO or CLA)
  is undecided.
- **Remaining work:**
  1. A short "Who can use Vixl for free" block near the README top and in getting-started, with a one-line FAQ ("Is
     Vixl open source? No: source-available under PolyForm Small Business"), stating both thresholds as cumulative
     (fewer than 100 total employees and contractors and under US$1,000,000 revenue in the prior tax year, in 2019
     dollars adjusted for CPI-U).
  2. Show the licence in the Windows installer (`LicenseFile=` in `vixl.iss`) and in the release-notes template; check
     that the `.mcpb` manifest carries the licence identifier.
  3. A commercial-licence page (for example `docs/reference/licensing.md`) with the contact route (owner).
  4. An "Is Vixl a fit?" section in getting-started, linked from the README, listing each constraint above with its
     reference page, and a `docs/use-cases.md` row "print/photo professional pipeline" marked partial or blocked.
  5. Owner: enable private vulnerability reporting; choose DCO or CLA. For a DCO, add a `Signed-off-by` check to
     `pr-hygiene.yml` and a line in CONTRIBUTING and the PR template; for a CLA, add a CLA bot. Counsel approves any
     change to the LICENSE notice line; the PolyForm body is never edited.
  6. When a hosted service happens: terms stating that outputs belong to the user and that the software licence governs
     the software, not the designs.
- **Done when:** the README top, getting-started, installer and release notes say who can use Vixl free and how to get
  a commercial licence; a docs test asserts the README top section links to `LICENSE`; the vulnerability-reporting API
  reports enabled; CONTRIBUTING states the inbound terms.
- **Rating:** C1, P3. **Depends on:** owner and counsel.

### 5.8 Repository hygiene and the review process (#692, #678)

- **Problem:** (a) commits keep violating the no-trailer rule because agent tooling appends trailers by default and the
  CI check is advisory. (b) Every clone (CI, agents, cloud sessions, the `fetch-depth: 0` checkouts in
  `pr-hygiene.yml` and `pr-size.yml`) downloads about 600 MB of history for a 31 MB tree; the large art and marketing
  binaries already moved to VixlExamples, so only history remains. (c) Change volume and cadence exceed what one person
  can review: a release roughly every day, many large agent-authored pull requests, and no required second review.
- **Remaining work:**
  1. Trailer policy (owner): make the advisory check blocking and configure agent tooling to omit trailers, or reword
     CONTRIBUTING.md and the `CLAUDE.md` rules to allow standard `Co-Authored-By` trailers in commit metadata and drop the
     hook sample and the check. Do not rewrite past commits for trailers alone.
  2. History purge (owner, once): merge or close open pull requests and announce a freeze; take a
     `git clone --mirror` backup and confirm VixlExamples holds everything the docs link to; run
     `git filter-repo --analyze` and build `purge.txt` (`marketing/`, `art/`, `explorations/`, `promo/`, `movie/`,
     `evals/tool-comparison/**/packages/`, `eval-results/**/*.zip`, `src/vixl/data/emojis/artwork.zip`); run
     `git filter-repo --invert-paths --paths-from-file purge.txt` on the mirror; check that each `v*` tag still builds
     (`pip wheel .`) and that the updater and release manifest paths are unaffected; force-push branches and tags, ask
     GitHub Support to collect cached pull-request refs, and have contributors re-clone.
  3. Add `tests/test_repo_hygiene.py`: no tracked file over 5 MB outside an allow-list (fonts in `src/vixl/data`), and a
     cap on the total size of `tests/visual/golden`.
  4. In `pr-size.yml` and `pr-hygiene.yml`, replace `fetch-depth: 0` with a shallow fetch of base and head.
  5. Review process (owner): branch protection on `main` with one required review (or a required review attachment
     where no second human exists); `.github/CODEOWNERS` for `src/vixl/fetch.py`, `src/vixl/interfaces.py`,
     `src/vixl/updater*`, `distribution/` and `.github/`; confirm the `release` environment has required reviewers and
     update "Release rhythm and soak" in `docs/reference/releases.md`; decide whether `pr-size.yml` fails above a
     threshold with a `size-justified` override label; follow the documented cadence or rewrite it.
- **Done when:** CONTRIBUTING, `CLAUDE.md` and the CI check agree and new commits match them; a fresh clone's pack is
  under about 60 MB and the hygiene test passes; branch protection shows a required review, CODEOWNERS exists, and
  `releases.md` and CONTRIBUTING match the settings. If the owner keeps the rules as conventions, close the enforcement
  part as not planned.
- **Docs:** CONTRIBUTING.md (policy, cloning note), `CLAUDE.md` rules, `docs/reference/releases.md`, a release-notes
  line about rewritten history.
- **Rating:** C1 (policy) and C3 (purge), P3. **Depends on:** owner decisions.

### 5.9 Vixl as a local alternative to template-rendering APIs (#772)

- **Problem:** people paying per render for hosted template APIs have no path to Vixl's local equivalent, and the docs
  do not say Vixl does this job.
- **Remaining work:**
  1. `docs/guides/automation/template-api-migration.md`: rebuild a typical hosted template (named layers, text and image
     slots) as a Vixl template, fill it from a CSV, adapt it to three sizes, check it and batch-export, with every command
     runnable under `tests/test_docs_executable.py` and a small CSV fixture in the docs folder.
  2. A `docs/use-cases.md` row ("replace a hosted template API with a local batch") and a sentence and row in the README's
     "What you can make".
  3. Templates for OG images, product cards, certificates, quote cards and event tickets: check which exist as layouts
     and add the missing ones (an event ticket, a dedicated OG card) as core layouts if small, or a content pack if they
     bring assets.
  4. Keep the comparison qualitative and without prices; marketing pages and media go to VixlExamples.
- **Done when:** the guide runs end to end in the docs tests and the use-cases row exists.
- **Rating:** C2, P3. **Depends on:** the owner decision on naming competitors.

**Close at the end of this stage:** [#753](https://github.com/jxburros/vixl/issues/753),
[#771](https://github.com/jxburros/vixl/issues/771), [#546](https://github.com/jxburros/vixl/issues/546),
[#547](https://github.com/jxburros/vixl/issues/547), [#535](https://github.com/jxburros/vixl/issues/535) (the hosting
epic, once #543, #546 and #547 are closed), [#756](https://github.com/jxburros/vixl/issues/756),
[#774](https://github.com/jxburros/vixl/issues/774), [#692](https://github.com/jxburros/vixl/issues/692),
[#678](https://github.com/jxburros/vixl/issues/678), [#772](https://github.com/jxburros/vixl/issues/772).

## 10. Stage 6: cut-paper, motion and character animation

All but the last item come from one build, a cut-paper unicorn in a parallax scene, and they share code paths in
`scene.py`, `textures.py`, `timeline.py` and the motion check. Order: the two reproduced bugs (6.1, 6.2), the small
check fix (6.3), the speed fix (6.4), then the new features (6.5-6.7). 6.6 should land before 6.7. 6.8 is independent.

### 6.1 Cut-paper grain renders as scanline streaks (#748)

- **Problem:** at the recommended `grain` of 0.04-0.08, large cut-paper pieces such as sky or hills look like TV
  scanlines (reproduced: row-mean spread 7.24 against 1.64 for columns). The only fixes are turning grain down to almost
  nothing or bringing in a texture tile made elsewhere.
- **Remaining work (core, `scene.py`):**
  1. In `scene.paper_image`, replace the per-row term with low-frequency mottling (seeded value noise at `grain_scale`,
     upsampled and tileable) and short fibres at random angles (`fibers: {count, length}`), drawn as short soft strokes,
     keeping the fine per-pixel grain.
  2. Add optional `grain_scale`, `fibers` and `pattern` (reusing a `pattern-define` tile) to the `cut-paper` schema, each
     with a type and description; defaults give paper-like output.
  3. Seeded and deterministic, and stable across the frames of one hold.
- **Done when:** on a flat sheet the row-mean and column-mean variances are within 1.5× of each other; the same seed
  gives the same pixels; cut-paper goldens are regenerated and reviewed (an intended render change, noted in the
  changelog).
- **Docs:** the `cut-paper` text in `guidance.py`, the cut-paper sections of the finishing and drawing guides, skills
  references.
- **Rating:** C2, P2. **Depends on:** none.

### 6.2 `pattern-fill` texture does not follow its animated base layer (#747)

- **Problem:** a texture added with `pattern-fill` is a sibling layer, so when the base layer is animated the texture
  stays where the base started and turns into a ghost (reproduced: the stripes stay behind, 68 px apart). The
  workaround is a group per textured piece, and texturing about 150 pieces doubled the scene to about 314 layers.
  `drawn-texture` uses the same sibling-overlay pattern (`textures.py`).
- **Remaining work:**
  1. Option A (recommended, also stops the layer count doubling): store the pattern on the base layer as a fill
     attachment or effect (`pattern_overlay: {pattern, transform, opacity, blend}`), drawn in the layer's own frame by
     `render.layer_effects` before flip, rotate and skew, as all effects are. Option B: keep the sibling but have it
     inherit the base's transform tracks at render (a `follows: base_id` link resolved in `timeline.project_at`). Owner
     decision; A changes the document model.
  2. The same for `drawn-texture`.
  3. Export parity: SVG pattern fill, PDF tiling or raster fallback, PPTX picture fill.
  4. Leave existing sibling layers alone; optionally offer a conversion-kit migration.
- **Done when:** the issue's batch rendered at 1000 ms has the stripes inside the rotated silhouette (a pixel test in
  the rotated region), the motion check reports nothing, and under option A texturing N pieces adds no layers; a visual
  golden.
- **Docs:** the texture pages under `docs/guides/finishing/`, the grouping note in the motion guide, skills references,
  changelog.
- **Rating:** C3, P3. **Depends on:** the A/B decision.

### 6.3 Motion check accepts seamless scrolls and symmetric rotations (#752)

- **Problem:** the parallax scene gets 8 false warnings and `needs_review`, and following the check's own advice snaps
  the strips back. Spin rotations are already recognised (`_full_turns`), but a strip that scrolls exactly one repeat
  per loop is flagged as a loop seam, and `symmetry` is not accepted on `keyframes` rotation tracks.
- **Remaining work (core):**
  1. Add an explicit `wrap` (period in property units) to `keyframes`, `keyframe` and `animate`, stored on the track
     like `symmetry`; allow `symmetry` on `keyframes` rotation tracks.
  2. `timeline.seam_matches` compares numeric tracks modulo `wrap`; `close_track` leaves wrapped tracks alone.
  3. `motion.findings` skips `linear-motion` for a constant-speed track that covers the whole loop with `wrap` or
     `symmetry`; generalise `_full_turns`.
  4. Optional: infer `wrap` when a group's children repeat at exactly the moved distance, or add a `motion` `scroll`
     recipe that writes it.
  5. The `loop-seam` message suggests `wrap` when the distance is a whole repeat.
- **Done when:** a strip scrolled 1200 px with `wrap: 1200`, and a 12-ray sun rotated 30° with `symmetry: 12`, give no
  `loop-seam` or `linear-motion`, while the same tracks without `wrap` still warn.
- **Docs:** the seamless-loop and parallax sections of the motion guides, the motion check reference, skills references,
  changelog.
- **Rating:** C2, P2. **Depends on:** none.

### 6.4 Cut-paper frames re-rasterise every piece on each new hold (#754)

- **Problem:** a 960×540 cut-paper scene with about 314 layers took about 4 s per frame in the report; a synthetic
  315-layer scene takes 1.2-1.5 s for each frame that starts a new stop-motion hold against 0.08 s inside a hold. The
  per-hold sub-pixel jitter moves every piece and group by a fraction of a pixel, so every layer misses the raster cache,
  and layout extents re-parse path polygons on every frame.
- **Remaining work:**
  1. Apply stop-motion jitter as a compositing offset: render cut-paper layers and groups at their unjittered position
     (a cache hit) and paste with a sub-pixel translation (whole-pixel for previews), without changing `layer["x"]` and
     `["y"]` in `scene.apply_at`; detach only the layers that change. Owner decision: this is a small pixel change.
  2. Memoise `geometry.path_polygons` (or `vector_strokes.primitives` / `margin`) by path string and stroke parameters,
     with an LRU like the SVG cache.
  3. A `draft` render option for previews and `render_at`: jitter off or whole-pixel, grain at reduced resolution,
     per-layer effects reused from the cache.
  4. A perf budget: a 300-layer jittered cut-paper scene renders a new-hold frame within about 3× the measured
     post-fix time.
- **Done when:** a regression test counts `shape_image` calls and shows a new-hold frame does not re-rasterise
  unchanged pieces; jittered output matches the previous pixels within the decided tolerance or goldens are reviewed;
  the `tests/test_perf.py` budget passes.
- **Docs:** draft previews in the cut-paper guidance, changelog with the measured figure.
- **Rating:** C3, P3. **Depends on:** the jitter decision. The rasteriser binding in stage 8 would also help.

### 6.5 Layer styles: inner shadow, inner glow and bevel (#751)

- **Problem:** there is no way to give a piece a lit edge facing the light and a soft shadow on the far side that follow
  its silhouette; the stand-in, `vignette` on every piece, darkens the layer's box evenly and is not directional.
- **Remaining work (core: layer styles are rendered and exported by core):**
  1. Add `inner-shadow` {color, dx, dy, blur, opacity}, `inner-glow` {color, blur, opacity} and `bevel` {angle, size,
     highlight, shadow, opacity} to `design_schema.STYLES` and its schema, computed from the layer's alpha (an inverted,
     offset and blurred alpha clipped to the silhouette; bevel from the alpha's distance field or gradient against the
     light angle).
  2. Render in the layer's own frame, so the light stays put when the layer turns (as `emboss` does).
  3. Exports: SVG filters (`feOffset`, `feGaussianBlur`, `feComposite in`), PDF raster fallback through the existing
     appearance path, PPTX `innerShdw` for inner shadow and raster fallback for the rest.
  4. Optional: `cut-paper` `edge_light: {angle}` applies a subtle bevel.
- **Done when:** pixels inside the silhouette darken on the side away from the light and stay transparent outside;
  SVG, PDF and PPTX parity tests; a golden per style.
- **Docs:** the layer-style reference in `docs/guides/finishing/looks.md`, skills references, changelog.
- **Rating:** C3, P2. **Depends on:** none.

### 6.6 Combine motion over time and add tracks together (#750)

- **Problem:** a periodic motion that hands over to a one-off pose sequence and back (a gallop, a jump, then the gallop
  again at the right phase), or two contributions summed on one property, cannot be described. The unicorn build wrote
  about 73 explicit keys per track for about 25 tracks, editable only as numbers.
- **Remaining work (core, timeline):**
  1. Additive layers: `keyframes` `mode: "add"` writes a named additive track (`track.layer: NAME`) on the same
     property; `timeline.sample_track` sums the base and its additive tracks at render, and exporters bake the sum
     (Lottie, SVG and video already sample through `project_at`). Owner decision: stored and summed at render, or
     compiled to keys.
  2. Blend windows: `sample.blend: {start, duration, poses: [{at, value}], easing}` eases from the wave's value at the
     window start through the poses and back to the wave at the window end.
  3. Piecewise samples: `sample` accepts a list of segments joined continuously.
  4. The seam and motion checks (`seam_findings`, `motion.findings`) read the summed value.
- **Done when:** a sine gallop plus a jump blend window matches the wave outside the window and the poses at their
  times, and is continuous at both edges; an additive bob plus a leap sums correctly in a render and in a Lottie export.
- **Docs:** `docs/guides/motion/animation-authoring.md` (drop "no expression language" where it no longer holds), the
  motion schema docs, skills references, changelog.
- **Rating:** C3, P2. **Depends on:** the storage decision.

### 6.7 A quadruped rig with walk, trot, gallop and jump (#749)

- **Problem:** animating a horse, dog, cat or unicorn means building the rig by hand (leg groups, nested lower legs,
  pivots in canvas coordinates) and computing every angle in Python; Vixl only stores the resulting keys.
- **Remaining work (extends the `characters` plugin):**
  1. A `quadruped` body plan for `character` (`species` presets for proportions: horse, dog, cat …) with body, neck,
     head, tail and four legs, each split into upper leg, lower leg and hoof or paw, with pivots at shoulder, hip, knee
     and hock.
  2. `character-cycle` cycles for it: `walk`, `trot`, `gallop` (per-leg phase offsets so the hooves land in sequence,
     body bob and tilt), `jump` (crouch, push off, tuck, reach, land) and `idle`, written as editable keys; seamless loops
     honour `loop_mode`.
  3. A `parts` binding for user-supplied artwork, as the humanoid has.
  4. New operations go into `targets.py` and the operations table is regenerated.
- **Done when:** tests build a quadruped, run each cycle, assert the gallop's foot-contact order and that joints stay
  connected (the `character` check); custom parts bind; a contact-sheet golden.
- **Docs:** the character guide under `docs/guides/motion/`, character guidance in `guidance.py`, skills references, a
  `docs/use-cases.md` row, changelog.
- **Rating:** C4, P2. **Depends on:** 6.6.

### 6.8 Hand-lettered work stays live text (#728)

- **Problem:** to get a hand-lettered look (each word its own size, baseline and tilt), a drawing kit converts every
  word to outlines, so the documents have no text layers: contrast, size, clipping, font and brand-font checks have
  nothing to evaluate, and the words cannot be edited. Rich-text spans have no per-span rise or rotation, and the
  `irregular` treatment refuses text.
- **Remaining work (core):**
  1. Per-span `rise` (px baseline shift), `rotate` (degrees) and `scale` on `richtext` spans, laid out in
     `richtext.layout` so PNG, SVG, PDF and PPTX agree (PPTX: a baseline offset; rotation falls back to per-run
     positioning or a note).
  2. A seeded `hand_set` option on text layers (`{seed, rise, rotate, scale, tracking}` ranges, per word or per glyph),
     resolved at draw time like `lettering.apply`, so the stored text stays plain and editable.
  3. Optional: record `source_text` (text, font, size, colour) on layers produced by outlining text, and have the text
     checks read it.
- **Done when:** a hand-set text layer renders with varied baselines and rotations identically in raster, SVG and PDF;
  contrast and font checks still report on it; editing its text keeps the variation seeded and stable; a golden covers
  it.
- **Docs:** the lettering pages under `docs/guides/text/`, `docs/guides/finishing/irregular.md` (point at `hand_set`),
  skills text references, changelog.
- **Rating:** C3, P3. **Depends on:** none.

**Close at the end of this stage:** [#748](https://github.com/jxburros/vixl/issues/748),
[#747](https://github.com/jxburros/vixl/issues/747), [#752](https://github.com/jxburros/vixl/issues/752),
[#754](https://github.com/jxburros/vixl/issues/754), [#751](https://github.com/jxburros/vixl/issues/751),
[#750](https://github.com/jxburros/vixl/issues/750), [#749](https://github.com/jxburros/vixl/issues/749),
[#728](https://github.com/jxburros/vixl/issues/728).

## 11. Stage 7: chart editing by data

Changing "the Brazil bar" or "make this one stand out" takes several layer-level operations today. Do the audit (7.1)
first or alongside 7.2; 7.3 needs 7.2's resolver.

### 7.1 Audit which chart edits still need raw layer operations (#780)

- **Problem:** nobody knows which common edits after `chart` still drop to layer operations, how often, and at what call
  cost, so chart work cannot be prioritised.
- **Remaining work:** list the common chart edits from the `docs/use-cases.md` rows DAT-10, 20, 21, 32, 40, 41 and 50,
  the chart tasks in `evals/tasks/` (for example `chart-fix-value.json`) and eval traces; for each, record whether it is
  one semantic operation or needs raw layer edits, its call cost now and if made semantic; rank them and file one issue
  per worthwhile case (known: 7.2, 7.3; data-bound callouts already work through shared datasets). Add the ranked table
  to this roadmap as new stage-7 items, and update the use-case rows whose status changes.
- **Done when:** the table is in this file and the issues are filed.
- **Rating:** C1, P2. **Depends on:** none.

### 7.2 Address chart marks by series and category (#778)

- **Problem:** to change one bar or label, an agent lists the chart's children and matches names, or works out
  coordinates; chart marks are keyed by index, so the address breaks on regeneration.
- **Remaining work:**
  1. In the `charts` plugin, `resolve_mark(project, {chart, series?, category?, part?})` returns layer ids for bar,
     slice, point, value label, total label and legend entry; unknown series or category values raise an error listing
     the valid names, like `chart-data`.
  2. The address survives `chart-data` edits: store `chart_mark: {series, category}` on each part, or key parts by name
     rather than index, so reorders keep identity.
  3. Core accepts the object target form in `selectors.py` / `targets.py` through a registry role (for example a
     `target-resolver` hook in `vixl.plugins.HOOKS`), so core never imports the plugin.
- **Done when:** one test resolves `{series, category}` to the right layers on bar, stacked bar, line and donut charts
  before and after a `chart-data` edit that reorders categories, and an unknown category errors with the valid list.
- **Docs:** `docs/guides/output/charts.md`, skills targets reference, changelog.
- **Rating:** C2, P3. **Depends on:** none.

### 7.3 Chart emphasis: highlight, mute, annotate (#779)

- **Problem:** "make this one stand out" (colour the key bar, tone down the rest, label it) takes several operations per
  mark and must be repeated after every data change.
- **Remaining work (`charts` plugin, writing ordinary layers):**
  1. A `chart-emphasis` operation: `focus` (categories, optionally a series), `mute` (`fade` through
     `normalize.opacity` or a palette mix, or `desaturate`) and `annotate` (callout text with `${value}`), stored in the
     chart recipe so `chart-data` re-applies it; `focus: []` restores the defaults.
  2. Bar, stacked, line, area, pie and donut; refuse other kinds with a clear message.
  3. Respect `color_vision` and contrast: muted marks stay distinguishable from the focus, with a finding if not.
  4. Add it to `targets.py` (per chart, not EACH) and regenerate the table; export parity in SVG, PDF, PPTX (native point
     colours in `chart_pptx.py`) and raster.
- **Done when:** emphasising one category on each chart type survives a `chart-data` value change, `focus: []`
  restores the original pixels, and goldens of non-emphasised charts are unchanged.
- **Docs:** `docs/guides/output/charts.md`, skills references, the DAT-20 row ("callouts typed by hand"), changelog.
- **Rating:** C3, P3. **Depends on:** 7.2.

**Close at the end of this stage:** [#780](https://github.com/jxburros/vixl/issues/780),
[#778](https://github.com/jxburros/vixl/issues/778), [#779](https://github.com/jxburros/vixl/issues/779).

## 12. Stage 8: rendering and export speed

### Where render time goes

Measured after the 0.29 speed work on a 4-core Linux container (`cProfile` and best-of-three wall clock; re-measure
before acting, the numbers are from one machine):

| Document | Cold render | Where the time goes |
| --- | --- | --- |
| 2,000 ellipses, rectangles and rounded rectangles, 80% opacity, 6000 × 6000 | 15.1 s | `resvg_py.svg_to_bytes` 7.6 s (1,309 calls), PNG decode of its output 0.8 s, `alpha_composite` 1.2 s |
| The same, caches warm, no snapshot | 3.2 s | `alpha_composite` 1.5 s, image copies and crops 0.5 s, the gradient background 0.2 s |
| 1,500 text labels, 3000 × 2000 | 3.0 s | `resvg_py.svg_to_bytes` 1.5 s (one call per label, about 1 ms each) |
| 80 soft-shadowed ellipses, 4000 × 4000 | 1.6 s | `alpha_composite` 0.5 s, Gaussian blur 0.5 s (both release the GIL) |
| 144 timeline frames of a 640 × 360 lyric film, 324 layers | 10.8 s | Python layout per frame: resolving layers, extents, stroke margins, cache keys (JSON encoding) |

Two facts decide most of this stage. **resvg_py holds the GIL and returns PNG:** four threads calling `svg_to_bytes`
take as long as one, and its time grows at about 170 ns per pixel (a 200 × 200 ellipse 6.7 ms, 1000 × 1000 130 ms),
mostly the PNG encode in the binding and the decode on our side, not rasterisation; a tiny SVG costs about 0.25 ms.
**Pillow and numpy release the GIL:** blur, compositing, resampling and image decoding run in parallel threads (a
1500 × 1500 blur: 1.8× on four threads).

Animation export, measured on 2026-10-22 (1280 × 720, 40 fading ellipses and 12 fading labels, 30 fps): MP4 of 90
frames 2.6 s with one worker and 4.4 s with the default workers; 311 frames 7.6 / 8.9 / 8.1 s with 1 / 2 / 3 workers;
a PNG frame zip of 311 frames 11.3 s; WebM of 90 frames 8.4 s. Re-encoding the 311 raw frames alone: libx264 `medium`
3.5 s, `veryfast` 2.1 s; libvpx-vp9 at defaults 18.7 s, tuned 10.1 s. For animations that move or fade the time is in
compositing, the per-frame copy of animated layers, writing to ffmpeg and `with_opacity`, not rasterising. Items 1-6
and 8 of that plan shipped in 0.33.0 (budgets, VP9 settings, measured worker count, fast frame zips, opaque MP4 frames,
scalar frame copies, draft/final presets); items 7 and 9 are below.

Decisions already taken: #590 (render pool), #595 (incremental lighting and per-pixel adjustments) and parallel frame
ranges shipped; #593 (native kernels) was closed because blur and compositing are Pillow C and numba would add about
50 MB to the frozen build for no measured gain; a Skia backend (#591) was explored and not adopted because it changes
every golden and adds about 30 MB, while the measured bottleneck is the binding, not the rasteriser.

### 8.1 A rasteriser binding that returns pixels and releases the GIL (remainder of #591)

- **Problem:** vector shapes and text rasterise through `resvg_py.svg_to_bytes`, which holds the GIL and round-trips
  through PNG; in the 2,000-shape profile that is 7.6 s of 15.1 s cold plus 0.8 s of decoding, and threads cannot help.
  The same call dominates label-heavy documents (#584), the vector half of tiled rendering (#588) and part of #754.
- **Remaining work:**
  1. Ask resvg_py upstream for an API that returns an RGBA buffer and releases the GIL.
  2. Otherwise carry a small optional binding (`vixl-engine[fastraster]`, a pyo3 wrapper over resvg/tiny-skia) behind
     `vector_raster`, with the current path as fallback and byte-identical pixels (owner decision: build and
     distribution cost for the frozen builds and the self-updater).
  3. Let the render pool draw vector and text layers when the fast binding is present.
- **Done when:** the fast path is pixel-identical on the golden set, the 1,500-label and 2,000-shape documents render
  at least 2× faster cold, and Windows, macOS arm64 and manylinux wheels exist, or the extra is documented as optional.
- **Docs:** `docs/reference/releases.md` (the extra), changelog.
- **Rating:** C3, P3. **Depends on:** an upstream answer.

### 8.2 Glyph-run cache (#584)

- **Problem:** labels that differ by one character ("Label 1", "Label 2", a counter across frames) rasterise every glyph
  again. A glyph atlas would make 1,500 labels cost about one call and save roughly half of a cold label-heavy render,
  but glyphs sit at fractional pen positions, so reuse needs their subpixel phase quantised: at 1/4 px an edge moves up
  to 1/8 px, tens of levels on an edge pixel, not the 2 levels first targeted. Compositing per-glyph coverage with `max`
  also differs from resvg where glyphs overlap.
- **Remaining work:**
  1. Do 8.1 first; it speeds the same work with no pixel change.
  2. Only if the owner accepts the tolerance: `src/vixl/glyph_cache.py`, an LRU keyed by (font digest, glyph id, size,
     quantised subpixel phase, linear matrix) with a 32 MB budget and a lock; batch a layer's missing glyphs into one
     atlas SVG; use it in `text.render_text` only for single-paint, unstroked, non-kinetic, non-path text with a
     translate or scale matrix; fall back where shaped clusters overlap; a `VIXL_GLYPH_CACHE=off` switch and
     `glyph_hits`/`glyph_misses` profile counters.
- **Done when:** 500 labels "Label 0" to "Label 499" cost at most (distinct glyphs + 1) rasteriser calls; a key change
  (font, size, offset) gives new pixels; the maximum difference against the SVG path stays within the accepted tolerance
  on a Latin, Cyrillic and Arabic corpus; goldens pass or are reviewed.
- **Docs:** the fast path and switch in `docs/project/render-parity.md`, changelog.
- **Rating:** C3, P2. **Depends on:** 8.1; the tolerance decision.

### 8.3 Tiled compositing for large canvases (#588)

- **Problem:** the compositor holds one canvas-sized RGBA image and each snapshot copy multiplies it, so large print
  canvases cost hundreds of MB per copy, and canvases over 40 MP (7,000 × 10,000 at 300 dpi) are refused. Tiling alone
  does not help: a layer larger than a quarter of the layer cache (96 MiB, a 24-megapixel layer) is not cached, so every
  tile it crosses would draw it again (a full-canvas gradient on 36 tiles is drawn 36 times). Incremental renders
  already cover the common case of an edit.
- **Remaining work:**
  1. Region drawing in `render.draw_ink`: solid fills, gradients, shape rectangles and rasters drawn cropped to a box
     before effects; bypass the layer-ink cache for layers over `cache.budget // 4`.
  2. `render.render_tiled(project, tile=1024, workers)`, used when `region_renders_alone` holds and pixels exceed 8 M,
     calling `render_region` per tile on the render pool.
  3. A streamed writer: a row-band PNG (zlib plus a hand-written IDAT in `fileio`) or a tiled TIFF; the PDF raster
     fallback as per-tile XObjects.
  4. After measuring, decide on a separate `max_tiled_pixels` limit (owner).
- **Done when:** tiled output equals the full render on random documents (tile sizes 256 and 1000, layers straddling
  tiles, text overhang), and a Linux perf test shows a 6000 × 6000, 2,000-shape document at least 30% lower in peak RSS
  than the single-canvas path within a time budget.
- **Docs:** large canvases in `docs/guides/output/exporting.md`, changelog with the RSS figure.
- **Rating:** C4, P3. **Depends on:** none (8.1 helps the vector half).

### 8.4 Incremental renders for documents that read the whole canvas (remainder of #595)

- **Problem:** every edit on a document with a blur, contrast, sharpen or noise adjustment layer, a canvas-edge blur or a
  selection-masked effect re-renders the whole canvas; these are common in finished looks.
- **Remaining work:** replace the boolean `render.region_renders_alone` with `region_reach(project) -> margin | None`;
  grow the dirty box by each non-pointwise filter's reach (`effect_margin`) through the segment snapshot per-pixel
  adjustments already use; include canvas-edge blur and selection-masked effects' absolute bounds in
  `layer_fingerprints` and grow the box by the blur margin.
- **Done when:** random-edit equality tests (the `test_incremental_renders_match_full_renders_through_random_edits`
  pattern) pass for each of the three, and `test_documents_that_read_the_whole_canvas_render_in_full` is inverted to
  assert snapshots.
- **Rating:** C3, P3. **Depends on:** none.

### 8.5 Film segments in parallel (remainder of #717)

- **Problem:** long film renders (`plugins/film`, resumable segments) still render one segment after another in one
  process, although timeline exports use worker processes.
- **Remaining work:** in `plugins/film/film.py` `export_segments`, render independent segments through
  `frame_workers.frames` or a segment-level process pool sized by `workers_for`, muxing in order; keep resume keys and
  per-segment caches valid.
- **Done when:** a film exported with 1 and 3 workers gives byte-identical segment files, and a cancelled export stops
  within one chunk per worker.
- **Docs:** film workers in `docs/guides/output/exporting.md`, changelog.
- **Rating:** C2, P2. **Depends on:** none.

### 8.6 Fade compositing cache (export-speed item 7, no issue)

- **Problem:** in animations that fade, every frame re-splits, remaps and re-attaches the alpha of every fading layer
  (`with_opacity`) and re-composites the unchanged layers below the animated ones; in the measured fade document these
  are the largest costs after encoding.
- **Remaining work:** apply layer opacity during compositing (scale the source alpha inside the composite step) instead
  of building a new RGBA image per layer per frame, or cache the scaled alpha per (layer image identity, quantised
  opacity step); detect runs of static layers below the lowest animated layer per frame range and composite them once
  as a reusable backdrop (`timeline.render_at` / `FrameState`), invalidated when any of them has a track; keep exact
  pixels.
- **Done when:** `tests/test_perf.py` gets a tighter fade-export budget that the new path meets (target at least 25%
  faster), and a parity test compares cached and uncached paths on fades, masks and blend modes.
- **Rating:** C3, P3. **Depends on:** a re-profile confirming compositing still leads.

### 8.7 Opt-in hardware video encoding (export-speed item 9, no issue)

- **Problem:** long or high-resolution MP4/WebM exports spend a real share of their time in software encoding, and
  machines with NVENC, QSV, VAAPI or VideoToolbox could encode much faster.
- **Remaining work:** `VIXL_VIDEO_ENCODER=auto|software|nvenc|qsv|vaapi|videotoolbox` (optionally an export field with
  a `schema.field` description) read in `timeline._video`; probe the encoder with a one-frame encode cached per process
  and fall back to software with a note; map `quality` and `preset` to each encoder's controls (`-cq`, `-global_quality`,
  `-qp`, `-q:v`), keeping yuv420p and software VP9 alpha; software stays the default; report the encoder used in the
  export result and in delivery verification.
- **Done when:** with a mocked ffmpeg each encoder name maps to the expected arguments, a failed probe falls back with
  a note, the default path is byte-identical on a runner with no hardware, and one measured run on an owner machine with
  hardware encoding is recorded in this section.
- **Rating:** C3, P2. **Depends on:** 8.6 or a long-film profile showing encoding is a real share; the owner decision on
  machine-dependent output.

**Close at the end of this stage:** [#584](https://github.com/jxburros/vixl/issues/584) (or close it as not planned if
the tolerance is refused), [#588](https://github.com/jxburros/vixl/issues/588).

## 13. Stage 9: interchange, fonts and accessibility

Handoff to other tools and offline fonts. Several items need one owner session in third-party apps (Figma, Photoshop
or Photopea, a browser player); they can be done together.

### 9.1 Tagged PDF structure tree (#719)

- **Problem:** PDF export writes `/Lang`, `/Alt` and `/Artifact` marked content but no structure tree, so screen
  readers and PDF/UA checkers treat the file as untagged and lose reading order and headings; accessible PDFs are a
  procurement requirement.
- **Remaining work:** in `src/vixl/pdf_export.py`, give the existing BDC marked-content operators MCIDs; write a
  `StructTreeRoot` (Document > Sect per page > Figure, P, H1-H6 with the heading level from text stages) in the
  document's `reading_order` (from the `accessibility` operation), with a `ParentTree` mapping MCIDs back and
  `/StructParents` on each page; set `/MarkInfo <</Marked true>>` and keep `/Lang`; decorative layers stay `/Artifact`;
  ship behind `export(tagged=True)` (CLI `--tagged`, MCP and REST fields with descriptions); update the "not written"
  sentences in `capabilities.py`, `guidance.py` and `accessibility.py`.
- **Done when:** pypdf reads the `StructTreeRoot`, MCIDs map one-to-one to marked content, the structure order follows
  `reading_order`, and `tagged=False` output is byte-identical to today.
- **Docs:** the accessibility guide, the PDF section of `docs/guides/output/exporting.md`, skills references, the QA-40
  row, changelog.
- **Rating:** C3, P3. **Depends on:** none.

### 9.2 Colour font files in text (#721)

- **Problem:** a text layer set in a colour font (Noto Color Emoji, a COLR display face, Apple sbix emoji) is refused
  with "bitmap/color fonts require appearance-preserving raster export", so brand display fonts and system emoji fonts
  cannot be used, and `checks.missing_glyphs` flags characters those fonts would cover.
- **Remaining work (core, the text renderer):** accept colour fonts in `text._face`, using the outline or a fallback
  face for metrics; OT-SVG and COLRv0 glyphs to SVG paths (fontTools `ColorLayers`) rasterised with resvg, COLRv1 paint
  graphs by the same route; CBDT/CBLC and sbix embed the strike nearest the requested size and scale it; SVG and PDF
  write vector glyphs where possible and otherwise report `raster_fallbacks`, PPTX gets a raster; glyphs sit on the
  baseline and count in `ink_bounds` and the overflow checks.
- **Done when:** one small licence-clean fixture font per format (COLRv0, COLRv1, CBDT, sbix, OT-SVG) under
  `tests/fixtures` renders coloured pixels in PNG; SVG and PDF write vector glyphs or list the glyph under
  `raster_fallbacks`; `missing_glyphs` no longer flags characters a colour font covers.
- **Docs:** `docs/guides/text/emojis.md`, the typography guide, changelog.
- **Rating:** C4, P2. **Depends on:** the owner decision on emoji preference.

### 9.3 Emoji pack destinations (#722)

- **Problem:** `export_pack` writes a portable image pack, Discord emoji and Slack emoji only. Sticker and emote sets
  for WhatsApp, Telegram, Twitch or iMessage, and animated sets, are resized, encoded and byte-checked by hand, and
  "Slack + Discord + WhatsApp from one document in one call" is unmet.
- **Remaining work:** add destinations to `DESTINATIONS` in `src/vixl/emojis.py` (WhatsApp stickers: 512 × 512 WebP,
  byte limits, tray icon; Telegram static stickers and custom emoji; Twitch emotes at 28/56/112; iMessage stickers),
  keeping every platform limit as data verified against the platform's documentation at implementation time; animated
  GIF/WebP packs from the timeline through `timeline.export_timeline` with per-destination loop, frame, duration and
  byte budgets and step-downs (fps, colours); a `telegram-animated` destination that writes TGS per emoji through the
  `timeline-export-format` hook (the lottie plugin, reached through the registry), refusing raster fallbacks as TGS
  export does; several destinations per call sharing the rendered masters.
- **Done when:** each destination's files pass its size, format and byte rules plus the manifest; an animated pack
  respects its budgets; one document exports Slack, Discord and WhatsApp packs in one call; a TGS pack passes the TGS
  constraints.
- **Docs:** the destinations table in `docs/guides/text/emojis.md`, skills references, changelog.
- **Rating:** C3, P2. **Depends on:** the iMessage scope decision.

### 9.4 Editable PSD handoff and bounded PSD import (#514)

- **Problem:** PSD export keeps pixel layers, groups and blend modes but rasterises text and shapes (each text layer is
  listed under `text_as_pixels`), so a designer who receives a Vixl PSD cannot edit the copy, and Vixl cannot open a
  layered PSD at all.
- **Remaining work:**
  1. Export (core, `psd_export` is a core exporter): a `TySh` type-tool block for plain `text` layers with one style run
     (PostScript name, size, colour, tracking, leading, alignment, point or box text), keeping the rendered pixels as the
     layer image; the EngineData descriptor writer in a new `src/vixl/psd_text.py`. Rich text, effects, transforms
     beyond rotate and scale, and image-filled text keep pixels with a located `text_as_pixels` reason.
  2. Import (plugin `psd_import` through the `import-format` hook): a hand-written bounded reader for 8-bit RGB with RLE
     or raw channels, sized by `Limits`, mapping image layers, groups, visibility, opacity, a known blend subset and layer
     masks and rejecting the rest; `psd-tools` only as an optional plugin dependency if the reader stalls (owner).
  3. Shape and vector layers: evaluate later.
- **Done when:** an exported type layer parses back with its text, font and size and opens editable in Photoshop or
  Photopea (owner check); a small committed third-party PSD imports with names, order, visibility, opacity and mask;
  malformed and oversized PSDs are rejected without large allocations; the round-trip render matches within tolerance.
- **Docs:** the PSD subset in `docs/guides/output/exporting.md`, PSD import in `docs/reference/converting.md`, the
  DOC-44 and BLK-02 rows, changelog.
- **Rating:** C5, P2. **Depends on:** none.

### 9.5 Figma interchange verified in Figma (#662)

- **Problem:** the `FIGMA` / `.figma.json` export, its published schema and the offline import plugin in
  `integrations/figma-plugin/` are tested only offline (schema validation, a mocked Figma API, round-trip re-import into
  Vixl). Nobody has opened a Vixl export in real Figma, so font loading, gradient transforms, auto-layout mapping, mask
  groups and raster placeholders are unverified against the real Plugin API.
- **Remaining work:** owner, in Figma desktop: Plugins → Development → Import plugin from manifest with
  `integrations/figma-plugin/manifest.json`; export three fixtures (a poster with gradients, a mask and effects; a
  three-page deck with stacks; a chart or diagram), import each and screenshot it beside the Vixl PNG; turn each
  discrepancy (position or size, gradient angle, a missing font report, a silently lost feature) into a fix in
  `figma_export.py` or `code.ts` with an offline regression test; record the verified Figma version and results in
  `docs/guides/images/figma.md`; decide whether to publish the plugin to the Figma Community.
- **Done when:** the three fixtures import with editable text, vectors and frames, every fallback appears in the
  plugin's report, and every fix has an offline test.
- **Rating:** C2, P2. **Depends on:** the owner session.

### 9.6 Lottie checked against real players (remainder of #177)

- **Problem:** the reference-player comparisons in `tests/test_lottie.py` (rlottie, seven scenes plus linked instances
  at seven frames) never run in CI because no workflow installs the `lottie-test` extra, so a Lottie regression passes CI.
  The lottie-web check the issue asked for (the motion tutorial's intro against Vixl's own frames) is not done. Animated
  link placement, corner pins and non-Bezier easings (bounce, elastic, spring, steps) still export as per-frame held
  keys or raster fallbacks.
- **Remaining work:** install `.[dev,lottie-test]` in a Linux job of `.github/workflows/test.yml` so the rlottie
  comparisons run; check other optional-extra test files and run them in one "all extras" job; optionally add a
  lottie-web check (a headless-browser script rendering the exported motion-tutorial intro at five times, compared with
  `timeline.render_at`, behind a marker); optionally express animated link placement as transform keys on the
  precomposition instead of a raster fallback in `src/vixl/plugins/lottie/lottie.py`.
- **Done when:** CI runs the rlottie comparisons and fails on a deliberate mismatch; if built, the intro matches in
  lottie-web (mean difference under one level, under 0.5% of pixels over 32) at five frames.
- **Docs:** verified players in the Lottie section of `docs/guides/output/exporting.md`, test notes in CONTRIBUTING.
- **Rating:** C2, P2. **Depends on:** the browser-dependency decision.

### 9.7 Fonts offline: a pinned CJK pack and a curated offline set (remainder of #419)

- **Problem:** CJK has no pinned content pack: a machine that never ran `font-cover` or `font install` for Han, with no
  `VIXL_CJK_PACK`, gets a warning rather than a one-step pinned download (`vixl.packs` has the `packs.local("cjk")` seam
  and a docstring placeholder, but `PACKS` holds only `emojis` and `fonts`). When the pairing download fails (offline,
  locked-down network, untrusted proxy), every rolled pairing falls back to the proofing face and a first-time user sees
  a rough proof; only Noto Sans and DejaVu Sans are bundled, with no offline serif or display face.
- **Remaining work:** owner commits `fonts/cjk.zip` (Noto Sans SC, TC, JP and KR regular, named like the font cache, e.g.
  `noto-sans-sc-400.ttf`) to VixlPacks; add the `cjk` entry to `vixl.packs.PACKS` (commit, SHA-256, bytes, install text)
  and remove the placeholder; let the CJK fallback in `typefaces.local_script_faces` use `packs.path("cjk")` when
  downloads are allowed, and only from an explicit step (`font-cover` or `vixl font cjk --download`), never during a
  render; choose one OFL serif, sans and display face and bundle them (watch the wheel size) or ship them as a pinned
  pack, and make rolled pairings fall back to them instead of the proofing face; run the house-style eval.
- **Done when:** a test with a local fixture pack installs `cjk` by SHA-256 and renders Han without tofu; with
  `VIXL_PACK_DOWNLOAD=off` it warns with the step; with downloads blocked a rolled pairing draws the curated offline
  faces.
- **Docs:** packs in `docs/reference/plugins.md`, the typography guide, `docs/troubleshooting.md`, NOTICE and licences,
  changelog.
- **Rating:** C2 + C2, P3. **Depends on:** the VixlPacks commit; the curated-set decision.

### 9.8 Spelling dictionaries beyond English (remainder of #554)

- **Problem:** only English has a dictionary (bundled `data/en.txt.gz` from SCOWL). A document whose `form.lang` or
  `accessibility.lang` is `de`, `fr`, `es` … asks for a `spelling-<lang>` content pack that does not exist, so the check
  can only report `dictionary-unavailable`.
- **Remaining work:** build word lists for the first languages (suggest de, fr, es, it, pt, nl) from a licence-compatible
  source with the licence in the header, each gzip under 1 MB; publish them in VixlPacks as `spelling-<lang>`; pin each in
  `PACKS`; check that the tokenizer in `src/vixl/plugins/spelling/spelling.py` handles apostrophes, German compounds and
  accented letters. The code stays in the plugin; the lists are content packs.
- **Done when:** with a fake `de` pack in the pack cache, `tests/test_spelling.py` flags a misspelt German word and
  accepts a correct compound; with downloads off and no cache the check still gives `dictionary-unavailable`.
- **Docs:** the spelling section and language list in `docs/guides/layout/brands.md`, `docs/reference/coverage.md`,
  changelog.
- **Rating:** C2, P2. **Depends on:** the owner choosing languages and the source licence.

### 9.9 Import a printer's template as guides, and check against it (#727)

- **Problem:** a print-on-demand wrap template (back, spine and front) marks the board edge, per-panel safe areas, a
  barcode keep-out notch and spine folds as coloured dashed lines in a PNG or PSD. Vixl cannot use them, so the user
  measured pixel positions by hand and eyeballed overlays outside the document. Guides have no roles.
- **Remaining work:** core: a guide `role` (`trim`, `safe`, `fold`, `keep-out`, `bleed`) in `guides.validate_guide`,
  with closed path or rectangle guides defining regions; core: a `guides` check rule (or an extension of `safe_area`)
  that reports content ink (strokes and effects included, from the existing ink bounds) outside any `safe` region of its
  panel or inside a `keep-out`, and important layers crossing a fold; plugin (`src/vixl/plugins/print_templates/`, or
  the `imposition` plugin): `guides-import` from an image, where the user maps colour to role and dashed lines and
  closed outlines are detected by colour with numpy and snapped to whole pixels, optionally from named PSD guide layers,
  saved as a reusable `guide-sets` resource.
- **Done when:** a fixture PNG with coloured dashed rectangles and a notch imports into role-tagged guides; the check
  flags a text layer crossing the keep-out notch and one outside the front-panel safe area; applying the saved preset to
  a new document reproduces the guides.
- **Docs:** `docs/guides/layout/guides.md`, `docs/guides/finishing/color-and-print.md`, the check reference, a new PRN
  row in `docs/use-cases.md`, skills references, changelog.
- **Rating:** C3, P3. **Depends on:** none.

**Close at the end of this stage:** [#719](https://github.com/jxburros/vixl/issues/719),
[#721](https://github.com/jxburros/vixl/issues/721), [#722](https://github.com/jxburros/vixl/issues/722),
[#514](https://github.com/jxburros/vixl/issues/514), [#662](https://github.com/jxburros/vixl/issues/662),
[#727](https://github.com/jxburros/vixl/issues/727).

## 14. Stage 10: craft measurement

Every craft item has been built (0.27.0 and 0.31.0) and none has been judged. Craft claims in the changelog must cite a
published blind re-judge, not a self-assessment, so no craft gain is claimed until this stage runs.

### Where craft stood at the last judging

The 2026-10-13 blind re-judging of the tool comparison scored every lane with three judges and a human calibration set:

- On scores alone Vixl's craft was level with web code (mean craft 3.81 against 3.78).
- Side by side, judges still preferred web code: asked which they would publish, they picked web code over Vixl in 16
  of 27 calls (Vixl 11), and web code won 6 of the 9 tests the lanes share. The human calibration agreed.
- Vixl's lowest sub-scores were motif (3.67) and spacing (3.78); hierarchy, type, colour and finish were 4.1-4.4.
- Correctness was not the problem: Vixl passed 92 of 96 hard checks, and every report was honest.
- The judges' reasons, most frequent first: spacing, rhythm and alignment (tests T02, T07, T08, T15, T16: a loose lower
  half, uneven gaps in a name block, two left margins, a dead band, a crowded donut label, rules pressed onto the first
  row, a ragged price column, lumpy pattern spread); flat scenes and generic motifs (T03, T12); tool finish (T10, T11,
  T13, T15: grain left in a crop, fill halos and blobs at line joins, a flat sprite silhouette, a scatter that re-rolled
  on a count change); data presentation (T08, T16).

What was built in response: composition checks (dead band, margin drift, uneven rhythm, crowding, clumped scatter, plus
`flat_hierarchy`, `single_weight`, `no_focal`, `accent_unused`) on by default as review findings and in the `final`
profile; `repair-layout` for them; a finishing pass at the end of the agent loop with one checklist (guidance
`finishing`); critiques returned with `check=true`; balanced and pretty wrapping, tab stops and leaders, accent words,
small caps and hanging punctuation; `key-value-list`, section-header clearance, rolled pills and highlights, callouts,
bands and labelled rules; reflection, haze, star-field, string-lights, bokeh and fog; motifs from the brief and new
catalog shapes; layered water; progressive `pattern-scatter` with `thin`; fills registered to strokes; denoised crops;
charts inside the safe area; shaded, outlined pixel sprites; the `variations` contact sheet; the craft grader and an
optional rubric judge in the agent eval.

### 10.1 Blind craft re-judge and the backtest gaps (#648)

- **Problem:** nothing measures whether the craft work closed the gap. The craft backtest (20 reconstructed files of
  the 16 round-1 documents, with 21 judged composition defects and 48 others) shows the composition family catching 12
  of 21 judged defects with no false findings (dead band 5/10, margin drift 4/5, uneven rhythm 2/4, crowding 1/1,
  clumped scatter 0/1), and `repair-layout` resolving 18 of 23 findings with no new one. Known gaps: dead bands crossed
  by thin lines (T12 waves, T03 ripples) are not caught; nor is the space beside a lone footnote (T08), nor clumping from
  similar motifs lining up rather than density (T15). The four hierarchy codes have an untested catch rate (no
  reconstruction has a judged hierarchy defect, and the reconstructions use the proofing font and no rolled direction).
  T16's own crowding came from a table's header rule, which the rule-clearance default does not change. The backtest
  documents are reconstructions because the round-1 `.vixl` sources were never committed; the re-run now saves them.
- **Remaining work:**
  1. Owner: run `python -m evals.craft_rerun` (re-runs the Vixl lane on the 16 briefs, packages it with `rejudge.py`
     beside the fixed other-lane runs and prints the judge prompt), judge blind with the re-judging kit in VixlExamples,
     and publish the results there.
  2. Record the numbers against the goals below in this section.
  3. Replace the reconstructed backtest documents in `evals/craft_backtest/` with the re-run's saved sources, re-score
     every composition code, and record catch and false-finding counts per code, hierarchy codes included.
  4. Close the three detection gaps in `src/vixl/composition.py`, each with backtest numbers and no new false findings:
     ignore hairline or low-coverage ink (thin strokes, line waves) when computing free rectangles for dead bands; a
     lone-footnote finding; motif-alignment clumping in `clumped_scatter`.
  5. Re-order further craft work by whichever sub-score (spacing, motif or finish) still loses publish calls.
  6. Optional: run `python -m evals.run --judge` once against a model so the rubric judge has a first result.
- **Done when** a published blind re-judge meets the goals, or the shortfall is recorded with next actions:
  - primary: Vixl wins at least 14 of 27 "which would you publish?" calls against web code (11 at the last judging);
  - spacing sub-score at least 4.2 (3.78) and motif at least 4.0 (3.67);
  - mean craft at least 4.0 (3.81);
  - hard checks at 92 of 96 or better, and median round-1 tool calls at or below 31.5.
- **Docs:** `evals/README.md` (results link), `evals/craft_backtest/README.md`, changelog craft claims cite the
  re-judge.
- **Rating:** C2 (run and record) + C3 (detection gaps), P5. **Depends on:** the owner funding a run that matches the
  2026-10-13 kit (model and lane setup) so it is comparable. Best run after stages 3 and 4, which change first results.

### 10.2 Public comparison against agent design tools (#773)

- **Problem:** the "editable and checked" claim has not been compared against the tools users weigh Vixl against
  (Canva, Figma), with cost and editability measured. The existing VixlExamples comparison covers web code and Python
  lanes only.
- **Remaining work:**
  1. In VixlExamples (not this repository): lanes for Canva MCP, Figma MCP or Make, and one or two generative tools; a
     business-card brief; scoring for editability (live text, layers, a copy change without a redraw), check pass rate,
     text accuracy, tool calls and tokens, and money cost at public prices.
  2. Here: `evals/craft_rerun.py` or `evals/run.py` records tool-call and token counts per brief for the Vixl lane
     (shared with 4.1), and `docs/reference/releases.md` gains a release-checklist step to re-run the Vixl lane each minor
     release.
  3. Publish results and write-ups in VixlExamples only, and link them from the README or the evals README.
- **Done when:** a VixlExamples results page covers the new lanes and axes, and the release checklist has the re-run
  step.
- **Rating:** C3, P3. **Depends on:** 4.1, 10.1; the owner's accounts and budget, who rates the human-judged craft, and
  the cadence.

**Close at the end of this stage:** [#648](https://github.com/jxburros/vixl/issues/648),
[#773](https://github.com/jxburros/vixl/issues/773).

## 15. Stage 11: code structure

Mechanical changes that alter no behaviour; each lands as its own small pull request gated on the full suite,
`pytest -m visual` and `pytest -m perf`. They can run alongside any stage. The issues behind them (#631, #632, #633)
are closed; their remainders live here.

### 11.1 Operations declare their own target mode, and long functions split (remainder of #631)

- **Problem:** adding an operation still means editing the `targets.py` sets by hand, and operations that live in
  `operations.py` itself are an if-chain inside a 669-line `execute`. The longest functions (`check_design` 815 lines
  with about 20 keyword parameters, `cli.project_command` 652, `commands.compile_command` 463, `interfaces.create_app`
  570, `shape_catalog.path` 652) are hard to review.
- **Remaining work:** move the inline operations out of `operations.execute` (`add`, `palette-generate` and the other
  `kind ==` branches) into feature modules or one `core_ops.py` registered in `CORE_OPERATION_MODULES`, leaving only the
  shared steps; give each registered module a `mode` (EACH, JOINT, ONE) and derive `targets.EACH` / `JOINT` from it,
  with plugins declaring it the same way (keep `targets.markdown_table()` and the docs drift test); a `@check("name")`
  registry with a `CheckContext` dataclass for `check_design`, about ten checks per PR with output compared on the
  existing fixtures; dispatch tables for `cli.project_command`, `commands.compile_command`, `render.draw_ink`,
  `interfaces.create_app` (`register_<group>(app, session)`) and `shape_catalog.path`.
- **Done when:** a test asserts every operation type has exactly one module with a declared mode and the derived sets
  equal `targets.EACH` / `JOINT`; a ratchet test keeps functions in `operations.py`, `checks.py`, `cli.py` and
  `commands.py` under about 200 lines.
- **Docs:** CONTRIBUTING.md and the "Targets" rule in `CLAUDE.md` (owner-approved wording).
- **Rating:** C4, P2.

### 11.2 A pure renderer and a split `render.py` (remainder of #632)

- **Problem:** the renderer still changes state: `render.resolve_font` installs fonts into `project.assets` during a
  render, contradicting `docs/reference/architecture.md`. `render.py` (2,406 lines) mixes colour parsing, font
  resolution, layout extents, effects, caches and compositing. 188 upward imports remain in `tests/layering_baseline.json`,
  and function-local imports grew from about 2,900 to 4,302.
- **Remaining work:** move font installation out of `render.resolve_font` into a pre-render or pre-apply step in
  `project.py`, shared with the deferred-font logic, so the renderer only reads `project.assets`; split `render.py` by
  mechanical moves (`render_layout.py` for extents, margins and ink bounds; `render_effects.py` for `apply_effect` and
  `layer_effects`; `render_cache.py` absorbing `LayerCache`), keeping `render.py` as the compositor; shrink the layering
  baseline starting with the largest importers; optionally a soft ratchet on function-local imports per core module.
- **Done when:** a test asserts `project.assets` is unchanged by `render()` on a document whose font is missing from
  assets, and `tests/test_layering.py` passes with a smaller baseline.
- **Docs:** the layering diagram and render purity in `docs/reference/architecture.md`.
- **Rating:** C3, P2.

### 11.3 Types on the public API (remainder of #633)

- **Problem:** the public `Project` API (`apply`, `render`, `export`, `save`, `load`, `inspect`, `layer`) is untyped,
  the apply path carries state through private `candidate._x` attributes and `__dict__` writes, and there is no
  `py.typed`, so library users get no types.
- **Remaining work:** annotate `project.py`'s public methods with `document_types` and add it to `[tool.mypy]`; an
  `ApplyContext` dataclass for the attributes the apply path sets on candidates, replacing external `_attr` writes and
  `getattr(x, "_attr")` probes incrementally; replace `isinstance(x, bool)` exclusions with `model.is_number` / `is_int`
  in typed modules; ship `src/vixl/py.typed` once `Project` and `VixlError` are annotated.
- **Done when:** mypy passes with `project.py` in the list, `tests/typecheck_baseline.json` includes it, and the wheel
  contains `py.typed`.
- **Docs:** "Types" in CONTRIBUTING.md, changelog (py.typed).
- **Rating:** C3, P2. **Depends on:** 11.1 (smaller functions are easier to type).

### 11.4 Small follow-ups (no issue)

Pick these up when the code is open for something else; each is C1.

- `layouts.py`, `adapt.py` and the charts and deck plugins compute `bleed + safe` themselves instead of calling
  `sizes.live_insets`; the 0.5 px tolerance from the business-card fix hides the difference. Switching changes layout
  output (goldens), so do it with a layout batch such as stage 3.
- `vixl_reference` has no `assets` topic for pack image assets.
- Frames ignore `focal` for their inner crop (responsive adaptation uses it elsewhere).
- The standard character's shoulders sit outside its torso, so raised-arm poses open a 6-7 px gap that the `object`
  check reports (documented and tested; fix if the standard character is ever revised).
- Most 0.28.0 changelog entries do not cite issue numbers; cite `(#NNN)` from now on (section 2).

## 16. Stage 12: security hardening from the 2026-11-09 scan

A full repository scan of `f66ed26` on 2026-11-09 reported eleven medium and two low findings, all filed as issues
labelled `security`. None is remote code execution or a credential leak. Most let an authorized or semi-trusted caller
use more CPU, memory, disk, processes or network than the limits that shipped in 0.28-0.29 intend; one lets a
document-scoped REST caller reach the user-global resource library; one discloses absolute server paths. They matter
most for `vixl mcp --http`, `vixl serve`, `vixl host` and any future hosted service (#770), and much less for local
stdio use. This stage can run alongside any other. Do 12.1 first: several of the other items assume every heavy path
goes through the limiter.

Every item follows section 2: core, a regression test that fails without the fix, a `CHANGELOG.md` entry with the
issue number, and an update to `docs/reference/interfaces.md` (where the call limits and body limits are documented)
and `SECURITY.md` when a limit is added or changed.

### 12.1 Every heavy service path goes through the call limiter (#821, #823, #826, #828)

- **Problem:** the bounded executor, workspace gate and hard timeout from 0.29 are bypassed in four places. The
  fixed-project REST `/import` and `/assets` routes have no `@limited`, and the Host asset endpoint calls `Host.call`
  with `heavy=False` (#821). `vixl_render` is outside `JOB_TOOLS`, so it never takes the workspace gate and
  `max_concurrent` does not apply to renders (#828). The MCP executor's work queue is unbounded, and `JobStore` can grow
  past `MAX_JOBS` when no job has finished (#823). The MCP Streamable HTTP app has no `BodyLimit` middleware (#826).
- **Remaining work:** (1) `@limited` on the REST import and asset routes, and `heavy=True` for Host assets
  (`interfaces.py`, `host.py`). (2) Separate "takes the workspace gate" from "may detach into a job" in
  `mcp_runtime.py`, and gate `vixl_render`. (3) Count queued and running calls; over the limit, refuse with a retryable
  busy error, and make `JobStore` refuse rather than exceed `MAX_JOBS`. (4) Add `BodyLimit` to the MCP HTTP app,
  configurable like REST's.
- **Done when:** with `max_concurrent=1`, two concurrent imports or renders never overlap; a slow mocked decoder hits
  the hard timeout through REST and Host; submitting past the queue limit returns the busy error and the store stays
  at or under `MAX_JOBS`; an oversized MCP POST gets 413 before it reaches the SDK.
- **Rating:** C2, P4 for served deployments.

### 12.2 Cumulative budgets for editable SVG and PDF import (#818, #819, #822)

- **Problem:** SVG import matches an unbounded number of CSS rules against every element, decodes an embedded raster
  again for every `use`, and allows 64 full-canvas raster fallbacks with no total pixel budget (#818). Up to 10,000
  embedded font records are resolved through Google Fonts before the 64-font archive limit applies, and service imports
  install fonts by default (#819). The PDF parser allocates whatever sizes PDFium reports, materializes paths before
  the path cap, recurses into nested forms with no depth or object budget, and can repeat full-page fallback renders
  (#822).
- **Remaining work:** `svg_import.py`: cap or index stylesheet rules, decode each embedded raster once, and replace the
  fallback count with a cumulative pixel budget; apply the font limit and dedupe families at parse time, before any
  network call (`typefaces.py`), and decide whether service imports install fonts by default (`imports.py`).
  `plugins/pdf_import/pdf_import.py`: bound reported sizes before allocating, check the path cap while iterating, add a
  form depth limit and one object budget per import, and bound total fallback pixels.
- **Done when:** crafted SVG fixtures (many rules, one raster `use`d many times, many full-canvas fallbacks, more font
  records than the limit) and mocked PDFium objects (huge reported length, deep form nesting, many fallbacks) each fail
  cleanly within budget; the font case makes no network call (mocked fetcher, call count asserted).
- **Rating:** C3, P3.

### 12.3 Network reads stop at their caps and deadlines (#827, #830)

- **Problem:** the shared fetch, provider and font readers append a decoded HTTPX chunk before checking the limit, and
  `FigmaClient` reads its whole body with an eager `client.get` before checking its 256 MiB cap (#827). The fetcher's
  120-second deadline is only checked on the final body, each redirect gets a fresh 30-second timeout, and webhook
  response draining has no absolute deadline (#830).
- **Remaining work:** `fetch.py`: check `len(buffer) + len(chunk)` before appending, use a bounded decoded chunk size,
  reject an oversized `Content-Length` early, set one deadline per fetch and give each redirect hop only the time left.
  `plugins/figma_import/figma_import.py` and `plugins/ai/ai.py`: use the shared streaming reader. `jobs.py`: an absolute
  deadline (or a small byte cap) on webhook draining.
- **Done when:** with mocked transports, a gzip bomb and an oversized Figma response fail with the buffer never past
  the cap plus one chunk; a redirect chain past the total deadline fails; a trickling webhook receiver is cut off at
  the deadline.
- **Rating:** C2, P3.

### 12.4 Caller regular expressions cannot outlive the hard timeout (#825)

- **Problem:** selectors, text suites and the optional replacement workflow compile caller patterns with Python's
  backtracking `re` after only syntax and length checks; a catastrophic pattern keeps its thread, CPU and workspace
  slot after the cooperative hard timeout fires.
- **Remaining work (`selectors.py`, `call_limits.py`):** use a linear-time engine for service-supplied patterns
  (`google-re2` as an optional dependency), or reject nested quantifiers and backreferences in those patterns and cap the
  subject length, or run them in a killable subprocess. The choice is the owner's (see the decision below).
- **Done when:** a known catastrophic pattern returns an error within a short time budget, and ordinary selectors and
  suites behave as before.
- **Rating:** C2, P3. **Owner decision:** an optional `google-re2` dependency, or a restricted pattern syntax for
  service callers.

### 12.5 Quotas for durable workflow queues (#824)

- **Problem:** MCP exposes `submit`, `work` and `start`; every `Queue.start` launches another detached Python process
  with up to four threads, and every submission writes persistent files with no count, disk, process or retention
  limit.
- **Remaining work (`workflows.py`, `jobs.py`):** one worker per queue (a lock or pid file; `start` does nothing while
  a worker is alive); a cap on pending jobs and queue disk use; finished jobs pruned after a retention period.
- **Done when:** a second `start` spawns no second process; submissions past the cap are refused; finished jobs older
  than the retention period are pruned.
- **Rating:** C2, P2.

### 12.6 Workspace isolation for resources and links (#820, #829)

- **Problem:** the fixed-document REST resource routes call catalog/get/register without the session workspace, so
  they fall back to `VIXL_RESOURCES` or `~/.config/vixl/resources.json` and can read and write the user-global library
  (#820). `links.status` returns absolute resolved paths, and missing-link errors carry absolute searched paths that
  skip the `OSError` redaction (#829).
- **Remaining work:** pass the session workspace on every service resource call and remove the global fallback on
  that path (`interfaces.py`, `resources.py`, `studio.py`); report link paths and missing-link searches relative to the
  workspace root (`links.py`).
- **Done when:** registering a resource through the one-document REST app leaves a temporary global library untouched;
  link status and the missing-link error, called through REST, contain no absolute path.
- **Rating:** C1, P3.

**Close at the end of this stage:** [#818](https://github.com/jxburros/vixl/issues/818),
[#819](https://github.com/jxburros/vixl/issues/819), [#820](https://github.com/jxburros/vixl/issues/820),
[#821](https://github.com/jxburros/vixl/issues/821), [#822](https://github.com/jxburros/vixl/issues/822),
[#823](https://github.com/jxburros/vixl/issues/823), [#824](https://github.com/jxburros/vixl/issues/824),
[#825](https://github.com/jxburros/vixl/issues/825), [#826](https://github.com/jxburros/vixl/issues/826),
[#827](https://github.com/jxburros/vixl/issues/827), [#828](https://github.com/jxburros/vixl/issues/828),
[#829](https://github.com/jxburros/vixl/issues/829), [#830](https://github.com/jxburros/vixl/issues/830).

## 17. Later and exploratory

Not scheduled. Each needs either an earlier item or an owner decision before it is worth starting. Close each issue
when its item ships, or as not planned if the owner decides against it:
[#383](https://github.com/jxburros/vixl/issues/383), [#522](https://github.com/jxburros/vixl/issues/522),
[#770](https://github.com/jxburros/vixl/issues/770), [#775](https://github.com/jxburros/vixl/issues/775).

### Detect and classify objects in existing documents (#383)

- **Problem:** documents often hold undeclared object-like art (a flat pile of shapes forming a cat, an organic `rose`
  group, a character, an imported drawing), and the object tools (inspect, isolate, the `object` check, outline policy)
  work only on declared objects. The eval brief `evals/tasks/object-detect-cat.json` exists ahead of the feature.
- **Remaining work (plugin `src/vixl/plugins/object_detect/`, registered in `BUILTIN`; it writes ordinary `group` and
  `object` operations):** proposal passes, from certain to uncertain: recipe groups (organic preset to kind through
  `objects.organic_presets`, character to person, `drawing` groups), skipping `parts.COLLECTIONS` (chart, diagram,
  container), text and frames; named groups scored against kind part names and aliases (`objects.find`) with a
  confidence; ungrouped siblings clustered by touching ink (the `parts.py` union-find), name prefix and z-adjacency into
  proposed `group` + `object` + part names; the provider `detect` step only when a provider is configured. Output
  `[{layers, proposed_kind, confidence, reasons, parts, batch}]`, dry run by default, `apply: true` with
  `min_confidence` applying the batches as one undo step; the workflow through `PLUGIN["workflows"]` and CLI
  `vixl object detect [--apply]`; applied proposals validated by the `object` check.
- **Done when:** a fixture with an organic rose, a character, a six-layer ungrouped cat and two unrelated shapes gives
  exactly three proposals with the right kinds; applying them keeps the render pixel-identical; charts, frames and text
  get none; the provider step is mocked; the `object-detect-cat` brief passes.
- **Docs:** "Detect objects" in `docs/guides/shapes/objects.md`, the QA-39 row, the plugin list, SKILL.md objects
  section, changelog.
- **Rating:** C4, P2.

### Screenshot to editable reconstruction (#522)

- **Problem:** a flattened poster, slide or social graphic cannot be turned into an editable document; an agent
  hand-places text and shapes over a traced image, with no confidence or difference report.
- **Remaining work (plugin `src/vixl/plugins/reconstruct/`, provider-dependent, writing ordinary layers):** a workflow
  `reconstruct {image, apply: false, min_confidence}` with stages: provider OCR text boxes (skipped with a note when no
  provider is configured); colour quantisation and segmentation of flat regions into rectangles, rounded rectangles,
  ellipses and lines fitted with shapely, with an IoU per element; leftover complex regions as cropped image layers
  marked `observed: raster`; a font guess by size and weight from the bundled catalog with the substitution reported.
  Each proposed layer carries `confidence`, `observed`, `inferred` and `reasons`; the proposal is rendered and compared
  against the source (IoU and pixel mismatch, reusing `drawing.fidelity`, plus a diff preview); `apply: true` commits
  only elements at or above `min_confidence` and lists the rest.
- **Done when:** a synthetic Vixl-rendered poster with mocked OCR reconstructs with IoU at least 0.95, a photo region
  stays raster, low-confidence OCR is flagged, and the geometry-only path works with no provider.
- **Rating:** C5, P2. **Depends on:** #383; the owner choosing an OCR provider for real examples.

### A public hosted MCP service (#770, tracker)

- **Problem:** Vixl can only be used locally or self-hosted with a static token; hosted connector screens expect OAuth
  or no authentication.
- **Engine work, if the owner decides to host:** OAuth 2.1 for `vixl mcp --http` and `vixl host` (protected-resource
  metadata and token validation against an external authorization server, or a documented gateway in front), with
  identity mapped to allowed workspaces; per-user workspaces with storage caps and quota hooks (`pre-call` / `post-call`
  usage events with raw units, added to `vixl.plugins.HOOKS`) a gateway can enforce; hard per-call memory and CPU limits
  with killing of timed-out calls (a subprocess worker with rlimits locally, cgroups when hosted); the export quote (2.7)
  feeding the meter; short-lived signed download links with expiry; workspace export always allowed and read-only mode
  over quota. Accounts, metering, credits and payments live outside this repository; billing stays out of core.
- **Done when:** a hosted-mode integration test signs in with an OAuth token, is confined to its own workspaces, hits a
  storage cap with a clean error, has a runaway call killed at the memory cap, and downloads an export through a signed
  link that expires.
- **Rating:** C5, P5 if pursued. **Depends on:** 2.7, 5.3, 5.7 (terms); the owner's decision on whether to host, who
  operates it, the allowance model, AI providers off or bring-your-own-key, and OAuth in the engine or a gateway.

### A previewer for people watching an agent work (#775)

- **Problem:** people compare Vixl with Canva and Figma, where they can see and touch the work; watching an agent today
  needs a second command, and canvas feedback must be described in words.
- **Possible steps, smallest first, each optional:** `vixl mcp` (stdio and HTTP) optionally starts or prints a viewer URL
  that follows the active document, behind a flag, adding nothing to tool replies; review aids in the viewer (a findings
  overlay reusing `overlay`, 1:1 zoom, side-by-side revisions reusing `vixl_render(action='compare')`, page and timeline
  scrubbing) built on existing REST endpoints; notes pinned to the canvas (an optional `region` [x, y, w, h] on
  `review.notes`, shown by `vixl_document(action='notes')`); maybe light direct edits recorded as ordinary operations.
  Constraint: no added tools or reply fields for agents, and the same authentication locally and hosted.
- **Done when (per step):** for example, `vixl mcp --viewer` prints a URL that serves the active document, and a note
  with a region round-trips through `vixl_document(action='notes')`.
- **Rating:** C3 for the first three steps (C4 with edits), P3. **Depends on:** the owner deciding whether to do it,
  how far, and whether the "headless only" stance (BLK-06) changes.

## 18. Issue index

Every issue open after the 2026-10-31 triage, plus the security findings filed on 2026-11-10, with where each is
finished.

| Issue | Item | Stage |
| --- | --- | --- |
| #383 | Detect objects in existing documents | Later |
| #514 | Editable PSD handoff and PSD import | 9.4 |
| #522 | Screenshot to editable reconstruction | Later |
| #535 | Hosting epic (closes after #543, #546, #547) | 5 |
| #543 | Host API schema missing from releases (fixed in 0.33.3; close when a release lists it) | 1 |
| #546 | Container image built by releases | 5.3 |
| #547 | Windows host task exercised on Windows | 5.4 |
| #584 | Glyph-run cache | 8.2 |
| #588 | Tiled compositing | 8.3 |
| #615 | The Token Project (umbrella) | 4 |
| #628 | Fewer tool calls: the cheapest path first | 4.1, 4.2 |
| #648 | Craft gap: blind re-judge | 10.1 |
| #662 | Figma interchange verified in Figma | 9.5 |
| #678 | Review process and release cadence | 5.8 |
| #692 | Trailer policy and history purge | 5.8 |
| #719 | Tagged PDF structure tree | 9.1 |
| #720 | Mid-word breaks, off-canvas contrast, halftone paper | 2.6 |
| #721 | Colour font files | 9.2 |
| #722 | Emoji pack destinations | 9.3 |
| #724 | Render and export report the check state | 2.2 |
| #725 | Check results lead with a verdict | 2.1 |
| #726 | Run a named suite in one command | 2.3 |
| #727 | Printer's template as guides | 9.9 |
| #728 | Hand-lettered work stays live text | 6.8 |
| #747 | Pattern texture follows its animated base | 6.2 |
| #748 | Cut-paper grain streaks | 6.1 |
| #749 | Quadruped rig and cycles | 6.7 |
| #750 | Additive and blended motion | 6.6 |
| #751 | Inner shadow, inner glow, bevel | 6.5 |
| #752 | Seamless scrolls and symmetric rotations | 6.3 |
| #753 | A package name agents can guess | 5.1 |
| #754 | Cut-paper frames re-rasterise every hold | 6.4 |
| #756 | Signed Windows updates | 5.6 |
| #763 | Event-poster dead band and stray motif | 3.2 |
| #764 | Every layout passes its checks | 3.3 |
| #765 | Dry-run repair outcome | 2.4 |
| #766 | `font-pair` restyles existing text | 3.4 |
| #767 | Errors name the valid choices | 2.5 |
| #768 | Edited copy reflows | 3.5 |
| #769 | Export quote before rendering | 2.7 |
| #770 | Public hosted MCP service (tracker) | Later |
| #771 | One-click install, directories, macOS | 5.2 |
| #772 | Local alternative to template APIs | 5.9 |
| #773 | Public comparison against design tools | 10.2 |
| #774 | Licence clarity | 5.7 |
| #775 | Previewer for people watching an agent | Later |
| #778 | Address chart marks by data | 7.2 |
| #779 | Chart emphasis | 7.3 |
| #780 | Audit chart edits | 7.1 |
| #818 | SVG import CSS, raster reuse and fallback budget | 12.2 |
| #819 | SVG font metadata resolved before the font limit | 12.2 |
| #820 | REST resource routes reach the global library | 12.6 |
| #821 | REST and Host imports bypass the call limiter | 12.1 |
| #822 | PDF import allocation and recursion budgets | 12.2 |
| #823 | MCP executor queue and job store bound | 12.1 |
| #824 | Durable workflow queue quotas | 12.5 |
| #825 | Caller regexes outlive the hard timeout | 12.4 |
| #826 | MCP HTTP body limit | 12.1 |
| #827 | Network reads overshoot their caps | 12.3 |
| #828 | MCP renders bypass the workspace gate | 12.1 |
| #829 | Link status discloses absolute paths | 12.6 |
| #830 | Fetch redirect and webhook deadlines | 12.3 |

Items without an open issue (remainders of closed issues and deferred work): 3.1, 3.6, 4.3-4.9 (under
#615), 5.5, 8.1, 8.4, 8.5, 8.6, 8.7, 9.6, 9.7, 9.8, 11.1-11.4.
