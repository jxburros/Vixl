# MCP toolset evaluation

The existing compact server with slim schemas is the recommended configuration when minimizing tool-discovery context matters. Keep one atomic editing tool and load exact operation fields on demand. This avoids splitting an edit across several transaction boundaries, while task-aware `vixl_capabilities` supplies relevant operations and gotchas.

Measured after adding `vixl_compose` (next release) using serialized `tools/list` tool objects (compact JSON, including input schemas; characters, not model tokens):

| Toolset | Schema | Tools | Characters |
| --- | --- | ---: | ---: |
| all | full | 62 | 134,431 |
| all | slim | 62 | 60,263 |
| core | full | 51 | 127,810 |
| core | slim | 51 | 53,642 |
| compact | full | 13 | 94,031 |
| compact | slim | 13 | 19,863 |
| ai | full | 16 | 10,367 |
| ai | slim | 16 | 10,367 |

`vixl_compose` is in core and compact (about 2,700 characters): it runs create → fonts → layout → style → look → operations → check → preview → save → exports in one atomic call, so a new piece needs one tool call instead of five. Its `operations` are typed as plain objects (fields from `vixl_operation_schema`) so the operation schema is not advertised twice.

Reproduce by constructing `build_server(Session(workspace=...), tools=MODE, schema=SCHEMA)`, awaiting `list_tools()`, and measuring `json.dumps([t.model_dump(exclude_none=True) for t in tools], separators=(',', ':'))`. Values change as tools evolve; the schema size tests guard against unbounded growth.

Use `vixl mcp --tools compact --schema slim` for the smallest general editing surface, or `--tools core --schema slim` when dedicated review, font, spatial and animation tools are useful. Provider-backed tools can run separately with `--tools ai`. Existing all/full clients continue to work. Compact callers access workflow actions and fetch exact fields through `vixl_operation_schema`; the canonical runtime validates the complete operation regardless of advertised schema mode.

The 0.21.0 review of the tool list removed one duplicate: the MCP text-adding tool did nothing a `text` operation in `vixl_operations_apply` does not (a registered font name works there too). The `vixl_guide("capabilities …")` alias of `vixl_capabilities` is gone as well. Tools that look alike but answer different questions now say so in their descriptions: `vixl_animation_inspect` / `vixl_animation_preview` cover frame-by-frame animation (saved frames), `vixl_timeline_inspect` / `vixl_timeline_preview` keyframed motion; `vixl_validate` checks rules and suites, `vixl_check` the rendered design; `vixl_measure_spacing` is a pass/fail gap check, `vixl_spatial` the open-ended layout query; `vixl_guide` says what to make and `vixl_capabilities` gives field-level reference. `vixl_operations_apply` takes `check` and `preview`, so the common apply → check → preview loop is one call.

Consolidation keeps aliases in one normalization registry, removes duplicate transform implementations, derives extension CLI flags from the canonical schema, and factors repeated constraints in the full MCP schema without dropping those constraints. Legacy spellings still normalize and are reported in results. Native JSON operation batches are shared by CLI, Python, REST and MCP; service filesystem restrictions remain explicit.

Recommendation: retain these selectable toolsets and on-demand schemas rather than add one MCP tool per operation. A focused-tool experiment should compare the same held-out briefs for invalid-field retries, calls, schema tokens and completion rate before changing defaults. These measurements establish discovery-size savings; they do not establish lower model error rates. No new comparative model evaluation was run for this release.
