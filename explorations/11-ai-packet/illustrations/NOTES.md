# Field notes: AI packet, illustrations and creative designs (Vixl 0.23.0)

Covers both `illustrations/` and `creative/`. Built with the Python API (`from vixl import Project`) plus the
CLI (`vixl roll`, `vixl new`, `vixl workflow logo-package`); the MCP server was not available. Rebuild with

```
python explorations/11-ai-packet/illustrations/build.py     # ~72 s: loop, tokens, poses, network, mascot
python explorations/11-ai-packet/creative/build.py          # ~136 s: rolls, stickers, logo, poster, carousel
```

The creative build links `illustrations/mascot.vixl`, so build illustrations first. Each script takes piece
names (`build.py mascot poses`) to rebuild one piece.

## What was made

| File | What | Main features used |
| --- | --- | --- |
| `illustrations/neural-network.{vixl,png,svg}` | "Inside a neural network", 1920×1200 | 78 cubic `path` weights, `group`, `look glow`, `scatter placement: along` pulses, `scatter` star dust (`merge`), `pixel-art` input cat, `text within`, constraints |
| `illustrations/mascot.{vixl,png,svg}` | Byte, the helper robot (transparent 1080², standalone) | shapes with `stroke_align: inside`, nested groups, `pivot units: canvas`, `look glow` |
| `illustrations/mascot-poses.{vixl,png}` | Three poses of the same rig + speech bubbles | `rotate` on pivots, `reorder` inside a group, `speech-bubble` + `text within`, **`reparent`** (new in 0.23) |
| `illustrations/tokens-tile.{vixl,png,svg}` | Seamless 800² tile of token chips | `pattern-scatter` (group motifs, `pattern` saved), seed search with dry-run/undo |
| `illustrations/tokens-wall.{vixl,png}` | "AI reads in tokens" card over the tiled pattern | `pattern-fill` with the saved pattern, `look hard-shadow`, `arrow` shape |
| `illustrations/training-loop.{vixl,png,svg}` | "The training loop" around a brain made of circuits | `pathfinder` union + subtract (brain + fissure), `radial-repeat` (`merge`), SVG arc paths with `marker_end`, `look soft-halo/glow/hard-shadow`, icon shapes |
| `creative/poster-ai-demystified.{vixl,png,pdf}` | Rolled poster (11×17 in) + hand finishing | `Project.new(purpose=poster)`, `roll_document(apply=True, locks=…)`, house-style tiers, `link` to the mascot |
| `creative/poster-roll-comparison.jpg` | The 10 rolls compared before choosing seed 23 | `roll_document`, same seeds as the CLI |
| `creative/myths-carousel.{vixl,pdf}`, `-1…-5.png`, `-sheet.jpg` | "5 AI myths, busted", instagram-portrait, 5 pages | `master` + `page`, `${page} / ${pages}`, `irregular` hand-drawn strikes, `stamp` shape, `link` (Byte on every page), `check(checks=["deck"])`, contact sheet export |
| `creative/logo.{vixl,png,svg}` + `creative/logo-package/` | "AI Explorers Club" mark + wordmark, full package | `pathfinder subtract` (mono-safe silhouette), `ring`, `star`, `radial-repeat`, strict SVG, `workflow logo-package` |
| `creative/sticker-sheet.{vixl,png}` | Six habit stickers, each a different look | looks `risograph`, `duotone`, `watercolor`, `sketch`, `gradient`, `hand-made`; die-cut shapes; `link` + `layer-style stroke` |

### Byte: layer names and pivots (for the animation builder)

Everything is under one top-level group `byte` (pivot at the feet, canvas point [540, 1010]). Canvas 1080×1080,
transparent. A loose `shadow` ellipse sits under it, outside the group (so jumps can leave it on the floor).

