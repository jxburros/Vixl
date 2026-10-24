# Objects

[Documentation home](../../README.md) · [Design tools](design-tools.md) · [Organic shapes](organic.md) · [Operation semantics](../../reference/operations.md)

A dog, a guitar or a person is drawn from many shapes, but it is one thing. An **object** is a group that
says so: it has a **kind** from the taxonomy, its layers can be named as **parts** (head, leg, neck), and an
object inside another object's group is a **sub-object** (a person holding a guitar). Vixl uses this to
address parts by path, review an object on its own, export it alone, reuse it as an editable copy, and keep
its identity in SVG, PowerPoint and PSD files.

## Concepts

| Term | Meaning |
| --- | --- |
| Domain › class › kind | The taxonomy: `organic › animal › mammal › dog`, `constructed › instrument › guitar`. A kind inherits every field from its parent. |
| Object | A group with `object: {kind, label?, notes?, references?}`, plus its [outline policy](#outline-policy) once one is applied. A standard character is a `person` without a record of its own: its `character_part` names read as person parts. |
| Part | A layer inside the object with `object_part: {name, side?, depth?}`, such as `{name: leg, side: left}`. |
| Sub-object | An object nested inside another object's group. Its parts belong to it, not to the outer object. |
| Path | `dog/head`, `dog/leg[left]`, `person/guitar/neck`: wherever a layer name is accepted. |

## The taxonomy

`vixl objects` searches the kinds, `vixl objects show dog` prints one with everything it inherits, and
`vixl objects tree` prints the tree. Over MCP the same data comes from
`vixl_reference('objects', name="dog")`, `vixl_reference('capabilities', name="objects")` (which includes the tree),
and `vixl_reference("dog")`, which resolves a kind from a brief such as "a friendly dog sitting".

```bash
vixl objects show puppy        # aliases resolve: puppy → dog, acoustic guitar → guitar
vixl objects tree
```

Each entry has `summary`, `aliases`, `parts` (`name`, `required`, `count`, `side`, `sub_object`),
`connections` (pairs of parts that must touch), `proportions` (a part's size against the object's height or
another part), `symmetry`, `layering` (back-to-front order hints), `outline` (the default outline policy) and
`build` (how to construct one, [below](#build-an-object)). `parts+` and `connections+` extend what the parent
defines; `build` merges field by field; every other field replaces it. The domains are
`organic` (people, animals, plants, fungi), `constructed` (instruments, vehicles, buildings, furniture, tools,
devices, containers), `natural` (rocks, clouds, water, mountains), `symbolic` (icons, badges, emblems) and
`texture` (fur, spots, scales, cells: surface patterns to apply to parts, not objects). Every
[organic preset](organic.md#presets-and-their-kinds) maps to a kind.

### Your own kinds

Add a kind (a brand mascot, a product) to the user library or, with a workspace, to its
`.vixl-resources.json`. It must name a parent and is checked against the same rules (known parent, no cycle,
no alias that another kind already uses):

```json
{"parent": "mascot-figure", "aliases": ["bean"], "summary": "The coffee-bean mascot",
 "parts+": [{"name": "antenna", "count": 2, "side": true}], "connections+": [["antenna", "head"]]}
```

That value goes to `vixl_apply(workflow='resource-save', request={kind: "objects", name: "coffee-bean", value: …})`.

## Build an object

The loop is: reference → object-plan → refine → outline → check.

1. **Reference.** `vixl_reference("guitar")` (or `vixl_reference('objects', name="guitar")`, `vixl objects show
   guitar`) returns the kind with its merged `build` block: how to draw one, and an `example` batch to adapt.
2. **Plan.** `vixl_apply(workflow='object-plan', request={kind: "guitar", height: 400, apply: true})` (CLI `vixl
   object plan guitar --height 400 --apply`) scaffolds the whole object as named placeholder parts, grouped and
   declared, that already pass the object check ([below](#scaffold-with-object-plan)).
3. **Refine.** Turn each placeholder into the part it stands for: edit it in place (`{type: shape, target:
   guitar-neck, …}`, a path, an organic preset) or draw the part and name it, keeping the overlaps.
4. **Outline.** `{type: object, action: outline, target: guitar}` applies the kind's [outline
   policy](#outline-policy): one outline around the silhouette, thin lines inside.
5. **Check.** `vixl_check` runs the [object check](#the-object-check); preview the object alone with
   `vixl_render(isolate=["guitar"], views=["parts"])`.

```bash
vixl new 600x500 -o guitar.vixl
vixl object plan guitar --height 400 --apply
vixl object outline guitar
vixl check --checks object
```

Drawing it yourself instead: draw each part as its own layer (shape, pen, organic, pathfinder) in the order the
kind's `layering` gives, letting parts that meet overlap by a few pixels; group them, declare the group and name
the parts. The `object` result's `next_steps` points back to the build block.

```json
[
  {"type": "shape", "shape": "capsule", "name": "leg-1", "x": 118, "y": 176, "width": 18, "height": 60, "fill": "#743"},
  {"type": "shape", "shape": "capsule", "name": "leg-2", "x": 214, "y": 176, "width": 18, "height": 60, "fill": "#743"},
  {"type": "shape", "shape": "ellipse", "name": "dog-body", "x": 100, "y": 120, "width": 160, "height": 80, "fill": "#a65"},
  {"type": "shape", "shape": "capsule", "name": "leg-3", "x": 136, "y": 176, "width": 18, "height": 62, "fill": "#a65"},
  {"type": "shape", "shape": "capsule", "name": "leg-4", "x": 232, "y": 176, "width": 18, "height": 62, "fill": "#a65"},
  {"type": "shape", "shape": "ellipse", "name": "dog-head", "x": 230, "y": 80, "width": 70, "height": 70, "fill": "#a65"},
  {"type": "group", "name": "dog", "targets": ["leg-1", "leg-2", "dog-body", "leg-3", "leg-4", "dog-head"]},
  {"type": "object", "target": "dog", "kind": "dog", "label": "Rex"},
  {"type": "object", "action": "part", "targets": ["dog-head"], "part": "head"},
  {"type": "object", "action": "part", "target": "dog-body", "part": "body"},
  {"type": "object", "action": "part", "targets": ["dog/leg-1", "leg-2"], "part": "leg", "depth": "far"},
  {"type": "object", "action": "part", "targets": ["leg-3", "leg-4"], "part": "leg", "depth": "near"}
]
```

`object` actions: `set` (the default: declare or update `kind`, `label`, `notes`, `references`, `stylized`,
`proportions`), `part` (`part`, `side`, `depth`, and the part's own `outline` and `interior`), `outline` and
`outline-remove` ([outline policy](#outline-policy)), and `unset` (drop the record and the object's direct part
names; an applied outline is removed first).
`side` (`left`, `right`, `center`) names a mirrored pair in a front view; `depth` (`far`, `near`) names limbs
behind or in front of the body in a side view. `stylized: true` says the proportions are exaggerated on purpose
(a mascot's big head) and `proportions: "ignore"` says the kind's ranges do not apply: either silences the
check's proportion findings. A part name outside the kind's list is kept with a warning that suggests the
closest name. `subject` is accepted for `object`, `object_kind` for `kind`, `name` for `label` and `stylised` for
`stylized`. The CLI spells it `vixl object dog --kind dog [--stylized] [--proportions ignore]`,
`vixl object part leg-1 --part leg --side left [--depth far]`, `vixl object outline dog [--outline parts]` and
`vixl object plan dog --height 300 [--apply]`.

A declared object stays one item: `move`, `scale`, `rotate`, `align`, `distribute`, `duplicate` and `remove`
act on the group as for any group; `duplicate` copies the records with the subtree. `ungroup` refuses an
object (its identity would be lost) until `{type: object, action: unset}` or `force: true`.

### The build block

A kind's `build` block says how to construct one. Each level of the taxonomy contributes: `organic` and
`constructed` give the general approach, `animal` and `mammal` the shapes and leg placements, `dog` the snout
and ears and a working example. Lists merge down the chain with the child's items first and duplicates dropped
(a kind's placement for a part replaces its parent's); `palette` and `example` are replaced.

| Field | What it holds |
| --- | --- |
| `approach` | Construction steps, most specific first. |
| `workflows`, `operations` | Workflow actions (`object-plan`) and operations that build it. |
| `organic`, `shapes`, `patterns` | Organic presets, catalog shapes, and pattern operations such as `{op: scatter, preset: fur}`. |
| `looks`, `palette` | Finishing looks, and a palette name or `natural:SUBJECT` (skin, foliage, sky, earth, water, stone). |
| `placements` | Where each part goes (below). |
| `guidance`, `checks` | Guidance texts to read (`vixl_reference(NAME)`) and the checks to run. |
| `research` | Short offline notes (`{title, notes, url?}`): proportions, telling features, common mistakes. |
| `example` | A batch of 6 to 20 operations that draws the object, groups it, declares it and names its parts. |

A placement is `{part, anchor: "PART.ANCHOR", at?, spread?: "a-b", side?, mirror?, note?}`: the part attaches
at the anchor point of another part's box (or of `object`, the whole object), using the anchor names of `align`
(`top-left`, `top`, `top-right`, `left`, `center`, `right`, `bottom-left`, `bottom`, `bottom-right`; synonyms such
as `bottom-center` read as `bottom`). `at` names the point of the part that sits there (default: the opposite
anchor, so a leg at `body.bottom` hangs from its top). `spread` spaces several instances along the anchor's edge
from fraction `a` to `b` (along the width for top, bottom, centre and corners, along the height for left and
right); `side` limits a placement to one side, and `mirror: true` applies it mirrored to the other. Placements
inherited from a class apply only to parts the kind has. Animals and vehicles are placed facing right in a side
view, people and buildings in a front view.

```json
{"part": "leg", "anchor": "body.bottom", "at": "top", "spread": "0.15-0.85"}
```

The 15 seed kinds have a block with an example that passes the object check: person, dog, cat, bird, fish,
tree, flower, leaf, mushroom, guitar, car, house, cup, rock and cloud. Every domain except `texture` has a
general block, so every other kind gets at least an approach; a workspace kind may add its own `build` (the
names it uses must exist).

### Scaffold with object-plan

The `object-plan` workflow turns a kind's build block into one batch of ordinary operations: a placeholder
shape per part, then `group`, `object` and one `object` `action: part` per part and side.

```json
{"kind": "dog", "height": 300, "x": 40, "y": 60, "apply": false}
```

- **Parts.** With a build `example`, the parts it draws, with their shapes, boxes, rotations, colours, sides and
  depths; otherwise every required part and every part the placements place, `count` of each. A side view shows
  one of an optional pair (the far eye is hidden) and a pair of limbs as a far and a near one.
- **Positions** come from the `placements`: the part's `at` point on the anchor point of the part it attaches to,
  several spread along the edge, a far limb half its width behind the near one, a radial kind's petals in a ring.
  Each part is then pushed toward what it attaches to until they overlap by 2 px, and every pair the kind says
  must touch is checked again, so the scaffold passes the object check as generated (every seed kind does, and so
  does every kind that lists parts).
- **Proportions**: a part the kind's `proportions` measure is sized at the middle of its range; `seed` picks a
  value inside the range instead and varies the other parts by up to 8%.
- **Order**: back to front as the example draws them, else by the kind's `layering`.
- **Size and place**: `height` with `x`/`y`, or `box: [x, y, width, height]` to fit inside; with neither, the
  object fits a centred box of 80% of the canvas width and 60% of its height (400 px at the origin without a
  document). Layer names are `NAME-PART` (`dog-leg-1-far`), made unique in the document.
- **View**: animals and vehicles are side views facing right, everything else a front view; `view` names the
  kind's own and refuses another.
- **People** come from head units: `head_units` (default 7.5, or the middle of the kind's head proportion) and
  `width_ratio` place all 17 standard parts; a head outside the kind's range declares the object `stylized`.
  `template: "figure-plan"` returns the seven-mass blocking figure instead; the `figure-plan` workflow is that
  template and says so under `normalized`.
- **Sub-objects**: `with: ["guitar"]` (or `{kind, name?, height?, anchor?, at?}`: `anchor` is a point of one of
  the object's parts such as `torso.center`, default `object.center`; `height` defaults to half the object's)
  plans each one the same way and nests it in front of the parts.
- **Result**: `apply: false` (the default) returns `operations`, `parts` (layer names by part), `box`, `view` and
  `next_steps` (the approach, one step per part naming its placeholder and placement, then outline and check) and
  changes nothing; `apply: true` applies the batch as one undo step.

Placeholders read as the kind's silhouette, not as finished art: refine them. A kind without an example or
placements (most classes outside the 15 seeds) gets a rough arrangement of its parts around the part with the
most connections.

## Outline policy

Whether an object has one outline around its silhouette, a line around every part or none is its **outline
policy**, `{type: object, action: outline, target: NAME, outline, interior, outline_color, outline_width}`:

| `outline` | What is drawn |
| --- | --- |
| `silhouette` | One `NAME/outline` path layer, the object's top child, around the union of what its layers fill (sub-objects included), holes kept. Part strokes follow `interior`: `hide`, `thin` (40% of the outline width) or `show` (as wide). |
| `parts` | No outline layer: every part's stroke is the outline colour and width. |
| `none` | Nothing: the part strokes the policy replaced come back. |
| `inherit` | The default: the kind's policy from the taxonomy's `outline` entry. Organic and constructed kinds are `silhouette` with `thin` interior lines, symbolic ones `silhouette` with `show`, natural ones `none` (`vixl_reference('objects', name=KIND)` lists it as `outline_policy`). |

```json
{"type": "object", "action": "outline", "target": "dog", "outline": "silhouette", "interior": "thin", "outline_width": 4}
```

- `outline_color` defaults to `#1d1d24` and `outline_width` to 1% of the object's larger side; the line scales with
  the object. The outline layer is marked `generated: {by: object-outline}` and drawn as an unfilled stroke in PNG,
  SVG, PDF and PowerPoint alike.
- The original part strokes are stored on the object record (`outlined`); `action: outline-remove` (or `outline:
  none`, or `unset`) puts them back and deletes the outline layer. Running `outline` again replaces the policy.
- Open lines and unfilled shapes (whiskers, strings, an open path: anything `geometry.default_fill` leaves
  unfilled) are line work: they add no area to the silhouette and keep their strokes. A pathfinder part has no
  stroke of its own; only the silhouette outlines it.
- Per part: `{type: object, action: part, target: LAYER, part: steam, outline: none}` leaves a part out (no
  silhouette, its own stroke), `outline: parts` gives it a full contour of its own, and `interior` sets its own
  interior.
- The outline follows the object: when a part moves, changes size or shape, or a part is added or removed, the
  apply that did it redraws the outline and gives new parts the policy's strokes, in the same undo step. While a
  policy is applied it owns the part strokes; a part styled by hand keeps its stroke only with `outline: none`.

The object check adds three findings for an object with an applied policy: `object.outline-seam` (a part stroke
that shows inside the silhouette where the policy hides it, or as heavy as the contour where it thins it),
`object.outline-weight` (part outlines whose widths differ by more than 25% under `parts`) and
`object.outline-stale` (the outline was drawn for other geometry, or its layer was deleted: run `outline` again).

## Paths and selectors

Paths resolve by the object's name or label, then each segment by part name (with `[left]`, `[right]` or
`[center]`), sub-object label or kind, or layer name, at any depth below. A path that names several layers
(`dog/leg` with four legs) is an error that lists them, and an unknown segment suggests the closest one.
`isolate` lists accept every match of a path and `object:KIND`, which names every object of that kind or a kind
below it (`object:animal` matches dogs and cats).

`edit-layers` selects with `where.object` (an object and its subtree), `where.object_kind` (objects of a kind
or below it, with their subtrees) and `where.part`:

```json
{"type": "edit-layers", "where": {"object_kind": "animal", "part": "leg"}, "do": {"type": "opacity", "value": 0.8}}
```

## Inspect, review and measure one object

- `vixl_document(action='inspect', object="dog")` (CLI `vixl inspect --object dog`) returns the kind chain, bounds in
  canvas and group space, each part with its side, path, bounds and layer count, the **required parts still
  missing**, layers that are not named as parts, notes, references and sub-objects. `object="*"` lists every
  object on the page. The compact inspect shows `object`, `object_part` and `object_path` on each layer and an
  `objects` list; `vixl manifest` lists the objects too.
- `vixl_render(isolate=["person/guitar"])` shows one object or part alone. With
  `views=["parts"]` it returns a labelled contact sheet: the assembled object, every part and sub-object alone;
  `exploded=true` adds a view with the parts pulled apart so overlaps and seams show.
- `vixl_check(action='spatial')` and `vixl_check(action='measure')` accept paths (`dog/head`), and `vixl_check`
  measures every declared object against its kind (below).

## The object check

`vixl_check` runs `object` by default whenever the page declares an object (`vixl check --checks object` runs it
alone). Each object and sub-object is measured against its kind, merged down the taxonomy:

| Rule | Action | Finds |
| --- | --- | --- |
| `object.part-missing` | fix | A required part no layer names (a dog without a head). |
| `object.part-count` | fix | Fewer layers than a required part's `count` (a dog with three legs); more than two of a paired part is review. |
| `object.part-side` | review | Two of a paired part (eyes, ears, wings) without a side, or both on the same side. |
| `object.part-unknown` | review | A part name the kind does not list. |
| `object.gap` | fix | Two parts the kind says must touch that do not, with the gap: `guitar/neck ↔ guitar/body: 6 px gap`. |
| `object.proportion` | review | A part's size against the object's height or another part outside the kind's range. |
| `object.symmetry-size` | review | A left/right pair whose sizes differ by more than 15%. |
| `object.symmetry-side` | review | A left/right pair that sits on one side of the centre of the part it attaches to. |
| `object.layering` | review | Parts that overlap stacked against the kind's back-to-front `layering` (a far leg over the body). |
| `object.outline-seam` | review | With an [outline policy](#outline-policy) applied: a part stroke showing inside the silhouette. |
| `object.outline-weight` | review | Under `outline: parts`: part outlines whose widths differ by more than 25%. |
| `object.outline-stale` | fix | The outline was drawn for other geometry, or its layer is gone. |

Every finding carries `layer_ids`, a canvas `box`, `measured` (actual against expected), `object` (its path),
`kind` and a `hint`, which names the kind's build placement for the part when there is one. Gaps are measured on
the parts' drawn ink, within `connect_tolerance` (default 2 px), and on a timeline at the poster, middle and last
frames (`frame` says where a part first comes loose), as `connected` samples them. Proportions and mirrored pairs
are measured in the object's own frame, so a rotated object reads the same.

- Exaggerated on purpose? `{type: object, target: NAME, stylized: true}` (or `proportions: "ignore"`) silences
  the proportion findings.
- A side view: name limbs `depth: far` (behind the body) and `depth: near` (in front); layering hints such as
  "far limbs" then apply to them, and a far/near pair is not expected to mirror.
- A part that floats on purpose (a spark, steam above a cup): `layer-intent detached_ok`.
- `connected` leaves declared objects to `object`, so a gap is reported once; it still checks every other group.
- A standard character is a `person` without a record of its own and is left to the `character` check; declare
  it (`{type: object, target: hero, kind: person}`) to check it here too.

## Export one object

`vixl_export(path, isolate=["guitar"], padding=8)` writes only that object, cropped to its ink plus
`padding` on a transparent canvas, in any format (PNG, SVG, PDF, PSD, PPTX …). A `.vixl` path writes a
**portable object document**: the object made top-level at its size on the page, with the fonts, images,
swatches and timeline tracks it uses.

```bash
vixl export guitar.svg --isolate guitar --padding 8
vixl export guitar.vixl --isolate guitar
```

## Save and place editable objects

- `{type: object-save, target: dog, name: rex}` keeps the subtree in the document's object library with its
  object and part records, recipes (organic, character …), timeline tracks and the fonts it uses.
- `{type: object-place, name: rex, x, y, scale | width | height, name_as, recolor}` inserts it again as an
  editable group with new IDs. `recolor` maps part names to colours (`{"body": "#c96", "ear": "#743"}`); each
  placement is independent. `source: "rex.vixl"` places a portable object document from the workspace instead,
  so an exported object and a saved one are interchangeable, and `name: "brand:rex"` places an element of the
  workspace brand.json ([brand elements](../layout/brands.md#elements)).
- The component library's `library-place` workflow action places a component as an editable group (its
  layers, fonts and images). `as: "image"` keeps the old raster snapshot.

## Exports keep the identity

| Format | What is written |
| --- | --- |
| SVG | Each object is `<g id="person--guitar" data-vixl-object="person/guitar" data-vixl-kind="guitar">` with a `<title>` (its label); parts carry `data-vixl-part` (and `data-vixl-side`). IDs are sanitised and unique, so `document.querySelector('[data-vixl-kind=guitar] [data-vixl-part=neck]')` finds the neck. |
| PowerPoint | Objects are group shapes named after their label with `descr` "label (kind)", so the selection pane lists "guitar" as one group. |
| PSD | Objects are layer groups named "label (kind)"; parts keep their layer names. |
| PDF | Not carried: optional-content groups would make objects toggle-able layers in viewers, which is not what an object is, so the PDF writer leaves them out. |

Alt text from [accessibility](../output/accessibility.md) is written alongside: an object's `alt` becomes its title.

## Limits

- Object records do not change rendering; only an applied outline policy draws (its outline layer and the part
  strokes it sets). The silhouette is computed from the parts' geometry at rest: on a timeline it does not follow
  animated parts. The object check reads a part's size from its box, not its silhouette,
  and compares only what the kind declares; it cannot tell whether a shape looks like the part it is named for
  (`vixl_render(isolate=[NAME], views=["parts"])` shows that).
- Build blocks are short curated notes and examples, read offline; nothing is fetched.
- A portable object loses the rotation and skew of groups above it (its size keeps their scale).
- SVG import restores objects from the document a Vixl SVG carries ([SVG round trip](../output/exporting.md#svg-round-trip));
  an SVG edited elsewhere is read element by element and `data-vixl-object`/`data-vixl-part` are not read back.
