# Agent evaluation suite

Vixl is a headless design engine for AI agents; people can drive the same interfaces.

Vixl is used mostly by AI agents, so the test that matters most is whether an agent can finish
real design briefs through the MCP tools, and at what cost. This suite measures that.

Each task in `tasks/` is a JSON file with:

- `prompt` — the brief given to the agent, exactly as a user might write it;
- `setup` — optional starting files (generated images, optionally with pen `lines` drawn on them
  as a stand-in for a sketch photo, and pre-built `.vixl` documents with history);
- `checks` — programmatic success criteria evaluated on the files the agent leaves behind
  (`canvas`, `layer`, `design` (runs `check_design`; `forbid` lists issue codes that fail it at any
  severity), `spacing`, `centered`, `layer_field` (a key or a path such as `["chart", "kind"]`),
  `variable`, `state_field`, `animated` (a layer has a changing timeline track), `pixel` (alpha at a
  point of the render), `file` (optionally `image_size`, `image_mode` or text it `contains`),
  `files_differ`, `assert`, `pdf_fields` for a PDF's form fields and page count, and `pptx` for slide
  count, slide text and speaker notes; `craft` scores the finished document's craft (below); layer matches can test a field's `field_key` and `field_kind`;
  `object` checks a declared object: its `kind` (or a kind below it), `complete` (no missing required
  parts), `parts` and `sub_objects` it must have, and `connected` (no part floating free));