| Group | Parent | Children | Pivot (canvas px) |
| --- | --- | --- | --- |
| `byte` | page | `antenna`, `arm-left`, `arm-right`, `leg-left`, `leg-right`, `neck`, `torso`, `head` | [540, 1010] feet |
| `antenna` | byte | `antenna-stalk`, `antenna-bulb` | [540, 250] base of stalk |
| `head` | byte | `ear-left`, `ear-right`, `head-shell`, `screen`, `screen-glare`, `face` | [540, 560] neck |
| `face` | head | `eyes`, `mouth`, `cheek-left`, `cheek-right` | centre (none set) |
| `eyes` | face | `eye-left`, `eye-right`, `eye-left-shine`, `eye-right-shine` | centre (for blinks: scale-y) |
| `arm-left` / `arm-right` | byte | `upper-arm-*`, `forearm-*` | shoulder [358, 636] / [722, 636]; rest rotation +10 / −10 (stored 350) |
| `forearm-left` / `forearm-right` | arm-* | `lower-arm-*`, `hand-*` | elbow [358, 744] / [722, 744] |
| `leg-left` / `leg-right` | byte | `upper-leg-*`, `shin-*` | hip [468, 850] / [612, 850] |
| `shin-left` / `shin-right` | leg-* | `lower-leg-*`, `foot-*` | knee [468, 916] / [612, 916] |
| `torso` | byte | `torso-shell`, `chest-panel`, `chest-heart` | centre |

Arms are drawn behind the torso; the "thinking" pose shows how to `reorder` an arm above `head` inside `byte`.
`eyes`, `chest-heart` and `antenna-bulb` carry a `glow` look. The rig is NOT bound with the `character`
operation (see the findings: `character` refuses nested parts).

## What worked well

- **Python API + atomic batches** made it easy to write deterministic generators: 78 weighted connections,
  token motifs and the brain circuits are a few loops each, and a failed batch changes nothing.
- **Validation errors are excellent.** E.g. `operations[0] (pen): Unknown field(s) 'opacity' for 'pen'. Allowed: closed, corners, …`;
  `layer-intent: allow_overlap must be array; got bool True`; `opacity value is on a 0–1 scale … got 50. For 50% use 0.5 or the string "50%"`;
  `pattern-scatter: source lists a layer twice`. All named the field and fix; batches report every invalid op at once.
- **`check` caught real mistakes**: missing glyphs in Space Mono (`'tile/…/mchip13-t' uses fallback glyphs` for U+2581 and `↻` in Figtree), low contrast
  (`coral` eyebrow on cream 2.61:1), a transparent helper region (`'dust-area' has no visible pixels`), text outside the Instagram safe area (60 px),
  and, very usefully, my packet swatches overwriting the rolled `@ink`/`@accent` roles on the poster (headline at 1.14:1 after I added
  `swatch ink=#141633` on top of a rolled layout).
- **`text within`** centred numbers in circles, labels in speech bubbles and stamp text with no maths.
- **`pattern-scatter`** with group motifs (chip + text) produced a genuinely seamless tile (`seam: {seamless: true, edge_error: 0.483,
  interior_variation: 1.112}`); `pattern-fill` with the saved pattern filled a wall correctly. Re-applying in a loop with `p.undo(1)`
  made a seed search possible.
- **`scatter placement: along`** with a `mark` put signal pulses along the highlighted curves in one op.
- **`pathfinder`** union/subtract is solid: an 8-lobe brain with a subtracted fissure, and a logo silhouette with holes; both export as
  real compound paths (strict SVG passed).
- **`link` layers** are great for a packet: Byte is drawn once in `illustrations/mascot.vixl` and appears live in the poster, all 5
  carousel pages and the sticker sheet, including in the PDFs.
- **Masters, pages and `${page} / ${pages}`** worked first time; `check(checks=["deck"])` ran across all pages; the vector PDF looks right.
- **`logo-package`** is impressive: 104 files in 12–27 s (SVG strict, PDF, PNG 1x/2x/3x, favicon set + manifest, avatar, OG image,
  lockups built from `mark` + `wordmark`). The mono variants exposed a real design flaw in my first mark (all detail separated only by
  colour, so mono-black was a solid disc), exactly as the docs warn; rebuilding the mark as one silhouette with holes fixed every variant.
