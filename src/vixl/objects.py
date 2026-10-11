"""Objects: a group declared as one thing (a dog, a guitar, a person) with a kind, named parts and sub-objects.

The kind taxonomy (domain > class > kind, ``data/objects.json``) describes what each kind is made of: its
parts, the parts that must touch, proportions, layering and outline policy. A kind inherits every field from
its parent; ``parts+`` and ``connections+`` extend the inherited lists. Workspace and user resources of kind
``objects`` add kinds (a brand mascot, a product) that may extend a built-in parent.

In a document, ``group["object"]`` declares the object (``{version, kind, label?, notes?, references?}``) and
``layer["object_part"]`` names a part (``{name, side?}``). An object inside another object's subtree is a
sub-object. A standard character group (``character``) is implicitly a ``person`` whose ``character_part``
values read as person parts; nothing is copied. Objects and parts are addressable as paths such as
``dog/head``, ``dog/leg[left]`` or ``person/guitar/neck`` wherever a layer reference is accepted
(``Project.layer`` falls back to ``resolve_path``), and ``object:KIND`` names every object of a kind in
``isolate``.
"""

from copy import deepcopy
import difflib
from functools import lru_cache
import json
from pathlib import Path
import re

from .errors import VixlError, require

TYPES = ("object", "object-save", "object-place")
DATA = Path(__file__).resolve().parent / "data" / "objects.json"
ENTRY_FIELDS = ("parent", "aliases", "summary", "parts", "parts+", "proportions", "symmetry", "connections",
                "connections+", "layering", "outline", "texture")
INHERITED = ("parts", "proportions", "symmetry", "connections", "layering", "outline", "texture")
PART_FIELDS = ("name", "required", "count", "side", "sub_object")
SIDES = ("left", "right", "center")
RECORD_VERSION = 1
MAX_REFERENCES = 32
MAX_KINDS = 2000
SEGMENT = re.compile(r"^(?P<name>[^\[\]]+?)(?:\[(?P<side>[a-z]+)\])?$")


# ---------------------------------------------------------------------------------------------------------------
# Taxonomy


def slug(text):
    return re.sub(r"[\s_]+", "-", str(text).strip().casefold())


@lru_cache(maxsize=1)
def _builtin():
    data = json.loads(DATA.read_text(encoding="utf-8"))
    validate_registry(data["kinds"])
    return data


def builtin_kinds():
    return deepcopy(_builtin()["kinds"])


def organic_presets():
    """``{organic preset: kind}`` for every organic preset."""
    return dict(_builtin()["organic_presets"])


def character_parts():
    """``{character part: (part name, side)}``: how a standard character's parts read as person parts."""
    return {key: tuple(value) for key, value in _builtin()["character_parts"].items()}


def validate_entry(name, entry):
    """Check one taxonomy entry's shape (not its parent; see ``validate_registry``)."""
    require(isinstance(name, str) and re.fullmatch(r"[a-z0-9][a-z0-9-]{0,79}", name),
            f"Object kind names are 1-80 lowercase letters, digits or hyphens; got {name!r}", field="name")
    require(isinstance(entry, dict), f"Object kind {name!r} must be an object", field=name)
    unknown = sorted(set(entry) - set(ENTRY_FIELDS))
    require(not unknown, f"Object kind {name!r} has unknown field(s) {unknown}; fields: {', '.join(ENTRY_FIELDS)}",
            field=name, allowed=list(ENTRY_FIELDS))
    if "parent" in entry:
        require(isinstance(entry["parent"], str), f"{name}.parent must be a kind name", field=f"{name}.parent")
    require(isinstance(entry.get("aliases", []), list) and all(isinstance(a, str) and a for a in entry.get("aliases", [])),
            f"{name}.aliases must be a list of names", field=f"{name}.aliases")
    require(isinstance(entry.get("summary", ""), str) and len(entry.get("summary", "")) <= 1000,
            f"{name}.summary must be text of at most 1000 characters", field=f"{name}.summary")
    for key in ("parts", "parts+"):
        parts = entry.get(key, [])
        require(isinstance(parts, list) and len(parts) <= 64, f"{name}.{key} must be a list of at most 64 parts",
                field=f"{name}.{key}")
        for part in parts:
            require(isinstance(part, dict) and isinstance(part.get("name"), str) and part["name"]
                    and set(part) <= set(PART_FIELDS), f"{name}.{key} entries are {{name, required?, count?, side?, "
                    "sub_object?}", field=f"{name}.{key}")
            require(isinstance(part.get("count", 1), int) and 1 <= part.get("count", 1) <= 64,
                    f"{name}.{key}: count is 1-64", field=f"{name}.{key}")
            require(isinstance(part.get("required", False), bool) and isinstance(part.get("side", False), bool),
                    f"{name}.{key}: required and side are true or false", field=f"{name}.{key}")
    for key in ("connections", "connections+"):
        pairs = entry.get(key, [])
        require(isinstance(pairs, list) and all(isinstance(p, list) and len(p) == 2 and all(isinstance(x, str) for x in p)
                                                for p in pairs),
                f"{name}.{key} must be a list of [part, part] pairs", field=f"{name}.{key}")
    proportions = entry.get("proportions", [])
    require(isinstance(proportions, list), f"{name}.proportions must be a list", field=f"{name}.proportions")
    for item in proportions:
        require(isinstance(item, dict) and isinstance(item.get("part"), str)
                and all(isinstance(item.get(k), (int, float)) for k in ("min", "max")) and item["min"] <= item["max"],
                f"{name}.proportions entries are {{part, of?, min, max, note?}}", field=f"{name}.proportions")
    require(isinstance(entry.get("layering", []), list) and all(isinstance(x, str) for x in entry.get("layering", [])),
            f"{name}.layering must be a list of names, back to front", field=f"{name}.layering")
    require(isinstance(entry.get("symmetry", ""), str), f"{name}.symmetry must be text", field=f"{name}.symmetry")
    require(isinstance(entry.get("outline", {}), dict), f"{name}.outline must be an object", field=f"{name}.outline")
    require(isinstance(entry.get("texture", False), bool), f"{name}.texture must be true or false", field=f"{name}.texture")


def validate_registry(kinds):
    """Every entry valid, every parent known, no parent cycles and no alias used twice."""
    require(isinstance(kinds, dict) and 0 < len(kinds) <= MAX_KINDS, "The object taxonomy needs 1-2000 kinds")
    names = {}
    for name, entry in kinds.items():
        validate_entry(name, entry)
        names.setdefault(name, name)
    for name, entry in kinds.items():
        parent = entry.get("parent")
        require(parent is None or parent in kinds, f"Object kind {name!r} names an unknown parent {parent!r}",
                field=f"{name}.parent")
        seen, cursor = {name}, parent
        while cursor is not None:
            require(cursor not in seen, f"Object kind {name!r} has a parent cycle", field=f"{name}.parent")
            seen.add(cursor)
            cursor = kinds[cursor].get("parent")
        for alias in entry.get("aliases", []):
            key = slug(alias)
            require(key not in names or names[key] == name,
                    f"Alias {alias!r} of {name!r} is already the name or an alias of {names.get(key)!r}",
                    field=f"{name}.aliases")
            names[key] = name


