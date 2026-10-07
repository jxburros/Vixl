# Agent evaluation suite

Vixl is a headless application designed for autonomous AI agents; humans can use the same interfaces.

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
  count, slide text and speaker notes; layer matches can test a field's `field_key` and `field_kind`);
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
| tool result tokens | approximate size of what the tools sent back (chars ÷ 4) |
| input / output tokens | from the API's usage, including cache reads |

## Running

```bash
pip install -e ".[dev]"

# Offline: replay reference solutions (no API key, also runs in pytest/CI)
python -m evals.run

# Claude through the official Anthropic SDK (spends API credits)
export ANTHROPIC_API_KEY=...        # or `ant auth login`
python -m evals.run --agent claude
python -m evals.run --agent claude --model claude-sonnet-5-5 --effort low --schema slim --tasks "photo-*"
```

Results go to `eval-results/results.json` (full traces) and `eval-results/report.md`; `--keep`
also saves each task's final workspace files for inspection. The **Agent eval** GitHub workflow
runs the same command on demand with the `ANTHROPIC_API_KEY` repository secret and uploads the
results.

The Claude agent uses a manual tool-use loop: assistant turns are appended unchanged (so thinking
blocks stay valid), parallel tool results return in a single user message, prompt caching is on,
and server-side refusal fallbacks (`fallbacks: "default"`) are enabled unless `--no-fallbacks`.

## Using it

Run the suite before and after changing tool descriptions, schemas, error messages, response
formats or normalization rules, and compare success rate, round trips and tokens. Run it with
`--schema full` and `--schema slim` to decide which mode suits a given model. When agents fail a
task, read the trace in `results.json`: repeated tool errors usually point at a confusing schema
or message, which is a product bug.

## Comparing Vixl with other tools

This suite measures agents using Vixl. To compare Vixl with the other ways an agent can make the
same thing (HTML and SVG, Python libraries, free desktop tools, image generation, Claude Design),
use the hand-run [tool comparison kit](tool-comparison/README.md): 16 briefs, judging notes with
answer keys, fixtures and an output inspector.

## Adding tasks

Write the brief the way a person would, keep checks objective (geometry, text, files, design
checks — not taste), include a reference solution, and run `pytest tests/test_eval_harness.py`:
it verifies that the reference passes and that an idle agent fails.

## Stored baseline and weekly comparison

There are 26 briefs: the original eight plus layouts, font pairing, applied rolls, templates,
CMYK export, timelines, checked workflow edits, editable SVG imports, a fillable registration
form, batch form filling with a bad row, and (added after the 0.20 tool comparison) a chart whose
value is corrected in place, a three-slide deck exported to PPTX and PDF, a sketch photo
vectorized as a drawing, an organic flower, a pathfinder badge with a see-through hole, a seamless
spinner loop, a promo adapted to two sizes, and a `targets` fan-out edit in one atomic batch. Font tasks populate
an isolated temporary font cache with the bundled DejaVu font under the requested pairing's
cache names. This tests pairing installation/registration and agent tool usage offline, not the
appearance or availability of Google Fonts. Live runs use the same fixtures for comparability.

```bash
python -m evals.run --schema full --tools core --baseline evals/baseline.json
python -m evals.run --schema slim --tools core --baseline evals/baseline.json
```

`baseline.json` stores required task passes, derived from working reference solutions. A missing
or failed baseline task fails the run. It also stores a tool-call budget per task
(`tool_call_budgets`: about twice the calls the recorded live run needed, at least 10) and a ceiling
on the mean (`max_mean_tool_calls`): calls per task are the cost measure, so a run over either is
reported as a regression. Reports show the mean and the largest number of calls per task. It is an acceptance baseline, not a fabricated measurement
of Claude success rate. `state_field` checks inspect nested persisted document fields; `file`
checks can also require an image mode (for example CMYK).