- **SVG export fidelity**: the network, mascot, loop and tile SVGs re-rendered with resvg match the PNGs, with zero `<image>` elements
  (even the `pixel-art` cat is vector).
- **0.23 looks**: `watercolor` on a flat lilac heart gives a convincing blotchy wash with a darker rim; `sketch` draws a graphite outline and
  hatching; `hand-made` adds a pleasant wobble. `irregular strength: natural` on pen strokes made convincing hand-drawn strike-throughs.
- **Rolls are reproducible across surfaces**: `roll_document(Project.new(...), seed=S, …)` in Python gave exactly the CLI's
  `vixl new … --seed S` + `vixl roll --apply --seed S` directions for all 10 seeds.
- **House-style purpose defaults**: `Project.new("logo-horizontal", purpose="logo")` gave a transparent canvas (`creation.background_from: mark`);
  `vixl new --purpose poster` chose poster-18x24 and installed the rolled pairing in 1.8 s.

## Bugs and wrong results (with repros)

1. **A group clips its children's strokes to the children's geometric boxes.** A stroked path lying on the edge of its own box loses the
   outer half of its stroke once grouped.
   ```python
   p = Project(400, 200, background="#fff")
   p.apply([{"type":"shape","shape":"path","name":"a","path":"M20 60 L380 60","stroke":"#e11","stroke_width":20},
            {"type":"shape","shape":"path","name":"b","path":"M20 140 L380 140","stroke":"#11e","stroke_width":20},
            {"type":"group","name":"g","targets":["b"]}])
   # 'a' renders 20 px thick, 'b' 10 px (bottom half cut at y=140). check() reports nothing.
   ```
   In the network the highlighted horizontal weight rendered at about a third of its width. Workaround: give paths a padded box, or
   `stroke_align: inside` on outlined shapes (used for the whole mascot).
2. **`scale` ignores the pivot** (shapes and groups): it shrinks towards the box's top-left although `pivot` is documented as "the point
   that rotation and scale turn about".
   ```python
   p.apply([{"type":"shape","shape":"rectangle","name":"a","x":100,"y":100,"width":200,"height":200,"fill":"#e11"},
            {"type":"pivot","target":"a","value":"bottom"},{"type":"scale","target":"a","value":0.5}])
   # ink bbox (100,100)-(199,199); expected (150,200)-(249,299). Same for a group with units: canvas.
   ```
   Workaround: `scale_about()` in `illustrations/build.py` (inspect, scale, then relative `move`).
3. **Rotation without an explicit pivot does not turn about the centre.** `rotate` (and `rotation` on creation or on a `shape` edit) keeps
   the top-left of the *expanded* bounds at the layer's x/y, so the layer drifts down-right.
   ```python
   p.apply([{"type":"shape","shape":"rectangle","name":"a","x":100,"y":150,"width":200,"height":100,"fill":"#000"},
            {"type":"rotate","target":"a","value":45}])
   # ink centre (206, 256); with {"type":"pivot","target":"a","value":"center"} first it is (199, 199).
   ```
   The docs say "Degrees clockwise about the layer's pivot (default: center)". My first logo's 45° back-needle star was shifted off-centre
   by this. Workaround: always set `pivot: center` before rotating (done for the stickers).
4. **`halftone` look ignores `color` and the fill**: always black dots on white. `{"type":"look","target":"e","look":"halftone","color":"#ff6b5b"}`
   on a `#ffd166` ellipse stores `color` in `looks.halftone` but renders black/white; a teal fill renders the same. On the sticker sheet it
   turned a night-blue seal into a black-and-white dot field and the text failed contrast (1.45:1). Replaced with `gradient`.