def validate_user_kind(name, entry, workspace=None):
    """A workspace or user kind: a valid entry whose parent is known, merged without cycles or alias clashes."""
    validate_entry(name, entry)
    kinds = registry(workspace)
    require(entry.get("parent") in kinds, f"A new object kind needs a parent kind (organic, animal, instrument …); "
            f"got {entry.get('parent')!r}", field="parent",
            suggestions=difflib.get_close_matches(str(entry.get("parent")), list(kinds), 3, 0.5))
    validate_registry({**kinds, name: entry})


def registry(workspace=None):
    """Every kind: built in, then user and workspace additions (``vixl_resource_add(kind="objects")``). A library
    whose additions no longer fit the taxonomy falls back to the built-in kinds."""
    from .resources import catalog

    try:
        kinds = catalog("objects", workspace=workspace)
        if kinds != _builtin()["kinds"]:
            validate_registry(kinds)
    except VixlError:
        kinds = builtin_kinds()
    return kinds


def _index(kinds):
    index = {}
    for name, entry in kinds.items():
        index.setdefault(name, name)
        for alias in entry.get("aliases", []):
            index.setdefault(slug(alias), name)
    return index


def find(name, kinds=None):
    """The canonical kind for a name or alias ('puppy' → 'dog', 'acoustic guitar' → 'guitar'), or None."""
    if not isinstance(name, str) or not name.strip():
        return None
    kinds = kinds if kinds is not None else registry()
    index = _index(kinds)
    key = slug(name)
    for candidate in (key, key[:-1] if key.endswith("s") else None, key[:-2] if key.endswith("es") else None):
        if candidate and candidate in index:
            return index[candidate]
    return None


def kind_in_text(text, kinds=None):
    """The first object kind a free-text brief names ('a friendly dog sitting' → dog), trying word pairs first."""
    kinds = kinds if kinds is not None else registry()
    words = re.findall(r"[a-z0-9]+", str(text).casefold())
    for size in (2, 1):
        for i in range(len(words) - size + 1):
            phrase = "-".join(words[i:i + size])
            if len(phrase) < 3 or phrase in STOP_WORDS:
                continue
            found = find(phrase, kinds)
            if found and not kinds[found].get("texture") and kinds[found].get("parent"):
                return found
    return None


# Everyday words that are also aliases; in a free-text brief they rarely name the subject.
STOP_WORDS = {"mark", "seat", "home", "cone", "cell", "wave", "mobile", "computer", "character", "figure", "people",
              "plant", "plants", "the", "and", "for", "with", "mug"}


def resolve_kind(name, kinds=None, field="kind"):
    """The canonical kind, or an error with a did-you-mean."""
    kinds = kinds if kinds is not None else registry()
    found = find(name, kinds)
    if found:
        return found
    close = difflib.get_close_matches(slug(name), list(_index(kinds)), 3, 0.6)
    close = list(dict.fromkeys(_index(kinds)[c] for c in close))
    raise VixlError("invalid_operation", f"Unknown object kind {name!r}" + (
        f"; did you mean {' or '.join(map(repr, close))}?" if close else
        "; see vixl objects (vixl_capabilities(topic='objects')) or add a workspace kind with "
        "vixl_resource_add(kind='objects')"), field=field, suggestions=close)


def chain(name, kinds=None):
    """The kind's ancestry from its domain down to itself."""
    kinds = kinds if kinds is not None else registry()
    result, cursor = [], name
    while cursor is not None:
        result.append(cursor)
        cursor = kinds[cursor].get("parent")
    return result[::-1]


def descends(kind, ancestor, kinds=None):
    """Whether ``kind`` is ``ancestor`` or below it."""
    kinds = kinds if kinds is not None else registry()
    return kind in kinds and ancestor in chain(kind, kinds)


def merged(name, kinds=None):
    """The kind's fields with inheritance applied (parts and connections extended by ``parts+``/``connections+``)."""
    kinds = kinds if kinds is not None else registry()
    result = {}
    for level in chain(name, kinds):
        entry = kinds[level]
        for key in INHERITED:
            if key in entry:
                result[key] = deepcopy(entry[key])
        for key in ("parts", "connections"):
            if f"{key}+" in entry:
                existing = result.get(key, [])
                extra = deepcopy(entry[f"{key}+"])
                if key == "parts":
                    names = {part["name"] for part in extra}
                    existing = [part for part in existing if part["name"] not in names]
                result[key] = existing + extra
    return result


def level(name, kinds):
    if kinds[name].get("parent") is None:
        return "domain"
    return "class" if any(entry.get("parent") == name for entry in kinds.values()) else "kind"


def describe(name, workspace=None):
    """One kind with inherited parts, connections, proportions and its chain (``organic › animal › mammal › dog``)."""
    kinds = registry(workspace)
    kind = resolve_kind(name, kinds, field="name")
    fields = merged(kind, kinds)
    path = chain(kind, kinds)
    return {
        "kind": kind,
        "chain": path,
        "path": " › ".join(path),
        "level": level(kind, kinds),
        "summary": kinds[kind].get("summary", ""),
        **({"aliases": kinds[kind]["aliases"]} if kinds[kind].get("aliases") else {}),
        "parts": fields.get("parts", []),
        "required_parts": [part["name"] for part in fields.get("parts", []) if part.get("required")],
        "connections": fields.get("connections", []),
        "proportions": fields.get("proportions", []),
        "symmetry": fields.get("symmetry", "none"),
        "layering": fields.get("layering", []),
        "outline": fields.get("outline", {}),
        **({"texture": True} if fields.get("texture") else {}),
        "children": sorted(k for k, entry in kinds.items() if entry.get("parent") == kind),
        "organic_presets": sorted(p for p, k in organic_presets().items() if k == kind),
    }


def search(query=None, workspace=None):
    """Kinds whose name, aliases or summary contain every word of ``query`` (all kinds without one)."""
    kinds = registry(workspace)
    words = [w for w in re.findall(r"[a-z0-9]+", (query or "").casefold())]
    found = []
    for name, entry in kinds.items():
        text = " ".join([name, *entry.get("aliases", []), entry.get("summary", "")]).casefold()
        if all(word in text for word in words):
            found.append({"kind": name, "path": " › ".join(chain(name, kinds)), "summary": entry.get("summary", "")})
    return found


