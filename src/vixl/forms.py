"""Form fields: fillable PDF forms, and filling Vixl-designed forms with data.

A field is a layer (``type: "field"``) that moves, aligns, groups and checks like any other. Its
``field`` record holds the data key, kind and rules; ``appearance`` is the box Vixl draws into the
artwork; ``font``, ``size``, ``color``, ``align`` and ``padding`` draw its value.

Every render shows each field's current value: its default, or a filled value on a throwaway
copy of the document (``with_values``). Filled values are personal data, so they never reach
the document, its history or the persistent render cache, and error messages name rows and keys
but never values. Field values are also ``${key}`` variables in text layers.

``pdf_forms`` writes the fillable PDF; this module owns the model, validation, tab order,
values, drawing, the ``form`` checks and filling.
"""

from copy import deepcopy
import datetime
from functools import lru_cache
import io
import math
from pathlib import Path
import re

from .errors import VixlError, require
from .form_rules import EMAIL, MAX_MESSAGE, MAX_PATTERN, check_pattern, date_picture, pattern_matches
from .model import finite, new_layer

TYPES = ("field", "field-set", "form")
KINDS = ("text", "multiline", "number", "date", "checkbox", "radio", "dropdown", "signature")
KIND_ALIASES = {"textbox": "text", "textarea": "multiline", "select": "dropdown", "combo": "dropdown",
                "combobox": "dropdown", "tickbox": "checkbox", "check": "checkbox", "radio-button": "radio",
                "input": "text", "email": "text", "numeric": "number"}
TEXT_KINDS = ("text", "multiline", "number", "date")
STYLES = ("box", "underline", "none")
MARKS = ("check", "cross", "dot")
OVERFLOW = ("shrink", "clip", "error")
MAX_FIELDS = 500
MAX_OPTIONS = 200
MAX_LABEL = 500
MAX_VALUE = 10000
KEY = re.compile(r"[\w-]{1,64}")
FIELD_SETTINGS = ("key", "kind", "label", "tooltip", "label_layer", "group_label", "required", "read_only", "default", "max_length",
                  "comb", "format", "pattern", "message", "options", "editable", "option", "on_value", "tab", "overflow",
                  "min_size")
APPEARANCE = ("style", "fill", "stroke", "stroke_width", "radius", "mark", "mark_color")
VALUE_STYLE = ("font", "size", "color", "align", "padding")
FORM_SETTINGS = ("tab_order", "entry_font", "title", "lang")
ERROR_CODES = ("missing_required", "unknown_key", "invalid_option", "invalid_number", "invalid_date", "too_long",
               "invalid_format", "overflow")
MARK_PATHS = {
    "check": "M 20 54 L 42 76 L 80 26",
    "cross": "M 25 25 L 75 75 M 75 25 L 25 75",
}


# ---------------------------------------------------------------------------------------------
# Units and records


def px_per_pt(state):
    dpi = state["canvas"].get("dpi")
    return dpi / 72 if dpi else 1.0


def is_field(layer):
    return layer.get("type") == "field"


def all_fields(project, state=None):
    """Every field layer in the document: the active page's, inactive pages' and masters'.
    Returns [(page record or None, layer)]."""
    if state is None:
        # A page view reads the whole document it was made from.
        project = getattr(project, "_document", None) or project
        state = project.state
    found = [(None, layer) for layer in state.get("layers", []) if is_field(layer)]
    for page in state.get("pages") or []:
        for layer in (page.get("content") or {}).get("layers", []):
            if is_field(layer):
                found.append((page, layer))
    return found


def has_fields(project):
    state = (getattr(project, "_document", None) or project).state
    if any(layer["type"] == "field" for layer in state.get("layers", [])):
        return True
    return any(layer["type"] == "field" for page in state.get("pages") or []
               for layer in (page.get("content") or {}).get("layers", []))


def form_settings(state):
    return {"tab_order": "reading", "entry_font": "standard", **(state.get("form") or {})}


# ---------------------------------------------------------------------------------------------
# Operations


def schemas(add):
    # Types and prose for every setting, so agents can build forms from vixl_operation_schema alone.
    # Cross-field rules (which kinds take which settings) are checked at run time (validate_field);
    # tools/list strips the descriptions to keep the inline catalog small.
    from .schema import COORD, SIZE

    S, INT, B, N = {"type": "string"}, {"type": "integer"}, {"type": "boolean"}, {"type": "number"}

    def d(schema, text):
        return {**schema, "description": text}

    def nullable(schema):
        # field-set and form clear a setting given null.
        schema = deepcopy(schema)
        if "anyOf" in schema:
            schema["anyOf"].append({"type": "null"})
        else:
            schema["type"] = [schema["type"], "null"] if isinstance(schema["type"], str) else [*schema["type"], "null"]
            if "enum" in schema:
                schema["enum"] = [*schema["enum"], None]
        return schema

    settings = {
        "kind": d({"type": "string", "enum": list(KINDS)}, "Field kind."),
        "key": d(S, "Data key used by fills and CSV columns: 1–64 letters, digits, _ or - (default: from name)."),
        "label": d(S, f"Accessible name, up to {MAX_LABEL} characters (label or label_layer is required)."),
        "tooltip": d(S, f"Accessible name (PDF tooltip) used as given, up to {MAX_LABEL} characters; by default it is the "
                        "label with required markers such as a trailing * removed."),
        "label_layer": d(S, "ID or name of a text layer whose text names the field."),
        "group_label": d(S, "Radio only: accessible name of the radio group."),
        "required": d(B, "The value must be filled. A required signature is flagged for the viewer and signed there."),
        "read_only": d(B, "Locked in the fillable PDF."),
        "default": d({"type": ["string", "number", "boolean"]}, "Initial value (checkbox: true/false)."),
        "max_length": d(INT, f"Text, multiline and number: maximum characters, 1–{MAX_VALUE}."),
        "comb": d(B, "Text with max_length only: one box per character."),
        "format": d({"anyOf": [{"type": "string", "enum": ["email", "digits"]}, {"type": "object"}]},
                    "Text: 'email' or 'digits'; number: {decimals, min, max}; date: {display: 'DD/MM/YYYY'}. "
                    "A fillable PDF enforces it in the viewer."),
        "pattern": d(S, f"Text only: a regular expression the whole value must match (up to {MAX_PATTERN} characters; "
                     "classes, groups, alternation and {n,m} counts; no flags, look-around or back-references). "
                     "A fillable PDF enforces it in the viewer."),
        "message": d(S, f"Text shown when a value breaks the email, digits, pattern or number-range rule, up to "
                     f"{MAX_MESSAGE} characters."),
        "options": d({"type": "array", "items": {"type": ["string", "object"]}},
                     f"Dropdown only: 1–{MAX_OPTIONS} choices as strings or {{value, label}}."),
        "editable": d(B, "Dropdown only: allow typed values outside options."),
        "option": d(S, "Radio only: this button's export value (radios sharing a key form a group)."),
        "on_value": d(S, "Checkbox only: export value when checked (default 'Yes')."),
        "tab": d(INT, "Position 1–10000 in the explicit tab order."),
        "overflow": d({"type": "string", "enum": list(OVERFLOW)}, "Text kinds: what a too-long value does."),
        "min_size": d(N, "Smallest font size shrink may use."),
        "font": d(S, "Value font: a font role (body, heading) or family."),
        "size": d(N, "Value font size in pixels."),
        "color": d(S, "Value text color."),
        "align": d({"type": "string", "enum": ["left", "center", "right"]}, "Value alignment."),
        "padding": d(N, "Inner padding in pixels."),
        "appearance": d({"type": "object"}, "Box look: {style: box|underline|none, fill, stroke, stroke_width, "
                        "radius, mark: check|cross|dot, mark_color}. fill/stroke/… may also be given top-level."),
    }
    add("field", {"name": d(S, "Layer name."), **settings, "x": COORD, "y": COORD, "width": SIZE, "height": SIZE},
        ["kind"])
    add("field-set", {"target": d(S, "Field layer ID or name."), "kind": settings["kind"],
                      **{k: nullable(v) for k, v in settings.items() if k != "kind"}}, ["target"])
    add("form", {k: nullable(v) for k, v in {
        "tab_order": d({"type": "string", "enum": ["reading", "explicit"]}, "Tab order: reading or by tab."),
        "entry_font": d({"type": "string", "enum": ["standard", "embed"]},
                        "Font viewers use for typed entries in a fillable PDF: standard (Helvetica) or embed "
                        "(each field's own font, Western European characters)."),
        "title": d(S, "PDF document title."), "lang": d(S, "Document language tag such as 'en-GB'.")}.items()}, [])


def normalize(op, note):
    """Kind aliases and top-level appearance settings (``fill``, ``stroke`` …) for field ops."""
    kind = op.get("kind")
    if isinstance(kind, str) and kind not in KINDS:
        canonical = KIND_ALIASES.get(kind.lower().replace("_", "-"))
        if canonical:
            note(f"kind {kind!r} → {canonical!r}")
            op["kind"] = canonical
            if kind.lower() == "email" and "format" not in op:
                op["format"] = "email"
    moved = [key for key in APPEARANCE if key in op]
    if moved:
        op["appearance"] = {**(op.get("appearance") or {}), **{key: op.pop(key) for key in moved}}
        note(f"{', '.join(moved)} → appearance")
    return op


def default_geometry(state, kind, size, padding):
    unit = px_per_pt(state)
    c = state["canvas"]
    if kind in ("checkbox", "radio"):
        side = max(8, round(14 * unit))
        return side, side
    if kind == "multiline":
        return round(c["width"] * 0.5), round(size * 1.25 * 4 + 2 * padding)
    if kind == "signature":
        return round(min(c["width"] * 0.45, 216 * unit)), round(max(size * 3, 36 * unit))
    width = round(c["width"] * (0.25 if kind in ("number", "date") else 0.4))
    return width, round(size * 1.5 + 2 * padding)


