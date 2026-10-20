# MCP tool surface

Every agent that connects to `vixl mcp` reads the tool list and the server instructions before it does anything, and
pays for them in context on every turn. Vixl keeps that surface small by consolidation: seven verb tools, each with a
handful of typed common fields and an `options` object, with the detail served on demand.

| Tool | Actions (`action`, or `kind` for exports) | What it covers |
| --- | --- | --- |
| `vixl_document` | `inspect` (default), `create`, `open`, `close`, `list`, `history`, `undo`, `redo`, `checkpoint`, `checkout`, `branch`, `begin`, `commit`, `rollback`, `compact`, `notes` | Documents, the workspace listing, history and human review notes. `create` takes a named `size`, `width`/`height`, a `purpose` or a `template`. |
| `vixl_apply` | a batch (default), `create={…}`, `workflow=ACTION` | Atomic operation batches with `check`, `suites`, `preview`, `repair` and `dry_run`; a whole new piece in one call (`create`, formerly compose); every production workflow (`request`). |
| `vixl_check` | `design` (default), `validate`, `measure`, `spacing`, `spatial`, `pixels` | Tests without looking: design checks with rule IDs and repairs, rule and suite validation, rendered colour samples, equal-gap pass/fail, spatial relations, pixel rows. |
| `vixl_render` | `preview` (default), `compare`, `timeline`, `timeline-inspect`, `animation`, `animation-inspect` | Bounded PNG previews (`region`, `page`, `time`, `isolate`, `overlay`), revision comparison, motion contact sheets and summaries. |
| `vixl_export` | `file` (default), `batch`, `animation`, `timeline`, `audio`, `icons`, `character` | Files: the format follows the extension, and the kind follows the extension and the document (`.wav` is audio, `.gif`/`.mp4` motion, `targets` a batch). |
| `vixl_reference` | topics: `start` (default), `guide`, `operations`, `workflows`, `capabilities`, `sizes`, `layouts`, `fonts`, `brushes`, `styles`, `looks`, `color`, `roll`, `palettes`, `templates`, `guidance`, `objects`, `house-style`; or a tool name with actions (all but `vixl_job`), a kind of work, a guidance name (`checks`, `exports`, `batches` …) or a free-text brief | Catalogs, exact schemas and craft guidance, all from the one guidance registry (`guidance.py`). |
| `vixl_job` | `status`, `result`, `cancel`, `list` | Calls that outlived the inline wait (about 40 s) or were sent with `as_job`. |

Saved calls, batches and client configurations for the earlier tools (51 in the default server, 64 names in all) convert
with `vixl convert-batch` ([Converting](converting.md#convert-saved-tool-calls)).

`vixl mcp --tools ai` serves the provider-backed tools (`vixl_ai_*`, `vixl_models_list`) as a second server that
shares `vixl_document`, `vixl_render` and `vixl_job`; see [interfaces](interfaces.md#mcp).

## Detail on demand

- **Operations.** `vixl_apply` advertises each item as `{type: string}` plus open fields. The exact JSON Schema of any
  operation (fields, enums, requirements, a summary and examples) is `vixl_reference('operations', name=[types])`;
  without a name it lists every operation by purpose.
- **Session steps.** Work that needs the workspace rather than the document is a batch item too, so it joins the
  same all-or-nothing batch: `import-image`, `import-document`, `import-font`, `font-pair`, `font-install`,
  `font-cover`, `style-use` and `roll`. Their schemas come from the same lookup.
- **Options.** Each action is a typed function; its parameters beyond the advertised fields go in `options`, and an
  argument a tool does not advertise is folded into `options` for you, so `vixl_render(max_width=200)` and
  `vixl_render(options={max_width: 200})` are the same call. `vixl_reference('vixl_export')` lists every action of a
  tool with its options (every tool but `vixl_job`, which has none); `vixl_reference('vixl_export', name='timeline')` one action.
- **Errors teach.** An unknown or mistyped option fails with the closest names and the action's schema; an invalid
  operation fails with the exact schema of each failing operation type, plus the usual `field`, `operation_index`
  and `suggestions`. `vixl_job` and the `vixl_ai_*` tools have no `options`: an argument they do not take is ignored with
  a warning that names the closest parameter.
- **Prose.** Long explanations live in the guidance registry: `vixl_reference('batches')` (batches, values, steps,
  create, workflows), `vixl_reference('checks')` (every check), `vixl_reference('exports')` (formats, CMYK, PDF,
  slides, motion), `vixl_reference('finishing')`, `vixl_reference('testing')`, and `vixl_reference()` for the
  start-here loop.
- **Terse results.** Results drop large echoes by default (a new document reports its path, canvas, seed and the
  fonts chosen, not the whole rolled direction); `verbose: true` on `vixl_document` and on a `vixl_apply` batch
  returns the full payload. Previews still return images.

## Size and the ratchet

Characters of the compact JSON of each tool object in `tools/list` (name, description and input schema), with an
approximate token count of characters / 4:

| Server | Before (the 51-tool server) | After |
| --- | ---: | ---: |
| default (`core`, slim schemas) | 51 tools, 66,535 characters | 7 tools, 7,329 characters (~1,830 tokens) |
| `compact`, slim | 13 tools, 26,462 characters | (removed) |
| `all`, slim | 62 tools, 73,145 characters | (removed) |
| `ai` | 16 tools, 12,016 characters | 14 tools, 9,438 characters (~2,360 tokens), without `--planner` |
| server instructions | 3,979 characters | 735 characters (716 on the `ai` server) |

The "before" figures are from Python 3.13; 3.11 and 3.12 sent docstring indentation as well and measured about 1,400
characters more. The "after" figures are the same on every Python.

The largest tools used to be the check (6.8k: a description listing every check), the batch (6.6k: the operation
enum) and the file export (5.3k: 36 parameters); the largest now is `vixl_apply` at 1,832.

`tests/mcp_surface_baseline.json` records, for both servers, the total, the instructions and every tool (characters,
with token estimates). `tests/test_mcp_surface.py` fails when the total, the instructions or any single tool is larger
than its baseline (a new tool counts as growth), when a tool exceeds the per-tool cap (2,000 characters), and when the
default server is no longer the seven tools within 12,000 characters and 1,000 characters of instructions. A smaller
surface needs nothing; lock the gain in so it cannot creep back:

```bash
python -m scripts.mcp_surface            # current sizes against the baseline; exit 1 on growth or a tool over the cap
python -m scripts.mcp_surface --update   # rewrite the baseline with the current sizes; refuses when anything grew
python -m scripts.mcp_surface --update --allow-growth   # a deliberate, reviewed increase
```

`--allow-growth` raises the baseline only: a tool over the 2,000-character cap still fails the test.

The same numbers come from `vixl.mcp_tools.surface("default")` (or `"ai"`).
