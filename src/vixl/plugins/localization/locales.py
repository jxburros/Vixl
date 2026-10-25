"""Locale tables: per-locale variable values on a document or a project group, and strings CSV files.

A document holds ``locales``, ``{code: {variable: value}}``: the values a locale gives the document's variables
(``${headline}`` in a text layer reads ``headline``). ``locale_options`` holds how the locales are checked and
built: the ``source`` locale (default ``en``; its values default to the document's own variables), ``same_ok``
(keys or values that may stay equal to the source, such as a brand name), per-locale font ``fonts`` (fallback
font names added in front of the document's ``font-fallbacks``), the text ``fit`` policy (``shrink`` or ``flag``,
for every text layer or per layer name) with its ``min_size``, ``rtl`` (the locales mirrored right to left;
default the ``ar``, ``he`` and ``fa`` locales) and ``mirror`` (false turns mirroring off).

A project group (``.vixl-groups/NAME.json``) may hold ``locales`` too; a document's own values win over its
groups'. A strings CSV has one row per key and one column per locale; an empty cell is a missing key.

The keys of a locale table are the union of every locale's keys. A locale that lacks one of them is missing that
key: the check reports it, and ``localize`` holds the locale.
"""

from copy import deepcopy
from pathlib import Path
import re

from ...errors import VixlError, require

TYPES = ("locales-set",)
CODE = re.compile(r"^[a-z]{2,3}(-[A-Za-z0-9]{1,8}){0,3}$")
KEY = re.compile(r"^[\w-]+$")
RTL = ("ar", "he", "fa")
FIT = ("shrink", "flag")
DEFAULT_SOURCE = "en"
DEFAULT_MIN_SIZE = 12
MAX_LOCALES = 100
MAX_KEYS = 2000
MAX_VALUE = 10000
OPTIONS = ("source", "same_ok", "fonts", "fit", "min_size", "rtl", "mirror")
SCALAR = ("string", "number", "boolean")


def schemas(add):
    from ...schema import B, field

    code = {"type": "string", "pattern": CODE.pattern}
    fields = {
        "locales": {"type": "object", "maxProperties": MAX_LOCALES,
                    "description": "Locale tables merged into the document: {locale code: {variable: value}}, such as "
                                   "{\"de\": {\"headline\": \"Neu\"}}. A null value removes that key, a null table "
                                   "removes the locale.",
                    "additionalProperties": {"type": ["object", "null"], "maxProperties": MAX_KEYS,
                                             "description": "One locale's variable values.",
                                             "additionalProperties": {"type": [*SCALAR, "null"],
                                                                      "description": "The variable's value in this "
                                                                                     "locale; null removes it."}}},
        "replace": field(B, "Replace the whole locale table instead of merging into it (default false)."),
        "source": {**code, "description": "The source locale the others are compared with (default en). Its values "
                                          "default to the document's variables."},
        "same_ok": {"type": "array", "maxItems": MAX_KEYS, "items": {"type": "string"},
                    "description": "Keys (or values) that may stay equal to the source without counting as "
                                   "untranslated, such as a brand or product name."},
        "fonts": {"type": "object", "maxProperties": MAX_LOCALES,
                  "description": "Per-locale font fallbacks: {locale code: [registered font names]}, tried before "
                                 "the document's font-fallbacks when that locale is checked or built.",
                  "additionalProperties": {"type": "array", "maxItems": 16, "items": {"type": "string"},
                                           "description": "Font names (font import or font-register) in order."}},
        "fit": {"type": ["string", "object"],
                "description": "Text that does not fit in a locale: shrink (fit-text down to min_size) or flag "
                               "(report it; the default), for every text layer, or {layer name: shrink|flag, "
                               "\"*\": default}."},
        "min_size": {"type": "integer", "minimum": 1, "maximum": 4096,
                     "description": "Smallest font size shrink may set, in pixels (default 12)."},
        "rtl": {"type": "array", "maxItems": MAX_LOCALES, "items": code,
                "description": "Locales laid out right to left and mirrored (default: the ar, he and fa locales)."},
        "mirror": field(B, "Mirror the layout of right-to-left locales (default true)."),
    }
    for key in OPTIONS:  # null removes an option
        fields[key] = {**fields[key], "type": [*([fields[key]["type"]] if isinstance(fields[key]["type"], str)
                                                 else fields[key]["type"]), "null"]}
    add("locales-set", fields)


