"""Diagrams: flowcharts, dependency graphs, org charts, mind maps and grids as ordinary layers.

``diagram`` takes nodes (id, label, kind, color, icon, size, group) and edges (from, to, label, kind,
ports), lays them out (``diagram_layout``), and writes editable vector layers into one group:

* each node is a shape layer plus a text layer (and an icon path), named ``<diagram>/<node id>``;
* each edge is one path layer (line, dashes and arrowhead) named ``<diagram>/<from>-><to>``, with a
  text layer for its label; the line is cut around the label so it stays readable;
* lanes and clusters are shape and text layers underneath.

The nodes and edges stay in ``state["diagrams"][name]`` as the source of truth, together with the
layer IDs. ``diagram-set`` changes them and lays the diagram out again *in place*, so layer IDs,
everything an agent added to those layers (effects, styles, timeline tracks) and the group's
position survive. Exports, checks and every other operation see ordinary layers.
"""

from copy import deepcopy
import difflib
import math
import re
from types import SimpleNamespace

from . import diagram_layout as L
from .errors import VixlError, require
from .geometry import compact_number
from .model import finite, new_layer

TYPES = ("diagram", "diagram-set", "diagram-from-text")
NODE_KINDS = ("process", "decision", "terminator", "io", "note", "group", "database", "circle")
EDGE_KINDS = ("arrow", "line", "dashed")
ARROWS = ("end", "start", "both", "none")
PORTS = ("top", "right", "bottom", "left")
LAYOUTS = ("auto", *L.ALGORITHMS)
FITS = ("shrink", "contain", "none")
THEMES = ("light", "dark", "mono")
ICONS = {
    "check": "M4 12.5 L6.6 9.9 L10 13.3 L17.4 5.9 L20 8.5 L10 18.5 Z",
    "cross": "M6 8.6 L8.6 6 L12 9.4 L15.4 6 L18 8.6 L14.6 12 L18 15.4 L15.4 18 L12 14.6 L8.6 18 L6 15.4 L9.4 12 Z",
    "warning": "M12 3 L22 20.5 L2 20.5 Z M10.9 9 L10.9 14.5 L13.1 14.5 L13.1 9 Z M10.9 16.5 L10.9 18.7 L13.1 18.7 L13.1 16.5 Z",
    "info": "M12 2.5 A9.5 9.5 0 1 1 12 21.5 A9.5 9.5 0 1 1 12 2.5 Z M10.9 6.8 L10.9 9 L13.1 9 L13.1 6.8 Z "
            "M10.9 10.5 L10.9 17 L13.1 17 L13.1 10.5 Z",
    "play": "M8 5 L19.5 12 L8 19 Z",
    "stop": "M6 6 L18 6 L18 18 L6 18 Z",
    "bolt": "M13.5 2 L4.5 13.5 L11 13.5 L9.5 22 L19.5 9.5 L13 9.5 Z",
    "star": "M12 2.5 L14.8 8.9 L21.7 9.5 L16.5 14.1 L18.1 20.9 L12 17.3 L5.9 20.9 L7.5 14.1 L2.3 9.5 L9.2 8.9 Z",
    "user": "M12 4 A4 4 0 1 1 12 12 A4 4 0 1 1 12 4 Z M4 21 C4 16.5 7.5 14 12 14 C16.5 14 20 16.5 20 21 Z",
    "flag": "M5 3 L7 3 L7 21 L5 21 Z M7 4 L19 4 L16 8.5 L19 13 L7 13 Z",
    "arrow": "M4 10 L14 10 L14 5 L21 12 L14 19 L14 14 L4 14 Z",
}
KIND_ALIASES = {
    "start": "terminator", "end": "terminator", "stop": "terminator", "oval": "terminator", "terminal": "terminator",
    "step": "process", "task": "process", "action": "process", "box": "process", "rect": "process", "node": "process",
    "condition": "decision", "choice": "decision", "branch": "decision", "diamond": "decision", "question": "decision",
    "data": "io", "input": "io", "output": "io", "parallelogram": "io",
    "comment": "note", "annotation": "note", "text": "note",
    "lane": "group", "swimlane": "group", "cluster": "group", "subgraph": "group", "container": "group",
    "db": "database", "storage": "database", "cylinder": "database", "ellipse": "circle", "connector": "circle",
}
# Fill and outline per node kind, text, connectors and group boxes for each theme.
PALETTES = {
    "light": {
        "process": ("#e8f0fe", "#3b6bb5"), "decision": ("#fff3d1", "#b7791f"), "terminator": ("#e1f5e6", "#2f855a"),
        "io": ("#efe8fb", "#6b46c1"), "note": ("#fffbe0", "#a39a3a"), "database": ("#e0f4f4", "#2c7a7b"),
        "circle": ("#fde8ec", "#c53053"), "group": ("#f5f6f8", "#9aa5b1"), "lane_header": "#e5e8ec",
        "text": "#1f2937", "edge": "#4b5563",
    },
    "dark": {
        "process": ("#1e3a5f", "#7aa7e0"), "decision": ("#5a4513", "#e0b252"), "terminator": ("#1f4d33", "#6cc58d"),
        "io": ("#3b2a63", "#a98be6"), "note": ("#4a4720", "#cfc769"), "database": ("#174b4c", "#5cc3c4"),
        "circle": ("#5b1f2d", "#f08aa0"), "group": ("#1b2230", "#566275"), "lane_header": "#273146",
        "text": "#f1f5f9", "edge": "#9fb0c6",
    },
    "mono": {
        "process": ("#ffffff", "#222222"), "decision": ("#ffffff", "#222222"), "terminator": ("#ffffff", "#222222"),
        "io": ("#ffffff", "#222222"), "note": ("#f4f4f4", "#555555"), "database": ("#ffffff", "#222222"),
        "circle": ("#ffffff", "#222222"), "group": ("#fafafa", "#888888"), "lane_header": "#ececec",
        "text": "#111111", "edge": "#222222",
    },
}
MAX_NODES, MAX_EDGES = 150, 300
PAD = 6  # room around the diagram inside its group, so strokes are never clipped
MIN_LABEL = 9  # smallest label size (px) that still reads
RANKS = {"background": -1, "box": 0, "header": 1, "title": 2, "edge": 3, "node": 4, "label": 5, "edge_label": 6}
OPTION_KEYS = ("layout", "direction", "routing", "lanes", "columns", "theme", "font", "size", "text_color", "node_color",
               "edge_color", "stroke_width", "node_gap", "rank_gap", "margin", "fit", "background", "arrows")


def schemas(add):
    from .schema import S, N, B, POSITIVE_INT, enum

    point = {"anyOf": [N, {"type": "array", "items": N, "minItems": 2, "maxItems": 2}],
             "description": "A size multiplier, or [width, height] in px."}
    node = {"type": "object", "additionalProperties": False, "required": ["id"],
            "properties": {"id": S, "label": S, "kind": enum(*NODE_KINDS), "color": S, "text_color": S, "icon": S,
                           "size": point, "group": S}}
    edge = {"type": "object", "additionalProperties": False, "required": ["from", "to"],
            "properties": {"id": S, "from": S, "to": S, "label": S, "kind": enum(*EDGE_KINDS), "from_port": enum(*PORTS),
                           "to_port": enum(*PORTS), "color": S, "arrow": enum(*ARROWS), "width": N}}
    nodes = {"type": "array", "maxItems": MAX_NODES, "items": {"anyOf": [S, node]},
             "description": "Node IDs or {id, label, kind, color, text_color, icon, size, group}."}
    edges = {"type": "array", "maxItems": MAX_EDGES,
             "items": {"anyOf": [{"type": "array", "items": S, "minItems": 2, "maxItems": 3}, edge]},
             "description": "{from, to, label, kind, from_port, to_port, color, arrow} or [from, to, label]."}
    options = {
        "layout": enum(*LAYOUTS), "direction": enum(*L.DIRECTIONS), "routing": enum(*L.ROUTINGS), "lanes": B,
        "columns": POSITIVE_INT, "theme": enum(*THEMES), "font": S, "size": N, "text_color": S, "node_color": S,
        "edge_color": S, "stroke_width": N, "node_gap": N, "rank_gap": N, "margin": N, "fit": enum(*FITS),
        "background": S, "arrows": B, "x": N, "y": N, "width": N, "height": N,
    }
    add("diagram", {"name": S, "text": S, "nodes": nodes, "edges": edges, "replace": B, **options}, ["name"])
    add("diagram-from-text", {"name": S, "text": S, "replace": B, **options}, ["name", "text"])
    add("diagram-set", {"name": S, "text": S, "nodes": nodes, "edges": edges, "remove_nodes": {"type": "array", "items": S},
                        "remove_edges": {"type": "array", "items": S}, "delete": B, **options}, ["name"])


