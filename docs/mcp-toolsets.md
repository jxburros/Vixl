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
| `vixl_reference` | topics: `start` (default), `operations`, `workflows`, `capabilities`, `sizes`, `layouts`, `fonts`, `brushes`, `styles`, `looks`, `color`, `roll`, `palettes`, `templates`, `guidance`, `objects`, `house-style`, a tool name, a guidance name or a free-text brief | Catalogs, exact schemas and craft guidance, all from the one guidance registry (`guidance.py`). |
| `vixl_job` | `status`, `result`, `cancel`, `list` | Calls that outlived the inline wait (about 40 s) or were sent with `as_job`. |

Saved calls, batches and client configurations for the earlier 51 tools convert with `vixl convert-batch`
([Converting](converting.md#convert-saved-tool-calls)).

`vixl mcp --tools ai` serves the provider-backed tools (`vixl_ai_*`, `vixl_models_list`) as a second server that
shares `vixl_document`, `vixl_render` and `vixl_job`; see [interfaces](interfaces.md#mcp).

## Detail on demand

- **Operations.** `vixl_apply` advertises each item as `{type: string}` plus open fields. The exact JSON Schema of any
  operation (fields, enums, requirements, a summary and examples) is `vixl_reference('operations', name=[types])`;
  without a name it lists every operation by purpose.
- **Session steps.** Work that needs the workspace rather than the document is a batch item too, so it joins the
  same all-or-nothing batch: `import-image`, `import-document`, `import-font`, `font-pair`, `font-install`,
  `style-use` and `roll`. Their schemas come from the same lookup.
- **Options.** Each action is a typed function; its parameters beyond the advertised fields go in `options`, and an
  argument a tool does not advertise is folded into `options` for you, so `vixl_render(max_width=200)` and
  `vixl_render(options={max_width: 200})` are the same call. `vixl_reference('vixl_export')` lists every action of a
  tool with its options; `vixl_reference('vixl_export', name='timeline')` one action.
- **Errors teach.** An unknown or mistyped option fails with the closest names and the action's schema; an invalid
  operation fails with the exact schema of each failing operation type, plus the usual `field`, `operation_index`
  and `suggestions`.
- **Prose.** Long explanations live in the guidance registry: `vixl_reference('batches')` (batches, values, steps,
  create, workflows), `vixl_reference('checks')` (every check), `vixl_reference('exports')` (formats, CMYK, PDF,
  slides, motion), `vixl_reference('finishing')`, `vixl_reference('testing')`, and `vixl_reference()` for the
  start-here loop.
- **Terse results.** Results drop large echoes by default (a new document reports its path, canvas, seed and the
  fonts chosen, not the whole rolled direction); `verbose: true` returns the full payload. Previews still return
  images.

## Size and the ratchet

Characters of the compact JSON of each tool object in `tools/list` (name, description and input schema), with an
approximate token count of characters / 4:

| Server | Before (0.26.0) | After |
| --- | ---: | ---: |
| default (`core`, slim schemas) | 51 tools, 66,735 characters | 7 tools, about 7,300 characters (~1,800 tokens) |
| `compact`, slim | 13 tools, 26,577 characters | (removed) |
| `all`, slim | 62 tools, 73,345 characters | (removed) |
| `ai` | 16 tools, 12,016 characters | 14 tools, about 9,400 characters |
| server instructions | 3,945 characters | about 750 characters |

The largest tools used to be the check (6.6k: a description listing every check), the batch (6.3k: the operation
enum) and the file export (5.3k: 36 parameters); the largest now is `vixl_apply` at about 1,800.

`tests/mcp_surface_baseline.json` records the total, the instructions and every tool for both servers, and
`tests/test_mcp_surface.py` fails when any of them grows or a tool exceeds the per-tool cap (2,000 characters).
After shrinking something, lock the gain in:

```bash
python -m scripts.mcp_surface            # current sizes against the baseline
python -m scripts.mcp_surface --update   # lower the baseline; refuses to raise it
python -m scripts.mcp_surface --update --allow-growth   # a deliberate, reviewed increase
```

The same numbers come from `vixl.mcp_tools.surface("default")` (or `"ai"`).
