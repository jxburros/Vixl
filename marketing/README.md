# Vixl marketing pack

**Ideas become editable.** A programmable design studio for AI agents.

Ready-to-use graphics, documents and motion, authored with Vixl. The materials are also working
examples: edit the chart's data in PowerPoint, type into the creative brief, generate campaign
variants from a recipe, or try the animation family's states and themes. Every design includes
an editable `.vixl` master with embedded fonts and content.

![Vixl marketing pack](output/kit-overview.png)

## Choose a piece

| Use | Ready-to-use files | What the piece demonstrates |
| --- | --- | --- |
| Link previews | [Open Graph card, 1200 × 630](output/social/og-card-1200x630.png) | Rich type, syntax-colored text, vector branding |
| Repository sharing | [GitHub preview, 1280 × 640](output/social/github-preview-1280x640.png) | Framed Vixl artwork, editable clipping |
| Profile branding | [LinkedIn banner, 1584 × 396](output/social/linkedin-banner-1584x396.png) | Brand geometry; left area reserved for a profile image |
| Vertical social | [Story, 1080 × 1920](output/social/story-1080x1920.png) | Image composition; top/bottom 250 px reserved for platform UI |
| Product introduction | [Six-slide carousel PDF](output/carousel/carousel-1080x1350.pdf) · [PNG slides](output/carousel/) · [Contact sheet](output/carousel/contact-sheet.png) | Pages, shared master and phone-profile checks |
| Product presentation | [12-slide PDF](output/deck/vixl-pitch-deck.pdf) · [Editable PPTX](output/deck/vixl-pitch-deck.pptx) · [HTML presenter](output/deck/vixl-pitch-deck.html) | Speaker notes, native chart with embedded data, screen-profile checks |
| Product handout | [US Letter product sheet](output/print/one-pager-letter.pdf) | Vector PDF, typography and feature summaries |
| Creative intake | [Fillable US Letter brief](output/print/creative-brief-letter.pdf) | Five text fields and a checkbox, accessible labels and tab order |
| Event signage | [Tabloid CMYK poster](output/print/poster-tabloid.pdf) · [Preview](output/print/poster-tabloid.png) | 11 × 17 in trim, bleed, TrimBox/BleedBox and a vector QR code |
| Event giveaway | [US Letter sticker handout](output/print/sticker-sheet-letter.pdf) | Editable vector marks and type; cut around the tiles |
| Social campaign | [Three square posts](output/campaign/) · [Contact sheet](output/campaign/contact-sheet.png) | Typed recipe, variables, fitting, saved suites and production batches |
| Feature overview | [Capability map PDF](output/showcase/capability-map.pdf) · [PNG](output/showcase/capability-map.png) · [SVG](output/showcase/capability-map.svg) | A vector infographic you can edit and reuse |
| Data storytelling | [Chart PPTX](output/showcase/editable-chart.pptx) · [PNG](output/showcase/editable-chart.png) · [SVG](output/showcase/editable-chart.svg) | Data-bound chart; PPTX's Edit Data opens its native workbook |
| Agent workflow | [Workflow PDF](output/showcase/agent-workflow.pdf) · [SVG](output/showcase/agent-workflow.svg) | Automatically routed diagram, editable shapes, paths and labels |
| Motion post | [6.6-second MP4](output/motion/teaser.mp4) · [GIF](output/motion/teaser.gif) · [Still alternative](output/motion/teaser-frame.png) | Editable keyframes and a sampled motion suite; silent, play once |
| App integration | [Animation family](output/app/package/index.html) · [Manifest](output/app/package/manifest.json) | Three states, light/dark themes, transitions, editable masters and reduced-motion PNGs |
| Publishing copy | [Plain text](output/copy/marketing-copy.txt) · [JSON](output/copy/marketing-copy.json) | Descriptions, captions, alt text, licensing and a three-minute demo script |
| Review | [Offline proof page](output/proof.html) | Vixl-generated previews with zoom and local decision download |

Download HTML files before opening them in a browser; GitHub displays their source. The proof page
embeds its previews and works offline. Keep the app package directory together: its HTML consumer
loads adjacent assets. Use **create → deliver → reset**, switch the theme, or enable your OS reduced-motion
preference. The pack supplies working artwork and a demo consumer; the host app owns its integration.

## Rebuild and verify

From the repository root with Python 3.11+:

```bash
python -m pip install -e '.[dev,server,pdf]'
python marketing/build.py
python marketing/verify.py
```

MP4 export and verification need `ffmpeg` and `ffprobe`. The first build downloads Inter Tight 800,
Inter 400/600 and JetBrains Mono 500 through Vixl's font installer; subsequent builds use its cache.
Fonts are embedded in the masters, so viewing and editing delivered files needs no font download.
Font licence notices are included in `output/licenses/`.

Build selected pieces by name; dependencies are rebuilt automatically:

```bash
python marketing/build.py og github deck
python marketing/build.py brief campaign app
```

Available names: `showcase`, `campaign`, `og`, `github`, `linkedin`, `story`, `carousel`, `poster`,
`onepager`, `brief`, `stickers`, `deck`, `app`, `teaser`, `copy`, `overview`, `proof`.
Run the complete build for a cohesive pack and its full proof page. The builder replaces only its
own generated outputs; put edited copies outside `marketing/output/` before rebuilding. `verify.py`
checks the complete delivered pack, rather than a selected-piece build.

The script is the visual source; [`posts.csv`](posts.csv) supplies the campaign's rows and
[`copy.json`](copy.json) supplies publishing copy. Public
materials describe the product directly, without release labels or comparisons to previous versions.
Registry counts are measured from the installed engine and recorded as build metadata in
[`output/manifest.json`](output/manifest.json); they are not used as headline claims.

## Try the working examples

- **Chart:** open the deck or chart PPTX and use **Edit Data**. The workflow numbers are illustrative,
  not customer metrics or performance results. In a `.vixl` master, use `chart-data` to revise the data.
- **Brief:** open the PDF in a viewer supporting AcroForms, tab through the fields, and save a filled
  copy. The `.vixl` master keeps the fields, layout and labels editable.
- **Campaign:** inspect [`posts.csv`](output/campaign/posts.csv), the typed
  [`campaign-recipe.vixl`](output/campaign/campaign-recipe.vixl), and
  [`production.json`](output/campaign/production.json). Change rows and run production into a **new**
  directory. The supplied rendered posts were generated with Vixl's checked production API.

  ```bash
  vixl -p marketing/output/campaign/campaign-recipe.vixl workflow run \
    --request marketing/output/campaign/production.json --workspace .
  ```

- **Git review:** [`campaign/source/project.json`](output/campaign/source/project.json) is the recipe's
  readable current-state snapshot, with hashed assets and registered fonts. Repack it with:

  ```bash
  vixl pack marketing/output/campaign/source campaign-custom.vixl
  ```

- **Motion:** the teaser master has a play-once timeline; the app package uses looping states with
  explicit theme variables and reduced-motion PNGs. See [app animation packages](../docs/animation-authoring.md#app-animation-packages).

## Craft, checks and provenance

The [Digital Shift identity](../assets/brand/digital-shift/START-HERE.md) supplies the palette and
outlined logo geometry. The builder imports the brand SVGs as editable vector shapes, preserving
proportions and internal spacing. It frames real Vixl outputs from `explorations/` and creates the
chart, diagram and campaign directly through Vixl's Python API. No AI provider is used in the build.

Each master has saved suites. Every release export is gated on the selected Vixl checks having
**zero `fix` findings** and every attached suite passing. Reports sit alongside the masters as
`.check.json`; the motion reports state their sampling coverage. Informational edge-cropped glows
are intentional. Checks establish their selected rules; the exported previews also need visual review.
The proof page is for visual review, while the per-piece reports carry the build's check results.

`verify.py` also checks file hashes, portable masters, the source-folder render roundtrip, PDF fields
and print boxes, native PPTX chart data and speaker notes, app variants, and video dimensions/duration.
Supported vectors and text stay editable; showcase photographs/artwork remain embedded raster images.
Format-specific fallbacks follow [Vixl's export behavior](../docs/exporting.md).

The poster uses device-naive CMYK conversion at export; it is not a colour-managed press proof.
Ask the printer for the required ICC profile and export with it for production. Sticker outlines are
visual cut guides, not a spot-colour die-cut separation.

Vixl is source-available under [PolyForm Small Business 1.0.0](../LICENSE). See the licence for eligibility
and required notices. Bundled fonts retain their own terms in `output/licenses/`. Please credit work
made with Vixl. AI generation and vision are optional provider-backed capabilities; core authoring,
checks and rendering run locally.