def execute(project, op):
    kind = op["type"]
    state = project.state
    diagrams = state.setdefault("diagrams", {})
    name = op["name"]
    if kind == "diagram-set":
        require(name in diagrams, _unknown(diagrams, name), field="name")
        rec = diagrams[name]
        _activate(project, rec)
        if op.get("delete"):
            _delete(project, name)
            return
        spec = rec["spec"]
        _merge(project, spec, op, rec)
    else:
        if name in diagrams:
            require(op.get("replace"), f"Diagram {name!r} already exists; change it with diagram-set, or pass replace: true",
                    field="name")
            _activate(project, diagrams[name])
            _delete(project, name)
            diagrams = state.setdefault("diagrams", {})
        require(not any(name in (x["name"], x["id"]) for x in state["layers"]), f"Layer name already exists: {name}",
                field="name")
        spec = _new_spec(project, op)
        rec = {"spec": spec, "group": None, "layers": {}, "page": state.get("page")}
        diagrams[name] = rec
    _layout_into_document(project, name, rec)


def _unknown(diagrams, name):
    close = difflib.get_close_matches(str(name), list(diagrams), 3, 0.5)
    return f"Unknown diagram {name!r}" + (f"; did you mean {' or '.join(map(repr, close))}?" if close else
                                          f". Diagrams: {', '.join(diagrams) or 'none'}")


def _activate(project, rec):
    """Make the page that holds the diagram the active one."""
    page = rec.get("page")
    if page and project.state.get("page") != page:
        from .pages import select

        select(project.state, page=page)


def _delete(project, name):
    from .operations import execute as apply

    rec = project.state["diagrams"].pop(name)
    if rec.get("group") and any(x["id"] == rec["group"] for x in project.state["layers"]):
        apply(project, {"type": "remove", "target": rec["group"]})
    if not project.state["diagrams"]:
        project.state.pop("diagrams")


def _id(value, what):
    require(isinstance(value, str) and 0 < len(value) <= 80 and value == value.strip() and "\n" not in value,
            f"{what} must be 1–80 characters without line breaks or surrounding spaces", field=what)
    return value


def _kind(value):
    value = str(value or "process").strip().lower()
    kind = KIND_ALIASES.get(value, value)
    require(kind in NODE_KINDS, f"Unknown node kind {value!r}; use {', '.join(NODE_KINDS)}", field="kind",
            suggestions=difflib.get_close_matches(value, NODE_KINDS, 2, 0.4))
    return kind


def _node(raw):
    if isinstance(raw, str):
        raw = {"id": raw}
    require(isinstance(raw, dict) and "id" in raw, "Each node needs an id", field="nodes")
    unknown = sorted(set(raw) - {"id", "label", "kind", "color", "text_color", "icon", "size", "group"})
    require(not unknown, f"Unknown node field(s) {', '.join(unknown)}; use id, label, kind, color, text_color, icon, size, group",
            field="nodes")
    node = {"id": _id(raw["id"], "id")}
    for key in ("label", "color", "text_color", "icon", "group"):
        if raw.get(key) is not None:
            require(isinstance(raw[key], str) and len(raw[key]) <= 400, f"node {key} must be text", field=key)
            node[key] = raw[key]
    if raw.get("kind") is not None:
        node["kind"] = _kind(raw["kind"])
    if raw.get("icon") is not None:
        require(raw["icon"] in ICONS, f"Unknown icon {raw['icon']!r}; use {', '.join(ICONS)}", field="icon",
                suggestions=difflib.get_close_matches(raw["icon"], list(ICONS), 2, 0.4))
    if raw.get("size") is not None:
        size = raw["size"]
        if isinstance(size, (int, float)) and not isinstance(size, bool):
            finite(size, "size", 0.2, 10)
        else:
            require(isinstance(size, (list, tuple)) and len(size) == 2, "node size is a multiplier or [width, height]", field="size")
            size = [finite(v, "size", 8, 4000) for v in size]
        node["size"] = size
    return node


def _edge(raw):
    if isinstance(raw, (list, tuple)):
        require(2 <= len(raw) <= 3, "A short edge is [from, to] or [from, to, label]", field="edges")
        raw = {"from": raw[0], "to": raw[1], **({"label": raw[2]} if len(raw) == 3 else {})}
    require(isinstance(raw, dict) and "from" in raw and "to" in raw, "Each edge needs from and to", field="edges")
    unknown = sorted(set(raw) - {"id", "from", "to", "label", "kind", "from_port", "to_port", "color", "arrow", "width"})
    require(not unknown, f"Unknown edge field(s) {', '.join(unknown)}; use from, to, label, kind, from_port, to_port, color, arrow, id",
            field="edges")
    edge = {"from": _id(raw["from"], "from"), "to": _id(raw["to"], "to")}
    if raw.get("id") is not None:
        edge["id"] = _id(raw["id"], "id")
    if raw.get("label") is not None:
        require(isinstance(raw["label"], str) and len(raw["label"]) <= 200, "edge label must be text", field="label")
        if raw["label"]:
            edge["label"] = raw["label"]
    if raw.get("kind") is not None:
        require(raw["kind"] in EDGE_KINDS, f"Unknown edge kind {raw['kind']!r}; use {', '.join(EDGE_KINDS)}", field="kind")
        edge["kind"] = raw["kind"]
    for key in ("from_port", "to_port"):
        if raw.get(key) is not None:
            require(raw[key] in PORTS, f"{key} must be one of {', '.join(PORTS)}", field=key)
            edge[key] = raw[key]
    if raw.get("arrow") is not None:
        require(raw["arrow"] in ARROWS, f"arrow must be one of {', '.join(ARROWS)}", field="arrow")
        edge["arrow"] = raw["arrow"]
    if raw.get("color") is not None:
        require(isinstance(raw["color"], str), "edge color must be text", field="color")
        edge["color"] = raw["color"]
    if raw.get("width") is not None:
        edge["width"] = finite(raw["width"], "width", 0.5, 20)
    return edge


def _edge_id(edges, edge):
    base = f"{edge['from']}->{edge['to']}"
    taken = {e.get("id") for e in edges}
    ident, index = base, 2
    while ident in taken:
        ident, index = f"{base}#{index}", index + 1
    return ident


def _options(project, op, spec):
    """Copy the layout, style and area options an operation carries into the spec."""
    for key in OPTION_KEYS:
        if key not in op:
            continue
        value = op[key]
        if key == "layout":
            require(value in LAYOUTS, f"layout must be one of {', '.join(LAYOUTS)}", field=key)
        elif key == "direction":
            value = {"TD": "TB", "DOWN": "TB", "UP": "BT", "RIGHT": "LR", "LEFT": "RL"}.get(str(value).upper(), str(value).upper())
            require(value in L.DIRECTIONS, f"direction must be one of {', '.join(L.DIRECTIONS)}", field=key)
        elif key == "routing":
            require(value in L.ROUTINGS, f"routing must be one of {', '.join(L.ROUTINGS)}", field=key)
        elif key == "theme":
            require(value in THEMES, f"theme must be one of {', '.join(THEMES)}", field=key)
        elif key == "fit":
            require(value in FITS, f"fit must be one of {', '.join(FITS)}", field=key)
        elif key in ("size", "stroke_width", "node_gap", "rank_gap", "margin"):
            finite(value, key, {"size": 6, "stroke_width": 0.5, "node_gap": 4, "rank_gap": 8, "margin": 0}[key], 2000)
        elif key == "font":
            from .render import resolve_font

            font, role = resolve_font(project, value)
            spec["font"] = font
            spec.pop("font_role", None)
            if role:
                spec["font_role"] = role
            from .operations import embed_font_file

            holder = {"font": font}
            embed_font_file(project, holder)
            spec["font"] = holder["font"]
            continue
        elif key in ("text_color", "node_color", "edge_color", "background"):
            _check_color(project, value)
        spec[key] = value
    for key in ("x", "y", "width", "height"):
        if key in op:
            spec.setdefault("area", {})[key] = finite(op[key], key, -1e6 if key in "xy" else 1, 1e6)


def _check_color(project, value):
    from .design import resolve_color
    from .render import color

    require(isinstance(value, str), "Colors are text", "invalid_color")
    color(resolve_color(value, project.state))


def _new_spec(project, op):
    spec = {"nodes": [], "edges": []}
    _options(project, op, spec)
    _merge(project, spec, op, None)
    return spec