def taxonomy(workspace=None):
    """The kind tree as nested ``{name: {children…}}``."""
    kinds = registry(workspace)

    def node(name):
        return {child: node(child) for child in sorted(k for k, e in kinds.items() if e.get("parent") == name)}

    return {name: node(name) for name in kinds if kinds[name].get("parent") is None}


def catalog_command(args, workspace=None):
    """``vixl objects [QUERY]``, ``vixl objects show KIND``, ``vixl objects tree``."""
    if any(arg in ("--help", "-h") for arg in args):
        return ("Usage: vixl objects [QUERY] | vixl objects show KIND | vixl objects tree\n"
                "The object taxonomy (domain > class > kind): search kinds, show one kind's inherited parts, "
                "connections, proportions and chain, or print the whole tree. Workspace kinds come from "
                ".vixl-resources.json (resource kind objects).")
    if args and args[0] == "show":
        require(len(args) == 2, "Use vixl objects show KIND")
        return describe(args[1], workspace)
    if args and args[0] == "tree":
        return {"taxonomy": taxonomy(workspace)}
    query = " ".join(args)
    if query and find(query, registry(workspace)):
        return describe(query, workspace)
    return {"kinds": search(query, workspace),
            "next": "vixl objects show KIND prints the inherited parts, connections and proportions"}


# ---------------------------------------------------------------------------------------------------------------
# Objects in a document


def record(layer):
    """The object a group declares: its explicit record, or ``{kind: person, implicit: true}`` for a character."""
    if layer.get("object"):
        return layer["object"]
    if layer.get("type") == "group" and layer.get("character"):
        return {"version": RECORD_VERSION, "kind": "person", "implicit": True}
    return None


def part_of(layer):
    """``{name, side?}`` for a part: its ``object_part`` record, or a standard character part read through."""
    if layer.get("object_part"):
        return layer["object_part"]
    part = layer.get("character_part")
    if part:
        name, side = character_parts().get(part, (part, None))
        return {"name": name, **({"side": side} if side else {})}
    return None


def _children(layers):
    children = {}
    for layer in layers:
        children.setdefault(layer.get("parent"), []).append(layer)
    return children


def owner(index, layer):
    """The nearest object above ``layer`` (not the layer itself), or None."""
    cursor = index.get(layer.get("parent"))
    while cursor is not None:
        if record(cursor):
            return cursor
        cursor = index.get(cursor.get("parent"))
    return None


def all_objects(project):
    return [layer for layer in project.state["layers"] if layer["type"] == "group" and record(layer)]


GENERATED_NAME = re.compile(r"lyr_[0-9a-f]+")


def _segment_name(layer, index):
    """How a layer is named in a path below its object: its part (with side), its sub-object label, else its name
    without the object's name prefix (a sub-object whose name is a generated ID, as duplicate gives, uses its kind)."""
    found = record(layer)
    tail = layer["name"].rsplit("/", 1)[-1]
    if found and layer.get("parent"):
        return found.get("label") or (found["kind"] if GENERATED_NAME.fullmatch(tail) else tail)
    part = part_of(layer)
    if part:
        return part["name"] + (f"[{part['side']}]" if part.get("side") else "")
    return tail


def path_of(project, layer, index=None):
    """``person/guitar/neck`` for a layer inside an object, or None for a layer outside every object. Plain groups
    between an object and its parts are left out (paths resolve parts at any depth)."""
    index = index if index is not None else {item["id"]: item for item in project.state["layers"]}
    segments, cursor, first = [], layer, True
    while cursor is not None:
        found = record(cursor)
        if found and owner(index, cursor) is None:
            segments.append(cursor["name"])
            return "/".join(reversed(segments))
        if first or found or part_of(cursor):
            segments.append(_segment_name(cursor, index))
        first = False
        cursor = index.get(cursor.get("parent"))
    return None


def _parse_segment(text):
    match = SEGMENT.match(text.strip())
    if not match:
        return text.strip(), None
    side = match["side"]
    return match["name"].strip(), side if side in SIDES else None


def _matches(layer, name, side, index):
    folded = name.casefold()
    part = part_of(layer)
    if part and part["name"].casefold() == folded and (side is None or part.get("side") == side):
        return True
    if side is not None:
        return False
    found = record(layer)
    if found and folded in ((found.get("label") or "").casefold(), found["kind"].casefold()):
        return True
    if layer.get("character_part", "").casefold() == folded:
        return True
    plain = layer["name"].casefold()
    return plain == folded or plain.endswith("/" + folded)


def _below(project, root, children, index, name, side):
    """Layers under ``root`` matching one path segment, shallowest first; part search stops at sub-objects."""
    level, depth = [root], 0
    while level:
        found = [child for parent in level for child in children.get(parent["id"], [])
                 if _matches(child, name, side, index)]
        if found:
            return found
        level = [child for parent in level for child in children.get(parent["id"], []) if not record(child)]
        depth += 1
        if depth > 16:
            break
    return []


def _available(root, children):
    names, level = [], [root]
    for _ in range(16):
        nxt = []
        for parent in level:
            for child in children.get(parent["id"], []):
                part = part_of(child)
                names.append(part["name"] + (f"[{part['side']}]" if part.get("side") else "") if part
                             else (record(child) or {}).get("label") or child["name"].rsplit("/", 1)[-1])
                if not record(child):
                    nxt.append(child)
        level = nxt
        if not level:
            break
    return list(dict.fromkeys(names))


def _roots(project, name):
    layer = project.find_layer(name)
    if layer is not None:
        return [layer]
    folded = name.casefold()
    return [item for item in all_objects(project)
            if (record(item).get("label") or "").casefold() == folded or record(item)["kind"] == folded]


def resolve_all(project, ref):
    """Every layer a path names (``dog/leg`` → each leg), or None when its first segment names nothing."""
    segments = [s for s in ref.split("/")]
    if len(segments) < 2 or not all(s.strip() for s in segments):
        return None
    layers = project.state["layers"]
    index = {item["id"]: item for item in layers}
    children = _children(layers)
    current = _roots(project, segments[0].strip())
    if not current:
        return None
    for position, segment in enumerate(segments[1:], 1):
        name, side = _parse_segment(segment)
        found = []
        for root in current:
            found += [item for item in _below(project, root, children, index, name, side) if item not in found]
        if not found:
            available = list(dict.fromkeys(n for root in current for n in _available(root, children)))
            close = difflib.get_close_matches(segment, available, 3, 0.5)
            prefix = "/".join(segments[:position])
            raise VixlError("layer_not_found", f"{prefix!r} has no part, sub-object or layer {segment!r}"
                            + (f"; did you mean {' or '.join(repr(prefix + '/' + c) for c in close)}?" if close else
                               f". Under it: {', '.join(available[:30]) or 'nothing'}"),
                            field="target", requested=ref, suggestions=[f"{prefix}/{c}" for c in close],
                            available=[f"{prefix}/{c}" for c in available[:50]])
        current = found
    return current


