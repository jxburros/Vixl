# HTML presenter

[Documentation home](README.md) · [Getting started](getting-started.md) · [Visual gallery](gallery.md)

A multi-page document ([pages, slides and decks](slides.md)) exports as one `.html` file that
presents in any browser, with no server, no network and no software to install: double-click it,
email it, or put it on a USB stick.

```bash
vixl export deck.html                                    # the whole deck, hidden pages left out
vixl export deck.html --pages 1-3,5 --presenter-theme light
vixl export deck.html --slide-images png --start-slide results --no-notes
vixl export deck.html --no-presenter                     # the old one-image artwork page instead
```

```python
project.export("deck.html")                                   # bytes, and a file when given a path
project.export("deck.html", presenter={"theme": "auto", "notes": False}, pages="1-3")
```

HTML export of a document with pages is the presenter. A single-page document, `--page N`
(one page) or `presenter=False` keep the plain artwork page described in [studio](studio.md);
`presenter=True` presents any document, even one canvas. Through MCP, `vixl_export_file(path="deck.html",
pages="1-3", presenter={"theme": "light"})`; through REST, `POST /export` with `{"format": "HTML",
"presenter": {…}}`.

## Options

| Option | CLI | Values | |
| --- | --- | --- | --- |
| `pages` | `--pages 1-3,5,intro` | numbers, ranges and names | Which pages and in what order. Hidden pages are skipped unless named here. |
| `theme` | `--presenter-theme` | `dark` (default), `light`, `auto` | The surround (letterbox) and controls; `auto` follows the system. |
| `slide_images` | `--slide-images` | `svg` (default), `png` | Slides as inline vectors or as embedded PNGs (sized by `--scale`). |
| `notes` | `--no-notes` | `true` (default), `false` | Whether speaker notes travel in the file. |
| `start` | `--start-slide` | a number or page name | The slide shown first when the URL has no `#N`. |
| `title` | | text | The browser tab title. Default: the form `title` setting, else the first slide's title. |
| `presenter` | `--presenter` / `--no-presenter` | `true`, `false`, or the options above | Force or refuse the presenter; options imply it. |

The result reports `slides`, `slide_images`, `notes` (pages with notes), `raster_fallbacks` and
`warnings`. `vixl export` also accepts `--set` variables and `--svg-policy strict` (an error when an
SVG slide would need an embedded raster). Profiles, artboards, comps, CMYK and proofing do not apply.

## Presenting

| Keys | |
| --- | --- |
| Right, Down, Space, PageDown, N | Next slide |
| Left, Up, Shift+Space, PageUp, P, Backspace | Previous slide |
| Home, End | First, last slide |
| a number, then Enter | Go to that slide |
| O, Esc | Overview grid of every slide (arrows move, Enter or a click opens one) |
| F | Fullscreen |
| B, W (or .) | Black, white screen; any step brings the slide back |
| S | Speaker view in a second window |
| ? | List the shortcuts |

Clicking or tapping the left quarter of a slide goes back and the rest goes forward; swiping
left or right on a touch screen moves between slides. A progress bar runs along the bottom, and a
control bar (previous, next, overview, fullscreen, speaker, help) appears when the pointer moves and
hides itself while presenting. Each slide has a link: `deck.html#3` opens slide 3 (so does
`#results`, a page name), and the address follows the slide as you move. Slides scale to the
window at the document's aspect ratio with letterboxing, so a 16:9 deck on a 4:3 screen keeps its
shape.

## Transitions

Each page's `transition` setting plays when it appears, using CSS animations only:

| Page setting | Plays |
| --- | --- |
| `fade` | Cross-fade in |
| `push` | The new slide pushes the old one off to the left |
| `cover` | The new slide slides in over the old one |
| `wipe` | Revealed from left to right |
| `split` | Revealed outward from the middle |
| `zoom` | Scales and fades in |
| none (default) | Cuts |