def _merge(project, spec, op, rec):
    """Apply an operation's nodes, edges, text and removals to ``spec``; validate the result."""
    _options(project, op, spec)
    nodes, edges = spec["nodes"], spec["edges"]
    index = {n["id"]: n for n in nodes}
    for raw in op.get("remove_nodes") or []:
        require(raw in index, f"Cannot remove unknown node {raw!r}; nodes: {', '.join(index)}", field="remove_nodes",
                suggestions=difflib.get_close_matches(str(raw), list(index), 3, 0.5))
        nodes[:] = [n for n in nodes if n["id"] != raw]
        edges[:] = [e for e in edges if raw not in (e["from"], e["to"])]
        for n in nodes:
            if n.get("group") == raw:
                n.pop("group")
        index.pop(raw)
    for raw in op.get("remove_edges") or []:
        found = [e for e in edges if e["id"] == raw]
        require(found, f"Cannot remove unknown edge {raw!r}; edges: {', '.join(e['id'] for e in edges[:30])}", field="remove_edges")
        edges[:] = [e for e in edges if e["id"] != raw]
    additions = {"nodes": list(op.get("nodes") or []), "edges": list(op.get("edges") or [])}
    options = {}
    if op.get("text"):
        parsed = parse_text(op["text"])
        additions["nodes"] = parsed["nodes"] + additions["nodes"]
        additions["edges"] = parsed["edges"] + additions["edges"]
        options = parsed["options"]
        for key, value in options.items():
            if key not in op and key in OPTION_KEYS:
                _options(project, {key: value}, spec)
    for raw in additions["nodes"]:
        node = _node(raw)
        if node["id"] in index:
            index[node["id"]].update({k: v for k, v in node.items() if k != "id"})
        else:
            nodes.append(node)
            index[node["id"]] = node
    before, matched = list(edges), []
    for raw in additions["edges"]:
        edge = _edge(raw)
        for end in ("from", "to"):
            require(edge[end] in index, f"Edge refers to unknown node {edge[end]!r}; nodes: {', '.join(index)}. List the node in nodes first.",
                    field="edges", suggestions=difflib.get_close_matches(edge[end], list(index), 3, 0.4))
        if edge.get("id"):
            match = next((e for e in before if e["id"] == edge["id"]), None)
        else:  # the same endpoints name the same edge; parallel edges need their own ids
            match = next((e for e in before if (e["from"], e["to"]) == (edge["from"], edge["to"]) and id(e) not in matched), None)
        if match is not None:
            matched.append(id(match))
            match.update(edge)
        else:
            edge.setdefault("id", _edge_id(edges, edge))
            edges.append(edge)
    _validate_spec(spec)
    if not spec["nodes"]:
        raise VixlError("invalid_operation", "A diagram needs at least one node: pass nodes, or text such as \"A -> B -> C\"",
                        field="nodes")


def _validate_spec(spec):
    nodes, edges = spec["nodes"], spec["edges"]
    require(len(nodes) <= MAX_NODES, f"A diagram holds at most {MAX_NODES} nodes; split it into several diagrams", "resource_limit")
    require(len(edges) <= MAX_EDGES, f"A diagram holds at most {MAX_EDGES} edges", "resource_limit")
    ids = {}
    for n in nodes:
        require(n["id"] not in ids, f"Duplicate node id {n['id']!r}", field="nodes")
        ids[n["id"]] = n
    edge_ids = {}
    for e in edges:
        require(e["id"] not in edge_ids, f"Duplicate edge id {e['id']!r}", field="edges")
        edge_ids[e["id"]] = e
        require(e["from"] in ids and e["to"] in ids, f"Edge {e['id']!r} refers to an unknown node", field="edges")
        require(ids[e["from"]].get("kind") != "group" and ids[e["to"]].get("kind") != "group",
                f"Edge {e['id']!r} ends at a group; connect the nodes inside it", field="edges")
    for n in nodes:
        group = n.get("group")
        if group is not None:
            require(group in ids and ids[group].get("kind") == "group",
                    f"Node {n['id']!r} is in group {group!r}, which is not a node of kind group; declare it with kind: group",
                    field="group", suggestions=difflib.get_close_matches(group, [i for i in ids if ids[i].get("kind") == "group"], 2, 0.4))
            require(group != n["id"], "A group cannot contain itself", field="group")
    for n in nodes:  # no group cycles
        seen, cursor = {n["id"]: True}, n.get("group")
        while cursor:
            require(cursor not in seen, f"Groups {n['id']!r} and {cursor!r} contain each other", field="group")
            seen[cursor] = True
            cursor = ids[cursor].get("group")


FLOW_OPERATORS = re.compile(
    r"(?P<dboth><-\.->)"
    r"|(?P<dashed>-\.+->|\.\.+>|-\.+>)"
    r"|(?P<dline>-\.-)"
    r"|(?P<both><-+>|<=+>)"
    r"|(?P<rev><-{1,3}(?![>\-])|<={1,3}(?![>=]))"
    r"|(?P<arrow>-{1,3}>|={1,3}>)"
    r"|(?<=\s)(?P<line>-{2,3})(?=\s)"
)
DIRECTIVE = re.compile(r"^(layout|direction|routing|theme|columns|lanes|fit|arrows|size|font|background)\s*[:=]\s*(.+)$", re.I)
GROUP_LINE = re.compile(r"^(group|lane|swimlane|cluster|subgraph)\s+(.+?)\s*:\s*(.+)$", re.I)
ATTRIBUTE = re.compile(r"""@(\w+)=("[^"]*"|'[^']*'|\S+)""")
BRACKETS = (("[(", ")]", "database"), ("([", "])", "terminator"), ("((", "))", "circle"), ("[/", "/]", "io"),
            ("[", "]", "process"), ("(", ")", "process"), ("{", "}", "decision"), (">", "]", "note"))


def _node_expression(text, line):
    """(id, label or None, kind or None, attributes) of ``id``, ``id[Label]``, ``id{Question?}`` … ``@key=value``."""
    attributes = {}
    for key, value in ATTRIBUTE.findall(text):
        attributes[key.lower()] = value.strip("\"'")
    text = ATTRIBUTE.sub("", text).strip()
    require(text, f"Line {line}: expected a node", field="text")
    for opener, closer, kind in BRACKETS:
        position = text.find(opener)
        if position > 0 and text.endswith(closer) and len(text) >= position + len(opener) + len(closer):
            ident = text[:position]
            label = text[position + len(opener):len(text) - len(closer)].strip()
            if re.fullmatch(r"[^\s\[\](){}|@<>]+", ident):  # the ID is one word, right against its bracket
                return ident, label or None, kind, attributes
    return text, None, None, attributes


def parse_text(text):
    """Nodes, edges and options from the simple text format (see docs/diagrams.md)."""
    require(isinstance(text, str) and len(text) <= 100000, "text must be up to 100000 characters", field="text")
    nodes, edges, options = {}, [], {}
    order = []
    indented = []  # (indent, line number, text) for hierarchy lines
    flow_lines = []

    def ensure(ident, label=None, kind=None, attributes=None, line=0):
        _id(ident, "node")
        node = nodes.setdefault(ident, {"id": ident})
        if label:
            node["label"] = label
        if kind:
            node["kind"] = kind
        for key, value in (attributes or {}).items():
            if key == "kind":
                node["kind"] = _kind(value)
            elif key == "size":
                node["size"] = [float(v) for v in re.split(r"[x,]", value)] if re.search(r"[x,]", value) else float(value)
            elif key in ("color", "text_color", "icon", "group", "label"):
                node[key] = value
            else:
                raise VixlError("invalid_operation", f"Line {line}: unknown node attribute @{key}; use @color, @text_color, "
                                "@icon, @kind, @size, @group, @label", field="text")
        if ident not in order:
            order.append(ident)
        return node

    for number, raw in enumerate(text.replace("\t", "    ").splitlines(), 1):
        stripped = raw.strip()
        if not stripped or stripped.startswith(("#", "//", "%%")):
            continue
        body = stripped
        group = GROUP_LINE.match(body)
        if group and not FLOW_OPERATORS.search(body):
            gid = group.group(2).strip()
            ensure(gid, None, "group", None, number)
            for member in group.group(3).split(","):
                if member.strip():
                    ident, label, kind, attributes = _node_expression(member.strip(), number)
                    ensure(ident, label, kind, attributes, number)["group"] = gid
            continue
        directive = DIRECTIVE.match(body)
        if directive and not FLOW_OPERATORS.search(body):
            key, value = directive.group(1).lower(), directive.group(2).strip()
            options[key] = {"lanes": lambda v: v.lower() in ("true", "yes", "on", "1"), "arrows": lambda v: v.lower() in ("true", "yes", "on", "1"),
                            "columns": int, "size": float}.get(key, lambda v: v)(value)
            continue
        if FLOW_OPERATORS.search(body):
            flow_lines.append((number, body))
        else:
            body = re.sub(r"^[-*+•]\s+", "", body)
            indented.append((len(raw) - len(raw.lstrip(" ")), number, body))
    for number, body in flow_lines:
        _flow_line(body, number, ensure, edges)
    flat = len(set(indent for indent, _, _ in indented)) <= 1
    stack = []
    for indent, number, body in indented:
        ident, label, kind, attributes = _node_expression(body, number)
        ensure(ident, label, kind, attributes, number)
        while stack and stack[-1][0] >= indent:
            stack.pop()
        if stack and not flat:
            edges.append({"from": stack[-1][1], "to": ident, "kind": "line"})
        stack.append((indent, ident))
    if indented and not flow_lines and len({i for i, _, _ in indented}) > 1:
        options.setdefault("layout", "tree")
    if edges and all(e.get("kind") == "line" for e in edges) and not flow_lines:
        options.setdefault("layout", "tree")
    return {"nodes": [nodes[i] for i in order], "edges": edges, "options": options}