def resolve_path(project, ref):
    """The one layer an object path names, None when its first segment names nothing, or an error when it is
    ambiguous or a later segment is unknown."""
    found = resolve_all(project, ref)
    if found is None:
        return None
    if len(found) > 1:
        index = {item["id"]: item for item in project.state["layers"]}
        options = [path_of(project, item, index) or item["name"] for item in found]
        names = [item["name"] for item in found]
        raise VixlError("ambiguous_target", f"{ref!r} names {len(found)} layers ({', '.join(map(repr, names[:8]))}); "
                        f"add a side such as {ref}[left], or use a layer name",
                        field="target", requested=ref, suggestions=list(dict.fromkeys(options))[:8] + names[:8])
    return found[0]


def expand_refs(project, refs):
    """Layer IDs for refs that may be object paths (every match) or ``object:KIND`` (every object of the kind)."""
    result = []
    kinds = registry(getattr(project, "_workspace", None))
    for ref in refs:
        if isinstance(ref, str) and ref.startswith("object:"):
            kind = resolve_kind(ref[len("object:"):], kinds, field="isolate")
            found = [layer["id"] for layer in all_objects(project) if descends(record(layer)["kind"], kind, kinds)]
            require(found, f"No object of kind {kind!r} (or below it) on this page", "layer_not_found", field="isolate")
            result += found
            continue
        layer = project.find_layer(ref)
        if layer is None and isinstance(ref, str) and "/" in ref:
            matches = resolve_all(project, ref)
            if matches:
                result += [item["id"] for item in matches]
                continue
        result.append(project.layer(ref)["id"])
    return list(dict.fromkeys(result))


def object_parts(project, group, children=None):
    """The parts directly owned by an object (not inside a sub-object), as layers."""
    children = children if children is not None else _children(project.state["layers"])
    found, level = [], [group]
    while level:
        nxt = []
        for parent in level:
            for child in children.get(parent["id"], []):
                if record(child):
                    continue
                if part_of(child):
                    found.append(child)
                nxt.append(child)
        level = nxt
    return found


def sub_objects(project, group, children=None):
    children = children if children is not None else _children(project.state["layers"])
    found, level = [], [group]
    while level:
        nxt = []
        for parent in level:
            for child in children.get(parent["id"], []):
                if record(child):
                    found.append(child)
                else:
                    nxt.append(child)
        level = nxt
    return found


def _round(box):
    return [round(v, 2) for v in box]


def missing_parts(project, group, kinds=None, children=None):
    """Required parts of the object's kind that no layer of the object names."""
    kinds = kinds if kinds is not None else registry(getattr(project, "_workspace", None))
    kind = record(group)["kind"]
    if kind not in kinds:
        return []
    named = {part_of(layer)["name"] for layer in object_parts(project, group, children)}
    named |= {record(child)["kind"] for child in sub_objects(project, group, children)}
    required = [part for part in merged(kind, kinds).get("parts", []) if part.get("required")]
    return [part["name"] for part in required if part["name"] not in named
            and not (part.get("sub_object") and part["sub_object"] in named)]


def tree(project, ref):
    """The object tree for ``vixl_document_inspect(object=...)``: kind chain, bounds in canvas and group space,
    parts with sides, bounds and layer counts, missing required parts, sub-objects, notes and references.
    ``ref='*'`` lists every object on the page as a compact outline."""
    from .design import descendants
    from .render import resolve_layout, resolved_layers
    from .spatial import canvas_boxes

    kinds = registry(getattr(project, "_workspace", None))
    layers = resolved_layers(project)
    local = resolve_layout(project, layers=layers)
    canvas = canvas_boxes(project, layers=layers, local=local)
    index = {item["id"]: item for item in project.state["layers"]}
    children = _children(project.state["layers"])
    if ref == "*":
        items = []
        for group in all_objects(project):
            if owner(index, group):
                continue
            found = record(group)
            items.append({"object": group["name"], "kind": found["kind"],
                          **({"label": found["label"]} if found.get("label") else {}),
                          **({"implicit": True} if found.get("implicit") else {}),
                          "bounds": _round(canvas[group["id"]]),
                          "parts": len(object_parts(project, group, children)),
                          "sub_objects": [path_of(project, sub, index) for sub in sub_objects(project, group, children)]})
        return {"objects": items, "count": len(items),
                "next": "vixl_document_inspect(object=NAME) returns one object's parts and sub-objects"}
    group = project.layer(ref)
    require(record(group) is not None, f"{group['name']!r} is not an object; declare it with "
            "{type: object, target: GROUP, kind: KIND}", field="object")

    def describe_object(group):
        found = record(group)
        kind = found["kind"]
        parts = []
        for layer in object_parts(project, group, children):
            part = part_of(layer)
            count = len(descendants(project, layer["id"])) + 1 if layer["type"] == "group" else 1
            parts.append({"part": part["name"], **({"side": part["side"]} if part.get("side") else {}),
                          "layer": layer["name"], "path": path_of(project, layer, index),
                          "bounds": _round(canvas[layer["id"]]), "layers": count})
        inside = descendants(project, group["id"])
        unnamed = [layer["name"] for layer in project.state["layers"]
                   if layer["id"] in inside and owner(index, layer) is group
                   and not part_of(layer) and not record(layer) and layer["type"] != "group"
                   and not any(part_of(a) for a in _ancestors(index, layer, group))]
        result = {
            "object": group["name"],
            "path": path_of(project, group, index),
            "kind": kind,
            **({"chain": chain(kind, kinds), "path_in_taxonomy": " › ".join(chain(kind, kinds))} if kind in kinds else {}),
            **({k: found[k] for k in ("label", "notes", "references") if found.get(k)}),
            **({"implicit": True, "from": "character"} if found.get("implicit") else {}),
            "bounds": {"canvas": _round(canvas[group["id"]]), "group": _round(local[group["id"]])},
            "layers": len(inside),
            "parts": parts,
            "missing_parts": missing_parts(project, group, kinds, children),
            **({"unnamed_layers": unnamed[:40]} if unnamed else {}),
            "sub_objects": [describe_object(sub) for sub in sub_objects(project, group, children)],
        }
        return result

    return describe_object(group)


def _ancestors(index, layer, stop):
    cursor = index.get(layer.get("parent"))
    while cursor is not None and cursor is not stop:
        yield cursor
        cursor = index.get(cursor.get("parent"))


def brief(layer, project=None, index=None):
    """The object fields a compact inspect shows for one layer."""
    result = {}
    found = record(layer)
    if found:
        result["object"] = {k: v for k, v in found.items() if k in ("kind", "label", "implicit")}
    part = part_of(layer)
    if part:
        result["object_part"] = part
    if project is not None and (found or part):
        path = path_of(project, layer, index)
        if path and path != layer["name"]:
            result["object_path"] = path
    return result