def execute(project, op):
    from .operations import append_layer, default_name, embed_font_file, unique_name
    from .render import resolve_font

    state = project.state
    kind = op["type"]
    if kind == "form":
        settings = state.setdefault("form", {})
        for key in FORM_SETTINGS:
            if key in op:
                if op[key] in (None, ""):
                    settings.pop(key, None)
                else:
                    settings[key] = op[key]
        validate_settings(settings)
        if not settings:
            state.pop("form", None)
        return
    if kind == "field":
        require(op["kind"] in KINDS, f"kind must be one of {', '.join(KINDS)}", field="kind")
        require(op.get("label") or op.get("label_layer"),
                "A field needs an accessible name: label (or label_layer, a text layer whose text names it)",
                field="label")
        name = unique_name(project, op["name"]) if "name" in op else default_name(project, op.get("key") or op["kind"])
        unit = px_per_pt(state)
        size = op.get("size", round(11 * unit) if state["canvas"].get("dpi") else 16)
        padding = op.get("padding", round(size * 0.4))
        width, height = default_geometry(state, op["kind"], size, padding)
        width, height = op.get("width", width), op.get("height", height)
        font, role = resolve_font(project, op.get("font", "body"))
        record = {"key": op.get("key") or _key_from(name), "kind": op["kind"]}
        layer = new_layer(name, "field", width, height, field=record, font=font, size=size,
                          color=op.get("color", "#1f2328"), align=op.get("align", "left"), padding=padding,
                          appearance=default_appearance(state, op["kind"]))
        if role:
            layer["font_role"] = role
        embed_font_file(project, layer)
        layer["x"] = finite(op.get("x", 0), "x")
        layer["y"] = finite(op.get("y", 0), "y")
        _apply_settings(project, layer, op)
        append_layer(project, layer)
        return
    layer = project.layer(op["target"])
    require(is_field(layer), f"{layer['name']!r} is not a field", field="target")
    _apply_settings(project, layer, op)


def fresh_key(project, layer):
    """Give a duplicated field a free key (``full_name-2``); a duplicated radio button keeps its
    group and gets a free option (``annual-2``)."""
    record = layer["field"]
    taken = {f["field"]["key"] for _, f in all_fields(project)}
    if record["kind"] == "radio":
        options = {f["field"]["option"] for _, f in all_fields(project) if f["field"]["key"] == record["key"]}
        base, index = record["option"], 2
        while f"{base}-{index}" in options:
            index += 1
        record["option"] = f"{base}-{index}"
        record.pop("default", None)
        return
    base, index = record["key"], 2
    while f"{base}-{index}"[:64] in taken:
        index += 1
    record["key"] = f"{base}-{index}"[:64]


def _key_from(name):
    key = re.sub(r"[^\w-]+", "_", name).strip("_")[:64]
    return key or "field"


def default_appearance(state, kind):
    unit = px_per_pt(state)
    appearance = {"style": "box", "fill": "#ffffff", "stroke": "#5b616b", "stroke_width": max(1, round(0.75 * unit)),
                  "radius": round(2 * unit)}
    if kind == "signature":
        appearance.update(style="underline", fill="transparent", radius=0)
    if kind in ("checkbox", "radio"):
        appearance["mark"] = "dot" if kind == "radio" else "check"
    return appearance


def _apply_settings(project, layer, op):
    from .operations import embed_font_file
    from .render import resolve_font

    record = layer["field"]
    for key in FIELD_SETTINGS:
        if key in op:
            if op[key] is None:
                record.pop(key, None)
            else:
                record[key] = deepcopy(op[key])
    if "label_layer" in op and op["label_layer"]:
        record["label_layer"] = project.layer(op["label_layer"])["id"]
    if "font" in op:
        layer["font"], role = resolve_font(project, op["font"])
        layer.pop("font_role", None)
        if role:
            layer["font_role"] = role
        embed_font_file(project, layer)
    for key in ("size", "color", "align", "padding"):
        if key in op:
            layer[key] = op[key]
    if "appearance" in op:
        layer["appearance"] = {**layer.get("appearance", {}), **deepcopy(op["appearance"])}
    if record["kind"] in ("checkbox", "radio"):
        layer["appearance"].setdefault("mark", "dot" if record["kind"] == "radio" else "check")
    else:
        layer["appearance"].pop("mark", None)
    if record["kind"] == "radio" and "option" not in record:
        record["option"] = record["key"] if record["key"] != op.get("key") else _key_from(layer["name"])
    validate_field(layer, project.state)


# ---------------------------------------------------------------------------------------------
# Validation


def validate_settings(settings):
    require(isinstance(settings, dict) and not set(settings) - set(FORM_SETTINGS), "Invalid form settings",
            "invalid_project")
    require(settings.get("tab_order", "reading") in ("reading", "explicit"), "tab_order must be reading or explicit",
            field="tab_order")
    require(settings.get("entry_font", "standard") in ("standard", "embed"), "entry_font must be standard or embed",
            field="entry_font")
    if "title" in settings:
        require(isinstance(settings["title"], str) and len(settings["title"]) <= 500, "title is up to 500 characters",
                field="title")
    if "lang" in settings:
        require(isinstance(settings["lang"], str) and re.fullmatch(r"[A-Za-z]{2,8}(-[A-Za-z0-9]{1,8})*", settings["lang"]),
                "lang must be a BCP 47 language tag such as en-US", field="lang")


def option_values(record):
    return [item if isinstance(item, str) else item["value"] for item in record.get("options") or []]


def option_label(record, value):
    for item in record.get("options") or []:
        if (item if isinstance(item, str) else item["value"]) == value:
            return item if isinstance(item, str) else item.get("label", item["value"])
    return value


def validate_field(layer, state):
    """One field layer's own settings (cross-field rules are in ``validate_form``)."""
    record = layer.get("field")
    require(isinstance(record, dict) and not set(record) - set(FIELD_SETTINGS), "Invalid field record", "invalid_project")
    kind = record.get("kind")
    require(kind in KINDS, f"kind must be one of {', '.join(KINDS)}", field="kind")
    key = record.get("key")
    require(isinstance(key, str) and KEY.fullmatch(key),
            "key must be 1–64 letters, digits, underscores or hyphens (no dots)", field="key")
    for name in ("label", "tooltip", "group_label"):
        if name in record:
            require(isinstance(record[name], str) and len(record[name]) <= MAX_LABEL,
                    f"{name} is text up to {MAX_LABEL} characters", field=name)
    require(record.get("group_label") is None or kind == "radio", "group_label is for radio buttons", field="group_label")
    for name in ("required", "read_only", "comb", "editable"):
        if name in record:
            require(isinstance(record[name], bool), f"{name} must be true or false", field=name)
    if "max_length" in record:
        require(kind in ("text", "multiline", "number") and isinstance(record["max_length"], int)
                and not isinstance(record["max_length"], bool) and 1 <= record["max_length"] <= MAX_VALUE,
                f"max_length is a whole number 1–{MAX_VALUE} for text, multiline and number fields", field="max_length")
    if record.get("comb"):
        require(kind == "text" and "max_length" in record, "comb needs a text field with max_length", field="comb")
    if "format" in record:
        fmt = record["format"]
        if kind == "text":
            require(fmt in ("email", "digits"), "A text field's format is email or digits", field="format")
        elif kind == "number":
            require(isinstance(fmt, dict) and not set(fmt) - {"decimals", "min", "max"}, "A number format is "
                    "{decimals, min, max}", field="format")
            if "decimals" in fmt:
                require(isinstance(fmt["decimals"], int) and 0 <= fmt["decimals"] <= 10, "decimals is 0–10", field="format")
            for bound in ("min", "max"):
                if bound in fmt:
                    finite(fmt[bound], bound)
            require(fmt.get("min", -math.inf) <= fmt.get("max", math.inf), "min must not exceed max", field="format")
        elif kind == "date":
            require(isinstance(fmt, dict) and set(fmt) <= {"display"} and isinstance(fmt.get("display", ""), str)
                    and len(fmt.get("display", "")) <= 40, "A date format is {display: 'DD/MM/YYYY'}", field="format")
        else:
            raise VixlError("invalid_operation", f"A {kind} field has no format", field="format")
    if "pattern" in record:
        require(kind == "text", "pattern is for text fields", field="pattern")
        check_pattern(record["pattern"])
    if "message" in record:
        require(isinstance(record["message"], str) and 0 < len(record["message"]) <= MAX_MESSAGE,
                f"message is text of 1–{MAX_MESSAGE} characters", field="message")
    if kind == "dropdown":
        options = record.get("options")
        require(isinstance(options, list) and 1 <= len(options) <= MAX_OPTIONS,
                f"A dropdown needs 1–{MAX_OPTIONS} options", field="options")
        values = option_values(record)
        require(all(isinstance(v, str) and 0 < len(v) <= MAX_LABEL for v in values) and all(
            isinstance(o, str) or (isinstance(o.get("label", ""), str) and len(o.get("label", "")) <= MAX_LABEL)
            for o in options), f"Options are text up to {MAX_LABEL} characters", field="options")
        require(len(set(values)) == len(values), "Dropdown options must be unique", field="options")
    else:
        require("options" not in record and "editable" not in record, "options and editable are for dropdowns",
                field="options")
    if kind == "radio":
        require(isinstance(record.get("option"), str) and 0 < len(record["option"]) <= MAX_LABEL
                and record["option"] != "Off", "A radio button needs an option value (not 'Off')", field="option")
    else:
        require("option" not in record, "option is for radio buttons", field="option")
    if "on_value" in record:
        require(kind == "checkbox" and isinstance(record["on_value"], str) and 0 < len(record["on_value"]) <= 64
                and record["on_value"] != "Off", "on_value is a checkbox's export value (not 'Off')", field="on_value")
    if "tab" in record:
        require(isinstance(record["tab"], int) and 1 <= record["tab"] <= 10000, "tab is a position 1–10000", field="tab")
    if "overflow" in record:
        require(record["overflow"] in OVERFLOW and kind in TEXT_KINDS, "overflow is shrink, clip or error for text kinds",
                field="overflow")
    if "min_size" in record:
        finite(record["min_size"], "min_size", 1, 4096)
    if "default" in record and kind != "radio":
        require(kind != "signature", "A signature field has no default", field="default")
        try:
            coerce(record, record["default"])
        except FieldValueError as exc:
            raise VixlError("invalid_operation", f"default: {exc.message}", field="default") from exc
    finite(layer.get("size", 16), "size", 1, 4096)
    finite(layer.get("padding", 0), "padding", 0, 1000)
    require(layer.get("align", "left") in ("left", "center", "right"), "align is left, center or right", field="align")
    appearance = layer.get("appearance") or {}
    require(isinstance(appearance, dict) and not set(appearance) - set(APPEARANCE), "Invalid field appearance",
            field="appearance")
    require(appearance.get("style", "box") in STYLES, "style is box, underline or none", field="appearance")
    require(appearance.get("mark", "check") in MARKS, "mark is check, cross or dot", field="appearance")
    finite(appearance.get("stroke_width", 0), "stroke_width", 0, 1000)
    finite(appearance.get("radius", 0), "radius", 0, 10000)
    from .design import resolve_color
    from .render import color

    for name in ("fill", "stroke", "mark_color"):
        if name in appearance:
            color(resolve_color(appearance[name], state))


