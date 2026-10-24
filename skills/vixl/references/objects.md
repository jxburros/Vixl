# Objects and accessibility

Declared objects (a dog, a guitar, a person) with named parts, their review loop and export, and accessibility
metadata.

- **Build from the kind** — `vixl_reference("guitar")` and `vixl_reference('objects', name="guitar")` (`vixl objects
  show guitar`) return the kind's parts, the parts that must touch, proportions, layering and its `build` block:
  approach, operations, shapes and organic presets, placements (`{part: neck, anchor: body.top, at: bottom}`: where
  each part goes, anchors from the align anchor names; `spread: "0.15-0.85"` spaces several along an edge), research
  notes and a working `example` batch. The 15 seed kinds (person, dog, cat, bird, fish, tree, flower, leaf, mushroom,
  guitar, car, house, cup, rock, cloud) have examples that pass the object check: adapt one rather than starting
  blank.
- **Scaffold, then refine** — the loop is reference → object-plan → refine → outline → check.
  `vixl_apply(workflow='object-plan', request={kind: "dog", height: 300, apply: true})` (CLI `vixl object plan dog
  --height 300 --apply`) writes the whole object as named placeholder parts placed by the kind's placements,
  proportions at mid-range, ordered back to front, grouped, declared and named: it passes the object check as
  generated. `apply: false` returns the batch with a next step per part; `box`, `x`/`y`/`height`, `seed`, `with:
  ["guitar"]` (a sub-object) and, for people, `head_units` shape it. Refine each placeholder in place (`{type: shape,
  target: dog-head, …}`). `figure-plan` is `object-plan` with `template: figure-plan`. In a document with a house
  style the batch ends with the flat vector finish (subtle wobble, outline `parts` at 1.2% of the larger side, now and
  then a double line, one hard offset shadow on the object); `illustration: plain` (or `outline: false`) leaves the
  bare scaffold.
- **Outline policy** — `{type: object, action: outline, target: dog}` applies the kind's policy (animals and made
  things: one outline around the silhouette with thin interior lines). `outline: silhouette|parts|none`, `interior:
  hide|thin|show`, `outline_color`, `outline_width` (1% of the larger side; 1.2% under `parts`), `outline_lines:
  [{gap, width}]` (a double or triple line inside the outline); a part takes `outline: none` (keeps its own stroke)
  or `parts`. The `NAME/outline` layer follows moved parts in the same undo step; `outline-remove` restores the part
  strokes.
- **Declare objects** — build a dog, a guitar or a person as one group, then `{type: object, target: GROUP,
  kind: dog}` and `{type: object, action: part, target: LAYER, part: leg, side: left}` (`depth: far|near` for limbs
  behind or in front of the body in a side view). A person holding a guitar is an object with a sub-object.
- **Address by path** — `dog/head`, `dog/leg[left]`, `person/guitar/neck` work wherever a layer name does;
  `isolate` also takes `object:KIND`; `edit-layers` selects `where.object`, `where.object_kind`, `where.part`.
- **Review loop** — `vixl_check` runs the `object` check whenever the page declares objects: missing or miscounted
  parts (a dog with three legs), gaps between parts that must touch (also at animation frames), proportions outside
  the kind's range (`stylized: true` on the object when the exaggeration is deliberate), mirrored pairs that differ
  or sit on one side, and parts stacked against the kind's layering (with an outline applied also seams, uneven part
  outlines and a stale outline); each finding's `hint` names the build placement.
  `vixl_document(action='inspect', object="dog")` lists parts and the required parts still missing
  (`object="*"` lists every object); `vixl_render(isolate=["dog"], views=["parts"], exploded=true)` shows
  each part alone; `vixl_check(checks=["connected"])` finds parts that float free in groups that are not objects.
- **Export and reuse** — `vixl_export(isolate=["guitar"], padding=8)` exports one object cropped to its
  ink (a `.vixl` path writes a portable object); `object-save` / `object-place` (`recolor` by part, `source` for a
  portable file, `brand:NAME` for a brand.json element) place editable copies; `library-place` places components as editable groups (`as: "image"` for a
  snapshot). SVG keeps `data-vixl-object`/`data-vixl-kind`/`data-vixl-part`, PowerPoint named groups, PSD group
  names. `ungroup` refuses an object unless `force: true`.
- **Accessibility** — `layer-intent` `alt` on meaningful images, frames, charts and object groups (or
  `decorative: true`); `{type: accessibility, lang, title, page_alt, page_lang, reading_order}`;
  `vixl_check(checks=["accessibility"])` bundles contrast and colour vision with missing alt, language, small
  text, colour-only charts and reading order. HTML, SVG, PPTX and PDF carry alt and language (no tagged PDF
  structure tree). See [objects](../../../docs/guides/shapes/objects.md) and [accessibility](../../../docs/guides/output/accessibility.md).