def execute(project, op):
    state = project.state
    if "locales" in op:
        table = {} if op.get("replace") else deepcopy(state.get("locales", {}))
        for code, values in op["locales"].items():
            code = canonical_code(code, "locales")
            if values is None:
                table.pop(code, None)
                continue
            entry = table.setdefault(code, {})
            for key, value in values.items():
                if value is None:
                    entry.pop(key, None)
                else:
                    entry[key] = value
        if table:
            state["locales"] = table
        else:
            state.pop("locales", None)
    else:
        require(not op.get("replace"), "replace needs locales", field="replace")
    options = dict(state.get("locale_options", {}))
    for key in OPTIONS:
        if key in op:
            if op[key] is None:
                options.pop(key, None)
            else:
                options[key] = deepcopy(op[key])
    if "source" in options:
        options["source"] = canonical_code(options["source"], "source")
    if "rtl" in options:
        options["rtl"] = [canonical_code(code, "rtl") for code in options["rtl"]]
    if "fonts" in options:
        options["fonts"] = {canonical_code(code, "fonts"): names for code, names in options["fonts"].items()}
    if options:
        state["locale_options"] = options
    else:
        state.pop("locale_options", None)
    validate(project, state, code="invalid_operation")


def canonical_code(value, field="locale"):
    """A locale code as written in tables: ``de``, ``pt-BR``, ``zh-Hant`` (underscores become hyphens)."""
    require(isinstance(value, str), f"{field}: a locale code is a string such as de or pt-BR", field=field)
    parts = value.strip().replace("_", "-").split("-")
    code = "-".join([parts[0].lower(), *parts[1:]])
    require(CODE.fullmatch(code), f"{field}: {value!r} is not a locale code such as de, ja or pt-BR", field=field)
    return code


def primary(code):
    return code.split("-")[0]


def validate_table(table, where="locales", code="invalid_project"):
    require(isinstance(table, dict) and len(table) <= MAX_LOCALES,
            f"{where} is {{locale code: {{variable: value}}}} with at most {MAX_LOCALES} locales", code, field=where)
    for locale, values in table.items():
        require(isinstance(locale, str) and CODE.fullmatch(locale), f"{where}: {locale!r} is not a locale code",
                code, field=where)
        require(isinstance(values, dict) and len(values) <= MAX_KEYS,
                f"{where}.{locale} is {{variable: value}} with at most {MAX_KEYS} keys", code, field=where)
        for key, value in values.items():
            require(isinstance(key, str) and KEY.fullmatch(key),
                    f"{where}.{locale}: {key!r} is not a variable name (letters, digits, _ and -)", code, field=where)
            require(isinstance(value, (str, int, float, bool)), f"{where}.{locale}.{key} must be a scalar value",
                    code, field=where)
            require(not isinstance(value, str) or len(value) <= MAX_VALUE,
                    f"{where}.{locale}.{key} is longer than {MAX_VALUE} characters", code, field=where)


def validate_options(options, code="invalid_project"):
    require(isinstance(options, dict) and set(options) <= set(OPTIONS),
            f"locale_options takes {', '.join(OPTIONS)}", code, field="locale_options")
    for key in ("source",):
        if key in options:
            require(isinstance(options[key], str) and CODE.fullmatch(options[key]),
                    f"{key} is a locale code", code, field=key)
    same = options.get("same_ok", [])
    require(isinstance(same, list) and all(isinstance(item, str) for item in same) and len(same) <= MAX_KEYS,
            "same_ok is a list of keys or values", code, field="same_ok")
    rtl = options.get("rtl", [])
    require(isinstance(rtl, list) and all(isinstance(c, str) and CODE.fullmatch(c) for c in rtl),
            "rtl is a list of locale codes", code, field="rtl")
    fonts = options.get("fonts", {})
    require(isinstance(fonts, dict) and all(
        isinstance(c, str) and CODE.fullmatch(c) and isinstance(names, list) and len(names) <= 16
        and all(isinstance(n, str) and n for n in names) for c, names in fonts.items()),
        "fonts is {locale code: [font names]}", code, field="fonts")
    validate_fit(options.get("fit", "flag"), code)
    size = options.get("min_size", DEFAULT_MIN_SIZE)
    require(type(size) is int and 1 <= size <= 4096, "min_size is a font size in pixels from 1 to 4096", code,
            field="min_size")
    require(type(options.get("mirror", True)) is bool, "mirror must be true or false", code, field="mirror")