5. **`marker_size` is silently invisible at small values.** With `stroke_width: 10`, `marker_size: 3.2` (which I read as a multiple of the
   stroke) draws no arrowhead at all, `1`/`2`/`5` likewise, `20` a small head; the default is about 4× the stroke. The schema says only
   "Marker size." with no unit, and no warning is given. Separately, the stroke runs on past the arrow tip by about half the head length.
6. **Rolled "large" headlines break words mid-word with no hyphen, and `check` passes.** All 10 rolls of "AI, demystified" on poster-11x17
   (seeds 11–16 medium/high, 21–24 high + `mode=dark`) except the condensed League Gothic one rendered `demysti / fied`, `demystifi / ed`,
   `demyst / ified` or `de / mysti / fied` (see `creative/poster-roll-comparison.jpg`). Every one returned `check` with zero `fix` findings.
   `--lock headline=measured` avoids it but leaves the headline small with ~40% of the poster empty.
7. **False positive: a look on a group that contains text makes `check` measure that text at 1.00:1.**
   ```python
   p = Project(800, 400, background="#fff6e5")
   p.apply([{"type":"shape","shape":"stamp","name":"stamp","x":72,"y":100,"width":330,"height":112,"fill":"#c2362a"},
            {"type":"text","name":"t","text":"BUSTED","within":"stamp","size":52,"color":"#fff6e5"},
            {"type":"group","name":"g","targets":["stamp","t"]},
            {"type":"look","target":"g","look":"hard-shadow","color":"#141633","amount":0.3}])
   p.check()  # contrast 'fix': "'t' contrast is 1.00:1 or lower …"; without the look: no finding
   ```
   Workaround: apply the look to the shape, not the group.
8. **`character` cannot bind a rig that uses nested groups.** Binding Byte's parts (`torso`, `head`, `eye-left` …) with
   `{"type":"character","parts":{…}}` fails with only `Layers must share a parent` (no layer named). The guide recommends
   "group parts into joints … set a pivot at each joint", which is exactly what makes `character` refuse them. So Byte stays a plain
   group/pivot rig, not a `character` (no `character-cycle`).
9. **`pattern-scatter` ghosts: unsuppressible `check` fixes.** Wrapped copies that fall entirely outside the tile produce
   `fix contrast Could not measure the contrast of 'tile/31/mchip0-t': Target has no visible content` (and, before I set it, `fix bounds … is entirely
   outside the canvas`). `layer-intent allow_crop: true, role: decoration` on the tile group silenced the bounds finding but not the contrast one.
   The apply result also warns `'tile/25/chip1-t' is entirely outside the canvas` for every ghost text. These copies are the whole point of a seamless tile.
10. **Slow first render from canvas-sized path boxes.** A path given in canvas coordinates with no x/y/width/height gets a box from (0, 0) to its
    farthest point. With 78 such layers the first render took **21–23 s** (second render 1.2 s). cProfile: 12.6 s in `render.warp` +
    6.8 s in `render.antiring` (the boxes had fractional sizes like 591.67) and 6.4 s in resvg. Giving each path a tight integer box
    (`path_layer()` in the build script) brought the whole network export to ~2 s. Nothing warns about it.
11. **`reparent keep: appearance` is not pixel-exact.** Reparenting a speech-bubble group into a scaled (0.7) `b-byte` group changed 5,291 pixels
    (summed RGB diff > 30), mostly a 1 px shift along the bubble's top edge and antialiasing on Byte. Visually fine, but not "stays where drawn"
    to the pixel. The sheet's export time also went from ~6 s to ~12 s after the reparent.
12. **`overlap` does not seem to consider `link` layers**: Byte (a link) overlapped the tip box and its text on carousel slides 1–2 and the
    check reported no overlap (only `review safe_area 'byte'`). I caught it in the preview.
13. **`risograph` look lightens and greys a coral fill** (`#ff6b5b` became a grainy salmon pink) so cream text on it dropped to 1.70:1; the changelog
    says flat coral now keeps its colour. `duotone` on a flat teal shield had almost no visible effect.

