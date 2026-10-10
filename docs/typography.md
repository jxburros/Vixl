# Typography: catalog, pairings and installs

[Documentation home](README.md) · [Getting started](getting-started.md) · [Visual gallery](gallery.md)

Vixl bundles DejaVu Sans only as a proofing fallback, so text renders before anyone has chosen type. Design type comes from a researched catalog and is downloaded only when you ask. The default `fonts` check warns while any text still uses the fallback (a fix-level finding, so `check.passed` stays false until real type is installed), and an apply that asks for the `heading` or `body` role before the document has typography says so in its `warnings`. Pass `font_pairing` to `vixl_document_create` (or call `vixl_font_pair`) to give the roles real typefaces.

## The catalog

104 open-licensed (OFL, Apache, UFL) Google Fonts families: neo-grotesque, grotesque, geometric and humanist sans; old-style, transitional, didone, slab and glyphic serifs; monospace, display, handwriting and blackletter; and Noto families for Japanese, Chinese, Arabic and Devanagari. Each entry records its classification, verified weights and italics, x-height, width, stroke contrast, era, mood, suitable roles, best uses, misuse cautions and a note on its character. Every family, weight and italic was checked against the Google Fonts CSS API. `scripts/verify_fonts.py --check src/vixl/data/fonts.json src/vixl/data/font-pairings.json` repeats the check.

```bash
vixl fonts --category serif            # or a classification: --category didone
vixl fonts --role heading --mood playful
vixl font show "Space Grotesk"         # full entry plus the pairings that use it
```

## Pairings

76 curated heading/body pairings: the original 60 plus 16 tiered ones from house style 3 (4 safe, 8 bold, 4 avant-garde; `tier` in each entry). They are described by their relationship (`contrast` of classification, `superfamily`, or `concord`), mood and best uses, a one-line reason they work, a caution and, where one exists, a published source. Single-family pairings get weight contrast from one family.

```bash
vixl font pairings --mood editorial --for reports
vixl font pairing dm-serif-dm-sans     # why it works, and the caution
vixl font principles                   # the full guide on choosing and combining type
```

The guide, `vixl font principles` (MCP: `vixl_fonts view=principles`), covers:

- **Classification:** Vox-ATypI and the sans subclasses.
- **Eight pairing principles:** contrast of classification without contrast of everything, matching x-height, shared construction or era, superfamilies, two families at most, fixed roles, and weight contrast.
- **Role assignment:** which faces suit headings, body, captions, UI, numerals and code.
- **Size and spacing:** leading, measure and tracking.
- **Where faces stop working:** display and script faces only at size, thumbnail legibility, and multilingual coverage.
- **Choosing at random:** pick the pairing first, then a palette whose mood fits it.

## Default size and leading

Text without a `size` uses the body size of the document's type scale (the `body` character style that `type-scale`
and layouts define), else about 2.6% of the canvas short side on screen, or a readable point size in print: 28 px on
1080×1080, 104 px on 4000×4000. The apply result lists filled-in values under `defaults`.

Leading is one rule everywhere (plain text, rich text, text flows, layouts and diagram labels): a line height as a
multiple of the font size, by text stage.

| Stage | Line height | Used for |
| --- | --- | --- |
| display | 1.0 | Display type, about 2.8 × body and up |
| heading | 1.1 | Headlines and titles |
| lead | 1.35 | Subtitles and lead paragraphs |
| body | 1.45 | Running text |
| caption | 1.3 | Captions, labels, footnotes |

Plain text stores it as `line_height` and the matching `spacing` (pixels added to the font's own line pitch, which is
negative for tight display type); a later size or font change keeps the multiple. `spacing` in pixels overrides it.
Layers saved before 0.23 keep their stored spacing.

## Text stages

Text is set on a ladder of ten stages. Each stage has a font role, a type-scale step, a line-height entry and an
optional case (craft `type_stages` in the house style):

| Stage | Font role | Type-scale step | Line height | Case |
| --- | --- | --- | --- | --- |
| display | heading | display | display (1.0) | |
| h1 | heading | headline | heading (1.1) | |
| h2 | heading | title | heading (1.1) | |
| h3 | heading | subhead | heading (1.1) | |
| subtitle | body | lead | lead (1.35) | |
| lead | body | lead | lead (1.35) | |
| body | body | body | body (1.45) | |
| caption | body | caption | caption (1.3) | |
| citation | body | caption | caption (1.3) | |
| label | body | caption | caption (1.3) | upper |

