# Diagrams

[Documentation home](README.md) · [Getting started](getting-started.md) · [Visual gallery](gallery.md)

Flowcharts, dependency graphs, org charts, mind maps, swimlane processes and grids. You give
Vixl the nodes and edges; it lays them out, routes the connectors, and writes **ordinary editable
layers**: shapes, paths and text in one group, named after your node and edge IDs. Everything else
(exports, checks, effects, timelines, `move`, `layer-style`) works on them like on any other layer.
There is no graph library behind it: the layout engine is pure Python and NumPy (`diagram_layout.py`).

```bash
vixl diagram-from-text 'Start([Start]) -> Check{Valid?}
Check -> Save[(Database)]: yes
Check -> Fix[Show error]: no
Fix -> Check
Save -> Done([Done])' --name signup --direction LR
vixl check --checks diagram
```

```json
{"type": "diagram", "name": "deps", "layout": "layered", "direction": "LR",
 "nodes": ["app", {"id": "api", "label": "API client", "icon": "bolt"}, {"id": "db", "kind": "database", "label": "Store"}],
 "edges": [["app", "api"], {"from": "api", "to": "db", "label": "SQL", "kind": "dashed"}]}
{"type": "diagram-set", "name": "deps", "text": "app -> cache[Cache]", "remove_nodes": ["db"]}
```

## The operations