## Confusing or poorly documented

- **Python `export(pages="all")` fails**: `Page 'all' does not exist. Pages: myth-1, …`. The docs say `export slide.png --pages all writes numbered files`,
  which is CLI-only; in Python you loop `export(path, page=NAME)`. `export(..., sheet=True)` is a `TypeError`; the contact sheet is `page="all"`.
- **Contact-sheet `width` is per thumbnail**, not the sheet width. `export(..., page="all", columns=5, width=2000)` made an 8096×2056 sheet (2.4 MB PNG).
- **SKILL.md and the operations reference disagree on opacity**: SKILL.md says "values from 1 to 100 are read as a percentage", but
  `opacity value: 50` is an error (the reference and the error message are right).
- **`pen` has no `opacity`** while `shape` does (`Unknown field(s) 'opacity' for 'pen'`).
- **numpy integers are rejected as "Operations must contain finite JSON values"**: they are finite; the message sent me looking for NaNs.
- **`motif` collides with the frame**: the rolled `direction-motif` (a small dash at the top right) pokes through the `accent` frame on the
  wide-statement / acid-violet roll and shows as a stray tick on several others (seeds 12, 14, 22). I removed it.
- **Rolled layouts sit low**: with `headline=measured`, seed 23 left ~1000 px of empty frame above the label; I moved the copy up 620 px.
- **`roll` needs a filled `subtitle/body/label/cta` set to look like anything**: every poster roll was a text column (no image slot, no art); the
  house style's purpose weighting gives typographic variety, but ten rolls looked like ten versions of one layout family. Expected (layouts
  are text compositions) but worth stating: the poster needed the network + mascot added by hand.
- **`within` text and `\n`**: worked, but there is no letter-spacing on plain text, so the logo's "C L U B" uses literal spaces.
- **`logo-package` `usage.html` is 2.8 MB** (42 embedded PNGs, ~70 KB each), more than every other file in the package together; the per-variant
  `.vixl` sources were another 3.7 MB (each embeds the fonts, ~240 KB). I turned the proof off and dropped `source/` and `@3x` to keep this repo small.

## Features looked at but not used

- **`character` / `character-cycle`**: wanted it for Byte, refused (finding 8).
- **`vixl compose`**: used `roll_document` + edits instead because I wanted to compare seeds before committing and then hand-finish; compose is
  one-shot.
- **`organic`**: considered for the brain; the 18 generators are plants and creatures, so `pathfinder` over ellipses was more direct.
- **`irregular` on the mascot**: the guide suggests subtle wobble on body parts; I kept Byte clean so the animation builder gets crisp,
  predictable outlines (irregular converts shapes to paths).
- **`tear`, `cut-paper`, `drawn-texture`**: not needed for this packet.
- **`halftone`**: tried, dropped (finding 4).

## Timings (this container)

| Step | Time |
| --- | --- |
| `vixl new --purpose poster` (download + embed pairing) | 1.8 s |
| `vixl roll --apply` on poster-11x17 | 7–18 s per seed (avg ~10 s); `check` after it 5–11 s; seed 16 (light-paper look) render 19.5 s, check 27 s |
| Network first render with canvas-box paths | 21–23 s (fixed to ~2 s with tight boxes) |
| Token tile seed search (30 dry runs) | 28 s (64 s when I called `inspect()` per group) |
| `logo-package` workflow | 12–27 s for 104 files |
| Full `illustrations/build.py` | ~72 s |
| Full `creative/build.py` | ~136 s (of which the 10-roll comparison is ~93 s) |

## Accuracy notes on the content

All numbers on the pieces are labelled illustrative (network output scores, token split). The myths/truths avoid statistics: "AI can
confidently make things up … most with facts, numbers, quotes and sources", "AI learns from human-made data, and that data carries our
gaps and biases", etc. The network footnote says "Real networks have thousands to billions of weights", which is a safe range.
