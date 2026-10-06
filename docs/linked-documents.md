# Linked documents

[Documentation home](README.md) · [Getting started](getting-started.md) · [Visual gallery](gallery.md)

A `link` layer shows another `.vixl` document inside this one, live. Nothing is flattened: each render
opens the source, draws it, and places the result in the layer's box. Change the source and every
document that links to it shows the change the next time it renders, so derived designs (an Instagram
crop and a caption card cut from one photo edit, a pattern preview and a mug wrap built from one tile,
a sheet of badges built from one template) stop going out of date.

```json
{"type": "link", "source": "tile.vixl", "name": "preview", "x": 100, "y": 100, "width": 600,
 "fit": "fill", "position": "top-left"}
```

## The `link` layer

| Field | Meaning |
| --- | --- |
| `source` | **Required** to create a link (or give `target` to change one). The linked `.vixl` file, workspace-relative (see [Where links resolve](#where-links-resolve)). |
| `name`, `x`, `y`, `width`, `height` | As for any layer. With neither size the layer takes the source's canvas size; with one, the other follows the source's aspect ratio. `x`/`y` accept `"center"`, `width`/`height` accept `"N%"`. |
| `fit` | How the source fills the box: `fill` (default; scales to cover the box and crops the overflow, like a frame), `fit` (scales to sit inside and leaves the rest transparent) or `stretch` (distorts to the box). |
| `position` | Where the content sits when it does not fill the box: `[x, y]` fractions (0 = left/top, 1 = right/bottom; default `[0.5, 0.5]`) or an anchor such as `top-left`. |
| `crop` | `{x, y, width, height}` in the source's pixels: only that region is placed. |
| `artboard` | Draw one of the source's [artboards](design-tools.md) instead of its whole canvas. |
| `source_page` | Draw one page (name or number) of a multi-page source. (`page` on an operation names the page of *this* document that it edits, so the linked page has its own field.) |
| `variables` | Overrides for the source's `${variables}`. A value may itself contain `${name}`, which reads this document's variable. A value for an image variable names a workspace image file. |

Rotation, flips, opacity, blend, masks, effects, layer styles, clipping, constraints and groups work on a
link exactly as on an image layer (`rotate`, `flip`, `opacity`, `blur`, `group`, `align` …). `resize` and
`scale` change the box, and `fit`/`position`/`crop` decide what happens inside it. The source is
re-rendered at the size it is shown at, so text and vectors stay sharp when you enlarge a link.

A `link` operation with a `target` (CLI: `link-set LAYER`) changes `source`, `artboard`, `source_page`, `variables`,
`fit`, `position` or `crop` (`null` clears an optional setting) and checks the result against the source; the layer's
name, position and size have their own operations (`rename`, `move`, `resize`). A link layer stores the
source's `source_hash` (SHA-256) and `source_size` as of the last `link`, change of `source` or
`link-refresh`.

## Keeping track of changes

Rendering always uses the source as it is on disk now, with no refresh needed. The recorded hash exists
so you can tell what changed behind your back:

- **`links`** (CLI), the `links` workflow action (MCP `vixl_workflow("links", {})`, REST
  `POST /workflow/links`) and `inspect` (`links` list) report every link with a `state`:
  `ok`, `stale` (the source changed since it was last recorded; the layer already draws the new version),
  `missing` (the error names the path it looked for), `cycle`, `forbidden` or `error` (an unreadable
  source, or an artboard, page or crop the source no longer has). `size_changed` flags a source whose
  canvas size differs from the recorded one.
- **`link-refresh [TARGET]`** records the current revision and size of one link (or every link of the
  active page) and re-checks it, so `stale` goes back to `ok`.
- **`check`** gains a `links` check: broken links are errors (and are left out of the other checks so one
  missing file does not hide the rest), stale or resized sources are warnings.
- Production runs (`vixl_workflow("run", …)`) include the revisions of linked sources in their
  fingerprints, so a changed source re-renders the variants that use it.

## Freezing a link

`link-embed TARGET` replaces the link with an ordinary image layer holding exactly what the link drew
(its fit, crop, rotation, effects and opacity, at the layer's size). The source path, hash and variables
are kept as `provenance`. Use it before sending a document without its sources, or to stop following a
source. Embedding needs the layer's styles and clipping removed, like `rasterize` (use `link-embed`
rather than `rasterize` on a link: it also drops the link's fields).

## Where links resolve

Linked files are an opt-in dependency, not an import (see the security notes in
[architecture](architecture.md)):

- A relative `source` resolves against the **workspace** (the folder `vixl mcp --workspace` serves, or the
  CLI's current folder), then the folder of the document itself. The `link` operation stores the
  workspace-relative path, so `source: "assets/tile.vixl"` works the same from the CLI, MCP and REST.
- Through **REST and MCP** a source must stay inside the workspace. Absolute paths, `..` escapes and
  symlinks that lead outside are refused with a `forbidden` error, both when linking and when a
  hand-edited document is rendered. Only `.vixl` files can be linked.
- On the **CLI and Python API**, a source outside the workspace needs `--allow-linked`
  (`Project.load(path, allow_linked=True)`). Without it the same `forbidden` error applies.
- A linked document is read the way `Project.load` reads any archive: validated, never extracted, bounded
  by the usual size limits. Its own links resolve the same way and obey the same rules.

## Cycles and depth

- A link that would lead back to the document that holds it, directly or through other links, is rejected
  when you create it (`link_cycle`, naming the chain `a.vixl → b.vixl → a.vixl`). A cycle created by editing
  the files is refused when drawn, so rendering never loops.
- Chains of links are limited to **4 levels** (`link_depth`). Both checks look at the link graph, not at
  what happens to be cached.

## Export

| Output | What a link becomes |
| --- | --- |
| PNG, JPEG, WebP, TIFF | The rendered pixels. |
| PDF (`pdf_content` vector, and print-size documents) | The source's own PDF graphics: shapes, gradients and **real, selectable text** with embedded font subsets, clipped to the box and carried through the link's rotation and flips. A link with opacity, effects, a mask, a blend mode, or a source that contains adjustment or blend layers is embedded as an image and listed under `raster_fallbacks`. |
| SVG, HTML | An embedded bitmap listed in the SVG's `raster_fallbacks` metadata (`svg_policy: "strict"` refuses it). |
| PPTX | A picture. |

## Commands

```text
vixl link FILE.vixl [--name N] [--x X] [--y Y] [--width W] [--height H] [--fit fill|fit|stretch]
          [--position top-left|0.5,0.5] [--crop X,Y,W,H] [--artboard NAME] [--source-page P] [--set NAME=VALUE]…
vixl link-set LAYER [--source F] [--fit …] [--position …] [--crop …] [--artboard …] [--source-page …]
          [--set NAME=VALUE]… [--clear artboard|source_page|variables|crop]…
vixl link-refresh [LAYER]
vixl link-embed LAYER
vixl links                       # every link with its state
```

Through MCP and REST the same operations go through `vixl_operations_apply` / `POST /operations`
(`link`, `link-refresh`, `link-embed`).

## Related

[Data merge and imposition](imposition.md) builds sheets out of link layers: each cell of a printed sheet
is a link to the template with one CSV row as its `variables`.