def validate_form(project, state):
    """Rules across fields: unique keys (radio groups share one), groups that agree, no key that
    is also a variable, no fields in masters, symbols or repeats, and the size limits."""
    if "form" in state:
        validate_settings(state["form"])
    fields = all_fields(project, state)
    for master in (state.get("masters") or {}).values():
        require(not any(is_field(layer) for layer in (master.get("content") or {}).get("layers", [])),
                "Master pages cannot hold fields (each page needs its own)", "invalid_project")
    if not fields:
        return
    require(len(fields) <= MAX_FIELDS, f"A document holds at most {MAX_FIELDS} fields", "resource_limit")
    variables = state.get("variables", {})
    groups = {}
    for _, layer in fields:
        record = layer["field"]
        require(record["key"] not in variables and record["key"] not in ("page", "pages", "page_name"),
                f"Field key {record['key']!r} is also a variable name; rename one", field="key")
        groups.setdefault(record["key"], []).append(layer)
    for key, members in groups.items():
        if len(members) == 1 and members[0]["field"]["kind"] != "radio":
            continue
        require(all(m["field"]["kind"] == "radio" for m in members),
                f"Field key {key!r} is used more than once; only radio buttons of one group share a key", field="key")
        for setting in ("required", "read_only"):
            require(len({bool(m["field"].get(setting)) for m in members}) == 1,
                    f"Radio buttons {key!r} must agree on {setting}", field=setting)
        labels = {m["field"]["group_label"] for m in members if m["field"].get("group_label")}
        require(len(labels) <= 1, f"Radio buttons {key!r} have different group labels", field="group_label")
        options = [m["field"]["option"] for m in members]
        require(len(set(options)) == len(options), f"Radio buttons {key!r} need different option values", field="option")
        defaults = {m["field"]["default"] for m in members if "default" in m["field"]}
        require(len(defaults) <= 1, f"Radio buttons {key!r} have different defaults", field="default")
        if defaults:
            require(next(iter(defaults)) in options, f"The default of radio group {key!r} is not one of its options",
                    field="default")
    for page, layer in fields:
        content = page["content"] if page else state
        index = {item["id"]: item for item in content.get("layers", [])}
        item = layer
        while item.get("parent"):
            item = index.get(item["parent"]) or {}
            require(not item.get("repeat"), "Fields cannot be inside a repeated group (their keys would repeat)",
                    "invalid_operation", field="target")
        symbols = content.get("symbols") or {}
        ancestors = {layer["id"]}
        item = layer
        while item.get("parent"):
            ancestors.add(item["parent"])
            item = index.get(item["parent"]) or {}
        require(not (ancestors & set(symbols.values())), "Fields cannot be part of a symbol master", "invalid_operation",
                field="target")


# ---------------------------------------------------------------------------------------------
# Values


class FieldValueError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code, self.message = code, message


def coerce(record, raw, group=None, rules=True):
    """(value, display text) for a field's raw value; raises FieldValueError. ``group`` is the
    radio group's option values; ``rules`` False skips the text ``pattern`` (worst-case samples
    are not written to match one)."""
    kind = record["kind"]
    if kind == "signature":
        if raw in (None, ""):
            return None, ""
        if not isinstance(raw, str):
            raise FieldValueError("invalid_format", "A signature sample is text or a data:image/png;base64,... image")
        if raw.startswith("data:"):
            signature_image(raw)
            return raw, ""
        if "\n" in raw or "\r" in raw or len(raw) > MAX_SIGNATURE:
            raise FieldValueError("invalid_format", f"A signature sample is one line of up to {MAX_SIGNATURE} characters")
        return raw, raw
    if kind == "checkbox":
        if isinstance(raw, bool):
            value = raw
        else:
            text = "" if raw is None else str(raw).strip().lower()
            if text in ("yes", "true", "1", "x", "on", "y", record.get("on_value", "Yes").lower()):
                value = True
            elif text in ("", "no", "false", "0", "off", "n"):
                value = False
            else:
                raise FieldValueError("invalid_format", "A checkbox takes yes/no, true/false, 1/0 or x")
        return value, "x" if value else ""
    if raw is None or (isinstance(raw, str) and raw == ""):
        return None, ""
    if kind == "radio":
        value = str(raw)
        if value not in (group or [record.get("option")]):
            raise FieldValueError("invalid_option", "The value is not one of the radio group's options")
        return value, value
    if kind == "dropdown":
        value = str(raw)
        if value not in option_values(record) and not record.get("editable"):
            raise FieldValueError("invalid_option", "The value is not one of the dropdown's options")
        return value, str(option_label(record, value))
    if isinstance(raw, bool):
        raise FieldValueError("invalid_format", "A text value cannot be true or false")
    if kind == "number":
        try:
            value = float(raw) if not isinstance(raw, (int, float)) else float(raw)
        except (TypeError, ValueError):
            raise FieldValueError("invalid_number", "The value is not a number") from None
        if not math.isfinite(value):
            raise FieldValueError("invalid_number", "The value is not a finite number")
        fmt = record.get("format") or {}
        if value < fmt.get("min", -math.inf) or value > fmt.get("max", math.inf):
            raise FieldValueError("invalid_number", "The number is outside the allowed range")
        decimals = fmt.get("decimals")
        if decimals is not None:
            display = f"{value:.{decimals}f}"
        else:
            display = str(int(value)) if value.is_integer() and abs(value) < 1e15 else repr(value)
        if len(display) > record.get("max_length", MAX_VALUE):
            raise FieldValueError("too_long", "The value is longer than max_length")
        return value, display
    if kind == "date":
        text = str(raw).strip()
        try:
            day = datetime.date.fromisoformat(text) if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text) else None
        except ValueError:
            day = None
        if day is None:
            raise FieldValueError("invalid_date", "Dates are written YYYY-MM-DD")
        pattern = (record.get("format") or {}).get("display", "YYYY-MM-DD")
        tokens = {"YYYY": f"{day.year:04d}", "MM": f"{day.month:02d}", "M": str(day.month), "DD": f"{day.day:02d}",
                  "D": str(day.day)}
        display = re.sub(r"YYYY|MM|M|DD|D", lambda m: tokens[m[0]], pattern)
        return day.isoformat(), display
    text = str(raw)
    if kind == "multiline":
        text = text.replace("\r\n", "\n").replace("\r", "\n")
    elif "\n" in text or "\r" in text:
        raise FieldValueError("invalid_format", "A single-line field cannot contain line breaks")
    if len(text) > min(record.get("max_length", MAX_VALUE), MAX_VALUE):
        raise FieldValueError("too_long", "The value is longer than max_length")
    fmt = record.get("format")
    if fmt == "digits" and not text.isdigit():
        raise FieldValueError("invalid_format", "Only the digits 0–9 are allowed")
    if fmt == "email" and not re.fullmatch(EMAIL, text):
        raise FieldValueError("invalid_format", "The value is not an email address")
    if rules and record.get("pattern") and not pattern_matches(record["pattern"], text):
        raise FieldValueError("invalid_format", "The value does not match the field's pattern")
    return text, text


MAX_SIGNATURE = 200
MAX_SIGNATURE_IMAGE = 4 * 1024 * 1024


@lru_cache(maxsize=8)
def signature_image(uri):
    """The RGBA image of a ``data:image/...;base64,`` signature sample; raises FieldValueError."""
    import base64
    import binascii

    from PIL import Image

    match = re.fullmatch(r"data:image/(png|jpeg|jpg|webp);base64,([A-Za-z0-9+/=\s]+)", uri)
    if not match or len(match[2]) > MAX_SIGNATURE_IMAGE * 4 // 3 + 4:
        raise FieldValueError("invalid_format", "A signature image is a data:image/png (or jpeg, webp) base64 URI of up "
                              "to 4 MB")
    try:
        image = Image.open(io.BytesIO(base64.b64decode(match[2], validate=False)))
        require(image.width * image.height <= 25_000_000, "Signature image is too large")
        image.load()
        return image.convert("RGBA")
    except (binascii.Error, OSError, ValueError, VixlError, Image.DecompressionBombError) as exc:
        raise FieldValueError("invalid_format", "The signature image cannot be read") from exc


def reject_signature_samples(project, values):
    """Signature samples are drawn into flattened fills only; a fillable PDF leaves signing to the viewer."""
    signed = {layer["field"]["key"] for _, layer in all_fields(project) if layer["field"]["kind"] == "signature"}
    keys = sorted(key for key, value in (values or {}).items() if key in signed and value not in (None, ""))
    require(not keys, f"{', '.join(keys)}: a signature sample is drawn only in flattened fills (mode flatten, or "
            "values= without fillable); a fillable PDF leaves signature fields for the viewer to sign", field="values")


def signature_font(project, layer):
    """The font a text signature sample is drawn in: the field's font when one was set on it,
    otherwise a registered handwriting/script font (catalog category, or a family named script,
    hand or signature) if the document has one, otherwise the field's font."""
    if not layer.get("font_role"):
        return layer["font"]
    from .typefaces import find_font

    for name, asset in sorted(project.state.get("fonts", {}).items()):
        data = project.assets.get(asset)
        if not data:
            continue
        try:
            family = _font_names(data)[0]
        except Exception:  # noqa: BLE001 - an unreadable font is simply not a candidate
            continue
        entry = find_font(family)
        if (entry and entry["category"] == "handwriting") or re.search(r"script|hand|signature", family, re.I):
            return name
    return layer["font"]


def _signature_parts(project, layer, value, display):
    """The sample drawn in a signature field: an image fitted into the box, or text in
    ``signature_font`` sized to the box."""
    w, h = layer["width"], layer["height"]
    pad = float(layer.get("padding", 0))
    inner_w, inner_h = max(1.0, w - 2 * pad), max(1.0, h - 2 * pad)
    if not display:
        image = signature_image(value)
        scale = min(inner_w / image.width, inner_h / image.height)
        fitted = image.resize((max(1, round(image.width * scale)), max(1, round(image.height * scale))))
        part = {"type": "sample-image", "image": fitted, "width": fitted.width, "height": fitted.height}
        spare = inner_w - fitted.width
        x = pad + {"center": spare / 2, "right": spare}.get(layer.get("align", "left"), 0)
        return [(part, x, pad + (inner_h - fitted.height) / 2, None)]
    styled = {**layer, "font": signature_font(project, layer)}
    if styled["font"] != layer["font"]:
        styled.pop("font_role", None)
    size = max(1.0, min(inner_h * 0.75, float(layer.get("size", 16)) * 2.5))
    measured = _measure(project, styled, display, size)
    if measured.width > inner_w:
        size = max(1.0, size * inner_w / measured.width)
        measured = _measure(project, styled, display, size)
    text = _text_layer(styled, display, size)
    text.update(width=max(1, round(measured.width)), height=max(1, round(measured.height)))
    align = layer.get("align", "left")
    x = pad + ((inner_w - measured.width) / 2 if align == "center" else inner_w - measured.width if align == "right" else 0)
    return [(text, x, (h - measured.height) / 2, (pad, pad, inner_w, inner_h))]