def _flow_line(body, number, ensure, edges):
    parts, operators, last = [], [], 0
    for match in FLOW_OPERATORS.finditer(body):
        parts.append(body[last:match.start()])
        operators.append(match.lastgroup)
        last = match.end()
    parts.append(body[last:])
    labels = [None] * len(operators)
    for i in range(1, len(parts)):  # -->|label| B
        m = re.match(r"\s*\|([^|]*)\|\s*(.*)$", parts[i])
        if m:
            labels[i - 1], parts[i] = m.group(1).strip() or None, m.group(2)
    final = parts[-1]
    trailing = None
    colon = re.search(r"\s*:\s+(.*)$", final) or (re.search(r":(.+)$", final) if "[" not in final and "(" not in final else None)
    if colon and not any(b in final[:colon.start()] for b in "[({") or (colon and final[:colon.start()].count("[") == final[:colon.start()].count("]")):
        trailing, final = colon.group(1).strip() or None, final[:colon.start()]
        parts[-1] = final
    require(all(p.strip() for p in parts), f"Line {number}: expected a node on both sides of every arrow", field="text")
    expressions = [_node_expression(p.strip(), number) for p in parts]
    for ident, label, kind, attributes in expressions:
        ensure(ident, label, kind, attributes, number)
    for i, op in enumerate(operators):
        src, dst = expressions[i][0], expressions[i + 1][0]
        edge = {}
        if op in ("rev",):
            src, dst = dst, src
        edge["from"], edge["to"] = src, dst
        if op in ("dashed", "dboth", "dline"):
            edge["kind"] = "dashed"
        elif op == "line":
            edge["kind"] = "line"
        if op in ("both", "dboth"):
            edge["arrow"] = "both"
        elif op == "dline":
            edge["arrow"] = "none"
        label = labels[i] or (trailing if i == len(operators) - 1 else None)
        if label:
            edge["label"] = label
        edges.append(edge)


class _Text:
    """Measures label text through the document's own text engine, with a cache."""

    def __init__(self, project, font):
        self.project, self.font, self.cache = project, font, {}

    def layer(self, text, size):
        return {"text": text, "font": self.font, "size": size, "spacing": max(0, round(size * 0.18)), "align": "center"}

    def measure(self, text, size):
        key = (text, size)
        if key not in self.cache:
            from .render import text_metrics

            w, h, _ = text_metrics(self.project, self.layer(text, size))
            self.cache[key] = (w, h)
        return self.cache[key]

    def wrap(self, text, size, width):
        """``text`` with line breaks so no line is wider than ``width`` (words are never split)."""
        if "\n" not in text and self.measure(text, size)[0] <= width:
            return text
        from .text import UnsupportedText, font_data, lines

        try:
            wrapped = lines(font_data(self.project, self.layer(text, size)), text, size, width)
        except UnsupportedText:
            wrapped = text.split("\n")
        return "\n".join(line.rstrip() for line in wrapped)


def _even(value):
    return int(math.ceil(value / 2) * 2)


class _Style:
    """Resolved look of a diagram at one scale."""

    def __init__(self, project, spec, scale, canvas_size):
        self.s = scale
        self.theme = PALETTES[spec.get("theme", "light")]
        base = spec.get("size") or max(12, min(30, round(min(canvas_size) / 38)))
        self.size = max(6, round(base * scale))
        self.label_size = max(6, round(self.size * 0.85))
        self.stroke = max(1.0, round(float(spec.get("stroke_width", 2)) * scale * 2) / 2)
        self.edge_width = self.stroke
        self.text_color = spec.get("text_color")
        self.edge_color = spec.get("edge_color") or self.theme["edge"]
        self.arrow = max(6.0, 11 * scale * (0.8 + 0.1 * float(spec.get("stroke_width", 2))))
        self.arrows = spec.get("arrows", True)


def _colors(project, spec, node, style):
    """(fill, stroke, text color) of a node: its own color, or the theme's for its kind."""
    from .colors import contrast_ratio, hex_of, mix, parse
    from .design import resolve_color

    kind = node.get("kind", "process")
    fill, stroke = style.theme[kind]
    if kind != "group" and spec.get("node_color"):
        fill = spec["node_color"]
        stroke = None
    if node.get("color"):
        fill, stroke = node["color"], None
    resolved = parse(resolve_color(fill, project.state))
    if stroke is None:
        darker = resolved[3] > 0 and (0.2126 * resolved[0] + 0.7152 * resolved[1] + 0.0722 * resolved[2]) > 0.45
        stroke = hex_of(mix(resolved, (0, 0, 0, 1) if darker else (1, 1, 1, 1), 0.45))
    text = node.get("text_color") or style.text_color
    if text is None:
        # The theme's text color when it reads on this fill, else whichever of near-black and white reads better.
        text = style.theme["text"]
        if contrast_ratio(resolved, parse(resolve_color(text, project.state))) < 4.5:
            near_black, white = (0.07, 0.09, 0.15, 1), (1, 1, 1, 1)
            text = hex_of(max((near_black, white), key=lambda c: contrast_ratio(resolved, c)))
    return fill, stroke, text


def _node_geometry(kind, text_w, text_h, style, icon, explicit):
    """(width, height, layout shape, inset) of a node that must hold a label of the given size."""
    s = style.s
    pad_x, pad_y = 16 * s, 11 * s
    extra = (style.size * 1.1 + 8 * s) if icon else 0.0
    tw = text_w + extra
    min_w, min_h = 96 * s, 46 * s
    if kind == "decision":
        h = max(80 * s, 2.3 * text_h + 2 * pad_y)
        w = max(128 * s, tw / max(0.2, 1 - text_h / h) + 2 * pad_x)
        shape, inset = "diamond", 0.0
    elif kind == "terminator":
        h = max(min_h, text_h + 2 * pad_y)
        w = max(min_w, tw + 2 * pad_x + h * 0.45)
        shape, inset = "capsule", h / 2
    elif kind == "io":
        h = max(min_h, text_h + 2 * pad_y)
        skew = min(20 * s, h * 0.4)
        w = max(min_w + 2 * skew, tw + 2 * pad_x + 2 * skew)
        shape, inset = "parallelogram", skew
    elif kind == "circle":
        w = max(min_h * 1.5, tw * 1.35 + 2 * pad_x)
        h = max(min_h * 1.5, text_h * 1.5 + 2 * pad_y)
        shape, inset = "ellipse", 0.0
    elif kind == "database":
        h = max(min_h * 1.2, text_h + 2 * pad_y + 22 * s)
        w = max(min_w, tw + 2 * pad_x)
        shape, inset = "cylinder", 0.0
    else:  # process, note
        h = max(min_h, text_h + 2 * pad_y)
        w = max(min_w, tw + 2 * pad_x)
        shape, inset = "rect", min(8 * s, h / 4) if kind == "process" else 0.0
    if explicit is not None:
        if isinstance(explicit, (int, float)):
            w, h = w * explicit, h * explicit
        else:
            w, h = explicit[0] * s, explicit[1] * s
    return _even(w), _even(h), shape, inset


Build = SimpleNamespace  # one layout of a diagram: sizes, geometry and what the layers will be


def _canvas_area(project, spec):
    c = project.state["canvas"]
    margin = float(spec.get("margin", max(24, round(0.04 * min(c["width"], c["height"])))))
    area = spec.get("area") or {}
    x = area.get("x", margin)
    y = area.get("y", margin)
    w = area.get("width", c["width"] - x - margin if "x" in area else c["width"] - 2 * margin)
    h = area.get("height", c["height"] - y - margin if "y" in area else c["height"] - 2 * margin)
    return float(x), float(y), max(40.0, float(w)), max(40.0, float(h))


def _auto_layout(spec):
    nodes = [n for n in spec["nodes"] if n.get("kind") != "group"]
    indegree = {}
    for e in spec["edges"]:
        indegree[e["to"]] = indegree.get(e["to"], 0) + 1
    forest = all(v <= 1 for v in indegree.values()) and not any(e["from"] == e["to"] for e in spec["edges"])
    if forest:  # no cycle: every node has at most one parent, so a cycle would leave no root
        roots = [n for n in nodes if n["id"] not in indegree]
        forest = bool(roots) or not nodes
    plain = not any(e.get("label") for e in spec["edges"]) and not any(n.get("kind") in ("decision", "io", "terminator") for n in nodes)
    return "tree" if forest and plain and not any(n.get("group") for n in spec["nodes"]) and nodes else "layered"


