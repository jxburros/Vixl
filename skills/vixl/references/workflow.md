# Workflow: start here, one-call builds and the core loop

The full default path and the loop the [skill entry point](../SKILL.md) summarizes. Tests and composition checks are
in [testing](testing.md); exact operation fields in [operations](operations.md).

## Start here (the default path)

For any new piece, and above all an open-ended brief ("make a few cool things"), follow this order
instead of improvising freehand shapes:

1. **What am I making?** `vixl_reference(brief)` (CLI `vixl guide a mascot for a coffee brand`) maps a brief
   to its kind (poster, social card, logo, icon, character, scene, pattern, mandala, diagram, slides …)
   and returns the operations, layouts, looks and styles that suit it, with a working example.
   `vixl_reference("operations")` lists every operation by purpose. Layouts are *text compositions*:
   ten requests for different things are not ten posters. Icons, characters, scenes and patterns are
   built from `shape`, `pen`, `pathfinder`, `organic` and `radial-repeat`; characters are grouped parts
   with a `pivot` at each joint, patterns scatter motifs rather than tile a grid, and animation loops
   are `motion` recipes (`period`, several `targets`, `stagger`). A kind names the guidance to read:
   `vixl_reference("looping-motion")` (or `natural-motion`, `character-rigging`, `imperfection` …)
   returns the text. A brief that implies a setting also returns `motifs`: draw those specific things
   (a cup with steam, a lighthouse standing in filled water), not a disc or a box standing in for them.
2. **Layout** — `vixl_reference('sizes')` → `vixl_document(action='create', size=…)` (or `purpose="social"|"slides"|"logo"…`, which
   picks the size; with neither it is 1080×1080). For anything with text,
   `vixl_reference('layouts')` → `layout-apply`, filling every slot it lists. An unfilled image slot comes back
   with `next_steps` (import, resource, draw, or AI) and its bounds.
3. **Fonts** — creation records the rolled pairing and the first batch with text installs it from the font cache
   or network (`font_install` in that result says so); otherwise, or to choose, `vixl_reference('fonts')` →
   `font-pair` (the bundled font is a proofing fallback).
4. **Finish** — apply a `look` (glow, soft-shadow, hard-shadow, gradient, grain, paper …) so flat shapes
   read as finished work; when the brief names a style (swiss, brutalist, art-deco, kawaii …) use
   `vixl_reference('styles')` and `style-set`, then `check --checks style`. A finish is a look on the surface; it is
   not the *finishing pass* of step 6.
5. **Test** — write the brief's requirements as a check suite before you build ([testing](testing.md)), and run it with
   `vixl_check` while you build: fix the `fix` findings, glance at `review`, accept `informational` ones;
   mark a deliberate edge crop with `layer-intent` `allow_crop`, and deliberately faint text with
   `layer-intent` `waive: [{check: "contrast", reason}]` (waived findings stay listed as informational).
   `vixl_apply(..., check=true, suites=true, preview=true)` returns the findings (the batch's
   layers plus every `fix` and every composition finding), the suite rules that did not pass and a small
   preview with the edit itself, so the loop is one call.