Going backwards plays the transition of the slide being left, in reverse. A key pressed during a
transition finishes it at once. Visitors who ask their system for reduced motion get cuts.

## Speaker view

`S` (or the **Speaker** button) opens a second window with the current slide, the next slide, the
speaker notes (page `notes`, with `A-` and `A+` buttons or `+` and `-` for their size), the slide
count, an elapsed timer with pause and reset, and the time of day. The two windows stay in step
whichever one you navigate, and `B` or `W` in the speaker window blanks the audience's screen. Move
the speaker window to your own display and the main window to the projector.

It works from a file on disk: the speaker window is the same file opened with `?speaker`, and the
windows exchange the current slide through `postMessage`, `BroadcastChannel` and `localStorage`
(any one is enough). If your browser blocks pop-ups, allow them for the file, or open
`deck.html?speaker` in another window yourself.

**Notes travel in the file.** Anyone with the file can open the speaker view or read the notes in
its source. Export with `--no-notes` (`notes: false`) for the copy you share.

## Slides: vectors, with raster fallbacks

By default every page is the ordinary SVG export inlined into the file: shapes, gradients and
text drawn as glyph outlines. They stay crisp at any size or zoom, look the same on every machine
with no fonts installed, and a 60-slide text deck is a couple of megabytes.

Whatever SVG cannot draw the same way (effects such as ink-blot, layer styles it cannot express,
masks, lookup tables, blend modes that need the backdrop, paint and some warped text) is embedded
as an image of exactly what Vixl renders, for that layer only, at the canvas's pixel size. Those
layers are listed under `raster_fallbacks` by slide number with the reason, so nothing changes
appearance silently. `--svg-policy strict` turns them into an error instead.

`--slide-images png` embeds each page as one PNG instead (sized by `--scale`, so `--scale 2` suits
a 4K display): identical to the preview, larger, and not vector. Use it when a deck is mostly
fallbacks anyway.

## Accessibility

- Each slide is a labelled group, `Slide 2 of 8: Results`, named by the page's title layer (a
  text layer called `title`, `heading` or `headline`, else the largest text near the top; else
  the page name). The label is announced when the slide changes, and the slide being shown is the
  only one in the accessibility tree.
- Every slide carries a visually hidden text layer for screen readers: the title as a heading,
  then the page's other text from top to bottom. Master layers and footer-like layers (named
  footer, page-number, source and the like) are left out as chrome. The picture itself is hidden
  from assistive technology, so nothing is read twice.
- Everything works from the keyboard; the controls are real buttons; focus is visible; the overview
  can be tabbed through. Transitions and the progress animation respect `prefers-reduced-motion`.
- Because the slide text is outlines, it cannot be selected or searched on the slide. The hidden text
  layer is the readable copy. (The PDF export has real, selectable text.)
- The interface strings (button labels, the shortcut list) are English. The document's language
  is the `form` setting `lang` (default `en`).

## Printing

Printing the page (or Save as PDF) gives one slide per page at the slide's size: physical size when
the canvas has a `dpi`, otherwise 7.5 inches tall at the canvas's aspect ratio, like the PowerPoint
export. Controls are hidden and backgrounds print. Without JavaScript the page is simply the slides
listed one under another.

## Self-contained, safe and reproducible

- No requests of any kind: no fonts, scripts, styles or images from anywhere. The page carries a
  Content-Security-Policy of `default-src 'none'` that names its one inline script and one inline
  style block by hash, so nothing else can run, and there are no third-party scripts.
- The same document always produces the same bytes. Ids inside each slide are prefixed per slide
  so gradients and masks of different slides cannot collide.
- Output over 24 MiB adds a warning (browsers open huge files slowly): use SVG slides, a smaller
  `--scale`, or fewer image-heavy slides. The document's size limit (256 MiB) is a hard stop.
- The script uses ordinary modern web features (CSS `aspect-ratio`, `inset`, `:focus-within`,
  `BroadcastChannel`); current Chrome, Edge, Firefox and Safari run it. It is tested in Chromium.
