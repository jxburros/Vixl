# Named sizes and principled layouts

## Named sizes

150 sizes are built in. Print sizes are stored in inches or millimetres with a default resolution, a standard bleed and a safe (live-area) margin; screen sizes are pixels with a recommended safe inset.

| Category | Examples |
| --- | --- |
| print | `letter`, `legal`, `tabloid`, `half-letter`, `a3`–`a7`, `b4`, `b5` |
| stationery | `business-card`, `business-card-eu`, `letterhead`, `letterhead-a4`, `envelope-10`, `postcard`, `invitation`, `certificate`, `menu`, `book-6x9`, `magazine`, `sticker`, `ticket` |
| photo / poster | `photo-4x6` … `photo-8x10`, `poster-11x17`, `poster-18x24`, `poster-24x36`, `a0`–`a2` |
| packaging | `cd-cover`, `vinyl-cover`, `album-art`, `tshirt-print`, `mug-wrap` |
| social | `instagram-square`/`-portrait`/`-landscape`/`-story`, `facebook-post`/`-cover`, `x-post`, `linkedin-post`, `youtube-thumbnail`/`-banner`, `pinterest-pin`, `tiktok`, `discord`, `profile-picture` |
| web, ads, email | `og-image`, `web-hero`, `blog-featured`, IAB `medium-rectangle`, `leaderboard`, `billboard`, `half-page`, `mobile-banner`, `email-header` |
| video, slides, screens | `video-1080p`, `video-4k`, `video-vertical`, `slide`, `slide-4x3`, `desktop-4k`, `phone-wallpaper` |
| app stores | `iphone-screenshot`, `ipad-screenshot`, `android-screenshot`, `play-feature-graphic` |
| icons | `favicon` (512 master), `favicon-16/32/48`, `apple-touch-icon`, `android-chrome-192/512`, `pwa-maskable`, `android-adaptive-icon`, `ios-app-icon`, `macos-app-icon`, `windows-tile`, `icon-16` … `icon-256` |
| logos | `logo`, `logo-mark`, `logo-horizontal`, `logo-stacked`, `wordmark`, `logo-wide`, `logo-badge`, `logo-avatar`, `email-logo` |
| game | `sprite-16/32/64`, `tile-16/32`, `game-cover`, `game-banner` |

```bash
vixl sizes --category print            # list (also --search card)
vixl sizes show a5 --landscape --bleed --dpi 150
vixl new letter --bleed -o flyer.vixl  # or: vixl new favicon, vixl new logo-horizontal …
vixl canvas size instagram-story       # change an open document
vixl canvas dpi 300
```

Operations: `{"type": "canvas", "size": "a4", "orientation": "landscape", "bleed": true, "dpi": 300}`; `canvas.preset` and `artboard.preset` accept the same names (older preset names still work). MCP: `vixl_document_create(path, size="letter", bleed=true)` and `vixl_sizes_list`.

A sized canvas records `size`, `dpi`, `physical`, `bleed` and `safe` (pixels), and generated guides `trim-*` and `safe-*`, so layers can be anchored with constraints such as `{"left": "guide:safe-left.left"}`. A custom canvas resize drops the size metadata and generated guides but keeps `dpi` and any guide a layer is anchored to. Export uses the canvas dpi for PNG/JPEG/TIFF/PDF metadata, and `vixl check --checks print` uses the bleed and safe area.

Icon sets: design on `favicon` (or any square canvas) and run `vixl export-icons --out icons --set web|apple|android|windows|all`, or export `favicon.ico` directly (`--icon-sizes 16 32 48`).

## Layouts: structure without sameness

Fixed templates make every adopter look alike. A layout is a composition system instead: it encodes a design principle, reads the canvas (aspect ratio, safe area, bleed, dpi) and uses a seed to choose among sound variations. The result is ordinary, editable layers plus the system they came from:

- **Color roles** — swatches `@background`, `@surface`, `@ink`, `@muted`, `@accent`, `@accent-text` and `@on-accent`, assigned from a palette with checked contrast: ink at least 7:1 on the background, muted and accent text at least 4.5:1 on the background and surface panels, the accent at least 3:1. Retint a whole layout by editing one swatch.
- **Type scale** — character styles `caption`, `body`, `lead`, `subhead`, `title`, `headline` and `display` from a medium-appropriate base size and a modular ratio (`minor-third` 1.2 … `golden` 1.618). Print bases are set in points at the canvas dpi.
- **Spacing** — margins from the density (`airy`, `balanced`, `dense`), never inside the safe area, and gaps on a spacing unit.
- **Composition** — alignment, focal placement, split proportions, accent device (`rule`, `bar`, `dot`, `block`, `outline`, `none`) and button shape.

Seeds are deterministic. Without one, the seed comes from the content and canvas, so different copy gives a different but stable variation. The applied choices are recorded in `state.layout` (and reported in the change summary), so you can re-roll with another `seed` (or `"random"`) or pin any choice explicitly.

