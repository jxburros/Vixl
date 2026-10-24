# Typography: catalog, pairings and installs

Vixl bundles Noto Sans only as a proofing fallback, so text renders before anyone has chosen type; missing glyphs fall back to `font-fallbacks`, then bundled Noto Sans, DejaVu Sans, Noto Sans Symbols, Symbols 2 and Math (Latin, Greek, Cyrillic, Arabic, Hebrew, symbols; not CJK, Devanagari or Thai). Text in those scripts draws from a matching face already in the font cache (or `VIXL_CJK_PACK`), never downloaded at render, and the apply warns that the document does not embed it; with none it draws as empty boxes, and the apply says so in `warnings` with the exact step: a `{type: font-cover}` step (CLI `vixl font cover`) installs the catalog Noto face for each uncovered script (Noto Sans JP, SC, KR, Devanagari, Thai) and appends it to `font-fallbacks`; it uses the font cache first and, with downloads off (`VIXL_OFFLINE=1`), refuses and names the families. `text` or `scripts` narrow it. Design type comes from a researched catalog and is downloaded only when you ask. The default `fonts` check warns while any text still uses the fallback.

## The catalog

107 open-licensed (OFL, Apache, UFL) Google Fonts families: neo-grotesque, grotesque, geometric and humanist sans; old-style, transitional, didone, slab and glyphic serifs; monospace, display, handwriting and blackletter; and Noto families for Japanese, Simplified and Traditional Chinese, Korean, Arabic, Devanagari and Thai. Each entry records its classification, verified weights and italics, x-height, width, stroke contrast, era, mood, suitable roles, best uses, misuse cautions and a note on its character. Every family, weight and italic was checked against the Google Fonts CSS API. `scripts/verify_fonts.py --check src/vixl/data/fonts.json src/vixl/data/font-pairings.json` repeats the check.

```bash
vixl fonts --category serif            # or a classification: --category didone
vixl fonts --role heading --mood playful
vixl font show "Space Grotesk"         # full entry plus the pairings that use it
```

## Pairings

76 curated heading/body pairings (16 of them tiered: 4 safe, 8 bold, 4 avant-garde). They are described by their relationship (`contrast` of classification, `superfamily`, or `concord`), mood and best uses, a one-line reason they work, a caution and, where one exists, a published source. Single-family pairings get weight contrast from one family.

```bash
vixl font pairings --mood editorial --for reports
vixl font pairing dm-serif-dm-sans     # why it works, and the caution
vixl font principles                   # the full guide on choosing and combining type
```

The guide, `vixl font principles` (MCP: `vixl_reference('fonts') view=principles`), covers:

- **Classification:** Vox-ATypI and the sans subclasses.
- **Eight pairing principles:** contrast of classification without contrast of everything, matching x-height, shared construction or era, superfamilies, two families at most, fixed roles, and weight contrast.
- **Role assignment:** which faces suit headings, body, captions, UI, numerals and code.
- **Size and spacing:** leading, measure and tracking.
- **Where faces stop working:** display and script faces only at size, thumbnail legibility, and multilingual coverage.
- **Choosing at random:** pick the pairing first, then a palette whose mood fits it.

## Installing

```bash
vixl font pair dm-serif-dm-sans        # heading + body; or: vixl font pair random --mood warm
vixl font install "Fraunces" --weight 700 --role heading
vixl font use dm-sans-400 --role body  # reassign an installed font
vixl font list                         # registered fonts, the document typography and the text stages
```

Installs fetch one static TTF per style from the Google Fonts CSS API (`fonts.gstatic.com`, HTTPS only, bounded size). Any Google Fonts family works, not only catalog entries. Files are validated and cached in `~/.cache/vixl/fonts` (set `VIXL_FONT_CACHE` to move it), then embedded in the document and registered as `family-weight` (for example `dm-serif-display-400`). A saved `.vixl` file therefore renders anywhere without the network. `font pair` and `--role` set `state.typography`, and layouts use it for headings and body unless you pass `font`/`display_font`. The structured operation is `{"type": "font-register", "name": "dm-sans-400", "role": "body"}`.