def validate_fit(fit, code="invalid_operation"):
    if isinstance(fit, str):
        require(fit in FIT, f"fit is {' or '.join(FIT)}, or {{layer name: policy}}", code, field="fit",
                allowed=list(FIT))
        return
    require(isinstance(fit, dict) and len(fit) <= 1000 and all(
        isinstance(k, str) and v in FIT for k, v in fit.items()),
        "fit is shrink or flag, or {layer name: shrink|flag, \"*\": default}", code, field="fit", allowed=list(FIT))


def validate(project, state, code="invalid_project"):
    if "locales" in state:
        validate_table(state["locales"], code=code)
    if "locale_options" in state:
        validate_options(state["locale_options"], code)


def options(project, overrides=None):
    """The document's locale options with request ``overrides`` (already validated) on top."""
    merged = dict(project.state.get("locale_options", {}))
    for key, value in (overrides or {}).items():
        if key in OPTIONS and value is not None:
            merged[key] = value
    validate_options(merged, "invalid_request")
    return merged


def is_rtl(code, opts):
    listed = opts.get("rtl")
    return code in listed if listed is not None else primary(code) in RTL


def fit_policy(opts, layer):
    fit = opts.get("fit", "flag")
    if isinstance(fit, str):
        return fit
    return fit.get(layer.get("name"), fit.get(layer.get("id"), fit.get("*", "flag")))


# ------------------------------------------------------------------------------------------------ groups


def group_locales(project):
    """``{code: {key: value}}`` from the project groups the document belongs to (in name order; earlier
    groups win), and the group names."""
    from ...assurance import document_key
    from ...production import read_json

    workspace = getattr(project, "_workspace", None)
    key = document_key(project)
    directory = Path(workspace) / ".vixl-groups" if workspace else None
    if not key or directory is None or not directory.is_dir():
        return {}, []
    merged, names = {}, []
    for path in sorted(directory.glob("*.json")):
        if path.name.endswith(".transaction.json"):
            continue
        try:
            group = read_json(path)
        except VixlError:
            continue
        if key not in group.get("documents", []) or not group.get("locales"):
            continue
        try:
            validate_table(group["locales"], f"group {group.get('name')} locales")
        except VixlError:
            continue
        names.append(group.get("name", path.stem))
        for code, values in group["locales"].items():
            for name, value in values.items():
                merged.setdefault(code, {}).setdefault(name, value)
    return merged, names


def set_group_locales(session, request):
    """The ``group-locales`` workflow action: merge (or ``replace``) a locale table into a group record."""
    from ...design import named
    from ...fileio import file_lock
    from ...production import read_json, write_json

    name = named(request["name"])
    path = session.resolve(f".vixl-groups/{name}.json")
    require(path.is_file(), f"Unknown project group {name!r}; define it with group-define first", "not_found",
            field="name")
    table = request.get("locales", {})
    require(isinstance(table, dict), "locales is {locale code: {variable: value}}", field="locales")
    with session._mutex, file_lock(str(path)):
        group = read_json(path)
        current = {} if request.get("replace") else deepcopy(group.get("locales", {}))
        for code, values in table.items():
            code = canonical_code(code, "locales")
            if values is None:
                current.pop(code, None)
                continue
            require(isinstance(values, dict), f"locales.{code} is {{variable: value}}", field="locales")
            entry = current.setdefault(code, {})
            for key, value in values.items():
                if value is None:
                    entry.pop(key, None)
                else:
                    entry[key] = value
        validate_table(current, code="invalid_request")
        if current:
            group["locales"] = current
        else:
            group.pop("locales", None)
        write_json(path, group)
    return {"group": name, "locales": sorted(current), "keys": len(keys(current))}


# ------------------------------------------------------------------------------------------------ CSV