def groups(fields):
    """{key: [option values]} for radio groups."""
    result = {}
    for _, layer in fields:
        if layer["field"]["kind"] == "radio":
            result.setdefault(layer["field"]["key"], []).append(layer["field"]["option"])
    return result


def check_values(project, values, row=None, unknown="error", complete=True, rules=True):
    """Validate input values against the document's fields. Returns (fields, variables, errors):
    ``fields`` maps keys to coerced values (only those supplied), ``variables`` holds keys that
    name document variables, ``errors`` lists ``{row, key, code, message}``. ``complete``
    also requires every required field (a fill); previews check only the values given.
    ``rules`` False skips text patterns. A required signature is signed in a viewer, so a fill
    never needs it."""
    require(isinstance(values, dict), "values must be an object of field keys and values", field="values")
    require(unknown in ("error", "ignore"), "unknown must be error or ignore", field="unknown")
    fields = all_fields(project)
    records = {}
    for _, layer in fields:
        records.setdefault(layer["field"]["key"], layer["field"])
    options = groups(fields)
    variables_known = project.state.get("variables", {})
    filled, variables, errors = {}, {}, []

    def error(key, code, message):
        errors.append({**({"row": row} if row is not None else {}), "key": key, "code": code,
                       "message": (f"Row {row}, " if row is not None else "") + f"{key}: {message}"})

    for key, raw in values.items():
        if key in records:
            try:
                filled[key] = coerce(records[key], raw, options.get(key), rules)[0]
            except FieldValueError as exc:
                error(key, exc.code, exc.message)
        elif key in variables_known:
            variables[key] = raw
        elif unknown == "error":
            error(key, "unknown_key", "No field or variable has this key")
    for key, record in records.items():
        if (not complete or not record.get("required") or record["kind"] == "signature"
                or any(e["key"] == key for e in errors)):
            continue
        value = filled.get(key) if key in values else current_default(record, fields)
        if record["kind"] == "checkbox":
            if not value:
                error(key, "missing_required", "This required box must be checked")
        elif value in (None, ""):
            error(key, "missing_required", "This required field is empty")
    return filled, variables, errors


def current_default(record, fields=None):
    if record["kind"] == "radio":
        for _, layer in fields or []:
            if layer["field"]["key"] == record["key"] and "default" in layer["field"]:
                return layer["field"]["default"]
        return None
    if "default" not in record:
        return False if record["kind"] == "checkbox" else None
    try:
        return coerce(record, record["default"])[0]
    except FieldValueError:
        return None


def current_values(project):
    """{key: (value, display)} for every field: filled values over defaults."""
    fields = all_fields(project)
    if not fields:
        return {}
    filled = getattr(project, "_form_values", None) or {}
    options = groups(fields)
    result = {}
    for _, layer in fields:
        record = layer["field"]
        key = record["key"]
        if key in result:
            continue
        value = filled[key] if key in filled else current_default(record, fields)
        try:
            # Filled values were validated by with_values; only defaults are checked against the pattern.
            result[key] = (coerce(record, value, options.get(key), key not in filled) if value not in (None, "")
                           else (None, ""))
        except FieldValueError:
            result[key] = (None, "")
    return result


def with_values(project, values=None, *, unknown="error", row=None, complete=True, rules=True):
    """A render-only copy of the document showing ``values`` (validated; ``complete`` requires
    every required field; ``rules`` False skips text patterns). Raises ``form_values_invalid``
    listing every problem. The copy never uses the persistent render cache, so personal data is
    not written to disk."""
    filled, variables, errors = check_values(project, values or {}, row=row, unknown=unknown, complete=complete,
                                             rules=rules)
    if errors:
        raise VixlError("form_values_invalid", f"{len(errors)} value problem(s): " + "; ".join(e["message"] for e in errors[:5]),
                        errors=errors)
    view = project.clone()
    view._disk_cache = None
    view._form_values = {**(getattr(project, "_form_values", None) or {}), **filled}
    if variables:
        view.state["variables"] = {**view.state["variables"], **variables}
    return view


def split_values(project, pairs):
    """Split ``KEY=VALUE`` render settings into field values and variables."""
    keys = {layer["field"]["key"] for _, layer in all_fields(project)}
    values = {k: v for k, v in (pairs or {}).items() if k in keys}
    variables = {k: v for k, v in (pairs or {}).items() if k not in keys}
    return values, variables


# ---------------------------------------------------------------------------------------------
# Drawing


def _text_layer(layer, text, size, *, width=None, height=None, align=None):
    """A synthetic rich text layer drawing ``text`` with the field's font and color."""
    synthetic = new_layer("value", "text", 1, 1, text=text, font=layer["font"], size=size, color=layer.get("color", "#1f2328"),
                          align=align or layer.get("align", "left"), spacing=0, auto_size=False,
                          rich={"spans": [{"text": text}], "paragraphs": [{} for _ in text.split("\n")], "line_height": 1.2})
    if width is not None:
        synthetic["text_layout"] = {"width": width, "height": height}
        synthetic.update(width=max(1, round(width)), height=max(1, round(height)))
    if layer.get("font_role"):
        synthetic["font_role"] = layer["font_role"]
    return synthetic


def _measure(project, layer, text, size, width=None):
    from .richtext import layout

    synthetic = _text_layer(layer, text, size)
    return layout(project, synthetic, width=width)


def _longest_word(project, layer, text, size):
    from .richtext import style_font_data
    from .text import shape

    words = set(text.split())
    if not words:
        return 0.0
    data = style_font_data(project, layer["font"], text)
    return max(shape(data, word, size)[1] for word in words)


def scale_field(layer, s):
    """Scale a field's value styling (size, padding, border, ``min_size``) by ``s`` for a reduced
    or enlarged render-only copy; the caller scales the box. Without this a proxy preview draws
    values at full-size type inside a shrunken box."""
    for key in ("size", "padding"):
        if key in layer:
            layer[key] = layer[key] * s
    appearance = layer.get("appearance") or {}
    for key in ("stroke_width", "radius"):
        if key in appearance:
            appearance[key] = appearance[key] * s
    record = layer.get("field") or {}
    if "min_size" in record:
        record["min_size"] = record["min_size"] * s


def _inner(layer):
    pad = float(layer.get("padding", 0))
    return max(1.0, layer["width"] - 2 * pad), max(1.0, layer["height"] - 2 * pad)


def _fits(project, layer, text, size):
    """(fits, measured) for ``text`` drawn at ``size`` in the field's box. ``measured`` is what was
    compared, in document pixels: a single line's ``width`` and ``height``, or a multiline value's
    wrapped ``height``, ``lines`` and ``longest_word`` width."""
    inner_w, inner_h = _inner(layer)
    if layer["field"]["kind"] == "multiline":
        result = _measure(project, layer, text, size, inner_w)
        word = _longest_word(project, layer, text, size)
        return (result.height <= inner_h + 0.5 and word <= inner_w + 0.5,
                {"height": result.height, "lines": len(result.lines), "longest_word": word})
    result = _measure(project, layer, text, size)
    return (result.box[2] <= inner_w + 0.5 and result.height <= inner_h * 1.2 + 0.5,
            {"width": result.box[2], "height": result.height})


def smallest_size(project, layer):
    """The smallest size ``shrink`` may use: ``min_size`` (default 70% of the size), never below 6 pt."""
    unit = px_per_pt(project.state)
    size = float(layer.get("size", 16))
    return max(float(layer["field"].get("min_size", size * 0.7)), 6 * unit if project.state["canvas"].get("dpi") else 6)


def _fit(project, layer, text):
    """(size, status, tried) for drawing ``text`` in the field: ``tried`` is the smallest size that
    was measured (the size when nothing shrank), the one an explanation should quote."""
    record = layer["field"]
    size = float(layer.get("size", 16))
    if not text or record["kind"] not in TEXT_KINDS or record.get("comb"):
        return size, "ok", size
    if _fits(project, layer, text, size)[0]:
        return size, "ok", size
    mode = record.get("overflow", "shrink")
    if mode == "clip":
        return size, "clipped", size
    if mode == "error":
        return size, "overflow", size
    floor = smallest_size(project, layer)
    if floor >= size:
        return size, "overflow", size
    if not _fits(project, layer, text, floor)[0]:
        return size, "overflow", floor
    low, high = floor, size
    for _ in range(12):
        middle = (low + high) / 2
        if _fits(project, layer, text, middle)[0]:
            low = middle
        else:
            high = middle
    best = math.floor(low * 4) / 4
    return best, "shrunk", best


def fit_value(project, layer, text):
    """(size, status) for drawing ``text`` in the field: status ``ok``, ``shrunk``, ``clipped``
    or ``overflow`` following the field's overflow setting."""
    return _fit(project, layer, text)[:2]


@lru_cache(maxsize=16)
def _font_names(data):
    from fontTools.ttLib import TTFont

    names = TTFont(io.BytesIO(data))["name"]
    return names.getBestFamilyName() or "", names.getBestSubFamilyName() or ""


def font_label(project, layer, text=""):
    """The font a field draws with, in words: family and style, the name it is registered under,
    and whether it is the bundled proofing fallback or other fonts fill in missing glyphs."""
    from .richtext import _registered_name, style_font_data
    from .text import primary_font_data

    font = layer.get("font", "DejaVuSans.ttf")
    family, style = _font_names(primary_font_data(project, {"font": font, "size": 12}))
    label = f"{family} {style}".strip() or font
    registered = _registered_name(project.state, font)
    if registered:
        label += f" (registered as {registered})"
    elif font == "DejaVuSans.ttf":
        label += " (the bundled proofing fallback)"
    if text and isinstance(style_font_data(project, font, text), tuple):
        label += ", with fallback fonts for glyphs it lacks"
    return label


def fit_details(project, layer, text, status, tried, *, reveal=False, suggest=False):
    """What a fit measured, so a result can be explained: the font, the sizes (configured and
    measured), the box and the rendered width (or a multiline value's wrapped height). ``reveal``
    adds an excerpt of the value (worst-case samples only: filled values are personal data);
    ``suggest`` adds the largest ``max_length`` whose worst-case value would fit."""
    record = layer["field"]
    inner_w, inner_h = _inner(layer)
    measured = _fits(project, layer, text, tried)[1]
    details = {"key": record["key"], "kind": record["kind"], "status": status, "characters": len(text),
               "font": font_label(project, layer, text), "size": float(layer.get("size", 16)),
               "size_measured": round(tried, 2), "overflow": record.get("overflow", "shrink"),
               "box_width": layer["width"], "box_height": layer["height"], "padding": float(layer.get("padding", 0)),
               "inner_width": round(inner_w, 2), "inner_height": round(inner_h, 2)}
    if details["overflow"] == "shrink":
        details["min_size"] = round(smallest_size(project, layer), 2)
    if reveal:
        details["sample"] = text if len(text) <= 40 else text[:40] + "…"
    if record["kind"] == "multiline":
        details.update(wrapped_height=round(measured["height"], 1), lines=measured["lines"],
                       longest_word_width=round(measured["longest_word"], 1))
    else:
        details["rendered_width"] = round(measured["width"], 1)
    if suggest and record["kind"] in ("text", "multiline") and record.get("format") != "email":
        details["max_length_that_fits"] = _longest_fit(project, layer, record, tried)
    return details


