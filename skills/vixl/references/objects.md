# Objects and accessibility

Declared objects (a dog, a guitar, a person) with named parts, their review loop and export, and accessibility
metadata.

- **Declare objects** — build a dog, a guitar or a person as one group, then `{type: object, target: GROUP,
  kind: dog}` and `{type: object, action: part, target: LAYER, part: leg, side: left}`. `vixl_reference("dog")`
  and `vixl_reference('objects', name="dog")` give the kind's parts, the parts that must touch,
  proportions and layering (`vixl objects show dog`). A person holding a guitar is an object with a sub-object.
- **Address by path** — `dog/head`, `dog/leg[left]`, `person/guitar/neck` work wherever a layer name does;
  `isolate` also takes `object:KIND`; `edit-layers` selects `where.object`, `where.object_kind`, `where.part`.
- **Review loop** — `vixl_document(action='inspect', object="dog")` lists parts and the required parts still missing
  (`object="*"` lists every object); `vixl_render(isolate=["dog"], views=["parts"], exploded=true)` shows
  each part alone; `vixl_check(checks=["connected"])` finds parts that float free.
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
