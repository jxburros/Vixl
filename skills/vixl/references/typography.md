# Typography: catalog, pairings and installs

Vixl bundles DejaVu Sans only as a proofing fallback, so text renders before anyone has chosen type. Design type comes from a researched catalog and is downloaded only when you ask. The default `fonts` check warns while any text still uses the fallback.

## The catalog

104 open-licensed (OFL, Apache, UFL) Google Fonts families: neo-grotesque, grotesque, geometric and humanist sans; old-style, transitional, didone, slab and glyphic serifs; monospace, display, handwriting and blackletter; and Noto families for Japanese, Chinese, Arabic and Devanagari. Each entry records its classification, verified weights and italics, x-height, width, stroke contrast, era, mood, suitable roles, best uses, misuse cautions and a note on its character. Every family, weight and italic was checked against the Google Fonts CSS API. `scripts/verify_fonts.py --check src/vixl/data/fonts.json src/vixl/data/font-pairings.json` repeats the check.

```bash
vixl fonts --category serif            # or a classification: --category didone
vixl fonts --role heading --mood playful
vixl font show "Space Grotesk"         # full entry plus the pairings that use it
```

## Pairings

60 curated heading/body pairings. They are described by their relationship (`contrast` of classification, `superfamily`, or `concord`), mood and best uses, a one-line reason they work, a caution and, where one exists, a published source. Single-family pairings get weight contrast from one family.

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

## Installing

```bash
vixl font pair dm-serif-dm-sans        # heading + body; or: vixl font pair random --mood warm
vixl font install "Fraunces" --weight 700 --role heading
vixl font use dm-sans-400 --role body  # reassign an installed font
vixl font list                         # registered fonts and the document typography
```

Installs fetch one static TTF per style from the Google Fonts CSS API (`fonts.gstatic.com`, HTTPS only, bounded size). Any Google Fonts family works, not only catalog entries. Files are validated and cached in `~/.cache/vixl/fonts` (set `VIXL_FONT_CACHE` to move it), then embedded in the document and registered as `family-weight` (for example `dm-serif-display-400`). A saved `.vixl` file therefore renders anywhere without the network. `font pair` and `--role` set `state.typography`, and layouts use it for headings and body unless you pass `font`/`display_font`. The structured operation is `{"type": "font-register", "name": "dm-sans-400", "role": "body"}`.

Each install reports where the font came from, so agents and CI can verify offline behaviour: `source.origin` is `cache` (served from `source.cache_file` with no network) or `download` (with the Google Fonts stylesheet in `source.stylesheet` and the font file in `source.url`; `cache_file` is the copy it was stored as, or null when the cache is not writable). `source.cache_dir` is the cache directory and `source.cache_dir_from` says whether `VIXL_FONT_CACHE` or the default chose it. `family`, `weight`, `italic` and `name` give the resolved style, and `file` names the embedded asset (`fonts/<sha256>.ttf`), its byte size and hash. `font pair` returns this for both the heading and body fonts plus `origin` (`cache`, `download` or `mixed`); `vixl_roll` with `apply` returns the same under `fonts`. `source.bundled_fallback` is always false: a font that cannot be downloaded or found in the cache fails with `font_download_failed` (or `unknown_font`), and the bundled DejaVu Sans is never substituted silently. To run offline, pre-fill the cache (or set `VIXL_FONT_CACHE` to a directory holding `family-weight[-italic].ttf` files such as `inter-400.ttf`) and check for `origin: "cache"`.

Text can also follow a role: `text`/`text-set` accept `font: "heading"` or `"body"` (CLI `--font heading`), and built-in templates give their largest text the heading role and the rest body. Changing a role (`font pair`, `font install --role`, `font use --role`) re-fonts every text layer with that role; before any typography is set they use the proofing fallback. `text-set` also accepts a registered font name to change one layer's face. An unknown font fails with `missing_font`, listing the registered fonts and roles.

### Workspace default fonts

A workspace can give every new document the same typography. `vixl_font_pair(pairing=..., scope="workspace")` (CLI `vixl font pair NAME --scope workspace`, REST `POST /typefaces/pair` with `"scope": "workspace"`) writes `pairing` into the workspace `brand.json`; `vixl_font_install(family=..., role="heading"|"body", scope="workspace")` (CLI `vixl font install FAMILY --role heading --scope workspace`) embeds that one style in `brand.json` under `fonts.<role>`, overriding the pairing for that role. A workspace pairing replaces embedded `fonts` entries, and the result lists them under `workspace.replaced`. Both fetch the fonts immediately, so an unknown family fails at once, and neither changes existing documents.

`vixl_document_create`, `Session.create` and `vixl new` then download (or reuse from the cache) and embed the workspace fonts as part of the creation step, and report them under `workspace_fonts` (`pairing`, and `applied.heading`/`applied.body` with each font's `name` and whether it came `from` the pairing or `fonts`). Fonts are embedded in each document, so files stay portable. Passing `font_pairing` to `vixl_document_create`, `workspace_fonts: false` (CLI `--no-workspace-fonts`) skips them. When a pairing cannot be fetched (offline, empty cache), the document is still created and `workspace_fonts.error` says why; run `vixl_font_pair` later. The CLI uses the `brand.json` beside the new document (`--scope workspace` writes it in the current directory).

MCP: `vixl_fonts` (views `fonts`, `font`, `pairings`, `pairing`, `principles`), `vixl_font_pair`, `vixl_font_install`. REST: `GET /typefaces`, `GET /typefaces/pairings`, `POST /typefaces/pair`, `POST /typefaces/install`.

## Rolling a direction

When a brief leaves the look open, roll instead of settling for defaults:

```bash
vixl roll --for poster --size instagram-post --mood warm
vixl roll --seed 11 --lock palette=sage --lock pairing=dm-serif-dm-sans
```

A roll draws from Vixl's house style: it first draws a tier (`safe`, `bold` or `avant-garde`; `--variety low` is safe only, `medium` is mostly safe, `high` uses every tier), then picks a pairing, a light or dark mode, a palette whose mood fits, a layout suited to the purpose and canvas, the type scale, density, accent, style and finishing look. The purpose (`--for poster|social|slides|document|form|diagram|logo|motion`, else the brief kind or the document's named size) weights every choice: slides favour UI sans pairings and tight scales, documents editorial serifs and light mode, posters display faces, large scales, a visible finish and about half dark. `--lock tier=bold` explores one tier; `vixl house show slides` prints a purpose profile. Results report `purpose`, `purpose_source`, `tier` and each choice's tier. It returns the steps and a ready `layout-apply` operation. The same seed reproduces it. Roll several times, preview, and keep the one you like (MCP `vixl_roll`, REST `GET /roll`). `--apply` leaves slots you did not fill out (`--unfilled omit`, the default when you pass `--set`/`slots`), so the result passes `check` with no second layout pass; `--unfilled blank` keeps `[Label]` placeholders for slots to fill later.
