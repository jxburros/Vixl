# MCP toolset evaluation

The existing compact server with slim schemas is the recommended configuration when minimizing tool-discovery context matters. Keep one atomic editing tool and load exact operation fields on demand. This avoids splitting an edit across several transaction boundaries, while task-aware `vixl_capabilities` supplies relevant operations and gotchas.

Measured on the 0.20.0 implementation using serialized `tools/list` tool objects (compact JSON, including input schemas; characters, not model tokens):

| Toolset | Schema | Tools | Characters |
| --- | --- | ---: | ---: |
| all | full | 62 | 121,691 |
| all | slim | 62 | 55,217 |
| core | full | 51 | 115,062 |
| core | slim | 51 | 48,588 |
| compact | full | 12 | 82,398 |
| compact | slim | 12 | 15,924 |
| ai | full | 16 | 10,439 |
| ai | slim | 16 | 10,439 |

Reproduce by constructing `build_server(Session(workspace=...), tools=MODE, schema=SCHEMA)`, awaiting `list_tools()`, and measuring `json.dumps([t.model_dump(exclude_none=True) for t in tools], separators=(',', ':'))`. Values change as tools evolve; the schema size tests guard against unbounded growth.

Use `vixl mcp --tools compact --schema slim` for the smallest general editing surface, or `--tools core --schema slim` when dedicated review, font, spatial and animation tools are useful. Provider-backed tools can run separately with `--tools ai`. Existing all/full clients continue to work. Compact callers access workflow actions and fetch exact fields through `vixl_operation_schema`; the canonical runtime validates the complete operation regardless of advertised schema mode.

Consolidation keeps aliases in one normalization registry, removes duplicate transform implementations, derives extension CLI flags from the canonical schema, and factors repeated constraints in the full MCP schema without dropping those constraints. Legacy spellings still normalize and are reported in results. Native JSON operation batches are shared by CLI, Python, REST and MCP; service filesystem restrictions remain explicit.

Recommendation: retain these selectable toolsets and on-demand schemas rather than add one MCP tool per operation. A focused-tool experiment should compare the same held-out briefs for invalid-field retries, calls, schema tokens and completion rate before changing defaults. These measurements establish discovery-size savings; they do not establish lower model error rates. No new comparative model evaluation was run for this release.