def validate_layers(project, state):
    """The stored object and part records of every layer are well formed."""
    for layer in state["layers"]:
        found = layer.get("object")
        if found is not None:
            require(layer["type"] == "group", f"Only groups can be objects ({layer['name']!r})", "invalid_project")
            require(isinstance(found, dict) and isinstance(found.get("kind"), str) and found["kind"]
                    and set(found) <= {"version", "kind", "label", "notes", "references"},
                    f"Invalid object record on {layer['name']!r}", "invalid_project")
            require(isinstance(found.get("label", ""), str) and isinstance(found.get("notes", ""), str),
                    f"Invalid object record on {layer['name']!r}", "invalid_project")
            refs = found.get("references", [])
            require(isinstance(refs, list) and len(refs) <= MAX_REFERENCES and all(isinstance(r, dict) for r in refs),
                    f"Invalid object references on {layer['name']!r}", "invalid_project")
        part = layer.get("object_part")
        if part is not None:
            require(isinstance(part, dict) and isinstance(part.get("name"), str) and part["name"]
                    and set(part) <= {"name", "side"} and part.get("side", "left") in SIDES,
                    f"Invalid object part on {layer['name']!r}", "invalid_project")
    library = state.get("object_library", {})
    require(isinstance(library, dict), "Invalid object library", "invalid_project")
    for name, item in library.items():
        require(isinstance(item, dict) and isinstance(item.get("layers"), list) and item["layers"]
                and isinstance(item.get("root"), str), f"Invalid saved object {name!r}", "invalid_project")


# ---------------------------------------------------------------------------------------------------------------
# Operations


def schemas(add):
    from .schema import B, N, S, field

    reference = {"type": "object", "properties": {
        "url": field(S, "A research link (https://…) or an embedded image asset ID."),
        "asset": field(S, "An embedded image asset ID used as reference."),
        "credit": field(S, "Attribution for the reference."),
        "license": field(S, "License or usage terms of the reference."),
        "note": field(S, "What the reference shows."),
    }, "additionalProperties": False, "description": "A reference: {url or asset, credit?, license?, note?}."}
    add("object", {
        "action": {"enum": ["set", "unset", "part"], "description": "set (default): declare the target group an object "
                   "of a kind (again: update it); unset: remove the declaration and its direct part names; part: name the "
                   "target layer as a part of the object it belongs to."},
        "kind": field(S, "set: what the object is, a kind or class of the taxonomy (dog, guitar, person, tree, "
                      "instrument …) or an alias such as puppy; vixl objects lists them."),
        "label": field(S, "set: a display name (accessibility title, exports); default the group's name."),
        "notes": {"type": "string", "maxLength": 2000, "description": "set: short design intent kept with the object."},
        "references": {"type": "array", "items": reference, "maxItems": MAX_REFERENCES,
                       "description": "set: research links or image asset IDs with optional credit and license."},
        "part": field(S, "part: the part name, from the kind's part list (head, leg, neck …) or free text (warned)."),
        "side": {"enum": list(SIDES), "description": "part: left, right or center, for symmetric parts."},
    })
    add("object-save", {
        "name": field(S, "Library name (letters, digits, hyphens, underscores)."),
        "description": {"type": "string", "maxLength": 2000, "description": "What the object is, for search."},
        "tags": {"type": "array", "items": S, "maxItems": 32, "description": "Search tags."},
    }, ["name"])
    add("object-place", {
        "name": field(S, "Saved object to place (object-save), or with source the new object's name."),
        "source": field(S, "A portable object .vixl file in the workspace (vixl_export_file(isolate=[OBJ], path=…vixl)) "
                        "to place instead of a saved object."),
        "name_as": field(S, "Name of the placed object group; default the saved name (made unique)."),
        "x": field(N, "Left edge of the placed object on the page (default: where it was saved)."),
        "y": field(N, "Top edge of the placed object on the page (default: where it was saved)."),
        "width": {"type": "number", "exclusiveMinimum": 0, "description": "Scale the placed object to this width in "
                  "pixels (keeps its aspect ratio)."},
        "height": {"type": "number", "exclusiveMinimum": 0, "description": "Scale the placed object to this height in "
                   "pixels (keeps its aspect ratio)."},
        "scale": {"type": "number", "exclusiveMinimum": 0, "maximum": 100, "description": "Scale factor (default 1)."},
        "recolor": {"type": "object", "additionalProperties": S, "description": "Colours by part name, e.g. {body: "
                    "'#c96', ear: '#743'}: every shape and text layer of that part takes the colour."},
        "motion": field(B, "Also copy the object's timeline tracks (default true)."),
    }, ["name"])


def _warn_unknown_part(project, group, name):
    kinds = registry(getattr(project, "_workspace", None))
    kind = record(group)["kind"]
    if kind not in kinds:
        return
    names = [part["name"] for part in merged(kind, kinds).get("parts", [])]
    if names and name not in names:
        from .notices import warn

        close = difflib.get_close_matches(name, names, 1, 0.6)
        warn(project, f"{name!r} is not a part of a {kind} ({', '.join(names)})"
             + (f"; did you mean {close[0]!r}?" if close else "; kept as a free-text part"))


def execute(project, op):
    kind = op["type"]
    if kind == "object":
        return _object(project, op)
    if kind == "object-save":
        return save(project, op)
    return place(project, op)


def _object(project, op):
    from .notices import note

    action = op.get("action", "set")
    layer = project.layer(op.get("target"))
    index = {item["id"]: item for item in project.state["layers"]}
    if action == "part":
        require("part" in op, "object action part needs part (the part name)", field="part")
        require(not any(k in op for k in ("kind", "label", "notes", "references")),
                "part names a part; kind, label, notes and references belong to action set", field="action")
        group = owner(index, layer)
        require(group is not None, f"{layer['name']!r} is not inside an object; declare its group first with "
                "{type: object, target: GROUP, kind: KIND}", field="target")
        name = slug(op["part"])
        require(re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}", name), "Part names are 1-64 letters, digits or hyphens",
                field="part")
        _warn_unknown_part(project, group, name)
        layer["object_part"] = {"name": name, **({"side": op["side"]} if op.get("side") else {})}
        return
    require("part" not in op and "side" not in op, "part and side name a part: use action part", field="action")
    require(layer["type"] == "group", f"{layer['name']!r} is a {layer['type']} layer; an object is a group. Group its "
            "layers first ({type: group, name, targets}) and declare the group", field="target")
    if action == "unset":
        require(not any(k in op for k in ("kind", "label", "notes", "references")), "unset takes only target",
                field="action")
        require(layer.get("object") or not layer.get("character"),
                f"{layer['name']!r} is a character: it reads as a person object until its character record goes",
                field="target")
        for part in object_parts(project, layer):
            part.pop("object_part", None)
        layer.pop("object", None)
        return
    existing = layer.get("object") or {}
    require("kind" in op or existing.get("kind") or layer.get("character"),
            "object needs kind (dog, guitar, person …); vixl objects lists them", field="kind")
    entry = dict(existing) or {"version": RECORD_VERSION}
    kinds = registry(getattr(project, "_workspace", None))
    if "kind" in op:
        canonical = resolve_kind(op["kind"], kinds)
        if slug(op["kind"]) != canonical:
            note(project, f"kind {op['kind']!r} → {canonical!r}")
        entry["kind"] = canonical
    elif not entry.get("kind"):
        entry["kind"] = "person"
    if "label" in op:
        if op["label"]:
            entry["label"] = op["label"][:200]
        else:
            entry.pop("label", None)
    if "notes" in op:
        if op["notes"]:
            entry["notes"] = op["notes"]
        else:
            entry.pop("notes", None)
    if "references" in op:
        for item in op["references"]:
            require(item.get("url") or item.get("asset"), "Each reference needs url or asset", field="references")
            if item.get("asset"):
                require(item["asset"] in project.assets, f"Unknown asset {item['asset']!r}", field="references")
        entry["references"] = deepcopy(op["references"])
    entry["version"] = RECORD_VERSION
    layer["object"] = entry


