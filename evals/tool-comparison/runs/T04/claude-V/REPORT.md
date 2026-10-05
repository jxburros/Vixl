# T04 Logo kit: Tidewick Café (lane V, Vixl MCP)

**Timing:** start 2026-10-05 22:18:22 UTC, end 22:35:30 UTC (about 17 minutes). About 100 tool calls, counting every Vixl MCP, Bash, Read, Write and ToolSearch call.

## The mark

The mark is a navy disc holding an amber lamp or candle flame with a small navy inner flame (the "wick" of Tide*wick*), set above an amber wave. It uses two colors, navy `#14263b` and amber `#f2a541`, and no anchors or ship wheels. I drew it with Vixl `shape` operations: an ellipse plus cubic-Bézier `path` shapes on a 512×512 grid. I tried and rejected a round "lamp" circle, because it read as a person icon. I also tried a plain teardrop, which read as a water drop, and a rounded wick slot, which read as a house door.

Type: Fraunces 700 for the wordmark and Work Sans 500 for the tagline. Both are open-licensed Google Fonts, installed with `vixl_font_install`. Vixl's SVG export turns all lettering into outline paths. I checked every SVG: no `<text>`, no `<image>`, no font references, no base64.

## Files (all in this folder)

| File | How it was made |
| --- | --- |
| `logo-horizontal.svg` | `logo-horizontal.vixl` (1400×440, transparent). The mark is a group of 4 shapes resized to 320 px, with the "Tidewick" wordmark (200 px, navy) to its right and the tagline (54 px, navy) under the wordmark. Exported with `svg_policy="strict"`. |
| `logo-stacked.svg` | `logo-stacked.vixl` (1000×800, transparent). The mark (380 px) is centered over the wordmark (180 px) and tagline (52 px), each centered by computed x. Exported strict. |
| `mark.svg` | `mark.vixl` (512×512, transparent): navy disc, amber flame, navy inner flame, amber wave. Exported strict. |
| `mark-mono.svg` | `mark-mono.vixl` (512×512, transparent), navy only: a ring (stroked ellipse), the flame as a 30 px stroked outline, a solid inner flame and a solid wave. Exported strict. |
| `favicon.ico` | `favicon.vixl`, exported with `vixl_export_file(icon_sizes=[16,32,48])`. Checked with PIL: it contains 16, 32 and 48 px images. |
| `app-icon-1024.png` | `app-icon.vixl` (1024×1024): a full-bleed navy solid with the amber flame and wave at about 82% of the width. Square corners, no disc. |
| `logo-sheet.png` | `logo-sheet.vixl` (1600×1200), split into a cream half and a navy half. Each half shows the horizontal lockup, the stacked lockup, the marks, the app icon, and the mark at real 16, 32 and 64 px. |

Extras, not requested: `logo-horizontal-reversed.svg`, `logo-stacked-reversed.svg` and `mark-reversed.svg` are the on-navy versions. In these the disc is amber, the flame and wave are navy, the wordmark is cream and the tagline is amber. The `.vixl` sources are kept and stay editable. `work/` holds the intermediate PNGs (lockup and mark renders, small-size tests) that went into the sheet.

## How the sheet was built

I exported each SVG's source document from Vixl to PNG and imported the PNGs into `logo-sheet.vixl` with `vixl_import_image`. The lockups and marks were scaled down there. The 16, 32 and 64 px marks were exported from `mark.vixl` (cream side) and `mark-reversed.vixl` (navy side) at exactly those sizes, then placed at integer positions with no resampling. Labels are Work Sans. `vixl_check` (bounds, overlap, contrast, fonts) passed.

## Where I differed from the brief, and why

- **Versions on navy.** The navy-only mono mark would vanish on navy, so the navy half doesn't show it. Instead it shows the color mark as it falls on navy (the disc merges into the background, leaving the amber flame and wave) and the amber reversed mark. Every lockup appears on both backgrounds.
- **The mono mark is not a silhouette of the color mark.** My first version was a knockout: a navy disc with the flame and wave cut out, made with Vixl `pathfinder subtract`. Vixl writes that boolean as SVG alpha masks (`mask-type="alpha"`). When I rendered it in Inkscape, the mark came out as a faint grey disc, which fails the "looks the same on another computer" rule. I rebuilt the mono mark from plain strokes and fills instead (ring, flame outline, solid inner flame, solid wave), and it now renders correctly in Inkscape. Its wave is a little narrower so it fits inside the ring.
- **The favicon leaves out the inner flame.** At 16 px the small navy counter turned into a muddy pixel, so `favicon.vixl` keeps only the disc, flame and wave. The 16/32/64 marks on the sheet do use the full mark.
- **The app icon PNG is RGBA, not RGB.** Every alpha value is 255 (checked: alpha extrema 255–255), so it is fully opaque, but the file still has an alpha channel. Vixl's PNG export kept RGBA even with a navy background and an opaque solid layer, and I didn't convert it outside Vixl. Some app-store checkers reject any alpha channel, so it may need flattening to RGB before submission.

## Things I'm unsure about

- I checked the SVGs only in Inkscape 1.x and in Vixl's own renderer. I didn't test them in a browser. The lockup and mark SVGs use nested `<svg>` and `<g transform>` but no masks.
- In `mark-mono.svg`, the tip of the stroked flame reaches the ring and ends in a slightly squared miter. It reads as the flame touching the rim, but it is less refined than the color mark.
- The flame and wave are recognizable at 16 px, but only just: the flame is about 5 px tall.
- Vixl's text bounds are glyph boxes, so the spacing between wordmark and tagline was set by eye from previews, not measured from baselines.
