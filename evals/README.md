# Agent evaluation suite

Vixl is a headless application designed for autonomous AI agents; humans can use the same interfaces.

Vixl is used mostly by AI agents, so the test that matters most is whether an agent can finish
real design briefs through the MCP tools, and at what cost. This suite measures that.

Each task in `tasks/` is a JSON file with:

- `prompt` — the brief given to the agent, exactly as a user might write it;
- `setup` — optional starting files (generated images, pre-built `.vixl` documents with history);
- `checks` — programmatic success criteria evaluated on the files the agent leaves behind
  (`canvas`, `layer`, `design` (runs `check_design`), `spacing`, `centered`, `layer_field`,
  `variable`, `file`, `files_differ`, `assert`);
- `reference` — a scripted tool-call solution, used to prove the task is solvable and the checks
  are correct.

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

## Adding tasks

Write the brief the way a person would, keep checks objective (geometry, text, files, design
checks — not taste), include a reference solution, and run `pytest tests/test_eval_harness.py`:
it verifies that the reference passes and that an idle agent fails.

## Stored baseline and weekly comparison

There are 16 briefs: the original eight plus layouts, font pairing, applied rolls, templates,
CMYK export, timelines, checked workflow edits, and editable SVG imports. Font tasks populate
an isolated temporary font cache with the bundled DejaVu font under the requested pairing's
cache names. This tests pairing installation/registration and agent tool usage offline, not the
appearance or availability of Google Fonts. Live runs use the same fixtures for comparability.

```bash
python -m evals.run --schema full --tools core --baseline evals/baseline.json
python -m evals.run --schema slim --tools core --baseline evals/baseline.json
```

`baseline.json` stores required task passes, derived from working reference solutions. A missing
or failed baseline task fails the run. It is an acceptance baseline, not a fabricated measurement
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

Both schema modes pass all 16 reference tasks. Recommend `--tools core --schema slim` for new
setups, while keeping the existing full/all default until live model results justify a change.
Reference replay cannot measure whether a model discovers the right operation fields.