def _build(project, spec, scale, area, name, direction=None):
    """Lay the spec out at ``scale``; returns a ``Build`` with node/edge geometry and layer parts."""
    style = _Style(project, spec, scale, (area[2], area[3]))
    font = spec.get("font", "DejaVuSans.ttf")
    if spec.get("font_role"):
        from .render import resolve_font

        font, _ = resolve_font(project, spec["font_role"])
    elif font == "DejaVuSans.ttf" and (project.state.get("typography") or {}).get("body"):
        from .render import resolve_font

        font, _ = resolve_font(project, "body")
    measure = _Text(project, font)
    layout_name = spec.get("layout", "auto")
    if layout_name == "auto":
        layout_name = _auto_layout(spec)
    direction = direction or spec.get("direction", "LR" if layout_name == "mindmap" else "TB")
    routing = spec.get("routing") or ("curved" if layout_name in ("mindmap",) else "orthogonal")
    lanes = bool(spec.get("lanes")) and layout_name == "layered"
    b = Build(style=style, font=font, layout_name=layout_name, direction=direction, routing=routing, scale=scale, notes=[])
    lnodes, ledges, lgroups = [], [], []
    b.info = {}
    max_w = 190 * scale
    nested = False
    for n in spec["nodes"]:
        kind = n.get("kind", "process")
        label = n.get("label", n["id"])
        if kind == "group":
            lines = label
            size = style.size
            tw, th = measure.measure(lines, size)
            parent = n.get("group")
            lane = lanes and not parent
            nested = nested or (lanes and bool(parent))
            lgroups.append(L.LGroup(n["id"], (tw + 4, th), parent, lane))
            b.info[n["id"]] = {"kind": "group", "label": lines, "tw": tw, "th": th, "size": size}
            continue
        width = max_w * (0.8 if kind == "decision" else 1.0)
        icon = n.get("icon")
        text = measure.wrap(label, style.size, width - (style.size * 1.1 + 8 * scale if icon else 0))
        tw, th = measure.measure(text, style.size)
        w, h, shape, inset = _node_geometry(kind, tw, th, style, icon, n.get("size"))
        fill, stroke, text_color = _colors(project, spec, n, style)
        b.info[n["id"]] = {"kind": kind, "label": text, "tw": tw, "th": th, "w": w, "h": h, "fill": fill, "stroke": stroke,
                           "text_color": text_color, "icon": icon, "inset": inset, "shape": shape}
        lnodes.append(L.LNode(n["id"], w, h, shape, inset, n.get("group")))
    if nested:
        b.notes.append("Lanes do not nest; groups inside a lane are placed in the lane without a box of their own.")
    b.edge_info = {}
    for e in spec["edges"]:
        label = e.get("label")
        size = None
        if label:
            text = measure.wrap(label, style.label_size, 170 * scale)
            tw, th = measure.measure(text, style.label_size)
            size = (tw + 12 * scale, th + 6 * scale)
            b.edge_info[e["id"]] = {"text": text, "tw": tw, "th": th, "box": size}
        else:
            b.edge_info[e["id"]] = {}
        ledges.append(L.LEdge(e["id"], e["from"], e["to"], size, e.get("from_port"), e.get("to_port")))
    options = L.Options(
        algorithm=layout_name, direction=direction, routing=routing,
        node_gap=float(spec.get("node_gap", 44)) * scale, rank_gap=float(spec.get("rank_gap", 68)) * scale,
        edge_gap=14.0 * scale, arrow=style.arrow, pad=16 * scale, lanes=lanes, columns=spec.get("columns"),
        aspect=max(0.5, area[2] / max(1.0, area[3])), loop=26 * scale, scale=scale,
    )
    result = L.layout(lnodes, ledges, lgroups, options)
    b.result, b.size = result, (result.size[0] + 2 * PAD, result.size[1] + 2 * PAD)
    b.lanes = lanes
    b.lnodes = {n.id: n for n in lnodes}
    b.measure = measure
    return b


def _parts(project, name, spec, b):
    """The layers a build needs: [{key, rank, type, name, x, y, width, height, fields}] with coordinates local to the group."""
    style, result = b.style, b.result
    s = b.scale
    parts = []
    nodes = {n["id"]: n for n in spec["nodes"]}

    def text_part(key, rank, layer_name, text, size, color, cx, cy, extra_dy=0.0):
        w, h = b.measure.measure(text, size)
        parts.append({"key": key, "rank": rank, "type": "text", "name": layer_name, "x": round(cx - w / 2), "y": round(cy - h / 2 + extra_dy),
                      "width": w, "height": h,
                      "fields": {"text": text, "font": b.font, "size": size, "color": color, "align": "center",
                                 "spacing": max(0, round(size * 0.18)), "auto_size": True},
                      "font_role": spec.get("font_role")})

    if spec.get("background"):
        parts.append({"key": "bg", "rank": RANKS["background"], "type": "shape", "name": f"{name}/background", "x": 0, "y": 0,
                      "width": math.ceil(b.size[0]), "height": math.ceil(b.size[1]),
                      "fields": {"shape": "rectangle", "fill": spec["background"], "stroke": "transparent", "stroke_width": 0}})
    for gid, (gx, gy, gw, gh, tx, ty) in result.groups.items():
        info = b.info[gid]
        fill, stroke, text_color = _colors(project, spec, nodes[gid], style)
        x, y = round(gx + PAD), round(gy + PAD)
        w, h = round(gw), round(gh)
        parts.append({"key": f"g:{gid}", "rank": RANKS["box"], "type": "shape", "name": f"{name}/{gid}", "x": x, "y": y, "width": w, "height": h,
                      "fields": {"shape": "rectangle" if b.lanes else "rounded-rectangle", "fill": fill, "stroke": stroke,
                                 "stroke_width": max(1.0, style.stroke * 0.6),
                                 **({} if b.lanes else {"radius": round(10 * s)})}})
        title = info["label"]
        if b.lanes:
            header = round(result.header)
            hx, hy, hw, hh = (x, y, w, header) if b.direction in ("TB", "BT") else (x, y, header, h)
            parts.append({"key": f"g:{gid}:header", "rank": RANKS["header"], "type": "shape", "name": f"{name}/{gid}.header", "x": hx, "y": hy,
                          "width": max(1, hw), "height": max(1, hh),
                          "fields": {"shape": "rectangle", "fill": style.theme["lane_header"], "stroke": stroke,
                                     "stroke_width": max(1.0, style.stroke * 0.6)}})
            text_part(f"g:{gid}:title", RANKS["title"], f"{name}/{gid}.title", title, style.size, style.theme["text"] if not spec.get("text_color") else spec["text_color"],
                      hx + hw / 2, hy + hh / 2)
        else:
            text_part(f"g:{gid}:title", RANKS["title"], f"{name}/{gid}.title", title, style.size, text_color,
                      x + 16 * s + info["tw"] / 2, y + 8 * s + info["th"] / 2)
    obstacles = [result.nodes[i] for i in result.nodes if b.info[i]["kind"] != "group"]
    b.labels = {}
    for e in spec["edges"]:
        route = result.edges.get(e["id"])
        if route is None:
            continue
        label_info = b.edge_info[e["id"]]
        box = label_info.get("box") if route.label else None
        geometry = _edge_geometry(route, e, style, box, obstacles, 3 * s)
        if geometry is None:
            continue
        x0, y0, w, h, path, label_at, look = geometry
        parts.append({"key": f"e:{e['id']}", "rank": RANKS["edge"], "type": "shape", "name": f"{name}/{e['id']}", "x": round(x0 + PAD), "y": round(y0 + PAD),
                      "width": w, "height": h,
                      "fields": {"shape": "path", "path": path, "path_view": [w, h], "fill": look["fill"], "stroke": look["stroke"],
                                 "stroke_width": look["width"], "line_cap": "round"}})
        if label_at is not None:
            b.labels[e["id"]] = label_at
            color = spec.get("text_color") or style.theme["text"]
            text_part(f"e:{e['id']}:label", RANKS["edge_label"], f"{name}/{e['id']}.label", label_info["text"], style.label_size, color,
                      label_at[0] + PAD, label_at[1] + PAD)
    for n in spec["nodes"]:
        info = b.info[n["id"]]
        if info["kind"] == "group":
            continue
        x, y, w, h = result.nodes[n["id"]]
        x, y = round(x + PAD), round(y + PAD)
        fields = _shape_fields(info, w, h, style, s)
        parts.append({"key": f"n:{n['id']}", "rank": RANKS["node"], "type": "shape", "name": f"{name}/{n['id']}", "x": x, "y": y, "width": w, "height": h,
                      "fields": fields})
        dy = (6 * s if info["kind"] == "database" else 0.0)
        cx = x + w / 2
        if info["icon"]:
            isize = round(style.size * 1.1)
            total = isize + 8 * s + info["tw"]
            left = cx - total / 2
            parts.append({"key": f"n:{n['id']}:icon", "rank": RANKS["label"], "type": "shape", "name": f"{name}/{n['id']}.icon",
                          "x": round(left), "y": round(y + h / 2 - isize / 2 + dy), "width": isize, "height": isize,
                          "fields": {"shape": "path", "path": ICONS[info["icon"]], "path_view": [24, 24], "fill": info["text_color"],
                                     "stroke": "transparent", "stroke_width": 0}})
            text_part(f"n:{n['id']}:label", RANKS["label"], f"{name}/{n['id']}.label", info["label"], style.size, info["text_color"],
                      left + isize + 8 * s + info["tw"] / 2, y + h / 2 + dy)
        else:
            text_part(f"n:{n['id']}:label", RANKS["label"], f"{name}/{n['id']}.label", info["label"], style.size, info["text_color"],
                      cx, y + h / 2 + dy)
    return parts