- `reference` — a scripted tool-call solution, used to prove the task is solvable and the checks
  are correct. A step with `save_as: NAME` keeps its JSON result, and a later argument
  `"${NAME.key}"` uses a value from it (an imported image's `asset`, for example).

The harness (`harness.py`) starts the real MCP server in-process on a fresh temporary workspace
per task, runs an agent, grades the workspace, and records:

| Metric | Meaning |
| --- | --- |
| success | every check passed |
| round trips | model calls (one per assistant turn) |
| tool calls / tool errors | MCP calls made, and how many returned an error |
| retries | calls that repeat the previous call's tool right after it returned an error |
| tool result tokens | approximate size of what the tools sent back (chars ÷ 4) |
| craft score | for a task with a `craft` check: 1 minus the share of `max_findings` the composition checks find in the delivered document (0-1; see [the craft grader](#craft-grader-and-judge)) |
| input / output tokens | from the API's usage, including cache reads |

## Running

```bash
pip install -e ".[dev]"

# Offline: replay reference solutions (no API key, also runs in pytest/CI)
python -m evals.run

# Claude through the official Anthropic SDK (spends API credits)
export ANTHROPIC_API_KEY=...        # or `ant auth login`
python -m evals.run --agent claude
python -m evals.run --agent claude --model claude-sonnet-5-5 --effort low --tasks "photo-*"
```

Results go to `eval-results/results.json` (full traces) and `eval-results/report.md`; `--keep`
also saves each task's final workspace files for inspection. The **Agent eval** GitHub workflow
runs the same command on demand with the `ANTHROPIC_API_KEY` repository secret and uploads the
results.

`--judge` adds a model's rubric score for every task with a `craft` check (off by default; see [the craft grader](#craft-grader-and-judge)).

The Claude agent uses a manual tool-use loop: assistant turns are appended unchanged (so thinking
blocks stay valid), parallel tool results return in a single user message, prompt caching is on,
and server-side refusal fallbacks (`fallbacks: "default"`) are enabled unless `--no-fallbacks`.

## Using it

Run the suite before and after changing tool descriptions, schemas, error messages, response
formats or normalization rules, and compare success rate, round trips and tokens. When agents fail a
task, read the trace in `results.json`: repeated tool errors usually point at a confusing schema
or message, which is a product bug.

## Comparing Vixl with other tools

This suite measures agents using Vixl. To compare Vixl with the other ways an agent can make the
same thing (HTML and SVG, Python libraries, free desktop tools, image generation, Claude Design),
use the hand-run [tool comparison kit](https://github.com/jxburros/VixlExamples/blob/main/evals/tool-comparison/README.md): 16 briefs, judging notes with
answer keys, fixtures and an output inspector.

## Craft re-run

The [craft plan](../docs/project/craft-plan.md) measures craft by re-running the Vixl lane of the tool comparison and
judging it blind against the same web-code and Python runs. `evals/craft_rerun.py` makes that a routine:

```text
python -m evals.craft_rerun --dry-run                      # the plan and both prompts; no API calls, nothing written
python -m evals.craft_rerun                                # all 16 briefs, rounds 1 and 2 (spends API credits)
python -m evals.craft_rerun --tests T02,T08 --model claude-opus-5-5 --effort high
python -m evals.craft_rerun --package-only --runs PATH     # package a finished re-run again
```

The kit lives in VixlExamples (`evals/tool-comparison/`): pass `--examples PATH`, set `VIXL_EXAMPLES`, or clone
VixlExamples beside this repository. For each brief the script:

1. makes a fresh workspace that mirrors the repository paths the brief uses: the brief, its fixtures (the song for
   T14 and the photo for T10 are generated or copied here, never in the kit) and `skills/vixl/`;
2. runs round 1 with the kit's own kickoff prompt and lane rule V, plus "Save your .vixl document(s) in the
   workspace.", through the agent harness (`ClaudeAgent`, the in-process MCP
   server); the run has no shell, so two text-file tools (`read_text_file`, `write_text_file`, text formats only)
   stand in for "small scripts for reading inputs" and for writing `REPORT.md`;
3. runs round 2 in a fresh session on the same workspace with the change request from `TESTS.md`;
4. copies the run folder to `<kit>/runs-<date>-<version>/<test>/claude-V/` (round 2 in `round2/`), with the lane's
   sources in `src/`: every `.vixl` document the agent left elsewhere in the workspace, `batches.json` (each
   operation batch it applied), `trace.json` (every tool call) and `run.json` (model, effort, Vixl version, calls,
   tokens, missing deliverables and any round-1 file that round 2 changed);
5. copies the other lanes unchanged from the last blind re-judging (`rejudge-*/packages/<test>.zip` decoded with its
   `sealed/key.csv`; `--fixed` takes another rejudge folder, or a `runs/` folder whose lanes are already built).

Then it calls the kit's `rejudge.py` to build the blind packages in `<kit>/rejudge-<date>-<version>/` (zipped per
test in `packages/`, the key in `sealed/key.csv`) and prints the prompt from `JUDGING.md` with the package paths.
Packaging needs what `rejudge.py` needs: Pillow, pypdf, Playwright with Chromium, `pdftoppm`, LibreOffice and
ffmpeg. Judge with three judges as in the kit's `rejudge-2026-10-12/README.md`.

The script sends no nudges and keeps no time box beyond `--max-turns` (60 by default); `run.json` lists the
deliverables each round did not produce. Commit the new runs folder in VixlExamples with its `.vixl` sources:
VixlExamples does not ignore `*.vixl` (only this repository does), so no `.gitignore` exception is needed there.
`tests/test_craft_rerun.py` exercises the layout, source capture and packaging call offline with a scripted agent.

## Adding tasks

Write the brief the way a person would, keep checks objective (geometry, text, files, design
checks — not taste), include a reference solution, and run `pytest tests/test_eval_harness.py`:
it verifies that the reference passes and that an idle agent fails.

## Stored baseline and weekly comparison

There are 35 briefs: the original eight plus four craft briefs (below), layouts, font pairing, applied rolls, templates,
CMYK export, timelines, checked workflow edits, editable SVG imports, a fillable registration
form, batch form filling with a bad row, and (added after the 0.20 tool comparison) a chart whose
value is corrected in place, a three-slide deck exported to PPTX and PDF, a sketch photo
vectorized as a drawing, an organic flower, a pathfinder badge with a see-through hole, a seamless
spinner loop, a promo adapted to two sizes, a `targets` fan-out edit in one atomic batch, and five object briefs (a potted
cactus, a dog, a guitar, a person playing a guitar, and a pile of loose shapes declared one cat). Font tasks populate
an isolated temporary font cache with the bundled DejaVu font under the requested pairing's
cache names. This tests pairing installation/registration and agent tool usage offline, not the
appearance or availability of Google Fonts. Live runs use the same fixtures for comparability.

```bash
python -m evals.run --baseline evals/baseline.json
```

`baseline.json` stores required task passes, derived from working reference solutions. A missing
or failed baseline task fails the run. It also stores a tool-call budget per task
(`tool_call_budgets`: about twice the calls the recorded live run needed, at least 10) and a ceiling
on the mean (`max_mean_tool_calls`): calls per task are the cost measure, so a run over either is
reported as a regression. `craft_scores` stores a floor per craft task and `min_mean_craft_score` one for their mean: a
reference solution that scores lower means a check or a default changed what a finished page looks like, which is how a
craft regression fails `--baseline`. Reports show the mean and the largest number of calls per task, and the craft score. It is an acceptance baseline, not a fabricated measurement
of Claude success rate. `state_field` checks inspect nested persisted document fields; `file`
checks can also require an image mode (for example CMYK).

The Agent eval workflow runs every Monday at 15:00 UTC, checking the offline baseline and then
running a live evaluation if `ANTHROPIC_API_KEY` is configured. Missing
credentials are reported explicitly; no live score is claimed. Results and traces are retained
as workflow artifacts. Set `model`/`effort` with a manual run to compare a specific model.

The agent sees the seven-tool server (about 1,800 estimated tokens of tool list; see
[MCP tool surface](../docs/reference/mcp-toolsets.md), whose ratchet keeps it from growing). Reference replay cannot measure
whether a model discovers the right operation fields and options through `vixl_reference`; live runs can.

## Craft grader and judge

Four sparse briefs (`craft-poster-event`, `craft-menu-prices` with tab stops and dot leaders, `craft-report-cover`,
`craft-social-quote`) say what to make and nothing about how it should look. Each has the usual content checks and a
`craft` check, and a reference solution that scores 1.0. The check runs the composition family on the document the agent
leaves (`project.check(checks=["composition"], waivers=False)`: the spacing codes and the hierarchy codes `flat_hierarchy`,
`single_weight`, `no_focal` and `accent_unused`), counts every `review` finding, waived or not, and reports

- `score`: `1 - min(1, findings / max_findings)` (`max_findings` defaults to 4);
- a pass when no finding has a code in `forbid` and the score reaches `min_score` (default 1.0);
- in `detail`, each finding's code, layers and region, so a failing run says where.

```json
{"type": "craft", "forbid": ["flat_hierarchy", "no_focal"], "max_findings": 3, "min_score": 0.75}
```

The reference solutions set their pairing from the task's offline font cache (`setup.font_pairings`), so the page is
set in the same faces with or without a network, and each carries `stripped`, a batch that takes the craft out of the
finished document (every text at the body size). `tests/test_eval_harness_craft.py` checks that the reference scores 1.0
and the stripped version falls below the threshold, offline. The craft check is deterministic and cheap; it measures
what the checks can measure, not taste.

`python -m evals.run --agent claude --judge` adds the part that is taste: for each task with a craft check it renders the
document at delivery size (at most 1568 px on the long side) and asks a model to score it 1-5 on the rubric of the craft
re-judging (hierarchy, spacing, type, colour, motif, finish; `evals/judge.py`). `--judge-model` picks the model (default
`--model`); `--judge-endpoint`, or `VIXL_JUDGE_ENDPOINT`, points it at any server that speaks the Anthropic Messages API.
The scores, the judge's notes and the judged images are stored beside the run (`judge.json`, `judge/TASK.png`, the
`judge` key of each result and `mean_judge_score` in the summary). The judge costs one model call per craft task, moves
with the judge (so it is not part of the stored baseline), is never used by the Agent eval workflow or the tests (they
give it a scripted client), and a failed call or an unreadable reply is recorded as an error, not a failed run. No
re-judging has been run with it: it measures nothing until someone does.

## House-style eval

`evals/house_style.py` measures what Vixl makes from a sparse brief, with no agent: 48 briefs (six each for
poster, social, slides, document, form, diagram, logo and motion, copy only) are rolled at each variety
level, applied to a document of the purpose's size, checked and rendered. It runs offline in about two
minutes per level (fonts come from a temporary cache holding the bundled font under each pairing's names,
so it measures installation, not typeface design).

```bash
python -m evals.house_style                                   # every brief at low, medium and high
python -m evals.house_style --compare evals/house-style-baseline.json   # exit 1 on a regression
python -m evals.house_style --limit 8 --levels medium         # a quick look
```

**Diversity** is the entropy in bits of the rolled palette, layout, mode, pairing, look and style; the mean
pairwise distance of 48 px renders (`image dist.`, dominated by light against dark); the same distance
within one mode (`same-mode dist.`); and `structure dist.`, one minus the correlation of normalised
lightness maps (the arrangement, whatever the colours). **Quality** is the share of designs with no `fix`
finding from `check`, with no `composition` finding (`no composition`: dead bands, margin drift, uneven rhythm,
crowding, clumped scatter, flat type hierarchy, one weight, no focal point or an unused accent, the craft the checks measure; see [the craft backtest](craft_backtest/README.md)), with
their fonts installed and passing the contrast check. `--compare` fails when a
quality share falls or a level's diversity falls by more than the baseline's tolerance; a deliberate
change updates `house-style-baseline.json` in the same commit. `tests/test_house_style.py` runs four
briefs at two levels as part of the test suite.

Since the composition checks, every rolled design at every level is free of
composition findings (`no composition` 1.0 at low, medium and high), so a default change that adds a dead band,
two left margins, a flat type scale or a crowded rule to rolled designs fails `--compare`. The four hierarchy codes left it at 1.0
(measured before and after adding them). The baseline was refreshed with that column;
the high level's diversity mean (3.73) had already fallen 0.08 below the stored 0.23 value (3.81) before the
column was added, and the refreshed baseline records the current house style.

## Craft backtest

`python -m evals.craft_backtest` runs the composition checks on reconstructions of the 16 round-1 Vixl documents
of the tool comparison and scores them against the defects the blind judges named: per kind, how many expected
defects it catches and misses, and how many findings match no judged defect. `tests/test_craft_backtest.py` pins
the numbers. How each document was rebuilt, and why it is not the original, is in
[craft_backtest/README.md](craft_backtest/README.md).

## Render parity

`python -m evals.render_parity` renders text, shapes, strokes, gradients, blends, blur, shadows, rotation and image
scaling with Vixl and with headless Chromium (same font file, sizes and colours) and measures both, against each
other and against exact supersampled references. It needs `pip install playwright` and writes images and a report
to `render-parity-results/`. See [render_parity/README.md](render_parity/README.md) and the findings in
[docs/project/render-parity.md](../docs/project/render-parity.md).