`text` and `text-set` take `stage` (alias `role`): the stage's font, size (from the document's type scale, else the
body size and a perfect-fourth scale), line height and case fill whatever the operation leaves out. Fonts follow
roles, so two fonts cover the whole ladder; to spread three or four, register a face for a role or a stage:
`{"type": "font-register", "name": "anton-400", "role": "h1"}` gives h1 its own face, and any lowercase role name
(`accent`, `hand`, `mono`) can be registered and named in `font`. A workspace brand maps stages onto its roles with
`stages` (see [brands](brands.md#font-roles-text-stages-and-extra-colours)). Text that follows a role or stage
changes face when that role is registered again.

Without `font` or `stage`, new text takes the stage its size reads as once the document has typography: from the
title step (h2) up a heading stage in the heading face, below it lead, body or caption in the body face. Markdown
headings (`#`, `##`, `###`) in rich text and text flows use the h1–h3 stage fonts (the heading face, set at its own
weight rather than synthesized bold). Layout slots use the stages too: display, headline (h1), title (h2), subhead
(subtitle), lead, body, caption and label slots take a stage's own face when the document maps one. Before any
typography is set, stages keep the proofing font. Templates may name a role or stage in `font`, or set `stage`.

## Installing

```bash
vixl font pair dm-serif-dm-sans        # heading + body; or: vixl font pair random --mood warm
vixl font install "Fraunces" --weight 700 --role heading
vixl font use dm-sans-400 --role body  # reassign an installed font
vixl font list                         # registered fonts, the document typography and the text stages
```

Installs fetch one static TTF per style from the Google Fonts CSS API (`fonts.gstatic.com`, HTTPS only, bounded size). Any Google Fonts family works, not only catalog entries. Files are validated and cached in `~/.cache/vixl/fonts` (set `VIXL_FONT_CACHE` to move it), then embedded in the document and registered as `family-weight` (for example `dm-serif-display-400`). A saved `.vixl` file therefore renders anywhere without the network. `font pair` and `--role` set `state.typography`, and layouts use it for headings and body unless you pass `font`/`display_font`. The structured operation is `{"type": "font-register", "name": "dm-sans-400", "role": "body"}`.

Each install reports where the font came from, so agents and CI can verify offline behaviour: `source.origin` is `cache` (served from `source.cache_file` with no network) or `download` (with the Google Fonts stylesheet in `source.stylesheet` and the font file in `source.url`; `cache_file` is the copy it was stored as, or null when the cache is not writable). `source.cache_dir` is the cache directory and `source.cache_dir_from` says whether `VIXL_FONT_CACHE` or the default chose it. `family`, `weight`, `italic` and `name` give the resolved style, and `file` names the embedded asset (`fonts/<sha256>.ttf`), its byte size and hash. `font pair` returns this for both the heading and body fonts plus `origin` (`cache`, `download` or `mixed`); `vixl_roll` with `apply` returns the same under `fonts`. `source.bundled_fallback` is always false: a font that cannot be downloaded or found in the cache fails with `font_download_failed` (or `unknown_font`), and the bundled DejaVu Sans is never substituted silently. To run offline, pre-fill the cache (or set `VIXL_FONT_CACHE` to a directory holding `family-weight[-italic].ttf` files such as `inter-400.ttf`) and check for `origin: "cache"`.

### Workspace default fonts

A workspace can give every new document the same typography. `vixl_font_pair(pairing=..., scope="workspace")` (CLI `vixl font pair NAME --scope workspace`, REST `POST /typefaces/pair` with `"scope": "workspace"`) writes `pairing` into the workspace `brand.json`; `vixl_font_install(family=..., role="heading"|"body"|any role, scope="workspace")` (CLI `vixl font install FAMILY --role heading --scope workspace`) embeds that one style in `brand.json` under `fonts.<role>`, overriding the pairing for that role. A workspace pairing replaces embedded `fonts.heading`/`fonts.body` entries (other roles stay), and the result lists them under `workspace.replaced`. Both fetch the fonts immediately, so an unknown family fails at once, and neither changes existing documents.

`vixl_document_create`, `Session.create` and `vixl new` then download (or reuse from the cache) and embed the workspace fonts as part of the creation step, and report them under `workspace_fonts` (`pairing`, and `applied.heading`/`applied.body` with each font's `name` and whether it came `from` the pairing or `fonts`). Fonts are embedded in each document, so files stay portable. Passing `font_pairing` to `vixl_document_create`, `workspace_fonts: false` (CLI `--no-workspace-fonts`) skips them. When a pairing cannot be fetched (offline, empty cache), the document is still created and `workspace_fonts.error` says why; run `vixl_font_pair` later. The CLI uses the `brand.json` beside the new document (`--scope workspace` writes it in the current directory).

MCP: `vixl_fonts` (views `fonts`, `font`, `pairings`, `pairing`, `principles`), `vixl_font_pair`, `vixl_font_install`. REST: `GET /typefaces`, `GET /typefaces/pairings`, `POST /typefaces/pair`, `POST /typefaces/install`.

## Baselines

Text results and `inspect` report each text layer's `baseline` (the first line), `baselines` (every line),
`ascent`, `descent`, `cap_height` and `x_height` in the layer's parent coordinates. Three operations position
text by its baseline instead of its box:

- **`baseline_y`** on `text` (creating, or editing with a `target`), `text-set` and `move` places the layer
  so its **first** line's baseline sits at that y, in the same coordinates as `y` (a grouped layer's group).
  Give `y` or `baseline_y`, not both. Multi-line text is positioned by its first line; to line up the last
  line, read `baselines[-1]` from `inspect` and move by the difference. Rich text with several sizes or fonts
  uses the measured first line, so a large word on that line counts. `baseline_y` positions once, like `y`:
  a later size change keeps the box's top, so give `baseline_y` again with the new size.
  `{"type": "text-set", "target": "price", "size": 64, "baseline_y": 540}`
- **`align` with `alignment: "baseline"`** moves text layers vertically so their first baselines match: the
  first of `targets` sets the line, or `relative_to` names a text layer. `margin` shifts the shared line down.
  Other layer kinds have no baseline and are rejected with a message saying so.
- **`snap` with `anchors: ["baseline"]`** snaps text layers' first baselines onto guides, for example the
  lines of a baseline grid (`{"type": "grid", "kind": "baseline", "spacing": 24}`). `baseline` is not one of
  the nine box anchors (`geometry.ANCHORS`): pivots, fits, link positions and the other anchor fields do not
  take it.

Rotated or skewed text is not positioned by baseline (the measurements are in the upright frame).

## Rolling a direction

When a brief leaves the look open, roll instead of settling for defaults:

```bash
vixl roll --for poster --size instagram-post --mood warm
vixl roll --seed 11 --lock palette=sage --lock pairing=dm-serif-dm-sans
```

A roll picks a pairing first, then a palette whose mood fits it, a layout suited to the purpose and canvas, and the mode, type scale, density and accent. It returns the steps and a ready `layout-apply` operation. The same seed reproduces it. Roll several times, preview, and keep the one you like (MCP `vixl_roll`, REST `GET /roll`). With a document (`vixl -p DOC roll` or the session's current document) the preview uses its canvas, so it picks the same direction `--apply` will. `--apply` leaves slots you did not fill out (`--unfilled omit`, the default when you pass `--set`/`slots`), so the result passes `check` with no second layout pass; `--unfilled blank` keeps `[Label]` placeholders for slots to fill later.

## Emoji artwork

[Emojis and custom packs](emojis.md) describes default VIXL emoji rendering, opting into font rendering, portable replacements, editable masters and destination-ready exports. Text-default symbols remain font text unless VS16 requests emoji presentation.

## Letter spacing and edits

Use `text-style` tracking for extra local pixels between glyphs, for example `{"type":"text-style","target":"headline","tracking":2}`. Negative values tighten text. It works on an entire layer or on the operation's selected span; `tracking` is also available in rich-text spans. This is the letter-spacing control, distinct from `spacing` (vertical line spacing). Inspect and preview after tracking changes because the text may wrap differently.

Width-only `text-layout` boxes grow vertically after `text-set` or variable substitution. Give both width and height to keep a fixed box and let overflow checks report copy that does not fit. Markdown text-flow retains its size-based line-height calculation when splitting across frames.

For social and poster purposes, automatic legibility checking and generated layout minor text use the house minimum (2.2% of the short canvas side). Explicit thumbnail widths remain a caller-selected viewing-context check. Print keeps the 6-point minimum and decks keep their profile checks. The contrast check treats bold text (font weight 700+) from 18.66 px (14 pt) as large, needing 3:1; regular text needs 24 px. Shared spacing expressions such as `2u` use half the body size per unit.
