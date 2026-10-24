# Finishing pairs: generic and finished, and the operations between them

Six gaps that separate a page that passes `vixl_check` from one that reads as designed, each as a pair: what the
generic page looks like, what the finished page looks like, the `composition` finding that names the gap, and the
operations that close it. They are described in words and operations, not images, so every pair can be rebuilt and
checked (`tests/test_finishing_pairs.py` applies `generic`, expects the finding, applies `fix` and expects it gone).

How to use a pair: run `vixl_check(checks=["composition"])` (or `vixl_apply` with `check=true`), find the finding's `code`
below, and adapt the `fix` operations to your layer names and sizes, in one batch with the rest of the critique. The
page is 1200 × 800 with a 26 px body; copy is the same in every pair. Layer names (`title`, `subtitle`, `details`) are
the generic page's; use yours. The `fonts` check also fails on these pages until a font pairing replaces the bundled
proofing font (`font-pair`), which is not part of any pair.

## 1. The type has no steps (`flat_hierarchy`)

**Generic.** A headline at 32 px over a subtitle at 28 px over a date line at 26 px: three lines of nearly one size, so the
page has no entry point and reads as a list. **Finished.** The headline sits at about three times the body size (88 px),
the subtitle and date line stay near the body size and move down to leave the headline room.

```json
{"finding": "flat_hierarchy",
 "generic": [
  {"type": "type-scale", "base": 26},
  {"type": "text", "name": "title", "text": "Harbor Night Market", "size": 32, "x": 80, "y": 100, "color": "#14263b"},
  {"type": "text", "name": "subtitle", "text": "Food, music and late shopping", "size": 28, "x": 80, "y": 160, "color": "#14263b"},
  {"type": "text", "name": "details", "text": "Fridays in June, 6 to 11 pm", "size": 26, "x": 80, "y": 215, "color": "#14263b"}],
 "fix": [
  {"type": "text", "target": "title", "size": 88},
  {"type": "move", "target": "subtitle", "y": 235},
  {"type": "move", "target": "details", "y": 295}]}
```

