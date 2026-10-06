"""Merge fields: ``${name}`` placeholders with optional filters, ``${name|filter:arg|...}``.

Text, image assets, colours, link variables and imposition templates all substitute through
``substitute`` so every renderer and check reads the same values. Filters run left to right:

- ``upper``, ``lower``, ``title``: change the case.
- ``default:TEXT``: TEXT when the variable is undefined or empty (an undefined variable without a
  default is an error).
- ``map:NAME``: look the value up in the document's ``maps[NAME]`` (``variable-map`` edits them); a
  map's ``"*"`` entry is used for values it does not list, otherwise an unmapped value is an error.
- ``number[:DECIMALS]``: a number with thousands separators (``1234.5|number:2`` is ``1,234.50``).
- ``format:SPEC``: a Python format spec applied to the number (``format:08.3f``) or, for text, to
  the string (``format:>10``).

Variable names are ``[\\w-]+``; an argument runs to the next ``|`` or ``}``.
"""

import math
import re

from .errors import VixlError, require

NAME = re.compile(r"[\w-]+")
PLACEHOLDER = re.compile(r"\$\{([\w-]+)((?:\|[^|{}]*)*)\}")
FILTERS = {"upper": False, "lower": False, "title": False, "default": True, "map": True, "number": None, "format": True}
# Maps travel with the variables under a key no ${name} can spell, so merged dicts keep them.
MAPS = "|maps"
MAX_MAPS, MAX_MAP_ENTRIES = 64, 1000


def parse_filters(spec):
    """[(filter, argument or None)] from the ``|...`` tail of a placeholder."""
    result = []
    for part in spec.split("|")[1:]:
        name, colon, argument = part.partition(":")
        name = name.strip()
        require(name in FILTERS, f"Unknown variable filter {name!r}; use {', '.join(FILTERS)}", "invalid_filter",
                field="text", suggestions=list(FILTERS))
        needs = FILTERS[name]
        require(not (needs is True and not colon), f"The {name} filter needs an argument ({name}:...)", "invalid_filter",
                field="text")
        require(not (needs is False and colon), f"The {name} filter takes no argument", "invalid_filter", field="text")
        result.append((name, argument if colon else None))
    return result


def placeholders(text):
    """Each placeholder in a string: {placeholder, name, filters: [{filter, argument}]}."""
    if not isinstance(text, str) or "${" not in text:
        return []
    found = []
    for match in PLACEHOLDER.finditer(text):
        filters = parse_filters(match[2])
        found.append({"placeholder": match[0], "name": match[1],
                      "filters": [{"filter": f, **({"argument": a} if a is not None else {})} for f, a in filters]})
    return found


def names(text):
    """The variable names a string uses (base names, filters stripped)."""
    return [match[1] for match in PLACEHOLDER.finditer(text)] if isinstance(text, str) else []


def required_names(text):
    """The names a string needs defined: those without a ``default`` filter."""
    if not isinstance(text, str):
        return []
    return [m[1] for m in PLACEHOLDER.finditer(text) if not any(f == "default" for f, _ in parse_filters(m[2]))]


def with_maps(variables, maps):
    """The variables with the document's maps attached for ``map:`` filters."""
    return {**variables, MAPS: maps or {}} if maps else variables


def _number(value, name):
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value
    try:
        text = str(value).replace(",", "").strip()
        return int(text) if re.fullmatch(r"[+-]?\d+", text) else float(text)
    except ValueError:
        raise VixlError("invalid_variable", f"Variable {name!r} is {value!r}, not a number", field="text") from None


def _apply(name, value, filters, maps):
    missing = value is None
    text = "" if missing else value
    for kind, argument in filters:
        if kind == "default":
            if missing or text == "":
                text, missing = argument, False
            continue
        if missing:
            continue
        if kind == "upper":
            text = str(text).upper()
        elif kind == "lower":
            text = str(text).lower()
        elif kind == "title":
            text = str(text).title()
        elif kind == "map":
            table = maps.get(argument)
            require(table is not None, f"Unknown map {argument!r} in ${{{name}|map:{argument}}}", "missing_map",
                    field="text", suggestions=sorted(maps))
            key = str(text)
            require(key in table or "*" in table, f"Map {argument!r} has no entry for {key!r} (add it, or a '*' entry)",
                    "missing_map_entry", field="text")
            text = table.get(key, table.get("*"))
        elif kind == "number":
            number = _number(text, name)
            decimals = 0 if argument is None and float(number).is_integer() else argument
            if decimals is None:
                text = f"{number:,}"
            else:
                require(re.fullmatch(r"\d{1,2}", str(decimals)), "number takes a decimal count 0-99", "invalid_filter",
                        field="text")
                text = f"{number:,.{int(decimals)}f}"
        elif kind == "format":
            try:
                subject = _number(text, name)
            except VixlError:
                subject = str(text)
            try:
                text = format(subject, argument)
            except (ValueError, TypeError) as exc:
                raise VixlError("invalid_filter", f"format:{argument} cannot format {text!r}: {exc}",
                                field="text") from None
    require(not missing, f"Undefined variable: {name}", "missing_variable")
    return str(text)