def _shape_fields(info, w, h, style, s):
    kind, sw = info["kind"], style.stroke
    fields = {"fill": info["fill"], "stroke": info["stroke"], "stroke_width": sw}
    i = sw / 2
    if kind == "process":
        fields.update(shape="rounded-rectangle", radius=round(info["inset"], 1))
    elif kind == "decision":
        fields.update(shape="diamond")
    elif kind == "terminator":
        fields.update(shape="capsule")
    elif kind == "circle":
        fields.update(shape="ellipse")
    elif kind == "io":
        k = info["inset"]
        fields.update(shape="path", path=f"M{k + i:g} {i:g} L{w - i:g} {i:g} L{w - k - i:g} {h - i:g} L{i:g} {h - i:g} Z", path_view=[w, h])
    elif kind == "note":
        f = min(16 * s, h * 0.35)
        fields.update(shape="path", path=(f"M{i:g} {i:g} L{w - f - i:g} {i:g} L{w - i:g} {f + i:g} L{w - i:g} {h - i:g} L{i:g} {h - i:g} Z "
                                          f"M{w - f - i:g} {i:g} L{w - f - i:g} {f + i:g} L{w - i:g} {f + i:g}"), path_view=[w, h])
    elif kind == "database":
        ry = min(h * 0.14, 12 * s)
        rx = (w - sw) / 2
        top, bottom = i + ry, h - i - ry
        fields.update(shape="path", path_view=[w, h], path=(
            f"M{i:g} {top:g} L{i:g} {bottom:g} A{rx:g} {ry:g} 0 0 0 {w - i:g} {bottom:g} L{w - i:g} {top:g} "
            f"A{rx:g} {ry:g} 0 0 0 {i:g} {top:g} Z M{i:g} {top:g} A{rx:g} {ry:g} 0 0 0 {w - i:g} {top:g}"))
    return fields


def _path_d(chains, close_heads=()):
    pieces = []
    for chain in chains:
        if not chain:
            continue
        pieces.append(f"M{compact_number(chain[0][1][0], 2)} {compact_number(chain[0][1][1], 2)}")
        for seg in chain:
            if seg[0] == "L":
                pieces.append(f"L{compact_number(seg[2][0], 2)} {compact_number(seg[2][1], 2)}")
            else:
                pieces.append("C" + " ".join(f"{compact_number(p[0], 2)} {compact_number(p[1], 2)}" for p in seg[2:]))
    return " ".join(pieces)


def _place_label(body, route, box, obstacles, margin):
    """(chains of the line, label centre). The label sits on the line, which is cut around it, when
    enough line is left on both sides; otherwise it sits beside the line and the line stays whole."""
    cx, cy = route.label
    rect = (cx - box[0] / 2 - margin, cy - box[1] / 2 - margin, box[0] + 2 * margin, box[1] + 2 * margin)
    chains = L.cut_rect(body, rect)
    start, end = body[0][1], body[-1][-1]
    close = lambda p, q: abs(p[0] - q[0]) < 0.01 and abs(p[1] - q[1]) < 0.01  # noqa: E731
    if chains and close(chains[0][0][1], start) and close(chains[-1][-1][-1], end):
        if all(L.route_length(c) >= 10 for c in (chains[0], chains[-1])):
            return chains, (cx, cy)
    # beside the line: nearest segment, on whichever side is free of nodes and of the line itself
    segments = [seg for seg in body if seg[0] == "L"] or body
    nearest = min(segments, key=lambda seg: min(math.hypot(p[0] - cx, p[1] - cy) for p in L.flatten([seg], 8)))
    dx, dy = L.end_direction([nearest])
    nx, ny = -dy, dx
    reach = (box[1] / 2 + 6 + margin) if abs(ny) > abs(nx) else (box[0] / 2 + 6 + margin)
    base = L.point_at_fraction([nearest], 0.5)
    fallback = None
    for along in (0.0, 0.3, -0.3):
        length = L.route_length([nearest])
        for sign in (-1, 1):
            px = base[0] + dx * along * length + sign * nx * reach
            py = base[1] + dy * along * length + sign * ny * reach
            candidate = (px - box[0] / 2, py - box[1] / 2, box[0], box[1])
            fallback = fallback or (px, py)
            if any(_rect_overlap(candidate, o) > 0 for o in obstacles):
                continue
            if L.route_hits_rect(body, (candidate[0] - 1, candidate[1] - 1, candidate[2] + 2, candidate[3] + 2)):
                continue
            return [body], (px, py)
    return [body], fallback


def _edge_geometry(route, edge, style, label_box, obstacles, margin):
    """(x, y, width, height, path d, label centre, look) of an edge layer, local to its own box."""
    kind = edge.get("kind", "arrow")
    arrow = edge.get("arrow") or ("none" if kind == "line" or not style.arrows else "end")
    sw = float(edge.get("width", style.edge_width))
    color = edge.get("color") or style.edge_color
    segments = route.segments
    head_len = style.arrow
    half = head_len * 0.42
    heads = []
    body = list(segments)
    inset = sw / 2
    if arrow in ("end", "both"):
        tip = body[-1][-1]
        if L.route_length(body) > head_len * 1.2:
            body, direction = L.trim_end(body, head_len * 0.8)
        else:
            direction = L.end_direction(body)
        heads.append((tip, direction))
    if arrow in ("start", "both"):
        tip = segments[0][1]
        flipped = L.reverse_segments(body)
        if L.route_length(flipped) > head_len * 1.2:
            flipped, direction = L.trim_end(flipped, head_len * 0.8)
        else:
            direction = L.end_direction(flipped)
        body = L.reverse_segments(flipped)
        heads.append((tip, direction))
    label_at = None
    if label_box and route.label:
        chains, label_at = _place_label(body, route, label_box, obstacles, margin)
    else:
        chains = [body]
    if kind == "dashed":
        dashed = []
        for chain in chains:
            if chain:
                dashed += L.dash_chain(chain, max(6.0, 3.2 * sw), max(4.0, 2.2 * sw))
        chains = dashed
    filled = bool(heads)
    if filled:
        # Open runs are drawn out and back so the fill that paints the arrowhead adds no area of its own.
        chains = [chain + L.reverse_segments(chain) for chain in chains]
    head_points = []
    for tip, (dx, dy) in heads:
        tx, ty = tip[0] - dx * inset, tip[1] - dy * inset
        bx, by = tx - dx * head_len, ty - dy * head_len
        nx, ny = -dy * half, dx * half
        head_points.append(((bx + nx, by + ny), (tx, ty), (bx - nx, by - ny)))
    points = []
    for chain in chains:
        points += L.flatten(chain, 12)
    for triple in head_points:
        points += list(triple)
    if not points:
        return None
    pad = sw / 2 + 2
    x0, y0 = math.floor(min(p[0] for p in points) - pad), math.floor(min(p[1] for p in points) - pad)
    x1, y1 = math.ceil(max(p[0] for p in points) + pad), math.ceil(max(p[1] for p in points) + pad)
    w, h = max(1, x1 - x0), max(1, y1 - y0)
    shifted = [[(seg[0], *[(p[0] - x0, p[1] - y0) for p in seg[1:]]) for seg in chain] for chain in chains]
    d = _path_d(shifted)
    for (a, tip, c) in head_points:
        d += " M{} {} L{} {} L{} {} Z".format(*(compact_number(v, 2) for v in (
            a[0] - x0, a[1] - y0, tip[0] - x0, tip[1] - y0, c[0] - x0, c[1] - y0)))
    return x0, y0, w, h, d.strip(), label_at, {"fill": color if filled else "transparent", "stroke": color, "width": sw}


def _layout_into_document(project, name, rec):
    """Lay the diagram out (shrinking to fit its area) and write or update its layers."""
    spec = rec["spec"]
    area = _canvas_area(project, spec)
    box = spec.get("area") or {}
    # A diagram given its own box fills it; one sized by the canvas only shrinks to fit.
    fit = spec.get("fit", "contain" if "width" in box and "height" in box else "shrink")
    scale = 1.0
    b = None
    natural = None
    direction = None
    first = _build(project, spec, scale, area, name)
    if "direction" not in spec and first.layout_name in ("layered", "tree"):
        # Without a direction, a diagram that would have to shrink to fit its box runs the way the box is longer.
        down = min(area[2] / first.size[0], area[3] / first.size[1])
        if down < 1:
            across = _build(project, spec, scale, area, name, direction="LR")
            if min(area[2] / across.size[0], area[3] / across.size[1]) > down * 1.05:
                direction, first = "LR", across
    for attempt in range(5):
        b = first if attempt == 0 else _build(project, spec, scale, area, name, direction)
        if natural is None:
            natural = list(b.size)
        if fit == "none":
            break
        factor = min(area[2] / b.size[0], area[3] / b.size[1])
        if fit == "shrink":
            factor = min(1.0, factor)
        else:
            factor = max(0.3, min(3.0, factor))
        if abs(factor - 1) < 0.015 or (fit == "shrink" and factor >= 0.999):
            break
        if b.style.size <= 6 and factor < 1:
            break
        scale = max(0.2, scale * (factor * 0.995 if factor < 1 else factor))
    parts = _parts(project, name, spec, b)
    _sync(project, name, rec, b, parts, area)
    result = b.result
    nodes_local = {k: [round(v[0] + PAD, 1), round(v[1] + PAD, 1), v[2], v[3]] for k, v in result.nodes.items()}
    rec["layout"] = {
        "algorithm": b.layout_name, "direction": b.direction, "routing": b.routing, "scale": round(scale, 3),
        "natural": [round(natural[0]), round(natural[1])], "size": [math.ceil(b.size[0]), math.ceil(b.size[1])],
        "font_size": b.style.size, "crossings": result.crossings, "reversed": list(result.reversed),
        "nodes": nodes_local,
        "shapes": {k: [b.lnodes[k].shape, round(b.lnodes[k].inset, 1)] for k in nodes_local if k in b.lnodes},
        "groups": {k: [round(v[0] + PAD, 1), round(v[1] + PAD, 1), round(v[2], 1), round(v[3], 1)] for k, v in result.groups.items()},
        "edges": {k: {"points": [[round(p[0] + PAD, 1), round(p[1] + PAD, 1)] for p in L.flatten(r.segments, 12)],
                      **({"label": [round(b.labels[k][0] + PAD - b.edge_info[k]["box"][0] / 2, 1),
                                    round(b.labels[k][1] + PAD - b.edge_info[k]["box"][1] / 2, 1),
                                    round(b.edge_info[k]["box"][0], 1), round(b.edge_info[k]["box"][1], 1)]}
                         if k in b.labels else {})}
                  for k, r in result.edges.items()},
        "notes": list(b.notes) + list(result.notes),
    }
    rec["layout"]["too_small"] = b.style.size < MIN_LABEL