def load_strings(path, *, key_column="key", languages=None):
    """A strings CSV: one row per key and one column per locale. Returns ``{"locales": {code: {key: value}},
    "keys": [...], "languages": [...], "missing": [{key, locale, row}]}``; an empty cell is a missing key. Without
    ``languages`` every column other than the key column whose header is a locale code is a language."""
    from ...exports import read_csv

    headers, rows = read_csv(path, MAX_KEYS)
    require(isinstance(key_column, str) and key_column in headers,
            f"The strings CSV has no {key_column!r} column; its columns: {', '.join(headers)}", "invalid_data",
            field="key_column", suggestions=list(headers))
    columns = {}
    if languages is not None:
        require(isinstance(languages, list) and languages and all(isinstance(c, str) for c in languages),
                "languages is a list of locale columns", field="languages")
        for column in languages:
            require(column in headers, f"The strings CSV has no {column!r} column", "invalid_data", field="languages",
                    suggestions=[h for h in headers if h != key_column])
            columns[column] = canonical_code(column, "languages")
    else:
        for column in headers:
            if column == key_column:
                continue
            try:
                columns[column] = canonical_code(column, "languages")
            except VixlError:
                continue  # A notes or context column.
    require(columns, "The strings CSV has no locale columns (headers such as de, ja or pt-BR)", "invalid_data",
            field="languages")
    require(len(columns) <= MAX_LOCALES, f"A strings CSV holds at most {MAX_LOCALES} locales", "resource_limit")
    table = {code: {} for code in columns.values()}
    found, missing = [], []
    for number, row in enumerate(rows, 2):
        key = row[key_column].strip()
        require(key, f"Row {number} of the strings CSV has an empty {key_column!r}", "invalid_data", row=number)
        require(KEY.fullmatch(key), f"Row {number}: {key!r} is not a variable name (letters, digits, _ and -)",
                "invalid_data", row=number)
        require(key not in found, f"Row {number}: the key {key!r} is listed twice", "invalid_data", row=number)
        found.append(key)
        for column, code in columns.items():
            value = row[column]
            if value.strip():
                require(len(value) <= MAX_VALUE, f"Row {number}: the {column} value is too long", "invalid_data")
                table[code][key] = value
            else:
                missing.append({"key": key, "locale": code, "row": number})
    return {"locales": table, "keys": found, "languages": list(columns.values()), "missing": missing}


# ------------------------------------------------------------------------------------------------ tables


def keys(table):
    found = {}
    for values in table.values():
        for key in values:
            found.setdefault(key, None)
    return list(found)


def locale_table(project, strings=None, opts=None):
    """``(table, sources)``: the locale table a check or build uses. Group values, then the document's, then a
    strings CSV (``load_strings`` result) win in that order. The source locale is always present: its values
    default to the document's variables for every key."""
    opts = opts if opts is not None else options(project)
    groups, group_names = group_locales(project)
    table = deepcopy(groups)
    for code, values in project.state.get("locales", {}).items():
        table.setdefault(code, {}).update(deepcopy(values))
    sources = {"groups": group_names, "document": bool(project.state.get("locales"))}
    if strings is not None:
        for code, values in strings["locales"].items():
            table.setdefault(code, {}).update(values)
        sources["strings"] = strings.get("path")
    source = opts.get("source", DEFAULT_SOURCE)
    variables = project.state.get("variables", {})
    base = table.setdefault(source, {})
    for key in keys(table):
        if key not in base and key in variables:
            base[key] = variables[key]
    return table, sources


def missing_keys(table, code, strings=None):
    """The keys of the table that locale ``code`` lacks, plus the CSV cells left empty for it."""
    all_keys = keys(table)
    missing = [key for key in all_keys if key not in table.get(code, {})]
    for item in (strings or {}).get("missing", []):
        if item["locale"] == code and item["key"] not in missing:
            missing.append(item["key"])
    return missing


def select(value, table, source):
    """The locales a request names: ``all`` (every locale but the source), a comma-separated string or a list."""
    available = [code for code in table if code != source]
    if value in (None, "all", ["all"]):
        require(available, "No locales to check: add them with locales-set, group-locales or a strings CSV",
                field="locales")
        return available
    if isinstance(value, str):
        value = [part for part in value.split(",") if part.strip()]
    require(isinstance(value, list) and value and all(isinstance(v, str) for v in value),
            "locales is all, a comma-separated list such as de,ja, or a list of codes", field="locales")
    codes = []
    for item in value:
        code = canonical_code(item, "locales")
        require(code in table, f"Unknown locale {code!r}; the document has: {', '.join(table) or 'none'}",
                field="locales", suggestions=list(table))
        if code not in codes:
            codes.append(code)
    return codes
