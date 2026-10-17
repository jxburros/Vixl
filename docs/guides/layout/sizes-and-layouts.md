# Named sizes and principled layouts

[Documentation home](../../README.md) · [Getting started](../../getting-started.md) · [Visual gallery](../../gallery.md)

## Named sizes

150 sizes are built in. Print sizes are stored in inches or millimetres with a default resolution, a standard bleed and a safe (live-area) margin; screen sizes are pixels with a recommended safe inset.

| Category | Examples |
| --- | --- |
| print | `letter`, `legal`, `tabloid`, `half-letter`, `a3`–`a7`, `b4`, `b5` |
| stationery | `business-card`, `business-card-eu`, `letterhead`, `letterhead-a4`, `envelope-10`, `postcard`, `invitation`, `certificate`, `menu`, `book-6x9`, `magazine`, `sticker`, `ticket` |
| photo / poster | `photo-4x6` … `photo-8x10`, `poster-11x17`, `poster-18x24`, `poster-24x36`, `a0`–`a2` |
| packaging | `cd-cover`, `vinyl-cover`, `album-art` (also `podcast-cover`), `ebook-cover` (also `book-cover`), `tshirt-print`, `mug-wrap` |
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

Operations: `{"type": "canvas", "size": "a4", "orientation": "landscape", "bleed": true, "dpi": 300}`; `canvas.preset` and `artboard.preset` accept the same names (older preset names still work). MCP: `vixl_document(action='create', path, size="letter", bleed=true)` and `vixl_reference('sizes')`.

