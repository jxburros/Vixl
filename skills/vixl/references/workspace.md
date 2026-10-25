# Workspace, brands and importing

## The MCP workspace

`vixl mcp --workspace .` serves seven tools (`vixl_document`, `vixl_apply`, `vixl_check`, `vixl_render`,
`vixl_export`, `vixl_reference`, `vixl_job`); fetch operation fields with `vixl_reference('operations', name=[…])`
and a tool's rarer options with `vixl_reference('vixl_export')` (any tool name but `vixl_job`). Unadvertised arguments go into
`options`, and an error returns the schema it expected. HTTP clients can use `--http` at `/mcp` with the configured bearer token.
Read `vixl_document(action='notes')` before revising a document and resolve notes after addressing them.
Humans can follow progress with `vixl -p DOCUMENT view`.

## Brands, workspace typography and rolls

Workspace `brand.json` provides default palette roles (plus `palette.extra` approved colours), pairing/embedded
fonts under any role name (`heading`, `body`, `hand` …) with `stages` mapping text stages onto them, embedded
logos, minimum contrast, required layer names, compliance rules (`fonts.allowed`, `colors.strict`, `logo.clear_space`,
`min_size` and `logo.variants`: `{"reversed": {"layers": "logo-rev*", "backgrounds": ["dark", "@brand-dark"]}}`, a
`fix` when a variant sits on a background it is not mapped to), copy rules (`words.forbid`, `words.prefer`, and
`words.allow` for names that forbid, prefer and the `spelling` check skip) and named `presets` (select one per document with `{"type": "brand-preset", "name": …}`).
Layouts, templates, rolls and checks honor it, and new documents embed its fonts at creation (`workspace_fonts` in
the result; `workspace_fonts: false` skips). `vixl brand validate` flags missing roles, fonts and logos; the
`brand-board` workflow draws the brand as a guidelines PDF.
Logos take `purpose` (`icon`, `wordmark`, `avatar`, `lockup`), `place` (`anchor`, `margin`, `width_fraction`, `safe`)
and `auto`: layouts and templates add only automatic logos (default: true for a single logo, false when there are
several), and `{"type": "brand-logo", "purpose": "wordmark", "anchor": "bottom"}` places one by purpose. brand.json
`elements` place with `object-place` as `brand:NAME`; brand `styles` are tagged `brand:NAME` with `style-set` and
checked by `check --checks style`. `vixl brand init`, `brand pack OUT.vixlbrand` and `brand install FILE` start,
package and install a brand with its resource library (install validates everything, then writes atomically).
`vixl brand import --design-profile FILE.json` writes brand.json from a Design Profile (`schemaVersion: 2`) and
`vixl brand export --design-profile FILE.json` writes one (workflows `brand-import`/`brand-export`); both list the
paths they could not map under `unmapped`.
Set the workspace typography with a `font-pair` or `font-install` step and `scope: "workspace"`.
Use a `roll` step in `vixl_apply` (CLI `roll --apply --set title=...`) to apply a whole direction, and
`vixl_reference('roll')` to see one without applying it;
`layout apply` returns unfilled slots immediately. Check and fill them before export. A roll with `slots` omits the slots you did not fill (`unfilled: "omit"`), so it passes `check`; pass `unfilled: "blank"` to keep `[Label]` placeholders instead. When no layout places every slot you pass, the roll keeps the previewed layout and the apply fails with `unused_slot`: drop the slots its `suggestions` leave out and apply again.

## Importing SVG, PDF and Figma

An `import-document` step (`vixl_apply`) imports SVG and PDF as editable layers. Vixl's own SVG export carries its document, so
re-importing it restores the same layers, live text, groups and effects (fonts are named, not stored: the import finds a
bundled, cached, same-named registered or Google Fonts face again; any other font falls back to the bundled face with a
warning). Other SVG becomes shapes, live text
(`<text>`), groups (`<g>`), gradients and images; a PDF page becomes live text, paths and images (shadings and
clipped content as image layers; its fonts are found again from `font_map`, registered fonts or the font cache, and
the result's `fonts` says how). With the default `svg_mode="editable"` an unsupported SVG feature returns an
error; `"auto"` draws just those elements as images (at most 64; more fails with `resource_limit`); `"appearance"` imports the whole SVG or PDF page as one image
(`dpi` sets a PDF page's resolution).
A Figma file or frame imports as editable layers, live text, stacks and gradients with `format="figma"` and `source` set to the URL or key
(`node_id` picks one frame, `rasterize_unsupported` draws nodes with no editable equivalent as images; CLI
`vixl import URL --format figma [--node 1:2] [--rasterize-unsupported]`, Python `import_document(project, b"URL", "figma")`, REST
`POST /import?format=figma`); the user's read-only token is the `FIGMA_TOKEN` (or `VIXL_FIGMA_TOKEN`) environment variable of
the process that runs Vixl, and the result's `report` lists what could not map. See [Import from Figma](../../../docs/guides/images/figma.md).