def _sync(project, name, rec, b, parts, area):
    """Create, update or remove the layers so they match ``parts``; keep IDs stable and order the children."""
    from .operations import append_layer, execute as apply

    state = project.state
    layers = state["layers"]
    index = {x["id"]: x for x in layers}
    existing = {k: v for k, v in rec["layers"].items() if v in index}
    wanted = {p["key"]: p for p in parts}
    needed = sum(1 for k in wanted if k not in existing) + (0 if rec.get("group") in index else 1)
    freed = sum(1 for k in existing if k not in wanted)
    require(len(layers) + needed - freed <= project.limits.max_layers,
            f"This diagram needs {len(wanted) + 1} layers and the document allows {project.limits.max_layers} in total; "
            "split it into several diagrams or remove layers", "resource_limit")
    for key in [k for k in existing if k not in wanted]:
        apply(project, {"type": "remove", "target": existing.pop(key)})
    width, height = math.ceil(b.size[0]), math.ceil(b.size[1])
    group = index.get(rec.get("group"))
    placement = rec.get("placement")
    if group is None:
        group = new_layer(name, "group", width, height, content_width=width, content_height=height)
        append_layer(project, group)
        rec["group"] = group["id"]
        moved = (0.0, 0.0)
    else:
        moved = (group["x"] - placement[0], group["y"] - placement[1]) if placement else (0.0, 0.0)
    x = area[0] + (area[2] - width) / 2 if width <= area[2] else area[0]
    y = area[1] + (area[3] - height) / 2 if height <= area[3] else area[1]
    x, y = round(x + moved[0]), round(y + moved[1])
    group.update(width=width, height=height, content_width=width, content_height=height, x=x, y=y)
    rec["placement"] = [round(x - moved[0]), round(y - moved[1])]
    group["constraints"] = {} if not group.get("constraints") else group["constraints"]
    created = []
    layer_map = {}
    for part in parts:
        layer = index.get(existing.get(part["key"]))
        fields = deepcopy(part["fields"])
        if layer is None:
            layer = new_layer(part["name"], part["type"], part["width"], part["height"], parent=group["id"])
            if part["type"] == "shape":
                layer.update(fields)
            else:
                layer.update(fields)
                if part.get("font_role"):
                    layer["font_role"] = part["font_role"]
            append_layer(project, layer)
            created.append(layer)
        else:
            if part["type"] == "shape":
                for stale in ("shape", "radius", "path", "path_view", "line_cap", "sides", "inner_radius"):
                    layer.pop(stale, None)
            else:
                layer.pop("font_role", None)
                if part.get("font_role"):
                    layer["font_role"] = part["font_role"]
            layer.update(fields)
            layer.update(width=part["width"], height=part["height"], parent=group["id"])
        layer["x"], layer["y"] = part["x"], part["y"]
        if part["type"] == "text":
            _embed_font(project, layer)
        layer_map[part["key"]] = layer["id"]
    rec["layers"] = layer_map
    # z-order of the children: the diagram's layers keep the slots they occupy, sorted by rank
    rank = {layer_map[p["key"]]: (p["rank"], i) for i, p in enumerate(parts)}
    slots = [i for i, x in enumerate(state["layers"]) if x["id"] in rank]
    ordered = sorted((state["layers"][i] for i in slots), key=lambda x: rank[x["id"]])
    for i, layer in zip(slots, ordered):
        state["layers"][i] = layer
    state["active_layer"] = group["id"]


def _embed_font(project, layer):
    from .operations import embed_font_file

    embed_font_file(project, layer)


def _all_layers(state):
    """Every layer of the document, on the active page and on the others."""
    for layer in state.get("layers", []):
        yield layer
    for page in state.get("pages") or []:
        for layer in (page.get("content") or {}).get("layers", []):
            yield layer


def refresh(project):
    """Forget parts of diagrams whose layers were removed; remove a node whose shape is gone."""
    state = project.state
    diagrams = state.get("diagrams")
    if not diagrams:
        return
    alive = {x["id"] for x in _all_layers(state)}
    for name in list(diagrams):
        rec = diagrams[name]
        if rec.get("group") not in alive:
            leftovers = [v for v in rec["layers"].values() if v in alive]
            for ident in leftovers:
                _drop_layer(project, ident)
            del diagrams[name]
            continue
        spec = rec["spec"]
        gone_nodes = [n["id"] for n in spec["nodes"] if f"n:{n['id']}" in rec["layers"] and rec["layers"][f"n:{n['id']}"] not in alive
                      or f"g:{n['id']}" in rec["layers"] and rec["layers"][f"g:{n['id']}"] not in alive]
        if gone_nodes:
            spec["nodes"] = [n for n in spec["nodes"] if n["id"] not in gone_nodes]
            spec["edges"] = [e for e in spec["edges"] if e["from"] not in gone_nodes and e["to"] not in gone_nodes]
            for n in spec["nodes"]:
                if n.get("group") in gone_nodes:
                    n.pop("group")
        valid = {f"n:{n['id']}" for n in spec["nodes"] if n.get("kind") != "group"} | {f"g:{n['id']}" for n in spec["nodes"] if n.get("kind") == "group"}
        valid_edges = {f"e:{e['id']}" for e in spec["edges"]}
        for key in list(rec["layers"]):
            ident = rec["layers"][key]
            base = key.split(":")
            owner = f"{base[0]}:{base[1]}" if base[0] in ("n", "g", "e") else key
            if ident not in alive:
                del rec["layers"][key]
            elif base[0] in ("n", "g") and owner not in valid or base[0] == "e" and owner not in valid_edges:
                _drop_layer(project, ident)
                del rec["layers"][key]
        if not spec["nodes"]:
            _drop_layer(project, rec["group"])
            del diagrams[name]
        elif gone_nodes:
            rec.get("layout", {}).get("nodes", {}).clear()
            rec["layout"]["stale"] = True
    if not diagrams:
        state.pop("diagrams", None)


def _drop_layer(project, ident):
    from .operations import execute as apply

    try:
        apply(project, {"type": "remove", "target": ident})
    except VixlError:
        for page in project.state.get("pages") or []:
            content = page.get("content")
            if content:
                content["layers"] = [x for x in content["layers"] if x["id"] != ident]


def report(project, operations):
    """Per-diagram summary for operation results: size, scale, crossings and what to look at."""
    names = []
    for op in operations:
        if op["type"] in TYPES and op["name"] not in names:
            names.append(op["name"])
    result = {}
    for name in names:
        rec = project.state.get("diagrams", {}).get(name)
        if rec is None:
            result[name] = {"deleted": True}
            continue
        layout = rec["layout"]
        info = {
            "group": name, "nodes": len([n for n in rec["spec"]["nodes"] if n.get("kind") != "group"]), "edges": len(rec["spec"]["edges"]),
            "layout": layout["algorithm"], "direction": layout["direction"], "routing": layout["routing"],
            "size": layout["size"], "scale": layout["scale"], "label_size": layout["font_size"], "crossings": layout["crossings"],
            "layers": len(rec["layers"]) + 1,
        }
        if layout["reversed"]:
            info["reversed_edges"] = layout["reversed"]
        warnings = list(layout.get("notes", []))
        if layout.get("too_small"):
            warnings.append(f"Labels were scaled down to {layout['font_size']} px, which is hard to read; enlarge the canvas or "
                            "the area, show fewer nodes, or try direction LR/TB or layout grid.")
        if warnings:
            info["warnings"] = warnings
        result[name] = info
    return result


def validate(state):
    """Structural checks of ``state["diagrams"]`` (on load and every commit)."""
    diagrams = state.get("diagrams")
    if diagrams is None:
        return
    require(isinstance(diagrams, dict) and len(diagrams) <= 64, "Invalid diagram registry", "invalid_project")
    for name, rec in diagrams.items():
        require(isinstance(name, str) and isinstance(rec, dict) and isinstance(rec.get("spec"), dict)
                and isinstance(rec.get("layers"), dict), "Invalid diagram record", "invalid_project")
        spec = rec["spec"]
        require(isinstance(spec.get("nodes"), list) and isinstance(spec.get("edges"), list), "Invalid diagram spec", "invalid_project")
        try:
            _validate_spec(spec)
        except VixlError as exc:
            raise VixlError("invalid_project", f"Invalid diagram {name!r}: {exc}") from exc
        for key, value in rec["layers"].items():
            require(isinstance(key, str) and isinstance(value, str), "Invalid diagram layer map", "invalid_project")
        layout = rec.get("layout", {})
        require(isinstance(layout, dict), "Invalid diagram layout record", "invalid_project")