A sized canvas records `size`, `dpi`, `physical`, `bleed` and `safe` (pixels; print sizes default to a quarter inch, story sizes to 250 px at the top and bottom and 60 px at the sides, as a `{left, top, right, bottom}` object when the sides differ), and generated guides `trim-*` and `safe-*` (trim guides sit exactly on the trim, which can be a half pixel with a 37.5 px bleed; safe guides round inward to whole pixels, and the print and safe-area checks allow 0.5 px, so text on an older document's half-pixel guide still passes), so layers can be anchored with constraints such as `{"left": "guide:safe-left.left"}`. A document made at a custom size (`vixl new 1000x1000`, `Project(w, h)`) or resized to one gets the craft default
safe area, 5% of the short side (50 px on 1000×1000); a named size keeps its own, including an explicit none (favicons,
sprites, wallpapers). A custom canvas resize drops the size metadata and generated guides but keeps `dpi` and any guide a
layer is anchored to. Full-bleed pictures in layouts (memes, photo captions, split images) are marked `allow_crop`, so
only their copy has to sit inside the safe area. Export uses the canvas dpi for PNG/JPEG/TIFF/PDF metadata, and `vixl check` tests text and artwork against the safe area by default (`--checks print` also uses the bleed).

Icon sets: design on `favicon` (or any square canvas) and run `vixl export-icons --out icons --set web|apple|android|windows|all`, or export `favicon.ico` directly (`--icon-sizes 16 32 48`).

## Layouts: structure without sameness

Fixed templates make every adopter look alike. A layout is a composition system instead: it encodes a design principle, reads the canvas (aspect ratio, safe area, bleed, dpi) and uses a seed to choose among sound variations. The result is ordinary, editable layers plus the system they came from:

- **Color roles** — swatches `@background`, `@surface`, `@ink`, `@muted`, `@accent`, `@accent-text` and `@on-accent`, assigned from a palette with checked contrast: ink at least 7:1 on the background, muted and accent text at least 4.5:1 on the background and surface panels, the accent at least 3:1. Retint a whole layout by editing one swatch.
- **Type scale** — character styles `caption`, `body`, `lead`, `subhead`, `title`, `headline` and `display` from a medium-appropriate base size and a modular ratio (`minor-third` 1.2 … `golden` 1.618). Print bases are set in points at the canvas dpi. Safe compositions and rolled directions on social and poster canvases keep every role at least 2.2% of the canvas short side (24 px on 1080), the minor-text minimum the legibility check also uses. Without `base_size`, every layout also sets each role at least as large as the check's use size asks of a regular face: 36 px on a 1080 px slide, 3% of a poster's short side, 10 px at a cover's 120 px or a book cover's 160 px thumbnail, 10 px at a 400 px thumbnail for a portrait diagram (see [Size at real use](../text/typography.md#size-at-real-use)).
- **Spacing** — margins from the density (`airy`, `balanced`, `dense`), never inside the safe area, and gaps on a spacing unit (half the body size, at least 2 px); `gap` overrides the content-stack gaps in pixels or units such as `"2u"`. Text and buttons stay inside the canvas safe area: type shrinks until they fit, and on a 3:1 banner the safe compositions set their copy in two columns. Rails, panels, accents and full-bleed pictures are marked as decoration or intentional crop.
- **Corners** — buttons, panels and rounded parts of placed containers take the document's corner style (the rolled `corner`, else the house corner, sharp).
- **Details** — a rolled direction also says how the call to action and a date line look. `cta: "pill"` sets the `cta` slot as a pill (fully rounded ends, whatever the corner style); `cta: "button"` keeps the corner-styled button. `date: "highlight"` sets the composition's date line (the first short one-line label, caption, subtitle or body that reads as a date, such as `Fri · November 19` or `21/6`) in `@on-accent` on an `@accent` highlight whose edge stays on the column edge; `date: "plain"` leaves it as text. The roll picks them from the seed, by tier (pills about two rolls in five for safe directions, three in five for bold ones; highlights a little less often), never pills for square-cornered styles (Swiss, brutalist, Bauhaus, editorial …) and always for a pill corner. A layout's own button style (the product card's rounded button) still wins, and the event poster keeps its date block. Lock them like any other choice (`--lock cta=button --lock date=plain`), pass them in `direction`.
- **Rules and the copy** — a footer rule keeps one spacing unit between itself and the last line of copy: copy too tall to leave that room is set smaller, as copy that would leave the safe area is. Rule accents above the copy already keep at least one unit. One unit is the smallest step of the spacing scale and twice the half-unit gap the [craft plan](../../project/craft-plan.md) counts as crowding.
- **Composition** — alignment, focal placement, split proportions, accent device (`rule`, `bar`, `dot`, `block`, `outline`, `none`) and button shape.

To carry a generated layout to another size, `adapt-layout` with `recompose: true` re-applies the saved layout recipe at the new canvas (replacing the generated layers and any manual edits to them); without it, adaptation scales and moves the existing layers proportionally.

Explicit seeds are deterministic. Without one, sparse designs get a fresh seed unless the document or workspace sets `variety: "fixed"`. The applied choices are recorded in `state.layout` (and reported in the change summary), so you can reproduce a result with its returned seed or pin any choice explicitly. See [safe variety](safe-variety.md) for safe pools, expanded roll dimensions and workspace history.

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
| `meme-top-bottom`, `meme-caption-above`, `meme-reaction` | text over or beside one picture, caption contrast | memes, social, GIFs |
| `meme-comparison`, `meme-four-panel`, `meme-labelled` | panels in reading order, short labels | memes, social |

```bash
vixl layout list
vixl layout show golden-section
vixl new instagram-portrait -o post.vixl
vixl layout apply hero-statement --set title='Spring collection' --set subtitle='New colors, same fit' \
  --set cta='Shop now' --palette sage --mode light --type-scale perfect-fourth --seed 7
vixl check
```

### Slots: fill in the blanks

Each layout is a form. `vixl layout show NAME` (or `vixl_reference('layouts')`) lists its slots, with a label and a hint for what each one means in that layout. In `event-poster`, for example, `label` is the date and `body` is one detail per line. Slot keys are `title`, `subtitle`, `body`, `label`, `cta`, `caption`, `items` (newline-separated; `Name | Price` rows for price lists, `Heading: text` for F-pattern) and `image` (an embedded asset ID); multi-panel layouts take `images`, a list of asset IDs in reading order.

- **Unfilled slots are blanks, not sample copy.** A slot the composition needs renders as a visible `[Label]` placeholder (`[Date]`, `[Time]`, `[Action]`) and is recorded in `state.blanks` and in the layout's `blanks` list. `check` reports every unfilled blank as an error, so placeholder text can never ship silently. An image slot without an asset draws a placeholder frame that is also a blank until you pass `image` or use `replace-contents`. Pass `unfilled: "omit"` to leave unfilled slots out instead: the layout is composed around the copy it has, passes `check`, and the layout record's `omitted` lists what was left out (supplying one later re-lays the layout out; text added by hand does not).
- **Unfilled image slots say how to fill them.** `vixl layout show NAME` gives the `image` slot a `fill_with` list, and the
  `layout-apply` result carries `next_steps` for every unfilled slot. For an image it names the frame layer, its
  `bounds` and `aspect_ratio`, and four options: **import** (`import-image` returns an asset; re-apply with `image=`
  and the same seed, or `replace-contents` on the frame), **resource** (`shape-place` a saved shape or container),
  **draw** (build it from `shape`, `pen`, `pathfinder`, `organic` and `paint` inside the bounds, group it, remove the
  placeholder; `rasterize` the group to get an asset for `replace-contents`) and **AI** (`vixl_ai_generate`, which needs a
  configured provider). Text slots get a re-apply hint with the seed.
- **Memes.** The six `meme-*` layouts are image slots plus caption rules; Vixl ships no meme images, so supply pictures
  you may use. Stroked captions (`meme-top-bottom`, `meme-labelled`, `meme-four-panel`) are uppercase (`uppercase: false`
  keeps the case), white with a black `stroke` style that the contrast check reads them through, and shrink until they
  fit their box without breaking a word. `meme-caption-above` and `meme-comparison` set plain dark text on white;
  `meme-reaction` sets a subtitle line on black. `items` holds one label or caption per line. For an Impact-style face
  install an OFL font such as Anton (`vixl font install Anton --role heading`, or `display_font`).

  GIF recipe: apply `meme-reaction` on `instagram-post`, then
  `{type: animate-preset, target: caption, preset: pop-in, duration: 400}` (or a looping `motion`), set the timeline
  (`timeline-set` 2–4 s, `loop: 0`), check a frame with `vixl_render(action='timeline')` and export with
  `vixl_export(kind='timeline', path="reaction.gif", fps=15)`. Keep GIFs short and small: 480–600 px wide and few colours.
- **Unused slots are errors.** Copy for a slot the layout does not read on this canvas, such as `subtitle` on `event-poster`, fails with `unused_slot` and lists the slots it does use, instead of being dropped.
- **Fill blanks by re-applying.** Re-apply with the copy, `replace: true` and the `seed` the first pass reported. The composition stays the same and type is sized for the real copy. Editing a blank layer's text directly also clears it.

**Accent words.** `accent_words: ["Winter"]` sets those words of the headline (the `title` slot) in the accent text
color (`@accent-text`, the accent adjusted to read on the background), through ordinary rich-text spans, so the
two-tone headline needs no second pass. Matching is by whole word and ignores case (`winter` accents "Winter" but not
"Winterland"); every match is styled. A word that is not in the headline is a warning and is listed under the layout
record's `accent_words.missing`; a layout that sets its headline on the accent color (a filled hero cell) leaves it
one color and warns. `accent` with a list is read as `accent_words` and reported under `normalized`, since `accent`
alone names the accent device (`rule`, `bar` …).

```json
{"type": "layout-apply", "name": "hero-statement", "title": "Winter warmers on the quay", "accent_words": ["Winter"],
 "seed": 3, "unfilled": "omit"}
```

Layout headlines also wrap balanced (`wrap: "balance"`, see
[line breaking](../text/typography.md#line-breaking)).

`prefix` namespaces layer names, `replace: true` removes the previous layout's layers, `transparent: true` skips the background, and `font`/`display_font` use registered fonts. Without them, layouts use the document typography set by `font pair`, or the proofing fallback font, which `check` flags.

### Palette roles and keeping your order

`palette` can be a name or a list of colors. Roles are assigned by luminance and chroma and follow mode: in light mode the
lightest color becomes `@background`, in dark mode the darkest, so a list passed as "background, surface, accents" can
come back rearranged. The layout record explains it: `layout.mode` with `layout.mode_source` (the `mode` argument,
inherited from the canvas background, taken from the first palette color, or rolled from the seed) and `layout.roles`,
one entry per role with its `color`, `source` (`palette[2]`, `derived`, `explicit`) and `reason`. When a custom list is
rearranged, `layout.notes` says how to take control:

- `keep_order: true` uses the list as given: first color `@background`, second `@surface`, the rest accents (the first is
  `@accent`). Nothing is lightened or darkened to suit a mode; mode follows the first color. `@ink` is not part of that
  order, so it is derived from the background hue for 7:1 contrast, and `@muted`, `@accent-text` and `@on-accent` are derived
  from it.
- `colors: {background: "#0f172a", accent: "#38bdf8"}` sets individual roles and wins over everything else. A given
  `background` also sets the mode (dark or light from its lightness), and the other roles are chosen to read on it.

`palette-apply` works the same way (`roles` true/false or `{role: color-or-palette-index}`, `keep_order`) and records the
mapping as `palette_roles` in the apply result. `palette-generate` never assigns roles; it only adds numbered swatches.

### Rolling the dice

`seed` accepts `"random"`. Choices you do not make (palette, mode, type scale, density, alignment, accent) are rolled from the seed and listed in the layout record's `rolled`. When most of them were rolled, the result says so and suggests exploring: apply with `seed: "random"` a few times, preview, and keep the seed you like. `vixl roll` (`vixl_reference('roll')`) rolls a whole direction at once: a font pairing, a palette whose mood fits it, a layout suited to the purpose and canvas, and its parameters, returned as a ready `layout-apply` operation. Use `--lock` to keep any choice fixed while re-rolling the rest. Applying a roll (`roll --apply`, the `roll` step of `vixl_apply`) honours `unfilled` (`omit` or `blank`, CLI `--unfilled`): when you pass `slots` the default is `omit`, so slots you did not fill are left out and the applied direction passes `check` without a second layout pass; with no slots every slot would be left out, so the default is `blank` and the `[Label]` placeholders show what to fill. The result lists `unfilled_slots` (blanks) or the layout's `omitted` slots.

Standalone design-system pieces:

```json
{"type": "type-scale", "base": 18, "ratio": "golden", "prefix": "t-"}
{"type": "guidance", "name": "typography", "style": "typography"}
```

Built-in guidance now covers `overall`, `minimal`, `editorial`, `playful`, `logo`, `pixel-art`, `typography`, `color`, `layout`, `accessibility`, `print`, `icon`, `motion`, `brush` and `image-rights`.

Layouts are text compositions, which is why open requests drift toward posters. For icons, characters, scenes, patterns,
mandalas and diagrams, `vixl_reference(brief)` (CLI `vixl guide BRIEF`) names the approach, operations, layouts, looks and
styles for the kind of work and gives a runnable example; see [looks](../finishing/looks.md) and [styles](styles.md).

Layouts are a starting structure, not a finished design: inspect, check and refine them. For open-ended briefs, applying a layout first prevents the common failure modes of unconstrained generation (no hierarchy, crowded edges, low contrast, arbitrary sizes).