def _longest_fit(project, layer, record, size):
    """The largest ``max_length`` whose worst-case value fits the field at ``size`` (the smallest
    size its overflow setting allows; 0 when not even one character fits)."""
    low, high = 0, record.get("max_length", default_length(record))
    while low < high:
        middle = (low + high + 1) // 2
        if _fits(project, layer, worst_text(record, middle), size)[0]:
            low = middle
        else:
            high = middle - 1
    return low


def explain_fit(details):
    """One sentence for ``fit_details``: what was measured against what the box holds."""
    tried, size = details["size_measured"], details["size"]
    at = f"{tried:g} px"
    if tried < size:
        at += " (the smallest size shrink may use)"
    elif details["overflow"] == "shrink" and details.get("min_size", 0) >= size:
        at += f" (no room to shrink: min_size {details['min_size']:g} is not below the size)"
    elif details["overflow"] != "shrink":
        at += f" (overflow: {details['overflow']})"
    count = f"{details['characters']} characters" + (f" ({details['sample']!r})" if "sample" in details else "")
    if details["kind"] == "multiline":
        sentence = (f"{count} wrap to {details['lines']} lines and {details['wrapped_height']:g} px tall at {at} in "
                    f"{details['font']}; the box is {details['inner_width']:g} px wide and holds "
                    f"{details['inner_height']:g} px of height (longest word {details['longest_word_width']:g} px)")
    else:
        sentence = (f"{count} measure {details['rendered_width']:g} px at {at} in {details['font']}; the box holds "
                    f"{details['inner_width']:g} px ({details['box_width']:g} px wide, {details['padding']:g} px padding "
                    "each side)")
    if "max_length_that_fits" in details:
        fits = details["max_length_that_fits"]
        sentence += (f". A max_length of {fits} would fit" if fits else ". Not even one character fits; make the box larger")
    return sentence


def parts(project, layer, *, values=True):
    """The field as positioned synthetic layers: [(layer, x, y, clip)] in the field's box. The
    box (or underline, comb cells, chevron) first, then the value when ``values``. ``clip`` is
    an (x, y, w, h) rectangle the value must be clipped to, or None."""
    from .design import resolve_color

    state = project.state
    record = layer["field"]
    kind = record["kind"]
    w, h = layer["width"], layer["height"]
    appearance = {**default_appearance(state, kind), **(layer.get("appearance") or {})}
    style = appearance.get("style", "box")
    stroke = resolve_color(appearance.get("stroke", "transparent"), state)
    fill = resolve_color(appearance.get("fill", "transparent"), state)
    stroke_width = float(appearance.get("stroke_width", 1))
    result = []
    if style == "box":
        shape = "ellipse" if kind == "radio" else ("rounded-rectangle" if appearance.get("radius") else "rectangle")
        box = new_layer("box", "shape", w, h, shape=shape, fill=fill, stroke=stroke, stroke_width=stroke_width,
                        radius=float(appearance.get("radius", 0)))
        result.append((box, 0, 0, None))
    elif style == "underline":
        if fill and fill != "transparent":
            result.append((new_layer("fill", "shape", w, h, shape="rectangle", fill=fill), 0, 0, None))
        line = new_layer("underline", "shape", w, max(1, round(stroke_width)), shape="rectangle", fill=stroke)
        result.append((line, 0, h - line["height"], None))
    if record.get("comb") and style != "none":
        cells = record["max_length"]
        for i in range(1, cells):
            x = w * i / cells
            divider = new_layer("cell", "shape", max(1, round(stroke_width)), max(1, round(h * (0.35 if style == "underline" else 1))),
                                shape="rectangle", fill=stroke)
            result.append((divider, x - divider["width"] / 2, h - divider["height"], None))
    pad = float(layer.get("padding", 0))
    chevron = 0.0
    if kind == "dropdown":
        side = min(h - 2 * pad, float(layer.get("size", 16))) * 0.6
        if side > 2:
            path = "M 0 0 L 100 0 L 50 60 Z"
            arrow = new_layer("chevron", "shape", max(1, round(side)), max(1, round(side * 0.6)), shape="path", path=path,
                              path_view=[100, 60], fill=resolve_color(layer.get("color", "#1f2328"), state))
            chevron = side + pad
            result.append((arrow, w - pad - side, (h - arrow["height"]) / 2, None))
    if not values:
        return result
    value, display = layer.get("value", (None, ""))
    if kind in ("checkbox", "radio"):
        on = bool(value) if kind == "checkbox" else value == record.get("option")
        if on:
            mark = appearance.get("mark", "dot" if kind == "radio" else "check")
            mark_color = resolve_color(appearance.get("mark_color", layer.get("color", "#1f2328")), state)
            if mark == "dot":
                side = min(w, h) * 0.5
                dot = new_layer("mark", "shape", max(1, round(side)), max(1, round(side)), shape="ellipse", fill=mark_color)
                result.append((dot, (w - dot["width"]) / 2, (h - dot["height"]) / 2, None))
            else:
                side = min(w, h) * 0.8
                glyph = new_layer("mark", "shape", max(1, round(side)), max(1, round(side)), shape="path", path=MARK_PATHS[mark],
                                  path_view=[100, 100], fill="transparent", stroke=mark_color, stroke_width=12, line_cap="round")
                result.append((glyph, (w - glyph["width"]) / 2, (h - glyph["height"]) / 2, None))
        return result
    if kind == "signature":
        return result + (_signature_parts(project, layer, value, display) if value not in (None, "") else [])
    if not display:
        return result
    clip = (pad, pad, max(1.0, w - 2 * pad - chevron), max(1.0, h - 2 * pad))
    if record.get("comb"):
        cells = record["max_length"]
        size = float(layer.get("size", 16))
        for i, char in enumerate(display[:cells]):
            if char.isspace():
                continue
            glyph = _text_layer(layer, char, size, align="center")
            measured = _measure(project, layer, char, size)
            glyph.update(width=max(1, round(measured.width)), height=max(1, round(measured.height)))
            result.append((glyph, w * (i + 0.5) / cells - measured.width / 2, (h - measured.height) / 2, None))
        return result
    size, _ = fit_value(project, layer, display)
    inner_w, inner_h = clip[2], clip[3]
    if kind == "multiline":
        text = _text_layer(layer, display, size, width=inner_w, height=inner_h)
        result.append((text, pad, pad, clip))
        return result
    measured = _measure(project, layer, display, size)
    text = _text_layer(layer, display, size)
    text.update(width=max(1, round(measured.width)), height=max(1, round(measured.height)))
    align = layer.get("align", "left")
    x = pad + ((inner_w - measured.width) / 2 if align == "center" else inner_w - measured.width if align == "right" else 0)
    y = (h - measured.height) / 2
    result.append((text, x, y, clip))
    return result


def field_image(project, layer):
    """The field drawn at its rest size (appearance plus its current value)."""
    from PIL import Image, ImageChops

    from .design_render import shape_image, text_image

    w, h = layer["width"], layer["height"]
    project.limits.size(w, h)
    image = Image.new("RGBA", (w, h))
    for part, x, y, clip in parts(project, layer):
        if part["type"] == "sample-image":
            tile = part["image"]
        else:
            tile = shape_image(project, part) if part["type"] == "shape" else text_image(project, part)
        canvas = Image.new("RGBA", (w, h))
        _composite(canvas, tile, round(x), round(y))
        if clip:
            cx, cy, cw, ch = clip
            mask = Image.new("L", (w, h))
            mask.paste(255, (math.floor(cx), math.floor(cy), math.ceil(cx + cw), math.ceil(cy + ch)))
            canvas.putalpha(ImageChops.multiply(canvas.getchannel("A"), mask))
        image.alpha_composite(canvas)
    return image


def _composite(canvas, tile, x, y):
    """alpha_composite ``tile`` at (x, y), which may be partly outside ``canvas``."""
    left, top = max(0, -x), max(0, -y)
    right, bottom = min(tile.width, canvas.width - x), min(tile.height, canvas.height - y)
    if right > left and bottom > top:
        canvas.alpha_composite(tile, dest=(x + left, y + top), source=(left, top, right, bottom))


def svg_field(exporter, parent, layer):
    """Static vector appearance of a field (with its current value) for SVG and HTML export."""
    from .svg import bitmap, node

    for part, x, y, clip in parts(exporter.project, layer):
        target = parent
        if clip:
            cx, cy, cw, ch = clip
            target = node(parent, "svg", x=cx, y=cy, width=cw, height=ch, viewBox=f"{cx} {cy} {cw} {ch}", overflow="hidden")
        holder = node(target, "svg", x=x, y=y, width=part["width"], height=part["height"],
                      viewBox=f"0 0 {part['width']} {part['height']}", overflow="visible")
        if part["type"] == "sample-image":
            bitmap(holder, part["image"])
        elif not exporter.geometry(holder, part):
            return False
    return True


def pdf_field_appearance(builder, layer, w, h):
    """Draw a field into a PDF page. In a fillable PDF (``builder.fillable``) the value is left
    to the field's widget; otherwise the value is drawn too (a flattened form)."""
    from .pdf_export import _fmt, affine, matrix_ops

    fillable = getattr(builder, "fillable", False)
    for part, x, y, clip in parts(builder.view, layer, values=not fillable):
        builder.ops += ["q"]
        if clip:
            cx, cy, cw, ch = clip
            builder.ops.append(f"{_fmt(cx)} {_fmt(cy)} {_fmt(cw)} {_fmt(ch)} re W n")
        builder.ops.append(matrix_ops(affine(1, 0, 0, 1, x, y)))
        if part["type"] == "sample-image":
            builder.place_image(part["image"], affine(), (0, 0, part["width"], part["height"]))
        elif part["type"] == "shape":
            builder.shape(part, part["width"], part["height"], layer["opacity"])
        else:
            builder.text(part, layer["opacity"])
        builder.ops.append("Q")


# ---------------------------------------------------------------------------------------------
# Geometry, tab order and summaries