Raise the largest line to at least 1.6 times the body size, in practice twice or more (the finding's `values.raise_to`),
and re-space what follows it. `type-scale` gives the steps by name (`title`, `headline`, `display`) when you set text
through layouts.

## 2. Size is the only contrast (`single_weight`)

**Generic.** Every line in the one regular face the body uses: the headline is large but light, and nothing else
differs between the lines. **Finished.** The headline is set in the heading role (the bolder face of the pairing), the
body and date lines stay in the body face, so weight and shape carry the hierarchy as well as size.

```json
{"finding": "single_weight",
 "generic": [
  {"type": "type-scale", "base": 26},
  {"type": "text", "name": "title", "text": "Harbor Night Market", "size": 88, "x": 80, "y": 100, "color": "#14263b", "font": "body"},
  {"type": "text", "name": "subtitle", "text": "Food, music and late shopping", "size": 36, "x": 80, "y": 235, "color": "#14263b", "font": "body"},
  {"type": "text", "name": "details", "text": "Fridays in June, 6 to 11 pm", "size": 26, "x": 80, "y": 300, "color": "#14263b", "font": "body"}],
 "fix": [
  {"type": "text", "target": "title", "font": "heading"}]}
```

This needs a pairing whose heading and body differ (`font-pair`; `vixl_reference('fonts')` lists them). With one family
only, install a bolder weight for the heading role: `{"type": "font-install", "family": "Inter", "weight": 700, "role": "heading"}`.

## 3. Two things shout (`no_focal`)

**Generic.** Two lines at 96 px, "Half price" and "Night Market", each as heavy as the other, and a small date line:
the eye starts in two places. **Finished.** One line leads: "Half price" stays at 96 px, "Night Market" drops to 56 px in
a muted colour and moves up under it, and the date line follows.

```json
{"finding": "no_focal",
 "generic": [
  {"type": "type-scale", "base": 26},
  {"type": "text", "name": "offer", "text": "Half price", "size": 96, "x": 80, "y": 90, "color": "#14263b"},
  {"type": "text", "name": "event", "text": "Night Market", "size": 96, "x": 80, "y": 260, "color": "#14263b"},
  {"type": "text", "name": "details", "text": "Fridays in June, 6 to 11 pm", "size": 26, "x": 80, "y": 440, "color": "#14263b"}],
 "fix": [
  {"type": "swatch", "name": "muted", "color": "#5b6878"},
  {"type": "text", "target": "event", "size": 56, "color": "@muted"},
  {"type": "move", "target": "event", "y": 230},
  {"type": "move", "target": "details", "y": 330}]}
```

Either block can be the one that leads; pick the one the brief is about. A block's weight grows roughly with the cube of its size, so a third larger
or a step quieter is enough: you do not need to shrink the other to nothing.

## 4. The accent is chosen and never used (`accent_unused`)

**Generic.** A page created with a rolled direction (`vixl new --for social --seed 5`, or `vixl_document` create with
`purpose` and `seed`): the palette has a rust accent, and every line is the ink colour. **Finished.** The accent appears
once, on the thing to find first: the date line is set in `@accent-text` and a short `@accent` bar sits above the
headline.

```json
{"finding": "accent_unused",
 "create": {"purpose": "social", "seed": 5},
 "generic": [
  {"type": "type-scale", "base": 26},
  {"type": "text", "name": "title", "text": "Harbor Night Market", "size": 88, "x": 80, "y": 120, "color": "@ink"},
  {"type": "text", "name": "subtitle", "text": "Food, music and late shopping", "size": 36, "x": 80, "y": 255, "color": "@ink"},
  {"type": "text", "name": "details", "text": "Fridays in June, 6 to 11 pm", "size": 26, "x": 80, "y": 320, "color": "@ink"}],
 "fix": [
  {"type": "text", "target": "details", "color": "@accent-text"},
  {"type": "shape", "name": "accent-bar", "shape": "rectangle", "x": 80, "y": 84, "width": 96, "height": 8, "fill": "@accent"}]}
```

Use the accent once or twice (a call to action, a rule, one key word with `text-style`), never sprinkled. Waive the
finding with a reason if the page is meant to be monochrome.

## 5. A hole in the middle (`dead_band`)

**Generic.** A headline and subtitle at the top, the date line stranded near the bottom edge, and 400 px of nothing
between them (half the page), which reads as two pages. **Finished.** The date line moves up under the subtitle, one step (about 70 px)
away, and the space left below is an edge margin, not a hole.

```json
{"finding": "dead_band",
 "generic": [
  {"type": "type-scale", "base": 26},
  {"type": "text", "name": "title", "text": "Harbor Night Market", "size": 72, "x": 80, "y": 60, "color": "#14263b"},
  {"type": "text", "name": "subtitle", "text": "Food, music and late shopping", "size": 36, "x": 80, "y": 160, "color": "#14263b"},
  {"type": "text", "name": "details", "text": "Fridays in June, 6 to 11 pm", "size": 26, "x": 80, "y": 600, "color": "#14263b"}],
 "fix": [
  {"type": "move", "target": "details", "y": 270}]}
```

`vixl_apply(workflow='repair-layout')` finds this move itself (a dry run by default); do it by hand when the space should
go somewhere else, for example centre the stack in the page with `move` on every block by the same amount.

## 6. Two left margins (`margin_drift`)

**Generic.** The subtitle starts 12 px to the right of the headline and the date line: close enough to read as a mistake,
too close to read as an indent. **Finished.** All three lines share one left edge.

```json
{"finding": "margin_drift",
 "generic": [
  {"type": "type-scale", "base": 26},
  {"type": "text", "name": "title", "text": "Harbor Night Market", "size": 72, "x": 80, "y": 100, "color": "#14263b"},
  {"type": "text", "name": "subtitle", "text": "Food, music and late shopping", "size": 36, "x": 92, "y": 210, "color": "#14263b"},
  {"type": "text", "name": "details", "text": "Fridays in June, 6 to 11 pm", "size": 26, "x": 80, "y": 280, "color": "#14263b"}],
 "fix": [
  {"type": "align", "target": "subtitle", "alignment": "left", "relative_to": "title"}]}
```

An indent of at least two spacing units (a spacing unit is half the body size, so 26 px here) is deliberate; anything
between 2 px and that is drift. A list's bullets hang left of the margin on purpose and are not drift.

See also: [testing](testing.md#composition-checks) for every code and its threshold, [workflow](workflow.md) for where the
finishing pass sits, and `vixl_reference('finishing')` for the checklist.