| Layout | Principles | Best for |
| --- | --- | --- |
| `hero-statement` | single focal point, scale contrast, negative space | social, posters, web, slides |
| `editorial-grid` | modular column grid, typographic hierarchy, rules | print, posters, web |
| `split-screen` | figure–ground zones, proportional division | web, social, slides, ads |
| `centered-axis` | symmetrical balance, optical centering | invitations, announcements |
| `asymmetric-balance` | asymmetric visual weight, tension | posters, social |
| `z-pattern` | Z reading path ending at the call to action | ads, web, banners |
| `f-pattern` | scannable left edge, parallel subheads | print, slides, infographics |
| `rule-of-thirds` | focal point on a thirds intersection | social, posters, photo |
| `golden-section` | golden-ratio division | print, web, social |
| `big-number` | data as focal point | infographics, slides |
| `quote-card` | typographic focal point, hanging punctuation | social, slides |
| `framed` | enclosure, symmetry, formality | certificates, invitations, menus |
| `diagonal-band` | diagonal energy | sales, sports, posters |
| `typographic-poster` | type as image, extreme scale contrast | posters, covers |
| `product-card` | proximity grouping, price emphasis | ecommerce, ads |
| `event-poster` | information hierarchy, chunked details | posters, flyers |
| `banner` | horizontal flow, CTA in terminal area | ads, headers, email |
| `letterhead` | identity consistency, quiet hierarchy | stationery |
| `business-card` | proximity, one alignment edge | stationery |
| `slide-title`, `slide-content` | one idea per slide, parallel bullets | slides |
| `logo-horizontal`, `logo-stacked`, `emblem`, `monogram` | clear space, reduction, small-size legibility | logos, badges |
| `app-icon` | keyline grid, single glyph | icons, favicons |
| `thumbnail-bold` | legibility at thumbnail size | YouTube, covers |
| `story-vertical` | UI safe zones, thumb-reach CTA | stories, reels, TikTok |
| `price-list` | tabular alignment, row rhythm | menus, price lists |
| `photo-caption` | scrim for contrast | social, covers |
| `minimal-mark` | negative space, restraint | posters, covers |
| `bento-grid` | modular tiles of varied span | web, slides, infographics |

```bash
vixl layout list
vixl layout show golden-section
vixl new instagram-portrait -o post.vixl
vixl layout apply hero-statement --set title='Spring collection' --set subtitle='New colors, same fit' \
  --set cta='Shop now' --palette sage --mode light --type-scale perfect-fourth --seed 7
vixl check
```

### Slots: fill in the blanks

Each layout is a form. `vixl layout show NAME` (or `vixl_layouts_list`) lists its slots, with a label and a hint for what each one means in that layout. In `event-poster`, for example, `label` is the date and `body` is one detail per line. Slot keys are `title`, `subtitle`, `body`, `label`, `cta`, `caption`, `items` (newline-separated; `Name | Price` rows for price lists, `Heading: text` for F-pattern) and `image` (an embedded asset ID).

- **Unfilled slots are blanks, not sample copy.** A slot the composition needs renders as a visible `[Label]` placeholder (`[Date]`, `[Time]`, `[Action]`) and is recorded in `state.blanks` and in the layout's `blanks` list. `check` reports every unfilled blank as an error, so placeholder text can never ship silently. An image slot without an asset draws a placeholder frame that is also a blank until you pass `image` or use `replace-contents`. Pass `unfilled: "omit"` to leave unfilled slots out instead.
- **Unused slots are errors.** Copy for a slot the layout does not read on this canvas, such as `subtitle` on `event-poster`, fails with `unused_slot` and lists the slots it does use, instead of being dropped.
- **Fill blanks by re-applying.** Re-apply with the copy, `replace: true` and the `seed` the first pass reported. The composition stays the same and type is sized for the real copy. Editing a blank layer's text directly also clears it.

`prefix` namespaces layer names, `replace: true` removes the previous layout's layers, `transparent: true` skips the background, and `font`/`display_font` use registered fonts. Without them, layouts use the document typography set by `font pair`, or the proofing fallback font, which `check` flags.

### Rolling the dice

`seed` accepts `"random"`. Choices you do not make (palette, mode, type scale, density, alignment, accent) are rolled from the seed and listed in the layout record's `rolled`. When most of them were rolled, the result says so and suggests exploring: apply with `seed: "random"` a few times, preview, and keep the seed you like. `vixl roll` (`vixl_roll`) rolls a whole direction at once: a font pairing, a palette whose mood fits it, a layout suited to the purpose and canvas, and its parameters, returned as a ready `layout-apply` operation. Use `--lock` to keep any choice fixed while re-rolling the rest.

Standalone design-system pieces:

```json
{"type": "type-scale", "base": 18, "ratio": "golden", "prefix": "t-"}
{"type": "guidance", "name": "typography", "style": "typography"}
```

Built-in guidance now covers `overall`, `minimal`, `editorial`, `playful`, `logo`, `pixel-art`, `typography`, `color`, `layout`, `accessibility`, `print`, `icon`, `motion` and `brush`.

Layouts are a starting structure, not a finished design: inspect, check and refine them. For open-ended briefs, applying a layout first prevents the common failure modes of unconstrained generation (no hierarchy, crowded edges, low contrast, arbitrary sizes).