def field_geometry(view):
    """[(resolved field layer, canvas bounds, matrix)] for the visible fields of a page view."""
    from .checks import canvas_projection
    from .render import resolve_layout, resolved_layers

    layers = resolved_layers(view)
    resolved = {item["id"]: item for item in layers}
    local = resolve_layout(view, layers=layers)
    projection = canvas_projection(resolved, local)

    def visible(item):
        while item:
            if not item["visible"] or item["opacity"] <= 0:
                return False
            item = resolved.get(item.get("parent"))
        return True

    return [(item, projection["bounds"][item["id"]], projection["matrices"][item["id"]])
            for item in layers if item["type"] == "field" and visible(item)], resolved, local, projection


def transformed(matrix):
    """Whether a canvas matrix rotates, skews or flips (fields must stay axis-aligned)."""
    return abs(matrix[0, 1]) > 1e-6 or abs(matrix[1, 0]) > 1e-6 or matrix[0, 0] <= 0 or matrix[1, 1] <= 0


def tab_order(state, entries):
    """Order field entries [(layer, bounds, …)] for tabbing. ``reading``: rows by vertical
    centre (two fields share a row when their centres are within half the smaller height), top
    to bottom, left to right; a radio group is one stop at its first button. ``explicit``: by
    ``tab``. Returns the entries in widget order (radio buttons of a group together)."""
    settings = form_settings(state)
    if settings["tab_order"] == "explicit":
        ordered = sorted(entries, key=lambda e: (e[0]["field"].get("tab", 10**6), e[1][1], e[1][0]))
    else:
        items = sorted(entries, key=lambda e: e[1][1] + e[1][3] / 2)
        rows = []
        for entry in items:
            cy, h = entry[1][1] + entry[1][3] / 2, entry[1][3]
            if rows and abs(cy - rows[-1]["cy"]) <= min(h, rows[-1]["h"]) / 2:
                rows[-1]["items"].append(entry)
            else:
                rows.append({"cy": cy, "h": h, "items": [entry]})
        ordered = [entry for row in rows for entry in sorted(row["items"], key=lambda e: e[1][0])]
    result, placed = [], set()
    for entry in ordered:
        record = entry[0]["field"]
        if record["kind"] == "radio":
            if record["key"] in placed:
                continue
            placed.add(record["key"])
            result += [e for e in ordered if e[0]["field"]["kind"] == "radio" and e[0]["field"]["key"] == record["key"]]
        else:
            result.append(entry)
    return result


def label_text(view, layer, resolved=None):
    """A field's accessible name: its label, or its label layer's text."""
    record = layer["field"]
    if record.get("tooltip"):
        return record["tooltip"]
    if record.get("label"):
        return plain_label(record["label"])
    if record.get("label_layer"):
        resolved = resolved or {}
        target = resolved.get(record["label_layer"])
        if target is None:
            target = next((item for item in view.state["layers"] if item["id"] == record["label_layer"]), None)
        if target and target.get("type") == "text":
            from .variables import substitute, with_maps

            return plain_label(substitute(target.get("text", ""), with_maps(view.state.get("variables", {}),
                                                                            view.state.get("maps"))))
    return ""


def plain_label(text):
    """A label without its required marker (a trailing or leading ``*``/``†``, ``(required)``), so screen
    readers say "Email" for "Email *"."""
    text = re.sub(r"\s*\(required\)\s*$", "", text.strip(), flags=re.I)
    text = re.sub(r"\s*[*\u2020\u2217\u204e]+\s*(?=(\(|$))", " ", text).strip()
    return re.sub(r"^[*\u2020]+\s*", "", text) or text


def summary(project, page=None):
    """Field summary for inspect and ``field list``: key, kind, required, tab stop, rectangle in
    points (PDF coordinates, origin bottom left) and page."""
    from .render import view_page

    if not has_fields(project):
        return []
    state = project.state
    k = 72 / (state["canvas"].get("dpi") or 72)
    records = state.get("pages") or [None]
    result = []
    for record in records:
        if page is not None and record is not None and page not in (record["id"], record["name"]):
            continue
        view = view_page(project, record["id"]) if record else project
        entries, resolved, _, _ = field_geometry(view)
        height = view.state["canvas"]["height"] * k
        stop = 0
        seen = set()
        for item, (x, y, w, h), _ in tab_order(state, entries):
            f = item["field"]
            if f["kind"] != "radio" or f["key"] not in seen:
                stop += 1
                seen.add(f["key"])
            result.append({
                "key": f["key"], "layer": item["name"], "kind": f["kind"], "required": bool(f.get("required")),
                **({"option": f["option"]} if f["kind"] == "radio" else {}),
                "tab": stop, "rect_pt": [round(x * k, 2), round(height - (y + h) * k, 2), round((x + w) * k, 2),
                                         round(height - y * k, 2)],
                **({"page": record["name"]} if record else {}),
                "label": label_text(view, item, resolved)[:120],
            })
    return result


def draw_overlay(image, project, scale=1.0, offset=(0, 0)):
    """Outline every field over a render with its key and tab number (``--show-fields``).
    ``offset`` is the document position of the image's top-left corner."""
    from PIL import ImageDraw, ImageFont

    entries, _, _, _ = field_geometry(project)
    draw = ImageDraw.Draw(image)
    size = max(10, round(min(image.width, image.height) / 70))
    font = ImageFont.load_default(size=size)
    stop, seen = 0, set()
    for item, (x, y, w, h), _ in tab_order(project.state, entries):
        f = item["field"]
        if f["kind"] != "radio" or f["key"] not in seen:
            stop += 1
            seen.add(f["key"])
        ox, oy = offset
        box = [(x - ox) * scale, (y - oy) * scale, (x + w - ox) * scale, (y + h - oy) * scale]
        color = (214, 40, 92, 255) if f.get("required") else (24, 110, 230, 255)
        draw.rectangle(box, outline=color, width=max(1, round(size / 6)))
        text = f"{stop} {f['key']}" + (f"={f['option']}" if f["kind"] == "radio" else "") + ("*" if f.get("required") else "")
        tw = draw.textlength(text, font=font)
        tag = [box[0], max(0, box[1] - size - 4), box[0] + tw + 6, max(size + 4, box[1])]
        draw.rectangle(tag, fill=color)
        draw.text((tag[0] + 3, tag[1] + 1), text, fill=(255, 255, 255, 255), font=font)
    return image


# ---------------------------------------------------------------------------------------------
# Checks


def winansi(text):
    try:
        text.encode("cp1252")
        return True
    except UnicodeEncodeError:
        return False


def default_length(record):
    """How many characters the worst-case sample has when a text field sets no ``max_length``."""
    return 12 if record.get("format") == "digits" else 40 if record["kind"] == "text" else 400


