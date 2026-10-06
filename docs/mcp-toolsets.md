# MCP toolset evaluation

`vixl mcp` serves `--tools core --schema slim` by default, the recommended configuration for most agents; `--tools compact --schema slim` is the smallest surface when tool-discovery context matters most. Keep one atomic editing tool and load exact operation fields on demand. This avoids splitting an edit across several transaction boundaries, while task-aware `vixl_capabilities` supplies relevant operations and gotchas.

Measured on the 0.21.0 implementation using serialized `tools/list` tool objects (compact JSON, including input schemas; characters, not model tokens):

| Toolset | Schema | Tools | Characters |
| --- | --- | ---: | ---: |
| all | full | 61 | 123,682 |
| all | slim | 61 | 55,675 |
| core | full | 50 | 117,061 |
| core | slim | 50 | 49,054 |
| compact | full | 12 | 85,146 |
| compact | slim | 12 | 17,139 |
| ai | full | 16 | 10,367 |
| ai | slim | 16 | 10,367 |

Reproduce by constructing `build_server(Session(workspace=...), tools=MODE, schema=SCHEMA)`, awaiting `list_tools()`, and measuring `json.dumps([t.model_dump(exclude_none=True) for t in tools], separators=(',', ':'))`. Values change as tools evolve; the schema size tests guard against unbounded growth.

Recommendation: keep the default `--tools core --schema slim` (dedicated review, font, spatial and animation tools, operation fields on demand). Use `--tools compact --schema slim` when the tool list must be smallest. Provider-backed tools run separately with `--tools ai`. Clients that relied on the earlier default (0.21 and before) pass `--tools all --schema full` (or set `VIXL_MCP_TOOLS=all` and `VIXL_MCP_SCHEMA=full`). Compact callers access workflow actions and fetch exact fields through `vixl_operation_schema`; the canonical runtime validates the complete operation regardless of advertised schema mode.

The 0.21.0 review of the tool list removed one duplicate: the MCP text-adding tool did nothing a `text` operation in `vixl_operations_apply` does not (a registered font name works there too). The `vixl_guide("capabilities …")` alias of `vixl_capabilities` is gone as well. A call to the removed text tool fails with an error that names its replacement, `vixl_guide("capabilities …")` fails pointing to `vixl_capabilities(topic)`, a tool that another `--tools` mode serves names that mode, and a misspelled tool name gets the closest names. Tools that look alike but answer different questions now say so in their descriptions: `vixl_animation_inspect` / `vixl_animation_preview` cover frame-by-frame animation (saved frames), `vixl_timeline_inspect` / `vixl_timeline_preview` keyframed motion; `vixl_validate` checks rules and suites, `vixl_check` the rendered design; `vixl_measure_spacing` is a pass/fail gap check, `vixl_spatial` the open-ended layout query; `vixl_guide` says what to make and `vixl_capabilities` gives field-level reference. `vixl_operations_apply` takes `check` and `preview`, so the common apply → check → preview loop is one call.

Consolidation keeps aliases in one normalization registry, removes duplicate transform implementations, derives extension CLI flags from the canonical schema, and factors repeated constraints in the full MCP schema without dropping those constraints. Legacy spellings still normalize and are reported in results. Native JSON operation batches are shared by CLI, Python, REST and MCP; service filesystem restrictions remain explicit.

Recommendation: retain these selectable toolsets and on-demand schemas rather than add one MCP tool per operation. A focused-tool experiment should compare the same held-out briefs for invalid-field retries, calls, schema tokens and completion rate before adding tools. The core/slim default rests on discovery-size savings and the 0.20 live comparison (`eval-results/`), in which agents used core/slim; it does not by itself establish lower model error rates.