def _rect_overlap(a, b):
    w = min(a[0] + a[2], b[0] + b[2]) - max(a[0], b[0])
    h = min(a[1] + a[3], b[1] + b[3]) - max(a[1], b[1])
    return w * h if w > 0 and h > 0 else 0.0


def check_diagrams(project, resolved, local_bounds, projection, issue, targets=None):
    """Report problems in the diagrams on the checked page (called by ``check_design``)."""
    from .colors import contrast_ratio, parse
    from .design import resolve_color

    diagrams = project.state.get("diagrams") or {}
    for name, rec in diagrams.items():
        group = resolved.get(rec.get("group"))
        if group is None:
            continue
        layout = rec.get("layout") or {}
        if not layout.get("nodes"):
            continue
        spec = rec["spec"]
        kinds = {n["id"]: n.get("kind", "process") for n in spec["nodes"]}
        layer = lambda key: resolved.get(rec["layers"].get(key))  # noqa: E731
        scale_to_canvas = projection["scales"].get(group["id"], 1.0)
        boxes, moved = {}, []
        for node_id, recorded in layout["nodes"].items():
            shape = layer(f"n:{node_id}") or layer(f"g:{node_id}")
            if shape is None:
                continue
            x, y, w, h = local_bounds[shape["id"]]
            boxes[node_id] = (x, y, w, h)
            if abs(x - recorded[0]) > 1.5 or abs(y - recorded[1]) > 1.5 or abs(w - recorded[2]) > 1.5 or abs(h - recorded[3]) > 1.5:
                moved.append(node_id)
        real = [i for i in boxes if kinds.get(i) != "group"]
        if moved:
            issue("diagram", "warning",
                  f"{len(moved)} node(s) of diagram {name!r} were moved or resized since the last layout "
                  f"({', '.join(map(repr, moved[:6]))}); its connectors are stale. Run diagram-set to lay it out again",
                  [group], nodes=moved)
        for i, a in enumerate(real):
            for b in real[i + 1:]:
                area = _rect_overlap(boxes[a], boxes[b])
                if area > 4:
                    issue("diagram", "error", f"Nodes {a!r} and {b!r} of diagram {name!r} overlap by {area:.0f} px²; "
                          "run diagram-set to lay the diagram out again, or give it more room",
                          [x for x in (layer(f'n:{a}'), layer(f'n:{b}')) if x], nodes=[a, b])
        stale = bool(moved)
        outlines = {i: L.LNode(i, boxes[i][2], boxes[i][3], *layout.get("shapes", {}).get(i, ["rect", 0.0]), x=boxes[i][0], y=boxes[i][1])
                    for i in real}
        for edge in spec["edges"]:
            geometry = layout.get("edges", {}).get(edge["id"])
            if not geometry or stale:
                continue
            points = [tuple(p) for p in geometry["points"]]
            segments = [("L", p, q) for p, q in zip(points, points[1:])]
            for node_id in real:
                margin = 3.0 if node_id in (edge["from"], edge["to"]) else 1.0
                if L.route_hits_node(segments, outlines[node_id], margin):
                    other = node_id in (edge["from"], edge["to"])
                    issue("diagram", "error",
                          f"Edge {edge['id']!r} of diagram {name!r} passes through "
                          f"{'its own node' if other else 'node'} {node_id!r}; reroute with ports (from_port/to_port) or another layout",
                          [x for x in (layer(f"e:{edge['id']}"), layer(f"n:{node_id}")) if x], edge=edge["id"], node=node_id)
            label = geometry.get("label")
            if label:
                for node_id in real:
                    if _rect_overlap(label, boxes[node_id]) > 4:
                        issue("diagram", "error", f"The label of edge {edge['id']!r} overlaps node {node_id!r}",
                              [x for x in (layer(f"e:{edge['id']}:label"), layer(f"n:{node_id}")) if x], edge=edge["id"], node=node_id)
        # labels: readable size, contrast with the node, inside the node
        for node in spec["nodes"]:
            node_id = node["id"]
            text = layer(f"n:{node_id}:label")
            shape = layer(f"n:{node_id}")
            if text is None or shape is None:
                continue
            size = text.get("size", 0) * scale_to_canvas
            if size < MIN_LABEL:
                issue("diagram", "warning", f"The label of node {node_id!r} is {size:.1f} px tall, too small to read; "
                      "enlarge the canvas or area, or show fewer nodes", [text], size=round(size, 2))
            tx, ty, tw, th = local_bounds[text["id"]]
            sx, sy, sw, sh = local_bounds[shape["id"]]
            kind = kinds.get(node_id)
            inner = (sx, sy, sw, sh) if kind not in ("decision", "circle") else (sx + sw * 0.15, sy + sh * 0.15, sw * 0.7, sh * 0.7)
            if tx < inner[0] - 1 or ty < inner[1] - 1 or tx + tw > inner[0] + inner[2] + 1 or ty + th > inner[1] + inner[3] + 1:
                issue("diagram", "error", f"The label of node {node_id!r} does not fit inside its {kind} shape; "
                      "shorten the label, enlarge the node with size, or run diagram-set to resize it", [text, shape], node=node_id)
            fill, ink = resolved[shape["id"]].get("fill"), text.get("color")
            try:
                f, t = parse(resolve_color(fill, project.state)), parse(resolve_color(ink, project.state))
                if f[3] > 0.5 and contrast_ratio(f, t) < 4.5:
                    issue("diagram", "error", f"The label of node {node_id!r} has {contrast_ratio(f, t):.1f}:1 contrast with its fill "
                          "(WCAG needs 4.5:1); set text_color or color", [text, shape], node=node_id,
                          contrast=round(contrast_ratio(f, t), 2))
            except VixlError:
                pass
        for edge in spec["edges"]:
            text = layer(f"e:{edge['id']}:label")
            if text is not None:
                size = text.get("size", 0) * scale_to_canvas
                if size < MIN_LABEL:
                    issue("diagram", "warning", f"The label of edge {edge['id']!r} is {size:.1f} px tall, too small to read", [text], size=round(size, 2))
        for gid, box in (layout.get("groups") or {}).items():
            if kinds.get(gid) != "group" or spec.get("lanes"):
                continue
            members = {n["id"] for n in spec["nodes"] if n.get("group") == gid}
            for node_id in real:
                if node_id not in members and node_id in boxes and _rect_overlap(boxes[node_id], box) > 0.5 * boxes[node_id][2] * boxes[node_id][3]:
                    issue("diagram", "warning", f"Group {gid!r} of diagram {name!r} covers node {node_id!r}, which is not a member; "
                          "try lanes: true, a tree or grid layout, or fewer cross-group links", [x for x in (layer(f"g:{gid}"), layer(f"n:{node_id}")) if x])
                    break
        if layout.get("too_small"):
            issue("diagram", "warning", f"Diagram {name!r} was scaled down to {layout['font_size']} px labels to fit; "
                  "enlarge the canvas, widen its area, or show fewer nodes", [group])


def compile_command(cmd, args):
    if cmd not in TYPES:
        return None
    import json

    from .commands import Parser

    p = Parser(prog=f"vixl {cmd}")
    if cmd == "diagram-from-text":
        p.add_argument("text", help='Text such as "A -> B -> C" or an indented hierarchy ("\\n" separates lines)')
    else:
        p.add_argument("name") if cmd == "diagram-set" else None
    if cmd == "diagram-from-text":
        p.add_argument("--name", required=True)
    if cmd == "diagram":
        p.add_argument("name")
        p.add_argument("--nodes", type=json.loads, help='JSON list of nodes: ["A", {"id": "B", "kind": "decision"}]')
        p.add_argument("--edges", type=json.loads, help='JSON list of edges: [["A", "B", "label"], {"from": "B", "to": "C"}]')
        p.add_argument("--text")
    if cmd == "diagram-set":
        p.add_argument("--text")
        p.add_argument("--nodes", type=json.loads)
        p.add_argument("--edges", type=json.loads)
        p.add_argument("--remove-nodes", nargs="+")
        p.add_argument("--remove-edges", nargs="+")
        p.add_argument("--delete", action="store_true", default=None)
    else:
        p.add_argument("--replace", action="store_true", default=None)
    p.add_argument("--layout", choices=list(LAYOUTS))
    p.add_argument("--direction", choices=list(L.DIRECTIONS))
    p.add_argument("--routing", choices=list(L.ROUTINGS))
    p.add_argument("--lanes", action="store_true", default=None)
    p.add_argument("--columns", type=int)
    p.add_argument("--theme", choices=list(THEMES))
    p.add_argument("--fit", choices=list(FITS))
    p.add_argument("--no-arrows", dest="arrows", action="store_false", default=None)
    for key in ("font", "text-color", "node-color", "edge-color", "background"):
        p.add_argument("--" + key)
    for key in ("size", "stroke-width", "node-gap", "rank-gap", "margin", "x", "y", "width", "height"):
        p.add_argument("--" + key, type=float)
    data = {k: v for k, v in vars(p.parse_args(args)).items() if v is not None}
    if "text" in data:
        data["text"] = data["text"].replace("\\n", "\n")
    return {"type": cmd, **data}