def substitute(value, variables):
    """``value`` with every placeholder filled from ``variables`` (non-strings pass through)."""
    if not isinstance(value, str) or "${" not in value:
        return value
    maps = variables.get(MAPS) or {}

    def replace(match):
        return _apply(match[1], variables.get(match[1]), parse_filters(match[2]), maps)

    return PLACEHOLDER.sub(replace, value)


def strings(value):
    """Every string inside a JSON-like value."""
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from strings(item)


def validate_maps(maps):
    require(isinstance(maps, dict) and len(maps) <= MAX_MAPS, f"maps holds at most {MAX_MAPS} named maps", "invalid_project")
    for name, table in maps.items():
        require(isinstance(name, str) and NAME.fullmatch(name), f"Invalid map name {name!r}", field="name")
        require(isinstance(table, dict) and 0 < len(table) <= MAX_MAP_ENTRIES,
                f"Map {name!r} needs 1 to {MAX_MAP_ENTRIES} entries", field="values")
        for key, item in table.items():
            require(isinstance(key, str) and len(key) <= 1000 and isinstance(item, (str, int, float, bool))
                    and (not isinstance(item, float) or math.isfinite(item)) and len(str(item)) <= 10000,
                    f"Map {name!r} maps text to short text or numbers", field="values")


def validate_state(state):
    """Maps are well formed, and every filtered placeholder names known filters and defined maps."""
    maps = state.get("maps", {})
    validate_maps(maps)
    for key in ("layers", "swatches", "character_styles", "paragraph_styles", "canvas", "pages", "masters"):
        for text in strings(state.get(key)):
            if "${" not in text or "|" not in text:
                continue
            for item in placeholders(text):
                for spec in item["filters"]:
                    if spec["filter"] == "map":
                        require(spec["argument"] in maps, f"{item['placeholder']} uses the undefined map "
                                f"{spec['argument']!r}; define it with variable-map", "missing_map", field="text",
                                suggestions=sorted(maps))


def execute_map(project, op):
    """``variable-map``: define, replace, extend or delete a named value map."""
    name = op["name"]
    require(isinstance(name, str) and NAME.fullmatch(name), f"Invalid map name {name!r}", field="name")
    maps = project.state.setdefault("maps", {})
    if op.get("delete"):
        require(name in maps, f"No map named {name!r}", "not_found", field="name", suggestions=sorted(maps))
        del maps[name]
        if not maps:
            project.state.pop("maps")
        return
    values = op.get("values")
    require(isinstance(values, dict) and values, "variable-map needs values: {text: replacement}", field="values",
            suggestions=[{"name": name, "values": {"NY": "New York", "*": "Elsewhere"}}])
    table = {**maps.get(name, {}), **values} if op.get("merge") else dict(values)
    maps[name] = {str(k): v for k, v in table.items()}
    validate_maps(maps)


def listing(project):
    """Every placeholder the document draws: where it is, its name and filters, and whether it resolves."""
    from .render import document_variables

    known = document_variables(project)
    result = []
    for layer in project.state.get("layers", []):
        for field in ("text", "asset", "color", "fill", "start", "end", "stroke", "stroke_color"):
            for item in placeholders(layer.get(field)):
                defaulted = any(f["filter"] == "default" for f in item["filters"])
                result.append({"layer": layer["id"], "layer_name": layer["name"], "field": field, **item,
                               "defined": item["name"] in known or defaulted})
        for name, value in (layer.get("variables") or {}).items() if layer.get("type") == "link" else ():
            for item in placeholders(value):
                result.append({"layer": layer["id"], "layer_name": layer["name"], "field": f"variables.{name}", **item,
                               "defined": item["name"] in known
                               or any(f["filter"] == "default" for f in item["filters"])})
    return result