| Operation | What it does |
| --- | --- |
| `diagram` | Creates a diagram from `nodes` and `edges` (and/or `text`). `replace: true` re-creates one that exists. |
| `diagram-from-text` | The same, from the [text format](#text-format) alone: one call for a whole diagram. |
| `diagram-set` | Changes a diagram and **lays it out again in place**: add or update `nodes`/`edges`/`text`, `remove_nodes`, `remove_edges`, any layout or style option, or `delete: true`. |

The result of each reports `{nodes, edges, layout, direction, routing, size, scale, label_size, crossings, layers}`,
`reversed_edges` (edges drawn against their direction to break a cycle) and `warnings`.

### Nodes

`nodes` is a list of IDs or `{id, label, kind, color, text_color, icon, size, group}`. The label defaults to the
ID and wraps to fit; the node grows to hold its label.

| `kind` | Drawn as | Aliases in the text format |
| --- | --- | --- |
| `process` (default) | rounded rectangle | step, task, action, box |
| `decision` | diamond | condition, choice, branch, question |
| `terminator` | capsule | start, end, oval |
| `io` | parallelogram | data, input, output |
| `note` | folded-corner rectangle | comment, annotation |
| `database` | cylinder | db, storage |
| `circle` | ellipse | connector |
| `group` | a lane or cluster that contains other nodes (see [groups](#groups-lanes-and-clusters)) | lane, swimlane, cluster |

`color` is the fill (any [color](color-and-print.md), including `@swatch`); the outline is derived from it and the
label color is chosen for 4.5:1 contrast unless `text_color` is set. `icon` is one of `check`, `cross`, `warning`,
`info`, `play`, `stop`, `bolt`, `star`, `user`, `flag`, `arrow`: a small vector glyph left of the label.
`size` is a multiplier (`1.5`) or `[width, height]` in px.

### Edges

`edges` is a list of `[from, to]`, `[from, to, label]` or `{from, to, label, kind, from_port, to_port, color, arrow, id}`.

* `kind`: `arrow` (solid, arrowhead at the end), `line` (solid, no head), `dashed` (dashed, arrowhead). `arrow` overrides
  the heads: `end`, `start`, `both` or `none`.
* `from_port` / `to_port`: `top`, `right`, `bottom` or `left` to leave or enter a node by a given side. The router then
  finds a right-angled path around the other nodes.
* `id` defaults to `from->to` (`#2`, `#3` for parallel edges). Updating an edge by endpoints changes the existing one;
  give parallel edges their own `id`.
* Self loops, parallel edges and cycles are all fine. A cycle is broken by reversing one edge in the layout
  (`reversed_edges`); the arrowhead still points at the edge's target.

Labels sit on the edge's line, which is cut around them, or beside it when the line is too short for a gap.

## Text format

`diagram-from-text` (or `text` in `diagram` / `diagram-set`) takes one statement per line. Blank lines and lines starting
with `#` or `//` are ignored.

```text
direction: LR                       # layout, direction, routing, theme, columns, lanes, fit, size, arrows, background
A -> B -> C                         # a chain; IDs are created as they appear
A -> B: label                       # a label on the last edge of the line (also  A -->|label| B)
Start([Start]) -> Check{Valid?}     # Mermaid-style shapes: [x] process, (x) process, ([x]) terminator,
Check -> Data[/Input/]              #   {x} decision, [/x/] io, [(x)] database, ((x)) circle, >x] note
A -> B @color=#fde68a @icon=check   # attributes: @color @text_color @icon @kind @size @group @label
A --> B   A => B   A -.-> B   A -- B   A <-> B   A -.- B   A <- B
group Billing: Invoice, Pay         # a group (lane or cluster) and its members
```

The ID is the single word right against the bracket (`Check{Valid?}`); anywhere else text is the node's ID and label.

**Hierarchies** are written with indentation and become a tree of line connectors (no arrowheads):

```text
CEO
  CTO
    Dev lead
  CFO
```

## Layouts

`layout` picks the algorithm (default `auto`: a tree when the graph is a plain hierarchy, otherwise layered).

| `layout` | For | Notes |
| --- | --- | --- |
| `layered` | flowcharts, dependency graphs, pipelines | Sugiyama style: layers by longest path, crossing minimisation, straightened long edges, labels on tracks between layers |
| `tree` | org charts, hierarchies, taxonomies | contour-packed tidy tree; several roots sit side by side; extra (non-tree) edges are routed around nodes |
| `radial` | one root with many branches | concentric rings, angles shared by subtree size; a back edge (a cycle) is routed around the nodes |
| `mindmap` | brainstorms | two balanced horizontal trees left and right of the root; curved connectors; extra edges are routed around nodes |
| `grid` | inventories, architecture blocks | row-major in input order (`columns`); connectors avoid the boxes |

`direction` is `TB` (default), `LR`, `BT` or `RL` for layered and tree layouts. `routing` is `orthogonal` (right
angles with bends on non-overlapping tracks), `curved` (cubic S-curves) or `straight`.
`node_gap` and `rank_gap` (px at scale 1) loosen or tighten the spacing. Extra edges (a cycle's back edge, edges the
layout did not place) attach beside the connectors already on a side, so a pair such as `A -> B` and `B -> A` draws as
two lines rather than one two-headed arrow.

### Groups, lanes and clusters

Declare a node with `kind: group` and put members in it with `group`. With `lanes: true` (layered layout) the groups
become **swimlanes**: columns for `TB`, rows for `LR`, each node kept inside its lane, with a header showing the lane
name. Without `lanes`, a group is a **cluster**: a rounded box around its members. Clusters follow the layout and can
overlap if their members are interleaved in the layers; the check says so, and `lanes: true` is the fix for
process flows.

### Fit to the canvas

The diagram is placed in an *area*: the canvas minus `margin` (default 4%), or the `x`, `y`, `width`, `height` you pass.
`fit` is `shrink` (scale everything, including the text, down until it fits), `contain` (also scale up, at most 3×)
or `none`. The default is `contain` when you pass both `width` and `height`, so the diagram fills the box you gave it,
and `shrink` otherwise. Without a `direction`, a tree or layered diagram that would have to shrink to fit its area
runs left to right when that fits better (a wide band gets a horizontal flow); pass `direction: TB` to keep it vertical. Text is never scaled below 6 px; below 9 px the result carries a warning and the check reports it.
`size` sets the label size (px at scale 1); the default follows the canvas.

### Style

`theme` is `palette`, `light`, `dark` or `mono`. Without one, a new diagram follows the document like a chart: `palette`
(surfaces for nodes, `@ink` for text and lines, `@accent` for highlights, as swatch references, so it retints and
follows dark mode) when the document has its palette role swatches, else `dark` on a dark canvas and `light`
otherwise. The choice is stored, so later `diagram-set` calls keep it; diagrams made before 0.23 keep `light`. Pass
`theme: "light"` for the old look. Labels use the caption line height (1.3); `node_color`, `edge_color`, `text_color`, `stroke_width`, `font`
(a role, registered font or, from the CLI, a file; defaults to the document's `body` font), `background` (adds a backdrop
layer) and `arrows: false` adjust it.

## The layers

For a diagram named `flow` the group `flow` holds, bottom to top:

1. lanes and clusters: `flow/<group>`, `flow/<group>.header` (lanes), `flow/<group>.title`
2. edges: `flow/<from>-><to>`, one path layer each (the line, its dashes and its arrowhead)
3. nodes: `flow/<id>` (a shape or path) plus `flow/<id>.icon`
4. labels: `flow/<id>.label`, then edge labels `flow/<from>-><to>.label`

Layer positions are relative to the group, so moving the group moves the diagram. Open runs of an edge are drawn out
and back so that the fill which paints the arrowhead adds no area: the arrowhead is part of the same path, and
`fill`/`stroke` recolor both.

The nodes and edges stay in the document (`state.diagrams`) with the layer IDs. `diagram-set` re-lays-out by updating those
layers *in place*: IDs, effects and styles you added, timeline tracks and the group's position survive. Deleting a node's
layer removes the node and its edges from the diagram; deleting the group removes the diagram. Layout is deterministic: the
same spec gives the same geometry.

## Checks

`vixl check` runs the `diagram` check by default (`--checks diagram` alone is cheap):

| Problem | Severity |
| --- | --- |
| two nodes overlap | error |
| an edge passes through a node (its own or another) | error |
| two edges run on top of each other, so they read as one line or a two-headed arrow (edges from one source or into one target may share a trunk) | error |
| a label does not fit inside its node, or an edge label overlaps a node | error |
| a label has less than 4.5:1 contrast with its node's fill | error |
| a label is under 9 px on the canvas; the diagram was scaled down to unreadable text | warning |
| nodes were moved or resized by hand, so connectors are stale (run `diagram-set`) | warning |
| a cluster covers a node that is not a member | warning |

The standard checks (`bounds`, `overlap`, `contrast`, `legibility`) see the diagram's layers like any others.

## Limits

* At most 150 nodes and 300 edges per diagram, and every node adds two layers (shape and label) and every edge one or
  two: the document's 4,096-layer limit applies, and a diagram that would exceed it is refused with an advice to split it.
* Lanes do not nest. Clusters can nest.
* Labels longer than about 170 px wrap; very long labels make large nodes.
* Characters that no font can draw are reported by the usual `fonts` check.

On pages: a diagram lives on the page that was active when it was created; `diagram-set` finds it from any page.
