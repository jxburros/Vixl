# Efficient agent workflows

Start with `vixl_capabilities(topic="animation", fields=true)` for operations, field names, workflows, guidance and gotchas relevant to a task. Topics include text, drawing, animation, film, layout, color and export. `vixl guide capabilities animation` provides the same discovery through the CLI; exact constraints and examples remain in `vixl_operation_schema(types=[...])`.

All interfaces normalize operation aliases with the same registry and validate against the same operation schema. MCP restricts filesystem access and accepts registered font names and roles. SVG path coordinates are literal local pixels, not percentages or normalized coordinates; `path-fit` fits a path into its layer box. Grouped positions are parent-relative unless `move` uses `space: "canvas"`.

An atomic batch holds up to 10,000 operations. Generated motion and compact `keyframes` can replace hundreds of handwritten operations. For larger edits use history `begin`, several batches, then `commit`; `rollback` discards the group. A failed batch applies nothing. Explicit `Limits(max_operations=...)` still enforces a lower application limit.

`vixl_validate` defaults to a summary with up to 50 failed checks. `detail="full"` includes passes; `targets` accepts layer-name globs, `severity` selects error/warning/info, and `offset`/`limit` paginate. Filters never hide an error from the overall `valid` result. `suppress` explicitly omits named rules or rule globs. Mark intentional bleed with `layer-intent` `allow_crop: true` or a background/decoration role; it then reports informational crop findings.

`vixl_timeline_inspect` defaults to track names, property names, key counts and time ranges. Use `detail="full"` to include keys, `targets`/`properties` globs and `start`/`end` to narrow the result. Track pagination uses `offset`/`limit`; key pagination uses `key_offset`/`key_limit`. A `next_offset` of null marks the end. Sample a film frame or interval with `film-preview` before rendering the full film; the preview includes film camera framing and transitions.
