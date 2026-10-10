# Authoring and CLI improvements in 0.17

[Documentation home](README.md) · [Getting started](getting-started.md) · [Visual gallery](gallery.md)

## Organic geometry

Organic helpers create ordinary editable SVG path layers. Seeds make variation reproducible;
regenerating a target preserves its layer ID and composition placement.

```sh
vixl new 800x1000 --background '#100b16' --out flowers.vixl --overwrite
vixl organic-shape rose --name rose --seed 12 --lobes 7 --width 440 --height 440 --x 180 --y 180 --stroke '#ff648a' --stroke-width 3
vixl organic-shape leaf --name leaf --seed 8 --width 120 --height 280 --x 530 --y 510 --fill '#67c7a0'
vixl organic-shape --target rose --seed 13
vixl path-fit rose --padding 12
vixl export --out flowers.svg
```

For whole organisms (flowers, trees, ferns, creatures, shells, coral, animal markings) built from
composable generators and growth rules, use [`organic`](organic.md). To start from a person's own
sketch — cleaned, traced, straightened and coloured while keeping their lines — use
[`drawing`](drawing.md).

Kinds: `rose`, `leaf`, `petal`, `blob`. `--variation 0..1` controls irregularity;
`--lobes 3..32` controls blob lobes or rose petals. Paths can be edited with `pen --target`.
For freehand points, `pen --tension 0..1` controls smoothing and `--corners '[0,3]'`
preserves sharp anchors. `path-fit` measures true curve extrema; `--stretch` permits
independent horizontal and vertical scaling.

## Paint coordinates and QA

`paint --space canvas` is the default: points are document pixels. `--space layer`
uses the paint layer's local stroke surface, including on moved or resized layers.
Paint responses report resolved local stroke bounds and surface dimensions. Fully invisible
paint generates a warning. `check --checks content fonts` detects layers with no rendered
pixels and unsupported glyphs. Deliberately empty paint layers are allowed.

Use `layer-intent grid --role decoration` for decorative geometry behind text. This suppresses
its incidental text-overlap warnings; contrast and bounds checks remain active.
`layer-intent title --allow-overlap badge` allows a specific pair, stored by stable layer ID.
An empty `--allow-overlap` list clears allowances. Text-text collisions still require explicit
pair allowances. Text meant to be faint (a watermark, a ghost numeral) takes a contrast waiver,
`layer-intent ghost --waive contrast` (or `waive: [{check, reason, expires}]`): its contrast finding stays
listed, as informational and `waived`; see [waivers](production.md#waivers-and-check-profiles).

## Fonts and layout previews

Text and layout `--font`/`--display-font` accept registered names, typography roles, system
font names, and local files. Explicit files are embedded before measurement and export.
For missing glyphs, every renderer and export uses the bundled outline fonts automatically: DejaVu Sans, then Noto Sans, Noto Sans Symbols, Noto Sans Symbols 2 and Noto Sans Math (more Latin, Greek and Cyrillic, symbols, dingbats, arrows and math). CJK is not bundled.
`font-fallbacks 'Registered CJK' 'Registered Symbols'` sets an ordered document fallback list;
each font is embedded. `font-fallbacks` with an empty list clears it. The list is document-wide: a `target` is rejected, because fallbacks apply to every text layer.
List several faces of a fallback family (for example `noto-sans-jp-400` and `noto-sans-jp-700`) and each text
uses the face that matches its own font best: the same slope (italic or upright) first, then the nearest
OS/2 weight, so a bold heading falls back to the bold face in PNG, SVG and PDF alike; a PPTX gives those
characters their own runs naming the fallback family. Families keep their list order. QA identifies fallback characters
and errors on characters unsupported by the entire stack. This is outline-font fallback;
font-native color emoji retain the existing font-engine limitations. The [bundled emoji library](emojis.md) supplies complete Unicode 17 artwork by default, including joined sequences.

```sh
vixl layout preview event-poster --set title=FLOWERS --predictable --font /path/to/font.ttf
vixl layout apply event-poster --set title=FLOWERS --predictable --font /path/to/font.ttf
```

Preview returns resolved palette, mode, alignment, type scale, seed, and created layers
without saving changes. The default mode inherits an opaque canvas background's light/dark
appearance; transparent canvases retain seeded selection. `--mode light|dark` overrides it.
`--predictable` defaults to left alignment, balanced density, a perfect-fourth type scale,
and a rule accent; explicit choices override these defaults.

## Repeatable builds and persistent sessions

`new --overwrite` explicitly replaces an existing document. It defaults to refusing replacement.
For large scripted builds, `session --project flowers.vixl` holds the project lock and loads once.
Send one JSON request per line on stdin; each response is one flushed JSON line on stdout:

```json
{"id":1,"operations":[{"type":"organic-shape","kind":"rose","name":"rose","seed":4}]}
{"id":2,"operations":[{"type":"move","target":"rose","x":100}],"dry_run":true}
{"id":3,"command":["check","--checks","content","fonts"]}
```

Requests apply atomically and save successful edits. Failed requests leave the document intact
and the session continues. CLI command requests use argv arrays, never shell strings. Save,
transaction, server, and nested session commands are excluded. Existing compact/full response
selection also applies to sessions. Export paths follow the ordinary CLI filesystem rules.

## Export fidelity and runtime diagnostics

Primitive, text, gradient, and pixel repeats expand into SVG vectors when their appearance is
supported. Repeated groups, raster masks, paint, and unsupported effects retain explicit raster
fallback metadata. Inspect `export`'s `svg.vector_only` and `raster_fallbacks` report.

GIF timing is quantized to centiseconds; WebP/APNG use milliseconds. Frame durations are
distributed using cumulative boundaries, preserving the requested timeline duration to the
format's resolution. Reports include `duration`, `requested_duration`, and `frame_durations`.
Very high frame rates or sub-resolution final frames need a lower fps. GIF has at most 256
palette colors; prefer WebP/APNG for smooth gradients. `export-timeline --progress` writes
frame counts to stderr, leaving stdout suitable for JSON processing.

`vixl --runtime-info --json` shows the active version, module, Python executable, and managed
installation root. Version/help and `VIXL_NO_UPDATE=1` launches read installation metadata
without obtaining a write lock or activating pending updates.

## Reading check results

An explicit `checks` list **replaces** the default list. `check(checks=["deck"])` checks the deck family only. Run `check()` and then the specialised check, or combine them explicitly: `check(checks=[*vixl.checks.CHECKS, "deck"])`. A report is passed only when it has no errors and no findings whose action is `fix`; review findings remain visible without automatically failing it.

A finding you accept on purpose (faint decorative text, a bar in the margin) takes a waiver with a reason and an optional expiry: `layer-intent waive`, or the `waiver` operation. It stays in the report as informational with `waived`, the report's `waivers` lists them, and an expired waiver turns the finding back on and fails `--strict` until it is renewed. `check --profile draft|review|final` chooses the checks, suites and the level that fails (`fail_on`); see [waivers and check profiles](production.md#waivers-and-check-profiles).

A footer that intentionally lives outside the safe area can use `layer-intent target=footer allow_crop=true`. This records the exception and reports the safe-area crossing as informational. It does not exempt tiny text, low contrast or a wholly off-canvas ordinary layer. Wrapped copies in a generated pattern tile are intentional, including copies wholly beyond the canvas. Unmarked content still receives bounds findings.