# ---------------------------------------------------------------------------------------------------------------
# Saving and placing: portable object records


ASSET_REFERENCE = re.compile(r"(?:assets|masks|fonts|sources|emoji-sources)/[0-9a-f]{64}\.[a-z0-9]{2,5}")
RESOURCE_KEYS = ("swatches", "character_styles", "paragraph_styles", "brushes")


def subtree(project, root_id):
    from .design import descendants

    ids = descendants(project, root_id) | {root_id}
    return [layer for layer in project.state["layers"] if layer["id"] in ids]


def snapshot(project, root_id, motion=True):
    """A portable record of the subtree under ``root_id``: its layers (the root re-based to the page), the fonts
    and resources they use and, with ``motion``, the timeline tracks that move them."""
    layers = deepcopy(subtree(project, root_id))
    root = next(layer for layer in layers if layer["id"] == root_id)
    root.pop("parent", None)
    text = json.dumps(layers)
    fonts = {name: asset for name, asset in project.state.get("fonts", {}).items()
             if asset in text or f'"{name}"' in text}
    tracks = []
    if motion:
        ids = {layer["id"] for layer in layers}
        tracks = deepcopy([track for track in (project.state.get("timeline") or {}).get("tracks", [])
                           if track.get("target") in ids])
    item = {"version": RECORD_VERSION, "root": root_id, "layers": layers, "fonts": fonts}
    if tracks:
        item["tracks"] = tracks
    for key in RESOURCE_KEYS:
        if project.state.get(key):
            item.setdefault("resources", {})[key] = deepcopy(project.state[key])
    found = record(project.layer(root_id))
    if found:
        item["kind"] = found["kind"]
    return item


def save(project, op):
    from .design import named

    root = project.layer(op.get("target"))
    require(root["type"] == "group", "object-save saves a group (an object); group its layers first", field="target")
    item = snapshot(project, root["id"])
    item.update(description=op.get("description", ""), tags=list(op.get("tags", [])))
    project.state.setdefault("object_library", {})[named(op["name"])] = item


def _from_file(project, source):
    """A saved-object record read from a portable object document in the workspace."""
    from .film import local_path
    from .project import Project

    root = getattr(project, "_workspace", None)
    require(root is not None, "Placing an object file needs a workspace", field="source")
    path = local_path(root, source)
    require(Path(path).suffix.lower() == ".vixl", "source is a portable object .vixl file", field="source")
    require(Path(path).is_file(), f"No object file at {source!r}", "not_found", field="source")
    return from_document(Project.load(path, limits=project.limits), source)


def from_document(other, label="document"):
    """(record, assets) for placing a whole document (or its one top-level object group) as an editable group."""
    tops = [layer for layer in other.state["layers"] if not layer.get("parent")]
    require(tops, f"{label} has no layers", field="source")
    objects = [layer for layer in tops if record(layer)]
    if len(tops) == 1 and tops[0]["type"] == "group":
        root_layer = tops[0]
    elif len(objects) == 1 and len(tops) == 1:
        root_layer = objects[0]
    else:
        from .operations import execute as apply

        other = other.clone()
        apply(other, {"type": "group", "name": "component", "targets": [layer["id"] for layer in tops]})
        root_layer = other.layer()
    item = snapshot(other, root_layer["id"])
    assets = {}
    for ref in set(ASSET_REFERENCE.findall(json.dumps(item))):
        if ref in other.assets:
            assets[ref] = other.assets[ref]
    return item, assets


def _remap(text_value, mapping):
    for old, new in mapping.items():
        text_value = text_value.replace(old + ".", new + ".")
    return text_value


def place(project, op, record_and_assets=None):
    """Insert a saved (or file) object as an editable group with new IDs; returns the new root layer.
    ``record_and_assets`` places an already-read record (the component library)."""
    from .model import finite, uid
    from .operations import append_layer, default_name, unique_name

    assets = {}
    if record_and_assets is not None:
        item, assets = record_and_assets
    elif op.get("source"):
        item, assets = _from_file(project, op["source"])
    else:
        library = project.state.get("object_library", {})
        require(op["name"] in library, f"No saved object {op['name']!r}"
                + (f"; saved: {', '.join(sorted(library)[:20])}" if library else "; save one with object-save"),
                field="name", suggestions=difflib.get_close_matches(op["name"], list(library), 3, 0.5))
        item = deepcopy(library[op["name"]])
    for key, data in assets.items():
        project.assets.setdefault(key, data)
    for name, asset in item.get("fonts", {}).items():
        fonts = project.state.setdefault("fonts", {})
        if name not in fonts and asset in project.assets:
            fonts[name] = asset
    for key, values in item.get("resources", {}).items():
        target = project.state.setdefault(key, {})
        for name, value in values.items():
            target.setdefault(name, deepcopy(value))
    layers = item["layers"]
    old_root = next(layer for layer in layers if layer["id"] == item["root"])
    mapping = {layer["id"]: uid("lyr") for layer in layers}
    if op.get("name_as"):
        root_name = unique_name(project, op["name_as"])
    else:
        root_name = default_name(project, op["name"])
    scale = finite(op.get("scale", 1), "scale", 0.0001, 100)
    if "width" in op or "height" in op:
        require(not ("width" in op and "height" in op), "Give width or height (the aspect ratio is kept), not both",
                field="width")
        scale = (op["width"] / old_root["width"]) if "width" in op else (op["height"] / old_root["height"])
        finite(scale, "scale", 0.0001, 100)
    root = None
    for layer in layers:
        old = layer["id"]
        layer["id"] = mapping[old]
        if old == item["root"]:
            layer["name"] = root_name
            layer.pop("parent", None)
            layer["x"], layer["y"] = op.get("x", layer["x"]), op.get("y", layer["y"])
            layer["width"] = max(1, layer["width"] * scale)
            layer["height"] = max(1, layer["height"] * scale)
            layer["constraints"] = {}
            root = layer
        else:
            suffix = layer["name"]
            prefix = old_root["name"] + "/"
            if suffix.startswith(prefix):
                suffix = suffix[len(prefix):]
            layer["name"] = default_name(project, f"{root_name}/{suffix}")
            layer["parent"] = mapping.get(layer.get("parent"))
        if layer.get("clip") in mapping:
            layer["clip"] = mapping[layer["clip"]]
        for anchor, expression in list(layer.get("constraints", {}).items()):
            if isinstance(expression, str):
                layer["constraints"][anchor] = _remap(expression, mapping)
        if layer.get("allow_overlap"):
            layer["allow_overlap"] = [mapping.get(ident, ident) for ident in layer["allow_overlap"]]
        if "character" in layer:
            layer["character"]["parts"] = {p: mapping.get(i, i) for p, i in layer["character"].get("parts", {}).items()}
            for bone in layer["character"].get("bones", {}).values():
                bone["layer"] = mapping.get(bone["layer"], bone["layer"])
        append_layer(project, layer)
    _recolor(project, root, op.get("recolor") or {})
    if op.get("motion", True) and item.get("tracks"):
        from .timeline import _timeline

        timeline = _timeline(project)
        for track in deepcopy(item["tracks"]):
            track["target"] = mapping[track["target"]]
            timeline["tracks"].append(track)
            timeline["duration"] = max(timeline["duration"], max((k.get("time", 0) for k in track.get("keys", [])),
                                                                 default=0))
    project.state["active_layer"] = root["id"]
    return root


