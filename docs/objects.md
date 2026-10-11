# Objects

[Documentation home](README.md) · [Design tools](design-tools.md) · [Organic shapes](organic.md) · [Operation semantics](operations.md)

A dog, a guitar or a person is drawn from many shapes, but it is one thing. An **object** is a group that
says so: it has a **kind** from the taxonomy, its layers can be named as **parts** (head, leg, neck), and an
object inside another object's group is a **sub-object** (a person holding a guitar). Vixl uses this to
address parts by path, review an object on its own, export it alone, reuse it as an editable copy, and keep
its identity in SVG, PowerPoint and PSD files.

## Concepts

| Term | Meaning |
| --- | --- |
| Domain › class › kind | The taxonomy: `organic › animal › mammal › dog`, `constructed › instrument › guitar`. A kind inherits every field from its parent. |
| Object | A group with `object: {kind, label?, notes?, references?}`. A standard character is a `person` without a record of its own: its `character_part` names read as person parts. |
| Part | A layer inside the object with `object_part: {name, side?}`, such as `{name: leg, side: left}`. |
| Sub-object | An object nested inside another object's group. Its parts belong to it, not to the outer object. |
| Path | `dog/head`, `dog/leg[left]`, `person/guitar/neck`: wherever a layer name is accepted. |

## The taxonomy

`vixl objects` searches the kinds, `vixl objects show dog` prints one with everything it inherits, and
`vixl objects tree` prints the tree. Over MCP the same data comes from
`vixl_resource_get(kind="objects", name="dog")`, `vixl_capabilities(topic="objects")` (which includes the tree),
and `vixl_guide(brief="dog")`, which resolves a kind from a brief such as "a friendly dog sitting".

```bash
vixl objects show puppy        # aliases resolve: puppy → dog, acoustic guitar → guitar
vixl objects tree
```

Each entry has `summary`, `aliases`, `parts` (`name`, `required`, `count`, `side`, `sub_object`),
`connections` (pairs of parts that must touch), `proportions` (a part's size against the object's height or
another part), `symmetry`, `layering` (back-to-front order hints) and `outline` (the default outline policy).
`parts+` and `connections+` extend what the parent defines; every other field replaces it. The domains are
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

That value goes to `vixl_resource_add(kind="objects", name="coffee-bean", value=…)`.

## Build an object

1. Draw each part as its own layer (shape, pen, organic, pathfinder) in the order the kind's `layering`
   gives, letting parts that meet overlap by a few pixels.
2. Group them and declare the group, then name the parts:

```json
[
  {"type": "shape", "shape": "ellipse", "name": "dog-body", "x": 100, "y": 120, "width": 160, "height": 80, "fill": "#a65"},
  {"type": "shape", "shape": "ellipse", "name": "dog-head", "x": 230, "y": 80, "width": 70, "height": 70, "fill": "#a65"},
  {"type": "shape", "shape": "rectangle", "name": "leg-1", "x": 110, "y": 190, "width": 16, "height": 50, "fill": "#743"},
  {"type": "shape", "shape": "rectangle", "name": "leg-2", "x": 230, "y": 190, "width": 16, "height": 50, "fill": "#743"},
  {"type": "group", "name": "dog", "targets": ["dog-body", "dog-head", "leg-1", "leg-2"]},
  {"type": "object", "target": "dog", "kind": "dog", "label": "Rex"},
  {"type": "object", "action": "part", "targets": ["dog-head"], "part": "head"},
  {"type": "object", "action": "part", "target": "dog-body", "part": "body"},
  {"type": "object", "action": "part", "target": "dog/leg-1", "part": "leg", "side": "left"},
  {"type": "object", "action": "part", "target": "leg-2", "part": "leg", "side": "right"}
]
```

`object` actions: `set` (the default: declare or update `kind`, `label`, `notes`, `references`), `part`
(`part`, `side`) and `unset` (drop the record and the object's direct part names). A part name outside the
kind's list is kept with a warning that suggests the closest name. `subject` is accepted for `object`,
`object_kind` for `kind` and `name` for `label`. The CLI spells it `vixl object dog --kind dog` and
`vixl object part leg-1 --part leg --side left`.

A declared object stays one item: `move`, `scale`, `rotate`, `align`, `distribute`, `duplicate` and `remove`
act on the group as for any group; `duplicate` copies the records with the subtree. `ungroup` refuses an
object (its identity would be lost) until `{type: object, action: unset}` or `force: true`.

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

- `vixl_document_inspect(object="dog")` (CLI `vixl inspect --object dog`) returns the kind chain, bounds in
  canvas and group space, each part with its side, path, bounds and layer count, the **required parts still
  missing**, layers that are not named as parts, notes, references and sub-objects. `object="*"` lists every
  object on the page. The compact inspect shows `object`, `object_part` and `object_path` on each layer and an
  `objects` list; `vixl manifest` lists the objects too.
- `vixl_render_preview(isolate=["person/guitar"])` shows one object or part alone. With
  `views=["parts"]` it returns a labelled contact sheet: the assembled object, every part and sub-object alone;
  `exploded=true` adds a view with the parts pulled apart so overlaps and seams show.
- `vixl_spatial` and `vixl_measure` accept paths (`dog/head`), and `vixl_check(checks=["connected"])` finds
  parts that float free of the object's body.

## Export one object

`vixl_export_file(path, isolate=["guitar"], padding=8)` writes only that object, cropped to its ink plus
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
  so an exported object and a saved one are interchangeable.
- The component library's `library-place` workflow action places a component as an editable group (its
  layers, fonts and images). `as: "image"` keeps the old raster snapshot.

## Exports keep the identity

| Format | What is written |
| --- | --- |
| SVG | Each object is `<g id="person--guitar" data-vixl-object="person/guitar" data-vixl-kind="guitar">` with a `<title>` (its label); parts carry `data-vixl-part` (and `data-vixl-side`). IDs are sanitised and unique, so `document.querySelector('[data-vixl-kind=guitar] [data-vixl-part=neck]')` finds the neck. |
| PowerPoint | Objects are group shapes named after their label with `descr` "label (kind)", so the selection pane lists "guitar" as one group. |
| PSD | Objects are layer groups named "label (kind)"; parts keep their layer names. |
| PDF | Not carried: optional-content groups would make objects toggle-able layers in viewers, which is not what an object is, so the PDF writer leaves them out. |

Alt text from [accessibility](accessibility.md) is written alongside: an object's `alt` becomes its title.

## Limits

- Object records do not change rendering. Proportion ranges and connections are reference data for agents and
  the `connected` check; there is no proportion check yet.
- A portable object loses the rotation and skew of groups above it (its size keeps their scale).
- SVG import does not read `data-vixl-*` back yet.
