# Typography: catalog, pairings and installs

[Documentation home](README.md) · [Getting started](getting-started.md) · [Visual gallery](gallery.md)

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

MCP: `vixl_fonts` (views `fonts`, `font`, `pairings`, `pairing`, `principles`), `vixl_font_pair`, `vixl_font_install`. REST: `GET /typefaces`, `GET /typefaces/pairings`, `POST /typefaces/pair`, `POST /typefaces/install`.

## Rolling a direction

When a brief leaves the look open, roll instead of settling for defaults:

```bash
vixl roll --for poster --size instagram-post --mood warm
vixl roll --seed 11 --lock palette=sage --lock pairing=dm-serif-dm-sans
```

A roll picks a pairing first, then a palette whose mood fits it, a layout suited to the purpose and canvas, and the mode, type scale, density and accent. It returns the steps and a ready `layout-apply` operation. The same seed reproduces it. Roll several times, preview, and keep the one you like (MCP `vixl_roll`, REST `GET /roll`). With a document (`vixl -p DOC roll` or the session's current document) the preview uses its canvas, so it picks the same direction `--apply` will.