Each install reports where the font came from, so agents and CI can verify offline behaviour: `source.origin` is `cache` (served from `source.cache_file` with no network) or `download` (with the Google Fonts stylesheet in `source.stylesheet` and the font file in `source.url`; `cache_file` is the copy it was stored as, or null when the cache is not writable). `source.cache_dir` is the cache directory and `source.cache_dir_from` says whether `VIXL_FONT_CACHE` or the default chose it. `family`, `weight`, `italic` and `name` give the resolved style, and `file` names the embedded asset (`fonts/<sha256>.ttf`), its byte size and hash. `font pair` returns this for both the heading and body fonts plus `origin` (`cache`, `download` or `mixed`); an applied roll (the `roll` step of `vixl_apply`, `vixl roll --apply`) returns the same under `fonts`. `source.bundled_fallback` is always false: a font that cannot be downloaded or found in the cache fails with `font_download_failed` (or `unknown_font`), and the bundled proofing face is never substituted silently. To run offline, pre-fill the cache (or set `VIXL_FONT_CACHE` to a directory holding `family-weight[-italic].ttf` files such as `inter-400.ttf`) and check for `origin: "cache"`.

Text can also follow a role: `text`/`text-set` accept `font: "heading"` or `"body"` (CLI `--font heading`), any other registered role (`font install --role hand`, `font-register role=accent`), or a text stage. Templates give their largest text the heading role and the rest body unless an operation names `font` (a role or stage) or `stage`. Changing a role (`font pair`, `font install --role`, `font use --role`) re-fonts every text layer with that role, or with a stage that inherits it; before any typography is set they use the proofing fallback. `text-set` also accepts a registered font name to change one layer's face. An unknown font fails with `missing_font`, listing the registered fonts and roles.

Text stages: display, h1, h2, h3, subtitle, lead, body, caption, citation and label. `stage: "h2"` (alias `role`) on `text`/`text-set` fills the stage's font, type-scale size, line height and case (label is uppercase). display and h1–h3 follow `heading`, the rest `body`, until a stage gets its own face (`font-register role=h1`) or a brand maps it (`brand.json` `stages`). Plain text without font takes the stage its size reads as (heading face from the title step up); markdown `#`–`###` headings use h1–h3; layout slots use the matching stage.

### Workspace default fonts

A workspace can give every new document the same typography. A `{type: font-pair, pairing: …, scope: workspace}` step in `vixl_apply` (CLI `vixl font pair NAME --scope workspace`, REST `POST /typefaces/pair` with `"scope": "workspace"`) writes `pairing` into the workspace `brand.json`; `a font-install step` (CLI `vixl font install FAMILY --role heading --scope workspace`) embeds that one style in `brand.json` under `fonts.<role>`, overriding the pairing for that role; without a role it becomes the heading font and the result says so under `normalized`. On the CLI, `--workspace DIR` writes the `brand.json` in DIR instead of the current directory (and implies `--scope workspace`). A workspace pairing replaces embedded `fonts.heading`/`fonts.body` entries (other roles stay), and the result lists them under `workspace.replaced`. Both fetch the fonts immediately, so an unknown family fails at once, and neither changes existing documents.