def _recolor(project, root, colors):
    if not colors:
        return
    from .design import descendants
    from .render import color as parse

    by_part = {}
    for layer in subtree(project, root["id"]):
        part = part_of(layer)
        if part:
            by_part.setdefault(part["name"], []).append(layer)
    unknown = sorted(set(colors) - set(by_part))
    require(not unknown, f"recolor names part(s) {unknown} the object does not have; parts: "
            f"{', '.join(sorted(by_part)) or 'none'}", field="recolor")
    for name, value in colors.items():
        from .design import resolve_color

        parse(resolve_color(value, project.state))
        for part in by_part[name]:
            ids = descendants(project, part["id"]) | {part["id"]}
            for layer in project.state["layers"]:
                if layer["id"] not in ids:
                    continue
                if layer["type"] in ("shape", "pathfinder"):
                    layer["fill"] = value
                elif layer["type"] in ("text", "solid"):
                    layer["color"] = value


def export_object_document(project, refs, *, padding=None, limits=None):
    """A portable ``.vixl`` document holding only the isolated object(s), cropped to their ink (see
    ``isolated_export``); the same format ``object-place source=`` reads."""
    from .project import Project

    from .spatial import canvas_boxes

    candidate = isolated_export(project, refs, padding=padding)
    roots, keep = candidate._isolated, set(candidate._isolated_keep)
    boxes = canvas_boxes(candidate)
    for ident in roots:
        layer = candidate.layer(ident)
        cursor = layer.get("parent")
        while cursor:
            # Ancestors only carried the object; it becomes top-level where it shows on the page, and their
            # scale is kept in its size.
            if cursor not in roots:
                keep.discard(cursor)
            cursor = candidate.layer(cursor).get("parent")
        if layer.get("parent") and layer["parent"] not in roots:
            x, y, w, h = boxes[ident]
            layer.update(parent=None, x=x, y=y, width=w, height=h, constraints={})
    c = candidate.state["canvas"]
    document = Project(c["width"], c["height"], "transparent", limits=limits or project.limits)
    for key in ("fonts", "font_fallbacks", *RESOURCE_KEYS, "palettes", "variables"):
        if key in project.state:
            document.state[key] = deepcopy(project.state[key])
    document.state["layers"] = deepcopy([layer for layer in candidate.state["layers"] if layer["id"] in keep])
    document.state["active_layer"] = roots[0]
    text = json.dumps(document.state)
    for ref in set(ASSET_REFERENCE.findall(text)):
        if ref in project.assets:
            document.assets[ref] = project.assets[ref]
    tracks = [track for track in (project.state.get("timeline") or {}).get("tracks", []) if track.get("target") in keep]
    if tracks:
        from .timeline import _timeline

        timeline = _timeline(document)
        timeline.update({k: deepcopy(v) for k, v in project.state["timeline"].items()
                         if k in ("duration", "fps", "loop", "loop_mode", "markers")})
        timeline["tracks"] = deepcopy(tracks)
    from .validation import check_state

    check_state(document, document.state)
    document._record([], "Export object")
    return document


# What vixl_export_file passes when an option is left alone; a .vixl object export takes no other options.
EXPORT_DEFAULTS = {"scale": 1, "background": "white", "sampling": "smooth", "svg_policy": "appearance",
                   "color_space": "rgb", "intent": "relative", "black_generation": 1.0, "fill_mode": "flatten",
                   "alpha": "auto", "proof": False, "fillable": False, "overwrite": False}


def portable_bytes(project, options, report=None):
    """The bytes of a portable object ``.vixl`` (``vixl_export_file(isolate=…, path=….vixl)``)."""
    import tempfile

    from .render import view_page

    unknown = sorted(key for key, value in options.items() if key not in ("isolate", "padding", "page")
                     and value is not None and EXPORT_DEFAULTS.get(key, object()) != value)
    require(not unknown, f"A .vixl object export takes isolate, padding and page only; got {', '.join(unknown)}",
            field="path")
    view = view_page(project, options["page"]) if options.get("page") is not None else project
    portable = export_object_document(view, options["isolate"], padding=options.get("padding"))
    with tempfile.TemporaryDirectory(prefix="vixl-object-") as staging:
        staged = Path(staging) / "object.vixl"
        portable.save(staged)
        data = staged.read_bytes()
    if report is not None:
        report["objects"] = [layer["name"] for layer in portable.state["layers"] if not layer.get("parent")]
        report["size"] = [portable.state["canvas"]["width"], portable.state["canvas"]["height"]]
    return data


def isolated_export(project, refs, *, padding=None):
    """A render copy holding only ``refs`` (paths and ``object:KIND`` accepted), moved so their ink, plus
    ``padding`` (default 0), fills a canvas of its own size on a transparent background."""
    from .design_render import viewport
    from .proxy import ink_region, isolated

    candidate = isolated(project, refs)
    region = ink_region(candidate, candidate._isolated, padding=0 if padding is None else padding)
    require(region is not None, "The isolated layers draw nothing; check their visibility", field="isolate")
    x, y, w, h = region
    import math

    left, top = math.floor(x), math.floor(y)
    width, height = max(1, math.ceil(x + w) - left), max(1, math.ceil(y + h) - top)
    viewport(candidate, left, top)
    candidate.state["canvas"].update(width=width, height=height, background="transparent")
    for key in ("size", "bleed", "safe", "physical"):
        candidate.state["canvas"].pop(key, None)
    from .render import LayerCache

    candidate._cache = LayerCache()
    return candidate