def worst_text(record, length):
    """The widest text of ``length`` characters a text field can hold: W's, 8's for digits and a
    long address for email. A multiline value wraps, so its W's come in words of seven (one
    unbroken word could never fit by shortening it)."""
    if record.get("format") == "digits":
        return "8" * length
    if record.get("format") == "email":
        return "w" * max(1, min(length, 64) - 12) + "@example.com"
    if record["kind"] == "multiline":
        return " ".join(["W" * 7] * (length // 8 + 1))[:length]
    return "W" * length


def worst_values(project):
    """The longest values each field allows: ``max_length`` W's (see ``worst_text``), the longest
    option label, the largest number."""
    values = {}
    for _, layer in all_fields(project):
        record = layer["field"]
        kind = record["kind"]
        if kind in ("text", "multiline"):
            values[record["key"]] = worst_text(record, record.get("max_length", default_length(record)))
        elif kind == "number":
            fmt = record.get("format") or {}
            values[record["key"]] = fmt.get("max", 10 ** min(record.get("max_length", 9), 15) - 1)
        elif kind == "date":
            values[record["key"]] = "2026-12-28"
        elif kind == "dropdown":
            values[record["key"]] = max(option_values(record), key=lambda v: len(str(option_label(record, v))))
        elif kind == "checkbox":
            values[record["key"]] = True
        elif kind == "radio":
            values.setdefault(record["key"], record["option"])
    return values


def sample_rows(project, sample):
    if sample == "worst":
        return [worst_values(project)]
    _, rows = read_rows(sample)
    return rows


def check_form(candidate, resolved, local_bounds, projection, layers, issue, sample=None):
    """The ``form`` check family (see docs/forms.md)."""
    import numpy as np

    from .checks import _contains, _intersects
    from .render import color

    fields = [item for item in resolved.values() if item["type"] == "field"]
    if not fields and not sample:
        return
    state = candidate.state
    c = state["canvas"]
    width, height = c["width"], c["height"]
    bounds = projection["bounds"]
    unit = px_per_pt(state)
    if fields and not c.get("dpi"):
        issue("form", "warning", "The canvas has no physical size (dpi), so the PDF maps one pixel to one point; "
              "start from a paper size such as letter or a4", [])
    visible_ids = {item["id"] for item in layers}
    entries = [(item, bounds[item["id"]], projection["matrices"][item["id"]]) for item in fields if item["id"] in visible_ids]
    keys = {}
    for item in fields:
        keys.setdefault(item["field"]["key"], []).append(item)
    for key, members in keys.items():
        if members[0]["field"]["kind"] == "radio" and len(all_group(candidate, key)) < 2:
            issue("form", "error", f"Radio group {key!r} has fewer than two options", members)
    settings = form_settings(state)
    if settings["tab_order"] == "explicit":
        tabs = [item["field"].get("tab") for item in fields if item["field"]["kind"] != "radio" or item is keys[item["field"]["key"]][0]]
        if None in tabs or len(set(tabs)) != len(tabs):
            issue("form", "error", "Explicit tab order needs a different tab number on every field (one per radio group)",
                  [item for item in fields if item["field"].get("tab") is None])
        else:
            ordered = sorted((item for item in entries), key=lambda e: e[0]["field"].get("tab", 0))
            for previous, current in zip(ordered, ordered[1:]):
                if current[1][1] + current[1][3] < previous[1][1]:
                    issue("form", "warning", f"Tab order jumps back up the page from {previous[0]['name']!r} to "
                          f"{current[0]['name']!r}", [previous[0], current[0]])
    bleed = c.get("bleed", 0)
    trim = (bleed, bleed, width - 2 * bleed, height - 2 * bleed)
    for item, box, matrix in entries:
        record = item["field"]
        if transformed(matrix):
            issue("form", "error", f"{item['name']!r} is rotated or flipped (or inside a rotated or flipped group); "
                  "PDF fields are upright rectangles", [item])
        if not _contains((0, 0, width, height), box):
            issue("form", "error", f"{item['name']!r} is outside the page", [item], bounds=list(box))
        elif bleed and not _contains(trim, box):
            issue("form", "error", f"{item['name']!r} crosses the trim line", [item], bounds=list(box))
        if not label_text(candidate, item, resolved):
            issue("form", "error", f"{item['name']!r} has no accessible name: set label, or label_layer to a text layer "
                  "with text", [item])
        if record["kind"] == "radio" and not any(m["field"].get("group_label") for m in all_group(candidate, record["key"])):
            issue("form", "error", f"Radio group {record['key']!r} needs a group_label (the question it asks)", [item])
        texts = [str(record["default"])] if "default" in record and isinstance(record["default"], str) else []
        texts += [str(option_label(record, v)) for v in option_values(record)] + option_values(record)
        if any(not winansi(text) for text in texts):
            entry = "standard entry font (Helvetica" if settings["entry_font"] == "standard" else "embedded entry font ("
            issue("form", "error", f"{item['name']!r} has a default or option the {entry}"
                  "Western European characters) cannot show", [item])
        if settings["entry_font"] == "embed" and record["kind"] in TEXT_KINDS + ("dropdown",):
            from .pdf_forms import entry_font_problem
            from .text import primary_font_data

            problem = entry_font_problem(primary_font_data(candidate, _text_layer(item, "", 16)))
            if problem:
                issue("form", "warning", f"{item['name']!r} will be typed in Helvetica in the fillable PDF: its font "
                      f"cannot be embedded ({problem})", [item])
        size = float(item.get("size", 16)) * projection["scales"][item["id"]]
        if record["kind"] in TEXT_KINDS + ("dropdown",):
            inner = box[3] - 2 * float(item.get("padding", 0)) * projection["scales"][item["id"]]
            if inner < 1.2 * size:
                issue("form", "warning", f"{item['name']!r} is too short for its {size:g} px text; make the box at least "
                      f"{math.ceil(1.2 * size + 2 * item.get('padding', 0))} px tall", [item])
            if size < 8 * unit:
                issue("form", "warning", f"{item['name']!r} draws values at {size / unit:.1f} pt (below 8 pt)", [item])
        if record["kind"] == "date" and not date_picture((record.get("format") or {}).get("display", "YYYY-MM-DD")):
            issue("form", "warning", f"{item['name']!r} draws dates with literal text a PDF viewer cannot enforce; the "
                  "fillable PDF accepts any text there (use only YYYY, MM, M, DD, D and - / . , or space)", [item])
        if record["kind"] in ("checkbox", "radio") and min(box[2], box[3]) < 10 * unit:
            issue("form", "warning", f"{item['name']!r} is smaller than 10 pt; it is hard to hit", [item])
        if item["opacity"] < 1 or item.get("blend", "normal") != "normal" or item.get("effects"):
            issue("form", "warning", f"{item['name']!r} has opacity, a blend mode or effects; the PDF field drawn over "
                  "it will not match", [item])
        if record.get("label_layer") in resolved:
            label_box = bounds.get(record["label_layer"])
            if label_box:
                gap = max(label_box[0] - (box[0] + box[2]), box[0] - (label_box[0] + label_box[2]),
                          label_box[1] - (box[1] + box[3]), box[1] - (label_box[1] + label_box[3]), 0)
                if gap > 2 * box[3]:
                    issue("form", "warning", f"{item['name']!r} is far from its label layer", [item])
    for i, (first, a, _) in enumerate(entries):
        for second, b, _ in entries[i + 1:]:
            if _intersects(a, b):
                left, top = max(a[0], b[0]), max(a[1], b[1])
                if min(a[0] + a[2], b[0] + b[2]) - left > 0.5 and min(a[1] + a[3], b[1] + b[3]) - top > 0.5:
                    issue("form", "error", f"Fields {first['name']!r} and {second['name']!r} overlap", [first, second])
    order = [item["id"] for item in layers]
    for item, box, _ in entries:
        above = [other for other in layers[order.index(item["id"]) + 1:]
                 if other["type"] not in ("field", "group", "adjustment") and other["id"] in bounds
                 and _intersects(bounds[other["id"]], box) and other.get("role") != "background"
                 and not any(p == item["id"] for p in _ancestors(other, resolved))]
        if above:
            issue("form", "warning", f"{above[0]['name']!r} is drawn above field {item['name']!r}; the artwork and the "
                  "PDF field will disagree", [item, above[0]])
    referenced = set(keys)
    for item in layers:
        if item["type"] == "text":
            original = next((x for x in state["layers"] if x["id"] == item["id"]), None)
            text = (original or {}).get("text", "")
            used = sorted(k for k in referenced if "${" + k + "}" in text)
            if used:
                issue("form", "warning", f"{item['name']!r} shows field value(s) {', '.join(used)}; in a fillable PDF it "
                      "keeps the default and does not follow typing", [item])
    if entries:
        _contrast_issues(candidate, entries, issue, color, np)
    radios = {item["field"]["option"] for item in fields if item["field"]["kind"] == "radio"}
    unreadable = sorted(option for option in radios if not re.fullmatch(r"[A-Za-z][A-Za-z0-9 _-]*", option))
    if unreadable:
        issue("form", "warning", f"Radio option values {', '.join(map(repr, unreadable[:6]))} are not readable words; "
              "some screen readers announce them", [])
    if sample:
        for number, row in enumerate(sample_rows(candidate, sample), 1):
            label = "worst-case values" if sample == "worst" else f"row {number}"
            try:
                view = with_values(candidate, row, unknown="ignore", row=None if sample == "worst" else number,
                                   complete=sample != "worst", rules=sample != "worst")
            except VixlError as exc:
                for error in exc.details.get("errors", []):
                    issue("form", "error", f"Sample {label}: {error['message']}", [], key=error["key"], code=error["code"])
                continue
            for report in overflow_report(view, reveal=sample == "worst", suggest=sample == "worst"):
                issue("form", "error" if report["code"] == "overflow" else "warning", f"Sample {label}: {report['message']}",
                      [], key=report["key"], code=report["code"], measured=report.get("measured"))


def _ancestors(item, resolved):
    while item.get("parent"):
        yield item["parent"]
        item = resolved.get(item["parent"]) or {}


def all_group(project, key):
    return [layer for _, layer in all_fields(project) if layer["field"]["key"] == key and layer["field"]["kind"] == "radio"]


def _contrast_issues(candidate, entries, issue, color, np):
    """Non-text contrast (WCAG 1.4.11): a field's border, underline or fill against what is
    behind it, sampled from one render without the fields."""
    from .colors import contrast_ratio
    from .design import resolve_color
    from .render import render

    backdrop = candidate.clone()
    backdrop._disk_cache = None
    hidden = {item["id"] for item, _, _ in entries}
    for layer in backdrop.state["layers"]:
        if layer["id"] in hidden:
            layer["visible"] = False
    image = np.asarray(render(backdrop).convert("RGBA")).astype(float)
    canvas_rgba = color(resolve_color(candidate.state["canvas"]["background"], candidate.state))
    alpha = image[..., 3:4] / 255
    base = np.array(canvas_rgba[:3] if canvas_rgba[3] else (255, 255, 255), float)
    rgb = image[..., :3] * alpha + base * (1 - alpha)
    height, width = rgb.shape[:2]
    for item, (x, y, w, h), _ in entries:
        appearance = {**default_appearance(candidate.state, item["field"]["kind"]), **(item.get("appearance") or {})}
        style = appearance.get("style", "box")
        x0, y0, x1, y1 = max(0, int(x)), max(0, int(y)), min(width, int(x + w)), min(height, int(y + h))
        if x1 <= x0 or y1 <= y0:
            continue
        ring = max(2, round(min(w, h) * 0.15))
        outer = rgb[max(0, y0 - ring):min(height, y1 + ring), max(0, x0 - ring):min(width, x1 + ring)]
        under = rgb[y0:y1, x0:x1]
        if style == "none":
            if float(under.reshape(-1, 3).std(axis=0).max()) < 2:
                issue("form", "warning", f"{item['name']!r} has style none and nothing is drawn under it, so people "
                      "cannot see where to write", [item])
            continue
        behind = np.median(outer.reshape(-1, 3), axis=0)
        ratios = []
        stroke = color(resolve_color(appearance.get("stroke", "transparent"), candidate.state))
        if stroke[3] > 0 and appearance.get("stroke_width", 1) > 0:
            ratios.append(contrast_ratio(tuple(v / 255 for v in stroke[:3]), tuple(v / 255 for v in behind)))
        fill = color(resolve_color(appearance.get("fill", "transparent"), candidate.state))
        if fill[3] > 0 and style == "box":
            ratios.append(contrast_ratio(tuple(v / 255 for v in fill[:3]), tuple(v / 255 for v in behind)))
        if ratios and max(ratios) < 3:
            issue("form", "warning", f"{item['name']!r} {'border' if style == 'box' else 'underline'} has "
                  f"{max(ratios):.2f}:1 contrast against its surroundings (needs 3:1 to be seen)", [item],
                  contrast=round(max(ratios), 2))


def overflow_report(view, *, reveal=False, suggest=False):
    """[{key, code, message, measured}] for values that overflow their boxes (``overflow``) or are
    clipped (``clipped``) in a view with values. ``measured`` is ``fit_details`` and the message
    ends with what it says (sizes, rendered width, box, font); ``reveal`` and ``suggest`` are for
    worst-case samples, which are not personal data."""
    from .render import view_page

    reports = []
    records = view.state.get("pages") or [None]
    for record in records:
        page = view_page(view, record["id"]) if record else view
        entries, _, _, _ = field_geometry(page)
        for item, _, _ in entries:
            value, display = item.get("value", (None, ""))
            if not display or item["field"]["kind"] not in TEXT_KINDS:
                continue
            key = item["field"]["key"]
            if item["field"].get("comb") and len(display) > item["field"]["max_length"]:
                reports.append({"key": key, "code": "too_long", "message": f"{key}: the value has more characters than cells"})
                continue
            _, status, tried = _fit(page, item, display)
            if status in ("overflow", "clipped"):
                details = fit_details(page, item, display, status, tried, reveal=reveal, suggest=suggest)
                said = "does not fit its box" if status == "overflow" else "is clipped by its box"
                reports.append({"key": key, "code": status, "message": f"{key}: the value {said}. {explain_fit(details)}",
                                "measured": details})
    return reports


# ---------------------------------------------------------------------------------------------
# Filling


def read_rows(path, limit=10000):
    """CSV rows for filling (shared with ``render --data``): UTF-8 with an optional BOM, unique
    non-empty headers, at most ``limit`` rows and 8 MiB."""
    from .exports import read_csv

    return read_csv(path, limit)


SAFE_NAME = re.compile(r"[^\w.-]+")


def output_name(template, row, number, suffix):
    def replace(match):
        token = match[1]
        if token == "row":
            return f"{number:04d}"
        require(token in row, f"Name template uses {{{token}}}, which is not a CSV column", field="name")
        return str(row[token])

    name = re.sub(r"\{([\w-]+)\}", replace, template)
    name = SAFE_NAME.sub("-", name).strip("-.")[:120] or f"{number:04d}"
    return name + suffix


def fill(project, values, path=None, *, format=None, mode="flatten", unknown="error", dpi=None, overwrite=False,
         **options):
    """Fill the form with ``values`` and export it. ``flatten`` draws the values into the artwork
    (any format); ``editable`` writes a fillable PDF with the values set. Returns a report;
    nothing is written to the document."""
    require(mode in ("flatten", "editable"), "mode must be flatten or editable", field="mode")
    view = with_values(project, values, unknown=unknown)
    warnings = [r for r in overflow_report(view)]
    errors = [r for r in warnings if r["code"] in ("overflow", "too_long")]
    if errors:
        raise VixlError("form_values_invalid", f"{len(errors)} value(s) do not fit: " + "; ".join(e["message"] for e in errors[:5]),
                        errors=errors)
    suffix = Path(path).suffix.lower() if path else ""
    if mode == "editable":
        require(suffix == ".pdf" or (format or "").upper() == "PDF", "Editable fills write a PDF", field="mode")
        data = project.export(None, fillable=True, values=values, dpi=dpi, **options)
    else:
        fmt = (format or suffix.lstrip(".") or "PNG").upper()
        if fmt == "PDF":
            options.setdefault("pdf_content", "vector")
        data = view.export(None, format=fmt, dpi=dpi, **options)
    if path:
        target = Path(path)
        require(overwrite or not target.exists(), "Output already exists", field="path")
        from .production import write_bytes

        write_bytes(target, data, replace=overwrite)
    return {"output": str(path) if path else None, "bytes": len(data), "warnings": [w for w in warnings if w not in errors]}


def fill_data(project, csv_path, directory=None, *, combine=None, name="{row}", format="pdf", mode="flatten",
              skip_invalid=False, dry_run=False, check=None, unknown="error", dpi=None, cancelled=None, progress=None,
              rows=None, **options):
    """Fill the form once per CSV row: one file per row in ``directory`` (named by the ``name``
    template of ``{column}`` and ``{row}``), or every row in one ``combine`` PDF. Every row is
    validated first; a bad row fails the batch unless ``skip_invalid``. ``dry_run`` only
    validates."""
    import shutil
    import tempfile

    require(bool(directory) != bool(combine) or dry_run, "Give an output directory or a combine PDF (not both)",
            field="output")
    require(mode in ("flatten", "editable"), "mode must be flatten or editable", field="mode")
    require(check in (None, "design"), "check is design or omitted", field="check")
    if rows is None:
        _, rows = read_rows(csv_path)
    require(rows, "The data has no rows", field="data")
    fmt = (format or "pdf").lower().lstrip(".")
    require(fmt in ("pdf", "png", "jpg", "jpeg", "webp", "tiff", "svg"), "format is pdf, png, jpeg, webp, tiff or svg",
            field="format")
    require(mode == "flatten" or fmt == "pdf", "Editable fills write PDF", field="mode")
    if combine:
        require(len(rows) <= 1000, "A combined PDF holds at most 1000 rows", "resource_limit", field="combine")
        require(Path(combine).suffix.lower() == ".pdf", "combine writes a .pdf file", field="combine")
        require(mode == "flatten", "Combined PDFs are flattened", field="mode")
    # Preflight: validate every row before rendering anything.
    report = {"rows": len(rows), "valid": 0, "invalid": [], "errors": [], "warnings": []}
    views = []
    for number, row in enumerate(rows, 1):
        try:
            view = with_values(project, row, unknown=unknown, row=number)
        except VixlError as exc:
            report["invalid"].append(number)
            report["errors"] += exc.details.get("errors", [])
            views.append(None)
            continue
        problems = overflow_report(view)
        for problem in problems:
            entry = {"row": number, "key": problem["key"], "code": problem["code"],
                     "message": f"Row {number}, {problem['message']}", **({"measured": problem["measured"]}
                                                                          if "measured" in problem else {})}
            if problem["code"] in ("overflow", "too_long"):
                report["errors"].append(entry)
            else:
                report["warnings"].append(entry)
        if any(p["code"] in ("overflow", "too_long") for p in problems):
            report["invalid"].append(number)
            views.append(None)
            continue
        if check == "design":
            from .checks import check_design

            result = check_design(view, checks=["bounds", "overlap", "contrast", "fonts", "form"])
            if not result["passed"]:
                report["invalid"].append(number)
                report["errors"] += [{"row": number, "code": "design", "key": None,
                                      "message": f"Row {number}: {issue['message']}"}
                                     for issue in result["issues"] if issue["severity"] == "error"]
                views.append(None)
                continue
        views.append(view)
    report["valid"] = sum(1 for view in views if view is not None)
    if dry_run:
        report["dry_run"] = True
        return report
    if report["invalid"] and not skip_invalid:
        raise VixlError("form_fill_failed", f"{len(report['invalid'])} row(s) failed validation; nothing was written "
                        "(use skip_invalid to write the valid rows)", report=report)
    require(report["valid"], "No valid rows to write", "form_fill_failed", report=report)
    if combine:
        target = Path(combine)
        require(not target.exists(), "Combined output already exists", field="combine")
        from .pdf_export import export_pdf, page_views

        selected = [(n, view) for n, view in enumerate(views, 1) if view is not None]
        estimate = sum(view.state["canvas"]["width"] * view.state["canvas"]["height"] for _, view in selected[:1]) * len(selected)
        require(estimate <= 512 * 1024 * 1024 * 4, "The combined PDF would be too large; lower dpi or split the data",
                "resource_limit", field="combine")
        pages = []
        for number, view in selected:
            if cancelled and cancelled():
                raise VixlError("cancelled", "Form fill cancelled")
            for label, page in page_views(view):
                pages.append((f"{number:04d}-{label}", page))
        data = export_pdf(project, None, views=pages, dpi=dpi, content=options.get("pdf_content", "vector"))
        require(len(data) <= 512 * 1024 * 1024, "The combined PDF exceeds 512 MiB", "resource_limit")
        from .production import write_bytes

        write_bytes(target, data)
        report["output"] = str(target)
        report["bytes"] = len(data)
        return report
    root = Path(directory)
    suffix = "." + ("jpg" if fmt == "jpeg" else fmt)
    names = {}
    for number, view in enumerate(views, 1):
        if view is None:
            continue
        filename = output_name(name, rows[number - 1], number, suffix)
        require(filename not in names, f"Rows {names.get(filename)} and {number} would both be named {filename!r}",
                "invalid_operation", field="name")
        names[filename] = number
    require(not any((root / filename).exists() for filename in names), "Output files already exist; choose an empty "
            "directory", field="output")
    outputs = []
    staging = Path(tempfile.mkdtemp(prefix="vixl-form-"))
    try:
        for done, (filename, number) in enumerate(names.items(), 1):
            if cancelled and cancelled():
                raise VixlError("cancelled", "Form fill cancelled")
            view = views[number - 1]
            if mode == "editable":
                data = project.export(None, fillable=True, values=rows[number - 1], dpi=dpi, unknown=unknown)
            else:
                extra = {"pdf_content": options.get("pdf_content", "vector")} if fmt == "pdf" else {}
                data = view.export(None, format={"jpg": "JPEG"}.get(fmt, fmt.upper()), dpi=dpi, **extra)
            (staging / filename).write_bytes(data)
            outputs.append({"row": number, "output": str(root / filename)})
            if progress:
                progress({"done": done, "total": len(names)})
        root.mkdir(parents=True, exist_ok=True)
        for filename in names:
            with (root / filename).open("xb") as stream:
                stream.write((staging / filename).read_bytes())
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    report["outputs"] = outputs
    return report


# ---------------------------------------------------------------------------------------------
# CLI


def compile_command(cmd, args):
    """``vixl field add|set …`` and ``vixl form settings …`` (``field list`` and ``form fill``
    are document commands)."""
    if cmd not in ("field", "form", "field-set"):
        return None
    import json

    from .commands import Parser

    if cmd == "form":
        p = Parser(prog="vixl form")
        p.add_argument("action", choices=["settings"], help="settings (form fill is a document command)")
        p.add_argument("--tab-order", choices=["reading", "explicit"])
        p.add_argument("--entry-font", choices=["standard", "embed"])
        p.add_argument("--title")
        p.add_argument("--lang")
        data = {k: v for k, v in vars(p.parse_args(args)).items() if v is not None}
        data.pop("action")
        return {"type": "form", **data}
    p = Parser(prog=f"vixl {cmd}")
    if cmd == "field":
        p.add_argument("action", choices=["add", "set"])
    p.add_argument("target", help="add: the field key (and layer name); set: the field layer")
    p.add_argument("--kind")
    p.add_argument("--name", help="add: a layer name other than the key")
    for key in ("label", "label-layer", "group-label", "option", "on-value", "font", "color", "fill", "stroke", "mark-color",
                "default", "pattern", "message"):
        p.add_argument("--" + key)
    for key in ("x", "y", "width", "height"):
        p.add_argument("--" + key)
    for key in ("size", "padding", "min-size", "stroke-width", "radius"):
        p.add_argument("--" + key, type=float)
    for key in ("max-length", "tab"):
        p.add_argument("--" + key, type=int)
    for flag in ("required", "read-only", "comb", "editable"):
        p.add_argument("--" + flag, action="store_true", default=None)
        p.add_argument("--not-" + flag, dest=flag.replace("-", "_"), action="store_false")
    p.add_argument("--format", help="text: email or digits; number/date: JSON such as {\"decimals\": 2}")
    p.add_argument("--options", help="Dropdown options: JSON list, or comma-separated values")
    p.add_argument("--overflow", choices=list(OVERFLOW))
    p.add_argument("--align", choices=["left", "center", "right"])
    p.add_argument("--style", choices=list(STYLES))
    p.add_argument("--mark", choices=list(MARKS))
    a = vars(p.parse_args(args))
    action = a.pop("action", "set")
    target = a.pop("target")
    data = {k: v for k, v in a.items() if v is not None}
    for key in ("x", "y", "width", "height"):
        if key in data and re.fullmatch(r"-?\d+(\.\d+)?", data[key]):
            data[key] = float(data[key]) if "." in data[key] else int(data[key])
    if "options" in data:
        text = data["options"]
        data["options"] = json.loads(text) if text.lstrip().startswith("[") else [v.strip() for v in text.split(",") if v.strip()]
    if "format" in data and data["format"].lstrip().startswith("{"):
        data["format"] = json.loads(data["format"])
    for key in ("x", "y", "width", "height", "size", "padding"):
        if isinstance(data.get(key), float) and data[key].is_integer():
            data[key] = int(data[key])
    op = {"type": "field" if action == "add" else "field-set"}
    if action == "add":
        op["key"] = target
        op["name"] = data.pop("name", target)
    else:
        op["target"] = target
        data.pop("name", None)
    return {**op, **data}