`vixl_document(action='create')`, `Session.create` and `vixl new` then download (or reuse from the cache) and embed the workspace fonts as part of the creation step, and report them under `workspace_fonts` (`pairing`, and `applied.heading`/`applied.body` with each font's `name` and whether it came `from` the pairing or `fonts`). Fonts are embedded in each document, so files stay portable. Passing `font_pairing` to `vixl_document(action='create')`, `workspace_fonts: false` (CLI `--no-workspace-fonts`) skips them. When a pairing cannot be fetched (offline, empty cache), the document is still created and `workspace_fonts.error` says why; run `font-pair` later. The CLI uses the `brand.json` beside the new document (`--scope workspace` writes it in the current directory).

MCP: `vixl_reference('fonts')` (views `fonts`, `font`, `pairings`, `pairing`, `principles`), `font-pair`, `font-install`. REST: `GET /typefaces`, `GET /typefaces/pairings`, `POST /typefaces/pair`, `POST /typefaces/install`.

## Making a font

To make a typeface or an icon font, draw the glyphs as layers and let the document's font design map them:

1. `font-design` with `family` (required to build) and `em` (pixels per em, default 200; ascent 0.8 em, descent
   0.2 em, x-height 0.5 em, cap height 0.7 em unless set).
2. `font-grid` with `chars` (`"ABC…"` or `uppercase`, `lowercase`, `letters`, `digits`, `punctuation`, `ascii`):
   one cell per character, `advance` wide (default 0.6 em), with `font-rN-cap`, `font-rN-x`, `font-rN-baseline` …
   guides. Read the cells' `origin` (baseline start) from `state.font_design.glyphs`.
3. Draw each glyph inside its cell with shapes, paths and stroked lines (several per `vixl_apply` batch). Every
   visible vector layer centred in the cell belongs to the glyph; the glyph is the union of their fills and outlined
   strokes. Cut counters with path holes or `pathfinder` `subtract`, not with a light shape on top.
4. Proof: `font-build` (registers the family with spaces as hyphens), a text layer with that `font`, `vixl_render`.
5. Tune `font-glyph` `advance` per character and `font-design` `kerning` (`{"AV": -12}` in pixels), then export
   `NAME.otf`, `.ttf` or `.woff`.

Icons need no grid: `font-glyph` with `char: "U+E001"` and `target` uses the named layers, sitting on their
bottom edge with a side bearing each side.

```json
[
  {"type": "font-design", "family": "Block Sans", "em": 200},
  {"type": "font-grid", "chars": "LT"},
  {"type": "shape", "shape": "rectangle", "name": "l-stem", "x": 70, "y": 70, "width": 28, "height": 140, "fill": "black"},
  {"type": "shape", "shape": "rectangle", "name": "l-foot", "x": 70, "y": 186, "width": 80, "height": 24, "fill": "black"},
  {"type": "shape", "shape": "rectangle", "name": "t-bar", "x": 225, "y": 70, "width": 110, "height": 24, "fill": "black"},
  {"type": "shape", "shape": "rectangle", "name": "t-stem", "x": 266, "y": 70, "width": 28, "height": 140, "fill": "black"},
  {"type": "font-design", "kerning": {"LT": -30}},
  {"type": "font-build"},
  {"type": "text", "text": "TLT", "font": "Block-Sans", "size": 120, "x": 50, "y": 320, "color": "black"}
]
```

Details, limits and the export formats: [making a font](../../../docs/guides/text/custom-fonts.md).

## Rolling a direction

When a brief leaves the look open, roll instead of settling for defaults:

```bash
vixl roll --for poster --size instagram-post --mood warm
vixl roll --seed 11 --lock palette=sage --lock pairing=dm-serif-dm-sans
```

A roll draws from Vixl's house style: it first draws a tier (`safe`, `bold` or `avant-garde`; `--variety low` is safe only, `medium` is mostly safe, `high` uses every tier), then picks a pairing, a light or dark mode, a palette whose mood fits, a layout suited to the purpose and canvas, the type scale, density, accent, style, finishing look and headline treatment. The purpose (`--for poster|social|slides|document|form|diagram|logo|motion` or an alias such as `story`, `deck`, `icon`, the same names `vixl new --purpose` takes; else the brief kind or the document's named size) weights every choice: slides favour UI sans pairings and tight scales, documents editorial serifs, light mode and airy density, diagrams dense density, posters display faces, large scales, a visible finish and about half dark. Bold and avant-garde rolls, and expressive moods (playful, bold, loud …), set `headline: large`, so the headline fills the canvas; quiet rolls keep `headline: measured`. `--lock tier=bold` explores one tier; `vixl house show slides` prints a purpose profile. Results report `purpose`, `purpose_source`, `tier` and each choice's tier. It returns the steps and a ready `layout-apply` operation. The same seed reproduces it; a document stores its rolled direction in `design_defaults`, so later rolls in it do not change. A roll also sets two details: `cta` (`pill` or `button`: how the call to action is set) and `date` (`highlight` or `plain`: whether a date line sits on an accent highlight); lock them like any choice (`--lock cta=button`). Roll several times, preview, and keep the one you like (MCP `vixl_reference('roll')` previews and the `roll` step of `vixl_apply` applies; REST `GET /roll`). `--apply` leaves slots you did not fill out (`--unfilled omit`, the default when you pass `--set`/`slots`), so the result passes `check` with no second layout pass; `--unfilled blank` keeps `[Label]` placeholders for slots to fill later.


