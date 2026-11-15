# Vixl roadmap

This is the single development plan for Vixl. It replaces the development plan, the implementation plan, the craft
plan and the render-performance decisions that used to live in `docs/project/`; those files are kept, unchanged, in
`docs/project/archive/` as history and are no longer maintained. Everything needed to pick up an item is in this file.

The roadmap was rebuilt on 2026-10-31 against `main` at 0.33.1 and updated for 0.36.0 (stages 1-4, 6, 7 and 12 shipped, with most of stage 9). Every open GitHub issue was read, with its comments,
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

**Close at the end of this stage:** [#543](https://github.com/jxburros/vixl/issues/543) (after the release check
above). #762 and #776 are closed.

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

The gate's exception list is empty since 0.36.0: all 204 layout × size pairs pass at three seeds (#803-#814), and
`tests/test_layout_quality.py` now requires the list to stay empty. On a story, `golden-section` and `split-screen`
set their copy on a `@surface` panel that owns the safe inset; the alternative, a dead-band check that knows the safe
area, would need craft-backtest numbers.

Later (owner decision): font role tokens on layers (`font: "@heading"`), a document-model change; `apply_to` shipped
first.

All issues of this stage (#763, #764, #766, #768, #803-#814) are closed.

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

- **Status (0.36.0):** step 1 and the meta-package source (`distribution/alias_package.py`, an `alias` job that is off
  until the Actions variable `PYPI_ALIAS_PUBLISH` is `true`) are done. Step 2 waits on the owner claiming `vixl` on PyPI.

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

- **Status (0.36.0):** steps 1 and 2 are done (the README table with checked snippets, the `vixl-engine` console script,
  `distribution/mcp_registry.py` and an `mcp-registry` job that is off until `MCP_REGISTRY_PUBLISH`,
  `MCP_PUBLISHER_URL` and `MCP_PUBLISHER_SHA256` are set). Steps 3 and 4 wait on the owner (a Homebrew tap or an Apple
  Developer ID; the directory submissions).

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

- **Status (0.36.0):** the explanatory docs are done (who can use Vixl free, `docs/reference/licensing.md`, "Is Vixl a
  fit?", the licence in the agent bundles). The commercial-licence terms and contact, the notice wording and the
  governance settings wait on the owner and counsel.

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

- **Status (0.36.0):** the migration guide is done, with no services named and no prices. Step 3 (an event-ticket and
  a dedicated OG-card layout) is open: new layouts change what existing seeds roll, so they need the house-style eval.
  Two defects seen while writing it: layout text boxes sized to the sample's ink clip descenders in other rows, and
  `adapt-layout` with `recompose` drops a filled image slot.

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

Shipped in 0.36.0: directionless cut-paper grain with texture controls (6.1, #748), `pattern-fill` and `drawn-texture`
as an effect on the layer they texture (6.2, #747), `wrap` and `symmetry` in the motion check with a `scroll` recipe
(6.3, #752), jitter as an offset on cached pieces with a perf budget (6.4, #754), `inner-shadow`, `inner-glow` and
`bevel` (6.5, #751), additive keyframe layers, blend windows and piecewise samples (6.6, #750), the quadruped rig with
walk, trot, gallop, jump and idle (6.7, #749) and `hand_set` text with span `rise`, `rotate` and `scale` (6.8, #728).

Follow-ups, none with an issue:

- Textured layers export to SVG, PDF and PPTX as a raster fallback; a native SVG `<pattern>`, PDF tiling pattern and
  PPTX picture fill would keep them vector. The conversion kit does not migrate old sibling texture layers.
- `draft` previews are not on the Studio host route (a change to the published host contract) or the CLI.
- `cut-paper` `edge_light` on a piece that ends within a few pixels of the canvas edge under jitter is untested.
- `python -m evals.craft_backtest` has not been run for the new `joint-detached` finding and the refined
  `loop-seam-speed` note.
- A lone PPTX `inner-shadow` is written as PowerPoint's own effect and has not been opened in PowerPoint.
- The optional `source_text` on outlined text (6.8 step 3) is unbuilt; `hand_set` removes most of the reason to outline.

## 11. Stage 7: chart editing by data

Shipped in 0.36.0: the audit (7.1, #780; `docs/project/chart-edit-audit.md`), chart marks addressed by series and
category through the `target-resolver` hook (7.2, #778) and `chart-emphasis` (7.3, #779).

The audit ranks three further edits that still cost several layer operations; each has a "done when" in the audit
page and wants an issue when it is picked up:

- **7.4 Reference and target lines** (`reference_lines` on a chart). C2, P3.
- **7.5 Bare charts for KPI tiles** (`axes: false`). C1, P2.
- **7.6 `chart-data` sort, order and rename by name.** C2, P2.

Not verified: PPTX emphasis in PowerPoint or Keynote (callouts sit at Vixl's layout coordinates over the native chart),
and craft-backtest numbers for the two emphasis findings in `color_vision`.

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

Shipped in 0.36.0: opt-in tagged PDF (9.1, #719; no PDF/UA identifier, and no veraPDF or PAC run yet), colour font
files in text (9.2, #721), emoji pack destinations and animated packs (9.3, #722), printer templates as role guides
with guide sets (9.9, #727), and for 9.4 (#514) a bounded layered PSD import and opt-in editable PSD text.

Left from these:

- **9.4 owner check (#514):** open a `psd_text: "editable"` export in Photoshop or Photopea and confirm the type
  layers are editable (the EngineData layout, tracking and size units and the closing rectangle of the type-tool block
  are unverified). When it holds, make `editable` the default and close #514. Shape and vector layers are still
  "evaluate later".
- **9.3:** the Twitch emote limits and the animated GIF limits of Discord and Slack were not read from the platforms'
  pages; confirm them and set `checked`.
- **9.2:** only the first palette is used, sweep gradients are drawn as wedges, and a translucent text colour does not
  fade a COLR glyph's foreground layers. ZWNJ is still dropped by the bidi pass (Persian).

Handoff to other tools and offline fonts. Several items need one owner session in third-party apps (Figma, Photoshop
or Photopea, a browser player); they can be done together.

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

**Close at the end of this stage:** [#514](https://github.com/jxburros/vixl/issues/514) (after the owner check),
[#662](https://github.com/jxburros/vixl/issues/662). #719, #721, #722 and #727 are closed.

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

Shipped in 0.36.0, all thirteen findings: every heavy service path through the call limiter, a bounded MCP queue and
job store and an MCP HTTP body limit (12.1; #821, #823, #826, #828), cumulative budgets for editable SVG and PDF
import with service font installation off by default (12.2; #818, #819, #822), network reads that stop at their caps
and deadlines (12.3; #827, #830), bounded caller regular expressions with the optional `re2` extra (12.4; #825),
queue quotas and one worker per queue (12.5; #824) and workspace isolation for REST resources and link paths (12.6;
#820, #829).

Follow-ups, none with an issue:

- CI has no job that installs the `re2` extra, so the RE2 tests skip there; the container image installs
  `vixl-engine[server,pdf]` without it.
- The Host import route has no `install_fonts` parameter, and the Figma import plugin still installs fonts by default.
- A workspace catalog still inherits the user resource library read-only; a served deployment that should inherit
  nothing points `VIXL_RESOURCES` at an empty file.
- The worker lock is untested on Windows.

## 17. Later and exploratory

Not scheduled. Each needs either an earlier item or an owner decision before it is worth starting. Close each issue
when its item ships, or as not planned if the owner decides against it:
[#522](https://github.com/jxburros/vixl/issues/522),
[#770](https://github.com/jxburros/vixl/issues/770), [#775](https://github.com/jxburros/vixl/issues/775).

### Detect and classify objects in existing documents (#383)

Shipped in 0.36.0 as the `object_detect` plugin (`object-detect`, `vixl object detect`): deterministic proposals from
recipes, names and touching part-named layers, applied only on request. Left: unnamed piles get no proposal (names are
the primary signal), the provider step for raster images is opt-in and was tested only with a mocked provider, and the
issue's acceptance on the VixlExamples gallery documents was not run.

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

Every issue still open after 0.36.0 that the roadmap plans, with where each is finished. #797 (agent setup) is also
open: the docs and `vixl guide --brief` shipped in 0.36.0, and what is left is the repository's `.mcp.json` starting
the server with `uvx`, which never puts `vixl` on PATH (an install-pin and environment decision for the owner).

| Issue | Item | Stage |
| --- | --- | --- |
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
| #753 | A package name agents can guess | 5.1 |
| #756 | Signed Windows updates | 5.6 |
| #770 | Public hosted MCP service (tracker) | Later |
| #771 | One-click install, directories, macOS | 5.2 |
| #772 | Local alternative to template APIs | 5.9 |
| #773 | Public comparison against design tools | 10.2 |
| #774 | Licence clarity | 5.7 |
| #775 | Previewer for people watching an agent | Later |

Items without an open issue (remainders of closed issues and deferred work): 3.1, 3.6, 4.3-4.9 (under
#615), 5.5, 8.1, 8.4, 8.5, 8.6, 8.7, 9.6, 9.7, 9.8, 11.1-11.4.