# ---------------------------------------------------------------------------------------------------------------
# Exports


def svg_ident(text, used):
    """A unique, valid XML ID from a path or name."""
    base = re.sub(r"[^A-Za-z0-9_.-]+", "-", text).strip("-") or "object"
    if not re.match(r"[A-Za-z_]", base):
        base = "o-" + base
    ident, n = base, 2
    while ident in used:
        ident, n = f"{base}-{n}", n + 1
    used.add(ident)
    return ident


def export_identity(layer, index):
    """``{path, kind?, label?, part?, side?}`` for exporters (object groups and named parts only), or None.
    ``index`` maps layer IDs to the layers being exported."""
    found = record(layer)
    part = part_of(layer)
    if not found and not part:
        return None
    result = {"path": path_of(None, layer, index) or layer["name"]}
    if found:
        result.update(kind=found["kind"], label=found.get("label") or layer["name"])
    if part:
        result.update(part=part["name"], **({"side": part["side"]} if part.get("side") else {}))
    return result


# ---------------------------------------------------------------------------------------------------------------
# Review: a labelled sheet of an object's parts


def exploded(project, group_id, amount=0.35):
    """A render copy where the object's parts and sub-objects move away from its centre by ``amount`` of their
    distance from it, so overlaps and seams show."""
    from copy import copy

    from .spatial import canvas_boxes

    candidate = copy(project)
    candidate.state = deepcopy(project.state)
    boxes = canvas_boxes(candidate)
    group = candidate.layer(group_id)
    gx, gy, gw, gh = boxes[group["id"]]
    cx, cy = gx + gw / 2, gy + gh / 2
    children = _children(candidate.state["layers"])
    for layer in object_parts(candidate, group, children) + sub_objects(candidate, group, children):
        x, y, w, h = boxes[layer["id"]]
        if isinstance(layer.get("x"), (int, float)) and isinstance(layer.get("y"), (int, float)):
            layer["x"] += (x + w / 2 - cx) * amount
            layer["y"] += (y + h / 2 - cy) * amount
            layer["constraints"] = {}
    from .render import LayerCache

    candidate._cache = LayerCache()
    return candidate


def parts_sheet(project, refs, max_width=1024, max_height=1024, *, explode=False, render_options=None):
    """A labelled contact sheet for each object in ``refs``: the assembled object, optionally an exploded view,
    then every part and sub-object alone (the review image for "does this guitar look right?")."""
    from PIL import Image, ImageDraw, ImageFont

    from .proxy import render_preview

    options = dict(render_options or {})
    tiles = []
    for ident in expand_refs(project, refs):
        group = project.layer(ident)
        name = path_of(project, group) or group["name"]
        tiles.append((f"{name} (assembled)", [ident], project))
        if explode and record(group):
            tiles.append((f"{name} (exploded)", [ident], exploded(project, ident)))
        if group["type"] != "group":
            continue
        children = _children(project.state["layers"])
        for layer in object_parts(project, group, children) + sub_objects(project, group, children):
            if layer["visible"]:
                tiles.append((path_of(project, layer) or layer["name"], [layer["id"]], project))
        if not record(group):
            for layer in children.get(group["id"], []):
                if layer["visible"]:
                    tiles.append((layer["name"], [layer["id"]], project))
    require(tiles, "Nothing to show", field="isolate")
    tiles = tiles[:48]
    columns = max(1, min(4, len(tiles)))
    rows = -(-len(tiles) // columns)
    gap, caption = 8, 18
    tile = max(48, min((max_width - gap * (columns + 1)) // columns, (max_height - gap * (rows + 1)) // rows - caption))
    sheet = Image.new("RGBA", (columns * tile + gap * (columns + 1), rows * (tile + caption) + gap * (rows + 1)),
                      (236, 236, 240, 255))
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default(size=12)
    for number, (text, refs_, view) in enumerate(tiles):
        x = gap + (number % columns) * (tile + gap)
        y = gap + (number // columns) * (tile + caption + gap)
        try:
            image = render_preview(view, tile, tile, isolate=refs_, **options).convert("RGBA")
        except VixlError:
            image = Image.new("RGBA", (tile, tile), (255, 255, 255, 255))
        image.thumbnail((tile, tile))
        sheet.alpha_composite(image, (x + (tile - image.width) // 2, y + (tile - image.height) // 2))
        draw.rectangle([x - 1, y - 1, x + tile, y + tile], outline=(200, 200, 208, 255))
        label_text = text if len(text) <= 40 else "…" + text[-39:]
        draw.text((x, y + tile + 3), label_text, fill=(40, 40, 48, 255), font=font)
    return sheet


def compile_command(cmd, args):
    """``vixl object TARGET --kind dog``, ``vixl object part LAYER --part head [--side left]``, ``vixl object unset
    TARGET``, ``vixl object-save TARGET --name N`` and ``vixl object-place NAME [--x X --y Y]``."""
    if cmd not in TYPES:
        return None
    import argparse

    from .commands import Parser

    if cmd == "object":
        action = args[0] if args and args[0] in ("set", "unset", "part") else "set"
        args = args[1:] if args and args[0] in ("set", "unset", "part") else args
        p = Parser(prog=f"vixl object {action}")
        p.add_argument("target")
        if action == "set":
            p.add_argument("--kind")
            p.add_argument("--label")
            p.add_argument("--notes")
            p.add_argument("--references", type=json.loads, help='JSON list [{"url": …, "credit": …}]')
        elif action == "part":
            p.add_argument("--part", required=True)
            p.add_argument("--side", choices=list(SIDES))
        values = {k: v for k, v in vars(p.parse_args(args)).items() if v is not None}
        return {"type": "object", **({"action": action} if action != "set" else {}), **values}
    p = Parser(prog=f"vixl {cmd}")
    if cmd == "object-save":
        p.add_argument("target")
        p.add_argument("--name", required=True)
        p.add_argument("--description")
        p.add_argument("--tags", nargs="*")
    else:
        p.add_argument("name")
        p.add_argument("--source", help="a portable object .vixl file in the workspace")
        p.add_argument("--name-as")
        for key in ("x", "y", "width", "height", "scale"):
            p.add_argument("--" + key, type=float)
        p.add_argument("--recolor", type=json.loads, help="JSON {part: colour}")
        p.add_argument("--motion", action=argparse.BooleanOptionalAction, default=None)
    return {"type": cmd, **{k: v for k, v in vars(p.parse_args(args)).items() if v is not None}}