6. **Finishing pass, then export** — passing checks prove the piece is correct, not that it reads as
   designed. Once `vixl_check` and your suite pass:
   1. **Check composition**: `vixl_check(checks=["composition"])` reports dead bands, margin drift,
      uneven rhythm, crowding and clumped scatter as `review` findings. `vixl_apply(workflow='repair-layout')`
      repairs most of them without adding a finding (a dry run by default; see [composition checks](testing.md#composition-checks)).
   2. **Critique** in a few lines against the finishing checklist (`vixl_reference('finishing')`, CLI
      `vixl guide finishing`), naming the layer for each miss.
   3. **Fix** everything the critique found in **one** batch (`check=true, preview=true`), not a string
      of nudges. With `check` the result lists every composition finding and `check.regions`, the two
      weakest regions (the most findings, else the densest text and the largest empty area); with
      `preview` their real-size crops come back after the preview (`preview={regions: 0}` leaves them out).
   4. **Look at real size** at two regions: the crops of step 3 are 1:1. For another place (the focal
      point, a detail) `vixl_render(region=[x, y, w, h], max_width=w, max_height=h)` is 1:1. The
      default preview is reduced; halos, crowding, runts and ragged edges only show at real size.
   5. **Export**: `vixl_check(profile="final")` (it also fails on unresolved review findings, composition
      included), then `vixl_export`.

## One call for a new piece

When you already know the size, layout slots, look and operations,
`vixl_apply(create={…})` (CLI `vixl compose --request req.json --preview p.png`) runs steps 1–5
atomically: nothing is saved or exported unless every step succeeds, and an error carries `step`
(request, create, fonts, layout, style, look, operations, check, preview, save, export). `strict=true` refuses to
save while `check` has `fix` findings; `dry_run=true` builds, checks and previews without writing. Layout `image`/`images`
take workspace paths or https URLs (one-call memes); `background` survives the layout; `style` sets the layout's
alignment and palette and installs its font pairing where you left them open. Keep editing the result with
`vixl_apply`.

## The core loop (do this every time)

0. **Start right** (see *Start here* above: guide → layout → fonts → finish → test → finishing pass) — for a new piece, create it from a named size (`size="instagram-portrait"`,
   `"letter"` with `bleed`, `"favicon"`, `"logo-horizontal"` …) rather than guessed pixels. If the brief
   is open-ended, apply a fitting layout (`layout-apply`) and refine it instead of improvising a
   composition from scratch. Choose a font pairing first (`font pair`), fill every slot the layout
   lists with real copy, and when the brief leaves the look open, roll (`roll`, `seed: "random"`) a few
   times and compare previews. To fill blanks after a first pass, re-apply with the copy,
   `replace: true` and the reported `seed` so the composition stays the same.
1. **Orient** — inspect before editing. MCP: `vixl_document(action='inspect')` returns a compact summary
   (one line per layer with `bounds`; `verbose=true` for every field, `target=` for one layer).
   CLI: `vixl -p F.vixl inspect --json` / `vixl layers`. Note canvas size, layer names/IDs and
   bounds (`[x, y, width, height]` after constraints).
2. **Plan a batch** of canonical operations. Group related edits into one atomic call.
3. **Dry-run anything risky** (`dry_run: true` / `vixl apply ops.json --dry-run`). It returns the
   changes without saving.
4. **Apply.** Read the returned change summary — new layers come back with ID, name, type and
   `bounds`; changed layers list only their new values. If it contains `normalized`, note the
   canonical spelling it reports and use that next time.
5. **Check without looking:** `vixl_check` / `vixl check` reports content cut off by the canvas,
   overlapping text (and decoration running through text, for review), text hidden under a layer stacked above it, low WCAG contrast, safe-area or reserved-zone violations (`safe_area="5%"`,
   `avoid=[[x,y,w,h]]`) and text too small at thumbnail width (on print sizes: below 6 pt). It lists only problems.
   Secondary text too small, light or faint at the size the piece is really seen (cover art at 120 px, a book
   cover at 160 px, a projected slide, a poster across a room) is a `use-size` review finding naming the
   font size or weight it needs; mark ornaments `decorative: true`.
   Then run your own suite (`vixl_apply(workflow='check', request={suite: NAME})`, or `suites=true` on the apply) for
   this brief's requirements; see [testing](testing.md). Fix failures before step 6.
   **Measure, don't eyeball,** when precision matters: `vixl_check(action='measure')` / `vixl info` (colors,
   WCAG contrast of a text layer), `vixl_check(action='spacing')` / `vixl spacing` (gaps),
   `vixl_check(action='validate')` / `vixl validate` (bounds, aspect ratios, assertions).
6. **Finishing pass** (a critique and polish; a *finish* is the look of *Start here* step 4). Run
   `vixl_check(checks=["composition"])` for dead bands, margin drift, uneven rhythm, crowding and clumped
   scatter (workflow `repair-layout` repairs most); write a short critique against the craft checklist
   (`vixl_reference("finishing")`), naming the layer for each miss; then make every fix in one batch with
   `check=true, preview=true`, or `undo` an edit that did not help.
7. **Look at the result, at real size.** MCP: `vixl_render()` returns an image (≤1024 px, ≤1 MiB by
   default, so a large canvas is reduced). The fix batch of step 6 already returned 1:1 crops of the two
   weakest regions (`check.regions`). For any other place, such as the focal point or a detail:
   `region=[x,y,w,h]` with `max_width=w, max_height=h` (a larger max enlarges the region up to 8x);
   `isolate=["mascot"]` shows one object alone, cropped to it.
   `vixl_render(action='compare')` shows previous vs current (also with `isolate`).
   CLI: `vixl render --out /tmp/preview.png` then view the file. Never declare a visual
   task done without looking.
8. **Export** after `vixl_check(profile="final")` passes (it also fails on unresolved review findings):
   `vixl_export` / `vixl export`. Profiles: `draft` fails only on errors, `review` on `fix` findings (as a plain
   check does) and runs every attached suite, `final` also fails on `review` findings and adds the `color_vision` and
   `composition` checks; a workspace `.vixl-checks.json` defines more.
   A `.psd` path writes a layered Photoshop handoff file (one pixel layer per layer, groups kept, text as pixels).
   A `.ttf`, `.otf` or `.woff` path writes the font drawn in the document (`font-design`, `font-grid`,
   `font-glyph`; see [typography](typography.md#making-a-font)).