The Agent eval workflow runs every Monday at 15:00 UTC, checking the offline baseline and then
running full/core and slim/core live evaluations if `ANTHROPIC_API_KEY` is configured. Missing
credentials are reported explicitly; no live score is claimed. Results and traces are retained
as workflow artifacts. Set `model`/`effort` with a manual run to compare a specific model.

Current deterministic tool-context measurements (compact JSON characters divided by four):

| Schema / tool set | Tools | Estimated schema tokens |
| --- | ---: | ---: |
| full / all | 53 | 12,789 |
| full / core | 42 | 11,644 |
| slim / all | 53 | 8,043 |
| slim / core | 42 | 6,898 |

Both schema modes pass every reference task. `vixl mcp` and `python -m evals.run` default to
`--tools core --schema slim`; pass `--tools all --schema full` to measure the old default.
Reference replay cannot measure whether a model discovers the right operation fields.

## House-style eval

`evals/house_style.py` measures what Vixl makes from a sparse brief, with no agent: 48 briefs (six each for
poster, social, slides, document, form, diagram, logo and motion, copy only) are rolled at each variety
level, applied to a document of the purpose's size, checked and rendered. It runs offline in about two
minutes per level (fonts come from a temporary cache holding the bundled font under each pairing's names,
so it measures installation, not typeface design).

```bash
python -m evals.house_style                                   # every brief at low, medium and high
python -m evals.house_style --compare evals/house-style-baseline.json   # exit 1 on a regression
python -m evals.house_style --house-style 1                   # the 0.20-0.22 rolls, for a before/after
python -m evals.house_style --limit 8 --levels medium         # a quick look
```

**Diversity** is the entropy in bits of the rolled palette, layout, mode, pairing, look and style; the mean
pairwise distance of 48 px renders (`image dist.`, dominated by light against dark); the same distance
within one mode (`same-mode dist.`); and `structure dist.`, one minus the correlation of normalised
lightness maps (the arrangement, whatever the colours). **Quality** is the share of designs with no `fix`
finding from `check`, with their fonts installed and passing the contrast check. `--compare` fails when a
quality share falls or a level's diversity falls by more than the baseline's tolerance; a deliberate
change updates `house-style-baseline.json` in the same commit. `tests/test_house_style.py` runs four
briefs at two levels as part of the test suite.

Before and after the 0.23 house style (the same seeds; "before" is `--house-style 1`):

| Level | palette | layout | mode | pairing | look | style | image | same-mode | structure | no fix |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| low, before | 3.83 | 3.66 | 0.98 | 3.92 | 1.00 | 1.57 | 0.372 | 0.056 | 1.006 | 1.0 |
| low, after | 4.99 | 3.90 | 0.87 | 3.94 | 1.40 | 2.84 | 0.371 | 0.092 | 0.965 | 1.0 |
| medium, before | 3.83 | 3.66 | 0.98 | 3.92 | 1.93 | 1.57 | 0.372 | 0.057 | 1.005 | 1.0 |
| medium, after | 5.19 | 4.16 | 0.87 | 4.61 | 1.58 | 3.71 | 0.367 | 0.100 | 0.968 | 1.0 |
| high, before | 3.83 | 3.66 | 0.99 | 3.92 | 1.92 | 1.58 | 0.386 | 0.059 | 1.003 | 1.0 |
| high, after | 5.19 | 4.21 | 0.87 | 4.97 | 1.75 | 4.37 | 0.363 | 0.126 | 0.986 | 1.0 |

Fonts and contrast pass everywhere. On the 0.22.1 code itself one brief (a LinkedIn post) failed its
legibility check at every level (no-fix share 0.979); the rolled-layout thumbnail fix brings it to 1.0.
Mode and look entropy fall on purpose: documents, forms, slides and logos are mostly light and carry no
finishing look (decisions D2 and F1), which also lowers the raw image distance. Within a mode, designs
are about twice as far apart, and every measure but mode rises from low to high.