### Field-report corrections

`check` reports `code: runt` (review) when wrapped display text (24 px+) leaves under 20% of the longest line, or one word under half of it (when the paragraph has more words than lines), alone on its last line; set `wrap`, widen the box or break the line.

### Line breaking, tab stops, accent words, small caps and hanging punctuation

- `text-layout` `wrap` (also `rich-text` with a width): `greedy` (fill each line), `balance` (same line count, even
  widths: headings, titles, short text) or `pretty` (no one-word last line: body text, lyrics). Kept when the box is
  resized. Breaks are shared by PNG, SVG, PDF and PPTX (explicit line breaks there). Headings and layout headlines
  default to `balance`; `wrap: "greedy"` restores greedy breaks.
- `tabs` on `text`/`text-set` (plain text): `[{at, align, leader}]`, `at` in px or `"100%"` of the box, `align`
  `left`/`right`/`center`/`decimal`, `leader` such as `"."`. Each `\t` moves to the next stop; a line with a tab is
  not wrapped. PPTX gets native tab stops with the leader written as characters. Tables take a column `leader`.
- `layout-apply` `accent_words: ["Winter"]` styles whole-word, any-case matches in the headline with
  `@accent-text` (rich-text spans); a word not found is a warning. `accent` with a list is read as `accent_words`.
  `text`/`text-set` take `accent_words` too (the layer becomes rich text), and rich-text Markdown has the flags
  `[Winter]{accent}` (`@accent-text`) and `[Sale]{accent-bg}` (`@on-accent` on an `@accent` highlight). All need the
  palette roles (`palette-apply` with roles, `layout-apply` or a roll) and are refused without them. Letter spacing is `tracking` in local pixels: on the layer (`text`/`text-set`, also for keyed or `${variable}` text) or on a span with `text-style`. `spacing` and `line_height` are line spacing. `text_transform` (`uppercase`, `lowercase`, `capitalize`, `small-caps`) cases the drawn text without changing the stored text, including keyed text. Width-only text boxes grow after copy/variable edits; fixed height stays fixed. Rich text-flow preserves size-based leading.
- Small caps: `text_transform: "small-caps"` (alias `font_variant: "small-caps"`) draws lowercase letters as small
  capitals, the font's own (OpenType `smcp`) or synthesized (capitals at 0.7 of the size, 5% tracking); a span takes
  `small_caps` (`[byline]{small-caps}`, `text-style small_caps: true`). PPTX writes `cap="small"`. Use it for eyebrows,
  bylines and acronyms in running text instead of uppercase at a smaller size.
- Hanging punctuation: `hanging_punctuation: true` on `text`, `text-set` or `rich-text` sets opening quotes, brackets
  and bullets outside the start of left-aligned lines (closing marks, stops and commas outside right-aligned line ends;
  both in centred lines), so the letters line up with the margin. Opt-in, for pull quotes and quoted headlines. The
  hung marks reach past the layer box, need no room in it (`fit-text` sizes the letters) and count in the bounds and
  safe-area checks: leave them a margin. PPTX gets `hangingPunct` and a negative first-line indent.
- `font pair` and `font install --role body` also fetch the body text face's italic (`body_italic` in the result,
  `skipped` with the reason when offline), so italic rich text uses the real italic. No optical sizes (`opsz`).

`check` judges text at its real use size (`legibility` finding, `code: use-size`, `action: review`): cover art (`album-art`, any 3000×3000 canvas) at 120 px, book covers (`ebook-cover`, 1600×2560) at a 160 px thumbnail, app icons at 60 px, social at its 320 px thumbnail, portrait infographics at 400 px, slides projected (36 px on a 1080 px slide), posters across a room (3% of the sheet's short side). Light weights (< 400) and faint colours need more; bold needs less. The finding names the needed font size or weight. Skip with `layer-intent decorative` or waive `legibility`.

The house style weights alignment and checks minor text by scale for social/poster work (2.2% of the short side). Large-text contrast is weight-aware: 18.66 px bold or 24 px regular. Explicit thumbnail settings and print/deck profiles retain their own contexts. Use `gap: "2u"` (1u = half the body size) for shared spacing in `stack` and `layout-apply`.
